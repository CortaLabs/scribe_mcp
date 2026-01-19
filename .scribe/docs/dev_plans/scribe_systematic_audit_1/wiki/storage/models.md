# Data Models - Storage Layer Contracts

**File**: `storage/models.py`
**LOC**: 207
**Models**: 13 dataclasses
**Purpose**: Define data contracts between storage backends and application code
**Last Audited**: 2026-01-05

---

## 1. Overview

All data models use Python `@dataclass` decorator for type-safe data structures. Each model maps 1:1 to a database table, providing consistent interfaces regardless of backend (SQLite/PostgreSQL).

### Design Principles

1. **Type Safety**: All fields have explicit type hints
2. **Immutability**: Dataclasses are frozen by default in critical paths
3. **Optional Fields**: Use `Optional[T]` for nullable columns
4. **JSON Support**: `Dict[str, Any]` for JSONB/JSON columns
5. **Backend Agnostic**: No SQL-specific types

---

## 2. Core Models (1 model)

### ProjectRecord

**File Location**: models.py:8-15

```python
@dataclass
class ProjectRecord:
    id: int
    name: str
    repo_root: str
    progress_log_path: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

**Maps To**: `scribe_projects` table
**Usage**: Primary project identity and metadata

---

## 3. Project Planning Models (6 models)

### DevPlanRecord

**File Location**: models.py:18-28

```python
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
```

**Maps To**: `dev_plans` table
**Constraints**: `plan_type` enum matches CHECK constraint

---

### PhaseRecord

**File Location**: models.py:31-44

```python
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
```

**Maps To**: `phases` table
**Constraints**:
- `status` enum matches CHECK constraint
- `confidence_score` must be 0.0-1.0

---

### MilestoneRecord

**File Location**: models.py:47-58

```python
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
```

**Maps To**: `milestones` table

---

### BenchmarkRecord

**File Location**: models.py:61-74

```python
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
```

**Maps To**: `benchmarks` table

---

### ChecklistRecord

**File Location**: models.py:77-91

```python
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
```

**Maps To**: `checklists` table

---

### PerformanceMetricsRecord

**File Location**: models.py:94-105

```python
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
```

**Maps To**: `performance_metrics` table

---

## 4. Document Management 2.0 Models (5 models)

### DocumentSectionRecord

**File Location**: models.py:110-120

```python
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
```

**Maps To**: `document_sections` table
**Note**: Only in SQLite backend

---

### CustomTemplateRecord

**File Location**: models.py:123-132

```python
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
```

**Maps To**: `custom_templates` table
**Note**: Only in SQLite backend

---

### DocumentChangeRecord

**File Location**: models.py:135-145

```python
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
```

**Maps To**: `document_changes` table
**Note**: Only in SQLite backend

---

### SyncStatusRecord

**File Location**: models.py:148-159

```python
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
```

**Maps To**: `sync_status` table
**Note**: Only in SQLite backend

---

### AgentReportCardRecord

**File Location**: models.py:162-173

```python
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
```

**Maps To**: `agent_report_cards` table
**Note**: Only in SQLite backend

---

## 5. Vector Index Models (2 models)

### VectorIndexRecord

**File Location**: models.py:178-192

```python
@dataclass
class VectorIndexRecord:
    id: int
    entry_id: str  # Deterministic UUID for the log entry
    project_slug: str  # Project identifier
    repo_slug: str  # Repository identifier
    vector_rowid: int  # Row ID in the FAISS index
    text_content: str  # Original message text
    agent_name: Optional[str]  # Entry author
    timestamp_utc: str  # Entry timestamp
    metadata_json: Optional[str]  # Entry metadata as JSON
    embedding_model: str  # Model used for embedding
    vector_dimension: int  # Vector dimension
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

**Maps To**: Vector indexer mapping database (separate DB)
**Note**: Used by vector_indexer plugin

---

### VectorShardMetadata

**File Location**: models.py:195-207

```python
@dataclass
class VectorShardMetadata:
    repo_slug: str  # Repository identifier
    dimension: int  # Vector dimension
    model: str  # Embedding model name
    scope: str  # Always 'repo-local' for isolation

    created_at: datetime  # When the shard was created
    backend: str  # Always 'faiss' for now
    index_type: str  # FAISS index type (e.g., 'IndexFlatIP')
    total_entries: int  # Number of entries in the index
    last_updated: Optional[datetime] = None  # Last index update
    embedding_model_version: Optional[str] = None  # Model version info
    index_size_bytes: Optional[int] = None  # Size of index file on disk
```

**Maps To**: Vector shard metadata (in-memory/file-based)
**Note**: Used by vector_indexer plugin

---

## 6. Model Relationships

### Foreign Key Relationships

```
scribe_projects (1)
  ├── scribe_entries (*) - project_id
  ├── scribe_metrics (1) - project_id
  ├── dev_plans (*) - project_id
  ├── phases (*) - project_id
  ├── milestones (*) - project_id
  ├── benchmarks (*) - project_id
  ├── checklists (*) - project_id
  ├── performance_metrics (*) - project_id
  ├── document_sections (*) - project_id [SQLite only]
  ├── custom_templates (*) - project_id [SQLite only]
  ├── document_changes (*) - project_id [SQLite only]
  ├── sync_status (*) - project_id [SQLite only]
  └── agent_report_cards (*) - project_id [SQLite only]

dev_plans (1)
  └── phases (*) - dev_plan_id

phases (1)
  ├── milestones (*) - phase_id (nullable)
  └── checklists (*) - phase_id (nullable)
```

---

## 7. Usage Patterns

### Creating Models from DB Rows

**SQLite**:
```python
row = cursor.fetchone()
project = ProjectRecord(
    id=row['id'],
    name=row['name'],
    repo_root=row['repo_root'],
    progress_log_path=row['progress_log_path'],
    created_at=parse_datetime(row['created_at']),
    updated_at=parse_datetime(row['updated_at'])
)
```

**PostgreSQL**:
```python
row = await conn.fetchrow("SELECT * FROM scribe_projects WHERE name = $1", name)
project = ProjectRecord(
    id=row['id'],
    name=row['name'],
    repo_root=row['repo_root'],
    progress_log_path=row['progress_log_path'],
    created_at=row['created_at'],  # Already datetime object
    updated_at=row['updated_at']
)
```

---

## 8. Type Conversion Patterns

### JSON Metadata

**SQLite** (TEXT column):
```python
# Writing
meta_str = json.dumps(metadata) if metadata else None

# Reading
metadata = json.loads(row['metadata']) if row['metadata'] else None
```

**PostgreSQL** (JSONB column):
```python
# Writing - asyncpg handles conversion
await conn.execute("INSERT ... metadata = $1", metadata)

# Reading - asyncpg handles conversion
metadata = row['metadata']  # Already dict
```

### Timestamps

**SQLite** (TEXT in ISO format):
```python
# Writing
ts_str = datetime.utcnow().isoformat()

# Reading
ts = datetime.fromisoformat(row['created_at'])
```

**PostgreSQL** (TIMESTAMPTZ):
```python
# Writing/Reading - asyncpg handles conversion automatically
created_at = datetime.utcnow()  # Stored as TIMESTAMPTZ
```

---

## 9. Backend Compatibility

| Model | SQLite | PostgreSQL | Notes |
|-------|--------|------------|-------|
| ProjectRecord | ✅ | ✅ | Full compatibility |
| DevPlanRecord | ✅ | ✅ | Full compatibility |
| PhaseRecord | ✅ | ✅ | Full compatibility |
| MilestoneRecord | ✅ | ✅ | Full compatibility |
| BenchmarkRecord | ✅ | ✅ | Full compatibility |
| ChecklistRecord | ✅ | ✅ | Full compatibility |
| PerformanceMetricsRecord | ✅ | ✅ | Full compatibility |
| DocumentSectionRecord | ✅ | ❌ | Table missing in PostgreSQL |
| CustomTemplateRecord | ✅ | ❌ | Table missing in PostgreSQL |
| DocumentChangeRecord | ✅ | ❌ | Table missing in PostgreSQL |
| SyncStatusRecord | ✅ | ❌ | Table missing in PostgreSQL |
| AgentReportCardRecord | ✅ | ❌ | Table missing in PostgreSQL |
| VectorIndexRecord | ✅ | N/A | Separate database |
| VectorShardMetadata | ✅ | N/A | In-memory/file |

---

## 10. Testing Recommendations

1. **Type Safety Tests**: Verify all fields have correct types
2. **Serialization Tests**: Test JSON metadata round-trip
3. **Datetime Tests**: Verify timezone handling across backends
4. **Nullable Tests**: Confirm Optional fields handle None correctly
5. **Enum Tests**: Verify status/type fields match CHECK constraints

---

**Related Files**:
- Storage implementations: `storage/sqlite.py`, `storage/postgres.py`
- Base interface: `storage/base.py`
- Database schema: `db/init.sql` (PostgreSQL)
