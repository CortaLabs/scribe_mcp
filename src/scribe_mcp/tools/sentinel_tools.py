"""Sentinel mode toolset (append_event/open_bug/open_security/link_fix)."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pathlib import Path

from scribe_mcp import server as server_module
from scribe_mcp.server import app
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


def _validate_link_fix_execution_id(context: Any, execution_id: str) -> Optional[str]:
    """Validate link_fix execution provenance against active execution context.

    Returns:
        None when valid; otherwise an error string.
    """
    if not isinstance(execution_id, str) or not execution_id.strip():
        return "execution_id is required"

    provided_id = execution_id.strip()
    allowed_ids: set[str] = set()

    current_execution_id = getattr(context, "execution_id", None)
    if isinstance(current_execution_id, str) and current_execution_id.strip():
        allowed_ids.add(current_execution_id.strip())

    parent_execution_id = getattr(context, "parent_execution_id", None)
    if isinstance(parent_execution_id, str) and parent_execution_id.strip():
        allowed_ids.add(parent_execution_id.strip())

    # When execution context does not expose IDs (e.g., legacy tests), avoid false negatives.
    if not allowed_ids:
        return None

    if provided_id not in allowed_ids:
        return (
            "execution_id does not match active execution context "
            "(must be current or parent execution_id)"
        )

    return None


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


@app.tool(**additive_local_tool(title="Open Bug Case", tags=("bugs", "sentinel", "write")))
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
    if not category or not category.strip():
        return {"ok": False, "error": "category is required"}

    context = _get_context()

    # Project mode: route through append_entry with bug status AND create bug report doc
    if context.mode == "project":
        if preview:
            try:
                case_id = _preview_case_id_for_project("BUG", context)
            except Exception as exc:
                return {"ok": False, "error": f"Failed to preview BUG case ID: {exc}"}
            return {"ok": True, "case_id": case_id, "preview": True}

        from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
        from scribe_mcp.tools.manage_docs import manage_docs as manage_docs_tool

        message = f"[BUG] {title}: {symptoms}"
        meta = {
            "case_type": "bug",
            "title": title,
            "symptoms": symptoms,
            "affected_paths": affected_paths or [],
            "landing_status": "proposed",
        }

        result = await append_entry_tool(
            message=message,
            status="bug",
            agent=agent,
            meta=meta,
            format="structured",  # Returns plain dict, not MCP-wrapped
        )

        if not result.get("ok"):
            return {"ok": False, "error": str(result.get("error", "append_entry failed"))}

        # Generate case ID after entry is written (so we can scan for existing IDs)
        try:
            case_id = _next_case_id_for_project("BUG", result)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Failed to allocate BUG case ID: {exc}",
                "entry_id": str(result.get("id", "")),
                "path": str(result.get("path", "")),
                "project_name": str(result.get("project_name", "")),
            }

        # Ensure fresh case IDs are immediately queryable by bare ID.
        # The initial append_entry is written before case-id allocation, so we emit
        # a scoped registration entry containing case_id in both message and metadata.
        registration_result = await append_entry_tool(
            message=f"[CASE REGISTERED] {case_id}",
            status="bug",
            agent=agent,
            meta={
                "case_type": "bug",
                "case_id": case_id,
                "registration_event": "case_opened",
                "title": title,
            },
            format="structured",
        )
        if not registration_result.get("ok"):
            return {
                "ok": False,
                "error": str(registration_result.get("error", "case registration append_entry failed")),
                "case_id": str(case_id),
                "entry_id": str(result.get("id", "")),
                "path": str(result.get("path", "")),
                "project_name": str(result.get("project_name", "")),
            }

        # Create detailed bug report document
        # Build metadata dict (used for both doc creation and completeness scoring)
        bug_metadata = {
            "doc_type": "bug",
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
            "severity": severity if severity is not None else "medium",  # Default severity
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
            metadata=bug_metadata,
        )

        # Check if document creation succeeded
        if not isinstance(doc_result, dict) or not doc_result.get("ok"):
            error_msg = doc_result.get("error", "Unknown error") if isinstance(doc_result, dict) else "manage_docs returned non-dict"
            return {
                "ok": False,
                "error": f"Bug report document creation failed: {error_msg}",
                "case_id": str(case_id),
                "entry_id": str(result.get("id", "")),
                "path": str(result.get("path", "")),
                "project_name": str(result.get("project_name", "")),
            }

        # Calculate completeness score
        filled_sections = []
        unfilled_sections = []
        
        for field in _BUG_TEMPLATE_FIELDS:
            value = bug_metadata.get(field)
            if value and value != "[UNFILLED]" and value != ["[UNFILLED]"]:
                filled_sections.append(field)
            else:
                unfilled_sections.append(field)
        
        total_fields = len(_BUG_TEMPLATE_FIELDS)
        filled_count = len(filled_sections)
        percentage = int((filled_count / total_fields) * 100) if total_fields > 0 else 0

        return {
            "ok": True,
            "case_id": str(case_id),
            "entry_id": str(result.get("id", "")),
            "path": str(result.get("path", "")),
            "project_name": str(result.get("project_name", "")),
            "bug_report": str(doc_result.get("path", "")),
            # NEW completeness metadata:
            "completeness": {
                "score": f"{filled_count}/{total_fields}",
                "percentage": percentage,
                "filled_sections": filled_sections,
                "unfilled_sections": unfilled_sections,
            },
            # UPDATED action_required with specific guidance:
            "action_required": (
                f"Bug report {percentage}% complete. "
                f"Use manage_docs(agent='{agent}', action='replace_section', "
                f"doc_name='{case_id}', section='<section_id>', content='...') "
                f"to fill remaining sections: {', '.join(unfilled_sections[:5])}"
                + (f" and {len(unfilled_sections) - 5} more" if len(unfilled_sections) > 5 else "")
            ),
        }

    # Sentinel mode: original behavior
    if preview:
        sentinel_day = getattr(context, "sentinel_day", None)
        if not isinstance(sentinel_day, str) or not sentinel_day.strip():
            sentinel_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {"ok": True, "case_id": f"BUG-{sentinel_day}-PREVIEW", "preview": True}

    case_id = append_case_event(
        context,
        kind="BUG",
        event_type="bug_opened",
        data={
            "title": title,
            "symptoms": symptoms,
            "affected_paths": affected_paths or [],
            "landing_status": "proposed",
        },
        include_md=True,
    )
    return {"ok": True, "case_id": case_id}


@app.tool(**additive_local_tool(title="Open Security Case", tags=("security", "sentinel", "write")))
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
    if not category or not category.strip():
        return {"ok": False, "error": "category is required"}

    context = _get_context()

    # Project mode: route through append_entry with security flag AND create security report doc
    if context.mode == "project":
        if preview:
            try:
                case_id = _preview_case_id_for_project("SEC", context)
            except Exception as exc:
                return {"ok": False, "error": f"Failed to preview SEC case ID: {exc}"}
            return {"ok": True, "case_id": case_id, "preview": True}

        from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
        from scribe_mcp.tools.manage_docs import manage_docs as manage_docs_tool

        message = f"[SECURITY] {title}: {symptoms}"
        meta = {
            "case_type": "security",
            "security_event": "1",  # Triggers auto-tee to security log
            "title": title,
            "symptoms": symptoms,
            "affected_paths": affected_paths or [],
            "landing_status": "proposed",
        }

        result = await append_entry_tool(
            message=message,
            status="warn",  # Security issues are warnings
            agent=agent,
            meta=meta,
            format="structured",  # Returns plain dict, not MCP-wrapped
        )

        if not result.get("ok"):
            return {"ok": False, "error": str(result.get("error", "append_entry failed"))}

        # Generate case ID after entry is written (so we can scan for existing IDs)
        try:
            case_id = _next_case_id_for_project("SEC", result)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Failed to allocate SEC case ID: {exc}",
                "entry_id": str(result.get("id", "")),
                "path": str(result.get("path", "")),
                "project_name": str(result.get("project_name", "")),
            }

        # Ensure fresh case IDs are immediately queryable by bare ID.
        registration_result = await append_entry_tool(
            message=f"[CASE REGISTERED] {case_id}",
            status="warn",
            agent=agent,
            meta={
                "case_type": "security",
                "security_event": "1",
                "case_id": case_id,
                "registration_event": "case_opened",
                "title": title,
            },
            format="structured",
        )
        if not registration_result.get("ok"):
            return {
                "ok": False,
                "error": str(registration_result.get("error", "case registration append_entry failed")),
                "case_id": str(case_id),
                "entry_id": str(result.get("id", "")),
                "path": str(result.get("path", "")),
                "project_name": str(result.get("project_name", "")),
            }

        # Create detailed security report document
        # Build metadata dict (used for both doc creation and completeness scoring)
        security_metadata = {
            "doc_type": "security",  # Use dedicated security template
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
            "severity": severity if severity is not None else "high",  # Default severity for security issues
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
            metadata=security_metadata,
        )

        # Check if document creation succeeded
        if not isinstance(doc_result, dict) or not doc_result.get("ok"):
            error_msg = doc_result.get("error", "Unknown error") if isinstance(doc_result, dict) else "manage_docs returned non-dict"
            return {
                "ok": False,
                "error": f"Security report document creation failed: {error_msg}",
                "case_id": str(case_id),
                "entry_id": str(result.get("id", "")),
                "path": str(result.get("path", "")),
                "project_name": str(result.get("project_name", "")),
            }

        # Calculate completeness score
        filled_sections = []
        unfilled_sections = []
        
        for field in _BUG_TEMPLATE_FIELDS:
            value = security_metadata.get(field)
            if value and value != "[UNFILLED]" and value != ["[UNFILLED]"]:
                filled_sections.append(field)
            else:
                unfilled_sections.append(field)
        
        total_fields = len(_BUG_TEMPLATE_FIELDS)
        filled_count = len(filled_sections)
        percentage = int((filled_count / total_fields) * 100) if total_fields > 0 else 0

        return {
            "ok": True,
            "case_id": str(case_id),
            "entry_id": str(result.get("id", "")),
            "path": str(result.get("path", "")),
            "project_name": str(result.get("project_name", "")),
            "security_report": str(doc_result.get("path", "")),
            # NEW completeness metadata:
            "completeness": {
                "score": f"{filled_count}/{total_fields}",
                "percentage": percentage,
                "filled_sections": filled_sections,
                "unfilled_sections": unfilled_sections,
            },
            # UPDATED action_required with specific guidance:
            "action_required": (
                f"Security report {percentage}% complete. "
                f"Use manage_docs(agent='{agent}', action='replace_section', "
                f"doc_name='{case_id}', section='<section_id>', content='...') "
                f"to fill remaining sections: {', '.join(unfilled_sections[:5])}"
                + (f" and {len(unfilled_sections) - 5} more" if len(unfilled_sections) > 5 else "")
            ),
        }

    # Sentinel mode: original behavior
    if preview:
        sentinel_day = getattr(context, "sentinel_day", None)
        if not isinstance(sentinel_day, str) or not sentinel_day.strip():
            sentinel_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return {"ok": True, "case_id": f"SEC-{sentinel_day}-PREVIEW", "preview": True}

    case_id = append_case_event(
        context,
        kind="SEC",
        event_type="security_opened",
        data={
            "title": title,
            "symptoms": symptoms,
            "affected_paths": affected_paths or [],
            "landing_status": "proposed",
        },
        include_md=True,
    )
    return {"ok": True, "case_id": case_id}


@app.tool(**additive_local_tool(title="Link Fix Artifact", tags=("bugs", "security", "traceability", "write")))
async def link_fix(
    agent: str,
    case_id: str,
    execution_id: str,
    artifact_ref: str,
    landing_status: str,
) -> Dict[str, Any]:
    """Link a fix artifact to a BUG/SEC case."""
    context = _get_context()

    execution_id_error = _validate_link_fix_execution_id(context, execution_id)
    if execution_id_error:
        return {"ok": False, "error": execution_id_error}

    case_id_upper = case_id.upper()
    if case_id_upper.startswith("BUG-"):
        event_type = "bug_fix_linked"
        kind = "BUG"
    elif case_id_upper.startswith("SEC-"):
        event_type = "security_fix_linked"
        kind = "SEC"
    else:
        return {"ok": False, "error": "case_id must start with BUG- or SEC-"}

    # Project mode: route through append_entry
    if context.mode == "project":
        from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
        from scribe_mcp.tools.manage_docs import manage_docs as manage_docs_tool
        import logging as _logging
        _logger = _logging.getLogger(__name__)

        message = f"[FIX LINKED] {case_id}: {artifact_ref} ({landing_status})"
        meta = {
            "case_type": "bug" if kind == "BUG" else "security",
            "case_id": case_id,
            "fix_link": {
                "execution_id": execution_id,
                "artifact_ref": artifact_ref,
            },
            "landing_status": landing_status,
        }

        # Add security_event flag for security cases to trigger auto-tee
        if kind == "SEC":
            meta["security_event"] = "1"

        result = await append_entry_tool(
            message=message,
            status="success" if landing_status in ("merged", "landed", "done") else "info",
            agent=agent,
            meta=meta,
            format="structured",  # Returns plain dict, not MCP-wrapped
        )

        if not result.get("ok"):
            return {"ok": False, "error": str(result.get("error", "append_entry failed"))}

        # Update the bug/security report document with fix reference information.
        # The case_id was registered in project["docs"] when open_bug/open_security was called.
        doc_update_warning: str | None = None
        try:
            # Update the appendix section with fix reference details
            appendix_content = (
                f"- **Fix Reference:** {artifact_ref} (execution: {execution_id})\n"
                f"- **Landing Status:** {landing_status}\n"
                f"- **Fix Linked By:** {agent}\n"
            )
            appendix_result = await manage_docs_tool(
                agent=agent,
                action="replace_section",
                doc_name=case_id,
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
                    case_id,
                    doc_update_warning,
                )
            else:
                # Update the resolution_plan section with landing status
                resolution_content = (
                    f"### Immediate Actions\n"
                    f"Fix landed with status: **{landing_status}**\n\n"
                    f"### Fix Details\n"
                    f"- Artifact: {artifact_ref}\n"
                    f"- Execution ID: {execution_id}\n"
                )
                resolution_result = await manage_docs_tool(
                    agent=agent,
                    action="replace_section",
                    doc_name=case_id,
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
                        case_id,
                        doc_update_warning,
                    )
        except Exception as exc:
            doc_update_warning = str(exc)
            _logger.warning("link_fix: exception updating doc for %s: %s", case_id, exc)

        response: dict[str, Any] = {
            "ok": True,
            "case_id": str(case_id),
            "entry_id": str(result.get("id", "")),
            "path": str(result.get("path", "")),
            "project_name": str(result.get("project_name", "")),
        }
        if doc_update_warning:
            response["doc_update_warning"] = doc_update_warning
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
            },
            "landing_status": landing_status,
        },
        include_md=True,
    )
    return {"ok": True, "case_id": str(case_id)}
