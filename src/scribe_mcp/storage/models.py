from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from scribe_mcp.utils.slug import normalize_project_input


ApplyPreviewReceiptState = Literal["issued", "applying", "applied", "failed_terminal"]
ApplyPreviewClaimStatus = Literal["claimed", "recovery", "terminal", "busy", "expired", "not_found"]
ApplyPreviewResultCode = Literal[
    "APPLY_RECEIPT_APPLIED",
    "APPLY_RECEIPT_REPLAYED",
    "APPLY_RECEIPT_INVALID",
    "APPLY_RECEIPT_EXPIRED",
    "APPLY_RECEIPT_SCOPE_MISMATCH",
    "APPLY_RECEIPT_INAPPLICABLE",
    "APPLY_RECEIPT_POLICY_DENIED",
    "APPLY_RECEIPT_TARGET_DRIFT",
    "APPLY_RECEIPT_BUSY",
    "APPLY_RECEIPT_RECOVERY_REQUIRED",
    "APPLY_RECEIPT_STORAGE_UNAVAILABLE",
]

APPLY_PREVIEW_RECEIPT_STATES = frozenset({"issued", "applying", "applied", "failed_terminal"})
APPLY_PREVIEW_CLAIM_STATUSES = frozenset(
    {"claimed", "recovery", "terminal", "busy", "expired", "not_found"}
)
APPLY_PREVIEW_RESULT_CODES = frozenset(
    {
        "APPLY_RECEIPT_APPLIED",
        "APPLY_RECEIPT_REPLAYED",
        "APPLY_RECEIPT_INVALID",
        "APPLY_RECEIPT_EXPIRED",
        "APPLY_RECEIPT_SCOPE_MISMATCH",
        "APPLY_RECEIPT_INAPPLICABLE",
        "APPLY_RECEIPT_POLICY_DENIED",
        "APPLY_RECEIPT_TARGET_DRIFT",
        "APPLY_RECEIPT_BUSY",
        "APPLY_RECEIPT_RECOVERY_REQUIRED",
        "APPLY_RECEIPT_STORAGE_UNAVAILABLE",
    }
)


def _require_nonempty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_aware_datetime(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class ApplyPreviewReceiptRecord:
    """Durable, secret-free storage representation of an apply-preview receipt."""

    token_sha256: str
    receipt_version: int
    state: ApplyPreviewReceiptState
    principal_id: str = field(repr=False)
    session_id: str = field(repr=False)
    run_id: str = field(repr=False)
    project_key: str = field(repr=False)
    repo_id: str = field(repr=False)
    action: str
    normalized_intent_json: str = field(repr=False)
    target_binding_json: str = field(repr=False)
    precondition_json: str = field(repr=False)
    predicted_after_json: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    fence: int
    apply_lease_expires_at: Optional[datetime]
    terminal_result_code: Optional[ApplyPreviewResultCode]
    terminal_result_json: Optional[str] = field(repr=False)
    terminal_at: Optional[datetime]
    audit_correlation_id: str
    updated_at: datetime

    def __post_init__(self) -> None:
        if len(self.token_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.token_sha256
        ):
            raise ValueError("token_sha256 must be exactly 64 lowercase hexadecimal characters")
        if (
            not isinstance(self.receipt_version, int)
            or isinstance(self.receipt_version, bool)
            or self.receipt_version < 1
        ):
            raise ValueError("receipt_version must be a positive integer")
        if self.state not in APPLY_PREVIEW_RECEIPT_STATES:
            raise ValueError(f"state must be one of {sorted(APPLY_PREVIEW_RECEIPT_STATES)}")

        for name in (
            "principal_id",
            "session_id",
            "run_id",
            "project_key",
            "repo_id",
            "action",
            "normalized_intent_json",
            "target_binding_json",
            "precondition_json",
            "predicted_after_json",
            "audit_correlation_id",
        ):
            _require_nonempty_string(name, getattr(self, name))

        for name in ("issued_at", "expires_at", "updated_at"):
            _require_aware_datetime(name, getattr(self, name))
        if self.apply_lease_expires_at is not None:
            _require_aware_datetime("apply_lease_expires_at", self.apply_lease_expires_at)
        if self.terminal_at is not None:
            _require_aware_datetime("terminal_at", self.terminal_at)
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at")
        if self.updated_at < self.issued_at:
            raise ValueError("updated_at must not be earlier than issued_at")
        if not isinstance(self.fence, int) or isinstance(self.fence, bool) or self.fence < 0:
            raise ValueError("fence must be a non-negative integer")

        terminal_values = (self.terminal_result_code, self.terminal_result_json, self.terminal_at)
        if self.state == "issued":
            if self.fence != 0 or self.apply_lease_expires_at is not None:
                raise ValueError("issued state requires fence 0 and no apply lease")
        elif self.fence < 1:
            raise ValueError("applying and terminal states require a positive fence")
        if self.state == "applying" and self.apply_lease_expires_at is None:
            raise ValueError("applying state requires an apply lease expiry")
        if self.state in {"applied", "failed_terminal"}:
            if any(value is None for value in terminal_values):
                raise ValueError("terminal states require terminal result code, result JSON, and timestamp")
        elif any(value is not None for value in terminal_values):
            raise ValueError("non-terminal states cannot contain terminal result fields")
        if (
            self.terminal_result_code is not None
            and self.terminal_result_code not in APPLY_PREVIEW_RESULT_CODES
        ):
            raise ValueError(f"terminal_result_code must be one of {sorted(APPLY_PREVIEW_RESULT_CODES)}")


@dataclass(frozen=True)
class ApplyPreviewClaimResult:
    """Result of one backend-atomic receipt claim attempt."""

    status: ApplyPreviewClaimStatus
    record: Optional[ApplyPreviewReceiptRecord] = None

    def __post_init__(self) -> None:
        if self.status not in APPLY_PREVIEW_CLAIM_STATUSES:
            raise ValueError(f"status must be one of {sorted(APPLY_PREVIEW_CLAIM_STATUSES)}")


def normalize_repo_root(repo_root: str) -> str:
    try:
        return str(Path(repo_root).expanduser().resolve())
    except Exception:
        return str(Path(repo_root).expanduser())


def compute_repo_id(repo_root: str) -> str:
    normalized_root = normalize_repo_root(repo_root)
    return sha256(normalized_root.encode("utf-8")).hexdigest()


def compute_project_key(*, repo_root: str, project_name: str) -> str:
    normalized_root = normalize_repo_root(repo_root)
    normalized_name = normalize_project_input(project_name) or project_name.strip().lower()
    digest = sha256(f"{normalized_root}::{normalized_name}".encode("utf-8")).hexdigest()
    return f"pk_{digest}"


def compute_legacy_project_key(*, repo_root: str, project_name: str, row_id: int) -> str:
    normalized_root = normalize_repo_root(repo_root)
    normalized_name = normalize_project_input(project_name) or project_name.strip().lower()
    digest = sha256(f"{normalized_root}::{normalized_name}::legacy::{row_id}".encode("utf-8")).hexdigest()
    return f"pk_legacy_{digest}"


@dataclass
class ProjectRecord:
    id: int
    name: str
    repo_root: str
    progress_log_path: str
    repo_id: Optional[str] = None
    project_key: Optional[str] = None
    docs_json: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    bridge_id: Optional[str] = None
    bridge_managed: bool = False


@dataclass
class DevPlanRecord:
    id: int
    project_id: int
    project_name: str
    plan_type: str  # 'architecture', 'phase_plan', 'checklist', 'progress_log'
    file_path: str
    version: str
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PhaseRecord:
    id: int
    project_id: int
    dev_plan_id: int
    phase_number: int
    phase_name: str
    status: str  # 'planned', 'in_progress', 'completed', 'blocked'
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    deliverables_count: int = 0
    deliverables_completed: int = 0
    confidence_score: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MilestoneRecord:
    id: int
    project_id: int
    phase_id: Optional[int]
    milestone_name: str
    description: str
    status: str  # 'pending', 'in_progress', 'completed', 'overdue'
    target_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    evidence_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class BenchmarkRecord:
    id: int
    project_id: int
    benchmark_type: str  # 'hash_performance', 'throughput', 'latency', 'stress_test'
    test_name: str
    metric_name: str
    metric_value: float
    metric_unit: str
    test_parameters: Optional[Dict[str, Any]] = None
    environment_info: Optional[Dict[str, Any]] = None
    test_timestamp: datetime = None
    requirement_target: Optional[float] = None
    requirement_met: bool = False


@dataclass
class ChecklistRecord:
    id: int
    project_id: int
    phase_id: Optional[int]
    checklist_item: str
    status: str  # 'pending', 'in_progress', 'completed', 'blocked'
    acceptance_criteria: str
    proof_required: bool = True
    proof_url: Optional[str] = None
    assignee: Optional[str] = None
    priority: str = 'medium'  # 'low', 'medium', 'high', 'critical'
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PerformanceMetricsRecord:
    id: int
    project_id: int
    metric_category: str  # 'development', 'testing', 'deployment', 'operations'
    metric_name: str
    metric_value: float
    metric_unit: str
    baseline_value: Optional[float] = None
    improvement_percentage: Optional[float] = None
    collection_timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None


# Document Management 2.0 Models

@dataclass
class DocumentSectionRecord:
    id: int
    project_id: int
    document_type: str  # 'architecture', 'phase_plan', 'checklist', 'progress_log', 'doc_log', 'security_log', 'bug_log'
    section_id: str     # 'problem_statement', 'requirements_constraints', etc.
    content: str
    file_hash: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class CustomTemplateRecord:
    id: int
    project_id: int
    template_name: str
    template_content: str
    variables: Optional[Dict[str, Any]] = None
    is_global: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DocumentChangeRecord:
    id: int
    project_id: int
    document_path: str
    change_type: str  # 'create', 'edit', 'delete', 'sync'
    change_summary: str
    old_content_hash: Optional[str] = None
    new_content_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


@dataclass
class SyncStatusRecord:
    id: int
    project_id: int
    file_path: str
    last_sync_at: Optional[datetime] = None
    last_file_hash: Optional[str] = None
    last_db_hash: Optional[str] = None
    sync_status: str = 'synced'  # 'synced', 'conflict', 'pending', 'error'
    conflict_details: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AgentReportCardRecord:
    id: int
    project_id: int
    file_path: str
    agent_name: str
    stage: Optional[str]
    overall_grade: Optional[float]
    performance_level: Optional[str]
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class RepoScopeGrantRecord:
    grant_id: str
    authoritative_session_key: str
    repo_root: str
    repo_id: str
    reason: str
    expires_at: datetime
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class CaseRegistryRecord:
    case_id: str
    case_type: str
    project_name: str
    repo_root: str
    repo_id: str
    project_key: str
    doc_type: str
    doc_name: str
    doc_path: str
    title: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
    source_tool: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
