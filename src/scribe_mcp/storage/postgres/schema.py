"""Schema bootstrap helpers for Postgres storage."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Awaitable, Callable

import asyncpg

from scribe_mcp.config.paths import db_init_sql, postgres_migrations_dir

SCHEMA_PATH = db_init_sql()
MIGRATIONS_PATH = postgres_migrations_dir()
PG_TRGM_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

LOGGER = logging.getLogger(__name__)

_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MIGRATION_FILE_RE = re.compile(r"^\d{3}_[A-Za-z0-9_]+\.sql$")


def _validate_schema_name(schema_name: str) -> str:
    candidate = (schema_name or "scribe").strip()
    if not candidate:
        return "scribe"
    if not _SCHEMA_NAME_RE.match(candidate):
        raise ValueError(f"Invalid Postgres schema name: {schema_name!r}")
    return candidate


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _is_duplicate_index_race(statement: str, exc: asyncpg.PostgresError) -> bool:
    """Allow idempotent index create races during startup schema bootstrap."""
    if "CREATE INDEX" not in statement.upper():
        return False
    return "pg_class_relname_nsp_index" in str(exc)


def _is_additive_index_before_migration(statement: str, exc: asyncpg.PostgresError) -> bool:
    """Allow additive indexes to be created by their migration after legacy tables upgrade."""
    normalized = " ".join(statement.upper().split())
    if "CREATE INDEX" not in normalized:
        return False
    if "IDX_TOOL_CALLS_CORRELATION" not in normalized:
        return False
    return "correlation_id" in str(exc)


async def _ensure_migration_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scribe_migrations (
            name TEXT PRIMARY KEY,
            completed_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )


async def _apply_numbered_migrations(
    *,
    conn: asyncpg.Connection,
    migrations_path: Path,
) -> None:
    if not migrations_path.exists():
        return

    migration_files = sorted(
        path for path in migrations_path.iterdir()
        if path.is_file() and _MIGRATION_FILE_RE.match(path.name)
    )

    for migration_file in migration_files:
        migration_name = f"sql:{migration_file.name}"
        already_applied = await conn.fetchval(
            "SELECT 1 FROM scribe_migrations WHERE name = $1 LIMIT 1;",
            migration_name,
        )
        if already_applied:
            continue

        sql_text = await asyncio.to_thread(migration_file.read_text, encoding="utf-8")
        if sql_text.strip():
            await conn.execute(sql_text)
        await conn.execute(
            """
            INSERT INTO scribe_migrations (name, completed_at)
            VALUES ($1, NOW())
            ON CONFLICT (name) DO UPDATE SET completed_at = NOW();
            """,
            migration_name,
        )
        LOGGER.info("Applied Postgres schema migration: %s", migration_file.name)


async def ensure_schema_on_connection(
    *,
    conn: asyncpg.Connection,
    schema_name: str,
    schema_path: Path = SCHEMA_PATH,
    migrations_path: Path = MIGRATIONS_PATH,
) -> None:
    """Apply idempotent schema DDL using an already-open connection."""
    schema_name = _validate_schema_name(schema_name)
    quoted_schema = _quote_ident(schema_name)

    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema};")
    await conn.execute(PG_TRGM_EXTENSION_SQL)
    await conn.execute(f"SET search_path TO {quoted_schema}, public;")

    if schema_path.exists():
        sql_text = await asyncio.to_thread(schema_path.read_text, encoding="utf-8")
        statements = [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]
        for statement in statements:
            try:
                await conn.execute(statement)
            except asyncpg.UniqueViolationError as exc:
                if _is_duplicate_index_race(statement, exc):
                    LOGGER.warning(
                        "Ignoring duplicate index race during schema bootstrap: %s",
                        statement[:160],
                    )
                    continue
                raise
            except asyncpg.UndefinedColumnError as exc:
                if _is_additive_index_before_migration(statement, exc):
                    LOGGER.warning(
                        "Deferring additive index until Postgres migration runs: %s",
                        statement[:160],
                    )
                    continue
                raise

    await _ensure_migration_table(conn)
    await _apply_numbered_migrations(
        conn=conn,
        migrations_path=migrations_path,
    )


async def ensure_schema(
    *,
    pool_provider: Callable[[], Awaitable[asyncpg.Pool]],
    schema_lock: asyncio.Lock,
    schema_ready: bool,
    schema_name: str,
    schema_path: Path = SCHEMA_PATH,
    migrations_path: Path = MIGRATIONS_PATH,
) -> bool:
    """Ensure DDL from init.sql and numbered migrations are applied exactly once."""
    if schema_ready:
        return True

    schema_name = _validate_schema_name(schema_name)

    async with schema_lock:
        if schema_ready:
            return True

        pool = await pool_provider()
        async with pool.acquire() as conn:
            await ensure_schema_on_connection(
                conn=conn,
                schema_name=schema_name,
                schema_path=schema_path,
                migrations_path=migrations_path,
            )

    return True
