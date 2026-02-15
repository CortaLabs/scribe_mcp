"""Document-domain operations for the Postgres backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

AsyncExecute = Callable[..., Awaitable[str]]
AsyncFetchRow = Callable[..., Awaitable[Any]]
AsyncFetch = Callable[..., Awaitable[List[Any]]]


def _normalize_repo_root(repo_root: Optional[str]) -> Optional[str]:
    if not repo_root:
        return None
    try:
        return str(Path(repo_root).expanduser().resolve())
    except Exception:
        return str(Path(repo_root).expanduser())


def _coerce_json(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _to_iso(value: Any) -> Any:
    try:
        return value.isoformat() if value is not None else None
    except Exception:
        return value


async def upsert_document_section(
    *,
    execute_fn: AsyncExecute,
    project_id: Optional[int],
    project_root: Optional[str],
    document_type: str,
    section_id: str,
    file_path: str,
    relative_path: Optional[str],
    content: str,
    file_hash: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    normalized_root = _normalize_repo_root(project_root)
    await execute_fn(
        """
        INSERT INTO document_sections (
            project_id, project_root, document_type, section_id,
            file_path, relative_path, content, file_hash, metadata, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW())
        ON CONFLICT (project_id, document_type, section_id) DO UPDATE SET
            project_root = EXCLUDED.project_root,
            file_path = EXCLUDED.file_path,
            relative_path = EXCLUDED.relative_path,
            content = EXCLUDED.content,
            file_hash = EXCLUDED.file_hash,
            metadata = EXCLUDED.metadata,
            updated_at = NOW();
        """,
        project_id,
        normalized_root,
        document_type,
        section_id,
        file_path,
        relative_path,
        content,
        file_hash,
        json.dumps(metadata or {}, sort_keys=True),
    )


async def get_document_section(
    *,
    fetchrow_fn: AsyncFetchRow,
    project_id: Optional[int],
    document_type: str,
    section_id: str,
) -> Optional[Dict[str, Any]]:
    row = await fetchrow_fn(
        """
        SELECT
            id, project_id, project_root, document_type, section_id,
            file_path, relative_path, content, file_hash, metadata,
            created_at, updated_at
        FROM document_sections
        WHERE project_id IS NOT DISTINCT FROM $1
          AND document_type = $2
          AND section_id = $3
        LIMIT 1;
        """,
        project_id,
        document_type,
        section_id,
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "project_root": row["project_root"],
        "document_type": row["document_type"],
        "section_id": row["section_id"],
        "file_path": row["file_path"],
        "relative_path": row["relative_path"],
        "content": row["content"],
        "file_hash": row["file_hash"],
        "metadata": _coerce_json(row["metadata"]),
        "created_at": _to_iso(row["created_at"]),
        "updated_at": _to_iso(row["updated_at"]),
    }


async def search_document_sections(
    *,
    fetch_fn: AsyncFetch,
    query: str,
    project_id: Optional[int] = None,
    document_type: Optional[str] = None,
    threshold: float = 0.3,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    safe_threshold = max(0.0, min(float(threshold), 1.0))
    safe_limit = max(1, min(int(limit), 200))

    clauses = ["similarity(content, $1) >= $2"]
    params: List[Any] = [query, safe_threshold]

    if project_id is not None:
        params.append(project_id)
        clauses.append(f"project_id = ${len(params)}")

    if document_type:
        params.append(document_type)
        clauses.append(f"document_type = ${len(params)}")

    params.append(safe_limit)
    rows = await fetch_fn(
        f"""
        SELECT
            id, project_id, project_root, document_type, section_id,
            file_path, relative_path, content, file_hash, metadata,
            created_at, updated_at, similarity(content, $1) AS score
        FROM document_sections
        WHERE {' AND '.join(clauses)}
        ORDER BY score DESC, updated_at DESC
        LIMIT ${len(params)};
        """,
        *params,
    )

    return [
        {
            "id": row["id"],
            "project_id": row["project_id"],
            "project_root": row["project_root"],
            "document_type": row["document_type"],
            "section_id": row["section_id"],
            "file_path": row["file_path"],
            "relative_path": row["relative_path"],
            "content": row["content"],
            "file_hash": row["file_hash"],
            "metadata": _coerce_json(row["metadata"]),
            "score": float(row["score"]),
            "created_at": _to_iso(row["created_at"]),
            "updated_at": _to_iso(row["updated_at"]),
        }
        for row in rows
    ]


async def record_document_change(
    *,
    execute_fn: AsyncExecute,
    project_id: Optional[int],
    project_root: Optional[str],
    file_path: str,
    change_type: str,
    old_content_hash: Optional[str] = None,
    new_content_hash: Optional[str] = None,
    change_summary: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    normalized_root = _normalize_repo_root(project_root)
    await execute_fn(
        """
        INSERT INTO document_changes (
            project_id, project_root, file_path, change_type,
            old_content_hash, new_content_hash, change_summary, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb);
        """,
        project_id,
        normalized_root,
        file_path,
        change_type,
        old_content_hash,
        new_content_hash,
        change_summary,
        json.dumps(metadata or {}, sort_keys=True),
    )

