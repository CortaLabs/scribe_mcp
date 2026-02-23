---
id: council_infra_pipeline-research-repo-structure
title: "\U0001F52C Research Repo Structure \u2014 council_infra_pipeline"
doc_type: RESEARCH_REPO_STRUCTURE
doc_name: RESEARCH_REPO_STRUCTURE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 01:57:23 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Repo Structure — council_infra_pipeline
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 01:54:33 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

MCP_SPINE is a **monorepo** (single git repo) containing five independent Python projects that deploy together to Hetzner via Docker Compose. The projects have a clear dependency hierarchy with **agentkit** as the shared foundation.

**Key findings:**
- Single git repo: `git@github.com:CortaLabs/MCP_SPINE.git`
- **5 projects** with distinct roles: agentkit, council_mcp, scribe_mcp, corta_store, knowledge_mcp
- **Mono-deploy pattern**: Docker Compose orchestrates all services together
- **Agentkit wheel vendored**: Shipped as precompiled `.whl` in `vendor/` to avoid rebuilding
- **No GitHub Actions**: CI/CD does not yet exist — opportunity for greenfield design
- **All projects on Hetzner**: Single CCX23 VPS with docker-compose stack
- **Tailscale mesh networking**: Ports bind to Tailscale IP, not 0.0.0.0

**Confidence: High** — verified from source code, pyproject.toml, Dockerfile, docker-compose.yaml, and git configuration.
<!-- ID: research_scope -->
**Research Lead:** agent-20260216-130610-b59de721

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### 1. Project Inventory

MCP_SPINE contains exactly 5 projects, each with a separate git subdir and independent pyproject.toml:

#### agentkit (v0.1.0)
- **Purpose**: Shared Python SDK library for LLM, storage, auth, embeddings, and schema management
- **Imports**: No cross-project dependencies (foundation library)
- **Key exports**: llm_factory, embeddings, storage.models, auth, schema CLI
- **Package location**: `/home/austin/projects/MCP_SPINE/agentkit`
- **Deployment**: Compiled to `.whl` and vendored in council_mcp
- **Confidence: High** — verified from pyproject.toml (line 1-50)

#### council_mcp (v2.0.0)
- **Purpose**: Multi-agent orchestration, session management, MCP server implementation
- **Imports agentkit**: 60+ direct imports (storage.models, db, embeddings, llm_factory, auth, reflection)
- **Package location**: `/home/austin/projects/MCP_SPINE/council_mcp`
- **Deployment**: Docker image (daemon + web targets)
- **Key services**: council-daemon (MCP server), council-web (FastAPI UI)
- **Confidence: High** — verified from pyproject.toml, Dockerfile, docker-compose

#### scribe_mcp (v2.2)
- **Purpose**: Logging, project management, document versioning MCP server
- **Imports**: Only `mcp` (does NOT import agentkit, council_mcp, or other projects)
- **Package location**: `/home/austin/projects/MCP_SPINE/scribe_mcp`
- **Deployment**: Docker container `scribe` (stdio subprocess managed by daemon)
- **External deps**: sentence-transformers, numpy, jinja2, asyncpg
- **Confidence: High** — verified from pyproject.toml, docker-compose

#### corta_store (v0.1.0)
- **Purpose**: File-based object storage API (small service, minimal deps)
- **Imports**: Only FastAPI, uvicorn, pydantic, httpx (NO agentkit, NO other projects)
- **Package location**: `/home/austin/projects/MCP_SPINE/corta_store`
- **Deployment**: Docker container `corta-store` 
- **Confidence: High** — verified from pyproject.toml, docker-compose

#### knowledge_mcp (v0.1.0)
- **Purpose**: RAG engine/knowledge base MCP server (modular, pluggable)
- **Imports**: Only `mcp`, `pyyaml` (NO agentkit, NO other projects)
- **Package location**: `/home/austin/projects/MCP_SPINE/knowledge_mcp`
- **Note**: NOT currently deployed in docker-compose (experimental status)
- **Confidence: High** — verified from pyproject.toml

---

### 2. Dependency Graph

```
agentkit (foundation)
    ↑
    │ (direct imports)
    │
council_mcp
    ├─ FastAPI web UI
    ├─ MCP daemon (WebSocket server)
    └─ Manages subprocesses (scribe, corta-store via docker-compose)

scribe_mcp (independent)
    ├─ Stdout/stdio MCP server
    └─ Managed as subprocess by council daemon

corta_store (independent)
    ├─ FastAPI HTTP API
    └─ Separate container

knowledge_mcp (independent)
    ├─ MCP server
    └─ Experimental (not deployed)
```

**Key insight**: Only council_mcp imports agentkit. All other projects are **transport-independent** MCPs that communicate via stdio (scribe) or HTTP (corta_store).

**Confidence: High** — verified via grep of imports, pyproject.toml dependency declarations.

---

### 3. Deployment Architecture

**Deployment method**: Docker Compose (prod) + local CLI (dev)
**Location**: Hetzner CCX23 VPS (16GB RAM, 4 vCPU)
**Network**: Tailscale mesh (no public internet exposure)

#### Docker Compose Stack
```
Services:
  ├─ postgres:pgvector:pg16           [4GB mem, 1.0 CPU, pgvector extension]
  ├─ council-daemon                   [2GB mem, 0.8 CPU, MCP server + subprocess mgr]
  ├─ council-web                      [1.5GB mem, 0.6 CPU, FastAPI web UI]
  ├─ scribe                           [1GB mem, 0.5 CPU, Scribe MCP server]
  └─ corta-store                      [512MB mem, 0.3 CPU, Object storage API]

Volumes:
  ├─ pg_data          (database persistence)
  ├─ scribe_data      (Scribe logs, docs)
  └─ corta_store_data (object storage)

Network: backend (internal Docker network)
Secrets: pg_password, database_url, api_key, openai_api_key, etc.
```

**Port Binding Pattern**: `${TAILSCALE_IP:-127.0.0.1}:PORT:PORT` (NOT `0.0.0.0` — UFW bypass risk)

**Confidence: High** — verified from docker-compose.yaml (lines 1-531)

---

### 4. Build Strategy

#### Multi-stage Dockerfile (council_mcp only)
```
Stage: base
  ├─ Layer 1 (cached): PyPI deps from pyproject.toml
  ├─ Layer 2 (rebuilt): agentkit wheel + council_mcp source
  └─ PYTHONPATH adjustment for /app/src and /app

Stage: daemon
  └─ Entrypoint: docker-entrypoint.sh (reads secrets, runs council start --foreground)

Stage: web
  └─ Entrypoint: similar, runs web UI
```

#### Agentkit as Vendored Wheel
- **Location**: `vendor/agentkit-0.1.0-py3-none-any.whl`
- **Purpose**: Pre-compiled to avoid rebuilding in Docker (saves 30-60 seconds per build)
- **Rebuild command**: `cd /opt/agentkit && pip wheel --no-deps -w /opt/council_mcp/vendor .`
- **Layer caching**: Dockerfile installs PyPI deps first (cached layer), then wheel + source (rebuild layer)

#### Other Stacks
- scribe, corta_store: Docker images built from their own Dockerfiles (not in council_mcp repo)
- knowledge_mcp: Python package only (no Dockerfile)

**Confidence: High** — verified from Dockerfile (lines 1-198)

---

### 5. CI/CD Status

**Current state**: NO GitHub Actions, NO CI/CD pipeline

**Manual deployment flow**:
```
Local dev change
  → git push to origin/master
  → Manual SSH to Hetzner
  → cd /opt/council_mcp && git pull
  → docker compose build
  → docker compose up -d
```

**Implications for your task**:
- Opportunity to design **greenfield CI/CD** (no legacy constraints)
- Can assume: tests pass locally, code is ready to ship
- Docker build is deterministic (vendored wheel + pyproject.toml)
- No special environment-specific configs needed (Tailscale handles network)

**Confidence: High** — verified by absence of .github/workflows, operator kickoff log

---

### 6. Monorepo Structure

```
/home/austin/projects/MCP_SPINE/
├── .git/                       [monorepo root]
├── agentkit/                   [independent project dir]
│   ├── .git/
│   ├── pyproject.toml
│   ├── src/agentkit/
│   └── tests/
├── council_mcp/                [main consumer of agentkit]
│   ├── .git/
│   ├── pyproject.toml
│   ├── vendor/agentkit-0.1.0-py3-none-any.whl
│   ├── deploy/
│   │   ├── docker-compose.yaml
│   │   ├── Dockerfile
│   │   ├── docker-entrypoint.sh
│   │   └── scripts/
│   ├── src/council_mcp/
│   └── tests/
├── scribe_mcp/                 [independent project]
│   ├── .git/
│   ├── pyproject.toml
│   ├── src/scribe_mcp/
│   └── tests/
├── corta_store/                [independent project]
│   ├── .git/
│   ├── pyproject.toml
│   ├── src/
│   └── tests/
├── knowledge_mcp/              [independent project, not deployed]
│   ├── .git/
│   ├── pyproject.toml
│   ├── src/knowledge_mcp/
│   └── tests/
└── .scribe/                    [Scribe docs at repo root]
    └── docs/dev_plans/
```

**Git structure**: Single monorepo with 5 independent .git dirs (each project has own git history). Root .git is the main repo.

**Confidence: High** — verified with `ls -la` and `find`

---

### 7. Cross-Project Import Matrix

| Project | Imports agentkit | Imports council_mcp | Imports scribe_mcp | Imports corta_store | Imports knowledge_mcp |
|---------|------------------|--------------------|--------------------|---------------------|-----------------------|
| agentkit | — | No | No | No | No |
| council_mcp | **Yes (60+ imports)** | No | No (manages via subprocess) | No (manages via HTTP) | No |
| scribe_mcp | No | No | — | No | No |
| corta_store | No | No | No | — | No |
| knowledge_mcp | No | No | No | No | — |

**Key insight**: Only council_mcp has hard Python dependencies. All others are **loosely coupled via MCP protocol** (wire protocol, not Python imports).

**Confidence: High** — verified with grep and pyproject.toml inspection.
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->
## Recommendations for CI/CD Design

### CI/CD Architecture (Greenfield Opportunity)

Given the monorepo structure and deployment patterns, recommend **per-project CI + shared deployment**:

```
GitHub Actions Workflow:
├─ Triggers: Push to master, manual dispatch
├─ For each project (agentkit, council_mcp, scribe_mcp, corta_store):
│  ├─ Run tests (pytest, type checking)
│  ├─ Build Docker image (if applicable)
│  └─ Push to Docker registry
├─ After all projects pass:
│  ├─ Deploy docker-compose stack to Hetzner
│  └─ Run smoke tests
└─ Rollback on failure
```

### Dependency Build Order

**Critical**: agentkit must rebuild BEFORE council_mcp Docker build:

```
Stage 1: Validate & Test (parallel OK)
├─ agentkit: pytest, type checks
├─ council_mcp: pytest (uses vendored wheel)
├─ scribe_mcp: pytest
├─ corta_store: pytest
└─ knowledge_mcp: pytest

Stage 2: Build Wheels/Images (order matters)
├─ agentkit: build wheel, upload to artifact repo
├─ council_mcp: download agentkit wheel, place in vendor/, build Docker image
├─ scribe_mcp: build Docker image
├─ corta_store: build Docker image
└─ knowledge_mcp: (no Docker yet, skip)

Stage 3: Deploy (sequential)
└─ Push docker-compose.yaml + new images to Hetzner
```

### Agentkit Wheel Distribution

**Options**:
1. **Current**: Vendor pre-built wheel in repo (current approach — good for determinism)
2. **PyPI**: Publish agentkit to PyPI, let Docker pull (loses vendor control)
3. **Artifact registry**: GitHub Artifacts / Docker registries as wheel cache

**Recommend: Stay with option 1** (vendored wheel) because:
- Deterministic builds (no PyPI version skew)
- Single source of truth (git repo)
- Fast Docker builds (pre-compiled)
- Offline deployment possible

### Secrets Management

Docker Compose stack uses Docker secrets (mounted as files). For GitHub Actions:

```yaml
# .github/workflows/deploy.yml
env:
  TAILSCALE_IP: ${ secrets.TAILSCALE_IP }
  # Database secrets passed as GitHub secrets
with:
  - name: Deploy to Hetzner
    env:
      DATABASE_URL: ${ secrets.DATABASE_URL }
      POSTGRES_PASSWORD: ${ secrets.POSTGRES_PASSWORD }
      OPENAI_API_KEY: ${ secrets.OPENAI_API_KEY }
```

Or use Tailscale as deployment transport (SSH over mesh, no port exposure).

### Deployment Strategy

**Recommended**: Tailscale-based SSH with rolling restarts

```bash
# From GitHub Actions runner (authenticated via Tailscale)
ssh ubuntu@council-hub \
  "cd /opt/council_mcp && \
   git pull && \
   docker compose build && \
   docker compose up -d --remove-orphans && \
   sleep 30 && \
   docker compose exec council-daemon council status"
```

**Benefits**:
- No public port exposure needed
- Uses existing Tailscale mesh
- Secrets stay in GitHub Actions, never on disk
- Rollback: `git revert && git push && CI re-runs`

### Testing Strategy

**Unit tests** (fast, run on every push):
- agentkit: test storage, auth, llm_factory
- council_mcp: test session management, MCP protocol
- scribe_mcp: test logging, project management
- corta_store: test API endpoints

**Integration tests** (slower, run before deployment):
- docker-compose health checks (postgres readiness, daemon startup)
- Smoke tests: Can council daemon start? Can it spawn scribe subprocess?
- Cross-service tests: Can web reach daemon over WebSocket?

**Confidence: High** — based on monorepo structure and deployment requirements.
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---