"""Integration test to verify backup location works with manage_docs."""

import pytest
import tempfile
from pathlib import Path
from scribe_mcp.utils.files import preflight_backup


def test_backup_integration_with_real_scenario():
    """Test that backup works in realistic scenario similar to manage_docs usage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Simulate a typical manage_docs scenario
        project_dir = tmpdir / ".scribe" / "docs" / "dev_plans" / "test_project"
        research_dir = project_dir / "research"
        research_dir.mkdir(parents=True)

        # Create a research document
        research_doc = research_dir / "RESEARCH_AUTH_20260119.md"
        original_content = """# Research: Authentication System

## Overview
Analysis of current auth implementation.

## Findings
- Token expiration not handled
- Session management issues
"""
        research_doc.write_text(original_content)

        # Create a backup (as manage_docs would do)
        backup_path = preflight_backup(
            research_doc,
            repo_root=tmpdir,
            context={
                "component": "files",
                "op": "backup",
                "managed_doc_archive": True,
                "project_docs_dir": str(project_dir),
                "backup_family": "research",
            },
        )

        # Verify backup is in project docs archive lane, NOT in research/ directory
        assert backup_path.parent == project_dir / "archive" / "preflight" / "research"
        assert backup_path.parent != research_dir  # NOT alongside original

        # Verify filename preserves relative path structure from repo root.
        assert ".scribe__docs__dev_plans__test_project__research__RESEARCH_AUTH_20260119.md.preflight-" in backup_path.name

        # Verify content matches
        assert backup_path.read_text() == original_content

        # Verify original file is untouched
        assert research_doc.read_text() == original_content

        # Verify research directory is clean (no sibling .bak files)
        bak_files_in_research = list(research_dir.glob("*.bak"))
        assert len(bak_files_in_research) == 0, "No .bak files should be in research directory"


def test_multiple_backups_same_file():
    """Test that multiple backups of same file create unique timestamped files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        test_file = tmpdir / "test.md"
        test_file.write_text("Version 1")

        # Create first backup
        backup1 = preflight_backup(test_file, repo_root=tmpdir)

        # Modify file
        test_file.write_text("Version 2")

        # Create second backup (different timestamp)
        import time
        time.sleep(0.01)  # Ensure different timestamp
        backup2 = preflight_backup(test_file, repo_root=tmpdir)

        # Both backups should exist
        assert backup1.exists()
        assert backup2.exists()

        # Both in same directory
        assert backup1.parent == backup2.parent
        assert backup1.parent == tmpdir / ".scribe" / "backups"

        # Different timestamps
        assert backup1.name != backup2.name

        # Different contents
        assert backup1.read_text() == "Version 1"
        assert backup2.read_text() == "Version 2"
