#!/usr/bin/env python3
"""Exercise real local identity/resumption state with pytest-enforced oracles."""

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager
from scribe_mcp.state.agent_identity import AgentIdentity
from scribe_mcp.state import agent_identity as identity_module


pytestmark = pytest.mark.regression


@asynccontextmanager
async def _local_components():
    """Own one disposable backend, including cleanup after a failed assertion."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        storage = SQLiteStorage(root / "test.db")
        try:
            await storage.setup()
            # Inject the owned backend rather than opening an unclosed second one.
            state_manager = StateManager(root / "state.json", storage_backend=storage)
            yield root, storage, state_manager
        finally:
            await storage.close()


@pytest.mark.asyncio
async def test_automatic_agent_identification(test_agent):
    """Preserve identity reuse, context identity, and activity tracking checks."""
    async with _local_components() as (_, storage, state_manager):
        identity = AgentIdentity(state_manager)
        agent_id_1 = await identity.get_or_create_agent_id()
        assert agent_id_1, "Agent ID should be created"
        agent_id_2 = await identity.get_or_create_agent_id()
        assert agent_id_1 == agent_id_2, "Agent IDs should match"

        # A new identity object must read the state, not just its own ID cache.
        reloaded_identity = AgentIdentity(state_manager)
        assert await reloaded_identity.get_or_create_agent_id() == agent_id_1
        state = await state_manager.load()
        assert state.agent_state["last_agent_id"] == agent_id_1

        context = {"client_id": test_agent, "session_id": "session-456"}
        agent_id_3 = await identity.get_or_create_agent_id(context)
        assert agent_id_3.startswith("mcp-"), "Agent ID should come from context"
        assert agent_id_3 == f"mcp-{test_agent}"

        await identity.update_agent_activity(agent_id_1, "test_activity", {"test": True})
        state = await state_manager.load()
        assert hasattr(state, "agent_state"), "Activity tracking failed"
        assert "activity_log" in state.agent_state, "Activity tracking failed"
        assert len(state.agent_state["activity_log"]) > 0, "Activity tracking failed"


@pytest.mark.asyncio
async def test_project_resumption(test_agent):
    """Reconnect with a genuine stable session; explicit logout revokes bindings."""
    async with _local_components() as (root, storage, state_manager):
        agent_manager = AgentContextManager(storage, state_manager)
        identity = AgentIdentity(state_manager)
        sessions = []
        try:
            project_root = root / "test_project"
            project_root.mkdir()
            progress_log = project_root / "PROGRESS_LOG.md"
            progress_log.touch()
            await storage.upsert_project(
                name="ResumptionTestProject",
                repo_root=str(project_root),
                progress_log_path=str(progress_log),
            )

            session_1 = await agent_manager.start_session(test_agent)
            sessions.append((test_agent, session_1))
            await agent_manager.set_current_project(
                test_agent, "ResumptionTestProject", session_1
            )

            # Reconnect through a fresh manager against the real persisted binding.
            # end_session is logout: it deliberately clears this binding, so it
            # belongs in cleanup, not in the reconnect fixture.
            agent_manager = AgentContextManager(storage, state_manager)
            resumed_session = await identity.resume_agent_session(
                test_agent, agent_manager, stable_session_id=session_1
            )
            assert resumed_session, "Failed to resume session"
            assert resumed_session == session_1, "Stable session should be reused"
            current_project = await agent_manager.get_current_project(test_agent)
            assert current_project and (
                current_project["project_name"] == "ResumptionTestProject"
            ), "Project was not restored"

            # Use the real context identity producer for a distinct local agent;
            # no Council persona or authority record is fabricated.
            fresh_agent = await identity.get_or_create_agent_id({"client_id": test_agent})
            assert fresh_agent != test_agent
            fresh_session = await identity.resume_agent_session(fresh_agent, agent_manager)
            assert fresh_session, "Failed to create fresh session"
            sessions.append((fresh_agent, fresh_session))
            current_project = await agent_manager.get_current_project(fresh_agent)
            assert current_project is None, "New agent should have no project"
        finally:
            for agent_id, session_id in reversed(sessions):
                await agent_manager.end_session(agent_id, session_id)


@pytest.mark.asyncio
async def test_agent_state_updates(test_agent, monkeypatch):
    """Check all activity semantics at the real persistence cadence, without waits."""
    # Replace only this module's clock reference, not process-wide time.monotonic
    # (which asyncio also uses). Keep the configured persistence interval intact.
    now = [1_000_000_000_000.0]
    monkeypatch.setattr(identity_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    async with _local_components() as (_, storage, state_manager):
        identity = AgentIdentity(state_manager)
        agent_id = await identity.get_or_create_agent_id({"client_id": test_agent})
        activities = [
            ("set_project", {"project_name": "TestProject"}),
            ("append_entry", {"message_length": 50}),
            ("read_recent", {"limit": 10}),
            ("query_entries", {"filters": "test"}),
        ]
        for index, (activity_type, metadata) in enumerate(activities):
            if index == len(activities) - 1:
                now[0] += identity._activity_persist_interval_seconds
            await identity.update_agent_activity(agent_id, activity_type, metadata)

        state = await state_manager.load()
        assert hasattr(state, "agent_state"), "Activity log not created"
        assert "activity_log" in state.agent_state, "Activity log not created"
        activity_log = state.agent_state["activity_log"]
        assert len(activity_log) >= len(activities), (
            f"Expected {len(activities)} activities, got {len(activity_log)}"
        )
        assert [(entry["activity_type"], entry["metadata"]) for entry in activity_log] == activities
        assert state.agent_state.get("last_activity") == activities[-1][0], (
            "Last activity not tracked correctly"
        )

        # Buffer more than the cap, then flush on the final real update.
        for index in range(110):
            if index == 109:
                now[0] += identity._activity_persist_interval_seconds
            await identity.update_agent_activity(agent_id, "bulk_test", {"index": index})

        state = await state_manager.load()
        activity_log = state.agent_state["activity_log"]
        assert len(activity_log) <= 100, "Activity log should be limited to 100 entries"
        assert len(activity_log) == 100
        assert [entry["metadata"]["index"] for entry in activity_log] == list(range(10, 110))
        assert state.agent_state["last_activity"] == "bulk_test"


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["project", "activities"])
async def test_semantic_failures_are_not_false_green(test_agent, monkeypatch, fault):
    """Test-of-test sensitivity only; injected bad observations are not product proof."""
    if fault == "project":
        real_get = AgentContextManager.get_current_project

        async def wrong_observation(manager, agent_id):
            project = await real_get(manager, agent_id)
            return {**project, "project_name": "incorrect-project"} if project else project

        monkeypatch.setattr(AgentContextManager, "get_current_project", wrong_observation)
        with pytest.raises(AssertionError, match="Project was not restored"):
            await test_project_resumption(test_agent)
    else:
        real_load = StateManager.load

        async def incomplete_observation(manager):
            state = await real_load(manager)
            activity_log = state.agent_state.get("activity_log", [])
            state.agent_state["activity_log"] = activity_log[:1]
            return state

        monkeypatch.setattr(StateManager, "load", incomplete_observation)
        with pytest.raises(AssertionError, match="Expected 4 activities, got 1"):
            await test_agent_state_updates(test_agent, monkeypatch)


def main():
    """Use the same pytest journeys/fixtures; assertion failures exit nonzero."""
    return pytest.main([str(Path(__file__).resolve()), "-q", "-n0"])


if __name__ == "__main__":
    raise SystemExit(main())
