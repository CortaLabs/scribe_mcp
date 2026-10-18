from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.shared.project_utils import merge_project_inventory_authority
from scribe_mcp.tools import list_projects as list_projects_module


@pytest.mark.asyncio
async def test_list_projects_uses_shared_inventory_authority_helper(monkeypatch):
    calls: list[dict] = []

    def _recording_helper(canonical, *, state_overlay=None, registry_info=None, backend_available=True):
        calls.append(
            {
                "canonical": dict(canonical),
                "has_state": state_overlay is not None,
                "has_registry": registry_info is not None,
                "backend_available": backend_available,
            }
        )
        merged = dict(canonical)
        if state_overlay:
            merged.update(state_overlay)
        return merged

    backend_record = SimpleNamespace(
        name="demo",
        repo_root="/tmp/demo",
        progress_log_path="/tmp/demo/PROGRESS_LOG.md",
    )
    backend = SimpleNamespace(
        list_projects_by_repo=AsyncMock(return_value=[backend_record]),
        count_entries=AsyncMock(return_value=0),
    )
    state_manager = SimpleNamespace(
        record_tool=AsyncMock(return_value={"tool": "list_projects"}),
        load=AsyncMock(return_value=SimpleNamespace(projects={"demo": {"status": "in_progress"}})),
    )
    fake_server = SimpleNamespace(
        state_manager=state_manager,
        storage_backend=backend,
        get_agent_identity=lambda: None,
    )

    monkeypatch.setattr(list_projects_module, "server_module", fake_server)
    monkeypatch.setattr(list_projects_module._LIST_PROJECTS_HELPER, "server_module", fake_server)
    monkeypatch.setattr(
        list_projects_module._LIST_PROJECTS_HELPER,
        "prepare_context",
        AsyncMock(
            return_value=LoggingContext(
                tool_name="list_projects",
                project=None,
                recent_projects=[],
                state_snapshot={},
                reminders=[],
            )
        ),
    )
    monkeypatch.setattr(list_projects_module, "get_current_repo_config", lambda: ("/tmp", None))
    monkeypatch.setattr(list_projects_module, "merge_project_inventory_authority", _recording_helper)
    monkeypatch.setattr(list_projects_module._PROJECT_REGISTRY, "get_project", lambda _name: None)
    monkeypatch.setattr(list_projects_module, "detect_project_state", lambda *_args, **_kwargs: ("NEW", "ok"))

    result = await list_projects_module.list_projects(format="structured", include_test=True, limit=10)

    assert result["ok"] is True
    assert result["count"] == 1
    assert calls
    assert any(call["has_state"] for call in calls)


@pytest.mark.asyncio
async def test_list_projects_only_counts_entries_for_returned_page(monkeypatch):
    backend_records = [
        SimpleNamespace(
            name=f"demo_{idx}",
            repo_root="/tmp/demo",
            progress_log_path=f"/tmp/demo/PROGRESS_LOG_{idx}.md",
        )
        for idx in range(3)
    ]
    backend = SimpleNamespace(
        list_projects_by_repo=AsyncMock(return_value=backend_records),
        count_entries=AsyncMock(return_value=0),
    )
    state_manager = SimpleNamespace(
        record_tool=AsyncMock(return_value={"tool": "list_projects"}),
        load=AsyncMock(return_value=SimpleNamespace(projects={})),
    )
    fake_server = SimpleNamespace(
        state_manager=state_manager,
        storage_backend=backend,
        get_agent_identity=lambda: None,
    )

    monkeypatch.setattr(list_projects_module, "server_module", fake_server)
    monkeypatch.setattr(list_projects_module._LIST_PROJECTS_HELPER, "server_module", fake_server)
    monkeypatch.setattr(
        list_projects_module._LIST_PROJECTS_HELPER,
        "prepare_context",
        AsyncMock(
            return_value=LoggingContext(
                tool_name="list_projects",
                project=None,
                recent_projects=[],
                state_snapshot={},
                reminders=[],
            )
        ),
    )
    monkeypatch.setattr(list_projects_module, "get_current_repo_config", lambda: ("/tmp/demo", None))
    monkeypatch.setattr(list_projects_module._PROJECT_REGISTRY, "get_project", lambda _name: None)
    monkeypatch.setattr(list_projects_module, "detect_project_state", lambda *_args, **_kwargs: ("NEW", "ok"))

    result = await list_projects_module.list_projects(format="structured", include_test=True, limit=1)

    assert result["ok"] is True
    assert result["count"] == 1
    assert backend.count_entries.await_count == 1


def test_merge_project_inventory_authority_preserves_backend_status_over_registry():
    registry_info = SimpleNamespace(status="planning", total_entries=99, last_entry_at="from-registry")
    merged = merge_project_inventory_authority(
        {"name": "demo", "status": "in_progress", "total_entries": 7},
        registry_info=registry_info,
        backend_available=True,
    )

    assert merged["status"] == "in_progress"
    assert merged["total_entries"] == 7
