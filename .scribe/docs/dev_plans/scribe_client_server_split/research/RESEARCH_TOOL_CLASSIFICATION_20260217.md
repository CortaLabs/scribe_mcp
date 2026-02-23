---
id: scribe_client_server_split-research-tool-classification-20260217
title: "\U0001F52C Research Tool Classification 20260217 \u2014 scribe_client_server_split"
doc_type: RESEARCH_TOOL_CLASSIFICATION_20260217
doc_name: RESEARCH_TOOL_CLASSIFICATION_20260217
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 02:19:27 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Tool Classification 20260217 — scribe_client_server_split
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 02:15:33 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Research Goal:** Classify all 21 Scribe MCP tools by I/O characteristics to inform the client/server split architecture. The split aims to put a lightweight local client (stdio) on the developer machine and a heavy Hetzner server with local Postgres access.

**Primary Objective:** Determine which tool operations can run locally (filesystem I/O) vs. which require the remote server (DB access), and identify HYBRID tools needing request decomposition.

**Key Takeaways:**

- **4 tools are LOCAL-ONLY**: `read_file`, `search`, `edit_file`, `scribe_doctor`. These can run entirely on the local client with no network roundtrips.
- **3 tools are REMOTE-ONLY**: `list_projects`, `read_recent`, `query_entries`. Pure DB reads - should proxy to server.
- **14 tools are HYBRID** (filesystem + DB): `append_entry`, `set_project`, `manage_docs`, `generate_doc_templates`, `rotate_log`, `delete_project`, `get_project`, `configure_reminders`, `query_reminders`, `reset_reminders`, `open_bug`, `open_security`, `append_event`, `link_fix`.
- **Critical architectural insight**: `append_entry` writes to filesystem FIRST (primary), DB is a secondary mirror. The file write never blocks on DB. This is a split-friendly design.
- **set_project is the worst offender**: 15+ sequential DB roundtrips on every call, creating 3+ minute latency over Tailscale. This is the primary motivation for the client/server split.
- **Confidence: 0.93** (high - based on direct code inspection of all 21 tools)
<!-- ID: research_scope -->
**Research Lead:** ResearchAnalyst-ToolClassification

**Investigation Window:** 2026-02-17

**Focus Areas:**
- [x] Complete tool inventory from `src/scribe_mcp/tools/__init__.py`
- [x] I/O classification: LOCAL-ONLY, REMOTE-ONLY, HYBRID
- [x] DB roundtrip counting per tool
- [x] `set_project` deep-dive: full DB operation sequence
- [x] `append_entry` DB mirror pattern analysis
- [x] `state_manager` call analysis (in-memory vs DB-backed)

**Files Investigated:**
- `src/scribe_mcp/tools/__init__.py` - canonical tool registry (21 tools)
- `src/scribe_mcp/tools/set_project.py` (1023 lines)
- `src/scribe_mcp/tools/append_entry.py` (2200 lines)
- `src/scribe_mcp/tools/read_file.py` (2572 lines)
- `src/scribe_mcp/tools/search.py`
- `src/scribe_mcp/tools/edit_file.py`
- `src/scribe_mcp/tools/list_projects.py`
- `src/scribe_mcp/tools/get_project.py`
- `src/scribe_mcp/tools/read_recent.py`
- `src/scribe_mcp/tools/query_entries.py`
- `src/scribe_mcp/tools/manage_docs.py`
- `src/scribe_mcp/tools/generate_doc_templates.py`
- `src/scribe_mcp/tools/rotate_log.py` (2130 lines)
- `src/scribe_mcp/tools/reminder_tools.py`
- `src/scribe_mcp/tools/sentinel_tools.py` (710 lines)
- `src/scribe_mcp/tools/doctor.py` (113 lines)
- `src/scribe_mcp/tools/delete_project.py`
- `src/scribe_mcp/state/manager.py` - StateManager DB backing analysis

**Dependencies and Constraints:**
- StateManager (`state_manager.record_tool()`) makes DB calls via `storage_backend.update_session_activity()` - every tool that calls `record_tool()` has at least 1 DB roundtrip before doing any real work.
- The `storage_backend` is the same Postgres instance that causes the Tailscale latency problem.
- Local filesystem is `/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/` directory tree.
<!-- ID: findings -->
### Finding 1: Complete Tool Inventory (21 Tools)

The canonical tool registry is `src/scribe_mcp/tools/__init__.py` in `_TOOL_NAME_TO_MODULE`. All 21 tools:

`append_entry`, `append_event`, `configure_reminders`, `delete_project`, `edit_file`, `generate_doc_templates`, `get_project`, `link_fix`, `list_projects`, `manage_docs`, `open_bug`, `open_security`, `query_entries`, `query_reminders`, `read_file`, `read_recent`, `reset_reminders`, `rotate_log`, `scribe_doctor`, `search`, `set_project`

**Evidence:** `src/scribe_mcp/tools/__init__.py:34-56` (`_TOOL_NAME_TO_MODULE` dict)
**Confidence:** 1.0

---

### Finding 2: Full Classification Table

| Tool | Category | DB Roundtrips | Filesystem Ops | Notes |
|------|----------|---------------|----------------|-------|
| `read_file` | LOCAL-ONLY | 0 | Read any file within repo boundary | No backend calls whatsoever |
| `search` | LOCAL-ONLY | 0 | ripgrep-equivalent directory scan | No backend calls |
| `edit_file` | LOCAL-ONLY | 0 | Read + atomic write | Requires prior read_file call |
| `scribe_doctor` | LOCAL-ONLY | 0 | Reads env/config files only | Returns env diagnostics dict |
| `list_projects` | REMOTE-ONLY | 2-N+2 | None | 1x list_projects + 1x count_entries per project |
| `read_recent` | REMOTE-ONLY | 3 | None | fetch_project + fetch_recent_entries_paginated + count_entries |
| `query_entries` | REMOTE-ONLY | 2 | None | fetch_project + query_entries_paginated |
| `append_entry` | HYBRID | 1-3 | Write primary log .md file | File is PRIMARY; DB is secondary mirror (best-effort). DB: record_tool(1) + fetch_project(1) + insert_entry(1) |
| `set_project` | HYBRID | 15-17 | mkdir + write 4 .md doc files | Worst offender - see Finding 3 |
| `get_project` | HYBRID | 2-3 | Read .md files for doc inventory | record_tool(1) + fetch_project(1) + fetch_recent_entries(1) |
| `manage_docs` | HYBRID | 1-3 | Read+write .md files (primary) | record_tool(1) + delegates to append_entry for doc updates |
| `generate_doc_templates` | HYBRID | 1 | Write template .md files | record_tool(1) only DB call; file writes are primary |
| `rotate_log` | HYBRID | 1 | Read log .md + write archive .md | record_tool(1) only; state_manager stats are in-memory after initial load |
| `delete_project` | HYBRID | 3 | Delete .md files, dirs | record_tool(1) + fetch_project(1) + delete_project(1) |
| `configure_reminders` | HYBRID | 1 | Reads reminder config files | record_tool(1) + update_project_metadata(1) in state_manager |
| `query_reminders` | HYBRID | 1 | Reads reminder log files | record_tool(1) only |
| `reset_reminders` | HYBRID | 1 | Writes reminder cooldown files | record_tool(1) only |
| `open_bug` | HYBRID | 2-4 | Writes bug report .md file | Delegates to append_entry + manage_docs |
| `open_security` | HYBRID | 2-4 | Writes security report .md file | Delegates to append_entry + manage_docs |
| `append_event` | HYBRID | 1-3 | Writes to sentinel JSONL + .md | In project mode: delegates to append_entry (1-3 DB); in sentinel mode: local file only |
| `link_fix` | HYBRID | 1-3 | Updates bug/security .md file | Delegates to append_entry |

**Evidence:** Direct code inspection of all tool files, grep for `await backend.` and `state_manager.` patterns
**Confidence:** 0.92

---

### Finding 3: state_manager.record_tool() is a DB Write

Almost every tool calls `state_manager.record_tool(tool_name)` as its first operation. This is NOT in-memory caching - it makes an actual DB call:

**Code path** (`src/scribe_mcp/state/manager.py:175-190`):
```python
async def record_tool(self, tool_name: str) -> State:
    async with self._lock:
        await self._ensure_backend_ready()
        session_id = self._resolve_session_id_from_context()
        if session_id and hasattr(self._storage_backend, "update_session_activity"):
            await self._storage_backend.update_session_activity(
                session_id=session_id,
                tool_name=tool_name,
                ...
            )
```

**Impact:** Even "lightweight" tools like `rotate_log` and `generate_doc_templates` make 1 DB write before doing any real work.

**Evidence:** `src/scribe_mcp/state/manager.py:175-190`
**Confidence:** 0.97

---

### Finding 4: append_entry DB Mirror Pattern (Split-Friendly Architecture)

`append_entry` has an architecturally important property: the filesystem write is the PRIMARY path, and DB insertion is a SECONDARY mirror operation. The DB insert failure never blocks the log write.

**Code path** (`src/scribe_mcp/tools/append_entry.py:636-680`):
```python
# Mirror entry into database-backed storage when available, without
# impacting the primary file append path.
backend = server_module.storage_backend
if backend:
    try:
        record = await backend.fetch_project(project["name"])  # DB read
        if not record:
            record = await backend.upsert_project(...)          # DB write (conditional)
        await backend.insert_entry(...)                         # DB write
        db_mirror["status"] = "ok"
    except Exception as db_exc:
        # Database mirror failures should never block logging.
        db_mirror["status"] = "error"
        logger.warning("append_entry database mirror failed: %s", db_exc)
```

**Key insight:** In a local client architecture, `append_entry` can write to the local filesystem immediately (sub-millisecond), then asynchronously send the entry to the Hetzner server for DB mirroring. This makes `append_entry` the most viable tool for async/fire-and-forget remote calls.

**Evidence:** `src/scribe_mcp/tools/append_entry.py:635-680`
**Confidence:** 1.0
<!-- ID: technical_analysis -->
### set_project Deep Dive: Complete DB Operation Sequence

`set_project` (`src/scribe_mcp/tools/set_project.py`, 1023 lines) makes the following sequential DB calls:

**Phase 1: State Initialization (3 DB calls)**
1. `state_manager.record_tool("set_project")` -> `backend.update_session_activity()` (DB write)
2. `agent_identity.update_agent_activity()` (DB write - agent activity table)
3. `_SET_PROJECT_HELPER.prepare_context()` -> `state_manager.load()` -> `backend.list_projects_by_repo()` or `backend.get_session_project()` (1-2 DB reads)

**Phase 2: Slug Collision Check (2 DB calls)**
4. `backend.fetch_project(name)` - Check if exact name exists (DB read)
5. `backend.list_projects()` - Query all projects for slug collisions (DB read)

**Phase 3: Project Upsert + Dev Plans (5 DB calls)**
6. `backend.upsert_project(name, repo_root, progress_log_path, docs_json, ...)` (DB write)
7. `backend.upsert_dev_plan(project_id, "architecture", ...)` (DB write)
8. `backend.upsert_dev_plan(project_id, "phase_plan", ...)` (DB write)
9. `backend.upsert_dev_plan(project_id, "checklist", ...)` (DB write)
10. `backend.upsert_dev_plan(project_id, "progress_log", ...)` (DB write)

**Phase 4: Agent Context Management (3-4 DB calls)**
11. `agent_manager.ensure_agent_session()` or `agent_manager.start_session()` (DB write)
12. `agent_manager.set_current_project()` (DB write with OCC version check)
13. `state_manager.set_current_project()` -> `backend.set_session_project()` + `backend.upsert_agent_recent_project()` (2 DB writes)

**Phase 5: Session Binding (3 DB calls)**
14. `backend.set_session_project(session_key, name)` (DB write)
15. `backend.set_session_mode(session_key, "project")` (DB write)
16. `backend.upsert_session(session_id, ...)` (DB write)

**Phase 6: Agent Tracking + Entry Count (2 DB calls)**
17. `backend.upsert_agent_recent_project(agent_id, name)` (DB write)
18. `backend.count_entries(project_record, ...)` (DB read - for readable format only)

**Total: ~17-18 sequential DB roundtrips** (15 guaranteed + 1-3 conditional)

**Filesystem operations in set_project:**
- `resolved_root.mkdir(parents=True, exist_ok=True)` - create project root
- `_ensure_documents()` - writes up to 4 .md files: ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md, PROGRESS_LOG.md

---

### Code Patterns Identified

**Pattern 1: Backend Proxy Pattern**
All tools access the DB backend via `server_module.storage_backend`. In a client/server split, `server_module` would become the proxy layer. Tools don't import backend directly.

**Pattern 2: N+1 Query Problem in list_projects**
`list_projects` calls `backend.count_entries(name)` for EACH project in a loop (lines 344-355). With 50 projects, this is 51 DB roundtrips (1 list + 50 count calls).

**Pattern 3: Conditional DB Writes**
In `append_entry`, `backend.upsert_project()` is called conditionally only if `fetch_project()` returns None. On warm paths (project already exists), this reduces to 2 DB calls (fetch + insert_entry).

**Pattern 4: State Manager Dual Mode**
`StateManager` has two modes:
- DB-backed: When `_storage_backend` is Postgres (production)
- File-backed: Falls back to local SQLite at `settings.sqlite_path`
The local client architecture could use StateManager with local SQLite, eliminating state_manager DB roundtrips for local operations.

---

### System Interactions

```
Tool Call Flow (Current - Problematic):
  Local stdio client
     |
     v (every call)
  Tool code (server_module)
     |
     v (17+ sequential roundtrips for set_project)
  PostgreSQL @ Hetzner (over Tailscale ~150ms per roundtrip)
  = 17 x 150ms = 2550ms minimum for set_project

Tool Call Flow (Proposed Split):
  Local stdio client (lightweight)
     |
     +---> [LOCAL-ONLY tools] -> local filesystem (0ms)
     |
     +---> [HYBRID tools - file part] -> local filesystem (0ms)
     |         |
     |         v (async, non-blocking)
     +---> [HYBRID tools - DB part] -> HTTP to Hetzner server (1 roundtrip per tool)
     |
     +---> [REMOTE-ONLY tools] -> HTTP to Hetzner server (1 roundtrip)
     |
  PostgreSQL @ Hetzner (local, <5ms)
```

---

### Risk Assessment

- **RISK-001 HIGH**: `set_project` cannot be cleanly split without significant refactoring. The filesystem ops (write .md files) and DB ops (17 calls) are deeply interleaved in a single function.
- **RISK-002 MEDIUM**: `state_manager.record_tool()` as mandatory first operation for most tools adds 1 DB call overhead that cannot be avoided without refactoring all tools.
- **RISK-003 MEDIUM**: `list_projects` N+1 query problem will be expensive even on Hetzner-local DB if not batched.
- **RISK-004 LOW**: `append_entry` bulk mode (items=[...]) loops over entries calling `backend.insert_entry()` per entry (line 2111). Batch insert would reduce roundtrips significantly.
- **RISK-005 LOW**: The `query_entries` cross-project search (`search_scope="all_projects"`) loads multiple project backends sequentially.
<!-- ID: recommendations -->
### Immediate Next Steps for Architect

1. **Design the proxy layer**: The `server_module.storage_backend` reference in every tool is the integration point. A proxy storage backend that routes DB calls to the Hetzner HTTP server would require minimal tool code changes.

2. **Prioritize set_project refactoring**: The 17-18 DB roundtrips in `set_project` must be collapsed to a single HTTP call. Options:
   - **Option A**: Batch all DB operations into a single `set_project` RPC on the Hetzner server
   - **Option B**: Parallelize independent DB calls (upsert_dev_plan x4 can be parallel, not sequential)
   - **Option C**: Make filesystem ops local, make all DB ops async/fire-and-forget (accept eventual consistency)

3. **Use append_entry's existing fire-and-forget pattern**: The "file first, DB mirror second" pattern in `append_entry` is already architecturally correct for a local client. The local client writes the .md file, queues the DB mirror to send to Hetzner server asynchronously.

4. **Eliminate record_tool() for LOCAL-ONLY tools**: `read_file`, `search`, `edit_file`, `scribe_doctor` don't call `record_tool()` at all - they're already clean local operations.

5. **Consider removing state_manager.record_tool() overhead**: For the client/server split, session activity tracking via `update_session_activity()` is a server-side concern. The local client should skip this call entirely or make it async.

### Long-Term Opportunities

- **Batch API for set_project**: Replace 17 sequential DB calls with 1 batch RPC: `{ action: "set_project", name: "...", root: "...", agent: "..." }` -> server handles all DB ops atomically
- **Local StateManager with SQLite**: Run `StateManager` with local SQLite for session state (`record_tool` etc.) and proxy only project/entry operations to Hetzner
- **Async DB mirroring bus**: A local queue that batches `append_entry` DB inserts and sends them to Hetzner server in bulk, reducing per-entry network overhead
- **Fix list_projects N+1**: Add a batch `count_entries_all_projects()` backend method returning a dict of project_name -> count in one query
- **Parallelize upsert_dev_plan**: The 4 sequential `upsert_dev_plan` calls in `set_project` are independent and could be `asyncio.gather()`'d to run in parallel
<!-- ID: appendix -->
### Key Code References

| File | Lines | Relevance |
|------|-------|-----------|
| `src/scribe_mcp/tools/__init__.py` | 34-56 | Canonical tool registry (`_TOOL_NAME_TO_MODULE`) |
| `src/scribe_mcp/tools/set_project.py` | 407-620 | Full DB operation sequence with `_mark()` timing |
| `src/scribe_mcp/tools/append_entry.py` | 635-680 | DB mirror pattern (file-first, DB-second) |
| `src/scribe_mcp/tools/append_entry.py` | 2108-2115 | Bulk mode per-entry DB insert loop |
| `src/scribe_mcp/state/manager.py` | 175-190 | `record_tool()` DB write mechanism |
| `src/scribe_mcp/state/manager.py` | 380-400 | `list_projects()` DB calls in state load |
| `src/scribe_mcp/tools/list_projects.py` | 269-355 | N+1 query: count_entries per project |
| `src/scribe_mcp/tools/sentinel_tools.py` | 175-293 | `append_event` dual-mode (project vs sentinel) |
| `src/scribe_mcp/tools/doctor.py` | 31-99 | `scribe_doctor` - pure LOCAL-ONLY tool |

### DB Roundtrip Summary by Tool (Sorted by Impact)

```
Tool                | DB Roundtrips | Impact Priority
--------------------|---------------|----------------
set_project         | 17-18         | CRITICAL
list_projects       | 2 + N         | HIGH (N+1 problem)
configure_reminders | 2             | MEDIUM
read_recent         | 3             | MEDIUM
get_project         | 2-3           | MEDIUM
open_bug            | 4-6           | MEDIUM
open_security       | 4-6           | MEDIUM
append_entry        | 1-3           | LOW (fire-and-forget)
delete_project      | 3             | LOW
query_entries       | 2             | LOW
append_event        | 0-3           | LOW (mode-dependent)
link_fix            | 1-3           | LOW
manage_docs         | 1-3           | LOW
rotate_log          | 1             | MINIMAL
generate_doc_tmpl   | 1             | MINIMAL
query_reminders     | 1             | MINIMAL
reset_reminders     | 1             | MINIMAL
read_file           | 0             | NONE (LOCAL-ONLY)
search              | 0             | NONE (LOCAL-ONLY)
edit_file           | 0             | NONE (LOCAL-ONLY)
scribe_doctor       | 0             | NONE (LOCAL-ONLY)
```

### Confidence Scores

- Tool inventory (21 tools): 1.0 - verified from source
- Classification (LOCAL/REMOTE/HYBRID): 0.92 - based on await backend.* and state_manager.* grep
- set_project roundtrip count (17-18): 0.95 - traced manually through 1023 lines
- append_entry fire-and-forget pattern: 1.0 - explicit in code comments
- list_projects N+1: 0.98 - confirmed loop + count_entries call
- state_manager.record_tool() as DB write: 0.97 - verified in state/manager.py
