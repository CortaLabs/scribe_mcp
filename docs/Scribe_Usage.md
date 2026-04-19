# Scribe MCP usage guide

Release line: `2.2.11`  
Updated: `2026-04-18`

This guide is about day-to-day usage once Scribe is installed.

If you have not installed or bootstrapped Scribe yet, start with [INSTALL_AND_BOOTSTRAP.md](INSTALL_AND_BOOTSTRAP.md). If you want the fast MCP-first tour first, start with [TOUR.md](TOUR.md).

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

This is the main managed-doc surface.

Typical operations:

- `create`
- `list_sections`
- `replace_section`
- `apply_patch`
- `status_update`

The key idea is that Scribe does not treat project docs as loose markdown blobs. It gives them stable editable structure, including anchor IDs such as:

```md
<!-- ID: problem_statement -->
<!-- ID: phase_0 -->
```

That is what makes later updates more reliable than heading-text guesswork.

Scribe also exposes health-oriented managed-doc actions such as `project_health`, which are useful when you want to inspect the recent doc surface for the active project before mutating it.

### File and search tools

#### `read_file`

Repo-safe file reads with modes such as:

- `scan_only`
- `line_range`
- `search`
- `full_stream`

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
export SCRIBE_DB_URL="postgresql://user:pass@host:5432/scribe"
```

### Standalone SQLite mode

This is the easiest local-only path for demos and one-user experimentation.

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
export SCRIBE_DB_PATH=".scribe/state/scribe.db"
```

### Authenticated remote/client mode

This is internal compatibility only for this release line.

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
