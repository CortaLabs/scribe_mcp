---
id: scribe_release_polish_20260408-phase-plan
title: "Release Polish Phase Plan \u2014 `scribe_release_polish_20260408`"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-08 02:50:00 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Release Polish Phase Plan — `scribe_release_polish_20260408`

This plan uses the operator's required package numbers, but execution order is determined by phase dependencies, not by numeric order.

## Phase Overview

| Phase | Goal | Packages | Parallelism |
| --- | --- | --- | --- |
| 0 | Freeze the governed planning baseline | Architecture package replacement | Complete |
| 1 | Clear blockers and lock the downstream boundary | 7, 4 | Sequential |
| 2 | Land the structural public-surface work | 2, 3, 5, 6 | Parallel after Phase 1 |
| 3 | Rewrite and align the public docs set | 1 | Sequential, after Phase 2 |
| 4 | Final release gate | 8 | Last |

## Milestone Tracking

| Milestone | Status | Evidence |
| --- | --- | --- |
| Phase 0 architecture package replacement | Complete | `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, and `CHECKLIST.md` replaced on 2026-04-08, then revised after pre-implementation review so Package 7 owns credential disposition, Package 6 stays out of README/file-map finalization, and runtime terminology work cites the canonical runtime research conclusions. |
| Phase 1 blocker and hygiene boundary | Pending | Packages 7 and 4 |
| Phase 2 structural public-surface work | Pending | Packages 2, 3, 5, and 6 |
| Phase 3 public-doc finalization | Pending | Package 1 |
| Phase 4 final review and signoff | Pending | Package 8 |

## Phase 0 — Planning Baseline

### Task Package 0.1 — Replace Scaffold Planning Docs

**Scope:** Replace the placeholder architecture, phase-plan, and checklist docs with a real governed implementation contract.

**Files to Modify:**
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/ARCHITECTURE_GUIDE.md` — governing design and issue inventory.
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/PHASE_PLAN.md` — bounded package sequencing.
- `.scribe/docs/dev_plans/scribe_release_polish_20260408/CHECKLIST.md` — package-level acceptance criteria.

**Dependencies:** None.

**Verification:**
- [x] Architecture doc names every remaining polish package.
- [x] Phase plan encodes safe sequencing and parallel lanes.
- [x] Checklist includes testable acceptance criteria and architecture proof items.

**Out of Scope:** Implementation.

## Phase 1 — Blocker And Boundary Lock

### Task Package 7 — Security/Blocker Cleanup For Tracked Sensitive Local Artifacts

**Type:** Code plus ops/docs.

**Scope:** Remove the credential-bearing backup manifest from the tracked public surface, fix the generation path so secrets cannot be emitted again, and complete the blocking credential disposition for `SEC-2026-04-08-0001` by rotating the exposed credential or proving it has already been invalidated and replaced.

**Files to Modify:**
- `.scribe/backups/postgres/latest_backup_manifest.json` — remove or replace the tracked sensitive artifact from the release surface.
- Backup/manifest generation path for Postgres backup metadata — redact or omit credential-bearing command payloads.
- `.gitignore` — ensure `.scribe/backups/**` is treated as runtime-local.
- Related release/runbook docs and security-case evidence — capture the new boundary plus the completed rotation or invalidated-secret proof.

**Dependencies:** None. This is the first implementation package.

**Specifications:**
1. Remove the tracked credential-bearing artifact from the repo-visible release surface.
2. Ensure future manifest output cannot serialize a raw DSN or credential-bearing command string.
3. Align ignore policy and runtime-local docs so `.scribe/backups/**` cannot quietly drift back into the tracked surface.
4. Rotate the exposed credential tied to `SEC-2026-04-08-0001`, or document an equivalently explicit blocking disposition showing the leaked secret is already dead and replaced.
5. Update security-case evidence so Package 7 cannot be marked complete without artifact removal, generator hardening, and credential-disposition proof.

**Patterns to Follow:**
- Respect `docs/RELEASE_FILE_MAP.md` runtime-local classification.
- Keep security case tracking explicit; do not bury it inside a generic cleanup commit.

**Verification:**
- [ ] No tracked artifact under `.scribe/backups/**` contains credentials.
- [ ] Backup manifest generation omits or redacts credential-bearing fields.
- [ ] Ignore policy prevents accidental retracking of backup output.
- [ ] Security case proof shows artifact removal, generator hardening, and completed credential rotation or explicit invalidated-secret proof before signoff.

**Out of Scope:** Broader security audit beyond the confirmed blocker.

### Task Package 4 — Public-Surface Hygiene / Tracked Local-Runtime-Generated Cleanup Policy

**Type:** Code plus docs.

**Scope:** Align git/package/runtime boundaries so local managed-doc output, repo overlays, generated metadata, and runtime residue are not treated as downstream public surface.

**Files to Modify:**
- `.gitignore` — runtime-local and generated residue coverage.
- `docs/RELEASE_SURFACE.md` — public-vs-local policy language.
- Generated-artifact cleanup targets such as `src/scribe_mcp.egg-info/**` if still tracked.
- Any narrow packaging or repo-hygiene file needed to keep the boundary enforceable.

**Dependencies:** Requires Package 7 complete when touching overlapping ignore/runtime-local policy.

**Specifications:**
1. Make runtime-local policy explicit for `.scribe/docs/**`, `docs/dev_plans/**`, `.scribe/data/**`, repo-root `logs/` and `state/`, and other documented local residue.
2. Remove or quarantine generated metadata from the tracked source surface.
3. Preserve tracked docs/examples and public support material while excluding local overlays.
4. Leave final `README.md` and `docs/RELEASE_FILE_MAP.md` polish to Package 1 so they describe the post-cleanup state.

**Patterns to Follow:**
- `docs/RELEASE_SURFACE.md` and `docs/RELEASE_FILE_MAP.md` are the truth sources; code hygiene must match them.
- Do not reintroduce local overlays into package data or tracked examples.

**Verification:**
- [ ] Ignore policy matches the documented runtime-local boundary.
- [ ] Generated metadata is no longer treated as source truth.
- [ ] Managed-doc workspaces remain local-only and are not promoted accidentally.
- [ ] Public examples and tracked docs remain intact.

**Out of Scope:** Final docs index wording and README/file-map copy edits.

## Phase 2 — Structural Public-Surface Work

### Task Package 2 — Install UX And `install.sh` Redesign

**Type:** Code plus focused docs.

**Scope:** Turn `install.sh` into a professional, release-safe installer story for checkout, deploy, and automation users while keeping the default behavior non-interactive and scriptable.

**Files to Modify:**
- `install.sh` — public installer behavior and help surface.
- `pyproject.toml` — only if installer-facing metadata or entrypoint naming must support the final story.
- `requirements.txt` — only if contributor-only framing needs tightening.
- Narrow installer-facing docs/examples needed to explain supported profiles without pre-empting Package 1.

**Dependencies:** Requires Package 4 complete. Can run in parallel with Packages 3, 5, and 6.

**Specifications:**
1. Preserve non-interactive default execution with explicit profiles and machine-friendly exit behavior.
2. Keep core install light; optional dependencies stay behind extras.
3. Clarify which install paths are for checkout/deploy automation versus normal `pip install scribe-mcp` consumers.
4. Do not absorb Codex or Claude bootstrap into the base installer.

**Patterns to Follow:**
- `install.sh` remains deterministic shell, not an interactive wizard.
- Package-first truth in `README.md` and `pyproject.toml` remains authoritative.

**Verification:**
- [ ] Installer profiles remain scriptable and documented.
- [ ] Core install path does not pull Postgres or S3 extras by default.
- [ ] Installer messaging matches the eventual public docs contract.

**Out of Scope:** Codex/Claude plugin bootstrap commands.

### Task Package 3 — Codex And Claude Plugin Bootstrap Parity Plus Shipped `scribe-integration`

**Type:** Code plus docs.

**Scope:** Replace the ambiguous Codex-only `project-codex` public surface with symmetric client bootstrap commands and ship `scribe-integration` in both bundles as the public-safe Scribe skill.

**Files to Modify:**
- `src/scribe_mcp/cli/main.py` — public plugin command surface.
- `src/scribe_mcp/scripts/project_codex_plugin.py` or successor client-bootstrap module(s).
- `plugins/codex/**` — plugin metadata, skill bundle, and agent references.
- `plugins/claude/**` — plugin metadata, skill bundle, and agent references.
- `.agents/plugins/marketplace.json` — public plugin discovery surface if still required.

**Files to Create:**
- `plugins/codex/skills/scribe-integration/SKILL.md` — public-safe Scribe-focused skill.
- `plugins/claude/skills/scribe-integration/SKILL.md` — matching Claude bundle skill.
- Optional shared bootstrap helper module(s) if needed to avoid duplicating client installation logic.

**Dependencies:** Requires Package 4 complete. Can run in parallel with Packages 2, 5, and 6.

**Specifications:**
1. Introduce first-class Codex and Claude install/bootstrap commands with symmetric naming.
2. Preserve compatibility for `project-codex` only if a short migration alias is needed.
3. Point shipped agent configs at `scribe-integration` instead of `scribe-mcp-usage`.
4. Keep bundle content public-safe and downstream-consumable.

**Patterns to Follow:**
- Existing bundle validation/projection logic in `project_codex_plugin.py`.
- Shipped plugin metadata under `plugins/codex/**` and `plugins/claude/**`.

**Verification:**
- [ ] Codex and Claude both have documented first-class bootstrap paths.
- [ ] `scribe-integration` ships in both bundles and is referenced by agent configs.
- [ ] Legacy naming does not remain the only public path.

**Out of Scope:** README/docs index finalization.

### Task Package 5 — Test/Public Split And Shipped Regression Contract Cleanup

**Type:** Code plus docs.

**Scope:** Define which regression assets belong in the public release surface, separate them from contributor-only or noisy internal tests, and align packaging with that policy.

**Files to Modify:**
- `MANIFEST.in` — explicit shipped-vs-dev test boundary.
- `tests/**` — organize or label the intentional public regression subset versus contributor-only/internal tests.
- Any minimal package/test documentation needed to explain the release regression contract.

**Dependencies:** Requires Package 4 complete. Can run in parallel with Packages 2, 3, and 6.

**Specifications:**
1. Replace the current one-off excluded-test rule with an intentional release regression policy.
2. Ensure shipped artifacts do not include noisy internal test junk.
3. Preserve contributor workflows for the full test suite.
4. Make the public regression contract reviewable and easy to verify.

**Patterns to Follow:**
- Keep packaging rules explicit in `MANIFEST.in` rather than relying on accidental inclusion or exclusion.
- Favor a named public regression subset over ad hoc file-by-file exceptions.

**Verification:**
- [ ] Packaging manifest encodes a principled test boundary.
- [ ] Public regression assets are intentionally named or grouped.
- [ ] Contributor-only tests remain available in-source without shipping by default.

**Out of Scope:** Broad test rewrites unrelated to release polish.

### Task Package 6 — Runtime/Terminology/Doc Contract Cleanup For Scribe Modes

**Type:** Code plus docs.

**Scope:** Normalize the public language for local/core, installed-package entrypoints, optional authenticated SSE, and optional authenticated remote/client posture so commands, env vars, and supporting docs tell one coherent story without touching README/file-map finalization.

**Files to Modify:**
- `docs/REMOTE_CLIENT.md` — client-side posture and auth naming.
- `docs/RELEASE_SURFACE.md` — release contract wording where mode labels appear.
- CLI/help text or entrypoint descriptions touched by naming drift.
- Supporting docs outside `README.md` and `docs/RELEASE_FILE_MAP.md` that must be correct before Package 1 finalizes the index.

**Dependencies:** Requires Package 4 complete. Can run in parallel with Packages 2, 3, and 5.

**Specifications:**
1. Make the four supported truths explicit: local/core stdio default, package entrypoints, optional authenticated SSE, optional authenticated remote/client.
2. Separate server-side auth token naming from client-side remote auth naming in docs.
3. Remove ambiguous phrasing that makes `scribe` look like the server process instead of the CLI dispatcher.
4. Feed the final normalized language into Package 1 without editing `README.md` or `docs/RELEASE_FILE_MAP.md`.

**Patterns to Follow:**
- Runtime truth documented in `.scribe/docs/dev_plans/scribe_release_polish_20260408/research/RESEARCH_RUNTIME_INTEGRATION_TRUTH_20260408.md`, specifically `# Summary`, `# Supported Modes and Intended Audience`, `# Export vs Runtime Contract`, and `# Naming and Contract Drift`.
- Existing entrypoints and transport semantics already implemented in code.

**Verification:**
- [ ] Docs and help text describe the same runtime modes.
- [ ] Token naming is separated clearly between server and client contexts.
- [ ] SSE posture and remote/client posture are not conflated.
- [ ] `README.md` and `docs/RELEASE_FILE_MAP.md` remain reserved for Package 1 finalization.

**Out of Scope:** New runtime capabilities and README/file-map finalization.

## Phase 3 — Public Docs Finalization

### Task Package 1 — Public Docs Truth And README/Docs Index Rewrite

**Type:** Docs only.

**Scope:** Rewrite the public-facing docs set so the final public story is accurate, complete, high-level at the README layer, and synchronized with the landed structural work.

**Files to Modify:**
- `README.md`
- `docs/GLOBAL_DEPLOYMENT_GUIDE.md`
- `docs/mcp_server_guide.md`
- `docs/whitepapers/scribe_mcp_whitepaper.md`
- `docs/RELEASE_FILE_MAP.md`
- `docs/BRIDGE_DEVELOPMENT.md` or other public docs that need index/cross-link cleanup

**Dependencies:** Requires Packages 2, 3, 4, 5, and 6 complete.

**Specifications:**
1. Keep README high-level, professional, and explicit about what Scribe is.
2. Make README the docs index for the important public docs and examples.
3. Keep the file map dedicated in `docs/RELEASE_FILE_MAP.md`; update it only after the structural packages land.
4. Rewrite older public docs so the primary flows are package-first and release-safe.
5. Ensure Codex and Claude plugin support, runtime posture language, and installer story all match the landed implementation.

**Patterns to Follow:**
- README is the front door, not the exhaustive manual.
- Use tracked docs/examples, never repo-local overlays, as public guidance.

**Verification:**
- [ ] README explains Scribe clearly and links the important docs.
- [ ] File map remains dedicated and reflects the landed structure.
- [ ] Deployment guide, server guide, and whitepaper no longer teach repo-local release paths as the primary public story.

**Out of Scope:** New product marketing or feature expansion.

## Phase 4 — Final Review And Signoff

### Task Package 8 — Final Review / Signoff Package

**Type:** Review only.

**Scope:** Validate that the final public surface, shipped bundles, runtime docs, hygiene boundaries, and security posture all match the contract before release signoff.

**Files to Inspect:**
- All files touched by Packages 1 through 7.
- Final planning docs and checklist proof.

**Dependencies:** Requires Packages 1 through 7 complete.

**Specifications:**
1. Re-run a bounded public-surface truth pass.
2. Re-run the narrow release-security sanity pass to confirm the blocker is gone.
3. Verify docs truth, plugin parity, installer truth, test/public split, and runtime terminology alignment.
4. Record explicit signoff or blocking findings.

**Verification:**
- [ ] No unresolved blocker remains.
- [ ] Review can map every landed change back to one package and checklist item.
- [ ] README/file-map finalization matches the actual landed structure.

**Out of Scope:** New implementation except for review-directed fixups.
