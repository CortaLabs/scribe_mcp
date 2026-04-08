#!/usr/bin/env python3
"""
Backfill log_type column from meta JSON field for existing entries.

Run this script manually after adding the log_type column to scribe_entries.

Usage:
    python scripts/backfill_log_type.py
"""

import sqlite3
from pathlib import Path

from scribe_mcp.config.paths import default_db_path

# Default database path
DB_PATH = default_db_path()


def backfill_log_type(db_path: Path = DB_PATH) -> dict:
    """
    Backfill log_type from meta JSON field.

    Returns dict with stats about the migration.
    """
    if not db_path.exists():
        return {"error": f"Database not found: {db_path}"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Check current state
        cursor = conn.execute("SELECT COUNT(*) as total FROM scribe_entries")
        total = cursor.fetchone()["total"]

        cursor = conn.execute("""
            SELECT COUNT(*) as with_meta_log_type
            FROM scribe_entries
            WHERE json_extract(meta, '$.log_type') IS NOT NULL
        """)
        with_meta = cursor.fetchone()["with_meta_log_type"]

        cursor = conn.execute("""
            SELECT COUNT(*) as needs_update
            FROM scribe_entries
            WHERE json_extract(meta, '$.log_type') IS NOT NULL
              AND (log_type IS NULL OR log_type = 'progress')
              AND json_extract(meta, '$.log_type') != 'progress'
        """)
        needs_update = cursor.fetchone()["needs_update"]

        print(f"Total entries: {total}")
        print(f"Entries with meta.log_type: {with_meta}")
        print(f"Entries needing update: {needs_update}")

        if needs_update == 0:
            print("Nothing to update!")
            return {
                "total": total,
                "with_meta_log_type": with_meta,
                "updated": 0
            }

        # Perform the update
        cursor = conn.execute("""
            UPDATE scribe_entries
            SET log_type = json_extract(meta, '$.log_type')
            WHERE json_extract(meta, '$.log_type') IS NOT NULL
              AND (log_type IS NULL OR log_type = 'progress')
              AND json_extract(meta, '$.log_type') != 'progress'
        """)
        updated = cursor.rowcount
        conn.commit()

        print(f"Updated {updated} entries!")

        # Show breakdown by log_type
        cursor = conn.execute("""
            SELECT log_type, COUNT(*) as count
            FROM scribe_entries
            GROUP BY log_type
            ORDER BY count DESC
        """)
        print("\nLog type breakdown:")
        for row in cursor.fetchall():
            print(f"  {row['log_type']}: {row['count']}")

        return {
            "total": total,
            "with_meta_log_type": with_meta,
            "updated": updated
        }

    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    # Allow custom db path as argument
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        db_path = DB_PATH

    print(f"Backfilling log_type from meta in: {db_path}")
    print("-" * 50)

    result = backfill_log_type(db_path)

    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)

    print("-" * 50)
    print("Done!")
