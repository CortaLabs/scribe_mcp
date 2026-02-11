"""Centralized path helpers for Scribe runtime and packaging."""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path
from typing import Optional

_PACKAGE_NAME = "scribe_mcp"


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def package_root() -> Path:
    """Return the installed package root with editable-install fallback."""
    try:
        return Path(str(importlib.resources.files(_PACKAGE_NAME))).resolve()
    except Exception:
        # Editable installs on some Python versions can fail resource lookup.
        return Path(__file__).resolve().parents[1]


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
    return repo_root() / ".scribe"


def config_data_dir() -> Path:
    """Directory containing packaged configuration assets."""
    return package_root() / "config"


def templates_dir() -> Path:
    """Directory containing packaged template assets."""
    return package_root() / "templates"


def db_init_sql() -> Path:
    """Path to bootstrap SQL script."""
    return package_root() / "db" / "init.sql"


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


def default_db_path() -> Path:
    """Resolve default SQLite DB path with env overrides."""
    db_override = _env_path("SCRIBE_DB_PATH")
    if db_override:
        return db_override

    legacy_override = _env_path("SCRIBE_SQLITE_PATH")
    if legacy_override:
        return legacy_override

    return user_data_dir() / "scribe_projects.db"


def cli_session_dir() -> Path:
    """Directory for persistent CLI session state."""
    return scribe_dir() / "cli"


def cli_session_state_path(session_name: str = "default") -> Path:
    """Path to a named CLI session-state file."""
    safe_name = session_name.strip() or "default"
    safe_name = safe_name.replace("/", "_").replace("\\", "_")
    return cli_session_dir() / f"{safe_name}.json"


__all__ = [
    "cli_session_dir",
    "cli_session_state_path",
    "config_data_dir",
    "db_init_sql",
    "default_db_path",
    "package_root",
    "repo_root",
    "scribe_dir",
    "templates_dir",
    "user_data_dir",
]
