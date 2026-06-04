
# 🔬 Research Sentinel Case Authority — scribe_mcp_bug_log_tooling_20260604
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-06-04 01:49:49 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** [Describe the primary research goal]

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
<!-- ID: research_scope -->
This research covers the BUG/SEC open-and-fix lifecycle in `src/scribe_mcp/tools/sentinel_tools.py`, the shared case registry/listing path in `src/scribe_mcp/tools/list_open_cases.py` and storage models, and the regression tests that pin the expected contract. The central question is whether BUG/SEC authority lives in repo-root governed report docs, Scribe project docs, registry rows, or a combination.

Bottom line: the implementation is a combination model.
- The Scribe project progress log is used to allocate the per-day case_id and to make the fresh case immediately queryable (`append_entry` + registration event).
- The repo-root governed report doc is the narrative artifact created for the case and later edited by `manage_docs`.
- The shared case registry row is the operational authority for listing and link-fix ownership checks.

Confidence: high. Evidence comes directly from source and tests in `sentinel_tools.py`, `list_open_cases.py`, `doc_management/utils.py`, `doc_management/special_create.py`, and the targeted tests.
## Findings
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.
### Finding 1
- **Summary:** [Describe the finding]
- **Evidence:** [Link to logs, code references, or experiments]
- **Confidence:** Medium

### Finding 2
- **Summary:** [Describe the finding]
- **Evidence:** [Link to supporting material]
- **Confidence:** Medium

### Additional Notes
- Capture supporting observations or open follow-ups.


---
## Technical Analysis
<!-- ID: technical_analysis -->
### Findings

1. `open_bug` and `open_security` follow the same project-mode lifecycle: validate `category`, append a project log entry, allocate a date-scoped case ID from the appended log path, emit a second registration entry so the case is queryable immediately, create the governed report doc, and then upsert a shared case-registry row. Confidence: high (`src/scribe_mcp/tools/sentinel_tools.py:798-965`, `src/scribe_mcp/tools/sentinel_tools.py:1093-1260`).

2. The authority model is a combination, not a single surface. The repo-root governed report doc is the narrative artifact, but the registry row is the operational source for ownership, listing, and fix-link authorization. The project progress log is the ingestion event that seeds the case ID and queryability. Confidence: high (`src/scribe_mcp/tools/sentinel_tools.py:808-889`, `src/scribe_mcp/tools/sentinel_tools.py:905-965`, `src/scribe_mcp/tools/sentinel_tools.py:1248-1309`, `src/scribe_mcp/tools/sentinel_tools.py:1421-1603`, `src/scribe_mcp/tools/list_open_cases.py:175-300`, `tests/test_case_registry_ownership.py:83-123`).

3. `list_open_cases` is registry-first and repo/project scoped. It defaults to the active execution context, queries the shared registry by `repo_root`, `project_name`, and `case_type`, filters to open statuses plus requested repo/category/severity, and returns normalized case objects that include `case_id`, `case_type`, `title`, `status`, `severity`, `category`, `project`, `repo_id`, `doc_type`, `doc_name`, `doc_path`, `created_at`, and `updated_at`. Confidence: high (`src/scribe_mcp/tools/list_open_cases.py:119-300`, `tests/test_list_open_cases.py:95-240`).

4. `link_fix` is registry-authorized and report-doc-aware. It rejects invalid case IDs or missing artifact/landing data, loads the case registry row with active repo/project ownership checks, writes a fix-link event, merges `fix_link` metadata back into the registry row, and then updates the report doc using the registry row's `doc_name` plus `manage_docs replace_section` for `appendix` and `resolution_plan`. Confidence: high (`src/scribe_mcp/tools/sentinel_tools.py:1354-1654`, `tests/test_case_registry_ownership.py:126-255`, `tests/test_sentinel_tools.py:401-550`, `tests/test_sentinel_tools.py:915-941`).

5. The follow-up editing contract depends on coherent registry fields. `build_case_registry_upsert_kwargs` requires `case_id`, `case_type`, `project_name`, `repo_root`, `doc_type`, `doc_name`, and `doc_path`; `list_open_cases` exposes `doc_name` and `doc_path`; `link_fix` uses `doc_name` to resolve which report doc to patch. If `manage_docs` path resolution changes, these fields must stay in lockstep or `link_fix` and `list_open_cases` will drift. Confidence: high (`src/scribe_mcp/doc_management/utils.py:637-700`, `src/scribe_mcp/doc_management/special_create.py:446-503`, `src/scribe_mcp/tools/list_open_cases.py:144-166`, `src/scribe_mcp/tools/sentinel_tools.py:1503-1559`).

### Return Payload Gaps

- Present on successful project-mode open: `case_id`, `artifacts`, `next_step`, `entry_id`, `path` (append-entry path), `project_name`, `bug_report` or `security_report`, `completeness`, and `action_required`. Confidence: high (`src/scribe_mcp/tools/sentinel_tools.py:995-1023`, `src/scribe_mcp/tools/sentinel_tools.py:1290-1318`).
- Missing from successful project-mode open: explicit `doc_name`, `doc_type`, `registry_id`, `repo_id`, and a direct registry row reference. The report path is only returned via `bug_report`/`security_report`; the registry row itself is not echoed. Confidence: high (`src/scribe_mcp/tools/sentinel_tools.py:995-1023`, `src/scribe_mcp/tools/sentinel_tools.py:1290-1318`).
- Sentinel-mode preview returns only a preview `case_id` and `next_step`, so it is intentionally non-mutating and does not expose report or registry paths. Confidence: high (`src/scribe_mcp/tools/sentinel_tools.py:812-828`, `src/scribe_mcp/tools/sentinel_tools.py:1105-1123`, `tests/tools/test_sentinel_case_ids.py:32-110`).

### Implications For Blueprint

- Keep the managed report path canonical and derive follow-up edits from the returned `case_id` plus the registry row, not from shell-constructed paths.
- Preserve `doc_name == case_id` for newly opened BUG/SEC cases unless a deliberate contract change updates both registry and link-fix consumers.
- Preserve the registry metadata keys `category`, `ownership`, `execution_provenance`, and `fix_link`, because tests and list/link flows depend on them.
- If `manage_docs` resolution is widened or re-keyed, update the open-flow return payloads so operators still receive an obvious follow-up handle for the same artifact.
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
### Evidence Index

| Topic | Evidence |
| --- | --- |
| Case ID allocation and non-mutating preview | `src/scribe_mcp/tools/sentinel_tools.py:127-270`, `src/scribe_mcp/tools/sentinel_tools.py:273-353`, `tests/tools/test_sentinel_case_ids.py:31-110` |
| Project-mode open lifecycle | `src/scribe_mcp/tools/sentinel_tools.py:808-965`, `src/scribe_mcp/tools/sentinel_tools.py:1103-1260` |
| Registry ownership and upsert payload | `src/scribe_mcp/tools/sentinel_tools.py:469-620`, `src/scribe_mcp/doc_management/utils.py:637-700`, `tests/test_case_registry_ownership.py:83-123` |
| Listing contract | `src/scribe_mcp/tools/list_open_cases.py:119-300`, `tests/test_list_open_cases.py:95-240` |
| Fix-link contract | `src/scribe_mcp/tools/sentinel_tools.py:1354-1654`, `tests/test_case_registry_ownership.py:126-255`, `tests/test_sentinel_tools.py:401-550`, `tests/test_sentinel_tools.py:915-941` |
| Managed report path resolution | `src/scribe_mcp/doc_management/special_create.py:446-503`, `src/scribe_mcp/doc_management/utils.py:447-700` |

### Blueprint Constraints

1. Keep BUG/SEC case opening on the combined authority path: project log entry, governed report doc, and shared registry row.
2. Do not replace registry authority with report-path inference alone; `link_fix` and `list_open_cases` rely on registry scope and metadata.
3. If manage_docs resolution is changed, update the open return payloads so follow-up editing stays obvious and stable.
4. Preserve `doc_name == case_id` for fresh cases unless the registry/link contract is deliberately reworked together.
5. Preserve the current metadata keys used for ownership, execution provenance, category, and fix link so case registry mutations remain merge-safe.
