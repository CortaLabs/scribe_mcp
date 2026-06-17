"""Regex pre-validation tests for the ``query_entries`` MCP tool (WS1 F7).

Prior behavior: a malformed ``message_mode="regex"`` pattern was swallowed
per-entry in ``utils.search.message_matches`` (``except re.error: return False``),
so the query returned an empty result set indistinguishable from a valid query
that genuinely matched nothing.

F7 compiles the user's pattern ONCE at the tool boundary and returns a teaching
error dict (naming the offending pattern and the regex error, suggesting
substring mode) instead of silently matching nothing. The per-entry fast path in
``utils/search.py`` is intentionally left unchanged.
"""

from __future__ import annotations

import asyncio
import json

from scribe_mcp.tools.query_entries import query_entries


def _result_dict(raw):
    if isinstance(raw, dict):
        return raw
    try:
        from mcp.types import CallToolResult, TextContent

        if isinstance(raw, CallToolResult) and raw.content:
            first = raw.content[0]
            if isinstance(first, TextContent):
                return json.loads(first.text)
    except ImportError:
        pass
    return {"ok": True}


def _run(coro):
    return asyncio.run(coro)


def test_invalid_regex_returns_teaching_error_naming_pattern():
    bad_pattern = "[invalid(regex"
    raw = _run(
        query_entries(
            agent="test-agent",
            message=bad_pattern,
            message_mode="regex",
            format="structured",
        )
    )
    result = _result_dict(raw)
    assert result["ok"] is False
    # The error names the offending pattern and the regex failure reason.
    assert bad_pattern in result["error"]
    assert "Invalid regex pattern" in result["error"]
    # The teaching suggestion points at the substring escape hatch.
    assert "substring" in result["suggestion"]
    # Empty result envelope is preserved so callers see no spurious matches.
    assert result["entries"] == []
    assert result["pagination"]["total_count"] == 0


def test_invalid_regex_distinguishable_from_genuine_zero_match():
    """A bad pattern (ok=False) must be distinguishable from a real zero-result query.

    The whole point of F7: previously both produced an empty result set with no
    signal. The teaching error gives the bad pattern an ``ok=False`` + ``error``
    that a genuine zero-match query never carries.
    """
    raw = _run(
        query_entries(
            agent="test-agent",
            message="(unbalanced",
            message_mode="regex",
            format="structured",
        )
    )
    result = _result_dict(raw)
    assert result["ok"] is False
    assert "error" in result
