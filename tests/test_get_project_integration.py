#!/usr/bin/env python3
"""Integration tests for get_project context hydration."""

from pathlib import Path
from dataclasses import replace

import pytest
import pytest_asyncio
import tempfile
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from scribe_mcp.tools.get_project import _read_recent_progress_entries, _gather_doc_info, get_project
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp import server
from scribe_mcp.shared.execution_context import (
    AgentAttributionV1, AuthorizationEvidenceV1, ResolvedProjectTargetV1,
    RouterContextManager, build_resolved_request_context,
)
from scribe_mcp.state.agent_manager import AgentContextManager
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with test files."""
    temp_dir = tempfile.mkdtemp()
    dev_plan_dir = Path(temp_dir) / ".scribe" / "docs" / "dev_plans" / "test_project"
    dev_plan_dir.mkdir(parents=True, exist_ok=True)

    yield dev_plan_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_progress_log(temp_project_dir):
    """Create a sample progress log with multiple entries."""
    log_path = temp_project_dir / "PROGRESS_LOG.md"

    # Create log with 7 entries (to test limit of 5)
    entries = [
        "[ℹ️] [2026-01-03 08:00:00 UTC] [Agent: ResearchAgent] [Project: test_project] Initial research started",
        "[✅] [2026-01-03 09:00:00 UTC] [Agent: ResearchAgent] [Project: test_project] Research phase complete with high confidence (0.95)",
        "[ℹ️] [2026-01-03 10:00:00 UTC] [Agent: ArchitectAgent] [Project: test_project] Architecture design in progress",
        "[✅] [2026-01-03 11:00:00 UTC] [Agent: ArchitectAgent] [Project: test_project] Architecture guide completed - all sections filled",
        "[🐞] [2026-01-03 12:00:00 UTC] [Agent: CoderAgent] [Project: test_project] Found bug in authentication module during implementation",
        "[✅] [2026-01-03 13:00:00 UTC] [Agent: CoderAgent] [Project: test_project] Bug fix deployed and tested - all tests passing",
        "[🎯] [2026-01-03 14:00:00 UTC] [Agent: ReviewAgent] [Project: test_project] Final review complete - project approved with 95% score",
    ]

    with open(log_path, 'w') as f:
        f.write("# Progress Log\n\n")
        for entry in entries:
            f.write(f"{entry}\n")

    return log_path


@pytest.fixture
def sample_docs(temp_project_dir):
    """Create sample documentation files."""
    # Architecture guide
    arch_path = temp_project_dir / "ARCHITECTURE_GUIDE.md"
    with open(arch_path, 'w') as f:
        f.write("# Architecture Guide\n\n")
        f.write("## Problem Statement\n\nSample problem.\n\n")
        f.write("## System Overview\n\nSample overview.\n\n")
        for i in range(50):  # Make it 50+ lines
            f.write(f"Line {i}\n")

    # Phase plan
    phase_path = temp_project_dir / "PHASE_PLAN.md"
    with open(phase_path, 'w') as f:
        f.write("# Phase Plan\n\n")
        for i in range(30):
            f.write(f"Phase {i}\n")

    # Checklist
    checklist_path = temp_project_dir / "CHECKLIST.md"
    with open(checklist_path, 'w') as f:
        f.write("# Checklist\n\n")
        for i in range(20):
            f.write(f"- [ ] Task {i}\n")

    return {
        "architecture": arch_path,
        "phase_plan": phase_path,
        "checklist": checklist_path
    }


class TestReadRecentProgressEntries:
    """Test the _read_recent_progress_entries helper function."""

    @pytest.mark.asyncio
    async def test_read_5_entries_from_log_with_7(self, sample_progress_log):
        """Test reading last 5 entries when log has 7 entries."""
        entries = await _read_recent_progress_entries(str(sample_progress_log), limit=5)

        assert len(entries) == 5, "Should return exactly 5 entries"

        # Verify it returns the LAST 5 entries
        assert entries[0]["agent"] == "ArchitectAgent"
        assert entries[-1]["agent"] == "ReviewAgent"

        # Verify NO truncation - complete messages
        assert "Architecture design in progress" in entries[0]["message"]
        assert "Final review complete - project approved with 95% score" in entries[-1]["message"]

    @pytest.mark.asyncio
    async def test_read_all_entries_when_fewer_than_limit(self, temp_project_dir):
        """Test reading entries when log has fewer than limit."""
        log_path = temp_project_dir / "PROGRESS_LOG.md"

        # Create log with only 3 entries
        entries_text = [
            "[ℹ️] [2026-01-03 08:00:00 UTC] [Agent: ResearchAgent] [Project: test] Entry 1",
            "[✅] [2026-01-03 09:00:00 UTC] [Agent: ArchitectAgent] [Project: test] Entry 2",
            "[🎯] [2026-01-03 10:00:00 UTC] [Agent: CoderAgent] [Project: test] Entry 3",
        ]

        with open(log_path, 'w') as f:
            f.write("# Progress Log\n\n")
            for entry in entries_text:
                f.write(f"{entry}\n")

        entries = await _read_recent_progress_entries(str(log_path), limit=5)

        assert len(entries) == 3, "Should return all 3 available entries"
        assert entries[0]["message"] == "Entry 1"
        assert entries[-1]["message"] == "Entry 3"

    @pytest.mark.asyncio
    async def test_no_entries_returns_empty_list(self, temp_project_dir):
        """Test handling of empty progress log."""
        log_path = temp_project_dir / "PROGRESS_LOG.md"

        with open(log_path, 'w') as f:
            f.write("# Progress Log\n\n")

        entries = await _read_recent_progress_entries(str(log_path), limit=5)

        assert len(entries) == 0, "Should return empty list for log with no entries"

    @pytest.mark.asyncio
    async def test_nonexistent_log_returns_empty_list(self):
        """Test handling of nonexistent log file."""
        entries = await _read_recent_progress_entries("/nonexistent/path.md", limit=5)

        assert len(entries) == 0, "Should return empty list for nonexistent file"

    @pytest.mark.asyncio
    async def test_complete_messages_no_truncation(self, sample_progress_log):
        """Critical test: Verify NO truncation of messages."""
        entries = await _read_recent_progress_entries(str(sample_progress_log), limit=5)

        # Find the longest message
        longest_entry = max(entries, key=lambda e: len(e["message"]))

        # Verify complete message is present
        assert len(longest_entry["message"]) > 50, "Should have long messages"
        assert "..." not in longest_entry["message"], "Should NOT have truncation markers"

        # Verify specific complete messages
        review_entry = [e for e in entries if e["agent"] == "ReviewAgent"]
        if review_entry:
            assert "Final review complete - project approved with 95% score" == review_entry[0]["message"]

    @pytest.mark.asyncio
    async def test_timestamp_parsing(self, sample_progress_log):
        """Test that timestamps are correctly parsed."""
        entries = await _read_recent_progress_entries(str(sample_progress_log), limit=5)

        for entry in entries:
            assert "timestamp" in entry
            assert "UTC" in entry["timestamp"]
            # Verify timestamp format
            assert entry["timestamp"].startswith("2026-01-03")

    @pytest.mark.asyncio
    async def test_emoji_extraction(self, sample_progress_log):
        """Test that emojis are correctly extracted."""
        entries = await _read_recent_progress_entries(str(sample_progress_log), limit=5)

        emojis = [e["emoji"] for e in entries]
        assert "ℹ️" in emojis or "✅" in emojis or "🐞" in emojis or "🎯" in emojis


class TestGatherDocInfo:
    """Test the _gather_doc_info helper function."""

    @pytest.mark.asyncio
    async def test_gather_all_docs(self, temp_project_dir, sample_docs, sample_progress_log):
        """Test gathering info for all standard documents."""
        project = {
            "name": "test_project",
            "progress_log": str(sample_progress_log)
        }

        docs_info = await _gather_doc_info(project)

        assert "architecture" in docs_info
        assert "phase_plan" in docs_info
        assert "checklist" in docs_info
        assert "progress" in docs_info

        # Verify architecture info
        assert docs_info["architecture"]["exists"] is True
        assert docs_info["architecture"]["lines"] > 50

    @pytest.mark.asyncio
    async def test_missing_docs_not_included(self, temp_project_dir):
        """Test that missing docs are not included in result."""
        log_path = temp_project_dir / "PROGRESS_LOG.md"
        with open(log_path, 'w') as f:
            f.write("# Progress Log\n\n")

        project = {
            "name": "test_project",
            "progress_log": str(log_path)
        }

        docs_info = await _gather_doc_info(project)

        # Should only have progress (since other docs don't exist)
        assert "progress" in docs_info
        assert "architecture" not in docs_info
        assert "phase_plan" not in docs_info

    @pytest.mark.asyncio
    async def test_progress_entry_count(self, sample_progress_log):
        """Test accurate counting of progress log entries."""
        project = {
            "name": "test_project",
            "progress_log": str(sample_progress_log)
        }

        docs_info = await _gather_doc_info(project)

        assert docs_info["progress"]["exists"] is True
        assert docs_info["progress"]["entries"] == 7




async def verified_reader_context(storage, router, root, session_id, agent, project_name):
    """Build typed test authority only from the current canonical stored binding."""
    binding = await storage.get_session_project(session_id)
    record = await storage.fetch_project(project_name, repo_root=str(root))
    assert binding is not None and record is not None
    assert binding.project_key == record.project_key
    assert binding.canonical_repo_root == str(root)
    context = await router.build_execution_context({
        "repo_root": str(root), "session_id": session_id, "stable_session_id": session_id,
        "transport_session_id": f"reader-test::actor={agent}", "mode": "project",
        "intent": "reader-neighbor-regression",
        "scope_provenance": {"repo_root": "verified", "stable_session_id": "verified"},
        "trust_level": "verified", "session_binding": binding,
    })
    request = build_resolved_request_context(
        caller_session_key=session_id,
        resolved_target=ResolvedProjectTargetV1(
            project_key=record.project_key, project_name=record.name,
            canonical_repo_root=str(root), repository_id=record.repo_id,
            resolution_source="caller_default", default_binding_generation=binding.binding_generation,
        ),
        agent_attribution=AgentAttributionV1(agent=agent, agent_id=agent),
        correlation_id="reader-neighbor-test", operating_mode="project",
        authorization_evidence=AuthorizationEvidenceV1(
            source="server_verified", verified=True, scope_refs=(f"repo:{record.repo_id}",),
        ),
    )
    return replace(context, resolved_request_context=request)


@pytest_asyncio.fixture
async def reader_environment(tmp_path, monkeypatch, test_agent):
    """Real ephemeral canonical storage; each test explicitly installs its request context."""
    root = tmp_path / "repo"
    root.mkdir()
    log = root / "PROGRESS_LOG.md"
    log.write_text("# Progress Log\n")
    storage = SQLiteStorage(tmp_path / "reader.db")
    manager = StateManager(path=tmp_path / "reader.db", storage_backend=storage)
    router = RouterContextManager(storage_backend=storage)
    try:
        await storage.setup()
        manager._backend_ready = True
        record = await storage.upsert_project(
            name="demo", repo_root=str(root), progress_log_path=str(log),
        )
        session_id = "current-reader-session"
        await storage.upsert_session(session_id=session_id, repo_root=str(root), agent_id=test_agent)
        await storage.set_session_project(session_id, "demo")
        await storage.set_agent_project(
            test_agent, "demo", expected_version=None, updated_by=test_agent, session_id=session_id,
        )
        context = await verified_reader_context(storage, router, root, session_id, test_agent, "demo")
        monkeypatch.setattr(server, "storage_backend", storage)
        monkeypatch.setattr(server, "state_manager", manager)
        monkeypatch.setattr(server, "router_context_manager", router)
        monkeypatch.setattr(server, "agent_context_manager", AgentContextManager(storage, manager))
        monkeypatch.setattr(server, "agent_identity", None)
        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", server)
        monkeypatch.setattr("scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module", server)

        async def snapshot():
            return (
                await storage.fetch_project("demo", repo_root=str(root), project_key=record.project_key),
                await storage.get_session_project(session_id),
                await storage.get_agent_project(test_agent),
                await storage.count_entries(record),
                log.read_bytes(),
            )

        yield SimpleNamespace(
            storage=storage, manager=manager, router=router, context=context,
            root=root, record=record, session_id=session_id, agent=test_agent, snapshot=snapshot,
        )
    finally:
        await storage.close()


class TestGetProjectIntegration:
    """Integration tests for get_project with readable format."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_explicit_agent_selection_exposes_cas_version(self, reader_environment):
        """A raw selection exposes CAS metadata without granting project authority."""
        env = reader_environment
        before = await env.snapshot()
        selection = await env.storage.get_agent_project(env.agent)
        result = await get_project(agent=env.agent, format="structured")
        assert result["ok"] is False
        assert "project" not in result
        assert result["selection_version"] == selection["version"]
        assert await env.snapshot() == before

    @pytest.mark.asyncio
    async def test_missing_explicit_agent_selection_keeps_cas_version(
        self, monkeypatch
    ):
        """A cleared project remains repairable through its selection version."""
        state_manager = AsyncMock()
        state_manager.record_tool.return_value = {"tool": "get_project"}
        state_manager.load.return_value = SimpleNamespace(
            recent_projects=[], current_project=None
        )
        fake_server = Mock()
        fake_server.state_manager = state_manager
        fake_server.get_agent_identity.return_value = None
        fake_server.get_execution_context.return_value = None
        fake_server.storage_backend = None
        fake_server.get_agent_context_manager.return_value.get_current_project = AsyncMock(
            return_value={
                "agent_id": "sentinel",
                "project_name": None,
                "version": 9,
            }
        )
        context = LoggingContext(
            tool_name="get_project",
            project=None,
            recent_projects=[],
            state_snapshot={},
            reminders=[],
            agent_id="sentinel",
            resolution_source="agent_project",
        )

        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", fake_server)
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module",
            fake_server,
        )
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._GET_PROJECT_HELPER.prepare_context",
            AsyncMock(return_value=context),
        )
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._GET_PROJECT_HELPER.apply_context_payload",
            lambda payload, _context: payload,
        )

        result = await get_project(agent="sentinel", format="structured")

        assert result["ok"] is False
        assert result["error"] == "No project configured."
        assert result["selection_version"] == 9

    @pytest.mark.asyncio
    async def test_fail_closed_without_recovery_mode(self, monkeypatch):
        """No-arg lookup must fail closed and not invoke hidden active-project fallback."""
        state_manager = AsyncMock()
        state_manager.record_tool.return_value = {"tool": "get_project"}
        state_manager.load.return_value = SimpleNamespace(recent_projects=[], current_project=None)

        fake_server = Mock()
        fake_server.state_manager = state_manager
        fake_server.get_agent_identity.return_value = None
        fake_server.get_execution_context.return_value = None
        fake_server.storage_backend = None

        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", fake_server)
        monkeypatch.setattr("scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module", fake_server)
        monkeypatch.setattr(
            "scribe_mcp.tools.project_utils.load_active_project",
            AsyncMock(side_effect=AssertionError("hidden fallback should not run")),
        )

        result = await get_project(format="structured")

        assert result["ok"] is False
        assert result["error"] == "No project configured."
        assert result["resolution_source"] == "unresolved"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_explicit_recovery_mode_compat_active_project(self, reader_environment, monkeypatch):
        """Compatibility hints cannot promote a stored label without request authority."""
        env = reader_environment
        env.manager._projects_cache = {"demo": {"name": "demo", "root": str(env.root)}}
        env.manager._projects_cache_at = float("inf")
        forbidden = AsyncMock(side_effect=AssertionError("Unverified recovery must not prepare a project"))
        monkeypatch.setattr("scribe_mcp.tools.get_project._GET_PROJECT_HELPER.prepare_context", forbidden)
        before = await env.snapshot()
        result = await get_project(agent=env.agent, recovery_mode="compat_active_project")
        assert result["ok"] is False
        assert "project" not in result
        assert result["resolution_source"] == "unresolved"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []
        assert result["compatibility_recovery"] == {
            "requested": True, "mode": "compat_active_project",
            "applied": False, "reason": "current_authority_unavailable",
        }
        forbidden.assert_not_awaited()
        assert await env.snapshot() == before

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_structured_lookup_resolves_via_session_binding_without_bootstrap_fallback(
        self, reader_environment, monkeypatch
    ):
        """Current typed request and real binding resolve the canonical record."""
        env = reader_environment
        before = await env.snapshot()
        lookup = AsyncMock(wraps=env.storage.get_session_project)
        monkeypatch.setattr(env.storage, "get_session_project", lookup)
        token = env.router.set_current(env.context)
        try:
            result = await get_project(agent=env.agent, format="structured")
        finally:
            env.router.reset(token)
        assert result["ok"] is True
        assert result["project"]["name"] == env.record.name
        assert result["project"]["project_key"] == env.record.project_key
        assert result["project"]["root"] == str(env.root)
        assert result["recent_projects"] == ["demo"]
        assert result["resolution_source"] == "session_binding"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []
        assert "resolved via 'session_binding'" in result["resolution_summary"].lower()
        assert result["state"] == "NEW"
        lookup.assert_any_await(env.session_id)
        assert all(call.args == (env.session_id,) for call in lookup.await_args_list)
        assert await env.snapshot() == before

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_structured_lookup_requires_verified_canonical_session_after_stable_miss(
        self, reader_environment
    ):
        """A stale stable hint cannot grant a fallback; verified canonical recovery succeeds."""
        env = reader_environment
        before = await env.snapshot()
        stale = replace(env.context, stable_session_id="stable-session-missing")
        token = env.router.set_current(stale)
        try:
            refused = await get_project(agent=env.agent, format="structured")
        finally:
            env.router.reset(token)
        assert refused["ok"] is False
        assert "project" not in refused
        assert refused["resolution_source"] == "unresolved"
        assert refused["fallback_chain"] == []
        assert await env.snapshot() == before

        # The runtime-owned recovery must establish the current canonical key.
        # Supplying the fixture's existing verified context does not mutate a binding.
        token = env.router.set_current(env.context)
        try:
            result = await get_project(agent=env.agent, format="structured")
        finally:
            env.router.reset(token)
        assert result["ok"] is True
        assert result["project"]["project_key"] == env.record.project_key
        assert result["project"]["root"] == str(env.root)
        assert result["resolution_source"] == "session_binding"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []
        assert result["state"] == "NEW"
        assert await env.snapshot() == before

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_structured_lookup_recovery_mode_does_not_mark_fallback_when_session_binding_resolves(
        self, reader_environment
    ):
        """Verified binding resolution keeps compatibility metadata truthful."""
        env = reader_environment
        before = await env.snapshot()
        token = env.router.set_current(env.context)
        try:
            result = await get_project(agent=env.agent, recovery_mode="compat_active_project")
        finally:
            env.router.reset(token)
        assert result["ok"] is True
        assert result["project"]["project_key"] == env.record.project_key
        assert result["project"]["root"] == str(env.root)
        assert result["resolution_source"] == "session_binding"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []
        assert result["compatibility_recovery"] == {
            "requested": True, "mode": "compat_active_project",
            "applied": False, "reason": "session_authority_present",
        }
        assert await env.snapshot() == before

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_readable_lookup_includes_resolution_metadata_and_recovery_chain(
        self, reader_environment, monkeypatch
    ):
        """Readable compatibility requests also refuse unverified enrichment."""
        env = reader_environment
        reads = AsyncMock(side_effect=AssertionError("Unverified reads must not enrich a project"))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_progress_entries", reads)
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_entries_from_db", reads)
        before = await env.snapshot()
        result = await get_project(agent=env.agent, format="readable", recovery_mode="compat_active_project")
        assert result["ok"] is False
        assert "project" not in result
        assert "recent_entries" not in result
        assert result["resolution_source"] == "unresolved"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []
        assert result["compatibility_recovery"]["requested"] is True
        assert result["compatibility_recovery"]["applied"] is False
        assert result["compatibility_recovery"]["reason"] == "current_authority_unavailable"
        reads.assert_not_awaited()
        assert await env.snapshot() == before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
