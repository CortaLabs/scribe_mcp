from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.storage.models import SessionBindingRecordV2
from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared.execution_context import resolve_application_identity
from scribe_mcp.mcp_adapter import ProtocolEra
from scribe_mcp.shared.tool_runtime import (
    execute_tool_call,
    issue_repo_root_grant,
    validate_repo_root_grant,
)


class _NoopStateManager:
    async def load(self):
        return SimpleNamespace(get_session_mode=lambda _session_id: None)


@asynccontextmanager
async def _server_context(router, *, session_id, stable_session_id=None):
    """Model a nested call from a context already built by the server."""
    context = await router.build_execution_context({
        "repo_root": "/server", "mode": "project", "session_id": session_id,
        "stable_session_id": stable_session_id, "intent": "server-nested-call",
    })
    token = router.set_current(context)
    try:
        yield
    finally:
        router.reset(token)


async def _execute_from_server_context(router, *, session_id, stable_session_id=None, **kwargs):
    async with _server_context(router, session_id=session_id, stable_session_id=stable_session_id):
        return await execute_tool_call(**kwargs)


class _UnboundStorage:
    async def get_session_by_transport(self, _transport_session_id: str):
        return None

    async def fetch_project(self, _project_name: str):
        return None

    async def get_session_project(self, _session_id: str):
        return None

    async def upsert_session(self, **_kwargs):
        return None


class _RepoScopedProjectStorage(_UnboundStorage):
    def __init__(self, *, repo_root: Path, project_name: str) -> None:
        self.repo_root = str(repo_root)
        self.project_name = project_name
        self.fetch_calls: list[tuple[str, str | None]] = []

    async def fetch_project(self, project_name: str, *, repo_root: str | None = None, project_key: str | None = None):
        self.fetch_calls.append((project_name, repo_root))
        if project_name == self.project_name and repo_root == self.repo_root:
            return SimpleNamespace(repo_root=self.repo_root)
        return None


class _BoundStorage:
    def __init__(self, *, repo_root: Path, project_name: str) -> None:
        self._repo_root = str(repo_root)
        self._project_name = project_name
        self.fetch_calls: list[tuple[str, str | None, str | None]] = []

    async def get_session_by_transport(self, _transport_session_id: str):
        return {
            "session_id": "session-verified-1",
            "repo_root": self._repo_root,
        }

    async def get_session_project(self, _session_id: str):
        return SessionBindingRecordV2(
            hashlib.sha256(_session_id.encode()).hexdigest(), "binding-project-key",
            self._project_name, self._repo_root, 3, datetime.now(timezone.utc),
        )

    async def fetch_project(self, _project_name: str, *, repo_root: str | None = None, project_key: str | None = None):
        self.fetch_calls.append((_project_name, repo_root, project_key))
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
        return SessionBindingRecordV2(
            hashlib.sha256(_session_id.encode()).hexdigest(), "binding-project-key",
            self._project_name, self._repo_root, 3, datetime.now(timezone.utc),
        )

    async def fetch_project(self, _project_name: str, *, repo_root: str | None = None, project_key: str | None = None):
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
async def test_execute_tool_call_resolves_explicit_project_with_repo_root(
    tmp_path: Path,
) -> None:
    repo_root = (tmp_path / "scoped-repo").resolve()
    repo_root.mkdir(parents=True)
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _RepoScopedProjectStorage(
        repo_root=repo_root,
        project_name="shared-project",
    )
    router = RouterContextManager(storage_backend=storage)

    result = await execute_tool_call(
        name="capture_tool",
        arguments={
            "agent": "CoderAgent",
            "project": "shared-project",
            "root": str(repo_root),
        },
        kwargs={"context": {"mode": "project", "transport_session_id": "transport-scoped"}},
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
    assert storage.fetch_calls == [("shared-project", str(repo_root))]


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
    assert storage.fetch_calls == [("verified-project", None, "binding-project-key")]


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


class _CanonicalKeyBindingStorage:
    """Session->project binding written under the canonical key.

    Mirrors the write side (set_project ->
    resolve_context_authoritative_session_key -> set_session_project), which
    keys ``session_projects`` on ``stable_session_id or session_id`` (see
    scribe_mcp.shared.session_utils.get_canonical_session_key). Records the key
    each ``get_session_project`` read queried with so a test can assert the
    read used the SAME canonical key as the write.
    """

    def __init__(self, *, repo_root: Path, project_name: str, bound_key: str) -> None:
        self._repo_root = str(repo_root)
        self._project_name = project_name
        self._bound_key = bound_key
        self.queried_keys: list[str | None] = []
        self.project_keys: list[str | None] = []
        self.binding = SessionBindingRecordV2(
            hashlib.sha256(bound_key.encode()).hexdigest(), "binding-project-key", project_name,
            self._repo_root, 3, datetime(2026, 10, 18, tzinfo=timezone.utc),
        )

    async def get_session_by_transport(self, _transport_session_id: str):
        return None

    async def get_session_project(self, session_id):
        self.queried_keys.append(session_id)
        if session_id != self._bound_key:
            return None
        return self.binding

    async def fetch_project(self, project_name: str, *, repo_root: str | None = None, project_key: str | None = None):
        self.project_keys.append(project_key)
        if project_name == self._project_name and project_key == "binding-project-key":
            return SimpleNamespace(repo_root=self._repo_root)
        return None

    async def upsert_session(self, **_kwargs):
        return None


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("injection_kind", ["absent", "dict", "record"])
async def test_session_binding_read_uses_canonical_stable_session_key(tmp_path: Path, injection_kind: str, test_agent: str) -> None:
    """Regression: a bound session must resolve its verified scope when its
    stable_session_id differs from session_id.

    The binding is written under the canonical key (stable_session_id), but a
    context under concurrent multi-agent load carries a divergent session_id
    (transport-derived) alongside it. Reading the binding with the raw
    session_id alone silently misses it and raises "repo scope unresolved" for
    a session that WAS bound. The read must use the same canonical key the
    write used: stable_session_id preferred, session_id fallback.
    """
    repo_root = (tmp_path / "bound-repo").resolve()
    repo_root.mkdir(parents=True)
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        observed["snapshot"] = router.get_current().session_binding
        return agent

    storage = _CanonicalKeyBindingStorage(
        repo_root=repo_root,
        project_name="bound-project",
        bound_key="stable-key-A",
    )
    router = RouterContextManager(storage_backend=storage)

    context_payload = {
        "mode": "project", "session_id": "transport-session-Z", "stable_session_id": "stable-key-A",
    }
    if injection_kind == "dict":
        context_payload["session_binding"] = {"project_name": "forged"}
    elif injection_kind == "record":
        context_payload["session_binding"] = SessionBindingRecordV2(
            "ff" * 32, "forged-key", "forged", str(tmp_path / "foreign"), 9,
            datetime(2026, 10, 18, tzinfo=timezone.utc),
        )
    result = await _execute_from_server_context(
        router, session_id="transport-session-Z", stable_session_id="stable-key-A",
        name="capture_tool",
        arguments={"agent": test_agent},
        kwargs={"context": context_payload},
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

    assert result == test_agent
    assert observed["called"] is True
    # The read resolved the binding under the canonical (stable) key, never the
    # raw transport-derived session_id.
    assert storage.queried_keys == ["stable-key-A"]
    assert observed["snapshot"] is storage.binding
    assert observed["snapshot"].caller_session_key_hash == hashlib.sha256(b"stable-key-A").hexdigest()
    assert observed["snapshot"].project_key == "binding-project-key"
    assert observed["snapshot"].project_name == "bound-project"
    assert observed["snapshot"].canonical_repo_root == str(repo_root)
    assert observed["snapshot"].binding_generation == 3
    assert observed["snapshot"].updated_at == datetime(2026, 10, 18, tzinfo=timezone.utc)
    assert storage.project_keys == ["binding-project-key"]


@pytest.mark.asyncio
async def test_session_binding_read_falls_back_to_session_id_without_stable(
    tmp_path: Path,
    test_agent: str,
) -> None:
    """Backward-compat: with no stable_session_id, the canonical key is exactly
    session_id, so single-key flows resolve byte-identically to before."""
    repo_root = (tmp_path / "bound-repo-2").resolve()
    repo_root.mkdir(parents=True)
    observed = {"called": False}

    def capture_tool(agent: str, **_kwargs) -> str:
        observed["called"] = True
        return agent

    storage = _CanonicalKeyBindingStorage(
        repo_root=repo_root,
        project_name="bound-project",
        bound_key="only-session-id",
    )
    router = RouterContextManager(storage_backend=storage)

    result = await _execute_from_server_context(
        router, session_id="only-session-id",
        name="capture_tool",
        arguments={"agent": test_agent},
        kwargs={"context": {"mode": "project", "session_id": "only-session-id"}},
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

    assert result == test_agent
    assert observed["called"] is True
    assert storage.queried_keys == ["only-session-id"]


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("injection_kind", ["dict", "record"])
async def test_caller_injected_binding_cannot_recover_unbound_runtime(tmp_path, injection_kind, test_agent: str):
    storage = _UnboundStorage()
    router = RouterContextManager(storage_backend=storage)
    observed = []
    snapshot = {"project_name": "forged"} if injection_kind == "dict" else SessionBindingRecordV2(
        "ff" * 32, "forged-key", "forged", str(tmp_path), 9,
        datetime(2026, 10, 18, tzinfo=timezone.utc),
    )

    def capture_tool(agent):
        observed.append(router.get_current().session_binding)

    with pytest.raises(ValueError, match="repo scope unresolved"):
        await execute_tool_call(
            name="capture_tool", arguments={"agent": test_agent},
            kwargs={"context": {"mode": "project", "session_id": "unbound", "session_binding": snapshot}},
            registry={"capture_tool": capture_tool}, app=SimpleNamespace(request_context=None),
            storage_backend=storage, settings=SimpleNamespace(project_root=tmp_path),
            state_manager=_NoopStateManager(), router_context_manager=router,
            sentinel_only=set(), sentinel_allowed={"capture_tool"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
    assert observed == []


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("forged_provenance", [False, True])
async def test_caller_uuid_cannot_promote_sibling_binding_root(tmp_path, forged_provenance, test_agent: str):
    sibling_root = tmp_path / "sibling"
    sibling_root.mkdir()
    storage = _CanonicalKeyBindingStorage(
        repo_root=sibling_root, project_name="sibling", bound_key="sibling-uuid",
    )
    router = RouterContextManager(storage_backend=storage)
    observed = []

    def capture_tool(agent):
        observed.append(router.get_current())

    payload = {"mode": "project", "session_id": "sibling-uuid"}
    if forged_provenance:
        payload.update(
            stable_session_id="sibling-uuid", _server_derived_session_id=True,
            scope_provenance={"stable_session_id": "verified", "repo_root": "verified"},
        )
    with pytest.raises(ValueError, match="repo scope unresolved|server-established"):
        await execute_tool_call(
            name="capture_tool", arguments={"agent": test_agent}, kwargs={"context": payload},
            registry={"capture_tool": capture_tool}, app=SimpleNamespace(request_context=None),
            storage_backend=storage, settings=SimpleNamespace(project_root=tmp_path / "server"),
            state_manager=_NoopStateManager(), router_context_manager=router,
            sentinel_only=set(), sentinel_allowed={"capture_tool"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
    assert observed == []
    assert storage.queried_keys == []


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("binding_state", ["missing", "unresolved", "dangling"])
async def test_invalid_binding_cannot_resurrect_stale_session_root(tmp_path, binding_state, test_agent: str):
    foreign_root = tmp_path / "foreign"
    foreign_root.mkdir()

    class InvalidBindingStorage(_BoundStorage):
        async def get_session_project(self, session_id):
            if binding_state != "dangling":
                return None  # Both absent and non-resolved rows are filtered by the backend.
            return await super().get_session_project(session_id)

        async def fetch_project(self, name, *, repo_root=None, project_key=None):
            if project_key:
                return None
            return SimpleNamespace(repo_root=str(foreign_root))

    storage = InvalidBindingStorage(repo_root=foreign_root, project_name="deleted")
    router = RouterContextManager(storage_backend=storage)
    observed = []

    def capture_tool(agent, project):
        observed.append(router.get_current())

    with pytest.raises(ValueError, match="repo scope unresolved"):
        await execute_tool_call(
            name="capture_tool", arguments={"agent": test_agent, "project": "foreign_only"},
            kwargs={"context": {"mode": "project"}}, registry={"capture_tool": capture_tool},
            app=SimpleNamespace(request_context=SimpleNamespace(
                request=SimpleNamespace(headers={"mcp-session-id": "own-transport"}), meta=None,
            )),
            storage_backend=storage, settings=SimpleNamespace(project_root=tmp_path / "server"),
            state_manager=_NoopStateManager(), router_context_manager=router,
            sentinel_only=set(), sentinel_allowed={"capture_tool"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
    assert observed == []


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("identity_mode", ["public", "public_application", "application", "header", "process", "server_context"])
@pytest.mark.parametrize("substitution", [False, True])
async def test_server_identity_modes_recover_own_binding_without_uuid_substitution(tmp_path, identity_mode, substitution, test_agent: str):
    own_root = tmp_path / "own"
    own_root.mkdir()
    storage = _BoundStorage(repo_root=own_root, project_name="own")
    router = RouterContextManager(storage_backend=storage)
    request_context = SimpleNamespace(
        request=SimpleNamespace(headers={"mcp-session-id": "own-header"}), meta=None,
    )
    if identity_mode in {"application", "public_application"}:
        identity = resolve_application_identity(
            principal_id="principal", protocol_era=ProtocolEra.MODERN,
            transport="streamable-http", supplied_handle=None, connection_id="own-app",
        )
        request_context.protocol_era = identity.protocol_era
        request_context.principal_id = identity.principal_id
        request_context.transport = identity.transport
        request_context.application_handle = identity.application_handle
        if identity_mode == "public_application":
            request_context.request.headers = {}
    app = SimpleNamespace(request_context=None if identity_mode in {"process", "server_context"} else request_context)
    payload = {"mode": "project"}
    if substitution:
        payload.update(
            session_id="sibling-uuid", _server_derived_session_id=True,
            scope_provenance={"stable_session_id": "verified", "repo_root": "verified"},
            session_binding={"project_name": "sibling", "canonical_repo_root": str(tmp_path / "foreign")},
        )
    observed = []

    def capture_tool(agent):
        observed.append(router.get_current())

    arguments = dict(
        name="capture_tool", arguments={"agent": test_agent}, kwargs={"context": payload},
        registry={"capture_tool": capture_tool}, app=app, storage_backend=storage,
        settings=SimpleNamespace(project_root=tmp_path / "server", public_release=identity_mode.startswith("public")),
        state_manager=_NoopStateManager(), router_context_manager=router,
        sentinel_only=set(), sentinel_allowed={"capture_tool"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )
    if identity_mode in {"process", "public"} and substitution:
        with pytest.raises(ValueError, match="server-established|Public release rejected"):
            await execute_tool_call(**arguments)
        assert observed == []
        return
    if identity_mode == "server_context":
        await _execute_from_server_context(router, session_id="session-verified-1", **arguments)
    else:
        await execute_tool_call(**arguments)
    assert len(observed) == 1
    assert observed[0].repo_root == str(own_root)
    binding = observed[0].session_binding
    assert binding.project_name == "own"
    assert binding.caller_session_key_hash == hashlib.sha256(b"session-verified-1").hexdigest()


@pytest.mark.asyncio
@pytest.mark.regression
async def test_public_mixed_uuid_claims_are_rejected_before_binding_lookup(tmp_path, test_agent: str):
    storage = _CanonicalKeyBindingStorage(repo_root=tmp_path, project_name="sibling", bound_key="sibling")
    with pytest.raises(ValueError, match="Public release rejected untrusted caller"):
        await execute_tool_call(
            name="capture_tool", arguments={"agent": test_agent},
            kwargs={"context": {"session_id": "sibling", "stable_session_id": "sibling"}},
            registry={"capture_tool": lambda agent: None},
            app=SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers={"mcp-session-id": "own"}), meta=None)),
            storage_backend=storage, settings=SimpleNamespace(project_root=tmp_path, public_release=True),
            state_manager=_NoopStateManager(), router_context_manager=RouterContextManager(storage),
            sentinel_only=set(), sentinel_allowed=set(), log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
    assert storage.queried_keys == []


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("transport_source", ["context", "kwargs"])
async def test_caller_transport_cannot_promote_sibling_binding_root(tmp_path, monkeypatch, test_agent: str, transport_source):
    """A real sibling transport row must not become no-header caller authority."""
    from scribe_mcp import server
    from scribe_mcp.shared.execution_context import get_current_execution_context
    from scribe_mcp.shared.logging_utils import ProjectResolutionError
    from scribe_mcp.state.manager import StateManager
    from scribe_mcp.storage.sqlite import SQLiteStorage
    from scribe_mcp.tools.append_entry import append_entry

    storage = SQLiteStorage(db_path=tmp_path / "transport-authority.sqlite3")
    await storage.setup()
    try:
        own_root, foreign_root = tmp_path / "own", tmp_path / "foreign"
        for root in (own_root, foreign_root):
            root.mkdir()
            (root / ".git").mkdir()
        own_log, foreign_log = own_root / "PROGRESS_LOG.md", foreign_root / "PROGRESS_LOG.md"
        own_log.write_text("# Own log\n", encoding="utf-8")
        foreign_log.write_bytes(b"# Foreign log\nKEEP EXACT BYTES\n")
        foreign_before = foreign_log.read_bytes()
        await storage.upsert_project(name="transport_own", repo_root=str(own_root), progress_log_path=str(own_log))
        await storage.upsert_project(name="transport_foreign", repo_root=str(foreign_root), progress_log_path=str(foreign_log))
        router = RouterContextManager(storage_backend=storage)
        own_key = "00000000-0000-4000-8000-000000000001"
        sibling_key = "00000000-0000-4000-8000-000000000002"
        own_transport = f"process:{router._process_instance_id}::actor={test_agent}"
        sibling_transport = f"sibling-connection::actor={test_agent}"
        for key, transport, root, project in (
            (own_key, own_transport, own_root, "transport_own"),
            (sibling_key, sibling_transport, foreign_root, "transport_foreign"),
        ):
            await storage.upsert_session(session_id=key, transport_session_id=transport, repo_root=str(root), mode="project")
            await storage.upsert_agent_session(test_agent, key, {"source": "transport-authority-regression"})
            await storage.set_session_project(key, project)
        own_binding = await storage.get_session_project(own_key)
        sibling_binding = await storage.get_session_project(sibling_key)
        assert (await storage.get_session_by_transport(sibling_transport))["session_id"] == sibling_key
        state = StateManager(tmp_path / "state.json", storage_backend=storage)
        monkeypatch.setattr(server, "storage_backend", storage)
        monkeypatch.setattr(server, "state_manager", state)
        monkeypatch.setattr(server, "get_agent_identity", lambda: None)

        def context_getter(*_args, **kwargs):
            context = get_current_execution_context()
            return (context, {}) if kwargs.get("include_metadata") else context

        monkeypatch.setattr(server, "get_execution_context", context_getter)
        observed = []

        async def observed_append(**arguments):
            observed.append(get_current_execution_context())
            return await append_entry(**arguments)

        async def call(project, context, message, **caller_kwargs):
            return await execute_tool_call(
                name="append_entry",
                arguments={"agent": test_agent, "project": project, "message": message, "status": "info", "format": "structured"},
                kwargs={"context": context, **caller_kwargs}, registry={"append_entry": observed_append},
                app=SimpleNamespace(request_context=None), storage_backend=storage,
                settings=SimpleNamespace(project_root=tmp_path / "install", default_repo_root=str(own_root)),
                state_manager=state, router_context_manager=router,
                sentinel_only=set(), sentinel_allowed=set(), log_scope_violation_cb=lambda *_args, **_kwargs: None,
            )

        # Legitimate stdio has no header: the server's process identity recovers its own row.
        result = await call("transport_own", {"mode": "project"}, "legitimate-stdio-append")
        assert result["ok"] is True, result
        assert observed[-1].authoritative_session_key == own_key
        assert observed[-1].session_binding == own_binding
        assert "legitimate-stdio-append" in own_log.read_text(encoding="utf-8")
        own_before = own_log.read_bytes()
        observed.clear()
        payload = {"mode": "project"}
        caller_kwargs = {}
        if transport_source == "context":
            payload["transport_session_id"] = sibling_transport
        else:
            caller_kwargs["transport_session_id"] = sibling_transport
        try:
            await call(
                "transport_foreign", payload, "untrusted-sibling-transport-append", **caller_kwargs,
            )
        except (ValueError, ProjectResolutionError):
            pass  # Rejection before the consumer is also a valid fail-closed result.

        assert await storage.get_session_project(own_key) == own_binding
        assert await storage.get_session_project(sibling_key) == sibling_binding
        assert own_log.read_bytes() == own_before
        assert foreign_log.read_bytes() == foreign_before
        assert all(context.authoritative_session_key != sibling_key for context in observed)
        assert all(context.session_binding != sibling_binding for context in observed)
    finally:
        await storage.close()
