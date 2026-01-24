"""Sentinel mode toolset (append_event/open_bug/open_security/link_fix)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.utils.sentinel_logs import append_case_event, append_sentinel_event


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
    """Generate a case ID for project mode by scanning recent entries.

    Args:
        kind: "BUG" or "SEC"
        result: The result from append_entry containing paths info

    Returns:
        Case ID like "BUG-2026-01-24-0001"
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = f"{kind}-{today}-"

    # Try to scan the log file for existing case IDs with this prefix
    last_seq = 0
    paths = result.get("paths", [])
    primary_path = result.get("path")
    if primary_path:
        paths = [primary_path] + [p for p in paths if p != primary_path]

    case_id_pattern = re.compile(rf"{re.escape(prefix)}(\d+)")

    for log_path in paths:
        try:
            from pathlib import Path
            path = Path(log_path)
            if not path.exists():
                continue
            # Read last 64KB to find recent case IDs
            size = path.stat().st_size
            read_size = min(size, 65536)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if size > read_size:
                    f.seek(size - read_size)
                content = f.read()
                for match in case_id_pattern.finditer(content):
                    seq = int(match.group(1))
                    if seq > last_seq:
                        last_seq = seq
        except Exception:
            continue

    return f"{prefix}{last_seq + 1:04d}"


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


@app.tool()
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


@app.tool()
async def open_bug(
    agent: str,
    title: str,
    symptoms: str,
    category: str,
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Open a BUG case with per-day stable ID and create a detailed bug report document.

    Args:
        agent: Agent identifier
        title: Short bug title
        symptoms: Description of the bug symptoms
        category: Bug category for organization (e.g., 'auth', 'api', 'ui')
        affected_paths: Optional list of affected file paths
    """
    if not category or not category.strip():
        return {"ok": False, "error": "category is required"}

    context = _get_context()

    # Project mode: route through append_entry with bug status AND create bug report doc
    if context.mode == "project":
        from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
        from scribe_mcp.tools.manage_docs import manage_docs as manage_docs_tool

        # Generate case ID first so we can use it in the document
        # We'll use a temporary result to get paths, then generate ID
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        case_id_prefix = f"BUG-{today}-"

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
        case_id = _next_case_id_for_project("BUG", result)

        # Create detailed bug report document
        doc_result = await manage_docs_tool(
            agent=agent,
            action="create",
            metadata={
                "doc_type": "bug",
                "category": category,
                "slug": case_id,
                "title": title,
                "case_id": case_id,
                "symptoms": symptoms,
                "affected_paths": affected_paths or [],
                "body": f"""# {case_id}: {title}

**Status:** Open
**Reported:** {today}
**Reporter:** {agent}

## Symptoms
{symptoms}

## Affected Paths
{chr(10).join(f'- `{p}`' for p in (affected_paths or [])) or '_None specified_'}

## Investigation
_Add investigation notes here_

## Root Cause
_To be determined_

## Fix
_To be determined_

## Verification
- [ ] Root cause identified
- [ ] Fix implemented
- [ ] Tests added/updated
- [ ] Fix verified
""",
            },
        )

        return {
            "ok": True,
            "case_id": str(case_id),
            "entry_id": str(result.get("id", "")),
            "path": str(result.get("path", "")),
            "project_name": str(result.get("project_name", "")),
            "bug_report": str(doc_result.get("path", "")) if isinstance(doc_result, dict) and doc_result.get("ok") else None,
        }

    # Sentinel mode: original behavior
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


@app.tool()
async def open_security(
    agent: str,
    title: str,
    symptoms: str,
    category: str,
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Open a SECURITY case with per-day stable ID and create a detailed security report document.

    Args:
        agent: Agent identifier
        title: Short security issue title
        symptoms: Description of the security issue
        category: Category for organization (e.g., 'auth', 'injection', 'xss')
        affected_paths: Optional list of affected file paths
    """
    if not category or not category.strip():
        return {"ok": False, "error": "category is required"}

    context = _get_context()

    # Project mode: route through append_entry with security flag AND create security report doc
    if context.mode == "project":
        from scribe_mcp.tools.append_entry import append_entry as append_entry_tool
        from scribe_mcp.tools.manage_docs import manage_docs as manage_docs_tool

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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
        case_id = _next_case_id_for_project("SEC", result)

        # Create detailed security report document
        doc_result = await manage_docs_tool(
            agent=agent,
            action="create",
            metadata={
                "doc_type": "bug",  # Use bug template for security too
                "category": category,
                "slug": case_id,
                "title": title,
                "case_id": case_id,
                "symptoms": symptoms,
                "affected_paths": affected_paths or [],
                "body": f"""# {case_id}: {title}

**Status:** Open
**Severity:** To be assessed
**Reported:** {today}
**Reporter:** {agent}

## Description
{symptoms}

## Affected Paths
{chr(10).join(f'- `{p}`' for p in (affected_paths or [])) or '_None specified_'}

## Security Impact
_Assess the security impact here_

## Attack Vector
_Describe how this could be exploited_

## Mitigation
_Immediate mitigation steps_

## Permanent Fix
_Long-term fix approach_

## Verification
- [ ] Impact assessed
- [ ] Mitigation applied
- [ ] Permanent fix implemented
- [ ] Security review completed
- [ ] No regression introduced
""",
            },
        )

        return {
            "ok": True,
            "case_id": str(case_id),
            "entry_id": str(result.get("id", "")),
            "path": str(result.get("path", "")),
            "project_name": str(result.get("project_name", "")),
            "security_report": str(doc_result.get("path", "")) if isinstance(doc_result, dict) and doc_result.get("ok") else None,
        }

    # Sentinel mode: original behavior
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


@app.tool()
async def link_fix(
    agent: str,
    case_id: str,
    execution_id: str,
    artifact_ref: str,
    landing_status: str,
) -> Dict[str, Any]:
    """Link a fix artifact to a BUG/SEC case."""
    context = _get_context()

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

        return {
            "ok": True,
            "case_id": str(case_id),
            "entry_id": str(result.get("id", "")),
            "path": str(result.get("path", "")),
            "project_name": str(result.get("project_name", "")),
        }

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
