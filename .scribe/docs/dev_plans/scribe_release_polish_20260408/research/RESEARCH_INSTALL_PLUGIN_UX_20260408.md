---
id: scribe_release_polish_20260408-research-install-plugin-ux-20260408
title: "\U0001F52C Research Install Plugin Ux 20260408 \u2014 scribe_release_polish_20260408"
doc_type: RESEARCH_INSTALL_PLUGIN_UX_20260408
doc_name: RESEARCH_INSTALL_PLUGIN_UX_20260408
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-08 02:18:43 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Install Plugin Ux 20260408 — scribe_release_polish_20260408
**Author:** Scribe
**Version:** v0.1
**Status:** scaffolded
**Last Updated:** 2026-04-08 02:17:58 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
Primary objective: audit the current install UX, plugin UX, and shipped skill support against the public release surface.

Current truth:
- `pip install scribe-mcp` is the canonical public install path for end users (`README.md:37-48`).
- `install.sh` is a deterministic checkout/helper script, not an interactive installer (`install.sh:4-65`).
- `scribe plugins project-codex` is the only public plugin command, and it is Codex-only (`src/scribe_mcp/cli/main.py:151-188,506-523`).
- Claude has a shipped bundle, but no matching public install/project command (`plugins/claude/.claude-plugin/plugin.json:1-22`).
- Both shipped plugin trees currently point at `scribe-mcp-usage`, not `scribe-integration` (`plugins/codex/agents/scribe-research-analyst.toml:1-9`; `plugins/claude/agents/scribe-research-analyst.md:1-28`).

Desired public surface:
- Keep README as the canonical public install entry point.
- Keep install.sh scriptable and automation-safe, with optional human-friendly wrapping only if needed.
- Replace the ambiguous Codex-only `project-codex` phrasing with a first-class `plugins codex install`-style command.
- Add a parallel Claude path.
- Ship a public-safe `scribe-integration` skill in both plugin bundles, focused on direct Scribe MCP usage rather than council-agent guidance.

Bottom line: the repo already has the package install truth and the Codex projector internals, but the public story is split, Claude parity is missing, and the shipped skill name does not match the requested public feature name.
<!-- ID: research_scope -->
**Research Lead:** scribe-research-analyst

**Investigation Window:** 2026-04-08

**Focus Areas:**
- Audit `install.sh`, `requirements.txt`, `pyproject.toml`, and package metadata for the public install contract.
- Audit plugin CLI/export helpers and the plugin bundle directories under `plugins/codex/**` and `plugins/claude/**`.
- Audit docs that describe installation or host setup, especially README, `docs/GLOBAL_DEPLOYMENT_GUIDE.md`, `docs/mcp_server_guide.md`, and `docs/RELEASE_SURFACE.md`.
- Determine whether Codex and Claude are first-class public features or repo-local artifacts.
- Determine whether `scribe-integration` is present in shipped plugin bundles or only in council-oriented templates elsewhere.

**Dependencies & Constraints:**
- No implementation work was performed.
- No packaging changes were made.
- All conclusions are based on direct file reads and search results from the current repository state.
- A handful of older docs and backup artifacts mention prior release-audit findings; they were used only as orientation, not as primary evidence.
<!-- ID: findings -->
### Finding 1
- **Summary:** The public install contract is package-first, and `requirements.txt` is explicitly a legacy contributor wrapper.
- **Evidence:** `README.md:37-48` defines `pip install scribe-mcp` as the standard install; `requirements.txt:1-3` says release truth lives in `pyproject.toml`; `pyproject.toml:5-38` defines the package metadata, extras, and scripts; `install.sh:4-65` performs a local-path pip install from the checkout.
- **Confidence:** High

### Finding 2
- **Summary:** `install.sh` is deterministic and non-interactive today; it already supports the needed local workflows, but it does not manage client/plugin bootstrap.
- **Evidence:** `install.sh:4-65` supports `sqlite`, `postgres`, `trusted-sse`, `dev`, and `dev-postgres` profiles, creates/activates `.venv`, upgrades pip, and installs the local checkout with no prompt loop.
- **Confidence:** High

### Finding 3
- **Summary:** Codex plugin support exists, but it is hidden behind the ambiguous `project-codex` verb and no Claude-equivalent public command exists.
- **Evidence:** `src/scribe_mcp/cli/main.py:151-188,506-523` exposes only `plugins project-codex`; `src/scribe_mcp/scripts/project_codex_plugin.py:311-313` validates a Codex manifest and skill bundle; `.agents/plugins/marketplace.json:5-14` publishes only the Codex plugin path; `search project-claude` returned zero matches.
- **Confidence:** High

### Finding 4
- **Summary:** The shipped skill support in both plugin trees is `scribe-mcp-usage`, not the requested public-safe `scribe-integration`.
- **Evidence:** `plugins/codex/skills/scribe-mcp-usage/SKILL.md:1-156` and `plugins/claude/skills/scribe-mcp-usage/SKILL.md:1-156` are the shipped skill files; both agent trees point at that skill (`plugins/codex/agents/scribe-research-analyst.toml:1-9`; `plugins/claude/agents/scribe-research-analyst.md:1-28`); searches for `plugins/codex/skills/scribe-integration` and `plugins/claude/skills/scribe-integration` returned zero matches.
- **Confidence:** High

### Finding 5
- **Summary:** The docs are split between the new package-first README and older checkout/install guidance, which keeps the public setup story inconsistent.
- **Evidence:** `docs/GLOBAL_DEPLOYMENT_GUIDE.md:60-117` still teaches clone + `pip install -r requirements.txt` + manual `codex mcp add`; `docs/mcp_server_guide.md:19-27` still tells readers to run `./install.sh`; `docs/RELEASE_SURFACE.md:1-74` explicitly says repo-root overlays are not public release truth.
- **Confidence:** High

### Additional Notes
- The Codex projector preserves existing agent files and merges into `CODEX_HOME`, so it behaves more like a projection/export operation than a generic installer.
- The current plugin bundles are intentionally distinct: Codex uses `.codex-plugin` plus `.app.json` and projected agents/assets, while Claude uses `.claude-plugin` plus hooks and agent markdown files.
- Optional dependency pressure should stay low on the public path: keep `asyncpg` and `boto3` optional extras, and avoid making plugin bootstrap or client-specific tooling mandatory for core users.
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- `install.sh` is a small shell profile selector plus local `pip install` wrapper. It supports the core local install variants but does not inspect client environments, write client config, or provision plugin bundles.
- `src/scribe_mcp/scripts/project_codex_plugin.py` is a projection/export utility, not a general installer. It validates a Codex manifest, requires the shipped skill bundle, checks for public-safe agent content, and preserves existing target files when projecting into `CODEX_HOME`.
- The shipped plugin bundles are structurally different by client: Codex ships `.codex-plugin/plugin.json`, `.mcp.json`, `.app.json`, `assets/agents.json`, projected `agents/*.toml`, and `skills/scribe-mcp-usage/SKILL.md`; Claude ships `.claude-plugin/plugin.json`, `.mcp.json`, `hooks/hooks.json`, `agents/*.md`, and the same `scribe-mcp-usage` skill.
- The README and `docs/RELEASE_SURFACE.md` already point at the package-first, tracked-docs contract, while `docs/GLOBAL_DEPLOYMENT_GUIDE.md` and `docs/mcp_server_guide.md` still describe older checkout-based flows.

**System Interactions:**
- Public installation for end users is package-centric (`pip install scribe-mcp`).
- Automation and deploy users rely on local checkout or scripted installs (`install.sh` and `pyproject.toml` extras), with optional Postgres and SSE postures.
- Plugin users are split today: Codex has a projector path, Claude has only a bundle artifact path.

**Risk Assessment:**
- If the repo keeps using `project-codex` as the public noun, users will continue to misread it as a repo-only projection helper instead of an install/bootstrap command.
- If Claude parity is not added, the public feature set will remain asymmetric and hard to explain.
- If `scribe-integration` is not shipped as a public-safe skill in both bundles, the public plugin story will continue to depend on a council-oriented or implementation-specific name that does not match the end-user workflow.
- Keep heavy dependencies out of the core public path: `asyncpg` and `boto3` should remain opt-in extras, and any client-specific bootstrap helpers should stay separate from the base package install.
<!-- ID: recommendations -->
### Immediate Next Steps
- [ ] Keep `install.sh` dual-mode in practice, but make the documented/public path non-interactive and explicit: support core install, sqlite, postgres, trusted-SSE, dev, and dev-postgres; do not move Codex or Claude bootstrap into the base installer.
- [ ] Replace the public Codex noun/verb pair with a clearer command surface such as `scribe plugins codex install`; keep `project-codex` only as a compatibility alias if needed during transition.
- [ ] Add a first-class Claude parity command, likely `scribe plugins claude install` or `scribe plugins claude validate`, so the public feature set is symmetric and easy to explain.
- [ ] Ship a public-safe `scribe-integration` skill in both plugin bundles and point the agent configs at that name instead of `scribe-mcp-usage`.
- [ ] Update or retire `docs/GLOBAL_DEPLOYMENT_GUIDE.md` and `docs/mcp_server_guide.md`; keep `README.md` and `docs/RELEASE_SURFACE.md` as the canonical public install/setup references.
- [ ] Keep optional dependency surfaces optional: `asyncpg` stays with the Postgres extra, `boto3` stays with the S3 extra, and any plugin-export helper dependencies should not become core runtime requirements.

### Long-Term Opportunities
- Split client bootstrap from package installation as a dedicated plugin subcommand family so install UX, client projection, and docs can evolve independently.
- Publish release-safe plugin setup examples under tracked docs/examples rather than repo-root overlays, matching the current release-surface policy.
- If the public skill name is standardized on `scribe-integration`, reserve council-specific or internal workflow guidance for non-shipped templates only.
- Consider a dedicated config-export or example-generation command if the public surface eventually needs to emit client bootstrap snippets for Codex and Claude from one place.
<!-- ID: appendix -->
- `README.md:37-48` for the package-first install story.
- `requirements.txt:1-3` and `pyproject.toml:5-38` for the release-vs-legacy package split.
- `install.sh:4-65` for the current deterministic installer helper behavior.
- `src/scribe_mcp/cli/main.py:151-188,506-523` for the current plugin CLI surface.
- `src/scribe_mcp/scripts/project_codex_plugin.py:311-313` for the Codex manifest/skill validation.
- `plugins/codex/.codex-plugin/plugin.json:1-35`, `plugins/codex/.mcp.json:1-9`, `plugins/codex/.app.json:1-3`, and `plugins/codex/skills/scribe-mcp-usage/SKILL.md:1-156` for the Codex bundle shape.
- `plugins/claude/.claude-plugin/plugin.json:1-22`, `plugins/claude/.mcp.json:1-9`, `plugins/claude/hooks/hooks.json:1-16`, and `plugins/claude/skills/scribe-mcp-usage/SKILL.md:1-156` for the Claude bundle shape.
- `docs/GLOBAL_DEPLOYMENT_GUIDE.md:60-117`, `docs/mcp_server_guide.md:19-27`, and `docs/RELEASE_SURFACE.md:1-74` for the public-doc drift assessment.
- `.agents/plugins/marketplace.json:5-14` for the current Codex-only marketplace entry.
- Search results for `project-claude`, `plugins/codex/skills/scribe-integration`, and `plugins/claude/skills/scribe-integration` returned zero matches, which supports the parity and naming-gap conclusions.
