---
id: scribe-document-topology-foundation-20260524-research-doc-type-template-governance
title: "RESEARCH: Scribe Doc Type and Template Governance"
doc_type: custom
doc_name: RESEARCH_SCRIBE_DOC_TYPE_TEMPLATE_GOVERNANCE
category: research|governance
status: complete
version: '0.1'
last_updated: 2026-05-25 04:00:00 UTC
maintained_by: Euler
created_by: Euler
owners:
- Euler
related_docs:
- SPEC
- SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY
- RESEARCH_SCRIBE_METADATA_SURFACE
tags:
- scribe
- doc_type
- templates
- governance
- source-authority
summary: Evidence-backed governance proposal for canonical document type adoption via create-time aliasing and handler/template resolution without breaking existing managed docs or generated/source-authority boundaries.
intended_doc_type: synthesis
---

# RESEARCH_SCRIBE_DOC_TYPE_TEMPLATE_GOVERNANCE

## Current Evidence
- `create` routing currently only has built-in handler doc types: `research`, `bug`, `security`, `review`, `agent_card`, `spec` plus generic `custom` path in [`src/scribe_mcp/doc_management/actions/create.py:10`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/doc_management/actions/create.py:10).
- Unknown doc_type errors still return the current valid list (matching the observed rejection of `synthesis`) in [`src/scribe_mcp/doc_management/actions/create.py:128`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/doc_management/actions/create.py:128).
- Alias/template config support already exists via `resolve_create_doc_type_config` and metadata transparency fields (`requested_doc_type`, `resolved_doc_type`, `resolved_handler`, `config_source`) in [`src/scribe_mcp/doc_management/actions/create.py:32`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/doc_management/actions/create.py:32).
- Repo config reserves built-ins as `custom/spec/research/bug/security/review/agent_card` in [`src/scribe_mcp/config/repo_config.py:22`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/config/repo_config.py:22).
- Template registry already includes non-create canonical families such as `architecture`, `phase_plan`, `checklist`, `progress_log`, and report templates like `research_report`, `bug_report`, `review_report` in [`src/scribe_mcp/templates/__init__.py:14`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/templates/__init__.py:14).
- Tests already validate alias/template mapping behavior for create-time doc types in [`tests/test_manage_docs_create_doc.py:593`](/home/austin/projects/MCP_SPINE/scribe_mcp/tests/test_manage_docs_create_doc.py:593).

## Source-of-Truth Map
- Canonical create-time routing authority: [`src/scribe_mcp/doc_management/actions/create.py`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/doc_management/actions/create.py).
- Create-time doc type config authority: [`src/scribe_mcp/config/repo_config.py`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/config/repo_config.py).
- Template name registry authority: [`src/scribe_mcp/templates/__init__.py`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/templates/__init__.py).
- Managed-doc metadata and reserved-field handling authority: [`src/scribe_mcp/doc_management/manager.py`](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/doc_management/manager.py).
- Generated instruction surfaces (`AGENTS.md`, `.claude/**`, `.codex/**`) remain non-authoritative outputs from council templates/roster/compiler per current governance.
- Managed docs under `.scribe/docs/dev_plans/<project>/...` are authoritative project artifacts, but their behavior is still defined by source code + templates above.

## Backward-Compatible Canonical Type Strategy
1. Canonical taxonomy target (mission-aligned): `architecture`, `spec`, `phase_plan`, `checklist`, `research`, `synthesis`, `review`, `security_review`, `bug_rca`, `progress_log`, `work_item`, `other`.
2. Phase 1 (no breakage): keep runtime built-ins unchanged, add repo-config aliases mapping new canonical values to existing handlers.
3. Alias mapping recommendation:
- `synthesis -> custom` (optionally template-backed)
- `architecture -> custom` (template-backed)
- `phase_plan -> custom` (template-backed)
- `checklist -> custom` (template-backed)
- `progress_log -> custom` (template-backed)
- `work_item -> custom` (template-backed)
- `other -> custom`
- `security_review -> security` (special handler)
- `bug_rca -> bug` (special handler)
- `review -> review` (unchanged)
- `research -> research` (unchanged)
- `spec -> spec` (unchanged)
4. Add `intended_doc_type` frontmatter as canonical semantic declaration when resolved handler differs; keep `doc_type` as actual operational routing value for compatibility.
5. Resolution precedence:
- `requested_doc_type` (caller)
- alias/template resolution from repo config
- mapped special handler or generic `create_doc`
- persisted transparency fields (`requested_doc_type`, `resolved_doc_type`, `resolved_handler`, `config_source`)

## Template and Handler Additions
- Prefer template additions before new handlers for: `synthesis`, `architecture`, `phase_plan`, `checklist`, `progress_log`, `work_item`.
- Reuse existing special handlers for `bug_rca` and `security_review` through aliasing to `bug`/`security` to avoid forking report flows.
- Only add a new special handler if a canonical type requires different indexing/side-effects than `create_doc` + frontmatter + template can provide.

## Test Plan (Compatibility-Focused)
- Extend alias tests with canonical mappings listed above (positive path).
- Add assertions that `requested_doc_type` remains canonical while `resolved_doc_type` may be legacy/built-in.
- Add regression test for `intended_doc_type` persistence through create/update/frontmatter_update.
- Add template-resolution tests for canonical types mapped to `create_templates`.
- Keep legacy type tests passing unchanged (`research`, `review`, `bug`, `security`, `spec`, `agent_card`, `custom`).

## Impact on Existing Docs
- Existing `SPEC.md`, `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`, and current `RESEARCH_*` docs remain valid and require no migration for behavior correctness.
- Optional migration path: backfill `intended_doc_type` on key docs where current `doc_type` is generic/custom but semantic type is known (for ingestion/readability only).
- `SYNTHESIS_WAVE_1_DOCUMENT_TOPOLOGY.md` pattern (`doc_type: custom` + `intended_doc_type: synthesis`) is already a working bridge pattern and should be formalized.

## Generated/Source-Authority Implications
- No managed change should hand-edit generated `.claude/.codex` surfaces.
- Governance updates belong in source code, template sources, and config schema/tests; generated outputs update only via standard generation commands.
- Canonical doc type adoption is a manage_docs/runtime concern, not a council generated-surface override.

## Recommendations for Blueprint and Sequencing
1. Blueprint package A: canonical doc type contract and alias matrix (spec + config schema + docs).
2. Blueprint package B: template coverage for canonical generic types (`synthesis`, `architecture`, `phase_plan`, `checklist`, `progress_log`, `work_item`).
3. Blueprint package C: runtime transparency and frontmatter bridge (`intended_doc_type`) with backward-compat guarantees.
4. Blueprint package D: test expansion and migration/backfill helper (non-destructive, optional).
5. Gate: no changes to generated outputs directly; prove via tests and manage_docs quality flow only.

## Quality Status
- Research artifact prepared with source evidence and compatibility-first rollout guidance.
- `manage_docs quality_check` could not be run directly from this tool surface; follow-up run is required through the Scribe MCP `manage_docs` tool for formal gate proof.
