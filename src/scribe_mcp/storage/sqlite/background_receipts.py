"""Atomic SQLite persistence for generic background-operation receipts."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from scribe_mcp.background.models import (
    BACKGROUND_LEGAL_TRANSITIONS,
    BACKGROUND_NONTERMINAL_STATES,
    BackgroundAdmissionResultV1,
    BackgroundOperationIntentV1,
    BackgroundPartitionV1,
    BackgroundQueueLimitsV1,
    BackgroundReceiptNotFoundError,
    BackgroundRecoverySnapshotV1,
    BackgroundStaleFenceError,
    BackgroundStateVersionConflictError,
    BackgroundTransitionOutcomeV1,
    DurableOperationReceiptV1,
)


InitialiseFn = Callable[[], Awaitable[None]]
FetchOneFn = Callable[[str, tuple[Any, ...]], Awaitable[sqlite3.Row | None]]
FetchAllFn = Callable[[str, tuple[Any, ...]], Awaitable[list[sqlite3.Row]]]

_RECEIPT_COLUMNS = """operation_id, canonical_project_key, lane, idempotency_key,
payload_digest, payload_bytes, durability_class, state, state_version,
attempt_count, next_attempt_at, lease_owner, lease_expires_at, fencing_token,
cancel_requested, result_ref, error_code, created_at, updated_at"""
_NONTERMINAL_STATES = tuple(sorted(BACKGROUND_NONTERMINAL_STATES))
_NONTERMINAL_PLACEHOLDERS = ", ".join("?" for _ in _NONTERMINAL_STATES)


def _utc_iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _decode_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    decoded = datetime.fromisoformat(value)
    if decoded.tzinfo is None or decoded.utcoffset() is None:
        raise ValueError("stored receipt timestamp must be timezone-aware")
    return decoded


def _decode_receipt(row: sqlite3.Row) -> DurableOperationReceiptV1:
    return DurableOperationReceiptV1(
        operation_id=row["operation_id"],
        canonical_project_key=row["canonical_project_key"],
        lane=row["lane"],
        idempotency_key=row["idempotency_key"],
        payload_digest=row["payload_digest"],
        payload_bytes=int(row["payload_bytes"]),
        durability_class=row["durability_class"],
        state=row["state"],
        state_version=int(row["state_version"]),
        attempt_count=int(row["attempt_count"]),
        next_attempt_at=_decode_datetime(row["next_attempt_at"]),
        lease_owner=row["lease_owner"],
        lease_expires_at=_decode_datetime(row["lease_expires_at"]),
        fencing_token=int(row["fencing_token"]),
        cancel_requested=bool(row["cancel_requested"]),
        result_ref=row["result_ref"],
        error_code=row["error_code"],
        created_at=_decode_datetime(row["created_at"]),
        updated_at=_decode_datetime(row["updated_at"]),
    )


def _admission_result(
    status: str, receipt: DurableOperationReceiptV1 | None, limits: BackgroundQueueLimitsV1
) -> BackgroundAdmissionResultV1:
    return BackgroundAdmissionResultV1(
        status=status, receipt=receipt, retry_after_ms=limits.retry_after_ms if status == "busy" else None
    )


async def admit_background_receipt(
    *,
    initialise_fn: InitialiseFn,
    write_lock: asyncio.Lock,
    fetchone_fn: FetchOneFn,
    intent: BackgroundOperationIntentV1,
    limits: BackgroundQueueLimitsV1,
    now: datetime,
) -> BackgroundAdmissionResultV1:
    """Insert only when all capacity predicates hold in the same SQLite write."""
    await initialise_fn()
    async with write_lock:
        existing = await fetchone_fn(
            f"SELECT {_RECEIPT_COLUMNS} FROM background_receipts "
            "WHERE canonical_project_key = ? AND idempotency_key = ?;",
            (intent.canonical_project_key, intent.idempotency_key),
        )
        if existing is not None:
            receipt = _decode_receipt(existing)
            if receipt.payload_digest == intent.payload_digest:
                return _admission_result("duplicate", receipt, limits)
            return _admission_result("digest_conflict", None, limits)

        row = await fetchone_fn(
            f"""
            INSERT INTO background_receipts ({_RECEIPT_COLUMNS})
            SELECT ?, ?, ?, ?, ?, ?, ?, 'accepted', 1, 0, NULL, NULL, NULL, 0,
                   0, NULL, NULL, ?, ?
            WHERE ? = 1
              AND (SELECT COUNT(*) FROM background_receipts
                   WHERE state IN ({_NONTERMINAL_PLACEHOLDERS})) < ?
              AND (SELECT COALESCE(SUM(payload_bytes), 0) FROM background_receipts
                   WHERE state IN ({_NONTERMINAL_PLACEHOLDERS})) + ? <= ?
              AND (SELECT COUNT(*) FROM background_receipts
                   WHERE canonical_project_key = ?
                     AND state IN ({_NONTERMINAL_PLACEHOLDERS})) < ?
              AND (SELECT COALESCE(SUM(payload_bytes), 0) FROM background_receipts
                   WHERE canonical_project_key = ?
                     AND state IN ({_NONTERMINAL_PLACEHOLDERS})) + ? <= ?
            ON CONFLICT(canonical_project_key, idempotency_key) DO NOTHING
            RETURNING {_RECEIPT_COLUMNS};
            """,
            (
                intent.operation_id,
                intent.canonical_project_key,
                intent.lane,
                intent.idempotency_key,
                intent.payload_digest,
                intent.payload_bytes,
                intent.durability_class,
                _utc_iso(intent.created_at),
                _utc_iso(now),
                int(limits.accepting),
                *_NONTERMINAL_STATES,
                limits.max_pending_items,
                *_NONTERMINAL_STATES,
                intent.payload_bytes,
                limits.max_pending_bytes,
                intent.canonical_project_key,
                *_NONTERMINAL_STATES,
                limits.max_project_pending_items,
                intent.canonical_project_key,
                *_NONTERMINAL_STATES,
                intent.payload_bytes,
                limits.max_project_pending_bytes,
            ),
        )
        if row is not None:
            return _admission_result("accepted", _decode_receipt(row), limits)

        # A concurrent insert may have won the idempotency key after the first read.
        existing = await fetchone_fn(
            f"SELECT {_RECEIPT_COLUMNS} FROM background_receipts "
            "WHERE canonical_project_key = ? AND idempotency_key = ?;",
            (intent.canonical_project_key, intent.idempotency_key),
        )
        if existing is not None:
            receipt = _decode_receipt(existing)
            if receipt.payload_digest == intent.payload_digest:
                return _admission_result("duplicate", receipt, limits)
            return _admission_result("digest_conflict", None, limits)
        if not limits.accepting:
            return _admission_result("shutting_down", None, limits)
        return _admission_result("busy", None, limits)


async def get_background_receipt(
    *, initialise_fn: InitialiseFn, fetchone_fn: FetchOneFn, operation_id: str
) -> DurableOperationReceiptV1 | None:
    await initialise_fn()
    row = await fetchone_fn(
        f"SELECT {_RECEIPT_COLUMNS} FROM background_receipts WHERE operation_id = ?;",
        (operation_id,),
    )
    return _decode_receipt(row) if row is not None else None


async def claim_background_receipt(
    *,
    initialise_fn: InitialiseFn,
    write_lock: asyncio.Lock,
    fetchone_fn: FetchOneFn,
    partition: BackgroundPartitionV1,
    worker_id: str,
    lease_ms: int,
    now: datetime,
) -> DurableOperationReceiptV1 | None:
    await initialise_fn()
    now_text = _utc_iso(now)
    expires_text = _utc_iso(now + timedelta(milliseconds=lease_ms))
    async with write_lock:
        row = await fetchone_fn(
            f"""
            WITH candidate AS (
                SELECT operation_id FROM background_receipts
                WHERE canonical_project_key = ? AND lane = ?
                  AND (state = 'ready'
                       OR (state = 'retry_wait' AND next_attempt_at <= ?)
                       OR (state = 'leased' AND lease_expires_at <= ?))
                ORDER BY created_at ASC, operation_id ASC
                LIMIT 1
            )
            UPDATE background_receipts
            SET state = 'leased', state_version = state_version + 1,
                attempt_count = attempt_count + 1, fencing_token = fencing_token + 1,
                next_attempt_at = NULL, lease_owner = ?, lease_expires_at = ?, updated_at = ?
            WHERE operation_id = (SELECT operation_id FROM candidate)
              AND canonical_project_key = ? AND lane = ?
              AND (state = 'ready'
                   OR (state = 'retry_wait' AND next_attempt_at <= ?)
                   OR (state = 'leased' AND lease_expires_at <= ?))
            RETURNING {_RECEIPT_COLUMNS};
            """,
            (
                partition.canonical_project_key,
                partition.lane,
                now_text,
                now_text,
                worker_id,
                expires_text,
                now_text,
                partition.canonical_project_key,
                partition.lane,
                now_text,
                now_text,
            ),
        )
    return _decode_receipt(row) if row is not None else None


async def transition_background_receipt(
    *,
    initialise_fn: InitialiseFn,
    write_lock: asyncio.Lock,
    fetchone_fn: FetchOneFn,
    operation_id: str,
    expected_state_version: int,
    fencing_token: int,
    outcome: BackgroundTransitionOutcomeV1,
    now: datetime,
) -> DurableOperationReceiptV1:
    await initialise_fn()
    async with write_lock:
        current = await fetchone_fn(
            f"SELECT {_RECEIPT_COLUMNS} FROM background_receipts WHERE operation_id = ?;",
            (operation_id,),
        )
        if current is None:
            raise BackgroundReceiptNotFoundError(operation_id)
        current_receipt = _decode_receipt(current)
        if current_receipt.state_version != expected_state_version:
            raise BackgroundStateVersionConflictError(operation_id)
        if current_receipt.fencing_token != fencing_token:
            raise BackgroundStaleFenceError(operation_id)
        if outcome.state not in BACKGROUND_LEGAL_TRANSITIONS[current_receipt.state]:
            raise ValueError(
                f"illegal background receipt transition: {current_receipt.state} -> {outcome.state}"
            )
        legal_source_states = tuple(
            sorted(
                source_state
                for source_state, legal_targets in BACKGROUND_LEGAL_TRANSITIONS.items()
                if outcome.state in legal_targets
            )
        )
        if not legal_source_states:
            raise ValueError(f"illegal background receipt target state: {outcome.state}")
        legal_state_placeholders = ", ".join("?" for _ in legal_source_states)

        row = await fetchone_fn(
            f"""
            UPDATE background_receipts
            SET state = ?, state_version = state_version + 1,
                next_attempt_at = ?, lease_owner = NULL, lease_expires_at = NULL,
                cancel_requested = ?, result_ref = ?, error_code = ?, updated_at = ?
            WHERE operation_id = ? AND state_version = ? AND fencing_token = ?
              AND state IN ({legal_state_placeholders})
            RETURNING {_RECEIPT_COLUMNS};
            """,
            (
                outcome.state,
                _utc_iso(outcome.next_attempt_at) if outcome.next_attempt_at is not None else None,
                int(outcome.cancel_requested),
                outcome.result_ref,
                outcome.error_code,
                _utc_iso(now),
                operation_id,
                expected_state_version,
                fencing_token,
                *legal_source_states,
            ),
        )
        if row is not None:
            return _decode_receipt(row)

        current = await fetchone_fn(
            f"SELECT {_RECEIPT_COLUMNS} FROM background_receipts WHERE operation_id = ?;",
            (operation_id,),
        )
        if current is None:
            raise BackgroundReceiptNotFoundError(operation_id)
        current_receipt = _decode_receipt(current)
        if current_receipt.state_version != expected_state_version:
            raise BackgroundStateVersionConflictError(operation_id)
        if current_receipt.fencing_token != fencing_token:
            raise BackgroundStaleFenceError(operation_id)
        raise ValueError("background receipt transition was rejected by its state predicate")


async def recover_background_receipts(
    *, initialise_fn: InitialiseFn, fetchall_fn: FetchAllFn, now: datetime
) -> BackgroundRecoverySnapshotV1:
    await initialise_fn()
    now_text = _utc_iso(now)
    rows = await fetchall_fn(
        f"""
        SELECT {_RECEIPT_COLUMNS} FROM background_receipts
        WHERE state IN ({_NONTERMINAL_PLACEHOLDERS})
        ORDER BY created_at ASC, operation_id ASC;
        """,
        _NONTERMINAL_STATES,
    )
    receipts = tuple(_decode_receipt(row) for row in rows)
    reclaimable = tuple(
        receipt.operation_id
        for receipt in receipts
        if receipt.state == "leased"
        and receipt.lease_expires_at is not None
        and _utc_iso(receipt.lease_expires_at) <= now_text
    )
    return BackgroundRecoverySnapshotV1(
        receipts=receipts,
        pending_items=len(receipts),
        pending_bytes=sum(receipt.payload_bytes for receipt in receipts),
        reclaimable_operation_ids=reclaimable,
    )
