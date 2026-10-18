from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from scribe_mcp.tools.sentinel_tools import link_fix


def _make_execution_context() -> SimpleNamespace:
    return SimpleNamespace(
        mode="project",
        repo_root="/tmp/repo",
        execution_id="exec-live",
        parent_execution_id=None,
        stable_session_id="session-1",
        authoritative_session_key="session-1",
        resolved_scope=SimpleNamespace(
            repo_root="/tmp/repo",
            project_name="test-project",
            trust_level="verified",
            resolution_source="runtime_context",
            provenance=SimpleNamespace(repo_root="verified", project_name="verified"),
        ),
    )


class _RegistryBackend:
    def __init__(self) -> None:
        self.records: Dict[str, SimpleNamespace] = {}
        self.upsert_calls: list[dict[str, Any]] = []

    async def upsert_case_registry_record(self, **kwargs: Any) -> SimpleNamespace:
        self.upsert_calls.append(kwargs)
        record = SimpleNamespace(**kwargs)
        self.records[str(kwargs["case_id"])] = record
        return record

    async def fetch_case_registry_record(self, case_id: str, **_kwargs: Any) -> SimpleNamespace | None:
        return self.records.get(case_id)

    def seed_case(self, *, case_id: str, status: str | None = "open") -> None:
        kind = "security" if case_id.startswith("SEC-") else "bug"
        self.records[case_id] = SimpleNamespace(
            case_id=case_id,
            case_type=kind,
            repo_root="/tmp/repo",
            project_name="test-project",
            project_key="repo-key:test-project",
            doc_type=kind,
            doc_name=case_id,
            doc_path=f"/tmp/repo/docs/{kind}s/runtime/{case_id}/report.md",
            status=status,
            severity="high",
            metadata={},
        )


def _append_result() -> dict[str, Any]:
    return {
        "ok": True,
        "id": "entry-1",
        "path": "/tmp/repo/.scribe/docs/dev_plans/test-project/PROGRESS_LOG.md",
        "project_name": "test-project",
    }


def _quality_pass_result() -> dict[str, Any]:
    return {"ok": True, "quality_status": "pass", "warnings": [], "readiness_blockers": []}


def _quality_fail_result() -> dict[str, Any]:
    return {
        "ok": True,
        "quality_status": "fail",
        "warnings": [{"code": "SCF_PLACEHOLDER_BRACKET", "blocking": True}],
        "readiness_blockers": [
            {
                "code": "SCF_PLACEHOLDER_BRACKET",
                "message": "placeholder remains in required sections",
                "blocking": True,
            }
        ],
    }


def _manage_docs_router(
    *,
    quality_result: dict[str, Any] | None = None,
    doc_update_ok: bool = True,
) -> AsyncMock:
    async def _route(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("action") == "quality_check":
            return dict(quality_result or _quality_pass_result())
        if doc_update_ok:
            return {"ok": True, "path": "/tmp/repo/report.md"}
        return {"ok": False, "error": "doc write failed"}

    return AsyncMock(side_effect=_route)


async def _call_link_fix(
    *,
    backend: _RegistryBackend,
    landing_status: str,
    manage_docs_mock: AsyncMock,
    append_mock: AsyncMock | None = None,
    case_id: str = "BUG-2026-06-25-0001",
) -> dict[str, Any]:
    with (
        patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=_make_execution_context()),
        patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend),
        patch("scribe_mcp.tools.append_entry.append_entry", append_mock or AsyncMock(return_value=_append_result())),
        patch("scribe_mcp.tools.manage_docs.manage_docs", manage_docs_mock),
    ):
        return await link_fix(
            agent="test-agent",
            case_id=case_id,
            execution_id="exec-live",
            artifact_ref="src/module.py:42",
            landing_status=landing_status,
        )


@pytest.mark.asyncio
async def test_link_fix_non_terminal_records_link_but_keeps_case_open() -> None:
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-06-25-0001", status="open")

    result = await _call_link_fix(
        backend=backend,
        landing_status="in_progress",
        manage_docs_mock=_manage_docs_router(),
    )

    assert result["ok"] is True
    assert result["fix_link_recorded"] is True
    assert result["case_closed"] is False
    assert result["registry_status_before"] == "open"
    assert result["registry_status_after"] == "open"
    assert result["landing_status_terminal"] is False
    assert result["closure_reason"] is None
    assert result["last_fix_link"]["landing_status"] == "in_progress"
    assert result["doc_binding"]["canonical_doc_name"] == "BUG-2026-06-25-0001"
    assert result["lifecycle"]["case_closed"] is False
    assert "remains open" in result["next_step"]
    assert "merged" in result["next_step"]
    assert "resolved" in result["next_step"]


@pytest.mark.asyncio
async def test_link_fix_terminal_fix_status_closes_case() -> None:
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-06-25-0002", status="open")

    result = await _call_link_fix(
        backend=backend,
        landing_status="merged",
        manage_docs_mock=_manage_docs_router(quality_result=_quality_pass_result()),
        case_id="BUG-2026-06-25-0002",
    )

    assert result["ok"] is True
    assert result["fix_link_recorded"] is True
    assert result["case_closed"] is True
    assert result["registry_status_before"] == "open"
    assert result["registry_status_after"] == "closed"
    assert result["landing_status_terminal"] is True
    assert result["closure_reason"] == "closed"
    assert result["lifecycle"]["case_closed"] is True


@pytest.mark.asyncio
async def test_link_fix_non_fix_terminal_preserves_closure_reason() -> None:
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-06-25-0003", status="investigating")

    result = await _call_link_fix(
        backend=backend,
        landing_status="wontfix",
        manage_docs_mock=_manage_docs_router(),
        case_id="BUG-2026-06-25-0003",
    )

    assert result["ok"] is True
    assert result["fix_link_recorded"] is True
    assert result["case_closed"] is True
    assert result["registry_status_before"] == "investigating"
    assert result["registry_status_after"] == "wontfix"
    assert result["landing_status_terminal"] is True
    assert result["closure_reason"] == "wontfix"


@pytest.mark.asyncio
async def test_link_fix_partial_doc_update_warning_keeps_lifecycle_fields() -> None:
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-06-25-0004", status="open")

    result = await _call_link_fix(
        backend=backend,
        landing_status="merged",
        manage_docs_mock=_manage_docs_router(quality_result=_quality_pass_result(), doc_update_ok=False),
        case_id="BUG-2026-06-25-0004",
    )

    assert result["ok"] is True
    assert result["partial"] is True
    assert result["doc_update_warning"] == "doc write failed"
    assert result["fix_link_recorded"] is True
    assert result["case_closed"] is True
    assert result["registry_status_after"] == "closed"
    assert result["lifecycle"]["doc_binding"]["canonical_doc_name"] == "BUG-2026-06-25-0004"
    assert "manage_docs replace_section" in result["next_step"]


@pytest.mark.asyncio
async def test_link_fix_completeness_gate_blocks_before_lifecycle_mutation() -> None:
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-06-25-0005", status="open")
    append_mock = AsyncMock(return_value=_append_result())

    result = await _call_link_fix(
        backend=backend,
        landing_status="merged",
        manage_docs_mock=_manage_docs_router(quality_result=_quality_fail_result()),
        append_mock=append_mock,
        case_id="BUG-2026-06-25-0005",
    )

    assert result["ok"] is True
    assert result["partial"] is True
    assert result["completeness_gate"]["blocked"] is True
    assert "fix_link_recorded" not in result
    assert backend.upsert_calls == []
    append_mock.assert_not_awaited()
