#!/usr/bin/env python3
"""
Unit tests for log_enums module.

Tests LogPriority and LogCategory enums and their helper functions.
"""

import sys
from pathlib import Path

# Add parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scribe_mcp.shared.log_enums import (
    LogPriority,
    LogCategory,
    validate_priority,
    validate_category,
    infer_priority_from_status,
    get_priority_sort_key,
)


class TestLogPriority:
    """Test LogPriority enum values and access"""

    def test_enum_values(self):
        """Test all LogPriority enum values are accessible"""
        assert LogPriority.CRITICAL.value == "critical"
        assert LogPriority.HIGH.value == "high"
        assert LogPriority.MEDIUM.value == "medium"
        assert LogPriority.LOW.value == "low"

    def test_enum_membership(self):
        """Test enum membership checks"""
        assert LogPriority.CRITICAL in LogPriority
        assert LogPriority.HIGH in LogPriority
        assert LogPriority.MEDIUM in LogPriority
        assert LogPriority.LOW in LogPriority

    def test_enum_count(self):
        """Test correct number of priority levels"""
        assert len(LogPriority) == 4


class TestLogCategory:
    """Test LogCategory enum values and access"""

    def test_enum_values(self):
        """Test all LogCategory enum values are accessible"""
        assert LogCategory.DECISION.value == "decision"
        assert LogCategory.INVESTIGATION.value == "investigation"
        assert LogCategory.BUG.value == "bug"
        assert LogCategory.IMPLEMENTATION.value == "implementation"
        assert LogCategory.TEST.value == "test"
        assert LogCategory.MILESTONE.value == "milestone"
        assert LogCategory.CONFIG.value == "config"
        assert LogCategory.SECURITY.value == "security"
        assert LogCategory.PERFORMANCE.value == "performance"
        assert LogCategory.DOCUMENTATION.value == "documentation"

    def test_enum_membership(self):
        """Test enum membership checks"""
        assert LogCategory.BUG in LogCategory
        assert LogCategory.SECURITY in LogCategory
        assert LogCategory.MILESTONE in LogCategory

    def test_enum_count(self):
        """Test correct number of categories"""
        assert len(LogCategory) == 10


class TestValidatePriority:
    """Test validate_priority helper function"""

    def test_valid_lowercase(self):
        """Test validation with lowercase priority strings"""
        assert validate_priority("critical") == LogPriority.CRITICAL
        assert validate_priority("high") == LogPriority.HIGH
        assert validate_priority("medium") == LogPriority.MEDIUM
        assert validate_priority("low") == LogPriority.LOW

    def test_valid_uppercase(self):
        """Test validation with uppercase priority strings (case-insensitive)"""
        assert validate_priority("CRITICAL") == LogPriority.CRITICAL
        assert validate_priority("HIGH") == LogPriority.HIGH
        assert validate_priority("MEDIUM") == LogPriority.MEDIUM
        assert validate_priority("LOW") == LogPriority.LOW

    def test_valid_mixed_case(self):
        """Test validation with mixed case priority strings"""
        assert validate_priority("Critical") == LogPriority.CRITICAL
        assert validate_priority("HiGh") == LogPriority.HIGH

    def test_enum_passthrough(self):
        """Test that LogPriority enum values pass through unchanged"""
        assert validate_priority(LogPriority.CRITICAL) == LogPriority.CRITICAL
        assert validate_priority(LogPriority.HIGH) == LogPriority.HIGH

    def test_none_value(self):
        """Test that None returns None"""
        assert validate_priority(None) is None

    def test_invalid_string(self):
        """Test that invalid priority strings raise ValueError"""
        with pytest.raises(ValueError, match="Invalid priority"):
            validate_priority("invalid")

        with pytest.raises(ValueError, match="Invalid priority"):
            validate_priority("super_high")

    def test_invalid_type(self):
        """Test that non-string, non-enum values raise ValueError"""
        with pytest.raises(ValueError, match="Priority must be string or LogPriority enum"):
            validate_priority(123)

        with pytest.raises(ValueError, match="Priority must be string or LogPriority enum"):
            validate_priority([])


class TestValidateCategory:
    """Test validate_category helper function"""

    def test_valid_lowercase(self):
        """Test validation with lowercase category strings"""
        assert validate_category("bug") == LogCategory.BUG
        assert validate_category("decision") == LogCategory.DECISION
        assert validate_category("security") == LogCategory.SECURITY
        assert validate_category("test") == LogCategory.TEST

    def test_valid_uppercase(self):
        """Test validation with uppercase category strings (case-insensitive)"""
        assert validate_category("BUG") == LogCategory.BUG
        assert validate_category("SECURITY") == LogCategory.SECURITY
        assert validate_category("MILESTONE") == LogCategory.MILESTONE

    def test_valid_mixed_case(self):
        """Test validation with mixed case category strings"""
        assert validate_category("Bug") == LogCategory.BUG
        assert validate_category("SeCuRiTy") == LogCategory.SECURITY

    def test_enum_passthrough(self):
        """Test that LogCategory enum values pass through unchanged"""
        assert validate_category(LogCategory.BUG) == LogCategory.BUG
        assert validate_category(LogCategory.SECURITY) == LogCategory.SECURITY

    def test_none_value(self):
        """Test that None returns None"""
        assert validate_category(None) is None

    def test_invalid_string(self):
        """Test that invalid category strings raise ValueError"""
        with pytest.raises(ValueError, match="Invalid category"):
            validate_category("invalid")

        with pytest.raises(ValueError, match="Invalid category"):
            validate_category("super_bug")

    def test_invalid_type(self):
        """Test that non-string, non-enum values raise ValueError"""
        with pytest.raises(ValueError, match="Category must be string or LogCategory enum"):
            validate_category(123)

        with pytest.raises(ValueError, match="Category must be string or LogCategory enum"):
            validate_category({})


class TestInferPriorityFromStatus:
    """Test infer_priority_from_status helper function"""

    def test_high_priority_statuses(self):
        """Test that error and bug statuses map to HIGH priority"""
        assert infer_priority_from_status("error") == LogPriority.HIGH
        assert infer_priority_from_status("bug") == LogPriority.HIGH

    def test_medium_priority_statuses(self):
        """Test that warn, success, and plan statuses map to MEDIUM priority"""
        assert infer_priority_from_status("warn") == LogPriority.MEDIUM
        assert infer_priority_from_status("success") == LogPriority.MEDIUM
        assert infer_priority_from_status("plan") == LogPriority.MEDIUM

    def test_low_priority_statuses(self):
        """Test that info status maps to LOW priority"""
        assert infer_priority_from_status("info") == LogPriority.LOW

    def test_case_insensitive(self):
        """Test that status matching is case-insensitive"""
        assert infer_priority_from_status("ERROR") == LogPriority.HIGH
        assert infer_priority_from_status("Bug") == LogPriority.HIGH
        assert infer_priority_from_status("SUCCESS") == LogPriority.MEDIUM
        assert infer_priority_from_status("Info") == LogPriority.LOW

    def test_unknown_status_defaults_to_medium(self):
        """Test that unknown statuses default to MEDIUM priority"""
        assert infer_priority_from_status("unknown") == LogPriority.MEDIUM
        assert infer_priority_from_status("custom") == LogPriority.MEDIUM
        assert infer_priority_from_status("") == LogPriority.MEDIUM

    def test_all_standard_statuses(self):
        """Test all six standard status values"""
        status_map = {
            "error": LogPriority.HIGH,
            "bug": LogPriority.HIGH,
            "warn": LogPriority.MEDIUM,
            "success": LogPriority.MEDIUM,
            "info": LogPriority.LOW,
            "plan": LogPriority.MEDIUM,
        }

        for status, expected_priority in status_map.items():
            assert infer_priority_from_status(status) == expected_priority


class TestGetPrioritySortKey:
    """Test get_priority_sort_key helper function"""

    def test_critical_highest(self):
        """Test that critical has lowest sort key (highest priority)"""
        assert get_priority_sort_key("critical") == 0
        assert get_priority_sort_key(LogPriority.CRITICAL) == 0

    def test_high_second(self):
        """Test that high has second lowest sort key"""
        assert get_priority_sort_key("high") == 1
        assert get_priority_sort_key(LogPriority.HIGH) == 1

    def test_medium_third(self):
        """Test that medium has third lowest sort key"""
        assert get_priority_sort_key("medium") == 2
        assert get_priority_sort_key(LogPriority.MEDIUM) == 2

    def test_low_lowest(self):
        """Test that low has highest sort key (lowest priority)"""
        assert get_priority_sort_key("low") == 3
        assert get_priority_sort_key(LogPriority.LOW) == 3

    def test_case_insensitive(self):
        """Test that sort key works with case-insensitive input"""
        assert get_priority_sort_key("CRITICAL") == 0
        assert get_priority_sort_key("High") == 1

    def test_enum_input(self):
        """Test that LogPriority enum values work correctly"""
        assert get_priority_sort_key(LogPriority.CRITICAL) == 0
        assert get_priority_sort_key(LogPriority.HIGH) == 1
        assert get_priority_sort_key(LogPriority.MEDIUM) == 2
        assert get_priority_sort_key(LogPriority.LOW) == 3

    def test_sort_ordering(self):
        """Test that priorities sort correctly using the key"""
        priorities = ["low", "critical", "medium", "high", "low", "critical"]
        sorted_priorities = sorted(priorities, key=get_priority_sort_key)
        assert sorted_priorities == ["critical", "critical", "high", "medium", "low", "low"]

    def test_invalid_priority_raises(self):
        """Test that invalid priority raises ValueError"""
        with pytest.raises(ValueError, match="Invalid priority"):
            get_priority_sort_key("invalid")

    def test_none_priority_raises(self):
        """Test that None priority raises ValueError"""
        with pytest.raises(ValueError, match="Priority cannot be None"):
            get_priority_sort_key(None)


class TestIntegration:
    """Integration tests combining multiple functions"""

    def test_status_to_priority_to_sort_key(self):
        """Test full pipeline: status → priority → sort key"""
        # error -> HIGH -> 1
        priority = infer_priority_from_status("error")
        sort_key = get_priority_sort_key(priority)
        assert sort_key == 1

        # info -> LOW -> 3
        priority = infer_priority_from_status("info")
        sort_key = get_priority_sort_key(priority)
        assert sort_key == 3

    def test_validate_then_sort(self):
        """Test validation followed by sorting"""
        priorities = ["HIGH", "low", "CRITICAL", "medium"]
        validated = [validate_priority(p) for p in priorities]
        sorted_validated = sorted(validated, key=lambda p: get_priority_sort_key(p))

        assert sorted_validated == [
            LogPriority.CRITICAL,
            LogPriority.HIGH,
            LogPriority.MEDIUM,
            LogPriority.LOW,
        ]

    def test_round_trip_priority(self):
        """Test that priority values survive round-trip conversion"""
        for priority in LogPriority:
            validated = validate_priority(priority.value)
            assert validated == priority
            assert validated.value == priority.value

    def test_round_trip_category(self):
        """Test that category values survive round-trip conversion"""
        for category in LogCategory:
            validated = validate_category(category.value)
            assert validated == category
            assert validated.value == category.value
