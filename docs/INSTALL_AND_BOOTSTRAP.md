# Install and bootstrap

Release line: `2.2.11`  
Updated: `2026-04-18`

This is the canonical onboarding guide for public users of `scribe-mcp`.

If you want the short product tour first, read [TOUR.md](TOUR.md). If you want the MCP-host setup details, read [mcp_server_guide.md](mcp_server_guide.md).

## Which path should you use?

Choose the smallest path that matches what you are trying to do:

| Goal | Recommended path |
| --- | --- |
| Real install for day-to-day use | Bootstrap Postgres with `scribe bootstrap` |
| Local-only demo or single-user experiment | Explicit standalone SQLite |
| Connect Scribe to Codex after local setup | Run `scribe plugins project-codex` |
| Use a remote/client deployment | Internal-only posture for this release line |

## 1. Install the package

```bash
pip install scribe-mcp
```

Sanity-check the public CLI surface:

```bash
scribe --help
scribe bootstrap --help
scribe-server --help
```

Those commands are the right first checks after installation. You do not need to guess entry points or go spelunking through `pyproject.toml`.

Scribe also ships a broader operator toolchain:

- `scribe-bootstrap-postgres`
- `scribe-migrate`
- `scribe-migrate-postgres`
- `scribe-migrate-objects`
- `scribe-backup-postgres`
- `scribe-metrics-postgres`
- `scribe-soak-postgres`
- `scribe-server-sse`

## 2. Recommended path: bootstrap Postgres

Scribe is Postgres-first in normal server/runtime posture. If you want the path that best matches the supported public runtime model, start here:

```bash
scribe bootstrap
```

The bootstrap flow is designed to handle the setup work that most users do not want to do by hand:

- create or update database roles
- provision the Scribe application database
- apply schema grants
- write or update runtime keys in `.env`
- generate secure app/admin credentials when needed
- provision required extensions and schema ownership for the application runtime

Useful variants:

```bash
scribe bootstrap --dry-run
scribe bootstrap --no-interactive --superuser-password '<password>'
```

After bootstrap completes, load the generated environment and start the server:

```bash
set -a
source .env
set +a
scribe-server
```

If you already manage environment variables another way, mirror the values from `.env` into your own secret/config system instead of sourcing the file directly.

## 3. Fast local-only path: standalone SQLite

If you just want to try Scribe on one machine without provisioning Postgres, explicit standalone SQLite is supported:

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
export SCRIBE_DB_PATH=".scribe/state/scribe.db"
scribe-server
```

This is the lightest way to evaluate the CLI and the governed-doc flow, but it is not the recommended shared/team runtime.

If you later decide to move from local SQLite to a shared deployment, the migration commands above are the right bridge rather than a hand-rolled export/import path.

## 4. Create your first governed project

Once the runtime is configured, bind a project to the current repo:

```bash
scribe call set_project \
  --agent demo-agent \
  --repo-root "$PWD" \
  --arg name=demo_docs \
  --arg root="$PWD" \
  --arg format=structured \
  --pretty
```

On a fresh project, this scaffolds the core managed docs:

```text
.scribe/docs/dev_plans/demo_docs/
  ARCHITECTURE_GUIDE.md
  PHASE_PLAN.md
  CHECKLIST.md
  PROGRESS_LOG.md
  DOC_LOG.md
  SECURITY_LOG.md
  BUG_LOG.md
```

That one step shows what Scribe actually does: it gives agent work a repeatable artifact surface.

For a walkthrough of what those files look like and why they matter, read [TOUR.md](TOUR.md).

Once you have a project bound, the next useful checks are:

- `scribe call read_recent ...` to rehydrate context
- `scribe call list_projects ...` to inspect the project inventory surface
- managed-doc health and update workflows such as `manage_docs`

## 5. Connect Scribe to your MCP host

The usual host entry point is:

```bash
scribe-server
```

Generic `mcp.json` example:

```json
{
  "mcpServers": {
    "scribe": {
      "command": "scribe-server",
      "env": {
        "SCRIBE_STORAGE_BACKEND": "postgres",
        "SCRIBE_DB_URL": "postgresql://scribe_app:pass@127.0.0.1:5432/scribe"
      }
    }
  }
}
```

If you want the host-specific details and environment table, use [mcp_server_guide.md](mcp_server_guide.md).

## 6. Codex projection path

If you want the bundled Scribe plugin projected into native Codex surfaces, use the shipped projection command:

```bash
scribe plugins project-codex --repo-root /absolute/path/to/repo
```

Useful flags:

- `--plugin-root` to override the plugin bundle path
- `--codex-home` to target a specific `CODEX_HOME`
- `--config-path` to target a specific Codex `config.toml`

This is the supported projection flow for this release line.

The package also ships bundled plugin assets under `plugins/` for Codex and Claude-oriented setups.

## 7. Remote/client posture

Remote/client is internal compatibility only for this release line.
Public-release posture (`SCRIBE_RELEASE_PROFILE=public`) excludes remote/client startup.

When used internally:

- `SCRIBE_REMOTE_URL` is the service root
- mode detection probes `<root>/health`
- SSE stream transport is `<root>/sse`
- message POST target is `<root>/messages/`

Example internal-only client environment:

```bash
export SCRIBE_MODE=client
export SCRIBE_RELEASE_PROFILE=internal
export SCRIBE_REMOTE_URL="https://scribe.internal.example"
export SCRIBE_REMOTE_AUTH_TOKEN="replace-with-token"
```

## 8. What to read next

- [TOUR.md](TOUR.md)  
  The fastest way to understand the governed-doc workflow.
- [Scribe_Usage.md](Scribe_Usage.md)  
  The day-to-day loop once Scribe is installed.
- [mcp_server_guide.md](mcp_server_guide.md)  
  The MCP-host connection guide.
- [COMPATIBILITY_MATRIX.md](COMPATIBILITY_MATRIX.md)  
  Version pairing and release posture details.
