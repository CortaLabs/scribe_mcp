# Tour: Scribe as an MCP product

Release line: `2.10.1`
Updated: `2026-06-29`

This tour is about the **MCP tools**. The CLI exists to help you run them locally, but the product is the MCP surface.

This page uses real MCP captures from `2026-04-18`. If we did not re-check a payload live, we do not pretend we did.

Install posture for this release line:

- preferred path is `scribe install`
- default install is preview-only (no DB mutation, no `.env` mutation, no projection)
- mutation requires explicit `--commit` (and `--yes` for non-interactive commit)
- Codex projection is explicit opt-in with `--project-codex` after successful commit

The current `2.10.1` release line fixes readable `read_recent(compact=True)` output; adds `scribe_doctor` internal repo-local plugin diagnostics for trust state, discovered stems, allow/block lists, blocked reasons, and restart/opt-in guidance without enabling production plugin trust; improves `manage_docs` registration/drift diagnostics; adds advisory reminder guidance fields; and accepts bounded single-managed-doc Codex-style `manage_docs(apply_patch)` input while rejecting add/delete, multi-doc, and target-mismatch patches with guidance. Reminder hook/context injection remains security-blocked future work. It carries the 2.9.0 public-safe affected-row referential inventory preflight for governed project-row repair planning, exposed as MCP tool `scribe_affected_row_referential_inventory_readonly_public_safe` and CLI command `scribe affected-row-inventory preflight --dry-run`, returning labels, booleans, and aggregate buckets only while failing closed on unproven target binding, ambiguous selected context, incomplete reference inventory, low-cardinality/private-output risk, missing storage backend, or mutation-shaped invocation. It keeps the 2.8.x tool discoverability, onboarding, install ergonomics, runtime honesty, stale managed-doc registration repair, clean-checkout plugin sync, lean shipped Scribe plugin skills (`scribe-integration` and `scribe-onboarding`), and clean-room wheel install/projection proof. This builds on `2.7.2` furnace-project quality-check O(N^2) elimination and several O(1) fast paths, and on `2.7.1`, which made Scribe's runtime faster to operate and easier to audit while keeping managed docs topology-aware, quality-check output agent-actionable, and operator-only mutation safer:

- Repeated same-session `set_project` calls for the same agent, project, and repo root return `side_effects.binding_reused=true` on the cheap path instead of repeating persistent binding writes or mutation-time reminder refresh.
- Runtime telemetry now persists tool durations, correlation IDs, measurement scope, and repo root for later audit.
- `append_entry` returns phase timing, so file WAL, DB mirror, state, reminder, formatting, and total latency are visible.
- Probe tooling can emit JSON, compare same-server roots, and drain background telemetry before process exit.
- Managed-doc frontmatter now has canonical lifecycle state, stable IDs, summaries, display-name-first attribution, and canonical doc-type/status normalization.
- Typed deterministic edges describe dependencies, supporting evidence, validations, supersession, blockers, and touched paths.
- `quality_check` remains the single proof path and blocks scaffold residue, failed-write residue, topology gaps, and unsafe ready/complete handoffs.
- `quality_check` returns grouped warning families, ranked agent actions, body/file line mapping, nearest-section context, repair kind, edit-action hints, and provenance.
- Atlas-style bulk mode can check all managed readiness docs or an explicit doc wave with `metadata={"quality": {"bulk": true}}` or `metadata={"quality": {"bulk": {"doc_names": [...]}}}`.
- Operators and agents can run topology scans, metadata scans, safe repairs, assisted repair plans, stale cleanup scans, handoff checks, and downstream manifest inspection through `manage_docs`.
- Operators and agents can edit bug/security reports created by `open_bug` or `open_security` through `manage_docs` using the returned case id, governed path, explicit report path, or canonical category metadata; resolved fix links close the shared case registry.
- Scribe exports sanitized derived topology and ingestion-manifest artifacts for downstream systems while leaving retrieval, embeddings, semantic ranking, and graph-RAG traversal outside Scribe.
- Managed-doc release governance still raises `SCF_CHANGELOG_CURRENT_VERSION_MISSING` when the active package version lacks accepted changelog coverage, and that warning flows through `quality_check`, reminders, and `project_health`.
- Scribe-owned write barriers protect mutation surfaces during maintenance, and exported remote transport blocks local operator-only tools unless they are explicitly remote-invokable.

If you only remember one thing, make it this:

- Scribe is not “a markdown generator with a server attached”
- Scribe is a project-scoped MCP tool system for audit trails, governed docs, and repo-safe inspection

## The shortest useful MCP loop

In most MCP hosts, the first meaningful sequence is:

1. `set_project(...)`
2. `read_recent(...)`
3. `read_file(..., mode="scan_only")`
4. `append_entry(...)`
5. `manage_docs(...)`

That is the core product loop.

## 1. Bind a project

Start here:

```python
set_project(
    agent="demo-agent",
    name="demo_docs",
    root="/absolute/path/to/repo",
    format="structured",
)
```

Verified live structured top-level keys:

```json
[
  "ok",
  "project",
  "generated",
  "skipped",
  "side_effects",
  "root_authorization",
  "scope_resolution",
  "recent_projects",
  "reminders"
]
```

Verified nested `project` keys included:

```json
[
  "name",
  "root",
  "progress_log",
  "docs_dir",
  "docs",
  "defaults",
  "author",
  "description",
  "tags",
  "meta",
  "version",
  "updated_by",
  "session_id"
]
```

Why this matters:

- it binds the repo and session boundary
- it creates the governed-doc working surface on a fresh project
- it gives later tools a trusted project context instead of leaving them to guess

## 2. Rehydrate context

Next:

```python
read_recent(
    agent="demo-agent",
    limit=5,
    format="readable",
)
```

Verified live readable shape:

```json
[
  {
    "type": "text",
    "text": "<ANSI-formatted log output>"
  }
]
```

This is how a session stops being stateless.

## 3. Inspect files without blowing tokens

One of Scribe’s best inspection paths is `read_file(..., mode="scan_only")`.

```python
read_file(
    agent="demo-agent",
    path="README.md",
    mode="scan_only",
    format="structured",
)
```

Verified top-level keys:

```json
[
  "ok",
  "scan",
  "mode",
  "frontmatter",
  "frontmatter_raw",
  "frontmatter_line_count",
  "frontmatter_byte_count",
  "has_frontmatter",
  "structure",
  "structure_pagination",
  "navigation_hints",
  "advanced_analysis_hint",
  "reminders"
]
```

Verified `scan` keys:

```json
[
  "absolute_path",
  "repo_relative_path",
  "byte_size",
  "line_count",
  "sha256",
  "newline_type",
  "encoding",
  "estimated_chunk_count"
]
```

Verified `structure` keys:

```json
[
  "ok",
  "type",
  "headings",
  "total_headings",
  "truncated"
]
```

This is the MCP version of looking before you leap. You get shape, size, structure, and navigation hints before you spend tokens on a deeper read.

Follow-up targeted read:

```python
read_file(
    agent="demo-agent",
    path="README.md",
    mode="line_range",
    start_line=1,
    end_line=40,
    format="readable",
)
```

Verified live readable shape:

```json
[
  {
    "type": "text",
    "text": "<formatted file snippet>"
  }
]
```

## 4. Search the repo safely

```python
search(
    agent="demo-agent",
    pattern="drift_score",
    format="structured",
)
```

Verified top-level keys:

```json
[
  "ok",
  "output_mode",
  "pattern",
  "files_searched",
  "files_with_matches",
  "total_matches",
  "files_skipped",
  "skip_details",
  "matches",
  "pagination"
]
```

This is the other half of the inspection story: `read_file` for one file, `search` for the repo.

This exact minimal call is the one we re-verified live. A first attempt with extra filter arguments was rejected by runtime validation in the active harness, so this example stays conservative on purpose.

## 5. Keep the audit trail alive

```python
append_entry(
    agent="demo-agent",
    message="Validated bootstrap and created governed docs scaffold.",
    status="success",
)
```

This is why Scribe is not just a file-editing tool. It preserves the execution trail next to the work.

## 6. Use the project registry like an operator

Scribe projects are not just directories. They become queryable registry objects.

```python
list_projects(
    agent="demo-agent",
    limit=5,
    format="structured",
)
```

Verified top-level keys:

```json
[
  "ok",
  "projects",
  "count",
  "total",
  "pagination",
  "summary",
  "resolution_source",
  "fallback_used",
  "fallback_chain",
  "resolution_summary",
  "active_project",
  "compatibility_recovery",
  "recent_projects",
  "reminders"
]
```

Verified per-project fields included:

```json
[
  "name",
  "root",
  "progress_log",
  "state",
  "sitrep_message",
  "entry_count"
]
```

This is where Scribe stops looking like a pile of markdown files and starts looking like an operational surface:

- projects have lifecycle state
- docs have drift signals
- activity becomes queryable instead of anecdotal

## 7. Query the execution trail directly

```python
query_entries(
    agent="demo-agent",
    message="bootstrap",
    format="structured",
)
```

Verified top-level keys:

```json
[
  "ok",
  "entries",
  "pagination",
  "search_params",
  "validation_warnings",
  "total_found",
  "returned",
  "source",
  "search_message",
  "reminders",
  "project",
  "project_resolution"
]
```

This is the difference between "I saw it happen once" and "I can prove what happened later."

## 8. Govern docs without guessing the contract

The managed-doc surface matters because:

- actions like `create`, `replace_section`, and `status_update` are real
- managed docs carry stable anchors like `<!-- ID: problem_statement -->`
- that is what keeps later updates deterministic instead of devolving into heading-text guesswork

We are not inventing a fake success payload for `manage_docs`. In the live harness used for this docs pass, `manage_docs(action="list_sections", ...)` did not return a clean verified success example, so this tour leaves that example out.

## What to read next

- [Scribe_Usage.md](Scribe_Usage.md) for the day-to-day operating loop
- [INSTALL_AND_BOOTSTRAP.md](INSTALL_AND_BOOTSTRAP.md) for runtime setup
- [mcp_server_guide.md](mcp_server_guide.md) for host wiring details
