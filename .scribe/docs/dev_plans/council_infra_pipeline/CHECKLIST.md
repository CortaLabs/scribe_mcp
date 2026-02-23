---
id: council_infra_pipeline-checklist
title: Acceptance Checklist -- council_infra_pipeline
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 03:20:41 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# Acceptance Checklist -- council_infra_pipeline
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 03:10:00 UTC

> Acceptance checklist for council_infra_pipeline.

---
<!-- ID: documentation_hygiene -->
## Documentation Hygiene
- [ ] ARCHITECTURE_GUIDE.md is complete with all sections including Security Hardening (proof: file exists, no TODOs)
- [ ] PHASE_PLAN.md has all 5 phases with task packages (proof: file exists, 16 task packages P1.1-P5.5)
- [ ] CHECKLIST.md tracks all acceptance criteria (proof: this file)
- [ ] All ADRs documented in architecture guide (proof: 9 ADRs -- ADR-1 through ADR-9 including security ADRs)

---

## Phase 1 -- Platform CI/CD Pipeline

### P1.1 Deploy Scripts
- [x] `deploy/scripts/deploy.sh` exists and passes `bash -n` syntax check (proof: `bash -n` PASS)
- [x] `deploy/scripts/health-check.sh` exists and passes `bash -n` syntax check (proof: `bash -n` PASS)
- [x] `deploy/scripts/rollback.sh` exists and passes `bash -n` syntax check (proof: `bash -n` PASS)
- [x] All scripts have `#!/bin/bash` and `set -euo pipefail` (proof: `#!/usr/bin/env bash` + `set -euo pipefail` verified)
- [x] All scripts are executable (`chmod +x`) (proof: `test -x` returns yes for all 3)
- [x] deploy.sh writes secrets to `/opt/council_mcp/secrets/*.txt` with correct permissions (proof: write_secret function uses `chmod 600`)
- [x] health-check.sh checks all 5 services in order (postgres, daemon, web, scribe, corta-store) (proof: 5 check_service calls in order with correct commands)
- [x] rollback.sh accepts previous tag as argument and reverts (proof: `ROLLBACK_TAG="$1"` with validation)

### P1.2 Docker Compose Image Tag Support
- [ ] docker-compose.yaml has `image:` directives for daemon and web services with `${DOCKER_IMAGE_TAG:-latest}`
- [ ] `docker compose -f deploy/docker-compose.yaml config` validates without errors
- [ ] Local `docker compose build` still works (backward compatible)
- [ ] `.env.example` has `DOCKER_IMAGE_TAG` and `ENVIRONMENT` entries
- [ ] Images tagged with commit SHA (immutable tags for security pinning -- feeds P5.5)

### P1.3 GitHub Actions Platform Workflow
- [ ] `.github/workflows/platform.yml` exists and is valid YAML
- [ ] Workflow triggers on `push` to `master` and `workflow_dispatch`
- [ ] Test job runs pytest subset (not full suite)
- [ ] Build job pushes to `ghcr.io/cortalabs/mcp_spine/{daemon,web}:SHA`
- [ ] Deploy job uses Tailscale ephemeral node for SSH
- [ ] Deploy job calls deploy.sh with secrets passed as env vars
- [ ] Deploy job captures previous SHA for rollback capability

### P1.2 Docker Compose Image Tag Support
- [x] docker-compose.yaml has `image:` directives for daemon and web services with `${DOCKER_IMAGE_TAG:-latest}` -- lines 156 and 241
- [x] `docker compose -f deploy/docker-compose.yaml config` validates without errors -- exit code 0
- [x] Local `docker compose build` still works (backward compatible) -- build directives intact with context/dockerfile/target
- [x] `.env.example` has `DOCKER_IMAGE_TAG` and `ENVIRONMENT` entries -- deploy/.env.example lines 78,84
- [x] Images tagged with commit SHA (immutable tags for security pinning -- feeds P5.5) -- DOCKER_IMAGE_TAG=abc123 resolves to :abc123

---

## Phase 2 -- Multi-Council Deployment

### P2.1 Docker Compose Bind Mount and Manifest
- [ ] docker-compose.yaml has `${COUNCILS_ROOT:-/opt/councils}:/councils:ro` on council-web service ONLY
- [ ] `COUNCILS_ROOT=/councils` environment variable set on council-web
- [ ] `deploy/councils/manifest.yaml` exists with all 6 councils listed
- [ ] Manifest includes symlink entries for scribe_mcp and knowledge_mcp
- [ ] `docker compose config` validates with new volume

### P2.2 Setup Councils Script
- [ ] `deploy/scripts/setup-councils.sh` exists and passes syntax check
- [ ] Script reads manifest.yaml correctly
- [ ] Script handles `repo: symlink` entries (creates symlinks)
- [ ] Script handles git URL entries (clones or updates)
- [ ] Script is idempotent (safe to run multiple times)
- [ ] Script reports success/failure count

### P2.3 Council Registration
- [ ] `deploy/scripts/register-councils.sh` exists and passes syntax check
- [ ] Script uses container paths (`/councils/...`) not host paths (`/opt/councils/...`)
- [ ] deploy.sh calls register-councils.sh after health check
- [ ] Registration failures are non-fatal (do not trigger rollback)

### Phase 2 Gate
- [ ] All P2.1-P2.3 items checked
- [ ] Councils are cloned/symlinked under `/opt/councils/` on council-hub
- [ ] Councils appear in web UI after registration
- [ ] Custom pages from downstream councils load correctly
- [ ] Arbiter review >= 93%

---

## Phase 3 -- Downstream CI/CD

### P3.1 Reusable Sync Workflow
- [ ] `.github/workflows/sync-council.yml` exists in MCP_SPINE repo
- [ ] Workflow uses `workflow_call` trigger with `council_name`, `council_path`, `branch` inputs
- [ ] Workflow connects via Tailscale and uses SSH to sync code
- [ ] Workflow triggers cache clear on web container after sync
- [ ] Workflow registers/re-registers council after sync

### P3.2 Downstream Caller Workflows
- [ ] `sync.yml` exists in voicelab, rom_lab, MyBB_Playground, osrs_hiscore_pull repos
- [ ] Each caller uses `CortaLabs/MCP_SPINE/.github/workflows/sync-council.yml@master`
- [ ] Each caller passes correct `council_name` and `council_path`
- [ ] `secrets: inherit` is set on all callers
- [ ] scribe_mcp and knowledge_mcp do NOT have caller workflows (monorepo sub-projects)

### Phase 3 Gate
- [ ] All P3.1-P3.2 items checked
- [ ] Push to a downstream repo triggers sync workflow
- [ ] Code changes appear on council-hub after workflow completes
- [ ] Web UI shows updated council pages after sync
- [ ] Arbiter review >= 93%

---

## Phase 4 -- Hardening and Future-Proofing

### P4.1 Server Node Registry Schema
- [ ] `agentkit_extensions/db/schema_extensions/council/server_nodes.sql` exists
- [ ] Contains `server_nodes` and `deploy_targets` tables in `council` schema
- [ ] `agentkit-schema plan` shows tables without errors
- [ ] `agentkit-schema apply` creates tables successfully
- [ ] Tables have proper indexes

### P4.2 GHCR Image Cleanup
- [ ] `.github/workflows/cleanup-images.yml` exists
- [ ] Workflow runs on weekly schedule (Sunday 6 AM UTC)
- [ ] Keeps `latest` tag and last 10 versions
- [ ] Deletes untagged versions older than 30 days
- [ ] Manual trigger via `workflow_dispatch` works

### P4.3 Operations Documentation
- [ ] `deploy/OPERATIONS.md` exists
- [ ] Contains all required sections (overview, deploy flow, manual ops, adding council, troubleshooting, secrets rotation, monitoring, rollback, disaster recovery)
- [ ] All commands in the doc are accurate
- [ ] No placeholder/TODO sections remain

### Phase 4 Gate
- [ ] All P4.1-P4.3 items checked
- [ ] Schema applied without breaking existing tables
- [ ] Cleanup workflow dry-run succeeds
- [ ] Ops doc reviewed and accurate
- [ ] Arbiter review >= 93%

---

## Phase 5 -- Docker Security Hardening

### P5.1 Council Image Non-Root Conversion
- [ ] `deploy/Dockerfile` creates `council` user (UID 1000, GID 1000)
- [ ] `deploy/Dockerfile` installs `gosu` package
- [ ] `deploy/Dockerfile` has `RUN chown -R council:council /app` after final COPY
- [ ] `deploy/docker-entrypoint.sh` uses `exec gosu council "$@"` after reading secrets
- [ ] `docker exec council-daemon id` shows `uid=1000(council)`
- [ ] `docker exec council-web id` shows `uid=1000(council)`
- [ ] All health checks pass after rebuild
- [ ] No permission errors in daemon or web logs

### P5.2 Compose Hardening -- Stateless Services (daemon, web)
- [ ] `council-daemon` has `read_only: true`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `pids_limit: 200`
- [ ] `council-web` has `read_only: true`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `pids_limit: 200`
- [ ] Both services have `tmpfs: [/tmp:size=100M]`
- [ ] `docker compose config` validates without errors
- [ ] `docker inspect council-daemon --format '{{.HostConfig.ReadonlyRootfs}}'` returns `true`
- [ ] `docker inspect council-web --format '{{.HostConfig.ReadonlyRootfs}}'` returns `true`
- [ ] No write errors in logs for 10+ minutes of normal operation
- [ ] MCP tools respond, web UI loads, Scribe logging works

### P5.3 Compose Hardening -- Scribe and CortaStore
- [ ] Scribe Dockerfile creates non-root user with gosu privilege drop
- [ ] CortaStore Dockerfile creates non-root user with gosu privilege drop
- [ ] `scribe` service has `read_only`, `cap_drop`, `security_opt`, `pids_limit`, `tmpfs`
- [ ] `corta-store` service has `read_only`, `cap_drop`, `security_opt`, `pids_limit`, `tmpfs`
- [ ] `docker exec scribe-mcp id` shows non-root user
- [ ] `docker exec corta-store id` shows non-root user
- [ ] All health checks pass
- [ ] Scribe append_entry works, CortaStore health responds
- [ ] No permission errors in logs for 10+ minutes

### P5.4 Postgres User Validation
- [ ] `docker exec council-postgres ps -o user= -p 1` output documented
- [ ] Effective user is non-root (expected: `postgres`)
- [ ] If non-root: `cap_drop: ALL` + `cap_add` (CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID) applied
- [ ] `security_opt: [no-new-privileges:true]` applied
- [ ] `pids_limit: 300` applied
- [ ] `read_only` is NOT applied to postgres (explicit exclusion per ADR-9)
- [ ] `pg_isready -U council` returns success after restart
- [ ] Existing data intact (`SELECT count(*) FROM persona_profiles` returns expected count)
- [ ] No permission errors in postgres logs for 10+ minutes

### P5.5 Image Tag Pinning Verification
- [ ] `platform.yml` tags images with commit SHA (verify, do not modify)
- [ ] `docker-compose.yaml` uses `${IMAGE_TAG:-latest}` for daemon and web (verify)
- [ ] Postgres image pinned to `pgvector/pgvector:pg16@sha256:<digest>`
- [ ] `docker compose pull` works with pinned digest
- [ ] All services start successfully with pinned images

### Phase 5 Gate
- [ ] All P5.1-P5.5 items checked
- [ ] `docker inspect` shows non-root user for all app services
- [ ] Services remain healthy after restart (docker ps shows healthy for 30+ minutes)
- [ ] No regression in MCP/web endpoints
- [ ] No write errors from read-only rootfs (logs clean for 30+ minutes)
- [ ] Rollback command documented and tested (can revert security changes if needed)
- [ ] Arbiter review >= 93%

---

## Security Checklist

### Infrastructure Security (Phases 1-4)
- [ ] No secrets committed to git (all in GitHub Secrets or `/opt/council_mcp/secrets/`)
- [ ] Docker ports bound to `${TAILSCALE_IP}` only (never `0.0.0.0`)
- [ ] Deploy SSH key has minimal permissions (read-only to repos)
- [ ] Tailscale OAuth uses ephemeral nodes (auto-expire)
- [ ] GHCR packages are org-scoped (not public)
- [ ] API key auth required for council registration endpoint
- [ ] Secrets files on server have `chmod 600`
- [ ] No secrets echoed in CI/CD logs (use `::add-mask::`)

### Container Security (Phase 5)
- [ ] All application containers run as non-root (council UID 1000)
- [ ] All application containers have `cap_drop: ALL`
- [ ] All application containers have `security_opt: no-new-privileges:true`
- [ ] All application containers have `read_only: true` with explicit tmpfs for writable paths
- [ ] All application containers have `pids_limit` set
- [ ] Postgres has `cap_drop: ALL` + minimum `cap_add` (CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID)
- [ ] Postgres does NOT have `read_only: true` (explicit exclusion)
- [ ] All platform images use immutable SHA tags from GHCR
- [ ] Postgres image pinned to digest
- [ ] Privilege drop via gosu verified at runtime (not just Dockerfile inspection)

---

## Rollback Verification

- [ ] rollback.sh can revert to previous image tag
- [ ] Rollback triggers health-check.sh to verify success
- [ ] deploy.sh captures previous SHA before deploying new one
- [ ] Manual rollback procedure documented in OPERATIONS.md
- [ ] Database backup runs before every deploy (backup-postgres.sh)
- [ ] Security hardening changes can be reverted by removing compose flags (no data migration needed)

---
<!-- ID: phase_0 -->
## End-to-End Integration
- [ ] Push to MCP_SPINE master triggers full platform.yml pipeline (test -> build -> deploy)
- [ ] Push to downstream repo triggers sync-council.yml via caller workflow
- [ ] All 6 downstream councils visible in web UI after full deploy
- [ ] Custom pages from downstream councils render correctly
- [ ] Rollback procedure tested and working
- [ ] No manual intervention required for standard deploy flow
- [ ] All containers running as non-root with hardening flags (post-Phase 5)
<!-- ID: final_verification -->
## Final Verification
- [ ] All phase gate items checked with proof evidence attached (Phases 1-5)
- [ ] Security checklist fully green (both infrastructure and container sections)
- [ ] Rollback verification complete
- [ ] End-to-end integration test passed
- [ ] Operations documentation reviewed by operator
- [ ] Arbiter final review >= 93%
- [ ] Operator sign-off recorded (name + date)
