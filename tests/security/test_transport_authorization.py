from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import scribe_mcp.server as server_module
from scribe_mcp.server_sse import TransportAuthMiddleware, handle_backend_operation, handle_batch, handle_tool_invoke


LOCAL_OPERATOR_TOOL_DESCRIPTIONS = {
    "scribe_doctor": {
        "meta": {
            "scribe": {
                "trustTier": 0,
                "surface": "operator",
                "locality": "local",
            }
        }
    },
    "read_file": {
        "meta": {
            "scribe": {
                "trustTier": 0,
                "surface": "operator",
                "locality": "local",
            }
        }
    },
}


@pytest.fixture()
def mock_backend():
    backend = MagicMock()
    backend.list_projects = AsyncMock(return_value=[{"name": "alpha"}])
    backend.query_entries = AsyncMock(return_value=[])
    backend.read_recent = AsyncMock(return_value=[])
    backend.delete_project = AsyncMock(return_value=1)

    original = server_module.storage_backend
    server_module.storage_backend = backend
    try:
        yield backend
    finally:
        server_module.storage_backend = original


@pytest.fixture()
def restore_transport_policy():
    original_policy = server_module.get_transport_policy()
    try:
        yield
    finally:
        server_module.app.state.transport_policy = original_policy


@pytest.fixture()
def client(mock_backend):
    app = Starlette(
        routes=[
            Route("/api/v1/backend/{operation}", handle_backend_operation, methods=["POST"]),
            Route("/api/v1/batch", handle_batch, methods=["POST"]),
            Route("/api/v1/tools/invoke", handle_tool_invoke, methods=["POST"]),
        ]
    )
    app.add_middleware(TransportAuthMiddleware, expected_auth_token="test-token")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _set_network_exposed_transport() -> None:
    server_module.set_transport_policy(
        server_module.build_transport_policy(
            transport="sse",
            host="0.0.0.0",
            port=8200,
            auth_required=True,
            auth_configured=True,
        )
    )


def _assert_local_operator_tool_denied(response, tool_name: str) -> None:
    assert response.status_code == 403
    body = response.json()
    assert body == {
        "ok": False,
        "error": "tool_not_remote_invokable",
        "reason_code": "local_operator_tool_blocked",
        "tool_name": tool_name,
        "message": "This tool is not available over exported remote transport.",
    }
    assert "repo_root" not in str(body)
    assert "absolute_path" not in str(body)


def test_tool_invoke_requires_auth(client) -> None:
    response = client.post("/api/v1/tools/invoke", json={"tool_name": "manage_docs", "arguments": {}, "context": {}})
    assert response.status_code == 401
    assert response.json()["type"] == "Unauthorized"


@pytest.mark.parametrize("tool_name", ["scribe_doctor", "read_file"])
def test_public_exported_tool_invoke_denies_local_operator_tools_before_dispatch(
    monkeypatch,
    client,
    restore_transport_policy,
    tool_name: str,
) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    describe_tools = MagicMock(return_value=LOCAL_OPERATOR_TOOL_DESCRIPTIONS)
    invoke_tool = AsyncMock(return_value={"repo_root": "/private/repo"})
    monkeypatch.setattr(server_module, "describe_registered_tools", describe_tools)
    monkeypatch.setattr(server_module, "invoke_tool", invoke_tool)

    response = client.post(
        "/api/v1/tools/invoke",
        json={"tool_name": tool_name, "arguments": {}, "context": {}},
        headers={"authorization": "Bearer test-token"},
    )

    _assert_local_operator_tool_denied(response, tool_name)
    describe_tools.assert_called_once()
    invoke_tool.assert_not_awaited()


@pytest.mark.parametrize("tool_name", ["scribe_doctor", "read_file"])
def test_internal_network_exposed_tool_invoke_denies_local_operator_tools_before_dispatch(
    monkeypatch,
    client,
    restore_transport_policy,
    tool_name: str,
) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "internal")
    _set_network_exposed_transport()
    describe_tools = MagicMock(return_value=LOCAL_OPERATOR_TOOL_DESCRIPTIONS)
    invoke_tool = AsyncMock(return_value={"absolute_path": "/private/repo/file.txt"})
    monkeypatch.setattr(server_module, "describe_registered_tools", describe_tools)
    monkeypatch.setattr(server_module, "invoke_tool", invoke_tool)

    response = client.post(
        "/api/v1/tools/invoke",
        json={"tool_name": tool_name, "arguments": {}, "context": {}},
        headers={"authorization": "Bearer test-token"},
    )

    _assert_local_operator_tool_denied(response, tool_name)
    describe_tools.assert_called_once()
    invoke_tool.assert_not_awaited()


def test_crafted_context_cannot_self_label_exported_remote_invoke_as_local(
    monkeypatch,
    client,
    restore_transport_policy,
) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    invoke_tool = AsyncMock(return_value={"repo_root": "/private/repo"})
    monkeypatch.setattr(server_module, "describe_registered_tools", MagicMock(return_value=LOCAL_OPERATOR_TOOL_DESCRIPTIONS))
    monkeypatch.setattr(server_module, "invoke_tool", invoke_tool)

    response = client.post(
        "/api/v1/tools/invoke",
        json={
            "tool_name": "scribe_doctor",
            "arguments": {},
            "context": {"transport": "stdio", "local": True, "profile": "operator"},
        },
        headers={"authorization": "Bearer test-token"},
    )

    _assert_local_operator_tool_denied(response, "scribe_doctor")
    invoke_tool.assert_not_awaited()


def test_unknown_tool_invoke_uses_existing_dispatch_failure_path(
    monkeypatch,
    client,
) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    invoke_tool = AsyncMock(side_effect=KeyError("unknown tool"))
    monkeypatch.setattr(server_module, "describe_registered_tools", MagicMock(return_value=LOCAL_OPERATOR_TOOL_DESCRIPTIONS))
    monkeypatch.setattr(server_module, "invoke_tool", invoke_tool)

    response = client.post(
        "/api/v1/tools/invoke",
        json={"tool_name": "unknown_tool", "arguments": {}, "context": {}},
        headers={"authorization": "Bearer test-token"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["type"] == "KeyError"
    assert body["error"] != "tool_not_remote_invokable"
    invoke_tool.assert_awaited_once_with("unknown_tool", {}, context={})


def test_public_release_denied_operation_rejected_single(monkeypatch, client, mock_backend) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")

    response = client.post(
        "/api/v1/backend/delete_project",
        json={"name": "alpha"},
        headers={"authorization": "Bearer test-token"},
    )

    assert response.status_code == 403
    assert response.json()["type"] == "ForbiddenOperation"
    assert response.json()["type"] != "TransportClosed"
    mock_backend.delete_project.assert_not_awaited()


def test_public_release_mixed_batch_with_denied_operation_fails_closed(monkeypatch, client, mock_backend) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")

    response = client.post(
        "/api/v1/batch",
        json={
            "operations": [
                {"op": "list_projects", "args": {}},
                {"op": "delete_project", "args": {"name": "alpha"}},
            ]
        },
        headers={"authorization": "Bearer test-token"},
    )

    assert response.status_code == 403
    assert response.json()["type"] == "ForbiddenOperation"
    assert response.json()["type"] != "TransportClosed"
    mock_backend.list_projects.assert_not_awaited()
    mock_backend.delete_project.assert_not_awaited()


def test_public_release_allowed_operation_succeeds(monkeypatch, client, mock_backend) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")

    response = client.post("/api/v1/backend/list_projects", json={}, headers={"authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == [{"name": "alpha"}]
    mock_backend.list_projects.assert_awaited_once_with()


def test_internal_profile_keeps_legacy_allowlist_for_transport(monkeypatch, client, mock_backend) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "internal")

    response = client.post(
        "/api/v1/backend/delete_project",
        json={"name": "alpha"},
        headers={"authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    mock_backend.delete_project.assert_awaited_once_with(name="alpha")


def test_modern_ingress_attaches_only_authenticated_application_identity(monkeypatch) -> None:
    import scribe_mcp.server_sse as sse_mod

    observed: list[dict[str, object]] = []

    async def capture_identity(_request):
        request_context = sse_mod.app.request_context
        identity = request_context.application_identity
        observed.append(
            {
                "principal_id": request_context.principal_id,
                "protocol_era": request_context.protocol_era,
                "transport": request_context.transport,
                "identity_key": identity.identity_key,
                "agent_label": getattr(request_context, "agent_id", None),
                "client_info": getattr(request_context, "client_info", None),
                "capabilities": getattr(request_context, "capabilities", None),
                "request_id": getattr(request_context, "request_id", None),
                "process_id": getattr(request_context, "process_id", None),
                "mcp_session_id": getattr(request_context, "mcp_session_id", None),
            }
        )
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", capture_identity, methods=["POST"])])
    app.add_middleware(TransportAuthMiddleware, expected_auth_token="test-token")

    hostile_body = {
        "jsonrpc": "2.0",
        "id": "caller-request-id",
        "method": "initialize",
        "params": {
            "protocolVersion": "2026-07-28",
            "clientInfo": {"name": "forged-agent", "version": "1"},
            "capabilities": {"forged": True},
        },
    }
    hostile_headers = {
        "authorization": "Bearer test-token",
        "mcp-protocol-version": "2026-07-28",
        "mcp-session-id": "caller-selected-session",
        "x-agent-id": "forged-agent",
        "x-request-id": "forged-request",
        "x-process-id": "1234",
    }
    with TestClient(app, raise_server_exceptions=False) as test_client:
        first = test_client.post("/mcp", json=hostile_body, headers=hostile_headers)
        handle = first.headers["scribe-application-handle"]
        second = test_client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={
                **hostile_headers,
                "scribe-application-handle": handle,
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert observed[0]["identity_key"] == observed[1]["identity_key"]
    assert observed[0]["principal_id"] != "forged-agent"
    assert observed[0]["protocol_era"].value == "modern"
    assert observed[0]["transport"] == "streamable-http"
    for untrusted_name in (
        "agent_label",
        "client_info",
        "capabilities",
        "request_id",
        "process_id",
        "mcp_session_id",
    ):
        assert observed[0][untrusted_name] is None


@pytest.mark.parametrize(
    ("path", "revision"),
    [
        ("/mcp", "2026-07-28"),
        ("/messages/?session_id=caller-selected", "2025-11-25"),
    ],
)
def test_native_modern_and_legacy_tool_calls_share_remote_authorization(
    monkeypatch,
    path: str,
    revision: str,
) -> None:
    import scribe_mcp.server_sse as sse_mod

    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    monkeypatch.setattr(
        server_module,
        "describe_registered_tools",
        MagicMock(return_value=LOCAL_OPERATOR_TOOL_DESCRIPTIONS),
    )
    call_tool = AsyncMock()
    monkeypatch.setattr(sse_mod.app, "call_tool", call_tool)
    monkeypatch.setattr(sse_mod, "_shutdown", AsyncMock())
    app = sse_mod._build_starlette_app(
        sse_transport=sse_mod.SseServerTransport("/messages/"),
        expected_auth_token="test-token",
    )

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            path,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "scribe_doctor", "arguments": {}},
            },
            headers={
                "authorization": "Bearer test-token",
                "mcp-protocol-version": revision,
                "mcp-method": "tools/call",
                "mcp-name": "scribe_doctor",
                "accept": "application/json, text/event-stream",
            },
        )

    _assert_local_operator_tool_denied(response, "scribe_doctor")
    call_tool.assert_not_awaited()


def test_modern_header_and_capability_errors_never_dispatch_or_fallback(monkeypatch) -> None:
    import scribe_mcp.server_sse as sse_mod

    call_tool = AsyncMock()
    monkeypatch.setattr(sse_mod.app, "call_tool", call_tool)
    monkeypatch.setattr(sse_mod, "_shutdown", AsyncMock())
    app = sse_mod._build_starlette_app(
        sse_transport=sse_mod.SseServerTransport("/messages/"),
        expected_auth_token="test-token",
    )
    base_headers = {
        "authorization": "Bearer test-token",
        "mcp-protocol-version": "2026-07-28",
        "accept": "application/json, text/event-stream",
    }

    with TestClient(app, raise_server_exceptions=False) as test_client:
        header_mismatch = test_client.post(
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
            headers={**base_headers, "mcp-method": "tools/call"},
        )
        missing_capability_envelope = test_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    }
                },
            },
            headers={**base_headers, "mcp-method": "tools/list"},
        )
        malformed = test_client.post(
            "/mcp",
            content=b"{not-json",
            headers={**base_headers, "content-type": "application/json"},
        )

    assert header_mismatch.status_code == 400
    assert header_mismatch.json()["error"]["code"] == -32020
    assert missing_capability_envelope.status_code == 400
    assert missing_capability_envelope.json()["error"]["code"] == -32602
    assert malformed.status_code == 400
    assert malformed.json()["type"] == "ParseError"
    assert malformed.json()["error"]["code"] == -32700
    call_tool.assert_not_awaited()


def test_native_modern_dispatch_consumes_only_ingress_attached_identity(monkeypatch) -> None:
    import mcp.types as mcp_types
    import scribe_mcp.server_sse as sse_mod
    from scribe_mcp.shared.tool_runtime import _resolve_runtime_application_identity

    observed = []

    async def identity_probe(_name, _arguments, _context):
        identity = _resolve_runtime_application_identity(sse_mod.app)
        observed.append(identity)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="ok")]
        )

    monkeypatch.setattr(sse_mod, "_shutdown", AsyncMock())
    app = sse_mod._build_starlette_app(
        sse_transport=sse_mod.SseServerTransport("/messages/"),
        expected_auth_token="test-token",
    )
    meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {"forged": True},
        "io.modelcontextprotocol/clientInfo": {"name": "forged-agent", "version": "1"},
    }
    base_headers = {
        "authorization": "Bearer test-token",
        "mcp-protocol-version": "2026-07-28",
        "accept": "application/json, text/event-stream",
        "mcp-session-id": "caller-selected-session",
        "x-agent-id": "forged-agent",
        "x-request-id": "forged-request",
        "x-process-id": "1234",
    }

    with TestClient(app, raise_server_exceptions=False) as test_client:
        first = test_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {"_meta": meta},
            },
            headers={**base_headers, "mcp-method": "tools/list"},
        )
        handle = first.headers["scribe-application-handle"]
        monkeypatch.setattr(sse_mod.app, "call_tool", identity_probe)
        second = test_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "identity_probe",
                    "arguments": {},
                    "_meta": meta,
                },
            },
            headers={
                **base_headers,
                "mcp-method": "tools/call",
                "mcp-name": "identity_probe",
                "scribe-application-handle": handle,
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert observed and observed[0] is not None
    assert observed[0].principal_id != "forged-agent"
    assert observed[0].protocol_era.value == "modern"
    assert observed[0].transport == "streamable-http"
    assert observed[0].identity_key


def test_caller_selected_modern_application_handle_rejects_before_dispatch(monkeypatch) -> None:
    import scribe_mcp.server_sse as sse_mod

    call_tool = AsyncMock()
    monkeypatch.setattr(sse_mod.app, "call_tool", call_tool)
    monkeypatch.setattr(sse_mod, "_shutdown", AsyncMock())
    app = sse_mod._build_starlette_app(
        sse_transport=sse_mod.SseServerTransport("/messages/"),
        expected_auth_token="test-token",
    )

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "unknown", "arguments": {}},
            },
            headers={
                "authorization": "Bearer test-token",
                "mcp-protocol-version": "2026-07-28",
                "mcp-method": "tools/call",
                "mcp-name": "unknown",
                "scribe-application-handle": "caller-selected",
                "accept": "application/json, text/event-stream",
            },
        )

    assert response.status_code == 401
    assert response.json()["type"] == "InvalidApplicationIdentity"
    assert response.json()["reason_code"] == "application_identity_denied"
    call_tool.assert_not_awaited()
