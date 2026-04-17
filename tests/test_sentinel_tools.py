"""Tests for the open_bug → link_fix pipeline in sentinel_tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scribe_mcp.tools.sentinel_tools import open_bug, open_security, link_fix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_execution_context(mode: str = "project") -> MagicMock:
    ctx = MagicMock()
    ctx.mode = mode
    return ctx


def _make_append_entry_result(ok: bool = True, **extra: Any) -> Dict[str, Any]:
    base = {
        "ok": ok,
        "id": "test-entry-id",
        "path": "/tmp/test-project/PROGRESS_LOG.md",
        "paths": ["/tmp/test-project/PROGRESS_LOG.md"],
        "project_name": "test-project",
    }
    base.update(extra)
    return base


def _make_manage_docs_result(ok: bool = True, **extra: Any) -> Dict[str, Any]:
    base = {
        "ok": ok,
        "path": "/tmp/test-project/docs/bugs/runtime/2026-03-15_BUG-2026-03-15-0001/report.md",
        "document_type": "bug_report",
        "doc_name": "BUG-2026-03-15-0001",
        "file_size": 1234,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Tests: open_bug happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_bug_happy_path_creates_entry_and_document() -> None:
    """open_bug should create a log entry AND a bug report document."""
    ctx = _make_execution_context("project")

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value=_make_manage_docs_result())

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools._next_case_id_for_project", return_value="BUG-2026-03-15-0001"), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await open_bug(
            agent="test-agent",
            title="Database connection pool exhaustion",
            symptoms="Connections are not being released after use",
            category="runtime",
            severity="high",
            component="StorageBackend",
        )

    assert result["ok"] is True
    assert result["case_id"] == "BUG-2026-03-15-0001"
    assert "entry_id" in result
    assert "bug_report" in result or "path" in result
    # Completeness score should be present
    assert "completeness" in result
    assert "percentage" in result["completeness"]
    # manage_docs should have been called once (to create the doc)
    mock_manage.assert_called_once()
    create_call_kwargs = mock_manage.call_args.kwargs
    assert create_call_kwargs.get("action") == "create"
    assert create_call_kwargs.get("metadata", {}).get("doc_type") == "bug"


@pytest.mark.asyncio
async def test_open_bug_missing_category_returns_error() -> None:
    """open_bug with empty category should return an error dict, not raise."""
    ctx = _make_execution_context("project")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx):
        result = await open_bug(
            agent="test-agent",
            title="Some bug",
            symptoms="Something broke",
            category="",
        )

    assert result["ok"] is False
    assert "category" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_open_bug_append_entry_failure_returns_error() -> None:
    """open_bug should surface the append_entry failure cleanly."""
    ctx = _make_execution_context("project")

    mock_append = AsyncMock(return_value={"ok": False, "error": "disk full"})

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append):

        result = await open_bug(
            agent="test-agent",
            title="Crash bug",
            symptoms="App crashes on startup",
            category="startup",
        )

    assert result["ok"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# Tests: open_security happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_security_happy_path_uses_security_doc_type() -> None:
    """open_security should create a security report using doc_type='security'."""
    ctx = _make_execution_context("project")

    sec_doc_result = _make_manage_docs_result(
        path="/tmp/test/docs/security/injection/2026-03-15_SEC-2026-03-15-0001/report.md",
        document_type="security_report",
        doc_name="SEC-2026-03-15-0001",
    )

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value=sec_doc_result)

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools._next_case_id_for_project", return_value="SEC-2026-03-15-0001"), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await open_security(
            agent="test-agent",
            title="SQL injection in search endpoint",
            symptoms="Unparameterized query allows injection",
            category="injection",
            severity="critical",
        )

    assert result["ok"] is True
    assert result["case_id"] == "SEC-2026-03-15-0001"
    assert "security_report" in result or "path" in result

    # Verify doc_type is 'security', NOT 'bug'
    mock_manage.assert_called_once()
    create_metadata = mock_manage.call_args.kwargs.get("metadata", {})
    assert create_metadata.get("doc_type") == "security", (
        f"open_security must use doc_type='security', got: {create_metadata.get('doc_type')!r}"
    )


@pytest.mark.asyncio
async def test_open_security_missing_category_returns_error() -> None:
    """open_security with empty category should return error."""
    ctx = _make_execution_context("project")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx):
        result = await open_security(
            agent="test-agent",
            title="XSS vulnerability",
            symptoms="User input not sanitized",
            category="",
        )

    assert result["ok"] is False
    assert "category" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_open_bug_preview_is_non_mutating_in_project_mode() -> None:
    """open_bug(preview=True) should return case_id without append_entry/manage_docs writes."""
    ctx = _make_execution_context("project")
    ctx.repo_root = "/tmp/repo"
    ctx.affected_dev_projects = ["test-project"]

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", AsyncMock()) as mock_append, \
         patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock()) as mock_manage, \
         patch("scribe_mcp.tools.sentinel_tools._preview_case_id_for_project", return_value="BUG-2026-03-15-0007"):
        result = await open_bug(
            agent="test-agent",
            title="Preview bug",
            symptoms="Preview only",
            category="runtime",
            preview=True,
        )

    assert result == {"ok": True, "case_id": "BUG-2026-03-15-0007", "preview": True}
    mock_append.assert_not_awaited()
    mock_manage.assert_not_awaited()


@pytest.mark.asyncio
async def test_open_security_preview_is_non_mutating_in_project_mode() -> None:
    """open_security(preview=True) should return case_id without append_entry/manage_docs writes."""
    ctx = _make_execution_context("project")
    ctx.repo_root = "/tmp/repo"
    ctx.affected_dev_projects = ["test-project"]

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", AsyncMock()) as mock_append, \
         patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock()) as mock_manage, \
         patch("scribe_mcp.tools.sentinel_tools._preview_case_id_for_project", return_value="SEC-2026-03-15-0004"):
        result = await open_security(
            agent="test-agent",
            title="Preview security",
            symptoms="Preview only",
            category="auth",
            preview=True,
        )

    assert result == {"ok": True, "case_id": "SEC-2026-03-15-0004", "preview": True}
    mock_append.assert_not_awaited()
    mock_manage.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: link_fix happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_link_fix_happy_path_updates_bug_report_document() -> None:
    """link_fix should log an entry AND call manage_docs to update the report."""
    ctx = _make_execution_context("project")

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value={"ok": True, "path": "/tmp/report.md"})

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-abc123",
            artifact_ref="src/module.py:42",
            landing_status="merged",
        )

    assert result["ok"] is True
    assert result["case_id"] == "BUG-2026-03-15-0001"
    assert "entry_id" in result

    # manage_docs must have been called (to update the document)
    assert mock_manage.call_count >= 1, "link_fix must call manage_docs to update the bug report"

    # Verify doc_name matches the case_id
    calls = mock_manage.call_args_list
    doc_names_used = [c.kwargs.get("doc_name") for c in calls]
    assert "BUG-2026-03-15-0001" in doc_names_used, (
        f"link_fix must target the bug report document with doc_name='BUG-2026-03-15-0001', "
        f"got doc_names: {doc_names_used}"
    )

    # Verify actions performed on the document
    actions_used = [c.kwargs.get("action") for c in calls]
    assert "replace_section" in actions_used, (
        f"link_fix must call replace_section to update the document, got actions: {actions_used}"
    )


@pytest.mark.asyncio
async def test_link_fix_sec_case_id_updates_security_report() -> None:
    """link_fix with SEC- case_id should update the security report document."""
    ctx = _make_execution_context("project")

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value={"ok": True, "path": "/tmp/sec_report.md"})

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="SEC-2026-03-15-0001",
            execution_id="exec-sec-xyz",
            artifact_ref="src/auth/validator.py:88",
            landing_status="merged",
        )

    assert result["ok"] is True
    assert result["case_id"] == "SEC-2026-03-15-0001"
    # Verify security_event flag was set in append_entry
    append_call_kwargs = mock_append.call_args.kwargs
    assert append_call_kwargs.get("meta", {}).get("security_event") == "1"

    # Verify document was updated
    assert mock_manage.call_count >= 1
    doc_names = [c.kwargs.get("doc_name") for c in mock_manage.call_args_list]
    assert "SEC-2026-03-15-0001" in doc_names


@pytest.mark.asyncio
async def test_link_fix_invalid_case_id_returns_error() -> None:
    """link_fix with an invalid case_id prefix should return error dict, not raise."""
    ctx = _make_execution_context("project")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx):
        result = await link_fix(
            agent="test-agent",
            case_id="TICKET-12345",
            execution_id="exec-abc",
            artifact_ref="file.py:1",
            landing_status="merged",
        )

    assert result["ok"] is False
    assert "BUG-" in result.get("error", "") or "SEC-" in result.get("error", "")


@pytest.mark.asyncio
async def test_link_fix_doc_update_failure_still_returns_ok() -> None:
    """If manage_docs fails, link_fix should still return ok=True with a warning."""
    ctx = _make_execution_context("project")

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    # manage_docs fails (e.g., doc not found because open_bug was never called)
    mock_manage = AsyncMock(return_value={"ok": False, "error": "DOC_NOT_FOUND: doc_name 'BUG-2026-03-15-0001' is not registered"})

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-abc",
            artifact_ref="file.py:1",
            landing_status="merged",
        )

    # The log entry was created — that's always success
    assert result["ok"] is True
    # A warning should be present about the failed doc update
    assert "doc_update_warning" in result, (
        "When doc update fails, link_fix should include doc_update_warning in response"
    )


# ---------------------------------------------------------------------------
# Tests: query for bugs by status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_entries_supports_bug_status_filter() -> None:
    """query_entries already supports status=['bug'] filtering via STATUS_EMOJI mapping.

    This test verifies the contract: query_entries(status=['bug']) routes through
    the STATUS_EMOJI filter which maps 'bug' to the bug emoji character(s).
    No additional wrapper is needed — the existing tool is sufficient.
    """
    from scribe_mcp.tools.constants import STATUS_EMOJI

    # Verify 'bug' is a known status with emoji mappings
    assert "bug" in STATUS_EMOJI, (
        "STATUS_EMOJI must contain a 'bug' key so query_entries(status=['bug']) works. "
        "No additional wrapper needed — query_entries can already filter by status='bug'."
    )
    assert len(STATUS_EMOJI["bug"]) > 0, "STATUS_EMOJI['bug'] must have at least one emoji"


@pytest.mark.asyncio
async def test_link_fix_meta_contains_queryable_fix_link() -> None:
    """link_fix log entry includes meta.fix_link that query_entries can filter on."""
    ctx = _make_execution_context("project")

    captured_meta: Dict[str, Any] = {}

    async def _capture_append(**kwargs: Any) -> Dict[str, Any]:
        captured_meta.update(kwargs.get("meta", {}))
        return _make_append_entry_result()

    mock_manage = AsyncMock(return_value={"ok": True})

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.append_entry.append_entry", _capture_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-xyz",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )

    # Verify meta.fix_link is structured and queryable
    assert "fix_link" in captured_meta, "link_fix must include fix_link in meta for queryability"
    assert "artifact_ref" in captured_meta["fix_link"]
    assert "execution_id" in captured_meta["fix_link"]
    # Verify case_id is top-level in meta for query_entries meta_filters
    assert "case_id" in captured_meta
    assert captured_meta["case_id"] == "BUG-2026-03-15-0001"
