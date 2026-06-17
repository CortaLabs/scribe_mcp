"""F5 — link_fix completeness ENFORCEMENT gate (P1.6).

Proves that closing a case via ``link_fix`` is refused while the report still
lacks required-section content, that a complete report still closes, and that
non-closing / non-fix-terminal landing statuses are never gated.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from scribe_mcp.tools.sentinel_tools import link_fix


# ---------------------------------------------------------------------------
# Helpers (mirror tests/test_sentinel_tools.py fixture shapes)
# ---------------------------------------------------------------------------

def _make_execution_context(mode: str = "project") -> SimpleNamespace:
    return SimpleNamespace(
        mode=mode,
        repo_root="/tmp",
        execution_id="exec-live-123",
        parent_execution_id=None,
        stable_session_id="session-1",
        authoritative_session_key="session-1",
        resolved_scope=SimpleNamespace(
            repo_root="/tmp",
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

    def compute_repo_id(self, repo_root: str) -> str:
        import hashlib

        return hashlib.sha256(repo_root.encode("utf-8")).hexdigest()

    def seed_case(self, *, case_id: str, doc_name: str | None = None) -> None:
        kind = "security" if case_id.startswith("SEC-") else "bug"
        self.records[case_id] = SimpleNamespace(
            case_id=case_id,
            case_type=kind,
            repo_root="/tmp",
            project_name="test-project",
            project_key="repo-key:test-project",
            doc_type=kind,
            doc_name=doc_name or case_id,
            doc_path=f"/tmp/docs/{'security' if kind == 'security' else 'bugs'}/runtime/{case_id}/report.md",
            metadata={},
        )

    async def upsert_case_registry_record(self, **kwargs: Any):
        self.upsert_calls.append(kwargs)
        record = SimpleNamespace(**kwargs)
        self.records[str(kwargs["case_id"])] = record
        return record

    async def fetch_case_registry_record(self, case_id: str, **_kwargs: Any):
        return self.records.get(case_id)


def _make_append_result(ok: bool = True) -> Dict[str, Any]:
    return {
        "ok": ok,
        "id": "test-entry-id",
        "path": "/tmp/test-project/PROGRESS_LOG.md",
        "project_name": "test-project",
    }


def _quality_fail_result() -> Dict[str, Any]:
    """Shape returned by manage_docs(action='quality_check') for an incomplete report."""
    return {
        "ok": True,
        "quality_status": "fail",
        "warnings": [
            {"code": "SCF_PLACEHOLDER_BRACKET", "message": "[UNFILLED] placeholder remains", "blocking": True},
        ],
        "readiness_blockers": [
            {
                "code": "SCF_PLACEHOLDER_BRACKET",
                "message": "[UNFILLED] placeholder remains in root_cause/fix",
                "blocking": True,
                "suggested_repair": "Replace [UNFILLED] with real content.",
            }
        ],
    }


def _quality_pass_result() -> Dict[str, Any]:
    return {"ok": True, "quality_status": "pass", "warnings": [], "readiness_blockers": []}


def _manage_docs_router(*, quality_result: Dict[str, Any]) -> AsyncMock:
    """A manage_docs mock that returns the quality result for quality_check calls
    and a generic ok=True for replace_section (report-body) calls."""

    async def _route(*_args: Any, **kwargs: Any) -> Dict[str, Any]:
        if kwargs.get("action") == "quality_check":
            return dict(quality_result)
        return {"ok": True, "path": "/tmp/report.md"}

    return AsyncMock(side_effect=_route)


# ---------------------------------------------------------------------------
# (a) incomplete report + fix-terminal close -> REFUSED, stays open
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_fix_blocks_incomplete_report_on_fix_terminal_close() -> None:
    ctx = _make_execution_context("project")
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")

    mock_append = AsyncMock(return_value=_make_append_result())
    mock_manage = _manage_docs_router(quality_result=_quality_fail_result())

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="src/module.py:42",
            landing_status="merged",  # fix-terminal
        )

    # Teaching refusal: never raises, returns an envelope.
    assert result["ok"] is True
    assert result.get("partial") is True
    assert result["completeness_gate"]["blocked"] is True
    assert any("cannot be closed" in w for w in result["warnings"])
    assert any("SCF_PLACEHOLDER_BRACKET" in w for w in result["warnings"])
    assert result["case_event"]["event"] == "fix_link_blocked_incomplete"

    # The case was NOT closed: no registry upsert, no report mutation occurred.
    assert backend.upsert_calls == [], "blocked close must not write a closed registry record"
    assert mock_append.call_count == 0, "blocked close must not append the fix-linked entry"
    # quality_check ran; replace_section (report body update) did NOT.
    actions = [c.kwargs.get("action") for c in mock_manage.call_args_list]
    assert "quality_check" in actions
    assert "replace_section" not in actions


# ---------------------------------------------------------------------------
# (b) complete report + fix-terminal close -> SUCCEEDS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_fix_allows_complete_report_on_fix_terminal_close() -> None:
    ctx = _make_execution_context("project")
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0002")

    mock_append = AsyncMock(return_value=_make_append_result())
    mock_manage = _manage_docs_router(quality_result=_quality_pass_result())

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0002",
            execution_id="exec-live-123",
            artifact_ref="src/module.py:42",
            landing_status="merged",
        )

    assert result["ok"] is True
    assert result.get("completeness_gate") is None  # gate did not fire as a blocker
    assert result.get("partial") is not True
    # Close actually happened: registry upsert recorded the closed status.
    assert len(backend.upsert_calls) == 1
    assert backend.upsert_calls[0].get("status") == "closed"
    # Report body was updated.
    actions = [c.kwargs.get("action") for c in mock_manage.call_args_list]
    assert "replace_section" in actions


# ---------------------------------------------------------------------------
# (c) non-closing landing_status -> NOT gated, even with incomplete report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_fix_does_not_gate_non_terminal_status() -> None:
    ctx = _make_execution_context("project")
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0003")

    mock_append = AsyncMock(return_value=_make_append_result())
    # Quality would fail, but the gate must never even consult it for a
    # non-terminal status -> the case stays open by design, not by refusal.
    mock_manage = _manage_docs_router(quality_result=_quality_fail_result())

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0003",
            execution_id="exec-live-123",
            artifact_ref="src/module.py:42",
            landing_status="proposed",  # non-terminal: case stays open, not a close
        )

    assert result["ok"] is True
    # Not a completeness refusal.
    assert result.get("completeness_gate") is None
    assert result["case_event"]["event"] != "fix_link_blocked_incomplete"
    # The non-terminal path proceeded (fix link recorded); registry upsert ran
    # with a non-closed status (None) so the case stays open.
    assert len(backend.upsert_calls) == 1
    assert backend.upsert_calls[0].get("status") is None
    # quality_check must NOT have been consulted for a non-terminal status.
    actions = [c.kwargs.get("action") for c in mock_manage.call_args_list]
    assert "quality_check" not in actions


# ---------------------------------------------------------------------------
# (d) non-FIX terminal status (wontfix) -> NOT gated; closes verbatim
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_fix_does_not_gate_nonfix_terminal_status() -> None:
    ctx = _make_execution_context("project")
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0004")

    mock_append = AsyncMock(return_value=_make_append_result())
    mock_manage = _manage_docs_router(quality_result=_quality_fail_result())

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0004",
            execution_id="exec-live-123",
            artifact_ref="src/module.py:42",
            landing_status="wontfix",  # non-fix terminal: closes, but not as a fix
        )

    assert result["ok"] is True
    assert result.get("completeness_gate") is None
    # Closed as a non-fix outcome: status preserved verbatim, not refused.
    assert len(backend.upsert_calls) == 1
    assert backend.upsert_calls[0].get("status") == "wontfix"
    actions = [c.kwargs.get("action") for c in mock_manage.call_args_list]
    assert "quality_check" not in actions
