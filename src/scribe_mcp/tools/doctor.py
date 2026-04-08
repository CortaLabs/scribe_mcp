"""Scribe doctor tool for runtime diagnostics."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.config.settings import settings
from scribe_mcp.config.repo_config import RepoDiscovery
from scribe_mcp.tool_contracts import read_only_local_tool
from scribe_mcp.plugins.registry import get_plugin_registry


def _list_loaded_plugins() -> list[str]:
    try:
        registry = get_plugin_registry()
    except Exception:
        return []
    return sorted(registry.plugins.keys())


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _redact_db_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        path = parts.path or ""
        netloc = f"***@{host}{port}" if host else "***"
        return urlunsplit((parts.scheme, netloc, path, "", ""))
    except Exception:
        return "<configured>"


def _backend_name(value: Any) -> str | None:
    if value is None:
        return None
    return type(value).__name__


@app.tool(**read_only_local_tool(title="Scribe Doctor", tags=("diagnostics", "runtime", "read-only")))
async def scribe_doctor(agent: str) -> Dict[str, Any]:
    """Return runtime diagnostics for the current MCP server instance."""
    repo_root = settings.project_root
    repo_root_str = str(repo_root) if repo_root else None
    module_root = Path(settings.project_root)
    cwd = Path.cwd()
    config = None
    config_error = None
    config_path = None
    if repo_root:
        try:
            config = RepoDiscovery.load_config(Path(repo_root))
            config_path = _detect_config_path(Path(repo_root))
        except Exception as exc:  # pragma: no cover - defensive
            config_error = str(exc)

    plugin_info: Dict[str, Any] = {}
    loaded_plugins = _list_loaded_plugins()
    plugin_info["loaded"] = loaded_plugins
    plugin_info["count"] = len(loaded_plugins)

    runtime_storage_backend = getattr(server_module, "storage_backend", None)
    runtime_state_manager = getattr(server_module, "state_manager", None)
    runtime_router_context_manager = getattr(server_module, "router_context_manager", None)
    runtime_exec_context = None
    try:
        runtime_exec_context = server_module.get_execution_context()
    except Exception:
        runtime_exec_context = None

    config_view = None
    if config is not None:
        config_view = {
            "repo_slug": config.repo_slug,
            "repo_root": str(config.repo_root),
            "plugins_dir": str(config.plugins_dir) if config.plugins_dir else None,
            "plugin_config_enabled": _safe_bool((config.plugin_config or {}).get("enabled")),
            "storage_backend": config.storage_backend,
            "doc_snapshots": _safe_bool(config.doc_snapshots),
        }

    return {
        "ok": True,
        "repo_root": repo_root_str,
        "module_root": str(module_root),
        "cwd": str(cwd),
        "env": {
            "SCRIBE_ROOT": os.environ.get("SCRIBE_ROOT"),
            "SCRIBE_STATE_PATH": os.environ.get("SCRIBE_STATE_PATH"),
            "SCRIBE_STORAGE_BACKEND": os.environ.get("SCRIBE_STORAGE_BACKEND"),
            "SCRIBE_DB_URL_set": bool(os.environ.get("SCRIBE_DB_URL")),
            "SCRIBE_ALLOW_SQLITE_WITH_DB_URL": os.environ.get("SCRIBE_ALLOW_SQLITE_WITH_DB_URL"),
            "SCRIBE_MODE": os.environ.get("SCRIBE_MODE"),
            "SCRIBE_REMOTE_URL": os.environ.get("SCRIBE_REMOTE_URL"),
        },
        "repo_root_candidates": {
            "from_settings": repo_root_str,
            "from_module_root": str(module_root),
            "from_cwd": str(cwd),
            "from_discovery": str(RepoDiscovery.find_repo_root(cwd) or ""),
        },
        "settings": {
            "project_root": repo_root_str,
            "dotenv_path": str((repo_root / ".env").resolve()) if repo_root else None,
            "dotenv_exists": bool(repo_root and (repo_root / ".env").exists()),
            "storage_backend": settings.storage_backend,
            "db_url_set": bool(settings.db_url),
            "db_url_redacted": _redact_db_url(settings.db_url),
            "mode": settings.mode,
            "remote_server_url": settings.remote_server_url,
            "remote_auth_configured": bool(settings.remote_auth_token),
            "sqlite_path": str(settings.sqlite_path),
            "postgres_schema": settings.postgres_schema,
        },
        "runtime": {
            "storage_backend": _backend_name(runtime_storage_backend),
            "state_manager_backend": _backend_name(
                getattr(runtime_state_manager, "_storage_backend", None)
            ),
            "router_context_backend": _backend_name(
                getattr(runtime_router_context_manager, "_storage_backend", None)
            ),
            "execution_context": {
                "repo_root": getattr(runtime_exec_context, "repo_root", None),
                "mode": getattr(runtime_exec_context, "mode", None),
                "session_id": getattr(runtime_exec_context, "session_id", None),
                "stable_session_id": getattr(runtime_exec_context, "stable_session_id", None),
                "transport_session_id": getattr(runtime_exec_context, "transport_session_id", None),
            } if runtime_exec_context else None,
        },
        "config": config_view,
        "config_path": str(config_path) if config_path else None,
        "config_error": config_error,
        "plugins": plugin_info,
    }


def _detect_config_path(repo_root: Path) -> Path | None:
    config_paths = [
        repo_root / ".scribe" / "config" / "scribe.yaml",
        repo_root / ".scribe" / "scribe.yaml",
        repo_root / ".scribe" / "scribe.yml",
        repo_root / "docs" / "dev_plans" / "scribe.yaml",
        repo_root / ".scribe" / "config.json",
    ]
    for candidate in config_paths:
        if candidate.exists():
            return candidate
    return None
