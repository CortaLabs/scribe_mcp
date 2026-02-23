---
id: scribe_perf_optimization-research-sqlite-persist-optimization
title: "\U0001F52C Research Sqlite Persist Optimization \u2014 scribe_perf_optimization"
doc_type: RESEARCH_SQLITE_PERSIST_OPTIMIZATION
doc_name: RESEARCH_SQLITE_PERSIST_OPTIMIZATION
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 06:03:42 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Sqlite Persist Optimization — scribe_perf_optimization
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 06:01:41 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

`StateManager.persist()` in `src/scribe_mcp/state/manager.py` (lines 134-185) iterates ALL projects in the loaded state and calls `_upsert_project()` for each one sequentially. With 43 projects, this produces 43 sequential SQLite transactions (each its own `BEGIN`/`COMMIT`) dispatched as 86 `asyncio.to_thread` calls. For Postgres, it produces 43 sequential pool acquisitions and round-trips.

**The core problem has three layers:**

1. **No dirty tracking** — Every project is written on every persist() call, regardless of whether any project data changed.
2. **No batch writes** — Each upsert is an independent transaction instead of a single wrapped transaction.
3. **Wrong place for writes** — The two most frequent callers (`_store_agent_id`, `update_agent_activity`) load all projects from DB and write them back unchanged; the actual data they modify (`agent_state`) lives in an in-memory cache, not in project rows.

**Recommended approach**: Dual strategy — (1) skip the project upsert loop entirely when only `agent_state` changes, and (2) add a `batch_upsert_projects()` method to `StorageBackend` for the cases that genuinely need to write multiple projects.

Estimated effort: 2-3 hours. Estimated speedup: 95%+ for agent_identity persist() paths, 60-80% for delete_project path.
<!-- ID: research_scope -->
## Research Scope

**Research Goal:** Analyze `StateManager.persist()` cost model and identify optimization strategies for SQLite and Postgres backends.

**Files Investigated:**
- `src/scribe_mcp/state/manager.py` — StateManager.persist(), _upsert_project(), _set_global_project()
- `src/scribe_mcp/state/agent_identity.py` — Primary persist() callers
- `src/scribe_mcp/tools/delete_project.py` — Secondary persist() caller
- `src/scribe_mcp/storage/sqlite/projects.py` — SQLite upsert_project SQL
- `src/scribe_mcp/storage/sqlite/__init__.py` — SQLiteStorage class, _write_lock
- `src/scribe_mcp/storage/sqlite/internals.py` — asyncio.to_thread dispatch, write_gate, execute_many
- `src/scribe_mcp/storage/postgres/__init__.py` — PostgresStorage.upsert_project, _execute, _fetchrow
- `src/scribe_mcp/storage/base.py` — StorageBackend abstract API
- `src/scribe_mcp/storage/pool.py` — SQLiteConnectionPool

**Scope Boundary:** This research covers only the persist() path. The set_current_project(), record_tool(), and append_entry() paths are out of scope.
<!-- ID: findings -->
## Findings

### Finding 1: persist() DB Call Count Model (Confidence: 0.98)

**File:** `src/scribe_mcp/state/manager.py` lines 134-185

For a state with N projects and M session entries, a single `persist()` call generates:

| Operation | Count | Backend Calls |
|-----------|-------|--------------|
| `_upsert_project()` per state.project | N | N (SQLite: 2 async ops each = 2N thread dispatches) |
| `_set_global_project()` | 1 | 1 (set_agent_project) |
| `_upsert_project()` per session_project | up to M | up to M (2M thread dispatches for SQLite) |
| `upsert_session()` per session_mode | up to M | up to M |
| `set_session_mode()` per session_mode | up to M | up to M |

**Total backend calls:** N + 1 + up to 4M

**For the typical case (43 projects, 1-2 sessions):**
- **SQLite:** 43 * 2 = 86 `asyncio.to_thread` dispatches for project upserts alone; 43 separate `conn.commit()` calls
- **Postgres:** 43 separate `pool.acquire()` context managers, each a full network round-trip

**Per SQLite upsert cost breakdown** (`src/scribe_mcp/storage/sqlite/projects.py:69-105`):
1. Acquire `_write_lock` (asyncio.Lock in SQLiteStorage) — serializes concurrent async writes
2. `await execute_fn(INSERT OR REPLACE ... ON CONFLICT DO UPDATE)` → `asyncio.to_thread` → acquire `_write_gate` (threading.Lock) → `conn.execute()` → `conn.commit()` — 1 transaction
3. Release `_write_lock`
4. `await fetchone_fn(SELECT ... WHERE name = ?)` → `asyncio.to_thread` → `conn.execute()` (no lock for reads) — 1 read
5. Return `ProjectRecord`

Each upsert = 2 thread pool dispatches + 1 SQLite transaction + 1 read query.

---

### Finding 2: Caller Analysis (Confidence: 0.97)

**Files:** `src/scribe_mcp/state/agent_identity.py`, `src/scribe_mcp/tools/delete_project.py`

There are exactly 3 call sites for `persist()`:

**Caller 1: `agent_identity._store_agent_id()` (line 163)**
- Triggered by: `get_or_create_agent_id()` when agent ID changes or every 300s (default)
- Rate-limiting: `_should_persist()` guards with 300s interval (`SCRIBE_AGENT_ID_PERSIST_INTERVAL_SECONDS`)
- Frequency: Low — changes only on agent identity shift

**Caller 2: `agent_identity.update_agent_activity()` (line 283)**
- Triggered by: `append_entry`, `set_project`, `delete_project` — every tool call
- Rate-limiting: Inner `persist()` only fires after 60s cooldown (`SCRIBE_AGENT_ACTIVITY_PERSIST_INTERVAL_SECONDS=60`)
- Frequency: At most once per 60 seconds, despite tool calls every second

**Caller 3: `delete_project.py` (line 212)**
- Triggered by: User invoking delete_project tool
- Rate-limiting: None — fires unconditionally on each delete
- Frequency: Low — user-driven

**Key insight:** `update_agent_activity` is the highest-frequency caller but is already rate-limited. The per-call cost when persist() does fire is still O(N) across all callers.

**NO persist() calls found in:** `agent_manager.py` (only uses `.load()` and `.set_current_project()`), `append_entry.py`, `set_project.py`.

---

### Finding 3: The Core Waste — Writing Unchanged Projects (Confidence: 0.93)

**Files:** `src/scribe_mcp/state/manager.py:129-185`, `src/scribe_mcp/state/agent_identity.py:147-169`

When `_store_agent_id()` and `update_agent_activity()` call `persist()`:

1. They call `self.state_manager.load()` first → `_load_locked()` → `_load_projects()` → queries DB for ALL projects
2. They modify only `state.agent_state` (an in-memory dict) and call `persist(state)`
3. `persist()` loops over `state.projects` (all N projects that were just read from DB) and writes them all back

**The project data did not change.** The only thing that changed was `agent_state`, which is stored in `StateManager._agent_state_cache` (an in-memory field, not a DB column in `scribe_projects`). The project upsert loop writes project `name`, `repo_root`, `progress_log_path`, `docs_json` — none of which changed.

**Conclusion:** For agent_identity callers, 100% of the project upsert work in persist() is wasted I/O.

For `delete_project()`, state.projects has had one entry removed — so N-1 projects need writing. However, the deleted project has already been removed from the DB by `backend.delete_project()` before `persist()` is called. So the N-1 project writes are also redundant (projects already exist in DB unchanged).

**The only genuinely useful work in persist() for all callers is:**
- `_set_global_project()` (the 1 agent_project write for current project tracking)
- Session writes (`set_session_project`, `upsert_session`)

---

### Finding 4: SQLite Transaction Architecture (Confidence: 0.98)

**File:** `src/scribe_mcp/storage/sqlite/internals.py:91-177`

SQLiteInternals dispatches writes via `asyncio.to_thread(self.execute_sync, ...)`. Inside the thread:
- `_write_gate` (threading.Lock) serializes ALL writes globally
- Each call to `execute_sync` is a separate `BEGIN` (implicit) → `conn.execute()` → `conn.commit()`
- No way to batch multiple INSERTs into one transaction using current `_execute` API

**`execute_many()` exists** at `internals.py:103-113` and `sqlite/__init__.py:414-415`, but it:
- Accepts `List[str]` (raw SQL strings, no parameterization)  
- Runs all statements in one connection and one `commit()`
- Is only used for schema migrations
- Is NOT suitable for parameterized batch upserts as-is

**Write lock architecture:**
- `SQLiteStorage._write_lock` (asyncio.Lock) — async-layer serialization, held for duration of `_write_lock` context in projects.py
- `SQLiteInternals._write_gate` (threading.Lock) — thread-layer serialization inside to_thread
- Both locks are acquired per individual upsert operation

**WAL mode is enabled** (`PRAGMA journal_mode = WAL`) which allows concurrent reads during writes, but does NOT help with batching multiple sequential writes.

---

### Finding 5: Postgres Architecture (Confidence: 0.97)

**File:** `src/scribe_mcp/storage/postgres/__init__.py:170-204, 2011-2021`

PostgresStorage.upsert_project uses `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` — a single query, no separate fetchone needed (more efficient than SQLite).

But each call:
1. `await self._ensure_schema()` — cheap (cached flag)
2. `pool = await self._ensure_pool()` — cheap (pool already running)
3. `async with pool.acquire() as conn:` — acquires connection from asyncpg pool (min=2, max=20)
4. `await conn.fetchrow(query, *params)` — network round-trip to Postgres

With 43 projects: 43 pool acquisitions, 43 SQL round-trips (local Postgres is fast ~1ms each = ~43ms). Batching to single transaction would reduce to ~5-10ms.

asyncpg supports `conn.executemany()` natively — suitable for multi-row parameterized upserts.
<!-- ID: technical_analysis -->
## Technical Analysis

### persist() Call Flow Diagram

```
persist(state)
├── is_remote? → YES → skip all DB writes (CLIENT mode, already done)
└── NO (SQLite/Postgres)
    ├── [LOOP N] for project_name, payload in state.projects:
    │   └── _upsert_project(name, payload)
    │       ├── SQLite: async with _write_lock → asyncio.to_thread(execute INSERT OR REPLACE) → asyncio.to_thread(fetchone SELECT)
    │       └── Postgres: async with pool.acquire() → conn.fetchrow(INSERT ... RETURNING)
    │
    ├── _set_global_project(current_project)  ← 1 write, always useful
    │   └── backend.set_agent_project(agent_id="Scribe", project_name=..., ...)
    │
    ├── [LOOP M] for session_id, project_payload in state.session_projects:
    │   ├── _upsert_project(name, project_payload)  ← potentially redundant
    │   └── backend.set_session_project(session_id, project_name)  ← useful
    │
    └── [LOOP M] for session_id, mode in state.session_modes:
        ├── backend.upsert_session(session_id, mode)  ← useful
        └── backend.set_session_mode(session_id, mode)  ← useful
```

### When project upserts are useful vs. wasteful

| Caller | Are project rows stale? | Upsert needed? |
|--------|------------------------|----------------|
| `_store_agent_id()` | No — just loaded from DB | NEVER |
| `update_agent_activity()` | No — just loaded from DB | NEVER |
| `delete_project()` | Yes — 1 project removed | NOT for N-1 survivors (already in DB) |

### Existing Infrastructure for Optimization

1. **`execute_many()`** exists in `SQLiteInternals` — but takes `List[str]` (no params). Could be extended.
2. **`_write_gate` threading.Lock** — currently acquired per-upsert; could wrap entire batch.
3. **asyncpg `executemany()`** — native support for parameterized multi-row operations.
4. **`StateManager._write_lock`** (asyncio.Lock) — manager-level write serialization; already wraps persist().
5. **`_projects_cache`** in StateManager — stores last-known project data; usable for dirty checking.

### Data Flow: What Actually Changes Per Caller

```
_store_agent_id() changes:
  state.agent_state["last_agent_id"]  → written to StateManager._agent_state_cache (in-memory)
  state.projects                       → UNCHANGED (loaded from DB, written back verbatim)

update_agent_activity() changes:
  state.agent_state["activity_log"]   → written to StateManager._agent_state_cache (in-memory)
  state.agent_state["last_agent_id"]  → written to StateManager._agent_state_cache (in-memory)
  state.projects                       → UNCHANGED (loaded from DB, written back verbatim)

delete_project() changes:
  state.projects                       → 1 project REMOVED (but backend.delete_project already handled DB side)
  state.recent_projects                → project removed from list (in-memory only)
  state.current_project                → possibly None (in-memory only)
```
<!-- ID: recommendations -->
## Recommendations

### Strategy A: Skip Project Upserts Entirely (RECOMMENDED, High Impact, Low Effort)

**File to modify:** `src/scribe_mcp/state/manager.py`

**Rationale:** The project upsert loop in `persist()` is wasteful for ALL current callers. The projects in `state.projects` are always loaded from DB immediately before persist() is called, so they're already consistent. The `agent_state` changes are handled by in-memory cache updates at lines 176-185, which ALREADY happen correctly.

**Implementation:** Remove the project upsert loop from `persist()` entirely and replace it with ONLY the operations that are genuinely useful:

```python
async def persist(self, state: State) -> None:
    """Persist cache-compatible state fields into database-backed storage.

    Project rows are intentionally NOT written here — they are always
    consistent in the DB (set_current_project / set_project tool handle
    individual project upserts at creation time). This method only
    persists session-level state: current project binding, session modes.
    """
    async with self._lock:
        from scribe_mcp.storage.remote import RemoteStorageBackend
        is_remote = isinstance(self._storage_backend, RemoteStorageBackend)

        if not is_remote:
            await self._ensure_backend_ready()
            await self._run_legacy_migration_once()

            # REMOVED: for project_name, payload in state.projects — NEVER needed
            # (projects are loaded fresh from DB; they didn't change here)

            await self._set_global_project(
                project_name=state.current_project,
                updated_by=state.last_updated_by or _GLOBAL_AGENT_ID,
                session_id=None,
            )

            for session_id, project_payload in state.session_projects.items():
                project_name = self._resolve_project_name(project_payload)
                if not project_name:
                    continue
                # REMOVED: _upsert_project here too — project already in DB
                if hasattr(self._storage_backend, "set_session_project"):
                    await self._storage_backend.set_session_project(session_id, project_name)

            for session_id, mode in state.session_modes.items():
                if mode not in {"project", "sentinel"}:
                    continue
                if hasattr(self._storage_backend, "upsert_session"):
                    await self._storage_backend.upsert_session(session_id=session_id, mode=mode)
                if hasattr(self._storage_backend, "set_session_mode"):
                    await self._storage_backend.set_session_mode(session_id, mode)

        # In-memory cache updates — always run
        self._agent_state_cache = dict(state.agent_state or {})
        self._recent_projects_cache = list(state.recent_projects or [])
        self._session_projects_cache.update(dict(state.session_projects or {}))
        self._session_modes_cache.update(dict(state.session_modes or {}))
        self._activity_cache = {
            "recent_tools": list(state.recent_tools or []),
            "last_activity_at": state.last_activity_at,
            "session_started_at": state.session_started_at,
        }
```

**Impact:** Reduces persist() from N+1+2M calls to 1+2M calls. For 43 projects: 43 upserts → 0. SQLite: from 86 asyncio.to_thread calls to 0. **~95% reduction in persist() DB work**.

**Risk:** Low. The only scenario where the project loop was "needed" would be if a caller modified project data before calling persist(). Current callers only modify `agent_state`. VERIFY no new callers added in future.

---

### Strategy B: Batch Transaction Wrapping (Secondary, Medium Impact)

**Files to modify:** `src/scribe_mcp/storage/sqlite/projects.py`, `src/scribe_mcp/storage/sqlite/internals.py`, `src/scribe_mcp/storage/base.py`

Add `batch_upsert_projects()` to `StorageBackend` for cases that genuinely need multi-project writes.

**SQLite implementation sketch:**

```python
# In src/scribe_mcp/storage/sqlite/internals.py
async def execute_many_parameterized(
    self,
    query: str,
    params_list: List[tuple],
) -> None:
    """Execute one SQL statement with many parameter sets in a single transaction."""
    await asyncio.to_thread(self._execute_many_parameterized_sync, query, params_list)

def _execute_many_parameterized_sync(
    self,
    query: str,
    params_list: List[tuple],
) -> None:
    def _op() -> None:
        with self._write_gate:
            self._run_with_connection(
                lambda conn: self._executemany_write(conn, query, params_list)
            )
    self._with_lock_retry(_op, query=query, is_write=True)

def _executemany_write(
    self,
    conn: sqlite3.Connection,
    query: str,
    params_list: List[tuple],
) -> None:
    conn.executemany(query, params_list)
    conn.commit()


# In src/scribe_mcp/storage/sqlite/projects.py
async def batch_upsert_projects(
    *,
    initialise_fn: AsyncInitialise,
    internals: SQLiteInternals,
    projects: List[tuple],  # (name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed)
) -> None:
    await initialise_fn()
    query = """
        INSERT INTO scribe_projects (name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(name)
        DO UPDATE SET repo_root = excluded.repo_root,
                      progress_log_path = excluded.progress_log_path,
                      docs_json = excluded.docs_json,
                      bridge_id = excluded.bridge_id,
                      bridge_managed = excluded.bridge_managed;
    """
    await internals.execute_many_parameterized(query, projects)
```

**PostgreSQL implementation sketch:**

```python
# In src/scribe_mcp/storage/postgres/__init__.py
async def batch_upsert_projects(
    self,
    projects: List[Dict],
) -> None:
    """Upsert multiple projects in a single transaction."""
    await self._ensure_schema()
    pool = await self._ensure_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for p in projects:
                await conn.execute(
                    """
                    INSERT INTO scribe_projects
                        (name, repo_root, progress_log_path, docs_json, bridge_id, bridge_managed, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    ON CONFLICT(name) DO UPDATE SET
                        repo_root = EXCLUDED.repo_root,
                        progress_log_path = EXCLUDED.progress_log_path,
                        docs_json = EXCLUDED.docs_json,
                        bridge_id = EXCLUDED.bridge_id,
                        bridge_managed = EXCLUDED.bridge_managed,
                        updated_at = NOW()
                    """,
                    p["name"], p["repo_root"], p["progress_log_path"],
                    p.get("docs_json"), p.get("bridge_id"), p.get("bridge_managed", False),
                )
    # Note: UNNEST approach would be faster but requires asyncpg-specific syntax
```

**Impact:** For N=43 batch: SQLite from 43 transactions to 1 transaction, from 86 asyncio.to_thread to 1. Postgres from 43 round-trips to 1 transaction.

---

### Strategy C: Dirty Tracking in StateManager (Alternative, Medium Complexity)

**File to modify:** `src/scribe_mcp/state/manager.py`

Add a `_dirty_projects` set to StateManager that tracks project names modified since last persist:

```python
class StateManager:
    def __init__(self, ...):
        ...
        self._dirty_projects: set[str] = set()  # names of projects modified since last DB write

    async def _upsert_project(self, project_name: str, payload: Dict) -> None:
        # Existing upsert logic
        ...
        self._dirty_projects.discard(project_name)  # mark clean after write

    async def set_current_project(self, name, ...):
        ...
        if name:
            self._dirty_projects.add(name)  # mark dirty
        ...

    async def persist(self, state: State) -> None:
        ...
        # Only upsert dirty projects
        for project_name in list(self._dirty_projects):
            if project_name in state.projects:
                await self._upsert_project(project_name, state.projects[project_name])
        ...
```

**Impact:** Would reduce persist() writes to only changed projects. But Strategy A is simpler and achieves the same result since persist() callers don't modify projects.

**Recommendation:** Implement Strategy A first (simple, no risk). Add Strategy B if batch writes are needed for other operations in the future.

---

### Immediate Next Steps

1. **[Priority 1]** Remove the project upsert loop from `persist()` — Strategy A. Modify `src/scribe_mcp/state/manager.py` lines 151-152 and 160-164. Also remove `_upsert_project()` from session_projects loop.
2. **[Priority 2]** Add `execute_many_parameterized()` to `SQLiteInternals` and `batch_upsert_projects()` to StorageBackend — Strategy B. Add as abstract method to `base.py`, implement in `sqlite/projects.py` and `postgres/__init__.py`.
3. **[Priority 3]** Update tests in `tests/` to verify persist() no longer writes projects (regression protection).

### Risk Assessment

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Future caller modifies projects before persist() | Low | Add assertion/comment in persist() docstring |
| Removing session _upsert_project breaks session state | Medium | Verify sessions only need set_session_project, not full upsert |
| Postgres batch in single transaction causes partial failure | Low | asyncpg rolls back on exception; add error handling |
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---