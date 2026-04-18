"""Tests for RemoteStorageBackend -- HTTP proxy storage backend.

Tests are organised into five categories:
1. Session methods (in-memory, zero network)
2. Remote methods (HTTP proxy, mocked httpx)
3. Error handling (connection, timeout, server errors)
4. ProjectRecord deserialization (dict -> ProjectRecord)
5. Batch operations (execute_batch)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Ensure the src package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scribe_mcp.storage.base import ConflictError, RemoteUnavailableError
from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.storage.remote import RemoteStorageBackend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backend() -> RemoteStorageBackend:
    """Backend instance (not yet setup -- no real client)."""
    return RemoteStorageBackend("http://remote-server:8200", timeout=5.0)


@pytest.fixture
def live_backend() -> RemoteStorageBackend:
    """Backend instance with a mocked httpx client already attached."""
    b = RemoteStorageBackend("http://remote-server:8200", timeout=5.0)
    b._client = AsyncMock(spec=httpx.AsyncClient)
    return b


@pytest.fixture
def auth_live_backend() -> RemoteStorageBackend:
    """Backend instance with auth configured and a mocked httpx client attached."""
    b = RemoteStorageBackend(
        "http://remote-server:8200",
        timeout=5.0,
        auth_token="client-token",
    )
    b._client = AsyncMock(spec=httpx.AsyncClient)
    return b


def _make_response(json_body: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _make_project_dict(**overrides: Any) -> dict:
    """Create a server-style project dict."""
    base = {
        "id": 42,
        "name": "test_project",
        "repo_root": "/home/user/repo",
        "progress_log_path": ".scribe/docs/dev_plans/test_project/PROGRESS_LOG.md",
        "docs_json": '{"architecture": "arch.md"}',
        "created_at": "2026-02-17T00:00:00",
        "updated_at": "2026-02-17T01:00:00",
        "bridge_id": None,
        "bridge_managed": False,
    }
    base.update(overrides)
    return base


# ===================================================================
# 1. Session methods (in-memory, zero network)
# ===================================================================


class TestSessionMethods:
    """Session methods must work entirely in-memory with NO HTTP calls."""

    @pytest.mark.asyncio
    async def test_upsert_and_get_session_by_transport(self, backend: RemoteStorageBackend) -> None:
        """upsert_session stores data, get_session_by_transport retrieves it."""
        await backend.upsert_session(
            session_id="s1",
            transport_session_id="t1",
            repo_root="/repo",
            mode="client",
        )
        session = await backend.get_session_by_transport("t1")
        assert session is not None
        assert session["session_id"] == "s1"
        assert session["repo_root"] == "/repo"

    @pytest.mark.asyncio
    async def test_session_mode_get_set(self, backend: RemoteStorageBackend) -> None:
        """set/get_session_mode roundtrips correctly."""
        assert await backend.get_session_mode("s1") is None
        await backend.set_session_mode("s1", "client")
        assert await backend.get_session_mode("s1") == "client"

    @pytest.mark.asyncio
    async def test_session_project_get_set(self, backend: RemoteStorageBackend) -> None:
        """set/get_session_project roundtrips correctly."""
        assert await backend.get_session_project("s1") is None
        await backend.set_session_project("s1", "my_project")
        assert await backend.get_session_project("s1") == "my_project"

    @pytest.mark.asyncio
    async def test_agent_project_version_control(self, backend: RemoteStorageBackend) -> None:
        """set_agent_project enforces optimistic concurrency."""
        # First set
        result = await backend.set_agent_project(
            agent_id="agent1",
            project_name="proj_a",
            expected_version=None,
            updated_by="test",
            session_id="s1",
        )
        assert result["version"] == 1
        assert result["project_name"] == "proj_a"

        # Second set with correct version
        result2 = await backend.set_agent_project(
            agent_id="agent1",
            project_name="proj_b",
            expected_version=1,
            updated_by="test",
            session_id="s1",
        )
        assert result2["version"] == 2

        # Conflict: wrong version
        with pytest.raises(ConflictError):
            await backend.set_agent_project(
                agent_id="agent1",
                project_name="proj_c",
                expected_version=1,  # stale
                updated_by="test",
                session_id="s1",
            )

    @pytest.mark.asyncio
    async def test_get_or_create_agent_session_idempotent(self, backend: RemoteStorageBackend) -> None:
        """get_or_create_agent_session returns same session_id for same scoped identity."""
        sid1 = await backend.get_or_create_agent_session(
            identity_key="key1",
            agent_name="a1",
            repo_root="/tmp/repo",
            mode="project",
            scope_key="project-a",
        )
        sid2 = await backend.get_or_create_agent_session(
            identity_key="key1",
            agent_name="a1",
            repo_root="/tmp/repo",
            mode="project",
            scope_key="project-a",
        )
        assert sid1 == sid2
        allocation = await backend.get_last_agent_session_allocation("key1")
        assert allocation is not None
        assert allocation["status"] == "reused"
        assert allocation["session_id"] == sid1
        assert allocation["scoped_reuse_key"] == "/tmp/repo:project-a"
        assert allocation["repo_root"] == "/tmp/repo"
        assert allocation["scope_key"] == "project-a"
        assert allocation["mode"] == "project"
        # Different key gets different session
        sid3 = await backend.get_or_create_agent_session(identity_key="key2", agent_name="a2")
        assert sid3 != sid1

    @pytest.mark.asyncio
    async def test_get_or_create_agent_session_allocates_new_on_scope_change(
        self, backend: RemoteStorageBackend
    ) -> None:
        sid_a = await backend.get_or_create_agent_session(
            identity_key="key1",
            agent_name="a1",
            repo_root="/tmp/repo",
            mode="project",
            scope_key="project-a",
        )
        sid_b = await backend.get_or_create_agent_session(
            identity_key="key1",
            agent_name="a1",
            repo_root="/tmp/repo",
            mode="project",
            scope_key="project-b",
        )
        assert sid_a != sid_b
        allocation = await backend.get_last_agent_session_allocation("key1")
        assert allocation is not None
        assert allocation["status"] == "allocated"
        assert allocation["session_id"] == sid_b
        assert allocation["scoped_reuse_key"] == "/tmp/repo:project-b"
        assert allocation["repo_root"] == "/tmp/repo"
        assert allocation["scope_key"] == "project-b"
        assert allocation["mode"] == "project"

    @pytest.mark.asyncio
    async def test_get_or_create_agent_session_does_not_collide_on_repo_root(
        self, backend: RemoteStorageBackend
    ) -> None:
        sid_a = await backend.get_or_create_agent_session(
            identity_key="shared-key",
            agent_name="a1",
            repo_root="/tmp/repo-a",
            mode="project",
            scope_key="project-a",
        )
        sid_b = await backend.get_or_create_agent_session(
            identity_key="shared-key",
            agent_name="a1",
            repo_root="/tmp/repo-b",
            mode="project",
            scope_key="project-a",
        )
        assert sid_a != sid_b

    @pytest.mark.asyncio
    async def test_get_or_create_agent_session_reuse_survives_compatibility_transport_inputs(
        self, backend: RemoteStorageBackend
    ) -> None:
        await backend.upsert_session(
            session_id="legacy-session-1",
            transport_session_id="legacy-client-id",
            repo_root="/tmp/repo",
            mode="project",
        )
        await backend.upsert_session(
            session_id="legacy-session-2",
            transport_session_id="legacy-connection-id",
            repo_root="/tmp/repo",
            mode="project",
        )

        sid_a = await backend.get_or_create_agent_session(
            identity_key="compat-key",
            agent_name="a1",
            repo_root="/tmp/repo",
            mode="project",
            scope_key="project-a",
        )
        sid_a_repeat = await backend.get_or_create_agent_session(
            identity_key="compat-key",
            agent_name="a1",
            repo_root="/tmp/repo",
            mode="project",
            scope_key="project-a",
        )
        sid_b = await backend.get_or_create_agent_session(
            identity_key="compat-key",
            agent_name="a1",
            repo_root="/tmp/repo",
            mode="project",
            scope_key="project-b",
        )

        assert sid_a == sid_a_repeat
        assert sid_b != sid_a
        allocation = await backend.get_last_agent_session_allocation("compat-key")
        assert allocation is not None
        assert allocation["status"] == "allocated"
        assert allocation["session_id"] == sid_b
        assert allocation["scoped_reuse_key"] == "/tmp/repo:project-b"

    @pytest.mark.asyncio
    async def test_heartbeat_and_end_session(self, backend: RemoteStorageBackend) -> None:
        """heartbeat updates timestamp, end_session marks expired."""
        await backend.upsert_agent_session("agent1", "s1", {"role": "coder"})
        session = backend._sessions["s1"]
        assert session["state"] == "active"

        await backend.heartbeat_session("s1")
        assert backend._sessions["s1"]["last_active_at"] is not None

        await backend.end_session("s1")
        assert backend._sessions["s1"]["state"] == "expired"

    @pytest.mark.asyncio
    async def test_session_activity_minimal(self, backend: RemoteStorageBackend) -> None:
        """update_session_activity is no-op, get_session_activity returns minimal data."""
        await backend.upsert_session(session_id="s1")
        # No-op should not raise
        await backend.update_session_activity("s1", "append_entry", "2026-01-01T00:00:00")
        activity = await backend.get_session_activity("s1")
        assert activity is not None
        assert "last_activity_at" in activity
        assert activity["recent_tools"] == []

    @pytest.mark.asyncio
    async def test_get_session_activity_missing(self, backend: RemoteStorageBackend) -> None:
        """get_session_activity returns None for unknown session."""
        result = await backend.get_session_activity("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_agent_recent_project(self, backend: RemoteStorageBackend) -> None:
        """upsert_agent_recent_project stores and overwrites."""
        await backend.upsert_agent_recent_project("agent1", "proj_a")
        assert backend._agent_recent_projects["agent1"] == "proj_a"
        await backend.upsert_agent_recent_project("agent1", "proj_b")
        assert backend._agent_recent_projects["agent1"] == "proj_b"

    @pytest.mark.asyncio
    async def test_session_methods_no_http(self, backend: RemoteStorageBackend) -> None:
        """Session methods must NOT touch _client (it's None and that's fine)."""
        assert backend._client is None  # No setup() called
        # All these should work without HTTP:
        await backend.upsert_session(session_id="s1")
        await backend.set_session_mode("s1", "client")
        await backend.set_session_project("s1", "proj")
        await backend.upsert_agent_session("a1", "s2", None)
        await backend.heartbeat_session("s2")
        await backend.end_session("s2")
        await backend.get_or_create_agent_session(identity_key="k1")
        await backend.upsert_agent_recent_project("a1", "proj")
        await backend.update_session_activity("s1", "tool", "ts")
        await backend.get_session_activity("s1")
        # If we get here, no HTTP was attempted (client is None)


# ===================================================================
# 2. Remote methods (HTTP proxy)
# ===================================================================


class TestRemoteMethods:
    """Remote methods send correct HTTP requests and deserialize responses."""

    @pytest.mark.asyncio
    async def test_fetch_project(self, live_backend: RemoteStorageBackend) -> None:
        """fetch_project sends correct request and returns ProjectRecord."""
        proj_dict = _make_project_dict()
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": proj_dict}))

        result = await live_backend.fetch_project("test_project")
        assert isinstance(result, ProjectRecord)
        assert result.id == 42
        assert result.name == "test_project"

        # Verify correct endpoint and payload
        live_backend._client.post.assert_called_once()
        call_args = live_backend._client.post.call_args
        assert call_args.args[0] == "/api/v1/backend/fetch_project"
        payload = call_args.kwargs["json"]
        assert payload["name"] == "test_project"

    @pytest.mark.asyncio
    async def test_fetch_project_not_found(self, live_backend: RemoteStorageBackend) -> None:
        """fetch_project returns None when server returns null."""
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": None}))
        result = await live_backend.fetch_project("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_project(self, live_backend: RemoteStorageBackend) -> None:
        """upsert_project sends all parameters and returns ProjectRecord."""
        proj_dict = _make_project_dict(name="new_proj")
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": proj_dict}))

        result = await live_backend.upsert_project(
            name="new_proj",
            repo_root="/repo",
            progress_log_path="log.md",
            docs_json='{"a":"b"}',
        )
        assert isinstance(result, ProjectRecord)
        assert result.name == "new_proj"

        call_kwargs = live_backend._client.post.call_args
        payload = call_kwargs.kwargs["json"] if "json" in call_kwargs.kwargs else call_kwargs[1]["json"]
        assert payload["name"] == "new_proj"
        assert payload["docs_json"] == '{"a":"b"}'

    @pytest.mark.asyncio
    async def test_list_projects(self, live_backend: RemoteStorageBackend) -> None:
        """list_projects returns list of ProjectRecords."""
        proj_dicts = [_make_project_dict(id=1, name="p1"), _make_project_dict(id=2, name="p2")]
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": proj_dicts}))

        result = await live_backend.list_projects()
        assert len(result) == 2
        assert result[0].name == "p1"
        assert result[1].name == "p2"

    @pytest.mark.asyncio
    async def test_insert_entry(self, live_backend: RemoteStorageBackend) -> None:
        """insert_entry serializes ProjectRecord and datetime correctly."""
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": None}))
        proj = ProjectRecord(id=1, name="p", repo_root="/r", progress_log_path="l.md")

        await live_backend.insert_entry(
            entry_id="e1",
            project=proj,
            ts=datetime(2026, 2, 17, 12, 0, 0),
            emoji="info",
            agent="tester",
            message="test msg",
            meta={"key": "val"},
            raw_line="raw",
            sha256="abc",
        )

        call_kwargs = live_backend._client.post.call_args
        payload = call_kwargs.kwargs["json"] if "json" in call_kwargs.kwargs else call_kwargs[1]["json"]
        assert payload["project"] == {"name": "p", "id": 1}
        assert payload["ts"] == "2026-02-17T12:00:00"

    @pytest.mark.asyncio
    async def test_fetch_recent_entries(self, live_backend: RemoteStorageBackend) -> None:
        """fetch_recent_entries returns list of dicts from server."""
        entries = [{"id": "e1", "message": "hello"}, {"id": "e2", "message": "world"}]
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": entries}))
        proj = ProjectRecord(id=1, name="p", repo_root="/r", progress_log_path="l.md")

        result = await live_backend.fetch_recent_entries(project=proj, limit=10)
        assert len(result) == 2
        assert result[0]["message"] == "hello"

    @pytest.mark.asyncio
    async def test_fetch_recent_entries_paginated(self, live_backend: RemoteStorageBackend) -> None:
        """fetch_recent_entries_paginated unpacks [entries, count] tuple."""
        entries = [{"id": "e1"}]
        live_backend._client.post = AsyncMock(
            return_value=_make_response({"result": [entries, 42]})
        )
        proj = ProjectRecord(id=1, name="p", repo_root="/r", progress_log_path="l.md")

        result_entries, total = await live_backend.fetch_recent_entries_paginated(
            project=proj, page=1, page_size=10
        )
        assert result_entries == entries
        assert total == 42

    @pytest.mark.asyncio
    async def test_delete_project(self, live_backend: RemoteStorageBackend) -> None:
        """delete_project returns bool."""
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": True}))
        assert await live_backend.delete_project("p") is True

    @pytest.mark.asyncio
    async def test_count_entries(self, live_backend: RemoteStorageBackend) -> None:
        """count_entries returns integer."""
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": 99}))
        proj = ProjectRecord(id=1, name="p", repo_root="/r", progress_log_path="l.md")
        assert await live_backend.count_entries(proj) == 99

    @pytest.mark.asyncio
    async def test_cleanup_old_entries(self, live_backend: RemoteStorageBackend) -> None:
        """cleanup_old_entries proxies to server and returns int."""
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": 15}))
        assert await live_backend.cleanup_old_entries(project_id=1, retention_days=30) == 15


# ===================================================================
# 3. Auth + error handling
# ===================================================================


class TestRemoteAuth:
    """Verify request auth headers are emitted on optional remote/client calls."""

    @pytest.mark.asyncio
    async def test_backend_requests_emit_auth_headers(
        self,
        auth_live_backend: RemoteStorageBackend,
    ) -> None:
        """Backend calls send the documented auth headers."""
        auth_live_backend._client.post = AsyncMock(
            return_value=_make_response({"result": _make_project_dict(name="secured_project")})
        )

        result = await auth_live_backend.fetch_project("secured_project")

        assert result is not None
        request = auth_live_backend._client.post.await_args
        assert request.args[0] == "/api/v1/backend/fetch_project"
        assert request.kwargs["headers"] == {
            "Authorization": "Bearer client-token",
            "x-scribe-auth": "client-token",
        }

    @pytest.mark.asyncio
    async def test_execute_batch_emits_auth_headers(
        self,
        auth_live_backend: RemoteStorageBackend,
    ) -> None:
        """Batch calls send the documented auth headers."""
        auth_live_backend._client.post = AsyncMock(
            return_value=_make_response({"results": [{"ok": True, "result": 1}]})
        )

        results = await auth_live_backend.execute_batch(
            [{"op": "count_entries", "args": {"project_id": 1}}]
        )

        assert results == [{"ok": True, "result": 1}]
        request = auth_live_backend._client.post.await_args
        assert request.args[0] == "/api/v1/batch"
        assert request.kwargs["headers"] == {
            "Authorization": "Bearer client-token",
            "x-scribe-auth": "client-token",
        }


class TestErrorHandling:
    """Verify correct exceptions for network and server errors."""

    @pytest.mark.asyncio
    async def test_call_without_setup_raises(self, backend: RemoteStorageBackend) -> None:
        """Calling _call before setup() raises RemoteUnavailableError."""
        with pytest.raises(RemoteUnavailableError, match="not initialized"):
            await backend._call("fetch_project", name="x")

    @pytest.mark.asyncio
    async def test_connection_error(self, live_backend: RemoteStorageBackend) -> None:
        """httpx.ConnectError is wrapped in RemoteUnavailableError."""
        live_backend._client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(RemoteUnavailableError, match="Cannot reach"):
            await live_backend.fetch_project("p")

    @pytest.mark.asyncio
    async def test_timeout_error(self, live_backend: RemoteStorageBackend) -> None:
        """httpx.TimeoutException is wrapped in RemoteUnavailableError."""
        live_backend._client.post = AsyncMock(
            side_effect=httpx.TimeoutException("Timed out")
        )
        with pytest.raises(RemoteUnavailableError, match="timeout"):
            await live_backend.fetch_project("p")

    @pytest.mark.asyncio
    async def test_server_error_in_response(self, live_backend: RemoteStorageBackend) -> None:
        """Server returning {"error": "..."} raises RuntimeError."""
        live_backend._client.post = AsyncMock(
            return_value=_make_response({"error": "something broke", "type": "InternalError"})
        )
        with pytest.raises(RuntimeError, match="something broke"):
            await live_backend.fetch_project("p")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status_code", "status_label"),
        [(401, "Unauthorized"), (403, "Forbidden")],
    )
    async def test_auth_failures_surface_explicit_guidance(
        self,
        auth_live_backend: RemoteStorageBackend,
        status_code: int,
        status_label: str,
    ) -> None:
        """401/403 responses surface clear remote auth guidance."""
        auth_live_backend._client.post = AsyncMock(
            return_value=_make_response({"detail": "token rejected"}, status_code=status_code)
        )

        with pytest.raises(
            RuntimeError,
            match="Remote authentication failed for backend/fetch_project",
        ) as excinfo:
            await auth_live_backend.fetch_project("p")

        message = str(excinfo.value)
        assert f"HTTP {status_code} {status_label}" in message
        assert "SCRIBE_REMOTE_AUTH_TOKEN" in message

    @pytest.mark.asyncio
    async def test_execute_batch_without_setup_raises(self, backend: RemoteStorageBackend) -> None:
        """execute_batch before setup() raises RemoteUnavailableError."""
        with pytest.raises(RemoteUnavailableError, match="not initialized"):
            await backend.execute_batch([{"op": "list_projects", "args": {}}])

    @pytest.mark.asyncio
    async def test_record_doc_change_swallows_errors(self, live_backend: RemoteStorageBackend) -> None:
        """record_doc_change is fire-and-forget -- errors are swallowed."""
        live_backend._client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        proj = ProjectRecord(id=1, name="p", repo_root="/r", progress_log_path="l.md")
        # Should NOT raise
        await live_backend.record_doc_change(
            proj, doc="arch.md", section="intro", action="edit",
            agent="test", metadata=None, sha_before="a", sha_after="b",
        )

    @pytest.mark.asyncio
    async def test_reminder_methods_swallow_errors(self, live_backend: RemoteStorageBackend) -> None:
        """Reminder methods return empty results on error instead of raising."""
        live_backend._client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        assert await live_backend.get_reminder_history() == []
        assert await live_backend.clear_reminder_history() == 0


def test_remote_backend_rejects_public_release_profile(monkeypatch) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    monkeypatch.delenv("SCRIBE_PUBLIC_RELEASE", raising=False)
    with pytest.raises(
        ValueError,
        match="RemoteStorageBackend is internal-only and unavailable in public release profile.",
    ):
        RemoteStorageBackend("http://remote-server:8200", timeout=5.0)


def test_remote_backend_rejects_explicit_public_release_flag(monkeypatch) -> None:
    monkeypatch.setenv("SCRIBE_PUBLIC_RELEASE", "true")
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "internal")
    with pytest.raises(
        ValueError,
        match="RemoteStorageBackend is internal-only and unavailable in public release profile.",
    ):
        RemoteStorageBackend("http://remote-server:8200", timeout=5.0)


# ===================================================================
# 4. ProjectRecord deserialization
# ===================================================================


class TestProjectRecordDeserialization:
    """Verify _to_project_record handles various input shapes."""

    def test_dict_to_project_record(self, backend: RemoteStorageBackend) -> None:
        """Standard dict from server converts to ProjectRecord with correct types."""
        data = _make_project_dict(id=99, name="my_proj")
        result = backend._to_project_record(data)
        assert isinstance(result, ProjectRecord)
        assert result.id == 99
        assert result.name == "my_proj"
        assert result.repo_root == "/home/user/repo"
        assert result.docs_json == '{"architecture": "arch.md"}'
        assert result.bridge_managed is False

    def test_none_returns_none(self, backend: RemoteStorageBackend) -> None:
        """None input returns None."""
        assert backend._to_project_record(None) is None

    def test_minimal_dict(self, backend: RemoteStorageBackend) -> None:
        """Dict with only required fields gets defaults."""
        result = backend._to_project_record({"id": 1, "name": "x"})
        assert result.id == 1
        assert result.name == "x"
        assert result.repo_root == ""
        assert result.progress_log_path == ""
        assert result.docs_json is None
        assert result.bridge_managed is False

    def test_integer_id_preserved(self, backend: RemoteStorageBackend) -> None:
        """Ensure id stays as int (not string from JSON)."""
        result = backend._to_project_record({"id": 123, "name": "p"})
        assert isinstance(result.id, int)
        assert result.id == 123

    def test_passthrough_project_record(self, backend: RemoteStorageBackend) -> None:
        """If input is already a ProjectRecord, return as-is."""
        pr = ProjectRecord(id=1, name="p", repo_root="/r", progress_log_path="l.md")
        assert backend._to_project_record(pr) is pr


# ===================================================================
# 5. Batch operations
# ===================================================================


class TestBatchOperations:
    """Test execute_batch sends correct payload and handles responses."""

    @pytest.mark.asyncio
    async def test_batch_success(self, live_backend: RemoteStorageBackend) -> None:
        """Batch with multiple operations returns all results."""
        batch_response = {
            "results": [
                {"ok": True, "result": _make_project_dict(name="p1")},
                {"ok": True, "result": 42},
            ]
        }
        live_backend._client.post = AsyncMock(
            return_value=_make_response(batch_response)
        )

        ops = [
            {"op": "fetch_project", "args": {"name": "p1"}},
            {"op": "count_entries", "args": {"project": {"name": "p1", "id": 1}}},
        ]
        results = await live_backend.execute_batch(ops)
        assert len(results) == 2
        assert results[0]["ok"] is True
        assert results[1]["result"] == 42

        # Verify payload structure
        call_kwargs = live_backend._client.post.call_args
        payload = call_kwargs.kwargs["json"] if "json" in call_kwargs.kwargs else call_kwargs[1]["json"]
        assert payload["operations"] == ops

    @pytest.mark.asyncio
    async def test_batch_partial_failure(self, live_backend: RemoteStorageBackend) -> None:
        """Batch with partial failure returns mixed ok/error results."""
        batch_response = {
            "results": [
                {"ok": True, "result": None},
                {"ok": False, "error": "Not found", "type": "NotFound"},
            ]
        }
        live_backend._client.post = AsyncMock(
            return_value=_make_response(batch_response)
        )

        results = await live_backend.execute_batch([
            {"op": "delete_project", "args": {"name": "p1"}},
            {"op": "fetch_project", "args": {"name": "missing"}},
        ])
        assert results[0]["ok"] is True
        assert results[1]["ok"] is False
        assert results[1]["error"] == "Not found"

    @pytest.mark.asyncio
    async def test_batch_connection_error(self, live_backend: RemoteStorageBackend) -> None:
        """Batch raises RemoteUnavailableError on connection failure."""
        live_backend._client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(RemoteUnavailableError, match="Cannot reach"):
            await live_backend.execute_batch([{"op": "list_projects", "args": {}}])

    @pytest.mark.asyncio
    async def test_batch_timeout_error(self, live_backend: RemoteStorageBackend) -> None:
        """Batch raises RemoteUnavailableError on timeout."""
        live_backend._client.post = AsyncMock(
            side_effect=httpx.TimeoutException("Timed out")
        )
        with pytest.raises(RemoteUnavailableError, match="timeout"):
            await live_backend.execute_batch([{"op": "list_projects", "args": {}}])


# ===================================================================
# 6. Bridge methods (no-ops)
# ===================================================================


class TestBridgeNoOps:
    """Bridge methods should be no-ops returning empty/None."""

    @pytest.mark.asyncio
    async def test_bridge_methods_are_noop(self, backend: RemoteStorageBackend) -> None:
        """All bridge methods work without HTTP client and return empty values."""
        await backend.insert_bridge("b1", "bridge", "1.0", "{}", "active")
        await backend.update_bridge_state("b1", "inactive")
        await backend.update_bridge_health("b1", "{}")
        assert await backend.fetch_bridge("b1") is None
        assert await backend.list_bridges() == []
        await backend.delete_bridge("b1")  # Should not raise


# ===================================================================
# 7. Lifecycle (setup/close)
# ===================================================================


class TestLifecycle:
    """Test setup and close methods."""

    @pytest.mark.asyncio
    async def test_setup_creates_client(self, backend: RemoteStorageBackend) -> None:
        """setup() creates an httpx.AsyncClient."""
        assert backend._client is None
        await backend.setup()
        assert backend._client is not None
        assert isinstance(backend._client, httpx.AsyncClient)
        await backend.close()

    @pytest.mark.asyncio
    async def test_close_clears_client(self, backend: RemoteStorageBackend) -> None:
        """close() sets _client to None."""
        await backend.setup()
        assert backend._client is not None
        await backend.close()
        assert backend._client is None

    @pytest.mark.asyncio
    async def test_close_without_setup_is_safe(self, backend: RemoteStorageBackend) -> None:
        """close() is safe to call even without setup()."""
        await backend.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_fetch_project_sync_delegates(self, live_backend: RemoteStorageBackend) -> None:
        """fetch_project_sync delegates to fetch_project."""
        proj_dict = _make_project_dict()
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": proj_dict}))
        result = await live_backend.fetch_project_sync("test_project")
        assert isinstance(result, ProjectRecord)
        assert result.name == "test_project"


# ===================================================================
# 8. Project cache (OPT-2)
# ===================================================================


class TestProjectCache:
    """Tests for the short-lived project record cache (OPT-2)."""

    @pytest.mark.asyncio
    async def test_project_cache_hit(self, live_backend: RemoteStorageBackend) -> None:
        """Second fetch_project call returns cached result with no HTTP call."""
        proj_dict = _make_project_dict()
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": proj_dict}))

        # First call -- should hit the server
        result1 = await live_backend.fetch_project("test_project")
        assert isinstance(result1, ProjectRecord)
        assert live_backend._client.post.call_count == 1

        # Second call -- should return from cache, no new HTTP call
        result2 = await live_backend.fetch_project("test_project")
        assert isinstance(result2, ProjectRecord)
        assert result2.name == result1.name
        assert result2.id == result1.id
        assert live_backend._client.post.call_count == 1  # still only 1 HTTP call

    @pytest.mark.asyncio
    async def test_upsert_populates_cache(self, live_backend: RemoteStorageBackend) -> None:
        """upsert_project populates cache so subsequent fetch_project avoids HTTP."""
        proj_dict = _make_project_dict(name="upserted_proj")
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": proj_dict}))

        # Upsert -- should also populate cache
        upserted = await live_backend.upsert_project(
            name="upserted_proj",
            repo_root="/repo",
            progress_log_path="log.md",
        )
        assert upserted is not None
        assert live_backend._client.post.call_count == 1

        # Fetch immediately after upsert -- should come from cache
        fetched = await live_backend.fetch_project("upserted_proj")
        assert isinstance(fetched, ProjectRecord)
        assert fetched.name == "upserted_proj"
        assert live_backend._client.post.call_count == 1  # no second HTTP call

    @pytest.mark.asyncio
    async def test_project_cache_expiry(self, live_backend: RemoteStorageBackend) -> None:
        """Cache expires after TTL and subsequent fetch hits the server again."""
        proj_dict = _make_project_dict()
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": proj_dict}))

        # First fetch -- populates cache
        await live_backend.fetch_project("test_project")
        assert live_backend._client.post.call_count == 1

        # Artificially expire the cache entry by setting cached_at to past TTL
        name = "test_project"
        record, _cached_at = live_backend._project_cache[name]
        live_backend._project_cache[name] = (record, 0.0)  # epoch (definitely expired)

        # Second fetch -- cache is expired, should hit server again
        await live_backend.fetch_project("test_project")
        assert live_backend._client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_project_cache_invalidation(self, live_backend: RemoteStorageBackend) -> None:
        """delete_project removes the entry from the cache."""
        proj_dict = _make_project_dict()
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": proj_dict}))

        # Populate cache via fetch
        await live_backend.fetch_project("test_project")
        assert "test_project" in live_backend._project_cache

        # delete_project should invalidate the cache entry
        live_backend._client.post = AsyncMock(return_value=_make_response({"result": True}))
        await live_backend.delete_project("test_project")
        assert "test_project" not in live_backend._project_cache

    def test_cache_miss_returns_none(self, backend: RemoteStorageBackend) -> None:
        """_get_cached_project returns None for unknown project names."""
        result = backend._get_cached_project("nonexistent")
        assert result is None

    def test_cache_hit_returns_record(self, backend: RemoteStorageBackend) -> None:
        """_cache_project + _get_cached_project round-trip works correctly."""
        record = ProjectRecord(
            id=1,
            name="cached_proj",
            repo_root="/repo",
            progress_log_path="log.md",
        )
        backend._cache_project(record)
        cached = backend._get_cached_project("cached_proj")
        assert cached is not None
        assert cached.name == "cached_proj"
        assert cached.id == 1
