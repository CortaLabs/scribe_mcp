
# 🔬 Research Scribe Quality Lifecycle — scribe_document_topology_foundation_20260524
**Author:** Scribe
**Version:** v0.1
**Status:** in_progress
**Last Updated:** 2026-05-25 03:09:32 UTC

> Quality lifecycle audit for integrating document topology into existing quality_check

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Determine how document-topology and lifecycle checks can be integrated into the existing `quality_check` gate without creating a second validator path or changing the canonical response contract.

**Key Takeaways:**
- `quality_check` is already the canonical proof path and the same implementation powers `scaffold_quality_check`.
- Blocker semantics already exist at the warning level, so new topology rules can plug into the existing `blocking` and `readiness_blocker_count` model.
- Readiness aggregation already consumes managed-doc quality output, but `status_update` and `frontmatter_update` do not currently call `quality_check` as a required guard for ready/complete transitions.
- Compatibility risk is low if the extension is additive and preserves the existing top-level keys and alias behavior.
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-Topology

**Investigation Window:** 2026-05-24 to 2026-05-25

**Focus Areas:**
- Existing `quality_check` and `scaffold_quality_check` handler flow, response compatibility, and blocker semantics.
- Warning schemas, `SCF_*` code families, and how blocker counts feed readiness.
- Status-transition behavior for `ready` and `complete` lifecycle states.
- Test coverage that already proves quality/readiness and alias compatibility.

**Dependencies & Constraints:**
- No source code edits in this wave.
- No rival `quality_check_v2` or parallel validator path.
- Compatibility with the current top-level response shape is mandatory.
- Any topology/lifecycle extension must be additive and must reuse the existing warning/blocker model.
## Findings
<!-- ID: findings -->
### Finding 1: `quality_check` is the single canonical proof path
- **Summary:** `quality_check` and `scaffold_quality_check` share the same runtime handler and return the same legacy top-level keys, so topology/lifecycle checks should extend this path instead of introducing a parallel validator.
- **Evidence:** `src/scribe_mcp/doc_management/runtime.py:870-1088`, `src/scribe_mcp/doc_management/runtime.py:1980-1995`, `src/scribe_mcp/tools/manage_docs.py:108-116`, `tests/test_manage_docs_quality_check.py:413-461`.
- **Confidence:** High

### Finding 2: Blocker semantics already drive quality status and readiness
- **Summary:** Warning payloads already carry `severity`, `blocking`, `location`, `message`, and `suggested_repair`; `summarize_quality_warnings` turns that into `readiness_blocker_count`, and `readiness.py` promotes blockers to project-level readiness failures.
- **Evidence:** `src/scribe_mcp/doc_management/scaffold_quality.py:158-170`, `src/scribe_mcp/doc_management/quality/results.py:10-50`, `src/scribe_mcp/readiness.py:48-150`, `tests/test_readiness.py:9-27`, `tests/test_readiness.py:96-110`.
- **Confidence:** High

### Finding 3: Existing SCF families already cover scaffold, lifecycle, research index, and release gating
- **Summary:** The current warning taxonomy includes scaffold residue, lifecycle mismatch, research index hygiene, changelog structure, and release-gate coverage. That means topology warnings can be added as a new family without changing the warning container contract.
- **Evidence:** `src/scribe_mcp/doc_management/scaffold_quality.py:26-50`, `src/scribe_mcp/doc_management/scaffold_quality.py:246-442`, `src/scribe_mcp/doc_management/quality/rules/scaffold.py:8-60`, `src/scribe_mcp/doc_management/quality/rules/research.py:22-131`, `src/scribe_mcp/doc_management/quality/rules/changelog.py:13-64`, `src/scribe_mcp/doc_management/quality/rules/release_gate.py:6-53`.
- **Confidence:** High

### Finding 4: Ready/complete transitions still need a direct quality gate
- **Summary:** The write pipeline removes `status` from `status_update` metadata before applying the frontmatter pipeline, but there is no evidence that the edit path itself requires a `quality_check` pass before `ready` or `complete` is written. The gating hook therefore needs to be added in the same status path, not as a separate validator service.
- **Evidence:** `src/scribe_mcp/doc_management/manager.py:813-852`, `src/scribe_mcp/doc_management/actions/edit.py:86-87,153-231`, `src/scribe_mcp/doc_management/validation.py:33-38`, `tests/test_manage_docs_status_intent_guardrails.py:14-170`.
- **Confidence:** Medium
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- `DEFAULT_WARNING_POLICIES` and `UNSUPPRESSIBLE_BLOCKER_CODES` define the gate contract for every `SCF_*` warning, including severity and whether suppression is allowed.
- `evaluate_scaffold_rules` composes the scaffold registry in a fixed order, and `collect_managed_doc_quality_warnings` layers on research-index, changelog, and release-mode checks before suppression/normalization.
- `normalize_warnings` preserves the old warning shape by adding default `category`, `gate_scope`, `scope_kind`, `suppressible`, `source_owner`, and `rule_version` fields.
- `summarize_quality_warnings` derives blocker counts directly from the warning list, so topology warnings only need to set `blocking` correctly to participate in readiness.
- `manager.apply_doc_change` already stores `scaffold_quality_warnings` after a write, which is a natural seam for post-write topology proof or recovery signals.

**System Interactions:**
- `manage_docs` routes both `quality_check` and `scaffold_quality_check` through the same runtime handler, so compatibility updates automatically apply to both entry points.
- `project_health` folds managed-doc quality into a larger readiness summary and uses the blocker count as one of its primary health signals.
- `rehome_doc` already records a `quality_check_binding` and `readiness` sub-structure, proving that quality output can be referenced by lifecycle operations without a new validator path.

**Risk Assessment:**
- New topology codes must remain additive or the existing response compatibility tests will fail.
- If the topology graph depends on a registry that is missing or stale, the gate must emit an explicit blocking warning rather than silently passing.
- Ready/complete enforcement should reuse the same quality result path as `quality_check`; otherwise the system will drift into a second validation contract that is harder to keep consistent.
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
- Add a new topology warning family to the same warning collection path used by `collect_managed_doc_quality_warnings`, with additive `SCF_*` codes for missing ID, duplicate ID, dangling edge, invalid status, missing summary, agent ID leakage, registry missing, cycles, ready depends on draft, and unresolved blockers.
- Make the readiness-critical topology codes blocking, and keep non-readiness hygiene codes advisory unless Blueprint explicitly defines otherwise.
- Wire ready/complete transitions to consult the same quality result path before persisting status changes, so `quality_check` remains the single validator source of truth.
- Preserve the current response shape, alias behavior, and legacy top-level keys exactly as they are today.
- Add tests that prove topology warnings are surfaced through `quality_check`, counted by readiness, and respected by status-transition guardrails.

### Long-Term Opportunities
- Add a reusable topology graph builder that can validate document IDs and edges from the existing doc registry and managed-doc metadata.
- Surface a small, structured readiness explanation in the status-transition response using the existing warning payload instead of a new contract.
- Expand `project_health` to summarize topology health alongside existing index and artifact-claim signals once the warning family is in place.
## Appendix
<!-- ID: appendix -->
- **References:**
  - `src/scribe_mcp/doc_management/runtime.py:870-1088`
  - `src/scribe_mcp/doc_management/runtime.py:1389-1461`
  - `src/scribe_mcp/doc_management/scaffold_quality.py:26-50, 246-442`
  - `src/scribe_mcp/doc_management/quality/results.py:10-50`
  - `src/scribe_mcp/readiness.py:48-150`
  - `src/scribe_mcp/doc_management/quality/rules/scaffold.py:8-60`
  - `src/scribe_mcp/doc_management/quality/rules/research.py:22-131`
  - `src/scribe_mcp/doc_management/quality/rules/changelog.py:13-64`
  - `src/scribe_mcp/doc_management/quality/rules/release_gate.py:6-53`
  - `tests/test_manage_docs_quality_check.py:57-461`
  - `tests/test_manage_docs_scaffold_quality.py:10-320`
  - `tests/test_manage_docs_project_health_quality.py:87-360`
  - `tests/test_manage_docs_cleanup_support.py:228-239`
  - `tests/test_manage_docs_status_intent_guardrails.py:14-170`
- **Attachments:**
  - Managed doc path: `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_SCRIBE_QUALITY_LIFECYCLE.md`
  - Research index: `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/INDEX.md`
