# Global Deployment Guide

Last updated: **2026-04-08**  
Baseline: **v2.5 compatibility baseline**

## What This Guide Is For

This guide explains how to deploy **one shared Scribe MCP installation** that multiple repositories can use.

Use this guide when you are setting up Scribe as a reusable service endpoint (local/shared host or managed private network), not when doing a single-repo local quickstart.

For local-only first run, start with [README.md](../README.md).

## Deployment Posture

Scribe supports these runtime postures:

| Posture | Status | Use case |
| --- | --- | --- |
| Local/core runtime | Default and recommended | Local development and most day-to-day MCP usage |
| Authenticated remote/client runtime | Internal-only compatibility posture | Not part of the initial public release profile |
| Open unauthenticated internet exposure | Unsupported | Not a supported security posture |

Remote/client mode is excluded from the initial public release profile. It remains internal compatibility only via `SCRIBE_RELEASE_PROFILE=internal`.

## Install Once (Package-First)

Install from PyPI on the host that will run Scribe:

```bash
pip install scribe-mcp
```

Verify binaries:

```bash
scribe --help
scribe-server --help
```

## Run the Server

Minimal local/core run:

```bash
scribe-server
```

This starts the MCP server with the default local/core behavior.

## Configure MCP Clients

Use `scribe-server` as the command in your MCP client config.

Example (`mcp.json` style):

```json
{
  "mcpServers": {
    "scribe": {
      "command": "scribe-server",
      "env": {
        "SCRIBE_ROOT": "/absolute/path/to/project",
        "SCRIBE_STORAGE_BACKEND": "sqlite",
        "SCRIBE_DB_PATH": "/absolute/path/to/project/.scribe/state/scribe.db"
      }
    }
  }
}
```

See full examples:
- [docs/examples/mcp.json.example](examples/mcp.json.example)
- [docs/examples/opencode.json.example](examples/opencode.json.example)

## Internal-Only Remote/Client Compatibility

Remote/client mode is not supported in `SCRIBE_RELEASE_PROFILE=public`. For internal compatibility testing only, set:

```bash
export SCRIBE_REMOTE_URL="https://your-scribe-endpoint.example"
export SCRIBE_REMOTE_AUTH_TOKEN="replace-with-your-token"
```

Server-side deployments validate tokens using transport auth settings (see [REMOTE_CLIENT.md](REMOTE_CLIENT.md)).

Important boundaries:
- Remote mode is opt-in.
- Broad bind/public exposure without strong auth and private network controls is not supported.
- Reachability alone does not make a deployment supported.

## Storage Choices

Use the backend that matches your runtime:

- `sqlite`: default, local-first, lowest setup cost
- `postgres`: optional for shared/centralized persistence

If you choose Postgres, provide a valid `SCRIBE_DB_URL` in your server environment.

## Operational Checklist

Before sharing a deployment with teams:

1. Confirm package install uses `scribe-mcp` from PyPI.
2. Confirm `scribe-server` starts cleanly.
3. Confirm client can connect with your selected env vars.
4. If remote mode is enabled, verify auth token enforcement.
5. Confirm posture matches supported boundary (local/core or authenticated private remote).

## Related Documentation

- [README.md](../README.md)
- [MCP server guide](mcp_server_guide.md)
- [Remote client contract](REMOTE_CLIENT.md)
- [Compatibility matrix](COMPATIBILITY_MATRIX.md)
- [Release surface](RELEASE_SURFACE.md)
