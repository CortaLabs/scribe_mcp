# MCP Server Guide

Last updated: **2026-04-08**  
Baseline: **v2.5 compatibility baseline**

## What This Guide Is For

This guide explains how to run and configure **Scribe MCP as an MCP server** for client tools such as Codex or Claude-compatible hosts.

This is a product usage guide for Scribe, not a generic tutorial for building arbitrary MCP servers from scratch.

## Quick Start

Install from PyPI:

```bash
pip install scribe-mcp
```

Validate entry points:

```bash
scribe --help
scribe-server --help
```

Run server:

```bash
scribe-server
```

## Runtime Modes

Server and public-release runtime posture is Postgres-only. SQLite is supported only as an explicit standalone local fallback.

| Mode | Status | Description |
| --- | --- | --- |
| Local/core runtime (Postgres) | Default and recommended | Runs Scribe locally for standard MCP usage; this is the required backend for server/public-release runtime |
| Authenticated remote/client runtime | Supported optional posture | Client connects to managed remote Scribe endpoint |
| Explicit standalone SQLite | Supported (opt-in local fallback) | Local-only usage when `SCRIBE_MODE=standalone` and `SCRIBE_STORAGE_BACKEND=sqlite` are set |
| Open unauthenticated internet exposure | Unsupported | Not a supported deployment posture |

## Client Configuration

Use `scribe-server` in your MCP client config.

### Example: Generic `mcp.json`

```json
{
  "mcpServers": {
    "scribe": {
      "command": "scribe-server",
      "env": {
        "SCRIBE_ROOT": "/absolute/path/to/project",
        "SCRIBE_STORAGE_BACKEND": "postgres",
        "SCRIBE_DB_URL": "postgresql://scribe_app:pass@127.0.0.1:5432/scribe"
      }
    }
  }
}
```

### Example: Codex CLI

```bash
codex mcp add scribe \
  --env SCRIBE_ROOT=/absolute/path/to/project \
  --env SCRIBE_STORAGE_BACKEND=postgres \
  --env SCRIBE_DB_URL=postgresql://scribe_app:pass@127.0.0.1:5432/scribe \
  -- scribe-server
```

## Core Environment Variables

| Variable | Required | Typical value | Purpose |
| --- | --- | --- | --- |
| `SCRIBE_ROOT` | Recommended | `/absolute/path/to/project` | Project root Scribe operates against |
| `SCRIBE_STORAGE_BACKEND` | Optional | `postgres` (server/default) or `sqlite` (standalone local-only) | Select storage backend |
| `SCRIBE_DB_PATH` | Optional (sqlite standalone local-only) | `/path/to/.scribe/state/scribe.db` | SQLite database path |
| `SCRIBE_DB_URL` | Required for postgres | `postgresql://...` | Postgres connection string |
| `SCRIBE_REMOTE_URL` | Required in remote client mode | `https://...` | Remote Scribe endpoint |
| `SCRIBE_REMOTE_AUTH_TOKEN` | Required in remote client mode | token string | Client bearer token |

## Remote Client Naming (Public Canonical)

For v2.5 public docs, use:
- `SCRIBE_REMOTE_URL`
- `SCRIBE_REMOTE_AUTH_TOKEN`
- `SCRIBE_TRANSPORT_AUTH_TOKEN` (server-side enforcement variable)

Compatibility aliases may exist for mixed environments, but they are not the primary public naming story.

## Verification

After configuration:

1. Start `scribe-server` with your selected env vars.
2. Confirm MCP client can initialize the server process.
3. Run one simple tool call (for example project set/read flow) from the client.
4. If remote mode is enabled, verify requests fail when auth token is missing or invalid.

## Troubleshooting (Public-Scope)

### Server command not found

Cause: package not installed in current environment.  
Fix:

```bash
pip install scribe-mcp
```

### SQLite path errors

Cause: `SCRIBE_DB_PATH` points to a non-writable or missing parent directory.  
Fix: choose a writable path under your project and retry.

### Postgres connection failures

Cause: invalid `SCRIBE_DB_URL` or unreachable database.  
Fix: verify URL, credentials, and network path.

### Remote auth failures

Cause: token mismatch or missing auth variables.  
Fix: set `SCRIBE_REMOTE_AUTH_TOKEN` on client and corresponding server token configuration.

## Related Documentation

- [README.md](../README.md)
- [Global deployment guide](GLOBAL_DEPLOYMENT_GUIDE.md)
- [Remote client contract](REMOTE_CLIENT.md)
- [Compatibility matrix](COMPATIBILITY_MATRIX.md)
- [Release surface](RELEASE_SURFACE.md)
