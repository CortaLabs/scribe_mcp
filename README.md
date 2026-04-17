# Scribe MCP

Scribe MCP is a production documentation and audit platform for agent-driven software work.
It gives teams a durable execution record, governed planning artifacts, and tool contracts that
make multi-agent development observable, reviewable, and reproducible.

If your system depends on agents making changes over time, Scribe is the layer that preserves truth.

## Overview

Scribe is designed to solve four hard problems in one package:

- persistent audit logging for agent and operator actions
- governed document workflows for architecture, planning, and execution tracking
- consistent file/search/edit tool contracts for automation-safe operations
- portable runtime modes for local usage and authenticated remote access

This repository ships the public package, public docs, and public plugin bundles needed to run Scribe in real projects.

## Core capabilities

- **Structured audit trail:** project-aware entries with queryable history
- **Governed docs engine:** architecture/phase/checklist/progress workflows with managed updates
- **Operator tooling:** file read/search/edit helpers and diagnostics for day-to-day execution
- **Storage posture:** Postgres-first server/runtime contract with explicit standalone SQLite support
- **Plugin bundles:** ready-to-use Codex and Claude plugin surfaces under `plugins/`

## Install and start

Install from PyPI:

```bash
pip install scribe-mcp
```

Quick sanity check:

```bash
scribe --help
scribe-server --help
```

Minimal local run (Postgres server/runtime):

```bash
export SCRIBE_STORAGE_BACKEND=postgres
export SCRIBE_DB_URL="postgresql://scribe_app:pass@127.0.0.1:5432/scribe"
scribe-server
```

Explicit standalone SQLite run (local-only):

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
scribe-server
```

## Runtime postures

| Posture | Status | Usage |
| --- | --- | --- |
| Postgres server/runtime | Default, recommended, and required for public-release/server usage | Day-to-day usage, local development, managed deployments, and all server/public-release runtime postures |
| Explicit standalone SQLite | Supported (opt-in local fallback) | Standalone local-only usage when `SCRIBE_MODE=standalone` and `SCRIBE_STORAGE_BACKEND=sqlite` are set |
| Authenticated remote/client runtime | Supported | Managed/private deployments that require centralized access |
| Open unauthenticated internet exposure | Unsupported | Not a supported security posture |

For authenticated remote clients:

```bash
export SCRIBE_REMOTE_URL="https://your-scribe-endpoint.example"
export SCRIBE_REMOTE_AUTH_TOKEN="replace-with-your-token"
```

## Documentation index

Start here for product truth and boundaries:

- [Compatibility matrix](docs/COMPATIBILITY_MATRIX.md)
- [Release surface](docs/RELEASE_SURFACE.md)
- [Release file map](docs/RELEASE_FILE_MAP.md)

Usage and operator references:

- [Scribe usage guide](docs/Scribe_Usage.md)
- [MCP server guide](docs/mcp_server_guide.md)
- [Remote client contract](docs/REMOTE_CLIENT.md)
- [Bridge development](docs/BRIDGE_DEVELOPMENT.md)
- [Template variables reference](docs/TEMPLATE_VARIABLES.md)

Deployment and environment setup:

- [Global deployment guide](docs/GLOBAL_DEPLOYMENT_GUIDE.md)
- [Deployment README](deploy/README.md)

Examples:

- [mcp.json example](docs/examples/mcp.json.example)
- [opencode.json example](docs/examples/opencode.json.example)

Background and context:

- [Scribe MCP whitepaper](docs/whitepapers/scribe_mcp_whitepaper.md)

## Plugins and integrations

Public plugin bundles are included in this repository:

- `plugins/codex/`
- `plugins/claude/`

These are packaged as public integration surfaces for downstream users.

## License

See [LICENSE](LICENSE).
