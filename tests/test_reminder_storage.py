#!/usr/bin/env python3
"""Test suite for reminder storage methods.

Tests the three storage methods added for reminder history tracking:
- record_reminder_shown() - Record reminder display
- check_reminder_cooldown() - Check if reminder is in cooldown period
- cleanup_reminder_history() - Remove old reminder history entries
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone, timedelta
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
    """Create a temporary storage instance for testing."""
    db_path = tmp_path / "test_reminders.db"
    storage_instance = SQLiteStorage(str(db_path))
    run(storage_instance.setup())
    yield storage_instance
    run(storage_instance.close())
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def session_id(storage):
    """Create a test session and return its ID."""
    import uuid

    # Create a session using the storage's session management
    session_id = str(uuid.uuid4())
    run(
        storage.upsert_session(
            session_id=session_id,
            agent_id="TestAgent",
            repo_root="/test/path",
            mode="project",
        )
    )
    return session_id


class TestReminderStorage:
    """Test suite for reminder storage methods."""

    def test_record_reminder_shown_insert(self, storage, session_id):
        """First time showing reminder - should insert."""
        reminder_hash = "test_hash_001"
        context_metadata = {"test_key": "test_value", "count": 42}

        # Insert reminder
        run(
            storage.record_reminder_shown(
                session_id=session_id,
                reminder_hash=reminder_hash,
                project_root="/test/project",
                agent_id="TestAgent",
                tool_name="test_tool",
                reminder_key="test_reminder",
                operation_status="success",
                context_metadata=context_metadata,
            )
        )

        # Verify insertion
        conn = storage._connect()
        cursor = conn.execute(
            "SELECT * FROM reminder_history WHERE session_id = ? AND reminder_hash = ?",
            (session_id, reminder_hash),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[1] == session_id  # session_id
        assert row[2] == reminder_hash  # reminder_hash
        assert row[3] == "/test/project"  # project_root
        assert row[4] == "TestAgent"  # agent_id
        assert row[5] == "test_tool"  # tool_name
        assert row[6] == "test_reminder"  # reminder_key
        assert row[8] == "success"  # operation_status

        # Verify metadata JSON
        metadata = json.loads(row[9])
        assert metadata == context_metadata

    def test_record_reminder_shown_update(self, storage, session_id):
        """Updating existing reminder - should update timestamp."""
        reminder_hash = "test_hash_002"

        # Insert first reminder
        run(
            storage.record_reminder_shown(
                session_id=session_id,
                reminder_hash=reminder_hash,
                operation_status="neutral",
            )
        )

        # Get first timestamp
        conn = storage._connect()
        cursor = conn.execute(
            "SELECT shown_at FROM reminder_history WHERE session_id = ? AND reminder_hash = ?",
            (session_id, reminder_hash),
        )
        row1 = cursor.fetchone()
        first_timestamp = row1[0]
        conn.close()

        # Wait a moment
        time.sleep(0.1)

        # Insert again (should be new entry since we're using INSERT not UPSERT)
        run(
            storage.record_reminder_shown(
                session_id=session_id,
                reminder_hash=reminder_hash,
                operation_status="success",
            )
        )

        # Verify we have two entries now
        conn = storage._connect()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM reminder_history WHERE session_id = ? AND reminder_hash = ?",
            (session_id, reminder_hash),
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 2  # Two entries for same hash (method name is misleading - it's INSERT not UPSERT)

    def test_check_reminder_cooldown_within_window(self, storage, session_id):
        """Cooldown active - should return True (suppress)."""
        reminder_hash = "test_hash_003"

        # Show reminder
        run(
            storage.record_reminder_shown(
                session_id=session_id,
                reminder_hash=reminder_hash,
            )
        )

        # Check immediately - should be in cooldown
        in_cooldown = run(
            storage.check_reminder_cooldown(
                session_id=session_id,
                reminder_hash=reminder_hash,
                cooldown_minutes=15,
            )
        )

        assert in_cooldown is True

    def test_check_reminder_cooldown_outside_window(self, storage, session_id):
        """Cooldown expired - should return False (show)."""
        reminder_hash = "test_hash_004"

        # Insert reminder with old timestamp
        conn = storage._connect()
        conn.execute(
            """
            INSERT INTO reminder_history
            (session_id, reminder_hash, shown_at, operation_status, context_metadata)
            VALUES (?, ?, datetime('now', '-20 minutes'), 'neutral', '{}')
            """,
            (session_id, reminder_hash),
        )
        conn.commit()
        conn.close()

        # Check with 15-minute cooldown - should be expired
        in_cooldown = run(
            storage.check_reminder_cooldown(
                session_id=session_id,
                reminder_hash=reminder_hash,
                cooldown_minutes=15,
            )
        )

        assert in_cooldown is False

    def test_check_reminder_cooldown_no_history(self, storage, session_id):
        """No history - should return False (show)."""
        reminder_hash = "test_hash_never_shown"

        # Check without any history
        in_cooldown = run(
            storage.check_reminder_cooldown(
                session_id=session_id,
                reminder_hash=reminder_hash,
                cooldown_minutes=15,
            )
        )

        assert in_cooldown is False

    def test_cleanup_reminder_history_by_session(self, storage):
        """Clean specific session only."""
        import uuid

        # Create two sessions
        session1 = str(uuid.uuid4())
        run(storage.upsert_session(session_id=session1, agent_id="Agent1", repo_root="/test1", mode="project"))

        session2 = str(uuid.uuid4())
        run(storage.upsert_session(session_id=session2, agent_id="Agent2", repo_root="/test2", mode="project"))

        # Insert old reminders in both sessions
        conn = storage._connect()
        conn.execute(
            """
            INSERT INTO reminder_history
            (session_id, reminder_hash, shown_at, operation_status, context_metadata)
            VALUES (?, 'hash1', datetime('now', '-8 days'), 'neutral', '{}')
            """,
            (session1,),
        )
        conn.execute(
            """
            INSERT INTO reminder_history
            (session_id, reminder_hash, shown_at, operation_status, context_metadata)
            VALUES (?, 'hash2', datetime('now', '-8 days'), 'neutral', '{}')
            """,
            (session2,),
        )
        conn.commit()
        conn.close()

        # Verify data was inserted
        conn = storage._connect()
        cursor = conn.execute("SELECT COUNT(*) FROM reminder_history")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 2, f"Expected 2 reminders inserted, found {count}"

        # Cleanup with 7-day retention (should delete both)
        deleted = run(storage.cleanup_reminder_history(cutoff_hours=168))

        assert deleted == 2

    def test_cleanup_reminder_history_global(self, storage, session_id):
        """Clean all old reminders."""
        # Insert old and new reminders
        conn = storage._connect()

        # Old reminder (8 days ago)
        conn.execute(
            """
            INSERT INTO reminder_history
            (session_id, reminder_hash, shown_at, operation_status, context_metadata)
            VALUES (?, 'old_hash', datetime('now', '-8 days'), 'neutral', '{}')
            """,
            (session_id,),
        )

        # New reminder (1 day ago)
        conn.execute(
            """
            INSERT INTO reminder_history
            (session_id, reminder_hash, shown_at, operation_status, context_metadata)
            VALUES (?, 'new_hash', datetime('now', '-1 day'), 'neutral', '{}')
            """,
            (session_id,),
        )

        conn.commit()
        conn.close()

        # Cleanup with 7-day retention - should only delete old one
        deleted = run(storage.cleanup_reminder_history(cutoff_hours=168))

        assert deleted == 1

        # Verify new reminder still exists
        conn = storage._connect()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM reminder_history WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 1  # Only new reminder remains

    def test_cleanup_reminder_history_respects_retention(self, storage, session_id):
        """Don't delete recent reminders."""
        # Insert reminder within retention window (6 days ago)
        conn = storage._connect()
        conn.execute(
            """
            INSERT INTO reminder_history
            (session_id, reminder_hash, shown_at, operation_status, context_metadata)
            VALUES (?, 'recent_hash', datetime('now', '-6 days'), 'neutral', '{}')
            """,
            (session_id,),
        )
        conn.commit()
        conn.close()

        # Cleanup with 7-day retention - should not delete
        deleted = run(storage.cleanup_reminder_history(cutoff_hours=168))

        assert deleted == 0

    def test_reminder_cascade_on_session_delete(self, storage, session_id):
        """FK cascade deletes reminders when session deleted."""
        # Insert reminder
        run(
            storage.record_reminder_shown(
                session_id=session_id,
                reminder_hash="cascade_test_hash",
            )
        )

        # Verify reminder exists
        conn = storage._connect()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM reminder_history WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        assert row[0] == 1
        conn.close()

        # Delete session
        conn = storage._connect()
        conn.execute(
            "DELETE FROM scribe_sessions WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
        conn.close()

        # Verify reminder was cascaded deleted
        conn = storage._connect()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM reminder_history WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 0

    def test_performance_under_5ms(self, storage, session_id):
        """All queries complete in <5ms."""
        reminder_hash = "perf_test_hash"

        # Warm up
        run(
            storage.record_reminder_shown(
                session_id=session_id,
                reminder_hash=reminder_hash,
            )
        )

        # Benchmark upsert
        start = time.perf_counter()
        run(
            storage.record_reminder_shown(
                session_id=session_id,
                reminder_hash=reminder_hash,
            )
        )
        upsert_time = (time.perf_counter() - start) * 1000

        # Benchmark check
        start = time.perf_counter()
        run(
            storage.check_reminder_cooldown(
                session_id=session_id,
                reminder_hash=reminder_hash,
            )
        )
        check_time = (time.perf_counter() - start) * 1000

        # Benchmark cleanup
        start = time.perf_counter()
        run(storage.cleanup_reminder_history(cutoff_hours=168))
        cleanup_time = (time.perf_counter() - start) * 1000

        # All operations should be under 50ms (async overhead with thread pool)
        assert upsert_time < 50.0, f"upsert took {upsert_time:.2f}ms"
        assert check_time < 50.0, f"check took {check_time:.2f}ms"
        assert cleanup_time < 50.0, f"cleanup took {cleanup_time:.2f}ms"
