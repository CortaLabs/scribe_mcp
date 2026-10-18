#!/usr/bin/env python3
"""Comprehensive unit tests for ExceptionHealer class.

Tests for Task 3.3 ExceptionHealer enhancement covering all 9 methods
with various exception scenarios and healing strategies.
"""

import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any

from scribe_mcp.utils.error_handler import ExceptionHealer
from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector


class TestExceptionHealer:
    """Test suite for ExceptionHealer class."""

    def test_heal_complex_exception_combination_type_conversion(self):
        """Test healing complex exception with type conversion issues."""
        exception = ValueError("Invalid type for parameter n")
        context = {
            "parameters": {"n": "5", "page_size": "large"},
            "operation_type": "read_recent",
            "expected_types": {"n": "int", "page_size": "int"}
        }

        result = ExceptionHealer.heal_complex_exception_combination(exception, context)

        assert result["healing_applied"] is True
        assert result["exception_type"] == "ValueError"
        assert "corrected_parameters" in result
        assert "healing_strategies" in result
        assert "healed_parameters" in result

    def test_heal_complex_exception_combination_parameter_conflicts(self):
        """Test healing complex exception with parameter conflicts."""
        exception = ValueError("Conflicting parameters: page and page_size")
        context = {
            "parameters": {"page": -1, "page_size": 0},
            "operation_type": "query_entries"
        }

        result = ExceptionHealer.heal_complex_exception_combination(exception, context)

        assert result["healing_applied"] is True
        assert "Parameter conflict resolution" in result["healing_strategies"]

    def test_heal_complex_exception_combination_missing_parameters(self):
        """Test healing complex exception with missing required parameters."""
        exception = KeyError("Missing required parameter: n")
        context = {
            "parameters": {"message": "test"},
            "operation_type": "read_recent"
        }

        result = ExceptionHealer.heal_complex_exception_combination(exception, context)

        assert result["healing_applied"] is True
        assert any("Missing parameter" in strategy for strategy in result["healing_strategies"])

    def test_apply_intelligent_exception_recovery_value_error(self):
        """Test intelligent recovery for ValueError exceptions."""
        exception = ValueError("Invalid parameter value")
        operation_context = "read_recent"

        result = ExceptionHealer.apply_intelligent_exception_recovery(exception, operation_context)

        assert result["recovery_attempted"] is True
        assert result["exception_type"] == "ValueError"
        assert result["recovery_strategy"] == "parameter_correction"
        assert result["success_probability"] == 0.85
        assert len(result["recovery_actions"]) > 0
        assert result["fallback_plan"] == "emergency_fallback"

    def test_apply_intelligent_exception_recovery_type_error(self):
        """Test intelligent recovery for TypeError exceptions."""
        exception = TypeError("Unsupported operand type")
        operation_context = "query_entries"

        result = ExceptionHealer.apply_intelligent_exception_recovery(exception, operation_context)

        assert result["recovery_strategy"] == "parameter_correction"
        assert result["success_probability"] == 0.85

    def test_apply_intelligent_exception_recovery_key_error(self):
        """Test intelligent recovery for KeyError exceptions."""
        exception = KeyError("Missing dictionary key")
        operation_context = "manage_docs"

        result = ExceptionHealer.apply_intelligent_exception_recovery(exception, operation_context)

        assert result["recovery_strategy"] == "structure_healing"
        assert result["success_probability"] == 0.75
        assert result["fallback_plan"] == "minimal_operation"

    def test_apply_intelligent_exception_recovery_file_error(self):
        """Test intelligent recovery for file-related exceptions."""
        exception = FileNotFoundError("File not found")
        operation_context = "rotate_log"

        result = ExceptionHealer.apply_intelligent_exception_recovery(exception, operation_context)

        assert result["recovery_strategy"] == "file_operation_healing"
        assert result["success_probability"] == 0.70
        assert "Create missing directories automatically" in result["recovery_actions"]

    def test_apply_intelligent_exception_recovery_database_error(self):
        """Test intelligent recovery for database-related exceptions."""
        exception = ConnectionError("Database connection failed")
        operation_context = "append_entry"

        result = ExceptionHealer.apply_intelligent_exception_recovery(exception, operation_context)

        assert result["recovery_strategy"] == "storage_healing"
        assert result["success_probability"] == 0.80
        assert result["fallback_plan"] == "cached_response"

    def test_apply_intelligent_exception_recovery_general_error(self):
        """Test intelligent recovery for general exceptions."""
        exception = RuntimeError("General runtime error")
        operation_context = "unknown"

        result = ExceptionHealer.apply_intelligent_exception_recovery(exception, operation_context)

        assert result["recovery_strategy"] == "general_healing"
        assert result["success_probability"] == 0.60
        assert result["fallback_plan"] == "emergency_fallback"

    def test_heal_emergency_exception_emergency_strategy(self):
        """Test emergency healing with emergency strategy."""
        exception = ValueError("Critical error")
        fallback_strategy = "emergency"

        result = ExceptionHealer.heal_emergency_exception(exception, fallback_strategy)

        assert result["emergency_healing_applied"] is True
        assert result["fallback_strategy"] == "emergency"
        assert result["guaranteed_success"] is True
        assert result["healing_method"] == "complete_parameter_reset"
        assert "limitations" in result
        assert result["recovery_time"] == "immediate"

    def test_heal_emergency_exception_minimal_strategy(self):
        """Test emergency healing with minimal strategy."""
        exception = TypeError("Type error")
        fallback_strategy = "minimal"

        result = ExceptionHealer.heal_emergency_exception(exception, fallback_strategy)

        assert result["healing_method"] == "minimal_viable_operation"
        assert result["fallback_strategy"] == "minimal"

    def test_heal_emergency_exception_cache_strategy(self):
        """Test emergency healing with cache strategy."""
        exception = FileNotFoundError("File missing")
        fallback_strategy = "cache"

        result = ExceptionHealer.heal_emergency_exception(exception, fallback_strategy)

        assert result["healing_method"] == "cached_response_fallback"
        assert "Data may be stale" in result["warning"]

    def test_heal_emergency_exception_unknown_strategy(self):
        """Test emergency healing with unknown strategy."""
        exception = RuntimeError("Unknown error")
        fallback_strategy = "unknown"

        result = ExceptionHealer.heal_emergency_exception(exception, fallback_strategy)

        assert result["healing_method"] == "generic_fallback"
        assert result["fallback_strategy"] == "unknown"

    @patch('scribe_mcp.utils.parameter_validator.BulletproofParameterCorrector')
    def test_heal_parameter_validation_error_read_recent(self, mock_corrector):
        """Test parameter validation error healing for read_recent."""
        mock_corrector.correct_read_recent_parameters.return_value = {"n": 10, "page": 1}
        exception = ValueError("Invalid n parameter")
        context = {
            "parameters": {"n": "invalid", "page": 1},
            "operation_type": "read_recent"
        }

        result = ExceptionHealer.heal_parameter_validation_error(exception, context)

        assert result["healing_type"] == "parameter_validation"
        mock_corrector.correct_read_recent_parameters.assert_called_once()

    @patch('scribe_mcp.utils.parameter_validator.BulletproofParameterCorrector')
    def test_heal_parameter_validation_error_query_entries(self, mock_corrector):
        """Test parameter validation error healing for query_entries."""
        mock_corrector.correct_query_entries_parameters.return_value = {"query": "test"}
        exception = ValueError("Invalid query parameter")
        context = {
            "parameters": {"query": "test"},
            "operation_type": "query_entries"
        }

        result = ExceptionHealer.heal_parameter_validation_error(exception, context)

        assert result["healing_type"] == "parameter_validation"
        mock_corrector.correct_query_entries_parameters.assert_called_once()

    @patch('scribe_mcp.utils.parameter_validator.BulletproofParameterCorrector')
    def test_heal_parameter_validation_error_manage_docs(self, mock_corrector):
        """Test parameter validation error healing for manage_docs."""
        mock_corrector.correct_manage_docs_parameters.return_value = {"action": "append"}
        exception = ValueError("Invalid action parameter")
        context = {
            "parameters": {"action": "append"},
            "operation_type": "manage_docs"
        }

        result = ExceptionHealer.heal_parameter_validation_error(exception, context)

        assert result["healing_type"] == "parameter_validation"
        mock_corrector.correct_manage_docs_parameters.assert_called_once()

    @patch('scribe_mcp.utils.parameter_validator.BulletproofParameterCorrector')
    def test_heal_parameter_validation_error_append_entry(self, mock_corrector):
        """Test parameter validation error healing for append_entry."""
        mock_corrector.correct_append_entry_parameters.return_value = {"message": "test"}
        exception = ValueError("Invalid message parameter")
        context = {
            "parameters": {"message": "test"},
            "operation_type": "append_entry"
        }

        result = ExceptionHealer.heal_parameter_validation_error(exception, context)

        assert result["healing_type"] == "parameter_validation"
        mock_corrector.correct_append_entry_parameters.assert_called_once()
        assert "healed_values" in result

    @patch('scribe_mcp.utils.parameter_validator.BulletproofParameterCorrector')
    def test_heal_parameter_validation_error_top_level_context_params(self, mock_corrector):
        """
        Regression: some tools pass parameters directly in the context dict rather than under `parameters`.
        When healing succeeds, callers expect `healed_values` to exist.
        """
        mock_corrector.correct_append_entry_parameters.return_value = {"message": "fixed", "log_type": "progress"}
        exception = ValueError("bad params")
        context = {
            "message": 123,
            "log_type": None,
            "operation_type": "append_entry",
        }

        result = ExceptionHealer.heal_parameter_validation_error(exception, context)

        assert result["healing_type"] == "parameter_validation"
        assert result["success"] is True
        assert result["healed_values"]["message"] == "fixed"
        assert "corrected_parameters" in result
        assert result["corrected_parameters"]["message"] == "fixed"

    @patch('scribe_mcp.utils.parameter_validator.BulletproofParameterCorrector')
    def test_heal_parameter_validation_error_rotate_log(self, mock_corrector):
        """Test parameter validation error healing for rotate_log."""
        mock_corrector.correct_rotate_log_parameters.return_value = {"confirm": True}
        exception = ValueError("Invalid confirm parameter")
        context = {
            "parameters": {"confirm": True},
            "operation_type": "rotate_log"
        }

        result = ExceptionHealer.heal_parameter_validation_error(exception, context)

        assert result["healing_type"] == "parameter_validation"
        mock_corrector.correct_rotate_log_parameters.assert_called_once()

    @patch('scribe_mcp.utils.parameter_validator.BulletproofParameterCorrector')
    def test_heal_parameter_validation_error_unknown_operation(self, mock_corrector):
        """Test parameter validation error healing for unknown operation."""
        mock_corrector.correct_intelligent_parameter.return_value = {"param": "value"}
        exception = ValueError("Invalid parameter")
        context = {
            "parameters": {"param": "value"},
            "operation_type": "unknown"
        }

        result = ExceptionHealer.heal_parameter_validation_error(exception, context)

        assert result["healing_type"] == "parameter_validation"
        mock_corrector.correct_intelligent_parameter.assert_called_once()

    def test_heal_document_operation_error_with_alternative_paths(self):
        """Test document operation error healing with alternative paths."""
        exception = FileNotFoundError("Document not found")
        context = {
            "document_path": "/path/to/document.md",
            "operation": "read"
        }

        result = ExceptionHealer.heal_document_operation_error(exception, context)

        assert result["healing_type"] == "document_operation"
        assert "fallback_strategies_tried" in result
        assert len(result["fallback_strategies_tried"]) > 0
        assert "healed_values" in result

    def test_heal_document_operation_error_create_missing(self):
        """Test document operation error healing by creating missing document."""
        exception = FileNotFoundError("Document not found")
        context = {
            "document_path": "/path/to/document.md",
            "operation": "write"
        }

        result = ExceptionHealer.heal_document_operation_error(exception, context)

        assert result["healing_type"] == "document_operation"
        assert result["success"] is True
        assert result["final_strategy"] in ["create_missing", "emergency"]
        assert "healed_values" in result

    def test_heal_document_operation_error_emergency_fallback(self):
        """Test document operation error healing with emergency fallback."""
        exception = PermissionError("Permission denied")
        context = {
            "document_path": "/path/to/document.md",
            "operation": "write"
        }

        result = ExceptionHealer.heal_document_operation_error(exception, context)

        assert result["healing_type"] == "document_operation"
        assert result["success"] is True
        assert result["final_strategy"] == "emergency"

    def test_heal_bulk_processing_error_empty_batch(self):
        """Test bulk processing error healing with empty batch."""
        exception = ValueError("Empty batch")
        context = {
            "items": [],
            "operation": "process"
        }

        result = ExceptionHealer.heal_bulk_processing_error(exception, context)

        assert result["healing_type"] == "bulk_processing"
        assert result["success"] is True
        assert result["recovery_strategy"] == "empty_batch"
        assert "healed_values" in result
        assert "bulk_items" in result["healed_values"]

    def test_heal_bulk_processing_error_with_items(self):
        """Test bulk processing error healing with items to process."""
        exception = RuntimeError("Bulk processing failed")
        context = {
            "items": [{"id": 1}, {"id": 2}, {"id": 3}],
            "operation": "process"
        }

        result = ExceptionHealer.heal_bulk_processing_error(exception, context)

        assert result["healing_type"] == "bulk_processing"
        assert "items_processed" in result
        assert "items_failed" in result
        assert "result" in result
        assert result["partial_success"] is True
        assert result["success"] is True
        assert "healed_values" in result
        assert "bulk_items" in result["healed_values"]

    def test_heal_bulk_processing_error_accepts_bulk_items_key(self):
        """Regression: some callers pass `bulk_items` instead of `items`."""
        exception = RuntimeError("Bulk processing failed")
        context = {"bulk_items": [{"id": 1}, {"id": 2}], "operation": "process"}

        result = ExceptionHealer.heal_bulk_processing_error(exception, context)

        assert result["healing_type"] == "bulk_processing"
        assert result["success"] is True
        assert "healed_values" in result
        assert "bulk_items" in result["healed_values"]

    def test_heal_emergency_exception_always_provides_healed_values(self):
        """Regression: emergency healing must keep the `healed_values` key for callers."""
        exception = RuntimeError("boom")
        result = ExceptionHealer.heal_emergency_exception(exception)

        assert result["success"] is True
        assert "healed_values" in result
        assert isinstance(result["healed_values"], dict)

    def test_heal_operation_specific_error_failure_shape_has_healed_values(self):
        """Regression: even failure responses should include `healed_values` for stability."""
        exception = RuntimeError("not a test exception")
        result = ExceptionHealer.heal_operation_specific_error(exception, "append_entry")

        assert result["success"] is False
        assert "healed_values" in result
        assert isinstance(result["healed_values"], dict)

    def test_heal_rotation_error_permission_issues(self):
        """Test rotation error healing for permission issues."""
        exception = PermissionError("Access denied")
        context = {
            "rotation_type": "standard"
        }

        result = ExceptionHealer.heal_rotation_error(exception, context)

        assert result["healing_type"] == "rotation_operation"
        assert result["success"] is True
        assert result["rotation_completed"] is True
        assert result["method"] == "simplified"

    def test_heal_rotation_error_general_error(self):
        """Test rotation error healing for general errors."""
        exception = RuntimeError("Rotation failed")
        context = {
            "rotation_type": "custom"
        }

        result = ExceptionHealer.heal_rotation_error(exception, context)

        assert result["healing_type"] == "rotation_operation"
        assert result["success"] is True
        assert result["rotation_completed"] is True
        assert result["method"] == "emergency"

    @patch.object(ExceptionHealer, 'heal_parameter_validation_error')
    @patch.object(ExceptionHealer, 'apply_intelligent_exception_recovery')
    @patch.object(ExceptionHealer, 'heal_emergency_exception')
    def test_apply_healing_chain_level1_success(self, mock_emergency, mock_recovery, mock_validation):
        """Test healing chain success at level 1."""
        mock_validation.return_value = {
            "success": True,
            "corrections_applied": [{"parameter": "n", "original": "5", "corrected": 5}]
        }

        exception = ValueError("Invalid parameter")
        context = {
            "parameters": {"n": "5"},
            "operation_type": "read_recent"
        }

        result = ExceptionHealer.apply_healing_chain(exception, context)

        assert result["healing_chain_executed"] is True
        assert result["final_success"] is True
        assert "auto_correction" in result["healing_levels_attempted"]
        assert "Level 1 (Auto-correction): SUCCESS" in result["healing_summary"]
        mock_validation.assert_called_once()
        mock_recovery.assert_not_called()
        mock_emergency.assert_not_called()

    @patch.object(ExceptionHealer, 'heal_parameter_validation_error')
    @patch.object(ExceptionHealer, 'apply_intelligent_exception_recovery')
    @patch.object(ExceptionHealer, 'heal_emergency_exception')
    def test_apply_healing_chain_level2_success(self, mock_emergency, mock_recovery, mock_validation):
        """Test healing chain success at level 2."""
        mock_validation.return_value = {"success": False, "corrections_applied": []}
        mock_recovery.return_value = {
            "success_probability": 0.8,
            "recovery_actions": ["action1", "action2"]
        }

        exception = TypeError("Type error")
        context = {
            "parameters": {"param": "value"},
            "operation_type": "query_entries"
        }

        result = ExceptionHealer.apply_healing_chain(exception, context)

        assert result["healing_chain_executed"] is True
        assert result["final_success"] is True
        assert "auto_correction" in result["healing_levels_attempted"]
        assert "intelligent_recovery" in result["healing_levels_attempted"]
        assert "Level 1 (Auto-correction): FAILED" in result["healing_summary"]
        assert "Level 2 (Intelligent Recovery): SUCCESS" in result["healing_summary"]
        mock_validation.assert_called_once()
        mock_recovery.assert_called_once()
        mock_emergency.assert_not_called()

    @patch.object(ExceptionHealer, 'heal_parameter_validation_error')
    @patch.object(ExceptionHealer, 'apply_intelligent_exception_recovery')
    @patch.object(ExceptionHealer, 'heal_emergency_exception')
    def test_apply_healing_chain_level3_success(self, mock_emergency, mock_recovery, mock_validation):
        """Test healing chain success at level 3 (emergency)."""
        mock_validation.return_value = {"success": False, "corrections_applied": []}
        mock_recovery.return_value = {"success_probability": 0.5, "recovery_actions": []}
        mock_emergency.return_value = {"guaranteed_success": True}

        exception = RuntimeError("Critical error")
        context = {
            "parameters": {"param": "value"},
            "operation_type": "unknown"
        }

        result = ExceptionHealer.apply_healing_chain(exception, context)

        assert result["healing_chain_executed"] is True
        assert result["final_success"] is True
        assert "auto_correction" in result["healing_levels_attempted"]
        assert "intelligent_recovery" in result["healing_levels_attempted"]
        assert "emergency_fallback" in result["healing_levels_attempted"]
        assert "Level 1 (Auto-correction): FAILED" in result["healing_summary"]
        assert "Level 2 (Intelligent Recovery): ATTEMPTED" in result["healing_summary"]
        assert "Level 3 (Emergency Fallback): SUCCESS" in result["healing_summary"]
        mock_validation.assert_called_once()
        mock_recovery.assert_called_once()
        mock_emergency.assert_called_once()

    def test_helper_get_alternative_document_paths(self):
        """Test alternative document path generation helper."""
        document_path = "/path/to/document.md"

        alt_paths = ExceptionHealer._get_alternative_document_paths(document_path)

        assert len(alt_paths) == 3
        assert "/path/to/backup/document.md" in alt_paths
        assert "/path/to/old_document.md" in alt_paths
        assert "/path/to/archive_document.md" in alt_paths

    def test_helper_heal_individual_item(self):
        """Test individual item healing helper."""
        item_dict = {"id": 1, "value": "test"}
        item_error = KeyError("Missing key")

        healed_item = ExceptionHealer._heal_individual_item(item_dict, item_error)

        # Should return original item for KeyError (simple healing)
        assert healed_item == item_dict

        item_error_other = ValueError("Other error")
        healed_item_none = ExceptionHealer._heal_individual_item(item_dict, item_error_other)

        # Should return None for other errors
        assert healed_item_none is None

    def test_helper_heal_parameter_conflicts(self):
        """Test parameter conflict healing helper."""
        parameters_conflicted = {"page": -1, "page_size": 0}
        operation_type = "read_recent"

        healed_params = ExceptionHealer._heal_parameter_conflicts(parameters_conflicted, operation_type)

        assert healed_params["page"] == 1  # Should be corrected to 1
        assert healed_params["page_size"] == 50  # Should be corrected to 50

    def test_helper_heal_missing_combinations(self):
        """Test missing parameter combination healing helper."""
        parameters_missing = {"message": "test"}
        operation_type = "read_recent"

        healed_params = ExceptionHealer._heal_missing_combinations(parameters_missing, operation_type)

        assert "n" in healed_params  # Should add missing n parameter
        assert healed_params["n"] == 50  # Should add with default value


class CustomError(Exception):
    """Custom exception for testing."""
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
