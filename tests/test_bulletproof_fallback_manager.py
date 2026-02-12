#!/usr/bin/env python3
"""
Comprehensive unit tests for BulletproofFallbackManager (Task 3.4).

Tests all 4-level fallback chain functionality, operation-specific strategies,
emergency fallback guarantees, and integration with Task 3.1 and 3.3 enhancements.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock

from scribe_mcp.utils.config_manager import BulletproofFallbackManager
from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector
from scribe_mcp.utils.error_handler import ExceptionHealer


class TestBulletproofFallbackManager(unittest.TestCase):
    """Test cases for BulletproofFallbackManager class."""

    def setUp(self):
        """Set up test environment."""
        self.fallback_manager = BulletproofFallbackManager()
        self.sample_context = {
            "tool_name": "read_recent",
            "operation_type": "read_entries",
            "timestamp": "2025-01-01T00:00:00Z"
        }

    def test_initialization(self):
        """Test BulletproofFallbackManager initialization."""
        manager = BulletproofFallbackManager()

        # Verify integration components are loaded
        self.assertIsInstance(manager.parameter_corrector, BulletproofParameterCorrector)
        self.assertIsInstance(manager.exception_healer, ExceptionHealer)
        self.assertIsNotNone(manager.logger)

    def test_resolve_parameter_fallback_level1_success(self):
        """Test Level 1 intelligent correction success."""
        param_name = "message"
        invalid_value = 123  # Wrong type
        context = {"tool_name": "append_entry"}

        # Mock the parameter corrector to return a corrected value
        with patch.object(self.fallback_manager.parameter_corrector, 'correct_append_entry_parameters') as mock_correct:
            mock_correct.return_value = {param_name: "corrected_message"}

            result = self.fallback_manager.resolve_parameter_fallback(
                param_name, invalid_value, context
            )

            self.assertEqual(result, "corrected_message")
            mock_correct.assert_called_once_with({param_name: invalid_value}, context)

    def test_resolve_parameter_fallback_level2_success(self):
        """Test Level 2 context-aware fallback success."""
        param_name = "n"
        invalid_value = "invalid"
        context = {"tool_name": "read_recent"}

        # Mock Level 1 to fail
        with patch.object(self.fallback_manager, '_apply_level1_correction') as mock_level1:
            mock_level1.side_effect = Exception("Level 1 failed")

            result = self.fallback_manager.resolve_parameter_fallback(
                param_name, invalid_value, context
            )

            # Should get Level 2 context-aware fallback
            self.assertEqual(result, 20)  # read_recent context fallback for "n"

    def test_resolve_parameter_fallback_level3_success(self):
        """Test Level 3 parameter-specific fallback success."""
        param_name = "limit"
        invalid_value = "invalid"
        context = {"tool_name": "unknown_tool"}

        # Mock Level 1 and Level 2 to fail
        with patch.object(self.fallback_manager, '_apply_level1_correction') as mock_level1, \
             patch.object(self.fallback_manager, '_apply_level2_context_aware_fallback') as mock_level2:
            mock_level1.side_effect = Exception("Level 1 failed")
            mock_level2.return_value = None

            result = self.fallback_manager.resolve_parameter_fallback(
                param_name, invalid_value, context
            )

            # Should get Level 3 parameter-specific fallback
            self.assertEqual(result, 10)  # Parameter-specific fallback for "limit"

    def test_resolve_parameter_fallback_level4_emergency(self):
        """Test Level 4 emergency fallback (always succeeds)."""
        param_name = "unknown_param"
        invalid_value = "invalid"
        context = {"tool_name": "unknown_tool"}

        # Mock all levels to fail
        with patch.object(self.fallback_manager, '_apply_level1_correction') as mock_level1, \
             patch.object(self.fallback_manager, '_apply_level2_context_aware_fallback') as mock_level2, \
             patch.object(self.fallback_manager, '_apply_level3_parameter_specific_fallback') as mock_level3:
            mock_level1.side_effect = Exception("Level 1 failed")
            mock_level2.return_value = None
            mock_level3.return_value = None

            result = self.fallback_manager.resolve_parameter_fallback(
                param_name, invalid_value, context
            )

            # Should get Level 4 emergency fallback
            self.assertIsNone(result)  # Emergency fallback for unknown parameter

    def test_apply_operation_fallback_with_exception_healing(self):
        """Test operation fallback with successful exception healing."""
        failed_operation = "read_recent failed"
        context = {"tool_name": "read_recent", "exception": Exception("Test exception")}

        # Mock exception healer to succeed
        mock_healed_result = {"success": True, "result": "healed_result"}
        with patch.object(self.fallback_manager.exception_healer, 'heal_operation_specific_error') as mock_heal:
            mock_heal.return_value = mock_healed_result

            result = self.fallback_manager.apply_operation_fallback(failed_operation, context)

            self.assertTrue(result["success"])
            self.assertEqual(result["result"], "healed_result")

    def test_apply_operation_fallback_read_recent(self):
        """Test read_recent-specific operation fallback."""
        failed_operation = "read_recent operation failed"
        context = {"tool_name": "read_recent"}

        # Mock exception healing to fail
        with patch.object(self.fallback_manager.exception_healer, 'heal_operation_specific_error') as mock_heal:
            mock_heal.return_value = {"success": False}

            result = self.fallback_manager.apply_operation_fallback(failed_operation, context)

            self.assertTrue(result["ok"])
            self.assertEqual(result["operation"], "read_recent_fallback")
            self.assertIn("result", result)
            self.assertTrue(result["fallback_applied"])

    def test_apply_operation_fallback_query_entries(self):
        """Test query_entries-specific operation fallback."""
        failed_operation = "query_entries operation failed"
        context = {"tool_name": "query_entries"}

        # Mock exception healing to fail
        with patch.object(self.fallback_manager.exception_healer, 'heal_operation_specific_error') as mock_heal:
            mock_heal.return_value = {"success": False}

            result = self.fallback_manager.apply_operation_fallback(failed_operation, context)

            self.assertTrue(result["ok"])
            self.assertEqual(result["operation"], "query_entries_fallback")
            self.assertIn("entries", result["result"])
            self.assertEqual(result["result"]["total_count"], 0)

    def test_apply_operation_fallback_manage_docs(self):
        """Test manage_docs-specific operation fallback."""
        failed_operation = "manage_docs operation failed"
        context = {"tool_name": "manage_docs"}

        # Mock exception healing to fail
        with patch.object(self.fallback_manager.exception_healer, 'heal_operation_specific_error') as mock_heal:
            mock_heal.return_value = {"success": False}

            result = self.fallback_manager.apply_operation_fallback(failed_operation, context)

            self.assertTrue(result["ok"])
            self.assertEqual(result["operation"], "manage_docs_fallback")
            self.assertEqual(result["result"]["status"], "completed")

    def test_apply_operation_fallback_append_entry(self):
        """Test append_entry-specific operation fallback."""
        failed_operation = "append_entry operation failed"
        context = {"tool_name": "append_entry"}

        # Mock exception healing to fail
        with patch.object(self.fallback_manager.exception_healer, 'heal_operation_specific_error') as mock_heal:
            mock_heal.return_value = {"success": False}

            result = self.fallback_manager.apply_operation_fallback(failed_operation, context)

            self.assertTrue(result["ok"])
            self.assertEqual(result["operation"], "append_entry_fallback")
            self.assertIn("entry_id", result["result"])
            self.assertEqual(result["result"]["status"], "success")

    def test_apply_operation_fallback_rotate_log(self):
        """Test rotate_log-specific operation fallback."""
        failed_operation = "rotate_log operation failed"
        context = {"tool_name": "rotate_log"}

        # Mock exception healing to fail
        with patch.object(self.fallback_manager.exception_healer, 'heal_operation_specific_error') as mock_heal:
            mock_heal.return_value = {"success": False}

            result = self.fallback_manager.apply_operation_fallback(failed_operation, context)

            self.assertTrue(result["ok"])
            self.assertEqual(result["operation"], "rotate_log_fallback")
            self.assertEqual(result["result"]["files_rotated"], 0)

    def test_apply_operation_fallback_generic(self):
        """Test generic operation fallback for unknown tools."""
        failed_operation = "unknown_tool operation failed"
        context = {"tool_name": "unknown_tool"}

        # Mock exception healing to fail
        with patch.object(self.fallback_manager.exception_healer, 'heal_operation_specific_error') as mock_heal:
            mock_heal.return_value = {"success": False}

            result = self.fallback_manager.apply_operation_fallback(failed_operation, context)

            self.assertTrue(result["ok"])
            self.assertEqual(result["operation"], "generic_fallback")
            self.assertIn(failed_operation, result["result"]["message"])

    def test_emergency_fallback(self):
        """Test emergency fallback returns guaranteed success."""
        context = {
            "tool_name": "read_recent",
            "timestamp": "2025-01-01T00:00:00Z"
        }

        result = self.fallback_manager.emergency_fallback(context)

        self.assertTrue(result["ok"])
        self.assertEqual(result["fallback_applied"], "emergency")
        self.assertEqual(result["tool_name"], "read_recent")
        self.assertIn("result", result)
        self.assertIn("reminders", result)
        self.assertEqual(len(result["reminders"]), 1)
        self.assertEqual(result["reminders"][0]["level"], "warn")

    def test_emergency_fallback_all_tools(self):
        """Test emergency fallback works for all supported tools."""
        tools = ["read_recent", "query_entries", "manage_docs", "append_entry", "rotate_log", "unknown"]

        for tool_name in tools:
            context = {"tool_name": tool_name}
            result = self.fallback_manager.emergency_fallback(context)

            self.assertTrue(result["ok"], f"Emergency fallback failed for {tool_name}")
            self.assertEqual(result["fallback_applied"], "emergency")
            self.assertEqual(result["tool_name"], tool_name)
            self.assertIn("result", result)

    def test_intelligent_parameter_resolution(self):
        """Test intelligent parameter resolution with multiple parameters."""
        params = {
            "invalid_param": "invalid_value",
            "n": "invalid_number",
            "status": 123
        }
        operation_context = "read_recent operation"

        # Mock parameter fallback to avoid circular dependencies
        with patch.object(self.fallback_manager, 'resolve_parameter_fallback') as mock_resolve:
            mock_resolve.side_effect = ["corrected_invalid", 20, "info"]

            result = self.fallback_manager.intelligent_parameter_resolution(
                params, operation_context
            )

            self.assertEqual(result["invalid_param"], "corrected_invalid")
            self.assertEqual(result["n"], 20)
            self.assertEqual(result["status"], "info")
            self.assertEqual(mock_resolve.call_count, 3)

    def test_intelligent_parameter_resolution_with_exception(self):
        """Test intelligent parameter resolution handles exceptions gracefully."""
        params = {
            "param1": "value1",
            "param2": "value2"
        }
        operation_context = "unknown_tool operation"

        # Mock parameter fallback to raise exception for first param
        with patch.object(self.fallback_manager, 'resolve_parameter_fallback') as mock_resolve, \
             patch.object(self.fallback_manager, '_apply_level4_emergency_fallback') as mock_emergency:

            mock_resolve.side_effect = [Exception("Failed"), "corrected_value"]
            mock_emergency.return_value = "emergency_value"

            result = self.fallback_manager.intelligent_parameter_resolution(
                params, operation_context
            )

            self.assertEqual(result["param1"], "emergency_value")
            self.assertEqual(result["param2"], "corrected_value")

    def test_generate_emergency_content_read_recent(self):
        """Test emergency content generation for read_recent."""
        tool_name = "read_recent"
        context = {}

        result = self.fallback_manager.generate_emergency_content(tool_name, context)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "emergency_fallback")
        self.assertEqual(result[0]["status"], "info")

    def test_generate_emergency_content_query_entries(self):
        """Test emergency content generation for query_entries."""
        tool_name = "query_entries"
        context = {}

        result = self.fallback_manager.generate_emergency_content(tool_name, context)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_count"], 0)
        self.assertIn("page_info", result)
        self.assertTrue(result["fallback_applied"])

    def test_generate_emergency_content_manage_docs(self):
        """Test emergency content generation for manage_docs."""
        tool_name = "manage_docs"
        context = {}

        result = self.fallback_manager.generate_emergency_content(tool_name, context)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "completed")
        self.assertIn("message", result)

    def test_generate_emergency_content_append_entry(self):
        """Test emergency content generation for append_entry."""
        tool_name = "append_entry"
        context = {}

        result = self.fallback_manager.generate_emergency_content(tool_name, context)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "success")
        self.assertIn("entry_id", result)
        self.assertTrue(result["entry_id"].startswith("emergency_fallback_"))

    def test_generate_emergency_content_rotate_log(self):
        """Test emergency content generation for rotate_log."""
        tool_name = "rotate_log"
        context = {}

        result = self.fallback_manager.generate_emergency_content(tool_name, context)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["files_rotated"], 0)

    def test_generate_emergency_content_unknown_tool(self):
        """Test emergency content generation for unknown tool."""
        tool_name = "unknown_tool"
        context = {}

        result = self.fallback_manager.generate_emergency_content(tool_name, context)

        self.assertIsInstance(result, dict)
        self.assertTrue(result["emergency_fallback"])
        self.assertEqual(result["tool_name"], tool_name)

    def test_apply_context_aware_defaults_read_recent(self):
        """Test context-aware defaults for read_recent."""
        params = {}
        tool_name = "read_recent"
        operation_type = "read_entries"

        result = self.fallback_manager.apply_context_aware_defaults(
            params, tool_name, operation_type
        )

        self.assertEqual(result["n"], 20)
        self.assertFalse(result["compact"])
        self.assertFalse(result["include_metadata"])
        self.assertEqual(result["fields"], ["message", "status", "agent"])

    def test_apply_context_aware_defaults_query_entries(self):
        """Test context-aware defaults for query_entries."""
        params = {"max_results": 100}  # Override one default
        tool_name = "query_entries"
        operation_type = "search"

        result = self.fallback_manager.apply_context_aware_defaults(
            params, tool_name, operation_type
        )

        self.assertEqual(result["search_scope"], "project")
        self.assertEqual(result["document_types"], ["progress"])
        self.assertEqual(result["relevance_threshold"], 0.5)
        self.assertEqual(result["max_results"], 100)  # Preserved override
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 20)

    def test_apply_context_aware_defaults_manage_docs(self):
        """Test context-aware defaults for manage_docs."""
        params = {}
        tool_name = "manage_docs"
        operation_type = "update_document"

        result = self.fallback_manager.apply_context_aware_defaults(
            params, tool_name, operation_type
        )

        self.assertEqual(result["action"], "status_update")
        self.assertEqual(result["doc"], "checklist")
        self.assertEqual(result["section"], "general")
        self.assertEqual(result["metadata"], {})

    def test_apply_context_aware_defaults_append_entry(self):
        """Test context-aware defaults for append_entry."""
        params = {"message": "Custom message"}  # Override one default
        tool_name = "append_entry"
        operation_type = "create_entry"

        result = self.fallback_manager.apply_context_aware_defaults(
            params, tool_name, operation_type
        )

        self.assertEqual(result["message"], "Custom message")  # Preserved override
        self.assertEqual(result["status"], "info")
        self.assertEqual(result["emoji"], "📝")
        self.assertEqual(result["agent"], "Scribe")
        self.assertEqual(result["meta"], {})
        self.assertEqual(result["log_type"], "progress")

    def test_apply_context_aware_defaults_rotate_log(self):
        """Test context-aware defaults for rotate_log."""
        params = {}
        tool_name = "rotate_log"
        operation_type = "rotate"

        result = self.fallback_manager.apply_context_aware_defaults(
            params, tool_name, operation_type
        )

        self.assertFalse(result["confirm"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["suffix"], "")
        self.assertEqual(result["log_type"], "progress")
        self.assertEqual(result["threshold_entries"], 500)

    def test_context_aware_fallback_methods(self):
        """Test all context-aware fallback methods."""
        test_cases = [
            ("_get_read_recent_context_fallback", "n", 20),
            ("_get_query_entries_context_fallback", "search_scope", "project"),
            ("_get_manage_docs_context_fallback", "action", "status_update"),
            ("_get_append_entry_context_fallback", "message", "Log entry created"),
            ("_get_rotate_log_context_fallback", "confirm", False)
        ]

        for method_name, param_name, expected_value in test_cases:
            method = getattr(self.fallback_manager, method_name)
            result = method(param_name, {"tool_name": "test_tool"})
            self.assertEqual(result, expected_value, f"Failed for {method_name}")

    def test_parameter_specific_fallback_patterns(self):
        """Test parameter-specific fallback patterns."""
        test_cases = [
            ("limit", 10),
            ("count", 10),
            ("page", 1),
            ("status", "info"),
            ("agent", "Scribe"),
            ("message", "Operation completed"),
            ("format", "compact"),
            ("sort", "desc"),
            ("scope", "project"),
            ("unknown_param", None)
        ]

        for param_name, expected_value in test_cases:
            result = self.fallback_manager._apply_level3_parameter_specific_fallback(
                param_name, "invalid_value", {}
            )
            self.assertEqual(result, expected_value, f"Failed for {param_name}")

    def test_emergency_fallback_patterns(self):
        """Test emergency fallback type patterns."""
        test_cases = [
            ("enabled_param", False),
            ("bool_setting", False),
            ("limit_param", 1),
            ("count_param", 1),
            ("name_param", ""),
            ("message_param", ""),
            ("items_param", []),
            ("entries_param", []),
            ("config_param", {}),
            ("meta_param", {}),
            ("unknown_param", None)
        ]

        for param_name, expected_value in test_cases:
            result = self.fallback_manager._apply_level4_emergency_fallback(
                param_name, "invalid_value", {}
            )
            self.assertEqual(result, expected_value, f"Failed for {param_name}")

    def test_integration_with_task31_enhancements(self):
        """Test integration with Task 3.1 BulletproofParameterCorrector."""
        context = {"tool_name": "read_recent"}

        # Test that Level 1 correction uses BulletproofParameterCorrector
        with patch.object(self.fallback_manager.parameter_corrector, 'correct_read_recent_parameters') as mock_correct:
            mock_correct.return_value = {"n": "corrected_value"}

            result = self.fallback_manager.resolve_parameter_fallback(
                "n", "invalid", context
            )

            mock_correct.assert_called_once_with({"n": "invalid"}, context)
            self.assertEqual(result, "corrected_value")

    def test_integration_with_task33_enhancements(self):
        """Test integration with Task 3.3 ExceptionHealer."""
        context = {
            "tool_name": "read_recent",
            "exception": Exception("Test exception")
        }

        # Test that operation fallback uses ExceptionHealer
        with patch.object(self.fallback_manager.exception_healer, 'heal_operation_specific_error') as mock_heal:
            mock_heal.return_value = {"success": True, "result": "healed"}

            result = self.fallback_manager.apply_operation_fallback(
                "failed_operation", context
            )

            mock_heal.assert_called_once()
            self.assertTrue(result["success"])

    def test_four_level_fallback_chain_integration(self):
        """Test complete 4-level fallback chain integration."""
        # Test scenario where each level fails until emergency
        param_name = "test_param"
        invalid_value = "invalid"
        context = {"tool_name": "unknown_tool"}

        with patch.object(self.fallback_manager, '_apply_level1_correction') as mock_l1, \
             patch.object(self.fallback_manager, '_apply_level2_context_aware_fallback') as mock_l2, \
             patch.object(self.fallback_manager, '_apply_level3_parameter_specific_fallback') as mock_l3:

            mock_l1.side_effect = Exception("Level 1 failed")
            mock_l2.return_value = None
            mock_l3.return_value = None

            result = self.fallback_manager.resolve_parameter_fallback(
                param_name, invalid_value, context
            )

            # Should reach Level 4 emergency fallback
            self.assertIsNone(result)
            mock_l1.assert_called_once()
            mock_l2.assert_called_once()
            mock_l3.assert_called_once()

    def test_zero_failure_guarantee(self):
        """Test that zero-failure guarantee is maintained."""
        # Test various failure scenarios
        test_scenarios = [
            # Parameter resolution failures
            lambda: self.fallback_manager.resolve_parameter_fallback("invalid", "invalid", {"tool_name": "unknown"}),
            # Operation fallback failures
            lambda: self.fallback_manager.apply_operation_fallback("invalid_operation", {"tool_name": "unknown"}),
            # Emergency fallback
            lambda: self.fallback_manager.emergency_fallback({"tool_name": "unknown"}),
            # Intelligent parameter resolution
            lambda: self.fallback_manager.intelligent_parameter_resolution({"invalid": "invalid"}, "unknown operation"),
            # Emergency content generation
            lambda: self.fallback_manager.generate_emergency_content("unknown", {}),
            # Context-aware defaults
            lambda: self.fallback_manager.apply_context_aware_defaults({}, "unknown", "operation")
        ]

        for scenario in test_scenarios:
            try:
                result = scenario()
                # All scenarios should return some result without raising exceptions
                self.assertIsNotNone(result)
            except Exception as e:
                self.fail(f"Zero-failure guarantee violated: {e}")

    def test_backward_compatibility(self):
        """Test backward compatibility with existing interfaces."""
        # Test that the class can be instantiated and used without breaking
        manager = BulletproofFallbackManager()

        # Test basic functionality
        self.assertIsNotNone(manager.resolve_parameter_fallback("test", "value", {}))
        self.assertIsNotNone(manager.apply_operation_fallback("test", {}))
        self.assertIsNotNone(manager.emergency_fallback({}))
        self.assertIsNotNone(manager.intelligent_parameter_resolution({}, "test"))
        self.assertIsNotNone(manager.generate_emergency_content("test", {}))
        self.assertIsNotNone(manager.apply_context_aware_defaults({}, "test", "operation"))

        # All should work without exceptions
        self.assertTrue(True)


class TestBulletproofFallbackManagerPerformance(unittest.TestCase):
    """Performance tests for BulletproofFallbackManager."""

    def setUp(self):
        """Set up performance test environment."""
        self.fallback_manager = BulletproofFallbackManager()

    def test_parameter_resolution_performance(self):
        """Test parameter resolution performance."""
        import time

        # Test with multiple parameters
        params = {f"param_{i}": f"invalid_value_{i}" for i in range(100)}

        start_time = time.time()
        result = self.fallback_manager.intelligent_parameter_resolution(
            params, "performance_test_operation"
        )
        end_time = time.time()

        # Should complete within reasonable time (<1 second for 100 parameters)
        self.assertLess(end_time - start_time, 1.0)
        self.assertEqual(len(result), 100)

    def test_operation_fallback_performance(self):
        """Test operation fallback performance."""
        import time

        operations = [f"operation_{i}" for i in range(50)]
        context = {"tool_name": "performance_test_tool"}

        start_time = time.time()
        results = []
        for operation in operations:
            result = self.fallback_manager.apply_operation_fallback(operation, context)
            results.append(result)
        end_time = time.time()

        # Should complete within reasonable time (<1 second for 50 operations)
        self.assertLess(end_time - start_time, 1.0)
        self.assertEqual(len(results), 50)
        for result in results:
            self.assertTrue(result["ok"])


if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)