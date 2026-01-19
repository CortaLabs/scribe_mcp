"""Unit tests for utility helpers and state management."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import sys

# Add the MCP_SPINE directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.state.manager import StateManager
from scribe_mcp.config.settings import settings
from scribe_mcp.tools import set_project
from scribe_mcp.tools.append_entry import (
    _normalise_meta,
    _sanitize_identifier,
    _validate_message,
)
from scribe_mcp.shared.logging_utils import _clean_meta_value


def test_sanitize_identifier_strips_brackets():
    assert _sanitize_identifier("[Agent: Test]") == "Agent: Test"
    assert _sanitize_identifier("|Scribe|") == "Scribe"
    assert _sanitize_identifier("   ") == "Scribe"


def test_validate_message_disallows_newlines_and_pipes():
    assert _validate_message("hello\nworld") == "Message cannot contain newline characters."
    assert _validate_message("pipe | value") == "Message cannot contain pipe characters."
    assert _validate_message("valid message") is None


def test_normalise_meta_orders_and_sanitises_keys():
    meta = {"b key": "value\nline", "a": 1}
    pairs = _normalise_meta(meta)
    assert pairs == (("a", "1"), ("b_key", "value line"))


def test_clean_meta_value_replaces_newlines_and_pipes():
    assert _clean_meta_value("line1\nline2|x") == "line1 line2 x"


@pytest.mark.asyncio
async def test_set_project_rejects_log_outside_root(tmp_path: Path):
    safe_root = tmp_path / "safe_root"
    outside_log = tmp_path / "elsewhere" / "PROGRESS_LOG.md"
    result = await set_project.set_project(
        name="malicious",
        root=str(safe_root),
        progress_log=str(outside_log),
    )
    assert not result["ok"]
    assert "Progress log must be within the project root." in result["error"]


@pytest.mark.asyncio
async def test_set_project_allows_external_root(tmp_path: Path):
    external_root = tmp_path / "external_repo"
    result = await set_project.set_project(
        name="external_project",
        root=str(external_root),
    )

    try:
        assert result["ok"]
        assert Path(result["project"]["root"]).resolve() == external_root.resolve()
        expected_docs = external_root / settings.dev_plans_base / "external_project"
        assert Path(result["project"]["progress_log"]).resolve() == (expected_docs / "PROGRESS_LOG.md").resolve()
    finally:
        if external_root.exists():
            shutil.rmtree(external_root)


@pytest.mark.asyncio
async def test_state_manager_atomic_write_and_backup(tmp_path: Path):
    state_file = tmp_path / "state.json"
    manager = StateManager(path=state_file)

    # First write to populate state file
    final_state = await manager.set_current_project(
        "proj1",
        {"name": "proj1", "root": ".", "progress_log": "./log"},
    )
    assert final_state.current_project == "proj1"
    assert state_file.exists()

    # Simulate corruption in main file but intact backup
    state_file.write_text("{ invalid json", encoding="utf-8")
    backup = state_file.with_suffix(state_file.suffix + ".tmp")
    backup.write_text(json.dumps({"current_project": "proj2", "projects": {}, "recent_projects": []}), encoding="utf-8")

    loaded = await manager.load()
    assert loaded.current_project == "proj2"


@pytest.mark.asyncio
async def test_state_manager_session_project_does_not_overwrite_global(tmp_path: Path):
    state_file = tmp_path / "state.json"
    manager = StateManager(path=state_file)

    await manager.set_current_project(
        "proj1",
        {"name": "proj1", "root": ".", "progress_log": "./log"},
    )

    updated = await manager.set_current_project(
        "proj2",
        {"name": "proj2", "root": ".", "progress_log": "./log2"},
        session_id="session-1",
        mirror_global=False,
    )

    assert updated.current_project == "proj1"
    assert updated.session_projects["session-1"]["name"] == "proj2"
