"""Document-domain operations for the SQLite storage backend."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, Optional

from scribe_mcp.storage.models import ProjectRecord


AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncInitialise = Callable[[], Awaitable[None]]


async def record_doc_change(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    project: ProjectRecord,
    doc: str,
    section: Optional[str],
    action: str,
    agent: Optional[str],
    metadata: Optional[Dict[str, Any]],
    sha_before: str,
    sha_after: str,
) -> None:
    await initialise_fn()
    meta_json = json.dumps(metadata or {}, sort_keys=True)
    async with write_lock:
        await execute_fn(
            """
            INSERT INTO doc_changes
                (project_id, doc_name, section, action, agent, metadata, sha_before, sha_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                project.id,
                doc,
                section,
                action,
                agent,
                meta_json,
                sha_before,
                sha_after,
            ),
        )
        await execute_fn(
            """
            DELETE FROM doc_changes
            WHERE id IN (
                SELECT id FROM doc_changes
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT -1 OFFSET 500
            );
            """,
            (project.id,),
        )
