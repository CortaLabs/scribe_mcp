"""Fail-closed Postgres restore primitive for private Scribe backups."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from scribe_mcp.config.settings import settings

RestoreRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

_SAFE_LABEL_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
_VALID_MODES = {"require-empty-target", "replace-after-backup"}
_REQUIRED_TARGET_LABEL_CLASSES = (
    "local",
    "non_active",
    "non_prod",
    "non_remote",
    "non_main",
    "non_shared",
    "non_canonical",
)
_ACTIVE_RUNTIME_REVIEW_TOKENS = {"excluded", "exclusion", "review", "reviewed"}


@dataclass(frozen=True)
class RestorePlan:
    dump_file: Path
    target_postgres_dsn: str | None
    target_schema: str
    source_schema: str | None
    mode: str
    backup_before_restore: bool
    preflight_only: bool
    private_manifest_dir: Path
    public_summary_json: Path | None
    target_class_label: str
    active_runtime_exclusion_label: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_safe_label(value: str | None) -> bool:
    if not value or len(value) > 128:
        return False
    return all(char in _SAFE_LABEL_CHARS for char in value)


def _label_tokens(value: str) -> list[str]:
    return [token for token in value.lower().replace("-", "_").replace(".", "_").split("_") if token]


def _has_label_class(tokens: Sequence[str], label_class: str) -> bool:
    class_tokens = label_class.split("_")
    if len(class_tokens) == 1:
        return class_tokens[0] in tokens
    return any(tokens[index : index + len(class_tokens)] == class_tokens for index in range(len(tokens)))


def _is_safe_target_class_label(value: str | None) -> bool:
    if not _is_safe_label(value):
        return False
    tokens = _label_tokens(value or "")
    return all(_has_label_class(tokens, label_class) for label_class in _REQUIRED_TARGET_LABEL_CLASSES)


def _is_safe_active_runtime_exclusion_label(value: str | None) -> bool:
    if not _is_safe_label(value):
        return False
    tokens = _label_tokens(value or "")
    return (
        _has_label_class(tokens, "active_runtime")
        and any(token in _ACTIVE_RUNTIME_REVIEW_TOKENS for token in tokens)
    )


def _private_value_label(value: str | None) -> str:
    return "provided" if value else "default-source"


def _schema_label(value: str | None) -> str:
    return "provided" if value else "default"


def _path_is_owner_only_dir(path: Path) -> bool:
    mode = stat.S_IMODE(path.stat().st_mode)
    return path.is_dir() and mode & (stat.S_IRWXG | stat.S_IRWXO) == 0


def _ensure_owner_only_dir(path: Path) -> None:
    parts = path.parts
    for idx, part in enumerate(parts[:-1]):
        if part == ".scribe" and parts[idx + 1] == "docs":
            raise ValueError("private manifest directory must not be under managed docs")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    if not _path_is_owner_only_dir(path):
        raise ValueError("private manifest directory is not owner-only")


def _default_target_dsn() -> str | None:
    raw = getattr(settings, "db_url", None)
    return str(raw) if raw else None


def _build_summary(plan: RestorePlan, *, status: str, reason: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": status,
        "created_at_utc": _utc_now(),
        "operation": "postgres_restore",
        "preflight_only": plan.preflight_only,
        "mode": plan.mode,
        "backup_before_restore": plan.backup_before_restore,
        "target_class_label": plan.target_class_label,
        "active_runtime_exclusion_label": plan.active_runtime_exclusion_label,
        "dump_file": "provided",
        "target_postgres_dsn": _private_value_label(plan.target_postgres_dsn),
        "target_schema": _schema_label(plan.target_schema),
        "source_schema": _schema_label(plan.source_schema),
        "command_plan": _command_plan_labels(plan),
    }
    if reason:
        payload["reason"] = reason
    return payload


def _write_public_summary(plan: RestorePlan, *, status: str, reason: str | None = None) -> None:
    if plan.public_summary_json is None:
        return
    plan.public_summary_json.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_summary(plan, status=status, reason=reason)
    plan.public_summary_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_private_manifest(plan: RestorePlan, *, status: str) -> None:
    _ensure_owner_only_dir(plan.private_manifest_dir)
    payload = {
        "created_at_utc": _utc_now(),
        "status": status,
        "operation": "postgres_restore",
        "mode": plan.mode,
        "preflight_only": plan.preflight_only,
        "backup_before_restore": plan.backup_before_restore,
        "target_class_label": plan.target_class_label,
        "active_runtime_exclusion_label": plan.active_runtime_exclusion_label,
        "private_inputs": {
            "dump_file": "provided",
            "target_postgres_dsn": _private_value_label(plan.target_postgres_dsn),
            "target_schema": _schema_label(plan.target_schema),
            "source_schema": _schema_label(plan.source_schema),
        },
        "command_plan": _command_plan_labels(plan),
    }
    manifest_path = plan.private_manifest_dir / "restore_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)


def _command_plan_labels(plan: RestorePlan) -> list[str]:
    labels = ["validate_dump_artifact", "validate_target_exclusion_label"]
    if plan.mode == "require-empty-target":
        labels.append("verify_target_empty")
    if plan.backup_before_restore:
        labels.append("backup_target_before_restore")
    labels.append("restore_private_dump")
    return labels


def _run_checked(command: Sequence[str], *, runner: RestoreRunner) -> subprocess.CompletedProcess[str]:
    completed = runner(command)
    if completed.returncode != 0:
        raise RuntimeError("subprocess command failed; private output suppressed")
    return completed


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def _run_backup_before_restore(plan: RestorePlan, *, runner: RestoreRunner) -> None:
    if not plan.target_postgres_dsn:
        raise RuntimeError("target connection source is unavailable")
    backup_file = plan.private_manifest_dir / "pre_restore_target_backup.dump"
    command = [
        "pg_dump",
        "--format=custom",
        f"--schema={plan.target_schema}",
        f"--file={backup_file}",
        f"--dbname={plan.target_postgres_dsn}",
    ]
    _run_checked(command, runner=runner)


def _run_empty_target_check(plan: RestorePlan, *, runner: RestoreRunner) -> None:
    if not plan.target_postgres_dsn:
        raise RuntimeError("target connection source is unavailable")
    target_schema = plan.target_schema.replace("'", "''")
    command = [
        "psql",
        "--no-psqlrc",
        "--tuples-only",
        "--quiet",
        f"--dbname={plan.target_postgres_dsn}",
        "--command",
        (
            "SELECT count(*) FROM information_schema.tables "
            f"WHERE table_schema = '{target_schema}';"
        ),
    ]
    completed = _run_checked(command, runner=runner)
    raw_count = completed.stdout.strip()
    try:
        count = int(raw_count)
    except ValueError as exc:
        raise RuntimeError("target emptiness could not be verified") from exc
    if raw_count != str(count) or count < 0:
        raise RuntimeError("target emptiness could not be verified")
    if count != 0:
        raise RuntimeError("target schema is not empty")


def _run_restore(plan: RestorePlan, *, runner: RestoreRunner) -> None:
    if not plan.target_postgres_dsn:
        raise RuntimeError("target connection source is unavailable")
    command = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        f"--dbname={plan.target_postgres_dsn}",
    ]
    if plan.source_schema:
        command.append(f"--schema={plan.source_schema}")
    command.append(str(plan.dump_file))
    _run_checked(command, runner=runner)


def _validate_plan(plan: RestorePlan) -> list[str]:
    errors: list[str] = []
    if not plan.dump_file.exists() or not plan.dump_file.is_file():
        errors.append("dump artifact is unavailable")
    if plan.mode not in _VALID_MODES:
        errors.append("restore mode is invalid")
    if plan.mode == "replace-after-backup" and not plan.backup_before_restore:
        errors.append("replace restore requires backup-before-restore")
    if not plan.target_postgres_dsn:
        errors.append("target connection source is unavailable")
    if not _is_safe_target_class_label(plan.target_class_label):
        errors.append("target class label is required")
    if not _is_safe_active_runtime_exclusion_label(plan.active_runtime_exclusion_label):
        errors.append("active runtime exclusion label is required")
    return errors


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preflight or restore a private Scribe Postgres dump with redacted public output.",
    )
    parser.add_argument("--dump-file", required=True, help="Private dump artifact path.")
    parser.add_argument("--target-postgres-dsn", default=None, help="Private target Postgres DSN.")
    parser.add_argument("--target-schema", default=settings.postgres_schema, help="Private target schema.")
    parser.add_argument("--source-schema", default=None, help="Private source schema filter.")
    parser.add_argument(
        "--mode",
        choices=sorted(_VALID_MODES),
        default="require-empty-target",
        help="Restore safety mode.",
    )
    parser.add_argument(
        "--backup-before-restore",
        action="store_true",
        help="Create a private target backup before restore; required for replace-after-backup.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate restore inputs and command plan without database mutation.",
    )
    parser.add_argument(
        "--private-manifest-dir",
        required=True,
        help="Owner-only private directory for restore manifests.",
    )
    parser.add_argument("--public-summary-json", default=None, help="Optional redacted public summary path.")
    parser.add_argument("--target-class-label", required=True, help="Safe public target classification label.")
    parser.add_argument(
        "--active-runtime-exclusion-label",
        required=True,
        help="Safe public label proving active runtime exclusion review.",
    )
    return parser.parse_args(argv)


def _plan_from_args(args: argparse.Namespace) -> RestorePlan:
    target_dsn = args.target_postgres_dsn or _default_target_dsn()
    return RestorePlan(
        Path(args.dump_file).expanduser().resolve(),
        target_dsn,
        (args.target_schema or settings.postgres_schema or "scribe").strip() or "scribe",
        (args.source_schema or "").strip() or None,
        args.mode,
        bool(args.backup_before_restore),
        bool(args.preflight_only),
        Path(args.private_manifest_dir).expanduser().resolve(),
        Path(args.public_summary_json).expanduser().resolve() if args.public_summary_json else None,
        args.target_class_label,
        args.active_runtime_exclusion_label,
    )


def _execute_plan(plan: RestorePlan, *, runner: RestoreRunner = _default_runner) -> int:
    errors = _validate_plan(plan)
    if errors:
        reason = "; ".join(errors)
        _write_public_summary(plan, status="blocked", reason=reason)
        print(f"restore blocked: {reason}", file=sys.stderr)
        return 2

    try:
        _write_private_manifest(plan, status="preflight" if plan.preflight_only else "started")
        if plan.preflight_only:
            _write_public_summary(plan, status="preflight-ok")
            print("restore preflight ok")
            print(f"target_class_label={plan.target_class_label}")
            print(f"active_runtime_exclusion_label={plan.active_runtime_exclusion_label}")
            print(f"mode={plan.mode}")
            print("private_inputs=redacted")
            return 0

        if plan.mode == "require-empty-target":
            _run_empty_target_check(plan, runner=runner)
        if plan.backup_before_restore:
            _run_backup_before_restore(plan, runner=runner)
        _run_restore(plan, runner=runner)
        _write_private_manifest(plan, status="restored")
        _write_public_summary(plan, status="restored")
        print("restore complete")
        print(f"target_class_label={plan.target_class_label}")
        print("private_inputs=redacted")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        _write_public_summary(plan, status="blocked", reason=str(exc))
        print(f"restore blocked: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        plan = _plan_from_args(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"restore blocked: invalid configuration: {exc}", file=sys.stderr)
        return 2
    return _execute_plan(plan)


if __name__ == "__main__":
    raise SystemExit(main())
