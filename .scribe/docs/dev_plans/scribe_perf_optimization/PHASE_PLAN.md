---
id: scribe_perf_optimization-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_perf_optimization"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 06:15:19 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — scribe_perf_optimization
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-17 05:57:35 UTC

> Execution roadmap for scribe_perf_optimization.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview

| Phase | Goal | Key Deliverables | Est. Effort | Confidence |
|-------|------|------------------|-------------|------------|
| Phase 1 -- persist() Cleanup (Track B) | Eliminate redundant project upserts from persist() | Cleaned persist() method, regression tests | 1-2 hours | 0.95 |
| Phase 2 -- set_project Call Reduction (Track A) | Reduce CLIENT mode HTTP calls from 8-9 to 2-3 | Batch upsert, project cache, count_entries skip | 2-3 hours | 0.90 |
| Phase 3 -- CortaStore Fixes (Track C) | Fix minor CLIENT mode issues | Mode auto-detection, health probe, .env docs | 1 hour | 0.95 |
| Phase 4 -- Deploy and Verify | Push to Hetzner and validate | Deployed server, verified timing | 30 min | 0.95 |

**Total estimated effort: 5-7 hours**
**Expected outcome: set_project CLIENT mode from ~28s to ~1-3s (90%+ improvement)**
<!-- ID: phase_0 -->
---
## Phase 1 -- persist() Cleanup (Track B)
<!-- ID: phase_1_persist -->

**Objective:** Remove redundant project upsert loop from `StateManager.persist()` for all backends.

**Why first:** Highest universal impact (affects SQLite, Postgres, and Remote). Simplest change. No dependencies. Eliminates the single biggest bottleneck (43 upserts per persist call).

### Task Package 1.1: Remove Project Upsert Loop from persist()

**Scope:** Remove the `for project_name, payload in state.projects.items():` loop and the `_upsert_project()` call within the session_projects loop.
**Files to Modify:** `src/scribe_mcp/state/manager.py` (lines 134-185 only)
**Dependencies:** None

**Specifications:**
1. Delete lines 151-152 (the project upsert loop):
   ```python
   for project_name, payload in state.projects.items():
       await self._upsert_project(project_name, payload)
   ```
2. Delete line 164 (the session_projects _upsert_project call):
   ```python
   await self._upsert_project(project_name, project_payload)
   ```
3. Keep the `isinstance(RemoteStorageBackend)` guard (lines 144-146) but now it only protects `_ensure_backend_ready`, `_run_legacy_migration_once`, and `_set_global_project`
4. Keep ALL session operations (`set_session_project`, `upsert_session`, `set_session_mode`) -- these ARE needed
5. Keep ALL in-memory cache updates (lines 176-185) -- these ARE needed
6. Update the persist() docstring to document why project upserts are not needed

**Verification:**
- [ ] `pytest tests/ -x --timeout=120` -- all existing tests pass
- [ ] Manually invoke `set_project` -- no regression in behavior
- [ ] Add test: mock `_upsert_project`, call `persist()`, assert `_upsert_project` was NOT called

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify `_upsert_project()` method itself (it is still used by `set_current_project`)
- Do NOT modify any other method in manager.py
- Do NOT modify `agent_identity.py` or `delete_project.py`
- Do NOT remove `_mirror_session_to_json_state` (already a no-op, leave it)

### Task Package 1.2: Add Regression Test for persist()

**Scope:** Add a unit test ensuring persist() does not call upsert_project
**Files to Modify:** Create `tests/test_persist_cleanup.py`
**Dependencies:** Task 1.1

**Specifications:**
1. Create test file `tests/test_persist_cleanup.py`
2. Test `test_persist_does_not_upsert_projects`:
   - Create a mock StorageBackend
   - Create a StateManager with the mock backend
   - Call `persist(state)` with a state containing 5+ projects
   - Assert `upsert_project` was NOT called on the mock
   - Assert `set_session_project` WAS called for session entries
3. Test `test_persist_updates_in_memory_caches`:
   - Call `persist(state)` with known agent_state
   - Assert `_agent_state_cache` was updated

**Verification:**
- [ ] `pytest tests/test_persist_cleanup.py -v` passes
- [ ] Tests validate both the removal (no upsert) and the preservation (session ops + caches)

**Out of Scope:**
- Do NOT test RemoteStorageBackend behavior (that is unchanged)
- Do NOT write integration tests (unit tests with mocks are sufficient)
<!-- ID: phase_1 -->
---
## Phase 2 -- set_project Call Reduction (Track A)
<!-- ID: phase_2_set_project -->

**Objective:** Reduce CLIENT mode HTTP calls in set_project from 8-9 to 2-3.

**Dependencies:** Phase 1 must be complete (persist cleanup simplifies the code path).

### Task Package 2.1: Batch upsert_dev_plan via execute_batch (OPT-1)

**Scope:** Replace sequential upsert_dev_plan loop with batched execute_batch call
**Files to Modify:** `src/scribe_mcp/tools/set_project.py` (lines 452-478 only)
**Dependencies:** None (execute_batch and OPERATION_ALLOWLIST already support upsert_dev_plan)

**Specifications:**
1. At line 462, BEFORE the existing `for plan_type, path_str in core_docs.items():` loop, add a branch:
   ```python
   if hasattr(backend, "execute_batch"):
       # Build batch operations list
       ops = []
       for plan_type, path_str in core_docs.items():
           if not path_str:
               continue
           path_obj = _Path(path_str)
           if not path_obj.exists():
               continue
           ops.append({"op": "upsert_dev_plan", "args": {
               "project_id": project_record.id,
               "project_name": name,
               "plan_type": plan_type,
               "file_path": str(path_obj),
               "version": "1.0",
               "metadata": {"source": "set_project"},
           }})
       if ops:
           await backend.execute_batch(ops)
   else:
       # Keep existing sequential loop as fallback
       ...
   ```
2. The existing sequential loop becomes the `else` branch (SQLite/Postgres fallback)
3. Wrap the entire batch attempt in the existing try/except (line 476)

**Verification:**
- [ ] `pytest tests/ -x` -- no regression
- [ ] In CLIENT mode: verify only 1 HTTP call to /api/v1/batch instead of 4 individual calls
- [ ] Verify SQLite mode still works (sequential fallback path)

**Out of Scope:**
- Do NOT modify `execute_batch()` on RemoteStorageBackend
- Do NOT modify server_sse.py or OPERATION_ALLOWLIST
- Do NOT change any other part of set_project.py

### Task Package 2.2: Add Project Record Cache to RemoteStorageBackend (OPT-2)

**Scope:** Add TTL-based project cache to eliminate redundant fetch_project HTTP calls
**Files to Modify:** `src/scribe_mcp/storage/remote.py`
**Dependencies:** None

**Specifications:**
1. Add to `__init__()`:
   ```python
   import time as _time
   self._project_cache: dict[str, tuple] = {}  # name -> (ProjectRecord, expires_at)
   ```
2. In `upsert_project()` (after `_to_project_record`), cache the result:
   ```python
   if record:
       self._project_cache[name] = (record, _time.monotonic() + 10.0)
   ```
3. In `fetch_project()`, check cache before HTTP call:
   ```python
   cached = self._project_cache.get(name)
   if cached:
       record, expires_at = cached
       if _time.monotonic() < expires_at:
           return record
       del self._project_cache[name]
   # ... existing HTTP call ...
   # After _to_project_record, also cache the result
   if record:
       self._project_cache[name] = (record, _time.monotonic() + 10.0)
   ```

**Verification:**
- [ ] Unit test: call `upsert_project`, then `fetch_project` same name -- no HTTP call on second
- [ ] Unit test: wait 11s, call `fetch_project` -- triggers HTTP call (TTL expired)
- [ ] `pytest tests/ -x` -- no regression

**Out of Scope:**
- Do NOT add cache to any other method (list_projects, delete_project, etc.)
- Do NOT add cache invalidation beyond TTL (keep it simple)
- Do NOT modify any callers of fetch_project

### Task Package 2.3: Skip count_entries for New Projects (OPT-3)

**Scope:** Avoid HTTP call to count_entries when project was just created
**Files to Modify:** `src/scribe_mcp/tools/set_project.py` (lines 608-631)
**Dependencies:** None

**Specifications:**
1. `docs_were_generated` is currently computed at line 630 (AFTER count_entries). Move this computation BEFORE the count_entries block:
   ```python
   # Move this line to BEFORE the count_entries call
   docs_were_generated = bool(doc_result.get("generated") or doc_result.get("files"))
   ```
2. Add conditional skip:
   ```python
   if backend and project_record:
       if docs_were_generated:
           entry_count = 0  # New project: guaranteed 0 entries
       else:
           try:
               entry_count = await backend.count_entries(
                   project_record,
                   filters={"log_type": ["progress", "bugs", "bug", "security"]},
               )
           except TypeError:
               entry_count = await backend.count_entries(project_record)
   ```

**Verification:**
- [ ] `pytest tests/ -x` -- no regression
- [ ] New project in CLIENT mode: verify count_entries HTTP call is NOT made
- [ ] Existing project: verify count_entries still works

**Out of Scope:**
- Do NOT change count_entries for non-readable formats (already skipped)
- Do NOT modify the count_entries method itself
<!-- ID: milestone_tracking -->
---
## Phase 3 -- CortaStore Fixes (Track C)
<!-- ID: phase_3_corta -->

**Objective:** Fix minor CLIENT mode issues: wasteful PG object creation, missing health probe.

**Dependencies:** None (independent of Phases 1-2).

### Task Package 3.1: Fix create_storage_backend Mode Auto-Detection (FIX-1)

**Scope:** Make create_storage_backend() check settings.mode when no explicit mode is passed
**Files to Modify:** `src/scribe_mcp/storage/__init__.py` (lines 13-39 only)
**Dependencies:** None

**Specifications:**
1. After `from scribe_mcp.config.settings import settings` (line 26), add:
   ```python
   # Auto-detect CLIENT mode from settings when not explicitly provided
   if mode is None and getattr(settings, "mode", None) == "client":
       from scribe_mcp.config.mode_detection import OperatingMode
       mode = OperatingMode.CLIENT
   ```
2. This ensures the module-level call at server.py:117 (which passes no mode) creates RemoteStorageBackend when SCRIBE_MODE=client

**Verification:**
- [ ] Unit test: settings.mode="client" + no explicit mode -> returns RemoteStorageBackend
- [ ] Unit test: settings.mode="standalone" + no mode -> returns SQLiteStorage (no regression)
- [ ] `pytest tests/ -x` -- no regression

**Out of Scope:**
- Do NOT modify server.py line 117 (the module-level call stays as-is)
- Do NOT change behavior when mode is explicitly passed

### Task Package 3.2: Add CortaStore Health Probe (FIX-2)

**Scope:** Add non-fatal connectivity check to CortaStoreProvider.setup()
**Files to Modify:** `src/scribe_mcp/object_store/providers/corta.py` (lines 45-49 only)
**Dependencies:** None

**Specifications:**
1. After creating httpx client (line 49), add health probe:
   ```python
   # Non-fatal connectivity probe
   try:
       resp = await self._client.get("/health", timeout=2.0)
       if resp.status_code != 200:
           logger.warning("CortaStore health check returned %d at %s", resp.status_code, self._base_url)
   except Exception as exc:
       logger.warning("CortaStore unreachable at %s: %s -- sync will be skipped", self._base_url, exc)
   ```
2. Import logger at module level if not already present
3. Do NOT make this a hard failure -- setup() must always succeed

**Verification:**
- [ ] Unit test: mock httpx to return connection error -> setup() succeeds, warning logged
- [ ] Unit test: mock httpx to return 200 -> setup() succeeds, no warning
- [ ] `pytest tests/ -x` -- no regression

**Out of Scope:**
- Do NOT add health probes to HybridStore or FilesystemStore
- Do NOT change retry behavior in CortaStoreProvider

### Task Package 3.3: Update .env.example Documentation (FIX-3)

**Scope:** Add comments to .env.example about CLIENT mode configuration
**Files to Modify:** `.env.example`
**Dependencies:** None

**Specifications:**
1. Add comments explaining SCRIBE_DB_URL is not needed in CLIENT mode
2. Add recommended minimal CLIENT mode config section

**Verification:**
- [ ] .env.example has clear CLIENT mode documentation

**Out of Scope:**
- Do NOT modify the actual .env file

---
## Phase 4 -- Deploy and Verify
<!-- ID: phase_4_deploy -->

**Objective:** Deploy all changes to Hetzner and verify performance improvement.

### Task Package 4.1: Deploy to Hetzner

**Scope:** Push code, rebuild Docker image, restart service
**Dependencies:** Phases 1-3 complete and tests passing

**Specifications:**
1. Commit all changes with descriptive message
2. Push to master
3. SSH to council-hub, pull, rebuild, restart scribe service
4. Run `curl http://localhost:8200/health` to verify

### Task Package 4.2: Verify Performance

**Scope:** Measure set_project timing in CLIENT mode before and after
**Dependencies:** Task 4.1

**Specifications:**
1. Restart local MCP (stdio) to pick up code changes
2. Run `set_project` with an existing project -- measure response time
3. Verify < 3 seconds (was ~28 seconds)
4. Check server logs for /api/v1/batch endpoint hits
5. Check startup logs for CortaStore health probe

---
## Milestone Tracking

| Milestone | Target | Status | Evidence |
|-----------|--------|--------|----------|
| Phase 1: persist() cleanup | 2026-02-17 | Planned | PROGRESS_LOG.md |
| Phase 2: set_project optimization | 2026-02-17 | Planned | PROGRESS_LOG.md |
| Phase 3: CortaStore fixes | 2026-02-17 | Planned | PROGRESS_LOG.md |
| Phase 4: Deploy + verify | 2026-02-17 | Planned | Server logs |
<!-- ID: retro_notes -->
## Retro Notes and Adjustments

- Architecture designed on 2026-02-17 based on 3 dedicated research docs + 1 prior bottleneck audit
- All code references verified against actual codebase -- zero discrepancies found
- persist() cleanup (Phase 1) was prioritized over set_project call reduction (Phase 2) because it affects ALL backends, not just CLIENT mode
- OPT-4 (refactor _check_slug_collision) was deliberately excluded because OPT-2 (project cache) makes it redundant
- The isinstance(RemoteStorageBackend) guard in persist() will be kept (not removed) because _ensure_backend_ready and _set_global_project still need it
