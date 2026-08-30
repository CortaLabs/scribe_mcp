"""Hermetic contract coverage for the server-only apply-preview engine."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.doc_management.apply_preview import (
    ApplyPreviewBinding,
    ApplyPreviewService,
)
from scribe_mcp.doc_management.manager import MutationLockTarget, document_mutation_locks
from scribe_mcp.storage.models import ApplyPreviewClaimResult, ApplyPreviewReceiptRecord


pytestmark = [pytest.mark.core, pytest.mark.asyncio]


class MemoryReceiptStorage:
    def __init__(self) -> None:
        self.records: dict[str, ApplyPreviewReceiptRecord] = {}
        self._gate = asyncio.Lock()
        self.claim_calls = 0
        self.fail_fetch = False
        self.reject_finalize = False
        self.fail_finalize = False

    async def issue_apply_preview_receipt(
        self, record: ApplyPreviewReceiptRecord
    ) -> ApplyPreviewReceiptRecord:
        self.records[record.token_sha256] = record
        return record

    async def fetch_apply_preview_receipt(
        self, token_sha256: str
    ) -> ApplyPreviewReceiptRecord | None:
        if self.fail_fetch:
            raise RuntimeError("database unavailable with private details")
        return self.records.get(token_sha256)

    async def claim_apply_preview_receipt(
        self, token_sha256: str, *, lease_seconds: int
    ) -> ApplyPreviewClaimResult:
        async with self._gate:
            self.claim_calls += 1
            record = self.records.get(token_sha256)
            if record is None:
                return ApplyPreviewClaimResult(status="not_found")
            now = datetime.now(timezone.utc)
            if record.state in {"applied", "failed_terminal"}:
                return ApplyPreviewClaimResult(status="terminal", record=record)
            if record.expires_at <= now:
                return ApplyPreviewClaimResult(status="expired", record=record)
            if record.state == "applying" and record.apply_lease_expires_at is not None:
                if record.apply_lease_expires_at > now:
                    return ApplyPreviewClaimResult(status="busy", record=record)
                status = "recovery"
            else:
                status = "claimed"
            applying = replace(
                record,
                state="applying",
                fence=record.fence + 1,
                apply_lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
            self.records[token_sha256] = applying
            return ApplyPreviewClaimResult(status=status, record=applying)

    async def finalize_apply_preview_receipt(
        self,
        token_sha256: str,
        *,
        fence: int,
        terminal_state: str,
        result_code: str,
        result_json: str,
    ) -> ApplyPreviewReceiptRecord:
        async with self._gate:
            if self.fail_finalize:
                raise RuntimeError("database unavailable with private details")
            record = self.records[token_sha256]
            if self.reject_finalize or record.state != "applying" or record.fence != fence:
                raise LookupError("no active fenced claim")
            now = datetime.now(timezone.utc)
            terminal = replace(
                record,
                state=terminal_state,
                apply_lease_expires_at=None,
                terminal_result_code=result_code,
                terminal_result_json=result_json,
                terminal_at=now,
                updated_at=now,
            )
            self.records[token_sha256] = terminal
            return terminal


class Executor:
    def __init__(self, *, initial: dict[str, object], after: dict[str, object]) -> None:
        self.current = initial
        self.after = after
        self.execute_calls = 0
        self.authorized = True
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False
        self.seen_intent: dict[str, object] | None = None

    async def authorize_apply_preview(self, *, execution_context, binding) -> bool:
        return self.authorized

    async def resolve_apply_preview_targets(self, *, execution_context, binding):
        return tuple(
            MutationLockTarget(repo_root=item["repo_root"], path=item["path"])
            for item in binding["targets"]
        )

    async def inspect_apply_preview_state(self, *, execution_context, binding):
        return self.current

    async def execute_retained_intent(
        self, *, action, normalized_intent, execution_context, binding, fence
    ):
        self.execute_calls += 1
        self.seen_intent = dict(normalized_intent)
        self.entered.set()
        if self.block:
            await self.release.wait()
        self.current = self.after
        return {"ok": True, "private_path": "/must/not/escape"}


def _context(root: Path, **overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "principal_id": "principal-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "project_key": "project-1",
        "repo_id": "repo-1",
        "repo_root": str(root),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _binding(root: Path) -> ApplyPreviewBinding:
    return ApplyPreviewBinding(
        principal_id="principal-1",
        session_id="session-1",
        run_id="run-1",
        project_key="project-1",
        repo_id="repo-1",
        repo_root=str(root),
        targets=(MutationLockTarget(repo_root=str(root), path=root / "DOC.md"),),
        target_binding={"doc_key": "doc"},
    )


async def _issued(tmp_path: Path, *, ttl_seconds: int = 600):
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    storage = MemoryReceiptStorage()
    service = ApplyPreviewService(storage, ttl_seconds=ttl_seconds)
    affordance = await service.issue(
        action="replace_section",
        normalized_intent={"content": "retained-secret", "section": "alpha"},
        binding=_binding(root),
        precondition={"sha256": "before"},
        predicted_after={"sha256": "after"},
    )
    return root, storage, service, affordance


async def test_issue_uses_opaque_digest_only_and_caps_ttl(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    storage = MemoryReceiptStorage()
    service = ApplyPreviewService(storage, ttl_seconds=9999, max_ttl_seconds=9999)

    affordance = await service.issue(
        action="replace_section",
        normalized_intent={"content": "retained-secret"},
        binding=_binding(root),
        precondition={"sha256": "before"},
        predicted_after={"sha256": "after"},
    )

    assert affordance.action == "apply_preview"
    assert len(affordance.receipt) == 43
    assert affordance.receipt not in repr(affordance)
    assert len(storage.records) == 1
    record = next(iter(storage.records.values()))
    assert record.token_sha256 != affordance.receipt
    assert affordance.receipt not in repr(record)
    assert record.expires_at - record.issued_at == timedelta(seconds=1800)


async def test_two_concurrent_applies_invoke_executor_at_most_once(tmp_path: Path) -> None:
    root, _, service, affordance = await _issued(tmp_path)
    executor = Executor(initial={"sha256": "before"}, after={"sha256": "after"})
    executor.block = True

    first = asyncio.create_task(
        service.apply(receipt=affordance.receipt, execution_context=_context(root), executor=executor)
    )
    await executor.entered.wait()
    second = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )
    executor.release.set()
    first_result = await first

    assert first_result == {
        "ok": True,
        "code": "APPLY_RECEIPT_APPLIED",
        "replayed": False,
        "audit_correlation_id": first_result["audit_correlation_id"],
    }
    assert second["code"] == "APPLY_RECEIPT_BUSY"
    assert executor.execute_calls == 1
    assert executor.seen_intent == {"content": "retained-secret", "section": "alpha"}


async def test_terminal_replay_returns_stored_safe_result_without_execution(tmp_path: Path) -> None:
    root, _, service, affordance = await _issued(tmp_path)
    executor = Executor(initial={"sha256": "before"}, after={"sha256": "after"})

    applied = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )
    replayed = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )

    assert applied["code"] == "APPLY_RECEIPT_APPLIED"
    assert replayed["code"] == "APPLY_RECEIPT_REPLAYED"
    assert replayed["replayed"] is True
    assert executor.execute_calls == 1
    assert "private_path" not in replayed


async def test_expired_lease_recovery_reconciles_after_state_without_execution(tmp_path: Path) -> None:
    root, storage, service, affordance = await _issued(tmp_path)
    digest = next(iter(storage.records))
    issued = storage.records[digest]
    storage.records[digest] = replace(
        issued,
        state="applying",
        fence=4,
        apply_lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    executor = Executor(initial={"sha256": "after"}, after={"sha256": "after"})

    result = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )

    assert result["code"] == "APPLY_RECEIPT_REPLAYED"
    assert result["replayed"] is True
    assert executor.execute_calls == 0
    assert storage.records[digest].fence == 5
    assert storage.records[digest].state == "applied"


async def test_expired_lease_recovery_resumes_once_from_bound_preimage(tmp_path: Path) -> None:
    root, storage, service, affordance = await _issued(tmp_path)
    digest = next(iter(storage.records))
    issued = storage.records[digest]
    storage.records[digest] = replace(
        issued,
        state="applying",
        fence=2,
        apply_lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    executor = Executor(initial={"sha256": "before"}, after={"sha256": "after"})

    result = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )

    assert result["code"] == "APPLY_RECEIPT_APPLIED"
    assert executor.execute_calls == 1
    assert storage.records[digest].fence == 3
    assert storage.records[digest].state == "applied"


async def test_expired_receipt_fails_before_claim_or_execution(tmp_path: Path) -> None:
    root, storage, service, affordance = await _issued(tmp_path)
    digest = next(iter(storage.records))
    issued = storage.records[digest]
    storage.records[digest] = replace(
        issued,
        issued_at=issued.issued_at - timedelta(hours=1),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        updated_at=issued.issued_at,
    )
    executor = Executor(initial={"sha256": "before"}, after={"sha256": "after"})

    result = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )

    assert result["code"] == "APPLY_RECEIPT_EXPIRED"
    assert storage.claim_calls == 0
    assert executor.execute_calls == 0


async def test_target_drift_and_stale_fence_fail_closed(tmp_path: Path) -> None:
    root, storage, service, affordance = await _issued(tmp_path)
    drifted = Executor(initial={"sha256": "other"}, after={"sha256": "after"})

    drift_result = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=drifted
    )
    assert drift_result["code"] == "APPLY_RECEIPT_TARGET_DRIFT"
    assert drifted.execute_calls == 0

    _, stale_storage, stale_service, stale_affordance = await _issued(tmp_path / "stale")
    stale_storage.reject_finalize = True
    executor = Executor(initial={"sha256": "before"}, after={"sha256": "after"})
    stale_result = await stale_service.apply(
        receipt=stale_affordance.receipt,
        execution_context=_context(tmp_path / "stale" / "repo"),
        executor=executor,
    )
    assert stale_result["code"] == "APPLY_RECEIPT_RECOVERY_REQUIRED"
    assert executor.execute_calls == 1


async def test_storage_unavailable_is_stable_and_non_mutating(tmp_path: Path) -> None:
    root, storage, service, affordance = await _issued(tmp_path)
    storage.fail_fetch = True
    executor = Executor(initial={"sha256": "before"}, after={"sha256": "after"})

    result = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )

    assert result == {
        "ok": False,
        "code": "APPLY_RECEIPT_STORAGE_UNAVAILABLE",
        "replayed": False,
    }
    assert executor.execute_calls == 0


async def test_finalize_storage_failure_is_distinct_from_stale_fence(tmp_path: Path) -> None:
    root, storage, service, affordance = await _issued(tmp_path)
    storage.fail_finalize = True
    executor = Executor(initial={"sha256": "before"}, after={"sha256": "after"})

    result = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )

    assert result["code"] == "APPLY_RECEIPT_STORAGE_UNAVAILABLE"
    assert executor.execute_calls == 1


async def test_document_mutation_locks_deduplicate_sort_and_reverse_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scribe_mcp.doc_management.manager as manager

    events: list[tuple[str, str]] = []

    async def acquire(path: Path):
        events.append(("acquire", path.name))
        return path

    async def release(handle: Path):
        events.append(("release", handle.name))

    monkeypatch.setattr(manager, "_acquire_mutation_lock", acquire)
    monkeypatch.setattr(manager, "_release_mutation_lock", release)
    targets = [
        MutationLockTarget(repo_root=str(tmp_path), path=tmp_path / "z.md"),
        MutationLockTarget(repo_root=str(tmp_path), path=tmp_path / "a.md"),
        MutationLockTarget(repo_root=str(tmp_path), path=tmp_path / "z.md"),
    ]

    async with document_mutation_locks(targets):
        assert [event[0] for event in events] == ["acquire", "acquire"]

    acquired = [name for operation, name in events if operation == "acquire"]
    released = [name for operation, name in events if operation == "release"]
    assert acquired == sorted(acquired)
    assert released == list(reversed(acquired))
