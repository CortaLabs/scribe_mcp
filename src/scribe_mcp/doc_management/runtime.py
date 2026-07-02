"""Runtime orchestration helpers for the manage_docs MCP tool."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from scribe_mcp.log_intelligence import build_report_from_path
from scribe_mcp.doc_management.manager import apply_doc_change, resolve_registered_doc_key, _resolve_doc_path
from scribe_mcp.doc_management.scaffold_quality import (
    collect_managed_doc_quality_warnings,
    configured_log_quality_exclusion_paths,
    is_managed_doc_quality_target,
    summarize_quality_warnings,
)
from scribe_mcp.doc_management.quality.results import SCHEMA_VERSION, build_quality_agent_actions, enrich_quality_warning_context, group_quality_warnings, normalize_warnings
from scribe_mcp.doc_management.quality.rules.release_gate import resolve_quality_mode
from scribe_mcp.readiness import (
    build_readiness_summary,
    collect_managed_doc_quality_blockers,
    collect_managed_doc_quality_state,
)
from scribe_mcp.doc_management import healing as healing_shared
from scribe_mcp.doc_management import indexing as indexing_shared
from scribe_mcp.doc_management import intelligence_workflows as intelligence_workflows_shared
from scribe_mcp.doc_management import intelligence_exports as intelligence_exports_shared
from scribe_mcp.doc_management import special_indexes as special_indexes_shared
from scribe_mcp.doc_management import utils as utils_shared
from scribe_mcp.doc_management.actions import append as append_actions
from scribe_mcp.doc_management.actions import batch as batch_actions
from scribe_mcp.doc_management.actions import create as create_actions
from scribe_mcp.doc_management.actions import edit as edit_actions
from scribe_mcp.doc_management.actions import query as query_actions
from scribe_mcp.doc_management.actions import search as search_actions
from scribe_mcp.doc_management.actions import status as status_actions
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import (
    LoggingContext,
    ProjectResolutionError,
    build_resolution_metadata,
)
from scribe_mcp.shared.write_barrier import assert_writes_allowed
from scribe_mcp.tools.agent_project_utils import resolve_authoritative_write_scope
from scribe_mcp.utils.slug import slugify_project_name, normalize_project_input


PRIMARY_ACTIONS = {
    "create",
    "replace_section",
    "apply_patch",
    "replace_range",
    "replace_text",
    "append",
    "status_update",
    "frontmatter_update",
}


def _verified_execution_repo_root(server_module: Any) -> Optional[str]:
    if not hasattr(server_module, "get_execution_context"):
        return None
    try:
        exec_context = server_module.get_execution_context()
    except Exception:
        return None
    resolved_scope = getattr(exec_context, "resolved_scope", None)
    repo_root = getattr(resolved_scope, "repo_root", None) or getattr(exec_context, "repo_root", None)
    if not repo_root:
        return None
    provenance = getattr(getattr(resolved_scope, "provenance", None), "repo_root", None)
    if resolved_scope is not None and provenance != "verified":
        return None
    try:
        return str(Path(str(repo_root)).expanduser().resolve())
    except Exception:
        return str(repo_root)

# Deprecated action aliases intentionally removed in fail-hard mode.
DEPRECATED_ALIASES: Dict[str, tuple[str, Dict[str, Any]]] = {}

HIDDEN_ACTIONS = {
    "normalize_headers",
    "generate_toc",
    "validate_crosslinks",
    "list_sections",
    "list_checklist_items",
    "preview_reconciliation",
    "apply_global_changelog",
    "project_health",
    "quality_check",
    "quality_handoff_check",
    "scaffold_quality_check",
    "rehome_doc",
    "search",
    "batch",
    "topology_scan",
    "metadata_scan",
    "metadata_repair",
    "stale_cleanup_scan",
    "ingestion_manifest_inspect",
    "regenerate_intelligence_exports",
}

VALID_ACTIONS = PRIMARY_ACTIONS | HIDDEN_ACTIONS

_CLEANUP_ACTIONS = {"project_health", "rehome_doc"}
_ADVANCED_ACTIONS = HIDDEN_ACTIONS - _CLEANUP_ACTIONS

ACTION_ROUTER = {
    "create": "edit",
    "create_doc": "edit",
    "replace_section": "edit",
    "apply_patch": "edit",
    "replace_range": "edit",
    "replace_text": "edit",
    "append": "append",
    "status_update": "status",
    "frontmatter_update": "edit",
    "normalize_headers": "query_transform",
    "generate_toc": "query_transform",
    "validate_crosslinks": "query_transform",
    "list_sections": "query",
    "list_checklist_items": "query",
    "preview_reconciliation": "query",
    "apply_global_changelog": "query",
    "search": "search",
    "batch": "batch",
    "topology_scan": "query",
    "metadata_scan": "query",
    "metadata_repair": "edit",
    "stale_cleanup_scan": "query",
    "ingestion_manifest_inspect": "query",
    "regenerate_intelligence_exports": "edit",
}


def build_manage_docs_action_manifest() -> Dict[str, Any]:
    """Return a stable, truthful action-discovery payload for manage_docs."""
    return {
        "primary_actions": sorted(PRIMARY_ACTIONS),
        "cleanup_actions": sorted(_CLEANUP_ACTIONS),
        "advanced_actions": sorted(_ADVANCED_ACTIONS),
        "all_actions": sorted(VALID_ACTIONS),
    }

_MUTATION_ACTIONS = {
    "replace_section",
    "apply_patch",
    "replace_range",
    "append",
    "status_update",
    "frontmatter_update",
    "normalize_headers",
    "generate_toc",
    "replace_text",
    "validate_crosslinks",
    "metadata_repair",
}

_CUSTOM_DOC_TYPES = {
    "research",
    "bugs",
    "bug",
    "bug_report",
    "security",
    "security_report",
    "reviews",
    "review",
    "agent_cards",
}
_READ_ONLY_REGISTRATION_GATED_ACTIONS = {
    "list_sections",
    "list_checklist_items",
    "preview_reconciliation",
    "search",
}
_DOC_TARGETED_REGISTRATION_ACTIONS = (
    _MUTATION_ACTIONS
    | _READ_ONLY_REGISTRATION_GATED_ACTIONS
    | {"quality_check", "scaffold_quality_check"}
)


_SPECIAL_DOC_TYPES = {"research", "bug", "security", "review", "agent_card"}
_UNSAFE_PROJECT_WRITE_RESOLUTION_SOURCES = {
    "agent_context",
    "compat_state_current_project",
    "compat_active_project",
    "compat_recent_project",
}
_IN_PROGRESS_PHASE_RE = re.compile(r"##\s+(Phase\s+.+?)\s*\(In Progress\)")
_DOC_KEY_ALIASES: Dict[str, str] = {
    "architecture_guide": "architecture",
    "architecture-guide": "architecture",
    "phaseplan": "phase_plan",
}
_SINGLETON_HEALTH_DOC_TYPES = {"architecture", "phase_plan", "checklist"}


def _canonical_doc_key(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace(".md", "")
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return _DOC_KEY_ALIASES.get(normalized, normalized)


def _health_doc_identity(entry: Dict[str, Any]) -> str:
    path_value = str(entry.get("path") or "")
    path = Path(path_value)
    stem_key = _canonical_doc_key(path.stem) if path.suffix else ""
    doc_type_key = _canonical_doc_key(entry.get("doc_type"))
    project_slug = str(entry.get("project_slug") or "unscoped")
    if doc_type_key in _SINGLETON_HEALTH_DOC_TYPES:
        return f"{project_slug}:{doc_type_key}"
    best_key = stem_key or doc_type_key or _canonical_doc_key(path.name)
    return f"{project_slug}:{best_key}:{path_value}"


def _dedupe_health_entries(entries: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    deduped: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for entry in sorted(entries, key=lambda item: float(item.get("modified_at") or 0.0), reverse=True):
        identity = _health_doc_identity(entry)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(entry)
    return deduped


def _extract_current_phase(phase_plan_path: Optional[str]) -> Optional[str]:
    if not phase_plan_path:
        return None
    try:
        with open(phase_plan_path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                match = _IN_PROGRESS_PHASE_RE.search(line)
                if match:
                    return match.group(1).strip()
    except OSError:
        return None
    return None


def _classify_dev_plans_lane(*, project_root: Path, docs_dir: Path) -> Dict[str, str]:
    resolved_root = project_root.expanduser().resolve()
    resolved_docs_dir = docs_dir.expanduser().resolve()
    modern_docs_dir = resolved_root / ".scribe" / "docs" / "dev_plans"
    legacy_docs_dir = resolved_root / "docs" / "dev_plans"
    if resolved_docs_dir == modern_docs_dir or modern_docs_dir in resolved_docs_dir.parents:
        return {"root_kind": "modern", "lane_class": "canonical"}
    if resolved_docs_dir == legacy_docs_dir or legacy_docs_dir in resolved_docs_dir.parents:
        return {"root_kind": "legacy", "lane_class": "compatibility"}
    return {"root_kind": "custom", "lane_class": "explicit"}


def _collect_log_friction_signals(active_project: Dict[str, Any]) -> list[Dict[str, Any]]:
    progress_log = str(active_project.get("progress_log") or "").strip()
    if not progress_log:
        return []
    path = Path(progress_log)
    if not path.exists():
        return []
    try:
        report = build_report_from_path(path, project=active_project.get("name"))
    except OSError:
        return []
    signals = report.get("signals")
    if not isinstance(signals, list):
        return []
    return [dict(signal) for signal in signals if str(signal.get("code", "")).startswith("LOG_")]


def _is_manage_docs_write_intent(action: str) -> bool:
    return action in {"create", "rehome_doc"} or action in _MUTATION_ACTIONS


def _looks_like_path(value: str) -> bool:
    return "/" in value or "\\" in value or value.endswith(".md")


def _path_registration_key(project: Dict[str, Any], doc_name: str, doc_path: Path, docs: Dict[str, str]) -> str:
    stem_key = doc_path.stem
    existing_target = docs.get(stem_key)
    if existing_target:
        try:
            if Path(existing_target).expanduser().resolve() == doc_path.resolve():
                return stem_key
        except Exception:
            if str(existing_target) == str(doc_path):
                return stem_key
        project_root = Path(str(project.get("root") or "")).expanduser().resolve()
        try:
            return str(doc_path.resolve().relative_to(project_root)).replace("\\", "/")
        except Exception:
            return str(doc_name).replace("\\", "/").lstrip("./")
    return stem_key


async def _merged_registered_docs(
    *,
    backend: Any,
    project: Dict[str, Any],
    project_name: str,
) -> Dict[str, str]:
    current_docs = dict(project.get("docs", {}) or {})
    fetch_project = getattr(backend, "fetch_project", None)
    if not callable(fetch_project):
        return current_docs

    try:
        record = fetch_project(project_name, repo_root=project.get("root"))
        if inspect.isawaitable(record):
            record = await record
    except Exception:
        return current_docs

    docs_json = getattr(record, "docs_json", None)
    if not isinstance(docs_json, str) or not docs_json.strip():
        return current_docs

    try:
        persisted_docs = json.loads(docs_json)
    except json.JSONDecodeError:
        return current_docs
    if not isinstance(persisted_docs, dict):
        return current_docs

    merged_docs = {str(key): str(value) for key, value in persisted_docs.items()}
    merged_docs.update({str(key): str(value) for key, value in current_docs.items()})
    return merged_docs


def _default_rehome_relative_path(source_path: Path, project_root: Path) -> Path:
    try:
        repo_relative = source_path.relative_to(project_root)
    except ValueError:
        return Path(source_path.name)
    if repo_relative.parts and repo_relative.parts[0] == "research":
        return repo_relative
    if source_path.parent.name == "research" or source_path.name.startswith("RESEARCH_"):
        return Path("research") / source_path.name
    return Path(source_path.name)


def _coerce_rehome_relative_path(
    candidate: Path,
    *,
    target_docs_dir: Path,
    target_project_root: Path,
) -> Path:
    """Keep caller-provided rehome targets relative to the target docs root."""
    if candidate.is_absolute():
        try:
            return candidate.expanduser().resolve().relative_to(target_docs_dir)
        except ValueError as exc:
            raise ValueError(
                "rehome_doc target path must stay within the target project's docs_dir."
            ) from exc

    if ".scribe" not in candidate.parts:
        return candidate

    try:
        return (target_project_root / candidate).resolve().relative_to(target_docs_dir)
    except ValueError as exc:
        raise ValueError(
            "rehome_doc target paths must be docs-relative; nested .scribe paths are not allowed."
        ) from exc


def _case_registry_method(storage_backend: Any) -> Optional[Callable[..., Any]]:
    for method_name in (
        "upsert_case_registry_record",
        "upsert_case_registry",
        "upsert_case_record",
        "register_case",
    ):
        candidate = getattr(storage_backend, method_name, None)
        if callable(candidate):
            return candidate
    return None


async def _call_case_registry_method(method: Callable[..., Any], upsert_kwargs: Dict[str, Any]) -> None:
    def _is_signature_mismatch(exc: TypeError) -> bool:
        message = str(exc)
        markers = (
            "unexpected keyword argument",
            "positional argument",
            "required positional argument",
            "keyword-only argument",
            "multiple values for argument",
            "takes",
            "missing",
        )
        return any(marker in message for marker in markers)

    attempts = (
        ((), upsert_kwargs),
        ((upsert_kwargs,), {}),
        ((), {"payload": upsert_kwargs}),
    )
    last_error: Optional[Exception] = None
    for args, kwargs in attempts:
        try:
            result = method(*args, **kwargs)
            if inspect.isawaitable(result):
                await result
            return
        except TypeError as exc:
            if not _is_signature_mismatch(exc):
                raise
            last_error = exc
            continue
    if last_error is not None:
        raise last_error


def _resolve_mutated_doc_path(
    *,
    response: Dict[str, Any],
    project: Dict[str, Any],
    doc_name: Optional[str],
    doc_category: str,
) -> Optional[Path]:
    response_path = response.get("path")
    if isinstance(response_path, str) and response_path.strip():
        return Path(response_path).resolve()

    docs_mapping = project.get("docs", {}) or {}
    for key in (doc_name, doc_category):
        if not key:
            continue
        candidate = docs_mapping.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return Path(candidate).resolve()
    return None


async def _refresh_case_registry_for_mutation(
    *,
    storage_backend: Any,
    project: Dict[str, Any],
    response: Dict[str, Any],
    doc_name: Optional[str],
    doc_category: str,
) -> Optional[str]:
    if not storage_backend:
        return None

    register_method = _case_registry_method(storage_backend)
    if register_method is None:
        return None

    target_path = _resolve_mutated_doc_path(
        response=response,
        project=project,
        doc_name=doc_name,
        doc_category=doc_category,
    )
    if target_path is None or not target_path.exists():
        return None

    extracted = utils_shared.extract_case_registry_metadata_from_report(
        target_path,
        project_root=Path(str(project.get("root", ""))),
        project=project,
    )
    existing_record = None
    fetch_record = getattr(storage_backend, "fetch_case_registry_record", None)
    if callable(fetch_record) and isinstance(extracted, dict) and extracted.get("case_id"):
        try:
            existing_record = await fetch_record(
                case_id=str(extracted["case_id"]),
                repo_root=str(project.get("root") or ""),
                project_name=str(project.get("name") or ""),
            )
        except Exception:
            existing_record = None
    status_override = None
    existing_status = getattr(existing_record, "status", None)
    if isinstance(existing_record, dict):
        existing_status = existing_record.get("status")
    if utils_shared.case_status_closes(existing_status):
        status_override = utils_shared.normalize_case_status(existing_status)
    upsert_kwargs = utils_shared.build_case_registry_upsert_kwargs(
        extracted=extracted,
        existing_record=existing_record,
        overrides={
            "source_tool": "manage_docs.mutation",
            "status": status_override,
        },
    )
    if upsert_kwargs is None:
        return None

    try:
        await _call_case_registry_method(register_method, upsert_kwargs)
    except Exception as exc:
        return f"Case registry refresh failed after mutation: {exc}"
    return None


def _attach_case_doc_binding_readback(
    response: Dict[str, Any],
    *,
    project: Dict[str, Any],
    doc_name: Optional[str],
    doc_category: str,
) -> Dict[str, Any]:
    canonical_category = utils_shared.normalize_case_report_category(
        doc_category,
        case_reference=doc_name,
    )
    if canonical_category is None and not utils_shared.looks_like_case_report_reference(doc_name):
        return response

    target_path = _resolve_mutated_doc_path(
        response=response,
        project=project,
        doc_name=doc_name,
        doc_category=canonical_category or doc_category,
    )
    if target_path is None or not target_path.exists():
        return response

    extracted = utils_shared.extract_case_registry_metadata_from_report(
        target_path,
        project_root=Path(str(project.get("root", ""))),
        project=project,
    )
    if not isinstance(extracted, dict) or not extracted.get("case_id"):
        return response

    binding = utils_shared.build_case_doc_binding_metadata(
        str(extracted["case_id"]),
        str(target_path),
        project.get("docs", {}) if isinstance(project.get("docs"), dict) else {},
        primary_key=doc_name,
    )
    response["canonical_doc_name"] = binding["canonical_doc_name"]
    response["canonical_doc_path"] = binding["canonical_doc_path"]
    response["aliases"] = binding["aliases"]
    return response


async def _resolve_manage_docs_actor_id(
    *,
    caller_agent: Optional[str],
    execution_context: Any,
    server_module: Any,
) -> str:
    """Prefer caller-facing identity for attribution, fall back to runtime internal identity."""
    if isinstance(caller_agent, str) and caller_agent.strip():
        return caller_agent.strip()

    runtime_identity = getattr(execution_context, "agent_identity", None)
    display_name = getattr(runtime_identity, "display_name", None)
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()

    agent_identity = server_module.get_agent_identity()
    if agent_identity:
        resolved = await agent_identity.get_or_create_agent_id()
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()

    return "Scribe"


def _attach_manage_docs_project_context(
    response: Dict[str, Any],
    *,
    context: LoggingContext,
) -> Dict[str, Any]:
    response.setdefault("project_name", context.project.get("name") if context.project else None)
    response.setdefault("project_resolution", build_resolution_metadata(context))
    return response


async def _attach_create_section_inventory(response: Dict[str, Any]) -> Dict[str, Any]:
    def _extract_preview_text(payload: Dict[str, Any]) -> Optional[str]:
        content_value = payload.get("content")
        if isinstance(content_value, str) and content_value.strip():
            return content_value

        preview_value = payload.get("preview")
        if isinstance(preview_value, str) and preview_value.strip():
            return preview_value

        diff_value = payload.get("diff")
        if isinstance(diff_value, str) and diff_value.strip():
            added_lines: list[str] = []
            for line in diff_value.splitlines():
                if line.startswith("+++"):
                    continue
                if line.startswith("+"):
                    added_lines.append(line[1:])
            if added_lines:
                return "\n".join(added_lines)
        return None

    path_value = response.get("path")
    section_payload: Optional[Dict[str, Any]] = None
    if isinstance(path_value, str) and path_value.strip():
        path = Path(path_value)
        if path.exists() and path.is_file():
            try:
                section_payload = await query_actions.inspect_document_sections(path)
            except Exception:
                section_payload = None

    if section_payload is None:
        preview_content = _extract_preview_text(response)
        if isinstance(preview_content, str) and preview_content.strip():
            try:
                section_payload = query_actions.inspect_document_sections_from_text(preview_content)
            except Exception:
                section_payload = None

    if section_payload is None:
        return response

    response.setdefault("editable_sections", section_payload.get("sections", []))
    response.setdefault("section_source", section_payload.get("section_source"))
    if section_payload.get("warning"):
        response.setdefault("section_warning", section_payload.get("warning"))
    if section_payload.get("duplicates"):
        response.setdefault("section_duplicates", section_payload.get("duplicates"))
    return response


async def _load_project_record(
    *,
    project_name: str,
    server_module: Any,
) -> Optional[Dict[str, Any]]:
    backend = getattr(server_module, "storage_backend", None)
    if backend and hasattr(backend, "fetch_project"):
        try:
            repo_root = _verified_execution_repo_root(server_module)
            if repo_root:
                record = await backend.fetch_project(project_name, repo_root=repo_root)
            else:
                record = await backend.fetch_project(project_name)
        except Exception:
            record = None
        if record:
            payload = {
                "name": record.name,
                "root": record.repo_root,
                "progress_log": record.progress_log_path,
            }
            if record.progress_log_path:
                payload["docs_dir"] = str(Path(record.progress_log_path).expanduser().resolve().parent)
            if getattr(record, "docs_json", None):
                try:
                    payload["docs"] = json.loads(record.docs_json)
                except (TypeError, json.JSONDecodeError):
                    payload["docs"] = {}
                progress_log = payload["docs"].get("progress_log") if isinstance(payload.get("docs"), dict) else None
                if isinstance(progress_log, str) and progress_log:
                    payload["docs_dir"] = str(Path(progress_log).expanduser().resolve().parent)
            return payload

    state_manager = getattr(server_module, "state_manager", None)
    if state_manager and hasattr(state_manager, "load"):
        try:
            state = await state_manager.load()
            project = state.get_project(project_name)
        except Exception:
            project = None
        if project:
            return dict(project)
    return None


async def _handle_project_health(
    *,
    active_project: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    helper: LoggingToolMixin,
    context: LoggingContext,
) -> Dict[str, Any]:
    repo_root = Path(str(active_project.get("root") or "")).expanduser()
    if not repo_root.exists():
        return helper.apply_context_payload(
            helper.error_response(
                "project_health requires an active project with a readable repo root.",
            ),
            context,
        )

    limit = int((metadata or {}).get("limit", 20) or 20)
    discovered = utils_shared.discover_scribe_source_documents(repo_root)
    entries: list[Dict[str, Any]] = []
    for doc in discovered:
        try:
            modified_at = doc.path.stat().st_mtime
        except OSError:
            modified_at = 0.0
        entries.append(
            {
                "project_slug": doc.project_slug or "unscoped",
                "path": str(doc.path),
                "doc_type": doc.doc_type,
                "source_family": doc.source_family,
                "category": doc.category,
                "case_id": doc.case_id,
                "modified_at": modified_at,
            }
        )

    entries = _dedupe_health_entries(entries)
    active_slug = slugify_project_name(active_project.get("name", ""))
    grouped: Dict[str, list[Dict[str, Any]]] = {}
    for entry in entries[: max(limit * 3, limit)]:
        grouped.setdefault(entry["project_slug"], []).append(entry)

    project_groups = []
    for project_slug, docs in sorted(
        grouped.items(),
        key=lambda item: max(doc["modified_at"] for doc in item[1]) if item[1] else 0.0,
        reverse=True,
    ):
        project_groups.append(
            {
                "project_slug": project_slug,
                "is_active_project": project_slug == active_slug,
                "recent_docs": docs[:limit],
            }
        )

    response = {
        "ok": True,
        "active_project": active_project.get("name"),
        "active_project_slug": active_slug,
        "recent_projects": project_groups[:limit],
        "cross_project_recent_docs": [
            entry for entry in entries[: max(limit * 2, limit)]
            if entry["project_slug"] != active_slug
        ][:limit],
    }

    current_phase = _extract_current_phase((active_project.get("docs") or {}).get("phase_plan"))
    active_project_with_phase = dict(active_project)
    active_project_with_phase["current_phase"] = current_phase
    managed_doc_quality = collect_managed_doc_quality_state(active_project_with_phase)
    log_signals = _collect_log_friction_signals(active_project)
    readiness = build_readiness_summary(
        current_phase=current_phase,
        managed_doc_quality=managed_doc_quality,
        log_signals=log_signals,
    ).to_dict()
    response["managed_doc_quality"] = managed_doc_quality
    response["readiness_summary"] = readiness
    warnings = managed_doc_quality.get("warnings") if isinstance(managed_doc_quality, dict) else []
    documents = managed_doc_quality.get("documents") if isinstance(managed_doc_quality, dict) else []
    digest_items: list[Dict[str, Any]] = []
    ownership_counts = {"active_project": 0, "cross_project": 0, "unscoped": 0}
    normalized_warnings: list[Dict[str, Any]] = []
    if isinstance(warnings, list) and warnings:
        normalized_warnings.extend(warning for warning in warnings if isinstance(warning, dict))
    elif isinstance(documents, list):
        for document in documents:
            if not isinstance(document, dict):
                continue
            for warning_code in document.get("warning_codes") or []:
                normalized_warnings.append(
                    {
                        "code": warning_code,
                        "severity": "unknown",
                        "blocking": warning_code in set(document.get("blocking_warning_codes") or []),
                        "doc_name": document.get("doc_name"),
                        "path": document.get("path"),
                        "suggested_repair": None,
                    }
                )

    for warning in normalized_warnings:
        path = str(warning.get("path") or "")
        project_slug = "unscoped"
        if path:
            matched = next((doc for doc in entries if doc.get("path") == path), None)
            if matched:
                project_slug = str(matched.get("project_slug") or "unscoped")
        owner_scope = "active_project" if project_slug == active_slug else ("unscoped" if project_slug == "unscoped" else "cross_project")
        ownership_counts[owner_scope] += 1
        digest_items.append(
            {
                "warning_code": warning.get("code"),
                "severity": warning.get("severity"),
                "blocking": bool(warning.get("blocking")),
                "source_doc_name": warning.get("doc_name"),
                "source_path": path or None,
                "source_project_slug": project_slug,
                "ownership_scope": owner_scope,
                "truth_label": "direct_artifact",
                "next_safe_action": warning.get("suggested_repair"),
            }
        )
    docs_dir = Path(str(active_project.get("docs_dir") or "")).expanduser()
    project_root = Path(str(active_project.get("root") or "")).expanduser().resolve()
    lane_classification = _classify_dev_plans_lane(project_root=project_root, docs_dir=docs_dir)
    archive_preflight_dir = docs_dir / "archive" / "preflight"
    archive_family_counts: Dict[str, int] = {}
    archive_file_count = 0
    if archive_preflight_dir.exists() and archive_preflight_dir.is_dir():
        for child in archive_preflight_dir.iterdir():
            if child.is_dir():
                count = sum(1 for file_path in child.rglob("*") if file_path.is_file())
                archive_family_counts[child.name] = count
                archive_file_count += count
        # Include root-level files as uncategorized archive artifacts.
        root_level_count = sum(1 for file_path in archive_preflight_dir.iterdir() if file_path.is_file())
        if root_level_count:
            archive_family_counts["uncategorized"] = root_level_count
            archive_file_count += root_level_count

    active_docs = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
    registered_doc_paths: Dict[str, str] = {}
    missing_registered_paths: list[str] = []
    alias_by_path: Dict[str, list[str]] = {}
    for alias, raw_path in active_docs.items():
        path_str = str(raw_path) if isinstance(raw_path, str) else ""
        if not path_str:
            continue
        resolved_path = str(Path(path_str).expanduser())
        registered_doc_paths[alias] = resolved_path
        alias_by_path.setdefault(resolved_path, []).append(alias)
        if not Path(path_str).expanduser().exists():
            missing_registered_paths.append(alias)

    duplicate_claimed_paths = {
        path_value: sorted(aliases)
        for path_value, aliases in alias_by_path.items()
        if len(aliases) > 1
    }
    active_doc_set = {str(Path(entry.get("path") or "").expanduser()) for entry in entries if entry.get("project_slug") == active_slug and entry.get("path")}

    def _is_system_managed_index(path_value: str) -> bool:
        candidate = Path(path_value).expanduser()
        if candidate.name != "INDEX.md":
            return False
        try:
            relative = candidate.relative_to(docs_dir)
        except ValueError:
            return False
        return relative.parts == ("research", "INDEX.md")

    def _is_indexed_research_doc(path_value: str) -> bool:
        candidate = Path(path_value).expanduser()
        if candidate.name == "INDEX.md":
            return False
        try:
            relative = candidate.relative_to(docs_dir)
        except ValueError:
            return False
        if not relative.parts or relative.parts[0] != "research":
            return False
        index_path = docs_dir / "research" / "INDEX.md"
        if not index_path.exists():
            return False
        try:
            index_text = index_path.read_text(encoding="utf-8")
        except OSError:
            return False
        return candidate.name in index_text or relative.as_posix() in index_text

    unregistered_active_docs = sorted(
        path_value
        for path_value in active_doc_set
        if path_value
        and path_value not in set(registered_doc_paths.values())
        and not _is_system_managed_index(path_value)
        and not _is_indexed_research_doc(path_value)
    )
    discovered_entry_by_path = {
        str(Path(entry.get("path") or "").expanduser()): entry
        for entry in entries
        if entry.get("project_slug") == active_slug and entry.get("path")
    }
    registration_drift: list[Dict[str, Any]] = []
    for path_value in unregistered_active_docs:
        entry = discovered_entry_by_path.get(path_value, {})
        registration_drift.append(
            {
                "code": "DOC_REGISTRY_DRIFT",
                "kind": "filesystem_only",
                "path": path_value,
                "doc_type": entry.get("doc_type"),
                "source_family": entry.get("source_family"),
                "available_action": "Register this file through manage_docs(action='create') or manage_docs(action='rehome_doc'), then rerun manage_docs(action='project_health').",
            }
        )
    for alias in sorted(missing_registered_paths):
        registration_drift.append(
            {
                "code": "DOC_REGISTRY_DRIFT",
                "kind": "docs_json_missing_file",
                "alias": alias,
                "path": registered_doc_paths.get(alias),
                "available_action": "Repair the docs_json mapping by recreating/rehome_doc-ing the document, or remove the stale alias through a governed metadata repair.",
            }
        )

    modern_dev_plans_root = project_root / ".scribe" / "docs" / "dev_plans"
    legacy_dev_plans_root = project_root / "docs" / "dev_plans"
    dual_root_inventory = {
        "modern": {
            "root_kind": "modern",
            "lane_class": "canonical",
            "path": str(modern_dev_plans_root),
            "exists": modern_dev_plans_root.exists(),
        },
        "legacy": {
            "root_kind": "legacy",
            "lane_class": "compatibility",
            "path": str(legacy_dev_plans_root),
            "exists": legacy_dev_plans_root.exists(),
        },
    }

    index_warning_codes = {"SCF_INDEX_MISSING", "SCF_INDEX_STALE", "SCF_DOC_UNINDEXED"}
    index_warnings: list[Dict[str, Any]] = []
    for item in digest_items:
        code = str(item.get("warning_code") or "")
        if code not in index_warning_codes:
            continue
        source_path = str(item.get("source_path") or "")
        matched_entry = next((entry for entry in entries if str(entry.get("path") or "") == source_path), None)
        if matched_entry and str(matched_entry.get("doc_type") or "") != "research":
            continue
        if matched_entry is None and "/research/" not in source_path.replace("\\", "/"):
            continue
        index_warnings.append(item)

    project_artifact_families = {"review_report", "agent_report_card", "bug_report", "security_report"}
    project_artifact_docs = [entry for entry in entries if str(entry.get("doc_type") or "") in project_artifact_families]
    project_artifact_warning_count = 0
    for item in digest_items:
        source_path = str(item.get("source_path") or "")
        matched_entry = next((entry for entry in project_artifact_docs if str(entry.get("path") or "") == source_path), None)
        source_doc_name = str(item.get("source_doc_name") or "").lower()
        if matched_entry or source_doc_name.startswith(("review_report", "agent_report_card", "bug_report", "security_report")):
            project_artifact_warning_count += 1

    status_sections = {
        "organization": {
            "status": "needs_attention" if digest_items else "ok",
            "truth_label": "derived_signal",
            "summary": f"Organization digest contains {len(digest_items)} quality warning signals.",
            "next_safe_action": "Review warning ownership scopes and resolve active-project warnings first."
            if digest_items
            else "No organization warning signals detected.",
        },
        "index": {
            "status": "needs_attention" if index_warnings else "ok",
            "truth_label": "derived_signal",
            "summary": f"Detected {len(index_warnings)} research-index warning signals from managed-doc quality warnings.",
            "next_safe_action": "Run manage_docs(action='quality_check', ...) for research docs and address index warning codes (missing/stale/unindexed)."
            if index_warnings
            else "No research-index warning codes detected.",
        },
        "project_artifacts": {
            "status": "needs_attention" if project_artifact_warning_count > 0 else ("evidence_present" if project_artifact_docs else "no_evidence"),
            "truth_label": "direct_artifact",
            "summary": (
                f"Discovered {len(project_artifact_docs)} project-level synthesis/review artifact(s); "
                f"{project_artifact_warning_count} warning signal(s) currently attached."
            ),
            "next_safe_action": "Use manage_docs(action='quality_check', doc_name=...) for synthesis/review docs and rely on project-level docs indexes (e.g., REVIEW_INDEX.md), not research/INDEX.md.",
        },
        "archive": {
            "status": "evidence_present" if archive_file_count > 0 else "no_evidence",
            "truth_label": "direct_artifact",
            "summary": f"Archive preflight contains {archive_file_count} files across {len(archive_family_counts)} families.",
            "next_safe_action": "Inspect docs_dir/archive/preflight families before any archive cleanup."
            if archive_file_count > 0
            else "No archive preflight evidence found; generate/archive evidence before cleanup operations.",
            "cleanup_mode": "preview_only",
            "destructive_default": False,
            "preview_groups": [
                {
                    "group": family,
                    "file_count": count,
                    "root_kind": lane_classification["root_kind"],
                    "lane_class": lane_classification["lane_class"],
                }
                for family, count in sorted(archive_family_counts.items())
            ],
        },
        "artifact_claims": {
            "status": "needs_attention" if missing_registered_paths or duplicate_claimed_paths or unregistered_active_docs or registration_drift else "ok",
            "truth_label": "derived_signal",
            "summary": (
                f"Registered docs: {len(registered_doc_paths)}; missing paths: {len(missing_registered_paths)}; "
                f"duplicate path claims: {len(duplicate_claimed_paths)}; unregistered active docs: {len(unregistered_active_docs)}; "
                f"registration drift records: {len(registration_drift)}."
            ),
            "next_safe_action": "Repair missing doc registrations, register disk-only docs through manage_docs, and deduplicate alias-to-path claims."
            if missing_registered_paths or duplicate_claimed_paths or unregistered_active_docs or registration_drift
            else "Artifact claims align for registered paths; monitor unregistered active docs as needed.",
            "details": {
                "missing_registered_paths": sorted(missing_registered_paths),
                "duplicate_claimed_paths": duplicate_claimed_paths,
                "unregistered_active_docs": unregistered_active_docs,
                "registration_drift": registration_drift,
            },
        },
        "ownership": {
            "status": "needs_attention" if ownership_counts["cross_project"] > 0 else "ok",
            "truth_label": "derived_signal",
            "summary": (
                f"Warning ownership distribution - active_project: {ownership_counts['active_project']}, "
                f"cross_project: {ownership_counts['cross_project']}, unscoped: {ownership_counts['unscoped']}."
            ),
            "next_safe_action": "Rehome cross-project docs before mutation actions."
            if ownership_counts["cross_project"] > 0
            else "No cross-project ownership drift in warning ownership signals.",
        },
        "dev_plan_roots": {
            "status": "compatibility_present" if dual_root_inventory["legacy"]["exists"] else "ok",
            "truth_label": "direct_artifact",
            "summary": "Dual-root inventory distinguishes canonical .scribe/docs/dev_plans from legacy docs/dev_plans before any apply path.",
            "next_safe_action": "No active migration action required; keep using canonical .scribe/docs/dev_plans for new writes and treat legacy docs/dev_plans as read-only compatibility inventory unless explicitly migrating.",
            "details": dual_root_inventory,
        },
    }

    response["organization_digest"] = {
        "truth_model": {
            "direct_artifact": "Derived from concrete files and analyzer warning payloads.",
            "derived_signal": "Inferred grouping/ownership summaries from direct artifact observations.",
        },
        "quality_warning_digest": digest_items,
        "ownership_summary": ownership_counts,
        "status_sections": status_sections,
        "derived_signals": [
            {
                "signal": "cross_project_quality_warnings_present",
                "active": ownership_counts["cross_project"] > 0,
                "truth_label": "derived_signal",
                "next_safe_action": "Run manage_docs(action='rehome_doc', ...) for mis-owned docs before mutation."
                if ownership_counts["cross_project"] > 0
                else "No cross-project warning ownership drift detected.",
            },
            {
                "signal": "readiness_blockers_present",
                "active": bool(managed_doc_quality.get("readiness_blocker_count", 0)) if isinstance(managed_doc_quality, dict) else False,
                "truth_label": "derived_signal",
                "next_safe_action": "Address blocking quality warnings before marking phase gates ready."
                if isinstance(managed_doc_quality, dict) and managed_doc_quality.get("readiness_blocker_count", 0)
                else "No blocking quality warnings detected.",
            },
            {
                "signal": "release_changelog_coverage_missing",
                "active": bool((managed_doc_quality.get("readiness_blocker_counts_by_code") or {}).get("SCF_CHANGELOG_CURRENT_VERSION_MISSING", 0))
                if isinstance(managed_doc_quality, dict)
                else False,
                "truth_label": "derived_signal",
                "next_safe_action": "Add or update an accepted managed CHANGELOG entry for the active pyproject version, then run preview_reconciliation and apply_global_changelog before release closeout."
                if isinstance(managed_doc_quality, dict)
                and bool((managed_doc_quality.get("readiness_blocker_counts_by_code") or {}).get("SCF_CHANGELOG_CURRENT_VERSION_MISSING", 0))
                else "No missing current-version managed CHANGELOG coverage warning detected.",
            },
        ],
    }
    return helper.apply_context_payload(response, context)


async def _handle_quality_check(
    *,
    active_project: Dict[str, Any],
    doc_name: Optional[str],
    doc_category: Optional[str],
    metadata: Optional[Dict[str, Any]],
    project_registry: Any,
    append_entry: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
    server_module: Any,
    execution_context: Any,
    agent_id: str,
    helper: LoggingToolMixin,
    context: LoggingContext,
) -> Dict[str, Any]:
    def _resolve_explicit_markdown_path(raw_value: str) -> Optional[Path]:
        candidate_raw = str(raw_value or "").strip()
        if not candidate_raw:
            return None
        if "/" not in candidate_raw and "\\" not in candidate_raw:
            return None
        candidate = Path(candidate_raw).expanduser()
        if not candidate.is_absolute():
            project_root_raw = str(active_project.get("root") or "").strip()
            if not project_root_raw:
                return None
            candidate = (Path(project_root_raw).expanduser() / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if candidate.suffix.lower() != ".md":
            return None
        if not candidate.exists():
            return None
        project_root = Path(str(active_project.get("root") or "")).expanduser().resolve()
        if project_root not in candidate.parents and candidate != project_root:
            return None
        return candidate

    def _coerce_bool(value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    def _coerce_positive_int(value: Any, *, default: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if parsed < 1:
            return default
        return min(parsed, maximum)

    def _metadata_quality_cfg() -> Dict[str, Any]:
        quality_metadata = metadata or {}
        quality_cfg = quality_metadata.get("quality") if isinstance(quality_metadata.get("quality"), dict) else {}
        return quality_cfg

    def _quality_bulk_options(requested_value: str) -> Optional[Dict[str, Any]]:
        quality_metadata = metadata if isinstance(metadata, dict) else {}
        quality_cfg = _metadata_quality_cfg()
        bulk_raw: Any = quality_cfg.get("bulk")
        if bulk_raw is None:
            bulk_raw = quality_metadata.get("bulk_quality_check")
        if bulk_raw is None:
            bulk_raw = quality_metadata.get("bulk")

        requested_normalized = str(requested_value or "").strip().lower()
        if bulk_raw is None and requested_normalized in {"*", "all", "atlas", "managed_docs", "project"}:
            bulk_raw = True
        if bulk_raw is None or bulk_raw is False:
            return None

        bulk_cfg = bulk_raw if isinstance(bulk_raw, dict) else {}
        doc_names_raw = (
            bulk_cfg.get("doc_names")
            or bulk_cfg.get("docs")
            or bulk_cfg.get("documents")
            or bulk_cfg.get("targets")
        )
        doc_names: list[str] = []
        if isinstance(doc_names_raw, str):
            doc_names = [part.strip() for part in doc_names_raw.split(",") if part.strip()]
        elif isinstance(doc_names_raw, list):
            doc_names = [str(item).strip() for item in doc_names_raw if str(item).strip()]

        return {
            "scope": str(bulk_cfg.get("scope") or ("doc_names" if doc_names else "project")),
            "doc_names": doc_names,
            "include_clean": _coerce_bool(bulk_cfg.get("include_clean"), default=True),
            "include_warnings": _coerce_bool(bulk_cfg.get("include_warnings"), default=True),
            "max_agent_actions": _coerce_positive_int(bulk_cfg.get("max_agent_actions"), default=10, maximum=50),
            "max_docs": _coerce_positive_int(bulk_cfg.get("max_docs"), default=250, maximum=500),
        }

    def _build_document_quality_payload(
        *,
        target_name: str,
        path: Path,
        mode_info: Dict[str, Any],
        runtime_warnings: list[str],
    ) -> Dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        quality_metadata = metadata or {}
        quality_cfg = _metadata_quality_cfg()
        warnings = collect_managed_doc_quality_warnings(
            text=text,
            metadata={**quality_metadata, "quality": {**quality_cfg, "mode": mode_info["mode"]}},
            doc_name=target_name,
            path=path,
            project=active_project,
        )
        warnings = enrich_quality_warning_context(normalize_warnings(warnings), text=text)
        summary = summarize_quality_warnings(warnings)
        warning_groups = group_quality_warnings(warnings)
        readiness_blockers = [w for w in warnings if bool(w.get("blocking"))]
        status = "pass" if not warnings else ("fail" if readiness_blockers else "warn")
        return {
            "ok": True,
            "quality_status": status,
            "scope": {"type": "document", "doc_name": target_name, "path": str(path)},
            "summary": {
                **summary,
                "config_source": "metadata.quality" if isinstance((metadata or {}).get("quality"), dict) else "defaults",
                "mode": mode_info["mode"],
                "schema_version": SCHEMA_VERSION,
                "category": "quality_check",
                "gate_scope": "manage_docs",
                "scope_kind": "document",
                "release_trigger": mode_info["release_trigger"],
                "release_trigger_source": mode_info["trigger_source"],
                "release_triggers": mode_info.get("release_triggers", []),
            },
            "warnings": warnings,
            "warning_groups": warning_groups,
            "agent_actions": build_quality_agent_actions(warning_groups),
            "runtime_warnings": runtime_warnings,
            "readiness_blockers": readiness_blockers,
            "next_actions": [w.get("suggested_repair") for w in readiness_blockers[:3] if isinstance(w.get("suggested_repair"), str)],
        }

    def _select_bulk_quality_targets(options: Dict[str, Any], runtime_warnings: list[str]) -> list[Dict[str, Any]]:
        docs = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
        selected: list[Dict[str, Any]] = []
        seen_paths: set[str] = set()
        configured_log_paths = configured_log_quality_exclusion_paths(active_project)
        explicit_doc_names = list(options.get("doc_names") or [])

        if explicit_doc_names:
            iterable = [(requested, docs.get(resolve_registered_doc_key(active_project, requested) or _canonical_doc_key(requested))) for requested in explicit_doc_names]
        else:
            iterable = list(docs.items())

        for raw_name, raw_path in iterable:
            requested_name = str(raw_name or "").strip()
            resolved_path = _resolve_explicit_markdown_path(requested_name)
            if resolved_path is not None:
                target_name = _canonical_doc_key(resolved_path.stem)
                path = resolved_path
            else:
                target_name = resolve_registered_doc_key(active_project, requested_name) or _canonical_doc_key(requested_name)
                if not isinstance(raw_path, str) or not raw_path.strip():
                    runtime_warnings.append(f"bulk quality_check skipped unresolved document '{requested_name}'.")
                    continue
                path = Path(raw_path).expanduser().resolve()

            if path.suffix.lower() != ".md" or not path.exists():
                runtime_warnings.append(f"bulk quality_check skipped missing or non-markdown document '{requested_name}' at '{path}'.")
                continue
            if not explicit_doc_names and not is_managed_doc_quality_target(
                target_name,
                path,
                configured_log_paths=configured_log_paths,
            ):
                continue
            key = str(path)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            selected.append({"doc_name": target_name, "path": path})

        max_docs = int(options.get("max_docs") or 250)
        if len(selected) > max_docs:
            runtime_warnings.append(
                f"bulk quality_check truncated {len(selected)} candidate documents to max_docs={max_docs}."
            )
            selected = selected[:max_docs]
        return selected

    def _build_bulk_quality_response(options: Dict[str, Any], runtime_warnings: list[str]) -> Dict[str, Any]:
        mode_info = resolve_quality_mode(metadata=metadata, project_root=Path(str(active_project.get("root") or "")).resolve())
        targets = _select_bulk_quality_targets(options, runtime_warnings)
        include_clean = bool(options.get("include_clean"))
        include_warnings = bool(options.get("include_warnings"))
        flat_warnings: list[Dict[str, Any]] = []
        document_results: list[Dict[str, Any]] = []

        for target in targets:
            doc_runtime_warnings: list[str] = []
            document_payload = _build_document_quality_payload(
                target_name=str(target["doc_name"]),
                path=target["path"],
                mode_info=mode_info,
                runtime_warnings=doc_runtime_warnings,
            )
            if doc_runtime_warnings:
                runtime_warnings.extend(doc_runtime_warnings)
            warnings_with_doc = [
                {**warning, "doc_name": document_payload["scope"]["doc_name"], "path": document_payload["scope"]["path"]}
                for warning in document_payload["warnings"]
            ]
            flat_warnings.extend(warnings_with_doc)
            if include_clean or warnings_with_doc:
                document_results.append(
                    {
                        "doc_name": document_payload["scope"]["doc_name"],
                        "path": document_payload["scope"]["path"],
                        "quality_status": document_payload["quality_status"],
                        "summary": document_payload["summary"],
                        "warnings": warnings_with_doc if include_warnings else [],
                        "warning_groups": document_payload["warning_groups"],
                        "agent_actions": document_payload["agent_actions"],
                        "readiness_blockers": [
                            {**warning, "doc_name": document_payload["scope"]["doc_name"], "path": document_payload["scope"]["path"]}
                            for warning in document_payload["readiness_blockers"]
                        ]
                        if include_warnings
                        else [],
                    }
                )

        bulk_summary = summarize_quality_warnings(flat_warnings)
        readiness_blockers = [warning for warning in flat_warnings if bool(warning.get("blocking"))]
        warning_groups = group_quality_warnings(flat_warnings)
        max_agent_actions = int(options.get("max_agent_actions") or 10)
        agent_actions = build_quality_agent_actions(warning_groups, max_items=max_agent_actions)
        documents_with_warnings = sum(1 for document in document_results if int((document.get("summary") or {}).get("total_warnings", 0) or 0) > 0)
        documents_with_blockers = sum(
            1 for document in document_results if int((document.get("summary") or {}).get("readiness_blocker_count", 0) or 0) > 0
        )
        status = "pass" if not flat_warnings else ("fail" if readiness_blockers else "warn")
        response = {
            "ok": True,
            "quality_status": status,
            "scope": {
                "type": "bulk",
                "project": active_project.get("name"),
                "mode": options.get("scope"),
                "requested_count": len(options.get("doc_names") or targets),
                "checked_count": len(targets),
                "included_document_count": len(document_results),
                "include_clean": include_clean,
                "include_warnings": include_warnings,
            },
            "summary": {
                **bulk_summary,
                "config_source": "metadata.quality" if isinstance((metadata or {}).get("quality"), dict) else "defaults",
                "mode": mode_info["mode"],
                "schema_version": SCHEMA_VERSION,
                "category": "quality_check",
                "gate_scope": "manage_docs",
                "scope_kind": "bulk",
                "release_trigger": mode_info["release_trigger"],
                "release_trigger_source": mode_info["trigger_source"],
                "release_triggers": mode_info.get("release_triggers", []),
                "checked_documents": len(targets),
                "included_documents": len(document_results),
                "documents_with_warnings": documents_with_warnings,
                "documents_with_blockers": documents_with_blockers,
                "max_agent_actions": max_agent_actions,
            },
            "documents": document_results,
            "warnings": flat_warnings if include_warnings else [],
            "warning_groups": warning_groups,
            "agent_actions": agent_actions,
            "runtime_warnings": runtime_warnings,
            "readiness_blockers": readiness_blockers if include_warnings else [],
            "next_actions": [
                warning.get("suggested_repair")
                for warning in readiness_blockers[:3]
                if isinstance(warning.get("suggested_repair"), str)
            ],
        }
        return response

    docs = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
    requested_name = str(doc_name or "").strip()
    runtime_warnings: list[str] = []
    bulk_options = _quality_bulk_options(requested_name)
    if bulk_options is not None:
        return helper.apply_context_payload(_build_bulk_quality_response(bulk_options, runtime_warnings), context)

    explicit_md_path = _resolve_explicit_markdown_path(requested_name)
    if explicit_md_path is not None:
        path_str = str(explicit_md_path)
        target_name = _canonical_doc_key(explicit_md_path.stem)
    else:
        target_name = resolve_registered_doc_key(active_project, requested_name) if requested_name else ""
        path_str = docs.get(target_name) if target_name else None
    requested_category = str(doc_category or "").strip().lower()
    requested_stem = requested_name[:-3] if requested_name.lower().endswith(".md") else requested_name
    research_like = bool(requested_name) and (
        requested_category == "research" or requested_stem.upper().startswith("RESEARCH_")
    )
    # For research requests, canonical research path must be authoritative before generic docs_dir fallback.
    if (not isinstance(path_str, str) or not Path(path_str).exists()) and requested_name and research_like:
        resolved_research = utils_shared.resolve_custom_doc_path(
            project=active_project,
            doc_category="research",
            doc_name=requested_stem,
        )
        if resolved_research and resolved_research.exists():
            candidate_key = _canonical_doc_key(requested_stem)
            try:
                await register_document_path(
                    active_project,
                    candidate_key,
                    resolved_research,
                    server_module=server_module,
                    project_registry=project_registry,
                    append_entry=append_entry,
                    logger=logger,
                    execution_context=execution_context,
                    agent_id=agent_id,
                )
                docs = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
                target_name = resolve_registered_doc_key(active_project, requested_name) or candidate_key
                path_str = docs.get(target_name) or str(resolved_research)
            except Exception as exc:
                logger.warning("quality_check research pre-bind failed for '%s': %s", requested_name, exc)
                target_name = candidate_key
                path_str = str(resolved_research)
                runtime_warnings.append(
                    f"quality_check used discovered research document '{requested_name}' at "
                    f"'{resolved_research}' after registry pre-bind failed: {exc}"
                )
    if (not isinstance(path_str, str) or not Path(path_str).exists()) and requested_name:
        candidate_key = _canonical_doc_key(requested_name)
        docs_dir_raw = str(active_project.get("docs_dir") or "").strip()
        docs_dir: Optional[Path] = Path(docs_dir_raw).expanduser() if docs_dir_raw else None
        if docs_dir is None:
            progress_log = str(
                active_project.get("progress_log")
                or (docs.get("progress_log") if isinstance(docs, dict) else "")
                or ""
            ).strip()
            if progress_log:
                docs_dir = Path(progress_log).expanduser().resolve().parent
        candidates: list[Path] = []
        if docs_dir:
            if requested_name.lower().endswith(".md"):
                candidates.append((docs_dir / requested_name).resolve())
            else:
                candidates.append((docs_dir / f"{requested_name}.md").resolve())
            candidates.append((docs_dir / f"{candidate_key}.md").resolve())
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if not candidate.exists():
                continue
            try:
                await register_document_path(
                    active_project,
                    candidate_key,
                    candidate,
                    server_module=server_module,
                    project_registry=project_registry,
                    append_entry=append_entry,
                    logger=logger,
                    execution_context=execution_context,
                    agent_id=agent_id,
                )
                docs = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
                target_name = resolve_registered_doc_key(active_project, requested_name) or candidate_key
                path_str = docs.get(target_name)
            except Exception as exc:
                logger.warning("quality_check auto-registration failed for '%s': %s", requested_name, exc)
                target_name = candidate_key
                path_str = str(candidate)
                runtime_warnings.append(
                    f"quality_check used discovered unregistered document '{requested_name}' at '{candidate}' "
                    f"after registry auto-registration failed: {exc}"
                )
            break
    # Recovery lane for stale/missing registry after research doc rename:
    # allow exact on-disk resolution only for research family, then optionally re-bind.
    if (not isinstance(path_str, str) or not Path(path_str).exists()) and requested_name:
        if research_like:
            resolved_research = utils_shared.resolve_custom_doc_path(
                project=active_project,
                doc_category="research",
                doc_name=requested_stem,
            )
            if resolved_research and resolved_research.exists():
                candidate_key = _canonical_doc_key(requested_stem)
                try:
                    await register_document_path(
                        active_project,
                        candidate_key,
                        resolved_research,
                        server_module=server_module,
                        project_registry=project_registry,
                        append_entry=append_entry,
                        logger=logger,
                        execution_context=execution_context,
                        agent_id=agent_id,
                    )
                    docs = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
                    target_name = resolve_registered_doc_key(active_project, requested_name) or candidate_key
                    path_str = docs.get(target_name) or str(resolved_research)
                except Exception as exc:
                    logger.warning("quality_check research re-bind failed for '%s': %s", requested_name, exc)
                    target_name = candidate_key
                    path_str = str(resolved_research)
                    runtime_warnings.append(
                        f"quality_check used discovered research document '{requested_name}' at "
                        f"'{resolved_research}' after registry re-bind failed: {exc}"
                    )
    if not isinstance(path_str, str) or not Path(path_str).exists():
        explicit_md_path = _resolve_explicit_markdown_path(requested_name)
        if explicit_md_path is not None:
            path_str = str(explicit_md_path)
            target_name = _canonical_doc_key(explicit_md_path.stem)
    if not isinstance(path_str, str) or not Path(path_str).exists():
        return helper.apply_context_payload(
            helper.error_response(
                "quality_check requires a valid doc_name/doc in the active project registry or a valid markdown path under the project root."
            ),
            context,
        )
    mode_info = resolve_quality_mode(metadata=metadata, project_root=Path(str(active_project.get("root") or "")).resolve())
    response = _build_document_quality_payload(
        target_name=target_name,
        path=Path(path_str),
        mode_info=mode_info,
        runtime_warnings=runtime_warnings,
    )
    return helper.apply_context_payload(response, context)


async def _handle_quality_handoff_check(*, active_project: Dict[str, Any], agent_id: str, helper: LoggingToolMixin, context: LoggingContext) -> Dict[str, Any]:
    blocker_result = collect_managed_doc_quality_blockers(active_project)
    blocked = bool(blocker_result.get("blocked"))
    blocker_docs = list(blocker_result.get("blocker_docs") or [])
    quality_state = blocker_result.get("quality_state") if isinstance(blocker_result.get("quality_state"), dict) else {}
    handoff_actions = [
        {
            "rank": index,
            "doc_name": document.get("doc_name"),
            "path": document.get("path"),
            "blocker_codes": list(document.get("blocker_codes") or []),
            "command_hint": f"manage_docs(action='quality_check', doc_name='{document.get('doc_name')}', dry_run=True)",
            "suggested_next_step": "Run quality_check for this document, then resolve the listed blocker codes before handoff.",
        }
        for index, document in enumerate(blocker_docs[:5], start=1)
        if isinstance(document, dict)
    ]
    if not handoff_actions:
        handoff_actions = [
            {
                "rank": 1,
                "status": "clear",
                "suggested_next_step": "Managed-doc quality handoff is clear for current project scope.",
            }
        ]
    response = {
        "ok": not blocked,
        "action": "quality_handoff_check",
        "agent": agent_id,
        "project": active_project.get("name"),
        "blocked": blocked,
        "blocker_docs": blocker_docs,
        "total_blocker_count": int(blocker_result.get("total_blocker_count", 0)),
        "quality_summary": {
            "status": quality_state.get("status", "blocked" if blocked else "pass"),
            "total_warning_count": int(quality_state.get("total_warning_count", 0) or 0),
            "readiness_blocker_count": int(quality_state.get("readiness_blocker_count", 0) or 0),
            "warning_counts_by_code": dict(quality_state.get("warning_counts_by_code") or {}),
            "readiness_blocker_counts_by_code": dict(quality_state.get("readiness_blocker_counts_by_code") or {}),
            "frontmatter_mismatch_count": int(quality_state.get("frontmatter_mismatch_count", 0) or 0),
            "stale_research_index_count": int(quality_state.get("stale_research_index_count", 0) or 0),
        },
        "handoff_actions": handoff_actions,
    }
    return helper.apply_context_payload(response, context)


async def _handle_rehome_doc(
    *,
    active_project: Dict[str, Any],
    doc_name: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    helper: LoggingToolMixin,
    context: LoggingContext,
    execution_context: Any,
    server_module: Any,
    agent_id: str,
) -> Dict[str, Any]:
    metadata_mapping = metadata if isinstance(metadata, dict) else {}
    requested_target_dir = str(metadata_mapping.get("target_dir") or "").strip()
    target_project_name = str(metadata_mapping.get("target_project") or "").strip()
    if not target_project_name:
        return helper.apply_context_payload(
            helper.error_response("rehome_doc requires metadata.target_project."),
            context,
        )
    if not doc_name:
        return helper.apply_context_payload(
            helper.error_response("rehome_doc requires doc/doc_name."),
            context,
        )

    project_root = Path(str(active_project.get("root") or "")).expanduser().resolve()
    source_docs = dict(active_project.get("docs") or {})
    source_doc_key = resolve_registered_doc_key(active_project, doc_name)
    source_path_str = source_docs.get(source_doc_key)
    source_registered = bool(source_path_str)
    if not source_path_str:
        raw_source_path = metadata_mapping.get("source_path")
        if not raw_source_path and _looks_like_path(str(doc_name)):
            raw_source_path = doc_name
        if not raw_source_path:
            return helper.apply_context_payload(
                helper.error_response(
                    f"rehome_doc requires a registered source document or metadata.source_path; '{doc_name}' is not registered.",
                ),
                context,
            )
        source_candidate = Path(str(raw_source_path)).expanduser()
        if not source_candidate.is_absolute():
            source_candidate = project_root / source_candidate
        source_path = source_candidate.resolve()
        try:
            source_path.relative_to(project_root)
        except ValueError:
            return helper.apply_context_payload(
                helper.error_response(
                    "rehome_doc source_path must stay within the active project's root.",
                    extra={"source_path": str(source_path), "project_root": str(project_root)},
                ),
                context,
            )
        if not source_path.exists():
            return helper.apply_context_payload(
                helper.error_response(
                    "rehome_doc source_path does not exist.",
                    extra={"source_path": str(source_path)},
                ),
                context,
            )
        source_path_str = str(source_path)
        source_doc_key = str(metadata_mapping.get("target_doc_name") or source_path.stem).strip() or source_path.stem

    target_project = await _load_project_record(
        project_name=target_project_name,
        server_module=server_module,
    )
    if not target_project:
        return helper.apply_context_payload(
            helper.error_response(
                f"Target project '{target_project_name}' was not found.",
            ),
            context,
        )

    source_docs_dir = Path(str(active_project.get("docs_dir") or "")).expanduser().resolve()
    raw_target_docs_dir = str(target_project.get("docs_dir") or "").strip()
    if raw_target_docs_dir:
        target_docs_dir = Path(raw_target_docs_dir).expanduser().resolve()
    else:
        target_progress = Path(str(target_project.get("progress_log") or "")).expanduser()
        target_docs_dir = target_progress.parent.resolve()
    target_project_root = Path(str(target_project.get("root") or project_root)).expanduser().resolve()
    source_path = Path(source_path_str).expanduser().resolve()

    try:
        source_path.relative_to(project_root)
    except ValueError:
        return helper.apply_context_payload(
            helper.error_response(
                "rehome_doc source document must stay within the active project's root.",
                extra={"path": str(source_path), "project_root": str(project_root)},
            ),
            context,
        )

    target_doc_key = str(metadata_mapping.get("target_doc_name") or source_doc_key).strip() or source_doc_key
    try:
        relative_path = source_path.relative_to(source_docs_dir)
    except ValueError:
        relative_path = _default_rehome_relative_path(source_path, project_root)
    if ".scribe" in relative_path.parts:
        relative_path = _default_rehome_relative_path(source_path, project_root)

    target_relative_path = metadata_mapping.get("target_relative_path")
    try:
        if isinstance(target_relative_path, str) and target_relative_path.strip():
            relative_path = _coerce_rehome_relative_path(
                Path(target_relative_path.strip()),
                target_docs_dir=target_docs_dir,
                target_project_root=target_project_root,
            )
        elif requested_target_dir:
            requested_dir = _coerce_rehome_relative_path(
                Path(requested_target_dir),
                target_docs_dir=target_docs_dir,
                target_project_root=target_project_root,
            )
            relative_path = requested_dir / source_path.name
        else:
            relative_path = _coerce_rehome_relative_path(
                relative_path,
                target_docs_dir=target_docs_dir,
                target_project_root=target_project_root,
            )
    except ValueError as exc:
        return helper.apply_context_payload(
            helper.error_response(
                str(exc),
                extra={"target_docs_dir": str(target_docs_dir)},
            ),
            context,
        )

    if ".scribe" in relative_path.parts:
        return helper.apply_context_payload(
            helper.error_response(
                "rehome_doc target paths must be docs-relative; nested .scribe paths are not allowed.",
                extra={"target_relative_path": str(relative_path), "target_docs_dir": str(target_docs_dir)},
            ),
            context,
        )

    target_path = (target_docs_dir / relative_path).resolve()
    overwrite = bool(metadata_mapping.get("overwrite"))
    raw_move_mode = metadata_mapping.get("move", True)
    move_mode = bool(raw_move_mode) if not isinstance(raw_move_mode, str) else raw_move_mode.strip().lower() in {"1", "true", "yes", "on"}

    try:
        target_path.relative_to(target_docs_dir)
    except ValueError:
        return helper.apply_context_payload(
            helper.error_response(
                "rehome_doc target path must stay within the target project's docs_dir.",
                extra={"target_path": str(target_path), "target_docs_dir": str(target_docs_dir)},
            ),
            context,
        )

    if target_path.exists() and not overwrite:
        return helper.apply_context_payload(
            helper.error_response(
                "rehome_doc target already exists (set metadata.overwrite=true to replace).",
                extra={"target_path": str(target_path)},
            ),
            context,
        )

    removed_doc_keys = [
        key for key, value in source_docs.items()
        if Path(str(value)).expanduser().resolve() == source_path
    ]
    target_docs = dict(target_project.get("docs") or {})
    target_docs[target_doc_key] = str(target_path)

    checkpoint_file_location = {
        "ok": True,
        "source_path": str(source_path),
        "target_path": str(target_path),
        "target_path_in_target_docs_dir": True,
        "dry_run": dry_run,
    }
    checkpoint_registry_mapping = {
        "source_doc_keys": removed_doc_keys,
        "target_doc_key": target_doc_key,
        "source_registered": source_registered,
        "source_mapping_removed": False,
        "target_mapping_written": False,
    }
    checkpoint_quality_binding = {
        "attempted": False,
        "ok": None,
        "project": target_project_name,
        "doc": target_doc_key,
        "summary": None,
        "error": None,
    }
    checkpoint_readiness = {
        "attempted": False,
        "ok": None,
        "status": "deferred",
        "readiness_blocker_count": None,
        "total_warnings": None,
        "quality_status": None,
        "error": None,
    }
    checkpoint_index_freshness = {
        "source_research_index_refresh": "not_applicable",
        "target_research_index_refresh": "not_applicable",
        "index_freshness_reported_separately": True,
    }

    if not dry_run:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if move_mode:
            if overwrite and target_path.exists():
                target_path.unlink()
            shutil.move(str(source_path), str(target_path))
        else:
            shutil.copy2(source_path, target_path)

        for key in removed_doc_keys:
            source_docs.pop(key, None)
        checkpoint_registry_mapping["source_mapping_removed"] = (
            not source_registered
            or all(key not in source_docs for key in removed_doc_keys)
        )
        active_project["docs"] = source_docs
        target_project["docs"] = target_docs
        checkpoint_registry_mapping["target_mapping_written"] = target_docs.get(target_doc_key) == str(target_path)

        backend = getattr(server_module, "storage_backend", None)
        if backend and hasattr(backend, "update_project_docs"):
            await backend.update_project_docs(
                active_project.get("name"),
                json.dumps(source_docs),
                repo_root=active_project.get("root"),
            )
            await backend.update_project_docs(
                target_project_name,
                json.dumps(target_docs),
                repo_root=target_project.get("root"),
            )

        state_refresh_warnings: list[str] = []
        state_manager = getattr(server_module, "state_manager", None)
        if state_manager and hasattr(state_manager, "update_project_metadata"):
            for project_name, project_payload in (
                (active_project.get("name"), active_project),
                (target_project_name, target_project),
            ):
                if not project_name:
                    continue
                try:
                    await state_manager.update_project_metadata(
                        str(project_name),
                        {
                            "root": project_payload.get("root"),
                            "docs_dir": project_payload.get("docs_dir"),
                            "progress_log": project_payload.get("progress_log"),
                            "docs": project_payload.get("docs") or {},
                            "repo_id": project_payload.get("repo_id"),
                            "project_key": project_payload.get("project_key"),
                        },
                    )
                except Exception as exc:
                    state_refresh_warnings.append(
                        f"Rehome persisted docs mapping for '{project_name}', but state cache refresh failed: {exc}"
                    )

        authoritative_scope = resolve_authoritative_write_scope(
            context=execution_context,
            agent_session_id=None,
        )
        authoritative_session_id = authoritative_scope.get("authoritative_session_id")
        if state_manager and hasattr(state_manager, "set_current_project") and authoritative_session_id:
            await state_manager.set_current_project(
                active_project.get("name"),
                active_project,
                agent_id=agent_id,
                session_id=authoritative_session_id,
                resolved_scope=authoritative_scope.get("resolved_scope"),
                mirror_global=False,
            )

        # Keep research indexes truthful on move/copy flows without introducing a second writer.
        try:
            source_research_dir = source_docs_dir / "research"
            if source_research_dir.exists() and source_path.is_relative_to(source_research_dir):
                await special_indexes_shared.update_research_index(source_research_dir, agent_id)
                checkpoint_index_freshness["source_research_index_refresh"] = "updated"
        except Exception:
            checkpoint_index_freshness["source_research_index_refresh"] = "refresh_failed"
        try:
            target_research_dir = target_docs_dir / "research"
            if target_research_dir.exists() and target_path.is_relative_to(target_research_dir):
                await special_indexes_shared.update_research_index(target_research_dir, agent_id)
                checkpoint_index_freshness["target_research_index_refresh"] = "updated"
        except Exception:
            checkpoint_index_freshness["target_research_index_refresh"] = "refresh_failed"

        checkpoint_file_location["ok"] = target_path.exists() and (not move_mode or not source_path.exists())
        checkpoint_file_location["source_exists_after"] = source_path.exists()
        checkpoint_file_location["target_exists_after"] = target_path.exists()

        try:
            target_text = target_path.read_text(encoding="utf-8")
            quality_warnings = collect_managed_doc_quality_warnings(
                text=target_text,
                metadata={},
                doc_name=target_doc_key,
                path=target_path,
                project=target_project,
            )
            warning_summary = summarize_quality_warnings(quality_warnings)
            readiness_blocker_count = int(warning_summary.get("readiness_blocker_count") or 0)
            total_warnings = int(warning_summary.get("total") or 0)
            quality_status = "pass" if total_warnings == 0 else ("fail" if readiness_blocker_count > 0 else "warn")

            checkpoint_quality_binding["attempted"] = True
            checkpoint_quality_binding["ok"] = readiness_blocker_count == 0
            checkpoint_quality_binding["summary"] = {
                "quality_status": quality_status,
                "total_warnings": total_warnings,
                "readiness_blocker_count": readiness_blocker_count,
            }

            checkpoint_readiness["attempted"] = True
            checkpoint_readiness["ok"] = readiness_blocker_count == 0
            checkpoint_readiness["status"] = quality_status
            checkpoint_readiness["readiness_blocker_count"] = readiness_blocker_count
            checkpoint_readiness["total_warnings"] = total_warnings
            checkpoint_readiness["quality_status"] = quality_status
        except Exception as exc:
            error_text = str(exc)
            checkpoint_quality_binding["attempted"] = True
            checkpoint_quality_binding["ok"] = False
            checkpoint_quality_binding["error"] = error_text

            checkpoint_readiness["attempted"] = True
            checkpoint_readiness["ok"] = False
            checkpoint_readiness["status"] = "error"
            checkpoint_readiness["error"] = error_text
    else:
        checkpoint_quality_binding["ok"] = "deferred_dry_run"
        checkpoint_quality_binding["summary"] = {"quality_status": "deferred_dry_run"}
        checkpoint_readiness["ok"] = "deferred_dry_run"
        checkpoint_readiness["status"] = "deferred_dry_run"
        if source_path.is_relative_to(source_docs_dir / "research"):
            checkpoint_index_freshness["source_research_index_refresh"] = "would_refresh"
        if target_path.is_relative_to(target_docs_dir / "research"):
            checkpoint_index_freshness["target_research_index_refresh"] = "would_refresh"

    response = {
        "ok": True,
        "action": "rehome_doc",
        "requested_doc_name": doc_name,
        "canonical_doc_name": source_doc_key,
        "final_path": str(target_path),
        "source_project": active_project.get("name"),
        "target_project": target_project_name,
        "source_path": str(source_path),
        "target_path": str(target_path),
        "moved": move_mode,
        "dry_run": dry_run,
        "removed_doc_keys": removed_doc_keys if move_mode else [],
        "target_doc_key": target_doc_key,
        "rehome_verification": {
            "file_location": checkpoint_file_location,
            "registry_mapping": checkpoint_registry_mapping,
            "quality_check_binding": checkpoint_quality_binding,
            "readiness": checkpoint_readiness,
            "index_freshness": checkpoint_index_freshness,
        },
    }
    if not dry_run and "state_refresh_warnings" in locals() and state_refresh_warnings:
        response["warnings"] = state_refresh_warnings
    return helper.apply_context_payload(response, context)


def build_create_intent_payload(
    *,
    result: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    requested_doc_name: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Build additive create-intent guidance for caller-facing clarity."""
    if not isinstance(result, dict) or not result.get("ok"):
        return None

    metadata_mapping = metadata if isinstance(metadata, dict) else {}
    doc_type = str(metadata_mapping.get("doc_type", "custom") or "custom").strip().lower()
    canonical_doc_name = (
        metadata_mapping.get("register_as")
        or metadata_mapping.get("doc_name")
        or result.get("doc_name")
        or requested_doc_name
    )
    canonical_doc_name = str(canonical_doc_name).strip() if canonical_doc_name else ""

    section_source = str(result.get("section_source") or "").strip().lower()
    first_write_action = "replace_section"
    target_for_guidance = canonical_doc_name or requested_doc_name or "doc_name"

    if bool(metadata_mapping.get("register_existing")):
        first_write_action = "apply_patch"
        follow_up = (
            "create registered an existing file without writing new content. "
            "For the first mutation, call manage_docs(action='apply_patch', "
            f"doc='{target_for_guidance}', ...) so edits work on non-scaffold content."
        )
        return {
            "kind": "empty_registered_doc",
            "canonical_doc_name": canonical_doc_name or None,
            "first_write_action": first_write_action,
            "next_step_guidance": follow_up,
        }

    if doc_type in _SPECIAL_DOC_TYPES or bool(result.get("document_type")):
        # Special docs are contentful scaffolds with anchored placeholder
        # sections: populate them with replace_section (same as governed
        # scaffolds); apply_patch is for surgical edits to existing content.
        follow_up = (
            "create produced a contentful special document. Populate its anchored "
            f"sections with manage_docs(action='replace_section', doc='{target_for_guidance}', ...); "
            "for surgical edits to existing content switch to action='apply_patch'."
        )
        return {
            "kind": "contentful_special_doc",
            "canonical_doc_name": canonical_doc_name or None,
            "first_write_action": first_write_action,
            "next_step_guidance": follow_up,
        }

    if section_source == "headings":
        first_write_action = "apply_patch"
        follow_up = (
            "create produced a governed document with heading-derived section inventory. "
            "Those ids are preview-only until explicit <!-- ID: ... --> anchors exist. "
            "For the first mutation, use manage_docs(action='apply_patch', ...) or "
            "manage_docs(action='replace_range', ...) for explicit control, or add explicit "
            f"anchors before using manage_docs(action='replace_section', doc='{target_for_guidance}', ...)."
        )
    else:
        follow_up = (
            "create scaffolds a governed document. Next, call "
            f"manage_docs(action='replace_section', doc='{target_for_guidance}', ...) "
            "to add or replace section content anchored by <!-- ID: ... --> markers. "
            "If section boundaries drift or anchors/headings become ambiguous, switch to "
            "manage_docs(action='replace_range', ...) or action='apply_patch' for explicit control."
        )
    return {
        "kind": "governed_scaffold_doc",
        "canonical_doc_name": canonical_doc_name or None,
        "first_write_action": first_write_action,
        "next_step_guidance": follow_up,
    }


async def get_or_create_storage_project(backend: Any, project: Dict[str, Any], server_module: Any) -> Any:
    """Fetch or create the backing storage record for a project."""
    timeout = server_module.settings.storage_timeout_seconds
    async with asyncio.timeout(timeout):
        storage_record = await backend.fetch_project(
            project["name"],
            repo_root=project.get("root"),
        )
    if not storage_record:
        async with asyncio.timeout(timeout):
            storage_record = await backend.upsert_project(
                name=project["name"],
                repo_root=project["root"],
                progress_log_path=project["progress_log"],
            )
    return storage_record


async def auto_register_document(
    project: Dict[str, Any],
    doc_name: str,
    *,
    server_module: Any,
    resolve_doc_path: Callable[[Dict[str, Any], str], Path],
    project_registry: Any,
    append_entry: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> bool:
    """Auto-register an unregistered document into persistent docs mapping."""
    try:
        doc_path = resolve_doc_path(project, doc_name)
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise ValueError(
            f"Cannot auto-register '{doc_name}': Invalid document identifier or path resolution failed. "
            f"Use 'generate_doc_templates' to create standard documents first. Error: {exc}"
        ) from exc

    if not doc_path.exists():
        raise ValueError(
            f"Cannot auto-register '{doc_name}': File {doc_path} does not exist. "
            f"Use 'generate_doc_templates' to create it first."
        )

    try:
        with open(doc_path, "rb") as handle:
            doc_hash = hashlib.sha256(handle.read()).hexdigest()
    except Exception as exc:  # pragma: no cover - filesystem failure
        raise ValueError(f"Failed to read document {doc_path} for hashing: {exc}") from exc

    backend = server_module.storage_backend
    if not backend:
        raise ValueError("Storage backend not available for auto-registration")

    project_name = project.get("name")
    if not project_name:
        raise ValueError("Project must have a name for auto-registration")

    try:
        execution_context = None
        get_execution_context = getattr(server_module, "get_execution_context", None)
        if callable(get_execution_context):
            try:
                execution_context = get_execution_context()
            except Exception:  # pragma: no cover - defensive context lookup
                execution_context = None
        authoritative_scope = resolve_authoritative_write_scope(
            context=execution_context,
            agent_session_id=None,
        )
        authoritative_session_id = authoritative_scope.get("authoritative_session_id")
        if not authoritative_session_id:
            raise ValueError(
                "Cannot establish authoritative session binding for manage_docs auto-registration."
            )

        current_docs = await _merged_registered_docs(
            backend=backend,
            project=project,
            project_name=project_name,
        )
        registration_key = (
            _path_registration_key(project, str(doc_name), doc_path, current_docs)
            if _looks_like_path(str(doc_name))
            else doc_name
        )
        current_docs[registration_key] = str(doc_path)
        project["docs"] = current_docs
        docs_json = json.dumps(current_docs)
        await backend.update_project_docs(project_name, docs_json, repo_root=project.get("root"))
        state_manager = getattr(server_module, "state_manager", None)
        if state_manager and hasattr(state_manager, "set_current_project"):
            try:
                await state_manager.set_current_project(
                    project_name,
                    project,
                    agent_id="manage_docs",
                    session_id=authoritative_session_id,
                    resolved_scope=authoritative_scope.get("resolved_scope"),
                    mirror_global=False,
                )
            except Exception as exc:
                raise ValueError(
                    f"Authoritative session binding failed during auto-registration: {exc}"
                ) from exc
        logger.info("Auto-registered document '%s' for project '%s'", doc_name, project_name)
    except Exception as exc:
        raise ValueError(f"Failed to update database for auto-registration: {exc}") from exc

    try:
        registry_call = project_registry.record_doc_update(
            project_name=project_name,
            doc=registration_key,
            action="auto_register",
            after_hash=doc_hash,
        )
        if inspect.isawaitable(registry_call):
            await registry_call
    except Exception as exc:  # pragma: no cover - non-fatal logging path
        logger.warning("Failed to update ProjectRegistry for '%s': %s", doc_name, exc)

    try:
        await append_entry(
            message=f"Auto-registered document: {registration_key} ({doc_path.name})",
            status="info",
            agent="manage_docs",
            meta={
                "action": "auto_register",
                "doc": registration_key,
                "doc_name": registration_key,
                "path": str(doc_path),
                "hash": doc_hash[:8],
            },
            format="structured",
        )
    except Exception as exc:  # pragma: no cover - non-fatal logging path
        logger.warning("Failed to log auto-registration event: %s", exc)

    return True


async def register_document_path(
    project: Dict[str, Any],
    doc_name: str,
    doc_path: Path,
    *,
    server_module: Any,
    project_registry: Any,
    append_entry: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
    execution_context: Any = None,
    agent_id: str = "manage_docs",
) -> Optional[str]:
    """Persist a resolved document path into docs mapping and registry state."""
    if not doc_path.exists():
        raise ValueError(f"Cannot register '{doc_name}': File {doc_path} does not exist.")

    try:
        with open(doc_path, "rb") as handle:
            doc_hash = hashlib.sha256(handle.read()).hexdigest()
    except Exception as exc:  # pragma: no cover - filesystem failure
        raise ValueError(f"Failed to read document {doc_path} for hashing: {exc}") from exc

    backend = server_module.storage_backend
    if not backend:
        raise ValueError("Storage backend not available for registration")

    project_name = project.get("name")
    if not project_name:
        raise ValueError("Project must have a name for registration")

    authoritative_scope = resolve_authoritative_write_scope(
        context=execution_context,
        agent_session_id=None,
    )
    authoritative_session_id = authoritative_scope.get("authoritative_session_id")
    if not authoritative_session_id:
        raise ValueError("Cannot establish authoritative session binding for manage_docs registration.")

    current_docs = await _merged_registered_docs(
        backend=backend,
        project=project,
        project_name=project_name,
    )
    current_docs[doc_name] = str(doc_path)
    project["docs"] = current_docs
    docs_json = json.dumps(current_docs)
    state_manager = getattr(server_module, "state_manager", None)
    if state_manager and hasattr(state_manager, "set_current_project"):
        try:
            await state_manager.set_current_project(
                project_name,
                project,
                agent_id=agent_id,
                session_id=authoritative_session_id,
                resolved_scope=authoritative_scope.get("resolved_scope"),
                mirror_global=False,
            )
        except Exception as exc:
            raise ValueError(
                f"Cannot bind project for authoritative session during registration: {exc}"
            ) from exc

    await backend.update_project_docs(project_name, docs_json, repo_root=project.get("root"))

    try:
        registry_call = project_registry.record_doc_update(
            project_name=project_name,
            doc=doc_name,
            action="auto_register",
            after_hash=doc_hash,
        )
        if inspect.isawaitable(registry_call):
            await registry_call
    except Exception as exc:  # pragma: no cover - non-fatal logging path
        logger.warning("Failed to update ProjectRegistry for '%s': %s", doc_name, exc)

    try:
        await append_entry(
            message=f"Auto-registered document: {doc_name} ({doc_path.name})",
            status="info",
            agent="manage_docs",
            meta={
                "action": "auto_register",
                "doc": doc_name,
                "doc_name": doc_name,
                "path": str(doc_path),
                "hash": doc_hash[:8],
            },
            format="structured",
        )
    except Exception as exc:  # pragma: no cover - non-fatal logging path
        logger.warning("Failed to log auto-registration event: %s", exc)

    return None


async def _resolve_case_report_registered_key(
    *,
    active_project: Dict[str, Any],
    requested_name: str,
    doc_category: str,
    server_module: Any,
    project_registry: Any,
    append_entry: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
    execution_context: Any,
    agent_id: str,
    dry_run: bool,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve BUG/SEC case references to a registered manage_docs key."""
    if not requested_name:
        return None, None, None
    if not utils_shared.looks_like_case_report_reference(
        requested_name,
        doc_category=doc_category,
    ):
        return None, None, None

    project_root_raw = str(active_project.get("root") or "").strip()
    if not project_root_raw:
        return None, None, None
    project_root = Path(project_root_raw).expanduser().resolve()
    docs_mapping = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}

    canonical_category = utils_shared.normalize_case_report_category(
        doc_category,
        case_reference=requested_name,
    )
    case_record = None
    resolved_path: Optional[Path] = None
    candidate_doc_name: Optional[str] = None
    registry_summary: Optional[Dict[str, Any]] = None

    backend = getattr(server_module, "storage_backend", None)
    fetch_record = getattr(backend, "fetch_case_registry_record", None) if backend is not None else None
    if callable(fetch_record) and requested_name.upper().startswith(("BUG-", "SEC-")):
        try:
            case_record = await fetch_record(
                case_id=requested_name,
                repo_root=str(project_root),
                project_name=str(active_project.get("name") or ""),
            )
        except Exception as exc:
            logger.warning("Case registry lookup failed for '%s': %s", requested_name, exc)
            case_record = None

    if case_record is not None:
        registry_summary = utils_shared.case_registry_record_summary(case_record)
        record_path_raw = str(getattr(case_record, "doc_path", "") or "").strip()
        if record_path_raw:
            record_path = Path(record_path_raw).expanduser()
            if not record_path.is_absolute():
                record_path = project_root / record_path
            resolved_path = utils_shared.resolve_governed_case_report_path(
                active_project,
                str(record_path.resolve()),
                doc_category=canonical_category,
            )
        candidate_doc_name = str(getattr(case_record, "doc_name", "") or "").strip() or requested_name

    if resolved_path is None:
        resolved_path = utils_shared.resolve_governed_case_report_path(
            active_project,
            requested_name,
            doc_category=canonical_category,
        )
        candidate_doc_name = candidate_doc_name or requested_name

    if resolved_path is None:
        return None, canonical_category, None

    try:
        resolved_path.relative_to(project_root)
    except ValueError:
        return None, canonical_category, (
            f"Refused case report path outside active project root: {resolved_path}"
        )

    if not str(candidate_doc_name or "").upper().startswith(("BUG-", "SEC-")):
        extracted_case = utils_shared.extract_case_registry_metadata_from_report(
            resolved_path,
            project_root=project_root,
            project=active_project,
        )
        if isinstance(extracted_case, dict) and extracted_case.get("case_id"):
            candidate_doc_name = str(extracted_case["case_id"])

    path_bound_key = resolve_registered_doc_key(active_project, str(resolved_path))
    if path_bound_key and path_bound_key in docs_mapping:
        return path_bound_key, canonical_category, None

    candidate_doc_key = str(candidate_doc_name or resolved_path.parent.name).strip()
    if candidate_doc_key in docs_mapping:
        return candidate_doc_key, canonical_category, None

    if dry_run:
        staged_docs = dict(docs_mapping)
        staged_docs[candidate_doc_key] = str(resolved_path)
        active_project["docs"] = staged_docs
        return candidate_doc_key, canonical_category, (
            f"dry_run: would register case report '{candidate_doc_key}' to '{resolved_path}' before mutation."
        )

    reload_warning = await register_document_path(
        active_project,
        candidate_doc_key,
        resolved_path,
        server_module=server_module,
        project_registry=project_registry,
        append_entry=append_entry,
        logger=logger,
        execution_context=execution_context,
        agent_id=agent_id,
    )
    docs_mapping = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
    rebound_key = resolve_registered_doc_key(active_project, candidate_doc_key)
    if rebound_key in docs_mapping:
        return rebound_key, canonical_category, reload_warning
    path_bound_key = resolve_registered_doc_key(active_project, str(resolved_path))
    if path_bound_key in docs_mapping:
        return path_bound_key, canonical_category, reload_warning

    registry_hint = f" registry={registry_summary}" if registry_summary else ""
    return None, canonical_category, (
        f"Case report '{requested_name}' resolved to '{resolved_path}' but did not re-bind to a registered key.{registry_hint}"
    )


async def handle_manage_docs_request(
    *,
    action: str,
    doc_category: str,
    section: Optional[str],
    content: Optional[str],
    patch: Optional[str],
    patch_source_hash: Optional[str],
    edit: Optional[Dict[str, Any] | str],
    patch_mode: Optional[str],
    start_line: Optional[int],
    end_line: Optional[int],
    template: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    doc_name: Optional[str],
    target_dir: Optional[str],
    project: Optional[str],
    state_snapshot: Dict[str, Any],
    helper: LoggingToolMixin,
    context: Optional[LoggingContext] = None,
    server_module: Any,
    append_entry: Callable[..., Awaitable[Any]],
    project_registry: Any,
    logger: logging.Logger,
    handle_special_document_creation: Callable[..., Awaitable[Dict[str, Any]]],
    get_or_create_storage_project: Callable[..., Awaitable[Any]],
    get_index_updater_for_path: Callable[[Path, Path, Path, str], Optional[Callable[[], Awaitable[None]]]],
    auto_register_document: Callable[[Dict[str, Any], str], Awaitable[bool]],
    valid_actions: set[str] = VALID_ACTIONS,
    action_router: Dict[str, str] = ACTION_ROUTER,
    caller_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute manage_docs runtime flow after thin-router argument collection."""
    try:
        healed_params, _, healing_messages = healing_shared.heal_manage_docs_parameters(
            action=action,
            doc_category=doc_category,
            section=section,
            content=content,
            patch=patch,
            patch_source_hash=patch_source_hash,
            edit=edit,
            patch_mode=patch_mode,
            start_line=start_line,
            end_line=end_line,
            template=template,
            metadata=metadata,
            dry_run=dry_run,
            doc_name=doc_name,
            target_dir=target_dir,
            valid_actions=valid_actions,
        )

        action = healed_params["action"]
        doc_category = healed_params["doc_category"]
        section = healed_params["section"]
        content = healed_params["content"]
        patch = healed_params["patch"]
        patch_source_hash = healed_params["patch_source_hash"]
        edit = healed_params["edit"]
        patch_mode = healed_params["patch_mode"]
        start_line = healed_params["start_line"]
        end_line = healed_params["end_line"]
        template = healed_params["template"]
        metadata = healed_params["metadata"]
        dry_run = healed_params["dry_run"]
        doc_name = healed_params["doc_name"]
        target_dir = healed_params["target_dir"]
    except Exception as healing_error:
        return helper.error_response(
            "manage_docs parameter healing failed; no changes applied.",
            suggestion="Verify action/doc/section parameters and retry. For edits, prefer action='apply_patch'.",
            extra={"error_detail": str(healing_error)},
        )

    deprecation_warning: Optional[str] = None

    if healed_params.get("invalid_action"):
        routed_actions = sorted({candidate for candidate in valid_actions if candidate in action_router})
        return helper.error_response(
            f"Invalid manage_docs action '{action}'.",
            suggestion="Use action='apply_patch' for edits, 'replace_section' only for initial scaffolding.",
            extra={
                "allowed_actions": routed_actions,
                "healing_messages": healing_messages,
            },
        )

    if action == "apply_patch" and healed_params.get("patch_mode_invalid"):
        return helper.error_response(
            "Invalid patch_mode; expected 'structured' or 'unified'.",
            suggestion="Set patch_mode to 'structured' for edit payloads or 'unified' for diff patches.",
            extra={
                "allowed_patch_modes": ["structured", "unified"],
                "received_patch_mode": patch_mode,
                "healing_messages": healing_messages,
            },
        )

    scaffold_flag = False
    if isinstance(metadata, dict):
        raw_scaffold = metadata.get("scaffold")
        if isinstance(raw_scaffold, bool):
            scaffold_flag = raw_scaffold
        elif isinstance(raw_scaffold, str):
            scaffold_flag = raw_scaffold.strip().lower() in {"true", "1", "yes"}

    raw_project_input = project
    normalized_project_input = normalize_project_input(project) if project is not None else None
    if normalized_project_input is not None:
        project = normalized_project_input

    if context is not None and project is not None:
        try:
            context = await helper.prepare_context(
                tool_name="manage_docs",
                agent_id=None,
                explicit_project=project,
                require_project=True,
                state_snapshot=state_snapshot,
                reminder_variables={"action": action, "scaffold": scaffold_flag},
                recovery_mode="none",
            )
        except ProjectResolutionError as exc:
            payload = helper.translate_project_error(exc)
            payload.setdefault("suggestion", "Invoke set_project before managing docs.")
            payload.setdefault("reminders", [])
            return payload
    elif context is None:
        try:
            context = await helper.prepare_context(
                tool_name="manage_docs",
                agent_id=None,
                explicit_project=project,
                require_project=True,
                state_snapshot=state_snapshot,
                reminder_variables={"action": action, "scaffold": scaffold_flag},
                recovery_mode="none",
            )
        except ProjectResolutionError as exc:
            payload = helper.translate_project_error(exc)
            payload.setdefault("suggestion", "Invoke set_project before managing docs.")
            payload.setdefault("reminders", [])
            return payload

    active_project = context.project or {}
    if not active_project and raw_project_input:
        fallback_project = await _load_project_record(
            project_name=str(raw_project_input),
            server_module=server_module,
        )
        if fallback_project is None and normalized_project_input and normalized_project_input != raw_project_input:
            fallback_project = await _load_project_record(
                project_name=str(normalized_project_input),
                server_module=server_module,
            )
        if isinstance(fallback_project, dict) and fallback_project:
            active_project = fallback_project
    original_doc_name = doc_name
    doc_name_is_case_path = (
        bool(doc_name)
        and utils_shared.looks_like_case_report_reference(doc_name, doc_category=doc_category)
        and ("/" in str(doc_name) or "\\" in str(doc_name))
    )
    doc_name = (
        resolve_registered_doc_key(active_project, doc_name)
        if doc_name and not doc_name_is_case_path
        else doc_name
    )
    if original_doc_name and doc_name and original_doc_name != doc_name:
        logger.info("Canonicalized doc reference '%s' -> '%s'", original_doc_name, doc_name)

    backend = server_module.storage_backend
    if _is_manage_docs_write_intent(action) and not dry_run:
        assert_writes_allowed(
            Path(active_project.get("root") or ""),
            operation_label="manage_docs",
        )

    runtime_warnings: list[str] = []
    execution_context = None
    if hasattr(server_module, "get_execution_context"):
        try:
            execution_context = server_module.get_execution_context()
        except Exception:
            execution_context = None

    agent_id = await _resolve_manage_docs_actor_id(
        caller_agent=caller_agent,
        execution_context=execution_context,
        server_module=server_module,
    )

    if doc_name:
        docs_mapping = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
        canonical_category = utils_shared.normalize_case_report_category(
            doc_category,
            case_reference=doc_name,
        )
        if canonical_category is not None and doc_category != canonical_category:
            doc_category = canonical_category
        normalized_doc_reference = str(doc_name).strip().replace("\\", "/")
        doc_name_is_direct_case_reference = normalized_doc_reference.upper().startswith(("BUG-", "SEC-"))
        doc_name_is_governed_case_report_path = (
            normalized_doc_reference.endswith("/report.md")
            and (
                "/docs/bugs/" in normalized_doc_reference
                or "/docs/security/" in normalized_doc_reference
            )
        )
        if (
            action in _DOC_TARGETED_REGISTRATION_ACTIONS
            and doc_name not in docs_mapping
            and (doc_name_is_direct_case_reference or doc_name_is_governed_case_report_path)
        ):
            resolved_case_key, resolved_case_category, case_resolution_warning = (
                await _resolve_case_report_registered_key(
                    active_project=active_project,
                    requested_name=str(doc_name),
                    doc_category=doc_category,
                    server_module=server_module,
                    project_registry=project_registry,
                    append_entry=append_entry,
                    logger=logger,
                    execution_context=execution_context,
                    agent_id=str(agent_id),
                    dry_run=dry_run,
                )
            )
            if resolved_case_category is not None:
                doc_category = resolved_case_category
            if case_resolution_warning:
                runtime_warnings.append(case_resolution_warning)
            if resolved_case_key:
                logger.info("Resolved case report reference '%s' -> '%s'", doc_name, resolved_case_key)
                doc_name = resolved_case_key

    if (
        _is_manage_docs_write_intent(action)
        and execution_context is not None
        and getattr(execution_context, "mode", None) == "project"
        and context.resolution_source in _UNSAFE_PROJECT_WRITE_RESOLUTION_SOURCES
    ):
        authority_error = helper.error_response(
            "manage_docs refused a write because project resolution fell back to non-session context.",
            suggestion=(
                "Re-run set_project for this session before creating or mutating docs. "
                "Writes must use the session-bound active project, not agent or legacy fallback state."
            ),
            extra={
                "project_name": active_project.get("name"),
                "project_resolution": build_resolution_metadata(context),
                "reason_code": "manage_docs_write_requires_session_binding",
            },
        )
        return helper.apply_context_payload(authority_error, context)

    if doc_name and action in _DOC_TARGETED_REGISTRATION_ACTIONS:
        docs = active_project.get("docs", {}) if isinstance(active_project.get("docs"), dict) else {}
        if doc_name not in docs:
            logger.info("Document '%s' not registered, attempting safe registration for action '%s'...", doc_name, action)
            try:
                if dry_run:
                    resolved_path = _resolve_doc_path(active_project, str(doc_name))
                    if not resolved_path.exists():
                        raise ValueError(f"File {resolved_path} does not exist.")
                    active_project = dict(active_project)
                    staged_docs = dict(active_project.get("docs", {}) or {})
                    staged_docs[str(doc_name)] = str(resolved_path)
                    active_project["docs"] = staged_docs
                    runtime_warnings.append(
                        f"dry_run: would auto-register '{doc_name}' before executing action '{action}'."
                    )
                else:
                    await auto_register_document(active_project, str(doc_name))
                    try:
                        context = await helper.prepare_context(
                            tool_name="manage_docs",
                            agent_id=None,
                            require_project=True,
                            state_snapshot=state_snapshot,
                            reminder_variables={"action": action, "scaffold": scaffold_flag},
                        )
                        active_project = context.project or active_project
                        logger.info(
                            "Successfully registered and reloaded project context for '%s'",
                            doc_name,
                        )
                    except Exception as reload_error:
                        warning = (
                            "Auto-registration succeeded but context reload failed: "
                            f"{reload_error}"
                        )
                        runtime_warnings.append(warning)
                        logger.warning(warning)
            except Exception as exc:
                error_payload = helper.error_response(
                    f"Auto-registration failed for document '{doc_name}'",
                    suggestion=(
                        "Ensure the file exists inside the active project's managed docs tree. "
                        f"Error: {str(exc)}"
                    ),
                    extra={"doc_name": doc_name, "auto_registration_error": str(exc)},
                )
                return helper.apply_context_payload(error_payload, context)

    if action == "project_health":
        response = await _handle_project_health(
            active_project=active_project,
            metadata=metadata if isinstance(metadata, dict) else {},
            helper=helper,
            context=context,
        )
        return _attach_manage_docs_project_context(response, context=context)
    if action in {"quality_check", "scaffold_quality_check"}:
        response = await _handle_quality_check(
            active_project=active_project,
            doc_name=doc_name,
            doc_category=doc_category,
            metadata=metadata if isinstance(metadata, dict) else {},
            project_registry=project_registry,
            append_entry=append_entry,
            logger=logger,
            server_module=server_module,
            execution_context=execution_context,
            agent_id=str(agent_id),
            helper=helper,
            context=context,
        )
        return _attach_manage_docs_project_context(response, context=context)
    if action == "quality_handoff_check":
        response = await _handle_quality_handoff_check(
            active_project=active_project,
            agent_id=str(agent_id),
            helper=helper,
            context=context,
        )
        return _attach_manage_docs_project_context(response, context=context)
    if action == "topology_scan":
        response = intelligence_workflows_shared.topology_scan(active_project=active_project)
        return _attach_manage_docs_project_context(helper.apply_context_payload(response, context), context=context)
    if action == "metadata_scan":
        response = intelligence_workflows_shared.metadata_scan(active_project=active_project)
        return _attach_manage_docs_project_context(helper.apply_context_payload(response, context), context=context)
    if action == "metadata_repair":
        response = intelligence_workflows_shared.metadata_repair(
            active_project=active_project,
            mode=str((metadata or {}).get("mode") or "report_only") if isinstance(metadata, dict) else "report_only",
        )
        return _attach_manage_docs_project_context(helper.apply_context_payload(response, context), context=context)
    if action == "stale_cleanup_scan":
        response = intelligence_workflows_shared.stale_cleanup_scan(active_project=active_project)
        return _attach_manage_docs_project_context(helper.apply_context_payload(response, context), context=context)

    if action == "ingestion_manifest_inspect":
        payload = intelligence_exports_shared.build_export_payload(active_project=active_project)
        response = {"ok": True, "action": "ingestion_manifest_inspect", "read_only": True, "preview": payload["downstream_ingestion_manifest"]}
        return _attach_manage_docs_project_context(helper.apply_context_payload(response, context), context=context)
    if action == "regenerate_intelligence_exports":
        paths = intelligence_exports_shared.write_export_artifacts(active_project=active_project)
        response = {"ok": True, "action": "regenerate_intelligence_exports", "artifact_paths": paths}
        return _attach_manage_docs_project_context(helper.apply_context_payload(response, context), context=context)

    if action == "rehome_doc":
        rehome_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        if isinstance(target_dir, str) and target_dir.strip() and not rehome_metadata.get("target_dir"):
            rehome_metadata["target_dir"] = target_dir.strip()
        response = await _handle_rehome_doc(
            active_project=active_project,
            doc_name=doc_name,
            metadata=rehome_metadata,
            dry_run=dry_run,
            helper=helper,
            context=context,
            execution_context=execution_context,
            server_module=server_module,
            agent_id=str(agent_id),
        )
        return _attach_manage_docs_project_context(response, context=context)

    docs_for_target = active_project.get("docs", {}) if isinstance(active_project.get("docs"), dict) else {}
    registered_case_alias = (
        bool(doc_name)
        and doc_name in docs_for_target
        and utils_shared.normalize_case_report_category(doc_category, case_reference=doc_name) is not None
    )
    if action in _MUTATION_ACTIONS and doc_category in _CUSTOM_DOC_TYPES and doc_name and not registered_case_alias:
        resolved_path = utils_shared.resolve_custom_doc_path(
            project=active_project,
            doc_category=doc_category,
            doc_name=doc_name,
        )
        if resolved_path:
            logger.info("Resolved custom document: %s", resolved_path)
            if not resolved_path.exists():
                error_payload = helper.error_response(
                    f"Custom document '{doc_name}' resolved to a missing file",
                    suggestion="Ensure the file exists before running mutation actions.",
                    extra={"doc_name": doc_name, "resolved_path": str(resolved_path)},
                )
                return helper.apply_context_payload(error_payload, context)

            docs_mapping = active_project.get("docs", {}) or {}
            needs_registration = doc_name not in docs_mapping or doc_category not in docs_mapping
            if needs_registration and dry_run:
                active_project = active_project.copy()
                staged_docs = dict(active_project.get("docs", {}) or {})
                staged_docs[doc_name] = str(resolved_path)
                staged_docs[doc_category] = str(resolved_path)
                active_project["docs"] = staged_docs
                runtime_warnings.append(
                    f"dry_run: would register '{doc_name}' and '{doc_category}' to '{resolved_path}' before mutation."
                )
            elif needs_registration:
                for registration_key in (doc_name, doc_category):
                    if registration_key in docs_mapping:
                        continue
                    try:
                        reload_warning = await register_document_path(
                            active_project,
                            registration_key,
                            resolved_path,
                            server_module=server_module,
                            project_registry=project_registry,
                            append_entry=append_entry,
                            logger=logger,
                            execution_context=execution_context,
                            agent_id=str(agent_id),
                        )
                        if reload_warning:
                            runtime_warnings.append(reload_warning)
                    except Exception as reg_exc:
                        # Deterministic custom-doc path resolution already located a real file.
                        # Keep mutation flow available even when durable registration is degraded.
                        staged_docs = dict(active_project.get("docs", {}) or {})
                        staged_docs[registration_key] = str(resolved_path)
                        active_project["docs"] = staged_docs
                        runtime_warnings.append(
                            "Custom document registration degraded; using deterministic path "
                            f"fallback for '{registration_key}' at '{resolved_path}': {reg_exc}"
                        )
                try:
                    context = await helper.prepare_context(
                        tool_name="manage_docs",
                        agent_id=None,
                        require_project=True,
                        state_snapshot=state_snapshot,
                        reminder_variables={"action": action, "scaffold": scaffold_flag},
                    )
                    active_project = context.project or active_project
                except Exception as reload_error:
                    runtime_warnings.append(
                        f"Custom document registration persisted, but context reload failed: {reload_error}"
                    )
                    logger.warning(runtime_warnings[-1])
        else:
            project_slug = slugify_project_name(active_project.get("name", "<project>"))
            error_payload = helper.error_response(
                f"Custom document '{doc_name}' not found",
                suggestion=(
                    f"Ensure document was created with create_{doc_category}_doc action. "
                    f"Check doc_name spelling and verify the document exists. "
                    f"For research docs: check .scribe/docs/dev_plans/{project_slug}/research/ "
                    f"For bug reports: check docs/bugs/<category>/<date>_{doc_name}/"
                ),
                extra={
                    "doc_type": doc_category,
                    "doc_name": doc_name,
                    "searched_in": str(Path(active_project.get("progress_log")).parent)
                    if active_project.get("progress_log")
                    else "unknown",
                    "project_root": str(active_project.get("root")),
                },
            )
            return helper.apply_context_payload(error_payload, context)
    elif action in _MUTATION_ACTIONS and doc_name:
        docs = active_project.get("docs", {})
        if doc_name not in docs:
            logger.info("Document '%s' not registered, attempting auto-registration...", doc_name)
            if dry_run:
                runtime_warnings.append(
                    f"dry_run: would auto-register '{doc_name}' before executing mutation action '{action}'."
                )
            try:
                if not dry_run:
                    await auto_register_document(active_project, doc_name)
                    try:
                        context = await helper.prepare_context(
                            tool_name="manage_docs",
                            agent_id=None,
                            require_project=True,
                            state_snapshot=state_snapshot,
                            reminder_variables={"action": action, "scaffold": scaffold_flag},
                        )
                        active_project = context.project or {}
                        logger.info(
                            "Successfully auto-registered and reloaded project context for '%s'",
                            doc_name,
                        )
                    except Exception as reload_error:
                        warning = (
                            "Auto-registration succeeded but context reload failed: "
                            f"{reload_error}"
                        )
                        runtime_warnings.append(warning)
                        logger.warning(warning)
            except Exception as exc:
                error_payload = helper.error_response(
                    f"Auto-registration failed for document '{doc_name}'",
                    suggestion=(
                        f"Ensure the file exists or use 'generate_doc_templates' to create it. "
                        f"Error: {str(exc)}"
                    ),
                    extra={"doc_name": doc_name, "auto_registration_error": str(exc)},
                )
                return helper.apply_context_payload(error_payload, context)

    metadata_mapping = metadata if isinstance(metadata, dict) else None

    # For replace_range called via the MCP tool surface, default to file-relative
    # line numbers so that agents using read_file line numbers get correct results.
    # The internal API (apply_doc_change) defaults to body-relative for backwards
    # compatibility; this injection bridges the gap.
    if action == "replace_range":
        if metadata_mapping is None:
            metadata_mapping = {}
        if "line_reference" not in metadata_mapping:
            metadata_mapping["line_reference"] = "file"

    action, create_response = await create_actions.normalize_or_handle_create_action(
        action=action,
        metadata=metadata_mapping,
        doc_name=doc_name,
        target_dir=target_dir,
        content=content,
        dry_run=dry_run,
        agent_id=agent_id,
        project=active_project,
        storage_backend=backend,
        helper=helper,
        context=context,
        handle_special_document_creation=handle_special_document_creation,
        deprecation_warning=deprecation_warning,
    )
    if create_response is not None:
        enriched_create = _attach_manage_docs_project_context(create_response, context=context)
        if isinstance(enriched_create, dict) and enriched_create.get("ok"):
            enriched_create = await _attach_create_section_inventory(enriched_create)
        return enriched_create

    route_key = action_router.get(action)
    if route_key is None:
        return helper.apply_context_payload({"ok": False, "error": f"Unsupported action '{action}'"}, context)

    action_kwargs = {
        "action": action,
        "project": active_project,
        "doc_name": doc_name,
        "doc_category": doc_category,
        "section": section,
        "content": content,
        "patch": patch,
        "patch_source_hash": patch_source_hash,
        "edit": edit,
        "patch_mode": patch_mode,
        "start_line": start_line,
        "end_line": end_line,
        "template": template,
        "metadata": metadata_mapping,
        "dry_run": dry_run,
        "backend": backend,
        "agent_id": agent_id,
        "helper": helper,
        "context": context,
        "execution_context": execution_context,
        "deprecation_warning": deprecation_warning,
        "apply_doc_change": apply_doc_change,
        "get_or_create_storage_project": get_or_create_storage_project,
        "append_entry": append_entry,
        "normalize_metadata_with_healing": healing_shared.normalize_metadata_with_healing,
        "index_doc_for_vector": indexing_shared.index_doc_for_vector,
        "vector_indexing_enabled": indexing_shared.vector_indexing_enabled,
        "get_index_updater_for_path": get_index_updater_for_path,
        "project_registry": project_registry,
        "server_module": server_module,
        "logger": logger,
    }

    if route_key == "query":
        response = await query_actions.handle_query_actions(
            action=action,
            project=active_project,
            doc_name=doc_name,
            metadata=metadata_mapping,
            helper=helper,
            context=context,
        )
    elif route_key == "search":
        response = await search_actions.handle_search_action(
            action=action,
            project=active_project,
            doc_name=doc_name,
            metadata=metadata_mapping,
            helper=helper,
            context=context,
        )
    elif route_key == "query_transform":
        response = await query_actions.handle_query_transform_actions(
            action=action,
            action_kwargs=action_kwargs,
            handle_edit_action=edit_actions.handle_edit_action,
        )
    elif route_key == "append":
        response = await append_actions.handle_append_action(**action_kwargs)
    elif route_key == "status":
        response = await status_actions.handle_status_action(**action_kwargs)
    elif route_key == "edit":
        response = await edit_actions.handle_edit_action(**action_kwargs)
    elif route_key == "batch":
        response = await batch_actions.handle_batch_action(
            action=action,
            project=active_project,
            metadata=metadata_mapping,
            dry_run=dry_run,
            helper=helper,
            context=context,
            doc_name=doc_name,
        )
    else:
        return helper.apply_context_payload(
            {
                "ok": False,
                "error": f"ACTION_ROUTER misconfigured for action '{action}'",
                "route_key": route_key,
            },
            context,
        )

    if response is not None:
        if isinstance(response, dict):
            response = _attach_manage_docs_project_context(response, context=context)
            if response.get("ok") and action in {"create", "create_doc"}:
                response = await _attach_create_section_inventory(response)
            if response.get("ok") and action in _MUTATION_ACTIONS:
                response = _attach_case_doc_binding_readback(
                    response,
                    project=active_project,
                    doc_name=doc_name,
                    doc_category=doc_category,
                )
            if response.get("ok") and not dry_run and action in _MUTATION_ACTIONS:
                case_registry_warning = await _refresh_case_registry_for_mutation(
                    storage_backend=backend,
                    project=active_project,
                    response=response,
                    doc_name=doc_name,
                    doc_category=doc_category,
                )
                if case_registry_warning:
                    response.setdefault("warnings", []).append(case_registry_warning)
        if runtime_warnings and isinstance(response, dict) and response.get("ok") is not False:
            response.setdefault("warnings", []).extend(runtime_warnings)
        return response

    return helper.apply_context_payload(
        {"ok": False, "error": f"No handler consumed action '{action}'", "route_key": route_key},
        context,
    )
