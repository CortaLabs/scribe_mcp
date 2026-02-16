# AGENTS.md — Scribe Agent Contract (Base Template)

> **Scope:** This file is the canonical operating contract for *all* agents in this repo.
>
> **Two doc worlds:**
>
> * **`.scribe/docs/`** = managed workspace (dev plans, run artifacts, scratch research). Often hidden/gitignored.
> * **`/docs/`** = official curated documentation (only update when explicitly “promoting”). These **can** be managed with `manage_docs` when promotion is explicitly required.

---

## Required Reading

You must follow the Scribe MCP usage skill:

* **`$scribe-mcp-usage`** (tool usage policy + logging discipline)

If you haven’t internalized it, stop and request the skill text before proceeding.

---

## 🚨 Commandments (Critical Rules) — With Explanations

### MCP Tool Usage Policy (from `$scribe-mcp-usage`)

**Rule:**

* You have access to every tool exposed by the MCP server.
* If a tool exists (`append_entry`, `rotate_log`, etc.), **call it directly** via MCP—no manual scripting or substitutes.
* **Log intent only after** the tool call succeeds or fails.
* Confirmation flags (`confirm`, `dry_run`, etc.) must be passed as **actual tool parameters**.

**Why:** Tool calls are the auditable execution layer. If you “simulate” a tool with hand-written actions, the system can’t trust your output.

**How to comply:** Always use the MCP tool first, then append the log entry describing what happened.

**Read-file policy (auditability):** Any time you need repository file contents or metadata, you must use `read_file` (scan-only allowed) instead of manual/implicit reads.

**Search policy:** All multi-file content searches must use `search` (NOT grep, rg, find, or bash search commands). Supports regex, glob filtering, file type filtering, and multiple output modes.

**Edit-file policy:** File edits should use `edit_file` for auditable, safe string replacement. The tool enforces read-before-edit (file must be read via `read_file` first). Defaults to `dry_run=True` for safety.

---

### COMMANDMENT #0 — Always Check Progress Log First

**Sentinel Mode branch (no active project):** `read_recent` / `query_entries` operate on **global/sentinel scope**. Do **not** target a project `PROGRESS_LOG.md` path when no project is active.

**Rule:** Before starting *any* work, rehydrate from the progress log using `read_recent` and/or `query_entries`.

* Target: **`.scribe/docs/dev_plans/<current_project>/PROGRESS_LOG.md`**
* Minimum: read **last 5 entries**.
* For project context: read **first ~20 entries** (or more if needed).
* Do **not** open or dump the entire log unless explicitly required.

**Why:** The progress log is the source of truth for current context. Skipping it is how agents hallucinate priorities and break invariants.

**How to comply:** Start every session with `read_recent` (last 5). Use `query_entries` for targeted history.

---

### COMMANDMENT #0.5 — Infrastructure Primacy (Global Law)

**Rule:** You must work within the existing system. **Never** create parallel/replacement files to avoid integration (e.g., `enhanced_*`, `*_v2`, `*_new`).

**Why:** Replacement files create technical debt, split the code path, and destroy reliability. The goal is to improve the real system, not fork it.

**How to comply:** Edit, extend, or refactor the existing component directly. If the existing design blocks progress, escalate with a plan—don’t fork.

---

### COMMANDMENT #1 — Always Scribe (Append Entry for Everything Significant)

**Rule:** Always use `append_entry` to record every significant action/decision:

* investigations
* design decisions
* code changes
* test results
* bugs discovered
* plan updates

If it’s not Scribed, it didn’t happen.

**Why:** This is your audit trail and the only trustworthy chain of work.

**How to comply:** After each meaningful step, `append_entry` with **intent → action → result → next step**.

**Orchestrator add-on (Claude Code):** Always pass the current `project_name` to subagents so they don’t log to the wrong project.

---

### COMMANDMENT #2 — Reasoning Traces & Constraint Visibility

**Rule:** Every `append_entry` must include a `reasoning` block with:

* **why**: goal / decision point
* **what**: constraints / alternatives considered
* **how**: method / steps / remaining uncertainty

**Why:** This creates an auditable decision record and prevents shallow “looks good” work.

**How to comply:** If you can’t justify the decision with constraints and method, you’re not done.

**Review enforcement:** Missing `why/what/how` = reject. Weak constraint coverage = request clarification.

---

### COMMANDMENT #3 — No Replacement Files (Re-stated, Because Agents Cheat)

**Rule:** Don’t abandon working modules and drop in new files to “fix” things. Improve what exists.

**Why:** File forks are how systems become unmaintainable.

**How to comply:** Make surgical edits. Refactor only when required by the plan.

---

### COMMANDMENT #4 — Structure, Cleanliness, and Tests

**Rule:** Follow repo structure and best practices.

* Tests belong in `/tests` using the repo’s existing layout and naming.
* Don’t clutter the repo with random files.

**Why:** Consistency keeps the repo navigable and prevents “mystery behavior” from untracked changes.

**How to comply:** Mirror existing test patterns and module structure. When in doubt: search existing tests first.

---

### COMMANDMENT #5 — Complete the Integration

**Rule:** If you build new infrastructure (DB tables, classes, methods), you MUST wire it to production code in THE SAME implementation phase. Infrastructure that only exists in tests is NOT DONE.

**Why:** Unconnected infrastructure is dead code. It passes tests but doesn't ship.

**How to comply:** Every new class/method/table must have a call site in production code before the phase is complete.

---

### PROGRESS VETO RULE (Carl Authority)

**Rule:** If unresolved issues, missing tests, or unproven claims exist, **do not advance**.

* The only valid response is: **“no”** + the exact blockers.

**Why:** Momentum is not correctness.

**How to comply:** Stop, enumerate blockers, and fix them before moving forward.

---

## 🔁 Canonical Protocol Sequence

**1) Research → 2) Architect → 3) Review → 4) Code → 5) Review**

**Why:** This chain forces clarity before implementation and forces proof after implementation.

---

## Codex vs Claude Code Identity Rules

### Codex (ChatGPT Codex CLI)

* **Must always use agent name:** `Codex`

### Claude Code (Subagents)

Claude Code may use these role agents:

* `Review`
* `Architect`
* `Research`
* `BugHunter`
* `Coder`

**Runtime identity (unique):** `<Role>-<short_id>` (example: `Coder-4821`)

Orchestrator must pass `project_name` to every subagent.

---

## Sentinel Mode vs Project Mode

Scribe operates in **two mutually exclusive modes**:

### Project Mode (default)

* **Enter:** call `set_project(<project_name>)`.
* **Scope:** work is scoped to **`.scribe/docs/dev_plans/<project>/`** (progress log, doc artifacts, etc.).
* **Use for:** any structured work (research → plan → implement → test) tied to a dev plan.
* **Primary logging:** `append_entry`.

### Sentinel Mode (no active project)

* **Enter:** **do not** call `set_project()`.
* **Scope:** repository-wide governance and case tracking outside dev-plan boundaries (e.g., **`.scribe/sentinel/<YYYY-MM-DD>/`**).
* **Use for:** minor fixes, cross-project issues, repo-level auditing, security/bug cases that should not live inside one dev plan.
* **Primary logging:** `append_event`.

### Sentinel-only case tools (blocked in Project Mode by design)

* `open_bug` — open a repository-wide bug case
* `open_security` — open a repository-wide security case
* `link_fix` — attach fix artifacts (commit/PR/etc.) to a case

### Mode switching rule

* If a Sentinel task becomes non-trivial (multi-step change, refactor, new feature): **create a project** with `set_project()` and follow the New Project Workflow.
* If you need to open/link cases while a project is active: do it in a **separate Sentinel session** (or after exiting project context).

---

## 🚀 New Project Workflow (Mandatory)

When spinning up a new project:

1. Immediately call `set_project(<project_name>)`.
   - **Project names are automatically normalized**: "My-Project", "my_project", and "MY PROJECT" all resolve to "my_project"
   - Use descriptive names (hyphens/underscores/spaces all work)
2. Use `manage_docs` to draft/populate, in **`.scribe/docs/`**:

   * `ARCHITECTURE_GUIDE.md`
   * `PHASE_PLAN.md`
   * `CHECKLIST.md`
3. Keep these three docs consistent: architecture decisions must be reflected in phase/checklist, and phase/checklist changes must not contradict architecture.
4. Only after docs exist and are coherent may you begin feature code.
5. Continue using `append_entry` while drafting docs (docs and logs are both mandatory).

**Note:** `manage_docs` is for structured project documentation and artifacts.

* **AGENTS.md is edited by hand** (do not generate/maintain it via `manage_docs`).
* **New unified create syntax**: Use `manage_docs(action="create", doc_type="research|bug|review|agent_card|custom", ...)` instead of deprecated `create_research_doc`, `create_bug_report`, etc.

---

## Execution Loop (Every Task)

### 1) Rehydrate

* `read_recent` (last 5)
* `query_entries` as needed
* read the relevant dev plan section in `.scribe/docs/`

### 2) Execute

* smallest correct change
* add/adjust tests
* verify (tests/lint/typecheck as applicable)

### 3) Log + Update

* `append_entry` with outcome + next step
* update dev plan status/checklist if needed (in `.scribe/docs/`)
* promote to `/docs/` only when explicitly required

---

## Tooling Contract (Fill Repo-Specific Commands)

**Canonical Scribe tools (expected):**

* `set_project`
* `manage_docs`
* `append_entry` (Project)
* `append_event` (Sentinel)
* `read_file`
* `read_recent`
* `query_entries`

If available in this repo, you may also have:

* `rotate_log`
* `scribe_doctor`
* `open_bug` / `open_security` / `link_fix` (Sentinel-only; blocked in Project Mode by design)

### v2.1.1 Enhanced Tools

**`read_file(path, mode, include_dependencies)`** - Repo-scoped file access with governance features:
- **AST structure extraction**: Python (functions/classes/methods), Markdown (headings), JS/TS (basic structure)
- **Dependency analysis** (`include_dependencies=True`): Static import analysis with categorization (stdlib/third-party/local)
- **Impact radius (blast radius)**: Shows how many files import the current file (low/medium/high risk levels)
- **Boundary enforcement**: Detects forbidden import patterns via `.scribe/config/boundary_rules.yaml`
- **Regex search default**: `search_mode="regex"` (changed from `"literal"`)
- **SKILL.md urgent detection**: Special warning when reading SKILL.md files
- **Static analysis disclaimer**: Honest limitations noted (no runtime deps, dynamic imports, reflection)

**Performance:**
- Zero overhead when `include_dependencies=False` (default)
- ~20% overhead when dependency analysis enabled
- <20ms boundary checking overhead

### 🗄️ Database Abstraction Layer (MANDATORY)

**NEVER use direct SQL in tools.** All database operations MUST go through `StorageBackend` (`storage/base.py`).

**Canonical API (`storage/base.py`):**

| Method | Purpose |
|--------|---------|
| `upsert_project(name, repo_root, progress_log_path, docs_json)` | Create/update project |
| `fetch_project(name)` | Get project by name |
| `list_projects()` | List all projects |
| `delete_project(name)` | Delete project |
| `update_project_docs(name, docs_json)` | Update only docs_json field |
| `insert_entry(...)` | Add log entry |
| `fetch_recent_entries(...)` | Get recent entries |
| `query_entries(...)` | Search entries |

**Why this matters:**
- Direct `_execute()` calls bypass the abstraction layer
- Changes won't work across backends (SQLite/Postgres)
- No write locking, no initialization checks
- Schema migrations won't apply

**Violation pattern (❌ NEVER DO THIS):**
```python
await backend._execute("UPDATE scribe_projects SET docs_json = ?", ...)
```

**Correct pattern (✅ ALWAYS DO THIS):**
```python
await backend.update_project_docs(project_name, docs_json)
```

**Important:**

* Do not invent new tool behaviors or `manage_docs` actions.
* If the needed action does not exist: stop, log the blocker, request a tool update.

---

## 🐳 Docker & Deployment

### Architecture

Scribe MCP runs as a containerized SSE service on Hetzner, integrated with Council MCP via Docker Compose overlay.

| Component | Port | Transport | Image |
|-----------|------|-----------|-------|
| Scribe MCP | 8200 | SSE (HTTP) | `scribe-mcp:latest` |
| CortaStore | 8201 | HTTP REST | `corta-store:latest` |
| Council MCP | 8100 | SSE (HTTP) | `council-mcp:latest` |
| PostgreSQL | 5432 | TCP | `pgvector/pgvector:pg16` |

### Build & Run Commands

```bash
# Build image (from scribe_mcp/ root)
docker build -f deploy/Dockerfile -t scribe-mcp:latest .

# Standalone run (SQLite, local dev)
docker run -d --name scribe-mcp -p 8200:8200 -v scribe_data:/app/.scribe scribe-mcp:latest

# Production deploy (with Council, PostgreSQL, CortaStore)
docker compose \
  -f council_mcp/deploy/docker-compose.yaml \
  -f scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d

# Validate compose config without starting
docker compose -f deploy/docker-compose.scribe.yaml config

# Rebuild after code changes
docker compose -f deploy/docker-compose.scribe.yaml build --no-cache scribe

# View logs
docker compose logs scribe --tail=50 -f

# Health check
curl http://localhost:8200/health
```

### Secrets (Non-Negotiable)

**NEVER put credentials in environment variables, compose files, or code.**

All secrets go in `secrets/` (gitignored) and are mounted as Docker secrets:

| Secret File | Mounted At | Env Var |
|-------------|-----------|---------|
| `secrets/scribe_db_url.txt` | `/run/secrets/scribe_db_url` | `SCRIBE_DB_URL` |
| `secrets/store_hmac_key.txt` | `/run/secrets/store_hmac_key` | `SCRIBE_OBJECT_STORE_KEY` |

The entrypoint script (`deploy/docker-entrypoint.sh`) reads secret files and exports them as environment variables before dropping privileges to the `scribe` user (UID 1001).

### Object Store Integration

Scribe syncs managed docs to CortaStore (content-addressable object store on Hetzner) for cross-machine access.

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRIBE_OBJECT_STORE_URL` | (none) | CortaStore URL. Presence enables sync. |
| `SCRIBE_OBJECT_STORE_KEY` | (none) | HMAC-SHA256 signing key (from Docker secret) |
| `SCRIBE_OBJECT_STORE_PROJECT` | `${COMPOSE_PROJECT_NAME}` | CortaStore project namespace |
| `SCRIBE_OBJECT_STORE_PROVIDER` | `corta` | Provider: `corta` or `s3` |

**In Docker Compose**, CortaStore is reached via Docker DNS: `http://corta-store:8201`

### Deployment Workflow (Hetzner)

```bash
# 1. Push code
git push origin master

# 2. SSH to Hetzner
ssh council-hub

# 3. Pull and rebuild
cd /opt/council_mcp
git -C scribe_mcp pull origin master
docker compose \
  -f council_mcp/deploy/docker-compose.yaml \
  -f scribe_mcp/deploy/docker-compose.scribe.yaml \
  build scribe

# 4. Rolling restart
docker compose \
  -f council_mcp/deploy/docker-compose.yaml \
  -f scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d scribe

# 5. Verify
curl http://localhost:8200/health
docker compose logs scribe --tail=20
```

### File Inventory

| File | Purpose |
|------|---------|
| `deploy/Dockerfile` | Multi-stage build (builder → runtime, ~330MB) |
| `deploy/docker-compose.scribe.yaml` | Compose overlay for Council integration |
| `deploy/docker-entrypoint.sh` | Secret bridge + privilege drop via gosu |
| `deploy/README.md` | Complete deployment guide |
| `.dockerignore` | Build context filter |
| `.env.example` | Environment variable template |

### Rules for Docker Changes

1. **Image size matters** — no PyTorch/sentence-transformers in Docker (excluded deliberately). Keep image under 400MB.
2. **Non-root always** — app runs as `scribe` (UID 1001). Only the entrypoint reads secrets as root.
3. **Compose overlay pattern** — Scribe's compose merges with Council's. Don't duplicate postgres/network definitions.
4. **Test locally first** — `docker build && docker run` before pushing to Hetzner.
5. **Health checks are required** — every service must expose `/health`.

---

## References (Deeper Governance)

This template is intentionally short. If present in the repo, these docs provide full rationale and examples:

* `AGENTS_EXTENDED.md`
* `deploy/README.md` (full Docker deployment guide)
* `.scribe/docs/dev_plans/.../wiki/ORCHESTRATION_RULES.md`
* `.scribe/docs/dev_plans/.../wiki/...` (bucket discipline, doc lifecycle examples)

---

## Repo-Specific Overrides

### Language & Runtime

* **Language:** Python 3.11+
* **Package:** `scribe_mcp` (src layout: `src/scribe_mcp/`)
* **Install:** `pip install -e .` (dev) or `pip install .` (production)

### Test Commands

```bash
# All functional tests
pytest

# Specific test file
pytest tests/test_object_store.py -v

# Performance tests (opt-in)
pytest -m performance
```

### Docker Commands

```bash
# Build
docker build -f deploy/Dockerfile -t scribe-mcp:latest .

# Run with health check
docker run -d -p 8200:8200 --name scribe-mcp scribe-mcp:latest
curl http://localhost:8200/health

# Compose validate
docker compose -f deploy/docker-compose.scribe.yaml config
```

### Key Entry Points

| Command | Purpose |
|---------|---------|
| `scribe-server-sse` | SSE transport server (Docker) |
| `scribe-mcp` | CLI entry point (`--transport sse\|stdio`) |
| `scribe-migrate-objects` | Bulk sync local docs to object store |
| `scribe-bootstrap-postgres` | PostgreSQL initial setup |

**Rule:** Overrides must not contradict the commandments above.
