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

from scribe_mcp.config.downstream_assets import ensure_downstream_seed_assets
from scribe_mcp.config.paths import config_home_dir
from scribe_mcp.config.settings import settings
# Setup structured logging for repository configuration operations
repo_config_logger = logging.getLogger(__name__)
_RESERVED_CREATE_DOC_TYPES = {
    "custom",
    "spec",
    "research",
    "bug",
    "security",
    "review",
    "agent_card",
}
_CANONICAL_DOC_TYPE_ALIASES = {
    "architecture": "custom",
    "phase_plan": "custom",
    "checklist": "custom",
    "synthesis": "custom",
    "progress_log": "custom",
    "work_item": "custom",
    "other": "custom",
    "security_review": "security",
    "bug_rca": "bug",
}


@dataclass(frozen=True)
class DocTypeCreateResolution:
    aliases: Dict[str, str] = field(default_factory=dict)
    templates: Dict[str, str] = field(default_factory=dict)
    template_doc_types: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    source_path: str = "built_in"

_REPO_ENV_OWNED_IGNORE_KEYS = {
    "db_url",
    "postgres_schema",
    "db_schema",
    "postgres_pool_min_size",
    "postgres_pool_max_size",
    "postgres_command_timeout_seconds",
    "postgres_connect_timeout_seconds",
    "postgres_connect_retries",
    "postgres_connect_retry_backoff_seconds",
    "postgres_max_inactive_seconds",
    "postgres_max_inactive_connection_lifetime_seconds",
    "reminder_idle_minutes",
    "reminder_warmup_minutes",
}

_REPO_CREDENTIAL_IGNORE_KEYS = {
    "transport_auth_token",
    "remote_auth_token",
    "object_store_key",
    "db_password",
    "postgres_password",
    "auth_token",
    "api_key",
}


def _canonical_dev_plans_base() -> Path:
    """Return the canonical relative base for per-project docs."""
    return Path(settings.dev_plans_base)


def _default_dev_plans_dir(repo_root: Path) -> Path:
    """Prefer the canonical .scribe home, but preserve legacy trees if they already exist."""
    canonical_path = (repo_root / _canonical_dev_plans_base()).resolve()
    legacy_path = (repo_root / "docs" / "dev_plans").resolve()
    if canonical_path.exists():
        return canonical_path
    if legacy_path.exists():
        return legacy_path
    return canonical_path


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dicts with override values taking precedence."""
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _sanitize_repo_config_data(data: Dict[str, Any], source_label: str) -> Dict[str, Any]:
    """Warn+ignore unsupported env-owned and credential-like repo config keys."""
    cleaned: Dict[str, Any] = {}
    for key, value in data.items():
        normalized = str(key).strip().lower()
        if normalized in _REPO_ENV_OWNED_IGNORE_KEYS:
            repo_config_logger.warning(
                "Ignoring env-owned repo config key '%s' from %s; use runtime env defaults instead.",
                key,
                source_label,
            )
            continue
        if normalized in _REPO_CREDENTIAL_IGNORE_KEYS or (
            "token" in normalized
            or "secret" in normalized
            or "password" in normalized
            or "credential" in normalized
        ):
            repo_config_logger.warning(
                "Ignoring credential-like repo config key '%s' from %s; keep credentials in env/runtime channels.",
                key,
                source_label,
            )
            continue
        cleaned[key] = value
    return cleaned


def _load_structured_config(path: Path) -> Dict[str, Any]:
    """Load yaml/json config data from a path, returning a dict or empty dict."""
    if not path.exists():
        return {}
    try:
        if path.suffix in [".yaml", ".yml"]:
            with open(path, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        else:
            import json

            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        if isinstance(data, dict):
            return data
        return {}
    except Exception as exc:
        repo_config_logger.warning("Failed to load config from %s: %s", path, exc)
        return {}


def _repo_config_paths(repo_root: Path) -> list[Path]:
    """Canonical repo-local config lookup order (excluding global fallback)."""
    return [
        repo_root / ".scribe" / "config" / "scribe.yaml",
        repo_root / ".scribe" / "scribe.yaml",
        repo_root / ".scribe" / "scribe.yml",
        repo_root / "docs" / "dev_plans" / "scribe.yaml",
        repo_root / ".scribe" / "config.json",
    ]


def resolve_repo_runtime_overrides(repo_root: Path) -> Dict[str, Any]:
    """Resolve repo-local runtime override keys allowed by the overlap contract.

    Supported keys:
    - ``storage_backend`` (repo override, lower precedence than env)
    - ``db_path`` (active only when effective backend resolves to sqlite)
    """
    for config_path in _repo_config_paths(repo_root):
        raw = _load_structured_config(config_path)
        if not raw:
            continue
        sanitized = _sanitize_repo_config_data(raw, source_label=str(config_path))
        backend = sanitized.get("storage_backend")
        db_path_raw = sanitized.get("db_path")
        db_path: Optional[Path] = None
        if isinstance(db_path_raw, str) and db_path_raw.strip():
            db_path = (repo_root / Path(db_path_raw)).resolve()
        return {
            "storage_backend": str(backend).strip().lower() if backend else None,
            "db_path": db_path,
            "config_path": config_path,
        }
    return {"storage_backend": None, "db_path": None, "config_path": None}


def resolve_runtime_efficiency_budgets(repo_root: Path | None) -> Dict[str, Dict[str, float]]:
    """Resolve runtime-efficiency budgets from repo config defaults with safe fallbacks."""
    from scribe_mcp.runtime_timing_envelope import DEFAULT_RUNTIME_EFFICIENCY_BUDGETS

    if repo_root is None:
        return dict(DEFAULT_RUNTIME_EFFICIENCY_BUDGETS)

    for config_path in _repo_config_paths(repo_root):
        raw = _load_structured_config(config_path)
        if not raw:
            continue
        sanitized = _sanitize_repo_config_data(raw, source_label=str(config_path))
        defaults = sanitized.get("defaults")
        if not isinstance(defaults, dict):
            continue
        runtime_efficiency = defaults.get("runtime_efficiency")
        if not isinstance(runtime_efficiency, dict):
            continue
        budgets = runtime_efficiency.get("budgets")
        if not isinstance(budgets, dict):
            continue
        merged: Dict[str, Dict[str, float]] = dict(DEFAULT_RUNTIME_EFFICIENCY_BUDGETS)
        for metric_name, threshold in budgets.items():
            if not isinstance(threshold, dict):
                continue
            warn = threshold.get("warn")
            fail = threshold.get("fail")
            if isinstance(warn, (int, float)) and isinstance(fail, (int, float)):
                merged[str(metric_name)] = {"warn": float(warn), "fail": float(fail)}
        return merged
    return dict(DEFAULT_RUNTIME_EFFICIENCY_BUDGETS)


def _extract_doc_type_config_map(repo_config: "RepoConfig") -> tuple[Optional[Dict[str, Any]], str]:
    top_level = getattr(repo_config, "_raw_config", None)
    if isinstance(top_level, dict):
        doc_types = top_level.get("doc_types")
        if isinstance(doc_types, dict):
            return doc_types, "repo_config:doc_types"
    reminder_config = repo_config.reminder_config if isinstance(repo_config.reminder_config, dict) else {}
    doc_types = reminder_config.get("doc_types")
    if isinstance(doc_types, dict):
        return doc_types, "repo_config:reminder_config.doc_types"
    return None, "built_in"


def resolve_create_doc_type_config(repo_config: "RepoConfig") -> DocTypeCreateResolution:
    """Resolve validated create aliases/templates from repo config.

    Primary path: `doc_types.*`
    Compatibility path: `reminder_config.doc_types.*`
    """
    aliases: Dict[str, str] = dict(_CANONICAL_DOC_TYPE_ALIASES)
    templates: Dict[str, str] = {}
    warnings: list[str] = []
    template_doc_types: set[str] = set()
    doc_types, source_path = _extract_doc_type_config_map(repo_config)
    if not isinstance(doc_types, dict):
        return DocTypeCreateResolution(
            aliases=aliases,
            templates=templates,
            template_doc_types=template_doc_types,
            warnings=warnings,
            source_path=source_path,
        )
    raw_aliases = doc_types.get("create_aliases")
    if isinstance(raw_aliases, dict):
        for raw_alias, raw_target in raw_aliases.items():
            alias = str(raw_alias or "").strip().lower()
            target = str(raw_target or "").strip().lower()
            if not alias or not target:
                warnings.append("Ignoring empty create_aliases entry; both alias and target are required.")
                continue
            if alias in _RESERVED_CREATE_DOC_TYPES:
                warnings.append(f"Ignoring create_aliases['{alias}']: alias conflicts with reserved built-in doc_type.")
                continue
            if target not in _RESERVED_CREATE_DOC_TYPES:
                warnings.append(f"Ignoring create_aliases['{alias}']: target '{target}' is not a valid built-in doc_type.")
                continue
            aliases[alias] = target

    raw_templates = doc_types.get("create_templates")
    if isinstance(raw_templates, dict):
        for raw_doc_type, raw_template in raw_templates.items():
            doc_type = str(raw_doc_type or "").strip().lower()
            template = str(raw_template or "").strip()
            if not doc_type or not template:
                warnings.append("Ignoring empty create_templates entry; both doc_type and template are required.")
                continue
            if doc_type in _RESERVED_CREATE_DOC_TYPES:
                warnings.append(f"Ignoring create_templates['{doc_type}']: doc_type is reserved by built-ins.")
                continue
            templates[doc_type] = template
            template_doc_types.add(doc_type)
    return DocTypeCreateResolution(
        aliases=aliases,
        templates=templates,
        template_doc_types=template_doc_types,
        warnings=warnings,
        source_path=source_path,
    )



@dataclass
class RepoConfig:
    """Per-repository configuration for Scribe."""

    # Core repository identification
    repo_slug: str
    repo_root: Path

    # Documentation structure
    dev_plans_dir: Path = field(default_factory=_canonical_dev_plans_base)
    progress_log_name: str = "PROGRESS_LOG.md"
    log_path: Optional[Path] = None
    log_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Template and customization
    templates_pack: str = "default"
    custom_templates_dir: Optional[Path] = None

    # Permissions and constraints
    permissions: Dict[str, bool] = field(default_factory=dict)

    # Plugin configuration
    plugins_dir: Optional[Path] = None
    plugin_config: Dict[str, Any] = field(default_factory=dict)

    # Project defaults
    default_emoji: str = "📋"
    default_agent: str = "Agent"
    reminder_config: Dict[str, Any] = field(default_factory=dict)

    # Hooks configuration
    hooks: Dict[str, Optional[str]] = field(default_factory=dict)

    # Scribe MCP specific settings
    mcp_server_name: str = "scribe.mcp"
    storage_backend: str = "postgres"  # postgres by default; sqlite is explicit standalone
    db_path: Optional[Path] = None  # for sqlite
    doc_snapshots: bool = True
    path_policy: Dict[str, Any] = field(default_factory=dict)

    # Output formatting settings
    use_ansi_colors: bool = True  # Enable ANSI colors in tool output (Phase 1.5 - Issue #9962 fix)

    def allows_outside_repo_reads(self) -> bool:
        """Return the legacy repo-local preference flag.

        Tool-time authorization must still flow through the runtime transport/trust
        policy surface; this flag is not the final outside-repo allow/deny decision.
        """
        permissions = self.permissions if isinstance(self.permissions, dict) else {}
        return bool(
            permissions.get("allow_outside_repo_reads", False)
            or permissions.get("allow_cross_repo_reads", False)
        )

    def plugin_loading_requested(self) -> bool:
        """Return whether repo config requests repo-local plugin loading."""
        plugin_config = self.plugin_config if isinstance(self.plugin_config, dict) else {}
        return bool(plugin_config.get("enabled", False))

    @classmethod
    def from_dict(cls, data: Dict[str, Any], repo_root: Path) -> "RepoConfig":
        """Create RepoConfig from dictionary data."""
        permissions = data.get("permissions", {})
        if not isinstance(permissions, dict):
            permissions = {}

        plugin_config = data.get("plugin_config", {})
        if not isinstance(plugin_config, dict):
            plugin_config = {}

        # Resolve path fields relative to repo root
        dev_plans_dir_value = data.get("dev_plans_dir")
        if dev_plans_dir_value:
            dev_plans_dir = repo_root / Path(dev_plans_dir_value)
        else:
            dev_plans_dir = _default_dev_plans_dir(repo_root)
        log_path = None
        log_path_value = data.get("log_path") or data.get("progress_log_path")
        if log_path_value:
            log_path = Path(str(log_path_value)).expanduser()
            if not log_path.is_absolute():
                log_path = repo_root / log_path
        log_config = data.get("logs") or data.get("log_config") or {}
        if not isinstance(log_config, dict):
            log_config = {}
        custom_templates_dir = None
        if data.get("custom_templates_dir"):
            custom_templates_dir = repo_root / Path(data["custom_templates_dir"])
        plugins_dir = None
        if data.get("plugins_dir"):
            plugins_dir = repo_root / Path(data["plugins_dir"])

        db_path = None
        if data.get("db_path"):
            db_path = repo_root / Path(data["db_path"])

        config = cls(
            repo_slug=data.get("repo_slug", repo_root.name),
            repo_root=repo_root,
            dev_plans_dir=dev_plans_dir,
            progress_log_name=data.get("progress_log_name", "PROGRESS_LOG.md"),
            log_path=log_path,
            log_config=log_config,
            templates_pack=data.get("templates_pack", "default"),
            custom_templates_dir=custom_templates_dir,
            permissions=permissions,
            plugins_dir=plugins_dir,
            plugin_config=plugin_config,
            default_emoji=data.get("default_emoji", "📋"),
            default_agent=data.get("default_agent", "Agent"),
            reminder_config=data.get("reminder_config", {}),
            hooks=data.get("hooks", {}),
            mcp_server_name=data.get("mcp_server_name", "scribe.mcp"),
            storage_backend=data.get("storage_backend", "postgres"),
            db_path=db_path,
            doc_snapshots=bool(data.get("doc_snapshots", True)),
            path_policy=data.get("path_policy") if isinstance(data.get("path_policy"), dict) else {},
            use_ansi_colors=bool(data.get("use_ansi_colors", True)),  # Colors ON by default
        )
        setattr(config, "_raw_config", dict(data))
        return config

    @classmethod
    def defaults_for_repo(cls, repo_root: Path) -> "RepoConfig":
        """Create default RepoConfig for a repository."""
        return cls(
            repo_slug=repo_root.name,
            repo_root=repo_root,
            dev_plans_dir=_default_dev_plans_dir(repo_root),
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
            "log_path": (
                str(self.log_path.relative_to(self.repo_root))
                if self.log_path and self.log_path.is_relative_to(self.repo_root)
                else str(self.log_path) if self.log_path else None
            ),
            "logs": self.log_config,
            "templates_pack": self.templates_pack,
            "permissions": self.permissions,
            "plugin_config": self.plugin_config,
            "default_emoji": self.default_emoji,
            "default_agent": self.default_agent,
            "reminder_config": self.reminder_config,
            "hooks": self.hooks,
            "mcp_server_name": self.mcp_server_name,
            "storage_backend": self.storage_backend,
            "doc_snapshots": self.doc_snapshots,
            "use_ansi_colors": self.use_ansi_colors,
        }
        if self.path_policy:
            result["path_policy"] = self.path_policy

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
    def load_config(repo_root: Path, *, seed_if_missing: bool = True) -> RepoConfig:
        """
        Load Scribe configuration for a repository.

        Search order:
        1. .scribe/config/scribe.yaml
        2. .scribe/scribe.yaml (legacy)
        3. .scribe/scribe.yml (legacy)
        4. docs/dev_plans/scribe.yaml (legacy)
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

        if seed_if_missing and not config_file.exists():
            try:
                if legacy_config.exists():
                    shutil.copy2(legacy_config, config_file)
                    repo_config_logger.info(f"Copied legacy config to {config_file}")
            except Exception as exc:
                repo_config_logger.warning(f"Failed to seed repo config at {config_file}: {exc}")
        if seed_if_missing:
            try:
                seed_result = ensure_downstream_seed_assets(
                    repo_root,
                    asset_ids=("repo_config", "env_example"),
                )
                repo_config_logger.info(
                    "Seeded downstream repo assets for '%s' (seeded=%s adopted=%s refreshed=%s skipped=%s customized=%s errors=%s)",
                    repo_root,
                    seed_result.seeded,
                    seed_result.adopted,
                    seed_result.refreshed,
                    seed_result.skipped,
                    seed_result.customized,
                    seed_result.errors,
                )
            except Exception as exc:
                repo_config_logger.warning(f"Failed to seed downstream assets at {repo_root}: {exc}")

        for config_path in config_paths:
            if config_path.exists():
                try:
                    global_config_path = config_home_dir() / "scribe.yaml"
                    global_data = _load_structured_config(global_config_path)
                    repo_data = _load_structured_config(config_path)
                    sanitized_repo_data = _sanitize_repo_config_data(
                        repo_data,
                        source_label=str(config_path),
                    )
                    data = _merge_dicts(global_data, sanitized_repo_data)
                    canonical_policy_path = repo_root / ".scribe" / "config" / "scribe.yaml"
                    if config_path != canonical_policy_path or "path_policy" not in sanitized_repo_data:
                        data.pop("path_policy", None)

                    repo_config_logger.info(f"Successfully loaded config from {config_path}")
                    return RepoConfig.from_dict(data, repo_root)

                except Exception as e:
                    repo_config_logger.warning(f"Failed to load config from {config_path}: {e}")
                    continue

        # No config found, return defaults
        global_config_path = config_home_dir() / "scribe.yaml"
        global_data = _load_structured_config(global_config_path)
        if global_data:
            global_data.pop("path_policy", None)
            return RepoConfig.from_dict(global_data, repo_root)
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
