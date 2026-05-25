---
id: scribe-document-topology-foundation-20260524-research-scribe-metadata-surface
title: "\U0001F52C Scribe Managed-Document Metadata Surface \u2014 scribe_document_topology_foundation_20260524"
doc_type: research_report
doc_name: RESEARCH_SCRIBE_METADATA_SURFACE
category: research|metadata_surface
status: complete
version: '0.1'
last_updated: 2026-05-25 03:23:20 UTC
maintained_by: agent-20260525-030724-0663482e
created_by: agent-20260525-030724-0663482e
owners:
- ResearchAgent-MetadataSurface
related_docs: []
tags:
- scribe
- metadata
- frontmatter
- managed-docs
- research
summary: Audit of managed-doc metadata/frontmatter behavior, reserved fields, template
  reuse, and Blueprint extension points.
edit_trace:
  tool: manage_docs
  created_at: 2026-05-25 03:21:11 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-05-25 03:23:20 UTC
  last_edited_by: agent-20260525-030724-0663482e
  last_action: frontmatter_update
---

# 🔬 Scribe Managed-Document Metadata Surface — scribe_document_topology_foundation_20260524
**Author:** Scribe
**Version:** 0.1
**Status:** complete
**Last Updated:** 2026-05-25 03:18:47 UTC

> Audit of managed-doc metadata/frontmatter behavior, reserved fields, template reuse, and Blueprint extension points.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** verify the current managed-document metadata/frontmatter surface and identify the safest extension path for Blueprint.

**Key Takeaways:**
- The existing workflow already covers `summary`, `tags`, `owners`, `category`, `status`, `version`, and `related_docs` in the generic frontmatter pipeline.
- `created_by`, `maintained_by`, and `edit_trace` are reserved and tool-authored.
- `related_docs` is already derived from body links, so there is an existing graph surface to extend.
- `id` already acts as the stable identifier; there is no separate `stable_id` contract in the inspected code.
- Blueprint should extend the current surface rather than create a parallel metadata system.
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-MetadataSurface

**Investigation Window:** 2026-05-24 to 2026-05-25 UTC

**Focus Areas:**
- `manage_docs` create, edit, and `frontmatter_update` behavior.
- Current frontmatter defaults, reserved fields, and lifecycle attribution.
- Existing document templates and the metadata they consume.
- Stable IDs, lifecycle status, related-doc extraction, and edge-like fields.
- Tests that cover frontmatter behavior and managed-doc metadata.

**Dependencies & Constraints:**
- No source code edits were made in this lane.
- Recommendations must reuse the current Scribe surfaces, not add a competing metadata system.
- Special-create and generic frontmatter flows are separate and both must be respected.
- If a capability is not already implemented, Blueprint should place it in the existing extension surface rather than deferring it into a parallel store.
## Findings
<!-- ID: findings -->
### Finding 1
- **Summary:** `manage_docs` is a router; the actual metadata contract lives in shared runtime and manager helpers.
- **Evidence:** `src/scribe_mcp/tools/manage_docs.py:73-172`, `src/scribe_mcp/doc_management/runtime.py:101-108`, `src/scribe_mcp/doc_management/runtime.py:1468-1530`.
- **Confidence:** High

### Finding 2
- **Summary:** The generic frontmatter surface already supports the core workflow metadata keys Blueprint is likely to need.
- **Evidence:** `src/scribe_mcp/tools/manage_docs.py:96-116`, `src/scribe_mcp/doc_management/manager.py:3095-3119`, `src/scribe_mcp/doc_management/manager.py:3238-3255`.
- **Confidence:** High

### Finding 3
- **Summary:** `created_by`, `maintained_by`, and `edit_trace` are reserved, tool-authored fields, not caller-controlled metadata.
- **Evidence:** `src/scribe_mcp/tools/manage_docs.py:100-106`, `src/scribe_mcp/doc_management/manager.py:3261-3387`, `tests/test_frontmatter.py:362-418`.
- **Confidence:** High

### Finding 4
- **Summary:** `related_docs` already behaves like an implicit doc graph derived from markdown links, which is the closest existing surface to edge-like metadata.
- **Evidence:** `src/scribe_mcp/doc_management/manager.py:3019-3058`, `src/scribe_mcp/doc_management/manager.py:3197-3203`, `tests/test_frontmatter.py:293-316`.
- **Confidence:** High

### Finding 5
- **Summary:** A stable identifier already exists as `id`, derived from project slug plus doc name, and there is no separate `stable_id` contract in the inspected code paths.
- **Evidence:** `src/scribe_mcp/doc_management/manager.py:3061-3092`, `src/scribe_mcp/doc_management/utils.py:124-127`, `tests/test_frontmatter.py:123-163`.
- **Confidence:** Medium-High

### Finding 6
- **Summary:** Special create flows already pass metadata through project-scoped template/rendering and registry paths, so Blueprint can extend those branches without replacing them.
- **Evidence:** `src/scribe_mcp/doc_management/special_create.py:335-443`, `src/scribe_mcp/doc_management/special_create.py:446-525`, `src/scribe_mcp/doc_management/special_create.py:637-663`.
- **Confidence:** High

### Finding 7
- **Summary:** The template engine already flattens metadata into the render context, and the base document template renders only a narrow set of generic fields.
- **Evidence:** `src/scribe_mcp/template_engine/engine.py:342-393`, `src/scribe_mcp/templates/__init__.py:61-133`, `src/scribe_mcp/templates/documents/base_document.md:7-21`.
- **Confidence:** High

### Finding 8
- **Summary:** The test suite already proves the field contract for create-time normalization, frontmatter editing, and checklist/body behavior, but it does not yet fully lock the research-doc metadata surface end-to-end.
- **Evidence:** `tests/test_manage_docs_create_doc.py:137-245`, `tests/test_manage_docs_create_doc.py:593-777`, `tests/test_frontmatter.py:40-418`, `tests/test_template_engine_manage_docs.py:30-156`, `tests/test_template_engine_manage_docs.py:904-1026`.
- **Confidence:** Medium

### Additional Notes
- `manage_docs` create-path warnings already hint at a missing summary on create and at stale research index hygiene, which is useful context for Blueprint but not a reason to invent new metadata storage.
- The research doc itself is a managed artifact created through existing Scribe surfaces, which confirms the current pipeline is sufficient for this lane when used as intended.
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- The frontmatter pipeline is intentionally centralized in `manager.py`, with normalization, reserved-field enforcement, and attribution all handled in one place.
- The template engine is context-driven rather than metadata-schema-driven; templates consume whatever keys are present in the render context.
- Special create flows are thin wrappers that mostly choose templates, paths, and registry updates.
- `related_docs` is a body-derived topology signal, not a manually curated edge table.

**System Interactions:**
- Generic docs rely on `apply_doc_change` and the frontmatter utilities.
- Special docs rely on template rendering plus index/registry updates.
- Research, bug, security, review, and agent-card families are all already routed through separate but shared creation helpers.

**Risk Assessment:**
- If callers try to override reserved fields directly, the tool will ignore or normalize them, which can surprise downstream users unless documented.
- Because `related_docs` comes from body links, graph edges vanish when authors stop linking the related documents in the text.
- Special-create docs and generic frontmatter docs are different paths, so Blueprint should verify both when introducing any new metadata field or lifecycle rule.
- A separate stable-id concept would become a compatibility burden unless it is explicitly aliased to `id`.
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
- Add a focused contract note for the existing workflow-frontmatter surface so future contributors know the supported keys and the reserved fields.
- Add regression tests for research-doc create plus follow-up frontmatter edits, including `summary`, `tags`, `owners`, `status`, `related_docs`, `created_by`, `maintained_by`, and `edit_trace`.
- If Blueprint needs a stable-id alias, implement it as a compatibility alias of `id`, not as a new identifier subsystem.
- Refresh or regenerate any stale research index references that still point at removed artifacts.

### Long-Term Opportunities
- Promote the current workflow-frontmatter contract into a concise source-of-truth table in the repo docs.
- Add explicit tests for the special-create research path so it stays aligned with the generic frontmatter path over time.
- Consider generating a small metadata reference appendix from the same managed-doc contract if operators need a quick field map.
- Keep `related_docs` body-link extraction as the default graph primitive and extend it only if a genuinely stronger topology signal is required.
## Appendix
<!-- ID: appendix -->
- **References:** `src/scribe_mcp/tools/manage_docs.py`, `src/scribe_mcp/doc_management/manager.py`, `src/scribe_mcp/doc_management/runtime.py`, `src/scribe_mcp/doc_management/utils.py`, `src/scribe_mcp/doc_management/special_create.py`, `src/scribe_mcp/template_engine/engine.py`, `src/scribe_mcp/templates/__init__.py`, `src/scribe_mcp/templates/documents/base_document.md`, `src/scribe_mcp/templates/documents/RESEARCH_REPORT_TEMPLATE.md`, `src/scribe_mcp/templates/documents/BUG_REPORT_TEMPLATE.md`, `src/scribe_mcp/templates/documents/REVIEW_REPORT_TEMPLATE.md`, `tests/test_frontmatter.py`, `tests/test_manage_docs_create_doc.py`, `tests/test_template_engine_manage_docs.py`.
- **Attachments:** Canonical managed research artifact at `.scribe/docs/dev_plans/scribe_document_topology_foundation_20260524/research/RESEARCH_SCRIBE_METADATA_SURFACE.md`. The artifact intentionally reuses existing Scribe surfaces and does not introduce a separate metadata system.
