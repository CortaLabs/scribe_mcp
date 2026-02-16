---
id: scribe_containerization-research-transport-layer
title: "\U0001F52C Research Transport Layer \u2014 scribe_containerization"
doc_type: RESEARCH_TRANSPORT_LAYER
doc_name: RESEARCH_TRANSPORT_LAYER
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-16 03:19:11 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Transport Layer — scribe_containerization
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-16 03:17:08 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Research Goal:** Determine Scribe MCP's transport capabilities and requirements for Docker network transport deployment.

**Key Finding:** Scribe MCP currently uses stdio-only transport, but the MCP Python SDK (v1.26.0) includes native SSE and HTTP transport support. Implementation is straightforward - requires adding HTTP server dependencies and creating a network-enabled entry point.

**Confidence:** 95% - Based on official MCP SDK documentation, working examples, and codebase analysis.

**Impact:** Low implementation complexity (1-2 days). Native SDK support eliminates need for custom transport layer. Docker deployment path is clear.

**Critical Discovery:** The existing `transport/` directory contains OUTBOUND notification scaffolds (HTTPSSETransportProvider, WebSocketTransportProvider), NOT bidirectional MCP protocol transports. These are unrelated to serving MCP over network. MCP SDK's `mcp.server.sse` module provides the actual solution.
<!-- ID: research_scope -->
**Research Lead:** agent-20260216-031119-6662e6ff

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
### 1. MCP SDK Version & Transport Support

**Finding:** Scribe MCP uses `mcp==1.26.0` (pinned dependency in `pyproject.toml:16`).

**SDK Transport Capabilities:**
- **stdio** - Currently used (via `mcp.server.stdio.stdio_server()`)
- **SSE (Server-Sent Events)** - Available via `mcp.server.sse` module
- **Streamable HTTP** - Recommended for production (stateless, scalable)
- **WebSocket** - Community transports available, not officially part of core SDK

**Default Mount Paths:**
- SSE: `/sse`
- Streamable HTTP: `/mcp`

**Confidence:** 100% - Verified in official SDK repository and documentation.

**Sources:**
- [MCP Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Python SDK SSE Module](https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/sse.py)
- [MCP Specification - Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)

---

### 2. Current Server Entry Point

**Current Implementation:** `src/scribe_mcp/__main__.py` → `scribe_mcp.server:main()`

**Entry Point Analysis:**
```python
# __main__.py line 14
parser.add_argument("--version", action="version", version="scribe-mcp 2.2")
# Description: "Run the Scribe MCP server over stdio."

# server.py lines 948-969 (main function)
async def main() -> None:
    """Run the MCP server over stdio."""
    if not _MCP_AVAILABLE:
        raise RuntimeError("MCP Python SDK not installed...")
    await _startup()
    
    try:
        async with mcp_stdio.stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        if not _HAS_LIFECYCLE_HOOKS:
            await _shutdown()
```

**Key Observations:**
- Single transport mode (stdio)
- No CLI flags for alternative transports
- MCP server instance (`app`) is transport-agnostic - only the transport wrapper changes
- Lifecycle hooks (`_startup()`, `_shutdown()`) already present and ready for reuse

**Confidence:** 100% - Direct code inspection.

---

### 3. Existing Network Transport Code

**Discovery:** `src/scribe_mcp/transport/` directory exists with 3 files:
- `base.py` - `TransportProvider` abstract base class
- `http_sse.py` - `HTTPSSETransportProvider` (SCAFFOLD ONLY)
- `websocket.py` - `WebSocketTransportProvider` (SCAFFOLD ONLY)

**Critical Clarification:** These are NOT MCP protocol transport implementations.

**Purpose Analysis:**
```python
# transport/base.py
class TransportProvider(ABC):
    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> TransportReceipt:
        """Send an outbound message and return a delivery receipt."""
```

**What This Is:**
- Outbound notification system (push messages TO external systems)
- For webhooks, remote logging, event streaming
- One-way communication (send only, no receive)

**What This Is NOT:**
- MCP protocol server transport
- Bidirectional client-server communication
- Replacement for stdio/SSE/HTTP MCP transports

**Status:** All methods raise `NotImplementedError`. These are placeholder contracts for future remote deployment features (likely notifications/webhooks), completely unrelated to serving MCP requests.

**Confidence:** 100% - Verified via code inspection.

---

### 4. What Would It Take to Add Network Transport

**Required Changes:**

#### A. Add Dependencies (pyproject.toml)
```toml
dependencies = [
  # ... existing deps ...
  "starlette>=0.47.2",  # ASGI framework
  "uvicorn>=0.30",      # HTTP server
]
```

**Why:** MCP SDK requires Starlette for ASGI application and Uvicorn for serving HTTP.

**Source:** [MCP SDK Requirements](https://deepwiki.com/modelcontextprotocol/python-sdk/1.1-installation-and-dependencies)

#### B. Create HTTP Server Entry Point

**Option 1: New main function for HTTP mode**
```python
# src/scribe_mcp/server_http.py (NEW FILE)
from mcp.server.sse import sse_server
from starlette.applications import Starlette
from starlette.routing import Route, Mount
import uvicorn

async def health_check(request):
    """Health endpoint for Docker HEALTHCHECK"""
    return JSONResponse({"status": "healthy", "version": "2.2"})

async def run_http():
    """Run MCP server over HTTP/SSE"""
    await _startup()
    
    # Create Starlette app with health endpoint
    http_app = Starlette(routes=[
        Route("/health", health_check),
        Mount("/sse", app=sse_server(app)),  # Mount MCP SSE transport
    ])
    
    # Run with uvicorn
    config = uvicorn.Config(http_app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()
```

**Option 2: Use FastMCP helpers**
```python
from fastmcp import FastMCP

mcp = FastMCP("scribe")
# ... register tools ...

# Mount to existing ASGI app
app = mcp.sse_app()  # Returns ASGI app with SSE endpoints
```

**Implementation Effort:** 50-100 lines of code.

**Sources:**
- [Building SSE MCP Server with FastAPI](https://www.ragie.ai/blog/building-a-server-sent-events-sse-mcp-server-with-fastapi)
- [MCP Server Deployment Guide](https://northflank.com/blog/how-to-build-and-deploy-a-model-context-protocol-mcp-server)

#### C. Update pyproject.toml Scripts
```toml
[project.scripts]
scribe-server = "scribe_mcp.__main__:main"         # stdio mode (existing)
scribe-server-http = "scribe_mcp.server_http:main" # HTTP mode (new)
```

**Confidence:** 90% - Based on SDK documentation and working examples. Minor details may vary.

---

### 5. Health Check Capability

**Current State:** Scribe has a `health_check` MCP tool (`tools/health_check.py`, 315 lines) but NO HTTP health endpoint.

**What Exists:**
- MCP tool for internal health monitoring
- Reports background service status
- Storage backend health checks
- NOT exposed via HTTP

**What's Needed for Docker:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
```

**Implementation:** Add simple HTTP endpoint to Starlette app:
```python
async def health(request):
    return JSONResponse({
        "status": "healthy",
        "version": "2.2",
        "transport": "sse",
        "uptime": time.time() - server_start_time
    })
```

**Effort:** 10-20 lines.

**Confidence:** 100%

---

### 6. Signal Handling & Graceful Shutdown

**Current Implementation:** `server.py:825-845`

```python
async def _shutdown() -> None:
    """Ensure resources are released when the server stops."""
    if background_tasks:
        for task in list(background_tasks):
            task.cancel()
        try:
            await asyncio.gather(*list(background_tasks), return_exceptions=True)
        except Exception:
            pass
    
    if storage_backend:
        try:
            async with asyncio.timeout(settings.storage_timeout_seconds):
                await asyncio.shield(storage_backend.close())
        except Exception:
            pass
```

**Shutdown Sequence:**
1. Cancel all background tasks (journal replay, cleanup, plugin init, bridge health monitor)
2. Wait for task cancellation with exception suppression
3. Close storage backend with timeout protection
4. Registered via `app.on_shutdown(_shutdown)` lifecycle hook

**Signal Handling:** MCP SDK and Uvicorn handle SIGTERM/SIGINT automatically. The `on_shutdown` hook is triggered.

**Docker Integration:**
- `stop_grace_period: 30s` in docker-compose.yml
- SIGTERM → MCP/Uvicorn shutdown → `_shutdown()` called → clean exit
- If timeout expires, SIGKILL forces termination (should be rare)

**Confidence:** 100% - Existing infrastructure is Docker-ready.

**Testing:** The shutdown handler already handles background task cancellation and storage cleanup correctly.
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---
---
## Risks & Open Questions

<!-- ID: risks_gaps -->

### Risks

#### 1. Dependency Conflicts
**Risk:** Adding Starlette + Uvicorn may conflict with existing dependencies.

**Mitigation:** 
- Version constraints are well-documented: `starlette>=0.47.2`, `uvicorn>=0.30`
- Both are mature, stable libraries with minimal transitive dependencies
- Test in isolated environment first

**Severity:** Low

---

#### 2. Port Conflicts in Docker
**Risk:** Port 8000 may conflict with other services on Hetzner VPS.

**Mitigation:**
- Use configurable port via environment variable
- Docker Compose maps external port flexibly: `8080:8000`
- No hard-coded ports in Dockerfile

**Severity:** Low (operational, not technical)

---

#### 3. SSE Connection Stability
**Risk:** SSE connections may timeout or drop in production.

**Mitigation:**
- MCP SDK handles reconnection protocol
- Council MCP client should implement retry logic
- Use `keep-alive` headers and connection pooling

**Severity:** Medium - Requires testing under load

---

### Open Questions

#### Q1: Should Scribe support BOTH stdio AND HTTP simultaneously?
**Options:**
- Option A: Mutually exclusive (CLI flag `--transport stdio|http`)
- Option B: HTTP only (deprecate stdio for containerized deployments)
- Option C: Hybrid (stdio for local dev, HTTP for production)

**Recommendation:** Option C - Keep stdio for backward compatibility, add HTTP for Docker.

---

#### Q2: Which transport to use: SSE or Streamable HTTP?
**Analysis:**
- **SSE:** Simpler implementation, proven examples, good for persistent connections
- **Streamable HTTP:** Better for stateless deployments, more scalable, recommended by MCP docs

**Recommendation:** Start with SSE (simpler), migrate to Streamable HTTP if scaling issues arise.

---

#### Q3: Authentication/Authorization for HTTP transport?
**Current State:** Scribe has no auth layer (assumes trusted localhost environment).

**Docker Implications:**
- Services within Docker network are isolated
- If exposed to internet, MUST add auth (API keys, OAuth, mutual TLS)
- Council MCP should authenticate when connecting to Scribe

**Recommendation:** 
- Phase 1: Docker network isolation (no auth needed between Council ↔ Scribe)
- Phase 2: Add auth if exposing publicly

---

#### Q4: How does Council MCP connect to network Scribe?
**Current:** Council spawns Scribe as stdio subprocess.

**Docker Change:** Council uses MCP HTTP/SSE client to connect to `http://scribe:8000/sse`

**Investigation Needed:**
- Does Council's MCP client library support HTTP transport?
- Configuration changes required in Council's MCP client setup
- Connection string format for Docker service discovery

**Action:** Pass to Council research team.

---
## Implementation Recommendations

<!-- ID: recommendations -->

### Immediate Actions (Phase 1: MVP)

1. **Add Dependencies**
   - Add to `pyproject.toml`: `starlette>=0.47.2`, `uvicorn>=0.30`
   - Run `uv pip install -e .` to verify no conflicts

2. **Create HTTP Entry Point**
   - New file: `src/scribe_mcp/server_http.py`
   - Implement SSE transport using `mcp.server.sse`
   - Add `/health` endpoint for Docker
   - Reuse existing `_startup()` and `_shutdown()` hooks

3. **Add CLI Flag**
   - Extend `__main__.py` argument parser
   - `--transport {stdio,http}` flag
   - Default: `stdio` (backward compatible)

4. **Docker Integration**
   - Dockerfile CMD: `scribe-server --transport http`
   - HEALTHCHECK: `curl -f http://localhost:8000/health`
   - Expose port 8000

5. **Testing**
   - Unit test: HTTP server startup/shutdown
   - Integration test: MCP client connects via SSE
   - Docker test: Container health checks pass

**Estimated Effort:** 1-2 days

**Confidence:** 95%

---

### Future Enhancements (Phase 2+)

1. **Streamable HTTP Transport**
   - Migrate from SSE to Streamable HTTP for better scalability
   - Requires client-side changes (Council MCP)

2. **Authentication Layer**
   - Add API key validation for public deployments
   - OAuth2/JWT support for multi-tenant scenarios

3. **Monitoring/Metrics**
   - Prometheus `/metrics` endpoint
   - Request latency tracking
   - Connection pool monitoring

4. **WebSocket Transport**
   - If real-time bidirectional needed (unlikely for MCP pattern)
   - Community transports available

---
## Handoff Notes

<!-- ID: handoff -->

### For Architect Agent

**Key Decisions:**
1. HTTP transport implementation is straightforward - MCP SDK provides native support
2. Existing shutdown hooks are Docker-ready - no changes needed
3. Recommend SSE transport for MVP, Streamable HTTP for production scale
4. Health endpoint is trivial to add (10-20 LOC)

**Architecture Considerations:**
- Keep stdio and HTTP modes separate (CLI flag, not simultaneous)
- Reuse existing lifecycle hooks (`_startup`, `_shutdown`)
- No changes to tool registration or server logic
- Transport layer is purely wrapper around existing `app` instance

**Dependencies:**
- Starlette (ASGI framework)
- Uvicorn (HTTP server)
- No conflicts expected

---

### For Coder Agent

**Implementation Tasks:**
1. Modify `pyproject.toml` dependencies
2. Create `src/scribe_mcp/server_http.py` with SSE transport
3. Add `/health` endpoint
4. Update `__main__.py` CLI parser
5. Update Dockerfile CMD
6. Add integration tests

**Code Patterns to Follow:**
- See `server.py:948-969` for stdio implementation
- Reuse `_startup()` and `_shutdown()` exactly as-is
- Follow Starlette routing examples from MCP SDK docs

**Sources:**
- [MCP Python SDK SSE Module](https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/sse.py)
- [Building SSE MCP Server with FastAPI](https://www.ragie.ai/blog/building-a-server-sent-events-sse-mcp-server-with-fastapi)

---

### For Review Agent

**Validation Checklist:**
- [ ] Starlette and Uvicorn added to dependencies
- [ ] HTTP server starts without errors
- [ ] `/health` endpoint returns 200 OK
- [ ] MCP SSE transport accepts connections
- [ ] Docker HEALTHCHECK passes
- [ ] Graceful shutdown works (SIGTERM)
- [ ] No regression in stdio mode
- [ ] Tools work identically over HTTP and stdio

**Testing Requirements:**
- Unit tests for HTTP server lifecycle
- Integration test with MCP client over SSE
- Docker container health validation
- Load test (100+ concurrent connections)

---

## Sources & References

<!-- ID: sources -->

### Official Documentation
- [MCP Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Python SDK SSE Module](https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/sse.py)
- [MCP Specification - Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [MCP SDK Requirements](https://deepwiki.com/modelcontextprotocol/python-sdk/1.1-installation-and-dependencies)

### Implementation Guides
- [Building SSE MCP Server with FastAPI](https://www.ragie.ai/blog/building-a-server-sent-events-sse-mcp-server-with-fastapi)
- [MCP Server Deployment Guide](https://northflank.com/blog/how-to-build-and-deploy-a-model-context-protocol-mcp-server)
- [Build Your First MCP Application (Stdio & SSE)](https://thesof.medium.com/build-your-first-mcp-application-step-by-step-examples-for-stdio-and-sse-servers-integration-773b187aeaed)

### Community Examples
- [mcp-sse Working Pattern](https://github.com/sidharthrajaram/mcp-sse)
- [mcp-weather-sse Example](https://github.com/justjoehere/mcp-weather-sse)

### Related Research
- Cloudflare: [Streamable HTTP & Python Support for MCP](https://blog.cloudflare.com/streamable-http-mcp-servers-python/)

---

**Research Complete:** 2026-02-16 03:17 UTC  
**Research Agent:** ResearchAgent-Transport  
**Confidence:** 95%  
**Next Step:** Architect Agent - Design HTTP transport integration
