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
- ``/api/v1/tools/invoke``           -- Invoke a registered tool through server pipeline (POST)

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
import contextvars
import dataclasses
import datetime
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any

from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
import uvicorn

import scribe_mcp.server as server_module
from scribe_mcp.config.settings import Settings
from scribe_mcp.mcp_adapter import MCPCompatibilityPolicy, ProtocolEra
from scribe_mcp.server import app, _startup, _shutdown
from scribe_mcp.shared.execution_context import (
    ApplicationIdentity,
    resolve_application_identity,
)
from scribe_mcp.state.agent_manager import SessionLeaseExpired
from scribe_mcp.storage.base import ProjectRecord
from scribe_mcp.storage.models import ApplyPreviewReceiptRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_server_start_time: float | None = None
_AUTH_EXEMPT_PATHS: frozenset[str] = frozenset({"/health"})
_MODERN_PATH = "/mcp"
_LEGACY_ENDPOINTS: frozenset[str] = frozenset({"/sse", "/messages", "/messages/"})
DOWNGRADE_REASONS: frozenset[str] = frozenset(
    {"explicit_legacy_mode", "recognized_legacy_endpoint"}
)
_APPLICATION_HANDLE_HEADER = "scribe-application-handle"
_INGRESS_PRINCIPAL_SECRET = secrets.token_bytes(32)


@dataclasses.dataclass(frozen=True, slots=True)
class _IngressRequestIdentity:
    principal_id: str
    protocol_era: ProtocolEra
    transport: str
    application_identity: ApplicationIdentity


_INGRESS_REQUEST_IDENTITY: contextvars.ContextVar[_IngressRequestIdentity | None] = (
    contextvars.ContextVar("scribe_ingress_request_identity", default=None)
)


class _IngressRequestContextProxy:
    """Expose only server-attached ingress identity to the tool chokepoint."""

    def __getattr__(self, name: str) -> Any:
        attached = _INGRESS_REQUEST_IDENTITY.get()
        if attached is None or name not in {
            "principal_id",
            "protocol_era",
            "transport",
            "application_identity",
        }:
            raise AttributeError(name)
        return getattr(attached, name)


# ``tool_runtime`` consumes this server-owned seam. The proxy is context-local,
# so concurrent requests never share identity attributes.
app.request_context = _IngressRequestContextProxy()


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


def _typed_ingress_response(
    *,
    status_code: int,
    error_type: str,
    message: str,
    reason_code: str,
) -> JSONResponse:
    return JSONResponse(
        {
            "error": message,
            "type": error_type,
            "reason_code": reason_code,
        },
        status_code=status_code,
    )


def _typed_mcp_rejection(
    request: Request,
    payload: Any | None,
    *,
    status_code: int,
    error_type: str,
    message: str,
    reason_code: str,
    jsonrpc_code: int,
    data: dict[str, Any] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": jsonrpc_code, "message": message}
    if data is not None:
        error["data"] = data
    request_id = payload.get("id") if isinstance(payload, dict) else None
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error,
            "type": error_type,
            "reason_code": reason_code,
        },
        status_code=status_code,
    )


def _request_json_payload(request: Request, raw_body: bytes) -> tuple[Any | None, JSONResponse | None]:
    if not raw_body:
        return None, None
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return None, _typed_ingress_response(
            status_code=415,
            error_type="UnsupportedMediaType",
            message="Request body must use application/json",
            reason_code="unsupported_media_type",
        )
    try:
        return json.loads(raw_body), None
    except (ValueError, RecursionError):
        if request.url.path.rstrip("/") == _MODERN_PATH:
            return None, _typed_mcp_rejection(
                request,
                None,
                status_code=400,
                error_type="ParseError",
                message="Malformed JSON request body",
                reason_code="malformed_request",
                jsonrpc_code=-32700,
            )
        return None, _typed_ingress_response(
            status_code=400,
            error_type="ParseError",
            message="Malformed JSON request body",
            reason_code="malformed_request",
        )


def _protocol_rejection(
    request: Request,
    payload: Any | None,
    *,
    legacy_enabled: bool,
) -> JSONResponse | None:
    path = request.url.path
    modern_path = path.rstrip("/") == _MODERN_PATH
    if not modern_path and path not in _LEGACY_ENDPOINTS:
        return None
    revision_values = request.headers.getlist("mcp-protocol-version")
    if len(revision_values) > 1 or any("," in item for item in revision_values):
        if modern_path:
            return _typed_mcp_rejection(
                request,
                payload,
                status_code=400,
                error_type="HeaderMismatch",
                message="MCP-Protocol-Version must appear at most once",
                reason_code="duplicate_protocol_header",
                jsonrpc_code=-32020,
            )
        return _typed_ingress_response(
            status_code=400,
            error_type="HeaderMismatch",
            message="MCP-Protocol-Version must appear at most once",
            reason_code="duplicate_protocol_header",
        )
    header_revision = revision_values[0].strip() if revision_values else None
    body_revision = None
    if isinstance(payload, dict) and payload.get("method") == "initialize":
        params = payload.get("params")
        if isinstance(params, dict):
            candidate = params.get("protocolVersion")
            body_revision = candidate.strip() if isinstance(candidate, str) else None

    policy = MCPCompatibilityPolicy(legacy_enabled=legacy_enabled)
    expected = (
        policy.default_revision
        if modern_path
        else policy.legacy_revisions[0]
    )
    supplied = [item for item in (header_revision, body_revision) if item is not None]
    if header_revision and body_revision and header_revision != body_revision:
        if modern_path:
            return _typed_mcp_rejection(
                request,
                payload,
                status_code=400,
                error_type="HeaderMismatch",
                message="MCP protocol header and initialize body disagree",
                reason_code="protocol_header_body_mismatch",
                jsonrpc_code=-32020,
            )
        return _typed_ingress_response(
            status_code=400,
            error_type="HeaderMismatch",
            message="MCP protocol header and initialize body disagree",
            reason_code="protocol_header_body_mismatch",
        )
    if path in _LEGACY_ENDPOINTS and not legacy_enabled:
        return _typed_ingress_response(
            status_code=410,
            error_type="LegacyTransportDisabled",
            message="Legacy HTTP compatibility is disabled",
            reason_code="legacy_transport_disabled",
        )
    if any(revision != expected for revision in supplied):
        if modern_path:
            return _typed_mcp_rejection(
                request,
                payload,
                status_code=400,
                error_type="UnsupportedProtocolVersion",
                message=f"Unsupported protocol revision for {path}",
                reason_code="unsupported_protocol_revision",
                jsonrpc_code=-32022,
                data={"supported": [policy.default_revision]},
            )
        return _typed_ingress_response(
            status_code=400,
            error_type="UnsupportedProtocolVersion",
            message=f"Unsupported protocol revision for {path}",
            reason_code="unsupported_protocol_revision",
        )
    return None


def _request_principal(expected_auth_token: str) -> str:
    digest = hmac.new(
        _INGRESS_PRINCIPAL_SECRET,
        expected_auth_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"operator-root:{digest}"


class TransportAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, expected_auth_token: str) -> None:
        super().__init__(app)
        self._expected_auth_token = expected_auth_token
        settings = Settings.load()
        self._allowed_origins = frozenset(settings.transport_allowed_origins)
        self._max_request_bytes = settings.transport_max_request_bytes
        self._request_timeout_seconds = settings.transport_request_timeout_seconds
        self._legacy_enabled = settings.transport_legacy_enabled

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _AUTH_EXEMPT_PATHS:
            return await call_next(request)

        origins = request.headers.getlist("origin")
        if len(origins) > 1 or any("," in origin for origin in origins):
            return _typed_ingress_response(
                status_code=400,
                error_type="HeaderMismatch",
                message="Origin must appear at most once",
                reason_code="multiple_origin",
            )
        if origins and origins[0] not in self._allowed_origins:
            return _typed_ingress_response(
                status_code=403,
                error_type="InvalidOrigin",
                message="Origin is not allowed",
                reason_code="invalid_origin",
            )

        bearer_headers = request.headers.getlist("authorization")
        token_headers = request.headers.getlist("x-scribe-auth")
        if len(bearer_headers) > 1 or len(token_headers) > 1:
            return _typed_ingress_response(
                status_code=400,
                error_type="HeaderMismatch",
                message="Authentication headers must not be repeated",
                reason_code="duplicate_auth_header",
            )
        if bearer_headers and token_headers:
            bearer = bearer_headers[0].strip()
            bearer = bearer[7:].strip() if bearer.lower().startswith("bearer ") else ""
            if not bearer or not secrets.compare_digest(bearer, token_headers[0].strip()):
                return _typed_ingress_response(
                    status_code=400,
                    error_type="HeaderMismatch",
                    message="Authentication headers disagree",
                    reason_code="auth_header_mismatch",
                )
        if not _request_is_authenticated(request, self._expected_auth_token):
            return _unauthorized_response()
        shutdown_phase = str(
            server_module.get_transport_shutdown_state().get("phase") or "running"
        )
        if shutdown_phase != "running":
            return _shutdown_phase_response(shutdown_phase)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self._max_request_bytes:
                    raise OverflowError
            except (ValueError, OverflowError):
                return _typed_ingress_response(
                    status_code=413,
                    error_type="RequestTooLarge",
                    message="Request body exceeds the configured limit",
                    reason_code="request_limit_exceeded",
                )
        raw_body = await request.body()
        if len(raw_body) > self._max_request_bytes:
            return _typed_ingress_response(
                status_code=413,
                error_type="RequestTooLarge",
                message="Request body exceeds the configured limit",
                reason_code="request_limit_exceeded",
            )
        payload, body_rejection = _request_json_payload(request, raw_body)
        if body_rejection is not None:
            return body_rejection
        protocol_rejection = _protocol_rejection(
            request,
            payload,
            legacy_enabled=self._legacy_enabled,
        )
        if protocol_rejection is not None:
            return protocol_rejection

        is_legacy = path in _LEGACY_ENDPOINTS
        era = ProtocolEra.LEGACY if is_legacy else ProtocolEra.MODERN
        transport = "http-sse" if is_legacy else "streamable-http"
        supplied_handle = request.headers.get(_APPLICATION_HANDLE_HEADER)
        method = payload.get("method") if isinstance(payload, dict) else None
        params = payload.get("params") if isinstance(payload, dict) else None
        tool_name = params.get("name") if isinstance(params, dict) else None
        if (
            method == "tools/call"
            and isinstance(tool_name, str)
            and _is_remote_tool_invoke_transport()
            and _tool_is_local_operator_only(tool_name)
        ):
            return _local_operator_tool_blocked_response(tool_name)
        requires_handle = path.rstrip("/") == _MODERN_PATH and method == "tools/call"
        if requires_handle and not supplied_handle:
            return _typed_ingress_response(
                status_code=401,
                error_type="ApplicationIdentityRequired",
                message="Scribe-Application-Handle is required",
                reason_code="application_handle_required",
            )
        try:
            identity = resolve_application_identity(
                principal_id=_request_principal(self._expected_auth_token),
                protocol_era=era,
                transport=transport,
                supplied_handle=supplied_handle,
                connection_id="authenticated-http-ingress" if supplied_handle is None else None,
            )
        except (TypeError, ValueError) as exc:
            return _typed_ingress_response(
                status_code=401,
                error_type="InvalidApplicationIdentity",
                message=str(exc),
                reason_code="application_identity_denied",
            )
        if supplied_handle and identity.application_handle is None:
            identity = dataclasses.replace(identity, application_handle=supplied_handle)
        attached = _IngressRequestIdentity(
            principal_id=identity.principal_id,
            protocol_era=era,
            transport=transport,
            application_identity=identity,
        )

        phase = await server_module.begin_transport_operation()
        if phase != "running":
            return _shutdown_phase_response(phase)
        token = _INGRESS_REQUEST_IDENTITY.set(attached)
        try:
            try:
                async with asyncio.timeout(self._request_timeout_seconds):
                    response = await call_next(request)
            except TimeoutError:
                return _typed_ingress_response(
                    status_code=504,
                    error_type="RequestTimeout",
                    message="Request exceeded the configured timeout",
                    reason_code="request_timeout",
                )
            if identity.application_handle and supplied_handle is None:
                response.headers[_APPLICATION_HANDLE_HEADER] = identity.application_handle
            downgrade_reason = "recognized_legacy_endpoint" if is_legacy else None
            logger.info(
                "HTTP ingress accepted route=%s era=%s downgrade_reason=%s",
                path,
                era.value,
                downgrade_reason,
                extra={
                    "event_type": "http_ingress",
                    "service": "scribe_mcp",
                    "route": path,
                    "summary": "authenticated MCP ingress accepted",
                    "downgrade_reason": downgrade_reason,
                },
            )
            return response
        finally:
            _INGRESS_REQUEST_IDENTITY.reset(token)
            await server_module.end_transport_operation()


# ---------------------------------------------------------------------------
# REST API: operation allowlist
# ---------------------------------------------------------------------------

#: Legacy allowlist of StorageBackend methods exposed via REST for non-public profiles.
#: Operations NOT in this set are rejected with HTTP 403 Forbidden.
_LEGACY_OPERATION_ALLOWLIST: frozenset[str] = frozenset({
    # Apply-preview receipt operations (internal-only)
    "issue_apply_preview_receipt",
    "fetch_apply_preview_receipt",
    "claim_apply_preview_receipt",
    "finalize_apply_preview_receipt",
    "cleanup_apply_preview_receipts",
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
    "issue_apply_preview_receipt",
    "fetch_apply_preview_receipt",
    "claim_apply_preview_receipt",
    "finalize_apply_preview_receipt",
    "cleanup_apply_preview_receipts",
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


def _is_remote_tool_invoke_transport() -> bool:
    policy = server_module.get_transport_policy()
    return _is_public_release_transport() or bool(policy.get("network_exposed"))


def _tool_is_local_operator_only(tool_name: str) -> bool:
    tool_descriptions = server_module.describe_registered_tools()
    tool_description = tool_descriptions.get(tool_name)
    if not isinstance(tool_description, dict):
        return False

    meta = tool_description.get("meta", {})
    scribe_meta = meta.get("scribe", {}) if isinstance(meta, dict) else {}
    if not isinstance(scribe_meta, dict):
        return False
    if scribe_meta.get("remoteInvokable") is True:
        return False

    surface = scribe_meta.get("surface")
    locality = scribe_meta.get("locality")
    trust_tier = scribe_meta.get("trustTier")
    return surface == "operator" and (locality == "local" or trust_tier == 0)


def _local_operator_tool_blocked_response(tool_name: str) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": "tool_not_remote_invokable",
            "reason_code": "local_operator_tool_blocked",
            "tool_name": tool_name,
            "message": "This tool is not available over exported remote transport.",
        },
        status_code=403,
    )


def _shutdown_phase_response(phase: str) -> JSONResponse:
    if phase == "backend_close" or phase == "closed":
        return JSONResponse(
            {"error": "Transport closed", "type": "TransportClosed"},
            status_code=503,
        )
    return JSONResponse(
        {"error": "Transport draining in-flight requests", "type": "TransportDraining"},
        status_code=503,
    )


def _service_unavailable_response() -> JSONResponse:
    shutdown_state = server_module.get_transport_shutdown_state()
    phase = str(shutdown_state.get("phase") or "running")
    if phase != "running":
        return _shutdown_phase_response(phase)
    return JSONResponse(
        {"error": "Storage backend not yet initialised", "type": "ServiceUnavailable"},
        status_code=503,
    )


def _stale_session_response(exc: SessionLeaseExpired) -> JSONResponse:
    return JSONResponse(
        {
            "error": str(exc),
            "type": "StaleSession",
            "stale_session_reason": exc.reason,
            "agent_id": exc.agent_id,
            "session_id": exc.session_id,
        },
        status_code=409,
    )


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

    receipt = kwargs.get("record")
    if isinstance(receipt, dict):
        def _parse_receipt_datetime(value: Any) -> datetime.datetime:
            if isinstance(value, datetime.datetime):
                return value
            text = str(value).strip()
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            return datetime.datetime.fromisoformat(text)

        kwargs["record"] = ApplyPreviewReceiptRecord(
            token_sha256=receipt["token_sha256"],
            receipt_version=receipt["receipt_version"],
            state=receipt["state"],
            principal_id=receipt["principal_id"],
            session_id=receipt["session_id"],
            run_id=receipt["run_id"],
            project_key=receipt["project_key"],
            repo_id=receipt["repo_id"],
            action=receipt["action"],
            normalized_intent_json=receipt["normalized_intent_json"],
            target_binding_json=receipt["target_binding_json"],
            precondition_json=receipt["precondition_json"],
            predicted_after_json=receipt["predicted_after_json"],
            issued_at=_parse_receipt_datetime(receipt["issued_at"]),
            expires_at=_parse_receipt_datetime(receipt["expires_at"]),
            fence=receipt["fence"],
            apply_lease_expires_at=(
                _parse_receipt_datetime(receipt["apply_lease_expires_at"])
                if receipt.get("apply_lease_expires_at") is not None
                else None
            ),
            terminal_result_code=receipt.get("terminal_result_code"),
            terminal_result_json=receipt.get("terminal_result_json"),
            terminal_at=(
                _parse_receipt_datetime(receipt["terminal_at"])
                if receipt.get("terminal_at") is not None
                else None
            ),
            audit_correlation_id=receipt["audit_correlation_id"],
            updated_at=_parse_receipt_datetime(receipt["updated_at"]),
        )


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
    phase = await server_module.begin_transport_operation()
    if phase != "running":
        return _shutdown_phase_response(phase)
    try:
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
            return _service_unavailable_response()

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
        except SessionLeaseExpired as exc:
            return _stale_session_response(exc)
        except Exception as exc:
            return JSONResponse(
                {"error": str(exc), "type": type(exc).__name__},
                status_code=500,
            )
    finally:
        await server_module.end_transport_operation()


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
    phase = await server_module.begin_transport_operation()
    if phase != "running":
        return _shutdown_phase_response(phase)
    try:
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
            return _service_unavailable_response()

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
            except SessionLeaseExpired as exc:
                results.append(
                    {
                        "ok": False,
                        "error": str(exc),
                        "type": "StaleSession",
                        "stale_session_reason": exc.reason,
                        "agent_id": exc.agent_id,
                        "session_id": exc.session_id,
                    }
                )
            except Exception as exc:
                results.append({"ok": False, "error": str(exc), "type": type(exc).__name__})

        return JSONResponse({"results": results})
    finally:
        await server_module.end_transport_operation()


async def handle_tool_invoke(request: Request) -> JSONResponse:
    """Invoke a registered tool via the standard server invocation pipeline."""
    phase = await server_module.begin_transport_operation()
    if phase != "running":
        return _shutdown_phase_response(phase)
    try:
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}

        tool_name = body.get("tool_name")
        arguments = body.get("arguments", {})
        context = body.get("context", {})

        if not isinstance(tool_name, str) or not tool_name.strip():
            return JSONResponse(
                {"error": "'tool_name' must be a non-empty string", "type": "ValidationError"},
                status_code=400,
            )
        if not isinstance(arguments, dict):
            return JSONResponse(
                {"error": "'arguments' must be an object", "type": "ValidationError"},
                status_code=400,
            )
        if not isinstance(context, dict):
            return JSONResponse(
                {"error": "'context' must be an object", "type": "ValidationError"},
                status_code=400,
            )

        if _is_remote_tool_invoke_transport() and _tool_is_local_operator_only(tool_name):
            return _local_operator_tool_blocked_response(tool_name)

        try:
            result = await server_module.invoke_tool(tool_name, arguments, context=context)
            return JSONResponse({"result": _serialize(result)})
        except SessionLeaseExpired as exc:
            return _stale_session_response(exc)
        except Exception as exc:
            return JSONResponse(
                {"error": str(exc), "type": type(exc).__name__},
                status_code=500,
            )
    finally:
        await server_module.end_transport_operation()


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
    runtime_settings = Settings.load()
    modern_starlette_app = app.streamable_http_app(
        streamable_http_path=_MODERN_PATH,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
        max_request_body_size=runtime_settings.transport_max_request_bytes,
    )
    modern_route = next(
        route
        for route in modern_starlette_app.routes
        if getattr(route, "path", None) == _MODERN_PATH
    )
    # ``SseServerTransport.connect_sse`` manages the SSE response stream
    # directly through the ASGI ``send`` callable (accessed via the
    # semi-private ``request._send``). After the connection closes we return an
    # empty ``Response`` so Starlette's ``request_response`` wrapper does not
    # raise ``TypeError`` when the handler returns ``None``.
    async def handle_sse(request: Request) -> Response:
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send,
        ) as (read_stream, write_stream):
            await app._lowlevel_server.run(
                read_stream,
                write_stream,
                app._lowlevel_server.create_initialization_options(),
            )
        return Response()

    @asynccontextmanager
    async def lifespan(_: Starlette):
        async with modern_starlette_app.router.lifespan_context(modern_starlette_app):
            try:
                yield
            finally:
                await _shutdown()

    starlette_app = Starlette(
        routes=[
            Route("/health", health_check),
            modern_route,
            Route("/sse", handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
            Route("/api/v1/backend/{operation}", handle_backend_operation, methods=["POST"]),
            Route("/api/v1/batch", handle_batch, methods=["POST"]),
            Route("/api/v1/tools/invoke", handle_tool_invoke, methods=["POST"]),
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
