---
id: read_file_search_audit-research-session-state-persistence-20260128
title: "\U0001F52C Research Session State Persistence 20260128 \u2014 read_file_search_audit"
doc_name: RESEARCH_SESSION_STATE_PERSISTENCE_20260128
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-29'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Session State Persistence 20260128 — read_file_search_audit
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-29 03:10:26 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Problem:** The `edit_file` tool must enforce "read before edit" — agents must call `read_file` on a file before editing it. This requires tracking which files have been read in the current session. The Architect proposed adding `files_read_in_session` to `ExecutionContext`, but Review Agent found this won't work because `ExecutionContext` is created fresh per-request.

**Key Findings:**
1. `ExecutionContext` is NOT frozen, but IS created fresh per tool call (per-request lifecycle)
2. `RouterContextManager` is a module-level singleton that persists for the server's lifetime
3. Session identity is `transport_session_id` from MCP headers — stable across tool calls
4. Module-level state with locks is an established pattern (see `append_entry.py`)
5. Session boundary = MCP connection lifetime

**Recommendation:** Use **Option 2 - RouterContextManager** to track files read. It already manages session state, has the right lifecycle, and follows existing patterns.

**Confidence:** 1.0 (verified through code inspection of 6 files)
<!-- ID: research_scope -->
**Research Lead:** Scribe

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### Finding #1: ExecutionContext Lifecycle (CRITICAL)

**File:** `shared/execution_context.py` lines 35-50, 158-212

**What Review Agent Said:** "ExecutionContext is frozen dataclass, can't store mutable state"

**Actual Truth:** ExecutionContext is a **regular class** (not frozen), but it IS created **fresh per-request**:
- `RouterContextManager.build_execution_context()` at line 158 creates new instance
- Called from `server.py` line 624 for EVERY tool call
- Set in contextvar at line 636, reset after execution (lines 655, 659)

**Impact:** Adding `files_read_in_session` to ExecutionContext WILL NOT WORK because each tool call gets a fresh instance. The set would be empty on every call.

**Confidence:** 1.0 (verified by code inspection)

---

### Finding #2: RouterContextManager Persistence (KEY INSIGHT)

**File:** `server.py` line 112, `shared/execution_context.py` lines 53-221

**Discovery:** RouterContextManager is instantiated at **MODULE LEVEL** in server.py:
```python
router_context_manager = RouterContextManager(storage_backend=storage_backend)
```

**Lifecycle:** Persists for entire server process lifetime (not per-request)

**Existing State:** Already maintains two in-memory caches:
- `_transport_sessions: Dict[str, str]` — transport_id -> session_id mapping (line 58)
- `_session_projects: Dict[str, str]` — session_id -> project_name cache (line 59)
- `_lock: asyncio.Lock` — Thread-safe access control (line 57)

**Pattern:** This is the RIGHT place to add `files_read_in_session` tracking.

**Confidence:** 1.0 (verified by code inspection)

---

### Finding #3: Session Identity System

**Files:** `shared/execution_context.py` lines 63-113, `server.py` lines 373-398, `storage/sqlite.py` lines 880-900, 2132-2200

**Session Boundary:** MCP connection lifetime

**Session Identity Flow:**
1. MCP client sends `mcp-session-id` header or `client_id` in meta (server.py line 390, 394)
2. Extracted as `transport_session_id` (server.py lines 373-398)
3. RouterContextManager maps to stable `session_id` UUID (execution_context.py lines 63-113)
4. Uses 3-tier lookup: in-memory cache → database → create new

**Database Tables:**
- `scribe_sessions` — router session records (sqlite.py line 2147)
- `agent_sessions` — legacy agent session records (sqlite.py line 880)

**Key Points:**
- `transport_session_id` persists across tool calls in same MCP connection
- `session_id` is stable UUID that survives server restarts (stored in DB)
- Session dies when MCP connection closes

**Confidence:** 1.0 (verified by code inspection)

---

### Finding #4: Module-Level State Precedent

**File:** `tools/append_entry.py` lines 65-81

**Existing Pattern:** Multiple module-level globals for cross-request state:
```python
_RATE_TRACKER: Dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCKS: Dict[str, asyncio.Lock] = {}
_RATE_MAP_LOCK = asyncio.Lock()
_CONFIG_MANAGER = ConfigManager("append_entry")
_BULK_CALCULATOR = BulkProcessingCalculator()
_PARALLEL_PROCESSOR = ParallelBulkProcessor()
```

**Pattern:** 
- Module-level dict keyed by some identifier (e.g., agent or session)
- Separate lock dict or single lock for thread safety
- State persists across tool calls within server process

**Precedent Value:** This pattern is already used and working in production.

**Confidence:** 1.0 (verified by code inspection)

---

### Finding #5: No Existing Read Tracking

**File:** `tools/read_file.py`

**Search Results:** No tracking mechanism exists. Only cache is `_find_workspace_root._cache` for workspace root lookups (lines 418-437).

**Impact:** We're building from scratch — no existing infrastructure to reuse.

**Confidence:** 1.0 (verified by code inspection)

---

### Finding #6: ContextVar Usage

**File:** `shared/execution_context.py` lines 14-18, 214-221; `server.py` lines 636, 655, 659, 915-917

**Mechanism:** `_CURRENT_CONTEXT` is a `contextvars.ContextVar` that stores ExecutionContext per-request:
- Set before tool execution: `router_context_manager.set_current(exec_context)` (server.py line 636)
- Reset after tool execution: `router_context_manager.reset(token)` (lines 655, 659)
- Tools can access via `get_execution_context()` (server.py lines 915-917)

**Lifecycle:** Per-request only — ContextVar is designed for async request isolation, not cross-request persistence.

**Impact:** ContextVar is NOT suitable for tracking files_read across tool calls.

**Confidence:** 1.0 (verified by code inspection)

---

### Finding #7: Database is Overkill

**File:** `storage/sqlite.py` lines 880-900 (agent_sessions table)

**Assessment:** We COULD add a `files_read_json` column to `agent_sessions` or `scribe_sessions` table and persist on every read_file call.

**Why Not:**
- Disk I/O on every read_file call (performance hit)
- Need DB migrations for new column
- Overkill for ephemeral session state
- Session dies when MCP disconnects anyway
- In-memory tracking is sufficient and faster

**Confidence:** 0.9 (design decision, not just code facts)
<!-- ID: technical_analysis -->
## Technical Analysis

### Three Viable Options for files_read_in_session Tracking

---

#### **Option 1: Module-Level Dict in read_file.py**

**Implementation:**
```python
# In tools/read_file.py
_FILES_READ_IN_SESSION: Dict[str, Set[str]] = defaultdict(set)  # session_id -> set of paths
_FILES_READ_LOCK = asyncio.Lock()

async def read_file(agent: str, path: str, ...):
    exec_ctx = get_execution_context()
    session_id = exec_ctx.session_id
    
    async with _FILES_READ_LOCK:
        _FILES_READ_IN_SESSION[session_id].add(path)
    # ... rest of read_file logic
```

**Pros:**
- ✅ Simple, follows precedent (see `append_entry.py` `_RATE_TRACKER`)
- ✅ Fast (in-memory, no DB)
- ✅ Self-contained in read_file module

**Cons:**
- ❌ edit_file would need to import from read_file.py (cross-module dependency)
- ❌ No automatic session cleanup (memory leak risk)
- ❌ Lost on server restart (but sessions die anyway)

**Key Question:** How does edit_file check if file was read?
```python
# In tools/edit_file.py
from scribe_mcp.tools.read_file import _FILES_READ_IN_SESSION, _FILES_READ_LOCK

async def edit_file(agent: str, path: str, ...):
    exec_ctx = get_execution_context()
    session_id = exec_ctx.session_id
    
    async with _FILES_READ_LOCK:
        if path not in _FILES_READ_IN_SESSION.get(session_id, set()):
            raise ValueError(f"Must call read_file on {path} before editing")
```

**Confidence:** 0.85 (works but cross-module coupling is awkward)

---

#### **Option 2: RouterContextManager (RECOMMENDED)**

**Implementation:**
```python
# In shared/execution_context.py
class RouterContextManager:
    def __init__(self, storage_backend=None) -> None:
        self._lock = asyncio.Lock()
        self._transport_sessions: Dict[str, str] = {}
        self._session_projects: Dict[str, str] = {}
        self._files_read_in_session: Dict[str, Set[str]] = defaultdict(set)  # NEW
        self._process_instance_id = str(uuid.uuid4())
        self._storage_backend = storage_backend

    async def record_file_read(self, session_id: str, file_path: str) -> None:
        """Record that a file was read in this session."""
        async with self._lock:
            self._files_read_in_session[session_id].add(file_path)
    
    async def has_file_been_read(self, session_id: str, file_path: str) -> bool:
        """Check if a file was read in this session."""
        async with self._lock:
            return file_path in self._files_read_in_session.get(session_id, set())
```

**Usage in tools:**
```python
# In tools/read_file.py
from scribe_mcp.server import router_context_manager, get_execution_context

async def read_file(agent: str, path: str, ...):
    exec_ctx = get_execution_context()
    await router_context_manager.record_file_read(exec_ctx.session_id, path)
    # ... rest of logic

# In tools/edit_file.py
async def edit_file(agent: str, path: str, ...):
    exec_ctx = get_execution_context()
    if not await router_context_manager.has_file_been_read(exec_ctx.session_id, path):
        raise ValueError(f"Must call read_file on {path} before editing")
```

**Pros:**
- ✅ **Perfect lifecycle match** — RouterContextManager already persists across requests
- ✅ **Already manages session state** — consistent with `_session_projects` cache
- ✅ **Built-in locking** — `_lock` already protects all session state
- ✅ **Centralized** — single source of truth for session data
- ✅ **Clean API** — explicit methods for recording/checking
- ✅ **No cross-module coupling** — both tools import from server.py

**Cons:**
- ⚠️ RouterContextManager grows in responsibility (but it's already the session manager)
- ⚠️ No automatic cleanup (same as Option 1)

**Why This is Best:**
- RouterContextManager is DESIGNED to manage session-scoped state
- Already does this for project bindings (`_session_projects`)
- Natural fit for files_read tracking
- Single lock protects all session state

**Confidence:** 1.0 (cleanest design, best alignment with existing architecture)

---

#### **Option 3: Database Persistence**

**Implementation:**
```sql
-- Add column to scribe_sessions table
ALTER TABLE scribe_sessions ADD COLUMN files_read_json TEXT;

-- Or create separate table
CREATE TABLE session_files_read (
    session_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, file_path)
);
```

**Storage Backend Method:**
```python
# In storage/sqlite.py
async def record_file_read(self, session_id: str, file_path: str) -> None:
    await self._execute(
        "INSERT OR IGNORE INTO session_files_read (session_id, file_path) VALUES (?, ?)",
        (session_id, file_path)
    )

async def has_file_been_read(self, session_id: str, file_path: str) -> bool:
    row = await self._fetchone(
        "SELECT 1 FROM session_files_read WHERE session_id = ? AND file_path = ?",
        (session_id, file_path)
    )
    return row is not None
```

**Pros:**
- ✅ Survives server restarts (sessions persist in DB)
- ✅ Can query historical read patterns
- ✅ Explicit cleanup on session expiry

**Cons:**
- ❌ **Disk I/O on EVERY read_file call** (performance penalty)
- ❌ **DB migration required** (new table/column)
- ❌ **Overkill** — sessions die when MCP disconnects anyway
- ❌ **More complexity** — storage backend changes, migration logic
- ❌ **No real benefit** — in-memory is sufficient for ephemeral session state

**When This Would Make Sense:**
- If sessions needed to survive server restarts (they don't)
- If we needed audit trail of all file reads (we don't)
- If session lifetime was decoupled from MCP connection (it isn't)

**Confidence:** 0.7 (works but overengineered for this use case)

---

### Session Cleanup Strategy (Important for All Options)

**Problem:** In-memory tracking (Options 1 & 2) needs cleanup to prevent memory leaks.

**Solution:** Session cleanup already exists in `server.py` lines 920-935:
```python
async def _session_cleanup_task(agent_manager):
    """Background task to clean up expired sessions."""
    # Already handles agent_sessions table cleanup
```

**Recommendation:** Extend existing cleanup to purge `_files_read_in_session` for expired sessions.

**Implementation (for Option 2):**
```python
# Add to RouterContextManager
async def cleanup_session(self, session_id: str) -> None:
    """Remove session from all caches."""
    async with self._lock:
        self._transport_sessions.pop(session_id, None)
        self._session_projects.pop(session_id, None)
        self._files_read_in_session.pop(session_id, None)  # NEW
```

**Confidence:** 1.0 (follows existing cleanup patterns)
<!-- ID: recommendations -->
## Recommendations

### PRIMARY RECOMMENDATION: Use Option 2 (RouterContextManager)

**Why RouterContextManager is the Right Choice:**

1. **Architectural Fit** — It's DESIGNED to manage session-scoped state
2. **Existing Pattern** — Already manages `_session_projects` cache the same way
3. **Lifecycle Match** — Module-level singleton persists across requests, dies with server (same as sessions)
4. **Built-in Locking** — Single `_lock` protects all session state
5. **Clean API** — Explicit `record_file_read()` / `has_file_been_read()` methods
6. **No Coupling** — Both read_file and edit_file import from server.py (no cross-tool imports)

**Implementation Plan:**

#### Step 1: Add to RouterContextManager (shared/execution_context.py)
```python
class RouterContextManager:
    def __init__(self, storage_backend=None) -> None:
        self._lock = asyncio.Lock()
        self._transport_sessions: Dict[str, str] = {}
        self._session_projects: Dict[str, str] = {}
        self._files_read_in_session: Dict[str, Set[str]] = defaultdict(set)  # NEW
        self._process_instance_id = str(uuid.uuid4())
        self._storage_backend = storage_backend

    async def record_file_read(self, session_id: str, file_path: str) -> None:
        """Record that a file was read in this session."""
        if not session_id or not file_path:
            return
        async with self._lock:
            self._files_read_in_session[session_id].add(file_path)
    
    async def has_file_been_read(self, session_id: str, file_path: str) -> bool:
        """Check if a file was read in this session."""
        if not session_id or not file_path:
            return False
        async with self._lock:
            return file_path in self._files_read_in_session.get(session_id, set())
    
    async def cleanup_session(self, session_id: str) -> None:
        """Remove session from all caches (called by session cleanup task)."""
        async with self._lock:
            self._transport_sessions.pop(session_id, None)
            self._session_projects.pop(session_id, None)
            self._files_read_in_session.pop(session_id, None)  # NEW
```

#### Step 2: Update read_file.py
```python
from scribe_mcp.server import router_context_manager, get_execution_context

async def read_file(agent: str, path: str, ...):
    # ... existing validation logic ...
    
    # Record file read AFTER successful read
    exec_ctx = get_execution_context()
    if exec_ctx and exec_ctx.session_id:
        await router_context_manager.record_file_read(exec_ctx.session_id, str(normalized_path))
    
    # ... return result ...
```

#### Step 3: Implement edit_file.py
```python
from scribe_mcp.server import router_context_manager, get_execution_context

async def edit_file(agent: str, path: str, old_string: str, new_string: str, ...):
    # Get execution context
    exec_ctx = get_execution_context()
    if not exec_ctx or not exec_ctx.session_id:
        raise ValueError("edit_file requires valid session context")
    
    # ENFORCE: Must read before edit
    normalized_path = Path(path).resolve()
    if not await router_context_manager.has_file_been_read(exec_ctx.session_id, str(normalized_path)):
        raise ValueError(
            f"Security policy: Must call read_file on '{path}' before editing. "
            f"This ensures you understand the file's current state."
        )
    
    # ... rest of edit logic ...
```

#### Step 4: Extend Session Cleanup (server.py)
```python
async def _session_cleanup_task(agent_manager):
    """Background task to clean up expired sessions."""
    # ... existing cleanup logic ...
    
    # Clean up RouterContextManager caches for expired sessions
    expired_session_ids = [...]  # Get from DB query
    for session_id in expired_session_ids:
        await router_context_manager.cleanup_session(session_id)
```

---

### Immediate Next Steps for Architect Agent

1. **Update ARCHITECTURE_GUIDE.md Section 4.1** — Replace ExecutionContext approach with RouterContextManager approach
2. **Update PHASE_PLAN.md Task 0.1** — Change implementation details:
   - Target file: `shared/execution_context.py` (not ExecutionContext class)
   - Add three methods: `record_file_read()`, `has_file_been_read()`, `cleanup_session()`
   - Add `_files_read_in_session: Dict[str, Set[str]]` to `__init__`
3. **Update Task 1.1** — Modify read_file to call `router_context_manager.record_file_read()`
4. **Update Task 2.1** — Modify edit_file to call `router_context_manager.has_file_been_read()`
5. **Add Task 0.3** — Extend session cleanup in server.py to call `router_context_manager.cleanup_session()`

---

### Why NOT the Other Options

**Option 1 (Module-Level in read_file.py):**
- ❌ Cross-module coupling (edit_file imports private state from read_file)
- ❌ Awkward API (accessing module-level dicts directly)
- ✅ Works, but less elegant than Option 2

**Option 3 (Database Persistence):**
- ❌ Disk I/O on every read_file call (performance penalty)
- ❌ Overengineered (sessions die with MCP connection anyway)
- ❌ DB migration required (complexity)
- ✅ Would work, but massive overkill

---

### Open Questions (None Blocking)

1. **Session expiry timing?** — How long before inactive sessions are cleaned up? (Already handled by existing `_session_cleanup_task`)
2. **Memory bounds?** — If a session reads 10,000 files, is that a problem? (Same issue exists for `_session_projects`, not a new concern)
3. **Path normalization?** — Should we normalize paths before tracking? (Yes, use `Path().resolve()` for consistency)

---

### Confidence Assessment

| Aspect | Confidence | Reason |
|--------|-----------|--------|
| RouterContextManager lifecycle | 1.0 | Verified by code inspection |
| Session identity system | 1.0 | Verified by code inspection |
| Recommended approach (Option 2) | 1.0 | Best architectural fit |
| Implementation feasibility | 0.95 | Straightforward, follows existing patterns |
| No blocking issues | 0.95 | All requirements can be met |

---

### Handoff Notes for Architect

**Key Insight:** The Review Agent's concern was VALID (ExecutionContext won't work), but the diagnosis was WRONG (ExecutionContext is not frozen). The real issue is ExecutionContext is created fresh per-request.

**Solution:** RouterContextManager is the perfect place for this tracking because:
- It already manages session state (`_session_projects`)
- It persists across requests (module-level singleton)
- It has built-in locking for thread safety
- It's the canonical session manager in the architecture

**No New Patterns Needed:** This solution uses existing infrastructure and follows established patterns. No new abstractions, no DB changes, no external dependencies.

**Estimated Rework:** 2-3 hours to update architecture docs + phase plan. Implementation is ~50 lines of code across 3 files.
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---