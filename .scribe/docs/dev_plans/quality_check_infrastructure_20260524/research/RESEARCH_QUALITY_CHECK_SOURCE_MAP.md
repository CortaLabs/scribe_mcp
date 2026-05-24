# 🔬 Research Quality Check Source Map — quality_check_infrastructure_20260524
**Author:** ResearchAgent-QualityCheck
**Version:** v0.1
**Status:** in_progress
**Last Updated:** 2026-05-24 03:18 UTC

> Source-map only. No implementation changes were made in this wave.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Source-map the current `manage_docs(action="quality_check")` implementation only, with evidence for routing, warning collectors, markdown parsing assumptions, supported response shape, and regression coverage.

**Key Takeaways:**
- The public `manage_docs` wrapper is thin. `runtime.handle_manage_docs_request` routes `quality_check` and `scaffold_quality_check` into `_handle_quality_check`.
- The warning semantics live in `src/scribe_mcp/doc_management/scaffold_quality.py`, with changelog/version helpers in `changelog.py` and context resolution in `version_context.py`.
- The checker is deliberately lightweight and mostly line/regex driven, which keeps it deterministic but makes nested fenced examples, tables, and some anchor-style prose semantics the most brittle areas.

---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-QualityCheck

**Investigation Window:** 2026-05-23 to 2026-05-24

**Focus Areas:**
- Route and response shape for `manage_docs(action="quality_check")`.
- Collector seams for scaffold residue, changelog/version drift, readiness blockers, warning locations, excerpts, severities, and config overrides.
- Markdown parsing assumptions for frontmatter, fences, quotes, headings, anchors, tables, and examples.
- Existing regression tests and obvious gaps.

**Dependencies & Constraints:**
- Source-map only. No fixes, no architecture design, no code changes.
- The nested fenced-code false positive called out by the SPEC is the main known parsing risk.
- The active project reminders already report scaffold residue and changelog coverage blockers in the surrounding workstream, so this research stays bounded to source truth only.

---
## Findings
<!-- ID: findings -->
### Finding 1
- **Summary:** `quality_check` is routed by `runtime.handle_manage_docs_request`, not by the public wrapper. The public `manage_docs` API only forwards arguments and the runtime branch resolves doc paths, registry aliases, explicit markdown paths, and runtime fallback warnings before collecting quality warnings.
- **Evidence:** `src/scribe_mcp/tools/manage_docs.py:94-116`, `src/scribe_mcp/doc_management/runtime.py:868-1072`, `src/scribe_mcp/doc_management/runtime.py:1736-1975`.
- **Confidence:** High.

### Finding 2
- **Summary:** The warning engine is centralized in `scaffold_quality.py`. `DEFAULT_WARNING_POLICIES`, `_warning`, `summarize_quality_warnings`, `_apply_quality_overrides`, `analyze_scaffold_quality`, `collect_managed_doc_quality_warnings`, `_research_context_drift_warnings`, `_changelog_warnings`, and `build_research_index_hygiene_warnings` together define codes, severities, blockers, locations, excerpts, suggested repairs, and suppression behavior.
- **Evidence:** `src/scribe_mcp/doc_management/scaffold_quality.py:18-42`, `src/scribe_mcp/doc_management/scaffold_quality.py:111-156`, `src/scribe_mcp/doc_management/scaffold_quality.py:183-232`, `src/scribe_mcp/doc_management/scaffold_quality.py:235-423`, `src/scribe_mcp/doc_management/scaffold_quality.py:426-652`.
- **Confidence:** High.

### Finding 3
- **Summary:** Markdown handling is heuristic rather than AST-based. Frontmatter is parsed via `parse_frontmatter`, then the body is scanned line-by-line. The checker suppresses some matches inside triple-backtick fences and blockquotes, strips simple markdown markup for lifecycle detection, and skips link-label placeholders on the same line. Tables are not parsed as tables; they are only matched by a regex for specific empty-finding patterns.
- **Evidence:** `src/scribe_mcp/utils/frontmatter.py:24-62`, `src/scribe_mcp/doc_management/scaffold_quality.py:117-180`, `src/scribe_mcp/doc_management/scaffold_quality.py:284-366`.
- **Confidence:** High.

### Finding 4
- **Summary:** The current test suite already covers the main `quality_check` contract, scaffold-quality codes and payload shape, changelog quality, research-context drift, and project-health integration. The obvious missing regressions are nested or alternate fenced-code examples, table-cell placeholders, and broader anchor/example variants that could still slip through the current line-based heuristics.
- **Evidence:** `tests/test_manage_docs_quality_check.py:57-340`, `tests/test_manage_docs_scaffold_quality.py:10-239`, `tests/doc_management/test_changelog_quality.py:8-120`, `tests/doc_management/test_research_context_drift.py:6-81`, `tests/test_manage_docs_project_health_quality.py:100-300`.
- **Confidence:** High for coverage inventory, medium for the gap callouts.

### Additional Notes
- `manager.apply_doc_change` reuses the same collector by attaching `scaffold_quality_warnings` into edit results, and `actions/edit.py` turns those warnings into readiness blocks for done-state claims.
- `changelog.py` is a good reuse seam because it already handles accepted entries, safe provenance, global reconciliation, and current-version coverage checks without depending on runtime routing.

---
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- `scaffold_quality.py` is the center of gravity and shows god-module pressure: policies, generic warning construction, markdown-ish parsing, changelog checks, research-index hygiene, and config overrides all live together.
- `runtime._handle_quality_check` is the main orchestration seam and also a pressure point: it handles session/project authority, explicit markdown-path recovery, research-doc rebinding, registry fallback, runtime warning collection, and response assembly.
- `changelog.py`, `version_context.py`, and `utils/frontmatter.py` are cleaner reusable helpers that the checker already depends on instead of reimplementing those responsibilities.

**System Interactions:**
- `manage_docs(action="quality_check")` -> `handle_manage_docs_request` -> `_handle_quality_check` -> `collect_managed_doc_quality_warnings`.
- `collect_managed_doc_quality_warnings` fans out into `analyze_scaffold_quality`, changelog-specific warnings, research-context drift warnings, and research-index hygiene warnings when the target is a research doc with a resolvable path.
- `apply_doc_change` also reuses the collector for preview/readiness blocking, so this code influences both the direct check action and mutation-time done-state gating.

**Risk Assessment:**
- Nested fenced examples are still fragile because `_in_code_fence()` is a parity check on triple-backtick count, not a real markdown parser. That makes nested fences, alternate fence styles, and embedded fence examples the most likely false-positive/false-negative area.
- The checker does not understand tables as structured markdown; it just uses regexes against raw text. Any future table-driven docs could accumulate accidental matches unless tests guard them.
- Runtime path recovery is powerful but branchy. Registry rebinding, explicit markdown paths, and research-family recovery all coexist, which raises the risk of subtle behavior changes if aliasing or path rules evolve.

---
## Recommendations
<!-- ID: recommendations -->
### Immediate Next Steps
- Add regression tests for nested fenced-code examples, alternate fence styles, and table-cell marker text.
- Add one explicit route test for the `scaffold_quality_check` alias so the runtime dispatch stays intentional.
- Keep reusing `collect_managed_doc_quality_warnings`, `summarize_quality_warnings`, `parse_changelog_entries`, `preview_current_release_coverage`, and `parse_frontmatter` rather than splitting the semantics across new parallel helpers.

### Long-Term Opportunities
- Split `scaffold_quality.py` into smaller collector modules behind a thin dispatcher facade so new doc-type rules do not keep accreting in one file.
- Consider a markdown-aware parser layer for the few behaviors that are currently heuristic only, especially fenced-code and table handling.
- Keep runtime routing thin and authority-aware; the doc-resolution and warning composition helpers already exist and should be extended before introducing new branches.

---
## Appendix
<!-- ID: appendix -->
- `src/scribe_mcp/doc_management/runtime.py:868-1072` - quality-check routing, path recovery, response shape.
- `src/scribe_mcp/doc_management/scaffold_quality.py:18-42` - warning policies.
- `src/scribe_mcp/doc_management/scaffold_quality.py:111-180` - line/markdown helper functions for warnings.
- `src/scribe_mcp/doc_management/scaffold_quality.py:235-423` - scaffold analysis, changelog hooks, and collector fan-out.
- `src/scribe_mcp/doc_management/scaffold_quality.py:426-652` - research drift and index hygiene warnings.
- `src/scribe_mcp/doc_management/changelog.py:28-358` - changelog parsing and release coverage helpers.
- `src/scribe_mcp/utils/frontmatter.py:24-62` - frontmatter parser used before body scanning.
- `tests/test_manage_docs_quality_check.py:57-340` - direct `quality_check` coverage.
- `tests/test_manage_docs_scaffold_quality.py:10-239` - scaffold-quality payload and suppression coverage.
- `tests/doc_management/test_changelog_quality.py:8-120` - changelog warnings and current-version coverage.
- `tests/doc_management/test_research_context_drift.py:6-81` - research-context drift coverage.
- `tests/test_manage_docs_project_health_quality.py:100-300` - project-health integration for quality digests.
