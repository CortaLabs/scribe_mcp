---
id: hello_world_scribe_20260418-research-scribe-feature-surface
title: "\U0001F52C Research Scribe Feature Surface \u2014 hello_world_scribe_20260418"
doc_type: RESEARCH_SCRIBE_FEATURE_SURFACE
doc_name: RESEARCH_SCRIBE_FEATURE_SURFACE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-18 13:28:06 UTC
maintained_by: agent-20260418-131659-0ccd443d
created_by: agent-20260418-131659-0ccd443d
owners: []
related_docs: []
tags: []
summary: ''
edit_trace:
  tool: manage_docs
  created_at: 2026-04-18 13:27:08 UTC
  created_via: replace_section
  last_edited_at: 2026-04-18 13:28:06 UTC
  last_edited_by: agent-20260418-131659-0ccd443d
  last_action: replace_section
---

# 🔬 Research Scribe Feature Surface — hello_world_scribe_20260418
**Author:** Scribe
**Version:** v0.1
**Status:** draft
**Last Updated:** 2026-04-18 13:26:26 UTC

> Authoritative operator-facing feature taxonomy and coverage matrix for the current Scribe repository.

---
## Executive Summary
<!-- ID: executive_summary -->This research establishes an operator-facing taxonomy for the currently registered Scribe tool surface and separates core workflow capabilities from support/admin surfaces so planning can scope the hello-world demo without losing truthfulness. The canonical inventory is the 23-tool registration contract in `tests/test_tool_metadata_contract.py:6-30`, aligned with the runtime registry/discovery path in `src/scribe_mcp/server.py:622-647` and `src/scribe_mcp/server.py:1158-1189`.

Primary conclusion: the feature surface is best planned as seven operator-relevant families (session/project bootstrap, logging/history, repo inspection/mutation, structured docs, case lifecycle, reminders, diagnostics) plus a bounded support/admin appendix. This keeps the demo aligned to the planning definition of “every feature” as meaningful operator-facing capability rather than internal helpers (FRAME: 38-43, 45-51; SPEC: 63-71).

Planning implication: Blueprint and implementation should treat the matrix below as the truth source for required behavior coverage and side-effect boundaries, while explicitly deciding presentation treatment for overlap/ambiguity points (`append_event`, `read_recent` vs `query_entries`, reminder configuration depth, and admin/support tools).


---
## Research Scope
<!-- ID: research_scope -->
## Research Scope
This research defines the authoritative operator-facing Scribe feature surface for the current repository. The planning docs explicitly say that “every single feature” should be interpreted as every meaningful operator-facing capability, not every hidden helper, and they ask for a coverage matrix that separates real side effects from read-only observation (FRAME: lines 38-43, 45-51; SPEC: lines 63-71).

The source of truth for the registered surface is `server.list_registered_tools()` / `describe_registered_tools()` in `src/scribe_mcp/server.py:1158-1189`, which are populated from the tool registry built during tool decoration in `src/scribe_mcp/server.py:622-647`. The current test contract enumerates the registered tool set in `tests/test_tool_metadata_contract.py:6-30` and verifies that every registered tool exposes title, description, annotations, metadata, and tags in `tests/test_tool_metadata_contract.py:44-59`.

This pass also used behavior-specific tests to confirm the semantics of the main families: session resolution advisories for `read_recent` and `get_project` (`tests/test_session_resolution_advisories.py:16-63`), explicit project resolution for `query_entries` (`tests/test_query_entries_explicit_project_resolution.py:12-84`), reminder registration and state changes (`tests/test_reminder_tools.py:83-176`), and shared case registry ownership for `open_bug`, `open_security`, and `link_fix` (`tests/test_case_registry_ownership.py:42-218`).
## Findings
<!-- ID: findings -->
### Finding 1: Canonical coverage boundary is the 23-tool registry, not the older phase subset
- **Summary:** The authoritative “what exists now” boundary is the 23-tool metadata contract and server registry/discovery path; older phase scripts are partial scaffolding and should not drive planning completeness claims.
- **Evidence:** `tests/test_tool_metadata_contract.py:6-30`; `src/scribe_mcp/server.py:622-647`; `src/scribe_mcp/server.py:1158-1189`; cross-check note in Technical Analysis.
- **Confidence:** High

### Finding 2: The operator-facing surface clusters cleanly into workflow families with clear side-effect distinctions
- **Summary:** The matrix supports a stable taxonomy where read-only observation surfaces (`read_file`, `search`, `query_entries`, `query_reminders`, `scribe_doctor`) are distinct from mutation surfaces (`append_entry`, `manage_docs`, `edit_file`, case/reminder mutation tools), and where startup sequencing (`set_project` first) remains foundational.
- **Evidence:** Capability families and tool-to-capability matrix in Technical Analysis; `src/scribe_mcp/tools/set_project.py:380-416`; `src/scribe_mcp/tools/read_file.py:1782-1821`; `src/scribe_mcp/tools/edit_file.py:174-260`; `src/scribe_mcp/tools/query_entries.py:1169-1245`; `src/scribe_mcp/tools/reminder_tools.py:137-170`.
- **Confidence:** High

### Finding 3: A small ambiguity set must be resolved at planning/presentation level, not by changing capability truth
- **Summary:** The remaining uncertainty is presentation/packaging ambiguity, not feature discovery ambiguity: `append_event` behaves as compatibility delegation, `read_recent` overlaps with `query_entries`, reminder tooling has optional depth, and several registered tools are support/admin surfaces.
- **Evidence:** `src/scribe_mcp/tools/sentinel_tools.py:579-640`; `src/scribe_mcp/tools/read_recent.py:170-240`; `src/scribe_mcp/tools/query_entries.py:1169-1245`; `tests/test_reminder_tools.py:83-176`; `tests/test_tool_metadata_contract.py:6-30`; Ambiguities section below.
- **Confidence:** High

### Additional Notes
- No evidence in this pass contradicts the matrix taxonomy or side-effect boundaries.
- Medium-confidence items are confined to depth-of-presentation decisions for support/admin tools rather than core workflow behavior.


---
## Technical Analysis
<!-- ID: technical_analysis -->
## Feature Taxonomy

### Capability Families

| Family | Tools | Operator-facing? | Required side effects / sequencing | Evidence |
|---|---|---:|---|---|
| Session bootstrap and project registry | `set_project`, `get_project`, `list_projects`, `read_recent` | Yes | `set_project` must happen first for a fresh session; `read_recent` and most read/write tools depend on execution context/session binding; `list_projects` is scoped by current repo unless `global_mode=True`; `get_project` can recover via compatibility modes. | `src/scribe_mcp/tools/set_project.py:380-416`; `src/scribe_mcp/tools/get_project.py:402-470`; `src/scribe_mcp/tools/list_projects.py:209-252`; `src/scribe_mcp/tools/read_recent.py:170-240`; `CLAUDE.md:572-582` |
| Logging and history | `append_entry`, `append_event`, `query_entries`, `read_recent`, `scribe_doctor` | Mostly yes; `append_event` is supporting | `append_entry` writes progress/log records and accepts bulk/multiline/config forms; `append_event` is a compatibility wrapper that routes to `append_entry` in project mode or emits sentinel events outside it; `query_entries` searches the project log; `read_recent` is a recent-history view; `scribe_doctor` is diagnostics-only. | `src/scribe_mcp/tools/append_entry.py:1069-1125`; `src/scribe_mcp/tools/sentinel_tools.py:579-640`; `src/scribe_mcp/tools/query_entries.py:1169-1245`; `src/scribe_mcp/tools/read_recent.py:170-240`; `src/scribe_mcp/tools/doctor.py:219-290` |
| Repository inspection and mutation | `read_file`, `search`, `edit_file` | Yes | `read_file` and `search` are read-only inspection surfaces; `edit_file` requires prior `read_file` use in the current session, defaults to `dry_run=True`, and enforces repo-boundary/symlink checks before writing. | `src/scribe_mcp/tools/read_file.py:1782-1821`; `src/scribe_mcp/tools/search.py:590-660`; `src/scribe_mcp/tools/edit_file.py:174-260`; `tests/test_tool_metadata_contract.py:62-70` |
| Structured document management | `manage_docs` | Yes | `manage_docs` is the canonical structured-doc workflow; create/edit operations are frontmatter-aware, preserve `created_by`, default `maintained_by`, and treat `edit_trace` as tool-authored. It depends on state resolution and the runtime doc-management path. | `src/scribe_mcp/tools/manage_docs.py:74-166`; `CLAUDE.md:586-607` |
| Bug and security case lifecycle | `open_bug`, `open_security`, `link_fix` | Yes | `open_bug`/`open_security` require a non-empty category and in project mode create a case record, append a log entry, and create a report doc; `link_fix` requires a `BUG-` or `SEC-` case id plus a valid execution chain and case ownership. | `src/scribe_mcp/tools/sentinel_tools.py:700-781`; `src/scribe_mcp/tools/sentinel_tools.py:995-1065`; `src/scribe_mcp/tools/sentinel_tools.py:1290-1355`; `tests/test_case_registry_ownership.py:42-218`; `CLAUDE.md:599-607` |
| Reminder lifecycle | `query_reminders`, `configure_reminders`, `reset_reminders` | Yes | Reminder tools require a project binding; `query_reminders` is read-only and returns history/active reminders, `configure_reminders` mutates defaults, and `reset_reminders` refuses to run unless at least one reset flag is true. | `src/scribe_mcp/tools/reminder_tools.py:137-170`; `src/scribe_mcp/tools/reminder_tools.py:309-340`; `tests/test_reminder_tools.py:83-176` |
| Diagnostics / environment introspection | `scribe_doctor` | Yes | No mutation; returns runtime diagnostics, env/config state, plugin inventory, storage diagnostics, and authority snapshots. | `src/scribe_mcp/tools/doctor.py:219-290` |
| Admin / support / internal plumbing | `delete_project`, `generate_doc_templates`, `list_open_cases`, `authorize_repo_root`, `rotate_log` | Mixed; mostly admin/support | These are in the registered surface but are not part of the primary hello-world narrative yet. They are best treated as appendix/admin capabilities unless Blueprint explicitly decides to feature them. | `tests/test_tool_metadata_contract.py:6-30`; `tests/test_all_tools_phase5.py:11-28` |

### Tool-to-Capability Matrix

| Tool | Capability family | Surface | Key prerequisites / side effects | Confidence |
|---|---|---|---|---|
| `set_project` | Session bootstrap and project registry | Operator-facing | Requires `agent` and `root`; records tool state, binds session identity, and establishes repository authority. | High |
| `read_recent` | Logging and history | Operator-facing | Uses active project/session context; can fall back to compatibility resolution; returns recent entries plus advisories. | High |
| `append_entry` | Logging and history | Operator-facing write surface | Writes log entries, supports multiline/bulk/config payloads, and tolerates unknown kwargs; records tool activity. | High |
| `append_event` | Logging and history | Supporting / compatibility surface | In project mode it delegates to `append_entry`; otherwise it emits sentinel events. It is real surface, but not a distinct primary workflow. | High |
| `manage_docs` | Structured document management | Operator-facing write surface | Requires state resolution; create/edit semantics are frontmatter-aware and preserve lifecycle metadata. | High |
| `read_file` | Repository inspection | Operator-facing read-only | Must run inside execution context; denies repo escapes and requires `include_dependencies` if `include_impact=True`. | High |
| `search` | Repository inspection | Operator-facing read-only | Requires execution context and repo root; supports path/glob/type filters, paging, regex, and binary/file-size guards. | High |
| `edit_file` | Repository mutation | Operator-facing write surface | Requires prior `read_file` on the path in the current session; defaults to dry-run and blocks repo-boundary escapes. | High |
| `query_entries` | Logging and history | Operator-facing read-only | Requires explicit project resolution; supports log search filters, pagination, priorities, categories, and confidence thresholds. | High |
| `list_projects` | Session bootstrap and project registry | Operator-facing read-only | Defaults to current repo scope; can widen to global mode; supports pagination/filtering and compatibility recovery modes. | High |
| `get_project` | Session bootstrap and project registry | Operator-facing read-only | Resolves active or explicit project; supports compatibility modes and can attach recent log / resolution metadata. | High |
| `scribe_doctor` | Diagnostics / environment introspection | Operator-facing read-only | No direct state mutation; reports runtime config, plugin inventory, storage diagnostics, and authority state. | High |
| `open_bug` | Bug/security case lifecycle | Operator-facing write surface | Requires category; in project mode it appends a bug log entry, creates a bug report doc, and allocates a stable case id. | High |
| `open_security` | Bug/security case lifecycle | Operator-facing write surface | Same pattern as `open_bug`, but security-specific case type and default severity. | High |
| `link_fix` | Bug/security case lifecycle | Operator-facing write surface | Requires valid case id and execution id; enforces case ownership and links the landed artifact back to the case record. | High |
| `query_reminders` | Reminder lifecycle | Operator-facing read-only | Requires project binding; returns history and active reminders. | High |
| `reset_reminders` | Reminder lifecycle | Admin/support write surface | Requires project binding and at least one reset flag; can clear cooldowns and/or history. | High |
| `configure_reminders` | Reminder lifecycle | Admin/support write surface | Registered in tests; mutates project reminder defaults. | Medium |
| `delete_project` | Admin / support | Admin destructive surface | Registered tool; treat as destructive admin operation, not a hello-world demo step. | Medium |
| `generate_doc_templates` | Admin / support | Supporting tool | Registered tool; likely scaffolds docs/templates rather than core demo behavior. | Medium |
| `list_open_cases` | Case support | Supporting / admin surface | Registered tool; likely lists tracked cases and supports case triage. | Medium |
| `authorize_repo_root` | Security / bootstrap support | Internal/admin support | Registered tool; likely establishes or validates repo-root authorization. | Medium |
| `rotate_log` | Logging support | Internal/admin support | Registered tool; likely log maintenance/rotation rather than operator workflow. | Medium |

### Notable Cross-Checks

- `tests/test_tool_metadata_contract.py:6-30` is the current authoritative registration list for the repo, and it is larger than the older Phase 5 script.
- `tests/test_all_tools_phase5.py:11-28` still lists a 16-tool audit subset; treat it as historical/coverage scaffolding, not the final inventory.
- `src/scribe_mcp/server.py:622-647` is the actual tool registry write path, while `src/scribe_mcp/server.py:1158-1189` is the discovery/export path used by CLI tooling.
## Recommendations
<!-- ID: recommendations -->Translate the matrix and cross-checks into immediate planning moves.
### Immediate Next Steps
- [ ] Use the 23-tool contract (`tests/test_tool_metadata_contract.py:6-30`) as the single acceptance boundary for “feature-surface completeness” in planning artifacts and review gates.
- [ ] Keep the core demo narrative centered on the operator workflow families in this document; move support/admin tools (`delete_project`, `generate_doc_templates`, `list_open_cases`, `authorize_repo_root`, `rotate_log`) to an explicit appendix track unless operator scope expands.
- [ ] Make explicit presentation choices for the ambiguity set before implementation handoff: treat `append_event` as compatibility/support, define primary-vs-secondary use of `read_recent` and `query_entries`, and decide whether reminder configuration is in-scope or appendix-only.
- [ ] Preserve side-effect safety in all planned examples: `set_project` first, no write operations without explicit mutation intent, and `edit_file` only in flows that satisfy read-before-edit constraints.

### Long-Term Opportunities
- Add a maintained generated “operator feature catalog” artifact derived from `describe_registered_tools()` and matrix labels to reduce drift between registry truth and planning docs.
- Add a focused validation test that asserts demo-facing taxonomy groupings stay consistent with the registered tool list, so future capability additions trigger explicit planning decisions instead of implicit scope creep.


---
## Appendix
<!-- ID: appendix -->
## Ambiguities and Blueprint Inputs

### Ambiguities Blueprint Must Resolve

1. `append_event` is registered, but its implementation is a compatibility wrapper that either delegates to `append_entry` in project mode or emits a sentinel event directly (`src/scribe_mcp/tools/sentinel_tools.py:579-640`). Blueprint needs to decide whether this is a first-class demo surface or a supporting alias of the logging family.
2. `read_recent` and `query_entries` overlap conceptually. `read_recent` is the startup/history view with advisories and compatibility behavior (`src/scribe_mcp/tools/read_recent.py:170-240`; `tests/test_session_resolution_advisories.py:16-63`), while `query_entries` is the broader filtered search surface (`src/scribe_mcp/tools/query_entries.py:1169-1245`). Blueprint should decide whether the demo presents both or uses one as the primary example.
3. Reminder tooling has three registered forms: `query_reminders`, `configure_reminders`, and `reset_reminders` (`src/scribe_mcp/tools/reminder_tools.py:137-170; 309-340`; `tests/test_reminder_tools.py:83-176`). The minimum matrix only called out query/reset, so Blueprint must decide whether configuration belongs in the demo path or appendix.
4. The repo’s current authoritative registry list is the 23-tool contract in `tests/test_tool_metadata_contract.py:6-30`, but the older Phase 5 script still advertises a 16-tool subset (`tests/test_all_tools_phase5.py:11-28`). Blueprint should use the registry contract, not the older script, as the proof of “every feature.”
5. Several registered tools are clearly support/admin rather than hello-world narrative material: `delete_project`, `generate_doc_templates`, `list_open_cases`, `authorize_repo_root`, and `rotate_log` (`tests/test_tool_metadata_contract.py:6-30`). Blueprint should decide whether these go in an advanced appendix, an operator appendix, or are excluded from the core walkthrough.
6. `edit_file` is a distinct exposed mutation surface, but it is intentionally constrained by a read-before-edit rule and repo-boundary checks (`src/scribe_mcp/tools/edit_file.py:174-260`). Blueprint should decide whether to demonstrate it in the main demo or reserve it for an advanced editing appendix.

### Confidence

- High confidence: the registry contract, the primary families, and the side-effect boundaries for `set_project`, `read_recent`, `append_entry`, `manage_docs`, `read_file`, `search`, `edit_file`, `query_entries`, `open_bug`, `open_security`, `link_fix`, `query_reminders`, `reset_reminders`, and `scribe_doctor`.
- High confidence: `server.list_registered_tools()` / `describe_registered_tools()` are the authoritative discovery surfaces (`src/scribe_mcp/server.py:1158-1189`).
- Medium confidence: the exact role of the supporting/admin tools (`delete_project`, `generate_doc_templates`, `list_open_cases`, `authorize_repo_root`, `rotate_log`) because this pass verified registration but did not line-read each implementation.
- Medium confidence: `append_event` should be treated as supporting/compatibility rather than a separate demo family; that conclusion is strongly supported by its delegation structure, but Blueprint still needs to decide presentation.

### Handoff Notes for Blueprint

- Use `tests/test_tool_metadata_contract.py:6-30` as the canonical “what exists now” inventory.
- Use the registry/build/export path in `src/scribe_mcp/server.py:622-647` and `src/scribe_mcp/server.py:1158-1189` when proving coverage.
- Preserve the planning-doc definition of “every feature” as meaningful operator-facing capability, not every internal helper (`FRAME: 38-43`; `SPEC: 63-71`).
- Treat the additional admin/support tools as bounded appendix material unless the operator explicitly wants a broader governance demo.
