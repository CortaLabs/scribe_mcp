---
id: council_infra_pipeline-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 council_infra_pipeline"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 03:06:07 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — council_infra_pipeline
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 01:48:55 UTC

> Architecture guide for council_infra_pipeline.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## Problem Statement

Council MCP currently deploys to a Hetzner CCX23 VPS (16GB RAM, 4 vCPU) via manual SSH commands: `git pull`, `docker compose build`, `docker compose up -d`. There is no CI/CD pipeline, no automated testing before deploy, no rollback mechanism, and no audit trail. Additionally, 6 downstream council repos (voicelab, rom_lab, MyBB_Playground, osrs_hiscore_pull, knowledge_mcp, scribe_mcp) need their full repositories cloned to production to support custom routes, pages, and future Claude Code / Ray worker execution.

**What must change:**
1. Push-to-main must trigger automated build, test, and deploy
2. Docker images must build on GitHub (not the constrained VPS) and push to GHCR
3. Downstream repos must sync to production with full git clones
4. Secrets must flow from GitHub Secrets to Docker Secrets files on the VPS
5. Health checks must gate deployments with automatic rollback on failure
6. The architecture must support adding new servers without redesign
<!-- ID: requirements_constraints -->
## Requirements and Constraints

### Functional Requirements
1. **Platform CI/CD**: Push to `master` on MCP_SPINE triggers: lint/test -> build Docker images -> push to GHCR -> deploy to Hetzner -> verify health
2. **Downstream Sync**: Push to `main` on any downstream CortaLabs repo triggers: SSH git pull on Hetzner -> council registration check -> web restart if routes changed
3. **Secrets Management**: GitHub Secrets -> SSH -> `/opt/council_mcp/secrets/*.txt` files (existing Docker Secrets pattern preserved)
4. **Health-Gated Deploy**: All 5 services must pass health checks before deployment is considered successful; rollback to previous images on failure
5. **Multi-Council Bind Mount**: Full repo clones at `/opt/councils/<name>/` bind-mounted read-only into Docker containers at `/councils/<name>/`
6. **Auto-Registration**: New councils auto-register with the web UI on first sync via the existing `POST /api/councils/register` endpoint

### Non-Functional Requirements
1. **Build time**: Under 10 minutes for full platform build (GHCR caching)
2. **Deploy time**: Under 5 minutes for image pull + service restart
3. **Resource budget**: Build happens on GitHub runners, not the CCX23 (4 vCPU must run services, not builds)
4. **Zero public ports**: All connectivity via Tailscale mesh (GitHub Actions uses ephemeral Tailscale node)
5. **Rollback speed**: Under 2 minutes (pull previous tagged image + restart)

### Constraints
- **Hardware**: Hetzner CCX23 -- 16GB RAM, 4 vCPU, 240GB SSD. Already allocating ~10GB to Docker services. ~6GB headroom.
- **Network**: Tailscale mesh only. No public internet exposure. Docker ports bind to `${TAILSCALE_IP:-127.0.0.1}`.
- **Bandwidth**: Hetzner 2TB/month outbound. GHCR image pulls + git operations must stay well under.
- **GitHub Actions**: CortaLabs org. Budget-conscious -- cache aggressively, minimize minutes.
- **Monorepo**: MCP_SPINE contains 5 projects (agentkit, council_mcp, scribe_mcp, corta_store, knowledge_mcp) in one git repo with separate `.git` dirs per project.
- **Existing infrastructure**: Docker Compose stack with 5 services (postgres, daemon, web, scribe, corta-store). Multi-stage Dockerfile with layer caching. Docker Secrets for credentials. External volumes for data persistence.
- **Agentkit vendoring**: Agentkit ships as a pre-built `.whl` in `vendor/`. CI must rebuild this wheel when agentkit changes and place it in `vendor/` before building council_mcp images.
<!-- ID: architecture_overview -->
## Architecture Overview

### System Architecture Diagram

```
                          GITHUB (CortaLabs org)
    ┌─────────────────────────────────────────────────────────┐
    │                                                         │
    │  MCP_SPINE repo          Downstream repos (6)           │
    │  ┌──────────────┐       ┌───────────────────────┐       │
    │  │ push master   │       │ push main              │       │
    │  └──────┬───────┘       └──────────┬────────────┘       │
    │         │                          │                     │
    │         v                          v                     │
    │  ┌──────────────┐       ┌───────────────────────┐       │
    │  │ platform.yml │       │ sync-council.yml       │       │
    │  │              │       │                         │       │
    │  │ 1. Test      │       │ 1. Tailscale connect   │       │
    │  │ 2. Build     │       │ 2. SSH git pull        │       │
    │  │    images    │       │ 3. Register council    │       │
    │  │ 3. Push GHCR │       │ 4. Restart web         │       │
    │  │ 4. Deploy    │       │    (if routes changed) │       │
    │  └──────┬───────┘       └──────────┬────────────┘       │
    │         │                          │                     │
    │         │    GitHub Secrets         │                     │
    │         │    ┌─────────────┐       │                     │
    │         │    │ SSH key      │       │                     │
    │         │    │ TS OAuth     │       │                     │
    │         │    │ Prod secrets │       │                     │
    │         │    └─────────────┘       │                     │
    └─────────┼──────────────────────────┼─────────────────────┘
              │                          │
              │    Tailscale Mesh         │
              │    (ephemeral nodes)      │
              v                          v
    ┌─────────────────────────────────────────────────────────┐
    │              HETZNER CCX23 (council-hub)                 │
    │                                                         │
    │  /opt/council_mcp/          /opt/councils/               │
    │  ├── deploy/                ├── voicelab/      (full)   │
    │  │   ├── docker-compose.yaml│   ├── .council/            │
    │  │   ├── Dockerfile         │   ├── src/                 │
    │  │   └── scripts/           │   └── ...                  │
    │  ├── secrets/*.txt          ├── rom_lab/       (full)   │
    │  └── .env                   ├── MyBB_Playground/(full)  │
    │                             ├── osrs_hiscore_pull/(full)│
    │                             ├── scribe_mcp/    (full)   │
    │                             └── knowledge_mcp/ (full)   │
    │                                                         │
    │  Docker Compose Stack                                    │
    │  ┌────────────────────────────────────────────────────┐ │
    │  │ postgres  │ daemon │ web   │ scribe │ corta-store  │ │
    │  │ :5432     │ :8016  │ :8015 │ :8200  │ :8201        │ │
    │  │ 4GB/1CPU  │ 2GB    │ 1.5GB │ 2GB    │ 512MB        │ │
    │  └────────────────────────────────────────────────────┘ │
    │                  │                                       │
    │                  │ Bind mount: /opt/councils:/councils:ro│
    │                  │                                       │
    │  Named Volumes: pg_data, scribe_data, corta_store_data  │
    └─────────────────────────────────────────────────────────┘
```

### Component Inventory

| Component | Location | Purpose | Owner |
|-----------|----------|---------|-------|
| `platform.yml` | `.github/workflows/platform.yml` | Build + deploy platform on push to master | GitHub Actions |
| `sync-council.yml` | `.github/workflows/sync-council.yml` | Sync downstream councils on push to main | GitHub Actions (reusable) |
| `deploy.sh` | `deploy/scripts/deploy.sh` | SSH-based deployment script (pull images, write secrets, restart) | Called by platform.yml |
| `sync-councils.sh` | `deploy/scripts/sync-councils.sh` | Git pull all downstream repos, register councils | Called by sync-council.yml |
| `rollback.sh` | `deploy/scripts/rollback.sh` | Revert to previous Docker image tags | Manual or auto on health failure |
| `health-check.sh` | `deploy/scripts/health-check.sh` | Verify all services healthy post-deploy | Called by deploy.sh |
| `council-manifest.yaml` | `/opt/councils/manifest.yaml` (on Hetzner) | Lists all downstream repos to sync | sync-councils.sh reads this |

### Data Flow: Platform Deploy

```
1. Developer pushes to master (MCP_SPINE)
2. GitHub Actions: platform.yml triggers
3. Job: test
   a. Checkout code
   b. Set up Python 3.12
   c. Install deps (cached pip)
   d. Run pytest for council_mcp (fast subset)
4. Job: build (needs: test)
   a. Set up Docker Buildx
   b. Login to GHCR (github.actor + GITHUB_TOKEN)
   c. Build daemon image (target: daemon) with registry cache
   d. Build web image (target: web) with registry cache
   e. Push both to ghcr.io/cortalabs/mcp_spine/daemon:sha,latest
   f. Push both to ghcr.io/cortalabs/mcp_spine/web:sha,latest
5. Job: deploy (needs: build, environment: production)
   a. Connect to Tailscale (ephemeral node via OAuth)
   b. SSH to council-hub
   c. Write secrets to /opt/council_mcp/secrets/*.txt
   d. docker login ghcr.io
   e. cd /opt/council_mcp && git pull
   f. docker compose pull (daemon + web images from GHCR)
   g. docker compose up -d --remove-orphans
   h. Wait for health checks (postgres -> daemon -> web -> scribe -> corta-store)
   i. On failure: rollback to previous SHA tag
   j. Disconnect Tailscale (automatic, ephemeral node removed)
```

### Data Flow: Downstream Council Sync

```
1. Developer pushes to main (e.g., voicelab)
2. GitHub Actions: sync-council.yml triggers (in that repo, calls reusable workflow)
3. Connect to Tailscale (ephemeral node)
4. SSH to council-hub
   a. cd /opt/councils/voicelab && git pull
   b. Check if .council/web/routes/ changed (git diff HEAD~1 -- .council/web/routes/)
   c. Register council: curl POST /api/councils/register (idempotent via ON CONFLICT)
   d. If routes changed: docker compose -f /opt/council_mcp/deploy/docker-compose.yaml restart council-web
5. Disconnect Tailscale
```

### Path Mapping Strategy

| Context | Platform Path | Downstream Council Path |
|---------|--------------|------------------------|
| Dev (WSL2) | /home/austin/projects/MCP_SPINE/council_mcp | /home/austin/projects/voicelab |
| Prod (Hetzner host) | /opt/council_mcp | /opt/councils/voicelab |
| Prod (Docker container) | /app | /councils/voicelab |
| DB (council.councils.repo_path) | N/A | /councils/voicelab (container path) |

**Critical**: Council `repo_path` in the database stores the **container-relative path** (`/councils/<name>`), NOT the host path. The bind mount `/opt/councils:/councils:ro` makes host paths transparent to the application.

### Secrets Management Flow

```
GitHub Secrets (encrypted at rest)
        │
        v
GitHub Actions runner (ephemeral)
        │
        │ SSH to council-hub
        v
/opt/council_mcp/secrets/
    pg_password.txt         ← PROD_PG_PASSWORD
    database_url.txt        ← PROD_DATABASE_URL
    api_key.txt             ← PROD_COUNCIL_API_KEY
    openai_api_key.txt      ← PROD_OPENAI_API_KEY
    scribe_db_url.txt       ← PROD_SCRIBE_DB_URL
    store_hmac_key.txt      ← PROD_STORE_HMAC_KEY
        │
        v
docker-compose.yaml secrets: section
        │
        v
/run/secrets/<name> inside containers
        │
        v
docker-entrypoint.sh reads files → exports as env vars
```

**Secrets never appear in**: git history, Docker image layers, GitHub Actions logs, `docker inspect` output.
<!-- ID: detailed_design -->
## Detailed Design

### 1. GitHub Actions Workflow: platform.yml

**Trigger**: Push to `master` branch of MCP_SPINE repo, or `workflow_dispatch` for manual trigger.

**Jobs**:

```yaml
# Job 1: test (runs pytest, fast subset)
test:
  runs-on: ubuntu-latest
  steps:
    - checkout
    - setup-python 3.12
    - pip install (cached) council_mcp dev deps
    - pytest tests/ -x --timeout=60 -q (smoke tests only, not full 2000+ suite)

# Job 2: build (needs: test)
build:
  runs-on: ubuntu-latest
  steps:
    - checkout
    - docker/setup-buildx-action
    - docker/login-action (ghcr.io, GITHUB_TOKEN)
    - docker/build-push-action: daemon target
        tags: ghcr.io/cortalabs/mcp_spine/daemon:$SHA, :latest
        cache-from: type=registry,ref=ghcr.io/cortalabs/mcp_spine/daemon:buildcache
        cache-to: type=registry,mode=max
    - docker/build-push-action: web target (same pattern)

# Job 3: deploy (needs: build, environment: production)
deploy:
  runs-on: ubuntu-latest
  environment: production
  steps:
    - tailscale/github-action@v4 (ephemeral, OAuth)
    - SSH: write secrets files
    - SSH: git pull on /opt/council_mcp
    - SSH: docker login ghcr.io
    - SSH: docker compose pull
    - SSH: deploy/scripts/backup-postgres.sh (pre-deploy backup)
    - SSH: docker compose up -d --remove-orphans
    - SSH: deploy/scripts/health-check.sh
    - On failure: SSH: deploy/scripts/rollback.sh $PREVIOUS_SHA
```

### 2. GitHub Actions Workflow: sync-council.yml (Reusable)

**Trigger**: Called from downstream repos via `workflow_call`, or manually via `workflow_dispatch`.

**Inputs**: `council_name` (string), `repo_name` (string)

```yaml
# Reusable workflow in MCP_SPINE repo
sync-council:
  runs-on: ubuntu-latest
  steps:
    - tailscale/github-action@v4
    - SSH to council-hub:
        cd /opt/councils/$COUNCIL_NAME
        git pull origin main
        # Check for route changes
        ROUTES_CHANGED=$(git diff HEAD~1 --name-only -- .council/web/routes/ | wc -l)
        # Register council (idempotent)
        curl -s -X POST http://localhost:8015/api/councils/register \
          -H "X-API-Key: $(cat /opt/council_mcp/secrets/api_key.txt)" \
          -H "Content-Type: application/json" \
          -d '{"path": "/councils/$COUNCIL_NAME", "name": "$COUNCIL_NAME"}'
        # Restart web only if routes changed
        if [ "$ROUTES_CHANGED" -gt 0 ]; then
          docker compose -f /opt/council_mcp/deploy/docker-compose.yaml restart council-web
        fi
```

**Downstream repo caller workflow** (placed in each downstream repo):
```yaml
# .github/workflows/deploy.yml in voicelab repo
on:
  push:
    branches: [main]
jobs:
  sync:
    uses: CortaLabs/MCP_SPINE/.github/workflows/sync-council.yml@master
    with:
      council_name: voicelab
      repo_name: voicelab
    secrets: inherit
```

### 3. Deploy Scripts

**deploy/scripts/deploy.sh**: Main deployment orchestrator called by platform.yml.
- Receives secrets as environment variables from GitHub Actions
- Writes each secret to `/opt/council_mcp/secrets/<name>.txt` with `chmod 600`
- Runs `docker compose pull` then `docker compose up -d`
- Calls `health-check.sh` and returns exit code

**deploy/scripts/health-check.sh**: Post-deploy verification.
- Waits up to 120s for all services
- Checks: `pg_isready`, daemon TCP:8016, web HTTP:8015/login, scribe TCP:8200, corta-store HTTP:8201/health
- Returns 0 on success, 1 on timeout/failure

**deploy/scripts/rollback.sh**: Reverts to previous deployment.
- Takes `$PREVIOUS_SHA` as argument
- Runs `docker compose pull` with previous SHA tags
- Restarts services
- Re-runs health-check.sh

**deploy/scripts/sync-councils.sh**: Council sync orchestrator.
- Reads `/opt/councils/manifest.yaml` for list of repos
- For each: `cd /opt/councils/<name> && git pull`
- Registers each council via API
- Returns list of councils that had route changes (for selective restart)

### 4. Docker Compose Changes

**New bind mount** for council-web service:
```yaml
council-web:
  volumes:
    - scribe_data:/app/.scribe
    - /opt/councils:/councils:ro    # NEW: downstream council content
```

**No changes to**: daemon, postgres, scribe, corta-store (they do not need downstream content).

### 5. Council Manifest (Hetzner-side)

**File**: `/opt/councils/manifest.yaml`

```yaml
# Council deployment manifest
# Each entry maps a council name to its git repo
councils:
  voicelab:
    repo: git@github.com:CortaLabs/voicelab.git
    branch: main
  rom_lab:
    repo: git@github.com:CortaLabs/rom_lab.git
    branch: main
  MyBB_Playground:
    repo: git@github.com:CortaLabs/MyBB_Playground.git
    branch: main
  osrs_hiscore_pull:
    repo: git@github.com:CortaLabs/osrs_hiscore_pull.git
    branch: main
  scribe_mcp:
    repo: git@github.com:CortaLabs/MCP_SPINE.git
    branch: master
    sparse_path: scribe_mcp  # Sub-directory of monorepo
  knowledge_mcp:
    repo: git@github.com:CortaLabs/MCP_SPINE.git
    branch: master
    sparse_path: knowledge_mcp
```

**Note on monorepo sub-councils**: scribe_mcp and knowledge_mcp are inside MCP_SPINE. On Hetzner, `/opt/council_mcp` already has the full monorepo. We symlink:
```bash
ln -s /opt/council_mcp/../scribe_mcp /opt/councils/scribe_mcp
ln -s /opt/council_mcp/../knowledge_mcp /opt/councils/knowledge_mcp
```
Or better: since MCP_SPINE is already cloned to `/opt/council_mcp`, and scribe_mcp/knowledge_mcp are siblings, just clone MCP_SPINE once and reference the subdirectories. The manifest handles this.

### Architecture Decision Records

**ADR-1: Build on GitHub + GHCR over Build on Server**
- **Decision**: Build Docker images on GitHub Actions runners, push to GHCR, pull on Hetzner
- **Rationale**: CCX23 has only 4 vCPU -- building 5 services would consume all resources for 20-30 minutes, degrading running services. GitHub Actions builds in ~5 min with better caching.
- **Trade-off**: Requires GHCR auth on VPS, slightly more complex workflow. Acceptable.

**ADR-2: Tailscale Ephemeral Nodes for CI/CD**
- **Decision**: Use `tailscale/github-action@v4` with OAuth credentials to join Tailscale mesh during CI
- **Rationale**: Zero public ports. Runner gets ephemeral node, auto-removed after workflow. Matches existing Tailscale-only architecture.
- **Trade-off**: Requires Tailscale OAuth app setup (one-time). No alternative is as secure without public ports.

**ADR-3: Full Git Clone over Sparse Checkout for Downstream Repos**
- **Decision**: Clone full repositories to `/opt/councils/<name>/`, not just `.council/` directories
- **Rationale**: Operator override. Custom route modules may import from parent projects (e.g., MyBB imports mybb_mcp). Claude Code / Codex CLI will be installed on server for remote agent work. Ray workers need full repos. Future route modules need project code access.
- **Trade-off**: More disk space (~500MB-2GB per repo vs ~5MB for .council/ only). Acceptable given 240GB SSD.

**ADR-4: Reusable Workflow for Downstream Sync**
- **Decision**: Create a reusable workflow in MCP_SPINE that downstream repos call, rather than duplicating workflows
- **Rationale**: Single source of truth for sync logic. Downstream repos only need a 10-line caller workflow. Changes to sync logic propagate automatically.
- **Trade-off**: Cross-repo workflow dependency. If MCP_SPINE workflow breaks, all downstream deploys fail. Acceptable risk.

**ADR-5: Health-Check Gated Deploy with Automatic Rollback**
- **Decision**: Deploy script waits for health checks on all 5 services. On failure, automatically rolls back to previous image SHA.
- **Rationale**: Manual deploy has no rollback mechanism. Automated deploy without health gates is worse than manual. Rolling back to known-good SHA is fast and deterministic.
- **Trade-off**: Slightly longer deploy time (health check wait). Cold-start timeout must be generous (120s) to avoid false failures.

**ADR-6: Secrets as Files, Not Environment Variables**
- **Decision**: Keep the existing pattern of Docker Secrets mounted as files at `/run/secrets/<name>`, with `docker-entrypoint.sh` bridging to env vars
- **Rationale**: File-based secrets never appear in `docker inspect` or process listings. Already implemented and working. GitHub Actions writes secret files via SSH just-in-time.
- **Trade-off**: Extra indirection (file -> env var). But this is a well-known Docker pattern.

**ADR-7: Server Node Registry Deferred to Future Phase**
- **Decision**: Include `server_nodes` and `server_health_checks` tables in the architecture but defer implementation to Phase 4 (future-proofing)
- **Rationale**: No immediate need -- single Hetzner server. But when a second server or GPU rental is added, the registry must already exist. Schema is 2 tables, trivial to add.
- **Trade-off**: Tables exist but are unused initially. Minimal overhead.
<!-- ID: directory_structure -->
## Directory Structure

### New Files to Create

```
/home/austin/projects/MCP_SPINE/council_mcp/
├── .github/
│   └── workflows/
│       ├── platform.yml              # Platform CI/CD (build + deploy)
│       └── sync-council.yml          # Reusable downstream sync workflow
├── deploy/
│   ├── docker-compose.yaml           # MODIFIED: add bind mount for councils
│   ├── scripts/
│   │   ├── deploy.sh                 # NEW: deployment orchestrator
│   │   ├── health-check.sh           # NEW: post-deploy health verification
│   │   ├── rollback.sh               # NEW: rollback to previous image
│   │   ├── sync-councils.sh          # NEW: pull all downstream repos
│   │   ├── setup-councils.sh         # NEW: initial clone of downstream repos
│   │   ├── backup-postgres.sh        # EXISTING: pre-deploy DB backup
│   │   ├── setup-hetzner.sh          # EXISTING: initial server setup
│   │   └── safe-down.sh              # EXISTING: volume-safe compose down
│   └── Dockerfile                    # EXISTING: no changes needed
└── .env.example                      # MODIFIED: add ENVIRONMENT key

/opt/councils/ (on Hetzner only)
├── manifest.yaml                     # Council deployment manifest
├── voicelab/                         # Full git clone
├── rom_lab/                          # Full git clone
├── MyBB_Playground/                  # Full git clone
├── osrs_hiscore_pull/                # Full git clone
├── scribe_mcp -> ../council_mcp/../scribe_mcp  # Symlink
└── knowledge_mcp -> ../council_mcp/../knowledge_mcp  # Symlink
```

### Files Modified (Existing)

| File | Change | Reason |
|------|--------|--------|
| `deploy/docker-compose.yaml` | Add `/opt/councils:/councils:ro` volume to council-web | Downstream content access |
| `.env.example` | Add `ENVIRONMENT=dev` key | Dev/prod differentiation |
| `.gitignore` | Add `.github/workflows/*.yml` exceptions (ensure tracked) | CI/CD workflows must be in git |
<!-- ID: data_storage -->
## Data and Storage

### Docker Volumes (Unchanged)

| Volume | Mount Point | Purpose | Survives Rebuild |
|--------|------------|---------|-----------------|
| `deploy_pg_data` | `/var/lib/postgresql/data` | PostgreSQL database | Yes (external) |
| `deploy_scribe_data` | `/app/.scribe` | Scribe logs, projects, docs | Yes (external) |
| `deploy_corta_store_data` | `/data` | CortaStore objects | Yes (external) |

### New Bind Mount

| Mount | Host Path | Container Path | Mode | Service |
|-------|-----------|---------------|------|---------|
| Councils | `/opt/councils` | `/councils` | Read-only | council-web only |

### GitHub Container Registry (GHCR)

| Image | Tag Pattern | Retention |
|-------|------------|-----------|
| `ghcr.io/cortalabs/mcp_spine/daemon` | `latest`, `$SHA` | Last 10 tagged images |
| `ghcr.io/cortalabs/mcp_spine/web` | `latest`, `$SHA` | Last 10 tagged images |

### Secrets Storage

| Location | What | Access |
|----------|------|--------|
| GitHub Secrets (encrypted) | All prod credentials | GitHub Actions only |
| `/opt/council_mcp/secrets/*.txt` | Docker Secrets source files | `chmod 600`, root only |
| `/run/secrets/<name>` (in container) | Docker-mounted secrets | Container processes only |

### Database Migrations

Database migrations run via `agentkit-schema` as part of the auto-bootstrap flow in `docker-entrypoint.sh`. No changes needed for CI/CD -- the existing flow handles migrations on container start. Pre-deploy backup ensures rollback capability.
<!-- ID: testing_strategy -->
## Testing and Validation Strategy

### CI Tests (run in GitHub Actions, Job 1)

- **Scope**: Fast smoke tests only. NOT the full 2000+ test suite.
- **Command**: `pytest tests/test_config.py tests/test_session*.py -x --timeout=60 -q`
- **Purpose**: Catch obvious breakage before building images. Full regression is operator-gated.

### Deploy Validation (run on Hetzner, post-deploy)

| Check | Command | Timeout | Success Criteria |
|-------|---------|---------|-----------------|
| Postgres ready | `pg_isready -U council` | 60s | Exit 0 |
| Daemon healthy | `curl -sf http://localhost:8016/health` | 30s | HTTP 200 |
| Web healthy | `curl -sf http://localhost:8015/login` | 30s | HTTP 200 |
| Scribe running | `nc -z localhost 8200` | 15s | TCP open |
| CortaStore running | `curl -sf http://localhost:8201/health` | 15s | HTTP 200 |

### Rollback Criteria

If ANY health check fails after deploy, the `rollback.sh` script:
1. Pulls the previous SHA-tagged images from GHCR
2. Restarts services with `docker compose up -d`
3. Re-runs health checks
4. If rollback also fails: alert operator (GitHub Actions failure notification)

### Manual Verification (Post-Phase)

After each phase is complete, operator should manually verify:
- Web UI loads and shows all registered councils
- Custom pages render for downstream councils
- MCP tools respond (daemon WebSocket connection)
- Scribe logging works (append_entry succeeds)
<!-- ID: deployment_operations -->
## Deployment and Operations

### Environments

| Environment | Purpose | Config Source | Deploy Trigger |
|-------------|---------|--------------|---------------|
| Local (WSL2) | Development | `.env` + `council.yaml` | Manual |
| Production (Hetzner) | Live services | GitHub Secrets -> `secrets/*.txt` + `.env.prod` | Push to master |

### Operational Runbook

**Normal Deploy** (automated):
1. Push to master
2. GitHub Actions runs platform.yml
3. Images built, pushed, deployed
4. Health checks pass -> done

**Emergency Rollback** (manual):
```bash
ssh deploy@council-hub
cd /opt/council_mcp
# Find previous working SHA from docker images
docker images ghcr.io/cortalabs/mcp_spine/daemon --format "{.Tag}" | head -5
# Rollback
./deploy/scripts/rollback.sh <previous-sha>
```

**Add New Downstream Council**:
1. Clone repo on Hetzner: `cd /opt/councils && git clone git@github.com:CortaLabs/<repo>.git`
2. Add entry to `/opt/councils/manifest.yaml`
3. Register: `curl -X POST http://localhost:8015/api/councils/register ...`
4. Add caller workflow to downstream repo (`.github/workflows/deploy.yml`)
5. Restart web: `docker compose restart council-web`

**Secrets Rotation**:
1. Update secret value in GitHub Secrets (repo Settings -> Secrets)
2. Trigger manual deploy: `gh workflow run platform.yml`
3. Deploy writes new secret files, restarts services

### Monitoring (Existing)

- `council logs -f` -- live tail all services
- `council logs --level error --since 5m` -- recent errors
- `council status` -- process health
- Docker Compose logs: `docker compose logs -f council-web`

### Future: Multi-Server Operations

When a second server is added:
1. Register it in `server_nodes` table (Phase 4)
2. Add its Tailscale IP to the manifest
3. Health check loop monitors it automatically
4. Ray workers can discover it via `/api/server/nodes`

No architectural changes needed -- the node registry and Tailscale mesh handle it.
<!-- ID: open_questions -->
## Security Hardening

**Source**: REVIEW_DOCKER_SECURITY.md (2026-02-17). Sentinel security review of production Docker deployment.

### Threat Model

The Docker stack runs on a Hetzner CCX23 behind Tailscale mesh (no public ports). The primary threat is lateral movement after application-level compromise -- if an attacker gains code execution inside a container, root-level privileges and writable filesystems amplify the blast radius. Hardening reduces the impact of container escapes and limits privilege escalation.

### 1. Non-Root User Strategy

All Council application containers (council-daemon, council-web) must run as a non-root user after reading secrets.

**Pattern**: Two-phase entrypoint using `gosu`:
1. Container starts as root (required to read Docker Secrets at `/run/secrets/`)
2. `docker-entrypoint.sh` reads secrets, exports env vars
3. Entrypoint calls `exec gosu council "$@"` to drop privileges
4. Application process runs as `council` (UID 1000, GID 1000)

**Dockerfile additions**:
```dockerfile
# In base stage (after apt-get install)
RUN groupadd -g 1000 council && useradd -u 1000 -g council -m council
RUN apt-get install -y gosu && rm -rf /var/lib/apt/lists/*

# Ensure app directory owned by council
RUN chown -R council:council /app
```

**Entrypoint modification** (`docker-entrypoint.sh`):
```bash
#!/usr/bin/env bash
set -e

# Read secrets (requires root for /run/secrets/)
for f in /run/secrets/*; do
    [ -f "$f" ] || continue
    var=$(basename "$f" .txt | tr '[:lower:]' '[:upper:]')
    export "$var"="$(cat "$f")"
done

# Drop privileges and exec
exec gosu council "$@"
```

**Third-party images** (Scribe, CortaStore): Same pattern must be applied to their respective Dockerfiles. These are separate repos but same org.

**Postgres container**: The `pgvector/pgvector:pg16` image already has an internal `postgres` user. The container entrypoint starts as root then drops to `postgres` via `gosu`. Validation required (inspect `ps -o user= -p 1` inside the running container) but no code change expected.

### 2. Container Hardening Flags

All application services in `docker-compose.yaml` must add these security primitives:

```yaml
# Applied to: council-daemon, council-web, scribe, corta-store
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
read_only: true
tmpfs:
  - /tmp:size=100M
pids_limit: 200
```

**Service-specific writable paths** (via tmpfs or named volumes):
- `council-daemon`: `/tmp` (subprocess temp files), `/app/.scribe` (already a volume)
- `council-web`: `/tmp` (Jinja2 template compilation cache), `/app/.scribe` (already a volume)
- `scribe`: `/tmp`, `/app/.scribe` (already a volume)
- `corta-store`: `/tmp`, `/data` (already a volume)

**Postgres exclusion**: Do NOT apply `read_only: true` to postgres. The pgvector image expects writable paths beyond what we can easily enumerate via tmpfs. Postgres hardening is limited to `cap_drop`, `security_opt`, and `pids_limit`.

### 3. Image Pinning Policy

All images referenced in production compose files must use immutable tags:
- **Platform images** (daemon, web): Tagged with git commit SHA (`ghcr.io/cortalabs/mcp_spine/daemon:abc1234`). The `latest` tag is also pushed but `docker-compose.yaml` references the SHA tag via `IMAGE_TAG` variable.
- **Third-party images**: Pin to digest where stable (`pgvector/pgvector:pg16@sha256:...`) or to specific minor version tags (`pg16` is acceptable if the image maintainer follows semver).
- **Scribe/CortaStore standalone**: When building on-server, the compose build context is pinned by the git commit on disk. When GHCR builds are added later, same SHA tagging pattern applies.

This is naturally handled by Phase 1 (P1.2 and P1.3) which establish GHCR builds with SHA tags. A verification item is added to the P1.2 checklist.

### Architecture Decision Records (continued)

**ADR-8: Non-Root Containers via gosu Privilege Drop**
- **Decision**: Add a `council` user (UID 1000) to the Dockerfile. Entrypoint reads secrets as root, then drops to `council` via `exec gosu council "$@"`.
- **Rationale**: Running application processes as root inside containers is unnecessary and increases blast radius of any code execution vulnerability. The gosu pattern is the Docker-standard approach when secrets must be read at startup as root.
- **Trade-off**: Requires `gosu` in the image (~1MB). File permissions must be correct for the `council` user. Debugging may require `docker exec -u root` for privileged operations.
- **Alternatives rejected**: (1) USER directive without gosu -- cannot read Docker Secrets files which are root-owned. (2) Modifying secret file permissions in compose -- introduces compose complexity and may not work with all Docker versions.

**ADR-9: Defense-in-Depth Container Hardening**
- **Decision**: Apply `read_only`, `cap_drop: ALL`, `security_opt: no-new-privileges`, and `pids_limit` to all application containers. Postgres gets cap_drop + security_opt + pids_limit but NOT read_only.
- **Rationale**: These are zero-cost security primitives that restrict container capabilities without impacting normal operation. `read_only` prevents filesystem tampering. `cap_drop: ALL` removes all Linux capabilities (none needed for Python apps). `no-new-privileges` blocks SUID binaries. `pids_limit` prevents fork bombs.
- **Trade-off**: `read_only` requires explicit tmpfs mounts for writable paths. Any new writable path needed by the application requires a compose change. This is a feature, not a bug -- it forces intentional decisions about filesystem writes.
- **Postgres exception**: PostgreSQL manages its own filesystem layout extensively (WAL, shared memory, temp tables). Constraining it with `read_only` risks subtle data corruption or write failures. The pgvector image handles its own security posture via internal gosu.

## Open Questions and Follow-Ups

| Item | Owner | Status | Decision |
|------|-------|--------|----------|
| Should scribe/corta-store images also build from GHCR? | Blueprint | Decided | No. They build from their own Dockerfiles in the compose stack. Only daemon + web images go through GHCR since they are the primary platform images. Scribe and corta-store build on-server since they are simple single-stage builds. |
| How to handle council removal? | Deferred | Open | For now, manual: delete from `/opt/councils/`, remove from manifest, deregister via API. Auto-detection deferred to Phase 4. |
| Should we add a `deploy` user on Hetzner? | Operator | Recommended | Yes. A dedicated `deploy` user with sudo for docker commands, SSH key auth only. Reduces blast radius vs using `root` or `ubuntu`. |
| Monorepo sub-councils (scribe_mcp, knowledge_mcp) strategy? | Blueprint | Decided | Symlink from `/opt/councils/scribe_mcp` -> `/opt/council_mcp/../scribe_mcp`. Both are under `/opt/MCP_SPINE/` already. The platform deploy pulls the full monorepo; sub-councils get updated automatically. |
| GitHub Actions minutes budget? | Operator | Open | Current estimate: ~5 min per platform build, ~1 min per downstream sync. At ~2 pushes/day, ~15 min/day. Well within free tier for public repos, or paid org tier. |
| Postgres effective runtime user? | Phase 5 | Open | Must validate with `docker exec council-postgres ps -o user= -p 1`. Expected: `postgres`. If confirmed, no code change needed. If root, will need compose `user:` override or entrypoint investigation. |
<!-- ID: references_appendix -->
- PROGRESS_LOG.md
- ARCHITECTURE_GUIDE.md

Generated via generate_doc_templates.


---