from __future__ import annotations

import scribe_mcp.object_store as object_store_module
import pytest
from mcp.types import CallToolRequest

from scribe_mcp import server
from scribe_mcp.config.mode_detection import OperatingMode


class _Annotations:
    def __init__(self, *, read_only: bool, destructive: bool = False, open_world: bool = False) -> None:
        self.readOnlyHint = read_only
        self.destructiveHint = destructive
        self.openWorldHint = open_world


class _ToolDef:
    def __init__(self, *, trust_tier: int | None, annotations: _Annotations) -> None:
        self.meta = {"scribe": {"trustTier": trust_tier}} if trust_tier is not None else {}
        self.annotations = annotations


@pytest.mark.asyncio
async def test_mcp_call_tool_handler_returns_dispatch_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execute_tool_call(**kwargs: object) -> dict[str, object]:
        return {"ok": True, "tool": kwargs["name"]}

    monkeypatch.setattr(server.tools, "ensure_tool_loaded", lambda _name: None)
    monkeypatch.setattr(server, "execute_tool_call", fake_execute_tool_call)

    handler = server.app.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params={
                "name": "set_project",
                "arguments": {"agent": "test-agent", "name": "demo", "root": "/tmp/demo"},
            },
        )
    )

    assert result.root.structuredContent == {"ok": True, "tool": "set_project"}
    assert result.root.isError is False


@pytest.mark.asyncio
async def test_invoke_tool_skips_startup_for_local_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fail_startup() -> None:
        raise RuntimeError("startup should not run")

    async def fake_shutdown() -> None:
        calls.append("shutdown")

    async def fake_execute_tool_call(**_: object) -> dict[str, object]:
        calls.append("execute")
        return {"ok": True}

    monkeypatch.setattr(server, "_startup", fail_startup)
    monkeypatch.setattr(server, "_shutdown", fake_shutdown)
    monkeypatch.setattr(server.tools, "ensure_tool_loaded", lambda _name: None)
    monkeypatch.setattr(server, "execute_tool_call", fake_execute_tool_call)

    monkeypatch.setattr(
        server.Server,
        "_scribe_tool_defs",
        {"analyze_logs": _ToolDef(trust_tier=0, annotations=_Annotations(read_only=True))},
    )

    result = await server.invoke_tool("analyze_logs", {"agent": "test-agent", "path": "sample.md"}, context={})

    assert result == {"ok": True}
    assert calls == ["execute"]


@pytest.mark.asyncio
async def test_invoke_tool_runs_startup_for_storage_backed_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_profile: str | None = None

    async def fail_startup(*, startup_profile: str = "full_server") -> None:
        nonlocal captured_profile
        captured_profile = startup_profile
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(server, "_startup", fail_startup)
    monkeypatch.setattr(server.tools, "ensure_tool_loaded", lambda _name: None)
    monkeypatch.setattr(
        server.Server,
        "_scribe_tool_defs",
        {"manage_docs": _ToolDef(trust_tier=2, annotations=_Annotations(read_only=False))},
    )

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await server.invoke_tool("manage_docs", {"agent": "test-agent", "action": "project_health"}, context={})
    assert captured_profile == "storage_only"


@pytest.mark.asyncio
async def test_invoke_tool_storage_profile_reports_bridge_resolution_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_startup(*, startup_profile: str = "full_server") -> None:
        assert startup_profile == "storage_only"

    async def fake_shutdown() -> None:
        return None

    async def fake_execute_tool_call(**kwargs: object) -> dict[str, object]:
        resolver = kwargs.get("bridge_tool_resolver")
        if resolver is not None:
            raise AssertionError("bridge resolver should be disabled on storage_only path")
        raise ValueError("Unknown tool 'council_mcp:demo' (bridge resolution unavailable for this runtime path)")

    monkeypatch.setattr(server, "_startup", fake_startup)
    monkeypatch.setattr(server, "_shutdown", fake_shutdown)
    monkeypatch.setattr(server.tools, "ensure_tool_loaded", lambda _name: None)
    monkeypatch.setattr(server, "execute_tool_call", fake_execute_tool_call)
    monkeypatch.setattr(
        server.Server,
        "_scribe_tool_defs",
        {"council_mcp:demo": _ToolDef(trust_tier=2, annotations=_Annotations(read_only=False))},
    )

    with pytest.raises(ValueError, match="bridge resolution unavailable for this runtime path"):
        await server.invoke_tool("council_mcp:demo", {"agent": "test-agent"}, context={})


@pytest.mark.asyncio
async def test_startup_storage_only_sets_up_storage_and_document_store_without_deferred_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled: list[str] = []
    events: list[str] = []

    class _FakeStorage:
        async def setup(self) -> None:
            events.append("storage_setup")

    class _FakeDocStore:
        async def setup(self) -> None:
            events.append("document_store_setup")

    async def _fake_detect_mode(_settings: object) -> OperatingMode:
        return OperatingMode.STANDALONE

    monkeypatch.setattr(server, "_startup_complete", False)
    monkeypatch.setattr(server, "detect_operating_mode", _fake_detect_mode)
    fake_storage = _FakeStorage()
    monkeypatch.setattr(server, "storage_backend", fake_storage)
    monkeypatch.setattr(server, "_rebind_storage_backend_for_mode", lambda _mode: fake_storage)
    monkeypatch.setattr(server, "schedule_background_task", lambda *_a, service_name=None, **_k: scheduled.append(str(service_name)))
    monkeypatch.setattr(server, "_register_bridge_custom_tools", lambda: events.append("register_bridge_tools"))
    monkeypatch.setattr(server, "_session_cleanup_task", lambda *_a, **_k: "session_cleanup_task")
    monkeypatch.setattr(server, "_run_after_delay", lambda *_a, **_k: "delayed")
    monkeypatch.setattr(server, "_cleanup_old_entries_background", lambda: None)
    monkeypatch.setattr(server, "_init_plugins_background", lambda: None)
    monkeypatch.setattr(server, "_init_bridges_background", lambda: "bridge")
    monkeypatch.setattr(server, "_migrate_legacy_state_background", lambda: None)
    monkeypatch.setattr(server, "_replay_journals_background", lambda: "journal")
    monkeypatch.setattr(server, "init_agent_context_manager", lambda *_a, **_k: object())
    monkeypatch.setattr(server, "init_agent_identity", lambda *_a, **_k: object())
    monkeypatch.setattr(object_store_module, "create_document_store", lambda _settings: _FakeDocStore())

    await server._startup(startup_profile="storage_only")

    assert "storage_setup" in events
    assert "document_store_setup" in events
    assert scheduled == []


@pytest.mark.asyncio
async def test_startup_full_server_schedules_deferred_services(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduled: list[str] = []

    class _FakeStorage:
        async def setup(self) -> None:
            return None

    class _FakeDocStore:
        async def setup(self) -> None:
            return None

    async def _fake_detect_mode(_settings: object) -> OperatingMode:
        return OperatingMode.STANDALONE

    monkeypatch.setattr(server, "_startup_complete", False)
    monkeypatch.setattr(server, "detect_operating_mode", _fake_detect_mode)
    fake_storage = _FakeStorage()
    monkeypatch.setattr(server, "storage_backend", fake_storage)
    monkeypatch.setattr(server, "_rebind_storage_backend_for_mode", lambda _mode: fake_storage)
    monkeypatch.setattr(server, "schedule_background_task", lambda *_a, service_name=None, **_k: scheduled.append(str(service_name)))
    monkeypatch.setattr(server, "_register_bridge_custom_tools", lambda: None)
    monkeypatch.setattr(server, "_session_cleanup_task", lambda *_a, **_k: "session_cleanup_task")
    monkeypatch.setattr(server, "_run_after_delay", lambda *_a, **_k: "delayed")
    monkeypatch.setattr(server, "_cleanup_old_entries_background", lambda: None)
    monkeypatch.setattr(server, "_init_plugins_background", lambda: None)
    monkeypatch.setattr(server, "_init_bridges_background", lambda: "bridge")
    monkeypatch.setattr(server, "_migrate_legacy_state_background", lambda: None)
    monkeypatch.setattr(server, "_replay_journals_background", lambda: "journal")
    monkeypatch.setattr(server, "init_agent_context_manager", lambda *_a, **_k: object())
    monkeypatch.setattr(server, "init_agent_identity", lambda *_a, **_k: object())
    monkeypatch.setattr(object_store_module, "create_document_store", lambda _settings: _FakeDocStore())

    await server._startup(startup_profile="full_server")

    assert {
        "entry_cleanup",
        "plugin_init",
        "bridge_init",
        "legacy_state_migration",
        "session_cleanup",
        "journal_replay",
    }.issubset(set(scheduled))
