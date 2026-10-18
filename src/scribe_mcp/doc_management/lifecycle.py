"""Canonical metadata and lifecycle helpers for managed docs."""

from __future__ import annotations

from typing import Optional

CANONICAL_DOC_TYPES = {
    "architecture",
    "spec",
    "phase_plan",
    "checklist",
    "research",
    "synthesis",
    "review",
    "security_review",
    "bug_rca",
    "progress_log",
    "work_item",
    "other",
}

CANONICAL_STATUSES = {
    "scaffolded",
    "in_progress",
    "ready",
    "complete",
    "stale",
    "superseded",
    "blocked",
    "archived",
}

STATUS_ALIASES = {"draft": "scaffolded", "active": "in_progress", "authoritative": "ready", "done": "complete"}


def derive_canonical_doc_type(doc_type: Optional[str], intended_doc_type: Optional[str]) -> str:
    canonical = (intended_doc_type or doc_type or "other").strip().lower()
    return canonical or "other"


def normalize_canonical_status(status: Optional[str]) -> str:
    normalized = str(status or "scaffolded").strip().lower()
    normalized = STATUS_ALIASES.get(normalized, normalized)
    if normalized not in CANONICAL_STATUSES:
        raise ValueError(
            f"Invalid canonical status '{status}'. Allowed values: {sorted(CANONICAL_STATUSES)}"
        )
    return normalized
