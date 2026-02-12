#!/usr/bin/env python3
"""Test script for read_file enhancements."""

import asyncio
import json
from pathlib import Path

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.execution_context import AgentIdentity, ExecutionContext
from scribe_mcp.tools.read_file import read_file

pytestmark = pytest.mark.asyncio


@pytest.fixture
def exec_context_token():
    repo_root = Path(__file__).parent.parent
    context = ExecutionContext(
        repo_root=str(repo_root),
        mode="sentinel",
        session_id="read-file-enhancements-session",
        execution_id="read-file-enhancements-exec",
        agent_identity=AgentIdentity(
            agent_kind="test",
            model=None,
            instance_id="test-agent",
            sub_id=None,
            display_name=None,
        ),
        intent="read_file_enhancements",
        timestamp_utc="2026-02-11T00:00:00+00:00",
        affected_dev_projects=[],
        sentinel_day="2026-02-11",
    )
    token = server_module.router_context_manager.set_current(context)
    try:
        yield
    finally:
        server_module.router_context_manager.reset(token)


async def test_python_ast(exec_context_token):
    """Test Python AST structure extraction."""
    print("\n" + "="*80)
    print("TEST 1: Python AST Structure Extraction")
    print("="*80)

    result = await read_file(
        agent="test_agent",
        path="src/scribe_mcp/tools/read_file.py",
        mode="scan_only",
        format="structured"
    )

    print(f"\nOK: {result.get('ok')}")
    print(f"File: {result.get('scan', {}).get('repo_relative_path')}")
    print(f"Line Count: {result.get('scan', {}).get('line_count')}")

    structure = result.get('structure', {})
    if structure:
        print(f"\nStructure Type: {structure.get('type')}")
        print(f"Total Functions: {structure.get('total_functions')}")
        print(f"Total Classes: {structure.get('total_classes')}")
        print(f"Truncated: {structure.get('truncated')}")

        functions = structure.get('functions', [])
        print(f"\nFirst 5 Functions:")
        for func in functions[:5]:
            print(f"  - {func['name']}() at line {func['line']} [{func['type']}]")

        classes = structure.get('classes', [])
        if classes:
            print(f"\nFirst 2 Classes:")
            for cls in classes[:2]:
                print(f"  - {cls['name']} at line {cls['line']} ({cls['method_count']} methods)")

    nav_hints = result.get('navigation_hints', {})
    if nav_hints:
        print(f"\nNavigation Hints:")
        print(f"  Total Chunks: {nav_hints.get('total_chunks')}")
        print(f"  Suggested Chunk Size: {nav_hints.get('suggested_chunk_size')}")

    assert result.get('ok', False)


async def test_markdown_headings(exec_context_token):
    """Test Markdown heading extraction."""
    print("\n" + "="*80)
    print("TEST 2: Markdown Heading Extraction")
    print("="*80)

    result = await read_file(
        agent="test_agent",
        path="CLAUDE.md",
        mode="scan_only",
        format="structured"
    )

    print(f"\nOK: {result.get('ok')}")
    print(f"File: {result.get('scan', {}).get('repo_relative_path')}")

    structure = result.get('structure', {})
    if structure:
        print(f"\nStructure Type: {structure.get('type')}")
        print(f"Total Headings: {structure.get('total_headings')}")
        print(f"Truncated: {structure.get('truncated')}")

        headings = structure.get('headings', [])
        print(f"\nFirst 10 Headings:")
        for heading in headings[:10]:
            indent = "  " * (heading['level'] - 1)
            print(f"{indent}{'#'*heading['level']} {heading['text']} (line {heading['line']})")

    assert result.get('ok', False)


async def test_skill_detection(exec_context_token):
    """Test SKILL.md special file detection."""
    print("\n" + "="*80)
    print("TEST 3: SKILL.md Special Detection")
    print("="*80)

    result = await read_file(
        agent="test_agent",
        path=".codex/skills/scribe-mcp-usage/SKILL.md",
        mode="scan_only",
        format="structured"
    )

    print(f"\nOK: {result.get('ok')}")
    print(f"File: {result.get('scan', {}).get('repo_relative_path')}")

    special = result.get('special_file', {})
    if special:
        print(f"\n🚨 SPECIAL FILE DETECTED 🚨")
        print(f"  Type: {special.get('type')}")
        print(f"  Urgency: {special.get('urgency')}")
        print(f"  Requires Full Read: {special.get('requires_full_read')}")
        print(f"  Reason: {special.get('reason')}")
        print(f"  Instruction: {special.get('instruction')}")
        print(f"  Suggested Action: {special.get('suggested_action')}")
    else:
        print("\n❌ SKILL.md detection FAILED - no special_file metadata!")

    assert result.get('ok', False)
    assert bool(special)


async def test_regex_search(exec_context_token):
    """Test regex search mode (now default)."""
    print("\n" + "="*80)
    print("TEST 4: Regex Search Mode (Default)")
    print("="*80)

    # Test complex regex pattern - find all async functions
    result = await read_file(
        agent="test_agent",
        path="src/scribe_mcp/tools/read_file.py",
        mode="search",
        query=r"async\s+def\s+\w+",  # Should match async function definitions
        format="structured"
    )

    print(f"\nOK: {result.get('ok')}")
    print(f"Search Pattern: async\\s+def\\s+\\w+")

    matches = result.get('matches', [])
    print(f"Matches Found: {len(matches)}")

    if matches:
        print(f"\nFirst 5 Matches:")
        for match in matches[:5]:
            line_num = match['line_number']
            line_text = match['line'].strip()
            print(f"  Line {line_num}: {line_text[:80]}")

    assert result.get('ok', False)


async def test_navigation_hints(exec_context_token):
    """Test navigation hints in scan mode."""
    print("\n" + "="*80)
    print("TEST 5: Navigation Hints")
    print("="*80)

    result = await read_file(
        agent="test_agent",
        path="src/scribe_mcp/server.py",
        mode="scan_only",
        format="structured"
    )

    nav_hints = result.get('navigation_hints', {})
    if nav_hints:
        print(f"\n✓ Navigation Hints Present")
        print(f"  Total Chunks: {nav_hints.get('total_chunks')}")
        print(f"  Suggested Chunk Size: {nav_hints.get('suggested_chunk_size')}")
        print(f"  Modes Available: {', '.join(nav_hints.get('modes_available', []))}")

        examples = nav_hints.get('examples', {})
        if examples:
            print(f"\n  Example Calls:")
            for mode_name, example in examples.items():
                print(f"    {mode_name}: {example[:100]}...")
    else:
        print("\n❌ Navigation hints MISSING!")

    assert bool(nav_hints)


async def main():
    """Run all tests."""
    print("\n" + "🧪 "*20)
    print("READ_FILE ENHANCEMENTS TEST SUITE")
    print("🧪 "*20)

    results = {}

    try:
        results['python_ast'] = await test_python_ast()
    except Exception as e:
        print(f"\n❌ Python AST test FAILED: {e}")
        results['python_ast'] = False

    try:
        results['markdown_headings'] = await test_markdown_headings()
    except Exception as e:
        print(f"\n❌ Markdown headings test FAILED: {e}")
        results['markdown_headings'] = False

    try:
        results['skill_detection'] = await test_skill_detection()
    except Exception as e:
        print(f"\n❌ SKILL.md detection test FAILED: {e}")
        results['skill_detection'] = False

    try:
        results['regex_search'] = await test_regex_search()
    except Exception as e:
        print(f"\n❌ Regex search test FAILED: {e}")
        results['regex_search'] = False

    try:
        results['navigation_hints'] = await test_navigation_hints()
    except Exception as e:
        print(f"\n❌ Navigation hints test FAILED: {e}")
        results['navigation_hints'] = False

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
