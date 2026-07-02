"""Read tool for one shared case-registry lifecycle snapshot."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

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

from scribe_mcp.case_lifecycle import (
    build_canonical_doc_binding,
    case_status_snapshot,
    doc_binding_from_metadata,
)
from scribe_mcp.tool_contracts import read_only_local_tool


def _operator_envelope(
    *,
    ok: bool,
    mode: str,
    case_id: str,
    warnings: Optional[list[str]] = None,
    next_step: str,
    **extra: Any,
) -> Dict[str, Any]:
    envelope: Dict[str, Any] = {
        "ok": ok,
        "mode": mode,
        "case_id": case_id,
        "warnings": warnings or [],
        "next_step": next_step,
    }
    envelope.update(extra)
    return envelope


def _normalize_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _context_mode_repo_project() -> tuple[str, Optional[str], Optional[str]]:
    if not hasattr(server_module, "get_execution_context"):
        return "unknown", None, None
    try:
        context = server_module.get_execution_context()
    except Exception:
        return "unknown", None, None
    if context is None:
        return "unknown", None, None

    mode = str(getattr(context, "mode", "") or "unknown")
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
    return mode, repo_default, project_default


def _empty_case_fields(
    *,
    case_closed: Optional[bool] = None,
    project_name: Optional[str] = None,
    repo_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "case_type": None,
        "case_closed": case_closed,
        "lifecycle_status": None,
        "registry_status": None,
        "doc_binding": None,
        "last_fix_link": None,
        "closure_reason": None,
        "project_name": project_name,
        "repo_id": repo_id,
    }


def _doc_binding_for_record(record: Any, *, case_id: str) -> Any:
    metadata = getattr(record, "metadata", None)
    doc_path = str(getattr(record, "doc_path", "") or "")
    binding = doc_binding_from_metadata(
        metadata if isinstance(metadata, dict) else None,
        fallback_case_id=case_id or None,
        fallback_doc_path=doc_path or None,
    )
    if binding is not None:
        return binding
    if not case_id or not doc_path:
        return None
    return build_canonical_doc_binding(
        case_id,
        doc_path,
        {},
        preferred_doc_name=str(getattr(record, "doc_name", "") or case_id),
    )


def _record_to_status_payload(record: Any) -> Dict[str, Any]:
    case_id = str(getattr(record, "case_id", "") or "")
    lifecycle = case_status_snapshot(record, doc_binding=_doc_binding_for_record(record, case_id=case_id))
    lifecycle_data = lifecycle.to_dict()
    return {
        "case_type": lifecycle_data["case_type"],
        "case_closed": lifecycle_data["case_closed"],
        "lifecycle_status": lifecycle_data["lifecycle_status"],
        "registry_status": lifecycle_data["registry_status_after"],
        "doc_binding": lifecycle_data["doc_binding"],
        "last_fix_link": lifecycle_data["last_fix_link"],
        "closure_reason": lifecycle_data["closure_reason"],
        "project_name": getattr(record, "project_name", None),
        "repo_id": getattr(record, "repo_id", None),
        "next_step": lifecycle_data["next_step"],
    }


@app.tool(
    **read_only_local_tool(
        title="Get Case Status",
        tags=("cases", "bugs", "security", "read-only"),
    )
)
async def get_case_status(
    case_id: str,
    project: Optional[str] = None,
    repo_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return one Council-safe case lifecycle snapshot from registry truth."""
    normalized_case_id = _normalize_str(case_id)
    normalized_project = _normalize_str(project)
    normalized_repo_id = _normalize_str(repo_id)
    mode, active_repo_root, default_project = _context_mode_repo_project()
    query_project = normalized_project or default_project

    if not normalized_case_id:
        return _operator_envelope(
            ok=False,
            mode=mode,
            case_id="",
            warnings=["case_id is required"],
            next_step="Provide a case_id and retry get_case_status.",
            **_empty_case_fields(project_name=query_project, repo_id=normalized_repo_id),
        )

    backend = getattr(server_module, "storage_backend", None)
    if backend is None or not hasattr(backend, "fetch_case_registry_record"):
        return _operator_envelope(
            ok=False,
            mode=mode,
            case_id=normalized_case_id,
            warnings=["shared case registry backend is unavailable"],
            next_step="Configure the shared case registry backend, then retry get_case_status.",
            **_empty_case_fields(project_name=query_project, repo_id=normalized_repo_id),
        )

    if not active_repo_root:
        return _operator_envelope(
            ok=False,
            mode=mode,
            case_id=normalized_case_id,
            warnings=["unable to resolve authoritative repo_root for case ownership validation"],
            next_step="Bind Scribe to an active repo/project scope, then retry get_case_status.",
            **_empty_case_fields(project_name=query_project, repo_id=normalized_repo_id),
        )

    try:
        record = await backend.fetch_case_registry_record(
            case_id=normalized_case_id,
            repo_root=active_repo_root,
            project_name=query_project,
        )
    except Exception as exc:
        return _operator_envelope(
            ok=False,
            mode=mode,
            case_id=normalized_case_id,
            warnings=[f"failed to fetch shared case registry record: {exc}"],
            next_step="Resolve backend fetch failure and retry get_case_status.",
            **_empty_case_fields(project_name=query_project, repo_id=normalized_repo_id),
        )

    if record is None:
        return _operator_envelope(
            ok=False,
            mode=mode,
            case_id=normalized_case_id,
            warnings=["case is not registered in the shared case registry for the active repo/project scope"],
            next_step="Verify the case_id, active repo/project scope, and optional filters, then retry get_case_status.",
            **_empty_case_fields(project_name=query_project, repo_id=normalized_repo_id),
        )

    record_repo_id = _normalize_str(getattr(record, "repo_id", None))
    if normalized_repo_id and record_repo_id != normalized_repo_id:
        return _operator_envelope(
            ok=False,
            mode=mode,
            case_id=normalized_case_id,
            warnings=["case is not registered in the shared case registry for the requested repo_id filter"],
            next_step="Verify the repo_id filter for the active repo/project scope, then retry get_case_status.",
            **_empty_case_fields(project_name=query_project, repo_id=normalized_repo_id),
        )

    payload = _record_to_status_payload(record)
    next_step = str(payload.pop("next_step"))
    return _operator_envelope(
        ok=True,
        mode=mode,
        case_id=normalized_case_id,
        next_step=next_step,
        **payload,
    )
