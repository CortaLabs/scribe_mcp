from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from scribe_mcp.storage.models import ApplyPreviewReceiptRecord
from scribe_mcp.storage.sqlite import SQLiteStorage


pytestmark = [pytest.mark.core, pytest.mark.asyncio]


def _receipt(
    token_sha256: str,
    *,
    now: datetime,
    state: str = "issued",
    fence: int = 0,
    expires_at: datetime | None = None,
    apply_lease_expires_at: datetime | None = None,
) -> ApplyPreviewReceiptRecord:
    return ApplyPreviewReceiptRecord(
        token_sha256=token_sha256,
        receipt_version=1,
        state=state,
        principal_id="principal-1",
        session_id="session-1",
        run_id="run-1",
        project_key="project-1",
        repo_id="repo-1",
        action="replace_section",
        normalized_intent_json='{"section":"findings"}',
        target_binding_json='{"doc":"ARCHITECTURE_GUIDE"}',
        precondition_json='{"sha256":"before"}',
        predicted_after_json='{"sha256":"after"}',
        issued_at=now,
        expires_at=expires_at or now + timedelta(minutes=10),
        fence=fence,
        apply_lease_expires_at=apply_lease_expires_at,
        terminal_result_code=None,
        terminal_result_json=None,
        terminal_at=None,
        audit_correlation_id="audit-1",
        updated_at=now,
    )


@pytest_asyncio.fixture
async def storage(tmp_path):
    backend = SQLiteStorage(tmp_path / "scribe.db")
    await backend.setup()
    try:
        yield backend
    finally:
        await backend.close()


async def test_issue_fetch_and_schema_persist_only_bearer_digest(storage, tmp_path) -> None:
    now = datetime.now(timezone.utc)
    record = _receipt("a" * 64, now=now)

    assert await storage.issue_apply_preview_receipt(record) == record
    assert await storage.fetch_apply_preview_receipt(record.token_sha256) == record

    connection = sqlite3.connect(tmp_path / "scribe.db")
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(apply_preview_receipts)")}
        persisted = connection.execute(
            "SELECT token_sha256 FROM apply_preview_receipts WHERE token_sha256 = ?",
            (record.token_sha256,),
        ).fetchone()
    finally:
        connection.close()

    assert persisted == (record.token_sha256,)
    assert "token_sha256" in columns
    assert not ({"token", "receipt", "bearer", "bearer_token"} & columns)


async def test_concurrent_claim_has_one_owner_and_monotonic_fence(tmp_path) -> None:
    db_path = tmp_path / "scribe.db"
    first = SQLiteStorage(db_path)
    second = SQLiteStorage(db_path)
    await first.setup()
    await second.setup()
    try:
        record = _receipt("b" * 64, now=datetime.now(timezone.utc))
        await first.issue_apply_preview_receipt(record)

        results = await asyncio.gather(
            first.claim_apply_preview_receipt(record.token_sha256, lease_seconds=60),
            second.claim_apply_preview_receipt(record.token_sha256, lease_seconds=60),
        )

        assert sorted(result.status for result in results) == ["busy", "claimed"]
        owner = next(result for result in results if result.status == "claimed")
        assert owner.record is not None
        assert owner.record.state == "applying"
        assert owner.record.fence == 1
    finally:
        await asyncio.gather(first.close(), second.close())


async def test_expired_apply_lease_is_recovered_with_larger_fence(storage) -> None:
    now = datetime.now(timezone.utc)
    record = _receipt(
        "c" * 64,
        now=now - timedelta(minutes=2),
        state="applying",
        fence=4,
        expires_at=now + timedelta(minutes=8),
        apply_lease_expires_at=now - timedelta(seconds=1),
    )
    await storage.issue_apply_preview_receipt(record)

    result = await storage.claim_apply_preview_receipt(record.token_sha256, lease_seconds=60)

    assert result.status == "recovery"
    assert result.record is not None
    assert result.record.state == "applying"
    assert result.record.fence == 5
    assert result.record.apply_lease_expires_at is not None
    assert result.record.apply_lease_expires_at > now


async def test_finalize_requires_current_fence_and_terminal_rows_replay(storage) -> None:
    record = _receipt("d" * 64, now=datetime.now(timezone.utc))
    await storage.issue_apply_preview_receipt(record)
    claim = await storage.claim_apply_preview_receipt(record.token_sha256, lease_seconds=60)
    assert claim.record is not None

    with pytest.raises(LookupError, match="active fenced claim"):
        await storage.finalize_apply_preview_receipt(
            record.token_sha256,
            fence=claim.record.fence + 1,
            terminal_state="applied",
            result_code="APPLY_RECEIPT_APPLIED",
            result_json='{"ok":true}',
        )

    terminal = await storage.finalize_apply_preview_receipt(
        record.token_sha256,
        fence=claim.record.fence,
        terminal_state="applied",
        result_code="APPLY_RECEIPT_APPLIED",
        result_json='{"ok":true}',
    )
    replay = await storage.claim_apply_preview_receipt(record.token_sha256, lease_seconds=60)

    assert terminal.state == "applied"
    assert terminal.apply_lease_expires_at is None
    assert terminal.terminal_result_json == '{"ok":true}'
    assert replay.status == "terminal"
    assert replay.record == terminal


async def test_expiry_and_cleanup_are_fail_closed_and_bounded(storage) -> None:
    now = datetime.now(timezone.utc)
    for index in range(105):
        issued_at = now - timedelta(hours=2)
        await storage.issue_apply_preview_receipt(
            _receipt(
                f"{index:064x}",
                now=issued_at,
                expires_at=now - timedelta(hours=1),
            )
        )

    applying = _receipt(
        "f" * 64,
        now=now - timedelta(hours=2),
        state="applying",
        fence=1,
        expires_at=now - timedelta(hours=1),
        apply_lease_expires_at=now - timedelta(minutes=30),
    )
    await storage.issue_apply_preview_receipt(applying)
    nonexpired = _receipt("9" * 64, now=now)
    await storage.issue_apply_preview_receipt(nonexpired)

    expired = await storage.claim_apply_preview_receipt(f"{0:064x}", lease_seconds=60)
    assert expired.status == "expired"
    assert await storage.cleanup_apply_preview_receipts() == 100
    assert await storage.cleanup_apply_preview_receipts() == 5
    assert await storage.cleanup_apply_preview_receipts() == 0
    assert await storage.fetch_apply_preview_receipt(applying.token_sha256) == applying
    assert await storage.fetch_apply_preview_receipt(nonexpired.token_sha256) == nonexpired


async def test_duplicate_issue_and_storage_errors_do_not_fall_back(storage, monkeypatch) -> None:
    record = _receipt("e" * 64, now=datetime.now(timezone.utc))
    await storage.issue_apply_preview_receipt(record)

    with pytest.raises(sqlite3.IntegrityError):
        await storage.issue_apply_preview_receipt(replace(record, action="append"))

    async def _fail(*args, **kwargs):
        raise sqlite3.OperationalError("forced storage failure")

    monkeypatch.setattr(storage, "_fetchone", _fail)
    with pytest.raises(sqlite3.OperationalError, match="forced storage failure"):
        await storage.fetch_apply_preview_receipt(record.token_sha256)
