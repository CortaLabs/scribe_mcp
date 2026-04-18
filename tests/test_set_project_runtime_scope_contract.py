from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest

from scribe_mcp.shared.tool_runtime import execute_tool_call
from scribe_mcp.shared.tool_runtime import issue_repo_root_grant
from scribe_mcp.shared.repo_authority import RepoAuthoritySnapshot
from scribe_mcp.tools import set_project as set_project_tool
from scribe_mcp.utils.formatters.project import ProjectFormatter


class _DummyState:
    @staticmethod
    def get_session_mode(_session_id: str):
        return None


class _DummyStateManager:
    async def load(self):
        return _DummyState()


class _GrantStorage:
    def __init__(self) -> None:
        self._grants: dict[str, SimpleNamespace] = {}

    async def create_repo_scope_grant(
        self,
        *,
        authoritative_session_key: str,
        repo_root: str,
        reason: str,
        ttl_minutes: int = 30,
    ) -> SimpleNamespace:
        grant_id = f"grant-{len(self._grants) + 1}"
        grant = SimpleNamespace(
            grant_id=grant_id,
            authoritative_session_key=authoritative_session_key,
            repo_root=str(Path(repo_root).resolve()),
            repo_id="repo-id-1",
            reason=reason,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=max(1, ttl_minutes)),
        )
        self._grants[grant_id] = grant
        return grant

    async def fetch_repo_scope_grant(self, grant_id: str) -> SimpleNamespace | None:
        return self._grants.get(grant_id)


class _NoPrefetchStorage:
    def __init__(self) -> None:
        self.fetch_project_called = False

    async def fetch_project(self, _name: str):
        self.fetch_project_called = True
        raise AssertionError("set_project preflight must not fetch_project by name")


class _CapturingRuntimeRouter:
    _process_instance_id = "proc-test"

    def __init__(self) -> None:
        self.last_payload: dict[str, object] | None = None

    async def get_or_create_session_id(self, _transport_session_id: str) -> str:
        return "stable-session-1"

    async def build_execution_context(self, payload: dict[str, object]):
        self.last_payload = dict(payload)
        return SimpleNamespace(
            mode=payload.get("mode", "project"),
            stable_session_id=payload.get("session_id", "stable-session-1"),
            repo_root=payload.get("repo_root"),
            transport_session_id=payload.get("transport_session_id"),
            session_id=payload.get("session_id", "stable-session-1"),
        )

    def set_current(self, _exec_context):
        return "token-1"

    def reset(self, _token):
        return None

    async def get_cached_project(self, _stable_session_id: str):
        return None


@pytest.mark.asyncio
async def test_execute_tool_call_set_project_root_omitted_fails_without_verified_binding(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    router = _CapturingRuntimeRouter()
    observed = {"called": False}

    def set_project_stub(agent: str, name: str, root: str | None = None, **_kwargs) -> dict[str, str | None]:
        observed["called"] = True
        return {"agent": agent, "name": name, "root": root}

    with pytest.raises(ValueError, match="repo scope unresolved"):
        await execute_tool_call(
            name="set_project",
            arguments={"agent": "codex", "name": "demo"},
            kwargs={},
            registry={"set_project": set_project_stub},
            app=SimpleNamespace(request_context=None),
            storage_backend=None,
            settings=SimpleNamespace(project_root=workspace_root),
            state_manager=_DummyStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"set_project"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

    assert observed["called"] is False
    assert router.last_payload is None


@pytest.mark.asyncio
async def test_execute_tool_call_set_project_uses_verified_request_local_repo_root(tmp_path: Path):
    workspace_root = (tmp_path / "workspace").resolve()
    workspace_root.mkdir()
    downstream_repo = (tmp_path / "outside" / "customer-repo").resolve()
    downstream_repo.mkdir(parents=True)
    (downstream_repo / ".git").mkdir()
    nested_cwd = downstream_repo / "src"
    nested_cwd.mkdir()

    router = _CapturingRuntimeRouter()

    def set_project_stub(agent: str, name: str, root: str | None = None, **_kwargs) -> dict[str, str | None]:
        return {"agent": agent, "name": name, "root": root}

    result = await execute_tool_call(
        name="set_project",
        arguments={"agent": "codex", "name": "demo"},
        kwargs={},
        registry={"set_project": set_project_stub},
        app=SimpleNamespace(request_context=SimpleNamespace(meta={"cwd": str(nested_cwd)})),
        storage_backend=None,
        settings=SimpleNamespace(project_root=workspace_root),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"set_project"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result["root"] is None
    assert router.last_payload is not None
    assert router.last_payload["repo_root"] == str(downstream_repo)
    assert router.last_payload["scope_provenance"]["repo_root"] == "verified"


@pytest.mark.asyncio
async def test_execute_tool_call_set_project_uses_explicit_root_without_name_prefetch(tmp_path: Path):
    workspace_root = (tmp_path / "workspace").resolve()
    workspace_root.mkdir()
    explicit_root = (tmp_path / "outside" / "customer-repo").resolve()
    explicit_root.mkdir(parents=True)
    (explicit_root / ".git").mkdir()

    router = _CapturingRuntimeRouter()
    storage = _NoPrefetchStorage()

    def set_project_stub(agent: str, name: str, root: str | None = None, **_kwargs) -> dict[str, str | None]:
        return {"agent": agent, "name": name, "root": root}

    result = await execute_tool_call(
        name="set_project",
        arguments={"agent": "codex", "name": "demo_project", "root": str(explicit_root)},
        kwargs={},
        registry={"set_project": set_project_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=storage,
        settings=SimpleNamespace(project_root=workspace_root),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"set_project"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result["root"] == str(explicit_root)
    assert storage.fetch_project_called is False
    assert router.last_payload is not None
    assert router.last_payload["repo_root"] == str(explicit_root)
    assert router.last_payload["scope_provenance"]["repo_root"] == "claimed"


@pytest.mark.asyncio
async def test_execute_tool_call_set_project_uses_explicit_root_without_storage_backend(tmp_path: Path):
    workspace_root = (tmp_path / "workspace").resolve()
    workspace_root.mkdir()
    explicit_root = (tmp_path / "outside" / "customer-repo").resolve()
    explicit_root.mkdir(parents=True)
    (explicit_root / ".git").mkdir()

    router = _CapturingRuntimeRouter()

    def set_project_stub(agent: str, name: str, root: str | None = None, **_kwargs) -> dict[str, str | None]:
        return {"agent": agent, "name": name, "root": root}

    result = await execute_tool_call(
        name="set_project",
        arguments={"agent": "codex", "name": "demo_project", "root": str(explicit_root)},
        kwargs={},
        registry={"set_project": set_project_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(project_root=workspace_root),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"set_project"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result["root"] == str(explicit_root)
    assert router.last_payload is not None
    assert router.last_payload["repo_root"] == str(explicit_root)
    assert router.last_payload["scope_provenance"]["repo_root"] == "claimed"


@pytest.mark.asyncio
async def test_execute_tool_call_preserves_verified_request_repo_root_for_non_set_project(tmp_path: Path):
    workspace_root = (tmp_path / "workspace").resolve()
    workspace_root.mkdir()
    downstream_repo = (tmp_path / "outside" / "customer-repo").resolve()
    downstream_repo.mkdir(parents=True)
    (downstream_repo / ".git").mkdir()
    nested_cwd = downstream_repo / "src"
    nested_cwd.mkdir()

    router = _CapturingRuntimeRouter()

    async def list_projects_stub(agent: str, **_kwargs) -> dict[str, str]:
        return {"agent": agent, "status": "ok"}

    result = await execute_tool_call(
        name="list_projects",
        arguments={"agent": "codex", "global_mode": True},
        kwargs={},
        registry={"list_projects": list_projects_stub},
        app=SimpleNamespace(request_context=SimpleNamespace(meta={"cwd": str(nested_cwd)})),
        storage_backend=None,
        settings=SimpleNamespace(project_root=workspace_root),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"list_projects"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result["status"] == "ok"
    assert router.last_payload is not None
    assert router.last_payload["repo_root"] == str(downstream_repo)
    assert router.last_payload["scope_provenance"]["repo_root"] == "verified"


@pytest.mark.asyncio
async def test_execute_tool_call_allows_list_projects_with_explicit_root_without_verified_binding(
    tmp_path: Path,
):
    workspace_root = (tmp_path / "workspace").resolve()
    workspace_root.mkdir()
    explicit_root = (tmp_path / "outside" / "customer-repo").resolve()
    explicit_root.mkdir(parents=True)
    (explicit_root / ".git").mkdir()

    router = _CapturingRuntimeRouter()

    async def list_projects_stub(agent: str, root: str | None = None, **_kwargs) -> dict[str, str | None]:
        return {"agent": agent, "status": "ok", "root": root}

    result = await execute_tool_call(
        name="list_projects",
        arguments={"agent": "codex", "global_mode": True, "root": str(explicit_root)},
        kwargs={},
        registry={"list_projects": list_projects_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(project_root=workspace_root),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"list_projects"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result["status"] == "ok"
    assert result["root"] == str(explicit_root)
    assert router.last_payload is not None
    assert router.last_payload["repo_root"] == str(workspace_root)
    assert router.last_payload["scope_provenance"]["repo_root"] in {"claimed", "anonymous"}


@pytest.mark.asyncio
async def test_set_project_root_resolution_fails_closed_when_root_omitted_without_verified_binding(tmp_path: Path):
    authority_snapshot = RepoAuthoritySnapshot(
        verified_binding_root=None,
        verified_request_root=None,
        enrolled_first_party_roots=tuple(),
        authoritative_session_key="stable-session-1",
    )

    with pytest.raises(set_project_tool.ProjectRootAuthorizationError) as excinfo:
        await set_project_tool._resolve_root(
            root=None,
            authority_snapshot=authority_snapshot,
            skip_validation=True,
            grant_id=None,
            storage_backend=None,
            scribe_user=None,
        )

    payload = excinfo.value.payload
    assert payload["reason_code"] == "missing_root_without_verified_runtime_binding"


@pytest.mark.asyncio
async def test_set_project_root_resolution_allows_explicit_local_repo_root_without_prior_binding(
    tmp_path: Path,
) -> None:
    external_root = (tmp_path / "external-repo").resolve()
    external_root.mkdir()
    (external_root / ".git").mkdir()
    authority_snapshot = RepoAuthoritySnapshot(
        verified_binding_root=None,
        verified_request_root=None,
        enrolled_first_party_roots=tuple(),
        authoritative_session_key="stable-session-1",
    )

    resolved_root, payload = await set_project_tool._resolve_root(
        root=str(external_root),
        authority_snapshot=authority_snapshot,
        skip_validation=False,
        grant_id=None,
        storage_backend=None,
        scribe_user=None,
    )

    assert resolved_root == external_root
    assert payload["authorization_mode"] == "first_party"
    assert payload["authority_source"] == "explicit_local_repo_root"
    assert payload["reason_code"] == "first_party_explicit_local_repo_root"


@pytest.mark.asyncio
async def test_set_project_root_resolution_prefers_explicit_local_repo_even_when_grant_matches_session(tmp_path: Path) -> None:
    external_root = (tmp_path / "external-repo").resolve()
    external_root.mkdir()
    (external_root / ".git").mkdir()
    authority_snapshot = RepoAuthoritySnapshot(
        verified_binding_root=None,
        verified_request_root=None,
        enrolled_first_party_roots=tuple(),
        authoritative_session_key="stable-session-1",
    )
    storage = _GrantStorage()
    grant = await issue_repo_root_grant(
        storage_backend=storage,
        repo_root=str(external_root),
        reason="phase-1.2b-test",
        ttl_minutes=30,
        authoritative_session_key="stable-session-1",
    )

    resolved_root, authorization = await set_project_tool._resolve_root(
        root=str(external_root),
        authority_snapshot=authority_snapshot,
        skip_validation=False,
        grant_id=grant["grant_id"],
        storage_backend=storage,
        scribe_user=None,
    )

    assert resolved_root == external_root
    assert authorization["reason_code"] == "first_party_explicit_local_repo_root"
    assert authorization["authority_source"] == "explicit_local_repo_root"
    assert "grant_id" not in authorization


@pytest.mark.asyncio
async def test_set_project_root_resolution_ignores_mismatched_grant_for_explicit_local_repo(tmp_path: Path) -> None:
    external_root = (tmp_path / "external-repo").resolve()
    external_root.mkdir()
    (external_root / ".git").mkdir()
    other_root = (tmp_path / "other-repo").resolve()
    other_root.mkdir()
    (other_root / ".git").mkdir()
    authority_snapshot = RepoAuthoritySnapshot(
        verified_binding_root=None,
        verified_request_root=None,
        enrolled_first_party_roots=tuple(),
        authoritative_session_key="stable-session-1",
    )
    storage = _GrantStorage()
    grant = await issue_repo_root_grant(
        storage_backend=storage,
        repo_root=str(other_root),
        reason="phase-1.2b-test",
        ttl_minutes=30,
        authoritative_session_key="stable-session-1",
    )

    resolved_root, authorization = await set_project_tool._resolve_root(
        root=str(external_root),
        authority_snapshot=authority_snapshot,
        skip_validation=False,
        grant_id=grant["grant_id"],
        storage_backend=storage,
        scribe_user=None,
    )

    assert resolved_root == external_root
    assert authorization["reason_code"] == "first_party_explicit_local_repo_root"
    assert authorization["authority_source"] == "explicit_local_repo_root"


@pytest.mark.asyncio
async def test_set_project_root_resolution_binds_first_party_repo_outside_shared_spine(
    tmp_path: Path,
) -> None:
    bound_repo = (tmp_path / "a" / "bound-repo").resolve()
    bound_repo.mkdir(parents=True)
    (bound_repo / ".git").mkdir()
    outside_repo = (tmp_path / "b" / "outside-first-party").resolve()
    outside_repo.mkdir(parents=True)
    (outside_repo / ".git").mkdir()

    authority_snapshot = RepoAuthoritySnapshot(
        verified_binding_root=str(bound_repo),
        verified_request_root=str(outside_repo),
        enrolled_first_party_roots=tuple(),
        authoritative_session_key="stable-session-1",
    )

    resolved_root, authorization = await set_project_tool._resolve_root(
        root=str(outside_repo),
        authority_snapshot=authority_snapshot,
        skip_validation=False,
        grant_id=None,
        storage_backend=_GrantStorage(),
        scribe_user=None,
    )

    assert resolved_root == outside_repo
    assert authorization["authorization_mode"] == "first_party"
    assert authorization["authority_source"] == "verified_request_root"
    assert authorization["reason_code"] == "first_party_verified_request_root_match"


@pytest.mark.asyncio
async def test_set_project_root_resolution_rejects_unmatched_repo_without_grant(
    tmp_path: Path,
) -> None:
    verified_repo = (tmp_path / "verified").resolve()
    verified_repo.mkdir()
    (verified_repo / ".git").mkdir()
    external_root = (tmp_path / "external-repo").resolve()
    external_root.mkdir()
    (external_root / ".git").mkdir()
    authority_snapshot = RepoAuthoritySnapshot(
        verified_binding_root=str(verified_repo),
        verified_request_root=str(verified_repo),
        enrolled_first_party_roots=tuple(),
        authoritative_session_key="stable-session-1",
    )

    with pytest.raises(set_project_tool.ProjectRootAuthorizationError) as excinfo:
        await set_project_tool._resolve_root(
            root=str(external_root),
            authority_snapshot=authority_snapshot,
            skip_validation=True,
            grant_id=None,
            storage_backend=_GrantStorage(),
            scribe_user=None,
        )

    payload = excinfo.value.payload
    assert payload["reason_code"] == "external_root_requires_grant"
    assert payload["authority_source"] == "none"
    assert "authorize_repo_root" in payload["suggestion"]
    assert "authorize_repo_root" in payload["migration_hint"]


@pytest.mark.asyncio
async def test_set_project_root_resolution_rejects_non_repo_path_even_with_matching_claims(
    tmp_path: Path,
) -> None:
    verified_repo = (tmp_path / "verified").resolve()
    verified_repo.mkdir()
    (verified_repo / ".git").mkdir()
    non_repo_dir = (tmp_path / "not-a-repo").resolve()
    non_repo_dir.mkdir()
    authority_snapshot = RepoAuthoritySnapshot(
        verified_binding_root=str(verified_repo),
        verified_request_root=str(non_repo_dir),
        enrolled_first_party_roots=tuple(),
        authoritative_session_key="stable-session-1",
    )

    with pytest.raises(set_project_tool.ProjectRootAuthorizationError) as excinfo:
        await set_project_tool._resolve_root(
            root=str(non_repo_dir),
            authority_snapshot=authority_snapshot,
            skip_validation=False,
            grant_id=None,
            storage_backend=_GrantStorage(),
            scribe_user=None,
        )

    payload = excinfo.value.payload
    assert payload["reason_code"] == "explicit_root_not_local_repo"


def test_project_formatter_marks_compatibility_shim_with_migration_guidance() -> None:
    formatter = ProjectFormatter()
    project = {
        "name": "demo",
        "root": "/tmp/demo",
        "progress_log": "/tmp/demo/.scribe/docs/dev_plans/demo/PROGRESS_LOG.md",
        "root_authorization": {
            "compatibility_override_used": True,
            "deprecation_notice": "skip_validation=true compatibility mode is deprecated.",
            "migration_hint": "Use authorize_repo_root and pass grant_id to set_project.",
        },
    }

    rendered = formatter.format_project_sitrep_new(
        project=project,
        docs_created={"progress_log": "/tmp/demo/.scribe/docs/dev_plans/demo/PROGRESS_LOG.md"},
    )

    assert "legacy skip_validation compatibility shim (grant-backed)" in rendered
    assert "Deprecation: skip_validation=true compatibility mode is deprecated." in rendered
    assert "Migration: Use authorize_repo_root and pass grant_id to set_project." in rendered
