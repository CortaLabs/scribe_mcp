"""Host-neutral façade over durable background-receipt storage."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from scribe_mcp.background.models import (
    BackgroundAdmissionResultV1,
    BackgroundOperationIntentV1,
    BackgroundPartitionV1,
    BackgroundQueueLimitsV1,
    BackgroundRecoverySnapshotV1,
    BackgroundTransitionOutcomeV1,
    DurableOperationReceiptV1,
)
from scribe_mcp.storage.base import StorageBackend


def _require_aware_datetime(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_nonempty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_nonnegative_integer(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_integer(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


class BackgroundReceiptStoreV1:
    """Thin clock-injecting façade for the shared durable receipt contract."""

    def __init__(self, backend: StorageBackend, *, clock: Callable[[], datetime]) -> None:
        if not callable(clock):
            raise ValueError("clock must be callable")
        self._backend = backend
        self._clock = clock

    def _now(self) -> datetime:
        now = self._clock()
        _require_aware_datetime("clock result", now)
        return now

    async def admit(
        self,
        intent: BackgroundOperationIntentV1,
        limits: BackgroundQueueLimitsV1,
    ) -> BackgroundAdmissionResultV1:
        """Atomically persist or classify one admission attempt."""
        return await self._backend.admit_background_receipt(intent, limits, now=self._now())

    async def get(self, operation_id: str) -> DurableOperationReceiptV1 | None:
        """Fetch one durable receipt by operation ID."""
        _require_nonempty_string("operation_id", operation_id)
        return await self._backend.get_background_receipt(operation_id)

    async def claim(
        self,
        partition: BackgroundPartitionV1,
        worker_id: str,
        lease_ms: int,
    ) -> DurableOperationReceiptV1 | None:
        """Atomically lease the next eligible receipt in a partition."""
        _require_nonempty_string("worker_id", worker_id)
        _require_positive_integer("lease_ms", lease_ms)
        return await self._backend.claim_background_receipt(
            partition,
            worker_id,
            lease_ms,
            now=self._now(),
        )

    async def transition(
        self,
        operation_id: str,
        expected_state_version: int,
        fencing_token: int,
        outcome: BackgroundTransitionOutcomeV1,
    ) -> DurableOperationReceiptV1:
        """Apply one versioned and, when leased, fenced legal transition."""
        _require_nonempty_string("operation_id", operation_id)
        _require_positive_integer("expected_state_version", expected_state_version)
        _require_nonnegative_integer("fencing_token", fencing_token)
        return await self._backend.transition_background_receipt(
            operation_id,
            expected_state_version,
            fencing_token,
            outcome,
            now=self._now(),
        )

    async def recover(self, now: datetime) -> BackgroundRecoverySnapshotV1:
        """Read durable nonterminal receipts and reconstruct capacity accounting."""
        _require_aware_datetime("now", now)
        return await self._backend.recover_background_receipts(now)
