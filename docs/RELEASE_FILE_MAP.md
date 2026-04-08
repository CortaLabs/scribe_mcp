# Release File Map

Frozen on **2026-04-05** for the **2.5 compatibility-release** documentation wave.

This document is the authoritative file-map reference for the frozen public contract. Use it to distinguish:

- **tracked repo truth**
- **shipped package source**
- **tracked support material**
- **local runtime/operator-only state**
- **generated or stale build output**

## Table of contents

- [How to read this map](#how-to-read-this-map)
- [Public contract anchors](#public-contract-anchors)
- [Shipped package source](#shipped-package-source)
- [Tracked support material](#tracked-support-material)
- [Runtime-local paths](#runtime-local-paths)
- [Repo-local overlays and operator material](#repo-local-overlays-and-operator-material)
- [Generated and stale output](#generated-and-stale-output)
- [Cross-repo pointer](#cross-repo-pointer)

## How to read this map

| Classification | Meaning |
| --- | --- |
| **Public contract** | Tracked files that define what downstream users should read, install, or configure. |
| **Shipped package source** | Tracked source/manifests that feed built wheels or sdists. |
| **Tracked support material** | Versioned repo content that is useful for development, deployment, or verification, but is not itself local runtime state. |
| **Runtime-local** | Mutable local state produced while running Scribe. Not release truth. |
| **Overlay/local operator** | Workstation-specific or repo-local convenience material. Not release truth. |
| **Generated/stale output** | Build output or caches. Never release truth. |

## Public contract anchors

These are the first files to consult for the frozen release contract:

| Path | Classification | Notes |
| --- | --- | --- |
| `README.md` | Public contract | High-signal overview for the 2.5 compatibility wave. |
| `pyproject.toml` | Public contract / shipped manifest | Defines `scribe-mcp`, version `2.2`, and CLI entry points including `scribe`, `scribe-mcp`, and `scribe-server`. |
| `MANIFEST.in` | Public contract / shipped manifest | Controls what package data enters build artifacts. |
| `LICENSE` | Public contract | Licensing terms. |
| `docs/COMPATIBILITY_MATRIX.md` | Public contract | Frozen package/runtime compatibility decision; explicitly defers `v3`. |
| `docs/RELEASE_SURFACE.md` | Public contract | Repo-truth vs overlay/runtime policy. |
| `docs/REMOTE_CLIENT.md` | Public contract | Optional authenticated remote/client posture. |
| `docs/RELEASE_FILE_MAP.md` | Public contract | This detailed file map. |

## Shipped package source

### Core package: `src/scribe_mcp/**`

| Path | Classification | Notes |
| --- | --- | --- |
| `src/scribe_mcp/__main__.py` | Shipped package source | Installed CLI/server entry target. |
| `src/scribe_mcp/server.py` | Shipped package source | Core MCP server runtime. |
| `src/scribe_mcp/server_sse.py` | Shipped package source | SSE transport entry point. |
| `src/scribe_mcp/tools/**` | Shipped package source | Public MCP tool implementations. |
| `src/scribe_mcp/doc_management/**` | Shipped package source | Managed document lifecycle engine. |
| `src/scribe_mcp/storage/**` | Shipped package source | SQLite/Postgres/remote storage backends. |
| `src/scribe_mcp/bridges/**` | Shipped package source | Core bridge runtime, registry, policy, and hooks. |
| `src/scribe_mcp/config/**` | Shipped package source | Settings, runtime-path helpers, and config payloads. |
| `src/scribe_mcp/templates/**` | Shipped package source | Tracked template assets that belong to `scribe-mcp`. |
| `src/scribe_mcp/council_templates/__init__.py` | Shipped package source | Deprecated compatibility shim only; removal is deferred to the later breaking release. |

### Optional package: `packages/scribe_council/**`

| Path | Classification | Notes |
| --- | --- | --- |
| `packages/scribe_council/pyproject.toml` | Shipped package source | Defines the optional `scribe-council` package, version `2.2`. |
| `packages/scribe_council/src/scribe_council/**` | Shipped package source | Optional council/template assets. |
| `packages/scribe_council/src/scribe_council/council_templates/**` | Shipped package source | Owns the optional `council.templates` provider for this frozen wave. |

## Tracked support material

These paths are versioned repo truth, but they are not runtime-local state.

| Path | Classification | Notes |
| --- | --- | --- |
| `docs/**` | Tracked support material | Release docs, guides, examples, whitepapers, and historical notes. |
| `docs/examples/**` | Tracked support material | Public example configuration files; prefer these over repo-root overlays. |
| `deploy/**` | Tracked support material | Dockerfile, compose overlay, entrypoint, and deployment guide. |
| `tests/**` | Tracked support material | Verification and regression coverage. |
| `examples/**` | Tracked support material | Example project material kept in the repo. |
| `benchmarks/**` | Tracked support material | Benchmark harness and artifacts. |
| `research/**`, `architecture/**` | Tracked support material | Versioned design/research context, not runtime state. |

## Runtime-local paths

These paths are mutable local runtime state. They are **not** release truth and should not be used as public guidance.

| Path | Classification | Notes |
| --- | --- | --- |
| `.scribe/cli/*.json` | Runtime-local | Per-operator CLI/session state. |
| `.scribe/state/**` | Runtime-local | Local runtime bookkeeping and state files. |
| `.scribe/logs/**` | Runtime-local | Local logs. |
| `.scribe/backups/**` | Runtime-local | Local backup material created during operation. |
| `.scribe/data/**` | Runtime-local | Local data generated by a running environment. |
| `.scribe/sentinel/**` | Runtime-local | Local sentinel-mode state. |

If repo-root `state/` or `logs/` residue exists in a workstation checkout, treat it as local residue rather than as part of the release contract.

## Repo-local overlays and operator material

These paths may be useful on a particular workstation, but they are **not** the public contract:

| Path | Classification | Notes |
| --- | --- | --- |
| `.mcp.json` | Overlay/local operator | Local client bootstrap convenience only. |
| `opencode.json` | Overlay/local operator | Local operator convenience only. |
| `AGENTS.md` | Overlay/local operator | Repo-specific operator/agent context, not shipped package truth. |
| `CLAUDE.md` | Overlay/local operator | Local/operator instruction overlay. |
| `.claude/**` | Overlay/local operator | Generated/local Claude-specific material. |
| `.codex/**` | Overlay/local operator | Generated/local Codex-specific material. |
| `.council/**` | Overlay/local operator | Local council scaffolding and overlays. |
| `.agents/**`, `.opencode/**` | Overlay/local operator | Local plugin/agent operator material. |

When public docs need examples, point to tracked files under `docs/examples/**` instead.

## Generated and stale output

These paths must never define the release contract:

| Path | Classification | Notes |
| --- | --- | --- |
| `build/**` | Generated/stale output | Local build output. |
| `dist/**` | Generated/stale output | Local wheels/sdists after a build. |
| `*.egg-info/**` | Generated/stale output | Build metadata, not source of truth. |
| `__pycache__/**` | Generated/stale output | Python cache output. |
| `.pytest_cache/**` | Generated/stale output | Test cache output. |
| `.coverage` | Generated/stale output | Local coverage artifact. |

Release truth comes from tracked source/manifests/docs and the fresh artifacts inspected against them, not from leftover generated trees.

## Cross-repo pointer

For the synchronized Council pairing documented in this wave, use:

- the matching `council_mcp` release docs from that checkout

That document freezes the `council_mcp 2.0.0` side of the installed-package contract while keeping local/core as default and remote/client as optional and authenticated.
