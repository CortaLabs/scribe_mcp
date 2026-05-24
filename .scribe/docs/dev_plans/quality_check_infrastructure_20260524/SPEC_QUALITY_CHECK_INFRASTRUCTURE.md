---
id: quality_check_infrastructure_20260524-spec-quality-check-infrastructure
title: 'SPEC: Quality Check Infrastructure'
doc_type: custom
doc_name: SPEC_QUALITY_CHECK_INFRASTRUCTURE
category: planning
status: draft
version: '0.1'
last_updated: 2026-05-24 03:04:28 UTC
maintained_by: agent-20260524-025636-a27de3e3
created_by: agent-20260524-025636-a27de3e3
owners: []
related_docs: []
tags:
- quality_check
- manage_docs
- spec
- research-bracket
summary: Problem definition and research bracket for turning manage_docs quality_check
  into a markdown-aware infrastructure-quality gate.
edit_trace:
  tool: manage_docs
  created_at: 2026-05-24 03:04:28 UTC
  created_via: create_doc
  last_edited_at: 2026-05-24 03:04:28 UTC
  last_edited_by: agent-20260524-025636-a27de3e3
  last_action: create_doc
---
# SPEC: Quality Check Infrastructure

## Problem Statement

`manage_docs quality_check` is already part of Scribe's managed-document readiness gate, but it is not yet strong enough to act as a durable infrastructure tool. The immediate symptom is false failure around fenced code blocks and nested code-block examples in research documents. The broader concern is that the current checker may be a brittle collection of rules instead of a composable, markdown-aware, product-grade validation layer.

## Goals

- Make `quality_check` markdown-aware enough to distinguish prose, fenced code, nested/quoted examples, frontmatter, anchors, tables, and generated scaffold surfaces.
- Preserve useful blockers for real scaffold residue, weak managed-doc readiness, changelog/version drift, malformed metadata, and release-closeout hazards.
- Improve output usefulness: clear codes, severity, blocking status, line locations, excerpts, suggested repairs, and optional categories suitable for agents and humans.
- Keep the system lightweight: deterministic local checks first, no heavy runtime dependency, no LLM requirement, no slow global analysis by default.
- Design an extension path so Scribe can add document-type rules without turning `manager.py` or quality collectors into a god module.
- Maintain backwards compatibility for the existing `manage_docs(action="quality_check")` contract unless research proves a narrow additive change is necessary.

## Non-Goals

- Do not replace Scribe managed docs with a separate documentation platform.
- Do not add heavyweight external services or mandatory LLM review.
- Do not make every style preference blocking.
- Do not hand-edit generated outputs or bypass managed-doc tooling.
- Do not implement before research and architecture have produced bounded task packages.

## Constraints

- Project: `quality_check_infrastructure_20260524` for all Scribe/Council calls.
- Repo root: `/home/austin/projects/MCP_SPINE/scribe_mcp`.
- Existing `manage_docs` behavior and tool response shape must be mapped before redesign.
- The nested fenced-code false positive must be covered by regression tests in the implementation phase.
- Any release bump, commit, or push is blocked until post-implementation validation and review pass.
- Research wave size is capped at five concurrent specialists.

## Research Questions

1. Where does current `quality_check` logic live, how does it detect scaffold residue and changelog warnings, and where are parsing assumptions brittle?
2. How should markdown-aware parsing treat fenced code blocks, nested fences, escaped fences, blockquotes, raw examples, and generated anchors?
3. What patterns from markdown linting, Vale/prose linting, docs-as-code gates, schema/rule engines, suppressions, and severity models fit Scribe without adding heavy dependencies?
4. How should `quality_check` integrate with Scribe's document lifecycle: research docs, architecture docs, phase plans, checklists, bug/security reports, changelog coverage, reminders, and release gates?
5. What minimal rule-registry or collector architecture would make quality checks extensible without creating parallel systems?
6. Which warnings should be blocking, advisory, suppressible, document-type-specific, or release-gate-only?

## Research Bracket: Wave 1

- Source Map: `scribe-research-analyst` maps current source, tests, response shape, failure modes, and exact seams.
- Managed Authoring/Governance: `maat` evaluates how quality_check should fit managed templates, generated surfaces, roster/rule/skill governance, and Council/Scribe authoring workflows.
- Operations/Release Gate: `ptah` evaluates how quality_check can serve CI, release, Docker/build, live runtime, and operator closeout gates without becoming expensive.
- External Patterns: external research lane surveys current documentation-quality tooling and extracts lightweight patterns applicable to Scribe.

## Acceptance Criteria For Research Closeout

- Each lane produces a managed research artifact or Scribe-logged artifact path with concrete evidence and confidence.
- Synthesis identifies reuse-first changes and rejects unnecessary heavyweight paths.
- Architecture does not begin until wave outputs are read, checked for scaffold residue, and summarized in Scribe.
