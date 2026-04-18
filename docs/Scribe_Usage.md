# Scribe MCP Usage Guide (v2.5)

Version: 2.5  
Updated: 2026-04-18

## Overview

Scribe MCP is the execution record and documentation governance layer for agent-driven software work.
This guide explains day-to-day usage of Scribe tools and runtime posture.

For canonical setup and onboarding, use [Install and Bootstrap](INSTALL_AND_BOOTSTRAP.md).

## Table of contents

1. [What Scribe is for](#what-scribe-is-for)
2. [Install and bootstrap](#install-and-bootstrap)
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
- explicit runtime posture controls (Postgres default, standalone SQLite opt-in)

## Install and bootstrap

1. Install:

```bash
pip install scribe-mcp
```

2. Validate CLI availability:

```bash
scribe --help
scribe-server --help
```

3. Complete onboarding with the canonical guide:

- [Install and Bootstrap](INSTALL_AND_BOOTSTRAP.md)

## Core workflow

The standard operating loop:

1. Set project context with `set_project`.
2. Read existing history with `read_recent` or `query_entries`.
3. Perform work and log outcomes with `append_entry`.
4. Update governed docs with `manage_docs` when plans/specs/checklists change.
5. Use `read_file`, `search`, and `edit_file` for targeted operations.
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

#### `read_recent`

Read recent project log entries.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `agent` | string | Yes | — | Agent identity |
| `project` | string | No | active project | Project override |
| `limit` / `n` | string | No | `10` | Number of entries |
| `format` | string | No | `readable` | Output format |

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

### File and search operations

#### `read_file`

Repository-safe file reader with multiple modes.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `agent` | string | Yes | — | Agent identity |
| `path` | string | Yes | — | File path |
| `mode` | string | No | `full_stream` | `scan_only`, `line_range`, `search`, etc. |
| `start_line`/`end_line` | int | Mode-dependent | — | Line bounds for targeted reads |

#### `search`

Cross-file search with literal or regex matching.

#### `edit_file`

Safe exact-string replacement with dry-run support.

### Diagnostics

#### `scribe_doctor`

Check runtime/config health for the current environment.

## Storage and runtime modes

### PostgreSQL-backed mode (default posture)

Postgres is the default backend when `SCRIBE_STORAGE_BACKEND` is unset.
Use Postgres with `SCRIBE_DB_URL` for server/runtime posture.

```bash
export SCRIBE_STORAGE_BACKEND=postgres
export SCRIBE_DB_URL="postgresql://user:pass@host:5432/scribe"
```

### Standalone SQLite mode (explicit local-only opt-in)

SQLite is supported when you explicitly run standalone mode.

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
# Optional path override:
# export SCRIBE_DB_PATH=".scribe/scribe.db"
```

### Authenticated remote/client mode (internal compatibility only)

Remote/client mode is excluded by `SCRIBE_RELEASE_PROFILE=public` in this release line.
When used internally, `SCRIBE_REMOTE_URL` is the service root URL.
Mode detection probes `<root>/health`; SSE transport connects at `<root>/sse`.

```bash
export SCRIBE_MODE=client
export SCRIBE_REMOTE_URL="https://your-scribe-endpoint.example"
export SCRIBE_REMOTE_AUTH_TOKEN="replace-with-your-token"
```

## Configuration reference

### Core runtime variables

| Variable | Required | Description |
|---|---|---|
| `SCRIBE_STORAGE_BACKEND` | No | `postgres` (default) or `sqlite` (standalone only) |
| `SCRIBE_DB_PATH` | No | SQLite path override for standalone mode |
| `SCRIBE_DB_URL` | Server/Postgres mode | Postgres connection URL |
| `SCRIBE_POSTGRES_SCHEMA` | No | Postgres schema override |
| `SCRIBE_MODE` | No | `auto` (default), `server`, `client`, `standalone` |
| `SCRIBE_REMOTE_URL` | Client mode | Remote service root URL; health probe uses `/health` |
| `SCRIBE_REMOTE_AUTH_TOKEN` | Client mode | Authentication token for remote client auth |
| `SCRIBE_RELEASE_PROFILE` | No | `public` fail-closes remote/client; `internal` allows compatibility behavior |

### Compatibility aliases

| Alias | Canonical variable |
|---|---|
| `SCRIBE_SQLITE_PATH` | `SCRIBE_DB_PATH` |
| `SCRIBE_DB_SCHEMA` | `SCRIBE_POSTGRES_SCHEMA` |

## Troubleshooting

### "No active project" errors

Set project context first with `set_project`.

### Empty or incomplete query results

- verify you are pointed at the intended project
- widen filters in `query_entries`
- check time-range and status/category filters

### Connection errors in remote mode

- verify `SCRIBE_REMOTE_URL` points to service root and `<root>/health` is reachable
- verify auth token value and server-side acceptance
- run `scribe_doctor` for environment diagnostics

## Related docs

- [Install and Bootstrap](INSTALL_AND_BOOTSTRAP.md)
- [MCP Server Guide](mcp_server_guide.md)
- [Remote Client Contract](REMOTE_CLIENT.md)
- [Template Variables Reference](TEMPLATE_VARIABLES.md)
- [Scribe MCP Whitepaper](whitepapers/scribe_mcp_whitepaper.md)
