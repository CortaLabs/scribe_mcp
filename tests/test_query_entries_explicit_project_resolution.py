from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

import scribe_mcp.tools.query_entries as query_entries_tool


@pytest.mark.asyncio
async def test_query_entries_passes_explicit_project_to_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Optional[str]] = {"explicit_project": None}

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

    monkeypatch.setattr(
        query_entries_tool,
        "server_module",
        SimpleNamespace(state_manager=DummyStateManager()),
    )

    async def fake_resolve_logging_context(*, explicit_project: Optional[str] = None, **_kwargs: Any) -> Any:
        captured["explicit_project"] = explicit_project
        return SimpleNamespace(project=None, recent_projects=[], reminders=[])

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

    result = await query_entries_tool.query_entries(
        project="council_mcp_v2",
        message="anything",
        format="structured",
        page_size=1,
    )

    assert captured["explicit_project"] == "council_mcp_v2"
    assert result["ok"] is True

