from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from scribe_mcp.scripts.migrate_sqlite_to_postgres import (
    _IGNORED_SQLITE_TABLES,
    _apply_special_column_fallback,
    _coerce_float,
    _coerce_int,
    _coerce_timestamp,
    _discover_postgres_tables,
    _ensure_placeholder_projects_by_id,
    _ensure_placeholder_projects_by_name,
    _ensure_placeholder_sessions,
    _ordered_tables,
    _reset_serial_sequences,
    _sqlite_project_ids,
    _sqlite_project_names,
    _sqlite_referenced_project_ids,
    _sqlite_referenced_project_names,
    _sqlite_referenced_session_ids,
    _sqlite_session_ids,
    TableMigrationStats,
)


def test_ignored_sqlite_tables_include_fts_shadow_tables() -> None:
    assert "document_sections_fts" in _IGNORED_SQLITE_TABLES
    assert "document_sections_fts_config" in _IGNORED_SQLITE_TABLES
    assert "document_sections_fts_data" in _IGNORED_SQLITE_TABLES
    assert "document_sections_fts_docsize" in _IGNORED_SQLITE_TABLES
    assert "document_sections_fts_idx" in _IGNORED_SQLITE_TABLES


def test_ordered_tables_prioritizes_legacy_document_tables() -> None:
    discovered = [
        "global_log_entries",
        "scribe_entries",
        "documents",
        "document_relationships",
        "scribe_projects",
    ]

    ordered = _ordered_tables(discovered, requested=set())

    assert ordered[:4] == [
        "scribe_projects",
        "documents",
        "document_relationships",
        "global_log_entries",
    ]
    assert ordered[-1] == "scribe_entries"


@pytest.mark.asyncio
async def test_discover_postgres_tables_returns_base_tables_only() -> None:
    class _FakeConn:
        async def fetch(self, _query: str, _schema_name: str):
            return [
                {"table_name": "scribe_projects"},
                {"table_name": "documents"},
                {"table_name": "global_log_entries"},
            ]

    tables = await _discover_postgres_tables(_FakeConn(), schema_name="scribe")
    assert tables == ["scribe_projects", "documents", "global_log_entries"]


def test_coerce_timestamp_parses_common_sqlite_formats() -> None:
    iso = _coerce_timestamp("2026-02-15T07:30:00Z")
    assert isinstance(iso, datetime)
    assert iso.tzinfo is not None

    spaced = _coerce_timestamp("2026-02-15 07:30:00")
    assert isinstance(spaced, datetime)
    assert spaced.tzinfo == timezone.utc


def test_coerce_timestamp_normalizes_naive_datetime() -> None:
    naive = datetime(2026, 2, 15, 7, 30, 0)
    parsed = _coerce_timestamp(naive)
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo == timezone.utc


def test_numeric_coercion_handles_string_values() -> None:
    assert _coerce_float("0.85") == pytest.approx(0.85)
    assert _coerce_float("  ") is None
    assert _coerce_int("42") == 42
    assert _coerce_int("42.0") == 42
    assert _coerce_int("bad") is None


def test_special_fallback_uses_ts_iso_when_ts_missing() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT NULL AS ts, '2026-02-15 07:30:00' AS ts_iso").fetchone()
    assert row is not None

    value = _apply_special_column_fallback(
        table="scribe_entries",
        column="ts",
        row=row,
        transformed=None,
        pg_types={"ts": "timestamptz", "ts_iso": "timestamptz"},
    )
    conn.close()

    assert isinstance(value, datetime)
    assert value.tzinfo == timezone.utc


def test_special_fallback_normalizes_blank_project_name_to_null() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT '' AS project_name").fetchone()
    assert row is not None

    value = _apply_special_column_fallback(
        table="session_projects",
        column="project_name",
        row=row,
        transformed="",
        pg_types={"project_name": "text"},
    )
    conn.close()

    assert value is None


@pytest.mark.asyncio
async def test_reset_serial_sequences_advances_to_max_plus_one() -> None:
    class _FakeConn:
        def __init__(self) -> None:
            self.setval_calls: list[tuple[str, int]] = []

        async def fetch(self, _query: str, _schema: str, _tables: list[str]):
            return [
                {
                    "table_name": "scribe_projects",
                    "column_name": "id",
                    "sequence_name": "scribe.scribe_projects_id_seq",
                }
            ]

        async def fetchval(self, _query: str):
            return 41

        async def execute(self, _query: str, sequence_name: str, next_value: int):
            self.setval_calls.append((sequence_name, next_value))

    conn = _FakeConn()
    await _reset_serial_sequences(
        conn,
        schema_name="scribe",
        tables=["scribe_projects"],
    )
    assert conn.setval_calls == [("scribe.scribe_projects_id_seq", 42)]


def test_sqlite_project_ids_ignores_non_numeric_values() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE scribe_projects (id TEXT)")
    conn.execute("INSERT INTO scribe_projects (id) VALUES ('1'), ('2'), ('bad'), (NULL)")
    conn.commit()

    ids = _sqlite_project_ids(conn)
    conn.close()

    assert ids == {1, 2}


def test_sqlite_name_and_session_extractors_ignore_empty_values() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE scribe_projects (name TEXT)")
    conn.execute("INSERT INTO scribe_projects (name) VALUES ('alpha'), (''), (NULL)")
    conn.execute("CREATE TABLE scribe_sessions (session_id TEXT)")
    conn.execute("INSERT INTO scribe_sessions (session_id) VALUES ('sess-1'), (' '), (NULL)")
    conn.commit()

    names = _sqlite_project_names(conn)
    session_ids = _sqlite_session_ids(conn)
    conn.close()

    assert names == {"alpha"}
    assert session_ids == {"sess-1"}


def test_sqlite_referenced_extractors_collect_fk_domain_values() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE doc_changes (project_id INTEGER)")
    conn.execute("INSERT INTO doc_changes (project_id) VALUES (1), (2), (NULL)")
    conn.execute("CREATE TABLE agent_projects (project_name TEXT)")
    conn.execute("INSERT INTO agent_projects (project_name) VALUES ('alpha'), (NULL), ('')")
    conn.execute("CREATE TABLE tool_calls (session_id TEXT)")
    conn.execute("INSERT INTO tool_calls (session_id) VALUES ('sess-1'), (''), (NULL)")
    conn.commit()

    ref_ids = _sqlite_referenced_project_ids(conn)
    ref_names = _sqlite_referenced_project_names(conn)
    ref_sessions = _sqlite_referenced_session_ids(conn)
    conn.close()

    assert ref_ids == {1, 2}
    assert ref_names == {"alpha"}
    assert ref_sessions == {"sess-1"}


def test_table_migration_stats_match_accounts_for_skipped_rows() -> None:
    stats = TableMigrationStats(
        table="doc_changes",
        sqlite_rows=10,
        postgres_rows=9,
        skipped_rows=1,
    )
    assert stats.matched is True


@pytest.mark.asyncio
async def test_placeholder_parent_helpers_emit_insert_statements() -> None:
    class _FakeConn:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        async def execute(self, query: str, *args: object):
            self.calls.append((query, args))

    conn = _FakeConn()
    await _ensure_placeholder_projects_by_id(conn, schema_name="scribe", missing_project_ids={9})
    await _ensure_placeholder_projects_by_name(conn, schema_name="scribe", missing_project_names={"proj-missing"})
    await _ensure_placeholder_sessions(conn, schema_name="scribe", missing_session_ids={"sess-missing"})

    assert len(conn.calls) == 3
    assert "INSERT INTO \"scribe\".scribe_projects" in conn.calls[0][0]
    assert "INSERT INTO \"scribe\".scribe_projects" in conn.calls[1][0]
    assert "INSERT INTO \"scribe\".scribe_sessions" in conn.calls[2][0]
