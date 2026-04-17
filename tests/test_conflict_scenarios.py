#!/usr/bin/env python3
"""Conflict and concurrency scenarios for agent-scoped operations."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scribe_mcp.state.agent_manager import AgentContextManager, SessionLeaseExpired
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.base import ConflictError
from scribe_mcp.storage.sqlite import SQLiteStorage


@pytest.mark.asyncio
async def test_same_repo_different_project_concurrent_agents_keep_final_attribution(tmp_path: Path) -> None:
    """Concurrent writes in one repo must preserve per-agent final project attribution."""
    db_path = tmp_path / "test.db"
    state_path = tmp_path / "state.json"
    repo_root = tmp_path / "shared_repo"
    repo_root.mkdir(parents=True)

    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    await storage.upsert_project(
        name="ProjectAlpha",
        repo_root=str(repo_root),
        progress_log_path=str(repo_root / "alpha.log"),
    )
    await storage.upsert_project(
        name="ProjectBeta",
        repo_root=str(repo_root),
        progress_log_path=str(repo_root / "beta.log"),
    )

    session_a = await manager.start_session("AgentAlpha")
    session_b = await manager.start_session("AgentBeta")

    result_a, result_b = await asyncio.gather(
        manager.set_current_project("AgentAlpha", "ProjectAlpha", session_a),
        manager.set_current_project("AgentBeta", "ProjectBeta", session_b),
    )

    final_a = await manager.get_current_project("AgentAlpha")
    final_b = await manager.get_current_project("AgentBeta")

    assert result_a["project_name"] == "ProjectAlpha"
    assert result_b["project_name"] == "ProjectBeta"
    assert final_a is not None and final_a["project_name"] == "ProjectAlpha"
    assert final_b is not None and final_b["project_name"] == "ProjectBeta"
    assert final_a["session_id"] == session_a
    assert final_b["session_id"] == session_b
    assert final_a["updated_by"] == "AgentAlpha"
    assert final_b["updated_by"] == "AgentBeta"

    await storage.close()


@pytest.mark.asyncio
async def test_stale_expected_version_raises_conflict_error(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    state_path = tmp_path / "state.json"

    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    await storage.upsert_project(
        name="ConflictProject",
        repo_root=str(tmp_path / "repo"),
        progress_log_path=str(tmp_path / "repo" / "log.md"),
    )

    session_id = await manager.start_session("ConflictAgent")
    first = await manager.set_current_project("ConflictAgent", "ConflictProject", session_id)

    with pytest.raises(ConflictError):
        await manager.set_current_project(
            "ConflictAgent",
            "ConflictProject",
            session_id,
            expected_version=first["version"] + 10,
        )

    await storage.close()


@pytest.mark.asyncio
async def test_expired_and_hijacked_sessions_are_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    state_path = tmp_path / "state.json"

    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    await storage.upsert_project(
        name="SessionTestProject",
        repo_root=str(tmp_path / "repo"),
        progress_log_path=str(tmp_path / "repo" / "log.md"),
    )

    session_a = await manager.start_session("AgentA")
    session_b = await manager.start_session("AgentB")
    await manager.set_current_project("AgentA", "SessionTestProject", session_a)

    await manager.end_session("AgentA", session_a)
    with pytest.raises(SessionLeaseExpired):
        await manager.set_current_project("AgentA", "SessionTestProject", session_a)

    with pytest.raises(SessionLeaseExpired):
        await manager.set_current_project("AgentB", "SessionTestProject", session_a)

    # Control assertion: owner can still write with active lease.
    success = await manager.set_current_project("AgentB", "SessionTestProject", session_b)
    assert success["project_name"] == "SessionTestProject"
    assert success["session_id"] == session_b

    await storage.close()
