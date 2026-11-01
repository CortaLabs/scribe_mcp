"""Tests for Phase 1: Transport Layer (SSE server + CLI flags).

Verifies:
- server_sse module imports and exports
- CLI argument parsing with defaults and overrides
- Environment variable fallbacks
- Health check endpoint response format
- SSE transport route structure
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import os
import secrets
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from scribe_mcp.state.agent_manager import SessionLeaseExpired

pytestmark = pytest.mark.startup


@pytest.fixture(autouse=True)
def restore_transport_policy():
    """Keep real SSE startup policy changes local to each test."""
    from scribe_mcp import server as server_module

    original_policy = server_module.get_transport_policy()
    try:
        yield
    finally:
        server_module.app.state.transport_policy = original_policy


# Ensure the src directory is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@contextmanager
def _managed_child_process(command, *, cwd: Path, env: dict[str, str], log_path: Path):
    """Start one child and guarantee bounded terminate/kill/reap cleanup."""
    with log_path.open("w+", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


# ---------------------------------------------------------------------------
# Task 1.1: server_sse module tests
# ---------------------------------------------------------------------------

class TestServerSSEImports:
    """Verify that server_sse exports all required symbols."""

    def test_import_run_sse(self):
        from scribe_mcp.server_sse import run_sse
        assert callable(run_sse)

    def test_import_health_check(self):
        from scribe_mcp.server_sse import health_check
        assert callable(health_check)

    def test_import_main(self):
        from scribe_mcp.server_sse import main
        assert callable(main)

    def test_run_sse_is_coroutine(self):
        from scribe_mcp.server_sse import run_sse
        assert asyncio.iscoroutinefunction(run_sse)

    def test_health_check_is_coroutine(self):
        from scribe_mcp.server_sse import health_check
        assert asyncio.iscoroutinefunction(health_check)


class TestHealthCheckEndpoint:
    """Verify the /health endpoint returns the correct JSON structure."""

    @pytest.mark.asyncio
    async def test_health_check_response_fields(self):
        """Health check must return all 5 required fields."""
        import scribe_mcp.server_sse as sse_mod

        # Set server start time so uptime is calculable
        sse_mod._server_start_time = 1000.0

        with patch("scribe_mcp.server_sse.time") as mock_time:
            mock_time.time.return_value = 1042.0

            # Create a minimal mock request
            mock_request = MagicMock()

            response = await sse_mod.health_check(mock_request)

        # Parse the response body
        body = json.loads(response.body.decode())

        assert body["status"] == "healthy"
        assert body["service"] == "scribe-mcp"
        assert body["version"] == "2.2"
        assert body["transport"] == "sse"
        assert body["uptime_seconds"] == 42

    @pytest.mark.asyncio
    async def test_health_check_uptime_zero_before_startup(self):
        """Before server start, uptime should be 0."""
        import scribe_mcp.server_sse as sse_mod

        original = sse_mod._server_start_time
        try:
            sse_mod._server_start_time = None
            mock_request = MagicMock()
            response = await sse_mod.health_check(mock_request)
            body = json.loads(response.body.decode())
            assert body["uptime_seconds"] == 0
        finally:
            sse_mod._server_start_time = original

    @pytest.mark.asyncio
    async def test_health_check_returns_json_response(self):
        """Health check must return a JSONResponse (200 status)."""
        from starlette.responses import JSONResponse
        import scribe_mcp.server_sse as sse_mod

        sse_mod._server_start_time = 1000.0
        mock_request = MagicMock()

        with patch("scribe_mcp.server_sse.time") as mock_time:
            mock_time.time.return_value = 1000.0
            response = await sse_mod.health_check(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 200


class TestSSERouteStructure:
    """Verify the SSE CLI alias exposes only the modern MCP HTTP route."""

    def test_builder_has_no_legacy_transport_routes(self):
        import scribe_mcp.server_sse as sse_mod

        assembled = sse_mod._build_starlette_app(expected_auth_token="top-secret")
        route_paths = {getattr(route, "path", None) for route in assembled.routes}
        assert "/mcp" in route_paths
        assert "/health" in route_paths
        assert not route_paths.intersection({"/sse", "/messages", "/messages/"})

    @pytest.mark.asyncio
    async def test_run_sse_creates_starlette_app(self):
        """run_sse should create a Starlette app with /health and /mcp routes."""

        captured_app = None

        with patch("scribe_mcp.server_sse._startup", new_callable=AsyncMock) as mock_startup, \
             patch("scribe_mcp.server_sse.uvicorn") as mock_uvicorn:

            # Make uvicorn.Server.serve() a coroutine that captures the config
            mock_server_instance = MagicMock()

            async def fake_serve():
                pass

            mock_server_instance.serve = fake_serve
            mock_uvicorn.Server.return_value = mock_server_instance

            # Capture the Config call
            def capture_config(app, **kwargs):
                nonlocal captured_app
                captured_app = app
                return MagicMock()

            mock_uvicorn.Config = capture_config

            from scribe_mcp.server_sse import run_sse
            await run_sse(host="127.0.0.1", port=9999, auth_token="test-token")

        mock_startup.assert_called_once()
        assert captured_app is not None

        # Check routes
        route_paths = []
        for route in captured_app.routes:
            if hasattr(route, "path"):
                route_paths.append(route.path)

        assert "/health" in route_paths, f"Missing /health route in {route_paths}"
        assert any(p.rstrip("/") == "/mcp" for p in route_paths), (
            f"Missing /mcp route in {route_paths}"
        )
        assert "/sse" not in route_paths
        assert not any(p.rstrip("/") == "/messages" for p in route_paths)

    @pytest.mark.asyncio
    async def test_run_sse_passes_host_port_to_uvicorn(self):
        """run_sse should forward host and port to uvicorn.Config."""
        captured_kwargs = {}

        with patch("scribe_mcp.server_sse._startup", new_callable=AsyncMock), \
             patch("scribe_mcp.server_sse.uvicorn") as mock_uvicorn:

            mock_server_instance = MagicMock()

            async def fake_serve():
                pass

            mock_server_instance.serve = fake_serve
            mock_uvicorn.Server.return_value = mock_server_instance

            def capture_config(app, **kwargs):
                captured_kwargs.update(kwargs)
                return MagicMock()

            mock_uvicorn.Config = capture_config

            from scribe_mcp.server_sse import run_sse
            await run_sse(host="192.168.1.1", port=7777, auth_token="test-token")

        assert captured_kwargs["host"] == "192.168.1.1"
        assert captured_kwargs["port"] == 7777
        assert captured_kwargs["log_level"] == "info"

    @pytest.mark.asyncio
    async def test_run_sse_registers_shutdown_handler(self):
        """run_sse should register _shutdown via the app lifespan."""
        captured_app = None

        with patch("scribe_mcp.server_sse._startup", new_callable=AsyncMock), \
             patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock) as mock_shutdown, \
             patch("scribe_mcp.server_sse.uvicorn") as mock_uvicorn:

            mock_server_instance = MagicMock()

            async def fake_serve():
                pass

            mock_server_instance.serve = fake_serve
            mock_uvicorn.Server.return_value = mock_server_instance

            def capture_config(app, **kwargs):
                nonlocal captured_app
                captured_app = app
                return MagicMock()

            mock_uvicorn.Config = capture_config

            from scribe_mcp.server_sse import run_sse
            await run_sse(auth_token="test-token")

            async with captured_app.router.lifespan_context(captured_app):
                pass

            mock_shutdown.assert_awaited_once()


class TestSSEOutsideRepoRuntimePolicy:
    def test_loopback_authenticated_sse_is_trusted_default_allow(self):
        from scribe_mcp.server_sse import _resolve_transport_runtime

        with patch.dict(os.environ, {"SCRIBE_TRANSPORT_AUTH_TOKEN": "top-secret"}, clear=False):
            runtime_settings, policy, resolved_token = _resolve_transport_runtime(
                "127.0.0.1",
                8200,
                None,
            )

        effective_policy = runtime_settings.resolve_outside_repo_read_policy(
            {
                "transport": policy.transport,
                "bind_host": policy.bind_host,
                "port": policy.port,
                "network_exposed": policy.network_exposed,
                "auth_required": policy.auth_required,
                "auth_configured": policy.auth_configured,
                "allow_outside_repo_reads": policy.allow_outside_repo_reads,
            }
        )

        assert resolved_token == "top-secret"
        assert effective_policy["trusted_runtime"] is True
        assert effective_policy["enabled"] is True
        assert effective_policy["force_enabled"] is False

    def test_non_loopback_sse_requires_explicit_force_enable(self):
        from scribe_mcp.server_sse import _resolve_transport_runtime

        with patch.dict(
            os.environ,
            {
                "SCRIBE_TRANSPORT_AUTH_TOKEN": "top-secret",
                "SCRIBE_ALLOW_OUTSIDE_REPO_READS": "1",
            },
            clear=False,
        ):
            runtime_settings, policy, _ = _resolve_transport_runtime("0.0.0.0", 8200, None)

        effective_policy = runtime_settings.resolve_outside_repo_read_policy(
            {
                "transport": policy.transport,
                "bind_host": policy.bind_host,
                "port": policy.port,
                "network_exposed": policy.network_exposed,
                "auth_required": policy.auth_required,
                "auth_configured": policy.auth_configured,
                "allow_outside_repo_reads": policy.allow_outside_repo_reads,
            }
        )

        assert effective_policy["network_exposed"] is True
        assert effective_policy["trusted_runtime"] is False
        assert effective_policy["force_enabled"] is True
        assert effective_policy["enabled"] is True


# ---------------------------------------------------------------------------
# Task 1.2: __main__.py CLI tests
# ---------------------------------------------------------------------------

class TestTransportAuthBoundary:
    """Verify the shared auth boundary for SSE, MCP message POST, and REST helpers."""

    def test_unauthenticated_sse_and_rest_requests_are_rejected(self):
        import scribe_mcp.server_sse as sse_mod

        with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
            app = sse_mod._build_starlette_app(
                expected_auth_token="top-secret",
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                modern_response = client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                )
                sse_response = client.get("/sse")
                rest_response = client.post("/api/v1/batch", json={"operations": []})
                message_response = client.post("/messages/")
                invalid_response = client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    headers={"authorization": "Bearer wrong-token"},
                )
                health_response = client.get("/health")

        assert modern_response.status_code == 401
        assert sse_response.status_code == 401
        assert rest_response.status_code == 401
        assert message_response.status_code == 401
        assert invalid_response.status_code == 401
        assert modern_response.json()["type"] == "Unauthorized"
        assert sse_response.json()["type"] == "Unauthorized"
        assert rest_response.json()["type"] == "Unauthorized"
        assert message_response.json()["type"] == "Unauthorized"
        assert health_response.status_code == 200

    def test_all_non_health_routes_share_origin_and_auth_policy(self, monkeypatch):
        import scribe_mcp.server_sse as sse_mod

        monkeypatch.setenv("SCRIBE_TRANSPORT_ALLOWED_ORIGINS", "https://trusted.example")
        with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
            app = sse_mod._build_starlette_app(
                expected_auth_token="top-secret",
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                for method, path, payload in (
                    ("post", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                    ("get", "/sse", None),
                    ("post", "/messages/", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                    ("post", "/api/v1/batch", {"operations": []}),
                ):
                    request_kwargs = {
                        "headers": {
                            "authorization": "Bearer top-secret",
                            "origin": "https://evil.example",
                        }
                    }
                    if payload is not None:
                        request_kwargs["json"] = payload
                    response = getattr(client, method)(path, **request_kwargs)
                    assert response.status_code == 403, (path, response.text)
                    assert response.json()["type"] == "InvalidOrigin"

                health = client.get("/health", headers={"origin": "https://evil.example"})

        assert health.status_code == 200

    def test_multiple_origin_and_conflicting_auth_headers_fail_closed(self):
        import scribe_mcp.server_sse as sse_mod

        with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
            app = sse_mod._build_starlette_app(
                expected_auth_token="top-secret",
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                multiple_origin = client.post(
                    "/api/v1/batch",
                    json={"operations": []},
                    headers=[
                        ("authorization", "Bearer top-secret"),
                        ("origin", "https://one.example"),
                        ("origin", "https://two.example"),
                    ],
                )
                auth_mismatch = client.post(
                    "/api/v1/batch",
                    json={"operations": []},
                    headers={
                        "authorization": "Bearer top-secret",
                        "x-scribe-auth": "different-token",
                    },
                )

        assert multiple_origin.status_code == 400
        assert multiple_origin.json()["type"] == "HeaderMismatch"
        assert auth_mismatch.status_code == 400
        assert auth_mismatch.json()["type"] == "HeaderMismatch"

    def test_modern_revision_and_body_mismatch_reject_before_dispatch(self, monkeypatch):
        import scribe_mcp.server_sse as sse_mod

        call_tool = AsyncMock()
        monkeypatch.setattr(sse_mod.app, "call_tool", call_tool)
        with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
            app = sse_mod._build_starlette_app(
                expected_auth_token="top-secret",
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                unsupported = client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {
                            "_meta": {
                                "io.modelcontextprotocol/protocolVersion": "2099-01-01",
                                "io.modelcontextprotocol/clientCapabilities": {},
                            }
                        },
                    },
                    headers={
                        "authorization": "Bearer top-secret",
                        "mcp-protocol-version": "2099-01-01",
                        "mcp-method": "tools/list",
                        "accept": "application/json, text/event-stream",
                    },
                )
                mismatch = client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "clientInfo": {"name": "untrusted-label", "version": "1"},
                            "capabilities": {},
                        },
                    },
                    headers={
                        "authorization": "Bearer top-secret",
                        "mcp-protocol-version": "2026-07-28",
                        "accept": "application/json, text/event-stream",
                    },
                )

        assert unsupported.status_code == 400
        assert unsupported.json()["type"] == "UnsupportedProtocolVersion"
        assert unsupported.json()["error"]["code"] == -32022
        assert mismatch.status_code == 400
        assert mismatch.json()["type"] == "HeaderMismatch"
        assert mismatch.json()["error"]["code"] == -32020
        call_tool.assert_not_awaited()

    def test_valid_modern_tools_list_dispatches_without_protocol_session(self):
        import scribe_mcp.server_sse as sse_mod

        meta = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "test-client", "version": "1"},
        }
        with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
            app = sse_mod._build_starlette_app(
                expected_auth_token="top-secret",
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {"_meta": meta},
                    },
                    headers={
                        "authorization": "Bearer top-secret",
                        "mcp-protocol-version": "2026-07-28",
                        "mcp-method": "tools/list",
                        "accept": "application/json, text/event-stream",
                    },
                )

        assert response.status_code == 200
        assert "result" in response.json()
        assert "tools" in response.json()["result"]
        assert "mcp-session-id" not in response.headers
        assert response.headers["scribe-application-handle"]

    def test_invalid_modern_ingress_is_rejected_before_identity_resolution(self, monkeypatch):
        import scribe_mcp.server_sse as sse_mod

        resolve_identity = MagicMock(side_effect=AssertionError("invalid request resolved identity"))
        monkeypatch.setattr(sse_mod, "resolve_application_identity", resolve_identity)
        with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
            app = sse_mod._build_starlette_app(expected_auth_token="top-secret")
            with TestClient(app, raise_server_exceptions=False) as client:
                current_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {
                        "_meta": {
                            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                            "io.modelcontextprotocol/clientCapabilities": {},
                        }
                    },
                }
                base_headers = {
                    "authorization": "Bearer top-secret",
                    "mcp-protocol-version": "2026-07-28",
                    "mcp-method": "tools/list",
                    "accept": "application/json, text/event-stream",
                }
                missing_header = client.post(
                    "/mcp",
                    json=current_payload,
                    headers={key: value for key, value in base_headers.items() if key != "mcp-protocol-version"},
                )
                header_body_mismatch = client.post(
                    "/mcp",
                    json=current_payload,
                    headers={**base_headers, "mcp-protocol-version": "2025-11-25"},
                )
                unsupported = client.post(
                    "/mcp",
                    json={
                        **current_payload,
                        "params": {
                            "_meta": {
                                "io.modelcontextprotocol/protocolVersion": "2025-11-25",
                                "io.modelcontextprotocol/clientCapabilities": {},
                            }
                        },
                    },
                    headers={**base_headers, "mcp-protocol-version": "2025-11-25"},
                )
                missing_capability = client.post(
                    "/mcp",
                    json={
                        **current_payload,
                        "params": {
                            "_meta": {
                                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                            }
                        },
                    },
                    headers=base_headers,
                )
                bad_accept = client.post(
                    "/mcp",
                    json=current_payload,
                    headers={**base_headers, "accept": "text/plain"},
                )
                invalid_notification = client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/progress",
                        "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
                    },
                    headers={**base_headers, "mcp-method": "notifications/progress"},
                )

        assert missing_header.status_code == 400
        assert missing_header.json()["error"]["code"] == -32020
        assert header_body_mismatch.status_code == 400
        assert header_body_mismatch.json()["error"]["code"] == -32020
        assert unsupported.status_code == 400
        assert unsupported.json()["error"]["code"] == -32022
        assert missing_capability.status_code == 400
        assert missing_capability.json()["error"]["code"] == -32602
        assert bad_accept.status_code == 406
        assert invalid_notification.status_code == 400
        assert invalid_notification.content == b""
        resolve_identity.assert_not_called()

    def test_modern_get_delete_are_sdk_method_rejections_without_identity(self, monkeypatch):
        import scribe_mcp.server_sse as sse_mod

        resolve_identity = MagicMock(side_effect=AssertionError("non-POST resolved identity"))
        monkeypatch.setattr(sse_mod, "resolve_application_identity", resolve_identity)
        with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
            app = sse_mod._build_starlette_app(expected_auth_token="top-secret")
            with TestClient(app, raise_server_exceptions=False) as client:
                headers = {"authorization": "Bearer top-secret"}
                get_response = client.get("/mcp", headers=headers)
                delete_response = client.delete("/mcp", headers=headers)

        for response in (get_response, delete_response):
            assert response.status_code == 405
            assert response.headers["allow"] == "POST"
        resolve_identity.assert_not_called()

    def test_request_body_limit_rejects_before_route_dispatch(self, monkeypatch):
        import scribe_mcp.server_sse as sse_mod

        monkeypatch.setenv("SCRIBE_TRANSPORT_MAX_REQUEST_BYTES", "64")
        dispatch = AsyncMock(return_value={})
        monkeypatch.setattr(sse_mod.server_module, "invoke_tool", dispatch)
        with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
            app = sse_mod._build_starlette_app(
                expected_auth_token="top-secret",
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/api/v1/tools/invoke",
                    json={"tool_name": "x", "arguments": {"value": "x" * 256}},
                    headers={"authorization": "Bearer top-secret"},
                )

        assert response.status_code == 413
        assert response.json()["type"] == "RequestTooLarge"
        dispatch.assert_not_awaited()

    def test_request_timeout_is_typed_and_does_not_downgrade(self, monkeypatch):
        import scribe_mcp.server_sse as sse_mod

        async def slow_route(_request):
            await asyncio.sleep(0.2)
            return sse_mod.JSONResponse({"ok": True})

        monkeypatch.setenv("SCRIBE_TRANSPORT_REQUEST_TIMEOUT_SECONDS", "0.1")
        app = Starlette(routes=[Route("/mcp", slow_route, methods=["POST"])])
        app.add_middleware(
            sse_mod.TransportAuthMiddleware,
            expected_auth_token="top-secret",
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {
                        "_meta": {
                            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                            "io.modelcontextprotocol/clientCapabilities": {},
                        }
                    },
                },
                headers={
                    "authorization": "Bearer top-secret",
                    "mcp-protocol-version": "2026-07-28",
                    "mcp-method": "tools/list",
                    "accept": "application/json, text/event-stream",
                },
            )

        assert response.status_code == 504
        assert response.json()["type"] == "RequestTimeout"
        assert response.json()["reason_code"] == "request_timeout"

    def test_sdk_23_real_child_http_sse_and_application_handle_journey(self, tmp_path, test_agent):
        import asyncio
        import urllib.error
        import urllib.request

        import httpx2
        import mcp
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client

        sdk_version = __import__("importlib.metadata", fromlist=["version"]).version("mcp")
        assert sdk_version == "2.3.0"

        worktree_root = Path(__file__).resolve().parents[1]
        source_root = worktree_root / "src"
        runtime_root = tmp_path / "runtime"
        repo_root = tmp_path / "repo"
        hook_root = tmp_path / "child_hook"
        for path in (runtime_root, repo_root, hook_root):
            path.mkdir()
        sample = repo_root / "transport-proof.txt"
        sample.write_text("real-child-http-proof\n", encoding="utf-8")
        git_init = subprocess.run(
            ["git", "init", "--quiet", str(repo_root)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert git_init.returncode == 0, git_init.stderr
        origin_path = tmp_path / "child-origins.json"
        port = _free_loopback_port()
        token = secrets.token_urlsafe(32)

        (hook_root / "sitecustomize.py").write_text(
            textwrap.dedent(
                """
                import asyncio
                import contextvars
                import dataclasses
                import hashlib
                import importlib.metadata
                import json
                import os
                from pathlib import Path

                import mcp
                import scribe_mcp.server as server_module
                import scribe_mcp.server_sse as server_sse
                from mcp.server.mcpserver import Context as MCPContext
                from starlette.responses import JSONResponse
                from starlette.routing import Route

                effect_counters = {
                    "identity_resolutions": 0,
                    "begin_transport_operation": 0,
                    "end_transport_operation": 0,
                    "mcp_tool_dispatch": 0,
                    "restored_legacy_route_dispatch": 0,
                }
                progress_handler_counters = {
                    "started": 0,
                    "completed": 0,
                    "cancelled": 0,
                    "active": 0,
                }
                progress_release = asyncio.Event()
                original_identity_resolver = server_sse.resolve_application_identity

                def count_identity_resolution(*args, **kwargs):
                    effect_counters["identity_resolutions"] += 1
                    return original_identity_resolver(*args, **kwargs)

                server_sse.resolve_application_identity = count_identity_resolution
                original_begin_operation = server_module.begin_transport_operation
                original_end_operation = server_module.end_transport_operation
                original_call_tool = server_module.app.call_tool

                async def count_begin_operation(*args, **kwargs):
                    effect_counters["begin_transport_operation"] += 1
                    return await original_begin_operation(*args, **kwargs)

                async def count_end_operation(*args, **kwargs):
                    effect_counters["end_transport_operation"] += 1
                    return await original_end_operation(*args, **kwargs)

                async def count_mcp_tool_dispatch(*args, **kwargs):
                    effect_counters["mcp_tool_dispatch"] += 1
                    return await original_call_tool(*args, **kwargs)

                server_module.begin_transport_operation = count_begin_operation
                server_module.end_transport_operation = count_end_operation
                server_module.app.call_tool = count_mcp_tool_dispatch

                progress_context = contextvars.ContextVar("test_progress_context", default=None)

                @server_module.app.tool(
                    name="transport_progress_probe",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "agent": {"type": "string"},
                            "hold": {"type": "boolean"},
                        },
                        "required": ["agent"],
                        "additionalProperties": False,
                    },
                )
                async def transport_progress_probe(agent: str, hold: bool = False) -> str:
                    _ = agent
                    progress_handler_counters["started"] += 1
                    progress_handler_counters["active"] += 1
                    try:
                        context = progress_context.get()
                        if context is None:
                            raise RuntimeError("MCP request context was not injected into the test handler")
                        request_params = context.request_context.params or {}
                        request_meta = request_params.get("_meta", {})
                        progress_token = request_meta.get("progressToken")
                        if not progress_token:
                            raise RuntimeError("SDK client did not request progress for this call")
                        await context.report_progress(0.25, total=1, message="connected")
                        if hold:
                            progress_release.clear()
                            await progress_release.wait()
                        await context.report_progress(1, total=1, message="finished")
                        progress_handler_counters["completed"] += 1
                        return "progress-result"
                    except asyncio.CancelledError:
                        progress_handler_counters["cancelled"] += 1
                        raise
                    finally:
                        progress_handler_counters["active"] -= 1

                async def release_progress_probe(_request):
                    progress_release.set()
                    return JSONResponse({"released": True})

                async def establish_disposable_default(_request):
                    await server_module.state_manager.set_current_project(
                        "transport_http_test",
                        project_data={
                            "name": "transport_http_test",
                            "root": os.environ["SCRIBE_REPO_ROOT"],
                        },
                        agent_id=None,
                        session_id=None,
                        mirror_global=True,
                    )
                    return JSONResponse({"default_project": "transport_http_test"})

                async def inject_progress_context(request_context, call_next):
                    params = request_context.params or {}
                    name = params.get("name") if isinstance(params, dict) else None
                    if request_context.method == "tools/call" and name == "transport_progress_probe":
                        context = MCPContext(
                            request_context=request_context,
                            mcp_server=server_module.app,
                        )
                        token = progress_context.set(
                            context
                        )
                        try:
                            return await call_next(request_context)
                        finally:
                            progress_context.reset(token)
                    return await call_next(request_context)

                server_module.app.middleware.append(inject_progress_context)

                async def snapshot_real_child_state(_request):
                    from scribe_mcp.shared import execution_context as identity_module

                    state_manager = server_module.state_manager
                    state = await state_manager.load()
                    state_payload = dataclasses.asdict(state)
                    state_payload.pop("operation_timestamp", None)
                    agent_context = server_module.get_agent_context_manager()
                    async with agent_context._lease_lock:
                        leases = dict(agent_context._session_leases)
                    router = server_module.router_context_manager
                    async with router._lock:
                        transport_sessions = dict(router._transport_sessions)
                        router_projects = dict(router._session_projects)
                        files_read = {
                            key: sorted(value)
                            for key, value in router._files_read_in_session.items()
                        }
                        stable_sessions = dict(router._stable_agent_sessions)
                    stable_session_ids = dict(stable_sessions)
                    lease_session_ids = {
                        agent_id: lease[0] for agent_id, lease in leases.items()
                    }
                    session_ids = (
                        set(transport_sessions.values())
                        | set(router_projects)
                        | set(stable_session_ids.values())
                        | set(lease_session_ids.values())
                    )
                    session_bindings = {}
                    backend = server_module.storage_backend
                    global_default = await backend.get_agent_project("Scribe")
                    if hasattr(backend, "get_session_project"):
                        for session_id in sorted(session_ids):
                            binding = await backend.get_session_project(session_id)
                            if binding is not None:
                                session_bindings[session_id] = dataclasses.asdict(binding)
                    with identity_module._APPLICATION_IDENTITIES_LOCK:
                        identities = {
                            key: {
                                "identity_key": record.identity.identity_key,
                                "protocol_era": record.identity.protocol_era.value,
                                "transport": record.identity.transport,
                                "revoked": record.identity.revoked,
                                "expires_at": record.identity.expires_at.isoformat(),
                            }
                            for key, record in sorted(identity_module._APPLICATION_IDENTITIES.items())
                        }
                        stdio_identities = {
                            key: {
                                "identity_key": identity.identity_key,
                                "protocol_era": identity.protocol_era.value,
                                "transport": identity.transport,
                                "revoked": identity.revoked,
                                "expires_at": identity.expires_at.isoformat(),
                            }
                            for key, identity in sorted(identity_module._STDIO_IDENTITIES.items())
                        }
                    file_hashes = {}
                    file_sizes = {}
                    for label, root_text in (
                        ("runtime", os.environ["SCRIBE_ROOT"]),
                        ("repo", os.environ["SCRIBE_REPO_ROOT"]),
                    ):
                        root = Path(root_text)
                        for path in sorted(root.rglob("*")):
                            if not path.is_file() or ".git" in path.parts:
                                continue
                            rel = f"{label}/{path.relative_to(root).as_posix()}"
                            file_hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
                            file_sizes[rel] = path.stat().st_size
                    snapshot = {
                        "state": state_payload,
                        "global_default_project": global_default,
                        "state_manager_caches": {
                            "agent_state": state_manager._agent_state_cache,
                            "session_projects": state_manager._session_projects_cache,
                            "session_modes": state_manager._session_modes_cache,
                            "recent_projects": state_manager._recent_projects_cache,
                            "activity": state_manager._activity_cache,
                            "projects": state_manager._projects_cache,
                            "projects_cache_at": state_manager._projects_cache_at,
                        },
                        "router_caches": {
                            "transport_sessions": transport_sessions,
                            "session_projects": router_projects,
                            "files_read_in_session": files_read,
                            "stable_agent_sessions": stable_sessions,
                            "stable_session_ids": stable_session_ids,
                        },
                        "session_bindings": session_bindings,
                        "session_leases": leases,
                        "lease_session_ids": lease_session_ids,
                        "application_handle_registry": identities,
                        "stdio_identity_registry": stdio_identities,
                        "transport_shutdown": server_module.get_transport_shutdown_state(),
                        "dispatch_counters": dict(effect_counters),
                        "progress_handler_counters": dict(progress_handler_counters),
                        "file_sha256": file_hashes,
                        "file_sizes": file_sizes,
                    }
                    return JSONResponse(json.loads(json.dumps(snapshot, default=str, sort_keys=True)))

                original_build_app = server_sse._build_starlette_app

                def build_app_with_state_snapshot(**kwargs):
                    host_app = original_build_app(**kwargs)
                    original_auth_dispatch = server_sse.TransportAuthMiddleware.dispatch
                    saved_auth_dispatch = [None]
                    original_protocol_rejection = server_sse._protocol_rejection

                    async def restored_legacy_dispatch(self, request, call_next):
                        if request.url.path == "/sse":
                            return await call_next(request)
                        return await original_auth_dispatch(self, request, call_next)

                    async def restored_legacy_route(_request):
                        effect_counters["restored_legacy_route_dispatch"] += 1
                        return JSONResponse({"legacy": "restored"})

                    async def restore_legacy_route(_request):
                        if not any(route.path == "/sse" for route in host_app.routes):
                            host_app.routes.append(
                                Route("/sse", restored_legacy_route, methods=["GET"])
                            )
                        layer = host_app.middleware_stack
                        while layer is not None:
                            if isinstance(layer, server_sse.TransportAuthMiddleware):
                                saved_auth_dispatch[0] = layer.dispatch_func
                                layer.dispatch_func = restored_legacy_dispatch.__get__(
                                    layer, server_sse.TransportAuthMiddleware
                                )
                                break
                            layer = getattr(layer, "app", None)
                        assert saved_auth_dispatch[0] is not None
                        return JSONResponse({"restored": True})

                    async def remove_legacy_route(_request):
                        host_app.routes[:] = [
                            route for route in host_app.routes if route.path != "/sse"
                        ]
                        layer = host_app.middleware_stack
                        while layer is not None:
                            if isinstance(layer, server_sse.TransportAuthMiddleware):
                                if saved_auth_dispatch[0] is not None:
                                    layer.dispatch_func = saved_auth_dispatch[0]
                                break
                            layer = getattr(layer, "app", None)
                        return JSONResponse({"restored": False})

                    # Keep auth/origin middleware intact and bypass only protocol admission.
                    def bypass_invalid_protocol_admission(request, payload):
                        if (
                            request.url.path == "/mcp"
                            and request.method == "POST"
                            and request.headers.get("mcp-protocol-version") == "2025-11-25"
                        ):
                            return None
                        return original_protocol_rejection(request, payload)

                    async def bypass_protocol_admission(_request):
                        server_sse._protocol_rejection = bypass_invalid_protocol_admission
                        return JSONResponse({"admission": "protocol-bypassed-for-invalid-version"})

                    async def restore_protocol_admission(_request):
                        server_sse._protocol_rejection = original_protocol_rejection
                        return JSONResponse({"admission": "protocol-restored"})

                    host_app.routes.append(
                        Route("/__test/state", snapshot_real_child_state, methods=["GET"])
                    )
                    host_app.routes.append(
                        Route("/__test/release-progress", release_progress_probe, methods=["POST"])
                    )
                    host_app.routes.append(
                        Route("/__test/establish-default", establish_disposable_default, methods=["POST"])
                    )
                    host_app.routes.extend(
                        [
                            Route("/__test/sensitivity/restore-legacy", restore_legacy_route, methods=["POST"]),
                            Route("/__test/sensitivity/remove-legacy", remove_legacy_route, methods=["POST"]),
                            Route("/__test/sensitivity/bypass-protocol-admission", bypass_protocol_admission, methods=["POST"]),
                            Route("/__test/sensitivity/restore-protocol-admission", restore_protocol_admission, methods=["POST"]),
                        ]
                    )
                    return host_app

                server_sse._build_starlette_app = build_app_with_state_snapshot

                Path(os.environ["SCRIBE_TEST_TRANSPORT_ORIGIN_PATH"]).write_text(
                    json.dumps({
                        "mcp": mcp.__file__,
                        "server": server_module.__file__,
                        "server_sse": server_sse.__file__,
                        "sdk_version": importlib.metadata.version("mcp"),
                    }),
                    encoding="utf-8",
                )
                """
            ),
            encoding="utf-8",
        )

        child_env = {
            key: value
            for key, value in os.environ.items()
            if key in {"HOME", "PATH", "LANG", "LC_ALL", "VIRTUAL_ENV"}
        }
        child_env.update(
            {
                "PYTHONPATH": os.pathsep.join((str(hook_root), str(source_root))),
                "PYTHONDONTWRITEBYTECODE": "1",
                "SCRIBE_MODE": "standalone",
                "SCRIBE_STORAGE_BACKEND": "sqlite",
                "SCRIBE_DB_PATH": str(runtime_root / "scribe.sqlite3"),
                "SCRIBE_STATE_PATH": str(runtime_root / "state.json"),
                "SCRIBE_ROOT": str(runtime_root),
                "SCRIBE_REPO_ROOT": str(repo_root),
                "SCRIBE_REQUIRE_EXPLICIT_ROOT": "1",
                "SCRIBE_DISABLE_DOTENV": "1",
                "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
                "SCRIBE_TRANSPORT_LEGACY_ENABLED": "1",
                "SCRIBE_TRANSPORT_AUTH_TOKEN": token,
                "SCRIBE_TEST_TRANSPORT_ORIGIN_PATH": str(origin_path),
            }
        )
        endpoint = f"http://127.0.0.1:{port}/mcp"
        health_url = f"http://127.0.0.1:{port}/health"
        command = [
            sys.executable,
            "-m",
            "scribe_mcp",
            "--transport",
            "sse",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]

        with _managed_child_process(
            command,
            cwd=repo_root,
            env=child_env,
            log_path=tmp_path / "server.log",
        ) as child:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(health_url, timeout=0.25) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                raise AssertionError("child server did not become healthy before its deadline")
            assert child.poll() is None, (tmp_path / "server.log").read_text(encoding="utf-8")
            assert origin_path.exists(), (tmp_path / "server.log").read_text(encoding="utf-8")
            child_origins = json.loads(origin_path.read_text(encoding="utf-8"))
            assert child_origins["sdk_version"] == "2.3.0"
            assert Path(child_origins["server"]).is_relative_to(source_root)
            assert Path(child_origins["server_sse"]).is_relative_to(source_root)
            assert Path(child_origins["mcp"]).is_relative_to(Path(sys.prefix))

            async def exercise_client() -> tuple[list, list[bool]]:
                handles: list[str] = []
                protocol_sessions: list[bool] = []
                request_handles: list[str | None] = []
                progress_requests: list[dict] = []
                progress = asyncio.Event()
                progress_events: list[tuple[float, float | None, str | None]] = []
                http_client = None

                async def capture_request(request):
                    request_handles.append(request.headers.get("scribe-application-handle"))
                    try:
                        request_body = json.loads(request.content)
                    except (TypeError, ValueError):
                        return
                    if (
                        request_body.get("method") == "tools/call"
                        and request_body.get("params", {}).get("name") == "transport_progress_probe"
                    ):
                        progress_requests.append(request_body)

                async def capture_response(response):
                    nonlocal http_client
                    protocol_sessions.append("mcp-session-id" in response.headers)
                    handle = response.headers.get("scribe-application-handle")
                    if handle:
                        handles.append(handle)
                        http_client.headers["scribe-application-handle"] = handle

                async def on_progress(value, total, message):
                    progress_events.append((value, total, message))
                    progress.set()

                async def on_message(message):
                    if getattr(message, "method", None) != "notifications/progress":
                        return
                    params = message.params
                    progress_events.append((params.progress, params.total, params.message))
                    progress.set()

                http_client = httpx2.AsyncClient(
                    headers={"authorization": f"Bearer {token}"},
                    timeout=httpx2.Timeout(10),
                    event_hooks={"request": [capture_request], "response": [capture_response]},
                )
                async with http_client:
                    get_response = await http_client.get(endpoint)
                    delete_response = await http_client.delete(endpoint)
                    assert get_response.status_code == 405
                    assert delete_response.status_code == 405
                    assert get_response.headers["allow"] == "POST"
                    assert delete_response.headers["allow"] == "POST"
                    async with Client(
                        streamable_http_client(endpoint, http_client=http_client),
                        mode="2026-07-28",
                        cache=None,
                        message_handler=on_message,
                    ) as client:
                        discovery = await client.session.send_discover("2026-07-28")
                        assert discovery is not None
                        catalog = await client.list_tools()
                        names = {item.name for item in catalog.tools}
                        assert "read_file" in names
                        assert "transport_progress_probe" in names
                        progress_tool = next(item for item in catalog.tools if item.name == "transport_progress_probe")
                        assert set(progress_tool.input_schema["properties"]) == {"agent", "hold"}
                        read_file_tool = next(item for item in catalog.tools if item.name == "read_file")
                        assert "path" in read_file_tool.input_schema["required"]
                        assert "full" in read_file_tool.input_schema["properties"]["mode"]["enum"]
                        assert read_file_tool.input_schema["additionalProperties"] is True

                        binding = await client.call_tool(
                            "set_project",
                            {
                                "agent": test_agent,
                                "name": "transport_http_test",
                                "root": str(repo_root),
                            },
                        )
                        assert binding.is_error is False
                        assert request_handles[-1] == handles[0]
                        established_default = await http_client.post(
                            f"http://127.0.0.1:{port}/__test/establish-default"
                        )
                        assert established_default.status_code == 200
                        assert established_default.json()["default_project"] == "transport_http_test"

                        before_binding_sensitivity = await http_client.get(
                            f"http://127.0.0.1:{port}/__test/state"
                        )
                        assert before_binding_sensitivity.status_code == 200
                        before_binding_state = before_binding_sensitivity.json()
                        bound_rows_before = list(before_binding_state["session_bindings"].values())
                        assert bound_rows_before
                        before_binding_generation = max(
                            row["binding_generation"] for row in bound_rows_before
                        )
                        changed_binding = await client.call_tool(
                            "set_project",
                            {
                                "agent": test_agent,
                                "name": "transport_sensitivity_probe",
                                "root": str(repo_root),
                            },
                        )
                        assert changed_binding.is_error is False
                        changed_response = await http_client.get(
                            f"http://127.0.0.1:{port}/__test/state"
                        )
                        assert changed_response.status_code == 200
                        changed_state = changed_response.json()
                        changed_rows = list(changed_state["session_bindings"].values())
                        assert any(
                            row["project_name"] == "transport_sensitivity_probe"
                            and row["binding_generation"] > before_binding_generation
                            for row in changed_rows
                        ), (before_binding_state, changed_state)
                        restored_binding = await client.call_tool(
                            "set_project",
                            {
                                "agent": test_agent,
                                "name": "transport_http_test",
                                "root": str(repo_root),
                            },
                        )
                        assert restored_binding.is_error is False

                        file_result = await client.call_tool(
                            "read_file",
                            {"agent": test_agent, "path": str(sample), "mode": "full"},
                        )
                        assert file_result.is_error is False, (binding.content, file_result.content)
                        assert "real-child-http-proof" in "\n".join(
                            item.text for item in file_result.content if hasattr(item, "text")
                        )
                        structured_scan = await client.call_tool(
                            "read_file",
                            {
                                "agent": test_agent,
                                "path": str(sample),
                                "mode": "scan_only",
                                "format": "both",
                            },
                        )
                        assert structured_scan.is_error is False
                        assert structured_scan.structured_content["ok"] is True
                        assert sample.name in "\n".join(
                            item.text for item in structured_scan.content if hasattr(item, "text")
                        )
                        missing_file = await client.call_tool(
                            "read_file",
                            {
                                "agent": test_agent,
                                "path": str(repo_root / "missing.txt"),
                                "mode": "full",
                                "format": "both",
                            },
                        )
                        assert missing_file.is_error is False
                        assert missing_file.structured_content["ok"] is False
                        assert missing_file.structured_content["error"] == "file not found"

                        completed_progress = await client.call_tool(
                            "transport_progress_probe",
                            {"agent": test_agent},
                            progress_callback=on_progress,
                        )
                        assert completed_progress.is_error is False, completed_progress.content
                        assert "progress-result" in "\n".join(
                            item.text for item in completed_progress.content if hasattr(item, "text")
                        )
                        assert progress_events, progress_requests
                        assert progress_events[0][0] == 0.25
                        assert progress_events[-1][0] == 1

                        progress.clear()
                        progress_event_start = len(progress_events)
                        progress_call = asyncio.create_task(
                            client.call_tool(
                                "transport_progress_probe",
                                {"agent": test_agent, "hold": True},
                                progress_callback=on_progress,
                            )
                        )
                        await asyncio.wait_for(progress.wait(), timeout=5)
                        assert not progress_call.done(), "tool result completed before the release barrier"
                        release_response = await http_client.post(
                            f"http://127.0.0.1:{port}/__test/release-progress"
                        )
                        assert release_response.status_code == 200
                        released_progress = await asyncio.wait_for(progress_call, timeout=5)
                        assert released_progress.is_error is False
                        released_values = [
                            event[0] for event in progress_events[progress_event_start:]
                        ]
                        assert released_values[0] == 0.25 and released_values[-1] == 1

                        progress.clear()
                        cancelled_call = asyncio.create_task(
                            client.call_tool(
                                "transport_progress_probe",
                                {"agent": test_agent, "hold": True},
                                progress_callback=on_progress,
                            )
                        )
                        await asyncio.wait_for(progress.wait(), timeout=5)
                        assert not cancelled_call.done(), "cancellation probe completed before client disconnect"
                        cancelled_call.cancel()
                        try:
                            await cancelled_call
                        except asyncio.CancelledError:
                            pass
                        cancel_deadline = time.monotonic() + 5
                        cancelled_on_server = False
                        while time.monotonic() < cancel_deadline:
                            state_response = await http_client.get(
                                f"http://127.0.0.1:{port}/__test/state"
                            )
                            assert state_response.status_code == 200
                            handler_state = state_response.json()["progress_handler_counters"]
                            if handler_state["cancelled"] == 1 and handler_state["active"] == 0:
                                cancelled_on_server = True
                                break
                            await asyncio.sleep(0.05)
                        assert cancelled_on_server, handler_state
                    assert handles
                    assert all(not present for present in protocol_sessions)

                # A fresh SDK connection reuses the authentic application handle after stream closure.
                async with httpx2.AsyncClient(
                    headers={
                        "authorization": f"Bearer {token}",
                        "scribe-application-handle": handles[-1],
                    },
                    timeout=httpx2.Timeout(10),
                    event_hooks={"request": [capture_request], "response": [capture_response]},
                ) as reconnect_http:
                    http_client = reconnect_http
                    async with Client(
                        streamable_http_client(endpoint, http_client=reconnect_http),
                        mode="2026-07-28",
                        cache=None,
                    ) as client:
                        reconnect_catalog = await client.list_tools()
                        assert any(item.name == "read_file" for item in reconnect_catalog.tools)

                    async with httpx2.AsyncClient(
                        headers={"authorization": f"Bearer {token}"},
                        timeout=httpx2.Timeout(10),
                    ) as raw_client:
                        snapshot_url = f"http://127.0.0.1:{port}/__test/state"

                        async def snapshot():
                            response = await raw_client.get(snapshot_url)
                            assert response.status_code == 200
                            return response.json()

                        def state_without_identity_counter(value):
                            return {
                                **value,
                                "dispatch_counters": {
                                    key: count
                                    for key, count in value["dispatch_counters"].items()
                                    if key != "identity_resolutions"
                                },
                            }

                        current_version = "2026-07-28"
                        modern_meta = {
                            "io.modelcontextprotocol/protocolVersion": current_version,
                            "io.modelcontextprotocol/clientCapabilities": {},
                        }

                        def modern_request(method="tools/list", request_id=101, meta=None):
                            return {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "method": method,
                                "params": {"_meta": dict(modern_meta if meta is None else meta)},
                            }

                        def modern_headers(method="tools/list", version=current_version, accept="application/json, text/event-stream"):
                            headers = {
                                "authorization": f"Bearer {token}",
                                "mcp-method": method,
                                "accept": accept,
                            }
                            if version is not None:
                                headers["mcp-protocol-version"] = version
                            return headers

                        def require_unchanged_rejection(response, expected_status, before, after):
                            status_matches = response.status_code == expected_status
                            effect_free = after == before
                            assert status_matches and effect_free, (
                                f"Expected status {expected_status}, got {response.status_code}; "
                                f"snapshot unchanged={effect_free}: {response.text}"
                            )

                        sensitivity_control_counts = {
                            "restored_legacy_route": 0,
                            "bypassed_protocol_admission": 0,
                        }

                        legacy_control_before = await snapshot()
                        restored_route = await raw_client.post(
                            f"http://127.0.0.1:{port}/__test/sensitivity/restore-legacy"
                        )
                        assert restored_route.status_code == 200
                        restored_legacy_response = await raw_client.get(
                            f"http://127.0.0.1:{port}/sse"
                        )
                        restored_route_after = await snapshot()
                        sensitivity_control_counts["restored_legacy_route"] += 1
                        with pytest.raises(AssertionError, match="Expected status 404"):
                            require_unchanged_rejection(
                                restored_legacy_response,
                                404,
                                legacy_control_before,
                                restored_route_after,
                            )
                        assert (
                            restored_route_after["dispatch_counters"]["restored_legacy_route_dispatch"]
                            == legacy_control_before["dispatch_counters"]["restored_legacy_route_dispatch"] + 1
                        )
                        removed_route = await raw_client.post(
                            f"http://127.0.0.1:{port}/__test/sensitivity/remove-legacy"
                        )
                        assert removed_route.status_code == 200

                        admission_control_before = await snapshot()
                        bypassed_admission = await raw_client.post(
                            f"http://127.0.0.1:{port}/__test/sensitivity/bypass-protocol-admission"
                        )
                        assert bypassed_admission.status_code == 200
                        invalid_protocol_meta = {
                            "io.modelcontextprotocol/protocolVersion": "2025-11-25",
                            "io.modelcontextprotocol/clientCapabilities": {},
                        }
                        invalid_authenticated_protocol = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=130, meta=invalid_protocol_meta),
                            headers=modern_headers(version="2025-11-25"),
                        )
                        assert invalid_authenticated_protocol.request.headers.get("authorization") == f"Bearer {token}"
                        bypassed_admission_after = await snapshot()
                        sensitivity_control_counts["bypassed_protocol_admission"] += 1
                        assert (
                            bypassed_admission_after["dispatch_counters"]["identity_resolutions"]
                            == admission_control_before["dispatch_counters"]["identity_resolutions"] + 1
                        ), (admission_control_before, bypassed_admission_after)
                        assert (
                            bypassed_admission_after["application_handle_registry"]
                            != admission_control_before["application_handle_registry"]
                        )
                        with pytest.raises(AssertionError, match="snapshot unchanged=False"):
                            require_unchanged_rejection(
                                invalid_authenticated_protocol,
                                400,
                                admission_control_before,
                                bypassed_admission_after,
                            )
                        restored_admission = await raw_client.post(
                            f"http://127.0.0.1:{port}/__test/sensitivity/restore-protocol-admission"
                        )
                        assert restored_admission.status_code == 200
                        assert sensitivity_control_counts == {
                            "restored_legacy_route": 1,
                            "bypassed_protocol_admission": 1,
                        }

                        await asyncio.sleep(0.2)
                        before_rejections = await snapshot()
                        assert before_rejections["global_default_project"]["project_name"] == "transport_http_test"
                        assert "transport_http_test" in before_rejections["state_manager_caches"]["projects"]
                        assert before_rejections["state_manager_caches"]["session_projects"]
                        assert before_rejections["router_caches"]["stable_session_ids"]
                        assert before_rejections["lease_session_ids"]
                        assert before_rejections["session_bindings"]
                        bound_records = list(before_rejections["session_bindings"].values())
                        assert any(
                            row["project_name"] == "transport_http_test"
                            and row["project_key"]
                            and row["canonical_repo_root"] == str(repo_root)
                            and row["binding_generation"] > 0
                            for row in bound_records
                        ), bound_records
                        assert before_rejections["session_leases"]
                        assert before_rejections["application_handle_registry"]
                        assert any(
                            record["protocol_era"] == "modern"
                            and record["transport"] == "streamable-http"
                            and record["identity_key"]
                            and not record["revoked"]
                            for record in before_rejections["application_handle_registry"].values()
                        )
                        assert all(
                            handles[-1] not in json.dumps(record)
                            for record in before_rejections["application_handle_registry"].values()
                        )
                        sqlite_key = "runtime/scribe.sqlite3"
                        assert before_rejections["file_sha256"].get(sqlite_key)
                        assert before_rejections["file_sizes"].get(sqlite_key, 0) > 0
                        assert before_rejections["file_sha256"].get("repo/transport-proof.txt")
                        retired_paths = (
                            "/sse",
                            "/sse/",
                            "/sse?probe=retired",
                            "/sse/?probe=retired",
                            "/messages",
                            "/messages/",
                            "/messages?session_id=caller-selected",
                            "/messages/?session_id=caller-selected",
                        )
                        retired_responses = []
                        for path in retired_paths:
                            retired_responses.append(
                                await raw_client.get(f"http://127.0.0.1:{port}{path}")
                            )
                            retired_responses.append(
                                await raw_client.post(
                                    f"http://127.0.0.1:{port}{path}",
                                    json={"jsonrpc": "2.0", "id": 102, "method": "tools/list"},
                                )
                            )
                        for response in retired_responses:
                            assert response.status_code == 404, response.text
                            assert "mcp-session-id" not in response.headers
                            assert "scribe-application-handle" not in response.headers

                        unauthenticated_client = httpx2.AsyncClient(timeout=httpx2.Timeout(10))
                        async with unauthenticated_client:
                            unauthenticated = await unauthenticated_client.post(
                                endpoint,
                                json=modern_request(request_id=103),
                                headers={
                                    key: value
                                    for key, value in modern_headers().items()
                                    if key != "authorization"
                                },
                            )
                        assert unauthenticated.status_code == 401

                        invalid_origin = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=118),
                            headers={**modern_headers(), "origin": "https://untrusted.example"},
                        )
                        assert invalid_origin.status_code == 403
                        duplicate_origins = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=119),
                            headers=[
                                ("authorization", f"Bearer {token}"),
                                ("origin", "https://first.example"),
                                ("origin", "https://second.example"),
                                ("mcp-protocol-version", current_version),
                                ("mcp-method", "tools/list"),
                                ("accept", "application/json, text/event-stream"),
                            ],
                        )
                        assert duplicate_origins.status_code == 400
                        duplicate_auth_headers = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=120),
                            headers=[
                                ("authorization", f"Bearer {token}"),
                                ("authorization", f"Bearer {token}"),
                                ("mcp-protocol-version", current_version),
                                ("mcp-method", "tools/list"),
                                ("accept", "application/json, text/event-stream"),
                            ],
                        )
                        assert duplicate_auth_headers.status_code == 400

                        bad_origin = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=104),
                            headers={**modern_headers(), "origin": "https://untrusted.example"},
                        )
                        assert bad_origin.status_code == 403
                        multiple_origins = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=105),
                            headers=[
                                ("authorization", f"Bearer {token}"),
                                ("origin", "https://trusted-one.example"),
                                ("origin", "https://trusted-two.example"),
                                ("mcp-protocol-version", current_version),
                                ("mcp-method", "tools/list"),
                                ("accept", "application/json, text/event-stream"),
                            ],
                        )
                        assert multiple_origins.status_code == 400
                        duplicate_auth = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=106),
                            headers=[
                                ("authorization", f"Bearer {token}"),
                                ("authorization", f"Bearer {token}"),
                                ("mcp-protocol-version", current_version),
                                ("mcp-method", "tools/list"),
                                ("accept", "application/json, text/event-stream"),
                            ],
                        )
                        assert duplicate_auth.status_code == 400

                        old_initialize = await raw_client.post(
                            endpoint,
                            json={
                                "jsonrpc": "2.0",
                                "id": 107,
                                "method": "initialize",
                                "params": {
                                    "protocolVersion": "2025-11-25",
                                    "clientInfo": {"name": "obsolete-client", "version": "1"},
                                    "capabilities": {},
                                },
                            },
                            headers=modern_headers("initialize", "2025-11-25"),
                        )
                        assert old_initialize.status_code == 400
                        assert old_initialize.json()["error"]["code"] == -32022
                        current_initialize = await raw_client.post(
                            endpoint,
                            json={
                                "jsonrpc": "2.0",
                                "id": 108,
                                "method": "initialize",
                                "params": {
                                    "protocolVersion": current_version,
                                    "clientInfo": {"name": "current-client", "version": "1"},
                                    "capabilities": {},
                                },
                            },
                            headers=modern_headers("initialize"),
                        )
                        assert current_initialize.status_code == 400
                        assert current_initialize.json()["error"]["code"] == -32600
                        initialize_mismatch = await raw_client.post(
                            endpoint,
                            json={
                                "jsonrpc": "2.0",
                                "id": 109,
                                "method": "initialize",
                                "params": {
                                    "protocolVersion": "2025-11-25",
                                    "clientInfo": {"name": "mismatched-client", "version": "1"},
                                    "capabilities": {},
                                },
                            },
                            headers=modern_headers("initialize"),
                        )
                        assert initialize_mismatch.status_code == 400
                        assert initialize_mismatch.json()["error"]["code"] == -32020

                        unsupported_meta = {
                            "io.modelcontextprotocol/protocolVersion": "2025-11-25",
                            "io.modelcontextprotocol/clientCapabilities": {},
                        }
                        unsupported_revision = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=110, meta=unsupported_meta),
                            headers=modern_headers("tools/list", "2025-11-25"),
                        )
                        assert unsupported_revision.status_code == 400
                        assert unsupported_revision.json()["error"]["code"] == -32022
                        missing_version_header = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=111),
                            headers=modern_headers(version=None),
                        )
                        assert missing_version_header.status_code == 400
                        assert missing_version_header.json()["error"]["code"] == -32020
                        header_body_mismatch = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=112),
                            headers=modern_headers("tools/call"),
                        )
                        assert header_body_mismatch.status_code == 400
                        assert header_body_mismatch.json()["error"]["code"] == -32020
                        duplicate_routing_header = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=113),
                            headers=[
                                ("authorization", f"Bearer {token}"),
                                ("mcp-protocol-version", current_version),
                                ("mcp-protocol-version", current_version),
                                ("mcp-method", "tools/list"),
                                ("accept", "application/json, text/event-stream"),
                            ],
                        )
                        assert duplicate_routing_header.status_code == 400
                        assert duplicate_routing_header.json()["error"]["code"] == -32020
                        missing_capability = await raw_client.post(
                            endpoint,
                            json=modern_request(
                                request_id=114,
                                meta={"io.modelcontextprotocol/protocolVersion": current_version},
                            ),
                            headers=modern_headers(),
                        )
                        assert missing_capability.status_code == 400
                        assert missing_capability.json()["error"]["code"] == -32602
                        malformed_json = await raw_client.post(
                            endpoint,
                            content=b"{malformed",
                            headers={**modern_headers(), "content-type": "application/json"},
                        )
                        assert malformed_json.status_code == 400
                        assert malformed_json.json()["error"]["code"] == -32700
                        invalid_media = await raw_client.post(
                            endpoint,
                            content=b"{}",
                            headers={**modern_headers(), "content-type": "text/plain"},
                        )
                        assert invalid_media.status_code == 415
                        invalid_accept = await raw_client.post(
                            endpoint,
                            json=modern_request(request_id=115),
                            headers=modern_headers(accept="text/plain"),
                        )
                        assert invalid_accept.status_code == 406
                        invalid_notification = await raw_client.post(
                            endpoint,
                            json={
                                "jsonrpc": "2.0",
                                "method": "notifications/progress",
                                "params": {
                                    "_meta": {
                                        "io.modelcontextprotocol/protocolVersion": current_version,
                                    }
                                },
                            },
                            headers=modern_headers("notifications/progress"),
                        )
                        assert invalid_notification.status_code == 400
                        assert invalid_notification.content == b""
                        missing_application_handle = await raw_client.post(
                            endpoint,
                            json={
                                "jsonrpc": "2.0",
                                "id": 116,
                                "method": "tools/call",
                                "params": {
                                    "name": "read_file",
                                    "arguments": {"agent": test_agent, "path": str(sample), "mode": "full"},
                                    "_meta": modern_meta,
                                },
                            },
                            headers=modern_headers("tools/call") | {"mcp-name": "read_file"},
                        )
                        assert missing_application_handle.status_code == 401
                        assert missing_application_handle.json()["reason_code"] == "application_handle_required"
                        too_large = await raw_client.post(
                            endpoint,
                            content=b" " * (4 * 1024 * 1024 + 1),
                            headers={**modern_headers(), "content-type": "application/json"},
                        )
                        assert too_large.status_code == 413
                        assert too_large.json()["type"] == "RequestTooLarge"
                        after_rejections = await snapshot()
                        assert after_rejections == before_rejections

                        before_forged_handle = await snapshot()
                        forged_handle = await raw_client.post(
                            endpoint,
                            json={
                                "jsonrpc": "2.0",
                                "id": 117,
                                "method": "tools/call",
                                "params": {
                                    "name": "read_file",
                                    "arguments": {"agent": test_agent, "path": str(sample), "mode": "full"},
                                    "_meta": modern_meta,
                                },
                            },
                            headers=modern_headers("tools/call")
                            | {
                                "mcp-name": "read_file",
                                "scribe-application-handle": "caller-selected-handle",
                                "mcp-session-id": "caller-selected-session",
                                "x-agent-id": "forged-agent",
                                "x-request-id": "forged-request",
                            },
                        )
                        assert forged_handle.status_code == 401
                        assert forged_handle.json()["reason_code"] == "application_identity_denied"
                        after_forged_handle = await snapshot()
                        assert (
                            after_forged_handle["dispatch_counters"]["identity_resolutions"]
                            == before_forged_handle["dispatch_counters"]["identity_resolutions"] + 1
                        )
                        assert state_without_identity_counter(after_forged_handle) == state_without_identity_counter(
                            before_forged_handle
                        )

                assert progress_events, progress_requests
                assert progress_events[0][0] == 0.25
                assert progress_events[0][2] == "connected"
                assert all(not present for present in protocol_sessions)
                return progress_events, protocol_sessions

            progress_events, protocol_sessions = asyncio.run(exercise_client())
            assert progress_events
            assert protocol_sessions and not any(protocol_sessions)

        assert child.returncode is not None
        with pytest.raises((OSError, urllib.error.URLError)):
            urllib.request.urlopen(health_url, timeout=0.25)


class TestTransportFailureTaxonomy:
    def test_backend_operation_maps_stale_session_to_typed_response(self):
        import scribe_mcp.server_sse as sse_mod
        import scribe_mcp.server as server_mod

        backend = MagicMock()
        backend.set_agent_project = AsyncMock(
            side_effect=SessionLeaseExpired(
                "Session ID mismatch for agent AgentA",
                reason="session_mismatch",
                agent_id="AgentA",
                session_id="sess-123",
            )
        )

        app = Starlette(
            routes=[Route("/api/v1/backend/{operation}", sse_mod.handle_backend_operation, methods=["POST"])]
        )

        original_backend = server_mod.storage_backend
        try:
            server_mod.storage_backend = backend
            with patch(
                "scribe_mcp.server.begin_transport_operation",
                new=AsyncMock(return_value="running"),
            ), patch(
                "scribe_mcp.server.end_transport_operation",
                new=AsyncMock(),
            ):
                with TestClient(app, raise_server_exceptions=False) as client:
                    response = client.post("/api/v1/backend/set_agent_project", json={})
        finally:
            server_mod.storage_backend = original_backend

        assert response.status_code == 409
        body = response.json()
        assert body["type"] == "StaleSession"
        assert body["stale_session_reason"] == "session_mismatch"
        assert body["agent_id"] == "AgentA"
        assert body["session_id"] == "sess-123"

    def test_shutdown_phase_reports_draining_before_transport_closed(self):
        import scribe_mcp.server_sse as sse_mod
        import scribe_mcp.server as server_mod

        app = Starlette(
            routes=[Route("/api/v1/backend/{operation}", sse_mod.handle_backend_operation, methods=["POST"])]
        )

        original_backend = server_mod.storage_backend
        try:
            server_mod.storage_backend = MagicMock()
            with patch(
                "scribe_mcp.server.begin_transport_operation",
                new=AsyncMock(return_value="draining"),
            ):
                with TestClient(app, raise_server_exceptions=False) as client:
                    draining = client.post("/api/v1/backend/list_projects", json={})
            with patch(
                "scribe_mcp.server.begin_transport_operation",
                new=AsyncMock(return_value="backend_close"),
            ):
                with TestClient(app, raise_server_exceptions=False) as client:
                    closed = client.post("/api/v1/backend/list_projects", json={})
        finally:
            server_mod.storage_backend = original_backend

        assert draining.status_code == 503
        assert draining.json()["type"] == "TransportDraining"
        assert closed.status_code == 503
        assert closed.json()["type"] == "TransportClosed"


class TestCLIArgumentParsing:
    """Verify --transport, --port, --host arguments work correctly."""

    def test_default_transport_is_stdio(self):
        from scribe_mcp.__main__ import _parse_args
        # Clear env vars to test defaults
        env_backup = {k: os.environ.pop(k) for k in
                      ["SCRIBE_TRANSPORT", "SCRIBE_TRANSPORT_PORT", "SCRIBE_TRANSPORT_HOST"]
                      if k in os.environ}
        try:
            args = _parse_args([])
            assert args.transport == "stdio"
        finally:
            os.environ.update(env_backup)

    def test_default_port_is_8200(self):
        from scribe_mcp.__main__ import _parse_args
        env_backup = {k: os.environ.pop(k) for k in
                      ["SCRIBE_TRANSPORT_PORT"] if k in os.environ}
        try:
            args = _parse_args([])
            assert args.port == 8200
        finally:
            os.environ.update(env_backup)

    def test_default_host_is_loopback_safe(self):
        from scribe_mcp.__main__ import _parse_args
        env_backup = {k: os.environ.pop(k) for k in
                      ["SCRIBE_TRANSPORT_HOST"] if k in os.environ}
        try:
            args = _parse_args([])
            assert args.host == "127.0.0.1"
        finally:
            os.environ.update(env_backup)

    def test_transport_sse_flag(self):
        from scribe_mcp.__main__ import _parse_args
        args = _parse_args(["--transport", "sse"])
        assert args.transport == "sse"

    def test_transport_stdio_flag(self):
        from scribe_mcp.__main__ import _parse_args
        args = _parse_args(["--transport", "stdio"])
        assert args.transport == "stdio"

    def test_port_override(self):
        from scribe_mcp.__main__ import _parse_args
        args = _parse_args(["--port", "9999"])
        assert args.port == 9999

    def test_host_override(self):
        from scribe_mcp.__main__ import _parse_args
        args = _parse_args(["--host", "127.0.0.1"])
        assert args.host == "127.0.0.1"

    def test_combined_flags(self):
        from scribe_mcp.__main__ import _parse_args
        args = _parse_args(["--transport", "sse", "--port", "4567", "--host", "10.0.0.1"])
        assert args.transport == "sse"
        assert args.port == 4567
        assert args.host == "10.0.0.1"

    def test_invalid_transport_rejected(self):
        from scribe_mcp.__main__ import _parse_args
        with pytest.raises(SystemExit):
            _parse_args(["--transport", "websocket"])


class TestCLIEnvironmentVariables:
    """Verify environment variable fallbacks work."""

    def test_scribe_transport_env_var(self):
        from scribe_mcp.__main__ import _parse_args
        with patch.dict(os.environ, {"SCRIBE_TRANSPORT": "sse"}):
            args = _parse_args([])
            assert args.transport == "sse"

    def test_scribe_transport_port_env_var(self):
        from scribe_mcp.__main__ import _parse_args
        with patch.dict(os.environ, {"SCRIBE_TRANSPORT_PORT": "3000"}):
            args = _parse_args([])
            assert args.port == 3000

    def test_scribe_transport_host_env_var(self):
        from scribe_mcp.__main__ import _parse_args
        with patch.dict(os.environ, {"SCRIBE_TRANSPORT_HOST": "10.0.0.5"}):
            args = _parse_args([])
            assert args.host == "10.0.0.5"

    def test_cli_flag_overrides_env_var(self):
        """Explicit CLI flags should override environment variables."""
        from scribe_mcp.__main__ import _parse_args
        with patch.dict(os.environ, {"SCRIBE_TRANSPORT": "sse", "SCRIBE_TRANSPORT_PORT": "3000"}):
            args = _parse_args(["--transport", "stdio", "--port", "5555"])
            assert args.transport == "stdio"
            assert args.port == 5555


class TestCLIMainFunction:
    """Verify that main() dispatches correctly based on transport."""

    def test_stdio_calls_server_main(self):
        from scribe_mcp.__main__ import main

        mock_server_main = MagicMock(return_value="server-main-coro")
        with patch("scribe_mcp.__main__.asyncio") as mock_asyncio, \
             patch("scribe_mcp.server.main", mock_server_main):
            main(["--transport", "stdio"])
            # asyncio.run should be called once with a coroutine from server_main
            mock_asyncio.run.assert_called_once()
            call_args = mock_asyncio.run.call_args
            # The argument to asyncio.run should be the result of server_main()
            assert call_args is not None

    def test_sse_lazy_imports_run_sse(self):
        from scribe_mcp.__main__ import main

        mock_run_sse = MagicMock(return_value="run-sse-coro")

        with patch("scribe_mcp.__main__.asyncio") as mock_asyncio, \
             patch("scribe_mcp.server_sse.run_sse", mock_run_sse):
            main(["--transport", "sse", "--port", "8200", "--host", "0.0.0.0"])
            # asyncio.run should be called with the result of run_sse(...)
            mock_asyncio.run.assert_called_once()


# ---------------------------------------------------------------------------
# Task 1.3: pyproject.toml entry point test
# ---------------------------------------------------------------------------

class TestPyprojectEntryPoints:
    """Verify that pyproject.toml has the correct entry points."""

    def test_scribe_server_sse_entry_point_exists(self):
        """pyproject.toml should have scribe-server-sse entry point."""
        import tomllib
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)

        scripts = config.get("project", {}).get("scripts", {})
        assert "scribe-server-sse" in scripts, (
            f"Missing scribe-server-sse in [project.scripts]. Found: {list(scripts.keys())}"
        )
        assert scripts["scribe-server-sse"] == "scribe_mcp.server_sse:main"

    def test_existing_scribe_mcp_entry_point_preserved(self):
        """Existing scribe-mcp entry point must not be modified."""
        import tomllib
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)

        scripts = config.get("project", {}).get("scripts", {})
        assert "scribe-mcp" in scripts
        assert scripts["scribe-mcp"] == "scribe_mcp.__main__:main"

    def test_no_new_dependencies_added(self):
        """starlette/uvicorn must NOT be added as explicit dependencies."""
        import tomllib
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)

        deps = config.get("project", {}).get("dependencies", [])
        dep_names = [d.split("~")[0].split("=")[0].split(">")[0].split("<")[0].strip()
                     for d in deps]

        assert "starlette" not in dep_names, "starlette should not be an explicit dependency"
        assert "uvicorn" not in dep_names, "uvicorn should not be an explicit dependency"
