from __future__ import annotations

import stat
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from scribe_mcp.scripts.postgres_backup import (
    BackupFile,
    _backup_filename,
    _redact_dsn,
    _sanitize_command,
    _select_retained_backups,
    main,
)


def _dt(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def test_redact_dsn_hides_private_fragment() -> None:
    dsn = "opaque-a:opaque-b@opaque-c/opaque-d"
    redacted = _redact_dsn(dsn)
    assert "opaque-b" not in redacted
    assert "opaque-a:***@" in redacted


def test_sanitize_command_redacts_dbname_dsn() -> None:
    command = [
        "pg_dump",
        "--format=custom",
        "--dbname=opaque-a:opaque-b@opaque-c/opaque-d",
    ]

    sanitized = _sanitize_command(command)

    assert sanitized[:2] == command[:2]
    assert "opaque-b" not in sanitized[2]
    assert sanitized[2] == "--dbname=opaque-a:***@opaque-c/opaque-d"


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


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _argv(
    output_dir: Path,
    *,
    dsn: str = "opaque-a:opaque-b@opaque-c/opaque-d",
) -> list[str]:
    return [
        "--postgres-dsn",
        dsn,
        "--schema",
        "scribe",
        "--output-dir",
        str(output_dir),
    ]


def test_new_output_dir_becomes_owner_only_and_manifest_is_private(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "custody-area"

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        destination = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--file=")))
        destination.write_bytes(b"fake dump")
        return SimpleNamespace(returncode=0, **{"stderr": ""})

    monkeypatch.setattr("scribe_mcp.scripts.postgres_backup.subprocess.run", fake_run)

    assert main(_argv(output_dir)) == 0

    manifest_path = output_dir / "latest_backup_manifest.json"
    assert _mode(output_dir) == 0o700
    assert _mode(manifest_path) == 0o600


def test_existing_broad_output_dir_fails_closed_without_repair_or_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "wide-area"
    output_dir.mkdir(mode=0o777)
    output_dir.chmod(0o777)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        destination = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--file=")))
        destination.write_bytes(b"should not be written")
        return SimpleNamespace(returncode=0, **{"stderr": ""})

    monkeypatch.setattr("scribe_mcp.scripts.postgres_backup.subprocess.run", fake_run)

    assert main(_argv(output_dir)) == 1

    assert _mode(output_dir) == 0o777
    assert not (output_dir / "latest_backup_manifest.json").exists()
    assert not list(output_dir.glob("*.dump"))


def test_existing_file_output_dir_fails_closed_without_private_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_path = tmp_path / "custody-file"
    output_path.write_text("not a directory", encoding="utf-8")

    def fail_run(command: list[str], **_: object) -> SimpleNamespace:
        raise AssertionError(f"pg_dump must not run for rejected output dir: {command!r}")

    monkeypatch.setattr("scribe_mcp.scripts.postgres_backup.subprocess.run", fail_run)

    assert main(_argv(output_path)) == 1

    captured = capsys.readouterr()
    public_output = captured.out + captured.err
    forbidden = [
        str(output_path),
        "opaque-d",
        "opaque-c",
        "opaque-a",
        "opaque-b",
        "opaque-a:opaque-b@opaque-c/opaque-d",
    ]
    for value in forbidden:
        assert value not in public_output
    assert "output_status=rejected_not_directory" in captured.err


def test_existing_owner_only_output_dir_succeeds_under_fake_pg_dump(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "owner-area"
    output_dir.mkdir(mode=0o700)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        destination = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--file=")))
        destination.write_bytes(b"fake dump")
        return SimpleNamespace(returncode=0, **{"stderr": ""})

    monkeypatch.setattr("scribe_mcp.scripts.postgres_backup.subprocess.run", fake_run)

    assert main(_argv(output_dir)) == 0
    assert (output_dir / "latest_backup_manifest.json").exists()
    assert len(list(output_dir.glob("scribe_scribe_*.dump"))) == 1


def test_fake_pg_dump_success_enforces_dump_mode_before_manifest_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = tmp_path / "owner-area"
    output_dir.mkdir(mode=0o700)
    observed_dump_modes: list[int] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        destination = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--file=")))
        destination.write_bytes(b"fake dump")
        destination.chmod(0o644)
        return SimpleNamespace(returncode=0, **{"stderr": ""})

    def fake_write_manifest(**kwargs: object) -> None:
        backup_path = kwargs["backup_path"]
        assert isinstance(backup_path, Path)
        observed_dump_modes.append(_mode(backup_path))
        original_write_manifest(**kwargs)

    from scribe_mcp.scripts import postgres_backup

    original_write_manifest = postgres_backup._write_manifest
    monkeypatch.setattr(postgres_backup.subprocess, "run", fake_run)
    monkeypatch.setattr(postgres_backup, "_write_manifest", fake_write_manifest)

    assert main(_argv(output_dir)) == 0

    dump_path = next(output_dir.glob("scribe_scribe_*.dump"))
    assert observed_dump_modes == [0o600]
    assert _mode(dump_path) == 0o600


def test_pg_dump_failure_public_output_is_redacted(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_dir = tmp_path / "custody-area"
    dsn = "opaque-a:opaque-b@opaque-c/opaque-d"
    raw_stderr = "opaque-e opaque-f opaque-g opaque-h opaque-i"

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=37, **{"stderr": raw_stderr})

    monkeypatch.setattr("scribe_mcp.scripts.postgres_backup.subprocess.run", fake_run)

    assert main(_argv(output_dir, dsn=dsn)) == 1

    captured = capsys.readouterr()
    public_output = captured.out + captured.err
    forbidden = [
        str(output_dir),
        "scribe_scribe_",
        "opaque-d",
        "opaque-c",
        "opaque-a",
        "opaque-b",
        "opaque-i",
        raw_stderr,
        dsn,
    ]
    for value in forbidden:
        assert value not in public_output
    assert "pg_dump_status=failed" in public_output
    assert "return_code=37" in public_output


def test_success_public_output_uses_redacted_status_labels_only(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_dir = tmp_path / "custody-area"
    dsn = "opaque-a:opaque-b@opaque-c/opaque-d"

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        destination = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--file=")))
        destination.write_bytes(b"fake dump")
        return SimpleNamespace(returncode=0, **{"stderr": ""})

    monkeypatch.setattr("scribe_mcp.scripts.postgres_backup.subprocess.run", fake_run)

    assert main(_argv(output_dir, dsn=dsn)) == 0

    captured = capsys.readouterr()
    public_output = captured.out + captured.err
    forbidden = [
        str(output_dir),
        "scribe_scribe_",
        "opaque-d",
        "opaque-c",
        "opaque-a",
        "opaque-b",
        dsn,
    ]
    for value in forbidden:
        assert value not in public_output
    assert "backup_status=success" in public_output
    assert "manifest_status=written" in public_output


def test_managed_docs_output_placement_is_rejected(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / ".scribe" / "docs" / "custody-area"

    assert main(_argv(output_dir)) == 1

    captured = capsys.readouterr()
    assert "output_status=rejected_managed_docs" in captured.err
    assert str(output_dir) not in captured.err
    assert not output_dir.exists()


def test_main_is_importable_and_callable() -> None:
    assert callable(main)
