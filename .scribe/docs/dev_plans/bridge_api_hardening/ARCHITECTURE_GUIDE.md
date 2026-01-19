---
id: bridge_api_hardening-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 bridge_api_hardening"
doc_name: architecture
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

# 🏗️ Architecture Guide — bridge_api_hardening
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-16 11:55:04 UTC

> Architecture guide for bridge_api_hardening.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement
<!-- ID: problem_statement -->

**Context:** Scribe MCP has a complete bridge extension infrastructure (10 modules, 75+ methods, full storage layer) but server.py has ZERO bridge initialization code. The BridgeRegistry is never instantiated, manifests are never discovered, and bridges cannot activate. The entire bridge system is dormant despite being production-ready.

**Goals:**
- Add BridgeRegistry initialization to server.py startup sequence
- Discover and register bridge manifests from `.scribe/config/bridges/*.yaml`
- Activate registered bridges with proper error isolation
- Start BridgeHealthMonitor background task for health tracking
- Enable downstream projects (Council MCP) to integrate via bridge manifests

**Non-Goals:**
- Modify existing bridge module architecture (already complete)
- Change storage layer (6 methods fully implemented)
- Add Council-specific logic to Scribe (keep Scribe pure)
- Create UI/dashboard for bridge management (future work)

**Success Metrics:**
- Server successfully initializes BridgeRegistry on startup
- Manifests are automatically discovered and registered
- Bridges activate without crashing server (graceful degradation)
- Health monitor runs in background without blocking
- Downstream projects can drop manifest in `.scribe/config/bridges/` and integrate
- ~40-50 lines of integration code added to server.py

**Research Verification:**
- Storage layer: ✅ COMPLETE (6 methods in sqlite.py lines 2475-2573)
- Bridge modules: ✅ COMPLETE (10 files with 75+ methods)
- Database schema: ✅ EXISTS (scribe_bridges table lines 1163-1180)
- Server integration: ❌ MISSING (critical gap - this project's focus)
- Confidence: 0.95 (verified via research document)
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
- Atomic document updates- Jinja2 templates with inheritance
- **Non-Functional Requirements:**
- Backwards-compatible file layout- Sandboxed template rendering
- **Assumptions:**
- Filesystem read/write access- Python runtime available
- **Risks & Mitigations:**
- User edits outside manage_docs- Template misuse causing errors


---
## 3. Architecture Overview
<!-- ID: architecture_overview -->
## 3. Architecture Overview
<!-- ID: architecture_overview -->

### Solution Summary
Add bridge initialization code to `server.py`'s `_startup()` function (lines 638-703) to instantiate BridgeRegistry, discover manifests, register bridges, activate them, and start health monitoring. The integration will be OPTIONAL (graceful degradation if bridges fail) and positioned after plugin initialization (line 661) but before agent context (line 664).

### Component Breakdown

**1. BridgeRegistry Initialization**
- **Purpose:** Central lifecycle manager for all bridges
- **Location:** `bridges/registry.py` (existing, 341 lines)
- **Integration Point:** server.py `_startup()`, after line 661
- **Interfaces:**
  - `__init__(storage_backend, config_dir)` - Constructor with storage backend
  - `discover_manifests()` → List[Path] - Finds `.yaml` files in config dir
  - `load_manifest(path)` → BridgeManifest - Parses and validates manifest
  - `register_bridge(manifest)` → str - Persists bridge to storage
  - `activate_bridge(bridge_id)` → None - Activates bridge lifecycle
- **Notes:** Already complete, just needs instantiation in server startup

**2. Manifest Discovery & Registration**
- **Purpose:** Auto-discover bridge manifests from filesystem
- **Discovery Path:** `.scribe/config/bridges/*.yaml`
- **Process Flow:**
  1. `discover_manifests()` scans directory
  2. For each manifest: `load_manifest(path)` parses YAML
  3. `register_bridge(manifest)` persists to storage (calls `storage.insert_bridge()`)
  4. `activate_bridge(bridge_id)` triggers plugin lifecycle hooks
- **Error Handling:** Individual manifest failures don't block server startup

**3. BridgeHealthMonitor Background Task**
- **Purpose:** Periodic health checks for active bridges
- **Location:** `bridges/health.py` (existing, 338 lines)
- **Integration:**
  - Create monitor with `BridgeHealthMonitor(registry, check_interval=60.0)`
  - Call `set_health_monitor(monitor)` to register global instance
  - Start background task: `await monitor.start()`
- **Interfaces:**
  - `start()` → None - Begins background monitoring loop
  - `stop()` → None - Graceful shutdown
  - `check_bridge_health(bridge_id)` → Dict - On-demand health check
- **Notes:** Non-blocking async task, continues running after startup

**4. Tool Registry Exposure (Already Exists)**
- **Current State:** Lines 682-702 in server.py already register bridge custom tools
- **No Changes Needed:** This part already works correctly
- **Purpose:** Expose bridge-provided tools to MCP clients (e.g., `council_mcp:custom_audit`)

### Data Flow Diagram

```
Server Startup Sequence (server.py _startup())
│
├─ [Line 646] Storage backend setup ✅ (existing)
│
├─ [Line 648-661] Plugin system initialization ✅ (existing)
│
├─ [NEW: After line 661] Bridge System Initialization
│   │
│   ├─ Create BridgeRegistry(storage_backend, config_dir)
│   │   └─ Storage: SQLite/Postgres backend (already complete)
│   │
│   ├─ Discover manifests from .scribe/config/bridges/
│   │   └─ Returns: List[Path] of .yaml files
│   │
│   ├─ For each manifest:
│   │   ├─ Load & validate manifest
│   │   ├─ Register bridge → storage.insert_bridge()
│   │   └─ Activate bridge → plugin.on_activate()
│   │
│   └─ Start BridgeHealthMonitor background task
│       └─ Runs async loop: check health every 60s
│
├─ [Line 664-680] Agent context initialization ✅ (existing)
│
└─ [Line 682-702] Bridge tool registration ✅ (existing)
```

### External Integrations

**Storage Backend (`storage/sqlite.py`):**
- `insert_bridge()` - Persist bridge registration (line 2475)
- `update_bridge_state()` - Track lifecycle state (line 2498)
- `update_bridge_health()` - Store health metrics (line 2519)
- `fetch_bridge()` - Retrieve bridge details (line 2539)
- `list_bridges()` - Query registered bridges (line 2557)
- All methods ✅ COMPLETE - no changes needed

**Bridge Modules (`bridges/` directory):**
- `registry.py` - BridgeRegistry class ✅ COMPLETE
- `manifest.py` - BridgeManifest dataclass ✅ COMPLETE
- `plugin.py` - BridgePlugin base class ✅ COMPLETE
- `health.py` - BridgeHealthMonitor ✅ COMPLETE
- `api.py` - BridgeToScribeAPI ✅ COMPLETE
- No module modifications needed

**Configuration:**
- Manifests live in: `.scribe/config/bridges/`
- Example: `.scribe/config/bridges/council_mcp.yaml` (114 lines)
- Downstream projects drop manifest here and restart server

### Design Decisions & Trade-offs

**Decision 1: Initialization Placement (After Plugins, Before Agents)**
- **Rationale:** Bridges may depend on plugins (vector search) but agents may use bridges
- **Trade-off:** Can't use bridges before agent context exists, but acceptable sequencing
- **Alternative Rejected:** Initialize bridges last (would delay tool registration)

**Decision 2: Graceful Degradation on Bridge Failures**
- **Rationale:** Scribe must work even if bridges fail (optional feature)
- **Implementation:** Wrap bridge init in try/except, print warning, continue startup
- **Trade-off:** Silent failures possible, but server availability prioritized

**Decision 3: Background Health Monitoring**
- **Rationale:** Don't block startup waiting for health checks
- **Implementation:** `asyncio.create_task()` for monitor.start()
- **Trade-off:** Health failures detected after startup, not before

**Decision 4: No Admin CLI in This Phase**
- **Rationale:** Manual bridge management not MVP requirement
- **Alternative:** Could add `scribe-admin bridge list/activate/health` commands
- **Deferred:** Future enhancement, not blocking for Council MCP integration
<!-- ID: detailed_design -->
## 4. Detailed Design
<!-- ID: detailed_design -->

### Subsystem 1: BridgeRegistry Initialization

**Purpose:** Create central registry and wire to storage backend

**Implementation Pseudocode:**
```python
# Location: server.py _startup(), after line 661

if BRIDGES_AVAILABLE and storage_backend:
    try:
        from scribe_mcp.bridges.registry import BridgeRegistry
        from scribe_mcp.bridges.health import BridgeHealthMonitor, set_health_monitor
        from pathlib import Path
        
        # Create registry with storage backend
        config_dir = Path(".scribe/config/bridges")
        bridge_registry = BridgeRegistry(
            storage_backend=storage_backend,
            config_dir=config_dir
        )
        
        print("🌉 BridgeRegistry initialized")
    except Exception as e:
        print(f"⚠️  Bridge system initialization failed: {e}")
        print("   💡 Continuing without bridges (downstream integrations unavailable)")
        bridge_registry = None
```

**Interfaces:**
- Input: `storage_backend` (StorageBackend instance)
- Output: `bridge_registry` (BridgeRegistry instance or None)
- Storage Calls: None at init (just object creation)

**Error Handling:**
- ImportError: BRIDGES_AVAILABLE = False at top of file, skip entire block
- Registry creation error: Catch exception, print warning, set None, continue startup
- Rationale: Bridges are optional feature, server must work without them

### Subsystem 2: Manifest Discovery & Registration Loop

**Purpose:** Auto-discover manifests from filesystem and register to storage

**Implementation Pseudocode:**
```python
# Continues from Subsystem 1, inside try block

if bridge_registry:
    # Discover manifest files
    manifests = bridge_registry.discover_manifests()
    
    if manifests:
        registered_count = 0
        for manifest_path in manifests:
            try:
                # Load and validate manifest
                manifest = bridge_registry.load_manifest(manifest_path)
                
                # Register bridge (persists to storage)
                bridge_id = await bridge_registry.register_bridge(manifest)
                
                # Activate bridge (calls plugin.on_activate())
                await bridge_registry.activate_bridge(bridge_id)
                
                registered_count += 1
                print(f"   ✅ Registered & activated bridge: {bridge_id}")
            except Exception as e:
                print(f"   ⚠️  Failed to register {manifest_path.name}: {e}")
                # Continue with next manifest
        
        print(f"🌉 Bridge system initialized ({registered_count}/{len(manifests)} bridges active)")
    else:
        print("🌉 Bridge system initialized (no manifests found)")
```

**Interfaces:**
- `discover_manifests()` → List[Path] - Scans `.scribe/config/bridges/*.yaml`
- `load_manifest(path)` → BridgeManifest - Parses YAML, validates schema
- `register_bridge(manifest)` → str - Calls `storage.insert_bridge()`, returns bridge_id
- `activate_bridge(bridge_id)` → None - Loads plugin, calls `on_activate()` hook

**Storage Calls:**
- `storage.insert_bridge()` - Called by register_bridge() for each manifest
- `storage.update_bridge_state()` - Called by activate_bridge() to set state="active"
- `storage.update_bridge_health()` - Called by activate_bridge() with initial health

**Error Handling:**
- Per-manifest try/except: Individual failures don't crash server
- Missing manifest directory: discover_manifests() returns [], print "no manifests found"
- Invalid YAML: load_manifest() raises, caught, logged, continue loop
- Storage failure: register_bridge() raises, caught, logged, continue loop

### Subsystem 3: Health Monitor Background Task

**Purpose:** Start async health monitoring loop for active bridges

**Implementation Pseudocode:**
```python
# Continues from Subsystem 2, inside try block

if bridge_registry:
    # Create health monitor
    health_monitor = BridgeHealthMonitor(
        registry=bridge_registry,
        check_interval=60.0  # Check every 60 seconds
    )
    
    # Register global instance (for other code to access)
    set_health_monitor(health_monitor)
    
    # Start background task (non-blocking)
    asyncio.create_task(health_monitor.start())
    
    print("🏥 Bridge health monitor started (60s interval)")
```

**Interfaces:**
- `BridgeHealthMonitor.__init__(registry, check_interval)` - Constructor
- `set_health_monitor(monitor)` - Registers global singleton
- `monitor.start()` → None - Async loop: check health, update storage, sleep, repeat

**Background Task Behavior:**
- Runs indefinitely in asyncio event loop
- Each iteration: call `registry.check_health()` for each active bridge
- Updates storage via `storage.update_bridge_health()`
- Sleeps for check_interval seconds
- Non-blocking: doesn't delay server startup

**Error Handling:**
- Monitor creation error: Caught in outer try/except, server continues
- Runtime errors in monitor loop: Caught internally, logged, loop continues
- Bridge health check failure: Logged, state updated to "error", other bridges unaffected

### Subsystem 4: Integration with Existing Tool Registration (No Changes)

**Current State:** Lines 682-702 already handle bridge tool registration

**How It Works:**
```python
# Already exists in server.py
if BRIDGES_AVAILABLE:
    tool_registry = get_tool_registry()  # Singleton from bridges.tools
    custom_tools = tool_registry.list_all_custom_tools()
    
    for tool_info in custom_tools:
        full_name = tool_info["full_name"]  # e.g., "council_mcp:custom_audit"
        bridge_id = tool_info["bridge_id"]
        tool_name = tool_info["tool_name"]
        
        impl = tool_registry.get_custom_tool(bridge_id, tool_name)
        if impl:
            Server._scribe_tool_registry[full_name] = impl
            print(f"🔧 Registered bridge tool: {full_name}")
```

**Notes:**
- This code runs AFTER bridge registration (lines 664-680 in new design)
- get_tool_registry() returns singleton that bridges populate during activation
- No modifications needed - existing code already handles this correctly

### Implementation Notes

**Estimated Code Size:**
- Subsystem 1 (Registry init): ~15 lines
- Subsystem 2 (Discovery/registration): ~20 lines
- Subsystem 3 (Health monitor): ~10 lines
- Total: ~45 lines (matches research estimate of 40-50)

**Async/Await Requirements:**
- `register_bridge()` - async (calls storage)
- `activate_bridge()` - async (calls plugin hooks)
- `health_monitor.start()` - async (background loop)
- All must be awaited properly in _startup()

**Import Requirements:**
- `from scribe_mcp.bridges.registry import BridgeRegistry`
- `from scribe_mcp.bridges.health import BridgeHealthMonitor, set_health_monitor`
- `from pathlib import Path`
- `import asyncio` (already imported in server.py)

**Configuration:**
- Config dir: `.scribe/config/bridges/` (hardcoded, reasonable default)
- Check interval: 60.0 seconds (hardcoded, can be env var later)
- No additional settings needed

### Error Recovery Strategies

**Scenario 1: No manifests found**
- Impact: No bridges registered
- Behavior: Print "no manifests found", continue startup
- Downstream: Server works normally, bridge tools unavailable

**Scenario 2: Invalid manifest YAML**
- Impact: Single bridge fails to load
- Behavior: Print warning, skip that manifest, continue with others
- Downstream: Other bridges work fine

**Scenario 3: Storage failure during registration**
- Impact: Bridge not persisted to database
- Behavior: Caught in per-manifest try/except, logged, continue loop
- Downstream: Failed bridge not available, others work

**Scenario 4: Bridge activation failure**
- Impact: Bridge registered but not active
- Behavior: Exception caught, bridge state remains "registered" not "active"
- Downstream: Bridge exists in storage but won't process hooks or provide tools

**Scenario 5: Health monitor crashes**
- Impact: No health tracking
- Behavior: Exception caught, print warning, continue startup
- Downstream: Server works, bridges work, just no health monitoring

### Testing Strategy (Coder Phase)

**Unit Tests:**
- Mock storage backend, test registry initialization
- Mock manifest files, test discovery logic
- Test error handling for each subsystem independently

**Integration Tests:**
- Place test manifest in `.scribe/config/bridges/test_bridge.yaml`
- Start server, verify bridge registered in storage
- Verify health monitor task running
- Verify bridge tools exposed to MCP

**Manual QA:**
- Test with no manifests (clean config dir)
- Test with invalid YAML manifest
- Test with valid Council MCP manifest
- Verify server continues if bridge fails
<!-- ID: directory_structure -->
```
/home/austin/projects/MCP_SPINE/scribe_mcp/docs/dev_plans/bridge_api_hardening
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