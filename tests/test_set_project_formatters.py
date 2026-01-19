#!/usr/bin/env python3
"""
Comprehensive tests for set_project SITREP formatters.

Tests Phase 4 formatter methods:
- format_project_sitrep_new() - New project bootstrap
- format_project_sitrep_existing() - Existing project activation
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from utils.response import ResponseFormatter


class TestFormatProjectSitrepNew:
    """Test suite for format_project_sitrep_new() formatter."""

    @pytest.fixture
    def formatter(self):
        """Create ResponseFormatter instance."""
        return ResponseFormatter()

    @pytest.fixture
    def sample_project(self):
        """Sample project dict for new project."""
        return {
            'name': 'my_new_feature',
            'root': '/home/austin/projects/MCP_SPINE/scribe_mcp',
            'progress_log': '/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/my_new_feature/PROGRESS_LOG.md'
        }

    @pytest.fixture
    def sample_docs_created(self, tmp_path):
        """Create sample template docs with known line counts."""
        docs = {}

        # Create architecture doc (120 lines)
        arch_path = tmp_path / "ARCHITECTURE_GUIDE.md"
        arch_path.write_text("line\n" * 120)  # 120 lines total
        docs['architecture'] = str(arch_path)

        # Create phase plan (80 lines)
        phase_path = tmp_path / "PHASE_PLAN.md"
        phase_path.write_text("line\n" * 80)  # 80 lines total
        docs['phase_plan'] = str(phase_path)

        # Create checklist (60 lines)
        checklist_path = tmp_path / "CHECKLIST.md"
        checklist_path.write_text("line\n" * 60)  # 60 lines total
        docs['checklist'] = str(checklist_path)

        # Create progress log (empty)
        progress_path = tmp_path / "PROGRESS_LOG.md"
        progress_path.write_text("")
        docs['progress_log'] = str(progress_path)

        return docs

    def test_header_shows_new_project_created(self, formatter, sample_project, sample_docs_created):
        """Verify header shows 'NEW PROJECT CREATED' with project name."""
        output = formatter.format_project_sitrep_new(sample_project, sample_docs_created)

        assert "✨ NEW PROJECT CREATED: my_new_feature" in output
        assert "╔══════════════════════════════════════════════════════════╗" in output
        assert "╚══════════════════════════════════════════════════════════╝" in output

    def test_location_section_present(self, formatter, sample_project, sample_docs_created):
        """Verify location section shows root and dev plan paths."""
        output = formatter.format_project_sitrep_new(sample_project, sample_docs_created)

        assert "📂 Location:" in output
        assert "Root: /home/austin/projects/MCP_SPINE/scribe_mcp" in output
        assert "Dev Plan: .scribe/docs/dev_plans/my_new_feature/" in output

    def test_template_doc_line_counts(self, formatter, sample_project, sample_docs_created):
        """Verify template docs show correct line counts."""
        output = formatter.format_project_sitrep_new(sample_project, sample_docs_created)

        assert "✓ ARCHITECTURE_GUIDE.md (template, 120 lines)" in output
        assert "✓ PHASE_PLAN.md (template, 80 lines)" in output
        assert "✓ CHECKLIST.md (template, 60 lines)" in output

    def test_progress_log_shows_empty_ready(self, formatter, sample_project, sample_docs_created):
        """Verify PROGRESS_LOG shows 'empty, ready for entries' not line count."""
        output = formatter.format_project_sitrep_new(sample_project, sample_docs_created)

        assert "✓ PROGRESS_LOG.md (empty, ready for entries)" in output
        # Should NOT show line count for progress log
        assert "PROGRESS_LOG.md (template" not in output

    def test_status_shows_planning_new_project(self, formatter, sample_project, sample_docs_created):
        """Verify status shows 'planning (new project)'."""
        output = formatter.format_project_sitrep_new(sample_project, sample_docs_created)

        assert "🎯 Status: planning (new project)" in output

    def test_next_steps_tip_present(self, formatter, sample_project, sample_docs_created):
        """Verify next steps tip is shown."""
        output = formatter.format_project_sitrep_new(sample_project, sample_docs_created)

        assert "💡 Next: Start with research or architecture phase" in output

    def test_handles_missing_docs_gracefully(self, formatter, sample_project):
        """Verify formatter handles missing docs without crashing."""
        # Empty docs_created dict
        output = formatter.format_project_sitrep_new(sample_project, {})

        assert "📄 Documents Created:" in output
        # Should not crash

    def test_dev_plan_path_extraction(self, formatter, sample_docs_created):
        """Verify dev plan path extraction works correctly."""
        project = {
            'name': 'test_project',
            'root': '/home/user/scribe_mcp',
            'progress_log': '/home/user/scribe_mcp/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md'
        }

        output = formatter.format_project_sitrep_new(project, sample_docs_created)

        assert "Dev Plan: .scribe/docs/dev_plans/test_project/" in output


class TestFormatProjectSitrepExisting:
    """Test suite for format_project_sitrep_existing() formatter."""

    @pytest.fixture
    def formatter(self):
        """Create ResponseFormatter instance."""
        return ResponseFormatter()

    @pytest.fixture
    def sample_project(self):
        """Sample project dict for existing project."""
        return {
            'name': 'scribe_tool_output_refinement',
            'root': '/home/austin/projects/MCP_SPINE/scribe_mcp',
            'progress_log': '/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/scribe_tool_output_refinement/PROGRESS_LOG.md'
        }

    @pytest.fixture
    def sample_inventory(self):
        """Sample inventory dict with docs and custom content."""
        return {
            'docs': {
                'architecture': {'exists': True, 'lines': 1274, 'modified': True},
                'phase_plan': {'exists': True, 'lines': 542, 'modified': False},
                'checklist': {'exists': True, 'lines': 356, 'modified': False},
                'progress': {'exists': True, 'entries': 298}
            },
            'custom': {
                'research_files': 3,
                'bugs_present': False,
                'jsonl_files': ['TOOL_LOG.jsonl']
            }
        }

    @pytest.fixture
    def sample_activity(self):
        """Sample activity dict with status and entry counts."""
        return {
            'status': 'in_progress',
            'total_entries': 298,
            'last_entry_at': '2026-01-03T08:15:30Z',
            'per_log_counts': {
                'progress': 298,
                'doc_updates': 13,
                'bugs': 0
            }
        }

    def test_header_shows_project_activated(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify header shows 'PROJECT ACTIVATED' with project name."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        assert "📌 PROJECT ACTIVATED: scribe_tool_output_refinement" in output
        assert "╔══════════════════════════════════════════════════════════╗" in output

    def test_status_annotation_active_work(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify 'in_progress' status shows '(active work)' annotation."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        assert "Status: in_progress (active work)" in output

    def test_status_without_annotation(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify other statuses don't get annotation."""
        activity = sample_activity.copy()
        activity['status'] = 'planning'

        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, activity
        )

        assert "Status: planning" in output
        assert "(active work)" not in output

    def test_per_log_breakdown_in_total_entries(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify per-log breakdown shows in total entries."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        assert "Total Entries: 298 (doc_updates: 13, progress: 298)" in output

    def test_per_log_breakdown_excludes_zero_counts(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify zero-count log types are excluded from breakdown."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        # bugs: 0 should not appear
        assert "bugs: 0" not in output
        # Only non-zero counts
        assert "progress: 298" in output
        assert "doc_updates: 13" in output

    def test_modified_doc_warnings(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify modified docs get ⚠️ warning marker."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        # Architecture is modified
        assert "⚠️ ARCHITECTURE_GUIDE.md (1274 lines, modified recently)" in output
        # Phase plan is NOT modified
        assert "✓ PHASE_PLAN.md (542 lines)" in output
        # Checklist is NOT modified
        assert "✓ CHECKLIST.md (356 lines)" in output

    def test_progress_log_shows_entries_count(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify progress log shows entries count not lines."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        assert "✓ PROGRESS_LOG.md (298 entries)" in output

    def test_custom_content_section_when_present(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify custom content section shows when content present."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        assert "📁 Custom Documents:" in output
        assert "• research/ (3 files)" in output
        assert "• TOOL_LOG.jsonl (present)" in output

    def test_custom_content_section_omitted_when_absent(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify custom content section omitted when no custom content."""
        inventory = sample_inventory.copy()
        inventory['custom'] = {
            'research_files': 0,
            'bugs_present': False,
            'jsonl_files': []
        }

        output = formatter.format_project_sitrep_existing(
            sample_project, inventory, sample_activity
        )

        # Custom Documents section should not appear
        assert "📁 Custom Documents:" not in output

    def test_relative_time_formatting(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify last activity uses relative time formatting."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        # Should contain "Last Activity:" with relative time
        assert "Last Activity:" in output
        # Should not be the raw timestamp
        assert "2026-01-03T08:15:30Z" not in output

    def test_handles_missing_per_log_counts(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify formatter handles missing per_log_counts gracefully."""
        activity = sample_activity.copy()
        del activity['per_log_counts']

        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, activity
        )

        # Should show total entries without breakdown
        assert "Total Entries: 298" in output
        # Should not crash

    def test_handles_missing_last_entry_at(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify formatter handles missing last_entry_at gracefully."""
        activity = sample_activity.copy()
        del activity['last_entry_at']

        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, activity
        )

        # Should not show Last Activity line
        assert "Last Activity:" not in output
        # Should not crash

    def test_all_docs_modified_warnings(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify all docs can show modified warnings."""
        inventory = sample_inventory.copy()
        inventory['docs'] = {
            'architecture': {'exists': True, 'lines': 1274, 'modified': True},
            'phase_plan': {'exists': True, 'lines': 542, 'modified': True},
            'checklist': {'exists': True, 'lines': 356, 'modified': True},
            'progress': {'exists': True, 'entries': 298, 'modified': True}
        }

        output = formatter.format_project_sitrep_existing(
            sample_project, inventory, sample_activity
        )

        # All should have warning markers
        assert output.count("⚠️") == 4
        assert "modified recently" in output

    def test_empty_docs_list(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify formatter handles empty docs list gracefully."""
        inventory = sample_inventory.copy()
        inventory['docs'] = {}

        output = formatter.format_project_sitrep_existing(
            sample_project, inventory, sample_activity
        )

        assert "📄 Documents (0 total):" in output
        # Should not crash

    def test_multiple_jsonl_files(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify multiple JSONL files are shown."""
        inventory = sample_inventory.copy()
        inventory['custom']['jsonl_files'] = ['TOOL_LOG.jsonl', 'CUSTOM_LOG.jsonl']

        output = formatter.format_project_sitrep_existing(
            sample_project, inventory, sample_activity
        )

        assert "• TOOL_LOG.jsonl (present)" in output
        assert "• CUSTOM_LOG.jsonl (present)" in output

    def test_footer_tip_present(self, formatter, sample_project, sample_inventory, sample_activity):
        """Verify footer tip is shown."""
        output = formatter.format_project_sitrep_existing(
            sample_project, sample_inventory, sample_activity
        )

        assert "💡 Context: Continuing active development - review recent progress entries" in output


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def formatter(self):
        """Create ResponseFormatter instance."""
        return ResponseFormatter()

    def test_new_project_with_colors_enabled(self, tmp_path):
        """Verify new project formatter works with ANSI colors."""
        formatter = ResponseFormatter()

        project = {
            'name': 'test_project',
            'root': '/home/user/scribe',
            'progress_log': '/home/user/scribe/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md'
        }

        docs = {
            'architecture': str(tmp_path / "arch.md"),
            'progress_log': str(tmp_path / "progress.md")
        }

        # Create minimal files
        (tmp_path / "arch.md").write_text("test\n")
        (tmp_path / "progress.md").write_text("")

        output = formatter.format_project_sitrep_new(project, docs)

        # Should contain ANSI color codes
        assert "\033[" in output or "NEW PROJECT CREATED" in output

    def test_existing_project_with_colors_enabled(self):
        """Verify existing project formatter works with ANSI colors."""
        formatter = ResponseFormatter()

        project = {'name': 'test', 'root': '/test', 'progress_log': '/test/PROGRESS_LOG.md'}
        inventory = {'docs': {}, 'custom': {}}
        activity = {'status': 'planning', 'total_entries': 0, 'per_log_counts': {}}

        output = formatter.format_project_sitrep_existing(project, inventory, activity)

        # Should not crash with colors enabled
        assert "PROJECT ACTIVATED" in output

    def test_minimal_data_new_project(self, formatter):
        """Verify new project formatter works with minimal data."""
        project = {'name': 'minimal', 'root': '/root', 'progress_log': '/root/log.md'}
        docs = {}

        output = formatter.format_project_sitrep_new(project, docs)

        assert "NEW PROJECT CREATED: minimal" in output
        # Should not crash

    def test_minimal_data_existing_project(self, formatter):
        """Verify existing project formatter works with minimal data."""
        project = {'name': 'minimal'}
        inventory = {'docs': {}}
        activity = {'total_entries': 0}

        output = formatter.format_project_sitrep_existing(project, inventory, activity)

        assert "PROJECT ACTIVATED: minimal" in output
        # Should not crash


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
