"""Test cleanup_old_entries method for data retention policy (Phase 4).

Tests the archive-then-delete pattern for scribe_entries.
"""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage


@pytest.fixture
def temp_db_path():
    """Provide a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.mark.asyncio
async def test_cleanup_old_entries_with_archive(temp_db_path):
    """Test that old entries are archived before deletion."""
    storage = SQLiteStorage(temp_db_path)
    await storage.setup()

    try:
        # Create a test project
        project = await storage.upsert_project(
            name="test_cleanup_project",
            repo_root="/test/repo",
            progress_log_path="/test/repo/.scribe/progress.md",
        )

        # Insert entries with old timestamps
        old_ts = (datetime.utcnow() - timedelta(days=100)).isoformat()
        recent_ts = (datetime.utcnow() - timedelta(days=10)).isoformat()

        # Insert an old entry (should be cleaned up)
        await storage.insert_entry(
            entry_id="old-entry-001",
            project=project,
            ts=datetime.fromisoformat(old_ts),
            emoji="info",
            agent="TestAgent",
            message="Old entry for cleanup test",
            meta={"test": True},
            raw_line="[2024-01-01] info | Old entry",
            sha256="abc123",
        )

        # Insert a recent entry (should NOT be cleaned up)
        await storage.insert_entry(
            entry_id="recent-entry-001",
            project=project,
            ts=datetime.fromisoformat(recent_ts),
            emoji="info",
            agent="TestAgent",
            message="Recent entry should stay",
            meta={"test": True},
            raw_line="[2025-01-15] info | Recent entry",
            sha256="def456",
        )

        # Run cleanup with archive=True
        deleted_count = await storage.cleanup_old_entries(
            retention_days=90,
            archive=True,
        )

        # Verify: 1 entry deleted
        assert deleted_count == 1, f"Expected 1 entry deleted, got {deleted_count}"

        # Verify: old entry is in archive
        archive_row = await storage._fetchone(
            "SELECT * FROM scribe_entries_archive WHERE id = ?",
            ("old-entry-001",),
        )
        assert archive_row is not None, "Old entry should be in archive"
        assert archive_row["message"] == "Old entry for cleanup test"

        # Verify: old entry is NOT in scribe_entries
        entry_row = await storage._fetchone(
            "SELECT * FROM scribe_entries WHERE id = ?",
            ("old-entry-001",),
        )
        assert entry_row is None, "Old entry should be deleted from scribe_entries"

        # Verify: recent entry is still in scribe_entries
        recent_row = await storage._fetchone(
            "SELECT * FROM scribe_entries WHERE id = ?",
            ("recent-entry-001",),
        )
        assert recent_row is not None, "Recent entry should still exist"

    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_cleanup_old_entries_without_archive(temp_db_path):
    """Test that entries are deleted without archiving when archive=False."""
    storage = SQLiteStorage(temp_db_path)
    await storage.setup()

    try:
        # Create a test project
        project = await storage.upsert_project(
            name="test_cleanup_no_archive",
            repo_root="/test/repo2",
            progress_log_path="/test/repo2/.scribe/progress.md",
        )

        # Insert an old entry
        old_ts = (datetime.utcnow() - timedelta(days=100)).isoformat()
        await storage.insert_entry(
            entry_id="old-entry-002",
            project=project,
            ts=datetime.fromisoformat(old_ts),
            emoji="info",
            agent="TestAgent",
            message="Old entry without archive",
            meta={"test": True},
            raw_line="[2024-01-01] info | Old entry",
            sha256="ghi789",
        )

        # Run cleanup with archive=False
        deleted_count = await storage.cleanup_old_entries(
            retention_days=90,
            archive=False,
        )

        # Verify: 1 entry deleted
        assert deleted_count == 1, f"Expected 1 entry deleted, got {deleted_count}"

        # Verify: entry is NOT in archive
        archive_row = await storage._fetchone(
            "SELECT * FROM scribe_entries_archive WHERE id = ?",
            ("old-entry-002",),
        )
        assert archive_row is None, "Entry should NOT be in archive when archive=False"

        # Verify: entry is deleted from scribe_entries
        entry_row = await storage._fetchone(
            "SELECT * FROM scribe_entries WHERE id = ?",
            ("old-entry-002",),
        )
        assert entry_row is None, "Old entry should be deleted"

    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_cleanup_old_entries_with_project_filter(temp_db_path):
    """Test that cleanup respects project_id filter."""
    storage = SQLiteStorage(temp_db_path)
    await storage.setup()

    try:
        # Create two test projects
        project1 = await storage.upsert_project(
            name="test_project_1",
            repo_root="/test/repo1",
            progress_log_path="/test/repo1/.scribe/progress.md",
        )
        project2 = await storage.upsert_project(
            name="test_project_2",
            repo_root="/test/repo2",
            progress_log_path="/test/repo2/.scribe/progress.md",
        )

        # Insert old entries in both projects
        old_ts = (datetime.utcnow() - timedelta(days=100)).isoformat()

        await storage.insert_entry(
            entry_id="proj1-old-001",
            project=project1,
            ts=datetime.fromisoformat(old_ts),
            emoji="info",
            agent="TestAgent",
            message="Project 1 old entry",
            meta={"test": True},
            raw_line="[2024-01-01] info | Project 1",
            sha256="proj1hash",
        )

        await storage.insert_entry(
            entry_id="proj2-old-001",
            project=project2,
            ts=datetime.fromisoformat(old_ts),
            emoji="info",
            agent="TestAgent",
            message="Project 2 old entry",
            meta={"test": True},
            raw_line="[2024-01-01] info | Project 2",
            sha256="proj2hash",
        )

        # Cleanup only project 1
        deleted_count = await storage.cleanup_old_entries(
            project_id=project1.id,
            retention_days=90,
            archive=True,
        )

        # Verify: only 1 entry deleted (from project 1)
        assert deleted_count == 1, f"Expected 1 entry deleted, got {deleted_count}"

        # Verify: project 1 entry is deleted
        proj1_entry = await storage._fetchone(
            "SELECT * FROM scribe_entries WHERE id = ?",
            ("proj1-old-001",),
        )
        assert proj1_entry is None, "Project 1 entry should be deleted"

        # Verify: project 2 entry still exists
        proj2_entry = await storage._fetchone(
            "SELECT * FROM scribe_entries WHERE id = ?",
            ("proj2-old-001",),
        )
        assert proj2_entry is not None, "Project 2 entry should still exist"

    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_cleanup_returns_zero_when_no_old_entries(temp_db_path):
    """Test that cleanup returns 0 when there are no old entries."""
    storage = SQLiteStorage(temp_db_path)
    await storage.setup()

    try:
        # Create a project with only recent entries
        project = await storage.upsert_project(
            name="test_recent_only",
            repo_root="/test/repo",
            progress_log_path="/test/repo/.scribe/progress.md",
        )

        recent_ts = datetime.utcnow().isoformat()
        await storage.insert_entry(
            entry_id="recent-only-001",
            project=project,
            ts=datetime.fromisoformat(recent_ts),
            emoji="info",
            agent="TestAgent",
            message="Recent entry only",
            meta={"test": True},
            raw_line="[2025-01-23] info | Recent",
            sha256="recenthash",
        )

        # Run cleanup
        deleted_count = await storage.cleanup_old_entries(retention_days=90)

        # Verify: 0 entries deleted
        assert deleted_count == 0, f"Expected 0 entries deleted, got {deleted_count}"

        # Verify: entry still exists
        entry_row = await storage._fetchone(
            "SELECT * FROM scribe_entries WHERE id = ?",
            ("recent-only-001",),
        )
        assert entry_row is not None, "Recent entry should still exist"

    finally:
        await storage.close()
