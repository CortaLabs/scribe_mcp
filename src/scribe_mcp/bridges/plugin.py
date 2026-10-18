"""Bridge plugin base class and interfaces."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from .manifest import BridgeManifest, BridgeState


class BridgePlugin(ABC):
    """
    Base class for bridge plugins.

    All bridge integrations must extend this class and implement
    the required lifecycle and health check methods.

    The registry will set the _api attribute after construction
    to provide access to Scribe API methods.
    """

    def __init__(self, manifest: BridgeManifest):
        """
        Initialize bridge plugin.

        Args:
            manifest: Bridge manifest configuration
        """
        self.manifest = manifest
        self.bridge_id = manifest.bridge_id
        self.state = BridgeState.REGISTERED
        self._api = None  # Set by registry after construction
        self._policy = None
        self._owner_package: Optional[str] = None
        self._plugin_reference: Optional[str] = None

    @abstractmethod
    async def on_activate(self) -> None:
        """
        Called when bridge transitions to ACTIVE state.

        This is where bridges should:
        - Establish external connections
        - Initialize resources
        - Register webhooks
        - Start background tasks

        Raises:
            Exception: If activation fails, bridge will remain REGISTERED
        """
        pass

    @abstractmethod
    async def on_deactivate(self) -> None:
        """
        Called when bridge transitions to INACTIVE state.

        This is where bridges should:
        - Close external connections
        - Clean up resources
        - Unregister webhooks
        - Stop background tasks

        Should be idempotent - safe to call multiple times.
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Return health status for monitoring.

        Must include {"healthy": bool} at minimum.
        Additional fields are optional but recommended:
        - message: Human-readable status message
        - latency_ms: Response time for health check
        - last_error: Most recent error message
        - uptime_seconds: Time since activation

        Returns:
            Dictionary with at least {"healthy": bool}

        Example:
            {
                "healthy": True,
                "message": "All systems operational",
                "latency_ms": 42,
                "uptime_seconds": 3600
            }
        """
        pass

    # Optional hook methods (override if needed)

    async def pre_append(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Called before entry is appended to log.

        Bridges can:
        - Validate entry data
        - Enrich with additional metadata
        - Transform or normalize data
        - Reject invalid entries (raise exception)

        Args:
            entry_data: Entry data about to be logged

        Returns:
            Modified entry data (or original if no changes)

        Raises:
            ValueError: If entry should be rejected
        """
        return entry_data

    async def post_append(self, entry_data: Dict[str, Any]) -> None:
        """
        Called after entry is successfully appended to log.

        Bridges can:
        - Send notifications
        - Update external systems
        - Trigger workflows
        - Collect analytics

        This is fire-and-forget - exceptions are logged but don't
        affect the append operation.

        Args:
            entry_data: Entry data that was logged
        """
        pass

    async def pre_rotate(self, log_type: str) -> None:
        """
        Called before log rotation begins.

        Bridges can:
        - Archive data to external storage
        - Generate reports
        - Send summaries

        Args:
            log_type: Type of log being rotated
        """
        pass

    async def post_rotate(self, log_type: str, archive_path: str) -> None:
        """
        Called after log rotation completes.

        Args:
            log_type: Type of log that was rotated
            archive_path: Path to archived log file
        """
        pass

    # read-hook-event: generic, content-agnostic read hooks (async). Mirror
    # pre_append/post_append above. Scribe never inspects the returned payload;
    # any non-None post_read return is collected by the hook manager into a
    # generic ``result["read_annotations"]`` list.

    async def pre_read(self, path: str, context: Dict[str, Any]) -> None:
        """
        Called before a read result is produced.

        This is non-critical by default; failures are isolated and do not
        affect the read unless the hook is configured as critical.

        Args:
            path: Path being read
            context: Generic read context
        """
        pass

    async def post_read(
        self, path: str, result: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Called after a read result is produced.

        This is fire-and-forget - exceptions are logged but don't affect the
        read operation. Return an optional generic annotation payload (opaque
        to Scribe) or ``None`` for no annotation.

        Args:
            path: Path that was read
            result: Read result
            context: Generic read context

        Returns:
            Optional generic annotation payload, or None
        """
        return None

    async def pre_project_create(self, project_name: str, project_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Called before project is created.

        Bridges can:
        - Validate project configuration
        - Add default metadata
        - Apply naming conventions

        Args:
            project_name: Name of project being created
            project_config: Project configuration

        Returns:
            Modified project config (or original if no changes)

        Raises:
            ValueError: If project creation should be rejected
        """
        return project_config

    async def post_project_create(self, project_name: str, project_data: Dict[str, Any]) -> None:
        """
        Called after project is created.

        Args:
            project_name: Name of project that was created
            project_data: Complete project data
        """
        pass

    # API access helpers

    def bind_runtime(
        self,
        *,
        api,
        policy=None,
        owner_package: Optional[str] = None,
        plugin_reference: Optional[str] = None,
    ) -> None:
        """Bind runtime services injected by the registry."""
        self._api = api
        self._policy = policy
        self._owner_package = owner_package
        self._plugin_reference = plugin_reference

    def set_api(self, api) -> None:
        """
        Set API instance for accessing Scribe functionality.

        Called by registry during bridge registration.

        Args:
            api: Scribe API instance
        """
        self._api = api

    def get_api(self):
        """
        Get Scribe API instance.

        Returns:
            Scribe API instance or None if not set

        Raises:
            RuntimeError: If API not set (bridge not properly registered)
        """
        if self._api is None:
            raise RuntimeError(f"Bridge {self.bridge_id} API not initialized - bridge not properly registered")
        return self._api

    def get_policy(self):
        """Get the bound BridgePolicyPlugin instance."""
        if self._policy is None:
            raise RuntimeError(f"Bridge {self.bridge_id} policy not initialized - bridge not properly registered")
        return self._policy

    @property
    def owner_package(self) -> Optional[str]:
        """Top-level package that owns this bridge runtime."""
        return self._owner_package

    @property
    def plugin_reference(self) -> Optional[str]:
        """Resolved manifest plugin reference when one was used."""
        return self._plugin_reference
