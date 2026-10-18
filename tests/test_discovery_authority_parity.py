from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.shared.repo_authority import (
    RepoAuthorityResolutionError,
    RepoAuthoritySnapshot,
    project_root_is_first_party,
    resolve_authorized_project_root,
)
from scribe_mcp.tools import list_projects as list_projects_module


@pytest.mark.asyncio
async def test_list_projects_discovery_includes_verified_request_root_outside_local_tree(monkeypatch, tmp_path: Path) -> None:
    outside_root = (tmp_path / "outside-first-party").resolve()
    outside_root.mkdir(parents=True)
    (outside_root / ".git").mkdir()

    unrelated_root = (tmp_path / "unrelated").resolve()
    unrelated_root.mkdir(parents=True)
    (unrelated_root / ".git").mkdir()

    outside_record = SimpleNamespace(
        name="outside",
        repo_root=str(outside_root),
        progress_log_path=str(outside_root / "PROGRESS_LOG.md"),
    )
    unrelated_record = SimpleNamespace(
        name="unrelated",
        repo_root=str(unrelated_root),
        progress_log_path=str(unrelated_root / "PROGRESS_LOG.md"),
    )
    backend = SimpleNamespace(
        list_projects=AsyncMock(return_value=[outside_record, unrelated_record]),
        list_projects_by_repo=AsyncMock(return_value=[]),
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
        get_execution_context=lambda: None,
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
    monkeypatch.setattr(
        list_projects_module,
        "build_repo_authority_snapshot",
        lambda **_kwargs: RepoAuthoritySnapshot(
            verified_binding_root=None,
            verified_request_root=str(outside_root),
            enrolled_first_party_roots=tuple(),
            authoritative_session_key="session-1",
        ),
    )
    monkeypatch.setattr(list_projects_module, "list_project_configs", lambda: {})
    monkeypatch.setattr(list_projects_module._PROJECT_REGISTRY, "get_project", lambda _name: None)
    monkeypatch.setattr(list_projects_module, "detect_project_state", lambda *_args, **_kwargs: ("NEW", "ok"))

    result = await list_projects_module.list_projects(format="structured", include_test=True, limit=10)

    assert result["ok"] is True
    assert [project["name"] for project in result["projects"]] == ["outside"]
    backend.list_projects.assert_awaited_once()
    backend.list_projects_by_repo.assert_not_awaited()


@pytest.mark.asyncio
async def test_discovery_and_set_project_share_same_first_party_roots_including_enrolled(tmp_path: Path) -> None:
    binding_root = (tmp_path / "bound").resolve()
    binding_root.mkdir(parents=True)
    (binding_root / ".git").mkdir()
    request_root = (tmp_path / "request").resolve()
    request_root.mkdir(parents=True)
    (request_root / ".git").mkdir()
    enrolled_root = (tmp_path / "enrolled").resolve()
    enrolled_root.mkdir(parents=True)
    (enrolled_root / ".git").mkdir()

    snapshot = RepoAuthoritySnapshot(
        verified_binding_root=str(binding_root),
        verified_request_root=str(request_root),
        enrolled_first_party_roots=(str(enrolled_root),),
        authoritative_session_key="session-1",
    )

    async def _grant_validator(_storage: object, _grant_id: str, _root: str, _session: str | None):
        return False, {"reason_code": "grant_unexpected"}

    for expected_source, root in (
        ("verified_binding_root", binding_root),
        ("verified_request_root", request_root),
        ("enrolled_first_party_roots", enrolled_root),
    ):
        visible, authority_source, reason_code, normalized = project_root_is_first_party(
            project_root=str(root),
            snapshot=snapshot,
        )
        assert visible is True
        assert authority_source == expected_source
        assert reason_code is not None
        assert normalized == str(root)

        resolved_root, authorization = await resolve_authorized_project_root(
            root=str(root),
            skip_validation=False,
            grant_id=None,
            snapshot=snapshot,
            base_root=tmp_path,
            scribe_user=None,
            validate_repo_root_grant=_grant_validator,
            storage_backend=SimpleNamespace(),
        )
        assert resolved_root == root
        assert authorization["authorization_mode"] == "first_party"
        assert authorization["authority_source"] == expected_source


@pytest.mark.asyncio
async def test_unrelated_root_is_not_visible_but_explicit_local_bind_is_first_party(tmp_path: Path) -> None:
    trusted_root = (tmp_path / "trusted").resolve()
    trusted_root.mkdir(parents=True)
    (trusted_root / ".git").mkdir()
    unrelated_root = (tmp_path / "unrelated").resolve()
    unrelated_root.mkdir(parents=True)
    (unrelated_root / ".git").mkdir()

    snapshot = RepoAuthoritySnapshot(
        verified_binding_root=str(trusted_root),
        verified_request_root=None,
        enrolled_first_party_roots=tuple(),
        authoritative_session_key="session-1",
    )

    visible, authority_source, reason_code, normalized = project_root_is_first_party(
        project_root=str(unrelated_root),
        snapshot=snapshot,
    )
    assert visible is False
    assert authority_source is None
    assert reason_code is None
    assert normalized == str(unrelated_root)

    async def _grant_validator(_storage: object, _grant_id: str, _root: str, _session: str | None):
        return False, {"reason_code": "grant_unexpected"}

    resolved_root, authorization = await resolve_authorized_project_root(
        root=str(unrelated_root),
        skip_validation=False,
        grant_id=None,
        snapshot=snapshot,
        base_root=tmp_path,
        scribe_user=None,
        validate_repo_root_grant=_grant_validator,
        storage_backend=SimpleNamespace(),
    )

    assert resolved_root == unrelated_root
    assert authorization["authorization_mode"] == "first_party"
    assert authorization["authority_source"] == "explicit_local_repo_root"
    assert authorization["reason_code"] == "first_party_explicit_local_repo_root"
