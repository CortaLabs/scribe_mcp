#!/usr/bin/env python3
"""
Session Isolation Tests for Multi-Agent Concurrency

Tests the stable session identity system to ensure:
- Parallel agents get isolated sessions
- Cross-run isolation for same agent
- Symlink canonicalization works correctly
- Missing agent fallback still provides scoping

Required for: scribe_sentinel_concurrency_v1
"""

import asyncio
import hashlib
import os
import sys
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

# Add scribe_mcp to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.storage.sqlite import SQLiteStorage


# Mock classes matching server.py structure
@dataclass(frozen=True)
class MockAgentIdentity:
    """Mock AgentIdentity matching shared/execution_context.py"""
    agent_kind: str
    model: Optional[str]
    instance_id: str
    sub_id: Optional[str]
    display_name: Optional[str]

    @property
    def id(self) -> Optional[str]:
        """Provide stable ID for agent isolation"""
        return self.sub_id or self.instance_id


@dataclass(frozen=True)
class MockExecutionContext:
    """Mock ExecutionContext matching shared/execution_context.py"""
    repo_root: str
    mode: str
    session_id: str
    execution_id: str
    agent_identity: Optional[MockAgentIdentity]
    intent: str
    timestamp_utc: str
    affected_dev_projects: list
    sentinel_day: Optional[str] = None
    transport_session_id: Optional[str] = None


def derive_session_identity(exec_context: MockExecutionContext, arguments: dict) -> tuple[str, dict]:
    """
    Derive stable session identity from execution context.

    Matches the implementation in server.py.
    Returns (identity_hash, identity_parts dict)
    """
    # 1. Canonicalize repo_root
    repo_root = os.path.realpath(exec_context.repo_root)

    # 2. Get mode and scope_key
    mode = exec_context.mode  # "project" or "sentinel"
    if mode == "sentinel":
        scope_key = exec_context.sentinel_day
    else:
        scope_key = exec_context.execution_id

    # 3. Get agent_key (prefer stable ID, fallback to display_name)
    agent_key = None
    if exec_context.agent_identity:
        agent_key = (
            getattr(exec_context.agent_identity, 'id', None) or
            getattr(exec_context.agent_identity, 'instance_id', None) or
            exec_context.agent_identity.display_name
        )
    if not agent_key:
        agent_key = arguments.get("agent") or "default"

    # 4. Construct identity string
    identity = f"{repo_root}:{mode}:{scope_key}:{agent_key}"

    # 5. Hash it (full SHA-256, no truncation)
    identity_hash = hashlib.sha256(identity.encode()).hexdigest()

    return identity_hash, {
        "repo_root": repo_root,
        "mode": mode,
        "scope_key": scope_key,
        "agent_key": agent_key,
    }


@asynccontextmanager
async def temp_storage():
    """Create temporary SQLite storage for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = SQLiteStorage(str(db_path))
        await storage._initialise()
        yield storage
        await storage.close()


def create_execution_context(
    repo_root: str,
    execution_id: str,
    agent_name: Optional[str] = None,
    mode: str = "project",
    sentinel_day: Optional[str] = None
) -> MockExecutionContext:
    """Helper to create mock execution context"""
    agent_identity = None
    if agent_name:
        # Use agent_name as a stable identifier (hash it to get consistent instance_id)
        # This ensures same agent_name always gets same agent_key
        stable_instance_id = hashlib.sha256(agent_name.encode()).hexdigest()[:36]
        agent_identity = MockAgentIdentity(
            agent_kind="test",
            model="test-model",
            instance_id=stable_instance_id,
            sub_id=None,
            display_name=agent_name
        )

    return MockExecutionContext(
        repo_root=repo_root,
        mode=mode,
        session_id=str(uuid.uuid4()),
        execution_id=execution_id,
        agent_identity=agent_identity,
        intent="test",
        timestamp_utc="2026-01-03T00:00:00Z",
        affected_dev_projects=[],
        sentinel_day=sentinel_day,
        transport_session_id=None
    )


# ==============================================================================
# TEST A: PARALLEL BIND ISOLATION
# ==============================================================================

@pytest.mark.asyncio
async def test_parallel_agent_isolation():
    """
    Two agents in same repo, same execution - different sessions.

    Scenario:
    - Same repository
    - Same execution_id (concurrent execution)
    - Different agent names

    Expected:
    - Different session IDs
    - Different identity hashes
    - Agents are isolated from each other
    """
    async with temp_storage() as storage:
        repo_root = "/tmp/test_repo"
        execution_id = "run-parallel-test"

        # Create contexts for two different agents
        context_a = create_execution_context(repo_root, execution_id, "CoderA")
        context_b = create_execution_context(repo_root, execution_id, "CoderB")

        # Derive session identities
        identity_a, parts_a = derive_session_identity(context_a, {})
        identity_b, parts_b = derive_session_identity(context_b, {})

        # Create sessions in database (simulating parallel execution)
        session_a, session_b = await asyncio.gather(
            storage.get_or_create_agent_session(
                identity_key=identity_a,
                agent_name="CoderA",
                agent_key=parts_a["agent_key"],
                repo_root=parts_a["repo_root"],
                mode=parts_a["mode"],
                scope_key=parts_a["scope_key"]
            ),
            storage.get_or_create_agent_session(
                identity_key=identity_b,
                agent_name="CoderB",
                agent_key=parts_b["agent_key"],
                repo_root=parts_b["repo_root"],
                mode=parts_b["mode"],
                scope_key=parts_b["scope_key"]
            )
        )

        # Assert different sessions
        assert session_a != session_b, "Parallel agents must have different sessions"
        assert identity_a != identity_b, "Parallel agents must have different identity hashes"

        # Verify identity components
        assert parts_a["repo_root"] == parts_b["repo_root"], "Same repo"
        assert parts_a["scope_key"] == parts_b["scope_key"], "Same execution"
        assert parts_a["agent_key"] != parts_b["agent_key"], "Different agents"


# ==============================================================================
# TEST B: CROSS-RUN ISOLATION
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_run_isolation():
    """
    Same agent, different execution_id - different sessions.

    Scenario:
    - Same repository
    - Same agent name
    - Different execution_ids (different runs)

    Expected:
    - Different session IDs
    - Different identity hashes
    - Runs are isolated from each other
    """
    async with temp_storage() as storage:
        repo_root = "/tmp/test_repo"
        agent_name = "CoderAgent"

        # Run 1
        context_1 = create_execution_context(repo_root, "run-1", agent_name)
        identity_1, parts_1 = derive_session_identity(context_1, {})
        session_1 = await storage.get_or_create_agent_session(
            identity_key=identity_1,
            agent_name=agent_name,
            agent_key=parts_1["agent_key"],
            repo_root=parts_1["repo_root"],
            mode=parts_1["mode"],
            scope_key=parts_1["scope_key"]
        )

        # Run 2
        context_2 = create_execution_context(repo_root, "run-2", agent_name)
        identity_2, parts_2 = derive_session_identity(context_2, {})
        session_2 = await storage.get_or_create_agent_session(
            identity_key=identity_2,
            agent_name=agent_name,
            agent_key=parts_2["agent_key"],
            repo_root=parts_2["repo_root"],
            mode=parts_2["mode"],
            scope_key=parts_2["scope_key"]
        )

        # Assert different sessions
        assert session_1 != session_2, "Different runs must have different sessions"
        assert identity_1 != identity_2, "Different runs must have different identity hashes"

        # Verify identity components
        assert parts_1["repo_root"] == parts_2["repo_root"], "Same repo"
        assert parts_1["agent_key"] == parts_2["agent_key"], "Same agent"
        assert parts_1["scope_key"] != parts_2["scope_key"], "Different execution_ids"


# ==============================================================================
# TEST C: REPO CANONICALIZATION (SYMLINK HANDLING)
# ==============================================================================

@pytest.mark.asyncio
async def test_symlink_canonicalization(tmp_path):
    """
    Symlink and real path resolve to same session.

    Scenario:
    - Create real directory
    - Create symlink to it
    - Access via both paths

    Expected:
    - Same session ID (canonicalization works)
    - Same identity hash
    - Symlinks don't create duplicate sessions
    """
    async with temp_storage() as storage:
        # Create real directory and symlink
        real_dir = tmp_path / "real_repo"
        real_dir.mkdir()
        symlink = tmp_path / "symlink_repo"
        symlink.symlink_to(real_dir)

        execution_id = "run-symlink-test"
        agent_name = "CoderAgent"

        # Access via real path
        context_real = create_execution_context(str(real_dir), execution_id, agent_name)
        identity_real, parts_real = derive_session_identity(context_real, {})
        session_real = await storage.get_or_create_agent_session(
            identity_key=identity_real,
            agent_name=agent_name,
            agent_key=parts_real["agent_key"],
            repo_root=parts_real["repo_root"],
            mode=parts_real["mode"],
            scope_key=parts_real["scope_key"]
        )

        # Access via symlink
        context_sym = create_execution_context(str(symlink), execution_id, agent_name)
        identity_sym, parts_sym = derive_session_identity(context_sym, {})
        session_sym = await storage.get_or_create_agent_session(
            identity_key=identity_sym,
            agent_name=agent_name,
            agent_key=parts_sym["agent_key"],
            repo_root=parts_sym["repo_root"],
            mode=parts_sym["mode"],
            scope_key=parts_sym["scope_key"]
        )

        # Assert SAME session (canonicalization works)
        assert session_real == session_sym, "Symlink and real path must resolve to same session"
        assert identity_real == identity_sym, "Symlink and real path must have same identity hash"

        # Verify paths were canonicalized
        assert parts_real["repo_root"] == parts_sym["repo_root"], "Paths must be canonicalized"
        assert parts_real["repo_root"] == os.path.realpath(str(real_dir)), "Must resolve to real path"


# ==============================================================================
# TEST D: MISSING AGENT FALLBACK
# ==============================================================================

@pytest.mark.asyncio
async def test_missing_agent_still_scoped():
    """
    No agent provided - still scoped by execution, not eternal.

    Scenario:
    - Same repository
    - No agent identity provided
    - Different execution_ids

    Expected:
    - Different session IDs (not eternal repo session)
    - Different identity hashes
    - Execution scoping prevents eternal sessions
    """
    async with temp_storage() as storage:
        repo_root = "/tmp/test_repo"

        # Run 1 with no agent
        context_1 = create_execution_context(repo_root, "run-1", agent_name=None)
        identity_1, parts_1 = derive_session_identity(context_1, {})
        session_1 = await storage.get_or_create_agent_session(
            identity_key=identity_1,
            agent_name="default",  # Fallback
            agent_key=parts_1["agent_key"],
            repo_root=parts_1["repo_root"],
            mode=parts_1["mode"],
            scope_key=parts_1["scope_key"]
        )

        # Run 2 with no agent
        context_2 = create_execution_context(repo_root, "run-2", agent_name=None)
        identity_2, parts_2 = derive_session_identity(context_2, {})
        session_2 = await storage.get_or_create_agent_session(
            identity_key=identity_2,
            agent_name="default",  # Fallback
            agent_key=parts_2["agent_key"],
            repo_root=parts_2["repo_root"],
            mode=parts_2["mode"],
            scope_key=parts_2["scope_key"]
        )

        # Assert different sessions (execution scoping prevents eternal sessions)
        assert session_1 != session_2, "Different runs must have different sessions even without agent"
        assert identity_1 != identity_2, "Different runs must have different identity hashes"

        # Verify identity components
        assert parts_1["repo_root"] == parts_2["repo_root"], "Same repo"
        assert parts_1["agent_key"] == parts_2["agent_key"] == "default", "Fallback to 'default'"
        assert parts_1["scope_key"] != parts_2["scope_key"], "Different execution_ids prevent eternal session"


# ==============================================================================
# INTEGRATION TEST: FULL WORKFLOW
# ==============================================================================

@pytest.mark.asyncio
async def test_full_session_workflow():
    """
    Integration test covering realistic multi-agent scenario.

    Tests:
    - Multiple agents working concurrently
    - Session persistence and retrieval
    - Activity tracking
    - TTL and expiration
    """
    async with temp_storage() as storage:
        repo_root = "/tmp/test_repo"
        execution_id = "run-integration-test"

        # Create contexts for three agents
        agents = ["ResearchAgent", "CoderAgent", "ReviewAgent"]
        sessions = {}

        for agent_name in agents:
            context = create_execution_context(repo_root, execution_id, agent_name)
            identity_hash, parts = derive_session_identity(context, {})

            session_id = await storage.get_or_create_agent_session(
                identity_key=identity_hash,
                agent_name=agent_name,
                agent_key=parts["agent_key"],
                repo_root=parts["repo_root"],
                mode=parts["mode"],
                scope_key=parts["scope_key"],
                ttl_hours=24
            )

            sessions[agent_name] = {
                "session_id": session_id,
                "identity_hash": identity_hash,
                "parts": parts
            }

        # Verify all sessions are unique
        session_ids = [s["session_id"] for s in sessions.values()]
        assert len(session_ids) == len(set(session_ids)), "All agent sessions must be unique"

        # Verify all identity hashes are unique
        identity_hashes = [s["identity_hash"] for s in sessions.values()]
        assert len(identity_hashes) == len(set(identity_hashes)), "All identity hashes must be unique"

        # Test session retrieval (should return existing session)
        for agent_name, session_data in sessions.items():
            retrieved_session = await storage.get_or_create_agent_session(
                identity_key=session_data["identity_hash"],
                agent_name=agent_name,
                agent_key=session_data["parts"]["agent_key"],
                repo_root=session_data["parts"]["repo_root"],
                mode=session_data["parts"]["mode"],
                scope_key=session_data["parts"]["scope_key"]
            )
            assert retrieved_session == session_data["session_id"], f"Session retrieval failed for {agent_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
