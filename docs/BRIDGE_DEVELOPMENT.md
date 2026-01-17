# Bridge Development Guide

This guide explains how to create bridges that integrate external MCPs with Scribe.

## Overview

Bridges allow external MCP servers to:
- Register with Scribe and persist configuration
- Execute hooks during Scribe operations (append, rotate, etc.)
- Create and manage projects with ownership semantics
- Wrap or extend Scribe tools with custom behavior
- Be monitored for health and managed via CLI

## Quick Start

### 1. Create a Bridge Manifest

Create `.scribe/config/bridges/my_bridge.yaml`:

```yaml
bridge_id: my_bridge
name: My Bridge
version: 1.0.0
description: Description of what my bridge does
author: Your Name

permissions:
  - read:all_projects
  - write:own_projects
  - create:projects

project_config:
  can_create_projects: true
  project_prefix: "mybr_"
  auto_tag:
    - automated
    - my-bridge

hooks:
  pre_append:
    callback_type: async
    timeout_ms: 5000
    critical: false
  post_append:
    callback_type: async
    timeout_ms: 5000
    critical: false

min_scribe_version: "2.1.0"
```

### 2. Implement the Bridge Plugin

Create your plugin by extending `BridgePlugin`:

```python
from scribe_mcp.bridges import BridgePlugin, BridgeManifest

class MyBridgePlugin(BridgePlugin):
    """My bridge implementation."""

    def __init__(self, manifest: BridgeManifest):
        super().__init__(manifest)
        self._connected = False

    async def on_activate(self) -> None:
        """Called when bridge is activated."""
        self._connected = True

    async def on_deactivate(self) -> None:
        """Called when bridge is deactivated."""
        self._connected = False

    async def health_check(self) -> dict:
        """Return health status."""
        return {
            "healthy": self._connected,
            "message": "Connected" if self._connected else "Disconnected"
        }

    async def pre_append(self, entry_data: dict) -> dict:
        """Modify entries before they're logged."""
        entry_data.setdefault("meta", {})
        entry_data["meta"]["bridge_id"] = self.bridge_id
        return entry_data

    async def post_append(self, entry_data: dict) -> None:
        """React to logged entries."""
        # Send notification, update external system, etc.
        pass
```

### 3. Register and Activate

```python
import asyncio
from pathlib import Path
from scribe_mcp.bridges import BridgeRegistry
from scribe_mcp.storage.sqlite import SQLiteStorage

async def main():
    # Initialize storage and registry
    storage = SQLiteStorage("path/to/db")
    await storage._initialise()
    registry = BridgeRegistry(storage)

    # Load manifest
    manifest = registry.load_manifest(Path(".scribe/config/bridges/my_bridge.yaml"))

    # Register with plugin class
    await registry.register_bridge(manifest, MyBridgePlugin)

    # Activate
    await registry.activate_bridge(manifest.bridge_id)

    print(f"Bridge {manifest.bridge_id} is now active!")

asyncio.run(main())
```

## Permission System

Bridges request permissions in their manifest:

| Permission | Description |
|------------|-------------|
| `read:all_projects` | Read any project's logs |
| `read:own_projects` | Read only bridge-owned projects |
| `write:all_projects` | Write to any project (admin) |
| `write:own_projects` | Write only to bridge-owned projects |
| `create:projects` | Create new projects |

## Hook Lifecycle

Bridges can implement hooks for various Scribe operations:

| Hook | When Called | Can Modify Data |
|------|-------------|-----------------|
| `pre_append` | Before entry is logged | Yes (entry_data) |
| `post_append` | After entry is logged | No (fire-and-forget) |
| `pre_rotate` | Before log rotation | No |
| `post_rotate` | After log rotation | No |
| `pre_project_create` | Before project creation | Yes (project_config) |
| `post_project_create` | After project creation | No |

## Admin CLI

Manage bridges from the command line:

```bash
# List all bridges
python -m scribe_mcp.scripts.scribe_admin bridge list

# Register a bridge
python -m scribe_mcp.scripts.scribe_admin bridge register --manifest path/to/manifest.yaml

# Activate/deactivate
python -m scribe_mcp.scripts.scribe_admin bridge activate my_bridge
python -m scribe_mcp.scripts.scribe_admin bridge deactivate my_bridge

# Check health
python -m scribe_mcp.scripts.scribe_admin bridge health my_bridge
python -m scribe_mcp.scripts.scribe_admin bridge health  # all bridges

# Detailed status
python -m scribe_mcp.scripts.scribe_admin bridge status my_bridge

# View bridge logs
python -m scribe_mcp.scripts.scribe_admin bridge logs my_bridge

# Health monitor
python -m scribe_mcp.scripts.scribe_admin health status
python -m scribe_mcp.scripts.scribe_admin health start --interval 300
python -m scribe_mcp.scripts.scribe_admin health stop
```

## Health Monitoring

The `BridgeHealthMonitor` runs periodic health checks:

- Transitions unhealthy bridges to ERROR state after configurable failures
- Recovers bridges to ACTIVE state after successful health checks
- Provides callbacks for state change notifications

```python
from scribe_mcp.bridges import create_health_monitor

async def on_state_change(bridge_id, old_state, new_state):
    print(f"Bridge {bridge_id}: {old_state} -> {new_state}")

monitor = await create_health_monitor(
    registry,
    check_interval=300,  # 5 minutes
    unhealthy_threshold=3,  # 3 failures before ERROR
    recovery_threshold=2,  # 2 successes to recover
    on_state_change=on_state_change
)
```

## Project Ownership

Bridge-created projects are automatically tagged with ownership:

```python
# Creating a project through the bridge
async def create_my_project(api: BridgeToScribeAPI):
    result = await api.set_project(
        name="task_123",  # Will become "mybr_task_123" with prefix
        description="Project for task 123"
    )
    # Project is automatically owned by this bridge
```

## Custom Tools

Bridges can wrap existing tools or register new ones:

```python
from scribe_mcp.bridges import get_tool_registry

registry = get_tool_registry()

# Wrap an existing tool
async def my_pre_hook(args, kwargs):
    kwargs["meta"] = kwargs.get("meta", {})
    kwargs["meta"]["source"] = "my_bridge"
    return args, kwargs

registry.wrap_tool(
    "my_bridge",
    "append_entry",
    original_append_entry,
    pre_hook=my_pre_hook
)

# Register a custom tool
async def my_custom_tool(param1: str, param2: int = 10) -> dict:
    return {"result": f"{param1}:{param2}"}

registry.register_custom_tool(
    "my_bridge",
    "my_tool",
    my_custom_tool,
    description="My custom tool"
)
```

## Security Considerations

1. **Environment Variables**: Store secrets in env vars, not manifests
2. **Timeouts**: All hooks have configurable timeouts (default 5s)
3. **Error Isolation**: Hook failures don't affect Scribe operations
4. **Permission Scoping**: Request minimum required permissions
5. **Validation**: Use strict mode for production bridges

## Reference Documentation

For complete API reference, see:
- [Bridge Manifest Schema](../.codex/skills/scribe-mcp-usage/references/bridges/manifest.md)
- [BridgePlugin API](../.codex/skills/scribe-mcp-usage/references/bridges/plugin.md)
- [Hook Lifecycle](../.codex/skills/scribe-mcp-usage/references/bridges/hooks.md)
- [Permission System](../.codex/skills/scribe-mcp-usage/references/bridges/permissions.md)
- [Tool Extension](../.codex/skills/scribe-mcp-usage/references/bridges/tools.md)

## Templates

Copy templates from `.codex/skills/scribe-mcp-usage/assets/templates/bridge/`:
- `bridge_manifest_template.yaml` - Manifest with all options documented
- `bridge_plugin_template.py` - Complete plugin implementation example
