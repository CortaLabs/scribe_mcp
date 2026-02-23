---
id: council_downstream_cicd-research-downstream-cicd-flow-20260217
title: "\U0001F52C Research Downstream Cicd Flow 20260217 \u2014 council_downstream_cicd"
doc_type: RESEARCH_DOWNSTREAM_CICD_FLOW_20260217
doc_name: RESEARCH_DOWNSTREAM_CICD_FLOW_20260217
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 09:08:36 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Downstream Cicd Flow 20260217 — council_downstream_cicd
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 09:07:15 UTC

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
**Research Lead:** atlas

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] downstream_registration
- [ ] ci_cd_workflow
- [ ] repo_management
- [ ] multi_council_deployment
- [ ] custom_pages_integration


**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### 1. Hub Platform CI/CD Workflow (platform.yml)

**File:** `.github/workflows/platform.yml` (184 lines)

The primary platform workflow runs 3 sequential jobs on push to master:

1. **Test Job** — Runs fast pytest subset on ubuntu-latest
   - Python 3.12, cached pip deps
   - Tests: `test_package_structure.py`, `test_config_validation.py`, `test_portable_config.py`
   - Purpose: Catch regressions before expensive Docker builds
   - **Confidence: HIGH** — Implementation verified

2. **Build Job** — Builds daemon and web Docker images, pushes to GHCR
   - Uses docker/build-push-action@v5 with BuildKit layer caching
   - Images tagged with `github.sha` (commit) and `latest`
   - Registry: `ghcr.io/cortalabs/mcp_spine/<service>:<tag>`
   - Cache reference: `buildcache` tag for layer reuse
   - **Confidence: HIGH** — Implementation verified

3. **Deploy Job** — Deploys to Hetzner via Tailscale SSH
   - Connects to Tailscale as ephemeral node (tag:ci)
   - SSH to `deploy@council-hub` (hardcoded hostname)
   - Steps:
     * `git pull` on 3 repos (`council_mcp`, `scribe_mcp`, `corta_store`)
     * `docker login` to GHCR on server
     * Runs `/opt/council_mcp/deploy/scripts/deploy.sh` with secrets as env vars
   - Secrets passed: PG_PASSWORD, DATABASE_URL, COUNCIL_API_KEY, OPENAI_API_KEY, SCRIBE_DB_URL, STORE_HMAC_KEY, IMAGE_TAG
   - **Confidence: HIGH** — Implementation verified

**Key Insight:** Deploy job uses hardcoded `council-hub` hostname. For downstream repos, would need either:
- New GitHub org-level workflow that targets different hostnames
- Hub-based webhook receiver that triggers downstream CI/CD when upstream deploys
- Manual `council repo sync` CLI command

**File:** `/home/austin/projects/MCP_SPINE/council_mcp/.github/workflows/platform.yml` (Lines 1-184)

---

### 2. Downstream Council Registration System

**Files:** 
- `src/council_mcp/cli/init_cmd.py` (969 lines)
- `src/council_mcp/storage/registry.py` (419 lines)

#### Registration Flow

`council init --parent <parent_name>` scaffolds a downstream council:

1. **Parameter:** `--parent` flag accepts parent council name (e.g., `council-main`)

2. **Scaffolding** (`scaffold_council()`, lines 600-720):
   - Creates `.council/` with full config, roster, templates
   - Calls `_build_council_yaml(parent=...)` to set:
     * `council.parent_council_name = parent`
     * `council.deployment.mode = "remote"`
     * `council.compute.ray_enabled = False` (downstream doesn't run Ray head)
     * `council.compute.ray_address = "hub_tailscale_ip:6379"` (if hub IP known)

3. **Environment Setup** (`_build_downstream_env_example()`, lines 438-483):
   - Generates `.env.example` with connection string placeholders
   - No docker-compose for downstream (uses shared hub infrastructure)

4. **Registration with Hub** (`register_council()`, lines 70-113):
   - Makes HTTP POST to `/api/councils/register` on hub web server
   - Payload: `{ path, name, parent, preset }`
   - Hub validates API key via `X-API-Key` header
   - Returns: `{ council: { id: uuid, ... } }`

5. **Database Update** (`register_council_sync()`, lines 46-79):
   - Inserts into `council.councils(name, repo_path, parent_council_id)`
   - Looks up parent by name, gets parent_id
   - Upsert logic: ON CONFLICT (name) DO UPDATE
   - Returns council_id (UUID)

6. **Council ID Storage** (`write_council_id()`, lines 116-142):
   - Writes council_id into `.council/council.yaml` under `council.council_id`
   - Persists for future CLI operations

#### Key Insight: Hierarchy Support

The registry stores:
- `council_id` (UUID) — unique identifier
- `parent_council_id` (UUID) — reference to parent
- `name` (string) — human-readable, unique
- `repo_path` (string) — filesystem path on hub

Hierarchy is **flat:** downstream can reference parent, but no grandparent chains yet.

**Confidence: HIGH** — Code verified, registration contract clear

---

### 3. Secrets & Environment Management

**File:** `deploy/scripts/deploy.sh` (208 lines)

The deploy script manages secrets via Docker secrets pattern:

1. **Secret Files** (lines 75):
   - Stored at `/opt/council_mcp/secrets/<name>.txt`
   - Each secret is a single-line file

2. **Environment Variable Mapping**:
   - `PG_PASSWORD` → `/opt/council_mcp/secrets/pg_password.txt`
   - `DATABASE_URL` → `/opt/council_mcp/secrets/database_url.txt`
   - `COUNCIL_API_KEY` → `/opt/council_mcp/secrets/api_key.txt`
   - `OPENAI_API_KEY` → `/opt/council_mcp/secrets/openai_api_key.txt`
   - `SCRIBE_DB_URL` → `/opt/council_mcp/secrets/scribe_db_url.txt`
   - `STORE_HMAC_KEY` → `/opt/council_mcp/secrets/store_hmac_key.txt`

3. **Overwrite Logic**:
   - If env var is set, write it to the secrets file
   - If not set, preserve existing file (allows manual deploys to skip rotation)

4. **Health Checks** (referenced in deploy.sh):
   - Runs `./deploy/scripts/health-check.sh` after containers up
   - Verifies: postgres, council-daemon, council-web, scribe, corta-store
   - Timeout: configurable per service
   - On failure: runs `./deploy/scripts/rollback.sh` to previous image tag

**Confidence: HIGH** — Deploy script verified

---

### 4. Multi-Repo Deployment Pattern

The current CI/CD assumes 3 repos all live under `/opt/`:

```
/opt/council_mcp/
/opt/scribe_mcp/
/opt/corta_store/
```

All three `git pull` on each deploy (platform.yml, lines 161-166):

```bash
ssh -i ~/.ssh/deploy_key deploy@council-hub \
  "cd /opt/council_mcp && git pull && \
   cd /opt/scribe_mcp && git pull && \
   cd /opt/corta_store && git pull"
```

**Key Insight:** No per-repo triggering yet. All repos must be in git pull + docker-compose.yaml simultaneously.

For downstream repos (e.g., rom-lab, osrs_hiscore_pull), the pattern would be:

Option A: **Webhook from downstream repos**
- Each downstream repo's `.github/workflows/` sends webhook to hub
- Hub receiver script: `curl https://council-hub:8016/api/webhooks/repo-sync --data '{"repo": "rom-lab"}'`
- Hub script does: `cd /opt/rom-lab && git pull`
- No rebuild needed (downstream runs on hub's daemon + web)

Option B: **Cron job on hub**
- Hub runs periodic `git pull` on all registered downstream repos
- E.g., `0 * * * * cd /opt/rom-lab && git pull && council update`

Option C: **Manual CLI command**
- `council repo sync <repo_name>` or `council repo pull <repo_url>`
- Operator runs on hub after downstream repo is ready

**Current State:** No repo management CLI exists. Need to implement.

**Confidence: MEDIUM** — Pattern identified but CLI not yet built

---

### 5. Downstream Repo Filesystem Layout

Downstream repos are **not Docker containers**. They're checked out as directories on Hetzner:

```
/opt/rom-lab/                           # Checked out from GitHub
├── .council/                           # Council config (from init --parent)
│   ├── council.yaml                    # parent_council_name: council-main
│   ├── roster.yaml                     # Custom agents for rom-lab
│   ├── .env                            # DATABASE_URL (shared hub Postgres)
│   └── ...
├── .mcp.json                           # MCP servers for this council
├── .github/                            # Own CI/CD workflows (optional)
│   └── workflows/
│       └── deploy.yml                  # Triggers hub webhook on push
└── src/                                # Application code
```

**Key:** Downstream repos share the **same Postgres database** and **same daemon/web processes** as the hub. They don't get their own containers; they get their own `.council/` directory and custom pages served from their filesystem.

**Confidence: HIGH** — Inferred from init_cmd.py parent logic

---

### 6. Custom Pages Integration (Open Issue)

From ARCHITECTURE_GUIDE.md and project context, custom pages are served from `.council/web/pages/`:

- Template loader discovers `.council/web/pages/*.html.j2` files
- Rendered on-the-fly when navigating to `/pages/<name>`
- Requires **filesystem access** to downstream repo

**Current Problem:** The `council-web` container runs in Docker. It has no direct access to `/opt/rom-lab/.council/web/pages/`. 

**Possible Solutions:**

1. **Volume mounts in docker-compose:**
   ```yaml
   services:
     council-web:
       volumes:
         - /opt/rom-lab/.council/web/pages:/app/.council/web/pages_rom_lab
   ```
   - Breaks multi-council support (each council needs its own volume)

2. **Project loader sync before rendering:**
   - Web process mounts `/opt` as shared volume
   - Template loader reads from `/opt/<council_name>/.council/web/pages/`
   - **Preferred approach** — stateless, works for any downstream repo

3. **Symlink approach:**
   - Create symlinks from hub cache to downstream repo dirs
   - Risky if downstream repos move or get deleted

**Confidence: LOW** — Custom pages path issue needs verification with actual deployment

---

### 7. Missing Patterns & Gaps

| Item | Current State | Needed For |
|------|---------------|-----------|
| **`council repo` CLI group** | ❌ Does not exist | Managing downstream repos on hub |
| **Repo webhook receiver** | ❌ Not implemented | Auto-sync from downstream pushes |
| **Multi-council volume mounting** | ❌ Hardcoded paths | Custom pages serving downstream |
| **Downstream repo cleanup** | ❌ No policy | Deleting councils from hub |
| **Downstream CI/CD trigger** | ❌ Unknown entry point | How downstream repos trigger hub updates |
| **Postgres schema per-council** | ✅ Exists (`council_<slug>`) | Council data isolation |
| **Authority model** | ✅ Exists (parent/child UUID refs) | Hierarchy enforcement |

**Confidence: MEDIUM** — Gaps identified but require user/downstream repo validation

---

### 8. Downstream Council Workflow (Proposed)

This is how a downstream repo operator would onboard onto Hetzner:

1. **On dev PC:**
   ```bash
   git init rom-lab
   cd rom-lab
   council init --name rom-lab --parent council-main --auto-register --api-key $KEY --web-url http://council-hub:8015
   git add .council/
   git commit -m "feat: init downstream council"
   git push origin master
   ```

2. **On Hetzner (hub):**
   - Hub receives git push notification (or operator runs `council repo add` manually)
   - Hub: `cd /opt && git clone https://github.com/user/rom-lab.git`
   - Hub: `council update` to pick up rom-lab in registry
   - Rom-lab council is now registered, custom pages discoverable

3. **In Web UI:**
   - Council dropdown shows both "Council MCP" and "rom-lab"
   - Clicking "rom-lab" loads rom-lab's custom pages from `/opt/rom-lab/.council/web/pages/`

4. **Downstream developer pushes new custom page:**
   - Adds `.council/web/pages/monitoring.html.j2`
   - Pushes to GitHub
   - Hub receives webhook → `cd /opt/rom-lab && git pull`
   - Next time user navigates to `/pages/monitoring`, new page is served

**Confidence: MEDIUM** — Workflow is logical but requires validation with actual implementation

---
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
## Recommendations

### For Implementing Downstream CI/CD Support

**Priority 1 (Critical for MVP):**

1. **Implement `council repo` CLI group** with 4 commands:
   - `council repo add <url>` — Clone downstream repo from GitHub to `/opt/<name>`
   - `council repo list` — Show all registered downstream repos with status
   - `council repo sync <name>` — Manual git pull + council update for a downstream repo
   - `council repo remove <name>` — Cleanup (archive or delete) a downstream repo from hub

   **Location:** New file `src/council_mcp/cli/repo_cmd.py`
   **Implementation guide:**
   - Parse GitHub URL to extract owner/repo
   - Clone to `/opt/<repo-name>`
   - Register in `council.councils` with parent_council_id = hub's ID
   - Store repo metadata (GitHub URL, branch, last_sync_at) in council.metadata JSONB

2. **Add `/api/webhooks/repo-sync` endpoint** for GitHub Actions integration:
   - Receives POST from downstream repo's `.github/workflows/` on master push
   - Validates API key via header
   - Queues async git pull + council update for that downstream repo
   - Returns 202 Accepted immediately (don't block GitHub Actions)

   **Location:** `src/council_mcp/web/routes/webhooks.py` (new file)
   **GitHub Actions template:** Provide `.github/workflows/hub-sync.yml` in `council init --parent` output

**Priority 2 (Nice-to-have):**

3. **Mount `/opt` as read-only volume in council-web container** for custom pages discovery:
   - Allows template loader to read from `/opt/<council_name>/.council/web/pages/`
   - Update docker-compose.yaml:
     ```yaml
     council-web:
       volumes:
         - /opt:/opt_readonly:ro
     ```
   - Template loader: `read_from_path = f"/opt_readonly/{active_council_name}/.council/web/pages/..."`

4. **Add `council repo cron` daemon** for periodic sync (alternative to webhooks):
   - Runs every hour: iterate registered downstream repos, git pull + council update
   - Useful for air-gapped or webhook-restricted deployments
   - Config: `council.deployment.downstream_sync_enabled`, `downstream_sync_interval_minutes`

**Priority 3 (Future):**

5. **Implement grandparent chains** (optional multi-level hierarchy):
   - Allow downstream repos to themselves have children
   - E.g., council-main > rom-lab > rom-lab-testing
   - Currently: registry supports `parent_council_id`, just need recursive queries

6. **Per-council authentication** for downstream repos:
   - Generate unique API key per downstream council (not shared hub key)
   - Scope webhook requests to only affect that council's data
   - Requires: API key table with `council_id` foreign key

---

### Questions for Operator/User

Before implementation, clarify:

1. **Deployment strategy for downstream repos:**
   - Do we prefer webhooks (auto on push) or cron (periodic polling)?
   - Should hub automatically sync all downstream repos, or require manual `council repo sync`?

2. **Custom pages for downstream councils:**
   - Must custom pages be editable in web UI, or read-only from filesystem?
   - Should downstream repos be able to override hub's custom pages (e.g., `/pages/admin`)?

3. **Secrets & environment per-council:**
   - Do downstream repos get their own `.env` files, or share hub's secrets?
   - If their own: how are they managed? (via web UI, git, or manual)?

4. **Authority model:**
   - Can a downstream council create its own downstream councils (grandchildren)?
   - Can downstream repos push changes back to hub's infrastructure?

5. **CI/CD triggering from downstream repos:**
   - When rom-lab pushes to GitHub, should it trigger hub's Docker rebuild?
   - Or should downstream repos trigger only filesystem sync (no Docker rebuild)?

---
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---
## References & Appendix

### Key Files Investigated

| File | Lines | Purpose | Confidence |
|------|-------|---------|------------|
| `.github/workflows/platform.yml` | 184 | Hub CI/CD workflow (test→build→deploy) | HIGH |
| `src/council_mcp/cli/init_cmd.py` | 969 | Council initialization, downstream registration | HIGH |
| `src/council_mcp/storage/registry.py` | 419 | Council registry, hierarchy tracking | HIGH |
| `deploy/scripts/deploy.sh` | 208 | Deployment orchestration, health checks | HIGH |
| `.scribe/docs/dev_plans/council_downstream_cicd/ARCHITECTURE_GUIDE.md` | 127 | Project context | MEDIUM |

### Code Locations (Absolute Paths)

- **Hub CI/CD:** `/home/austin/projects/MCP_SPINE/council_mcp/.github/workflows/platform.yml`
- **Init command:** `/home/austin/projects/MCP_SPINE/council_mcp/src/council_mcp/cli/init_cmd.py`
- **Registry:** `/home/austin/projects/MCP_SPINE/council_mcp/src/council_mcp/storage/registry.py`
- **Deploy orchestration:** `/home/austin/projects/MCP_SPINE/council_mcp/deploy/scripts/deploy.sh`

### Key Classes & Functions

**init_cmd.py:**
- `scaffold_council()` (lines 600-720) — Main scaffolding entry point
- `_build_council_yaml()` (lines 386-435) — Generates council.yaml with parent config
- `_build_downstream_env_example()` (lines 438-483) — Env setup for downstream
- `register_council()` (lines 70-113) — HTTP registration with hub
- `validate_api_key()` (lines 27-67) — API key validation against hub
- `init()` (lines 760-969) — Main CLI command handler

**registry.py:**
- `register_council_sync()` (lines 46-79) — Register or upsert council in DB
- `list_councils_sync()` (lines 91-100) — List all councils
- `get_council_by_name_sync()` (lines 103-111) — Lookup by name
- `get_hierarchy_sync()` (lines 246-285) — Fetch full hierarchy tree

### Database Schema (Relevant)

```sql
-- From council.councils table
CREATE TABLE council.councils (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    parent_council_id UUID REFERENCES council.councils(id),
    repo_path TEXT,
    status TEXT DEFAULT 'active',
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW()
);

-- Deployed schema per-council
CREATE SCHEMA council_<slug>;  -- e.g., council_rom_lab
```

### GitHub Actions Secrets (Required for Hub Deploy)

- `TAILSCALE_OAUTH_CLIENT_ID` — Ephemeral node connection
- `TAILSCALE_OAUTH_SECRET` — Ephemeral node secret
- `DEPLOY_SSH_KEY` — SSH key for deploy@council-hub
- `PROD_PG_PASSWORD` — Postgres superuser password
- `PROD_DATABASE_URL` — Connection string
- `PROD_COUNCIL_API_KEY` — Web UI auth (ck_...)
- `PROD_OPENAI_API_KEY` — LLM provider key
- `PROD_SCRIBE_DB_URL` — Scribe DB connection
- `PROD_STORE_HMAC_KEY` — CortaStore signing secret

### Follow-Up Questions for Operator

1. **Do you want automatic sync of downstream repos via webhooks, or manual `council repo sync` commands?**
   - Webhooks = automatic, more overhead on hub
   - Manual = operator-controlled, simpler infrastructure

2. **Should downstream repo changes trigger hub's Docker rebuild, or just filesystem sync?**
   - If just filesystem: no docker-compose update needed
   - If Docker rebuild: need new CI/CD workflow on downstream repos

3. **How should custom pages from downstream repos be served?**
   - Via volume mount (requires docker-compose changes per-council)?
   - Via API endpoint that reads from `/opt/<council_name>`?
   - Via symlinks (simpler but fragile)?

4. **Should downstream repos share secrets with the hub, or have their own?**
   - Shared: simpler, but less isolation
   - Own: requires separate `.env` files, per-council secret rotation

---
