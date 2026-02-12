"""Helpers for loading and rendering documentation templates."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

# Import with absolute paths from MCP_SPINE root
from scribe_mcp.config.settings import settings
from scribe_mcp.utils.slug import slugify_project_name
from scribe_mcp.utils.time import format_utc


TEMPLATE_FILENAMES = {
    "architecture": "ARCHITECTURE_GUIDE_TEMPLATE.md",
    "phase_plan": "PHASE_PLAN_TEMPLATE.md",
    "progress_log": "PROGRESS_LOG_TEMPLATE.md",
    "checklist": "CHECKLIST_TEMPLATE.md",
    "doc_log": "DOC_LOG_TEMPLATE.md",
    "security_log": "SECURITY_LOG_TEMPLATE.md",
    "bug_log": "BUG_LOG_TEMPLATE.md",
    "research_report": "RESEARCH_REPORT_TEMPLATE.md",
    "bug_report": "BUG_REPORT_TEMPLATE.md",
    "review_report": "REVIEW_REPORT_TEMPLATE.md",
    "agent_report_card": "AGENT_REPORT_CARD_TEMPLATE.md",
}

_PROJECT_VARIABLES_CACHE: Dict[str, Any] | None = None


def template_root() -> Path:
    """Return the canonical template directory."""
    legacy_path = (settings.project_root / "scribe_mcp" / "templates" / "documents").resolve()
    modern_path = (settings.project_root / "templates" / "documents").resolve()
    if modern_path.exists():
        return modern_path
    return legacy_path


async def load_templates() -> Dict[str, str]:
    """Load all base templates into memory."""
    root = template_root()
    contents: Dict[str, str] = {}
    for key, filename in TEMPLATE_FILENAMES.items():
        path = root / filename
        contents[key] = await asyncio.to_thread(_read_text, path)
    return contents


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        return handle.read()


def substitution_context(project_name: str, author: str | None = None, rotation_context: Dict[str, str] | None = None) -> Dict[str, str]:
    """Return default variables for template rendering."""
    author_value = author or "Scribe"
    date_value = format_utc()
    slug = slugify_project_name(project_name)
    project_root = str(settings.project_root)

    # Base context
    context = {
        "project_name": project_name,
        "PROJECT_NAME": project_name,
        "project_slug": slug,
        "PROJECT_SLUG": slug,
        "author": author_value,
        "AUTHOR": author_value,
        "date_utc": date_value,
        "DATE_UTC": date_value,
        "project_root": project_root,
        "PROJECT_ROOT": project_root,
    }

    # Add rotation-specific context if provided
    if rotation_context:
        # Rotation metadata
        context.update({
            "rotation_id": rotation_context.get("rotation_id", ""),
            "ROTATION_ID": rotation_context.get("rotation_id", ""),
            "rotation_timestamp_utc": rotation_context.get("rotation_timestamp_utc", ""),
            "ROTATION_TIMESTAMP_UTC": rotation_context.get("rotation_timestamp_utc", ""),
            "previous_log_path": rotation_context.get("previous_log_path", ""),
            "PREVIOUS_LOG_PATH": rotation_context.get("previous_log_path", ""),
            "previous_log_hash": rotation_context.get("previous_log_hash", ""),
            "PREVIOUS_LOG_HASH": rotation_context.get("previous_log_hash", ""),
            "previous_log_entries": rotation_context.get("previous_log_entries", "0"),
            "PREVIOUS_LOG_ENTRIES": rotation_context.get("previous_log_entries", "0"),
            "current_sequence": rotation_context.get("current_sequence", "1"),
            "CURRENT_SEQUENCE": rotation_context.get("current_sequence", "1"),
            "total_rotations": rotation_context.get("total_rotations", "0"),
            "TOTAL_ROTATIONS": rotation_context.get("total_rotations", "0"),
            "is_rotation": rotation_context.get("is_rotation", "false"),
            "IS_ROTATION": rotation_context.get("is_rotation", "false"),

            # Hash chaining variables
            "hash_chain_previous": rotation_context.get("hash_chain_previous", ""),
            "HASH_CHAIN_PREVIOUS": rotation_context.get("hash_chain_previous", ""),
            "hash_chain_sequence": rotation_context.get("hash_chain_sequence", "1"),
            "HASH_CHAIN_SEQUENCE": rotation_context.get("hash_chain_sequence", "1"),
            "hash_chain_root": rotation_context.get("hash_chain_root", ""),
            "HASH_CHAIN_ROOT": rotation_context.get("hash_chain_root", ""),
        })

        # Additional metadata that might be in rotation context
        for key, value in rotation_context.items():
            if key not in context:
                context[key] = str(value)
                context[key.upper()] = str(value)

    custom_vars = _load_project_variables()
    if custom_vars:
        for key, value in custom_vars.items():
            # Do not override explicit context (e.g., passed-in author)
            if key not in context:
                context[key] = value
            if isinstance(key, str) and isinstance(value, (str, int, float, bool)):
                context.setdefault(key.upper(), str(value))

    return context


def create_rotation_context(
    rotation_id: str,
    rotation_timestamp: str,
    previous_log_path: str = "",
    previous_log_hash: str = "",
    previous_log_entries: str = "0",
    current_sequence: str = "1",
    total_rotations: str = "1",
    hash_chain_previous: str = "",
    hash_chain_sequence: str = "1",
    hash_chain_root: str = ""
) -> Dict[str, str]:
    """
    Create rotation context dictionary for template rendering.

    Args:
        rotation_id: Unique identifier for this rotation
        rotation_timestamp: UTC timestamp of rotation
        previous_log_path: Path to previous log file
        previous_log_hash: Hash of previous log file
        previous_log_entries: Number of entries in previous log
        current_sequence: Current rotation sequence number
        total_rotations: Total number of rotations completed
        hash_chain_previous: Previous hash in chain
        hash_chain_sequence: Current position in hash chain
        hash_chain_root: Root hash of chain

    Returns:
        Rotation context dictionary for template substitution
    """
    return {
        "rotation_id": rotation_id,
        "rotation_timestamp_utc": rotation_timestamp,
        "previous_log_path": previous_log_path,
        "previous_log_hash": previous_log_hash,
        "previous_log_entries": previous_log_entries,
        "current_sequence": current_sequence,
        "total_rotations": total_rotations,
        "is_rotation": "true",
        "hash_chain_previous": hash_chain_previous,
        "hash_chain_sequence": hash_chain_sequence,
        "hash_chain_root": hash_chain_root,
    }


def _load_project_variables() -> Dict[str, Any]:
    """Load variables from .scribe/variables.json once per process."""
    global _PROJECT_VARIABLES_CACHE
    if _PROJECT_VARIABLES_CACHE is not None:
        return _PROJECT_VARIABLES_CACHE

    variables_path = settings.project_root / ".scribe" / "variables.json"
    if not variables_path.exists():
        _PROJECT_VARIABLES_CACHE = {}
        return _PROJECT_VARIABLES_CACHE

    try:
        content = variables_path.read_text(encoding="utf-8")
        data = json.loads(content) if content.strip() else {}
        if isinstance(data, dict):
            _PROJECT_VARIABLES_CACHE = data
        else:
            _PROJECT_VARIABLES_CACHE = {}
    except json.JSONDecodeError:
        _PROJECT_VARIABLES_CACHE = {}
    except OSError:
        _PROJECT_VARIABLES_CACHE = {}

    return _PROJECT_VARIABLES_CACHE
