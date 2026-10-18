"""End-to-end manage-docs apply-preview and composite rehome evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.config.repo_config import RepoConfig
from scribe_mcp.doc_management import runtime
from scribe_mcp.doc_management.apply_preview import (
    ApplyPreviewBinding,
    ApplyPreviewService,
)
from scribe_mcp.doc_management.manager import MutationLockTarget
from scribe_mcp.doc_management.rehome_transaction import (
    RehomeCompositeBinding,
    execute_rehome_transaction,
    recover_rehome_transaction,
)
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.manage_docs import manage_docs


pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.regression]


def _project(tmp_path: Path) -> tuple[dict[str, object], Path]:
    root = tmp_path / "lifecycle-repo"
    docs_dir = root / ".scribe" / "docs" / "dev_plans" / "lifecycle"
    docs_dir.mkdir(parents=True)
    architecture = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture.write_text("# Architecture\n\nbefore-value\n", encoding="utf-8")
    progress = docs_dir / "PROGRESS_LOG.md"
    progress.write_text("# Progress\n", encoding="utf-8")
    project: dict[str, object] = {
        "name": "lifecycle",
        "project_key": "lifecycle",
        "repo_id": "repo-lifecycle",
        "root": str(root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress),
        "docs": {
            "architecture": str(architecture),
            "progress_log": str(progress),
        },
    }
    return project, architecture


@contextmanager
def _isolated_runtime(
    state_manager: StateManager,
    storage: SQLiteStorage,
    project: dict[str, object],
    execution: dict[str, object],
):
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
        "get_execution_context": getattr(server_module, "get_execution_context", None),
        "get_agent_identity": getattr(server_module, "get_agent_identity", None),
    }
    from scribe_mcp.tools import manage_docs as manage_docs_module

    original_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context
    server_module.state_manager = state_manager
    server_module.storage_backend = storage
    server_module.get_execution_context = lambda: SimpleNamespace(**execution)
    server_module.get_agent_identity = lambda: None
    root = Path(str(project["root"])).resolve()

    async def _prepare_context(**kwargs):
        return LoggingContext(
            tool_name=str(kwargs.get("tool_name") or "manage_docs"),
            project=project,
            recent_projects=[str(project["name"])],
            state_snapshot=kwargs.get("state_snapshot") or {},
            reminders=[],
            resolution_source="session_binding",
        )

    manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context
    try:
        with patch(
            "scribe_mcp.config.repo_config.get_current_repo_config",
            return_value=(root, RepoConfig(repo_slug="test", repo_root=root)),
        ):
            yield
    finally:
        server_module.state_manager = originals["state_manager"]
        server_module.storage_backend = originals["storage_backend"]
        if originals["get_execution_context"] is not None:
            server_module.get_execution_context = originals["get_execution_context"]
        if originals["get_agent_identity"] is not None:
            server_module.get_agent_identity = originals["get_agent_identity"]
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = (
            original_prepare_context
        )


async def _lifecycle_setup(tmp_path: Path):
    project, architecture = _project(tmp_path)
    storage = SQLiteStorage(tmp_path / "lifecycle.sqlite3")
    await storage.setup()
    await storage.upsert_project(
        name=str(project["name"]),
        repo_root=str(project["root"]),
        progress_log_path=str(project["progress_log"]),
    )
    await storage.update_project_docs(
        str(project["name"]),
        json.dumps(project["docs"]),
        repo_root=str(project["root"]),
    )
    state_manager = StateManager(path=tmp_path / "state.json", storage_backend=storage)
    agent_manager = AgentContextManager(storage, state_manager)
    await storage.upsert_session(
        session_id="session-lifecycle",
        transport_session_id="session-lifecycle",
        agent_id="test-agent",
        repo_root=str(project["root"]),
        mode="project",
    )
    await agent_manager.start_session("test-agent", session_id="session-lifecycle")
    await state_manager.set_current_project(
        str(project["name"]),
        project,
        agent_id="test-agent",
        session_id="session-lifecycle",
    )
    execution: dict[str, object] = {
        "mode": "project",
        "session_id": "session-lifecycle",
        "stable_session_id": "session-lifecycle",
        "run_id": "run-lifecycle",
        "repo_root": str(project["root"]),
    }
    return project, architecture, storage, state_manager, execution


async def _preview_replace(test_agent: str) -> dict[str, object]:
    return await manage_docs(
        action="replace_text",
        doc="architecture",
        metadata={
            "find": "before-value",
            "replace": "after-value-private-intent",
        },
        dry_run=True,
        agent=test_agent,
    )


async def _issue_retained_replace(
    *,
    storage: SQLiteStorage,
    project: dict[str, object],
    architecture: Path,
    execution: dict[str, object],
    test_agent: str,
):
    before_bytes = architecture.read_bytes()
    after_bytes = before_bytes.replace(b"before-value", b"after-value-private-intent")
    resolved = architecture.resolve()
    service = ApplyPreviewService(storage)
    return await service.issue(
        action="replace_text",
        normalized_intent={
            "action": "replace_text",
            "metadata": {
                "find": "before-value",
                "replace": "after-value-private-intent",
            },
            "doc_name": "architecture",
        },
        binding=ApplyPreviewBinding(
            principal_id=test_agent,
            session_id=str(execution["session_id"]),
            run_id=str(execution["run_id"]),
            project_key=str(project["project_key"]),
            repo_id=str(project["repo_id"]),
            repo_root=str(project["root"]),
            targets=(
                MutationLockTarget(repo_root=str(project["root"]), path=resolved),
            ),
            target_binding={"doc": "architecture"},
        ),
        precondition={
            "paths": [
                {
                    "path": str(resolved),
                    "exists": True,
                    "sha256": hashlib.sha256(before_bytes).hexdigest(),
                }
            ]
        },
        predicted_after={
            "paths": [
                {
                    "path": str(resolved),
                    "exists": True,
                    "sha256": hashlib.sha256(after_bytes).hexdigest(),
                }
            ]
        },
    )


async def test_public_preview_issues_exact_affordance_only_for_eligible_mutation(
    tmp_path: Path, test_agent: str
) -> None:
    project, architecture, storage, state_manager, execution = await _lifecycle_setup(
        tmp_path
    )
    try:
        with _isolated_runtime(state_manager, storage, project, execution):
            ineligible = await manage_docs(
                action="quality_check",
                doc="architecture",
                dry_run=True,
                agent=test_agent,
            )
            preview = await _preview_replace(test_agent)

            assert "apply" not in ineligible
            assert preview["ok"] is True
            assert "apply" in preview, preview.get("warnings")
            assert preview["apply"].keys() == {"action", "receipt", "expires_at"}
            assert preview["apply"]["action"] == "apply_preview"

        assert architecture.read_text(encoding="utf-8") == (
            "# Architecture\n\nbefore-value\n"
        )
    finally:
        await storage.close()


async def test_public_receipt_only_apply_replays_without_leaking_bearer_or_intent(
    tmp_path: Path,
    test_agent: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    project, architecture, storage, state_manager, execution = await _lifecycle_setup(
        tmp_path
    )
    caplog.set_level(logging.INFO)
    try:
        with _isolated_runtime(state_manager, storage, project, execution):
            affordance = await _issue_retained_replace(
                storage=storage,
                project=project,
                architecture=architecture,
                execution=execution,
                test_agent=test_agent,
            )
            receipt = affordance.receipt

            applied = await manage_docs(
                action="apply_preview",
                metadata={"receipt": receipt},
                agent=test_agent,
            )
            replayed = await manage_docs(
                action="apply_preview",
                metadata={"receipt": receipt},
                agent=test_agent,
            )

        assert architecture.read_text(encoding="utf-8") == (
            "# Architecture\n\nafter-value-private-intent\n"
        )
        assert applied["code"] == "APPLY_RECEIPT_APPLIED"
        assert applied["replayed"] is False
        assert replayed["code"] == "APPLY_RECEIPT_REPLAYED"
        assert replayed["replayed"] is True

        public_and_logs = (
            json.dumps([applied, replayed], sort_keys=True)
            + "\n"
            + "\n".join(record.getMessage() for record in caplog.records)
        )
        assert receipt not in public_and_logs
        assert "after-value-private-intent" not in public_and_logs
        assert str(architecture) not in public_and_logs
    finally:
        await storage.close()


async def test_public_lifecycle_fails_closed_for_scope_mismatch_and_target_drift(
    tmp_path: Path, test_agent: str
) -> None:
    project, architecture, storage, state_manager, execution = await _lifecycle_setup(
        tmp_path
    )
    try:
        with _isolated_runtime(state_manager, storage, project, execution):
            identity_affordance = await _issue_retained_replace(
                storage=storage,
                project=project,
                architecture=architecture,
                execution=execution,
                test_agent=test_agent,
            )
            identity_receipt = identity_affordance.receipt
            execution["run_id"] = "different-run"
            identity_denied = await manage_docs(
                action="apply_preview",
                metadata={"receipt": identity_receipt},
                agent=test_agent,
            )
            assert identity_denied["code"] == "APPLY_RECEIPT_SCOPE_MISMATCH"
            assert "before-value" in architecture.read_text(encoding="utf-8")

            execution["run_id"] = "run-lifecycle"
            drift_affordance = await _issue_retained_replace(
                storage=storage,
                project=project,
                architecture=architecture,
                execution=execution,
                test_agent=test_agent,
            )
            drift_receipt = drift_affordance.receipt
            architecture.write_text(
                "# Architecture\n\nintruder-change\n", encoding="utf-8"
            )
            drift_denied = await manage_docs(
                action="apply_preview",
                metadata={"receipt": drift_receipt},
                agent=test_agent,
            )

        assert drift_denied["code"] == "APPLY_RECEIPT_TARGET_DRIFT"
        assert architecture.read_text(encoding="utf-8") == (
            "# Architecture\n\nintruder-change\n"
        )
    finally:
        await storage.close()


async def test_public_rehome_receipt_applies_immutable_binding_once_and_replays(
    tmp_path: Path, test_agent: str
) -> None:
    project, architecture, storage, state_manager, execution = await _lifecycle_setup(
        tmp_path
    )
    target = Path(str(project["docs_dir"])) / "archive" / "ARCHITECTURE_GUIDE.md"
    try:
        with _isolated_runtime(state_manager, storage, project, execution):
            preview = await manage_docs(
                action="rehome_doc",
                doc="architecture",
                metadata={
                    "target_project": "lifecycle",
                    "target_relative_path": "archive/ARCHITECTURE_GUIDE.md",
                },
                dry_run=True,
                agent=test_agent,
            )
            receipt = preview["apply"]["receipt"]
            record = await storage.fetch_apply_preview_receipt(
                hashlib.sha256(receipt.encode("ascii")).hexdigest()
            )
            assert record is not None
            stored_binding = json.loads(record.target_binding_json)["target"]["rehome"]
            immutable_binding = RehomeCompositeBinding.from_storage_payload(
                stored_binding
            )
            source_record = await runtime._load_project_record(  # noqa: SLF001
                project_name=immutable_binding.source_project,
                server_module=server_module,
            )
            target_record = await runtime._load_project_record(  # noqa: SLF001
                project_name=immutable_binding.target_project,
                server_module=server_module,
            )
            initial_state = runtime.classify_rehome_transaction_state(  # noqa: SLF001
                immutable_binding,
                source_project=source_record,
                target_project=target_record,
            )
            assert initial_state == "BEFORE", {
                "source": {
                    key: source_record.get(key)
                    for key in ("name", "root", "docs_dir", "project_key", "repo_id")
                },
                "target": {
                    key: target_record.get(key)
                    for key in ("name", "root", "docs_dir", "project_key", "repo_id")
                },
            }
            applied = await manage_docs(
                action="apply_preview",
                metadata={"receipt": receipt},
                agent=test_agent,
            )
            replayed = await manage_docs(
                action="apply_preview",
                metadata={"receipt": receipt},
                agent=test_agent,
            )

        assert applied["code"] == "APPLY_RECEIPT_APPLIED"
        assert replayed["code"] == "APPLY_RECEIPT_REPLAYED"
        assert not architecture.exists()
        assert target.read_text(encoding="utf-8") == "# Architecture\n\nbefore-value\n"
    finally:
        await storage.close()


async def test_public_rehome_receipt_rejects_registry_and_index_drift_before_mutation(
    tmp_path: Path, test_agent: str
) -> None:
    project, architecture, storage, state_manager, execution = await _lifecycle_setup(
        tmp_path
    )
    docs_dir = Path(str(project["docs_dir"]))
    review_index = docs_dir / "REVIEW_INDEX.md"
    review_index.write_text("# Review Index\n", encoding="utf-8")

    async def _preview() -> str:
        preview = await manage_docs(
            action="rehome_doc",
            doc="architecture",
            metadata={
                "target_project": "lifecycle",
                "target_relative_path": "archive/ARCHITECTURE_GUIDE.md",
            },
            dry_run=True,
            agent=test_agent,
        )
        return str(preview["apply"]["receipt"])

    try:
        with _isolated_runtime(state_manager, storage, project, execution):
            registry_receipt = await _preview()
            drifted_docs = dict(project["docs"])
            drifted_docs["contradictory"] = str(docs_dir / "CONTRADICTORY.md")
            await storage.update_project_docs(
                "lifecycle",
                json.dumps(drifted_docs),
                repo_root=str(project["root"]),
            )
            registry_denied = await manage_docs(
                action="apply_preview",
                metadata={"receipt": registry_receipt},
                agent=test_agent,
            )

            await storage.update_project_docs(
                "lifecycle",
                json.dumps(project["docs"]),
                repo_root=str(project["root"]),
            )
            index_receipt = await _preview()
            review_index.write_text("attacker index drift\n", encoding="utf-8")
            index_denied = await manage_docs(
                action="apply_preview",
                metadata={"receipt": index_receipt},
                agent=test_agent,
            )

            review_index.write_text("# Review Index\n", encoding="utf-8")
            authority_receipt = await _preview()
            original_loader = runtime._load_project_record  # noqa: SLF001

            async def _contradictory_authority(**kwargs):
                record = await original_loader(**kwargs)
                return {**record, "root": str(tmp_path / "contradictory-root")}

            with patch.object(
                runtime, "_load_project_record", _contradictory_authority
            ):
                authority_denied = await manage_docs(
                    action="apply_preview",
                    metadata={"receipt": authority_receipt},
                    agent=test_agent,
                )

        assert registry_denied["code"] == "APPLY_RECEIPT_TARGET_DRIFT"
        assert index_denied["code"] == "APPLY_RECEIPT_TARGET_DRIFT"
        assert authority_denied["code"] == "APPLY_RECEIPT_TARGET_DRIFT"
        assert architecture.is_file()
        assert not (docs_dir / "archive" / "ARCHITECTURE_GUIDE.md").exists()
    finally:
        await storage.close()


async def test_public_rehome_receipt_recovers_partial_crash_exactly_once(
    tmp_path: Path, test_agent: str
) -> None:
    project, architecture, storage, state_manager, execution = await _lifecycle_setup(
        tmp_path
    )
    target = Path(str(project["docs_dir"])) / "archive" / "ARCHITECTURE_GUIDE.md"
    original_service = runtime.ApplyPreviewService
    original_operation = runtime._apply_rehome_mutation_steps  # noqa: SLF001
    operation_calls = 0

    async def _crash_once(**kwargs):
        nonlocal operation_calls
        operation_calls += 1
        if operation_calls == 1:
            kwargs["target_path"].parent.mkdir(parents=True, exist_ok=True)
            kwargs["target_path"].write_bytes(kwargs["source_path"].read_bytes())
            raise RuntimeError("simulated crash after destination durability")
        return await original_operation(**kwargs)

    try:
        with (
            _isolated_runtime(state_manager, storage, project, execution),
            patch.object(
                runtime,
                "ApplyPreviewService",
                side_effect=lambda backend: original_service(
                    backend, claim_lease_seconds=1
                ),
            ),
            patch.object(runtime, "_apply_rehome_mutation_steps", _crash_once),
        ):
            preview = await manage_docs(
                action="rehome_doc",
                doc="architecture",
                metadata={
                    "target_project": "lifecycle",
                    "target_relative_path": "archive/ARCHITECTURE_GUIDE.md",
                },
                dry_run=True,
                agent=test_agent,
            )
            receipt = preview["apply"]["receipt"]
            partial = await manage_docs(
                action="apply_preview",
                metadata={"receipt": receipt},
                agent=test_agent,
            )
            await asyncio.sleep(1.1)
            recovered = await manage_docs(
                action="apply_preview",
                metadata={"receipt": receipt},
                agent=test_agent,
            )
            replayed = await manage_docs(
                action="apply_preview",
                metadata={"receipt": receipt},
                agent=test_agent,
            )

        assert partial["code"] == "APPLY_RECEIPT_RECOVERY_REQUIRED"
        assert recovered["code"] == "APPLY_RECEIPT_APPLIED", {
            "operation_calls": operation_calls,
            "source_exists": architecture.exists(),
            "target_exists": target.exists(),
        }
        assert replayed["code"] == "APPLY_RECEIPT_REPLAYED"
        assert operation_calls == 2
        assert not architecture.exists()
        assert target.read_text(encoding="utf-8") == "# Architecture\n\nbefore-value\n"
    finally:
        await storage.close()


def _rehome_binding(root: Path, source: Path, target: Path) -> RehomeCompositeBinding:
    return RehomeCompositeBinding(
        source_project="source",
        target_project="target",
        source_repo_root=str(root),
        target_repo_root=str(root),
        source_docs_dir=str(root / "source-docs"),
        target_docs_dir=str(root / "target-docs"),
        source_doc_keys=("architecture",),
        target_doc_key="architecture",
        source_path=str(source),
        target_path=str(target),
        move=True,
        overwrite=False,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        target_sha256=None,
        source_registry_digest="source-registry",
        target_registry_digest="target-registry",
        index_paths=(),
    )


async def test_composite_rehome_partial_crash_recovers_once_and_unknown_state_stops(
    tmp_path: Path, test_agent: str
) -> None:
    assert test_agent == "test-agent"
    root = tmp_path / "rehome"
    root.mkdir()
    source = root / "source.md"
    target = root / "target.md"
    source.write_text("bound-content", encoding="utf-8")
    binding = _rehome_binding(root, source, target)

    async def _crash_after_copy() -> dict[str, object]:
        target.write_bytes(source.read_bytes())
        raise RuntimeError("simulated crash after destination durability")

    partial = await execute_rehome_transaction(binding, operation=_crash_after_copy)
    assert partial == {
        "ok": False,
        "code": "APPLY_RECEIPT_RECOVERY_REQUIRED",
        "recovery_state": "PARTIAL",
    }
    assert source.is_file() and target.is_file()

    recovery_calls = 0

    async def _finish_move() -> dict[str, object]:
        nonlocal recovery_calls
        recovery_calls += 1
        source.unlink()
        return {"ok": True, "moved": True}

    recovered = await recover_rehome_transaction(binding, operation=_finish_move)
    assert recovered == {"ok": True, "moved": True}
    assert recovery_calls == 1
    assert not source.exists()
    assert target.read_text(encoding="utf-8") == "bound-content"

    async def _must_not_reexecute() -> dict[str, object]:
        raise AssertionError("terminal AFTER state must replay without execution")

    replay = await recover_rehome_transaction(binding, operation=_must_not_reexecute)
    assert replay == {"ok": True, "code": "APPLY_RECEIPT_REPLAYED", "replayed": True}

    unknown_source = root / "unknown-source.md"
    unknown_target = root / "unknown-target.md"
    unknown_source.write_text("expected", encoding="utf-8")
    unknown_binding = _rehome_binding(root, unknown_source, unknown_target)
    unknown_target.write_text("unexpected", encoding="utf-8")
    operation_called = False

    async def _unsafe_operation() -> dict[str, object]:
        nonlocal operation_called
        operation_called = True
        return {"ok": True}

    stopped = await recover_rehome_transaction(
        unknown_binding, operation=_unsafe_operation
    )
    assert stopped == {
        "ok": False,
        "code": "APPLY_RECEIPT_RECOVERY_REQUIRED",
        "recovery_state": "OTHER",
    }
    assert operation_called is False
