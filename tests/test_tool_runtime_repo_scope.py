from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared.tool_runtime import execute_tool_call


class _NoopStateManager:
    async def load(self):
        return SimpleNamespace(get_session_mode=lambda _session_id: None)


class _UnboundStorage:
    async def get_session_by_transport(self, _transport_session_id: str):
        return None

    async def fetch_project(self, _project_name: str):
        return None

    async def get_session_project(self, _session_id: str):
        return None

    async def upsert_session(self, **_kwargs):
        return None


class _BoundStorage:
    def __init__(self, *, repo_root: Path, project_name: str) -> None:
        self._repo_root = str(repo_root)
        self._project_name = project_name

    async def get_session_by_transport(self, _transport_session_id: str):
        return {
            "session_id": "session-verified-1",
            "repo_root": self._repo_root,
        }

    async def get_session_project(self, _session_id: str):
        return self._project_name

    async def fetch_project(self, _project_name: str):
        return SimpleNamespace(repo_root=self._repo_root)

    async def upsert_session(self, **_kwargs):
        return None

    async def get_or_create_agent_session(self, **_kwargs):
        return "stable-agent-session-1"

    async def get_last_agent_session_allocation(self, _identity_hash: str):
        return None


@pytest.mark.asyncio
async def test_execute_tool_call_fails_closed_when_repo_scope_unresolved(tmp_path: Path) -> None:
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _UnboundStorage()
    router = RouterContextManager(storage_backend=storage)

    with pytest.raises(ValueError, match="repo scope unresolved"):
        await execute_tool_call(
            name="capture_tool",
            arguments={"agent": "CoderAgent"},
            kwargs={"context": {"mode": "project", "transport_session_id": "transport-unbound"}},
            registry={"capture_tool": capture_tool},
            app=SimpleNamespace(request_context=None),
            storage_backend=storage,
            settings=SimpleNamespace(project_root=tmp_path / "server-default"),
            state_manager=_NoopStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"capture_tool"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

    assert observed["called"] is False


@pytest.mark.asyncio
async def test_execute_tool_call_labels_claimed_repo_root_from_arguments(tmp_path: Path) -> None:
    repo_root = (tmp_path / "claimed-repo").resolve()
    repo_root.mkdir(parents=True)
    observed: dict[str, object] = {}

    def capture_tool(agent: str, **_kwargs) -> str:
        current = router.get_current()
        assert current is not None
        assert current.resolved_scope is not None
        observed["repo_root"] = current.repo_root
        observed["repo_root_provenance"] = current.resolved_scope.provenance.repo_root
        return agent

    storage = _UnboundStorage()
    router = RouterContextManager(storage_backend=storage)

    result = await execute_tool_call(
        name="capture_tool",
        arguments={"agent": "CoderAgent", "repo_root": str(repo_root)},
        kwargs={"context": {"mode": "project", "transport_session_id": "transport-claimed"}},
        registry={"capture_tool": capture_tool},
        app=SimpleNamespace(request_context=None),
        storage_backend=storage,
        settings=SimpleNamespace(project_root=tmp_path / "server-default"),
        state_manager=_NoopStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"capture_tool"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == "CoderAgent"
    assert observed["repo_root"] == str(repo_root)
    assert observed["repo_root_provenance"] == "claimed"


@pytest.mark.asyncio
async def test_execute_tool_call_preserves_verified_repo_root_from_bound_project(
    tmp_path: Path,
) -> None:
    verified_repo = (tmp_path / "verified-repo").resolve()
    verified_repo.mkdir(parents=True)
    observed: dict[str, object] = {}

    def capture_tool(agent: str, **_kwargs) -> str:
        current = router.get_current()
        assert current is not None
        assert current.resolved_scope is not None
        observed["repo_root"] = current.repo_root
        observed["repo_root_provenance"] = current.resolved_scope.provenance.repo_root
        observed["project_name_provenance"] = current.resolved_scope.provenance.project_name
        return agent

    storage = _BoundStorage(repo_root=verified_repo, project_name="verified-project")
    router = RouterContextManager(storage_backend=storage)

    result = await execute_tool_call(
        name="capture_tool",
        arguments={"agent": "CoderAgent"},
        kwargs={"context": {"mode": "project", "transport_session_id": "transport-verified"}},
        registry={"capture_tool": capture_tool},
        app=SimpleNamespace(request_context=None),
        storage_backend=storage,
        settings=SimpleNamespace(project_root=tmp_path / "server-default"),
        state_manager=_NoopStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"capture_tool"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == "CoderAgent"
    assert observed["repo_root"] == str(verified_repo)
    assert observed["repo_root_provenance"] == "verified"
    assert observed["project_name_provenance"] == "verified"
