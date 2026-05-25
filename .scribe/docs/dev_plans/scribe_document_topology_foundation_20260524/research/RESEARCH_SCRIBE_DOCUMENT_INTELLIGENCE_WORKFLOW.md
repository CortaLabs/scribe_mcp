
# 🔬 Research Scribe Document Intelligence Workflow — scribe_document_topology_foundation_20260524
**Author:** Scribe
**Version:** v0.1
**Status:** in_progress
**Last Updated:** 2026-05-25 03:35:24 UTC

> Operator and agent workflow contract for deterministic document intelligence actions covering scan, repair, quality-gated handoff, ingestion inspection, and stale corpus cleanup without destructive guessing.

---
## Executive Summary
<!-- ID: executive_summary -->
This research defines a frictionless operator and agent workflow surface for Scribe document intelligence using existing managed-doc and quality surfaces, not parallel systems.

**Primary Objective:** Specify deterministic scan, repair, handoff, and ingestion-inspection actions that reduce manual metadata burden, preserve non-destructive safety, and produce machine-usable proof.

**Key Takeaways:**
- Existing flow evidence already supports a unified lifecycle: `set_project` for context binding, `manage_docs` for mutations and quality checks, structured warning/blocker payloads for readiness gating, and quality summaries that can drive handoff decisions.
- Workflow actions should be explicit and mode-safe: `topology_scan`, `metadata_scan`, `metadata_repair(report_only|repair_safe|repair_assisted)`, `ingestion_manifest_inspect`, `quality_handoff_check`, and `stale_cleanup_scan`.
- Batch repair must separate deterministic fixes from assisted fixes with rejection reason codes and proof fields so operators can approve intentionally and avoid destructive guessing.
- Stale/empty docs/projects should surface as report-first recommendations, including optional merge-to-sentinel-log plans, never silent deletion or irreversible mutation.
- Knowledge MCP handoff belongs at contract artifacts (ingestion manifest, topology index, rejection report), while Scribe remains source authority for lifecycle/quality truth.
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** DocWriterAgent

**Investigation Window:** 2026-05-24 — 2026-05-25

**Focus Areas:**
- Operator/agent managed-doc workflows evidenced in SPEC, Wave 1 synthesis, quality lifecycle audit, and ingestion boundary research.
- Contract shapes for scan/repair/index/handoff actions with deterministic fields and non-destructive lifecycle control.
- Repair batch UX split between report-only, safe auto-repair, and assisted-repair with explicit rejection/proof semantics.
- Stale/empty project and document surfacing + cleanup recommendations that preserve auditability.
- External handoff points for Knowledge MCP and public documentation/test requirements.

**Dependencies & Constraints:**
- No source code changes in this wave.
- No manual maintenance of fields Scribe can infer deterministically.
- No destructive deletion proposals without explicit report/confirm lifecycle.
- Reuse existing `quality_check` and readiness semantics; do not invent `quality_check_v2`.
- Maintain compatibility with current manage_docs warning/blocker response conventions.
## Findings
<!-- ID: findings -->
### Finding 1
- **Summary:** The current Scribe lifecycle already has the right operator touchpoints: project bind, managed-doc edit, quality proof, readiness summary, and structured warnings.
- **Evidence:** `SPEC.md`; `SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY.md`; `RESEARCH_SCRIBE_QUALITY_LIFECYCLE.md` (quality_check as canonical gate and blocker semantics); project `read_recent` evidence showing quality-check gating and scaffold blocker policy.
- **Confidence:** High

### Finding 2
- **Summary:** A frictionless workflow should be action-oriented and deterministic, with each action returning both human summary and machine-proof payload.
- **Evidence:** Wave 1 synthesis requirement for operator/agent workflow lane plus ingestion-boundary requirement for deterministic manifest/rejection-coded flows.
- **Confidence:** High

### Finding 3
- **Summary:** Repair operations need a three-mode model to protect trust: `report_only` (discover), `repair_safe` (deterministic auto-fix only), and `repair_assisted` (operator-confirmed ambiguous changes).
- **Evidence:** SPEC non-goals prohibit guessing/manual over-maintenance; quality lifecycle findings show blocker-compatible semantics already exist; ingestion boundary research defines rejection-code model.
- **Confidence:** High

### Finding 4
- **Summary:** Stale/empty cleanup needs explicit recommendation artifacts and confirm steps, including optional merge-to-sentinel-log plans for project retirement evidence.
- **Evidence:** Mission constraints prohibit destructive deletion guessing; Wave doctrine emphasizes recoverable audit trail and handoff-proof logging.
- **Confidence:** Medium

### Finding 5
- **Summary:** Knowledge MCP handoff should occur only after Scribe quality/eligibility checks produce stable topology + ingestion artifacts.
- **Evidence:** `RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY.md` responsibility split and rejection reason catalog.
- **Confidence:** High
## Technical Analysis
<!-- ID: technical_analysis -->
**Code/Contract Patterns Identified:**
- Existing managed-doc contract already supports structured quality outputs with warning code, severity, blocking, location, and suggested repair.
- Quality summary/readiness path already produces blocker counts suitable for handoff gating.
- Managed-doc creation and section replacement flows provide deterministic edit traces and ownership context.

**Proposed Operator/Agent Action Surface (Workflow Contracts):**
- `topology_scan`
  - Purpose: Build deterministic doc/work topology snapshot without mutating docs.
  - Inputs: `project`, optional `doc_types[]`, `statuses[]`, `paths[]`, `include_edges`, `include_cycles`.
  - Expected response: `summary` counts + `nodes[]`, `edges[]`, `anomalies[]`, `scan_proof` (`run_id`, `generated_at`, `source_paths`, `hash_algo`).
- `metadata_scan`
  - Purpose: Detect missing/invalid/inferred metadata drift.
  - Inputs: scope filters + `strictness` + `include_inferred`.
  - Expected response: `issues[]` with `issue_code`, `doc_ref`, `field`, `current_value`, `inferred_value`, `repair_mode_hint`.
- `metadata_repair`
  - Modes: `report_only`, `repair_safe`, `repair_assisted`.
  - Expected response: `mode`, `evaluated`, `repaired`, `skipped`, `requires_confirmation`, `rejections[]`, `proof[]`.
- `quality_handoff_check`
  - Purpose: Evaluate whether an agent can mark handoff/clock-out cleanly.
  - Inputs: `agent`, `project`, optional `owned_docs[]`.
  - Expected response: `handoff_allowed`, `blocking_warning_count`, `blocking_codes[]`, `doc_failures[]`, `repair_plan_ref`.
- `ingestion_manifest_inspect`
  - Purpose: Preview Scribe-to-Knowledge eligibility and rejection causes.
  - Inputs: project/scope + optional status allowlist.
  - Expected response: `eligible_docs[]`, `rejected_docs[]`, `rejection_summary`, `manifest_preview`, `topology_index_ref`.
- `stale_cleanup_scan`
  - Purpose: Surface stale/empty docs/projects with non-destructive recommendations.
  - Inputs: inactivity thresholds + orphan detection flags.
  - Expected response: `stale_candidates[]`, `empty_candidates[]`, `risk_flags[]`, `recommended_actions[]`, `requires_confirm=true` for destructive classes.

**Repair Batch UX Contract:**
- `report_only`: never mutates content; emits full findings with recommended patch class.
- `repair_safe`: applies only deterministic transforms, for example: normalize header levels, regenerate TOC, infer missing immutable derivatives (`doc_id` from canonical naming rules), normalize known status aliases, fill machine-derivable fields.
- `repair_assisted`: proposes patches for ambiguous fields/links and requires explicit operator confirmation per batch or per doc.
- Required rejection reason codes:
  - `REJECT_AMBIGUOUS_OWNER`
  - `REJECT_CONFLICTING_CANONICAL_ID`
  - `REJECT_MULTIPLE_PLAUSIBLE_STATUSES`
  - `REJECT_UNRESOLVED_EDGE_TARGET`
  - `REJECT_DESTRUCTIVE_OPERATION_UNCONFIRMED`
  - `REJECT_EXTERNAL_CONTRACT_MISSING`
- Required proof fields per repair item:
  - `doc_ref`, `issue_code`, `mode`, `before_hash`, `after_hash` (if changed), `change_class`, `rule_id`, `applied_by`, `applied_at_utc`, `quality_delta`, `rollback_hint`.

**Stale/Empty Surfacing + Merge-to-Sentinel Recommendation Model:**
- Classify candidates without deletion:
  - `empty_scaffold_doc`, `stale_in_progress_doc`, `orphaned_project`, `duplicate_workstream_doc`.
- Emit recommendation bundles:
  - `keep_with_status_update`, `archive_recommendation`, `merge_to_sentinel_log_recommendation`, `operator_review_required`.
- Merge-to-sentinel recommendation must include non-destructive plan only:
  - source doc refs, extracted key events, unresolved blockers, and suggested sentinel entry payload.
- Destructive actions require explicit two-step lifecycle:
  - Step 1 report with impact preview.
  - Step 2 explicit confirm token or operator flag before any destructive operation.

**Knowledge MCP Handoff Points:**
- Handoff artifact set:
  - `knowledge_ingestion_manifest.json`
  - `doc_topology.json`
  - `rejection_report.json`
- Contract boundary:
  - Scribe owns lifecycle truth, topology edges, quality gating, and rejection reasons.
  - Knowledge MCP owns embedding/index/retrieval semantics and downstream ranking.

**Risk Assessment:**
- Over-automation risk is controlled by mode separation and rejection-coded assisted flow.
- False cleanup risk is controlled by report-first recommendations and explicit confirmation gates.
- Contract drift risk is controlled by versioned response schemas and test fixtures for backward compatibility.
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
- Define and review the proposed action contract names and response schemas in Blueprint packaging, preserving existing quality-check top-level compatibility.
- Add workflow-level acceptance criteria for `report_only`, `repair_safe`, and `repair_assisted` with explicit rejection code coverage.
- Add handoff gate requirement: `quality_handoff_check` must return `handoff_allowed=true` before clean clock-out/handoff claims for owned managed docs.
- Define stale/empty cleanup as recommendation-first with mandatory confirm lifecycle for destructive classes.
- Define ingestion inspection artifacts and schema versioning for Knowledge MCP handoff.

### Test and Documentation Requirements
- Tests:
  - Contract tests for each action response shape and required proof fields.
  - Deterministic repair tests showing only `repair_safe` performs auto-mutations.
  - Assisted-flow tests verifying ambiguous items are rejected with explicit reason codes.
  - Handoff-gate tests proving blocker warnings prevent clean handoff.
  - Cleanup-flow tests proving no destructive mutations occur without confirm.
  - Ingestion inspection tests proving eligibility/rejection summary parity with manifest output.
- Documentation:
  - Operator runbook for scan -> repair -> quality handoff -> ingestion inspect.
  - Agent quick-reference for choosing repair mode and interpreting rejection reasons.
  - Schema reference docs for topology scan, repair proof, and ingestion manifest inspection payloads.
## Appendix
<!-- ID: appendix -->
- **Required source docs reviewed:**
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/SPEC.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY.md`
  - `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_SCRIBE_QUALITY_LIFECYCLE.md`
- **Related evidence:** project `read_recent` entries for Wave 1/Wave 2 gates and scaffold-blocker doctrine.
- **Output artifact:** `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_SCRIBE_DOCUMENT_INTELLIGENCE_WORKFLOW.md`
