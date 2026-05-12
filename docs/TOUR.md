# Tour: Scribe as an MCP product

Release line: `2.2.19`
Updated: `2026-05-12`

This tour is about the **MCP tools**. The CLI exists to help you run them locally, but the product is the MCP surface.

This page uses real MCP captures from `2026-04-18`. If we did not re-check a payload live, we do not pretend we did.

Install posture for this release line:

- preferred path is `scribe install`
- default install is preview-only (no DB mutation, no `.env` mutation, no projection)
- mutation requires explicit `--commit` (and `--yes` for non-interactive commit)
- Codex projection is explicit opt-in with `--project-codex` after successful commit

Release `2.2.19` adds version-aware changelog memory to the governed-doc loop:

- Project `CHANGELOG.md` is the curated source for accepted project outcomes.
- `.scribe/docs/GLOBAL_CHANGELOG.md` is derived from accepted project entries through preview/apply reconciliation.
- Changelog entry identity stays local (`<yyyymmdd>:<slug>`) while global dedupe uses `(project_slug, entry_id)`.
- Version context is advisory only: Scribe observes `pyproject.toml` or explicit metadata without enforcing SemVer or auto-bumping.
- Research context can warn when historical version evidence drifts, while active code remains the source of truth.
- `quality_check` now blocks lifecycle mismatch, changelog escaped-newline sludge, and other scaffold/readiness failures.

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
