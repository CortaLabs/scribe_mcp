from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import scribe_mcp.server as server_module
import scribe_mcp.server_sse as sse_module


APPLY_PREVIEW_OPERATIONS = frozenset(
    {
        "issue_apply_preview_receipt",
        "fetch_apply_preview_receipt",
        "claim_apply_preview_receipt",
        "finalize_apply_preview_receipt",
        "cleanup_apply_preview_receipts",
    }
)


@pytest.fixture()
def backend_app():
    return Starlette(
        routes=[
            Route(
                "/api/v1/backend/{operation}",
                sse_module.handle_backend_operation,
                methods=["POST"],
            )
        ]
    )


def test_apply_preview_operations_are_internal_only() -> None:
    assert APPLY_PREVIEW_OPERATIONS <= sse_module._LEGACY_OPERATION_ALLOWLIST
    assert APPLY_PREVIEW_OPERATIONS <= sse_module.PUBLIC_RELEASE_DENIED_OPERATIONS
    assert APPLY_PREVIEW_OPERATIONS.isdisjoint(sse_module.PUBLIC_RELEASE_ALLOWED_OPERATIONS)
    assert all(sse_module._operation_is_permitted(operation, public_release=False) for operation in APPLY_PREVIEW_OPERATIONS)
    assert not any(sse_module._operation_is_permitted(operation, public_release=True) for operation in APPLY_PREVIEW_OPERATIONS)


@pytest.mark.parametrize("operation", sorted(APPLY_PREVIEW_OPERATIONS))
def test_public_release_denies_without_backend_execution(monkeypatch, backend_app: Starlette, operation: str) -> None:
    backend = MagicMock()
    method = AsyncMock()
    setattr(backend, operation, method)
    monkeypatch.setattr(server_module, "storage_backend", backend)
    monkeypatch.setattr(sse_module, "_is_public_release_transport", lambda: True)

    with (
        patch(
            "scribe_mcp.server.begin_transport_operation",
            new=AsyncMock(return_value="running"),
        ),
        patch("scribe_mcp.server.end_transport_operation", new=AsyncMock()),
    ):
        with TestClient(backend_app, raise_server_exceptions=False) as client:
            response = client.post(f"/api/v1/backend/{operation}", json={})

    assert response.status_code == 403
    assert response.json()["type"] == "ForbiddenOperation"
    method.assert_not_awaited()


def test_missing_backend_method_fails_closed(monkeypatch, backend_app: Starlette) -> None:
    monkeypatch.setattr(server_module, "storage_backend", object())
    monkeypatch.setattr(sse_module, "_is_public_release_transport", lambda: False)

    with (
        patch(
            "scribe_mcp.server.begin_transport_operation",
            new=AsyncMock(return_value="running"),
        ),
        patch("scribe_mcp.server.end_transport_operation", new=AsyncMock()),
    ):
        with TestClient(backend_app, raise_server_exceptions=False) as client:
            response = client.post("/api/v1/backend/claim_apply_preview_receipt", json={})

    assert response.status_code == 404
    assert response.json()["type"] == "NotFound"


def test_authenticated_transport_rejects_missing_auth_before_dispatch(monkeypatch, backend_app: Starlette) -> None:
    backend = MagicMock()
    backend.claim_apply_preview_receipt = AsyncMock()
    monkeypatch.setattr(server_module, "storage_backend", backend)
    backend_app.add_middleware(
        sse_module.TransportAuthMiddleware,
        expected_auth_token="internal-secret",
    )

    with TestClient(backend_app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/backend/claim_apply_preview_receipt", json={})

    assert response.status_code == 401
    backend.claim_apply_preview_receipt.assert_not_awaited()
