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


# --- Postgres migration 007: legacy session bindings -------------------------
#
# Migration 007 (c9a988b) raised inside a DO guard whenever a legacy
# session_projects row matched zero or several scribe_projects rows. Numbered
# migrations run at scribe-server startup, so one stale binding killed every
# fresh server before MCP initialize. These tests run the real 007 file against
# a disposable database seeded with the legacy shapes seen live.

_M007_NAME = "sql:007_reliability_receipts.sql"
_M007_ROOT = "/fixture/repo"


def _replace_pg_db_name(dsn: str, db_name: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}", parts.query, parts.fragment))


@pytest.fixture
def m007_database():
    """A freshly created, dropped-after Postgres database. Never a shared DB."""
    import os
    import uuid

    asyncpg = pytest.importorskip("asyncpg")
    base_dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not base_dsn:
        pytest.skip("Set SCRIBE_TEST_POSTGRES_URL to run the Postgres migration 007 regression")
    admin_dsn = os.getenv(
        "SCRIBE_TEST_POSTGRES_ADMIN_URL", _replace_pg_db_name(base_dsn, "postgres")
    )
    db_name = f"scribe_m007_{uuid.uuid4().hex[:10]}"

    async def _admin(sql: str) -> None:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(sql)
        finally:
            await admin.close()

    try:
        run(_admin(f'CREATE DATABASE "{db_name}";'))
    except asyncpg.InsufficientPrivilegeError:
        pytest.skip("Migration 007 regression needs CREATEDB; it never runs against a shared DB")
    try:
        yield _replace_pg_db_name(base_dsn, db_name)
    finally:
        run(_admin(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE);'))


async def _bootstrap_pre_007(conn, tmp_path: Path) -> None:
    import shutil

    from scribe_mcp.storage.postgres import schema as schema_mod

    pre_dir = tmp_path / "pre_007_migrations"
    pre_dir.mkdir()
    for path in sorted(schema_mod.MIGRATIONS_PATH.iterdir()):
        if path.suffix == ".sql" and path.name < "007_":
            shutil.copy(path, pre_dir / path.name)
    await schema_mod.ensure_schema_on_connection(
        conn=conn, schema_name="scribe", migrations_path=pre_dir
    )


async def _seed_legacy_bindings(conn) -> None:
    await conn.executemany(
        """
        INSERT INTO scribe_projects (name, repo_root, project_key, progress_log_path)
        VALUES ($1, $2, $3, $4);
        """,
        [
            ("normal", _M007_ROOT, "key-normal", "/fixture/normal.md"),
            ("dup", _M007_ROOT, "key-dup-a", "/fixture/dup-a.md"),
            ("dup", _M007_ROOT, "key-dup-b", "/fixture/dup-b.md"),
        ],
    )
    await conn.executemany(
        "INSERT INTO scribe_sessions (session_id, repo_root) VALUES ($1, $2);",
        [(sid, _M007_ROOT) for sid in ("s-normal", "s-zero", "s-many", "s-unnamed", "s-new")],
    )
    await conn.executemany(
        "INSERT INTO session_projects (session_id, project_name) VALUES ($1, $2);",
        [
            ("s-normal", "normal"),
            ("s-zero", "ghost"),
            ("s-many", "dup"),
            ("s-unnamed", None),
        ],
    )


async def _bindings(conn) -> dict:
    rows = await conn.fetch(
        """
        SELECT session_id, project_name, project_key, binding_generation,
               binding_state, binding_state_reason
        FROM session_projects;
        """
    )
    return {row["session_id"]: dict(row) for row in rows}


@pytest.mark.postgres
@pytest.mark.regression
def test_migration_007_classifies_unresolved_legacy_bindings_instead_of_refusing_startup(
    m007_database, tmp_path
):
    import asyncpg

    from scribe_mcp.storage.postgres import schema as schema_mod

    async def body() -> None:
        conn = await asyncpg.connect(m007_database)
        try:
            await _bootstrap_pre_007(conn, tmp_path)
            await _seed_legacy_bindings(conn)

            # The startup path: pending numbered migrations, 007 included.
            await schema_mod.ensure_schema_on_connection(conn=conn, schema_name="scribe")
            assert await conn.fetchval(
                "SELECT 1 FROM scribe_migrations WHERE name = $1;", _M007_NAME
            )

            bindings = await _bindings(conn)
            assert set(bindings) == {"s-normal", "s-zero", "s-many", "s-unnamed"}
            assert bindings["s-normal"] == {
                "session_id": "s-normal",
                "project_name": "normal",
                "project_key": "key-normal",
                "binding_generation": 1,
                "binding_state": "resolved",
                "binding_state_reason": None,
            }
            # Unresolved bindings keep their legacy project_name and get no guessed key.
            for session_id, name, reason in (
                ("s-zero", "ghost", "project_identity_zero_matches"),
                ("s-many", "dup", "project_identity_ambiguous"),
                ("s-unnamed", None, "project_name_absent"),
            ):
                row = bindings[session_id]
                assert row["project_name"] == name
                assert row["project_key"] is None
                assert row["binding_state"] == "unresolved"
                assert row["binding_state_reason"] == reason
                assert row["binding_generation"] == 1

            # Unusable for writes: a forced promotion without a key is re-classified
            # unresolved, the table refuses a keyed row marked unresolved, and a
            # durable write keyed by the binding's project key cannot land.
            await conn.execute(
                "UPDATE session_projects SET binding_state = 'resolved', "
                "binding_state_reason = NULL WHERE session_id = 's-zero';"
            )
            forced = (await _bindings(conn))["s-zero"]
            assert forced["binding_state"] == "unresolved"
            assert forced["project_key"] is None
            await conn.execute(
                "ALTER TABLE session_projects DISABLE TRIGGER session_projects_classify_binding;"
            )
            try:
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(
                        "UPDATE session_projects SET project_key = 'key-dup-a' "
                        "WHERE session_id = 's-many';"
                    )
            finally:
                await conn.execute(
                    "ALTER TABLE session_projects ENABLE TRIGGER session_projects_classify_binding;"
                )
            with pytest.raises(asyncpg.NotNullViolationError):
                await conn.execute(
                    """
                    INSERT INTO background_receipts (
                        operation_id, canonical_project_key, lane, idempotency_key,
                        payload_digest, payload_bytes, durability_class, state
                    )
                    SELECT 'op-1', project_key, 'durable', 'idem-1',
                           repeat('0', 64), 0, 'durable', 'accepted'
                    FROM session_projects WHERE session_id = 's-many';
                    """
                )

            # Re-applying 007 (a crash between the SQL and its ledger row) is a no-op.
            migration_sql = (schema_mod.MIGRATIONS_PATH / "007_reliability_receipts.sql").read_text(
                encoding="utf-8"
            )
            await conn.execute(migration_sql)
            assert await _bindings(conn) == bindings
        finally:
            await conn.close()

    run(body())


@pytest.mark.postgres
@pytest.mark.regression
def test_migration_007_keeps_the_legacy_postgres_binding_writer_working(
    m007_database, tmp_path
):
    """The runtime writer still inserts project_name only; 007 must not reject it."""
    import asyncpg

    from scribe_mcp.storage.postgres import PostgresStorage

    async def body() -> None:
        conn = await asyncpg.connect(m007_database)
        try:
            await _bootstrap_pre_007(conn, tmp_path)
            await _seed_legacy_bindings(conn)
        finally:
            await conn.close()

        storage = PostgresStorage(m007_database, schema_name="scribe", pool_min_size=1, pool_max_size=2)
        await storage.setup()
        try:
            await storage.set_session_project("s-new", "normal")
            await storage.set_session_project("s-normal", "ghost")
            await storage.set_session_project("s-zero", "normal")
            assert await storage.get_session_project("s-normal") == "ghost"
        finally:
            await storage.close()

        conn = await asyncpg.connect(m007_database)
        try:
            await conn.execute("SET search_path TO scribe, public;")
            bindings = await _bindings(conn)
            # setup() canonicalizes project keys after migrations run.
            normal_key = await conn.fetchval(
                "SELECT project_key FROM scribe_projects WHERE name = 'normal';"
            )
        finally:
            await conn.close()

        assert normal_key
        assert bindings["s-new"]["binding_state"] == "resolved"
        assert bindings["s-new"]["project_key"] == normal_key
        assert bindings["s-new"]["binding_generation"] == 1
        # A rebind to a name with no project demotes the binding instead of keeping a stale key.
        assert bindings["s-normal"]["project_key"] is None
        assert bindings["s-normal"]["binding_state"] == "unresolved"
        assert bindings["s-normal"]["binding_state_reason"] == "project_identity_zero_matches"
        assert bindings["s-normal"]["binding_generation"] == 2
        # Rebinding an unresolved binding to a real project resolves it.
        assert bindings["s-zero"]["project_key"] == normal_key
        assert bindings["s-zero"]["binding_state"] == "resolved"
        assert bindings["s-zero"]["binding_generation"] == 2

    run(body())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
