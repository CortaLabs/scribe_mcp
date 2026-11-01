"""Helpers for compiling unified diffs from text changes."""

from __future__ import annotations

from difflib import unified_diff

from scribe_mcp.doc_management.quality.scopes import markdown_lines


def compile_unified_diff(
    before: str,
    after: str,
    *,
    fromfile: str = "before",
    tofile: str = "after",
) -> str:
    """Return a valid unified diff for the provided before/after text."""
    return "\n".join(
        unified_diff(
            [line.rstrip("\r\n") for line in markdown_lines(before)],
            [line.rstrip("\r\n") for line in markdown_lines(after)],
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )
