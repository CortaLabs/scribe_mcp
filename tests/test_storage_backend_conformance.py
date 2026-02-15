#!/usr/bin/env python
"""Conformance checks that run the same core assertions on SQLite and Postgres."""

from __future__ import annotations

import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio

from scribe_mcp.storage.postgres import PostgresStorage
from scribe_mcp.storage.sqlite import SQLiteStorage

pytestmark = pytest.mark.asyncio


def _replace_db_name(dsn: str, db_name: str) -> str:
    parts = urlsplit(dsn)
    path = f"/{db_name}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


async def _create_test_database(base_dsn: str, admin_dsn: str, db_name: str) -> str:
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{db_name}";')
    finally:
        await admin.close()
    return _replace_db_name(base_dsn, db_name)


async def _drop_test_database(admin_dsn: str, db_name: str) -> None:
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1
              AND pid <> pg_backend_pid();
            """,
            db_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}";')
    finally:
        await admin.close()


@pytest_asyncio.fixture(params=["sqlite", "postgres"], ids=["sqlite", "postgres"])
async def backend(request, tmp_path):
    backend_name = request.param
    if backend_name == "sqlite":
        storage = SQLiteStorage(db_path=tmp_path / "conformance.sqlite3")
        await storage.setup()
        try:
            yield storage, "sqlite"
        finally:
            await storage.close()
        return

    base_dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not base_dsn:
        pytest.skip("Set SCRIBE_TEST_POSTGRES_URL to enable Postgres conformance tests")
    admin_dsn = os.getenv("SCRIBE_TEST_POSTGRES_ADMIN_URL", _replace_db_name(base_dsn, "postgres"))

    db_name = f"scribe_p8_{uuid.uuid4().hex[:10]}"
    using_shared_db = False
    try:
        test_dsn = await _create_test_database(base_dsn, admin_dsn, db_name)
    except asyncpg.InsufficientPrivilegeError:
        using_shared_db = True
        test_dsn = base_dsn

    storage = PostgresStorage(test_dsn)
    setattr(storage, "_conformance_projects", [])
    setattr(storage, "_conformance_isolated_db", not using_shared_db)
    await storage.setup()
    try:
        yield storage, "postgres"
    finally:
        for project_name in getattr(storage, "_conformance_projects", []):
            try:
                await storage.delete_project(project_name)
            except Exception:
                pass
        await storage.close()
        if not using_shared_db:
            await _drop_test_database(admin_dsn, db_name)


async def _seed_project(storage, root: Path):
    project_name = f"conformance_{uuid.uuid4().hex[:8]}"
    project = await storage.upsert_project(
        name=project_name,
        repo_root=str(root),
        progress_log_path=str(root / "PROGRESS_LOG.md"),
        docs_json='{"checklist":"CHECKLIST.md"}',
    )
    tracked = getattr(storage, "_conformance_projects", None)
    if isinstance(tracked, list):
        tracked.append(project_name)
    return project


async def test_project_entry_roundtrip(backend, tmp_path):
    storage, _ = backend
    project_name = f"conformance_{uuid.uuid4().hex[:8]}"
    project = await storage.upsert_project(
        name=project_name,
        repo_root=str(tmp_path),
        progress_log_path=str(tmp_path / "PROGRESS_LOG.md"),
        docs_json=None,
    )
    tracked = getattr(storage, "_conformance_projects", None)
    if isinstance(tracked, list):
        tracked.append(project_name)

    old_ts = datetime.now(timezone.utc) - timedelta(days=10)
    await storage.insert_entry(
        entry_id=f"entry-{uuid.uuid4().hex}",
        project=project,
        ts=old_ts,
        emoji="✅",
        agent="Codex",
        message="alpha needle",
        meta={"scope": "conformance", "kind": "old"},
        raw_line="alpha needle",
        sha256=uuid.uuid4().hex,
        priority="high",
        category="test",
        log_type="progress",
    )
    await storage.insert_entry(
        entry_id=f"entry-{uuid.uuid4().hex}",
        project=project,
        ts=datetime.now(timezone.utc),
        emoji="ℹ️",
        agent="Codex",
        message="beta needle",
        meta={"scope": "conformance", "kind": "new"},
        raw_line="beta needle",
        sha256=uuid.uuid4().hex,
        priority="medium",
        category="test",
        log_type="progress",
    )

    fetched = await storage.fetch_project(project.name)
    assert fetched is not None
    assert fetched.name == project.name

    recent = await storage.fetch_recent_entries(project=project, limit=20)
    assert len(recent) >= 2

    by_substring = await storage.query_entries(
        project=project,
        limit=20,
        message="needle",
        message_mode="substring",
    )
    assert len(by_substring) >= 2

    by_regex = await storage.query_entries(
        project=project,
        limit=20,
        message="^alpha",
        message_mode="regex",
    )
    assert len(by_regex) == 1
    assert by_regex[0]["message"].startswith("alpha")

    total = await storage.count_entries(project=project)
    assert total >= 2

    deleted = await storage.cleanup_old_entries(project_id=project.id, retention_days=1, archive=True)
    assert deleted >= 1


async def test_agent_project_context_flow(backend, tmp_path):
    storage, _ = backend
    project = await _seed_project(storage, tmp_path)

    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    await storage.upsert_agent_session(agent_id, session_id, {"source": "test"})
    assignment = await storage.set_agent_project(
        agent_id=agent_id,
        project_name=project.name,
        expected_version=None,
        updated_by="test",
        session_id=session_id,
    )
    assert assignment["project_name"] == project.name
    snapshot = await storage.get_agent_project(agent_id)
    assert snapshot is not None
    assert snapshot["project_name"] == project.name


async def test_postgres_specific_document_and_session_apis(backend, tmp_path):
    storage, backend_name = backend
    if backend_name != "postgres":
        pytest.skip("Postgres-only API surface")

    project = await _seed_project(storage, tmp_path)
    await storage.upsert_document_section(
        project_id=project.id,
        project_root=str(tmp_path),
        document_type="research",
        section_id="s1",
        file_path="docs/RESEARCH.md",
        relative_path="docs/RESEARCH.md",
        content="postgres trigram search alpha beta",
        file_hash=uuid.uuid4().hex,
        metadata={"owner": "codex"},
    )

    matches = await storage.search_document_sections(
        query="trigram alpha",
        project_id=project.id,
        threshold=0.1,
        limit=10,
    )
    assert matches, "expected at least one pg_trgm match"
    assert 0.0 <= matches[0]["score"] <= 1.0

    fetched = await storage.get_document_section(
        project_id=project.id,
        document_type="research",
        section_id="s1",
    )
    assert fetched is not None
    assert fetched["content"].startswith("postgres trigram")

    await storage.record_document_change(
        project_id=project.id,
        project_root=str(tmp_path),
        file_path="docs/RESEARCH.md",
        change_type="update",
        change_summary="updated section",
        metadata={"kind": "test"},
    )

    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    await storage.upsert_agent_session(agent_id, session_id, {"source": "test"})
    state = await storage.fetch_agent_session(session_id)
    assert state is not None
    assert state["session_id"] == session_id


async def test_postgres_migration_helpers_on_existing_db(backend, tmp_path):
    storage, backend_name = backend
    if backend_name != "postgres":
        pytest.skip("Postgres-only migration helper checks")

    assert await storage.migrate_add_docs_json_column() is True
    assert await storage.migrate_add_docs_json_column() is True

    project_name = f"conformance_{uuid.uuid4().hex[:8]}"
    project = await storage.upsert_project(
        name=project_name,
        repo_root=str(tmp_path),
        progress_log_path=str(tmp_path / "PROGRESS_LOG.md"),
        docs_json=None,
    )
    tracked = getattr(storage, "_conformance_projects", None)
    if isinstance(tracked, list):
        tracked.append(project_name)
    state_path = tmp_path / "state.json"
    state_payload = {
        "projects": {
            project.name: {
                "docs": {
                    "architecture": "ARCHITECTURE_GUIDE.md",
                    "checklist": "CHECKLIST.md",
                }
            }
        }
    }
    state_path.write_text(json.dumps(state_payload), encoding="utf-8")

    updated = await storage.backfill_docs_json_from_state(state_path)
    assert updated >= 1

    refreshed = await storage.fetch_project(project.name)
    assert refreshed is not None
    assert refreshed.docs_json is not None
    assert "ARCHITECTURE_GUIDE.md" in refreshed.docs_json


async def test_postgres_migration_tracking_idempotent(backend):
    storage, backend_name = backend
    if backend_name != "postgres":
        pytest.skip("Postgres-only migration tracking checks")

    marker = f"conformance_migration_{uuid.uuid4().hex[:12]}"
    calls = {"count": 0}

    async def _migration_body() -> None:
        calls["count"] += 1

    first = await storage._run_migration(marker, _migration_body)
    second = await storage._run_migration(marker, _migration_body)

    assert first is True
    assert second is False
    assert calls["count"] == 1


async def test_dual_backend_query_equivalence(tmp_path):
    base_dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not base_dsn:
        pytest.skip("Set SCRIBE_TEST_POSTGRES_URL to enable dual-backend comparison")

    sqlite = SQLiteStorage(db_path=tmp_path / "equiv.sqlite3")
    postgres = PostgresStorage(base_dsn)
    await sqlite.setup()
    await postgres.setup()
    project_suffix = uuid.uuid4().hex[:8]
    sqlite_project_name = f"equiv_sqlite_{project_suffix}"
    postgres_project_name = f"equiv_postgres_{project_suffix}"
    sqlite_project = None
    postgres_project = None
    try:
        sqlite_project = await sqlite.upsert_project(
            name=sqlite_project_name,
            repo_root=str(tmp_path),
            progress_log_path=str(tmp_path / "sqlite.log"),
        )
        postgres_project = await postgres.upsert_project(
            name=postgres_project_name,
            repo_root=str(tmp_path),
            progress_log_path=str(tmp_path / "postgres.log"),
        )

        messages = [
            ("alpha query line", {"idx": 1}),
            ("beta query line", {"idx": 2}),
            ("alpha regex target", {"idx": 3}),
        ]
        for text, meta in messages:
            ts = datetime.now(timezone.utc) - timedelta(minutes=5 - meta["idx"])
            await sqlite.insert_entry(
                entry_id=f"sqlite-{uuid.uuid4().hex}",
                project=sqlite_project,
                ts=ts,
                emoji="ℹ️",
                agent="Codex",
                message=text,
                meta=meta,
                raw_line=text,
                sha256=uuid.uuid4().hex,
            )
            await postgres.insert_entry(
                entry_id=f"postgres-{uuid.uuid4().hex}",
                project=postgres_project,
                ts=ts,
                emoji="ℹ️",
                agent="Codex",
                message=text,
                meta=meta,
                raw_line=text,
                sha256=uuid.uuid4().hex,
            )

        sqlite_sub = await sqlite.query_entries(
            project=sqlite_project,
            limit=20,
            message="query",
            message_mode="substring",
        )
        postgres_sub = await postgres.query_entries(
            project=postgres_project,
            limit=20,
            message="query",
            message_mode="substring",
        )
        assert sorted(entry["message"] for entry in sqlite_sub) == sorted(
            entry["message"] for entry in postgres_sub
        )

        sqlite_regex = await sqlite.query_entries(
            project=sqlite_project,
            limit=20,
            message="^alpha",
            message_mode="regex",
        )
        postgres_regex = await postgres.query_entries(
            project=postgres_project,
            limit=20,
            message="^alpha",
            message_mode="regex",
        )
        assert sorted(entry["message"] for entry in sqlite_regex) == sorted(
            entry["message"] for entry in postgres_regex
        )
    finally:
        try:
            if postgres_project is not None:
                await postgres.delete_project(postgres_project.name)
            else:
                await postgres.delete_project(postgres_project_name)
        except Exception:
            pass
        try:
            if sqlite_project is not None:
                await sqlite.delete_project(sqlite_project.name)
            else:
                await sqlite.delete_project(sqlite_project_name)
        except Exception:
            pass
        await postgres.close()
        await sqlite.close()
