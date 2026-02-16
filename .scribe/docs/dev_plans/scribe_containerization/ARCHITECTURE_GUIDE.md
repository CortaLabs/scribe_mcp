---
id: scribe_containerization-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_containerization"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-16 03:53:41 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — scribe_containerization
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-16 02:56:56 UTC

> Architecture guide for scribe_containerization.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
### Context

Scribe MCP currently runs exclusively over **stdio transport**, meaning it must be launched as a subprocess by its consumer (e.g., Claude Code, Council daemon). This architecture is incompatible with Docker container networking, where services run as independent containers communicating over TCP/IP.

Council MCP is being containerized on a Hetzner CCX23 VPS (16GB RAM, 4 vCPU, Ubuntu 24.04) with PostgreSQL (pgvector/pgvector:pg16). For Council to invoke Scribe tools from a separate container, Scribe must serve over a network-capable transport protocol.

### Goals

1. **Network Transport**: Add SSE (Server-Sent Events) transport to Scribe MCP alongside existing stdio, using native MCP SDK support (`mcp.server.sse.SseServerTransport`)
2. **Containerization**: Create production-ready Dockerfile following Docker best practices verified from Council's deployment experience
3. **Database Integration**: Connect Scribe to Council's existing PostgreSQL instance with schema isolation (`scribe` schema in `agentkit` database)
4. **Council Integration**: Enable Council to connect to Scribe over Docker internal network instead of subprocess spawning
5. **Operational Readiness**: HTTP health endpoint, graceful shutdown, named volumes, resource limits, non-root execution

### Non-Goals (Out of Scope)

- Authentication/authorization layer (Docker network provides isolation)
- Streamable HTTP transport (future upgrade path, not MVP)
- Vector indexing / ML dependencies in container (optional, excluded for image size)
- Public internet exposure (Tailscale handles external access)
- Multi-instance scaling (single Scribe container sufficient)

### Research Foundation

This architecture is based on 4 verified research documents:
- `RESEARCH_TRANSPORT_LAYER.md` -- MCP SDK 1.26.0 native SSE support, implementation path
- `RESEARCH_STORAGE_CONFIG.md` -- Postgres backend with schema isolation, env var mapping
- `RESEARCH_CONTAINERIZATION_REQS.md` -- Dependencies, resources, security profile
- `RESEARCH_DOCKER_BEST_PRACTICES.md` -- Council Docker patterns (the standard to follow)
<!-- ID: requirements_constraints -->
### Functional Requirements

| ID | Requirement | Priority | Verification |
|----|-------------|----------|--------------|
| FR-1 | Scribe serves MCP tools over SSE transport on configurable port | P0 | MCP client connects and invokes tools |
| FR-2 | Stdio transport preserved for local development | P0 | `scribe-mcp` (no args) works as before |
| FR-3 | `--transport` CLI flag selects stdio or sse mode | P0 | `scribe-mcp --transport sse` starts HTTP server |
| FR-4 | `/health` HTTP endpoint returns JSON status | P0 | `curl http://localhost:8200/health` returns 200 |
| FR-5 | Postgres backend with `scribe` schema isolation | P0 | Tables created in `scribe.*` namespace |
| FR-6 | `.scribe/` directory persisted via Docker volume | P0 | Data survives container restart |
| FR-7 | `SCRIBE_TRANSPORT_PORT` env var for port config | P1 | Container starts on configured port |
| FR-8 | Graceful shutdown on SIGTERM (flush DB, cancel tasks) | P1 | `docker stop` exits cleanly within 30s |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Docker image size (without ML deps) | < 300MB |
| NFR-2 | Container memory limit | 1GB (512MB typical) |
| NFR-3 | Container CPU limit | 0.5 cores |
| NFR-4 | Health check response time | < 1s |
| NFR-5 | Container startup time | < 15s to healthy |
| NFR-6 | Graceful shutdown time | < 30s |

### Constraints

1. **MCP SDK Version**: Pinned to `mcp==1.26.0` -- transport implementation must use this version's API
2. **Python Version**: >= 3.11 (per pyproject.toml)
3. **Base Image**: `python:3.11-slim` (Alpine breaks asyncpg/psycopg2 compilation)
4. **Port Allocation**: Scribe uses port 8200 (8015=Council web, 8016=Council daemon, 8017=reserved for Council health)
5. **Network**: Single `backend` bridge network shared with Council services
6. **No New Dependencies**: starlette (>=0.27) and uvicorn (>=0.31.1) are already transitive dependencies of `mcp==1.26.0` -- no additions to pyproject.toml needed
7. **Existing Code**: Must not modify existing tool registration, server logic, or storage backends -- transport is a wrapper around the existing `app` (Server) instance
8. **sentence-transformers**: EXCLUDED from Docker image (optional, adds 2GB+ -- lazy-loaded with graceful fallback)
<!-- ID: architecture_overview -->
### System Topology (Docker Deployment)

```
                    Docker Host (Hetzner CCX23)
    ┌──────────────────────────────────────────────────────────┐
    │                   backend network (bridge)               │
    │                                                          │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
    │  │ council-web  │  │council-daemon│  │   postgres   │   │
    │  │  :8015       │  │  :8016 (WS)  │  │  :5432       │   │
    │  │  FastAPI     │  │  MCP Server  │  │ pgvector/pg16│   │
    │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
    │         │                 │                  │           │
    │         │    ┌────────────┼──────────────────┤           │
    │         │    │            │                  │           │
    │         │    │  ┌─────────▼────────┐         │           │
    │         │    │  │     scribe       │         │           │
    │         │    │  │  :8200 (SSE)     │─────────┘           │
    │         │    │  │  MCP Server      │                     │
    │         │    │  │  /health         │                     │
    │         │    │  │  /sse (MCP)      │                     │
    │         │    │  └──────────────────┘                     │
    │         │    │                                           │
    │  Named Volumes:                                          │
    │  pg_data ─── postgres data                               │
    │  scribe_data ─── .scribe/ (docs, logs, config)           │
    │  council_data ─── .council/ (config, state)              │
    └──────────────────────────────────────────────────────────┘
```

### Transport Architecture

Scribe MCP's server instance (`app = Server(...)` at `server.py:111`) is **transport-agnostic**. Currently wrapped by `mcp_stdio.stdio_server()` for stdin/stdout communication. This architecture adds SSE as an alternative transport wrapper:

```
                          ┌─────────────────────┐
                          │   MCP Server (app)   │
                          │   server.py:111      │
                          │   Transport-agnostic │
                          └──────────┬──────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
    ┌─────────▼──────────┐ ┌────────▼──────────┐           │
    │  stdio transport   │ │  SSE transport    │           │
    │  (existing)        │ │  (NEW)            │           │
    │  server.py:957     │ │  server_sse.py    │    Future:│
    │  mcp_stdio.stdio_  │ │  SseServerTransp  │  Streamable
    │  server()          │ │  ort + Starlette  │    HTTP   │
    └────────────────────┘ └───────────────────┘           │
                                                           │
                                               ┌───────────▼───┐
                                               │ Streamable    │
                                               │ HTTP (v2)     │
                                               └───────────────┘
```

### Component Summary

| Component | Type | Location | Purpose |
|-----------|------|----------|---------|
| `server_sse.py` | NEW file | `src/scribe_mcp/server_sse.py` | SSE transport entry point with health endpoint |
| `__main__.py` | MODIFY | `src/scribe_mcp/__main__.py` | Add `--transport` flag and `SCRIBE_TRANSPORT` env var |
| `Dockerfile` | NEW file | `scribe_mcp/Dockerfile` | Multi-stage build (builder + runtime) |
| `.dockerignore` | NEW file | `scribe_mcp/.dockerignore` | Reduce build context |
| `docker-compose.scribe.yaml` | NEW file | `scribe_mcp/deploy/docker-compose.scribe.yaml` | Scribe service definition (composable with Council) |
| `docker-entrypoint.sh` | NEW file | `scribe_mcp/deploy/docker-entrypoint.sh` | Secrets-to-env bridge, volume permissions |
| `pyproject.toml` | MODIFY | `pyproject.toml` | Add `scribe-server-sse` script entry point |
<!-- ID: detailed_design -->
### 4.1 SSE Transport Server (`server_sse.py`)

**Location**: `src/scribe_mcp/server_sse.py` (NEW FILE, ~120 lines)

This file creates a Starlette ASGI application that:
1. Mounts the MCP SSE transport at `/sse` and message posting at `/messages/`
2. Adds a `/health` endpoint for Docker HEALTHCHECK
3. Runs via uvicorn with configurable host/port
4. Reuses existing `_startup()` and `_shutdown()` lifecycle hooks from `server.py`

**Key Implementation Details:**

```python
# server_sse.py - Architectural specification (not exact code)

from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import time

# Import shared server infrastructure
from scribe_mcp.server import app, _startup, _shutdown

# Module-level state
_server_start_time = None

async def health_check(request):
    """HTTP health endpoint for Docker HEALTHCHECK."""
    return JSONResponse({
        "status": "healthy",
        "service": "scribe-mcp",
        "version": "2.2",
        "transport": "sse",
        "uptime_seconds": int(time.time() - _server_start_time) if _server_start_time else 0,
    })

async def run_sse(host: str = "0.0.0.0", port: int = 8200) -> None:
    """Run MCP server over SSE transport."""
    global _server_start_time
    
    # Initialize server (same as stdio path)
    await _startup()
    _server_start_time = time.time()
    
    # Create SSE transport
    sse_transport = SseServerTransport("/messages/")
    
    # SSE endpoint handler
    async def handle_sse(request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await app.run(
                streams[0], streams[1],
                app.create_initialization_options()
            )
    
    # Build Starlette app
    starlette_app = Starlette(
        routes=[
            Route("/health", health_check),
            Route("/sse", handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
        on_shutdown=[_shutdown],
    )
    
    # Run uvicorn
    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()
```

**Design Decisions:**

1. **Separate file, not inline in server.py**: Keeps transport concerns isolated. `server.py` remains stdio-focused. This follows the single-responsibility principle.
2. **Import `app` from server.py**: The MCP Server instance is the same -- only the transport wrapper changes. No tool re-registration needed.
3. **Reuse `_startup()` / `_shutdown()`**: These hooks handle storage backend init, background tasks, and cleanup. Identical for both transport modes.
4. **`/messages/` endpoint**: Required by `SseServerTransport` -- the SSE endpoint tells clients to POST messages here.
5. **`/health` as plain HTTP**: Simple JSON response, no MCP protocol involvement. Docker `curl` can check it.

### 4.2 CLI Flag & Entry Point Changes (`__main__.py`)

**Location**: `src/scribe_mcp/__main__.py` (MODIFY, ~15 lines added)

Add `--transport` argument and `SCRIBE_TRANSPORT` env var support:

```python
# Modified _parse_args
def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the Scribe MCP server.",
    )
    parser.add_argument("--version", action="version", version="scribe-mcp 2.2")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=os.environ.get("SCRIBE_TRANSPORT", "stdio"),
        help="Transport mode (default: stdio, env: SCRIBE_TRANSPORT)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SCRIBE_TRANSPORT_PORT", "8200")),
        help="Port for SSE transport (default: 8200, env: SCRIBE_TRANSPORT_PORT)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("SCRIBE_TRANSPORT_HOST", "0.0.0.0"),
        help="Host for SSE transport (default: 0.0.0.0, env: SCRIBE_TRANSPORT_HOST)",
    )
    return parser.parse_args(argv)

# Modified main
def main(argv=None):
    args = _parse_args(argv)
    if args.transport == "sse":
        from scribe_mcp.server_sse import run_sse
        asyncio.run(run_sse(host=args.host, port=args.port))
    else:
        asyncio.run(server_main())
```

**Environment Variables (NEW):**

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCRIBE_TRANSPORT` | `stdio` | Transport mode selection |
| `SCRIBE_TRANSPORT_PORT` | `8200` | SSE server listen port |
| `SCRIBE_TRANSPORT_HOST` | `0.0.0.0` | SSE server bind address |

**pyproject.toml addition:**

```toml
[project.scripts]
# ... existing entries ...
scribe-server-sse = "scribe_mcp.server_sse:main"  # Direct SSE entry point
```

### 4.3 Dockerfile (Multi-Stage Build)

**Location**: `scribe_mcp/Dockerfile` (NEW FILE)

Follows verified best practices from Council's Docker deployment research:

```dockerfile
# ===== STAGE 1: BUILDER =====
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/

# Build wheel, excluding sentence-transformers
# Filter it out at install time to keep image small
RUN pip install --no-cache-dir --no-deps . \
    && pip install --no-cache-dir \
       asyncpg~=0.29 jinja2~=3.1 "mcp==1.26.0" \
       "numpy~=1.20" portalocker~=2.0 psutil~=7.1 \
       pyyaml~=6.0 rich~=13.7 tiktoken~=0.5 watchdog~=3.0

# ===== STAGE 2: RUNTIME =====
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (UID 1001, matching Council convention)
RUN groupadd -r scribe --gid=1001 && \
    useradd -r -g scribe --uid=1001 --create-home --shell=/bin/false scribe

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages \
     /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
WORKDIR /app
COPY src/ ./src/
COPY pyproject.toml ./

# Copy entrypoint script
COPY deploy/docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh

# Create volume mount points
RUN mkdir -p /app/.scribe && chown -R scribe:scribe /app

# Environment defaults
ENV PYTHONPATH="/app/src:${PYTHONPATH}" \
    SCRIBE_ROOT="/app" \
    SCRIBE_TRANSPORT="sse" \
    SCRIBE_TRANSPORT_PORT="8200" \
    SCRIBE_TRANSPORT_HOST="0.0.0.0" \
    PYTHONUNBUFFERED="1" \
    HF_HUB_DISABLE_PROGRESS_BARS="1"

EXPOSE 8200

USER scribe

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8200/health || exit 1

ENTRYPOINT ["tini", "--", "./docker-entrypoint.sh"]
CMD ["python", "-m", "scribe_mcp", "--transport", "sse"]
```

**Design Decisions:**

1. **Multi-stage build**: gcc/libpq-dev only in builder stage. Runtime gets libpq5 (shared lib only). Saves ~120MB.
2. **Explicit dependency install**: Installs each dep individually, EXCLUDING `sentence-transformers`. This avoids pulling in PyTorch (~2GB).
3. **tini as ENTRYPOINT**: Handles PID 1 signal forwarding and zombie reaping. Critical for subprocess cleanup.
4. **Non-root user**: `scribe` user with UID 1001 (matches Council's convention). Application files owned by this user.
5. **HEALTHCHECK via curl**: Simple HTTP check against `/health` endpoint. 10s start period allows DB init.
6. **PYTHONPATH set to /app/src**: Ensures `import scribe_mcp` resolves correctly without pip install in runtime.
7. **Entrypoint chain**: tini (PID 1) -\> docker-entrypoint.sh (secret bridging) -\> exec CMD (application). This matches Council's pattern. The entrypoint script bridges Docker secrets to env vars before handing off to the application.

### 4.4 Docker Compose Service

**Location**: `scribe_mcp/deploy/docker-compose.scribe.yaml` (NEW FILE)

Designed to be composable with Council's existing `docker-compose.yaml`:

```yaml
# Scribe MCP service definition
# Usage: docker compose -f deploy/docker-compose.yaml \
#        -f ../scribe_mcp/deploy/docker-compose.scribe.yaml up

services:
  scribe:
    build:
      context: ../  # scribe_mcp root
      dockerfile: Dockerfile
    image: scribe-mcp:latest
    container_name: scribe-mcp
    restart: unless-stopped
    
    networks:
      - backend
    
    # No ports exposed to host -- internal Docker network only
    # Council connects via http://scribe:8200/sse
    
    volumes:
      - scribe_data:/app/.scribe
    
    environment:
      SCRIBE_ROOT: /app
      SCRIBE_TRANSPORT: sse
      SCRIBE_TRANSPORT_PORT: "8200"
      SCRIBE_STORAGE_BACKEND: postgres
      SCRIBE_POSTGRES_SCHEMA: scribe
      SCRIBE_POSTGRES_POOL_MIN_SIZE: "2"
      SCRIBE_POSTGRES_POOL_MAX_SIZE: "10"
      SCRIBE_LOG_LEVEL: INFO
      HF_HUB_DISABLE_PROGRESS_BARS: "1"
    
    secrets:
      - scribe_db_url
    
    depends_on:
      postgres:
        condition: service_healthy
    
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.1'
    
    stop_grace_period: 30s
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8200/health"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 10s

secrets:
  scribe_db_url:
    file: ../../secrets/scribe_db_url.txt

volumes:
  scribe_data:
    name: scribe_data
```

**Design Decisions:**

1. **No exposed ports**: Scribe is internal-only. Council connects via Docker DNS (`http://scribe:8200/sse`). No host port mapping needed.
2. **File-based secrets**: `SCRIBE_DB_URL` contains credentials. Uses Docker secrets (mounted at `/run/secrets/scribe_db_url`). Entrypoint script bridges to env var.
3. **depends_on with service_healthy**: Scribe waits for Postgres to be ready before starting.
4. **Resource limits**: 1GB RAM / 0.5 CPU based on research (512MB typical, 1GB headroom). Reservations ensure minimum resources.
5. **stop_grace_period: 30s**: Allows time for graceful shutdown (cancel background tasks, flush DB connections).
6. **Pool size 10 (not 20)**: Container has limited resources; 10 connections is sufficient.

### 4.5 Entrypoint Script

**Location**: `scribe_mcp/deploy/docker-entrypoint.sh` (NEW FILE, ~30 lines)

```bash
#!/bin/bash
set -e

# Bridge Docker secrets to environment variables
# Pattern: Check env var first, then fall back to secret file
if [ -z "$SCRIBE_DB_URL" ] && [ -f /run/secrets/scribe_db_url ]; then
    export SCRIBE_DB_URL="$(cat /run/secrets/scribe_db_url)"
fi

# Ensure .scribe directory exists and is writable
if [ ! -d "/app/.scribe" ]; then
    mkdir -p /app/.scribe
fi

exec "$@"
```

### 4.6 .dockerignore

**Location**: `scribe_mcp/.dockerignore` (NEW FILE)

```
.scribe/
.git/
.github/
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
*.db
*.db-journal
tmp_tests/
tests/
data/
.codex/
.claude/
*.md
!README.md
deploy/
```

### 4.7 Council Integration

**Change Required in Council**: Update MCP client configuration to connect to Scribe over SSE instead of spawning as subprocess.

**Council config change** (in `council.yaml` or equivalent):

```yaml
# BEFORE (stdio subprocess):
mcp_servers:
  scribe:
    transport: stdio
    command: ["python", "-m", "scribe_mcp"]

# AFTER (SSE over Docker network):
mcp_servers:
  scribe:
    transport: sse
    url: "http://scribe:8200/sse"
```

**Note**: This change is in Council's repository, not Scribe's. The Scribe containerization architecture enables this but does not implement the Council-side change. Council's MCP client library must support SSE client connections (the MCP SDK provides `mcp.client.sse` for this).
<!-- ID: directory_structure -->
### New Files Created

```
scribe_mcp/
├── Dockerfile                          # NEW - Multi-stage build
├── .dockerignore                       # NEW - Build context filter
├── deploy/
│   ├── docker-compose.scribe.yaml      # NEW - Scribe service definition
│   └── docker-entrypoint.sh            # NEW - Secrets bridge script
├── src/scribe_mcp/
│   ├── server_sse.py                   # NEW - SSE transport entry point
│   ├── __main__.py                     # MODIFIED - --transport flag
│   └── server.py                       # UNCHANGED
└── pyproject.toml                      # MODIFIED - new script entry
```

### Container Filesystem Layout

```
/app/                                   # WORKDIR
├── src/scribe_mcp/                     # Application code (read-only)
├── pyproject.toml                      # Package metadata
├── docker-entrypoint.sh                # Entrypoint script
└── .scribe/                            # VOLUME MOUNT (scribe_data)
    ├── config/                         # Runtime config overlays
    ├── docs/dev_plans/                 # Project documentation
    ├── logs/                           # MCP server logs
    ├── backups/                        # Log rotation backups
    └── sentinel/                       # Sentinel mode artifacts
```
<!-- ID: data_storage -->
### Database Strategy

**Primary**: PostgreSQL (shared with Council MCP)
- **Database**: `agentkit` (Council's existing database)
- **Schema**: `scribe` (dedicated schema, created by `schema.py:114`)
- **Connection**: `postgresql://council:password@postgres:5432/agentkit` (via Docker secrets)
- **Pool**: Min 2, Max 10 connections (reduced from default 20 for container resource limits)
- **Extensions**: `pg_trgm` required, `pgvector` optional
- **Init**: Automatic -- Postgres backend runs `CREATE SCHEMA IF NOT EXISTS scribe` and all table migrations on first connection (`storage/postgres/schema.py`)

**Fallback**: SQLite (for local development without Docker)
- Unchanged behavior when `SCRIBE_DB_URL` is not set
- No container volume needed for `data/` directory when using Postgres

### Volume Strategy

| Volume | Mount Point | Purpose | Required |
|--------|-------------|---------|----------|
| `scribe_data` | `/app/.scribe` | Project docs, progress logs, config, backups | YES |
| `pg_data` | (postgres container) | Database files | YES (shared) |

**NOT mounted (no longer needed with Postgres backend):**
- `data/` directory (SQLite database lives here, not used in Docker)
- `.scribe/scribe.db` (deprecated, not used)

### Data Persistence Guarantees

1. **Database entries**: Persisted in Postgres with connection pooling and timeout protection
2. **Project documentation**: Persisted in `scribe_data` volume (PROGRESS_LOG.md, research docs, etc.)
3. **Graceful shutdown**: `_shutdown()` cancels background tasks and closes storage backend with 5s timeout
4. **Volume survives**: Container rebuilds, restarts, and image updates preserve data
<!-- ID: testing_strategy -->
### Test Layers

| Layer | What | How | Pass Criteria |
|-------|------|-----|---------------|
| **Unit** | SSE server startup/shutdown | pytest with mock uvicorn | Server initializes without error |
| **Unit** | Health endpoint response | Direct function call | Returns 200 with expected JSON |
| **Unit** | CLI flag parsing | argparse test | `--transport sse --port 8200` parsed correctly |
| **Integration** | MCP tools over SSE | MCP client connects, invokes `set_project` | Tool returns valid response |
| **Integration** | Postgres connection | Container connects to Postgres | Schema created, queries succeed |
| **Docker** | Image builds | `docker build` | Exits 0, image < 300MB |
| **Docker** | Container health | `docker run` + health check | HEALTHCHECK passes within 15s |
| **Docker** | Graceful shutdown | `docker stop` | Exits 0 within 30s, no data loss |
| **Docker** | Volume persistence | Restart container, check `.scribe/` | Data survives restart |
| **E2E** | Council-to-Scribe | Council invokes Scribe tool via SSE | Tool response received correctly |

### Testing Commands

```bash
# 1. Local SSE server test (no Docker)
python -m scribe_mcp --transport sse --port 8200 &
curl -f http://localhost:8200/health
kill %1

# 2. Docker build test
docker build -t scribe-mcp:test .
docker images scribe-mcp:test --format "{.Size}"  # Should be < 300MB

# 3. Docker run test
docker run -d --name scribe-test \
  -e SCRIBE_TRANSPORT=sse \
  -e SCRIBE_TRANSPORT_PORT=8200 \
  scribe-mcp:test
docker exec scribe-test curl -f http://localhost:8200/health
docker stop scribe-test && docker rm scribe-test

# 4. Docker Compose integration test
docker compose -f deploy/docker-compose.scribe.yaml up -d
docker compose ps  # scribe should show "healthy"
docker compose down
```
<!-- ID: deployment_operations -->
### Deployment Workflow

**Local Development (stdio, unchanged):**
```bash
# No Docker needed -- stdio transport works as always
python -m scribe_mcp  # or: scribe-mcp
```

**Local Development (SSE, for testing):**
```bash
python -m scribe_mcp --transport sse --port 8200
# Then connect MCP client to http://localhost:8200/sse
```

**Docker Deployment (Production):**
```bash
# From council_mcp/deploy/ directory:
docker compose -f docker-compose.yaml \
  -f ../../scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d --build

# Or standalone Scribe:
cd scribe_mcp
docker build -t scribe-mcp:latest .
docker compose -f deploy/docker-compose.scribe.yaml up -d
```

### Operational Commands

```bash
# Check health
curl http://localhost:8200/health  # From host (if port exposed)
docker exec scribe-mcp curl -f http://localhost:8200/health  # From container

# View logs
docker logs scribe-mcp --tail 100 -f

# Restart
docker compose restart scribe

# Stop gracefully (30s grace period)
docker compose stop scribe

# Resource monitoring
docker stats scribe-mcp

# Database migration (one-time, if migrating from SQLite)
docker exec scribe-mcp python -m scribe_mcp.scripts.migrate_sqlite_to_postgres
```

### Environment Variable Reference (Complete)

| Variable | Default | Docker Value | Purpose |
|----------|---------|-------------|---------|
| `SCRIBE_TRANSPORT` | `stdio` | `sse` | Transport mode |
| `SCRIBE_TRANSPORT_PORT` | `8200` | `8200` | SSE listen port |
| `SCRIBE_TRANSPORT_HOST` | `0.0.0.0` | `0.0.0.0` | SSE bind address |
| `SCRIBE_ROOT` | auto-detect | `/app` | Repository root |
| `SCRIBE_DB_URL` | None | via secret | Postgres DSN |
| `SCRIBE_STORAGE_BACKEND` | auto | `postgres` | Backend type |
| `SCRIBE_POSTGRES_SCHEMA` | `scribe` | `scribe` | Schema name |
| `SCRIBE_POSTGRES_POOL_MIN_SIZE` | `2` | `2` | Min pool |
| `SCRIBE_POSTGRES_POOL_MAX_SIZE` | `20` | `10` | Max pool |
| `SCRIBE_LOG_LEVEL` | `WARNING` | `INFO` | Log verbosity |
| `HF_HUB_DISABLE_PROGRESS_BARS` | unset | `1` | Suppress ML output |
| `PYTHONUNBUFFERED` | unset | `1` | Immediate log output |

### Monitoring & Alerting

- **Health check**: Docker HEALTHCHECK polls `/health` every 30s. Container marked unhealthy after 3 consecutive failures.
- **Logs**: Standard Docker logging driver. Use `docker logs` or ship to centralized logging (future).
- **Resource alerts**: Docker stats shows memory/CPU. Set up alerts for >80% memory usage.
- **Postgres metrics**: Connection pool usage visible via `pg_stat_activity`.
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Council MCP client SSE support | Council team | OPEN | Does Council's MCP client library support SSE connections? Need to verify `mcp.client.sse` compatibility |
| Volume UID/GID mapping | Ops | OPEN | Container uses UID 1001. Host volume permissions may need adjustment |
| Postgres user/role for Scribe | DBA/Ops | OPEN | Can Scribe share Council's `council` user or need dedicated `scribe_user` role? |
| SQLite-to-Postgres data migration | Ops | OPEN | 108MB existing SQLite DB. Migration script exists but needs testing in container context |
| sentence-transformers opt-in | Architecture | DEFERRED | Future: separate Docker image variant with ML deps if vector indexing needed |
| Streamable HTTP upgrade | Architecture | DEFERRED | Replace SSE with Streamable HTTP when scaling demands it |
| Authentication layer | Security | DEFERRED | Not needed while Docker network provides isolation. Required if exposing publicly |
| Log shipping | Ops | DEFERRED | Docker logging driver to centralized system (Loki, ELK) |
<!-- ID: references_appendix -->
### Research Documents
- `RESEARCH_TRANSPORT_LAYER.md` -- MCP SDK 1.26.0 SSE/HTTP transport analysis
- `RESEARCH_STORAGE_CONFIG.md` -- Postgres backend, schema isolation, env vars
- `RESEARCH_CONTAINERIZATION_REQS.md` -- Dependencies, resources, security audit
- `RESEARCH_DOCKER_BEST_PRACTICES.md` -- Council Docker patterns (canonical reference)

### Key Source Files (Verified)
- `src/scribe_mcp/server.py` -- MCP Server instance (`app`, line 111), lifecycle hooks (`_startup`, `_shutdown`)
- `src/scribe_mcp/__main__.py` -- CLI entry point (31 lines, to be extended)
- `src/scribe_mcp/storage/__init__.py` -- Backend factory (`create_storage_backend`)
- `src/scribe_mcp/config/settings.py` -- Environment variable mapping (280 lines)
- `pyproject.toml` -- Dependencies, entry points, package config

### MCP SDK References
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) -- Official SDK
- [MCP SSE Module](https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/sse.py) -- `SseServerTransport` implementation
- [MCP Transport Spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) -- Protocol specification

### Docker References
- [Docker Multi-Stage Builds](https://collabnix.com/docker-multi-stage-builds-for-python-developers-a-complete-guide/)
- [tini init process](https://github.com/krallin/tini) -- PID 1 signal handling
- [Docker Compose Secrets](https://docs.docker.com/compose/how-tos/use-secrets/) -- File-based secrets

### Architecture Decisions Log
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Transport Protocol | SSE (not Streamable HTTP) | Simpler, proven, upgrade path available |
| Port | 8200 | Avoids 8015-8017 used/reserved by Council |
| Base Image | python:3.11-slim | Alpine breaks asyncpg; slim is optimal |
| Init Process | tini | PID 1 signal forwarding, zombie reaping |
| User | scribe (UID 1001) | Matches Council convention, non-root |
| Dependencies | No additions needed | starlette/uvicorn are MCP SDK transitive deps |
| ML Stack | Excluded | sentence-transformers adds 2GB+, not needed |
| Pool Size | 10 (not 20) | Container resource limits |
| Ports Exposed | None to host | Internal Docker network only |
| Secrets | File-based | Docker secrets pattern, not env vars |
