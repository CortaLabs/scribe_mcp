---
id: scribe_codebase_audit-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_codebase_audit"
doc_name: phase_plan
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

# ⚙️ Phase Plan — scribe_codebase_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-23 05:07:16 UTC

> Execution roadmap for scribe_codebase_audit.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Effort | Confidence |
|-------|------|------------------|--------|------------|
| Phase 1 | Quick performance wins (indexes) | 4 new indexes, query optimization | 1-2 hours | 0.95 |
| Phase 2 | Connection pooling | SQLiteConnectionPool, 50-80% latency reduction | 1-2 weeks | 0.85 |
| Phase 3 | state.json elimination | DB migration, deprecation path | 1 week | 0.80 |
| Phase 4 | Data retention | Cleanup policy, archive table | 3-4 days | 0.90 |
| Phase 5 | Code decomposition | ResponseFormatter split into 7 modules | 2-3 weeks | 0.75 |
| Phase 6 | Startup optimization | Lazy loading, deferred init | 1 week | 0.85 |

**Priority Order:** Security > Performance > Maintainability
**Total Estimated Effort:** 6-8 weeks
**Expected Performance Gain:** 50-80% database latency reduction

### Phase Dependencies

```
Phase 1 (Indexes) ─────────────────────────────────────────┐
                                                           │
Phase 2 (Connection Pool) ─────────────────────────────────┤
         │                                                 │
         ▼                                                 ▼
Phase 3 (state.json) ─────────────────────────────────> Phase 6 (Startup)
         │
         ▼
Phase 4 (Retention)

Phase 5 (Decomposition) ─── Independent, can run in parallel
```

**Notes:**
- Phases 1-2 are independent and can start immediately
- Phase 3 depends on Phase 2 (pool must be stable before state changes)
- Phase 4 depends on Phase 3 (uses new DB patterns)
- Phase 5 is independent (can run in parallel with any phase)
- Phase 6 depends on Phases 2-4 (startup changes after core optimizations)
<!-- ID: phase_0 -->
**Objective:** Add missing database indexes to eliminate full table scans on common query patterns.

**Effort:** 1-2 hours | **Risk:** Low | **Impact:** Medium

### Task Packages

#### Task 1.1: Add Agent Index
**Scope:** Add composite index for agent-filtered queries
**Files to Modify:** `storage/sqlite.py` (lines ~1065-1075, _initialise method)
**Dependencies:** None

**Specifications:**
1. Add to _initialise() after existing index creation:
```python
await self._ensure_index(
    "scribe_entries", 
    "idx_entries_agent_ts",
    "agent, ts_iso DESC"
)
```

**Verification:**
- [ ] Server starts without errors
- [ ] `EXPLAIN QUERY PLAN SELECT * FROM scribe_entries WHERE agent='test' ORDER BY ts_iso DESC` shows index usage

**Out of Scope:** Do NOT modify any query logic, only add index creation

---

#### Task 1.2: Add Emoji Index
**Scope:** Add composite index for emoji/status-filtered queries
**Files to Modify:** `storage/sqlite.py` (same location as 1.1)
**Dependencies:** Task 1.1

**Specifications:**
1. Add immediately after Task 1.1 index:
```python
await self._ensure_index(
    "scribe_entries",
    "idx_entries_emoji_ts", 
    "emoji, ts_iso DESC"
)
```

**Verification:**
- [ ] Server starts without errors
- [ ] `EXPLAIN QUERY PLAN SELECT * FROM scribe_entries WHERE emoji='success' ORDER BY ts_iso DESC` shows index usage

---

#### Task 1.3: Add Log Type and Repo Indexes
**Scope:** Add remaining optimization indexes
**Files to Modify:** `storage/sqlite.py` (same location)
**Dependencies:** Task 1.2

**Specifications:**
1. Add log_type index:
```python
await self._ensure_index(
    "scribe_entries",
    "idx_entries_logtype_ts",
    "log_type, ts_iso DESC"
)
```

2. Add repo_root index on projects:
```python
await self._ensure_index(
    "scribe_projects",
    "idx_projects_repo",
    "repo_root"
)
```

**Verification:**
- [ ] All 4 new indexes appear in `PRAGMA index_list(scribe_entries)` and `PRAGMA index_list(scribe_projects)`
- [ ] All existing tests pass

---

### Phase 1 Acceptance Criteria
- [ ] 4 new indexes created idempotently
- [ ] No regression in existing tests
- [ ] Server startup time unchanged
- [ ] Query plans show index usage for agent/emoji/log_type filters
<!-- ID: phase_1 -->
**Objective:** Implement SQLite connection pooling to eliminate connection overhead on every query.

**Effort:** 1-2 weeks | **Risk:** Medium | **Impact:** HIGH (50-80% latency reduction)

### Task Packages

#### Task 2.1: Create Connection Pool Module
**Scope:** Create new `storage/pool.py` with SQLiteConnectionPool class
**Files to Modify:** NEW FILE: `storage/pool.py`
**Dependencies:** None

**Specifications:**
1. Create `SQLiteConnectionPool` class with:
   - `__init__(db_path: Path, min_size: int = 1, max_size: int = 3)`
   - `acquire() -> sqlite3.Connection` - Get connection from pool
   - `release(conn: sqlite3.Connection) -> None` - Return to pool
   - `close_all() -> None` - Close all connections (shutdown)
   - Thread-safe with `threading.Lock`

2. Connection setup must replicate existing pattern:
   - `detect_types=sqlite3.PARSE_DECLTYPES`
   - `timeout=SQLITE_TIMEOUT_SECONDS`
   - `check_same_thread=False`
   - `row_factory = sqlite3.Row`
   - `PRAGMA foreign_keys = ON`
   - `PRAGMA busy_timeout = SQLITE_BUSY_TIMEOUT_MS`

**Verification:**
- [ ] Unit tests for acquire/release cycle
- [ ] Concurrency test with multiple threads
- [ ] Pool respects max_size limit

**Out of Scope:** Integration with SQLiteStorage (Task 2.2)

---

#### Task 2.2: Integrate Pool with SQLiteStorage
**Scope:** Replace _connect() pattern with pool acquire/release
**Files to Modify:** `storage/sqlite.py` (lines 1565-1622)
**Dependencies:** Task 2.1

**Specifications:**
1. Add pool attribute to SQLiteStorage:
```python
def __init__(self, db_path: Path | str) -> None:
    self._path = Path(db_path).expanduser()
    self._pool: Optional[SQLiteConnectionPool] = None
```

2. Initialize pool in setup():
```python
async def setup(self) -> None:
    await self._initialise()
    self._pool = SQLiteConnectionPool(self._path, min_size=1, max_size=3)
```

3. Replace all 4 sync methods (lines 1568-1610):
```python
def _execute_sync(self, query: str, params: tuple[Any, ...]) -> None:
    conn = self._pool.acquire()  # Was: self._connect()
    try:
        conn.execute(query, params)
        conn.commit()
    finally:
        self._pool.release(conn)  # Was: conn.close()
```

4. Add close() method for pool cleanup

**Verification:**
- [ ] All existing tests pass
- [ ] Server starts and tools work normally
- [ ] Benchmark shows latency improvement

---

#### Task 2.3: Add Pool Lifecycle to Server
**Scope:** Ensure pool is properly closed on server shutdown
**Files to Modify:** `server.py`
**Dependencies:** Task 2.2

**Specifications:**
1. Add shutdown handler to close pool:
```python
async def _shutdown():
    if backend and hasattr(backend, 'close'):
        await backend.close()
```

2. Register with MCP server lifecycle

**Verification:**
- [ ] Clean shutdown with no resource leaks
- [ ] No "connection not closed" warnings

---

#### Task 2.4: Benchmark and Validate
**Scope:** Create benchmark script and measure improvement
**Files to Modify:** NEW FILE: `tests/benchmark_connection_pool.py`
**Dependencies:** Task 2.3

**Specifications:**
1. Create benchmark measuring:
   - append_entry latency (before/after)
   - query_entries latency (before/after)
   - Concurrent operations performance

2. Document baseline and improvement metrics

**Verification:**
- [ ] Documented 50-80% latency improvement
- [ ] No regression under load

---

### Phase 2 Acceptance Criteria
- [ ] SQLiteConnectionPool module complete with tests
- [ ] All existing tests pass
- [ ] Pool properly integrated with SQLiteStorage
- [ ] Clean server shutdown
- [ ] Benchmark shows 50-80% latency improvement
<!-- ID: milestone_tracking -->
**Objective:** Migrate state.json fields to database and eliminate dual-write pattern.

**Effort:** 1 week | **Risk:** Medium | **Impact:** Medium (removes file I/O from hot path)

### Task Packages

#### Task 3.1: Add Database Columns
**Scope:** Add state.json fields to agent_sessions table
**Files to Modify:** `storage/sqlite.py` (_initialise method)
**Dependencies:** Phase 2 complete

**Specifications:**
1. Add columns using idempotent migration:
```python
await self._ensure_column("agent_sessions", "recent_tools", "TEXT")
await self._ensure_column("agent_sessions", "session_started_at", "TEXT")
await self._ensure_column("agent_sessions", "last_activity_at", "TEXT")
```

**Verification:**
- [ ] Columns exist after server restart
- [ ] Existing sessions unaffected

---

#### Task 3.2: Add Storage Methods
**Scope:** Add methods to read/write session activity data
**Files to Modify:** `storage/sqlite.py`, `storage/base.py`
**Dependencies:** Task 3.1

**Specifications:**
1. Add abstract method to StorageBackend:
```python
async def update_session_activity(
    self, session_id: str, tool_name: str, timestamp: str
) -> None: ...
```

2. Implement in SQLiteStorage:
```python
async def update_session_activity(self, session_id, tool_name, timestamp):
    # Update recent_tools JSON array
    # Update last_activity_at
    # Update session_started_at if needed
```

**Verification:**
- [ ] Unit tests for update_session_activity
- [ ] Data persists across restarts

---

#### Task 3.3: Dual-Write Transition
**Scope:** Update StateManager to write to both locations
**Files to Modify:** `state/manager.py`
**Dependencies:** Task 3.2

**Specifications:**
1. Modify record_tool() to:
   - Write to database (new path)
   - Write to state.json (legacy, with deprecation warning)
   - Log deprecation on state.json access

2. Add deprecation warning:
```python
logger.warning(
    "state.json writes are deprecated and will be removed in v2.2.0. "
    "Data is now stored in the database."
)
```

**Verification:**
- [ ] Both locations updated
- [ ] Deprecation warning appears in logs
- [ ] All existing functionality works

---

#### Task 3.4: Database-Only Mode
**Scope:** Remove state.json writes, keep read-only fallback
**Files to Modify:** `state/manager.py`
**Dependencies:** Task 3.3, one release cycle

**Specifications:**
1. Remove state.json writes from record_tool()
2. Keep read-only fallback for migration:
```python
async def record_tool(self, tool_name: str, session_id: str) -> State:
    # Database-only write
    await storage.update_session_activity(session_id, tool_name, now)
    # Read from DB, fallback to state.json for old data
    return await self._build_state_from_db_with_fallback()
```

**Verification:**
- [ ] No state.json writes
- [ ] Old data still accessible via fallback
- [ ] Performance improvement measurable

---

### Phase 3 Acceptance Criteria
- [ ] Database columns added and working
- [ ] record_tool() writes to database only
- [ ] state.json read-only fallback for migration
- [ ] Zero file I/O on hot path
- [ ] All existing tests pass
<!-- ID: retro_notes -->
**Objective:** Implement database-level cleanup for scribe_entries to prevent unbounded growth.

**Effort:** 3-4 days | **Risk:** Low | **Impact:** Low (data hygiene, long-term health)

### Task Packages

#### Task 4.1: Create Archive Table
**Scope:** Add scribe_entries_archive table for audit trail
**Files to Modify:** `storage/sqlite.py` (_initialise method)
**Dependencies:** Phase 3 complete

**Specifications:**
1. Create archive table (idempotent):
```python
await self._execute("""
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
    )
""")
```

**Verification:**
- [ ] Archive table exists after restart
- [ ] Schema matches scribe_entries + archived_at column

---

#### Task 4.2: Implement Cleanup Method
**Scope:** Add cleanup_old_entries() to SQLiteStorage
**Files to Modify:** `storage/sqlite.py`, `storage/base.py`
**Dependencies:** Task 4.1

**Specifications:**
1. Add abstract method to StorageBackend:
```python
async def cleanup_old_entries(
    self,
    project_id: Optional[int] = None,
    retention_days: int = 90,
    archive: bool = True
) -> int:
    """Remove old entries, optionally archiving first. Returns deleted count."""
```

2. Implement in SQLiteStorage with archive-then-delete pattern

**Verification:**
- [ ] Entries older than cutoff are deleted
- [ ] Archived entries exist in archive table
- [ ] Returns correct count
- [ ] Works with project_id filter

---

#### Task 4.3: Add Scheduled Cleanup
**Scope:** Call cleanup during server startup
**Files to Modify:** `server.py`
**Dependencies:** Task 4.2

**Specifications:**
1. Add cleanup call to startup (after journal replay):
```python
async def _startup():
    # ... existing startup ...
    # Cleanup old entries (non-blocking)
    deleted = await backend.cleanup_old_entries(retention_days=90)
    logger.info(f"Cleaned up {deleted} old entries")
```

2. Make cleanup configurable via settings

**Verification:**
- [ ] Cleanup runs on startup
- [ ] Does not block startup significantly
- [ ] Respects configuration

---

### Phase 4 Acceptance Criteria
- [ ] Archive table created
- [ ] cleanup_old_entries() works correctly
- [ ] Scheduled cleanup on startup
- [ ] Configurable retention period
- [ ] All existing tests pass

---

## Phase 5 - ResponseFormatter Decomposition
<!-- ID: phase_5 -->

**Objective:** Split 2,934-line ResponseFormatter god class into focused domain modules.

**Effort:** 2-3 weeks | **Risk:** Medium | **Impact:** Low (maintainability, not performance)

### Task Packages

#### Task 5.1: Create Base Formatter Module
**Scope:** Extract base utilities and color handling
**Files to Modify:** NEW: `utils/formatters/base.py`, `utils/formatters/__init__.py`
**Dependencies:** None (can run in parallel with other phases)

**Specifications:**
1. Create `utils/formatters/` directory
2. Extract from response.py:
   - `_get_use_ansi_colors()` (lines 41-54)
   - Color constants and utilities
   - Base formatter class with common methods

**Verification:**
- [ ] BaseFormatter importable
- [ ] Color utilities work correctly

---

#### Task 5.2: Create UI Formatter Module
**Scope:** Extract box drawing, headers, footers
**Files to Modify:** NEW: `utils/formatters/ui.py`
**Dependencies:** Task 5.1

**Specifications:**
1. Extract from response.py:
   - `_create_header_box()` (lines 280-349)
   - `_create_footer_box()` (lines 351-436)
   - `_add_line_numbers()` (lines 244-278)

**Verification:**
- [ ] UIFormatter produces identical output
- [ ] Unit tests pass

---

#### Task 5.3: Create Domain Formatters
**Scope:** Extract entry, file, project, query formatters
**Files to Modify:** NEW: `utils/formatters/entry.py`, `file.py`, `project.py`, `query.py`
**Dependencies:** Tasks 5.1, 5.2

**Specifications:**
1. EntryFormatter: format_entry, _format_full_entry, _format_compact_entry
2. FileFormatter: file content formatting methods
3. ProjectFormatter: project list/detail formatting
4. QueryFormatter: query results formatting

Each formatter:
- Inherits from BaseFormatter
- Uses UIFormatter for box drawing
- Has own unit tests

**Verification:**
- [ ] Each formatter produces identical output to original
- [ ] All domain tests pass

---

#### Task 5.4: Create Dispatcher and Facade
**Scope:** Create dispatcher and update response.py as facade
**Files to Modify:** NEW: `utils/formatters/dispatcher.py`, UPDATE: `utils/response.py`
**Dependencies:** Task 5.3

**Specifications:**
1. Create FormatterDispatcher:
```python
class FormatterDispatcher:
    def __init__(self, token_threshold: int = 4000):
        self.entry = EntryFormatter(token_threshold)
        self.file = FileFormatter(token_threshold)
        self.project = ProjectFormatter(token_threshold)
        self.query = QueryFormatter(token_threshold)
        self.ui = UIFormatter()
```

2. Update ResponseFormatter as facade:
```python
class ResponseFormatter:
    def __init__(self, token_warning_threshold: int = 4000):
        self._dispatcher = FormatterDispatcher(token_warning_threshold)
    
    def format_entry(self, entry, **kwargs):
        return self._dispatcher.entry.format(entry, **kwargs)
```

**Verification:**
- [ ] ResponseFormatter API unchanged
- [ ] All tool outputs unchanged
- [ ] All integration tests pass

---

### Phase 5 Acceptance Criteria
- [ ] 7 new formatter modules created
- [ ] ResponseFormatter slimmed from 2,934 to ~200 lines
- [ ] Zero breaking changes to public API
- [ ] All existing tests pass
- [ ] New modules have dedicated tests

---

## Phase 6 - Startup Optimization
<!-- ID: phase_6 -->

**Objective:** Optimize server startup time through lazy loading and deferred initialization.

**Effort:** 1 week | **Risk:** Low | **Impact:** Low (startup time reduction)

### Task Packages

#### Task 6.1: Lazy Journal Replay
**Scope:** Move journal replay to background task
**Files to Modify:** `server.py`
**Dependencies:** Phases 2-4 complete

**Specifications:**
1. Move journal replay from _startup() to background:
```python
async def _startup():
    # ... existing startup (minus journal replay) ...
    # Start background journal replay
    asyncio.create_task(_replay_journals_background())

async def _replay_journals_background():
    """Replay journals in background, don't block startup."""
    # Existing replay logic
```

**Verification:**
- [ ] Server responds immediately after startup
- [ ] Journals still replayed eventually

---

#### Task 6.2: Skip Completed Migrations
**Scope:** Add flag to skip already-completed migrations
**Files to Modify:** `storage/sqlite.py`
**Dependencies:** Task 6.1

**Specifications:**
1. Track migration status:
```python
await self._execute("""
    CREATE TABLE IF NOT EXISTS scribe_migrations (
        name TEXT PRIMARY KEY,
        completed_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
""")
```

2. Check before running migrations:
```python
if await self._migration_complete("legacy_state_migration"):
    return  # Skip
# Run migration
await self._mark_migration_complete("legacy_state_migration")
```

**Verification:**
- [ ] Migrations only run once
- [ ] Startup time reduced on subsequent runs

---

#### Task 6.3: Lazy Config Loading
**Scope:** Defer vector config loading until needed
**Files to Modify:** `config/vector_config.py` or equivalent
**Dependencies:** Task 6.2

**Specifications:**
1. Move config loading from import-time to first-access
2. Use lazy property pattern

**Verification:**
- [ ] Config not loaded until first use
- [ ] No behavioral changes

---

### Phase 6 Acceptance Criteria
- [ ] Journal replay in background
- [ ] Migrations tracked and skipped when complete
- [ ] Config loading deferred
- [ ] Measurable startup time improvement
- [ ] All existing tests pass

---

## Milestone Tracking
<!-- ID: milestones -->

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| Phase 1 Complete | Week 1 | Coder | Planned | PROGRESS_LOG.md |
| Phase 2 Complete | Week 3 | Coder | Planned | Benchmark results |
| Phase 3 Complete | Week 4 | Coder | Planned | PROGRESS_LOG.md |
| Phase 4 Complete | Week 5 | Coder | Planned | PROGRESS_LOG.md |
| Phase 5 Complete | Week 7 | Coder | Planned | Test coverage |
| Phase 6 Complete | Week 8 | Coder | Planned | Startup benchmarks |
| Full Cleanup Complete | Week 8 | Review | Planned | Final review grade |

---

## Retro Notes & Adjustments
<!-- ID: retro_final -->

- Summarize lessons learned after each phase completes
- Document any scope changes or re-planning decisions here
- Track blocked items and resolutions
