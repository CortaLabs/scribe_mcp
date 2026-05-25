---
id: scribe_document_topology_foundation_20260524-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_document_topology_foundation_20260524"
doc_type: architecture
doc_name: architecture
category: engineering
status: ready
version: Blueprint v1.0
last_updated: 2026-05-25 04:31:36 UTC
maintained_by: agent-20260525-041721-403c6ea5
created_by: agent-20260525-034854-92f169b6
owners:
- ArchitectAgent
related_docs: []
tags: []
summary: Decision-complete architecture contract for the Scribe Document Topology
  Foundation implementation stage.
edit_trace:
  tool: manage_docs
  created_at: 2026-05-25 04:03:59 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-05-25 04:31:36 UTC
  last_edited_by: agent-20260525-041721-403c6ea5
  last_action: replace_text
---
# 🏗️ Architecture Guide — scribe_document_topology_foundation_20260524
**Author:** ArchitectAgent
**Version:** Blueprint v1.0
**Status:** Ready
**Last Updated:** 2026-05-25 03:55 UTC

> Decision-complete implementation contract for the Scribe Document Topology Foundation mission.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
- **Context:** Scribe already owns managed documents, frontmatter mutation, quality checks, project registration, and special index generation, but it does not yet act as a deterministic authority for document topology, lifecycle truth, and downstream ingestion/export eligibility.
- **Primary Outcome:** extend the existing Scribe document lifecycle so the same managed-doc truth surface can answer what a document is, who owns it, what it depends on, whether it is quality-clean, whether it is safe to hand off, and whether it is eligible for sanitized downstream export.
- **Goals:**
  - Canonical metadata contract with stable identity, display-name-first attribution, lifecycle status, and typed topology edges.
  - Backward-compatible doc_type expansion through aliasing instead of breaking existing handlers.
  - Deterministic structural parsing and target resolution using existing helpers plus `markdown-it-py` where richer tokenization is needed.
  - Integration of topology, lifecycle, and handoff findings into the existing `manage_docs(action="quality_check")` path.
  - Derived v1 indexes and a managed downstream ingestion/export contract document without adding a second registry or forcing a storage migration.
- **Non-Goals:**
  - No `quality_check_v2` or parallel validator.
  - No semantic inference, embeddings, LLM classification, or Graph RAG logic inside Scribe.
  - No second metadata store or second document registry.
  - No v1 storage schema migration unless implementation uncovers a direct blocker and returns through review.
- **Success Metrics:**
  - `ready` and `complete` transitions are quality-gated and topology-aware.
  - Hard handoff and Scribe-owned clock-out fail mechanically when owned docs still have blocking scaffold or topology findings.
  - `.scribe/indexes/doc_topology.json`, `work_topology.json`, and `downstream_ingestion_manifest.json` generate deterministically from existing truth surfaces.
  - Downstream export records contain only publication-safe, repo-internal, rejection-coded data.

---
## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
  - Keep `id` as the canonical stable document identifier; do not invent a second stable-id subsystem.
  - Expand semantic doc types through aliasing while preserving current create handlers for `custom`, `spec`, `research`, `bug`, `security`, `review`, and `agent_card`.
  - Normalize attribution so `created_by` and `maintained_by` are human display names, with opaque runtime IDs retained only as secondary provenance fields.
  - Support canonical statuses `scaffolded`, `in_progress`, `ready`, `complete`, `stale`, `superseded`, `blocked`, and `archived`.
  - Support typed edge fields `depends_on`, `supports`, `validates`, `supersedes`, `blocked_by`, and `touches`, while keeping `related_docs` as the compatibility bridge.
  - Provide workflow actions for `topology_scan`, `metadata_scan`, `metadata_repair`, `quality_handoff_check`, `ingestion_manifest_inspect`, and `stale_cleanup_scan`.
  - Produce `DOWNSTREAM_INGESTION_CONTRACT.md` as a managed project deliverable.
- **Compatibility Constraints:**
  - Reuse `src/scribe_mcp/doc_management/actions/create.py`, `manager.py`, `runtime.py`, `special_indexes.py`, and the current warning payload contract.
  - Preserve legacy top-level quality keys and additive `SCF_*` warning semantics.
  - Prefer new helper modules over expanding `runtime.py` or `manager.py` further, but do not create a parallel subsystem.
- **Security Constraints:**
  - Downstream-facing artifacts may expose only repo-relative allowlisted paths.
  - Outside-repo discovered docs, archived/preflight/backup families, and quality-failing or ineligible-status docs are rejected by default.
  - User-authored `related_docs` and markdown links are untrusted until deterministic repo-internal resolution succeeds.
- **Operational Constraints:**
  - `set_project` is the clock-in surface.
  - Managed-doc ownership stays inside existing metadata fields: `owners` first, `maintained_by` second, `created_by` only as session/work-item fallback.
  - Creation itself is not quality-gated; readiness claims and handoff/clock-out are.

---
## 3. Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** build one additive document-intelligence layer on top of the current managed-doc lifecycle.
- **Component Breakdown:**
  - **Metadata and Lifecycle Contract**
    - Primary files: `src/scribe_mcp/doc_management/actions/create.py`, `src/scribe_mcp/config/repo_config.py`, `src/scribe_mcp/doc_management/manager.py`, `src/scribe_mcp/doc_management/lifecycle.py` (new).
    - Responsibility: semantic doc_type aliasing, lifecycle normalization, canonical metadata defaults, display-name attribution, and ownership scoping.
  - **Topology Normalization Layer**
    - Primary files: `src/scribe_mcp/doc_management/topology.py` (new), `src/scribe_mcp/doc_management/manager.py`, `src/scribe_mcp/doc_management/actions/query.py`.
    - Responsibility: parse typed edges, normalize mixed string/object entries, resolve targets, and detect hard-dependency cycles.
  - **Quality and Handoff Gate**
    - Primary files: `src/scribe_mcp/doc_management/quality/rules/topology.py` (new), `src/scribe_mcp/doc_management/scaffold_quality.py`, `src/scribe_mcp/doc_management/runtime.py`, `src/scribe_mcp/state/agent_manager.py`, `src/scribe_mcp/tools/set_project.py`.
    - Responsibility: integrate topology/lifecycle findings into `quality_check`, guard `ready` and `complete`, and block clean handoff or clock-out when owned docs still fail.
  - **Workflow Action Surface**
    - Primary files: `src/scribe_mcp/doc_management/runtime.py`, `src/scribe_mcp/doc_management/healing.py`, `src/scribe_mcp/doc_management/intelligence_workflows.py` (new).
    - Responsibility: expose scan/repair/inspect actions with deterministic proof payloads.
  - **Derived Export Artifacts**
    - Primary files: `src/scribe_mcp/doc_management/intelligence_exports.py` (new), `src/scribe_mcp/doc_management/special_indexes.py`, `src/scribe_mcp/doc_management/utils.py`.
    - Responsibility: generate `doc_topology.json`, `work_topology.json`, and `downstream_ingestion_manifest.json` with publication-safe fields and stable ordering.
- **Data Flow:**
  1. `set_project` binds agent, project, and authoritative session context.
  2. `manage_docs` create/edit/frontmatter paths normalize metadata and ownership.
  3. Topology helpers parse frontmatter/body structure and resolve graph targets.
  4. `quality_check` collects scaffold, lifecycle, topology, and export-eligibility findings through one warning pipeline.
  5. Status changes, explicit handoff checks, and Scribe-owned session teardown reuse that same warning summary.
  6. Derived export builders project the same truth into deterministic JSON artifacts and a managed contract doc.

---
## 4. Detailed Design
<!-- ID: detailed_design -->
### 4.1 Canonical Metadata Contract
- `id` remains the canonical stored identity field. Derived artifacts may expose `doc_id` as an alias, but Scribe does not add a second stored ID subsystem.
- `doc_type` remains the operational routing field. `intended_doc_type` is the v1 bridge when semantic type differs from the routed handler. Runtime-derived `canonical_doc_type = intended_doc_type or doc_type` is the value used by topology, quality, and export logic.
- Accepted semantic taxonomy for this mission: `architecture`, `spec`, `phase_plan`, `checklist`, `research`, `synthesis`, `review`, `security_review`, `bug_rca`, `progress_log`, `work_item`, `other`.
- `created_by` and `maintained_by` store display names. `created_by_id`, `maintained_by_id`, and `edit_trace.actor_id` carry opaque provenance only as secondary fields.
- Tool-authored and reserved fields remain `id`, attribution fields, and `edit_trace`. Export-only fields such as `visibility`, `sensitivity`, `path_policy`, `ingestion_eligibility`, `rejection_reasons`, `source_scope`, and `active_project_key` are derived, not manually maintained in v1.

### 4.2 Doc Type Alias and Expansion Strategy
- Extend alias/config resolution before adding new special handlers.
- Canonical-to-handler mapping:
  - `architecture`, `phase_plan`, `checklist`, `synthesis`, `progress_log`, `work_item`, `other` -> `custom` handler with template-backed creation.
  - `security_review` -> `security` handler.
  - `bug_rca` -> `bug` handler.
  - `review`, `research`, and `spec` stay on existing handlers.
- Preserve `requested_doc_type`, `resolved_doc_type`, `resolved_handler`, and `config_source` for transparency.

### 4.3 Lifecycle Model and Status Transitions
- Canonical statuses are `scaffolded`, `in_progress`, `ready`, `complete`, `stale`, `superseded`, `blocked`, and `archived`.
- Creation may yield `scaffolded` or `in_progress`; creation is never blocked for scaffold residue.
- `ready` requires zero blocking quality warnings, zero unresolved hard dependencies, and no hard-dependency cycle involving the document.
- `complete` requires the same checks as `ready` and may only advance from `ready` or an equivalently clean `in_progress` document.
- `stale`, `superseded`, `blocked`, and `archived` remain explicit state changes, but export eligibility logic deny-lists them.

### 4.4 Ownership and Handoff Scope
- Ownership precedence for handoff gating is `owners` first, `maintained_by` second, and `created_by` only as same-session or same-work-item fallback.
- `set_project` returns a `clock_in` summary with authoritative session context and any currently owned blocking docs, but it never rejects the bind.
- `quality_handoff_check` is a thin wrapper over the same warning collector used by `quality_check` plus ownership scoping.
- Blocked handoff logging must append a Scribe entry before returning failure with `agent`, `project`, `operation`, `session_id`, `docs[]`, `warning_codes`, `blocker_codes`, `total_blocker_count`, and `repair_summary`.

### 4.5 Typed Topology Edge Schema
- Keep `related_docs` as the compatibility bridge.
- Canonical edge fields are `depends_on`, `supports`, `validates`, `supersedes`, `blocked_by`, and `touches`.
- Authored forms may be either string refs such as `ARCHITECTURE_GUIDE#requirements_constraints` or structured refs such as `{target: "CHECKLIST#p1-metadata-contract", relation: "hard", note: "required for handoff"}`.
- Normalized internal records must include `edge_id`, `kind`, `source_doc_id`, `target_ref`, `target_doc_id`, `target_path`, `target_anchor`, `target_resolved`, `relation_strength`, `state`, `note`, and `source_field`.
- Only `depends_on`, `blocked_by`, and `supersedes` participate in cycle blocking for v1. `supports`, `validates`, `touches`, and `related_docs` remain non-blocking adjacency edges.

### 4.6 Deterministic Parsing and Resolution
- `parse_frontmatter` remains the YAML frontmatter entrypoint.
- `inspect_document_sections_from_text` remains the anchor inventory and heading fallback source.
- `markdown-it-py` is the only new parser dependency used for fence-aware markdown tokenization when body links or richer structure must be interpreted.
- Resolution order is: registered doc name or key, then repo-internal relative path under the project docs root, then explicit anchor, then heading-derived anchor only when no explicit anchor exists.
- Any target that resolves outside the active repo or active project docs roots is rejected as unsafe for topology and export use.

### 4.7 Quality Integration
- Topology and lifecycle rules plug into `collect_managed_doc_quality_warnings` and the existing normalization and summary path. No second validator is added.
- Required additive warning families cover invalid status, missing summary, primary opaque-ID leakage, missing semantic type bridge where aliasing requires it, unresolved targets, missing anchors, cross-project targets, hard-dependency cycles, dependency targets not in `ready|complete`, registry mismatch, and generic literal failed-write residue for all managed docs.
- The response contract keeps existing top-level keys and additive warning objects unchanged.

### 4.8 Workflow Actions
- `topology_scan` is a read-only snapshot of nodes, edges, anomalies, and cycle paths.
- `metadata_scan` reports missing or invalid metadata with inferred-value hints.
- `metadata_repair` supports `report_only`, `repair_safe`, and `repair_assisted`.
- `stale_cleanup_scan` emits non-destructive stale, orphan, and duplicate recommendations with explicit confirm requirements for destructive classes.
- `ingestion_manifest_inspect` previews export eligibility and rejection reasons from the same builders used for final manifest generation.

### 4.9 Derived Indexes and Downstream Contract
- v1 artifact location is `.scribe/indexes/`.
- Required artifacts are `doc_topology.json`, `work_topology.json`, and `downstream_ingestion_manifest.json`.
- Determinism requirements are stable schema versions, stable key ordering, sorted arrays, and repeated-run byte identity when inputs do not change.
- The export projector may emit only allowlisted fields; it must never mirror raw registry rows, absolute repo roots, raw resolved link paths, or arbitrary frontmatter maps.
- The managed contract doc must be created at `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/DOWNSTREAM_INGESTION_CONTRACT.md`.
- Scribe owns deterministic truth plus sanitized exports; downstream consumers own retrieval, embeddings, Graph RAG traversal, ranking, and model-based classification. Knowledge MCP may remain only as an optional council-private example adapter outside Scribe public core.

---
## 5. Directory Structure (Keep Updated)
<!-- ID: directory_structure -->
```text
src/scribe_mcp/
  config/repo_config.py                         # alias matrix and create-time config
  doc_management/
    actions/create.py                           # doc_type resolution hooks
    actions/query.py                            # section and anchor reuse where needed
    manager.py                                  # frontmatter defaults, attribution, status-gate hook
    runtime.py                                  # manage_docs action routing and shared quality/handoff entrypoints
    scaffold_quality.py                         # warning registry composition
    special_indexes.py                          # generated index emission and sync
    lifecycle.py                                # NEW: status normalization and eligibility helpers
    topology.py                                 # NEW: typed-edge normalization, resolution, cycles
    intelligence_workflows.py                   # NEW: scan and repair helper surface
    intelligence_exports.py                     # NEW: deterministic index and manifest builders
    quality/rules/topology.py                   # NEW: topology and lifecycle warning producer
  state/agent_manager.py                        # Scribe-owned end_session preflight
  tools/set_project.py                          # clock_in summary integration

.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/
  ARCHITECTURE_GUIDE.md
  PHASE_PLAN.md
  CHECKLIST.md
  DOWNSTREAM_INGESTION_CONTRACT.md              # planned implementation deliverable

tests/
  test_document_topology_metadata.py            # NEW
  test_document_topology_parsing.py             # NEW
  test_document_topology_quality.py             # NEW
  test_document_handoff_gate.py                 # NEW
  test_document_intelligence_workflows.py       # NEW
  test_document_topology_exports.py             # NEW
```

---
## 6. Data & Storage
<!-- ID: data_storage -->
- **Authoritative truth surfaces for v1:** managed markdown documents, existing project `docs_json` registration state, deterministic hashes from current utilities, current quality outputs, and filesystem mtimes.
- **No storage migration in v1:** topology and ingestion outputs are derived artifacts only. If implementers encounter a direct blocker that truly requires new persisted columns or tables, they must stop and return through review with evidence.
- **Artifact schemas:**
  - `doc_topology.json` carries document-level metadata plus edge records.
  - `work_topology.json` carries workstream, phase, checklist, and blocker rollups.
  - `downstream_ingestion_manifest.json` carries safe eligibility records and rejection summaries.
- **Security posture:** export `path` only when repo-relative and allowlisted; outside-repo discovered docs become `local_only` or rejected; archived/preflight/backup families and statuses outside `ready` or `complete` are rejected; arbitrary frontmatter pass-through is forbidden in export builders.

---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
- Add focused contract tests:
  - `tests/test_document_topology_metadata.py` for aliasing, canonical semantic type derivation, status normalization, and display-name attribution.
  - `tests/test_document_topology_parsing.py` for edge normalization, repo-internal resolution, anchor lookup, and cycle detection.
  - `tests/test_document_topology_quality.py` for additive `SCF_*` topology and lifecycle warnings through the existing quality path.
  - `tests/test_document_handoff_gate.py` for readiness claims, ownership precedence, blocked handoff logging, and Scribe-owned session teardown preflight.
  - `tests/test_document_intelligence_workflows.py` for scan and repair mode contracts plus stale cleanup safety.
  - `tests/test_document_topology_exports.py` for deterministic repeated generation, export sanitization, and rejection-code parity.
- Keep these regressions green: `tests/test_manage_docs_create_doc.py`, `tests/test_frontmatter.py`, `tests/test_manage_docs_quality_check.py`, `tests/test_manage_docs_status_intent_guardrails.py`, and `tests/test_readiness.py`.
- Use the canonical `test_agent` fixture; do not invent custom persona names.
- Verification commands:
  - `pytest -q tests/test_document_topology_metadata.py tests/test_manage_docs_create_doc.py tests/test_frontmatter.py`
  - `pytest -q tests/test_document_topology_parsing.py tests/test_document_topology_quality.py tests/test_manage_docs_quality_check.py tests/test_readiness.py`
  - `pytest -q tests/test_document_handoff_gate.py tests/test_manage_docs_status_intent_guardrails.py`
  - `pytest -q tests/test_document_intelligence_workflows.py tests/test_document_topology_exports.py`

---
## 8. Deployment & Operations
<!-- ID: deployment_operations -->
- Rollout remains additive, source-compatible, and derived-only.
- Regeneration triggers are explicit generation or inspect actions plus targeted post-mutation refresh where current managed-doc flows already regenerate special indexes. No hidden background daemon is introduced in v1.
- Scribe-owned `end_session` must consult the same preflight as `quality_handoff_check`. External Council session close must call the Scribe preflight rather than re-implement its own validator.
- Blocked handoff writes an additive Scribe log entry and returns the same warning payload family used by `quality_check`.
- Only sanitized derived index artifacts may sync by default; raw unsafe export mirrors never do.

---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
- No blocking architecture questions remain for v1.
- Deferred follow-ups after v1 ships:
  - Measure whether full derived regeneration is expensive enough to justify an internal cache layer.
  - Decide whether future cross-repo export is ever allowed; v1 assumes it is not.
  - Consider a richer public or operator field-reference doc once the contract stabilizes in source and tests.

---
## 10. References & Appendix
<!-- ID: references_appendix -->
- `SPEC.md`
- `SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY.md`
- `SYNTHESIS_WAVE_2_DOCUMENT_INTELLIGENCE.md`
- `research/RESEARCH_SCRIBE_METADATA_SURFACE.md`
- `research/RESEARCH_SCRIBE_DOC_REGISTRATION.md`
- `research/RESEARCH_SCRIBE_QUALITY_LIFECYCLE.md`
- `research/RESEARCH_SCRIBE_STRUCTURAL_TOPOLOGY.md`
- `research/RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY.md`
- `research/RESEARCH_SCRIBE_HANDOFF_GATE_LIFECYCLE.md`
- `research/RESEARCH_SCRIBE_TOPOLOGY_SECURITY_BOUNDARY.md`
- `research/RESEARCH_SCRIBE_DOC_TYPE_TEMPLATE_GOVERNANCE.md`
- `research/RESEARCH_SCRIBE_TOPOLOGY_INDEX_IMPLEMENTATION.md`
- `research/RESEARCH_SCRIBE_DOCUMENT_INTELLIGENCE_WORKFLOW.md`
- Verified implementation seams: `src/scribe_mcp/doc_management/actions/create.py`, `src/scribe_mcp/doc_management/runtime.py`, `src/scribe_mcp/doc_management/manager.py`, `src/scribe_mcp/doc_management/special_indexes.py`

---
