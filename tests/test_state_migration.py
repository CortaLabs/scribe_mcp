from __future__ import annotations

import json
from pathlib import Path

import pytest

from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.migration import migrate_legacy_state_file
from scribe_mcp.storage.sqlite import SQLiteStorage


pytestmark = pytest.mark.asyncio


async def test_migrate_legacy_state_file_moves_payload_into_db(tmp_path: Path) -> None:
    db_path = tmp_path / "scribe.db"
    state_path = tmp_path / "state.json"

    state_payload = {
        "current_project": "proj_alpha",
        "projects": {
            "proj_alpha": {
                "name": "proj_alpha",
                "root": str(tmp_path),
                "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
                "docs": {"checklist": str(tmp_path / "CHECKLIST.md")},
            }
        },
        "session_projects": {
            "session-1": {
                "name": "proj_alpha",
                "root": str(tmp_path),
                "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
            }
        },
        "session_modes": {"session-1": "project"},
        "recent_tools": [
            {"name": "set_project", "ts": "2026-02-12 00:00:00 UTC"},
            {"name": "append_entry", "ts": "2026-02-12 00:01:00 UTC"},
        ],
    }
    state_path.write_text(json.dumps(state_payload, indent=2), encoding="utf-8")

    backend = SQLiteStorage(db_path)
    await backend.setup()

    result = await migrate_legacy_state_file(
        storage_backend=backend,
        state_path=state_path,
        rename_source=True,
    )

    assert result.migrated is True
    assert result.projects_migrated == 1
    assert result.session_projects_migrated == 1
    assert result.session_modes_migrated == 1

    assert not state_path.exists()
    assert result.renamed_to is not None
    assert Path(result.renamed_to).exists()

    project = await backend.fetch_project("proj_alpha")
    assert project is not None

    agent_project = await backend.get_agent_project("Scribe")
    assert agent_project is not None
    assert agent_project["project_name"] == "proj_alpha"

    session_project = await backend.get_session_project("session-1")
    assert session_project == "proj_alpha"

    session_mode = await backend.get_session_mode("session-1")
    assert session_mode == "project"

    migrated_activity = await backend.get_session_activity("__legacy_state_migration__")
    assert migrated_activity is not None
    assert "set_project" in migrated_activity["recent_tools"]
    assert "append_entry" in migrated_activity["recent_tools"]


async def test_migrate_legacy_state_file_is_idempotent_when_source_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "scribe.db"
    state_path = tmp_path / "state.json"

    backend = SQLiteStorage(db_path)
    await backend.setup()

    first = await migrate_legacy_state_file(
        storage_backend=backend,
        state_path=state_path,
        rename_source=True,
    )
    second = await migrate_legacy_state_file(
        storage_backend=backend,
        state_path=state_path,
        rename_source=True,
    )

    assert first.migrated is False
    assert second.migrated is False


async def test_state_manager_uses_injected_storage_backend(tmp_path: Path) -> None:
    injected_db = tmp_path / "injected.db"
    fallback_db = tmp_path / "state.db"

    backend = SQLiteStorage(injected_db)
    await backend.setup()

    manager = StateManager(path=tmp_path / "state.json", storage_backend=backend)
    state = await manager.set_current_project(
        "proj_backend",
        {
            "name": "proj_backend",
            "root": str(tmp_path),
            "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
        },
    )

    assert state.current_project == "proj_backend"
    assert await backend.fetch_project("proj_backend") is not None
    assert not fallback_db.exists()
