"""Public-safe affected-row referential inventory reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

STATUS_PASS = "PASS"
STATUS_BLOCK = "BLOCK"
REDACTION_GUARD_PASS = "REDACTION_GUARD_PASS"
REDACTION_GUARD_BLOCK = "REDACTION_GUARD_BLOCK"

INVENTORY_NO_AFFECTED_ROWS = "INVENTORY_NO_AFFECTED_ROWS"
INVENTORY_REPAIR_NOT_REQUIRED = "INVENTORY_REPAIR_NOT_REQUIRED"
INVENTORY_MUTATION_CANDIDATE_REQUIRES_CUSTODY_AND_REHEARSAL = (
    "INVENTORY_MUTATION_CANDIDATE_REQUIRES_CUSTODY_AND_REHEARSAL"
)

BLOCKED_READONLY_AUTHORITY_MISSING = "BLOCKED_READONLY_AUTHORITY_MISSING"
BLOCKED_TARGET_IDENTITY_AMBIGUOUS = "BLOCKED_TARGET_IDENTITY_AMBIGUOUS"
BLOCKED_TARGET_BINDING_UNPROVEN = "BLOCKED_TARGET_BINDING_UNPROVEN"
BLOCKED_REFERENTIAL_INVENTORY_INCOMPLETE = "BLOCKED_REFERENTIAL_INVENTORY_INCOMPLETE"
BLOCKED_LOW_CARDINALITY_OR_PRIVATE_RISK = "BLOCKED_LOW_CARDINALITY_OR_PRIVATE_RISK"
BLOCKED_PUBLIC_SAFE_OUTPUT_CONTRACT_UNPROVEN = "BLOCKED_PUBLIC_SAFE_OUTPUT_CONTRACT_UNPROVEN"
BLOCKED_STORAGE_BACKEND_UNAVAILABLE = "BLOCKED_STORAGE_BACKEND_UNAVAILABLE"
BLOCKED_PREFLIGHT_SURFACE_INSUFFICIENT = "BLOCKED_PREFLIGHT_SURFACE_INSUFFICIENT"

_SAFE_PASS_LABELS = {
    STATUS_PASS,
    "TARGET_BINDING_PROVEN",
    "TARGET_IDENTITY_PROVEN",
    "SELECTED_CONTEXT_READBACK_PROVEN",
    "SELECTED_CONTEXT_READBACK_ACCEPTED",
    "ACCEPTED_SELECTOR_READBACK_STATUS_LABEL",
}
_PRIVATE_STRING_PREFIXES = ("pk_", "pk_legacy_")
_PRIVATE_STRING_FRAGMENTS = (
    "/",
    "\\",
    "postgresql://",
    "sqlite://",
    "select ",
    "update ",
    "insert ",
    "delete ",
    "dump",
    "database=",
    "host=",
    "user=",
    "password",
    "credential",
    "private_selector",
    "private_output",
)
_REFERENCE_COUNT_KEYS = (
    "session_projects",
    "agent_projects",
    "agent_recent_projects",
)
_REFERENCE_COUNT_BUCKETS = ("0", "LOW_CARDINALITY_SUPPRESSED", "PUBLIC_SAFE_AGGREGATE")


@dataclass(frozen=True)
class AffectedRowReferentialInventoryReport:
    """Aggregate-only result for affected-row referential inventory."""

    status_label: str
    mutation_attempted: bool = False
    mutation_authorized: bool = False
    dry_run: bool = True
    readonly_authority_status_label: str = STATUS_PASS
    target_binding_status_label: str = STATUS_PASS
    selected_context_readback_status_label: str = STATUS_PASS
    referential_inventory_status_label: str = STATUS_PASS
    low_cardinality_status_label: str = STATUS_PASS
    output_contract_status_label: str = STATUS_PASS
    storage_backend_status_label: str = STATUS_PASS
    redaction_status_label: str = REDACTION_GUARD_PASS
    private_output_detected: bool = False
    affected_project_rows_count: int = 0
    affected_project_rows_count_bucket: str = "0"
    total_reference_rows_count: int = 0
    total_reference_rows_count_bucket: str = "0"
    reference_count_buckets: Mapping[str, str] = field(default_factory=dict)
    blocked_state_count: int = 0
    labels: tuple[str, ...] = field(default_factory=tuple)

    def to_public_dict(self) -> dict[str, object]:
        """Return only labels, booleans, statuses, and public-safe aggregates."""
        payload: dict[str, object] = {
            "status_label": self.status_label,
            "mutation_attempted": self.mutation_attempted,
            "mutation_authorized": self.mutation_authorized,
            "dry_run": self.dry_run,
            "readonly_authority_status_label": self.readonly_authority_status_label,
            "target_binding_status_label": self.target_binding_status_label,
            "selected_context_readback_status_label": self.selected_context_readback_status_label,
            "referential_inventory_status_label": self.referential_inventory_status_label,
            "low_cardinality_status_label": self.low_cardinality_status_label,
            "output_contract_status_label": self.output_contract_status_label,
            "storage_backend_status_label": self.storage_backend_status_label,
            "redaction_status_label": self.redaction_status_label,
            "private_output_detected": self.private_output_detected,
            "affected_project_rows_count": self.affected_project_rows_count,
            "affected_project_rows_count_bucket": self.affected_project_rows_count_bucket,
            "total_reference_rows_count": self.total_reference_rows_count,
            "total_reference_rows_count_bucket": self.total_reference_rows_count_bucket,
            "reference_count_buckets": dict(self.reference_count_buckets),
            "blocked_state_count": self.blocked_state_count,
            "labels": list(self.labels),
        }
        if _contains_private_output(payload) or not _public_payload_shape_is_safe(payload):
            return _blocked_public_contract_report().to_public_dict()
        return payload


def build_affected_row_referential_inventory_report(
    *,
    project_rows: Sequence[Mapping[str, object]],
    reference_counts: Mapping[str, int],
    target_binding_status_label: str,
    selected_context_readback_status_label: str,
    low_cardinality_threshold: int = 5,
) -> AffectedRowReferentialInventoryReport:
    """Build a fail-closed, aggregate-only affected-row inventory report."""
    threshold = max(2, int(low_cardinality_threshold))
    affected_rows = [_coerce_project_row(row) for row in project_rows]
    references = _coerce_reference_counts(reference_counts)
    labels: list[str] = []
    blocked_state_count = 0

    target_binding_status = _coerce_status_label(target_binding_status_label)
    selected_context_status = _coerce_status_label(selected_context_readback_status_label)
    referential_status = STATUS_PASS
    low_cardinality_status = STATUS_PASS
    output_contract_status = STATUS_PASS

    if not _is_proven_status_label(target_binding_status):
        labels.append(BLOCKED_TARGET_BINDING_UNPROVEN if target_binding_status else BLOCKED_TARGET_IDENTITY_AMBIGUOUS)
        target_binding_status = BLOCKED_TARGET_BINDING_UNPROVEN if target_binding_status else BLOCKED_TARGET_IDENTITY_AMBIGUOUS
        blocked_state_count += 1

    if not _is_proven_status_label(selected_context_status):
        labels.append(BLOCKED_TARGET_IDENTITY_AMBIGUOUS)
        selected_context_status = BLOCKED_TARGET_IDENTITY_AMBIGUOUS
        blocked_state_count += 1

    if not references or any(key not in references for key in _REFERENCE_COUNT_KEYS):
        labels.append(BLOCKED_REFERENTIAL_INVENTORY_INCOMPLETE)
        referential_status = BLOCKED_REFERENTIAL_INVENTORY_INCOMPLETE
        blocked_state_count += 1
    if any(_contains_private_output(key) for key in references):
        labels.append(BLOCKED_PUBLIC_SAFE_OUTPUT_CONTRACT_UNPROVEN)
        output_contract_status = BLOCKED_PUBLIC_SAFE_OUTPUT_CONTRACT_UNPROVEN
        blocked_state_count += 1

    affected_count = len(affected_rows)
    total_reference_count = sum(references.values())
    count_values = (affected_count, total_reference_count, *references.values())
    if any(0 < count < threshold for count in count_values):
        labels.append(BLOCKED_LOW_CARDINALITY_OR_PRIVATE_RISK)
        low_cardinality_status = BLOCKED_LOW_CARDINALITY_OR_PRIVATE_RISK
        blocked_state_count += 1

    reference_buckets = {key: _count_bucket(value, threshold) for key, value in sorted(references.items())}
    affected_bucket = _count_bucket(affected_count, threshold)
    reference_bucket = _count_bucket(total_reference_count, threshold)

    if blocked_state_count == 0:
        if affected_count == 0:
            labels.append(INVENTORY_NO_AFFECTED_ROWS)
        elif total_reference_count == 0:
            labels.append(INVENTORY_REPAIR_NOT_REQUIRED)
        else:
            labels.append(INVENTORY_MUTATION_CANDIDATE_REQUIRES_CUSTODY_AND_REHEARSAL)

    status_label = labels[0] if blocked_state_count == 0 else STATUS_BLOCK
    report = AffectedRowReferentialInventoryReport(
        status_label=status_label,
        target_binding_status_label=target_binding_status,
        selected_context_readback_status_label=selected_context_status,
        referential_inventory_status_label=referential_status,
        low_cardinality_status_label=low_cardinality_status,
        output_contract_status_label=output_contract_status,
        affected_project_rows_count=affected_count if affected_bucket != "LOW_CARDINALITY_SUPPRESSED" else 0,
        affected_project_rows_count_bucket=affected_bucket,
        total_reference_rows_count=total_reference_count if reference_bucket != "LOW_CARDINALITY_SUPPRESSED" else 0,
        total_reference_rows_count_bucket=reference_bucket,
        reference_count_buckets=reference_buckets,
        blocked_state_count=blocked_state_count,
        labels=tuple(dict.fromkeys(labels)),
    )
    public_payload = report.to_public_dict()
    if public_payload.get("output_contract_status_label") != STATUS_PASS:
        return _blocked_public_contract_report()
    return report


def storage_backend_unavailable_report() -> AffectedRowReferentialInventoryReport:
    return AffectedRowReferentialInventoryReport(
        status_label=STATUS_BLOCK,
        storage_backend_status_label=BLOCKED_STORAGE_BACKEND_UNAVAILABLE,
        blocked_state_count=1,
        labels=(BLOCKED_STORAGE_BACKEND_UNAVAILABLE,),
    )


def readonly_authority_missing_report() -> AffectedRowReferentialInventoryReport:
    return AffectedRowReferentialInventoryReport(
        status_label=STATUS_BLOCK,
        readonly_authority_status_label=BLOCKED_READONLY_AUTHORITY_MISSING,
        blocked_state_count=1,
        labels=(BLOCKED_READONLY_AUTHORITY_MISSING,),
    )


def mutation_rejected_report() -> AffectedRowReferentialInventoryReport:
    return AffectedRowReferentialInventoryReport(
        status_label=STATUS_BLOCK,
        blocked_state_count=1,
        labels=(BLOCKED_PREFLIGHT_SURFACE_INSUFFICIENT,),
    )


def _blocked_public_contract_report() -> AffectedRowReferentialInventoryReport:
    return AffectedRowReferentialInventoryReport(
        status_label=STATUS_BLOCK,
        redaction_status_label=REDACTION_GUARD_BLOCK,
        private_output_detected=True,
        output_contract_status_label=BLOCKED_PUBLIC_SAFE_OUTPUT_CONTRACT_UNPROVEN,
        blocked_state_count=1,
        labels=(BLOCKED_PUBLIC_SAFE_OUTPUT_CONTRACT_UNPROVEN,),
    )


def _coerce_project_row(row: Mapping[str, object]) -> dict[str, bool]:
    return {
        "has_repo_id": bool(_row_value(row, "repo_id")),
        "has_project_key": bool(_row_value(row, "project_key")),
    }


def _coerce_reference_counts(reference_counts: Mapping[str, int]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in reference_counts.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count < 0:
            continue
        counts[key_text] = count
    return counts


def _coerce_status_label(value: str) -> str:
    return str(value or "").strip()


def _is_proven_status_label(value: str) -> bool:
    return value in _SAFE_PASS_LABELS


def _count_bucket(count: int, threshold: int) -> str:
    if count == 0:
        return "0"
    if count < threshold:
        return "LOW_CARDINALITY_SUPPRESSED"
    return "PUBLIC_SAFE_AGGREGATE"


def _public_payload_shape_is_safe(payload: Mapping[str, object]) -> bool:
    for key, value in payload.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            continue
        if isinstance(value, str):
            if key.endswith("_bucket") and value not in _REFERENCE_COUNT_BUCKETS:
                return False
            continue
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            continue
        if isinstance(value, Mapping) and all(
            isinstance(k, str) and isinstance(v, str) and v in _REFERENCE_COUNT_BUCKETS
            for k, v in value.items()
        ):
            continue
        return False
    return True


def _contains_private_output(value: object) -> bool:
    if isinstance(value, str):
        lower = value.lower()
        return value.startswith(_PRIVATE_STRING_PREFIXES) or any(fragment in lower for fragment in _PRIVATE_STRING_FRAGMENTS)
    if isinstance(value, Mapping):
        return any(_contains_private_output(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_private_output(item) for item in value)
    return False


def _row_value(row: Mapping[str, object], key: str) -> object:
    if isinstance(row, Mapping):
        return row.get(key)
    try:
        return row[key]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return None
