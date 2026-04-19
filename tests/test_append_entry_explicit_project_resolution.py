from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
import types
from typing import Any, Dict, Optional

import pytest

os.environ["SCRIBE_MODE"] = "standalone"
os.environ["SCRIBE_STORAGE_BACKEND"] = "sqlite"

if "httpx" not in sys.modules:
    sys.modules["httpx"] = types.SimpleNamespace(
        AsyncClient=object,
        ConnectError=Exception,
        TimeoutException=Exception,
    )

if "mcp" not in sys.modules:
    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    mcp_types_module = types.ModuleType("mcp.types")

    class _ServerStub:
        def __init__(self, _name: str) -> None:
            self.state = SimpleNamespace()

        def tool(self, _func=None, **_kwargs: Any):
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

if "scribe_mcp.server" not in sys.modules:
    server_stub = types.ModuleType("scribe_mcp.server")

    class _AppStub:
        def tool(self, _func=None, **_kwargs: Any):
            def _decorator(func):
                return func

            return _decorator

    class _ImportStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

    server_stub.app = _AppStub()
    server_stub.state_manager = _ImportStateManager()
    server_stub.get_execution_context = lambda: None
    server_stub.get_agent_identity = lambda: None
    sys.modules["scribe_mcp.server"] = server_stub

import scribe_mcp.tools.append_entry as append_entry_tool


class _DummyStateManager:
    async def record_tool(self, tool_name: str) -> Dict[str, Any]:
        return {"tool": tool_name}


def test_append_entry_passes_explicit_project_to_context_in_sentinel_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: Dict[str, Optional[str]] = {"explicit_project": None}

    monkeypatch.setattr(
        append_entry_tool,
        "server_module",
        SimpleNamespace(
            state_manager=_DummyStateManager(),
            get_execution_context=lambda: SimpleNamespace(mode="sentinel"),
            get_agent_identity=lambda: None,
        ),
    )

    async def fake_resolve_logging_context(*, explicit_project: Optional[str] = None, **_kwargs: Any) -> Any:
        captured["explicit_project"] = explicit_project
        return SimpleNamespace(
            project={
                "name": "target_project",
                "root": "/tmp/target_project",
                "progress_log": "/tmp/target_project/PROGRESS_LOG.md",
            },
            recent_projects=[],
            reminders=[],
        )

    async def fake_process_single_entry(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "path": "/tmp/target_project/PROGRESS_LOG.md",
            "project_name": "target_project",
            "reminders": [],
        }

    async def fake_finalize_tool_response(*, data: Dict[str, Any], **_kwargs: Any) -> Dict[str, Any]:
        return data

    monkeypatch.setattr(append_entry_tool, "resolve_logging_context", fake_resolve_logging_context)
    monkeypatch.setattr(append_entry_tool, "_process_single_entry", fake_process_single_entry)
    monkeypatch.setattr(append_entry_tool.default_formatter, "finalize_tool_response", fake_finalize_tool_response)

    result = asyncio.run(
        append_entry_tool.append_entry(
            agent="atlas",
            message="Cross-project note",
            status="warn",
            project="target_project",
            format="structured",
        )
    )

    assert captured["explicit_project"] == "target_project"
    assert result["ok"] is True
    assert result["warning"] == "explicit_project_logged_without_rebinding_session"
    assert any(
        "Run set_project before relying on project-scoped follow-up tools." in reminder.get("message", "")
        for reminder in result["reminders"]
    )


def test_append_entry_missing_explicit_project_in_sentinel_mode_does_not_fallback_to_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        append_entry_tool,
        "server_module",
        SimpleNamespace(
            state_manager=_DummyStateManager(),
            get_execution_context=lambda: SimpleNamespace(mode="sentinel"),
            get_agent_identity=lambda: None,
        ),
    )

    async def fake_resolve_logging_context(*, explicit_project: Optional[str] = None, **_kwargs: Any) -> Any:
        raise append_entry_tool.ProjectResolutionError(
            f"Explicit project '{explicit_project}' was not found. Invoke set_project or pass a valid project name.",
            ["known_project"],
        )

    def fail_if_sentinel_write(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("append_entry should not fall back to sentinel logging when explicit project is provided")

    monkeypatch.setattr(append_entry_tool, "resolve_logging_context", fake_resolve_logging_context)
    monkeypatch.setattr(append_entry_tool, "append_sentinel_event", fail_if_sentinel_write)

    result = asyncio.run(
        append_entry_tool.append_entry(
            agent="atlas",
            message="Should fail closed",
            status="warn",
            project="missing_project",
            format="structured",
        )
    )

    assert result["ok"] is False
    assert "missing_project" in result["error"]
    assert result.get("warning") != "project_resolution_failed_fallback_to_sentinel"
