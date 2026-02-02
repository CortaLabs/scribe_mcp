"""Path suggestion helpers for enriched file-not-found errors.

Provides fuzzy filename matching, directory listings, and cross-tool command suggestions
for enhanced error messages in read_file and search tools.
"""

from __future__ import annotations

import difflib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Performance and safety constants
MAX_FUZZY_SUGGESTIONS = 5        # Top fuzzy matches only
MAX_DIRECTORY_ENTRIES = 30       # Prevent output explosion
MAX_SCAN_FILES = 1000           # Timeout protection for large dirs
FUZZY_CUTOFF = 0.6              # 60% similarity threshold


def get_fuzzy_file_suggestions(
    target_name: str,
    parent_dir: Path,
    max_suggestions: int = MAX_FUZZY_SUGGESTIONS,
    cutoff: float = FUZZY_CUTOFF,
    include_directories: bool = False
) -> List[Dict[str, Any]]:
    """Get fuzzy filename matches from parent directory.

    Args:
        target_name: The filename/dirname user tried to access
        parent_dir: Parent directory to search in
        max_suggestions: Maximum number of suggestions to return
        cutoff: Minimum similarity score (0.0-1.0)
        include_directories: Whether to include directories in suggestions

    Returns:
        [{"name": "auth.py", "score": 0.88, "is_dir": False}, ...]
        Empty list if parent unreadable or no matches found

    Performance: <2ms for typical directories (<500 files)
    """
    try:
        if not parent_dir.exists() or not parent_dir.is_dir():
            return []

        # Collect candidate names with early termination
        candidates = []
        scan_count = 0

        for entry in os.scandir(parent_dir):
            if scan_count >= MAX_SCAN_FILES:
                break

            scan_count += 1

            # Filter by include_directories flag
            if entry.is_dir() and not include_directories:
                continue

            candidates.append((entry.name, entry.is_dir()))

        # Get fuzzy matches using difflib
        candidate_names = [name for name, _ in candidates]
        matches = difflib.get_close_matches(
            target_name,
            candidate_names,
            n=max_suggestions,
            cutoff=cutoff
        )

        # Build result list with scores and is_dir flags
        results = []
        for match in matches:
            # Find the is_dir flag for this match
            is_dir = next((is_d for name, is_d in candidates if name == match), False)

            # Calculate similarity score
            score = difflib.SequenceMatcher(None, target_name, match).ratio()

            results.append({
                "name": match,
                "score": score,
                "is_dir": is_dir
            })

        return results

    except (OSError, PermissionError, Exception):
        # Graceful degradation on any filesystem error
        return []


def get_directory_listing(
    directory: Path,
    max_entries: int = MAX_DIRECTORY_ENTRIES,
    include_hidden: bool = False,
    separate_files_dirs: bool = True
) -> Dict[str, Any]:
    """Get truncated directory listing with files/dirs separated.

    Args:
        directory: Directory to list
        max_entries: Maximum entries to return (per category if separated)
        include_hidden: Include files starting with '.'
        separate_files_dirs: Separate into files and directories

    Returns:
        {
            "files": ["auth.py", "config.py"],
            "directories": ["api/", "utils/"],
            "truncated": False,
            "total_scanned": 15,
            "permission_error": False
        }
        Empty dict with permission_error=True if directory unreadable

    Performance: <1ms using os.scandir(), capped at MAX_SCAN_FILES iterations
    """
    try:
        if not directory.exists() or not directory.is_dir():
            return {"permission_error": True}

        files = []
        directories = []
        total_scanned = 0
        truncated = False

        for entry in os.scandir(directory):
            if total_scanned >= MAX_SCAN_FILES:
                truncated = True
                break

            total_scanned += 1

            # Skip hidden files unless requested
            if not include_hidden and entry.name.startswith('.'):
                continue

            if separate_files_dirs:
                if entry.is_dir():
                    directories.append(entry.name)
                else:
                    if len(files) < max_entries:
                        files.append(entry.name)
                    else:
                        truncated = True
            else:
                # Combined listing
                if len(files) < max_entries:
                    files.append(entry.name + ("/" if entry.is_dir() else ""))
                else:
                    truncated = True

        if separate_files_dirs:
            # Sort directories alphabetically
            directories.sort()
            # Sort files: .py first, then alphabetically within groups
            def _file_sort_key(name: str) -> tuple:
                is_py = name.endswith('.py')
                return (0 if is_py else 1, name.lower())
            files.sort(key=_file_sort_key)
            return {
                "files": files,
                "directories": directories,
                "truncated": truncated,
                "total_scanned": total_scanned,
                "permission_error": False
            }
        else:
            return {
                "entries": files,
                "truncated": truncated,
                "total_scanned": total_scanned,
                "permission_error": False
            }

    except (OSError, PermissionError, Exception):
        return {"permission_error": True}


def classify_path_error(target: Path) -> str:
    """Classify path error into specific error type.

    Args:
        target: Path that caused error

    Returns:
        "not_found" | "is_directory" | "permission_denied" | "is_symlink" | "unknown"

    Logic:
        if not target.exists(): return "not_found"
        if target.is_dir(): return "is_directory"
        if target.is_symlink() and not target.is_file(): return "is_symlink"
        # Try to read to detect permission issues
        try: target.stat()
        except PermissionError: return "permission_denied"
        return "unknown"
    """
    try:
        # Check for broken symlink BEFORE exists() check
        # (broken symlinks don't exist but we want to classify them specially)
        if target.is_symlink() and not target.exists():
            return "is_symlink"

        if not target.exists():
            return "not_found"

        if target.is_dir():
            return "is_directory"

        # Try to access the file to detect permission issues
        try:
            target.stat()
        except PermissionError:
            return "permission_denied"

        return "unknown"

    except Exception:
        return "unknown"


def build_search_suggestion(pattern: str, path: str, agent: str) -> str:
    """Build cross-tool search command suggestion.

    Returns formatted command string:
        'search(agent="YourAgent", pattern="auth_handler", path="src/")'
    """
    # Escape double quotes in inputs
    pattern_escaped = pattern.replace('"', '\\"')
    path_escaped = path.replace('"', '\\"')
    agent_escaped = agent.replace('"', '\\"')

    return f'search(agent="{agent_escaped}", pattern="{pattern_escaped}", path="{path_escaped}")'


def build_read_suggestion(file_path: str, agent: str, mode: str = "scan_only") -> str:
    """Build cross-tool read_file command suggestion.

    Returns formatted command string:
        'read_file(agent="YourAgent", path="src/auth/handler.py", mode="scan_only")'
    """
    # Escape double quotes in inputs
    file_path_escaped = file_path.replace('"', '\\"')
    agent_escaped = agent.replace('"', '\\"')
    mode_escaped = mode.replace('"', '\\"')

    return f'read_file(agent="{agent_escaped}", path="{file_path_escaped}", mode="{mode_escaped}")'
