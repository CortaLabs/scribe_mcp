---
id: bridge_api_hardening-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 bridge_api_hardening"
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-16'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — bridge_api_hardening
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-16 11:55:04 UTC

> Execution roadmap for bridge_api_hardening.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Goal | Key Deliverables | Est. Complexity | Dependencies |
|-------|------|------------------|-----------------|--------------|
| Phase 1 — Server Integration | Add bridge init code to server.py | BridgeRegistry instantiation, manifest discovery, activation loop, health monitor | Medium (~45 lines) | None (all infrastructure exists) |
| Phase 2 — Testing & Validation | Verify bridge system works end-to-end | Unit tests, integration tests, manual QA with test manifest | Low | Phase 1 complete |
| Phase 3 — Documentation & Polish | Update docs, add examples | Bridge development guide, example manifest, deployment notes | Low | Phase 2 complete |

**Confidence:** 0.95 (High - research verified all infrastructure exists, only server wiring needed)

**Timeline Estimate:** 
- Phase 1: 2-4 hours (implementation)
- Phase 2: 2-3 hours (testing)
- Phase 3: 1-2 hours (docs)
- Total: 5-9 hours developer time
<!-- ID: phase_0 -->
## Phase 1 — Server Integration
<!-- ID: phase_0 -->

**Objective:** Add bridge system initialization to server.py startup sequence

**Scope:** Modify 1 file (server.py), add ~45 lines of code

### Task Package 1.1: BridgeRegistry Initialization

**Files to Modify:** `server.py` (lines 661-663, insert after plugin initialization)

**Specifications:**
1. Add imports at top of _startup() function (after line 661):
   ```python
   from scribe_mcp.bridges.registry import BridgeRegistry
   from scribe_mcp.bridges.health import BridgeHealthMonitor, set_health_monitor
   from pathlib import Path
   import asyncio  # Already imported, just note for reference
   ```

2. Add conditional check for BRIDGES_AVAILABLE and storage_backend

3. Create BridgeRegistry instance with:
   - storage_backend parameter (from server globals)
   - config_dir = Path(".scribe/config/bridges")

4. Wrap entire bridge init in try/except:
   - On error: print warning, set bridge_registry = None, continue startup
   - Print: "🌉 BridgeRegistry initialized" on success

**Verification:**
- [ ] Server starts successfully with BRIDGES_AVAILABLE = True
- [ ] Server starts successfully with BRIDGES_AVAILABLE = False
- [ ] Server continues if BridgeRegistry creation fails
- [ ] Print statement confirms initialization

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify bridge module code (bridges/*.py)
- Do NOT modify storage layer (storage/*.py)
- Do NOT modify existing tool registration code (lines 682-702)

---

### Task Package 1.2: Manifest Discovery & Registration Loop

**Files to Modify:** `server.py` (continue in _startup() after 1.1)

**Specifications:**
1. Check if bridge_registry is not None

2. Call bridge_registry.discover_manifests() to get list of manifest paths

3. For each manifest_path in manifests:
   - Wrap in try/except (per-manifest error handling)
   - Call bridge_registry.load_manifest(manifest_path)
   - **Await** bridge_registry.register_bridge(manifest)
   - **Await** bridge_registry.activate_bridge(bridge_id)
   - Print: "   ✅ Registered & activated bridge: {bridge_id}"
   - On error: print warning, continue with next manifest

4. After loop:
   - If manifests found: print "🌉 Bridge system initialized (X/Y bridges active)"
   - If no manifests: print "🌉 Bridge system initialized (no manifests found)"

**Verification:**
- [ ] discover_manifests() called correctly
- [ ] Loop handles empty manifest list gracefully
- [ ] Individual manifest failures don't crash server
- [ ] register_bridge() and activate_bridge() are properly awaited
- [ ] Success messages print for each activated bridge

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify manifest.py validation logic
- Do NOT modify registry.py lifecycle methods
- Do NOT add custom error recovery beyond try/except

---

### Task Package 1.3: Health Monitor Background Task

**Files to Modify:** `server.py` (continue in _startup() after 1.2)

**Specifications:**
1. Check if bridge_registry is not None

2. Create BridgeHealthMonitor instance:
   - registry parameter: bridge_registry
   - check_interval parameter: 60.0 (hardcoded float)

3. Call set_health_monitor(health_monitor) to register global instance

4. Start background task:
   - Use: asyncio.create_task(health_monitor.start())
   - Do NOT await (non-blocking background task)

5. Print: "🏥 Bridge health monitor started (60s interval)"

**Verification:**
- [ ] Health monitor created successfully
- [ ] set_health_monitor() called
- [ ] Background task created (asyncio.create_task)
- [ ] Task does NOT block server startup
- [ ] Print statement confirms health monitor started

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify health.py monitoring logic
- Do NOT change check_interval dynamically
- Do NOT add health check UI or admin commands

---

### Deliverables

**Code Changes:**
- server.py: ~45 lines added after line 661
- No other files modified

**Expected Output (Server Startup):**
```
🔌 Plugin system initialized
🌉 BridgeRegistry initialized
   ✅ Registered & activated bridge: council_mcp
🌉 Bridge system initialized (1/1 bridges active)
🏥 Bridge health monitor started (60s interval)
🤖 AgentContextManager initialized for multi-agent support
...
```

**Acceptance Criteria:**
- [ ] Server starts without errors
- [ ] BridgeRegistry initialized
- [ ] Manifests discovered and registered
- [ ] Bridges activated successfully
- [ ] Health monitor running in background
- [ ] Server continues if no manifests found
- [ ] Server continues if bridge initialization fails
- [ ] All async/await used correctly
- [ ] No modifications to bridge modules or storage layer

**Dependencies:** None (all infrastructure exists)

**Estimated Effort:** 2-4 hours (implementation + initial testing)
<!-- ID: phase_1 -->
## Phase 2 — Testing & Validation
---

## Phase 3 — Documentation & Polish
<!-- ID: phase_3 -->

**Objective:** Create comprehensive bridge development documentation for downstream projects

**Scope:** Update docs, add examples, create developer guide

### Task Package 3.1: Bridge Development Guide

**Files to Create:** `docs/BRIDGE_DEVELOPMENT.md`

**Content Requirements:**

**Section 1: Overview**
- What are Scribe bridges?
- Use cases (Council MCP, future integrations)
- Architecture summary (BridgeRegistry, manifests, hooks)

**Section 2: Creating a Bridge**
- Step 1: Create manifest YAML
- Step 2: Implement BridgePlugin class
- Step 3: Define hooks (pre_append, post_append, etc.)
- Step 4: Add custom tools (optional)
- Step 5: Deploy manifest to `.scribe/config/bridges/`

**Section 3: Manifest Schema Reference**
- Required fields (bridge_id, name, version, description, author)
- Permissions model (read:all_projects, write:own_projects, create:projects)
- Project configuration (prefix, auto-tags, metadata)
- Hooks configuration (pre/post append/rotate/project)
- Custom tools definition

**Section 4: Testing Your Bridge**
- Local testing with test manifest
- Unit testing with mocks
- Integration testing with real server
- Debugging tips

**Section 5: Deployment**
- Manifest file placement
- Server restart required
- Verifying bridge registered
- Health monitoring

**Verification:**
- [ ] Document created with all 5 sections
- [ ] Code examples included
- [ ] Schema reference complete
- [ ] Testing guide clear

---

### Task Package 3.2: Example Bridge Template

**Files to Create:** 
- `examples/bridge_template/manifest.yaml`
- `examples/bridge_template/plugin.py`
- `examples/bridge_template/README.md`

**Specifications:**

**manifest.yaml:**
- Minimal working manifest
- Comments explaining each field
- Example permissions and hooks

**plugin.py:**
- BridgePlugin subclass with boilerplate
- Implement on_activate() hook
- Implement health_check() method
- Example pre_append() hook

**README.md:**
- Quick start guide
- How to customize
- Testing instructions

**Verification:**
- [ ] Template files created
- [ ] Template actually works (tested)
- [ ] README clear for developers
- [ ] Comments explain all fields

---

### Task Package 3.3: Update Main Documentation

**Files to Modify:**
- `CLAUDE.md` - Add bridge system overview
- `AGENTS.md` - Document bridge architecture section
- `README.md` - Add bridge extension capability mention

**Specifications:**

**CLAUDE.md Updates:**
- Add section: "Bridge Extension System"
- Explain manifest-based integration
- Link to BRIDGE_DEVELOPMENT.md
- Note: Bridges are optional, server works without them

**AGENTS.md Updates:**
- Document bridge architecture in system overview
- Explain bridge lifecycle (registered → active → inactive/error)
- Document storage layer bridge support

**README.md Updates:**
- Add feature bullet: "Extension system via bridge manifests"
- Link to bridge development docs
- Example: Council MCP integration

**Verification:**
- [ ] All 3 docs updated
- [ ] Links valid
- [ ] Consistent terminology
- [ ] No outdated information

---

### Deliverables

**New Documentation:**
- `docs/BRIDGE_DEVELOPMENT.md` (comprehensive guide)
- `examples/bridge_template/` (working template)

**Updated Documentation:**
- `CLAUDE.md` (bridge section added)
- `AGENTS.md` (architecture documented)
- `README.md` (feature mention)

**Acceptance Criteria:**
- [ ] Bridge development guide complete
- [ ] Example template works
- [ ] All docs updated and consistent
- [ ] Downstream developers can create bridges
- [ ] Links and references valid

**Dependencies:** Phase 2 complete (testing validated bridge system works)

**Estimated Effort:** 1-2 hours (documentation writing)

---

<!-- ID: phase_1 -->

**Objective:** Verify bridge system works end-to-end with comprehensive testing

**Scope:** Add test files, create test manifest, verify integration

### Task Package 2.1: Unit Tests for Bridge Initialization

**Files to Create:** `tests/test_bridge_server_integration.py`

**Specifications:**
1. Test BridgeRegistry initialization:
   - Mock storage_backend
   - Verify registry created with correct parameters
   - Verify graceful failure if import fails

2. Test manifest discovery:
   - Mock filesystem with test manifest directory
   - Verify discover_manifests() finds .yaml files
   - Verify empty directory returns []

3. Test registration loop error handling:
   - Mock manifests with one valid, one invalid
   - Verify invalid manifest doesn't crash loop
   - Verify valid manifest registers successfully

**Verification:**
- [ ] pytest tests/test_bridge_server_integration.py passes
- [ ] All initialization paths covered
- [ ] Error scenarios tested
- [ ] Mocks properly isolate bridge code

---

### Task Package 2.2: Integration Test with Test Manifest

**Files to Create:** 
- `tests/fixtures/test_bridge_manifest.yaml` (test manifest)
- `tests/test_bridge_end_to_end.py` (integration test)

**Specifications:**

**Test Manifest Content:**
```yaml
bridge_id: test_bridge
name: Test Bridge
version: 1.0.0
description: Test bridge for integration testing
author: Scribe Test Suite
permissions:
  - read:all_projects
project_config:
  can_create_projects: false
hooks: {}
```

**Integration Test:**
1. Start server with test manifest in config directory
2. Verify bridge registered in storage (query scribe_bridges table)
3. Verify bridge state = "active"
4. Verify health monitor background task running
5. Stop server, verify cleanup

**Verification:**
- [ ] Integration test passes end-to-end
- [ ] Bridge persisted to storage correctly
- [ ] Health monitor runs without blocking
- [ ] Server startup/shutdown clean

---

### Task Package 2.3: Manual QA Testing

**Test Scenarios:**

**Scenario 1: No Manifests (Clean State)**
- Remove all manifests from `.scribe/config/bridges/`
- Start server
- Expected: "🌉 Bridge system initialized (no manifests found)"
- Verify: Server works normally, no crashes

**Scenario 2: Invalid Manifest**
- Create invalid YAML manifest (syntax error)
- Start server
- Expected: Warning printed, server continues
- Verify: Server doesn't crash, other bridges unaffected

**Scenario 3: Valid Council MCP Manifest**
- Use existing `.scribe/config/bridges/council_mcp.yaml`
- Start server
- Expected: Bridge registered and activated
- Verify: Bridge tools available in MCP

**Scenario 4: Bridge Activation Failure**
- Create manifest with missing plugin class
- Start server
- Expected: Registration succeeds, activation fails gracefully
- Verify: Bridge state = "registered" not "active"

**Verification:**
- [ ] All 4 scenarios tested manually
- [ ] Results documented in PROGRESS_LOG
- [ ] No unexpected crashes or failures
- [ ] Graceful degradation confirmed

---

### Deliverables

**Test Files Created:**
- `tests/test_bridge_server_integration.py` (unit tests)
- `tests/test_bridge_end_to_end.py` (integration tests)
- `tests/fixtures/test_bridge_manifest.yaml` (test data)

**Test Coverage:**
- Unit tests: BridgeRegistry init, manifest discovery, error handling
- Integration tests: End-to-end server startup with bridge
- Manual QA: 4 scenarios covering edge cases

**Acceptance Criteria:**
- [ ] All unit tests pass (pytest)
- [ ] Integration test passes
- [ ] Manual QA scenarios documented
- [ ] No regressions in existing server functionality
- [ ] Test manifest works correctly

**Dependencies:** Phase 1 complete (server integration code exists)

**Estimated Effort:** 2-3 hours (test writing + execution)
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Foundation Complete | 2025-10-29 | DevTeam | 🚧 In Progress | PROGRESS_LOG.md |
| Template Engine Ship | 2025-11-02 | DevTeam | ⏳ Planned | Phase 1 tasks |
Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.


---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.


---