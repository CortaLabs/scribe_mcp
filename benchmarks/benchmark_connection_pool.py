#!/usr/bin/env python3
"""Benchmark script for SQLite Connection Pool.

Measures the performance improvement of using SQLiteConnectionPool vs
direct sqlite3.connect()/close() for each operation.

Usage:
    python benchmarks/benchmark_connection_pool.py

Expected improvement: 50-80% latency reduction for typical operations.
"""

import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Tuple

from scribe_mcp.storage.pool import SQLiteConnectionPool


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    name: str
    iterations: int
    without_pool_total_ms: float
    with_pool_total_ms: float

    @property
    def without_pool_avg_ms(self) -> float:
        return self.without_pool_total_ms / self.iterations

    @property
    def with_pool_avg_ms(self) -> float:
        return self.with_pool_total_ms / self.iterations

    @property
    def improvement_percent(self) -> float:
        if self.without_pool_avg_ms == 0:
            return 0.0
        return ((self.without_pool_avg_ms - self.with_pool_avg_ms) /
                self.without_pool_avg_ms) * 100


def setup_test_db(db_path: Path) -> None:
    """Create test table matching Scribe's schema pattern."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_entries (
            id INTEGER PRIMARY KEY,
            project TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL,
            emoji TEXT,
            agent TEXT,
            timestamp_utc TEXT NOT NULL,
            meta_json TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bench_project ON benchmark_entries(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bench_timestamp ON benchmark_entries(timestamp_utc)")
    conn.commit()
    conn.close()


def seed_test_data(db_path: Path, count: int = 100) -> None:
    """Pre-populate database with test entries for SELECT benchmarks."""
    conn = sqlite3.connect(db_path)
    for i in range(count):
        conn.execute(
            """INSERT INTO benchmark_entries
               (project, message, status, emoji, agent, timestamp_utc, meta_json)
               VALUES (?, ?, ?, ?, ?, datetime('now'), ?)""",
            (f"project_{i % 5}", f"Message {i}", "info", "i", "benchmark", "{}")
        )
    conn.commit()
    conn.close()


def benchmark_without_pool_insert(db_path: Path, iterations: int) -> float:
    """Benchmark single INSERTs without connection pool.

    Each iteration: connect -> insert -> commit -> close
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO benchmark_entries
               (project, message, status, emoji, agent, timestamp_utc, meta_json)
               VALUES (?, ?, ?, ?, ?, datetime('now'), ?)""",
            ("bench_project", f"Without pool message {i}", "success", "s", "benchmark", "{}")
        )
        conn.commit()
        conn.close()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_with_pool_insert(db_path: Path, pool: SQLiteConnectionPool, iterations: int) -> float:
    """Benchmark single INSERTs with connection pool.

    Each iteration: acquire -> insert -> commit -> release
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        with pool.connection() as conn:
            conn.execute(
                """INSERT INTO benchmark_entries
                   (project, message, status, emoji, agent, timestamp_utc, meta_json)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), ?)""",
                ("bench_project", f"With pool message {i}", "success", "s", "benchmark", "{}")
            )
            conn.commit()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_without_pool_select(db_path: Path, iterations: int) -> float:
    """Benchmark single SELECTs without connection pool.

    Each iteration: connect -> select -> close
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """SELECT * FROM benchmark_entries
               WHERE project = ? ORDER BY timestamp_utc DESC LIMIT 10""",
            (f"project_{i % 5}",)
        )
        _ = cursor.fetchall()
        conn.close()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_with_pool_select(db_path: Path, pool: SQLiteConnectionPool, iterations: int) -> float:
    """Benchmark single SELECTs with connection pool.

    Each iteration: acquire -> select -> release
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        with pool.connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM benchmark_entries
                   WHERE project = ? ORDER BY timestamp_utc DESC LIMIT 10""",
                (f"project_{i % 5}",)
            )
            _ = cursor.fetchall()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_without_pool_batch_insert(db_path: Path, iterations: int, batch_size: int = 10) -> float:
    """Benchmark batch INSERTs without connection pool.

    Each iteration: connect -> N inserts -> commit -> close
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        conn = sqlite3.connect(db_path)
        for j in range(batch_size):
            conn.execute(
                """INSERT INTO benchmark_entries
                   (project, message, status, emoji, agent, timestamp_utc, meta_json)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), ?)""",
                ("batch_project", f"Batch {i} item {j}", "info", "i", "benchmark", "{}")
            )
        conn.commit()
        conn.close()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_with_pool_batch_insert(db_path: Path, pool: SQLiteConnectionPool,
                                      iterations: int, batch_size: int = 10) -> float:
    """Benchmark batch INSERTs with connection pool.

    Each iteration: acquire -> N inserts -> commit -> release
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        with pool.connection() as conn:
            for j in range(batch_size):
                conn.execute(
                    """INSERT INTO benchmark_entries
                       (project, message, status, emoji, agent, timestamp_utc, meta_json)
                       VALUES (?, ?, ?, ?, ?, datetime('now'), ?)""",
                    ("batch_project", f"Batch {i} item {j}", "info", "i", "benchmark", "{}")
                )
            conn.commit()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_without_pool_batch_select(db_path: Path, iterations: int, batch_size: int = 10) -> float:
    """Benchmark batch SELECTs without connection pool.

    Each iteration: connect -> N selects -> close
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        for j in range(batch_size):
            cursor = conn.execute(
                """SELECT * FROM benchmark_entries
                   WHERE project = ? ORDER BY timestamp_utc DESC LIMIT 10""",
                (f"project_{j % 5}",)
            )
            _ = cursor.fetchall()
        conn.close()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_with_pool_batch_select(db_path: Path, pool: SQLiteConnectionPool,
                                      iterations: int, batch_size: int = 10) -> float:
    """Benchmark batch SELECTs with connection pool.

    Each iteration: acquire -> N selects -> release
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        with pool.connection() as conn:
            for j in range(batch_size):
                cursor = conn.execute(
                    """SELECT * FROM benchmark_entries
                       WHERE project = ? ORDER BY timestamp_utc DESC LIMIT 10""",
                    (f"project_{j % 5}",)
                )
                _ = cursor.fetchall()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_without_pool_mixed(db_path: Path, iterations: int) -> float:
    """Benchmark mixed workload without connection pool.

    Each iteration: connect -> 5 inserts + 5 selects -> commit -> close
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # 5 INSERTs
        for j in range(5):
            conn.execute(
                """INSERT INTO benchmark_entries
                   (project, message, status, emoji, agent, timestamp_utc, meta_json)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), ?)""",
                ("mixed_project", f"Mixed {i} insert {j}", "info", "i", "benchmark", "{}")
            )
        # 5 SELECTs
        for j in range(5):
            cursor = conn.execute(
                """SELECT * FROM benchmark_entries
                   WHERE project = ? ORDER BY timestamp_utc DESC LIMIT 10""",
                (f"project_{j}",)
            )
            _ = cursor.fetchall()
        conn.commit()
        conn.close()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_with_pool_mixed(db_path: Path, pool: SQLiteConnectionPool, iterations: int) -> float:
    """Benchmark mixed workload with connection pool.

    Each iteration: acquire -> 5 inserts + 5 selects -> commit -> release
    Returns total time in milliseconds.
    """
    start = time.perf_counter()
    for i in range(iterations):
        with pool.connection() as conn:
            # 5 INSERTs
            for j in range(5):
                conn.execute(
                    """INSERT INTO benchmark_entries
                       (project, message, status, emoji, agent, timestamp_utc, meta_json)
                       VALUES (?, ?, ?, ?, ?, datetime('now'), ?)""",
                    ("mixed_project", f"Mixed {i} insert {j}", "info", "i", "benchmark", "{}")
                )
            # 5 SELECTs
            for j in range(5):
                cursor = conn.execute(
                    """SELECT * FROM benchmark_entries
                       WHERE project = ? ORDER BY timestamp_utc DESC LIMIT 10""",
                    (f"project_{j}",)
                )
                _ = cursor.fetchall()
            conn.commit()
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_connection_overhead_only(db_path: Path, iterations: int) -> Tuple[float, float]:
    """Benchmark ONLY connection creation/release overhead, no actual queries.

    This isolates the specific improvement from connection pooling by removing
    the database I/O from the measurement.

    Returns: (without_pool_ms, with_pool_ms)
    """
    # Without pool: just connect and close
    start = time.perf_counter()
    for _ in range(iterations):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Apply the same pragmas as the pool does
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.close()
    without_pool = (time.perf_counter() - start) * 1000

    # With pool: acquire and release
    pool = SQLiteConnectionPool(db_path, min_size=1, max_size=3)
    start = time.perf_counter()
    for _ in range(iterations):
        conn = pool.acquire()
        pool.release(conn)
    with_pool = (time.perf_counter() - start) * 1000
    pool.close_all()

    return without_pool, with_pool


def print_result(result: BenchmarkResult) -> None:
    """Print formatted benchmark result."""
    print(f"\nOperation: {result.name} ({result.iterations} iterations)")
    print(f"  Without pool: {result.without_pool_avg_ms:.3f}ms avg ({result.without_pool_total_ms:.1f}ms total)")
    print(f"  With pool:    {result.with_pool_avg_ms:.3f}ms avg ({result.with_pool_total_ms:.1f}ms total)")
    print(f"  Improvement:  {result.improvement_percent:.1f}%")


def run_benchmark(iterations: int = 100) -> List[BenchmarkResult]:
    """Run full benchmark suite and return results."""
    results = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "benchmark.db"

        # Setup
        setup_test_db(db_path)
        seed_test_data(db_path, count=500)

        # First: benchmark connection overhead only (most important metric)
        without_conn, with_conn = benchmark_connection_overhead_only(db_path, iterations)
        results.append(BenchmarkResult(
            name="Connection Overhead Only",
            iterations=iterations,
            without_pool_total_ms=without_conn,
            with_pool_total_ms=with_conn
        ))

        # Create pool with typical settings
        pool = SQLiteConnectionPool(db_path, min_size=1, max_size=3)

        try:
            # Single INSERT
            without_insert = benchmark_without_pool_insert(db_path, iterations)
            with_insert = benchmark_with_pool_insert(db_path, pool, iterations)
            results.append(BenchmarkResult(
                name="Single INSERT",
                iterations=iterations,
                without_pool_total_ms=without_insert,
                with_pool_total_ms=with_insert
            ))

            # Single SELECT
            without_select = benchmark_without_pool_select(db_path, iterations)
            with_select = benchmark_with_pool_select(db_path, pool, iterations)
            results.append(BenchmarkResult(
                name="Single SELECT",
                iterations=iterations,
                without_pool_total_ms=without_select,
                with_pool_total_ms=with_select
            ))

            # Batch INSERT (10 per batch)
            batch_iterations = iterations // 10  # Reduce for batch to keep time reasonable
            without_batch_insert = benchmark_without_pool_batch_insert(db_path, batch_iterations)
            with_batch_insert = benchmark_with_pool_batch_insert(db_path, pool, batch_iterations)
            results.append(BenchmarkResult(
                name="Batch INSERT (10/batch)",
                iterations=batch_iterations,
                without_pool_total_ms=without_batch_insert,
                with_pool_total_ms=with_batch_insert
            ))

            # Batch SELECT (10 per batch)
            without_batch_select = benchmark_without_pool_batch_select(db_path, batch_iterations)
            with_batch_select = benchmark_with_pool_batch_select(db_path, pool, batch_iterations)
            results.append(BenchmarkResult(
                name="Batch SELECT (10/batch)",
                iterations=batch_iterations,
                without_pool_total_ms=without_batch_select,
                with_pool_total_ms=with_batch_select
            ))

            # Mixed workload (5 INSERT + 5 SELECT)
            without_mixed = benchmark_without_pool_mixed(db_path, batch_iterations)
            with_mixed = benchmark_with_pool_mixed(db_path, pool, batch_iterations)
            results.append(BenchmarkResult(
                name="Mixed (5 INSERT + 5 SELECT)",
                iterations=batch_iterations,
                without_pool_total_ms=without_mixed,
                with_pool_total_ms=with_mixed
            ))

        finally:
            pool.close_all()

    return results


def main():
    """Run benchmark and print results."""
    print("=" * 50)
    print("SQLite Connection Pool Benchmark")
    print("=" * 50)
    print("\nRunning benchmarks... (this may take a moment)\n")

    results = run_benchmark(iterations=100)

    # Print individual results
    for result in results:
        print_result(result)

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    # The connection overhead benchmark is the key metric
    conn_overhead_result = results[0]  # First result is connection overhead only
    other_results = results[1:]  # Other results include I/O time

    print(f"\n*** KEY METRIC: Connection Overhead ***")
    print(f"  Without pool: {conn_overhead_result.without_pool_avg_ms:.3f}ms per connection")
    print(f"  With pool:    {conn_overhead_result.with_pool_avg_ms:.3f}ms per acquire/release")
    print(f"  Improvement:  {conn_overhead_result.improvement_percent:.1f}%")

    if conn_overhead_result.improvement_percent >= 50:
        print(f"\n[PASS] Connection pool meets 50%+ target for connection overhead!")
    else:
        print(f"\n[INFO] Connection overhead improvement: {conn_overhead_result.improvement_percent:.1f}%")

    # Note about I/O-bound operations
    print(f"\n*** Note on I/O-Bound Operations ***")
    print(f"  INSERT/commit operations are dominated by disk I/O (fsync).")
    print(f"  The pool's benefit is in avoiding connection setup cost, not I/O.")

    avg_improvement = sum(r.improvement_percent for r in results) / len(results)

    # Detailed table
    print("\n" + "-" * 70)
    print(f"{'Operation':<30} {'Without Pool':>12} {'With Pool':>12} {'Improvement':>12}")
    print("-" * 70)
    for r in results:
        print(f"{r.name:<30} {r.without_pool_avg_ms:>10.3f}ms {r.with_pool_avg_ms:>10.3f}ms {r.improvement_percent:>10.1f}%")
    print("-" * 70)
    print(f"{'Average':<30} {'':<12} {'':<12} {avg_improvement:>10.1f}%")

    return results


if __name__ == "__main__":
    main()
