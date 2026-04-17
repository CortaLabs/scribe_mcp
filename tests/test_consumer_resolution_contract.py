from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

import pytest

import scribe_mcp.tools.query_entries as query_entries_tool
import scribe_mcp.tools.read_recent as read_recent_tool
from scribe_mcp.shared.logging_utils import LoggingContext


@pytest.mark.asyncio
async def test_read_recent_exposes_shared_resolution_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

    class DummyBackend:
        async def fetch_project(self, _name: str) -> Any:
            return SimpleNamespace(name="consumer_contract_project", repo_root="/tmp", progress_log_path="/tmp/PROGRESS_LOG.md")

        async def fetch_recent_entries_paginated(self, **_kwargs: Any) -> Any:
            return [], 0

    fake_server = SimpleNamespace(
        state_manager=DummyStateManager(),
        storage_backend=DummyBackend(),
        get_execution_context=lambda: None,
    )

    context = LoggingContext(
        tool_name="read_recent",
        project={"name": "consumer_contract_project", "root": "/tmp", "progress_log": "/tmp/PROGRESS_LOG.md"},
        recent_projects=["consumer_contract_project"],
        state_snapshot={"tool": "read_recent"},
        reminders=[],
        resolution_source="session_binding",
        fallback_used=False,
        fallback_chain=[],
    )

    async def fake_prepare_context(**_kwargs: Any) -> LoggingContext:
        return context

    monkeypatch.setattr(read_recent_tool, "server_module", fake_server)
    monkeypatch.setattr(read_recent_tool._READ_RECENT_HELPER, "server_module", fake_server)
    monkeypatch.setattr(read_recent_tool._READ_RECENT_HELPER, "prepare_context", fake_prepare_context)

    result = await read_recent_tool.read_recent(agent="CoderAgent", format="structured", page_size=5)

    assert result["ok"] is True
    assert result["project"] == "consumer_contract_project"
    assert result["project_resolution"]["resolution_source"] == "session_binding"
    assert result["project_resolution"]["fallback_used"] is False


@pytest.mark.asyncio
async def test_query_entries_exposes_shared_resolution_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

    fake_server = SimpleNamespace(state_manager=DummyStateManager())
    monkeypatch.setattr(query_entries_tool, "server_module", fake_server)

    context = LoggingContext(
        tool_name="query_entries",
        project={"name": "consumer_contract_project", "root": "/tmp", "progress_log": "/tmp/PROGRESS_LOG.md"},
        recent_projects=["consumer_contract_project"],
        state_snapshot={"tool": "query_entries"},
        reminders=[],
        resolution_source="session_binding",
        fallback_used=False,
        fallback_chain=[],
    )

    async def fake_resolve_logging_context(**_kwargs: Any) -> LoggingContext:
        return context

    async def fake_execute_search_with_fallbacks(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "entries": [],
            "pagination": {"page": 1, "page_size": 10, "total_count": 0},
            "total_found": 0,
            "returned": 0,
        }

    monkeypatch.setattr(query_entries_tool, "resolve_logging_context", fake_resolve_logging_context)
    monkeypatch.setattr(query_entries_tool, "_execute_search_with_fallbacks", fake_execute_search_with_fallbacks)

    result = await query_entries_tool.query_entries(project="consumer_contract_project", format="structured")

    assert result["ok"] is True
    assert result["project"] == "consumer_contract_project"
    assert result["project_resolution"]["resolution_source"] == "session_binding"
    assert result["project_resolution"]["fallback_used"] is False
