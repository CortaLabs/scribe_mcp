# RESEARCH: Transport & Proxy Architecture
**Project**: scribe_client_server_split  
**Analyst**: ResearchAnalyst-TransportProxy  
**Date**: 2026-02-17  
**Confidence**: 0.95  

---

## Executive Summary

The core problem: Scribe MCP running locally via stdio makes 17-20 sequential PostgreSQL roundtrips over Tailscale to Hetzner per tool call. At ~150ms per Tailscale RTT, this creates 2-3 second latency for operations like `set_project`. The solution is to proxy DB operations to a Hetzner-resident Scribe instance that has local Postgres access.

**Key Finding**: All infrastructure needed already exists. Council MCP has battle-tested proxy patterns (`MCPSSEClient`, `ScribeProxyClient`) and Scribe already has server-side path mapping (`SCRIBE_PATH_MAP`). The recommended approach is Option B (RemoteStorageBackend) because it is the minimum invasive change with maximum benefit.

---

## 1. Current MCP Transport Architecture

### 1.1 Transport Selection

**File**: `src/scribe_mcp/__main__.py` (61 lines)

Transport is selected via `--transport` CLI arg or `SCRIBE_TRANSPORT` env var:
- `stdio` (default): runs `server.main()` which calls `mcp_stdio.stdio_server()`
- `sse`: runs `server_sse.run_sse()` which starts Starlette/uvicorn on port 8200

Both modes converge on `app.run(read_stream, write_stream, init_options)` — the same `Server` object handles both.

### 1.2 stdio Transport (Lines 971-992 of server.py)

```python
async def main() -> None:
    await _startup()
    async with mcp_stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
```

Key facts:
- `mcp_stdio.stdio_server()` is from MCP Python SDK (`mcp.server.stdio`)
- Returns `(read_stream, write_stream)` as anyio memory streams wrapping stdin/stdout
- Claude Code connects via JSON-RPC 2.0 over stdin/stdout
- Single-session: one Claude Code instance per stdio process
- All `app.run()` calls in both transports are identical — transport is just stream source

### 1.3 SSE Transport (server_sse.py, 155 lines)

```python
sse_transport = SseServerTransport("/messages/")

async def handle_sse(request: Request) -> Response:
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send,
    ) as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
    return Response()

starlette_app = Starlette(routes=[
    Route("/health", health_check),
    Route("/sse", handle_sse),
    Mount("/messages/", app=sse_transport.handle_post_message),
])
```

Endpoints:
- `GET /sse` — persistent SSE stream where server pushes responses
- `POST /messages/` — client posts tool call requests
- `GET /health` — JSON health check for Docker HEALTHCHECK

Multi-session capable: each `/sse` connection gets its own `(read_stream, write_stream)` pair from the SSE transport layer.

### 1.4 Tool Registration & Dispatch

**File**: `src/scribe_mcp/server.py` lines 330-474

```python
# Tool registration via custom decorator:
Server._scribe_tool_registry[tool_name] = target  # Maps name to function
Server._scribe_tool_defs[tool_name] = mcp_types.Tool(...)  # MCP schema

# Dispatch on call_tool() MCP method:
@app.call_tool()
async def _call_tool(name: str, arguments: Dict[str, Any], **kwargs: Any) -> Any:
    return await execute_tool_call(name=name, arguments=dict(arguments or {}), ...)
```

`execute_tool_call()` in `shared/tool_runtime.py` runs the middleware chain (session resolution, mode detection, etc.) and calls the actual tool function.

### 1.5 DB Roundtrip Problem (VERIFIED)

`execute_tool_call()` (tool_runtime.py:185-378) performs these DB queries **before any tool business logic**:

1. `get_session_by_transport` (line 252) — resolve session from transport ID
2. `get_or_create_session_id` via RouterContextManager (line 263)
3. `fetch_project` for repo_root (line 271) — if agent param given
4. `get_session_project` (line 280) — fallback project lookup
5. `fetch_project` again (line 282) — second project resolution
6. `upsert_session` (line 308) — persist session state
7. `get_or_create_agent_session` (line 328) — stable session ID

Then `set_project` itself calls `upsert_project`, `fetch_project`, `update_project_docs` etc. Total of 17-20 roundtrips verified as credible. At 100-200ms Tailscale RTT each: **1.7-4.0 seconds per tool call**.

---

## 2. Existing Proxy Patterns in MCP_SPINE

### 2.1 Council ws_proxy.py — Stdio-to-WebSocket Bridge

**File**: `council_mcp/src/council_mcp/ws_proxy.py` (550+ lines)

Architecture: Claude Code connects via stdio → ws_proxy reads from stdio → forwards to Council daemon's WebSocket endpoint → forwards responses back.

```python
async def run_proxy(url, ...) -> None:
    async with stdio_server() as (local_read, local_write):  # Opens ONCE
        while True:  # WebSocket reconnects on drops
            async with websocket_client_with_keepalive(url) as (remote_read, remote_write):
                await _init_daemon_session(remote_read, remote_write)
                # Bidirectional pipe: local↔remote
                async with anyio.create_task_group() as tg:
                    tg.start_soon(_pipe, local_read, remote_write, ...)
                    tg.start_soon(_pipe, remote_read, local_write, ...)
```

Key design: `stdio_server()` opens ONCE and stays open (Claude Code connection is stable). Only the WebSocket side reconnects. This is critical — never close the local transport.

Also: `_inject_client_id()` mutates `tools/call` JSON-RPC params to inject `_meta.client_id`, `_meta.council_id`, `_meta.workspace` — showing how metadata enrichment works at the proxy layer.

### 2.2 Council scribe_proxy.py — MCP-to-MCP Tool Proxy

**File**: `council_mcp/src/council_mcp/tools/scribe_proxy.py` (217 lines)

The `scribe_call` MCP tool allows any MCP client (web UI, Claude Code) to call Scribe tools through Council:

```python
@mcp.tool()
async def scribe_call(tool_name: str, arguments: dict) -> dict:
    client = _RUNTIME_CONTEXT["scribe_clients"][client_key]
    result = await client.call(tool_name, arguments)
    return {"status": "ok", "result": result}
```

This is a live production implementation of MCP-to-MCP tool forwarding.

### 2.3 MCPSSEClient — SSE Client with Auto-Reconnect

**File**: `council_mcp/src/council_mcp/web/mcp_client.py` (lines 623-778)

```python
class MCPSSEClient:
    async def _sse_keeper(self, ready: asyncio.Event) -> None:
        async with sse_client(self.url) as (read_stream, write_stream):
            self._session = ClientSession(read_stream, write_stream, ...)
            await self._session.initialize()
            self._running = True
            ready.set()
            while self._running:  # Hold connection open
                await asyncio.sleep(1)

    async def call(self, tool_name, arguments, timeout) -> Any:
        result = await self._session.call_tool(
            name=tool_name, arguments=arguments or {},
            read_timeout_seconds=timedelta(seconds=effective_timeout),
        )
        return result.model_dump(by_alias=True, mode="json", exclude_none=True)
```

This is the exact client needed to connect local Scribe to remote Hetzner Scribe.

### 2.4 Path Mapping Infrastructure (ALREADY EXISTS)

**File**: `src/scribe_mcp/config/paths.py` (226 lines)

`map_client_root()` already handles local→server path translation:

```python
# Option 1: Explicit mapping via SCRIBE_PATH_MAP env var
# Format: "client_prefix=server_path;client_prefix2=server_path2"
export SCRIBE_PATH_MAP="/home/austin/projects=/app/workspaces"

# Option 2: SCRIBE_ROOT fallback — auto-creates workspace paths
# Result: /app/workspaces/{user}/{parent}/{repo}/
export SCRIBE_ROOT=/app
```

This is already used by the Hetzner Scribe server for Docker path translation.

---

## 3. MCP SDK Capabilities

### 3.1 MCP-to-MCP Communication

Yes, an MCP server CAN call another MCP server. Council demonstrates this in production:
- `MCPClient.call()` sends `{"method": "tools/call", "params": {"name": tool, "arguments": args}}` over stdio or WebSocket
- `ClientSession.call_tool()` from MCP SDK does the same over SSE or WebSocket
- `mcp.client.sse.sse_client(url)` provides SSE transport as async context manager

### 3.2 MCP Request Serialization Overhead

Each MCP tool call over SSE involves:
- 1 HTTP POST to `/messages/` with JSON-RPC payload (typically 100-500 bytes)
- 1 SSE event response from `/sse` stream
- JSON serialization/deserialization (~0.1ms)
- Tailscale overhead: ~15-50ms for persistent connection (vs 100-200ms for new Postgres connection over Tailscale)

Key insight: A **persistent SSE connection** amortizes the Tailscale RTT. Tool calls become ~50ms instead of 100-200ms per DB operation.

### 3.3 SSE vs WebSocket for Proxy

SSE (recommended for Scribe client):
- Scribe already exposes `/sse` and `/messages/` endpoints
- `mcp.client.sse.sse_client(url)` is in the MCP Python SDK
- One-directional (server→client) but MCP protocol handles bidirectionality via POST
- Simpler than WebSocket, works through HTTP proxies

WebSocket (alternative):
- Requires WebSocket transport support on server side (not currently in Scribe)
- Lower overhead for high-frequency calls
- More complex reconnect logic

---

## 4. Proxy Architecture Options — Full Analysis

### Option A: Tool-Level Forwarding (Selective Proxy)

**Concept**: Local Scribe server detects "this tool needs DB" → forwards specific tool calls to remote Scribe via HTTP.

```
Claude Code
    ↓ stdio
Local Scribe Server (no local DB)
    ↓ HTTP POST to remote /messages/
Remote Hetzner Scribe (local Postgres)
    ↓ Postgres
Database
```

**Pros**:
- Surgical: only DB-heavy tools go remote
- Local filesystem ops stay local (read_file, write_file)
- Fallback easy: if remote unavailable, error on DB tools

**Cons**:
- Tool categorization is complex (which tools are DB-heavy?)
- Shared state problem: session IDs, project context exist in remote DB but local needs them too
- Tool middleware in execute_tool_call() will STILL make DB roundtrips locally before forwarding
- Doesn't eliminate the middleware roundtrips (items 1-7 in section 1.5)

**Confidence**: LOW — tool categorization is fragile, middleware roundtrips still happen

### Option B: RemoteStorageBackend (RECOMMENDED)

**Concept**: Implement `StorageBackend` ABC that makes HTTP calls to remote Scribe's REST/MCP API instead of Postgres directly.

```
Claude Code
    ↓ stdio
Local Scribe Server
    ↓ RemoteStorageBackend.fetch_project()
    ↓ HTTP POST to remote Scribe /messages/ (tools/call)
Remote Hetzner Scribe
    ↓ Postgres (local network)
Database
```

**Implementation**:
```python
class RemoteStorageBackend(StorageBackend):
    def __init__(self, remote_url: str):
        self._client = MCPSSEClient("scribe-remote", remote_url + "/sse")

    async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
        result = await self._client.call("get_project", {"project": name})
        return ProjectRecord.from_dict(result)

    async def insert_entry(self, *, entry_id, project, ...) -> None:
        await self._client.call("append_entry", {...})
```

**Integration point**: `storage/__init__.py` `create_storage_backend()` — add `remote` as third backend type:
```python
if backend_name == "remote" and remote_url:
    from scribe_mcp.storage.remote import RemoteStorageBackend
    return RemoteStorageBackend(remote_url)
```

**Pros**:
- Clean abstraction — tools don't change at all
- All middleware roundtrips become single HTTP calls over persistent SSE connection
- Existing path mapping (`SCRIBE_PATH_MAP`) handles path translation automatically
- MCPSSEClient reference implementation already exists in council_mcp
- Fallback: `SCRIBE_REMOTE_URL` env var unset → falls back to local sqlite/postgres
- Session state lives on remote server (correct)

**Cons**:
- StorageBackend has 30+ abstract methods — substantial but mechanical implementation work
- Some methods don't map cleanly to MCP tools (e.g., `cleanup_old_entries`)
- RemoteStorageBackend becomes a new file but it's implementing an existing interface (compliant with Commandment #0.5)
- Session management complexity: local server still needs to track sessions

**Confidence**: HIGH — this is the architecturally cleanest approach

### Option C: Full MCP Proxy (Forward All)

**Concept**: Local server acts as transparent proxy forwarding ALL tool calls to remote Scribe, then performs local filesystem ops for tools that need it.

```
Claude Code
    ↓ stdio
Local Proxy Server (thin layer)
    ↓ all tool calls via HTTP
Remote Hetzner Scribe (full server)
    ↑ local file reads needed by remote
```

**Problem**: Remote Scribe can't read local files (for read_file, manage_docs). Would need a "local file agent" callback from remote to local.

**Pros**: Maximum simplicity for DB-only tools
**Cons**: File tool breakage, complex bidirectional callback needed, high protocol complexity

**Confidence**: LOW — file access problem is fundamental

### Option D: Two MCP Servers (Split Registration)

**Concept**: Register two MCP servers in Claude Code's config — one local (file tools), one remote (DB tools). Claude Code uses both.

```
Claude Code ←→ Local Scribe (file tools: read_file, manage_docs, edit_file)
Claude Code ←→ Remote Scribe at :8200 (DB tools: append_entry, set_project, query_entries)
```

**Pros**:
- No proxy code needed
- Cleanest separation
- Remote Scribe already deployed

**Cons**:
- Agent session state split across two servers — context breaks (which server has my project?)
- `set_project` on remote doesn't affect local `read_file` path resolution
- MCP tool discovery split (tools/list returns different sets)
- Requires Claude Code to know which server has which tool
- No graceful fallback when remote unavailable

**Confidence**: LOW — session state fragmentation is a hard problem

---

## 5. Recommendation: Option B with Optimization

### Primary Recommendation: RemoteStorageBackend

Implement `src/scribe_mcp/storage/remote.py` as a `StorageBackend` subclass that proxies to remote Scribe via SSE MCP client.

**Activation**: `SCRIBE_STORAGE_BACKEND=remote` + `SCRIBE_REMOTE_URL=https://council-hub:8200`

**Reference implementation**: Copy `MCPSSEClient` pattern from `council_mcp/src/council_mcp/web/mcp_client.py:623-778`

**Path mapping**: Set `SCRIBE_PATH_MAP=/home/austin/projects/MCP_SPINE=/app/workspaces/austin/MCP_SPINE` on local client — remote server already uses this.

### Optimization: In-Process Session Caching

To reduce the 7 middleware roundtrips to 1-2:

```python
class RemoteStorageBackend(StorageBackend):
    def __init__(self, remote_url: str):
        self._client = MCPSSEClient(...)
        self._session_cache: dict[str, SessionRecord] = {}  # TTL cache
        self._project_cache: dict[str, ProjectRecord] = {}  # TTL cache
```

Cache `get_session_by_transport`, `fetch_project`, and `get_session_project` locally with 60s TTL. This reduces 7 roundtrips to 0-2 per call after warmup.

### Connection: Single Persistent SSE

The `MCPSSEClient` maintains a single persistent SSE connection. All tool calls multiplex over this connection using MCP JSON-RPC IDs. This avoids Tailscale RTT per call — once connected, each call is just TCP round-trip overhead (~15-30ms vs 100-200ms for new connections).

### Fallback Mode

```python
def create_storage_backend() -> Optional[StorageBackend]:
    backend_name = settings.storage_backend
    if backend_name == "remote":
        remote_url = os.environ.get("SCRIBE_REMOTE_URL")
        if remote_url:
            from scribe_mcp.storage.remote import RemoteStorageBackend
            return RemoteStorageBackend(remote_url)
        else:
            logger.warning("SCRIBE_STORAGE_BACKEND=remote but SCRIBE_REMOTE_URL not set, falling back to sqlite")
            # Fall through to sqlite
```

---

## 6. Network Considerations

### Tailscale Latency

- Tailscale RTT to Hetzner (council-hub): ~15-50ms typical, ~100ms under load
- Current problem: 20 Postgres connections × 150ms = 3 seconds
- With RemoteStorageBackend on persistent SSE: 1-2 MCP calls × 50ms = 50-100ms
- **10-60x improvement** expected

### Connection Pooling

MCPSSEClient holds ONE persistent connection. The MCP JSON-RPC protocol is request/response with correlation IDs, so concurrent tool calls can multiplex over a single SSE connection without conflict.

### Timeout Handling

- SSE `/sse` is long-lived (minutes to hours)
- Tool calls use `call_tool(read_timeout_seconds=...)` — default 30s
- Reconnect on drop: `MCPSSEClient._reconnect()` with exponential backoff (1s→30s cap)
- For Tailscale: recommend 60s timeout, 5 retries

### SSE vs New Connection Per Call

Do NOT use a new HTTP client per tool call (common anti-pattern). The persistent SSE connection amortizes connection overhead. All the council_mcp implementations use the persistent pattern correctly.

---

## 7. Implementation Path (for Architect)

### Phase 1: RemoteStorageBackend Skeleton
- Create `src/scribe_mcp/storage/remote.py`
- Implement all abstract methods from `StorageBackend` (30+ methods)
- Use MCPSSEClient pattern from council_mcp for connection management
- Add `remote` option to `storage/__init__.py` factory
- Add `SCRIBE_REMOTE_URL` to settings.py and Settings dataclass

### Phase 2: Method Mapping
Most StorageBackend methods map to existing Scribe MCP tools:

| StorageBackend method | Scribe MCP tool | Notes |
|---|---|---|
| `upsert_project()` | `set_project` | Include root, log path |
| `fetch_project()` | `get_project` | Parse ProjectRecord |
| `list_projects()` | `list_projects` | Parse list |
| `insert_entry()` | `append_entry` | Include all fields |
| `fetch_recent_entries()` | `read_recent` | Parse entries |
| `query_entries()` | `query_entries` | Full query support |
| `get_session_by_transport()` | N/A — cache locally | Store in memory dict |
| `upsert_session()` | N/A — cache locally | Store in memory dict |
| `get_or_create_agent_session()` | N/A — derive from agent name | Cache locally |

**Key insight**: Session management methods do NOT need to proxy to remote — they can be cached in-process on the local server. Sessions are transient per Claude Code connection. Only persistent data (projects, entries, docs) needs remote storage.

### Phase 3: Path Mapping Integration
- Local server passes `root` in `set_project` calls with SCRIBE_PATH_MAP applied
- `map_client_root()` in paths.py already handles this
- Remote server receives mapped paths, stores them in Postgres

### Phase 4: Graceful Fallback
- `SCRIBE_REMOTE_URL` unset → local sqlite
- Remote unreachable → retry 3x → fall back to local sqlite (with log warning)
- Partial degradation: local writes + async flush to remote when reconnected

---

## 8. Open Questions & Gaps

1. **Filesystem tools on remote**: Tools like `read_file`, `manage_docs`, `generate_doc_templates` need local filesystem access. With Option B these stay local (local Scribe runs the tool, RemoteStorageBackend only handles the DB layer). This is CORRECT behavior. **VERIFIED SAFE**.

2. **RemoteStorageBackend method count**: 30+ abstract methods is substantial. Some may not map cleanly to existing MCP tools (e.g., `cleanup_old_entries`, `record_agent_report_card`). These can be no-ops in RemoteStorageBackend v1 with a stub that logs a warning.

3. **Concurrent calls**: MCP JSON-RPC over SSE supports concurrent in-flight requests (correlation IDs). However, MCPSSEClient's `call_tool()` is awaitable — concurrent callers will queue naturally via Python's event loop. No lock needed.

4. **Auth on remote Scribe**: Hetzner Scribe at :8200 is currently unauthenticated (trusted network only via Tailscale). RemoteStorageBackend should pass `SCRIBE_REMOTE_AUTH_TOKEN` as Bearer header if configured.

5. **UNVERIFIED**: Whether persistent SSE connection works reliably over Tailscale for hours without keep-alive issues. MCPSSEClient has reconnect logic but long-idle connections may drop. Recommend testing before production.

---

## 9. Handoff Notes for Architect

**Recommended architecture**: Option B (RemoteStorageBackend)

**Do not**: Create a new server entry point or modify transport code. The change is entirely in the storage layer.

**Existing infrastructure to use**:
- `council_mcp/src/council_mcp/web/mcp_client.py:MCPSSEClient` — copy/adapt this class
- `src/scribe_mcp/config/paths.py:map_client_root()` — use for path mapping
- `src/scribe_mcp/storage/__init__.py:create_storage_backend()` — injection point
- `src/scribe_mcp/storage/base.py:StorageBackend` — the ABC to implement

**Minimum viable implementation**:
1. RemoteStorageBackend with session methods as in-memory (no remote call)
2. Project/entry methods forwarded to remote Scribe MCP tools
3. All file-related tool execution stays local (no change needed)

**Environment variables to add**:
- `SCRIBE_REMOTE_URL` (e.g., `http://council-hub:8200`)
- `SCRIBE_REMOTE_AUTH_TOKEN` (optional Bearer token)
- `SCRIBE_PATH_MAP` (already exists, documented in paths.py)

**Quality gate**: With RemoteStorageBackend, `set_project` should complete in under 500ms (vs current 3+ seconds).
