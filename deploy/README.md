# Scribe MCP - Docker Deployment Guide

This directory contains production-ready Docker configurations for deploying Scribe MCP as a containerized service with SSE (Server-Sent Events) transport.

## Overview

The Docker deployment provides:

- **SSE Transport**: HTTP-based MCP communication on port 8200 (replaces stdio)
- **PostgreSQL Integration**: Shared database with Council MCP for enterprise deployments
- **Compose Overlay Pattern**: Seamlessly integrates with Council's docker-compose infrastructure
- **Standalone Option**: Can run independently with SQLite for simpler deployments
- **Health Checks**: Built-in Docker health monitoring via `/health` endpoint
- **Security**: Non-root user (UID 1001), Docker secrets for credentials, minimal attack surface

## Quick Start

### Standalone (SQLite, No PostgreSQL)

Get Scribe running in under 5 minutes:

```bash
# From scribe_mcp root directory
docker build -f deploy/Dockerfile -t scribe-mcp:latest .

docker run -d \
  --name scribe-mcp \
  -p 8200:8200 \
  -v scribe_data:/app/.scribe \
  scribe-mcp:latest
```

Verify it's running:
```bash
curl http://localhost:8200/health
# {"status":"healthy","service":"scribe-mcp","version":"2.2","transport":"sse","uptime_seconds":42}
```

### With Docker Compose (PostgreSQL)

Use the compose overlay pattern to run Scribe alongside Council with shared PostgreSQL:

```bash
# From MCP_SPINE root (parent of scribe_mcp/ and council_mcp/)
docker compose \
  -f council_mcp/deploy/docker-compose.yaml \
  -f scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d
```

This merges both compose files, creating a unified stack where:
- Council and Scribe share the `backend` network
- Both use the same PostgreSQL instance
- Council connects to Scribe via `http://scribe:8200/sse`

## Prerequisites

- **Docker 20.10+** - Container runtime
- **Docker Compose v2.0+** - For multi-service orchestration
- **PostgreSQL credentials** - If using Postgres backend (see Configuration below)

## Configuration

### Environment Variables

All configuration is done via environment variables. Defaults are set in the Dockerfile and can be overridden in docker-compose.scribe.yaml or via `docker run -e`.

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRIBE_TRANSPORT` | `sse` | Transport mode (use `sse` for Docker deployments) |
| `SCRIBE_TRANSPORT_PORT` | `8200` | HTTP port for SSE endpoints |
| `SCRIBE_TRANSPORT_HOST` | `0.0.0.0` | Network interface to bind (0.0.0.0 = all interfaces) |
| `SCRIBE_ROOT` | `/app` | Application root directory inside container |
| `SCRIBE_STORAGE_BACKEND` | `sqlite` | Storage backend (`sqlite` or `postgres`) |
| `SCRIBE_DB_URL` | (none) | PostgreSQL connection string (loaded from secret, see below) |
| `SCRIBE_POSTGRES_SCHEMA` | `scribe` | PostgreSQL schema name for Scribe tables |
| `SCRIBE_POSTGRES_POOL_MIN_SIZE` | `2` | Minimum connection pool size |
| `SCRIBE_POSTGRES_POOL_MAX_SIZE` | `10` | Maximum connection pool size |
| `SCRIBE_LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |

### Docker Secrets (PostgreSQL Authentication)

For production deployments, use Docker secrets instead of environment variables for database credentials:

1. **Create the secret file:**
   ```bash
   mkdir -p secrets/
   echo -n "postgresql://council:your_password@postgres:5432/agentkit?options=-c%20search_path%3Dscribe" \
     > secrets/scribe_db_url.txt
   chmod 600 secrets/scribe_db_url.txt
   ```

2. **The entrypoint script reads this secret:**
   - Mounted at `/run/secrets/scribe_db_url` inside container
   - `deploy/docker-entrypoint.sh` exports it as `SCRIBE_DB_URL`
   - Not visible in `docker inspect` or process listings

3. **Connection string format:**
   ```
   postgresql://<user>:<password>@<host>:<port>/<database>?options=-c%20search_path%3D<schema>
   ```

## Connecting MCP Clients

### SSE Transport Configuration

Configure your MCP client (Claude Code, etc.) to connect via HTTP SSE instead of stdio:

```json
{
  "mcpServers": {
    "scribe": {
      "url": "http://localhost:8200/sse"
    }
  }
}
```

**Key differences from stdio mode:**

| Aspect | stdio (legacy) | SSE (Docker) |
|--------|---------------|--------------|
| Connection | Subprocess spawn | HTTP connection |
| Transport | stdin/stdout pipes | Server-Sent Events + POST |
| Endpoints | N/A | `/sse`, `/messages/`, `/health` |
| Health checks | Process monitoring | HTTP health endpoint |
| Scalability | Local only | Network-accessible, load-balanceable |

### Endpoints

- **`/health`** - JSON health check for Docker HEALTHCHECK and monitoring tools
- **`/sse`** - SSE stream endpoint where MCP clients connect
- **`/messages/`** - POST endpoint where clients send MCP protocol messages

## PostgreSQL Setup

### Schema Initialization

Scribe automatically creates its PostgreSQL schema and tables on first startup. No manual SQL required.

**What happens on first startup:**

1. Connects to PostgreSQL using `SCRIBE_DB_URL`
2. Creates schema `SCRIBE_POSTGRES_SCHEMA` (default: `scribe`) if not exists
3. Creates tables: `scribe_projects`, `scribe_log`, `agent_sessions`
4. Sets up indexes for performance

**Requirements:**

- PostgreSQL 12+ (tested with PostgreSQL 16)
- Database must exist (e.g., `agentkit`)
- User must have `CREATE` privileges on the database
- Scribe creates and manages its own schema

### Shared Database with Council

When deploying with Council, both services use the same PostgreSQL database with separate schemas:

- Council: `council` schema (or default `public`)
- Scribe: `scribe` schema

This allows:
- Single PostgreSQL instance for both services
- Schema isolation (no table name conflicts)
- Simplified connection pooling and backups

## Council Integration

### Compose Overlay Pattern

The recommended deployment uses Docker Compose file merging:

```bash
docker compose \
  -f council_mcp/deploy/docker-compose.yaml \
  -f scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d
```

**How it works:**

1. Council's base compose defines:
   - PostgreSQL service
   - Backend network
   - Council MCP service

2. Scribe's overlay adds:
   - Scribe MCP service
   - Volume for Scribe data
   - Same backend network (merged)
   - Dependency on postgres service

3. Docker Compose merges these into a unified stack

**Council-to-Scribe communication:**

Council connects to Scribe via Docker DNS:
```
http://scribe:8200/sse
```

No host port mapping needed - services communicate over the internal `backend` network.

### Network Architecture

```
┌─────────────────┐
│  Claude Code    │ (external client)
└────────┬────────┘
         │ http://localhost:8200/sse (if Scribe port exposed)
         │
┌────────▼─────────────────────────────────────┐
│         Docker Host                          │
│  ┌──────────────┐    ┌──────────────┐       │
│  │   Council    │◄──►│   Scribe     │       │
│  │   :8100      │    │   :8200      │       │
│  └──────┬───────┘    └──────┬───────┘       │
│         │                   │                │
│         │   backend network │                │
│         └───────────┬───────┘                │
│                     │                        │
│            ┌────────▼────────┐               │
│            │   PostgreSQL    │               │
│            │   :5432         │               │
│            └─────────────────┘               │
└──────────────────────────────────────────────┘
```

## Architecture

### Multi-Stage Build

The Dockerfile uses a two-stage build to minimize image size:

1. **Builder stage** (`python:3.11-slim`):
   - Installs build dependencies (gcc, libpq-dev)
   - Builds Python packages
   - Deliberately excludes `sentence-transformers` to avoid PyTorch (~2GB)

2. **Runtime stage** (`python:3.11-slim`):
   - Copies only built packages (no build tools)
   - Installs runtime dependencies (libpq5, curl, tini)
   - Creates non-root user (UID 1001)
   - Sets up health checks

**Image size:** ~330MB (vs ~2.5GB with PyTorch)

### Process Management

- **Init system:** `tini` handles signal forwarding and zombie reaping
- **Main process:** Python MCP server (via `scribe-server-sse`)
- **Graceful shutdown:** SIGTERM propagation with 30-second grace period

### Security

- **Non-root user:** Runs as `scribe` (UID 1001), not root
- **Secrets:** Database credentials via Docker secrets, not environment variables
- **Minimal attack surface:** Only necessary packages installed, no build tools in runtime image
- **Health checks:** Automatic container restart on health check failure

## Troubleshooting

### Port Conflicts

**Symptom:** `docker run` fails with "port already in use"

**Solution:**
```bash
# Check what's using port 8200
lsof -i :8200

# Use a different port
docker run -p 8300:8200 scribe-mcp:latest
```

### "Storage: sqlite" When Expecting Postgres

**Symptom:** Health check shows `"storage": "sqlite"` but you configured Postgres

**Common causes:**
1. **Secret file not found:** Check `secrets/scribe_db_url.txt` exists
2. **Secret file path wrong:** Path in compose is relative to compose file location
3. **Connection string invalid:** Verify format with `cat secrets/scribe_db_url.txt`
4. **Postgres not ready:** Check `docker compose logs postgres`

**Debug:**
```bash
# Check if secret is mounted inside container
docker exec scribe-mcp cat /run/secrets/scribe_db_url
# Should print your connection string

# Check logs for connection errors
docker compose logs scribe
```

### Health Check Failures

**Symptom:** Container status shows "unhealthy"

**Debug steps:**
```bash
# Check if service is running
docker compose ps

# View logs
docker compose logs scribe

# Manual health check
docker exec scribe-mcp curl -f http://localhost:8200/health

# Check if port is bound
docker exec scribe-mcp netstat -tlnp | grep 8200
```

**Common causes:**
- Server startup failed (check logs)
- Port binding failed (check for conflicts)
- Health check timeout too short (increase in compose)

### Container Won't Start

**Check logs first:**
```bash
docker compose logs scribe --tail=50
```

**Common issues:**
1. **Missing environment variables:** Check compose file has all required vars
2. **Database connection failed:** Verify `SCRIBE_DB_URL` and Postgres is healthy
3. **Permission errors:** Check volume mounts have correct ownership
4. **Python import errors:** Rebuild image with `docker compose build --no-cache scribe`

## File Inventory

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage production build definition |
| `docker-compose.scribe.yaml` | Compose overlay for integration with Council |
| `docker-entrypoint.sh` | Entrypoint script that bridges secrets to environment vars |
| `README.md` | This file - deployment documentation |

**Related files:**
- `../src/scribe_mcp/server_sse.py` - SSE transport implementation
- `../src/scribe_mcp/__main__.py` - CLI entry point with `--transport sse` flag
- `../pyproject.toml` - Python package definition

## Additional Resources

- **Main README:** `../README.md` - Project overview, local development setup
- **Scribe Usage Guide:** `../docs/Scribe_Usage.md` - Tool reference and API docs
- **Council Integration:** `../../council_mcp/deploy/` - Council Docker deployment

---

**Questions or issues?** Check logs first (`docker compose logs scribe`), then consult the main README or open an issue.
