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
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the src directory is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


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
    """Verify the Starlette app is constructed with correct routes."""

    @pytest.mark.asyncio
    async def test_run_sse_creates_starlette_app(self):
        """run_sse should create a Starlette app with /health, /sse, /messages/ routes."""
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount

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
            await run_sse(host="127.0.0.1", port=9999)

        mock_startup.assert_called_once()
        assert captured_app is not None

        # Check routes
        route_paths = []
        for route in captured_app.routes:
            if hasattr(route, "path"):
                route_paths.append(route.path)

        assert "/health" in route_paths, f"Missing /health route in {route_paths}"
        assert "/sse" in route_paths, f"Missing /sse route in {route_paths}"
        # Starlette's Mount normalises trailing slashes; /messages/ becomes /messages
        assert any(p.rstrip("/") == "/messages" for p in route_paths), (
            f"Missing /messages route in {route_paths}"
        )

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
            await run_sse(host="192.168.1.1", port=7777)

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
            await run_sse()

            async with captured_app.router.lifespan_context(captured_app):
                pass

            mock_shutdown.assert_awaited_once()


# ---------------------------------------------------------------------------
# Task 1.2: __main__.py CLI tests
# ---------------------------------------------------------------------------

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

    def test_default_host_is_all_interfaces(self):
        from scribe_mcp.__main__ import _parse_args
        env_backup = {k: os.environ.pop(k) for k in
                      ["SCRIBE_TRANSPORT_HOST"] if k in os.environ}
        try:
            args = _parse_args([])
            assert args.host == "0.0.0.0"
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

        with patch("scribe_mcp.__main__.asyncio") as mock_asyncio, \
             patch("scribe_mcp.__main__.server_main") as mock_server_main:
            main(["--transport", "stdio"])
            # asyncio.run should be called once with a coroutine from server_main
            mock_asyncio.run.assert_called_once()
            call_args = mock_asyncio.run.call_args
            # The argument to asyncio.run should be the result of server_main()
            assert call_args is not None

    def test_sse_lazy_imports_run_sse(self):
        from scribe_mcp.__main__ import main

        mock_run_sse = AsyncMock()

        with patch("scribe_mcp.__main__.asyncio") as mock_asyncio, \
             patch.dict("sys.modules", {}), \
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
