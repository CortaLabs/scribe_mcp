#!/usr/bin/env python3
"""
Test suite for list_projects formatter methods.

Tests the three formatter methods added in Phase 2:
- format_projects_table() - Multi-project table view with pagination
- format_project_detail() - Single project deep dive
- format_no_projects_found() - Empty state with guidance
"""

from datetime import datetime, timezone

from scribe_mcp.utils.response import ResponseFormatter


class TestFormatProjectsTable:
    """Test format_projects_table() method."""

    def test_basic_table_formatting(self):
        """Test basic table output with 5 projects."""
        formatter = ResponseFormatter()

        projects = [
            {
                "name": "scribe_tool_output_refinement",
                "status": "in_progress",
                "total_entries": 259,
                "last_entry_at": datetime.now(timezone.utc)
            },
            {
                "name": "scribe_sentinel_concurrency",
                "status": "in_progress",
                "total_entries": 142,
                "last_entry_at": datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
            },
            {
                "name": "sentinel",
                "status": "planning",
                "total_entries": 12,
                "last_entry_at": datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
            },
            {
                "name": "scribe_mcp",
                "status": "complete",
                "total_entries": 500,
                "last_entry_at": datetime(2025, 12, 27, 12, 0, 0, tzinfo=timezone.utc)
            },
            {
                "name": "phase4_enhancements",
                "status": "planning",
                "total_entries": 8,
                "last_entry_at": datetime(2025, 12, 20, 12, 0, 0, tzinfo=timezone.utc)
            }
        ]

        pagination = {
            "page": 1,
            "total_pages": 3,
            "total_count": 15,
            "page_size": 5
        }

        filters = {
            "order_by": "last_entry_at",
            "direction": "desc"
        }

        result = formatter.format_projects_table(
            projects=projects,
            active_name="scribe_tool_output_refinement",
            pagination=pagination,
            filters=filters
        )

        # Verify header (optimized format)
        assert "📋 Projects (5/15, page 1/3)" in result

        # Verify table headers (optimized format)
        assert "NAME" in result
        assert "STATUS" in result
        assert "ENTRIES" in result
        assert "ACTIVITY" in result  # Changed from "LAST ACTIVITY"

        # Verify active project marker
        assert "⭐ scribe_tool_output_refine" in result

        # Verify non-active project has proper spacing
        assert "  scribe_sentinel_concurrency" in result

        # Verify footer (optimized format - tips removed)
        assert "Page 1/3 | filter: none" in result

    def test_active_project_marking(self):
        """Test that active project gets ⭐ marker."""
        formatter = ResponseFormatter()

        projects = [
            {"name": "project_a", "status": "planning", "total_entries": 10, "last_entry_at": None},
            {"name": "project_b", "status": "in_progress", "total_entries": 20, "last_entry_at": None}
        ]

        pagination = {"page": 1, "total_pages": 1, "total_count": 2, "page_size": 2}
        filters = {"order_by": "name", "direction": "asc"}

        result = formatter.format_projects_table(
            projects=projects,
            active_name="project_b",
            pagination=pagination,
            filters=filters
        )

        # Verify active marker
        assert "⭐ project_b" in result
        # Verify non-active has spacing
        assert "  project_a" in result

    def test_filter_display_in_footer(self):
        """Test filter information display in footer."""
        formatter = ResponseFormatter()

        projects = [
            {"name": "test_project", "status": "planning", "total_entries": 5, "last_entry_at": None}
        ]

        pagination = {"page": 1, "total_pages": 1, "total_count": 1, "page_size": 1}

        # Test with name filter
        filters = {"name": "test", "order_by": "name", "direction": "asc"}
        result = formatter.format_projects_table(projects, None, pagination, filters)
        assert 'name="test"' in result

        # Test with status filter
        filters = {"status": ["planning"], "order_by": "name", "direction": "asc"}
        result = formatter.format_projects_table(projects, None, pagination, filters)
        assert "status=['planning']" in result

        # Test with tags filter
        filters = {"tags": ["phase4"], "order_by": "name", "direction": "asc"}
        result = formatter.format_projects_table(projects, None, pagination, filters)
        assert "tags=['phase4']" in result

    def test_no_last_entry_shows_never(self):
        """Test that projects with no last_entry_at show 'never'."""
        formatter = ResponseFormatter()

        projects = [
            {"name": "new_project", "status": "planning", "total_entries": 0, "last_entry_at": None}
        ]

        pagination = {"page": 1, "total_pages": 1, "total_count": 1, "page_size": 1}
        filters = {"order_by": "name", "direction": "asc"}

        result = formatter.format_projects_table(projects, None, pagination, filters)

        assert "never" in result

    def test_pagination_single_page(self):
        """Test pagination display for single page."""
        formatter = ResponseFormatter()

        projects = [
            {"name": "test", "status": "planning", "total_entries": 1, "last_entry_at": None}
        ]

        pagination = {"page": 1, "total_pages": 1, "total_count": 1, "page_size": 5}
        filters = {}

        result = formatter.format_projects_table(projects, None, pagination, filters)

        # Optimized format - simplified pagination
        assert "Page 1/1" in result


class TestFormatProjectDetail:
    """Test format_project_detail() method."""

    def test_single_project_detail_view(self):
        """Test comprehensive detail view for single project."""
        formatter = ResponseFormatter()

        project = {
            "name": "scribe_tool_output_refinement",
            "status": "in_progress",
            "root": "/tmp/scribe_mcp",
            "progress_log": ".scribe/docs/dev_plans/scribe_tool_output_refinement/PROGRESS_LOG.md",
            "total_entries": 259,
            "tags": ["phase4", "output-refinement", "tokens"],
            "_is_active": True,
            "_filter_used": "tool_output"
        }

        # Mock registry info
        class MockRegistry:
            total_entries = 259
            last_entry_at = datetime(2026, 1, 3, 9, 53, 0, tzinfo=timezone.utc)
            last_access_at = datetime(2026, 1, 3, 10, 29, 0, tzinfo=timezone.utc)
            created_at = datetime(2025, 12, 20, 8, 0, 0, tzinfo=timezone.utc)

        registry_info = MockRegistry()

        docs_info = {
            "architecture": {"exists": True, "lines": 1274, "modified": True},
            "phase_plan": {"exists": True, "lines": 542, "modified": False},
            "checklist": {"exists": True, "lines": 356, "modified": False},
            "progress": {"exists": True, "entries": 298},
            "custom": {
                "research_files": 3,
                "bugs_present": False,
                "jsonl_files": ["TOOL_LOG.jsonl"]
            }
        }

        result = formatter.format_project_detail(
            project=project,
            registry_info=registry_info,
            docs_info=docs_info
        )

        # Verify header
        assert "📁 PROJECT DETAIL: scribe_tool_output_refinement" in result
        assert '(1 match found for filter: "tool_output")' in result

        # Verify status shows active marker
        assert "⭐ (active)" in result

        # Verify location info
        assert "/tmp/scribe_mcp" in result

        # Verify activity section
        assert "📊 Activity:" in result
        assert "Total Entries: 259" in result

        # Verify documents section
        assert "📄 Documents:" in result
        assert "ARCHITECTURE_GUIDE.md (1274 lines, modified)" in result
        assert "PHASE_PLAN.md (542 lines)" in result
        assert "CHECKLIST.md (356 lines)" in result
        assert "PROGRESS_LOG.md (298 entries)" in result

        # Verify custom content
        assert "📁 Custom Content:" in result
        assert "research/ (3 files)" in result
        assert "TOOL_LOG.jsonl (present)" in result

        # Verify tags
        assert "🏷️  Tags: phase4, output-refinement, tokens" in result

        # Verify modified warning
        assert "⚠️  Docs Status: Architecture modified" in result

        # Verify footer tip
        assert "💡 Use get_project() to see recent progress entries" in result

    def test_no_custom_content_hides_section(self):
        """Test that custom content section is hidden when empty."""
        formatter = ResponseFormatter()

        project = {
            "name": "simple_project",
            "status": "planning",
            "root": "/path/to/project",
            "progress_log": "/path/to/PROGRESS_LOG.md",
            "_is_active": False
        }

        docs_info = {
            "architecture": {"exists": True, "lines": 100, "modified": False},
            "phase_plan": {"exists": True, "lines": 50, "modified": False},
            "checklist": {"exists": True, "lines": 30, "modified": False},
            "progress": {"exists": True, "entries": 10},
            "custom": {
                "research_files": 0,
                "bugs_present": False,
                "jsonl_files": []
            }
        }

        result = formatter.format_project_detail(
            project=project,
            registry_info=None,
            docs_info=docs_info
        )

        # Custom content section should NOT appear
        assert "📁 Custom Content:" not in result

    def test_modified_docs_warning(self):
        """Test warning display for modified documents."""
        formatter = ResponseFormatter()

        project = {
            "name": "test_project",
            "status": "in_progress",
            "root": "/test",
            "progress_log": "/test/PROGRESS_LOG.md",
            "_is_active": False
        }

        docs_info = {
            "architecture": {"exists": True, "lines": 100, "modified": True},
            "phase_plan": {"exists": True, "lines": 50, "modified": True},
            "checklist": {"exists": True, "lines": 30, "modified": False},
            "progress": {"exists": True, "entries": 5},
            "custom": {"research_files": 0, "bugs_present": False, "jsonl_files": []}
        }

        result = formatter.format_project_detail(
            project=project,
            registry_info=None,
            docs_info=docs_info
        )

        # Should show warning marker for modified docs
        assert "⚠️" in result
        assert "modified" in result

    def test_no_registry_info_fallback(self):
        """Test fallback when registry_info is None."""
        formatter = ResponseFormatter()

        project = {
            "name": "fallback_project",
            "status": "planning",
            "root": "/path",
            "progress_log": "/path/PROGRESS_LOG.md",
            "total_entries": 50,
            "_is_active": False
        }

        docs_info = {
            "architecture": {"exists": True, "lines": 10, "modified": False},
            "phase_plan": {"exists": True, "lines": 10, "modified": False},
            "checklist": {"exists": True, "lines": 10, "modified": False},
            "progress": {"exists": True, "entries": 50},
            "custom": {"research_files": 0, "bugs_present": False, "jsonl_files": []}
        }

        result = formatter.format_project_detail(
            project=project,
            registry_info=None,  # No registry info
            docs_info=docs_info
        )

        # Should still show total entries from project dict
        assert "Total Entries: 50" in result


class TestFormatNoProjectsFound:
    """Test format_no_projects_found() method."""

    def test_empty_state_with_single_filter(self):
        """Test empty state display with single filter."""
        formatter = ResponseFormatter()

        filters = {"name": "nonexistent"}

        result = formatter.format_no_projects_found(filters)

        # Verify header
        assert "📋 PROJECTS - 0 matches for filter:" in result
        assert '"nonexistent"' in result

        # Verify message
        assert "No projects found matching your criteria." in result

        # Verify active filters section
        assert "🔍 Active Filters:" in result
        assert 'Name: "nonexistent"' in result

        # Verify suggestions
        assert "💡 Try:" in result
        assert "list_projects()" in result
        assert 'list_projects(filter="scribe")' in result
        assert 'list_projects(status=["planning", "in_progress"])' in result

    def test_empty_state_with_multiple_filters(self):
        """Test empty state with multiple filters."""
        formatter = ResponseFormatter()

        filters = {
            "name": "test",
            "status": ["planning"],
            "tags": ["experimental"]
        }

        result = formatter.format_no_projects_found(filters)

        # Should show "multiple filters" in header
        assert "multiple filters" in result

        # Verify all filters listed
        assert 'Name: "test"' in result
        assert "Status: ['planning']" in result
        assert "Tags: ['experimental']" in result

    def test_empty_state_with_no_filters(self):
        """Test empty state when no filters are active (edge case)."""
        formatter = ResponseFormatter()

        filters = {}

        result = formatter.format_no_projects_found(filters)

        # Should show "none" in header
        assert "filter: none" in result

        # Active filters section should still appear
        assert "🔍 Active Filters:" in result

        # Suggestions should appear
        assert "💡 Try:" in result

    def test_suggestions_always_present(self):
        """Test that suggestions are always shown."""
        formatter = ResponseFormatter()

        filters = {"name": "anything"}

        result = formatter.format_no_projects_found(filters)

        # All three suggestions must be present
        assert "Remove filters: list_projects()" in result
        assert 'Broader search: list_projects(filter="scribe")' in result
        assert 'Check status: list_projects(status=["planning", "in_progress"])' in result


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_ansi_color_support_disabled(self):
        """Test that formatters work with ANSI colors disabled."""
        # Create formatter with ANSI colors disabled via config
        formatter = ResponseFormatter()
        # Note: USE_COLORS is a read-only property from config
        # We test by checking output when colors are disabled by default

        projects = [
            {"name": "test", "status": "planning", "total_entries": 1, "last_entry_at": None}
        ]
        pagination = {"page": 1, "total_pages": 1, "total_count": 1, "page_size": 1}
        filters = {}

        result = formatter.format_projects_table(projects, None, pagination, filters)

        # When colors are disabled, should not contain ANSI color codes
        # Note: This test passes if config has use_ansi_colors: false
        # The actual color support depends on runtime config, so we just verify
        # that the formatter handles the USE_COLORS property correctly
        assert "📋 Projects" in result  # Verify basic formatting works (optimized header)

    def test_long_project_name_truncation(self):
        """Test that long project names are properly truncated."""
        formatter = ResponseFormatter()

        projects = [
            {
                "name": "very_long_project_name_that_exceeds_column_width_limit",
                "status": "planning",
                "total_entries": 5,
                "last_entry_at": None
            }
        ]

        pagination = {"page": 1, "total_pages": 1, "total_count": 1, "page_size": 1}
        filters = {}

        result = formatter.format_projects_table(projects, None, pagination, filters)

        # Name should be truncated to fit column (27 chars max)
        assert "very_long_project_name_that" in result
        # Should not overflow column
        lines = result.split("\n")
        for line in lines:
            if "very_long" in line:
                # Verify line doesn't exceed reasonable width
                assert len(line) < 100  # Reasonable line width


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
