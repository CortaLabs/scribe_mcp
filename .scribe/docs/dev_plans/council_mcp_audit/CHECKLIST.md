---
id: council_mcp_audit-checklist
title: "\u2705 Acceptance Checklist \u2014 council_mcp_audit"
doc_name: CHECKLIST
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

# ✅ Acceptance Checklist — council_mcp_audit
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-01-13 02:21:25 UTC

> Acceptance checklist for council_mcp_audit.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Pre-Audit Setup
<!-- ID: documentation_hygiene -->

- [x] Research document complete (proof: RESEARCH_council_mcp_audit_comprehensive.md)
- [x] Architecture guide populated (proof: ARCHITECTURE_GUIDE.md sections updated)
- [x] Phase plan created (proof: PHASE_PLAN.md with 6 phases)
- [x] Checklist initialized (proof: this document)
- [ ] All agents briefed on their assignments
<!-- ID: phase_0 -->
## Phase 1: Configuration Audit (Sentinel)
<!-- ID: phase_0 -->

### Task 1.1: Static Analysis
- [ ] Grep codebase for hardcoded model names (proof: grep output)
- [ ] Grep codebase for hardcoded timeouts (proof: grep output)
- [ ] Grep codebase for hardcoded limits (proof: grep output)

### Task 1.2: YAML Loading
- [ ] Verify `llm` section loads correctly (proof: config test)
- [ ] Verify `prompts` section loads correctly (proof: config test)
- [ ] Verify `queries` section loads correctly (proof: config test)
- [ ] Verify `access` section loads correctly (proof: config test)
- [ ] Verify `sessions` section loads correctly (proof: config test)
- [ ] Verify `memories` section loads correctly (proof: config test)
- [ ] Verify `messages` section loads correctly (proof: config test)
- [ ] Verify `reflection` section loads correctly (proof: config test)
- [ ] Verify `context` section loads correctly (proof: config test)
- [ ] Verify `reasoning` section loads correctly (proof: config test)
- [ ] Verify `explore` section loads correctly (proof: config test)

### Task 1.3: Environment Overrides
- [ ] Test `COUNCIL_LLM__*` overrides (proof: env test)
- [ ] Test `COUNCIL_PROMPTS__*` overrides (proof: env test)
- [ ] Test `COUNCIL_ACCESS__*` overrides (proof: env test)

### Task 1.4: Documentation
- [ ] Create config schema documentation (proof: doc file)
<!-- ID: final_verification -->
## Phase 2: Tool Functionality Audit (Crucible + Mantis)
<!-- ID: final_verification -->

### Session Tools
- [ ] open_session works with valid input (proof: test)
- [ ] end_session works with valid input (proof: test)
- [ ] list_active_sessions returns correct data (proof: test)
- [ ] close_stale_sessions cleans up correctly (proof: test)

### Profile Tools
- [ ] register_profile creates/updates profile (proof: test)
- [ ] get_profile returns correct profile (proof: test)
- [ ] list_profiles returns all profiles (proof: test)

### Memory Tools
- [ ] store_memory persists correctly (proof: test)
- [ ] query_memories returns relevant results (proof: test)
- [ ] reinforce_memory adjusts strength (proof: test)

### Ask Tools
- [ ] ask_self returns synthesized answer (proof: test)
- [ ] ask_agent enforces allow_cross_agent (proof: test)
- [ ] ask_council aggregates responses (proof: test)

### Message Tools
- [ ] record_message creates message (proof: test)
- [ ] list_messages returns messages (proof: test)
- [ ] mark_read updates status (proof: test)
- [ ] list_urgent_messages filters correctly (proof: test)

### Reflection Tools
- [ ] run_reflection generates layers (proof: test)
- [ ] run_dream_cycle creates synthesis (proof: test)
- [ ] mine_patterns identifies clusters (proof: test)

### Utility Tools
- [ ] log_audit records entry (proof: test)
- [ ] promote_message creates memory (proof: test)

### Policy Enforcement
- [ ] require_project_id blocks missing project (proof: test)
- [ ] require_open_session blocks without session (proof: test)
- [ ] require_profile blocks unregistered persona (proof: test)


---
## Phase 3: Scribe Integration Audit (Atlas)
<!-- ID: phase_3 -->

- [ ] ScribeBridge on_activate initializes cleanly (proof: logs)
- [ ] ScribeBridge on_deactivate cleans up (proof: logs)
- [ ] SessionTracker maps workspace to project (proof: test)
- [ ] AuditRelay transforms data correctly (proof: test)
- [ ] log_audit entries appear in Scribe progress log (proof: log inspection)
- [ ] Scribe failure does not block Council (proof: failure test)


---
## Phase 4: Agent Template Audit (Forge)
<!-- ID: phase_4 -->

- [ ] atlas.md has Council MCP usage section (proof: file)
- [ ] lens.md has Council MCP usage section (proof: file)
- [ ] blueprint.md has Council MCP usage section (proof: file)
- [ ] forge.md has Council MCP usage section (proof: file)
- [ ] arbiter.md has Council MCP usage section (proof: file)
- [ ] crucible.md has Council MCP usage section (proof: file)
- [ ] sentinel.md has Council MCP usage section (proof: file)
- [ ] mantis.md has Council MCP usage section (proof: file)
- [ ] codex.md has Council MCP usage section (proof: file)


---
## Phase 5: Web UI Architecture (Blueprint)
<!-- ID: phase_5 -->

- [ ] API surface documented for all 22 tools (proof: API spec)
- [ ] Component architecture designed (proof: diagram)
- [ ] Real-time events specified (proof: event catalog)
- [ ] Authentication approach defined (proof: spec)


---
## Phase 6: Final Review (Arbiter)
<!-- ID: phase_6 -->

- [ ] All phase findings compiled (proof: AUDIT_REPORT sections)
- [ ] Findings categorized by severity (proof: severity table)
- [ ] Recommendations prioritized (proof: priority list)
- [ ] AUDIT_REPORT.md complete (proof: file)
- [ ] No HIGH severity findings unaddressed (proof: status)


---
## Final Verification
<!-- ID: final_sign_off -->

- [ ] All checklist items checked with proofs attached
- [ ] Stakeholder sign-off recorded (name + date)
- [ ] Retro completed and lessons learned documented
