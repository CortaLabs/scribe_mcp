# Scribe MCP

Scribe MCP is Corta Labs' documentation and audit subsystem for agent-driven development. It provides structured logs, governed planning documents, checklist/progress workflows, release-safe examples, and file-reading/search/editing tools for operators and agents.

> **Release note — 2026-04-05:** this README reflects the frozen **2.5 compatibility-release** documentation wave. The artifact-backed package matrix for this wave is `scribe-mcp 2.2`, optional `scribe-council 2.2`, and synchronized `council_mcp 2.0.0`. **`v3` is explicitly deferred** to the later structural/refinement release.

## Table of contents

- [What Scribe is](#what-scribe-is)
- [Supported install profiles](#supported-install-profiles)
- [Quickstart](#quickstart)
- [Supported runtime postures](#supported-runtime-postures)
- [What `scribe-council` is](#what-scribe-council-is)
- [Release docs and navigation](#release-docs-and-navigation)
- [Deployment](#deployment)
- [License](#license)

## What Scribe is

Scribe is the persistent documentation and audit layer that sits beside agent runtimes:

- **Local/core by default** for normal usage
- **Tracked docs and examples** for release-safe guidance
- **Governed planning surfaces** for architecture, phase plans, checklists, and progress logs
- **Optional authenticated remote/client access** for operators who intentionally deploy Scribe as a managed service

If you are deciding what is public contract versus workstation-local state, start with:

- [`docs/COMPATIBILITY_MATRIX.md`](docs/COMPATIBILITY_MATRIX.md)
- [`docs/RELEASE_SURFACE.md`](docs/RELEASE_SURFACE.md)
- [`docs/RELEASE_FILE_MAP.md`](docs/RELEASE_FILE_MAP.md)

## Supported install profiles

| Use case | Install | Notes |
| --- | --- | --- |
| Standard Scribe usage | `pip install scribe-mcp` | Default local/core posture. Installs CLI entry points including `scribe` and `scribe-server`. |
| Optional council/template assets | `pip install scribe-mcp scribe-council` | Add only when you also need Scribe's optional `council.templates` provider and template payload. |
| Council ↔ Scribe compatibility review | See [`docs/COMPATIBILITY_MATRIX.md`](docs/COMPATIBILITY_MATRIX.md) | The frozen compatibility set for this wave is `scribe-mcp 2.2`, optional `scribe-council 2.2`, and `council_mcp 2.0.0`. |

## Quickstart

Minimal local/core setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install scribe-mcp

scribe --help
scribe-server --help
```

Optional extension install when you need council/template assets:

```bash
pip install scribe-council
```

## Supported runtime postures

| Posture | Status | Notes |
| --- | --- | --- |
| Local/core stdio or loopback-local usage | **Default / supported** | This is the primary public story for Scribe. |
| Authenticated remote/client usage on a managed private mesh or Tailscale-style network | **Supported optional posture** | Use only as an intentional operator choice with auth in place. |
| Casual public exposure | **Unsupported** | Do not present open or casually internet-reachable Scribe as the normal deployment model. |

Client-side remote/client configuration is optional and authenticated:

```bash
export SCRIBE_REMOTE_URL="https://your-private-scribe.example"
export SCRIBE_REMOTE_AUTH_TOKEN="replace-with-your-client-token"
```

Public docs should prefer the canonical client token name `SCRIBE_REMOTE_AUTH_TOKEN`. See [`docs/REMOTE_CLIENT.md`](docs/REMOTE_CLIENT.md) for the full posture and auth contract.

## What `scribe-council` is

`scribe-council` is a separate, optional package. It is **not** the core Scribe runtime.

Use it only when you also need Scribe's council/template assets:

- it owns the optional `council.templates` provider for this frozen wave
- it depends on `scribe-mcp==2.2`
- it is additive, not required, for standard local/core Scribe usage

The compatibility matrix explains where it fits in the synchronized release set: [`docs/COMPATIBILITY_MATRIX.md`](docs/COMPATIBILITY_MATRIX.md).

## Release docs and navigation

Start here, then follow the tracked docs that match your task:

- **Compatibility and release framing:** [`docs/COMPATIBILITY_MATRIX.md`](docs/COMPATIBILITY_MATRIX.md)
- **Repo truth vs runtime/local overlays:** [`docs/RELEASE_SURFACE.md`](docs/RELEASE_SURFACE.md)
- **Detailed repo/package/runtime boundary:** [`docs/RELEASE_FILE_MAP.md`](docs/RELEASE_FILE_MAP.md)
- **Remote/client auth posture:** [`docs/REMOTE_CLIENT.md`](docs/REMOTE_CLIENT.md)
- **Release-safe client examples:** [`docs/examples/mcp.json.example`](docs/examples/mcp.json.example), [`docs/examples/opencode.json.example`](docs/examples/opencode.json.example)

## Deployment

Container and compose guidance lives in [`deploy/README.md`](deploy/README.md).

That guide keeps the same frozen contract:

- local/core remains the default public posture
- authenticated SSE/remote is optional, not default
- `0.0.0.0` guidance is limited to operator-managed deployments

## License

See [`LICENSE`](LICENSE).
