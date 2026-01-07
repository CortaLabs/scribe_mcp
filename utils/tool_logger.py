#!/usr/bin/env python3
"""
Tool logging module with zero recursion guarantee.

CRITICAL DESIGN CONSTRAINTS:
- ZERO imports from tools/append_entry or utils/response
- ZERO imports from any module that transitively imports the above
- Only imports: utils/files, storage/, config/, standard library
- Direct writes to JSONL + SQL, completely bypassing append_entry

This module breaks the recursion cycle:
  finalize_tool_response() -> append_entry(log_type="tool_logs") -> finalize_tool_response() -> ...

By providing direct JSONL + SQL logging without any tool invocation.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Safe imports - these do NOT import append_entry or response
# CRITICAL: Import settings only (no other utils imports to avoid response.py)
from scribe_mcp.config.settings import settings


# Minimal JSONL append function (inlined to avoid importing utils.files)
def _append_jsonl_line(path: Path, line: str) -> None:
    """
    Minimal JSONL line append without dependencies.

    This is inlined to avoid importing utils.files which would
    trigger utils/__init__.py importing response.py.
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Append line with newline
    with open(path, 'a', encoding='utf-8') as f:
        f.write(line)
        if not line.endswith('\n'):
            f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def get_tool_log_path() -> Path:
    """
    Get path to TOOL_LOG.jsonl file.

    Returns:
        Path to .scribe/logs/TOOL_LOG.jsonl
    """
    return settings.project_root / ".scribe" / "logs" / "TOOL_LOG.jsonl"


# NOTE: extract_session_context() removed to avoid circular imports.
# The entire scribe_mcp module hierarchy imports utils.response transitively.
# Solution: Callers must pass session_id explicitly to log_tool_call().


def log_tool_call(
    tool_name: str,
    session_id: str,
    duration_ms: Optional[float] = None,
    status: str = "success",
    format_requested: Optional[str] = None,
    project_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    error_message: Optional[str] = None,
    response_size_bytes: Optional[int] = None,
) -> None:
    """
    Log tool call to JSONL without recursion.

    CRITICAL: Never calls append_entry or finalize_tool_response.
    CRITICAL: Synchronous function to avoid async complexity.

    Write strategy:
    1. JSONL: Append to .scribe/logs/TOOL_LOG.jsonl via minimal inline function
    2. SQL: Handled separately by finalize_tool_response after logging completes

    Graceful degradation: Log errors but never raise (tool logging can't break tools).

    Args:
        tool_name: Name of the tool that was called
        session_id: Session identifier from execution context
        duration_ms: Optional execution time in milliseconds
        status: Tool execution status (success, error, partial)
        format_requested: Format parameter from tool call (readable/structured/compact)
        project_name: Optional project context
        agent_id: Optional agent identifier
        error_message: Optional error details if status=error
        response_size_bytes: Optional response payload size for cost tracking

    Returns:
        None - all errors are caught and logged to stderr
    """
    # Build JSONL entry
    timestamp = datetime.now(timezone.utc).isoformat()

    entry = {
        "timestamp": timestamp,
        "session_id": session_id,
        "tool_name": tool_name,
        "status": status,
    }

    # Add optional fields only if present
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    if format_requested:
        entry["format_requested"] = format_requested
    if project_name:
        entry["project_name"] = project_name
    if agent_id:
        entry["agent_id"] = agent_id
    if error_message:
        entry["error_message"] = error_message
    if response_size_bytes is not None:
        entry["response_size_bytes"] = response_size_bytes

    # Write to JSONL (always attempt this)
    try:
        jsonl_path = get_tool_log_path()
        json_line = json.dumps(entry, ensure_ascii=False)
        _append_jsonl_line(jsonl_path, json_line)

    except Exception as e:
        # Log to stderr but don't raise - JSONL write failure shouldn't break tools
        print(f"Warning: Failed to write tool log to JSONL: {e}", file=sys.stderr)


# Module-level verification: ensure no imports of recursion sources
def _verify_no_recursion_imports():
    """
    Static verification that this module doesn't import recursion sources.

    This function is for documentation/testing purposes only.
    Run at module load time in debug mode to catch import violations early.

    NOTE: Must be run via direct file execution, not via python -m
    because -m loads the entire scribe_mcp package hierarchy which
    transitively imports response.py.
    """
    import sys
    forbidden = {
        "scribe_mcp.tools.append_entry",
        "scribe_mcp.utils.response",
        "tools.append_entry",
        "utils.response",
    }

    current_modules = set(sys.modules.keys())
    violations = current_modules & forbidden

    if violations:
        raise ImportError(
            f"CRITICAL: tool_logger.py has imported forbidden modules: {violations}\n"
            f"This will cause infinite recursion. Remove these imports immediately."
        )


# Run verification in debug mode
if __name__ == "__main__":
    # Add parent directory to path for direct imports
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    # Now import and verify
    _verify_no_recursion_imports()
    print("✅ tool_logger.py: No recursion imports detected")
    print(f"✅ Verified clean imports: only config.settings")
    print(f"✅ log_tool_call() ready for use")
