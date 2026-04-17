from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared.tool_runtime import execute_tool_call
from scribe_mcp.state.agent_manager import AgentContextManager
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage


class _NoopStateManager:
    async def load(self):
        return SimpleNamespace(get_session_mode=lambda _session_id: None)


@pytest.mark.asyncio
async def test_end_session_revokes_persisted_bindings_and_runtime_caches(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "session_teardown.db"
    state_path = tmp_path / "state.json"
    bound_repo = (tmp_path / "bound-repo").resolve()
    default_repo = (tmp_path / "default-repo").resolve()
    bound_repo.mkdir()
    default_repo.mkdir()

    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    await storage.upsert_project(
        name="hardening-project",
        repo_root=str(bound_repo),
        progress_log_path=str(bound_repo / "PROGRESS_LOG.md"),
    )

    session_id = await manager.start_session("CoderAgent", session_id="stable-session-hardening")
    await storage.upsert_session(
        session_id=session_id,
        transport_session_id="transport-hardening",
        repo_root=str(bound_repo),
        mode="project",
    )
    await storage.set_session_project(session_id, "hardening-project")
    await manager.set_current_project("CoderAgent", "hardening-project", session_id)

    router = RouterContextManager(storage_backend=storage)
    await router.get_or_create_session_id("transport-hardening")
    await router.cache_project_binding(session_id, "hardening-project")
    await router.cache_agent_session_id("identity-hardening", session_id)
    await router.record_file_read(session_id, str(bound_repo / "tracked.py"))

    import scribe_mcp.server as server_module

    monkeypatch.setattr(server_module, "router_context_manager", router, raising=False)

    await manager.end_session("CoderAgent", session_id)

    assert await storage.get_session_by_transport("transport-hardening") is None
    assert await storage.get_session_project(session_id) is None
    agent_project = await storage.get_agent_project("CoderAgent")
    assert agent_project is not None
    assert agent_project.get("project_name") is None

    assert await router.get_cached_project(session_id) is None
    assert await router.get_cached_agent_session_id("identity-hardening") is None
    assert not await router.has_file_been_read(session_id, str(bound_repo / "tracked.py"))

    observed: dict[str, str | None] = {"called": None}

    def capture_tool(agent: str) -> str:
        current = router.get_current()
        assert current is not None
        observed["called"] = "yes"
        observed["session_id"] = current.session_id
        observed["repo_root"] = current.repo_root
        observed["project_name"] = current.resolved_scope.project_name if current.resolved_scope else None
        return agent

    with pytest.raises(ValueError, match="repo scope unresolved"):
        await execute_tool_call(
            name="capture_tool",
            arguments={"agent": "CoderAgent"},
            kwargs={"context": {"transport_session_id": "transport-hardening", "mode": "project"}},
            registry={"capture_tool": capture_tool},
            app=SimpleNamespace(request_context=None),
            storage_backend=storage,
            settings=SimpleNamespace(project_root=default_repo),
            state_manager=_NoopStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"capture_tool"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

    assert observed["called"] is None

    await storage.close()
