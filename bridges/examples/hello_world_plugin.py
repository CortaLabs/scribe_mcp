"""
Hello World Example Bridge Plugin

This is a minimal example showing how to create a Scribe bridge plugin.
Use this as a template for your own bridge implementations.

To enable:
1. Copy .scribe/config/bridges/hello_world.yaml.example to hello_world.yaml
2. Set enabled: true
3. Restart the Scribe MCP server

Example Usage:
    This plugin is automatically loaded by the BridgeRegistry when enabled.
    It demonstrates:
    - Activation/deactivation lifecycle
    - Health check reporting
    - Pre-append hook for entry modification
    - Post-append hook for event tracking
"""

from typing import Any, Dict, Optional
import logging

from bridges.plugin import BridgePlugin

logger = logging.getLogger(__name__)


class HelloWorldBridgePlugin(BridgePlugin):
    """
    Minimal example bridge plugin demonstrating the bridge lifecycle.

    This plugin:
    - Logs activation/deactivation events
    - Provides a simple health check
    - Demonstrates pre/post append hooks
    - Tracks append events with a counter

    Attributes:
        bridge_id: Unique identifier for this bridge instance
        manifest: Bridge manifest configuration
        _active: Whether the bridge is currently active
        _append_count: Number of appends processed
    """

    def __init__(self, manifest: Any):
        """
        Initialize the HelloWorld bridge plugin.

        Args:
            manifest: Loaded BridgeManifest configuration
        """
        super().__init__(manifest)
        self._active = False
        self._append_count = 0
        logger.info(f"HelloWorldBridgePlugin initialized: {self.bridge_id}")

    async def on_activate(self) -> None:
        """
        Called when the bridge is activated.

        This is where you'd initialize connections, load resources, etc.
        """
        self._active = True
        self._append_count = 0
        logger.info(f"HelloWorldBridge activated: {self.bridge_id}")

    async def on_deactivate(self) -> None:
        """
        Called when the bridge is deactivated.

        This is where you'd clean up connections, save state, etc.
        """
        self._active = False
        logger.info(
            f"HelloWorldBridge deactivated: {self.bridge_id} "
            f"(processed {self._append_count} appends)"
        )

    async def health_check(self) -> Dict[str, Any]:
        """
        Return health status for monitoring.

        The BridgeRegistry calls this periodically to monitor bridge health.

        Returns:
            Dict with 'healthy' bool and optional details:
            {
                "healthy": True,
                "bridge_id": "hello_world",
                "append_count": 42,
                "message": "Optional status message"
            }
        """
        return {
            "healthy": self._active,
            "bridge_id": self.bridge_id,
            "append_count": self._append_count,
            "message": "Hello from the example bridge!"
        }

    async def pre_append(self, entry_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Called before an entry is appended.

        This hook can:
        - Modify entry_data and return the modified version
        - Return None to use the original entry_data unchanged
        - Return False to reject the append (only if critical=true in manifest)

        Example use cases:
        - Add metadata tags
        - Enrich entries with external data
        - Validate entry format
        - Filter sensitive information

        Args:
            entry_data: The entry about to be appended

        Returns:
            Modified entry_data dict, None for original, or False to reject
        """
        # Example: Add a tag to indicate this went through our bridge
        if entry_data.get("meta") is None:
            entry_data["meta"] = {}

        entry_data["meta"]["hello_world_processed"] = True

        logger.debug(
            f"HelloWorldBridge pre_append: "
            f"{entry_data.get('message', '')[:50]}"
        )

        return entry_data

    async def post_append(
        self,
        entry_data: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """
        Called after an entry is successfully appended.

        This hook is for side effects only - you cannot modify the entry.

        Example use cases:
        - Send notifications
        - Update metrics/dashboards
        - Trigger downstream workflows
        - Log to external systems

        Args:
            entry_data: The entry that was appended
            result: The result from the append operation
        """
        self._append_count += 1

        logger.debug(
            f"HelloWorldBridge post_append #{self._append_count}: "
            f"success={result.get('ok')}"
        )


def create_plugin(manifest: Any) -> HelloWorldBridgePlugin:
    """
    Factory function to create plugin instance.

    The BridgeRegistry uses this function to instantiate the plugin.
    This pattern allows for plugin initialization customization.

    Args:
        manifest: Loaded BridgeManifest configuration

    Returns:
        Initialized HelloWorldBridgePlugin instance
    """
    return HelloWorldBridgePlugin(manifest)
