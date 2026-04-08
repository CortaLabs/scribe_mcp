"""Shared helpers for log searching and filtering."""

from __future__ import annotations

import re
from typing import Optional


def message_matches(
    text: Optional[str],
    needle: Optional[str],
    *,
    mode: str = "substring",
    case_sensitive: bool = False,
) -> bool:
    """Return True when `needle` is found in `text` according to the mode."""
    if not needle:
        return True

    haystack = text or ""
    if mode == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(needle, flags)
        except re.error:
            return False
        return bool(pattern.search(haystack))

    if mode == "exact":
        candidate = needle
        target = haystack
        if not case_sensitive:
            candidate = needle.lower()
            target = haystack.lower()
        return candidate == target

    # Default to substring matching
    candidate = needle if case_sensitive else needle.lower()
    target = haystack if case_sensitive else haystack.lower()
    return candidate in target
