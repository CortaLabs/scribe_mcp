"""Schema-scoped Postgres backup utility with retention pruning."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from scribe_mcp.config.settings import settings
from scribe_mcp.shared.write_barrier import WriteBarrierError, assert_writes_allowed


@dataclass(frozen=True)
class BackupFile:
    path: Path
    timestamp_utc: datetime


class PgDumpError(RuntimeError):
    def __init__(self, returncode: int):
        super().__init__("pg_dump failed")
        self.returncode = returncode


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _redact_dsn(dsn: str) -> str:
    parts = urlsplit(dsn)
    if not parts.netloc:
        if "@" in dsn:
            userinfo, target = dsn.rsplit("@", 1)
            if ":" in userinfo:
                username = userinfo.split(":", 1)[0]
                return f"{username}:***@{target}"
        return dsn
    if "@" not in parts.netloc:
        return dsn
    userinfo, hostinfo = parts.netloc.rsplit("@", 1)
    username = userinfo.split(":", 1)[0]
    safe_netloc = f"{username}:***@{hostinfo}"
    return urlunsplit((parts.scheme, safe_netloc, parts.path, parts.query, parts.fragment))


def _sanitize_command(command: Iterable[str]) -> list[str]:
    sanitized: list[str] = []
    for arg in command:
        if arg.startswith("--dbname="):
            _, dsn = arg.split("=", 1)
            sanitized.append(f"--dbname={_redact_dsn(dsn)}")
            continue
        sanitized.append(arg)
    return sanitized


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
        raise PgDumpError(completed.returncode)
    return command


def _is_owner_only_dir(path: Path) -> bool:
    mode = stat.S_IMODE(path.stat().st_mode)
    return mode == 0o700


def _is_under_managed_docs(path: Path) -> bool:
    parts = path.resolve().parts
    return any(
        parts[index] == ".scribe" and index + 1 < len(parts) and parts[index + 1] == "docs"
        for index in range(len(parts))
    )


def _prepare_output_dir(output_dir: Path) -> bool:
    if _is_under_managed_docs(output_dir):
        print("output_status=rejected_managed_docs", file=sys.stderr)
        return False

    if output_dir.exists():
        if not output_dir.is_dir():
            print("output_status=rejected_not_directory", file=sys.stderr)
            return False
        if not _is_owner_only_dir(output_dir):
            print("output_status=rejected_permissions", file=sys.stderr)
            return False
        return True

    output_dir.mkdir(parents=True, mode=0o700)
    output_dir.chmod(0o700)
    if not _is_owner_only_dir(output_dir):
        print("output_status=rejected_permissions", file=sys.stderr)
        return False
    return True


def _barrier_root_for_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = resolved.parts
    if ".scribe" in parts:
        index = parts.index(".scribe")
        if index > 0:
            return Path(*parts[:index])
    return resolved.parent


def _secure_existing_private_file(path: Path) -> bool:
    if not path.is_file():
        print("dump_status=missing", file=sys.stderr)
        return False
    path.chmod(0o600)
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        print("dump_status=permission_verification_failed", file=sys.stderr)
        return False
    return True


def _write_private_text_atomic(path: Path, content: str) -> None:
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        path.chmod(0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        tmp_path.unlink(missing_ok=True)
        raise


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
        "pg_dump_command": _sanitize_command(command),
        "pruned_files": pruned_files,
        "dry_run": dry_run,
    }
    manifest_path = output_dir / "latest_backup_manifest.json"
    _write_private_text_atomic(manifest_path, json.dumps(manifest, indent=2) + "\n")


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
        print("dsn_status=missing", file=sys.stderr)
        return 2

    schema = (args.schema or "scribe").strip() or "scribe"
    keep_daily = max(0, int(args.keep_daily))
    keep_weekly = max(0, int(args.keep_weekly))
    dry_run = bool(args.dry_run)

    output_dir = Path(args.output_dir).expanduser().resolve()
    try:
        assert_writes_allowed(_barrier_root_for_path(output_dir), operation_label="postgres_backup")
    except WriteBarrierError:
        print("write_barrier_status=blocked", file=sys.stderr)
        return 1
    if not _prepare_output_dir(output_dir):
        return 1

    backup_path = output_dir / _backup_filename(schema=schema)
    try:
        command = _run_pg_dump(dsn=dsn, schema=schema, destination=backup_path, dry_run=dry_run)
    except PgDumpError as exc:
        print("pg_dump_status=failed", file=sys.stderr)
        print(f"return_code={exc.returncode}", file=sys.stderr)
        return 1

    if not dry_run and not _secure_existing_private_file(backup_path):
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

    print("backup_status=success")
    print(f"dump_status={'skipped' if dry_run else 'created'}")
    print("manifest_status=written")
    print(f"dry_run={'true' if dry_run else 'false'}")
    print(f"pruned_count={len(pruned_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
