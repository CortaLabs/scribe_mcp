"""Read tool for shared case-registry open case queries."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

try:
    from scribe_mcp import server as server_module
    from scribe_mcp.server import app
except Exception:
    server_module = SimpleNamespace(storage_backend=None, get_execution_context=lambda: None)

    class _AppStub:
        def tool(self, _func=None, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

    app = _AppStub()
from scribe_mcp.tool_contracts import read_only_local_tool

_OPEN_STATUS_VALUES = {
    "open",
    "investigating",
    "triage",
    "in_progress",
    "todo",
    "new",
}
_CLOSED_STATUS_VALUES = {
    "closed",
    "resolved",
    "fixed",
    "done",
    "wontfix",
    "won't fix",
    "duplicate",
    "false_positive",
    "mitigated",
}
_CASE_TYPE_ALIASES = {
    "bug": "bug",
    "bugs": "bug",
    "security": "security",
    "sec": "security",
}


def _operator_envelope(
    *,
    ok: bool,
    mode: str,
    case_id: str = "",
    artifacts: Optional[list[dict[str, str]]] = None,
    warnings: Optional[list[str]] = None,
    next_step: str = "",
    **extra: Any,
) -> Dict[str, Any]:
    envelope: Dict[str, Any] = {
        "ok": ok,
        "mode": mode,
        "case_id": case_id,
        "artifacts": artifacts or [],
        "warnings": warnings or [],
        "next_step": next_step,
    }
    envelope.update(extra)
    return envelope


def _normalize_case_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _CASE_TYPE_ALIASES.get(value.strip().lower(), value.strip().lower())


def _normalize_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _normalize_status(value: Optional[str]) -> str:
    if value is None:
        return ""
    return value.strip().lower()


def _is_open_case_status(value: Optional[str]) -> bool:
    normalized = _normalize_status(value)
    if not normalized:
        return True
    if normalized in _OPEN_STATUS_VALUES:
        return True
    return normalized not in _CLOSED_STATUS_VALUES


def _coerce_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return 25
    return max(1, min(parsed, 200))


def _format_timestamp(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def _context_repo_project_defaults() -> tuple[Optional[str], Optional[str]]:
    if not hasattr(server_module, "get_execution_context"):
        return None, None
    try:
        context = server_module.get_execution_context()
    except Exception:
        return None, None
    if context is None:
        return None, None

    resolved_scope = getattr(context, "resolved_scope", None)
    repo_root = getattr(resolved_scope, "repo_root", None)
    project_name = getattr(resolved_scope, "project_name", None)

    repo_default: Optional[str] = None
    if isinstance(repo_root, str) and repo_root.strip():
        try:
            repo_default = str(Path(repo_root).expanduser().resolve())
        except Exception:
            repo_default = repo_root.strip()

    project_default = project_name if isinstance(project_name, str) and project_name.strip() else None
    return repo_default, project_default


def _record_to_operator_case(record: Any) -> Dict[str, Any]:
    metadata = getattr(record, "metadata", None)
    category = None
    if isinstance(metadata, dict):
        raw_category = metadata.get("category")
        if isinstance(raw_category, str) and raw_category.strip():
            category = raw_category.strip()

    return {
        "case_id": getattr(record, "case_id", ""),
        "case_type": getattr(record, "case_type", ""),
        "title": getattr(record, "title", None),
        "status": getattr(record, "status", None),
        "severity": getattr(record, "severity", None),
        "category": category,
        "project": getattr(record, "project_name", ""),
        "repo_id": getattr(record, "repo_id", ""),
        "doc_type": getattr(record, "doc_type", ""),
        "doc_name": getattr(record, "doc_name", ""),
        "doc_path": getattr(record, "doc_path", ""),
        "updated_at": _format_timestamp(getattr(record, "updated_at", None)),
        "created_at": _format_timestamp(getattr(record, "created_at", None)),
    }


@app.tool(
    **read_only_local_tool(
        title="List Open Cases",
        tags=("cases", "bugs", "security", "read-only"),
    )
)
async def list_open_cases(
    case_type: Optional[str] = None,
    project: Optional[str] = None,
    repo_id: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """List open bug/security cases from the shared case registry.

    Args:
        case_type: Optional case type filter ("bug" or "security")
        project: Optional project-name filter; defaults to active project when available
        repo_id: Optional repository-id filter
        category: Optional case category filter (from case metadata)
        severity: Optional severity filter
        limit: Maximum number of returned open cases (1-200)
    """
    context_mode = "unknown"
    if hasattr(server_module, "get_execution_context"):
        try:
            context = server_module.get_execution_context()
            if context is not None:
                context_mode = str(getattr(context, "mode", "") or "unknown")
        except Exception:
            context_mode = "unknown"

    backend = getattr(server_module, "storage_backend", None)
    if backend is None or not hasattr(backend, "query_case_registry_records"):
        return _operator_envelope(
            ok=False,
            mode=context_mode,
            warnings=["shared case registry backend is unavailable"],
            next_step="Ensure the shared case registry backend is configured, then retry list_open_cases.",
            cases=[],
            count=0,
            filters={},
        )

    normalized_case_type = _normalize_case_type(case_type)
    normalized_project = _normalize_str(project)
    normalized_repo_id = _normalize_str(repo_id)
    normalized_category = _normalize_str(category)
    normalized_severity = _normalize_str(severity)
    normalized_limit = _coerce_limit(limit)

    default_repo_root, default_project = _context_repo_project_defaults()
    query_project = normalized_project or default_project

    try:
        raw_records = await backend.query_case_registry_records(
            repo_root=default_repo_root,
            project_name=query_project,
            case_type=normalized_case_type,
            limit=max(normalized_limit * 4, normalized_limit),
            offset=0,
        )
    except Exception as exc:
        return _operator_envelope(
            ok=False,
            mode=context_mode,
            warnings=[f"failed to query shared case registry: {exc}"],
            next_step="Resolve backend query failure and retry list_open_cases.",
            cases=[],
            count=0,
            filters={
                "case_type": normalized_case_type,
                "project": query_project,
                "repo_id": normalized_repo_id,
                "category": normalized_category,
                "severity": normalized_severity,
                "open_only": True,
                "limit": normalized_limit,
            },
        )

    filtered: List[Any] = []
    for record in raw_records:
        if not _is_open_case_status(getattr(record, "status", None)):
            continue

        if normalized_repo_id:
            record_repo_id = _normalize_str(getattr(record, "repo_id", None))
            if record_repo_id != normalized_repo_id:
                continue

        if normalized_severity:
            record_severity = _normalize_str(getattr(record, "severity", None))
            if not record_severity or record_severity.lower() != normalized_severity.lower():
                continue

        if normalized_category:
            metadata = getattr(record, "metadata", None)
            record_category = None
            if isinstance(metadata, dict):
                record_category = _normalize_str(metadata.get("category"))
            if not record_category or record_category.lower() != normalized_category.lower():
                continue

        filtered.append(record)

    filtered.sort(
        key=lambda item: (
            _format_timestamp(getattr(item, "updated_at", None)) or "",
            _format_timestamp(getattr(item, "created_at", None)) or "",
        ),
        reverse=True,
    )
    filtered = filtered[:normalized_limit]

    cases = [_record_to_operator_case(record) for record in filtered]
    return _operator_envelope(
        ok=True,
        mode=context_mode,
        cases=cases,
        count=len(cases),
        filters={
            "case_type": normalized_case_type,
            "project": query_project,
            "repo_id": normalized_repo_id,
            "category": normalized_category,
            "severity": normalized_severity,
            "open_only": True,
            "limit": normalized_limit,
        },
    )
