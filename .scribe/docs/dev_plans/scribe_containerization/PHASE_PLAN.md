---
id: scribe_containerization-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_containerization"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-16 03:53:46 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — scribe_containerization
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-16 02:56:56 UTC

> Execution roadmap for scribe_containerization.

---
## Phase Overview
<!-- ID: phase_overview -->
### Scribe MCP Containerization -- 5-Phase Implementation Plan

| Phase | Name | Scope | Est. Effort | Dependencies |
|-------|------|-------|-------------|--------------|
| **1** | Transport Layer | SSE server, CLI flag, health endpoint | 1 day | None |
| **2** | Dockerfile & Build | Multi-stage Dockerfile, .dockerignore | 0.5 day | Phase 1 |
| **3** | Docker Compose & Secrets | Service definition, entrypoint script | 0.5 day | Phase 2 |
| **4** | Council Integration | Config change, connection test | 0.5 day | Phase 3 |
| **5** | Testing & Validation | Docker tests, E2E, documentation | 1 day | Phase 4 |

**Total Estimated Effort**: 3.5 days

**Execution Model**: Phases are sequential. Each phase builds on the previous. Phase 1 can be tested without Docker. Phase 5 validates the complete stack.
<!-- ID: phase_0 -->
**Objective**: Add SSE transport support to Scribe MCP using native MCP SDK, with health endpoint and CLI flag.

**Dependencies**: None (first phase)

### Task Package 1.1: Create SSE Server Module

**Scope**: Create new `server_sse.py` file that wraps the existing MCP Server instance with SSE transport.

**Files to Create**: `src/scribe_mcp/server_sse.py`

**Specifications**:

1. Import `app`, `_startup`, `_shutdown` from `scribe_mcp.server`
2. Import `SseServerTransport` from `mcp.server.sse`
3. Import `Starlette`, `Route`, `Mount` from `starlette`
4. Import `uvicorn` for HTTP serving
5. Create `health_check(request)` async function:
   - Returns `JSONResponse` with keys: `status`, `service`, `version`, `transport`, `uptime_seconds`
   - Status is always "healthy" (if the server can respond, it is healthy)
6. Create `run_sse(host: str = "0.0.0.0", port: int = 8200)` async function:
   - Call `await _startup()` first (same as stdio path in `server.py:954`)
   - Create `SseServerTransport("/messages/")`
   - Create `handle_sse(request)` that uses `sse_transport.connect_sse(request.scope, request.receive, request._send)` to get streams, then calls `app.run(streams[0], streams[1], app.create_initialization_options())`
   - Build `Starlette` app with routes: `/health` (GET), `/sse` (GET), `/messages/` (POST mount to `sse_transport.handle_post_message`)
   - Register `_shutdown` as on_shutdown handler for the Starlette app
   - Create `uvicorn.Config` with the Starlette app, host, port, log_level="info"
   - Create `uvicorn.Server(config)` and call `await server.serve()`
7. Create `main()` function that calls `asyncio.run(run_sse())` for use as a direct entry point

**Verification**:
- [ ] `python -c "from scribe_mcp.server_sse import run_sse"` imports without error
- [ ] `python -m scribe_mcp --transport sse --port 8200` starts and responds to `curl http://localhost:8200/health`
- [ ] Health endpoint returns JSON with all required fields

**Out of Scope**:
- Do NOT modify `server.py` -- only import from it
- Do NOT add authentication
- Do NOT implement Streamable HTTP

---

### Task Package 1.2: Update CLI Entry Point

**Scope**: Modify `__main__.py` to support `--transport`, `--port`, and `--host` arguments.

**Files to Modify**: `src/scribe_mcp/__main__.py`

**Specifications**:

1. Add `import os` to imports
2. Add `--transport` argument to `_parse_args()`:
   - `choices=["stdio", "sse"]`
   - `default=os.environ.get("SCRIBE_TRANSPORT", "stdio")`
   - `help="Transport mode (default: stdio, env: SCRIBE_TRANSPORT)"`
3. Add `--port` argument:
   - `type=int`
   - `default=int(os.environ.get("SCRIBE_TRANSPORT_PORT", "8200"))`
   - `help="Port for SSE transport (default: 8200, env: SCRIBE_TRANSPORT_PORT)"`
4. Add `--host` argument:
   - `default=os.environ.get("SCRIBE_TRANSPORT_HOST", "0.0.0.0")`
   - `help="Host for SSE transport (default: 0.0.0.0, env: SCRIBE_TRANSPORT_HOST)"`
5. Modify `main()` function:
   - If `args.transport == "sse"`: lazy-import `run_sse` from `server_sse` and call `asyncio.run(run_sse(host=args.host, port=args.port))`
   - Else: call `asyncio.run(server_main())` as before
6. Update parser description from "Run the Scribe MCP server over stdio." to "Run the Scribe MCP server."

**Verification**:
- [ ] `python -m scribe_mcp --help` shows `--transport`, `--port`, `--host` options
- [ ] `python -m scribe_mcp` (no args) still works in stdio mode (backward compatible)
- [ ] `SCRIBE_TRANSPORT=sse python -m scribe_mcp` starts SSE server
- [ ] `python -m scribe_mcp --transport sse --port 9999` starts on port 9999

**Out of Scope**:
- Do NOT add `--transport streamable_http` (future)
- Do NOT modify `server.py`

---

### Task Package 1.3: Update pyproject.toml Entry Points

**Scope**: Add `scribe-server-sse` script entry point.

**Files to Modify**: `pyproject.toml`

**Specifications**:

1. Add to `[project.scripts]` section:
   ```toml
   scribe-server-sse = "scribe_mcp.server_sse:main"
   ```

**Verification**:
- [ ] `pip install -e .` succeeds
- [ ] `scribe-server-sse` command is available and starts SSE server

**Out of Scope**:
- Do NOT modify dependencies (starlette/uvicorn already transitive deps of mcp)

---

### Phase 1 Success Criteria

1. SSE server starts and accepts connections on configurable port
2. Health endpoint returns 200 with JSON status
3. MCP tools are accessible over SSE transport
4. Stdio mode is completely unchanged (backward compatible)
5. All three new environment variables work (`SCRIBE_TRANSPORT`, `SCRIBE_TRANSPORT_PORT`, `SCRIBE_TRANSPORT_HOST`)
<!-- ID: phase_1 -->
**Objective**: Create production-ready Dockerfile and .dockerignore following verified Docker best practices.

**Dependencies**: Phase 1 (transport layer must exist for CMD)

### Task Package 2.1: Create Dockerfile

**Scope**: Multi-stage Dockerfile with builder and runtime stages.

**Files to Create**: `Dockerfile` (in scribe_mcp root)

**Specifications**:

1. **Stage 1 (builder)**:
   - Base: `python:3.11-slim`
   - Install build deps: `gcc`, `libpq-dev`, `python3-dev`
   - Copy `pyproject.toml` and `src/` directory
   - Install scribe-mcp with `pip install --no-cache-dir --no-deps .`
   - Install each dependency individually (EXCLUDING `sentence-transformers`):
     `asyncpg~=0.29`, `jinja2~=3.1`, `mcp==1.26.0`, `numpy~=1.20`, `portalocker~=2.0`, `psutil~=7.1`, `pyyaml~=6.0`, `rich~=13.7`, `tiktoken~=0.5`, `watchdog~=3.0`

2. **Stage 2 (runtime)**:
   - Base: `python:3.11-slim`
   - Install runtime deps: `libpq5`, `curl`, `tini`
   - Create `scribe` user/group (UID/GID 1001)
   - Copy site-packages and bin from builder
   - Copy `src/` and `pyproject.toml` to `/app`
   - Copy `deploy/docker-entrypoint.sh` to `/app`
   - Create `/app/.scribe` directory, chown to scribe user
   - Set environment: `PYTHONPATH=/app/src`, `SCRIBE_ROOT=/app`, `SCRIBE_TRANSPORT=sse`, `SCRIBE_TRANSPORT_PORT=8200`, `PYTHONUNBUFFERED=1`, `HF_HUB_DISABLE_PROGRESS_BARS=1`
   - `EXPOSE 8200`
   - `USER scribe`
   - HEALTHCHECK: `curl -f http://localhost:8200/health` (interval 30s, timeout 3s, start-period 10s, retries 3)
   - `ENTRYPOINT ["tini", "--", "./docker-entrypoint.sh"]`
   - `CMD ["python", "-m", "scribe_mcp", "--transport", "sse"]`

**Verification**:
- [ ] `docker build -t scribe-mcp:test .` succeeds
- [ ] Image size < 300MB (`docker images scribe-mcp:test --format "{.Size}"`)
- [ ] Container starts: `docker run --rm scribe-mcp:test python -c "import scribe_mcp; print('OK')"`
- [ ] Non-root: `docker run --rm scribe-mcp:test whoami` returns `scribe`
- [ ] tini is PID 1: `docker run --rm scribe-mcp:test ps aux` shows tini as PID 1

**Out of Scope**:
- Do NOT include sentence-transformers
- Do NOT create dev/web build targets (single target for now)

---

### Task Package 2.2: Create .dockerignore

**Scope**: Reduce Docker build context by excluding unnecessary files.

**Files to Create**: `.dockerignore` (in scribe_mcp root)

**Specifications**:

Exclude the following patterns:
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
```

**Verification**:
- [ ] Build context is significantly smaller (check `docker build` output for context size)
- [ ] Build still succeeds after adding .dockerignore

**Out of Scope**:
- Do NOT exclude `deploy/` (needed for entrypoint script)
- Do NOT exclude `src/` (needed for application code)

---

### Phase 2 Success Criteria

1. Docker image builds successfully
2. Image size < 300MB
3. Container runs as non-root user (scribe, UID 1001)
4. tini is PID 1
5. HEALTHCHECK passes within 15s of container start
6. sentence-transformers is NOT in the image
<!-- ID: milestone_tracking -->
**Objective**: Create Docker Compose service definition and entrypoint script for production deployment.

**Dependencies**: Phase 2 (Dockerfile must build successfully)

### Task Package 3.1: Create Docker Compose Service

**Scope**: Define Scribe as a composable Docker service.

**Files to Create**: `deploy/docker-compose.scribe.yaml`

**Specifications**:

1. Service name: `scribe`
2. Build context: `../` (scribe_mcp root), dockerfile: `Dockerfile`
3. Image: `scribe-mcp:latest`
4. Container name: `scribe-mcp`
5. Restart policy: `unless-stopped`
6. Network: `backend` (bridge, shared with Council)
7. NO ports exposed to host (internal Docker network only)
8. Volume: `scribe_data:/app/.scribe`
9. Environment variables:
   - `SCRIBE_ROOT: /app`
   - `SCRIBE_TRANSPORT: sse`
   - `SCRIBE_TRANSPORT_PORT: "8200"`
   - `SCRIBE_STORAGE_BACKEND: postgres`
   - `SCRIBE_POSTGRES_SCHEMA: scribe`
   - `SCRIBE_POSTGRES_POOL_MIN_SIZE: "2"`
   - `SCRIBE_POSTGRES_POOL_MAX_SIZE: "10"`
   - `SCRIBE_LOG_LEVEL: INFO`
   - `HF_HUB_DISABLE_PROGRESS_BARS: "1"`
10. Secret: `scribe_db_url` (file: `../../secrets/scribe_db_url.txt`)
11. depends_on: `postgres` with `condition: service_healthy`
12. Resource limits: 1G memory, 0.5 cpus; reservations: 256M memory, 0.1 cpus
13. `stop_grace_period: 30s`
14. Healthcheck: `curl -f http://localhost:8200/health` (interval 30s, timeout 3s, retries 3, start_period 10s)
15. Define `scribe_data` named volume
16. Define `scribe_db_url` secret

**Verification**:
- [ ] `docker compose -f deploy/docker-compose.scribe.yaml config` validates without error
- [ ] Service starts with `docker compose -f deploy/docker-compose.scribe.yaml up -d` (when Postgres available)
- [ ] `docker compose ps` shows scribe as healthy

**Out of Scope**:
- Do NOT modify Council's docker-compose.yaml
- Do NOT create dev override file (future)

---

### Task Package 3.2: Create Entrypoint Script

**Scope**: Shell script to bridge Docker secrets to environment variables.

**Files to Create**: `deploy/docker-entrypoint.sh`

**Specifications**:

1. Shebang: `#!/bin/bash`
2. `set -e` for fail-fast behavior
3. Bridge `SCRIBE_DB_URL`:
   - If `$SCRIBE_DB_URL` is empty AND `/run/secrets/scribe_db_url` exists, read it
4. Ensure `/app/.scribe` directory exists
5. `exec "$@"` to hand off to CMD

**Verification**:
- [ ] Script is executable (`chmod +x`)
- [ ] Secret bridging works: `echo "test_url" > /tmp/secret && docker run -v /tmp/secret:/run/secrets/scribe_db_url scribe-mcp:test env | grep SCRIBE_DB_URL`
- [ ] Falls through to CMD correctly

**Out of Scope**:
- Do NOT add volume ownership fixes (user already owns /app)

---

### Phase 3 Success Criteria

1. Docker Compose validates successfully
2. Service starts and connects to Postgres
3. Health check passes
4. Secrets are bridged to environment variables
5. Resource limits are enforced
<!-- ID: retro_notes -->
**Objective**: Configure Council MCP to connect to Scribe over SSE transport via Docker network.

**Dependencies**: Phase 3 (Scribe must be running in Docker with healthy status)

### Task Package 4.1: Council MCP Client Configuration

**Scope**: Update Council's Scribe connection from stdio subprocess to SSE network transport.

**Files to Modify**: Council MCP configuration (in `council_mcp` repository)

**Specifications**:

1. Locate Council's MCP server configuration (likely `council.yaml` or process_manager config)
2. Change Scribe transport from `stdio` (subprocess) to `sse` (network)
3. Set Scribe URL to `http://scribe:8200/sse` (Docker DNS resolution)
4. Verify Council's MCP client library supports SSE connections (`mcp.client.sse`)
5. Test connection: Council should be able to invoke Scribe tools (e.g., `set_project`, `append_entry`)

**Verification**:
- [ ] Council connects to Scribe container over Docker network
- [ ] Council can invoke at least one Scribe tool successfully
- [ ] Connection survives Scribe container restart (reconnection)
- [ ] No stdio subprocess remnants (clean process tree)

**Out of Scope**:
- Do NOT modify Scribe code (this is Council-side only)
- Do NOT implement authentication
- Do NOT modify MCP protocol behavior

**Note**: This task package spans TWO repositories (council_mcp and scribe_mcp). The Coder Agent will need access to both.

---

### Phase 4 Success Criteria

1. Council connects to Scribe via `http://scribe:8200/sse`
2. Tools work identically over SSE as over stdio
3. Connection is resilient (handles transient failures)

---

## Phase 5 -- Testing & Validation

**Objective**: Comprehensive testing of the complete containerized stack, documentation update.

**Dependencies**: Phase 4 (full stack must be operational)

### Task Package 5.1: Docker Integration Tests

**Scope**: Validate Docker container behavior.

**Files to Create**: `tests/test_docker_integration.py` (or shell script)

**Specifications**:

1. Test image builds successfully
2. Test image size < 300MB
3. Test container starts and becomes healthy within 15s
4. Test health endpoint returns correct JSON
5. Test graceful shutdown completes within 30s
6. Test volume persistence (write data, restart, verify data exists)
7. Test non-root user enforcement
8. Test Postgres connection from container

**Verification**:
- [ ] All Docker tests pass
- [ ] No data loss on container restart
- [ ] Resource usage within limits

---

### Task Package 5.2: E2E MCP Tool Tests

**Scope**: Verify MCP tools work correctly over SSE transport.

**Files to Create**: `tests/test_sse_transport.py`

**Specifications**:

1. Start SSE server programmatically
2. Connect MCP client using `mcp.client.sse`
3. Invoke `set_project` tool -- verify response
4. Invoke `append_entry` tool -- verify entry persisted
5. Invoke `read_recent` tool -- verify entries returned
6. Invoke `manage_docs` tool -- verify document created
7. Test concurrent connections (multiple clients)
8. Test connection recovery after server restart

**Verification**:
- [ ] All tool invocations return correct results over SSE
- [ ] Concurrent connections handled properly
- [ ] No regressions compared to stdio mode

---

### Task Package 5.3: Documentation

**Scope**: Update README and create deployment guide.

**Files to Modify/Create**:
- `README.md` -- add Docker deployment section
- `deploy/README.md` -- deployment guide (optional)

**Specifications**:

1. Add "Docker Deployment" section to README:
   - Prerequisites (Docker, Docker Compose)
   - Quick start command
   - Configuration reference
   - Troubleshooting
2. Document environment variables
3. Document volume requirements
4. Document secret setup

**Verification**:
- [ ] README has Docker section
- [ ] Commands in README actually work

---

### Phase 5 Success Criteria

1. All Docker tests pass
2. All E2E MCP tests pass over SSE
3. Documentation is complete and accurate
4. No regressions in stdio mode
5. Resource usage within defined limits

---

## Milestone Tracking

| Milestone | Target | Status | Evidence |
|-----------|--------|--------|----------|
| Phase 1: Transport Layer | Day 1 | Planned | |
| Phase 2: Dockerfile | Day 1.5 | Planned | |
| Phase 3: Docker Compose | Day 2 | Planned | |
| Phase 4: Council Integration | Day 2.5 | Planned | |
| Phase 5: Testing & Docs | Day 3.5 | Planned | |
| **Full Stack Operational** | **Day 3.5** | **Planned** | |
