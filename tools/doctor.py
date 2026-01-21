"""Scribe doctor tool for runtime diagnostics."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from scribe_mcp.server import app
from scribe_mcp.config.settings import settings
from scribe_mcp.config.repo_config import RepoDiscovery


def _get_vector_indexer() -> Any:
    try:
        from scribe_mcp.plugins.registry import get_plugin_registry

        registry = get_plugin_registry()
        for plugin in registry.plugins.values():
            if getattr(plugin, "name", None) == "vector_indexer":
                return plugin
    except Exception:
        return None
    return None


def _safe_bool(value: Any) -> bool:
    return bool(value)


@app.tool()
async def scribe_doctor(agent: str) -> Dict[str, Any]:
    """Return runtime diagnostics for the current MCP server instance."""
    repo_root = settings.project_root
    repo_root_str = str(repo_root) if repo_root else None
    module_root = Path(__file__).resolve().parent.parent
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
    vector_indexer = _get_vector_indexer()
    plugin_info["vector_indexer_present"] = vector_indexer is not None
    if vector_indexer is not None:
        plugin_info["vector_indexer_initialized"] = _safe_bool(
            getattr(vector_indexer, "initialized", False)
        )
        plugin_info["vector_indexer_enabled"] = _safe_bool(
            getattr(vector_indexer, "enabled", False)
        )
        plugin_info["vector_indexer_repo_root"] = str(
            getattr(vector_indexer, "repo_root", "") or ""
        ) or None
        plugin_info["vector_indexer_repo_slug"] = getattr(vector_indexer, "repo_slug", None)

    try:
        from scribe_mcp.plugins.vector_indexer import FAISS_AVAILABLE
    except Exception:
        FAISS_AVAILABLE = False

    config_view = None
    if config is not None:
        config_view = {
            "repo_slug": config.repo_slug,
            "repo_root": str(config.repo_root),
            "plugins_dir": str(config.plugins_dir) if config.plugins_dir else None,
            "plugin_config_enabled": _safe_bool((config.plugin_config or {}).get("enabled")),
            "vector_index_docs": _safe_bool(getattr(config, "vector_index_docs", False)),
            "vector_index_logs": _safe_bool(getattr(config, "vector_index_logs", False)),
        }

    return {
        "ok": True,
        "repo_root": repo_root_str,
        "module_root": str(module_root),
        "cwd": str(cwd),
        "env": {
            "SCRIBE_ROOT": os.environ.get("SCRIBE_ROOT"),
            "SCRIBE_STATE_PATH": os.environ.get("SCRIBE_STATE_PATH"),
        },
        "repo_root_candidates": {
            "from_settings": repo_root_str,
            "from_module_root": str(module_root),
            "from_cwd": str(cwd),
            "from_discovery": str(RepoDiscovery.find_repo_root(cwd) or ""),
        },
        "config": config_view,
        "config_path": str(config_path) if config_path else None,
        "config_error": config_error,
        "vector_deps_available": _safe_bool(FAISS_AVAILABLE),
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
