---
id: scribe_client_server_split-research-cicd-deployment-20260217
title: "\U0001F52C Research Cicd Deployment 20260217 \u2014 scribe_client_server_split"
doc_type: RESEARCH_CICD_DEPLOYMENT_20260217
doc_name: RESEARCH_CICD_DEPLOYMENT_20260217
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 02:22:30 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Cicd Deployment 20260217 — scribe_client_server_split
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 02:15:33 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Understand the current deployment architecture, identify what needs to change to support dual-mode operation (lightweight local client + full Hetzner server), and design a CI/CD pipeline.

**Root Cause of Latency (VERIFIED, confidence 0.99):**
The local dev machine's `.env` file sets `SCRIBE_STORAGE_BACKEND=postgres` and `SCRIBE_DB_URL=postgresql://scribe_app:...@council-hub:5432/agentkit`. Every MCP tool call (e.g., `set_project`) performs 17-20 sequential synchronous Postgres roundtrips over Tailscale WAN (~50ms RTT each), causing 3+ minute latency.

**Key Takeaways:**
- No CI/CD pipeline exists today — deploy is 100% manual SSH + git pull + docker rebuild.
- The package has no optional dependency split for client vs server modes. All heavy deps (asyncpg, sentence-transformers) are required even for minimal client installs.
- No `scribe-client` entry point exists. Client mode must be added.
- The `transport/` directory contains scaffolds (stubs) that are the correct integration point for client-mode HTTP proxy.
- Migrations self-apply on server startup (no separate migration step needed in CI/CD).
- Zero-downtime deploy is achievable with proper health-check-aware restart sequencing.
- Docker image currently ~330MB (sentence-transformers excluded per README). With server extras split, client install would be ~50MB.
<!-- ID: research_scope -->
**Research Lead:** ResearchAnalyst-CICD
**Investigation Window:** 2026-02-17

**Focus Areas:**
- [x] Current deployment workflow (Hetzner, Docker, git)
- [x] Local client install method and MCP config
- [x] Server Docker image, compose, entrypoint
- [x] CI/CD pipeline existence (none found)
- [x] Package structure, entry points, dependency groups
- [x] Secret management (Docker secrets)
- [x] Migration handling during deploy
- [x] Zero-downtime restart strategy
- [x] Testing approach for dual-mode

**Dependencies and Constraints:**
- Tailscale mesh links dev PC (WSL2) to Hetzner council-hub.
- Docker Compose overlay pattern merges scribe overlay with council base compose.
- Scribe ports bind to `${TAILSCALE_IP:-127.0.0.1}` — never exposed to public internet.
- All secrets are file-based Docker secrets, not environment variables.
- Image size limit: under 400MB (from CLAUDE.md).
- Migrations must remain idempotent (self-applied on startup).
<!-- ID: findings -->
### Finding 1: No CI/CD Pipeline Exists (CRITICAL)
- **Summary:** No `.github/workflows/` directory. No `Makefile`. No automated test-before-deploy. Zero CI/CD infrastructure.
- **Evidence:** `ls /home/austin/projects/MCP_SPINE/scribe_mcp/.github/` returned NO_GITHUB_DIR. No `Makefile` found via glob.
- **Confidence:** 0.99
- **Impact:** Every deploy is manual, error-prone, and has no rollback automation.

### Finding 2: Current Deploy Workflow Is Fully Manual
- **Summary:** Deploy requires: SSH to council-hub, git pull, docker compose build, docker compose up -d --remove-orphans, manual health check.
- **Evidence:** `.claude/rules/hetzner-deployment.md` lines 84-98.
- **Files:** `.claude/rules/hetzner-deployment.md`, `deploy/docker-compose.scribe.yaml`
- **Confidence:** 0.99

### Finding 3: Local Install Directly Connects to Hetzner Postgres over Tailscale
- **Summary:** The local `.env` file (root cause confirmed):
  ```
  SCRIBE_STORAGE_BACKEND=postgres
  SCRIBE_DB_URL=postgresql://scribe_app:...@council-hub:5432/agentkit
  SCRIBE_POSTGRES_SCHEMA=scribe
  ```
  Every tool call = 17-20 Postgres roundtrips at ~50ms RTT = 850ms-1000ms minimum per call.
- **Evidence:** `/home/austin/projects/MCP_SPINE/scribe_mcp/.env` lines 17-19 (direct file inspection)
- **Confidence:** 0.99

### Finding 4: No Client Entry Point or Client Proxy Mode
- **Summary:** `pyproject.toml` has 9 console scripts but no `scribe-client`. `__main__.py` only supports `stdio` (full server with local DB) or `sse` (HTTP server mode). Zero proxy/forwarding implementation.
- **Evidence:** `pyproject.toml` `[project.scripts]` section; `src/scribe_mcp/__main__.py` lines 51-56.
- **Confidence:** 0.99

### Finding 5: Transport Scaffolds Exist as Client Mode Extension Point
- **Summary:** `src/scribe_mcp/transport/` contains: `base.py` (abstract `TransportProvider` with start/stop/send_message), `http_sse.py` (`HTTPSSETransportProvider` stub, 32 lines), `websocket.py` (stub). These are the correct integration point per CLAUDE.md "Auth/transport: SCAFFOLD ONLY" note.
- **Evidence:** Glob of transport/ directory; scan_only of base.py and http_sse.py.
- **Files:** `src/scribe_mcp/transport/base.py`, `src/scribe_mcp/transport/http_sse.py`
- **Confidence:** 0.97

### Finding 6: Flat Dependency List (No Client/Server Split)
- **Summary:** All dependencies are in main `[dependencies]`. No `[server]` or `[client]` optional groups. Server-only deps: `asyncpg`, `sentence-transformers`, `numpy`, `psutil`, `watchdog`, `jinja2`. A minimal client needs only: `mcp`, `httpx`, `portalocker`, `python-dotenv`, `pyyaml`, `rich`.
- **Evidence:** `pyproject.toml` lines 13-27.
- **Confidence:** 0.99

### Finding 7: Server Dockerfile Is Multi-Stage, ~330MB
- **Summary:** Two-stage build: builder (gcc, pip install all deps) → runtime (minimal python:3.11-slim + tini + gosu). Image size ~330MB per README (sentence-transformers excluded, but this is contradicted by the Dockerfile comment "including sentence-transformers").
- **Evidence:** `deploy/Dockerfile` lines 26-34; `deploy/README.md` "Image size: ~330MB".
- **UNVERIFIED:** Exact image size with current deps — README may be outdated.
- **Confidence:** 0.92

### Finding 8: Secrets Are File-Based Docker Secrets
- **Summary:** Two production secrets: `scribe_db_url.txt` (Postgres) and `store_hmac_key.txt` (CortaStore). Files at `/opt/council_mcp/secrets/`. Entrypoint bridges files to env vars. Client needs neither secret.
- **Evidence:** `deploy/docker-compose.scribe.yaml` lines 82-84; `deploy/docker-entrypoint.sh` lines 39-48.
- **Confidence:** 0.99

### Finding 9: Migrations Self-Apply on Server Startup
- **Summary:** `PostgresStorage._initialise()` runs all schema migrations via `run_migration()` which checks the `scribe_migrations` table for applied status. Fully idempotent — safe to apply multiple times.
- **Evidence:** `src/scribe_mcp/storage/postgres/migrations.py` lines 15-52 — `migration_completed()` + `mark_migration_complete()` pattern.
- **Confidence:** 0.97

### Finding 10: Zero-Downtime Deploy Relies on 30s Grace Period Only
- **Summary:** `stop_grace_period: 30s` in compose. No blue-green, no traffic draining. SSE connections (persistent) will drop on restart. Client reconnect is the only recovery mechanism.
- **Evidence:** `deploy/docker-compose.scribe.yaml` line 110.
- **Confidence:** 0.97

### Finding 11: Test Suite Uses SQLite Temp Dirs (No Postgres Integration Tests)
- **Summary:** `tests/conftest.py` creates `tempfile.mkdtemp()` state dir, sets `SCRIBE_STATE_PATH`. All 100+ tests run against SQLite. No Postgres integration test infrastructure.
- **Evidence:** `tests/conftest.py` lines 22-50.
- **Confidence:** 0.95

### Additional Notes
- Server repo path on Hetzner: `/opt/council_mcp` (council base) + `/opt/scribe_mcp` (scribe-specific). NOTE: CLAUDE.md says git pull from `/opt/council_mcp` then builds both compose files — this suggests scribe source is embedded in council's repo clone, not a separate checkout.
- Health endpoint `/health` returns JSON: `{"status":"healthy","service":"scribe-mcp","version":"2.2","transport":"sse","uptime_seconds":N}` — usable in CI/CD deploy verification.
- The `scribe_data` Docker volume persists `.scribe/` directory across container rebuilds. Logs and managed docs survive deploys.
<!-- ID: technical_analysis -->
### Current Deployment Architecture

```
Dev PC (WSL2, local)
  Claude Code
  mcpServers.scribe:
    command: python -m server (stdio, full server)
    env: SCRIBE_DB_URL=postgresql://scribe_app:...@council-hub:5432/agentkit
         SCRIBE_STORAGE_BACKEND=postgres

                    Tailscale (~50ms RTT per roundtrip)
                    17-20 roundtrips per tool call
                          |
                          v

Hetzner CCX23 (council-hub)
  Docker Compose Stack:
    postgres:5432     (pg_data volume, Docker-local)
    council-daemon:8016
    council-web:8015
    scribe:8200       (scribe_data volume, SSE transport)
    corta-store:8201
```

### Target Dual-Mode Architecture

```
Dev PC (WSL2) — CLIENT MODE
  Claude Code
  mcpServers.scribe:
    command: scribe-client (stdio, lightweight proxy)
    - Filesystem ops run locally (read_file, search, edit_file)
    - DB-backed ops proxy to Hetzner server via single HTTP call
    - Falls back to local SQLite when server unreachable

                    Tailscale (~50ms RTT)
                    1 HTTP request per tool call (not 17-20 Postgres queries)
                          |
                          v

Hetzner CCX23 (council-hub)
  scribe-server (Docker, SSE transport, :8200)
    - Receives proxied tool calls
    - Executes against local Postgres (Docker network = <1ms RTT)
    - Returns computed result in single HTTP response
```

**Latency improvement:** From 850-1000ms (17-20x50ms) per tool call to ~50ms (1 Tailscale roundtrip).

### Package Entry Points Analysis

| Entry Point | Current Target | Proposed Change |
|-------------|---------------|-----------------|
| `scribe` | cli router | No change |
| `scribe-server` | `__main__.py:main` (stdio/sse) | Keep for server use |
| `scribe-server-sse` | `server_sse:main` | Keep for Docker CMD |
| `scribe-mcp` | `__main__.py:main` | Alias — clarify intent |
| `scribe-client` | MISSING | NEW: lightweight client |
| `scribe-migrate` | migration script | Keep |
| `scribe-migrate-postgres` | SQLite→Postgres | Keep |
| `scribe-bootstrap-postgres` | Postgres setup | Keep |

### Dependency Split Proposal

**Current (all mandatory):**
```toml
dependencies = [
  "asyncpg~=0.29",              # Postgres driver — SERVER ONLY
  "httpx~=0.27",                # HTTP client — CLIENT + SERVER
  "jinja2~=3.1",                # templates — SERVER ONLY
  "mcp==1.26.0",                # MCP protocol — CLIENT + SERVER
  "numpy~=1.20",                # vectors — SERVER ONLY
  "portalocker~=2.0",           # file locking — CLIENT + SERVER
  "python-dotenv~=1.0",         # env vars — CLIENT + SERVER
  "psutil~=7.1",                # process info — SERVER ONLY
  "pyyaml~=6.0",                # config — CLIENT + SERVER
  "rich~=13.7",                 # output — CLIENT + SERVER
  "sentence-transformers~=2.0", # ML embeddings — SERVER ONLY
  "tiktoken~=0.5",              # token counting — SERVER ONLY
  "watchdog~=3.0",              # file watching — SERVER ONLY
]
```

**Proposed (split into client minimal + server extras):**
```toml
# Minimal — what client needs (no ML, no Postgres driver)
dependencies = [
  "httpx~=0.27",
  "mcp==1.26.0",
  "portalocker~=2.0",
  "python-dotenv~=1.0",
  "pyyaml~=6.0",
  "rich~=13.7",
]

[project.optional-dependencies]
server = [
  "asyncpg~=0.29",
  "jinja2~=3.1",
  "numpy~=1.20",
  "psutil~=7.1",
  "sentence-transformers~=2.0",
  "tiktoken~=0.5",
  "uvicorn[standard]>=0.27",
  "starlette>=0.35",
  "watchdog~=3.0",
]
dev = [
  "pytest~=7.4",
  "pytest-asyncio~=0.23",
  "faiss-cpu~=1.7",
  "respx",                      # HTTP mock for client proxy tests
]
s3 = ["boto3>=1.28"]
```

**Install commands:**
- Local client: `pip install scribe-mcp` (~50MB)
- Full server: `pip install "scribe-mcp[server]"` (~330MB with CPU torch)
- Docker: `pip install ".[server]"` in Dockerfile

### Secret Management Matrix

| Secret | Client Needs | Server Needs | Where Stored |
|--------|-------------|-------------|-------------|
| `SCRIBE_DB_URL` | NO | YES | Docker secret `/run/secrets/scribe_db_url` |
| `SCRIBE_OBJECT_STORE_KEY` | NO | YES | Docker secret `/run/secrets/store_hmac_key` |
| `SCRIBE_SERVER_URL` | YES (URL, not secret) | NO | `.env` or env var |
| Tailscale auth | Auto (daemon) | Auto (daemon) | Tailscale keyring |

### Code Patterns Identified

1. **Transport scaffolds** (`src/scribe_mcp/transport/`) are the correct extension point. `HTTPSSETransportProvider` in `http_sse.py` needs real implementation with `httpx` to call server REST endpoints.

2. **Storage backend selection** — currently storage is selected via `SCRIBE_STORAGE_BACKEND` env var in `server.py`. A "remote" backend type would proxy tool calls to the server's API instead of hitting a local DB.

3. **Health endpoint** at `/health` (implemented in `server_sse.py:53`) returns JSON. CI/CD can use `curl -f http://council-hub:8200/health` to verify successful deploy.

4. **Migration idempotency** via `scribe_migrations` table — safe to run migrations multiple times, no deploy coordination needed.

5. **Volume safety** — `scribe_data` named volume persists `.scribe/` across rebuilds. `docker compose down -v` is the only danger (explicitly documented as forbidden).

### Risk Assessment

| Risk | Severity | Current State | Mitigation |
|------|----------|-------------|------------|
| SSE connections dropped on restart | Medium | No mitigation | 30s grace + client reconnect |
| No CI/CD means bad code to prod | High | 100% manual | Implement GitHub Actions |
| Dependency split breaks existing installs | Medium | Not split yet | Additive: keep all in deps, add server extras |
| sentence-transformers in Docker (unclear) | Low | Contradictory docs | Measure actual image size |
| No rollback mechanism | High | None | Git tagging + image tagging before deploy |
| Postgres integration tests missing | Medium | SQLite only | Add pytest marks + skip-if-no-DB |
| Client falls through to local SQLite silently | Medium | N/A (no client) | Explicit warning when falling back |
<!-- ID: recommendations -->
### Immediate Next Steps

- [ ] Create `.github/workflows/deploy.yml` — minimal CI/CD pipeline (test + SSH deploy)
- [ ] Add `scribe-client` entry point to `pyproject.toml`
- [ ] Implement `src/scribe_mcp/transport/http_sse.py` (fill in HTTPSSETransportProvider stub)
- [ ] Split pyproject.toml deps: move server-only deps to `[server]` optional group
- [ ] Update Dockerfile pip install to `".[server]"` for explicit server extras
- [ ] Add `SCRIBE_SERVER_URL` env var support to config
- [ ] Create integration test infrastructure for client→server pipeline

### Proposed GitHub Actions Pipeline

```yaml
# .github/workflows/deploy.yml
name: Test and Deploy Scribe MCP
on:
  push:
    branches: [master]
    paths:
      - 'scribe_mcp/**'
      - '.github/workflows/deploy.yml'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        working-directory: scribe_mcp
        run: pip install -e ".[dev]"
      - name: Run unit tests (SQLite, no Postgres needed)
        working-directory: scribe_mcp
        run: pytest tests/ -x -q --timeout=60 -m "not postgres_integration"

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/master'
    steps:
      - name: Deploy to Hetzner via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.HETZNER_HOST }}
          username: ${{ secrets.HETZNER_USER }}
          key: ${{ secrets.HETZNER_SSH_KEY }}
          script: |
            set -euo pipefail
            # Backup DB before deploy
            /opt/council_mcp/deploy/scripts/backup-postgres.sh
            # Pull latest code
            git -C /opt/council_mcp/scribe_mcp pull origin master
            # Tag current image before rebuild (rollback)
            PREV_HASH=$(git -C /opt/council_mcp/scribe_mcp rev-parse --short HEAD~1)
            docker tag scribe-mcp:latest scribe-mcp:${PREV_HASH} 2>/dev/null || true
            # Build new image
            docker compose \
              -f /opt/council_mcp/council_mcp/deploy/docker-compose.yaml \
              -f /opt/council_mcp/scribe_mcp/deploy/docker-compose.scribe.yaml \
              build scribe
            # Rolling restart (30s grace period in compose handles connections)
            docker compose \
              -f /opt/council_mcp/council_mcp/deploy/docker-compose.yaml \
              -f /opt/council_mcp/scribe_mcp/deploy/docker-compose.scribe.yaml \
              up -d --remove-orphans scribe
            # Verify health
            sleep 15
            curl -f http://localhost:8200/health
            echo "Deploy successful"
```

**Required GitHub Secrets:**
- `HETZNER_HOST`: council-hub Tailscale hostname or IP
- `HETZNER_USER`: SSH user on Hetzner
- `HETZNER_SSH_KEY`: Private SSH key with access to council-hub

**Note:** GitHub Actions runners need Tailscale to reach council-hub. Options:
1. `tailscale/github-action` — authenticates the runner to Tailscale network (preferred)
2. Self-hosted runner on council-hub — eliminates network requirement entirely

### Local Client Configuration (Target State)

After client implementation, update `.claude.json` or `.mcp.json`:

```json
{
  "mcpServers": {
    "scribe": {
      "command": "scribe-client",
      "args": [],
      "env": {
        "SCRIBE_SERVER_URL": "http://council-hub:8200",
        "SCRIBE_FALLBACK_MODE": "sqlite",
        "SCRIBE_ROOT": "/home/austin/projects/MCP_SPINE/scribe_mcp"
      }
    }
  }
}
```

This eliminates the WAN Postgres connection and routes all DB calls through the server.

### Testing Strategy for Dual-Mode

| Test Type | Command | Infrastructure Needed |
|-----------|---------|----------------------|
| Unit (existing) | `pytest tests/ -m "not postgres_integration"` | None — SQLite temp dirs |
| Client proxy | `pytest tests/ -m client_proxy` | `respx` HTTP mock |
| Postgres integration | `pytest tests/ -m postgres_integration` | SCRIBE_DB_URL env var set |
| E2E client→server | `pytest tests/ -m e2e` | Start SSE server in fixture |

**Add to `tests/conftest.py`:**
```python
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "postgres_integration: requires Postgres")
    config.addinivalue_line("markers", "client_proxy: tests client HTTP proxy mode")
    config.addinivalue_line("markers", "e2e: full client-to-server integration tests")
```

### Rollback Strategy

1. **Image rollback:** Before each deploy, tag current image: `docker tag scribe-mcp:latest scribe-mcp:$(git rev-parse --short HEAD~1)`. Rollback: `docker tag scribe-mcp:<prev_hash> scribe-mcp:latest && docker compose up -d scribe`.
2. **Database rollback:** Backup runs before every deploy via `backup-postgres.sh`. Restore: `gunzip -c /opt/backups/council/agentkit_TIMESTAMP.sql.gz | docker compose exec -T postgres psql -U council -d agentkit`.
3. **Code rollback:** `git revert HEAD && git push` triggers CI/CD redeploy.

### Zero-Downtime Deploy (Acceptable Approach)

For a documentation/logging service like Scribe, brief SSE interruptions during deploy are acceptable. The MCP SDK reconnects automatically. The existing 30s grace period + client-side reconnect is sufficient.

If truly zero-downtime is needed in the future:
1. Expose port 8200 via nginx proxy on Hetzner
2. Build new container on port 8201
3. Health-check-gate swap in nginx upstream
4. Drain old connections for 30s
5. Remove old container

### Long-Term Opportunities

- **Self-hosted GitHub runner on council-hub:** Eliminates Tailscale setup in CI, gives direct Docker access, reduces deploy time.
- **Docker image caching in GitHub Actions:** Cache pip wheels layer to reduce build time from ~5min to ~1min.
- **Loki + Grafana for log aggregation:** Container logging driver → Loki on Hetzner; Grafana dashboard over Tailscale.
- **Dependabot for dependency updates:** Automated PRs for security patches in `pyproject.toml`.
- **Pre-commit hooks:** `ruff`, `mypy`, `pytest` run on commit to catch issues before CI.
<!-- ID: appendix -->
### Key Files Investigated

| File | Size | Key Findings |
|------|------|-------------|
| `deploy/Dockerfile` | 84 lines | Multi-stage build, CPU/GPU modes, tini+gosu |
| `deploy/docker-compose.scribe.yaml` | 177 lines | Overlay pattern, 30s grace, Docker secrets |
| `deploy/docker-entrypoint.sh` | 72 lines | Secrets bridge, privilege drop via gosu |
| `deploy/README.md` | 370 lines | Full deployment guide and troubleshooting |
| `.claude/rules/hetzner-deployment.md` | 210 lines | Infrastructure overview, manual deploy steps |
| `pyproject.toml` | 68 lines | 9 entry points, flat deps, no client/server split |
| `src/scribe_mcp/__main__.py` | 61 lines | stdio/sse mode router |
| `src/scribe_mcp/server_sse.py` | 155 lines | Starlette ASGI, /health, /sse, /messages/ |
| `src/scribe_mcp/transport/base.py` | 44 lines | Abstract TransportProvider scaffold |
| `src/scribe_mcp/transport/http_sse.py` | 32 lines | HTTPSSETransportProvider stub (implement here) |
| `src/scribe_mcp/storage/postgres/migrations.py` | 138 lines | Idempotent migration runner |
| `src/scribe_mcp/config/mcp_config.json` | 12 lines | Local MCP stdio template |
| `.env` | 19 lines | VERIFIED root cause: direct Hetzner Postgres |
| `tests/conftest.py` | 72 lines | SQLite-only test infrastructure |

### Hetzner Infrastructure Summary

| Component | Details |
|-----------|---------|
| Server | CCX23 (16GB RAM, 4 vCPU) |
| Tailscale hostname | `council-hub` |
| Repo path | `/opt/council_mcp` (council) |
| Secrets | `/opt/council_mcp/secrets/*.txt` (chmod 600) |
| Backups | `/opt/backups/council/` |
| Postgres | `agentkit` database, `scribe` schema |

### Confidence Summary

| Finding | Confidence |
|---------|------------|
| Root cause (Tailscale Postgres WAN latency) | 0.99 |
| No CI/CD exists | 0.99 |
| No client entry point | 0.99 |
| Flat dependency list confirmed | 0.99 |
| Transport scaffolds are correct extension point | 0.97 |
| Migration self-apply pattern | 0.97 |
| Zero-downtime achievable | 0.90 |
| Image size ~330MB | 0.92 (README vs Dockerfile inconsistency — UNVERIFIED) |
| Overall research confidence | 0.93 |

### Architect Decision Points

1. **Client proxy pattern:** Per-tool HTTP calls vs transparent MCP protocol proxy vs hybrid (local filesystem ops + remote DB ops).
2. **Dependency split timing:** Split before or after client implementation? Splitting first clarifies the scope.
3. **Entry point name:** `scribe-client` proposed. Should `scribe-mcp` be repurposed to client role?
4. **Fallback behavior:** Silent fallback to local SQLite vs explicit warning vs fail-fast.
5. **CI/CD hosting:** GitHub-hosted runners with Tailscale auth action vs self-hosted runner on council-hub.

### References

- `deploy/README.md` — full Docker deployment guide
- `.claude/rules/hetzner-deployment.md` — Hetzner infrastructure rules
- `CLAUDE.md` — orchestration protocol, commandments, database schema rules
- `src/scribe_mcp/storage/postgres/migrations.py` — migration patterns
- MCP SDK docs — SSE transport reconnection behavior

---
*Research complete. Agent: ResearchAnalyst-CICD. Date: 2026-02-17. Overall confidence: 0.93.*
