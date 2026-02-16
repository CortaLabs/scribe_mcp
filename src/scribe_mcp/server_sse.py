"""SSE transport entry point for Scribe MCP server.

Wraps the existing MCP Server instance (``app``) with an SSE transport
using ``mcp.server.sse.SseServerTransport`` and exposes it via a
Starlette ASGI application served by uvicorn.

Endpoints
---------
- ``/health``    -- JSON health check for Docker HEALTHCHECK
- ``/sse``       -- SSE stream (MCP client connects here)
- ``/messages/`` -- POST target for MCP client messages

Usage::

    # Programmatic
    import asyncio
    from scribe_mcp.server_sse import run_sse
    asyncio.run(run_sse(host="0.0.0.0", port=8200))

    # CLI
    python -m scribe_mcp --transport sse --port 8200
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
import uvicorn

from scribe_mcp.server import app, _startup, _shutdown

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_server_start_time: float | None = None


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

async def health_check(request: Request) -> JSONResponse:
    """HTTP health endpoint for Docker HEALTHCHECK.

    Returns a JSON object with service status, version, transport type,
    and uptime in seconds.  If the server can respond, it is healthy.
    """
    return JSONResponse({
        "status": "healthy",
        "service": "scribe-mcp",
        "version": "2.2",
        "transport": "sse",
        "uptime_seconds": int(time.time() - _server_start_time) if _server_start_time else 0,
    })


# ---------------------------------------------------------------------------
# SSE transport runner
# ---------------------------------------------------------------------------

async def run_sse(host: str = "0.0.0.0", port: int = 8200) -> None:
    """Run the MCP server over SSE transport.

    Parameters
    ----------
    host:
        Network interface to bind to.  Defaults to ``0.0.0.0`` (all
        interfaces) for container deployments.
    port:
        TCP port to listen on.  Defaults to ``8200``.

    The function performs the following steps:

    1. Calls ``_startup()`` to initialise storage, background tasks, etc.
       (same initialisation path as stdio mode in ``server.py``).
    2. Creates an ``SseServerTransport`` instance for ``/messages/``.
    3. Builds a Starlette ASGI application with health, SSE, and message
       routes.
    4. Runs the application via uvicorn until interrupted.
    """
    global _server_start_time

    # Initialise server (same as stdio path in server.py)
    await _startup()
    _server_start_time = time.time()

    logger.info("Scribe MCP SSE transport starting on %s:%d", host, port)

    # Create SSE transport -- ``/messages/`` is the path where clients POST
    # their MCP messages.
    sse_transport = SseServerTransport("/messages/")

    # SSE connection handler.
    #
    # ``SseServerTransport.connect_sse`` manages the SSE response stream
    # directly through the ASGI ``send`` callable (accessed via the
    # semi-private ``request._send``).  After the connection closes we
    # return an empty ``Response`` so that Starlette's
    # ``request_response`` wrapper does not raise ``TypeError`` when the
    # handler returns ``None``.  This pattern matches the MCP SDK's own
    # recommended usage (see ``mcp.server.sse`` module docstring).
    async def handle_sse(request: Request) -> Response:
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send,
        ) as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
        return Response()

    # Build the Starlette application -----------------------------------
    starlette_app = Starlette(
        routes=[
            Route("/health", health_check),
            Route("/sse", handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ],
        on_shutdown=[_shutdown],
    )

    # Run uvicorn -------------------------------------------------------
    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


# ---------------------------------------------------------------------------
# Direct entry point (used by ``scribe-server-sse`` console script)
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the ``scribe-server-sse`` console script."""
    asyncio.run(run_sse())


if __name__ == "__main__":
    main()
