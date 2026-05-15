"""Canonical reference parsing and non-raising resolution envelopes."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Optional

from scribe_mcp.shared.session_scope import ResolvedScope

ReferenceKind = Literal[
    "execution",
    "parent_execution",
    "session",
    "authoritative_session_key",
    "entry",
    "case",
    "document",
    "artifact",
    "commit",
    "unresolved",
]

_PREFIX_KIND_MAP: dict[str, ReferenceKind] = {
    "exec": "execution",
    "execution": "execution",
    "parent_exec": "parent_execution",
    "parent_execution": "parent_execution",
    "session": "session",
    "authoritative_session": "authoritative_session_key",
    "authoritative_session_key": "authoritative_session_key",
    "entry": "entry",
    "case": "case",
    "doc": "document",
    "document": "document",
    "artifact": "artifact",
    "commit": "commit",
}

_CASE_ID_RE = re.compile(r"^(BUG|SEC)-\d{4}-\d{2}-\d{2}-\d{4}$")
_HEX_32_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


@dataclass(frozen=True)
class ReferenceScope:
    execution_id: Optional[str]
    parent_execution_id: Optional[str]
    transport_session_id: Optional[str]
    stable_session_id: Optional[str]
    agent_session_id: Optional[str]
    authoritative_session_key: Optional[str]


@dataclass(frozen=True)
class ResolutionResult:
    ok: bool
    kind: ReferenceKind
    raw: str
    normalized: str
    source: str
    resolved_value: Optional[str] = None
    compatibility_hint: Optional[str] = None


@dataclass(frozen=True)
class ResolutionProblem:
    ok: bool
    code: str
    field: str
    message: str
    recovery_hint: str
    scope_summary: dict[str, Optional[str]]


PROBLEM_CODE_INVALID_REFERENCE = "REFERENCE_INVALID"
PROBLEM_CODE_INVALID_PREFIXED_REFERENCE = "REFERENCE_PREFIX_VALUE_MISSING"


def build_resolution_error(problem: ResolutionProblem) -> dict[str, Any]:
    """Normalize a resolution problem into the mutating-tool error envelope contract."""
    return {
        "ok": False,
        "error": {
            "code": problem.code,
            "field": problem.field,
            "message": problem.message,
            "recovery_hint": problem.recovery_hint,
            "scope_summary": dict(problem.scope_summary),
        },
    }


def normalize_resolution_result(result: ResolutionResult | ResolutionProblem) -> dict[str, Any]:
    """Return a JSON-serializable normalized shape for resolver outcomes."""
    if isinstance(result, ResolutionProblem):
        return build_resolution_error(result)
    return {"ok": True, "resolution": asdict(result)}


def build_reference_scope(context: Any) -> ReferenceScope:
    resolved_scope = getattr(context, "resolved_scope", None)
    if isinstance(resolved_scope, ResolvedScope):
        return ReferenceScope(
            execution_id=_as_optional_str(getattr(context, "execution_id", None)),
            parent_execution_id=_as_optional_str(getattr(context, "parent_execution_id", None)),
            transport_session_id=resolved_scope.transport_session_id,
            stable_session_id=resolved_scope.stable_session_id,
            agent_session_id=resolved_scope.agent_session_id,
            authoritative_session_key=resolved_scope.authoritative_session_key,
        )
    return ReferenceScope(
        execution_id=_as_optional_str(getattr(context, "execution_id", None)),
        parent_execution_id=_as_optional_str(getattr(context, "parent_execution_id", None)),
        transport_session_id=None,
        stable_session_id=None,
        agent_session_id=None,
        authoritative_session_key=_as_optional_str(getattr(context, "authoritative_session_key", None)),
    )


def resolve_reference(raw: Any, field_name: str, scope: ReferenceScope) -> ResolutionResult | ResolutionProblem:
    text = _as_optional_str(raw)
    if not text:
        return _problem(
            PROBLEM_CODE_INVALID_REFERENCE,
            field_name,
            "Reference is required.",
            "Provide a non-empty reference value.",
            scope,
        )

    if ":" in text:
        prefix, value = text.split(":", 1)
        kind = _PREFIX_KIND_MAP.get(prefix.strip().lower())
        if kind is not None:
            normalized_value = value.strip()
            if not normalized_value:
                return _problem(
                    PROBLEM_CODE_INVALID_PREFIXED_REFERENCE,
                    field_name,
                    "Prefixed reference is missing a value.",
                    "Use '<prefix>:<value>'.",
                    scope,
                )
            return ResolutionResult(True, kind, text, text, "explicit_prefix", resolved_value=normalized_value)

    runtime_match = _runtime_match(text, scope)
    if runtime_match is not None:
        return runtime_match

    if _CASE_ID_RE.match(text):
        return ResolutionResult(True, "case", text, text, "case_id_pattern", resolved_value=text)

    if _HEX_32_RE.match(text):
        return ResolutionResult(
            False,
            "unresolved",
            text,
            text,
            "compatibility",
            compatibility_hint="potential_entry_reference_requires_storage_lookup",
        )

    if text.startswith(".") or "/" in text:
        return ResolutionResult(True, "document", text, text, "compatibility", resolved_value=text)

    if ":" in text:
        return ResolutionResult(True, "artifact", text, text, "compatibility", resolved_value=text)

    if _COMMIT_RE.match(text):
        return ResolutionResult(True, "commit", text, text, "compatibility", resolved_value=text)

    return ResolutionResult(False, "unresolved", text, text, "compatibility")


def _runtime_match(text: str, scope: ReferenceScope) -> Optional[ResolutionResult]:
    candidates: tuple[tuple[str, Optional[str], ReferenceKind], ...] = (
        ("runtime_execution", scope.execution_id, "execution"),
        ("runtime_parent_execution", scope.parent_execution_id, "parent_execution"),
        ("runtime_transport_session", scope.transport_session_id, "session"),
        ("runtime_stable_session", scope.stable_session_id, "session"),
        ("runtime_agent_session", scope.agent_session_id, "session"),
        ("runtime_authoritative_session", scope.authoritative_session_key, "authoritative_session_key"),
    )
    for source, candidate, kind in candidates:
        if candidate and text == candidate:
            return ResolutionResult(True, kind, text, text, source, resolved_value=text)
    return None


def _problem(code: str, field: str, message: str, recovery_hint: str, scope: ReferenceScope) -> ResolutionProblem:
    return ResolutionProblem(
        ok=False,
        code=code,
        field=field,
        message=message,
        recovery_hint=recovery_hint,
        scope_summary={
            "execution_id": scope.execution_id,
            "parent_execution_id": scope.parent_execution_id,
            "stable_session_id": scope.stable_session_id,
            "authoritative_session_key": scope.authoritative_session_key,
        },
    )


def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None
