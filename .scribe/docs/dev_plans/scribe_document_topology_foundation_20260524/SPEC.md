---
id: spec-scribe-document-topology-foundation-20260524
title: Scribe Document Topology Foundation SPEC
doc_type: spec
doc_name: SPEC
category: planning
status: in_progress
version: '0.1'
last_updated: 2026-05-25 04:23:47 UTC
maintained_by: agent-20260525-041721-403c6ea5
created_by: agent-20260525-025041-98e5a737
owners:
- Seshat
related_docs: []
tags:
- document-topology
- metadata-lifecycle
- quality-check
- knowledge-ingestion
- integrate-system
- build-feature
summary: Problem-definition SPEC for building deterministic Scribe document topology,
  lifecycle metadata, quality-gated corpus readiness, back-scan repair, and generic
  downstream ingestion/export contracts without introducing competing registries or
  semantic inference inside Scribe.
depends_on: []
supports: []
validates: []
supersedes: []
blocked_by: []
touches:
- src/scribe_mcp/doc_management
- src/scribe_mcp/tools
- src/scribe_mcp/storage
- .scribe/docs/dev_plans
edit_trace:
  tool: manage_docs
  created_at: 2026-05-25 02:58:10 UTC
  created_via: create_doc
  last_edited_at: 2026-05-25 04:23:47 UTC
  last_edited_by: agent-20260525-041721-403c6ea5
  last_action: frontmatter_update
---

# Scribe Document Topology Foundation SPEC

## Problem Statement

Scribe already has powerful managed-document, logging, registry, and quality-check bones, but the document corpus is not yet deterministic enough to serve as the authoritative truth layer for downstream ingestion/export consumers such as RAG or graph-RAG systems. The system needs a single integrated document topology foundation that can identify what exists, where it lives, who maintains it, what state it is in, what it depends on, what it proves, whether it passed quality gates, and whether it is eligible for sanitized downstream ingestion/export.

This mission turns Scribe from a document store into a deterministic document lifecycle and topology authority. It must improve metadata, lifecycle status, typed links, structural parsing, quality integration, old-doc scanning, repair plans, registration, indexes, and the Scribe downstream ingestion/export contract without creating duplicate systems.

## Goals

- Extend existing Scribe managed-document surfaces rather than creating parallel registries, validators, or metadata stores.
- Define a canonical metadata contract with stable document IDs, human-readable agent display names, lifecycle status, summary requirements, quality metadata, and typed topology edges.
- Integrate topology and lifecycle checks into existing `quality_check` behavior.
- Add deterministic markdown/frontmatter structural parsing sufficient for headings, anchors, links, checklist items, code fences, tables, and summary blocks.
- Add back-scan and safe backfill workflows for old managed documents.
- Strengthen document registration so canonical IDs, path, status, content hash, quality state, and downstream ingestion/export eligibility are available to downstream systems.
- Generate machine-readable topology and sanitized downstream ingestion/export indexes for downstream consumers.
- Write `DOWNSTREAM_INGESTION_CONTRACT.md` as the boundary document for later downstream ingestion/export integrations.

## Non-Goals

- No transformer models inside Scribe.
- No embedding-based linkage or semantic guessing inside Scribe.
- No Graph RAG implementation inside Scribe.
- No `quality_check_v2` or competing quality path.
- No second document registry or parallel metadata truth system.
- No requirement that agents manually maintain fields Scribe can infer deterministically.
- No blanket blocking of authoring because old documents are imperfect; old docs should be staged through scan, report, and repair flows.

## Constraints

- `manage_docs`, the frontmatter pipeline, document registration, project registry, edit traces, and `quality_check` are the source surfaces to inspect and extend.
- Human-facing metadata must prefer display names such as `Forge`, `Blueprint`, `Witness`, `Crucible`, `Arbiter`, `Loom`, `Quill`, `Atlas`, or `Seshat`. Opaque runtime IDs may be retained only as secondary provenance fields.
- Status values are limited to `scaffolded`, `in_progress`, `ready`, `complete`, `stale`, `superseded`, `blocked`, and `archived` unless Blueprint proves a compatibility need.
- Status transitions to `ready` and `complete` must be quality-gated.
- Downstream consumers may consume Scribe outputs, but they do not define Scribe truth. Knowledge MCP may appear only as an optional council-private example consumer or adapter outside Scribe's public core.
- All fixes must preserve response compatibility unless explicitly planned and reviewed.

## Research Questions

- How do `manage_docs`, frontmatter defaults, edit traces, and document templates currently assign metadata and attribution?
- Where are quality checks implemented, what warning/blocker shape do they return, and how can topology checks be integrated without a parallel validator?
- How are documents currently registered, rehomed, discovered, indexed, hashed, and tracked across storage backends?
- What deterministic structural parsing already exists, and what lightweight parser or fallback should be used for markdown structure extraction?
- What generic fields and schemas should Scribe expose for sanitized downstream ingestion/export now, and what should remain deferred to downstream retrieval systems?
- What old-doc repair operations are safe to automate, and which must remain report-only or assisted?

## Bracket Classification

Initial tier: `STANDARD_BRACKET`, with escalation triggers for `GRAND_BRACKET` if research shows cross-repo migration risk, storage schema migration risk, generated-template source authority changes, or launch/release-critical behavior. The first wave is capped at five researchers with disjoint owned artifacts. Synthesis is required before Blueprint planning and before any implementation package.

## Research Bracket Outline

Wave 1 research tracks:

1. Existing capability and reuse audit: inspect current `manage_docs`, templates, frontmatter metadata, and document lifecycle affordances. Artifact: `RESEARCH_SCRIBE_METADATA_SURFACE.md`.
2. Document registration and storage topology audit: inspect registration, rehome/register-existing behavior, project registry, content hashes, doc update history, and storage implications. Artifact: `RESEARCH_SCRIBE_DOC_REGISTRATION.md`.
3. Quality lifecycle audit: inspect current `quality_check`, scaffold warnings, managed-doc readiness behavior, and compatibility constraints for adding topology warnings. Artifact: `RESEARCH_SCRIBE_QUALITY_LIFECYCLE.md`.
4. Structural parsing and topology linkage audit: inspect existing parsing/link validation support and propose deterministic parser/edge validation reuse. Artifact: `RESEARCH_SCRIBE_STRUCTURAL_TOPOLOGY.md`.
5. Downstream ingestion/export contract audit: inspect existing downstream and historical Knowledge MCP/dataset-related contracts, then define the generic sanitized outputs Scribe should produce without implementing retrieval. Artifact: `RESEARCH_KNOWLEDGE_INGESTION_BOUNDARY.md`.

Synthesis checkpoint:

- Seshat verifies that every artifact exists in the active Scribe project, has concrete file-level evidence, identifies reuse-vs-build decisions, and avoids duplicate systems.
- If the wave exposes missing core context, a second bounded research wave may be declared before Blueprint.
- If the wave is sufficient, Blueprint receives the SPEC plus all research artifacts and must produce `ARCHITECTURE_GUIDE`, `PHASE_PLAN`, `CHECKLIST`, and bounded implementation packages.

## Acceptance Criteria

- New managed documents use deterministic human-readable metadata and stable document IDs.
- Scribe can validate lifecycle status and typed deterministic edges.
- Existing `quality_check` reports topology and lifecycle findings with structured warning/blocker codes.
- Back-scan modes can report missing metadata, duplicate IDs, broken links, opaque agent ID leakage, missing summaries, orphan docs, and registry gaps.
- Safe repairs are deterministic and ambiguous repairs are reported rather than guessed.
- Document registration exposes canonical ID, path, doc type/name, project/workstream, status, content hash, mtime, quality status, and downstream ingestion/export eligibility.
- `.scribe/indexes/doc_topology.json`, `.scribe/indexes/work_topology.json`, and `.scribe/indexes/downstream_ingestion_manifest.json` or Blueprint-approved equivalents are generated deterministically.
- `DOWNSTREAM_INGESTION_CONTRACT.md` defines required fields, eligible statuses, quality requirements, schemas, rejection reasons, sanitized path rules, and downstream responsibilities.
- Tests cover metadata normalization, lifecycle validation, edge parsing, index generation, quality integration, old-doc repair, response compatibility, and no transformer/model dependency.
## Operator Authorization Update

On 2026-05-25, the operator expanded the authorization boundary for this mission:

- The workflow may proceed autonomously through research, synthesis, Blueprint planning, and pre-implementation review.
- The bracket may use more than two waves when that improves evidence quality.
- `GRAND_BRACKET` is approved when justified by the mission's document-intelligence, cross-surface integration, and downstream ingestion/export importance.
- Items explicitly named in this SPEC are in scope for planning and should not be deferred merely because they are ambitious.
- The final architecture must build one unified document-intelligence foundation: frictionless for operators and agents, deterministic inside Scribe, and ready for generic downstream ingestion/export.

Updated bracket tier: `GRAND_BRACKET`, with required synthesis gates between waves and before Blueprint.
## Hard Handoff Quality Doctrine

The operator added this requirement on 2026-05-25 after a Wave 1 research artifact was returned with scaffold placeholders still present:

- Scaffold residue, placeholder brackets, generated shell content, and literal failed-write residue are hard blockers for any agent claiming a managed document is complete.
- A delegated agent must not be able to cleanly clock out, hand off, or mark completion when its owned managed documents fail `quality_check` for scaffold or placeholder blockers.
- Failed clock-out or handoff attempts should be recorded in Scribe with enough detail for the coordinator and later agents to recover: agent, project, document path, warning codes, blocker count, and suggested repair path.
- Scribe should investigate automatic clock-in/project binding behavior around `set_project`, so agents get a consistent work session/project context without extra manual ceremony.
- Scribe should investigate continuous or pre-handoff quality checks during document authoring, so agents discover scaffold residue before final handoff.
- The enforcement must extend the existing Scribe quality_check/readiness lifecycle. It must not become `quality_check_v2` or a parallel validator.

Planning implication: Blueprint must include a bounded package for managed-document handoff enforcement and agent clock-out/quality-gate behavior. This package is not optional for the mission.
