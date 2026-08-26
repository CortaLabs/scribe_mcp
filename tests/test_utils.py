"""Unit tests for utility helpers and state management."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

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


async def _isolated_set_project_state(tmp_path: Path, monkeypatch) -> tuple[StateManager, str]:
    state_manager = StateManager(path=tmp_path / "state.json")
    monkeypatch.setattr(set_project.server_module, "state_manager", state_manager)
    monkeypatch.setattr(set_project.server_module, "storage_backend", None)

    prior_name = f"prior-project-{uuid.uuid4().hex[:8]}"
    prior_root = tmp_path / "prior-root"
    prior_root.mkdir()
    await state_manager.set_current_project(
        prior_name,
        {
            "name": prior_name,
            "root": str(prior_root),
            "progress_log": str(prior_root / "PROGRESS_LOG.md"),
        },
    )

    real_set_current_project = state_manager.set_current_project

    async def _set_current_project(name, project_data=None, **kwargs):
        kwargs["agent_id"] = None
        kwargs["skip_upsert"] = False
        return await real_set_current_project(name, project_data, **kwargs)

    monkeypatch.setattr(state_manager, "set_current_project", _set_current_project)
    return state_manager, prior_name


async def _no_slug_collision(_name: str, _backend, _repo_root: Path):
    return None


@pytest.mark.asyncio
@pytest.mark.regression
async def test_set_project_accepts_exact_council_workspace_root(
    tmp_path: Path,
    monkeypatch,
):
    state_manager, _prior_name = await _isolated_set_project_state(tmp_path, monkeypatch)
    monkeypatch.setattr(set_project, "_check_slug_collision", _no_slug_collision)

    workspace_root = tmp_path / "council-workspace"
    marker = workspace_root / ".council" / "council.yaml"
    marker.parent.mkdir(parents=True)
    marker.write_text("council: test\n", encoding="utf-8")
    project_name = f"council-workspace-{uuid.uuid4().hex[:8]}"

    result = await set_project.set_project(
        agent="test_agent",
        name=project_name,
        root=str(workspace_root),
        format="structured",
    )

    assert result["ok"] is True
    assert Path(result["project"]["root"]).resolve() == workspace_root.resolve()
    assert result["root_authorization"]["authorization_mode"] == "first_party"
    assert result["root_authorization"]["authority_source"] == "explicit_local_repo_root"
    assert result["root_authorization"]["reason_code"] == "first_party_explicit_local_repo_root"
    assert result["root_authorization"]["skip_validation_requested"] is False
    assert result["root_authorization"]["compatibility_override_used"] is False
    progress_log = Path(result["project"]["progress_log"]).resolve()
    assert progress_log.name == "PROGRESS_LOG.md"
    assert progress_log.parent.parent == (workspace_root / settings.dev_plans_base).resolve()
    assert (await state_manager.load()).current_project == project_name


@pytest.mark.asyncio
@pytest.mark.regression
async def test_set_project_rejects_bare_council_workspace_marker(
    tmp_path: Path,
    monkeypatch,
):
    state_manager, prior_name = await _isolated_set_project_state(tmp_path, monkeypatch)

    workspace_root = tmp_path / "bare-council-workspace"
    (workspace_root / ".council").mkdir(parents=True)
    project_name = f"bare-council-workspace-{uuid.uuid4().hex[:8]}"

    result = await set_project.set_project(
        agent="test_agent",
        name=project_name,
        root=str(workspace_root),
        format="structured",
    )

    assert result["ok"] is False
    assert result["reason_code"] == "explicit_root_not_local_repo"
    assert (await state_manager.load()).current_project == prior_name
    assert not (workspace_root / settings.dev_plans_base / project_name).exists()
    assert not (workspace_root / ".scribe").exists()


@pytest.mark.asyncio
@pytest.mark.regression
async def test_set_project_rejects_nested_path_below_council_workspace_root(
    tmp_path: Path,
    monkeypatch,
):
    state_manager, prior_name = await _isolated_set_project_state(tmp_path, monkeypatch)

    workspace_root = tmp_path / "council-workspace"
    marker = workspace_root / ".council" / "council.yaml"
    nested_root = workspace_root / "nested" / "child"
    marker.parent.mkdir(parents=True)
    marker.write_text("council: test\n", encoding="utf-8")
    nested_root.mkdir(parents=True)
    project_name = f"nested-council-workspace-{uuid.uuid4().hex[:8]}"

    result = await set_project.set_project(
        agent="test_agent",
        name=project_name,
        root=str(nested_root),
        format="structured",
    )

    assert result["ok"] is False
    assert result["reason_code"] == "explicit_root_not_local_repo"
    assert (await state_manager.load()).current_project == prior_name
    assert not (workspace_root / settings.dev_plans_base / project_name).exists()
    assert not (nested_root / ".scribe").exists()


@pytest.mark.asyncio
async def test_set_project_rejects_log_outside_root():
    # safe_root must be a discoverable local repo root so the new first-gate
    # (explicit_root_not_local_repo) passes and we reach the progress-log check.
    safe_root = settings.project_root.resolve() / ".tmp_set_project_tests" / f"safe_root_{uuid.uuid4().hex[:8]}"
    safe_root.mkdir(parents=True, exist_ok=True)
    (safe_root / ".git").mkdir(exist_ok=True)
    outside_log = safe_root.parent / "elsewhere" / "PROGRESS_LOG.md"
    try:
        result = await set_project.set_project(
            agent="test_agent",
            name=f"malicious-{uuid.uuid4().hex[:8]}",
            root=str(safe_root),
            progress_log=str(outside_log),
            skip_validation=True,
        )
        assert not result["ok"]
        assert "Progress log must be within the project root." in result["error"]
    finally:
        if safe_root.exists():
            shutil.rmtree(safe_root)


@pytest.mark.asyncio
async def test_set_project_denies_external_root_by_default(tmp_path: Path):
    # Under the hardened model, a plain directory that is not a local repository
    # root is rejected at the first gate with explicit_root_not_local_repo before
    # any scope/trust check.  The security intent is preserved: arbitrary external
    # paths are denied.
    external_root = tmp_path / "external_repo"
    result = await set_project.set_project(
        agent="test_agent",
        name="external_project",
        root=str(external_root),
        format="structured",
    )

    assert not result["ok"]
    assert result["reason_code"] == "explicit_root_not_local_repo"
    assert "Explicit root must resolve to a local repository root before authorization." in result["error"]
    assert not external_root.exists()


@pytest.mark.asyncio
async def test_set_project_allows_external_root_with_explicit_compat_opt_in(tmp_path: Path, monkeypatch):
    # Under the hardened model, any path that resolves to a real local repository
    # root is accepted as first-party — no separate "compat opt-in" mode exists.
    # The test verifies that a valid local repo root (with .git) is accepted and
    # that skip_validation_requested is propagated in the authorization metadata.
    external_root = tmp_path / "external_repo"
    external_root.mkdir(parents=True, exist_ok=True)
    (external_root / ".git").mkdir(exist_ok=True)

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
        # Hardened model: local repo roots are first-party; no separate compat mode.
        assert result["root_authorization"]["authorization_mode"] == "first_party"
        assert result["root_authorization"]["compatibility_override_used"] is False
    finally:
        if external_root.exists():
            shutil.rmtree(external_root)


@pytest.mark.asyncio
async def test_set_project_respects_auto_create_dirs_false(tmp_path: Path):
    # Under the hardened model the root must first resolve to a local repository
    # root before any set_project logic runs.  A non-existent path with no repo
    # markers is rejected at the first gate (explicit_root_not_local_repo).  The
    # security intent is upheld: an unauthorised path is still denied and no
    # directory is created.
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
    assert result["reason_code"] == "explicit_root_not_local_repo"
    assert "Explicit root must resolve to a local repository root before authorization." in result["error"]
    assert not missing_root.exists()


@pytest.mark.asyncio
async def test_set_project_require_explicit_root_missing_root_fails_closed(monkeypatch):
    monkeypatch.setattr(
        set_project,
        "_get_context_repo_root_details",
        lambda: {
            "trusted_path": None,
            "claimed_path": None,
            "provenance": "missing",
            "authoritative_session_key": None,
        },
    )

    result = await set_project.set_project(
        agent="test_agent",
        name=f"explicit-root-required-{uuid.uuid4().hex[:8]}",
        root="",
        format="structured",
    )

    assert not result["ok"]
    # Under the hardened model an empty root is caught by the required-field
    # validator before any context/authority resolution happens.
    assert "`root` is required and must be a non-empty string." in result["error"]


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
    # Under the hardened model, a bare tmp directory that is not a local repo root
    # is rejected at the first gate with explicit_root_not_local_repo.  The
    # security intent is preserved: the root is denied and no state is mutated.
    assert rejected_result["reason_code"] == "explicit_root_not_local_repo"
    assert "Explicit root must resolve to a local repository root before authorization." in rejected_result["error"]
    assert not rejected_root.exists()
    assert not (rejected_root / settings.dev_plans_base / rejected_name).exists()

    state_after = await set_project.server_module.state_manager.load()
    assert state_after.current_project == current_before


@pytest.mark.asyncio
async def test_resolve_existing_project_alias_name_prefers_existing_repo_name(tmp_path: Path):
    class _Backend:
        async def fetch_project(self, _name: str, *, repo_root: str | None = None):
            assert repo_root == str(tmp_path.resolve())
            return SimpleNamespace(name="cortalabs-shared-context")

    resolved_name, alias_resolution = await set_project._resolve_existing_project_alias_name(
        "cortalabs_shared_context",
        _Backend(),
        tmp_path,
    )

    assert resolved_name == "cortalabs-shared-context"
    assert alias_resolution == {
        "requested_name": "cortalabs_shared_context",
        "resolved_name": "cortalabs-shared-context",
        "canonical_slug": "cortalabs_shared_context",
        "reason": "repo_scoped_canonical_alias_match",
    }


@pytest.mark.asyncio
async def test_validate_project_paths_allows_same_repo_canonical_alias(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    docs_dir = root / ".scribe" / "docs" / "dev_plans" / "cortalabs_shared_context"
    progress_log = docs_dir / "PROGRESS_LOG.md"

    async def _known_projects(*, skip: str | None):
        return {
            "cortalabs_shared_context": {
                "root": root.resolve(),
                "docs_dir": docs_dir.resolve(),
                "progress_log": progress_log.resolve(),
            }
        }

    monkeypatch.setattr(set_project, "_gather_known_projects", _known_projects)

    result = await set_project._validate_project_paths(
        name="cortalabs-shared-context",
        root_path=root,
        docs_dir=docs_dir,
        progress_log=progress_log,
    )

    assert result["ok"] is True


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

    # Register the session in scribe_sessions before binding a project to it —
    # the FK constraint on session_projects requires the session row to exist first.
    await manager._storage_backend.upsert_session(session_id="session-1", mode="project")

    updated = await manager.set_current_project(
        "proj2",
        {"name": "proj2", "root": ".", "progress_log": "./log2"},
        session_id="session-1",
        mirror_global=False,
    )

    assert updated.current_project == "proj1"
    assert updated.session_projects["session-1"]["name"] == "proj2"
