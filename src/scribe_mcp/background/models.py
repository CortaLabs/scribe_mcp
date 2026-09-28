"""Host-neutral models for durable background-operation receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


BackgroundReceiptState = Literal[
    "accepted",
    "ready",
    "leased",
    "retry_wait",
    "succeeded",
    "failed_terminal",
    "cancelled",
]
BackgroundLane = Literal["control", "durable", "heavy"]
BackgroundAdmissionStatus = Literal[
    "accepted",
    "duplicate",
    "digest_conflict",
    "busy",
    "shutting_down",
]

BACKGROUND_RECEIPT_STATES = frozenset(
    {
        "accepted",
        "ready",
        "leased",
        "retry_wait",
        "succeeded",
        "failed_terminal",
        "cancelled",
    }
)
BACKGROUND_LANES = frozenset({"control", "durable", "heavy"})
BACKGROUND_ADMISSION_STATUSES = frozenset(
    {"accepted", "duplicate", "digest_conflict", "busy", "shutting_down"}
)
BACKGROUND_NONTERMINAL_STATES = frozenset({"accepted", "ready", "leased", "retry_wait"})
BACKGROUND_TERMINAL_STATES = frozenset({"succeeded", "failed_terminal", "cancelled"})
BACKGROUND_LEGAL_TRANSITIONS = {
    "accepted": frozenset({"ready", "cancelled"}),
    "ready": frozenset({"leased", "cancelled"}),
    "leased": frozenset({"retry_wait", "succeeded", "failed_terminal", "cancelled"}),
    "retry_wait": frozenset({"leased", "cancelled"}),
    "succeeded": frozenset(),
    "failed_terminal": frozenset(),
    "cancelled": frozenset(),
}


def _require_nonempty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_nonempty_string(name: str, value: str | None) -> None:
    if value is not None:
        _require_nonempty_string(name, value)


def _require_aware_datetime(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_optional_aware_datetime(name: str, value: datetime | None) -> None:
    if value is not None:
        _require_aware_datetime(name, value)


def _require_nonnegative_integer(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_integer(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _require_sha256(name: str, value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be exactly 64 lowercase hexadecimal characters")


@dataclass(frozen=True)
class BackgroundOperationIntentV1:
    """Validated admission intent for one logical background operation."""

    operation_id: str
    canonical_project_key: str
    lane: BackgroundLane
    idempotency_key: str
    payload_digest: str
    payload_bytes: int
    durability_class: str
    created_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "canonical_project_key",
            "idempotency_key",
            "durability_class",
        ):
            _require_nonempty_string(name, getattr(self, name))
        if self.lane not in BACKGROUND_LANES:
            raise ValueError(f"lane must be one of {sorted(BACKGROUND_LANES)}")
        _require_sha256("payload_digest", self.payload_digest)
        _require_nonnegative_integer("payload_bytes", self.payload_bytes)
        _require_aware_datetime("created_at", self.created_at)


@dataclass(frozen=True)
class BackgroundQueueLimitsV1:
    """Atomic global and per-project receipt admission limits."""

    max_pending_items: int
    max_pending_bytes: int
    max_project_pending_items: int
    max_project_pending_bytes: int
    retry_after_ms: int
    accepting: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_pending_items",
            "max_pending_bytes",
            "max_project_pending_items",
            "max_project_pending_bytes",
            "retry_after_ms",
        ):
            _require_positive_integer(name, getattr(self, name))
        if not isinstance(self.accepting, bool):
            raise ValueError("accepting must be a boolean")


@dataclass(frozen=True)
class DurableOperationReceiptV1:
    """Durable state for one admitted background operation."""

    operation_id: str
    canonical_project_key: str
    lane: BackgroundLane
    idempotency_key: str
    payload_digest: str
    payload_bytes: int
    durability_class: str
    state: BackgroundReceiptState
    state_version: int
    attempt_count: int
    next_attempt_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    fencing_token: int
    cancel_requested: bool
    result_ref: str | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "canonical_project_key",
            "idempotency_key",
            "durability_class",
        ):
            _require_nonempty_string(name, getattr(self, name))
        if self.lane not in BACKGROUND_LANES:
            raise ValueError(f"lane must be one of {sorted(BACKGROUND_LANES)}")
        if self.state not in BACKGROUND_RECEIPT_STATES:
            raise ValueError(f"state must be one of {sorted(BACKGROUND_RECEIPT_STATES)}")
        _require_sha256("payload_digest", self.payload_digest)
        _require_nonnegative_integer("payload_bytes", self.payload_bytes)
        _require_positive_integer("state_version", self.state_version)
        _require_nonnegative_integer("attempt_count", self.attempt_count)
        _require_nonnegative_integer("fencing_token", self.fencing_token)
        if self.attempt_count != self.fencing_token:
            raise ValueError("attempt_count and fencing_token must advance together")
        if not isinstance(self.cancel_requested, bool):
            raise ValueError("cancel_requested must be a boolean")
        for name in ("next_attempt_at", "lease_expires_at"):
            _require_optional_aware_datetime(name, getattr(self, name))
        for name in ("lease_owner", "result_ref", "error_code"):
            _require_optional_nonempty_string(name, getattr(self, name))
        _require_aware_datetime("created_at", self.created_at)
        _require_aware_datetime("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")

        if (self.lease_owner is None) != (self.lease_expires_at is None):
            raise ValueError("lease_owner and lease_expires_at must be set together")

        if self.state == "accepted":
            if self.state_version != 1 or self.attempt_count != 0 or self.fencing_token != 0:
                raise ValueError(
                    "accepted state requires state_version 1, attempt_count 0, and fencing_token 0"
                )
            if self.cancel_requested:
                raise ValueError("accepted state cannot have cancellation requested")
        elif self.state == "ready":
            if self.state_version < 2:
                raise ValueError("ready state requires at least state_version 2")
            if self.attempt_count != 0 or self.fencing_token != 0:
                raise ValueError("ready state requires attempt_count 0 and fencing_token 0")
            if self.cancel_requested:
                raise ValueError("ready state cannot have cancellation requested")
        elif self.state in {"leased", "retry_wait", "succeeded", "failed_terminal"}:
            if self.attempt_count < 1 or self.fencing_token < 1:
                raise ValueError(f"{self.state} state requires a positive attempt count and fence")
            minimum_state_version = 3 if self.state == "leased" else 4
            if self.state_version < minimum_state_version:
                raise ValueError(
                    f"{self.state} state requires at least state_version {minimum_state_version}"
                )
        elif self.state == "cancelled" and self.state_version < 2:
            raise ValueError("cancelled state requires at least state_version 2")

        if self.state == "leased":
            if self.lease_owner is None:
                raise ValueError("leased state requires a lease owner and expiry")
        elif self.lease_owner is not None:
            raise ValueError("only leased state may contain lease fields")

        if self.state == "retry_wait":
            if self.next_attempt_at is None:
                raise ValueError("retry_wait state requires next_attempt_at")
        elif self.next_attempt_at is not None:
            raise ValueError("only retry_wait state may contain next_attempt_at")

        if self.state == "succeeded":
            if self.result_ref is None or self.error_code is not None:
                raise ValueError("succeeded state requires result_ref and forbids error_code")
        elif self.state == "failed_terminal":
            if self.error_code is None or self.result_ref is not None:
                raise ValueError("failed_terminal state requires error_code and forbids result_ref")
        elif self.result_ref is not None or self.error_code is not None:
            raise ValueError("only matching terminal states may contain result or error fields")


@dataclass(frozen=True)
class BackgroundAdmissionResultV1:
    """Typed, non-exceptional outcome of one atomic admission attempt."""

    status: BackgroundAdmissionStatus
    receipt: DurableOperationReceiptV1 | None
    retry_after_ms: int | None

    def __post_init__(self) -> None:
        if self.status not in BACKGROUND_ADMISSION_STATUSES:
            raise ValueError(f"status must be one of {sorted(BACKGROUND_ADMISSION_STATUSES)}")
        if self.receipt is not None and not isinstance(self.receipt, DurableOperationReceiptV1):
            raise ValueError("receipt must be a DurableOperationReceiptV1 or None")
        if self.retry_after_ms is not None:
            _require_positive_integer("retry_after_ms", self.retry_after_ms)

        if self.status in {"accepted", "duplicate"}:
            if self.receipt is None or self.retry_after_ms is not None:
                raise ValueError(f"{self.status} requires a receipt and no retry delay")
            if self.status == "accepted" and self.receipt.state != "accepted":
                raise ValueError("accepted admission requires an accepted receipt")
        elif self.status == "busy":
            if self.receipt is not None or self.retry_after_ms is None:
                raise ValueError("busy requires a retry delay and no receipt")
        elif self.receipt is not None or self.retry_after_ms is not None:
            raise ValueError(f"{self.status} forbids a receipt and retry delay")


@dataclass(frozen=True)
class BackgroundPartitionV1:
    """Canonical project and lane partition used for claiming work."""

    canonical_project_key: str
    lane: BackgroundLane

    def __post_init__(self) -> None:
        _require_nonempty_string("canonical_project_key", self.canonical_project_key)
        if self.lane not in BACKGROUND_LANES:
            raise ValueError(f"lane must be one of {sorted(BACKGROUND_LANES)}")


@dataclass(frozen=True)
class BackgroundTransitionOutcomeV1:
    """Requested non-claim mutation of a durable receipt."""

    state: BackgroundReceiptState
    next_attempt_at: datetime | None = None
    cancel_requested: bool = False
    result_ref: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in BACKGROUND_RECEIPT_STATES:
            raise ValueError(f"state must be one of {sorted(BACKGROUND_RECEIPT_STATES)}")
        if self.state in {"accepted", "leased"}:
            raise ValueError("transition outcomes cannot enter accepted or leased state")
        _require_optional_aware_datetime("next_attempt_at", self.next_attempt_at)
        _require_optional_nonempty_string("result_ref", self.result_ref)
        _require_optional_nonempty_string("error_code", self.error_code)
        if not isinstance(self.cancel_requested, bool):
            raise ValueError("cancel_requested must be a boolean")

        if self.state == "retry_wait":
            if self.next_attempt_at is None:
                raise ValueError("retry_wait outcome requires next_attempt_at")
        elif self.next_attempt_at is not None:
            raise ValueError("only retry_wait outcome may contain next_attempt_at")
        if self.state == "ready" and self.cancel_requested:
            raise ValueError("ready outcome cannot have cancellation requested")

        if self.state == "succeeded":
            if self.result_ref is None or self.error_code is not None:
                raise ValueError("succeeded outcome requires result_ref and forbids error_code")
        elif self.state == "failed_terminal":
            if self.error_code is None or self.result_ref is not None:
                raise ValueError(
                    "failed_terminal outcome requires error_code and forbids result_ref"
                )
        elif self.result_ref is not None or self.error_code is not None:
            raise ValueError("only matching terminal outcomes may contain result or error fields")


@dataclass(frozen=True)
class BackgroundRecoverySnapshotV1:
    """Read-only reconstruction of durable nonterminal receipt capacity."""

    receipts: tuple[DurableOperationReceiptV1, ...]
    pending_items: int
    pending_bytes: int
    reclaimable_operation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.receipts, tuple):
            raise ValueError("receipts must be a tuple")
        if not isinstance(self.reclaimable_operation_ids, tuple):
            raise ValueError("reclaimable_operation_ids must be a tuple")
        _require_nonnegative_integer("pending_items", self.pending_items)
        _require_nonnegative_integer("pending_bytes", self.pending_bytes)

        operation_ids: set[str] = set()
        leased_operation_ids: set[str] = set()
        for receipt in self.receipts:
            if not isinstance(receipt, DurableOperationReceiptV1):
                raise ValueError("receipts must contain DurableOperationReceiptV1 values")
            if receipt.state not in BACKGROUND_NONTERMINAL_STATES:
                raise ValueError("recovery receipts must be nonterminal")
            if receipt.operation_id in operation_ids:
                raise ValueError("recovery receipts must have unique operation IDs")
            operation_ids.add(receipt.operation_id)
            if receipt.state == "leased":
                leased_operation_ids.add(receipt.operation_id)

        if self.pending_items != len(self.receipts):
            raise ValueError("pending_items must equal the number of recovery receipts")
        if self.pending_bytes != sum(receipt.payload_bytes for receipt in self.receipts):
            raise ValueError("pending_bytes must equal the recovery receipt payload-byte total")

        reclaimable_ids: set[str] = set()
        for operation_id in self.reclaimable_operation_ids:
            _require_nonempty_string("reclaimable_operation_id", operation_id)
            if operation_id in reclaimable_ids:
                raise ValueError("reclaimable operation IDs must be unique")
            reclaimable_ids.add(operation_id)
        if not reclaimable_ids <= leased_operation_ids:
            raise ValueError("reclaimable operation IDs must identify leased recovery receipts")


class BackgroundReceiptNotFoundError(RuntimeError):
    """Raised when a requested receipt does not exist."""


class BackgroundStateVersionConflictError(RuntimeError):
    """Raised when a receipt mutation loses its state-version compare-and-swap."""


class BackgroundStaleFenceError(RuntimeError):
    """Raised when a leased receipt mutation presents an obsolete fencing token."""
