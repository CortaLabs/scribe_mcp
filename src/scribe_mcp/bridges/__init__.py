"""Bridge registry system for external integrations."""

from .manifest import (
    BridgeManifest,
    BridgeState,
    LogTypeConfig,
    HookConfig,
    BridgeProjectConfig,
    BridgeValidationConfig,
)
from .plugin import BridgePlugin
from .registry import BridgeRegistry
from .api import BridgeToScribeAPI
from .policy import BridgePolicyPlugin
from .hooks import BridgeHookManager, get_hook_manager
from .security import BridgeSecurityManager
from .tools import BridgeToolWrapper, BridgeToolRegistry, get_tool_registry
from .health import (
    BridgeHealthMonitor,
    get_health_monitor,
    set_health_monitor,
    create_health_monitor,
)

__all__ = [
    "BridgeManifest",
    "BridgeState",
    "LogTypeConfig",
    "HookConfig",
    "BridgeProjectConfig",
    "BridgeValidationConfig",
    "BridgePlugin",
    "BridgeRegistry",
    "BridgeToScribeAPI",
    "BridgePolicyPlugin",
    "BridgeHookManager",
    "get_hook_manager",
    "BridgeSecurityManager",
    "BridgeToolWrapper",
    "BridgeToolRegistry",
    "get_tool_registry",
    "BridgeHealthMonitor",
    "get_health_monitor",
    "set_health_monitor",
    "create_health_monitor",
]
