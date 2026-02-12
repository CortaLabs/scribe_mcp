#!/usr/bin/env python3
"""Unit tests for SQLiteConnectionPool.

Tests the thread-safe connection pool implementation in storage/pool.py.
Verifies connection lifecycle, thread safety, and proper resource cleanup.
"""

import sqlite3
import threading
import time
import pytest

from scribe_mcp.storage.pool import SQLiteConnectionPool


class TestConnectionPoolBasic:
    """Basic functionality tests for SQLiteConnectionPool."""

    def test_pool_initialization(self, tmp_path):
        """Test pool initializes with correct defaults."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=1, max_size=3)

        assert pool.size == 0  # Pool starts empty (lazy initialization)
        assert pool.active == 0
        assert pool.total == 0
        assert not pool.is_closed

        pool.close_all()

    def test_pool_invalid_params(self, tmp_path):
        """Test pool rejects invalid initialization parameters."""
        db_path = tmp_path / "test.db"

        with pytest.raises(ValueError, match="min_size must be >= 0"):
            SQLiteConnectionPool(db_path, min_size=-1, max_size=3)

        with pytest.raises(ValueError, match="max_size must be >= 1"):
            SQLiteConnectionPool(db_path, min_size=0, max_size=0)

        with pytest.raises(ValueError, match="min_size cannot exceed max_size"):
            SQLiteConnectionPool(db_path, min_size=5, max_size=3)

    def test_acquire_creates_connection(self, tmp_path):
        """Test acquire() creates a new connection when pool is empty."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        conn = pool.acquire()

        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)
        assert pool.active == 1
        assert pool.size == 0  # Connection is in use, not in pool

        pool.release(conn)
        pool.close_all()

    def test_release_returns_connection_to_pool(self, tmp_path):
        """Test release() returns connection to pool for reuse."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        conn = pool.acquire()
        assert pool.active == 1
        assert pool.size == 0

        pool.release(conn)
        assert pool.active == 0
        assert pool.size == 1  # Connection returned to pool

        pool.close_all()

    def test_connection_reuse(self, tmp_path):
        """Test connections are reused from pool."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        # Acquire and release a connection
        conn1 = pool.acquire()
        conn1_id = id(conn1)
        pool.release(conn1)

        # Acquire again - should get the same connection
        conn2 = pool.acquire()
        assert id(conn2) == conn1_id  # Same object

        pool.release(conn2)
        pool.close_all()

    def test_connection_setup_matches_sqlite_storage(self, tmp_path):
        """Test connections have proper PRAGMA settings."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        conn = pool.acquire()

        # Verify row_factory
        assert conn.row_factory == sqlite3.Row

        # Verify foreign_keys is ON
        cursor = conn.execute("PRAGMA foreign_keys;")
        result = cursor.fetchone()
        assert result[0] == 1  # 1 means ON

        # Verify busy_timeout
        cursor = conn.execute("PRAGMA busy_timeout;")
        result = cursor.fetchone()
        assert result[0] == 5000  # SQLITE_BUSY_TIMEOUT_MS

        pool.release(conn)
        pool.close_all()


class TestConnectionPoolMaxSize:
    """Tests for max_size behavior and blocking."""

    def test_max_size_limit_enforced(self, tmp_path):
        """Test pool respects max_size limit."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=2)

        conn1 = pool.acquire()
        conn2 = pool.acquire()

        assert pool.active == 2
        assert pool.total == 2

        # Third acquire should block (we'll test with timeout)
        with pytest.raises(TimeoutError):
            pool.acquire(timeout=0.1)

        pool.release(conn1)
        pool.release(conn2)
        pool.close_all()

    def test_acquire_blocks_until_release(self, tmp_path):
        """Test acquire() blocks when at max_size and unblocks on release."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=1)

        conn1 = pool.acquire()
        result = {"acquired": False}

        def try_acquire():
            conn = pool.acquire()  # Should block
            result["acquired"] = True
            pool.release(conn)

        thread = threading.Thread(target=try_acquire)
        thread.start()

        # Give thread time to start and block
        time.sleep(0.1)
        assert not result["acquired"]

        # Release connection - thread should unblock
        pool.release(conn1)
        thread.join(timeout=1.0)

        assert result["acquired"]
        pool.close_all()

    def test_acquire_timeout_zero_nonblocking(self, tmp_path):
        """Test timeout=0 makes acquire non-blocking."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=1)

        conn = pool.acquire()

        # With timeout=0, should raise immediately
        with pytest.raises(TimeoutError, match="non-blocking"):
            pool.acquire(timeout=0)

        pool.release(conn)
        pool.close_all()


class TestConnectionPoolContextManager:
    """Tests for context manager interface."""

    def test_context_manager_basic(self, tmp_path):
        """Test context manager acquires and releases properly."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        with pool.connection() as conn:
            assert conn is not None
            assert pool.active == 1

            # Can execute queries
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.execute("INSERT INTO test VALUES (1)")

        assert pool.active == 0
        assert pool.size == 1  # Returned to pool

        pool.close_all()

    def test_context_manager_exception_releases(self, tmp_path):
        """Test context manager releases connection even on exception."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        try:
            with pool.connection() as conn:
                assert pool.active == 1
                raise RuntimeError("Test exception")
        except RuntimeError:
            pass

        assert pool.active == 0
        assert pool.size == 1  # Connection returned despite exception

        pool.close_all()


class TestConnectionPoolShutdown:
    """Tests for pool shutdown behavior."""

    def test_close_all_closes_pooled_connections(self, tmp_path):
        """Test close_all() closes all pooled connections."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        # Create and return a connection
        conn = pool.acquire()
        pool.release(conn)
        assert pool.size == 1

        pool.close_all()

        assert pool.is_closed
        assert pool.size == 0

    def test_close_all_prevents_new_acquisitions(self, tmp_path):
        """Test close_all() prevents new acquire() calls."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        pool.close_all()

        with pytest.raises(RuntimeError, match="closed"):
            pool.acquire()

    def test_close_all_idempotent(self, tmp_path):
        """Test close_all() can be called multiple times safely."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        pool.close_all()
        pool.close_all()  # Should not raise
        pool.close_all()  # Should not raise

        assert pool.is_closed

    def test_release_after_close_discards_connection(self, tmp_path):
        """Test releasing connection after close_all() discards it."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        conn = pool.acquire()
        pool.close_all()

        # Release should work but discard the connection
        pool.release(conn)
        assert pool.size == 0


class TestConnectionPoolThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_acquire_release(self, tmp_path):
        """Test concurrent acquire/release from multiple threads."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=5)

        results = {"success": 0, "errors": []}
        num_threads = 10
        operations_per_thread = 20

        def worker():
            for _ in range(operations_per_thread):
                try:
                    with pool.connection() as conn:
                        # Do a simple query
                        conn.execute("SELECT 1")
                        time.sleep(0.001)  # Small delay to increase contention
                    results["success"] += 1
                except Exception as e:
                    results["errors"].append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["success"] == num_threads * operations_per_thread
        assert len(results["errors"]) == 0

        pool.close_all()

    def test_stats_thread_safe(self, tmp_path):
        """Test stats() is thread-safe."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=5)

        # Acquire a connection
        conn = pool.acquire()

        stats = pool.stats()
        assert stats["active"] == 1
        assert stats["pooled"] == 0
        assert stats["total"] == 1
        assert stats["max_size"] == 5
        assert stats["closed"] is False

        pool.release(conn)
        pool.close_all()


class TestConnectionPoolValidation:
    """Tests for connection validation."""

    def test_invalid_connection_discarded_on_acquire(self, tmp_path):
        """Test invalid connections are discarded when acquired."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=0, max_size=3)

        # Get a connection and close it manually (making it invalid)
        conn = pool.acquire()
        pool.release(conn)

        # Manually close the connection in the pool
        # (simulating a connection that became invalid)
        pool._pool[0].close()

        # Next acquire should detect invalid connection and create new one
        conn2 = pool.acquire()
        assert conn2 is not None

        # Should be able to execute queries
        conn2.execute("SELECT 1")

        pool.release(conn2)
        pool.close_all()


class TestConnectionPoolRepr:
    """Tests for string representation."""

    def test_repr(self, tmp_path):
        """Test __repr__ returns useful information."""
        db_path = tmp_path / "test.db"
        pool = SQLiteConnectionPool(db_path, min_size=1, max_size=5)

        repr_str = repr(pool)

        assert "SQLiteConnectionPool" in repr_str
        assert str(db_path) in repr_str
        assert "max=5" in repr_str
        assert "closed=False" in repr_str

        pool.close_all()
