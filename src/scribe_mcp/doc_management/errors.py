"""Structured error remediation envelope for manage_docs (P3, design D2).

Extends the quality_check warning shape to edit errors: every enriched
error carries ``{code, message, remediation, alternatives[]}`` so a failed
call is self-documenting instead of a bare rejection.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional, Sequence

_ANCHOR_PATTERN = re.compile(r"<!--\s*ID:\s*([^>]+?)\s*-->")


def build_remediation_envelope(
    *,
    code: str,
    remediation: str,
    alternatives: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Build the structured remediation payload attached to error responses."""
    envelope: Dict[str, Any] = {
        "code": code,
        "remediation": remediation,
        "alternatives": list(alternatives or []),
    }
    return envelope


def find_near_misses(
    target: str,
    candidates: Sequence[str],
    *,
    limit: int = 3,
    cutoff: float = 0.5,
) -> List[str]:
    """Deterministic close-match candidates for a mistyped identifier."""
    if not target or not candidates:
        return []
    return difflib.get_close_matches(target, list(candidates), n=limit, cutoff=cutoff)


def document_anchor_ids(text: str) -> List[str]:
    """All section anchor ids present in a document body (substring scan,
    matching the edit path's resolution semantics)."""
    seen: List[str] = []
    for match in _ANCHOR_PATTERN.finditer(text):
        section_id = match.group(1).strip()
        if section_id and section_id not in seen:
            seen.append(section_id)
    return seen


def attach_remediation(response: Dict[str, Any], exc: Exception) -> Dict[str, Any]:
    """Copy a DocumentOperationError's remediation envelope onto a response."""
    extra = getattr(exc, "extra", None)
    if isinstance(extra, dict) and extra.get("remediation"):
        response["code"] = extra.get("code") or str(exc).split(":", 1)[0]
        response["remediation"] = extra["remediation"]
        response["alternatives"] = list(extra.get("alternatives") or [])
    return response
