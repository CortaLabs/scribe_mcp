"""Boundary guidance helpers for manage_docs target validation."""

from __future__ import annotations

from typing import Any, Dict, Optional


def is_manage_docs_boundary_error(message: str) -> bool:
    """Return True when error text indicates a project-root boundary violation."""
    normalized = str(message or "").lower()
    return "outside project root" in normalized


def build_manage_docs_boundary_guidance(
    project: Dict[str, Any],
    *,
    rejected_target: Optional[str] = None,
) -> Dict[str, Any]:
    """Build canonical boundary guidance payload for manage_docs write targets."""
    project_root = str(project.get("root") or "")
    docs_dir = str(project.get("docs_dir") or "")
    guidance: Dict[str, Any] = {
        "rule": "target_dir must resolve inside the active project root",
        "project_root": project_root,
        "supported_alternative": {
            "target_dir": docs_dir,
            "example": "Use an in-project target_dir (or omit it to use project docs_dir).",
        },
    }
    if rejected_target:
        guidance["rejected_target_dir"] = str(rejected_target)
    return guidance
