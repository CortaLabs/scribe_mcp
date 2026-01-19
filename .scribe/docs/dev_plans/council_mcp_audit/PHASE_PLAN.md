---
id: council_mcp_audit-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 council_mcp_audit"
doc_name: PHASE_PLAN
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-13'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — council_mcp_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-13 02:21:25 UTC

> Execution roadmap for council_mcp_audit.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Goal | Key Deliverables | Agent | Priority | Confidence |
|-------|------|------------------|-------|----------|------------|
| Phase 1 | Configuration Audit | Config validation report, zero hardcoded values | Sentinel | HIGH | 0.95 |
| Phase 2 | Tool Functionality Audit | 22 tools verified, policy enforcement confirmed | Crucible + Mantis | HIGH | 0.90 |
| Phase 3 | Scribe Integration Audit | Bridge relay verified, session tracking confirmed | Atlas | MEDIUM | 0.85 |
| Phase 4 | Agent Template Audit | All 9 agents updated with Council MCP guidance | Forge | MEDIUM | 0.90 |
| Phase 5 | Web UI Architecture | API surface design, component architecture spec | Blueprint | LOW | 0.80 |
| Phase 6 | Final Review | AUDIT_REPORT.md, all findings compiled | Arbiter | HIGH | 0.95 |

**Execution Order:** 1 -> 2 -> (3,4 parallel) -> 5 -> 6
**Blocking Dependencies:** Phase 6 requires all other phases complete
<!-- ID: phase_0 -->
## Phase 1 - Configuration Audit
<!-- ID: phase_0 -->

**Objective:** Verify all configuration loads from `.council/council.yaml` with no hardcoded values in code.

**Assigned Agent:** Sentinel (Security Specialist)

**Key Tasks:**
1. **Task 1.1:** Static analysis - grep codebase for hardcoded model names, timeouts, limits
2. **Task 1.2:** Verify YAML loading - confirm all 11 config sections load correctly
3. **Task 1.3:** Test environment overrides - verify `COUNCIL_<SECTION>__<KEY>` pattern works
4. **Task 1.4:** Document all config options with types and defaults

**Deliverables:**
- Config validation report listing any hardcoded values found
- Environment override test results
- Complete config schema documentation

**Acceptance Criteria:**
- [ ] Zero hardcoded config values in `council_mcp/` code (proof: grep results)
- [ ] All 11 config sections verified loadable (proof: test output)
- [ ] Environment overrides work for all sections (proof: test output)

**Dependencies:** None (first phase)

**Notes:** Focus on `council_mcp/config.py` (257 lines) and all files that import config values.
<!-- ID: phase_1 -->
## Phase 2 - Tool Functionality Audit
<!-- ID: phase_1 -->

**Objective:** Verify all 22 MCP tools function correctly with proper policy enforcement and error handling.

**Assigned Agents:** Crucible (Testing) + Mantis (Debugging)

**Key Tasks:**
1. **Task 2.1:** Test all 22 tools with valid inputs (happy path)
2. **Task 2.2:** Test all tools with invalid inputs (error handling)
3. **Task 2.3:** Verify policy enforcement (require_project_id, require_open_session, require_profile)
4. **Task 2.4:** Test tool chains (open_session -> store_memory -> ask_self -> end_session)

**Tool Groups to Test:**

| Group | Tools | Count |
|-------|-------|-------|
| Sessions | open_session, end_session, list_active_sessions, close_stale_sessions | 4 |
| Profiles | register_profile, get_profile, list_profiles | 3 |
| Memory | store_memory, query_memories, reinforce_memory | 3 |
| Ask | ask_self, ask_agent, ask_council | 3 |
| Messages | record_message, list_messages, mark_read, list_urgent_messages | 4 |
| Reflection | run_reflection, run_dream_cycle, mine_patterns | 3 |
| Utility | log_audit, promote_message | 2 |
| **Total** | | **22** |

**Deliverables:**
- Tool verification matrix (pass/fail for each tool)
- Policy enforcement test results
- Error handling documentation

**Acceptance Criteria:**
- [ ] All 22 tools pass functional verification (proof: test output)
- [ ] Policy decorators correctly block unauthorized access (proof: error logs)
- [ ] Error responses are informative and actionable (proof: error samples)

**Dependencies:** Phase 1 (config must be verified before testing tools)

**Notes:** Use existing test suite (`tests/test_phase3_*.py`, `tests/test_phase4_*.py`) as baseline.
<!-- ID: milestone_tracking -->
## Phase 3 - Scribe Integration Audit
<!-- ID: milestone_tracking -->

**Objective:** Verify ScribeBridge correctly relays audit entries to Scribe MCP without blocking Council operations.

**Assigned Agent:** Atlas (Coordinator)

**Key Tasks:**
1. **Task 3.1:** Test bridge lifecycle - on_activate/on_deactivate hooks
2. **Task 3.2:** Verify session-to-project mapping via SessionTracker
3. **Task 3.3:** Test audit relay - confirm log_audit entries appear in Scribe progress log
4. **Task 3.4:** Verify fire-and-forget behavior - Scribe failures don't block Council

**Bridge Components:**
- `ScribeBridge` - Main lifecycle hooks
- `SessionTracker` - workspace -> project mapping
- `AuditRelay` - Council audit -> Scribe append_entry transformation

**Deliverables:**
- Bridge lifecycle verification report
- Relay test results (Council action -> Scribe log entry)
- Failure handling documentation

**Acceptance Criteria:**
- [ ] Bridge activates/deactivates cleanly (proof: lifecycle logs)
- [ ] Session tracking correctly maps workspace to project (proof: mapping tests)
- [ ] Audit entries appear in Scribe progress log (proof: log inspection)
- [ ] Scribe failures are logged but don't block Council (proof: failure injection test)

**Dependencies:** Phase 2 (tools must work before testing bridge)

**Notes:** Focus on `council_mcp/bridges/` directory (~600 LOC across 3 files).
<!-- ID: retro_notes -->
## Phase 4 - Agent Template Audit
<!-- ID: retro_notes -->

**Objective:** Review and update all 9 agent templates with Council MCP usage guidance.

**Assigned Agent:** Forge (Implementation)

**Key Tasks:**
1. **Task 4.1:** Review all 9 agent .md files for completeness
2. **Task 4.2:** Add Council MCP session protocol section to each agent
3. **Task 4.3:** Add memory usage patterns (store_memory/ask_self) to each agent
4. **Task 4.4:** Document Scribe logging requirements (through bridge)
5. **Task 4.5:** Add access control awareness (allow_cross_agent)

**Agent Files to Update:**
```
.claude/agents/
├── atlas.md      (Coordinator) - session management focus
├── lens.md       (Research) - memory queries focus
├── blueprint.md  (Architecture) - memory storage focus
├── forge.md      (Implementation) - audit logging focus
├── arbiter.md    (Review) - cross-agent queries focus
├── crucible.md   (Testing) - tool testing focus
├── sentinel.md   (Security) - access control focus
├── mantis.md     (Debugging) - reflection focus
└── codex.md      (Alternative) - general usage
```

**Required Additions per Agent:**
```markdown
## Council MCP Usage
- Session: `open_session(persona_id="<agent>")` / `end_session(...)`
- Memory: `store_memory(...)` for learnings, `ask_self(...)` for recall
- Logging: Actions relay to Scribe via bridge
- Access: Use `allow_cross_agent=True` only when needed
```

**Deliverables:**
- Updated agent templates (9 files)
- Standard Council MCP usage section template

**Acceptance Criteria:**
- [ ] All 9 agent files have Council MCP usage section (proof: file inspection)
- [ ] Session protocol documented for each role (proof: section content)
- [ ] Memory patterns appropriate for each role (proof: section content)

**Dependencies:** Can run in parallel with Phase 3

**Notes:** Preserve existing agent content, only add Council MCP guidance section.


---
## Phase 5 - Web UI Architecture
<!-- ID: phase_5 -->

**Objective:** Design the architecture for a web UI to visualize and interact with Council MCP.

**Assigned Agent:** Blueprint (Architecture)

**Key Tasks:**
1. **Task 5.1:** Define API surface - which tools expose via REST/WebSocket
2. **Task 5.2:** Design component architecture - persona cards, memory browser, session timeline
3. **Task 5.3:** Spec real-time updates - WebSocket events for session activity
4. **Task 5.4:** Define authentication/authorization approach

**Deliverables:**
- Web UI Architecture document
- API surface specification
- Component hierarchy diagram
- Real-time update event catalog

**Acceptance Criteria:**
- [ ] API surface documented for all 22 tools (proof: API spec)
- [ ] Component architecture designed (proof: component diagram)
- [ ] Real-time events specified (proof: event catalog)

**Dependencies:** Phase 1-2 complete (tools verified before exposing via API)

**Notes:** Architecture only - no implementation in this audit phase.


---
## Phase 6 - Final Review
<!-- ID: phase_6 -->

**Objective:** Compile all findings into AUDIT_REPORT.md and issue final recommendations.

**Assigned Agent:** Arbiter (Review/Audit)

**Key Tasks:**
1. **Task 6.1:** Compile findings from all phases
2. **Task 6.2:** Categorize by severity (HIGH/MEDIUM/LOW)
3. **Task 6.3:** Generate prioritized recommendations
4. **Task 6.4:** Write AUDIT_REPORT.md

**Deliverables:**
- AUDIT_REPORT.md with all findings
- Prioritized recommendation list
- Success criteria verification

**Acceptance Criteria:**
- [ ] All phase findings compiled (proof: AUDIT_REPORT sections)
- [ ] No HIGH severity findings unaddressed (proof: recommendation status)
- [ ] Success criteria from ARCHITECTURE_GUIDE verified (proof: checklist)

**Dependencies:** All other phases complete

**Notes:** This is the final deliverable of the audit.


---
## Milestone Tracking
<!-- ID: milestones -->

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| Research Complete | Done | Lens | COMPLETE | RESEARCH_council_mcp_audit_comprehensive.md |
| Architecture Complete | Day 1 | Blueprint | IN PROGRESS | ARCHITECTURE_GUIDE.md, PHASE_PLAN.md |
| Phase 1 Complete | Day 2 | Sentinel | PENDING | Config validation report |
| Phase 2 Complete | Day 3 | Crucible/Mantis | PENDING | Tool verification matrix |
| Phase 3 Complete | Day 4 | Atlas | PENDING | Bridge verification report |
| Phase 4 Complete | Day 4 | Forge | PENDING | Updated agent templates |
| Phase 5 Complete | Day 5 | Blueprint | PENDING | Web UI architecture |
| Phase 6 Complete | Day 6 | Arbiter | PENDING | AUDIT_REPORT.md |

---
## Retro Notes

- Document lessons learned after each phase completes
- Record any scope changes or blockers encountered
