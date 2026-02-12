"""Compatibility migration helpers for SQLite backend bootstrap."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable


ConnectFn = Callable[[], Any]


def backfill_log_type_from_meta_sync(*, connect_fn: ConnectFn) -> None:
    conn = connect_fn()
    try:
        conn.execute(
            """
            UPDATE scribe_entries
            SET log_type = json_extract(meta, '$.log_type')
            WHERE json_extract(meta, '$.log_type') IS NOT NULL
              AND (log_type IS NULL OR log_type = 'progress')
              AND json_extract(meta, '$.log_type') != 'progress';
            """
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


async def backfill_log_type_from_meta(*, connect_fn: ConnectFn) -> None:
    await asyncio.to_thread(backfill_log_type_from_meta_sync, connect_fn=connect_fn)


def migrate_document_sections_sync(*, connect_fn: ConnectFn) -> None:
    conn = connect_fn()
    try:
        cursor = conn.execute("PRAGMA table_info(document_sections);")
        columns = cursor.fetchall()
        if not columns:
            return
        column_map = {row["name"]: row for row in columns}
        needs_rebuild = False
        document_type_info = column_map.get("document_type")
        if (
            "project_root" not in column_map
            or "file_path" not in column_map
            or (document_type_info and document_type_info["notnull"])
        ):
            needs_rebuild = True
        if not needs_rebuild:
            return

        conn.execute("ALTER TABLE document_sections RENAME TO document_sections_legacy;")
        conn.execute(
            """
            CREATE TABLE document_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
                project_root TEXT,
                document_type TEXT,
                section_id TEXT,
                file_path TEXT,
                relative_path TEXT,
                content TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, document_type, section_id),
                UNIQUE(project_root, file_path)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO document_sections (project_id, document_type, section_id, content, file_hash, metadata, created_at, updated_at)
            SELECT project_id, document_type, section_id, content, file_hash, metadata, created_at, updated_at
            FROM document_sections_legacy;
            """
        )
        conn.execute("DROP TABLE document_sections_legacy;")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def migrate_document_sections(*, connect_fn: ConnectFn) -> None:
    await asyncio.to_thread(migrate_document_sections_sync, connect_fn=connect_fn)


def migrate_agent_sessions_schema_sync(*, connect_fn: ConnectFn) -> None:
    conn = connect_fn()
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_sessions';"
        )
        if not cursor.fetchone():
            return

        cursor = conn.execute("PRAGMA table_info(agent_sessions);")
        columns = {row["name"] for row in cursor.fetchall()}

        if "id" in columns and "session_id" not in columns:
            conn.execute("DROP TABLE agent_sessions;")
            conn.commit()
    finally:
        conn.close()


async def migrate_agent_sessions_schema(*, connect_fn: ConnectFn) -> None:
    await asyncio.to_thread(migrate_agent_sessions_schema_sync, connect_fn=connect_fn)


def migrate_add_docs_json_column_sync(*, connect_fn: ConnectFn, logger: Any) -> bool:
    conn = connect_fn()
    try:
        cursor = conn.execute("PRAGMA table_info(scribe_projects);")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        if "docs_json" in column_names:
            logger.info("docs_json column already exists - migration already applied")
            return True

        conn.execute("ALTER TABLE scribe_projects ADD COLUMN docs_json TEXT;")
        conn.commit()
        logger.info("Successfully added docs_json column to scribe_projects table")
        return True
    except Exception as e:
        logger.error(f"Failed to add docs_json column: {e}")
        raise
    finally:
        conn.close()


async def migrate_add_docs_json_column(*, connect_fn: ConnectFn, logger: Any) -> bool:
    return await asyncio.to_thread(
        migrate_add_docs_json_column_sync,
        connect_fn=connect_fn,
        logger=logger,
    )


def backfill_docs_json_from_state_sync(
    *, state_path: Path, connect_fn: ConnectFn, logger: Any
) -> int:
    if not state_path.exists():
        logger.warning(f"State file not found: {state_path}")
        return 0

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse state.json: {e}")
        raise

    projects = state.get("projects", {})
    backfilled_count = 0

    conn = connect_fn()
    try:
        for project_name, project_data in projects.items():
            docs = project_data.get("docs")
            if not docs:
                continue

            docs_json = json.dumps(docs)
            cursor = conn.execute(
                "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
                (docs_json, project_name),
            )
            if cursor.rowcount > 0:
                backfilled_count += 1

        conn.commit()
        logger.info(f"Backfilled {backfilled_count} projects with docs_json from state.json")
        return backfilled_count
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to backfill docs_json: {e}")
        raise
    finally:
        conn.close()


async def backfill_docs_json_from_state(
    *, state_path: Path, connect_fn: ConnectFn, logger: Any
) -> int:
    return await asyncio.to_thread(
        backfill_docs_json_from_state_sync,
        state_path=state_path,
        connect_fn=connect_fn,
        logger=logger,
    )
