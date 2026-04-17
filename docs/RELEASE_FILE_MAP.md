# Release File Map

Baseline date: **2026-04-08**  
Coverage: **v2.5 compatibility baseline**

## Table of contents

- [How to use this map](#how-to-use-this-map)
- [Public contract anchors](#public-contract-anchors)
- [Shipped package source](#shipped-package-source)
- [Public support material](#public-support-material)
- [Local/operator-only paths](#localoperator-only-paths)
- [Generated output](#generated-output)

## How to use this map

| Classification | Meaning |
| --- | --- |
| Public contract | Files that define what users should install, run, and read. |
| Shipped package source | Tracked source/manifests that feed release artifacts. |
| Public support material | Tracked docs/examples that are safe to reference publicly. |
| Local/operator-only | Workstation/runtime state; not part of release contract. |
| Generated output | Build/cache artifacts; never source of truth. |

## Public contract anchors

| Path | Classification | Notes |
| --- | --- | --- |
| `README.md` | Public contract | Primary public overview. |
| `pyproject.toml` | Public contract / shipped manifest | Defines `scribe-mcp==2.2.3` and CLI scripts. |
| `MANIFEST.in` | Public contract / shipped manifest | Controls packaged data. |
| `LICENSE` | Public contract | License terms. |
| `docs/COMPATIBILITY_MATRIX.md` | Public contract | Baseline compatibility decision for this wave. |
| `docs/RELEASE_SURFACE.md` | Public contract | Public vs local boundary policy. |
| `docs/RELEASE_FILE_MAP.md` | Public contract | This map. |

## Shipped package source

### Core package (`scribe-mcp`)

| Path | Classification | Notes |
| --- | --- | --- |
| `src/scribe_mcp/__main__.py` | Shipped package source | CLI/server entry target. |
| `src/scribe_mcp/server.py` | Shipped package source | Core server runtime. |
| `src/scribe_mcp/server_sse.py` | Shipped package source | SSE entry path. |
| `src/scribe_mcp/tools/**` | Shipped package source | Tool implementations. |
| `src/scribe_mcp/storage/**` | Shipped package source | Storage backends. |
| `src/scribe_mcp/doc_management/**` | Shipped package source | Document management runtime. |
| `src/scribe_mcp/bridges/**` | Shipped package source | Bridge/plugin runtime framework. |
| `src/scribe_mcp/config/**` | Shipped package source | Runtime settings and config helpers. |
| `src/scribe_mcp/council_templates/__init__.py` | Shipped package source | Compatibility shim retained in this baseline. |

### Optional package (`scribe-council`)

| Path | Classification | Notes |
| --- | --- | --- |
| `packages/scribe_council/pyproject.toml` | Shipped package source | Defines optional package at `2.2.3`. |

## Versioning contract

| Rule | Why it exists |
| --- | --- |
| Release-bound pushes to `main` must include a fresh package version in `pyproject.toml`. | `main` auto-triggers PyPI publishing for package/release-surface changes. |
| Compatibility docs must be updated in the same change as the version bump. | Prevents repo docs from lagging the published package contract. |
| If `scribe-council` stays lockstep with `scribe-mcp`, bump `packages/scribe_council/pyproject.toml` too. | Keeps the optional package dependency contract truthful. |
| `packages/scribe_council/src/scribe_council/**` | Shipped package source | Optional template bundle and assets. |
| `packages/scribe_council/src/scribe_council/council_templates/**` | Shipped package source | Optional `council.templates` provider surface. |

## Public support material

| Path | Classification | Notes |
| --- | --- | --- |
| `docs/**` | Public support material | User-facing docs and guides. |
| `docs/examples/**` | Public support material | Public example configs and snippets. |
| `tests/**` | Public support material | Verification material (not runtime state). |
| `deploy/**` | Public support material | Deployment references. |

## Local/operator-only paths

| Path | Classification | Notes |
| --- | --- | --- |
| `.scribe/**` | Local/operator-only | Local runtime state, logs, and data. |
| Repo-root operator overlays/config files | Local/operator-only | Workstation convenience; not public contract. |
| Agent/tooling workspace directories | Local/operator-only | Local authoring/runtime aids only. |

## Generated output

| Path | Classification | Notes |
| --- | --- | --- |
| `build/**` | Generated output | Local build artifacts. |
| `dist/**` | Generated output | Local wheel/sdist output. |
| `*.egg-info/**` | Generated output | Package metadata artifacts. |
| `__pycache__/**` | Generated output | Python bytecode cache. |
| `.pytest_cache/**` | Generated output | Test cache. |
| `.coverage` | Generated output | Local coverage output. |
