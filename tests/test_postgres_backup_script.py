from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scribe_mcp.scripts.postgres_backup import (
    BackupFile,
    _backup_filename,
    _redact_dsn,
    _select_retained_backups,
)


def _dt(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def test_redact_dsn_hides_password() -> None:
    dsn = "postgresql://scribe:secret@127.0.0.1:5432/scribe"
    redacted = _redact_dsn(dsn)
    assert "secret" not in redacted
    assert "scribe:***@" in redacted


def test_backup_filename_contains_schema_and_timestamp() -> None:
    now = _dt("20260215T054500Z")
    name = _backup_filename(schema="scribe", now=now)
    assert name == "scribe_scribe_20260215T054500Z.dump"


def test_select_retained_backups_keeps_daily_and_weekly_windows() -> None:
    backups = [
        BackupFile(Path("a.dump"), _dt("20260215T054500Z")),  # week 7
        BackupFile(Path("b.dump"), _dt("20260214T054500Z")),  # week 7
        BackupFile(Path("c.dump"), _dt("20260208T054500Z")),  # week 6
        BackupFile(Path("d.dump"), _dt("20260201T054500Z")),  # week 5
        BackupFile(Path("e.dump"), _dt("20260125T054500Z")),  # week 4
        BackupFile(Path("f.dump"), _dt("20260118T054500Z")),  # week 3
    ]
    retained = _select_retained_backups(backups, keep_daily=2, keep_weekly=4)

    assert Path("a.dump") in retained
    assert Path("b.dump") in retained
    assert Path("c.dump") in retained
    assert Path("d.dump") in retained
    assert Path("e.dump") in retained
    assert Path("f.dump") not in retained

