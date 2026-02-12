"""Validation helpers for manage_docs routing and filesystem safety."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

from scribe_mcp.doc_management.manager import DocumentValidationError
from scribe_mcp.utils.files import ensure_parent


def validate_action(action: str, valid_actions: Iterable[str]) -> str:
    """Validate and normalize action names."""
    normalized = str(action or "").strip()
    action_set: Set[str] = set(valid_actions)
    if normalized not in action_set:
        raise DocumentValidationError(
            f"Invalid action '{action}'. Allowed actions: {', '.join(sorted(action_set))}"
        )
    return normalized


def validate_doc_name(doc_name: Optional[str]) -> str:
    """Validate doc_name presence and normalization."""
    if doc_name is None:
        raise DocumentValidationError("doc_name is required")
    normalized = str(doc_name).strip()
    if not normalized:
        raise DocumentValidationError("doc_name cannot be empty")
    return normalized


def validate_section_required(action: str, section: Optional[str]) -> Optional[str]:
    """Enforce section requirements for section-based actions."""
    normalized = str(section).strip() if section is not None else None
    if action in {"replace_section", "status_update"} and not normalized:
        raise DocumentValidationError(f"section is required for action '{action}'")
    return normalized


async def validate_safe_doc_path(path: Path, repo_root: Path) -> None:
    """Ensure doc path is writable and constrained to repository roots."""
    await ensure_parent(path, repo_root=repo_root.resolve())


def validate_metadata_dict(metadata: Any) -> Dict[str, Any]:
    """Ensure metadata payload is a dict-like mapping."""
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata
    raise DocumentValidationError("metadata must be an object")
