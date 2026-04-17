# Scribe MCP Usage Guide (v2.5)

Version: 2.5  
Updated: 2026-04-08

## Overview

Scribe MCP is the execution record and documentation governance layer for agent-driven software work.
This guide explains how to use Scribe as a product: initialize a project, capture work, manage governed docs, and retrieve high-signal history.

This document is for public users integrating Scribe into real projects. It focuses on stable usage patterns and tool contracts.

## Table of contents

1. [What Scribe is for](#what-scribe-is-for)
2. [Quickstart](#quickstart)
3. [Core workflow](#core-workflow)
4. [Tool families](#tool-families)
5. [Storage and runtime modes](#storage-and-runtime-modes)
6. [Configuration reference](#configuration-reference)
7. [Troubleshooting](#troubleshooting)
8. [Related docs](#related-docs)

## What Scribe is for

Use Scribe when you need:

- durable, queryable audit logs for agent and operator activity
- governed document updates for plans, architecture, and execution artifacts
- automation-safe file/search/edit contracts for programmatic workflows
- flexible runtime posture (local-first or authenticated remote)

Scribe is not a generic note app. It is designed for engineering execution that must remain reviewable and reproducible over time.

## Quickstart

### 1. Install

```bash
pip install scribe-mcp
```

### 2. Validate CLI availability

```bash
scribe --help
scribe-server --help
```

### 3. Start local server

```bash
scribe-server
```

### 4. Initialize project context

Every session should start by binding an agent name + project + repo root:

```python
set_project(
  agent="MyAgent",
  name="my_project",
  root="/absolute/path/to/repo"
)
```

### 5. Rehydrate recent context

```python
read_recent(agent="MyAgent", limit="5")
```

### 6. Log meaningful work

```python
append_entry(
  agent="MyAgent",
  status="info",
  message="Started implementation of auth token refresh",
  meta={"area": "auth", "ticket": "AUTH-142"}
)
```

## Core workflow

The standard operating loop:

1. Set project context with `set_project`.
2. Read existing history with `read_recent` or `query_entries`.
3. Perform work and log outcomes with `append_entry`.
4. Update governed docs with `manage_docs` when plans/specs/checklists change.
5. Use `read_file`, `search`, and `edit_file` for targeted code/document operations.
6. Close out with a success/failure log entry.

## Tool families

### Project and session context

#### `set_project`

Bind the active project and repository root for an agent session.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `agent` | string | Yes | — | Agent identity for session isolation |
| `name` | string | No | active/default | Project name |
| `root` | string | Yes (recommended) | repo cwd | Absolute repository root |
| `format` | string | No | `readable` | `readable`, `structured`, or `compact` |

Example:

```python
set_project(agent="MyAgent", name="payments", root="/workspace/payments-api")
```

#### `read_recent`

Read recent project log entries.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `agent` | string | Yes | — | Agent identity |
| `project` | string | No | active project | Project override |
| `limit` / `n` | string | No | `10` | Number of entries |
| `format` | string | No | `readable` | Output format |

Example:

```python
read_recent(agent="MyAgent", limit="10")
```

### Logging and audit trail

#### `append_entry`

Append one or more audit log entries with optional metadata.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `agent` | string | Yes | — | Entry author identity |
| `message` | string | Yes | — | Log message |
| `status` | string | No | `info` | `info`, `success`, `warn`, `error`, etc. |
| `meta` | object/string | No | `{}` | Structured metadata |
| `log_type` | string | No | `progress` | Alternate log stream |

Example:

```python
append_entry(
  agent="MyAgent",
  status="success",
  message="Completed migration validation",
  meta={"migrations": 3, "duration_seconds": 41}
)
```

### Document governance

#### `manage_docs`

Create, update, and patch governed documents.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `agent` | string | Yes | — | Agent identity |
| `action` | string | Yes | — | Operation (`create`, `replace_section`, `status_update`, etc.) |
| `doc_name` | string | Usually | — | Target document key/name |
| `section` | string | Action-dependent | — | Section identifier |
| `content` | string | Action-dependent | — | Replacement/append content |

Common pattern:

```python
manage_docs(agent="MyAgent", action="create", doc_name="PHASE_PLAN")
manage_docs(
  agent="MyAgent",
  action="replace_section",
  doc_name="PHASE_PLAN",
  section="phase_1",
  content="Deliver API contract stabilization and migration tests."
)
```

### File and search operations

#### `read_file`

Repository-safe file reader with multiple modes.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `agent` | string | Yes | — | Agent identity |
| `path` | string | Yes | — | File path |
| `mode` | string | No | `full_stream` | `scan_only`, `line_range`, `search`, etc. |
| `start_line`/`end_line` | int | Mode-dependent | — | Line bounds for targeted reads |

Example:

```python
read_file(agent="MyAgent", path="src/server.py", mode="scan_only")
read_file(agent="MyAgent", path="src/server.py", mode="line_range", start_line=120, end_line=220)
```

#### `search`

Cross-file search with literal or regex matching.

```python
search(agent="MyAgent", pattern="set_project", glob="**/*.py")
```

#### `edit_file`

Safe exact-string replacement with dry-run support.

```python
edit_file(
  agent="MyAgent",
  path="README.md",
  old_string="legacy phrasing",
  new_string="updated phrasing",
  dry_run=True
)
```

### Diagnostics

#### `scribe_doctor`

Check runtime/config health for the current environment.

```python
scribe_doctor(agent="MyAgent")
```

## Storage and runtime modes

### Local mode (default)

Best for most users and local development.

```bash
# Optional explicit setting
export SCRIBE_STORAGE_BACKEND=sqlite
```

### PostgreSQL-backed mode

Best for shared/team deployments requiring centralized persistence.

```bash
export SCRIBE_STORAGE_BACKEND=postgres
export SCRIBE_DB_URL="postgresql://user:pass@host:5432/scribe"
```

### Authenticated remote/client mode

Use when connecting to a managed Scribe endpoint.

```bash
export SCRIBE_MODE=client
export SCRIBE_REMOTE_URL="https://your-scribe-endpoint.example"
export SCRIBE_REMOTE_AUTH_TOKEN="replace-with-your-token"
```

## Configuration reference

### Core runtime variables

| Variable | Required | Description |
|---|---|---|
| `SCRIBE_STORAGE_BACKEND` | No | `sqlite` (default) or `postgres` |
| `SCRIBE_DB_PATH` | No | SQLite database path override |
| `SCRIBE_DB_URL` | Postgres mode | Postgres connection URL |
| `SCRIBE_POSTGRES_SCHEMA` | No | Postgres schema override |
| `SCRIBE_MODE` | Remote mode | Set to `client` for remote runtime |
| `SCRIBE_REMOTE_URL` | Remote mode | Remote Scribe server URL |
| `SCRIBE_REMOTE_AUTH_TOKEN` | Remote mode | Authentication token |

### Compatibility aliases

| Alias | Canonical variable |
|---|---|
| `SCRIBE_SQLITE_PATH` | `SCRIBE_DB_PATH` |
| `SCRIBE_DB_SCHEMA` | `SCRIBE_POSTGRES_SCHEMA` |

## Troubleshooting

### "No active project" errors

Set project context first:

```python
set_project(agent="MyAgent", name="my_project", root="/abs/repo")
```

### Empty or incomplete query results

- verify you are pointed at the intended project
- widen filters in `query_entries`
- check time-range filters and status/category filters

### Connection errors in remote mode

- verify `SCRIBE_REMOTE_URL`
- verify auth token value and server-side acceptance
- run `scribe_doctor` for environment diagnostics

## Related docs

- [MCP Server Guide](mcp_server_guide.md)
- [Remote Client Contract](REMOTE_CLIENT.md)
- [Template Variables Reference](TEMPLATE_VARIABLES.md)
- [Scribe MCP Whitepaper](whitepapers/scribe_mcp_whitepaper.md)
