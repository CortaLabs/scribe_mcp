---
id: council_infra_pipeline-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 council_infra_pipeline"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 03:08:15 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — council_infra_pipeline
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-17 01:48:55 UTC

> Execution roadmap for council_infra_pipeline.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview

| Phase | Goal | Key Deliverables | Est. Duration | Dependencies |
|-------|------|------------------|---------------|-------------|
| Phase 1 -- Platform CI/CD | Build + deploy pipeline for MCP_SPINE | platform.yml, deploy.sh, health-check.sh, rollback.sh | 3-5 days | GitHub Secrets setup (manual) |
| Phase 2 -- Multi-Council Deployment | Downstream repos cloned + bind-mounted + registered | sync-councils.sh, setup-councils.sh, docker-compose.yaml mod, manifest.yaml | 2-3 days | Phase 1 |
| Phase 3 -- Downstream CI/CD | Reusable sync workflow + caller workflows | sync-council.yml, per-repo caller workflows | 2-3 days | Phase 2 |
| Phase 4 -- Hardening and Future-Proofing | Node registry, GHCR cleanup, documentation | server_nodes schema, image retention, ops docs | 2-3 days | Phase 3 |
| Phase 5 -- Docker Security Hardening | Non-root containers, compose hardening, image pinning | Dockerfile user, entrypoint gosu, compose flags, postgres validation | 2-3 days | Phase 1 (P1.2 for image tags) |

**Total estimated duration**: 12-19 days (sequential, including Phase 5). Phases 1-4 are strictly sequential. Phase 5 depends only on Phase 1 and can run in parallel with Phases 2-4, but is sequenced last to avoid disrupting other phases.

**Critical path**: Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5

**Phase 5 rationale**: Security hardening is separated from Phase 4 (future-proofing) because it has distinct validation requirements, different risk profile, and its own rollback criteria. The security review (REVIEW_DOCKER_SECURITY.md) identified 2 HIGH and 2 MEDIUM severity findings that must be addressed as bounded, auditable task packages.
<!-- ID: phase_0 -->
## Phase 1 -- Platform CI/CD Pipeline

**Objective**: Create a complete CI/CD pipeline that builds Docker images on GitHub Actions, pushes to GHCR, and deploys to Hetzner via Tailscale SSH with health checks and rollback.

**Prerequisites (Manual, Operator)**:
- Create Tailscale OAuth app, store `TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_SECRET` in GitHub org secrets
- Store production secrets in GitHub repo secrets: `PROD_PG_PASSWORD`, `PROD_DATABASE_URL`, `PROD_COUNCIL_API_KEY`, `PROD_OPENAI_API_KEY`, `PROD_SCRIBE_DB_URL`, `PROD_STORE_HMAC_KEY`
- Store SSH deploy key in `DEPLOY_SSH_KEY` GitHub secret (or create `deploy` user on Hetzner)
- Create "production" environment in GitHub repo settings with optional approval rules
- Ensure GHCR access: repo must be under CortaLabs org, `GITHUB_TOKEN` has `packages:write`

---

### Task Package P1.1: Deploy Scripts

**Scope**: Create the deployment scripts that will be called by GitHub Actions to deploy, health-check, and rollback.

**Files to Create**:
- `deploy/scripts/deploy.sh`
- `deploy/scripts/health-check.sh`
- `deploy/scripts/rollback.sh`

**Dependencies**: None (these are standalone scripts)

#### Specifications

1. **deploy.sh** -- Main deployment orchestrator
   - Takes environment variables: `PG_PASSWORD`, `DATABASE_URL`, `COUNCIL_API_KEY`, `OPENAI_API_KEY`, `SCRIBE_DB_URL`, `STORE_HMAC_KEY`, `DEPLOY_HOST`, `IMAGE_TAG`
   - Writes each secret to `/opt/council_mcp/secrets/<name>.txt` with `chmod 600`
   - Sets `DOCKER_IMAGE_TAG` in `.env` file
   - Runs `docker compose -f deploy/docker-compose.yaml pull`
   - Runs `docker compose -f deploy/docker-compose.yaml up -d --remove-orphans`
   - Calls `health-check.sh`
   - If health-check fails, calls `rollback.sh $PREVIOUS_TAG` and exits 1
   - Signature: `./deploy.sh` (reads from env vars)

2. **health-check.sh** -- Post-deploy verification
   - Takes no arguments (uses localhost inside Hetzner)
   - Checks in order: postgres (`pg_isready -U council`, 60s), daemon (`curl -sf http://localhost:8016/health`, 30s), web (`curl -sf http://localhost:8015/login`, 30s), scribe (`nc -z localhost 8200`, 15s), corta-store (`curl -sf http://localhost:8201/health`, 15s)
   - Uses polling loop with 5s interval for each check
   - Returns 0 if all pass, 1 if any timeout
   - Prints status for each service to stdout

3. **rollback.sh** -- Reverts to previous image
   - Takes `$1` as previous image tag (git SHA)
   - Modifies `.env` to set `DOCKER_IMAGE_TAG=$1`
   - Runs `docker compose pull` then `docker compose up -d`
   - Calls `health-check.sh` to verify rollback succeeded
   - Returns health-check exit code

#### Verification
- [ ] `bash -n deploy/scripts/deploy.sh` passes (syntax check)
- [ ] `bash -n deploy/scripts/health-check.sh` passes
- [ ] `bash -n deploy/scripts/rollback.sh` passes
- [ ] All scripts have `set -euo pipefail` and `#!/bin/bash`
- [ ] All scripts have `chmod +x`

#### Out of Scope (DO NOT TOUCH)
- docker-compose.yaml (that is P1.2)
- GitHub Actions workflow files (that is P1.3)
- Existing deploy scripts (backup-postgres.sh, setup-hetzner.sh, safe-down.sh)

---

### Task Package P1.2: Docker Compose Image Tag Support

**Scope**: Modify docker-compose.yaml to support pulling pre-built images from GHCR instead of always building locally.

**Files to Modify**:
- `deploy/docker-compose.yaml`
- `.env.example`

**Dependencies**: None

#### Specifications

1. **docker-compose.yaml** changes:
   - For `council-daemon` service: add `image: ghcr.io/cortalabs/mcp_spine/daemon:${DOCKER_IMAGE_TAG:-latest}` alongside existing `build` directive
   - For `council-web` service: add `image: ghcr.io/cortalabs/mcp_spine/web:${DOCKER_IMAGE_TAG:-latest}` alongside existing `build` directive
   - When `DOCKER_IMAGE_TAG` is set, `docker compose pull` pulls from GHCR. When unset or building locally, `docker compose build` still works.
   - This dual mode allows local dev (build) and prod (pull from GHCR) to coexist.

2. **.env.example** changes:
   - Add `ENVIRONMENT=dev` line
   - Add `DOCKER_IMAGE_TAG=latest` line (commented out, with note: "Set by CI/CD deploy script")

#### Verification
- [ ] `docker compose -f deploy/docker-compose.yaml config` validates without errors
- [ ] Local `docker compose build` still works (image tag defaults to latest)
- [ ] With `DOCKER_IMAGE_TAG=abc123`, `docker compose pull` would attempt to pull from GHCR

#### Out of Scope (DO NOT TOUCH)
- Dockerfile (no changes needed)
- Service resource limits, ports, volumes (except adding councils bind mount in P2.1)
- Scribe/corta-store services (they keep building locally)

---

### Task Package P1.3: GitHub Actions Platform Workflow

**Scope**: Create the main CI/CD workflow that triggers on push to master, builds images, pushes to GHCR, and deploys.

**Files to Create**:
- `.github/workflows/platform.yml`

**Dependencies**: P1.1 (deploy scripts), P1.2 (docker-compose image tag support)

#### Specifications

1. **Trigger**: `push` to `master` branch, plus `workflow_dispatch` for manual trigger

2. **Job: test**
   - `runs-on: ubuntu-latest`
   - Steps: checkout, setup-python 3.12, pip install council_mcp deps (cached), run fast pytest subset
   - Pytest command: `pytest tests/test_config.py tests/test_tools.py -x --timeout=60 -q`

3. **Job: build** (needs: test)
   - `runs-on: ubuntu-latest`
   - Steps:
     - Checkout
     - `docker/setup-buildx-action@v3`
     - `docker/login-action@v3` with `registry: ghcr.io`, `username: ${{ github.actor }}`, `password: ${{ secrets.GITHUB_TOKEN }}`
     - `docker/build-push-action@v5` for daemon target: context `./council_mcp`, file `./council_mcp/deploy/Dockerfile`, target `daemon`, push `true`, tags `ghcr.io/cortalabs/mcp_spine/daemon:${{ github.sha }}` and `ghcr.io/cortalabs/mcp_spine/daemon:latest`, cache-from/to registry
     - Same for web target
   - Outputs: `image_tag: ${{ github.sha }}`

4. **Job: deploy** (needs: build, environment: production)
   - `runs-on: ubuntu-latest`
   - Steps:
     - Checkout
     - `tailscale/github-action@v4` with OAuth credentials from secrets
     - SSH setup: write `DEPLOY_SSH_KEY` to `~/.ssh/deploy_key`, chmod 600
     - Pre-deploy backup: `ssh deploy@council-hub "cd /opt/council_mcp && ./deploy/scripts/backup-postgres.sh"`
     - Git pull: `ssh deploy@council-hub "cd /opt/council_mcp && git pull"`
     - GHCR login on server: `ssh deploy@council-hub "docker login ghcr.io -u $GITHUB_ACTOR -p $GITHUB_TOKEN"`
     - Deploy: pass all secrets as env vars, SSH to run `deploy.sh`
     - Capture previous SHA for rollback

#### Verification
- [ ] Workflow YAML is valid (use `act` or GitHub Actions YAML validator)
- [ ] Manually trigger workflow via `workflow_dispatch` and observe all jobs
- [ ] Build job pushes images to GHCR (check Packages tab)
- [ ] Deploy job connects via Tailscale and executes deploy.sh on council-hub

#### Out of Scope (DO NOT TOUCH)
- Downstream council sync (that is Phase 3)
- Dockerfile changes
- Any application source code
<!-- ID: phase_1 -->
## Phase 2 -- Multi-Council Deployment

**Objective**: Set up the infrastructure for downstream council repos to be cloned on prod, bind-mounted into Docker containers, and registered in the Council web UI.

**Prerequisites**:
- Phase 1 complete and verified (platform deploys successfully via CI/CD)
- Operator has SSH access to council-hub for initial repo cloning

---

### Task Package P2.1: Docker Compose Bind Mount and Council Directory

**Scope**: Modify docker-compose.yaml to add the councils bind mount and create the council manifest file.

**Files to Modify**:
- `deploy/docker-compose.yaml`

**Files to Create**:
- `deploy/councils/manifest.yaml`

**Dependencies**: P1.2 (docker-compose changes merged)

#### Specifications

1. **docker-compose.yaml** -- Add councils volume to `council-web` service:
   - Add volume: `${COUNCILS_ROOT:-/opt/councils}:/councils:ro`
   - Add environment variable: `COUNCILS_ROOT=/councils` to council-web service
   - Do NOT add this volume to daemon, scribe, or corta-store services (they do not need downstream repo access)

2. **manifest.yaml** -- Council registry manifest:
   ```yaml
   # deploy/councils/manifest.yaml
   # Downstream councils to clone and register on prod
   # name: human-readable name
   # repo: git clone URL (SSH format for deploy key auth)
   # path: directory name under /opt/councils/
   # branch: branch to track (default: main or master)
   councils:
     - name: VoiceLab
       repo: git@github.com:CortaLabs/voicelab.git
       path: voicelab
       branch: main
     - name: ROM Lab
       repo: git@github.com:CortaLabs/rom_lab.git
       path: rom_lab
       branch: main
     - name: MyBB Playground
       repo: git@github.com:CortaLabs/MyBB_Playground.git
       path: MyBB_Playground
       branch: main
     - name: OSRS Hiscore Pull
       repo: git@github.com:CortaLabs/osrs_hiscore_pull.git
       path: osrs_hiscore_pull
       branch: main
     - name: Scribe MCP
       repo: symlink
       path: scribe_mcp
       symlink_target: /opt/council_mcp/../scribe_mcp
       branch: null
     - name: Knowledge MCP
       repo: symlink
       path: knowledge_mcp
       symlink_target: /opt/council_mcp/../knowledge_mcp
       branch: null
   ```
   - Scribe MCP and Knowledge MCP are symlinks because they live inside the already-cloned MCP_SPINE monorepo
   - The `repo: symlink` sentinel tells setup-councils.sh to create a symlink instead of git clone

#### Verification
- [ ] `docker compose -f deploy/docker-compose.yaml config` validates with councils volume
- [ ] manifest.yaml is valid YAML (`python -c "import yaml; yaml.safe_load(open('deploy/councils/manifest.yaml'))"`)
- [ ] Only council-web has the councils bind mount (not daemon, scribe, corta-store)

#### Out of Scope (DO NOT TOUCH)
- setup-councils.sh (that is P2.2)
- Council registration logic (that is P2.3)
- Application source code
- Existing deploy scripts from Phase 1

---

### Task Package P2.2: Setup Councils Script

**Scope**: Create the script that reads manifest.yaml and clones/symlinks all downstream repos on the production server.

**Files to Create**:
- `deploy/scripts/setup-councils.sh`

**Dependencies**: P2.1 (manifest.yaml exists)

#### Specifications

1. **setup-councils.sh** -- One-time setup and incremental sync:
   - Reads `deploy/councils/manifest.yaml` using a lightweight YAML parser (python one-liner or `yq`)
   - For each entry:
     - If `repo: symlink`: creates symlink at `/opt/councils/$path` pointing to `$symlink_target`
     - If repo is a git URL: checks if `/opt/councils/$path` exists
       - If not: `git clone --branch $branch $repo /opt/councils/$path`
       - If exists: `cd /opt/councils/$path && git fetch && git reset --hard origin/$branch`
   - Creates `/opt/councils/` directory if it does not exist
   - Sets permissions: `chown -R 1000:1000 /opt/councils/` (match container UID)
   - Prints summary of actions taken
   - Signature: `./setup-councils.sh [--manifest PATH]` (default: `deploy/councils/manifest.yaml`)
   - Must be idempotent (safe to run multiple times)

2. **Error handling**:
   - Continues on clone failure (logs error, does not abort)
   - Reports final count: "X/Y councils set up successfully"
   - Exits 0 if all succeed, exits 1 if any fail

#### Verification
- [ ] `bash -n deploy/scripts/setup-councils.sh` passes (syntax check)
- [ ] Script has `set -euo pipefail` and `#!/bin/bash`
- [ ] Script has `chmod +x`
- [ ] Script reads manifest.yaml correctly (dry-run test with echo instead of git clone)

#### Out of Scope (DO NOT TOUCH)
- docker-compose.yaml (already modified in P2.1)
- Council web registration (that is P2.3)
- GitHub Actions workflows

---

### Task Package P2.3: Council Registration on Deploy

**Scope**: Add automatic council registration to the deploy process so downstream councils appear in the web UI after deploy.

**Files to Modify**:
- `deploy/scripts/deploy.sh` (add registration step after health check)

**Files to Create**:
- `deploy/scripts/register-councils.sh`

**Dependencies**: P2.1 (manifest.yaml), P2.2 (councils cloned), P1.1 (deploy.sh exists)

#### Specifications

1. **register-councils.sh** -- Register councils via web API:
   - Reads `deploy/councils/manifest.yaml`
   - For each council, calls: `curl -sf -X POST http://localhost:8015/api/councils/register -H "Authorization: Bearer $COUNCIL_API_KEY" -H "Content-Type: application/json" -d '{"name": "$name", "repo_path": "/councils/$path"}'`
   - The `/api/councils/register` endpoint is idempotent (uses `ON CONFLICT` in DB)
   - Uses container path `/councils/$path` (not host path `/opt/councils/$path`) because the web UI runs inside the container
   - Requires `COUNCIL_API_KEY` environment variable (loaded from secrets)
   - Reports registration results per council

2. **deploy.sh modification** -- Add post-health-check step:
   - After successful health check, call `./deploy/scripts/register-councils.sh`
   - Registration failure is non-fatal (log warning, do not trigger rollback)
   - Add comment: "# Register downstream councils (non-fatal)"

#### Verification
- [ ] `bash -n deploy/scripts/register-councils.sh` passes
- [ ] register-councils.sh correctly uses container paths (`/councils/...`) not host paths (`/opt/councils/...`)
- [ ] deploy.sh calls register-councils.sh after health check
- [ ] Registration failures do not trigger rollback

#### Out of Scope (DO NOT TOUCH)
- Council registration API endpoint code (already exists in web app)
- Council discovery/template loading code
- GitHub Actions workflows (registration happens during deploy, not in CI)
<!-- ID: milestone_tracking -->
## Phase 3 -- Downstream CI/CD

**Objective**: Create a reusable GitHub Actions workflow that downstream repos can call to sync their changes to the production server, and add caller workflows to each downstream repo.

**Prerequisites**:
- Phase 2 complete (councils cloned on prod, bind-mounted, registered)
- Deploy key on council-hub can pull from all downstream repos

---

### Task Package P3.1: Reusable Sync Council Workflow

**Scope**: Create a reusable GitHub Actions workflow in MCP_SPINE that downstream repos call to sync their code to prod.

**Files to Create**:
- `.github/workflows/sync-council.yml`

**Dependencies**: P1.3 (platform.yml exists as reference), P2.2 (setup-councils.sh for reference)

#### Specifications

1. **Workflow type**: `workflow_call` (reusable workflow, called by downstream repos)

2. **Inputs**:
   - `council_name` (required, string): human-readable name
   - `council_path` (required, string): directory name under `/opt/councils/`
   - `branch` (optional, string, default: "main"): branch to sync

3. **Secrets** (inherited from caller via `secrets: inherit`):
   - `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET`
   - `DEPLOY_SSH_KEY`
   - `PROD_COUNCIL_API_KEY`

4. **Job: sync**:
   - `runs-on: ubuntu-latest`
   - Steps:
     - `tailscale/github-action@v4` with OAuth credentials
     - SSH setup (write deploy key)
     - SSH to council-hub: `cd /opt/councils/$council_path && git fetch && git reset --hard origin/$branch`
     - SSH to council-hub: `docker compose -f /opt/council_mcp/deploy/docker-compose.yaml exec -T council-web curl -sf http://localhost:8015/api/system/clear-cache` (trigger template cache refresh)
     - Register council: `curl -sf -X POST http://localhost:8015/api/councils/register -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"name": "$council_name", "repo_path": "/councils/$council_path"}'`

5. **No Docker build needed** -- downstream repos are source-only (bind-mounted), not containerized

#### Verification
- [ ] Workflow YAML is valid (GitHub Actions schema)
- [ ] `workflow_call` trigger is correctly defined with inputs and secrets
- [ ] SSH commands use correct paths (`/opt/councils/` on host)
- [ ] Cache clear step targets the web container correctly

#### Out of Scope (DO NOT TOUCH)
- platform.yml (Phase 1 workflow)
- Downstream repo code
- Docker/container configuration

---

### Task Package P3.2: Downstream Caller Workflows

**Scope**: Create GitHub Actions caller workflows in each of the 4 standalone downstream repos that invoke the reusable sync-council.yml.

**Files to Create** (in each downstream repo):
- `voicelab/.github/workflows/sync.yml`
- `rom_lab/.github/workflows/sync.yml`
- `MyBB_Playground/.github/workflows/sync.yml`
- `osrs_hiscore_pull/.github/workflows/sync.yml`

**Dependencies**: P3.1 (reusable workflow exists in MCP_SPINE)

#### Specifications

1. **Each caller workflow** follows this template:
   ```yaml
   name: Sync to Production
   on:
     push:
       branches: [main]
     workflow_dispatch:

   jobs:
     sync:
       uses: CortaLabs/MCP_SPINE/.github/workflows/sync-council.yml@master
       with:
         council_name: "<human-readable name>"
         council_path: "<directory name>"
         branch: "main"
       secrets: inherit
   ```

2. **Per-repo values**:
   | Repo | council_name | council_path |
   |------|-------------|-------------|
   | voicelab | VoiceLab | voicelab |
   | rom_lab | ROM Lab | rom_lab |
   | MyBB_Playground | MyBB Playground | MyBB_Playground |
   | osrs_hiscore_pull | OSRS Hiscore Pull | osrs_hiscore_pull |

3. **Scribe MCP and Knowledge MCP** do NOT get caller workflows because they are inside MCP_SPINE monorepo (synced by platform.yml git pull)

4. **Secrets requirement**: Each downstream repo must have access to the same GitHub org secrets (Tailscale OAuth, Deploy SSH key, Council API key). Since they are in CortaLabs org, org-level secrets work.

#### Verification
- [ ] Each workflow YAML is valid
- [ ] `uses:` reference points to `CortaLabs/MCP_SPINE/.github/workflows/sync-council.yml@master`
- [ ] `secrets: inherit` is set (not explicit secret passing)
- [ ] Only 4 repos get workflows (not scribe_mcp, not knowledge_mcp)

#### Out of Scope (DO NOT TOUCH)
- MCP_SPINE workflows (platform.yml, sync-council.yml)
- Any application code in downstream repos
- Docker configuration

---

## Phase 4 -- Hardening and Future-Proofing

**Objective**: Add operational polish: server node registry schema for future multi-server, GHCR image cleanup, and comprehensive ops documentation.

**Prerequisites**:
- Phases 1-3 complete and working end-to-end

---

### Task Package P4.1: Server Node Registry Schema

**Scope**: Create the database schema for tracking deployment targets, preparing for future multi-server deployments.

**Files to Create**:
- `agentkit_extensions/db/schema_extensions/council/server_nodes.sql`

**Dependencies**: None (schema-only, no application code changes)

#### Specifications

1. **server_nodes table**:
   ```sql
   CREATE TABLE IF NOT EXISTS council.server_nodes (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       hostname TEXT NOT NULL UNIQUE,
       tailscale_ip INET NOT NULL,
       role TEXT NOT NULL DEFAULT 'primary' CHECK (role IN ('primary', 'worker', 'standby')),
       status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'draining', 'offline')),
       resources JSONB NOT NULL DEFAULT '{}',
       last_heartbeat TIMESTAMPTZ,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   );
   ```

2. **deploy_targets table**:
   ```sql
   CREATE TABLE IF NOT EXISTS council.deploy_targets (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       node_id UUID NOT NULL REFERENCES council.server_nodes(id),
       service TEXT NOT NULL,
       image_tag TEXT,
       deployed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       deployed_by TEXT NOT NULL DEFAULT 'ci',
       status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'rolling', 'failed')),
       metadata JSONB NOT NULL DEFAULT '{}'
   );
   ```

3. **Indexes**:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_server_nodes_status ON council.server_nodes(status);
   CREATE INDEX IF NOT EXISTS idx_deploy_targets_node ON council.deploy_targets(node_id);
   CREATE INDEX IF NOT EXISTS idx_deploy_targets_service ON council.deploy_targets(service);
   ```

4. **Apply via**: `agentkit-schema plan` then `agentkit-schema apply` (standard migration flow)

#### Verification
- [ ] `agentkit-schema plan` shows the new tables without errors
- [ ] `agentkit-schema apply` creates tables in `council` schema
- [ ] `agentkit-schema status` shows clean state after apply
- [ ] Tables exist: `\dt council.server_nodes` and `\dt council.deploy_targets`

#### Out of Scope (DO NOT TOUCH)
- Application code (no API endpoints for node registry yet)
- Existing schema files
- Deploy scripts (they do not read from this table yet)

---

### Task Package P4.2: GHCR Image Retention and Cleanup

**Scope**: Add a GitHub Actions workflow to clean up old container images from GHCR, preventing unbounded storage growth.

**Files to Create**:
- `.github/workflows/cleanup-images.yml`

**Dependencies**: P1.3 (images are being pushed to GHCR)

#### Specifications

1. **Trigger**: `schedule: cron('0 6 * * 0')` (weekly, Sunday 6 AM UTC) plus `workflow_dispatch`

2. **Job: cleanup**:
   - `runs-on: ubuntu-latest`
   - Uses `actions/delete-package-versions@v5` (or equivalent)
   - For each package (`mcp_spine/daemon`, `mcp_spine/web`):
     - Keep last 10 tagged versions
     - Delete untagged versions older than 30 days
     - Keep any version tagged `latest`

3. **Permissions**: `packages: write` required

#### Verification
- [ ] Workflow YAML is valid
- [ ] Cron schedule is correct (weekly Sunday)
- [ ] Keeps `latest` tag and last 10 versions
- [ ] Manual trigger works via `workflow_dispatch`

#### Out of Scope (DO NOT TOUCH)
- platform.yml workflow
- Docker build configuration
- Any application code

---

### Task Package P4.3: Operations Documentation

**Scope**: Create comprehensive operations runbook for the new CI/CD infrastructure.

**Files to Create**:
- `deploy/OPERATIONS.md`

**Dependencies**: Phases 1-3 complete (document what exists)

#### Specifications

1. **Sections to include**:
   - **Overview**: Architecture diagram (ASCII), component list, data flow
   - **Deploy Flow**: Step-by-step what happens on `git push master`
   - **Manual Operations**: How to manually trigger deploy, rollback, add a new council
   - **Adding a New Downstream Council**: Step-by-step (add to manifest, clone, register)
   - **Troubleshooting**: Common failure modes and resolution
   - **Secrets Rotation**: How to rotate each secret type
   - **Monitoring**: What to check, health endpoints, log locations
   - **Rollback Procedure**: Detailed rollback steps with commands
   - **Disaster Recovery**: Database restore, full re-deploy from scratch

2. **Format**: Markdown with command examples, no prose fluff

3. **Audience**: Operator who needs to debug at 2 AM

#### Verification
- [ ] Document exists at `deploy/OPERATIONS.md`
- [ ] All sections listed above are present
- [ ] All commands in the doc are accurate and tested
- [ ] No placeholder/TODO sections remain

#### Out of Scope (DO NOT TOUCH)
- Application documentation
- Any code files
- Existing README files

---

## Milestone Tracking

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| P1.1 Deploy Scripts | Day 1 | Forge | Pending | -- |
| P1.2 Docker Compose Tags | Day 1 | Forge | Pending | -- |
| P1.3 Platform Workflow | Day 2-3 | Forge | Pending | -- |
| Phase 1 Gate | Day 3 | Arbiter | Pending | -- |
| P2.1 Bind Mount + Manifest | Day 4 | Forge | Pending | -- |
| P2.2 Setup Councils Script | Day 4-5 | Forge | Pending | -- |
| P2.3 Council Registration | Day 5 | Forge | Pending | -- |
| Phase 2 Gate | Day 5 | Arbiter | Pending | -- |
| P3.1 Reusable Sync Workflow | Day 6 | Forge | Pending | -- |
| P3.2 Downstream Callers | Day 7 | Forge | Pending | -- |
| Phase 3 Gate | Day 7 | Arbiter | Pending | -- |
| P4.1 Node Registry Schema | Day 8 | Forge | Pending | -- |
| P4.2 Image Cleanup | Day 8 | Forge | Pending | -- |
| P4.3 Ops Documentation | Day 9 | Forge | Pending | -- |
| Phase 4 Gate | Day 9 | Arbiter | Pending | -- |
| Full Pipeline Gate | Day 10 | Arbiter | Pending | -- |
<!-- ID: retro_notes -->
## Phase 5 -- Docker Security Hardening

**Objective**: Harden all Docker containers based on the security review findings (REVIEW_DOCKER_SECURITY.md). Convert application containers to run as non-root, add defense-in-depth compose flags, validate postgres user model, and ensure image pinning is in place.

**Prerequisites**:
- Phase 1 complete (P1.2 establishes image tagging, P1.3 establishes GHCR builds)
- Production stack running and healthy (baseline for regression testing)
- Access to production host for `docker inspect` / `docker exec` validation

**Security Review Reference**: REVIEW_DOCKER_SECURITY.md, findings #1-5

---

### Task Package P5.1: Council Image Non-Root Conversion

**Scope**: Add a non-root `council` user to the Council Dockerfile and modify `docker-entrypoint.sh` to drop privileges after reading secrets.

**Files to Modify**:
- `deploy/Dockerfile` (add user creation, gosu install, chown)
- `deploy/docker-entrypoint.sh` (add gosu exec at end)

**Dependencies**: None (can run first in Phase 5)

#### Specifications

1. **Dockerfile changes** (in the `base` stage, after apt-get install block):
   - Add `RUN groupadd -g 1000 council && useradd -u 1000 -g council -m -s /bin/bash council`
   - Add `gosu` to the apt-get install line (already has `tini` and other packages)
   - After the final `COPY . /app` and `pip install` steps, add `RUN chown -R council:council /app`
   - Do NOT add a `USER council` directive -- the entrypoint handles the privilege drop

2. **Entrypoint changes** (`deploy/docker-entrypoint.sh`):
   - Keep existing secret-reading logic (the `for f in /run/secrets/*` loop)
   - Replace the final `exec "$@"` with `exec gosu council "$@"`
   - Ensure `set -e` is at the top

3. **Do NOT change**: CMD, ENTRYPOINT directives, healthcheck definitions, or any application code

#### Verification
- [ ] `docker build` succeeds for both `daemon` and `web` targets
- [ ] `docker compose up -d` starts all services
- [ ] `docker exec council-daemon id` shows `uid=1000(council) gid=1000(council)`
- [ ] `docker exec council-web id` shows `uid=1000(council) gid=1000(council)`
- [ ] All health checks pass within 120s
- [ ] MCP tools respond (test via `council status`)
- [ ] Web UI loads at `/login`
- [ ] No permission errors in `docker compose logs council-daemon` or `council-web`

#### Out of Scope (DO NOT TOUCH)
- docker-compose.yaml (no compose changes in this task)
- Application Python code
- Scribe or CortaStore Dockerfiles (separate task)
- Postgres container

---

### Task Package P5.2: Compose Hardening -- Stateless Services

**Scope**: Add container hardening flags (`read_only`, `cap_drop`, `security_opt`, `pids_limit`, `tmpfs`) to `council-daemon` and `council-web` services in `docker-compose.yaml`.

**Files to Modify**:
- `deploy/docker-compose.yaml` (council-daemon and council-web service blocks only)

**Dependencies**: P5.1 (non-root user must be in place first, since `read_only` + root can mask permission issues)

#### Specifications

1. **Add to `council-daemon` service** (after `deploy:` block or at service level):
   ```yaml
   read_only: true
   cap_drop:
     - ALL
   security_opt:
     - no-new-privileges:true
   pids_limit: 200
   tmpfs:
     - /tmp:size=100M
   ```

2. **Add to `council-web` service** (same block):
   ```yaml
   read_only: true
   cap_drop:
     - ALL
   security_opt:
     - no-new-privileges:true
   pids_limit: 200
   tmpfs:
     - /tmp:size=100M
   ```

3. **Verify existing volumes**: Both services already have `scribe_data:/app/.scribe` volume mounts. These named volumes are writable regardless of `read_only`. No additional volume mounts needed.

4. **Do NOT modify**: postgres, scribe, or corta-store services in this task

#### Verification
- [ ] `docker compose config` validates without errors
- [ ] `docker compose up -d` starts daemon and web successfully
- [ ] `docker inspect council-daemon --format '{{.HostConfig.ReadonlyRootfs}}'` returns `true`
- [ ] `docker inspect council-web --format '{{.HostConfig.ReadonlyRootfs}}'` returns `true`
- [ ] `docker inspect council-daemon --format '{{.HostConfig.CapDrop}}'` includes `ALL`
- [ ] All health checks pass within 120s
- [ ] No write errors in logs for 10+ minutes of normal operation
- [ ] MCP tools respond, web UI loads, Scribe logging works

#### Out of Scope (DO NOT TOUCH)
- Dockerfile or entrypoint (done in P5.1)
- Scribe and CortaStore services (separate task P5.3)
- Postgres service (separate task P5.4)
- Application code

---

### Task Package P5.3: Compose Hardening -- Scribe and CortaStore

**Scope**: Apply the same container hardening flags to `scribe` and `corta-store` services in `docker-compose.yaml`. These services have their own Dockerfiles in separate repos, so non-root user must also be added to those Dockerfiles.

**Files to Modify**:
- `deploy/docker-compose.yaml` (scribe and corta-store service blocks only)
- `/opt/scribe_mcp/deploy/Dockerfile` (add council user + gosu) -- **cross-repo, coordinate with operator**
- `/opt/corta_store/deploy/Dockerfile` (add council user + gosu) -- **cross-repo, coordinate with operator**

**Dependencies**: P5.2 (validate pattern works on stateless services first)

#### Specifications

1. **Add to `scribe` service** in docker-compose.yaml:
   ```yaml
   read_only: true
   cap_drop:
     - ALL
   security_opt:
     - no-new-privileges:true
   pids_limit: 200
   tmpfs:
     - /tmp:size=100M
   ```

2. **Add to `corta-store` service** in docker-compose.yaml:
   ```yaml
   read_only: true
   cap_drop:
     - ALL
   security_opt:
     - no-new-privileges:true
   pids_limit: 200
   tmpfs:
     - /tmp:size=100M
   ```

3. **Scribe Dockerfile** (same pattern as P5.1):
   - Add `council` user (UID 1000), install `gosu`
   - Modify entrypoint to `exec gosu council "$@"`
   - Ensure `/app/.scribe` is writable by council user

4. **CortaStore Dockerfile** (same pattern):
   - Add `council` user (UID 1000), install `gosu`
   - Modify entrypoint to `exec gosu council "$@"`
   - Ensure `/data` is writable by council user

5. **Existing volumes**: scribe has `scribe_data:/app/.scribe`, corta-store has `corta_store_data:/data`. Both writable regardless of `read_only`.

#### Verification
- [ ] Both Dockerfiles build successfully
- [ ] `docker compose up -d` starts all 5 services
- [ ] `docker exec scribe-mcp id` shows non-root user
- [ ] `docker exec corta-store id` shows non-root user
- [ ] `docker inspect scribe-mcp --format '{{.HostConfig.ReadonlyRootfs}}'` returns `true`
- [ ] `docker inspect corta-store --format '{{.HostConfig.ReadonlyRootfs}}'` returns `true`
- [ ] All health checks pass
- [ ] Scribe append_entry works, CortaStore health endpoint responds
- [ ] No permission errors in logs for 10+ minutes

#### Out of Scope (DO NOT TOUCH)
- Council Dockerfile (done in P5.1)
- Council daemon/web compose sections (done in P5.2)
- Postgres service (separate task)
- Application code in any repo

---

### Task Package P5.4: Postgres User Validation

**Scope**: Validate the effective runtime user of the postgres container. Apply safe hardening flags (cap_drop, security_opt, pids_limit) but explicitly NOT read_only.

**Files to Modify**:
- `deploy/docker-compose.yaml` (postgres service block only) -- conditional on validation results

**Dependencies**: P5.2 (pattern established on stateless services)

#### Specifications

1. **Validation step** (run on production host):
   ```bash
   docker exec council-postgres ps -o user= -p 1
   docker exec council-postgres id
   ```
   Expected output: process runs as `postgres` user (the pgvector image handles this internally).

2. **If confirmed non-root**: Add to postgres service:
   ```yaml
   cap_drop:
     - ALL
   cap_add:
     - CHOWN
     - DAC_OVERRIDE
     - FOWNER
     - SETGID
     - SETUID
   security_opt:
     - no-new-privileges:true
   pids_limit: 300
   ```
   Note: Postgres needs CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID for its entrypoint to initialize the data directory and switch users. These are the minimum required capabilities.

3. **If running as root**: Document the finding and escalate. Do NOT force `user: postgres` without testing data directory permissions. Add an open question to the architecture guide.

4. **Do NOT add `read_only: true`** to postgres under any circumstances.

#### Verification
- [ ] `docker exec council-postgres ps -o user= -p 1` output documented
- [ ] If non-root confirmed: hardening flags added and compose validates
- [ ] `docker compose up -d` restarts postgres successfully
- [ ] `pg_isready -U council` returns success
- [ ] Existing data is intact (run a simple query: `SELECT count(*) FROM persona_profiles`)
- [ ] No permission errors in postgres logs for 10+ minutes
- [ ] agentkit-schema status shows no drift

#### Out of Scope (DO NOT TOUCH)
- Application containers (done in P5.1-P5.3)
- Postgres data or schema
- Any application code
- Postgres image version (do NOT change the base image)

---

### Task Package P5.5: Image Tag Pinning Verification

**Scope**: Verify that the Phase 1 GHCR build pipeline produces SHA-tagged images and that `docker-compose.yaml` uses the `IMAGE_TAG` variable pattern. Pin the postgres base image to a digest.

**Files to Modify**:
- `deploy/docker-compose.yaml` (postgres image line only -- add digest pin)

**Dependencies**: P1.2 and P1.3 (GHCR build pipeline must exist)

#### Specifications

1. **Verify platform images**: Confirm that `platform.yml` tags images with `${{ github.sha }}` (short SHA). This should already be done in P1.3. If not, flag as a gap.

2. **Verify compose uses variable**: Confirm `docker-compose.yaml` uses `image: ghcr.io/cortalabs/mcp_spine/daemon:${IMAGE_TAG:-latest}` pattern from P1.2. If not, flag as a gap.

3. **Pin postgres image**: Change the postgres image line from:
   ```yaml
   image: pgvector/pgvector:pg16
   ```
   to include a digest:
   ```yaml
   image: pgvector/pgvector:pg16@sha256:<current-digest>
   ```
   Obtain the current digest with: `docker inspect pgvector/pgvector:pg16 --format '{{index .RepoDigests 0}}'`

4. **Document pinning policy**: Add a comment in docker-compose.yaml above the postgres image line:
   ```yaml
   # Pinned to digest for reproducible deploys. Update digest when upgrading postgres.
   ```

#### Verification
- [ ] Platform workflow tags images with commit SHA (review platform.yml)
- [ ] docker-compose.yaml uses `${IMAGE_TAG:-latest}` for daemon and web
- [ ] Postgres image includes `@sha256:` digest
- [ ] `docker compose pull` still works with pinned digest
- [ ] `docker compose up -d` starts all services successfully
- [ ] All health checks pass

#### Out of Scope (DO NOT TOUCH)
- Platform workflow logic (just verify, don't modify)
- Application code
- Scribe/CortaStore image tags (they build on-server from local context)

---

## Phase 5 Milestone Tracking

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| P5.1 Non-Root Conversion | Day 11 | Forge | Pending | -- |
| P5.2 Compose Hardening (daemon/web) | Day 11-12 | Forge | Pending | -- |
| P5.3 Compose Hardening (scribe/corta) | Day 12 | Forge | Pending | -- |
| P5.4 Postgres Validation | Day 12 | Forge | Pending | -- |
| P5.5 Image Tag Pinning | Day 13 | Forge | Pending | -- |
| Phase 5 Gate | Day 13 | Arbiter | Pending | -- |

---

## Milestone Tracking

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| P1.1 Deploy Scripts | Day 1 | Forge | Pending | -- |
| P1.2 Docker Compose Tags | Day 1 | Forge | Pending | -- |
| P1.3 Platform Workflow | Day 2-3 | Forge | Pending | -- |
| Phase 1 Gate | Day 3 | Arbiter | Pending | -- |
| P2.1 Bind Mount + Manifest | Day 4 | Forge | Pending | -- |
| P2.2 Setup Councils Script | Day 4-5 | Forge | Pending | -- |
| P2.3 Council Registration | Day 5 | Forge | Pending | -- |
| Phase 2 Gate | Day 5 | Arbiter | Pending | -- |
| P3.1 Reusable Sync Workflow | Day 6 | Forge | Pending | -- |
| P3.2 Downstream Callers | Day 7 | Forge | Pending | -- |
| Phase 3 Gate | Day 7 | Arbiter | Pending | -- |
| P4.1 Node Registry Schema | Day 8 | Forge | Pending | -- |
| P4.2 Image Cleanup | Day 8 | Forge | Pending | -- |
| P4.3 Ops Documentation | Day 9 | Forge | Pending | -- |
| Phase 4 Gate | Day 9 | Arbiter | Pending | -- |
| P5.1 Non-Root Conversion | Day 11 | Forge | Pending | -- |
| P5.2 Compose Hardening (daemon/web) | Day 11-12 | Forge | Pending | -- |
| P5.3 Compose Hardening (scribe/corta) | Day 12 | Forge | Pending | -- |
| P5.4 Postgres Validation | Day 12 | Forge | Pending | -- |
| P5.5 Image Tag Pinning | Day 13 | Forge | Pending | -- |
| Phase 5 Gate | Day 13 | Arbiter | Pending | -- |
| Full Pipeline Gate | Day 14 | Arbiter | Pending | -- |

## Retro Notes and Adjustments

**Phase sequencing rationale**: Phases are strictly sequential because each builds on the prior:
- Phase 1 establishes the build/deploy pipeline (without it, nothing can deploy)
- Phase 2 creates the multi-council infrastructure (requires working deploy to test)
- Phase 3 adds downstream CI triggers (requires councils to exist on prod)
- Phase 4 is operational hardening (documents and optimizes what exists)
- Phase 5 is security hardening (requires working images from Phase 1, lower risk if done after operational stability is established)

**Key design decisions**:
- Full repo clones on prod (operator directive) -- not sparse checkouts. Enables Claude Code, Ray workers, route module imports.
- Build-on-GitHub strategy -- Hetzner CCX23 has only 4 vCPU, building Docker images would spike CPU and risk OOM during deploys.
- Symlinks for monorepo sub-councils (scribe_mcp, knowledge_mcp) -- avoids duplicating MCP_SPINE clone.
- Health-check gated deploys with automatic rollback -- production reliability over deploy speed.
- Reusable workflow pattern -- downstream repos call MCP_SPINE's workflow, centralizing deploy logic.
- Non-root containers via gosu (ADR-8) -- standard Docker security pattern for secret-reading entrypoints.
- Defense-in-depth hardening (ADR-9) -- zero-cost security primitives, postgres excluded from read_only.

**Risk register**:
- GHCR rate limits could slow deploys if many commits land in quick succession (mitigation: cache-from/to in build)
- Tailscale ephemeral node lifetime (default 6h) could be tight for long-running workflows (mitigation: keep jobs under 30min)
- Deploy key must have read access to all downstream repos (mitigation: org-level deploy key or per-repo keys)
- read_only rootfs may break if application writes to unexpected paths (mitigation: test with 10+ min soak, check logs for EROFS errors)
- gosu privilege drop may cause permission errors on volume mounts (mitigation: ensure volume ownership matches council UID 1000)

Update this section as phases complete with lessons learned.
