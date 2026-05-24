# 🔬 Research Quality Check Operations Release — quality_check_infrastructure_20260524
**Author:** ptah
**Version:** v0.1
**Status:** in_progress
**Last Updated:** 2026-05-24 03:22 UTC

> Operations and release-gating research for quality_check infrastructure

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Define an operations-safe and release-useful quality_check model that stays deterministic and fast by default, while supporting stronger optional gates for release closeout and runtime proof.

**Key Takeaways:**
- quality_check should use tiered gates: cheap local defaults, stronger optional release gates, and explicit operator-invoked live/runtime proofs.
- Output must remain machine-readable and stable (`code`, `severity`, `blocking`, `location`, `next_actions`) so CI/release tooling can consume it without parsing prose.
- Reuse existing seams (`runtime._handle_quality_check`, collector helpers, changelog/version context helpers) and avoid parallel rule engines.
- Performance safety depends on bounded default scope (changed docs first), deterministic checks, and cache-by-content-hash with explicit invalidation.
- The tool should catch release-closeout misses earlier: changelog/version coverage drift, unresolved scaffold blockers, and readiness-state mismatch.

**Confidence:** High for gate taxonomy and output contract; Medium for caching details pending profiling.

---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ptah

**Investigation Window:** 2026-05-23 — 2026-05-24

**Focus Areas:**
- Operational gate design for local, CI, and release usage.
- Output payload shape for agent and automation consumption.
- Interaction model with git hygiene, tests, changelog tooling, and version surfaces.
- Failure modes observed in prior Scribe release work that should be caught earlier.
- Runtime, cache, and config hazards that can make checks brittle or slow.

**Dependencies & Constraints:**
- Source-map findings from `RESEARCH_QUALITY_CHECK_SOURCE_MAP` are treated as current code truth.
- Scope is operations/release research only; no source edits, CI edits, packaging changes, or architecture commitments.
- Recommendations must preserve lightweight deterministic defaults and avoid mandatory heavy runtime dependencies.

---
## Findings
<!-- ID: findings -->
### Finding 1
- **Summary:** A three-tier gate model keeps quality_check useful without slowing daily work.
  - Tier A (default local): deterministic checks on changed/target docs only, no network/runtime calls.
  - Tier B (optional release/CI): expanded scope plus release-aware checks (changelog/version coverage, project-health quality aggregation).
  - Tier C (operator-invoked): live runtime proof checks for MCP route behavior and warning payload contract.
- **Evidence:** SPEC goals for lightweight deterministic checks and release hazard coverage; source-map confirmation that routing and collectors are centralized and reusable.
- **Confidence:** High

### Finding 2
- **Summary:** Output contract quality determines automation value. Each warning should expose stable machine fields: `code`, `severity`, `blocking`, `message`, `location{path,line_start,line_end}`, `excerpt`, `category`, `next_actions[]`, and top-level summary totals by severity/blocking.
- **Evidence:** Existing quality_check already emits structured warnings with codes/severity/blocking/location; this structure can be normalized and extended rather than replaced.
- **Confidence:** High

### Finding 3
- **Summary:** Integration points should be explicit rather than implicit.
  - `git diff --check` remains a separate low-cost whitespace gate run alongside quality_check.
  - test execution remains separate but should consume quality_check summary in closeout scripts.
  - `preview_reconciliation` and `apply_global_changelog` should be called as release-lane companions when changelog coverage warnings fire.
  - release version surfaces (`pyproject` version context) should be checked for accepted changelog coverage before ship.
- **Evidence:** Active project reminders already flag changelog coverage blockers; source-map lists changelog/version helpers used by quality warnings.
- **Confidence:** High

### Finding 4
- **Summary:** Prior release-work failure modes suggest early guardrails quality_check should catch before late-stage closeout.
  - scaffold residue left in research/review docs,
  - mismatch between doc status claims and scaffold-quality blockers,
  - missing accepted changelog entries for current release version,
  - path/alias recovery ambiguity around explicit markdown doc targets.
- **Evidence:** Source-map notes runtime path-recovery complexity and reminder patterns show recurring scaffold/changelog blockers.
- **Confidence:** Medium-High

### Finding 5
- **Summary:** Runtime/caching hazards to avoid.
  - global mutable caches without keying on file content hash plus checker config,
  - hidden network or subprocess dependencies in default quality_check path,
  - non-deterministic warning ordering that breaks CI baselines,
  - mode-dependent behavior not encoded in output metadata (`mode`, `scope`, `runtime_proof`).
- **Evidence:** SPEC requires deterministic lightweight local checks and additive compatibility; operational reliability requires reproducible outputs.
- **Confidence:** Medium
### Additional Notes
- `scaffold_quality.py` is already a pressure point; operations guidance should prefer composable collector registration over branching runtime logic.
- Keep warning codes forward-compatible and avoid frequent renames that break CI policies.

---
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- The runtime route (`_handle_quality_check`) is the control plane for target resolution and response assembly; keep it thin.
- Warning construction should stay collector-driven with a stable normalization layer before output.
- Release-aware checks should reuse changelog/version helper functions instead of duplicating release logic in runtime.

**System Interactions:**
- Local default checks should run purely on repository content and managed-doc metadata.
- CI/release lanes can combine: quality_check plus `git diff --check` plus targeted tests plus changelog reconciliation preview.
- Live MCP runtime proof should be explicit opt-in and run after local deterministic checks pass, not on every invocation.

**Risk Assessment:**
- Risk: slow/brittle checks if release/runtime checks are forced into default path. Mitigation: tiered modes with explicit flags.
- Risk: contract drift for automation consumers. Mitigation: versioned output schema and stable warning codes.
- Risk: false positives from markdown heuristics. Mitigation: regression suite for nested/alternate fences, table cases, and alias-route coverage.
- Risk: stale cache after config/rule changes. Mitigation: include config fingerprint and file hash in cache key; invalidate on mode changes.

---
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
- Define explicit quality_check modes in contract docs: `local_default`, `release_gate`, `runtime_proof`.
- Lock warning payload schema and enumerated severities/blocking semantics for CI policy consumers.
- Add release-oriented checks as optional gates, not default blockers, including changelog/version coverage and reconciliation guidance hooks.
- Add deterministic ordering and summary digest fields to outputs for stable automation.
- Add focused regressions for known parser/route gaps from source-map findings.

### Long-Term Opportunities
- Add pluggable collector registry with per-doc-type/per-mode activation to prevent god-module growth.
- Add optional JSONL or SARIF-like export for CI ingestion while preserving existing API response compatibility.
- Add baseline/suppression ledger with expiry for non-blocking advisories in large doc migrations.
- Add optional lightweight cache layer with transparent hit/miss diagnostics.

### Release-Gate Taxonomy (Proposed)
- Cheap local defaults: scaffold residue, frontmatter/lifecycle readiness coherence, deterministic warning formatting, target-doc scope only.
- Optional release gates: changelog/version coverage, project-wide quality digests, reconciliation preview requirements, expanded scope scans.
- Explicit operator-invoked checks: live MCP runtime proof, route/alias compatibility proofs, container/wheel smoke proof integration.

---
## Appendix
<!-- ID: appendix -->
- **References:**
  - `.scribe/docs/dev_plans/quality_check_infrastructure_20260524/SPEC_QUALITY_CHECK_INFRASTRUCTURE.md`
  - `.scribe/docs/dev_plans/quality_check_infrastructure_20260524/research/RESEARCH_QUALITY_CHECK_SOURCE_MAP.md`
  - Source-map evidence pointers: `src/scribe_mcp/doc_management/runtime.py`, `scaffold_quality.py`, `changelog.py`, `version_context.py`, and quality-check test files listed in source-map appendix.
- **Automation-Oriented Output Shape (recommended):**
  - top-level: `ok`, `summary{total,blocking,by_severity}`, `mode`, `scope`, `warnings[]`
  - warning: `code`, `severity`, `blocking`, `message`, `category`, `location{path,line_start,line_end}`, `excerpt`, `next_actions[]`
- **Confidence Scores by Question:**
  - Gate cost model and mode split: 0.90
  - Output contract recommendations: 0.92
  - Integration with git/tests/changelog/version surfaces: 0.88
  - Early failure-mode capture set: 0.84
  - Runtime/caching hazard controls: 0.78
