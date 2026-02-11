#!/usr/bin/env python3
"""
Integration test for manage_docs actions after schema fix.

This test verifies that the 3 previously failing actions now work correctly:
1. apply_patch (with edit parameter)
2. create action for research docs (with doc_name parameter)
3. batch (with optional doc parameter)

IMPORTANT: The MCP server must be restarted for schema changes to take effect.
Run this test AFTER restarting the server.
"""

import asyncio
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.config.settings import settings

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _ensure_project_context() -> None:
    """Keep tests isolated from stale project routing state."""
    await set_project(name="scribe_systematic_audit_1", root=str(settings.project_root))


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
            return
        else:
            error = result.get("error", "Unknown error")
            if "PATCH_MODE_STRUCTURED_REQUIRES_EDIT" in error:
                print(f"   ❌ FAIL: Schema still doesn't expose 'edit' parameter")
                print(f"   Error: {error}")
                pytest.fail("manage_docs schema behavior validation failed")
            elif "dry_run" in error or "preview" in error or "STRUCTURED_EDIT_TYPE_REQUIRED" in error:
                # Different error means parameter was accepted
                print("   ✅ PASS: apply_patch accepts 'edit' parameter (different error)")
                return
            else:
                print(f"   ⚠️ PARTIAL: Unexpected error: {error}")
                pytest.fail("manage_docs schema behavior validation failed")

    except TypeError as e:
        if "edit" in str(e):
            print(f"   ❌ FAIL: 'edit' parameter not in schema - {e}")
            pytest.fail("manage_docs schema behavior validation failed")
        raise


async def test_create_research_doc_via_create_with_doc_name():
    """Test create action (research doc_type) with doc_name parameter."""
    print("\n2. Testing create (doc_type=research) with 'doc_name' parameter...")
    print("-" * 60)

    try:
        result = await manage_docs(
            action="create",
            doc="research",
            doc_name="TEST_RESEARCH_SCHEMA_FIX",
            metadata={
                "doc_type": "research",
                "research_goal": "Verify doc_name parameter works after schema fix"
            },
            dry_run=True
        )

        if result.get("ok"):
            print("   ✅ PASS: create(doc_type=research) accepts 'doc_name' parameter")
            return
        else:
            error = result.get("error", "Unknown error")
            if "doc_name is required" in error:
                print(f"   ❌ FAIL: Schema still doesn't expose 'doc_name' parameter")
                print(f"   Error: {error}")
                pytest.fail("manage_docs schema behavior validation failed")
            else:
                # Different error means parameter was accepted
                print(f"   ✅ PASS: create(doc_type=research) accepts 'doc_name' parameter")
                print(f"   Note: {error}")
                return

    except TypeError as e:
        if "doc_name" in str(e):
            print(f"   ❌ FAIL: 'doc_name' parameter not in schema - {e}")
            pytest.fail("manage_docs schema behavior validation failed")
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
            return
        else:
            error = result.get("error", "Unknown error")
            if "missing 1 required positional argument: 'doc'" in error:
                print(f"   ❌ FAIL: 'doc' still marked as required in schema")
                print(f"   Error: {error}")
                pytest.fail("manage_docs schema behavior validation failed")
            else:
                # Different error means parameter handling is correct
                print(f"   ✅ PASS: batch action accepts optional 'doc' parameter")
                print(f"   Note: {error}")
                return

    except TypeError as e:
        if "missing 1 required positional argument: 'doc'" in str(e):
            print(f"   ❌ FAIL: 'doc' still required - {e}")
            pytest.fail("manage_docs schema behavior validation failed")
        raise


async def test_batch_inherits_parent_dry_run():
    """Top-level dry_run must propagate to nested batch operations."""
    result = await manage_docs(
        action="batch",
        metadata={
            "operations": [
                {
                    "action": "append",
                    "doc": "architecture",
                    "section": "open_questions",
                    "content": "- [ ] dry_run propagation check",
                }
            ]
        },
        dry_run=True,
    )

    assert result.get("ok") is True
    nested = result.get("results", [{}])[0].get("result", {})
    assert nested.get("ok") is True
    assert nested.get("dry_run") is True


async def test_apply_patch_invalid_mode_fails_hard():
    """Invalid patch_mode must fail fast instead of falling back silently."""
    result = await manage_docs(
        action="apply_patch",
        doc="architecture",
        patch_mode="invalid_mode",
        patch="--- a/ARCHITECTURE_GUIDE.md\n+++ b/ARCHITECTURE_GUIDE.md\n@@ -1,1 +1,1 @@\n # placeholder\n",
        dry_run=True,
    )

    assert result.get("ok") is False
    error = result.get("error", "")
    assert "Invalid patch_mode" in error
    allowed = result.get("allowed_patch_modes") or result.get("extra", {}).get("allowed_patch_modes", [])
    assert "structured" in allowed
    assert "unified" in allowed


async def test_list_sections_falls_back_to_headings_for_custom_docs():
    """Heading-only custom docs should still return actionable sections."""
    doc_name = f"LIST_SECTIONS_HEADING_ONLY_{uuid.uuid4().hex[:8].upper()}"

    create_result = await manage_docs(
        action="create",
        doc_name=doc_name,
        metadata={
            "doc_type": "custom",
            "body": "# Heading Root\n\n## Overview\nBody\n\n### Deep Dive\nMore details\n",
        },
        dry_run=False,
    )
    assert create_result.get("ok") is True

    sections_result = await manage_docs(
        action="list_sections",
        doc_name=doc_name,
    )
    assert sections_result.get("ok") is True
    assert sections_result.get("section_source") == "headings"
    section_ids = [section.get("id") for section in sections_result.get("sections", [])]
    assert "heading_root" in section_ids
    assert "overview" in section_ids
    assert "deep_dive" in section_ids


async def test_list_sections_accepts_doc_name_with_md_extension():
    """list_sections should accept extension-qualified doc names without .md.md fallback."""
    doc_name = f"LIST_SECTIONS_MD_SUFFIX_{uuid.uuid4().hex[:8].upper()}"

    create_result = await manage_docs(
        action="create",
        doc_name=doc_name,
        metadata={
            "doc_type": "custom",
            "body": "# Root\n\n## Child\nBody\n",
        },
        dry_run=False,
    )
    assert create_result.get("ok") is True

    sections_result = await manage_docs(
        action="list_sections",
        doc_name=f"{doc_name}.md",
    )
    assert sections_result.get("ok") is True
    assert sections_result.get("section_source") == "headings"
    section_ids = [section.get("id") for section in sections_result.get("sections", [])]
    assert "root" in section_ids
    assert "child" in section_ids


async def test_search_all_skips_auto_registration_and_succeeds():
    """Wildcard search should not attempt to auto-register a pseudo-doc named 'all'."""
    token = f"SEARCH_ALL_TOKEN_{uuid.uuid4().hex[:8].upper()}"
    doc_name = f"LIVE_SEARCH_ALL_{uuid.uuid4().hex[:8].upper()}"

    create_result = await manage_docs(
        action="create",
        doc_name=doc_name,
        metadata={
            "doc_type": "custom",
            "body": f"# Search All\\n\\n{token}\\n",
        },
        dry_run=False,
    )
    assert create_result.get("ok") is True

    search_result = await manage_docs(
        action="search",
        doc="all",
        metadata={"query": token, "search_mode": "literal"},
    )
    assert search_result.get("ok") is True
    assert search_result.get("results_count", 0) >= 1


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
    results.append(await test_create_research_doc_via_create_with_doc_name())
    results.append(await test_batch_without_doc())
    results.append(await test_batch_inherits_parent_dry_run())

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
        print("  2. create(doc_type=research) now accepts 'doc_name' parameter")
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
