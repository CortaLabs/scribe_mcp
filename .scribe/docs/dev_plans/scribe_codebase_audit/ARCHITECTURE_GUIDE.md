---
id: scribe_codebase_audit-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_codebase_audit"
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-23'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — scribe_codebase_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-23 05:07:16 UTC

> Architecture guide for scribe_codebase_audit.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
### Context
Scribe MCP v2.1.1 is a production-grade documentation governance system with ~50,000 lines of code. After comprehensive research audit, several technical debt items and optimization opportunities have been identified that require systematic cleanup.

### Current State Assessment

**Critical Issues (Security/Performance):**
1. **No Connection Pooling** - SQLite storage creates/destroys connection for EVERY query (storage/sqlite.py:1568-1622), causing 50-80% unnecessary latency overhead
2. **state.json Dual-Write Pattern** - Every tool invocation writes to both state.json AND database (state/manager.py:115-156), creating redundancy and drift risk

**High Priority Issues (Performance/Maintainability):**
3. **Missing Database Indexes** - `agent` and `emoji` columns in scribe_entries lack indexes, causing full table scans on filtered queries
4. **ResponseFormatter God Class** - 2,934-line class with 33 methods (utils/response.py:57-2990) violates single-responsibility principle
5. **PostgreSQL Implementation Gap** - Only 260 lines vs SQLite's 2,666 lines (75% feature gap), blocking backend flexibility

**Medium Priority Issues (Code Quality):**
6. **Unbounded Table Growth** - scribe_entries has no retention policy at database level
7. **Post-Query Filtering** - Message filtering happens in Python instead of SQL WHERE clauses
8. **Eager Config Loading** - Vector config loaded at import time

### What is NOT in Scope
- **Reminder System** - Research confirms it is production-ready with zero technical debt, excellent architecture, and no refactoring needed (RESEARCH_REMINDER_SYSTEM.md)
- **New Features** - This is a cleanup project, not a feature development effort

### Goals
1. Reduce database operation latency by 50-80% through connection pooling
2. Eliminate state.json redundancy through database consolidation
3. Improve query performance through proper indexing
4. Improve maintainability through code decomposition
5. Establish retention policies for data hygiene

### Success Metrics
| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| DB query latency | Baseline | -50-80% | Benchmark before/after pooling |
| File I/O per tool call | 2+ (state.json) | 0 | Remove state.json writes |
| ResponseFormatter lines | 2,934 | <500 per module | Line count after decomposition |
| Missing indexes | 2+ | 0 | Schema inspection |
| Unbounded tables | 1 | 0 | Retention policy in place |
<!-- ID: requirements_constraints -->
### Functional Requirements

**FR-1: Connection Pooling**
- Implement SQLite connection pool with configurable min/max connections
- Maintain thread safety (SQLite same-thread requirement)
- Add pool lifecycle management (setup on init, close on shutdown)
- Support existing async/sync execution patterns

**FR-2: state.json Elimination**
- Migrate all state.json fields to database tables
- Add backwards compatibility layer for 1-2 releases
- Remove state.json writes from hot path (record_tool)

**FR-3: Index Optimization**
- Add composite indexes for agent+ts_iso and emoji+ts_iso
- Use idempotent _ensure_index() pattern
- Support existing query patterns without breaking changes

**FR-4: ResponseFormatter Decomposition**
- Split into domain-specific formatters (entry, project, file, etc.)
- Maintain backwards-compatible facade
- Enable independent testing of each domain

**FR-5: Retention Policy**
- Implement database-level cleanup for scribe_entries
- Configurable retention period
- Archive-before-delete pattern for audit trail

### Non-Functional Requirements

**NFR-1: Performance**
- 50-80% reduction in database query latency
- Zero file I/O on record_tool hot path
- No regression in startup time (lazy initialization where possible)

**NFR-2: Backwards Compatibility**
- All public APIs must remain stable
- Deprecation warnings before removal
- Migration path for external integrations

**NFR-3: Testability**
- Each phase must have corresponding test coverage
- Existing tests must continue to pass
- New code must follow existing test patterns

### Constraints

1. **No Breaking Changes** - All changes must be backwards compatible
2. **Incremental Delivery** - Each phase independently shippable
3. **Reminder System Frozen** - No modifications to reminder system (confirmed production-ready)
4. **SQLite Primary** - Postgres improvements are lower priority (recommend deprecation)
5. **Existing Patterns** - Must follow established code conventions (StorageBackend API, async patterns)
<!-- ID: architecture_overview -->
### Solution Summary
A phased cleanup approach addressing issues in priority order: Security > Performance > Maintainability. Each phase is independently shippable and builds on prior phases.

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Tool Layer                                │
│  (append_entry, read_file, set_project, manage_docs, etc.)      │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Response Formatting Layer                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │
│  │EntryFormatter│ │FileFormatter │ │ProjectFmt    │  ...        │
│  └──────────────┘ └──────────────┘ └──────────────┘             │
│                    ResponseFormatter (Facade)                    │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Layer                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              SQLiteStorage + Connection Pool              │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                   │   │
│  │  │ Pool    │──│ Pool    │──│ Pool    │ (min=1, max=3)    │   │
│  │  │ Conn 1  │  │ Conn 2  │  │ Conn 3  │                   │   │
│  │  └─────────┘  └─────────┘  └─────────┘                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Database Schema Additions:                                      │
│  - New indexes: idx_entries_agent_ts, idx_entries_emoji_ts       │
│  - state.json fields migrated to agent_sessions table            │
│  - Retention cleanup via scheduled task                          │
└─────────────────────────────────────────────────────────────────┘
```

### Component Breakdown

**1. Connection Pool (NEW - storage/pool.py)**
- Thread-safe SQLite connection pool
- Configurable min/max connections (default: min=1, max=3)
- Lifecycle management (setup/teardown)
- Integrates with existing _execute/_fetchone/_fetchall methods
- Reference pattern: PostgresStorage._ensure_pool()

**2. Decomposed Formatters (NEW - formatters/ directory)**
| Module | Responsibility | Current Location |
|--------|----------------|------------------|
| formatters/base.py | Base utilities, color handling | response.py:244-349 |
| formatters/entry.py | Log entry formatting | response.py:112-187 |
| formatters/file.py | File content formatting | response.py:439-1200 (approx) |
| formatters/project.py | Project list/detail formatting | response.py:1500-1800 (approx) |
| formatters/query.py | Query results formatting | response.py:1800-2200 (approx) |
| formatters/ui.py | Boxes, headers, spinners | response.py:280-436 |
| formatters/dispatcher.py | Route to correct formatter | NEW |
| response.py | Backwards-compatible facade | RETAINED |

**3. Database Schema Extensions**
```sql
-- New indexes (Phase 2)
CREATE INDEX IF NOT EXISTS idx_entries_agent_ts 
    ON scribe_entries(agent, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_emoji_ts 
    ON scribe_entries(emoji, ts_iso DESC);

-- state.json migration (Phase 3)
ALTER TABLE agent_sessions ADD COLUMN recent_tools TEXT;  -- JSON array
ALTER TABLE agent_sessions ADD COLUMN session_started_at TEXT;
ALTER TABLE agent_sessions ADD COLUMN last_activity_at TEXT;
```

**4. Retention Policy (Phase 4)**
- `cleanup_old_entries(project_id, retention_days)` method
- Scheduled via existing cleanup patterns (similar to reminder_history)
- Archive table for audit trail (optional)

### Data Flow Changes

**Before (Current):**
```
Tool call → StateManager.record_tool() → Read state.json → Write state.json
         → Storage.insert_entry() → Open connection → Query → Close connection
```

**After (Target):**
```
Tool call → Storage.insert_entry() → Pool.acquire() → Query → Pool.release()
         (state.json eliminated from hot path)
```

### External Integrations
- No external integration changes required
- All public APIs remain stable
- Internal refactoring only
<!-- ID: detailed_design -->
### 4.1 Connection Pool Design

**File:** `storage/pool.py` (NEW)

```python
class SQLiteConnectionPool:
    """Thread-safe SQLite connection pool with lifecycle management."""
    
    def __init__(self, db_path: Path, min_size: int = 1, max_size: int = 3):
        self._path = db_path
        self._min_size = min_size
        self._max_size = max_size
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=max_size)
        self._pool_lock = threading.Lock()
        self._created = 0
        self._closed = False
    
    def acquire(self) -> sqlite3.Connection:
        """Get a connection from the pool (creates if needed)."""
        
    def release(self, conn: sqlite3.Connection) -> None:
        """Return connection to pool for reuse."""
        
    def close_all(self) -> None:
        """Close all connections (called on shutdown)."""
```

**Integration with SQLiteStorage:**
```python
class SQLiteStorage:
    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path).expanduser()
        self._pool: Optional[SQLiteConnectionPool] = None
    
    async def setup(self) -> None:
        """Initialize pool and run migrations."""
        await self._initialise()
        self._pool = SQLiteConnectionPool(self._path, min_size=1, max_size=3)
    
    async def close(self) -> None:
        """Cleanup pool on shutdown."""
        if self._pool:
            self._pool.close_all()
    
    def _execute_sync(self, query: str, params: tuple[Any, ...]) -> None:
        conn = self._pool.acquire()  # CHANGED: Use pool
        try:
            conn.execute(query, params)
            conn.commit()
        finally:
            self._pool.release(conn)  # CHANGED: Return to pool
```

**Thread Safety Notes:**
- SQLite connections are NOT thread-safe, but our pool manages this
- Each thread acquires exclusive connection, releases when done
- Pool lock prevents race conditions during acquire/release

### 4.2 state.json Migration Design

**Phase 1: Add Database Columns**
```python
# In storage/sqlite.py _initialise()
await self._ensure_column("agent_sessions", "recent_tools", "TEXT")
await self._ensure_column("agent_sessions", "session_started_at", "TEXT")
await self._ensure_column("agent_sessions", "last_activity_at", "TEXT")
```

**Phase 2: Dual-Write (Transition)**
```python
# In state/manager.py record_tool()
# Write to BOTH state.json and database during transition
await self._write_json(data)  # Legacy (deprecation warning logged)
await storage.update_session_activity(session_id, recent_tools, now)  # New
```

**Phase 3: Database-Only**
```python
# In state/manager.py record_tool() - FINAL
async def record_tool(self, tool_name: str, session_id: str) -> State:
    now = utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    await storage.update_session_activity(session_id, tool_name, now)
    # state.json read for fallback only, no writes
```

### 4.3 ResponseFormatter Decomposition Design

**Directory Structure:**
```
utils/
├── response.py              # Facade (retains public API)
└── formatters/
    ├── __init__.py          # Exports all formatters
    ├── base.py              # BaseFormatter, color utilities
    ├── entry.py             # EntryFormatter
    ├── file.py              # FileFormatter  
    ├── project.py           # ProjectFormatter
    ├── query.py             # QueryFormatter
    ├── ui.py                # UIFormatter (boxes, headers)
    └── dispatcher.py        # Routes to correct formatter
```

**Facade Pattern (response.py):**
```python
from utils.formatters import (
    EntryFormatter, FileFormatter, ProjectFormatter,
    QueryFormatter, UIFormatter, FormatterDispatcher
)

class ResponseFormatter:
    """Backwards-compatible facade delegating to domain formatters."""
    
    def __init__(self, token_warning_threshold: int = 4000):
        self._dispatcher = FormatterDispatcher(token_warning_threshold)
    
    def format_entry(self, entry: Dict, **kwargs) -> Dict:
        return self._dispatcher.entry.format(entry, **kwargs)
    
    def format_file_content(self, content: str, **kwargs) -> str:
        return self._dispatcher.file.format(content, **kwargs)
    
    # ... delegate all existing methods to appropriate formatter
```

**Extraction Order (Bottom-Up):**
1. `base.py` - No dependencies (Tier 1)
2. `ui.py` - Depends on base only (Tier 2)
3. `entry.py`, `file.py`, `project.py`, `query.py` - Depend on base+ui (Tier 3)
4. `dispatcher.py` - Depends on all above (Tier 4)
5. `response.py` - Facade using dispatcher (Tier 5)

### 4.4 Retention Policy Design

**Method Signature:**
```python
async def cleanup_old_entries(
    self,
    project_id: Optional[int] = None,  # None = all projects
    retention_days: int = 90,
    archive: bool = True  # Move to archive table before delete
) -> int:  # Returns count of deleted entries
```

**Implementation:**
```python
async def cleanup_old_entries(self, project_id, retention_days, archive):
    cutoff = (utcnow() - timedelta(days=retention_days)).isoformat()
    
    if archive:
        # Move to archive table first
        await self._execute("""
            INSERT INTO scribe_entries_archive
            SELECT * FROM scribe_entries
            WHERE ts_iso < ? AND (project_id = ? OR ? IS NULL)
        """, (cutoff, project_id, project_id))
    
    # Delete from main table
    result = await self._execute("""
        DELETE FROM scribe_entries
        WHERE ts_iso < ? AND (project_id = ? OR ? IS NULL)
    """, (cutoff, project_id, project_id))
    
    return result.rowcount
```

**Scheduling:**
- Call from server.py startup (after journal replay)
- Or via explicit tool invocation
- Configurable via project settings
<!-- ID: directory_structure -->
```
scribe_mcp/
├── storage/
│   ├── base.py              # StorageBackend abstract class
│   ├── sqlite.py            # SQLiteStorage (main backend)
│   ├── postgres.py          # PostgresStorage (deprecated, low priority)
│   └── pool.py              # NEW: SQLiteConnectionPool
├── state/
│   └── manager.py           # StateManager (modified: DB-first, state.json fallback)
├── utils/
│   ├── response.py          # ResponseFormatter (facade, slimmed from 2934→~200 lines)
│   └── formatters/          # NEW: Decomposed formatters
│       ├── __init__.py
│       ├── base.py          # BaseFormatter, utilities
│       ├── entry.py         # EntryFormatter
│       ├── file.py          # FileFormatter
│       ├── project.py       # ProjectFormatter
│       ├── query.py         # QueryFormatter
│       ├── ui.py            # UIFormatter
│       └── dispatcher.py    # FormatterDispatcher
├── tools/                   # No changes needed
├── shared/                  # No changes needed
├── config/                  # No changes needed
└── server.py                # Modified: Pool lifecycle, lazy startup optimizations
```

**New Files (Phase 2-5):**
- `storage/pool.py` - Connection pool implementation
- `utils/formatters/*.py` - 7 new formatter modules

**Modified Files:**
- `storage/sqlite.py` - Use pool, add indexes, add retention
- `state/manager.py` - DB-first writes, deprecate state.json
- `utils/response.py` - Facade pattern, delegate to formatters
- `server.py` - Pool lifecycle, lazy journal replay
<!-- ID: data_storage -->
### Database Schema Changes

**New Indexes (Phase 2):**
```sql
-- Optimize agent-filtered queries
CREATE INDEX IF NOT EXISTS idx_entries_agent_ts 
    ON scribe_entries(agent, ts_iso DESC);

-- Optimize emoji/status-filtered queries  
CREATE INDEX IF NOT EXISTS idx_entries_emoji_ts 
    ON scribe_entries(emoji, ts_iso DESC);

-- Optimize log_type queries (research vs progress)
CREATE INDEX IF NOT EXISTS idx_entries_logtype_ts 
    ON scribe_entries(log_type, ts_iso DESC);

-- Optimize repo-scoped project queries
CREATE INDEX IF NOT EXISTS idx_projects_repo 
    ON scribe_projects(repo_root);
```

**Schema Extensions (Phase 3):**
```sql
-- state.json fields migrated to agent_sessions
ALTER TABLE agent_sessions ADD COLUMN recent_tools TEXT;        -- JSON array
ALTER TABLE agent_sessions ADD COLUMN session_started_at TEXT;  -- Timestamp
ALTER TABLE agent_sessions ADD COLUMN last_activity_at TEXT;    -- Timestamp

-- Archive table for retention (Phase 4)
CREATE TABLE IF NOT EXISTS scribe_entries_archive (
    id TEXT PRIMARY KEY,
    project_id INTEGER,
    ts TEXT,
    ts_iso TEXT,
    emoji TEXT,
    agent TEXT,
    message TEXT,
    meta TEXT,
    raw_line TEXT,
    sha256 TEXT,
    log_type TEXT,
    priority TEXT,
    category TEXT,
    confidence REAL,
    archived_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Connection Pool Configuration

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `pool_min_size` | 1 | 1-10 | Minimum connections to maintain |
| `pool_max_size` | 3 | 1-20 | Maximum concurrent connections |
| `pool_timeout` | 30s | 5-120s | Connection acquire timeout |
| `pool_idle_timeout` | 300s | 60-3600s | Close idle connections after |

### Migration Strategy

**state.json Deprecation Timeline:**
1. **Phase 3a**: Add DB columns, begin dual-write
2. **Phase 3b**: Log deprecation warnings on state.json access
3. **Phase 3c**: Remove state.json writes, read-only fallback
4. **v2.2.0**: Remove state.json entirely

### Data Retention Policy

| Table | Retention | Archive | Notes |
|-------|-----------|---------|-------|
| scribe_entries | 90 days | Yes | Configurable per project |
| reminder_history | 7 days | No | Already implemented |
| agent_sessions | 30 days | No | Cleanup on expiry |
| doc_changes | 500 entries | No | Per-project limit |
<!-- ID: testing_strategy -->
### Test Categories by Phase

**Phase 1 (Connection Pooling):**
- Unit tests for SQLiteConnectionPool (acquire, release, close_all)
- Concurrency tests (multiple threads acquiring connections)
- Integration tests (full tool call with pooled connections)
- Benchmark tests (latency before/after comparison)

**Phase 2 (Indexes):**
- Query plan verification (EXPLAIN QUERY PLAN shows index usage)
- Performance tests (query latency with large datasets)

**Phase 3 (state.json Elimination):**
- Migration tests (data integrity after migration)
- Fallback tests (graceful degradation when DB fails)
- Integration tests (record_tool with DB-only writes)

**Phase 4 (Retention):**
- Unit tests for cleanup_old_entries
- Archive verification tests
- Retention policy configuration tests

**Phase 5 (Formatter Decomposition):**
- Unit tests for each new formatter module
- Integration tests (existing tool outputs unchanged)
- Backwards compatibility tests (facade API)

### Test File Locations

| Phase | Test Files |
|-------|------------|
| 1 | `tests/test_connection_pool.py` (NEW) |
| 2 | `tests/test_storage_indexes.py` (NEW) |
| 3 | `tests/test_state_migration.py` (NEW) |
| 4 | `tests/test_retention_policy.py` (NEW) |
| 5 | `tests/test_formatters/*.py` (NEW) |

### Acceptance Criteria

All phases must satisfy:
1. All existing tests pass (no regressions)
2. New functionality has >80% coverage
3. Integration tests cover main tool paths
4. Benchmark shows expected performance improvement (Phases 1-2)

### Manual QA Checklist

- [ ] Server starts without errors
- [ ] All tools respond correctly
- [ ] No visible changes to tool output format
- [ ] Performance improvement measurable
- [ ] No data corruption after migration
<!-- ID: deployment_operations -->
### Deployment Strategy

**Phased Rollout:**
Each phase is independently deployable. Recommended order:
1. Phase 1 (Indexes) - Quick win, no risk
2. Phase 2 (Connection Pooling) - Highest impact
3. Phase 3 (state.json) - Medium complexity
4. Phase 4 (Retention) - Data hygiene
5. Phase 5 (Decomposition) - Maintainability
6. Phase 6 (Startup) - Optional optimizations

**Rollback Plan:**
- Each phase can be reverted independently
- Database migrations are additive (no destructive changes)
- Facade pattern allows gradual formatter transition

### Configuration Changes

**New Config Options (scribe.yaml):**
```yaml
database:
  pool:
    min_size: 1
    max_size: 3
    timeout_seconds: 30
    idle_timeout_seconds: 300

retention:
  entries:
    enabled: true
    days: 90
    archive: true

state:
  use_database: true  # Phase 3 toggle
  json_fallback: true # Read-only fallback
```

### Monitoring

**Metrics to Track:**
- Database query latency (P50, P95, P99)
- Pool connection utilization
- Pool acquire wait time
- state.json read frequency (during deprecation)
- Retention cleanup counts

### Maintenance Tasks

**Automated:**
- Retention cleanup (daily, via startup or cron)
- Pool idle connection cleanup (ongoing)
- Session expiry (existing mechanism)

**Manual:**
- VACUUM (monthly recommended)
- ANALYZE (after major data changes)
- Backup verification
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| PostgreSQL deprecation decision | Architect | DECIDED | Recommend deprecation - focus on SQLite optimization |
| Retention period default (90 days) | Product | PROPOSED | May need adjustment based on usage patterns |
| Pool size defaults (min=1, max=3) | Architect | PROPOSED | Benchmark to validate |
| state.json removal timeline | Product | PROPOSED | v2.2.0 target |
| Formatter decomposition priority | Architect | DECIDED | Lower priority than performance fixes |

### Architectural Decisions Made

**AD-1: SQLite Connection Pool vs Postgres Migration**
- Decision: Implement SQLite connection pool
- Rationale: Lower effort, sufficient for single-user MCP, closes performance gap
- Alternative rejected: Complete Postgres implementation (4-6 weeks vs 1-2 weeks)

**AD-2: state.json Elimination vs Optimization**  
- Decision: Eliminate state.json, migrate to database
- Rationale: Dual-write is inherently redundant, database is already source of truth
- Alternative rejected: Optimize state.json access (caching) - still leaves drift risk

**AD-3: ResponseFormatter Decomposition Strategy**
- Decision: Facade pattern with gradual extraction
- Rationale: Zero breaking changes, enables incremental refactoring
- Alternative rejected: Full rewrite - too risky, would require updating all tools

**AD-4: Reminder System**
- Decision: NO CHANGES
- Rationale: Research confirms production-ready quality, zero technical debt
- Source: RESEARCH_REMINDER_SYSTEM.md
<!-- ID: references_appendix -->
### Research Documents (Source Material)

| Document | Key Findings | Confidence |
|----------|--------------|------------|
| RESEARCH_PERFORMANCE_AUDIT.md | Connection pooling, state.json dual-write, startup analysis | 90% |
| RESEARCH_DATABASE_OPTIMIZATION.md | Missing indexes, schema inventory, PostgreSQL gap | 95% |
| RESEARCH_REMINDER_SYSTEM.md | Production-ready, zero debt, no changes needed | 95% |

### Code References

| File | Lines | Relevant Finding |
|------|-------|------------------|
| storage/sqlite.py | 1568-1622 | No connection pooling (_connect per query) |
| state/manager.py | 115-156 | state.json dual-write pattern |
| utils/response.py | 57-2990 | ResponseFormatter god class (2934 lines) |
| storage/postgres.py | 1-260 | Incomplete implementation (75% gap) |

### Effort Estimates

| Phase | Effort | Impact | Risk |
|-------|--------|--------|------|
| Phase 1: Indexes | 1-2 hours | Medium | Low |
| Phase 2: Connection Pool | 1-2 weeks | High | Medium |
| Phase 3: state.json | 1 week | Medium | Medium |
| Phase 4: Retention | 3-4 days | Low | Low |
| Phase 5: Decomposition | 2-3 weeks | Low | Medium |
| Phase 6: Startup | 1 week | Low | Low |
| **TOTAL** | **6-8 weeks** | **High** | **Medium** |

### Related Documents

- PHASE_PLAN.md - Detailed execution phases
- CHECKLIST.md - Acceptance criteria checklist
- PROGRESS_LOG.md - Implementation progress tracking
