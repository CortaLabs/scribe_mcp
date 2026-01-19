---
id: scribe_haiku_audit_1-research-storage-modularization-20260108
title: 'Modularization Analysis: Storage Layer'
doc_name: RESEARCH_STORAGE_MODULARIZATION_20260108
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-08'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Modularization Analysis: Storage Layer

## Summary
- **Files Analyzed:** `storage/sqlite.py` (2,400 lines), `storage/base.py` (290 lines)
- **Total Lines:** 2,690 lines
- **Classes:** 2 (SQLiteStorage, StorageBackend)
- **Public Methods:** 45+
- **Complexity Rating:** HIGH
- **Modularization Urgency:** CRITICAL

---

## Executive Finding

The storage layer exhibits **severe architectural bloat** with high duplication and mixed responsibilities across multiple concerns. `sqlite.py` has grown into a monolithic 2,400-line implementation that combines:

1. **Query building logic** (repeated 4+ times across methods)
2. **Schema initialization & migrations** (480 lines)
3. **Session management** (30+ methods)
4. **Tool metrics collection** (10+ methods)
5. **Low-level SQLite helpers** (async/sync pairs)

This creates maintenance burden, testing complexity, and makes reasoning about the code difficult.

---

## Logical Clusters Identified

### Cluster 1: Query Builder Pattern (DUPLICATED)
**Lines:** ~150 lines of similar logic scattered across 4 methods
**Methods:**
- `fetch_recent_entries` (lines 354-454)
- `query_entries` (lines 456-535)
- `count_entries` (lines 537-598)
- `count_query_entries` (lines 600-681)

**Purpose:** Build WHERE clauses with filters for agent, emoji, timestamp, priority, category, confidence, log_type

**Extraction Candidate:** YES
**Proposed Module:** `storage/query_builder.py`
**Dependencies:** Needs message_matches from utils.search
**Dependents:** All four query methods above

**Problem Identified:**
```python
# Pattern repeats in all 4 methods:
clauses = ["project_id = ?"]
params: List[Any] = [project.id]

if agent:
    clauses.append("agent = ?")
    params.append(agent)
# ... repeated for emoji, timestamp, priority, category, confidence, log_type

where_clause = " AND ".join(clauses)
```

**Minimal Viable Extraction:**
```python
# storage/query_builder.py
class QueryBuilder:
    def __init__(self, project_id: int):
        self.clauses = ["project_id = ?"]
        self.params = [project_id]
    
    def add_agent_filter(self, agent: str) -> 'QueryBuilder':
        self.clauses.append("agent = ?")
        self.params.append(agent)
        return self
    
    # ... similar for emoji, timestamp, priority, etc.
    
    def build(self) -> Tuple[str, List[Any]]:
        where_clause = " AND ".join(self.clauses)
        return where_clause, tuple(self.params)
```

**Impact:** Reduces lines of code by ~80, improves testability, centralizes filter logic.

---

### Cluster 2: Schema Initialization & Migrations (MONOLITHIC)
**Lines:** 480 lines (lines 683-1163)
**Current Home:** `async def _initialise(self)`

**Purpose:** Create 30+ tables, set up indexes, handle schema migrations

**Sub-clusters within:**
1. **Core tables** (scribe_projects, scribe_entries, scribe_metrics)
2. **Session tables** (agent_sessions, agent_projects, agent_project_events, scribe_sessions)
3. **Dev plan infrastructure** (dev_plans, phases, milestones, benchmarks, checklists, performance_metrics)
4. **Document management 2.0** (document_sections, custom_templates, document_changes, sync_status)
5. **Tool logging** (tool_calls) - ~50 lines

**Extraction Candidate:** PARTIAL YES
**Proposed Modules:**
- `storage/migrations/schema_bootstrap.py` - Core table creation
- `storage/migrations/session_management.py` - Session tables
- `storage/migrations/dev_plan_infrastructure.py` - Dev plan tables
- `storage/migrations/document_management.py` - Document tables

**Reasoning:** Separate concerns avoid the need to modify one massive method. Each migration module can have:
- `create_tables()` - idempotent table creation
- `create_indexes()` - separate index setup
- `migrate_*()` - versioned migrations

**Risk:** Migration coordination becomes critical. Need a migration registry.

---

### Cluster 3: Session Management (30+ Methods)
**Lines:** ~600 lines (scattered throughout)
**Methods:**
- `upsert_agent_session`, `get_agent_session`, `delete_agent_session`
- `record_agent_project_event`, `get_agent_project_events`
- `set_agent_project`, `get_agent_project`, `set_session_project`, `get_session_project`
- `upsert_agent_recent_project`, `get_agent_recent_projects`
- `heartbeat_session`, `end_session`, `get_session_by_transport`
- `get_or_create_agent_session`, `get_all_agent_sessions`, `cleanup_expired_sessions`

**Purpose:** Track agent identity, project context, session lifecycle

**Extraction Candidate:** YES
**Proposed Module:** `storage/session_manager.py`
**Dependencies:** Models, base StorageBackend (for write_lock)
**Dependents:** All Scribe tools that need agent context

**Design Pattern:**
```python
class SessionManager:
    def __init__(self, storage_backend: SQLiteStorage):
        self._backend = storage_backend
    
    async def create_session(self, ...) -> str:
        ...
    
    async def get_current_project(self, agent_id: str) -> Optional[str]:
        ...
    
    async def heartbeat(self, session_id: str) -> None:
        ...
```

**Impact:** Reduces SQLiteStorage to ~1,800 lines. SessionManager becomes reusable for PostgreSQL backend.

---

### Cluster 4: Tool Metrics Collection (10+ Methods)
**Lines:** ~200 lines
**Methods:**
- `record_tool_call`, `record_tool_call_sync` (async/sync pair)
- `get_session_tool_calls`
- `get_tool_metrics`

**Purpose:** Track tool execution performance, status, format requests

**Extraction Candidate:** MAYBE
**Proposed Module:** `storage/tool_metrics.py` (optional, lower priority)
**Dependencies:** Low
**Dependents:** Server finalization code

**Rationale:** Could extract, but tight coupling with session tracking makes it less critical. Leave in place unless tool metrics becomes larger.

---

### Cluster 5: Low-Level Helper Methods (Async/Sync Pairs)
**Lines:** ~50 lines
**Methods:**
- `_execute` / `_execute_sync`
- `_execute_many` / `_execute_many_sync`
- `_fetchone` / `_fetchone_sync`
- `_fetchall` / `_fetchall_sync`
- `_connect`

**Purpose:** Thin async wrappers over SQLite sync calls

**Extraction Candidate:** NO
**Reasoning:** These are necessary internal implementation details. Extracting them provides no value and adds indirection. Keep with SQLiteStorage.

---

## Shared Code Opportunities

### 1. Query Filter Pattern (CRITICAL)
**Appears in:** fetch_recent_entries, query_entries, count_entries, count_query_entries
**Shared Logic:** "Build WHERE clause with N filters"
**Proposal:** Extract to `utils/storage_filters.py` or `storage/query_builder.py`
**Lines Saved:** ~80

### 2. Async/Sync Wrapper Pattern
**Appears in:** All methods using asyncio.to_thread + _*_sync pattern
**Current Implementation:** Manual asyncio.to_thread wrapping
**Proposal:** Could be unified, but currently working well. LOW priority.

### 3. Result Marshaling Pattern (meta JSON loading)
**Appears in:** fetch_recent_entries, query_entries, and others
**Pattern:**
```python
meta_value = json.loads(row["meta"]) if row["meta"] else {}
```
**Proposal:** Extract to utility function `utils/result_marshaling.py`
**Lines Saved:** ~10-15 across codebase

---

## Existing Utilities to Leverage

- `utils/search.py` - `message_matches()` function (already used in query_entries)
- `utils/time.py` - `format_utc()`, `utcnow()` (already used)
- Could add: `utils/query_filters.py` for filter building
- Could add: `utils/result_marshaling.py` for JSON unmarshaling

---

## Recommended Extractions (Priority Order)

### 1. **Query Builder** - HIGHEST PRIORITY
- **Why:** Eliminates 150 lines of duplication across 4 critical methods
- **Complexity:** LOW (straightforward builder pattern)
- **Risk:** LOW (internal refactoring, no API changes)
- **Est. Scope:** 60-80 lines for `storage/query_builder.py`
- **Testing:** Medium (3-4 test methods per filter type)
- **Files Affected:** 4 methods in sqlite.py, 0 new dependencies

### 2. **Session Manager** - HIGH PRIORITY
- **Why:** Separates 600 lines of session concern from core storage
- **Complexity:** MEDIUM (manages state, concurrency)
- **Risk:** MEDIUM (affects agent context tracking)
- **Est. Scope:** 200-250 lines for `storage/session_manager.py`
- **Testing:** High (session lifecycle, race conditions)
- **Files Affected:** 30+ methods in sqlite.py, becomes dependency for all tools

### 3. **Schema Migration Registry** - MEDIUM PRIORITY
- **Why:** Makes `_initialise()` composable and testable
- **Complexity:** MEDIUM (migration orchestration)
- **Risk:** MEDIUM (critical infrastructure)
- **Est. Scope:** 100-150 lines for registry + 50-100 lines per migration module
- **Testing:** High (must verify idempotency, ordering)
- **Files Affected:** Split 480 lines across 4-5 files

### 4. **Result Marshaling Utilities** - LOW PRIORITY
- **Why:** DRY principle, makes testing easier
- **Complexity:** LOW (simple utility functions)
- **Risk:** LOW
- **Est. Scope:** 20-30 lines for `utils/result_marshaling.py`
- **Testing:** LOW (pure functions)

---

## Risks & Considerations

### Risk 1: Query Builder Complexity
**Issue:** Different queries need different filter sets (some need message matching, others don't)
**Mitigation:** Use builder pattern with optional methods; let caller decide what to include

### Risk 2: Session Manager Dependency Injection
**Issue:** SessionManager needs access to SQLiteStorage._write_lock for thread safety
**Mitigation:** Pass lock to SessionManager, or create facade pattern where SQLiteStorage delegates to SessionManager

### Risk 3: Migration Ordering & Idempotency
**Issue:** Extracting migrations into separate modules requires careful orchestration
**Current State:** All tables created in one atomic batch (good)
**Proposal:** Keep atomic batch, but call registered migration modules in order
**Mitigation:** Build migration registry with version tracking

### Risk 4: PostgreSQL Backend Compatibility
**Issue:** These extractions must work with both SQLite and PostgreSQL backends
**Current State:** QueryBuilder is backend-agnostic (just builds WHERE clauses) ✓
**SessionManager:** Works with any backend via StorageBackend interface ✓
**Mitigation:** Keep all extractions backend-agnostic

### Risk 5: Circular Import Potential
**Issue:** storage/session_manager.py needs StorageBackend interface, but StorageBackend is in base.py
**Mitigation:** Session manager receives storage_backend instance, doesn't import StorageBackend class

---

## Architecture Constraints (Non-Negotiable)

### Constraint 1: Shared Utility Pattern
Per COORDINATION_PROTOCOL.md: "If two modules need similar functionality, propose a shared utility."
**Application:** QueryBuilder goes to `storage/query_builder.py` (extraction within storage module, not utils)

### Constraint 2: Clean Naming
Per COORDINATION_PROTOCOL.md: "Every proposed module must follow directory conventions."
**Naming:**
- ✓ `storage/query_builder.py` - domain-specific extraction
- ✓ `storage/session_manager.py` - domain-specific extraction
- ✓ `storage/migrations/schema_bootstrap.py` - migration submodule
- ✓ `utils/result_marshaling.py` - cross-cutting utility

### Constraint 3: No Parallel Files
Per CLAUDE.md COMMANDMENT #0.5: "NEVER create parallel or replacement files."
**Current Approach:** All extractions are additive, not replacing. SQLiteStorage will delegate to new modules.

### Constraint 4: Single Responsibility
Each extracted module must have one clear purpose:
- QueryBuilder: Build WHERE clauses
- SessionManager: Manage agent sessions
- Migrations: Create/maintain schema
- ResultMarshaling: Unmarshal JSON results

---

## Dependency Map (Before Extraction)

```
storage/sqlite.py (2400 lines)
  ├─ storage/base.py (interface)
  ├─ storage/models.py (data classes)
  ├─ utils/time.py (format_utc, utcnow)
  └─ utils/search.py (message_matches)
```

## Dependency Map (After Extraction)

```
storage/sqlite.py (1800 lines - core implementation)
  ├─ storage/base.py (interface)
  ├─ storage/models.py (data classes)
  ├─ storage/query_builder.py (query logic)
  ├─ storage/session_manager.py (session logic)
  ├─ storage/migrations/*.py (schema modules)
  ├─ utils/time.py (time utilities)
  ├─ utils/search.py (search utilities)
  └─ utils/result_marshaling.py (result utils)

storage/query_builder.py (80 lines)
  └─ utils/search.py (message_matches)

storage/session_manager.py (250 lines)
  └─ storage/models.py (data classes)

tools/*.py (tools using storage)
  └─ storage/session_manager.py (get current project context)
```

---

## Questions for Architect

1. **Migration Versioning:** Should we track migration versions in DB to support incremental upgrades, or keep atomic table creation?

2. **SessionManager Ownership:** Should SessionManager be instantiated once in server.py and injected, or should SQLiteStorage own it?

3. **Query Builder Fluency:** Is fluent builder pattern (method chaining) preferred over constructor with filters dict?

4. **Extraction Sequencing:** Should we extract QueryBuilder first (lowest risk) or SessionManager first (higher value)?

5. **Schema Modularization Depth:** Should we extract to `storage/migrations/` subdirectory or keep all migration code in one file with sections?

---

## Confidence Assessment

| Finding | Confidence | Basis |
|---------|-----------|-------|
| Query duplication exists | 0.95 | Direct code inspection - identical pattern in 4 methods |
| SessionManager extraction feasible | 0.90 | 30+ methods all operate on session tables, low coupling to other concerns |
| Migration extraction possible | 0.85 | 480 lines clearly divided into 5 table groups, but requires orchestration |
| No breaking API changes required | 0.98 | All extractions are internal refactoring, StorageBackend interface unchanged |
| PostgreSQL compatible | 0.88 | QueryBuilder is backend-agnostic, but schema modules need pg validation |

---

## Next Steps for Architect

1. **Review extraction priorities** - confirm QueryBuilder > SessionManager > Migrations order
2. **Design SessionManager facade** - decide on dependency injection pattern
3. **Plan QueryBuilder API** - fluent vs dict-based filter specification
4. **Schema migration strategy** - versioning, rollback capability, etc.
5. **Create implementation checklist** - per extraction, list files to create, edit, delete
