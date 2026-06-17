from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from scribe_mcp import reminders
from scribe_mcp import server as server_module
from scribe_mcp.state import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.reminder_tools import (
    configure_reminders,
    query_reminders,
    reset_reminders,
)


def _as_dict(result):
    if isinstance(result, dict):
        return result
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    return {}


def _build_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "reminder_tool_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "phase_9_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase Plan\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Progress\n", encoding="utf-8")

    return {
        "name": "phase_9_project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "Codex"},
    }


@pytest_asyncio.fixture
async def reminder_runtime(tmp_path: Path):
    project = _build_project(tmp_path)
    storage = SQLiteStorage(tmp_path / "reminder_tools.db")
    await storage.setup()

    # Register the transport session before binding a project to it. The
    # session_projects FK requires a live scribe_sessions row; set_current_project
    # writes the binding but does not create the parent session, so the fixture
    # must register it first (mirrors real set_project / set_session_mode flow).
    await storage.upsert_session(
        session_id="phase9-session",
        agent_id="Codex",
        repo_root=project["root"],
    )

    state_manager = StateManager(path=tmp_path / "state.json", storage_backend=storage)
    await state_manager.set_current_project(
        project["name"],
        project,
        agent_id="Codex",
        session_id="phase9-session",
    )

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend

    server_module.state_manager = state_manager
    server_module.storage_backend = storage
    reminders.reload_reminders()

    try:
        yield project
    finally:
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend
        reminders.reload_reminders()
        await storage.close()


def test_reminder_tools_registered() -> None:
    tools = set(server_module.list_registered_tools())
    assert "query_reminders" in tools
    assert "configure_reminders" in tools
    assert "reset_reminders" in tools


@pytest.mark.asyncio
async def test_query_reminders_returns_history_and_active(reminder_runtime: dict) -> None:
    project_name = reminder_runtime["name"]

    first = _as_dict(
        await query_reminders(
            agent="Codex",
            project=project_name,
            format="structured",
        )
    )
    assert first.get("ok") is True

    second = _as_dict(
        await query_reminders(
            agent="Codex",
            project=project_name,
            limit=25,
            format="structured",
        )
    )
    assert second.get("ok") is True
    assert isinstance(second.get("history"), list)
    assert isinstance(second.get("active_reminders"), list)
    assert len(second.get("history", [])) >= 1


@pytest.mark.asyncio
async def test_configure_reminders_updates_project_defaults(reminder_runtime: dict) -> None:
    project_name = reminder_runtime["name"]

    result = _as_dict(
        await configure_reminders(
            agent="Codex",
            project=project_name,
            enabled=False,
            cooldown_minutes=7,
            categories=["logging", "context"],
            tone="strict",
            format="structured",
        )
    )

    assert result.get("ok") is True
    settings = result.get("reminder_settings", {})
    assert settings.get("enabled") is False
    assert settings.get("cooldown_minutes") == 7
    assert settings.get("tone") == "strict"
    assert settings.get("categories") == ["logging", "context"]

    state = await server_module.state_manager.load()
    project_state = state.get_project(project_name) or {}
    assert project_state.get("defaults", {}).get("reminder", {}).get("tone") == "strict"


@pytest.mark.asyncio
async def test_reset_reminders_clears_history(reminder_runtime: dict) -> None:
    project_name = reminder_runtime["name"]
    project_root = reminder_runtime["root"]

    await query_reminders(agent="Codex", project=project_name, format="structured")

    history_before = await reminders.get_reminder_history(
        project_root=project_root,
        agent_id="Codex",
        limit=50,
    )
    assert len(history_before) >= 1

    reset_result = _as_dict(
        await reset_reminders(
            agent="Codex",
            project=project_name,
            reset_cooldowns=True,
            reset_history=True,
            format="structured",
        )
    )
    assert reset_result.get("ok") is True
    assert reset_result.get("history_cleared", 0) >= 1

    history_after = await reminders.get_reminder_history(
        project_root=project_root,
        agent_id="Codex",
        limit=50,
    )
    assert history_after == []
