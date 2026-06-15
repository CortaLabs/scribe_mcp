from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from typing import Sequence

from scribe_mcp.scripts import postgres_restore as restore_module
from scribe_mcp.scripts.postgres_restore import _execute_plan, _parse_args, _plan_from_args, main


PRIVATE_TARGET_SOURCE = "private-target-connection-source"
PRIVATE_CREDENTIAL_MARKER = "private-credential-marker"
PRIVATE_ENDPOINT_MARKER = "private-endpoint-marker"


def _base_args(tmp_path: Path, *, dsn: str = PRIVATE_TARGET_SOURCE) -> list[str]:
    dump_file = tmp_path / "source_artifact"
    dump_file.write_text("private dump placeholder", encoding="utf-8")
    return [
        "--preflight-only",
        "--dump-file",
        str(dump_file),
        "--target-postgres-dsn",
        dsn,
        "--private-manifest-dir",
        str(tmp_path / "private-manifest"),
        "--target-class-label",
        "reviewed_local_non_active_non_prod_non_remote_non_main_non_shared_non_canonical",
        "--active-runtime-exclusion-label",
        "active_runtime_excluded",
        "--public-summary-json",
        str(tmp_path / "public-summary.json"),
    ]


def test_preflight_writes_redacted_public_summary_and_owner_only_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    dump_file = tmp_path / "source_artifact"
    argv = _base_args(tmp_path)

    result = main(argv)

    captured = capsys.readouterr()
    assert result == 0
    assert "restore preflight ok" in captured.out
    for stream in (captured.out, captured.err):
        assert PRIVATE_TARGET_SOURCE not in stream
        assert PRIVATE_CREDENTIAL_MARKER not in stream
        assert str(dump_file) not in stream
        assert PRIVATE_ENDPOINT_MARKER not in stream

    public_summary = json.loads((tmp_path / "public-summary.json").read_text(encoding="utf-8"))
    assert public_summary["status"] == "preflight-ok"
    assert public_summary["target_postgres_dsn"] == "provided"
    assert public_summary["dump_file"] == "provided"
    public_blob = json.dumps(public_summary)
    assert PRIVATE_TARGET_SOURCE not in public_blob
    assert str(dump_file) not in public_blob
    assert PRIVATE_ENDPOINT_MARKER not in public_blob

    manifest_dir = tmp_path / "private-manifest"
    manifest_mode = stat.S_IMODE(manifest_dir.stat().st_mode)
    assert manifest_mode & (stat.S_IRWXG | stat.S_IRWXO) == 0


def test_preflight_blocks_missing_target_source_without_env_leak(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(restore_module, "_default_target_dsn", lambda: None)

    argv = _base_args(tmp_path)
    dsn_index = argv.index("--target-postgres-dsn")
    del argv[dsn_index : dsn_index + 2]

    result = main(argv)

    captured = capsys.readouterr()
    assert result == 2
    assert "target connection source is unavailable" in captured.err
    assert PRIVATE_TARGET_SOURCE not in captured.err
    assert PRIVATE_CREDENTIAL_MARKER not in captured.err
    public_summary = json.loads((tmp_path / "public-summary.json").read_text(encoding="utf-8"))
    assert public_summary["status"] == "blocked"
    assert public_summary["target_postgres_dsn"] == "default-source"
    assert public_summary["reason"] == "target connection source is unavailable"


def test_preflight_allows_default_target_source_when_available_without_env_leak(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    default_target_source = "default-private-target-source"
    monkeypatch.setattr(restore_module, "_default_target_dsn", lambda: default_target_source)

    argv = _base_args(tmp_path)
    dsn_index = argv.index("--target-postgres-dsn")
    del argv[dsn_index : dsn_index + 2]

    result = main(argv)

    captured = capsys.readouterr()
    assert result == 0
    assert "private_inputs=redacted" in captured.out
    assert default_target_source not in captured.out
    assert default_target_source not in captured.err
    assert PRIVATE_CREDENTIAL_MARKER not in captured.out
    assert PRIVATE_CREDENTIAL_MARKER not in captured.err
    public_summary = json.loads((tmp_path / "public-summary.json").read_text(encoding="utf-8"))
    assert public_summary["target_postgres_dsn"] == "provided"


def test_replace_after_backup_fails_closed_without_backup_flag(tmp_path: Path, capsys) -> None:
    argv = _base_args(tmp_path) + ["--mode", "replace-after-backup"]

    result = main(argv)

    captured = capsys.readouterr()
    assert result == 2
    assert "replace restore requires backup-before-restore" in captured.err
    assert PRIVATE_TARGET_SOURCE not in captured.err
    assert PRIVATE_CREDENTIAL_MARKER not in captured.err
    assert PRIVATE_ENDPOINT_MARKER not in captured.err


def test_labels_are_required_before_contact_path(tmp_path: Path, capsys) -> None:
    argv = _base_args(tmp_path)
    label_index = argv.index("--target-class-label")
    argv[label_index + 1] = "../unsafe"

    result = main(argv)

    captured = capsys.readouterr()
    assert result == 2
    assert "target class label is required" in captured.err
    assert PRIVATE_TARGET_SOURCE not in captured.err


def test_semantically_unsafe_target_labels_fail_closed(tmp_path: Path, capsys) -> None:
    for index, unsafe_label in enumerate(("prod", "remote", "unsafe", "local_non_prod")):
        case_dir = tmp_path / f"target-label-{index}"
        case_dir.mkdir()
        argv = _base_args(case_dir)
        label_index = argv.index("--target-class-label")
        argv[label_index + 1] = unsafe_label

        result = main(argv)

        captured = capsys.readouterr()
        assert result == 2
        assert "target class label is required" in captured.err
        assert PRIVATE_TARGET_SOURCE not in captured.err


def test_semantically_unsafe_active_runtime_labels_fail_closed(tmp_path: Path, capsys) -> None:
    for index, unsafe_label in enumerate(("prod", "remote", "unsafe", "active_runtime")):
        case_dir = tmp_path / f"active-label-{index}"
        case_dir.mkdir()
        argv = _base_args(case_dir)
        label_index = argv.index("--active-runtime-exclusion-label")
        argv[label_index + 1] = unsafe_label

        result = main(argv)

        captured = capsys.readouterr()
        assert result == 2
        assert "active runtime exclusion label is required" in captured.err
        assert PRIVATE_TARGET_SOURCE not in captured.err


def test_accepted_hyphenated_labels_pass_preflight(tmp_path: Path, capsys) -> None:
    argv = _base_args(tmp_path)
    target_label_index = argv.index("--target-class-label")
    argv[target_label_index + 1] = "reviewed-local-non-active-non-prod-non-remote-non-main-non-shared-non-canonical"
    exclusion_label_index = argv.index("--active-runtime-exclusion-label")
    argv[exclusion_label_index + 1] = "active-runtime-excluded"

    result = main(argv)

    captured = capsys.readouterr()
    assert result == 0
    assert "restore preflight ok" in captured.out


def test_mutation_path_uses_fake_subprocess_and_redacts_failure(
    tmp_path: Path,
    capsys,
) -> None:
    argv = _base_args(tmp_path)
    argv.remove("--preflight-only")
    args = _parse_args(argv)
    plan = _plan_from_args(args)
    calls: list[list[str]] = []

    def _fake_run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        return subprocess.CompletedProcess(
            list(command),
            1,
            f"private output {PRIVATE_TARGET_SOURCE} {PRIVATE_CREDENTIAL_MARKER}",
            f"private error {PRIVATE_ENDPOINT_MARKER}",
        )

    result = _execute_plan(plan, runner=_fake_run)

    captured = capsys.readouterr()
    assert result == 1
    assert calls
    assert calls[0][0] == "psql"
    assert "subprocess command failed; private output suppressed" in captured.err
    assert PRIVATE_TARGET_SOURCE not in captured.err
    assert PRIVATE_CREDENTIAL_MARKER not in captured.err
    assert PRIVATE_ENDPOINT_MARKER not in captured.err


def test_require_empty_target_blocks_nonzero_count_before_restore(
    tmp_path: Path,
    capsys,
) -> None:
    argv = _base_args(tmp_path)
    argv.remove("--preflight-only")
    args = _parse_args(argv)
    plan = _plan_from_args(args)
    calls: list[list[str]] = []

    def _fake_run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        return subprocess.CompletedProcess(
            list(command),
            0,
            "1\n",
            f"private error {PRIVATE_CREDENTIAL_MARKER} {PRIVATE_ENDPOINT_MARKER}",
        )

    result = _execute_plan(plan, runner=_fake_run)

    captured = capsys.readouterr()
    assert result == 1
    assert [call[0] for call in calls] == ["psql"]
    assert "target schema is not empty" in captured.err
    assert PRIVATE_TARGET_SOURCE not in captured.err
    assert PRIVATE_CREDENTIAL_MARKER not in captured.err
    assert PRIVATE_ENDPOINT_MARKER not in captured.err


def test_require_empty_target_blocks_unparsable_or_empty_count_before_restore(
    tmp_path: Path,
    capsys,
) -> None:
    for index, count_output in enumerate(("", "not-a-count\n", "-1\n", "0\n0\n")):
        case_dir = tmp_path / f"case-{index}"
        case_dir.mkdir()
        argv = _base_args(case_dir)
        argv.remove("--preflight-only")
        args = _parse_args(argv)
        plan = _plan_from_args(args)
        calls: list[list[str]] = []

        def _fake_run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
            calls.append(list(command))
            return subprocess.CompletedProcess(list(command), 0, count_output, PRIVATE_CREDENTIAL_MARKER)

        result = _execute_plan(plan, runner=_fake_run)

        captured = capsys.readouterr()
        assert result == 1
        assert [call[0] for call in calls] == ["psql"]
        assert "target emptiness could not be verified" in captured.err
        assert PRIVATE_TARGET_SOURCE not in captured.err
        assert PRIVATE_CREDENTIAL_MARKER not in captured.err


def test_private_manifest_under_managed_docs_fails_closed_without_target_source_leak(
    tmp_path: Path,
    capsys,
) -> None:
    argv = _base_args(tmp_path)
    manifest_index = argv.index("--private-manifest-dir")
    argv[manifest_index + 1] = str(tmp_path / ".scribe" / "docs" / "private-manifest")

    result = main(argv)

    captured = capsys.readouterr()
    assert result == 1
    assert "private manifest directory must not be under managed docs" in captured.err
    assert PRIVATE_TARGET_SOURCE not in captured.out
    assert PRIVATE_TARGET_SOURCE not in captured.err
    public_summary = json.loads((tmp_path / "public-summary.json").read_text(encoding="utf-8"))
    assert public_summary["status"] == "blocked"
    assert public_summary["reason"] == "private manifest directory must not be under managed docs"
    assert PRIVATE_TARGET_SOURCE not in json.dumps(public_summary)


def test_require_empty_target_zero_count_permits_restore_with_fake_subprocess(tmp_path: Path) -> None:
    argv = _base_args(tmp_path) + ["--target-schema", "scribe_test"]
    argv.remove("--preflight-only")
    args = _parse_args(argv)
    plan = _plan_from_args(args)
    calls: list[list[str]] = []

    def _fake_run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        private_output = "0\n" if command[0] == "psql" else ""
        return subprocess.CompletedProcess(list(command), 0, private_output, "")

    result = _execute_plan(plan, runner=_fake_run)

    assert result == 0
    assert [call[0] for call in calls] == ["psql", "pg_restore"]
    assert "table_schema = 'scribe_test'" in calls[0][-1]


def test_replace_restore_runs_backup_then_restore_with_fake_subprocess(tmp_path: Path) -> None:
    argv = _base_args(tmp_path) + ["--mode", "replace-after-backup", "--backup-before-restore"]
    argv.remove("--preflight-only")
    args = _parse_args(argv)
    plan = _plan_from_args(args)
    calls: list[list[str]] = []

    def _fake_run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        return subprocess.CompletedProcess(list(command), 0, "", "")

    result = _execute_plan(plan, runner=_fake_run)

    assert result == 0
    assert [call[0] for call in calls] == ["pg_dump", "pg_restore"]


def test_help_is_importable(capsys) -> None:
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "Preflight or restore" in captured.out
