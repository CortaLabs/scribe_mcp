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


def get_tool_log_path(
    repo_root: Optional[Path] = None,
    project_name: Optional[str] = None,
    progress_log_path: Optional[str] = None
) -> Path:
    """
    Get path to TOOL_LOG.jsonl file.

    Args:
        repo_root: Optional repository root.
        project_name: Optional project name (only used for logging, not path construction).
        progress_log_path: Optional path to project's PROGRESS_LOG.md - TOOL_LOG goes in same directory.
                          This ensures consistent slugification (uses same path as set_project created).

    Returns:
        Path to TOOL_LOG.jsonl in the appropriate location:
        - With progress_log_path: {progress_log_dir}/TOOL_LOG.jsonl (same dir as PROGRESS_LOG.md)
        - Sentinel/no project: {repo_root}/.scribe/logs/TOOL_LOG.jsonl
        - Fallback: {SCRIBE_ROOT}/.scribe/logs/TOOL_LOG.jsonl
    """
    # Priority 1: Use progress_log_path directory if provided (ensures correct slugification)
    if progress_log_path:
        progress_log = Path(progress_log_path)
        return progress_log.parent / "TOOL_LOG.jsonl"

    # Priority 2: Repo-level logs for sentinel mode or unknown projects
    base = repo_root if repo_root else settings.project_root
    return base / ".scribe" / "logs" / "TOOL_LOG.jsonl"


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
    repo_root: Optional[str] = None,
    progress_log_path: Optional[str] = None,
) -> None:
    """
    Log tool call to JSONL without recursion.

    CRITICAL: Never calls append_entry or finalize_tool_response.
    CRITICAL: Synchronous function to avoid async complexity.

    Write strategy:
    1. JSONL: Append to project's dev_plans directory or repo-level .scribe/logs/
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
        repo_root: Optional repository root path for sentinel/fallback mode.
        progress_log_path: Optional path to project's PROGRESS_LOG.md - TOOL_LOG goes in same dir.
                          This ensures consistent slugification with set_project.

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
    if repo_root:
        entry["repo_root"] = repo_root

    # Write to JSONL (always attempt this)
    try:
        # Resolve repo_root to Path if provided
        root_path = Path(repo_root) if repo_root else None
        jsonl_path = get_tool_log_path(root_path, project_name, progress_log_path)
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
