from __future__ import annotations

import sys
import types
import asyncio
from datetime import datetime, timezone
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

from scribe_mcp.tools import list_open_cases as list_open_cases_module


def _record(
    *,
    case_id: str,
    case_type: str = "bug",
    project_name: str = "integrate_bug_management_system_20260417",
    repo_root: str = "/tmp/repo",
    repo_id: str = "repo-1",
    category: str | None = None,
    severity: str | None = None,
    status: str | None = "open",
    updated_seconds: int = 0,
) -> CaseRegistryRecord:
    metadata = {"category": category} if category else None
    now = datetime(2026, 4, 17, 12, 0, updated_seconds, tzinfo=timezone.utc)
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
        severity=severity,
        source_tool="open_bug" if case_type == "bug" else "open_security",
        metadata=metadata,
        created_at=now,
        updated_at=now,
    )


def test_list_open_cases_filters_open_status_and_requested_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        backend = SimpleNamespace(
            query_case_registry_records=AsyncMock(
                return_value=[
                    _record(case_id="BUG-1", category="api", severity="high", status="open", updated_seconds=10),
                    _record(case_id="BUG-2", category="api", severity="high", status="resolved", updated_seconds=20),
                    _record(case_id="BUG-3", category="ui", severity="high", status="investigating", updated_seconds=30),
                    _record(case_id="BUG-4", category="api", severity="medium", status="open", updated_seconds=40),
                    _record(case_id="BUG-5", category="api", severity="high", status="open", repo_id="repo-2", updated_seconds=50),
                ]
            )
        )
        fake_server = SimpleNamespace(
            storage_backend=backend,
            get_execution_context=lambda: SimpleNamespace(
                mode="project",
                resolved_scope=SimpleNamespace(repo_root="/tmp/repo", project_name="integrate_bug_management_system_20260417")
            ),
        )
        monkeypatch.setattr(list_open_cases_module, "server_module", fake_server)

        result = await list_open_cases_module.list_open_cases(
            case_type="bug",
            category="api",
            severity="high",
            repo_id="repo-1",
            limit=10,
        )

        assert result["ok"] is True
        assert result["mode"] == "project"
        assert result["case_id"] == ""
        assert result["artifacts"] == []
        assert result["warnings"] == []
        assert isinstance(result["next_step"], str)
        assert [case["case_id"] for case in result["cases"]] == ["BUG-1"]
        assert result["filters"]["open_only"] is True
        backend.query_case_registry_records.assert_awaited_once()

    asyncio.run(_run())


def test_list_open_cases_uses_active_project_default(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        backend = SimpleNamespace(
            query_case_registry_records=AsyncMock(return_value=[_record(case_id="SEC-1", case_type="security")])
        )
        fake_server = SimpleNamespace(
            storage_backend=backend,
            get_execution_context=lambda: SimpleNamespace(
                mode="project",
                resolved_scope=SimpleNamespace(repo_root="/tmp/repo", project_name="integrate_bug_management_system_20260417")
            ),
        )
        monkeypatch.setattr(list_open_cases_module, "server_module", fake_server)

        result = await list_open_cases_module.list_open_cases(case_type="security", limit=5)

        assert result["ok"] is True
        assert result["count"] == 1
        backend.query_case_registry_records.assert_awaited_once_with(
            repo_root="/tmp/repo",
            project_name="integrate_bug_management_system_20260417",
            case_type="security",
            limit=20,
            offset=0,
        )

    asyncio.run(_run())


def test_list_open_cases_isolates_same_project_name_by_active_repo_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        records = [
            _record(case_id="BUG-1", project_name="shared_name", repo_root="/tmp/repo-a", repo_id="repo-a"),
            _record(case_id="BUG-2", project_name="shared_name", repo_root="/tmp/repo-b", repo_id="repo-b"),
        ]

        async def _query_case_registry_records(**kwargs: object):
            repo_root = kwargs.get("repo_root")
            project_name = kwargs.get("project_name")
            return [
                record
                for record in records
                if getattr(record, "repo_root", None) == repo_root
                and getattr(record, "project_name", None) == project_name
            ]

        backend = SimpleNamespace(
            query_case_registry_records=AsyncMock(side_effect=_query_case_registry_records)
        )
        fake_server = SimpleNamespace(
            storage_backend=backend,
            get_execution_context=lambda: SimpleNamespace(
                mode="project",
                resolved_scope=SimpleNamespace(repo_root="/tmp/repo-a", project_name="shared_name"),
            ),
        )
        monkeypatch.setattr(list_open_cases_module, "server_module", fake_server)

        result = await list_open_cases_module.list_open_cases(limit=10)

        assert result["ok"] is True
        assert [case["case_id"] for case in result["cases"]] == ["BUG-1"]
        backend.query_case_registry_records.assert_awaited_once_with(
            repo_root="/tmp/repo-a",
            project_name="shared_name",
            case_type=None,
            limit=40,
            offset=0,
        )
        assert result["filters"]["project"] == "shared_name"

    asyncio.run(_run())


def test_list_open_cases_returns_normalized_failure_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        backend = SimpleNamespace(query_case_registry_records=AsyncMock(side_effect=RuntimeError("db down")))
        fake_server = SimpleNamespace(
            storage_backend=backend,
            get_execution_context=lambda: SimpleNamespace(
                mode="project",
                resolved_scope=SimpleNamespace(repo_root="/tmp/repo", project_name="integrate_bug_management_system_20260417"),
            ),
        )
        monkeypatch.setattr(list_open_cases_module, "server_module", fake_server)

        result = await list_open_cases_module.list_open_cases(case_type="bug", limit=10)

        assert result["ok"] is False
        assert result["mode"] == "project"
        assert result["case_id"] == ""
        assert result["artifacts"] == []
        assert result["count"] == 0
        assert result["cases"] == []
        assert isinstance(result["warnings"], list) and result["warnings"]
        assert isinstance(result["next_step"], str) and result["next_step"]
        assert result["filters"]["case_type"] == "bug"

    asyncio.run(_run())


def test_list_open_cases_registered_in_lazy_registry() -> None:
    assert tool_module_for_name("list_open_cases") == "list_open_cases"
