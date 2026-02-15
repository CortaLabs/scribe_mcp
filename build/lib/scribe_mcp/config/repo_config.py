"""Repository discovery and configuration management for global Scribe deployment.

This module enables Scribe to automatically detect the current repository root
and load per-repository configuration, making it a true drop-in MCP solution.
"""

from __future__ import annotations

import logging
import shutil
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from scribe_mcp.config.settings import settings
# Setup structured logging for repository configuration operations
repo_config_logger = logging.getLogger(__name__)



@dataclass
class RepoConfig:
    """Per-repository configuration for Scribe."""

    # Core repository identification
    repo_slug: str
    repo_root: Path

    # Documentation structure
    dev_plans_dir: Path = field(default_factory=lambda: Path("docs/dev_plans"))
    progress_log_name: str = "PROGRESS_LOG.md"

    # Template and customization
    templates_pack: str = "default"
    custom_templates_dir: Optional[Path] = None

    # Permissions and constraints
    permissions: Dict[str, bool] = field(default_factory=dict)

    # Plugin configuration
    plugins_dir: Optional[Path] = None
    plugin_config: Dict[str, Any] = field(default_factory=dict)
    vector_index_docs: bool = False
    vector_index_logs: bool = False
    vector_search_doc_k: int = 5
    vector_search_log_k: int = 3

    # Project defaults
    default_emoji: str = "📋"
    default_agent: str = "Agent"
    reminder_config: Dict[str, Any] = field(default_factory=dict)

    # Hooks configuration
    hooks: Dict[str, Optional[str]] = field(default_factory=dict)

    # Scribe MCP specific settings
    mcp_server_name: str = "scribe.mcp"
    storage_backend: str = "sqlite"  # sqlite or postgres
    db_path: Optional[Path] = None  # for sqlite
    doc_snapshots: bool = True

    # Output formatting settings
    use_ansi_colors: bool = True  # Enable ANSI colors in tool output (Phase 1.5 - Issue #9962 fix)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], repo_root: Path) -> "RepoConfig":
        """Create RepoConfig from dictionary data."""
        # Resolve path fields relative to repo root
        dev_plans_dir = repo_root / Path(data.get("dev_plans_dir", "docs/dev_plans"))
        custom_templates_dir = None
        if data.get("custom_templates_dir"):
            custom_templates_dir = repo_root / Path(data["custom_templates_dir"])
        plugins_dir = None
        if data.get("plugins_dir"):
            plugins_dir = repo_root / Path(data["plugins_dir"])

        db_path = None
        if data.get("db_path"):
            db_path = repo_root / Path(data["db_path"])

        def _safe_int(value: Any, fallback: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return fallback

        return cls(
            repo_slug=data.get("repo_slug", repo_root.name),
            repo_root=repo_root,
            dev_plans_dir=dev_plans_dir,
            progress_log_name=data.get("progress_log_name", "PROGRESS_LOG.md"),
            templates_pack=data.get("templates_pack", "default"),
            custom_templates_dir=custom_templates_dir,
            permissions=data.get("permissions", {}),
            plugins_dir=plugins_dir,
            plugin_config=data.get("plugin_config", {}),
            vector_index_docs=bool(data.get("vector_index_docs", False)),
            vector_index_logs=bool(data.get("vector_index_logs", False)),
            vector_search_doc_k=_safe_int(data.get("vector_search_doc_k", 5), 5),
            vector_search_log_k=_safe_int(data.get("vector_search_log_k", 3), 3),
            default_emoji=data.get("default_emoji", "📋"),
            default_agent=data.get("default_agent", "Agent"),
            reminder_config=data.get("reminder_config", {}),
            hooks=data.get("hooks", {}),
            mcp_server_name=data.get("mcp_server_name", "scribe.mcp"),
            storage_backend=data.get("storage_backend", "sqlite"),
            db_path=db_path,
            doc_snapshots=bool(data.get("doc_snapshots", True)),
            use_ansi_colors=bool(data.get("use_ansi_colors", True)),  # Colors ON by default
        )

    @classmethod
    def defaults_for_repo(cls, repo_root: Path) -> "RepoConfig":
        """Create default RepoConfig for a repository."""
        return cls(
            repo_slug=repo_root.name,
            repo_root=repo_root,
            dev_plans_dir=repo_root / "docs/dev_plans",
            vector_index_docs=False,
            vector_index_logs=False,
            vector_search_doc_k=5,
            vector_search_log_k=3,
        )

    @classmethod
    def from_directory(cls, repo_root: Path) -> "RepoConfig":
        """Load RepoConfig for a specific repository root."""
        repo_root = repo_root.resolve()
        config = RepoDiscovery.load_config(repo_root)
        # Ensure base docs directory exists to match discovery expectations.
        config.dev_plans_dir.mkdir(parents=True, exist_ok=True)
        return config

    def to_dict(self) -> Dict[str, Any]:
        """Convert RepoConfig to dictionary for serialization."""
        result = {
            "repo_slug": self.repo_slug,
            "repo_root": str(self.repo_root),
            "dev_plans_dir": str(self.dev_plans_dir.relative_to(self.repo_root)),
            "progress_log_name": self.progress_log_name,
            "templates_pack": self.templates_pack,
            "permissions": self.permissions,
            "plugin_config": self.plugin_config,
            "vector_index_docs": self.vector_index_docs,
            "vector_index_logs": self.vector_index_logs,
            "vector_search_doc_k": self.vector_search_doc_k,
            "vector_search_log_k": self.vector_search_log_k,
            "default_emoji": self.default_emoji,
            "default_agent": self.default_agent,
            "reminder_config": self.reminder_config,
            "hooks": self.hooks,
            "mcp_server_name": self.mcp_server_name,
            "storage_backend": self.storage_backend,
            "doc_snapshots": self.doc_snapshots,
            "use_ansi_colors": self.use_ansi_colors,
        }

        if self.custom_templates_dir:
            result["custom_templates_dir"] = str(self.custom_templates_dir.relative_to(self.repo_root))
        if self.plugins_dir:
            result["plugins_dir"] = str(self.plugins_dir.relative_to(self.repo_root))
        if self.db_path:
            result["db_path"] = str(self.db_path.relative_to(self.repo_root))

        return result

    def get_progress_log_path(self, project_name: Optional[str] = None) -> Path:
        """Get the full path to the progress log for a project."""
        if project_name:
            return self.dev_plans_dir / project_name / self.progress_log_name
        return self.dev_plans_dir / self.repo_slug / self.progress_log_name

    def get_project_docs_dir(self, project_name: str) -> Path:
        """Get the full path to a project's documentation directory."""
        return self.dev_plans_dir / project_name


class RepoDiscovery:
    """Repository discovery and configuration loading."""

    @staticmethod
    def find_repo_root(start_path: Optional[Path] = None) -> Optional[Path]:
        """
        Find the repository root by searching up from start_path.

        Looks for:
        - .git directory
        - .scribe directory (Scribe-specific marker)
        - pyproject.toml (Python project marker)
        - package.json (Node.js project marker)

        Args:
            start_path: Path to start searching from (defaults to current working directory)

        Returns:
            Repository root path or None if not found
        """
        if start_path is None:
            start_path = Path.cwd()

        current = start_path.resolve()

        # Walk up the directory tree
        while current != current.parent:
            # Check for repository markers
            markers = [
                ".git",
                ".scribe",  # Scribe-specific marker
                "pyproject.toml",
                "package.json",
                "Cargo.toml",
                "go.mod",
            ]

            for marker in markers:
                if (current / marker).exists():
                    return current

            # Check for scribe config file directly
            if (current / ".scribe" / "scribe.yaml").exists():
                return current
            if (current / ".scribe" / "config" / "scribe.yaml").exists():
                return current

            current = current.parent

        # Check root directory as last resort
        for marker in [".git", ".scribe", "pyproject.toml", "package.json"]:
            if (current / marker).exists():
                return current

        return None

    @staticmethod
    def load_config(repo_root: Path) -> RepoConfig:
        """
        Load Scribe configuration for a repository.

        Search order:
        1. .scribe/config/scribe.yaml
        2. .scribe/scribe.yaml (legacy)
        3. .scribe/scribe.yml (legacy)
        4. docs/dev_plans/scribe.yaml
        5. .scribe/config.json
        6. Create default config

        Args:
            repo_root: Repository root path

        Returns:
            Loaded or default RepoConfig
        """
        config_paths = [
            repo_root / ".scribe" / "config" / "scribe.yaml",
            repo_root / ".scribe" / "scribe.yaml",
            repo_root / ".scribe" / "scribe.yml",
            repo_root / "docs" / "dev_plans" / "scribe.yaml",
            repo_root / ".scribe" / "config.json",
        ]

        config_dir = repo_root / ".scribe" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "scribe.yaml"
        legacy_config = repo_root / ".scribe" / "scribe.yaml"
        template_path = settings.project_root / "config" / "scribe_config_template.yaml"

        if not config_file.exists():
            try:
                if legacy_config.exists():
                    shutil.copy2(legacy_config, config_file)
                    repo_config_logger.info(f"Copied legacy config to {config_file}")
                elif template_path.exists():
                    shutil.copy2(template_path, config_file)
                    repo_config_logger.info(f"Seeded repo config from template at {config_file}")
            except Exception as exc:
                repo_config_logger.warning(f"Failed to seed repo config at {config_file}: {exc}")

        for config_path in config_paths:
            if config_path.exists():
                try:
                    if config_path.suffix in ['.yaml', '.yml']:
                        with open(config_path, 'r') as f:
                            data = yaml.safe_load(f) or {}
                    else:  # JSON
                        import json
                        with open(config_path, 'r') as f:
                            data = json.load(f)

                    repo_config_logger.info(f"Successfully loaded config from {config_path}")
                    return RepoConfig.from_dict(data, repo_root)

                except Exception as e:
                    repo_config_logger.warning(f"Failed to load config from {config_path}: {e}")
                    continue

        # No config found, return defaults
        return RepoConfig.defaults_for_repo(repo_root)

    @staticmethod
    def ensure_config(repo_root: Path, config: RepoConfig) -> None:
        """
        Ensure Scribe configuration exists in repository.

        Creates .scribe directory and scribe.yaml if they don't exist.

        Args:
            repo_root: Repository root path
            config: Configuration to save
        """
        scribe_dir = repo_root / ".scribe"
        scribe_dir.mkdir(parents=True, exist_ok=True)

        config_dir = scribe_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "scribe.yaml"

        if not config_file.exists():
            try:
                with open(config_file, 'w') as f:
                    yaml.dump(config.to_dict(), f, default_flow_style=False, indent=2)
                repo_config_logger.info(f"Successfully created Scribe config at {config_file}")
            except Exception as e:
                repo_config_logger.error(f"Failed to create config file: {e}")
                raise

    @staticmethod
    def discover_or_create(start_path: Optional[Path] = None) -> Tuple[Path, RepoConfig]:
        """
        Discover repository and load or create configuration.

        Args:
            start_path: Path to start discovery from (defaults to cwd)

        Returns:
            Tuple of (repo_root, config)

        Raises:
            RuntimeError: If no repository root can be found
        """
        repo_root = RepoDiscovery.find_repo_root(start_path)
        if not repo_root:
            raise RuntimeError(
                f"Could not find repository root starting from {start_path or Path.cwd()}. "
                "Create a .git repository or add a .scribe directory to mark this as a project."
            )

        config = RepoDiscovery.load_config(repo_root)

        # Ensure basic structure exists
        config.dev_plans_dir.mkdir(parents=True, exist_ok=True)

        return repo_root, config


# Global cache for discovered configuration
_current_repo_config: Optional[Tuple[Path, RepoConfig]] = None


def get_current_repo_config(refresh: bool = False) -> Tuple[Path, RepoConfig]:
    """
    Get the current repository configuration, with caching.

    Args:
        refresh: Force rediscovery even if cached

    Returns:
        Tuple of (repo_root, config)
    """
    global _current_repo_config

    if refresh or _current_repo_config is None:
        _current_repo_config = RepoDiscovery.discover_or_create()

    return _current_repo_config


def reload_repo_config() -> Tuple[Path, RepoConfig]:
    """Force reload of repository configuration."""
    return get_current_repo_config(refresh=True)
