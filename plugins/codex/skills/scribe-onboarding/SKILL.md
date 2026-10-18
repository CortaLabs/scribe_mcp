---
name: scribe-onboarding
description: Install Scribe MCP, choose a local storage profile, connect an MCP host, and verify the first project bind
---

# Scribe Onboarding

Use this guide to install and connect Scribe MCP. It covers the package, the recommended PostgreSQL setup, the optional SQLite evaluation path, generic MCP host configuration, and a first project bind. For day-to-day logging and managed documents, continue with [Scribe Integration](../scribe-integration/SKILL.md).

## When to use this guide

- You are setting up `scribe-mcp` on a new machine or repository.
- You need the canonical install command or want to choose between PostgreSQL and SQLite evaluation.
- You are connecting Scribe to an MCP host.
- A server start or project bind failed and you need to check the installation.

If Scribe is installed and the project is already bound, use [Scribe Integration](../scribe-integration/SKILL.md).

## Before you start

- Python 3.11 or newer is available on `PATH` (`python3.11 --version`).
- For the recommended profile, a local or reachable PostgreSQL instance is available.
- You can write to the repository where the install wizard will create its `.env` file.
- Host projection is optional; you only need it when you want Scribe's bundled Codex plugin installed into your Codex configuration.

## Install Scribe

```bash
pip install scribe-mcp
```

To request the documented PostgreSQL extra explicitly:

```bash
pip install 'scribe-mcp[postgres]'
```

Check the installed command surfaces:

```bash
scribe --help
scribe install --help
scribe-server --help
```

## Set up PostgreSQL

The install wizard previews changes by default. Preview the recommended local profile first:

```bash
scribe install
scribe install --profile local-postgres
```

When the preview is correct, apply it with the explicit `--commit` flag:

```bash
# Interactive confirmation
scribe install --profile local-postgres --commit

# Non-interactive setup
scribe install --profile local-postgres --commit --yes
```

The wizard prepares the application role and database, applies required grants and extensions, creates application credentials, and writes a repository `.env`. After a successful commit it runs readiness checks.

Choose the profile that matches the database you will use:

| Profile | Use |
| --- | --- |
| `local-postgres` | Recommended for a local PostgreSQL-backed runtime. |
| `existing-postgres` | Connect to a PostgreSQL instance you already manage. |
| `sqlite-eval` | Evaluate Scribe on one machine without provisioning PostgreSQL. |

Load the generated environment and start the server:

```bash
set -a
source .env
set +a
scribe-server
```

## Evaluate locally with SQLite

SQLite is an explicit, single-machine evaluation option:

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
export SCRIBE_DB_PATH=".scribe/state/scribe.db"
scribe-server
```

Use PostgreSQL for a shared project runtime. Use Scribe's documented migration commands if you later move an evaluation database.

## Connect an MCP host

A generic `mcp.json` host can start the server with environment values supplied by its own secret or configuration store:

```json
{
  "mcpServers": {
    "scribe": {
      "command": "scribe-server",
      "env": {
        "SCRIBE_STORAGE_BACKEND": "postgres",
        "SCRIBE_DB_URL": "postgresql://scribe_app:password@127.0.0.1:5432/scribe"
      }
    }
  }
}
```

Do not commit credentials in a shared configuration file. Prefer the repository `.env` created by the installer or your host's secret store.

To explicitly project the bundled Scribe plugin into Codex configuration:

```bash
scribe install --commit --yes --project-codex
```

The standard package includes the plugin assets and projection uses those bundled files. The base install does not modify `CODEX_HOME` unless projection is requested.

## Environment values

| Variable | Purpose |
| --- | --- |
| `SCRIBE_STORAGE_BACKEND` | `postgres` for the recommended runtime or `sqlite` for evaluation. |
| `SCRIBE_DB_URL` | PostgreSQL connection string. Supply credentials through a secret store or local `.env`. |
| `SCRIBE_MODE` | Set to `standalone` for local SQLite evaluation. |
| `SCRIBE_DB_PATH` | SQLite database file when `SCRIBE_STORAGE_BACKEND=sqlite`. |

## Verify the first project bind

Start the server using the configured host, then bind a named project and load its recent context:

```python
set_project(
    agent="developer",
    name="example_project",
    root="/path/to/repository",
)
read_recent(agent="developer", limit=5)
```

If the bind succeeds and recent entries return for the intended project, continue with [Scribe Integration](../scribe-integration/SKILL.md) to learn the logging and document workflow. For command details and setup examples, see the [installation guide](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/INSTALL_AND_BOOTSTRAP.md) and [Scribe usage guide](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/Scribe_Usage.md).
