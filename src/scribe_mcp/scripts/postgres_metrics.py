"""Collect Postgres operational metrics for Scribe schema."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import asyncpg

from scribe_mcp.config.settings import settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect table/index and database metrics for Scribe Postgres schema.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=settings.db_url,
        help="Postgres DSN (default from SCRIBE_DB_URL).",
    )
    parser.add_argument(
        "--schema-name",
        default=settings.postgres_schema,
        help="Schema to inspect (default from SCRIBE_POSTGRES_SCHEMA).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full JSON payload.",
    )
    parser.add_argument(
        "--top-tables",
        type=int,
        default=15,
        help="Number of largest tables to print in text mode (default: 15).",
    )
    return parser


async def _collect_metrics(dsn: str, schema_name: str) -> dict[str, Any]:
    conn = await asyncpg.connect(dsn)
    try:
        db_stats = await conn.fetchrow(
            """
            SELECT
                datname,
                numbackends,
                xact_commit,
                xact_rollback,
                blks_read,
                blks_hit,
                tup_returned,
                tup_fetched,
                tup_inserted,
                tup_updated,
                tup_deleted
            FROM pg_stat_database
            WHERE datname = current_database();
            """
        )

        table_stats = await conn.fetch(
            """
            SELECT
                c.relname AS table_name,
                pg_total_relation_size(c.oid) AS total_bytes,
                pg_relation_size(c.oid) AS table_bytes,
                pg_indexes_size(c.oid) AS index_bytes,
                COALESCE(s.n_live_tup, 0) AS live_rows,
                COALESCE(s.seq_scan, 0) AS seq_scan,
                COALESCE(s.idx_scan, 0) AS idx_scan
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
            WHERE n.nspname = $1
              AND c.relkind = 'r'
            ORDER BY pg_total_relation_size(c.oid) DESC;
            """,
            schema_name,
        )

        index_stats = await conn.fetch(
            """
            SELECT
                schemaname,
                relname AS table_name,
                indexrelname AS index_name,
                idx_scan,
                idx_tup_read,
                idx_tup_fetch
            FROM pg_stat_user_indexes
            WHERE schemaname = $1
            ORDER BY idx_scan DESC, indexrelname;
            """,
            schema_name,
        )

        connection_stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE state = 'active') AS active,
                COUNT(*) FILTER (WHERE state = 'idle') AS idle,
                COUNT(*) AS total
            FROM pg_stat_activity
            WHERE datname = current_database();
            """
        )
    finally:
        await conn.close()

    payload = {
        "schema": schema_name,
        "database": dict(db_stats) if db_stats is not None else {},
        "connections": dict(connection_stats) if connection_stats is not None else {},
        "tables": [dict(row) for row in table_stats],
        "indexes": [dict(row) for row in index_stats],
    }

    db = payload["database"]
    blks_read = float(db.get("blks_read") or 0.0)
    blks_hit = float(db.get("blks_hit") or 0.0)
    if (blks_hit + blks_read) > 0:
        payload["cache_hit_ratio"] = blks_hit / (blks_hit + blks_read)
    else:
        payload["cache_hit_ratio"] = None
    return payload


def _render_text(payload: dict[str, Any], top_tables: int) -> str:
    lines: list[str] = []
    db = payload.get("database", {})
    conns = payload.get("connections", {})
    cache_hit_ratio = payload.get("cache_hit_ratio")

    lines.append(f"schema={payload.get('schema')}")
    lines.append(f"database={db.get('datname')}")
    lines.append(
        "connections="
        f"total:{conns.get('total', 0)} active:{conns.get('active', 0)} idle:{conns.get('idle', 0)}"
    )
    if cache_hit_ratio is None:
        lines.append("cache_hit_ratio=unknown")
    else:
        lines.append(f"cache_hit_ratio={cache_hit_ratio:.4f}")
    lines.append("")
    lines.append("Top tables by total size:")

    tables = payload.get("tables", [])[: max(1, int(top_tables))]
    for row in tables:
        total_mb = float(row.get("total_bytes") or 0.0) / (1024 * 1024)
        table_mb = float(row.get("table_bytes") or 0.0) / (1024 * 1024)
        index_mb = float(row.get("index_bytes") or 0.0) / (1024 * 1024)
        seq_scan = int(row.get("seq_scan") or 0)
        idx_scan = int(row.get("idx_scan") or 0)
        lines.append(
            f"{row.get('table_name'):26} "
            f"total_mb={total_mb:9.2f} table_mb={table_mb:9.2f} index_mb={index_mb:9.2f} "
            f"rows={int(row.get('live_rows') or 0):10d} seq_scan={seq_scan:8d} idx_scan={idx_scan:8d}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    dsn = args.postgres_dsn
    if not dsn:
        print("error: --postgres-dsn is required when SCRIBE_DB_URL is not set", file=sys.stderr)
        return 2

    payload = asyncio.run(_collect_metrics(dsn, args.schema_name or settings.postgres_schema))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_text(payload, top_tables=args.top_tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
