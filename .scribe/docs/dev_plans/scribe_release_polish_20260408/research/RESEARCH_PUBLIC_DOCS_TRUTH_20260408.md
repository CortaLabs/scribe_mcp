---
id: scribe_release_polish_20260408-research-public-docs-truth-20260408
title: "\U0001F52C Research Public Docs Truth 20260408 \u2014 scribe_release_polish_20260408"
doc_type: RESEARCH_PUBLIC_DOCS_TRUTH_20260408
doc_name: RESEARCH_PUBLIC_DOCS_TRUTH_20260408
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-08 02:17:00 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Public Docs Truth 20260408 — scribe_release_polish_20260408
**Author:** Scribe
**Version:** v0.1
**Status:** scaffolded
**Last Updated:** 2026-04-08 02:14:21 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
This audit found that the release-policy docs are mostly aligned with the current package-first story, but three public how-to docs still teach older repo-checkout/runtime flows. The strongest contradictions are in `docs/GLOBAL_DEPLOYMENT_GUIDE.md`, `docs/mcp_server_guide.md`, and `docs/whitepapers/scribe_mcp_whitepaper.md`, which still point readers at source-checkout setup, `requirements.txt`, `install.sh`, and repo-local launch paths instead of the installed-package contract.

The README itself is directionally good and should remain high-level, but it still needs a cleaner docs index that points readers to the deeper guides for architecture, plugin/bridge support, deployment, and server setup. The file map should stay in `docs/RELEASE_FILE_MAP.md`; it should not be inlined into README.
<!-- ID: research_scope -->
**Research Lead:** scribe-research-analyst

**Investigation Window:** 2026-04-07 to 2026-04-08

**Focus Areas:**
- Public-facing entry docs likely read first by downstream users.
- README completeness and link strategy.
- Package-first install/runtime truth versus older source-checkout guidance.
- Release-safe examples and runtime posture docs.
- Plugin/bridge support docs and whether they should be surfaced from README.

**Dependencies & Constraints:**
- No code edits or implementation work were allowed.
- The report had to be backed by direct file evidence from the repo.
- The README should remain high-level if a dedicated file-map doc exists.
- The audit had to include contradiction detection, not just a summary of what is present.
<!-- ID: findings -->
Detail each major finding with evidence and confidence levels.

### Finding 1 - High severity
- **Summary:** `docs/GLOBAL_DEPLOYMENT_GUIDE.md` still leads with repository cloning, `requirements.txt`, and repo-local configuration examples, which conflicts with the package-first public contract.
- **Evidence:** `docs/GLOBAL_DEPLOYMENT_GUIDE.md:58-71` shows `git clone`, `python -m venv`, and `pip install -r requirements.txt`; `docs/GLOBAL_DEPLOYMENT_GUIDE.md:74-116` centers MCP client setup around local repo commands; `docs/GLOBAL_DEPLOYMENT_GUIDE.md:392-450` still frames migration from embedded mode as a repo-install workflow. The release file map instead says public guidance should come from tracked docs/examples and that repo-root overlays are not release truth (`docs/RELEASE_FILE_MAP.md:35-48`, `docs/RELEASE_FILE_MAP.md:104-120`).
- **Confidence:** High
- **Impact:** First-run readers are nudged toward source checkout and manual dependency install instead of the installed-package contract.
- **Recommendation:** Rewrite this guide as an operator-only or appendix-style deployment doc, and make the main flow start from installed `scribe-server` plus tracked examples.

### Finding 2 - High severity
- **Summary:** `docs/mcp_server_guide.md` is still a pre-release style tutorial that teaches `./install.sh`, `requirements.txt`, and `python -m MCP_SPINE.scribe_mcp.server` instead of the installed-package runtime.
- **Evidence:** `docs/mcp_server_guide.md:18-25` instructs users to run `./install.sh` and `pip install -r requirements.txt`; `docs/mcp_server_guide.md:384-409` uses `python -m MCP_SPINE.scribe_mcp.server` for the quickstart. That conflicts with the README and release docs that present `pip install scribe-mcp` and `scribe-server` as the default supported posture (`README.md:33-48`, `README.md:89-101`).
- **Confidence:** High
- **Impact:** This is the most likely doc to mis-teach new server authors because it looks like a canonical how-to guide.
- **Recommendation:** Modernize the guide to package-first examples, rename it if needed, and move any source-tree walkthroughs into a clearly marked development appendix.

### Finding 3 - High severity
- **Summary:** The whitepaper still contains repo-local config and launch paths that are not release-safe public guidance.
- **Evidence:** `docs/whitepapers/scribe_mcp_whitepaper.md:650-663` references `MCP_SPINE/config/mcp_config.json`, a Codex registration example that ends in `exec python -m server`, and `MCP_SPINE/scripts/test_mcp_server.py`. Those examples point at repo-local paths and an ad hoc module launch rather than the installed-package contract described by the release policy docs and README.
- **Confidence:** High
- **Impact:** A reader treating the whitepaper as a public guide will pick up internal-path assumptions that do not survive outside this checkout.
- **Recommendation:** Rewrite or demote the whitepaper so it uses tracked examples and installed `scribe-server`, or label it explicitly as background/architecture only.

### Finding 4 - Medium severity
- **Summary:** The README is mostly solid but does not yet act as a complete front door to the public docs set.
- **Evidence:** It already links `COMPATIBILITY_MATRIX`, `RELEASE_SURFACE`, `RELEASE_FILE_MAP`, `REMOTE_CLIENT`, and the example configs (`README.md:18-31`, `README.md:89-101`), but it does not surface `docs/mcp_server_guide.md`, `docs/GLOBAL_DEPLOYMENT_GUIDE.md`, `docs/whitepapers/scribe_mcp_whitepaper.md`, or `docs/BRIDGE_DEVELOPMENT.md`. The bridge guide is the explicit plugin/runtime contract doc and says every registered manifest must resolve to a real runtime plugin (`docs/BRIDGE_DEVELOPMENT.md:1-11`, `docs/BRIDGE_DEVELOPMENT.md:265-278`).
- **Confidence:** Medium
- **Impact:** Advanced users have to hunt for the deeper docs that explain package/runtime boundaries, plugin support, and deployment modes.
- **Recommendation:** Add a compact docs index or "More docs" section to README that points to the server guide, deployment guide, bridge guide, whitepaper, and examples.

### Additional Notes
- `docs/RELEASE_SURFACE.md` and `docs/REMOTE_CLIENT.md` are already aligned with the current default-local, optional-authenticated remote/client posture.
- `deploy/README.md` is also aligned: it starts from container build plus `scribe-server`, keeps local/core default, and limits broad bind guidance to managed deployments.
- `docs/examples/mcp.json.example` and `docs/examples/opencode.json.example` are release-safe examples because they use installed `scribe-server` and tracked example paths.
- No markdown plugin docs were found under `plugins/`; the bridge guide is the only explicit plugin/bridge documentation surfaced by the repo scan.
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- The release-policy docs are now the authoritative contract layer: `docs/RELEASE_SURFACE.md`, `docs/REMOTE_CLIENT.md`, `docs/COMPATIBILITY_MATRIX.md`, and `docs/RELEASE_FILE_MAP.md` all describe the package/runtime boundary in the same direction.
- The repo has two classes of public docs: contract docs that define truth, and older how-to docs that still describe source checkout and module-launch workflows. The audit problem is not missing information; it is stale ordering and stale entrypoints.
- The tracked example configs already model the correct installed-package runtime entrypoint (`scribe-server`) and should be the default examples in any user-facing index.
- The bridge/plugin story is real and documented, but it lives in `docs/BRIDGE_DEVELOPMENT.md` rather than in README, so plugin support is easy to miss unless README explicitly points to it.

**System Interactions:**
- README is the top-level public contract and should route readers into the more specific policy and support docs.
- `docs/RELEASE_FILE_MAP.md` is the right place for file-map detail; README should link it, not duplicate it inline.
- Deployment and MCP-server guides sit lower in the funnel and should inherit the package-first contract from README and the release-policy docs.

**Risk Assessment:**
- Stale docs can make downstream users install from source, reach for repo-local files, or assume `python -m ...` is the supported runtime path.
- The whitepaper is especially risky because it looks authoritative while mixing architecture text with repo-local operational commands.
- The README is not broken, but it is not yet a strong enough directory for the full public-doc set.
<!-- ID: recommendations -->
Translate research into recommended actions.

### Immediate Next Steps
- [ ] Update `README.md` to stay high-level and add a compact docs index that links `docs/COMPATIBILITY_MATRIX.md`, `docs/RELEASE_SURFACE.md`, `docs/RELEASE_FILE_MAP.md`, `docs/REMOTE_CLIENT.md`, `docs/mcp_server_guide.md`, `docs/GLOBAL_DEPLOYMENT_GUIDE.md`, `docs/BRIDGE_DEVELOPMENT.md`, `docs/whitepapers/scribe_mcp_whitepaper.md`, `deploy/README.md`, and the example configs.
- [ ] Keep the file map in `docs/RELEASE_FILE_MAP.md`; do not inline a full file map into README.
- [ ] Rewrite `docs/GLOBAL_DEPLOYMENT_GUIDE.md` so the primary flow starts from installed `scribe-server` and tracked examples, with source-checkout content moved to a clearly labeled development appendix if it remains at all.
- [ ] Rewrite `docs/mcp_server_guide.md` to remove `install.sh`, `requirements.txt`, and `python -m MCP_SPINE.scribe_mcp.server` from the primary path.
- [ ] Modernize or re-scope `docs/whitepapers/scribe_mcp_whitepaper.md` so it stops using repo-local config and launch commands as public guidance.

### Long-Term Opportunities
- Add a true front-door docs index page if the README grows beyond a compact link hub.
- Harmonize the naming and tone of the public docs so the contract docs, how-to docs, and deep background docs are clearly separated.
- Consider a short "what Scribe is / what it is not" summary block in README that mirrors the release-policy docs and reduces first-read ambiguity.
<!-- ID: appendix -->
- **References audited:** `README.md`, `docs/RELEASE_SURFACE.md`, `docs/REMOTE_CLIENT.md`, `docs/GLOBAL_DEPLOYMENT_GUIDE.md`, `docs/mcp_server_guide.md`, `docs/whitepapers/scribe_mcp_whitepaper.md`, `docs/COMPATIBILITY_MATRIX.md`, `docs/RELEASE_FILE_MAP.md`, `deploy/README.md`, `docs/examples/mcp.json.example`, `docs/examples/opencode.json.example`, `docs/BRIDGE_DEVELOPMENT.md`.
- **Plugin-doc inventory:** no markdown docs were found under `plugins/` during the repo scan.
- **Most important line ranges:**
  - `README.md:18-31`, `README.md:33-48`, `README.md:60-101`
  - `docs/GLOBAL_DEPLOYMENT_GUIDE.md:58-71`, `docs/GLOBAL_DEPLOYMENT_GUIDE.md:74-116`, `docs/GLOBAL_DEPLOYMENT_GUIDE.md:392-450`
  - `docs/mcp_server_guide.md:18-25`, `docs/mcp_server_guide.md:384-409`
  - `docs/whitepapers/scribe_mcp_whitepaper.md:650-663`, `docs/whitepapers/scribe_mcp_whitepaper.md:734-734`
  - `docs/RELEASE_SURFACE.md:1-24`, `docs/REMOTE_CLIENT.md:1-48`, `docs/RELEASE_FILE_MAP.md:35-48`, `docs/RELEASE_FILE_MAP.md:104-120`
  - `docs/BRIDGE_DEVELOPMENT.md:1-11`, `docs/BRIDGE_DEVELOPMENT.md:265-278`
- **README decision:** keep README high-level, link the dedicated file-map doc, and use a compact docs index rather than an inline file map.
