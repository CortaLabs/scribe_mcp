# Release File Map

Baseline date: **2026-08-26**
Coverage: **v2.13.x MCP SDK v2 migration line (current: 2.13.0)**

## Table of contents

- [How to use this map](#how-to-use-this-map)
- [Public contract anchors](#public-contract-anchors)
- [Shipped package source](#shipped-package-source)
- [Public support material](#public-support-material)
- [Public skills](#public-skills)
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
| `pyproject.toml` | Public contract / shipped manifest | Defines `scribe-mcp==2.13.0`, Python `>=3.11`, MCP SDK support `>=2.0.0,<3.0`, and CLI scripts. It carries the 2.11.1 hollow-`append_entry` rejection. The exact isolated candidate is `mcp==2.0.0` with `mcp-types==2.0.0` and `httpx2==2.5.0`; the modern wire default is `2026-07-28`. Named legacy compatibility is limited to `mcp==1.26.0`, protocol `2025-11-25`, handshake stdio, and retained `/sse` plus `/messages/`, with no automatic downgrade. |
| `MANIFEST.in` | Public contract / shipped manifest | Controls packaged data. |
| `LICENSE` | Public contract | License terms. |
| `docs/COMPATIBILITY_MATRIX.md` | Public contract | Baseline compatibility decision for this wave. |
| `docs/TOUR.md` | Public contract | Product tour and first-run artifact story. |
| `docs/DOCUMENT_TOPOLOGY.md` | Public contract | Document topology, lifecycle, scan/repair, handoff, and downstream export contract. |
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
| `src/scribe_mcp/plugins_bundle/**` | Shipped package source | Plugin bundles (Claude + Codex, including hidden `.claude-plugin`/`.codex-plugin` manifests) vendored into the wheel via package-data as of 2.8.0. `config/paths.py:resolve_codex_plugin_root()` prefers this packaged bundle so plugin projection works from a plain `pip install scribe-mcp`; `config/paths.py:onboarding_skill_path()` points at the shipped Codex `/scribe-onboarding` skill in this bundle. |

## Versioning contract

| Rule | Why it exists |
| --- | --- |
| Release-bound pushes to `main` must include a fresh package version in `pyproject.toml`. | `main` auto-triggers PyPI publishing for package/release-surface changes. |
| Compatibility docs must be updated in the same change as the version bump. | Prevents repo docs from lagging the published package contract. |
| Changelog/version-memory behavior must be documented with the release bump. | Project `CHANGELOG.md`, derived global reconciliation, and version-context warnings are user-visible governance behavior. |
| Missing accepted coverage for the current `pyproject.toml` version is release-blocking. | `SCF_CHANGELOG_CURRENT_VERSION_MISSING` appears via `quality_check`, reminders, and `project_health` until managed changelog coverage and reconciliation proof are complete. |

The four release-truth surfaces for this migration are `pyproject.toml`, `src/scribe_mcp/__main__.py`, `docs/COMPATIBILITY_MATRIX.md`, and this file. They report `2.13.0` and the same Python, SDK, modern-protocol, exact-candidate, and named-legacy contract. The optional `packages/scribe_council/pyproject.toml` package is independently versioned and is not changed in lockstep with the core release.

## Public support material

| Path | Classification | Notes |
| --- | --- | --- |
| `docs/**` | Public support material | User-facing docs and guides. |
| `docs/examples/**` | Public support material | Public example configs and snippets. |
| `skills/**` | Public support material | Public skills copied from generated output when intentionally promoted. |
| `tests/**` | Public support material | Verification material (not runtime state). |
| `deploy/**` | Public support material | Deployment references. |

## Public skills

| Path | Classification | Notes |
| --- | --- | --- |
| `skills/scribe-integration/SKILL.md` | Public support material | Public copy of the generated Scribe integration skill. In 2.8.0 this skill was completed to cover the full ~28-tool surface. The template source is not published here. |
| `src/scribe_mcp/plugins_bundle/*/skills/scribe-onboarding/SKILL.md` | Shipped package source | Lean onboarding/install skill shipped inside the Claude/Codex plugin bundles. Broad usage coverage belongs in `scribe-integration` plus repo docs, not a second package-onboarding tree. |

## Local/operator-only paths

| Path | Classification | Notes |
| --- | --- | --- |
| `.scribe/**` | Local/operator-only | Local runtime state, logs, and data. |
| Repo-root operator overlays/config files | Local/operator-only | Workstation convenience; not public contract. |
| Agent/tooling workspace directories | Local/operator-only | Local authoring/runtime aids only. |
| Generated authoring/runtime overlays | Local/operator-only / generated | Not public Scribe release truth unless a future exported copy is deliberately tracked. |

## Generated output

| Path | Classification | Notes |
| --- | --- | --- |
| `build/**` | Generated output | Local build artifacts. |
| `dist/**` | Generated output | Local wheel/sdist output. |
| `*.egg-info/**` | Generated output | Package metadata artifacts. |
| `__pycache__/**` | Generated output | Python bytecode cache. |
| `.pytest_cache/**` | Generated output | Test cache. |
| `.coverage` | Generated output | Local coverage output. |
