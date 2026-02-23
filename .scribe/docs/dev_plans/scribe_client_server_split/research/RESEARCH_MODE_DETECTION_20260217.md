# RESEARCH: Mode Detection, Configuration & Graceful Fallback

**Date**: 2026-02-17
**Analyst**: ResearchAnalyst-ModeDetection
**Project**: scribe_client_server_split
**Research Goal**: Design mode detection logic, configuration approach, and graceful fallback chain for the Scribe MCP client/server split.

---

## Executive Summary

The current Scribe MCP (stdio, local) always connects to a remote Postgres database on Hetzner (`council-hub:5432`) because `.env` hardcodes this. This causes 3+ minute startup latency due to TCP connection setup, schema migration, and asyncpg pool initialization over Tailscale.

The solution is a **three-mode operating model**:
- **Mode A: Full Server** — existing behavior, direct DB access (Postgres or SQLite)
- **Mode B: Lightweight Client** — detects remote Scribe SSE server, proxies DB ops to it
- **Mode C: Local Standalone** — SQLite only, no remote, truly offline

Critically, NO existing mode detection infrastructure exists. Everything must be built from scratch, but the architecture is clean and insertion points are clear.

---

## 1. Current Configuration System (VERIFIED)

### 1.1 Environment Variables Inventory

All variables from `src/scribe_mcp/config/settings.py` (lines 100-295):

#### Storage Configuration
| Variable | Default | Current .env Value | Effect |
|----------|---------|-------------------|--------|
| `SCRIBE_STORAGE_BACKEND` | `postgres` if DB_URL set, else `sqlite` | `postgres` | Forces postgres backend |
| `SCRIBE_DB_URL` | None | `postgresql://scribe_app:...@council-hub:5432/agentkit` | Remote Hetzner postgres |
| `SCRIBE_POSTGRES_SCHEMA` | `scribe` | `scribe` | DB schema name |
| `SCRIBE_DB_PATH` / `SCRIBE_SQLITE_PATH` | `data/scribe_projects.db` | (unset) | Local SQLite path |
| `SCRIBE_POSTGRES_POOL_MIN_SIZE` | `2` | (unset) | Min pool connections |
| `SCRIBE_POSTGRES_POOL_MAX_SIZE` | `20` | (unset) | Max pool connections |
| `SCRIBE_POSTGRES_COMMAND_TIMEOUT_SECONDS` | `30` | (unset) | Query timeout |
| `SCRIBE_POSTGRES_CONNECT_TIMEOUT_SECONDS` | `10` | (unset) | Per-connection timeout |
| `SCRIBE_POSTGRES_CONNECT_RETRIES` | `3` | (unset) | Retry attempts |
| `SCRIBE_POSTGRES_CONNECT_RETRY_BACKOFF_SECONDS` | `1.0` | (unset) | Retry backoff |

#### Path Configuration
| Variable | Default | Effect |
|----------|---------|--------|
| `SCRIBE_ROOT` | Inferred from package | Repo root, also used for path mapping |
| `SCRIBE_DATA_DIR` | `<SCRIBE_ROOT>/data` | Where SQLite DB lives |
| `SCRIBE_STATE_PATH` | `<root>/.scribe/state.json` | Legacy state (deprecated) |
| `SCRIBE_DEV_PLANS_BASE` | `.scribe/docs/dev_plans` | Dev plan directory |
| `SCRIBE_PATH_MAP` | None | Client-to-server path mapping (semicolon-separated `client=server` pairs) |

#### Transport Configuration
| Variable | Default | Effect |
|----------|---------|--------|
| `SCRIBE_TRANSPORT` | `stdio` | `stdio` or `sse` |
| `SCRIBE_TRANSPORT_PORT` | `8200` | Port for SSE |
| `SCRIBE_TRANSPORT_HOST` | `0.0.0.0` | Host for SSE |

#### Object Store Configuration
| Variable | Default | Current .env Value | Effect |
|----------|---------|-------------------|--------|
| `SCRIBE_OBJECT_STORE_URL` | None | `http://council-hub:8201` | CortaStore on Hetzner |
| `SCRIBE_OBJECT_STORE_PROVIDER` | `corta` | `corta` | Provider type |
| `SCRIBE_OBJECT_STORE_KEY` | None | HMAC key | Auth for CortaStore |
| `SCRIBE_OBJECT_STORE_PROJECT` | None | `scribe` | CortaStore namespace |
| `SCRIBE_OBJECT_STORE_TIMEOUT` | `10.0` | (unset) | HTTP timeout |

#### Other Key Variables
| Variable | Default | Effect |
|----------|---------|--------|
| `SCRIBE_ALLOW_NETWORK` | `false` | Network access flag |
| `SCRIBE_USER` | (unset) | User identity for workspace scoping |
| `SCRIBE_DEFAULT_PROJECT` | (unset) | Default project |
| `SCRIBE_STORAGE_TIMEOUT_SECONDS` | `5` | Tool-level storage timeout |
| `SCRIBE_REMINDER_IDLE_MINUTES` | `45` | Reminder idle threshold |
| `SCRIBE_REQUIRE_EXPLICIT_ROOT` | `true` | Root validation |

### 1.2 .env Loading (VERIFIED)

File: `src/scribe_mcp/config/settings.py` lines 13-21:
```python
from dotenv import load_dotenv
_dotenv_path = repo_root() / ".env"
load_dotenv(_dotenv_path, override=True)  # .env is source of truth; override parent env
```

**Key finding**: `.env` is loaded with `override=True`, meaning `.env` always wins over system env vars. This is the recent fix. Consequence: if you change `.env`, MCP restart picks it up. If Tailscale is down and `.env` points to `council-hub:5432`, startup BLOCKS for 36 seconds (3 retries x 10s timeout + backoff).

### 1.3 Current .env (Local Dev)

File: `/home/austin/projects/MCP_SPINE/scribe_mcp/.env`

Critical entries:
```bash
SCRIBE_STORAGE_BACKEND=postgres
SCRIBE_DB_URL=postgresql://scribe_app:J0TGXyJkxNtMVp6a5vxHQT8QaSGNpQaj@council-hub:5432/agentkit
SCRIBE_POSTGRES_SCHEMA=scribe
SCRIBE_OBJECT_STORE_URL=http://council-hub:8201
SCRIBE_USER=austin
```

**Assessment**: This is a "Full Server" config that works when Tailscale is up, but causes massive latency because the local Scribe directly connects to remote Postgres. The client/server split would proxy this through the remote Scribe SSE server instead.

### 1.4 .claude.json Scribe MCP Config (VERIFIED)

File: `/home/austin/.claude.json`, mcpServers.scribe section:
```json
{
  "scribe": {
    "type": "stdio",
    "command": "bash",
    "args": ["-lc", "cd /home/austin/projects/MCP_SPINE/scribe_mcp && exec python -m server"],
    "env": {
      "SCRIBE_ROOT": "/home/austin/projects/MCP_SPINE/scribe_mcp",
      "SCRIBE_STORAGE_BACKEND": "postgres",
      "SCRIBE_DB_URL": "postgresql://scribe_app:...@council-hub:5432/agentkit",
      "SCRIBE_POSTGRES_SCHEMA": "scribe"
    }
  }
}
```

**Note**: The env vars in `.claude.json` are **overridden by .env** because `load_dotenv(override=True)` runs first. This means `.claude.json` env vars are largely redundant for the Scribe process. The `.env` file is the true config source.

**Note on command**: The command is `python -m server` but should likely be `python -m scribe_mcp` given the package structure. This may be a legacy config.

---

## 2. Latency Root Cause (VERIFIED)

### 2.1 Module-Level Backend Creation

File: `src/scribe_mcp/server.py`, line 116:
```python
storage_backend = create_storage_backend()  # Eagerly creates backend at module import
```

This is called at module load time, before `_startup()`. The backend object is created but NOT connected yet. Connection happens in `_startup()` line 747:
```python
await storage_backend.setup()  # This triggers asyncpg pool creation over Tailscale
```

### 2.2 Postgres Pool Init Delays

File: `src/scribe_mcp/storage/postgres/internals.py`:
- `CONNECT_TIMEOUT_SECONDS = 10.0` per attempt
- `CONNECT_RETRIES = 3` (4 total attempts)
- `CONNECT_RETRY_BACKOFF_SECONDS = 1.0` (exponential: 2s, 4s, 8s)
- `POOL_MIN_SIZE = 2` - two connections established at pool creation

Worst-case: 10s + 10s+2s + 10s+4s + 10s+8s = **54 seconds** max wait for failed connection.

### 2.3 Schema Migration Overhead

During `storage_backend.setup()`, schema migration SQL runs over Tailscale. Each SQL statement is a separate round-trip. With 50ms Tailscale RTT, 17-20 statements = 850-1000ms additional latency.

### 2.4 Impact

Every startup of the Scribe MCP stdio process (triggered by Claude Code) requires waiting for remote Postgres connection. The `set_project` call taking 3+ minutes is because:
1. Startup waits for pool creation
2. Schema migration runs
3. First `set_project` query executes

---

## 3. Mode Definitions (PROPOSED)

### Mode A: Full Server (Current Behavior)

**Trigger**: Has direct DB access configured (Postgres DSN or SQLite path), NO remote Scribe server configured.

**Behavior**:
- Handles ALL storage locally (Postgres or SQLite)
- Handles ALL filesystem ops locally
- Object store syncs docs to CortaStore (optional)
- This is what the Hetzner scribe container runs
- This is what local dev runs today (minus the client/server optimization)

**Config signature**:
```bash
SCRIBE_DB_URL=postgresql://...    # OR no URL (sqlite fallback)
# SCRIBE_REMOTE_SERVER_URL NOT set (or set to empty)
```

### Mode B: Lightweight Client (NEW)

**Trigger**: `SCRIBE_REMOTE_SERVER_URL` is set AND remote server is reachable.

**Behavior**:
- Connects to remote Scribe SSE server at `SCRIBE_REMOTE_SERVER_URL`
- Proxies ALL DB operations (append_entry, set_project, list_projects, etc.) to remote via HTTP/SSE
- Handles filesystem ops LOCALLY (read_file, edit_file, manage_docs filesystem writes)
- Does NOT initialize local Postgres pool on startup
- Startup time drops from 3+ minutes to ~100ms
- Object store: client can talk to CortaStore directly OR proxy through server

**Config signature**:
```bash
SCRIBE_REMOTE_SERVER_URL=http://council-hub:8200  # NEW env var
# SCRIBE_DB_URL not needed (or ignored in client mode)
```

### Mode C: Local Standalone (NEW)

**Trigger**: Neither `SCRIBE_REMOTE_SERVER_URL` reachable NOR `SCRIBE_DB_URL` set for postgres, OR explicit `SCRIBE_MODE=standalone`.

**Behavior**:
- Uses local SQLite for ALL storage
- No remote connections
- Full functionality but isolated from shared state
- Startup time: <500ms (SQLite file open only)

**Config signature**:
```bash
SCRIBE_STORAGE_BACKEND=sqlite  # OR no postgres URL
# SCRIBE_REMOTE_SERVER_URL not set
```

---

## 4. Proposed Mode Detection Logic

### 4.1 New Environment Variables

| Variable | Default | Purpose |
|----------|---------|----------|
| `SCRIBE_REMOTE_SERVER_URL` | None | Remote Scribe SSE server URL. When set, enables client mode. Example: `http://council-hub:8200` |
| `SCRIBE_MODE` | `auto` | Override mode detection. Values: `auto`, `server`, `client`, `standalone` |
| `SCRIBE_REMOTE_CONNECT_TIMEOUT` | `3.0` | Timeout in seconds for remote server health check at startup |
| `SCRIBE_REMOTE_FALLBACK` | `true` | If `true`, fall back to local mode when remote is unreachable |
| `SCRIBE_REMOTE_RETRY_INTERVAL` | `60` | Seconds between remote reconnection attempts in runtime |

### 4.2 Detection Algorithm

```python
async def detect_operating_mode(settings: Settings) -> OperatingMode:
    """
    Determine which operating mode to use at startup.
    
    Priority order:
    1. SCRIBE_MODE=explicit → use that mode directly
    2. SCRIBE_REMOTE_SERVER_URL set → probe health, use client if reachable
    3. SCRIBE_DB_URL set → use server mode (existing behavior)
    4. Default → standalone SQLite
    """
    explicit_mode = os.environ.get("SCRIBE_MODE", "auto").lower()
    
    if explicit_mode == "server":
        return OperatingMode.SERVER
    elif explicit_mode == "client":
        return OperatingMode.CLIENT  
    elif explicit_mode == "standalone":
        return OperatingMode.STANDALONE
    
    # Auto-detection
    remote_url = settings.remote_server_url  # new field
    if remote_url:
        reachable = await _probe_remote_server(remote_url, timeout=settings.remote_connect_timeout)
        if reachable:
            return OperatingMode.CLIENT
        elif settings.remote_fallback:
            logger.warning("Remote Scribe at %s unreachable, falling back to local mode", remote_url)
            return OperatingMode.STANDALONE  # or SERVER if db_url available
        else:
            raise RuntimeError(f"Remote Scribe at {remote_url} is unreachable and fallback disabled")
    
    if settings.db_url:
        return OperatingMode.SERVER  # Postgres
    
    return OperatingMode.STANDALONE  # SQLite fallback
```

### 4.3 Health Probe (VERIFIED - existing endpoint)

File: `src/scribe_mcp/server_sse.py` lines 53-65:
```python
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "healthy",
        "service": "scribe-mcp",
        "version": "2.2",
        "transport": "sse",
        "uptime_seconds": int(time.time() - _server_start_time) if _server_start_time else 0,
    })
```

Probe implementation:
```python
async def _probe_remote_server(url: str, timeout: float = 3.0) -> bool:
    """Check if remote Scribe server is healthy. Uses existing /health endpoint."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{url.rstrip('/')}/health")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("service") == "scribe-mcp"
    except Exception:
        pass
    return False
```

**Note**: `httpx` is ALREADY a dependency (used in `object_store/providers/corta.py`). No new dependency needed.

---

## 5. .claude.json Configuration Analysis

### 5.1 Current State

Only ONE Scribe entry exists in `.claude.json`, configured as stdio. The Hetzner deployment guide (`.claude/rules/hetzner-deployment.md` line 67-77) shows the INTENDED configuration uses SSE for the remote server:
```json
"scribe": {
  "type": "sse",
  "url": "http://council-hub:8200/sse"
}
```

### 5.2 Client Mode Config Proposal

For **Mode B (lightweight client)**, the `.claude.json` entry changes to:
```json
"scribe": {
  "type": "stdio",
  "command": "python",
  "args": ["-m", "scribe_mcp"],
  "env": {
    "SCRIBE_ROOT": "/home/austin/projects/MCP_SPINE/scribe_mcp",
    "SCRIBE_MODE": "client",
    "SCRIBE_REMOTE_SERVER_URL": "http://council-hub:8200",
    "SCRIBE_REMOTE_CONNECT_TIMEOUT": "3.0",
    "SCRIBE_REMOTE_FALLBACK": "true"
  }
}
```

**Note**: In client mode, `SCRIBE_DB_URL` is NOT needed in `.claude.json`. The local process will NOT open any Postgres connections. DB ops are proxied to the server.

### 5.3 Two Scribe Entries (Optional)

Could have TWO entries for different use cases:
```json
{
  "scribe": {
    "type": "stdio",
    "command": "python",
    "args": ["-m", "scribe_mcp"],
    "env": {
      "SCRIBE_MODE": "client",
      "SCRIBE_REMOTE_SERVER_URL": "http://council-hub:8200",
      "SCRIBE_REMOTE_FALLBACK": "true"
    }
  },
  "scribe-direct": {
    "type": "sse",
    "url": "http://council-hub:8200/sse"
  }
}
```

However, having two Scribe entries could confuse Claude Code. **Recommendation**: Single `scribe` entry in client mode, no separate `scribe-direct`.

---

## 6. Fallback Chain Design

### 6.1 Startup Fallback Chain

```
Startup sequence for Mode B (client):

1. Load settings (.env + env vars)
2. Detect mode:
   a. SCRIBE_REMOTE_SERVER_URL set?
   b. Probe GET /health → 200 OK + service=scribe-mcp?
   c. YES → use ClientMode (local DB ops disabled)
   d. NO + SCRIBE_REMOTE_FALLBACK=true → switch to standalone (SQLite)
   e. NO + SCRIBE_REMOTE_FALLBACK=false → fail with clear error message
3. Initialize storage based on resolved mode
4. Log "Server ready" (Council MCP pattern-matches this)
```

### 6.2 Runtime Fallback (Session-Level)

**Can we switch mid-session?** YES but with caveats:
- If remote becomes unavailable during a session, tool calls will fail at the storage proxy layer
- Options:
  a. **Hard fail**: Return error to Claude, let user restart → simplest, least code
  b. **Automatic fallback to SQLite**: Switch active backend to SQLite for the rest of the session → more complex, possible data split
  c. **Queued writes**: Buffer writes locally, replay when remote returns → complex, risk of data loss

**Recommendation**: Option (a) Hard fail for initial implementation, with clear error message:
```
Error: Remote Scribe server unavailable. Restart MCP to retry connection or set SCRIBE_REMOTE_FALLBACK=true.
```

**Future enhancement**: Option (c) Write journal/queue. The existing `WriteAheadLog` and journal replay machinery (server.py lines 550-589) provides a model for this.

### 6.3 Data Separation (What is Local vs Remote)

| Data Type | Client Mode Storage | Server Mode Storage |
|-----------|---------------------|--------------------|
| Progress log entries (DB rows) | REMOTE (proxied) | LOCAL |
| Project metadata (DB rows) | REMOTE (proxied) | LOCAL |
| .scribe/docs/ filesystem | LOCAL | LOCAL |
| .scribe/config/ | LOCAL | LOCAL |
| Object store sync (CortaStore) | DIRECT (bypass server) | VIA server OR direct |
| Journal/WAL files | LOCAL | LOCAL |
| Session state (agent_sessions) | REMOTE (proxied) | LOCAL |

**Key insight**: Filesystem operations (read_file, edit_file, manage_docs writes) ALWAYS stay local. Only DB row operations (append_entry, set_project, list_projects) need proxying.

---

## 7. Object Store Relationship

### 7.1 Current Object Store Behavior

File: `src/scribe_mcp/object_store/__init__.py`:
- When `SCRIBE_OBJECT_STORE_URL` set → `HybridStore` (local filesystem + CortaStore sync)
- When not set → `FilesystemStore` (local only)
- Sync happens via `sync_file_to_store()` in fire-and-forget background tasks

### 7.2 Object Store in Client Mode

**Option A: Client talks to CortaStore directly** (RECOMMENDED)
- Client has `SCRIBE_OBJECT_STORE_URL=http://council-hub:8201` + HMAC key
- Syncs docs directly to CortaStore without going through the Scribe server
- Simpler architecture, no proxy overhead for large doc uploads
- Already possible with current code

**Option B: Client proxies object store through Scribe server**
- Adds latency for object store operations
- No benefit over Option A
- NOT recommended

**Recommendation**: Keep direct CortaStore access in client mode. The client `.env` should include:
```bash
SCRIBE_OBJECT_STORE_URL=http://council-hub:8201
SCRIBE_OBJECT_STORE_KEY=<hmac_key>
SCRIBE_OBJECT_STORE_PROJECT=scribe
```

---

## 8. Infrastructure Integration Points

### 8.1 Files to Modify (NOT create new replacements - COMMANDMENT #0.5)

| File | Change Needed | Risk |
|------|--------------|------|
| `src/scribe_mcp/config/settings.py` | Add 5 new fields: `remote_server_url`, `mode`, `remote_connect_timeout`, `remote_fallback`, `remote_retry_interval` | Low - additive |
| `src/scribe_mcp/storage/__init__.py` | Modify `create_storage_backend()` to check mode; in client mode return `RemoteProxyBackend` instead | Medium - new class needed |
| `src/scribe_mcp/server.py` | Modify `_startup()` to call mode detection before `storage_backend.setup()` | Medium - startup sequence change |
| `src/scribe_mcp/storage/base.py` | Add abstract `RemoteProxyBackend` class extending `StorageBackend` | Low - new class |

### 8.2 New Files to Create (MINIMAL, justified)

| File | Purpose |
|------|----------|
| `src/scribe_mcp/storage/remote_proxy.py` | `RemoteProxyBackend` implementation — HTTP client that calls remote Scribe server's tool endpoints to execute DB ops |
| `src/scribe_mcp/config/mode_detection.py` | `detect_operating_mode()` function + `OperatingMode` enum |

**RED FLAG AVOIDED**: These are genuinely NEW capabilities, not replacements for existing code. The existing `StorageBackend` class is extended, not replaced.

---

## 9. Remote Proxy Backend Architecture

### 9.1 How to Proxy DB Ops

The remote Scribe server already exposes ALL operations as MCP tools via SSE (`/sse` endpoint) or HTTP POST (`/messages/`). However, the MCP protocol is stateful and complex.

**Simpler approach**: The Hetzner Scribe server also exposes the MCP tool API. We can add a thin REST/HTTP API layer on top for client mode:

```
Option 1: Re-invoke MCP tools via HTTP (complex - MCP protocol overhead)
Option 2: Direct Postgres proxy (expose Postgres over Tailscale - security risk)
Option 3: Thin REST API on Scribe server for common operations (RECOMMENDED)
Option 4: Use existing SSE endpoint but maintain persistent SSE connection
```

**Option 3 Detail**: Add `/api/v1/` HTTP endpoints on the Scribe server for:
- `POST /api/v1/entries` (append_entry)
- `GET /api/v1/entries` (query_entries)
- `POST /api/v1/projects` (set_project)
- `GET /api/v1/projects` (list_projects)
- `GET /api/v1/projects/{name}` (get_project)

These endpoints call through to the existing StorageBackend on the server side.

**Note**: This requires adding API routes to `server_sse.py` (Starlette app). This is additive and follows the existing pattern.

---

## 10. Identified Risks and Open Questions

### 10.1 Risks

1. **Authentication**: The REST API endpoints would be accessible to anyone on Tailscale. Need HMAC auth (same pattern as CortaStore, already have httpx + HMAC code).
   - Confidence: HIGH that auth is needed. Pattern: reuse `corta.py` HMAC signing.

2. **Schema divergence**: If local SQLite fallback is used, schema may diverge from Postgres. Operations that succeed locally may fail when proxied to server.
   - Mitigation: Document that standalone mode is for offline work only; data doesn't sync back automatically.

3. **Session state**: `agent_sessions` table tracks active MCP sessions. In client mode, session state needs to be proxied too or replaced with local-only session management.
   - Confidence: MEDIUM concern. Most session state is per-tool-call, not persistent.

4. **.env override timing**: `load_dotenv(override=True)` runs at settings.py import. If SCRIBE_MODE is in `.claude.json` env but `.env` doesn't have it, `.claude.json` value wins (dotenv only overrides if the var EXISTS in .env).
   - CORRECTION: Actually `override=True` means dotenv ALWAYS wins over the process env, including env set in `.claude.json`. So `.env` must contain `SCRIBE_MODE=client` for client mode to work.
   - **IMPORTANT**: Users must set `SCRIBE_MODE=client` in `.env`, NOT just in `.claude.json`.

5. **Tailscale hostname resolution**: `council-hub` must resolve. If Tailscale is down, DNS fails before TCP. Health probe will fail fast (DNS timeout is ~1s, not 10s).
   - Benefit: Failure mode is fast, not stuck for 36 seconds.

### 10.2 Open Questions for Architect

1. **REST API vs MCP protocol proxy**: Should the proxy use a new REST API (Option 3) or find a way to reuse the MCP SSE protocol? REST is simpler but requires adding routes. MCP proxy preserves exact tool semantics.

2. **Authentication for REST API**: Use existing `SCRIBE_OBJECT_STORE_KEY` for HMAC (sharing key), or introduce a separate `SCRIBE_REMOTE_API_KEY`?

3. **Runtime fallback**: Is hard-fail acceptable for MVP, or must we support seamless mid-session fallback?

4. **`override=True` implications**: Should we change `.env` loading to NOT override, letting `.claude.json` env vars take precedence? This would make `.claude.json` the primary config for mode selection without requiring `.env` edits.

5. **What about the SSE server mode?**: The Hetzner Scribe runs as SSE server. Claude Code could connect directly via `type: sse` in `.claude.json`. This already works. Why not just use that? Answer: the client mode handles LOCAL filesystem ops (read_file, edit_file) which must run on the local machine.

---

## 11. Confidence Assessment

| Finding | Confidence | Basis |
|---------|-----------|-------|
| All env var defaults | 0.99 | Direct code read of settings.py |
| .env current values | 1.00 | Direct file read |
| .claude.json scribe config | 1.00 | Direct file read |
| /health endpoint response shape | 1.00 | Direct code read of server_sse.py:53-65 |
| Latency root cause (pool init) | 0.90 | Code trace, not profiled in production |
| No existing mode detection | 1.00 | Comprehensive search for SCRIBE_REMOTE|proxy|ClientMode |
| httpx already a dependency | 1.00 | Confirmed in corta.py, pyproject.toml assumed |
| Fallback chain design | 0.85 | Proposed, not yet validated by Architect |
| REST API approach | 0.75 | One of several valid options, needs Architect decision |

---

## 12. Handoff to Architect

### Critical Decisions Needed

1. **REST API vs MCP protocol**: Choose proxy mechanism. Research recommends REST API (Option 3).
2. **Override semantics**: Decide if `.env` should continue to use `override=True` or switch to non-override.
3. **Auth approach**: HMAC with existing key or new key.
4. **Runtime fallback**: Hard-fail vs graceful SQLite fallback.

### Implementation Order Recommendation

1. Add `remote_server_url` + `mode` to `Settings` class (settings.py)
2. Create `config/mode_detection.py` with `detect_operating_mode()`
3. Add `/api/v1/` routes to `server_sse.py` (Starlette app)
4. Create `storage/remote_proxy.py` implementing `StorageBackend` via HTTP
5. Modify `storage/__init__.py` `create_storage_backend()` to use `RemoteProxyBackend` in client mode
6. Modify `server.py` `_startup()` to call mode detection before `storage_backend.setup()`
7. Update `.env` with `SCRIBE_MODE=client` + `SCRIBE_REMOTE_SERVER_URL`
8. Update `.claude.json` (or keep `.env` as source of truth)

### Proposed .env for Client Mode

```bash
# Client mode config (lightweight local proxy)
SCRIBE_MODE=client
SCRIBE_REMOTE_SERVER_URL=http://council-hub:8200
SCRIBE_REMOTE_CONNECT_TIMEOUT=3.0
SCRIBE_REMOTE_FALLBACK=true
SCRIBE_ROOT=/home/austin/projects/MCP_SPINE/scribe_mcp
SCRIBE_USER=austin

# Object store - talk to CortaStore directly, not via proxy
SCRIBE_OBJECT_STORE_URL=http://council-hub:8201
SCRIBE_OBJECT_STORE_KEY=<hmac_key>
SCRIBE_OBJECT_STORE_PROJECT=scribe

# NOT needed in client mode (no local postgres)
# SCRIBE_STORAGE_BACKEND=postgres
# SCRIBE_DB_URL=postgresql://...
```

---

## 13. Summary of Infrastructure Gaps (No Speculation)

Items that **do not exist** and **must be built**:

1. `SCRIBE_REMOTE_SERVER_URL` env var — does not exist in settings.py
2. `SCRIBE_MODE` env var — does not exist
3. `detect_operating_mode()` function — does not exist
4. `RemoteProxyBackend` class — does not exist
5. `/api/v1/` REST endpoints on server_sse.py — does not exist
6. Health probe in `_startup()` — does not exist
7. Any client/server split logic anywhere in codebase — CONFIRMED ABSENT

Items that **DO exist** and are **leverageable**:

1. `/health` endpoint at `server_sse.py:53` — clean, minimal, ready to probe
2. `httpx.AsyncClient` pattern — in `corta.py`, copy this pattern
3. HMAC auth pattern — in `corta.py`, reusable
4. `StorageBackend` ABC — in `storage/base.py`, `RemoteProxyBackend` extends this
5. `create_storage_backend()` factory — in `storage/__init__.py`, add client branch here
6. `load_dotenv(override=True)` — settings.py, mode vars go in `.env`
7. Journal/WAL machinery — for future write queue/replay
8. Starlette ASGI app — in `server_sse.py`, add REST routes here
