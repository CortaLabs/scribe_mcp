---
id: session_project_caching-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 session_project_caching"
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-21'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — session_project_caching
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-21 02:05:13 UTC

> Architecture guide for session_project_caching.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
**Context:** After the `agent_param_audit` implementation, session identity is derived from `repo_root:mode:scope_key:agent_key`. This means the same agent name in the same repo maps to the same session. However, if two agents with the **same name** work on **different projects** within the same repo, they share a session binding and collide.

**The Gap:**
```
CoderAgent on project_A -> session: hash(repo:mode:scope:CoderAgent) -> project_A (cached)
CoderAgent on project_B -> session: hash(repo:mode:scope:CoderAgent) -> project_A (WRONG!)
```

**User Requirement:** "Ideally this should happen in the session code, so we don't have to change every single tool. The ideal setup was project name could be cached per session."

**Goals:**
- Cache `project_name` per session at the server layer
- Auto-inject `project_name` into tool arguments when not explicitly provided
- Zero changes to individual tool signatures
- Backwards compatible (explicit project param still works)

**Non-Goals:**
- Changing session identity hash to include project_name
- Modifying ExecutionContext dataclass schema
- Adding database persistence for the cache (DB already has it via session_projects table)

**Success Metrics:**
- `set_project()` populates in-memory cache
- Subsequent tool calls auto-receive `project` argument from cache
- Same agent switching projects mid-session works correctly (cache updates)
- MCP restart gracefully handled (agents re-call set_project as normal)
<!-- ID: requirements_constraints -->
**Functional Requirements:**
1. `set_project()` must populate an in-memory cache mapping `stable_session_id` -> `project_name`
2. Server tool dispatch must auto-inject `project` argument from cache when not provided
3. Explicit `project` parameter must override cache (backwards compatibility)
4. Cache must update when agent calls `set_project()` again (project switching)

**Non-Functional Requirements:**
- Thread-safe using existing `asyncio.Lock()` pattern
- No new files - enhance existing `RouterContextManager`
- Minimal code changes (~30-50 lines total)
- Implementation time: 1-2 hours

**Assumptions:**
- Agents call `set_project()` at session start (existing pattern)
- `stable_session_id` is available in `ExecutionContext` (verified: exists at line 403)
- Database already persists bindings via `session_projects` table (fallback on MCP restart)

**Constraints:**
- Must use existing `RouterContextManager._lock` for consistency with codebase patterns
- Must NOT modify `ExecutionContext` dataclass (immutable, frozen)
- Must NOT change tool function signatures

**Risks & Mitigations:**
| Risk | Mitigation |
|------|------------|
| Cache lost on MCP restart | Agents re-call `set_project()` per session (normal behavior) |
| Race condition | Use existing `asyncio.Lock()` in RouterContextManager |
| Stale cache after project delete | Cache cleared when `delete_project()` called (future enhancement) |
<!-- ID: architecture_overview -->
**Solution Summary:** Enhance `RouterContextManager` with a `_session_projects` dict that caches `stable_session_id` -> `project_name` mappings. Auto-inject `project` into tool arguments at server dispatch (line 618) when not explicitly provided.

**Component Breakdown:**

| Component | File | Changes |
|-----------|------|---------|
| **RouterContextManager** | `shared/execution_context.py` | Add `_session_projects` dict + 2 methods |
| **Server Dispatch** | `server.py` | Add auto-injection before line 618 |
| **set_project Tool** | `tools/set_project.py` | Call cache method after DB write |

**Data Flow:**
```
1. Agent calls set_project(agent="Coder", name="auth_fix", root="...")
   |
   v
2. set_project writes to DB: backend.set_session_project(session_key, name)
   |
   v
3. set_project updates cache: router_context_manager.cache_project_binding(session_id, name)
   |
   v
4. Later: Agent calls append_entry(agent="Coder", message="...")  [NO project param]
   |
   v
5. Server dispatch (line 617): Check if "project" in arguments
   |
   v
6. If missing: cached_project = router_context_manager.get_cached_project(exec_context.stable_session_id)
   |
   v
7. If cached: arguments["project"] = cached_project
   |
   v
8. Tool executes with project context
```

**External Integrations:**
- Uses existing `storage_backend.set_session_project()` for DB persistence (already implemented)
- Uses existing `RouterContextManager._lock` for thread safety
- No new external dependencies
<!-- ID: detailed_design -->
### 4.1 RouterContextManager Enhancement (`shared/execution_context.py`)

**Location:** Lines 56-60 (inside `__init__`)

**Current Code:**
```python
def __init__(self, storage_backend=None) -> None:
    self._lock = asyncio.Lock()
    self._transport_sessions: Dict[str, str] = {}  # Keep as performance cache
    self._process_instance_id = str(uuid.uuid4())
    self._storage_backend = storage_backend
```

**Add to `__init__` (line 59):**
```python
self._session_projects: Dict[str, str] = {}  # session_id -> project_name cache
```

**Add new methods (after line 112, before `_build_agent_identity`):**
```python
async def cache_project_binding(self, session_id: str, project_name: str) -> None:
    """Cache project binding for this session.
    
    Args:
        session_id: The stable_session_id from ExecutionContext
        project_name: Project name to cache
    """
    if not session_id or not project_name:
        return
    async with self._lock:
        self._session_projects[session_id] = project_name

async def get_cached_project(self, session_id: str) -> Optional[str]:
    """Get cached project for this session.
    
    Args:
        session_id: The stable_session_id from ExecutionContext
        
    Returns:
        Cached project name or None if not cached
    """
    if not session_id:
        return None
    async with self._lock:
        return self._session_projects.get(session_id)
```

### 4.2 Server Auto-Injection (`server.py`)

**Location:** Lines 616-618 (before tool execution)

**Current Code:**
```python
token = router_context_manager.set_current(exec_context)
try:
    result = func(**arguments)
```

**Modified Code (insert between lines 616-618):**
```python
token = router_context_manager.set_current(exec_context)

# Auto-inject cached project if not explicitly provided
if "project" not in arguments and "project_name" not in arguments:
    cached_project = await router_context_manager.get_cached_project(
        exec_context.stable_session_id
    )
    if cached_project:
        arguments["project"] = cached_project

try:
    result = func(**arguments)
```

### 4.3 set_project Cache Update (`tools/set_project.py`)

**Location:** Line 513 (after DB write)

**Current Code:**
```python
if hasattr(backend, "set_session_project"):
    await backend.set_session_project(session_key, name)
    # Debug logging follows...
```

**Add after line 513:**
```python
# Update in-memory cache for auto-injection
from scribe_mcp.server import router_context_manager
await router_context_manager.cache_project_binding(
    stable_session_id or session_key,
    name
)
```

### 4.4 Edge Cases

| Case | Behavior | Why |
|------|----------|-----|
| Explicit `project` param | Explicit wins, cache ignored | Backwards compatibility |
| Agent switches projects | Cache updated on `set_project()` | Last binding wins |
| MCP restart | Cache empty, agents re-call `set_project()` | Normal agent behavior |
| Same agent, different projects | Works - cache uses stable_session_id | Session identity is per-agent |
| `project` param is empty string | Treated as explicit, cache not used | Empty string is falsy but present |
<!-- ID: directory_structure -->
**Total Files: 3** (no new files needed)

```
/home/austin/projects/MCP_SPINE/scribe_mcp/
├── shared/
│   └── execution_context.py    # +1 line in __init__, +2 methods (~25 lines)
├── server.py                   # +6 lines (auto-injection logic)
└── tools/
    └── set_project.py          # +4 lines (cache update call)
```

**Estimated Total Lines Changed:** ~35 lines

> This enhancement follows the existing codebase pattern established by `_transport_sessions` cache in `RouterContextManager`.
<!-- ID: data_storage -->
**In-Memory Cache (NEW):**
- `RouterContextManager._session_projects: Dict[str, str]`
- Key: `stable_session_id` (UUID string)
- Value: `project_name` (string)
- Lifetime: Process lifetime (cleared on MCP restart)
- Thread Safety: Protected by `RouterContextManager._lock` (asyncio.Lock)

**Database Persistence (EXISTING - unchanged):**
- Table: `session_projects` (sqlite.py lines 940-945)
- Schema: `session_id TEXT PRIMARY KEY, project_name TEXT, updated_at TEXT`
- Used by: `backend.set_session_project()`, `backend.get_session_project()`

**Cache-DB Relationship:**
- Cache is a performance optimization layered ON TOP of existing DB persistence
- `set_project()` writes to BOTH DB and cache
- On MCP restart, cache is empty but DB has data; agents re-call `set_project()` which repopulates cache
- No cache invalidation logic needed - `set_project()` always overwrites
<!-- ID: testing_strategy -->
**Unit Tests (new test file: `tests/test_session_project_cache.py`):**

1. `test_cache_project_binding_stores_value`
   - Call `cache_project_binding(session_id, project_name)`
   - Verify `get_cached_project(session_id)` returns project_name

2. `test_cache_project_binding_overwrites_on_update`
   - Call `cache_project_binding(session_id, "project_a")`
   - Call `cache_project_binding(session_id, "project_b")`
   - Verify `get_cached_project(session_id)` returns "project_b"

3. `test_get_cached_project_returns_none_for_unknown`
   - Call `get_cached_project("unknown_session_id")`
   - Verify returns `None`

4. `test_cache_project_binding_handles_none_gracefully`
   - Call `cache_project_binding(None, "project")` - should not raise
   - Call `cache_project_binding("session", None)` - should not raise

**Integration Tests (add to existing `tests/test_set_project.py`):**

5. `test_set_project_populates_cache`
   - Call `set_project(agent="Test", name="my_project", root="...")`
   - Verify cache contains the binding

**Manual Verification:**
1. Start MCP server
2. Call `set_project(agent="Coder", name="test_proj", root=".")`
3. Call `append_entry(agent="Coder", message="test")` WITHOUT project param
4. Verify entry goes to `test_proj` project (check PROGRESS_LOG.md)
<!-- ID: deployment_operations -->
**Deployment:**
- Standard commit to `scribe_mcp` repository
- No database migrations needed (uses existing `session_projects` table)
- No configuration changes required
- MCP server restart required to pick up code changes

**Backwards Compatibility:**
- Tools that explicitly pass `project` continue to work unchanged
- Tools that don't pass `project` will now auto-receive it from cache
- Agents that don't call `set_project()` see no change (cache empty, no injection)

**Rollback:**
- Revert the 3 file changes
- No database cleanup needed
- Cache clears automatically on MCP restart
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should `delete_project()` clear cache? | Coder | FUTURE | Not needed for MVP - project delete is rare |
| Should cache be warmed from DB on startup? | Coder | FUTURE | Not needed - agents re-call set_project anyway |
| Add cache stats to `scribe_doctor`? | Coder | FUTURE | Nice-to-have observability |

All items marked FUTURE are out of scope for this implementation. MVP is the 3-file change described above.
<!-- ID: references_appendix -->
**Research Document:**
- `.scribe/docs/dev_plans/session_project_caching/research/RESEARCH_SESSION_LAYER_CACHING_20260120.md`
- 627 lines, 96-99% confidence on all findings
- Verified code locations and architectural recommendations

**Related Code:**
- `shared/execution_context.py` - RouterContextManager class (lines 53-194)
- `server.py` - Tool dispatch and ExecutionContext setup (lines 400-630)
- `tools/set_project.py` - Session binding logic (lines 500-530)
- `storage/sqlite.py` - session_projects table (lines 940-945)

**Precedent:**
- `RouterContextManager._transport_sessions` dict follows exact same caching pattern
- This enhancement is additive, following established architecture
