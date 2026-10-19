from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import asyncpg
import pytest

from scribe_mcp.storage.postgres import schema as postgres_schema
from scribe_mcp.storage.pool import SQLiteConnectionPool
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.storage.sqlite import schema as sqlite_schema


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
def test_fresh_init_uses_migration_007_binding_classifier() -> None:
    init_sql = postgres_schema.SCHEMA_PATH.read_text(encoding="utf-8")
    init_sql = init_sql.replace(f"{_BOUNDARY}\n", "")
    migration_sql = (
        postgres_schema.MIGRATIONS_PATH / "007_reliability_receipts.sql"
    ).read_text(encoding="utf-8")
    classifier = "CREATE OR REPLACE FUNCTION session_projects_classify_binding()"
    migration_control = migration_sql.split(classifier, 1)[1].split(
        "-- Backfill:", 1
    )[0]

    assert classifier + migration_control in init_sql


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
def test_postgres_bootstrap_preserves_complete_function_units(tmp_path: Path) -> None:
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
    assert create_index == drop_index + 1
    assert "DROP TRIGGER" not in init_queries[create_index]
    assert "CREATE TRIGGER" not in init_queries[drop_index]

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
