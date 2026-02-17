"""SSE transport entry point for Scribe MCP server.

Wraps the existing MCP Server instance (``app``) with an SSE transport
using ``mcp.server.sse.SseServerTransport`` and exposes it via a
Starlette ASGI application served by uvicorn.

Endpoints
---------
- ``/health``                        -- JSON health check for Docker HEALTHCHECK
- ``/sse``                           -- SSE stream (MCP client connects here)
- ``/messages/``                     -- POST target for MCP client messages
- ``/api/v1/backend/{operation}``    -- Proxy a single StorageBackend operation (POST)
- ``/api/v1/batch``                  -- Execute multiple StorageBackend operations (POST)

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
import dataclasses
import datetime
import logging
import time
from typing import Any

from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
import uvicorn

import scribe_mcp.server as server_module
from scribe_mcp.server import app, _startup, _shutdown
from scribe_mcp.storage.base import ProjectRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_server_start_time: float | None = None


# ---------------------------------------------------------------------------
# REST API: operation allowlist
# ---------------------------------------------------------------------------

#: Explicit allowlist of StorageBackend methods exposed via REST.
#: Operations NOT in this set are rejected with HTTP 403 Forbidden.
OPERATION_ALLOWLIST: frozenset[str] = frozenset({
    # Project operations
    "fetch_project",
    "upsert_project",
    "list_projects",
    "list_projects_by_repo",
    "delete_project",
    "update_project_docs",
    # Entry operations
    "insert_entry",
    "fetch_recent_entries",
    "fetch_recent_entries_paginated",
    "count_entries",
    "query_entries",
    "query_entries_paginated",
    "count_query_entries",
    # Session operations
    "upsert_session",
    "set_session_mode",
    "get_session_mode",
    "set_session_project",
    "get_session_project",
    "get_session_by_transport",
    "upsert_agent_session",
    "upsert_agent_recent_project",
    "get_or_create_agent_session",
    "heartbeat_session",
    "end_session",
    "update_session_activity",
    "get_session_activity",
    "get_agent_project",
    "set_agent_project",
    # Dev plan operations
    "upsert_dev_plan",
    # Doc tracking
    "record_doc_change",
    "record_agent_report_card",
    # Reminder operations
    "get_reminder_history",
    "clear_reminder_history",
    # Maintenance
    "cleanup_old_entries",
})


# ---------------------------------------------------------------------------
# REST API: serialisation helper
# ---------------------------------------------------------------------------

def _serialize(obj: Any) -> Any:
    """Recursively serialise StorageBackend return values to JSON-safe types.

    Handles:
    - dataclasses (e.g. ProjectRecord) → dict
    - datetime → ISO 8601 string
    - tuple → list  (for paginated result pairs)
    - dict / list / str / int / float / bool / None → pass-through
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            k: _serialize(v)
            for k, v in dataclasses.asdict(obj).items()
        }
    if isinstance(obj, tuple):
        return [_serialize(item) for item in obj]
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    # Fallback: attempt str conversion for unknown types
    return str(obj)


def _rehydrate_kwargs(kwargs: dict[str, Any]) -> None:
    """Deserialise JSON-transported kwargs back into Python objects.

    The RemoteStorageBackend client serialises rich types for transport:
    - ProjectRecord → dict with "name"/"id" keys
    - datetime → ISO 8601 string

    Backend methods expect real Python objects, so we reconstruct them here.
    """
    # ProjectRecord
    proj = kwargs.get("project")
    if isinstance(proj, dict) and "name" in proj:
        kwargs["project"] = ProjectRecord(
            id=proj.get("id"),
            name=proj["name"],
            repo_root=proj.get("repo_root", ""),
            progress_log_path=proj.get("progress_log_path", ""),
            docs_json=proj.get("docs_json"),
            created_at=proj.get("created_at"),
            updated_at=proj.get("updated_at"),
            bridge_id=proj.get("bridge_id"),
            bridge_managed=proj.get("bridge_managed", False),
        )

    # datetime (ts field from insert_entry)
    ts_val = kwargs.get("ts")
    if isinstance(ts_val, str):
        try:
            kwargs["ts"] = datetime.datetime.fromisoformat(ts_val)
        except (ValueError, TypeError):
            pass


# ---------------------------------------------------------------------------
# REST API: backend operation endpoints
# ---------------------------------------------------------------------------

async def handle_backend_operation(request: Request) -> JSONResponse:
    """Proxy a single StorageBackend method call.

    Route: POST /api/v1/backend/{operation}

    Request body (JSON)::

        {"arg1": value1, "arg2": value2, ...}

    Response (success)::

        {"result": <serialised return value>}

    Response (error)::

        {"error": "<message>", "type": "<ExceptionClassName>"}
    """
    operation: str = request.path_params["operation"]

    # Guard: allowlist check
    if operation not in OPERATION_ALLOWLIST:
        return JSONResponse(
            {"error": f"Operation '{operation}' is not permitted", "type": "ForbiddenOperation"},
            status_code=403,
        )

    # Guard: backend availability
    backend = getattr(server_module, "storage_backend", None)
    if backend is None:
        return JSONResponse(
            {"error": "Storage backend not yet initialised", "type": "ServiceUnavailable"},
            status_code=503,
        )

    # Resolve the method
    method = getattr(backend, operation, None)
    if method is None or not callable(method):
        return JSONResponse(
            {"error": f"Operation '{operation}' not found on backend", "type": "NotFound"},
            status_code=404,
        )

    # Parse kwargs from request body
    try:
        body: dict[str, Any] = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    # Deserialize ProjectRecord from dict if needed
    _rehydrate_kwargs(body)

    # Execute
    try:
        result = await method(**body)
        return JSONResponse({"result": _serialize(result)})
    except Exception as exc:
        return JSONResponse(
            {"error": str(exc), "type": type(exc).__name__},
            status_code=500,
        )


async def handle_batch(request: Request) -> JSONResponse:
    """Execute multiple StorageBackend method calls sequentially.

    Route: POST /api/v1/batch

    Request body (JSON)::

        {
            "operations": [
                {"op": "fetch_project", "args": {"name": "my_project"}},
                {"op": "insert_entry",  "args": {...}}
            ]
        }

    Response::

        {
            "results": [
                {"ok": true,  "result": ...},
                {"ok": false, "error": "...", "type": "..."}
            ]
        }

    Each operation is executed independently.  A failure in one operation
    does not abort subsequent operations (partial success semantics).
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Invalid JSON body", "type": "ParseError"},
            status_code=400,
        )

    operations = body.get("operations")
    if not isinstance(operations, list):
        return JSONResponse(
            {"error": "'operations' must be a list", "type": "ValidationError"},
            status_code=400,
        )

    backend = getattr(server_module, "storage_backend", None)
    if backend is None:
        return JSONResponse(
            {"error": "Storage backend not yet initialised", "type": "ServiceUnavailable"},
            status_code=503,
        )

    results: list[dict[str, Any]] = []

    for item in operations:
        if not isinstance(item, dict):
            results.append({"ok": False, "error": "Operation entry must be a dict", "type": "ValidationError"})
            continue

        op_name: str = item.get("op", "")
        args: dict[str, Any] = item.get("args", {})
        if not isinstance(args, dict):
            args = {}

        # Allowlist check per operation
        if op_name not in OPERATION_ALLOWLIST:
            results.append({
                "ok": False,
                "error": f"Operation '{op_name}' is not permitted",
                "type": "ForbiddenOperation",
            })
            continue

        method = getattr(backend, op_name, None)
        if method is None or not callable(method):
            results.append({
                "ok": False,
                "error": f"Operation '{op_name}' not found on backend",
                "type": "NotFound",
            })
            continue

        try:
            _rehydrate_kwargs(args)
            result = await method(**args)
            results.append({"ok": True, "result": _serialize(result)})
        except Exception as exc:
            results.append({"ok": False, "error": str(exc), "type": type(exc).__name__})

    return JSONResponse({"results": results})


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
            Route("/api/v1/backend/{operation}", handle_backend_operation, methods=["POST"]),
            Route("/api/v1/batch", handle_batch, methods=["POST"]),
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
