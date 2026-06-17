# Install and bootstrap

Release line: `2.8.0`
Updated: `2026-06-17`

This is the canonical onboarding guide for public users of `scribe-mcp`.

If you want the short product tour first, read [TOUR.md](TOUR.md). If you want the MCP-host setup details, read [mcp_server_guide.md](mcp_server_guide.md).

This release line includes faster repeated project binding, queryable runtime telemetry, append-entry phase timing, physical/logical reconciliation diagnostics, JSON probe output, same-server root comparison tooling, and background telemetry cleanup for local probes. It also includes the document topology foundation plus agent-ready quality governance: managed docs carry canonical lifecycle metadata, typed deterministic edges, quality-gated ready/complete transitions, topology/metadata scan actions, safe repair modes, stale cleanup recommendations, handoff checks, Atlas bulk quality checks, and sanitized downstream export manifests.
It also includes release-governance and operator-safety enforcement: missing accepted changelog coverage for the active `pyproject.toml` version raises `SCF_CHANGELOG_CURRENT_VERSION_MISSING` through `quality_check`, reminders, and managed-doc `project_health`; Scribe-owned write barriers and remote operator-tool blocking protect mutation and transport boundaries.

## Which path should you use?

Choose the smallest path that matches what you are trying to do:

| Goal | Recommended path |
| --- | --- |
| Real install for day-to-day use | Install wizard with `scribe install` (preview first, then explicit commit) |
| Local-only demo or single-user experiment | Explicit standalone SQLite |
| Connect Scribe to Codex after local setup | Run `scribe install --commit --yes --project-codex` |
| Use a remote/client deployment | Internal-only posture for this release line |

## 1. Install the package

```bash
pip install scribe-mcp
```

The Postgres driver (`asyncpg`) is already a core dependency, so the base install is Postgres-capable out of the box. The `[postgres]` extra is available as an explicit alias if you prefer to make the Postgres intent visible in your dependency list:

```bash
pip install 'scribe-mcp[postgres]'
```

Sanity-check the public CLI surface:

```bash
scribe --help
scribe install --help
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

## 2. Recommended path: install wizard

Scribe is local-first and repo-scoped by default. Start with preview mode:

```bash
scribe install
```

Preview mode is default and performs no DB mutation, no `.env` mutation, and no projection.

The bootstrap flow is designed to handle the setup work that most users do not want to do by hand:

- create or update database roles
- provision the Scribe application database
- apply schema grants
- write or update runtime keys in `.env`
- generate secure app/admin credentials when needed
- provision required extensions and schema ownership for the application runtime

Useful variants:

```bash
scribe install --profile local-postgres
scribe install --profile sqlite-eval
scribe install --profile existing-postgres
```

Apply mutations only with explicit commit:

```bash
scribe install --commit
```

Non-interactive commit requires the approved confirmation path:

```bash
scribe install --commit --yes
```

Advanced profile behavior:

- `internal-remote` is advanced and default-off
- to preview it, pass both `--profile internal-remote` and `--allow-advanced-profile`
- standard install remains local-first/repo-scoped

After successful commit, the wizard runs post-install diagnostics/readiness checks automatically.

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
scribe install --commit --yes --project-codex
```

Codex projection is explicit opt-in only and runs after core install commit verification. Base install never touches `CODEX_HOME` unless you explicitly request projection.

This is the supported projection flow for this release line.

As of the 2.8.0 line, the Codex and Claude plugin bundles ship inside the installed package: they are vendored into the wheel via package-data (a byte-identical copy of the repo `plugins/` tree under `plugins_bundle/`). `resolve_codex_plugin_root()` prefers that packaged bundle, so a plain `pip install scribe-mcp` followed by `scribe install --commit --yes --project-codex` projects the assets into your Codex surfaces with no clone required. The repo `plugins/` tree remains the canonical source for development and is used as a fallback when you run the projection command from a cloned checkout.

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
