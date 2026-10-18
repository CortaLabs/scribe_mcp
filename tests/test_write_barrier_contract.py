from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.scripts import postgres_backup, postgres_restore
from scribe_mcp.shared.write_barrier import (
    WriteBarrierError,
    assert_writes_allowed,
    read_write_barrier_state,
    scribe_owned_write_barrier_acquire,
    scribe_owned_write_barrier_lock,
    scribe_owned_write_barrier_release,
)
from scribe_mcp.tools import append_entry as append_entry_module
from scribe_mcp.tools import set_project as set_project_module


def test_barrier_acquires_public_safe_evidence_and_releases(tmp_path: Path) -> None:
    forbidden = {str(tmp_path), "postgres://", "password", "pg_restore", "stdout", "stderr"}

    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="test-owner",
        reason_label="test-maintenance",
    ) as evidence:
        state = read_write_barrier_state(tmp_path)

        assert evidence.status_label == "scribe_owned_write_barrier_lock:acquired"
        assert evidence.operation_label == "test-maintenance"
        assert evidence.private_values_recorded is False
        assert evidence.lock_fingerprint is not None
        assert state == evidence
        evidence_blob = json.dumps(evidence.__dict__, sort_keys=True)
        for value in forbidden:
            assert value not in evidence_blob

    assert read_write_barrier_state(tmp_path) is None


def test_assert_writes_allowed_blocks_other_operations_but_allows_owner(tmp_path: Path) -> None:
    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="test-owner",
        reason_label="restore-private-target",
    ):
        assert_writes_allowed(tmp_path, operation_label="restore-private-target")
        with pytest.raises(WriteBarrierError):
            assert_writes_allowed(tmp_path, operation_label="append_entry")


def test_maintained_barrier_acquires_reads_blocks_and_releases(tmp_path: Path) -> None:
    evidence = scribe_owned_write_barrier_acquire(
        tmp_path,
        owner_label="train-30bn-step-0",
        reason_label="replace-after-backup",
    )
    state = read_write_barrier_state(tmp_path)

    assert state == evidence
    assert evidence.owner_label == "train-30bn-step-0"
    assert evidence.operation_label == "replace-after-backup"
    assert_writes_allowed(tmp_path, operation_label="replace-after-backup")
    with pytest.raises(WriteBarrierError):
        assert_writes_allowed(tmp_path, operation_label="append_entry")

    repeated = scribe_owned_write_barrier_acquire(
        tmp_path,
        owner_label="train-30bn-step-0",
        reason_label="replace-after-backup",
    )
    assert repeated == evidence

    with pytest.raises(WriteBarrierError):
        scribe_owned_write_barrier_acquire(
            tmp_path,
            owner_label="another-operation",
            reason_label="replace-after-backup",
        )
    with pytest.raises(WriteBarrierError):
        scribe_owned_write_barrier_release(
            tmp_path,
            owner_label="another-operation",
            reason_label="replace-after-backup",
        )

    released = scribe_owned_write_barrier_release(
        tmp_path,
        owner_label="train-30bn-step-0",
        reason_label="replace-after-backup",
    )

    assert released == evidence
    assert read_write_barrier_state(tmp_path) is None
    assert (
        scribe_owned_write_barrier_release(
            tmp_path,
            owner_label="train-30bn-step-0",
            reason_label="replace-after-backup",
        )
        is None
    )


def test_malformed_lock_state_fails_closed_without_private_readback(tmp_path: Path) -> None:
    lock_path = tmp_path / ".scribe" / "locks" / "write-barrier.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(f"not-json {tmp_path}", encoding="utf-8")

    state = read_write_barrier_state(tmp_path)

    assert state is not None
    assert state.status_label == "scribe_owned_write_barrier_lock:malformed"
    assert state.operation_label == "unknown"
    assert str(tmp_path) not in json.dumps(state.__dict__, sort_keys=True)
    with pytest.raises(WriteBarrierError):
        assert_writes_allowed(tmp_path, operation_label="append_entry")


def test_append_entry_refuses_before_file_write_when_barrier_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = {
        "name": "barrier-test",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
        "docs_dir": str(tmp_path / ".scribe" / "docs"),
        "docs": {},
        "defaults": {},
    }
    context = SimpleNamespace(project=project, recent_projects=[], reminders=[])

    async def fail_record_tool(_tool_name: str) -> dict[str, object]:
        raise AssertionError("record_tool must not run while the write barrier is held")

    async def fail_append_line(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("append_line must not run while the write barrier is held")

    async def fake_finalize_tool_response(*, data: dict[str, object], **_kwargs: object) -> dict[str, object]:
        return data

    class FailAgentIdentity:
        async def get_or_create_agent_id(self) -> str:
            raise AssertionError("get_or_create_agent_id must not run while the write barrier is held")

        async def update_agent_activity(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("update_agent_activity must not run while the write barrier is held")

    monkeypatch.setattr(
        append_entry_module.server_module,
        "state_manager",
        SimpleNamespace(record_tool=fail_record_tool),
    )
    monkeypatch.setattr(append_entry_module.server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(append_entry_module.server_module, "get_agent_identity", lambda: FailAgentIdentity())
    async def fake_resolve_logging_context(**_kwargs: object) -> SimpleNamespace:
        return context

    monkeypatch.setattr(append_entry_module, "resolve_logging_context", fake_resolve_logging_context)
    monkeypatch.setattr(append_entry_module, "append_line", fail_append_line)
    monkeypatch.setattr(append_entry_module.default_formatter, "finalize_tool_response", fake_finalize_tool_response)

    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="test-owner",
        reason_label="maintenance-window",
    ):
        result = asyncio.run(
            append_entry_module.append_entry(
                agent="test-agent",
                message="blocked append",
                format="structured",
            )
        )

    assert result["ok"] is False
    assert "write barrier" in str(result["error"]).lower()
    assert not (tmp_path / "PROGRESS_LOG.md").exists()


def test_append_entry_allowed_path_preserves_persisted_agent_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = {
        "name": "barrier-test",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
        "docs_dir": str(tmp_path / ".scribe" / "docs"),
        "docs": {},
        "defaults": {},
    }
    context = SimpleNamespace(project=project, recent_projects=[], reminders=[])
    calls: dict[str, object] = {
        "created": 0,
        "updated_agent_id": None,
        "resolved_agent_id": None,
    }

    async def fake_record_tool(_tool_name: str) -> dict[str, object]:
        return {}

    async def fake_finalize_tool_response(*, data: dict[str, object], **_kwargs: object) -> dict[str, object]:
        return data

    async def fake_get_reminders(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        return []

    class FakeAgentIdentity:
        async def get_or_create_agent_id(self) -> str:
            calls["created"] = int(calls["created"]) + 1
            return "persisted-agent-id"

        async def update_agent_activity(
            self,
            agent_id: str,
            _tool_name: str,
            _metadata: dict[str, object],
        ) -> None:
            calls["updated_agent_id"] = agent_id

    async def fake_resolve_logging_context(**kwargs: object) -> SimpleNamespace:
        calls["resolved_agent_id"] = kwargs["agent_id"]
        return context

    monkeypatch.setattr(
        append_entry_module.server_module,
        "state_manager",
        SimpleNamespace(record_tool=fake_record_tool),
    )
    monkeypatch.setattr(append_entry_module.server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(append_entry_module.server_module, "get_agent_identity", lambda: FakeAgentIdentity())
    monkeypatch.setattr(append_entry_module.server_module, "storage_backend", None)
    monkeypatch.setattr(append_entry_module, "resolve_logging_context", fake_resolve_logging_context)
    monkeypatch.setattr(append_entry_module.reminders, "get_reminders", fake_get_reminders)
    monkeypatch.setattr(append_entry_module.default_formatter, "finalize_tool_response", fake_finalize_tool_response)
    monkeypatch.setattr(
        append_entry_module,
        "_PROJECT_REGISTRY",
        SimpleNamespace(touch_entry=lambda *_args, **_kwargs: None),
    )

    result = asyncio.run(
        append_entry_module.append_entry(
            agent="resolution-agent",
            message="allowed append",
            format="structured",
        )
    )

    assert result["ok"] is True
    assert calls == {
        "created": 1,
        "updated_agent_id": "persisted-agent-id",
        "resolved_agent_id": "resolution-agent",
    }
    assert (tmp_path / "PROGRESS_LOG.md").exists()


def test_apply_doc_change_refuses_before_ensure_parent_when_barrier_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_path = tmp_path / ".scribe" / "docs" / "CHECKLIST.md"
    project = {
        "name": "barrier-test",
        "root": str(tmp_path),
        "docs": {"checklist": str(doc_path)},
        "docs_dir": str(tmp_path / ".scribe" / "docs"),
    }

    async def fail_ensure_parent(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ensure_parent must not run while the write barrier is held")

    monkeypatch.setattr("scribe_mcp.doc_management.manager.ensure_parent", fail_ensure_parent)

    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="test-owner",
        reason_label="maintenance-window",
    ):
        result = asyncio.run(
            apply_doc_change(
                project,
                doc_name="checklist",
                action="replace_section",
                section="task",
                content="done",
                template=None,
                metadata={},
                dry_run=False,
            )
        )

    assert result.success is False
    assert "write barrier" in str(result.error_message).lower()
    assert not doc_path.exists()


def test_set_project_refuses_before_state_write_when_barrier_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_record_tool(_tool_name: str) -> dict[str, object]:
        raise AssertionError("record_tool must not run while the write barrier is held")

    monkeypatch.setattr(
        set_project_module.server_module,
        "state_manager",
        SimpleNamespace(record_tool=fail_record_tool),
    )

    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="test-owner",
        reason_label="maintenance-window",
    ):
        with pytest.raises(WriteBarrierError):
            asyncio.run(
                set_project_module.set_project(
                    agent="test-agent",
                    name="barrier-test",
                    root=str(tmp_path),
                    format="structured",
                )
            )


def test_backup_refuses_before_output_dir_or_subprocess_when_barrier_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "backup-output"

    def fail_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("pg_dump must not run while the write barrier is held")

    monkeypatch.setattr(postgres_backup.subprocess, "run", fail_run)

    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="test-owner",
        reason_label="maintenance-window",
    ):
        result = postgres_backup.main(
            [
                "--postgres-dsn",
                "opaque-a:opaque-b@opaque-c/opaque-d",
                "--schema",
                "scribe",
                "--output-dir",
                str(output_dir),
            ]
        )

    assert result == 1
    assert not output_dir.exists()


def test_restore_holds_barrier_around_target_mutation_with_fake_runner(tmp_path: Path) -> None:
    argv = [
        "--dump-file",
        str(tmp_path / "source.dump"),
        "--target-postgres-dsn",
        "private-target-source",
        "--private-manifest-dir",
        str(tmp_path / "private-manifest"),
        "--target-class-label",
        "reviewed_local_non_active_non_prod_non_remote_non_main_non_shared_non_canonical",
        "--active-runtime-exclusion-label",
        "active_runtime_excluded",
        "--mode",
        "replace-after-backup",
        "--backup-before-restore",
    ]
    (tmp_path / "source.dump").write_text("fake dump", encoding="utf-8")
    plan = postgres_restore._plan_from_args(postgres_restore._parse_args(argv))
    observed_states: list[object] = []

    def fake_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        observed_states.append(read_write_barrier_state(tmp_path))
        assert_writes_allowed(tmp_path, operation_label="postgres_restore")
        return subprocess.CompletedProcess(list(command), 0, "", "")

    result = postgres_restore._execute_plan(plan, runner=fake_runner)

    assert result == 0
    assert observed_states
    assert all(state is not None for state in observed_states)
    assert read_write_barrier_state(tmp_path) is None


def test_restore_refuses_before_manifest_summary_or_runner_when_barrier_held(tmp_path: Path) -> None:
    private_manifest_dir = tmp_path / "private-manifest"
    public_summary_json = tmp_path / "public" / "restore-summary.json"
    argv = [
        "--dump-file",
        str(tmp_path / "source.dump"),
        "--target-postgres-dsn",
        "private-target-source",
        "--private-manifest-dir",
        str(private_manifest_dir),
        "--public-summary-json",
        str(public_summary_json),
        "--target-class-label",
        "reviewed_local_non_active_non_prod_non_remote_non_main_non_shared_non_canonical",
        "--active-runtime-exclusion-label",
        "active_runtime_excluded",
        "--preflight-only",
    ]
    (tmp_path / "source.dump").write_text("fake dump", encoding="utf-8")
    plan = postgres_restore._plan_from_args(postgres_restore._parse_args(argv))
    runner_calls: list[Sequence[str]] = []

    def fail_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        runner_calls.append(command)
        raise AssertionError("pg_restore must not run while the write barrier is held")

    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="test-owner",
        reason_label="maintenance-window",
    ):
        result = postgres_restore._execute_plan(plan, runner=fail_runner)

    assert result == 1
    assert runner_calls == []
    assert not private_manifest_dir.exists()
    assert not public_summary_json.exists()


def test_restore_lock_creation_failure_refuses_before_manifest_summary_or_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_manifest_dir = tmp_path / "private-manifest"
    public_summary_json = tmp_path / "public" / "restore-summary.json"
    argv = [
        "--dump-file",
        str(tmp_path / "source.dump"),
        "--target-postgres-dsn",
        "private-target-source",
        "--private-manifest-dir",
        str(private_manifest_dir),
        "--public-summary-json",
        str(public_summary_json),
        "--target-class-label",
        "reviewed_local_non_active_non_prod_non_remote_non_main_non_shared_non_canonical",
        "--active-runtime-exclusion-label",
        "active_runtime_excluded",
        "--preflight-only",
    ]
    (tmp_path / "source.dump").write_text("fake dump", encoding="utf-8")
    plan = postgres_restore._plan_from_args(postgres_restore._parse_args(argv))
    runner_calls: list[Sequence[str]] = []

    def fail_barrier_lock(*_args: object, **_kwargs: object) -> object:
        raise OSError("lock directory creation failed")

    def fail_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        runner_calls.append(command)
        raise AssertionError("pg_restore must not run when barrier acquisition fails")

    monkeypatch.setattr(postgres_restore, "scribe_owned_write_barrier_lock", fail_barrier_lock)

    result = postgres_restore._execute_plan(plan, runner=fail_runner)

    assert result == 1
    assert runner_calls == []
    assert not private_manifest_dir.exists()
    assert not public_summary_json.exists()


def test_restore_invalid_plan_refuses_before_public_summary_when_barrier_held(tmp_path: Path) -> None:
    private_manifest_dir = tmp_path / "private-manifest"
    public_summary_json = tmp_path / "public" / "restore-summary.json"
    argv = [
        "--dump-file",
        str(tmp_path / "missing-source.dump"),
        "--target-postgres-dsn",
        "private-target-source",
        "--private-manifest-dir",
        str(private_manifest_dir),
        "--public-summary-json",
        str(public_summary_json),
        "--target-class-label",
        "reviewed_local_non_active_non_prod_non_remote_non_main_non_shared_non_canonical",
        "--active-runtime-exclusion-label",
        "active_runtime_excluded",
        "--preflight-only",
    ]
    plan = postgres_restore._plan_from_args(postgres_restore._parse_args(argv))
    runner_calls: list[Sequence[str]] = []

    def fail_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        runner_calls.append(command)
        raise AssertionError("pg_restore must not run for an invalid plan while the write barrier is held")

    with scribe_owned_write_barrier_lock(
        tmp_path,
        owner_label="test-owner",
        reason_label="maintenance-window",
    ):
        result = postgres_restore._execute_plan(plan, runner=fail_runner)

    assert result != 0
    assert runner_calls == []
    assert not private_manifest_dir.exists()
    assert not public_summary_json.exists()
