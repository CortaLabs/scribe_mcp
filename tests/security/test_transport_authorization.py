from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
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
