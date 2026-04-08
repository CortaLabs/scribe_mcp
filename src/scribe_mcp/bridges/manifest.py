"""Bridge manifest schema and configuration models."""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any
import os
import json


class BridgeState(Enum):
    """Bridge lifecycle states."""
    REGISTERED = "registered"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    UNREGISTERED = "unregistered"


@dataclass
class LogTypeConfig:
    """Configuration for a custom log type."""
    log_type: str
    path_template: str
    format: str = "markdown"  # markdown|jsonl
    metadata_requirements: List[str] = field(default_factory=list)
    rotation_threshold: Optional[int] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "log_type": self.log_type,
            "path_template": self.path_template,
            "format": self.format,
            "metadata_requirements": self.metadata_requirements,
            "rotation_threshold": self.rotation_threshold,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogTypeConfig":
        """Create from dictionary."""
        return cls(
            log_type=data["log_type"],
            path_template=data["path_template"],
            format=data.get("format", "markdown"),
            metadata_requirements=data.get("metadata_requirements", []),
            rotation_threshold=data.get("rotation_threshold"),
            description=data.get("description", ""),
        )


@dataclass
class HookConfig:
    """Configuration for a bridge hook."""
    hook_name: str
    callback_type: str = "async"  # sync|async|webhook
    timeout_ms: int = 5000
    critical: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hook_name": self.hook_name,
            "callback_type": self.callback_type,
            "timeout_ms": self.timeout_ms,
            "critical": self.critical,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, hook_name: Optional[str] = None) -> "HookConfig":
        """Create from dictionary.

        Supports both explicit `hook_name` in each hook config and keyed-hook
        manifests where the dictionary key is the hook name.
        """
        resolved_hook_name = data.get("hook_name") or hook_name
        if not resolved_hook_name:
            raise KeyError("hook_name")

        return cls(
            hook_name=resolved_hook_name,
            callback_type=data.get("callback_type", "async"),
            timeout_ms=data.get("timeout_ms", 5000),
            critical=data.get("critical", False),
        )


@dataclass
class BridgeProjectConfig:
    """Project management configuration for a bridge."""
    can_create_projects: bool = False
    project_prefix: Optional[str] = None
    auto_tag: List[str] = field(default_factory=list)
    default_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "can_create_projects": self.can_create_projects,
            "project_prefix": self.project_prefix,
            "auto_tag": self.auto_tag,
            "default_metadata": self.default_metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BridgeProjectConfig":
        """Create from dictionary."""
        return cls(
            can_create_projects=data.get("can_create_projects", False),
            project_prefix=data.get("project_prefix"),
            auto_tag=data.get("auto_tag", []),
            default_metadata=data.get("default_metadata", {}),
        )


@dataclass
class BridgeValidationConfig:
    """Validation configuration for a bridge."""
    mode: str = "lenient"  # strict|lenient|custom
    schema: Optional[Dict[str, Any]] = None
    custom_validator: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mode": self.mode,
            "schema": self.schema,
            "custom_validator": self.custom_validator,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BridgeValidationConfig":
        """Create from dictionary."""
        return cls(
            mode=data.get("mode", "lenient"),
            schema=data.get("schema"),
            custom_validator=data.get("custom_validator"),
        )


@dataclass
class BridgeManifest:
    """Complete bridge manifest configuration."""
    bridge_id: str
    name: str
    version: str
    description: str
    author: str
    plugin_factory: Optional[str] = None
    log_config: Dict[str, LogTypeConfig] = field(default_factory=dict)
    hooks: Dict[str, HookConfig] = field(default_factory=dict)
    project_config: BridgeProjectConfig = field(default_factory=BridgeProjectConfig)
    validation: BridgeValidationConfig = field(default_factory=BridgeValidationConfig)
    api_key: Optional[str] = None
    permissions: List[str] = field(default_factory=list)
    min_scribe_version: str = "2.1.0"
    max_scribe_version: Optional[str] = None

    def validate(self) -> List[str]:
        """
        Validate manifest configuration.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Required fields
        if not self.bridge_id:
            errors.append("bridge_id is required")
        if not self.name:
            errors.append("name is required")
        if not self.version:
            errors.append("version is required")

        # Validate bridge_id format (alphanumeric, hyphens, underscores only)
        if self.bridge_id and not all(c.isalnum() or c in ("-", "_") for c in self.bridge_id):
            errors.append("bridge_id must contain only alphanumeric characters, hyphens, and underscores")

        if self.plugin_factory and ":" not in self.plugin_factory:
            errors.append("plugin_factory must use 'module:attribute' syntax")

        # Validate log_config
        for log_type, config in self.log_config.items():
            if not config.log_type:
                errors.append(f"log_type is required for log config entry '{log_type}'")
            if not config.path_template:
                errors.append(f"path_template is required for log config '{log_type}'")
            if config.format not in ("markdown", "jsonl"):
                errors.append(f"Invalid format '{config.format}' for log config '{log_type}' (must be 'markdown' or 'jsonl')")

        # Validate hooks
        for hook_name, config in self.hooks.items():
            if not config.hook_name:
                errors.append(f"hook_name is required for hook config entry '{hook_name}'")
            if config.callback_type not in ("sync", "async", "webhook"):
                errors.append(f"Invalid callback_type '{config.callback_type}' for hook '{hook_name}' (must be 'sync', 'async', or 'webhook')")
            if config.timeout_ms <= 0:
                errors.append(f"timeout_ms must be positive for hook '{hook_name}'")

        # Validate validation config
        if self.validation.mode not in ("strict", "lenient", "custom"):
            errors.append(f"Invalid validation mode '{self.validation.mode}' (must be 'strict', 'lenient', or 'custom')")
        if self.validation.mode == "custom" and not self.validation.custom_validator:
            errors.append("custom_validator is required when validation mode is 'custom'")

        return errors

    def expand_env_vars(self) -> None:
        """
        Expand environment variables in api_key.

        Supports ${VAR_NAME} syntax. If variable is not found,
        api_key will be set to None.
        """
        if self.api_key and self.api_key.startswith("${") and self.api_key.endswith("}"):
            var_name = self.api_key[2:-1]
            self.api_key = os.environ.get(var_name)

    def to_json(self) -> str:
        """
        Serialize manifest to JSON string.

        Returns:
            JSON string representation
        """
        data = {
            "bridge_id": self.bridge_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "plugin_factory": self.plugin_factory,
            "log_config": {k: v.to_dict() for k, v in self.log_config.items()},
            "hooks": {k: v.to_dict() for k, v in self.hooks.items()},
            "project_config": self.project_config.to_dict(),
            "validation": self.validation.to_dict(),
            "api_key": self.api_key,
            "permissions": self.permissions,
            "min_scribe_version": self.min_scribe_version,
            "max_scribe_version": self.max_scribe_version,
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BridgeManifest":
        """
        Create manifest from dictionary (parsed YAML/JSON).

        Args:
            data: Dictionary containing manifest configuration

        Returns:
            BridgeManifest instance
        """
        # Parse nested configs
        log_config = {}
        for log_type, config_data in data.get("log_config", {}).items():
            log_config[log_type] = LogTypeConfig.from_dict(config_data)

        hooks = {}
        for hook_name, hook_data in data.get("hooks", {}).items():
            hooks[hook_name] = HookConfig.from_dict(hook_data, hook_name=hook_name)

        project_config = BridgeProjectConfig.from_dict(data.get("project_config", {}))
        validation = BridgeValidationConfig.from_dict(data.get("validation", {}))

        return cls(
            bridge_id=data["bridge_id"],
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data["author"],
            plugin_factory=data.get("plugin_factory"),
            log_config=log_config,
            hooks=hooks,
            project_config=project_config,
            validation=validation,
            api_key=data.get("api_key"),
            permissions=data.get("permissions", []),
            min_scribe_version=data.get("min_scribe_version", "2.1.0"),
            max_scribe_version=data.get("max_scribe_version"),
        )
