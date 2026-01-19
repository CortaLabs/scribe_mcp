---
id: council_mcp_bridge_api-checklist
title: "\u2705 Acceptance Checklist \u2014 council_mcp_bridge_api"
doc_name: CHECKLIST
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-12'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — council_mcp_bridge_api
**Author:** ArchitectAgent
**Version:** v1.0
**Status:** Ready for Implementation
**Last Updated:** 2026-01-12 03:15:00 UTC

> Acceptance checklist for Bridge Registry system implementation.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [x] ARCHITECTURE_GUIDE.md complete with all sections
- [x] PHASE_PLAN.md complete with 5 phases and 14 task packages
- [x] CHECKLIST.md structured with phase-aligned verification criteria


---
## Phase 1: Core Bridge Registry
<!-- ID: phase_1 -->

### Task 1.1: Bridge Manifest Schema
- [ ] **All dataclasses implemented** (proof: `bridges/manifest.py` exists with 5+ dataclasses)
- [ ] **Validation methods work** (proof: `pytest tests/test_bridge_manifest.py::test_validation`)
- [ ] **JSON serialization round-trips** (proof: `pytest tests/test_bridge_manifest.py::test_serialization`)
- [ ] **Environment variable expansion** (proof: `pytest tests/test_bridge_manifest.py::test_env_vars`)

### Task 1.2: BridgePlugin Base Class
- [ ] **BridgePlugin extends HookPlugin** (proof: `bridges/plugin.py` imports HookPlugin)
- [ ] **Abstract methods enforced** (proof: `pytest tests/test_bridge_plugin.py::test_abstract_methods`)
- [ ] **Constructor initializes correctly** (proof: `pytest tests/test_bridge_plugin.py::test_initialization`)
- [ ] **Hook method signatures correct** (proof: code review)

### Task 1.3: BridgeRegistry
- [ ] **YAML manifest loads** (proof: `pytest tests/test_bridge_registry.py::test_load_manifest`)
- [ ] **Bridge registration persists** (proof: `pytest tests/test_bridge_registry.py::test_register_bridge`)
- [ ] **State transitions work** (proof: `pytest tests/test_bridge_registry.py::test_state_transitions`)
- [ ] **Multiple bridges coexist** (proof: `pytest tests/test_bridge_registry.py::test_multiple_bridges`)
- [ ] **Unregistration cleans up** (proof: `pytest tests/test_bridge_registry.py::test_unregister`)

### Task 1.4: Storage Layer Extensions
- [ ] **scribe_bridges table created** (proof: `sqlite3 db.db ".schema scribe_bridges"`)
- [ ] **Bridge CRUD operations work** (proof: `pytest tests/test_storage_bridges.py`)
- [ ] **Indexes exist** (proof: `sqlite3 db.db ".indexes scribe_bridges"`)
- [ ] **JSON manifest storage** (proof: query returns valid JSON)

### Task 1.5: Configuration Loading
- [ ] **YAML discovery works** (proof: `pytest tests/test_bridge_registry.py::test_discover_manifests`)
- [ ] **Valid manifests load** (proof: server startup logs)
- [ ] **Invalid manifests logged** (proof: server startup with bad YAML)
- [ ] **BridgeRegistry accessible** (proof: `scribe-admin bridge list`)

**Phase 1 Acceptance**: All 5 tasks verified, unit tests pass, integration tests pass


---
## Phase 2: Bridge Hooks
<!-- ID: phase_2 -->

### Task 2.1: BridgeToScribeAPI
- [ ] **Permission checks block unauthorized ops** (proof: `pytest tests/test_bridge_api.py::test_permissions`)
- [ ] **Bridge metadata injected** (proof: `pytest tests/test_bridge_api.py::test_metadata_injection`)
- [ ] **API calls logged** (proof: progress log has bridge_id)
- [ ] **Policy enforces restrictions** (proof: `pytest tests/test_bridge_policy.py`)

### Task 2.2: Hook Integration
- [ ] **pre_append hooks receive params** (proof: `pytest tests/integration/test_bridge_hooks.py::test_pre_append`)
- [ ] **post_append hooks receive result** (proof: `pytest tests/integration/test_bridge_hooks.py::test_post_append`)
- [ ] **Critical hooks block operations** (proof: `pytest tests/integration/test_bridge_hooks.py::test_critical_failure`)
- [ ] **Non-critical hooks don't block** (proof: `pytest tests/integration/test_bridge_hooks.py::test_non_critical_failure`)
- [ ] **Timeout enforcement works** (proof: `pytest tests/integration/test_bridge_hooks.py::test_timeout`)

### Task 2.3: Error Isolation & Timeout
- [ ] **Bridge timeout doesn't crash** (proof: `pytest tests/test_bridge_security.py::test_timeout_isolation`)
- [ ] **Bridge exception doesn't crash** (proof: `pytest tests/test_bridge_security.py::test_exception_isolation`)
- [ ] **Repeated failures → ERROR state** (proof: `pytest tests/test_bridge_security.py::test_error_state_transition`)
- [ ] **Other bridges unaffected** (proof: `pytest tests/test_bridge_security.py::test_cross_bridge_isolation`)

**Phase 2 Acceptance**: All 3 tasks verified, append_entry performance <10ms overhead, hooks isolated


---
## Phase 3: Bridge-Managed Projects
<!-- ID: phase_3 -->

### Task 3.1: Project Namespacing
- [ ] **bridge_id stored in projects** (proof: `sqlite3 db.db "SELECT bridge_id FROM scribe_projects"`)
- [ ] **Prefix strategy works** (proof: `pytest tests/integration/test_bridge_projects.py::test_prefix_strategy`)
- [ ] **Tag strategy works** (proof: `pytest tests/integration/test_bridge_projects.py::test_tag_strategy`)
- [ ] **Bridge metadata in state** (proof: `scribe.get_project()` shows bridge_id)

### Task 3.2: Access Control
- [ ] **Bridge modifies own projects** (proof: `pytest tests/integration/test_bridge_projects.py::test_own_project_access`)
- [ ] **Bridge blocked from other projects** (proof: `pytest tests/integration/test_bridge_projects.py::test_cross_bridge_block`)
- [ ] **Non-managed projects accessible** (proof: `pytest tests/integration/test_bridge_projects.py::test_unmanaged_access`)
- [ ] **Access violations logged** (proof: progress log has access_violation status)

**Phase 3 Acceptance**: All 2 tasks verified, namespacing works, access control enforced


---
## Phase 4: Tool Extension
<!-- ID: phase_4 -->

### Task 4.1: BridgeToolWrapper
- [ ] **Tool wrapping preserves signature** (proof: `pytest tests/test_bridge_tools.py::test_signature_preservation`)
- [ ] **pre_call modifies args** (proof: `pytest tests/test_bridge_tools.py::test_pre_call`)
- [ ] **post_call receives result** (proof: `pytest tests/test_bridge_tools.py::test_post_call`)
- [ ] **Wrapped tools work via MCP** (proof: manual MCP call test)

### Task 4.2: MCP Server Integration
- [ ] **Bridge tools visible in MCP** (proof: MCP tools list includes prefixed tools)
- [ ] **Bridge tools callable** (proof: successful MCP tool call)
- [ ] **Tool permissions enforced** (proof: unauthorized call blocked)
- [ ] **Multiple bridges coexist** (proof: tools from 2+ bridges both work)

**Phase 4 Acceptance**: All 2 tasks verified, tools wrapped, MCP integration works


---
## Phase 5: Advanced Features
<!-- ID: phase_5 -->

### Task 5.1: BridgeHealthMonitor
- [ ] **Health checks run periodically** (proof: progress log shows health_check entries)
- [ ] **Unhealthy bridges → ERROR** (proof: simulated failure transitions state)
- [ ] **Recovery → ACTIVE** (proof: simulated recovery transitions back)
- [ ] **Non-blocking checks** (proof: server continues during health check)

### Task 5.2: Admin CLI Commands
- [ ] **All commands work** (proof: manual testing of each command)
- [ ] **State transitions immediate** (proof: `scribe-admin bridge status` after deactivate)
- [ ] **Error messages clear** (proof: invalid command produces helpful error)
- [ ] **Help text comprehensive** (proof: `scribe-admin bridge --help`)

### Task 5.3: Documentation & Examples
- [ ] **External developer can create bridge** (proof: fresh developer follows docs successfully)
- [ ] **Example bridge works E2E** (proof: `examples/council_bridge.py` runs successfully)
- [ ] **All features documented** (proof: docs cover manifest, hooks, tools, projects, health)
- [ ] **Security best practices included** (proof: docs mention API keys, permissions, timeouts)

**Phase 5 Acceptance**: All 3 tasks verified, health monitoring works, admin CLI complete, docs comprehensive


---
## Integration Testing
<!-- ID: integration_testing -->
- [ ] **End-to-end bridge lifecycle** (proof: `pytest tests/integration/test_bridge_lifecycle.py`)
- [ ] **Council MCP bridge registers** (proof: real council_mcp.yaml loads successfully)
- [ ] **Council bridge creates projects** (proof: "council_" prefixed project created)
- [ ] **Council bridge receives hooks** (proof: pre_append called on append_entry)
- [ ] **Council bridge calls Scribe APIs** (proof: bridge logs entry via BridgeToScribeAPI)
- [ ] **Multiple bridges don't interfere** (proof: 2 bridges active, both work independently)
- [ ] **Bridge failure doesn't crash Scribe** (proof: simulated crash, server continues)


---
## Performance Verification
<!-- ID: performance_verification -->
- [ ] **Append_entry overhead <10ms** (proof: benchmark with/without bridges)
- [ ] **Health checks don't block operations** (proof: append_entry during health check)
- [ ] **Manifest loading <100ms** (proof: server startup time measurement)
- [ ] **Bridge state cached** (proof: no DB query per hook call)


---
## Security Verification
<!-- ID: security_verification -->
- [ ] **API keys not committed** (proof: `git log --all -S "COUNCIL_BRIDGE_API_KEY"` empty)
- [ ] **Permissions enforced** (proof: unauthorized append_entry blocked)
- [ ] **Timeouts prevent hangs** (proof: slow bridge hook killed after timeout)
- [ ] **Cross-bridge isolation** (proof: bridge A can't modify bridge B's projects)
- [ ] **Error isolation works** (proof: bridge exception doesn't propagate)


---
## Final Verification
<!-- ID: final_verification -->
- [ ] **All phase checklists complete** (proof: phases 1-5 all checked)
- [ ] **All integration tests pass** (proof: `pytest tests/integration/`)
- [ ] **All unit tests pass** (proof: `pytest tests/`)
- [ ] **Performance benchmarks met** (proof: <10ms overhead, non-blocking)
- [ ] **Security audit complete** (proof: all security checks passed)
- [ ] **Documentation reviewed** (proof: external developer successful)
- [ ] **Example bridge works** (proof: council_bridge.py runs E2E)
- [ ] **Stakeholder sign-off** (proof: user approval of implementation)
- [ ] **Retro completed** (proof: lessons learned documented in PHASE_PLAN retro section)


---
