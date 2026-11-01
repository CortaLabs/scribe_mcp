"""Hermetic contract tests for the source-owned MCP compatibility adapter."""

from __future__ import annotations

import importlib.metadata
import asyncio
import copy
import json
import os
import sys
import textwrap
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from scribe_mcp.mcp_adapter import (
    MCPCompatibilityPolicy,
    MCPRuntime,
    ProtocolEra,
    build_mcp_server,
    classify_protocol_era,
    configure_mcp_server,
    load_mcp_runtime,
    normalize_tool_definition,
    normalize_tool_result,
)


_CHILD_TERMINATE_TIMEOUT = 0.5
_CHILD_KILL_TIMEOUT = 1.0


async def _terminate_and_reap(process):
    if process.stdin is not None and not process.stdin.is_closing():
        process.stdin.close()
        try:
            await asyncio.wait_for(process.stdin.wait_closed(), timeout=_CHILD_TERMINATE_TIMEOUT)
        except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError):
            pass

    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=_CHILD_TERMINATE_TIMEOUT)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await asyncio.wait_for(process.wait(), timeout=_CHILD_KILL_TIMEOUT)
    else:
        await process.wait()


@asynccontextmanager
async def _managed_child_process(*args, **kwargs):
    process = await asyncio.create_subprocess_exec(*args, **kwargs)
    try:
        yield process
    except BaseException as failure:
        cleanup = asyncio.create_task(_terminate_and_reap(process))
        try:
            await asyncio.shield(cleanup)
        except BaseException as cleanup_error:
            if not cleanup.done():
                try:
                    await cleanup
                except BaseException as final_cleanup_error:
                    cleanup_error = final_cleanup_error
            if hasattr(failure, "add_note"):
                failure.add_note(f"child cleanup also failed: {cleanup_error!r}")
        raise
    else:
        await _terminate_and_reap(process)


@pytest.mark.startup
@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "cancellation"])
async def test_managed_child_process_is_reaped_on_timeout_and_cancellation(failure):
    ready = asyncio.Event()
    spawned = []

    async def wait_for_child():
        async with _managed_child_process(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        ) as process:
            spawned.append(process)
            ready.set()
            if failure == "timeout":
                await asyncio.wait_for(process.wait(), timeout=0.01)
            else:
                await process.wait()

    task = asyncio.create_task(wait_for_child())
    await asyncio.wait_for(ready.wait(), timeout=5)
    if failure == "timeout":
        with pytest.raises(asyncio.TimeoutError):
            await task
    else:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    process = spawned[0]
    assert process.returncode is not None
    assert await asyncio.wait_for(process.wait(), timeout=_CHILD_KILL_TIMEOUT) == process.returncode


def test_load_mcp_runtime_selects_public_sdk_v2_surfaces():
    runtime = load_mcp_runtime()

    assert runtime.major == 2
    assert runtime.version == "2.3.0"
    assert runtime.server_type.__name__ == "MCPServer"
    assert runtime.types.Tool.__module__.startswith("mcp_types")
    assert callable(runtime.stdio.stdio_server)


@pytest.mark.parametrize("version", ["", "latest", "2x", " 2.0.0", "2.03.0", "2.3.00"])
def test_load_mcp_runtime_rejects_malformed_versions(monkeypatch, version):
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: version)

    with pytest.raises(RuntimeError, match="malformed mcp distribution version"):
        load_mcp_runtime()


@pytest.mark.parametrize(
    "version", ["1.26.0", "3.0.0"]
)
def test_load_mcp_runtime_rejects_unsupported_majors(monkeypatch, version):
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: version)
    monkeypatch.setattr(importlib, "import_module", lambda _name: pytest.fail("SDK import attempted"))

    with pytest.raises(RuntimeError, match="unsupported mcp distribution major"):
        load_mcp_runtime()


@pytest.mark.parametrize("version", ["2.3.0rc1", "2.3.0.dev1", "2.3.0+local"])
def test_load_mcp_runtime_rejects_nonstable_releases(monkeypatch, version):
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: version)
    monkeypatch.setattr(importlib, "import_module", lambda _name: pytest.fail("SDK import attempted"))

    with pytest.raises(RuntimeError, match="unsupported mcp distribution release"):
        load_mcp_runtime()


def test_load_mcp_runtime_rejects_missing_distribution(monkeypatch):
    def missing(_name):
        raise importlib.metadata.PackageNotFoundError("mcp")

    monkeypatch.setattr(importlib.metadata, "version", missing)

    with pytest.raises(RuntimeError, match="mcp distribution is not installed"):
        load_mcp_runtime()


def test_load_mcp_runtime_does_not_swallow_transitive_import_failures(monkeypatch):
    original_import = importlib.import_module

    def broken_import(name):
        if name == "mcp.server.mcpserver":
            error = ImportError("missing transitive dependency")
            error.name = "unrelated_dependency"
            raise error
        return original_import(name)

    monkeypatch.setattr(importlib, "import_module", broken_import)

    with pytest.raises(RuntimeError, match="required public MCP SDK v2 surface") as exc_info:
        load_mcp_runtime()

    assert isinstance(exc_info.value.__cause__, ImportError)
    assert exc_info.value.__cause__.name == "unrelated_dependency"


@pytest.mark.startup
def test_load_mcp_runtime_rejects_missing_current_protocol_api(monkeypatch):
    original_import = importlib.import_module

    def missing_context_surface(name):
        if name == "mcp.server.context":
            return SimpleNamespace()
        return original_import(name)

    monkeypatch.setattr(importlib, "import_module", missing_context_surface)

    with pytest.raises(RuntimeError, match="required public MCP SDK v2 surface") as exc_info:
        load_mcp_runtime()

    assert isinstance(exc_info.value.__cause__, AttributeError)


def test_protocol_era_classification_is_current_only_and_closed():
    assert MCPCompatibilityPolicy().legacy_revisions == ("2025-11-25",)
    assert MCPCompatibilityPolicy().legacy_enabled is False
    assert MCPCompatibilityPolicy().default_revision == "2026-07-28"
    assert MCPCompatibilityPolicy().modern_transports == ("stdio", "streamable-http")
    assert MCPCompatibilityPolicy().legacy_transports == ("stdio", "http-sse")
    assert MCPCompatibilityPolicy(legacy_enabled=True).legacy_enabled is False
    with pytest.raises(ValueError, match="default_revision is fixed"):
        MCPCompatibilityPolicy(default_revision="2025-11-25")
    with pytest.raises(ValueError, match="modern_transports are fixed"):
        MCPCompatibilityPolicy(modern_transports=("stdio",))
    with pytest.raises(ValueError, match="legacy_revisions are fixed"):
        MCPCompatibilityPolicy(legacy_revisions=("2025-06-18",))
    with pytest.raises(ValueError, match="legacy_transports are fixed"):
        MCPCompatibilityPolicy(legacy_transports=("http-sse",))
    with pytest.raises(TypeError, match="legacy_enabled must be boolean"):
        MCPCompatibilityPolicy(legacy_enabled=1)
    assert classify_protocol_era(
        protocol_revision=None,
        transport="stdio",
        explicit_legacy=False,
    ) is ProtocolEra.MODERN
    assert classify_protocol_era(
        protocol_revision="2026-07-28",
        transport="streamable-http",
        explicit_legacy=False,
    ) is ProtocolEra.MODERN
    with pytest.raises(ValueError, match="unsupported MCP protocol revision"):
        classify_protocol_era(
            protocol_revision="2025-11-25",
            transport="stdio",
            explicit_legacy=False,
        )
    with pytest.raises(ValueError, match="unsupported MCP protocol revision"):
        classify_protocol_era(
            protocol_revision="2025-11-25",
            transport="http-sse",
            explicit_legacy=True,
        )
    with pytest.raises(ValueError, match="unsupported MCP protocol revision"):
        classify_protocol_era(
            protocol_revision="2025-06-18",
            transport="stdio",
            explicit_legacy=True,
        )
    with pytest.raises(ValueError, match="unsupported MCP protocol revision"):
        classify_protocol_era(
            protocol_revision="2024-11-05",
            transport="stdio",
            explicit_legacy=True,
        )
    with pytest.raises(ValueError, match="unsupported MCP transport"):
        classify_protocol_era(
            protocol_revision="2026-07-28",
            transport="sse",
            explicit_legacy=False,
        )
    with pytest.raises(ValueError, match="protocol_revision must be"):
        classify_protocol_era(
            protocol_revision=" 2026-07-28",
            transport="stdio",
            explicit_legacy=False,
        )
    with pytest.raises(ValueError, match="unsupported MCP transport"):
        classify_protocol_era(
            protocol_revision="2026-07-28",
            transport=" stdio",
            explicit_legacy=False,
        )
    with pytest.raises(TypeError, match="explicit_legacy must be boolean"):
        classify_protocol_era(
            protocol_revision="2026-07-28",
            transport="stdio",
            explicit_legacy=1,
        )


def test_tool_definition_preserves_schema_metadata_and_hints():
    runtime = load_mcp_runtime()
    tool = normalize_tool_definition(
        runtime=runtime,
        era=ProtocolEra.MODERN,
        name="sample",
        title="Sample",
        description="Sample tool",
        input_schema={
            "type": "object",
            "properties": {"agent": {"type": "string"}},
            "required": ["agent"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        annotations={"readOnlyHint": True},
        execution={"taskSupport": "forbidden"},
        meta={"scribe": {"trustTier": 0}},
        tags=["read-only", "context"],
    )

    payload = tool.model_dump(by_alias=True, exclude_none=True)
    assert payload["name"] == "sample"
    assert payload["inputSchema"]["required"] == ["agent"]
    assert payload["outputSchema"] == {"type": "object"}
    assert payload["annotations"]["readOnlyHint"] is True
    assert payload["execution"]["taskSupport"] == "forbidden"
    assert payload["_meta"]["scribe"]["trustTier"] == 0
    assert payload["_meta"]["scribe"]["tags"] == ["read-only", "context"]


def test_tool_definition_rejects_malformed_schema():
    runtime = load_mcp_runtime()

    with pytest.raises(ValueError, match="required property"):
        normalize_tool_definition(
            runtime=runtime,
            era=ProtocolEra.MODERN,
            name="bad",
            description="bad",
            input_schema={"type": "object", "properties": {}, "required": ["agent"]},
        )


def test_result_normalization_preserves_structured_text_and_error_semantics():
    runtime = load_mcp_runtime()
    success = normalize_tool_result(
        {"ok": True, "count": 2}, runtime=runtime, era=ProtocolEra.MODERN
    )
    error = normalize_tool_result(
        {
            "content": [{"type": "text", "text": "denied"}],
            "structuredContent": {"ok": False, "reason": "denied"},
            "isError": True,
        },
        runtime=runtime,
        era=ProtocolEra.MODERN,
    )

    assert success.structured_content == {"ok": True, "count": 2}
    assert success.content[0].text == '{"count":2,"ok":true}'
    assert success.is_error is False
    assert error.structured_content == {"ok": False, "reason": "denied"}
    assert error.content[0].text == "denied"
    assert error.is_error is True


def test_build_mcp_server_uses_the_public_sdk_v2_surface():
    from scribe_mcp import __version__

    server = build_mcp_server("scribe-test", MCPCompatibilityPolicy())

    assert type(server).__name__ == "MCPServer"
    assert server.version == __version__
    assert callable(server.list_tools)
    assert callable(server.call_tool)
    assert callable(server.run_stdio_async)
    assert getattr(server.middleware[-1], "__name__", None) == "modern_only"


@pytest.mark.startup
@pytest.mark.asyncio
async def test_modern_stdio_discover_list_and_call_use_real_sdk_pipe(tmp_path):
    """Exercise the current protocol through the SDK's explicit discover flow."""
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    marker = tmp_path / "effects.jsonl"
    child = textwrap.dedent(
        """
        import asyncio, json, os
        from pathlib import Path
        from scribe_mcp.mcp_adapter import (
            MCPCompatibilityPolicy, ProtocolEra, build_mcp_server,
            configure_mcp_server, load_mcp_runtime, normalize_tool_definition,
        )
        runtime = load_mcp_runtime()
        server = build_mcp_server("modern-wire-test", MCPCompatibilityPolicy())
        tool = normalize_tool_definition(
            runtime=runtime, era=ProtocolEra.MODERN, name="echo",
            description="Pipe test", input_schema={"type":"object",
            "properties":{"value":{"type":"string"}},"required":["value"],
            "additionalProperties":False})
        def record(event):
            with Path(os.environ["SCRIBE_TEST_EFFECTS"]).open("a") as stream:
                stream.write(json.dumps(event) + "\\n")
        async def listed(era):
            record({"event":"list", "era":era.value})
            return [tool]
        async def called(name, arguments, context, era):
            record({"event":"call", "name":name})
            return {"ok":True, "value":arguments["value"]}
        configure_mcp_server(server, runtime=runtime,
            definition_provider=lambda:{"echo":tool}, list_handler=listed, call_handler=called)
        asyncio.run(server.run_stdio_async())
        """
    )
    child_env = dict(os.environ)
    child_env.update(
        {
            "SCRIBE_MODE": "standalone",
            "SCRIBE_STORAGE_BACKEND": "sqlite",
            "SCRIBE_DISABLE_DOTENV": "1",
            "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{os.getcwd()}/src:{os.getcwd()}/tests",
            "SCRIBE_TEST_EFFECTS": str(marker),
        }
    )
    server_params = StdioServerParameters(
        command=sys.executable, args=["-c", child], env=child_env, cwd=os.getcwd()
    )
    async with asyncio.timeout(15):
        async with Client(server_params, mode="2026-07-28", cache=None) as client:
            await client.session.send_discover("2026-07-28")
            listed = await client.list_tools()
            assert [item.name for item in listed.tools] == ["echo"]
            result = await client.call_tool("echo", {"value": "current"})
            assert result.structured_content == {"ok": True, "value": "current"}
    events = [json.loads(line) for line in marker.read_text().splitlines()]
    assert events == [
        {"event": "list", "era": "modern"},
        {"event": "call", "name": "echo"},
    ]


@pytest.mark.startup
@pytest.mark.asyncio
async def test_scribe_module_catalog_uses_current_sdk_discover(tmp_path):
    """Launch the actual package entrypoint and discover its nonbinding catalog."""
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    isolated_root = tmp_path / "root"
    isolated_root.mkdir()
    child_env = dict(os.environ)
    child_env.update(
        {
            "SCRIBE_MODE": "standalone",
            "SCRIBE_STORAGE_BACKEND": "sqlite",
            "SCRIBE_DB_PATH": str(tmp_path / "scribe.sqlite"),
            "SCRIBE_STATE_PATH": str(tmp_path / "state.json"),
            "SCRIBE_ROOT": str(isolated_root),
            "SCRIBE_PROJECT_ROOT": str(isolated_root),
            "SCRIBE_DISABLE_DOTENV": "1",
            "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{os.getcwd()}/src:{os.getcwd()}/tests",
        }
    )
    server_params = StdioServerParameters(
        command=sys.executable, args=["-m", "scribe_mcp"], env=child_env, cwd=os.getcwd()
    )

    async with asyncio.timeout(30):
        async with Client(server_params, mode="2026-07-28", cache=None) as client:
            await client.session.send_discover("2026-07-28")
            catalog = await client.list_tools()

    names = {tool.name for tool in catalog.tools}
    assert "list_projects" in names
    assert "append_entry" in names
    assert len(names) > 10


@pytest.mark.startup
@pytest.mark.asyncio
async def test_real_scribe_rejections_preserve_storage_session_defaults_and_files(tmp_path):
    """Observe actual Scribe state around SDK middleware without replacing it."""
    isolated_root = tmp_path / "scribe-root"
    isolated_root.mkdir()
    snapshot_path = tmp_path / "state-snapshots.jsonl"
    child = textwrap.dedent(
        """
        import asyncio, hashlib, json, os
        from pathlib import Path
        from mcp.server.mcpserver import MCPServer
        from scribe_mcp import server as scribe

        handler_counts = {"list": 0, "call": 0}

        def digest(path):
            candidate = Path(path)
            return hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.is_file() else None

        async def snapshot():
            root = Path(os.environ["SCRIBE_ROOT"])
            manager = scribe.state_manager
            context = scribe.agent_context_manager
            state = await manager.load()
            files = {
                str(path.relative_to(root)): {
                    "size": path.stat().st_size,
                    "sha256": digest(path),
                }
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }
            caches = {
                "agent_state": manager._agent_state_cache,
                "session_projects": manager._session_projects_cache,
                "session_modes": manager._session_modes_cache,
                "recent_projects": manager._recent_projects_cache,
                "activity": manager._activity_cache,
                "projects": manager._projects_cache,
            }
            leases = sorted(
                (agent, session, expires.isoformat())
                for agent, (session, expires) in context._session_leases.items()
            ) if context is not None else []
            encoded = lambda value: json.loads(json.dumps(value, sort_keys=True, default=str))
            return {
                "sqlite_sha256": digest(scribe.settings.sqlite_path),
                "default_state_sha256": digest(scribe.settings.default_state_path),
                "files": files,
                "state_caches": encoded(caches),
                "resolved_state": encoded({
                    "current_project": state.current_project,
                    "projects": state.projects,
                    "recent_projects": state.recent_projects,
                    "session_projects": state.session_projects,
                    "session_modes": state.session_modes,
                    "agent_state": state.agent_state,
                }),
                "session_leases": leases,
                "startup_complete": scribe._startup_complete,
                "registered_tools": sorted(scribe._SCRIBE_TOOL_REGISTRY),
                "registered_definitions": sorted(scribe._SCRIBE_TOOL_DEFS),
                "handler_counts": dict(handler_counts),
            }

        original_run = MCPServer.run_stdio_async

        async def measured_run(self, *args, **kwargs):
            if self is not scribe.app:
                return await original_run(self, *args, **kwargs)
            records = Path(os.environ["SCRIBE_TEST_SNAPSHOTS"])
            original_list = self.list_tools
            original_call = self.call_tool

            async def counted_list(*args, **kwargs):
                handler_counts["list"] += 1
                return await original_list(*args, **kwargs)

            async def counted_call(*args, **kwargs):
                handler_counts["call"] += 1
                return await original_call(*args, **kwargs)

            self.list_tools = counted_list
            self.call_tool = counted_call
            middleware = self.middleware
            original_middleware = middleware[-1]

            async def observed(ctx, call_next):
                before = await snapshot()
                forwarded = 0

                async def counted(ctx):
                    nonlocal forwarded
                    forwarded += 1
                    return await call_next(ctx)

                try:
                    return await original_middleware(ctx, counted)
                finally:
                    event = {
                        "method": ctx.method,
                        "request_id": ctx.request_id,
                        "protocol_version": ctx.protocol_version,
                        "call_next_count": forwarded,
                        "before": before,
                        "after": await snapshot(),
                    }
                    with records.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(event, sort_keys=True, default=str) + "\\n")

            middleware[-1] = observed
            before_run = await snapshot()
            try:
                return await original_run(self, *args, **kwargs)
            finally:
                event = {"kind": "server", "before": before_run, "after": await snapshot()}
                with records.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, sort_keys=True, default=str) + "\\n")

        MCPServer.run_stdio_async = measured_run
        asyncio.run(scribe.main())
        """
    )
    child_env = dict(os.environ)
    child_env.update(
        {
            "SCRIBE_MODE": "standalone",
            "SCRIBE_STORAGE_BACKEND": "sqlite",
            "SCRIBE_DB_PATH": str(isolated_root / "scribe.sqlite"),
            "SCRIBE_STATE_PATH": str(isolated_root / "state.json"),
            "SCRIBE_ROOT": str(isolated_root),
            "SCRIBE_PROJECT_ROOT": str(isolated_root),
            "SCRIBE_DISABLE_DOTENV": "1",
            "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{os.getcwd()}/src:{os.getcwd()}/tests",
            "SCRIBE_TEST_SNAPSHOTS": str(snapshot_path),
        }
    )

    def request(request_id, method, *, version="2026-07-28", params=None):
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        if version is not ...:
            payload["params"]["_meta"] = {
                "io.modelcontextprotocol/protocolVersion": version,
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        return json.dumps(payload, separators=(",", ":"))

    wire = [
        (json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "server/discover",
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        "io.modelcontextprotocol/clientInfo": {"name": "state-probe", "version": "1"},
                        "io.modelcontextprotocol/clientCapabilities": {},
                    }
                },
            }
        ), True),
        (request(9, "tools/list"), True),
        (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}), False),
        (json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2025-11-25"}}}), False),
        (json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"_meta": "invalid"}}), False),
        (request(12, "tools/list"), True),
        (request(1, "tools/list", version="2025-11-25"), True),
        ('{"jsonrpc":"2.0","id":13,"method":"tools/list","params":', False),
    ]
    async with _managed_child_process(
        sys.executable,
        "-c",
        child,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_env,
        cwd=os.getcwd(),
    ) as process:
        responses = []
        for message, expects_response in wire:
            process.stdin.write((message + "\n").encode())
            await process.stdin.drain()
            if expects_response:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
                assert line, "the real Scribe child closed before replying to a request"
                responses.append(json.loads(line))
        process.stdin.close()
        await asyncio.wait_for(process.wait(), timeout=10)
        stderr = await process.stderr.read()
        assert process.returncode == 0, stderr.decode()
    response_by_id = {item.get("id"): item for item in responses}
    assert response_by_id[0]["result"]
    assert response_by_id[1]["error"]["code"] == -32022
    assert response_by_id[9]["result"]["tools"]
    assert response_by_id[12]["result"]["tools"]

    events = [json.loads(line) for line in snapshot_path.read_text().splitlines()]
    middleware_events = [event for event in events if "call_next_count" in event]
    server_event = next(event for event in events if event.get("kind") == "server")
    assert server_event["before"]["startup_complete"] is True
    assert server_event["before"]["sqlite_sha256"] is not None
    assert server_event["before"]["files"]
    discover = [event for event in middleware_events if event["request_id"] == 0]
    assert len(discover) == 1
    assert discover[0]["call_next_count"] == 1
    barriers = [event for event in middleware_events if event["request_id"] in {9, 12}]
    assert {event["request_id"] for event in barriers} == {9, 12}
    assert all(event["call_next_count"] == 1 for event in barriers)
    assert barriers[-1]["after"] == server_event["after"]
    notifications = [event for event in middleware_events if event["method"].startswith("notifications/")]
    assert {event["method"] for event in notifications} == {
        "notifications/initialized",
        "notifications/cancelled",
    }
    assert all(event["call_next_count"] == 0 for event in notifications)
    assert all(event["before"] == event["after"] for event in notifications)


@pytest.mark.startup
@pytest.mark.asyncio
async def test_rejected_wire_requests_and_notifications_have_no_application_effects(tmp_path, monkeypatch):
    """The SDK parses real JSON-RPC pipes; the middleware fences legacy ingress."""
    marker = tmp_path / "effects.jsonl"
    child = textwrap.dedent(
        """
        import asyncio, json, os
        from pathlib import Path
        from scribe_mcp.mcp_adapter import (
            MCPCompatibilityPolicy, ProtocolEra, build_mcp_server,
            configure_mcp_server, load_mcp_runtime, normalize_tool_definition,
        )
        runtime = load_mcp_runtime()
        server = build_mcp_server("raw-wire-test", MCPCompatibilityPolicy())
        tool = normalize_tool_definition(runtime=runtime, era=ProtocolEra.MODERN,
            name="effect", description="Effect probe", input_schema={"type":"object",
            "properties":{"value":{"type":"string"}},"required":["value"],
            "additionalProperties":False})
        def record(event):
            with Path(os.environ["SCRIBE_TEST_EFFECTS"]).open("a") as stream:
                stream.write(json.dumps(event) + "\\n")
        async def listed(era):
            record({"event":"list", "era":era.value})
            return [tool]
        async def called(name, arguments, context, era):
            record({"event":"call", "name":name})
            return {"ok":True, "value":arguments["value"]}
        configure_mcp_server(server, runtime=runtime,
            definition_provider=lambda:{"effect":tool}, list_handler=listed, call_handler=called)
        asyncio.run(server.run_stdio_async())
        """
    )
    child_env = dict(os.environ)
    child_env.update(
        {
            "SCRIBE_MODE": "standalone",
            "SCRIBE_STORAGE_BACKEND": "sqlite",
            "SCRIBE_DISABLE_DOTENV": "1",
            "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": f"{os.getcwd()}/src:{os.getcwd()}/tests",
            "SCRIBE_TEST_EFFECTS": str(marker),
        }
    )
    version_key = "io.modelcontextprotocol/protocolVersion"
    capabilities_key = "io.modelcontextprotocol/clientCapabilities"
    def request(request_id, method, *, version="2026-07-28", params=None):
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        if version is not ...:
            payload["params"]["_meta"] = {
                version_key: version,
                capabilities_key: {},
            }
        return json.dumps(payload, separators=(",", ":"))

    async def exchange(messages, *, child_source=child, sequential=False):
        async with _managed_child_process(
            sys.executable,
            "-c",
            child_source,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_env,
            cwd=os.getcwd(),
        ) as process:
            if sequential:
                responses = []
                for message in messages:
                    process.stdin.write((message + "\n").encode())
                    await process.stdin.drain()
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
                    assert line, "the SDK child dropped a sequential request response"
                    responses.append(json.loads(line))
                process.stdin.close()
                await asyncio.wait_for(process.wait(), timeout=10)
                stderr = await process.stderr.read()
                assert process.returncode == 0, stderr.decode()
                return responses
            wire = "\n".join(messages) + "\n"
            stdout, stderr = await asyncio.wait_for(process.communicate(wire.encode()), timeout=15)
            assert process.returncode == 0, stderr.decode()
            return [json.loads(line) for line in stdout.decode().splitlines() if line.strip()]

    rejected = [
        (1, request(1, "initialize", version="2025-11-25", params={"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "wire-test", "version": "1.0"}}), -32022),
        (2, request(2, "initialize", version="2025-06-18", params={"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "wire-test", "version": "1.0"}}), -32022),
        (3, request(3, "initialize", version="2024-11-05", params={"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "wire-test", "version": "1.0"}}), -32022),
        (4, request(4, "initialize", version="2026-07-28", params={"protocolVersion": "2026-07-28", "capabilities": {}, "clientInfo": {"name": "wire-test", "version": "1.0"}}), -32022),
        (5, request(5, "tools/list", version="2025-11-25"), -32022),
        (6, request(6, "tools/list", version="2099-01-01"), -32022),
        (7, request(7, "tools/list", version="not-a-version"), -32022),
        (8, request(8, "tools/call", version="2099-01-01", params={"name": "effect", "arguments": {"value": "bad"}}), -32022),
        (9, request(9, "tools/list", version=3), -32602),
        (10, request(10, "tools/list", version=None), -32602),
        (11, request(11, "tools/list", version=...), -32022),
        (12, json.dumps({"jsonrpc": "2.0", "id": 12, "method": "tools/list", "params": {"_meta": None}}), -32022),
        (13, json.dumps({"jsonrpc": "2.0", "id": 13, "method": "tools/list", "params": {"_meta": "invalid"}}), -32022),
    ]
    for request_id, message, code in rejected:
        responses = await exchange([message])
        assert len(responses) == 1
        assert responses[0]["id"] == request_id
        assert responses[0]["error"]["code"] == code, (request_id, responses[0])
        if code == -32022:
            assert responses[0]["error"]["data"]["supported"] == ["2026-07-28"]
        assert not marker.exists(), f"rejected request {request_id} caused an application effect"

    malformed_json = await exchange(['{"jsonrpc":"2.0","id":14,"method":"tools/list","params":'])
    assert malformed_json == []
    assert not marker.exists(), "malformed JSON caused an application effect"

    notifications = await exchange(
        [
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"_meta": {version_key: "2025-11-25"}}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"_meta": "invalid"}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"_meta": {version_key: None}}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"_meta": {version_key: 3}}}),
            request(8, "tools/list"),
        ]
    )
    assert len(notifications) == 1
    assert notifications[0]["id"] == 8
    assert notifications[0]["result"]["tools"][0]["name"] == "effect"
    effects = [json.loads(line) for line in marker.read_text().splitlines()]
    assert effects == [{"event": "list", "era": "modern"}]

    discover = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 19,
            "method": "server/discover",
            "params": {
                "_meta": {
                    version_key: "2026-07-28",
                    "io.modelcontextprotocol/clientInfo": {"name": "wire-test", "version": "1.0"},
                    capabilities_key: {},
                }
            },
        }
    )
    after_valid = await exchange(
        [
            discover,
            request(20, "tools/list"),
            request(21, "initialize", version="2026-07-28", params={"protocolVersion": "2026-07-28", "capabilities": {}, "clientInfo": {"name": "wire-test", "version": "1.0"}}),
        ],
        sequential=True,
    )
    assert [item["id"] for item in after_valid] == [19, 20, 21]
    assert after_valid[0]["result"]
    assert after_valid[1]["result"]["tools"][0]["name"] == "effect"
    assert after_valid[2]["id"] == 21
    assert after_valid[2]["error"]["code"] == -32022
    assert after_valid[2]["error"]["data"]["supported"] == ["2026-07-28"]
    after_valid_effects = [json.loads(line) for line in marker.read_text().splitlines()]
    assert after_valid_effects == [
        {"event": "list", "era": "modern"},
        {"event": "list", "era": "modern"},
    ]

    legacy_initialize = request(
        30,
        "initialize",
        version="2025-11-25",
        params={"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "wire-test", "version": "1.0"}},
    )
    unguarded_source = child.replace(
        'server = build_mcp_server("raw-wire-test", MCPCompatibilityPolicy())',
        'server = runtime.server_type(name="raw-wire-test")',
    )
    unguarded = await exchange([legacy_initialize], child_source=unguarded_source)
    assert len(unguarded) == 1
    assert "result" in unguarded[0], "old-initialize sensitivity control did not expose the missing guard"

    omitted_middleware_source = child.replace(
        'server = build_mcp_server("raw-wire-test", MCPCompatibilityPolicy())',
        'server = runtime.server_type(name="raw-wire-test", middleware=[])',
    )
    omitted_middleware = await exchange([legacy_initialize], child_source=omitted_middleware_source)
    assert len(omitted_middleware) == 1
    assert "result" in omitted_middleware[0], "middleware sensitivity control did not expose the missing guard"

    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "1.26.0")
    with pytest.raises(RuntimeError, match="unsupported mcp distribution major"):
        load_mcp_runtime()


@pytest.mark.asyncio
async def test_first_call_loads_lazy_definitions_and_preserves_refusals():
    era = ProtocolEra.MODERN
    runtime = load_mcp_runtime()
    server = build_mcp_server("scribe-lazy-test", MCPCompatibilityPolicy())
    definitions = {}
    events = []

    async def list_handler(request_era):
        assert request_era is era
        events.append("load")
        definitions["sample"] = normalize_tool_definition(
            runtime=runtime,
            era=ProtocolEra.MODERN,
            name="sample",
            description="A lazily registered tool",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        return list(definitions.values())

    async def call_handler(name, arguments, context, request_era):
        assert name == "sample"
        assert request_era is era
        assert context is None
        events.append("call")
        return {"ok": True, "value": arguments["value"]}

    configure_mcp_server(
        server,
        runtime=runtime,
        definition_provider=lambda: definitions,
        list_handler=list_handler,
        call_handler=call_handler,
    )

    for value in ("first", "warm"):
        result = await server.call_tool("sample", {"value": value}, protocol_era=era)
        assert result.structured_content == {"ok": True, "value": value}
        assert result.is_error is False
    assert events == ["load", "call", "call"]

    for invalid in ({}, {"value": 1}, {"value": "valid", "extra": True}):
        with pytest.raises(ValueError, match="invalid arguments"):
            await server.call_tool("sample", invalid, protocol_era=era)
    assert events == ["load", "call", "call"]

    with pytest.raises(ValueError, match="Unknown tool"):
        await server.call_tool("missing", {}, protocol_era=era)
    assert events.count("call") == 2


_RETIRED_LEGACY_WIRE_NODES = (
    ("test_tool_definition_preserves_schema_metadata_and_hints[era=legacy]", "tools/list"),
    ("test_result_normalization_preserves_structured_text_and_error_semantics[era=legacy]", "tools/call"),
    ("test_first_call_loads_lazy_definitions_and_preserves_refusals[era=legacy]", "tools/call"),
    *(
        (f"TestSBRDefaultOutput.test_current_default_raw_and_existing_sdk_envelopes_fit[era=legacy,kind={kind}]", "tools/call")
        for kind in ("raw-dict", "raw-string", "text-structured", "sdk-result")
    ),
    ("TestSBRDefaultOutput.test_normalizer_preserves_exact_control_facts[era=legacy]", "tools/call"),
    *(
        (f"TestSBRDefaultOutput.test_error_control_retry_and_effect_facts_survive_both_eras[era=legacy,code={code}]", "tools/call")
        for code in ("SCRIBE_OUTPUT_DETAIL_REQUIRED", "SCRIBE_FACT_PERSISTENCE_FAILED", "UNKNOWN_TOOL")
    ),
    ("TestSBRDefaultOutput.test_legacy_text_only_projection_remains_complete_json[era=legacy]", "tools/call"),
    *(
        (f"TestSBRDefaultOutput.test_invalid_detail_is_rejected_before_adapter_producer[era=legacy,selector={selector}]", "tools/call")
        for selector in ("None", "False", "0", "1", "selector4", "selector5", "empty-string", "FULL", "leading-space", "trailing-space", "unknown")
    ),
    ("TestSBRDefaultOutput.test_raw_early_error_is_bounded_and_marked_error[era=legacy]", "tools/call"),
    ("TestSBRDefaultOutput.test_explicit_full_adapter_preserves_transient_content_once[era=legacy]", "tools/call"),
)


@pytest.mark.startup
class TestModernTransportIngress:
    @pytest.mark.parametrize(
        ("retired_node", "operation"),
        _RETIRED_LEGACY_WIRE_NODES,
        ids=[
            f"retired_{index:02d}_{operation.replace('/', '_')}"
            for index, (_, operation) in enumerate(_RETIRED_LEGACY_WIRE_NODES, start=1)
        ],
    )
    @pytest.mark.asyncio
    async def test_unsupported_legacy_wire_rejected_before_effects(
        self, tmp_path, retired_node, operation
    ):
        """Map each removed legacy-positive node to a denied SDK wire operation."""
        marker = tmp_path / "effects.jsonl"
        child = textwrap.dedent(
            """
            import asyncio, json, os
            from pathlib import Path
            from scribe_mcp.mcp_adapter import (
                MCPCompatibilityPolicy, ProtocolEra, build_mcp_server,
                configure_mcp_server, load_mcp_runtime, normalize_tool_definition,
            )
            runtime = load_mcp_runtime()
            server = build_mcp_server("retirement-wire-test", MCPCompatibilityPolicy())
            tool = normalize_tool_definition(runtime=runtime, era=ProtocolEra.MODERN,
                name="effect", description="Retirement probe", input_schema={"type":"object",
                "properties":{"value":{"type":"string"}},"required":["value"],
                "additionalProperties":False})
            def record(event):
                with Path(os.environ["SCRIBE_TEST_EFFECTS"]).open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event) + "\\n")
            async def listed(era):
                record({"event":"list"})
                return [tool]
            async def called(name, arguments, context, era):
                record({"event":"call"})
                return {"ok":True}
            configure_mcp_server(server, runtime=runtime,
                definition_provider=lambda:{"effect":tool}, list_handler=listed, call_handler=called)
            asyncio.run(server.run_stdio_async())
            """
        )
        child_env = dict(os.environ)
        child_env.update(
            {
                "PYTHONPATH": f"{os.getcwd()}/src:{os.getcwd()}/tests",
                "PYTHONDONTWRITEBYTECODE": "1",
                "SCRIBE_TEST_EFFECTS": str(marker),
            }
        )
        params = {"name": "effect", "arguments": {"value": "retired"}} if operation == "tools/call" else {}
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": operation,
            "params": {
                **params,
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2025-11-25",
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
            },
        }
        async with _managed_child_process(
            sys.executable, "-c", child,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=child_env, cwd=os.getcwd(),
        ) as process:
            stdout, stderr = await asyncio.wait_for(
                process.communicate((json.dumps(payload) + "\n").encode()), timeout=15
            )
            assert process.returncode == 0, f"{retired_node}: {stderr.decode()}"
            responses = [json.loads(line) for line in stdout.decode().splitlines() if line.strip()]
            assert len(responses) == 1, retired_node
            assert responses[0]["id"] == 1
            assert responses[0]["error"]["code"] == -32022, retired_node
            assert responses[0]["error"]["data"]["supported"] == ["2026-07-28"]
            assert not marker.exists(), f"{retired_node} dispatched {operation}"


@pytest.mark.core
@pytest.mark.regression
class TestSBRDefaultOutput:
    """Adapter value/serialization tests; no authenticated caller is simulated."""

    @staticmethod
    def _size(result):
        payload = result.model_dump(by_alias=True, exclude_none=True)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
        actual_sdk = result.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")
        return len(canonical), len(actual_sdk)

    @pytest.mark.parametrize("kind", ["raw-dict", "raw-string", "text-structured", "sdk-result"])
    def test_current_default_raw_and_existing_sdk_envelopes_fit(self, test_agent, kind):
        era = ProtocolEra.MODERN
        runtime = load_mcp_runtime()
        value = "漢🌊\\\"\n" * 20000
        data = {"ok": True, "metadata": {"notes": value}, "count": 1}
        if kind == "raw-dict":
            source = data
        elif kind == "raw-string":
            source = value
        else:
            source = {"content": [{"type": "text", "text": json.dumps(data)}],
                      "structuredContent": data, "isError": False}
            if kind == "sdk-result":
                source = runtime.types.CallToolResult(**source)
        before = copy.deepcopy(source)
        result = normalize_tool_result(source, runtime=runtime, era=era)
        canonical, sdk = self._size(result)
        assert source == before
        print(json.dumps({"fixture": "adapter-default", "era": era.value, "kind": kind,
                          "canonical_bytes": canonical, "sdk_bytes": sdk}))
        assert max(canonical, sdk) <= 2048, f"adapter bytes canonical={canonical} sdk={sdk}"

    def test_normalizer_preserves_exact_control_facts(self, test_agent):
        """Small transient control values, independent of runtime authentication."""
        era = ProtocolEra.MODERN
        runtime = load_mcp_runtime()
        data = {"ok": True, "entries": [{"id": 1, "message": "漢🌊"}],
                "binding": {"id": "b" * 64, "generation": 23, "reused": True, "write_performed": False},
                "durability": {"file": "committed", "db_mirror": "queued", "audit_id": "a" * 64},
                "convergence": {"state": "queued", "digest": "d" * 64, "generation": 8, "replay": False},
                "retry": {"queued": True, "retryable": False, "retry_after_ms": 1200},
                "correlation_id": "c" * 64, "release_handle": "response-only-control"}
        before = copy.deepcopy(data)
        result = normalize_tool_result(data, runtime=runtime, era=era)
        assert result.structured_content == before
        assert json.loads(result.content[0].text) == before
        assert result.is_error is False
        assert data == before

    @pytest.mark.parametrize("code", ["SCRIBE_OUTPUT_DETAIL_REQUIRED", "SCRIBE_FACT_PERSISTENCE_FAILED", "UNKNOWN_TOOL"])
    def test_error_control_retry_and_effect_facts_survive_current_era(self, test_agent, code):
        era = ProtocolEra.MODERN
        runtime = load_mcp_runtime()
        data = {"schema_version": "scribe-error-summary.v1", "ok": False, "error_code": code,
                "message": "Use explicit full detail for this operation.", "retryable": False,
                "correlation_id": "c" * 64, "retry_after_ms": 1200,
                "effect_status": "unknown", "mutation_retry_safe": False,
                "target": {"state": "not_disclosed"},
                "candidates": {"state": "unavailable", "total_count": None}}
        before = copy.deepcopy(data)
        result = normalize_tool_result(data, runtime=runtime, era=era, is_error=True)
        assert result.is_error is True
        assert result.structured_content == before
        assert json.loads(result.content[0].text) == before
        assert max(self._size(result)) <= 2048
        assert data == before

    def test_text_only_projection_remains_complete_json(self, test_agent):
        era = ProtocolEra.MODERN
        projected = {"ok": True, "kind": "preview", "returned_count": 3, "total_count": 10,
                     "omitted_count": 7, "complete": False,
                     "continuation": {"tool": "read_recent", "arguments": {"page": 4, "response_detail": "full"},
                                      "consistency": "current"}}
        result = normalize_tool_result(
            {"content": [{"type": "text", "text": json.dumps(projected)}], "isError": False},
            runtime=load_mcp_runtime(), era=era)
        assert json.loads(result.content[0].text) == projected
        assert max(self._size(result)) <= 2048

    @pytest.mark.asyncio
    @pytest.mark.parametrize("selector", [None, False, 0, 1, [], {}, "", "FULL", " full", "full ", "unknown"])
    async def test_invalid_detail_is_rejected_before_adapter_producer(self, test_agent, selector):
        era = ProtocolEra.MODERN
        from scribe_mcp import server as source_server

        runtime = load_mcp_runtime()
        sdk_server = build_mcp_server("scribe-output-selector-test", MCPCompatibilityPolicy())
        source_server.list_registered_tools()
        definition = source_server._SCRIBE_TOOL_DEFS["append_entry"]
        calls = []

        async def list_handler(request_era):
            return [definition]

        async def producer(name, arguments, context, request_era):
            calls.append(name)
            return {"ok": True}

        configure_mcp_server(sdk_server, runtime=runtime,
                             definition_provider=lambda: {"append_entry": definition},
                             list_handler=list_handler, call_handler=producer)
        with pytest.raises(ValueError, match="response_detail|invalid arguments"):
            await sdk_server.call_tool("append_entry", {"agent": test_agent, "message": "one write",
                                                       "response_detail": selector}, protocol_era=era)
        assert calls == [], f"invalid detail reached producer {len(calls)} time(s)"

    def test_raw_early_error_is_bounded_and_marked_error(self, test_agent):
        era = ProtocolEra.MODERN
        data = {"ok": False, "error_code": "SCRIBE_ARGUMENT_INVALID", "retryable": False,
                "correlation_id": "c" * 64, "effect_status": "none", "mutation_retry_safe": True,
                "message": "Invalid input", "debug": {"exception_notes": "x" * 100000}}
        before = copy.deepcopy(data)
        result = normalize_tool_result(data, runtime=load_mcp_runtime(), era=era)
        canonical, sdk = self._size(result)
        error_flag = result.is_error
        assert data == before
        print(json.dumps({"fixture": "early-error", "era": era.value,
                          "canonical_bytes": canonical, "sdk_bytes": sdk, "is_error": error_flag}))
        assert error_flag is True
        assert max(canonical, sdk) <= 2048
        for field in ("ok", "error_code", "retryable", "correlation_id", "effect_status", "mutation_retry_safe"):
            assert result.structured_content[field] == before[field]

    @pytest.mark.asyncio
    async def test_explicit_full_adapter_preserves_transient_content_once(self, test_agent):
        """SDK adapter proof only; the external producer makes no authority grant."""
        era = ProtocolEra.MODERN
        runtime = load_mcp_runtime()
        sdk_server = build_mcp_server("scribe-output-full-test", MCPCompatibilityPolicy())
        definition = normalize_tool_definition(
            runtime=runtime, era=era, name="selected_output", description="Test-only value producer",
            input_schema={"type": "object", "properties": {
                "agent": {"type": "string"},
                "response_detail": {"type": "string", "enum": ["default", "full"], "default": "default"}},
                "required": ["agent"], "additionalProperties": False})
        data = {"ok": True, "body": "漢🌊\\\"\n" * 20000,
                "apply": {"receipt": "test-only-response-control", "expires_at": "2030-01-01T00:00:00Z"}}
        calls = []

        async def list_handler(request_era):
            return [definition]

        async def producer(name, arguments, context, request_era):
            calls.append(name)
            return copy.deepcopy(data)

        configure_mcp_server(sdk_server, runtime=runtime,
                             definition_provider=lambda: {"selected_output": definition},
                             list_handler=list_handler, call_handler=producer)
        result = await sdk_server.call_tool("selected_output", {"agent": test_agent, "response_detail": "full"},
                                            protocol_era=era)
        assert calls == ["selected_output"]
        assert result.structured_content == data
        assert json.loads(result.content[0].text) == data
