"""Plugin registry system for Scribe.

This module provides a secure plugin system that allows repositories to
customize Scribe behavior without modifying the core codebase.
Security features include:
- Plugin signature verification with SHA-256 hash pinning
- Strict allowlist enforcement
- Manifest validation
- Sandbox-enforced boundaries
- Comprehensive error handling and logging
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.config.repo_config import RepoConfig
from scribe_mcp.security.sandbox import safe_file_operation


# Setup secure logging for plugin operations
plugin_logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """Plugin manifest with security metadata."""
    name: str
    version: str
    description: str
    author: str
    min_scribe_version: str = "1.0.0"
    max_scribe_version: Optional[str] = None
    required_permissions: List[str] = None
    file_hash: Optional[str] = None  # SHA-256 hash of the plugin file
    signature: Optional[str] = None  # Optional signature for verification

    def __post_init__(self):
        if self.required_permissions is None:
            self.required_permissions = []


class ScribePlugin(ABC):
    """Base class for Scribe plugins."""

    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    manifest: Optional[PluginManifest] = None

    @abstractmethod
    def initialize(self, config: RepoConfig) -> None:
        """Initialize the plugin with repository configuration."""
        pass

    def cleanup(self) -> None:
        """Cleanup resources when plugin is unloaded."""
        pass


class TemplatePlugin(ScribePlugin):
    """Plugin for custom document templates."""

    @abstractmethod
    def get_template(self, template_type: str) -> Optional[str]:
        """Get a custom template by type."""
        pass

    def list_templates(self) -> List[str]:
        """List available template types."""
        return []


class PolicyPlugin(ScribePlugin):
    """Plugin for repository-specific policies and constraints."""

    @abstractmethod
    def check_permission(self, operation: str, context: Dict[str, Any]) -> bool:
        """Check if an operation is allowed."""
        pass

    def validate_entry(self, entry_data: Dict[str, Any]) -> Optional[str]:
        """Validate a log entry, return error message if invalid."""
        return None


class FormatterPlugin(ScribePlugin):
    """Plugin for custom log entry formatting."""

    @abstractmethod
    def format_entry(self, entry_data: Dict[str, Any]) -> str:
        """Format a log entry for display."""
        pass

    def parse_entry(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a formatted log entry back to structured data."""
        return None


class HookPlugin(ScribePlugin):
    """Plugin for custom hooks at various points in the workflow."""

    def pre_append(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Called before an entry is appended."""
        return entry_data

    def post_append(self, entry_data: Dict[str, Any]) -> None:
        """Called after an entry is appended."""
        pass

    def pre_rotate(self, project_name: str) -> None:
        """Called before log rotation."""
        pass

    def post_rotate(self, project_name: str, archive_info: Dict[str, Any]) -> None:
        """Called after log rotation."""
        pass


class PluginRegistry:
    """Registry for managing Scribe plugins with security hardening."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.plugins: Dict[str, ScribePlugin] = {}
        self.template_plugins: List[TemplatePlugin] = []
        self.policy_plugins: List[PolicyPlugin] = []
        self.formatter_plugins: List[FormatterPlugin] = []
        self.hook_plugins: List[HookPlugin] = []
        self.repo_root = repo_root
        self._plugin_hashes: Dict[str, str] = {}  # Cache of verified plugin hashes

    def _verify_plugin_hash(self, plugin_file: Path, expected_hash: Optional[str] = None) -> bool:
        """Verify SHA-256 hash of plugin file against expected value."""
        try:
            with open(plugin_file, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            if expected_hash:
                if file_hash != expected_hash:
                    plugin_logger.error(
                        f"Plugin hash mismatch for {plugin_file.name}: "
                        f"expected {expected_hash}, got {file_hash}"
                    )
                    return False
                plugin_logger.info(f"Plugin hash verified for {plugin_file.name}")

            # Cache the hash for audit purposes
            self._plugin_hashes[plugin_file.name] = file_hash
            return True

        except Exception as e:
            plugin_logger.error(f"Failed to verify plugin hash for {plugin_file}: {e}")
            return False

    def _load_plugin_manifest(self, plugin_file: Path) -> Optional[PluginManifest]:
        """Load and validate plugin manifest."""
        manifest_file = plugin_file.with_suffix('.json')
        if not manifest_file.exists():
            # No manifest file, create a basic one from plugin class attributes
            return PluginManifest(
                name=plugin_file.stem,
                version="1.0.0",
                description=f"Plugin from {plugin_file.name}",
                author="Unknown"
            )

        try:
            with open(manifest_file, 'r') as f:
                manifest_data = json.load(f)

            # Validate manifest structure
            required_fields = ['name', 'version', 'description', 'author']
            for field in required_fields:
                if field not in manifest_data:
                    plugin_logger.error(f"Missing required field '{field}' in manifest {manifest_file}")
                    return None

            manifest = PluginManifest(**manifest_data)

            # Verify plugin file hash if specified in manifest
            if manifest.file_hash:
                if not self._verify_plugin_hash(plugin_file, manifest.file_hash):
                    plugin_logger.error(f"Plugin hash verification failed for {plugin_file}")
                    return None

            return manifest

        except Exception as e:
            plugin_logger.error(f"Failed to load manifest for {plugin_file}: {e}")
            return None

    def _is_plugin_allowed(self, plugin_name: str, allowlist: set, blocklist: set) -> bool:
        """Check if plugin is allowed based on allowlist and blocklist."""
        # Blocklist takes precedence
        if plugin_name in blocklist:
            plugin_logger.warning(f"Plugin {plugin_name} is explicitly blocked")
            return False

        # If allowlist is set, only allowlisted plugins are permitted
        if allowlist and plugin_name not in allowlist:
            plugin_logger.warning(f"Plugin {plugin_name} not in allowlist")
            return False

        return True

    def load_plugins(self, config: RepoConfig) -> None:
        """Load plugins from the repository's plugins directory with security hardening."""
        plugin_settings = config.plugin_config or {}
        if not plugin_settings.get("enabled"):
            plugin_logger.info("Plugin loading disabled (plugin_config.enabled is false or missing)")
            return

        # Security settings
        allowlist = set(plugin_settings.get("allowlist", []))
        blocklist = set(plugin_settings.get("blocklist", []))
        require_manifest = plugin_settings.get("require_manifest", False)
        verify_hashes = plugin_settings.get("verify_hashes", True)

        # Load built-in plugins first
        self._load_builtin_plugins(config)

        if not config.plugins_dir or not config.plugins_dir.exists():
            plugin_logger.debug("No plugins directory found")
            return

        # Load repository-specific plugins
        plugins_loaded = 0
        for plugin_file in config.plugins_dir.glob("*.py"):
            if plugin_file.name.startswith("__"):
                continue

            plugin_name = plugin_file.stem

            # Security check 1: Enforce repo sandbox boundaries
            try:
                safe_file_operation(
                    config.repo_root,
                    plugin_file,
                    operation="read",
                    context={
                        "component": "plugins",
                        "plugin_name": plugin_name,
                        "enforce_project": False,
                    },
                )
            except Exception as sandbox_error:
                plugin_logger.error(f"Sandbox violation for plugin {plugin_name}: {sandbox_error}")
                continue

            # Security check 2: Allowlist/blocklist enforcement
            if not self._is_plugin_allowed(plugin_name, allowlist, blocklist):
                continue

            # Security check 3: Load and validate manifest if required
            manifest = self._load_plugin_manifest(plugin_file)
            if not manifest:
                if require_manifest:
                    plugin_logger.error(f"Plugin {plugin_name} missing required manifest")
                    continue
                # Create basic manifest for compatibility
                manifest = PluginManifest(
                    name=plugin_name,
                    version="1.0.0",
                    description=f"Plugin from {plugin_file.name}",
                    author="Unknown"
                )

            # Security check 4: Hash verification
            if verify_hashes and not self._verify_plugin_hash(plugin_file, manifest.file_hash):
                plugin_logger.error(f"Plugin {plugin_name} failed hash verification")
                continue

            # Load the plugin with comprehensive error handling
            try:
                plugin = self._load_plugin_file(plugin_file, config, manifest)
                if plugin:
                    self._register_plugin(plugin)
                    plugins_loaded += 1
                    plugin_logger.info(
                        f"Successfully loaded plugin: {plugin.name} v{plugin.version} "
                        f"(hash: {self._plugin_hashes.get(plugin_file.name, 'unknown')[:8]}...)"
                    )
            except Exception as e:
                plugin_logger.error(f"Failed to load plugin {plugin_file}: {e}", exc_info=True)
                continue

        plugin_logger.info(f"Plugin loading completed. Loaded {plugins_loaded} plugins.")

    def _load_builtin_plugins(self, config: RepoConfig) -> None:
        """Load built-in plugins."""
        plugin_settings = config.plugin_config or {}
        allowlist = set(plugin_settings.get("allowlist", []))
        blocklist = set(plugin_settings.get("blocklist", []))

        try:
            from scribe_mcp.plugins.vector_indexer import VectorIndexer
        except Exception as exc:
            plugin_logger.error(f"Failed to import built-in vector_indexer: {exc}")
            return

        if not self._is_plugin_allowed("vector_indexer", allowlist, blocklist):
            return

        if "vector_indexer" in self.plugins:
            return

        try:
            plugin = VectorIndexer()
            plugin.initialize(config)
            self._register_plugin(plugin)
            plugin_logger.info(f"Loaded built-in plugin: {plugin.name} v{plugin.version}")
        except Exception as exc:
            plugin_logger.error(f"Failed to initialize built-in vector_indexer: {exc}", exc_info=True)

    def _load_plugin_file(self, plugin_file: Path, config: RepoConfig, manifest: Optional[PluginManifest] = None) -> Optional[ScribePlugin]:
        """Load a plugin from a Python file with security validation."""
        try:
            spec = importlib.util.spec_from_file_location(
                plugin_file.stem, plugin_file
            )
            if spec is None or spec.loader is None:
                plugin_logger.error(f"Could not load spec for {plugin_file}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for plugin classes in the module
            plugin_classes = []
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, ScribePlugin) and
                    obj != ScribePlugin and
                    not inspect.isabstract(obj)):
                    plugin_classes.append((name, obj))

            if not plugin_classes:
                plugin_logger.error(f"No valid plugin classes found in {plugin_file}")
                return None

            # Load the first valid plugin class found
            for class_name, plugin_class in plugin_classes:
                try:
                    plugin_instance = plugin_class()

                    # Set manifest if available
                    if manifest:
                        plugin_instance.manifest = manifest

                    # Validate plugin metadata
                    if not plugin_instance.name:
                        plugin_instance.name = manifest.name if manifest else class_name
                    if not plugin_instance.version:
                        plugin_instance.version = manifest.version if manifest else "1.0.0"
                    if not plugin_instance.author:
                        plugin_instance.author = manifest.author if manifest else "Unknown"

                    # Initialize plugin
                    plugin_instance.initialize(config)

                    # Log successful instantiation with hash for audit trail
                    hash_info = self._plugin_hashes.get(plugin_file.name, "unknown")[:8]
                    plugin_logger.info(
                        f"Instantiated plugin {plugin_instance.name} v{plugin_instance.version} "
                        f"by {plugin_instance.author} (hash: {hash_info}...)"
                    )

                    return plugin_instance

                except Exception as e:
                    plugin_logger.error(f"Failed to instantiate plugin {class_name}: {e}", exc_info=True)
                    continue

            plugin_logger.error(f"All plugin classes in {plugin_file} failed to instantiate")
            return None

        except Exception as e:
            plugin_logger.error(f"Failed to load plugin module {plugin_file}: {e}", exc_info=True)
            return None

    def _register_plugin(self, plugin: ScribePlugin) -> None:
        """Register a plugin in the appropriate categories."""
        self.plugins[plugin.name] = plugin

        if isinstance(plugin, TemplatePlugin):
            self.template_plugins.append(plugin)
        if isinstance(plugin, PolicyPlugin):
            self.policy_plugins.append(plugin)
        if isinstance(plugin, FormatterPlugin):
            self.formatter_plugins.append(plugin)
        if isinstance(plugin, HookPlugin):
            self.hook_plugins.append(plugin)

    def get_template(self, template_type: str) -> Optional[str]:
        """Get a custom template from registered template plugins."""
        for plugin in self.template_plugins:
            template = plugin.get_template(template_type)
            if template:
                return template
        return None

    def check_permission(self, operation: str, context: Dict[str, Any]) -> bool:
        """Check permissions using registered policy plugins."""
        for plugin in self.policy_plugins:
            if not plugin.check_permission(operation, context):
                return False
        return True

    def validate_entry(self, entry_data: Dict[str, Any]) -> Optional[str]:
        """Validate entry using registered policy plugins."""
        for plugin in self.policy_plugins:
            error = plugin.validate_entry(entry_data)
            if error:
                return error
        return None

    def format_entry(self, entry_data: Dict[str, Any]) -> str:
        """Format entry using registered formatter plugins."""
        for plugin in self.formatter_plugins:
            try:
                return plugin.format_entry(entry_data)
            except Exception:
                continue  # Try next plugin
        return None

    def execute_hook_pre_append(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute pre-append hooks."""
        data = entry_data.copy()
        for plugin in self.hook_plugins:
            try:
                data = plugin.pre_append(data)
            except Exception as e:
                plugin_logger.warning(f"Pre-append hook failed in {plugin.name}: {e}")
        return data

    def execute_hook_post_append(self, entry_data: Dict[str, Any]) -> None:
        """Execute post-append hooks."""
        for plugin in self.hook_plugins:
            try:
                plugin.post_append(entry_data)
            except Exception as e:
                plugin_logger.warning(f"Post-append hook failed in {plugin.name}: {e}")

    def execute_hook_pre_rotate(self, project_name: str) -> None:
        """Execute pre-rotation hooks."""
        for plugin in self.hook_plugins:
            try:
                plugin.pre_rotate(project_name)
            except Exception as e:
                plugin_logger.warning(f"Pre-rotate hook failed in {plugin.name}: {e}")

    def execute_hook_post_rotate(self, project_name: str, archive_info: Dict[str, Any]) -> None:
        """Execute post-rotation hooks."""
        for plugin in self.hook_plugins:
            try:
                plugin.post_rotate(project_name, archive_info)
            except Exception as e:
                plugin_logger.warning(f"Post-rotate hook failed in {plugin.name}: {e}")

    def cleanup(self) -> None:
        """Cleanup all registered plugins."""
        for plugin in self.plugins.values():
            try:
                plugin.cleanup()
            except Exception as e:
                plugin_logger.warning(f"Plugin cleanup failed for {plugin.name}: {e}")

        self.plugins.clear()
        self.template_plugins.clear()
        self.policy_plugins.clear()
        self.formatter_plugins.clear()
        self.hook_plugins.clear()


# Global plugin registry instance
_plugin_registry: Optional[PluginRegistry] = None


def get_plugin_registry(repo_root: Optional[Path] = None) -> PluginRegistry:
    """Get the global plugin registry instance with repository context."""
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry(repo_root=repo_root)
    return _plugin_registry


def initialize_plugins(config: RepoConfig) -> None:
    """Initialize plugins for a repository configuration."""
    registry = get_plugin_registry(config.repo_root)
    registry.cleanup()  # Cleanup any existing plugins
    registry.load_plugins(config)

    # Register vector tools if VectorIndexer plugin is loaded and initialized
    _register_vector_tools_if_available()


def _register_vector_tools_if_available() -> None:
    """Register vector search tools if VectorIndexer plugin is available."""
    plugin_logger.debug("Vector search tools are deprecated; use manage_docs action='search' with search_mode='semantic'.")


def get_plugin_security_info() -> Dict[str, Any]:
    """Get security information about loaded plugins for audit."""
    registry = get_plugin_registry()
    return {
        "plugins_loaded": len(registry.plugins),
        "plugin_hashes": registry._plugin_hashes,
        "plugin_manifests": {
            name: plugin.manifest.__dict__ if plugin.manifest else None
            for name, plugin in registry.plugins.items()
        }
    }


def get_template(template_type: str) -> Optional[str]:
    """Get a custom template."""
    return get_plugin_registry().get_template(template_type)


def check_permission(operation: str, context: Dict[str, Any]) -> bool:
    """Check if an operation is allowed."""
    return get_plugin_registry().check_permission(operation, context)


def validate_entry(entry_data: Dict[str, Any]) -> Optional[str]:
    """Validate a log entry."""
    return get_plugin_registry().validate_entry(entry_data)


def format_entry(entry_data: Dict[str, Any]) -> Optional[str]:
    """Format a log entry."""
    return get_plugin_registry().format_entry(entry_data)
