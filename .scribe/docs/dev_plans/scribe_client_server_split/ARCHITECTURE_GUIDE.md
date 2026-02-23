---
id: scribe_client_server_split-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_client_server_split"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 02:36:34 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — scribe_client_server_split
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 01:59:42 UTC

> Architecture guide for scribe_client_server_split.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
- **Context:** Scribe MCP currently runs locally as a stdio subprocess but connects directly to Hetzner Postgres over Tailscale. Every DB call is a ~50-200ms network roundtrip. `set_project` makes 17-18 sequential DB roundtrips totaling 3+ seconds minimum. The `execute_tool_call()` middleware adds another 5-7 DB roundtrips BEFORE any tool runs. A Scribe MCP server is already running ON Hetzner at :8200 (SSE) with local Postgres access (<1ms RTT).

- **Goals:**
  - Reduce `set_project` latency from 3+ seconds to <500ms (10x improvement)
  - Reduce per-tool-call middleware overhead from 5-7 roundtrips to 0 (local session cache)
  - Maintain full filesystem access for local tools (read_file, search, edit_file, manage_docs)
  - Support graceful fallback to local SQLite when no remote server is available
  - Zero tool code changes — the split is entirely in the storage layer

- **Non-Goals:**
  - Rewriting the MCP protocol layer or transport code
  - Implementing authentication (Tailscale provides network-level trust)
  - CI/CD pipeline (Phase 6, separate concern)
  - Modifying existing tool business logic
  - Blue-green deployment or zero-downtime server restarts

- **Success Metrics:**
  - `set_project` completes in <500ms over Tailscale (from 3+ seconds)
  - `append_entry` latency unchanged (file write remains primary, DB mirror can be async)
  - All 21 tools pass existing test suite with RemoteStorageBackend
  - Fallback to SQLite works when SCRIBE_REMOTE_URL is unset or unreachable
  - No regression in functionality for server mode (Mode A) or standalone mode (Mode C)

- **Research Foundation:**
  - RESEARCH_TOOL_CLASSIFICATION_20260217.md — 21 tools classified, DB roundtrip counts verified
  - RESEARCH_TRANSPORT_PROXY_20260217.md — Transport analysis, Option B (RemoteStorageBackend) recommended
  - RESEARCH_STORAGE_BACKEND_20260217.md — 37 StorageBackend methods cataloged, batch API proposed
  - RESEARCH_MODE_DETECTION_20260217.md — 3 operating modes defined, mode detection algorithm designed
  - RESEARCH_CICD_DEPLOYMENT_20260217.md — Deployment architecture, dependency split proposal
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
  - FR-1: RemoteStorageBackend implementing StorageBackend ABC, proxying DB operations to Hetzner Scribe server via REST API
  - FR-2: Mode detection at startup: auto-detect client/server/standalone based on environment variables
  - FR-3: Server-side REST API endpoints on existing Starlette app for backend operations
  - FR-4: Batch endpoint for high-roundtrip operations (set_project, append_entry bulk)
  - FR-5: In-memory session cache for execute_tool_call() middleware (eliminates 5-7 roundtrips per call)
  - FR-6: Startup health probe against remote server /health endpoint
  - FR-7: Fallback to local SQLite at startup when remote is unreachable (if SCRIBE_REMOTE_FALLBACK=true)

- **Non-Functional Requirements:**
  - NFR-1: Backward-compatible — Mode A (full server) must work exactly as before with zero changes
  - NFR-2: No new dependencies — httpx already exists, no MCP SDK client needed
  - NFR-3: Startup time in client mode < 1 second (probe + backend init)
  - NFR-4: Single HTTP roundtrip per tool call for remote operations (batch where needed)
  - NFR-5: No split-brain — mid-session fallback is not supported (fail clearly instead)

- **Assumptions:**
  - Tailscale provides network-level trust (no auth tokens needed initially)
  - Remote Scribe server at :8200 is the existing Hetzner SSE deployment
  - httpx ~0.27 is already a dependency (verified in corta.py, pyproject.toml)
  - ProjectRegistry remains local-only (already uses direct sqlite3, never remoted)
  - Hetzner Postgres RTT from Scribe server is < 1ms (same Docker network)

- **Constraints:**
  - C-1: MUST NOT modify existing tool business logic (storage layer change only)
  - C-2: MUST NOT create replacement files for existing modules (Commandment #0.5)
  - C-3: MUST keep existing server mode fully functional (no regression)
  - C-4: Docker image size limit: under 400MB (from CLAUDE.md)
  - C-5: Secrets management: Docker secrets for server, .env for client

- **Risks & Mitigations:**
  - R-1: Tailscale flaky → startup fallback to SQLite, clear warning message
  - R-2: Remote server downtime → tool calls fail with actionable error, user restarts to retry
  - R-3: Extended methods not in base.py → add NotImplementedError stubs to base.py first
  - R-4: ProjectRecord.id integer requirement → server returns real DB ID in REST responses
  - R-5: .env override=True → document that SCRIBE_MODE must be in .env not just .claude.json
<!-- ID: architecture_overview -->
- **Solution Summary:** Split Scribe MCP into three operating modes via a new `RemoteStorageBackend` that proxies DB operations to a Hetzner-resident Scribe server over a thin REST API. Local tools (read_file, search, edit_file) run locally. DB-backed tools (set_project, append_entry, query_entries) proxy their storage operations to the remote server. Session management stays local (in-memory). The mode is detected at startup based on environment variables and a health probe.

- **Three Operating Modes:**

  | Mode | Name | StorageBackend | When |
  |------|------|---------------|------|
  | A | Full Server | PostgresStorage or SQLiteStorage (direct) | Hetzner Docker container, or local dev with direct DB access |
  | B | Lightweight Client | RemoteStorageBackend (HTTP proxy) | Local dev machine, proxies to Hetzner :8200 |
  | C | Standalone | SQLiteStorage (local) | Offline/air-gapped, or when remote is unreachable at startup |

- **System Topology:**

  ```
  Dev PC (WSL2) — MODE B: Lightweight Client
    Claude Code (stdio)
        |
        v
    Local Scribe MCP (stdio transport)
        |
        +---> LOCAL-ONLY tools (read_file, search, edit_file, scribe_doctor)
        |       -> Local filesystem (0ms)
        |
        +---> HYBRID tools (append_entry, manage_docs, set_project...)
        |       -> File part: local filesystem (0ms)
        |       -> DB part: RemoteStorageBackend -> HTTP POST to Hetzner
        |
        +---> REMOTE-ONLY tools (list_projects, read_recent, query_entries)
                -> RemoteStorageBackend -> HTTP POST to Hetzner
                        |
                        v (~50ms Tailscale RTT, single roundtrip)
    Hetzner CCX23 (council-hub) — MODE A: Full Server
        Scribe MCP SSE Server (:8200)
            |
            +---> /api/v1/* REST endpoints (NEW)
            |       -> PostgresStorage (local, <1ms RTT)
            |
            +---> /health (existing)
            +---> /sse, /messages/ (existing MCP SSE transport)
            |
            v
        PostgreSQL (agentkit DB, scribe schema)
  ```

- **Component Breakdown:**
  - **RemoteStorageBackend** (`src/scribe_mcp/storage/remote.py` - NEW file): Implements StorageBackend ABC. Each method makes an HTTP call to the remote server's REST API. Session methods (get_session_by_transport, upsert_session, etc.) are handled locally with in-memory dict. Uses httpx.AsyncClient with a persistent connection pool.
  - **Server REST API** (`src/scribe_mcp/server_sse.py` - MODIFY): Add `/api/v1/backend/{operation}` and `/api/v1/batch` routes to the existing Starlette app. Each route calls through to the local PostgresStorage backend. HMAC auth optional.
  - **Mode Detection** (`src/scribe_mcp/config/mode_detection.py` - NEW file): `OperatingMode` enum + `detect_operating_mode()` function. Probes remote /health, returns mode enum.
  - **Settings Extension** (`src/scribe_mcp/config/settings.py` - MODIFY): Add `remote_server_url`, `mode`, `remote_connect_timeout`, `remote_fallback` fields.
  - **Storage Factory** (`src/scribe_mcp/storage/__init__.py` - MODIFY): Add `remote` case to `create_storage_backend()`.
  - **Server Startup** (`src/scribe_mcp/server.py` - MODIFY): Call `detect_operating_mode()` in `_startup()` before `storage_backend.setup()`.

- **Data Flow:**
  1. Claude Code sends JSON-RPC tool call via stdio
  2. Local Scribe receives via mcp_stdio transport
  3. `execute_tool_call()` runs middleware — session resolution uses LOCAL in-memory cache (0 remote calls)
  4. Tool function executes, reads/writes local .scribe/ filesystem as needed
  5. Tool calls `storage_backend.method()` for DB operations
  6. RemoteStorageBackend serializes call as HTTP POST to Hetzner `/api/v1/backend/{operation}`
  7. Hetzner server deserializes, calls local PostgresStorage, returns result
  8. RemoteStorageBackend returns deserialized result to tool
  9. Tool formats response, sends back via stdio

- **External Integrations:**
  - Hetzner Scribe SSE server (existing, :8200)
  - Tailscale mesh network (existing, provides connectivity)
  - CortaStore (existing, client talks directly for object store sync)
  - PostgreSQL (existing, accessed only by server mode)
<!-- ID: detailed_design -->
### 4.1 RemoteStorageBackend (`src/scribe_mcp/storage/remote.py` - NEW)

**Purpose:** Implement `StorageBackend` ABC, proxy persistent data operations to Hetzner Scribe REST API, handle session operations locally in-memory.

**Class Design:**
```python
class RemoteStorageBackend(StorageBackend):
    def __init__(self, server_url: str, *, timeout: float = 30.0):
        self._server_url = server_url.rstrip("/")
        self._client: httpx.AsyncClient  # Created in setup()
        self._timeout = timeout
        # Local session cache (in-memory, per-process)
        self._sessions: dict[str, dict] = {}        # session_id -> session data
        self._session_projects: dict[str, str] = {}  # session_id -> project_name
        self._session_modes: dict[str, str] = {}     # session_id -> mode
        self._agent_sessions: dict[str, str] = {}    # identity_key -> stable_session_id
        self._project_cache: dict[str, ProjectRecord] = {}  # name -> ProjectRecord (TTL 60s)
```

**Method Classification:**

| Category | Methods | Implementation |
|----------|---------|---------------|
| **Remote (HTTP proxy)** | `upsert_project`, `fetch_project`, `list_projects`, `list_projects_by_repo`, `delete_project`, `update_project_docs`, `insert_entry`, `fetch_recent_entries`, `fetch_recent_entries_paginated`, `count_entries`, `query_entries`, `query_entries_paginated`, `count_query_entries`, `upsert_dev_plan`, `cleanup_old_entries`, `record_doc_change`, `record_agent_report_card` | HTTP POST to `/api/v1/backend/{method}` |
| **Local (in-memory)** | `upsert_session`, `set_session_mode`, `get_session_mode`, `set_session_project`, `get_session_project`, `get_session_by_transport`, `upsert_agent_recent_project`, `get_or_create_agent_session`, `update_session_activity`, `get_session_activity`, `heartbeat_session`, `end_session` | In-memory dicts, no network |
| **Agent management** | `upsert_agent_session`, `get_agent_project`, `set_agent_project` | Remote for project data, local for session |
| **Bridge (no-op)** | `insert_bridge`, `update_bridge_state`, `update_bridge_health`, `fetch_bridge`, `list_bridges`, `delete_bridge` | No-op stubs (bridges are server-side only) |
| **Lifecycle** | `setup`, `close` | Create/close httpx.AsyncClient |

**HTTP Call Pattern:**
```python
async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
    resp = await self._client.post(
        f"{self._server_url}/api/v1/backend/fetch_project",
        json={"name": name},
        timeout=self._timeout,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    return ProjectRecord(**data["result"]) if data.get("result") else None
```

**Batch Pattern (for set_project):**
```python
async def execute_batch(self, operations: list[dict]) -> list[dict]:
    """Send multiple storage operations in a single HTTP call."""
    resp = await self._client.post(
        f"{self._server_url}/api/v1/batch",
        json={"operations": operations},
        timeout=self._timeout * 2,  # Batch may take longer
    )
    resp.raise_for_status()
    return resp.json()["results"]
```

**Error Handling:**
- HTTP 4xx → raise ValueError with server error message
- HTTP 5xx → raise RuntimeError with "Remote Scribe server error"
- Connection error → raise `RemoteUnavailableError(msg)` (new exception in storage/base.py)
- Timeout → raise `RemoteUnavailableError("timeout")`

---

### 4.2 Server REST API (`src/scribe_mcp/server_sse.py` - MODIFY)

**Purpose:** Expose StorageBackend methods as HTTP endpoints on the existing Starlette ASGI app. Only active when running in server/SSE mode.

**Endpoint Design:**

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| POST | `/api/v1/backend/{operation}` | `{"args": {...}}` | `{"result": ...}` | Execute single StorageBackend method |
| POST | `/api/v1/batch` | `{"operations": [{"op": "method_name", "args": {...}}, ...]}` | `{"results": [...]}` | Execute batch of operations sequentially |
| GET | `/health` | - | `{"status": "healthy", ...}` | Existing health check (no change) |

**Server-side handler:**
```python
async def handle_backend_operation(request: Request) -> JSONResponse:
    operation = request.path_params["operation"]
    body = await request.json()
    backend = server_module.storage_backend  # Same singleton used by tools
    method = getattr(backend, operation, None)
    if not method or operation.startswith("_"):
        return JSONResponse({"error": f"Unknown operation: {operation}"}, status_code=400)
    try:
        result = await method(**body.get("args", {}))
        return JSONResponse({"result": _serialize(result)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
```

**Batch handler:**
```python
async def handle_batch(request: Request) -> JSONResponse:
    body = await request.json()
    results = []
    for op in body["operations"]:
        method = getattr(backend, op["op"], None)
        try:
            result = await method(**op.get("args", {}))
            results.append({"ok": True, "result": _serialize(result)})
        except Exception as e:
            results.append({"ok": False, "error": str(e)})
    return JSONResponse({"results": results})
```

**Serialization:** `ProjectRecord` dataclass is serialized to dict. Entry dicts pass through as-is. `_serialize()` handles dataclass-to-dict conversion.

**Route Registration (added to existing Starlette routes):**
```python
starlette_app = Starlette(routes=[
    Route("/health", health_check),
    Route("/sse", handle_sse),
    Mount("/messages/", app=sse_transport.handle_post_message),
    # NEW: Backend API for remote client mode
    Route("/api/v1/backend/{operation}", handle_backend_operation, methods=["POST"]),
    Route("/api/v1/batch", handle_batch, methods=["POST"]),
])
```

---

### 4.3 Mode Detection (`src/scribe_mcp/config/mode_detection.py` - NEW)

```python
from enum import Enum

class OperatingMode(Enum):
    SERVER = "server"       # Mode A: Direct DB access
    CLIENT = "client"       # Mode B: Proxy to remote server
    STANDALONE = "standalone"  # Mode C: Local SQLite only

async def detect_operating_mode(settings) -> OperatingMode:
    explicit = os.environ.get("SCRIBE_MODE", "auto").lower()
    if explicit in ("server", "client", "standalone"):
        return OperatingMode(explicit)

    remote_url = getattr(settings, "remote_server_url", None)
    if remote_url:
        reachable = await _probe_remote(remote_url, timeout=settings.remote_connect_timeout)
        if reachable:
            return OperatingMode.CLIENT
        if settings.remote_fallback:
            logger.warning("Remote %s unreachable, falling back to standalone", remote_url)
            return OperatingMode.STANDALONE
        raise RuntimeError(f"Remote Scribe at {remote_url} unreachable and fallback disabled")

    if settings.db_url:
        return OperatingMode.SERVER

    return OperatingMode.STANDALONE
```

---

### 4.4 Settings Extension (`src/scribe_mcp/config/settings.py` - MODIFY)

New fields in Settings dataclass:

| Field | Env Var | Default | Purpose |
|-------|---------|---------|---------|
| `remote_server_url` | `SCRIBE_REMOTE_URL` | `None` | Remote Scribe server base URL |
| `mode` | `SCRIBE_MODE` | `"auto"` | Override mode detection |
| `remote_connect_timeout` | `SCRIBE_REMOTE_CONNECT_TIMEOUT` | `3.0` | Startup health probe timeout |
| `remote_fallback` | `SCRIBE_REMOTE_FALLBACK` | `True` | Fall back to SQLite if remote unreachable |

---

### 4.5 Storage Factory Modification (`src/scribe_mcp/storage/__init__.py` - MODIFY)

```python
def create_storage_backend(mode: Optional[OperatingMode] = None) -> Optional[StorageBackend]:
    from scribe_mcp.config.settings import settings

    if mode == OperatingMode.CLIENT:
        from scribe_mcp.storage.remote import RemoteStorageBackend
        return RemoteStorageBackend(settings.remote_server_url, timeout=settings.storage_timeout)

    # Existing logic for SERVER and STANDALONE modes...
    backend_name = settings.storage_backend
    if backend_name == "postgres" and settings.db_url:
        from scribe_mcp.storage.postgres import PostgresStorage
        return PostgresStorage(...)
    # ... etc (unchanged)
```

---

### 4.6 Server Startup Modification (`src/scribe_mcp/server.py` - MODIFY)

Modify `_startup()` to detect mode before initializing storage:

```python
async def _startup() -> None:
    global storage_backend, _startup_complete, _operating_mode
    if _startup_complete:
        return

    from scribe_mcp.config.mode_detection import detect_operating_mode, OperatingMode
    _operating_mode = await detect_operating_mode(settings)
    logger.info("Operating mode: %s", _operating_mode.value)

    if _operating_mode == OperatingMode.CLIENT:
        # In client mode, replace the module-level storage_backend
        from scribe_mcp.storage.remote import RemoteStorageBackend
        storage_backend = RemoteStorageBackend(settings.remote_server_url)

    if storage_backend:
        await storage_backend.setup()
    # ... rest of startup unchanged
```

---

### 4.7 Session Cache Design (In-Memory)

The execute_tool_call() middleware makes 5-7 DB calls for session resolution. In client mode, RemoteStorageBackend handles these locally:

```python
# These methods return from local dict, no network call:
async def get_session_by_transport(self, transport_id: str) -> Optional[dict]:
    return self._sessions.get(transport_id)

async def upsert_session(self, *, session_id, transport_session_id=None, **kwargs):
    self._sessions[transport_session_id or session_id] = {
        "session_id": session_id, **kwargs
    }

async def get_session_project(self, session_id: str) -> Optional[str]:
    return self._session_projects.get(session_id)

async def set_session_project(self, session_id: str, project_name: str):
    self._session_projects[session_id] = project_name

async def get_or_create_agent_session(self, *, identity_key, **kwargs) -> str:
    if identity_key not in self._agent_sessions:
        self._agent_sessions[identity_key] = str(uuid4())
    return self._agent_sessions[identity_key]
```

**Impact:** Every tool call saves 5-7 network roundtrips (250-1400ms) by using local session cache. This is the single biggest latency win outside of the batch endpoint.

---

### 4.8 base.py Interface Cleanup

Before implementing RemoteStorageBackend, promote extended methods to `StorageBackend` base class as optional (raise NotImplementedError):

Methods to add to base.py:
- `upsert_session()`
- `set_session_mode()` / `get_session_mode()`
- `set_session_project()` / `get_session_project()`
- `get_session_by_transport()`
- `upsert_agent_recent_project()`
- `get_or_create_agent_session()`
- `upsert_dev_plan()`
- `update_session_activity()` / `get_session_activity()`

This ensures RemoteStorageBackend can properly implement the full interface without relying on duck-typing.
<!-- ID: directory_structure -->
```
src/scribe_mcp/
  config/
    settings.py          # MODIFY: Add remote_server_url, mode, remote_connect_timeout, remote_fallback
    mode_detection.py    # NEW: OperatingMode enum + detect_operating_mode() function
    paths.py             # EXISTING: map_client_root() already handles path mapping
  storage/
    __init__.py          # MODIFY: Add 'remote' case to create_storage_backend()
    base.py              # MODIFY: Add extended methods as abstract/optional stubs
    remote.py            # NEW: RemoteStorageBackend class (~400 lines estimated)
    sqlite/              # EXISTING: No changes needed
    postgres/             # EXISTING: No changes needed
  server.py              # MODIFY: Call detect_operating_mode() in _startup()
  server_sse.py          # MODIFY: Add /api/v1/backend/* and /api/v1/batch routes
  transport/
    http_sse.py          # EXISTING SCAFFOLD: NOT used in this design (REST API is simpler)
  shared/
    tool_runtime.py      # NO CHANGES: Session cache in RemoteStorageBackend handles middleware
  tools/                 # NO CHANGES: Storage layer abstraction means zero tool modifications

tests/
  test_remote_backend.py    # NEW: Unit tests for RemoteStorageBackend with respx HTTP mocks
  test_mode_detection.py    # NEW: Unit tests for mode detection logic
  test_server_api.py        # NEW: Integration tests for /api/v1/* endpoints
  conftest.py              # MODIFY: Add pytest markers (client_proxy, e2e)

.env                        # MODIFY: Add SCRIBE_MODE, SCRIBE_REMOTE_URL for client mode
pyproject.toml             # MODIFY: Add optional [server] dependency group (future phase)
```

**File Change Summary:**

| File | Action | Estimated Lines Changed |
|------|--------|------------------------|
| `src/scribe_mcp/storage/remote.py` | CREATE | ~400-500 lines |
| `src/scribe_mcp/config/mode_detection.py` | CREATE | ~80 lines |
| `src/scribe_mcp/storage/base.py` | MODIFY | ~60 lines added (method stubs) |
| `src/scribe_mcp/storage/__init__.py` | MODIFY | ~10 lines added |
| `src/scribe_mcp/config/settings.py` | MODIFY | ~15 lines added |
| `src/scribe_mcp/server.py` | MODIFY | ~20 lines modified |
| `src/scribe_mcp/server_sse.py` | MODIFY | ~80 lines added |
| `tests/test_remote_backend.py` | CREATE | ~200 lines |
| `tests/test_mode_detection.py` | CREATE | ~100 lines |
| `tests/test_server_api.py` | CREATE | ~150 lines |
| **Total** | | **~1100-1200 lines** |
<!-- ID: data_storage -->
- **Data Locality:**

  | Data Type | Mode A (Server) | Mode B (Client) | Mode C (Standalone) |
  |-----------|-----------------|-----------------|---------------------|
  | Project metadata (DB rows) | Local Postgres | Remote (proxied via REST) | Local SQLite |
  | Log entries (DB rows) | Local Postgres | Remote (proxied via REST) | Local SQLite |
  | Progress log (.md files) | Local filesystem | Local filesystem | Local filesystem |
  | Managed docs (.md files) | Local filesystem | Local filesystem | Local filesystem |
  | .scribe/config/ | Local filesystem | Local filesystem | Local filesystem |
  | Session state | Local DB | Local in-memory dict | Local DB |
  | ProjectRegistry cache | Local SQLite | Local SQLite (unchanged) | Local SQLite |
  | CortaStore sync | Direct HTTP | Direct HTTP (unchanged) | N/A |

- **RemoteStorageBackend Caching:**
  - `_project_cache`: dict[str, (ProjectRecord, float)] with 60-second TTL
  - Cache invalidated on `upsert_project()` and `delete_project()` calls
  - Session cache has no TTL (in-memory per-process, cleared on restart)
  - No persistent local cache — RemoteStorageBackend does not write to local SQLite

- **Serialization Format:**
  - All REST API requests/responses use JSON
  - `ProjectRecord` dataclass serialized via `dataclasses.asdict()` on server, reconstructed on client
  - Entry dicts pass through as-is (already JSON-serializable)
  - Timestamps serialized as ISO 8601 strings

- **Migrations:**
  - No new database tables needed
  - No schema changes required
  - Server-side Postgres migrations continue to self-apply on startup (existing behavior)
  - Client mode does not run any migrations (no local DB access needed)
<!-- ID: testing_strategy -->
- **Unit Tests (RemoteStorageBackend):**
  - Use `respx` library to mock HTTP calls to /api/v1/backend/*
  - Test all remote methods return correct ProjectRecord/entry types
  - Test session cache methods work in-memory without HTTP
  - Test error handling: 4xx, 5xx, timeout, connection refused
  - Test batch endpoint serialization/deserialization
  - Marker: `@pytest.mark.client_proxy`

- **Unit Tests (Mode Detection):**
  - Test explicit SCRIBE_MODE overrides (server, client, standalone)
  - Test auto-detection with remote URL set + reachable
  - Test auto-detection with remote URL set + unreachable + fallback enabled
  - Test auto-detection with remote URL set + unreachable + fallback disabled (should raise)
  - Test auto-detection with db_url set (server mode)
  - Test default (no URL, no DB) returns standalone
  - Mock httpx for health probe testing

- **Integration Tests (Server API):**
  - Start Starlette test client (httpx.ASGITransport)
  - Test /api/v1/backend/fetch_project with real SQLiteStorage backend
  - Test /api/v1/batch with multiple operations
  - Test error responses for unknown operations
  - Test serialization roundtrip: ProjectRecord -> JSON -> ProjectRecord
  - Marker: `@pytest.mark.server_api`

- **End-to-End Tests (Future Phase):**
  - Start local SSE server in pytest fixture
  - Create RemoteStorageBackend pointing to local SSE server
  - Run set_project through full pipeline
  - Verify round-trip data consistency
  - Marker: `@pytest.mark.e2e`

- **Existing Test Compatibility:**
  - All existing tests continue to use SQLiteStorage (no regression)
  - New tests added alongside existing, never replacing
  - `conftest.py` updated with new markers only

- **Observability:**
  - RemoteStorageBackend logs each HTTP call at DEBUG level: method, URL, status, latency
  - Batch calls log operation count and total latency
  - Mode detection logs resolved mode at INFO level
  - Connection failures logged at WARNING level
<!-- ID: deployment_operations -->
- **Mode A (Server) — Hetzner Docker:**
  - No deployment changes needed. Existing docker-compose.scribe.yaml continues to work.
  - New /api/v1/* routes are automatically available when server starts in SSE mode.
  - Routes are part of the Starlette app, no additional configuration needed.

- **Mode B (Client) — Local Dev Machine:**
  - Update `.env` to add:
    ```
    SCRIBE_MODE=client
    SCRIBE_REMOTE_URL=http://council-hub:8200
    SCRIBE_REMOTE_CONNECT_TIMEOUT=3.0
    SCRIBE_REMOTE_FALLBACK=true
    ```
  - Remove or comment out:
    ```
    # SCRIBE_STORAGE_BACKEND=postgres
    # SCRIBE_DB_URL=postgresql://...
    ```
  - `.claude.json` change is optional (`.env` takes precedence due to override=True)

- **Mode C (Standalone) — Offline:**
  - Set `SCRIBE_MODE=standalone` in `.env` (or just remove all remote/postgres config)
  - Uses local SQLite at `data/scribe_projects.db`

- **Configuration Management:**
  - `.env` is the primary config source (load_dotenv(override=True))
  - All new env vars have safe defaults (auto mode, fallback enabled)
  - No mandatory config changes to switch modes — just add SCRIBE_REMOTE_URL

- **Rollback:**
  - To revert to direct Postgres mode: remove SCRIBE_MODE and SCRIBE_REMOTE_URL from .env
  - Server deployment: same as current (git pull + docker compose build + up)
  - No database migration to roll back

- **CI/CD (Future Phase 6):**
  - GitHub Actions pipeline: test -> build -> deploy
  - Tests run in standalone mode (SQLite, no remote needed)
  - Deploy via SSH to council-hub (existing manual process, automated)
  - Health check verification after deploy
<!-- ID: open_questions -->
| Item | Owner | Status | Decision |
|------|-------|--------|----------|
| REST API authentication? | Architect | DECIDED | Defer to future phase. Tailscale provides network-level trust. Add optional HMAC header support in v2 if needed. |
| .env override=True behavior? | Architect | DECIDED | Keep current behavior. Document that SCRIBE_MODE must be in .env. Users who want .claude.json to control mode must also update .env. |
| Mid-session fallback? | Architect | DECIDED | NO. Hard fail on remote disconnect. No split-brain. User restarts MCP to retry. |
| scribe-client entry point? | Architect | DECIDED | Not needed. Same `scribe-mcp` entry point with SCRIBE_MODE=client. Reduces confusion. |
| Dependency split timing? | Architect | DEFERRED | Phase 6. Splitting pyproject.toml deps into client/server groups is orthogonal to the core client/server split. Do it after MVP works. |
| ProjectRegistry in client mode? | Architect | DECIDED | Keep as-is. Already local SQLite only. No changes needed. |
| Persistent SSE vs REST per-call? | Architect | DECIDED | REST per-call with httpx connection pooling. Simpler than maintaining persistent SSE. Connection pool amortizes TCP handshake overhead. |
| record_tool() in client mode? | Architect | DECIDED | Skip entirely. Session activity tracking is server-side analytics, not needed by client. |

Close each question once answered and reference the relevant section above.
<!-- ID: references_appendix -->
- **Research Documents:**
  - RESEARCH_TOOL_CLASSIFICATION_20260217.md — Tool inventory and DB roundtrip analysis
  - RESEARCH_TRANSPORT_PROXY_20260217.md — Transport architecture and proxy options
  - RESEARCH_STORAGE_BACKEND_20260217.md — StorageBackend interface catalog
  - RESEARCH_MODE_DETECTION_20260217.md — Operating modes and configuration
  - RESEARCH_CICD_DEPLOYMENT_20260217.md — Deployment and CI/CD analysis

- **Key Source Files:**
  - `src/scribe_mcp/storage/base.py` — StorageBackend ABC (33 methods, 420 lines)
  - `src/scribe_mcp/storage/__init__.py` — Backend factory (50 lines)
  - `src/scribe_mcp/shared/tool_runtime.py` — execute_tool_call middleware (378 lines)
  - `src/scribe_mcp/server.py` — Server startup, storage_backend singleton (992 lines)
  - `src/scribe_mcp/server_sse.py` — Starlette ASGI app (155 lines)
  - `src/scribe_mcp/config/settings.py` — Settings dataclass (313 lines)
  - `src/scribe_mcp/transport/http_sse.py` — Transport scaffold (32 lines, NOT used)

- **External References:**
  - `council_mcp/src/council_mcp/web/mcp_client.py` — MCPSSEClient reference (not used directly, but design patterns referenced)
  - `council_mcp/src/council_mcp/tools/scribe_proxy.py` — MCP-to-MCP proxy reference
  - httpx documentation: https://www.python-httpx.org/async/

- **Latency Targets:**
  - set_project: 3+ seconds (current) -> <500ms (target) = 6x improvement minimum
  - Per-tool middleware: 250-1400ms (current) -> 0ms (local session cache) = eliminated
  - append_entry: ~100ms (current) -> ~100ms (unchanged, file-first design already optimal)

Generated by ArchitectAgent-ClientServerSplit, 2026-02-17.
