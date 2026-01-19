"""
Comprehensive test suite for project state detection (Phase 4.1).

Tests validate hash-based state detection logic that fixes BUG-001:
Post-rotation projects should show UNCHANGED/MODIFIED, not false NEW status.
"""

import pytest
from shared.project_utils import detect_project_state, _extract_modified_docs


class TestDetectProjectState:
    """Test suite for detect_project_state function."""

    def test_detect_state_new_project(self):
        """Test 1: NEW state - no baseline hashes AND no entries."""
        project = {"meta": {"docs": {}}}
        entry_count = 0

        state, message = detect_project_state(project, entry_count)

        assert state == "NEW"
        assert "🆕 New project initialized" in message
        assert "NEW" in state

    def test_detect_state_existing_legacy(self):
        """Test 2: EXISTING_LEGACY state - no baseline BUT has entries."""
        project = {"meta": {"docs": {}}}
        entry_count = 47

        state, message = detect_project_state(project, entry_count)

        assert state == "EXISTING_LEGACY"
        assert "📋 Existing project" in message
        assert "47 entries" in message
        assert "pre-hash-tracking" in message

    def test_detect_state_unchanged(self):
        """Test 3: UNCHANGED state - baseline == current hashes."""
        project = {
            "meta": {
                "docs": {
                    "baseline_hashes": {
                        "architecture": "abc123",
                        "phase_plan": "def456",
                        "checklist": "ghi789"
                    },
                    "current_hashes": {
                        "architecture": "abc123",
                        "phase_plan": "def456",
                        "checklist": "ghi789"
                    }
                }
            }
        }
        entry_count = 15

        state, message = detect_project_state(project, entry_count)

        assert state == "UNCHANGED"
        assert "📋 Project unchanged" in message
        assert "15 entries" in message
        assert "docs match baseline" in message

    def test_detect_state_modified_single_doc(self):
        """Test 4: MODIFIED state - one document changed."""
        project = {
            "meta": {
                "docs": {
                    "baseline_hashes": {
                        "architecture": "abc123",
                        "phase_plan": "def456"
                    },
                    "current_hashes": {
                        "architecture": "xyz999",  # Changed
                        "phase_plan": "def456"
                    },
                    "flags": {
                        "architecture_modified": True,
                        "phase_plan_modified": False
                    }
                }
            }
        }
        entry_count = 8

        state, message = detect_project_state(project, entry_count)

        assert state == "MODIFIED"
        assert "✏️ Modified:" in message
        assert "architecture" in message
        assert "8 entries" in message

    def test_detect_state_modified_multiple_docs(self):
        """Test 5: MODIFIED state - multiple documents changed."""
        project = {
            "meta": {
                "docs": {
                    "baseline_hashes": {
                        "architecture": "abc123",
                        "phase_plan": "def456",
                        "checklist": "ghi789"
                    },
                    "current_hashes": {
                        "architecture": "new1",
                        "phase_plan": "new2",
                        "checklist": "ghi789"
                    },
                    "flags": {
                        "architecture_modified": True,
                        "phase_plan_modified": True,
                        "checklist_modified": False
                    }
                }
            }
        }
        entry_count = 22

        state, message = detect_project_state(project, entry_count)

        assert state == "MODIFIED"
        assert "✏️ Modified:" in message
        assert "architecture" in message
        assert "phase_plan" in message
        assert "22 entries" in message

    def test_bug_001_fix_post_rotation(self):
        """
        Test 6: BUG-001 validation - post-rotation scenario.

        CRITICAL TEST: After log rotation, entry_count becomes 0.
        Old logic: entry_count == 0 → NEW (WRONG)
        New logic: baseline exists → UNCHANGED (CORRECT)

        This test MUST pass to validate BUG-001 fix.
        """
        # Simulate post-rotation: baseline exists, entry_count = 0
        project = {
            "meta": {
                "docs": {
                    "baseline_hashes": {
                        "architecture": "abc123",
                        "phase_plan": "def456"
                    },
                    "current_hashes": {
                        "architecture": "abc123",
                        "phase_plan": "def456"
                    }
                }
            }
        }
        entry_count = 0  # Post-rotation: no entries yet

        state, message = detect_project_state(project, entry_count)

        # MUST be UNCHANGED, NOT NEW
        assert state == "UNCHANGED", f"BUG-001 FAILURE: Post-rotation project marked as {state} instead of UNCHANGED"
        assert "📋 Project unchanged" in message
        assert "0 entries" in message
        assert state != "NEW", "BUG-001: Post-rotation project incorrectly flagged as NEW"

    def test_docs_json_in_project_record(self):
        """Test 7: Verify ProjectRecord model exposes docs_json field."""
        from storage.models import ProjectRecord

        # Verify docs_json field exists in model
        record = ProjectRecord(
            id=1,
            name="test_project",
            repo_root="/tmp/test",
            progress_log_path="/tmp/test/PROGRESS_LOG.md",
            docs_json='{"baseline_hashes": {"architecture": "abc123"}}'
        )

        assert hasattr(record, "docs_json")
        assert record.docs_json is not None
        assert "abc123" in record.docs_json

    def test_edge_case_no_flags(self):
        """Test 8: Handle missing flags gracefully."""
        project = {
            "meta": {
                "docs": {
                    "baseline_hashes": {"architecture": "abc123"},
                    "current_hashes": {"architecture": "xyz999"}
                    # No flags field
                }
            }
        }
        entry_count = 5

        state, message = detect_project_state(project, entry_count)

        assert state == "MODIFIED"
        # Should show generic modified message when flags missing
        assert "✏️ Project modified" in message or "Modified:" in message

    def test_edge_case_empty_meta(self):
        """Test 9: Handle empty or missing meta gracefully."""
        project = {}  # No meta field
        entry_count = 0

        state, message = detect_project_state(project, entry_count)

        # Should default to NEW when meta missing
        assert state == "NEW"
        assert "🆕 New project initialized" in message

    def test_sitrep_message_formats(self):
        """Test 10: Validate SITREP message format correctness."""
        # Test NEW message format
        project_new = {"meta": {"docs": {}}}
        state_new, msg_new = detect_project_state(project_new, 0)
        assert "🆕" in msg_new
        assert "New project" in msg_new

        # Test EXISTING_LEGACY message format
        state_legacy, msg_legacy = detect_project_state(project_new, 100)
        assert "📋" in msg_legacy
        assert "Existing project" in msg_legacy
        assert "100 entries" in msg_legacy

        # Test UNCHANGED message format
        project_unchanged = {
            "meta": {
                "docs": {
                    "baseline_hashes": {"architecture": "abc"},
                    "current_hashes": {"architecture": "abc"}
                }
            }
        }
        state_unchanged, msg_unchanged = detect_project_state(project_unchanged, 50)
        assert "📋" in msg_unchanged
        assert "unchanged" in msg_unchanged
        assert "50 entries" in msg_unchanged

        # Test MODIFIED message format
        project_modified = {
            "meta": {
                "docs": {
                    "baseline_hashes": {"architecture": "abc"},
                    "current_hashes": {"architecture": "xyz"},
                    "flags": {"architecture_modified": True}
                }
            }
        }
        state_modified, msg_modified = detect_project_state(project_modified, 25)
        assert "✏️" in msg_modified
        assert "Modified" in msg_modified
        assert "architecture" in msg_modified
        assert "25 entries" in msg_modified


class TestExtractModifiedDocs:
    """Test suite for _extract_modified_docs helper function."""

    def test_extract_single_modified_doc(self):
        """Test extracting single modified document."""
        flags = {
            "architecture_modified": True,
            "phase_plan_modified": False,
            "checklist_modified": False
        }

        result = _extract_modified_docs(flags)

        assert result == ["architecture"]

    def test_extract_multiple_modified_docs(self):
        """Test extracting multiple modified documents."""
        flags = {
            "architecture_modified": True,
            "phase_plan_modified": True,
            "checklist_modified": False
        }

        result = _extract_modified_docs(flags)

        assert "architecture" in result
        assert "phase_plan" in result
        assert "checklist" not in result
        assert len(result) == 2

    def test_extract_no_modified_docs(self):
        """Test when no documents are modified."""
        flags = {
            "architecture_modified": False,
            "phase_plan_modified": False
        }

        result = _extract_modified_docs(flags)

        assert result == []

    def test_extract_empty_flags(self):
        """Test with empty flags dict."""
        flags = {}

        result = _extract_modified_docs(flags)

        assert result == []

    def test_extract_ignores_non_modified_flags(self):
        """Test that non-modified flags are ignored."""
        flags = {
            "architecture_modified": True,
            "some_other_flag": True,  # Should be ignored
            "random_value": False
        }

        result = _extract_modified_docs(flags)

        assert result == ["architecture"]
        assert len(result) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
