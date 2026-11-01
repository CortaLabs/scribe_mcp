"""Bridge registry system for external integrations."""

from importlib import import_module
from typing import Any

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


_LAZY_EXPORTS = {
    "BridgeManifest": (".manifest", "BridgeManifest"),
    "BridgeState": (".manifest", "BridgeState"),
    "LogTypeConfig": (".manifest", "LogTypeConfig"),
    "HookConfig": (".manifest", "HookConfig"),
    "BridgeProjectConfig": (".manifest", "BridgeProjectConfig"),
    "BridgeValidationConfig": (".manifest", "BridgeValidationConfig"),
    "BridgePlugin": (".plugin", "BridgePlugin"),
    "BridgeRegistry": (".registry", "BridgeRegistry"),
    "BridgeToScribeAPI": (".api", "BridgeToScribeAPI"),
    "BridgePolicyPlugin": (".policy", "BridgePolicyPlugin"),
    "BridgeHookManager": (".hooks", "BridgeHookManager"),
    "get_hook_manager": (".hooks", "get_hook_manager"),
    "BridgeSecurityManager": (".security", "BridgeSecurityManager"),
    "BridgeToolWrapper": (".tools", "BridgeToolWrapper"),
    "BridgeToolRegistry": (".tools", "BridgeToolRegistry"),
    "get_tool_registry": (".tools", "get_tool_registry"),
    "BridgeHealthMonitor": (".health", "BridgeHealthMonitor"),
    "get_health_monitor": (".health", "get_health_monitor"),
    "set_health_monitor": (".health", "set_health_monitor"),
    "create_health_monitor": (".health", "create_health_monitor"),
}


def __getattr__(name: str) -> Any:
    """Load the bridge subsystem that owns a public export on first access."""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Keep lazy public exports discoverable through ``dir()``."""
    return sorted(set(globals()) | set(__all__))
