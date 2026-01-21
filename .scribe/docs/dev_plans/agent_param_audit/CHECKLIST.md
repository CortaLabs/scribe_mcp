---
id: agent_param_audit-checklist
title: "\u2705 Acceptance Checklist \u2014 agent_param_audit"
doc_name: CHECKLIST
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

# ✅ Acceptance Checklist — agent_param_audit
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-01-20 05:45:28 UTC

> Acceptance checklist for agent_param_audit.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [ ] **Architecture Guide Complete** - All sections filled, design decisions documented (proof: ARCHITECTURE_GUIDE.md exists and complete)
- [ ] **Phase Plan Complete** - All 3 phases defined with task packages (proof: PHASE_PLAN.md exists and complete)
- [ ] **Research Document Reviewed** - RESEARCH_AGENT_PARAM_AUDIT_20260120.md read and findings verified (proof: logged in progress)
- [ ] **Baseline Tests Pass** - All existing tests pass before changes (proof: `pytest tests/` exit code 0)
- [ ] **Feature Branch Created** - Branch `feat/agent-param-standardization` exists (proof: `git branch` shows it)
<!-- ID: phase_0 -->
- [ ] **Baseline Test Results** - All tests pass with 0 exit code (proof: pytest output log)
- [ ] **Feature Branch Created** - Branch created and checked out (proof: `git branch` output)
- [ ] **Server Enforcement Verified** - Confirmed line 355 in server.py has ValueError enforcement (proof: read_file output)
- [ ] **Current State Documented** - Logged which tools work/fail currently (proof: progress log entry)
- [ ] **Test Harness Created** - Created test script for agent parameter validation (proof: test file exists)

**Phase 1 Complete When:** All 5 items checked with proof attached
---
## Phase 2: Implementation
<!-- ID: phase_2 -->

### Task Package 1: Category A - Optional → REQUIRED
- [ ] **append_entry.py Updated** - Changed `agent: Optional[str] = None` to `agent: str` (proof: git diff)
- [ ] **query_entries.py Updated** - Changed `agent: Optional[Any]` to `agent: str` (proof: git diff)
- [ ] **read_file.py Updated** - Made agent parameter REQUIRED (proof: git diff)
- [ ] **sentinel append_event Updated** - Changed to `agent: str` REQUIRED (proof: git diff)
- [ ] **Package 1 Tests Pass** - All tests for these 4 tools pass (proof: pytest output)

### Task Package 2: Category B Part 1 - Core Tools
- [ ] **manage_docs.py Updated** - Added `agent: str` after `action` parameter (proof: git diff shows new signature)
- [ ] **get_project.py Updated** - Added `agent: str` as first parameter (proof: git diff)
- [ ] **list_projects.py Updated** - Added `agent: str` as first parameter (proof: git diff)
- [ ] **read_recent.py Updated** - Added `agent: str` as first parameter (proof: git diff)
- [ ] **rotate_log.py Updated** - Added `agent: str` as first parameter (proof: git diff)
- [ ] **generate_doc_templates.py Updated** - Added `agent: str` after `project_name` (proof: git diff)
- [ ] **Package 2 Tests Pass** - All tests pass (proof: pytest output)

### Task Package 3: Category B Part 2 - Sentinel Tools
- [ ] **open_bug Updated** - Added `agent: str` after `title` parameter (proof: git diff)
- [ ] **open_security Updated** - Added `agent: str` after `title` parameter (proof: git diff)
- [ ] **link_fix Updated** - Added `agent: str` after `case_id` parameter (proof: git diff)
- [ ] **Package 3 Tests Pass** - Sentinel tests pass (proof: pytest output)

### Task Package 4: Category C - Rename
- [ ] **delete_project.py Renamed** - Changed `agent_id` to `agent` (proof: git diff)
- [ ] **delete_project.py Repositioned** - Moved agent to 3rd position after `root` (proof: signature inspection)
- [ ] **delete_project.py Internal References** - All internal uses of agent_id updated to agent (proof: grep shows no agent_id references)
- [ ] **Package 4 Tests Pass** - delete_project tests pass (proof: pytest output)

### Task Package 5: Category D - Diagnostic Tools
- [ ] **health_check.py Updated** - Added `agent: str` as only parameter (proof: git diff)
- [ ] **scribe_doctor Updated** - Added `agent: str` as only parameter (proof: git diff)
- [ ] **Package 5 Tests Pass** - Diagnostic tool tests pass (proof: pytest output)
- [ ] **Manual Test** - Called health_check(agent="Test") and scribe_doctor(agent="Test") successfully (proof: logged output)

### Phase 2 Completion Gates
- [ ] **All 16 Tools Updated** - Git diff shows changes to all 16 tools (proof: `git diff --stat`)
- [ ] **All Tests Pass** - `pytest tests/` returns exit code 0 (proof: full pytest output)
- [ ] **No Import Errors** - All tools import successfully (proof: Python import test script)
- [ ] **Signature Verification** - Script confirms all tools have agent: str parameter (proof: signature inspection script output)

**Phase 2 Complete When:** All 5 task packages verified AND all 4 completion gates pass

---
## Phase 3: Documentation Updates
<!-- ID: phase_3_docs -->

- [ ] **Scribe_Usage.md: Tool Signatures** - All 16 tool signatures updated with `agent: str` (proof: grep verification)
- [ ] **Scribe_Usage.md: Examples** - All tool usage examples include agent parameter (proof: manual review count)
- [ ] **Scribe_Usage.md: Parameter Tables** - Parameter tables reflect new positioning (proof: visual inspection)
- [ ] **SCRIBE_PROTOCOL.md: Examples** - All tool call examples updated (proof: grep/manual review)
- [ ] **SCRIBE_MCP_GUIDE.md: Tool Reference** - Tool reference sections updated (proof: grep/manual review)
- [ ] **SCRIBE_MCP_GUIDE.md: Diagrams** - Architecture diagrams showing tool signatures updated (proof: visual inspection)
- [ ] **Documentation Consistency** - No contradictory signatures remain (proof: cross-reference check)

**Phase 3 Complete When:** All 7 documentation verification items pass with proof

---
## Phase 4: Agent Instruction Updates
<!-- ID: phase_4 -->

- [ ] **scribe-bug-hunter.md** - All tool calls include `agent="BugHunterAgent"` (proof: grep shows all tool calls have agent param)
- [ ] **scribe-research-analyst.md** - All tool calls include `agent="ResearchAgent"` (proof: grep verification)
- [ ] **scribe-architect.md** - All tool calls include `agent="ArchitectAgent"` (proof: grep verification)
- [ ] **scribe-review-agent.md** - All tool calls include `agent="ReviewAgent"` (proof: grep verification)
- [ ] **scribe-coder.md** - All tool calls include `agent="CoderAgent"` (proof: grep verification)
- [ ] **Agent Names Consistent** - Each file uses correct agent name throughout (proof: manual review)
- [ ] **No Missing Parameters** - No tool calls lacking agent parameter (proof: manual review of all 5 files)

**Phase 4 Complete When:** All 7 agent file verification items pass with proof

---
## Phase 5: CLAUDE.md Updates
<!-- ID: phase_5 -->

- [ ] **scribe_mcp/CLAUDE.md: Tool Examples** - All tool examples include agent parameter (proof: grep/manual review)
- [ ] **scribe_mcp/CLAUDE.md: Logging Quick Reference** - Logging examples updated with agent parameter (proof: visual inspection)
- [ ] **scribe_mcp/CLAUDE.md: manage_docs Examples** - manage_docs examples include agent parameter (proof: code block review)
- [ ] **MCP_SPINE/CLAUDE.md: Logging Examples** - Root CLAUDE.md logging examples updated (proof: grep/manual review)
- [ ] **MCP_SPINE/CLAUDE.md: Commandments** - Tool call examples in commandments updated (proof: manual review)
- [ ] **Consistency Check** - Both CLAUDE.md files consistent with Phase 3 docs (proof: signature comparison)
- [ ] **Orchestrator Context** - Examples use `agent="Orchestrator"` consistently (proof: grep verification)

**Phase 5 Complete When:** All 7 CLAUDE.md verification items pass with proof

---
## Phase 6: Validation & Integration
<!-- ID: phase_6 -->

- [ ] **Full Test Suite Pass** - All tests pass with exit code 0 (proof: `pytest tests/` output)
- [ ] **Server Enforcement Test** - Verified ValueError raised when agent missing (proof: test output showing expected error)
- [ ] **Server Acceptance Test** - Verified all tools work when agent provided (proof: integration test log)
- [ ] **MCP Protocol Integration Test** - All 16 tools invoked via MCP protocol successfully (proof: MCP client test log)
- [ ] **Diagnostic Tools Manual Test** - health_check(agent="Test") works (proof: command output)
- [ ] **Diagnostic Tools Manual Test** - scribe_doctor(agent="Test") works (proof: command output)
- [ ] **Edge Cases Documented** - Any issues discovered logged (proof: progress log entries)
- [ ] **No Import Errors** - Final verification all tools import cleanly (proof: import test script)

**Phase 6 Complete When:** All 8 verification items pass with proof attached

---
<!-- ID: final_verification -->
## Final Verification

- [ ] **All Phase 1 Items Complete** - Pre-flight validation passed (proof: checklist above)
- [ ] **All Phase 2 Items Complete** - Implementation complete (proof: checklist above)
- [ ] **All Phase 3 Items Complete** - Documentation updates complete (proof: checklist above)
- [ ] **All Phase 4 Items Complete** - Agent instructions updated (proof: checklist above)
- [ ] **All Phase 5 Items Complete** - CLAUDE.md files updated (proof: checklist above)
- [ ] **All Phase 6 Items Complete** - Validation passed (proof: checklist above)
- [ ] **Code Review Requested** - Review Agent assigned (proof: review request logged)
- [ ] **Review Grade ≥93%** - Passed quality gate (proof: review agent output)
- [ ] **Documentation Updated** - CLAUDE.md, AGENTS.md reflect any necessary changes (proof: git diff)
- [ ] **Merge to Master** - PR merged (proof: git log shows merge commit)
- [ ] **Stakeholder Sign-off** - Architect and Review agents approve (proof: names + dates below)

**Architect Sign-off:** ArchitectAgent - [Date pending]
**Review Sign-off:** [Pending review]

**Project Complete When:** All items checked AND merge to master complete
