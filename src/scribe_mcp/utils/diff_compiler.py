"""Helpers for compiling unified diffs from text changes."""

from __future__ import annotations

from difflib import unified_diff


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
            before.splitlines(),
            after.splitlines(),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )
