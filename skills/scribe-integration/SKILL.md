---
name: scribe-integration
description: How to use Scribe MCP tools correctly — logging, docs, topology, bugs, file reading, search
user-invocable: true
context: full
visibility: exported
owner: scribe-mcp
---

# Scribe Integration Guide

Scribe is the persistent audit trail for all Council work. Every significant action must be logged. Unlogged work is invisible to the team and to future agents.

## Evidence Family Boundary

- `scribe-integration` is the protocol entrypoint for Scribe work (startup sequence, logging cadence, docs lifecycle, bug/security reporting).
- Retrieval evidence (semantic search, citations, corpus refresh) belongs to `scribe-rag-workflow`.
- Runtime/log evidence (daemon/web/process telemetry, incident traces, log-plane checks) belongs to `log-observability`.
- Browser runtime validation belongs to a dedicated browser-validation skill package; do not expand this skill into browser troubleshooting procedures.

## Mandatory Startup Sequence

Before ANY work — reading files, editing code, planning — execute these two calls:

```python
# 1. Activate project (sets context for all subsequent calls)
set_project(agent="<your-name>", name="<project_name>", root="<repo_root>")

# 2. Load recent context (understand what's happened before you)
read_recent(agent="<your-name>", limit=5)
```

**Why this matters:**
- `set_project` ensures your `append_entry` calls go to the right project log
- Without `set_project`, logs are orphaned in the default project
- `read_recent` prevents duplicating work already done
- The base Scribe project is only for ephemeral tactical work; once a named workstream exists, stay on it
- Orchestrators must propagate the same active project to every delegated agent instead of silently falling back to the base project

**Skip these two steps = your work gets rejected.**

### Project Binding Is Sticky

`set_project` is not a per-log call.

- Call `set_project` once during startup for the active project.
- Do not call `set_project` before every `append_entry`.
- Keep using `append_entry`, `manage_docs`, `read_recent`, and related Scribe calls on the active project context.
- Re-run `set_project` only when the operator/orchestrator changes the active project, or when an `append_entry`/Scribe response indicates sentinel/fallback/base-project mode, project mismatch, or orphaned logging.

---

## Logging with append_entry

Log every 2-3 significant actions. If it's not logged, it didn't happen.

### Single Entry

```python
append_entry(
    agent="forge",
    message="Fixed JWT validation — expiry now checked with 15min grace period",
    status="success",
    meta={
        "reasoning": {
            "why": "JWT tokens were accepted after expiry, allowing stale sessions",
            "what": "Added expiry check with configurable grace period to auth.py:142",
            "how": "Read auth.py scan_only, identified missing check, added with config fallback"
        },
        "file": "src/council_mcp/web/auth.py",
        "line": 142
    }
)
```

### Status Levels

| Status | Use For |
|--------|---------|
| `info` | Investigation steps, reading files, planning |
| `success` | Completed work, passing tests, fixes verified |
| `warn` | Unexpected findings, degraded paths, skipped steps |
| `error` | Failures, blocked work, tool errors |
| `bug` | Bug discoveries (triggers bug tracking) |
| `plan` | Work plans, task decomposition, approach decisions |

### Bulk Entries (Backfilling)

When you have multiple actions to log at once:

```python
append_entry(
    agent="forge",
    items=json.dumps([
        {"message": "Scanned auth.py — found JWT validation at line 142", "status": "info"},
        {"message": "Identified missing expiry check", "status": "bug",
         "meta": {"file": "auth.py:142"}},
        {"message": "Added expiry check with 15min grace period", "status": "success"}
    ])
)
```

### Global Log (Milestones)

For repo-wide milestones (phase completions, major decisions):

```python
append_entry(
    agent="atlas",
    message="Phase 1 complete — auth system refactor shipped, 44/44 tests pass",
    status="success",
    log_type="global",
    meta={"project": "council_unified_platform", "entry_type": "milestone"}
)
```

### Reasoning Traces (Required)

Every `append_entry` for significant work MUST include reasoning in `meta`:

```python
meta={
    "reasoning": {
        "why": "research goal or decision point that prompted this action",
        "what": "constraints, alternatives considered, scope of change",
        "how": "methodology, tools used, steps taken"
    }
}
```

---

## Document Management with manage_docs

### Frontmatter, Status Intent, Topology, and Scaffold Quality Gates

- Narrative-doc frontmatter changes must use `frontmatter_update` with `metadata.frontmatter`.
- `status_update` is checklist-only; using it on narrative docs must be treated as an intent error (`DOC_STATUS_INTENT_MISMATCH`).
- Checklist item `metadata.status` is item state only; it must not update managed-doc frontmatter lifecycle `status`.
- Managed-doc lifecycle status must use Scribe's canonical values: `scaffolded`, `in_progress`, `ready`, `complete`, `stale`, `superseded`, `blocked`, or `archived`.
- Managed-doc frontmatter should include stable `id`, `doc_type`, `doc_name`, `status`, `summary`, `owners`, `tags`, and typed topology when relevant.
- Human-facing attribution should use display names such as `Forge`, `Atlas`, `Witness`, `Crucible`, `Blueprint`, `Arbiter`, `Loom`, and `Quill`; preserve opaque runtime IDs only as secondary provenance when Scribe provides them.
- Scaffold residue means not done; completion/readiness can be blocked with `DOC_NOT_DONE_SCAFFOLD_QUALITY`.
- Run `quality_check` before handoff on managed docs, use bulk `quality_check` for Atlas/project-wave validation, run `quality_handoff_check` before clean clock-out/handoff claims, and run `project_health` before closeout.
- `quality_check` is the agent remediation surface: consume `summary`, `warning_groups`, `agent_actions`, warning `location`, `section`, `repair_hint`, and provenance fields before inventing a manual grep plan.
- Configured log surfaces, including custom `logs:` entries in `.scribe/config/scribe.yaml`, are not readiness-quality targets.

Quality warnings to treat as authoritative:
- `SCF_PLACEHOLDER_BRACKET`
- `SCF_TEMPLATE_PROSE`
- `SCF_FAILED_WRITE_RESIDUE`
- `SCF_EMPTY_FINDING`
- `SCF_UNFILLED_APPENDIX`
- `SCF_TODO_ONLY_SECTION`
- `SCF_LOG_TEMPLATE_ONLY`
- `SCF_FRONTMATTER_MISMATCH`
- `SCF_LIFECYCLE_STATUS_MISMATCH`
- `SCF_INDEX_STALE`
- `SCF_INDEX_MISSING`
- `SCF_DOC_UNINDEXED`
- `SCF_NONCANONICAL_LOCATION`
- `SCF_CHANGELOG_ENTRY_ID_MISSING`
- `SCF_CHANGELOG_ENTRY_ID_INVALID`
- `SCF_CHANGELOG_SUMMARY_MISSING`
- `SCF_CHANGELOG_EVIDENCE_MISSING`
- `SCF_CHANGELOG_DUPLICATE_SOURCE_KEY`
- `SCF_CHANGELOG_RAW_PROGRESS_DUMP`
- `SCF_CHANGELOG_AMBIGUOUS_BODY_STATUS`
- `SCF_CHANGELOG_ESCAPED_NEWLINES`
- `SCF_RESEARCH_CONTEXT_DRIFT`

Topology and lifecycle warnings to treat as authoritative when present:
- `TOPOLOGY_MISSING_ID`
- `TOPOLOGY_DUPLICATE_ID`
- `TOPOLOGY_DANGLING_EDGE`
- `TOPOLOGY_INVALID_EDGE_SHAPE`
- `TOPOLOGY_READY_DEPENDS_ON_DRAFT`
- `TOPOLOGY_DEPENDENCY_CYCLE`
- `DOC_MISSING_SUMMARY`
- `DOC_STATUS_INVALID`
- `DOC_STATUS_TRANSITION_BLOCKED`
- `DOC_AGENT_ID_LEAK`
- `DOC_REGISTRY_MISSING`

### Document Topology MCP Usage

Use topology actions to keep the managed corpus deterministic and downstream-safe. These actions belong in normal Scribe workflow; do not invent a second registry, validator, semantic linker, or retrieval pipeline inside Scribe.

```python
manage_docs(
    agent="witness",
    action="topology_scan",
    dry_run=True
)

manage_docs(
    agent="witness",
    action="metadata_scan",
    dry_run=True
)

manage_docs(
    agent="forge",
    action="metadata_repair",
    metadata={"mode": "repair_safe"},
    dry_run=False
)

manage_docs(
    agent="witness",
    action="ingestion_manifest_inspect",
    dry_run=True
)
```

Repair modes:
- `report_only`: produce findings and perform no writes.
- `repair_safe`: apply deterministic fixes only, such as generated IDs, canonical missing status, scalar-to-list normalization, and safe metadata shells.
- `repair_assisted`: produce an operator/agent review plan for ambiguous fixes.

Topology fields:
- `depends_on`
- `supports`
- `validates`
- `supersedes`
- `blocked_by`
- `touches`
- `related_docs`

Downstream export boundary:
- Scribe may generate sanitized local artifacts such as `doc_topology.json`, `work_topology.json`, and `downstream_ingestion_manifest.json` under `.scribe/indexes/`.
- These artifacts are derived outputs, not a second source of truth.
- Downstream consumers may build retrieval or graph systems from them; Scribe itself must stay deterministic and must not add embeddings, transformer classification, semantic guessing, or graph-RAG behavior.

Canonical research/index guidance:
- Keep research docs in flat `.scribe/docs/dev_plans/<project>/research/`.
- Maintain `research/INDEX.md` as the canonical index surface.
- Treat noncanonical, stale, orphaned, or unindexed research states as warnings that must be resolved before done-state claims.
- Research docs for a named workstream must be created in the active Scribe project. A research artifact written to the repo root, base project, wrong dev-plan folder, wrong filename prefix, or another Scribe project is not accepted evidence.
- If a research doc lands in the wrong location/project, BLOCK downstream routing and use Scribe `manage_docs(action="rehome_doc", metadata={"target_project": "<active_project>"})` or the dedicated Scribe rehome-doc tool if exposed. Do not move managed docs with shell `mv`, `cp`, ad hoc file writes, or git-only renames.
- If `manage_docs(create)` lands a research artifact in the wrong place, rehome it before writing substantive content. The clean sequence is create -> verify path/project -> rehome if needed -> write body -> quality_check -> index/readback.
- Scribe quality checks are necessary but not sufficient. Coordinator/Witness should also scan for scaffold residue, duplicate headings, stale body status, noncanonical paths, escaped-newline sludge, and index drift before accepting research.

Project-level artifact guidance:
- Research docs belong in `research/INDEX.md`.
- Synthesis, review, architecture, phase-plan, checklist, and changelog documents are project-level artifacts, not research docs.
- Do not force synthesis/review/project-level docs into `research/INDEX.md`; rely on project-level artifact health and quality surfaces.

### Frontmatter Update MCP Usage

Use this for narrative-doc metadata, not checklist progress:

```python
manage_docs(
    agent="blueprint",
    action="frontmatter_update",
    doc_name="ARCHITECTURE_GUIDE",
    metadata={
        "frontmatter": {
            "status": "ready",
            "owners": ["blueprint"],
            "summary": "Architecture plan ready for Witness review"
        }
    },
    dry_run=True
)
```

Re-run with `dry_run=False` only after the preview shows the intended frontmatter keys. `created_by` and `edit_trace` are reserved lifecycle fields; do not try to author them manually.

### Quality Check MCP Usage

Use this before handoff on managed docs:

```python
manage_docs(
    agent="witness",
    action="quality_check",
    doc_name="ARCHITECTURE_GUIDE",
    dry_run=True
)
```

For Atlas-style project or wave validation, keep the existing `quality_check` action and request bulk mode through metadata:

```python
manage_docs(
    agent="atlas",
    action="quality_check",
    metadata={"quality": {"bulk": True}},
    dry_run=True
)

manage_docs(
    agent="atlas",
    action="quality_check",
    metadata={
        "quality": {
            "bulk": {
                "doc_names": ["ARCHITECTURE_GUIDE", "PHASE_PLAN", "CHECKLIST"],
                "include_clean": False,
                "include_warnings": False,
                "max_agent_actions": 5
            }
        }
    },
    dry_run=True
)
```

Bulk results include an aggregate `summary`, per-document `documents`, doc-aware flattened warnings, grouped warning families, and ranked `agent_actions`. Treat blocking warnings as unfinished work. Lifecycle/status mismatch and changelog escaped-newline warnings are blockers, not cosmetic notes.

### Quality Handoff MCP Usage

Use this before claiming clean handoff, completion, or clock-out for managed-doc work:

```python
manage_docs(
    agent="witness",
    action="quality_handoff_check",
    dry_run=True
)
```

If `handoff_allowed` is false, fix the listed managed docs before handing work back. Use returned actions as the repair checklist. Scaffold placeholders, failed-write residue, unresolved blockers, and serious topology warnings are not acceptable final-state paperwork.

### Planning Doc Ownership vs Checklist Proof

- The coordinator may create and update the managed pre-research `SPEC` doc with the operator.
- That `SPEC` is problem-definition only: problem, goals, non-goals, constraints, and research questions. It is not an architecture doc, phase plan, or task package.
- A usable `SPEC` is concrete enough that Lens can answer it; if the open questions are mushy or solution-biased, keep refining before research starts.
- Blueprint owns planning-content updates in `ARCHITECTURE_GUIDE`, `PHASE_PLAN`, and the planning structure of `CHECKLIST` for non-trivial named work.
- The active coordinator owns verification evidence plus `CHECKLIST` status/proof after task packages complete.
- `SPEC` is the only coordinator-owned planning artifact before Blueprint runs.
- Do not rewrite planning docs after every package-level correction. Update checklist status/proof for completed packages, and only route planning-doc rewrites when broader plan boundaries change.
- In named Scribe projects, no code may continue when direction/scope has deviated from the documented plan. Either correct execution back to plan immediately or update the plan first.
- If major reshaping or new phases are required mid-stream, open a new named Scribe project and run a fresh planning cycle instead of overwriting prior planning docs in place.

### Critical Rule: `create` is NOT enough

`manage_docs(action="create")` scaffolds an **empty** document template. You MUST follow it with `replace_section` calls to write actual content.

```python
# Step 1: Create the scaffold (empty doc)
manage_docs(
    agent="lens",
    action="create",
    doc_name="RESEARCH_AUTH_PATTERNS",
    metadata={
        "doc_type": "research",
        "research_goal": "Understand existing auth patterns before refactoring"
    }
)

# Step 2: ALWAYS follow with replace_section for each section
manage_docs(
    agent="lens",
    action="replace_section",
    doc_name="RESEARCH_AUTH_PATTERNS",
    section="findings",
    content="""## Auth Pattern Findings

JWT validation lives in `src/council_mcp/web/auth.py:142`.
Current flow: token decode → signature check → expiry NOT checked.
Grace period config key: `council.auth.token_grace_seconds` (missing from DEFAULT_CONFIG).
"""
)

manage_docs(
    agent="lens",
    action="replace_section",
    doc_name="RESEARCH_AUTH_PATTERNS",
    section="recommendations",
    content="Add expiry check with configurable grace period. Add key to DEFAULT_CONFIG."
)
```

### Built-In `create` Doc Types

| `doc_type` | Use For | Sections |
|------------|---------|---------|
| `research` | Lens investigation output | findings, recommendations, confidence |
| `bug` | Bug reports | symptoms, root_cause, fix, verification |
| `security` | Security reports | findings, severity, remediation |
| `review` | Review or audit reports | summary, findings, verdict |
| `agent_card` | Persona / agent documentation | role, capabilities, constraints |
| `custom` | Council-specific managed docs such as a pre-research `SPEC` | user-defined |

### Standard Scaffold Families

These are the common generated project-doc surfaces used by Scribe tooling:

| Scaffold | Use For |
|----------|---------|
| `architecture` | Design docs |
| `phase_plan` | Phase plans |
| `checklist` | Task tracking |
| `progress_log` | Workstream progress trail |
| `doc_log` | Documentation change trail |
| `security_log` | Security-specific tracking |
| `bug_log` | Bug-specific tracking |
| `changelog` | Curated project outcome history |

For generic test organization, naming, markers, and placement across codebases, use `/test-taxonomy`.

### Changelog and Version Context

Use changelogs for accepted outcomes, not raw progress-log dumps.

- Author curated entries in the project `CHANGELOG.md`.
- Treat `.scribe/docs/GLOBAL_CHANGELOG.md` as derived output only.
- Reconcile global entries only from project entries with `entry_status: accepted`.
- Run `quality_check` before reconciliation.
- Run `preview_reconciliation` before `apply_global_changelog`.
- Preview and quality actions diagnose; they do not perform hidden mutation.

Required accepted-entry fields:
- `entry_id`
- `entry_status`
- `summary`
- `evidence_refs`

Identity and dedupe:
- `entry_id` format: `<yyyymmdd>:<slug>`
- source key: `(project_slug, entry_id)`

Status boundary:
- `entry_status` is changelog-entry state only.
- Managed-doc frontmatter lifecycle `status` remains separate and must be repaired through `frontmatter_update`.
- Body prose such as `Status: accepted` inside changelog entries is ambiguous; prefer explicit `entry_status`.

Version/context behavior is advisory:
- Scribe observes context from manual metadata first, then `pyproject.toml`, then optional git fallback, then `unknown`.
- There is no SemVer enforcement, no auto-bump, and no hidden release management.
- Missing/unknown version context is allowed and non-blocking.
- Historical research context can warn as drifted without overriding active code as source of truth.

Escaped-newline rule:
- A project `CHANGELOG.md` must be real multiline markdown.
- Literal serialized `\n` sludge in changelog content is a blocking `SCF_CHANGELOG_ESCAPED_NEWLINES` quality failure.
- Fix it by rewriting the changelog with real newlines, not by suppressing the warning.

### Editing Documents: Prefer `apply_patch`

**`apply_patch` is the primary edit action.** It uses context matching (not bare line numbers) so it handles document drift gracefully. Always `dry_run=True` first.

#### Unified diff mode (recommended for most edits)

```python
# Apply a unified diff — context lines anchor the edit even if line numbers drifted
manage_docs(
    agent="forge",
    action="apply_patch",
    doc_name="architecture",
    patch="""--- before
+++ after
@@ -5,3 +5,4 @@
 ## Components

 Current auth uses basic JWT decode.
+Added expiry validation with 15s grace period.
""",
    dry_run=True  # ALWAYS dry_run first, then re-run with dry_run=False
)
```

#### Structured edit mode (for targeted line/section replacement)

```python
# Replace a specific section by anchor
manage_docs(
    agent="forge",
    action="apply_patch",
    doc_name="architecture",
    edit={"type": "replace_section", "section": "findings", "content": "Updated findings..."}
)

# Replace a block by anchor marker
manage_docs(
    agent="forge",
    action="apply_patch",
    edit={"type": "replace_block", "anchor": "<!-- ID: constraints -->", "content": "New constraints..."},
    doc_name="architecture"
)
```

**Why `apply_patch` over `replace_range`:**
- Context lines act as anchors even when line numbers shift
- Smart 3-tier matching: exact position, frontmatter offset, then full-document search
- Clear diagnostics when context doesn't match
- Handles multi-hunk patches atomically

### Other Edit Actions

#### `replace_range` (when you know exact line numbers)

**Line number coordinate system:** By default, `replace_range` called via the MCP tool uses **file-relative** line numbers (matching what `read_file` returns). This means you can use line numbers directly from `scan_only` or `line_range` output.

```python
# Line numbers from read_file work directly
manage_docs(
    agent="forge",
    action="replace_range",
    doc_name="phase_plan",
    start_line=45,   # file-relative (includes frontmatter in count)
    end_line=50,
    content="New content for these lines"
)

# For body-relative line numbers (legacy behavior, excludes frontmatter):
manage_docs(
    agent="forge",
    action="replace_range",
    doc_name="phase_plan",
    start_line=5,
    end_line=10,
    content="Body-relative replacement",
    metadata={"line_reference": "body"}
)
```

#### `replace_text` (find/replace with pattern matching)

```python
# Literal find/replace (default)
manage_docs(
    agent="forge",
    action="replace_text",
    doc_name="architecture",
    metadata={"find": "old_term", "replace": "new_term", "replace_all": True}
)

# Regex mode
manage_docs(
    agent="forge",
    action="replace_text",
    doc_name="architecture",
    metadata={"find": r"v\d+\.\d+", "replace": "v2.3", "match_mode": "regex"}
)

# Scoped to a section
manage_docs(
    agent="forge",
    action="replace_text",
    doc_name="architecture",
    metadata={"find": "TODO", "replace": "DONE", "scope": "section:findings"}
)
```

#### `append` (add content to end of doc or section)

```python
# Append to a section (inside = immediately after anchor)
manage_docs(
    agent="forge",
    action="append",
    doc_name="architecture",
    section="constraints",
    content="- New constraint added",
    metadata={"position": "inside"}  # "before" | "inside" | "after" (default)
)
```

### Checklist Updates

```python
# Mark a checklist item as done (with proof)
manage_docs(
    agent="forge",
    action="status_update",
    doc_name="checklist",
    section="task_auth_fix",
    metadata={"status": "done", "proof": "tests/test_auth.py::test_jwt_expiry PASSED"}
)
```

`section` may be a heading/section id or an inline item id such as `<!-- id: p4-task-3 -->`.
The helper should update exactly the targeted checklist item. If it appends a duplicate item, rewrites neighboring items, or cannot find an existing inline id, treat that as tool friction and fix/report it before final handoff.

---

## Bug Reporting

All agents report bugs — not just Mantis. When you find a bug, file it immediately.

```python
# Step 1: Open the case
open_bug(
    agent="forge",
    title="JWT tokens accepted after expiry",
    symptoms="Authenticated requests succeed with tokens expired >24h ago",
    category="logic"  # logic | runtime | config | data | integration | performance
)

# Step 2: Create the bug report doc scaffold
manage_docs(
    agent="forge",
    action="create",
    metadata={
        "doc_type": "bug",
        "category": "logic",
        "slug": "jwt-expiry-not-checked",
        "severity": "high",  # critical | high | medium | low
        "title": "JWT tokens accepted after expiry"
    }
)

# Step 3: Write each section
manage_docs(
    agent="forge",
    action="replace_section",
    doc_name="jwt-expiry-not-checked",
    section="symptoms",
    content="Authenticated requests succeed with JWT tokens expired >24 hours ago. No error returned."
)

manage_docs(
    agent="forge",
    action="replace_section",
    doc_name="jwt-expiry-not-checked",
    section="root_cause",
    content="auth.py:142 — `_validate_token()` checks signature but not `exp` claim. JWT decode uses `verify_exp=False`."
)

manage_docs(
    agent="forge",
    action="replace_section",
    doc_name="jwt-expiry-not-checked",
    section="fix",
    content="Set `verify_exp=True` in jwt.decode() call. Add 15s grace period via `council.auth.token_grace_seconds`."
)

# Step 4: Link the fix when resolved
link_fix(
    agent="forge",
    case_id="BUG-jwt-expiry-not-checked",
    artifact_ref="src/council_mcp/web/auth.py:142",
    landing_status="merged"
)
```

---

## File Reading with read_file

**RULE: ALWAYS scan before you read.** Never load entire large files.

### Step 1: Scan First

```python
# Get structure without loading content — cheap and fast
read_file(
    agent="forge",
    path="src/council_mcp/web/auth.py",
    mode="scan_only",
    include_dependencies=True  # shows imports and dependency graph
)
```

The scan returns class names, function names, and line numbers. Use these to target your reads.

### Step 2: Read Only What You Need

```python
# Read a specific range (from line numbers in the scan)
read_file(
    agent="forge",
    path="src/council_mcp/web/auth.py",
    mode="line_range",
    start_line=130,
    end_line=165
)
```

### Read Modes

| Mode | Use For | Cost |
|------|---------|------|
| `scan_only` | Structure overview, line numbers, imports | Cheapest |
| `line_range` | Specific function or class | Cheap |
| `chunk` | Sequential chunks (chunk_index=[0,1,2]) | Medium |
| `page` | Paginated reading (page_number, page_size) | Medium |
| `search` | Pattern search within file | Medium |
| `full_stream` | Entire file (only for small files) | Expensive |

### Cross-Repo Reading

```python
read_file(
    agent="forge",
    path="/home/user/projects/scribe_mcp/src/server.py",
    mode="scan_only",
    include_dependencies=True,
    allow_outside_repo=True  # REQUIRED for paths outside current repo
)
```

---

## Search Patterns

### Search Codebase (Regex)

```python
search(
    agent="forge",
    pattern="class.*Manager",      # Regex pattern
    glob="**/*.py"                  # File pattern filter
)
```

```python
search(
    agent="forge",
    pattern="_get_active_council_id",
    glob="src/**/*.py"
)
```

### Search Log History

```python
# Find recent entries about a topic
query_entries(
    agent="forge",
    message="JWT",                  # Search term
    message_mode="substring"        # Substring match
)
```

---

## Anti-Patterns

### Wrong — Creating a doc without writing content

```python
# WRONG: create alone produces an empty document
manage_docs(agent="forge", action="create", doc_name="RESEARCH_X", metadata={...})
# Nothing was written — doc is empty
```

### Right — Create then replace_section

```python
manage_docs(agent="forge", action="create", doc_name="RESEARCH_X", metadata={...})
manage_docs(agent="forge", action="replace_section",
            doc_name="RESEARCH_X", section="findings", content="Actual findings here...")
```

### Wrong — Using replace_range for multi-step document edits

```python
# WRONG: line numbers drift between calls, second edit hits wrong lines
manage_docs(action="replace_range", doc_name="arch", start_line=10, end_line=15, content="...")
manage_docs(action="replace_range", doc_name="arch", start_line=20, end_line=25, content="...")
```

### Right — Use apply_patch with context matching

```python
# RIGHT: context lines anchor each hunk independently
manage_docs(action="apply_patch", doc_name="arch", patch="..unified diff..", dry_run=True)
```

### Wrong — Skipping set_project

```python
# WRONG: logs go to wrong project or fail silently
append_entry(agent="forge", message="Did something important", status="success")
```

### Right — Always set_project first

```python
set_project(agent="forge", name="my_project", root="/path/to/repo")
append_entry(agent="forge", message="Did something important", status="success")
```

### Wrong — Reading entire large files

```python
# WRONG: loads 800 lines when you need 20
read_file(agent="forge", path="src/big_file.py", mode="full_stream")
```

### Right — Scan then target

```python
read_file(agent="forge", path="src/big_file.py", mode="scan_only")
# See line 142 has _validate_token()
read_file(agent="forge", path="src/big_file.py", mode="line_range", start_line=140, end_line=165)
```

### Wrong — Not calling read_recent before work

```python
# WRONG: starting blind, may duplicate work already done
set_project(agent="forge", name="my_project", root="/path/to/repo")
# Immediately starts coding without checking recent progress
```

### Right — Always check recent context

```python
set_project(agent="forge", name="my_project", root="/path/to/repo")
read_recent(agent="forge", limit=5)  # Load what's already been done
# NOW start working
```
