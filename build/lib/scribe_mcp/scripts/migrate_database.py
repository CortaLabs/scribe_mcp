#!/usr/bin/env python3
"""
Database migration script for Scribe MCP enhancement.

This script migrates the database from the old schema to the enhanced schema
that supports global logging, document tracking, and project status management.

Usage:
    python scripts/migrate_database.py [--dry-run] [--backup]
"""

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from scribe_mcp.config.paths import default_db_path, user_data_dir

# Database paths
NEW_DB_PATH = default_db_path()
BACKUP_DIR = user_data_dir() / "backups"


def create_backup(db_path: Path) -> Path:
    """Create a backup of the database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"scribe_backup_{timestamp}.db"

    if db_path.exists():
        shutil.copy2(db_path, backup_path)
        print(f"✅ Created backup: {backup_path}")
    else:
        print(f"⚠️  Database file not found: {db_path}")

    return backup_path


def check_migration_needed(conn: sqlite3.Connection) -> bool:
    """Check if migration is needed by checking for new columns."""
    cursor = conn.cursor()

    # Check if scribe_projects table has new columns
    cursor.execute("PRAGMA table_info(scribe_projects)")
    columns = {row[1] for row in cursor.fetchall()}

    needed_columns = {"status", "phase", "confidence", "completed_at", "last_activity"}
    has_new_columns = needed_columns.issubset(columns)

    # Check if new tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}

    needed_tables = {"documents", "document_relationships", "global_log_entries"}
    has_new_tables = needed_tables.issubset(existing_tables)

    return not (has_new_columns and has_new_tables)


def migrate_database_schema(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    """Apply database schema migrations."""
    cursor = conn.cursor()

    migrations = [
        # Add new columns to scribe_projects table
        """
        ALTER TABLE scribe_projects ADD COLUMN status TEXT DEFAULT 'planning'
        """,
        """
        ALTER TABLE scribe_projects ADD COLUMN phase TEXT DEFAULT 'setup'
        """,
        """
        ALTER TABLE scribe_projects ADD COLUMN confidence REAL DEFAULT 0.0
        """,
        """
        ALTER TABLE scribe_projects ADD COLUMN completed_at TIMESTAMP
        """,
        """
        ALTER TABLE scribe_projects ADD COLUMN last_activity TIMESTAMP
        """,

        # Create documents table
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            doc_type TEXT NOT NULL,
            name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            size_bytes INTEGER,
            checksum TEXT,
            metadata JSON
        )
        """,

        # Create document relationships table
        """
        CREATE TABLE IF NOT EXISTS document_relationships (
            id TEXT PRIMARY KEY,
            source_doc_id TEXT NOT NULL,
            target_doc_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Create global log entries table
        """
        CREATE TABLE IF NOT EXISTS global_log_entries (
            id TEXT PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            entry_type TEXT NOT NULL,
            agent TEXT,
            message TEXT NOT NULL,
            metadata JSON,
            project_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Create indexes for performance
        """
        CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_document_relationships_source ON document_relationships(source_doc_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_document_relationships_target ON document_relationships(target_doc_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_global_log_timestamp ON global_log_entries(timestamp)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_global_log_entry_type ON global_log_entries(entry_type)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_global_log_project_id ON global_log_entries(project_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_scribe_projects_status ON scribe_projects(status)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_scribe_projects_phase ON scribe_projects(phase)
        """,
    ]

    print("🔄 Applying database migrations...")

    for i, migration in enumerate(migrations, 1):
        if dry_run:
            print(f"   {i:2d}. DRY RUN: {migration.strip()[:80]}...")
        else:
            try:
                cursor.execute(migration)
                print(f"   {i:2d}. ✅ Applied: {migration.strip()[:80]}...")
            except sqlite3.Error as e:
                if "duplicate column name" in str(e).lower():
                    print(f"   {i:2d}. ⚠️  Skipped (column exists): {migration.strip()[:80]}...")
                else:
                    print(f"   {i:2d}. ❌ Error: {migration.strip()[:80]}... - {e}")
                    raise


def update_existing_projects(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    """Update existing projects with default values."""
    cursor = conn.cursor()

    # Get existing projects
    cursor.execute("SELECT id, name, created_at FROM scribe_projects")
    projects = cursor.fetchall()

    print(f"🔄 Updating {len(projects)} existing projects...")

    for project_id, name, created_at in projects:
        if dry_run:
            print(f"   - DRY RUN: Update project '{name}' with status='planning', phase='setup'")
        else:
            cursor.execute("""
                UPDATE scribe_projects
                SET status = 'planning',
                    phase = 'setup',
                    confidence = 0.0,
                    last_activity = ?
                WHERE id = ?
            """, (created_at or datetime.now().isoformat(), project_id))
            print(f"   ✅ Updated project: {name}")


def verify_migration(conn: sqlite3.Connection) -> bool:
    """Verify that the migration was successful."""
    cursor = conn.cursor()

    print("🔍 Verifying migration...")

    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    required_tables = {"scribe_projects", "documents", "document_relationships", "global_log_entries"}
    missing_tables = required_tables - tables

    if missing_tables:
        print(f"❌ Missing tables: {missing_tables}")
        return False

    # Check scribe_projects table columns
    cursor.execute("PRAGMA table_info(scribe_projects)")
    columns = {row[1] for row in cursor.fetchall()}

    required_columns = {"id", "name", "status", "phase", "confidence", "completed_at", "last_activity"}
    missing_columns = required_columns - columns

    if missing_columns:
        print(f"❌ Missing columns in scribe_projects table: {missing_columns}")
        return False

    # Check indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cursor.fetchall()}

    required_indexes = {
        "idx_documents_project_id", "idx_documents_doc_type",
        "idx_document_relationships_source", "idx_document_relationships_target",
        "idx_global_log_timestamp", "idx_global_log_entry_type", "idx_global_log_project_id",
        "idx_scribe_projects_status", "idx_scribe_projects_phase"
    }
    missing_indexes = required_indexes - indexes

    if missing_indexes:
        print(f"⚠️  Missing indexes: {missing_indexes}")

    print("✅ Migration verification passed!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate Scribe MCP database to enhanced schema")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--backup", action="store_true", default=True, help="Create backup before migration")
    parser.add_argument("--no-backup", dest="backup", action="store_false", help="Skip backup creation")

    args = parser.parse_args()

    print("🚀 Scribe MCP Database Migration")
    print("=" * 40)

    # Ensure backup directory exists
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Check if new database exists
    if not NEW_DB_PATH.exists():
        print(f"❌ New database not found at: {NEW_DB_PATH}")
        print("Please run the database copy step first.")
        return 1

    # Create backup if requested
    if args.backup and not args.dry_run:
        create_backup(NEW_DB_PATH)

    # Connect to database
    try:
        conn = sqlite3.connect(str(NEW_DB_PATH))
        conn.execute("PRAGMA foreign_keys = ON")

        # Check if migration is needed
        if not check_migration_needed(conn):
            print("✅ Database is already up to date!")
            return 0

        print("📋 Migration needed:")

        # Apply migrations
        migrate_database_schema(conn, args.dry_run)

        # Update existing projects
        update_existing_projects(conn, args.dry_run)

        # Commit changes
        if not args.dry_run:
            conn.commit()
            print("💾 Changes committed to database")

            # Verify migration
            if verify_migration(conn):
                print("🎉 Migration completed successfully!")
                return 0
            else:
                print("❌ Migration verification failed!")
                return 1
        else:
            print("🔍 DRY RUN completed - no changes made")
            return 0

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    exit(main())