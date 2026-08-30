"""Contract tests for durable apply-preview receipt persistence."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone

import pytest

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.storage.models import ApplyPreviewClaimResult, ApplyPreviewReceiptRecord


def _receipt(**overrides: object) -> ApplyPreviewReceiptRecord:
    issued_at = datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc)
    values: dict[str, object] = {
        "token_sha256": "a" * 64,
        "receipt_version": 1,
        "state": "issued",
        "principal_id": "principal-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "project_key": "project-1",
        "repo_id": "repo-1",
        "action": "replace_section",
        "normalized_intent_json": '{"content":"secret"}',
        "target_binding_json": '{"path":"/private/document.md"}',
        "precondition_json": '{"sha256":"before"}',
        "predicted_after_json": '{"sha256":"after"}',
        "issued_at": issued_at,
        "expires_at": issued_at + timedelta(minutes=10),
        "fence": 0,
        "apply_lease_expires_at": None,
        "terminal_result_code": None,
        "terminal_result_json": None,
        "terminal_at": None,
        "audit_correlation_id": "audit-1",
        "updated_at": issued_at,
    }
    values.update(overrides)
    return ApplyPreviewReceiptRecord(**values)  # type: ignore[arg-type]


def test_receipt_record_has_only_hashed_bearer_and_redacted_repr() -> None:
    record = _receipt()
    field_names = {field.name for field in fields(record)}

    assert "token_sha256" in field_names
    assert "token" not in field_names
    assert "receipt" not in field_names
    assert "secret" not in repr(record)
    assert "/private/document.md" not in repr(record)

    with pytest.raises(FrozenInstanceError):
        record.state = "applying"  # type: ignore[misc]


@pytest.mark.parametrize("token_sha256", ["a" * 63, "A" * 64, "g" * 64, "plaintext-token"])
def test_receipt_record_rejects_noncanonical_token_hash(token_sha256: str) -> None:
    with pytest.raises(ValueError, match="token_sha256"):
        _receipt(token_sha256=token_sha256)


@pytest.mark.parametrize("state", ["pending", "failed", "replayed", ""])
def test_receipt_record_rejects_open_ended_lifecycle_states(state: str) -> None:
    with pytest.raises(ValueError, match="state"):
        _receipt(state=state)


@pytest.mark.parametrize("status", ["pending", "failed", "replayed", ""])
def test_claim_result_rejects_open_ended_statuses(status: str) -> None:
    with pytest.raises(ValueError, match="status"):
        ApplyPreviewClaimResult(status=status, record=None)  # type: ignore[arg-type]


def test_receipt_record_enforces_terminal_state_contract() -> None:
    terminal_at = datetime(2026, 8, 30, 19, 1, tzinfo=timezone.utc)
    terminal = _receipt(
        state="applied",
        fence=1,
        terminal_result_code="APPLY_RECEIPT_APPLIED",
        terminal_result_json='{"ok":true}',
        terminal_at=terminal_at,
        updated_at=terminal_at,
    )
    assert terminal.state == "applied"

    with pytest.raises(ValueError, match="terminal"):
        _receipt(state="applied", fence=1)
    with pytest.raises(ValueError, match="terminal_result_code"):
        _receipt(
            state="failed_terminal",
            fence=1,
            terminal_result_code="UNREGISTERED_RESULT",
            terminal_result_json='{"ok":false}',
            terminal_at=terminal_at,
            updated_at=terminal_at,
        )


def test_storage_backend_receipt_signatures_are_exact() -> None:
    assert str(inspect.signature(StorageBackend.issue_apply_preview_receipt)) == (
        "(self, record: 'ApplyPreviewReceiptRecord') -> 'ApplyPreviewReceiptRecord'"
    )
    assert str(inspect.signature(StorageBackend.fetch_apply_preview_receipt)) == (
        "(self, token_sha256: 'str') -> 'ApplyPreviewReceiptRecord | None'"
    )
    assert str(inspect.signature(StorageBackend.claim_apply_preview_receipt)) == (
        "(self, token_sha256: 'str', *, lease_seconds: 'int') -> 'ApplyPreviewClaimResult'"
    )
    assert str(inspect.signature(StorageBackend.finalize_apply_preview_receipt)) == (
        "(self, token_sha256: 'str', *, fence: 'int', terminal_state: 'str', "
        "result_code: 'str', result_json: 'str') -> 'ApplyPreviewReceiptRecord'"
    )
    assert str(inspect.signature(StorageBackend.cleanup_apply_preview_receipts)) == "(self) -> 'int'"


def test_storage_backend_receipt_methods_fail_closed_by_default() -> None:
    backend = object()
    record = _receipt()

    async def exercise() -> None:
        with pytest.raises(NotImplementedError):
            await StorageBackend.issue_apply_preview_receipt(backend, record)  # type: ignore[arg-type]
        with pytest.raises(NotImplementedError):
            await StorageBackend.fetch_apply_preview_receipt(backend, "a" * 64)  # type: ignore[arg-type]
        with pytest.raises(NotImplementedError):
            await StorageBackend.claim_apply_preview_receipt(  # type: ignore[arg-type]
                backend, "a" * 64, lease_seconds=30
            )
        with pytest.raises(NotImplementedError):
            await StorageBackend.finalize_apply_preview_receipt(  # type: ignore[arg-type]
                backend,
                "a" * 64,
                fence=1,
                terminal_state="applied",
                result_code="APPLY_RECEIPT_APPLIED",
                result_json='{"ok":true}',
            )
        with pytest.raises(NotImplementedError):
            await StorageBackend.cleanup_apply_preview_receipts(backend)  # type: ignore[arg-type]

    asyncio.run(exercise())
