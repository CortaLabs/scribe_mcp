"""Unit tests for reminder_history schema migration."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Add the MCP_SPINE directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.storage.sqlite import SQLiteStorage


def run(coro):
    """Execute an async coroutine from a synchronous test."""
    return asyncio.run(coro)


@pytest.fixture
def storage(tmp_path):
    """Provide an isolated SQLite storage instance."""
    db_path = tmp_path / "test_reminder_history.db"
    storage = SQLiteStorage(db_path)
    run(storage.setup())
    yield storage
    run(storage.close())


class TestReminderHistorySchema:
    """Test suite for reminder_history table schema."""

    def test_reminder_history_table_exists(self, storage):
        """Verify reminder_history table is created during schema initialization."""
        conn = storage._connect()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reminder_history';"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None, "reminder_history table should exist"
        assert result["name"] == "reminder_history"

    def test_reminder_history_columns(self, storage):
        """Verify all expected columns exist with correct types."""
        conn = storage._connect()
        cursor = conn.execute("PRAGMA table_info(reminder_history);")
        columns = {row["name"]: row for row in cursor.fetchall()}
        conn.close()

        # Verify all 10 columns exist
        expected_columns = {
            "id",
            "session_id",
            "reminder_hash",
            "project_root",
            "agent_id",
            "tool_name",
            "reminder_key",
            "shown_at",
            "operation_status",
            "context_metadata",
        }
        assert set(columns.keys()) == expected_columns, "All 10 columns should exist"

        # Verify column constraints
        assert columns["id"]["pk"] == 1, "id should be primary key"
        assert columns["session_id"]["notnull"] == 1, "session_id should be NOT NULL"
        assert columns["reminder_hash"]["notnull"] == 1, "reminder_hash should be NOT NULL"
        assert columns["shown_at"]["notnull"] == 1, "shown_at should be NOT NULL"
        assert columns["operation_status"]["notnull"] == 1, "operation_status should be NOT NULL"
        assert columns["operation_status"]["dflt_value"] == "'neutral'", "operation_status default should be 'neutral'"

    def test_reminder_history_foreign_key_constraint(self, storage):
        """Verify FK constraint to scribe_sessions.session_id exists."""
        conn = storage._connect()
        cursor = conn.execute("PRAGMA foreign_key_list(reminder_history);")
        foreign_keys = cursor.fetchall()
        conn.close()

        assert len(foreign_keys) == 1, "Should have exactly 1 foreign key"
        fk = foreign_keys[0]
        assert fk["table"] == "scribe_sessions", "FK should reference scribe_sessions"
        assert fk["from"] == "session_id", "FK should be on session_id column"
        assert fk["to"] == "session_id", "FK should reference session_id column"
        assert fk["on_delete"] == "CASCADE", "FK should cascade on delete"

    def test_reminder_history_check_constraint(self, storage):
        """Verify CHECK constraint on operation_status."""
        conn = storage._connect()

        # Insert a test session first (required for FK constraint)
        conn.execute(
            """INSERT INTO scribe_sessions
            (session_id, mode, started_at, last_active_at)
            VALUES (?, 'sentinel', datetime('now'), datetime('now'))""",
            ("test-session-check",),
        )
        conn.commit()

        # Insert valid operation_status values
        for status in ["success", "failure", "neutral"]:
            conn.execute(
                """INSERT INTO reminder_history
                (session_id, reminder_hash, shown_at, operation_status)
                VALUES (?, ?, datetime('now'), ?)""",
                ("test-session-check", f"hash-{status}", status),
            )
        conn.commit()

        # Verify inserts succeeded
        cursor = conn.execute("SELECT COUNT(*) as count FROM reminder_history;")
        assert cursor.fetchone()["count"] == 3, "3 valid inserts should succeed"

        # Attempt invalid operation_status - should fail
        with pytest.raises(Exception) as exc_info:
            conn.execute(
                """INSERT INTO reminder_history
                (session_id, reminder_hash, shown_at, operation_status)
                VALUES (?, ?, datetime('now'), ?)""",
                ("test-session-check", "hash-invalid", "invalid_status"),
            )
            conn.commit()

        conn.close()
        assert "CHECK constraint failed" in str(exc_info.value), "Invalid operation_status should fail CHECK constraint"

    def test_reminder_history_indexes_exist(self, storage):
        """Verify all 3 indexes are created."""
        conn = storage._connect()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='reminder_history';"
        )
        indexes = {row["name"] for row in cursor.fetchall()}
        conn.close()

        expected_indexes = {
            "idx_reminder_history_session_hash",
            "idx_reminder_history_shown_at",
            "idx_reminder_history_session_tool",
        }
        assert expected_indexes.issubset(indexes), "All 3 indexes should exist"

    def test_reminder_history_index_columns(self, storage):
        """Verify index column definitions."""
        conn = storage._connect()

        # Check idx_reminder_history_session_hash (composite: session_id, reminder_hash)
        cursor = conn.execute("PRAGMA index_info(idx_reminder_history_session_hash);")
        columns = [row["name"] for row in cursor.fetchall()]
        assert columns == ["session_id", "reminder_hash"], "session_hash index should cover (session_id, reminder_hash)"

        # Check idx_reminder_history_shown_at
        cursor = conn.execute("PRAGMA index_info(idx_reminder_history_shown_at);")
        columns = [row["name"] for row in cursor.fetchall()]
        assert columns == ["shown_at"], "shown_at index should cover shown_at column"

        # Check idx_reminder_history_session_tool (composite: session_id, tool_name)
        cursor = conn.execute("PRAGMA index_info(idx_reminder_history_session_tool);")
        columns = [row["name"] for row in cursor.fetchall()]
        assert columns == ["session_id", "tool_name"], "session_tool index should cover (session_id, tool_name)"

        conn.close()

    def test_reminder_history_cascade_delete(self, storage):
        """Verify CASCADE delete behavior when session is deleted."""
        conn = storage._connect()

        # Insert a test session
        conn.execute(
            """INSERT INTO scribe_sessions
            (session_id, mode, started_at, last_active_at)
            VALUES (?, 'sentinel', datetime('now'), datetime('now'))""",
            ("test-session-cascade",),
        )

        # Insert reminder history entries for this session
        for i in range(3):
            conn.execute(
                """INSERT INTO reminder_history
                (session_id, reminder_hash, shown_at, operation_status)
                VALUES (?, ?, datetime('now'), 'neutral')""",
                ("test-session-cascade", f"hash-{i}"),
            )
        conn.commit()

        # Verify reminder entries exist
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM reminder_history WHERE session_id = ?;",
            ("test-session-cascade",),
        )
        assert cursor.fetchone()["count"] == 3, "3 reminder entries should exist"

        # Delete the session
        conn.execute("DELETE FROM scribe_sessions WHERE session_id = ?;", ("test-session-cascade",))
        conn.commit()

        # Verify reminder entries were CASCADE deleted
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM reminder_history WHERE session_id = ?;",
            ("test-session-cascade",),
        )
        assert cursor.fetchone()["count"] == 0, "Reminder entries should be CASCADE deleted"

        conn.close()

    def test_reminder_history_insert_and_query(self, storage):
        """Verify basic insert and query operations work correctly."""
        conn = storage._connect()

        # Insert a session
        conn.execute(
            """INSERT INTO scribe_sessions
            (session_id, mode, started_at, last_active_at)
            VALUES (?, 'project', datetime('now'), datetime('now'))""",
            ("test-session-ops",),
        )

        # Insert reminder history entry
        conn.execute(
            """INSERT INTO reminder_history
            (session_id, reminder_hash, project_root, agent_id, tool_name,
             reminder_key, shown_at, operation_status, context_metadata)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)""",
            (
                "test-session-ops",
                "hash-test-123",
                "/path/to/project",
                "agent-123",
                "append_entry",
                "log_warning",
                "success",
                '{"context": "test"}',
            ),
        )
        conn.commit()

        # Query the entry
        cursor = conn.execute(
            """SELECT session_id, reminder_hash, project_root, agent_id, tool_name,
                      reminder_key, operation_status, context_metadata
               FROM reminder_history
               WHERE session_id = ? AND reminder_hash = ?;""",
            ("test-session-ops", "hash-test-123"),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "Inserted row should be queryable"
        assert row["session_id"] == "test-session-ops"
        assert row["reminder_hash"] == "hash-test-123"
        assert row["project_root"] == "/path/to/project"
        assert row["agent_id"] == "agent-123"
        assert row["tool_name"] == "append_entry"
        assert row["reminder_key"] == "log_warning"
        assert row["operation_status"] == "success"
        assert row["context_metadata"] == '{"context": "test"}'

    def test_reminder_history_no_breaking_changes(self, storage):
        """Verify schema addition doesn't break existing tables."""
        conn = storage._connect()

        # Verify critical existing tables still exist
        cursor = conn.execute(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name IN
               ('scribe_projects', 'scribe_entries', 'scribe_sessions');"""
        )
        tables = {row["name"] for row in cursor.fetchall()}
        conn.close()

        assert tables == {"scribe_projects", "scribe_entries", "scribe_sessions"}, \
            "Existing critical tables should still exist"
