"""Project-domain operations for the SQLite storage backend."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional

from scribe_mcp.storage.models import (
    ProjectRecord,
    RepoScopeGrantRecord,
    compute_legacy_project_key,
    compute_project_key,
    compute_repo_id,
    normalize_repo_root,
)
from scribe_mcp.storage.project_identity_preflight import (
    ProjectIdentityPreflightReport,
    build_sqlite_project_identity_preflight,
)
from scribe_mcp.utils.slug import normalize_project_input


AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchOne = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchAll = Callable[[str, tuple[Any, ...]], Awaitable[List[Any]]]
AsyncInitialise = Callable[[], Awaitable[None]]
AsyncFetchProject = Callable[[str], Awaitable[Optional[ProjectRecord]]]


def _row_to_project(row: Any) -> ProjectRecord:
    return ProjectRecord(
        id=row["id"],
        name=row["name"],
        repo_root=row["repo_root"],
        progress_log_path=row["progress_log_path"],
        repo_id=row["repo_id"] if "repo_id" in row.keys() else None,
        project_key=row["project_key"] if "project_key" in row.keys() else None,
        docs_json=row["docs_json"] if "docs_json" in row.keys() else None,
        bridge_id=row["bridge_id"] if "bridge_id" in row.keys() else None,
        bridge_managed=bool(row["bridge_managed"]) if "bridge_managed" in row.keys() else False,
    )


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _row_to_repo_scope_grant(row: Any) -> RepoScopeGrantRecord:
    expires_at = _parse_datetime(row["expires_at"])
    if expires_at is None:
        expires_at = datetime.now(timezone.utc)
    return RepoScopeGrantRecord(
        grant_id=str(row["grant_id"]),
        authoritative_session_key=str(row["authoritative_session_key"]),
        repo_root=str(row["repo_root"]),
        repo_id=str(row["repo_id"]),
        reason=str(row["reason"]),
        expires_at=expires_at,
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
    )


async def _ensure_project_identity_schema(
    *,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
) -> None:
    table_sql_row = await fetchone_fn(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'scribe_projects'
        LIMIT 1;
        """,
        (),
    )
    table_sql = str(table_sql_row["sql"]) if table_sql_row and table_sql_row["sql"] else ""

    def _column_exists(column: str) -> Awaitable[Any]:
        return fetchone_fn(
            """
            SELECT 1 AS present
            FROM pragma_table_info('scribe_projects')
            WHERE name = ?
            LIMIT 1;
            """,
            (column,),
        )

    if not await _column_exists("repo_id"):
        await execute_fn("ALTER TABLE scribe_projects ADD COLUMN repo_id TEXT;", ())
    if not await _column_exists("project_key"):
        await execute_fn("ALTER TABLE scribe_projects ADD COLUMN project_key TEXT;", ())
    if not await _column_exists("bridge_id"):
        await execute_fn("ALTER TABLE scribe_projects ADD COLUMN bridge_id TEXT;", ())
    if not await _column_exists("bridge_managed"):
        await execute_fn("ALTER TABLE scribe_projects ADD COLUMN bridge_managed INTEGER NOT NULL DEFAULT 0;", ())

    dependent_fk_row = await fetchone_fn(
        """
        SELECT 1 AS present
        FROM sqlite_master
        WHERE type = 'table'
          AND name IN ('session_projects', 'agent_projects', 'agent_recent_projects')
        LIMIT 1;
        """,
        (),
    )
    has_dependent_tables = bool(dependent_fk_row)

    if (not has_dependent_tables) and "NAME TEXT NOT NULL UNIQUE" in table_sql.upper().replace("\n", " "):
        await execute_fn("ALTER TABLE scribe_projects RENAME TO scribe_projects_legacy;", ())
        await execute_fn(
            """
            CREATE TABLE scribe_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                repo_root TEXT NOT NULL,
                repo_id TEXT,
                project_key TEXT,
                progress_log_path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                docs_json TEXT,
                bridge_id TEXT,
                bridge_managed INTEGER NOT NULL DEFAULT 0
            );
            """,
            (),
        )
        await execute_fn(
            """
            INSERT INTO scribe_projects
                (id, name, repo_root, repo_id, project_key, progress_log_path, created_at, updated_at, docs_json, bridge_id, bridge_managed)
            SELECT
                id,
                name,
                repo_root,
                repo_id,
                project_key,
                progress_log_path,
                created_at,
                updated_at,
                docs_json,
                bridge_id,
                COALESCE(bridge_managed, 0)
            FROM scribe_projects_legacy;
            """,
            (),
        )
        await execute_fn("DROP TABLE scribe_projects_legacy;", ())

    assigned_project_keys: set[str] = set()
    while True:
        row = await fetchone_fn(
            """
            SELECT id, name, repo_root
            FROM scribe_projects
            WHERE repo_id IS NULL
               OR repo_id = ''
               OR project_key IS NULL
               OR project_key = ''
            ORDER BY id
            LIMIT 1;
            """,
            (),
        )
        if not row:
            break
        repo_root = normalize_repo_root(str(row["repo_root"]))
        name = str(row["name"])
        project_key = compute_project_key(repo_root=repo_root, project_name=name)
        existing_project_key_row = await fetchone_fn(
            """
            SELECT id
            FROM scribe_projects
            WHERE project_key = ?
              AND id != ?
            LIMIT 1;
            """,
            (project_key, int(row["id"])),
        )
        if project_key in assigned_project_keys or existing_project_key_row:
            project_key = compute_legacy_project_key(
                repo_root=repo_root,
                project_name=name,
                row_id=int(row["id"]),
            )
        assigned_project_keys.add(project_key)
        await execute_fn(
            """
            UPDATE scribe_projects
            SET repo_root = ?, repo_id = ?, project_key = ?
            WHERE id = ?;
            """,
            (
                repo_root,
                compute_repo_id(repo_root),
                project_key,
                int(row["id"]),
            ),
        )

    await execute_fn(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scribe_projects_project_key_unique
        ON scribe_projects(project_key);
        """,
        (),
    )
    await execute_fn(
        """
        CREATE INDEX IF NOT EXISTS idx_scribe_projects_name_repo_id
        ON scribe_projects(name, repo_id);
        """,
        (),
    )


async def preflight_project_identity_repair(
    *,
    db_path: Path,
) -> ProjectIdentityPreflightReport:
    uri = f"{db_path.expanduser().resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        async def _fetchone(query: str, params: tuple[Any, ...] = ()) -> Any:
            return conn.execute(query, params).fetchone()

        async def _fetchall(query: str, params: tuple[Any, ...] = ()) -> List[Any]:
            return list(conn.execute(query, params).fetchall())

        return await build_sqlite_project_identity_preflight(
            fetchall_fn=_fetchall,
            fetchone_fn=_fetchone,
        )
    finally:
        conn.close()


async def _ensure_repo_scope_grants_schema(
    *,
    execute_fn: AsyncExecute,
) -> None:
    await execute_fn(
        """
        CREATE TABLE IF NOT EXISTS repo_scope_grants (
            grant_id TEXT PRIMARY KEY,
            authoritative_session_key TEXT NOT NULL,
            repo_root TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
        (),
    )
    await execute_fn(
        """
        CREATE INDEX IF NOT EXISTS idx_repo_scope_grants_expires_at
        ON repo_scope_grants(expires_at);
        """,
        (),
    )


async def _fetch_project_row(
    fetchone_fn: AsyncFetchOne,
    name: str,
    repo_root: Optional[str] = None,
    project_key: Optional[str] = None,
) -> Any:
    if project_key:
        return await fetchone_fn(
            """
            SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE project_key = ?;
            """,
            (project_key,),
        )

    if repo_root:
        normalized_root = normalize_repo_root(repo_root)
        scoped_key = compute_project_key(repo_root=normalized_root, project_name=name)
        return await fetchone_fn(
            """
            SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE project_key = ?;
            """,
            (scoped_key,),
        )

    count_row = await fetchone_fn(
        """
        SELECT COUNT(*) AS count
        FROM scribe_projects
        WHERE name = ?;
        """,
        (name,),
    )
    if not count_row or int(count_row["count"]) != 1:
        rows = None
    else:
        rows = await fetchone_fn(
        """
        SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
        FROM scribe_projects
        WHERE name = ?;
        """,
        (name,),
    )
    row = rows

    if row:
        return row

    if rows is None:
        canonical = normalize_project_input(name)
        if canonical and canonical != name:
            canonical_count = await fetchone_fn(
                "SELECT COUNT(*) AS count FROM scribe_projects WHERE name = ?;",
                (canonical,),
            )
            if canonical_count and int(canonical_count["count"]) == 1:
                return await fetchone_fn(
                """
                SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
                FROM scribe_projects
                WHERE name = ?;
                """,
                (canonical,),
            )

    if "_" in name:
        denormalized = name.replace("_", "-")
        if denormalized != name:
            denormalized_count = await fetchone_fn(
                "SELECT COUNT(*) AS count FROM scribe_projects WHERE name = ?;",
                (denormalized,),
            )
            if denormalized_count and int(denormalized_count["count"]) == 1:
                return await fetchone_fn(
                """
                SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
                FROM scribe_projects
                WHERE name = ?;
                """,
                (denormalized,),
            )

    return None


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
    normalized_root = normalize_repo_root(repo_root)
    repo_id = compute_repo_id(normalized_root)
    project_key = compute_project_key(repo_root=normalized_root, project_name=name)

    async with write_lock:
        await _ensure_project_identity_schema(execute_fn=execute_fn, fetchone_fn=fetchone_fn)
        await execute_fn(
            """
            INSERT INTO scribe_projects
                (name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_key)
            DO UPDATE SET repo_root = excluded.repo_root,
                          repo_id = excluded.repo_id,
                          progress_log_path = excluded.progress_log_path,
                          docs_json = COALESCE(excluded.docs_json, scribe_projects.docs_json),
                          bridge_id = excluded.bridge_id,
                          bridge_managed = excluded.bridge_managed;
            """,
            (
                name,
                normalized_root,
                repo_id,
                project_key,
                progress_log_path,
                docs_json,
                bridge_id,
                1 if bridge_managed else 0,
            ),
        )
    row = await fetchone_fn(
        """
        SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
        FROM scribe_projects
        WHERE project_key = ?;
        """,
        (project_key,),
    )
    return _row_to_project(row)


async def fetch_project(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: Optional[AsyncExecute] = None,
    fetchone_fn: AsyncFetchOne,
    name: str,
    repo_root: Optional[str] = None,
    project_key: Optional[str] = None,
) -> Optional[ProjectRecord]:
    await initialise_fn()
    if execute_fn is not None:
        await _ensure_project_identity_schema(execute_fn=execute_fn, fetchone_fn=fetchone_fn)
    row = await _fetch_project_row(
        fetchone_fn,
        name,
        repo_root=repo_root,
        project_key=project_key,
    )
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
            SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
            FROM scribe_projects
            WHERE name = ?
            ORDER BY id;
            """,
            (name,),
        ).fetchall()
        row = row[0] if len(row) == 1 else None

        if not row:
            canonical = normalize_project_input(name)
            if canonical and canonical != name:
                row = conn.execute(
                    """
                    SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
                    FROM scribe_projects
                    WHERE name = ?
                    ORDER BY id;
                    """,
                    (canonical,),
                ).fetchall()
                row = row[0] if len(row) == 1 else None

        if not row and "_" in name:
            denormalized = name.replace("_", "-")
            if denormalized != name:
                row = conn.execute(
                    """
                    SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
                    FROM scribe_projects
                    WHERE name = ?
                    ORDER BY id;
                    """,
                    (denormalized,),
                ).fetchall()
                row = row[0] if len(row) == 1 else None

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
        SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
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
        SELECT id, name, repo_root, repo_id, project_key, progress_log_path, docs_json, bridge_id, bridge_managed
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
    repo_root: Optional[str] = None,
) -> bool:
    await initialise_fn()
    async with write_lock:
        if repo_root:
            project_key = compute_project_key(
                repo_root=normalize_repo_root(repo_root),
                project_name=name,
            )
            await execute_fn(
                "UPDATE scribe_projects SET docs_json = ? WHERE project_key = ?",
                (docs_json, project_key),
            )
        else:
            await execute_fn(
                "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
                (docs_json, name),
            )
    return True


async def create_repo_scope_grant(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    authoritative_session_key: str,
    repo_root: str,
    reason: str,
    ttl_minutes: int = 30,
) -> RepoScopeGrantRecord:
    await initialise_fn()
    normalized_root = normalize_repo_root(repo_root)
    repo_id = compute_repo_id(normalized_root)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl_minutes)
    grant_id = uuid.uuid4().hex

    async with write_lock:
        await _ensure_repo_scope_grants_schema(execute_fn=execute_fn)
        await execute_fn(
            """
            INSERT INTO repo_scope_grants
                (grant_id, authoritative_session_key, repo_root, repo_id, reason, expires_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                grant_id,
                authoritative_session_key,
                normalized_root,
                repo_id,
                reason,
                expires_at.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )

    row = await fetchone_fn(
        """
        SELECT grant_id, authoritative_session_key, repo_root, repo_id, reason, expires_at, created_at, updated_at
        FROM repo_scope_grants
        WHERE grant_id = ?;
        """,
        (grant_id,),
    )
    return _row_to_repo_scope_grant(row)


async def fetch_repo_scope_grant(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    grant_id: str,
) -> Optional[RepoScopeGrantRecord]:
    await initialise_fn()
    await _ensure_repo_scope_grants_schema(execute_fn=execute_fn)
    row = await fetchone_fn(
        """
        SELECT grant_id, authoritative_session_key, repo_root, repo_id, reason, expires_at, created_at, updated_at
        FROM repo_scope_grants
        WHERE grant_id = ?;
        """,
        (grant_id,),
    )
    if not row:
        return None
    grant = _row_to_repo_scope_grant(row)
    if grant.expires_at <= datetime.now(timezone.utc):
        return None
    return grant
