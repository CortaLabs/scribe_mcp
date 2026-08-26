#!/usr/bin/env python3
"""Integration tests for get_project context hydration."""

from pathlib import Path

import pytest
import tempfile
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from scribe_mcp.tools.get_project import _read_recent_progress_entries, _gather_doc_info, get_project
from scribe_mcp.shared.logging_utils import LoggingContext


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


class TestGetProjectIntegration:
    """Integration tests for get_project with readable format."""

    @pytest.mark.asyncio
    async def test_explicit_agent_selection_exposes_cas_version(
        self, monkeypatch, tmp_path
    ):
        """The requested agent row, including its CAS version, is public truth."""
        state_manager = AsyncMock()
        state_manager.record_tool.return_value = {"tool": "get_project"}
        state_manager.load.return_value = SimpleNamespace(
            recent_projects=["heartbeat"], current_project="heartbeat"
        )
        fake_server = Mock()
        fake_server.state_manager = state_manager
        fake_server.get_agent_identity.return_value = None
        fake_server.get_execution_context.return_value = None
        fake_server.storage_backend = None
        fake_server.get_agent_context_manager.return_value.get_current_project = AsyncMock(
            return_value={
                "agent_id": "sentinel",
                "project_name": "heartbeat",
                "version": 7,
            }
        )
        context = LoggingContext(
            tool_name="get_project",
            project={
                "name": "heartbeat",
                "root": str(tmp_path),
                "progress_log": "",
                "version": 7,
            },
            recent_projects=["heartbeat"],
            state_snapshot={},
            reminders=[],
            agent_id="sentinel",
            resolution_source="agent_project",
        )
        prepare = AsyncMock(return_value=context)

        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", fake_server)
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module",
            fake_server,
        )
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._GET_PROJECT_HELPER.prepare_context",
            prepare,
        )
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._GET_PROJECT_HELPER.apply_context_payload",
            lambda payload, _context: payload,
        )
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._compute_doc_status",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._compute_log_counts",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project._read_recent_entries_from_db",
            AsyncMock(return_value=[]),
        )
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project.detect_project_state",
            lambda *_args, **_kwargs: ("ACTIVE", "ok"),
        )

        result = await get_project(agent="sentinel", format="structured")

        assert result["project"]["version"] == 7
        assert result["selection_version"] == 7
        assert prepare.await_args.kwargs["agent_id"] == "sentinel"

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
            "scribe_mcp.tools.get_project.load_active_project",
            AsyncMock(side_effect=AssertionError("hidden fallback should not run")),
        )

        result = await get_project(format="structured")

        assert result["ok"] is False
        assert result["error"] == "No project configured."
        assert result["resolution_source"] == "unresolved"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []

    @pytest.mark.asyncio
    async def test_explicit_recovery_mode_compat_active_project(self, monkeypatch):
        """Compatibility recovery mode should opt into active-project fallback explicitly."""
        state_manager = AsyncMock()
        state_manager.record_tool.return_value = {"tool": "get_project"}
        state_manager.load.return_value = SimpleNamespace(recent_projects=["demo"], current_project=None)

        fake_server = Mock()
        fake_server.state_manager = state_manager
        fake_server.get_agent_identity.return_value = None
        fake_server.get_execution_context.return_value = None
        fake_server.storage_backend = None

        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", fake_server)
        monkeypatch.setattr("scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module", fake_server)
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project.load_active_project",
            AsyncMock(
                return_value=(
                    {"name": "demo", "root": "/tmp/demo", "progress_log": "/tmp/demo/PROGRESS_LOG.md", "docs": {}},
                    "demo",
                    ["demo"],
                )
            ),
        )
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_doc_status", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_log_counts", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_progress_entries", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_entries_from_db", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project.detect_project_state", lambda *_args, **_kwargs: ("NEW", "ok"))

        result = await get_project(format="structured", recovery_mode="compat_active_project")

        assert result["ok"] is True
        assert result["project"]["name"] == "demo"
        assert result["resolution_source"] == "unresolved"
        assert result["fallback_used"] is True
        assert "compat_active_project" in result["fallback_chain"]
        assert "recovery chain" in result["resolution_summary"].lower()

    @pytest.mark.asyncio
    async def test_structured_lookup_resolves_via_session_binding_without_bootstrap_fallback(self, monkeypatch):
        """Ordinary structured lookup should resolve through session binding, not bootstrap app.state."""
        state_manager = AsyncMock()
        state_manager.record_tool.return_value = {"tool": "get_project"}
        state_manager.load.return_value = SimpleNamespace(recent_projects=["demo"], current_project="demo")

        storage_backend = Mock()
        storage_backend.get_session_project = AsyncMock(return_value="demo")
        storage_backend.fetch_project = AsyncMock(
            return_value=SimpleNamespace(
                name="demo",
                repo_root="/tmp/demo",
                progress_log_path="/tmp/demo/PROGRESS_LOG.md",
                docs_json=None,
            )
        )
        storage_backend.count_entries = AsyncMock(return_value=0)

        fake_server = Mock()
        fake_server.state_manager = state_manager
        fake_server.get_agent_identity.return_value = None
        fake_server.get_execution_context.return_value = SimpleNamespace(
            mode="project",
            stable_session_id="stable-session-001",
            session_id="transport-session-001",
        )
        fake_server.storage_backend = storage_backend
        fake_server.app = SimpleNamespace(state=SimpleNamespace(execution_context={"forbidden": True}))

        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", fake_server)
        monkeypatch.setattr("scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module", fake_server)
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project.load_active_project",
            AsyncMock(side_effect=AssertionError("compat fallback must not run in ordinary mode")),
        )
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_doc_status", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_log_counts", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_progress_entries", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_entries_from_db", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project.detect_project_state", lambda *_args, **_kwargs: ("NEW", "ok"))

        result = await get_project(format="structured")

        assert result["ok"] is True
        assert result["project"]["name"] == "demo"
        assert result["recent_projects"] == ["demo"]
        assert result["resolution_source"] == "session_binding"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []
        assert "resolved via 'session_binding'" in result["resolution_summary"].lower()
        assert result["state"] == "NEW"
        storage_backend.get_session_project.assert_awaited_once_with("stable-session-001")

    @pytest.mark.asyncio
    async def test_structured_lookup_falls_back_to_transport_session_binding_when_stable_misses(self, monkeypatch):
        """Project lookup should retry with transport-backed session id when stable session binding is empty."""
        state_manager = AsyncMock()
        state_manager.record_tool.return_value = {"tool": "get_project"}
        state_manager.load.return_value = SimpleNamespace(recent_projects=["demo"], current_project="demo")

        storage_backend = Mock()
        storage_backend.get_session_project = AsyncMock(side_effect=[None, "demo"])
        storage_backend.fetch_project = AsyncMock(
            return_value=SimpleNamespace(
                name="demo",
                repo_root="/tmp/demo",
                progress_log_path="/tmp/demo/PROGRESS_LOG.md",
                docs_json=None,
            )
        )
        storage_backend.count_entries = AsyncMock(return_value=0)

        fake_server = Mock()
        fake_server.state_manager = state_manager
        fake_server.get_agent_identity.return_value = None
        fake_server.get_execution_context.return_value = SimpleNamespace(
            mode="project",
            stable_session_id="stable-session-missing",
            session_id="transport-session-bound",
        )
        fake_server.storage_backend = storage_backend
        fake_server.app = SimpleNamespace(state=SimpleNamespace(execution_context={"forbidden": True}))

        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", fake_server)
        monkeypatch.setattr("scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module", fake_server)
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project.load_active_project",
            AsyncMock(side_effect=AssertionError("compat fallback must not run in ordinary mode")),
        )
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_doc_status", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_log_counts", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_progress_entries", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_entries_from_db", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project.detect_project_state", lambda *_args, **_kwargs: ("NEW", "ok"))

        result = await get_project(format="structured")

        assert result["ok"] is True
        assert result["project"]["name"] == "demo"
        assert result["resolution_source"] == "session_binding"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []
        assert "resolved via 'session_binding'" in result["resolution_summary"].lower()
        assert result["state"] == "NEW"
        assert storage_backend.get_session_project.await_count == 2
        storage_backend.get_session_project.assert_any_await("stable-session-missing")
        storage_backend.get_session_project.assert_any_await("transport-session-bound")

    @pytest.mark.asyncio
    async def test_structured_lookup_recovery_mode_does_not_mark_fallback_when_session_binding_resolves(self, monkeypatch):
        """Compatibility mode metadata should stay truthful when session binding already resolved the project."""
        state_manager = AsyncMock()
        state_manager.record_tool.return_value = {"tool": "get_project"}
        state_manager.load.return_value = SimpleNamespace(recent_projects=["demo"], current_project="demo")

        storage_backend = Mock()
        storage_backend.get_session_project = AsyncMock(return_value="demo")
        storage_backend.fetch_project = AsyncMock(
            return_value=SimpleNamespace(
                name="demo",
                repo_root="/tmp/demo",
                progress_log_path="/tmp/demo/PROGRESS_LOG.md",
                docs_json=None,
            )
        )
        storage_backend.count_entries = AsyncMock(return_value=0)

        fake_server = Mock()
        fake_server.state_manager = state_manager
        fake_server.get_agent_identity.return_value = None
        fake_server.get_execution_context.return_value = SimpleNamespace(
            mode="project",
            stable_session_id="stable-session-001",
            session_id="transport-session-001",
        )
        fake_server.storage_backend = storage_backend
        fake_server.app = SimpleNamespace(state=SimpleNamespace(execution_context={"forbidden": True}))

        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", fake_server)
        monkeypatch.setattr("scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module", fake_server)
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project.load_active_project",
            AsyncMock(side_effect=AssertionError("compat fallback must not run when session binding resolves")),
        )
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_doc_status", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_log_counts", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_progress_entries", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_entries_from_db", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project.detect_project_state", lambda *_args, **_kwargs: ("NEW", "ok"))

        result = await get_project(format="structured", recovery_mode="compat_active_project")

        assert result["ok"] is True
        assert result["project"]["name"] == "demo"
        assert result["resolution_source"] == "session_binding"
        assert result["fallback_used"] is False
        assert result["fallback_chain"] == []
        assert result["compatibility_recovery"]["requested"] is True
        assert result["compatibility_recovery"]["applied"] is False
        assert result["compatibility_recovery"]["reason"] == "session_authority_present"

    @pytest.mark.asyncio
    async def test_readable_lookup_includes_resolution_metadata_and_recovery_chain(self, monkeypatch):
        """Readable lookup in explicit recovery mode should expose resolution metadata truthfully."""
        state_manager = AsyncMock()
        state_manager.record_tool.return_value = {"tool": "get_project"}
        state_manager.load.return_value = SimpleNamespace(recent_projects=["demo"], current_project=None)

        fake_server = Mock()
        fake_server.state_manager = state_manager
        fake_server.get_agent_identity.return_value = None
        fake_server.get_execution_context.return_value = None
        fake_server.storage_backend = None

        monkeypatch.setattr("scribe_mcp.tools.get_project.server_module", fake_server)
        monkeypatch.setattr("scribe_mcp.tools.get_project._GET_PROJECT_HELPER.server_module", fake_server)
        monkeypatch.setattr(
            "scribe_mcp.tools.get_project.load_active_project",
            AsyncMock(
                return_value=(
                    {"name": "demo", "root": "/tmp/demo", "progress_log": "/tmp/demo/PROGRESS_LOG.md", "docs": {}},
                    "demo",
                    ["demo"],
                )
            ),
        )
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_doc_status", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._compute_log_counts", AsyncMock(return_value={}))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_progress_entries", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project._read_recent_entries_from_db", AsyncMock(return_value=[]))
        monkeypatch.setattr("scribe_mcp.tools.get_project._format_readable_sitrep", AsyncMock(return_value="SITREP"))
        monkeypatch.setattr("scribe_mcp.tools.get_project.detect_project_state", lambda *_args, **_kwargs: ("NEW", "ok"))
        monkeypatch.setattr(
            "scribe_mcp.utils.response.default_formatter.finalize_tool_response",
            AsyncMock(side_effect=lambda payload, **_kwargs: payload),
        )

        result = await get_project(format="readable", recovery_mode="compat_active_project")

        assert result["ok"] is True
        assert result["project"]["name"] == "demo"
        assert result["resolution_source"] == "unresolved"
        assert result["fallback_used"] is True
        assert "compat_active_project" in result["fallback_chain"]
        assert "recovery chain" in result["resolution_summary"].lower()
        assert result["readable_content"] == "SITREP"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
