from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import asyncpg
import pytest

from scribe_mcp.storage.postgres import schema as postgres_schema
from scribe_mcp.storage.pool import SQLiteConnectionPool
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.storage.sqlite import schema as sqlite_schema
from scribe_mcp.storage.models import compute_project_key, compute_repo_id


_BOUNDARY = "-- scribe:statement-boundary"


class _SchemaRecorder:
    def __init__(self, *, fail_on: str | None = None, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.fail_on = fail_on
        self.error = error

    async def execute(self, query: str, *args: object) -> None:
        self.calls.append((query, args))
        if self.fail_on is not None and self.fail_on in query:
            assert self.error is not None
            raise self.error
        if "CREATE OR REPLACE FUNCTION session_projects_classify_binding()" in query:
            assert "RETURN NEW;" in query
            assert query.rstrip().endswith("$$;"), "the classifier must be sent as a whole unit"

    async def fetchval(self, query: str, *args: object) -> object:
        self.calls.append((query, args))
        return None


def _write_migrations(tmp_path: Path) -> Path:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_after_init.sql").write_text("SELECT 'migration';", encoding="utf-8")
    return migrations


def _write_init(tmp_path: Path, *statements: str) -> Path:
    schema_path = tmp_path / "init.sql"
    schema_path.write_text(f"\n{_BOUNDARY}\n".join(statements), encoding="utf-8")
    return schema_path


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_fresh_init_uses_migration_007_binding_classifier(test_agent: str) -> None:
    init_sql = postgres_schema.SCHEMA_PATH.read_text(encoding="utf-8")
    migration_sql = (
        postgres_schema.MIGRATIONS_PATH / "007_reliability_receipts.sql"
    ).read_text(encoding="utf-8")
    classifier = "CREATE OR REPLACE FUNCTION session_projects_classify_binding()"
    init_start = init_sql.index(classifier)
    init_end = init_sql.index("$$;", init_start) + len("$$;")
    migration_start = migration_sql.index(classifier)
    migration_end = migration_sql.index("$$;", migration_start) + len("$$;")

    assert init_sql[init_start:init_end] == migration_sql[migration_start:migration_end]


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_postgres_bootstrap_preserves_complete_function_units(tmp_path: Path, test_agent: str) -> None:
    """The real packaged init passes complete function and trigger units to asyncpg."""
    conn = _SchemaRecorder()
    migrations = _write_migrations(tmp_path)

    asyncio.run(
        postgres_schema.ensure_schema_on_connection(
            conn=conn,
            schema_name="scribe",
            schema_path=postgres_schema.SCHEMA_PATH,
            migrations_path=migrations,
        )
    )

    classifier_calls = [
        query
        for query, _ in conn.calls
        if "CREATE OR REPLACE FUNCTION session_projects_classify_binding()" in query
    ]
    assert len(classifier_calls) == 1
    classifier = classifier_calls[0]
    packaged_sql = postgres_schema.SCHEMA_PATH.read_text(encoding="utf-8")
    function_start = packaged_sql.index("CREATE OR REPLACE FUNCTION session_projects_classify_binding()")
    function_end = packaged_sql.index("$$;", function_start) + len("$$;")
    assert classifier == packaged_sql[function_start:function_end]

    init_queries = [query for query, _ in conn.calls if _BOUNDARY not in query]
    drop_index = next(
        i for i, query in enumerate(init_queries)
        if "DROP TRIGGER IF EXISTS session_projects_classify_binding" in query
    )
    create_index = next(
        i for i, query in enumerate(init_queries)
        if "CREATE TRIGGER session_projects_classify_binding" in query
    )
    assert create_index == drop_index
    trigger_batch = init_queries[drop_index]
    assert trigger_batch.index("DROP TRIGGER") < trigger_batch.index("CREATE TRIGGER")
    assert init_queries.index(classifier) < drop_index

    migration_index = next(i for i, (query, _) in enumerate(conn.calls) if "SELECT 'migration';" in query)
    assert migration_index > max(i for i, (query, _) in enumerate(conn.calls) if "CREATE INDEX" in query)
    assert conn.calls[-1][0] == "SELECT pg_advisory_unlock(hashtext($1));"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_postgres_bootstrap_keeps_an_unmarked_script_as_one_unit(tmp_path: Path) -> None:
    schema_path = tmp_path / "init.sql"
    schema_path.write_text("SELECT 1;\nSELECT 2;", encoding="utf-8")
    conn = _SchemaRecorder()

    asyncio.run(
        postgres_schema.ensure_schema_on_connection(
            conn=conn,
            schema_name="scribe",
            schema_path=schema_path,
            migrations_path=tmp_path / "no_migrations",
        )
    )

    assert sum(query == "SELECT 1;\nSELECT 2;" for query, _ in conn.calls) == 1
    assert conn.calls[-1][0] == "SELECT pg_advisory_unlock(hashtext($1));"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize(
    "index_sql",
    [
        "CREATE INDEX idx_duplicate ON sample (value);",
        "CREATE UNIQUE INDEX idx_duplicate ON sample (value);",
    ],
)
def test_postgres_bootstrap_tolerates_duplicate_index_races_only_on_index_units(
    tmp_path: Path, index_sql: str
) -> None:
    migrations = _write_migrations(tmp_path)
    schema_path = _write_init(
        tmp_path,
        "CREATE TABLE sample (value TEXT);",
        "-- This leading comment mentions CREATE INDEX, but is not the command.\n"
        + index_sql,
        "CREATE TABLE after_index (value TEXT);",
    )
    conn = _SchemaRecorder(
        fail_on="idx_duplicate",
        error=asyncpg.UniqueViolationError("pg_class_relname_nsp_index duplicate race"),
    )

    asyncio.run(
        postgres_schema.ensure_schema_on_connection(
            conn=conn,
            schema_name="scribe",
            schema_path=schema_path,
            migrations_path=migrations,
        )
    )

    assert any("CREATE TABLE after_index" in query for query, _ in conn.calls)
    assert any("SELECT 'migration';" in query for query, _ in conn.calls)
    assert conn.calls[-1][0] == "SELECT pg_advisory_unlock(hashtext($1));"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_postgres_bootstrap_defers_only_the_exact_additive_correlation_index(tmp_path: Path) -> None:
    migrations = _write_migrations(tmp_path)
    schema_path = _write_init(
        tmp_path,
        "-- additive index is supplied by the numbered migration\n"
        "CREATE INDEX idx_tool_calls_correlation ON tool_calls (correlation_id);",
        "CREATE TABLE after_index (value TEXT);",
    )
    conn = _SchemaRecorder(
        fail_on="idx_tool_calls_correlation",
        error=asyncpg.UndefinedColumnError("column correlation_id does not exist"),
    )

    asyncio.run(
        postgres_schema.ensure_schema_on_connection(
            conn=conn,
            schema_name="scribe",
            schema_path=schema_path,
            migrations_path=migrations,
        )
    )

    assert any("CREATE TABLE after_index" in query for query, _ in conn.calls)
    assert any("SELECT 'migration';" in query for query, _ in conn.calls)
    assert conn.calls[-1][0] == "SELECT pg_advisory_unlock(hashtext($1));"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize(
    ("statement", "error"),
    [
        (
            "-- CREATE INDEX idx_decoy ON sample (value);\nINSERT INTO sample VALUES ('x');",
            asyncpg.UniqueViolationError("pg_class_relname_nsp_index duplicate race"),
        ),
        (
            "CREATE INDEX idx_other ON sample (value);",
            asyncpg.UndefinedColumnError("column correlation_id does not exist"),
        ),
    ],
)
def test_postgres_bootstrap_propagates_unrelated_index_errors_and_unlocks(
    tmp_path: Path, statement: str, error: Exception
) -> None:
    migrations = _write_migrations(tmp_path)
    schema_path = _write_init(tmp_path, statement)
    failure_token = "INSERT INTO sample" if "INSERT INTO sample" in statement else "idx_other"
    conn = _SchemaRecorder(fail_on=failure_token, error=error)

    with pytest.raises(type(error)):
        asyncio.run(
            postgres_schema.ensure_schema_on_connection(
                conn=conn,
                schema_name="scribe",
                schema_path=schema_path,
                migrations_path=migrations,
            )
        )

    assert not any("SELECT 'migration';" in query for query, _ in conn.calls)
    assert conn.calls[-1][0] == "SELECT pg_advisory_unlock(hashtext($1));"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_reopen_reclassifies_semantically_forged_binding(tmp_path: Path) -> None:
    """Reopen repairs forged authority while preserving valid generations and timestamps."""
    storage = SQLiteStorage(tmp_path / "test.db")
    asyncio.run(storage._initialise())
    conn = storage._connect()
    try:
        conn.execute(
            "INSERT INTO scribe_projects (name, repo_root, project_key, progress_log_path) "
            "VALUES (?, ?, ?, ?);",
            ("alpha", "/fixture/repo", "pk-alpha", "/fixture/alpha.md"),
        )
        conn.executemany(
            "INSERT INTO scribe_sessions (session_id, repo_root) VALUES (?, ?);",
            [("s-forged", "/fixture/repo"), ("s-valid", "/fixture/repo")],
        )
        conn.executemany(
            "INSERT INTO session_projects (session_id, project_name, project_key, "
            "binding_generation, binding_state, binding_state_reason) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            [
                ("s-forged", "alpha", "pk-alpha", 1, "resolved", None),
                ("s-valid", "alpha", "pk-alpha", 1, "resolved", None),
            ],
        )
        conn.execute("DROP TRIGGER trg_session_projects_classify_insert;")
        conn.execute("DROP TRIGGER trg_session_projects_classify_update;")
        conn.execute(
            "UPDATE session_projects SET project_key = ?, binding_generation = ? "
            "WHERE session_id = ?;",
            ("pk-forged", 99, "s-forged"),
        )
        conn.execute(
            "UPDATE session_projects SET binding_generation = ? WHERE session_id = ?;",
            (7, "s-valid"),
        )
        conn.commit()
    finally:
        conn.close()

    asyncio.run(SQLiteStorage(storage._path)._initialise())
    conn = storage._connect()
    try:
        rows = {
            row[0]: tuple(row[1:])
            for row in conn.execute(
                "SELECT session_id, project_name, project_key, binding_generation, "
                "binding_state, binding_state_reason, updated_at FROM session_projects;"
            ).fetchall()
        }
        assert rows["s-forged"][:5] == ("alpha", "pk-alpha", 100, "resolved", None)
        assert rows["s-valid"][:5] == ("alpha", "pk-alpha", 7, "resolved", None)
    finally:
        conn.close()

    asyncio.run(SQLiteStorage(storage._path)._initialise())
    conn = storage._connect()
    try:
        reopened_rows = {
            row[0]: tuple(row[1:])
            for row in conn.execute(
                "SELECT session_id, project_name, project_key, binding_generation, "
                "binding_state, binding_state_reason, updated_at FROM session_projects;"
            ).fetchall()
        }
        assert reopened_rows == rows
    finally:
        conn.close()


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_reliability_rebuild_rolls_back_before_pooled_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed rebuild rolls back on its owner despite a second idle pool connection."""
    storage = SQLiteStorage(tmp_path / "rollback.db")
    conn = storage._connect()
    try:
        conn.execute(sqlite_schema.BACKGROUND_RECEIPT_TABLE_STATEMENTS[0])
        for statement in sqlite_schema.BACKGROUND_RECEIPT_INDEX_STATEMENTS:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO background_receipts (operation_id, canonical_project_key, lane, "
            "idempotency_key, payload_digest, payload_bytes, durability_class, state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            ("op-1", "project-1", "durable", "idem-1", "a" * 64, 12, "durable", "accepted"),
        )
        conn.execute(
            "CREATE TABLE rollback_sequence_probe (id INTEGER PRIMARY KEY AUTOINCREMENT);"
        )
        conn.execute("INSERT INTO rollback_sequence_probe DEFAULT VALUES;")
        conn.commit()
    finally:
        conn.close()
    pool = SQLiteConnectionPool(storage._path, min_size=1, max_size=3)
    storage._internals.pool = pool
    internals = storage._internals

    try:
        conn_a = pool.acquire()
        conn_b = pool.acquire()
        try:
            assert conn_a is not conn_b
            before = _sqlite_rebuild_state(conn_a)
            conn_a_id, conn_b_id = id(conn_a), id(conn_b)
        finally:
            pool.release(conn_a)
            pool.release(conn_b)

        assert pool.size == 2
        assert pool.active == 0
        fifo = [pool.acquire(), pool.acquire()]
        try:
            assert [id(conn) for conn in fifo] == [conn_a_id, conn_b_id]
        finally:
            pool.release(fifo[0])
            pool.release(fifo[1])

        rebuild_statements = sqlite_schema.BACKGROUND_RECEIPT_REBUILD_STATEMENTS
        rename_index = rebuild_statements.index(
            "ALTER TABLE background_receipts_reliability_new RENAME TO background_receipts;"
        )
        failing_statements = [
            *rebuild_statements[:rename_index],
            "UPDATE sqlite_sequence SET seq = seq + 1 WHERE name = 'rollback_sequence_probe';",
            "SELECT * FROM scribe_forced_rebuild_failure;",
        ]

        # RED control: the legacy split callbacks release A before rollback, so FIFO gives B the rollback.
        def legacy_two_callback_attempt() -> None:
            try:
                def rebuild_on_connection(conn: sqlite3.Connection) -> None:
                    conn.execute("BEGIN IMMEDIATE;")
                    for statement in failing_statements:
                        conn.execute(statement)

                internals._run_with_connection(rebuild_on_connection)
            except sqlite3.OperationalError:
                internals._run_with_connection(lambda conn: conn.rollback())
                raise

        with pytest.raises(sqlite3.OperationalError, match="scribe_forced_rebuild_failure"):
            legacy_two_callback_attempt()

        legacy_a, legacy_b = pool.acquire(), pool.acquire()
        try:
            assert [id(legacy_a), id(legacy_b)] == [conn_a_id, conn_b_id]
            assert legacy_a.in_transaction
            assert not legacy_b.in_transaction
            assert _sqlite_replacement_artifacts(legacy_a)
            assert not _sqlite_replacement_artifacts(legacy_b)
            assert legacy_a.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'background_receipts';"
            ).fetchone() is None
            assert legacy_b.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'background_receipts';"
            ).fetchone() is not None

            # Clean the deliberately reproduced legacy leak before exercising production code.
            legacy_a.rollback()
            assert _sqlite_rebuild_state(legacy_a) == before
            assert not _sqlite_replacement_artifacts(legacy_a)
        finally:
            pool.release(legacy_a)
            pool.release(legacy_b)

        callback_state_before_release: list[tuple[int, bool]] = []
        pool_release = pool.release

        def observe_release(conn: sqlite3.Connection) -> None:
            callback_state_before_release.append((id(conn), conn.in_transaction))
            pool_release(conn)

        monkeypatch.setattr(pool, "release", observe_release)
        with pytest.raises(sqlite3.OperationalError, match="scribe_forced_rebuild_failure"):
            asyncio.run(sqlite_schema._execute_rebuild(storage._execute_many, failing_statements))

        assert callback_state_before_release == [(conn_a_id, False)]
        assert pool.size == 2
        assert pool.active == 0

        after_a, after_b = pool.acquire(), pool.acquire()
        try:
            assert [id(after_a), id(after_b)] == [conn_b_id, conn_a_id]
            for conn in (after_a, after_b):
                assert not conn.in_transaction
                assert not _sqlite_replacement_artifacts(conn)
                assert _sqlite_rebuild_state(conn)[1:] == before[1:]
        finally:
            pool.release(after_a)
            pool.release(after_b)

        monkeypatch.setattr(pool, "release", pool_release)
        asyncio.run(
            storage._execute(
                "INSERT INTO background_receipts (operation_id, canonical_project_key, lane, "
                "idempotency_key, payload_digest, payload_bytes, durability_class, state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
                ("op-2", "project-1", "durable", "idem-2", "b" * 64, 14, "durable", "accepted"),
            )
        )
        conn = storage._connect()
        try:
            rows = conn.execute(
                "SELECT operation_id FROM background_receipts ORDER BY operation_id;"
            ).fetchall()
            assert [tuple(row) for row in rows] == [("op-1",), ("op-2",)]
        finally:
            conn.close()

        assert pool.active == 0
        final_a, final_b = pool.acquire(), pool.acquire()
        try:
            assert {id(final_a), id(final_b)} == {conn_a_id, conn_b_id}
            assert all(not conn.in_transaction for conn in (final_a, final_b))
            assert all(not _sqlite_replacement_artifacts(conn) for conn in (final_a, final_b))
        finally:
            pool.release(final_a)
            pool.release(final_b)
    finally:
        asyncio.run(storage.close())


def _sqlite_replacement_artifacts(conn: sqlite3.Connection) -> tuple[sqlite3.Row, ...]:
    return tuple(
        conn.execute(
            "SELECT type, name, tbl_name FROM sqlite_master "
            "WHERE name LIKE '%_reliability_new' OR tbl_name LIKE '%_reliability_new' "
            "ORDER BY type, name;"
        ).fetchall()
    )


def _sqlite_rebuild_state(conn: sqlite3.Connection) -> tuple[object, ...]:
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'background_receipts';"
    ).fetchone()[0]
    indexes = tuple(
        conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = 'background_receipts' ORDER BY name;"
        ).fetchall()
    )
    rows = tuple(
        conn.execute("SELECT * FROM background_receipts ORDER BY operation_id;").fetchall()
    )
    sequences = tuple(
        conn.execute("SELECT name, seq FROM sqlite_sequence ORDER BY name;").fetchall()
    )
    in_transaction = conn.in_transaction
    return id(conn), schema, indexes, rows, sequences, in_transaction


# Frozen legacy identity DDL: these three name references must exist BEFORE
# setup. Do not derive them from the schema being tested or seed via setup().
_SQLITE_IDENTITY_LEGACY_DDL = """
CREATE TABLE scribe_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    repo_root TEXT NOT NULL, repo_id TEXT, project_key TEXT,
    progress_log_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    docs_json TEXT, status TEXT, phase TEXT, confidence REAL DEFAULT 0.0,
    completed_at TIMESTAMP, last_activity TIMESTAMP, description TEXT,
    last_entry_at TEXT, last_access_at TEXT, last_status_change TEXT,
    tags TEXT, meta TEXT, bridge_id TEXT, bridge_managed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE scribe_sessions (
    session_id TEXT PRIMARY KEY, transport_session_id TEXT, agent_id TEXT,
    repo_root TEXT, mode TEXT NOT NULL DEFAULT 'sentinel'
        CHECK(mode IN ('sentinel','project')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE session_projects (
    session_id TEXT PRIMARY KEY REFERENCES scribe_sessions(session_id) ON DELETE CASCADE,
    project_name TEXT REFERENCES scribe_projects(name) ON DELETE SET NULL,
    project_key TEXT CHECK(project_key IS NULL OR trim(project_key) <> ''),
    binding_generation INTEGER NOT NULL DEFAULT 1 CHECK(binding_generation >= 1),
    binding_state TEXT NOT NULL DEFAULT 'unresolved'
        CHECK(binding_state IN ('resolved','unresolved')),
    binding_state_reason TEXT DEFAULT 'project_name_absent',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK((binding_state='resolved' AND project_key IS NOT NULL AND binding_state_reason IS NULL)
       OR (binding_state='unresolved' AND project_key IS NULL
           AND trim(COALESCE(binding_state_reason,'')) <> ''))
);
CREATE TABLE agent_projects (
    agent_id TEXT PRIMARY KEY,
    project_name TEXT REFERENCES scribe_projects(name) ON DELETE SET NULL,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT, session_id TEXT
);
CREATE TABLE agent_recent_projects (
    agent_id TEXT NOT NULL,
    project_name TEXT NOT NULL REFERENCES scribe_projects(name) ON DELETE CASCADE,
    last_access_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(agent_id,project_name)
);
"""


def _sqlite_identity_insert(conn: sqlite3.Connection, table: str, values: dict) -> None:
    columns = ', '.join('"' + column + '"' for column in values)
    placeholders = ', '.join('?' for _ in values)
    conn.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', tuple(values.values()))


def _sqlite_identity_legacy(path: Path, test_agent: str, *, extensions: bool = False) -> dict:
    """A valid, populated pre-upgrade file; setup has never seen this file."""
    roots = {name: str(path.parent / name) for name in ('repo-a', 'repo-c', 'repo-b')}
    with sqlite3.connect(path) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript(_SQLITE_IDENTITY_LEGACY_DDL)
        # Reuse only unrelated data-table definitions, never identity DDL or
        # classifier triggers. Every project-id child table gets real payload.
        for statement in [*sqlite_schema.CORE_TABLE_STATEMENTS[1:],
                          *sqlite_schema.DOCUMENT_TABLE_STATEMENTS,
                          *sqlite_schema.PLANNING_TABLE_STATEMENTS,
                          *sqlite_schema.ARCHIVE_TABLE_STATEMENTS,
                          *sqlite_schema.TELEMETRY_TABLE_STATEMENTS,
                          sqlite_schema.SESSION_TABLE_STATEMENTS[0]]:
            conn.execute(statement)
        # This legacy file already completed the unrelated additive column
        # migrations. Concurrent identity upgrades must not race on those.
        for table, declarations in {
            'scribe_entries': ('priority TEXT', 'category TEXT', 'tags TEXT', 'confidence REAL DEFAULT 1.0'),
            'agent_sessions': ('recent_tools TEXT', 'session_started_at TEXT', 'last_activity_at TEXT'),
            'tool_calls': ('repo_root TEXT', 'duration_ms REAL', "status TEXT NOT NULL DEFAULT 'success'",
                           'format_requested TEXT', 'project_name TEXT', 'agent_id TEXT', 'error_message TEXT',
                           'response_size_bytes INTEGER', 'correlation_id TEXT', 'measurement_scope TEXT'),
        }.items():
            existing = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            for declaration in declarations:
                if declaration.split()[0] not in existing:
                    conn.execute(f'ALTER TABLE {table} ADD COLUMN {declaration}')
        # A real legacy database has its FTS index maintained alongside old
        # entries; creating an empty index only at setup would make a later
        # cascade delete issue FTS "delete" commands for unindexed rows.
        for statement in sqlite_schema.FTS_TABLE_STATEMENTS:
            conn.execute(statement)
        if extensions:
            conn.executescript("""
                ALTER TABLE scribe_projects ADD COLUMN extension_blob BLOB;
                ALTER TABLE scribe_projects ADD COLUMN extension_code TEXT COLLATE NOCASE
                    NOT NULL DEFAULT 'kept' CHECK(length(extension_code) > 0);
                ALTER TABLE scribe_projects ADD COLUMN extension_generated TEXT
                    GENERATED ALWAYS AS (extension_code || ':' || name) VIRTUAL;
                CREATE UNIQUE INDEX extension_project_code ON scribe_projects(extension_code);
                CREATE INDEX extension_project_phase ON scribe_projects(phase COLLATE NOCASE);
                CREATE TABLE extension_audit (project_id INTEGER, old_value TEXT, new_value TEXT);
                CREATE TRIGGER extension_project_audit AFTER UPDATE OF description ON scribe_projects
                BEGIN INSERT INTO extension_audit VALUES(OLD.id, OLD.description, NEW.description); END;
                CREATE VIEW extension_project_view AS SELECT id, extension_code FROM scribe_projects;
                CREATE TABLE extension_children (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
                    nil_value, integer_value INTEGER, real_value REAL, text_value TEXT, blob_value BLOB
                );
            """)
        for index, (name, root) in enumerate((('shared', roots['repo-a']), ('other', roots['repo-c'])), 1):
            payload = dict(id=index, name=name, repo_root=root, repo_id=compute_repo_id(root),
                           project_key=compute_project_key(repo_root=root, project_name=name),
                           progress_log_path=str(Path(root) / 'PROGRESS_LOG.md'),
                           created_at=f'2020-01-0{index} 01:02:03', updated_at=f'2020-02-0{index} 04:05:06',
                           docs_json=json.dumps({'owner': name, 'value': index}), status='in_progress',
                           phase=f'phase-{index}', confidence=0.25 * index,
                           completed_at=None if index == 1 else '2021-01-01 00:00:00',
                           last_activity='2022-01-01 00:00:00', description=f'preserve-{name}',
                           last_entry_at='2022-02-02', last_access_at='2022-03-03',
                           last_status_change='2022-04-04', tags='["kept"]', meta='{"exact":true}',
                           bridge_id=f'bridge-{index}', bridge_managed=index % 2)
            if extensions:
                payload.update(extension_blob=bytes([0, index, 255]), extension_code=f'code-{index}')
            _sqlite_identity_insert(conn, 'scribe_projects', payload)
            required = {
                'scribe_entries': dict(id=f'e-{index}', ts='2020-01-01', ts_iso='2020-01-01T00:00:00Z',
                                       emoji='ℹ️', agent=test_agent, message=f'message-{index}', meta='{"n":1}',
                                       raw_line=f'raw-{index}', sha256=str(index) * 64),
                'scribe_metrics': dict(total_entries=11 + index, success_count=index, warn_count=2),
                'doc_changes': dict(doc_name='ARCHITECTURE_GUIDE.md', action='replace', agent=test_agent),
                'document_sections': dict(document_type='custom', section_id=f's-{index}',
                                          file_path=f'/fixture/{index}', content=f'content-{index}', file_hash='hash'),
                'custom_templates': dict(template_name=f't-{index}', template_content='{{exact}}'),
                'document_changes': dict(change_type='updated', metadata='{"preserve":null}'),
                'sync_status': dict(file_path=f'/sync/{index}', last_file_hash=f'h-{index}'),
                'agent_report_cards': dict(file_path=f'/report/{index}', agent_name=test_agent, overall_grade=87.5),
                'dev_plans': dict(id=index, project_name=name, plan_type='architecture', file_path=f'/plan/{index}'),
                'phases': dict(id=index, dev_plan_id=index, phase_number=index, phase_name=f'p-{index}',
                               confidence_score=0.75),
                'milestones': dict(phase_id=index, milestone_name=f'm-{index}'),
                'benchmarks': dict(benchmark_type='integrity', test_name='preserve', metric_name='bytes',
                                   metric_value=17.25, metric_unit='B'),
                'checklists': dict(phase_id=index, checklist_item=f'c-{index}', acceptance_criteria='exact'),
                'performance_metrics': dict(metric_category='testing', metric_name='duration',
                                            metric_value=3.5, metric_unit='s'),
                'scribe_entries_archive': dict(id=f'archive-{index}', ts='2020-01-01',
                                               ts_iso='2020-01-01T00:00:00Z', emoji='ℹ️',
                                               message='archived', raw_line='raw', sha256='a' * 64),
            }
            for table, row in required.items():
                _sqlite_identity_insert(conn, table, dict(project_id=index, **row))
            if extensions:
                _sqlite_identity_insert(conn, 'extension_children', dict(
                    project_id=index, nil_value=None, integer_value=2**40 + index,
                    real_value=0.125 * index, text_value=f'0{index}', blob_value=b'\x00\xff'))
            conn.execute('INSERT INTO scribe_sessions(session_id,repo_root,agent_id) VALUES(?,?,?)',
                         (f's-{index}', root, test_agent))
            conn.execute('INSERT INTO session_projects VALUES(?,?,?,?,?,?,?)',
                         (f's-{index}', name, payload['project_key'], 7 + index, 'resolved', None,
                          '2020-03-01 00:00:00'))
        conn.execute('INSERT INTO scribe_sessions(session_id,repo_root) VALUES(?,?)',
                     ('s-null', roots['repo-b']))
        conn.execute('INSERT INTO session_projects VALUES(?,?,?,?,?,?,?)',
                     ('s-null', 'shared', None, 5, 'unresolved', 'project_identity_zero_matches', '2020-03-02'))
        conn.execute('INSERT INTO agent_projects VALUES(?,?,?,?,?,?)',
                     (test_agent, 'shared', 13, '2020-03-03', test_agent, 's-1'))
        # The global compatibility row is intentionally unattributable.
        conn.execute('INSERT INTO agent_projects VALUES(?,?,?,?,?,?)',
                     ('Scribe', 'shared', 17, '2020-03-04', test_agent, None))
        conn.execute('INSERT INTO agent_recent_projects VALUES(?,?,?)', (test_agent, 'shared', '2020-03-05'))
        conn.execute("INSERT INTO scribe_projects(id,name,repo_root,progress_log_path) VALUES(900,'deleted-max','/deleted','/deleted/log')")
        conn.execute('DELETE FROM scribe_projects WHERE id=900')
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name='scribe_projects'").fetchone() == (900,)
        assert sum(row[2] == 'scribe_projects' and row[4] == 'name'
                   for table in ('session_projects', 'agent_projects', 'agent_recent_projects')
                   for row in conn.execute(f'PRAGMA foreign_key_list({table})')) == 3
    return roots


def _sqlite_identity_snapshot(path: Path) -> dict:
    """Full typed multisets: Python equality alone conflates 1 and 1.0."""
    with sqlite3.connect(path) as conn:
        schema = tuple(conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema "
                                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"))
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
        rows = {}
        columns = {}
        definitions = {}
        foreign_keys = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            definitions[table] = {row[1]: tuple(row[2:]) for row in conn.execute(f'PRAGMA table_xinfo({quoted})')}
            groups = {}
            for fk in conn.execute(f'PRAGMA foreign_key_list({quoted})'):
                groups.setdefault(fk[0], []).append((fk[1], tuple(fk[2:])))
            foreign_keys[table] = Counter(
                tuple(payload for _, payload in sorted(group)) for group in groups.values()
            )
            cursor = conn.execute(f'SELECT * FROM {quoted}')
            # FTS hidden xinfo columns are not emitted by SELECT *.
            columns[table] = tuple(column[0] for column in cursor.description)
            rows[table] = Counter(tuple((type(value).__name__, value) for value in row)
                                  for row in cursor)
        return dict(schema=schema, rows=rows, columns=columns, definitions=definitions, foreign_keys=foreign_keys)


def _sqlite_identity_assert_preserved(before: dict, after: dict) -> None:
    for table, rows in before['rows'].items():
        if table == 'sqlite_sequence':
            continue  # New setup tables may add sequences, old high-water marks cannot regress.
        expected_fks = before['foreign_keys'][table].copy()
        actual_fks = after['foreign_keys'][table].copy()
        if table in {'session_projects', 'agent_projects', 'agent_recent_projects'}:
            # Exactly these three label-only references may retire. All id,
            # session and extension relationships/actions must be identical.
            for relationships in (expected_fks, actual_fks):
                for group in list(relationships):
                    if len(group) == 1 and group[0][:3] == ('scribe_projects', 'project_name', 'name'):
                        del relationships[group]
        assert actual_fks == expected_fks, f'foreign-key relationship changed: {table}'
        for column, definition in before['definitions'][table].items():
            assert after['definitions'][table][column] == definition, (table, column)
        original_columns = before['columns'][table]
        positions = [after['columns'][table].index(column) for column in original_columns]
        projected = Counter()
        for row, count in after['rows'][table].items():
            projected[tuple(row[position] for position in positions)] += count
        assert projected == rows, f'complete typed payload changed: {table}'


async def _sqlite_identity_add_sibling(storage: SQLiteStorage, roots: dict):
    return await storage.upsert_project(name='shared', repo_root=roots['repo-b'],
                                        progress_log_path=str(Path(roots['repo-b']) / 'PROGRESS_LOG.md'),
                                        docs_json='{"owner":"B"}')


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_identity_legacy_same_label_upgrade(tmp_path: Path, test_agent: str) -> None:
    """Real old-schema RED: setup succeeds, public same-label insert must succeed."""
    path = tmp_path / 'legacy.db'
    roots = _sqlite_identity_legacy(path, test_agent)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            await storage.setup()
            own = await storage.fetch_project('shared', repo_root=roots['repo-a'])
            assert own is not None and own.id == 1
            sibling = await _sqlite_identity_add_sibling(storage, roots)
            assert sibling.id != own.id and sibling.project_key != own.project_key
            assert await storage.fetch_project('shared') is None
            assert (await storage.fetch_project('shared', project_key=sibling.project_key)).id == sibling.id
            before = _sqlite_identity_snapshot(path)
            again = await storage.upsert_project(name='shared', repo_root=roots['repo-a'],
                                                 progress_log_path=own.progress_log_path, docs_json='{"changed":"A"}')
            assert again.id == own.id
            assert (await storage.fetch_project('shared', repo_root=roots['repo-b'])).docs_json == '{"owner":"B"}'
            assert _sqlite_identity_snapshot(path)['rows']['session_projects'] == before['rows']['session_projects']
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_identity_fresh_same_label_journey(tmp_path: Path, test_agent: str) -> None:
    storage = SQLiteStorage(tmp_path / 'fresh.db')

    async def journey():
        try:
            await storage.setup()
            roots = {name: str(tmp_path / name) for name in ('repo-a', 'repo-b')}
            a = await storage.upsert_project(name='shared', repo_root=roots['repo-a'],
                                             progress_log_path=str(tmp_path / 'a.md'))
            b = await _sqlite_identity_add_sibling(storage, roots)
            assert a.project_key != b.project_key and a.id != b.id
            for session, root, record in (('s-a', roots['repo-a'], a), ('s-b', roots['repo-b'], b)):
                await storage.upsert_session(session_id=session, repo_root=root, agent_id=test_agent)
                await storage.set_session_project(session, 'shared')
                binding = await storage.get_session_project(session)
                assert binding.project_key == record.project_key
                assert binding.canonical_repo_root == root
            with storage._connect() as conn:
                assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
                assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('identity_keys', ['persisted', 'missing'])
def test_sqlite_identity_cascade_guard_extensions_and_sequence(
    tmp_path: Path, test_agent: str, identity_keys: str
) -> None:
    """N8: every discovered child, metadata byte, type and extension survives."""
    path = tmp_path / 'extensions.db'
    roots = _sqlite_identity_legacy(path, test_agent, extensions=True)
    before = _sqlite_identity_snapshot(path)
    if identity_keys == 'missing':
        # A real pre-trigger legacy row needs deterministic identity backfill.
        # The expected snapshot permits only these two fields to change back;
        # binding payload, generation and timestamps must survive C05 unchanged.
        with sqlite3.connect(path) as conn:
            conn.execute('UPDATE scribe_projects SET repo_id=NULL, project_key=NULL WHERE id=2')
    storage = SQLiteStorage(path)

    async def journey():
        try:
            await storage.setup()
            with storage._connect() as conn:
                identity = conn.execute('SELECT repo_id,project_key FROM scribe_projects WHERE id=2').fetchone()
                assert tuple(identity) == (
                    compute_repo_id(roots['repo-c']),
                    compute_project_key(repo_root=roots['repo-c'], project_name='other'),
                )
            _sqlite_identity_assert_preserved(before, _sqlite_identity_snapshot(path))
            with storage._connect() as conn:
                for obj in before['schema']:
                    if obj[1].startswith('extension_'):
                        actual = conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name=?',
                                              (obj[1],)).fetchone()
                        assert tuple(actual) == obj
                assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
                assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
            sibling = await _sqlite_identity_add_sibling(storage, roots)
            assert sibling.id > 900, 'deleted AUTOINCREMENT maximum must not be reused'
            with storage._connect() as conn:
                conn.execute("UPDATE scribe_projects SET description='new' WHERE id=1")
                assert tuple(conn.execute('SELECT * FROM extension_audit').fetchone()) == (1, 'preserve-shared', 'new')
                with pytest.raises(sqlite3.IntegrityError):
                    conn.execute("UPDATE scribe_projects SET extension_code='' WHERE id=1")
                with pytest.raises(sqlite3.IntegrityError):
                    conn.execute("UPDATE scribe_projects SET extension_code='CODE-1' WHERE id=2")
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('sibling_remains', [False, True], ids=['last-parent', 'sibling-remains'])
def test_sqlite_identity_raw_delete_cleanup_and_sibling_isolation(
    tmp_path: Path, test_agent: str, sibling_remains: bool
) -> None:
    """N1/N3: raw SQL cleanup, exactly one invalidation, C3 NULL-key scope."""
    path = tmp_path / 'delete.db'
    roots = _sqlite_identity_legacy(path, test_agent)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            await storage.setup()
            if sibling_remains:
                sibling = await _sqlite_identity_add_sibling(storage, roots)
                await storage.upsert_session(session_id='s-b', repo_root=roots['repo-b'])
                await storage.set_session_project('s-b', 'shared')
                with storage._connect() as conn:
                    conn.execute("INSERT INTO scribe_entries(id,project_id,ts,ts_iso,emoji,message,raw_line,sha256) "
                                 "VALUES('sibling-entry',?,'ts','iso','x','B bytes','B raw','B hash')", (sibling.id,))
                    _sqlite_identity_insert(conn, 'scribe_metrics', dict(
                        project_id=sibling.id, total_entries=42, success_count=19,
                        warn_count=3, error_count=2, last_update='2020-05-01'))
                    _sqlite_identity_insert(conn, 'doc_changes', dict(
                        project_id=sibling.id, doc_name='B.md', action='replace',
                        agent=test_agent, metadata='{"B":"untouched"}'))
                    _sqlite_identity_insert(conn, 'document_sections', dict(
                        project_id=sibling.id, document_type='custom', section_id='B',
                        content='B document bytes', file_hash='B document hash'))
                    _sqlite_identity_insert(conn, 'dev_plans', dict(
                        id=sibling.id, project_id=sibling.id, project_name='shared',
                        plan_type='architecture', file_path='/B/plan', metadata='{"B":7}'))
                    _sqlite_identity_insert(conn, 'phases', dict(
                        project_id=sibling.id, dev_plan_id=sibling.id, phase_number=1,
                        phase_name='B phase', confidence_score=0.875, metadata='{"B":null}'))
            before = _sqlite_identity_snapshot(path)
            with storage._connect() as conn:
                conn.execute('DELETE FROM scribe_projects WHERE id=?', (1,))
                rows = {row['session_id']: dict(row) for row in conn.execute('SELECT * FROM session_projects')}
                assert rows['s-1']['binding_state'] == 'unresolved'
                assert rows['s-1']['project_key'] is None
                assert rows['s-1']['binding_generation'] == 9
                assert rows['s-1']['project_name'] == ('shared' if sibling_remains else None)
                assert rows['s-1']['binding_state_reason'] == (
                    'project_identity_zero_matches' if sibling_remains else 'project_name_absent')
                assert rows['s-null']['project_name'] == ('shared' if sibling_remains else None)
                assert rows['s-null']['binding_generation'] == (5 if sibling_remains else 6)
                agents = {row['agent_id']: dict(row) for row in conn.execute('SELECT * FROM agent_projects')}
                assert agents[test_agent]['project_name'] is None
                assert agents[test_agent]['version'] == 14
                assert agents['Scribe']['project_name'] == ('shared' if sibling_remains else None)
                assert agents['Scribe']['version'] == (17 if sibling_remains else 18)
                recent_count = conn.execute("SELECT COUNT(*) FROM agent_recent_projects WHERE project_name='shared'").fetchone()[0]
                assert recent_count == int(sibling_remains)
                assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
                assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
                cascade_tables = {
                    table for table in before['columns']
                    for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")')
                    if fk[2] == 'scribe_projects' and fk[3] == 'project_id' and fk[6] == 'CASCADE'
                }
            after = _sqlite_identity_snapshot(path)
            # Every non-target id child is byte/type-identical, not just its count.
            for table, columns in before['columns'].items():
                if 'project_id' not in columns:
                    continue
                position = columns.index('project_id')
                expected = Counter({row: count for row, count in before['rows'][table].items()
                                    if row[position] != ('int', 1)})
                if table not in cascade_tables:
                    expected = before['rows'][table]
                assert after['rows'][table] == expected, table
            for session in ('s-2', 's-b') if sibling_remains else ('s-2',):
                index = before['columns']['session_projects'].index('session_id')
                prior = Counter({row: count for row, count in before['rows']['session_projects'].items()
                                 if row[index] == ('str', session)})
                current = Counter({row: count for row, count in after['rows']['session_projects'].items()
                                   if row[index] == ('str', session)})
                assert current == prior
            if sibling_remains:
                # C3: preserve the complete unattributable row, including time.
                for table, column, value in (('agent_projects', 'agent_id', 'Scribe'),
                                             ('session_projects', 'session_id', 's-null')):
                    index = before['columns'][table].index(column)
                    assert [row for row in before['rows'][table] if row[index] == ('str', value)] == [
                        row for row in after['rows'][table] if row[index] == ('str', value)]
                assert after['rows']['agent_recent_projects'] == before['rows']['agent_recent_projects']
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_identity_inconsistent_nonnull_key_fails_without_write(tmp_path: Path, test_agent: str) -> None:
    """C3: an inconsistent foreign key is a validation failure, never label cleanup."""
    path = tmp_path / 'inconsistent.db'
    _sqlite_identity_legacy(path, test_agent)
    with sqlite3.connect(path) as conn:
        foreign_key = conn.execute('SELECT project_key FROM scribe_projects WHERE id=2').fetchone()[0]
        conn.execute("UPDATE session_projects SET project_key=? WHERE session_id='s-1'", (foreign_key,))
    before = _sqlite_identity_snapshot(path)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            with pytest.raises((RuntimeError, sqlite3.DatabaseError, ValueError)):
                await storage.setup()
            assert not storage._initialised
            assert _sqlite_identity_snapshot(path) == before
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('target', ['absent', 'ambiguous', 'unique'])
def test_sqlite_identity_name_mutations_are_guarded(tmp_path: Path, test_agent: str, target: str) -> None:
    """N4: zero/ambiguous mutations have zero effects; scoped/unique paths work."""
    path = tmp_path / 'mutation.db'
    roots = _sqlite_identity_legacy(path, test_agent)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            await storage.setup()
            if target == 'ambiguous':
                await _sqlite_identity_add_sibling(storage, roots)
            name = 'missing' if target == 'absent' else 'shared'
            before = _sqlite_identity_snapshot(path)
            updated = await storage.update_project_docs(name, '{"new":true}')
            assert updated is (target == 'unique')
            if target != 'unique':
                assert _sqlite_identity_snapshot(path) == before
                assert await storage.delete_project(name) is False
                assert _sqlite_identity_snapshot(path) == before
            else:
                assert (await storage.fetch_project(name, repo_root=roots['repo-a'])).docs_json == '{"new":true}'
                assert await storage.delete_project(name) is True
                assert await storage.fetch_project(name) is None
                with storage._connect() as conn:
                    agents = {row['agent_id']: dict(row) for row in conn.execute('SELECT * FROM agent_projects')}
                    assert test_agent in agents and 'Scribe' in agents, 'public deletion erased compatibility rows'
                    assert agents[test_agent]['project_name'] is None
                    assert agents[test_agent]['version'] == 14
                    assert agents['Scribe']['project_name'] is None
                    assert agents['Scribe']['version'] == 18
            if target == 'ambiguous':
                assert await storage.update_project_docs('shared', '{"scoped":"A"}', repo_root=roots['repo-a']) is True
                assert (await storage.fetch_project('shared', repo_root=roots['repo-a'])).docs_json == '{"scoped":"A"}'
                assert (await storage.fetch_project('shared', repo_root=roots['repo-b'])).docs_json == '{"owner":"B"}'
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_identity_forged_key_and_local_binding(tmp_path: Path, test_agent: str) -> None:
    """N10 remains independently runnable without duplicate-name support."""
    path = tmp_path / 'forged.db'
    roots = _sqlite_identity_legacy(path, test_agent)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            await storage.setup()
            local = await storage.fetch_project('shared', repo_root=roots['repo-a'])
            foreign = await storage.fetch_project('other', repo_root=roots['repo-c'])
            with storage._connect() as conn:
                sibling_before = tuple(conn.execute("SELECT * FROM session_projects WHERE session_id='s-2'").fetchone())
                conn.execute("INSERT INTO scribe_sessions(session_id,repo_root) VALUES('forged',?)", (roots['repo-a'],))
                conn.execute("INSERT INTO session_projects(session_id,project_name,project_key,binding_state,binding_state_reason) "
                             "VALUES('forged','shared',?,'resolved',NULL)",
                             (foreign.project_key,))
                row = conn.execute("SELECT * FROM session_projects WHERE session_id='forged'").fetchone()
                assert (row['project_key'], row['binding_state'], row['binding_state_reason']) == (
                    None, 'unresolved', 'project_key_mismatch')
                assert row['binding_generation'] == 1
                conn.execute("UPDATE session_projects SET project_key=?,binding_state='resolved',binding_state_reason=NULL "
                             "WHERE session_id='forged'", (local.project_key,))
                row = conn.execute("SELECT * FROM session_projects WHERE session_id='forged'").fetchone()
                assert (row['project_key'], row['binding_state'], row['binding_generation']) == (local.project_key, 'resolved', 2)
                assert tuple(conn.execute("SELECT * FROM session_projects WHERE session_id='s-2'").fetchone()) == sibling_before
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_identity_parent_rename_guard(tmp_path: Path, test_agent: str) -> None:
    """N11: even an unreferenced parent cannot change its identity label."""
    path = tmp_path / 'rename.db'
    _sqlite_identity_legacy(path, test_agent)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            await storage.setup()
            # A child FK alone is insufficient: exercise a childless row too.
            solo = await storage.upsert_project(name='childless', repo_root=str(tmp_path),
                                                progress_log_path=str(tmp_path / 'log'))
            before = _sqlite_identity_snapshot(path)
            with storage._connect() as conn:
                conn.execute('UPDATE scribe_projects SET name=name WHERE id=?', (solo.id,))
                conn.commit()
                assert _sqlite_identity_snapshot(path) == before
                with pytest.raises(sqlite3.IntegrityError):
                    conn.execute("UPDATE scribe_projects SET name='renamed' WHERE id=?", (solo.id,))
                conn.rollback()
            assert _sqlite_identity_snapshot(path) == before
        finally:
            await storage.close()
    asyncio.run(journey())


def _sqlite_identity_fault_connections(monkeypatch: pytest.MonkeyPatch, path: Path, fault: str):
    """Inject IO faults at observable SQL boundaries, executing real SQLite DDL."""
    original_connect = sqlite3.connect
    observations = dict(connections=[], fired=False, attempted_off=False, drops=[], before=None)

    class FaultConnection(sqlite3.Connection):
        migrating = False
        replaced = False
        rollback_seen = False
        closed = False
        transaction_at_close = False

        def execute(self, sql, parameters=()):
            normalized = re.sub(r'["`\[\]]', '', ' '.join(sql.upper().split()))
            if re.match(r'PRAGMA FOREIGN_KEYS\s*=\s*(OFF|0)', normalized):
                self.migrating = True
                observations['attempted_off'] = True
                if observations['before'] is None:
                    observations['before'] = _sqlite_identity_snapshot(path)
                if fault == 'off-noop':
                    observations['fired'] = True
                    return super().execute('PRAGMA foreign_keys')
                if fault == 'active-transaction':
                    observations['fired'] = True
                    super().execute('BEGIN')
            if self.migrating and re.match(r'PRAGMA FOREIGN_KEYS\s*=\s*(ON|1)', normalized) and fault == 'restore-on':
                observations['fired'] = True
                return super().execute('PRAGMA foreign_keys')
            if re.match(r'DROP TABLE(?: IF EXISTS)? (SCRIBE_PROJECTS|SESSION_PROJECTS|AGENT_PROJECTS|AGENT_RECENT_PROJECTS)(?:\s|;|$)', normalized):
                observations['drops'].append(normalized)
            cursor = super().execute(sql, parameters)
            if self.migrating and re.match(r'DROP TABLE(?: IF EXISTS)? SCRIBE_PROJECTS(?:\s|;|$)', normalized):
                self.replaced = True
                if fault in ('after-parent', 'rollback'):
                    observations['fired'] = True
                    raise sqlite3.OperationalError('injected identity after-parent failure')
            if self.migrating and fault == 'after-copy' and normalized.startswith('INSERT') and re.search(
                r'FROM SCRIBE_PROJECTS(?:\s|;|$)', normalized
            ):
                observations['fired'] = True
                raise sqlite3.OperationalError('injected identity after-copy failure')
            if self.replaced and fault == 'objects' and normalized.startswith('CREATE') and 'EXTENSION_PROJECT_' in normalized:
                observations['fired'] = True
                raise sqlite3.OperationalError('injected identity object restoration failure')
            if self.replaced and fault == 'validation' and 'PRAGMA FOREIGN_KEY_CHECK' in normalized:
                observations['fired'] = True
                raise sqlite3.OperationalError('injected identity validation failure')
            if self.replaced and fault == 'cancel' and 'PRAGMA FOREIGN_KEY_CHECK' in normalized:
                observations['fired'] = True
                raise asyncio.CancelledError('injected identity cancellation')
            return cursor

        def commit(self):
            if self.replaced and fault == 'commit':
                observations['fired'] = True
                raise sqlite3.OperationalError('injected identity commit failure')
            return super().commit()

        def rollback(self):
            self.rollback_seen = True
            if self.replaced and fault == 'rollback':
                raise sqlite3.OperationalError('injected identity rollback failure')
            return super().rollback()

        def close(self):
            self.transaction_at_close = self.in_transaction
            self.closed = True
            return super().close()

    def connect(database, *args, **kwargs):
        # Snapshot/readback connections intentionally bypass fault injection.
        # Only product connections have check_same_thread=False.
        if Path(database) == path and kwargs.get('check_same_thread') is False:
            kwargs['factory'] = FaultConnection
            connection = original_connect(database, *args, **kwargs)
            observations['connections'].append(connection)
            return connection
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', connect)
    return observations


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('fault', ['after-copy', 'after-parent', 'objects', 'validation', 'commit', 'cancel'])
def test_sqlite_identity_migration_failure_rolls_back(
    tmp_path: Path, test_agent: str, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """N6: injected failure is reached, rolled back on owner, and never ready."""
    path = tmp_path / 'failure.db'
    _sqlite_identity_legacy(path, test_agent, extensions=True)
    observed = _sqlite_identity_fault_connections(monkeypatch, path, fault)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            with pytest.raises((sqlite3.DatabaseError, RuntimeError, asyncio.CancelledError)):
                await storage.setup()
            assert observed['fired'], f'failure boundary never exercised: {fault}'
            assert not storage._initialised
            assert observed['before'] is not None
            assert _sqlite_identity_snapshot(path) == observed['before']
            owners = [conn for conn in observed['connections'] if conn.migrating]
            assert owners and all(conn.rollback_seen for conn in owners)
            assert all(not conn.transaction_at_close for conn in owners)
            with storage._connect() as conn:
                assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
                assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('fault', ['off-noop', 'active-transaction'])
def test_sqlite_identity_pragma_failure_aborts_before_drop(
    tmp_path: Path, test_agent: str, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """N7: a failed OFF switch cannot cascade children away."""
    path = tmp_path / 'pragma.db'
    _sqlite_identity_legacy(path, test_agent, extensions=True)
    original = _sqlite_identity_snapshot(path)
    observed = _sqlite_identity_fault_connections(monkeypatch, path, fault)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            with pytest.raises((sqlite3.DatabaseError, RuntimeError)):
                await storage.setup()
            assert observed['attempted_off'] and observed['fired']
            assert observed['drops'] == []
            assert not storage._initialised
            assert _sqlite_identity_snapshot(path) == observed['before']
            _sqlite_identity_assert_preserved(original, _sqlite_identity_snapshot(path))
            with storage._connect() as conn:
                assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('fault', ['rollback', 'restore-on'])
def test_sqlite_identity_failed_connection_is_quarantined(
    tmp_path: Path, test_agent: str, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """N6/C5: failed rollback/restoration never returns poisoned owners to a pool."""
    path = tmp_path / 'quarantine.db'
    _sqlite_identity_legacy(path, test_agent, extensions=True)
    observed = _sqlite_identity_fault_connections(monkeypatch, path, fault)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            with pytest.raises((sqlite3.DatabaseError, RuntimeError)):
                await storage.setup()
            assert observed['fired']
            assert not storage._initialised
            owners = [conn for conn in observed['connections'] if conn.migrating]
            assert owners and all(conn.closed for conn in owners)
            for conn in owners:
                with pytest.raises(sqlite3.ProgrammingError, match='closed'):
                    conn.execute('SELECT 1')
            assert storage._pool is None or storage._pool.active == 0
            if fault == 'rollback':
                assert _sqlite_identity_snapshot(path) == observed['before']
            with storage._connect() as conn:
                assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_identity_reopen_is_canonical_and_stable(tmp_path: Path, test_agent: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """N9: canonical predicate, one session FK, parent controls, no replay DDL."""
    path = tmp_path / 'reopen.db'
    _sqlite_identity_legacy(path, test_agent)
    first = SQLiteStorage(path)
    asyncio.run(first.setup())
    asyncio.run(first.close())
    with first._connect() as conn:
        assert conn.execute(f'SELECT ({sqlite_schema.SESSION_PROJECTS_CANONICAL_PREDICATE})').fetchone()[0] == 1
        fks = conn.execute('PRAGMA foreign_key_list(session_projects)').fetchall()
        assert [(row['table'], row['from'], row['to'], row['on_delete']) for row in fks] == [
            ('scribe_sessions', 'session_id', 'session_id', 'CASCADE')]
        parent_triggers = [row[0].upper() for row in conn.execute(
            "SELECT sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='scribe_projects'")]
        assert any('DELETE' in sql and 'SESSION_PROJECTS' in sql for sql in parent_triggers)
        assert any('UPDATE OF NAME' in sql and 'RAISE' in sql for sql in parent_triggers)
    before = _sqlite_identity_snapshot(path)
    from scribe_mcp.storage.sqlite.internals import SQLiteInternals
    original = SQLiteInternals.connect
    statements = []

    def traced_connect(internals):
        conn = original(internals)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(SQLiteInternals, 'connect', traced_connect)
    for _ in range(2):
        reopened = SQLiteStorage(path)
        try:
            asyncio.run(reopened.setup())
            assert _sqlite_identity_snapshot(path) == before
        finally:
            asyncio.run(reopened.close())
    destructive = [sql for sql in statements if re.match(r'\s*(DROP TABLE|ALTER TABLE)', sql, re.I)]
    assert destructive == []


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_sqlite_identity_concurrent_reopen(tmp_path: Path, test_agent: str) -> None:
    """N9: independent storage owners serialize the actual legacy upgrade."""
    path = tmp_path / 'concurrent.db'
    roots = _sqlite_identity_legacy(path, test_agent)
    before = _sqlite_identity_snapshot(path)
    barrier = threading.Barrier(2)

    def reopen():
        storage = SQLiteStorage(path)
        barrier.wait(timeout=10)
        try:
            asyncio.run(storage.setup())
            return 'ready'
        except sqlite3.OperationalError as exc:
            assert 'locked' in str(exc).lower(), str(exc)
            assert not storage._initialised
            return 'bounded-contention'
        finally:
            asyncio.run(storage.close())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reopen(), range(2)))
    assert 'ready' in results
    storage = SQLiteStorage(path)

    async def journey():
        try:
            await storage.setup()
            _sqlite_identity_assert_preserved(before, _sqlite_identity_snapshot(path))
            sibling = await _sqlite_identity_add_sibling(storage, roots)
            assert sibling.id > 900
            with storage._connect() as conn:
                assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
                assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('operation', ['delete', 'docs'])
@pytest.mark.parametrize('serial_order', ['insert-before-write', 'insert-behind-lock'])
def test_sqlite_identity_two_connection_mutation_order(
    tmp_path: Path, test_agent: str, monkeypatch: pytest.MonkeyPatch, operation: str, serial_order: str
) -> None:
    """N5: barriers at the real SQLite boundary, with independent writer owners."""
    path = tmp_path / 'race.db'
    roots = _sqlite_identity_legacy(path, test_agent)
    original_connect = sqlite3.connect
    reached, release, insert_attempted = threading.Event(), threading.Event(), threading.Event()
    state = dict(armed=False, owner=None, paused=False)

    class RaceConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            normalized = ' '.join(sql.upper().split())
            targeted = (normalized.startswith('DELETE FROM SCRIBE_PROJECTS')
                        or normalized.startswith('DELETE FROM AGENT_PROJECTS')
                        or (normalized.startswith('UPDATE SCRIBE_PROJECTS') and 'DOCS_JSON' in normalized))
            is_owner = state['armed'] and id(self) == state['owner']
            if (state['armed'] and id(self) != state['owner']
                and (normalized.startswith('INSERT INTO SCRIBE_PROJECTS')
                     or normalized.startswith('CREATE UNIQUE INDEX'))):
                insert_attempted.set()
            before = serial_order == 'insert-before-write'
            boundary = targeted or normalized.startswith('BEGIN IMMEDIATE')
            if is_owner and not state['paused'] and boundary and before and not self.in_transaction:
                state['paused'] = True
                reached.set()
                assert release.wait(10), 'controller did not release pre-write barrier'
            cursor = super().execute(sql, parameters)
            if is_owner and not state['paused'] and boundary and not before and self.in_transaction:
                state['paused'] = True
                reached.set()
                assert release.wait(10), 'controller did not release held-write-lock barrier'
            return cursor

    def connect(database, *args, **kwargs):
        if Path(database) == path and kwargs.get('check_same_thread') is False:
            kwargs['factory'] = RaceConnection
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', connect)
    writer, sibling_writer = SQLiteStorage(path), SQLiteStorage(path)
    asyncio.run(writer.setup())
    asyncio.run(sibling_writer.setup())
    owner = writer._pool.acquire()
    state['owner'] = id(owner)
    writer._pool.release(owner)
    state['armed'] = True

    async def mutate():
        if operation == 'delete':
            return await writer.delete_project('shared')
        return await writer.update_project_docs('shared', '{"race":"A"}')

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            mutation = executor.submit(lambda: asyncio.run(mutate()))
            try:
                assert reached.wait(10), 'public mutation never reached a write serialization boundary'
                insertion = executor.submit(lambda: asyncio.run(_sqlite_identity_add_sibling(sibling_writer, roots)))
                if serial_order == 'insert-before-write':
                    sibling = insertion.result(timeout=10)
                    expected = _sqlite_identity_snapshot(path)
                    release.set()
                    assert mutation.result(timeout=10) is False
                    assert _sqlite_identity_snapshot(path) == expected
                else:
                    assert insert_attempted.wait(10), 'second connection never attempted competing insertion'
                    assert not insertion.done(), 'second writer bypassed an acquired SQLite write lock'
                    release.set()
                    assert mutation.result(timeout=10) is True
                    sibling = insertion.result(timeout=10)
                    fetched = asyncio.run(sibling_writer.fetch_project('shared', repo_root=roots['repo-b']))
                    assert fetched.id == sibling.id and fetched.docs_json == '{"owner":"B"}'
                    with writer._connect() as conn:
                        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
                        other = conn.execute('SELECT description FROM scribe_projects WHERE id=2').fetchone()[0]
                        assert other == 'preserve-other'
            finally:
                release.set()
                # Consume completion/exception before any connection is closed.
                # A failed legacy insertion can leave its owner's transaction
                # open. Close that owner before awaiting the first writer, and
                # retain the original prerequisite failure as the test error.
                if 'insertion' in locals() and insertion.done() and insertion.exception() is not None:
                    asyncio.run(sibling_writer.close())
                    try:
                        mutation.result(timeout=10)
                    except (sqlite3.DatabaseError, AssertionError):
                        pass
                elif not mutation.done():
                    mutation.result(timeout=10)
    finally:
        state['armed'] = False
        asyncio.run(writer.close())
        asyncio.run(sibling_writer.close())


async def _sqlite_identity_reader_context(router, storage, root, session, test_agent, target_name):
    from dataclasses import replace
    from scribe_mcp.shared.execution_context import (
        AgentAttributionV1, AuthorizationEvidenceV1, ResolvedProjectTargetV1,
        build_resolved_request_context,
    )
    binding = await storage.get_session_project(session)
    record = await storage.fetch_project(target_name, repo_root=root)
    context = await router.build_execution_context(dict(
        repo_root=root, session_id=session, stable_session_id=session,
        mode='project', intent='identity-regression',
        transport_session_id=f'identity-reader::actor={test_agent}',
        scope_provenance=dict(repo_root='verified', stable_session_id='verified'),
        trust_level='verified', session_binding=binding,
    ))
    immutable = build_resolved_request_context(
        caller_session_key=session,
        resolved_target=ResolvedProjectTargetV1(
            project_key=record.project_key, project_name=record.name,
            canonical_repo_root=root, repository_id=record.repo_id,
            resolution_source='caller_default', default_binding_generation=binding.binding_generation,
        ),
        agent_attribution=AgentAttributionV1(agent=test_agent, agent_id=test_agent),
        correlation_id='identity-reader-request', operating_mode='project',
        authorization_evidence=AuthorizationEvidenceV1(source='server_verified', verified=True,
                                                       scope_refs=(f'repo:{record.repo_id}',)),
    )
    return replace(context, resolved_request_context=immutable)


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('reader', ['helper', 'state', 'get-project'])
@pytest.mark.parametrize('selection', ['attributable', 'unattributable', 'recents-only'])
@pytest.mark.parametrize('cache', ['cold', 'warm'])
@pytest.mark.parametrize('authority', ['local', 'absent'])
def test_sqlite_identity_selection_never_repoints(
    tmp_path: Path, test_agent: str, monkeypatch: pytest.MonkeyPatch,
    reader: str, selection: str, cache: str, authority: str
) -> None:
    """N2: singleton B plus stale A metadata is valid on the old schema too."""
    from scribe_mcp import server
    from scribe_mcp.shared.execution_context import RouterContextManager
    from scribe_mcp.state.agent_manager import AgentContextManager
    from scribe_mcp.state.manager import StateManager
    from scribe_mcp.tools.agent_project_utils import get_agent_project_data
    from scribe_mcp.tools.get_project import get_project

    path = tmp_path / 'reader.db'
    roots = {name: str(tmp_path / name) for name in ('repo-a', 'repo-b')}
    for root in roots.values():
        Path(root).mkdir()
        (Path(root) / 'PROGRESS_LOG.md').write_text(f'private:{root}\n')
    storage = SQLiteStorage(path)
    manager = StateManager(path=path, storage_backend=storage)
    router = RouterContextManager(storage_backend=storage)
    agent_manager = AgentContextManager(storage, manager)
    monkeypatch.setattr(server, 'storage_backend', storage)
    monkeypatch.setattr(server, 'state_manager', manager)
    monkeypatch.setattr(server, 'router_context_manager', router)
    monkeypatch.setattr(server, 'agent_context_manager', agent_manager)
    monkeypatch.setattr(server, 'agent_identity', None)

    async def journey():
        token = None
        try:
            await storage.setup()
            manager._backend_ready = True
            await storage.upsert_project(name='local', repo_root=roots['repo-a'],
                                          progress_log_path=str(Path(roots['repo-a']) / 'PROGRESS_LOG.md'))
            foreign = await _sqlite_identity_add_sibling(storage, roots)
            await storage.upsert_session(session_id='reader-a', repo_root=roots['repo-a'], agent_id=test_agent)
            await storage.set_session_project('reader-a', 'local')
            if selection != 'recents-only':
                await storage.set_agent_project(test_agent, 'shared', expected_version=None, updated_by=test_agent,
                                                session_id='reader-a' if selection == 'attributable' else '')
            with storage._connect() as conn:
                conn.execute('INSERT INTO agent_recent_projects(agent_id,project_name) VALUES(?,?)', (test_agent, 'shared'))
                # The global compatibility label is deliberately inert.
                if selection != 'recents-only':
                    conn.execute('INSERT INTO agent_projects(agent_id,project_name,version) VALUES(?,?,?)', ('Scribe', 'shared', 19))
            manager._recent_projects_cache = ['shared']
            if cache == 'warm':
                stale = dict(name='shared', root=roots['repo-b'], project_key=foreign.project_key,
                             progress_log=str(Path(roots['repo-b']) / 'PROGRESS_LOG.md'))
                manager._projects_cache = {'shared': dict(stale)}
                manager._projects_cache_at = float('inf')
                manager._session_projects_cache['reader-a'] = dict(stale)
            if authority == 'local':
                context = await _sqlite_identity_reader_context(router, storage, roots['repo-a'], 'reader-a', test_agent, 'local')
                token = router.set_current(context)
            before = _sqlite_identity_snapshot(path)
            file_before = (Path(roots['repo-b']) / 'PROGRESS_LOG.md').read_bytes()
            if reader == 'helper':
                project, recent = await get_agent_project_data(test_agent)
                assert not project or project.get('name') != 'shared', project
            elif reader == 'state':
                state = await manager.load()
                assert state.current_project != 'shared', state
            else:
                result = await get_project(agent=test_agent, format='structured')
                assert result.get('name') != 'shared', result
                assert result.get('project', {}).get('name') != 'shared', result
            assert (Path(roots['repo-b']) / 'PROGRESS_LOG.md').read_bytes() == file_before
            after = _sqlite_identity_snapshot(path)
            for table in ('scribe_projects', 'session_projects', 'agent_projects', 'scribe_entries'):
                assert after['rows'][table] == before['rows'][table], table
            if authority == 'local':
                assert router.get_current() is context
                assert context.resolved_request_context.resolved_target.project_name == 'local'
        finally:
            if token is not None:
                router.reset(token)
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('reader', ['helper', 'state', 'get-project'])
def test_sqlite_identity_legitimate_reader_still_resolves(
    tmp_path: Path, test_agent: str, monkeypatch: pytest.MonkeyPatch, reader: str
) -> None:
    """N2 positive: current verified B authority still selects B without writes."""
    from scribe_mcp import server
    from scribe_mcp.shared.execution_context import RouterContextManager
    from scribe_mcp.state.agent_manager import AgentContextManager
    from scribe_mcp.state.manager import StateManager
    from scribe_mcp.tools.agent_project_utils import get_agent_project_data
    from scribe_mcp.tools.get_project import get_project

    path = tmp_path / 'legitimate-reader.db'
    root = tmp_path / 'repo-b'
    root.mkdir()
    log = root / 'PROGRESS_LOG.md'
    log.write_text('private B data\n')
    storage = SQLiteStorage(path)
    manager = StateManager(path=path, storage_backend=storage)
    router = RouterContextManager(storage_backend=storage)
    monkeypatch.setattr(server, 'storage_backend', storage)
    monkeypatch.setattr(server, 'state_manager', manager)
    monkeypatch.setattr(server, 'router_context_manager', router)
    monkeypatch.setattr(server, 'agent_context_manager', AgentContextManager(storage, manager))
    monkeypatch.setattr(server, 'agent_identity', None)

    async def journey():
        token = None
        try:
            await storage.setup()
            manager._backend_ready = True
            record = await storage.upsert_project(name='shared', repo_root=str(root), progress_log_path=str(log))
            await storage.upsert_session(session_id='reader-b', repo_root=str(root), agent_id=test_agent)
            await storage.set_session_project('reader-b', 'shared')
            await storage.set_agent_project(test_agent, 'shared', expected_version=None,
                                            updated_by=test_agent, session_id='reader-b')
            context = await _sqlite_identity_reader_context(router, storage, str(root), 'reader-b', test_agent, 'shared')
            token = router.set_current(context)
            before = _sqlite_identity_snapshot(path)
            if reader == 'helper':
                project, recent = await get_agent_project_data(test_agent)
                assert project['name'] == 'shared' and project['root'] == str(root)
                assert 'shared' in recent
            elif reader == 'state':
                state = await manager.load()
                assert state.current_project == 'shared'
                assert state.get_session_project('reader-b')['project_key'] == record.project_key
                assert state.get_project('shared')['root'] == str(root)
            else:
                result = await get_project(agent=test_agent, format='structured')
                project = result.get('project') or result
                assert project['name'] == 'shared' and project['root'] == str(root)
            assert router.get_current() is context
            assert log.read_text() == 'private B data\n'
            after = _sqlite_identity_snapshot(path)
            for table in ('scribe_projects', 'session_projects', 'agent_projects', 'scribe_entries'):
                assert after['rows'][table] == before['rows'][table], table
        finally:
            if token is not None:
                router.reset(token)
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('invalid_shape', ['unexpected-name-fk', 'dangling-id-fk'])
def test_sqlite_identity_unknown_relation_fails_before_mutation(
    tmp_path: Path, test_agent: str, invalid_shape: str
) -> None:
    """Unknown incoming name FKs and existing dangling rows cannot be discarded."""
    path = tmp_path / 'unsupported.db'
    _sqlite_identity_legacy(path, test_agent)
    # This offline writer constructs pre-existing corrupt input only.
    # Product connections still require foreign_keys=ON.
    with sqlite3.connect(path) as conn:
        if invalid_shape == 'unexpected-name-fk':
            conn.execute('CREATE TABLE unknown_label_child (label TEXT REFERENCES scribe_projects(name))')
            conn.execute("INSERT INTO unknown_label_child VALUES('shared')")
        else:
            conn.execute('CREATE TABLE unknown_id_child (id INTEGER REFERENCES scribe_projects(id))')
            conn.execute('INSERT INTO unknown_id_child VALUES(987654)')
    before = _sqlite_identity_snapshot(path)
    storage = SQLiteStorage(path)

    async def journey():
        try:
            with pytest.raises((sqlite3.DatabaseError, RuntimeError, ValueError)):
                await storage.setup()
            assert not storage._initialised
            assert _sqlite_identity_snapshot(path) == before
        finally:
            await storage.close()
    asyncio.run(journey())


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize('scenario', ['authorized-explicit', 'foreign-append', 'ambiguous-unbound'])
def test_sqlite_identity_real_runtime_targeting_preserves_defaults(
    tmp_path: Path, test_agent: str, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """Real dispatch/tools/backend: request-local targets cannot mutate defaults."""
    from dataclasses import replace
    from types import SimpleNamespace
    import importlib
    from scribe_mcp import server
    from scribe_mcp.shared.execution_context import RouterContextManager, ResolvedRequestContextV1
    from scribe_mcp.shared.tool_runtime import execute_tool_call
    from scribe_mcp.state.agent_manager import AgentContextManager
    from scribe_mcp.state.manager import StateManager
    from scribe_mcp.tools.append_entry import append_entry
    from scribe_mcp.tools.get_project import get_project

    path = tmp_path / 'runtime.db'
    root_a, root_b = tmp_path / 'repo-a', tmp_path / 'repo-b'
    local_settings = replace(
        server.settings, project_root=tmp_path, default_repo_root=tmp_path,
        trusted_repo_roots=(root_a, root_b), default_state_path=tmp_path / 'state.json',
        sqlite_path=path, db_url=None, allow_network=False,
    )
    monkeypatch.setattr(server, 'settings', local_settings)
    monkeypatch.setattr(importlib.import_module('scribe_mcp.tools.append_entry'), 'settings', local_settings)
    for root in (root_a, root_b):
        root.mkdir()
        (root / '.git').mkdir()
    storage = SQLiteStorage(path)
    manager = StateManager(path=path, storage_backend=storage)
    router = RouterContextManager(storage_backend=storage)
    monkeypatch.setattr(server, 'storage_backend', storage)
    monkeypatch.setattr(server, 'state_manager', manager)
    monkeypatch.setattr(server, 'router_context_manager', router)
    monkeypatch.setattr(server, 'agent_context_manager', AgentContextManager(storage, manager))
    monkeypatch.setattr(server, 'agent_identity', None)
    observed = []

    async def actual_get(agent, project=None, format='structured'):
        context = router.get_current()
        observed.append(context)
        if scenario == 'authorized-explicit':
            assert isinstance(context.resolved_request_context, ResolvedRequestContextV1)
            immutable = context.resolved_request_context
            assert immutable.resolved_target.project_name == 'explicit'
            assert immutable.resolved_target.canonical_repo_root == str(root_a)
            result = await get_project(agent=agent, project=project, format=format)
            assert router.get_current() is context
            assert context.resolved_request_context is immutable
            return result
        return await get_project(agent=agent, project=project, format=format)

    async def actual_append(agent, project, message, format='structured'):
        observed.append(router.get_current())
        return await append_entry(agent=agent, project=project, message=message, format=format)

    async def journey():
        try:
            await storage.setup()
            manager._backend_ready = True
            for name, root in (('shared', root_a), ('explicit', root_a), ('foreign', root_b), ('shared', root_b)):
                log = root / f'{name}.md'
                log.write_text(f'{root.name}/{name}:preserved\n')
                await storage.upsert_project(name=name, repo_root=str(root), progress_log_path=str(log))
            transport = f'identity-runtime::actor={test_agent}'
            await storage.upsert_session(session_id='runtime-a', transport_session_id=transport,
                                          repo_root=str(root_a), agent_id=test_agent, mode='project')
            await storage.set_session_project('runtime-a', 'shared')
            await storage.set_agent_project(test_agent, 'shared', expected_version=None,
                                            updated_by=test_agent, session_id='runtime-a')
            before = _sqlite_identity_snapshot(path)
            files = {str(file): file.read_bytes() for root in (root_a, root_b)
                     for file in root.rglob('*') if file.is_file()}
            tool = 'append_entry' if scenario == 'foreign-append' else 'get_project'
            arguments = dict(agent=test_agent, format='structured',
                             project={'authorized-explicit': 'explicit', 'foreign-append': 'foreign',
                                      'ambiguous-unbound': 'shared'}[scenario])
            if tool == 'append_entry':
                arguments['message'] = 'must never reach foreign file'
            context_payload = dict(mode='project', transport_session_id=transport)
            transport_base = 'identity-runtime'
            if scenario == 'ambiguous-unbound':
                context_payload['transport_session_id'] = f'identity-unbound::actor={test_agent}'
                transport_base = 'identity-unbound'
            try:
                result = await execute_tool_call(
                    name=tool, arguments=arguments, kwargs={'context': context_payload},
                    registry={'get_project': actual_get, 'append_entry': actual_append},
                    app=SimpleNamespace(request_context=SimpleNamespace(
                        request=SimpleNamespace(headers={'mcp-session-id': transport_base}))),
                    storage_backend=storage,
                    settings=SimpleNamespace(project_root=tmp_path / 'unregistered-server-root', public_release=False),
                    state_manager=manager, router_context_manager=router,
                    sentinel_only=set(), sentinel_allowed={'get_project'},
                    log_scope_violation_cb=lambda *_args, **_kwargs: None,
                )
            except ValueError as exc:
                assert scenario != 'authorized-explicit', str(exc)
                result = {'ok': False, 'error': str(exc)}
            if scenario == 'authorized-explicit':
                project = result.get('project') or result
                assert project['name'] == 'explicit' and project['root'] == str(root_a)
                assert observed
            else:
                assert result.get('ok') is False or result.get('error'), result
            after = _sqlite_identity_snapshot(path)
            for table in ('session_projects', 'agent_projects', 'scribe_projects', 'scribe_entries'):
                assert after['rows'][table] == before['rows'][table], table
            assert {str(file): file.read_bytes() for root in (root_a, root_b)
                    for file in root.rglob('*') if file.is_file()} == files
        finally:
            await storage.close()
    asyncio.run(journey())
