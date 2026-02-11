"""Migration helpers for the SQLite storage backend."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

ExecuteFn = Callable[[str, tuple[Any, ...]], Awaitable[None]]
FetchOneFn = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
EnsureColumnFn = Callable[[str, str, str], Awaitable[None]]
EnsureIndexFn = Callable[[str], Awaitable[None]]
NoArgMigrationFn = Callable[[], Awaitable[Any]]
BackfillDocsFn = Callable[[Path], Awaitable[int]]
ConnectFn = Callable[[], Any]
PoolGetterFn = Callable[[], Any]


async def migration_completed(fetchone_fn: FetchOneFn, name: str) -> bool:
    """Check whether a migration has already been recorded as completed."""
    try:
        row = await fetchone_fn(
            "SELECT 1 FROM scribe_migrations WHERE name = ?",
            (name,),
        )
        return row is not None
    except Exception:
        # Table may not exist yet during first bootstrap.
        return False


async def mark_migration_complete(
    execute_fn: ExecuteFn,
    name: str,
    logger: logging.Logger,
) -> None:
    """Record a migration as completed."""
    await execute_fn(
        "INSERT OR IGNORE INTO scribe_migrations (name) VALUES (?)",
        (name,),
    )
    logger.debug("Migration '%s' marked as complete", name)


async def run_migration(
    *,
    name: str,
    migration_coro: Awaitable[Any],
    execute_fn: ExecuteFn,
    fetchone_fn: FetchOneFn,
    logger: logging.Logger,
) -> bool:
    """Run a migration iff not previously completed."""
    if await migration_completed(fetchone_fn, name):
        logger.debug("Skipping migration '%s' (already completed)", name)
        return False
    await migration_coro
    await mark_migration_complete(execute_fn, name, logger)
    logger.debug("Completed migration '%s'", name)
    return True


async def ensure_column(
    connect_fn: ConnectFn,
    table: str,
    column: str,
    definition: str,
) -> None:
    """Ensure a table has a given column."""
    await asyncio.to_thread(
        ensure_column_sync,
        connect_fn,
        table,
        column,
        definition,
    )


def ensure_column_sync(
    connect_fn: ConnectFn,
    table: str,
    column: str,
    definition: str,
) -> None:
    """Sync implementation for ensuring a column exists."""
    conn = connect_fn()
    try:
        cursor = conn.execute(f"PRAGMA table_info({table});")
        existing = {row[1] for row in cursor.fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")
            conn.commit()
    finally:
        conn.close()


async def ensure_index(
    connect_fn: ConnectFn,
    pool_getter_fn: PoolGetterFn,
    statement: str,
) -> None:
    """Ensure an index exists."""
    await asyncio.to_thread(
        ensure_index_sync,
        connect_fn,
        pool_getter_fn,
        statement,
    )


def ensure_index_sync(
    connect_fn: ConnectFn,
    pool_getter_fn: PoolGetterFn,
    statement: str,
) -> None:
    """Sync implementation for ensuring an index exists."""
    pool = pool_getter_fn()
    if pool:
        conn = pool.acquire()
        try:
            conn.execute(statement)
            conn.commit()
        finally:
            pool.release(conn)
        return

    conn = connect_fn()
    try:
        conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


async def run_all_migrations(
    *,
    ensure_column_fn: EnsureColumnFn,
    ensure_index_fn: EnsureIndexFn,
    execute_fn: ExecuteFn,
    fetchone_fn: FetchOneFn,
    migrate_document_sections_fn: NoArgMigrationFn,
    migrate_add_docs_json_column_fn: NoArgMigrationFn,
    backfill_docs_json_from_state_fn: BackfillDocsFn,
    db_path: Path,
    logger: logging.Logger,
) -> None:
    """Run the full tracked migration suite for SQLite storage."""
    if not await migration_completed(fetchone_fn, "projects_extended_columns_v1"):
        logger.debug("Running migration: projects_extended_columns_v1")
        await ensure_column_fn("scribe_projects", "repo_root", "TEXT")
        await ensure_column_fn("scribe_projects", "progress_log_path", "TEXT")
        await ensure_column_fn("scribe_projects", "status", "TEXT")
        await ensure_column_fn("scribe_projects", "phase", "TEXT")
        await ensure_column_fn("scribe_projects", "confidence", "REAL DEFAULT 0.0")
        await ensure_column_fn("scribe_projects", "completed_at", "TIMESTAMP")
        await ensure_column_fn("scribe_projects", "last_activity", "TIMESTAMP")
        await ensure_column_fn("scribe_projects", "description", "TEXT")
        await ensure_column_fn("scribe_projects", "last_entry_at", "TEXT")
        await ensure_column_fn("scribe_projects", "last_access_at", "TEXT")
        await ensure_column_fn("scribe_projects", "last_status_change", "TEXT")
        await ensure_column_fn("scribe_projects", "tags", "TEXT")
        await ensure_column_fn("scribe_projects", "meta", "TEXT")
        await mark_migration_complete(execute_fn, "projects_extended_columns_v1", logger)
    else:
        logger.debug("Skipping migration: projects_extended_columns_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "projects_bridge_columns_v1"):
        logger.debug("Running migration: projects_bridge_columns_v1")
        await ensure_column_fn("scribe_projects", "bridge_id", "TEXT")
        await ensure_column_fn("scribe_projects", "bridge_managed", "INTEGER DEFAULT 0")
        await execute_fn(
            "CREATE INDEX IF NOT EXISTS idx_projects_bridge ON scribe_projects(bridge_id)",
            (),
        )
        await mark_migration_complete(execute_fn, "projects_bridge_columns_v1", logger)
    else:
        logger.debug("Skipping migration: projects_bridge_columns_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "entries_metadata_columns_v1"):
        logger.debug("Running migration: entries_metadata_columns_v1")
        await ensure_column_fn("scribe_entries", "priority", "TEXT")
        await ensure_column_fn("scribe_entries", "category", "TEXT")
        await ensure_column_fn("scribe_entries", "tags", "TEXT")
        await ensure_column_fn("scribe_entries", "confidence", "REAL DEFAULT 1.0")
        await ensure_column_fn("scribe_entries", "log_type", "TEXT DEFAULT 'progress'")
        await mark_migration_complete(execute_fn, "entries_metadata_columns_v1", logger)
    else:
        logger.debug("Skipping migration: entries_metadata_columns_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "document_sections_schema_v1"):
        logger.debug("Running migration: document_sections_schema_v1")
        await migrate_document_sections_fn()
        await ensure_column_fn("document_changes", "project_root", "TEXT")
        await ensure_column_fn("document_changes", "file_path", "TEXT")
        await ensure_column_fn("sync_status", "project_root", "TEXT")
        await ensure_column_fn("sync_status", "relative_path", "TEXT")
        await ensure_column_fn("document_sections", "project_root", "TEXT")
        await ensure_column_fn("document_sections", "file_path", "TEXT")
        await ensure_column_fn("document_sections", "relative_path", "TEXT")
        await ensure_index_fn(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_document_sections_file_path "
            "ON document_sections(project_root, file_path);"
        )
        await ensure_index_fn(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_status_file_path "
            "ON sync_status(project_root, file_path);"
        )
        await mark_migration_complete(execute_fn, "document_sections_schema_v1", logger)
    else:
        logger.debug("Skipping migration: document_sections_schema_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "agent_report_cards_indexes_v1"):
        logger.debug("Running migration: agent_report_cards_indexes_v1")
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_agent_report_cards_project_agent "
            "ON agent_report_cards(project_id, agent_name);"
        )
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_agent_report_cards_stage "
            "ON agent_report_cards(stage);"
        )
        await mark_migration_complete(execute_fn, "agent_report_cards_indexes_v1", logger)
    else:
        logger.debug("Skipping migration: agent_report_cards_indexes_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "entries_metadata_indexes_v1"):
        logger.debug("Running migration: entries_metadata_indexes_v1")
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_entries_priority_ts "
            "ON scribe_entries(priority, ts_iso DESC);"
        )
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_entries_category_ts "
            "ON scribe_entries(category, ts_iso DESC);"
        )
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_entries_project_priority_category "
            "ON scribe_entries(project_id, priority, category, ts_iso DESC);"
        )
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_entries_log_type "
            "ON scribe_entries(project_id, log_type, ts_iso DESC);"
        )
        await mark_migration_complete(execute_fn, "entries_metadata_indexes_v1", logger)
    else:
        logger.debug("Skipping migration: entries_metadata_indexes_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "phase1_optimization_indexes_v1"):
        logger.debug("Running migration: phase1_optimization_indexes_v1")
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_entries_agent_ts "
            "ON scribe_entries(agent, ts_iso DESC);"
        )
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_entries_emoji_ts "
            "ON scribe_entries(emoji, ts_iso DESC);"
        )
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_entries_logtype_ts "
            "ON scribe_entries(log_type, ts_iso DESC);"
        )
        await mark_migration_complete(execute_fn, "phase1_optimization_indexes_v1", logger)
    else:
        logger.debug("Skipping migration: phase1_optimization_indexes_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "tool_calls_repo_root_v1"):
        logger.debug("Running migration: tool_calls_repo_root_v1")
        await ensure_column_fn("tool_calls", "repo_root", "TEXT")
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_repo_root ON tool_calls(repo_root);"
        )
        await mark_migration_complete(execute_fn, "tool_calls_repo_root_v1", logger)
    else:
        logger.debug("Skipping migration: tool_calls_repo_root_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "projects_repo_index_v1"):
        logger.debug("Running migration: projects_repo_index_v1")
        await ensure_index_fn(
            "CREATE INDEX IF NOT EXISTS idx_projects_repo ON scribe_projects(repo_root);"
        )
        await mark_migration_complete(execute_fn, "projects_repo_index_v1", logger)
    else:
        logger.debug("Skipping migration: projects_repo_index_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "agent_sessions_activity_v1"):
        logger.debug("Running migration: agent_sessions_activity_v1")
        await ensure_column_fn("agent_sessions", "recent_tools", "TEXT")
        await ensure_column_fn("agent_sessions", "session_started_at", "TEXT")
        await ensure_column_fn("agent_sessions", "last_activity_at", "TEXT")
        await mark_migration_complete(execute_fn, "agent_sessions_activity_v1", logger)
    else:
        logger.debug("Skipping migration: agent_sessions_activity_v1 (already completed)")

    if not await migration_completed(fetchone_fn, "docs_json_column_v1"):
        logger.debug("Running migration: docs_json_column_v1")
        await migrate_add_docs_json_column_fn()
        await mark_migration_complete(execute_fn, "docs_json_column_v1", logger)
    else:
        logger.debug("Skipping migration: docs_json_column_v1 (already completed)")

    state_path = db_path.parent / "state.json"
    if state_path.exists() and not await migration_completed(fetchone_fn, "backfill_docs_json_v1"):
        logger.debug("Running migration: backfill_docs_json_v1")
        await backfill_docs_json_from_state_fn(state_path)
        await mark_migration_complete(execute_fn, "backfill_docs_json_v1", logger)
    elif await migration_completed(fetchone_fn, "backfill_docs_json_v1"):
        logger.debug("Skipping migration: backfill_docs_json_v1 (already completed)")
