#!/usr/bin/env python3
"""Test set_project tool integration with AgentContextManager."""

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager
from scribe_mcp.shared.session_scope import ResolvedScope, ScopeProvenance
from scribe_mcp import server as server_module
from scribe_mcp.tools import set_project as set_project_tool


@pytest.mark.asyncio
async def test_set_project_with_agent_context():
    """Test set_project tool integration with agent context."""
    print("🧪 Testing set_project with AgentContextManager integration...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        agent_manager = AgentContextManager(storage, state_manager)

        # Test 1: Set project for AgentA
        print("  ✓ Setting project for AgentA...")
        session_a = await agent_manager.start_session("AgentA")

        # Create project record first
        project = await storage.upsert_project(
            name="TestProjectA",
            repo_root=str(temp_path / "project_a"),
            progress_log_path=str(temp_path / "project_a" / "log.md")
        )

        result = await agent_manager.set_current_project("AgentA", "TestProjectA", session_a)
        print(f"    AgentA project: {result['project_name']} (version {result['version']})")

        # Test 2: Set different project for AgentB
        print("  ✓ Setting different project for AgentB...")
        session_b = await agent_manager.start_session("AgentB")

        project_b = await storage.upsert_project(
            name="TestProjectB",
            repo_root=str(temp_path / "project_b"),
            progress_log_path=str(temp_path / "project_b" / "log.md")
        )

        result_b = await agent_manager.set_current_project("AgentB", "TestProjectB", session_b)
        print(f"    AgentB project: {result_b['project_name']} (version {result_b['version']})")

        # Test 3: Verify agent isolation
        print("  ✓ Verifying agent isolation...")
        current_a = await agent_manager.get_current_project("AgentA")
        current_b = await agent_manager.get_current_project("AgentB")

        if current_a["project_name"] == "TestProjectA" and current_b["project_name"] == "TestProjectB":
            print("    ✓ Agent isolation working correctly")
        else:
            print("    ❌ Agent isolation failed")
            return False

        # Test 4: Version conflict detection
        print("  ✓ Testing version conflict detection...")
        try:
            # Try to update with wrong version
            await agent_manager.set_current_project(
                "AgentA", "NewProject", session_a, expected_version=999
            )
            print("    ❌ Should have detected version conflict")
            return False
        except Exception as e:
            print(f"    ✓ Correctly detected version conflict: {type(e).__name__}")

        # Test 5: Session validation
        print("  ✓ Testing session validation...")
        expired_session = await agent_manager.start_session("TestAgent")
        await agent_manager.end_session("TestAgent", expired_session)

        try:
            await agent_manager.set_current_project("TestAgent", "TestProject", expired_session)
            print("    ❌ Should have rejected expired session")
            return False
        except Exception as e:
            print(f"    ✓ Correctly rejected expired session: {type(e).__name__}")

        await storage.close()

    print("✅ set_project integration tests completed successfully!")
    return True


@pytest.mark.asyncio
async def test_agent_context_migration():
    """Test legacy state migration to agent context."""
    print("🧪 Testing legacy state migration...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)

        # Set up legacy state
        legacy_state = await state_manager.load()
        legacy_state.current_project = "LegacyProject"
        await state_manager.persist(legacy_state)

        # Initialize agent manager and run migration
        agent_manager = AgentContextManager(storage, state_manager)

        from scribe_mcp.state.agent_manager import migrate_legacy_state
        await migrate_legacy_state(state_manager, storage)

        # Verify migration
        scribe_project = await agent_manager.get_current_project("Scribe")
        if scribe_project and scribe_project["project_name"] == "LegacyProject":
            print("    ✓ Legacy state migrated successfully")
        else:
            print("    ❌ Legacy state migration failed")
            return False

        # Verify legacy state was cleared
        current_state = await state_manager.load()
        if current_state.current_project is None:
            print("    ✓ Legacy global state cleared")
        else:
            print("    ❌ Legacy global state not cleared")
            return False

        await storage.close()

    print("✅ Legacy migration tests completed successfully!")
    return True


async def main():
    """Run all integration tests."""
    print("🚀 Starting set_project integration tests...\n")

    success1 = await test_set_project_with_agent_context()
    print()
    success2 = await test_agent_context_migration()

    if success1 and success2:
        print("\n🎉 All integration tests passed!")
    else:
        print("\n❌ Some tests failed!")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())


@pytest.mark.asyncio
async def test_set_project_ordinary_mode_does_not_request_bootstrap_recovery(monkeypatch):
    """Ordinary set_project must not depend on explicit bootstrap recovery mode."""
    recovery_mode_calls: list[str | None] = []

    def guarded_bootstrap_resolver(_app_state, *, recovery_mode=None):
        recovery_mode_calls.append(recovery_mode)
        if recovery_mode in {"bootstrap_app_state", "compat_all"}:
            raise AssertionError("Ordinary set_project must not request bootstrap recovery mode")
        return None, {
            "resolution_source": "unresolved",
            "trust_level": "anonymous",
            "fallback_used": False,
            "fallback_chain": [],
        }

    monkeypatch.setattr(
        server_module.app.state,
        "execution_context",
        SimpleNamespace(session_id="bootstrap-session", stable_session_id="bootstrap-stable"),
        raising=False,
    )
    monkeypatch.setattr(server_module, "resolve_bootstrap_execution_context", guarded_bootstrap_resolver)

    with tempfile.TemporaryDirectory() as temp_dir:
        result = await set_project_tool.set_project(
            agent="BugHunterAgent-set-project-proof",
            name="set_project_ordinary_mode_proof",
            root=temp_dir,
            skip_validation=True,
            format="structured",
        )

    assert result["ok"] is True
    assert result["project"]["name"] == "set_project_ordinary_mode_proof"
    assert recovery_mode_calls
    assert all(mode in {None, "", "none"} for mode in recovery_mode_calls)


@pytest.mark.asyncio
async def test_set_project_reports_authoritative_session_id(monkeypatch):
    """set_project should report the authoritative session id used for persistence."""
    resolved_scope = ResolvedScope(
        transport_session_id="transport-session-1",
        stable_session_id=None,
        agent_session_id="agent-session-1",
        repo_root="/tmp",
        project_name=None,
        scoped_reuse_key="scope-key",
        resolution_source="runtime_context",
        trust_level="verified",
        provenance=ScopeProvenance(),
    )

    execution_context = SimpleNamespace(
        session_id="transport-session-1",
        stable_session_id="stable-fallback-1",
        transport_session_id="transport-session-1",
        resolved_scope=resolved_scope,
    )

    def bootstrap_resolver(_app_state, *, recovery_mode=None):
        return execution_context, {
            "resolution_source": "bootstrap_context",
            "trust_level": "claimed",
            "fallback_used": False,
            "fallback_chain": [],
        }

    monkeypatch.setattr(server_module, "resolve_bootstrap_execution_context", bootstrap_resolver)

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = SQLiteStorage(Path(temp_dir) / "authoritative.db")
        await storage.setup()
        state_manager = StateManager(Path(temp_dir) / "state.json", storage_backend=storage)
        agent_manager = AgentContextManager(storage, state_manager)
        monkeypatch.setattr(server_module, "storage_backend", storage)
        monkeypatch.setattr(server_module, "state_manager", state_manager)
        monkeypatch.setattr(server_module, "agent_context_manager", agent_manager, raising=False)
        await storage.upsert_session(
            session_id="transport-session-1",
            transport_session_id="transport-session-1",
            agent_id="CoderAgent-authoritative-session-proof",
            repo_root=temp_dir,
            mode="project",
        )
        await agent_manager.start_session(
            "CoderAgent-authoritative-session-proof",
            session_id="transport-session-1",
        )

        result = await set_project_tool.set_project(
            agent="CoderAgent-authoritative-session-proof",
            name="set_project_authoritative_session_proof",
            root=temp_dir,
            skip_validation=True,
            format="structured",
        )
        persisted_project = await storage.get_session_project(authoritative_session_id := result["side_effects"]["authoritative_session_id"])
        await storage.close()

    assert result["ok"] is True
    authoritative_session_id = result["side_effects"]["authoritative_session_id"]
    assert isinstance(authoritative_session_id, str)
    assert authoritative_session_id
    assert result["project"]["session_id"] == authoritative_session_id
    assert isinstance(result["side_effects"]["scope_resolution_source"], str)
    assert result["side_effects"]["scope_resolution_source"]
    assert result["side_effects"]["global_mirror"]["enabled"] is False
    assert result["scope_resolution"]["source"] == result["side_effects"]["scope_resolution_source"]
    assert result["scope_resolution"]["authoritative_session_id"] == authoritative_session_id
    assert result["scope_resolution"]["global_mirror_performed"] is False
    assert persisted_project == "set_project_authoritative_session_proof"


@pytest.mark.asyncio
async def test_state_manager_same_repo_writes_do_not_global_fallback():
    """Same-repo writes for different projects should stay session-scoped by default."""

    class _Backend:
        def __init__(self):
            self.session_projects = {}
            self.global_project_calls = []

        async def set_session_project(self, session_id, project_name):
            self.session_projects[str(session_id)] = project_name

        async def get_session_project(self, session_id):
            return self.session_projects.get(str(session_id))

        async def upsert_agent_recent_project(self, agent_id, project_name):
            return {"agent_id": agent_id, "project_name": project_name}

        async def set_agent_project(self, **kwargs):
            self.global_project_calls.append(kwargs)
            return kwargs

        async def list_projects_by_repo(self, _repo_root):
            return []

    with tempfile.TemporaryDirectory() as temp_dir:
        backend = _Backend()
        state_manager = StateManager(Path(temp_dir) / "state.json", storage_backend=backend)

        scope_a = ResolvedScope(
            transport_session_id="transport-a",
            stable_session_id="stable-a",
            agent_session_id="agent-a",
            repo_root=temp_dir,
            project_name="project_a",
            scoped_reuse_key=f"{temp_dir}:project_a",
            resolution_source="runtime_context",
            trust_level="verified",
            provenance=ScopeProvenance(),
        )
        scope_b = ResolvedScope(
            transport_session_id="transport-b",
            stable_session_id="stable-b",
            agent_session_id="agent-b",
            repo_root=temp_dir,
            project_name="project_b",
            scoped_reuse_key=f"{temp_dir}:project_b",
            resolution_source="runtime_context",
            trust_level="verified",
            provenance=ScopeProvenance(),
        )

        await state_manager.set_current_project(
            "project_a",
            {"name": "project_a", "root": temp_dir},
            agent_id="AgentA",
            resolved_scope=scope_a,
            mirror_global=False,
            skip_upsert=True,
        )
        await state_manager.set_current_project(
            "project_b",
            {"name": "project_b", "root": temp_dir},
            agent_id="AgentB",
            resolved_scope=scope_b,
            mirror_global=False,
            skip_upsert=True,
        )

        assert backend.session_projects["stable-a"] == "project_a"
        assert backend.session_projects["stable-b"] == "project_b"
        assert backend.global_project_calls == []
