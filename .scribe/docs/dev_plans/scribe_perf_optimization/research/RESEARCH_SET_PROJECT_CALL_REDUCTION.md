---
id: scribe_perf_optimization-research-set-project-call-reduction
title: "\U0001F52C Research Set Project Call Reduction \u2014 scribe_perf_optimization"
doc_type: RESEARCH_SET_PROJECT_CALL_REDUCTION
doc_name: RESEARCH_SET_PROJECT_CALL_REDUCTION
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 06:04:57 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Set Project Call Reduction — scribe_perf_optimization
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 06:01:11 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Trace every backend.* call in set_project and classify as HTTP vs in-memory
to find deduplication, batching, and elimination opportunities.

**Key Takeaways:**
- The original estimate of "8-14 remote calls" significantly overcounts. Many "backend calls" in
  set_project are SESSION operations that RemoteStorageBackend handles entirely in-memory (no network).
- Actual HTTP calls are **8-9 per set_project invocation** (8 for existing projects, 9 for new ones).
- The biggest batching opportunity is the 4x sequential `upsert_dev_plan` calls (HTTP calls 4-7).
- `count_entries` is only needed for the "readable" format SITREP and can be skipped for new projects.
- `_check_slug_collision` does 1-2 HTTP calls but returns early for existing projects (only 1 call).
- `execute_batch()` API already exists on RemoteStorageBackend and can batch the 4x upsert_dev_plan.
- With OPT-1+2+3+5 applied, set_project drops to 3 HTTP calls: upsert_project (1), upsert_dev_plan batch (1), count_entries (1, skippable).
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-SetProjectCalls

**Investigation Window:** 2026-02-17

**Focus Areas:**
- [x] set_project.py — full execution trace with backend.* call classification
- [x] state/manager.py — StateManager.set_current_project duplicate call analysis
- [x] shared/tool_runtime.py — pre-tool wrapper remote calls
- [x] state/agent_identity.py — update_agent_activity behavior in CLIENT mode
- [x] tools/agent_project_utils.py — ensure_agent_session call chain
- [x] state/agent_manager.py — start_session / set_current_project call chain
- [x] storage/remote.py — definitive classification: HTTP vs in-memory operations

**Dependencies and Constraints:**
- Analysis is specific to RemoteStorageBackend (CLIENT mode). SQLite backend has no HTTP cost.
- The 30-second TTL cache in StateManager._load_projects affects whether list_projects_by_repo
  is an HTTP call or served from cache.
- execute_batch() API is available on RemoteStorageBackend (remote.py:93) but not yet used by set_project.
<!-- ID: findings -->
### Finding 1: Session Operations Are All In-Memory (Zero Network Cost) — CONFIDENCE: HIGH

RemoteStorageBackend handles ALL session operations in local dict caches with zero network overhead.
The class docstring (remote.py:28) states: "Session management stays in-memory locally for
zero-latency middleware operations."

In-memory operations (no HTTP):
- `upsert_session` (remote.py:140)
- `get_session_by_transport` (remote.py:161)
- `set_session_mode` / `get_session_mode` (remote.py:167, 170)
- `set_session_project` / `get_session_project` (remote.py:173, 176)
- `upsert_agent_session` (remote.py:179)
- `set_agent_project` / `get_agent_project` (remote.py:202, 199)
- `get_or_create_agent_session` (remote.py:240)
- `upsert_agent_recent_project` (remote.py:264)
- `update_session_activity` (remote.py:228) — explicit no-op in CLIENT mode

This means set_project.py lines 560-592 (set_session_project, set_session_mode, upsert_session,
upsert_agent_recent_project) are all FREE in CLIENT mode. Evidence: storage/remote.py:136-268.


### Finding 2: Actual HTTP Call Inventory — CONFIDENCE: HIGH (0.9)

8 HTTP calls for existing projects, 9 for new projects:

| Call # | File:Line | Method | Purpose | Scenario | Optimization |
|--------|-----------|--------|---------|----------|-------------|
| 1 | set_project.py:163 | fetch_project(name) | slug collision check | ALL | Eliminate for existing |
| 2 | set_project.py:169 | list_projects() | slug collision scan | NEW only | Scope to repo |
| 3 | set_project.py:417 | upsert_project(...) | create/update record | ALL | NECESSARY |
| 4 | set_project.py:468 | upsert_dev_plan(arch) | persist doc path | ALL | BATCH with 5-7 |
| 5 | set_project.py:468 | upsert_dev_plan(phase) | persist doc path | ALL | BATCH with 4,6,7 |
| 6 | set_project.py:468 | upsert_dev_plan(check) | persist doc path | ALL | BATCH with 4,5,7 |
| 7 | set_project.py:468 | upsert_dev_plan(log) | persist doc path | ALL | BATCH with 4,5,6 |
| 8 | logging_utils.py:143 | fetch_project(name) | context resolution | ALL | Cache upsert result |
| 9 | set_project.py:617 | count_entries(...) | SITREP entry count | readable+existing | Skip for new |


### Finding 3: 4x upsert_dev_plan Sequential HTTP Calls Can Be Batched — CONFIDENCE: HIGH (1.0)

The loop at set_project.py:462-475 makes 4 sequential HTTP calls to upsert_dev_plan. The
execute_batch() method is already implemented on RemoteStorageBackend (remote.py:93-112) and sends
all operations in a single POST to /api/v1/batch. Batching these 4 calls saves approximately
1.2-1.8 seconds (3 round trips * 0.4-0.6s each).


### Finding 4: fetch_project Called Twice for Same Project — CONFIDENCE: HIGH (0.9)

fetch_project(name) is called at set_project.py:163 (in _check_slug_collision) and again at
logging_utils.py:143 (in resolve_logging_context during second prepare_context call). The result
from upsert_project at line 417 is a complete ProjectRecord that should be reused. This double-
fetch wastes 1 HTTP round trip (~0.4-0.5s over Tailscale).


### Finding 5: _check_slug_collision Returns Early for Existing Projects — CONFIDENCE: HIGH (0.95)

For existing projects (the common case), _check_slug_collision at set_project.py:163 calls
fetch_project, gets a non-None result, and returns None immediately without calling list_projects.
This means only 1 HTTP call is wasted for existing projects (not 2). The result from this fetch
is discarded, but it could be reused by the caller to skip the later fetch_project in
logging_utils if the project record was passed through.


### Finding 6: count_entries Is Optional — CONFIDENCE: HIGH (1.0)

count_entries at set_project.py:615-622 is inside `if format == "readable":`. It is never called
for structured/compact format. For new projects (docs_were_generated=True), entry_count is
always 0 and the HTTP call can be skipped entirely (new project has no entries).


### Finding 7: StateManager.set_current_project Duplicate Calls Are Harmless — CONFIDENCE: HIGH (0.95)

StateManager.set_current_project at manager.py:252-257 calls set_session_project and
upsert_agent_recent_project even with skip_upsert=True, duplicating calls already made at
set_project.py:563,592. However ALL these are in-memory in CLIENT mode, so no HTTP cost.
The duplication is harmless but slightly wasteful of CPU.


### Finding 8: tool_runtime Pre-Tool Calls Are All In-Memory — CONFIDENCE: HIGH (1.0)

execute_tool_call in tool_runtime.py makes backend calls before set_project runs:
- get_session_by_transport (line 253) — in-memory dict lookup
- upsert_session (line 309) — in-memory dict update
- get_or_create_agent_session (line 329) — in-memory dict lookup/create
All three are in-memory operations in RemoteStorageBackend with zero HTTP cost.


### Finding 9: update_agent_activity Is Effectively a No-Op in CLIENT Mode — CONFIDENCE: HIGH (0.9)

update_agent_activity at agent_identity.py:284 calls state_manager.persist(). In CLIENT mode,
persist() checks `isinstance(backend, RemoteStorageBackend)` at manager.py:144-146 and SKIPS
the upsert loop entirely, updating only in-memory caches. This means update_agent_activity
has zero remote cost in CLIENT mode.
<!-- ID: technical_analysis -->
### Complete set_project Execution Flow with HTTP Call Classification

```
set_project() entry
|-- state_manager.record_tool()                     [cache: list_projects_by_repo if cold]
|-- update_agent_activity()                         [CLIENT: persist() no-op -> FREE]
|-- prepare_context() #1 (require_project=False)    [state_snapshot provided]
|   `-- resolve_logging_context()
|       `-- get_session_project() -> in-memory -> FREE
|           (no project yet: no fetch_project call)
|-- _ensure_documents()                             [LOCAL filesystem only -> FREE]
|-- _check_slug_collision()
|   |-- backend.fetch_project(name)                 [HTTP CALL #1 - existing: returns early]
|   `-- backend.list_projects() (NEW ONLY)          [HTTP CALL #2 - new projects only]
|-- backend.upsert_project(...)                     [HTTP CALL #3 - ALWAYS REQUIRED]
|-- _PROJECT_REGISTRY.ensure_project()              [local in-memory SQLite -> FREE]
|-- backend.upsert_dev_plan(architecture)           [HTTP CALL #4 - BATCHABLE]
|-- backend.upsert_dev_plan(phase_plan)             [HTTP CALL #5 - BATCHABLE]
|-- backend.upsert_dev_plan(checklist)              [HTTP CALL #6 - BATCHABLE]
|-- backend.upsert_dev_plan(progress_log)           [HTTP CALL #7 - BATCHABLE]
|-- ensure_agent_session()
|   `-- resume_agent_session()
|       `-- agent_manager.start_session()           [upsert_agent_session -> in-memory -> FREE]
|           `-- log_agent_event()                   [direct SQL / no HTTP on remote -> FREE]
|-- agent_manager.set_current_project()
|   |-- storage.get_agent_project()                 [in-memory -> FREE]
|   |-- storage.set_agent_project()                 [in-memory -> FREE]
|   `-- log_agent_event()                           [no HTTP -> FREE]
|-- state_manager.set_current_project(skip_upsert=True)
|   |-- set_session_project()                       [in-memory -> FREE]
|   |-- upsert_agent_recent_project()               [in-memory -> FREE]
|   `-- _set_global_project() -> set_agent_project  [in-memory -> FREE]
|       `-- _load_locked()                          [cache hit within 30s -> likely FREE]
|-- state_manager.set_session_mode()
|   |-- upsert_session()                            [in-memory -> FREE]
|   `-- set_session_mode()                          [in-memory -> FREE]
|-- backend.set_session_project()                   [in-memory -> FREE]
|-- backend.set_session_mode()                      [in-memory -> FREE]
|-- backend.upsert_session()                        [in-memory -> FREE]
|-- backend.upsert_agent_recent_project()           [in-memory -> FREE]
|-- prepare_context() #2 (explicit_project=name)
|   `-- resolve_logging_context()
|       |-- get_session_project() -> in-memory -> FREE
|       `-- backend.fetch_project(name)             [HTTP CALL #8 - REDUNDANT with #1/#3]
`-- backend.count_entries() [readable format only]  [HTTP CALL #9 - SKIPPABLE for new]
```

### HTTP Call Summary

| Scenario | HTTP Calls | Calls |
|----------|-----------|-------|
| Existing project, readable format | 8 | #1,3,4,5,6,7,8,9 |
| New project, readable format | 9 | #1,2,3,4,5,6,7,8,9 |
| Any project, structured/compact format | 7 | #1,3,4,5,6,7,8 |
| Existing, structured/compact (common programmatic use) | 7 | #1,3,4,5,6,7,8 |

### Code Patterns Identified

1. **Batching gap**: execute_batch() exists on RemoteStorageBackend (remote.py:93) but is never
   used by set_project. The 4x upsert_dev_plan loop (set_project.py:462-475) is the obvious target.

2. **Double-fetch pattern**: fetch_project(name) is called at set_project.py:163 AND logging_utils.py:143.
   The result from upsert_project at line 417 (a ProjectRecord) should be cached and reused.

3. **Unnecessary collision check for existing projects**: _check_slug_collision fetches project,
   finds it exists, and discards the result. This 1 HTTP call could be eliminated by caching the
   result from _check_slug_collision and passing it to the caller.

4. **count_entries only needed for existing SITREP**: New projects always have 0 entries.

### Risk Assessment

- [ ] execute_batch() server-side must support upsert_dev_plan — verify /api/v1/batch handler
- [ ] ProjectRecord from upsert must be threaded to logging_utils to avoid second fetch
- [ ] Removing fetch_project in _check_slug_collision must preserve the return-early-if-exists behavior
- [ ] Client-side project cache in RemoteStorageBackend must handle invalidation on upsert
<!-- ID: recommendations -->
### Immediate Next Steps (Priority Order)

**OPT-1 [HIGH PRIORITY]: Batch upsert_dev_plan calls — saves 3 HTTP calls (4->1)**

Location: set_project.py:452-478
Current: 4 sequential await backend.upsert_dev_plan() calls
Fix: Replace loop with execute_batch() using RemoteStorageBackend (remote.py:93-112)

```python
# set_project.py lines 452-478 — replace loop with:
if hasattr(backend, "execute_batch") and project_record:
    ops = []
    for plan_type, path_str in core_docs.items():
        if not path_str:
            continue
        path_obj = Path(path_str)
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
    # Fallback: sequential upserts (existing behavior)
    for plan_type, path_str in core_docs.items():
        ...
```

PREREQUISITE: Verify /api/v1/batch handler on server-side calls upsert_dev_plan correctly.


**OPT-2 [HIGH PRIORITY]: Cache project record to eliminate second fetch_project — saves 1 HTTP call**

The simplest approach: add a short-lived in-process project cache to RemoteStorageBackend.
After upsert_project returns a ProjectRecord, store it in a dict with a 10s TTL.
When fetch_project is called for the same name within TTL, return cached.

```python
# In RemoteStorageBackend (storage/remote.py) after __init__:
self._project_cache: Dict[str, tuple] = {}  # name -> (ProjectRecord, expires_at)

async def upsert_project(self, *, name: str, ...) -> ProjectRecord:
    result = await self._call("upsert_project", ...)
    record = self._to_project_record(result)
    self._project_cache[name] = (record, time.monotonic() + 10.0)  # 10s TTL
    return record

async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
    cached = self._project_cache.get(name)
    if cached:
        record, expires_at = cached
        if time.monotonic() < expires_at:
            return record
    result = await self._call("fetch_project", name=name)
    record = self._to_project_record(result)
    if record:
        self._project_cache[name] = (record, time.monotonic() + 10.0)
    return record
```

This eliminates BOTH the slug collision fetch_project (call #1 for existing) AND the
logging_utils fetch_project (call #8) without any interface changes.


**OPT-3 [MEDIUM PRIORITY]: Skip count_entries for new projects — saves 1 HTTP call**

Location: set_project.py:615-622
Current: Always calls count_entries when format == "readable"
Fix: Skip for new projects (docs_were_generated is True)

```python
# set_project.py lines 615-622:
if backend and project_record:
    if docs_were_generated:
        entry_count = 0  # New project always has 0 entries
    else:
        try:
            entry_count = await backend.count_entries(
                project_record,
                filters={"log_type": ["progress", "bugs", "bug", "security"]},
            )
        except TypeError:
            entry_count = await backend.count_entries(project_record)
```


**OPT-4 [LOW PRIORITY]: Refactor _check_slug_collision to return fetch result — saves 1 HTTP call**

Location: set_project.py:140-194 and caller at set_project.py:411-413
Change _check_slug_collision signature to also return the fetched project record, and use it
directly in the upsert_project call or skip the slug check for already-known existing projects.

Note: With OPT-2 implemented (client-side cache), OPT-4 becomes unnecessary since fetch_project
for the same name will be served from cache (0ms). In that case, OPT-4 can be skipped.


### Estimated Impact After Optimizations

| Applied | HTTP Calls Before | HTTP Calls After | Time Saved (at 0.4s/call) |
|---------|-----------------|-----------------|--------------------------|
| OPT-1 only | 8-9 | 5-6 | ~1.2s |
| OPT-1 + OPT-2 | 8-9 | 3-4 | ~2.0s |
| OPT-1 + OPT-2 + OPT-3 | 8-9 | 2-3 | ~2.4s |
| All opts | 8-9 | 2 | ~2.8s |

Target: 3 HTTP calls (upsert_project + batched upsert_dev_plan + optional count_entries for existing).


### Long-Term Opportunities

1. **Single-endpoint set_project_complete**: Create a server-side endpoint that handles
   upsert_project + upsert_dev_plan(x4) atomically in one HTTP round trip. Reduces to 2 HTTP calls.

2. **Skip upsert_dev_plan entirely on update**: If the project already exists and core doc paths
   haven't changed, upsert_dev_plan calls are no-ops. Add a hash check against project_record.docs_json
   to skip upsert_dev_plan when paths are unchanged.

3. **Fire-and-forget upsert_dev_plan**: These calls are not in the critical path for the tool
   response. They could be dispatched as background asyncio tasks with a 5s deadline.

4. **Batched session + project persistence**: Combine upsert_project + upsert_dev_plan + set_session_project
   into a single batch call via execute_batch for the minimal set of necessary operations.
<!-- ID: appendix -->
**Files Analyzed:**
- `src/scribe_mcp/tools/set_project.py` (1024 lines) — main tool implementation
- `src/scribe_mcp/state/manager.py` (666 lines) — StateManager with TTL cache
- `src/scribe_mcp/storage/remote.py` (641 lines) — RemoteStorageBackend (definitive HTTP vs in-memory map)
- `src/scribe_mcp/shared/tool_runtime.py` (378 lines) — pre-tool wrapper dispatch
- `src/scribe_mcp/state/agent_identity.py` (305 lines) — AgentIdentity with batched persist
- `src/scribe_mcp/tools/agent_project_utils.py` (192 lines) — ensure_agent_session chain
- `src/scribe_mcp/state/agent_manager.py` (590 lines) — AgentContextManager
- `src/scribe_mcp/shared/base_logging_tool.py` (139 lines) — LoggingToolMixin.prepare_context
- `src/scribe_mcp/shared/logging_utils.py` (783 lines) — resolve_logging_context with fetch_project

**Key Code References:**
- Remote HTTP dispatch: `remote.py:69-91` (_call method — all HTTP calls go through here)
- Batch endpoint: `remote.py:93-112` (execute_batch — READY TO USE for upsert_dev_plan)
- In-memory session tier: `remote.py:136-268` (all session operations, zero HTTP)
- Slug collision check: `set_project.py:140-194` (_check_slug_collision)
- upsert_dev_plan loop: `set_project.py:452-478` (4x HTTP, primary batching target)
- Context fetch_project: `logging_utils.py:118-146` (resolve_logging_context call chain)
- count_entries for SITREP: `set_project.py:609-622` (skippable for new projects)
- StateManager TTL cache: `manager.py:378-428` (_load_projects with 30s cache)
- persist() CLIENT mode skip: `manager.py:134-186` (no-op for RemoteStorageBackend)
