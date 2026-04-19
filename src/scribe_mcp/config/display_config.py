#!/usr/bin/env python3
"""
Display configuration management for global verbosity and output control.

Part of SPEC-TOKEN-003 global optimization strategy. Provides centralized
configuration for verbosity levels, box drawing, tips, path formatting,
and timestamp display across all tools.
"""

from typing import Optional, Dict, Any
from pathlib import Path
import yaml

from scribe_mcp.config.paths import config_home_dir, repo_root


class DisplayConfig:
    """
    Manages display configuration with global defaults and per-tool overrides.

    Loads configuration from .scribe/config/scribe.yaml and provides
    convenient access methods for all display-related settings.

    Configuration Structure:
        display:
          # Global settings
          verbosity: 1  # 0=minimal, 1=standard, 2=verbose
          box_drawing: false
          show_tips: false
          use_relative_paths: true
          timestamp_format: "short"  # short, full, none

          # Per-tool overrides
          list_projects:
            verbosity: 1
            default_format: "readable"

          append_entry:
            show_file_path: true
            filter_default_metadata: true

    Verbosity Levels:
        0 (minimal): Automated workflows, token-constrained environments
        1 (standard): Default, balanced human + token efficiency
        2 (verbose): Maximum detail, debugging, learning
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize DisplayConfig with optional custom config path.

        Args:
            config_path: Path to scribe.yaml config file (optional)
                        Defaults to .scribe/config/scribe.yaml
        """
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if self.config_path:
            config_file = Path(self.config_path)
        else:
            # Try to find .scribe/config/scribe.yaml relative to project
            try:
                from scribe_mcp.config.repo_config import get_current_repo_config
                repo_root_path, _repo_config = get_current_repo_config()
                repo_data: Dict[str, Any] = {}
                repo_config_file = repo_root_path / ".scribe" / "config" / "scribe.yaml"
                if repo_config_file.exists():
                    try:
                        with open(repo_config_file, "r", encoding="utf-8") as handle:
                            loaded_repo = yaml.safe_load(handle) or {}
                        if isinstance(loaded_repo, dict):
                            repo_data = loaded_repo
                    except Exception:
                        repo_data = {}
                global_data: Dict[str, Any] = {}
                global_config = config_home_dir() / "scribe.yaml"
                if global_config.exists():
                    try:
                        with open(global_config, "r", encoding="utf-8") as handle:
                            loaded = yaml.safe_load(handle) or {}
                        if isinstance(loaded, dict):
                            global_data = loaded
                    except Exception:
                        global_data = {}
                self._config = dict(global_data)
                self._config.update(repo_data)  # repo remains authoritative
                if isinstance(global_data.get("display"), dict) and isinstance(repo_data.get("display"), dict):
                    merged_display = dict(global_data["display"])
                    merged_display.update(repo_data["display"])
                    self._config["display"] = merged_display
                return
            except Exception:
                # Fallback to default search
                possible_paths = [
                    Path.cwd() / ".scribe" / "config" / "scribe.yaml",
                    repo_root() / ".scribe" / "config" / "scribe.yaml",
                    Path.home() / ".scribe" / "config" / "scribe.yaml",
                ]
                config_file = None
                for path in possible_paths:
                    if path.exists():
                        config_file = path
                        break

        # Load YAML if file found
        if config_file and config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    self._config = yaml.safe_load(f) or {}
            except Exception:
                # Failed to load config, use empty dict
                self._config = {}
        else:
            # No config file found, use empty dict
            self._config = {}

    def _get_display_config(self) -> Dict[str, Any]:
        """Get the display section of config."""
        return self._config.get("display", {})

    def _get_tool_config(self, tool_name: str) -> Dict[str, Any]:
        """Get tool-specific configuration."""
        display_config = self._get_display_config()
        return display_config.get(tool_name, {})

    def get_verbosity(self, tool_name: Optional[str] = None) -> int:
        """
        Get verbosity level for a tool (or global default).

        Args:
            tool_name: Tool name for per-tool override (optional)

        Returns:
            Verbosity level (0=minimal, 1=standard, 2=verbose)
            Default: 1 (standard)
        """
        # Check tool-specific override first
        if tool_name:
            tool_config = self._get_tool_config(tool_name)
            if "verbosity" in tool_config:
                return tool_config["verbosity"]

        # Fall back to global setting
        display_config = self._get_display_config()
        return display_config.get("verbosity", 1)  # Default: standard

    def should_show_tips(self, tool_name: Optional[str] = None) -> bool:
        """
        Check if tips should be shown for a tool (or global default).

        Args:
            tool_name: Tool name for per-tool override (optional)

        Returns:
            True if tips should be shown, False otherwise
            Default: False (tips off per SPEC-TOKEN-003)
        """
        # Check tool-specific override first
        if tool_name:
            tool_config = self._get_tool_config(tool_name)
            if "show_tips" in tool_config:
                return tool_config["show_tips"]

        # Fall back to global setting
        display_config = self._get_display_config()
        return display_config.get("show_tips", False)  # Default: off

    def should_use_box_drawing(self, tool_name: Optional[str] = None) -> bool:
        """
        Check if box drawing should be used for a tool (or global default).

        Args:
            tool_name: Tool name for per-tool override (optional)

        Returns:
            True if box drawing should be used, False otherwise
            Default: False (box drawing off per SPEC-TOKEN-003)
        """
        # Check tool-specific override first
        if tool_name:
            tool_config = self._get_tool_config(tool_name)
            if "box_drawing" in tool_config:
                return tool_config["box_drawing"]

        # Fall back to global setting
        display_config = self._get_display_config()
        return display_config.get("box_drawing", False)  # Default: off

    def get_path_format(self, tool_name: Optional[str] = None) -> str:
        """
        Get path format preference for a tool (or global default).

        Args:
            tool_name: Tool name for per-tool override (optional)

        Returns:
            Path format: "relative", "absolute", or "auto"
            Default: "relative" (use relative paths per SPEC-TOKEN-003)
        """
        # Check tool-specific override first
        if tool_name:
            tool_config = self._get_tool_config(tool_name)
            if "path_format" in tool_config:
                return tool_config["path_format"]

        # Fall back to global setting
        display_config = self._get_display_config()
        use_relative = display_config.get("use_relative_paths", True)
        return "relative" if use_relative else "absolute"

    def get_timestamp_format(self, tool_name: Optional[str] = None) -> str:
        """
        Get timestamp format preference for a tool (or global default).

        Args:
            tool_name: Tool name for per-tool override (optional)

        Returns:
            Timestamp format: "short", "full", or "none"
            Default: "short" (HH:MM UTC per SPEC-TOKEN-003)
        """
        # Check tool-specific override first
        if tool_name:
            tool_config = self._get_tool_config(tool_name)
            if "timestamp_format" in tool_config:
                return tool_config["timestamp_format"]

        # Fall back to global setting
        display_config = self._get_display_config()
        return display_config.get("timestamp_format", "short")  # Default: short

    def get_tool_setting(
        self,
        setting_name: str,
        tool_name: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """
        Get a specific display setting for a tool.

        Args:
            setting_name: Name of the setting to retrieve
            tool_name: Tool name for per-tool override (optional)
            default: Default value if setting not found

        Returns:
            Setting value or default
        """
        # Check tool-specific setting first
        if tool_name:
            tool_config = self._get_tool_config(tool_name)
            if setting_name in tool_config:
                return tool_config[setting_name]

        # Fall back to global setting
        display_config = self._get_display_config()
        return display_config.get(setting_name, default)


# Global instance for convenience
_display_config_instance: Optional[DisplayConfig] = None


def get_display_config() -> DisplayConfig:
    """
    Get or create the global DisplayConfig instance.

    Returns:
        Global DisplayConfig instance
    """
    global _display_config_instance
    if _display_config_instance is None:
        _display_config_instance = DisplayConfig()
    return _display_config_instance
