---
id: council_mcp_audit-architecture-guide
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 council_mcp_audit"
doc_name: ARCHITECTURE_GUIDE
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

# 🏗️ Architecture Guide — council_mcp_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-13 02:21:25 UTC

> Architecture guide for council_mcp_audit.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement
<!-- ID: problem_statement -->

**Context:**
Council MCP v2 is a multi-agent orchestration system providing 12 specialized tools as thin wrappers over AgentKit. Before expanding to web UI and additional features, we need to verify:
- All configuration loads correctly from `.council/council.yaml` with no hardcoded values
- All 22 MCP tools function correctly with proper policy enforcement
- ScribeBridge integration properly relays audit entries
- Agent templates in `.claude/agents/*.md` include Council MCP usage guidance
- Security and access controls are properly enforced

**Goals:**
1. Validate all 12 tool modules work as documented (sessions, profiles, memory, ask, messages, reflection, audit, promote, contexts, personas, access, bridge)
2. Verify configuration externalization is complete (no hardcoded values in code)
3. Confirm ScribeBridge fire-and-forget relay works reliably
4. Ensure agent templates provide correct Council MCP guidance
5. Assess readiness for web UI architecture
6. Document any security gaps or policy enforcement issues

**Non-Goals:**
- Implementing new features during audit
- Changing existing architecture patterns
- Web UI implementation (architecture only)

**Success Metrics:**
- 100% of config values loaded from YAML or environment (zero hardcoded)
- All 22 tools pass functional verification with proper error handling
- ScribeBridge relay confirmed functional with stats monitoring
- All 9 agent templates updated with Council MCP usage
- Security audit produces no HIGH severity findings
<!-- ID: requirements_constraints -->
## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->

**Functional Requirements:**
1. **Configuration Audit:** All settings must load from `.council/council.yaml` with environment override support (`COUNCIL_<SECTION>__<KEY>`)
2. **Tool Verification:** Each of 22 MCP tools must pass functional tests with proper error handling
3. **Bridge Integration:** ScribeBridge must relay audit entries to Scribe MCP without blocking Council operations
4. **Agent Guidance:** All 9 agent templates must include Council MCP usage patterns
5. **Access Control:** Policy decorators must enforce project_id isolation and session requirements
6. **Security:** No HIGH severity vulnerabilities in authentication, authorization, or data handling

**Non-Functional Requirements:**
- Audit must complete within 1 week of starting
- All findings must be documented with severity ratings
- Recommendations must be actionable and prioritized
- No production data used in testing

**Assumptions:**
- AgentKit backend is stable and tested separately
- LLM providers (OSS, OpenAI) are operational
- Scribe MCP is functional for bridge testing
- Test environment matches production configuration

**Risks & Mitigations:**
| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM unavailability during ask_* testing | HIGH | Use skip_llm=true path, mock LLM responses |
| ScribeBridge failures silent | MEDIUM | Monitor relay stats, enable verbose logging |
| Configuration file missing | LOW | Verify default fallback behavior |
| Cross-agent memory leakage | LOW | Verify allow_cross_agent enforcement |
<!-- ID: architecture_overview -->
## 3. Architecture Overview
<!-- ID: architecture_overview -->

**Solution Summary:**
This audit verifies Council MCP v2's architecture across 6 domains: Configuration, Tools, Scribe Integration, Agents, Web UI Readiness, and Security.

**Council MCP Architecture (Under Audit):**
```
┌─────────────────────────────────────────────────────────────┐
│                    Council MCP v2                           │
├─────────────────────────────────────────────────────────────┤
│  .council/council.yaml    ──► Configuration System          │
│       ↓ (YAML + ENV)                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              12 Tool Modules                        │   │
│  │  sessions │ profiles │ memory │ ask │ messages     │   │
│  │  reflection │ audit │ promote │ contexts │ personas │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          │                                  │
│  ┌───────────────────────▼─────────────────────────────┐   │
│  │           AgentKit Backend (storage.models)         │   │
│  │  personas │ memories │ sessions │ messages          │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│  ┌───────────────────────▼─────────────────────────────┐   │
│  │              ScribeBridge                           │   │
│  │  SessionTracker │ AuditRelay │ Fire-and-Forget      │   │
│  └───────────────────────┬─────────────────────────────┘   │
└──────────────────────────┼──────────────────────────────────┘
                           │
                           ▼
                    Scribe MCP (append_entry)
```

**Audit Domains:**

| Domain | Scope | Agent Assignment | Priority |
|--------|-------|------------------|----------|
| 1. Configuration | YAML loading, env overrides, defaults | Sentinel | HIGH |
| 2. Tool Functionality | 22 MCP tools, policy enforcement, error handling | Crucible + Mantis | HIGH |
| 3. Scribe Integration | ScribeBridge relay, SessionTracker, AuditRelay | Atlas | MEDIUM |
| 4. Agent Templates | 9 agent .md files, Council MCP usage guidance | Forge | MEDIUM |
| 5. Web UI Architecture | API surface, component design, real-time updates | Blueprint | LOW |
| 6. Security Review | Access control, data isolation, authentication | Sentinel + Arbiter | HIGH |

**Component Breakdown:**
- **Configuration System:** `.council/council.yaml` with hierarchical defaults + file + environment override
- **Tool Registry:** FastMCP `@mcp.tool()` decorator pattern, lazy singleton handlers
- **AgentKit Integration:** Thin wrapper over `agentkit.storage.models` for all CRUD operations
- **ScribeBridge:** Fire-and-forget audit relay with session-to-project mapping
- **Access Policies:** Decorator-based enforcement (require_project_id, require_open_session, require_profile)
- **Context Manager:** SessionContextManager for thread-aware context tracking
<!-- ID: detailed_design -->
## 4. Detailed Design
<!-- ID: detailed_design -->

### 4.1 Configuration Audit Design

**Audit Targets:**
- `council_mcp/config.py` (257 lines) - Config loader with hierarchical merging
- `.council/council.yaml` - Main configuration file
- Environment variable overrides (`COUNCIL_<SECTION>__<KEY>`)

**Verification Methods:**
1. **Static Analysis:** Grep codebase for hardcoded values (model names, timeouts, limits)
2. **Dynamic Testing:** Override each config section via environment and verify behavior changes
3. **Default Behavior:** Remove config file and verify fallback defaults work correctly
4. **Schema Validation:** Document all available config options with types and defaults

**Config Sections to Audit:**
| Section | Key Settings | Verification |
|---------|-------------|--------------|
| llm | primary_provider, fallback_to_openai, oss_context_limit, temperature | LLM client tests |
| prompts | override_dir, first_person_mode, max_context_memories | Prompt rendering tests |
| queries | default_limit, max_limit, default_bias | Query behavior tests |
| access | require_project_id, allow_cross_project, reserved_personas | Policy enforcement tests |
| sessions | stale_timeout_minutes, max_concurrent_per_persona | Session lifecycle tests |
| memories | default_visibility, default_strength, neuroplasticity_enabled | Memory operation tests |
| messages | urgent_blocking_enabled, auto_thread, retention_days | Message handling tests |
| reflection | on_session_close, min_session_duration, dream_cycles_enabled | Reflection trigger tests |

### 4.2 Tool Functionality Audit Design

**Tool Inventory (22 tools across 12 modules):**

| Module | Tools | Priority |
|--------|-------|----------|
| sessions | open_session, end_session, list_active_sessions, close_stale_sessions | HIGH |
| profiles | register_profile, get_profile, list_profiles | HIGH |
| memory | store_memory, query_memories, reinforce_memory | HIGH |
| ask | ask_self, ask_agent, ask_council | HIGH |
| messages | record_message, list_messages, mark_read, list_urgent_messages | MEDIUM |
| reflection | run_reflection, run_dream_cycle, mine_patterns | MEDIUM |
| audit | log_audit | MEDIUM |
| promote | promote_message | MEDIUM |
| contexts | get_reminders, sync_claude_agents | LOW |
| personas | normalize_persona_id | LOW |

**Verification Methods:**
1. **Functional Tests:** Execute each tool with valid/invalid inputs
2. **Policy Enforcement:** Verify require_* decorators block unauthorized access
3. **Error Handling:** Test error responses for missing parameters, invalid states
4. **Integration:** Test tool chains (open_session -> store_memory -> end_session)

### 4.3 Scribe Bridge Audit Design

**Bridge Components:**
- `ScribeBridge` - Main bridge class with lifecycle hooks
- `SessionTracker` - Session-to-project mapping cache
- `AuditRelay` - Data transformation from Council to Scribe format

**Verification Methods:**
1. **Lifecycle:** Test on_activate/on_deactivate hooks
2. **Relay:** Verify log_audit entries appear in Scribe progress log
3. **Mapping:** Test session→project resolution with workspace matching
4. **Failure Handling:** Verify Scribe failures don't block Council operations

### 4.4 Agent Template Audit Design

**Agent Files (9 personas):**
```
.claude/agents/
├── atlas.md      (Coordinator)
├── lens.md       (Research)
├── blueprint.md  (Architecture)
├── forge.md      (Implementation)
├── arbiter.md    (Review/Audit)
├── crucible.md   (Testing)
├── sentinel.md   (Security)
├── mantis.md     (Debugging)
└── codex.md      (Alternative Perspective)
```

**Required Additions:**
- Council MCP session protocol (open_session/end_session)
- Memory usage patterns (store_memory/ask_self)
- Scribe logging requirements (through bridge)
- Access control awareness (allow_cross_agent)
<!-- ID: directory_structure -->
## 5. Directory Structure (Audit Scope)
<!-- ID: directory_structure -->

```
council_mcp/
├── .council/
│   ├── council.yaml              # [AUDIT] Main config file
│   └── prompts/                  # [AUDIT] Prompt overrides
├── .claude/agents/               # [AUDIT] 9 agent templates
│   ├── atlas.md, lens.md, blueprint.md, forge.md
│   ├── arbiter.md, crucible.md, sentinel.md
│   └── mantis.md, codex.md
├── council_mcp/
│   ├── config.py                 # [AUDIT] Config loader (257 lines)
│   ├── server.py                 # MCP server entry point
│   ├── tools/                    # [AUDIT] 12 tool modules
│   │   ├── __init__.py           # Tool registry
│   │   ├── sessions.py           # Session lifecycle
│   │   ├── profiles.py           # Profile management
│   │   ├── memory.py             # Memory operations
│   │   ├── ask.py, ask_base.py   # Query system
│   │   ├── messages.py           # Inter-agent messaging
│   │   ├── reflection.py         # Reflection/dream cycles
│   │   ├── audit.py              # Audit logging
│   │   └── promote.py            # Message promotion
│   ├── bridges/                  # [AUDIT] Scribe integration
│   │   ├── scribe_bridge.py      # Main bridge
│   │   ├── session_tracker.py    # Session→project mapping
│   │   └── audit_relay.py        # Data transformation
│   ├── context/                  # [AUDIT] Context tracking
│   │   └── manager.py            # SessionContextManager
│   ├── policies/                 # [AUDIT] Access control
│   │   └── personas.py           # Policy decorators
│   └── prompts/                  # Prompt templates
│       └── templates/*.yaml      # Jinja2 templates
└── tests/                        # [REFERENCE] Test coverage
    ├── test_phase3_memory_tools.py
    ├── test_phase4_prompts.py
    └── test_bridge/*.py
```

> Agents rely on this tree for orientation. Files marked [AUDIT] are within scope.
<!-- ID: data_storage -->
## 6. Data & Storage
<!-- ID: data_storage -->

**AgentKit Storage Backend (Primary):**
- **Personas:** `agentkit.storage.models.insert_persona_profile`, `get_persona_profile`, `query_personas`
- **Memories:** `insert_persona_memory`, `query_persona_memories`, `reinforce_memory_strength`
- **Sessions:** `insert_persona_session`, `end_persona_session`, `list_persona_sessions`
- **Messages:** `insert_message`, `query_messages`, `mark_messages_read`

**Embedding Storage:**
- Provider: AgentKit embeddings (384-dim, sentence-transformers based)
- Index: FAISS acceleration layer for semantic search
- Storage: Vector embeddings stored with memory records

**Configuration Storage:**
- File: `.council/council.yaml` (YAML format)
- Runtime: In-memory config dict with lazy loading
- Fallback: Default values in `config.py`

**Audit Storage:**
- Primary: AgentKit audit tables
- Secondary: Scribe MCP progress log (via ScribeBridge relay)

**Session Context:**
- Type: In-memory per-session state
- Cleanup: Automatic on session end or stale timeout (240min default)
- Compression: Reflection-based synthesis on session close
<!-- ID: testing_strategy -->
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->

**Existing Test Coverage (Reference):**
- 20 test files, 3,506 lines of code
- Phase-based organization: Phase2, Phase3, Phase4
- Component coverage: tools, integration, bridge, access policies

**Audit Test Strategy:**

| Test Type | Purpose | Files |
|-----------|---------|-------|
| Config Static | Scan for hardcoded values | `grep -r` analysis |
| Config Dynamic | Verify env override behavior | New audit tests |
| Tool Functional | Execute each tool with test cases | Existing + new |
| Policy Enforcement | Verify access control decorators | `test_access_policies.py` |
| Bridge Lifecycle | Test ScribeBridge activate/deactivate | `test_bridge/*.py` |
| Bridge Relay | Verify audit entries reach Scribe | Integration tests |
| Agent Templates | Validate Council usage guidance | Manual review |
| Security | Check data isolation and auth | Security audit tests |

**Verification Commands:**
```bash
# Run all existing tests
pytest tests/ -v

# Run specific phase tests
pytest tests/test_phase3_memory_tools.py -v
pytest tests/test_phase4_prompts.py -v

# Run bridge tests
pytest tests/test_bridge/ -v

# Check config hardcoding
grep -rn "gpt-4" council_mcp/
grep -rn "model=" council_mcp/ | grep -v "def\|config\|#"
```

**Manual QA:**
- Verify each agent template has Council MCP usage section
- Confirm bridge relay works end-to-end with Scribe
- Test LLM fallback path (OSS unavailable -> OpenAI)
<!-- ID: deployment_operations -->
## 8. Deployment & Operations
<!-- ID: deployment_operations -->

**Audit Environment:**
- Repository: `/home/austin/projects/MCP_SPINE/council_mcp`
- Config: `.council/council.yaml` (must exist for production-like testing)
- Dependencies: AgentKit, FastMCP, Scribe MCP

**Audit Execution:**
1. **Phase 1-2 (HIGH priority):** Run sequentially, block on failures
2. **Phase 3-4 (MEDIUM priority):** Can run in parallel after Phase 1-2
3. **Phase 5 (LOW priority):** Architecture only, no implementation
4. **Phase 6:** Final compilation after all phases complete

**Audit Artifacts:**
- `AUDIT_REPORT.md` - Final compilation of all findings
- Individual phase reports in progress log
- Updated agent templates with Council MCP guidance

**Success Criteria Verification:**
- [ ] Zero hardcoded config values in codebase
- [ ] All 22 tools pass functional verification
- [ ] ScribeBridge relay confirmed functional
- [ ] All 9 agent templates updated
- [ ] No HIGH severity security findings
<!-- ID: open_questions -->
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->

| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| LLM fallback behavior when OSS unavailable | Crucible | TODO | Verify graceful degradation path |
| ScribeBridge silent failure monitoring | Atlas | TODO | What metrics are available? |
| Cross-agent memory visibility defaults | Sentinel | TODO | Verify allow_cross_agent enforcement |
| Agent template update format | Forge | TODO | Define standard Council MCP usage section |
| Web UI API surface requirements | Blueprint | TODO | Phase 5 deliverable |
| Session context memory limits | Mantis | TODO | What happens when context exceeds limits? |

Close each question once answered and reference the relevant section above.
<!-- ID: references_appendix -->
## 10. References & Appendix
<!-- ID: references_appendix -->

**Research Documents:**
- `research/RESEARCH_council_mcp_audit_comprehensive.md` - Lens's comprehensive research findings

**Key Code References:**
| File | Purpose | LOC |
|------|---------|-----|
| `council_mcp/config.py` | Config loader | 257 |
| `council_mcp/tools/*.py` | Tool implementations | ~2,850 |
| `council_mcp/bridges/*.py` | ScribeBridge | ~600 |
| `council_mcp/context/*.py` | SessionContextManager | ~500 |
| `.claude/agents/*.md` | Agent templates | ~3,100 |
| `tests/*.py` | Test coverage | 3,506 |

**Configuration Schema (from research):**
- **llm:** primary_provider, fallback_to_openai, oss_context_limit, openai_model, temperature
- **prompts:** override_dir, first_person_mode, include_memory_metadata, max_context_memories
- **queries:** default_limit, max_limit, include_embeddings, default_bias
- **access:** require_project_id, allow_cross_project, default_cross_persona, omniscient_roles
- **sessions:** stale_timeout_minutes, max_concurrent_per_persona, cleanup_on_startup
- **memories:** default_visibility, default_strength, neuroplasticity_enabled
- **messages:** urgent_blocking_enabled, auto_thread, retention_days
- **reflection:** on_session_close, min_session_duration, contradiction_detection, dream_cycles_enabled

**Agent Roles:**
| Persona | Role | Audit Domain |
|---------|------|--------------|
| Atlas | Coordinator | Scribe Integration |
| Lens | Research | (Complete) |
| Blueprint | Architecture | Web UI Architecture |
| Forge | Implementation | Agent Templates |
| Arbiter | Review/Audit | Final Review |
| Crucible | Testing | Tool Functionality |
| Sentinel | Security | Config + Security |
| Mantis | Debugging | Tool Functionality |
| Codex | Alternative | (Available if needed) |

---
Generated by Blueprint (Architect Agent) for council_mcp_audit
