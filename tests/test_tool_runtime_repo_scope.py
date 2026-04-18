from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared.tool_runtime import (
    execute_tool_call,
    issue_repo_root_grant,
    validate_repo_root_grant,
)


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


class _StaleTransportStorage:
    def __init__(self, *, repo_root: Path, project_name: str) -> None:
        self._repo_root = str(repo_root)
        self._project_name = project_name

    async def get_session_by_transport(self, _transport_session_id: str):
        return {"session_id": "stale-session-1", "repo_root": self._repo_root}

    async def get_session_project(self, _session_id: str):
        return self._project_name

    async def fetch_project(self, _project_name: str):
        return SimpleNamespace(repo_root=self._repo_root)

    async def upsert_session(self, **_kwargs):
        return None


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


class _FailingSessionStorage:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = str(repo_root)

    async def get_session_by_transport(self, _transport_session_id: str):
        return {
            "session_id": "session-1",
            "repo_root": self._repo_root,
            "mode": "project",
        }

    async def fetch_project(self, _project_name: str):
        return None

    async def get_session_project(self, _session_id: str):
        return None

    async def upsert_session(self, **_kwargs):
        raise RuntimeError("boom")


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
async def test_execute_tool_call_relative_read_does_not_bind_from_stale_transport_history(
    tmp_path: Path,
) -> None:
    stale_repo = (tmp_path / "stale-repo").resolve()
    stale_repo.mkdir(parents=True)
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _StaleTransportStorage(repo_root=stale_repo, project_name="stale-project")
    router = RouterContextManager(storage_backend=storage)

    with pytest.raises(ValueError, match="repo scope unresolved"):
        await execute_tool_call(
            name="read_file",
            arguments={"agent": "CoderAgent", "path": "README.md"},
            kwargs={"context": {"mode": "project", "transport_session_id": "transport-stale"}},
            registry={"read_file": capture_tool},
            app=SimpleNamespace(request_context=None),
            storage_backend=storage,
            settings=SimpleNamespace(project_root=tmp_path / "server-default"),
            state_manager=_NoopStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"read_file"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

    assert observed["called"] is False


@pytest.mark.asyncio
async def test_execute_tool_call_does_not_grant_repo_scope_from_claimed_argument(
    tmp_path: Path,
) -> None:
    repo_root = (tmp_path / "claimed-repo").resolve()
    repo_root.mkdir(parents=True)
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _UnboundStorage()
    router = RouterContextManager(storage_backend=storage)

    with pytest.raises(ValueError, match="repo scope unresolved"):
        await execute_tool_call(
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

    assert observed["called"] is False


@pytest.mark.asyncio
async def test_execute_tool_call_does_not_bind_repo_scope_from_transport_derived_session_history(
    tmp_path: Path,
) -> None:
    verified_repo = (tmp_path / "verified-repo").resolve()
    verified_repo.mkdir(parents=True)
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _BoundStorage(repo_root=verified_repo, project_name="verified-project")
    router = RouterContextManager(storage_backend=storage)

    with pytest.raises(ValueError, match="repo scope unresolved"):
        await execute_tool_call(
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

    assert observed["called"] is False


@pytest.mark.asyncio
async def test_execute_tool_call_restores_repo_scope_from_verified_runtime_transport_binding(
    tmp_path: Path,
) -> None:
    verified_repo = (tmp_path / "verified-repo").resolve()
    verified_repo.mkdir(parents=True)
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _BoundStorage(repo_root=verified_repo, project_name="verified-project")
    router = RouterContextManager(storage_backend=storage)

    result = await execute_tool_call(
        name="capture_tool",
        arguments={"agent": "CoderAgent"},
        kwargs={"context": {"mode": "project"}},
        registry={"capture_tool": capture_tool},
        app=SimpleNamespace(
            request_context=SimpleNamespace(
                request=SimpleNamespace(headers={"mcp-session-id": "transport-verified"}),
                meta=None,
            )
        ),
        storage_backend=storage,
        settings=SimpleNamespace(project_root=tmp_path / "server-default"),
        state_manager=_NoopStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"capture_tool"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == "CoderAgent"
    assert observed["called"] is True


@pytest.mark.asyncio
async def test_execute_tool_call_restores_repo_scope_from_internal_process_binding(
    tmp_path: Path,
) -> None:
    verified_repo = (tmp_path / "verified-repo").resolve()
    verified_repo.mkdir(parents=True)
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _BoundStorage(repo_root=verified_repo, project_name="verified-project")
    router = RouterContextManager(storage_backend=storage)

    result = await execute_tool_call(
        name="capture_tool",
        arguments={"agent": "CoderAgent"},
        kwargs={"context": {"mode": "project"}},
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
    assert observed["called"] is True


@pytest.mark.asyncio
async def test_repo_root_grant_reuse_denied_for_other_authoritative_session(tmp_path: Path) -> None:
    repo_root = (tmp_path / "external").resolve()
    repo_root.mkdir(parents=True)
    storage = _GrantStorage()
    grant = await issue_repo_root_grant(
        storage_backend=storage,
        repo_root=str(repo_root),
        reason="phase-1.2b-test",
        ttl_minutes=30,
        authoritative_session_key="stable-session-A",
    )

    valid, details = await validate_repo_root_grant(
        storage_backend=storage,
        grant_id=grant["grant_id"],
        repo_root=str(repo_root),
        authoritative_session_key="stable-session-B",
    )

    assert valid is False
    assert details["reason_code"] == "grant_session_mismatch"


@pytest.mark.asyncio
async def test_execute_tool_call_raises_when_session_persistence_fails(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _FailingSessionStorage(repo_root)
    router = RouterContextManager(storage_backend=storage)

    with pytest.raises(RuntimeError, match="boom"):
        await execute_tool_call(
            name="capture_tool",
            arguments={"agent": "CoderAgent"},
            kwargs={"context": {"mode": "project"}},
            registry={"capture_tool": capture_tool},
            app=SimpleNamespace(
                request_context=SimpleNamespace(
                    request=SimpleNamespace(headers={"mcp-session-id": "transport-1"}),
                    meta={"cwd": str(repo_root)},
                )
            ),
            storage_backend=storage,
            settings=SimpleNamespace(project_root=tmp_path / "server-default"),
            state_manager=_NoopStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"capture_tool"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

    assert observed["called"] is False
