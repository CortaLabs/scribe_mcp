---
id: scribe_containerization-research-report-research-council-integration-guide
title: 'Council Integration Guide: Containerized Scribe MCP'
doc_type: research_report_RESEARCH_COUNCIL_INTEGRATION_GUIDE
doc_name: research_report_RESEARCH_COUNCIL_INTEGRATION_GUIDE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-16 04:41:48 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# Council Integration Guide: Containerized Scribe MCP

**Author:** ResearchAgent-CouncilHandoff
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-02-16 04:35 UTC
**Confidence:** 0.95

> This document provides the Council team with everything needed to switch from
> spawning Scribe as a stdio subprocess to connecting to Scribe as an independent
> Docker container via SSE transport. Following these steps, a developer should
> be able to deploy without asking questions.

---

## 1. Overview

<!-- ID: executive_summary -->

### What Changed

Scribe MCP has been containerized (Phases 1-3 of the `scribe_containerization` project). The key change is **transport protocol**:

| Aspect | Before (stdio) | After (SSE) |
|--------|----------------|-------------|
| **Transport** | stdin/stdout JSON-RPC | HTTP SSE on port 8200 |
| **Process ownership** | Council daemon spawns Scribe as child process | Scribe runs as independent Docker service |
| **Lifecycle** | Council starts/stops Scribe subprocess | Docker Compose manages Scribe lifecycle |
| **Discovery** | Filesystem path to scribe_mcp package | Docker DNS: `http://scribe:8200/sse` |
| **Database** | SQLite (local file) | PostgreSQL (`scribe` schema in `agentkit` DB) |
| **Health check** | Process liveness via `os.kill(pid, 0)` | HTTP health endpoint at `/health` |

### What Stays the Same

- **All 21 MCP tools** -- identical tool names, parameters, and return formats
- **MCP protocol** -- same MCP SDK, same ClientSession handshake
- **ScribeBridge API** -- same `ScribeMCPClient` methods (append_entry, query_entries, etc.)
- **Behavior** -- identical tool behavior; transport is transparent to tool logic
- **Data** -- projects, logs, documents all work identically over SSE

---

## 2. Docker Compose Integration

<!-- ID: research_scope -->

### Scribe's Compose File

Scribe ships a **composable Docker Compose overlay** designed to merge with Council's existing compose file:

- **File:** `scribe_mcp/deploy/docker-compose.scribe.yaml`
- **Design:** Defines the `scribe` service, `scribe_data` volume, `backend` network, and `scribe_db_url` secret
- **Merge behavior:** When combined with Council's compose file via `-f` flags, Docker Compose unifies shared resources (network `backend`, service `postgres`, volume `scribe_data`)

### How to Run Both Together

```bash
docker compose \
  -f /path/to/council_mcp/deploy/docker-compose.yaml \
  -f /path/to/scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d
```

On the Hetzner deployment:

```bash
docker compose \
  -f /opt/council_mcp/deploy/docker-compose.yaml \
  -f /opt/scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d
```

Docker Compose merges the two files:
- Council's `postgres`, `council-daemon`, `council-web` services from the first file
- Scribe's `scribe` service from the second file
- The `backend` network and `postgres` service definitions unify automatically
- The `scribe_data` volume is defined in both files (Council's compose already has it at line 323)

### Network Configuration

All services share the `backend` bridge network:

```
backend network (bridge)
  |-- postgres:5432       (shared database)
  |-- council-daemon:8016 (Council MCP/WebSocket)
  |-- council-web:8015    (Council Web UI)
  |-- scribe:8200         (Scribe MCP/SSE)  <-- NEW
```

Scribe does NOT expose any ports to the host. It is internal-only, reachable by Council containers via Docker DNS hostname `scribe`.

---

## 3. Council Code Changes Required

<!-- ID: findings -->

### 3.1 Overview of Affected Files

| File | Change Required | Difficulty |
|------|----------------|------------|
| `council_mcp/deploy/docker-compose.yaml` | Add `SCRIBE_SSE_URL` env var to daemon and web services | Trivial |
| `council_mcp/src/council_mcp/server.py` | Replace `_start_scribe_clients()` with SSE client | Medium |
| `council_mcp/src/council_mcp/web/mcp_client.py` | Add SSE path in `MCPClientPool.start_scribe()` | Medium |
| `council_mcp/src/council_mcp/bridges/scribe_mcp_client.py` | Update `ScribeMCPClient.start()` to use SSE | Low |
| `council_mcp/src/council_mcp/process_manager.py` | No changes needed | None |

### 3.2 The Core Change: stdio to SSE Client

Council currently connects to Scribe via `MCPClient` (stdio subprocess):

```python
# CURRENT (server.py:762-768) -- stdio subprocess
client = MCPClient(
    client_key,
    command=["python", "-m", "server"],
    cwd=str(scribe_root),
    env=env,
    ready_patterns=["Server ready"],
)
await client.start()
```

The replacement uses the MCP SDK's SSE client transport:

```python
# NEW -- SSE network client
from mcp.client.sse import sse_client

scribe_url = os.environ.get("SCRIBE_SSE_URL", "http://scribe:8200/sse")
async with sse_client(scribe_url) as (read_stream, write_stream):
    session = ClientSession(read_stream, write_stream)
    await session.initialize()
    # session is now ready for tool calls
```

**Important:** The MCP SDK's `sse_client` is a context manager that maintains a persistent connection. Council needs to manage this connection's lifecycle (start on daemon boot, close on shutdown).

### 3.3 _start_scribe_clients() Replacement

The function at `server.py:704-812` currently:
1. Locates `scribe_mcp` package on the filesystem
2. Builds PYTHONPATH for the subprocess
3. Spawns `MCPClient` with stdin/stdout pipes
4. Registers the process PID with ProcessManager

In Docker mode, ALL of this is unnecessary. Scribe is a network service, not a subprocess. The replacement should:
1. Connect to `http://scribe:8200/sse` via MCP SSE client
2. Initialize a `ClientSession`
3. Store the session in `_RUNTIME_CONTEXT["scribe_clients"]`
4. Skip ProcessManager registration (Docker manages Scribe lifecycle)

### 3.4 ScribeMCPClient Bridge Update

The `ScribeMCPClient` class (`bridges/scribe_mcp_client.py`) currently calls `MCPClientPool.start_scribe()` which spawns a subprocess. The key change is that `MCPClientPool.start_scribe()` must detect Docker mode and connect via SSE instead:

```python
SCRIBE_SSE_URL = os.environ.get("SCRIBE_SSE_URL")
if SCRIBE_SSE_URL:
    # Docker mode: connect via SSE
    return await self._start_scribe_sse(SCRIBE_SSE_URL)
else:
    # Local dev mode: spawn subprocess (existing behavior)
    return await self._start_scribe_direct(repo_root)
```

### 3.5 Environment Variable for Council

Add to Council's `docker-compose.yaml` for the `council-daemon` service:

```yaml
environment:
  - SCRIBE_SSE_URL=http://scribe:8200/sse
```

This tells Council's code to use SSE transport instead of spawning a subprocess.

---

## 4. Database Setup

<!-- ID: technical_analysis -->

### Schema Isolation

Scribe uses the `scribe` PostgreSQL schema within the existing `agentkit` database:

- **No new database** is needed
- Scribe's tables live in `search_path=scribe`, completely isolated from Council's `public` schema
- The same PostgreSQL instance serves both Council and Scribe

### Connection String Format

```
postgresql://council:<password>@postgres:5432/agentkit?options=-c%20search_path%3Dscribe
```

Breaking this down:
- `council:<password>` -- same database user as Council
- `postgres:5432` -- Docker DNS hostname for the postgres service
- `agentkit` -- shared database name
- `options=-c search_path=scribe` -- sets the PostgreSQL search path to the `scribe` schema (URL-encoded)

### Secret File

**File location:** `secrets/scribe_db_url.txt` (relative to the repo root)

**Content (single line, no trailing newline):**
```
postgresql://council:<PASSWORD>@postgres:5432/agentkit?options=-c%20search_path%3Dscribe
```

Replace `<PASSWORD>` with the actual PostgreSQL password (same as `pg_password.txt`).

**Note on secret file paths:**
- Council's compose resolves paths relative to `council_mcp/deploy/`: `../secrets/` = `council_mcp/secrets/`
- Scribe's compose resolves paths relative to `scribe_mcp/deploy/`: `../../secrets/` = `MCP_SPINE/secrets/` (monorepo root)
- On Hetzner production, paths may differ. Adjust the `secrets.scribe_db_url.file` entry in the compose file if needed.

**Council already defines this secret** in its `docker-compose.yaml` (line 378-379):
```yaml
scribe_db_url:
  file: ../secrets/scribe_db_url.txt
```

Council's `docker-entrypoint.sh` already bridges it to `SCRIBE_DB_URL` (lines 75-79).

---

## 5. Deployment Steps (Step-by-Step Checklist)

<!-- ID: recommendations -->

### Prerequisites

- Docker and Docker Compose installed
- Council's `docker-compose.yaml` working
- PostgreSQL running and healthy
- Access to the secrets directory

### Step 1: Create the Secret File (if not already present)

```bash
mkdir -p /opt/council_mcp/secrets/

echo -n "postgresql://council:YOUR_PASSWORD@postgres:5432/agentkit?options=-c%20search_path%3Dscribe" \
  > /opt/council_mcp/secrets/scribe_db_url.txt

chmod 600 /opt/council_mcp/secrets/scribe_db_url.txt
```

**Note:** Council's compose already references `scribe_db_url` (line 378-379). The file may already exist.

### Step 2: Ensure Scribe MCP Repository is Available

```bash
ls /opt/scribe_mcp/deploy/Dockerfile  # Verify presence
```

### Step 3: Build the Scribe Docker Image

```bash
cd /opt/scribe_mcp
docker build -f deploy/Dockerfile -t scribe-mcp:latest .
```

Or let Docker Compose build it automatically on first `up`.

### Step 4: Add Scribe to the Docker Compose Command

```bash
# OLD (Council only)
docker compose -f /opt/council_mcp/deploy/docker-compose.yaml up -d

# NEW (Council + Scribe)
docker compose \
  -f /opt/council_mcp/deploy/docker-compose.yaml \
  -f /opt/scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d
```

### Step 5: Update Council's Scribe Connection Config

Add `SCRIBE_SSE_URL` to `council_mcp/deploy/docker-compose.yaml`:

```yaml
council-daemon:
  environment:
    - DATABASE_URL_FILE=/run/secrets/database_url
    - SCRIBE_STORAGE_BACKEND=postgres
    - SCRIBE_SSE_URL=http://scribe:8200/sse    # ADD THIS

council-web:
  environment:
    - DATABASE_URL_FILE=/run/secrets/database_url
    - SCRIBE_STORAGE_BACKEND=postgres
    - SCRIBE_SSE_URL=http://scribe:8200/sse    # ADD THIS
```

Then implement the code changes described in Section 3.

### Step 6: Bring Up Services

```bash
docker compose \
  -f /opt/council_mcp/deploy/docker-compose.yaml \
  -f /opt/scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d
```

Startup order (enforced by `depends_on`):
1. `postgres` starts first (health check: `pg_isready`)
2. `scribe` starts after postgres is healthy
3. `council-daemon` starts after postgres is healthy
4. `council-web` starts after council-daemon

### Step 7: Verify Health

```bash
docker compose \
  -f /opt/council_mcp/deploy/docker-compose.yaml \
  -f /opt/scribe_mcp/deploy/docker-compose.scribe.yaml \
  ps

docker exec scribe-mcp curl -sf http://localhost:8200/health | python3 -m json.tool
```

Expected:
```json
{
    "status": "healthy",
    "service": "scribe-mcp",
    "version": "2.2",
    "transport": "sse",
    "uptime_seconds": 42
}
```

---

## 6. Verification Commands

<!-- ID: verification -->

### Health Check

```bash
# From Docker host
docker exec scribe-mcp curl -sf http://localhost:8200/health

# From Council container (verifies network connectivity)
docker exec council-daemon curl -sf http://scribe:8200/health
```

### MCP Connectivity Test

```bash
docker exec council-daemon python3 -c "
import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def test():
    async with sse_client('http://scribe:8200/sse') as (read, write):
        session = ClientSession(read, write)
        await session.initialize()
        tools = await session.list_tools()
        print(f'Connected! Found {len(tools.tools)} tools:')
        for t in sorted(tools.tools, key=lambda x: x.name):
            print(f'  - {t.name}')

asyncio.run(test())
"
```

Expected output: 21 Scribe MCP tools listed.

### Log Inspection

```bash
docker logs scribe-mcp
docker logs scribe-mcp --tail 50 --follow
docker logs scribe-mcp 2>&1 | grep -i error
docker logs scribe-mcp 2>&1 | grep scribe-entrypoint
```

### Resource Usage

```bash
docker stats scribe-mcp --no-stream
```

Expected: under 1GB memory, under 0.5 CPU.

---

## 7. Rollback Plan

<!-- ID: rollback -->

### Step 1: Remove Scribe from Docker Compose

```bash
docker compose -f /opt/council_mcp/deploy/docker-compose.yaml up -d
```

### Step 2: Remove SCRIBE_SSE_URL Environment Variable

Remove the `SCRIBE_SSE_URL` line from Council's compose.

### Step 3: Code Reverts

If SSE is gated by `SCRIBE_SSE_URL` env var, removing the env var automatically falls back to subprocess mode. No code revert needed.

### Step 4: Stop Scribe Container

```bash
docker stop scribe-mcp && docker rm scribe-mcp
```

### Summary

| Change | Rollback Action |
|--------|----------------|
| Compose `-f` flag | Remove the Scribe compose file from the command |
| `SCRIBE_SSE_URL` env var | Remove from compose environment |
| Code changes | No revert needed if SSE is gated by env var |
| Secret file | Can remain (harmless) |
| Scribe container | Stop and remove |

---

## 8. Troubleshooting

<!-- ID: appendix -->

### Scribe container fails to start

**Check:** `docker logs scribe-mcp`

**Common causes:**
- Missing `scribe_db_url` secret file
- PostgreSQL not healthy yet
- Wrong connection string format (must include `?options=-c%20search_path%3Dscribe`)

### Council cannot connect to Scribe

**Check:**
```bash
docker ps | grep scribe
docker exec scribe-mcp curl -sf http://localhost:8200/health
docker exec council-daemon curl -sf http://scribe:8200/health
```

**Common causes:**
- Scribe not on the `backend` network
- Scribe not yet healthy (`start_period: 10s`)
- DNS: service name is `scribe`, not `scribe-mcp` (container_name vs service name)

### Schema not created in PostgreSQL

**Check:** `docker exec council-postgres psql -U council -d agentkit -c "\dn"`

The `scribe` schema is auto-created on first connection. If missing, check connection string and database permissions.

### Empty results after SQLite migration

Data from local SQLite is NOT auto-migrated to PostgreSQL. A separate migration script is needed.

### Network Debugging

```bash
docker network ls | grep backend
docker network inspect backend
docker exec council-daemon getent hosts scribe
docker exec council-daemon curl -v http://scribe:8200/health
```

### Compose Validation

```bash
docker compose \
  -f /opt/council_mcp/deploy/docker-compose.yaml \
  -f /opt/scribe_mcp/deploy/docker-compose.scribe.yaml \
  config
```

---

## 9. Architecture Reference

### System Topology

```
                    Docker Host (Hetzner CCX23)
    +----------------------------------------------------------+
    |                   backend network (bridge)               |
    |                                                          |
    |  +--------------+  +--------------+  +--------------+    |
    |  | council-web  |  |council-daemon|  |   postgres   |    |
    |  |  :8015       |  |  :8016 (WS)  |  |  :5432       |    |
    |  |  FastAPI     |  |  MCP Server  |  | pgvector/pg16|    |
    |  +------+-------+  +------+-------+  +------+-------+    |
    |         |                 |                  |            |
    |         |    +------------+------------------+            |
    |         |    |            |                  |            |
    |         |    |  +---------v--------+         |            |
    |         |    |  |     scribe       |         |            |
    |         |    |  |  :8200 (SSE)     |---------+            |
    |         |    |  |  MCP Server      |                      |
    |         |    |  |  /health         |                      |
    |         |    |  |  /sse (MCP)      |                      |
    |         |    |  +------------------+                      |
    |         |    |                                            |
    |  Named Volumes:                                          |
    |  pg_data --- postgres data                               |
    |  scribe_data --- .scribe/ (docs, logs, config)           |
    |  council_data --- .council/ (config, state)              |
    +----------------------------------------------------------+
```

### Scribe Endpoints

| Endpoint | Purpose | Method |
|----------|---------|--------|
| `/health` | Docker HEALTHCHECK and monitoring | GET |
| `/sse` | MCP SSE stream (client connects here) | GET |
| `/messages/` | MCP client message posting | POST |

### Resource Allocation

| Resource | Scribe | Council Daemon | Council Web | Postgres |
|----------|--------|---------------|-------------|----------|
| Memory limit | 1 GB | 2 GB | 1.5 GB | 4 GB |
| CPU limit | 0.5 | 0.8 | 0.6 | 1.0 |

### Startup Order

```
postgres (pg_isready)
    |
    +---> scribe (depends_on: postgres healthy)
    +---> council-daemon (depends_on: postgres healthy)
              +---> council-web (depends_on: council-daemon)
```

---

## 10. Files Reference

### Scribe Deliverables

| File | Purpose |
|------|---------|
| `scribe_mcp/deploy/Dockerfile` | Multi-stage build, python:3.11-slim, non-root user, tini PID 1 |
| `scribe_mcp/deploy/docker-compose.scribe.yaml` | Composable overlay service definition |
| `scribe_mcp/deploy/docker-entrypoint.sh` | Docker secrets bridging, startup logging |
| `scribe_mcp/src/scribe_mcp/server_sse.py` | SSE transport: Starlette + uvicorn + SseServerTransport |
| `scribe_mcp/src/scribe_mcp/__main__.py` | CLI entry point with `--transport sse` flag |

### Council Files Needing Changes

| File | What to Change |
|------|----------------|
| `council_mcp/deploy/docker-compose.yaml` | Add `SCRIBE_SSE_URL` env var |
| `council_mcp/src/council_mcp/server.py` | Replace `_start_scribe_clients()` with SSE |
| `council_mcp/src/council_mcp/web/mcp_client.py` | Add SSE path in `MCPClientPool.start_scribe()` |
| `council_mcp/src/council_mcp/bridges/scribe_mcp_client.py` | Transparent (uses pool) |

---

## 11. Handoff Notes for Architect/Coder

### Critical Design Decisions

1. **Environment-variable gating:** Use `SCRIBE_SSE_URL` to toggle between subprocess (local dev) and SSE (Docker). Without the env var, existing subprocess path runs unchanged.

2. **Connection lifecycle:** The MCP SDK `sse_client()` is an async context manager. Council needs a wrapper that opens on daemon startup, handles reconnection, closes on shutdown, and provides the same `call()` interface as `MCPClient`.

3. **No subprocess management in Docker:** When `SCRIBE_SSE_URL` is set, skip ALL of `_start_scribe_clients()` -- no spawning, no PID files, no ProcessManager registration.

4. **Health check integration:** Council can hit `http://scribe:8200/health` before MCP tool calls. Config: `council.bridges.scribe_health_check_timeout` (default: 1.0s).

5. **Shared client:** Web UI and daemon should share one SSE client, not create separate connections.

### Open Questions

- **Reconnection strategy:** Suggest exponential backoff (1s base, 30s max) matching existing `exponential_backoff()` utility in `mcp_client.py`.
- **Startup race:** Council daemon and Scribe both depend on postgres. SSE connection should retry with backoff rather than crashing.
- **Volume sharing:** Both Council and Scribe define `scribe_data`. Verify no path conflicts in merged compose.

---
