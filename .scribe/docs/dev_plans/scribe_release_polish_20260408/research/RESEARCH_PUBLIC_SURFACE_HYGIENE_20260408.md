---
id: scribe_release_polish_20260408-research-public-surface-hygiene-20260408
title: "\U0001F52C Research Public Surface Hygiene 20260408 \u2014 scribe_release_polish_20260408"
doc_type: RESEARCH_PUBLIC_SURFACE_HYGIENE_20260408
doc_name: RESEARCH_PUBLIC_SURFACE_HYGIENE_20260408
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-08 02:16:37 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Public Surface Hygiene 20260408 — scribe_release_polish_20260408
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-04-08 02:14:25 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
This audit separates three downstream surfaces: git source, built package payload, and local runtime/operator state. The repo already encodes most of the intended boundary correctly: public docs and tracked examples are the release-safe guidance surface; `pyproject.toml` and `MANIFEST.in` define package payload and sdist pruning; and runtime overlays belong outside the public contract.

The main conclusion is that `.scribe/docs/**` and `docs/dev_plans/**` should remain excluded from git and from built packages. They are useful as local managed-doc workspaces, but downstream consumers should never inherit them. If a document needs to become public truth, it should be promoted into tracked `docs/` or another intentionally published location instead of living under `.scribe/`.

Two clean-downstream gaps remain visible in the current tree: generated `src/scribe_mcp.egg-info/**` metadata is present and should never be a source surface, and the runtime-local classes called out in `docs/RELEASE_FILE_MAP.md` for `.scribe/backups/**`, `.scribe/data/**`, `logs/**`, and `state/**` are not all fully covered by the current `.gitignore`. Confidence: high.
<!-- ID: research_scope -->
**Research Lead:** `scribe-research-analyst`

**Investigation Window:** 2026-04-07 to 2026-04-08

**Focus Areas:**
- Review repo-level ignore rules and packaging manifests for source/package/runtime boundaries.
- Inspect release docs that define public contract, runtime-local state, and build-artifact policy.
- Check tracked examples and deployment guidance so public config examples are preserved.
- Identify generated or consumer-hostile artifacts that should not reach downstream users.
- Determine whether `.scribe` docs and dev plans belong in git, in packages, or only in local managed-doc workflows.

**Dependencies & Constraints:**
- No deletions or implementation were performed.
- The audit is based on direct file evidence from `.gitignore`, `pyproject.toml`, `MANIFEST.in`, `README.md`, release docs, example configs, deployment docs, and generated egg-info metadata.
- Any policy statement about missing ignore coverage is an inference from the explicit policy documents plus the current ignore file contents.
<!-- ID: findings -->
### Finding 1: The repo already defines a clean source/package boundary.
- **Summary:** `pyproject.toml` limits wheel payload to package source and curated package data, while `MANIFEST.in` prunes local overlays, build trees, runtime state, and generated residue from the sdist surface.
- **Evidence:** `pyproject.toml` includes package data for `config/*.json`, `config/*.yaml`, `db/*.sql`, `db/postgres_migrations/*.sql`, `plugins/*.json`, and `templates/**`, while `MANIFEST.in` prunes `build`, `dist`, `.council`, `.claude`, `.codex`, `.scribe`, `logs`, and `state` and excludes repo-root overlay files.
- **Confidence:** High.

### Finding 2: `.scribe/docs/**` and `docs/dev_plans/**` should stay out of downstream git and packages.
- **Summary:** The public release docs classify `.scribe/` content as local runtime/operator state, and `.gitignore` explicitly excludes `.scribe/docs/` and `docs/dev_plans/`. The repo therefore already treats managed-doc workspaces as local-only, not public truth.
- **Evidence:** `docs/RELEASE_SURFACE.md` marks `.scribe/cli/*.json`, `.scribe/state/*.json`, and `.scribe/logs/*` as local overlays; `docs/RELEASE_FILE_MAP.md` classifies `.scribe/*` paths as runtime-local; `.gitignore` ignores `.scribe/docs/` and `docs/dev_plans/`.
- **Confidence:** High.

### Finding 3: Generated build metadata is still downstream-hostile if it is left in the tree.
- **Summary:** The checkout contains `src/scribe_mcp.egg-info/**`, which is generated packaging metadata, not source. It belongs in the ignore/runtime bucket, not the tracked release surface.
- **Evidence:** `src/scribe_mcp.egg-info/SOURCES.txt` lists `LICENSE`, `MANIFEST.in`, `README.md`, `pyproject.toml`, and then generated metadata files such as `PKG-INFO`, `SOURCES.txt`, `entry_points.txt`, and `requires.txt`; `.gitignore` also ignores `*.egg-info/`; `docs/RELEASE_FILE_MAP.md` marks `*.egg-info/**` as generated/stale output.
- **Confidence:** High.

### Finding 4: There is a small ignore-policy gap for some runtime-local residue.
- **Summary:** `docs/RELEASE_FILE_MAP.md` treats `.scribe/backups/**`, `.scribe/data/**`, `logs/**`, and `state/**` as runtime-local, but the current `.gitignore` does not explicitly cover those root or `.scribe` subpaths in the same way it covers `.scribe/state/`, `.scribe/logs/`, and `.scribe/sentinel/`.
- **Evidence:** Compare `docs/RELEASE_FILE_MAP.md` runtime-local rows with `.gitignore` lines covering `.scribe/state/`, `.scribe/logs/`, `.scribe/sentinel/`, and `.scribe/docs/` but not the other runtime-local paths listed above.
- **Confidence:** Medium to high.

### Additional Notes
- The public docs and examples are correctly preserved: `README.md` points users to tracked examples under `docs/examples/`, and `deploy/README.md` repeats that guidance instead of repo-root overlays.
- The release docs already make the right public/private distinction for `.mcp.json`, `opencode.json`, `AGENTS.md`, `CLAUDE.md`, `.claude/**`, `.codex/**`, and `.council/**`.
<!-- ID: technical_analysis -->
## Keep / Remove / Ignore Matrix

| Surface | Keep in git source | Include in built packages | Ignore as runtime/local state | Notes |
| --- | --- | --- | --- | --- |
| `src/scribe_mcp/**` | Yes | Yes | No | Core package source and runtime code. |
| `pyproject.toml`, `MANIFEST.in`, `LICENSE`, `README.md` | Yes | sdist-visible; `pyproject.toml` and `MANIFEST.in` define packaging | No | Source-of-truth manifests and release docs. |
| `docs/COMPATIBILITY_MATRIX.md`, `docs/RELEASE_SURFACE.md`, `docs/RELEASE_FILE_MAP.md`, `docs/REMOTE_CLIENT.md` | Yes | sdist-visible support docs | No | Public release contract and policy docs. |
| `docs/examples/*.example` | Yes | sdist-visible support material | No | These are the release-safe config examples downstream users need. |
| `deploy/**` | Yes | sdist-visible support material | No | Operator/deployment guidance stays tracked, but it is not runtime state. |
| `.scribe/docs/**` | No | No | Yes | Local managed-doc workspace only. If content should be public, promote it into tracked docs instead. |
| `docs/dev_plans/**` | No | No | Yes | Planning output should not be the downstream contract. |
| `.mcp.json`, `opencode.json`, `AGENTS.md`, `CLAUDE.md`, `.claude/**`, `.codex/**`, `.council/**` | No | No | Yes | Repo-root overlays and operator material are not public release truth. |
| `build/**`, `dist/**`, `*.egg-info/**`, `__pycache__/**` | No | No | Yes | Generated build metadata and stale artifacts. |
| `.scribe/cli/*.json`, `.scribe/state/**`, `.scribe/logs/**`, `.scribe/sentinel/**` | No | No | Yes | Mutable local runtime state. |
| `.scribe/backups/**`, `.scribe/data/**`, `logs/**`, `state/**` | No | No | Yes | Runtime residue that should stay out of the downstream experience. |

### Policy answer for `.scribe` docs and dev plans
- **Do not track them as source truth.** They are operational workspaces, not public release material.
- **Do not ship them in built packages.** `MANIFEST.in` already prunes `.scribe`, which is the correct direction.
- **Do not point downstream users at them.** Public docs should point to tracked docs/examples under `docs/`.
- **If a doc becomes canonical, promote it.** Move the curated content into `docs/` or another intentionally published location and leave the `.scribe` copy as local workspace output.

### Consumer-hostile surfaces still worth cleaning up
- `src/scribe_mcp.egg-info/**` should be treated as generated output only.
- Runtime residue paths not explicitly ignored in `.gitignore` should be added to the ignore policy in a later cleanup pass if they can appear in the checkout.
- `build/` and `dist/` should remain build-only, never source-of-truth surfaces.
<!-- ID: recommendations -->
### Immediate Next Steps
- [ ] Keep `.scribe/docs/**` and `docs/dev_plans/**` out of git and out of built packages; use them only for local managed-doc workflows.
- [ ] Promote any public-facing guidance into tracked `docs/` or `docs/examples/` instead of referencing repo-local overlays.
- [ ] Treat `src/scribe_mcp.egg-info/**` as generated noise, not a release surface, in any later cleanup pass.
- [ ] Add explicit ignore coverage for the runtime-local residue paths that are still only documented, not fully ignored, if downstream checkout hygiene is the goal.

### Long-Term Opportunities
- Consolidate the public release story around tracked docs/examples plus the packaging manifests, so there is one obvious place for downstream users to look.
- Consider a repo cleanup pass that removes or relocates generated metadata trees from the source checkout and tightens ignore coverage around runtime residue.
- Keep the release docs synced with ignore/package rules so future contributors do not accidentally reintroduce local overlays into the public surface.
<!-- ID: appendix -->
- **Primary policy sources:** `.gitignore`, `pyproject.toml`, `MANIFEST.in`, `README.md`.
- **Public surface docs:** `docs/RELEASE_SURFACE.md`, `docs/RELEASE_FILE_MAP.md`, `docs/COMPATIBILITY_MATRIX.md`, `docs/REMOTE_CLIENT.md`.
- **Config examples to preserve:** `docs/examples/mcp.json.example`, `docs/examples/opencode.json.example`.
- **Deployment guidance:** `deploy/README.md`.
- **Generated metadata inspected:** `src/scribe_mcp.egg-info/SOURCES.txt`, `src/scribe_mcp.egg-info/PKG-INFO`, `src/scribe_mcp.egg-info/requires.txt`, `src/scribe_mcp.egg-info/entry_points.txt`, `src/scribe_mcp.egg-info/top_level.txt`.
- **Key policy inference:** `.scribe/docs/**` remains local-only, and any public content should be promoted to tracked `docs/` instead of inheriting the `.scribe` workspace.
