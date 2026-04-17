"""Unit tests for utility helpers and state management."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

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
async def test_set_project_rejects_log_outside_root():
    safe_root = settings.project_root.resolve() / ".tmp_set_project_tests" / f"safe_root_{uuid.uuid4().hex[:8]}"
    outside_log = safe_root.parent / "elsewhere" / "PROGRESS_LOG.md"
    result = await set_project.set_project(
        agent="test_agent",
        name=f"malicious-{uuid.uuid4().hex[:8]}",
        root=str(safe_root),
        progress_log=str(outside_log),
        skip_validation=True,
    )
    assert not result["ok"]
    assert "Progress log must be within the project root." in result["error"]


@pytest.mark.asyncio
async def test_set_project_denies_external_root_by_default(tmp_path: Path):
    external_root = tmp_path / "external_repo"
    result = await set_project.set_project(
        agent="test_agent",
        name="external_project",
        root=str(external_root),
        format="structured",
    )

    assert not result["ok"]
    assert "outside trusted workspace scope" in result["error"]
    assert not external_root.exists()


@pytest.mark.asyncio
async def test_set_project_allows_external_root_with_explicit_compat_opt_in(tmp_path: Path, monkeypatch):
    external_root = tmp_path / "external_repo"

    async def _no_slug_collision(_name: str):
        return None

    monkeypatch.setattr(set_project, "_check_slug_collision", _no_slug_collision)
    monkeypatch.setattr(set_project.server_module, "storage_backend", None)
    monkeypatch.setattr(set_project.server_module.state_manager, "_storage_backend", None, raising=False)

    result = await set_project.set_project(
        agent="test_agent",
        name=f"external_project_{uuid.uuid4().hex[:8]}",
        root=str(external_root),
        skip_validation=True,
        format="structured",
    )

    try:
        assert result["ok"]
        assert Path(result["project"]["root"]).resolve() == external_root.resolve()
        expected_docs = external_root / settings.dev_plans_base / result["project"]["name"]
        assert Path(result["project"]["progress_log"]).resolve() == (expected_docs / "PROGRESS_LOG.md").resolve()
        assert result["root_authorization"]["skip_validation_requested"] is True
        assert result["root_authorization"]["compatibility_override_used"] is True
        assert result["root_authorization"]["authorization_mode"] == "compatibility_opt_in"
    finally:
        if external_root.exists():
            shutil.rmtree(external_root)


@pytest.mark.asyncio
async def test_set_project_respects_auto_create_dirs_false(tmp_path: Path):
    missing_root = tmp_path / "missing_root"
    result = await set_project.set_project(
        agent="test_agent",
        name="missing_project",
        root=str(missing_root),
        auto_create_dirs=False,
        skip_validation=True,
        format="structured",
    )

    assert not result["ok"]
    assert "auto_create_dirs is disabled" in result["error"]
    assert not missing_root.exists()


@pytest.mark.asyncio
async def test_set_project_require_explicit_root_missing_root_fails_closed(monkeypatch):
    monkeypatch.setattr(set_project, "_get_context_repo_root", lambda: None)

    result = await set_project.set_project(
        agent="test_agent",
        name=f"explicit-root-required-{uuid.uuid4().hex[:8]}",
        root="",
        format="structured",
    )

    assert not result["ok"]
    assert "Explicit trusted project root required" in result["error"]


@pytest.mark.asyncio
async def test_set_project_rejected_root_leaves_binding_and_docs_untouched(tmp_path: Path, monkeypatch):
    async def _no_slug_collision(_name: str):
        return None

    monkeypatch.setattr(set_project, "_check_slug_collision", _no_slug_collision)
    monkeypatch.setattr(set_project.server_module, "storage_backend", None)
    monkeypatch.setattr(set_project.server_module.state_manager, "_storage_backend", None, raising=False)

    state_before = await set_project.server_module.state_manager.load()
    current_before = state_before.current_project

    rejected_root = tmp_path / "rejected_external"
    rejected_name = f"rejected-{uuid.uuid4().hex[:8]}"
    rejected_result = await set_project.set_project(
        agent="test_agent",
        name=rejected_name,
        root=str(rejected_root),
        format="structured",
    )

    assert not rejected_result["ok"]
    assert "outside trusted workspace scope" in rejected_result["error"]
    assert not rejected_root.exists()
    assert not (rejected_root / settings.dev_plans_base / rejected_name).exists()

    state_after = await set_project.server_module.state_manager.load()
    assert state_after.current_project == current_before


@pytest.mark.asyncio
async def test_state_manager_db_persistence_without_state_file_writes(tmp_path: Path):
    state_file = tmp_path / "state.json"
    db_file = state_file.with_suffix(".db")
    manager = StateManager(path=state_file)

    final_state = await manager.set_current_project(
        "proj1",
        {"name": "proj1", "root": ".", "progress_log": "./log"},
    )
    assert final_state.current_project == "proj1"
    assert db_file.exists()
    assert not state_file.exists()

    loaded = await manager.load()
    assert loaded.current_project == "proj1"


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
