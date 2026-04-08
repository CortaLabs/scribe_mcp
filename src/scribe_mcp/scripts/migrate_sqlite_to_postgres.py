"""CLI tool to migrate Scribe data from SQLite into Postgres."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from scribe_mcp.config.settings import settings
from scribe_mcp.storage.postgres import PostgresStorage

_IGNORED_SQLITE_TABLES = {
    "sqlite_sequence",
    "scribe_migrations",
    "document_sections_fts",
    "document_sections_fts_config",
    "document_sections_fts_data",
    "document_sections_fts_docsize",
    "document_sections_fts_idx",
}
_PREFERRED_TABLE_ORDER = [
    "scribe_projects",
    "documents",
    "document_relationships",
    "global_log_entries",
    "dev_plans",
    "phases",
    "milestones",
    "checklists",
    "benchmarks",
    "performance_metrics",
    "scribe_sessions",
    "session_projects",
    "agent_sessions",
    "agent_projects",
    "agent_recent_projects",
    "agent_project_events",
    "scribe_entries",
    "scribe_metrics",
    "doc_changes",
    "document_sections",
    "custom_templates",
    "document_changes",
    "sync_status",
    "agent_report_cards",
    "reminder_history",
    "tool_calls",
    "scribe_bridges",
    "scribe_entries_archive",
]
_PROJECT_ID_FK_TABLES = {
    "scribe_entries",
    "scribe_metrics",
    "doc_changes",
    "document_sections",
    "custom_templates",
    "document_changes",
    "sync_status",
    "agent_report_cards",
    "dev_plans",
    "phases",
    "milestones",
    "benchmarks",
    "checklists",
    "performance_metrics",
}
_PROJECT_NAME_FK_TABLES = {
    "session_projects",
    "agent_projects",
    "agent_recent_projects",
}
_SESSION_ID_FK_TABLES = {
    "tool_calls",
    "reminder_history",
}


@dataclass(frozen=True)
class TableMigrationStats:
    table: str
    sqlite_rows: int
    postgres_rows: int
    skipped_rows: int = 0

    @property
    def matched(self) -> bool:
        return (self.sqlite_rows - self.skipped_rows) == self.postgres_rows


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _parse_table_list(raw_tables: str | None) -> set[str]:
    if not raw_tables:
        return set()
    return {part.strip() for part in raw_tables.split(",") if part.strip()}


def _discover_sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name;
        """
    ).fetchall()
    names = [str(row[0]) for row in rows if row and row[0]]
    return [name for name in names if name not in _IGNORED_SQLITE_TABLES]


def _ordered_tables(discovered: Sequence[str], requested: set[str]) -> list[str]:
    available = set(discovered)
    selected = available if not requested else available.intersection(requested)

    ordered = [name for name in _PREFERRED_TABLE_ORDER if name in selected]
    extras = sorted(name for name in selected if name not in ordered)
    return ordered + extras


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_ident(table)});").fetchall()
    return [str(row[1]) for row in rows if row and row[1]]


def _coerce_json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, bool, int, float)):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            return json.dumps(value)
    return json.dumps(str(value))


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
        if normalized in {"0", "false", "f", "no", "n"}:
            return False
    return bool(value)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(float(stripped))
            except ValueError:
                return None
    return None


def _coerce_timestamp(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        normalized = stripped.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(stripped, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
    return value


def _transform_value(value: Any, pg_udt_name: str) -> Any:
    udt = (pg_udt_name or "").lower()
    if udt in {"json", "jsonb"}:
        return _coerce_json_text(value)
    if udt == "bool":
        return _coerce_bool(value)
    if udt in {"float4", "float8", "numeric"}:
        return _coerce_float(value)
    if udt in {"int2", "int4", "int8"}:
        return _coerce_int(value)
    if udt.startswith("timestamp"):
        return _coerce_timestamp(value)
    return value


def _apply_special_column_fallback(
    *,
    table: str,
    column: str,
    row: sqlite3.Row,
    transformed: Any,
    pg_types: dict[str, str],
) -> Any:
    if table in _PROJECT_NAME_FK_TABLES and column == "project_name":
        raw = row[column]
        if raw is None:
            return None
        if isinstance(raw, str) and not raw.strip():
            return None
    if transformed is not None:
        return transformed
    if table != "scribe_entries":
        return transformed
    if column == "ts" and "ts_iso" in row.keys():
        return _transform_value(row["ts_iso"], pg_types[column])
    if column == "ts_iso" and "ts" in row.keys():
        return _transform_value(row["ts"], pg_types[column])
    return transformed


async def _postgres_column_types(
    conn: Any,
    *,
    schema_name: str,
    table: str,
    ) -> dict[str, str]:
    rows = await conn.fetch(
        """
        SELECT column_name, udt_name
        FROM information_schema.columns
        WHERE table_schema = $1
          AND table_name = $2
        ORDER BY ordinal_position;
        """,
        schema_name,
        table,
    )
    return {str(row["column_name"]): str(row["udt_name"]) for row in rows}


async def _discover_postgres_tables(
    conn: Any,
    *,
    schema_name: str,
) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = $1
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
        """,
        schema_name,
    )
    return [str(row["table_name"]) for row in rows if row and row["table_name"]]


def _sqlite_row_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {_quote_ident(table)};").fetchone()
    return int(row[0] if row else 0)


def _sqlite_project_ids(conn: sqlite3.Connection) -> set[int]:
    try:
        rows = conn.execute("SELECT id FROM scribe_projects;").fetchall()
    except sqlite3.Error:
        return set()
    project_ids: set[int] = set()
    for row in rows:
        value = _coerce_int(row[0] if row else None)
        if value is not None:
            project_ids.add(value)
    return project_ids


def _sqlite_project_names(conn: sqlite3.Connection) -> set[str]:
    try:
        rows = conn.execute("SELECT name FROM scribe_projects;").fetchall()
    except sqlite3.Error:
        return set()
    names: set[str] = set()
    for row in rows:
        value = row[0] if row else None
        if isinstance(value, str) and value.strip():
            names.add(value.strip())
    return names


def _sqlite_session_ids(conn: sqlite3.Connection) -> set[str]:
    try:
        rows = conn.execute("SELECT session_id FROM scribe_sessions;").fetchall()
    except sqlite3.Error:
        return set()
    session_ids: set[str] = set()
    for row in rows:
        value = row[0] if row else None
        if isinstance(value, str) and value.strip():
            session_ids.add(value.strip())
    return session_ids


def _sqlite_referenced_project_ids(conn: sqlite3.Connection) -> set[int]:
    values: set[int] = set()
    for table in sorted(_PROJECT_ID_FK_TABLES):
        try:
            rows = conn.execute(
                f"SELECT DISTINCT project_id FROM {_quote_ident(table)} WHERE project_id IS NOT NULL;"
            ).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            parsed = _coerce_int(row[0] if row else None)
            if parsed is not None:
                values.add(parsed)
    return values


def _sqlite_referenced_project_names(conn: sqlite3.Connection) -> set[str]:
    values: set[str] = set()
    for table in sorted(_PROJECT_NAME_FK_TABLES):
        try:
            rows = conn.execute(
                f"SELECT DISTINCT project_name FROM {_quote_ident(table)} WHERE project_name IS NOT NULL;"
            ).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            raw = row[0] if row else None
            if isinstance(raw, str) and raw.strip():
                values.add(raw.strip())
    return values


def _sqlite_referenced_session_ids(conn: sqlite3.Connection) -> set[str]:
    values: set[str] = set()
    for table in sorted(_SESSION_ID_FK_TABLES):
        try:
            rows = conn.execute(
                f"SELECT DISTINCT session_id FROM {_quote_ident(table)} WHERE session_id IS NOT NULL;"
            ).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            raw = row[0] if row else None
            if isinstance(raw, str) and raw.strip():
                values.add(raw.strip())
    return values


async def _ensure_placeholder_projects_by_id(
    conn: Any,
    *,
    schema_name: str,
    missing_project_ids: set[int],
) -> None:
    if not missing_project_ids:
        return
    schema_sql = _quote_ident(schema_name)
    for project_id in sorted(missing_project_ids):
        placeholder_name = f"__migrated_project_id_{project_id}"
        await conn.execute(
            f"""
            INSERT INTO {schema_sql}.scribe_projects (
                id,
                name,
                repo_root,
                progress_log_path,
                status,
                description
            )
            VALUES ($1, $2, '__migration_placeholder__', '__migration_placeholder__/PROGRESS_LOG.md', 'migrated_placeholder', 'Auto-generated placeholder project for migration FK integrity')
            ON CONFLICT (id) DO NOTHING;
            """,
            project_id,
            placeholder_name,
        )


async def _ensure_placeholder_projects_by_name(
    conn: Any,
    *,
    schema_name: str,
    missing_project_names: set[str],
) -> None:
    if not missing_project_names:
        return
    schema_sql = _quote_ident(schema_name)
    for project_name in sorted(missing_project_names):
        await conn.execute(
            f"""
            INSERT INTO {schema_sql}.scribe_projects (
                name,
                repo_root,
                progress_log_path,
                status,
                description
            )
            VALUES ($1, '__migration_placeholder__', '__migration_placeholder__/PROGRESS_LOG.md', 'migrated_placeholder', 'Auto-generated placeholder project for migration FK integrity')
            ON CONFLICT (name) DO NOTHING;
            """,
            project_name,
        )


async def _ensure_placeholder_sessions(
    conn: Any,
    *,
    schema_name: str,
    missing_session_ids: set[str],
) -> None:
    if not missing_session_ids:
        return
    schema_sql = _quote_ident(schema_name)
    for session_id in sorted(missing_session_ids):
        await conn.execute(
            f"""
            INSERT INTO {schema_sql}.scribe_sessions (
                session_id,
                transport_session_id,
                agent_id,
                repo_root,
                mode
            )
            VALUES ($1, $1, 'migration-placeholder', '__migration_placeholder__', 'sentinel')
            ON CONFLICT (session_id) DO NOTHING;
            """,
            session_id,
        )


async def _postgres_row_count(conn: Any, *, schema_name: str, table: str) -> int:
    value = await conn.fetchval(
        f"SELECT COUNT(*) FROM {_quote_ident(schema_name)}.{_quote_ident(table)};"
    )
    return int(value or 0)


async def _truncate_tables(conn: Any, *, schema_name: str, tables: Sequence[str]) -> None:
    if not tables:
        return
    qualified = ", ".join(
        f"{_quote_ident(schema_name)}.{_quote_ident(table)}" for table in tables
    )
    await conn.execute(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE;")


async def _reset_serial_sequences(
    conn: Any,
    *,
    schema_name: str,
    tables: Sequence[str],
) -> None:
    if not tables:
        return
    rows = await conn.fetch(
        """
        SELECT
            c.table_name,
            c.column_name,
            pg_get_serial_sequence(
                format('%I.%I', c.table_schema, c.table_name),
                c.column_name
            ) AS sequence_name
        FROM information_schema.columns c
        WHERE c.table_schema = $1
          AND c.table_name = ANY($2::text[])
          AND c.column_default LIKE 'nextval(%'
        ORDER BY c.table_name, c.column_name;
        """,
        schema_name,
        list(tables),
    )
    for row in rows:
        sequence_name = row["sequence_name"]
        if not sequence_name:
            continue
        table = str(row["table_name"])
        column = str(row["column_name"])
        max_value = await conn.fetchval(
            f"SELECT COALESCE(MAX({_quote_ident(column)}), 0) "
            f"FROM {_quote_ident(schema_name)}.{_quote_ident(table)};"
        )
        await conn.execute(
            "SELECT setval($1::regclass, $2, false);",
            str(sequence_name),
            int(max_value or 0) + 1,
        )


async def _copy_table(
    *,
    sqlite_conn: sqlite3.Connection,
    pg_conn: Any,
    schema_name: str,
    table: str,
    batch_size: int,
    valid_project_ids: set[int] | None = None,
    valid_project_names: set[str] | None = None,
    valid_session_ids: set[str] | None = None,
) -> tuple[int, int]:
    sqlite_columns = _sqlite_columns(sqlite_conn, table)
    if not sqlite_columns:
        return 0, 0

    pg_types = await _postgres_column_types(pg_conn, schema_name=schema_name, table=table)
    common_columns = [column for column in sqlite_columns if column in pg_types]
    if not common_columns:
        return 0, 0

    selected_columns_sql = ", ".join(_quote_ident(column) for column in common_columns)
    cursor = sqlite_conn.execute(
        f"SELECT {selected_columns_sql} FROM {_quote_ident(table)};"
    )

    copied = 0
    skipped_orphan_rows = 0
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break

        records: list[tuple[Any, ...]] = []
        for row in rows:
            if valid_project_ids is not None and table in _PROJECT_ID_FK_TABLES and "project_id" in common_columns:
                project_id = _coerce_int(row["project_id"])
                if project_id is not None and project_id not in valid_project_ids:
                    skipped_orphan_rows += 1
                    continue
            if valid_project_names is not None and table in _PROJECT_NAME_FK_TABLES and "project_name" in common_columns:
                project_name = str(row["project_name"]).strip() if row["project_name"] is not None else ""
                if project_name and project_name not in valid_project_names:
                    skipped_orphan_rows += 1
                    continue
            if valid_session_ids is not None and table in _SESSION_ID_FK_TABLES and "session_id" in common_columns:
                session_id = str(row["session_id"]).strip() if row["session_id"] is not None else ""
                if not session_id or session_id not in valid_session_ids:
                    skipped_orphan_rows += 1
                    continue
            values: list[Any] = []
            for column in common_columns:
                transformed = _transform_value(row[column], pg_types[column])
                transformed = _apply_special_column_fallback(
                    table=table,
                    column=column,
                    row=row,
                    transformed=transformed,
                    pg_types=pg_types,
                )
                values.append(transformed)
            records.append(tuple(values))

        if not records:
            continue
        await pg_conn.copy_records_to_table(
            table_name=table,
            schema_name=schema_name,
            columns=common_columns,
            records=records,
        )
        copied += len(records)

    return copied, skipped_orphan_rows


async def _migrate(args: argparse.Namespace) -> int:
    sqlite_path = Path(args.sqlite_path).expanduser()
    if not sqlite_path.exists():
        print(f"error: sqlite path does not exist: {sqlite_path}", file=sys.stderr)
        return 2

    postgres_dsn = args.postgres_dsn or settings.db_url
    if not postgres_dsn:
        print("error: --postgres-dsn is required when SCRIBE_DB_URL is not set", file=sys.stderr)
        return 2

    schema_name = args.schema_name or settings.postgres_schema
    requested_tables = _parse_table_list(args.tables)
    mode = args.mode
    batch_size = max(100, int(args.batch_size))

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row
    valid_project_ids = _sqlite_project_ids(sqlite_conn)
    valid_project_names = _sqlite_project_names(sqlite_conn)
    valid_session_ids = _sqlite_session_ids(sqlite_conn)
    referenced_project_ids = _sqlite_referenced_project_ids(sqlite_conn)
    referenced_project_names = _sqlite_referenced_project_names(sqlite_conn)
    referenced_session_ids = _sqlite_referenced_session_ids(sqlite_conn)

    missing_project_ids = referenced_project_ids - valid_project_ids
    missing_project_names = referenced_project_names - valid_project_names
    missing_session_ids = referenced_session_ids - valid_session_ids

    storage = PostgresStorage(
        postgres_dsn,
        schema_name=schema_name,
        pool_min_size=settings.postgres_pool_min_size,
        pool_max_size=settings.postgres_pool_max_size,
        command_timeout_seconds=settings.postgres_command_timeout_seconds,
        connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
        max_inactive_connection_lifetime_seconds=settings.postgres_max_inactive_connection_lifetime_seconds,
        connect_retries=settings.postgres_connect_retries,
        connect_retry_backoff_seconds=settings.postgres_connect_retry_backoff_seconds,
    )

    try:
        await storage.setup()
        pool = await storage._ensure_pool()  # noqa: SLF001 - migration utility
        stats: list[TableMigrationStats] = []
        skipped_missing_in_postgres: list[str] = []
        async with pool.acquire() as pg_conn:
            available_tables = _discover_sqlite_tables(sqlite_conn)
            requested = _ordered_tables(available_tables, requested_tables)
            postgres_tables = set(
                await _discover_postgres_tables(
                    pg_conn,
                    schema_name=schema_name,
                )
            )
            tables = [table for table in requested if table in postgres_tables]
            skipped_missing_in_postgres = [table for table in requested if table not in postgres_tables]

            if not tables:
                print("No matching SQLite tables found to migrate.")
                return 0

            if mode == "replace":
                await _truncate_tables(pg_conn, schema_name=schema_name, tables=tables)

            for table in tables:
                sqlite_rows = _sqlite_row_count(sqlite_conn, table)
                _copied_rows, skipped_rows = await _copy_table(
                    sqlite_conn=sqlite_conn,
                    pg_conn=pg_conn,
                    schema_name=schema_name,
                    table=table,
                    batch_size=batch_size,
                    valid_project_ids=valid_project_ids,
                    valid_project_names=valid_project_names,
                    valid_session_ids=valid_session_ids,
                )
                postgres_rows = await _postgres_row_count(
                    pg_conn,
                    schema_name=schema_name,
                    table=table,
                )
                stats.append(
                    TableMigrationStats(
                        table=table,
                        sqlite_rows=sqlite_rows,
                        postgres_rows=postgres_rows,
                        skipped_rows=skipped_rows,
                    )
                )
                if table == "scribe_projects":
                    await _ensure_placeholder_projects_by_id(
                        pg_conn,
                        schema_name=schema_name,
                        missing_project_ids=missing_project_ids,
                    )
                    await _ensure_placeholder_projects_by_name(
                        pg_conn,
                        schema_name=schema_name,
                        missing_project_names=missing_project_names,
                    )
                    valid_project_ids |= missing_project_ids
                    valid_project_names |= missing_project_names
                if table == "scribe_sessions":
                    await _ensure_placeholder_sessions(
                        pg_conn,
                        schema_name=schema_name,
                        missing_session_ids=missing_session_ids,
                    )
                    valid_session_ids |= missing_session_ids
            await _reset_serial_sequences(
                pg_conn,
                schema_name=schema_name,
                tables=tables,
            )

        mismatches = [item for item in stats if not item.matched]
        print(f"SQLite source: {sqlite_path}")
        print(f"Postgres target schema: {schema_name}")
        print(f"Mode: {mode}")
        if skipped_missing_in_postgres:
            print(f"Skipped tables missing in Postgres schema: {', '.join(skipped_missing_in_postgres)}")
        print("")
        for item in stats:
            status = "OK" if item.matched else "MISMATCH"
            suffix = f" skipped={item.skipped_rows:<6}" if item.skipped_rows else ""
            print(
                f"{status:8} {item.table:26} sqlite={item.sqlite_rows:<8} postgres={item.postgres_rows:<8}{suffix}"
            )

        print("")
        print(f"tables_migrated={len(stats)}")
        print(f"mismatches={len(mismatches)}")

        if mismatches:
            return 1
        return 0
    finally:
        sqlite_conn.close()
        await storage.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate Scribe data from SQLite to Postgres schema.",
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(settings.sqlite_path),
        help="Path to source SQLite DB (default from SCRIBE_DB_PATH).",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=settings.db_url,
        help="Target Postgres DSN (default from SCRIBE_DB_URL).",
    )
    parser.add_argument(
        "--schema-name",
        default=settings.postgres_schema,
        help="Target Postgres schema (default from SCRIBE_POSTGRES_SCHEMA).",
    )
    parser.add_argument(
        "--mode",
        choices=("replace", "append"),
        default="replace",
        help="replace=truncate target tables first; append=copy without truncating.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Rows per copy batch (default: 2000).",
    )
    parser.add_argument(
        "--tables",
        default="",
        help="Optional comma-separated table subset.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_migrate(args))


if __name__ == "__main__":
    raise SystemExit(main())
