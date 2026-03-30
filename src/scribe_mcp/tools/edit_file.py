"""Safe file editing tool with exact string replacement and read-before-edit enforcement."""

from __future__ import annotations

import difflib
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app, router_context_manager
from scribe_mcp.tool_contracts import stateful_local_tool
from scribe_mcp.utils.response import default_formatter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ReplaceResult:
    """Tracks replacement operation metadata."""

    occurrences_found: int = 0
    occurrences_replaced: int = 0
    lines_affected: List[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _perform_replacement(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool,
) -> Tuple[str, ReplaceResult]:
    """Find and replace exact string in content.

    Returns (modified_content, ReplaceResult).
    """
    result = ReplaceResult()

    # Count total occurrences
    result.occurrences_found = content.count(old_string)
    if result.occurrences_found == 0:
        return content, result

    # Find line numbers of all occurrences
    lines = content.split("\n")
    for i, line in enumerate(lines, start=1):
        if old_string in line:
            result.lines_affected.append(i)

    # Perform replacement
    if replace_all:
        modified = content.replace(old_string, new_string)
        result.occurrences_replaced = result.occurrences_found
    else:
        modified = content.replace(old_string, new_string, 1)
        result.occurrences_replaced = 1
        # Only first affected line for single replace
        if result.lines_affected:
            result.lines_affected = result.lines_affected[:1]

    return modified, result


def _generate_diff(original: str, modified: str, filepath: str) -> str:
    """Generate unified diff between original and modified content."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm="",
    )
    return "".join(diff)


def _backup_file(file_path: Path, repo_root: Path) -> Path:
    """Create a timestamped backup of the file.

    Backup goes to .scribe/backups/ relative to repo root.
    Returns the backup path.
    """
    backup_dir = repo_root / ".scribe" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    backup_name = f"{file_path.name}.{ts}.bak"
    backup_path = backup_dir / backup_name

    shutil.copy2(file_path, backup_path)
    return backup_path


def _format_edit_readable(
    data: Dict[str, Any],
    is_dry_run: bool,
) -> str:
    """Format edit result as readable text with box-drawing characters."""
    lines: List[str] = []
    path = data.get("path", "")
    ok = data.get("ok", False)

    if not ok:
        lines.append(f"ERROR: {data.get('message', data.get('error', 'Unknown error'))}")
        if data.get("required_action"):
            lines.append(f"  Required: {data['required_action']}")
        return "\n".join(lines)

    mode_label = "DRY RUN PREVIEW" if is_dry_run else "CHANGES APPLIED"
    lines.append(f"EDIT FILE {path} | {mode_label}")
    lines.append("")

    if is_dry_run:
        preview = data.get("preview", {})
        found = preview.get("occurrences_found", 0)
        would_replace = preview.get("occurrences_would_replace", 0)
        affected = preview.get("lines_affected", [])
        lines.append(f"  Occurrences found: {found}")
        lines.append(f"  Would replace: {would_replace}")
        if affected:
            lines.append(f"  Lines affected: {', '.join(str(ln) for ln in affected)}")
        lines.append("")
        diff = preview.get("diff", "")
        if diff:
            lines.append("Diff:")
            lines.append(diff)
        lines.append("")
        lines.append("DRY_RUN: No changes written. Set dry_run=False to apply.")
    else:
        applied = data.get("applied", {})
        replacements = applied.get("replacements_made", 0)
        modified_lines = applied.get("lines_modified", [])
        backup = applied.get("backup_path", "")
        lines.append(f"  Replacements made: {replacements}")
        if modified_lines:
            lines.append(f"  Lines modified: {', '.join(str(ln) for ln in modified_lines)}")
        if backup:
            lines.append(f"  Backup: {backup}")
        size_before = applied.get("file_size_before")
        size_after = applied.get("file_size_after")
        if size_before is not None:
            lines.append(f"  Size: {size_before} -> {size_after} bytes")
        diff = data.get("diff", "")
        if diff:
            lines.append("")
            lines.append("Diff:")
            lines.append(diff)
        lines.append("")
        lines.append("Changes applied successfully.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP Tool
# ---------------------------------------------------------------------------


@app.tool(**stateful_local_tool(title="Edit File", tags=("files", "code", "write")))
async def edit_file(
    # REQUIRED
    agent: str,
    path: str,
    old_string: str,
    new_string: str,
    # Behavior
    replace_all: bool = False,
    # Safety
    dry_run: bool = True,
    # Output
    format: str = "readable",
) -> Union[Dict[str, Any], str]:
    """Safe file editing with exact string replacement.

    CRITICAL REQUIREMENTS:
    - read_file MUST have been called on this path in the current session
    - dry_run=True by default - must explicitly set False to commit changes
    - Only exact string matching (no regex in MVP)

    Parameters:
        agent: Agent identifier (required for audit trail)
        path: File to edit (repo-relative or absolute)
        old_string: Exact string to find in the file
        new_string: Replacement string
        replace_all: Replace all occurrences (default: False, first only)
        dry_run: Preview without writing (default: True for safety)
        format: Output format - "readable", "structured", "compact"

    Returns diff preview in dry_run mode, confirmation in commit mode.
    """
    # --- Execution context ---
    exec_context = server_module.get_execution_context()
    if exec_context is None:
        return {"ok": False, "error": "ExecutionContext missing"}

    repo_root = Path(exec_context.repo_root).resolve()
    session_id = exec_context.session_id

    # --- Resolve path with symlink-aware traversal prevention ---
    file_path = Path(path).expanduser()

    # Step 1: Check unresolved path for boundary escape attempts
    if not file_path.is_absolute():
        unresolved = repo_root / file_path
        try:
            normalized = unresolved.resolve(strict=False)
            if not str(normalized).startswith(str(repo_root)):
                return {
                    "ok": False,
                    "error": "SANDBOX_VIOLATION",
                    "message": f"Path escapes repository boundary: {path}",
                }
        except (OSError, ValueError):
            pass  # Let downstream checks handle broken paths

    # Step 2: Resolve path (follows symlinks)
    if not file_path.is_absolute():
        file_path = (repo_root / file_path).resolve()
    else:
        file_path = file_path.resolve()

    # Step 3: Sandbox check on resolved path
    try:
        file_path.relative_to(repo_root)
    except ValueError:
        return {
            "ok": False,
            "error": "SANDBOX_VIOLATION",
            "message": f"Cannot edit file outside repository boundary: {file_path}",
        }

    # Step 4: If original path is a symlink, verify target is within repo
    raw_path = Path(path).expanduser()
    if not raw_path.is_absolute():
        raw_path = repo_root / raw_path
    if raw_path.is_symlink():
        link_dest = raw_path.resolve()
        if not str(link_dest).startswith(str(repo_root)):
            return {
                "ok": False,
                "error": "SANDBOX_VIOLATION",
                "message": f"Symlink target escapes repository boundary: {path}",
            }

    # --- Read-before-edit enforcement ---
    if session_id:
        file_was_read = await router_context_manager.has_file_been_read(
            session_id, str(file_path)
        )
        if not file_was_read:
            rel_path = str(file_path.relative_to(repo_root))
            return {
                "ok": False,
                "error": "READ_BEFORE_EDIT_REQUIRED",
                "message": f"Cannot edit {rel_path} - file not read in this session",
                "required_action": f"Call read_file(path='{rel_path}') before editing",
                "reason": "Safety mechanism prevents blind edits",
            }
    else:
        return {
            "ok": False,
            "error": "SESSION_REQUIRED",
            "message": "No session ID available - cannot verify read-before-edit",
        }

    # --- Validate file exists and is readable ---
    if not file_path.exists():
        return {"ok": False, "error": "FILE_NOT_FOUND", "message": f"File does not exist: {file_path}"}

    if not file_path.is_file():
        return {"ok": False, "error": "NOT_A_FILE", "message": f"Path is not a file: {file_path}"}

    # --- Read file content ---
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": "READ_ERROR", "message": f"Cannot read file: {exc}"}

    # --- Perform replacement ---
    rel_path = str(file_path.relative_to(repo_root))
    modified, result = _perform_replacement(content, old_string, new_string, replace_all)

    if result.occurrences_found == 0:
        # Suggest: show first ~60 chars of old_string for debugging
        preview = old_string[:60] + ("..." if len(old_string) > 60 else "")
        return {
            "ok": False,
            "error": "STRING_NOT_FOUND",
            "message": f"old_string not found in {rel_path}",
            "old_string_preview": preview,
            "suggestion": "Verify the exact string exists in the file. Use read_file to check.",
        }

    # --- Generate diff ---
    diff_text = _generate_diff(content, modified, rel_path)

    # --- Dry-run mode (default) ---
    if dry_run:
        response: Dict[str, Any] = {
            "ok": True,
            "path": rel_path,
            "dry_run": True,
            "preview": {
                "old_string": old_string[:200],
                "new_string": new_string[:200],
                "occurrences_found": result.occurrences_found,
                "occurrences_would_replace": result.occurrences_replaced,
                "lines_affected": result.lines_affected,
                "diff": diff_text,
            },
            "warning": "DRY_RUN: No changes written. Set dry_run=False to apply.",
            "next_step": "Review diff, then call again with dry_run=False",
        }
    else:
        # --- Commit mode: backup and write ---
        try:
            backup_path = _backup_file(file_path, repo_root)
        except Exception as exc:
            return {"ok": False, "error": "BACKUP_ERROR", "message": f"Failed to create backup: {exc}"}

        try:
            file_path.write_text(modified, encoding="utf-8")
        except Exception as exc:
            return {
                "ok": False,
                "error": "WRITE_ERROR",
                "message": f"Failed to write file: {exc}",
                "backup_path": str(backup_path.relative_to(repo_root)),
            }

        # Fire-and-forget sync to remote object store
        try:
            from scribe_mcp.object_store import sync_file_to_store
            import asyncio
            task = asyncio.create_task(sync_file_to_store(file_path, modified, repo_root))
            from scribe_mcp.server import background_tasks
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
        except Exception:
            pass

        response = {
            "ok": True,
            "path": rel_path,
            "dry_run": False,
            "applied": {
                "old_string": old_string[:200],
                "new_string": new_string[:200],
                "occurrences_found": result.occurrences_found,
                "replacements_made": result.occurrences_replaced,
                "lines_modified": result.lines_affected,
                "file_size_before": len(content.encode("utf-8")),
                "file_size_after": len(modified.encode("utf-8")),
                "backup_path": str(backup_path.relative_to(repo_root)),
            },
            "diff": diff_text,
            "success": "Changes applied successfully",
        }

    # --- Format output ---
    if format == "structured":
        return response
    elif format == "compact":
        compact: Dict[str, Any] = {
            "ok": response["ok"],
            "path": response["path"],
            "dry_run": response["dry_run"],
        }
        if dry_run:
            p = response["preview"]
            compact["found"] = p["occurrences_found"]
            compact["would_replace"] = p["occurrences_would_replace"]
        else:
            a = response["applied"]
            compact["replaced"] = a["replacements_made"]
            compact["backup"] = a["backup_path"]
        return compact
    else:
        # Readable: route through finalize_tool_response
        readable_text = _format_edit_readable(response, dry_run)
        response["readable_content"] = readable_text
        return await default_formatter.finalize_tool_response(
            data=response,
            format="readable",
            tool_name="edit_file",
        )
