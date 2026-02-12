#!/usr/bin/env python3
"""
Test suite for database migration: docs_json column addition.

Tests Phase 1 implementation of BUG-MANAGE-DOCS-001 fix.
Validates idempotent migration, backfill functionality, and error handling.
"""

import asyncio
import json
import pytest
import sqlite3
import tempfile
from pathlib import Path

from scribe_mcp.storage.sqlite import SQLiteStorage


def run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


@pytest.fixture
def temp_storage(tmp_path):
    """Create a temporary SQLite storage for testing."""
    db_path = tmp_path / "test.db"
    storage = SQLiteStorage(db_path)
    run(storage._initialise())
    yield storage


@pytest.fixture
def temp_storage_no_init(tmp_path):
    """Create a temporary SQLite storage WITHOUT initialization (for testing migration)."""
    db_path = tmp_path / "test.db"
    storage = SQLiteStorage(db_path)
    yield storage


@pytest.fixture
def temp_state_file():
    """Create a temporary state.json file with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.json"
        state_data = {
            "projects": {
                "test_project_1": {
                    "name": "test_project_1",
                    "root": "/tmp/test1",
                    "progress_log": "/tmp/test1/PROGRESS_LOG.md",
                    "docs": {
                        "architecture": "/tmp/test1/ARCHITECTURE.md",
                        "checklist": "/tmp/test1/CHECKLIST.md"
                    }
                },
                "test_project_2": {
                    "name": "test_project_2",
                    "root": "/tmp/test2",
                    "progress_log": "/tmp/test2/PROGRESS_LOG.md",
                    "docs": {
                        "phase_plan": "/tmp/test2/PHASE_PLAN.md"
                    }
                },
                "test_project_no_docs": {
                    "name": "test_project_no_docs",
                    "root": "/tmp/test3",
                    "progress_log": "/tmp/test3/PROGRESS_LOG.md"
                }
            }
        }

        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state_data, f)

        yield state_path


class TestMigrationIdempotency:
    """Test that migration can run multiple times safely."""

    def test_migrate_adds_column_when_missing(self, temp_storage_no_init):
        """Test migration adds column when it doesn't exist."""
        storage = temp_storage_no_init

        # Create table WITHOUT docs_json column (simulate old schema)
        conn = storage._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scribe_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    repo_root TEXT NOT NULL,
                    progress_log_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        finally:
            conn.close()

        # Verify column doesn't exist
        conn = storage._connect()
        try:
            cursor = conn.execute("PRAGMA table_info(scribe_projects);")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            assert 'docs_json' not in column_names, "Column should not exist before migration"
        finally:
            conn.close()

        # Run migration
        result = run(storage.migrate_add_docs_json_column())
        assert result is True, "Migration should return True when adding column"

        # Verify column was added
        conn = storage._connect()
        try:
            cursor = conn.execute("PRAGMA table_info(scribe_projects);")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            assert 'docs_json' in column_names, "Column should exist after migration"
        finally:
            conn.close()

    def test_migrate_idempotent(self, temp_storage):
        """Test migration can run multiple times without errors."""
        storage = temp_storage

        # Run migration first time
        result1 = run(storage.migrate_add_docs_json_column())
        assert result1 is True, "First migration should succeed"

        # Run migration second time (idempotent)
        result2 = run(storage.migrate_add_docs_json_column())
        assert result2 is True, "Second migration should succeed (idempotent)"

        # Run migration third time (idempotent)
        result3 = run(storage.migrate_add_docs_json_column())
        assert result3 is True, "Third migration should succeed (idempotent)"

        # Verify column still exists and only one column was created
        conn = storage._connect()
        try:
            cursor = conn.execute("PRAGMA table_info(scribe_projects);")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            docs_json_count = column_names.count('docs_json')
            assert docs_json_count == 1, "Should have exactly one docs_json column"
        finally:
            conn.close()


class TestBackfillFunctionality:
    """Test backfill from state.json functionality."""

    def test_backfill_populates_docs_json(self, temp_storage, temp_state_file):
        """Test backfill successfully populates docs_json from state.json."""
        storage = temp_storage
        state_path = temp_state_file

        # Insert test projects without docs_json
        conn = storage._connect()
        try:
            conn.execute(
                "INSERT INTO scribe_projects (name, repo_root, progress_log_path) VALUES (?, ?, ?)",
                ("test_project_1", "/tmp/test1", "/tmp/test1/PROGRESS_LOG.md")
            )
            conn.execute(
                "INSERT INTO scribe_projects (name, repo_root, progress_log_path) VALUES (?, ?, ?)",
                ("test_project_2", "/tmp/test2", "/tmp/test2/PROGRESS_LOG.md")
            )
            conn.execute(
                "INSERT INTO scribe_projects (name, repo_root, progress_log_path) VALUES (?, ?, ?)",
                ("test_project_no_docs", "/tmp/test3", "/tmp/test3/PROGRESS_LOG.md")
            )
            conn.commit()
        finally:
            conn.close()

        # Run backfill
        backfilled_count = run(storage.backfill_docs_json_from_state(state_path))
        assert backfilled_count == 2, "Should backfill 2 projects (only those with docs)"

        # Verify docs_json was populated correctly
        conn = storage._connect()
        try:
            # Check test_project_1
            cursor = conn.execute(
                "SELECT docs_json FROM scribe_projects WHERE name = ?",
                ("test_project_1",)
            )
            row = cursor.fetchone()
            assert row is not None, "Project should exist"
            assert row[0] is not None, "docs_json should be populated"

            docs = json.loads(row[0])
            assert docs["architecture"] == "/tmp/test1/ARCHITECTURE.md"
            assert docs["checklist"] == "/tmp/test1/CHECKLIST.md"

            # Check test_project_2
            cursor = conn.execute(
                "SELECT docs_json FROM scribe_projects WHERE name = ?",
                ("test_project_2",)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] is not None

            docs = json.loads(row[0])
            assert docs["phase_plan"] == "/tmp/test2/PHASE_PLAN.md"

            # Check test_project_no_docs (should remain NULL)
            cursor = conn.execute(
                "SELECT docs_json FROM scribe_projects WHERE name = ?",
                ("test_project_no_docs",)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] is None, "Project without docs should have NULL docs_json"
        finally:
            conn.close()

    def test_backfill_missing_state_file(self, temp_storage):
        """Test backfill handles missing state.json gracefully."""
        storage = temp_storage
        nonexistent_path = Path("/nonexistent/state.json")

        # Should not raise exception, just return 0
        backfilled_count = run(storage.backfill_docs_json_from_state(nonexistent_path))
        assert backfilled_count == 0, "Should return 0 for missing state file"

    def test_backfill_skips_nonexistent_projects(self, temp_storage, temp_state_file):
        """Test backfill only updates projects that exist in database."""
        storage = temp_storage
        state_path = temp_state_file

        # Insert only one project (test_project_1)
        conn = storage._connect()
        try:
            conn.execute(
                "INSERT INTO scribe_projects (name, repo_root, progress_log_path) VALUES (?, ?, ?)",
                ("test_project_1", "/tmp/test1", "/tmp/test1/PROGRESS_LOG.md")
            )
            conn.commit()
        finally:
            conn.close()

        # Run backfill (state.json has 3 projects, only 1 in DB)
        backfilled_count = run(storage.backfill_docs_json_from_state(state_path))
        assert backfilled_count == 1, "Should only backfill projects that exist in DB"


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_backfill_malformed_json(self, temp_storage):
        """Test backfill handles malformed state.json."""
        storage = temp_storage

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "bad_state.json"
            with open(state_path, 'w') as f:
                f.write("{ invalid json }")

            # Should raise JSONDecodeError
            with pytest.raises(json.JSONDecodeError):
                run(storage.backfill_docs_json_from_state(state_path))

    def test_migration_on_new_database(self, temp_storage):
        """Test migration works correctly on brand new database."""
        storage = temp_storage

        # Verify docs_json column exists (should be created during _initialise)
        conn = storage._connect()
        try:
            cursor = conn.execute("PRAGMA table_info(scribe_projects);")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            assert 'docs_json' in column_names, "New database should have docs_json column"
        finally:
            conn.close()


class TestIntegration:
    """Integration tests for complete migration workflow."""

    def test_full_migration_workflow(self):
        """Test complete migration: CREATE TABLE -> migrate -> backfill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            state_path = Path(tmpdir) / "state.json"

            # Create state.json
            state_data = {
                "projects": {
                    "integration_test": {
                        "name": "integration_test",
                        "root": "/tmp/integration",
                        "progress_log": "/tmp/integration/PROGRESS_LOG.md",
                        "docs": {
                            "architecture": "/tmp/integration/ARCH.md"
                        }
                    }
                }
            }
            with open(state_path, 'w') as f:
                json.dump(state_data, f)

            # Create old-schema database
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scribe_projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        repo_root TEXT NOT NULL,
                        progress_log_path TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.execute(
                    "INSERT INTO scribe_projects (name, repo_root, progress_log_path) VALUES (?, ?, ?)",
                    ("integration_test", "/tmp/integration", "/tmp/integration/PROGRESS_LOG.md")
                )
                conn.commit()
            finally:
                conn.close()

            # Now run migration workflow
            storage = SQLiteStorage(db_path)

            # Step 1: Add column
            run(storage.migrate_add_docs_json_column())

            # Step 2: Backfill
            backfilled = run(storage.backfill_docs_json_from_state(state_path))
            assert backfilled == 1

            # Verify final state
            conn = storage._connect()
            try:
                cursor = conn.execute(
                    "SELECT docs_json FROM scribe_projects WHERE name = ?",
                    ("integration_test",)
                )
                row = cursor.fetchone()
                assert row is not None
                assert row[0] is not None

                docs = json.loads(row[0])
                assert docs["architecture"] == "/tmp/integration/ARCH.md"
            finally:
                conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
