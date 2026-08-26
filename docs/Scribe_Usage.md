# Scribe MCP usage guide

Release line: `2.11.1`
Updated: `2026-06-29`

This guide is about day-to-day usage once Scribe is installed.

If you have not installed or bootstrapped Scribe yet, start with [INSTALL_AND_BOOTSTRAP.md](INSTALL_AND_BOOTSTRAP.md). If you want the fast MCP-first tour first, start with [TOUR.md](TOUR.md).

Install behavior reminder for day-to-day operators:

- use `scribe install` as the preferred setup path
- default install is preview-only and does not mutate DB, `.env`, or projection state
- use `scribe install --commit` to apply mutations
- use `scribe install --commit --yes` for approved non-interactive commit flows
- use `--project-codex` only when you explicitly want Codex projection after core install

The current `2.11.1` release line rejects hollow `append_entry` payloads before any write, fixes readable `read_recent(compact=True)` output so rendered entries retain full fields, and adds `scribe_doctor` diagnostics for repo-local plugin loading/trust state, discovered plugin stems, configured allow/block lists, blocked reasons, and restart/opt-in guidance. It carries the `2.9.0` read-only affected-row referential inventory preflight for governed project-row repair planning: the MCP tool `scribe_affected_row_referential_inventory_readonly_public_safe` and CLI command `scribe affected-row-inventory preflight --dry-run` emit only public-safe labels, booleans, and aggregate buckets, and fail closed on unproven target binding, ambiguous selected context, incomplete reference inventory, low-cardinality/private-output risk, missing storage backend, or mutation-shaped invocation. It keeps the 2.8.x host-facing `manage_docs` input-schema enrichment, unified case-status vocabulary, `read_file` pagination and message-filter speedups, wired reminder engine, tool discoverability and onboarding skills, packaged plugin projection, targeted existing-doc auto-registration, clean-checkout plugin sync, lean shipped plugin skills (`scribe-integration` and `scribe-onboarding`), and terminal `complete` case filtering.
Release governance in this line also blocks missing current-version changelog coverage: `SCF_CHANGELOG_CURRENT_VERSION_MISSING` is emitted by `quality_check`, echoed in reminders, and shown in `project_health` quality signals until fixed. Quality responses include grouped warning families, ranked agent actions, file/section repair hints, and handoff follow-up actions so agents can move directly from finding to fix.

## The short mental model

Scribe is easiest to understand as a loop:

1. bind a project
2. read the current record
3. do work
4. log what happened
5. keep the governed docs current

This is not just about having logs or docs. It is about keeping execution history and project artifacts tied together closely enough that an agent or operator can reconstruct what happened later.

## The first useful workflow

Once your runtime is configured, the smallest meaningful loop looks like this:

```bash
scribe call set_project \
  --agent demo-agent \
  --repo-root "$PWD" \
  --arg name=demo_docs \
  --arg root="$PWD" \
  --arg format=structured \
  --pretty
```

Then:

```bash
scribe call read_recent \
  --agent demo-agent \
  --repo-root "$PWD" \
  --arg limit=5 \
  --pretty
```

Then start leaving an audit trail:

```bash
scribe call append_entry \
  --agent demo-agent \
  --repo-root "$PWD" \
  --arg message="Validated bootstrap and created governed docs scaffold." \
  --arg status=success \
  --pretty
```

That loop is intentionally simple:

- `set_project` gives the session a repo/project boundary
- `read_recent` rehydrates context
- `append_entry` records meaningful milestones

## What `set_project` actually does

On a fresh project, `set_project` can do more than bind context. It can scaffold the governed docs surface too:

```text
.scribe/docs/dev_plans/<project>/
  ARCHITECTURE_GUIDE.md
  PHASE_PLAN.md
  CHECKLIST.md
  PROGRESS_LOG.md
  DOC_LOG.md
  SECURITY_LOG.md
  BUG_LOG.md
```

That is why `set_project` is such an important starting point. It creates the workspace where later `manage_docs`, `append_entry`, and query tools can operate coherently.

It also sets up the basis for the project-registry view later. Scribe is not just creating files; it is creating a project the runtime can inspect for lifecycle, activity, and doc-health signals.

If the same agent is already bound to the same project and repo root in the same live session, structured and compact `set_project` calls take the reuse path. That response includes `side_effects.binding_reused=true`, skips persistent project/session/doc writes, skips mutation-time reminder refresh, and leaves performance timing in structured telemetry instead of warning output.

## The tool families you will actually use

### Project and session tools

Use these first.

#### `set_project`

Bind the active project and repo root for the current session.

Important parameters:

- `agent`: required agent identity
- `name`: project name
- `root`: repo root
- `format`: `readable`, `structured`, or `compact`

#### `read_recent`

Read the most recent entries for the active project.

Common parameters:

- `agent`
- `project` override when needed
- `limit` or `n`
- `format`

### Logging and audit tools

Use these continuously, not just at the end.

#### `append_entry`

Append a structured audit entry with optional metadata.

Common parameters:

- `agent`
- `message`
- `status`
- `meta`
- `log_type`

#### `query_entries`

Use this when `read_recent` is not enough and you need historical truth:

- search by message substring
- filter by agent or status
- narrow to a project or widen to a broader scope

#### `list_projects`

Use this when you want the project inventory surface instead of a raw log slice.

Depending on runtime and available registry data, this can surface:

- lifecycle timestamps
- entry and file counters
- staleness buckets such as `fresh`, `warming`, `stale`, and `frozen`
- doc-health hints such as `doc_drift_suspected` and `drift_score`

### Governed document tools

#### `manage_docs`

This is the main managed-doc surface, and it is far more than create/edit. It is a
governed-document engine with **28 actions**: 8 primary write/edit actions plus a
20-action "governance engine" for discovery, quality gating, scans, and safe
maintenance.

**Primary write/edit actions:**

- `create` — scaffold a new doc (a template, *not* a finished doc — always follow
  with `replace_section`)
- `replace_section` — fill a scaffold section by its anchor ID
- `apply_patch` — context-anchored surgical edit (preferred for existing content;
  survives line drift)
- `replace_range` — replace an explicit line span
- `replace_text` — find/replace
- `append` — append content
- `status_update` — mark a checklist item done with proof (checklist-only)
- `frontmatter_update` — narrative-doc frontmatter/status edits

The key idea is that Scribe does not treat project docs as loose markdown blobs. It gives them stable editable structure, including anchor IDs such as:

```md
<!-- ID: problem_statement -->
<!-- ID: phase_0 -->
```

That is what makes later updates more reliable than heading-text guesswork.

**The governance engine (the actions most people never discover):**

- *Discovery* — `list_sections`, `list_checklist_items`, `search`
- *Quality gating* — `quality_check` (structured `SCF_*` warnings: codes, severity,
  blocking status, locations, suggested repairs), `quality_handoff_check`,
  `scaffold_quality_check`. These make "no scaffold residue ships" an enforceable
  tool call, not just a convention.
- *Health & topology* — `project_health` (inspect the recent doc surface before
  mutating), `topology_scan` (typed cross-doc edges), `metadata_scan`
- *Safe maintenance* — `metadata_repair`, `stale_cleanup_scan`, `generate_toc`,
  `normalize_headers`, `validate_crosslinks` (find broken cross-references),
  `rehome_doc` (move a managed doc to its canonical location without losing Scribe
  registration — never use shell `mv`/`cp` on a managed doc)
- *Reporting & batch* — `apply_global_changelog`, `preview_reconciliation`,
  `regenerate_intelligence_exports`, `ingestion_manifest_inspect`, `batch` (run
  several managed-doc operations in one call)

### File and search tools

#### `read_file`

Repo-safe file reads — and a lightweight code-intelligence tool. Always start with
`scan_only` (cheapest), then read only the lines you need.

**Modes:**

- `scan_only` (default) — structure (classes/functions with line numbers) + imports,
  no content
- `line_range` — an exact line span, the targeted follow-up to a scan
- `chunk` / `page` — walk a large file in bounded pieces
- `search` — find content within one file, with `search_mode` regex|literal|smart|
  fuzzy (auto-inferred when unset; `fuzzy_threshold` tunes fuzzy matching) and
  `context_lines`
- `full_stream` / `full` — the whole file, only when you genuinely need it

**Advanced scan flags (with `scan_only`):**

- `include_dependencies=True` — attach the file's import dependency graph
- `include_impact=True` — attach impact-radius / blast-radius analysis (requires
  `include_dependencies=True`)
- `structure_filter="<regex>"` — filter the scanned classes/functions by name
- `allow_outside_repo=True` — read a file outside the repo root (the security
  denylist still applies) — needed for cross-repo reads

Together these turn `read_file` into a dependency- and impact-analysis tool, not just
a pager.

#### `search`

Cross-file search under the repo boundary.

#### `edit_file`

Safe exact-string replacement with dry-run support.

### Diagnostics

#### `scribe_doctor`

Use this when the environment, config, or runtime posture looks suspicious.

#### Reminder and drift governance

Scribe can track more than "did someone append a log line." The runtime also computes project and doc-health signals such as:

- `days_since_last_entry`
- `days_since_last_access`
- `staleness_level`
- `activity_score`
- `doc_drift_days_since_update`
- `drift_score`

Those signals matter because they let you ask "is this project healthy?" instead of only "does this file exist?"

## Runtime modes in practice

### PostgreSQL-backed mode

This is the normal shared/team posture and the recommended public runtime path.

```bash
export SCRIBE_STORAGE_BACKEND=postgres
export SCRIBE_DB_URL="postgresql://user:example-password@host:5432/scribe"
```

### Standalone SQLite mode

This is the easiest local-only path for demos and one-user experimentation.

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
export SCRIBE_DB_PATH=".scribe/state/scribe.db"
```

### Authenticated remote/client mode

This is internal compatibility only for this release line. `internal-remote` is advanced/default-off and must be explicitly allowed via install profile controls.

```bash
export SCRIBE_MODE=client
export SCRIBE_REMOTE_URL="https://your-scribe-endpoint.example"
export SCRIBE_REMOTE_AUTH_TOKEN="replace-with-your-token"
```

## Configuration reference

### Core runtime variables

| Variable | Required | Description |
| --- | --- | --- |
| `SCRIBE_STORAGE_BACKEND` | No | `postgres` by default, or `sqlite` in standalone mode |
| `SCRIBE_DB_URL` | Postgres mode | Postgres connection URL |
| `SCRIBE_DB_PATH` | Standalone SQLite | SQLite database path |
| `SCRIBE_MODE` | No | `auto`, `server`, `client`, or `standalone` |
| `SCRIBE_REMOTE_URL` | Client mode | Remote service root URL |
| `SCRIBE_REMOTE_AUTH_TOKEN` | Client mode | Auth token for remote client mode |
| `SCRIBE_RELEASE_PROFILE` | No | `public` fail-closes remote/client; `internal` allows compatibility behavior |

### Compatibility aliases

| Alias | Canonical variable |
| --- | --- |
| `SCRIBE_SQLITE_PATH` | `SCRIBE_DB_PATH` |
| `SCRIBE_DB_SCHEMA` | `SCRIBE_POSTGRES_SCHEMA` |

## Troubleshooting

### "No active project" errors

Run `set_project` first.

### I can install Scribe, but I do not know what to do next

Do not start by reading every reference doc. Start with:

1. [INSTALL_AND_BOOTSTRAP.md](INSTALL_AND_BOOTSTRAP.md)
2. [TOUR.md](TOUR.md)
3. one real `set_project` call in a test repo

### Empty or incomplete query results

- verify you are pointed at the intended project
- widen filters in `query_entries`
- check status or time-range filters

### Connection errors in remote mode

- verify `SCRIBE_REMOTE_URL` points to the service root and `<root>/health` is reachable
- verify the auth token value
- run `scribe_doctor`

## Related docs

- [INSTALL_AND_BOOTSTRAP.md](INSTALL_AND_BOOTSTRAP.md)
- [TOUR.md](TOUR.md)
- [mcp_server_guide.md](mcp_server_guide.md)
- [REMOTE_CLIENT.md](REMOTE_CLIENT.md)
- [TEMPLATE_VARIABLES.md](TEMPLATE_VARIABLES.md)
- [whitepapers/scribe_mcp_whitepaper.md](whitepapers/scribe_mcp_whitepaper.md)
