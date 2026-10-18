"""Atomic SQLite persistence for apply-preview receipts."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from scribe_mcp.storage.models import (
    APPLY_PREVIEW_RESULT_CODES,
    ApplyPreviewClaimResult,
    ApplyPreviewReceiptRecord,
)


InitialiseFn = Callable[[], Awaitable[None]]
FetchOneFn = Callable[[str, tuple[Any, ...]], Awaitable[sqlite3.Row | None]]
FetchAllFn = Callable[[str, tuple[Any, ...]], Awaitable[list[sqlite3.Row]]]

_RECEIPT_COLUMNS = """
token_sha256, receipt_version, state, principal_id, session_id, run_id,
project_key, repo_id, action, normalized_intent_json, target_binding_json,
precondition_json, predicted_after_json, issued_at, expires_at, fence,
apply_lease_expires_at, terminal_result_code, terminal_result_json, terminal_at,
audit_correlation_id, updated_at
"""


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _decode_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _decode_receipt(row: sqlite3.Row) -> ApplyPreviewReceiptRecord:
    return ApplyPreviewReceiptRecord(
        token_sha256=row["token_sha256"],
        receipt_version=row["receipt_version"],
        state=row["state"],
        principal_id=row["principal_id"],
        session_id=row["session_id"],
        run_id=row["run_id"],
        project_key=row["project_key"],
        repo_id=row["repo_id"],
        action=row["action"],
        normalized_intent_json=row["normalized_intent_json"],
        target_binding_json=row["target_binding_json"],
        precondition_json=row["precondition_json"],
        predicted_after_json=row["predicted_after_json"],
        issued_at=datetime.fromisoformat(row["issued_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        fence=row["fence"],
        apply_lease_expires_at=_decode_datetime(row["apply_lease_expires_at"]),
        terminal_result_code=row["terminal_result_code"],
        terminal_result_json=row["terminal_result_json"],
        terminal_at=_decode_datetime(row["terminal_at"]),
        audit_correlation_id=row["audit_correlation_id"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _validate_token_sha256(token_sha256: str) -> None:
    if (
        not isinstance(token_sha256, str)
        or len(token_sha256) != 64
        or any(character not in "0123456789abcdef" for character in token_sha256)
    ):
        raise ValueError("token_sha256 must be exactly 64 lowercase hexadecimal characters")


async def issue_apply_preview_receipt(
    *,
    initialise_fn: InitialiseFn,
    write_lock: asyncio.Lock,
    fetchone_fn: FetchOneFn,
    record: ApplyPreviewReceiptRecord,
) -> ApplyPreviewReceiptRecord:
    await initialise_fn()
    async with write_lock:
        row = await fetchone_fn(
            f"""
            INSERT INTO apply_preview_receipts ({_RECEIPT_COLUMNS})
            VALUES ({", ".join("?" for _ in range(22))})
            RETURNING {_RECEIPT_COLUMNS};
            """,
            (
                record.token_sha256,
                record.receipt_version,
                record.state,
                record.principal_id,
                record.session_id,
                record.run_id,
                record.project_key,
                record.repo_id,
                record.action,
                record.normalized_intent_json,
                record.target_binding_json,
                record.precondition_json,
                record.predicted_after_json,
                _utc_iso(record.issued_at),
                _utc_iso(record.expires_at),
                record.fence,
                _utc_iso(record.apply_lease_expires_at)
                if record.apply_lease_expires_at is not None
                else None,
                record.terminal_result_code,
                record.terminal_result_json,
                _utc_iso(record.terminal_at) if record.terminal_at is not None else None,
                record.audit_correlation_id,
                _utc_iso(record.updated_at),
            ),
        )
    if row is None:
        raise RuntimeError("SQLite did not return the issued apply-preview receipt")
    return _decode_receipt(row)


async def fetch_apply_preview_receipt(
    *,
    initialise_fn: InitialiseFn,
    fetchone_fn: FetchOneFn,
    token_sha256: str,
) -> ApplyPreviewReceiptRecord | None:
    _validate_token_sha256(token_sha256)
    await initialise_fn()
    row = await fetchone_fn(
        f"SELECT {_RECEIPT_COLUMNS} FROM apply_preview_receipts WHERE token_sha256 = ?;",
        (token_sha256,),
    )
    return _decode_receipt(row) if row is not None else None


async def claim_apply_preview_receipt(
    *,
    initialise_fn: InitialiseFn,
    write_lock: asyncio.Lock,
    fetchone_fn: FetchOneFn,
    token_sha256: str,
    lease_seconds: int,
) -> ApplyPreviewClaimResult:
    _validate_token_sha256(token_sha256)
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds < 1:
        raise ValueError("lease_seconds must be a positive integer")
    await initialise_fn()
    now = datetime.now(timezone.utc)
    now_iso = _utc_iso(now)
    lease_expires_iso = _utc_iso(now + timedelta(seconds=lease_seconds))
    async with write_lock:
        row = await fetchone_fn(
            f"""
            UPDATE apply_preview_receipts
            SET state = 'applying',
                fence = fence + 1,
                apply_lease_expires_at = ?,
                updated_at = ?
            WHERE token_sha256 = ?
              AND expires_at > ?
              AND (
                  state = 'issued'
                  OR (
                      state = 'applying'
                      AND apply_lease_expires_at IS NOT NULL
                      AND apply_lease_expires_at <= ?
                  )
              )
            RETURNING {_RECEIPT_COLUMNS};
            """,
            (lease_expires_iso, now_iso, token_sha256, now_iso, now_iso),
        )

    if row is not None:
        record = _decode_receipt(row)
        return ApplyPreviewClaimResult(
            status="claimed" if record.fence == 1 else "recovery",
            record=record,
        )

    record = await fetch_apply_preview_receipt(
        initialise_fn=initialise_fn,
        fetchone_fn=fetchone_fn,
        token_sha256=token_sha256,
    )
    if record is None:
        return ApplyPreviewClaimResult(status="not_found")
    if record.state in {"applied", "failed_terminal"}:
        return ApplyPreviewClaimResult(status="terminal", record=record)
    if record.expires_at <= now:
        return ApplyPreviewClaimResult(status="expired", record=record)
    return ApplyPreviewClaimResult(status="busy", record=record)


async def finalize_apply_preview_receipt(
    *,
    initialise_fn: InitialiseFn,
    write_lock: asyncio.Lock,
    fetchone_fn: FetchOneFn,
    token_sha256: str,
    fence: int,
    terminal_state: str,
    result_code: str,
    result_json: str,
) -> ApplyPreviewReceiptRecord:
    _validate_token_sha256(token_sha256)
    if not isinstance(fence, int) or isinstance(fence, bool) or fence < 1:
        raise ValueError("fence must be a positive integer")
    if terminal_state not in {"applied", "failed_terminal"}:
        raise ValueError("terminal_state must be applied or failed_terminal")
    if result_code not in APPLY_PREVIEW_RESULT_CODES:
        raise ValueError("result_code is not a recognized apply-preview result code")
    if not isinstance(result_json, str) or not result_json:
        raise ValueError("result_json must be a non-empty string")

    await initialise_fn()
    now_iso = _utc_iso(datetime.now(timezone.utc))
    async with write_lock:
        row = await fetchone_fn(
            f"""
            UPDATE apply_preview_receipts
            SET state = ?,
                apply_lease_expires_at = NULL,
                terminal_result_code = ?,
                terminal_result_json = ?,
                terminal_at = ?,
                updated_at = ?
            WHERE token_sha256 = ?
              AND state = 'applying'
              AND fence = ?
            RETURNING {_RECEIPT_COLUMNS};
            """,
            (
                terminal_state,
                result_code,
                result_json,
                now_iso,
                now_iso,
                token_sha256,
                fence,
            ),
        )
    if row is None:
        raise LookupError("apply-preview receipt has no active fenced claim")
    return _decode_receipt(row)


async def cleanup_apply_preview_receipts(
    *,
    initialise_fn: InitialiseFn,
    write_lock: asyncio.Lock,
    fetchall_fn: FetchAllFn,
) -> int:
    await initialise_fn()
    now_iso = _utc_iso(datetime.now(timezone.utc))
    async with write_lock:
        rows = await fetchall_fn(
            """
            DELETE FROM apply_preview_receipts
            WHERE token_sha256 IN (
                SELECT token_sha256
                FROM apply_preview_receipts
                WHERE expires_at <= ? AND state != 'applying'
                ORDER BY expires_at, token_sha256
                LIMIT 100
            )
            RETURNING token_sha256;
            """,
            (now_iso,),
        )
    return len(rows)
