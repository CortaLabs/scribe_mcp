import argparse
import asyncio
from typing import Any

import pytest

from scribe_mcp.cli import main as cli_main


@pytest.mark.asyncio
async def test_call_prefers_bound_server_when_endpoint_configured(monkeypatch):
    class Server:
        storage_backend = None

        @staticmethod
        def resolve_tool_startup_profile(_name):
            return "storage_only"

        @staticmethod
        async def invoke_tool(_tool, _args, context=None):
            raise AssertionError("local invoke_tool should not run on healthy bound_server path")

    monkeypatch.setenv("SCRIBE_REMOTE_URL", "http://127.0.0.1:8200")
    monkeypatch.setattr("scribe_mcp.server", Server, raising=False)
    bound_calls = {"count": 0}

    async def fake_bound_call(**kwargs):
        bound_calls["count"] += 1
        assert kwargs["tool"] == "manage_docs"
        assert kwargs["endpoint"] == "http://127.0.0.1:8200"
        assert kwargs["context"]["dispatch_path"] == "bound_server"
        assert kwargs["context"].get("remote_server_url") == "http://127.0.0.1:8200"
        return {"ok": True}

    monkeypatch.setattr(cli_main, "_invoke_tool_bound_server", fake_bound_call)

    args = argparse.Namespace(
        repo_root=cli_main.Path.cwd(),
        session="default",
        agent="test-agent",
        args_json=None,
        arg=[],
        context_json=None,
        session_mode="auto",
        no_save_session=True,
        pretty=False,
        tool="manage_docs",
        tool_timeout_seconds=0.1,
    )
    rc = await cli_main._run_call_command(args, {})
    assert rc == 0
    assert bound_calls["count"] == 1


@pytest.mark.asyncio
async def test_call_bound_server_timeout_falls_back_to_local(monkeypatch, capsys):
    class Server:
        storage_backend = None
        local_attempts = 0

        @staticmethod
        def resolve_tool_startup_profile(_name):
            return "storage_only"

        @staticmethod
        async def invoke_tool(_tool, _args, context=None):
            Server.local_attempts += 1
            assert context.get("dispatch_path") == "local_one_shot"
            return {"ok": True, "path": context.get("dispatch_path")}

    monkeypatch.setenv("SCRIBE_REMOTE_URL", "http://127.0.0.1:8200")
    monkeypatch.setattr("scribe_mcp.server", Server, raising=False)
    bound_calls = {"count": 0}

    async def fake_bound_call(**_kwargs):
        bound_calls["count"] += 1
        raise asyncio.TimeoutError()

    monkeypatch.setattr(cli_main, "_invoke_tool_bound_server", fake_bound_call)

    args = argparse.Namespace(
        repo_root=cli_main.Path.cwd(),
        session="default",
        agent="test-agent",
        args_json=None,
        arg=[],
        context_json=None,
        session_mode="auto",
        no_save_session=True,
        pretty=False,
        tool="manage_docs",
        tool_timeout_seconds=0.01,
    )
    rc = await cli_main._run_call_command(args, {})
    assert rc == 0
    assert bound_calls["count"] == 1
    assert Server.local_attempts == 1
    assert "falling back to local_one_shot" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_call_skip_startup_tool_stays_local_one_shot(monkeypatch):
    class Server:
        storage_backend = None

        @staticmethod
        def resolve_tool_startup_profile(_name):
            return "local_only"

        @staticmethod
        async def invoke_tool(_tool, _args, context=None):
            return {"ok": True, "dispatch_path": context.get("dispatch_path")}

    monkeypatch.setenv("SCRIBE_REMOTE_URL", "http://127.0.0.1:8200")
    monkeypatch.setattr("scribe_mcp.server", Server, raising=False)

    args = argparse.Namespace(
        repo_root=cli_main.Path.cwd(),
        session="default",
        agent="test-agent",
        args_json=None,
        arg=[],
        context_json=None,
        session_mode="auto",
        no_save_session=True,
        pretty=False,
        tool="analyze_logs",
        tool_timeout_seconds=0.1,
    )
    rc = await cli_main._run_call_command(args, {})
    assert rc == 0


@pytest.mark.asyncio
async def test_bound_server_helper_uses_supported_route_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"result": {"ok": True}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setenv("SCRIBE_REMOTE_AUTH_TOKEN", "token-123")
    monkeypatch.setattr(cli_main.httpx, "AsyncClient", FakeAsyncClient)
    result = await cli_main._invoke_tool_bound_server(
        endpoint="http://127.0.0.1:8200",
        tool="manage_docs",
        call_args={"agent": "test-agent", "action": "project_health"},
        context={"mode": "project"},
        timeout_seconds=1.0,
    )
    assert result == {"ok": True}
    assert captured["url"] == "http://127.0.0.1:8200/api/v1/tools/invoke"
    assert captured["json"] == {
        "tool_name": "manage_docs",
        "arguments": {"agent": "test-agent", "action": "project_health"},
        "context": {"mode": "project"},
    }
