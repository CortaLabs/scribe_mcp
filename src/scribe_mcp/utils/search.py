"""Shared helpers for log searching and filtering."""

from __future__ import annotations

import re
from typing import Optional, Tuple


# Modes whose matching semantics can be expressed exactly in SQL and therefore
# pushed into the storage query as an authoritative, exhaustive predicate.
# ``regex`` cannot be expressed portably across SQLite/Postgres, so it stays a
# Python post-filter (documented, bounded) — see ``message_matches``.
SQL_PUSHABLE_MESSAGE_MODES = frozenset({"substring", "exact"})


def message_predicate_pushable(message: Optional[str], mode: str) -> bool:
    """Return True when the message predicate can be pushed into SQL exhaustively.

    Empty/None ``message`` matches everything (no predicate needed); ``substring``
    and ``exact`` map cleanly to ``LIKE``/``instr``/equality; ``regex`` does not.
    """
    if not message:
        return False
    return mode in SQL_PUSHABLE_MESSAGE_MODES


def _escape_like(needle: str, escape: str = "\\") -> str:
    """Escape LIKE wildcards so the needle matches literally."""
    return (
        needle.replace(escape, escape + escape)
        .replace("%", escape + "%")
        .replace("_", escape + "_")
    )


def sqlite_message_clause(
    message: str,
    *,
    mode: str = "substring",
    case_sensitive: bool = False,
) -> Tuple[str, list]:
    """Build a SQLite WHERE fragment + params for a pushable message predicate.

    Mirrors :func:`message_matches` for ``substring``/``exact``. Case-insensitive
    matching uses ``lower()`` to match the Python ``.lower()`` casefolding the
    post-filter performed. Callers MUST gate on :func:`message_predicate_pushable`
    (regex/empty are not handled here).
    """
    if mode == "exact":
        if case_sensitive:
            return "message = ?", [message]
        return "lower(message) = lower(?)", [message]

    # substring (default)
    if case_sensitive:
        # ESCAPE makes wildcards literal; GLOB/instr would be case-sensitive but
        # instr keeps semantics simplest and index-agnostic.
        return "instr(message, ?) > 0", [message]
    return "instr(lower(message), lower(?)) > 0", [message]


def postgres_message_clause(
    message: str,
    placeholder: str,
    *,
    mode: str = "substring",
    case_sensitive: bool = False,
) -> Tuple[str, list]:
    """Build a Postgres WHERE fragment + params for a pushable message predicate.

    ``placeholder`` is the bind token (e.g. ``"$5"``). Mirrors
    :func:`message_matches` for ``substring``/``exact``. Substring uses
    ``position`` (case-insensitive via ``lower()``); exact uses equality.
    Callers MUST gate on :func:`message_predicate_pushable`.
    """
    if mode == "exact":
        if case_sensitive:
            return f"message = {placeholder}", [message]
        return f"lower(message) = lower({placeholder})", [message]

    # substring (default)
    if case_sensitive:
        return f"position({placeholder} IN message) > 0", [message]
    return f"position(lower({placeholder}) IN lower(message)) > 0", [message]


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
