"""Shared helpers for project discovery and validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from scribe_mcp.config.settings import settings
from scribe_mcp.state import StateManager
from scribe_mcp.utils.slug import slugify_project_name, normalize_project_input  # Re-export for backwards compat

PROJECTS_DIR = settings.project_root / "config" / "projects"
_PROJECT_CACHE: Dict[Path, Tuple[float, Dict[str, Any]]] = {}


def list_project_configs() -> Dict[str, Dict[str, Any]]:
    configs: Dict[str, Dict[str, Any]] = {}
    if not PROJECTS_DIR.exists():
        return configs
    for path in sorted(PROJECTS_DIR.glob("*.json")):
        project = _load_project_file(path)
        if project:
            configs[project["name"]] = dict(project)
    return configs


def _is_temp_project(project_path: Path) -> bool:
    """
    Simple NLP-based detection of temporary/test projects.

    ⚠️  DEVELOPER NOTICE: This function automatically skips projects with certain patterns
    to prevent auto-switching to test projects. AVOID these terms in real project names:

    Reserved Keywords:
        - test, temp, tmp, demo, sample, example
        - mock, fake, dummy, trial, experiment

    Reserved Patterns:
        - UUID suffixes: "project-xxxxxxxx" (8+ chars)
        - Numeric suffixes: "project-123", "test_001"
        - Any project name containing reserved keywords

    Args:
        project_path: Path to project JSON file

    Returns:
        True if this appears to be a temp/test project (will be skipped during auto-selection)

    Examples of names that WILL be skipped:
        - "test-project.json", "temp-project.json", "demo-project.json"
        - "history-test-711f48a0.json" (UUID pattern)
        - "project-123.json" (numeric suffix)

    Examples of names that WILL be recognized:
        - "my-project.json", "production-app.json", "real-work.json"
    """
    filename = project_path.name.lower()
    stem = project_path.stem.lower()

    # Temp project indicators - simple pattern matching
    temp_indicators = [
        "test", "temp", "tmp", "demo", "sample", "example",
        "mock", "fake", "dummy", "trial", "experiment"
    ]

    # Check filename patterns
    if any(indicator in filename for indicator in temp_indicators):
        return True

    # Check for UUID-like patterns (common in test isolation)
    if any(char in stem for char in ['-', '_']) and len(stem.split('-')[-1]) >= 8:
        # Likely has UUID suffix
        return True

    # Check for numeric suffix patterns (test-001, test_123, etc.)
    if stem.split('_')[-1].isdigit() or stem.split('-')[-1].isdigit():
        return True

    return False


def load_project_config(
    project_name: Optional[str] = None,
    *,
    allow_fallback: bool = True,
) -> Optional[Dict[str, Any]]:
    if project_name:
        project = _load_project_file(PROJECTS_DIR / f"{normalize_project_input(project_name) or project_name}.json")
        if project:
            return dict(project)
        if not allow_fallback:
            return None

    if not allow_fallback:
        return None

    env_project = os.environ.get("SCRIBE_DEFAULT_PROJECT")
    if env_project and env_project != project_name:
        project = _load_project_file(PROJECTS_DIR / f"{env_project}.json")
        if project:
            return dict(project)

    for path in sorted(PROJECTS_DIR.glob("*.json")):
        # Skip temp/test projects to prevent auto-switching during testing
        if _is_temp_project(path):
            continue
        project = _load_project_file(path)
        if project:
            return dict(project)

    # Final fallback: legacy single config file
    legacy = _load_legacy_config()
    if legacy:
        return dict(legacy)
    return None


def load_project_config_by_path(path: Path) -> Optional[Dict[str, Any]]:
    project = _load_project_file(path)
    if project:
        return dict(project)
    return _normalise_project_data(_read_json(path), path.parent)


def load_config_project(project_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return load_project_config(project_name)


async def load_active_project(state_manager: StateManager) -> Tuple[Optional[Dict[str, Any]], Optional[str], Tuple[str, ...]]:
    state = await state_manager.load()
    project = state.get_project(state.current_project)
    if project:
        return project, state.current_project, tuple(state.recent_projects)
    return None, state.current_project, tuple(state.recent_projects)


def _load_project_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _PROJECT_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    data = _read_json(path)
    project = _normalise_project_data(data, path.parent)
    if project:
        _PROJECT_CACHE[path] = (mtime, project)
        if len(_PROJECT_CACHE) > 128:
            _PROJECT_CACHE.pop(next(iter(_PROJECT_CACHE)))
    return project


def _load_legacy_config() -> Optional[Dict[str, Any]]:
    legacy_path = settings.project_root / "config" / "project.json"
    if not legacy_path.exists():
        return None
    data = _read_json(legacy_path)
    if not data:
        return None
    if "name" not in data:
        data["name"] = data.get("project_name")
    if "defaults" not in data:
        data["defaults"] = {
            "emoji": data.get("default_emoji"),
            "agent": data.get("default_agent"),
        }
    return _normalise_project_data(data, legacy_path.parent)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _normalise_project_data(data: Dict[str, Any], base_dir: Path) -> Optional[Dict[str, Any]]:
    name = data.get("name") or data.get("project_name")
    if not name:
        return None

    root_value = data.get("root")
    if root_value:
        root_path = Path(root_value).expanduser()
        if not root_path.is_absolute():
            root_path = (settings.project_root / root_path).resolve()
        else:
            root_path = root_path.resolve()
    else:
        root_path = settings.project_root

    docs_value = data.get("docs_dir")
    if docs_value:
        docs_path = Path(docs_value)
        if not docs_path.is_absolute():
            docs_path = (root_path / docs_path).resolve()
    else:
        slug = slugify_project_name(name)
        docs_path = (root_path / "docs" / "dev_plans" / slug).resolve()
    if not _is_within(docs_path, root_path):
        return None

    progress_value = data.get("progress_log")
    if progress_value:
        log_path = Path(progress_value)
        if not log_path.is_absolute():
            log_path = (root_path / log_path).resolve()
    else:
        log_path = docs_path / "PROGRESS_LOG.md"
    if not _is_within(log_path, root_path):
        return None

    defaults_raw = data.get("defaults") or {}
    defaults = {
        key: value
        for key, value in defaults_raw.items()
        if value
    }

    docs = {
        "architecture": str(docs_path / "ARCHITECTURE_GUIDE.md"),
        "phase_plan": str(docs_path / "PHASE_PLAN.md"),
        "checklist": str(docs_path / "CHECKLIST.md"),
        "progress_log": str(log_path),
    }

    return {
        "name": name,
        "root": str(root_path),
        "progress_log": str(log_path),
        "docs_dir": str(docs_path),
        "docs": docs,
        "defaults": defaults,
    }


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
