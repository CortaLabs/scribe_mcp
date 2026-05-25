---
id: synthesis-wave-1-document-topology-20260525
title: 'Wave 1 Synthesis: Scribe Document Topology Foundation'
doc_type: custom
doc_name: SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY
category: research
status: in_progress
version: '0.1'
last_updated: 2026-05-25 04:25:21 UTC
maintained_by: agent-20260525-041721-403c6ea5
created_by: agent-20260525-025041-98e5a737
owners:
- Seshat
related_docs: []
tags:
- wave-1
- synthesis
- document-topology
- quality-gate
- knowledge-ingestion
summary: Synthesis of the first GRAND_BRACKET research wave for Scribe document intelligence,
  unifying metadata/frontmatter, registration/storage, quality lifecycle, structural
  parsing, and downstream ingestion/export boundary findings into a reuse-first direction
  for Wave 2 and Blueprint.
intended_doc_type: synthesis
depends_on:
- RESEARCH_SCRIBE_METADATA_SURFACE
- RESEARCH_SCRIBE_DOC_REGISTRATION
- RESEARCH_SCRIBE_QUALITY_LIFECYCLE
- RESEARCH_SCRIBE_STRUCTURAL_TOPOLOGY
- RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY
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
  created_at: 2026-05-25 03:31:52 UTC
  created_via: create_doc
  last_edited_at: 2026-05-25 04:25:21 UTC
  last_edited_by: agent-20260525-041721-403c6ea5
  last_action: replace_text
---

# Wave 1 Synthesis: Scribe Document Topology Foundation

## Evidence Base

Wave 1 produced five quality-clean managed research artifacts:

- `RESEARCH_SCRIBE_METADATA_SURFACE.md` by Turing, `scribe-research-analyst`: metadata/frontmatter and reuse audit.
- `RESEARCH_SCRIBE_DOC_REGISTRATION.md` by Wegener and repaired by Einstein, `Sia`: document registration and storage topology audit.
- `RESEARCH_SCRIBE_QUALITY_LIFECYCLE.md` by Rawls, `scribe-research-analyst`: quality lifecycle and status-gate audit.
- `RESEARCH_SCRIBE_STRUCTURAL_TOPOLOGY.md` by Noether, `scribe-research-analyst`: structural parsing and deterministic topology linkage audit.
- `RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY.md` by Feynman, `scribe-doc-writer`: historical private-adapter boundary audit that informs the generic downstream ingestion/export contract.

Every artifact passed `manage_docs quality_check` with zero warnings and zero readiness blockers after the Sia registration artifact was repaired in place.

## Unified Findings

Scribe already has the bones needed for a document intelligence foundation. The correct architecture is extension and integration, not replacement.

- Metadata/frontmatter: `manage_docs` already owns workflow metadata, reserved attribution fields, edit traces, related docs, stable `id`, special-create/template paths, and tests. The gap is a canonical contract that makes these fields strict, complete, and externally ingestible.
- Registration/storage: Scribe already has document/project management, change history, storage backend contracts, and registration-adjacent behavior. The gap is a topology-aware single registry record that captures canonical ID, path, status, hash, mtime, quality state, and downstream ingestion/export eligibility without creating a second registry.
- Quality lifecycle: `quality_check` and `scaffold_quality_check` already share a runtime path, and warning objects already support blocker semantics. The gap is status-transition enforcement and topology/lifecycle warning codes integrated into the current gate.
- Structural parsing: Scribe already has deterministic helpers for frontmatter parsing, section discovery, checklist extraction, header normalization, TOC generation, and crosslink diagnostics. `markdown-it-py` is already present and suitable for deterministic tokenization. The gap is typed topology semantics, edge normalization, target resolution, and cycle detection.
- Downstream ingestion/export: Scribe must produce clean metadata, lifecycle status, quality status, topology index, downstream ingestion manifest, content hashes, and edge graph. Downstream consumers own embeddings, semantic retrieval, Graph RAG, ranking, and model-based classification. Knowledge MCP may remain only as an optional council-private example adapter outside public Scribe core.

## Integration Direction

The document hive mind should be a single Scribe-owned lifecycle:

1. `set_project` binds agent and workstream context and should become the natural place to formalize clock-in/project-session state.
2. `manage_docs` remains the document lifecycle and metadata mutation surface.
3. Frontmatter carries the canonical metadata contract and typed topology edges.
4. Structural parsing extracts headings, anchors, links, checklists, summaries, and code/table structure deterministically.
5. Registration records canonical identity and file/storage truth.
6. `quality_check` validates scaffold quality, metadata completeness, lifecycle transitions, registry consistency, topology links, and ingestion eligibility.
7. Failed quality at handoff/clock-out is recorded in Scribe and blocks clean completion.
8. Topology indexes and downstream ingestion manifests are generated from the same document lifecycle, not from a separate crawler.

## Required Wave 2 Research And Design Lanes

Wave 2 should focus on risks and enforcement details that Wave 1 deliberately did not over-design:

1. Agent lifecycle and hard handoff gate lane: design automatic clock-in via `set_project`, pre-handoff/clock-out quality enforcement, failed handoff logging, and operator-friendly repair loops.
2. Security/trust boundary lane: review safe downstream ingestion/export manifests, path exposure, remote backend/proxy implications, external corpus export boundaries, and generated index safety.
3. Template/doc-type governance lane: investigate canonical doc_type expansion, generated template/source authority implications, and how to introduce synthesis/phase_plan/checklist/security_review/bug_rca/work_item without breaking current manage_docs behavior.
4. Storage/index implementation lane: refine topology index/work index/downstream ingestion manifest generation placement, deterministic content hashing, storage persistence, and cross-backend migration strategy.
5. Operator and agent workflow lane: design frictionless commands/actions for topology_scan, metadata_scan, metadata_repair, quality-driven handoff, and repair batches.

## Non-Negotiable Design Constraints For Blueprint

- No competing metadata system.
- No competing document registry.
- No `quality_check_v2`.
- No transformer, embedding, or LLM classification inside Scribe.
- No clean handoff for managed docs with scaffold residue.
- No deferred handling of SPEC-named outcomes unless research proves an implementation dependency that must be sequenced inside the same mission.
- Human-facing metadata must use display names first and opaque runtime IDs only as secondary provenance.
- Indexes and manifests must be deterministic and reproducible.

## Open Questions For Wave 2

- Which existing Scribe/Council session or project-binding surfaces can safely support automatic clock-in without surprising standalone MCP clients?
- Where should handoff blocking live: inside manage_docs quality transitions, a Council/Scribe session close hook, a new Scribe action, or a combination?
- How should failed handoff entries identify document ownership when multiple agents edit the same managed doc across a wave?
- Which canonical doc_type additions require template updates, tests, or backward-compatible aliases?
- Does topology index generation require storage schema changes, or can v1 derive from frontmatter + registered paths + file hashes?
- How should downstream ingestion/export manifests avoid leaking local-only or sensitive paths while still being useful to downstream consumers?

## Synthesis Decision

Proceed to Wave 2 GRAND_BRACKET research/design. The mission remains implementation-blocked until Wave 2 synthesis, Blueprint architecture documents, and pre-implementation review pass. Wave 2 must explicitly include the new hard handoff quality doctrine.
