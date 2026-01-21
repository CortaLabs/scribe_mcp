"""Sentinel mode toolset (append_event/open_bug/open_security/link_fix)."""

from __future__ import annotations

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
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Open a BUG case with per-day stable ID."""
    context = _require_sentinel_context()
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
    affected_paths: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Open a SECURITY case with per-day stable ID."""
    context = _require_sentinel_context()
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
    context = _require_sentinel_context()
    case_id_upper = case_id.upper()
    if case_id_upper.startswith("BUG-"):
        event_type = "bug_fix_linked"
        kind = "BUG"
    elif case_id_upper.startswith("SEC-"):
        event_type = "security_fix_linked"
        kind = "SEC"
    else:
        return {"ok": False, "error": "case_id must start with BUG- or SEC-"}

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
    return {"ok": True, "case_id": case_id}
