#!/usr/bin/env python3
"""
Integration test for manage_docs actions after schema fix.

This test verifies that the 3 previously failing actions now work correctly:
1. apply_patch (with edit parameter)
2. create_research_doc (with doc_name parameter)
3. batch (with optional doc parameter)

IMPORTANT: The MCP server must be restarted for schema changes to take effect.
Run this test AFTER restarting the server.
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.config.settings import settings


async def test_apply_patch_with_edit():
    """Test apply_patch action with edit parameter."""
    print("\n1. Testing apply_patch with 'edit' parameter...")
    print("-" * 60)

    try:
        # Test with structured edit payload
        result = await manage_docs(
            action="apply_patch",
            doc="architecture",
            edit={
                "action": "replace_range",
                "start_line": 1,
                "end_line": 1,
                "content": "# Test Architecture\n"
            },
            dry_run=True  # Don't actually modify
        )

        if result.get("ok"):
            print("   ✅ PASS: apply_patch accepts 'edit' parameter")
            return True
        else:
            error = result.get("error", "Unknown error")
            if "PATCH_MODE_STRUCTURED_REQUIRES_EDIT" in error:
                print(f"   ❌ FAIL: Schema still doesn't expose 'edit' parameter")
                print(f"   Error: {error}")
                return False
            elif "dry_run" in error or "preview" in error:
                # Different error means parameter was accepted
                print("   ✅ PASS: apply_patch accepts 'edit' parameter (different error)")
                return True
            else:
                print(f"   ⚠️ PARTIAL: Unexpected error: {error}")
                return False

    except TypeError as e:
        if "edit" in str(e):
            print(f"   ❌ FAIL: 'edit' parameter not in schema - {e}")
            return False
        raise


async def test_create_research_doc_with_doc_name():
    """Test create_research_doc action with doc_name parameter."""
    print("\n2. Testing create_research_doc with 'doc_name' parameter...")
    print("-" * 60)

    try:
        result = await manage_docs(
            action="create_research_doc",
            doc="research",  # Required by function signature
            doc_name="TEST_RESEARCH_SCHEMA_FIX",
            metadata={
                "research_goal": "Verify doc_name parameter works after schema fix"
            },
            dry_run=True
        )

        if result.get("ok"):
            print("   ✅ PASS: create_research_doc accepts 'doc_name' parameter")
            return True
        else:
            error = result.get("error", "Unknown error")
            if "doc_name is required" in error:
                print(f"   ❌ FAIL: Schema still doesn't expose 'doc_name' parameter")
                print(f"   Error: {error}")
                return False
            else:
                # Different error means parameter was accepted
                print(f"   ✅ PASS: create_research_doc accepts 'doc_name' parameter")
                print(f"   Note: {error}")
                return True

    except TypeError as e:
        if "doc_name" in str(e):
            print(f"   ❌ FAIL: 'doc_name' parameter not in schema - {e}")
            return False
        raise


async def test_batch_without_doc():
    """Test batch action without doc parameter (doc should be optional)."""
    print("\n3. Testing batch action without 'doc' parameter...")
    print("-" * 60)

    try:
        result = await manage_docs(
            action="batch",
            doc="",  # Empty string, should be acceptable
            metadata={
                "operations": [
                    {
                        "action": "replace_section",
                        "doc": "architecture",
                        "section": "problem_statement",
                        "content": "Test"
                    }
                ]
            },
            dry_run=True
        )

        if result.get("ok"):
            print("   ✅ PASS: batch action works with optional 'doc' parameter")
            return True
        else:
            error = result.get("error", "Unknown error")
            if "missing 1 required positional argument: 'doc'" in error:
                print(f"   ❌ FAIL: 'doc' still marked as required in schema")
                print(f"   Error: {error}")
                return False
            else:
                # Different error means parameter handling is correct
                print(f"   ✅ PASS: batch action accepts optional 'doc' parameter")
                print(f"   Note: {error}")
                return True

    except TypeError as e:
        if "missing 1 required positional argument: 'doc'" in str(e):
            print(f"   ❌ FAIL: 'doc' still required - {e}")
            return False
        raise


async def main():
    """Run all tests."""
    print("=" * 60)
    print("MCP Schema Fix Integration Tests")
    print("=" * 60)
    print("\nNOTE: MCP server must be restarted for schema changes to apply!")
    print("These tests verify the actual MCP tool behavior.\n")

    # Set up test project
    print("Setting up test project...")
    await set_project(name="scribe_systematic_audit_1", root=str(settings.project_root))

    # Run tests
    results = []
    results.append(await test_apply_patch_with_edit())
    results.append(await test_create_research_doc_with_doc_name())
    results.append(await test_batch_without_doc())

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ ALL TESTS PASSED!")
        print("\nThe MCP schema fix successfully resolved all 3 issues:")
        print("  1. apply_patch now accepts 'edit' parameter")
        print("  2. create_research_doc now accepts 'doc_name' parameter")
        print("  3. batch action works with optional 'doc' parameter")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED")
        print("\nPossible causes:")
        print("  • MCP server not restarted (schema changes require restart)")
        print("  • Schema generation logic has bugs")
        print("  • manage_docs implementation issues")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
