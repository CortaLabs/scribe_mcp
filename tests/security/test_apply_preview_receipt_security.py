"""Security regression coverage for apply-preview bearer receipts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.doc_management.apply_preview import ApplyPreviewBinding, ApplyPreviewService
from scribe_mcp.doc_management.manager import MutationLockTarget
from scribe_mcp.storage.models import ApplyPreviewClaimResult, ApplyPreviewReceiptRecord


pytestmark = [pytest.mark.core, pytest.mark.asyncio]


class MemoryReceiptStorage:
    def __init__(self) -> None:
        self.records: dict[str, ApplyPreviewReceiptRecord] = {}
        self.claim_calls = 0
        self._gate = asyncio.Lock()

    async def issue_apply_preview_receipt(self, record):
        self.records[record.token_sha256] = record
        return record

    async def fetch_apply_preview_receipt(self, token_sha256):
        return self.records.get(token_sha256)

    async def claim_apply_preview_receipt(self, token_sha256, *, lease_seconds):
        async with self._gate:
            self.claim_calls += 1
            record = self.records[token_sha256]
            now = datetime.now(timezone.utc)
            applying = replace(
                record,
                state="applying",
                fence=record.fence + 1,
                apply_lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
            self.records[token_sha256] = applying
            return ApplyPreviewClaimResult(status="claimed", record=applying)

    async def finalize_apply_preview_receipt(
        self, token_sha256, *, fence, terminal_state, result_code, result_json
    ):
        record = self.records[token_sha256]
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

    async def authorize_apply_preview(self, *, execution_context, binding):
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
        self.current = self.after
        return {"ok": True}


def _context(root: Path, **overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "principal_id": "principal-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "project_key": "project-1",
        "repo_id": "repo-1",
        "repo_root": str(root),
        "agent": "untrusted-attribution",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _service(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    storage = MemoryReceiptStorage()
    service = ApplyPreviewService(storage)
    binding = ApplyPreviewBinding(
        principal_id="principal-1",
        session_id="session-1",
        run_id="run-1",
        project_key="project-1",
        repo_id="repo-1",
        repo_root=str(root),
        targets=(MutationLockTarget(repo_root=str(root), path=root / "private.md"),),
        target_binding={"absolute_path": str(root / "private.md")},
    )
    affordance = await service.issue(
        action="replace_section",
        normalized_intent={"content": "TOP-SECRET-CONTENT"},
        binding=binding,
        precondition={"sha256": "before-secret-hash"},
        predicted_after={"sha256": "after-secret-hash"},
    )
    return root, storage, service, affordance, binding


async def test_wrong_verified_scope_fails_before_claim_or_executor(tmp_path: Path) -> None:
    root, storage, service, affordance, _ = await _service(tmp_path)
    executor = Executor(initial={"sha256": "before-secret-hash"}, after={"sha256": "after-secret-hash"})

    mismatches = (
        {"principal_id": "other-principal", "agent": "principal-1"},
        {"session_id": "other-session"},
        {"run_id": "other-run"},
        {"project_key": "other-project"},
        {"repo_id": "other-repo"},
        {"repo_root": str(tmp_path / "other-repo-root")},
    )
    for mismatch in mismatches:
        result = await service.apply(
            receipt=affordance.receipt,
            execution_context=_context(root, **mismatch),
            executor=executor,
        )
        assert result == {
            "ok": False,
            "code": "APPLY_RECEIPT_SCOPE_MISMATCH",
            "replayed": False,
        }
    assert storage.claim_calls == 0
    assert executor.execute_calls == 0


async def test_receipt_apply_rejects_companion_mutation_fields_before_lookup(tmp_path: Path) -> None:
    root, storage, service, affordance, _ = await _service(tmp_path)
    executor = Executor(initial={"sha256": "before-secret-hash"}, after={"sha256": "after-secret-hash"})

    with pytest.raises(TypeError):
        await service.apply(  # type: ignore[call-arg]
            receipt=affordance.receipt,
            execution_context=_context(root),
            executor=executor,
            normalized_intent={"content": "attacker-controlled"},
        )

    assert storage.claim_calls == 0
    assert executor.execute_calls == 0


async def test_current_policy_denial_never_executes_or_claims(tmp_path: Path) -> None:
    root, storage, service, affordance, _ = await _service(tmp_path)
    executor = Executor(initial={"sha256": "before-secret-hash"}, after={"sha256": "after-secret-hash"})
    executor.authorized = False

    result = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )

    assert result["code"] == "APPLY_RECEIPT_POLICY_DENIED"
    assert storage.claim_calls == 0
    assert executor.execute_calls == 0


async def test_repr_logs_and_public_results_redact_bearer_intent_and_paths(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root, storage, service, affordance, binding = await _service(tmp_path)
    executor = Executor(initial={"sha256": "before-secret-hash"}, after={"sha256": "after-secret-hash"})

    result = await service.apply(
        receipt=affordance.receipt, execution_context=_context(root), executor=executor
    )
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    combined = repr((service, affordance, binding, next(iter(storage.records.values())), result, rendered))

    assert affordance.receipt not in combined
    assert "TOP-SECRET-CONTENT" not in combined
    assert str(root / "private.md") not in combined
    assert "before-secret-hash" not in combined
    assert "after-secret-hash" not in combined
    assert "principal-1" not in combined


async def test_malformed_and_unknown_receipts_are_detail_normalized(tmp_path: Path) -> None:
    root, _, service, _, _ = await _service(tmp_path)
    executor = Executor(initial={"sha256": "before-secret-hash"}, after={"sha256": "after-secret-hash"})

    malformed = await service.apply(receipt="not-a-token", execution_context=_context(root), executor=executor)
    unknown = await service.apply(receipt="A" * 43, execution_context=_context(root), executor=executor)

    assert malformed == unknown == {
        "ok": False,
        "code": "APPLY_RECEIPT_INVALID",
        "replayed": False,
    }
    assert executor.execute_calls == 0
