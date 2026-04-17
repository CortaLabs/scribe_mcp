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
    asyncio.run(run_sse(host="127.0.0.1", port=8200, auth_token="change-me"))

    # CLI
    python -m scribe_mcp --transport sse --port 8200
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import dataclasses
import datetime
import logging
import secrets
import time
from typing import Any

from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
import uvicorn

import scribe_mcp.server as server_module
from scribe_mcp.config.settings import Settings
from scribe_mcp.server import app, _startup, _shutdown
from scribe_mcp.storage.base import ProjectRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_server_start_time: float | None = None
_AUTH_EXEMPT_PATHS: frozenset[str] = frozenset({"/health"})


def _resolve_transport_runtime(
    host: str | None,
    port: int | None,
    auth_token: str | None,
) -> tuple[Settings, server_module.TransportPolicy, str]:
    runtime_settings = Settings.load()
    resolved_host = (host or runtime_settings.transport_host).strip() or runtime_settings.transport_host
    resolved_port = int(port if port is not None else runtime_settings.transport_port)
    resolved_auth_token = (auth_token or runtime_settings.transport_auth_token or "").strip()
    policy = server_module.build_transport_policy(
        transport="sse",
        host=resolved_host,
        port=resolved_port,
        auth_required=True,
        auth_configured=bool(resolved_auth_token),
        allow_outside_repo_reads=runtime_settings.allow_outside_repo_reads,
    )
    if not resolved_auth_token:
        raise RuntimeError(
            "SSE/REST transport requires SCRIBE_TRANSPORT_AUTH_TOKEN (or auth_token=...) so "
            "network requests cannot reach the server anonymously."
        )
    return runtime_settings, policy, resolved_auth_token


def _extract_request_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        candidate = auth_header[7:].strip()
        if candidate:
            return candidate
    header_token = request.headers.get("x-scribe-auth", "").strip()
    return header_token or None


def _request_is_authenticated(request: Request, expected_token: str) -> bool:
    candidate = _extract_request_token(request)
    if candidate is None:
        return False
    return secrets.compare_digest(candidate, expected_token)


def _unauthorized_response() -> JSONResponse:
    return JSONResponse(
        {
            "error": "Missing or invalid transport auth token",
            "type": "Unauthorized",
        },
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


class TransportAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, expected_auth_token: str) -> None:
        super().__init__(app)
        self._expected_auth_token = expected_auth_token

    async def dispatch(self, request: Request, call_next):
        if request.url.path not in _AUTH_EXEMPT_PATHS and not _request_is_authenticated(
            request,
            self._expected_auth_token,
        ):
            return _unauthorized_response()
        return await call_next(request)


# ---------------------------------------------------------------------------
# REST API: operation allowlist
# ---------------------------------------------------------------------------

#: Legacy allowlist of StorageBackend methods exposed via REST for non-public profiles.
#: Operations NOT in this set are rejected with HTTP 403 Forbidden.
_LEGACY_OPERATION_ALLOWLIST: frozenset[str] = frozenset({
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

#: Explicit denied operations for public-release transport hardening.
PUBLIC_RELEASE_DENIED_OPERATIONS: frozenset[str] = frozenset({
    "delete_project",
    "upsert_project",
    "upsert_session",
    "set_session_mode",
    "set_session_project",
    "get_or_create_agent_session",
    "end_session",
    "record_doc_change",
    "clear_reminder_history",
    "cleanup_old_entries",
})

#: Minimal allowlist for public-release transport.
PUBLIC_RELEASE_ALLOWED_OPERATIONS: frozenset[str] = frozenset({
    "health",
    "resolve_project_context",
    "list_projects",
    "query_entries",
    "read_recent",
})

# Backwards-compatible symbol used in existing tests/import sites.
OPERATION_ALLOWLIST: frozenset[str] = _LEGACY_OPERATION_ALLOWLIST


def _is_public_release_transport() -> bool:
    settings = Settings.load()
    return bool(getattr(settings, "public_release", False))


def _operation_is_permitted(operation: str, *, public_release: bool) -> bool:
    if public_release:
        if operation in PUBLIC_RELEASE_DENIED_OPERATIONS:
            return False
        return operation in PUBLIC_RELEASE_ALLOWED_OPERATIONS
    return operation in _LEGACY_OPERATION_ALLOWLIST


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
    public_release_transport = _is_public_release_transport()

    # Guard: allowlist check
    if not _operation_is_permitted(operation, public_release=public_release_transport):
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
    public_release_transport = _is_public_release_transport()
    if public_release_transport:
        batch_ops = [
            item.get("op")
            for item in operations
            if isinstance(item, dict) and isinstance(item.get("op"), str)
        ]
        denied_in_batch = sorted({op for op in batch_ops if op in PUBLIC_RELEASE_DENIED_OPERATIONS})
        if denied_in_batch:
            denied_text = ", ".join(denied_in_batch)
            return JSONResponse(
                {
                    "error": (
                        "Batch rejected: contains denied operation(s): "
                        f"{denied_text}. Public release fails closed with no partial execution."
                    ),
                    "type": "ForbiddenOperation",
                },
                status_code=403,
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
        if not _operation_is_permitted(op_name, public_release=public_release_transport):
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

def _build_starlette_app(
    *,
    sse_transport: SseServerTransport,
    expected_auth_token: str,
) -> Starlette:
    # ``SseServerTransport.connect_sse`` manages the SSE response stream
    # directly through the ASGI ``send`` callable (accessed via the
    # semi-private ``request._send``). After the connection closes we return an
    # empty ``Response`` so Starlette's ``request_response`` wrapper does not
    # raise ``TypeError`` when the handler returns ``None``.
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

    @asynccontextmanager
    async def lifespan(_: Starlette):
        try:
            yield
        finally:
            await _shutdown()

    starlette_app = Starlette(
        routes=[
            Route("/health", health_check),
            Route("/sse", handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
            Route("/api/v1/backend/{operation}", handle_backend_operation, methods=["POST"]),
            Route("/api/v1/batch", handle_batch, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
    starlette_app.add_middleware(
        TransportAuthMiddleware,
        expected_auth_token=expected_auth_token,
    )

    return starlette_app


async def run_sse(
    host: str | None = None,
    port: int | None = None,
    auth_token: str | None = None,
) -> None:
    """Run the MCP server over SSE transport.

    Parameters
    ----------
    host:
        Network interface to bind to. Defaults to the configured transport host,
        which is loopback-safe unless explicitly overridden.
    port:
        TCP port to listen on. Defaults to the configured transport port.
    auth_token:
        Application-layer token required for ``/sse``, ``/messages/``, and
        ``/api/v1/*``. Defaults to ``SCRIBE_TRANSPORT_AUTH_TOKEN``.

    The function performs the following steps:

    1. Calls ``_startup()`` to initialise storage, background tasks, etc.
       (same initialisation path as stdio mode in ``server.py``).
    2. Creates an ``SseServerTransport`` instance for ``/messages/``.
    3. Builds a Starlette ASGI application with health, SSE, and message
       routes.
    4. Runs the application via uvicorn until interrupted.
    """
    global _server_start_time

    _, policy, resolved_auth_token = _resolve_transport_runtime(host, port, auth_token)
    server_module.set_transport_policy(policy)

    # Initialise server (same as stdio path in server.py)
    await _startup()
    _server_start_time = time.time()

    logger.info(
        "Scribe MCP SSE transport starting on %s:%d (network_exposed=%s)",
        policy.bind_host,
        policy.port,
        policy.network_exposed,
    )

    # Create SSE transport -- ``/messages/`` is the path where clients POST
    # their MCP messages.
    sse_transport = SseServerTransport("/messages/")

    # Build the Starlette application -----------------------------------
    starlette_app = _build_starlette_app(
        sse_transport=sse_transport,
        expected_auth_token=resolved_auth_token,
    )

    # Run uvicorn -------------------------------------------------------
    config = uvicorn.Config(
        starlette_app,
        host=policy.bind_host,
        port=policy.port,
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
