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

**Objective:** Split 2,934-line ResponseFormatter god class into 6 focused domain modules.

**Effort:** ~17 days | **Risk:** Medium-High | **Impact:** High (maintainability, testability)

**Research Reference:** `research/RESEARCH_FORMATTER_DECOMPOSITION_DETAILED.md` (2026-01-23)

**Extraction Order:** UI -> Base -> File -> Entry -> Project -> Dispatcher (risk-ordered)

### Task Packages

---

#### Task 5.1: Create UI Formatter Module (LOWEST RISK)
**Scope:** Extract box drawing, headers, footers, tables, line numbers
**Files to Create:** `utils/formatters/__init__.py`, `utils/formatters/ui.py`
**Files to Modify:** `utils/response.py` (add imports from new module)
**Dependencies:** None (first task)
**Effort:** ~2 days

**Methods to Extract (with line ranges from response.py):**

| Method | Lines | Size | Notes |
|--------|-------|------|-------|
| `_add_line_numbers` | 244-278 | 35 | Well-tested (8 tests) |
| `_create_header_box` | 280-349 | 70 | Well-tested (8 tests) |
| `_create_footer_box` | 351-436 | 86 | Well-tested (8 tests) |
| `_format_table` | 438-491 | 54 | Well-tested (8 tests) |

**Standalone Functions to Extract:**

| Function | Lines | Size |
|----------|-------|------|
| `format_header` | 3094-3179 | 86 |
| `add_tip` | 3182-3223 | 42 |

**Specifications:**
1. Create `utils/formatters/` directory with `__init__.py`
2. Create `utils/formatters/ui.py` with UIFormatter class containing extracted methods
3. UIFormatter needs access to ANSI constants - temporarily copy until base.py exists
4. Update `response.py` to import from `formatters.ui` and delegate calls
5. Maintain backward compatibility - ResponseFormatter methods become thin wrappers

**Implementation Pattern:**
```python
# utils/formatters/ui.py
class UIFormatter:
    # Temporarily embed ANSI constants (will be moved to base.py in Task 5.2)
    ANSI_RESET = "\033[0m"
    ANSI_CYAN = "\033[36m"
    # ... other constants
    
    def __init__(self, use_colors: bool = True):
        self._use_colors = use_colors
    
    def add_line_numbers(self, content: str, start_line: int = 1) -> str:
        # Extracted from lines 244-278
        ...

# utils/response.py (updated)
from utils.formatters.ui import UIFormatter

class ResponseFormatter:
    def __init__(self, token_warning_threshold: int = 4000):
        self._ui = UIFormatter(use_colors=self.USE_COLORS)
        # ... existing init
    
    def _add_line_numbers(self, content: str, start_line: int = 1) -> str:
        return self._ui.add_line_numbers(content, start_line)
```

**Verification:**
- [ ] `pytest tests/test_response_formatter_helpers.py` passes (8 line number tests)
- [ ] `pytest tests/test_response_formatter_readable.py -k "box or table"` passes
- [ ] UIFormatter importable: `from utils.formatters.ui import UIFormatter`
- [ ] All tool outputs unchanged (run 3 random tool tests)

**Out of Scope:**
- Do NOT extract entry/project/file formatting yet
- Do NOT modify tool files
- Do NOT change public API signatures

---

#### Task 5.2: Create Base Formatter Module (LOW RISK)
**Scope:** Extract core infrastructure, constants, shared utilities
**Files to Create:** `utils/formatters/base.py`
**Files to Modify:** `utils/formatters/ui.py` (import from base), `utils/response.py`
**Dependencies:** Task 5.1
**Effort:** ~2 days

**Methods to Extract (with line ranges):**

| Method | Lines | Size | Notes |
|--------|-------|------|-------|
| `USE_COLORS` property | 76-84 | 8 | Used by 15+ methods |
| `__init__` | 102-104 | 3 | Token threshold storage |
| `estimate_tokens` | 106-110 | 5 | Delegates to TokenEstimator |
| `_format_relative_time` | 1472-1537 | 66 | Shared by 6 methods |
| `format_readable_error` | 1411-1439 | 29 | Error formatting utility |

**Standalone Functions to Extract:**

| Function | Lines | Target |
|----------|-------|--------|
| `_get_use_ansi_colors` | 41-54 | base.py (module level) |
| `create_pagination_info` | 2996-2998 | base.py |
| `format_compact_json` | 3010-3091 | base.py (with nested `abbreviate_dict`) |

**Constants to Extract:**
- `READABLE`, `STRUCTURED`, `COMPACT`, `BOTH` format constants
- All ANSI color constants (`ANSI_RESET`, `ANSI_CYAN`, `ANSI_BOLD`, etc.)
- `COMPACT_FIELD_MAP`, `COMPACT_DEFAULT_FIELDS`

**Specifications:**
1. Create `utils/formatters/base.py` with BaseFormatter class
2. Move ANSI constants from ui.py to base.py
3. Update UIFormatter to inherit from BaseFormatter or import constants
4. Update response.py ResponseFormatter to inherit from BaseFormatter
5. Ensure `_format_relative_time` is accessible to all formatters

**Implementation Pattern:**
```python
# utils/formatters/base.py
from utils.estimator import TokenEstimator, PaginationInfo
from config.repo_config import get_current_repo_config

READABLE = "readable"
STRUCTURED = "structured"
# ... format constants

def _get_use_ansi_colors() -> bool:
    # Extracted from lines 41-54
    ...

class BaseFormatter:
    ANSI_RESET = "\033[0m"
    ANSI_CYAN = "\033[36m"
    # ... all ANSI constants
    
    @property
    def USE_COLORS(self) -> bool:
        return _get_use_ansi_colors()
    
    def _format_relative_time(self, dt) -> str:
        # Extracted from lines 1472-1537
        ...
```

**Verification:**
- [ ] `pytest tests/test_response_formatter_helpers.py -k "relative_time"` passes
- [ ] BaseFormatter importable: `from utils.formatters.base import BaseFormatter`
- [ ] UIFormatter still works after inheriting/importing from base
- [ ] All existing tests pass

**Out of Scope:**
- Do NOT extract domain-specific formatters yet
- Do NOT change tool file imports

---

#### Task 5.3: Create File Formatter Module (MEDIUM RISK - HIGH VALUE)
**Scope:** Extract the massive `format_readable_file_content` method (605 lines)
**Files to Create:** `utils/formatters/file.py`
**Files to Modify:** `utils/response.py`
**Dependencies:** Tasks 5.1, 5.2
**Effort:** ~3 days

**BLOCKER: Add Tests First**
The `format_readable_file_content` method (lines 495-1100) has **0 direct tests** despite being 605 lines and handling 6+ display modes. Tests MUST be added before extraction.

**Pre-Extraction Test Requirements:**
```python
# tests/test_file_formatter.py (NEW - create before extraction)
class TestFormatReadableFileContent:
    def test_basic_file_content(self): ...
    def test_line_range_mode(self): ...
    def test_search_mode_with_matches(self): ...
    def test_chunk_mode_pagination(self): ...
    def test_structure_mode_python(self): ...
    def test_structure_mode_markdown(self): ...
    def test_error_handling(self): ...
    def test_large_file_truncation(self): ...
```

**Method to Extract:**

| Method | Lines | Size | Notes |
|--------|-------|------|-------|
| `format_readable_file_content` | 495-1100 | 605 | 20% of entire class |

**Specifications:**
1. **FIRST:** Create `tests/test_file_formatter.py` with 8+ test cases covering all modes
2. Run tests against current implementation to establish baseline
3. Create `utils/formatters/file.py` with FileFormatter class
4. Extract method preserving exact behavior
5. FileFormatter depends on: BaseFormatter (USE_COLORS), UIFormatter (_add_line_numbers)
6. Update response.py to delegate to FileFormatter

**Implementation Pattern:**
```python
# utils/formatters/file.py
from utils.formatters.base import BaseFormatter
from utils.formatters.ui import UIFormatter

class FileFormatter(BaseFormatter):
    def __init__(self, token_threshold: int = 4000):
        self._ui = UIFormatter(use_colors=self.USE_COLORS)
        self._token_threshold = token_threshold
    
    def format_readable_file_content(self, result: dict, ...) -> str:
        # Extracted from lines 495-1100
        # Uses self._ui.add_line_numbers() for line numbering
        ...
```

**Verification:**
- [ ] All new `tests/test_file_formatter.py` tests pass
- [ ] `pytest tests/ -k "read_file"` passes (integration)
- [ ] FileFormatter importable: `from utils.formatters.file import FileFormatter`
- [ ] `read_file` tool outputs unchanged (manual verification with 3 modes)

**Out of Scope:**
- Do NOT refactor internal structure of `format_readable_file_content` (follow-up task)
- Do NOT extract other methods

**Future Opportunity:** After extraction, break the 605-line method into ~6 sub-methods (~100 lines each) for better maintainability.

---

#### Task 5.4: Create Entry Formatter Module (MEDIUM RISK)
**Scope:** Extract log entry formatting methods
**Files to Create:** `utils/formatters/entry.py`
**Files to Modify:** `utils/response.py`
**Dependencies:** Tasks 5.1, 5.2
**Effort:** ~3 days

**Methods to Extract (with line ranges):**

| Method | Lines | Size | Notes |
|--------|-------|------|-------|
| `format_entry` | 112-127 | 16 | Entry point |
| `_format_full_entry` | 129-147 | 19 | Full format |
| `_format_compact_entry` | 149-187 | 39 | Compact format |
| `format_response` | 189-240 | 52 | Response routing |
| `format_readable_log_entries` | 1101-1292 | 192 | Log list formatting |
| `_truncate_message_smart` | 1294-1316 | 23 | Smart truncation |
| `_parse_reasoning_block` | 1441-1470 | 30 | Reasoning extraction |
| `format_readable_append_entry` | 2380-2407 | 28 | Append response |
| `_format_single_append_entry` | 2409-2543 | 135 | Single entry |
| `_format_bulk_append_entry` | 2545-2646 | 102 | Bulk entries |
| `_extract_compact_log_line` | 2648-2676 | 29 | Compact log line |

**Total:** 11 methods, ~600 lines

**Specifications:**
1. Create `utils/formatters/entry.py` with EntryFormatter class
2. EntryFormatter depends on: BaseFormatter (USE_COLORS, _format_relative_time)
3. Group related methods logically within class
4. Update response.py to delegate to EntryFormatter
5. Preserve all method signatures exactly

**Implementation Pattern:**
```python
# utils/formatters/entry.py
from utils.formatters.base import BaseFormatter

class EntryFormatter(BaseFormatter):
    def format_entry(self, entry: dict, full: bool = True) -> str:
        # Extracted from lines 112-127
        ...
    
    def format_readable_log_entries(self, entries: list, ...) -> str:
        # Extracted from lines 1101-1292
        # Uses self._parse_reasoning_block internally
        ...
```

**Verification:**
- [ ] `pytest tests/test_response_formatter_readable.py -k "entry or append"` passes
- [ ] `pytest tests/test_response_formatter_helpers.py` passes
- [ ] EntryFormatter importable: `from utils.formatters.entry import EntryFormatter`
- [ ] `append_entry`, `read_recent`, `query_entries` tools work correctly

**Out of Scope:**
- Do NOT modify tool files yet
- Do NOT change method signatures

---

#### Task 5.5: Create Project Formatter Module (MEDIUM-HIGH RISK)
**Scope:** Extract project-related formatting (largest domain by method count)
**Files to Create:** `utils/formatters/project.py`
**Files to Modify:** `utils/response.py`
**Dependencies:** Tasks 5.1, 5.2
**Effort:** ~4 days

**Methods to Extract (with line ranges):**

| Method | Lines | Size | Notes |
|--------|-------|------|-------|
| `format_readable_projects` | 1318-1365 | 48 | List wrapper |
| `format_readable_confirmation` | 1367-1409 | 43 | Confirmation box |
| `_get_doc_line_count` | 1539-1564 | 26 | Doc utility |
| `_detect_custom_content` | 1566-1617 | 52 | Custom content check |
| `format_projects_table` | 1619-1710 | 92 | Table format |
| `format_project_detail` | 1712-1902 | 191 | Detail format |
| `format_no_projects_found` | 1904-1965 | 62 | Empty state |
| `format_project_context` | 1967-2123 | 157 | Context box |
| `format_project_sitrep_new` | 2125-2208 | 84 | New project SITREP |
| `format_project_sitrep_existing` | 2210-2378 | 169 | Existing SITREP |
| `format_projects_response` | 2947-2990 | 44 | Response router |

**Total:** 11 methods, ~950 lines

**Specifications:**
1. Create `utils/formatters/project.py` with ProjectFormatter class
2. ProjectFormatter depends on: BaseFormatter (_format_relative_time), UIFormatter (_create_header_box, _format_table)
3. This is the largest extraction - work methodically
4. Update response.py to delegate to ProjectFormatter

**Implementation Pattern:**
```python
# utils/formatters/project.py
from utils.formatters.base import BaseFormatter
from utils.formatters.ui import UIFormatter

class ProjectFormatter(BaseFormatter):
    def __init__(self, token_threshold: int = 4000):
        self._ui = UIFormatter(use_colors=self.USE_COLORS)
        self._token_threshold = token_threshold
    
    def format_projects_table(self, projects: list, ...) -> str:
        # Extracted from lines 1619-1710
        # Uses self._ui._create_header_box, self._ui._format_table
        ...
```

**Verification:**
- [ ] `pytest tests/test_list_projects_formatters.py` passes (15 tests)
- [ ] `pytest tests/test_get_project_formatter.py` passes
- [ ] `pytest tests/test_set_project_formatters.py` passes
- [ ] ProjectFormatter importable: `from utils.formatters.project import ProjectFormatter`
- [ ] `list_projects`, `get_project`, `set_project` tools work correctly

**Out of Scope:**
- Do NOT modify tool files yet
- Do NOT split into multiple sub-modules (future opportunity)

---

#### Task 5.6: Create Dispatcher and Finalize Facade (HIGHEST RISK)
**Scope:** Extract async dispatcher, update all imports, finalize response.py as facade
**Files to Create:** `utils/formatters/dispatcher.py`
**Files to Modify:** `utils/response.py`, `utils/__init__.py`, 10+ tool files
**Dependencies:** Tasks 5.1-5.5 (ALL)
**Effort:** ~3 days

**BLOCKER: Add Integration Tests First**
The `finalize_tool_response` method is the async router used by ALL tools. Integration tests MUST be added before extraction.

**Pre-Extraction Test Requirements:**
```python
# tests/test_formatter_dispatcher.py (NEW - create before extraction)
class TestFinalizeToolResponse:
    async def test_readable_format_routing(self): ...
    async def test_structured_format_routing(self): ...
    async def test_compact_format_routing(self): ...
    async def test_tool_logging_integration(self): ...
    async def test_error_handling(self): ...
    async def test_large_response_truncation(self): ...
```

**Method to Extract:**

| Method | Lines | Size | Notes |
|--------|-------|------|-------|
| `finalize_tool_response` | 2678-2945 | 268 | Async router, MCP SDK dependency |

**External Dependencies (must be preserved):**
- `utils/tool_logger.py` - `log_tool_call`
- `server.py` - `get_execution_context` (runtime import)
- `mcp.types` - `CallToolResult`, `TextContent`

**Specifications:**
1. **FIRST:** Create `tests/test_formatter_dispatcher.py` with 6+ async test cases
2. Run tests against current implementation
3. Create `utils/formatters/dispatcher.py` with FormatterDispatcher class
4. Dispatcher holds references to all other formatters
5. Update `utils/response.py` to be a thin facade:
   - Import and re-export public API
   - ResponseFormatter becomes delegation wrapper
6. Update `utils/__init__.py` to maintain public exports
7. Update ALL tool files to ensure imports still work

**Implementation Pattern:**
```python
# utils/formatters/dispatcher.py
from utils.formatters.base import BaseFormatter, create_pagination_info
from utils.formatters.ui import UIFormatter
from utils.formatters.entry import EntryFormatter
from utils.formatters.file import FileFormatter
from utils.formatters.project import ProjectFormatter

class FormatterDispatcher:
    def __init__(self, token_threshold: int = 4000):
        self.base = BaseFormatter(token_threshold)
        self.ui = UIFormatter(use_colors=self.base.USE_COLORS)
        self.entry = EntryFormatter(token_threshold)
        self.file = FileFormatter(token_threshold)
        self.project = ProjectFormatter(token_threshold)
    
    async def finalize_tool_response(self, result: dict, ...) -> CallToolResult:
        # Extracted from lines 2678-2945
        # Routes to appropriate formatter based on tool/format
        ...

# utils/response.py (FACADE)
from utils.formatters.dispatcher import FormatterDispatcher
from utils.formatters.base import (
    BaseFormatter, create_pagination_info, format_compact_json,
    READABLE, STRUCTURED, COMPACT, BOTH
)

class ResponseFormatter:
    """Facade for backward compatibility. Delegates to focused formatters."""
    
    def __init__(self, token_warning_threshold: int = 4000):
        self._dispatcher = FormatterDispatcher(token_warning_threshold)
    
    # Delegate all methods to dispatcher's formatters
    def format_entry(self, *args, **kwargs):
        return self._dispatcher.entry.format_entry(*args, **kwargs)
    
    async def finalize_tool_response(self, *args, **kwargs):
        return await self._dispatcher.finalize_tool_response(*args, **kwargs)
    
    # ... other delegations

# Maintain singleton
default_formatter = ResponseFormatter()
```

**Tool Files to Verify (imports must still work):**
- `tools/append_entry.py`
- `tools/read_file.py`
- `tools/list_projects.py`
- `tools/set_project.py`
- `tools/get_project.py`
- `tools/query_entries.py`
- `tools/read_recent.py`
- `tools/rotate_log.py`
- `shared/base_logging_tool.py`
- `utils/__init__.py`

**Verification:**
- [ ] All new `tests/test_formatter_dispatcher.py` tests pass
- [ ] `pytest tests/` full test suite passes
- [ ] All 10+ tool files import successfully
- [ ] `from utils.response import ResponseFormatter, default_formatter` works
- [ ] `from utils import ResponseFormatter` works
- [ ] Manual test: Run each tool with `format="readable"` and `format="structured"`

**Out of Scope:**
- Do NOT change tool logic
- Do NOT add new formatting features

---

### Phase 5 Acceptance Criteria
<!-- ID: phase_5_acceptance -->

- [ ] 6 new formatter modules created in `utils/formatters/`:
  - [ ] `base.py` (~350 lines)
  - [ ] `ui.py` (~350 lines)
  - [ ] `file.py` (~650 lines)
  - [ ] `entry.py` (~600 lines)
  - [ ] `project.py` (~950 lines)
  - [ ] `dispatcher.py` (~300 lines)
- [ ] `utils/response.py` reduced from 2,934 lines to ~200 lines (facade only)
- [ ] Zero breaking changes to public API:
  - [ ] `ResponseFormatter` class signature unchanged
  - [ ] `default_formatter` singleton available
  - [ ] `create_pagination_info` function available
  - [ ] All tool imports work without modification
- [ ] Test coverage maintained or improved:
  - [ ] All existing tests pass
  - [ ] NEW: `tests/test_file_formatter.py` (8+ tests)
  - [ ] NEW: `tests/test_formatter_dispatcher.py` (6+ tests)
- [ ] Documentation updated:
  - [ ] Module docstrings in each new file
  - [ ] Updated import examples in relevant docs

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
