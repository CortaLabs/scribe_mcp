"""Project-domain operations for the SQLite storage backend."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional

from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.utils.slug import normalize_project_input


AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchOne = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchAll = Callable[[str, tuple[Any, ...] | tuple], Awaitable[List[Any]]]
AsyncInitialise = Callable[[], Awaitable[None]]
AsyncFetchProject = Callable[[str], Awaitable[Optional[ProjectRecord]]]


def _row_to_project(row: Any) -> ProjectRecord:
    return ProjectRecord(
        id=row["id"],
        name=row["name"],
        repo_root=row["repo_root"],
        progress_log_path=row["progress_log_path"],
        docs_json=row["docs_json"] if "docs_json" in row.keys() else None,
        bridge_id=row["bridge_id"] if "bridge_id" in row.keys() else None,
        bridge_managed=bool(row["bridge_managed"]) if "bridge_managed" in row.keys() else False,
    )


async def _fetch_project_row(fetchone_fn: AsyncFetchOne, name: str) -> Any:
    row = await fetchone_fn(
        """
        SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
        FROM scribe_projects
        WHERE name = ?;
        """,
        (name,),
    )

    if not row:
        canonical = normalize_project_input(name)
        if canonical and canonical != name:
            row = await fetchone_fn(
                """
                SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
                FROM scribe_projects
                WHERE name = ?;
                """,
                (canonical,),
            )

    if not row and "_" in name:
        denormalized = name.replace("_", "-")
        if denormalized != name:
            row = await fetchone_fn(
                """
                SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
                FROM scribe_projects
                WHERE name = ?;
                """,
                (denormalized,),
            )

    return row


async def upsert_project(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    name: str,
    repo_root: str,
    progress_log_path: str,
    docs_json: Optional[str] = None,
    bridge_id: Optional[str] = None,
    bridge_managed: bool = False,
) -> ProjectRecord:
    await initialise_fn()
    async with write_lock:
        await execute_fn(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name)
            DO UPDATE SET repo_root = excluded.repo_root,
                          progress_log_path = excluded.progress_log_path,
                          docs_json = excluded.docs_json,
                          bridge_id = excluded.bridge_id,
                          bridge_managed = excluded.bridge_managed;
            """,
            (name, repo_root, progress_log_path, docs_json, bridge_id, 1 if bridge_managed else 0),
        )
    row = await fetchone_fn(
        """
        SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
        FROM scribe_projects
        WHERE name = ?;
        """,
        (name,),
    )
    return _row_to_project(row)


async def fetch_project(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    name: str,
) -> Optional[ProjectRecord]:
    await initialise_fn()
    row = await _fetch_project_row(fetchone_fn, name)
    if not row:
        return None
    return _row_to_project(row)


def fetch_project_sync(*, db_path: Path | str, name: str) -> Optional[ProjectRecord]:
    """Synchronous project lookup used by response finalization path."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")

        row = conn.execute(
            """
            SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE name = ?;
            """,
            (name,),
        ).fetchone()

        if not row:
            canonical = normalize_project_input(name)
            if canonical and canonical != name:
                row = conn.execute(
                    """
                    SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
                    FROM scribe_projects
                    WHERE name = ?;
                    """,
                    (canonical,),
                ).fetchone()

        if not row and "_" in name:
            denormalized = name.replace("_", "-")
            if denormalized != name:
                row = conn.execute(
                    """
                    SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
                    FROM scribe_projects
                    WHERE name = ?;
                    """,
                    (denormalized,),
                ).fetchone()

        conn.close()
        if not row:
            return None
        return _row_to_project(row)
    except Exception:
        return None


async def list_projects(
    *,
    initialise_fn: AsyncInitialise,
    fetchall_fn: AsyncFetchAll,
) -> List[ProjectRecord]:
    await initialise_fn()
    rows = await fetchall_fn(
        """
        SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
        FROM scribe_projects
        ORDER BY name;
        """
    )
    return [_row_to_project(row) for row in rows]


async def list_projects_by_repo(
    *,
    initialise_fn: AsyncInitialise,
    fetchall_fn: AsyncFetchAll,
    repo_root: str,
) -> List[ProjectRecord]:
    await initialise_fn()
    normalized_root = str(Path(repo_root).resolve())
    rows = await fetchall_fn(
        """
        SELECT id, name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed
        FROM scribe_projects
        WHERE repo_root = ?
        ORDER BY name;
        """,
        (normalized_root,),
    )
    return [_row_to_project(row) for row in rows]


async def delete_project(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    fetch_project_fn: AsyncFetchProject,
    name: str,
) -> bool:
    await initialise_fn()
    project = await fetch_project_fn(name)
    if not project:
        return False

    async with write_lock:
        await execute_fn(
            "DELETE FROM agent_projects WHERE project_name = ?;",
            (name,),
        )

        await execute_fn(
            "DELETE FROM scribe_projects WHERE name = ?;",
            (name,),
        )

        remaining = await fetchone_fn(
            "SELECT COUNT(*) as count FROM scribe_projects WHERE name = ?;",
            (name,),
        )
        return remaining["count"] == 0


async def update_project_docs(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    name: str,
    docs_json: str,
) -> bool:
    await initialise_fn()
    async with write_lock:
        await execute_fn(
            "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
            (docs_json, name),
        )
    return True
