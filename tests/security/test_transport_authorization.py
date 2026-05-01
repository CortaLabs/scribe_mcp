from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import scribe_mcp.server as server_module
from scribe_mcp.server_sse import TransportAuthMiddleware, handle_backend_operation, handle_batch, handle_tool_invoke


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


def test_tool_invoke_requires_auth(client) -> None:
    response = client.post("/api/v1/tools/invoke", json={"tool_name": "manage_docs", "arguments": {}, "context": {}})
    assert response.status_code == 401
    assert response.json()["type"] == "Unauthorized"


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
