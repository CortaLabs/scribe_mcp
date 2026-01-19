# SQLite Storage Backend - Implementation Audit

**File**: `storage/sqlite.py`
**LOC**: 2,207
**Schema LOC**: ~410 (lines 650-1060)
**Purpose**: Default persistence layer using SQLite database
**Last Audited**: 2026-01-05

---

## 1. Overview

The SQLite backend is the default storage implementation for Scribe MCP, providing zero-configuration persistence with comprehensive table schema supporting all system features.

### Key Characteristics

1. **Zero Configuration**: No server setup required
2. **File-Based**: Single `.db` file per database
3. **ACID Compliant**: Full transaction support
4. **FTS5 Support**: Full-text search on document content
5. **Thread-Safe**: Uses connection pooling and WAL mode

---

## 2. Database Schema

### 2.1 Core Project Tables (3 tables)

#### scribe_projects

**Purpose**: Primary project registry
**File Location**: storage/sqlite.py:652-659

```sql
CREATE TABLE IF NOT EXISTS scribe_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    repo_root TEXT NOT NULL,
    progress_log_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes**: Unique index on `name`

---

#### scribe_entries

**Purpose**: Progress log entries
**File Location**: storage/sqlite.py:662-674

```sql
CREATE TABLE IF NOT EXISTS scribe_entries (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    ts_iso TEXT NOT NULL,
    emoji TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    meta TEXT,
    raw_line TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE
**Indexes**: `idx_entries_project_ts` on `(project_id, ts_iso DESC)`

---

#### scribe_metrics

**Purpose**: Aggregated project metrics
**File Location**: storage/sqlite.py:677-684

```sql
CREATE TABLE IF NOT EXISTS scribe_metrics (
    project_id INTEGER PRIMARY KEY REFERENCES scribe_projects(id) ON DELETE CASCADE,
    total_entries INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    warn_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_update TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE

---

### 2.2 Agent Session Tables (6 tables)

#### agent_sessions

**Purpose**: Multi-agent context management
**File Location**: storage/sqlite.py:687-698

```sql
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    identity_key TEXT UNIQUE NOT NULL,
    agent_name TEXT NOT NULL,
    agent_key TEXT NOT NULL,
    repo_root TEXT NOT NULL,
    mode TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);
```

**Indexes**:
- `idx_agent_sessions_identity` on `identity_key`
- `idx_agent_sessions_last_active` on `last_active_at`
- `idx_agent_sessions_expires` on `expires_at`

---

#### agent_projects

**Purpose**: Agent-scoped current project tracking
**File Location**: storage/sqlite.py:710-718

```sql
CREATE TABLE IF NOT EXISTS agent_projects (
    agent_id TEXT PRIMARY KEY,
    project_name TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    session_id TEXT,
    FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
);
```

**Foreign Keys**: `project_name` → `scribe_projects(name)` ON DELETE SET NULL
**Indexes**: `idx_agent_projects_updated_at` on `updated_at DESC`

---

#### agent_project_events

**Purpose**: Audit log for project switches
**File Location**: storage/sqlite.py:724-737

```sql
CREATE TABLE IF NOT EXISTS agent_project_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('project_set', 'project_switched', 'session_started', 'session_ended', 'conflict_detected')),
    from_project TEXT,
    to_project TEXT NOT NULL,
    expected_version INTEGER,
    actual_version INTEGER,
    success BOOLEAN NOT NULL DEFAULT 1,
    error_message TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Constraints**: CHECK on `event_type` enum
**Indexes**:
- `idx_agent_project_events_agent_id` on `agent_id`
- `idx_agent_project_events_created_at` on `created_at`

---

#### scribe_sessions

**Purpose**: Transport session tracking
**File Location**: storage/sqlite.py:746-754

```sql
CREATE TABLE IF NOT EXISTS scribe_sessions (
    session_id TEXT PRIMARY KEY,
    transport_session_id TEXT,
    agent_id TEXT,
    repo_root TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('sentinel','project')) DEFAULT 'sentinel',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Constraints**: CHECK on `mode` enum
**Indexes**:
- `idx_scribe_sessions_transport` on `transport_session_id`
- `idx_scribe_sessions_agent` on `agent_id`

---

#### session_projects

**Purpose**: Session-scoped project context
**File Location**: storage/sqlite.py:763-768

```sql
CREATE TABLE IF NOT EXISTS session_projects (
    session_id TEXT PRIMARY KEY,
    project_name TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
);
```

**Foreign Keys**: `project_name` → `scribe_projects(name)` ON DELETE SET NULL

---

#### agent_recent_projects

**Purpose**: Agent recent project history
**File Location**: storage/sqlite.py:771-777

```sql
CREATE TABLE IF NOT EXISTS agent_recent_projects (
    agent_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    last_access_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(agent_id, project_name),
    FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE CASCADE
);
```

**Foreign Keys**: `project_name` → `scribe_projects(name)` ON DELETE CASCADE
**Composite Key**: `(agent_id, project_name)`

---

### 2.3 Documentation Tracking (1 table)

#### doc_changes

**Purpose**: Documentation edit history
**File Location**: storage/sqlite.py:780-791

```sql
CREATE TABLE IF NOT EXISTS doc_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    doc_name TEXT NOT NULL,
    section TEXT,
    action TEXT NOT NULL,
    agent TEXT,
    metadata TEXT,
    sha_before TEXT,
    sha_after TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE
**Indexes**: `idx_doc_changes_project` on `(project_id, created_at DESC)`

---

### 2.4 Project Planning Tables (6 tables)

#### dev_plans

**Purpose**: Development plan documents
**File Location**: storage/sqlite.py:797-808

```sql
CREATE TABLE IF NOT EXISTS dev_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    plan_type TEXT NOT NULL CHECK (plan_type IN ('architecture', 'phase_plan', 'checklist', 'progress_log')),
    file_path TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,
    UNIQUE(project_id, plan_type)
);
```

**Constraints**:
- CHECK on `plan_type` enum
- UNIQUE on `(project_id, plan_type)`
**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE
**Indexes**: `idx_dev_plans_project_type` on `(project_id, plan_type)`

---

#### phases

**Purpose**: Project phase tracking
**File Location**: storage/sqlite.py:811-825

```sql
CREATE TABLE IF NOT EXISTS phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    dev_plan_id INTEGER NOT NULL REFERENCES dev_plans(id) ON DELETE CASCADE,
    phase_number INTEGER NOT NULL,
    phase_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned', 'in_progress', 'completed', 'blocked')) DEFAULT 'planned',
    start_date TEXT,
    end_date TEXT,
    deliverables_count INTEGER NOT NULL DEFAULT 0,
    deliverables_completed INTEGER NOT NULL DEFAULT 0,
    confidence_score REAL NOT NULL DEFAULT 0.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    metadata TEXT,
    UNIQUE(project_id, phase_number)
);
```

**Constraints**:
- CHECK on `status` enum
- CHECK on `confidence_score` range
- UNIQUE on `(project_id, phase_number)`
**Foreign Keys**:
- `project_id` → `scribe_projects(id)` ON DELETE CASCADE
- `dev_plan_id` → `dev_plans(id)` ON DELETE CASCADE
**Indexes**: `idx_phases_project_status` on `(project_id, status)`

---

#### milestones

**Purpose**: Project milestone tracking
**File Location**: storage/sqlite.py:828-839

```sql
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
    milestone_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'overdue')) DEFAULT 'pending',
    target_date TEXT,
    completed_date TEXT,
    evidence_url TEXT,
    metadata TEXT
);
```

**Constraints**: CHECK on `status` enum
**Foreign Keys**:
- `project_id` → `scribe_projects(id)` ON DELETE CASCADE
- `phase_id` → `phases(id)` ON DELETE SET NULL
**Indexes**: `idx_milestones_project_status` on `(project_id, status)`

---

#### benchmarks

**Purpose**: Performance benchmark results
**File Location**: storage/sqlite.py:842-855

```sql
CREATE TABLE IF NOT EXISTS benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    benchmark_type TEXT NOT NULL CHECK (benchmark_type IN ('hash_performance', 'throughput', 'latency', 'stress_test', 'integrity', 'concurrency')),
    test_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    test_parameters TEXT,
    environment_info TEXT,
    test_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    requirement_target REAL,
    requirement_met BOOLEAN NOT NULL DEFAULT FALSE
);
```

**Constraints**: CHECK on `benchmark_type` enum
**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE
**Indexes**:
- `idx_benchmarks_project_type` on `(project_id, benchmark_type)`
- `idx_benchmarks_timestamp` on `test_timestamp DESC`

---

#### checklists

**Purpose**: Project checklist items
**File Location**: storage/sqlite.py:858-872

```sql
CREATE TABLE IF NOT EXISTS checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
    checklist_item TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'blocked')) DEFAULT 'pending',
    acceptance_criteria TEXT NOT NULL,
    proof_required BOOLEAN NOT NULL DEFAULT TRUE,
    proof_url TEXT,
    assignee TEXT,
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    metadata TEXT
);
```

**Constraints**:
- CHECK on `status` enum
- CHECK on `priority` enum
**Foreign Keys**:
- `project_id` → `scribe_projects(id)` ON DELETE CASCADE
- `phase_id` → `phases(id)` ON DELETE SET NULL
**Indexes**:
- `idx_checklists_project_status` on `(project_id, status)`
- `idx_checklists_phase` on `phase_id`

---

#### performance_metrics

**Purpose**: Performance metric collection
**File Location**: storage/sqlite.py:875-886

```sql
CREATE TABLE IF NOT EXISTS performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    metric_category TEXT NOT NULL CHECK (metric_category IN ('development', 'testing', 'deployment', 'operations')),
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    baseline_value REAL,
    improvement_percentage REAL,
    collection_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);
```

**Constraints**: CHECK on `metric_category` enum
**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE
**Indexes**:
- `idx_metrics_project_category` on `(project_id, metric_category)`
- `idx_metrics_timestamp` on `collection_timestamp DESC`

---

### 2.5 Document Management 2.0 Tables (4 tables)

#### document_sections

**Purpose**: Cached document sections
**File Location**: storage/sqlite.py:901-916

```sql
CREATE TABLE IF NOT EXISTS document_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
    project_root TEXT,
    document_type TEXT,
    section_id TEXT,
    file_path TEXT,
    relative_path TEXT,
    content TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, document_type, section_id),
    UNIQUE(project_root, file_path)
);
```

**Constraints**:
- UNIQUE on `(project_id, document_type, section_id)`
- UNIQUE on `(project_root, file_path)`
**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE
**Indexes**:
- `idx_document_sections_project` on `project_id`
- `idx_document_sections_updated` on `updated_at`

**⚠️ NOTE**: Also has FTS5 virtual table (see section 2.6)

---

#### custom_templates

**Purpose**: Custom Jinja2 templates
**File Location**: storage/sqlite.py:919-929

```sql
CREATE TABLE IF NOT EXISTS custom_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    template_name TEXT NOT NULL,
    template_content TEXT NOT NULL,
    variables TEXT,
    is_global BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, template_name)
);
```

**Constraints**: UNIQUE on `(project_id, template_name)`
**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE

---

#### document_changes

**Purpose**: Document change history
**File Location**: storage/sqlite.py:932-943

```sql
CREATE TABLE IF NOT EXISTS document_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
    project_root TEXT,
    file_path TEXT,
    change_type TEXT NOT NULL,
    old_content_hash TEXT,
    new_content_hash TEXT,
    change_summary TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE
**Indexes**:
- `idx_document_changes_project` on `project_id`
- `idx_document_changes_created` on `created_at`

---

#### sync_status

**Purpose**: File sync conflict tracking
**File Location**: storage/sqlite.py:946-960

```sql
CREATE TABLE IF NOT EXISTS sync_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
    project_root TEXT,
    file_path TEXT NOT NULL,
    relative_path TEXT,
    last_sync_at TEXT,
    last_file_hash TEXT,
    last_db_hash TEXT,
    sync_status TEXT NOT NULL DEFAULT 'synced',
    conflict_details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, file_path)
);
```

**Constraints**: UNIQUE on `(project_id, file_path)`
**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE
**Indexes**:
- `idx_sync_status_project` on `project_id`
- `idx_sync_status_status` on `sync_status`

---

### 2.6 Agent Review Tables (1 table)

#### agent_report_cards

**Purpose**: Agent performance grades
**File Location**: storage/sqlite.py:963-975

```sql
CREATE TABLE IF NOT EXISTS agent_report_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    stage TEXT,
    overall_grade REAL,
    performance_level TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, file_path)
);
```

**Constraints**: UNIQUE on `(project_id, file_path)`
**Foreign Keys**: `project_id` → `scribe_projects(id)` ON DELETE CASCADE

---

### 2.7 Reminder System Tables (1 table)

#### reminder_history

**Purpose**: Reminder cooldown tracking
**File Location**: storage/sqlite.py:978-990

```sql
CREATE TABLE IF NOT EXISTS reminder_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    reminder_hash TEXT NOT NULL,
    project_root TEXT,
    agent_id TEXT,
    tool_name TEXT,
    reminder_key TEXT,
    shown_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    operation_status TEXT NOT NULL DEFAULT 'neutral' CHECK (operation_status IN ('success', 'failure', 'neutral')),
    context_metadata TEXT,
    FOREIGN KEY (session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE
);
```

**Constraints**: CHECK on `operation_status` enum
**Foreign Keys**: `session_id` → `scribe_sessions(session_id)` ON DELETE CASCADE
**Indexes**:
- `idx_reminder_history_session_hash` on `(session_id, reminder_hash)`
- `idx_reminder_history_shown_at` on `shown_at`
- `idx_reminder_history_session_tool` on `(session_id, tool_name)`

---

### 2.8 Tool Call Logging (1 table)

#### tool_calls

**Purpose**: Tool invocation tracking
**File Location**: storage/sqlite.py:1006-1019

```sql
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_ms REAL,
    status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'error', 'partial')),
    format_requested TEXT,
    project_name TEXT,
    agent_id TEXT,
    error_message TEXT,
    response_size_bytes INTEGER,
    FOREIGN KEY (session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE
);
```

**Constraints**: CHECK on `status` enum
**Foreign Keys**: `session_id` → `scribe_sessions(session_id)` ON DELETE CASCADE
**Indexes**:
- `idx_tool_calls_session` on `session_id`
- `idx_tool_calls_tool_name` on `tool_name`
- `idx_tool_calls_timestamp` on `timestamp`
- `idx_tool_calls_project` on `project_name`

---

### 2.9 Full-Text Search (1 virtual table)

#### document_sections_fts

**Purpose**: FTS5 full-text search index
**File Location**: storage/sqlite.py:1042-1043

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS document_sections_fts
USING fts5(document_type, section_id, content, content=document_sections, content_rowid=id)
```

**Triggers**: Auto-sync with `document_sections` table
- `document_sections_fts_insert` (AFTER INSERT)
- `document_sections_fts_update` (AFTER UPDATE)
- `document_sections_fts_delete` (AFTER DELETE)

**File Location**: storage/sqlite.py:1046-1066

---

## 3. Table Summary

| Category | Tables | Total Columns | Primary Purpose |
|----------|--------|---------------|-----------------|
| Core | 3 | 16 | Projects, entries, metrics |
| Agent Session | 6 | 42 | Multi-agent coordination |
| Documentation | 1 | 10 | Doc change tracking |
| Planning | 6 | 57 | Project planning |
| Doc Mgmt 2.0 | 4 | 42 | Document caching/sync |
| Agent Review | 1 | 10 | Performance tracking |
| Reminders | 1 | 10 | Cooldown management |
| Tool Logging | 1 | 11 | Tool call tracking |
| **TOTAL** | **23** | **198** | **Full system** |

---

## 4. Index Summary

Total indexes: **27+** (including 3 unique constraint indexes)

### Performance Indexes

- Entry queries: `idx_entries_project_ts`
- Session lookups: 3 indexes on `agent_sessions`
- Event history: 2 indexes on `agent_project_events`
- Document changes: 2 indexes per table
- Phase/milestone: Status-based indexes
- Benchmarks: Type and timestamp indexes
- Reminders: Composite session+hash index
- Tool calls: 4 indexes for analysis

---

## 5. Method Implementations

### 5.1 Fully Implemented Methods (17/17)

All abstract methods from `StorageBackend` are fully implemented:

✅ `upsert_project()` - Lines 1091-1139
✅ `fetch_project()` - Lines 1141-1158
✅ `list_projects()` - Lines 1160-1177
✅ `delete_project()` - Lines 1179-1212 (CASCADE deletes all related data)
✅ `insert_entry()` - Lines 1214-1258
✅ `fetch_recent_entries()` - Lines 1327-1403
✅ `query_entries()` - Lines 1405-1548
✅ `upsert_agent_session()` - Lines 1813-1853
✅ `heartbeat_session()` - Lines 1855-1865
✅ `end_session()` - Lines 1867-1877
✅ `get_agent_project()` - Lines 1879-1898
✅ `set_agent_project()` - Lines 1900-1973

### 5.2 Optional Method Implementations

✅ `record_doc_change()` - Lines 1264-1325
✅ `record_agent_report_card()` - Lines 1597-1642

### 5.3 Performance Optimizations

✅ `count_entries()` - Overrides default with proper COUNT query
✅ `count_query_entries()` - Overrides default with proper COUNT query

---

## 6. Connection Management

### File Location: Lines 1260-1295

```python
conn = sqlite3.connect(
    str(self._path),
    check_same_thread=False,
    timeout=30.0,
)
conn.row_factory = sqlite3.Row
# Enable WAL mode for concurrent reads
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
```

**Features**:
- WAL (Write-Ahead Logging) mode for concurrency
- Foreign key enforcement enabled
- 30-second timeout for lock contention
- Row factory for dict-like access

---

## 7. Critical Implementation Details

### 7.1 Metadata Handling

All `metadata`/`meta` columns store JSON as TEXT:
```python
meta_str = json.dumps(meta) if meta else None
```

### 7.2 Timestamp Format

All timestamps stored as TEXT in ISO 8601 format:
```python
ts_iso = ts.isoformat()
```

### 7.3 Boolean Handling

SQLite doesn't have native BOOLEAN type:
```python
# Stored as INTEGER (0/1)
success BOOLEAN NOT NULL DEFAULT 1
```

---

## 8. Known Issues

### 8.1 No PostgreSQL Parity

10 tables missing from PostgreSQL schema:
1. scribe_sessions
2. session_projects
3. agent_recent_projects
4. document_sections
5. custom_templates
6. document_changes
7. sync_status
8. agent_report_cards
9. reminder_history
10. tool_calls

### 8.2 Duplicate Table Definition

Line 1128 has duplicate `CREATE TABLE document_sections` (appears to be dead code)

---

## 9. Testing Coverage

**Recommended Tests**:
- [ ] Foreign key CASCADE behavior
- [ ] Unique constraint enforcement
- [ ] CHECK constraint validation
- [ ] FTS5 trigger synchronization
- [ ] Concurrent write handling (WAL mode)
- [ ] Transaction rollback scenarios

---

**Next**: See `postgres_backend.md` for PostgreSQL comparison and gap analysis
