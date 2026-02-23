# CLIENT MODE BOTTLENECK AUDIT

**Date:** 2026-02-17
**Researcher:** ResearchAgent-ClientAudit
**Confidence:** 0.93 overall
**Status:** COMPLETE

---

## 1. Executive Summary

**Problem:** `set_project` takes ~28 seconds in CLIENT mode because it makes 35-70+ sequential HTTP calls to the remote Hetzner server, each taking ~0.3-0.5s over Tailscale.

**Root Cause:** The CLIENT mode (`RemoteStorageBackend`) correctly proxies storage operations via HTTP, but the existing code was designed for local database access (~0.1ms per call). Three categories of waste:

| Category | HTTP Calls | Time Cost | Fix Complexity |
|----------|-----------|-----------|----------------|
| **persist() fan-out** | N+M per call (N=projects, M=sessions) | 10-25s | Medium |
| **Redundant project lookups** | 3-5 per set_project | 1.5-2.5s | Low |
| **Unnecessary operations** | 4-6 per set_project | 2-3s | Low |
| **Total** | **35-70+** | **~14-28s** | |

**Key Finding:** `execute_batch()` already exists on `RemoteStorageBackend` (line 93) but NO call site uses it. This is the single biggest optimization lever.

---

## 2. Call Chain Analysis: set_project -> Remote HTTP Calls

Each entry below identifies a remote HTTP call triggered during a single `set_project` invocation in CLIENT mode.

### 2.1 Phase 1: record_tool (set_project.py:248)

**Call chain:** `set_project` -> `state_manager.record_tool('set_project')` -> `_load_locked()` -> `_load_projects()` -> `list_projects_by_repo(repo_root)` 

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `list_projects_by_repo` | manager.py:390 | YES (1 HTTP) | Once per call (30s cache TTL) | Fetches ALL projects for this repo root |
| `get_session_project` | manager.py:426 | No (in-memory) | Once | RemoteStorageBackend stores in dict |
| `get_session_mode` | manager.py:461 | No (in-memory) | Once | |
| `get_session_activity` | manager.py:472 | No (in-memory) | Once | |
| `update_session_activity` | manager.py:188 | No (no-op) | Once | RemoteStorageBackend: pass |

**Subtotal: 1 HTTP call** (or 0 if cache is warm from <30s ago)

### 2.2 Phase 2: update_agent_activity (set_project.py:277)

**Call chain:** `set_project` -> `agent_identity.update_agent_activity(agent_id, 'set_project', ...)` -> `state_manager.persist(state)` -> loop over ALL projects calling `_upsert_project` each

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `persist()` -> `_upsert_project` per project | manager.py:140-141 | YES (N HTTP) | N = number of projects in state | **BIGGEST BOTTLENECK** |
| `persist()` -> `_set_global_project` | manager.py:143 -> 510 | No (in-memory) | Once | set_agent_project is in-memory |
| `persist()` -> `_upsert_project` per session project | manager.py:149-153 | YES (M HTTP) | M = session projects | Also calls set_session_project (in-memory) |
| `persist()` -> `upsert_session` per session mode | manager.py:160-161 | No (in-memory) | Per session | |

**CRITICAL:** `_last_activity_persist_at` initializes to `0.0` (agent_identity.py:40), so the debounce check at line 257 (`now - 0.0 < 60.0` is FALSE) means the FIRST call to `update_agent_activity` ALWAYS triggers `persist()`. With ~20-30 projects typical, this is **20-30 HTTP calls x 0.4s = 8-12 seconds**.

**Subtotal: N+M HTTP calls** (typically 20-40 calls, ~8-16s)

### 2.3 Phase 3: prepare_context (set_project.py:282)

**Call chain:** `prepare_context` -> `resolve_logging_context` -> `backend.get_session_project` + `backend.fetch_project`

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `get_session_project` | logging_utils.py:122 | No (in-memory) | Once | |
| `fetch_project` | logging_utils.py:143 | YES (1 HTTP) | Once | Only if session project found |

**Note:** `set_project` passes `require_project=False` and already did `record_tool` so `state_snapshot` is passed in, avoiding a second `record_tool` call.

**Subtotal: 0-1 HTTP call**

### 2.4 Phase 4: _validate_project_paths (set_project.py:326)

**Call chain:** `_validate_project_paths` -> `_gather_known_projects` -> `state_manager.load()` -> `_load_locked()` -> `_load_projects()`

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `list_projects_by_repo` | manager.py:390 | YES (0-1 HTTP) | Once | Cache may be warm from Phase 1 |

**Subtotal: 0-1 HTTP call** (depends on cache TTL)

### 2.5 Phase 5: _check_slug_collision (set_project.py:411)

**Call chain:** `_check_slug_collision(name, backend)` -> `backend.fetch_project(name)` + `backend.list_projects()`

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `fetch_project(name)` | set_project.py:163 | YES (1 HTTP) | Once | Check if exact name exists |
| `list_projects()` | set_project.py:169 | YES (1 HTTP) | Once | Fetch ALL projects to check slugs |

**Subtotal: 2 HTTP calls** (~0.8s)

### 2.6 Phase 6: backend.upsert_project (set_project.py:417)

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `upsert_project` | set_project.py:417 | YES (1 HTTP) | Once | The actual project creation/update |

**Subtotal: 1 HTTP call** (~0.4s)

### 2.7 Phase 7: upsert_dev_plan (set_project.py:468-475)

**Call chain:** Loop over 4 core doc types, calling `backend.upsert_dev_plan` for each existing file.

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `upsert_dev_plan` | set_project.py:468 | YES (up to 4 HTTP) | Per core doc type | architecture, phase_plan, checklist, progress_log |

**Subtotal: up to 4 HTTP calls** (~1.6s)

### 2.8 Phase 8: ensure_agent_session (set_project.py:498)

**Call chain:** `ensure_agent_session` -> `agent_identity.resume_agent_session` -> `agent_manager.start_session`

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `get_current_project` | agent_identity.py:192 | No (in-memory) | Once | get_agent_project is in-memory |
| `upsert_agent_session` | agent_manager.py:71 | No (in-memory) | Once | |
| `log_agent_event` | agent_manager.py:79 | No (no-op) | Once | Uses _execute which RemoteBackend lacks |
| `_mirror_session_to_json_state` | agent_manager.py:88 | No (no-op) | Once | **Already fixed to no-op** |

**Subtotal: 0 HTTP calls**

### 2.9 Phase 9: agent_manager.set_current_project (set_project.py:509)

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `get_agent_project` | agent_manager.py:121 | No (in-memory) | Once | |
| `set_agent_project` | agent_manager.py:129 | No (in-memory) | Once | |
| `log_agent_event` | agent_manager.py:154 | No (no-op) | Once | No _execute on RemoteBackend |
| `_mirror_project_to_json_state` -> `state_manager.load` | agent_manager.py:317 | YES (0-1 HTTP) | Once | Calls _load_projects if cache expired |

**Subtotal: 0-1 HTTP call**

### 2.10 Phase 10: state_manager.set_current_project (set_project.py:539)

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `_upsert_project` | manager.py:235 | YES (1 HTTP) | Once | Upserts the current project |
| `set_session_project` | manager.py:238 | No (in-memory) | Once | |
| `upsert_agent_recent_project` | manager.py:242 | No (in-memory) | Once | |
| `_set_global_project` -> `set_agent_project` | manager.py:247-250 | No (in-memory) | Once | |
| `_load_locked` -> `_load_projects` | manager.py:253 | YES (0-1 HTTP) | Once | Cache may be warm |

**Subtotal: 1-2 HTTP calls**

### 2.11 Phase 11: Direct backend session ops (set_project.py:556-591)

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `set_session_project` | set_project.py:562 | No (in-memory) | Once | |
| `set_session_mode` | set_project.py:578 | No (in-memory) | Once | |
| `upsert_session` | set_project.py:581 | No (in-memory) | Once | |
| `upsert_agent_recent_project` | set_project.py:591 | No (in-memory) | Once | |

**Subtotal: 0 HTTP calls**

### 2.12 Phase 12: prepare_context (second call, set_project.py:596)

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `fetch_project` | logging_utils.py:143 | YES (0-1 HTTP) | Once | May use different session key |

**Subtotal: 0-1 HTTP call**

### 2.13 Phase 13: count_entries (set_project.py:615)

| Operation | File:Line | Remote? | Frequency | Notes |
|-----------|-----------|---------|-----------|-------|
| `count_entries` | set_project.py:615 | YES (1 HTTP) | Once | Entry count for SITREP display |

**Subtotal: 1 HTTP call**

### 2.14 TOTAL SUMMARY

| Phase | Min HTTP | Max HTTP | Primary Operation |
|-------|---------|---------|-------------------|
| 1. record_tool | 0 | 1 | list_projects_by_repo |
| 2. update_agent_activity + persist | 0 | **N+M** | _upsert_project x (projects + sessions) |
| 3. prepare_context #1 | 0 | 1 | fetch_project |
| 4. _validate_project_paths | 0 | 1 | list_projects_by_repo |
| 5. _check_slug_collision | 2 | 2 | fetch_project + list_projects |
| 6. upsert_project | 1 | 1 | upsert_project |
| 7. upsert_dev_plan | 0 | 4 | upsert_dev_plan x4 |
| 8. ensure_agent_session | 0 | 0 | all in-memory |
| 9. agent_manager.set_current_project | 0 | 1 | list_projects_by_repo |
| 10. state_manager.set_current_project | 1 | 2 | _upsert_project + list_projects_by_repo |
| 11. backend session ops | 0 | 0 | all in-memory |
| 12. prepare_context #2 | 0 | 1 | fetch_project |
| 13. count_entries | 1 | 1 | count_entries |
| **TOTAL** | **5** | **N+M+14** | |

**With N=25 projects, M=5 sessions:** 5 + 25 + 5 + 14 = **49 HTTP calls**
**With N=40 projects, M=10 sessions:** 5 + 40 + 10 + 14 = **69 HTTP calls**
**At 0.4s per call over Tailscale:** 49 x 0.4 = **19.6 seconds** to 69 x 0.4 = **27.6 seconds**

This matches the observed ~28 second latency.

---

## 3. Other Bottleneck Operations (Non-upsert)

### 3.1 list_projects_by_repo / list_projects

Called by `_load_projects()` (manager.py:390) which is called by `_load_locked()`, which is called by:
- `record_tool()` -> `_load_locked()` (always)
- `set_current_project()` -> `_load_locked()` (always)
- `load()` -> `_load_locked()` (always)
- `persist()` -> `_run_legacy_migration_once()` -> not directly, but persist calls `_load_locked` indirectly

The 30-second cache TTL (`_PROJECT_CACHE_TTL_SECONDS`, manager.py:38) helps when calls happen within the same set_project, but on the FIRST call it always misses.

### 3.2 fetch_project

Called by:
- `resolve_logging_context` (logging_utils.py:143) - 2x per set_project
- `_check_slug_collision` (set_project.py:163) - 1x per set_project
- `get_or_create_storage_project` (runtime.py:126) - per manage_docs call
- `_get_or_create_storage_project` (special_create.py:67) - per special create
- `append_entry` (append_entry.py:650, 1911) - per append_entry call

### 3.3 count_entries

Called once per set_project (line 615) for the SITREP display. This is 1 HTTP call.

---

## 4. read_recent / append_entry CLIENT Mode Paths

### 4.1 append_entry Path

**Per single-entry append_entry call:**
1. `state_manager.record_tool('append_entry')` -> _load_locked -> `list_projects_by_repo` [0-1 HTTP, cached]
2. `resolve_logging_context` -> `get_session_project` [in-memory] + `fetch_project` [1 HTTP]
3. DB mirror: `backend.fetch_project` [1 HTTP] + conditional `backend.upsert_project` [0-1 HTTP]
4. `backend.insert_entry` [1 HTTP]

**Total per append_entry: 2-4 HTTP calls** (~0.8-1.6s)

The `fetch_project` is called both in `resolve_logging_context` and in the DB mirror block -- that is a redundant second fetch.

### 4.2 read_recent Path

**Per read_recent call:**
1. `state_manager.record_tool` -> `list_projects_by_repo` [0-1 HTTP]
2. `resolve_logging_context` -> `fetch_project` [1 HTTP]
3. `backend.fetch_project` [1 HTTP] (for the storage record)
4. `backend.fetch_recent_entries_paginated` [1 HTTP]

**Total per read_recent: 2-4 HTTP calls** (~0.8-1.6s)

### 4.3 query_entries Path

Similar to read_recent: 2-4 HTTP calls per invocation.

---

## 5. Prioritized Fix List

Ordered by impact (estimated time saved).

### FIX 1 (CRITICAL): Make persist() a no-op in CLIENT mode
**Impact:** Eliminates N+M HTTP calls (typically 25-50 calls, ~10-20s saved)
**File:** `src/scribe_mcp/state/manager.py` lines 134-173
**Change:** At the top of `persist()`, check if `self._storage_backend` is `RemoteStorageBackend` and return early. The persist() method re-upserts ALL projects which is completely unnecessary -- the authoritative data is already in the remote database. persist() was designed for JSON state mirroring which is irrelevant in CLIENT mode.

```python
async def persist(self, state: State) -> None:
    async with self._lock:
        await self._ensure_backend_ready()
        # In CLIENT mode, the remote DB is the source of truth.
        # Re-upserting every project is pure waste.
        if isinstance(self._storage_backend, RemoteStorageBackend):
            # Still update local caches for in-process consistency
            self._agent_state_cache = dict(state.agent_state or {})
            self._recent_projects_cache = list(state.recent_projects or [])
            self._session_projects_cache.update(dict(state.session_projects or {}))
            self._session_modes_cache.update(dict(state.session_modes or {}))
            return
        # ... existing persist logic for local backends
```

**Alternative:** Add a `client_mode` flag to StateManager init and skip the upsert loop.

### FIX 2 (HIGH): Eliminate _check_slug_collision or cache it
**Impact:** Saves 2 HTTP calls (~0.8s)
**File:** `src/scribe_mcp/tools/set_project.py` lines 140-194
**Change:** The slug collision check calls `fetch_project` + `list_projects` sequentially. Since `_load_projects` already fetched all projects (cached), use the StateManager cache instead of hitting the remote backend directly. Or simply skip the collision check when the project already exists (which is the common case -- re-activating an existing project).

```python
async def _check_slug_collision(name, backend):
    # Skip entirely if project already exists (re-activation, not creation)
    existing = await backend.fetch_project(name)
    if existing:
        return None  # Not a collision, just re-opening
    # For new projects, use state_manager cache instead of list_projects
    state = await server_module.state_manager.load()
    canonical_slug = normalize_project_input(name)
    for project_name in state.projects:
        if normalize_project_input(project_name) == canonical_slug and project_name != name:
            return {"ok": False, "error": f"Collision..."}
    return None
```

### FIX 3 (HIGH): Eliminate duplicate upsert_project calls
**Impact:** Saves 1-2 HTTP calls (~0.4-0.8s)
**File:** `src/scribe_mcp/tools/set_project.py` + `src/scribe_mcp/state/manager.py`
**Issue:** `set_project` calls `backend.upsert_project` directly at line 417, THEN `state_manager.set_current_project` calls `_upsert_project` AGAIN at line 235 for the same project. This is a duplicate upsert of the same project record.
**Change:** Pass the already-created `project_record` from line 417 to `set_current_project` to skip the internal `_upsert_project`. Or have `set_current_project` accept a `skip_upsert=True` flag.

### FIX 4 (HIGH): Batch upsert_dev_plan calls
**Impact:** Saves 3 HTTP calls (~1.2s) by batching 4 into 1
**File:** `src/scribe_mcp/tools/set_project.py` lines 452-477
**Change:** Use `RemoteStorageBackend.execute_batch()` (already implemented at line 93!) to send all 4 upsert_dev_plan operations in a single HTTP request.

```python
if hasattr(backend, 'execute_batch'):
    ops = []
    for plan_type, path_str in core_docs.items():
        if path_str and Path(path_str).exists():
            ops.append({"op": "upsert_dev_plan", "args": {
                "project_id": project_record.id,
                "project_name": name,
                "plan_type": plan_type,
                "file_path": str(path_str),
                "version": "1.0",
                "metadata": {"source": "set_project"},
            }})
    if ops:
        await backend.execute_batch(ops)
```

### FIX 5 (MEDIUM): Cache fetch_project results within a tool call
**Impact:** Saves 1-3 HTTP calls across the tool lifecycle (~0.4-1.2s)
**File:** Multiple (logging_utils.py, set_project.py)
**Issue:** `fetch_project` for the SAME project name is called 2-4 times during a single set_project: once in `_check_slug_collision`, once in `prepare_context`, once in `set_current_project`'s `_load_locked`, and once in `prepare_context` again.
**Change:** Add a simple `_fetch_project_cache: Dict[str, ProjectRecord]` to `RemoteStorageBackend` with a short TTL (e.g., 5 seconds). Or pass the project record around explicitly.

### FIX 6 (MEDIUM): Skip _validate_project_paths for existing projects
**Impact:** Saves 0-1 HTTP call (~0.4s)
**File:** `src/scribe_mcp/tools/set_project.py` line 326
**Change:** `_validate_project_paths` calls `_gather_known_projects` which loads all state. For existing projects (re-activation), path validation is unnecessary -- paths haven't changed. Only validate for NEW projects.

### FIX 7 (MEDIUM): Eliminate second prepare_context call
**Impact:** Saves 0-1 HTTP call (~0.4s)
**File:** `src/scribe_mcp/tools/set_project.py` line 596
**Change:** The second `prepare_context` call at line 596 is just for attaching reminders to the response. Use the first context or build reminder context without a full project resolution.

### FIX 8 (LOW): Batch ALL remote operations via execute_batch
**Impact:** Reduces 5-10 individual calls to 1-2 batch calls (~2-4s)
**File:** `src/scribe_mcp/storage/remote.py` + call sites
**Change:** The `execute_batch()` method already exists. Create a `BatchContext` context manager that collects operations and sends them in one HTTP call:

```python
async with backend.batch() as batch:
    batch.upsert_project(name=..., ...)
    batch.upsert_dev_plan(project_id=..., ...)
    batch.upsert_dev_plan(project_id=..., ...)
    # All sent as single HTTP request
```

This is the most impactful long-term change but requires refactoring call sites.

---

## 6. Migration.py Impact Assessment

`migrate_legacy_state_file` (migration.py:97) calls `upsert_project` once per legacy project (line 161) and once per session project (line 218). However, `_run_legacy_migration_once` (manager.py:338) has an `_legacy_migration_checked` flag that ensures it only runs ONCE per StateManager lifetime. It also requires a legacy state file to exist (`state.json`), which should not exist in CLIENT mode. **Impact: LOW (one-time only, likely never triggers in CLIENT mode)**.

---

## 7. Handoff Notes for Architect

1. **Fix 1 is non-negotiable** -- persist() fan-out is ~80% of the problem. Making it a no-op (or cache-only) in CLIENT mode is the single highest-impact change.

2. **Fix 4 uses existing infrastructure** -- execute_batch() is already implemented and tested. Just need to use it.

3. **Fix 8 is the strategic solution** -- a BatchContext pattern would solve the problem permanently for all tools, not just set_project.

4. **RemoteStorageBackend design is sound** -- the in-memory/remote split is correct. The problem is in the callers, not the backend.

5. **append_entry has the same category of problem** (2-4 HTTP calls per entry) but is less acute because users don't call it 70 times in a row. Still worth optimizing.

6. **The db_mirror error in append_entry** (`RemoteStorageBackend.insert_entry() got an unexpected keyword argument 'log_type'`) indicates the append_entry db mirror code is passing parameters the remote backend doesn't accept. This is a separate bug.

---

## 8. Estimated Impact After Fixes

| Scenario | Before | After Fix 1 | After All Fixes |
|----------|--------|------------|------------------|
| set_project (25 projects) | 49 calls / ~19.6s | 14 calls / ~5.6s | 5-8 calls / ~2-3s |
| set_project (40 projects) | 69 calls / ~27.6s | 14 calls / ~5.6s | 5-8 calls / ~2-3s |
| append_entry | 2-4 calls / ~1.2s | 2-4 calls / ~1.2s | 1-2 calls / ~0.6s |
| read_recent | 2-4 calls / ~1.2s | 2-4 calls / ~1.2s | 1-2 calls / ~0.6s |

**Fix 1 alone would reduce set_project from ~28s to ~5.6s (80% improvement).**
**All fixes combined would achieve ~2-3s (90%+ improvement).**
