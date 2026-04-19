"""Centralized path helpers for Scribe runtime and packaging."""

from __future__ import annotations

import importlib.resources
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_PACKAGE_NAME = "scribe_mcp"
_SCRIBE_DIR_NAME = ".scribe"
_CLI_RUNTIME_DIR_NAME = "cli"
_STATE_RUNTIME_DIR_NAME = "state"
_LOGS_RUNTIME_DIR_NAME = "logs"

CLI_RUNTIME_RELATIVE_PREFIX = f"{_SCRIBE_DIR_NAME}/{_CLI_RUNTIME_DIR_NAME}/"
STATE_RUNTIME_RELATIVE_PREFIX = f"{_SCRIBE_DIR_NAME}/{_STATE_RUNTIME_DIR_NAME}/"
LOGS_RUNTIME_RELATIVE_PREFIX = f"{_SCRIBE_DIR_NAME}/{_LOGS_RUNTIME_DIR_NAME}/"


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def package_root() -> Path:
    """Return the installed package root with robust filesystem fallbacks."""

    try:
        resource_root = importlib.resources.files(_PACKAGE_NAME)
        resource_path = Path(str(resource_root)).expanduser().resolve()
        if resource_path.exists():
            return resource_path
    except Exception:
        # Fall through to module-based resolution.
        pass

    package_module = sys.modules.get(_PACKAGE_NAME)
    package_file = getattr(package_module, "__file__", None)
    if package_file:
        package_path = Path(str(package_file)).expanduser().resolve().parent
        if package_path.exists():
            return package_path

    package_paths = getattr(package_module, "__path__", None)
    if package_paths:
        for entry in package_paths:
            candidate = Path(str(entry)).expanduser().resolve()
            if candidate.exists():
                return candidate

    # Editable installs on some Python versions can fail resource lookup.
    module = sys.modules.get(__name__)
    origin = getattr(getattr(module, "__spec__", None), "origin", None)
    if origin:
        origin_path = Path(str(origin)).expanduser().resolve().parents[1]
        if origin_path.exists():
            return origin_path

    return Path.cwd().resolve()


def repo_root() -> Path:
    """Resolve repository root from env override or package location."""
    override = _env_path("SCRIBE_ROOT")
    if override:
        return override

    pkg_root = package_root()
    if pkg_root.parent.name == "src":
        return pkg_root.parent.parent.resolve()
    return pkg_root.resolve()


def scribe_dir() -> Path:
    """Path to repository-scoped Scribe directory."""
    return repo_root() / _SCRIBE_DIR_NAME


def config_data_dir() -> Path:
    """Directory containing packaged configuration assets."""
    return package_root() / "config"


def packaged_config_asset(relative_path: str | Path) -> Path:
    """Resolve a packaged config asset path relative to ``config_data_dir``."""
    return (config_data_dir() / Path(relative_path)).resolve()


def packaged_template_asset(relative_path: str | Path) -> Path:
    """Resolve a packaged template asset path relative to ``templates_dir``."""
    return (templates_dir() / Path(relative_path)).resolve()


def downstream_seed_manifest_path() -> Path:
    """Return the packaged downstream seed manifest path."""
    return packaged_config_asset("downstream_seed_manifest.yaml")


def templates_dir() -> Path:
    """Directory containing packaged template assets."""
    return package_root() / "templates"


def db_init_sql() -> Path:
    """Path to bootstrap SQL script."""
    return package_root() / "db" / "init.sql"


def postgres_migrations_dir() -> Path:
    """Path to numbered Postgres migration SQL files."""
    return package_root() / "db" / "postgres_migrations"


def user_data_dir() -> Path:
    """Resolve writable data directory (override -> repo -> XDG)."""
    override = _env_path("SCRIBE_DATA_DIR")
    if override:
        return override

    repo_data = repo_root() / "data"
    if repo_data.exists() or os.environ.get("SCRIBE_ROOT"):
        return repo_data.resolve()

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return (Path(xdg_data_home).expanduser() / _PACKAGE_NAME).resolve()

    return (Path.home() / ".local" / "share" / _PACKAGE_NAME).resolve()


def config_home_dir() -> Path:
    """Resolve writable user/global config home (override -> XDG -> ~/.config)."""
    override = _env_path("SCRIBE_CONFIG_DIR")
    if override:
        return override

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return (Path(xdg_config_home).expanduser() / _PACKAGE_NAME).resolve()

    return (Path.home() / ".config" / _PACKAGE_NAME).resolve()


def default_db_path() -> Path:
    """Resolve the default explicit-standalone SQLite DB path with env overrides."""
    db_override = _env_path("SCRIBE_DB_PATH")
    if db_override:
        return db_override

    legacy_override = _env_path("SCRIBE_SQLITE_PATH")
    if legacy_override:
        return legacy_override

    return user_data_dir() / "scribe_projects.db"


def cli_session_dir() -> Path:
    """Directory for persistent CLI session state."""
    return scribe_dir() / _CLI_RUNTIME_DIR_NAME


def runtime_state_dir() -> Path:
    """Directory for repo-local mutable runtime JSON state."""
    return scribe_dir() / _STATE_RUNTIME_DIR_NAME


def runtime_logs_dir() -> Path:
    """Directory for repo-local runtime log output."""
    return scribe_dir() / _LOGS_RUNTIME_DIR_NAME


def cli_session_state_path(session_name: str = "default") -> Path:
    """Path to a named CLI session-state file."""
    safe_name = session_name.strip() or "default"
    safe_name = safe_name.replace("/", "_").replace("\\", "_")
    return cli_session_dir() / f"{safe_name}.json"


def map_client_root(
    client_path: str,
    user: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Map a client-provided repo root to a server-accessible path.

    Enables remote SSE clients to use Scribe when their local filesystem
    paths don't exist on the server (e.g. Docker containers).

    Args:
        client_path: The repo root path as sent by the client.
        user: Explicit user identity (e.g. from Council's ``_scribe_user``).
              Falls back to ``SCRIBE_USER`` env var, then ``"default"``.

    Returns ``(effective_path, original_client_path_or_None)``.

    * Path exists on this filesystem → ``(client_path, None)`` — no mapping.
    * ``SCRIBE_PATH_MAP`` has an explicit match → ``(mapped, client_path)``.
    * Path missing + ``SCRIBE_ROOT`` set → scoped workspace path.
    * Otherwise → ``(client_path, None)`` — no mapping available.

    **Scoping** (user-first, prevents collisions across repos and users)::

        {SCRIBE_ROOT}/workspaces/{user}/{parent}/{repo_name}/

    Where ``user`` is resolved from the ``user`` parameter, ``SCRIBE_USER``
    env var, or ``"default"``.  ``parent/repo_name`` are the last two
    components of the client path (e.g. ``MCP_SPINE/council_mcp``).
    """
    # 1. Explicit multi-repo map (semicolon-separated "client=server" pairs)
    path_map_raw = os.environ.get("SCRIBE_PATH_MAP")
    if path_map_raw:
        for entry in path_map_raw.split(";"):
            entry = entry.strip()
            if "=" not in entry:
                continue
            client_prefix, server_path = entry.split("=", 1)
            client_prefix = client_prefix.strip()
            server_path = server_path.strip()
            if client_path.rstrip("/") == client_prefix.rstrip("/") or client_path.startswith(client_prefix.rstrip("/") + "/"):
                suffix = client_path[len(client_prefix.rstrip("/")):].lstrip("/")
                mapped = str(Path(server_path) / suffix) if suffix else server_path
                logger.info("Path map (explicit): %s → %s", client_path, mapped)
                return (mapped, client_path)

    # 2. Path exists locally — no mapping needed (local dev / stdio)
    if Path(client_path).exists():
        return (client_path, None)

    # 3. Fallback to SCRIBE_ROOT when client path doesn't exist on server.
    #    Hierarchy: workspaces/{user}/{parent}/{repo} — user-first scoping.
    scribe_root = os.environ.get("SCRIBE_ROOT")
    if scribe_root:
        resolved = Path(scribe_root).resolve()
        if resolved.exists():
            # Resolve user identity: explicit param > env var > default
            effective_user = user or os.environ.get("SCRIBE_USER") or "default"

            # Repo scope from last two path components (e.g. MCP_SPINE/council_mcp)
            parts = Path(client_path).parts
            if len(parts) >= 2:
                repo_scope = Path(parts[-2]) / parts[-1]
            else:
                repo_scope = Path(parts[-1] if parts else "unknown")

            mapped = resolved / "workspaces" / effective_user / repo_scope
            logger.info("Path map (SCRIBE_ROOT fallback): %s → %s", client_path, mapped)
            return (str(mapped), client_path)

    # 4. No mapping available
    return (client_path, None)


__all__ = [
    "cli_session_dir",
    "cli_session_state_path",
    "config_home_dir",
    "config_data_dir",
    "db_init_sql",
    "downstream_seed_manifest_path",
    "map_client_root",
    "packaged_config_asset",
    "packaged_template_asset",
    "postgres_migrations_dir",
    "default_db_path",
    "package_root",
    "repo_root",
    "scribe_dir",
    "templates_dir",
    "user_data_dir",
]
