---
id: scribe_document_topology_foundation_20260524-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_document_topology_foundation_20260524"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: ready
version: Blueprint v1.0
last_updated: 2026-05-25 04:34:06 UTC
maintained_by: agent-20260525-041721-403c6ea5
created_by: agent-20260525-034854-92f169b6
owners:
- ArchitectAgent
related_docs: []
tags: []
summary: Ordered Forge package contract for the Scribe Document Topology Foundation
  implementation stage.
edit_trace:
  tool: manage_docs
  created_at: 2026-05-25 04:04:12 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-05-25 04:34:06 UTC
  last_edited_by: agent-20260525-041721-403c6ea5
  last_action: replace_range
---
# ⚙️ Phase Plan — scribe_document_topology_foundation_20260524
**Author:** ArchitectAgent
**Version:** Blueprint v1.0
**Status:** Ready
**Last Updated:** 2026-05-25 04:02 UTC

> Ordered Forge package contract for the Scribe Document Topology Foundation implementation stage.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Coherent Outcome | Depends On | Primary Surfaces | Verification Gate |
|-------|------------------|------------|------------------|-------------------|
| Phase 1 | Canonical metadata, doc_type aliasing, lifecycle normalization, and display-name attribution are wired into current create/frontmatter flows | Pre-implementation review pass | `actions/create.py`, `repo_config.py`, `manager.py`, `lifecycle.py` | Metadata contract tests + legacy create/frontmatter regressions |
| Phase 2 | Typed topology normalization, deterministic target resolution, and cycle detection exist as reusable helpers | Phase 1 | `topology.py`, `actions/query.py`, `manager.py` | Parsing/resolution tests |
| Phase 3 | Existing `quality_check` becomes topology-aware, handoff-aware, and lifecycle-gating without a second validator | Phases 1-2 | `runtime.py`, `scaffold_quality.py`, `quality/rules/topology.py`, `state/agent_manager.py`, `tools/set_project.py` | Quality, handoff, and status-gate tests |
| Phase 4 | Scan and repair workflows expose deterministic, non-destructive operator actions | Phases 1-3 | `runtime.py`, `healing.py`, `intelligence_workflows.py` | Workflow contract tests |
| Phase 5 | Derived indexes, ingestion inspection, and the generic downstream contract doc ship with security filtering and deterministic output | Phases 1-4 | `intelligence_exports.py`, `special_indexes.py`, `runtime.py`, project managed docs | Export determinism, sanitization, and contract-doc quality proof |

Parallelism note: because `manager.py` and `runtime.py` are shared choke points, the phases above should execute sequentially. Test authoring inside a phase can parallelize only after the helper/module interfaces for that phase are committed.

---
## Phase 1 — Metadata Contract And Doc-Type Expansion
<!-- ID: phase_1 -->
### Task Package: 1.1 — Canonical Metadata And Lifecycle Contract
**Scope:** Make the current create/frontmatter path understand the canonical semantic doc taxonomy, lifecycle normalization, and display-name-first attribution without breaking existing handlers.

**Files to Modify:**
- `src/scribe_mcp/doc_management/actions/create.py` — preserve current create routing while honoring canonical semantic aliases.
- `src/scribe_mcp/config/repo_config.py` — declare the alias matrix and template-backed canonical create families.
- `src/scribe_mcp/doc_management/manager.py` — normalize frontmatter defaults, reserved attribution, and lifecycle fields.
- `tests/test_manage_docs_create_doc.py` — expand create-time alias and transparency coverage.
- `tests/test_frontmatter.py` — expand reserved-field and attribution coverage.

**Files to Create:**
- `src/scribe_mcp/doc_management/lifecycle.py` — canonical status normalization, semantic doc type derivation, and export-eligibility helpers.
- `tests/test_document_topology_metadata.py` — focused metadata and lifecycle contract coverage.

**Dependencies:**
- Requires pre-implementation review pass.

**Specifications:**
1. Keep `id` as the only stored canonical identity field.
2. Preserve `doc_type` as the operational routing field and derive `canonical_doc_type` from `intended_doc_type or doc_type`.
3. Map canonical semantic types through alias resolution instead of adding new special handlers unless a later phase proves one is required.
4. Normalize `created_by` and `maintained_by` to display names, storing opaque identifiers only in secondary provenance fields.
5. Centralize canonical status parsing in `lifecycle.py` and reject non-canonical values in the same validation pipeline.

**Patterns to Follow:**
- Match alias resolution style already present in `src/scribe_mcp/doc_management/actions/create.py`.
- Match reserved-field enforcement and frontmatter mutation style in `src/scribe_mcp/doc_management/manager.py`.

**Verification:**
- `pytest -q tests/test_document_topology_metadata.py tests/test_manage_docs_create_doc.py tests/test_frontmatter.py`
- Existing legacy create doc types still pass unchanged.

**Out of Scope:**
- Topology parsing, quality warnings, handoff gating, and export artifact generation.

---
## Phase 2 — Typed Topology Foundation
<!-- ID: phase_2 -->
### Task Package: 2.1 — Deterministic Edge Normalization And Resolution
**Scope:** Add reusable topology helpers that parse typed edges, resolve only repo-internal targets, and detect hard-dependency cycles.

**Files to Modify:**
- `src/scribe_mcp/doc_management/manager.py` — hand the compatibility `related_docs` surface into the new topology helper.
- `src/scribe_mcp/doc_management/actions/query.py` — reuse section and anchor discovery where target validation needs it.

**Files to Create:**
- `src/scribe_mcp/doc_management/topology.py` — edge parsing, normalization, resolution, and cycle detection.
- `tests/test_document_topology_parsing.py` — typed-edge parsing, allowlisting, anchor resolution, and cycle tests.

**Dependencies:**
- Requires Package 1.1 complete for canonical metadata and status helpers.

**Specifications:**
1. Accept string and structured edge entries across `depends_on`, `supports`, `validates`, `supersedes`, `blocked_by`, `touches`, and `related_docs`.
2. Normalize each edge into one internal record shape with stable `edge_id` generation.
3. Resolve targets in deterministic order: registered doc key, repo-internal relative path, explicit anchor, derived anchor fallback.
4. Reject outside-repo and cross-project targets before they become trusted edges.
5. Detect cycles only on hard dependency edges: `depends_on`, `blocked_by`, and `supersedes`.

**Patterns to Follow:**
- Reuse `parse_frontmatter` and `inspect_document_sections_from_text`; do not invent a second parser stack.
- Use `markdown-it-py` only for deterministic tokenization gaps that current helpers do not already cover.

**Verification:**
- `pytest -q tests/test_document_topology_parsing.py`
- Hard dependency cycles produce stable cycle-path payloads.

**Out of Scope:**
- Quality integration, handoff enforcement, scan/repair actions, and export builders.

---
## Phase 3 — Quality, Lifecycle, And Handoff Enforcement
<!-- ID: phase_3 -->
### Task Package: 3.1 — Single-Path Quality And Handoff Gate
**Scope:** Extend the current `quality_check` path so topology, lifecycle, failed-write residue, readiness claims, and Scribe-owned clock-out all share one blocking contract.

**Files to Modify:**
- `src/scribe_mcp/doc_management/runtime.py` — shared quality-handoff helper, status-gate routing, and explicit `quality_handoff_check` action.
- `src/scribe_mcp/doc_management/scaffold_quality.py` — register additive topology/lifecycle and generic failed-write residue warnings.
- `src/scribe_mcp/state/agent_manager.py` — Scribe-owned teardown preflight.
- `src/scribe_mcp/tools/set_project.py` — additive `clock_in` summary for already-owned blockers.
- `tests/test_manage_docs_quality_check.py` — legacy quality contract regression coverage.
- `tests/test_manage_docs_status_intent_guardrails.py` — status-gate enforcement coverage.
- `tests/test_readiness.py` — blocker propagation coverage.

**Files to Create:**
- `src/scribe_mcp/doc_management/quality/rules/topology.py` — additive topology and lifecycle warning producer.
- `tests/test_document_topology_quality.py` — topology/lifecycle quality rule coverage.
- `tests/test_document_handoff_gate.py` — blocked handoff, blocked session end, and ownership-precedence coverage.

**Dependencies:**
- Requires Packages 1.1 and 2.1 complete because the gate depends on canonical status and normalized topology results.

**Specifications:**
1. Add topology and lifecycle warnings to the existing warning collection path with additive `SCF_*` codes only.
2. Gate `ready` and `complete` mutations on the same quality summary path used by `quality_check`.
3. Add one generic document-wide failed-write residue blocker instead of keeping that rule changelog-only.
4. Implement `quality_handoff_check` using ownership precedence `owners -> maintained_by -> created_by fallback`.
5. Block Scribe-owned `end_session` when the active agent still owns docs with blocking warnings; external Council wrappers must call the same preflight instead of re-implementing it.
6. Append a structured blocked-handoff log entry before returning any failure.

**Patterns to Follow:**
- Match the current warning normalization and `readiness_blocker_count` contract.
- Match existing readiness summaries; do not add a second validator response schema.

**Verification:**
- `pytest -q tests/test_document_topology_quality.py tests/test_document_handoff_gate.py tests/test_manage_docs_quality_check.py tests/test_manage_docs_status_intent_guardrails.py tests/test_readiness.py`
- A doc with scaffold blockers cannot transition to `ready` or end a Scribe-owned session cleanly.

**Out of Scope:**
- Batch repair, stale cleanup, final export builders, and the downstream contract doc body.

---
## Phase 4 — Scan And Repair Workflow Surface
<!-- ID: phase_4 -->
### Task Package: 4.1 — Deterministic Scan And Safe Repair Actions
**Scope:** Expose read-only scan actions plus safe and assisted repair workflows without destructive guessing.

**Files to Modify:**
- `src/scribe_mcp/doc_management/runtime.py` — action manifest and runtime routing for workflow actions.
- `src/scribe_mcp/doc_management/healing.py` — reuse or extend current repair helpers where safe.

**Files to Create:**
- `src/scribe_mcp/doc_management/intelligence_workflows.py` — workflow orchestration for scans, repair modes, and stale cleanup recommendations.
- `tests/test_document_intelligence_workflows.py` — action contract, repair mode, and cleanup safety coverage.

**Dependencies:**
- Requires Package 3.1 complete because workflow actions must reuse the shipped quality and ownership semantics.

**Specifications:**
1. Add `topology_scan`, `metadata_scan`, `metadata_repair`, and `stale_cleanup_scan`.
2. Support `report_only`, `repair_safe`, and `repair_assisted` exactly; only `repair_safe` may mutate docs automatically.
3. Emit rejection codes for ambiguous owners, conflicting IDs, unresolved targets, destructive cleanup, and missing external contract prerequisites.
4. Keep stale cleanup non-destructive by default and require explicit confirm semantics for destructive classes.
5. Return machine-usable proof fields for every evaluated repair item.

**Patterns to Follow:**
- Reuse the current warning and quality delta surfaces instead of inventing a second repair report format.
- Keep stale cleanup as recommendation-first, matching the project’s audit-trail doctrine.

**Verification:**
- `pytest -q tests/test_document_intelligence_workflows.py`
- `repair_safe` mutates only deterministic cases; ambiguous cases remain reported, not guessed.

**Out of Scope:**
- Final JSON artifact generation and generic downstream contract authoring.

---
## Phase 5 — Derived Indexes And Downstream Export Contract
<!-- ID: phase_5 -->
### Task Package: 5.1 — Deterministic Export Artifacts And Managed Contract Doc
**Scope:** Generate sanitized topology and downstream ingestion/export artifacts, expose inspection previews, and author the managed generic downstream contract document.

**Files to Modify:**
- `src/scribe_mcp/doc_management/special_indexes.py` — integrate the new derived index generation and sync rules.
- `src/scribe_mcp/doc_management/runtime.py` — expose `ingestion_manifest_inspect` and any explicit regenerate entrypoint used by the mission.
- `tests/test_manage_docs_quality_check.py` — keep quality/export gate regressions green where shared code paths overlap.

**Files to Create:**
- `src/scribe_mcp/doc_management/intelligence_exports.py` — deterministic builders for `doc_topology.json`, `work_topology.json`, and `downstream_ingestion_manifest.json`.
- `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/DOWNSTREAM_INGESTION_CONTRACT.md` — managed contract doc describing schemas, rejection codes, responsibility boundaries, sanitized path rules, and the operator runbook.
- `tests/test_document_topology_exports.py` — export determinism, sanitization, rejection-code parity, and inspect preview coverage.

**Dependencies:**
- Requires Packages 1.1 through 4.1 complete.

**Specifications:**
1. Build all three `.scribe/indexes/*.json` artifacts from managed docs, existing registration truth, normalized topology, and quality output.
2. Enforce repo-internal allowlisting, path hiding, and stable rejection codes for outside-repo, local-only, archived, blocked, scaffolded, and unsafe-link cases.
3. Keep the artifacts derived-only for v1; no new storage schema or remote backend contract is added.
4. Expose `ingestion_manifest_inspect` as a preview over the same builders used for final artifact generation.
5. Author `DOWNSTREAM_INGESTION_CONTRACT.md` as a quality-clean managed doc with schema tables, producer-consumer responsibility split, rejection reason catalog, sanitized path rules, and the generate -> inspect -> repair -> re-export runbook.
6. Preserve the public/private boundary explicitly: Scribe owns deterministic truth plus sanitized exports, while downstream consumers own retrieval, embeddings, Graph RAG traversal, ranking, and model-based classification. Knowledge MCP may appear only as an optional council-private example adapter outside Scribe public core.

**Patterns to Follow:**
- Match existing special index generation and sync patterns in `special_indexes.py`.
- Project only allowlisted export fields; do not serialize raw registry rows or arbitrary frontmatter maps.

**Verification:**
- `pytest -q tests/test_document_topology_exports.py tests/test_document_intelligence_workflows.py`
- Regenerating artifacts twice with unchanged inputs yields byte-identical JSON output.
- `DOWNSTREAM_INGESTION_CONTRACT.md` passes `manage_docs(action="quality_check", dry_run=True)` with zero readiness blockers.

**Out of Scope:**
- Embedding generation, retrieval ranking, Graph RAG traversal, and any downstream consumer implementation, including council-private Knowledge MCP adapters.

---
## Milestone Tracking
<!-- ID: milestone_tracking -->
| Milestone | Status | Evidence | Next Gate |
|-----------|--------|----------|-----------|
| Blueprint architecture package corrected on 2026-05-25 | Complete | `SPEC.md`, both synthesis docs, `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, and `CHECKLIST.md` all passed `quality_check` dry runs with quality_status=`pass`, total_warnings=`0`, readiness_blocker_count=`0` after the generic downstream contract rename and public/private boundary correction | Pre-implementation review rerun |
| Package 1.1 ready for Forge routing | Planned | Phase 1 package contract above | Requires pre-implementation review PASS |
| Package 3.1 ready for Forge routing | Planned | Phase 3 package contract above | Requires Packages 1.1 and 2.1 complete and package-specific Crucible PASS |
| Package 5.1 release gate | Planned | Phase 5 package contract above | Requires Packages 1.1-4.1 complete and package-specific Crucible PASS |

---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->
- The research corpus supports a sequential v1 because `manager.py` and `runtime.py` are shared choke points; forcing fake parallelism here would increase merge and gate risk.
- If implementation uncovers a direct need for storage schema changes, stop the package and return through review with evidence rather than silently expanding the mission.
- If a workflow action or export field cannot be kept additive to the current warning or registry contract, route the delta back through review before code lands.

---
