#!/usr/bin/env python3
"""
Comprehensive test suite for list_projects SITREP enhancement (Phase 4.3).

Tests state detection integration, pagination, summary statistics,
and removal of hardcoded modified:False bug.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pathlib import Path

from scribe_mcp.tools.list_projects import (
    list_projects,
    _gather_doc_info,
    _compute_summary_stats,
    STATE_ICONS,
)


class TestHardcodedModifiedBugFixed:
    """Test 1: Verify hardcoded modified:False bug is fixed."""

    @pytest.mark.asyncio
    async def test_gather_doc_info_uses_actual_flags(self):
        """Verify _gather_doc_info uses real modification flags from project meta."""
        # Create project with modification flags
        project = {
            "name": "test_project",
            "progress_log": "/tmp/test_project/PROGRESS_LOG.md",
            "meta": {
                "docs": {
                    "flags": {
                        "architecture_modified": True,
                        "phase_plan_modified": False,
                        "checklist_modified": True,
                    }
                }
            }
        }

        # Create mock files
        test_dir = Path("/tmp/test_project")
        test_dir.mkdir(parents=True, exist_ok=True)

        arch_file = test_dir / "ARCHITECTURE_GUIDE.md"
        phase_file = test_dir / "PHASE_PLAN.md"
        checklist_file = test_dir / "CHECKLIST.md"
        progress_file = test_dir / "PROGRESS_LOG.md"

        arch_file.write_text("# Architecture\n" * 100)
        phase_file.write_text("# Phase Plan\n" * 50)
        checklist_file.write_text("# Checklist\n" * 30)
        progress_file.write_text("[✅] Entry 1\n[ℹ️] Entry 2\n")

        try:
            result = await _gather_doc_info(project)

            # Verify modification flags are used (NOT hardcoded False)
            assert result["architecture"]["modified"] is True, "Architecture should show as modified"
            assert result["phase_plan"]["modified"] is False, "Phase plan should show as unmodified"
            assert result["checklist"]["modified"] is True, "Checklist should show as modified"

            # Verify we're not just returning hardcoded False
            assert result["architecture"]["modified"] != result["phase_plan"]["modified"], \
                "Different modification states should be detected"

        finally:
            # Cleanup
            arch_file.unlink(missing_ok=True)
            phase_file.unlink(missing_ok=True)
            checklist_file.unlink(missing_ok=True)
            progress_file.unlink(missing_ok=True)
            test_dir.rmdir()


class TestStateDetectionIntegration:
    """Test 2-3: Verify detect_project_state is integrated for all projects."""

    @pytest.mark.asyncio
    async def test_state_detection_integrated(self):
        """Verify detect_project_state is called for each project."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server, \
             patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load, \
             patch('scribe_mcp.tools.list_projects._PROJECT_REGISTRY') as mock_registry, \
             patch('scribe_mcp.tools.list_projects.detect_project_state') as mock_detect:

            # Setup mocks
            mock_backend = AsyncMock()
            mock_backend.list_projects.return_value = []
            mock_backend.count_entries.return_value = 5
            mock_server.storage_backend = mock_backend

            mock_state_manager = AsyncMock()
            mock_state_manager.record_tool.return_value = {}
            mock_state_manager.load.return_value = MagicMock(projects={
                "project1": {"root": "/path1", "progress_log": "/path1/PROGRESS_LOG.md"},
                "project2": {"root": "/path2", "progress_log": "/path2/PROGRESS_LOG.md"},
            })
            mock_server.state_manager = mock_state_manager
            mock_server.get_agent_identity.return_value = None

            mock_load.return_value = (None, None, [])
            mock_registry.get_project.side_effect = Exception("Not found")

            # Mock detect_project_state to return different states
            mock_detect.side_effect = [
                ("NEW", "🆕 New project initialized"),
                ("MODIFIED", "✏️ Modified: architecture (5 entries)"),
            ]

            # Execute
            result = await list_projects(format="structured", include_test=True)

            # Verify detect_project_state was called for each project
            assert mock_detect.call_count == 2, "Should call detect_project_state for each project"
            assert result["ok"] is True

            # Verify state information is in projects
            projects = result["projects"]
            assert len(projects) == 2
            assert all("state" in p for p in projects), "All projects should have state field"

    @pytest.mark.asyncio
    async def test_all_four_states_displayed(self):
        """Verify all four states (NEW/EXISTING_LEGACY/UNCHANGED/MODIFIED) can be shown."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server, \
             patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load, \
             patch('scribe_mcp.tools.list_projects._PROJECT_REGISTRY') as mock_registry, \
             patch('scribe_mcp.tools.list_projects.detect_project_state') as mock_detect:

            # Setup mocks
            mock_backend = AsyncMock()
            mock_backend.list_projects.return_value = []
            mock_backend.count_entries.return_value = 10
            mock_server.storage_backend = mock_backend

            mock_state_manager = AsyncMock()
            mock_state_manager.record_tool.return_value = {}
            mock_state_manager.load.return_value = MagicMock(projects={
                "new_proj": {"root": "/new", "progress_log": "/new/PROGRESS_LOG.md"},
                "legacy_proj": {"root": "/legacy", "progress_log": "/legacy/PROGRESS_LOG.md"},
                "unchanged_proj": {"root": "/unchanged", "progress_log": "/unchanged/PROGRESS_LOG.md"},
                "modified_proj": {"root": "/modified", "progress_log": "/modified/PROGRESS_LOG.md"},
            })
            mock_server.state_manager = mock_state_manager
            mock_server.get_agent_identity.return_value = None

            mock_load.return_value = (None, None, [])
            mock_registry.get_project.side_effect = Exception("Not found")

            # Mock all four states
            mock_detect.side_effect = [
                ("NEW", "🆕 New project initialized"),
                ("EXISTING_LEGACY", "📋 Existing project (10 entries, pre-hash-tracking)"),
                ("UNCHANGED", "📋 Project unchanged (10 entries, docs match baseline)"),
                ("MODIFIED", "✏️ Modified: architecture (10 entries)"),
            ]

            # Execute
            result = await list_projects(format="structured", include_test=True)

            # Verify all four states are present
            projects = result["projects"]
            states = {p["state"] for p in projects}
            assert states == {"NEW", "EXISTING_LEGACY", "UNCHANGED", "MODIFIED"}, \
                "All four states should be represented"


class TestPaginationIntegration:
    """Test 4: Verify pagination works for JSON format."""

    @pytest.mark.asyncio
    async def test_pagination_prevents_token_explosion(self):
        """Verify pagination limits projects returned even with 50+ total."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server, \
             patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load, \
             patch('scribe_mcp.tools.list_projects._PROJECT_REGISTRY') as mock_registry, \
             patch('scribe_mcp.tools.list_projects.detect_project_state') as mock_detect:

            # Setup mocks
            mock_backend = AsyncMock()
            mock_backend.list_projects.return_value = []
            mock_backend.count_entries.return_value = 5
            mock_server.storage_backend = mock_backend

            mock_state_manager = AsyncMock()
            mock_state_manager.record_tool.return_value = {}

            # Create 60 projects
            projects_dict = {
                f"project_{i}": {
                    "root": f"/path{i}",
                    "progress_log": f"/path{i}/PROGRESS_LOG.md"
                }
                for i in range(60)
            }
            mock_state_manager.load.return_value = MagicMock(projects=projects_dict)
            mock_server.state_manager = mock_state_manager
            mock_server.get_agent_identity.return_value = None

            mock_load.return_value = (None, None, [])
            mock_registry.get_project.side_effect = Exception("Not found")

            # Mock detect_project_state for all projects
            mock_detect.return_value = ("UNCHANGED", "✓ Unchanged")

            # Execute with page_size=10
            result = await list_projects(
                format="structured",
                include_test=True,
                page=1,
                page_size=10
            )

            # Verify pagination worked
            assert result["ok"] is True
            assert len(result["projects"]) == 10, "Should only return 10 projects per page"
            assert result["pagination"]["total_count"] == 60, "Should show total of 60 projects"
            assert result["pagination"]["page_size"] == 10
            assert result["pagination"]["has_next"] is True, "Should have next page"


class TestReadableFormatCompact:
    """Test 5: Verify readable format stays compact (~150-200 tokens per project)."""

    @pytest.mark.asyncio
    async def test_readable_format_compact_output(self):
        """Verify readable format produces compact output per project."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server, \
             patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load, \
             patch('scribe_mcp.tools.list_projects._PROJECT_REGISTRY') as mock_registry, \
             patch('scribe_mcp.tools.list_projects.detect_project_state') as mock_detect, \
             patch('scribe_mcp.utils.response.default_formatter') as mock_formatter:

            # Setup mocks
            mock_backend = AsyncMock()
            mock_backend.list_projects.return_value = []
            mock_backend.count_entries.return_value = 15
            mock_server.storage_backend = mock_backend

            mock_state_manager = AsyncMock()
            mock_state_manager.record_tool.return_value = {}
            mock_state_manager.load.return_value = MagicMock(projects={
                "proj1": {"root": "/p1", "progress_log": "/p1/PROGRESS_LOG.md"},
                "proj2": {"root": "/p2", "progress_log": "/p2/PROGRESS_LOG.md"},
            })
            mock_server.state_manager = mock_state_manager
            mock_server.get_agent_identity.return_value = None

            mock_load.return_value = (None, "proj1", [])
            mock_registry.get_project.side_effect = Exception("Not found")
            mock_detect.return_value = ("MODIFIED", "✏️ Modified: architecture (15 entries)")

            # Mock formatter to return compact table
            mock_formatter.format_projects_table.return_value = "Compact table view"
            mock_formatter.finalize_tool_response = AsyncMock(
                return_value={"ok": True, "readable_content": "Compact table view"}
            )

            # Execute
            result = await list_projects(format="readable", include_test=True)

            # Verify formatter was called (which handles compact output)
            assert mock_formatter.format_projects_table.called, \
                "Should call formatter for compact table view"
            assert result["ok"] is True


class TestJSONFormatFullMetadata:
    """Test 6: Verify JSON format includes full metadata."""

    @pytest.mark.asyncio
    async def test_json_format_includes_full_sitrep(self):
        """Verify JSON format includes state, sitrep_message, entry_count, and summary."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server, \
             patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load, \
             patch('scribe_mcp.tools.list_projects._PROJECT_REGISTRY') as mock_registry, \
             patch('scribe_mcp.tools.list_projects.detect_project_state') as mock_detect:

            # Setup mocks — provide a backend record matching the state project
            # so backend_records lookup succeeds and count_entries is called.
            mock_record = MagicMock()
            mock_record.name = "project1"
            mock_record.repo_root = "/p1"
            mock_record.progress_log_path = "/p1/PROGRESS_LOG.md"

            mock_backend = AsyncMock()
            mock_backend.list_projects.return_value = [mock_record]
            # Production prefers list_projects_by_repo when present (a bare AsyncMock
            # always "has" it); configure both branches or backend_records stays empty
            # and entry_count never picks up the count_entries value.
            mock_backend.list_projects_by_repo = AsyncMock(return_value=[mock_record])
            mock_backend.count_entries.return_value = 25
            mock_server.storage_backend = mock_backend

            mock_state_manager = AsyncMock()
            mock_state_manager.record_tool.return_value = {}
            mock_state_manager.load.return_value = MagicMock(projects={
                "project1": {"root": "/p1", "progress_log": "/p1/PROGRESS_LOG.md"},
            })
            mock_server.state_manager = mock_state_manager
            mock_server.get_agent_identity.return_value = None

            mock_load.return_value = (None, None, [])
            mock_registry.get_project.side_effect = Exception("Not found")
            mock_detect.return_value = ("MODIFIED", "✏️ Modified: architecture, phase_plan (25 entries)")

            # Execute
            result = await list_projects(format="structured", include_test=True)

            # Verify full SITREP metadata in response
            assert result["ok"] is True
            project = result["projects"][0]

            assert "state" in project, "Should include state field"
            assert "sitrep_message" in project, "Should include sitrep_message field"
            assert "entry_count" in project, "Should include entry_count field"
            assert project["state"] == "MODIFIED"
            assert project["entry_count"] == 25

            # Verify summary statistics
            assert "summary" in result, "Should include summary field"
            assert "total_projects" in result["summary"]
            assert "MODIFIED" in result["summary"]


class TestSummaryStatistics:
    """Test 7: Verify summary statistics computation."""

    def test_compute_summary_stats(self):
        """Verify _compute_summary_stats calculates correct state breakdown."""
        projects = [
            {"name": "p1", "state": "NEW"},
            {"name": "p2", "state": "NEW"},
            {"name": "p3", "state": "EXISTING_LEGACY"},
            {"name": "p4", "state": "UNCHANGED"},
            {"name": "p5", "state": "UNCHANGED"},
            {"name": "p6", "state": "UNCHANGED"},
            {"name": "p7", "state": "MODIFIED"},
            {"name": "p8", "state": "MODIFIED"},
        ]

        stats = _compute_summary_stats(projects)

        assert stats["total_projects"] == 8
        assert stats["NEW"] == 2
        assert stats["EXISTING_LEGACY"] == 1
        assert stats["UNCHANGED"] == 3
        assert stats["MODIFIED"] == 2


class TestStateIconsDisplay:
    """Test 8: Verify state icons are defined correctly."""

    def test_state_icons_mapping(self):
        """Verify STATE_ICONS dictionary has correct emoji mappings."""
        assert STATE_ICONS["NEW"] == "🆕"
        assert STATE_ICONS["EXISTING_LEGACY"] == "📋"
        assert STATE_ICONS["UNCHANGED"] == "✓"
        assert STATE_ICONS["MODIFIED"] == "✏️"
        assert len(STATE_ICONS) == 4, "Should have exactly 4 state icons"


class TestLargeProjectCount:
    """Test 9: Verify large project counts (50+) work with pagination."""

    @pytest.mark.asyncio
    async def test_large_project_count_pagination(self):
        """Verify 50+ projects handled efficiently with pagination."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server, \
             patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load, \
             patch('scribe_mcp.tools.list_projects._PROJECT_REGISTRY') as mock_registry, \
             patch('scribe_mcp.tools.list_projects.detect_project_state') as mock_detect:

            # Setup mocks
            mock_backend = AsyncMock()
            mock_backend.list_projects.return_value = []
            mock_backend.count_entries.return_value = 10
            mock_server.storage_backend = mock_backend

            mock_state_manager = AsyncMock()
            mock_state_manager.record_tool.return_value = {}

            # Create 100 projects
            projects_dict = {
                f"project_{i:03d}": {
                    "root": f"/path{i}",
                    "progress_log": f"/path{i}/PROGRESS_LOG.md"
                }
                for i in range(100)
            }
            mock_state_manager.load.return_value = MagicMock(projects=projects_dict)
            mock_server.state_manager = mock_state_manager
            mock_server.get_agent_identity.return_value = None

            mock_load.return_value = (None, None, [])
            mock_registry.get_project.side_effect = Exception("Not found")
            mock_detect.return_value = ("UNCHANGED", "✓ Unchanged")

            # Execute with default page_size (should limit results)
            result = await list_projects(format="structured", include_test=True, page_size=5)

            # Verify pagination prevents explosion
            assert result["ok"] is True
            assert len(result["projects"]) == 5, "Should limit to page_size"
            assert result["pagination"]["total_count"] == 100
            assert result["summary"]["total_projects"] == 5, "Summary reflects current page"
            # Note: Summary is for items in current page, pagination shows total


class TestInfrastructureReuse:
    """Test 10: Verify existing infrastructure is reused correctly."""

    @pytest.mark.asyncio
    async def test_reuses_backend_count_entries(self):
        """Verify backend.count_entries is called for entry counting."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server, \
             patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load, \
             patch('scribe_mcp.tools.list_projects._PROJECT_REGISTRY') as mock_registry, \
             patch('scribe_mcp.tools.list_projects.detect_project_state') as mock_detect:

            # Setup mocks — provide a backend record matching the state project so the
            # backend_records dict is populated and count_entries is actually called.
            # Production builds record_key = (name, _normalise_project_root(root)).
            mock_record = MagicMock()
            mock_record.name = "test_proj"
            mock_record.repo_root = "/test"
            mock_record.progress_log_path = "/test/PROGRESS_LOG.md"

            mock_backend = AsyncMock()
            mock_backend.list_projects.return_value = [mock_record]
            # Production prefers the repo-scoped query when the backend exposes
            # list_projects_by_repo (a bare AsyncMock always "has" it), so configure
            # both branches to return the record — otherwise backend_records is empty
            # and count_entries is never reached.
            mock_backend.list_projects_by_repo = AsyncMock(return_value=[mock_record])
            mock_backend.count_entries = AsyncMock(return_value=42)
            mock_server.storage_backend = mock_backend

            mock_state_manager = AsyncMock()
            mock_state_manager.record_tool.return_value = {}
            mock_state_manager.load.return_value = MagicMock(projects={
                "test_proj": {"root": "/test", "progress_log": "/test/PROGRESS_LOG.md"},
            })
            mock_server.state_manager = mock_state_manager
            mock_server.get_agent_identity.return_value = None

            mock_load.return_value = (None, None, [])
            mock_registry.get_project.side_effect = Exception("Not found")
            mock_detect.return_value = ("UNCHANGED", "✓ Unchanged")

            # Execute
            await list_projects(format="structured", include_test=True)

            # Verify backend.count_entries was called with the project record (not the name string).
            # Production passes the full record object to count_entries.
            mock_backend.count_entries.assert_called_once_with(mock_record)

    def test_reuses_detect_project_state_function(self):
        """Verify detect_project_state is imported from Phase 4.1."""
        from scribe_mcp.tools.list_projects import detect_project_state
        from scribe_mcp.shared.project_utils import detect_project_state as phase41_func

        # Verify it's the same function from Phase 4.1
        assert detect_project_state is phase41_func, \
            "Should import detect_project_state from shared.project_utils (Phase 4.1)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
