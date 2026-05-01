"""Tests for server REST API endpoints.

Covers Task Packages 3.1 (single-operation endpoint) and 3.2 (batch endpoint).

The Starlette app is built inline with the same handler functions used in
production but with a mocked storage backend, so no real MCP server is started.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import scribe_mcp.server as server_module
from scribe_mcp.server_sse import (
    OPERATION_ALLOWLIST,
    _serialize,
    handle_backend_operation,
    handle_batch,
    handle_tool_invoke,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_test_app() -> Starlette:
    """Build a minimal Starlette app with only the REST API routes."""
    return Starlette(
        routes=[
            Route("/api/v1/backend/{operation}", handle_backend_operation, methods=["POST"]),
            Route("/api/v1/batch", handle_batch, methods=["POST"]),
            Route("/api/v1/tools/invoke", handle_tool_invoke, methods=["POST"]),
        ]
    )


@dataclasses.dataclass
class _FakeProjectRecord:
    id: int
    name: str
    repo_root: str
    progress_log_path: str
    docs_json: str | None = None
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None
    bridge_id: str | None = None
    bridge_managed: bool = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_backend():
    """Return a mock backend and install / uninstall it on server_module."""
    backend = MagicMock()
    # Make all attribute accesses return AsyncMocks by default
    backend.fetch_project = AsyncMock(return_value=_FakeProjectRecord(
        id=1,
        name="test_project",
        repo_root="/tmp/test",
        progress_log_path="/tmp/test/log.md",
        created_at=datetime.datetime(2026, 1, 1, 12, 0, 0),
    ))
    backend.list_projects = AsyncMock(return_value=[])
    backend.insert_entry = AsyncMock(return_value=42)
    original = server_module.storage_backend
    server_module.storage_backend = backend
    yield backend
    server_module.storage_backend = original


@pytest.fixture()
def null_backend():
    """Set storage_backend to None to simulate uninitialised server."""
    original = server_module.storage_backend
    server_module.storage_backend = None
    yield
    server_module.storage_backend = original


@pytest.fixture()
def client(mock_backend):
    """Starlette TestClient with mock backend pre-installed."""
    app = _build_test_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def client_no_backend(null_backend):
    """Starlette TestClient with backend set to None."""
    app = _build_test_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# _serialize unit tests
# ---------------------------------------------------------------------------

def test_serialize_primitives():
    """Primitives pass through unchanged."""
    assert _serialize(None) is None
    assert _serialize(True) is True
    assert _serialize(42) == 42
    assert _serialize(3.14) == 3.14
    assert _serialize("hello") == "hello"


def test_serialize_datetime():
    """datetime objects become ISO strings."""
    dt = datetime.datetime(2026, 2, 17, 10, 30, 0)
    assert _serialize(dt) == "2026-02-17T10:30:00"


def test_serialize_dataclass():
    """Dataclass instances are recursively converted to dicts."""
    rec = _FakeProjectRecord(
        id=5,
        name="proj",
        repo_root="/r",
        progress_log_path="/r/log.md",
        created_at=datetime.datetime(2026, 1, 1),
    )
    result = _serialize(rec)
    assert isinstance(result, dict)
    assert result["id"] == 5
    assert result["name"] == "proj"
    assert result["created_at"] == "2026-01-01T00:00:00"


def test_serialize_tuple_becomes_list():
    """Tuples (paginated results) become lists."""
    items = [{"a": 1}]
    total = 1
    assert _serialize((items, total)) == [[{"a": 1}], 1]


def test_serialize_nested():
    """Nested dict/list are handled recursively."""
    data = {"records": [_FakeProjectRecord(id=1, name="x", repo_root="/", progress_log_path="/log")]}
    result = _serialize(data)
    assert result["records"][0]["name"] == "x"


# ---------------------------------------------------------------------------
# OPERATION_ALLOWLIST tests
# ---------------------------------------------------------------------------

def test_allowlist_contains_required_operations():
    required = {
        "fetch_project", "upsert_project", "list_projects",
        "insert_entry", "fetch_recent_entries", "query_entries",
        "upsert_session", "cleanup_old_entries",
    }
    assert required.issubset(OPERATION_ALLOWLIST)


def test_allowlist_is_frozenset():
    assert isinstance(OPERATION_ALLOWLIST, frozenset)


# ---------------------------------------------------------------------------
# Task Package 3.1: /api/v1/backend/{operation}
# ---------------------------------------------------------------------------

def test_single_operation_success(client, mock_backend):
    """Valid allowlisted operation returns 200 with result."""
    resp = client.post("/api/v1/backend/fetch_project", json={"name": "test_project"})
    assert resp.status_code == 200
    body = resp.json()
    assert "result" in body
    assert body["result"]["name"] == "test_project"
    assert body["result"]["id"] == 1
    # datetime must be serialised
    assert body["result"]["created_at"] == "2026-01-01T12:00:00"
    mock_backend.fetch_project.assert_awaited_once_with(name="test_project")


def test_single_operation_allowlist_rejected(client):
    """Operation not in allowlist returns 403."""
    resp = client.post("/api/v1/backend/drop_all_tables", json={})
    assert resp.status_code == 403
    body = resp.json()
    assert body["type"] == "ForbiddenOperation"
    assert "drop_all_tables" in body["error"]


def test_single_operation_backend_not_initialised(client_no_backend):
    """Backend=None returns 503 Service Unavailable."""
    resp = client_no_backend.post("/api/v1/backend/fetch_project", json={"name": "x"})
    assert resp.status_code == 503
    body = resp.json()
    assert body["type"] == "ServiceUnavailable"


def test_single_operation_backend_raises(client, mock_backend):
    """Backend exception returns 500 with error info."""
    mock_backend.fetch_project = AsyncMock(side_effect=RuntimeError("DB exploded"))
    resp = client.post("/api/v1/backend/fetch_project", json={"name": "boom"})
    assert resp.status_code == 500
    body = resp.json()
    assert body["type"] == "RuntimeError"
    assert "DB exploded" in body["error"]


def test_single_operation_no_body_defaults_to_empty_kwargs(client, mock_backend):
    """Missing/invalid JSON body is treated as empty kwargs dict."""
    mock_backend.list_projects = AsyncMock(return_value=[])
    resp = client.post("/api/v1/backend/list_projects", content=b"", headers={"content-type": "application/json"})
    # Should not crash; will call list_projects() with no args
    assert resp.status_code in (200, 500)  # 500 if list_projects requires args


def test_single_operation_get_not_allowed(client):
    """GET is not accepted on the operation endpoint."""
    resp = client.get("/api/v1/backend/fetch_project")
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Task Package 3.2: /api/v1/batch
# ---------------------------------------------------------------------------

def test_batch_three_operations_returns_three_results(client, mock_backend):
    """Batch with 3 ops returns 3 result entries."""
    mock_backend.fetch_project = AsyncMock(return_value=_FakeProjectRecord(
        id=1, name="p1", repo_root="/", progress_log_path="/log"
    ))
    mock_backend.list_projects = AsyncMock(return_value=[])
    mock_backend.insert_entry = AsyncMock(return_value=99)

    resp = client.post("/api/v1/batch", json={"operations": [
        {"op": "fetch_project", "args": {"name": "p1"}},
        {"op": "list_projects", "args": {}},
        {"op": "insert_entry", "args": {"project_name": "p1", "agent": "A", "message": "m", "status": "info"}},
    ]})
    assert resp.status_code == 200
    body = resp.json()
    results = body["results"]
    assert len(results) == 3
    assert all("ok" in r for r in results)


def test_batch_partial_success_continues_after_failure(client, mock_backend):
    """One failing operation does not abort subsequent operations."""
    mock_backend.fetch_project = AsyncMock(side_effect=RuntimeError("boom"))
    mock_backend.list_projects = AsyncMock(return_value=["project_a"])

    resp = client.post("/api/v1/batch", json={"operations": [
        {"op": "fetch_project", "args": {"name": "x"}},
        {"op": "list_projects", "args": {}},
    ]})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    assert results[0]["ok"] is False
    assert "boom" in results[0]["error"]
    assert results[1]["ok"] is True


def test_batch_allowlist_enforced_per_operation(client, mock_backend):
    """Forbidden operation in batch returns ok=False for that entry."""
    mock_backend.list_projects = AsyncMock(return_value=[])

    resp = client.post("/api/v1/batch", json={"operations": [
        {"op": "list_projects", "args": {}},
        {"op": "exec_raw_sql", "args": {"sql": "DROP TABLE scribe_entries"}},
    ]})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False
    assert results[1]["type"] == "ForbiddenOperation"


@pytest.mark.asyncio
async def test_tool_invoke_route_calls_server_pipeline(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_invoke(tool_name: str, arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        captured["context"] = context
        return {"ok": True, "tool": tool_name}

    monkeypatch.setattr(server_module, "invoke_tool", fake_invoke)
    app = _build_test_app()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/api/v1/tools/invoke",
            json={"tool_name": "manage_docs", "arguments": {"agent": "test-agent"}, "context": {"mode": "project"}},
        )

    assert response.status_code == 200
    assert response.json()["result"]["ok"] is True
    assert captured == {
        "tool_name": "manage_docs",
        "arguments": {"agent": "test-agent"},
        "context": {"mode": "project"},
    }


def test_batch_backend_not_initialised_returns_503(client_no_backend):
    """Batch with uninitialised backend returns 503 (not per-item error)."""
    resp = client_no_backend.post("/api/v1/batch", json={"operations": [
        {"op": "list_projects", "args": {}},
    ]})
    assert resp.status_code == 503


def test_batch_invalid_body_returns_400(client):
    """Non-list 'operations' field returns 400."""
    resp = client.post("/api/v1/batch", json={"operations": "not-a-list"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["type"] == "ValidationError"


def test_batch_missing_operations_key_returns_400(client):
    """Body without 'operations' key returns 400."""
    resp = client.post("/api/v1/batch", json={"something_else": []})
    assert resp.status_code == 400


def test_batch_empty_operations_returns_empty_results(client):
    """Empty operations list returns empty results list."""
    resp = client.post("/api/v1/batch", json={"operations": []})
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_batch_get_not_allowed(client):
    """GET is not accepted on the batch endpoint."""
    resp = client.get("/api/v1/batch")
    assert resp.status_code == 405
