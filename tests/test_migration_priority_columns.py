#!/usr/bin/env python3
"""Test migration of priority, category, tags, and confidence columns to scribe_entries table."""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
import tempfile
from datetime import datetime

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.storage.models import ProjectRecord


@pytest.mark.asyncio
async def test_priority_columns_exist():
    """Verify new columns exist after migration."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = SQLiteStorage(db_path)
        await storage._initialise()

        # Check columns exist using _fetchall instead of direct connection
        rows = await storage._fetchall("PRAGMA table_info(scribe_entries);", ())
        column_names = [row["name"] for row in rows]

        assert "priority" in column_names, "priority column missing"
        assert "category" in column_names, "category column missing"
        assert "tags" in column_names, "tags column missing"
        assert "confidence" in column_names, "confidence column missing"
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_existing_entries_have_defaults():
    """Verify existing entries get default priority when columns are added."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = SQLiteStorage(db_path)
        await storage._initialise()

        # Create a test project
        project = await storage.upsert_project(
            name="test_project",
            repo_root="/tmp/test",
            progress_log_path="/tmp/test/PROGRESS_LOG.md"
        )

        # Insert entry without priority (backward compatibility test)
        await storage.insert_entry(
            entry_id="test123",
            project=project,
            ts=datetime.utcnow(),
            emoji="✅",
            agent="TestAgent",
            message="Test message",
            meta={},
            raw_line="[✅] [04:50] [Agent: TestAgent] Test message",
            sha256="abc123"
        )

        # Verify it got default priority
        rows = await storage._fetchall(
            "SELECT priority, category, tags, confidence FROM scribe_entries WHERE id = ?;",
            ("test123",)
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["priority"] == "medium", f"Expected 'medium', got {row['priority']}"
        assert row["category"] is None, f"Expected None, got {row['category']}"
        assert row["tags"] is None, f"Expected None, got {row['tags']}"
        assert row["confidence"] == 1.0, f"Expected 1.0, got {row['confidence']}"
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_explicit_values_stored():
    """Verify explicit priority/category/tags/confidence values are stored correctly."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = SQLiteStorage(db_path)
        await storage._initialise()

        # Create a test project
        project = await storage.upsert_project(
            name="test_project",
            repo_root="/tmp/test",
            progress_log_path="/tmp/test/PROGRESS_LOG.md"
        )

        # Insert entry with explicit values
        await storage.insert_entry(
            entry_id="test456",
            project=project,
            ts=datetime.utcnow(),
            emoji="✅",
            agent="TestAgent",
            message="Test message with metadata",
            meta={"component": "auth"},
            raw_line="[✅] [04:50] [Agent: TestAgent] Test message",
            sha256="def456",
            priority="high",
            category="implementation",
            tags="auth,security",
            confidence=0.95
        )

        # Verify values were stored
        rows = await storage._fetchall(
            "SELECT priority, category, tags, confidence FROM scribe_entries WHERE id = ?;",
            ("test456",)
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["priority"] == "high"
        assert row["category"] == "implementation"
        assert row["tags"] == "auth,security"
        assert row["confidence"] == 0.95
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_values_from_meta():
    """Verify priority/category/tags/confidence are extracted from meta dict when not explicit."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = SQLiteStorage(db_path)
        await storage._initialise()

        # Create a test project
        project = await storage.upsert_project(
            name="test_project",
            repo_root="/tmp/test",
            progress_log_path="/tmp/test/PROGRESS_LOG.md"
        )

        # Insert entry with values in meta dict
        await storage.insert_entry(
            entry_id="test789",
            project=project,
            ts=datetime.utcnow(),
            emoji="🐞",
            agent="TestAgent",
            message="Bug found",
            meta={
                "priority": "critical",
                "category": "bug",
                "tags": "database,migration",
                "confidence": 0.85,
                "component": "storage"
            },
            raw_line="[🐞] [04:50] [Agent: TestAgent] Bug found",
            sha256="ghi789"
        )

        # Verify values were extracted from meta
        rows = await storage._fetchall(
            "SELECT priority, category, tags, confidence FROM scribe_entries WHERE id = ?;",
            ("test789",)
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["priority"] == "critical"
        assert row["category"] == "bug"
        assert row["tags"] == "database,migration"
        assert row["confidence"] == 0.85
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_indexes_created():
    """Verify indexes were created successfully."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        storage = SQLiteStorage(db_path)
        await storage._initialise()

        # Check indexes exist
        rows = await storage._fetchall("PRAGMA index_list(scribe_entries);", ())
        index_names = [row["name"] for row in rows]

        assert "idx_entries_priority_ts" in index_names, "Priority+ts index missing"
        assert "idx_entries_category_ts" in index_names, "Category+ts index missing"
        assert "idx_entries_project_priority_category" in index_names, "Composite index missing"
    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_migration_is_idempotent():
    """Verify migration can be run multiple times without errors."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Run initialization twice
        storage1 = SQLiteStorage(db_path)
        await storage1._initialise()

        storage2 = SQLiteStorage(db_path)
        await storage2._initialise()

        # Should not raise any errors
        rows = await storage2._fetchall("PRAGMA table_info(scribe_entries);", ())
        column_names = [row["name"] for row in rows]

        # Verify columns still exist
        assert "priority" in column_names
        assert "category" in column_names
        assert "tags" in column_names
        assert "confidence" in column_names
    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    # Allow running tests directly
    asyncio.run(test_priority_columns_exist())
    asyncio.run(test_existing_entries_have_defaults())
    asyncio.run(test_explicit_values_stored())
    asyncio.run(test_values_from_meta())
    asyncio.run(test_indexes_created())
    asyncio.run(test_migration_is_idempotent())
    print("All tests passed!")
