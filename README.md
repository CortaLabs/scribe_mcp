# Scribe MCP

Scribe MCP is a documentation-governance and execution-record system for agent-driven software work.

This README is a landing page. For install and onboarding truth, use:
- [Install and Bootstrap](docs/INSTALL_AND_BOOTSTRAP.md)

## Overview

Scribe provides:

- persistent audit logging for agent and operator actions
- governed document workflows for architecture, planning, and execution tracking
- consistent file/search/edit tool contracts for automation-safe operations
- a Postgres-first runtime contract with explicit local-only SQLite opt-in

## Runtime posture (public onboarding)

| Posture | Status | Notes |
| --- | --- | --- |
| Postgres runtime | Default and recommended | `SCRIBE_STORAGE_BACKEND` defaults to `postgres`; server/runtime requires `SCRIBE_DB_URL` in server posture |
| Standalone SQLite | Supported, opt-in local-only | Explicitly set `SCRIBE_MODE=standalone` + `SCRIBE_STORAGE_BACKEND=sqlite` |
| Remote/client | Internal compatibility only for this release line | Excluded by `SCRIBE_RELEASE_PROFILE=public` |

## Documentation

Start here for product truth and boundaries:

- [Install and Bootstrap](docs/INSTALL_AND_BOOTSTRAP.md)
- [Compatibility matrix](docs/COMPATIBILITY_MATRIX.md)
- [Release surface](docs/RELEASE_SURFACE.md)
- [Release file map](docs/RELEASE_FILE_MAP.md)

Usage and operator references:

- [Scribe usage guide](docs/Scribe_Usage.md)
- [Remote client contract](docs/REMOTE_CLIENT.md)
- [MCP server guide](docs/mcp_server_guide.md)
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

## License

See [LICENSE](LICENSE).
