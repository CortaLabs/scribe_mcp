"""Tests for preflight_backup centralized backup location."""

import time
import pytest
import tempfile
from pathlib import Path
from scribe_mcp.utils.files import preflight_backup


def test_preflight_backup_creates_centralized_backup():
    """Test that preflight_backup creates backup in .scribe/backups/ directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a test file in a subdirectory
        test_dir = tmpdir / "research"
        test_dir.mkdir(parents=True)
        test_file = test_dir / "RESEARCH_TEST.md"
        test_file.write_text("# Test Content\n\nThis is a test file.")

        # Create backup
        backup_path = preflight_backup(test_file, repo_root=tmpdir)

        # Verify backup location
        expected_backup_dir = tmpdir / ".scribe" / "backups"
        assert backup_path.parent == expected_backup_dir
        assert expected_backup_dir.exists()

        # Verify backup filename preserves path structure
        # Should be: research__RESEARCH_TEST.md.preflight-TIMESTAMP.bak
        assert backup_path.name.startswith("research__RESEARCH_TEST.md.preflight-")
        assert backup_path.name.endswith(".bak")

        # Verify backup content matches original
        assert backup_path.read_text() == test_file.read_text()


def test_preflight_backup_nested_directories():
    """Test backup filename for deeply nested files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a deeply nested file
        test_dir = tmpdir / "docs" / "dev_plans" / "project" / "research"
        test_dir.mkdir(parents=True)
        test_file = test_dir / "analysis.md"
        test_file.write_text("Analysis content")

        # Create backup
        backup_path = preflight_backup(test_file, repo_root=tmpdir)

        # Verify filename has all directory components
        # Should be: docs__dev_plans__project__research__analysis.md.preflight-TIMESTAMP.bak
        assert "docs__dev_plans__project__research__analysis.md.preflight-" in backup_path.name
        assert backup_path.name.endswith(".bak")

        # Verify location
        assert backup_path.parent == tmpdir / ".scribe" / "backups"


def test_preflight_backup_single_level_file():
    """Test backup for file at repo root level."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create file at root
        test_file = tmpdir / "README.md"
        test_file.write_text("README content")

        # Create backup
        backup_path = preflight_backup(test_file, repo_root=tmpdir)

        # Verify filename doesn't have directory prefix
        # Should be: README.md.preflight-TIMESTAMP.bak
        assert backup_path.name.startswith("README.md.preflight-")
        assert "__" not in backup_path.name.split(".preflight-")[0]  # No __ in base name


def test_preflight_backup_preserves_file_content():
    """Test that backup preserves file metadata and content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test file
        test_file = tmpdir / "test.md"
        test_content = "# Header\n\nMultiple\nLines\nOf\nContent\n"
        test_file.write_text(test_content)

        # Create backup
        backup_path = preflight_backup(test_file, repo_root=tmpdir)

        # Verify content
        assert backup_path.read_text() == test_content

        # Verify file stats (modification time) preserved by shutil.copy2
        # Note: Just verify backup exists and has content, exact metadata may vary
        assert backup_path.stat().st_size == test_file.stat().st_size


def test_preflight_backup_retains_only_three_latest_backups():
    """Test that preflight_backup enforces a 3-backup retention policy per file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        test_file = tmpdir / "retention.md"

        created_backups = []
        for i in range(5):
            test_file.write_text(f"content-{i}")
            created_backups.append(preflight_backup(test_file, repo_root=tmpdir))
            time.sleep(0.005)

        backup_dir = tmpdir / ".scribe" / "backups"
        backups = sorted(backup_dir.glob("retention.md.preflight-*.bak"), key=lambda p: p.name)

        assert len(backups) == 3
        assert created_backups[0].exists() is False
        assert created_backups[1].exists() is False
        assert created_backups[2].exists() is True
        assert created_backups[3].exists() is True
        assert created_backups[4].exists() is True


def test_preflight_backup_nonexistent_file_raises():
    """Test that backing up non-existent file raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        nonexistent = tmpdir / "does_not_exist.md"

        with pytest.raises(Exception) as exc_info:
            preflight_backup(nonexistent, repo_root=tmpdir)

        assert "non-existent" in str(exc_info.value).lower() or "does not exist" in str(exc_info.value).lower()


def test_preflight_backup_managed_doc_routes_to_docs_archive_family():
    """Managed-doc backups route under docs_dir/archive/preflight/<family>/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        docs_dir = tmpdir / ".scribe" / "docs" / "dev_plans" / "proj1"
        research_dir = docs_dir / "research"
        research_dir.mkdir(parents=True)
        test_file = research_dir / "RESEARCH_TEST.md"
        test_file.write_text("research body")

        backup_path = preflight_backup(
            test_file,
            repo_root=tmpdir,
            context={
                "component": "files",
                "op": "backup",
                "managed_doc_archive": True,
                "project_docs_dir": str(docs_dir),
                "backup_family": "research",
            },
        )

        assert backup_path.parent == docs_dir / "archive" / "preflight" / "research"
        assert backup_path.suffix == ".bak"
        assert not backup_path.name.endswith(".md")


def test_preflight_backup_managed_doc_fallback_family_misc():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        docs_dir = tmpdir / "docs" / "dev_plans" / "legacy_proj"
        docs_dir.mkdir(parents=True)
        test_file = docs_dir / "UNKNOWN.md"
        test_file.write_text("x")

        backup_path = preflight_backup(
            test_file,
            repo_root=tmpdir,
            context={
                "managed_doc_archive": True,
                "project_docs_dir": str(docs_dir),
            },
        )

        assert backup_path.parent == docs_dir / "archive" / "preflight" / "misc"


@pytest.mark.parametrize("unsafe_family", ["../escape", "research/extra"])
def test_preflight_backup_managed_doc_unsafe_family_routes_to_misc(unsafe_family: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        docs_dir = tmpdir / ".scribe" / "docs" / "dev_plans" / "proj_unsafe"
        docs_dir.mkdir(parents=True)
        test_file = docs_dir / "RESEARCH_UNSAFE.md"
        test_file.write_text("unsafe test")

        backup_path = preflight_backup(
            test_file,
            repo_root=tmpdir,
            context={
                "managed_doc_archive": True,
                "project_docs_dir": str(docs_dir),
                "backup_family": unsafe_family,
            },
        )

        assert backup_path.parent == docs_dir / "archive" / "preflight" / "misc"
