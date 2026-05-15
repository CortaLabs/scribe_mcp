from __future__ import annotations

from types import SimpleNamespace

from scribe_mcp.shared.reference_resolution import (
    PROBLEM_CODE_INVALID_PREFIXED_REFERENCE,
    PROBLEM_CODE_INVALID_REFERENCE,
    build_reference_scope,
    build_resolution_error,
    normalize_resolution_result,
    resolve_reference,
)
from scribe_mcp.shared.session_scope import build_resolved_scope


def test_prefixed_reference_takes_priority() -> None:
    scope = build_reference_scope(SimpleNamespace())
    result = resolve_reference("entry:abc123", "entry_ref", scope)
    assert result.ok is True
    assert result.kind == "entry"
    assert result.source == "explicit_prefix"


def test_runtime_match_precedes_case_pattern() -> None:
    resolved_scope = build_resolved_scope(
        {
            "stable_session_id": "BUG-2026-05-15-0001",
            "repo_root": "/tmp/repo",
        }
    )
    context = SimpleNamespace(resolved_scope=resolved_scope, execution_id="exec-1", parent_execution_id="exec-0")
    scope = build_reference_scope(context)

    result = resolve_reference("BUG-2026-05-15-0001", "ref", scope)
    assert result.ok is True
    assert result.kind == "session"
    assert result.source == "runtime_stable_session"


def test_case_id_pattern_matches_when_not_runtime() -> None:
    scope = build_reference_scope(SimpleNamespace())
    result = resolve_reference("SEC-2026-05-15-0002", "case_id", scope)
    assert result.ok is True
    assert result.kind == "case"


def test_raw_32_hex_is_unresolved_compatibility() -> None:
    scope = build_reference_scope(SimpleNamespace())
    result = resolve_reference("0123456789abcdef0123456789abcdef", "entry_ref", scope)
    assert result.ok is False
    assert result.kind == "unresolved"
    assert result.compatibility_hint == "potential_entry_reference_requires_storage_lookup"


def test_bad_input_returns_structured_problem() -> None:
    scope = build_reference_scope(SimpleNamespace())
    problem = resolve_reference("", "entry_ref", scope)
    assert problem.ok is False
    assert problem.code == PROBLEM_CODE_INVALID_REFERENCE
    assert problem.field == "entry_ref"
    assert "scope_summary" in problem.__dict__


def test_prefixed_missing_value_uses_stable_code() -> None:
    scope = build_reference_scope(SimpleNamespace())
    problem = resolve_reference("entry:", "entry_ref", scope)
    assert problem.ok is False
    assert problem.code == PROBLEM_CODE_INVALID_PREFIXED_REFERENCE


def test_normalized_problem_envelope_shape() -> None:
    scope = build_reference_scope(SimpleNamespace())
    problem = resolve_reference("", "entry_ref", scope)
    payload = build_resolution_error(problem)
    assert payload["ok"] is False
    assert payload["error"]["code"] == PROBLEM_CODE_INVALID_REFERENCE
    assert payload["error"]["field"] == "entry_ref"
    assert "scope_summary" in payload["error"]


def test_normalize_resolution_result_success_shape() -> None:
    scope = build_reference_scope(SimpleNamespace())
    result = resolve_reference("entry:abc123", "entry_ref", scope)
    payload = normalize_resolution_result(result)
    assert payload["ok"] is True
    assert payload["resolution"]["kind"] == "entry"
