"""Thread-safe SQLite connection pool for Scribe MCP.

This module provides connection pooling to eliminate the overhead of creating
new database connections for each operation. The pool maintains a set of
reusable connections with proper initialization (PRAGMA settings, row factory).

Usage:
    pool = SQLiteConnectionPool(db_path, min_size=1, max_size=3)

    # Acquire/release pattern
    conn = pool.acquire()
    try:
        cursor = conn.execute("SELECT * FROM ...")
        # ... use connection
    finally:
        pool.release(conn)

    # Context manager pattern (preferred)
    with pool.connection() as conn:
        cursor = conn.execute("SELECT * FROM ...")
        # ... use connection

    # Shutdown
    pool.close_all()

Thread Safety:
    The pool is thread-safe and can be used from multiple threads concurrently.
    When the pool is exhausted, acquire() will block until a connection becomes
    available or a new one can be created (up to max_size).

Connection Validation:
    Connections are validated before being returned from acquire(). Invalid
    connections (closed or corrupted) are discarded and a fresh connection
    is created.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

# Connection configuration constants (must match sqlite.py)
SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = 5000

logger = logging.getLogger(__name__)


class SQLiteConnectionPool:
    """Thread-safe SQLite connection pool.

    This pool manages a set of reusable SQLite connections. Connections are
    initialized with the same PRAGMA settings as the direct _connect() method
    in SQLiteStorage to ensure consistency.

    Attributes:
        db_path: Path to the SQLite database file.
        min_size: Minimum number of connections to keep in the pool.
        max_size: Maximum number of connections allowed (pool + active).

    Thread Safety:
        All public methods are thread-safe. The pool uses a lock for state
        mutations and a condition variable for blocking acquire() calls.

    Example:
        pool = SQLiteConnectionPool(Path("db.sqlite"), min_size=1, max_size=3)

        with pool.connection() as conn:
            rows = conn.execute("SELECT * FROM my_table").fetchall()

        pool.close_all()
    """

    def __init__(
        self,
        db_path: Path,
        min_size: int = 1,
        max_size: int = 3,
        timeout_seconds: int = SQLITE_TIMEOUT_SECONDS,
        busy_timeout_ms: int = SQLITE_BUSY_TIMEOUT_MS,
    ) -> None:
        """Initialize the connection pool.

        Args:
            db_path: Path to the SQLite database file.
            min_size: Minimum connections to maintain in the pool. Connections
                are created lazily, so this is a target rather than immediate.
            max_size: Maximum total connections (pooled + in-use). When all
                connections are in use and max is reached, acquire() will block.
            timeout_seconds: SQLite connection timeout (SQLITE_TIMEOUT_SECONDS).
            busy_timeout_ms: SQLite busy timeout in milliseconds.

        Raises:
            ValueError: If min_size < 0, max_size < 1, or min_size > max_size.
        """
        if min_size < 0:
            raise ValueError("min_size must be >= 0")
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if min_size > max_size:
            raise ValueError("min_size cannot exceed max_size")

        self._db_path = Path(db_path).expanduser()
        self._min_size = min_size
        self._max_size = max_size
        self._timeout_seconds = timeout_seconds
        self._busy_timeout_ms = busy_timeout_ms

        # Pool of available connections
        self._pool: deque[sqlite3.Connection] = deque()

        # Count of connections currently in use (not in pool)
        self._active_count = 0

        # Lock protects _pool and _active_count
        self._lock = threading.Lock()

        # Condition for blocking when pool is exhausted
        self._not_full = threading.Condition(self._lock)

        # Flag to prevent new acquisitions during shutdown
        self._closed = False

        logger.debug(
            "SQLiteConnectionPool initialized: path=%s, min_size=%d, max_size=%d",
            self._db_path, self._min_size, self._max_size
        )

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with proper initialization.

        This method creates a connection with the same settings as
        SQLiteStorage._connect() to ensure consistency.

        Returns:
            Initialized sqlite3.Connection ready for use.

        Raises:
            sqlite3.Error: If connection creation fails.
        """
        conn = sqlite3.connect(
            str(self._db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=self._timeout_seconds,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")

        logger.debug("Created new connection for pool")
        return conn

    def _validate_connection(self, conn: sqlite3.Connection) -> bool:
        """Check if a connection is still valid and usable.

        Args:
            conn: Connection to validate.

        Returns:
            True if connection is valid, False otherwise.
        """
        try:
            # Simple query to verify connection is working
            conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            logger.debug("Connection validation failed, will discard")
            return False

    def _total_connections(self) -> int:
        """Return total connections (pooled + active).

        Must be called with _lock held.
        """
        return len(self._pool) + self._active_count

    def acquire(self, timeout: Optional[float] = None) -> sqlite3.Connection:
        """Acquire a connection from the pool.

        This method returns an available connection from the pool. If no
        connections are available:
        - If under max_size, creates a new connection
        - If at max_size, blocks until a connection is released

        Args:
            timeout: Maximum seconds to wait for a connection. None means
                wait indefinitely. 0 means non-blocking (raise immediately
                if no connection available).

        Returns:
            A valid sqlite3.Connection.

        Raises:
            RuntimeError: If pool is closed.
            TimeoutError: If timeout expires before getting a connection.
            sqlite3.Error: If connection creation fails.
        """
        with self._not_full:
            if self._closed:
                raise RuntimeError("Connection pool is closed")

            deadline = None
            if timeout is not None:
                import time
                deadline = time.monotonic() + timeout

            while True:
                # Try to get a connection from the pool
                while self._pool:
                    conn = self._pool.popleft()
                    if self._validate_connection(conn):
                        self._active_count += 1
                        logger.debug(
                            "Acquired connection from pool: active=%d, pooled=%d",
                            self._active_count, len(self._pool)
                        )
                        return conn
                    else:
                        # Connection is invalid, close it and try next
                        try:
                            conn.close()
                        except sqlite3.Error:
                            pass

                # Pool is empty - can we create a new connection?
                if self._total_connections() < self._max_size:
                    self._active_count += 1
                    # Release lock while creating connection
                    self._lock.release()
                    try:
                        conn = self._create_connection()
                        logger.debug(
                            "Created new connection: active=%d, pooled=%d",
                            self._active_count, len(self._pool)
                        )
                        return conn
                    except Exception:
                        # Creation failed, decrement count
                        with self._lock:
                            self._active_count -= 1
                        raise
                    finally:
                        self._lock.acquire()

                # At max_size, must wait for a connection to be released
                if timeout == 0:
                    raise TimeoutError("No connection available (non-blocking)")

                remaining = None
                if deadline is not None:
                    import time
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Timed out waiting for connection")

                logger.debug("Pool exhausted, waiting for connection release")
                notified = self._not_full.wait(remaining)

                if self._closed:
                    raise RuntimeError("Connection pool was closed while waiting")

                if not notified and deadline is not None:
                    import time
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for connection")

    def release(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool.

        The connection is returned to the pool for reuse. If the pool is
        closed or the connection is invalid, it is closed instead.

        Args:
            conn: Connection to return to the pool.
        """
        with self._not_full:
            self._active_count -= 1

            if self._closed:
                # Pool is closed, just close the connection
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
                logger.debug("Released connection (closed pool)")
                return

            # Validate before returning to pool
            if self._validate_connection(conn):
                self._pool.append(conn)
                logger.debug(
                    "Released connection to pool: active=%d, pooled=%d",
                    self._active_count, len(self._pool)
                )
            else:
                # Connection is bad, discard it
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
                logger.debug("Discarded invalid connection on release")

            # Notify any waiting threads
            self._not_full.notify()

    @contextmanager
    def connection(self, timeout: Optional[float] = None) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for acquiring and releasing connections.

        This is the preferred way to use connections as it guarantees
        the connection is released even if an exception occurs.

        Args:
            timeout: Maximum seconds to wait for a connection.

        Yields:
            A valid sqlite3.Connection.

        Example:
            with pool.connection() as conn:
                rows = conn.execute("SELECT * FROM table").fetchall()
        """
        conn = self.acquire(timeout)
        try:
            yield conn
        finally:
            self.release(conn)

    def close_all(self) -> None:
        """Close all connections and shut down the pool.

        After calling this method, no new connections can be acquired.
        Active connections should still be released, but they will be
        closed rather than returned to the pool.

        This method is idempotent and can be called multiple times safely.
        """
        with self._not_full:
            self._closed = True

            # Close all pooled connections
            while self._pool:
                conn = self._pool.popleft()
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

            # Wake up any waiting threads so they can see pool is closed
            self._not_full.notify_all()

        logger.debug("Connection pool closed")

    @property
    def size(self) -> int:
        """Return the number of available connections in the pool."""
        with self._lock:
            return len(self._pool)

    @property
    def active(self) -> int:
        """Return the number of connections currently in use."""
        with self._lock:
            return self._active_count

    @property
    def total(self) -> int:
        """Return total connections (pooled + active)."""
        with self._lock:
            return self._total_connections()

    @property
    def is_closed(self) -> bool:
        """Return True if the pool has been closed."""
        with self._lock:
            return self._closed

    def stats(self) -> dict:
        """Return pool statistics as a dictionary.

        Returns:
            Dictionary with keys: pooled, active, total, max_size, closed
        """
        with self._lock:
            return {
                "pooled": len(self._pool),
                "active": self._active_count,
                "total": self._total_connections(),
                "max_size": self._max_size,
                "closed": self._closed,
            }

    def __repr__(self) -> str:
        """Return string representation of the pool."""
        with self._lock:
            return (
                f"SQLiteConnectionPool("
                f"path={self._db_path}, "
                f"pooled={len(self._pool)}, "
                f"active={self._active_count}, "
                f"max={self._max_size}, "
                f"closed={self._closed})"
            )
