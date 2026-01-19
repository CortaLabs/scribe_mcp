#!/usr/bin/env python3
"""
Tests for EntryLimitManager utility.
"""

import sys
from pathlib import Path

# Add MCP_SPINE root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scribe_mcp.utils.entry_limit import EntryLimitManager


@pytest.fixture
def manager():
    """Create EntryLimitManager instance."""
    return EntryLimitManager()


@pytest.fixture
def test_entries():
    """Create test entries with various priorities and timestamps."""
    return [
        {"message": "Critical bug", "priority": "critical", "ts_iso": "2026-01-02T10:00:00Z"},
        {"message": "High priority task", "priority": "high", "ts_iso": "2026-01-02T11:00:00Z"},
        {"message": "Medium task", "priority": "medium", "ts_iso": "2026-01-02T12:00:00Z"},
        {"message": "Low debug log", "priority": "low", "ts_iso": "2026-01-02T09:00:00Z"},
        {"message": "No priority set", "ts_iso": "2026-01-02T08:00:00Z"},  # Defaults to medium
        {"message": "Another critical", "priority": "critical", "ts_iso": "2026-01-02T13:00:00Z"},
        {"message": "Another high", "priority": "high", "ts_iso": "2026-01-02T07:00:00Z"},
        {"message": "Another medium", "priority": "medium", "ts_iso": "2026-01-02T14:00:00Z"},
    ]


class TestEntryLimitManager:
    """Test suite for EntryLimitManager."""

    def test_limit_entries_default_mode(self, manager, test_entries):
        """Test limit_entries with default mode (summary)."""
        limited, metadata = manager.limit_entries(test_entries)

        # Should use summary mode limit (50)
        assert len(limited) == 8  # We have 8 entries, all should be returned
        assert metadata["mode"] == "summary"
        assert metadata["limit_applied"] == 50
        assert metadata["total_available"] == 8
        assert metadata["returned_count"] == 8
        assert metadata["entries_omitted"] == 0

    def test_limit_entries_full_mode(self, manager, test_entries):
        """Test limit_entries with full mode (limit 10)."""
        limited, metadata = manager.limit_entries(test_entries, mode="full")

        # Should use full mode limit (10)
        assert len(limited) == 8  # We have 8 entries, all should be returned
        assert metadata["mode"] == "full"
        assert metadata["limit_applied"] == 10
        assert metadata["total_available"] == 8
        assert metadata["returned_count"] == 8
        assert metadata["entries_omitted"] == 0

    def test_limit_entries_compact_mode(self, manager, test_entries):
        """Test limit_entries with compact mode (limit 200)."""
        limited, metadata = manager.limit_entries(test_entries, mode="compact")

        assert len(limited) == 8
        assert metadata["mode"] == "compact"
        assert metadata["limit_applied"] == 200

    def test_limit_entries_readable_mode(self, manager, test_entries):
        """Test limit_entries with readable mode (limit 50)."""
        limited, metadata = manager.limit_entries(test_entries, mode="readable")

        assert len(limited) == 8
        assert metadata["mode"] == "readable"
        assert metadata["limit_applied"] == 50

    def test_limit_entries_structured_mode(self, manager, test_entries):
        """Test limit_entries with structured mode (limit 100)."""
        limited, metadata = manager.limit_entries(test_entries, mode="structured")

        assert len(limited) == 8
        assert metadata["mode"] == "structured"
        assert metadata["limit_applied"] == 100

    def test_limit_entries_expandable_mode(self, manager, test_entries):
        """Test limit_entries with expandable mode (limit 50)."""
        limited, metadata = manager.limit_entries(test_entries, mode="expandable")

        assert len(limited) == 8
        assert metadata["mode"] == "expandable"
        assert metadata["limit_applied"] == 50

    def test_priority_filtering(self, manager, test_entries):
        """Test filtering by priority."""
        # Filter to only critical entries
        limited, metadata = manager.limit_entries(
            test_entries,
            priority_filter=["critical"]
        )

        assert len(limited) == 2
        assert all(e["priority"] == "critical" for e in limited)
        assert metadata["total_available"] == 8
        assert metadata["filtered_count"] == 2
        assert metadata["returned_count"] == 2

    def test_priority_filtering_multiple(self, manager, test_entries):
        """Test filtering with multiple priorities."""
        limited, metadata = manager.limit_entries(
            test_entries,
            priority_filter=["critical", "high"]
        )

        assert len(limited) == 4
        assert all(e["priority"] in ["critical", "high"] for e in limited)
        assert metadata["filtered_count"] == 4

    def test_priority_based_sorting(self, manager, test_entries):
        """Test priority-based sorting (critical first, then by timestamp DESC)."""
        limited, metadata = manager.limit_entries(
            test_entries,
            sort_by_priority=True
        )

        # Expected order:
        # 1. Critical entries (newest first): 13:00, 10:00
        # 2. High entries (newest first): 11:00, 07:00
        # 3. Medium entries (newest first): 14:00, 12:00, 08:00 (no priority defaults to medium)
        # 4. Low entries (newest first): 09:00

        assert limited[0]["priority"] == "critical"
        assert limited[0]["ts_iso"] == "2026-01-02T13:00:00Z"  # Newest critical

        assert limited[1]["priority"] == "critical"
        assert limited[1]["ts_iso"] == "2026-01-02T10:00:00Z"  # Older critical

        assert limited[2]["priority"] == "high"
        assert limited[2]["ts_iso"] == "2026-01-02T11:00:00Z"  # Newest high

        assert limited[3]["priority"] == "high"
        assert limited[3]["ts_iso"] == "2026-01-02T07:00:00Z"  # Older high

        # Medium priority entries
        assert limited[4]["priority"] == "medium"
        assert limited[4]["ts_iso"] == "2026-01-02T14:00:00Z"  # Newest medium

        assert limited[5]["priority"] == "medium"
        assert limited[5]["ts_iso"] == "2026-01-02T12:00:00Z"

        # Entry without priority should default to medium
        assert "priority" not in limited[6] or limited[6].get("priority") == "medium"
        assert limited[6]["ts_iso"] == "2026-01-02T08:00:00Z"

        # Low priority last
        assert limited[7]["priority"] == "low"
        assert limited[7]["ts_iso"] == "2026-01-02T09:00:00Z"

    def test_custom_max_entries_override(self, manager, test_entries):
        """Test custom max_entries override."""
        limited, metadata = manager.limit_entries(
            test_entries,
            max_entries=3
        )

        assert len(limited) == 3
        assert metadata["limit_applied"] == 3
        assert metadata["entries_omitted"] == 5  # 8 - 3 = 5

    def test_custom_max_entries_larger_than_available(self, manager, test_entries):
        """Test custom max_entries larger than available entries."""
        limited, metadata = manager.limit_entries(
            test_entries,
            max_entries=100
        )

        assert len(limited) == 8  # All entries
        assert metadata["limit_applied"] == 100
        assert metadata["entries_omitted"] == 0

    def test_metadata_accuracy(self, manager, test_entries):
        """Test metadata accuracy with various scenarios."""
        # Test with limiting
        limited, metadata = manager.limit_entries(
            test_entries,
            max_entries=5
        )

        assert metadata["total_available"] == 8
        assert metadata["filtered_count"] == 8
        assert metadata["returned_count"] == 5
        assert metadata["entries_omitted"] == 3
        assert metadata["limit_applied"] == 5

    def test_empty_entries_list(self, manager):
        """Test with empty entries list."""
        limited, metadata = manager.limit_entries([])

        assert len(limited) == 0
        assert metadata["total_available"] == 0
        assert metadata["filtered_count"] == 0
        assert metadata["returned_count"] == 0
        assert metadata["entries_omitted"] == 0

    def test_entries_without_priority_field(self, manager):
        """Test entries without priority field (should default to medium)."""
        entries = [
            {"message": "No priority 1", "ts_iso": "2026-01-02T10:00:00Z"},
            {"message": "No priority 2", "ts_iso": "2026-01-02T11:00:00Z"},
            {"message": "Has critical", "priority": "critical", "ts_iso": "2026-01-02T12:00:00Z"},
        ]

        limited, metadata = manager.limit_entries(
            entries,
            sort_by_priority=True
        )

        # Critical should come first
        assert limited[0]["priority"] == "critical"
        # Entries without priority should be treated as medium (after critical but before low)
        assert "priority" not in limited[1] or limited[1].get("priority") == "medium"
        assert "priority" not in limited[2] or limited[2].get("priority") == "medium"

    def test_entries_without_timestamp(self, manager):
        """Test entries without ts_iso field."""
        entries = [
            {"message": "No timestamp 1", "priority": "high"},
            {"message": "No timestamp 2", "priority": "high"},
            {"message": "Has timestamp", "priority": "high", "ts_iso": "2026-01-02T10:00:00Z"},
        ]

        limited, metadata = manager.limit_entries(
            entries,
            sort_by_priority=True
        )

        # Should not crash, all entries should be returned
        assert len(limited) == 3
        assert metadata["returned_count"] == 3

    def test_no_sorting_by_priority(self, manager, test_entries):
        """Test with sort_by_priority=False."""
        limited, metadata = manager.limit_entries(
            test_entries,
            sort_by_priority=False
        )

        # Should preserve original order
        assert limited == test_entries[:50]  # Default limit
        assert len(limited) == 8

    def test_priority_filter_with_custom_limit(self, manager, test_entries):
        """Test priority filter combined with custom limit."""
        limited, metadata = manager.limit_entries(
            test_entries,
            priority_filter=["critical", "high"],
            max_entries=2
        )

        # Should filter to critical/high (4 entries), then limit to 2
        assert len(limited) == 2
        assert metadata["filtered_count"] == 4
        assert metadata["returned_count"] == 2
        assert metadata["entries_omitted"] == 2

    def test_complete_entries_returned(self, manager, test_entries):
        """Test that complete entry dicts are returned (no truncation)."""
        limited, metadata = manager.limit_entries(test_entries, max_entries=3)

        # Verify entries are complete dicts
        for entry in limited:
            assert isinstance(entry, dict)
            assert "message" in entry
            # No fields should be modified or truncated
            if "priority" in test_entries[0]:
                assert "priority" in entry or entry.get("message") == "No priority set"

    def test_unrecognized_mode_uses_default(self, manager, test_entries):
        """Test that unrecognized mode uses default limit (50)."""
        limited, metadata = manager.limit_entries(
            test_entries,
            mode="unknown_mode"
        )

        assert metadata["mode"] == "unknown_mode"
        assert metadata["limit_applied"] == 50  # Default

    def test_priority_filter_no_matches(self, manager, test_entries):
        """Test priority filter with no matching entries."""
        limited, metadata = manager.limit_entries(
            test_entries,
            priority_filter=["nonexistent"]
        )

        assert len(limited) == 0
        assert metadata["filtered_count"] == 0
        assert metadata["returned_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
