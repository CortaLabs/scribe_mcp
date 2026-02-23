# Research: Storage Backend Abstraction & Remote Backend Design

**Date**: 2026-02-17  
**Analyst**: ResearchAnalyst-StorageBackend (Research Analyst 3 of 5)  
**Project**: scribe_client_server_split  
**Confidence**: 0.97 (high - all claims directly verified from code)

---

## Executive Summary

Scribe MCP has a `StorageBackend` abstract class (`storage/base.py`, 420 lines) with two concrete implementations: `SQLiteStorage` (decomposed across 14 sub-modules) and `PostgresStorage` (monolithic 2148 lines). The backend is a module-level singleton in `server.py` shared across all tools.

The core performance problem: when a local client (stdio) connects to Hetzner Postgres directly, every tool call makes 2-20 sequential async DB roundtrips over Tailscale. `set_project` alone makes 19-20 roundtrips. At 10-50ms per roundtrip, this creates 0.2s-3+ minute latency.

**A `RemoteStorageBackend` that proxies operations to a Hetzner Scribe SSE server is technically feasible** and would reduce 17-20 sequential remote DB calls to 1 HTTP call per tool invocation.

---

## 1. StorageBackend Interface: Complete Method Catalog

Source: `src/scribe_mcp/storage/base.py` (420 lines, 13KB)

### 1.1 Lifecycle Methods (concrete, not abstract)

| Method | Signature | Notes |
|--------|-----------|-------|
| `setup()` | `async () -> None` | Optional startup (connection pool init) |
| `close()` | `async () -> None` | Release resources (connection pool close) |

### 1.2 Project CRUD (abstract - all required)

| Method | Signature | R/W | Returns |
|--------|-----------|-----|--------|
| `upsert_project()` | `(*, name, repo_root, progress_log_path, docs_json?, bridge_id?, bridge_managed) -> ProjectRecord` | W | ProjectRecord dataclass |
| `fetch_project()` | `(name: str) -> Optional[ProjectRecord]` | R | ProjectRecord or None |
| `list_projects()` | `() -> List[ProjectRecord]` | R | All projects globally |
| `list_projects_by_repo()` | `(repo_root: str) -> List[ProjectRecord]` | R | Projects scoped to repo |
| `delete_project()` | `(name: str) -> bool` | W | True if deleted |
| `update_project_docs()` | `(name: str, docs_json: str) -> bool` | W | True if updated |

### 1.3 Entry Management (mix of abstract and concrete)

| Method | Signature | R/W | Abstract? |
|--------|-----------|-----|----------|
| `insert_entry()` | `(*, entry_id, project, ts, emoji, agent, message, meta, raw_line, sha256) -> None` | W | YES |
| `fetch_recent_entries()` | `(*, project, limit, filters?, offset) -> List[Dict]` | R | YES |
| `fetch_recent_entries_paginated()` | `(*, project, page, page_size, filters?) -> Tuple[List, int]` | R | NO (default impl) |
| `count_entries()` | `(project, filters?) -> int` | R | NO (default: fetch all + count) |
| `query_entries()` | `(*, project, limit, start?, end?, agents?, emojis?, message?, message_mode, case_sensitive, meta_filters?, offset) -> List[Dict]` | R | NO (default: empty) |
| `query_entries_paginated()` | `(*, project, page, page_size, ...) -> Tuple[List, int]` | R | NO (default impl) |
| `count_query_entries()` | `(*, project, ...) -> int` | R | NO (default: fetch all + count) |

### 1.4 Agent Session Management (abstract)

| Method | Signature | R/W |
|--------|-----------|-----|
| `upsert_agent_session()` | `(agent_id, session_id, metadata?) -> None` | W |
| `heartbeat_session()` | `(session_id: str) -> None` | W |
| `end_session()` | `(session_id: str) -> None` | W |
| `get_agent_project()` | `(agent_id: str) -> Optional[Dict]` | R |
| `set_agent_project()` | `(agent_id, project_name?, expected_version?, updated_by, session_id) -> Dict` | W |
| `update_session_activity()` | `(session_id, tool_name, timestamp) -> None` | W |
| `get_session_activity()` | `(session_id: str) -> Optional[Dict]` | R |

### 1.5 Bridge Management (abstract)

| Method | Signature | R/W |
|--------|-----------|-----|
| `insert_bridge()` | `(bridge_id, name, version, manifest_json, state) -> None` | W |
| `update_bridge_state()` | `(bridge_id, state) -> None` | W |
| `update_bridge_health()` | `(bridge_id, health_json, error?) -> None` | W |
| `fetch_bridge()` | `(bridge_id: str) -> Optional[Dict]` | R |
| `list_bridges()` | `(state?) -> List[Dict]` | R |
| `delete_bridge()` | `(bridge_id: str) -> None` | W |

### 1.6 Auxiliary (concrete with optional override)

| Method | Signature | Notes |
|--------|-----------|-------|
| `record_doc_change()` | `(project, *, doc, section, action, agent, metadata, sha_before, sha_after)` | Optional |
| `record_agent_report_card()` | `(project, *, file_path, agent_name, stage, overall_grade, performance_level, metadata)` | Optional |
| `get_reminder_history()` | `(*, project_root?, agent_id?, category?, limit) -> List[Dict]` | Default: returns [] |
| `clear_reminder_history()` | `(*, project_root?, agent_id?) -> int` | Default: returns 0 |
| `cleanup_old_entries()` | `(project_id?, retention_days, archive) -> int` | Abstract |

---

## 2. Extended Methods (NOT in base.py but called in production code)

These methods exist in both `SQLiteStorage` and `PostgresStorage` but are **NOT declared in `StorageBackend`**. They are accessed via duck-typing (hasattr checks) or direct calls. Any `RemoteStorageBackend` MUST implement them.

| Method | Called From | Tables Touched |
|--------|-------------|----------------|
| `upsert_session()` | set_project, state/manager.py, migration.py, execution_context.py | `scribe_sessions` |
| `set_session_mode()` | set_project, state/manager.py | `scribe_sessions` |
| `get_session_mode()` | tool_runtime.py, state/manager.py | `scribe_sessions` |
| `set_session_project()` | set_project, state/manager.py, migration.py | `session_projects` |
| `get_session_project()` | state/manager.py, tool_runtime.py | `session_projects` |
| `get_session_by_transport()` | execution_context.py, tool_runtime.py | `scribe_sessions` |
| `upsert_agent_recent_project()` | set_project, state/manager.py, migration.py | `agent_recent_projects` |
| `get_or_create_agent_session()` | tool_runtime.py | `agent_sessions` |
| `upsert_dev_plan()` | set_project (per plan_type), migration.py | `dev_plans` |
| `fetch_project_sync()` | Likely doc management sync code | `scribe_projects` |
| `count_entries()` | list_projects, set_project (already in base but no abstract) | `scribe_log_entries` |
| `get_project()` | agent_project_utils.py line 43 | `scribe_projects` (alias for fetch_project) |

---

## 3. Implementation Analysis

### 3.1 SQLiteStorage
- **File**: `src/scribe_mcp/storage/sqlite/__init__.py` (433 lines, 46 methods)
- **Architecture**: Thin facade delegating to sub-modules:
  - `entries.py` - log entry operations
  - `projects.py` - project CRUD
  - `sessions.py` - session management (includes extended methods)
  - `planning.py` - dev_plans operations  
  - `documents.py` - doc change recording
  - `domain_facade.py` - mixin providing extended methods
  - `schema.py` + `migrations.py` - schema management
  - `internals.py` + `pool.py` - connection pooling
  - `telemetry.py` - metrics
- **Connection**: SQLite file at `settings.sqlite_path`, lazy init, write lock
- **Notable**: Has `SQLiteDomainFacadeMixin` as extra parent class providing extended methods

### 3.2 PostgresStorage
- **File**: `src/scribe_mcp/storage/postgres/__init__.py` (2148 lines, 78 methods)
- **Architecture**: Monolithic class, everything in one file
- **Connection**: asyncpg connection pool (min=2, max=20 default), schema management
- **Config**: Supports schema_name, pool sizing, command/connect timeouts, retries
- **Notable**: The current production backend for Hetzner; it IS the performance bottleneck

### 3.3 ProjectRegistry (SEPARATE - NOT a StorageBackend)
- **File**: `src/scribe_mcp/shared/project_registry.py` (780 lines)
- **Architecture**: Direct sync `sqlite3` access, bypasses StorageBackend entirely
- **Methods called from tools**: `ensure_project()`, `touch_access()`, `touch_entry()`, `record_doc_update()`, `set_status()`, `get_project()`, `list_projects()`, `get_last_known_project()`
- **CRITICAL ISSUE**: This is an abstraction violation. It writes directly to the same SQLite DB that SQLiteStorage uses. When running with PostgresStorage, it STILL writes to local SQLite.
- **Implication for remote backend**: ProjectRegistry calls will NEVER be remoted - they always use local SQLite. This is actually fine for a client/server split: local metadata can stay local.

### 3.4 Backend Singleton Pattern
- Created once at import time in `server.py` line 116: `storage_backend = create_storage_backend()`
- Shared via module-level reference: `server_module.storage_backend`
- Also injected into `StateManager` and `RouterContextManager` constructors
- Tools access it via `server_module.storage_backend` directly OR via injected `storage_backend` parameter in `execute_tool_call()`

---

## 4. DB Roundtrip Analysis: The Performance Problem

### set_project call (worst case): 19-20 roundtrips

```
Direct backend calls:
1.  backend.fetch_project(name)                    # check exists
2.  backend.list_projects()                         # slug collision check  
3.  backend.upsert_project(...)                     # create/update
4.  backend.upsert_dev_plan() x4                   # arch/phase/checklist/log = 4 calls
5.  backend.set_session_project(session_key, name) # bind session
6.  backend.set_session_mode(session_key, 'project') 
7.  backend.upsert_session(...)                    # persist session data
8.  backend.upsert_agent_recent_project(...)       # track agent history

Via StateManager (each StateManager call may make multiple backend calls):
9.  backend.list_projects() (or list_projects_by_repo)  # load projects cache
10. backend.get_session_project(session_id)        # resolve current project
11. backend.get_agent_project(GLOBAL_AGENT_ID)     # global fallback
12. backend.get_session_mode(session_id)           # session modes
13. backend.get_session_activity(session_id)       # activity tracking
14. backend.upsert_project(...)                    # persist via state manager
15. backend.set_agent_project(...)                 # set global project
16. backend.update_session_activity(...)           # record_tool

ProjectRegistry (direct SQLite - NOT remoted):
17. registry.ensure_project(project_record)        # backfill registry
18. registry.touch_access(project_record.name)     # update access time

Total: 18-20 backend calls = 18-20 TCP roundtrips over Tailscale
At 25ms avg roundtrip: 450-500ms minimum for set_project
```

### append_entry call: 3-4 roundtrips minimum
```
1. backend.fetch_project(project_name)    # ensure project exists
2. backend.upsert_project(...) [if not found]
3. backend.insert_entry(...)              # write log entry
4. ProjectRegistry.touch_entry()          # local SQLite, not remoted
Total: 3-4 roundtrips = 75-150ms over Tailscale
```

---

## 5. Remote Backend Design Options

### Option A: Tool-Proxy RemoteStorageBackend (RECOMMENDED)

**Concept**: Each StorageBackend method maps to ONE HTTP POST to the Hetzner Scribe server's HTTP management API (not MCP tools). The backend batches related calls.

**How it works**:
```
Local client (stdio) -> RemoteStorageBackend -> HTTP POST to :8200/api/v1/backend/{operation} -> Hetzner Scribe -> PostgresStorage (local DB)
```

**Why this is best**: 
- Clean separation: the 17-20 roundtrips happen on Hetzner (local to DB, microseconds) not over Tailscale
- Local client makes 1 HTTP call per tool invocation (not 1 per DB operation)
- Hetzner server runs existing tools with local PostgresStorage
- Client-side RemoteStorageBackend calls remote MCP tools via HTTP

**Method mapping**:
```python
class RemoteStorageBackend(StorageBackend):
    # Project ops: POST /api/v1/projects/{name}
    async def upsert_project(...) -> ProjectRecord:
        resp = await self._http.post('/api/v1/projects', json={...})
        return ProjectRecord(**resp.json())

    # Entry ops: POST /api/v1/entries  
    async def insert_entry(...) -> None:
        await self._http.post('/api/v1/entries', json={...})

    # Batch endpoint for set_project's 8 direct calls:
    async def set_project_batch(...) -> Dict:
        # Single HTTP call replacing 8 sequential DB calls
        await self._http.post('/api/v1/batch/set_project', json={...})
```

**Roundtrip reduction**: 17-20 Tailscale roundtrips -> 1 HTTP call

### Option B: MCP Tool Forwarding

**Concept**: Instead of a backend, the local client delegates entire tool calls to Hetzner Scribe MCP server via SSE/HTTP.

**How it works**:
```
Local Claude (stdio) -> tools/set_project.py (local) -> RemoteToolForwarder -> HTTP MCP call to Hetzner:8200 -> set_project (remote) -> PostgresStorage (local to Hetzner)
```

**Why this is attractive**: 
- No new HTTP API needed on server side
- Hetzner's existing tool handles all 17-20 DB ops locally
- Local client is a thin proxy

**Why this is complex**:
- Tools have complex context injection (execution context, session management)
- File system operations (read/write to .scribe/ dirs) must remain local
- Can't forward filesystem-touching operations remotely
- Session identity must map correctly between local and remote

### Option C: Hybrid Split-Backend

**Concept**: Some storage operations stay local (filesystem-backed), others are proxied remote.

**Proposed split**:
```
Local (SQLiteStorage or FileStorage):
- ProjectRegistry operations (always local SQLite)
- File writes (progress log, managed docs)
- Session mode/project binding (session state = local)
- Vector indexing (if enabled locally)

Remote (HTTP proxy via RemoteStorageBackend):
- insert_entry (DB mirror)
- fetch_recent_entries / query_entries
- fetch_project / list_projects (project catalog)
- upsert_project (DB registration)
```

**How it works**:
```python
class HybridStorageBackend(StorageBackend):
    def __init__(self, local: SQLiteStorage, remote: RemoteStorageBackend):
        self._local = local    # Always write session/state here
        self._remote = remote  # Write log entries and project catalog here
    
    async def insert_entry(self, ...) -> None:
        await self._local.insert_entry(...)   # Local first for fast response
        await self._remote.insert_entry(...)  # Async mirror to Hetzner (fire-and-forget)
    
    async def fetch_recent_entries(self, ...) -> List[Dict]:
        # Try remote first for full history, fall back to local
        try:
            return await self._remote.fetch_recent_entries(...)
        except RemoteUnavailableError:
            return await self._local.fetch_recent_entries(...)
```

**Why this is most flexible**:
- Graceful degradation when Hetzner is unreachable
- Local SQLite has recent history for fast reads
- Fire-and-forget remote writes don't block tool responses

---

## 6. Implementation Challenges

### 6.1 ProjectRecord Requires `id: int`

The `ProjectRecord` dataclass requires `id: int` from the DB. A remote backend must either:
- Return a fake/hash-based ID (risk: breaks anything that uses ID as FK)
- Ask the remote server for the real ID (adds a roundtrip)
- Use a UUID-based ID scheme in RemoteStorageBackend

### 6.2 ProjectRegistry Cannot Be Remoted

`ProjectRegistry` uses synchronous `sqlite3` directly. It is NOT a StorageBackend. Its 8 methods touch local SQLite. For a remote backend, these calls will ALWAYS stay local. This is acceptable: registry is metadata, not primary storage.

### 6.3 Extended Methods Must Be Implemented

All 12 extended methods (not in base.py) must be implemented in RemoteStorageBackend. The duck-typing pattern means missing methods are silently skipped (hasattr returns False), which could cause subtle state corruption.

**Recommendation**: Add all extended methods to `StorageBackend` base class as optional (raise NotImplementedError by default) so RemoteStorageBackend can provide stubs that return safe defaults.

### 6.4 Session Management Complexity

Session management (`upsert_session`, `set_session_project`, etc.) is deeply tied to the local execution context. For a remote backend:
- Local sessions should be managed locally (SQLiteStorage handles this)
- Only log entries and project catalog need to be remote
- RemoteStorageBackend should return dummy/no-op responses for session ops

### 6.5 Optimistic Concurrency in `set_agent_project()`

`set_agent_project()` has `expected_version` parameter for OCC. This requires the remote server to handle versioning correctly. A proxy can forward this but must handle `ConflictError` exceptions.

### 6.6 Synchronous `fetch_project_sync()` 

Called from some contexts that can't be async. A remote backend cannot implement this efficiently (would need blocking HTTP). Recommended: implement via `asyncio.run()` in a thread pool (same as PostgresStorage does).

---

## 7. Recommended Architecture: Option A with Batch Endpoints

The best path forward is **Option A (Tool-Proxy RemoteStorageBackend) with batch endpoints**:

1. **Add HTTP management API to Hetzner Scribe server** (`/api/v1/backend/...`)
   - `POST /api/v1/backend/batch` - accepts list of operations, returns list of results
   - Each operation = `{"op": "upsert_project", "args": {...}}`
   - Hetzner server executes all ops locally with local PostgresStorage

2. **Create `RemoteStorageBackend(StorageBackend)`**
   - File: `src/scribe_mcp/storage/remote.py`
   - Constructor: `__init__(self, server_url: str, api_key: str, timeout: float = 30.0)`
   - Uses `httpx.AsyncClient` for HTTP
   - Implements all 25 abstract methods + 12 extended methods
   - Session management methods return safe no-ops (local-only)
   - Batch support: collects multiple calls and sends as one HTTP request

3. **Update `create_storage_backend()`**
   - Add `"remote"` backend type
   - Read `SCRIBE_REMOTE_URL` and `SCRIBE_REMOTE_KEY` from settings
   - Fallback: if remote unreachable at startup, warn and fall back to local SQLite

4. **ProjectRegistry stays local**
   - No changes needed - it's already SQLite-only
   - Remote backend doesn't need to implement ProjectRegistry behavior

---

## 8. Files Requiring Modification

| File | Change | Priority |
|------|--------|----------|
| `src/scribe_mcp/storage/base.py` | Add extended methods as `raise NotImplementedError` optionals | HIGH |
| `src/scribe_mcp/storage/__init__.py` | Add `create_storage_backend()` case for `"remote"` | HIGH |
| `src/scribe_mcp/storage/remote.py` | CREATE: `RemoteStorageBackend` class | HIGH (new file) |
| `src/scribe_mcp/config/settings.py` | Add `remote_backend_url`, `remote_backend_key` settings | HIGH |
| `src/scribe_mcp/server.py` | Add `/api/v1/backend/batch` HTTP endpoint | HIGH (server side) |

---

## 9. Open Questions for Architect

1. **Batch endpoint design**: Should the batch API be a new HTTP endpoint, or should it reuse the existing SSE MCP protocol?

2. **Authentication**: How does RemoteStorageBackend authenticate to Hetzner Scribe server? Same HMAC key as CortaStore? New token?

3. **Session management in split**: Should session bindings (set_session_project, etc.) be:
   - Local-only (SQLite on client) = simplest, works offline
   - Remote (Hetzner tracks sessions) = needed for cross-machine session persistence
   - Both (write to both, read from local)

4. **ProjectRegistry refactoring**: Should ProjectRegistry eventually be replaced by StorageBackend calls, or keep it as a local-only SQLite cache that complements the remote backend?

5. **Failure modes**: What behavior is required when Hetzner is unreachable? Silent skip? Error? Fallback to local cache?

6. **base.py cleanup**: Should extended methods be promoted to the official interface now, or added as optional stubs?

---

## 10. Confidence Assessment

| Claim | Confidence | Evidence |
|-------|-----------|----------|
| StorageBackend has 25 abstract methods | 1.0 | Read base.py fully |
| 12 extended methods not in interface | 0.97 | Searched all files for usage patterns |
| set_project makes 19-20 DB roundtrips | 0.95 | Traced code flow, some StateManager calls may merge |
| ProjectRegistry bypasses StorageBackend | 1.0 | sqlite3 direct calls confirmed |
| No existing remote backend | 1.0 | Comprehensive search found nothing |
| Backend is module-level singleton | 1.0 | server.py line 116 confirmed |
| Option A technically feasible | 0.90 | Design validated; implementation complexity unknown |
| ProjectRecord.id integer requirement is a challenge | 0.95 | Checked all dataclass fields in models.py |

---

## Handoff Notes for Architect

**Critical decision points**:
1. Whether to add `/api/v1/backend/batch` endpoint to server, or use MCP protocol
2. Whether session management is local-only or replicated to Hetzner
3. Whether to fix the `base.py` interface gap (extended methods) in this sprint

**For Coder**:
- `src/scribe_mcp/storage/remote.py` is the primary new file (CREATE, not replace)
- `create_storage_backend()` in `__init__.py` needs a 3rd case
- Server needs a batch HTTP handler route
- All extended methods need safe defaults in RemoteStorageBackend (return empty, skip silently)

**For Review**:
- Verify that session management no-ops in RemoteStorageBackend don't break session isolation
- Check that `ProjectRecord.id` handling is correct (fake IDs vs real IDs)
- Ensure fallback to local SQLite works correctly when remote is unavailable
