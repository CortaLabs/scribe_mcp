---
id: council_infra_pipeline-research-current-deploy
title: "\U0001F52C Research Current Deploy \u2014 council_infra_pipeline"
doc_type: RESEARCH_CURRENT_DEPLOY
doc_name: RESEARCH_CURRENT_DEPLOY
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 01:57:17 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Current Deploy — council_infra_pipeline
**Author:** Scribe
**Version:** v0.1
**Status:** in_progress
**Last Updated:** 2026-02-17 01:55:18 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** [Describe the primary research goal]

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** agent-20260216-130610-b59de721

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.
### Finding 1
- **Summary:** [Describe the finding]
- **Evidence:** [Link to logs, code references, or experiments]
- **Confidence:** Medium

### Finding 2
- **Summary:** [Describe the finding]
- **Evidence:** [Link to supporting material]
- **Confidence:** Medium

### Additional Notes
- Capture supporting observations or open follow-ups.


---
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---
# RESEARCH: Current Hetzner Deployment Infrastructure

## Executive Summary

The current deployment is **fully containerized via Docker Compose** on a **Hetzner CCX23 VPS** (16GB RAM, 4 vCPU) behind **Tailscale mesh** encryption. It is **manually deployed** (git pull → docker build → restart) with **NO CI/CD pipeline**. The infrastructure is well-documented and modular, but deployment is operator-driven.

### Current State
- **6 Docker services** (postgres, daemon, web, scribe, corta-store, ray-head placeholder)
- **3 external volumes** protected from accidental deletion (pg_data, scribe_data, corta_store_data)
- **Docker secrets** for password/API key management (pg_password, database_url, api_key, openai_api_key, scribe_db_url, store_hmac_key)
- **Multi-stage Dockerfile** (base → daemon, web) with layer caching for fast rebuilds
- **Docker entrypoint script** that reads secrets and auto-bootstraps database on first run
- **Backup workflow** via shell script (pg_dump + 7-day rotation)
- **Post-provision setup** via setup-hetzner.sh for initial server bringup

**Confidence: HIGH** — All information verified from source files with explicit line numbers.

---

## FINDINGS

### Finding 1: Service Topology and Port Mapping

**Location:** `deploy/docker-compose.yaml` lines 54-445

**Services:**
| Service | Port | Memory | CPU | Purpose |
|---------|------|--------|-----|---------|
| postgres | 5432 | 4GB | 1.0 | PostgreSQL + pgvector |
| council-daemon | 8016 | 2GB | 0.8 | MCP server, WebSocket, process mgmt |
| council-web | 8015 | 1.5GB | 0.6 | FastAPI UI, REST API |
| scribe | 8200 | 2GB | 0.5 | Project logging, managed docs |
| corta-store | 8201 | 512MB | 0.3 | Text object storage (SHA-256) |

**Port Binding:** All ports bind to `${TAILSCALE_IP:-127.0.0.1}` from `deploy/.env` (prevents public exposure).

**Confidence: HIGH**

---

### Finding 2: Docker Secrets Management

**Location:** `deploy/docker-compose.yaml` lines 494-531, `deploy/scripts/setup-hetzner.sh` lines 109-179

**6 Secrets:**
| File | Env Var | Purpose |
|------|---------|---------|
| pg_password.txt | POSTGRES_PASSWORD | PostgreSQL superuser |
| database_url.txt | DATABASE_URL | AgentKit connection string |
| api_key.txt | COUNCIL_API_KEY | Web UI authentication (ck_*) |
| openai_api_key.txt | OPENAI_API_KEY | LLM provider |
| scribe_db_url.txt | SCRIBE_DB_URL | Scribe logging DB |
| store_hmac_key.txt | SCRIBE_OBJECT_STORE_KEY | CortaStore verification |

**Location:** `/opt/council_mcp/secrets/*.txt` (manual creation, NOT in git)

**Loading Flow:** `docker-entrypoint.sh` (lines 45-88) reads each secret file and exports as env var.

**Confidence: HIGH**

---

### Finding 3: Multi-Stage Dockerfile

**Location:** `deploy/Dockerfile` lines 1-198

**Three Stages:**
1. **base:** System deps + PyPI packages (cached), local packages (rebuilds on code change)
2. **daemon:** MCP server, health check (TCP), CMD: `council start --foreground --no-web`
3. **web:** FastAPI app, health check (HTTP /login), CMD: `python -m council_mcp.web.app`

**Layer Caching Strategy:**
- Layer 1 (cached): PyPI deps from pyproject.toml (stays until pyproject.toml changes)
- Layer 2 (rebuilt): agentkit wheel + council_mcp source code

**Build Speed:** Code-only changes rebuild in ~5s (layer 2), full rebuild ~40s (including PyPI).

**Confidence: HIGH**

---

### Finding 4: Auto-Bootstrap on First Run

**Location:** `deploy/docker-entrypoint.sh` lines 91-148

**Process:**
1. Check if `schema_migrations` table exists
2. If not found → first run detected
3. Run: `agentkit init --auto --root /app --force --no-copy-extensions`
4. Creates roles, installs pgvector, runs migrations

**Web Container Skips:** Line 257 sets `AGENTKIT_SKIP_AUTO_BOOTSTRAP=1` to prevent race conditions.

**Confidence: HIGH**

---

### Finding 5: .dockerignore and Build Context

**Location:** `.dockerignore` lines 1-87, `Dockerfile` lines 28-31

**Excluded:**
- `.git/` (large history)
- `tests/` (not needed in prod)
- `.env`, `secrets/` (security)
- `deploy/` except `docker-entrypoint.sh`

**Included:**
- `.council/` (agent roster, templates)
- `src/`, `vendor/` (app code)

**Impact:** ~50MB upload vs ~500MB (10x faster build).

**Confidence: HIGH**

---

### Finding 6: Volume Management

**Location:** `deploy/docker-compose.yaml` lines 447-473

**3 External Volumes:**
| Name | Path | Purpose |
|------|------|---------|
| deploy_pg_data | /var/lib/postgresql/data | Database persistence |
| deploy_scribe_data | /app/.scribe | Logs, projects, docs |
| deploy_corta_store_data | /data | Objects + refs |

**Protection:** Marked `external: true` — `docker compose down -v` cannot delete them (safety feature).

**Pre-Creation:** setup-hetzner.sh lines 235-237 creates volumes before stack starts.

**Confidence: HIGH**

---

### Finding 7: Manual Deploy Workflow

**Location:** `deploy/scripts/setup-hetzner.sh` lines 67-335

**Steps:**
1. Clone from GitHub
2. Validate secrets exist
3. Pull base images
4. Create backup (if postgres running)
5. Build images
6. Detect Tailscale IP → write to .env
7. Create volumes
8. Start stack
9. Wait for postgres health
10. Verify services running

**Pain Points:**
- No git tag/release workflow (always pulls master)
- Secrets manual
- No automated pre-flight checks
- No health verification beyond container status
- Ad-hoc backup
- No audit trail
- Manual rollback (git checkout + rebuild)

**Confidence: HIGH**

---

### Finding 8: Backup and Disaster Recovery

**Location:** `deploy/scripts/backup-postgres.sh` lines 1-188

**Backup Process:**
- Location: `/opt/council_mcp/backups/agentkit-YYYYMMDD-HHMMSS.sql.gz`
- Command: `pg_dump` with `--clean --if-exists --create`
- Verification: `gunzip -t` integrity test
- Rotation: 7-day retention (auto-delete older)

**Restore (5 steps):**
1. Stop services
2. Start postgres only
3. Drop + recreate database
4. Restore from gunzip
5. Restart stack

**Current State:** No automated backup scheduling (manual or cron only).

**Confidence: HIGH**

---

## CURRENT PAIN POINTS

### P1: No CI/CD Pipeline
- Manual SSH + commands for deploy
- No automated testing before deploy
- No audit trail
- No secret rotation automation

### P2: Secrets Manual Management
- Stored as plain files on server
- No encryption at rest
- No versioning
- Manual rotation required

### P3: Single Point of Failure
- All services on one Hetzner CCX23
- No database replication
- No load balancing
- No failover mechanism

### P4: Incomplete Gitignore-Based File Sync
- Some files (.env, secrets/) must not be in git
- Operator manually creates/updates
- Error-prone (missing secrets prevent startup)
- No template validation

### P5: Ad-Hoc Backup Rotation
- Manual scheduling
- No offsite backup
- No backup verification beyond gunzip -t
- 7-day window limited

### P6: Limited Observability
- Logs scattered in docker volumes
- No centralized logging
- No metrics (CPU/memory/disk)
- No alerts

---

## WHAT NEEDS TO CHANGE FOR CI/CD

### Change 1: GitHub Actions Workflow
Add `.github/workflows/deploy.yml` to trigger on push:
- Lint, test, build Docker images
- Push to registry (GHCR or Docker Hub)
- Deploy to Hetzner via SSH
- Verify health checks

### Change 2: Secrets Management
Replace plain files with GitHub Secrets:
- Store `POSTGRES_PASSWORD`, `API_KEY` as secrets
- Pass via environment during deployment
- Consider HashiCorp Vault for future

### Change 3: Docker Image Registry
Add GHCR or Docker Hub:
- Push daemon:latest, web:latest, scribe:latest
- Version control via tags
- No build on Hetzner server

### Change 4: Deployment Strategy
Replace manual git pull + build:
- Pull pre-built images
- `docker compose pull && docker compose up -d`
- Health check waits for services healthy

### Change 5: Gitignore-Safe File Generation
Script to generate `.env` and `secrets/*.txt` from GitHub Secrets:
- Validate format before deployment
- Store in deployment logs (redacted)

### Change 6: Database Migrations
Ensure reliable `agentkit init --auto`:
- Test migrations in GitHub Actions
- Backup before deploying schema changes
- Verify database health before app startup

### Change 7: Post-Deploy Health Verification
Auto-rollback on failure:
- Wait for all services healthy
- Ports responsive
- On failure: rollback to previous image
- Alert operator

### Change 8: Multi-Server / HA (Future)
Postgres replication + Ray workers:
- Multiple Hetzner instances
- HAProxy or Tailscale-based LB
- Auto-failover

---

## ARCHITECTURE SUMMARY

| Component | Current | Status |
|-----------|---------|--------|
| Hosting | Hetzner CCX23 (single) | Functional |
| Containerization | Docker Compose (5 services) | Functional |
| Database | PostgreSQL + pgvector (single) | Functional |
| Secrets | Docker files (manual) | Functional, not secure |
| Build | Multi-stage Dockerfile (fast) | Functional |
| Deployment | Shell script (manual) | Functional, not automated |
| Backup | pg_dump + 7-day rotation | Functional, manual |
| CI/CD | None | **MISSING — blocking GitHub Actions integration** |
| Monitoring | Container logs (manual) | Functional, not centralized |
| Scaling | None (placeholder Ray) | Not implemented |

---

## RECOMMENDATIONS FOR BLUEPRINT

Design:
1. GitHub Actions CI/CD pipeline
2. Docker image registry (GHCR)
3. Secrets management (GitHub Secrets → environment)
4. Deployment automation (image pull → health check)
5. Multi-server foundation (database replication, Ray worker registry)
6. Monitoring integration (centralized logs, metrics, alerts)
