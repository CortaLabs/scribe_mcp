"""Run append/read/query soak workload against Postgres storage backend."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import time
import uuid
from datetime import datetime, timezone

from scribe_mcp.config.settings import settings
from scribe_mcp.storage.postgres import PostgresStorage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run sustained Postgres append/read/query workload for soak validation.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=settings.db_url,
        help="Postgres DSN (default from SCRIBE_DB_URL).",
    )
    parser.add_argument(
        "--schema-name",
        default=settings.postgres_schema,
        help="Postgres schema name (default from SCRIBE_POSTGRES_SCHEMA).",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=300,
        help="How long to run the workload (default: 300s).",
    )
    parser.add_argument(
        "--write-interval-ms",
        type=int,
        default=100,
        help="Delay between append operations (default: 100ms).",
    )
    parser.add_argument(
        "--read-recent-every",
        type=int,
        default=10,
        help="Run read_recent every N writes (default: 10).",
    )
    parser.add_argument(
        "--query-every",
        type=int,
        default=20,
        help="Run query_entries every N writes (default: 20).",
    )
    parser.add_argument(
        "--project-name",
        default="",
        help="Optional fixed project name. Defaults to generated `postgres_soak_<ts>`.",
    )
    parser.add_argument(
        "--cleanup-project",
        action="store_true",
        help="Delete soak project at the end.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    dsn = args.postgres_dsn
    if not dsn:
        print("error: --postgres-dsn is required when SCRIBE_DB_URL is not set", file=sys.stderr)
        return 2

    duration_seconds = max(1, int(args.duration_seconds))
    write_interval = max(0.0, int(args.write_interval_ms) / 1000.0)
    read_recent_every = max(1, int(args.read_recent_every))
    query_every = max(1, int(args.query_every))

    storage = PostgresStorage(
        dsn,
        schema_name=args.schema_name or settings.postgres_schema,
        pool_min_size=settings.postgres_pool_min_size,
        pool_max_size=settings.postgres_pool_max_size,
        command_timeout_seconds=settings.postgres_command_timeout_seconds,
        connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
        max_inactive_connection_lifetime_seconds=settings.postgres_max_inactive_connection_lifetime_seconds,
        connect_retries=settings.postgres_connect_retries,
        connect_retry_backoff_seconds=settings.postgres_connect_retry_backoff_seconds,
    )

    project_name = args.project_name.strip()
    if not project_name:
        project_name = f"postgres_soak_{_utcnow().strftime('%Y%m%d_%H%M%S')}"

    writes = 0
    reads_recent = 0
    queries = 0
    errors = 0
    started = time.monotonic()
    deadline = started + duration_seconds
    project = None

    try:
        await storage.setup()
        project = await storage.upsert_project(
            name=project_name,
            repo_root=str(settings.project_root),
            progress_log_path=str(settings.project_root / ".scribe" / "SOAK_PROGRESS_LOG.md"),
            docs_json=None,
        )

        while time.monotonic() < deadline:
            idx = writes + 1
            now = _utcnow()
            message = f"postgres soak entry {idx}"
            raw_line = (
                f"[ℹ️] [{now.isoformat()}] [Agent: soak] [Project: {project.name}] {message}"
            )
            try:
                await storage.insert_entry(
                    entry_id=f"soak-{uuid.uuid4().hex}",
                    project=project,
                    ts=now,
                    emoji="ℹ️",
                    agent="soak",
                    message=message,
                    meta={"soak": True, "index": idx},
                    raw_line=raw_line,
                    sha256=hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
                    priority="medium",
                    category="soak",
                    log_type="progress",
                )
                writes += 1
            except Exception:
                errors += 1

            if writes and writes % read_recent_every == 0:
                try:
                    await storage.fetch_recent_entries(project=project, limit=50)
                    reads_recent += 1
                except Exception:
                    errors += 1

            if writes and writes % query_every == 0:
                try:
                    await storage.query_entries(
                        project=project,
                        limit=25,
                        message="postgres soak entry",
                        message_mode="substring",
                    )
                    queries += 1
                except Exception:
                    errors += 1

            if write_interval:
                await asyncio.sleep(write_interval)

        persisted = await storage.count_entries(project=project)
        drift = persisted - writes

        print(f"project={project.name}")
        print(f"duration_seconds={duration_seconds}")
        print(f"writes={writes}")
        print(f"reads_recent={reads_recent}")
        print(f"queries={queries}")
        print(f"errors={errors}")
        print(f"persisted_entries={persisted}")
        print(f"drift={drift}")

        if errors:
            return 1
        if persisted < writes:
            return 1
        return 0
    finally:
        if args.cleanup_project and project is not None:
            try:
                await storage.delete_project(project.name)
            except Exception:
                pass
        await storage.close()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
