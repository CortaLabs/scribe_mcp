"""Bridge registry for managing bridge integrations."""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Type, Any
import logging

from .manifest import BridgeManifest, BridgeState
from .hooks import BridgeHookManager
from .plugin import BridgePlugin
from .runtime import bind_bridge_runtime
from scribe_mcp.utils.error_handler import sanitize_error_message

logger = logging.getLogger(__name__)


class BridgeRegistry:
    """
    Central registry for bridge integrations.

    Manages bridge lifecycle: registration, activation, deactivation,
    health monitoring, and discovery.
    """

    def __init__(
        self,
        storage_backend,
        config_dir: Optional[Path] = None,
        hook_manager: Optional[BridgeHookManager] = None,
    ):
        """
        Initialize bridge registry.

        Args:
            storage_backend: StorageBackend instance for persistence
            config_dir: Directory containing bridge manifest YAML files
                       (defaults to .scribe/config/bridges)
        """
        self._storage = storage_backend
        self._config_dir = config_dir or Path(".scribe/config/bridges")
        self._bridges: Dict[str, BridgePlugin] = {}
        self._manifests: Dict[str, BridgeManifest] = {}
        self._hook_manager = hook_manager or BridgeHookManager()

    def load_manifest(self, path: Path) -> BridgeManifest:
        """
        Load and validate manifest from YAML file.

        Args:
            path: Path to YAML manifest file

        Returns:
            Validated BridgeManifest instance

        Raises:
            ValueError: If manifest is invalid
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        if not path.exists():
            raise FileNotFoundError(f"Manifest file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty manifest file: {path}")

        manifest = BridgeManifest.from_dict(data)

        # Validate manifest
        errors = manifest.validate()
        if errors:
            raise ValueError(f"Invalid manifest in {path}: {'; '.join(errors)}")

        # Expand environment variables
        manifest.expand_env_vars()

        return manifest

    async def register_bridge(
        self,
        manifest: BridgeManifest,
        plugin_class: Optional[Type[BridgePlugin]] = None
    ) -> str:
        """
        Register a new bridge.

        Persists bridge to database and creates plugin instance if provided.

        Args:
            manifest: Bridge manifest configuration
            plugin_class: Optional plugin class to instantiate

        Returns:
            Bridge ID

        Raises:
            ValueError: If bridge already registered or manifest invalid
        """
        # Check if already registered
        if manifest.bridge_id in self._manifests:
            raise ValueError(f"Bridge {manifest.bridge_id} already registered")

        # Validate manifest
        errors = manifest.validate()
        if errors:
            raise ValueError(f"Invalid manifest: {'; '.join(errors)}")

        binding = bind_bridge_runtime(
            manifest=manifest,
            storage_backend=self._storage,
            plugin_class=plugin_class,
        )

        # Persist to database
        await self._storage.insert_bridge(
            bridge_id=manifest.bridge_id,
            name=manifest.name,
            version=manifest.version,
            manifest_json=manifest.to_json(for_persistence=True),
            state=BridgeState.REGISTERED.value
        )

        self._bridges[manifest.bridge_id] = binding.plugin
        self._hook_manager.register_bridge(binding.plugin)

        self._manifests[manifest.bridge_id] = manifest

        logger.info(
            "Registered bridge: %s v%s (runtime owner=%s)",
            manifest.bridge_id,
            manifest.version,
            binding.owner_package,
        )
        return manifest.bridge_id

    async def activate_bridge(self, bridge_id: str) -> None:
        """
        Transition bridge to ACTIVE state.

        Calls bridge's on_activate() method and updates state.

        Args:
            bridge_id: ID of bridge to activate

        Raises:
            ValueError: If bridge not registered
            RuntimeError: If activation fails
        """
        if bridge_id not in self._manifests:
            raise ValueError(f"Bridge {bridge_id} not registered")

        bridge = self._bridges.get(bridge_id)
        if not bridge:
            raise ValueError(f"Bridge {bridge_id} has no plugin instance")

        # Check current state
        if bridge.state == BridgeState.ACTIVE:
            logger.warning(f"Bridge {bridge_id} already active")
            return

        # Call activation hook
        try:
            await bridge.on_activate()
            bridge.state = BridgeState.ACTIVE
            await self._storage.update_bridge_state(bridge_id, BridgeState.ACTIVE.value)
            logger.info(f"Activated bridge: {bridge_id}")
        except Exception as e:
            # Update state to ERROR
            bridge.state = BridgeState.ERROR
            await self._storage.update_bridge_state(bridge_id, BridgeState.ERROR.value)
            safe_error = sanitize_error_message(str(e))
            error_msg = f"Failed to activate bridge {bridge_id}: {safe_error}"
            logger.error(error_msg)
            # Update health with error
            await self._storage.update_bridge_health(
                bridge_id,
                '{"healthy": false}',
                error=safe_error
            )
            raise RuntimeError(error_msg) from e

    async def deactivate_bridge(self, bridge_id: str) -> None:
        """
        Transition bridge to INACTIVE state.

        Calls bridge's on_deactivate() method and updates state.

        Args:
            bridge_id: ID of bridge to deactivate

        Raises:
            ValueError: If bridge not registered
        """
        bridge = self._bridges.get(bridge_id)
        if not bridge:
            raise ValueError(f"Bridge {bridge_id} has no loaded runtime plugin")

        # Check current state
        if bridge.state == BridgeState.INACTIVE:
            logger.warning(f"Bridge {bridge_id} already inactive")
            return

        # Call deactivation hook (should be idempotent)
        try:
            await bridge.on_deactivate()
            bridge.state = BridgeState.INACTIVE
            await self._storage.update_bridge_state(bridge_id, BridgeState.INACTIVE.value)
            logger.info(f"Deactivated bridge: {bridge_id}")
        except Exception as e:
            safe_error = sanitize_error_message(str(e))
            logger.error(f"Error during deactivation of bridge {bridge_id}: {safe_error}")
            # Still mark as inactive - deactivation should be best-effort
            bridge.state = BridgeState.INACTIVE
            await self._storage.update_bridge_state(bridge_id, BridgeState.INACTIVE.value)

    async def unregister_bridge(self, bridge_id: str) -> None:
        """
        Remove bridge from registry.

        Deactivates bridge if active, then removes from memory and database.

        Args:
            bridge_id: ID of bridge to unregister

        Raises:
            ValueError: If bridge not registered
        """
        if bridge_id not in self._manifests:
            raise ValueError(f"Bridge {bridge_id} not registered")

        # Deactivate if active
        if bridge_id in self._bridges:
            bridge = self._bridges[bridge_id]
            if bridge.state == BridgeState.ACTIVE:
                await self.deactivate_bridge(bridge_id)
            self._hook_manager.unregister_bridge(bridge_id)
            del self._bridges[bridge_id]

        # Remove from manifests
        del self._manifests[bridge_id]

        # Update database state to UNREGISTERED
        await self._storage.update_bridge_state(bridge_id, BridgeState.UNREGISTERED.value)

        logger.info(f"Unregistered bridge: {bridge_id}")

    async def list_bridges(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all registered bridges.

        Args:
            state: Optional state filter (registered|active|inactive|error|unregistered)

        Returns:
            List of bridge records from database
        """
        return await self._storage.list_bridges(state)

    def get_bridge(self, bridge_id: str) -> Optional[BridgePlugin]:
        """
        Get bridge plugin by ID.

        Args:
            bridge_id: Bridge ID

        Returns:
            BridgePlugin instance or None if not found
        """
        return self._bridges.get(bridge_id)

    def get_manifest(self, bridge_id: str) -> Optional[BridgeManifest]:
        """
        Get bridge manifest by ID.

        Args:
            bridge_id: Bridge ID

        Returns:
            BridgeManifest instance or None if not found
        """
        return self._manifests.get(bridge_id)

    def discover_manifests(self) -> List[Path]:
        """
        Find all YAML manifest files in config directory.

        Looks for *.yaml and *.yml files, excluding templates
        (files starting with underscore).

        Returns:
            List of paths to manifest files
        """
        if not self._config_dir.exists():
            logger.warning(f"Bridge config directory does not exist: {self._config_dir}")
            return []

        manifests = []
        for pattern in ("*.yaml", "*.yml"):
            for path in self._config_dir.glob(pattern):
                # Skip template files
                if path.name.startswith("_"):
                    continue
                manifests.append(path)

        return manifests

    async def load_all_manifests(self) -> List[BridgeManifest]:
        """
        Load all discovered manifest files.

        Logs errors for invalid manifests but continues loading others.

        Returns:
            List of successfully loaded manifests
        """
        manifests = []
        for path in self.discover_manifests():
            try:
                manifest = self.load_manifest(path)
                manifests.append(manifest)
                logger.info(f"Loaded manifest: {manifest.bridge_id} from {path}")
            except Exception as e:
                safe_error = sanitize_error_message(str(e))
                logger.error(f"Failed to load manifest {path}: {safe_error}")

        return manifests

    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Run health checks on all active bridges.

        Returns:
            Dictionary mapping bridge_id to health check results
        """
        results = {}

        for bridge_id, bridge in self._bridges.items():
            if bridge.state != BridgeState.ACTIVE:
                continue

            try:
                health = await bridge.health_check()
                results[bridge_id] = health

                # Update database
                import json
                await self._storage.update_bridge_health(
                    bridge_id,
                    json.dumps(health),
                    error=None
                )

            except Exception as e:
                safe_error = sanitize_error_message(str(e))
                logger.error(f"Health check failed for bridge {bridge_id}: {safe_error}")
                results[bridge_id] = {
                    "healthy": False,
                    "error": safe_error
                }

                # Update database with error
                await self._storage.update_bridge_health(
                    bridge_id,
                    '{"healthy": false}',
                    error=safe_error
                )

        return results
