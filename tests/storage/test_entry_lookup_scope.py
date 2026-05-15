from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.storage.postgres import PostgresStorage
from scribe_mcp.storage.remote import RemoteStorageBackend
from scribe_mcp.storage.sqlite import SQLiteStorage


@pytest.mark.asyncio
async def test_sqlite_fetch_entry_by_id_honors_repo_and_project_scope(tmp_path):
    storage = SQLiteStorage(tmp_path / "entry_lookup.sqlite3")
    project_a = await storage.upsert_project(
        name="alpha",
        repo_root=str(tmp_path / "repo-a"),
        progress_log_path=str(tmp_path / "a.log"),
    )
    project_b = await storage.upsert_project(
        name="beta",
        repo_root=str(tmp_path / "repo-b"),
        progress_log_path=str(tmp_path / "b.log"),
    )

    entry_id = "a" * 32
    await storage.insert_entry(
        entry_id=entry_id,
        project=project_a,
        ts=datetime.now(timezone.utc),
        emoji="✅",
        agent="tester",
        message="scoped entry",
        meta={"log_type": "progress"},
        raw_line="raw",
        sha256="b" * 64,
    )

    found = await storage.fetch_entry_by_id(
        entry_id=entry_id,
        repo_id=project_a.repo_id,
        project_name=project_a.name,
    )
    assert found is not None
    assert found["entry_id"] == entry_id
    assert found["repo_id"] == project_a.repo_id
    assert found["project_name"] == project_a.name

    wrong_repo = await storage.fetch_entry_by_id(
        entry_id=entry_id,
        repo_id=project_b.repo_id,
        project_name=project_a.name,
    )
    assert wrong_repo is None

    wrong_project = await storage.fetch_entry_by_id(
        entry_id=entry_id,
        repo_id=project_a.repo_id,
        project_name=project_b.name,
    )
    assert wrong_project is None

    await storage.close()


@pytest.mark.asyncio
async def test_sqlite_fetch_entry_by_id_not_found_returns_none(tmp_path):
    storage = SQLiteStorage(tmp_path / "entry_lookup_none.sqlite3")
    project = await storage.upsert_project(
        name="alpha",
        repo_root=str(tmp_path / "repo-a"),
        progress_log_path=str(tmp_path / "a.log"),
    )

    not_found = await storage.fetch_entry_by_id(
        entry_id="f" * 32,
        repo_id=project.repo_id,
        project_name=project.name,
    )
    assert not_found is None
    await storage.close()


@pytest.mark.asyncio
async def test_remote_forwards_fetch_entry_by_id_contract(monkeypatch: pytest.MonkeyPatch):
    remote = RemoteStorageBackend(server_url="http://example.test")
    expected = {
        "entry_id": "c" * 32,
        "project_name": "alpha",
        "repo_id": "r" * 64,
        "timestamp": "2026-05-15T00:00:00+00:00",
        "agent": "tester",
        "log_type": "progress",
    }

    async def fake_call(method: str, **kwargs):
        assert method == "fetch_entry_by_id"
        assert kwargs["entry_id"] == expected["entry_id"]
        assert kwargs["repo_id"] == expected["repo_id"]
        assert kwargs["project_name"] == expected["project_name"]
        return expected

    monkeypatch.setattr(remote, "_call", fake_call)

    result = await remote.fetch_entry_by_id(
        entry_id=expected["entry_id"],
        repo_id=expected["repo_id"],
        project_name=expected["project_name"],
    )
    assert result == expected


@pytest.mark.asyncio
async def test_postgres_fetch_entry_by_id_query_shape_and_scoped_result(
    monkeypatch: pytest.MonkeyPatch,
):
    storage = PostgresStorage(dsn="postgresql://user:pass@localhost:5432/db")
    captured: dict[str, object] = {}

    async def fake_fetchrow(query: str, *params):
        captured["query"] = query
        captured["params"] = params
        return {
            "entry_id": "d" * 32,
            "project_name": "alpha",
            "repo_id": "r" * 64,
            "ts": datetime(2026, 5, 15, tzinfo=timezone.utc),
            "agent": "tester",
            "log_type": "progress",
        }

    monkeypatch.setattr(storage, "_fetchrow", fake_fetchrow)

    result = await storage.fetch_entry_by_id(
        entry_id="d" * 32,
        repo_id="r" * 64,
        project_name="alpha",
    )

    assert result == {
        "entry_id": "d" * 32,
        "project_name": "alpha",
        "repo_id": "r" * 64,
        "timestamp": "2026-05-15 00:00:00 UTC",
        "agent": "tester",
        "log_type": "progress",
    }
    query = str(captured["query"])
    assert "JOIN scribe_projects p ON p.id = e.project_id" in query
    assert "e.id = $1" in query
    assert "p.repo_id = $2" in query
    assert "p.name = $3" in query
    assert "SELECT e.id AS entry_id, p.name AS project_name, p.repo_id, e.ts, e.agent, e.log_type" in query
    assert captured["params"] == ("d" * 32, "r" * 64, "alpha")
