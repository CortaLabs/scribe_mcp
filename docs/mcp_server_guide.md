# MCP server guide

Release line: `2.7.1`
Updated: `2026-06-16`

This guide shows how to run Scribe as an MCP server for hosts such as Codex or Claude-compatible clients.

If you have not installed or bootstrapped Scribe yet, start with [INSTALL_AND_BOOTSTRAP.md](INSTALL_AND_BOOTSTRAP.md).

## The short version

The usual public entry point is:

```bash
scribe-server
```

For most real installs, that means:

- install `scribe-mcp`
- run `scribe install` (preview) and then explicit commit when ready
- load the resulting `.env`
- point your MCP host at `scribe-server`

The package also ships a broader operational surface than just one stdio entry point:

- `scribe-server` for stdio MCP
- `scribe-server-sse` for SSE transport
- `scribe_doctor` and startup probes for diagnostics
- bundled plugin assets under `plugins/` plus `scribe plugins project-codex` for Codex projection
- write-barrier protected Postgres backup/restore helpers for Scribe-owned maintenance windows

## Quick host examples

### Generic `mcp.json`

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

### Codex CLI

```bash
codex mcp add scribe \
  --env SCRIBE_STORAGE_BACKEND=postgres \
  --env SCRIBE_DB_URL=postgresql://scribe_app:pass@127.0.0.1:5432/scribe \
  -- scribe-server
```

### Codex projection path

If you want Scribe's bundled Codex plugin projected into native Codex config surfaces:

```bash
scribe install --commit --yes --project-codex
```

Projection is explicit opt-in and is not part of base install preview/commit unless you pass `--project-codex`.

## Runtime modes

Scribe supports several runtime postures, but they are not equally important for public users.

| Mode | Status | What it is for |
| --- | --- | --- |
| Local/core Postgres runtime | Default and recommended | The main public MCP-server posture |
| Explicit standalone SQLite | Supported local-only opt-in | Small local demos or one-user experimentation |
| Authenticated remote/client runtime | Internal compatibility only | Managed internal service access |
| Open unauthenticated internet exposure | Unsupported | Not a supported deployment posture |

## Environment variables you will care about

| Variable | Required | Typical value | Purpose |
| --- | --- | --- | --- |
| `SCRIBE_STORAGE_BACKEND` | Optional | `postgres` or `sqlite` | Select storage backend |
| `SCRIBE_DB_URL` | Required for Postgres | `postgresql://...` | Postgres connection string |
| `SCRIBE_DB_PATH` | Standalone SQLite only | `/path/to/.scribe/state/scribe.db` | SQLite database path |
| `SCRIBE_REMOTE_URL` | Client mode | `https://...` | Remote Scribe service root |
| `SCRIBE_REMOTE_AUTH_TOKEN` | Client mode | token string | Remote client auth token |

`SCRIBE_ROOT` can still be useful in some setups, but it is not the most important thing for new users to learn first. The key decision is runtime posture plus storage configuration.

## A good first-run verification

After configuring the environment:

1. start `scribe-server`
2. connect your MCP host
3. run one real project-binding call such as `set_project`
4. verify that the governed docs scaffold and progress log appear under `.scribe/docs/dev_plans/<project>/`
5. verify that project inventory and health surfaces respond the way you expect

That is a stronger proof than just checking that the process launches.

Good follow-up checks include:

- `list_projects` for the project inventory surface
- `read_recent` for immediate context rehydration
- `manage_docs` / `project_health` to confirm the governed-doc surface is visible
- `manage_docs(action="quality_check", metadata={"quality": {"bulk": true}}, dry_run=True)` to get Atlas-style project quality summaries, per-doc results, grouped warnings, and ranked agent actions

## Remote/client naming

For this release line, the public naming story is:

- `SCRIBE_REMOTE_URL`
- `SCRIBE_REMOTE_AUTH_TOKEN`
- `SCRIBE_TRANSPORT_AUTH_TOKEN` for server-side transport enforcement

Exported remote transport blocks local operator-only Scribe tools unless the tool metadata explicitly marks the tool as remote-invokable. Treat remote/client use as internal compatibility unless the deployment has its own reviewed trust boundary.

Release-governance reminder for operators: missing accepted changelog coverage for the active package version raises `SCF_CHANGELOG_CURRENT_VERSION_MISSING` through `manage_docs` quality/readiness flows (`quality_check`, reminders, `project_health`) until coverage and reconciliation proof are complete.

Compatibility aliases may exist, but these are the names public docs should lead with.

## Troubleshooting

### `scribe-server` command not found

Cause: package not installed in the active environment.

Fix:

```bash
pip install scribe-mcp
```

### Server starts but Postgres connection fails

Cause: invalid `SCRIBE_DB_URL`, unreachable database, or incomplete bootstrap.

Fix:

- rerun `scribe install` for preview, then `scribe install --commit` when ready
- verify the connection string
- verify local network/database access

### SQLite path errors

Cause: `SCRIBE_DB_PATH` points at a missing or non-writable parent directory.

Fix: choose a writable path under your project and retry.

### Remote auth failures

Cause: missing or invalid auth token.

Fix: verify `SCRIBE_REMOTE_AUTH_TOKEN` on the client and the matching server-side token configuration.

### You installed Scribe, but you still want the product tour

Cause: this guide is about wiring a host, not showing the day-to-day MCP loop.

Fix: start with [TOUR.md](TOUR.md), then come back here once you are ready to wire a real host.

## Related docs

- [INSTALL_AND_BOOTSTRAP.md](INSTALL_AND_BOOTSTRAP.md)
- [TOUR.md](TOUR.md)
- [Scribe_Usage.md](Scribe_Usage.md)
- [REMOTE_CLIENT.md](REMOTE_CLIENT.md)
- [COMPATIBILITY_MATRIX.md](COMPATIBILITY_MATRIX.md)
- [RELEASE_SURFACE.md](RELEASE_SURFACE.md)
