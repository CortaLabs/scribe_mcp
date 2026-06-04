
# 🔬 Report Templates and Test Surface — scribe_mcp_bug_log_tooling_20260604
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-06-04 01:52:34 UTC

> Research the bug/security report templates and regression-test surface for open_bug/open_security follow-up editing.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** Determine the section IDs, creation paths, and regression-test gaps for bug/security report follow-up editing.

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent

**Investigation Window:** 2026-06-03

**Focus Areas:**
- Verify the section anchors and metadata defaults exposed by the bug and security report templates.
- Confirm the create path for bug/security reports and the exact report file location.
- Verify how `manage_docs` resolves case-report paths for follow-up section replacement.
- Identify which regression tests already cover allocation, registry ownership, list-open behavior, and target resolution.

**Dependencies & Constraints:**
- Direct Scribe tools only; no shell edits and no source/test modifications.
- The report-template answer must be sourced from the templates themselves, not from assumptions about downstream docs.
- The solution should prefer existing infrastructure and avoid template edits if the contract is already present.
## Findings
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.
### Finding 1
- **Summary:** The bug and security report templates already expose the exact section anchors Blueprint needs for managed follow-up edits.
- **Evidence:** `src/scribe_mcp/templates/documents/base_document.md:25-35` defines the shared `section(title, anchor)` macro and the `<!-- ID: ... -->` anchor markers; `src/scribe_mcp/templates/documents/BUG_REPORT_TEMPLATE.md:8-77` exposes `bug_overview`, `description`, `investigation`, `resolution_plan`, and `appendix`; `src/scribe_mcp/templates/documents/SECURITY_REPORT_TEMPLATE.md:8-95` exposes `security_overview`, `description`, `affected_systems`, `investigation`, `resolution_plan`, and `appendix` plus `mitigation_status`.
- **Confidence:** High

### Finding 2
- **Summary:** The source already implements first-class special creation for case reports and registers the returned slug/path aliases for later lookup.
- **Evidence:** `src/scribe_mcp/doc_management/special_create.py:335-445` and `src/scribe_mcp/doc_management/special_create.py:446-503` create `docs/bugs/<category>/<date>_<slug>/report.md` and `docs/security/<category>/<date>_<slug>/report.md`; `src/scribe_mcp/doc_management/special_create.py:702-807` registers both the slug and legacy aliases and returns `path` and `doc_name`.
- **Confidence:** High

### Additional Notes
- `manage_docs` generic `create_doc` still routes through `_resolve_create_doc_path`, so follow-up edit success depends on the report being created through the special case-report path or an equivalent payload that preserves the report slug/path.
- The existing tests already cover allocation uniqueness, registry ownership, and list-open behavior, so the new regression should stay narrowly focused on case-report creation plus `replace_section` follow-up.


---
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- `BUG_REPORT_TEMPLATE.md` and `SECURITY_REPORT_TEMPLATE.md` both extend `documents/base_document.md` and therefore inherit the shared `section(title, anchor)` macro with `## <title>` plus an HTML `<!-- ID: <anchor> -->` marker. Bug anchors are `bug_overview`, `description`, `investigation`, `resolution_plan`, and `appendix`. Security adds `security_overview`, `affected_systems`, and `mitigation_status` in addition to the shared sections.
- The shared base template exposes global document metadata fields (`title`, `icon`, `status`, `version`, `author`, `last_updated`, `summary`) and is the source of truth for section-ID behavior used by `manage_docs replace_section`.
- `special_create.py` already has explicit `create_bug_report` and `create_security_report` branches that write `docs/bugs/<category>/<date>_<slug>/report.md` and `docs/security/<category>/<date>_<slug>/report.md`, respectively, register the slug plus legacy aliases, and return `path` and `doc_name` in the success payload.
- `manage_docs.py` itself resolves generic `create_doc` through `_resolve_create_doc_path`, while `replace_section` operates on an already-resolved document and requires an existing section anchor; that makes the follow-up edit contract dependent on the returned `path`/`doc_name`/slug alias being usable, not on new template sections.

**System Interactions:**
- `open_bug` and `open_security` already surface `bug_report` / `security_report`, `case_id`, `path`, and `project_name` in their success envelopes, which is exactly the kind of follow-up pointer a tool-based workflow needs.
- The remaining gap is not the report templates themselves; it is the action/resolution path between `open_bug`/`open_security` and the special-create branch that lands in the case-report tree.
- The existing registry and list-open tests show the repo already cares about repo-root ownership, case IDs, and normalized registry queries, so the follow-up edit behavior should slot into that model without changing list/open semantics.

**Risk Assessment:**
- If only the returned payload is improved but the action still resolves to the generic create path, the workflow can still land in the wrong document shape or location.
- If only the action is corrected but the returned path/doc_name is not surfaced clearly, users will still have a fragile follow-up editing experience.
- Template source changes are low-risk and likely unnecessary because the required anchors already exist in both case templates.
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] Add a regression that calls `open_bug`, asserts a returned `bug_report` path under `docs/bugs/runtime/.../report.md`, then uses `manage_docs(action='replace_section', doc=<returned path or slug alias>, section='description', content='...')` and verifies the section body is replaced cleanly.
- [ ] Add the same parity regression for `open_security`, asserting a returned `security_report` path under `docs/security/<category>/.../report.md` and a successful `replace_section` follow-up on a named anchor such as `description` or `affected_systems`.
- [ ] Extend the target-resolution test surface to prove that case-report paths or slug aliases resolve without guessing the docs tree layout.
- [ ] Keep the case-ID allocation tests and list-open filters unchanged unless the implementation explicitly changes those contracts.

### Long-Term Opportunities
- Normalize the `open_bug` and `open_security` return payloads so callers always receive the same follow-up identifiers: `case_id`, `path`, `bug_report`/`security_report`, and the report `doc_name` alias.
- Keep bug/security report creation behavior in special-create and avoid adding template-specific branching to the generic docs path unless future contracts require it.


---
## Appendix
<!-- ID: appendix -->
**References:**
- `src/scribe_mcp/templates/documents/base_document.md`
- `src/scribe_mcp/templates/documents/BUG_REPORT_TEMPLATE.md`
- `src/scribe_mcp/templates/documents/SECURITY_REPORT_TEMPLATE.md`
- `src/scribe_mcp/doc_management/special_create.py`
- `src/scribe_mcp/doc_management/manager.py`
- `src/scribe_mcp/tools/sentinel_tools.py`
- `tests/test_bug_management_regression_matrix.py`
- `tests/test_manage_docs_target_resolution.py`
- `tests/tools/test_sentinel_case_ids.py`
- `tests/test_phase2_case_registry_contract.py`
- `tests/test_list_open_cases.py`

**Attachments:**
- Managed research notes for Blueprint on bug/security report follow-up editing and regression coverage.
