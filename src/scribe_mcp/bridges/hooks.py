"""Bridge hook system for bidirectional communication."""

from typing import Dict, Any, List, Optional
import asyncio
import logging
from datetime import datetime, timezone

from .manifest import BridgeState
from .plugin import BridgePlugin

logger = logging.getLogger(__name__)


class BridgeHookManager:
    """
    Manages hook execution for all registered bridges.

    Coordinates calling pre_append/post_append across all active bridges
    with proper error isolation and timeout handling.
    """

    def __init__(self):
        self._bridges: Dict[str, BridgePlugin] = {}
        self._default_timeout_ms = 5000

    def register_bridge(self, bridge: BridgePlugin) -> None:
        """
        Register a bridge for hook callbacks.

        Args:
            bridge: BridgePlugin instance to register
        """
        self._bridges[bridge.bridge_id] = bridge
        logger.info(f"Registered bridge for hooks: {bridge.bridge_id}")

    def unregister_bridge(self, bridge_id: str) -> None:
        """
        Unregister a bridge from hook callbacks.

        Args:
            bridge_id: Bridge ID to unregister
        """
        if bridge_id in self._bridges:
            del self._bridges[bridge_id]
            logger.info(f"Unregistered bridge from hooks: {bridge_id}")

    async def execute_pre_append(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute pre_append hooks on all active bridges.

        Hooks are called in registration order. Each hook can modify
        entry_data. Critical hook failures block the operation.

        Args:
            entry_data: Entry data to process

        Returns:
            Modified entry_data after all hooks

        Raises:
            RuntimeError: If a critical hook fails or times out
        """
        result = entry_data.copy()

        for bridge_id, bridge in self._bridges.items():
            if bridge.state != BridgeState.ACTIVE:
                continue

            # Get hook config
            hook_config = bridge.manifest.hooks.get("pre_append")
            if not hook_config:
                continue

            timeout_ms = hook_config.timeout_ms
            is_critical = hook_config.critical

            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    bridge.pre_append(result),
                    timeout=timeout_ms / 1000.0
                )
                logger.debug(f"Bridge {bridge_id} pre_append hook executed successfully")
            except asyncio.TimeoutError:
                error_msg = f"Bridge {bridge_id} pre_append timed out after {timeout_ms}ms"
                logger.error(error_msg)
                if is_critical:
                    raise RuntimeError(f"Critical hook {bridge_id}.pre_append timed out")
            except Exception as e:
                error_msg = f"Bridge {bridge_id} pre_append failed: {e}"
                logger.error(error_msg)
                if is_critical:
                    raise RuntimeError(f"Critical hook {bridge_id}.pre_append failed: {e}")

        return result

    async def execute_post_append(self, entry_data: Dict[str, Any]) -> None:
        """
        Execute post_append hooks on all active bridges.

        Hooks are fire-and-forget - errors are logged but don't
        affect the operation.

        Args:
            entry_data: Entry data that was appended
        """
        for bridge_id, bridge in self._bridges.items():
            if bridge.state != BridgeState.ACTIVE:
                continue

            # Get hook config
            hook_config = bridge.manifest.hooks.get("post_append")
            if not hook_config:
                continue

            timeout_ms = hook_config.timeout_ms

            try:
                await asyncio.wait_for(
                    bridge.post_append(entry_data),
                    timeout=timeout_ms / 1000.0
                )
                logger.debug(f"Bridge {bridge_id} post_append hook executed successfully")
            except asyncio.TimeoutError:
                logger.error(f"Bridge {bridge_id} post_append timed out after {timeout_ms}ms")
            except Exception as e:
                logger.error(f"Bridge {bridge_id} post_append failed: {e}")

    async def execute_pre_rotate(self, log_type: str) -> None:
        """
        Execute pre_rotate hooks on all active bridges.

        Args:
            log_type: Log type being rotated
        """
        for bridge_id, bridge in self._bridges.items():
            if bridge.state != BridgeState.ACTIVE:
                continue

            # Get hook config
            hook_config = bridge.manifest.hooks.get("pre_rotate")
            if not hook_config:
                continue

            timeout_ms = hook_config.timeout_ms
            is_critical = hook_config.critical

            try:
                await asyncio.wait_for(
                    bridge.pre_rotate(log_type),
                    timeout=timeout_ms / 1000.0
                )
                logger.debug(f"Bridge {bridge_id} pre_rotate hook executed successfully")
            except asyncio.TimeoutError:
                error_msg = f"Bridge {bridge_id} pre_rotate timed out after {timeout_ms}ms"
                logger.error(error_msg)
                if is_critical:
                    raise RuntimeError(f"Critical hook {bridge_id}.pre_rotate timed out")
            except Exception as e:
                error_msg = f"Bridge {bridge_id} pre_rotate failed: {e}"
                logger.error(error_msg)
                if is_critical:
                    raise RuntimeError(f"Critical hook {bridge_id}.pre_rotate failed: {e}")

    async def execute_post_rotate(self, log_type: str, archive_path: str) -> None:
        """
        Execute post_rotate hooks on all active bridges.

        Args:
            log_type: Log type that was rotated
            archive_path: Path to rotated archive
        """
        for bridge_id, bridge in self._bridges.items():
            if bridge.state != BridgeState.ACTIVE:
                continue

            # Get hook config
            hook_config = bridge.manifest.hooks.get("post_rotate")
            if not hook_config:
                continue

            timeout_ms = hook_config.timeout_ms

            try:
                await asyncio.wait_for(
                    bridge.post_rotate(log_type, archive_path),
                    timeout=timeout_ms / 1000.0
                )
                logger.debug(f"Bridge {bridge_id} post_rotate hook executed successfully")
            except asyncio.TimeoutError:
                logger.error(f"Bridge {bridge_id} post_rotate timed out after {timeout_ms}ms")
            except Exception as e:
                logger.error(f"Bridge {bridge_id} post_rotate failed: {e}")


# Global hook manager instance
_hook_manager: Optional[BridgeHookManager] = None


def get_hook_manager() -> BridgeHookManager:
    """
    Get or create the global hook manager.

    Returns:
        Singleton BridgeHookManager instance
    """
    global _hook_manager
    if _hook_manager is None:
        _hook_manager = BridgeHookManager()
    return _hook_manager
