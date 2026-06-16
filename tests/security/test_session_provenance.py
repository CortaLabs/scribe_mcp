from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared import tool_runtime
from scribe_mcp.shared.tool_runtime import execute_tool_call


class _State:
    def get_session_mode(self, _session_id: str):
        return None


class _StateManager:
    async def load(self):
        return _State()


class _SessionAllocatorStorage:
    def __init__(self) -> None:
        self._sessions_by_identity: dict[str, str] = {}
        self._session_by_transport: dict[str, dict[str, str]] = {}

    async def upsert_session(
        self,
        *,
        session_id: str | None,
        transport_session_id: str | None,
        repo_root: str | None,
        mode: str | None,
    ) -> None:
        if session_id and transport_session_id:
            self._session_by_transport[str(transport_session_id)] = {
                "session_id": str(session_id),
                "repo_root": str(repo_root or ""),
                "mode": str(mode or ""),
            }

    async def get_session_by_transport(self, transport_session_id: str):
        return self._session_by_transport.get(str(transport_session_id))

    async def get_or_create_agent_session(
        self,
        *,
        identity_key: str,
        agent_name: str,
        agent_key: str,
        repo_root: str,
        mode: str,
        scope_key: str,
    ) -> str:
        del agent_name, agent_key, repo_root, mode, scope_key
        session_id = self._sessions_by_identity.get(identity_key)
        if session_id is None:
            session_id = f"agent-session-{len(self._sessions_by_identity) + 1}"
            self._sessions_by_identity[identity_key] = session_id
        return session_id

    async def get_last_agent_session_allocation(self, identity_key: str):
        session_id = self._sessions_by_identity.get(identity_key)
        if not session_id:
            return None
        return {
            "status": "allocated",
            "scoped_reuse_key": None,
            "session_id": session_id,
        }


@pytest.mark.asyncio
async def test_public_release_rejects_mixed_untrusted_session_identifiers() -> None:
    router = RouterContextManager()

    with pytest.raises(
        ValueError,
        match="Public release rejected untrusted caller session identifiers",
    ):
        await execute_tool_call(
            name="noop",
            arguments={
                "agent": "security-tester",
                "context": {"repo_root": "/tmp/repo", "mode": "project", "session_id": "forged"},
            },
            kwargs={"client_id": "forged-client"},
            registry={"noop": lambda agent: agent},
            app=SimpleNamespace(request_context=None),
            storage_backend=None,
            settings=SimpleNamespace(project_root=Path("/tmp/repo"), public_release=True),
            state_manager=_StateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"noop"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )


@pytest.mark.asyncio
async def test_public_release_ignores_single_untrusted_identifier_and_uses_runtime_transport(
    tmp_path: Path,
) -> None:
    # In public_release mode a caller-supplied session_id is untrusted and is
    # discarded.  The runtime derives the transport_session_id from a trusted
    # transport source on request_context (here: request_context.meta).  Unlike
    # the caller-supplied session_id — and unlike a client-settable mcp-session-id
    # HTTP header — meta is NOT counted as an untrusted caller claim, so exactly
    # ONE untrusted identifier (the forged session_id) remains, which the
    # public_release path must ignore in favor of the runtime transport.
    #
    # The repo_root must be a real directory with a repo marker and must be
    # listed in trusted_repo_roots so the runtime can verify it.
    repo_root = tmp_path / "trusted-repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    router = RouterContextManager()
    observed: dict[str, str] = {}
    trusted_transport_id = "runtime-transport-abc123"

    def capture(agent: str) -> str:
        current = router.get_current()
        assert current is not None
        observed["transport_session_id"] = current.transport_session_id or ""
        observed["session_id"] = current.session_id
        return agent

    # Trusted runtime transport supplied via request_context.meta (not a header,
    # not a caller kwarg) so it is treated as the verified runtime transport and
    # not as an untrusted caller claim.
    mock_request_context = SimpleNamespace(
        request=None, meta={"transport_session_id": trusted_transport_id}
    )
    app = SimpleNamespace(request_context=mock_request_context)

    result = await execute_tool_call(
        name="capture",
        arguments={
            "agent": "security-tester",
            "context": {"repo_root": str(repo_root), "mode": "project", "session_id": "forged"},
        },
        kwargs={},
        registry={"capture": capture},
        app=app,
        storage_backend=None,
        settings=SimpleNamespace(
            project_root=repo_root,
            public_release=True,
            trusted_repo_roots=(str(repo_root),),
        ),
        state_manager=_StateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"capture"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == "security-tester"
    # The runtime-derived transport ID (from request_context.meta) is used,
    # not the untrusted caller-supplied session_id.
    assert observed["transport_session_id"] == trusted_transport_id
    assert observed["session_id"]


@pytest.mark.asyncio
async def test_execution_context_public_release_requires_runtime_owned_identity() -> None:
    router = RouterContextManager()
    base_payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "public_release": True,
    }

    with pytest.raises(ValueError, match="server-owned in public_release"):
        await router.build_execution_context({**base_payload, "session_id": "forged"})

    with pytest.raises(ValueError, match="trusted runtime-derived transport_session_id"):
        await router.build_execution_context({**base_payload, "transport_session_id": "forged-transport"})


@pytest.mark.asyncio
async def test_public_release_sentinel_isolates_same_day_runs_by_trusted_transport_context(
    tmp_path: Path,
) -> None:
    # In public_release mode the only trusted session discriminator is the
    # runtime-derived transport_session_id from the HTTP mcp-session-id header.
    # Two requests arriving on different transport connections (different header
    # values) must produce different stable session IDs, while repeated calls on
    # the same connection must produce the same stable session ID.
    #
    # The repo_root must be a real directory with a repo marker and must be
    # listed in trusted_repo_roots so the runtime can verify the scope binding.
    repo_root = tmp_path / "sentinel-repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    observed: dict[str, str] = {}
    storage = _SessionAllocatorStorage()

    def _make_app(transport_id: str) -> SimpleNamespace:
        mock_request = SimpleNamespace(headers={"mcp-session-id": transport_id})
        mock_request_context = SimpleNamespace(request=mock_request, meta=None)
        return SimpleNamespace(request_context=mock_request_context)

    async def invoke(router: RouterContextManager, label: str, transport_id: str) -> str:
        def capture(agent: str) -> str:
            current = router.get_current()
            assert current is not None
            observed[label] = current.session_id
            return agent

        return await execute_tool_call(
            name="capture",
            arguments={"agent": "security-tester", "context": {"repo_root": str(repo_root)}},
            kwargs={},
            registry={"capture": capture},
            app=_make_app(transport_id),
            storage_backend=storage,
            settings=SimpleNamespace(
                project_root=repo_root,
                public_release=True,
                trusted_repo_roots=(str(repo_root),),
            ),
            state_manager=_StateManager(),
            router_context_manager=router,
            sentinel_only={"capture"},
            sentinel_allowed={"capture"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

    first_router = RouterContextManager()
    second_router = RouterContextManager()

    assert await invoke(first_router, "run_a_first", "transport-run-A") == "security-tester"
    assert await invoke(first_router, "run_a_second", "transport-run-A") == "security-tester"
    assert await invoke(second_router, "run_b_first", "transport-run-B") == "security-tester"

    # Same transport connection → same stable session
    assert observed["run_a_first"] == observed["run_a_second"]
    # Different transport connections → different stable sessions
    assert observed["run_a_first"] != observed["run_b_first"]


@pytest.mark.asyncio
async def test_public_release_sentinel_fails_closed_without_trusted_transport_discriminator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = RouterContextManager()
    monkeypatch.setattr(tool_runtime, "_derive_transport_session_id", lambda **_kwargs: "")

    with pytest.raises(
        ValueError,
        match="requires trusted runtime-derived transport_session_id",
    ):
        await execute_tool_call(
            name="capture",
            arguments={
                "agent": "security-tester",
                "context": {
                    "repo_root": "/tmp/repo",
                    "mode": "sentinel",
                },
            },
            kwargs={},
            registry={"capture": lambda agent: agent},
            app=SimpleNamespace(request_context=None),
            storage_backend=None,
            settings=SimpleNamespace(project_root=Path("/tmp/repo"), public_release=True),
            state_manager=_StateManager(),
            router_context_manager=router,
            sentinel_only={"capture"},
            sentinel_allowed={"capture"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
