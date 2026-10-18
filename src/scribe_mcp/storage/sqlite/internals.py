"""Low-level SQLite connection/pool operations for SQLiteStorage."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional, TypeVar

from scribe_mcp.storage.pool import SQLiteConnectionPool


def _normalise_sqlite_param(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _normalise_sqlite_params(params: tuple[Any, ...] | tuple) -> tuple[Any, ...]:
    return tuple(_normalise_sqlite_param(value) for value in params)

def _float_env(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


# Interactive defaults: prioritize responsiveness under contention while still retrying.
SQLITE_TIMEOUT_SECONDS = _float_env("SCRIBE_SQLITE_TIMEOUT_SECONDS", 5.0, 0.1)
SQLITE_BUSY_TIMEOUT_MS = _int_env("SCRIBE_SQLITE_BUSY_TIMEOUT_MS", 1000, 10)
SQLITE_LOCK_RETRIES = _int_env("SCRIBE_SQLITE_LOCK_RETRIES", 4, 0)
SQLITE_LOCK_RETRY_BASE_SECONDS = _float_env("SCRIBE_SQLITE_LOCK_RETRY_BASE_SECONDS", 0.02, 0.001)
SQLITE_LOCK_RETRY_MAX_SECONDS = _float_env("SCRIBE_SQLITE_LOCK_RETRY_MAX_SECONDS", 0.25, SQLITE_LOCK_RETRY_BASE_SECONDS)
SQLITE_JOURNAL_MODE = os.environ.get("SCRIBE_SQLITE_JOURNAL_MODE", "WAL")
SQLITE_SYNCHRONOUS = os.environ.get("SCRIBE_SQLITE_SYNCHRONOUS", "NORMAL")
SQLITE_TEMP_STORE = os.environ.get("SCRIBE_SQLITE_TEMP_STORE", "MEMORY")

logger = logging.getLogger(__name__)
T = TypeVar("T")

_SQL_LEADING_COMMENTS_RE = re.compile(r"^\s*(?:(?:--[^\n]*\n)|(?:/\*.*?\*/\s*))*", re.DOTALL)
_WRITE_SQL_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "REPLACE",
    "CREATE",
    "ALTER",
    "DROP",
    "VACUUM",
    "REINDEX",
    "ANALYZE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "RELEASE",
}


class SQLiteInternals:
    """Encapsulate low-level DB access helpers shared by SQLiteStorage."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser()
        self.pool: Optional[SQLiteConnectionPool] = None
        # Serialize writers across all async threads to avoid SQLite write lock fights.
        self._write_gate = threading.Lock()

    async def setup(self, initialise_fn: Callable[[], Awaitable[None]]) -> None:
        await initialise_fn()
        self.pool = SQLiteConnectionPool(self.db_path, min_size=1, max_size=3)

    async def close(self) -> None:
        if self.pool:
            self.pool.close_all()
            self.pool = None

    async def execute(self, query: str, params: tuple[Any, ...]) -> None:
        await asyncio.to_thread(self.execute_sync, query, params)

    def execute_sync(self, query: str, params: tuple[Any, ...]) -> None:
        def _op() -> None:
            with self._write_gate:
                self._run_with_connection(
                    lambda conn: self._execute_write(conn, query, params)
                )

        self._with_lock_retry(_op, query=query, is_write=True)

    async def execute_many(self, statements: List[str]) -> None:
        await asyncio.to_thread(self.execute_many_sync, statements)

    def execute_many_sync(self, statements: List[str]) -> None:
        def _op() -> None:
            with self._write_gate:
                self._run_with_connection(
                    lambda conn: self._execute_many_writes(conn, statements)
                )

        self._with_lock_retry(_op, query="; ".join(statements), is_write=True)

    async def fetchone(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        return await asyncio.to_thread(self.fetchone_sync, query, params)

    def fetchone_sync(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        is_write = self._is_write_query(query)

        def _op() -> Optional[sqlite3.Row]:
            if is_write:
                with self._write_gate:
                    return self._run_with_connection(
                        lambda conn: self._fetchone_write(conn, query, params)
                    )
            return self._run_with_connection(
                lambda conn: self._fetchone_read(conn, query, params)
            )

        return self._with_lock_retry(_op, query=query, is_write=is_write)

    async def fetchall(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        return await asyncio.to_thread(self.fetchall_sync, query, params)

    def fetchall_sync(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        is_write = self._is_write_query(query)

        def _op() -> List[sqlite3.Row]:
            if is_write:
                with self._write_gate:
                    return self._run_with_connection(
                        lambda conn: self._fetchall_write(conn, query, params)
                    )
            return self._run_with_connection(
                lambda conn: self._fetchall_read(conn, query, params)
            )

        return self._with_lock_retry(_op, query=query, is_write=is_write)

    def _run_with_connection(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        if self.pool:
            conn = self.pool.acquire()
            try:
                return fn(conn)
            finally:
                self.pool.release(conn)

        conn = self.connect()
        try:
            return fn(conn)
        finally:
            conn.close()

    def _execute_write(
        self,
        conn: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...],
    ) -> None:
        conn.execute(query, _normalise_sqlite_params(params))
        conn.commit()

    def _execute_many_writes(self, conn: sqlite3.Connection, statements: List[str]) -> None:
        for statement in statements:
            conn.execute(statement)
        conn.commit()

    def _fetchone_read(
        self,
        conn: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...],
    ) -> Optional[sqlite3.Row]:
        cursor = conn.execute(query, _normalise_sqlite_params(params))
        return cursor.fetchone()

    def _fetchall_read(
        self,
        conn: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...] | tuple,
    ) -> List[sqlite3.Row]:
        cursor = conn.execute(query, _normalise_sqlite_params(params))
        return cursor.fetchall()

    def _fetchone_write(
        self,
        conn: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...],
    ) -> Optional[sqlite3.Row]:
        cursor = conn.execute(query, _normalise_sqlite_params(params))
        row = cursor.fetchone()
        if conn.in_transaction:
            conn.commit()
        return row

    def _fetchall_write(
        self,
        conn: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...] | tuple,
    ) -> List[sqlite3.Row]:
        cursor = conn.execute(query, _normalise_sqlite_params(params))
        rows = cursor.fetchall()
        if conn.in_transaction:
            conn.commit()
        return rows

    def _with_lock_retry(
        self,
        fn: Callable[[], T],
        *,
        query: str,
        is_write: bool,
    ) -> T:
        for attempt in range(SQLITE_LOCK_RETRIES + 1):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                if not self._is_locked_error(exc) or attempt >= SQLITE_LOCK_RETRIES:
                    raise
                delay = min(
                    SQLITE_LOCK_RETRY_MAX_SECONDS,
                    SQLITE_LOCK_RETRY_BASE_SECONDS * (2**attempt),
                )
                logger.warning(
                    "SQLite lock contention on %s query (retry %d/%d in %.3fs): %s",
                    "write" if is_write else "read",
                    attempt + 1,
                    SQLITE_LOCK_RETRIES,
                    delay,
                    self._query_preview(query),
                )
                time.sleep(delay)

        # Unreachable: loop always returns or raises.
        raise RuntimeError("SQLite retry loop exhausted unexpectedly")

    @staticmethod
    def _is_locked_error(exc: sqlite3.OperationalError) -> bool:
        msg = str(exc).lower()
        return "database is locked" in msg or "database table is locked" in msg or "database schema is locked" in msg

    @staticmethod
    def _query_preview(query: str, max_len: int = 120) -> str:
        compact = " ".join(query.strip().split())
        if len(compact) <= max_len:
            return compact
        return compact[: max_len - 3] + "..."

    @classmethod
    def _is_write_query(cls, query: str) -> bool:
        stripped = _SQL_LEADING_COMMENTS_RE.sub("", query or "").lstrip()
        if not stripped:
            return False

        upper = stripped.upper()
        first = upper.split(None, 1)[0]

        if first == "WITH":
            return bool(re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", upper))

        return first in _WRITE_SQL_KEYWORDS

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=SQLITE_TIMEOUT_SECONDS,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
        # Enable WAL and moderate sync level for better concurrent read/write behavior.
        conn.execute(f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE};")
        conn.execute(f"PRAGMA synchronous = {SQLITE_SYNCHRONOUS};")
        conn.execute(f"PRAGMA temp_store = {SQLITE_TEMP_STORE};")
        return conn
