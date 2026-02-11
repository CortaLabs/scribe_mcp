#!/usr/bin/env python3
"""Simple test for dual parameter logic.

This test validates the core dual parameter functionality.
"""

import sys
from pathlib import Path

# Add the MCP_SPINE directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.tools.config.append_entry_config import AppendEntryConfig


def test_dual_parameter_simple():
    """Test the core dual parameter logic."""

    print("🧪 Testing dual parameter logic...")

    # Test 1: Legacy parameters create config correctly
    print("   📋 Test 1: Legacy parameter conversion")
    try:
        config = AppendEntryConfig.from_legacy_params(
            message="Test legacy",
            status="info",
            agent="LegacyAgent"
        )
        assert config.message == "Test legacy"
        assert config.status == "info"
        assert config.agent == "LegacyAgent"
        print("      ✅ Legacy parameter conversion works")
    except Exception as e:
        print(f"      ❌ Legacy conversion test failed: {e}")
        raise

    # Test 2: Config object creation
    print("   📋 Test 2: Config object creation")
    try:
        config = AppendEntryConfig(
            message="Test config",
            status="success",
            agent="ConfigAgent"
        )
        assert config.message == "Test config"
        assert config.status == "success"
        assert config.agent == "ConfigAgent"
        print("      ✅ Config object creation works")
    except Exception as e:
        print(f"      ❌ Config creation test failed: {e}")
        raise

    # Test 3: Dict conversion and merging
    print("   📋 Test 3: Dict conversion and merging")
    try:
        # Base config
        base_config = AppendEntryConfig(
            message="Base message",
            status="warn",
            agent="BaseAgent"
        )

        # Override config (simulating legacy params)
        override_config = AppendEntryConfig.from_legacy_params(
            message="Override message",  # This should override
            status="error",             # This should override
            agent="OverrideAgent"       # This should override
        )

        # Manual merge (simplified version of append_entry logic)
        base_dict = base_config.to_dict()
        override_dict = override_config.to_dict()

        # Apply overrides
        for key, value in override_dict.items():
            if value is not None or key in ['message']:
                base_dict[key] = value

        merged_config = AppendEntryConfig(**base_dict)

        # Verify overrides took effect
        assert merged_config.message == "Override message"
        assert merged_config.status == "error"
        assert merged_config.agent == "OverrideAgent"
        print("      ✅ Dict conversion and merging works")
    except Exception as e:
        print(f"      ❌ Dict merging test failed: {e}")
        raise

    # Test 4: Bulk mode detection
    print("   📋 Test 4: Bulk mode detection")
    try:
        # Single entry mode
        config1 = AppendEntryConfig(message="Single entry")
        assert config1.is_bulk_mode() == False

        # Bulk mode with items_list
        config2 = AppendEntryConfig(
            items_list=[
                {"message": "Item 1"},
                {"message": "Item 2"}
            ]
        )
        assert config2.is_bulk_mode() == True

        print("      ✅ Bulk mode detection works")
    except Exception as e:
        print(f"      ❌ Bulk mode test failed: {e}")
        raise

    # Test 5: Empty string handling
    print("   📋 Test 5: Empty string handling")
    try:
        # Empty message with config override
        base_config = AppendEntryConfig(message="Base message")
        override_config = AppendEntryConfig.from_legacy_params(message="")

        base_dict = base_config.to_dict()
        override_dict = override_config.to_dict()

        # Apply override logic
        for key, value in override_dict.items():
            if value is not None or key in ['message']:
                base_dict[key] = value

        merged_config = AppendEntryConfig(**base_dict)

        # Empty string should override because of the 'message' special case
        assert merged_config.message == ""
        print("      ✅ Empty string handling works")
    except Exception as e:
        print(f"      ❌ Empty string test failed: {e}")
        raise

    print("✅ All simple dual parameter tests passed!")


def main():
    """Run simple tests."""
    print("🚀 Phase 2 Task 2.4 - Simple Dual Parameter Tests")
    print("=" * 60)

    test_dual_parameter_simple()
    success = True

    if success:
        print("\n🎉 Simple dual parameter tests passed!")
        print("   • Legacy parameter conversion: ✅")
        print("   • Config object creation: ✅")
        print("   • Dict conversion and merging: ✅")
        print("   • Bulk mode detection: ✅")
        print("   • Empty string handling: ✅")
    else:
        print("\n❌ Simple tests failed!")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)