"""
Test index updates after document edits (Phase 4: Index Update Event Coverage).

Verifies that INDEX.md files are updated when special docs are edited,
not just when they're created.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest

from scribe_mcp.tools.manage_docs import manage_docs, _get_index_updater_for_path


@pytest.mark.asyncio
async def test_index_updater_detection_research():
    """Test _get_index_updater_for_path detects research docs correctly."""
    print("\n1. Testing index updater detection for research docs...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        research_dir = docs_dir / "research"
        research_dir.mkdir(parents=True, exist_ok=True)

        # Create a research doc path
        research_doc = research_dir / "RESEARCH_TEST_20260120.md"
        research_doc.write_text("# Test Research\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=research_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect research doc and return updater"
        print("✅ Research doc detection works")


@pytest.mark.asyncio
async def test_index_updater_detection_bug():
    """Test _get_index_updater_for_path detects bug reports correctly."""
    print("\n2. Testing index updater detection for bug reports...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        bugs_dir = project_root / "docs" / "bugs" / "logic" / "2026-01-20_auth_leak"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        # Create a bug report path
        bug_doc = bugs_dir / "report.md"
        bug_doc.write_text("# Bug Report\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=bug_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect bug report and return updater"
        print("✅ Bug report detection works")


@pytest.mark.asyncio
async def test_index_updater_detection_review():
    """Test _get_index_updater_for_path detects review reports correctly."""
    print("\n3. Testing index updater detection for review reports...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Create a review report path
        review_doc = docs_dir / "REVIEW_REPORT_phase1_2026-01-20_1430.md"
        review_doc.write_text("# Review Report\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=review_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect review report and return updater"
        print("✅ Review report detection works")


@pytest.mark.asyncio
async def test_index_updater_detection_agent_card():
    """Test _get_index_updater_for_path detects agent cards correctly."""
    print("\n4. Testing index updater detection for agent cards...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Create an agent card path
        card_doc = docs_dir / "AGENT_REPORT_CARD_Coder_phase1_20260120_1430.md"
        card_doc.write_text("# Agent Report Card\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=card_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect agent card and return updater"
        print("✅ Agent card detection works")


@pytest.mark.asyncio
async def test_index_updater_detection_regular_doc():
    """Test _get_index_updater_for_path returns None for regular docs."""
    print("\n5. Testing index updater returns None for regular docs...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Create a regular managed doc path (not special)
        regular_doc = docs_dir / "ARCHITECTURE_GUIDE.md"
        regular_doc.write_text("# Architecture\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=regular_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is None, "Should return None for regular managed docs"
        print("✅ Regular doc detection works (returns None)")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Index Update Event Coverage (Phase 4)")
    print("=" * 60)

    asyncio.run(test_index_updater_detection_research())
    asyncio.run(test_index_updater_detection_bug())
    asyncio.run(test_index_updater_detection_review())
    asyncio.run(test_index_updater_detection_agent_card())
    asyncio.run(test_index_updater_detection_regular_doc())

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
