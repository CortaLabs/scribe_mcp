---
id: scribe_client_server_split-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_client_server_split"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 02:42:04 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — scribe_client_server_split
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-17 01:59:42 UTC

> Execution roadmap for scribe_client_server_split.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Est. Complexity | Confidence |
|-------|------|------------------|-----------------|------------|
| Phase 1 — Interface Cleanup | Promote extended methods to StorageBackend base class | Updated base.py with 12 new method stubs | Low | 0.95 |
| Phase 2 — Mode Detection | Add operating mode detection and settings | mode_detection.py, settings.py updates | Low | 0.95 |
| Phase 3 — Server REST API | Add /api/v1/* endpoints to Starlette app | server_sse.py with backend routes + batch | Medium | 0.90 |
| Phase 4 — RemoteStorageBackend | Implement the HTTP proxy storage backend | storage/remote.py (core deliverable) | High | 0.85 |
| Phase 5 — Integration & Testing | Wire everything together, full test suite | Tests, .env config, startup flow | Medium | 0.85 |
| Phase 6 — CI/CD & Packaging (Deferred) | GitHub Actions pipeline, dependency split | .github/workflows/, pyproject.toml split | Medium | 0.80 |

**Execution Order:** Phase 1 -> 2 -> 3 -> 4 -> 5 (sequential, each builds on previous). Phase 6 is independent and deferred.

**Total Estimated Effort:** ~1100-1200 lines of new/modified code across 10 files.
<!-- ID: phase_0 -->
### Phase 1 — Interface Cleanup (base.py)

**Objective:** Promote 12 extended StorageBackend methods from duck-typed to formally declared in base.py. This is a prerequisite for RemoteStorageBackend to implement the full interface.

**Task Package 1.1: Add extended method stubs to StorageBackend**

**Scope:** Add 12 method stubs to `src/scribe_mcp/storage/base.py`
**Files to Modify:** `src/scribe_mcp/storage/base.py` (lines 17-420)
**Dependencies:** None (first task)

**Specifications:**
1. Add the following methods to `StorageBackend` class with `raise NotImplementedError` default implementations:
   - `async def upsert_session(self, *, session_id: str, transport_session_id: Optional[str] = None, repo_root: Optional[str] = None, mode: Optional[str] = None) -> None`
   - `async def set_session_mode(self, session_id: str, mode: str) -> None`
   - `async def get_session_mode(self, session_id: str) -> Optional[str]`
   - `async def set_session_project(self, session_id: str, project_name: str) -> None`
   - `async def get_session_project(self, session_id: str) -> Optional[str]`
   - `async def get_session_by_transport(self, transport_session_id: str) -> Optional[dict]`
   - `async def upsert_agent_recent_project(self, agent_id: str, project_name: str) -> None`
   - `async def get_or_create_agent_session(self, *, identity_key: str, agent_name: str = "", agent_key: str = "", repo_root: str = "", mode: str = "", scope_key: str = "") -> str`
   - `async def upsert_dev_plan(self, project_id: int, plan_type: str, **kwargs) -> None`
   - `async def update_session_activity(self, *, session_id: str, tool_name: str, timestamp: Optional[str] = None) -> None`
   - `async def get_session_activity(self, session_id: str) -> Optional[dict]`
   - `async def fetch_project_sync(self, name: str) -> Optional['ProjectRecord']` (synchronous wrapper)
2. Add `RemoteUnavailableError` exception class at the top of base.py
3. Each method should have a docstring explaining its purpose

**Verification:**
- [ ] `python -c "from scribe_mcp.storage.base import StorageBackend; print(len([m for m in dir(StorageBackend) if not m.startswith('_')]))"` returns >= 45
- [ ] Existing tests pass unchanged (pytest tests/ -x -q)
- [ ] SQLiteStorage and PostgresStorage still work (they already implement these methods)

**Out of Scope:**
- Do NOT modify SQLiteStorage or PostgresStorage (they already have these methods)
- Do NOT change method signatures of existing abstract methods

---

### Phase 2 — Mode Detection

**Objective:** Add mode detection infrastructure and settings fields so the system can determine at startup whether to run as server, client, or standalone.

**Task Package 2.1: Create mode_detection.py**

**Scope:** Create `src/scribe_mcp/config/mode_detection.py` with OperatingMode enum and detect function
**Files to Modify:** `src/scribe_mcp/config/mode_detection.py` (CREATE)
**Dependencies:** Phase 1 complete

**Specifications:**
1. Create `OperatingMode` enum with values: SERVER, CLIENT, STANDALONE
2. Create `async def detect_operating_mode(settings) -> OperatingMode` function
3. Create `async def _probe_remote(url: str, timeout: float = 3.0) -> bool` using httpx
4. Detection priority: explicit SCRIBE_MODE > SCRIBE_REMOTE_URL probe > SCRIBE_DB_URL > standalone default
5. If probe fails and fallback enabled, return STANDALONE with warning log
6. If probe fails and fallback disabled, raise RuntimeError

**Verification:**
- [ ] `pytest tests/test_mode_detection.py -v` passes
- [ ] Mode detection returns CLIENT when health endpoint returns {"service": "scribe-mcp"}
- [ ] Mode detection returns STANDALONE when health endpoint unreachable and fallback=true

**Task Package 2.2: Add settings fields**

**Scope:** Add 4 new fields to Settings dataclass
**Files to Modify:** `src/scribe_mcp/config/settings.py` (lines 39-295)
**Dependencies:** None (can run parallel with 2.1)

**Specifications:**
1. Add field `remote_server_url: Optional[str] = None` mapped to `SCRIBE_REMOTE_URL`
2. Add field `mode: str = "auto"` mapped to `SCRIBE_MODE`
3. Add field `remote_connect_timeout: float = 3.0` mapped to `SCRIBE_REMOTE_CONNECT_TIMEOUT`
4. Add field `remote_fallback: bool = True` mapped to `SCRIBE_REMOTE_FALLBACK`
5. Parse in `Settings.load()` using `os.environ.get()` with defaults

**Verification:**
- [ ] Settings loads correctly with no new env vars set (defaults work)
- [ ] Settings loads correctly with SCRIBE_REMOTE_URL=http://example.com
- [ ] Existing tests pass unchanged

**Out of Scope:**
- Do NOT modify .env file (that's Phase 5)
- Do NOT modify server.py startup (that's Phase 5)

---

### Phase 3 — Server REST API

**Objective:** Add HTTP endpoints to the Hetzner Scribe server's Starlette app so RemoteStorageBackend can call them.

**Task Package 3.1: Add /api/v1/backend/{operation} route**

**Scope:** Add single-operation REST endpoint to server_sse.py
**Files to Modify:** `src/scribe_mcp/server_sse.py` (155 lines)
**Dependencies:** Phase 1 complete (base.py has full method inventory)

**Specifications:**
1. Add `handle_backend_operation(request: Request) -> JSONResponse` handler
2. Extract operation name from path params, args from JSON body
3. Look up method on `server_module.storage_backend`
4. Reject operations starting with `_` (private methods)
5. Call method with `**args`, serialize result
6. Create `_serialize(obj)` helper that handles ProjectRecord, datetime, and dict types
7. Return `{"result": serialized}` on success, `{"error": msg}` on failure
8. Add Route to Starlette routes list

**Verification:**
- [ ] `curl -X POST http://localhost:8200/api/v1/backend/fetch_project -d '{"args":{"name":"test"}}' -H 'Content-Type: application/json'` returns valid JSON
- [ ] `pytest tests/test_server_api.py::test_single_operation` passes

**Task Package 3.2: Add /api/v1/batch route**

**Scope:** Add batch operation endpoint
**Files to Modify:** `src/scribe_mcp/server_sse.py`
**Dependencies:** Task 3.1 complete

**Specifications:**
1. Add `handle_batch(request: Request) -> JSONResponse` handler
2. Accept `{"operations": [{"op": "method_name", "args": {...}}, ...]}` body
3. Execute operations sequentially (order matters for set_project)
4. Return `{"results": [{"ok": true, "result": ...}, ...]}` — each result independent
5. If one operation fails, continue with remaining (partial success)
6. Add Route to Starlette routes list

**Verification:**
- [ ] Batch with 3 operations returns 3 results
- [ ] Batch with 1 failing operation returns partial results (2 ok, 1 error)
- [ ] `pytest tests/test_server_api.py::test_batch_operations` passes

**Out of Scope:**
- Do NOT add authentication (Phase 6)
- Do NOT modify existing /health, /sse, /messages routes
<!-- ID: phase_1 -->
### Phase 4 — RemoteStorageBackend (Core Deliverable)

**Objective:** Implement the HTTP proxy storage backend that connects local Scribe to Hetzner server.

**Task Package 4.1: Create RemoteStorageBackend skeleton**

**Scope:** Create `src/scribe_mcp/storage/remote.py` with class structure, lifecycle, and session cache
**Files to Modify:** `src/scribe_mcp/storage/remote.py` (CREATE)
**Dependencies:** Phase 1 (base.py interface), Phase 3 (server API to call)

**Specifications:**
1. Create `RemoteStorageBackend(StorageBackend)` class
2. Constructor takes `server_url: str` and `timeout: float = 30.0`
3. `setup()` creates `httpx.AsyncClient` with connection pooling (max_connections=10)
4. `close()` closes httpx client
5. Initialize in-memory session dicts: `_sessions`, `_session_projects`, `_session_modes`, `_agent_sessions`
6. Implement `_call(operation: str, **args) -> dict` helper for HTTP POST to /api/v1/backend/{operation}
7. Implement `execute_batch(operations: list[dict]) -> list[dict]` for /api/v1/batch

**Verification:**
- [ ] RemoteStorageBackend instantiates without error
- [ ] setup() creates httpx client successfully
- [ ] close() cleans up client

**Task Package 4.2: Implement session methods (local, in-memory)**

**Scope:** Implement all 12 session-related methods as in-memory operations
**Files to Modify:** `src/scribe_mcp/storage/remote.py`
**Dependencies:** Task 4.1

**Specifications:**
1. Implement all methods from the "Local (in-memory)" category in ARCHITECTURE_GUIDE section 4.1
2. `get_session_by_transport()` returns from `self._sessions` dict
3. `upsert_session()` stores in `self._sessions` dict
4. `get_or_create_agent_session()` generates UUID if not cached, stores in `self._agent_sessions`
5. `update_session_activity()` is a no-op (session analytics not needed in client mode)
6. `heartbeat_session()` and `end_session()` are no-ops

**Verification:**
- [ ] Session methods work without any HTTP calls (mock client to verify no network)
- [ ] get_or_create_agent_session returns consistent IDs for same identity_key

**Task Package 4.3: Implement remote (HTTP proxy) methods**

**Scope:** Implement project and entry methods that proxy to remote server
**Files to Modify:** `src/scribe_mcp/storage/remote.py`
**Dependencies:** Task 4.1, Phase 3 (server API exists)

**Specifications:**
1. Implement `fetch_project(name)` — POST /api/v1/backend/fetch_project, return ProjectRecord
2. Implement `upsert_project(...)` — POST /api/v1/backend/upsert_project, return ProjectRecord
3. Implement `list_projects()` — POST /api/v1/backend/list_projects, return list[ProjectRecord]
4. Implement `list_projects_by_repo(repo_root)` — same pattern
5. Implement `delete_project(name)` — return bool
6. Implement `update_project_docs(name, docs_json)` — return bool
7. Implement `insert_entry(...)` — POST, return None
8. Implement `fetch_recent_entries(...)` — POST, return list[dict]
9. Implement `fetch_recent_entries_paginated(...)` — POST, return tuple[list, int]
10. Implement `count_entries(...)` — POST, return int
11. Implement `query_entries(...)` / `query_entries_paginated(...)` / `count_query_entries(...)`
12. Implement `upsert_dev_plan(...)` — POST
13. Implement bridge methods as no-ops (return empty/None)
14. Implement `record_doc_change()` and `record_agent_report_card()` as fire-and-forget POSTs
15. Handle ProjectRecord deserialization (dict -> ProjectRecord with integer id)
16. Handle RemoteUnavailableError on connection failure

**Verification:**
- [ ] `pytest tests/test_remote_backend.py -v` passes (all methods tested with respx mocks)
- [ ] fetch_project returns ProjectRecord with correct id field
- [ ] insert_entry sends correct JSON to server
- [ ] Connection failure raises RemoteUnavailableError

**Out of Scope:**
- Do NOT implement caching beyond session cache (future optimization)
- Do NOT add retry logic beyond httpx defaults (future optimization)

---

### Phase 5 — Integration & Testing

**Objective:** Wire RemoteStorageBackend into the server startup, update storage factory, add integration tests, configure .env.

**Task Package 5.1: Update storage factory**

**Scope:** Add 'remote' backend type to create_storage_backend()
**Files to Modify:** `src/scribe_mcp/storage/__init__.py` (50 lines)
**Dependencies:** Phase 4 (RemoteStorageBackend exists)

**Specifications:**
1. Import OperatingMode from config.mode_detection
2. Add `mode: Optional[OperatingMode] = None` parameter to `create_storage_backend()`
3. If `mode == OperatingMode.CLIENT`, return `RemoteStorageBackend(settings.remote_server_url)`
4. All existing paths unchanged (postgres, sqlite, fallback)

**Verification:**
- [ ] `create_storage_backend(mode=OperatingMode.CLIENT)` returns RemoteStorageBackend
- [ ] `create_storage_backend()` with no mode returns existing behavior
- [ ] Existing tests pass unchanged

**Task Package 5.2: Update server.py startup**

**Scope:** Add mode detection to _startup() function
**Files to Modify:** `src/scribe_mcp/server.py` (lines 738-790)
**Dependencies:** Phase 2 (mode detection), Phase 4 (RemoteStorageBackend), Task 5.1 (factory)

**Specifications:**
1. In `_startup()`, after `_startup_complete` guard, call `detect_operating_mode(settings)`
2. Log resolved mode at INFO level
3. If mode is CLIENT, replace `storage_backend` global with `create_storage_backend(mode)`
4. Continue with existing `storage_backend.setup()` call
5. In client mode, skip background services that require server-only capabilities (plugin init, bridge init, cleanup)

**Verification:**
- [ ] Server starts in client mode when SCRIBE_REMOTE_URL set and server reachable
- [ ] Server starts in standalone mode when SCRIBE_REMOTE_URL set but server unreachable
- [ ] Server starts in server mode with no new env vars (backward compatible)
- [ ] Log output shows "Operating mode: client|server|standalone"

**Task Package 5.3: Create integration tests**

**Scope:** Write test suite for client/server interaction
**Files to Modify:** `tests/test_remote_backend.py` (CREATE), `tests/test_mode_detection.py` (CREATE), `tests/test_server_api.py` (CREATE), `tests/conftest.py` (MODIFY)
**Dependencies:** All phases complete

**Specifications:**
1. test_remote_backend.py: Use respx to mock HTTP calls, test all remote methods
2. test_mode_detection.py: Test all mode detection scenarios with mocked httpx
3. test_server_api.py: Use httpx.ASGITransport with real Starlette app + SQLiteStorage
4. Add pytest markers to conftest.py: client_proxy, server_api, e2e
5. All tests must pass in CI (no Postgres or remote server required)

**Verification:**
- [ ] `pytest tests/test_remote_backend.py tests/test_mode_detection.py tests/test_server_api.py -v` all pass
- [ ] `pytest tests/ -x -q` (full suite) passes without regression

**Task Package 5.4: Update .env for client mode**

**Scope:** Document and provide example .env configuration for client mode
**Files to Modify:** `.env.example` (or document in ARCHITECTURE_GUIDE)
**Dependencies:** All phases complete

**Specifications:**
1. Add SCRIBE_MODE=client
2. Add SCRIBE_REMOTE_URL=http://council-hub:8200
3. Comment out SCRIBE_DB_URL and SCRIBE_STORAGE_BACKEND=postgres
4. Keep SCRIBE_OBJECT_STORE_* settings (client talks to CortaStore directly)

**Verification:**
- [ ] Scribe MCP starts in <1 second with new .env
- [ ] set_project completes in <500ms
- [ ] All 21 tools work correctly in client mode

**Out of Scope:**
- Do NOT modify .claude.json (users can do this themselves)
- Do NOT deploy to Hetzner (server API is already running after Phase 3 deploy)

---

### Phase 6 — CI/CD & Packaging (DEFERRED)

**Objective:** Add automated deployment pipeline and split dependencies.

**Note:** This phase is DEFERRED. It is not a prerequisite for the client/server split to work. It can be implemented independently after Phases 1-5 are verified.

**Task Packages (not scoped in detail — requires separate architecture):**
- 6.1: Create .github/workflows/deploy.yml with test + SSH deploy
- 6.2: Split pyproject.toml dependencies into client/server optional groups
- 6.3: Update Dockerfile to use pip install ".[server]"
- 6.4: Add scribe-client entry point to pyproject.toml (optional convenience)
- 6.5: Configure Tailscale GitHub Action for runner connectivity
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Research Complete (5 docs) | 2026-02-17 | Research Agents | Done | research/ directory (112KB) |
| Architecture Complete | 2026-02-17 | ArchitectAgent | Done | ARCHITECTURE_GUIDE.md |
| Phase 1 — base.py Cleanup | TBD | CoderAgent | Planned | Task Package 1.1 |
| Phase 2 — Mode Detection | TBD | CoderAgent | Planned | Task Packages 2.1, 2.2 |
| Phase 3 — Server REST API | TBD | CoderAgent | Planned | Task Packages 3.1, 3.2 |
| Phase 4 — RemoteStorageBackend | TBD | CoderAgent | Planned | Task Packages 4.1-4.3 |
| Phase 5 — Integration | TBD | CoderAgent | Planned | Task Packages 5.1-5.4 |
| MVP Latency Target Met (<500ms) | TBD | Review Agent | Planned | Benchmark test |
| Phase 6 — CI/CD (Deferred) | TBD | TBD | Deferred | Separate architecture needed |

Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.
<!-- ID: retro_notes -->
- **Research Phase (2026-02-17):** 5 parallel research analysts completed in ~30 minutes. Total 112KB of research docs with 0.93-0.97 confidence across all findings. All critical claims verified by Architect against actual code. No significant discrepancies found between research and reality.
- **Architecture Decision:** Chose REST API over MCP protocol proxy — simpler, stateless, supports batch natively. Chose in-memory session cache — eliminates middleware overhead without network calls.
- **Scope Note:** CI/CD (Phase 6) deferred to keep MVP focused on latency fix. Can be implemented independently.

Generated by ArchitectAgent-ClientServerSplit, 2026-02-17.
