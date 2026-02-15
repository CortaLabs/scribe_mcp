"""Schema-scoped Postgres backup utility with retention pruning."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from scribe_mcp.config.settings import settings


@dataclass(frozen=True)
class BackupFile:
    path: Path
    timestamp_utc: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _redact_dsn(dsn: str) -> str:
    parts = urlsplit(dsn)
    if not parts.netloc:
        return dsn
    if "@" not in parts.netloc:
        return dsn
    userinfo, hostinfo = parts.netloc.rsplit("@", 1)
    username = userinfo.split(":", 1)[0]
    safe_netloc = f"{username}:***@{hostinfo}"
    return urlunsplit((parts.scheme, safe_netloc, parts.path, parts.query, parts.fragment))


def _backup_filename(*, schema: str, now: datetime | None = None) -> str:
    ts = (now or _utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return f"scribe_{schema}_{ts}.dump"


def _parse_backup_timestamp(path: Path) -> datetime | None:
    stem = path.stem
    parts = stem.rsplit("_", 1)
    if len(parts) != 2:
        return None
    raw_ts = parts[1]
    try:
        return datetime.strptime(raw_ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _discover_backups(output_dir: Path, schema: str) -> list[BackupFile]:
    pattern = f"scribe_{schema}_*.dump"
    backups: list[BackupFile] = []
    for path in output_dir.glob(pattern):
        if not path.is_file():
            continue
        ts = _parse_backup_timestamp(path)
        if ts is None:
            continue
        backups.append(BackupFile(path=path, timestamp_utc=ts))
    backups.sort(key=lambda item: item.timestamp_utc, reverse=True)
    return backups


def _select_retained_backups(
    backups: Iterable[BackupFile],
    *,
    keep_daily: int,
    keep_weekly: int,
) -> set[Path]:
    selected: set[Path] = set()
    seen_days: set[str] = set()
    seen_weeks: set[tuple[int, int]] = set()

    for item in backups:
        day_key = item.timestamp_utc.strftime("%Y-%m-%d")
        if len(seen_days) < keep_daily and day_key not in seen_days:
            selected.add(item.path)
            seen_days.add(day_key)

        iso_year, iso_week, _ = item.timestamp_utc.isocalendar()
        week_key = (iso_year, iso_week)
        if len(seen_weeks) < keep_weekly and week_key not in seen_weeks:
            selected.add(item.path)
            seen_weeks.add(week_key)

        if len(seen_days) >= keep_daily and len(seen_weeks) >= keep_weekly:
            break

    return selected


def _run_pg_dump(*, dsn: str, schema: str, destination: Path, dry_run: bool) -> list[str]:
    command = [
        "pg_dump",
        "--format=custom",
        f"--schema={schema}",
        f"--file={destination}",
        f"--dbname={dsn}",
    ]
    if dry_run:
        return command

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(f"pg_dump failed ({completed.returncode}): {stderr}")
    return command


def _write_manifest(
    *,
    output_dir: Path,
    backup_path: Path,
    schema: str,
    dsn: str,
    command: list[str],
    pruned_files: list[str],
    dry_run: bool,
) -> None:
    manifest = {
        "created_at_utc": _utc_now().isoformat(),
        "schema": schema,
        "dsn": _redact_dsn(dsn),
        "backup_file": str(backup_path),
        "pg_dump_command": command,
        "pruned_files": pruned_files,
        "dry_run": dry_run,
    }
    manifest_path = output_dir / "latest_backup_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create schema-scoped Postgres backup and enforce retention.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=settings.db_url,
        help="Postgres DSN (default from SCRIBE_DB_URL).",
    )
    parser.add_argument(
        "--schema",
        default=settings.postgres_schema,
        help="Schema to backup (default from SCRIBE_POSTGRES_SCHEMA).",
    )
    parser.add_argument(
        "--output-dir",
        default=".scribe/backups/postgres",
        help="Backup output directory (default: .scribe/backups/postgres).",
    )
    parser.add_argument(
        "--keep-daily",
        type=int,
        default=7,
        help="Number of distinct daily backups to keep (default: 7).",
    )
    parser.add_argument(
        "--keep-weekly",
        type=int,
        default=4,
        help="Number of distinct ISO weeks to keep (default: 4).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without running pg_dump or deleting files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    dsn = args.postgres_dsn
    if not dsn:
        print("error: --postgres-dsn is required when SCRIBE_DB_URL is not set", file=sys.stderr)
        return 2

    schema = (args.schema or "scribe").strip() or "scribe"
    keep_daily = max(0, int(args.keep_daily))
    keep_weekly = max(0, int(args.keep_weekly))
    dry_run = bool(args.dry_run)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    backup_path = output_dir / _backup_filename(schema=schema)
    try:
        command = _run_pg_dump(dsn=dsn, schema=schema, destination=backup_path, dry_run=dry_run)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    backups = _discover_backups(output_dir, schema)
    retained = _select_retained_backups(backups, keep_daily=keep_daily, keep_weekly=keep_weekly)
    pruned_files: list[str] = []
    for item in backups:
        if item.path in retained:
            continue
        pruned_files.append(str(item.path))
        if not dry_run:
            item.path.unlink(missing_ok=True)

    _write_manifest(
        output_dir=output_dir,
        backup_path=backup_path,
        schema=schema,
        dsn=dsn,
        command=command,
        pruned_files=pruned_files,
        dry_run=dry_run,
    )

    print(f"schema={schema}")
    print(f"backup_file={backup_path}")
    print(f"dry_run={dry_run}")
    print(f"pruned={len(pruned_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

