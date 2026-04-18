from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from scribe_mcp.utils.slug import normalize_project_input


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
