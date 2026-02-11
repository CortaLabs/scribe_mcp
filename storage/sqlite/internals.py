"""Low-level SQLite connection/pool operations for SQLiteStorage."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional

from scribe_mcp.storage.pool import SQLiteConnectionPool

SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = 5000


class SQLiteInternals:
    """Encapsulate low-level DB access helpers shared by SQLiteStorage."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser()
        self.pool: Optional[SQLiteConnectionPool] = None

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
        if self.pool:
            conn = self.pool.acquire()
            try:
                conn.execute(query, params)
                conn.commit()
            finally:
                self.pool.release(conn)
            return

        conn = self.connect()
        try:
            conn.execute(query, params)
            conn.commit()
        finally:
            conn.close()

    async def execute_many(self, statements: List[str]) -> None:
        await asyncio.to_thread(self.execute_many_sync, statements)

    def execute_many_sync(self, statements: List[str]) -> None:
        if self.pool:
            conn = self.pool.acquire()
            try:
                for statement in statements:
                    conn.execute(statement)
                conn.commit()
            finally:
                self.pool.release(conn)
            return

        conn = self.connect()
        try:
            for statement in statements:
                conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    async def fetchone(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        return await asyncio.to_thread(self.fetchone_sync, query, params)

    def fetchone_sync(self, query: str, params: tuple[Any, ...]) -> Optional[sqlite3.Row]:
        if self.pool:
            conn = self.pool.acquire()
            try:
                cursor = conn.execute(query, params)
                row = cursor.fetchone()
                return row
            finally:
                self.pool.release(conn)

        conn = self.connect()
        try:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return row
        finally:
            conn.close()

    async def fetchall(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        return await asyncio.to_thread(self.fetchall_sync, query, params)

    def fetchall_sync(self, query: str, params: tuple[Any, ...] | tuple = ()) -> List[sqlite3.Row]:
        if self.pool:
            conn = self.pool.acquire()
            try:
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                return rows
            finally:
                self.pool.release(conn)

        conn = self.connect()
        try:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return rows
        finally:
            conn.close()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=SQLITE_TIMEOUT_SECONDS,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
        return conn
