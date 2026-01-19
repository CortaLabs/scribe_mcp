#!/usr/bin/env python3
"""Integration tests for list_projects.py with readable formatters."""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from scribe_mcp.tools.list_projects import list_projects, _gather_doc_info


class TestGatherDocInfo:
    """Test the _gather_doc_info helper function."""

    @pytest.mark.asyncio
    async def test_gather_doc_info_all_docs_present(self, tmp_path):
        """Test gathering info when all standard docs are present."""
        # Create a project directory structure
        dev_plan_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "test_project"
        dev_plan_dir.mkdir(parents=True, exist_ok=True)

        # Create standard documents
        arch_file = dev_plan_dir / "ARCHITECTURE_GUIDE.md"
        arch_file.write_text("# Architecture\n" + "Line\n" * 100)

        phase_file = dev_plan_dir / "PHASE_PLAN.md"
        phase_file.write_text("# Phase Plan\n" + "Line\n" * 50)

        checklist_file = dev_plan_dir / "CHECKLIST.md"
        checklist_file.write_text("# Checklist\n" + "Line\n" * 30)

        progress_file = dev_plan_dir / "PROGRESS_LOG.md"
        progress_file.write_text(
            "[✅] Entry 1\n[ℹ️] Entry 2\n[⚠️] Entry 3\nNot an entry\n"
        )

        # Create project dict
        project = {
            "name": "test_project",
            "root": str(tmp_path),
            "progress_log": str(progress_file)
        }

        # Gather info
        result = await _gather_doc_info(project)

        # Verify
        assert "architecture" in result
        assert result["architecture"]["exists"] is True
        assert result["architecture"]["lines"] > 0

        assert "phase_plan" in result
        assert result["phase_plan"]["exists"] is True

        assert "checklist" in result
        assert result["checklist"]["exists"] is True

        assert "progress" in result
        assert result["progress"]["exists"] is True
        assert result["progress"]["entries"] == 3  # 3 lines starting with '['

    @pytest.mark.asyncio
    async def test_gather_doc_info_missing_docs(self, tmp_path):
        """Test gathering info when some docs are missing."""
        dev_plan_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "minimal_project"
        dev_plan_dir.mkdir(parents=True, exist_ok=True)

        # Only create progress log
        progress_file = dev_plan_dir / "PROGRESS_LOG.md"
        progress_file.write_text("[✅] Only entry\n")

        project = {
            "name": "minimal_project",
            "root": str(tmp_path),
            "progress_log": str(progress_file)
        }

        result = await _gather_doc_info(project)

        # Only progress should be present
        assert "progress" in result
        assert result["progress"]["exists"] is True
        assert "architecture" not in result
        assert "phase_plan" not in result
        assert "checklist" not in result

    @pytest.mark.asyncio
    async def test_gather_doc_info_invalid_path(self):
        """Test gathering info with invalid progress log path."""
        project = {
            "name": "nonexistent",
            "root": "/nonexistent/path",
            "progress_log": "/nonexistent/path/PROGRESS_LOG.md"
        }

        result = await _gather_doc_info(project)

        # Should return empty dict
        assert result == {}

    @pytest.mark.asyncio
    async def test_gather_doc_info_custom_content(self, tmp_path):
        """Test detection of custom content (research, bugs, jsonl)."""
        dev_plan_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "custom_project"
        dev_plan_dir.mkdir(parents=True, exist_ok=True)

        # Create progress log
        progress_file = dev_plan_dir / "PROGRESS_LOG.md"
        progress_file.write_text("[✅] Entry\n")

        # Create research directory with files
        research_dir = dev_plan_dir / "research"
        research_dir.mkdir(exist_ok=True)
        (research_dir / "RESEARCH_TOPIC_20260103.md").write_text("# Research\n")

        # Create a JSONL file
        (dev_plan_dir / "TOOL_LOG.jsonl").write_text('{"test": "data"}\n')

        project = {
            "name": "custom_project",
            "root": str(tmp_path),
            "progress_log": str(progress_file)
        }

        result = await _gather_doc_info(project)

        # Verify custom content detection
        assert "custom" in result
        assert result["custom"]["research_files"] > 0
        assert "TOOL_LOG.jsonl" in result["custom"].get("jsonl_files", [])


class TestListProjectsIntegration:
    """Integration tests for list_projects with 3-way routing."""

    @pytest.fixture
    def mock_state_manager(self):
        """Mock state manager."""
        manager = AsyncMock()
        manager.record_tool.return_value = {"test": "snapshot"}
        manager.load.return_value = Mock(projects={})
        return manager

    @pytest.fixture
    def mock_storage_backend(self):
        """Mock storage backend."""
        backend = AsyncMock()
        backend.list_projects.return_value = []
        return backend

    @pytest.mark.asyncio
    async def test_readable_format_zero_matches(self, mock_state_manager, mock_storage_backend):
        """Test readable format with 0 matches returns empty state."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server:
            mock_server.state_manager = mock_state_manager
            mock_server.storage_backend = mock_storage_backend
            mock_server.get_agent_identity.return_value = None

            with patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load:
                mock_load.return_value = (None, None, [])

                # Call with filter that matches nothing
                result = await list_projects(
                    filter="nonexistent_project_xyz",
                    format="readable"
                )

                # Verify response structure
                assert result["ok"] is True
                assert result["count"] == 0
                assert result["projects"] == []
                assert "readable_content" in result
                # Verify it contains helpful empty state message
                assert "No projects found" in result["readable_content"] or \
                       "no matches" in result["readable_content"].lower()

    @pytest.mark.asyncio
    async def test_readable_format_single_match(self, mock_state_manager, tmp_path):
        """Test readable format with 1 match returns detail view."""
        # Setup a single project in state
        dev_plan_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "single_project"
        dev_plan_dir.mkdir(parents=True, exist_ok=True)

        progress_file = dev_plan_dir / "PROGRESS_LOG.md"
        progress_file.write_text("[✅] Entry 1\n")

        project_data = {
            "single_project": {
                "name": "single_project",
                "root": str(tmp_path),
                "progress_log": str(progress_file),
                "docs": {},
                "defaults": {}
            }
        }

        mock_state = Mock()
        mock_state.projects = project_data
        mock_state_manager.load.return_value = mock_state

        mock_backend = AsyncMock()
        mock_backend.list_projects.return_value = []

        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server:
            mock_server.state_manager = mock_state_manager
            mock_server.storage_backend = mock_backend
            mock_server.get_agent_identity.return_value = None

            with patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load:
                mock_load.return_value = (None, None, [])

                # Call with exact match
                result = await list_projects(
                    filter="single_project",
                    format="readable"
                )

                # Verify response structure
                assert result["ok"] is True
                assert result["count"] == 1
                assert len(result["projects"]) == 1
                assert "readable_content" in result
                # Detail view should contain project name
                assert "single_project" in result["readable_content"]

    @pytest.mark.asyncio
    async def test_readable_format_multiple_matches(self, mock_state_manager, tmp_path):
        """Test readable format with multiple matches returns table view."""
        # Setup multiple projects
        projects_data = {}
        for i in range(5):
            project_name = f"test_project_{i}"
            dev_plan_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / project_name
            dev_plan_dir.mkdir(parents=True, exist_ok=True)

            progress_file = dev_plan_dir / "PROGRESS_LOG.md"
            progress_file.write_text(f"[✅] Entry {i}\n")

            projects_data[project_name] = {
                "name": project_name,
                "root": str(tmp_path),
                "progress_log": str(progress_file),
                "docs": {},
                "defaults": {}
            }

        mock_state = Mock()
        mock_state.projects = projects_data
        mock_state_manager.load.return_value = mock_state

        mock_backend = AsyncMock()
        mock_backend.list_projects.return_value = []

        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server:
            mock_server.state_manager = mock_state_manager
            mock_server.storage_backend = mock_backend
            mock_server.get_agent_identity.return_value = None

            with patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load:
                mock_load.return_value = (None, None, [])

                # Call with filter matching all test projects
                result = await list_projects(
                    filter="test_project",
                    format="readable"
                )

                # Verify response structure
                assert result["ok"] is True
                assert result["count"] == 5
                assert len(result["projects"]) == 5
                assert "readable_content" in result
                # Table view should contain pagination info
                assert "Page" in result["readable_content"] or \
                       "page" in result["readable_content"].lower()

    @pytest.mark.asyncio
    async def test_structured_format_backward_compatibility(self, mock_state_manager, mock_storage_backend):
        """Test that structured format still works as before."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server:
            mock_server.state_manager = mock_state_manager
            mock_server.storage_backend = mock_storage_backend
            mock_server.get_agent_identity.return_value = None

            with patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load:
                mock_load.return_value = (None, None, [])

                # Call with default format (structured)
                result = await list_projects(format="structured")

                # Verify response structure (no readable_content)
                assert result["ok"] is True
                assert "projects" in result
                assert "count" in result
                assert "pagination" in result
                assert "readable_content" not in result  # Should not have readable content

    @pytest.mark.asyncio
    async def test_compact_format_backward_compatibility(self, mock_state_manager, mock_storage_backend):
        """Test that compact format still works as before."""
        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server:
            mock_server.state_manager = mock_state_manager
            mock_server.storage_backend = mock_storage_backend
            mock_server.get_agent_identity.return_value = None

            with patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load:
                mock_load.return_value = (None, None, [])

                # Call with compact format
                result = await list_projects(format="compact", compact=True)

                # Verify response structure
                assert result["ok"] is True
                assert "projects" in result
                assert "compact" in result
                assert result["compact"] is True
                assert "readable_content" not in result


class TestListProjectsPagination:
    """Test pagination behavior with readable format."""

    @pytest.mark.asyncio
    async def test_pagination_info_in_table_view(self, tmp_path):
        """Test that pagination info is correctly passed to table formatter."""
        # Setup many projects to trigger pagination
        projects_data = {}
        for i in range(15):
            project_name = f"paginated_project_{i:02d}"
            dev_plan_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / project_name
            dev_plan_dir.mkdir(parents=True, exist_ok=True)

            progress_file = dev_plan_dir / "PROGRESS_LOG.md"
            progress_file.write_text(f"[✅] Entry {i}\n")

            projects_data[project_name] = {
                "name": project_name,
                "root": str(tmp_path),
                "progress_log": str(progress_file),
                "docs": {},
                "defaults": {}
            }

        mock_state = Mock()
        mock_state.projects = projects_data

        mock_state_manager = AsyncMock()
        mock_state_manager.record_tool.return_value = {"test": "snapshot"}
        mock_state_manager.load.return_value = mock_state

        mock_backend = AsyncMock()
        mock_backend.list_projects.return_value = []

        with patch('scribe_mcp.tools.list_projects.server_module') as mock_server:
            mock_server.state_manager = mock_state_manager
            mock_server.storage_backend = mock_backend
            mock_server.get_agent_identity.return_value = None

            with patch('scribe_mcp.tools.list_projects.load_active_project') as mock_load:
                mock_load.return_value = (None, None, [])

                # Request page 2 with page_size 5
                result = await list_projects(
                    filter="paginated_project",
                    format="readable",
                    page=2,
                    page_size=5
                )

                # Verify pagination is in response
                assert result["ok"] is True
                assert "pagination" in result
                assert result["pagination"]["page"] == 2
                assert result["pagination"]["page_size"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
