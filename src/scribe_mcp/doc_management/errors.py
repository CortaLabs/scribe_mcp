"""Structured error remediation envelope for manage_docs (P3, design D2).

Extends the quality_check warning shape to edit errors: every enriched
error carries ``{code, message, remediation, alternatives[]}`` so a failed
call is self-documenting instead of a bare rejection.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, Iterator, List, Optional, Sequence

from scribe_mcp.doc_management.quality.scopes import create_scope_provider

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


def iter_unfenced_lines(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield line number, absolute offset and raw text outside fenced artifacts.

    Reuse the quality engine's Markdown scopes so editing and discovery agree
    on fence type, delimiter length, and unterminated fences.
    """
    fences = sorted(
        (scope.start_offset, scope.end_offset)
        for scope in create_scope_provider().collect_scopes(text)
        if scope.kind == "fenced_code"
    )
    offset = 0
    fence_index = 0
    for line_no, line in enumerate(text.splitlines(keepends=True), start=1):
        while fence_index < len(fences) and fences[fence_index][1] <= offset:
            fence_index += 1
        if fence_index == len(fences) or offset < fences[fence_index][0]:
            yield line_no, offset, line
        offset += len(line)


def document_anchor_matches(text: str) -> Iterator[re.Match[str]]:
    """Resolve real markers with absolute offsets, leaving fenced bytes opaque."""
    for _, offset, line in iter_unfenced_lines(text):
        yield from _ANCHOR_PATTERN.finditer(text, offset, offset + len(line))


def document_anchor_ids(text: str) -> List[str]:
    """Distinct section IDs outside fenced code, in document order."""
    seen: List[str] = []
    for match in document_anchor_matches(text):
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
