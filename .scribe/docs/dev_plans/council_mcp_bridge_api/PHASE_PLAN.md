---
id: council_mcp_bridge_api-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 council_mcp_bridge_api"
doc_name: PHASE_PLAN
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

# ⚙️ Phase Plan — council_mcp_bridge_api
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-12 02:48:54 UTC

> Execution roadmap for council_mcp_bridge_api.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview

This implementation follows a 5-phase incremental approach, where each phase builds on verified previous work:

**Phase 1: Core Bridge Registry** (Foundation)
- Bridge manifest schema and validation
- BridgePlugin base class
- BridgeRegistry with load/register/unregister
- Storage layer extensions (scribe_bridges table)
- Configuration loading

**Phase 2: Bridge Hooks** (Bidirectional Communication)
- BridgeHookPlugin extending HookPlugin
- Hook registration per bridge
- BridgeToScribeAPI for bridge→Scribe calls
- Error isolation and timeout handling

**Phase 3: Bridge-Managed Projects** (Project Ownership)
- Project creation via BridgeToScribeAPI
- Project namespacing (prefix/tagging)
- Bridge metadata injection
- BridgePolicyPlugin for access control

**Phase 4: Tool Extension** (Tool Wrapping)
- BridgeToolWrapper class
- BridgeToolRegistry
- Custom tool registration
- MCP server integration

**Phase 5: Advanced Features** (Health Monitoring & Admin)
- BridgeHealthMonitor
- Admin CLI commands (register, activate, deactivate, list, health)
- Documentation for external bridge authors
- Example bridge implementation

**Dependencies:**
- Phase 2 depends on Phase 1 (needs registry infrastructure)
- Phase 3 depends on Phase 2 (needs API abstraction)
- Phase 4 depends on Phase 1 (needs registry but not hooks)
- Phase 5 depends on all previous phases (integrates everything)
<!-- ID: phase_0 -->
## Phase 1: Core Bridge Registry (Foundation)

**Objective:** Establish bridge infrastructure with manifest-based configuration and persistent registry.

**Task Packages:**

### Task 1.1: Bridge Manifest Schema
**Scope**: Create manifest dataclasses and validation
**Files to Modify**: `bridges/manifest.py` (new)
**Dependencies**: None

**Specifications:**
1. Create `BridgeState` enum (REGISTERED, ACTIVE, INACTIVE, ERROR, UNREGISTERED)
2. Create dataclasses: `LogTypeConfig`, `HookConfig`, `BridgeProjectConfig`, `BridgeValidationConfig`, `BridgeManifest`
3. Add validation methods to BridgeManifest:
   - `validate_schema()` - check required fields
   - `to_json()` / `from_json()` - serialization
   - `expand_env_vars()` - expand ${VAR} in api_key

**Verification:**
- [ ] All dataclasses have proper type hints
- [ ] Validation catches missing required fields
- [ ] JSON serialization round-trips correctly
- [ ] Environment variable expansion works

**Out of Scope:**
- YAML loading (handled in Task 1.3)
- Hook execution (Phase 2)

---

### Task 1.2: BridgePlugin Base Class
**Scope**: Create abstract base class for bridge plugins
**Files to Modify**: `bridges/plugin.py` (new)
**Dependencies**: Task 1.1 (needs BridgeManifest)

**Specifications:**
1. Create `BridgePlugin(HookPlugin, ABC)` class
2. Constructor accepts `manifest: BridgeManifest`, `api: BridgeToScribeAPI`
3. Abstract methods: `on_activate()`, `on_deactivate()`, `health_check()`
4. Optional hook methods: `pre_append()`, `post_append()`
5. State tracking with `self.state: BridgeState`

**Verification:**
- [ ] BridgePlugin extends HookPlugin correctly
- [ ] Abstract methods must be implemented by subclasses
- [ ] Constructor initializes manifest, api, state
- [ ] Hook methods have correct signatures

**Out of Scope:**
- Actual hook execution (Phase 2)
- Health monitoring (Phase 5)

---

### Task 1.3: BridgeRegistry
**Scope**: Registry for loading, registering, and managing bridges
**Files to Modify**: `bridges/registry.py` (new)
**Dependencies**: Task 1.1, 1.2 (needs manifest and plugin)

**Specifications:**
1. Create `BridgeRegistry(PluginRegistry)` class
2. Methods:
   - `load_manifest(path: str) -> BridgeManifest` - load and validate YAML
   - `register_bridge(manifest, plugin_class) -> str` - register new bridge
   - `activate_bridge(bridge_id: str)` - transition to ACTIVE
   - `deactivate_bridge(bridge_id: str)` - transition to INACTIVE
   - `unregister_bridge(bridge_id: str)` - remove bridge
   - `list_bridges(state: Optional[str]) -> List[Dict]` - list all bridges
3. Bridge lifecycle: REGISTERED → ACTIVE → INACTIVE/ERROR → UNREGISTERED
4. Persist bridge state to database via StorageBackend

**Verification:**
- [ ] YAML manifest loads and validates
- [ ] Bridge registration persists to database
- [ ] State transitions work correctly
- [ ] Multiple bridges can coexist
- [ ] Unregistration removes bridge from memory and marks DB

**Out of Scope:**
- Hook registration (Phase 2)
- Health monitoring (Phase 5)

---

### Task 1.4: Storage Layer Extensions
**Scope**: Add bridge storage methods to StorageBackend
**Files to Modify**: 
- `storage/base.py` (add abstract methods)
- `storage/sqlite.py` (implement for SQLite)
**Dependencies**: Task 1.1 (needs BridgeManifest for JSON storage)

**Specifications:**
1. Add to `storage/base.py`:
   - `insert_bridge(bridge_id, name, version, manifest_json, state)`
   - `update_bridge_state(bridge_id, state)`
   - `update_bridge_health(bridge_id, health_json, error)`
   - `fetch_bridge(bridge_id) -> Optional[Dict]`
   - `list_bridges(state: Optional[str]) -> List[Dict]`
   - `delete_bridge(bridge_id)`

2. Implement in `storage/sqlite.py`:
   - Create `scribe_bridges` table in `_initialise()`
   - Implement all abstract methods with proper SQL

**Verification:**
- [ ] scribe_bridges table created on initialization
- [ ] Bridge CRUD operations work correctly
- [ ] Indexes on state and last_health_check exist
- [ ] JSON manifest stored and retrieved correctly

**Out of Scope:**
- PostgreSQL implementation (can be added later)
- Bridge-managed projects (Phase 3)

---

### Task 1.5: Configuration Loading
**Scope**: Load bridge manifests from `.scribe/config/bridges/*.yaml`
**Files to Modify**: 
- `bridges/registry.py` (add discovery method)
- `server.py` (initialize BridgeRegistry)
**Dependencies**: Task 1.3 (needs BridgeRegistry)

**Specifications:**
1. Add to BridgeRegistry:
   - `discover_manifests(config_dir: str) -> List[Path]` - find all YAML files
   - `load_all_manifests() -> List[BridgeManifest]` - load discovered manifests
2. Modify `server.py`:
   - Initialize BridgeRegistry after storage backend
   - Call `discover_manifests()` and `load_all_manifests()` on startup
   - Store registry globally for access by tools

**Verification:**
- [ ] All YAML files in .scribe/config/bridges/ discovered
- [ ] Valid manifests loaded successfully
- [ ] Invalid manifests logged as errors (don't crash server)
- [ ] BridgeRegistry accessible from tools

**Out of Scope:**
- Hot-reload (can be added later)
- Bridge activation (manual via CLI in Phase 5)

**Estimated Complexity**: Medium
**Estimated Time**: 2-3 implementation sessions
<!-- ID: phase_1 -->
## Phase 2: Bridge Hooks (Bidirectional Communication)

**Objective:** Enable bridges to receive Scribe events and call Scribe APIs.

**Task Packages:**

### Task 2.1: BridgeToScribeAPI
**Scope**: API interface for bridge→Scribe calls
**Files to Modify**: `bridges/api.py` (new), `bridges/policy.py` (new)
**Dependencies**: Phase 1 complete (needs BridgeManifest)

**Specifications:**
1. Create `BridgeToScribeAPI` class:
   - Constructor: `__init__(storage, manifest)`
   - Methods: `append_entry()`, `create_project()`, `query_entries()`
   - Each method enforces permissions via `BridgePolicyPlugin`
   - Injects bridge metadata into all operations

2. Create `BridgePolicyPlugin` class:
   - Methods: `can_append_entry()`, `can_create_projects()`, `can_read_entries()`
   - Checks manifest.permissions list
   - Validates log_type against allowed_log_types
   - Checks forbidden_projects list

**Verification:**
- [ ] Permission checks block unauthorized operations
- [ ] Bridge metadata injected correctly
- [ ] All API calls logged with bridge_id
- [ ] Policy enforces allowed_log_types and forbidden_projects

**Out of Scope:**
- Tool wrapping (Phase 4)

---

### Task 2.2: Hook Integration
**Scope**: Integrate bridge hooks into append_entry
**Files to Modify**: `tools/append_entry.py`, `bridges/hooks.py` (new)
**Dependencies**: Task 2.1 (needs BridgeToScribeAPI)

**Specifications:**
1. Create `BridgeHookPlugin` extending `BridgePlugin`:
   - Implements pre_append/post_append hooks
   - Handles timeout enforcement
   - Isolates errors per bridge

2. Modify `tools/append_entry.py`:
   - Before writing entry: call all registered `pre_append` hooks
   - After writing entry: call all registered `post_append` hooks
   - Critical hooks block on failure; non-critical log errors
   - Pass hook results through chain

**Verification:**
- [ ] pre_append hooks receive correct parameters
- [ ] post_append hooks receive entry_id and full entry
- [ ] Critical hook failure blocks append_entry
- [ ] Non-critical hook failure logged but doesn't block
- [ ] Timeout enforcement works (hooks killed after timeout)

**Out of Scope:**
- Other tool hooks (can be added incrementally)

---

### Task 2.3: Error Isolation & Timeout
**Scope**: Ensure bridge failures don't crash Scribe
**Files to Modify**: `bridges/hooks.py`, `bridges/security.py` (new)
**Dependencies**: Task 2.2 (needs hook integration)

**Specifications:**
1. Create `BridgeSecurityManager`:
   - `execute_with_timeout(func, timeout)` - run with timeout
   - `isolate_errors(func)` - catch and log all exceptions
   - Bridge errors logged but don't propagate

2. Wrap all hook calls with security manager:
   - Timeout enforcement (configurable per hook)
   - Exception catching and logging
   - State transition to ERROR on repeated failures

**Verification:**
- [ ] Bridge timeout doesn't crash append_entry
- [ ] Bridge exception doesn't crash append_entry
- [ ] Repeated failures transition bridge to ERROR state
- [ ] Other bridges continue working when one fails

**Out of Scope:**
- Health monitoring (Phase 5)

**Estimated Complexity**: Medium-High
**Estimated Time**: 2-3 implementation sessions

---

## Phase 3: Bridge-Managed Projects (Project Ownership)

**Objective:** Allow bridges to create and manage projects with automatic namespacing.

**Task Packages:**

### Task 3.1: Project Namespacing
**Scope**: Add bridge metadata to projects
**Files to Modify**: `tools/set_project.py`, `storage/base.py`, `storage/sqlite.py`
**Dependencies**: Phase 2 complete (needs BridgeToScribeAPI)

**Specifications:**
1. Extend `scribe_projects` table:
   - Add `bridge_id TEXT` column
   - Add `bridge_managed BOOLEAN` column
   - Migration in SQLiteStorage._initialise()

2. Modify `set_project()`:
   - Accept optional `bridge_id` and `bridge_managed` kwargs
   - Store in project state
   - Apply namespace strategy (prefix/tag) if bridge_managed=True

3. Update BridgeToScribeAPI.create_project():
   - Implement prefix strategy (prepend bridge_id_ or custom prefix)
   - Implement tag strategy (add bridge_id to tags)
   - Inject bridge metadata into project defaults

**Verification:**
- [ ] Bridge-created projects have bridge_id set
- [ ] Prefix strategy works (e.g., "council_my_project")
- [ ] Tag strategy works (bridge_id in tags)
- [ ] Bridge metadata stored in project state

**Out of Scope:**
- Access control (Task 3.2)

---

### Task 3.2: Access Control
**Scope**: Prevent cross-bridge project modification
**Files to Modify**: `bridges/policy.py`, `tools/set_project.py`, `tools/append_entry.py`
**Dependencies**: Task 3.1 (needs bridge_id in projects)

**Specifications:**
1. Extend `BridgePolicyPlugin`:
   - `can_modify_project(project_name, bridge_id)` - check ownership
   - Allow if project.bridge_id matches current bridge OR project not bridge-managed
   - Deny if project owned by different bridge

2. Modify tools to enforce access control:
   - `set_project()` - check before modifying bridge-managed projects
   - `append_entry()` - check before appending to bridge-managed projects
   - Log access violations with bridge_id

**Verification:**
- [ ] Bridge can modify its own projects
- [ ] Bridge blocked from modifying other bridges' projects
- [ ] Non-bridge-managed projects accessible to all
- [ ] Access violations logged

**Out of Scope:**
- Fine-grained permissions (can be added later)

**Estimated Complexity**: Medium
**Estimated Time**: 1-2 implementation sessions

---

## Phase 4: Tool Extension (Tool Wrapping)

**Objective:** Allow bridges to wrap existing tools or register custom ones.

**Task Packages:**

### Task 4.1: BridgeToolWrapper
**Scope**: Wrapper for existing Scribe tools with pre/post hooks
**Files to Modify**: `bridges/tools.py` (new)
**Dependencies**: Phase 2 complete (needs hook infrastructure)

**Specifications:**
1. Create `BridgeToolWrapper`:
   - Wraps any Scribe tool function
   - Adds optional `pre_call(args, kwargs)` hook
   - Adds optional `post_call(result)` hook
   - Returns wrapped function with same signature

2. Create `BridgeToolRegistry`:
   - `register_tool(name, func)` - register custom tool
   - `wrap_tool(name, wrapper)` - wrap existing tool
   - `list_tools(bridge_id)` - list tools per bridge

**Verification:**
- [ ] Tool wrapping preserves function signature
- [ ] pre_call hook can modify arguments
- [ ] post_call hook receives result
- [ ] Wrapped tools work via MCP

**Out of Scope:**
- MCP server integration (Task 4.2)

---

### Task 4.2: MCP Server Integration
**Scope**: Expose bridge tools via MCP protocol
**Files to Modify**: `server.py`, `bridges/tools.py`
**Dependencies**: Task 4.1 (needs BridgeToolWrapper)

**Specifications:**
1. Modify `server.py`:
   - Discover bridge tools from BridgeToolRegistry
   - Register bridge tools with MCP server
   - Prefix with bridge_id (e.g., "council_mcp:custom_tool")

2. Add tool metadata:
   - Tool descriptions from bridge manifest
   - Parameter schemas
   - Permission requirements

**Verification:**
- [ ] Bridge tools visible in MCP tool list
- [ ] Bridge tools callable via MCP protocol
- [ ] Tool permissions enforced
- [ ] Multiple bridges' tools coexist

**Out of Scope:**
- Complex tool chaining (can be added later)

**Estimated Complexity**: Medium
**Estimated Time**: 1-2 implementation sessions

---

## Phase 5: Advanced Features (Health Monitoring & Admin)

**Objective:** Add health monitoring, admin CLI, and documentation.

**Task Packages:**

### Task 5.1: BridgeHealthMonitor
**Scope**: Periodic health checks and state management
**Files to Modify**: `bridges/health.py` (new), `server.py`
**Dependencies**: All previous phases complete

**Specifications:**
1. Create `BridgeHealthMonitor`:
   - `check_bridge_health(bridge_id)` - call bridge.health_check()
   - `run_periodic_checks(interval)` - async loop
   - State transitions: ACTIVE → ERROR on failure
   - Recovery: ERROR → ACTIVE on successful health check

2. Integrate with server:
   - Start health monitor on MCP server startup
   - Configurable check interval (default: 5 minutes)
   - Log all health check results

**Verification:**
- [ ] Health checks run periodically
- [ ] Unhealthy bridges transition to ERROR
- [ ] Recovered bridges transition back to ACTIVE
- [ ] Health check doesn't block server operations

---

### Task 5.2: Admin CLI Commands
**Scope**: CLI for bridge management
**Files to Modify**: `scripts/scribe_admin.py` (new)
**Dependencies**: Task 5.1 (needs complete bridge system)

**Specifications:**
1. Create admin commands:
   - `scribe-admin bridge register --manifest <path>` - register bridge
   - `scribe-admin bridge activate <bridge_id>` - activate bridge
   - `scribe-admin bridge deactivate <bridge_id>` - deactivate bridge
   - `scribe-admin bridge list` - list all bridges with state
   - `scribe-admin bridge status <bridge_id>` - detailed status
   - `scribe-admin bridge health <bridge_id>` - run health check
   - `scribe-admin bridge logs <bridge_id>` - view bridge logs

2. Output formatting:
   - Table format for list
   - Detailed format for status
   - Color-coded state indicators

**Verification:**
- [ ] All commands work correctly
- [ ] State transitions reflected immediately
- [ ] Error messages are clear
- [ ] Help text is comprehensive

---

### Task 5.3: Documentation & Examples
**Scope**: Documentation for external bridge authors
**Files to Modify**: `docs/BRIDGE_DEVELOPMENT.md` (new), `examples/council_bridge.py` (new)
**Dependencies**: All implementation complete

**Specifications:**
1. Create comprehensive documentation:
   - Bridge manifest schema reference
   - BridgePlugin API reference
   - Hook lifecycle explanation
   - Security considerations
   - Example manifests

2. Create example bridge implementation:
   - Simple Council MCP bridge
   - Demonstrates all features (hooks, tools, projects)
   - Well-commented code
   - README with setup instructions

**Verification:**
- [ ] External developer can create bridge from docs
- [ ] Example bridge works end-to-end
- [ ] All features documented with examples
- [ ] Security best practices included

**Estimated Complexity**: Low-Medium
**Estimated Time**: 1-2 implementation sessions
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