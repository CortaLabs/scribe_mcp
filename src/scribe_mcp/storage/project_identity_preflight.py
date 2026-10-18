"""Public-safe project identity repair preflight reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Sequence

from scribe_mcp.storage.models import (
    compute_legacy_project_key,
    compute_project_key,
    compute_repo_id,
    normalize_repo_root,
)

AsyncFetchAll = Callable[[str, tuple[object, ...]], Awaitable[Sequence[Any]]]
AsyncFetchOne = Callable[[str, tuple[object, ...]], Awaitable[Any | None]]

STATUS_PASS = "PASS"
STATUS_BLOCK = "BLOCK"
REDACTION_GUARD_PASS = "REDACTION_GUARD_PASS"
REDACTION_GUARD_BLOCK = "REDACTION_GUARD_BLOCK"
MUTATION_REJECTED_LABEL = "PROJECT_IDENTITY_PREFLIGHT_MUTATION_UNAVAILABLE"
DRY_RUN_REQUIRED_LABEL = "PROJECT_IDENTITY_PREFLIGHT_DRY_RUN_REQUIRED"
AMBIGUOUS_TARGET_BINDING_LABEL = "AMBIGUOUS_TARGET_BINDING_BLOCK"
REFERENTIAL_INTEGRITY_UNCERTAIN_LABEL = "REFERENTIAL_INTEGRITY_UNCERTAIN_BLOCK"
DEPENDENT_REFERENCE_PRESERVATION_REQUIRED_LABEL = "DEPENDENT_REFERENCE_PRESERVATION_REQUIRED"
LOW_CARDINALITY_BUCKET_LABEL = "LOW_CARDINALITY_IDENTIFYING_BUCKET_BLOCK"
ROLLBACK_PROOF_MISSING_LABEL = "ROLLBACK_PROOF_MISSING_BLOCK"
OPERATOR_APPROVAL_MISSING_LABEL = "OPERATOR_APPROVAL_MISSING_BLOCK"

_PRIVATE_STRING_PREFIXES = ("pk_", "pk_legacy_")
_PRIVATE_STRING_FRAGMENTS = (
    "/",
    "\\",
    "postgresql://",
    "sqlite://",
    "SELECT ",
    "UPDATE ",
    "INSERT ",
    "DELETE ",
    "PRIVATE_OUTPUT_SENTINEL",
)


@dataclass(frozen=True)
class ProjectIdentityRowSnapshot:
    """Internal row snapshot; never serialize this dataclass publicly."""

    row_id: int
    name: str
    repo_root: str
    repo_id: str
    project_key: str


@dataclass(frozen=True)
class ProjectIdentityPreflightReport:
    """Aggregate-only result for the project identity repair preflight."""

    status_label: str
    mutation_attempted: bool = False
    mutation_authorized: bool = False
    dry_run: bool = True
    redaction_status_label: str = REDACTION_GUARD_PASS
    private_output_detected: bool = False
    ambiguous_target_binding_status_label: str = AMBIGUOUS_TARGET_BINDING_LABEL
    rollback_proof_status_label: str = ROLLBACK_PROOF_MISSING_LABEL
    operator_approval_status_label: str = OPERATOR_APPROVAL_MISSING_LABEL
    referential_integrity_status_label: str = STATUS_PASS
    dependent_reference_preservation_status_label: str = STATUS_PASS
    low_cardinality_bucket_status_label: str = STATUS_PASS
    unexpected_row_class_status_label: str = STATUS_PASS
    total_project_rows: int = 0
    missing_identity_rows: int = 0
    partial_identity_rows: int = 0
    canonical_retention_candidates: int = 0
    legacy_key_assignment_candidates: int = 0
    already_populated_duplicate_project_key_groups: int = 0
    missing_unusable_repo_root_rows: int = 0
    legacy_name_constraint_present: bool = False
    legacy_name_index_present: bool = False
    dependent_reference_rows: int = 0
    blocked_state_count: int = 0
    labels: tuple[str, ...] = field(default_factory=tuple)

    def to_public_dict(self) -> dict[str, object]:
        """Return only labels, booleans, and aggregate counts."""
        payload: dict[str, object] = {
            "status_label": self.status_label,
            "mutation_attempted": self.mutation_attempted,
            "mutation_authorized": self.mutation_authorized,
            "dry_run": self.dry_run,
            "redaction_status_label": self.redaction_status_label,
            "private_output_detected": self.private_output_detected,
            "ambiguous_target_binding_status_label": self.ambiguous_target_binding_status_label,
            "rollback_proof_status_label": self.rollback_proof_status_label,
            "operator_approval_status_label": self.operator_approval_status_label,
            "referential_integrity_status_label": self.referential_integrity_status_label,
            "dependent_reference_preservation_status_label": self.dependent_reference_preservation_status_label,
            "low_cardinality_bucket_status_label": self.low_cardinality_bucket_status_label,
            "unexpected_row_class_status_label": self.unexpected_row_class_status_label,
            "total_project_rows": self.total_project_rows,
            "missing_identity_rows": self.missing_identity_rows,
            "partial_identity_rows": self.partial_identity_rows,
            "canonical_retention_candidates": self.canonical_retention_candidates,
            "legacy_key_assignment_candidates": self.legacy_key_assignment_candidates,
            "already_populated_duplicate_project_key_groups": self.already_populated_duplicate_project_key_groups,
            "missing_unusable_repo_root_rows": self.missing_unusable_repo_root_rows,
            "legacy_name_constraint_present": self.legacy_name_constraint_present,
            "legacy_name_index_present": self.legacy_name_index_present,
            "dependent_reference_rows": self.dependent_reference_rows,
            "blocked_state_count": self.blocked_state_count,
            "labels": list(self.labels),
        }
        if self.ambiguous_target_binding_status_label != STATUS_PASS:
            payload["status_label"] = STATUS_BLOCK
            payload["blocked_state_count"] = max(1, int(payload["blocked_state_count"]))
            labels = list(payload["labels"])
            if self.ambiguous_target_binding_status_label not in labels:
                labels.append(self.ambiguous_target_binding_status_label)
            payload["labels"] = labels
        if _contains_private_output(payload):
            payload = {
                "status_label": STATUS_BLOCK,
                "mutation_attempted": False,
                "mutation_authorized": False,
                "dry_run": True,
                "redaction_status_label": REDACTION_GUARD_BLOCK,
                "private_output_detected": True,
                "blocked_state_count": max(1, self.blocked_state_count),
                "labels": [REDACTION_GUARD_BLOCK],
            }
        return payload


def build_project_identity_preflight_report(
    *,
    project_rows: Sequence[Any],
    legacy_name_constraint_present: bool,
    legacy_name_index_present: bool,
    dependent_reference_rows: int,
) -> ProjectIdentityPreflightReport:
    rows = [_coerce_row(row) for row in project_rows]
    duplicate_groups = _already_populated_duplicate_project_key_groups(rows)
    missing_unusable_repo_root_rows = 0
    missing_identity_rows = 0
    partial_identity_rows = 0
    canonical_retention_candidates = 0
    legacy_key_assignment_candidates = 0
    unexpected_row_classes = 0

    assigned_project_keys = {
        row.project_key
        for row in rows
        if row.project_key and not _identity_needs_assignment(row)
    }

    for row in rows:
        if not row.name:
            unexpected_row_classes += 1
            continue
        if not row.repo_root:
            missing_unusable_repo_root_rows += 1
            continue
        if not _identity_needs_assignment(row):
            continue

        missing_repo_id = not row.repo_id
        missing_project_key = not row.project_key
        if missing_repo_id and missing_project_key:
            missing_identity_rows += 1
        else:
            partial_identity_rows += 1

        normalized_root = normalize_repo_root(row.repo_root)
        canonical_key = compute_project_key(repo_root=normalized_root, project_name=row.name)
        if canonical_key in assigned_project_keys:
            legacy_key_assignment_candidates += 1
            assigned_project_keys.add(
                compute_legacy_project_key(
                    repo_root=normalized_root,
                    project_name=row.name,
                    row_id=row.row_id,
                )
            )
            continue
        canonical_retention_candidates += 1
        assigned_project_keys.add(canonical_key)

    labels: list[str] = [AMBIGUOUS_TARGET_BINDING_LABEL]
    blocked_state_count = 1
    ambiguous_target_binding_status_label = AMBIGUOUS_TARGET_BINDING_LABEL
    referential_integrity_status_label = STATUS_PASS
    dependent_reference_preservation_status_label = STATUS_PASS
    low_cardinality_bucket_status_label = STATUS_PASS
    unexpected_row_class_status_label = STATUS_PASS

    if duplicate_groups:
        labels.append("ALREADY_POPULATED_DUPLICATE_PROJECT_KEY_GROUPS")
        blocked_state_count += duplicate_groups
    if missing_unusable_repo_root_rows:
        labels.append("MISSING_UNUSABLE_REPO_ROOT_ROWS")
        blocked_state_count += missing_unusable_repo_root_rows
    if dependent_reference_rows:
        labels.append(DEPENDENT_REFERENCE_PRESERVATION_REQUIRED_LABEL)
        dependent_reference_preservation_status_label = DEPENDENT_REFERENCE_PRESERVATION_REQUIRED_LABEL
        referential_integrity_status_label = REFERENTIAL_INTEGRITY_UNCERTAIN_LABEL
        blocked_state_count += 1
    if unexpected_row_classes:
        labels.append("UNEXPECTED_ROW_CLASS_BLOCK")
        unexpected_row_class_status_label = STATUS_BLOCK
        blocked_state_count += unexpected_row_classes

    identifying_bucket_counts = (
        missing_identity_rows,
        partial_identity_rows,
        canonical_retention_candidates,
        legacy_key_assignment_candidates,
        duplicate_groups,
        missing_unusable_repo_root_rows,
        dependent_reference_rows,
    )
    if any(count == 1 for count in identifying_bucket_counts):
        labels.append(LOW_CARDINALITY_BUCKET_LABEL)
        low_cardinality_bucket_status_label = LOW_CARDINALITY_BUCKET_LABEL
        blocked_state_count += 1

    if missing_identity_rows or partial_identity_rows or canonical_retention_candidates or legacy_key_assignment_candidates:
        labels.append("EXISTING_ROW_REPAIR_READINESS_CANDIDATES")
        blocked_state_count += 1

    labels.extend((ROLLBACK_PROOF_MISSING_LABEL, OPERATOR_APPROVAL_MISSING_LABEL))
    blocked_state_count += 2

    status_label = STATUS_PASS if blocked_state_count == 0 else STATUS_BLOCK
    return ProjectIdentityPreflightReport(
        status_label=status_label,
        legacy_name_constraint_present=legacy_name_constraint_present,
        legacy_name_index_present=legacy_name_index_present,
        total_project_rows=len(rows),
        missing_identity_rows=missing_identity_rows,
        partial_identity_rows=partial_identity_rows,
        canonical_retention_candidates=canonical_retention_candidates,
        legacy_key_assignment_candidates=legacy_key_assignment_candidates,
        already_populated_duplicate_project_key_groups=duplicate_groups,
        missing_unusable_repo_root_rows=missing_unusable_repo_root_rows,
        dependent_reference_rows=max(0, int(dependent_reference_rows)),
        ambiguous_target_binding_status_label=ambiguous_target_binding_status_label,
        dependent_reference_preservation_status_label=dependent_reference_preservation_status_label,
        referential_integrity_status_label=referential_integrity_status_label,
        low_cardinality_bucket_status_label=low_cardinality_bucket_status_label,
        unexpected_row_class_status_label=unexpected_row_class_status_label,
        blocked_state_count=blocked_state_count,
        labels=tuple(dict.fromkeys(labels)),
    )


async def build_sqlite_project_identity_preflight(
    *,
    fetchall_fn: AsyncFetchAll,
    fetchone_fn: AsyncFetchOne,
) -> ProjectIdentityPreflightReport:
    table_sql_row = await fetchone_fn(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'scribe_projects'
        LIMIT 1;
        """,
        (),
    )
    table_sql = str(_row_value(table_sql_row, "sql", "") or "")
    index_row = await fetchone_fn(
        """
        SELECT 1 AS present
        FROM sqlite_master
        WHERE type = 'index'
          AND name = 'scribe_projects_name_key'
        LIMIT 1;
        """,
        (),
    )
    project_rows = await fetchall_fn(
        """
        SELECT id, name, repo_root, repo_id, project_key
        FROM scribe_projects
        ORDER BY id;
        """,
        (),
    )
    dependent_reference_rows = 0
    for table_name in ("session_projects", "agent_projects", "agent_recent_projects"):
        table_row = await fetchone_fn(
            """
            SELECT 1 AS present
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            LIMIT 1;
            """,
            (table_name,),
        )
        if not table_row:
            continue
        count_row = await fetchone_fn(
            f"SELECT COUNT(*) AS count FROM {table_name};",
            (),
        )
        dependent_reference_rows += int(_row_value(count_row, "count", 0) or 0)

    return build_project_identity_preflight_report(
        project_rows=project_rows,
        legacy_name_constraint_present="NAME TEXT NOT NULL UNIQUE" in table_sql.upper().replace("\n", " "),
        legacy_name_index_present=bool(index_row),
        dependent_reference_rows=dependent_reference_rows,
    )


def _identity_needs_assignment(row: ProjectIdentityRowSnapshot) -> bool:
    if not row.repo_root:
        return True
    normalized_root = normalize_repo_root(row.repo_root)
    expected_repo_id = compute_repo_id(normalized_root)
    return not row.repo_id or not row.project_key or row.repo_id != expected_repo_id


def _already_populated_duplicate_project_key_groups(rows: Sequence[ProjectIdentityRowSnapshot]) -> int:
    counts: dict[str, int] = {}
    for row in rows:
        if row.project_key:
            counts[row.project_key] = counts.get(row.project_key, 0) + 1
    return sum(1 for count in counts.values() if count > 1)


def _coerce_row(row: Any) -> ProjectIdentityRowSnapshot:
    row_id = _row_value(row, "id", 0)
    return ProjectIdentityRowSnapshot(
        row_id=int(row_id or 0),
        name=str(_row_value(row, "name", "") or ""),
        repo_root=str(_row_value(row, "repo_root", "") or ""),
        repo_id=str(_row_value(row, "repo_id", "") or ""),
        project_key=str(_row_value(row, "project_key", "") or ""),
    )


def _row_value(row: Any, key: str, default: object = None) -> object:
    if row is None:
        return default
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _contains_private_output(value: object) -> bool:
    if isinstance(value, str):
        upper = value.upper()
        lower = value.lower()
        return value.startswith(_PRIVATE_STRING_PREFIXES) or any(
            fragment in upper or fragment in lower for fragment in _PRIVATE_STRING_FRAGMENTS
        )
    if isinstance(value, Mapping):
        return any(_contains_private_output(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_private_output(item) for item in value)
    return False
