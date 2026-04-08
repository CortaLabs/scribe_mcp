"""Unit tests for shared.base_logging_tool.LoggingToolMixin."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext


class DummyTool(LoggingToolMixin):
    def __init__(self, server_module: Any = object()) -> None:
        self.server_module = server_module


@pytest.mark.asyncio
async def test_prepare_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}
    context = LoggingContext(
        tool_name="append_entry",
        project={"name": "demo"},
        recent_projects=["demo"],
        state_snapshot={"tool": "append_entry"},
        reminders=[],
    )

    async def fake_resolve_logging_context(**kwargs):
        captured.update(kwargs)
        return context

    tool = DummyTool(server_module=object())

    monkeypatch.setattr(
        "scribe_mcp.shared.base_logging_tool.resolve_logging_context",
        fake_resolve_logging_context,
    )

    result = await tool.prepare_context(
        tool_name="append_entry",
        agent_id="agent-123",
        explicit_project=None,
        require_project=True,
        state_snapshot={"tool": "append_entry"},
    )

    assert result is context
    assert captured["tool_name"] == "append_entry"
    assert captured["agent_id"] == "agent-123"


def test_error_response_appends_context() -> None:
    context = LoggingContext(
        tool_name="append_entry",
        project={"name": "demo"},
        recent_projects=["demo"],
        state_snapshot={},
        reminders=[{"message": "ping"}],
    )

    payload = LoggingToolMixin.error_response(
        "Something went wrong",
        suggestion="Check input",
        context=context,
        extra={"code": 400},
    )

    assert payload["ok"] is False
    assert payload["error"] == "Something went wrong"
    assert payload["suggestion"] == "Check input"
    assert payload["recent_projects"] == ["demo"]
    assert payload["reminders"] == [{"message": "ping"}]


def test_success_with_entries_uses_formatter(monkeypatch: pytest.MonkeyPatch) -> None:
    formatted_calls: List[Dict[str, Any]] = []

    def fake_format_response(**kwargs):
        formatted_calls.append(kwargs)
        return {"ok": True, "entries": kwargs["entries"]}

    monkeypatch.setattr(
        "scribe_mcp.shared.base_logging_tool.default_formatter.format_response",
        fake_format_response,
    )

    context = LoggingContext(
        tool_name="query_entries",
        project={"name": "demo"},
        recent_projects=["demo"],
        state_snapshot={},
        reminders=[],
    )

    response = LoggingToolMixin.success_with_entries(
        entries=[{"message": "hi"}],
        context=context,
        compact=True,
        fields=["message"],
        include_metadata=False,
        pagination={"page": 1},
        extra_data={"foo": "bar"},
    )

    assert formatted_calls
    assert response["reminders"] == []
    assert response["recent_projects"] == ["demo"]


def test_validate_metadata_requirements() -> None:
    definition = {"metadata_requirements": ["doc", "section"]}
    missing = LoggingToolMixin.validate_metadata_requirements(definition, {"doc": "a"})
    assert missing == "Missing metadata for log entry: section"


def test_translate_project_error() -> None:
    from scribe_mcp.shared.logging_utils import ProjectResolutionError

    error = ProjectResolutionError("no project", ["demo"])
    payload = LoggingToolMixin.translate_project_error(error)
    assert payload["ok"] is False
    assert payload["recent_projects"] == ["demo"]
