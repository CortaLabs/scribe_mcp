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
2. Use `manage_docs` to draft/populate, in **`.scribe/docs/`**:

   * `ARCHITECTURE_GUIDE.md`
   * `PHASE_PLAN.md`
   * `CHECKLIST.md`
3. Keep these three docs consistent: architecture decisions must be reflected in phase/checklist, and phase/checklist changes must not contradict architecture.
4. Only after docs exist and are coherent may you begin feature code.
5. Continue using `append_entry` while drafting docs (docs and logs are both mandatory).

**Note:** `manage_docs` is for structured project documentation and artifacts.

* **AGENTS.md is edited by hand** (do not generate/maintain it via `manage_docs`).

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

**Important:**

* Do not invent new tool behaviors or `manage_docs` actions.
* If the needed action does not exist: stop, log the blocker, request a tool update.

---

## References (Deeper Governance)

This template is intentionally short. If present in the repo, these docs provide full rationale and examples:

* `AGENTS_EXTENDED.md`
* `.scribe/docs/dev_plans/.../wiki/ORCHESTRATION_RULES.md`
* `.scribe/docs/dev_plans/.../wiki/...` (bucket discipline, doc lifecycle examples)

---

## Repo-Specific Overrides

Fill in:

* language/runtime details
* test commands
* lint/typecheck commands
* directory conventions

**Rule:** Overrides must not contradict the commandments above.
