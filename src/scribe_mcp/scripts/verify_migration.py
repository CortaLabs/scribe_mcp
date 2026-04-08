#!/usr/bin/env python3
"""
Verification script for docs_json migration (BUG-MANAGE-DOCS-001).

This script checks the migration status and provides diagnostic information
about the docs_json column in the scribe_projects table.

Usage:
    python scripts/verify_migration.py
"""

from pathlib import Path

import asyncio
import json
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.config.settings import settings
from scribe_mcp.config.paths import repo_root

REPO_ROOT = repo_root()


async def verify_migration():
    """Verify docs_json migration status."""
    print("=" * 70)
    print("DOCS_JSON MIGRATION VERIFICATION")
    print("=" * 70)
    print()

    # Initialize storage
    db_path = settings.project_root / "data" / "scribe_projects.db"
    print(f"Database: {db_path}")
    print()

    storage = SQLiteStorage(db_path)
    await storage._initialise()

    # Check if column exists
    conn = storage._connect()
    try:
        cursor = conn.execute("PRAGMA table_info(scribe_projects);")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        print(f"scribe_projects table has {len(column_names)} columns:")
        for i, col in enumerate(columns, 1):
            col_name = col[1]
            col_type = col[2]
            is_docs = " <- DOCS_JSON COLUMN" if col_name == "docs_json" else ""
            print(f"  {i}. {col_name} ({col_type}){is_docs}")
        print()

        if 'docs_json' in column_names:
            print("✅ MIGRATION STATUS: docs_json column EXISTS")
            print()

            # Count projects with docs_json
            cursor = conn.execute(
                "SELECT COUNT(*) FROM scribe_projects WHERE docs_json IS NOT NULL"
            )
            with_docs = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM scribe_projects")
            total = cursor.fetchone()[0]

            without_docs = total - with_docs

            print(f"Projects with docs_json populated: {with_docs}/{total}")
            print(f"Projects without docs_json: {without_docs}/{total}")
            print()

            if with_docs > 0:
                # Show sample project
                cursor = conn.execute(
                    "SELECT name, docs_json FROM scribe_projects WHERE docs_json IS NOT NULL LIMIT 1"
                )
                row = cursor.fetchone()
                if row:
                    name, docs_json = row
                    print(f"Sample project: {name}")
                    print(f"docs_json content:")
                    try:
                        docs = json.loads(docs_json)
                        print(json.dumps(docs, indent=2))
                    except json.JSONDecodeError:
                        print(f"  (Invalid JSON: {docs_json[:100]}...)")
                    print()

            print("✅ Migration successful!")
            return True
        else:
            print("❌ MIGRATION STATUS: docs_json column MISSING")
            print()
            print("The migration has NOT been applied yet.")
            print("The docs_json column is required for manage_docs to function.")
            print()
            print("Migration should run automatically on next storage initialization.")
            return False

    finally:
        conn.close()


def main():
    """Run verification."""
    try:
        result = asyncio.run(verify_migration())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
