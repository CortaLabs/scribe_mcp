---
id: council_docker_overhaul-research-docker-best-practices
title: 'RESEARCH: Docker Best Practices for Council MCP'
doc_type: RESEARCH_DOCKER_BEST_PRACTICES
doc_name: RESEARCH_DOCKER_BEST_PRACTICES
category: engineering
status: complete
version: '1.0'
last_updated: 2026-02-16 03:11:57 UTC
maintained_by: Corta Labs
created_by: Lens (Research Analyst)
owners: []
related_docs: []
tags:
- docker
- containerization
- best-practices
- devops
summary: Comprehensive Docker best practices for Council MCP multi-service containerization
---

# RESEARCH: Docker Best Practices for Council MCP

**Author:** Lens (Research Analyst)
**Date:** 2026-02-15
**Project:** council_docker_overhaul (imported into scribe_containerization)
**Status:** Complete
**Confidence:** HIGH (source code verified + industry best practices cross-referenced)

---

## Executive Summary
<!-- ID: executive_summary -->

This research documents Docker best practices for containerizing Council MCP -- a multi-service Python application consisting of a daemon process (MCP server on port 8016), a web UI (FastAPI on port 8015), PostgreSQL with pgvector, and a Scribe MCP subprocess. The system must run identically on local WSL2 development and a remote Hetzner CCX23 VPS (Ubuntu 24.04).

**Primary Objective:** Produce actionable Docker containerization recommendations that Blueprint can use to design a complete Docker overhaul achieving local/remote parity, production security, and operational reliability.

**Current State Assessment**: The existing Docker setup (`deploy/`) already follows many best practices:
- Multi-stage Dockerfile with base/daemon/web stages [GOOD]
- Docker Compose with secrets, named volumes, and health checks [GOOD]
- Dev override file with bind mounts for hot-reload [GOOD]
- Well-documented entrypoint script bridging secrets to env vars [GOOD]

**Key Gaps Identified** (from deploy experience and code review):
1. No non-root user in containers (security risk) [HIGH]
2. No init process (tini/dumb-init) for PID 1 signal handling -- daemon manages subprocesses [HIGH]
3. Health check on daemon hits `/health` but no such endpoint exists on daemon server (only web has it) [HIGH]
4. gcc remains in runtime image (should be build-stage only) [MEDIUM]
5. Web service depends_on daemon but without health check condition [MEDIUM]
6. No `.env.example` template for secrets setup [MEDIUM]
7. No graceful shutdown for subprocess tree (Scribe MCP child processes) [MEDIUM]
8. Missing SCRIBE_DB_URL secret in production compose [LOW]

**Key Takeaways:**
- The existing setup is ~70% complete -- well-structured multi-stage build, proper compose separation, secrets pattern
- Critical gaps are security (non-root user) and reliability (PID 1 init, health checks, graceful shutdown)
- The daemon health check is the most urgent fix: Docker HEALTHCHECK curls a nonexistent endpoint
- Adding tini as init process is essential since the daemon spawns Scribe as a child subprocess

---

## Finding 1: Multi-Stage Dockerfile Patterns
<!-- ID: findings -->

**Confidence:** HIGH

### Current State (deploy/Dockerfile)
The existing Dockerfile uses a 3-stage pattern: `base` -> `daemon` / `web`. This is fundamentally sound.

**What works well:**
- Dependency caching: `pyproject.toml` copied before source code (line 91-93)
- AgentKit wheel pre-built and installed from `vendor/` (line 89-90)
- `COPY . .` after deps install maximizes layer cache hits
- Separate targets for daemon/web with different EXPOSE/CMD

**What needs improvement:**

1. **gcc in runtime image (MEDIUM):** `gcc` is installed in the base stage (line 56) and inherited by both daemon and web. gcc is only needed to compile psycopg2 (C extension). Solution: use a proper builder/runtime split.

   ```dockerfile
   # RECOMMENDED: 3-stage with builder separation
   FROM python:3.11-slim AS builder
   RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev
   COPY vendor/agentkit*.whl ./vendor/
   RUN pip install --no-cache-dir ./vendor/agentkit*.whl
   COPY pyproject.toml ./
   COPY src/ ./src/
   RUN pip install --no-cache-dir .

   FROM python:3.11-slim AS runtime
   RUN apt-get update && apt-get install -y --no-install-recommends \
       libpq5 curl tini && rm -rf /var/lib/apt/lists/*
   COPY --from=builder /usr/local/lib/python3.11/site-packages ...
   COPY --from=builder /usr/local/bin ...

   FROM runtime AS daemon
   FROM runtime AS web
   ```

   **Impact:** Removes ~120MB of build tools from final image.

2. **No non-root user (HIGH):** Containers run as root. Every best practice guide flags this as critical.

   ```dockerfile
   RUN groupadd -r council --gid=1001 && \
       useradd -r -g council --uid=1001 --no-create-home --shell=/bin/false council
   RUN chown -R council:council /app
   USER council
   ```

3. **No init process (HIGH):** The daemon manages Scribe as a subprocess. Without an init process, zombie processes can accumulate and SIGTERM may not propagate to children.

   ```dockerfile
   RUN apt-get install -y --no-install-recommends tini
   ENTRYPOINT ["tini", "--", "./docker-entrypoint.sh"]
   ```

4. **Image choice:** `python:3.11-slim` is correct. Alpine breaks psycopg2 (musl patches needed). Full image wastes ~750MB. Slim-bookworm is the sweet spot.

### Recommended Dockerfile Structure

```
python:3.11-slim AS builder    # gcc, libpq-dev, pip install
python:3.11-slim AS runtime    # libpq5, curl, tini, non-root user
runtime AS daemon              # ENTRYPOINT with tini, CMD council start
runtime AS web                 # ENTRYPOINT with tini, CMD python -m ...
```

**Evidence:** `deploy/Dockerfile` lines 44-186, cross-referenced with Docker Python best practices and TestDriven.io guide.

---

## Finding 2: Docker Compose Dev/Prod Parity
<!-- ID: finding_2 -->

**Confidence:** HIGH

### Current State
- `deploy/docker-compose.yaml` (production, 367 lines) -- secrets, named volumes, resource limits
- `deploy/docker-compose.dev.yaml` (dev override, 131 lines) -- relaxed limits, bind mounts, env vars

### What Works Well
- Base + override pattern is the correct approach
- Dev overlay relaxes resource limits and uses simpler auth
- Bind mounts for `src/` and `.council/` enable hot-reload
- Production uses Docker secrets via files, dev uses env vars

### What Needs Improvement

1. **Web depends_on without health condition (MEDIUM):**
   ```yaml
   # CURRENT (line 240-241):
   depends_on:
     - council-daemon    # No health check condition!

   # RECOMMENDED:
   depends_on:
     council-daemon:
       condition: service_healthy
   ```
   Without the health condition, the web container starts as soon as daemon container launches, not when it is healthy.

2. **Missing SCRIBE_DB_URL in production (LOW):**
   Dev override sets `SCRIBE_DB_URL` (line 96) but production compose does not provide it. The entrypoint handles the secret (line 75-79) but no secret file is defined.

3. **No `.env.example` (MEDIUM):**
   New developers must read the deployment guide to understand required secrets. A `.env.example` would be self-documenting:
   ```
   POSTGRES_PASSWORD=changeme
   DATABASE_URL=postgresql://council:changeme@postgres:5432/agentkit
   COUNCIL_API_KEY=ck_your_key_here
   OPENAI_API_KEY=sk-your-key-here
   SCRIBE_DB_URL=postgresql://council:changeme@postgres:5432/agentkit
   ```

4. **No profiles for optional services (LOW):**
   ```yaml
   ray-head:
     profiles: ["gpu", "distributed"]
   ```
   Usage: `docker compose --profile gpu up`

### Recommended Compose Strategy
```
docker-compose.yaml          # Base: all services, production defaults
docker-compose.dev.yaml      # Dev override: bind mounts, relaxed limits, env vars
.env.example                 # Template for environment variables
```

**Evidence:** `deploy/docker-compose.yaml` lines 1-367, `deploy/docker-compose.dev.yaml` lines 1-131.

---

## Finding 3: Health Checks
<!-- ID: finding_3 -->

**Confidence:** HIGH

### CRITICAL BUG: Daemon Health Check is Broken

**Daemon health check (BROKEN):**
```dockerfile
# deploy/Dockerfile line 157-158
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8016/health || exit 1
```
The daemon (server.py) is an MCP server using WebSocket transport. **There is NO `/health` HTTP endpoint on port 8016.** The daemon does not run an HTTP server -- it runs a WebSocket server. This health check always fails, meaning Docker perpetually marks the daemon container as unhealthy.

**Web health check (WORKS):** `src/council_mcp/web/routes/health.py` has `/health` endpoint checking MCP pool and WebSocket manager. Returns JSON with council/scribe connectivity status.

**PostgreSQL health check (GOOD):** Uses native `pg_isready -U council -d agentkit` utility.

### Recommended Solutions

**For daemon (PICK ONE):**

**Option A -- Add lightweight HTTP health endpoint (PREFERRED):**
```python
# Minimal HTTP health server alongside MCP WebSocket server
from aiohttp import web

async def create_health_server(port=8017):
    async def health(request):
        scribe_ok = _RUNTIME_CONTEXT.get("scribe_client") is not None
        return web.json_response({
            "status": "healthy" if scribe_ok else "degraded",
            "scribe": "connected" if scribe_ok else "disconnected",
        })
    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner
```
Then in Dockerfile: `HEALTHCHECK CMD curl -f http://localhost:8017/health || exit 1`
And expose port 8017 in compose for internal health checks.

**Option B -- File-based health check (simpler):**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD test -f /tmp/council-daemon-healthy || exit 1
```
Daemon writes `/tmp/council-daemon-healthy` on successful startup and updates timestamp periodically. Check script verifies file exists and is recent.

**Option C -- WebSocket-based check:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import websockets,asyncio; asyncio.run(websockets.connect('ws://localhost:8016'))" || exit 1
```
Slower (~2s per check) but verifies actual WebSocket connectivity.

**Recommendation:** Option A is best for production. Adds minimal HTTP surface for health, future metrics, and readiness. Option C is acceptable as a quick fix.

**For web -- split liveness/readiness:**
```python
@router.get("/health/live")
async def liveness():
    """Process is alive -- always returns 200 unless crashed."""
    return {"status": "ok"}

@router.get("/health/ready")
async def readiness():
    """Can serve traffic -- checks all dependencies."""
    mcp_pool = get_mcp_pool()
    council_ok = mcp_pool.get("council") is not None
    scribe_ok = mcp_pool.get("scribe") is not None
    if not (council_ok and scribe_ok):
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}
```

Docker HEALTHCHECK should use `/health/ready`. This enables proper health semantics:
- **Liveness:** Is the process running? (restart if not)
- **Readiness:** Can it serve traffic? (don't route traffic if not)
- **Startup:** Has it finished initializing? (give it time before checking)

**Evidence:** `deploy/Dockerfile` lines 157-158, 182-183; `src/council_mcp/web/routes/health.py` lines 28-46; `src/council_mcp/server.py` (WebSocket only, no HTTP server).

---

## Finding 4: Secrets Management
<!-- ID: finding_4 -->

**Confidence:** HIGH

### Current State -- Mostly Good
- File-based Docker secrets mounted at `/run/secrets/<name>`
- Entrypoint script (`deploy/docker-entrypoint.sh`) bridges secrets to env vars
- Dev override uses plain env vars for simplicity
- Separate files per secret value (pg_password, database_url, api_key, openai_api_key)

### What Works Well
- File-based secrets are more secure than env vars (don't leak in `docker inspect`)
- Entrypoint pattern: check env var first, then fall back to secret file
- Each secret in its own file for granular access control

### Improvements Needed

1. **Missing SCRIBE_DB_URL secret (LOW):** Entrypoint handles it (line 75-79) but no secret defined in compose. Add:
   ```yaml
   secrets:
     scribe_db_url:
       file: ../secrets/scribe_db_url.txt
   ```

2. **No `.env.example` (MEDIUM):** Add template at repo root for developer onboarding.

3. **Secrets directory permissions (MEDIUM):** Enforce in setup/deploy script:
   ```bash
   mkdir -p /opt/council_mcp/secrets
   chmod 700 /opt/council_mcp/secrets
   chmod 600 /opt/council_mcp/secrets/*.txt
   ```

### Recommendation
Keep current file-based pattern -- it is correct for this scale. Add missing SCRIBE_DB_URL secret definition and `.env.example`.

For future scale: Consider Mozilla SOPS for encrypted secrets in git, or HashiCorp Vault for dynamic secret rotation.

**Evidence:** `deploy/docker-entrypoint.sh` lines 46-88; `deploy/docker-compose.yaml` lines 334-367.

---

## Finding 5: Process Management (PID 1)
<!-- ID: finding_5 -->

**Confidence:** HIGH

### The PID 1 Problem
When Docker starts a container, the main process becomes PID 1. PID 1 has special kernel behavior:
- Default signal handlers do NOT apply (SIGTERM is silently ignored unless explicitly handled)
- PID 1 is responsible for reaping zombie child processes
- If PID 1 exits, all container processes are killed

### Current State
- `server.py` lines 1125-1126: Registers SIGTERM/SIGINT handlers via `signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))`
- Entrypoint uses `exec "$@"` correctly (replaces shell with app, so app becomes PID 1)
- Signal handlers work for the daemon process itself
- BUT: signals do NOT propagate to Scribe subprocess (child of daemon)
- Scribe MCP runs as a child process managed by `process_manager.py`

### Why This Matters for Council MCP
The daemon spawns Scribe as a subprocess. When `docker stop` sends SIGTERM:
1. Daemon catches it and calls `sys.exit(0)`
2. Python runs atexit handlers (`_cleanup_pid_file`, `_cleanup_bridge`, `_stop_stale_cleanup`)
3. BUT: Scribe subprocess may not receive a signal or have time to flush
4. After 10s (Docker default), SIGKILL kills everything -- data loss possible

### Recommended Solution: tini

```dockerfile
# Install in runtime stage
RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

# In daemon/web stages
ENTRYPOINT ["tini", "--", "./docker-entrypoint.sh"]
```

**What tini does:**
1. Becomes PID 1 (handles kernel's special PID 1 behavior)
2. Spawns the application as PID 2
3. Forwards SIGTERM/SIGINT to the entire process group
4. Reaps zombie child processes automatically
5. Exits with the application's exit code

**Why tini over dumb-init:**
- tini is smaller (~30KB vs ~50KB)
- tini is included in Docker as `--init` flag
- Both handle signal forwarding and zombie reaping equally well
- tini is more commonly used in Python container ecosystems

**Alternative: Docker Compose `init: true`:**
```yaml
council-daemon:
  init: true  # Uses Docker's built-in tini
```
Simpler but less portable. Explicit tini in Dockerfile is preferred.

### Graceful Shutdown Chain (with tini)
```
docker stop
  -> SIGTERM
  -> tini (PID 1)
  -> forwards SIGTERM to process group
  -> council daemon catches SIGTERM
  -> daemon signals Scribe subprocess (SIGTERM)
  -> daemon waits for Scribe to exit (grace period)
  -> daemon closes WebSocket connections
  -> daemon runs atexit handlers
  -> daemon exits
  -> tini reaps any remaining children
  -> tini exits
  -> container stops
```

Add `stop_grace_period: 30s` to give daemon time for graceful shutdown:
```yaml
council-daemon:
  stop_grace_period: 30s  # Default is 10s, too short for subprocess cleanup
```

**Evidence:** `src/council_mcp/server.py` lines 1125-1126; `deploy/docker-entrypoint.sh` line 104; `src/council_mcp/process_manager.py`.

---

## Finding 6: Persistent Data and Volumes
<!-- ID: finding_6 -->

**Confidence:** HIGH

### Current State
```yaml
# docker-compose.yaml lines 310-313
volumes:
  pg_data:         # PostgreSQL data directory
  council_data:    # .council/ configuration and state
  scribe_data:     # .scribe/ logs and project documents
```

### Assessment

**PostgreSQL (pg_data) -- CORRECT:**
- Named volume is the right choice for database data
- Survives container rebuilds and restarts
- Never share between multiple Postgres instances
- Recommendation: Add `shm_size: 256mb` to postgres service for better performance

**Council data (council_data) -- CORRECT but needs bootstrap:**
- `.council/` contains configuration generated by `council init`
- First deploy on empty volume needs bootstrap strategy
- Options: init container, entrypoint check, or pre-populated volume

**Scribe data (scribe_data) -- CORRECT:**
- Project logs and documents
- Named volume preserves across rebuilds

### Recommendations

1. **Keep named volumes for production** -- pg_data, council_data, scribe_data
2. **Add bind mount in dev override for `.scribe/`** (for direct access to logs)
3. **Add backup strategy:**
   ```bash
   # Backup PostgreSQL
   docker exec council-postgres pg_dump -U council agentkit > backup.sql

   # Backup named volumes
   docker run --rm -v council-mcp_pg_data:/data -v $(pwd):/backup \
     alpine tar czf /backup/pg_data.tar.gz -C /data .
   ```
4. **Add `shm_size` to postgres:**
   ```yaml
   postgres:
     shm_size: 256mb  # Prevent "out of shared memory" errors
   ```

**Evidence:** `deploy/docker-compose.yaml` lines 299-313; `deploy/docker-compose.dev.yaml` lines 85-87.

---

## Finding 7: Networking
<!-- ID: finding_7 -->

**Confidence:** HIGH

### Assessment
Single `backend` bridge network is appropriate. All services communicate:
- Web -> Daemon (WebSocket on 8016)
- Daemon -> Postgres (5432)
- Web -> Postgres (5432)
- Scribe (subprocess of daemon) -> Postgres

Port binding to `127.0.0.1` is correct -- Tailscale handles external access. No accidental internet exposure.

### Service Discovery
Services reference each other by name (built-in Docker DNS):
- `postgres:5432` -- database
- `council-daemon:8016` -- MCP WebSocket
- `council-web:8015` -- Web UI (if needed internally)

### Optional Future: Network Segmentation
For defense-in-depth, split into frontend/backend:
```yaml
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true  # No external access

services:
  postgres:
    networks: [backend]
  council-daemon:
    networks: [frontend, backend]
  council-web:
    networks: [frontend, backend]
```
**Assessment:** Not needed at current scale. Single network with localhost binding is sufficient. Revisit when adding untrusted services.

**Evidence:** `deploy/docker-compose.yaml` lines 316-331.

---

## Finding 8: Local/Remote Parity
<!-- ID: finding_8 -->

**Confidence:** HIGH

### Current Strategy -- Correct
- Same base compose file for both environments
- Dev overlay for local development with bind mounts and env vars
- Same service names, same network topology
- Production uses Docker secrets, dev uses plain env vars

### What Needs Improvement

1. **Deployment workflow (MEDIUM):** Currently relies on manual rsync + ssh. Codify into a script:
   ```bash
   #!/bin/bash
   # deploy.sh
   rsync -avz --exclude='.git' --exclude='secrets/' \
     . hetzner:/opt/council_mcp/
   ssh hetzner "cd /opt/council_mcp && docker compose -f deploy/docker-compose.yaml up -d --build"
   ```

2. **Config parity (MEDIUM):** Non-secret parts of `.council/council.yaml` should be in git. Secret-dependent config should use environment variable interpolation.

3. **Build vs pull (LOW for now):** Currently builds images on-server from source. For faster deploys, consider a container registry (GitHub Container Registry):
   ```bash
   # Build + push locally
   docker build --target daemon -t ghcr.io/org/council-daemon:latest .
   docker push ghcr.io/org/council-daemon:latest

   # Pull on server
   docker compose pull && docker compose up -d
   ```

### Recommended Commands
```bash
# Local dev:
docker compose -f deploy/docker-compose.yaml \
               -f deploy/docker-compose.dev.yaml up

# Production (Hetzner):
docker compose -f deploy/docker-compose.yaml up -d --build

# CI/CD (future):
docker compose -f deploy/docker-compose.yaml \
               -f deploy/docker-compose.ci.yaml up --build --abort-on-container-exit
```

**Evidence:** `deploy/docker-compose.yaml`, `deploy/docker-compose.dev.yaml`, `deploy/DEPLOYMENT_GUIDE.md`.

---

## Technical Analysis
<!-- ID: technical_analysis -->

### Architecture Diagram
```
                 ┌─────────────────────────────────┐
                 │        Docker Host               │
                 │  (Hetzner CCX23 / WSL2)          │
                 └──────────────┬──────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            │                   │                   │
  ┌─────────▼────────┐ ┌───────▼───────┐ ┌────────▼────────┐
  │  council-web     │ │ council-daemon│ │   postgres      │
  │  :8015 (FastAPI) │ │ :8016 (WS)   │ │   :5432         │
  │  /health  OK     │ │ /health BROKE│ │   pg_isready OK  │
  │  -> daemon (WS)  │ │ Scribe child │ │   pgvector/pg16  │
  │  Named vol:      │ │ Named vol:   │ │   Named vol:     │
  │  (council_data)  │ │ (scribe_data)│ │   pg_data        │
  └──────────────────┘ └──────────────┘ └─────────────────┘
            │                   │                   │
            └───────────────────┼───────────────────┘
                        backend network
                    (bridge, localhost only)
```

### Code Patterns Identified

1. **Entrypoint bridge pattern** (`deploy/docker-entrypoint.sh`): Secret file -> env var bridge with `exec "$@"`. Clean, handles "env var already set" case. Well-established Docker pattern.

2. **Multi-stage target pattern** (`deploy/Dockerfile`): `--target daemon` / `--target web` from same Dockerfile. Correct and maintainable.

3. **Signal handling** (`src/council_mcp/server.py` line 1125-1126): Direct SIGTERM/SIGINT registration. Works for main process but does not propagate to subprocess tree. Needs tini.

4. **Health endpoint** (`src/council_mcp/web/routes/health.py`): Simple status check. Should split into liveness/readiness for proper orchestration support.

### Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Daemon health check never passes | HIGH | CERTAIN | Fix health endpoint or check method |
| Root container compromise | HIGH | LOW | Add non-root user |
| Zombie processes from Scribe | MEDIUM | MEDIUM | Add tini init process |
| Data loss on volume deletion | HIGH | LOW | Backup strategy + documentation |
| Web starts before daemon ready | MEDIUM | HIGH | Add service_healthy condition |
| Secret exposure via env vars | LOW | LOW | Already mitigated by file-based secrets |

---

## Recommendations
<!-- ID: recommendations -->

### P0: Before Next Deploy (CRITICAL)
- [ ] **Fix daemon health check** -- Add HTTP health endpoint on port 8017 or change to WebSocket/file-based check
- [ ] **Add `condition: service_healthy`** to web's depends_on for daemon
- [ ] **Add tini init process** -- Install tini in runtime stage, update ENTRYPOINT
- [ ] **Add non-root user** -- Create council user (UID 1001), chown /app, USER council
- [ ] **Move gcc to builder stage** -- Proper builder/runtime separation

### P1: Short-Term Improvements
- [ ] Split web health into `/health/live` and `/health/ready` endpoints
- [ ] Add `.env.example` template at repo root
- [ ] Add SCRIBE_DB_URL secret to production compose
- [ ] Add `stop_grace_period: 30s` for daemon container
- [ ] Add `shm_size: 256mb` to postgres service
- [ ] Add Docker Compose profiles for Ray head node

### P2: Long-Term / Future Phases
- [ ] Container registry (GHCR) for pre-built images and faster deploys
- [ ] Network segmentation if adding external-facing or untrusted services
- [ ] Log shipping via Docker logging driver (e.g., fluentd or loki)
- [ ] Automated backup: scheduled pg_dump + volume snapshots
- [ ] Secret rotation via SOPS or Vault

---

## Appendix A: Complete Recommended Dockerfile
<!-- ID: appendix -->

```dockerfile
# ===== BUILDER =====
FROM python:3.11-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY vendor/agentkit*.whl ./vendor/
RUN pip install --no-cache-dir ./vendor/agentkit*.whl
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# ===== RUNTIME =====
FROM python:3.11-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl tini && rm -rf /var/lib/apt/lists/*
RUN groupadd -r council --gid=1001 && \
    useradd -r -g council --uid=1001 --no-create-home --shell=/bin/false council
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY deploy/docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh
COPY . .
ENV PYTHONPATH="/app:${PYTHONPATH}"
RUN chown -R council:council /app

# ===== DAEMON =====
FROM runtime AS daemon
EXPOSE 8016 8017
USER council
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8017/health || exit 1
ENTRYPOINT ["tini", "--", "./docker-entrypoint.sh"]
CMD ["council", "start", "--foreground", "--no-web"]

# ===== WEB =====
FROM runtime AS web
EXPOSE 8015
USER council
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8015/health/ready || exit 1
ENTRYPOINT ["tini", "--", "./docker-entrypoint.sh"]
CMD ["python", "-m", "council_mcp.web.app"]
```

## Appendix B: Recommended docker-compose.yaml Additions

```yaml
services:
  postgres:
    shm_size: 256mb

  council-daemon:
    init: true  # Alternative to tini in Dockerfile
    stop_grace_period: 30s
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8017/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s

  council-web:
    init: true
    stop_grace_period: 10s
    depends_on:
      council-daemon:
        condition: service_healthy  # CRITICAL FIX
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8015/health/ready"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s

secrets:
  scribe_db_url:
    file: ../secrets/scribe_db_url.txt  # ADD THIS
```

---

## Sources
- [Docker Multi-Stage Builds for Python](https://collabnix.com/docker-multi-stage-builds-for-python-developers-a-complete-guide/)
- [FastAPI Docker Best Practices - Better Stack](https://betterstack.com/community/guides/scaling-python/fastapi-docker-best-practices/)
- [Docker Compose in Production - Docker Docs](https://docs.docker.com/compose/production/)
- [Docker Compose Override Files - Docker Recipes](https://docker.recipes/docs/compose-overrides)
- [Secrets in Compose - Docker Docs](https://docs.docker.com/compose/how-tos/use-secrets/)
- [PID 1 Signal Handling - Peter Malmgren](https://petermalmgren.com/signal-handling-docker/)
- [tini - GitHub](https://github.com/krallin/tini)
- [dumb-init - GitHub](https://github.com/Yelp/dumb-init)
- [Docker Volumes - Docker Docs](https://docs.docker.com/engine/storage/volumes/)
- [Docker Networking - Docker Docs](https://docs.docker.com/compose/how-tos/networking/)
- [FastAPI Health Checks for Docker](https://medium.com/write-a-catalyst/healthchecks-readiness-and-liveness-for-fastapi-on-docker-efea2db0fe92)
- [Docker Security for Python - Collabnix](https://collabnix.com/10-essential-docker-best-practices-for-python-developers-in-2025/)
- [Docker Best Practices for Python - TestDriven.io](https://testdriven.io/blog/docker-best-practices/)
- [Docker Security Best Practices 2025](https://oneuptime.com/blog/post/2026-02-02-docker-security-best-practices/view)
- [Production FastAPI Docker Deployment 2025](https://blog.greeden.me/en/2025/09/02/the-definitive-guide-to-fastapi-production-deployment-with-dockeryour-one-stop-reference-for-uvicorn-gunicorn-nginx-https-health-checks-and-observability-2025-edition/)
