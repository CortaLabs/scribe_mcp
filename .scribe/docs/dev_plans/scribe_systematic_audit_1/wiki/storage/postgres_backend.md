# PostgreSQL Storage Backend - Gap Analysis

**File**: `storage/postgres.py`
**Schema File**: `db/init.sql`
**LOC**: 260 (postgres.py) + 210 (init.sql)
**Status**: ⚠️ INCOMPLETE (85% parity)
**Last Audited**: 2026-01-05

---

## 1. Executive Summary

The PostgreSQL backend implements core functionality but is **missing 10 tables and 1 critical method** compared to SQLite. This creates a parity gap preventing full feature availability when using PostgreSQL as the storage backend.

### Completion Status

| Component | SQLite | PostgreSQL | Gap |
|-----------|--------|------------|-----|
| Tables | 23 | 13 | **10 missing** |
| Abstract Methods | 17/17 | 16/17 | **1 NotImplementedError** |
| Optional Methods | 2/2 | 2/2 | ✅ Complete |
| Indexes | 27+ | 15 | **12+ missing** |

---

## 2. PostgreSQL-Specific Tables (13 tables)

### 2.1 Core Tables (Parity: ✅ Complete)

#### scribe_projects
**File**: db/init.sql:2-9
**Parity**: ✅ Matches SQLite

```sql
CREATE TABLE IF NOT EXISTS scribe_projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    repo_root TEXT NOT NULL,
    progress_log_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Differences from SQLite**:
- Uses `SERIAL` instead of `INTEGER AUTOINCREMENT`
- Uses `TIMESTAMPTZ` instead of `TEXT` for timestamps

---

#### scribe_entries
**File**: db/init.sql:11-23
**Parity**: ✅ Matches SQLite

```sql
CREATE TABLE IF NOT EXISTS scribe_entries (
    id UUID PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL,
    ts_iso TIMESTAMPTZ NOT NULL,
    emoji TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    meta JSONB,
    raw_line TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Differences from SQLite**:
- Uses `UUID` instead of `TEXT` for id
- Uses `JSONB` instead of `TEXT` for meta (better performance)
- Uses `TIMESTAMPTZ` for all timestamps

---

#### scribe_metrics
**File**: db/init.sql:25-32
**Parity**: ✅ Matches SQLite

---

### 2.2 Agent Session Tables (Parity: ⚠️ Partial - 3/6 tables)

#### ✅ agent_sessions
**File**: db/init.sql:35-42
**Parity**: ⚠️ Schema Mismatch

**SQLite has**:
- `session_id`, `identity_key`, `agent_name`, `agent_key`, `repo_root`, `mode`, `scope_key`, `created_at`, `last_active_at`, `expires_at`

**PostgreSQL has**:
- `id`, `agent_id`, `started_at`, `last_active_at`, `status`, `metadata`

**⚠️ CRITICAL**: Different schema - not compatible!

---

#### ✅ agent_projects
**File**: db/init.sql:47-55
**Parity**: ✅ Matches SQLite

---

#### ✅ agent_project_events
**File**: db/init.sql:59-72
**Parity**: ✅ Matches SQLite (BOOLEAN TRUE instead of 1)

---

#### ❌ **MISSING**: scribe_sessions
**Impact**: HIGH - Session tracking broken in PostgreSQL mode

---

#### ❌ **MISSING**: session_projects
**Impact**: HIGH - Session-scoped project context unavailable

---

#### ❌ **MISSING**: agent_recent_projects
**Impact**: MEDIUM - Agent recent project history lost

---

### 2.3 Documentation Tables (Parity: ✅ Complete - 1/1)

#### ✅ doc_changes
**File**: db/init.sql:77-88
**Parity**: ✅ Matches SQLite

---

### 2.4 Planning Tables (Parity: ✅ Complete - 6/6)

#### ✅ dev_plans
**File**: db/init.sql:92-103
**Parity**: ✅ Matches SQLite

---

#### ✅ phases
**File**: db/init.sql:105-119
**Parity**: ✅ Matches SQLite

---

#### ✅ milestones
**File**: db/init.sql:121-132
**Parity**: ✅ Matches SQLite

---

#### ✅ benchmarks
**File**: db/init.sql:134-147
**Parity**: ✅ Matches SQLite

---

#### ✅ checklists
**File**: db/init.sql:149-163
**Parity**: ✅ Matches SQLite

---

#### ✅ performance_metrics
**File**: db/init.sql:165-176
**Parity**: ✅ Matches SQLite

---

### 2.5 Document Management 2.0 (Parity: ❌ ZERO - 0/4 tables)

#### ❌ **MISSING**: document_sections
**Impact**: CRITICAL - Document caching completely broken
**Used By**: manage_docs tool, read_file tool

---

#### ❌ **MISSING**: custom_templates
**Impact**: HIGH - Custom Jinja2 templates unavailable
**Used By**: Template engine

---

#### ❌ **MISSING**: document_changes
**Impact**: MEDIUM - Document change history lost
**Used By**: Audit trails

---

#### ❌ **MISSING**: sync_status
**Impact**: HIGH - File sync conflict detection broken
**Used By**: Document synchronization

---

### 2.6 Agent Review (Parity: ❌ ZERO - 0/1 table)

#### ❌ **MISSING**: agent_report_cards
**Impact**: HIGH - Agent performance tracking unavailable
**Used By**: Review agent grading system

---

### 2.7 Reminder System (Parity: ❌ ZERO - 0/1 table)

#### ❌ **MISSING**: reminder_history
**Impact**: CRITICAL - Reminder cooldowns broken (file-based fallback only)
**Used By**: Reminder engine

---

### 2.8 Tool Call Logging (Parity: ❌ ZERO - 0/1 table)

#### ❌ **MISSING**: tool_calls
**Impact**: HIGH - Tool usage analytics unavailable
**Used By**: Tool logger

---

### 2.9 Full-Text Search (Parity: ❌ ZERO - 0/1 virtual table)

#### ❌ **MISSING**: document_sections_fts (or equivalent)
**Impact**: CRITICAL - Full-text search completely unavailable
**Note**: PostgreSQL should use `tsvector` instead of FTS5

---

## 3. Missing Tables Summary

| Table Name | Category | Impact | Used By |
|------------|----------|--------|---------|
| scribe_sessions | Agent Session | HIGH | Session tracking |
| session_projects | Agent Session | HIGH | Session context |
| agent_recent_projects | Agent Session | MEDIUM | Recent history |
| document_sections | Doc Mgmt 2.0 | CRITICAL | manage_docs, read_file |
| custom_templates | Doc Mgmt 2.0 | HIGH | Template engine |
| document_changes | Doc Mgmt 2.0 | MEDIUM | Audit trails |
| sync_status | Doc Mgmt 2.0 | HIGH | File sync |
| agent_report_cards | Review | HIGH | Review agent |
| reminder_history | Reminders | CRITICAL | Reminder engine |
| tool_calls | Logging | HIGH | Analytics |

**Total**: 10 tables missing

---

## 4. Method Implementation Status

### 4.1 Fully Implemented (16/17)

All methods delegate to `db/ops.py` module:

✅ `upsert_project()` - Lines 40-55 → `ops.upsert_project()`
✅ `fetch_project()` - Lines 57-61 → `ops.fetch_project_by_name()`
✅ `list_projects()` - Lines 63-67 → `ops.list_projects()`
✅ `insert_entry()` - Lines 86-113 → `ops.insert_entry()`
✅ `record_doc_change()` - Lines 115-140 → `ops.record_doc_change()`
✅ `fetch_recent_entries()` - Lines 142-157 → `ops.fetch_recent_entries()`
✅ `query_entries()` - Lines 159-200 → `ops.query_entries()`
✅ `upsert_agent_session()` - Lines 225-229 → `ops.upsert_agent_session()`
✅ `heartbeat_session()` - Lines 231-235 → `ops.heartbeat_session()`
✅ `end_session()` - Lines 237-241 → `ops.end_session()`
✅ `get_agent_project()` - Lines 243-247 → `ops.get_agent_project()`
✅ `set_agent_project()` - Lines 249-260 → `ops.set_agent_project()`

### 4.2 NOT IMPLEMENTED (1/17)

❌ **delete_project()** - Lines 69-84

```python
async def delete_project(self, name: str) -> bool:
    """Delete a project and all associated data."""
    pool = await self._ensure_pool()

    # Check if project exists first
    project = await self.fetch_project(name)
    if not project:
        return False

    # The actual database operations should be implemented in scribe_mcp.db.ops
    # For now, we'll add a placeholder that raises NotImplementedError
    # TODO: Implement delete_project in scribe_mcp.db.ops module
    raise NotImplementedError(
        "delete_project not yet implemented for PostgreSQL backend. "
        "Add implementation to scribe_mcp.db.ops module."
    )
```

**Impact**: HIGH - Cannot delete projects in PostgreSQL mode
**Fix Location**: Must add to `db/ops.py`

---

## 5. Connection Management

### Pool Configuration
**File**: storage/postgres.py:15-17

```python
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 10
COMMAND_TIMEOUT_SECONDS = 30
```

### Pool Creation
**File**: storage/postgres.py:202-212

```python
self._pool = await asyncpg.create_pool(
    dsn=self._dsn,
    min_size=POOL_MIN_SIZE,
    max_size=POOL_MAX_SIZE,
    command_timeout=COMMAND_TIMEOUT_SECONDS,
)
```

**Benefits**:
- Connection pooling for concurrency
- Automatic connection recycling
- Timeout protection

---

## 6. Data Type Differences

| SQLite | PostgreSQL | Impact |
|--------|-----------|--------|
| `TEXT` timestamps | `TIMESTAMPTZ` | Better timezone handling |
| `TEXT` for JSON | `JSONB` | Better query performance |
| `INTEGER` for IDs | `SERIAL`, `UUID` | Native auto-increment, better distribution |
| `BOOLEAN` (0/1) | `BOOLEAN` | True native type |
| FTS5 virtual tables | `tsvector` + GIN index | Different search syntax |

---

## 7. Missing Indexes

### SQLite Has (27+), PostgreSQL Has (15)

**Missing indexes** (estimated 12+):
- agent_sessions: 2 indexes (identity, last_active, expires)
- agent_project_events: 1 index (agent_id or created_at)
- scribe_sessions tables: All indexes
- document_sections: 2 indexes
- document_changes: 2 indexes
- sync_status: 2 indexes
- reminder_history: 3 indexes
- tool_calls: 4 indexes

---

## 8. Critical Issues

### 8.1 Reminder System Broken

**Cause**: `reminder_history` table missing
**Workaround**: Falls back to file-based cooldown cache
**File**: `data/reminder_cooldowns.json`
**Impact**: Cooldowns not persisted across database migrations

### 8.2 Tool Analytics Unavailable

**Cause**: `tool_calls` table missing
**Impact**: No usage metrics, no performance tracking
**Workaround**: None - feature completely unavailable

### 8.3 Document Management 2.0 Inoperable

**Cause**: All 4 tables missing
**Impact**:
- `manage_docs` may fail in PostgreSQL mode
- Document caching disabled
- Sync conflict detection unavailable
- Custom templates unavailable

### 8.4 Agent Review System Broken

**Cause**: `agent_report_cards` table missing
**Impact**: Cannot persist Review Agent grades in PostgreSQL mode

---

## 9. Migration Complexity Estimate

### High Complexity (Document Management)

**Reason**: 4 tables + FTS5 → tsvector conversion
**Effort**: 40-60 hours
**Considerations**:
- Convert FTS5 triggers to PostgreSQL tsvector
- Rewrite full-text search queries
- Test document sync workflows

### Medium Complexity (Session Tracking)

**Reason**: 3 tables + schema mismatch in agent_sessions
**Effort**: 20-30 hours
**Considerations**:
- Reconcile agent_sessions schema differences
- Migrate session-scoped project tracking
- Test multi-agent concurrency

### Low Complexity (Logging Tables)

**Reason**: 2 simple tables (reminder_history, tool_calls)
**Effort**: 8-12 hours
**Considerations**:
- Straightforward schema porting
- Update reminder engine queries
- Add tool logger PostgreSQL support

### Critical (delete_project)

**Reason**: Single method but complex CASCADE logic
**Effort**: 4-8 hours
**Considerations**:
- Must handle all foreign key relationships
- Test CASCADE DELETE behavior
- Add to db/ops.py module

---

## 10. Recommended Implementation Order

1. **Priority 1 (Critical)**: delete_project() method
2. **Priority 2 (Critical)**: reminder_history table
3. **Priority 3 (High)**: tool_calls table
4. **Priority 4 (High)**: Session tracking tables (3 tables)
5. **Priority 5 (High)**: agent_report_cards table
6. **Priority 6 (Complex)**: Document Management 2.0 (4 tables + FTS)

**Total Effort Estimate**: 80-120 hours

---

## 11. Open Questions

### 11.1 Deprecate PostgreSQL Support?

**Arguments For**:
- 85% incomplete
- High maintenance burden
- SQLite sufficient for most use cases
- No known production users

**Arguments Against**:
- Multi-user deployments need centralized database
- Team collaboration requires shared storage
- Enterprise deployments prefer PostgreSQL
- Async architecture benefits from connection pooling

### 11.2 Partial vs. Full Parity?

**Option A**: Implement only critical tables (reminder_history, delete_project)
**Option B**: Achieve 100% parity with all 23 tables
**Option C**: Deprecate and remove PostgreSQL backend entirely

**Recommendation**: Document trade-offs and let Architect decide

---

## 12. Testing Gaps

**Missing PostgreSQL-specific tests**:
- [ ] Connection pool behavior under load
- [ ] JSONB query performance vs TEXT/JSON
- [ ] TIMESTAMPTZ timezone handling
- [ ] CASCADE DELETE across all relationships
- [ ] Concurrent write conflict resolution
- [ ] Migration path from SQLite to PostgreSQL

---

**Next**: See `SPEC-PG-001-postgres-parity.yaml` for implementation specification
