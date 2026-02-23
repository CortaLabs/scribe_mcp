---
id: scribe_perf_optimization-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_perf_optimization"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 06:13:22 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — scribe_perf_optimization
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 05:57:35 UTC

> Architecture guide for scribe_perf_optimization.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## Problem Statement

### Context

Scribe MCP in CLIENT mode proxies all storage operations via HTTP to a remote Hetzner server over Tailscale. Two critical performance bottlenecks have been identified through instrumented research:

1. **persist() fan-out** (ALL backends): `StateManager.persist()` iterates ALL projects (N=43) and calls `_upsert_project()` for each one, writing back data that was just loaded unchanged from the DB. This produces 43 sequential SQLite transactions (86 `asyncio.to_thread` calls) or 43 Postgres round-trips. In CLIENT mode, these become 43 sequential HTTP calls taking ~17 seconds. The project upsert loop is provably wasteful for ALL 3 current callers (`_store_agent_id`, `update_agent_activity`, `delete_project`).

2. **set_project HTTP call count** (CLIENT mode): `set_project` makes 8-9 sequential HTTP calls, reducible to 2-3 through batching, caching, and elimination of redundant calls.

3. **CortaStore minor issues** (CLIENT mode): Wasteful PostgresStorage object creation at import time, and no startup health probe for CortaStore connectivity.

### Measured Before State

| Metric | Current | Target |
|--------|---------|--------|
| persist() project upserts (SQLite, N=43) | 43 transactions / 86 thread dispatches | 0 transactions / 0 dispatches |
| persist() project upserts (Postgres, N=43) | 43 pool acquisitions / 43 round-trips | 0 |
| persist() project upserts (CLIENT, N=43) | 43 HTTP calls / ~17s | 0 HTTP calls / 0s |
| set_project HTTP calls (CLIENT) | 8-9 calls / ~3.6s | 2-3 calls / ~1.2s |
| set_project total time (CLIENT, N=43) | ~28s (incl. persist) | ~1.2s |
| Module import (CLIENT + SCRIBE_DB_URL) | Creates wasted PostgresStorage | No wasted object |
| CortaStore startup | Silent on connectivity failure | Warning log if unreachable |

### Goals

- **G1**: Eliminate all redundant project upserts from persist() for ALL backends (95%+ reduction in persist() DB work)
- **G2**: Reduce set_project HTTP calls from 8-9 to 2-3 (batch upsert_dev_plan, cache fetch_project, skip count_entries for new)
- **G3**: Fix CortaStore minor issues (wasteful PG init, missing health probe)
- **G4**: Zero behavioral regressions -- all existing tests must pass, no observable change in tool output

### Research Documents

- `RESEARCH_SQLITE_PERSIST_OPTIMIZATION.md` -- persist() cost model, caller analysis, Strategy A recommendation
- `RESEARCH_SET_PROJECT_CALL_REDUCTION.md` -- HTTP call inventory, OPT-1/2/3 designs
- `RESEARCH_CORTA_STORE_CLIENT_MODE.md` -- CortaStore integration audit, 2 minor issues
- `RESEARCH_CLIENT_MODE_BOTTLENECK_AUDIT_20260217.md` -- Broader bottleneck audit (prior project, provides context)
<!-- ID: requirements_constraints -->
## 2. Requirements and Constraints

### Functional Requirements

- **FR-1**: Remove the project upsert loop from `persist()` for all backends -- projects loaded from DB are never modified by persist() callers
- **FR-2**: Keep session operations (`set_session_project`, `upsert_session`, `set_session_mode`) in persist() -- these ARE needed
- **FR-3**: Keep in-memory cache updates at the end of persist() -- these ARE needed
- **FR-4**: Batch 4x sequential `upsert_dev_plan` calls into 1 `execute_batch()` call in set_project
- **FR-5**: Add project-record cache to `RemoteStorageBackend` with 10s TTL to eliminate redundant `fetch_project` HTTP calls
- **FR-6**: Skip `count_entries` HTTP call for new projects (entry_count is always 0 when docs_were_generated)
- **FR-7**: Make `create_storage_backend()` check `settings.mode` when no explicit mode parameter is passed
- **FR-8**: Add non-fatal health probe to `CortaStoreProvider.setup()` -- log warning if CortaStore is unreachable

### Non-Functional Requirements

- **NFR-1**: Zero behavioral regressions -- all existing tests pass
- **NFR-2**: No new dependencies
- **NFR-3**: Changes must be backward-compatible (no API signature changes)
- **NFR-4**: All changes are idempotent (safe to deploy incrementally)

### Constraints

- **C-1**: `_mirror_session_to_json_state` is already a no-op (agent_manager.py:297-306) -- leave it alone
- **C-2**: The `isinstance(RemoteStorageBackend)` guard in persist() (manager.py:144-146) was added as a hotfix. Once the project upsert loop is removed for ALL backends, this guard should be removed to simplify the code
- **C-3**: `execute_batch()` on RemoteStorageBackend (remote.py:93-112) already exists and `upsert_dev_plan` is in the OPERATION_ALLOWLIST (server_sse.py:94) -- no server-side changes needed for OPT-1
- **C-4**: The `_check_slug_collision` function (set_project.py:140-194) calls `fetch_project` then `list_projects`. With project cache (FR-5), the first call becomes a cache hit, making OPT-4 (refactor slug check) unnecessary
<!-- ID: architecture_overview -->
## 3. Architecture Overview

### Solution Summary

Three surgical optimization tracks targeting different layers of the Scribe MCP stack. All changes are isolated edits to existing files -- no new modules, no new abstractions, no API changes.

### Track B: persist() Cleanup (Phase 1 -- ALL backends)

**File: `src/scribe_mcp/state/manager.py` lines 134-185**

**Current state:** persist() has a project upsert loop (lines 151-152) that iterates ALL projects in state and writes each back to the database. A `RemoteStorageBackend` guard (lines 144-146) already skips this for CLIENT mode. The session_projects loop (lines 160-164) also calls `_upsert_project()` redundantly.

**Design:** Remove the project upsert loop entirely from persist() for ALL backends, not just Remote. This eliminates the need for the isinstance check. The method becomes:

```
persist(state) -> None:
    # NO project upsert loop (removed -- projects are never dirty here)
    _set_global_project(current_project)   # 1 write, always useful
    for session_id, project in session_projects:
        set_session_project(session_id, project_name)   # session binding only, no upsert
    for session_id, mode in session_modes:
        upsert_session(session_id, mode)
        set_session_mode(session_id, mode)
    # Update in-memory caches (unchanged)
```

**Rationale (per RESEARCH_SQLITE_PERSIST_OPTIMIZATION.md, Finding 3):** All 3 callers load projects from DB then call persist() without modifying project data. The upsert writes back identical data 100% of the time.

### Track A: set_project Call Reduction (Phase 2 -- CLIENT mode)

**Files: `src/scribe_mcp/tools/set_project.py`, `src/scribe_mcp/storage/remote.py`**

Three independent optimizations:

**OPT-1: Batch upsert_dev_plan** (set_project.py:452-478)
- Replace 4x sequential `await backend.upsert_dev_plan()` with 1x `await backend.execute_batch(ops)`
- Only when `hasattr(backend, "execute_batch")` (CLIENT mode only -- SQLite/Postgres backends do not have this method)
- Fallback to sequential for non-Remote backends

**OPT-2: Project record cache** (storage/remote.py)
- Add `_project_cache: Dict[str, Tuple[ProjectRecord, float]]` to RemoteStorageBackend
- After `upsert_project()` returns, cache the result with 10s TTL
- On `fetch_project()`, check cache first -- if within TTL, return cached
- This eliminates the slug collision fetch (#1) and logging_utils fetch (#8) without code changes to callers

**OPT-3: Skip count_entries for new projects** (set_project.py:614-622)
- When `docs_were_generated` is True, set `entry_count = 0` without HTTP call
- New projects always have 0 entries -- no need to ask the server

**Combined effect:** 8-9 HTTP calls reduced to 2-3 (upsert_project + batched upsert_dev_plan + optional count_entries)

### Track C: CortaStore Fixes (Phase 3 -- CLIENT mode)

**FIX-1: Wasteful PostgresStorage creation** (storage/__init__.py:13-72)
- `create_storage_backend()` does not check `settings.mode` when called without explicit `mode` parameter
- Module-level call at server.py:117 passes no mode, causing PostgresStorage creation when SCRIBE_DB_URL is set
- Fix: Check `settings.mode` inside `create_storage_backend()` and return RemoteStorageBackend when mode is "client"

**FIX-2: CortaStore health probe** (object_store/providers/corta.py:45-49)
- `CortaStoreProvider.setup()` creates httpx client but does not probe connectivity
- Fix: Add optional `GET /health` probe with 2s timeout after client creation. Log warning on failure, do NOT hard-fail

**FIX-3: Documentation** (.env.example)
- Note that `SCRIBE_DB_URL` is not needed in CLIENT mode

### Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Future persist() caller modifies projects before calling persist | Low | Medium | Add docstring comment + assertion in persist() |
| Project cache serves stale data after external update | Low | Low | 10s TTL ensures staleness is bounded; only affects CLIENT mode re-fetch within same tool call |
| execute_batch partial failure | Low | Low | Server rolls back entire batch on any error; fallback to sequential on batch error |
| CortaStore health probe adds startup latency | Low | Low | 2s timeout cap; non-blocking; skip if no URL configured |
<!-- ID: detailed_design -->
## 4. Detailed Design

### 4.1 persist() Cleanup (Track B)

**File: `src/scribe_mcp/state/manager.py`**

#### Changes to `persist()` method (lines 134-185):

1. **Remove the project upsert loop** (lines 151-152):
   ```python
   # DELETE these 2 lines:
   for project_name, payload in state.projects.items():
       await self._upsert_project(project_name, payload)
   ```

2. **Remove the isinstance(RemoteStorageBackend) guard** (lines 144-146):
   ```python
   # DELETE these 3 lines:
   from scribe_mcp.storage.remote import RemoteStorageBackend
   is_remote = isinstance(self._storage_backend, RemoteStorageBackend)
   if not is_remote:
   ```

3. **Remove _upsert_project from session_projects loop** (line 164):
   ```python
   # DELETE this 1 line:
   await self._upsert_project(project_name, project_payload)
   ```

4. **Flatten the remaining code** (remove `if not is_remote:` nesting):
   - `_ensure_backend_ready()` and `_run_legacy_migration_once()` should still run for local backends
   - Need a simpler backend-type check: `if not isinstance(self._storage_backend, RemoteStorageBackend):`
   - Actually, since session ops in RemoteStorageBackend are in-memory, we still need them to run for all backends
   - The simplest correct approach: keep `_ensure_backend_ready` and `_run_legacy_migration_once` behind a local-backend check, but let session ops run for ALL backends

**Final persist() shape:**

```python
async def persist(self, state: State) -> None:
    """Persist session-level state into database-backed storage.

    Project rows are NOT written here -- they are already consistent in the
    DB (set_project tool handles individual project upserts at creation time).
    """
    async with self._lock:
        from scribe_mcp.storage.remote import RemoteStorageBackend
        is_remote = isinstance(self._storage_backend, RemoteStorageBackend)

        if not is_remote:
            await self._ensure_backend_ready()
            await self._run_legacy_migration_once()

        # REMOVED: project upsert loop (projects never change in persist callers)

        if not is_remote:
            await self._set_global_project(
                project_name=state.current_project,
                updated_by=state.last_updated_by or _GLOBAL_AGENT_ID,
                session_id=None,
            )

        for session_id, project_payload in state.session_projects.items():
            project_name = self._resolve_project_name(project_payload)
            if not project_name:
                continue
            # REMOVED: _upsert_project here (redundant)
            if hasattr(self._storage_backend, "set_session_project"):
                await self._storage_backend.set_session_project(session_id, project_name)

        for session_id, mode in state.session_modes.items():
            if mode not in {"project", "sentinel"}:
                continue
            if hasattr(self._storage_backend, "upsert_session"):
                await self._storage_backend.upsert_session(session_id=session_id, mode=mode)
            if hasattr(self._storage_backend, "set_session_mode"):
                await self._storage_backend.set_session_mode(session_id, mode)

        # Always update in-memory caches
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

**Note on `_set_global_project`:** This calls `set_agent_project()` which is in-memory on RemoteStorageBackend. For local backends it writes to DB. We keep it behind `if not is_remote:` because the remote server already has the project binding. However, this is a refinement -- the coder can keep the isinstance check for `_set_global_project` only.

### 4.2 Batch upsert_dev_plan (Track A, OPT-1)

**File: `src/scribe_mcp/tools/set_project.py` lines 452-478**

Replace the sequential loop with a batch call when running on RemoteStorageBackend:

```python
try:
    if hasattr(backend, "upsert_dev_plan") and project_record:
        from pathlib import Path as _Path

        core_docs = {
            "architecture": docs.get("architecture"),
            "phase_plan": docs.get("phase_plan"),
            "checklist": docs.get("checklist"),
            "progress_log": docs.get("progress_log"),
        }

        # OPT-1: Batch when execute_batch is available (CLIENT mode)
        if hasattr(backend, "execute_batch"):
            ops = []
            for plan_type, path_str in core_docs.items():
                if not path_str:
                    continue
                path_obj = _Path(path_str)
                if not path_obj.exists():
                    continue
                ops.append({
                    "op": "upsert_dev_plan",
                    "args": {
                        "project_id": project_record.id,
                        "project_name": name,
                        "plan_type": plan_type,
                        "file_path": str(path_obj),
                        "version": "1.0",
                        "metadata": {"source": "set_project"},
                    },
                })
            if ops:
                await backend.execute_batch(ops)
        else:
            # Fallback: sequential upserts for local backends
            for plan_type, path_str in core_docs.items():
                if not path_str:
                    continue
                path_obj = _Path(path_str)
                if not path_obj.exists():
                    continue
                await backend.upsert_dev_plan(
                    project_id=project_record.id,
                    project_name=name,
                    plan_type=plan_type,
                    file_path=str(path_obj),
                    version="1.0",
                    metadata={"source": "set_project"},
                )
except Exception as exc:
    logger.warning("dev_plans upsert failed in set_project: %s", exc)
```

### 4.3 Project Record Cache (Track A, OPT-2)

**File: `src/scribe_mcp/storage/remote.py`**

Add to `RemoteStorageBackend.__init__()`:

```python
import time
self._project_cache: dict[str, tuple[ProjectRecord, float]] = {}  # name -> (record, expires_at)
```

Modify `upsert_project()` to cache result:

```python
async def upsert_project(self, *, name, repo_root, progress_log_path, docs_json=None, ...) -> ProjectRecord:
    result = await self._call("upsert_project", ...)
    record = self._to_project_record(result)
    if record:
        self._project_cache[name] = (record, time.monotonic() + 10.0)
    return record
```

Modify `fetch_project()` to check cache first:

```python
async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
    cached = self._project_cache.get(name)
    if cached:
        record, expires_at = cached
        if time.monotonic() < expires_at:
            return record
        del self._project_cache[name]  # expired
    result = await self._call("fetch_project", name=name)
    record = self._to_project_record(result)
    if record:
        self._project_cache[name] = (record, time.monotonic() + 10.0)
    return record
```

### 4.4 Skip count_entries for New Projects (Track A, OPT-3)

**File: `src/scribe_mcp/tools/set_project.py` lines 614-622**

```python
if backend and project_record:
    if docs_were_generated:
        entry_count = 0  # New project has 0 entries, skip HTTP call
    else:
        try:
            entry_count = await backend.count_entries(
                project_record,
                filters={"log_type": ["progress", "bugs", "bug", "security"]},
            )
        except TypeError:
            entry_count = await backend.count_entries(project_record)
```

**Note:** `docs_were_generated` is computed at line 630 currently (AFTER the count_entries call). The coder must move the `docs_were_generated` computation to before the count_entries block, or use the `doc_result` dict directly.

### 4.5 create_storage_backend Mode Check (Track C, FIX-1)

**File: `src/scribe_mcp/storage/__init__.py` lines 13-72**

Add mode auto-detection when no explicit mode is passed:

```python
def create_storage_backend(mode=None):
    from scribe_mcp.config.settings import settings

    # Auto-detect CLIENT mode when not explicitly provided
    if mode is None and getattr(settings, "mode", None) == "client":
        from scribe_mcp.config.mode_detection import OperatingMode
        mode = OperatingMode.CLIENT

    # CLIENT mode: proxy all DB operations to remote
    if mode is not None:
        from scribe_mcp.config.mode_detection import OperatingMode as _OM
        if mode == _OM.CLIENT:
            from scribe_mcp.storage.remote import RemoteStorageBackend
            return RemoteStorageBackend(
                server_url=settings.remote_server_url or "",
                timeout=settings.remote_connect_timeout,
            )

    # ... rest of factory unchanged
```

### 4.6 CortaStore Health Probe (Track C, FIX-2)

**File: `src/scribe_mcp/object_store/providers/corta.py` lines 45-49**

```python
async def setup(self) -> None:
    self._client = httpx.AsyncClient(
        base_url=self._base_url,
        timeout=httpx.Timeout(self._timeout),
    )
    # Non-fatal connectivity probe
    try:
        resp = await self._client.get("/health", timeout=2.0)
        if resp.status_code != 200:
            logger.warning(
                "CortaStore health check returned %d at %s -- sync may fail",
                resp.status_code, self._base_url
            )
    except Exception as exc:
        logger.warning(
            "CortaStore unreachable at %s: %s -- document sync will be skipped",
            self._base_url, exc
        )
```

### Testing Strategy

| Change | Test Approach |
|--------|--------------|
| persist() cleanup | Existing `tests/` persist tests should pass. Add test verifying persist() does NOT call upsert_project. |
| Batch upsert_dev_plan | Mock `execute_batch` on RemoteStorageBackend, verify called with 4 ops. Test fallback path (no execute_batch). |
| Project cache | Unit test: upsert_project then fetch_project returns cached. Test TTL expiry. Test cache invalidation on new upsert. |
| Skip count_entries | Test: docs_were_generated=True -> entry_count=0 without backend call. Test existing path still works. |
| create_storage_backend | Test: settings.mode="client" without explicit mode param -> returns RemoteStorageBackend. |
| CortaStore health probe | Test: unreachable URL -> warning logged, setup() still succeeds. Test: reachable -> no warning. |
<!-- ID: directory_structure -->
## 5. Files Modified (Complete List)

No new files are created. All changes are edits to existing files.

```
src/scribe_mcp/
  state/manager.py                  # Phase 1: persist() cleanup (remove project upsert loop)
  tools/set_project.py              # Phase 2: OPT-1 (batch upsert_dev_plan), OPT-3 (skip count_entries)
  storage/remote.py                 # Phase 2: OPT-2 (project record cache)
  storage/__init__.py               # Phase 3: FIX-1 (mode auto-detection)
  object_store/providers/corta.py   # Phase 3: FIX-2 (health probe)

.env.example                        # Phase 3: FIX-3 (document CLIENT mode config)

tests/
  test_persist_cleanup.py           # Phase 1: verify no project upserts
  test_set_project_batch.py         # Phase 2: verify batch + cache + skip
  test_storage_factory.py           # Phase 3: verify mode auto-detection
  test_corta_health.py              # Phase 3: verify health probe behavior
```
<!-- ID: data_storage -->
## 6. Data and Storage Impact

### No Schema Changes

None of the optimizations require database schema changes. All changes are to application-level code.

### Storage Backend Impact

| Backend | persist() Impact | set_project Impact | CortaStore Impact |
|---------|-----------------|-------------------|-------------------|
| SQLite | Eliminates N*2 thread dispatches per persist() | No change (sequential upsert_dev_plan stays) | No change |
| Postgres | Eliminates N round-trips per persist() | No change | No change |
| Remote (CLIENT) | Already guarded (no change) | 8-9 HTTP -> 2-3 HTTP | Health probe + no wasted PG object |

### Cache Behavior

The new `_project_cache` on RemoteStorageBackend is ephemeral (in-memory only, no persistence). It is automatically populated by `upsert_project()` and consulted by `fetch_project()`. The 10s TTL ensures consistency bounds. Cache entries are never shared between processes.
<!-- ID: testing_strategy -->
## 7. Testing and Validation Strategy

### Test Matrix

| Test | Type | Phase | What It Validates |
|------|------|-------|-------------------|
| persist() no longer calls upsert_project | Unit | 1 | FR-1: Project upserts removed |
| persist() still writes session state | Unit | 1 | FR-2: Session ops preserved |
| persist() cache updates unchanged | Unit | 1 | FR-3: In-memory caches still work |
| execute_batch called with 4 ops | Unit (mock) | 2 | FR-4: Batch upsert_dev_plan |
| Sequential fallback when no execute_batch | Unit (mock) | 2 | FR-4: Backward compatibility |
| fetch_project returns cached after upsert | Unit | 2 | FR-5: Project cache works |
| Cache expires after TTL | Unit | 2 | FR-5: TTL enforcement |
| count_entries skipped for new projects | Unit (mock) | 2 | FR-6: Skip count_entries |
| create_storage_backend returns Remote in client mode | Unit | 3 | FR-7: Mode auto-detection |
| CortaStore setup warns on unreachable | Unit | 3 | FR-8: Health probe non-fatal |
| CortaStore setup succeeds when reachable | Unit | 3 | FR-8: No false warnings |

### Regression Testing

Run the full existing test suite after each phase:
```bash
pytest tests/ -x --timeout=120
```

### Manual Validation

After deployment to Hetzner:
1. Run `set_project` in CLIENT mode -- verify response time < 3s (was ~28s)
2. Check server logs for batch endpoint hits
3. Verify CortaStore health probe message in startup logs
4. Verify no PostgresStorage import warning in CLIENT mode startup
<!-- ID: deployment_operations -->
## 8. Deployment and Operations

### Deployment Sequence

1. **Commit and push** all changes to master
2. **Deploy to Hetzner:**
   ```bash
   ssh council-hub
   cd /opt/council_mcp
   git -C scribe_mcp pull origin master
   docker compose -f council_mcp/deploy/docker-compose.yaml \
     -f scribe_mcp/deploy/docker-compose.scribe.yaml \
     build scribe && \
   docker compose -f council_mcp/deploy/docker-compose.yaml \
     -f scribe_mcp/deploy/docker-compose.scribe.yaml \
     up -d scribe
   curl http://localhost:8200/health
   ```
3. **Restart local MCP** (stdio transport) to pick up code changes
4. **Verify** set_project performance in CLIENT mode

### Rollback

All changes are backward-compatible. If issues arise:
- Revert the commit and redeploy
- The project cache in RemoteStorageBackend is in-memory only -- no persistent state to clean up
- persist() changes affect all backends equally -- revert restores original behavior

### Monitoring

- Check Hetzner server logs for `/api/v1/batch` requests (indicates OPT-1 is working)
- Monitor CortaStore health probe warnings in startup logs
- Compare set_project response times before and after (expect ~90% improvement in CLIENT mode)
<!-- ID: open_questions -->
## 9. Open Questions and Future Work

| Item | Status | Notes |
|------|--------|-------|
| Batch ALL remote operations (BatchContext pattern) | Future | Research doc FIX-8 describes a ctx manager approach. Out of scope for this project but would further reduce append_entry/read_recent calls |
| Single-endpoint set_project_complete | Future | Server-side endpoint that handles upsert_project + upsert_dev_plan atomically. Would reduce to 1 HTTP call total |
| Skip upsert_dev_plan when paths unchanged | Future | Hash check against project_record.docs_json to skip dev_plan writes on re-activation |
| Fire-and-forget upsert_dev_plan | Future | Background asyncio tasks for non-critical path operations |
| append_entry fetch_project redundancy | Future | Same double-fetch pattern exists in append_entry (2-4 HTTP calls). Project cache (OPT-2) partially addresses this |
<!-- ID: references_appendix -->
## 10. References

### Research Documents
- `RESEARCH_SQLITE_PERSIST_OPTIMIZATION.md` -- persist() cost model and optimization strategies
- `RESEARCH_SET_PROJECT_CALL_REDUCTION.md` -- HTTP call inventory and batching design
- `RESEARCH_CORTA_STORE_CLIENT_MODE.md` -- CortaStore integration audit
- `RESEARCH_CLIENT_MODE_BOTTLENECK_AUDIT_20260217.md` -- Broader bottleneck audit (prior project)

### Key Code Locations
- `src/scribe_mcp/state/manager.py:134-185` -- persist() method
- `src/scribe_mcp/tools/set_project.py:452-478` -- upsert_dev_plan loop
- `src/scribe_mcp/tools/set_project.py:614-622` -- count_entries call
- `src/scribe_mcp/storage/remote.py:93-112` -- execute_batch method
- `src/scribe_mcp/storage/__init__.py:13-72` -- create_storage_backend factory
- `src/scribe_mcp/object_store/providers/corta.py:45-49` -- CortaStoreProvider.setup
- `src/scribe_mcp/server_sse.py:61-103` -- OPERATION_ALLOWLIST (includes upsert_dev_plan)
