from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import scribe_mcp.tools.append_entry as append_entry_tool


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize(
    ("content_kwargs", "unexpected_parameters"),
    [
        ({}, []),
        ({"content": "This text must not be silently discarded"}, ["content"]),
        ({"message": " \t\n"}, []),
    ],
)
async def test_append_entry_rejects_hollow_single_entries_before_context_resolution(
    content_kwargs: dict[str, str],
    unexpected_parameters: list[str],
    monkeypatch: pytest.MonkeyPatch,
    test_agent: str,
) -> None:
    """A missing or misnamed message must fail before any logging side effect."""
    resolve_logging_context = AsyncMock(
        side_effect=AssertionError("context resolution must not run for invalid content")
    )
    monkeypatch.setattr(
        append_entry_tool,
        "resolve_logging_context",
        resolve_logging_context,
    )

    result = await append_entry_tool.append_entry(
        agent=test_agent,
        **content_kwargs,
    )

    assert result["ok"] is False
    assert result.get("error_code") == "APPEND_ENTRY_CONTENT_REQUIRED", result
    assert result["unexpected_parameters"] == unexpected_parameters
    assert "no log entry was written" in result["error"]
    resolve_logging_context.assert_not_awaited()
