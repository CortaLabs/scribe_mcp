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


@pytest.mark.asyncio
async def test_end_session_blocked_by_canonical_managed_doc_quality_blocker(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "session_teardown_blocked.db"
    state_path = tmp_path / "state.json"
    repo_root = tmp_path.resolve()
    doc_path = tmp_path / "PHASE_PLAN.md"
    doc_path.write_text("# Phase Plan\n", encoding="utf-8")

    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    await storage.upsert_project(
        name="blocked-quality-project",
        repo_root=str(repo_root),
        progress_log_path=str(repo_root / "PROGRESS_LOG.md"),
        docs_json=f'{{"phase_plan":"{doc_path}"}}',
    )
    session_id = await manager.start_session("CoderAgent", session_id="stable-session-blocked")
    await manager.set_current_project("CoderAgent", "blocked-quality-project", session_id)
    original_get_agent_project = storage.get_agent_project

    async def _get_agent_project_with_docs(agent_id: str):
        row = await original_get_agent_project(agent_id)
        if isinstance(row, dict):
            row = dict(row)
            row["docs"] = {"phase_plan": str(doc_path)}
        return row

    monkeypatch.setattr(storage, "get_agent_project", _get_agent_project_with_docs)

    from scribe_mcp import readiness

    monkeypatch.setattr(
        readiness,
        "collect_managed_doc_quality_warnings",
        lambda **_: [{"code": "SCF_FAILED_WRITE_RESIDUE", "blocking": True, "severity": "critical"}],
    )

    with pytest.raises(ValueError, match="SESSION_END_BLOCKED_BY_DOC_QUALITY"):
        await manager.end_session("CoderAgent", session_id)

    await storage.close()


@pytest.mark.asyncio
async def test_end_session_ignores_excluded_non_target_docs_for_quality_blockers(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "session_teardown_excluded.db"
    state_path = tmp_path / "state.json"
    repo_root = tmp_path.resolve()
    progress_log = tmp_path / "PROGRESS_LOG.md"
    progress_log.write_text("# Progress\n", encoding="utf-8")

    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    await storage.upsert_project(
        name="excluded-quality-project",
        repo_root=str(repo_root),
        progress_log_path=str(progress_log),
        docs_json=f'{{"progress_log":"{progress_log}"}}',
    )
    session_id = await manager.start_session("CoderAgent", session_id="stable-session-excluded")
    await manager.set_current_project("CoderAgent", "excluded-quality-project", session_id)
    original_get_agent_project = storage.get_agent_project

    async def _get_agent_project_with_progress_doc(agent_id: str):
        row = await original_get_agent_project(agent_id)
        if isinstance(row, dict):
            row = dict(row)
            row["docs"] = {"progress_log": str(progress_log)}
            row["progress_log"] = str(progress_log)
        return row

    monkeypatch.setattr(storage, "get_agent_project", _get_agent_project_with_progress_doc)

    from scribe_mcp import readiness

    monkeypatch.setattr(
        readiness,
        "collect_managed_doc_quality_warnings",
        lambda **_: [{"code": "SCF_FAILED_WRITE_RESIDUE", "blocking": True, "severity": "critical"}],
    )

    await manager.end_session("CoderAgent", session_id)
    assert await storage.get_session_project(session_id) is None

    await storage.close()
