from __future__ import annotations

import pytest

from scribe_mcp.case_lifecycle import (
    CaseReopenDecision,
    CaseReopenValidationError,
    CaseLifecycleResult,
    GovernedCaseReportProjection,
    build_canonical_doc_binding,
    build_link_fix_lifecycle_result,
    build_reopen_transition_decision,
    case_status_snapshot,
    doc_binding_from_metadata,
    doc_binding_to_metadata,
    infer_reopen_case_type,
    normalize_landing_status,
    parse_governed_case_report,
    resolve_registry_status_after,
)
from scribe_mcp.storage.models import CaseRegistryRecord


def _case_record(
    *,
    case_id: str = "BUG-2026-06-25-0001",
    case_type: str = "bug",
    status: str | None = "open",
    doc_type: str | None = None,
    doc_name: str | None = None,
    metadata: dict[str, object] | None = None,
) -> CaseRegistryRecord:
    return CaseRegistryRecord(
        case_id=case_id,
        case_type=case_type,
        project_name="scribe_bug_tools_hardening_062526",
        repo_root="/tmp/repo",
        repo_id="repo-1",
        project_key="project-key",
        doc_type=doc_type if doc_type is not None else case_type,
        doc_name=doc_name if doc_name is not None else case_id,
        doc_path=f"/tmp/repo/docs/{case_type}/{case_id}/report.md",
        status=status,
        metadata=metadata or {},
    )


def test_in_progress_landing_status_records_fix_link_but_leaves_case_open() -> None:
    before = _case_record(status="open")

    result = build_link_fix_lifecycle_result(
        case_record_before=before,
        case_record_after=None,
        landing_status="in_progress",
        fix_link_recorded=True,
        doc_binding=None,
    )

    assert result.fix_link_recorded is True
    assert result.case_closed is False
    assert result.landing_status == "in_progress"
    assert result.landing_status_terminal is False
    assert result.registry_status_before == "open"
    assert result.registry_status_after == "open"
    assert result.closure_reason is None
    assert "terminal" in result.next_step


def test_fix_terminal_status_closes_case_as_closed() -> None:
    before = _case_record(status="in_progress")

    after_status, closes_case, closure_reason = resolve_registry_status_after(
        before.status,
        "merged",
    )
    result = build_link_fix_lifecycle_result(
        case_record_before=before,
        case_record_after=_case_record(status=after_status),
        landing_status="merged",
        fix_link_recorded=True,
        doc_binding=None,
    )

    assert closes_case is True
    assert closure_reason == "closed"
    assert result.case_closed is True
    assert result.landing_status_terminal is True
    assert result.registry_status_after == "closed"
    assert result.lifecycle_status == "closed"
    assert result.closure_reason == "closed"


def test_fix_terminal_status_requires_registry_readback_to_close() -> None:
    before = _case_record(status="open")

    result = build_link_fix_lifecycle_result(
        case_record_before=before,
        case_record_after=None,
        landing_status="resolved",
        fix_link_recorded=True,
        doc_binding=None,
    )

    assert result.fix_link_recorded is True
    assert result.case_closed is False
    assert result.landing_status_terminal is True
    assert result.registry_status_before == "open"
    assert result.registry_status_after is None
    assert result.closure_reason == "closed"
    assert "terminal landing_status" in result.next_step
    assert "registry close readback" in result.next_step


def test_nonfix_terminal_status_closes_case_and_preserves_reason() -> None:
    before = _case_record(status="triage")

    after_status, closes_case, closure_reason = resolve_registry_status_after(
        before.status,
        "false positive",
    )
    result = build_link_fix_lifecycle_result(
        case_record_before=before,
        case_record_after=_case_record(status=after_status),
        landing_status="false positive",
        fix_link_recorded=True,
        doc_binding=None,
    )

    assert closes_case is True
    assert closure_reason == "false_positive"
    assert result.case_closed is True
    assert result.registry_status_after == "false_positive"
    assert result.closure_reason == "false_positive"


def test_unknown_landing_status_is_rejected() -> None:
    try:
        normalize_landing_status("mystery-status")
    except ValueError as exc:
        assert "Unknown case landing status" in str(exc)
    else:
        raise AssertionError("unknown landing status should reject")


def test_doc_binding_metadata_round_trip_keeps_canonical_path_and_aliases() -> None:
    binding = build_canonical_doc_binding(
        "BUG-2026-06-25-0001",
        "/tmp/repo/docs/bugs/runtime/report.md",
        {
            "bugs": "/tmp/repo/docs/bugs/runtime/report.md",
            "BUG-2026-06-25-0001": "/tmp/repo/docs/bugs/runtime/report.md",
            "legacy-bug": "/tmp/repo/docs/bugs/runtime/report.md",
            "other": "/tmp/repo/docs/bugs/other/report.md",
        },
        preferred_doc_name="bugs",
    )

    metadata = doc_binding_to_metadata(binding)
    restored = doc_binding_from_metadata(metadata)

    assert restored == binding
    assert binding.canonical_doc_name == "BUG-2026-06-25-0001"
    assert binding.canonical_doc_path == "/tmp/repo/docs/bugs/runtime/report.md"
    assert {alias.alias for alias in binding.aliases} == {
        "bugs",
        "BUG-2026-06-25-0001",
        "legacy-bug",
    }
    assert metadata["aliases"][0]["alias_kind"] == "primary"


def test_lifecycle_result_to_dict_is_json_safe() -> None:
    binding = build_canonical_doc_binding(
        "SEC-2026-06-25-0001",
        "/tmp/repo/docs/security/runtime/report.md",
        {"security": "/tmp/repo/docs/security/runtime/report.md"},
    )
    result = case_status_snapshot(
        _case_record(
            case_id="SEC-2026-06-25-0001",
            case_type="security",
            status="closed",
            metadata={"fix_link": {"artifact_ref": "src/module.py:10"}},
        ),
        doc_binding=binding,
    )

    data = result.to_dict()

    assert isinstance(result, CaseLifecycleResult)
    assert data["case_id"] == "SEC-2026-06-25-0001"
    assert data["doc_binding"]["canonical_doc_name"] == "SEC-2026-06-25-0001"
    assert data["doc_binding"]["aliases"][0]["alias_kind"] == "primary"
    assert data["last_fix_link"] == {"artifact_ref": "src/module.py:10"}


def test_parse_governed_bug_report_requires_exact_identity_and_agreeing_statuses() -> (
    None
):
    projection = parse_governed_case_report(
        """
        **Bug ID:** BUG-2026-07-11-0001
        **Status:** INVESTIGATING
        **Landing Status:** closed
        **Status:** investigating
        """,
        "BUG-2026-07-11-0001",
        "bug",
    )

    assert projection == GovernedCaseReportProjection(
        case_id="BUG-2026-07-11-0001",
        case_type="bug",
        status="investigating",
    )
    assert projection.to_dict() == {
        "case_id": "BUG-2026-07-11-0001",
        "case_type": "bug",
        "status": "investigating",
    }


def test_parse_governed_security_report_requires_case_id_header() -> None:
    projection = parse_governed_case_report(
        """
        **Case ID:** SEC-2026-07-11-0001
        **Status:** TRIAGE
        **Status:** triage
        """,
        "SEC-2026-07-11-0001",
        "security",
    )

    assert projection == GovernedCaseReportProjection(
        case_id="SEC-2026-07-11-0001",
        case_type="security",
        status="triage",
    )


def test_infer_reopen_case_type_trims_once_and_preserves_exact_grammar() -> None:
    assert infer_reopen_case_type(" \tBUG-2026-07-11-0001\n") == "bug"
    assert infer_reopen_case_type(" SEC-2026-07-11-0001 ") == "security"


@pytest.mark.parametrize(
    "case_id",
    [
        "",
        "bug-2026-07-11-0001",
        "BUG-20260711-0001",
        "BUG-2026-07-11",
        "BUG-2026-07-11-0001 extra",
        "CASE-2026-07-11-0001",
    ],
)
def test_invalid_requested_case_ids_raise_stable_code(case_id: str) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        infer_reopen_case_type(case_id)

    assert caught.value.error_code == "INVALID_CASE_ID"
    assert isinstance(caught.value, ValueError)


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(None, id="none"),
        pytest.param(7, id="int"),
        pytest.param([], id="list"),
        pytest.param({}, id="mapping"),
        pytest.param(b"BUG-2026-07-11-0001", id="bytes"),
    ],
)
@pytest.mark.parametrize("boundary", ["infer", "parse", "decision"])
def test_non_string_case_ids_fail_typed_at_every_pure_boundary(
    case_id: object,
    boundary: str,
) -> None:
    valid_case_id = "BUG-2026-07-11-0001"
    report = GovernedCaseReportProjection(
        case_id=valid_case_id,
        case_type="bug",
        status="investigating",
    )

    with pytest.raises(CaseReopenValidationError) as caught:
        if boundary == "infer":
            infer_reopen_case_type(case_id)
        elif boundary == "parse":
            parse_governed_case_report(
                f"**Bug ID:** {valid_case_id}\n**Status:** investigating",
                case_id,
                "bug",
            )
        else:
            build_reopen_transition_decision(
                case_id=case_id,
                case_record=_case_record(case_id=valid_case_id, status="closed"),
                target_status="investigating",
                report=report,
            )

    assert caught.value.error_code == "INVALID_CASE_ID"


@pytest.mark.parametrize(
    "report_text",
    [
        pytest.param(None, id="none"),
        pytest.param(7, id="int"),
        pytest.param([], id="list"),
        pytest.param({}, id="mapping"),
        pytest.param(b"**Bug ID:** BUG-2026-07-11-0001", id="bytes"),
    ],
)
def test_non_string_governed_reports_raise_stable_missing_header_code(
    report_text: object,
) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            report_text,
            "BUG-2026-07-11-0001",
            "bug",
        )

    assert caught.value.error_code == "REPORT_ID_HEADER_MISSING"


@pytest.mark.parametrize(
    ("report_text", "expected_case_id", "expected_case_type", "error_code"),
    [
        pytest.param(
            None,
            None,
            "bug",
            "INVALID_CASE_ID",
            id="invalid-requested-id-first",
        ),
        pytest.param(
            None,
            "SEC-2026-07-11-0001",
            "bug",
            "REPORT_ID_HEADER_TYPE_MISMATCH",
            id="identity-type-mismatch-second",
        ),
        pytest.param(
            None,
            "BUG-2026-07-11-0001",
            "bug",
            "REPORT_ID_HEADER_MISSING",
            id="report-shape-after-valid-identity",
        ),
    ],
)
def test_non_string_report_shape_preserves_identity_failure_precedence(
    report_text: object,
    expected_case_id: object,
    expected_case_type: str,
    error_code: str,
) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            report_text,
            expected_case_id,
            expected_case_type,
        )

    assert caught.value.error_code == error_code


def test_valid_str_subclasses_remain_accepted_at_pure_boundaries() -> None:
    class GovernedText(str):
        pass

    case_id = GovernedText("BUG-2026-07-11-0001")
    report = parse_governed_case_report(
        GovernedText("**Bug ID:** BUG-2026-07-11-0001\n**Status:** investigating"),
        case_id,
        "bug",
    )

    assert infer_reopen_case_type(case_id) == "bug"
    assert report.status == "investigating"
    assert (
        build_reopen_transition_decision(
            case_id=case_id,
            case_record=_case_record(
                case_id="BUG-2026-07-11-0001",
                status="closed",
            ),
            target_status="investigating",
            report=report,
        ).transition_required
        is True
    )


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("BUG-\u200b2026-07-11-0001", id="zero-width"),
        pytest.param("BUG-2026-07-11-0001\ud800", id="lone-surrogate"),
    ],
)
def test_malformed_unicode_case_ids_remain_typed(case_id: str) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        infer_reopen_case_type(case_id)

    assert caught.value.error_code == "INVALID_CASE_ID"


@pytest.mark.parametrize(
    ("report_text", "error_code"),
    [
        pytest.param(
            "**Bug ID:** BUG-2026-07-11-0001\u200b\n**Status:** investigating",
            "REPORT_ID_HEADER_MALFORMED",
            id="zero-width-header",
        ),
        pytest.param(
            "**Bug ID:** BUG-2026-07-11-0001\n**Status:** investi\u200bgating",
            "REPORT_STATUS_INVALID",
            id="zero-width-status",
        ),
    ],
)
def test_malformed_unicode_report_fields_remain_typed(
    report_text: str,
    error_code: str,
) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            report_text,
            "BUG-2026-07-11-0001",
            "bug",
        )

    assert caught.value.error_code == error_code


def test_missing_report_identity_header_raises_stable_code() -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            "**Status:** investigating",
            "BUG-2026-07-11-0001",
            "bug",
        )

    assert caught.value.error_code == "REPORT_ID_HEADER_MISSING"


@pytest.mark.parametrize(
    "identity_headers",
    [
        """
        **Bug ID:** BUG-2026-07-11-0001
        **Bug ID:** BUG-2026-07-11-0001
        """,
        """
        **Bug ID:** BUG-2026-07-11-0001
        **Bug ID:** BUG-2026-07-11-0002
        """,
    ],
)
def test_duplicate_report_identity_headers_raise_stable_code(
    identity_headers: str,
) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            f"{identity_headers}\n**Status:** investigating",
            "BUG-2026-07-11-0001",
            "bug",
        )

    assert caught.value.error_code == "REPORT_ID_HEADER_DUPLICATE"


@pytest.mark.parametrize(
    "identity_header",
    [
        "**Bug ID:**",
        "**Bug ID**: BUG-2026-07-11-0001",
        "**Bug ID:** bug-2026-07-11-0001",
        "**Bug ID:** BUG-20260711-0001",
        "**Bug ID:** BUG-2026-07-11-001",
    ],
)
def test_malformed_report_identity_headers_raise_stable_code(
    identity_header: str,
) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            f"{identity_header}\n**Status:** investigating",
            "BUG-2026-07-11-0001",
            "bug",
        )

    assert caught.value.error_code == "REPORT_ID_HEADER_MALFORMED"


@pytest.mark.parametrize(
    "identity_header",
    [
        "**Case ID:** BUG-2026-07-11-0001",
        "**Bug ID:** SEC-2026-07-11-0001",
    ],
)
def test_report_identity_type_mismatches_raise_stable_code(
    identity_header: str,
) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            f"{identity_header}\n**Status:** investigating",
            "BUG-2026-07-11-0001",
            "bug",
        )

    assert caught.value.error_code == "REPORT_ID_HEADER_TYPE_MISMATCH"


def test_canonical_but_unequal_report_identity_raises_stable_code() -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            """
            **Bug ID:** BUG-2026-07-11-0002
            **Status:** investigating
            """,
            "BUG-2026-07-11-0001",
            "bug",
        )

    assert caught.value.error_code == "REPORT_ID_MISMATCH"


@pytest.mark.parametrize(
    ("status_lines", "error_code"),
    [
        ("", "REPORT_STATUS_MISSING"),
        (
            "**Status:** open\n**Status:** investigating",
            "REPORT_STATUS_CONFLICT",
        ),
        ("**Status:** mystery", "REPORT_STATUS_INVALID"),
        ("**Status:** closed", "REPORT_STATUS_INVALID"),
        ("**Status:** validated", "REPORT_STATUS_INVALID"),
        ("**Status:** duplicate", "REPORT_STATUS_INVALID"),
        ("**Status:** false positive", "REPORT_STATUS_INVALID"),
    ],
)
def test_governed_report_status_failures_use_stable_codes(
    status_lines: str,
    error_code: str,
) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        parse_governed_case_report(
            f"**Bug ID:** BUG-2026-07-11-0001\n{status_lines}",
            "BUG-2026-07-11-0001",
            "bug",
        )

    assert caught.value.error_code == error_code


@pytest.mark.parametrize(
    "registry_status",
    ["closed", "validated", "duplicate", "false positive"],
)
def test_terminal_registry_families_require_reopen_transition(
    registry_status: str,
) -> None:
    decision = build_reopen_transition_decision(
        case_id="BUG-2026-07-11-0001",
        case_record=_case_record(
            case_id="BUG-2026-07-11-0001",
            status=registry_status,
        ),
        target_status="INVESTIGATING",
        report=GovernedCaseReportProjection(
            case_id="BUG-2026-07-11-0001",
            case_type="bug",
            status="investigating",
        ),
    )

    assert decision.transition_required is True
    assert decision.idempotent is False
    assert decision.target_status == "investigating"


def test_already_matching_open_target_is_idempotent() -> None:
    decision = build_reopen_transition_decision(
        case_id="SEC-2026-07-11-0001",
        case_record=_case_record(
            case_id="SEC-2026-07-11-0001",
            case_type="security",
            status="investigating",
        ),
        target_status="investigating",
        report=GovernedCaseReportProjection(
            case_id="SEC-2026-07-11-0001",
            case_type="security",
            status="investigating",
        ),
    )

    assert decision.transition_required is False
    assert decision.idempotent is True


def test_different_open_registry_status_cannot_be_moved_by_reopen() -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        build_reopen_transition_decision(
            case_id="BUG-2026-07-11-0001",
            case_record=_case_record(
                case_id="BUG-2026-07-11-0001",
                status="open",
            ),
            target_status="investigating",
            report=GovernedCaseReportProjection(
                case_id="BUG-2026-07-11-0001",
                case_type="bug",
                status="investigating",
            ),
        )

    assert caught.value.error_code == "TRANSITION_NOT_ALLOWED"


@pytest.mark.parametrize("registry_status", [None, "mystery"])
def test_invalid_registry_status_raises_stable_code(
    registry_status: str | None,
) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        build_reopen_transition_decision(
            case_id="BUG-2026-07-11-0001",
            case_record=_case_record(
                case_id="BUG-2026-07-11-0001",
                status=registry_status,
            ),
            target_status="investigating",
            report=GovernedCaseReportProjection(
                case_id="BUG-2026-07-11-0001",
                case_type="bug",
                status="investigating",
            ),
        )

    assert caught.value.error_code == "REGISTRY_STATUS_INVALID"


@pytest.mark.parametrize("target_status", ["", "mystery", "closed", "validated"])
def test_invalid_reopen_target_status_raises_stable_code(target_status: str) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        build_reopen_transition_decision(
            case_id="BUG-2026-07-11-0001",
            case_record=_case_record(
                case_id="BUG-2026-07-11-0001",
                status="closed",
            ),
            target_status=target_status,
            report=GovernedCaseReportProjection(
                case_id="BUG-2026-07-11-0001",
                case_type="bug",
                status="investigating",
            ),
        )

    assert caught.value.error_code == "INVALID_TARGET_STATUS"


def test_report_status_must_match_normalized_target() -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        build_reopen_transition_decision(
            case_id="BUG-2026-07-11-0001",
            case_record=_case_record(
                case_id="BUG-2026-07-11-0001",
                status="closed",
            ),
            target_status="investigating",
            report=GovernedCaseReportProjection(
                case_id="BUG-2026-07-11-0001",
                case_type="bug",
                status="open",
            ),
        )

    assert caught.value.error_code == "REPORT_STATUS_MISMATCH"


@pytest.mark.parametrize(
    "case_record",
    [
        _case_record(
            case_id="BUG-2026-07-11-0002",
            doc_name="BUG-2026-07-11-0001",
            status="closed",
        ),
        _case_record(
            case_id="BUG-2026-07-11-0001",
            case_type="security",
            doc_type="bug",
            status="closed",
        ),
        _case_record(
            case_id="BUG-2026-07-11-0001",
            doc_type="security",
            status="closed",
        ),
        _case_record(
            case_id="BUG-2026-07-11-0001",
            doc_name="BUG-2026-07-11-0002",
            status="closed",
        ),
    ],
)
def test_registry_identity_binding_is_exact(case_record: CaseRegistryRecord) -> None:
    with pytest.raises(CaseReopenValidationError) as caught:
        build_reopen_transition_decision(
            case_id="BUG-2026-07-11-0001",
            case_record=case_record,
            target_status="investigating",
            report=GovernedCaseReportProjection(
                case_id="BUG-2026-07-11-0001",
                case_type="bug",
                status="investigating",
            ),
        )

    assert caught.value.error_code == "REGISTRY_IDENTITY_MISMATCH"


def test_reopen_decision_serialization_is_exact_and_deterministic() -> None:
    record = _case_record(
        case_id="SEC-2026-07-11-0001",
        case_type="security",
        status="closed",
    )
    report = GovernedCaseReportProjection(
        case_id="SEC-2026-07-11-0001",
        case_type="security",
        status="investigating",
    )

    first = build_reopen_transition_decision(
        case_id="SEC-2026-07-11-0001",
        case_record=record,
        target_status="investigating",
        report=report,
    )
    second = build_reopen_transition_decision(
        case_id="SEC-2026-07-11-0001",
        case_record=record,
        target_status="investigating",
        report=report,
    )

    assert (
        first
        == second
        == CaseReopenDecision(
            case_id="SEC-2026-07-11-0001",
            case_type="security",
            registry_status_before="closed",
            target_status="investigating",
            report_case_id="SEC-2026-07-11-0001",
            report_case_type="security",
            report_status="investigating",
            transition_required=True,
            idempotent=False,
        )
    )
    assert first.to_dict() == {
        "case_id": "SEC-2026-07-11-0001",
        "case_type": "security",
        "registry_status_before": "closed",
        "target_status": "investigating",
        "report_case_id": "SEC-2026-07-11-0001",
        "report_case_type": "security",
        "report_status": "investigating",
        "transition_required": True,
        "idempotent": False,
    }
    assert record.status == "closed"
