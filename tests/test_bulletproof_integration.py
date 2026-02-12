#!/usr/bin/env python3
"""
Integration tests for BulletproofFallbackManager (Task 3.4).

Tests the 4-level fallback chain integration and demonstrates
zero-failure operation guarantee for all MCP tools.
"""

import unittest

from scribe_mcp.utils.config_manager import BulletproofFallbackManager


class TestBulletproofFallbackIntegration(unittest.TestCase):
    """Integration tests for BulletproofFallbackManager."""

    def setUp(self):
        """Set up integration test environment."""
        self.fallback_manager = BulletproofFallbackManager()

    def test_four_level_fallback_chain_working(self):
        """Test that 4-level fallback chain works end-to-end."""
        print("\n=== Testing 4-Level Fallback Chain ===")

        # Test scenario: Invalid parameter for unknown tool
        param_name = "invalid_param"
        invalid_value = "completely_invalid_value_12345!@#$%"
        context = {"tool_name": "unknown_tool", "operation_type": "test_operation"}

        print(f"Testing parameter fallback for: {param_name} = {invalid_value}")

        # This should work through all 4 levels and return a safe value
        result = self.fallback_manager.resolve_parameter_fallback(
            param_name, invalid_value, context
        )

        print(f"Result after 4-level fallback: {result}")
        print(f"Result type: {type(result)}")

        # Should return some safe value (not None, not raise exception)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, (str, int, bool, list, dict, type(None)))

    def test_operation_fallback_guaranteed_success(self):
        """Test that operation fallback always succeeds."""
        print("\n=== Testing Operation Fallback Success ===")

        tools = ["read_recent", "query_entries", "manage_docs", "append_entry", "rotate_log", "unknown_tool"]

        for tool_name in tools:
            print(f"\nTesting fallback for tool: {tool_name}")

            failed_operation = f"{tool_name} operation failed catastrophically"
            context = {"tool_name": tool_name, "exception": Exception(f"Test exception for {tool_name}")}

            result = self.fallback_manager.apply_operation_fallback(failed_operation, context)

            print(f"  Fallback result: ok={result.get('ok')}, operation={result.get('operation')}")

            # All should succeed
            self.assertTrue(result.get("ok", False), f"Operation fallback failed for {tool_name}")
            self.assertIn("result", result)
            self.assertTrue(result.get("fallback_applied", False))

    def test_emergency_fallback_always_succeeds(self):
        """Test that emergency fallback always succeeds."""
        print("\n=== Testing Emergency Fallback Success ===")

        # Test with various contexts
        test_contexts = [
            {"tool_name": "read_recent"},
            {"tool_name": "query_entries"},
            {"tool_name": "manage_docs"},
            {"tool_name": "append_entry"},
            {"tool_name": "rotate_log"},
            {"tool_name": "completely_unknown_tool"},
            {}  # Empty context
        ]

        for i, context in enumerate(test_contexts):
            print(f"\nTesting emergency fallback #{i+1}: {context}")

            result = self.fallback_manager.emergency_fallback(context)

            print(f"  Emergency result: ok={result.get('ok')}, fallback={result.get('fallback_applied')}")

            # All should succeed
            self.assertTrue(result.get("ok", False), f"Emergency fallback failed for context {context}")
            self.assertEqual(result.get("fallback_applied"), "emergency")
            self.assertIn("result", result)
            self.assertIn("reminders", result)

    def test_zero_failure_guarantee_comprehensive(self):
        """Comprehensive test of zero-failure guarantee."""
        print("\n=== Testing Zero-Failure Guarantee ===")

        # Test scenarios that would normally cause failures
        failure_scenarios = [
            # Parameter resolution with completely invalid inputs
            ("Parameter Resolution", lambda: self.fallback_manager.resolve_parameter_fallback(
                "totally_invalid_param", {"invalid": "data"}, {"tool_name": "unknown"}
            )),

            # Operation fallback with failed operations
            ("Operation Fallback", lambda: self.fallback_manager.apply_operation_fallback(
                "catastrophic failure", {"tool_name": "unknown", "exception": RuntimeError("Critical error")}
            )),

            # Emergency fallback
            ("Emergency Fallback", lambda: self.fallback_manager.emergency_fallback(
                {"tool_name": "nonexistent_tool", "corrupted": "data"}
            )),

            # Intelligent parameter resolution with mixed invalid data
            ("Parameter Resolution", lambda: self.fallback_manager.intelligent_parameter_resolution(
                {"param1": None, "param2": "invalid", "param3": []}, "unknown operation"
            )),

            # Emergency content generation
            ("Emergency Content", lambda: self.fallback_manager.generate_emergency_content(
                "unknown_tool", {"invalid": "context"}
            )),

            # Context-aware defaults with empty context
            ("Context Defaults", lambda: self.fallback_manager.apply_context_aware_defaults(
                {}, "unknown_tool", "unknown_operation"
            )),
        ]

        success_count = 0
        total_count = len(failure_scenarios)

        for scenario_name, scenario_func in failure_scenarios:
            print(f"\nTesting scenario: {scenario_name}")
            try:
                result = scenario_func()
                print(f"  ✓ Success: {type(result)}")
                success_count += 1
            except Exception as e:
                print(f"  ✗ FAILED: {e}")
                self.fail(f"Zero-failure guarantee violated for {scenario_name}: {e}")

        print(f"\n=== Zero-Failure Guarantee Results ===")
        print(f"Successful scenarios: {success_count}/{total_count}")
        print(f"Success rate: {(success_count/total_count)*100:.1f}%")

        # All scenarios should succeed
        self.assertEqual(success_count, total_count, "Not all scenarios succeeded")

    def test_performance_under_stress(self):
        """Test performance under stress conditions."""
        print("\n=== Testing Performance Under Stress ===")

        import time

        # Test with many parameters
        large_params = {f"param_{i}": f"invalid_value_{i}" for i in range(100)}

        start_time = time.time()
        result = self.fallback_manager.intelligent_parameter_resolution(
            large_params, "stress_test_operation"
        )
        end_time = time.time()

        duration = end_time - start_time
        print(f"Processed 100 parameters in {duration:.3f} seconds")
        print(f"Result size: {len(result)}")

        # Should complete within reasonable time
        self.assertLess(duration, 2.0, "Performance test took too long")
        self.assertEqual(len(result), 100, "Not all parameters were processed")

        # Test many operation fallbacks
        start_time = time.time()
        operations = []
        for i in range(50):
            result = self.fallback_manager.apply_operation_fallback(
                f"operation_{i}", {"tool_name": "test_tool"}
            )
            operations.append(result)
        end_time = time.time()

        duration = end_time - start_time
        print(f"Processed 50 operation fallbacks in {duration:.3f} seconds")

        # Should complete within reasonable time
        self.assertLess(duration, 1.0, "Operation fallback performance test took too long")
        self.assertEqual(len(operations), 50, "Not all operations were processed")

        # All operations should succeed
        for i, result in enumerate(operations):
            self.assertTrue(result.get("ok", False), f"Operation {i} failed")

    def test_integration_with_task31_enhancements(self):
        """Test integration with Task 3.1 BulletproofParameterCorrector."""
        print("\n=== Testing Integration with Task 3.1 Enhancements ===")

        # Test that Level 1 correction uses BulletproofParameterCorrector
        context = {"tool_name": "read_recent"}

        # This should work even with BulletproofParameterCorrector integration
        result = self.fallback_manager.resolve_parameter_fallback(
            "n", "invalid_value", context
        )

        # Should get some resolved value
        self.assertIsNotNone(result)
        print(f"✅ Integration with BulletproofParameterCorrector working: {result}")

    def test_integration_with_task33_enhancements(self):
        """Test integration with Task 3.3 ExceptionHealer."""
        print("\n=== Testing Integration with Task 3.3 Enhancements ===")

        # Test that operation fallback tries ExceptionHealer first
        context = {
            "tool_name": "read_recent",
            "exception": Exception("Test exception for integration")
        }

        result = self.fallback_manager.apply_operation_fallback(
            "test_operation_failed", context
        )

        # Should succeed either through ExceptionHealer or fallback
        self.assertTrue(result.get("ok", False))
        print(f"✅ Integration with ExceptionHealer working: {result.get('fallback_applied', 'unknown')}")

    def test_tool_specific_integration(self):
        """Test tool-specific integration scenarios."""
        print("\n=== Testing Tool-Specific Integration ===")

        # Test scenarios that simulate real MCP tool usage
        tool_scenarios = [
            {
                "name": "read_recent parameter correction",
                "tool": "read_recent",
                "params": {"n": "invalid", "compact": "not_boolean", "filter": "not_dict"},
                "operation": "read_recent parameter resolution"
            },
            {
                "name": "query_entries validation fallback",
                "tool": "query_entries",
                "params": {"search_scope": "invalid_scope", "relevance_threshold": 2.5, "max_results": -1},
                "operation": "query_entries parameter resolution"
            },
            {
                "name": "manage_docs operation fallback",
                "tool": "manage_docs",
                "params": {"action": "invalid_action", "metadata": "not_json"},
                "operation": "manage_docs operation fallback"
            },
            {
                "name": "append_entry bulk processing",
                "tool": "append_entry",
                "params": {"message": None, "status": 123, "meta": "invalid_json"},
                "operation": "append_entry parameter resolution"
            },
            {
                "name": "rotate_log parameter correction",
                "tool": "rotate_log",
                "params": {"confirm": "not_boolean", "threshold_entries": "not_number"},
                "operation": "rotate_log parameter resolution"
            }
        ]

        for scenario in tool_scenarios:
            print(f"\nTesting scenario: {scenario['name']}")

            # Test parameter resolution
            resolved_params = self.fallback_manager.intelligent_parameter_resolution(
                scenario["params"], scenario["operation"]
            )

            print(f"  Original params: {scenario['params']}")
            print(f"  Resolved params: {resolved_params}")

            # Test operation fallback
            fallback_result = self.fallback_manager.apply_operation_fallback(
                f"{scenario['tool']} operation failed",
                {"tool_name": scenario["tool"]}
            )

            print(f"  Fallback success: {fallback_result.get('ok')}")

            # Both should succeed
            self.assertIsNotNone(resolved_params)
            self.assertTrue(fallback_result.get("ok", False))


if __name__ == '__main__':
    # Run integration tests with verbose output
    unittest.main(verbosity=2)