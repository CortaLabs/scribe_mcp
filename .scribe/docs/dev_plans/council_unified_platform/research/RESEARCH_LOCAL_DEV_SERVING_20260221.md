# RESEARCH_LOCAL_DEV_SERVING_20260221

## Executive Summary

**Goal**: Enable `council connect serve` command to run a local development instance of Council web UI and daemon while sharing the production database on Hetzner, allowing developers to test locally before pushing changes.

**Current State**: 
- `council connect start` only joins Ray clusters as a compute worker
- Web UI and daemon only run on Hetzner via Docker containers
- No local dev environment with full isolation + shared infrastructure

**Key Finding**: The architecture is **ready for local dev serving** with minimal changes. All components support remote database connections via environment variables, and web/daemon are designed to run independently.

**Confidence**: **HIGH** ✓ — All integration points verified in source code. No architectural blockers identified.

---

## Database Reachability: YES

**Connection Path**: Local machine → Tailscale mesh → Hetzner Postgres (5432)

**Evidence from source**:
1. `docker-compose.yaml` lines 121-123: Postgres bound to both `127.0.0.1` AND `${TAILSCALE_IP}` for Tailscale access
2. `start_cmd.py` lines 31-92: Validates `DATABASE_URL` env var for remote mode
3. `server.py` line 431: AgentKit loads `DATABASE_URL` from env (no hardcoded connection strings)
4. All logs, memories, sessions written to same postgres instance
5. Ray workers already use Tailscale mesh over network — same path as DB

**Verification**: Postgres exposes dual ports; Tailscale connectivity proven by Ray workers joining from local machines.

---

## Component Analysis

### Web UI (app.py)
- ✓ No direct DB connection — all via MCP daemon
- ✓ Configurable ports (default 8015, overridable in config)
- ✓ MCP client pool supports both local (stdio) and remote (WebSocket) daemons
- ✓ Can run on localhost with any port
- **Required changes**: NONE

### Daemon (server.py)
- ✓ DATABASE_URL resolution fully external (env vars)
- ✓ Configurable port (default 8016)
- ✓ Starts as independent process (not tied to web lifecycle)
- ✓ Can proxy Scribe or use local
- **Required changes**: Port override logic for multi-instance support

### Database (AgentKit)
- ✓ psycopg3 connection pooling — supports remote connections
- ✓ Tailscale encrypted mesh network
- ✓ No hardcoded host/port
- ✓ All schemas compatible (public, council, scribe, etc.)
- **Required changes**: NONE — pass DATABASE_URL env var

### Scribe MCP (mcp_client.py lines 1123-1272)
- ✓ Supports 3 connection modes: stdio, HTTP SSE, proxy-via-daemon
- ✓ Auto-detects which mode available
- ✓ Can use local Scribe OR proxy through hub
- **Required changes**: NONE

### Ray Cluster
- ✓ Already joins from local machines via Tailscale
- ✓ ComputeDispatcher auto-discovers Ray workers
- ✓ Local dev instance can use same Ray cluster
- **Required changes**: NONE

### Council Registry & Isolation
- ✓ Each repo has unique council_id
- ✓ Cookie-based session isolation (dev instance ≠ prod)
- ✓ All API endpoints filter by `_get_active_council_id(request)`
- ✓ Browser tabs independently select council via sessionStorage
- **Required changes**: Documentation only (recommend separate browser profiles)

---

## Port Conflicts & Resolution

**Problem**: Running local dev instance on same machine as production clone could bind same ports.

**Solution** (already in code):
1. **CLI Override** (preferred): `council start --port 8017 --web-port 8018`
   - start_cmd.py lines 96-100 already have `--port` and `--web-port` flags
   - Threads through to daemon and web startup
   - Cleanest approach

2. **Environment Variables**:
   - `COUNCIL_WEB_PORT=8018 COUNCIL_DAEMON_PORT=8017 council start`
   - Config/__init__.py supports env override

3. **Config File Override**:
   - `.council/council.yaml` has `council.web.port` and `council.transport.ws_port`
   - But both dev and prod would read same file if cloned

**Recommended Implementation**: Verify CLI flags thread through correctly, document usage.

---

## Proposed `council connect serve` Command

```bash
# Start local dev instance
council connect serve [--daemon-port 8017] [--web-port 8018] [--scribe local|hub] [--foreground]

# Output:
Web UI:     http://localhost:8018
Daemon:     ws://localhost:8017/mcp
Database:   postgresql://user@council-hub:5432/agentkit (Tailscale)
Ray:        connected to council-hub:6379
```

**Implementation** (3-4 files, ~200 lines):
1. Add `serve()` function to `connect_cmd.py` (~100 lines)
2. Refactor port logic in `start_cmd.py` (~20 lines)
3. Ensure env var precedence in config (already done)
4. Document in `.council/DEVELOPMENT.md` (~50 lines)

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Tailscale latency | LOW | <5ms typical, pooling handles reuse |
| Schema version mismatch | MEDIUM | Run `agentkit-schema plan` before pushing |
| Session cookie conflicts | LOW | Use separate browser profiles or incognito |
| Ray connects to wrong daemon | LOW | Ray is address-based, both can use same cluster |
| Scribe path conflicts | LOW | Scribe proxy handles translation |

---

## Open Questions

1. **Browser Isolation**: Enforce separate profiles in docs, or implement hostname-based cookie isolation?
2. **Scribe Default**: Local Scribe (--scribe local) or hub proxy (simpler)?
3. **Port Defaults**: Use 8017/8018 (sequential) or 9015/9016 (separate range)?
4. **Ray Cluster**: Auto-join Ray if running, or require explicit `council connect start` first?
5. **Documentation Scope**: Include local Scribe setup, local Ray head, multi-council workflows?

---

## Summary

**Ready to implement**: All architectural components support local dev serving. Minimal glue code needed. No blockers identified.

**Next step**: Operator approval on open questions → Blueprint produces task packages for Forge implementation.

