"""Bridge tool wrapping and custom tool registration."""

from typing import Callable, Dict, Any, List, Optional
import functools
import logging
import asyncio

logger = logging.getLogger(__name__)


class BridgeToolWrapper:
    """
    Wraps a Scribe tool to add bridge-specific behavior.

    Enables pre/post hooks on any tool without modifying the original.
    """

    def __init__(self, bridge_id: str, tool_name: str, original_tool: Callable):
        self.bridge_id = bridge_id
        self.tool_name = tool_name
        self.original_tool = original_tool
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []

    def add_pre_hook(self, hook: Callable) -> "BridgeToolWrapper":
        """
        Add pre-execution hook.

        Hook signature: async def hook(args, kwargs) -> (args, kwargs)
        Can modify arguments before tool execution.
        """
        self._pre_hooks.append(hook)
        return self

    def add_post_hook(self, hook: Callable) -> "BridgeToolWrapper":
        """
        Add post-execution hook.

        Hook signature: async def hook(result, args, kwargs) -> result
        Can modify result after tool execution.
        """
        self._post_hooks.append(hook)
        return self

    async def __call__(self, *args, **kwargs) -> Any:
        """Execute wrapped tool with all hooks."""
        # Run pre-hooks
        current_args, current_kwargs = args, kwargs
        for hook in self._pre_hooks:
            try:
                result = hook(current_args, current_kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                if result is not None:
                    current_args, current_kwargs = result
            except Exception as e:
                logger.error(f"Pre-hook failed for {self.tool_name}: {e}")

        # Execute original tool
        result = self.original_tool(*current_args, **current_kwargs)
        if asyncio.iscoroutine(result):
            result = await result

        # Run post-hooks
        for hook in self._post_hooks:
            try:
                hook_result = hook(result, current_args, current_kwargs)
                if asyncio.iscoroutine(hook_result):
                    hook_result = await hook_result
                if hook_result is not None:
                    result = hook_result
            except Exception as e:
                logger.error(f"Post-hook failed for {self.tool_name}: {e}")

        return result


class BridgeToolRegistry:
    """
    Registry for bridge-specific tools.

    Manages:
    - Wrapped versions of existing Scribe tools
    - Custom tools registered by bridges
    - Tool access control per bridge
    """

    def __init__(self):
        # bridge_id -> tool_name -> wrapper/callable
        self._wrapped_tools: Dict[str, Dict[str, BridgeToolWrapper]] = {}
        self._custom_tools: Dict[str, Dict[str, Callable]] = {}
        self._tool_schemas: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def wrap_tool(
        self,
        bridge_id: str,
        tool_name: str,
        original_tool: Callable
    ) -> BridgeToolWrapper:
        """
        Create a wrapped version of a Scribe tool for a bridge.

        Returns wrapper that can have hooks added.
        """
        wrapper = BridgeToolWrapper(bridge_id, tool_name, original_tool)

        if bridge_id not in self._wrapped_tools:
            self._wrapped_tools[bridge_id] = {}
        self._wrapped_tools[bridge_id][tool_name] = wrapper

        logger.info(f"Bridge {bridge_id} wrapped tool: {tool_name}")
        return wrapper

    def register_custom_tool(
        self,
        bridge_id: str,
        tool_name: str,
        implementation: Callable,
        schema: Optional[Dict[str, Any]] = None,
        description: str = ""
    ) -> None:
        """
        Register a custom tool provided by a bridge.

        Tool will be exposed via MCP as {bridge_id}:{tool_name}
        """
        if bridge_id not in self._custom_tools:
            self._custom_tools[bridge_id] = {}
            self._tool_schemas[bridge_id] = {}

        self._custom_tools[bridge_id][tool_name] = implementation
        self._tool_schemas[bridge_id][tool_name] = {
            "name": f"{bridge_id}:{tool_name}",
            "description": description,
            "schema": schema or {}
        }

        logger.info(f"Bridge {bridge_id} registered custom tool: {tool_name}")

    def unregister_bridge_tools(self, bridge_id: str) -> None:
        """Remove all tools for a bridge."""
        if bridge_id in self._wrapped_tools:
            del self._wrapped_tools[bridge_id]
        if bridge_id in self._custom_tools:
            del self._custom_tools[bridge_id]
        if bridge_id in self._tool_schemas:
            del self._tool_schemas[bridge_id]
        logger.info(f"Unregistered all tools for bridge: {bridge_id}")

    def get_wrapped_tool(
        self,
        bridge_id: str,
        tool_name: str
    ) -> Optional[BridgeToolWrapper]:
        """Get wrapped tool for a bridge."""
        return self._wrapped_tools.get(bridge_id, {}).get(tool_name)

    def get_custom_tool(
        self,
        bridge_id: str,
        tool_name: str
    ) -> Optional[Callable]:
        """Get custom tool for a bridge."""
        return self._custom_tools.get(bridge_id, {}).get(tool_name)

    def list_bridge_tools(self, bridge_id: str) -> Dict[str, List[str]]:
        """List all tools for a bridge."""
        return {
            "wrapped": list(self._wrapped_tools.get(bridge_id, {}).keys()),
            "custom": list(self._custom_tools.get(bridge_id, {}).keys())
        }

    def list_all_custom_tools(self) -> List[Dict[str, Any]]:
        """List all custom tools from all bridges (for MCP registration)."""
        tools = []
        for bridge_id, bridge_tools in self._tool_schemas.items():
            for tool_name, schema in bridge_tools.items():
                tools.append({
                    "bridge_id": bridge_id,
                    "tool_name": tool_name,
                    "full_name": f"{bridge_id}:{tool_name}",
                    **schema
                })
        return tools


# Global registry instance
_tool_registry: Optional[BridgeToolRegistry] = None


def get_tool_registry() -> BridgeToolRegistry:
    """Get or create the global tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = BridgeToolRegistry()
    return _tool_registry
