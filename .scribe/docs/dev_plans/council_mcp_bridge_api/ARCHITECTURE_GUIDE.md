---
id: council_mcp_bridge_api-architecture-guide
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 council_mcp_bridge_api"
doc_name: ARCHITECTURE_GUIDE
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

# 🏗️ Architecture Guide — council_mcp_bridge_api
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-12 02:48:54 UTC

> Architecture guide for council_mcp_bridge_api.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## Problem Statement

**Context:**

MCP_SPINE currently has a plugin architecture designed for internal Scribe extensions, but lacks a formalized system for integrating external MCP servers (like Council MCP) as **integration partners**. External MCPs need:

1. **Bidirectional communication** with Scribe (receive Scribe events, call Scribe APIs)
2. **Custom configuration** per bridge (log types, validation rules, hooks)
3. **Project management** capabilities (bridge-managed projects with namespacing)
4. **Tool extension** patterns (wrap/extend Scribe tools, expose custom tools)
5. **Security isolation** (prevent cross-bridge interference, enforce access control)
6. **Health monitoring** (detect unhealthy bridges, automatic recovery)

**Current Gap:**

The existing PluginRegistry is designed for:
- Internal Scribe plugins (VectorIndexer, etc.)
- Single-direction extension (plugins extend Scribe, not vice versa)
- No external configuration or validation
- No project ownership concepts

**Goals:**

1. **Bridge Registry System**: Formal registry for external MCP integrations with manifest-based configuration
2. **Bidirectional Hooks**: Bridges receive Scribe lifecycle events AND can call Scribe APIs
3. **Bridge-Managed Projects**: Projects owned by bridges with automatic namespacing and metadata
4. **Tool Extension**: Bridges can wrap existing tools or register new ones
5. **Security & Isolation**: Per-bridge policies, access control, error isolation
6. **Health Monitoring**: Automatic health checks, state transitions, recovery

**Success Criteria:**

- Council MCP can register as a bridge with custom log types and hooks
- Bridge receives callbacks on Scribe events (pre_append, post_append, etc.)
- Bridge can create projects prefixed with bridge_id for namespacing
- Bridge can call Scribe APIs without direct import coupling
- Multiple bridges coexist without interference
- Unhealthy bridges automatically transition to ERROR state
<!-- ID: requirements_constraints -->
## Requirements & Constraints

**Functional Requirements:**

1. **Bridge Registration**:
   - Load bridge manifests from `.scribe/config/bridges/*.yaml`
   - Validate manifest schema (bridge_id, version, permissions, hooks)
   - Register bridges programmatically via BridgeRegistry API
   - Persist bridge state and metadata to database

2. **Bidirectional Hooks**:
   - Bridges receive callbacks on Scribe lifecycle events (pre_append, post_append, etc.)
   - Bridges can call Scribe APIs via BridgeToScribeAPI (append_entry, create project, query)
   - Critical hooks block operations on failure; non-critical hooks log errors

3. **Bridge-Managed Projects**:
   - Bridges can create projects via API with automatic namespacing (prefix or tags)
   - Bridge metadata injected into project state
   - Access control prevents cross-bridge project modification

4. **Tool Extension**:
   - Bridges can wrap existing Scribe tools with pre/post hooks
   - Bridges can register custom tools exposed via MCP
   - Tool access control enforced per bridge

5. **Security & Isolation**:
   - Per-bridge API keys and permission scopes
   - Bridge errors isolated (no cascading failures)
   - Timeout enforcement on bridge operations

6. **Health Monitoring**:
   - Periodic health checks with configurable intervals
   - Automatic state transitions (ACTIVE → ERROR → INACTIVE)
   - Bridge recovery mechanisms

**Non-Functional Constraints:**

1. **Backward Compatibility**: Existing Scribe tools and plugins must continue working
2. **Performance**: Bridge hooks must not degrade append_entry performance >10%
3. **Security**: Bridges must not access other bridges' data or bypass Scribe policies
4. **Maintainability**: Bridge interface must be stable (minimal breaking changes)
5. **Documentation**: External bridge authors need comprehensive docs and examples

**Technical Constraints:**

1. **Extends PluginRegistry**: BridgeRegistry inherits from PluginRegistry for consistency
2. **Storage Backend Agnostic**: Works with both SQLite and PostgreSQL
3. **MCP Protocol**: Bridge tools follow MCP protocol standards
4. **Python 3.10+**: Uses modern Python features (dataclasses, type hints, async)
<!-- ID: architecture_overview -->
## Architecture Overview

**System Design:**

The Bridge Registry system extends Scribe's existing plugin architecture to support external MCP integrations. It follows these design principles:

1. **Manifest-Based Configuration**: Each bridge defines capabilities via YAML manifest
2. **Registry Pattern**: BridgeRegistry manages bridge lifecycle (register, activate, monitor, unregister)
3. **Plugin Inheritance**: BridgePlugin extends HookPlugin for consistency
4. **API Abstraction**: BridgeToScribeAPI provides clean interface for bridge→Scribe calls
5. **Security by Design**: Per-bridge permissions, isolated execution, timeout enforcement
6. **Observable System**: Health monitoring, state tracking, audit logging

**High-Level Flow:**

```
1. Bridge Manifest (.yaml) → BridgeRegistry.load_manifest()
2. BridgeRegistry validates manifest → creates BridgePlugin instance
3. BridgePlugin registers hooks (pre_append, post_append, etc.)
4. Scribe event occurs → HookManager dispatches to bridge hooks
5. Bridge hook executes → can call BridgeToScribeAPI methods
6. Health monitor periodically checks bridge status
7. State transitions tracked in scribe_bridges table
```

**Component Relationships:**

```
BridgeRegistry (extends PluginRegistry)
    ├── Loads: BridgeManifest (.yaml configs)
    ├── Creates: BridgePlugin instances
    ├── Manages: Bridge lifecycle & state
    └── Monitors: BridgeHealthMonitor

BridgePlugin (extends HookPlugin)
    ├── Implements: HookPlugin interface
    ├── Registers: Bridge-specific hooks
    ├── Uses: BridgeToScribeAPI for callbacks
    └── Enforces: BridgePolicyPlugin rules

BridgeToScribeAPI
    ├── Provides: append_entry(), create_project(), query_entries()
    ├── Enforces: Permission checks via BridgePolicyPlugin
    └── Logs: All API calls for audit

BridgeToolWrapper
    ├── Wraps: Existing Scribe tools
    ├── Adds: Pre/post hooks for bridge extensions
    └── Registers: Custom tools via BridgeToolRegistry
```

**Data Flow:**

```
External MCP (Council) ↔ Bridge Manifest
                         ↓
                    BridgeRegistry
                         ↓
                    BridgePlugin ← BridgeToScribeAPI
                         ↓
                    HookManager → Scribe Core (append_entry, set_project, etc.)
                         ↓
                    StorageBackend (scribe_projects, scribe_entries, scribe_bridges)
```
<!-- ID: detailed_design -->
## Detailed Design

### 1. Bridge Manifest Schema

**File:** `bridges/manifest.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

class BridgeState(Enum):
    REGISTERED = "registered"  # Initial registration
    ACTIVE = "active"          # Operational
    INACTIVE = "inactive"      # Temporarily disabled
    ERROR = "error"            # Health check failed
    UNREGISTERED = "unregistered"  # Removed

@dataclass
class LogTypeConfig:
    """Configuration for bridge-specific log types."""
    path_template: str  # e.g., "{docs_dir}/COUNCIL_LOG.md"
    required_meta: List[str]  # Required metadata fields
    format: str = "markdown"

@dataclass
class HookConfig:
    """Configuration for bridge hook registration."""
    hook_type: str  # pre_append, post_append, etc.
    critical: bool = False  # Block operation on failure?
    timeout_seconds: float = 5.0

@dataclass
class BridgeProjectConfig:
    """Configuration for bridge-managed projects."""
    namespace_strategy: str = "prefix"  # prefix|tag
    prefix: Optional[str] = None  # e.g., "council_"
    auto_tag: bool = True  # Automatically tag projects with bridge_id

@dataclass
class BridgeValidationConfig:
    """Validation rules for bridge operations."""
    max_append_size_kb: int = 100
    allowed_log_types: List[str] = field(default_factory=list)
    forbidden_projects: List[str] = field(default_factory=list)

@dataclass
class BridgeManifest:
    """Complete bridge configuration manifest."""
    bridge_id: str  # Unique identifier (e.g., "council_mcp")
    name: str  # Human-readable name
    version: str  # Semantic version
    description: str
    author: str
    
    # Configuration sections
    log_config: Dict[str, LogTypeConfig] = field(default_factory=dict)
    hooks: Dict[str, HookConfig] = field(default_factory=dict)
    project_config: BridgeProjectConfig = field(default_factory=BridgeProjectConfig)
    validation: BridgeValidationConfig = field(default_factory=BridgeValidationConfig)
    
    # Security
    api_key: Optional[str] = None
    permissions: List[str] = field(default_factory=list)  # read_entries, create_projects, etc.
    
    # Compatibility
    min_scribe_version: str = "2.1.0"
```

**Example Manifest (`.scribe/config/bridges/council_mcp.yaml`):**

```yaml
bridge_id: council_mcp
name: Council MCP Integration
version: 1.0.0
description: Bidirectional integration with Council MCP for protocol coordination
author: Council Team

log_config:
  council_events:
    path_template: "{docs_dir}/COUNCIL_LOG.md"
    required_meta: ["event_type", "council_session"]
    format: markdown

hooks:
  pre_append:
    hook_type: pre_append
    critical: false
    timeout_seconds: 3.0
  post_append:
    hook_type: post_append
    critical: false
    timeout_seconds: 2.0

project_config:
  namespace_strategy: prefix
  prefix: "council_"
  auto_tag: true

validation:
  max_append_size_kb: 50
  allowed_log_types: ["progress", "council_events"]
  forbidden_projects: ["scribe_mcp", "internal"]

permissions:
  - read_entries
  - append_entry
  - create_projects
  - query_entries

api_key: "${COUNCIL_BRIDGE_API_KEY}"
min_scribe_version: "2.1.0"
```

### 2. BridgePlugin Base Class

**File:** `bridges/plugin.py`

```python
from abc import ABC, abstractmethod
from plugins.hooks import HookPlugin
from bridges.manifest import BridgeManifest, BridgeState
from bridges.api import BridgeToScribeAPI

class BridgePlugin(HookPlugin, ABC):
    """Base class for all bridge plugins."""
    
    def __init__(self, manifest: BridgeManifest, api: BridgeToScribeAPI):
        super().__init__(
            name=manifest.bridge_id,
            version=manifest.version,
            priority=100  # Bridge hooks run after internal plugins
        )
        self.manifest = manifest
        self.api = api
        self.state = BridgeState.REGISTERED
    
    @abstractmethod
    async def on_activate(self) -> None:
        """Called when bridge transitions to ACTIVE state."""
        pass
    
    @abstractmethod
    async def on_deactivate(self) -> None:
        """Called when bridge transitions to INACTIVE state."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if bridge is healthy, False otherwise."""
        pass
    
    # Hook implementations (optional)
    async def pre_append(self, message: str, status: str, meta: dict) -> dict:
        """Called before append_entry. Return modified params or raise to block."""
        return {"message": message, "status": status, "meta": meta}
    
    async def post_append(self, entry_id: str, entry: dict) -> None:
        """Called after append_entry completes."""
        pass
```

### 3. BridgeRegistry

**File:** `bridges/registry.py`

```python
from typing import Dict, Optional
from plugins.registry import PluginRegistry
from bridges.manifest import BridgeManifest, BridgeState
from bridges.plugin import BridgePlugin
from bridges.api import BridgeToScribeAPI
from storage.base import StorageBackend
import yaml

class BridgeRegistry(PluginRegistry):
    """Registry for managing external MCP bridge integrations."""
    
    def __init__(self, storage: StorageBackend):
        super().__init__()
        self.storage = storage
        self.bridges: Dict[str, BridgePlugin] = {}
        self.api_factory = BridgeToScribeAPI
    
    async def load_manifest(self, path: str) -> BridgeManifest:
        """Load and validate bridge manifest from YAML."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        # Validation logic here
        return BridgeManifest(**data)
    
    async def register_bridge(self, manifest: BridgeManifest, plugin_class: type) -> str:
        """Register a new bridge."""
        api = self.api_factory(self.storage, manifest)
        plugin = plugin_class(manifest, api)
        
        # Persist to database
        await self.storage.insert_bridge(
            bridge_id=manifest.bridge_id,
            name=manifest.name,
            version=manifest.version,
            manifest_json=manifest.to_json(),
            state=BridgeState.REGISTERED.value
        )
        
        # Register hooks
        await self.register_plugin(plugin)
        self.bridges[manifest.bridge_id] = plugin
        
        return manifest.bridge_id
    
    async def activate_bridge(self, bridge_id: str) -> None:
        """Activate a registered bridge."""
        bridge = self.bridges.get(bridge_id)
        if not bridge:
            raise ValueError(f"Bridge {bridge_id} not found")
        
        await bridge.on_activate()
        bridge.state = BridgeState.ACTIVE
        await self.storage.update_bridge_state(bridge_id, BridgeState.ACTIVE.value)
    
    async def unregister_bridge(self, bridge_id: str) -> None:
        """Unregister and remove a bridge."""
        bridge = self.bridges.get(bridge_id)
        if bridge:
            await bridge.on_deactivate()
            await self.unregister_plugin(bridge.name)
            del self.bridges[bridge_id]
        
        await self.storage.update_bridge_state(bridge_id, BridgeState.UNREGISTERED.value)
```

### 4. BridgeToScribeAPI

**File:** `bridges/api.py`

```python
from typing import Dict, Any, Optional, List
from storage.base import StorageBackend
from bridges.manifest import BridgeManifest
from bridges.policy import BridgePolicyPlugin

class BridgeToScribeAPI:
    """API interface for bridges to call Scribe operations."""
    
    def __init__(self, storage: StorageBackend, manifest: BridgeManifest):
        self.storage = storage
        self.manifest = manifest
        self.policy = BridgePolicyPlugin(manifest)
    
    async def append_entry(
        self,
        message: str,
        status: str = "info",
        meta: Optional[Dict[str, Any]] = None,
        log_type: str = "progress",
        project: Optional[str] = None
    ) -> str:
        """Append entry via bridge (enforces permissions)."""
        # Permission check
        if not self.policy.can_append_entry():
            raise PermissionError(f"Bridge {self.manifest.bridge_id} lacks append_entry permission")
        
        # Validation
        if log_type not in self.manifest.validation.allowed_log_types:
            raise ValueError(f"Log type {log_type} not allowed for bridge")
        
        # Inject bridge metadata
        meta = meta or {}
        meta["bridge_id"] = self.manifest.bridge_id
        meta["bridge_version"] = self.manifest.version
        
        # Call core append_entry logic
        from tools.append_entry import append_entry
        return await append_entry(
            message=message,
            status=status,
            meta=meta,
            log_type=log_type,
            project=project
        )
    
    async def create_project(
        self,
        name: str,
        root: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a bridge-managed project."""
        if not self.policy.can_create_projects():
            raise PermissionError(f"Bridge {self.manifest.bridge_id} lacks create_projects permission")
        
        # Apply namespace strategy
        if self.manifest.project_config.namespace_strategy == "prefix":
            prefix = self.manifest.project_config.prefix or f"{self.manifest.bridge_id}_"
            if not name.startswith(prefix):
                name = f"{prefix}{name}"
        
        # Inject bridge metadata
        kwargs["bridge_id"] = self.manifest.bridge_id
        kwargs["bridge_managed"] = True
        
        from tools.set_project import set_project
        return await set_project(name=name, root=root, **kwargs)
    
    async def query_entries(
        self,
        project: Optional[str] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """Query entries (enforces permissions)."""
        if not self.policy.can_read_entries():
            raise PermissionError(f"Bridge {self.manifest.bridge_id} lacks read_entries permission")
        
        from tools.query_entries import query_entries
        return await query_entries(project=project, **filters)
```

### 5. Database Schema

**Storage Extension:**

```sql
-- New table for bridge registry
CREATE TABLE IF NOT EXISTS scribe_bridges (
    bridge_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'registered',
    health_json TEXT,
    registered_at TEXT NOT NULL,
    last_health_check TEXT,
    last_error TEXT
);

CREATE INDEX idx_bridge_state ON scribe_bridges(state);
CREATE INDEX idx_bridge_health ON scribe_bridges(last_health_check);

-- Extend scribe_projects with bridge metadata
ALTER TABLE scribe_projects ADD COLUMN bridge_id TEXT;
ALTER TABLE scribe_projects ADD COLUMN bridge_managed BOOLEAN DEFAULT 0;
```

**StorageBackend Methods:**

```python
# In storage/base.py
async def insert_bridge(self, bridge_id: str, name: str, version: str, 
                       manifest_json: str, state: str) -> None:
    """Insert a new bridge record."""
    pass

async def update_bridge_state(self, bridge_id: str, state: str) -> None:
    """Update bridge state."""
    pass

async def fetch_bridge(self, bridge_id: str) -> Optional[Dict[str, Any]]:
    """Fetch bridge by ID."""
    pass

async def list_bridges(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all bridges, optionally filtered by state."""
    pass
```
<!-- ID: directory_structure -->
## Directory Structure

```
scribe_mcp/
├── bridges/                          # NEW: Bridge infrastructure
│   ├── __init__.py
│   ├── manifest.py                   # BridgeManifest, configs
│   ├── plugin.py                     # BridgePlugin base class
│   ├── registry.py                   # BridgeRegistry
│   ├── hooks.py                      # BridgeHookPlugin
│   ├── api.py                        # BridgeToScribeAPI
│   ├── tools.py                      # BridgeToolWrapper, BridgeToolRegistry
│   ├── policy.py                     # BridgePolicyPlugin
│   ├── security.py                   # BridgeSecurityManager
│   └── health.py                     # BridgeHealthMonitor
│
├── .scribe/
│   └── config/
│       └── bridges/                  # NEW: Bridge configurations
│           ├── council_mcp.yaml      # Example bridge manifest
│           └── README.md             # Bridge configuration guide
│
├── storage/
│   ├── base.py                       # MODIFIED: Add bridge methods
│   ├── sqlite.py                     # MODIFIED: Implement bridge storage
│   └── postgres.py                   # MODIFIED: Implement bridge storage
│
├── plugins/
│   ├── registry.py                   # EXISTING: Base for BridgeRegistry
│   └── hooks.py                      # EXISTING: Base for BridgePlugin
│
├── tools/
│   ├── append_entry.py               # MODIFIED: Call bridge hooks
│   ├── set_project.py                # MODIFIED: Support bridge metadata
│   └── query_entries.py              # MODIFIED: Filter by bridge_id
│
└── server.py                         # MODIFIED: Initialize BridgeRegistry
```

**Key Changes:**

1. **New `bridges/` Directory**: Complete bridge infrastructure isolated from core
2. **New `.scribe/config/bridges/`**: YAML manifests for bridge configurations
3. **Storage Layer Extensions**: New table and methods for bridge management
4. **Tool Modifications**: Minimal changes to support bridge hooks and metadata
5. **Plugin Integration**: BridgeRegistry extends existing PluginRegistry pattern
<!-- ID: data_storage -->
## Data & Storage

**Storage Architecture:**

1. **scribe_bridges Table** (NEW):
   - **Primary Key**: `bridge_id` (unique identifier)
   - **Fields**: name, version, manifest_json, state, health_json, registered_at, last_health_check, last_error
   - **Indexes**: `idx_bridge_state`, `idx_bridge_health`
   - **Purpose**: Persistent bridge registry with state tracking

2. **scribe_projects Table** (MODIFIED):
   - **New Fields**: `bridge_id`, `bridge_managed`
   - **Purpose**: Track which bridges own which projects

3. **Bridge Configuration Files**:
   - **Location**: `.scribe/config/bridges/*.yaml`
   - **Format**: YAML manifests with BridgeManifest schema
   - **Validation**: Schema validated on load

**Data Flow:**

```
Bridge Manifest (YAML) → BridgeRegistry.load_manifest() → BridgeManifest (dataclass)
                                                          ↓
                                                   StorageBackend.insert_bridge()
                                                          ↓
                                                   scribe_bridges table
```

**Performance Considerations:**

- Bridge hooks add <10ms overhead to append_entry (enforced via timeout)
- Health checks run asynchronously (don't block operations)
- Bridge state cached in memory (avoid repeated DB reads)
- Manifest JSON stored for audit but not parsed on every operation

**Consistency Guarantees:**

- Bridge registration is atomic (transaction-based)
- State transitions logged for audit
- Bridge metadata in projects immutable after creation
- Failed hook operations rollback atomically
<!-- ID: testing_strategy -->
## Testing & Validation Strategy

**Unit Tests:**

1. **Bridge Manifest Validation** (`tests/test_bridge_manifest.py`):
   - Schema validation (required fields, types)
   - YAML parsing and deserialization
   - Invalid manifest rejection
   - Environment variable expansion

2. **BridgePlugin Base Class** (`tests/test_bridge_plugin.py`):
   - Lifecycle methods (on_activate, on_deactivate, health_check)
   - Hook registration and callback
   - State transitions
   - Error isolation

3. **BridgeRegistry** (`tests/test_bridge_registry.py`):
   - Bridge registration/unregistration
   - Manifest loading from YAML
   - State persistence
   - Multiple bridge coexistence

4. **BridgeToScribeAPI** (`tests/test_bridge_api.py`):
   - Permission enforcement
   - API call logging
   - Metadata injection
   - Error handling

**Integration Tests:**

1. **End-to-End Bridge Registration** (`tests/integration/test_bridge_lifecycle.py`):
   - Load manifest → Register → Activate → Health check → Deactivate → Unregister
   - Verify database state at each step

2. **Hook Execution** (`tests/integration/test_bridge_hooks.py`):
   - Pre/post append hooks
   - Critical vs non-critical hook failures
   - Timeout enforcement
   - Hook isolation (one bridge failure doesn't affect others)

3. **Bridge-Managed Projects** (`tests/integration/test_bridge_projects.py`):
   - Project creation via BridgeToScribeAPI
   - Namespace enforcement (prefix/tag)
   - Access control (cross-bridge isolation)

4. **Tool Extension** (`tests/integration/test_bridge_tools.py`):
   - Tool wrapping with pre/post hooks
   - Custom tool registration
   - MCP server exposure

**Acceptance Criteria:**

| Phase | Criteria | Test Coverage |
|-------|----------|---------------|
| Phase 1 | Bridge manifest loads and validates | Unit + Integration |
| Phase 1 | Bridge persists to database | Integration |
| Phase 2 | Bridge receives pre/post append callbacks | Integration |
| Phase 2 | Bridge can call Scribe APIs | Integration |
| Phase 3 | Bridge can create namespaced projects | Integration |
| Phase 3 | Access control prevents cross-bridge access | Integration |
| Phase 4 | Tool wrapping works | Integration |
| Phase 4 | Custom tools accessible via MCP | Integration |
| Phase 5 | Health checks detect unhealthy bridges | Integration |
| Phase 5 | State transitions work correctly | Integration |

**Test Environment:**

- SQLite backend for unit/integration tests
- Isolated temp directories for test projects
- Mock bridges for testing infrastructure
- Real Council MCP bridge for E2E validation
<!-- ID: deployment_operations -->
## Deployment & Operations

**Deployment Process:**

1. **Phase 1-2 (Foundation)**: Core bridge infrastructure
   - Deploy: `bridges/` module with manifest, plugin, registry, API
   - Migrate: Database schema changes (scribe_bridges table)
   - Test: Unit + integration tests pass
   - No bridge YAML required yet (infrastructure only)

2. **Phase 3 (Bridge-Managed Projects)**: Project management support
   - Deploy: Project creation enhancements in set_project
   - Migrate: scribe_projects table columns (bridge_id, bridge_managed)
   - Test: Project namespace enforcement

3. **Phase 4 (Tool Extension)**: Tool wrapping and custom tools
   - Deploy: BridgeToolWrapper and BridgeToolRegistry
   - No migration needed (tool-level only)
   - Test: Tool hooks work correctly

4. **Phase 5 (Advanced Features)**: Health monitoring and admin tools
   - Deploy: BridgeHealthMonitor, admin CLI
   - No migration needed
   - Test: Health checks and recovery

**Operations:**

**Bridge Registration (Admin):**
```bash
# Load bridge manifest
scribe-admin bridge register --manifest .scribe/config/bridges/council_mcp.yaml

# Activate bridge
scribe-admin bridge activate council_mcp

# Check bridge status
scribe-admin bridge list
scribe-admin bridge status council_mcp
```

**Bridge Monitoring:**
```bash
# Health check
scribe-admin bridge health council_mcp

# View bridge logs
scribe-admin bridge logs council_mcp --last 50

# Deactivate unhealthy bridge
scribe-admin bridge deactivate council_mcp
```

**Configuration Management:**
- Bridge manifests in `.scribe/config/bridges/*.yaml`
- Environment variables for API keys (e.g., `COUNCIL_BRIDGE_API_KEY`)
- Hot-reload supported for manifest changes (restart MCP server)

**Observability:**

1. **Bridge State Tracking**: All state transitions logged to progress log
2. **Health Monitoring**: Periodic checks with configurable intervals
3. **API Call Logging**: All bridge→Scribe API calls logged with metadata
4. **Error Tracking**: Failed hooks and operations logged with stack traces

**Security Considerations:**

- API keys stored securely (environment variables, not committed)
- Per-bridge permissions enforced at API layer
- Bridge errors isolated (no cascading failures)
- Timeout enforcement prevents hung bridges from blocking operations
- Access control prevents cross-bridge interference

**Rollback Strategy:**

- Schema migrations are additive (safe to rollback code)
- Bridge deactivation immediately stops hook execution
- Unregister bridge to fully remove (preserves data for audit)
- Database backups before major version upgrades
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