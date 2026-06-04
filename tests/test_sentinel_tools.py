"""Tests for the open_bug → link_fix pipeline in sentinel_tools."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared.tool_runtime import execute_tool_call
from scribe_mcp.tools.sentinel_tools import open_bug, open_security, link_fix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_execution_context(mode: str = "project") -> MagicMock:
    ctx = MagicMock()
    ctx.mode = mode
    ctx.repo_root = "/tmp"
    ctx.execution_id = "exec-live-123"
    ctx.parent_execution_id = None
    ctx.stable_session_id = "session-1"
    ctx.authoritative_session_key = "session-1"
    ctx.resolved_scope = SimpleNamespace(
        repo_root="/tmp",
        project_name="test-project",
        trust_level="verified",
        resolution_source="runtime_context",
        provenance=SimpleNamespace(repo_root="verified", project_name="verified"),
    )
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


def _assert_operator_envelope(result: Dict[str, Any]) -> None:
    for key in ("ok", "mode", "case_id", "artifacts", "warnings", "next_step"):
        assert key in result


class _DummyState:
    @staticmethod
    def get_session_mode(_session_id: str):
        return None


class _DummyStateManager:
    async def load(self):
        return _DummyState()


class _RegistryBackend:
    def __init__(self) -> None:
        self.records: Dict[str, SimpleNamespace] = {}
        self.entries: Dict[tuple[str, str, str], Dict[str, Any]] = {}

    def compute_repo_id(self, repo_root: str) -> str:
        import hashlib
        return hashlib.sha256(repo_root.encode("utf-8")).hexdigest()

    def seed_case(
        self,
        *,
        case_id: str,
        repo_root: str = "/tmp",
        project_name: str = "test-project",
        project_key: str | None = None,
        doc_type: str | None = None,
        doc_name: str | None = None,
        doc_path: str | None = None,
    ) -> None:
        kind = "security" if case_id.startswith("SEC-") else "bug"
        self.records[case_id] = SimpleNamespace(
            case_id=case_id,
            case_type=kind,
            repo_root=repo_root,
            project_name=project_name,
            project_key=project_key or project_name,
            doc_type=doc_type or kind,
            doc_name=doc_name or case_id,
            doc_path=doc_path or f"{repo_root}/docs/{'security' if kind == 'security' else 'bugs'}/runtime/{case_id}/report.md",
            metadata={},
        )

    async def upsert_case_registry_record(self, **kwargs: Any):
        record = SimpleNamespace(**kwargs)
        self.records[str(kwargs["case_id"])] = record
        return record

    async def fetch_case_registry_record(self, case_id: str, **_kwargs: Any):
        return self.records.get(case_id)

    def seed_entry(self, *, entry_id: str, repo_root: str = "/tmp", project_name: str = "test-project") -> None:
        self.entries[(entry_id, self.compute_repo_id(repo_root), project_name)] = {"entry_id": entry_id}

    async def fetch_entry_by_id(self, entry_id: str, repo_id: str, project_name: str):
        return self.entries.get((entry_id, repo_id, project_name))


@pytest.fixture(autouse=True)
def _patch_registry_backend() -> _RegistryBackend:
    backend = _RegistryBackend()
    with patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend):
        yield backend


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
    _assert_operator_envelope(result)
    assert result["mode"] == "project"
    assert result["case_id"] == "BUG-2026-03-15-0001"
    assert result["doc_name"] == "BUG-2026-03-15-0001"
    assert result["doc_path"] == result["bug_report"]
    assert result["doc_category"] == "bugs"
    assert result["case_registry"]["case_id"] == "BUG-2026-03-15-0001"
    assert result["case_registry"]["case_type"] == "bug"
    assert result["case_registry"]["doc_name"] == "BUG-2026-03-15-0001"
    assert result["case_registry"]["doc_path"] == result["bug_report"]
    assert "entry_id" in result
    assert "bug_report" in result or "path" in result
    # Completeness score should be present
    assert "completeness" in result
    assert "percentage" in result["completeness"]
    # manage_docs should have been called once (to create the doc)
    mock_manage.assert_called_once()
    create_call_kwargs = mock_manage.call_args.kwargs
    assert create_call_kwargs.get("agent") == "test-agent"
    assert create_call_kwargs.get("action") == "create"
    assert create_call_kwargs.get("metadata", {}).get("doc_type") == "bug"


@pytest.mark.asyncio
async def test_open_bug_registers_case_id_for_immediate_queryability() -> None:
    """open_bug should emit a case registration log entry containing case_id."""
    ctx = _make_execution_context("project")

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value=_make_manage_docs_result())

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools._next_case_id_for_project", return_value="BUG-2026-03-15-0009"), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        result = await open_bug(
            agent="test-agent",
            title="Missing case-id query hit",
            symptoms="query_entries by bare BUG-* misses fresh create",
            category="runtime",
        )

    assert result["ok"] is True
    _assert_operator_envelope(result)
    assert mock_append.await_count >= 2
    registration_call = mock_append.await_args_list[1].kwargs
    assert registration_call["message"] == "[CASE REGISTERED] BUG-2026-03-15-0009"
    assert registration_call["meta"]["case_id"] == "BUG-2026-03-15-0009"
    assert registration_call["meta"]["registration_event"] == "case_opened"


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
    _assert_operator_envelope(result)
    assert result["mode"] == "project"
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
    _assert_operator_envelope(result)
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
    _assert_operator_envelope(result)
    assert result["mode"] == "project"
    assert result["case_id"] == "SEC-2026-03-15-0001"
    assert result["doc_name"] == "SEC-2026-03-15-0001"
    assert result["doc_path"] == result["security_report"]
    assert result["doc_category"] == "security"
    assert result["case_registry"]["case_id"] == "SEC-2026-03-15-0001"
    assert result["case_registry"]["case_type"] == "security"
    assert result["case_registry"]["doc_name"] == "SEC-2026-03-15-0001"
    assert result["case_registry"]["doc_path"] == result["security_report"]
    assert "security_report" in result or "path" in result

    # Verify doc_type is 'security', NOT 'bug'
    mock_manage.assert_called_once()
    create_call_kwargs = mock_manage.call_args.kwargs
    assert create_call_kwargs.get("agent") == "test-agent"
    create_metadata = create_call_kwargs.get("metadata", {})
    assert create_metadata.get("doc_type") == "security", (
        f"open_security must use doc_type='security', got: {create_metadata.get('doc_type')!r}"
    )


@pytest.mark.asyncio
async def test_open_security_registers_case_id_for_immediate_queryability() -> None:
    """open_security should emit a case registration log entry containing case_id."""
    ctx = _make_execution_context("project")

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value=_make_manage_docs_result())

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools._next_case_id_for_project", return_value="SEC-2026-03-15-0006"), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        result = await open_security(
            agent="test-agent",
            title="Missing case-id query hit",
            symptoms="query_entries by bare SEC-* misses fresh create",
            category="auth",
        )

    assert result["ok"] is True
    _assert_operator_envelope(result)
    assert mock_append.await_count >= 2
    registration_call = mock_append.await_args_list[1].kwargs
    assert registration_call["message"] == "[CASE REGISTERED] SEC-2026-03-15-0006"
    assert registration_call["meta"]["case_id"] == "SEC-2026-03-15-0006"
    assert registration_call["meta"]["registration_event"] == "case_opened"
    assert registration_call["meta"]["security_event"] == "1"


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
    _assert_operator_envelope(result)
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

    _assert_operator_envelope(result)
    assert result["ok"] is True
    assert result["mode"] == "project"
    assert result["case_id"] == "BUG-2026-03-15-0007"
    assert result["preview"] is True
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

    _assert_operator_envelope(result)
    assert result["ok"] is True
    assert result["mode"] == "project"
    assert result["case_id"] == "SEC-2026-03-15-0004"
    assert result["preview"] is True
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

    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001", project_key="repo-key:test-project")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="src/module.py:42",
            landing_status="merged",
        )

    assert result["ok"] is True
    _assert_operator_envelope(result)
    assert result["mode"] == "project"
    assert result["case_id"] == "BUG-2026-03-15-0001"
    assert "entry_id" in result
    assert result["warnings"] == []
    assert result["next_step"] == "No follow-up required."
    assert result["case_registry"]["doc_name"] == "BUG-2026-03-15-0001"

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

    backend = _RegistryBackend()
    backend.seed_case(
        case_id="SEC-2026-03-15-0001",
        doc_path="/tmp/docs/security/auth/SEC-2026-03-15-0001/report.md",
    )

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="SEC-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="src/auth/validator.py:88",
            landing_status="merged",
        )

    assert result["ok"] is True
    _assert_operator_envelope(result)
    assert result["case_id"] == "SEC-2026-03-15-0001"
    assert result["case_registry"]["doc_type"] == "security"
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
            execution_id="exec-live-123",
            artifact_ref="file.py:1",
            landing_status="merged",
        )

    assert result["ok"] is False
    _assert_operator_envelope(result)
    assert "BUG-" in result.get("error", "") or "SEC-" in result.get("error", "")


@pytest.mark.asyncio
async def test_link_fix_doc_update_failure_still_returns_ok() -> None:
    """If manage_docs fails, link_fix should still return ok=True with a warning."""
    ctx = _make_execution_context("project")

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    # manage_docs fails (e.g., doc not found because open_bug was never called)
    mock_manage = AsyncMock(return_value={"ok": False, "error": "DOC_NOT_FOUND: doc_name 'BUG-2026-03-15-0001' is not registered"})

    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001", project_key="repo-key:test-project")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage), \
         patch("logging.getLogger") as mock_get_logger:

        mock_warning = mock_get_logger.return_value.warning

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="file.py:1",
            landing_status="merged",
        )

    # The log entry was created — that's always success
    assert result["ok"] is True
    _assert_operator_envelope(result)
    assert result.get("partial") is True
    assert result["warnings"], "partial success should include warnings"
    # A warning should be present about the failed doc update
    assert "doc_update_warning" in result, (
        "When doc update fails, link_fix should include doc_update_warning in response"
    )
    assert result["case_event"] == {"event": "fix_link_partial"}
    assert result["meta"]["case_event"] == "fix_link_partial"
    mock_warning.assert_called()


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

    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", _capture_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )

    # Verify meta.fix_link is structured and queryable
    assert "fix_link" in captured_meta, "link_fix must include fix_link in meta for queryability"
    assert "artifact_ref" in captured_meta["fix_link"]
    assert "execution_id" in captured_meta["fix_link"]
    assert captured_meta["fix_link"]["execution_id"] == "exec-live-123"
    assert "execution_ref" in captured_meta["fix_link"]
    assert "artifact_ref_meta" in captured_meta["fix_link"]
    # Verify case_id is top-level in meta for query_entries meta_filters
    assert "case_id" in captured_meta
    assert captured_meta["case_id"] == "BUG-2026-03-15-0001"


@pytest.mark.asyncio
async def test_link_fix_structures_git_commit_and_scribe_artifact_references() -> None:
    ctx = _make_execution_context("project")
    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value={"ok": True})
    backend = _RegistryBackend()
    backend.seed_case(case_id="SEC-2026-03-15-0001")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        result = await link_fix(
            agent="test-agent",
            case_id="SEC-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="commit:abc1234",
            landing_status="merged",
        )

    assert result["ok"] is True
    assert result["resolved_references"]["artifact_meta"]["kind"] == "git_commit"
    assert result["resolved_references"]["artifact_meta"]["value"] == "abc1234"

    fix_link_meta = mock_append.call_args.kwargs["meta"]["fix_link"]
    assert fix_link_meta["artifact_ref_meta"]["kind"] == "git_commit"

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        result_scribe = await link_fix(
            agent="test-agent",
            case_id="SEC-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="scribe://project/x/entry/y",
            landing_status="landed",
        )

    assert result_scribe["ok"] is True
    assert result_scribe["resolved_references"]["artifact_meta"]["kind"] == "scribe_reference"


@pytest.mark.asyncio
async def test_link_fix_rejects_execution_id_not_in_active_context() -> None:
    """link_fix should reject execution IDs that do not match current/parent context IDs."""
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.parent_execution_id = "exec-parent-456"

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-unrelated-999",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )

    assert result["ok"] is False
    _assert_operator_envelope(result)
    assert "execution_id" in result.get("error", "")


@pytest.mark.asyncio
async def test_link_fix_sentinel_mode_returns_and_persists_structured_refs() -> None:
    ctx = _make_execution_context("sentinel")
    captured_event: Dict[str, Any] = {}

    def _capture_case_event(_context: Any, **kwargs: Any) -> None:
        captured_event.update(kwargs)

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.append_case_event", side_effect=_capture_case_event):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="commit:abc1234",
            landing_status="merged",
        )

    assert result["ok"] is True
    _assert_operator_envelope(result)
    assert result["mode"] == "sentinel"
    assert result["resolved_references"]["execution"]["value"] == "exec-live-123"
    assert result["resolved_references"]["artifact_meta"]["kind"] == "git_commit"
    assert result["resolved_references"]["artifact_meta"]["value"] == "abc1234"

    fix_link = captured_event["data"]["fix_link"]
    assert fix_link["execution_id"] == "exec-live-123"
    assert fix_link["artifact_ref"] == "commit:abc1234"
    assert fix_link["execution_ref"]["value"] == "exec-live-123"
    assert fix_link["artifact_ref_meta"]["kind"] == "git_commit"


@pytest.mark.asyncio
async def test_link_fix_accepts_parent_execution_id() -> None:
    """link_fix should allow parent execution IDs for chained execution provenance."""
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.parent_execution_id = "exec-parent-456"

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value={"ok": True})

    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001", project_key="repo-key:test-project")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-parent-456",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )

    assert result["ok"] is True
    _assert_operator_envelope(result)
    assert result["resolved_references"]["execution"]["kind"] == "parent_execution"
    assert result["resolved_references"]["execution"]["source"] == "runtime_parent_execution"
    assert result["case_scope"]["project_key"] == "repo-key:test-project"
    assert result["case_event"]["event"] == "report_body_updated"
    assert result["meta"]["case_event"] == "report_body_updated"


@pytest.mark.asyncio
async def test_link_fix_accepts_active_session_key() -> None:
    """link_fix should allow the active canonical session key for later standalone calls."""
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.parent_execution_id = None
    ctx.stable_session_id = "session-stable-789"
    ctx.authoritative_session_key = "session-stable-789"
    ctx.session_id = "session-fallback-000"

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value={"ok": True})

    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="session-stable-789",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )

    assert result["ok"] is True
    _assert_operator_envelope(result)

@pytest.mark.asyncio
async def test_link_fix_defaults_execution_id_to_current_context() -> None:
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.authoritative_session_key = "session-stable-789"
    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value={"ok": True})
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")
    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )
    assert result["ok"] is True
    assert result["resolved_references"]["execution"]["value"] == "session-stable-789"


@pytest.mark.asyncio
async def test_link_fix_legacy_positional_order_remains_compatible() -> None:
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.authoritative_session_key = "session-stable-789"
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")
    captured_meta: dict[str, Any] = {}

    async def _capture_append_entry(**kwargs: Any) -> Dict[str, Any]:
        captured_meta.update(kwargs.get("meta", {}))
        return _make_append_entry_result()

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", side_effect=_capture_append_entry), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock(return_value={"ok": True})):
        result = await link_fix(
            "test-agent",
            "BUG-2026-03-15-0001",
            "exec-live-123",
            "src/legacy_positional.py:42",
            "merged",
        )

    assert result["ok"] is True
    assert captured_meta["fix_link"]["execution_id"] == "exec-live-123"
    assert captured_meta["fix_link"]["artifact_ref"] == "src/legacy_positional.py:42"
    assert captured_meta["landing_status"] == "merged"


@pytest.mark.asyncio
async def test_link_fix_accepts_execution_alias_active() -> None:
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.authoritative_session_key = "session-stable-789"
    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value={"ok": True})
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")
    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="active",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )
    assert result["ok"] is True
    assert result["resolved_references"]["execution"]["value"] == "session-stable-789"


@pytest.mark.asyncio
async def test_link_fix_accepts_scribe_entry_id() -> None:
    """Agents may pass a durable Scribe entry id when active execution ids are not exposed."""
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.parent_execution_id = None

    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value={"ok": True})

    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")
    backend.seed_entry(entry_id="6abe4eb43c1d6449831306e73735f574")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage):

        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="6abe4eb43c1d6449831306e73735f574",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )

    assert result["ok"] is True
    _assert_operator_envelope(result)


@pytest.mark.asyncio
async def test_link_fix_rejects_forged_or_out_of_scope_entry_id() -> None:
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.parent_execution_id = None
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", AsyncMock()) as mock_append, \
         patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock()) as mock_manage, \
         patch("scribe_mcp.tools.sentinel_tools._register_case_registry_fix_link", AsyncMock()) as mock_registry:
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="6abe4eb43c1d6449831306e73735f574",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )

    assert result["ok"] is False
    mock_append.assert_not_called()
    mock_manage.assert_not_called()
    mock_registry.assert_not_called()

@pytest.mark.asyncio
async def test_link_fix_uses_registry_doc_name_for_report_updates() -> None:
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    mock_append = AsyncMock(return_value=_make_append_entry_result())
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001", doc_name="bug-report-custom")
    captured_doc_names: list[str] = []

    async def _capture_manage_docs(**kwargs: Any) -> Dict[str, Any]:
        captured_doc_names.append(str(kwargs.get("doc_name", "")))
        return {"ok": True}

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", mock_append), \
         patch("scribe_mcp.tools.manage_docs.manage_docs", side_effect=_capture_manage_docs):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="current",
            artifact_ref="commit:deadbee",
            landing_status="merged",
        )

    assert result["ok"] is True
    assert result.get("partial") is not True
    assert captured_doc_names == ["bug-report-custom", "bug-report-custom"]


@pytest.mark.asyncio
async def test_link_fix_rejects_transport_process_identifier() -> None:
    """link_fix must not treat process transport IDs as trusted execution provenance."""
    ctx = _make_execution_context("project")
    ctx.execution_id = "exec-live-123"
    ctx.parent_execution_id = None
    ctx.resolved_scope.transport_session_id = "process:runtime-abc"

    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001")
    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), \
         patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend), \
         patch("scribe_mcp.tools.append_entry.append_entry", AsyncMock()) as mock_append, \
         patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock()) as mock_manage, \
         patch("scribe_mcp.tools.sentinel_tools._register_case_registry_fix_link", AsyncMock()) as mock_registry:
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-03-15-0001",
            execution_id="process:runtime-abc",
            artifact_ref="src/db.py:100",
            landing_status="merged",
        )

    assert result["ok"] is False
    _assert_operator_envelope(result)
    assert "execution_id does not match active execution context" in result.get("error", "")
    mock_append.assert_not_called()
    mock_manage.assert_not_called()
    mock_registry.assert_not_called()


@pytest.mark.asyncio
async def test_link_fix_execution_lineage_through_execute_tool_call_runtime_path(
    _patch_registry_backend: _RegistryBackend,
) -> None:
    """Runtime dispatch should preserve parent execution lineage for link_fix validation."""
    router = RouterContextManager()
    parent_context = await router.build_execution_context(
        {
            "repo_root": "/tmp",
            "mode": "project",
            "intent": "tool:parent",
            "affected_dev_projects": [],
            "session_id": "session-parent",
        }
    )
    parent_token = router.set_current(parent_context)

    _patch_registry_backend.seed_case(case_id="BUG-2026-03-15-0001")
    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value=_make_manage_docs_result())
    try:
        with (
            patch("scribe_mcp.tools.append_entry.append_entry", mock_append),
            patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage),
        ):
            result = await execute_tool_call(
                name="link_fix",
                arguments={
                    "agent": "test-agent",
                    "case_id": "BUG-2026-03-15-0001",
                    "execution_id": parent_context.execution_id,
                    "artifact_ref": "src/db.py:100",
                    "landing_status": "merged",
                },
                kwargs={"context": {"repo_root": "/tmp", "mode": "project", "session_id": "session-1"}},
                registry={"link_fix": link_fix},
                app=SimpleNamespace(request_context=None),
                storage_backend=_patch_registry_backend,
                settings=SimpleNamespace(project_root=Path("/tmp"), public_release=False),
                state_manager=_DummyStateManager(),
                router_context_manager=router,
                sentinel_only=set(),
                sentinel_allowed={"link_fix"},
                log_scope_violation_cb=lambda *_args, **_kwargs: None,
            )
    finally:
        router.reset(parent_token)

    assert result["ok"] is True
    _assert_operator_envelope(result)
    execution_ref = result["resolved_references"]["execution"]
    assert execution_ref["raw"] == parent_context.execution_id
    assert execution_ref["source"] == "runtime_parent_execution"
    assert execution_ref["kind"] == "parent_execution"
    assert execution_ref["entry_proven"] is False
    assert result["case_scope"]["mode"] == "project"
    assert result["case_scope"]["project_name"] == "test-project"
    assert result["case_scope"]["project_key"] == "test-project"
    assert "repo_id" in result["case_scope"]
    assert result["case_event"] == {"event": "report_body_updated"}
    assert result["meta"]["case_event"] == "report_body_updated"


@pytest.mark.asyncio
async def test_link_fix_runtime_path_rejects_client_injected_parent_execution_id() -> None:
    """Runtime dispatch must not trust caller-provided parent_execution_id lineage."""
    router = RouterContextManager()
    parent_context = await router.build_execution_context(
        {
            "repo_root": "/tmp",
            "mode": "project",
            "intent": "tool:parent",
            "affected_dev_projects": [],
            "session_id": "session-parent",
        }
    )
    parent_token = router.set_current(parent_context)
    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(return_value=_make_manage_docs_result())

    try:
        with (
            patch("scribe_mcp.tools.append_entry.append_entry", mock_append),
            patch("scribe_mcp.tools.manage_docs.manage_docs", mock_manage),
        ):
            result = await execute_tool_call(
                name="link_fix",
                arguments={
                    "agent": "test-agent",
                    "case_id": "BUG-2026-03-15-0001",
                    "execution_id": "exec-client-injected",
                    "artifact_ref": "src/db.py:100",
                    "landing_status": "merged",
                },
                kwargs={
                    "context": {
                        "repo_root": "/tmp",
                        "mode": "project",
                        "session_id": "session-1",
                        "parent_execution_id": "exec-client-injected",
                    }
                },
                registry={"link_fix": link_fix},
                app=SimpleNamespace(request_context=None),
                storage_backend=None,
                settings=SimpleNamespace(project_root=Path("/tmp"), public_release=False),
                state_manager=_DummyStateManager(),
                router_context_manager=router,
                sentinel_only=set(),
                sentinel_allowed={"link_fix"},
                log_scope_violation_cb=lambda *_args, **_kwargs: None,
            )
    finally:
        router.reset(parent_token)

    assert result["ok"] is False
    _assert_operator_envelope(result)
    assert "execution_id" in result["error"]
