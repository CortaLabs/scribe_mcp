"""Log configuration loader for multi-log append_entry."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from scribe_mcp.config.settings import settings
from scribe_mcp.utils.slug import slugify_project_name as _slugify_project_name

# Setup structured logging for configuration operations
config_logger = logging.getLogger(__name__)

DEFAULT_LOGS: Dict[str, Dict[str, Any]] = {
    "progress": {
        "path": "{progress_log}",
        "metadata_requirements": [],
    },
    "doc_updates": {
        "path": "{docs_dir}/DOC_LOG.md",
        "metadata_requirements": ["doc", "section", "action"],
    },
    "security": {
        "path": "{docs_dir}/SECURITY_LOG.md",
        "metadata_requirements": ["severity", "area", "impact"],
    },
    "bugs": {
        "path": "{docs_dir}/BUG_LOG.md",
        "metadata_requirements": ["severity", "component", "status"],
    },
}


def _effective_repo_root(repo_root: Optional[str | Path] = None) -> Path:
    if repo_root:
        return Path(repo_root).expanduser().resolve()
    configured_root = getattr(settings, "default_repo_root", None)
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    return settings.project_root.resolve()


def _repo_log_config_path(repo_root: Path) -> Path:
    return repo_root / ".scribe" / "config" / "log_config.json"


def _legacy_log_config_path() -> Path:
    return settings.project_root / "config" / "log_config.json"


def _load_json_log_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        config_logger.debug("Successfully loaded log configuration from %s", path)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        config_logger.warning("Log config JSON invalid, ignoring: %s", path)
    except Exception as exc:
        config_logger.error("Failed to read log config at %s: %s", path, exc)
    return {}


def _extract_logs(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    logs = data.get("logs") if isinstance(data, dict) else None
    if not isinstance(logs, dict):
        logs = data
    if not isinstance(logs, dict):
        return {}
    return {key: value for key, value in logs.items() if isinstance(value, dict)}


def _load_repo_yaml_log_config(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    from scribe_mcp.config.repo_config import RepoDiscovery

    config = RepoDiscovery.load_config(repo_root, seed_if_missing=False)
    logs = dict(getattr(config, "log_config", {}) or {})
    log_path = getattr(config, "log_path", None)
    if log_path:
        progress = dict(logs.get("progress") or {})
        progress["path"] = str(Path(log_path).expanduser().resolve())
        logs["progress"] = progress
    return {key: value for key, value in logs.items() if isinstance(value, dict)}


def load_log_config(repo_root: Optional[str | Path] = None) -> Dict[str, Dict[str, Any]]:
    return _load_log_config_cached(str(_effective_repo_root(repo_root)))


@lru_cache(maxsize=32)
def _load_log_config_cached(repo_root_key: str) -> Dict[str, Dict[str, Any]]:
    """Load log configuration, merged with defaults."""
    merged = dict(DEFAULT_LOGS)

    repo_root = Path(repo_root_key).expanduser().resolve()
    for path in (_legacy_log_config_path(), _repo_log_config_path(repo_root)):
        for key, value in _extract_logs(_load_json_log_config(path)).items():
            merged[key] = value

    for key, value in _load_repo_yaml_log_config(repo_root).items():
        merged[key] = value

    return merged


def _write_default_config(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"logs": DEFAULT_LOGS}
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        config_logger.info(f"Successfully wrote default log configuration to {path}")
    except Exception as e:
        config_logger.error(f"Failed to write default log config to {path}: {e}")
        raise


def get_log_definition(log_type: str, repo_root: Optional[str | Path] = None) -> Dict[str, Any]:
    """Return log definition for the given type (defaults to progress)."""
    log_type = (log_type or "progress").lower()
    logs = load_log_config(repo_root)
    return logs.get(log_type) or logs["progress"]


def resolve_log_path(project: Dict[str, Any], definition: Dict[str, Any]) -> Path:
    """Resolve the filesystem path for a log based on project context."""
    path_template = definition.get("path") or "{progress_log}"

    docs_dir = project.get("docs_dir") or (Path(project.get("progress_log", "")).parent if project.get("progress_log") else "")
    if not docs_dir:
        docs_dir = (
            Path(project.get("root", settings.project_root))
            / settings.dev_plans_base
            / _slugify_project_name(project["name"])
        )

    context = {
        "project_slug": _slugify_project_name(project["name"]),
        "PROJECT_SLUG": _slugify_project_name(project["name"]),
        "project_root": project.get("root") or str(settings.project_root),
        "PROJECT_ROOT": project.get("root") or str(settings.project_root),
        "progress_log": project.get("progress_log"),
        "docs_dir": str(docs_dir),
        "DOCS_DIR": str(docs_dir),
    }

    try:
        rendered = path_template.format(**context)
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder {exc} in log path template '{path_template}'")

    resolved = Path(rendered)
    if not resolved.is_absolute():
        root = Path(project.get("root") or settings.project_root)
        resolved = (root / resolved).resolve()
    return resolved
