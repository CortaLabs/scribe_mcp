"""Case registry operations for SQLite storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from scribe_mcp.storage.models import (
    CaseRegistryRecord,
    compute_project_key,
    compute_repo_id,
    normalize_repo_root,
)

AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchAll = Callable[[str, tuple[Any, ...]], Awaitable[List[Any]]]
AsyncFetchOne = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncInitialise = Callable[[], Awaitable[None]]


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


def _decode_metadata(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _row_to_case(row: Any) -> CaseRegistryRecord:
    return CaseRegistryRecord(
        case_id=str(row["case_id"]),
        case_type=str(row["case_type"]),
        project_name=str(row["project_name"]),
        repo_root=str(row["repo_root"]),
        repo_id=str(row["repo_id"]),
        project_key=str(row["project_key"]),
        doc_type=str(row["doc_type"]),
        doc_name=str(row["doc_name"]),
        doc_path=str(row["doc_path"]),
        title=row["title"],
        status=row["status"],
        severity=row["severity"],
        source_tool=row["source_tool"],
        metadata=_decode_metadata(row["metadata"]),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
    )


async def ensure_case_registry_schema(
    *,
    execute_fn: AsyncExecute,
) -> None:
    await execute_fn(
        """
        CREATE TABLE IF NOT EXISTS case_registry (
            case_id TEXT PRIMARY KEY,
            case_type TEXT NOT NULL,
            project_name TEXT NOT NULL,
            repo_root TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            project_key TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            doc_name TEXT NOT NULL,
            doc_path TEXT NOT NULL,
            title TEXT,
            status TEXT,
            severity TEXT,
            source_tool TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
        (),
    )
    await execute_fn(
        "CREATE INDEX IF NOT EXISTS idx_case_registry_repo_project ON case_registry(repo_id, project_name);",
        (),
    )
    await execute_fn(
        "CREATE INDEX IF NOT EXISTS idx_case_registry_case_type ON case_registry(case_type);",
        (),
    )
    await execute_fn(
        "CREATE INDEX IF NOT EXISTS idx_case_registry_project_key ON case_registry(project_key);",
        (),
    )


async def upsert_case_registry_record(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    case_id: str,
    case_type: str,
    project_name: str,
    repo_root: str,
    doc_type: str,
    doc_name: str,
    doc_path: str,
    title: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    source_tool: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> CaseRegistryRecord:
    await initialise_fn()
    normalized_root = normalize_repo_root(repo_root)
    repo_id = compute_repo_id(normalized_root)
    project_key = compute_project_key(repo_root=normalized_root, project_name=project_name)
    metadata_json = json.dumps(metadata, sort_keys=True) if metadata is not None else None

    async with write_lock:
        await ensure_case_registry_schema(execute_fn=execute_fn)
        await execute_fn(
            """
            INSERT INTO case_registry (
                case_id, case_type, project_name, repo_root, repo_id, project_key,
                doc_type, doc_name, doc_path, title, status, severity, source_tool, metadata,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(case_id) DO UPDATE SET
                case_type = excluded.case_type,
                project_name = excluded.project_name,
                repo_root = excluded.repo_root,
                repo_id = excluded.repo_id,
                project_key = excluded.project_key,
                doc_type = excluded.doc_type,
                doc_name = excluded.doc_name,
                doc_path = excluded.doc_path,
                title = excluded.title,
                status = excluded.status,
                severity = excluded.severity,
                source_tool = excluded.source_tool,
                metadata = excluded.metadata,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                case_id,
                case_type,
                project_name,
                normalized_root,
                repo_id,
                project_key,
                doc_type,
                doc_name,
                doc_path,
                title,
                status,
                severity,
                source_tool,
                metadata_json,
            ),
        )

    row = await fetchone_fn("SELECT * FROM case_registry WHERE case_id = ?;", (case_id,))
    if row is None:
        raise RuntimeError("Failed to upsert case registry record")
    return _row_to_case(row)


async def fetch_case_registry_record(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    case_id: str,
    repo_root: Optional[str] = None,
    project_name: Optional[str] = None,
) -> Optional[CaseRegistryRecord]:
    await initialise_fn()
    await ensure_case_registry_schema(execute_fn=execute_fn)

    clauses = ["case_id = ?"]
    params: List[Any] = [case_id]
    if repo_root:
        clauses.append("repo_root = ?")
        params.append(normalize_repo_root(repo_root))
    if project_name:
        clauses.append("project_name = ?")
        params.append(project_name)

    row = await fetchone_fn(
        f"SELECT * FROM case_registry WHERE {' AND '.join(clauses)} LIMIT 1;",
        tuple(params),
    )
    if row is None:
        return None
    return _row_to_case(row)


async def query_case_registry_records(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    fetchall_fn: AsyncFetchAll,
    repo_root: Optional[str] = None,
    project_name: Optional[str] = None,
    case_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[CaseRegistryRecord]:
    await initialise_fn()
    await ensure_case_registry_schema(execute_fn=execute_fn)

    clauses = ["1=1"]
    params: List[Any] = []
    if repo_root:
        clauses.append("repo_root = ?")
        params.append(normalize_repo_root(repo_root))
    if project_name:
        clauses.append("project_name = ?")
        params.append(project_name)
    if case_type:
        clauses.append("case_type = ?")
        params.append(case_type)
    params.extend([limit, offset])

    rows = await fetchall_fn(
        f"""
        SELECT *
        FROM case_registry
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC, case_id ASC
        LIMIT ? OFFSET ?;
        """,
        tuple(params),
    )
    return [_row_to_case(row) for row in rows]
