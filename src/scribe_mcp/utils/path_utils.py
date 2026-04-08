#!/usr/bin/env python3
"""
Path utility functions for token-optimized path formatting.

Part of SPEC-TOKEN-003 global optimization strategy.
"""

from pathlib import Path
from typing import Optional


def abbreviate_path(
    absolute_path: str,
    context_root: Optional[str] = None,
    verbosity: int = 1
) -> str:
    """
    Abbreviate absolute path to relative form based on verbosity level.

    This function implements Pattern 1 from SPEC-TOKEN-003: Absolute Path Reduction.
    Converts verbose absolute paths to context-aware relative paths, saving 30-60 tokens
    per occurrence.

    Args:
        absolute_path: Full absolute path to abbreviate
        context_root: Known root directory to make path relative to (optional)
        verbosity: Output verbosity level
            - 0 (minimal): Filename only - "PROGRESS_LOG.md"
            - 1 (standard): Relative from context root - ".scribe/docs/.../PROGRESS_LOG.md"
            - 2 (verbose): Full absolute path - "/home/user/projects/.../PROGRESS_LOG.md"

    Returns:
        Abbreviated path string appropriate for the verbosity level

    Examples:
        >>> abbreviate_path("/home/user/MCP_SPINE/scribe_mcp/.scribe/docs/project/PROGRESS_LOG.md", verbosity=0)
        'PROGRESS_LOG.md'

        >>> abbreviate_path("/home/user/MCP_SPINE/scribe_mcp/.scribe/docs/project/PROGRESS_LOG.md", verbosity=1)
        '.scribe/docs/project/PROGRESS_LOG.md'

        >>> abbreviate_path("/home/user/MCP_SPINE/scribe_mcp/.scribe/docs/project/PROGRESS_LOG.md", verbosity=2)
        '/home/user/MCP_SPINE/scribe_mcp/.scribe/docs/project/PROGRESS_LOG.md'

        >>> abbreviate_path("/home/user/project/src/main.py", context_root="/home/user/project", verbosity=1)
        'src/main.py'
    """
    if not absolute_path:
        return ""

    path_obj = Path(absolute_path)

    # Verbosity 2: Return full absolute path unchanged
    if verbosity >= 2:
        return absolute_path

    # Verbosity 0: Return filename only
    if verbosity == 0:
        return path_obj.name

    # Verbosity 1: Return relative path from context root
    # If context_root provided, make path relative to it
    if context_root:
        try:
            context_path = Path(context_root).resolve()
            abs_path = path_obj.resolve()
            relative = abs_path.relative_to(context_path)
            return str(relative)
        except (ValueError, RuntimeError):
            # Path is not relative to context_root, continue to smart detection
            pass

    # Smart context detection for verbosity 1
    # Common patterns to abbreviate from:
    path_str = str(path_obj)

    # Pattern 1: Look for .scribe directory and show from there
    if "/.scribe/" in path_str:
        scribe_idx = path_str.find("/.scribe/")
        return path_str[scribe_idx + 1:]  # Include .scribe in output

    # Pattern 2: Look for scribe_mcp directory and show from there
    if "/scribe_mcp/" in path_str:
        scribe_mcp_idx = path_str.find("/scribe_mcp/")
        return path_str[scribe_mcp_idx + len("/scribe_mcp/"):]

    # Pattern 3: Look for MCP_SPINE directory and show from there
    if "/MCP_SPINE/" in path_str:
        mcp_spine_idx = path_str.find("/MCP_SPINE/")
        return path_str[mcp_spine_idx + len("/MCP_SPINE/"):]

    # Pattern 4: Look for projects directory and show from there
    if "/projects/" in path_str:
        projects_idx = path_str.find("/projects/")
        return path_str[projects_idx + len("/projects/"):]

    # Pattern 5: Look for home directory and show from ~ equivalent
    try:
        home = Path.home()
        if path_obj.is_relative_to(home):
            relative = path_obj.relative_to(home)
            return f"~/{relative}"
    except (ValueError, RuntimeError):
        pass

    # Fallback: Return as-is (already minimal or unknown pattern)
    return absolute_path
