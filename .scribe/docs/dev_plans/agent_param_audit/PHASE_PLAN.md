---
id: agent_param_audit-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 agent_param_audit"
doc_name: PHASE_PLAN
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

# ⚙️ Phase Plan — agent_param_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-20 05:45:28 UTC

> Execution roadmap for agent_param_audit.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 1 — Pre-flight Validation | Verify current state, create safety measures | Current state audit, test baseline, safety branch | 0.95 |
| Phase 2 — Implementation | Update all 16 tools with agent parameter | 16 tools updated, all tests passing | 0.90 |
| Phase 3 — Documentation Updates | Update reference docs with new signatures | Scribe_Usage.md, SCRIBE_PROTOCOL.md, SCRIBE_MCP_GUIDE.md updated | 0.95 |
| Phase 4 — Agent Instruction Updates | Update agent prompt files with agent parameter | All 5 agent instruction files updated | 0.95 |
| Phase 5 — CLAUDE.md Updates | Update orchestration guides | Root and scribe_mcp CLAUDE.md updated | 0.95 |
| Phase 6 — Validation & Integration | Verify server.py enforcement works | Integration tests pass, zero ValueError exceptions | 0.95 |

**Implementation Strategy:** Single atomic phase approach - all tools updated together to avoid partial broken state.

**Risk Mitigation:** Pre-flight phase establishes baseline, safety branch allows rollback if issues discovered.
<!-- ID: phase_0 -->
**Objective:** Establish baseline and safety measures before making changes

**Key Tasks:**
1. Run full test suite to establish baseline (all tests must pass)
2. Create feature branch: `feat/agent-param-standardization`
3. Verify server.py enforcement is active (line 355 check)
4. Document which tools currently work/fail with enforcement
5. Create test harness for agent parameter validation

**Deliverables:**
- Baseline test results (all green)
- Feature branch created
- Current state documentation (which tools work/fail)
- Test harness for validation

**Acceptance Criteria:**
- [ ] All existing tests pass (pytest returns 0 exit code)
- [ ] Feature branch created and checked out
- [ ] Current state documented in progress log
- [ ] Test harness created for agent parameter validation

**Dependencies:** None (first phase)

**Estimated Duration:** 1-2 hours

**Notes:** This phase is critical - establishes known-good baseline before changes.
<!-- ID: phase_1 -->
**Objective:** Update all 16 tools with standardized agent parameter

**Implementation Order:**
Tools are updated in dependency order to minimize breakage:

### Task Package 1: Category A - Optional → REQUIRED (4 tools)
**Scope:** Update tools that already have agent parameter but it's Optional
**Files:** 
- tools/append_entry.py (line ~1245)
- tools/query_entries.py (line ~1002)  
- tools/read_file.py (verify current state first)
- tools/sentinel_tools.py (append_event function)

**Specifications:**
1. Change `agent: Optional[str] = None` → `agent: str`
2. Remove any default values
3. Keep parameter position (already correct)
4. Update docstrings to reflect REQUIRED status

**Verification:**
- [ ] Parameter signatures updated (no Optional, no default)
- [ ] All four tools import and load without errors
- [ ] Run `pytest tests/test_append_entry.py` - passes
- [ ] Run `pytest tests/test_query_entries.py` - passes

**Estimated Duration:** 30-45 minutes

---

### Task Package 2: Category B Part 1 - Core Tools (6 tools)
**Scope:** Add agent parameter to high-impact core tools
**Files:**
- tools/manage_docs.py → `action, agent, doc_category, ...`
- tools/get_project.py → `agent, project=None, ...`
- tools/list_projects.py → `agent, limit=5, ...`
- tools/read_recent.py → `agent, project=None, ...`
- tools/rotate_log.py → `agent, project=None, ...`
- tools/generate_doc_templates.py → `project_name, agent, author=None, ...`

**Specifications:**
1. Add `agent: str` parameter at specified position
2. Update internal logic if tool uses agent for tracking
3. Update docstrings with parameter description
4. No changes to return types or other parameters

**Verification:**
- [ ] All six tools import and load without errors
- [ ] manage_docs can be called with agent parameter
- [ ] Run `pytest tests/` - all tests pass
- [ ] Manual test: call each tool with agent="TestAgent"

**Estimated Duration:** 1-1.5 hours

---

### Task Package 3: Category B Part 2 - Sentinel Tools (3 tools)
**Scope:** Add agent parameter to bug tracking/sentinel tools
**Files:**
- tools/sentinel_tools.py (open_bug, open_security, link_fix)

**Specifications:**
- open_bug: `title, agent, symptoms, ...`
- open_security: `title, agent, symptoms, ...`  
- link_fix: `case_id, agent, execution_id, ...`

**Verification:**
- [ ] All three functions updated
- [ ] Sentinel tools import without errors
- [ ] Run `pytest tests/test_sentinel*.py` - passes

**Estimated Duration:** 20-30 minutes

---

### Task Package 4: Category C - Rename (1 tool)
**Scope:** Rename agent_id → agent in delete_project
**Files:**
- tools/delete_project.py

**Specifications:**
1. Rename parameter: `agent_id` → `agent`
2. Move position: end of signature → after `root`
3. New signature: `name: str, root: str, agent: str, mode="archive", confirm: bool, ...`
4. Update all internal references from agent_id to agent
5. Update docstring

**Verification:**
- [ ] Parameter renamed throughout file
- [ ] Tool imports without errors
- [ ] Run `pytest tests/test_delete_project.py` - passes

**Estimated Duration:** 15-20 minutes

---

### Task Package 5: Category D - Diagnostic Tools (2 tools)
**Scope:** Add agent parameter to parameterless diagnostic tools
**Files:**
- tools/health_check.py
- tools/doctor.py (scribe_doctor function)

**Specifications:**
1. Add `agent: str` as ONLY parameter
2. Update internal logic to accept but possibly ignore agent
3. Update docstrings

**Verification:**
- [ ] Both tools accept agent parameter
- [ ] Tools import without errors
- [ ] Run `pytest tests/test_health*.py tests/test_doctor.py` - passes
- [ ] Manual test: health_check(agent="TestAgent") works

**Estimated Duration:** 15-20 minutes

---

**Phase 2 Deliverables:**
- All 16 tools updated with agent: str parameter
- All test suites passing
- Zero import errors

**Phase 2 Acceptance Criteria:**
- [ ] All 16 tools updated per specifications
- [ ] `pytest tests/` returns 0 exit code (all pass)
- [ ] No import errors when loading tools
- [ ] Manual smoke test of each tool works

**Dependencies:** Phase 1 (baseline established)

**Total Estimated Duration:** 3-4 hours

**Notes:** If any task package fails tests, STOP and fix before proceeding to next package. Incremental validation prevents cascading failures.
---

## Phase 3 — Documentation Updates
<!-- ID: phase_3_docs -->

**Objective:** Update all reference documentation to reflect new agent parameter requirement

**Scope:** Update canonical reference documents that developers and agents consult for tool usage

**Files to Update:**
1. `docs/references/Scribe_Usage.md` - Master tool reference (all 16 tool signatures + examples)
2. `docs/references/SCRIBE_PROTOCOL.md` - Protocol documentation
3. `docs/references/SCRIBE_MCP_GUIDE.md` - MCP guide documentation

**Key Tasks:**

1. **Update Scribe_Usage.md**
   - Update all 16 tool signatures to show `agent: str` as required parameter
   - Update all tool usage examples to include `agent` parameter
   - Update parameter tables to reflect new positioning
   - Verify all code examples are syntactically correct with agent parameter

2. **Update SCRIBE_PROTOCOL.md**
   - Update any tool call examples in protocol documentation
   - Ensure workflow examples include agent parameter
   - Update agent responsibility sections if needed

3. **Update SCRIBE_MCP_GUIDE.md**
   - Update tool reference sections
   - Update any architecture diagrams showing tool signatures
   - Update integration examples

**Deliverables:**
- All tool signatures in docs/references/ updated with `agent: str`
- All tool usage examples include agent parameter
- No outdated examples remain in reference docs

**Acceptance Criteria:**
- [ ] Scribe_Usage.md: All 16 tool signatures updated (proof: grep shows agent: str for all tools)
- [ ] Scribe_Usage.md: All tool examples include agent parameter (proof: manual review)
- [ ] SCRIBE_PROTOCOL.md: All tool examples updated (proof: grep/manual review)
- [ ] SCRIBE_MCP_GUIDE.md: All tool examples updated (proof: grep/manual review)
- [ ] Documentation is internally consistent (proof: no contradictory signatures)

**Dependencies:** Phase 2 (implementation complete)

**Estimated Duration:** 1-1.5 hours

**Notes:** This phase ensures developers and agents have accurate reference documentation. Missing this phase would cause confusion between code reality and documentation.

---

## Phase 4 — Agent Instruction Updates
<!-- ID: phase_4 -->

**Objective:** Update agent prompt files to reflect mandatory agent parameter in all tool calls

**Scope:** Update all agent instruction files that contain tool usage examples

**Files to Update:**
1. `.claude/agents/scribe-bug-hunter.md`
2. `.claude/agents/scribe-research-analyst.md`
3. `.claude/agents/scribe-architect.md`
4. `.claude/agents/scribe-review-agent.md`
5. `.claude/agents/scribe-coder.md`

**Key Tasks:**

1. **For each agent file:**
   - Identify all tool call examples in the file
   - Update each tool call to include `agent` parameter with appropriate agent name
   - Ensure agent parameter is positioned correctly per tool specifications
   - Update any quick reference tables or parameter lists

2. **Agent-specific updates:**
   - Bug Hunter: `agent="BugHunterAgent"`
   - Research Agent: `agent="ResearchAgent"`
   - Architect Agent: `agent="ArchitectAgent"`
   - Review Agent: `agent="ReviewAgent"`
   - Coder Agent: `agent="CoderAgent"`

3. **Verify consistency:**
   - All tool calls in each file use correct agent name for that agent
   - No outdated examples without agent parameter remain
   - Examples match Phase 3 documentation updates

**Deliverables:**
- All 5 agent instruction files updated
- All tool call examples include agent parameter
- Agent names are consistent throughout each file

**Acceptance Criteria:**
- [ ] scribe-bug-hunter.md: All tool calls include `agent="BugHunterAgent"` (proof: grep verification)
- [ ] scribe-research-analyst.md: All tool calls include `agent="ResearchAgent"` (proof: grep verification)
- [ ] scribe-architect.md: All tool calls include `agent="ArchitectAgent"` (proof: grep verification)
- [ ] scribe-review-agent.md: All tool calls include `agent="ReviewAgent"` (proof: grep verification)
- [ ] scribe-coder.md: All tool calls include `agent="CoderAgent"` (proof: grep verification)
- [ ] No tool calls missing agent parameter in any file (proof: manual review)

**Dependencies:** Phase 3 (documentation updated)

**Estimated Duration:** 1-1.5 hours

**Notes:** This phase ensures agents have correct instruction on how to use tools. Agents will fail with ValueError if they follow outdated instructions missing agent parameter.

---

## Phase 5 — CLAUDE.md Updates
<!-- ID: phase_5 -->

**Objective:** Update orchestration guide files with agent parameter examples

**Scope:** Update CLAUDE.md files that contain tool usage examples for orchestrator guidance

**Files to Update:**
1. `scribe_mcp/CLAUDE.md` - Scribe MCP operational guidance
2. `MCP_SPINE/CLAUDE.md` - Root orchestration guide

**Key Tasks:**

1. **Update scribe_mcp/CLAUDE.md**
   - Update tool usage quick reference section
   - Update logging examples to include agent parameter
   - Update manage_docs examples
   - Update any operational checklist tool calls

2. **Update MCP_SPINE/CLAUDE.md**
   - Update logging quick reference examples
   - Update any tool call examples in commandments
   - Ensure consistency with scribe_mcp/CLAUDE.md

3. **Verify orchestrator context:**
   - Examples use `agent="Orchestrator"` consistently
   - Subagent dispatch instructions mention agent parameter requirement
   - Integration examples are complete and correct

**Deliverables:**
- Both CLAUDE.md files updated with agent parameter
- All tool examples include agent parameter
- Orchestrator guidance is clear on agent parameter requirement

**Acceptance Criteria:**
- [ ] scribe_mcp/CLAUDE.md: All tool examples include agent parameter (proof: grep/manual review)
- [ ] scribe_mcp/CLAUDE.md: Logging quick reference updated (proof: visual inspection)
- [ ] MCP_SPINE/CLAUDE.md: All tool examples include agent parameter (proof: grep/manual review)
- [ ] Both files consistent with Phase 3 documentation (proof: signature comparison)
- [ ] No outdated examples remain (proof: manual review)

**Dependencies:** Phase 4 (agent instructions updated)

**Estimated Duration:** 45 minutes - 1 hour

**Notes:** This phase ensures the orchestrator (Claude Code) has correct guidance. CLAUDE.md is read at the start of each session, so outdated examples would train incorrect behavior.

---

## Phase 6 — Validation & Integration
<!-- ID: phase_6 -->

**Objective:** Verify server.py enforcement works correctly with all updated tools

**Key Tasks:**
1. Run full test suite (all tests must pass)
2. Test server.py enforcement - verify ValueError raised when agent missing
3. Test server.py acceptance - verify tools work when agent provided
4. Integration test: run MCP server and invoke each tool via MCP protocol
5. Manual verification of diagnostic tools (health_check, scribe_doctor)
6. Document any edge cases discovered

**Deliverables:**
- Full test suite passing (pytest exit code 0)
- Integration test results documented
- Edge cases (if any) documented in progress log
- Final verification report

**Acceptance Criteria:**
- [ ] `pytest tests/` returns 0 exit code (100% pass rate)
- [ ] Manual MCP protocol test - all 16 tools work with agent parameter
- [ ] Server.py enforcement test - ValueError raised when agent missing (expected)
- [ ] No import errors across entire codebase
- [ ] health_check(agent="Test") and scribe_doctor(agent="Test") both work
- [ ] Integration test with real MCP client passes

**Dependencies:** Phase 5 (CLAUDE.md updated)

**Estimated Duration:** 1-2 hours

**Notes:** This phase ensures the implementation actually works in production conditions, not just unit tests.

<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Pre-flight Complete | Day 1 | Coder Agent | ⏳ Planned | Phase 1 tasks |
| Implementation Complete | Day 1-2 | Coder Agent | ⏳ Planned | Phase 2 tasks (all 5 packages) |
| Documentation Complete | Day 2 | Coder Agent | ⏳ Planned | Phases 3-5 tasks |
| Validation Complete | Day 2-3 | Coder Agent | ⏳ Planned | Phase 6 tasks |
| Merge to Master | Day 3 | Review Agent | ⏳ Planned | After ≥93% review score |

**Critical Path:** Phase 1 → Phase 2 (all packages) → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Review → Merge

Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.


---