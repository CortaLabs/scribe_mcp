---
id: agent_param_audit-research-agent-param-audit-20260120
title: "\U0001F52C Research Agent Param Audit 20260120 \u2014 agent_param_audit"
doc_name: RESEARCH_AGENT_PARAM_AUDIT_20260120
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-20'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Agent Param Audit 20260120 — agent_param_audit
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-20 05:46:39 UTC

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
**Research Lead:** Scribe

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
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
## Technical Analysis

### Summary Statistics

| Status | Count | Details |
|--------|-------|---------|
| **Has agent param (OPTIONAL)** | 7 | append_entry, read_file, query_entries, read_recent, sentinel: append_event, rotate_log, generate_doc_templates |
| **Has agent param (REQUIRED)** | 1 | set_project |
| **Needs agent param** | 9 | manage_docs, get_project, list_projects, delete_project, health_check, doctor, sentinel: open_bug, open_security, link_fix |
| **TOTAL TOOLS** | 17 | All @app.tool() decorated functions |

### Complete Audit Table

| # | File | Function | Line | Current Signature | Has agent? | Type | Needs Change? | Notes |
|---|------|----------|------|-------------------|-----------|------|---------------|-------|
| 1 | append_entry.py | append_entry | 1241 | `append_entry(message="", status=None, emoji=None, **agent: Optional[str]**, ...)` | YES | OPTIONAL | NO | Already has agent parameter with full support |
| 2 | set_project.py | set_project | 190 | `set_project(name: str, **agent: str**, root=None, ...)` | YES | REQUIRED | NO | Agent REQUIRED for session identity - correct design |
| 3 | manage_docs.py | manage_docs | 1117 | `manage_docs(action: str, doc_category: str, ..., project=None)` | NO | N/A | YES | Missing agent parameter - needs addition |
| 4 | get_project.py | get_project | 353 | `get_project(project=None, format="structured", verbose=False)` | NO | N/A | YES | Missing agent parameter - needs addition |
| 5 | list_projects.py | list_projects | 183 | `list_projects(limit=5, filter=None, ...)` | NO | N/A | YES | Missing agent parameter - needs addition |
| 6 | read_file.py | read_file | 1694 | `read_file(path: str, mode="scan_only", ..., allow_outside_repo=False)` | NO | N/A | YES | Missing agent parameter - needs addition |
| 7 | read_recent.py | read_recent | 156 | `read_recent(project=None, n=None, limit=None, ...)` | NO | N/A | YES | Missing agent parameter - needs addition |
| 8 | query_entries.py | query_entries | 1002 | `query_entries(project=None, start=None, ..., **agent: Optional[Any]**, agents=None, ...)` | YES | OPTIONAL | NO | Has agent parameter with legacy single-agent support |
| 9 | delete_project.py | delete_project | 24 | `delete_project(name: str, root: str, mode="archive", ..., agent_id=None)` | PARTIAL | OPTIONAL (as agent_id) | NO | Has agent_id instead of agent - functionally equivalent but naming inconsistent |
| 10 | rotate_log.py | rotate_log | 1368 | `rotate_log(project=None, suffix=None, ..., config=None, format="structured")` | NO | N/A | YES | Missing agent parameter - needs addition |
| 11 | generate_doc_templates.py | generate_doc_templates | 46 | `generate_doc_templates(project_name: str, author=None, ...)` | NO | N/A | YES | Missing agent parameter - needs addition |
| 12 | sentinel_tools.py | append_event | 73 | `append_event(message=None, status=None, emoji=None, **agent: Optional[str]**, ...)` | YES | OPTIONAL | NO | Has agent parameter - sentinel wrapper for append_entry |
| 13 | sentinel_tools.py | open_bug | 194 | `open_bug(title: str, symptoms: str, affected_paths=None)` | NO | N/A | YES | Missing agent parameter - case creation tool |
| 14 | sentinel_tools.py | open_security | 217 | `open_security(title: str, symptoms: str, affected_paths=None)` | NO | N/A | YES | Missing agent parameter - case creation tool |
| 15 | sentinel_tools.py | link_fix | 240 | `link_fix(case_id: str, execution_id: str, artifact_ref: str, landing_status: str)` | NO | N/A | YES | Missing agent parameter - case linking tool |
| 16 | health_check.py | health_check | 22 | `health_check()` | NO | N/A | NO | No parameters at all - uses auto-detection from server context |
| 17 | doctor.py | scribe_doctor | 32 | `scribe_doctor()` | NO | N/A | NO | No parameters at all - diagnostic tool, auto-detection appropriate |

### Detailed Findings by Category

#### Category A: Tools WITH agent parameter (8 tools) - NO CHANGE NEEDED
1. **append_entry** - OPTIONAL agent parameter - correctly implemented
2. **set_project** - REQUIRED agent parameter - correct for session identity
3. **query_entries** - OPTIONAL agent parameter - has legacy agent support
4. **read_file** - NO agent parameter - ANALYSIS: This tool uses ExecutionContext from server for repo discovery, agent identity can be auto-detected
5. **sentinel: append_event** - OPTIONAL agent parameter - wrapper around append_entry
6. **rotate_log** - NO agent parameter - ANALYSIS: Uses auto-detection from context
7. **generate_doc_templates** - NO agent parameter - ANALYSIS: Project-scoped operation, agent auto-detected
8. **delete_project** - Has agent_id (not agent) - ANALYSIS: Naming inconsistency but functionally equivalent

#### Category B: Tools WITHOUT agent parameter (9 tools) - NEED REVIEW FOR ADDITION

**Candidates for agent parameter addition (tools that should track agent identity):**
1. **manage_docs** - Document creation/modification - should track which agent made changes
2. **get_project** - Project retrieval - should track agent access patterns
3. **list_projects** - Project enumeration - should track agent query patterns
4. **read_recent** - Log reading - should track agent viewing history (optional)
5. **open_bug** - Case creation - should track which agent opened the bug
6. **open_security** - Security case creation - should track which agent reported the issue
7. **link_fix** - Case linking - should track which agent linked the fix

**Tools that DON'T need agent parameter (appropriate for auto-detection or parameterless design):**
1. **health_check** - System diagnostic, no parameters needed
2. **doctor** - System diagnostic, no parameters needed
3. **read_file** - Uses ExecutionContext repo_root discovery

### Reasoning and Constraint Analysis

**Why agent parameter matters:**
- Session isolation: Multiple agents may work in parallel; agent parameter creates audit trails per agent
- Agent identity tracking: Enables logging which agent made changes (append_entry already does this)
- Consistency: set_project REQUIRES agent, so other tools should accept it as OPTIONAL for consistency

**Constraints to consider:**
- Backward compatibility: Adding optional parameters is safe
- Auto-detection fallback: If agent not provided, can use server_module.get_agent_identity() pattern
- Parameter naming consistency: Some tools use `agent`, some use `agent_id` - should standardize

**Current patterns observed:**
- append_entry/query_entries/sentinel tools: use `agent: Optional[str]`
- delete_project: uses `agent_id: Optional[str]`
- Most project/doc tools: rely on auto-detection from context

### Recommended Actions

**Priority 1 - Add agent parameter (OPTIONAL) to these tools:**
- manage_docs
- get_project  
- list_projects
- read_recent
- rotate_log
- generate_doc_templates

**Priority 2 - Add agent parameter (OPTIONAL) to sentinel tools:**
- open_bug
- open_security
- link_fix

**Priority 3 - Standardize naming:**
- Change delete_project's `agent_id` to `agent` for consistency with other tools

**Not recommended for agent parameter:**
- health_check (diagnostic, no state changes)
- doctor (diagnostic, no state changes)
- read_file (utility, uses ExecutionContext for repo discovery)
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---