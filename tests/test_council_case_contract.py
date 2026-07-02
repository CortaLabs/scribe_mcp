from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scribe_mcp.storage.models import CaseRegistryRecord
from scribe_mcp.tools import tool_module_for_name

if "httpx" not in sys.modules:
    httpx_stub = types.SimpleNamespace(
        AsyncClient=object,
        ConnectError=Exception,
        TimeoutException=Exception,
    )
    sys.modules["httpx"] = httpx_stub

if "mcp" not in sys.modules:
    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    mcp_types_module = types.ModuleType("mcp.types")

    class _ServerStub:
        def __init__(self, _name: str) -> None:
            self.state = SimpleNamespace()

        def tool(self, _func=None, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

        def list_tools(self, *args, **kwargs):
            def _decorator(func):
                return func

            return _decorator

        def call_tool(self, *args, **kwargs):
            def _decorator(func):
                return func

            return _decorator

    mcp_server_module.Server = _ServerStub
    mcp_server_module.stdio = SimpleNamespace(stdio_server=lambda: None)
    mcp_module.server = mcp_server_module
    mcp_module.types = mcp_types_module
    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = mcp_server_module
    sys.modules["mcp.types"] = mcp_types_module

from scribe_mcp.tools import get_case_status as get_case_status_module


def _doc_binding(case_id: str) -> dict[str, object]:
    doc_path = f".scribe/docs/bugs/{case_id}/report.md"
    return {
        "canonical_doc_name": case_id,
        "canonical_doc_path": doc_path,
        "aliases": [
            {
                "alias": case_id,
                "alias_kind": "primary",
                "doc_path": doc_path,
            }
        ],
    }


def _record(
    *,
    case_id: str = "BUG-2026-06-25-0001",
    case_type: str = "bug",
    project_name: str = "scribe_bug_tools_hardening_062526",
    repo_root: str = "/tmp/repo",
    repo_id: str = "repo-1",
    status: str | None = "open",
    metadata: dict[str, object] | None = None,
) -> CaseRegistryRecord:
    return CaseRegistryRecord(
        case_id=case_id,
        case_type=case_type,
        project_name=project_name,
        repo_root=repo_root,
        repo_id=repo_id,
        project_key="pk_test",
        doc_type=case_type,
        doc_name=case_id,
        doc_path=f".scribe/docs/{case_type}/{case_id}/report.md",
        title=f"Case {case_id}",
        status=status,
        severity="high",
        source_tool="open_bug" if case_type == "bug" else "open_security",
        metadata=metadata or {},
    )


def _fake_server(*, backend: object, repo_root: str = "/tmp/repo", project_name: str = "scribe_bug_tools_hardening_062526") -> object:
    return SimpleNamespace(
        storage_backend=backend,
        get_execution_context=lambda: SimpleNamespace(
            mode="project",
            resolved_scope=SimpleNamespace(repo_root=repo_root, project_name=project_name),
        ),
        read_recent=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("progress logs must not be read")),
        query_entries=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("progress logs must not be queried")),
    )


def test_get_case_status_returns_open_registry_lifecycle_and_doc_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        case_id = "BUG-2026-06-25-0001"
        backend = SimpleNamespace(
            fetch_case_registry_record=AsyncMock(
                return_value=_record(case_id=case_id, metadata={"doc_binding": _doc_binding(case_id)})
            )
        )
        monkeypatch.setattr(get_case_status_module, "server_module", _fake_server(backend=backend))

        result = await get_case_status_module.get_case_status(case_id)

        assert result["ok"] is True
        assert result["case_id"] == case_id
        assert result["case_type"] == "bug"
        assert result["case_closed"] is False
        assert result["lifecycle_status"] == "open"
        assert result["registry_status"] == "open"
        assert result["doc_binding"]["canonical_doc_name"] == case_id
        assert result["last_fix_link"] is None
        assert result["closure_reason"] is None
        assert result["project_name"] == "scribe_bug_tools_hardening_062526"
        assert result["repo_id"] == "repo-1"
        assert "fix link" in result["next_step"].lower()
        backend.fetch_case_registry_record.assert_awaited_once_with(
            case_id=case_id,
            repo_root="/tmp/repo",
            project_name="scribe_bug_tools_hardening_062526",
        )

    asyncio.run(_run())


def test_get_case_status_returns_closed_registry_lifecycle_with_optional_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        case_id = "BUG-2026-06-25-0002"
        backend = SimpleNamespace(
            fetch_case_registry_record=AsyncMock(
                return_value=_record(
                    case_id=case_id,
                    project_name="override-project",
                    status="resolved",
                    metadata={
                        "doc_binding": _doc_binding(case_id),
                        "fix_link": {"artifact_ref": "src/module.py:10", "landing_status": "merged"},
                    },
                )
            )
        )
        monkeypatch.setattr(get_case_status_module, "server_module", _fake_server(backend=backend))

        result = await get_case_status_module.get_case_status(case_id, project="override-project", repo_id="repo-1")

        assert result["ok"] is True
        assert result["case_closed"] is True
        assert result["lifecycle_status"] == "resolved"
        assert result["registry_status"] == "resolved"
        assert result["closure_reason"] == "closed"
        assert result["last_fix_link"] == {"artifact_ref": "src/module.py:10", "landing_status": "merged"}
        assert result["next_step"] == "Case is terminal; no follow-up required."
        backend.fetch_case_registry_record.assert_awaited_once_with(
            case_id=case_id,
            repo_root="/tmp/repo",
            project_name="override-project",
        )

    asyncio.run(_run())


def test_get_case_status_returns_actionable_not_found_when_scope_has_no_case(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        backend = SimpleNamespace(fetch_case_registry_record=AsyncMock(return_value=None))
        monkeypatch.setattr(get_case_status_module, "server_module", _fake_server(backend=backend))

        result = await get_case_status_module.get_case_status("BUG-2026-06-25-9999", repo_id="repo-1")

        assert result["ok"] is False
        assert result["case_id"] == "BUG-2026-06-25-9999"
        assert result["case_closed"] is None
        assert result["doc_binding"] is None
        assert result["last_fix_link"] is None
        assert result["project_name"] == "scribe_bug_tools_hardening_062526"
        assert result["repo_id"] == "repo-1"
        assert "active repo/project scope" in result["next_step"]

    asyncio.run(_run())


def test_get_case_status_returns_actionable_backend_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.setattr(get_case_status_module, "server_module", _fake_server(backend=SimpleNamespace()))

        result = await get_case_status_module.get_case_status("BUG-2026-06-25-0001")

        assert result["ok"] is False
        assert result["case_id"] == "BUG-2026-06-25-0001"
        assert result["case_closed"] is None
        assert "backend is unavailable" in result["warnings"][0]
        assert "configure" in result["next_step"].lower()

    asyncio.run(_run())


def test_get_case_status_returns_actionable_missing_active_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        backend = SimpleNamespace(fetch_case_registry_record=AsyncMock())
        monkeypatch.setattr(get_case_status_module, "server_module", _fake_server(backend=backend, repo_root=""))

        result = await get_case_status_module.get_case_status("BUG-2026-06-25-0001")

        assert result["ok"] is False
        assert result["case_id"] == "BUG-2026-06-25-0001"
        assert result["case_closed"] is None
        assert "repo_root" in result["warnings"][0]
        assert "active repo/project scope" in result["next_step"]
        backend.fetch_case_registry_record.assert_not_awaited()

    asyncio.run(_run())


def test_get_case_status_returns_actionable_fetch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        backend = SimpleNamespace(fetch_case_registry_record=AsyncMock(side_effect=RuntimeError("db offline")))
        monkeypatch.setattr(get_case_status_module, "server_module", _fake_server(backend=backend))

        result = await get_case_status_module.get_case_status("BUG-2026-06-25-0001")

        assert result["ok"] is False
        assert result["case_id"] == "BUG-2026-06-25-0001"
        assert result["case_closed"] is None
        assert "failed to fetch shared case registry record" in result["warnings"][0]
        assert "db offline" in result["warnings"][0]
        assert "retry get_case_status" in result["next_step"]

    asyncio.run(_run())


def test_get_case_status_returns_actionable_repo_filter_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        case_id = "BUG-2026-06-25-0004"
        backend = SimpleNamespace(fetch_case_registry_record=AsyncMock(return_value=_record(case_id=case_id, repo_id="repo-1")))
        monkeypatch.setattr(get_case_status_module, "server_module", _fake_server(backend=backend))

        result = await get_case_status_module.get_case_status(case_id, repo_id="repo-2")

        assert result["ok"] is False
        assert result["case_id"] == case_id
        assert result["case_closed"] is None
        assert result["repo_id"] == "repo-2"
        assert "requested repo_id filter" in result["warnings"][0]
        assert "repo_id filter" in result["next_step"]
        backend.fetch_case_registry_record.assert_awaited_once_with(
            case_id=case_id,
            repo_root="/tmp/repo",
            project_name="scribe_bug_tools_hardening_062526",
        )

    asyncio.run(_run())


def test_get_case_status_does_not_infer_closure_from_progress_log_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        case_id = "BUG-2026-06-25-0003"
        backend = SimpleNamespace(
            fetch_case_registry_record=AsyncMock(
                return_value=_record(
                    case_id=case_id,
                    status="open",
                    metadata={
                        "doc_binding": _doc_binding(case_id),
                        "fix_link": {"artifact_ref": "src/module.py:10", "landing_status": "merged"},
                        "progress_log_status": "closed",
                    },
                )
            )
        )
        monkeypatch.setattr(get_case_status_module, "server_module", _fake_server(backend=backend))

        result = await get_case_status_module.get_case_status(case_id)

        assert result["ok"] is True
        assert result["case_closed"] is False
        assert result["lifecycle_status"] == "open"
        assert result["registry_status"] == "open"
        assert "terminal" in result["next_step"]

    asyncio.run(_run())


def test_get_case_status_registered_in_lazy_registry() -> None:
    assert tool_module_for_name("get_case_status") == "get_case_status"
