from __future__ import annotations

from scribe_mcp.case_lifecycle import (
    CaseLifecycleResult,
    build_canonical_doc_binding,
    build_link_fix_lifecycle_result,
    case_status_snapshot,
    doc_binding_from_metadata,
    doc_binding_to_metadata,
    normalize_landing_status,
    resolve_registry_status_after,
)
from scribe_mcp.storage.models import CaseRegistryRecord


def _case_record(
    *,
    case_id: str = "BUG-2026-06-25-0001",
    case_type: str = "bug",
    status: str | None = "open",
    metadata: dict[str, object] | None = None,
) -> CaseRegistryRecord:
    return CaseRegistryRecord(
        case_id=case_id,
        case_type=case_type,
        project_name="scribe_bug_tools_hardening_062526",
        repo_root="/tmp/repo",
        repo_id="repo-1",
        project_key="project-key",
        doc_type=case_type,
        doc_name=case_id,
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
