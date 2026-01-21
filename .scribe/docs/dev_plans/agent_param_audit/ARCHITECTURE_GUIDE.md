---
id: agent_param_audit-architecture-guide
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 agent_param_audit"
doc_name: ARCHITECTURE_GUIDE
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

# 🏗️ Architecture Guide — agent_param_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-20 05:45:28 UTC

> Architecture guide for agent_param_audit.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
**Context:** 
Server.py now enforces agent parameter as REQUIRED for all tool calls (line 355: `raise ValueError("agent parameter is required for all tool calls")`). Currently, 14 out of 17 MCP tools are non-compliant with this enforcement:
- 4 tools have agent as Optional[str] (need to become REQUIRED)
- 9 tools completely lack agent parameter (need to add as REQUIRED)
- 1 tool uses `agent_id` instead of `agent` (naming inconsistency)

This causes immediate failures when tools are invoked without the agent parameter.

**Goals:**
- Make all MCP tools compliant with server.py enforcement
- Standardize agent parameter naming and positioning across all tools
- Maintain consistent parameter positioning (agent after primary identifier)
- Handle diagnostic tools (health_check, scribe_doctor) appropriately
- Preserve API consistency and minimize breaking changes
- Update all documentation to reflect new agent parameter requirement
- Update all agent instruction files with correct tool usage examples
- Update orchestration guides (CLAUDE.md files) with agent parameter

**Non-Goals:**
- Change server.py enforcement logic (it's correct as-is)
- Add optional fallbacks or auto-detection (defeats purpose of REQUIRED)
- Modify tools beyond parameter signature changes
- Change tool behavior or logic (only signatures)

**Success Metrics:**
- All 16 tools updated with agent: str parameter
- All tools accept agent in same position pattern (after primary ID)
- Zero server.py ValueError exceptions from missing agent parameter
- All existing tests updated and passing
- All reference documentation (Scribe_Usage.md, SCRIBE_PROTOCOL.md, SCRIBE_MCP_GUIDE.md) updated
- All 5 agent instruction files updated with agent parameter examples
- Both CLAUDE.md files updated with agent parameter in all examples
- No outdated tool signatures or examples remain in any documentation
<!-- ID: requirements_constraints -->
**Functional Requirements:**

**Code Changes:**
- FR1: Add `agent: str` parameter to all 14 non-compliant tools
- FR2: Position agent parameter consistently (after primary identifier like name/path/action)
- FR3: Remove Optional typing - agent must be REQUIRED with no default
- FR4: Rename `agent_id` to `agent` in delete_project.py for naming consistency
- FR5: Handle diagnostic tools (health_check, scribe_doctor) - DECISION: Add agent parameter

**Documentation Changes:**
- FR6: Update all 16 tool signatures in docs/references/Scribe_Usage.md with `agent: str`
- FR7: Update all tool usage examples in Scribe_Usage.md to include agent parameter
- FR8: Update SCRIBE_PROTOCOL.md and SCRIBE_MCP_GUIDE.md with agent parameter examples
- FR9: Update all 5 agent instruction files (.claude/agents/*.md) with agent parameter in tool calls
- FR10: Update scribe_mcp/CLAUDE.md and MCP_SPINE/CLAUDE.md with agent parameter examples

**Non-Functional Requirements:**
- NFR1: Zero breaking changes to tools that already have correct agent: str parameter
- NFR2: All changes must pass existing test suites
- NFR3: Implementation must be completable in single phase
- NFR4: Parameter position must match established patterns (set_project as reference)

**Assumptions:**
- Server.py enforcement at line 355 is final and will not be reverted
- All tools are invoked through the same server.py call handler
- Diagnostic tools will require special consideration (exception or parameter addition)
- Tests exist for all tools and will catch signature mismatches

**Risks & Mitigations:**
- **Risk**: Diagnostic tools (health_check, doctor) have zero parameters - adding agent breaks their "parameterless" design
  - **Mitigation Option 1**: Add agent: str parameter to both (consistent but changes semantic)
  - **Mitigation Option 2**: Create exception list in server.py for diagnostic tools
  - **DECISION REQUIRED**: Which approach maintains better system consistency?
  
- **Risk**: Tools with many parameters may have agent buried deep in signature
  - **Mitigation**: Enforce "agent after primary ID" rule - keeps it visible and consistent
  
- **Risk**: Breaking changes for any existing callers
  - **Mitigation**: Since server.py already enforces REQUIRED, any existing working code must be passing agent already - changes are internal only
<!-- ID: architecture_overview -->
**Solution Summary:** 
Systematically update all 14 non-compliant tools to include `agent: str` parameter positioned immediately after their primary identifier parameter. This creates universal compliance with server.py enforcement while maintaining API consistency.

**Design Decision - Diagnostic Tools:**
After analysis, **RECOMMEND Option 1**: Add `agent: str` parameter to health_check and scribe_doctor.

**Rationale:**
- ✅ Maintains universal pattern (all tools have agent parameter - zero exceptions)
- ✅ Enables audit trail for diagnostic tool invocations
- ✅ Avoids special-case logic in server.py
- ✅ Diagnostic value: knowing which agent ran health checks is useful debugging info
- ❌ Minor semantic change (tools no longer "parameterless") - acceptable trade-off

**Component Breakdown:**

1. **Category A: Optional → REQUIRED (4 tools)**
   - Tools: append_entry.py, read_file.py, query_entries.py, sentinel_tools.py::append_event
   - Change: Remove `Optional[str] = None`, make `agent: str` REQUIRED
   - Position: Verify agent positioned after primary identifier (already correct in most)

2. **Category B: Add agent parameter (9 tools)**
   - Tools: manage_docs.py, get_project.py, list_projects.py, read_recent.py, rotate_log.py, generate_doc_templates.py
   - Sentinel: open_bug, open_security, link_fix
   - Change: Add `agent: str` parameter after primary identifier
   - Position pattern:
     - manage_docs: `action, agent, doc_category, ...`
     - get_project: `agent, project=None, ...` (no primary ID, agent comes first)
     - list_projects: `agent, limit=5, ...` (no primary ID, agent comes first)
     - read_recent: `agent, project=None, ...` (no primary ID, agent comes first)
     - rotate_log: `agent, project=None, ...` (no primary ID, agent comes first)
     - generate_doc_templates: `project_name, agent, author=None, ...`
     - open_bug: `title, agent, symptoms, ...`
     - open_security: `title, agent, symptoms, ...`
     - link_fix: `case_id, agent, execution_id, ...`

3. **Category C: Rename parameter (1 tool)**
   - Tool: delete_project.py
   - Change: Rename `agent_id` → `agent`
   - Position: After `name` and `root` (currently at end, move forward)
   - New signature: `name: str, root: str, agent: str, mode="archive", ...`

4. **Category D: Diagnostic tools (2 tools)**
   - Tools: health_check.py, scribe_doctor.py
   - Change: Add `agent: str` as ONLY parameter
   - New signatures: `health_check(agent: str)`, `scribe_doctor(agent: str)`

**Data Flow:**
1. Client calls tool via MCP protocol
2. Server.py call handler extracts `agent` from arguments (line 353)
3. If missing → ValueError raised (line 355)
4. If present → tool executes with agent parameter for tracking/audit

**External Integrations:** 
None - this is purely internal parameter signature standardization
<!-- ID: detailed_design -->
### Implementation Specifications by Category

#### Category A: Optional → REQUIRED (4 tools)

**1. append_entry.py**
- Current: `agent: Optional[str] = None` at line ~1245
- Target: `agent: str` (remove Optional, remove default)
- Position: After `emoji` parameter (currently correct)
- Additional: Has `agent_id` parameter at line 1253 - KEEP for backward compat, but make agent the primary

**2. read_file.py**
- Research doc says has agent somewhere - need to verify current state
- Target: `agent: str` REQUIRED
- Position: After `path` parameter
- Impact: High-frequency tool - ensure all call sites updated

**3. query_entries.py**
- Current: `agent: Optional[Any]` at line ~1002
- Target: `agent: str` (proper typing, remove Optional)
- Position: Currently correct position
- Note: Has `agents` (plural) parameter for filtering - keep both

**4. sentinel_tools.py::append_event**
- Current: `agent: Optional[str] = None`
- Target: `agent: str` (remove Optional, remove default)
- Position: After `emoji` parameter
- Note: This is a wrapper around append_entry

#### Category B: Add agent parameter (9 tools)

**5. manage_docs.py**
- Current: NO agent parameter
- Target: Add `agent: str` after `action` parameter
- New signature: `async def manage_docs(action: str, agent: str, doc_category: str = "", ...)`
- Impact: Core documentation tool - high usage

**6. get_project.py**
- Current: NO agent parameter
- Target: Add `agent: str` as FIRST parameter (no primary ID)
- New signature: `async def get_project(agent: str, project=None, format="structured", verbose=False)`
- Impact: Medium usage

**7. list_projects.py**
- Current: NO agent parameter
- Target: Add `agent: str` as FIRST parameter
- New signature: `async def list_projects(agent: str, limit=5, filter=None, ...)`
- Impact: Medium usage

**8. read_recent.py**
- Current: NO agent parameter
- Target: Add `agent: str` as FIRST parameter
- New signature: `async def read_recent(agent: str, project=None, n=None, limit=None, ...)`
- Impact: High usage

**9. rotate_log.py**
- Current: NO agent parameter
- Target: Add `agent: str` as FIRST parameter
- New signature: `async def rotate_log(agent: str, project=None, suffix=None, ...)`
- Impact: Low usage

**10. generate_doc_templates.py**
- Current: NO agent parameter
- Target: Add `agent: str` after `project_name`
- New signature: `async def generate_doc_templates(project_name: str, agent: str, author=None, ...)`
- Impact: Medium usage

**11-13. sentinel_tools.py: open_bug, open_security, link_fix**
- open_bug: `async def open_bug(title: str, agent: str, symptoms: str, affected_paths=None)`
- open_security: `async def open_security(title: str, agent: str, symptoms: str, affected_paths=None)`
- link_fix: `async def link_fix(case_id: str, agent: str, execution_id: str, artifact_ref: str, landing_status: str)`
- Impact: Low usage, bug tracking tools

#### Category C: Rename parameter (1 tool)

**14. delete_project.py**
- Current: `agent_id: Optional[str] = None` (at end of signature)
- Target: `agent: str` REQUIRED, moved forward
- New signature: `async def delete_project(name: str, root: str, agent: str, mode="archive", confirm: bool, ...)`
- Impact: Low usage, destructive operation

#### Category D: Diagnostic tools (2 tools)

**15. health_check.py**
- Current: `async def health_check()` (zero parameters)
- Target: `async def health_check(agent: str)`
- Impact: Low usage, diagnostic tool

**16. scribe_doctor.py**
- Current: `async def scribe_doctor()` (zero parameters)
- Target: `async def scribe_doctor(agent: str)`
- Impact: Low usage, diagnostic tool

### Implementation Notes

**Type Annotations:**
- All agent parameters use `agent: str` (not Optional, not Any)
- No default values (REQUIRED parameter)
- Proper typing for clarity and IDE support

**Backward Compatibility:**
- append_entry keeps `agent_id` parameter for backward compat (internal)
- Server.py already enforces agent REQUIRED, so no external code can be calling without it
- This is purely internal signature standardization

**Error Handling:**
- No changes needed - server.py handles missing agent at line 355
- Tools don't need to validate agent parameter (server guarantees it's present)
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/docs/dev_plans/agent_param_audit
```
> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.


---
## 6. Data & Storage
<!-- ID: data_storage -->
- **Datastores:** ['Filesystem markdown', 'SQLite mirror']
- **Indexes & Performance:** FTS for sections
- **Migrations:** Sequential migrations tracked in storage layer


---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
- **Unit Tests:** Template rendering + doc ops
- **Integration Tests:** manage_docs tool exercises real files
- **Manual QA:** Project review after each release
- **Observability:** Structured logging via doc_updates log


---
## 8. Deployment & Operations
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should templates support conditionals per phase? | Docs Lead | TODO | Evaluate after initial rollout. |
Close each question once answered and reference the relevant section above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->
- PROGRESS_LOG.md- ARCHITECTURE_GUIDE.md
Generated via generate_doc_templates.


---