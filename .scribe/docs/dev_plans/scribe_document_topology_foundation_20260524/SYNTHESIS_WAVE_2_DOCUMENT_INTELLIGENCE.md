---
id: synthesis-wave-2-document-intelligence-20260525
title: 'Wave 2 Synthesis: Scribe Document Intelligence Enforcement'
doc_type: custom
doc_name: SYNTHESIS_WAVE_2_DOCUMENT_INTELLIGENCE
category: research
status: in_progress
version: '0.1'
last_updated: 2026-05-25 04:26:45 UTC
maintained_by: agent-20260525-041721-403c6ea5
created_by: agent-20260525-025041-98e5a737
owners:
- Seshat
related_docs: []
tags:
- wave-2
- synthesis
- handoff-gate
- topology-index
- security-boundary
- workflow
summary: Synthesis of the second GRAND_BRACKET wave covering hard handoff gates, topology
  security boundaries, doc type/template governance, derived topology indexes, and
  frictionless operator/agent workflows for Scribe document intelligence.
intended_doc_type: synthesis
depends_on:
- RESEARCH_SCRIBE_HANDOFF_GATE_LIFECYCLE
- RESEARCH_SCRIBE_TOPOLOGY_SECURITY_BOUNDARY
- RESEARCH_SCRIBE_DOC_TYPE_TEMPLATE_GOVERNANCE
- RESEARCH_SCRIBE_TOPOLOGY_INDEX_IMPLEMENTATION
- RESEARCH_SCRIBE_DOCUMENT_INTELLIGENCE_WORKFLOW
- SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY
supports:
- SPEC
validates: []
supersedes: []
blocked_by: []
touches:
- src/scribe_mcp/doc_management
- src/scribe_mcp/tools/manage_docs.py
- src/scribe_mcp/storage
- src/scribe_mcp/readiness.py
edit_trace:
  tool: manage_docs
  created_at: 2026-05-25 03:47:09 UTC
  created_via: create_doc
  last_edited_at: 2026-05-25 04:26:45 UTC
  last_edited_by: agent-20260525-041721-403c6ea5
  last_action: replace_range
---

# Wave 2 Synthesis: Scribe Document Intelligence Enforcement

## Evidence Base

Wave 2 produced five quality-clean managed research artifacts:

- `RESEARCH_SCRIBE_HANDOFF_GATE_LIFECYCLE.md` by Dewey, `scribe-architect`: hard handoff gate, set_project clock-in, ownership, and failed handoff logging.
- `RESEARCH_SCRIBE_TOPOLOGY_SECURITY_BOUNDARY.md` by Sagan, `scribe-security-agent`: downstream ingestion/index trust boundaries and export controls.
- `RESEARCH_SCRIBE_DOC_TYPE_TEMPLATE_GOVERNANCE.md` by Euler, `Ma'at`: canonical doc_type/template governance and alias strategy. Coordinator verified quality because the agent lacked direct Scribe tools.
- `RESEARCH_SCRIBE_TOPOLOGY_INDEX_IMPLEMENTATION.md` by Sartre, `Sia`: derived index and downstream ingestion manifest implementation strategy.
- `RESEARCH_SCRIBE_DOCUMENT_INTELLIGENCE_WORKFLOW.md` by Hilbert, `scribe-doc-writer`: operator/agent workflow actions and repair UX.

Every artifact has a formal `manage_docs quality_check` pass with zero warnings and zero readiness blockers. All completed agents were closed after logging.

## Synthesis Decisions

### 1. Hard Handoff Gate Is Required For V1

Scribe should make scaffold-placeholder handoff failure mechanical, not cultural.

V1 direction:

- Treat `set_project` as Scribe clock-in/project binding.
- Keep `quality_check` as the single validator.
- Add a quality-handoff gate around managed-doc completion/status transitions and final handoff claims.
- Add equivalent preflight before Scribe-owned session teardown where Scribe owns the session lifecycle.
- Log failed handoff attempts to Scribe with agent, project, owned docs, warning codes, blocker count, and suggested repair path.
- Extend failed-write residue detection beyond the existing changelog-specific escaped-newline rule.

### 2. Downstream Exports Must Be Curated

Scribe topology and downstream ingestion/export outputs must not mirror raw registry state.

V1 direction:

- Reject outside-repo discovered docs from downstream ingestion/export artifacts by default.
- Reject archived, stale, superseded, blocked, scaffolded, and in-progress docs by default.
- Reject archived/preflight/backup material by default.
- Treat user-authored `related_docs` and markdown links as untrusted until repo-internal allowlisting and deterministic resolution pass.
- Include rejection reasons in the downstream ingestion manifest.
- Preserve enough source reference for traceability without leaking unsafe absolute/local-only paths in external-facing outputs.
- Scribe owns deterministic truth plus sanitized exports; downstream consumers own embeddings, retrieval, Graph RAG traversal, ranking, and model-based classification. Knowledge MCP may remain only as an optional council-private example adapter outside Scribe public core.
### 3. Canonical Doc Types Need Backward-Compatible Aliasing

Current `manage_docs` create support is narrower than the target contract. Blueprint must plan doc_type expansion without breaking existing handlers.

V1 direction:

- Introduce canonical doc_type aliases and handler resolution rather than a hard break.
- Preserve current `custom/spec/agent_card/bug/research/review/security` compatibility.
- Add or alias target types including architecture, phase_plan, checklist, synthesis, security_review, bug_rca, progress_log, work_item, and other.
- Use `intended_doc_type` as a bridge only where necessary during migration; it is not the final contract.
- Keep template/source-authority boundaries intact and avoid generated-output hand edits.

### 4. V1 Indexes Should Be Derived Artifacts

No storage schema migration is required for the first topology foundation unless Blueprint uncovers a direct implementation blocker.

V1 direction:

- Generate `.scribe/indexes/doc_topology.json` from managed docs, frontmatter, registration/path truth, quality state, and file hashes.
- Generate `.scribe/indexes/work_topology.json` from workstream/project docs, status, checklists, and progress/doc relationships where deterministic.
- Generate `.scribe/indexes/downstream_ingestion_manifest.json` from eligible docs after quality, status, security, and topology checks.
- Make generation deterministic across repeated runs.
- Treat a storage-backed cache as future optimization only after performance evidence.

### 5. Operator And Agent Workflow Must Be Frictionless

Powerful document intelligence should feel like Scribe doing the boring work, not agents filling out paperwork.

V1 action surface should include or equivalent:

- `topology_scan`
- `metadata_scan`
- `metadata_repair`
- `quality_handoff_check`
- `ingestion_manifest_inspect`
- `stale_cleanup_scan`

Repair modes:

- `report_only`: findings only.
- `repair_safe`: deterministic safe fixes only.
- `repair_assisted`: repair plan requiring agent/operator confirmation for ambiguous cases.

Cleanup of stale/empty docs/projects must be non-destructive by default. Merge-to-sentinel-log or archival recommendations require report/confirm lifecycle and proof fields.

## Blueprint Requirements

Blueprint must now produce an implementation plan that includes all SPEC-named outcomes plus these Wave 2 requirements:

- Canonical metadata contract and doc_type alias strategy.
- Human display-name attribution with opaque IDs only as secondary provenance.
- Lifecycle statuses and quality-gated transitions.
- Typed topology edges with deterministic parsing, normalization, target resolution, and cycle detection.
- Integration of topology/lifecycle findings into existing `quality_check`.
- Hard quality handoff gate that blocks scaffold-placeholder completion claims and logs failed attempts.
- Back-scan and safe/assisted repair actions.
- Derived topology/work/downstream ingestion indexes with security-filtered eligibility and rejection reasons.
- `DOWNSTREAM_INGESTION_CONTRACT.md` as the managed generic downstream contract document.
- Tests for metadata, lifecycle, topology, indexes, quality integration, repair modes, security filtering, deterministic repeated generation, and handoff blockers.

## No Additional Research Wave Needed Before Blueprint

Wave 1 and Wave 2 together resolve the architecture-critical uncertainties. The remaining work is synthesis into executable architecture and task packages, not more discovery. Blueprint may request targeted follow-up only if a specific implementation seam is ambiguous after reading the research artifacts.

## Next Gate

Proceed to Blueprint architecture package:

- `ARCHITECTURE_GUIDE.md`
- `PHASE_PLAN.md`
- `CHECKLIST.md`
- bounded task packages

After Blueprint, run pre-implementation review before any Forge implementation.
