"""Migration helpers for Postgres storage."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

FetchValFn = Callable[..., Awaitable[Any]]
ExecuteFn = Callable[..., Awaitable[str]]


async def migration_completed(fetchval_fn: FetchValFn, name: str) -> bool:
    value = await fetchval_fn(
        """
        SELECT 1
        FROM scribe_migrations
        WHERE name = $1
        LIMIT 1;
        """,
        name,
    )
    return bool(value)


async def mark_migration_complete(execute_fn: ExecuteFn, name: str) -> None:
    await execute_fn(
        """
        INSERT INTO scribe_migrations (name, completed_at)
        VALUES ($1, NOW())
        ON CONFLICT (name) DO UPDATE SET completed_at = NOW();
        """,
        name,
    )


async def run_migration(
    *,
    name: str,
    migration_coro: Callable[[], Awaitable[None]],
    fetchval_fn: FetchValFn,
    execute_fn: ExecuteFn,
    logger: logging.Logger,
) -> bool:
    if await migration_completed(fetchval_fn, name):
        return False
    await migration_coro()
    await mark_migration_complete(execute_fn, name)
    logger.info("Applied Postgres migration: %s", name)
    return True


async def ensure_column(
    *,
    fetchval_fn: FetchValFn,
    execute_fn: ExecuteFn,
    table: str,
    column: str,
    definition: str,
    schema_name: str = "scribe",
) -> None:
    exists = await fetchval_fn(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = $1
          AND table_name = $2
          AND column_name = $3
        LIMIT 1;
        """,
        schema_name,
        table,
        column,
    )
    if exists:
        return
    await execute_fn(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")


async def migrate_add_docs_json_column(
    *,
    execute_fn: ExecuteFn,
) -> bool:
    await execute_fn(
        """
        ALTER TABLE scribe_projects
        ADD COLUMN IF NOT EXISTS docs_json TEXT;
        """
    )
    return True


async def backfill_docs_json_from_state(
    *,
    execute_fn: ExecuteFn,
    state_path: Path,
    logger: logging.Logger,
) -> int:
    path = Path(state_path).expanduser()
    if not path.exists():
        return 0

    try:
        raw_text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        payload = json.loads(raw_text)
    except Exception as exc:
        logger.warning("Could not load state file for docs_json backfill (%s): %s", path, exc)
        return 0

    projects = payload.get("projects")
    if not isinstance(projects, dict):
        return 0

    updated = 0
    for name, project_state in projects.items():
        if not isinstance(project_state, dict):
            continue
        docs = project_state.get("docs")
        if not isinstance(docs, dict) or not docs:
            continue

        tag = await execute_fn(
            """
            UPDATE scribe_projects
            SET docs_json = $1, updated_at = NOW()
            WHERE name = $2
              AND (docs_json IS NULL OR docs_json = '');
            """,
            json.dumps(docs, sort_keys=True),
            str(name),
        )
        try:
            updated += int(str(tag).split()[-1])
        except Exception:
            pass
    return updated
