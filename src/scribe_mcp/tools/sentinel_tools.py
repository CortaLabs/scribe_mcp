"""Sentinel mode toolset (append_event/open_bug/open_security/link_fix)."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Optional
from pathlib import Path

from scribe_mcp import server as server_module
from scribe_mcp.case_lifecycle import (
    CanonicalDocBinding,
    build_canonical_doc_binding,
    build_link_fix_lifecycle_result,
    doc_binding_from_metadata,
    doc_binding_to_metadata,
)
from scribe_mcp.doc_management import utils as doc_utils
from scribe_mcp.shared.reference_resolution import build_reference_scope, resolve_reference
from scribe_mcp.shared.tool_runtime import resolve_context_authoritative_session_key
from scribe_mcp.server import app
from scribe_mcp.shared.log_enums import LogPriority
from scribe_mcp.tool_contracts import additive_local_tool
from scribe_mcp.utils.sentinel_logs import append_case_event, append_sentinel_event


# Template field list for completeness scoring
_BUG_TEMPLATE_FIELDS = [
    "summary_long",
    "symptoms",
    "category",
    "severity",
    "status",
    "expected_behavior",
    "actual_behavior",
    "reproduction_steps",
    "component",
    "environment",
    "customer_impact",
    "affected_areas",
    "root_cause",
    "immediate_actions",
]

# Completeness fields are SEMANTIC fields, not section anchors. Guidance must
# name the anchor that hosts each field, or replace_section fails with
# SECTION_ANCHOR_MISSING (live-reproduced on BUG-2026-06-11-0004, P1.6).
_BUG_FIELD_SECTION_ANCHORS = {
    "summary_long": "description",
    "symptoms": "description",
    "expected_behavior": "description",
    "actual_behavior": "description",
    "reproduction_steps": "description",
    "category": "bug_overview",
    "severity": "bug_overview",
    "status": "bug_overview",
    "component": "bug_overview",
    "environment": "bug_overview",
    "customer_impact": "bug_overview",
    "root_cause": "investigation",
    "affected_areas": "investigation",
    "immediate_actions": "resolution_plan",
}

_SECURITY_FIELD_SECTION_ANCHORS = {
    **_BUG_FIELD_SECTION_ANCHORS,
    "category": "security_overview",
    "severity": "security_overview",
    "status": "security_overview",
    "component": "security_overview",
    "environment": "security_overview",
    "customer_impact": "security_overview",
    "affected_areas": "affected_systems",
}

# Completeness scoring must use a per-case-type field set so a future
# security-only field (CVSS, exposure, blast-radius) is scored against the
# security contract rather than the bug field set (F4). Currently equal to the
# bug set, but kept as a distinct binding so the scoring source is explicit and
# can diverge without touching the shared scoring loop.
_SECURITY_TEMPLATE_FIELDS = list(_BUG_TEMPLATE_FIELDS)


# ---------------------------------------------------------------------------
# Host input-schema enrichment (P2.2)
#
# Mirrors the proven ``set_project`` / ``manage_docs`` (P1.2) ``input_schema=``
# override pattern: each ``@app.tool`` passes a hand-authored schema that the
# host uses verbatim, and the server's ``_with_runtime_agent_schema`` then
# injects the required ``agent`` field. ``additionalProperties`` stays ``True``
# so the rich optional-kwarg surface (component, environment, preview, ...) is
# never regressed into a hard host rejection.
#
# Enum values are sourced LIVE from their real accepted-value sources so they
# cannot drift from runtime behavior:
#   * ``severity`` -> ``LogPriority`` (critical/high/medium/low), the same
#     severity vocabulary the docstrings advertise.
#   * ``landing_status`` -> the unified case-status vocabulary in
#     ``doc_management/utils.py`` (the exact tokens ``resolved_case_close_status``
#     understands: open + fix-terminal + non-fix-terminal). A non-terminal token
#     legitimately leaves the case open, which is why the open set is included.
# ``category`` is intentionally NOT enumerated: it is a free-form organizational
# label ("auth"/"api"/"injection"/...) validated only as non-empty at runtime.
# There is no canonical accepted-value source for it, so it carries teaching
# guidance via ``description`` rather than a fabricated enum that would falsely
# reject valid free-form categories.

# Severity values, live from the canonical priority vocabulary (single source of
# truth — derived, never hand-copied).
_SEVERITY_ENUM: list[str] = [member.value for member in LogPriority]

# The case-category guidance (free-form; teach, do not constrain).
_BUG_CATEGORY_DESCRIPTION = (
    "Free-form organizational label for the bug (e.g. 'auth', 'api', 'ui', "
    "'runtime', 'startup'). Required and non-empty; not constrained to a fixed "
    "vocabulary."
)
_SECURITY_CATEGORY_DESCRIPTION = (
    "Free-form organizational label for the security issue (e.g. 'auth', "
    "'injection', 'xss', 'secrets'). Required and non-empty; not constrained to "
    "a fixed vocabulary."
)
_CASE_ID_FORMAT_HINT = (
    "Stable per-day case identifier. Format: 'BUG-YYYYMMDD-NNNN' for bug cases "
    "or 'SEC-YYYYMMDD-NNNN' for security cases."
)


def _landing_status_enum() -> list[str]:
    """Live accepted-value list for ``link_fix`` ``landing_status``.

    Sourced from the unified case-status vocabulary (P1.1) so it tracks exactly
    the tokens ``doc_utils.resolved_case_close_status`` recognizes:
    open (non-terminal, leaves the case open), fix-terminal (collapses to
    "closed"), and non-fix-terminal (preserved as the closure reason). Sorted
    for stable host presentation; derived, never frozen.
    """
    return sorted(
        doc_utils.CASE_OPEN_STATUS_VALUES | doc_utils.CASE_CLOSED_STATUS_VALUES
    )


def _build_open_bug_input_schema() -> Dict[str, Any]:
    """Hand-authored host input schema for ``open_bug`` (severity enum)."""
    return {
        "type": "object",
        "properties": {
            "agent": {"type": "string"},
            "title": {"type": "string"},
            "symptoms": {"type": "string"},
            "category": {"type": "string", "description": _BUG_CATEGORY_DESCRIPTION},
            "affected_paths": {"type": "array"},
            "expected_behaviour": {"type": "string"},
            "steps_to_reproduce": {"type": "array"},
            "root_cause": {"type": "string"},
            "resolution_notes": {"type": "string"},
            "severity": {
                "type": "string",
                "enum": list(_SEVERITY_ENUM),
                "description": (
                    "Bug severity level (sourced from the canonical priority "
                    "vocabulary). Defaults to 'medium' when omitted."
                ),
            },
            "component": {"type": "string"},
            "environment": {"type": "string"},
            "customer_impact": {"type": "string"},
            "preview": {"type": "boolean"},
        },
        "required": ["title", "symptoms", "category"],
        "additionalProperties": True,
    }


def _build_open_security_input_schema() -> Dict[str, Any]:
    """Hand-authored host input schema for ``open_security`` (severity enum)."""
    return {
        "type": "object",
        "properties": {
            "agent": {"type": "string"},
            "title": {"type": "string"},
            "symptoms": {"type": "string"},
            "category": {
                "type": "string",
                "description": _SECURITY_CATEGORY_DESCRIPTION,
            },
            "affected_paths": {"type": "array"},
            "expected_behaviour": {"type": "string"},
            "steps_to_reproduce": {"type": "array"},
            "root_cause": {"type": "string"},
            "resolution_notes": {"type": "string"},
            "severity": {
                "type": "string",
                "enum": list(_SEVERITY_ENUM),
                "description": (
                    "Security severity level (sourced from the canonical "
                    "priority vocabulary). Defaults to 'high' when omitted."
                ),
            },
            "component": {"type": "string"},
            "environment": {"type": "string"},
            "customer_impact": {"type": "string"},
            "preview": {"type": "boolean"},
        },
        "required": ["title", "symptoms", "category"],
        "additionalProperties": True,
    }


def _build_link_fix_input_schema() -> Dict[str, Any]:
    """Hand-authored host input schema for ``link_fix`` (landing_status enum)."""
    return {
        "type": "object",
        "properties": {
            "agent": {"type": "string"},
            "case_id": {"type": "string", "description": _CASE_ID_FORMAT_HINT},
            "execution_id": {"type": "string"},
            "artifact_ref": {"type": "string"},
            "landing_status": {
                "type": "string",
                "enum": _landing_status_enum(),
                "description": (
                    "Landing/lifecycle status for the linked fix (sourced from "
                    "the unified case-status vocabulary). Fix-terminal values "
                    "(e.g. 'merged', 'resolved') close the case; non-fix-terminal "
                    "values (e.g. 'wontfix', 'duplicate') close it with the "
                    "reason preserved; open values (e.g. 'in_progress') leave the "
                    "case open."
                ),
            },
        },
        "required": ["case_id", "artifact_ref", "landing_status"],
        "additionalProperties": True,
    }


_OPEN_BUG_INPUT_SCHEMA: Dict[str, Any] = _build_open_bug_input_schema()
_OPEN_SECURITY_INPUT_SCHEMA: Dict[str, Any] = _build_open_security_input_schema()
_LINK_FIX_INPUT_SCHEMA: Dict[str, Any] = _build_link_fix_input_schema()


def _format_unfilled_guidance(
    unfilled_fields: list[str],
    anchor_map: dict[str, str],
    limit: int,
) -> str:
    """Render unfilled fields with their hosting section anchors for guidance."""
    rendered = [
        f"{field} (section='{anchor_map.get(field, 'description')}')"
        for field in unfilled_fields[:limit]
    ]
    suffix = (
        f" and {len(unfilled_fields) - limit} more"
        if len(unfilled_fields) > limit
        else ""
    )
    return ", ".join(rendered) + suffix


def _normalize_artifact_reference(artifact_ref: str) -> dict[str, Any]:
    raw = str(artifact_ref or "").strip()
    if not raw:
        return {"raw": raw, "kind": "artifact", "source": "link_fix_argument", "value": raw}
    if re.fullmatch(r"[0-9a-f]{7,40}", raw):
        return {"raw": raw, "kind": "git_commit", "source": "link_fix_argument", "value": raw}
    if raw.startswith("commit:"):
        return {"raw": raw, "kind": "git_commit", "source": "link_fix_argument", "value": raw.split(":", 1)[1].strip()}
    if raw.startswith("scribe://"):
        return {"raw": raw, "kind": "scribe_reference", "source": "link_fix_argument", "value": raw}
    return {"raw": raw, "kind": "artifact", "source": "link_fix_argument", "value": raw}

def _operator_envelope(
    *,
    ok: bool,
    mode: str,
    case_id: Optional[str] = None,
    artifacts: Optional[list[dict[str, str]]] = None,
    warnings: Optional[list[str]] = None,
    next_step: str = "",
    **extra: Any,
) -> Dict[str, Any]:
    envelope: Dict[str, Any] = {
        "ok": ok,
        "mode": mode,
        "case_id": case_id or "",
        "artifacts": artifacts or [],
        "warnings": warnings or [],
        "next_step": next_step,
    }
    envelope.update(extra)
    return envelope


def _require_sentinel_context():
    context = server_module.get_execution_context()
    if not context:
        raise ValueError("ExecutionContext missing")
    if context.mode != "sentinel":
        raise ValueError("Sentinel tool called outside sentinel mode")
    return context


def _get_context():
    context = server_module.get_execution_context()
    if not context:
        raise ValueError("ExecutionContext missing")
    return context


def _unwrap_result(result: Any) -> Dict[str, Any]:
    """Extract dict from result, handling MCP CallToolResult wrapper if present."""
    import json

    if isinstance(result, dict):
        return result

    # Handle MCP CallToolResult wrapper
    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, list) and content:
            first = content[0]
            if hasattr(first, "text"):
                try:
                    return json.loads(first.text)
                except Exception:
                    pass
            # If first item is a dict directly
            if isinstance(first, dict):
                return first

    # Try to serialize and deserialize to get a plain dict
    try:
        return json.loads(json.dumps(result, default=str))
    except Exception:
        pass

    # Fallback: try to convert to dict
    if hasattr(result, "__dict__"):
        try:
            return json.loads(json.dumps(result.__dict__, default=str))
        except Exception:
            return dict(result.__dict__)

    return {"ok": False, "error": "Could not unwrap result"}


def _case_id_directory_exists(repo_root: Path, candidate_case_id: str, suffix: str) -> bool:
    """Return True if a report directory already owns ``candidate_case_id``.

    Report directories are named ``{date}_{slug}`` where ``slug`` is the case ID,
    so collision detection is an EXACT directory-name suffix match (F8). This
    reads directory NAMES only — never report bodies — so the per-allocation cost
    is bounded by the number of report directories and independent of report file
    size. A bare exact-name match (``slug`` only) is also honoured for resilience
    against any non-date-prefixed layout.
    """
    docs_root = repo_root / "docs"
    for section in (docs_root / "bugs", docs_root / "security"):
        if not section.exists():
            continue
        # ``*/*`` mirrors the report layout ``{category}/{date}_{slug}`` without
        # touching ``report.md`` contents.
        for report_dir in section.glob("*/*"):
            try:
                if not report_dir.is_dir():
                    continue
            except OSError:
                continue
            name = report_dir.name
            if name.endswith(suffix) or name == candidate_case_id:
                return True
    return False


def _next_case_id_for_project(kind: str, result: Dict[str, Any]) -> str:
    """Generate a case ID for project mode using a repo-scoped atomic counter.

    Args:
        kind: "BUG" or "SEC"
        result: The result from append_entry containing paths info

    Returns:
        Case ID like "BUG-2026-01-24-0001"
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = f"{kind}-{today}-"

    paths = result.get("paths", [])
    primary_path = result.get("path")
    if primary_path:
        paths = [primary_path] + [p for p in paths if p != primary_path]

    project_dir: Optional[Path] = None
    for log_path in paths:
        try:
            candidate = Path(log_path).resolve().parent
            if candidate.exists() and candidate.is_dir():
                project_dir = candidate
                break
        except Exception:
            continue

    if project_dir is None:
        raise RuntimeError(
            "case-id allocation failed: unable to resolve project directory from append_entry result paths"
        )

    repo_root = project_dir
    for parent in project_dir.parents:
        expected = parent / ".scribe" / "docs" / "dev_plans" / project_dir.name
        try:
            if expected.resolve() == project_dir:
                repo_root = parent
                break
        except Exception:
            continue

    counter_dir = repo_root / ".scribe" if repo_root != project_dir else project_dir
    counter_dir.mkdir(parents=True, exist_ok=True)
    counter_file = counter_dir / ".sentinel_case_id_counters.json"
    lock_file = counter_dir / ".sentinel_case_id_counters.lock"
    lock_fd: Optional[int] = None
    deadline = time.monotonic() + 2.0

    while True:
        try:
            lock_fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError("case-id allocation failed: timeout acquiring counter lock")
            time.sleep(0.01)
        except Exception as exc:
            raise RuntimeError(f"case-id allocation failed: lock acquisition error: {exc}") from exc

    try:
        counters: Dict[str, Dict[str, int]] = {}
        if counter_file.exists():
            try:
                import json
                loaded = json.loads(counter_file.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RuntimeError(
                    f"case-id allocation failed: unable to read persisted counter state: {exc}"
                ) from exc
            if not isinstance(loaded, dict):
                raise RuntimeError(
                    "case-id allocation failed: persisted counter state is malformed (expected JSON object)"
                )
            counters = loaded

        day_counters = counters.get(today)
        if day_counters is None:
            day_counters = {}
            counters[today] = day_counters
        elif not isinstance(day_counters, dict):
            raise RuntimeError(
                "case-id allocation failed: persisted counter state is malformed "
                f"(expected object at date bucket '{today}')"
            )

        for counter_kind in ("BUG", "SEC"):
            if counter_kind not in day_counters:
                continue
            persisted_value = day_counters[counter_kind]
            if not isinstance(persisted_value, int) or isinstance(persisted_value, bool) or persisted_value < 0:
                raise RuntimeError(
                    "case-id allocation failed: persisted counter state is malformed "
                    f"(expected non-negative integer at date bucket '{today}' for kind '{counter_kind}')"
                )

        persisted_seq = day_counters.get(kind, 0)
        if not isinstance(persisted_seq, int) or isinstance(persisted_seq, bool) or persisted_seq < 0:
            raise RuntimeError(
                "case-id allocation failed: persisted counter state is malformed "
                f"(expected non-negative integer at date bucket '{today}' for kind '{kind}')"
            )
        # Uniqueness check (F8): the atomic counter is the allocator. Report
        # directories are named ``{date}_{slug}`` where ``slug == case_id``, so a
        # collision is an EXACT directory-name suffix match — never full-text body
        # content. The previous implementation read every report body under this
        # lock (O(reports x filesize) per allocation) and false-positived when a
        # case ID was quoted in another report (e.g. a cross-reference). Comparing
        # directory names only keeps the per-allocation cost bounded by the report
        # count and independent of report file size.
        next_seq = persisted_seq + 1
        while True:
            candidate_case_id = f"{prefix}{next_seq:04d}"
            suffix = f"_{candidate_case_id}"
            if not _case_id_directory_exists(repo_root, candidate_case_id, suffix):
                break
            next_seq += 1

        day_counters[kind] = next_seq

        import json
        tmp_file = counter_file.with_suffix(f"{counter_file.suffix}.tmp")
        tmp_file.write_text(json.dumps(counters, sort_keys=True), encoding="utf-8")
        tmp_file.replace(counter_file)

        return f"{prefix}{next_seq:04d}"
    finally:
        try:
            if lock_fd is not None:
                os.close(lock_fd)
        finally:
            try:
                lock_file.unlink()
            except Exception:
                pass


def _preview_case_id_for_project(kind: str, context: Any) -> str:
    """Compute next case ID without mutating state.

    This preview path reads persisted counter/docs state but does not write counters,
    append entries, or create documents.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = f"{kind}-{today}-"

    repo_root_raw = getattr(context, "repo_root", None)
    if not isinstance(repo_root_raw, str) or not repo_root_raw.strip():
        raise RuntimeError("case-id preview failed: missing repo_root in execution context")
    repo_root = Path(repo_root_raw).resolve()

    affected_projects = getattr(context, "affected_dev_projects", None)
    project_name = (
        affected_projects[0]
        if isinstance(affected_projects, list) and affected_projects and isinstance(affected_projects[0], str)
        else None
    )

    if project_name:
        project_dir = (repo_root / ".scribe" / "docs" / "dev_plans" / project_name).resolve()
        if project_dir.exists() and project_dir.is_dir():
            counter_dir = repo_root / ".scribe"
        else:
            counter_dir = repo_root / ".scribe"
    else:
        counter_dir = repo_root / ".scribe"

    counter_file = counter_dir / ".sentinel_case_id_counters.json"
    persisted_seq = 0
    if counter_file.exists():
        try:
            import json
            loaded = json.loads(counter_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"case-id preview failed: unable to read persisted counter state: {exc}"
            ) from exc
        if not isinstance(loaded, dict):
            raise RuntimeError(
                "case-id preview failed: persisted counter state is malformed (expected JSON object)"
            )
        day_counters = loaded.get(today, {})
        if not isinstance(day_counters, dict):
            raise RuntimeError(
                "case-id preview failed: persisted counter state is malformed "
                f"(expected object at date bucket '{today}')"
            )
        persisted_value = day_counters.get(kind, 0)
        if not isinstance(persisted_value, int) or isinstance(persisted_value, bool) or persisted_value < 0:
            raise RuntimeError(
                "case-id preview failed: persisted counter state is malformed "
                f"(expected non-negative integer at date bucket '{today}' for kind '{kind}')"
            )
        persisted_seq = persisted_value

    next_seq = persisted_seq + 1
    while True:
        candidate_case_id = f"{prefix}{next_seq:04d}"
        duplicate_found = False
        docs_root = repo_root / "docs"
        for candidate in (
            docs_root / "bugs",
            docs_root / "security",
        ):
            if not candidate.exists():
                continue
            for report_path in candidate.glob("*/*/report.md"):
                try:
                    if candidate_case_id in report_path.read_text(encoding="utf-8"):
                        duplicate_found = True
                        break
                except OSError:
                    continue
            if duplicate_found:
                break
        if not duplicate_found:
            return candidate_case_id
        next_seq += 1


def _build_descriptive_message(event_type: Optional[str], data: Optional[Dict[str, Any]]) -> str:
    """Build a human-readable message from event_type and data.

    Instead of terse messages like "scope_violation", creates descriptive ones like:
    "Scope violation: absolute_path_not_allowlisted - /path/to/file.py"
    """
    if not event_type:
        return "sentinel_event"

    # Handle known event types with specific formatting
    if event_type == "scope_violation" and isinstance(data, dict):
        reason = data.get("reason", "unknown")
        path = data.get("path", "")
        tool_name = data.get("tool_name", "")

        # Build descriptive message
        parts = [f"Scope violation: {reason}"]
        if path:
            # Truncate long paths for readability
            display_path = path if len(path) <= 60 else f"...{path[-57:]}"
            parts.append(f"path={display_path}")
        if tool_name:
            parts.append(f"tool={tool_name}")
        return " | ".join(parts)

    if event_type == "read_file_error" and isinstance(data, dict):
        reason = data.get("reason", "unknown")
        path = data.get("path", "")
        parts = [f"Read file error: {reason}"]
        if path:
            display_path = path if len(path) <= 60 else f"...{path[-57:]}"
            parts.append(f"path={display_path}")
        return " | ".join(parts)

    # Generic fallback: use event_type but try to extract key info from data
    if isinstance(data, dict):
        # Try common keys that might contain useful info
        for key in ["reason", "error", "title", "description"]:
            if key in data and data[key]:
                return f"{event_type}: {data[key]}"

    return event_type


async def _resolve_link_fix_execution_reference(context: Any, execution_id: Optional[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    alias_value = execution_id if isinstance(execution_id, str) else ""
    alias_token = alias_value.strip().lower()
    if alias_token in {"", "current", "active", "session"}:
        authoritative = resolve_context_authoritative_session_key(context)
        if isinstance(authoritative, str) and authoritative.strip():
            execution_id = authoritative.strip()
        else:
            execution_id = str(getattr(context, "execution_id", "") or "").strip()
    if not isinstance(execution_id, str) or not execution_id.strip():
        return None, "execution_id is required and no active execution/session context is available"

    scope = build_reference_scope(context)
    resolution = resolve_reference(execution_id, "execution_id", scope)
    if not resolution.ok and resolution.compatibility_hint != "potential_entry_reference_requires_storage_lookup":
        return None, (
            "execution_id does not match active execution context "
            "(must be current/parent execution_id, the active session key, or a Scribe entry id)"
        )

    if resolution.ok:
        if resolution.source == "runtime_transport_session":
            return None, (
                "execution_id does not match active execution context "
                "(transport session identifiers are not accepted; use current/parent execution_id, "
                "authoritative session key, or a Scribe entry id)"
            )
        if resolution.kind not in {"execution", "parent_execution", "session", "authoritative_session_key", "entry"}:
            return None, (
                "execution_id does not match active execution context "
                "(must be current/parent execution_id, the active session key, or a Scribe entry id)"
            )
        return {
            "raw": execution_id,
            "kind": resolution.kind,
            "source": resolution.source,
            "value": resolution.resolved_value or execution_id,
            "entry_proven": False,
        }, None

    repo_root, project_name, _ownership_meta = _active_repo_project_authority(context, None)
    backend = getattr(server_module, "storage_backend", None)
    if backend is None or not repo_root or not project_name:
        return None, (
            "execution_id does not match active execution context "
            "(must be current/parent execution_id, the active session key, or a Scribe entry id)"
        )
    repo_id = backend.compute_repo_id(repo_root)
    entry = await backend.fetch_entry_by_id(
        entry_id=execution_id.strip(),
        repo_id=repo_id,
        project_name=project_name,
    )
    if not isinstance(entry, dict):
        return None, (
            "execution_id does not match active execution context "
            "(must be current/parent execution_id, the active session key, or a Scribe entry id)"
        )
    return {
        "raw": execution_id,
        "kind": "entry",
        "source": "storage_scope_lookup",
        "value": execution_id.strip(),
        "entry_proven": True,
        "scope_repo_id": repo_id,
        "scope_project_name": project_name,
    }, None


def _active_repo_project_authority(context: Any, fallback_project_name: Optional[str] = None) -> tuple[Optional[str], Optional[str], dict[str, Any]]:
    resolved_scope = getattr(context, "resolved_scope", None)
    resolved_repo_root = getattr(resolved_scope, "repo_root", None)
    resolved_project_name = getattr(resolved_scope, "project_name", None)
    repo_root = resolved_repo_root if isinstance(resolved_repo_root, str) and resolved_repo_root.strip() else getattr(context, "repo_root", None)
    project_name = resolved_project_name if isinstance(resolved_project_name, str) and resolved_project_name.strip() else fallback_project_name

    provenance = getattr(resolved_scope, "provenance", None)
    ownership_meta = {
        "trust_level": getattr(resolved_scope, "trust_level", None),
        "resolution_source": getattr(resolved_scope, "resolution_source", None),
        "repo_root_provenance": getattr(provenance, "repo_root", None),
        "project_name_provenance": getattr(provenance, "project_name", None),
    }
    return (
        str(repo_root).strip() if isinstance(repo_root, str) and repo_root.strip() else None,
        str(project_name).strip() if isinstance(project_name, str) and project_name.strip() else None,
        ownership_meta,
    )


async def _register_case_registry_ownership(
    *,
    context: Any,
    case_id: str,
    case_type: str,
    project_name: str,
    doc_type: str,
    doc_name: str,
    doc_path: str,
    title: str,
    status: str,
    severity: Optional[str],
    source_tool: str,
) -> tuple[bool, Optional[str], Optional[dict[str, Any]]]:
    backend = getattr(server_module, "storage_backend", None)
    if backend is None or not hasattr(backend, "upsert_case_registry_record"):
        return False, "shared case registry backend is unavailable", None

    repo_root, authority_project_name, ownership_meta = _active_repo_project_authority(
        context, fallback_project_name=project_name
    )
    if not repo_root:
        return False, "unable to resolve authoritative repo_root for case registry ownership", None
    if not authority_project_name:
        return False, "unable to resolve authoritative project_name for case registry ownership", None

    execution_meta = {
        "execution_id": getattr(context, "execution_id", None),
        "parent_execution_id": getattr(context, "parent_execution_id", None),
        "authoritative_session_key": getattr(context, "authoritative_session_key", None),
        "stable_session_id": getattr(context, "stable_session_id", None),
    }
    existing_record = None
    fetch_record = getattr(backend, "fetch_case_registry_record", None)
    if callable(fetch_record):
        try:
            existing_record = await fetch_record(
                case_id=case_id,
                repo_root=repo_root,
                project_name=authority_project_name,
            )
        except Exception:
            existing_record = None

    upsert_kwargs = doc_utils.build_case_registry_upsert_kwargs(
        existing_record=existing_record,
        overrides={
            "case_id": case_id,
            "case_type": case_type,
            "project_name": authority_project_name,
            "repo_root": repo_root,
            "doc_type": doc_type,
            "doc_name": doc_name,
            "doc_path": doc_path,
            "title": title,
            "status": status,
            "severity": severity,
            "source_tool": source_tool,
        },
        metadata_overrides={
            "ownership": ownership_meta,
            "execution_provenance": execution_meta,
            "registration_event": "case_opened",
        },
    )
    if upsert_kwargs is None:
        return False, "unable to build case registry payload for ownership registration", None
    await backend.upsert_case_registry_record(**upsert_kwargs)
    return True, None, {
        "case_id": upsert_kwargs["case_id"],
        "case_type": upsert_kwargs["case_type"],
        "doc_name": upsert_kwargs["doc_name"],
        "doc_path": upsert_kwargs["doc_path"],
        "project_name": upsert_kwargs["project_name"],
    }


async def _completeness_gate_blockers(
    *,
    manage_docs_tool: Any,
    agent: str,
    doc_name: str,
    landing_status: str,
) -> Optional[list[str]]:
    """Return blocking-warning messages if a fix-terminal close is incomplete.

    F5 enforcement: closing a case (fix-terminal ``landing_status``) is only
    legitimate once the report has real content in its required sections. The
    completeness signal is read from the canonical content-quality reader —
    ``manage_docs(action="quality_check")`` — not a parallel parser. An
    incomplete/scaffold report (``[UNFILLED]`` placeholders in
    symptoms/root_cause/fix) surfaces as ``quality_status == "fail"`` with
    ``readiness_blockers`` (e.g. ``SCF_PLACEHOLDER_BRACKET``).

    Returns:
        - ``None`` when the close is allowed: the transition is not fix-terminal,
          the report doc is unknown, the quality reader is inconclusive (soft
          gate — fail open so a transient/unavailable reader never traps a real
          close), or the report passes.
        - a non-empty ``list[str]`` of teaching messages when the close must be
          refused because the quality reader affirmatively reports blockers.
    """
    # Only fix-terminal closes are gated. Non-fix terminal statuses
    # (wontfix/duplicate/false_positive/mitigated) and non-terminal statuses
    # (proposed/open/...) leave a case in a state that does not assert "this was
    # fixed", so a complete fix narrative is not required.
    if doc_utils.resolved_case_close_status(landing_status) != "closed":
        return None

    target_doc = str(doc_name or "").strip()
    if not target_doc:
        # Without a resolvable report doc there is nothing to read; do not trap
        # the close on a missing reference (soft gate).
        return None

    try:
        quality_result = await manage_docs_tool(
            agent=agent,
            action="quality_check",
            doc_name=target_doc,
            dry_run=True,
        )
    except Exception:
        # The quality reader is advisory at this boundary; an exception inside it
        # must not raise out of link_fix (MCP tools return error dicts, never
        # raise) and must not block a legitimate close.
        return None

    if not isinstance(quality_result, dict):
        return None

    # Affirmative-failure only: block when the reader explicitly reports a failing
    # quality status with readiness blockers. Anything inconclusive (no
    # quality_status, ok=False, pass/warn) falls open.
    if str(quality_result.get("quality_status") or "").lower() != "fail":
        return None

    blockers = quality_result.get("readiness_blockers")
    if not isinstance(blockers, list) or not blockers:
        return None

    messages: list[str] = []
    for blocker in blockers[:5]:
        if not isinstance(blocker, dict):
            continue
        code = str(blocker.get("code") or "").strip()
        detail = str(blocker.get("message") or blocker.get("suggested_repair") or "").strip()
        if code and detail:
            messages.append(f"{code}: {detail}")
        elif code:
            messages.append(code)
        elif detail:
            messages.append(detail)
    if not messages:
        # quality_status=="fail" with opaque blockers — still a real failure.
        messages.append("Report has unresolved scaffold/placeholder content in required sections.")
    return messages


async def _register_case_registry_fix_link(
    *,
    case_record: Any,
    context: Any,
    case_id: str,
    execution_id: str,
    artifact_ref: str,
    normalized_execution_ref: Optional[dict[str, Any]] = None,
    normalized_artifact_ref: Optional[dict[str, Any]] = None,
    landing_status: str,
    doc_binding: CanonicalDocBinding | None = None,
) -> tuple[bool, Optional[str], Any | None]:
    backend = getattr(server_module, "storage_backend", None)
    if backend is None or not hasattr(backend, "upsert_case_registry_record"):
        return False, "shared case registry backend is unavailable", None

    execution_meta = {
        "execution_id": getattr(context, "execution_id", None),
        "parent_execution_id": getattr(context, "parent_execution_id", None),
        "authoritative_session_key": getattr(context, "authoritative_session_key", None),
        "stable_session_id": getattr(context, "stable_session_id", None),
    }
    # Canonical lifecycle vocabulary shared with list_open_cases (doc_utils). A
    # non-fix terminal status (wontfix/duplicate/false_positive/mitigated) is
    # preserved as the recorded case status so the closure reason survives; a fix
    # terminal status collapses to "closed"; a non-terminal status leaves the case
    # open (close_status is None).
    close_status = doc_utils.resolved_case_close_status(landing_status)
    closes_case = close_status is not None
    metadata_overrides: dict[str, Any] = {
        "execution_provenance": execution_meta,
        "fix_link": {
            "execution_id": execution_id,
            "artifact_ref": artifact_ref,
            "execution_ref": normalized_execution_ref or {"value": execution_id},
            "artifact_ref_meta": normalized_artifact_ref or {"value": artifact_ref},
            "landing_status": landing_status,
        },
    }
    if doc_binding is not None:
        metadata_overrides["doc_binding"] = doc_binding_to_metadata(doc_binding)

    upsert_kwargs = doc_utils.build_case_registry_upsert_kwargs(
        existing_record=case_record,
        overrides={"case_id": case_id, "status": close_status},
        metadata_overrides=metadata_overrides,
    )
    if upsert_kwargs is None:
        return False, "unable to build case registry payload for fix link update", None
    upserted_record = await backend.upsert_case_registry_record(**upsert_kwargs)
    return True, None, upserted_record


async def _fetch_case_registry_record_after_fix(
    *,
    context: Any,
    case_id: str,
) -> Any | None:
    backend = getattr(server_module, "storage_backend", None)
    if backend is None or not hasattr(backend, "fetch_case_registry_record"):
        return None
    active_repo_root, _, _ = _active_repo_project_authority(context)
    active_project_name = getattr(getattr(context, "resolved_scope", None), "project_name", None)
    try:
        return await backend.fetch_case_registry_record(
            case_id=case_id,
            repo_root=active_repo_root,
            project_name=active_project_name,
        )
    except Exception:
        return None


def _doc_binding_for_case_record(case_record: Any, *, case_id: str) -> CanonicalDocBinding | None:
    metadata = getattr(case_record, "metadata", None)
    doc_path = str(getattr(case_record, "doc_path", "") or "")
    binding = doc_binding_from_metadata(
        metadata if isinstance(metadata, dict) else None,
        fallback_case_id=case_id,
        fallback_doc_path=doc_path or None,
    )
    if binding is not None:
        return binding
    if not doc_path:
        return None
    return build_canonical_doc_binding(
        case_id,
        doc_path,
        {},
        preferred_doc_name=str(getattr(case_record, "doc_name", "") or case_id),
    )


def _apply_lifecycle_readback(
    response: dict[str, Any],
    lifecycle: Any,
    *,
    preserve_next_step: bool = False,
) -> None:
    lifecycle_dict = lifecycle.to_dict()
    response["lifecycle"] = dict(lifecycle_dict)
    for field in (
        "fix_link_recorded",
        "case_closed",
        "registry_status_before",
        "registry_status_after",
        "landing_status_terminal",
        "closure_reason",
        "doc_binding",
        "last_fix_link",
    ):
        response[field] = lifecycle_dict[field]
    if preserve_next_step:
        return
    next_step = str(lifecycle_dict.get("next_step") or "")
    if lifecycle.case_closed:
        response["next_step"] = "No follow-up required."
        return
    if lifecycle.fix_link_recorded:
        next_step = (
            f"{next_step} The fix link was recorded, but the case remains open; "
            "use a terminal landing_status such as merged or resolved when closure is ready."
        )
        response["lifecycle"]["next_step"] = next_step
    response["next_step"] = next_step


def _case_record_for_lifecycle(case_record: Any, *, fallback_status: str | None = None) -> Any:
    if hasattr(case_record, "status"):
        return case_record
    return SimpleNamespace(
        case_id=str(getattr(case_record, "case_id", "") or ""),
        case_type=str(getattr(case_record, "case_type", "") or ""),
        status=fallback_status,
        metadata=getattr(case_record, "metadata", None),
    )


def _landing_status_for_lifecycle(landing_status: str, current_status: str | None) -> str:
    normalized = doc_utils.normalize_case_status(landing_status)
    allowed_values = doc_utils.CASE_OPEN_STATUS_VALUES | doc_utils.CASE_CLOSED_STATUS_VALUES
    if normalized in allowed_values:
        return landing_status
    normalized_current = doc_utils.normalize_case_status(current_status)
    if normalized_current in doc_utils.CASE_OPEN_STATUS_VALUES:
        return normalized_current
    return "open"


async def _load_and_authorize_case_registry_record(
    *,
    context: Any,
    case_id: str,
) -> tuple[Optional[Any], Optional[str]]:
    backend = getattr(server_module, "storage_backend", None)
    if backend is None or not hasattr(backend, "fetch_case_registry_record"):
        return None, "shared case registry backend is unavailable"

    active_repo_root, _, _ = _active_repo_project_authority(context)
    if not active_repo_root:
        return None, "unable to resolve authoritative repo_root for case ownership validation"
    active_project_name = getattr(getattr(context, "resolved_scope", None), "project_name", None)

    case_record = await backend.fetch_case_registry_record(
        case_id=case_id,
        repo_root=active_repo_root,
        project_name=active_project_name,
    )
    if case_record is None:
        return None, (
            f"case_id '{case_id}' is not registered in the shared case registry "
            "for the active repo/project scope"
        )

    record_repo_root = str(getattr(case_record, "repo_root", "") or "").strip()
    if not record_repo_root:
        return None, f"shared case registry record for '{case_id}' is missing repo ownership"

    active_resolved = str(Path(active_repo_root).expanduser().resolve())
    record_resolved = str(Path(record_repo_root).expanduser().resolve())
    if active_resolved != record_resolved:
        return None, (
            "repo ownership mismatch for case_id "
            f"'{case_id}' (active repo='{active_resolved}', case repo='{record_resolved}')"
        )

    return case_record, None


@app.tool(**additive_local_tool(title="Append Sentinel Event", tags=("sentinel", "logs", "write")))
async def append_event(
    agent: str,
    message: Optional[str] = None,
    status: Optional[str] = None,
    emoji: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    timestamp_utc: Optional[str] = None,
    items: Optional[Any] = None,
    items_list: Optional[list[Dict[str, Any]]] = None,
    auto_split: bool = True,
    split_delimiter: str = "\n",
    stagger_seconds: int = 1,
    # Legacy parameters (supported for backward compatibility)
    event_type: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append a general sentinel event to sentinel.jsonl (append_entry-compatible args)."""
    context = _get_context()

    if context.mode == "project":
        from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
        payload_message = message
        if not payload_message and isinstance(data, dict):
            payload_message = data.get("message") or data.get("event") or None
        if not payload_message:
            # Build descriptive message from event_type and data instead of terse event_type
            payload_message = _build_descriptive_message(event_type, data)
        meta_payload = meta if isinstance(meta, dict) else {}
        if isinstance(data, dict):
            meta_payload = {**meta_payload, **data}
        return await append_entry_tool(
            message=payload_message or "",
            status=status or event_type or "info",
            emoji=emoji,
            agent=agent,
            meta=meta_payload,
            timestamp_utc=timestamp_utc,
            items=items,
            items_list=items_list,
            auto_split=auto_split,
            split_delimiter=split_delimiter,
            stagger_seconds=stagger_seconds,
        )

    def _emit(payload: Dict[str, Any], resolved_event_type: str) -> None:
        append_sentinel_event(
            context,
            event_type=resolved_event_type,
            data=payload,
            log_type="sentinel",
            include_md=True,
        )

    if event_type is not None or data is not None:
        payload = data if isinstance(data, dict) else {}
        resolved_event_type = event_type or "info"
        _emit(payload, resolved_event_type)
        return {"ok": True, "event_type": resolved_event_type}

    bulk_items: list[Dict[str, Any]] = []
    if isinstance(items_list, list):
        bulk_items = items_list
    elif items is not None:
        if isinstance(items, list):
            bulk_items = items
        elif isinstance(items, str):
            try:
                import json
                parsed = json.loads(items)
                if isinstance(parsed, list):
                    bulk_items = parsed
            except Exception:
                bulk_items = []

    if bulk_items:
        written = 0
        for entry in bulk_items:
            if not isinstance(entry, dict):
                continue
            entry_message = entry.get("message")
            if not entry_message:
                continue
            payload = {
                "message": entry_message,
                "status": entry.get("status"),
                "emoji": entry.get("emoji"),
                "agent": entry.get("agent"),
                "meta": entry.get("meta") if isinstance(entry.get("meta"), dict) else None,
                "timestamp_utc_override": entry.get("timestamp_utc"),
            }
            resolved_event_type = entry.get("status") or "info"
            _emit(payload, resolved_event_type)
            written += 1
        return {"ok": True, "event_type": "bulk", "written_count": written}

    if not message:
        return {"ok": False, "error": "message or items are required"}

    if auto_split and split_delimiter and split_delimiter in message:
        parts = [part for part in message.split(split_delimiter) if part]
    else:
        parts = [message]

    written = 0
    for part in parts:
        payload = {
            "message": part,
            "status": status,
            "emoji": emoji,
            "agent": agent,
            "meta": meta if isinstance(meta, dict) else None,
            "timestamp_utc_override": timestamp_utc,
        }
        resolved_event_type = status or "info"
        _emit(payload, resolved_event_type)
        written += 1

    return {"ok": True, "event_type": status or "info", "written_count": written}


# ---------------------------------------------------------------------------
# Shared case-opening implementation (F4)
#
# ``open_bug`` and ``open_security`` were ~290 lines of near-duplicate logic
# differing only in a handful of literals (case kind, status strings, default
# severity, security flag, doc_type, anchor map, template field set). The
# duplication doubled maintenance surface and, worse, ``open_security`` scored
# completeness against the BUG field set — so any security-only field would be
# silently mis-scored. ``_open_case`` is the single implementation both tools
# call with their constants; completeness is scored against ``template_fields``
# so the source is per-case-type.
# ---------------------------------------------------------------------------
async def _open_case(
    *,
    kind: str,
    case_type: str,
    doc_type: str,
    doc_category: str,
    report_artifact_type: str,
    report_key: str,
    label: str,
    message_prefix: str,
    append_status: str,
    default_severity: str,
    security_event: bool,
    template_fields: list[str],
    anchor_map: dict[str, str],
    sentinel_event_type: str,
    preview_tool_name: str,
    open_tool_name: str,
    agent: str,
    title: str,
    symptoms: str,
    category: str,
    affected_paths: Optional[list[str]] = None,
    expected_behaviour: Optional[str] = None,
    steps_to_reproduce: Optional[list[str]] = None,
    root_cause: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    severity: Optional[str] = None,
    component: Optional[str] = None,
    environment: Optional[str] = None,
    customer_impact: Optional[str] = None,
    preview: bool = False,
) -> Dict[str, Any]:
    """Open a BUG or SECURITY case. See ``open_bug``/``open_security`` for the
    public contracts; this is their shared body keyed on ``kind`` constants."""
    context = _get_context()
    if not category or not category.strip():
        return _operator_envelope(
            ok=False,
            mode=str(getattr(context, "mode", "") or "unknown"),
            warnings=["category is required"],
            next_step=f"Provide a non-empty 'category' value and retry {open_tool_name}.",
            error="category is required",
        )

    # Project mode: route through append_entry AND create a report doc.
    if context.mode == "project":
        if preview:
            try:
                case_id = _preview_case_id_for_project(kind, context)
            except Exception as exc:
                message = f"Failed to preview {kind} case ID: {exc}"
                return _operator_envelope(
                    ok=False,
                    mode="project",
                    warnings=[message],
                    next_step="Verify execution context repo binding (repo_root/project scope) and retry preview.",
                    error=message,
                )
            return _operator_envelope(
                ok=True,
                mode="project",
                case_id=case_id,
                next_step=f"Preview only. Run {open_tool_name} with preview=False to register and create docs.",
                preview=True,
            )

        from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
        from scribe_mcp.tools.manage_docs import manage_docs as manage_docs_tool

        message = f"{message_prefix} {title}: {symptoms}"
        meta: Dict[str, Any] = {
            "case_type": case_type,
            "title": title,
            "symptoms": symptoms,
            "affected_paths": affected_paths or [],
            "landing_status": "proposed",
        }
        if security_event:
            meta["security_event"] = "1"  # Triggers auto-tee to security log

        result = await append_entry_tool(
            message=message,
            status=append_status,
            agent=agent,
            meta=meta,
            format="structured",  # Returns plain dict, not MCP-wrapped
        )

        if not result.get("ok"):
            message = str(result.get("error", "append_entry failed"))
            return _operator_envelope(
                ok=False,
                mode="project",
                warnings=[message],
                next_step=f"Resolve append_entry failure and retry {open_tool_name}.",
                error=message,
            )

        # Generate case ID after entry is written (so paths are resolvable).
        try:
            case_id = _next_case_id_for_project(kind, result)
        except Exception as exc:
            message = f"Failed to allocate {kind} case ID: {exc}"
            return _operator_envelope(
                ok=False,
                mode="project",
                warnings=[message],
                next_step=f"Validate repo docs/counter state and retry {open_tool_name}.",
                error=message,
                entry_id=str(result.get("id", "")),
                path=str(result.get("path", "")),
                project_name=str(result.get("project_name", "")),
            )

        # Ensure fresh case IDs are immediately queryable by bare ID.
        registration_meta: Dict[str, Any] = {
            "case_type": case_type,
            "case_id": case_id,
            "registration_event": "case_opened",
            "title": title,
        }
        if security_event:
            registration_meta["security_event"] = "1"
        registration_result = await append_entry_tool(
            message=f"[CASE REGISTERED] {case_id}",
            status=append_status,
            agent=agent,
            meta=registration_meta,
            format="structured",
        )
        if not registration_result.get("ok"):
            message = str(registration_result.get("error", "case registration append_entry failed"))
            return _operator_envelope(
                ok=False,
                mode="project",
                case_id=str(case_id),
                warnings=[message],
                next_step="Fix registration append failure so case_id is queryable, then retry.",
                error=message,
                entry_id=str(result.get("id", "")),
                path=str(result.get("path", "")),
                project_name=str(result.get("project_name", "")),
            )

        # Build metadata (used for both doc creation and completeness scoring).
        case_metadata = {
            "doc_type": doc_type,
            "category": category,
            "slug": case_id,
            "title": title,
            "case_id": case_id,
            "symptoms": symptoms,
            "summary_long": symptoms,  # Map to template field
            "actual_behavior": symptoms,  # Map to template field
            "affected_paths": affected_paths or [],
            "affected_areas": affected_paths or [],  # Map to template field
            "reporter": agent,  # Map to template field
            "status": "INVESTIGATING",  # Default status
            "severity": severity if severity is not None else default_severity,
            # NEW parameter mappings (use [UNFILLED] for missing values):
            "expected_behavior": expected_behaviour if expected_behaviour is not None else "[UNFILLED]",
            "reproduction_steps": steps_to_reproduce if steps_to_reproduce is not None else ["[UNFILLED]"],
            "root_cause": root_cause if root_cause is not None else "[UNFILLED]",
            "immediate_actions": resolution_notes if resolution_notes is not None else "[UNFILLED]",
            "component": component if component is not None else "[UNFILLED]",
            "environment": environment if environment is not None else "[UNFILLED]",
            "customer_impact": customer_impact if customer_impact is not None else "[UNFILLED]",
        }

        doc_result = await manage_docs_tool(
            agent=agent,
            action="create",
            metadata=case_metadata,
        )

        # Check if document creation succeeded
        if not isinstance(doc_result, dict) or not doc_result.get("ok"):
            error_msg = doc_result.get("error", "Unknown error") if isinstance(doc_result, dict) else "manage_docs returned non-dict"
            message = f"{label} report document creation failed: {error_msg}"
            return _operator_envelope(
                ok=False,
                mode="project",
                case_id=str(case_id),
                warnings=[message],
                next_step=f"Fix manage_docs(create) failure and retry {open_tool_name} for this case.",
                error=message,
                entry_id=str(result.get("id", "")),
                path=str(result.get("path", "")),
                project_name=str(result.get("project_name", "")),
            )

        registry_result = await _register_case_registry_ownership(
            context=context,
            case_id=case_id,
            case_type=case_type,
            project_name=str(result.get("project_name", "")),
            doc_type=doc_type,
            doc_name=case_id,
            doc_path=str(doc_result.get("path", "")),
            title=title,
            status="open",
            severity=case_metadata.get("severity"),
            source_tool=open_tool_name,
        )
        registry_ok = registry_result[0]
        registry_error = registry_result[1]
        case_registry_summary = registry_result[2] if len(registry_result) > 2 else None
        if not registry_ok:
            message = f"Case registry ownership registration failed: {registry_error}"
            return _operator_envelope(
                ok=False,
                mode="project",
                case_id=str(case_id),
                warnings=[message],
                next_step="Ensure project ownership context is bound and shared registry backend is available.",
                error=message,
                entry_id=str(result.get("id", "")),
                path=str(result.get("path", "")),
                project_name=str(result.get("project_name", "")),
            )

        # Calculate completeness score against the case-type-specific field set.
        filled_sections = []
        unfilled_sections = []
        for field in template_fields:
            value = case_metadata.get(field)
            if value and value != "[UNFILLED]" and value != ["[UNFILLED]"]:
                filled_sections.append(field)
            else:
                unfilled_sections.append(field)

        total_fields = len(template_fields)
        filled_count = len(filled_sections)
        percentage = int((filled_count / total_fields) * 100) if total_fields > 0 else 0

        report_path = str(doc_result.get("path", ""))
        return _operator_envelope(
            ok=True,
            mode="project",
            case_id=str(case_id),
            artifacts=[{"type": report_artifact_type, "ref": report_path}],
            next_step=(
                f"Use manage_docs replace_section with doc_name='{case_id}' to complete remaining fields: "
                f"{_format_unfilled_guidance(unfilled_sections, anchor_map, 3)}."
            ),
            entry_id=str(result.get("id", "")),
            path=str(result.get("path", "")),
            project_name=str(result.get("project_name", "")),
            doc_name=str(case_id),
            doc_path=report_path,
            doc_category=doc_category,
            case_registry=case_registry_summary
            or {
                "case_id": str(case_id),
                "case_type": case_type,
                "doc_name": str(case_id),
                "doc_path": report_path,
                "project_name": str(result.get("project_name", "")),
            },
            completeness={
                "score": f"{filled_count}/{total_fields}",
                "percentage": percentage,
                "filled_sections": filled_sections,
                "unfilled_sections": unfilled_sections,
                "field_section_anchors": {
                    field: anchor_map.get(field, "description")
                    for field in unfilled_sections
                },
            },
            action_required=(
                f"{label} report {percentage}% complete. "
                f"Use manage_docs(agent='{agent}', action='replace_section', "
                f"doc_name='{case_id}', section='<section_anchor>', content='...') "
                f"(doc_path '{report_path}' is also a governed alias) "
                f"to fill remaining fields: "
                f"{_format_unfilled_guidance(unfilled_sections, anchor_map, 5)}"
            ),
            **{report_key: report_path},
        )

    # Sentinel mode: original behavior
    if preview:
        sentinel_day = getattr(context, "sentinel_day", None)
        if not isinstance(sentinel_day, str) or not sentinel_day.strip():
            sentinel_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return _operator_envelope(
            ok=True,
            mode="sentinel",
            case_id=f"{kind}-{sentinel_day}-PREVIEW",
            next_step=f"Preview only. Run {open_tool_name} with preview=False to append sentinel case event.",
            preview=True,
        )

    case_id = append_case_event(
        context,
        kind=kind,
        event_type=sentinel_event_type,
        data={
            "title": title,
            "symptoms": symptoms,
            "affected_paths": affected_paths or [],
            "landing_status": "proposed",
        },
        include_md=True,
    )
    return _operator_envelope(
        ok=True,
        mode="sentinel",
        case_id=case_id,
        next_step="Case opened in sentinel mode. Run link_fix when a fix artifact is ready.",
    )


@app.tool(
    **additive_local_tool(title="Open Bug Case", tags=("bugs", "sentinel", "write")),
    input_schema=_OPEN_BUG_INPUT_SCHEMA,
)
async def open_bug(
    agent: str,
    title: str,
    symptoms: str,
    category: str,
    affected_paths: Optional[list[str]] = None,
    # NEW optional parameters for richer bug reports:
    expected_behaviour: Optional[str] = None,
    steps_to_reproduce: Optional[list[str]] = None,
    root_cause: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    severity: Optional[str] = None,
    component: Optional[str] = None,
    environment: Optional[str] = None,
    customer_impact: Optional[str] = None,
    preview: bool = False,
) -> Dict[str, Any]:
    """Open a BUG case with per-day stable ID and create a detailed bug report document.

    Args:
        agent: Agent identifier
        title: Short bug title
        symptoms: Description of the bug symptoms
        category: Bug category for organization (e.g., 'auth', 'api', 'ui')
        affected_paths: Optional list of affected file paths
        expected_behaviour: What should happen (populates Expected Behaviour section)
        steps_to_reproduce: List of steps to reproduce the bug (populates Steps to Reproduce)
        root_cause: Suspected or confirmed root cause (populates Investigation section)
        resolution_notes: Immediate actions or fix notes (populates Resolution Plan)
        severity: Bug severity level (low/medium/high/critical), defaults to 'medium'
        component: Affected component or subsystem name
        environment: Environment where bug occurs (local/staging/production)
        customer_impact: Description of impact on users/customers
    """
    return await _open_case(
        kind="BUG",
        case_type="bug",
        doc_type="bug",
        doc_category="bugs",
        report_artifact_type="bug_report",
        report_key="bug_report",
        label="Bug",
        message_prefix="[BUG]",
        append_status="bug",
        default_severity="medium",
        security_event=False,
        template_fields=_BUG_TEMPLATE_FIELDS,
        anchor_map=_BUG_FIELD_SECTION_ANCHORS,
        sentinel_event_type="bug_opened",
        preview_tool_name="open_bug",
        open_tool_name="open_bug",
        agent=agent,
        title=title,
        symptoms=symptoms,
        category=category,
        affected_paths=affected_paths,
        expected_behaviour=expected_behaviour,
        steps_to_reproduce=steps_to_reproduce,
        root_cause=root_cause,
        resolution_notes=resolution_notes,
        severity=severity,
        component=component,
        environment=environment,
        customer_impact=customer_impact,
        preview=preview,
    )


@app.tool(
    **additive_local_tool(title="Open Security Case", tags=("security", "sentinel", "write")),
    input_schema=_OPEN_SECURITY_INPUT_SCHEMA,
)
async def open_security(
    agent: str,
    title: str,
    symptoms: str,
    category: str,
    affected_paths: Optional[list[str]] = None,
    # NEW optional parameters for richer security reports:
    expected_behaviour: Optional[str] = None,
    steps_to_reproduce: Optional[list[str]] = None,
    root_cause: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    severity: Optional[str] = None,
    component: Optional[str] = None,
    environment: Optional[str] = None,
    customer_impact: Optional[str] = None,
    preview: bool = False,
) -> Dict[str, Any]:
    """Open a SECURITY case with per-day stable ID and create a detailed security report document.

    Args:
        agent: Agent identifier
        title: Short security issue title
        symptoms: Description of the security issue
        category: Category for organization (e.g., 'auth', 'injection', 'xss')
        affected_paths: Optional list of affected file paths
        expected_behaviour: What should happen (populates Expected Behaviour section)
        steps_to_reproduce: List of steps to reproduce the security issue (populates Steps to Reproduce)
        root_cause: Suspected or confirmed root cause (populates Investigation section)
        resolution_notes: Immediate actions or fix notes (populates Resolution Plan)
        severity: Security severity level (low/medium/high/critical), defaults to 'high'
        component: Affected component or subsystem name
        environment: Environment where issue occurs (local/staging/production)
        customer_impact: Description of impact on users/customers
    """
    return await _open_case(
        kind="SEC",
        case_type="security",
        doc_type="security",
        doc_category="security",
        report_artifact_type="security_report",
        report_key="security_report",
        label="Security",
        message_prefix="[SECURITY]",
        append_status="warn",
        default_severity="high",
        security_event=True,
        template_fields=_SECURITY_TEMPLATE_FIELDS,
        anchor_map=_SECURITY_FIELD_SECTION_ANCHORS,
        sentinel_event_type="security_opened",
        preview_tool_name="open_security",
        open_tool_name="open_security",
        agent=agent,
        title=title,
        symptoms=symptoms,
        category=category,
        affected_paths=affected_paths,
        expected_behaviour=expected_behaviour,
        steps_to_reproduce=steps_to_reproduce,
        root_cause=root_cause,
        resolution_notes=resolution_notes,
        severity=severity,
        component=component,
        environment=environment,
        customer_impact=customer_impact,
        preview=preview,
    )


@app.tool(
    **additive_local_tool(title="Link Fix Artifact", tags=("bugs", "security", "traceability", "write")),
    input_schema=_LINK_FIX_INPUT_SCHEMA,
)
async def link_fix(
    agent: str,
    case_id: str,
    execution_id: str = "current",
    artifact_ref: str = "",
    landing_status: str = "",
) -> Dict[str, Any]:
    """Link a fix artifact to a BUG/SEC case."""
    context = _get_context()
    if not isinstance(execution_id, str):
        execution_id = str(execution_id or "")
    execution_id = execution_id.strip() or "current"
    artifact_ref = str(artifact_ref or "").strip()
    landing_status = str(landing_status or "").strip()
    if not artifact_ref:
        message = "artifact_ref is required"
        return _operator_envelope(
            ok=False,
            mode=str(getattr(context, "mode", "") or "unknown"),
            case_id=str(case_id or ""),
            warnings=[message],
            next_step="Provide artifact_ref and retry link_fix.",
            error=message,
        )
    if not landing_status:
        message = "landing_status is required"
        return _operator_envelope(
            ok=False,
            mode=str(getattr(context, "mode", "") or "unknown"),
            case_id=str(case_id or ""),
            warnings=[message],
            next_step="Provide landing_status and retry link_fix.",
            error=message,
        )
    normalized_artifact_ref = _normalize_artifact_reference(artifact_ref)

    resolved_execution, execution_id_error = await _resolve_link_fix_execution_reference(context, execution_id)
    if execution_id_error:
        return _operator_envelope(
            ok=False,
            mode=str(getattr(context, "mode", "") or "unknown"),
            case_id=str(case_id or ""),
            warnings=[execution_id_error],
            next_step=(
                "Run link_fix with the current/parent execution_id, active session key, or a Scribe entry id."
            ),
            error=execution_id_error,
        )

    case_id_upper = case_id.upper()
    if case_id_upper.startswith("BUG-"):
        event_type = "bug_fix_linked"
        kind = "BUG"
    elif case_id_upper.startswith("SEC-"):
        event_type = "security_fix_linked"
        kind = "SEC"
    else:
        message = "case_id must start with BUG- or SEC-"
        return _operator_envelope(
            ok=False,
            mode=str(getattr(context, "mode", "") or "unknown"),
            case_id=str(case_id or ""),
            warnings=[message],
            next_step="Provide a valid BUG-* or SEC-* case_id and retry link_fix.",
            error=message,
        )

    # Project mode: route through append_entry
    if context.mode == "project":
        case_record, ownership_error = await _load_and_authorize_case_registry_record(
            context=context,
            case_id=case_id,
        )
        if ownership_error:
            return _operator_envelope(
                ok=False,
                mode="project",
                case_id=str(case_id),
                warnings=[ownership_error],
                next_step=(
                    "Use a case_id registered to this repo/session context or reopen the case in the active project."
                ),
                error=ownership_error,
            )

        from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
        from scribe_mcp.tools.manage_docs import manage_docs as manage_docs_tool
        import logging as _logging
        _logger = _logging.getLogger(__name__)

        # F5 completeness gate: refuse a fix-terminal close while the report still
        # has scaffold/[UNFILLED] content in its required sections. The case stays
        # OPEN (no registry close, no report mutation) and the operator gets a
        # teaching envelope. Non-fix-terminal/non-terminal landing statuses pass
        # straight through (gate returns None).
        completeness_blockers = await _completeness_gate_blockers(
            manage_docs_tool=manage_docs_tool,
            agent=agent,
            doc_name=str(getattr(case_record, "doc_name", "") or case_id),
            landing_status=landing_status,
        )
        if completeness_blockers:
            block_warning = (
                f"Case {case_id} cannot be closed with landing_status='{landing_status}': "
                "the report is missing required content (symptoms/root_cause/fix). "
                "It remains OPEN."
            )
            gate_response = _operator_envelope(
                ok=True,
                mode="project",
                case_id=str(case_id),
                warnings=[block_warning, *completeness_blockers],
                next_step=(
                    f"Fill the required sections via manage_docs(action='replace_section', doc_name='{case_id}', ...) "
                    "for symptoms/root_cause/fix, then retry link_fix. To close without a fix, use a non-fix "
                    "landing_status (e.g. wontfix/duplicate/false_positive)."
                ),
            )
            gate_response["partial"] = True
            gate_response["completeness_gate"] = {
                "blocked": True,
                "landing_status": landing_status,
                "blockers": list(completeness_blockers),
            }
            gate_response["case_event"] = {"event": "fix_link_blocked_incomplete"}
            return gate_response

        doc_binding = _doc_binding_for_case_record(case_record, case_id=case_id)
        resolved_execution_value = str((resolved_execution or {}).get("value") or execution_id)
        message = f"[FIX LINKED] {case_id}: {artifact_ref} ({landing_status})"
        meta = {
            "case_type": "bug" if kind == "BUG" else "security",
            "case_id": case_id,
            "fix_link": {
                "execution_id": resolved_execution_value,
                "artifact_ref": artifact_ref,
                "execution_ref": resolved_execution or {"value": execution_id},
                "artifact_ref_meta": normalized_artifact_ref,
            },
            "landing_status": landing_status,
        }

        # Add security_event flag for security cases to trigger auto-tee
        if kind == "SEC":
            meta["security_event"] = "1"

        case_event_name = "fix_linked"
        result = await append_entry_tool(
            message=message,
            status="success" if landing_status in ("merged", "landed", "done") else "info",
            agent=agent,
            meta={**meta, "case_event": case_event_name},
            format="structured",  # Returns plain dict, not MCP-wrapped
        )

        if not result.get("ok"):
            message = str(result.get("error", "append_entry failed"))
            return _operator_envelope(
                ok=False,
                mode="project",
                case_id=str(case_id),
                warnings=[message],
                next_step="Resolve append_entry failure and retry link_fix.",
                error=message,
            )

        registry_ok, registry_error, upserted_case_record = await _register_case_registry_fix_link(
            case_record=case_record,
            context=context,
            case_id=case_id,
            execution_id=resolved_execution_value,
            artifact_ref=artifact_ref,
            normalized_execution_ref=resolved_execution,
            normalized_artifact_ref=normalized_artifact_ref,
            landing_status=landing_status,
            doc_binding=doc_binding,
        )
        if not registry_ok:
            message = f"Case registry fix-link update failed: {registry_error}"
            return _operator_envelope(
                ok=False,
                mode="project",
                case_id=str(case_id),
                warnings=[message],
                next_step="Ensure case registry backend is available and retry link_fix.",
                error=message,
            )
        fetched_case_record_after = await _fetch_case_registry_record_after_fix(context=context, case_id=case_id)
        case_record_after = (
            fetched_case_record_after
            if fetched_case_record_after is not None and hasattr(fetched_case_record_after, "status")
            else upserted_case_record
        )

        # Update the bug/security report document with fix reference information.
        # The case_id was registered in project["docs"] when open_bug/open_security was called.
        doc_update_warning: str | None = None
        try:
            # Update the appendix section with fix reference details
            report_doc_name = str(getattr(case_record, "doc_name", "") or case_id)
            appendix_content = (
                f"- **Fix Reference:** {artifact_ref} (execution: {resolved_execution_value})\n"
                f"- **Landing Status:** {landing_status}\n"
                f"- **Fix Linked By:** {agent}\n"
            )
            appendix_result = await manage_docs_tool(
                agent=agent,
                action="replace_section",
                doc_name=report_doc_name,
                section="appendix",
                content=appendix_content,
            )
            if not isinstance(appendix_result, dict) or not appendix_result.get("ok"):
                doc_update_warning = (
                    appendix_result.get("error", "Unknown error")
                    if isinstance(appendix_result, dict)
                    else "manage_docs returned non-dict"
                )
                _logger.warning(
                    "link_fix: failed to update appendix section for %s: %s",
                    report_doc_name,
                    doc_update_warning,
                )
            else:
                # Update the resolution_plan section with landing status
                resolution_content = (
                    f"### Immediate Actions\n"
                    f"Fix landed with status: **{landing_status}**\n\n"
                    f"### Fix Details\n"
                    f"- Artifact: {artifact_ref}\n"
                    f"- Execution ID: {resolved_execution_value}\n"
                )
                resolution_result = await manage_docs_tool(
                    agent=agent,
                    action="replace_section",
                    doc_name=report_doc_name,
                    section="resolution_plan",
                    content=resolution_content,
                )
                if not isinstance(resolution_result, dict) or not resolution_result.get("ok"):
                    doc_update_warning = (
                        resolution_result.get("error", "Could not update resolution_plan")
                        if isinstance(resolution_result, dict)
                        else "manage_docs returned non-dict"
                    )
                    _logger.warning(
                        "link_fix: failed to update resolution_plan for %s: %s",
                        report_doc_name,
                        doc_update_warning,
                    )
        except Exception as exc:
            doc_update_warning = str(exc)
            _logger.warning("link_fix: exception updating doc for %s: %s", case_id, exc)

        response: dict[str, Any] = _operator_envelope(
            ok=True,
            mode="project",
            case_id=str(case_id),
            artifacts=[{"type": "fix_artifact", "ref": str(artifact_ref)}],
            warnings=[],
            next_step="Fix link recorded.",
            entry_id=str(result.get("id", "")),
            path=str(result.get("path", "")),
            project_name=str(result.get("project_name", "")),
        )
        response["resolved_references"] = {
            "execution": dict(resolved_execution or {}),
            "case": {"raw": case_id, "kind": kind.lower(), "source": "case_id_prefix", "value": case_id},
            "artifact": {"raw": artifact_ref, "kind": "artifact", "source": "link_fix_argument", "value": artifact_ref},
            "artifact_meta": dict(normalized_artifact_ref),
        }
        response["case_scope"] = {
            "mode": "project",
            "project_name": str(getattr(case_record, "project_name", "") or ""),
            "project_key": str(
                getattr(case_record, "project_key", None)
                or getattr(case_record, "project_name", "")
                or ""
            ),
            "repo_id": str(getattr(case_record, "repo_id", "") or ""),
        }
        response["case_event"] = {"event": case_event_name}
        response["case_registry"] = {
            "doc_name": str(getattr(case_record, "doc_name", "") or ""),
            "doc_type": str(getattr(case_record, "doc_type", "") or ""),
            "project_name": str(getattr(case_record, "project_name", "") or ""),
        }
        lifecycle_record_before = _case_record_for_lifecycle(case_record)
        lifecycle_record_after = (
            _case_record_for_lifecycle(
                case_record_after,
                fallback_status=getattr(lifecycle_record_before, "status", None),
            )
            if case_record_after is not None
            else None
        )
        lifecycle_landing_status = _landing_status_for_lifecycle(
            landing_status,
            getattr(lifecycle_record_before, "status", None),
        )
        lifecycle = build_link_fix_lifecycle_result(
            case_record_before=lifecycle_record_before,
            case_record_after=lifecycle_record_after,
            landing_status=lifecycle_landing_status,
            fix_link_recorded=True,
            doc_binding=doc_binding,
            doc_update_warning=doc_update_warning,
        )
        _apply_lifecycle_readback(response, lifecycle)
        report_event_name = "report_body_updated"
        if doc_update_warning:
            report_event_name = "fix_link_partial"
            response["warnings"].append(doc_update_warning)
            response["doc_update_warning"] = doc_update_warning
            response["partial"] = True
            response["case_event"] = {"event": report_event_name}
            response["meta"] = {**response.get("meta", {}), "case_event": report_event_name}
            response["next_step"] = (
                f"Fix report updates for {case_id} via manage_docs replace_section (appendix/resolution_plan)."
            )
            _apply_lifecycle_readback(response, lifecycle, preserve_next_step=True)
        else:
            response["case_event"] = {"event": report_event_name}
            response["meta"] = {**response.get("meta", {}), "case_event": report_event_name}
        await append_entry_tool(
            message=f"[CASE REPORT EVENT] {case_id}: {report_event_name}",
            status="info",
            agent=agent,
            meta={
                **meta,
                "case_event": report_event_name,
                "report_event": report_event_name,
            },
            format="structured",
        )
        return response

    # Sentinel mode: original behavior
    append_case_event(
        context,
        kind=kind,
        event_type=event_type,
        data={
            "case_id": case_id,
            "fix_link": {
                "execution_id": execution_id,
                "artifact_ref": artifact_ref,
                "execution_ref": resolved_execution or {"value": execution_id},
                "artifact_ref_meta": normalized_artifact_ref,
            },
            "landing_status": landing_status,
        },
        include_md=True,
    )
    response = _operator_envelope(
        ok=True,
        mode="sentinel",
        case_id=str(case_id),
        artifacts=[{"type": "fix_artifact", "ref": str(artifact_ref)}],
        next_step="Fix link appended in sentinel mode.",
    )
    response["resolved_references"] = {
        "execution": dict(resolved_execution or {}),
        "case": {"raw": case_id, "kind": kind.lower(), "source": "case_id_prefix", "value": case_id},
        "artifact": {"raw": artifact_ref, "kind": "artifact", "source": "link_fix_argument", "value": artifact_ref},
        "artifact_meta": dict(normalized_artifact_ref),
    }
    return response
