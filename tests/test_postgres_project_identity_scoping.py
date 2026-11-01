from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import hashlib
import json
import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio

import scribe_mcp.storage.postgres as postgres_module
from scribe_mcp.storage.models import SessionBindingRecordV2, compute_project_key
from scribe_mcp.storage.postgres import PostgresStorage


@pytest_asyncio.fixture
async def delete_postgres_storage():
    """Opt-in disposable schema; never use the configured product DSN."""
    dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip("Set SCRIBE_TEST_POSTGRES_URL for PostgreSQL delete regressions")
    schema = f"scribe_delete_{uuid.uuid4().hex}"
    database = f"scribe_delete_{uuid.uuid4().hex}"
    parts = urlsplit(dsn)
    isolated_dsn = urlunsplit(parts._replace(path=f"/{database}"))
    storage = PostgresStorage(isolated_dsn, schema_name=schema, pool_min_size=1, pool_max_size=4)
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE DATABASE "{database}"')
    try:
        await storage.setup()
        yield storage
    finally:
        await storage.close()
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database}"')
            assert not await admin.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = $1)", database
            ), "disposable PostgreSQL database leaked"
        finally:
            await admin.close()


async def _delete_snapshot(storage):
    """All table payloads, including keys, generations and timestamps."""
    pool = await storage._ensure_pool()
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = $1 ORDER BY tablename",
            storage.schema_name,
        )
        return {
            table["tablename"]: json.loads(await conn.fetchval(
                f'SELECT COALESCE(jsonb_agg(payload ORDER BY payload::text), \'[]\'::jsonb) '
                f'FROM (SELECT to_jsonb(t) AS payload FROM "{storage.schema_name}".'
                f'"{table["tablename"]}" AS t) AS rows'
            ))
            for table in tables
        }


async def _seed_delete_project(storage, *, name, root, session, test_agent):
    project = await storage.upsert_project(
        name=name, repo_root=root, progress_log_path=f"{root}/PROGRESS_LOG.md",
        docs_json='{"payload":"preserve"}',
    )
    await storage._execute(
        "INSERT INTO scribe_sessions(session_id, agent_id, repo_root) VALUES ($1, $2, $3)",
        session, test_agent, root,
    )
    await storage.set_session_project(session, name)
    await storage.set_agent_project(test_agent, name, None, test_agent, session)
    await storage.upsert_agent_recent_project(test_agent, name)
    await storage._execute(
        "INSERT INTO scribe_entries(id, project_id, ts, ts_iso, emoji, agent, message, "
        "raw_line, sha256, meta) VALUES ($1, $2, NOW(), NOW(), 'i', $3, $4, $4, $4, $5::jsonb)",
        session, project.id, test_agent, f"payload-{session}", '{"nested":[1,"data"]}',
    )
    await storage._execute(
        "INSERT INTO scribe_metrics(project_id, total_entries) VALUES ($1, 19)", project.id
    )
    await storage._execute(
        "INSERT INTO document_sections(project_id, document_type, section_id, content, file_hash, metadata) "
        "VALUES ($1, 'architecture', 'design', $2, $2, '{\"nested\":[2,\"document\"]}'::jsonb)",
        project.id, f"document-{session}",
    )
    await storage._execute(
        "INSERT INTO dev_plans(project_id, project_name, plan_type, file_path, metadata) "
        "VALUES ($1, $2, 'architecture', $3, '{\"nested\":[3,\"plan\"]}'::jsonb)",
        project.id, name, f"{root}/ARCHITECTURE_GUIDE.md",
    )
    return project


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.storage
async def test_postgres_delete_unique_canonical_cleanup(delete_postgres_storage, test_agent):
    storage = delete_postgres_storage
    target = await _seed_delete_project(
        storage, name="delete_target", root="/tmp/delete-a", session="target", test_agent=test_agent
    )
    sibling = await _seed_delete_project(
        storage, name="sibling", root="/tmp/delete-b", session="sibling", test_agent=f"{test_agent}:sibling"
    )
    await storage._execute(
        "INSERT INTO scribe_sessions(session_id, agent_id, repo_root) VALUES ('unresolved', $1, '/tmp/missing')",
        test_agent,
    )
    await storage.set_session_project("unresolved", target.name)
    await storage.set_agent_project(f"{test_agent}:unknown", target.name, None, test_agent, "missing")
    before = await _delete_snapshot(storage)
    assert await storage.delete_project("Delete Target") is True
    after = await _delete_snapshot(storage)
    assert await storage.fetch_project(target.name) is None
    assert await storage.fetch_project(sibling.name) == sibling
    changed = {"scribe_projects", "scribe_entries", "scribe_metrics", "document_sections", "dev_plans", "session_projects", "agent_projects", "agent_recent_projects"}
    for table in before.keys() - changed:
        assert after[table] == before[table], table
    for session_id in ["target", "unresolved"]:
        old = next(row for row in before["session_projects"] if row["session_id"] == session_id)
        row = next(row for row in after["session_projects"] if row["session_id"] == session_id)
        assert row["project_name"] is None
        assert row["project_key"] is None
        assert row["binding_state"] == "unresolved"
        assert row["binding_state_reason"] == "project_name_absent"
        assert row["binding_generation"] == old["binding_generation"] + 1
    for agent in [test_agent, f"{test_agent}:unknown"]:
        selection = await storage.get_agent_project(agent)
        assert selection["project_name"] is None
        assert selection["version"] == 2
    for table in ["scribe_entries", "scribe_metrics", "document_sections", "dev_plans", "scribe_projects"]:
        key = "id" if table == "scribe_projects" else "project_id"
        assert after[table] == [row for row in before[table] if row[key] == sibling.id]
    for table, key, value in [("session_projects", "session_id", "sibling"), ("agent_projects", "agent_id", f"{test_agent}:sibling"), ("agent_recent_projects", "project_name", sibling.name)]:
        assert [row for row in after[table] if row[key] == value] == [row for row in before[table] if row[key] == value]
    assert not [row for row in after["agent_recent_projects"] if row["project_name"] == target.name]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize("ambiguous", [False, True], ids=["absent", "ambiguous"])
async def test_postgres_delete_refuses_without_effects(delete_postgres_storage, test_agent, ambiguous):
    storage = delete_postgres_storage
    for suffix in ["a", "b"]:
        await _seed_delete_project(
            storage, name="shared", root=f"/tmp/delete-{suffix}", session=suffix,
            test_agent=f"{test_agent}:{suffix}",
        )
    before = await _delete_snapshot(storage)
    assert await storage.delete_project("shared" if ambiguous else "absent") is False
    assert await _delete_snapshot(storage) == before


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.storage
async def test_postgres_delete_sibling_committed_before_write(delete_postgres_storage, monkeypatch, test_agent):
    storage = delete_postgres_storage
    await _seed_delete_project(storage, name="shared", root="/tmp/delete-a", session="a", test_agent=test_agent)
    resolved, release = asyncio.Event(), asyncio.Event()
    original = storage.fetch_project

    async def pause_after_resolution(*args, **kwargs):
        project = await original(*args, **kwargs)
        resolved.set()
        await asyncio.wait_for(release.wait(), 10)
        return project

    monkeypatch.setattr(storage, "fetch_project", pause_after_resolution)
    deletion = asyncio.create_task(storage.delete_project("shared"))
    try:
        await asyncio.wait_for(resolved.wait(), 10)
        # A separate pool guarantees a different physical PostgreSQL connection.
        writer = PostgresStorage(storage._dsn, schema_name=storage.schema_name, pool_min_size=1)
        try:
            await writer.setup()
            await _seed_delete_project(
                writer, name="shared", root="/tmp/delete-b", session="b", test_agent=f"{test_agent}:sibling"
            )
        finally:
            await writer.close()
        before = await _delete_snapshot(storage)
        release.set()
        result = await asyncio.wait_for(deletion, 10)
        after = await _delete_snapshot(storage)
        assert after == before, "same-label insertion erased sibling data or compatibility rows"
        assert result is False
    finally:
        release.set()
        await asyncio.gather(deletion, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.storage
async def test_postgres_delete_cleanup_failure_rolls_back(delete_postgres_storage, test_agent):
    storage = delete_postgres_storage
    await _seed_delete_project(storage, name="shared", root="/tmp/delete-a", session="a", test_agent=test_agent)
    await storage._execute(
        "CREATE FUNCTION fail_delete_cleanup() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION 'injected delete cleanup failure'; END $$"
    )
    await storage._execute(
        "CREATE TRIGGER fail_delete_cleanup BEFORE UPDATE OR DELETE ON agent_projects "
        "FOR EACH ROW EXECUTE FUNCTION fail_delete_cleanup()"
    )
    before = await _delete_snapshot(storage)
    with pytest.raises(asyncpg.RaiseError, match="injected delete cleanup failure"):
        await storage.delete_project("shared")
    assert await _delete_snapshot(storage) == before


async def _wait_delete_lock(conn, query, *args):
    async def wait():
        while not await conn.fetchval(query, *args):
            await asyncio.sleep(0.01)
    await asyncio.wait_for(wait(), 10)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.storage
async def test_postgres_delete_inconsistent_key_refuses_without_effects(delete_postgres_storage, test_agent):
    storage = delete_postgres_storage
    await _seed_delete_project(storage, name="shared", root="/tmp/delete-a", session="a", test_agent=test_agent)
    foreign = await _seed_delete_project(
        storage, name="sibling", root="/tmp/delete-b", session="b", test_agent=f"{test_agent}:sibling"
    )
    # Model pre-existing corrupt data without changing production classification.
    await storage._execute("ALTER TABLE session_projects DISABLE TRIGGER USER")
    try:
        await storage._execute("UPDATE session_projects SET project_key=$1 WHERE session_id='a'", foreign.project_key)
    finally:
        await storage._execute("ALTER TABLE session_projects ENABLE TRIGGER USER")
    before = await _delete_snapshot(storage)
    with pytest.raises(postgres_module.ConflictError, match="inconsistent session binding"):
        await storage.delete_project("shared")
    assert await _delete_snapshot(storage) == before


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.storage
async def test_postgres_delete_sibling_insert_waits_for_delete(delete_postgres_storage, test_agent):
    storage = delete_postgres_storage
    await _seed_delete_project(storage, name="shared", root="/tmp/delete-a", session="a", test_agent=test_agent)
    settings = {"search_path": f"{storage.schema_name},public"}
    gate = await asyncpg.connect(storage._dsn, server_settings=settings)
    writer = await asyncpg.connect(storage._dsn, server_settings=settings)
    lock_key = int(uuid.uuid4().hex[:7], 16)
    deletion = insertion = None
    try:
        await gate.execute("SELECT pg_advisory_lock($1::bigint)", lock_key)
        await storage._execute(
            "CREATE FUNCTION pause_delete() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN PERFORM pg_advisory_xact_lock({lock_key}::bigint); RETURN OLD; END $$"
        )
        await storage._execute(
            "CREATE TRIGGER pause_delete BEFORE DELETE ON scribe_projects "
            "FOR EACH ROW EXECUTE FUNCTION pause_delete()"
        )
        deletion = asyncio.create_task(storage.delete_project("shared"))
        await _wait_delete_lock(
            gate, "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=$1 AND NOT granted)", lock_key
        )
        sibling_key = compute_project_key(repo_root="/tmp/delete-b", project_name="shared")
        insertion = asyncio.create_task(writer.fetchrow(
            "INSERT INTO scribe_projects(name, repo_root, project_key, progress_log_path, docs_json) "
            "VALUES ('shared', '/tmp/delete-b', $1, '/tmp/delete-b/PROGRESS_LOG.md', '{\"sibling\":true}') RETURNING *",
            sibling_key,
        ))
        # Observe actual server lock contention, not timing or a Python lock.
        await _wait_delete_lock(
            gate, "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=$1 AND locktype='relation' AND NOT granted)", writer.get_server_pid()
        )
        assert not insertion.done()
        await gate.execute("SELECT pg_advisory_unlock($1::bigint)", lock_key)
        assert await asyncio.wait_for(deletion, 10) is True
        inserted = await asyncio.wait_for(insertion, 10)
        # Populate all sibling payloads/defaults after the serialized insert.
        await writer.execute(
            "INSERT INTO scribe_sessions(session_id, agent_id, repo_root) VALUES ('b', $1, '/tmp/delete-b')", test_agent
        )
        await writer.execute("INSERT INTO session_projects(session_id, project_name) VALUES ('b', 'shared')")
        binding = dict(await writer.fetchrow("SELECT * FROM session_projects WHERE session_id='b'"))
        assert binding["project_key"] == sibling_key
        assert binding["binding_state"] == "resolved"
        assert binding["binding_generation"] == 1
        assert dict(await writer.fetchrow("SELECT * FROM scribe_projects WHERE id=$1", inserted["id"])) == dict(inserted)
        assert await storage.get_session_project("a") is None
        assert (await storage.get_agent_project(test_agent))["project_name"] is None
    finally:
        await gate.execute("SELECT pg_advisory_unlock($1::bigint)", lock_key)
        tasks = [task for task in (deletion, insertion) if task is not None]
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 15)
        finally:
            await writer.close()
            await gate.close()


@pytest.mark.asyncio
async def test_setup_repairs_repo_scoped_project_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    calls: list[str] = []

    async def fake_ensure_schema() -> None:
        calls.append("ensure_schema")

    async def fake_ensure_repo_scoped_project_identity() -> None:
        calls.append("ensure_repo_scoped_project_identity")

    monkeypatch.setattr(storage, "_ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(
        storage,
        "_ensure_repo_scoped_project_identity",
        fake_ensure_repo_scoped_project_identity,
    )

    await storage.setup()

    assert calls == ["ensure_schema", "ensure_repo_scoped_project_identity"]


@pytest.mark.asyncio
async def test_fetch_project_row_backfills_only_matched_legacy_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    legacy_name = "cortalabs_shared_context"
    legacy_root = "/home/austin/projects/CortaLabs"

    backfill_calls: list[dict[str, object]] = []
    row_after_backfill = {
        "id": 12,
        "name": legacy_name,
        "repo_root": legacy_root,
        "repo_id": "repo-1",
        "project_key": "pk-1",
        "progress_log_path": "/tmp/PROGRESS_LOG.md",
        "docs_json": None,
        "created_at": None,
        "updated_at": None,
        "bridge_id": None,
        "bridge_managed": False,
    }

    async def fake_ensure_repo_scoped_project_identity() -> None:
        return None

    async def fake_fetchval(query: str, *params):
        normalized = " ".join(query.split())
        if "SELECT COUNT(*) FROM scribe_projects WHERE name = $1;" in normalized:
            return 1
        raise AssertionError(f"unexpected fetchval query: {normalized} {params!r}")

    async def fake_fetchrow(query: str, *params):
        normalized = " ".join(query.split())
        if "FROM scribe_projects WHERE name = $1;" in normalized:
            return {
                "id": 12,
                "name": legacy_name,
                "repo_root": legacy_root,
                "repo_id": None,
                "project_key": None,
                "progress_log_path": "/tmp/PROGRESS_LOG.md",
                "docs_json": None,
                "created_at": None,
                "updated_at": None,
                "bridge_id": None,
                "bridge_managed": False,
            }
        if "FROM scribe_projects WHERE id = $1;" in normalized:
            return row_after_backfill
        raise AssertionError(f"unexpected fetchrow query: {normalized} {params!r}")

    async def fake_backfill_repo_scoped_project_identity_for_row(
        *,
        row_id: int,
        name: str,
        repo_root: str,
    ) -> None:
        backfill_calls.append(
            {
                "row_id": row_id,
                "name": name,
                "repo_root": repo_root,
            }
        )

    monkeypatch.setattr(
        storage,
        "_ensure_repo_scoped_project_identity",
        fake_ensure_repo_scoped_project_identity,
    )
    monkeypatch.setattr(storage, "_fetchval", fake_fetchval)
    monkeypatch.setattr(storage, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(
        storage,
        "_backfill_repo_scoped_project_identity_for_row",
        fake_backfill_repo_scoped_project_identity_for_row,
    )

    row = await storage._fetch_project_row(legacy_name)

    assert row == row_after_backfill
    assert backfill_calls == [
        {
            "row_id": 12,
            "name": legacy_name,
            "repo_root": legacy_root,
        }
    ]


@pytest.mark.asyncio
async def test_upsert_project_allows_same_name_across_repo_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    rows_by_key: dict[str, dict[str, object]] = {}

    async def fake_ensure_repo_scoped_project_identity() -> None:
        return None

    async def fake_fetchrow(query: str, *params: object):
        normalized = " ".join(query.split())
        if not normalized.startswith("INSERT INTO scribe_projects"):
            raise AssertionError(f"unexpected query: {normalized}")
        (
            name,
            repo_root,
            repo_id,
            project_key,
            progress_log_path,
            docs_json,
            bridge_id,
            bridge_managed,
        ) = params
        row = rows_by_key.setdefault(
            str(project_key),
            {
                "id": len(rows_by_key) + 1,
                "name": name,
                "repo_root": repo_root,
                "repo_id": repo_id,
                "project_key": project_key,
                "progress_log_path": progress_log_path,
                "docs_json": docs_json,
                "created_at": None,
                "updated_at": None,
                "bridge_id": bridge_id,
                "bridge_managed": bridge_managed,
            },
        )
        row.update(
            {
                "name": name,
                "repo_root": repo_root,
                "repo_id": repo_id,
                "progress_log_path": progress_log_path,
                "docs_json": docs_json,
                "bridge_id": bridge_id,
                "bridge_managed": bridge_managed,
            }
        )
        return row

    monkeypatch.setattr(
        storage,
        "_ensure_repo_scoped_project_identity",
        fake_ensure_repo_scoped_project_identity,
    )
    monkeypatch.setattr(storage, "_fetchrow", fake_fetchrow)

    first = await storage.upsert_project(
        name="shared_project",
        repo_root="/repo/a",
        progress_log_path="/repo/a/PROGRESS_LOG.md",
    )
    second = await storage.upsert_project(
        name="shared_project",
        repo_root="/repo/b",
        progress_log_path="/repo/b/PROGRESS_LOG.md",
    )

    assert first.name == second.name == "shared_project"
    assert first.repo_root == "/repo/a"
    assert second.repo_root == "/repo/b"
    assert first.project_key != second.project_key
    assert {row["repo_root"] for row in rows_by_key.values()} == {"/repo/a", "/repo/b"}


def test_record_tool_call_sync_bootstraps_schema_before_metadata_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe", schema_name="scribe")
    calls: list[tuple[str, object]] = []

    class FakeConn:
        async def execute(self, query: str, *params: object) -> str:
            calls.append(("execute", query))
            if "INSERT INTO tool_calls" in query:
                assert any(kind == "ensure_schema" for kind, _value in calls)
                assert "correlation_id" in query
                assert "measurement_scope" in query
            return "INSERT 0 1"

        async def close(self) -> None:
            calls.append(("close", None))

    async def fake_connect(*args: object, **kwargs: object) -> FakeConn:
        calls.append(("connect_kwargs", kwargs))
        return FakeConn()

    async def fake_ensure_schema_on_connection(**kwargs: object) -> None:
        calls.append(("ensure_schema", kwargs["schema_name"]))

    monkeypatch.setattr(postgres_module.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(
        postgres_module,
        "ensure_schema_on_connection",
        fake_ensure_schema_on_connection,
    )

    storage.record_tool_call_sync(
        session_id="session-1",
        tool_name="set_project",
        correlation_id="call-1",
        measurement_scope="tool_only",
    )

    connect_kwargs = next(value for kind, value in calls if kind == "connect_kwargs")
    insert_index = next(
        index
        for index, (kind, value) in enumerate(calls)
        if kind == "execute" and "INSERT INTO tool_calls" in str(value)
    )
    ensure_index = next(index for index, (kind, _value) in enumerate(calls) if kind == "ensure_schema")
    assert connect_kwargs["server_settings"] == {"search_path": "scribe,public"}
    assert ensure_index < insert_index
    assert calls[-1] == ("close", None)


@pytest.mark.asyncio
async def test_upsert_project_does_not_root_swap_on_legacy_unique_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    queries: list[str] = []

    async def fake_ensure_repo_scoped_project_identity() -> None:
        return None

    async def fake_fetchrow(query: str, *params: object):
        normalized = " ".join(query.split())
        queries.append(normalized)
        if normalized.startswith("INSERT INTO scribe_projects"):
            raise postgres_module.asyncpg.UniqueViolationError(
                'duplicate key value violates unique constraint "scribe_projects_name_key"'
            )
        raise AssertionError(f"unexpected query: {normalized}")

    monkeypatch.setattr(
        storage,
        "_ensure_repo_scoped_project_identity",
        fake_ensure_repo_scoped_project_identity,
    )
    monkeypatch.setattr(storage, "_fetchrow", fake_fetchrow)

    with pytest.raises(RuntimeError, match="refusing to change an existing project's repo_root"):
        await storage.upsert_project(
            name="shared_project",
            repo_root="/repo/b",
            progress_log_path="/repo/b/PROGRESS_LOG.md",
        )

    assert not any(query.startswith("UPDATE scribe_projects") for query in queries)

@pytest.mark.asyncio
async def test_ensure_repo_scoped_project_identity_drops_legacy_name_unique_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    calls: list[str] = []

    async def fake_ensure_column(table: str, column: str, definition: str) -> None:
        calls.append(f"ensure_column:{table}.{column}:{definition}")

    async def fake_execute(query: str, *params: object) -> str:
        calls.append(" ".join(query.split()))
        return "OK"

    async def fake_fetch(query: str, *params: object):
        calls.append(" ".join(query.split()))
        return []

    monkeypatch.setattr(storage, "_ensure_column", fake_ensure_column)
    monkeypatch.setattr(storage, "_execute", fake_execute)
    monkeypatch.setattr(storage, "_fetch", fake_fetch)

    await storage._ensure_repo_scoped_project_identity()

    assert calls[:2] == [
        "ensure_column:scribe_projects.repo_id:TEXT",
        "ensure_column:scribe_projects.project_key:TEXT",
    ]
    assert any(
        "ALTER TABLE agent_projects DROP CONSTRAINT IF EXISTS agent_projects_project_name_fkey"
        in call
        for call in calls
    )
    assert any(
        "ALTER TABLE session_projects DROP CONSTRAINT IF EXISTS session_projects_project_name_fkey"
        in call
        for call in calls
    )
    assert any(
        "ALTER TABLE agent_recent_projects DROP CONSTRAINT IF EXISTS agent_recent_projects_project_name_fkey"
        in call
        for call in calls
    )
    assert any(
        "DROP CONSTRAINT IF EXISTS scribe_projects_name_key" in call
        for call in calls
    )
    assert any(
        "DROP INDEX IF EXISTS scribe_projects_name_key" in call
        for call in calls
    )
    assert any(
        "idx_scribe_projects_project_key_unique ON scribe_projects(project_key)"
        in call
        for call in calls
    )


@pytest.mark.asyncio
async def test_ensure_repo_scoped_project_identity_backfills_before_unique_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    calls: list[str] = []

    async def fake_ensure_column(table: str, column: str, definition: str) -> None:
        calls.append(f"ensure_column:{table}.{column}:{definition}")

    async def fake_fetch(query: str, *params: object):
        calls.append("fetch_missing_identity_rows")
        return [
            {
                "id": 7,
                "name": "shared_project",
                "repo_root": "/repo/a",
            }
        ]

    async def fake_execute(query: str, *params: object) -> str:
        normalized = " ".join(query.split())
        if normalized.startswith("UPDATE scribe_projects"):
            calls.append(f"backfill_row:{params[3]}:{params[0]}:{params[1]}:{params[2]}")
        elif "idx_scribe_projects_project_key_unique" in normalized:
            calls.append("create_project_key_unique_index")
        else:
            calls.append(normalized)
        return "OK"

    monkeypatch.setattr(storage, "_ensure_column", fake_ensure_column)
    monkeypatch.setattr(storage, "_fetch", fake_fetch)
    monkeypatch.setattr(storage, "_execute", fake_execute)

    await storage._ensure_repo_scoped_project_identity()

    assert "backfill_row:7:/repo/a:" in next(
        call for call in calls if call.startswith("backfill_row:")
    )
    assert calls.index("fetch_missing_identity_rows") < calls.index(
        "create_project_key_unique_index"
    )


@pytest.mark.asyncio
async def test_ensure_repo_scoped_project_identity_deconflicts_legacy_alias_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    repo_root = "/repo/a"
    canonical_key = compute_project_key(repo_root=repo_root, project_name="alias-project")
    updated_keys: dict[int, str] = {}

    async def fake_ensure_column(table: str, column: str, definition: str) -> None:
        return None

    async def fake_fetch(query: str, *params: object):
        normalized = " ".join(query.split())
        if "SELECT project_key" in normalized:
            return []
        if "SELECT id, name, repo_root FROM scribe_projects" in normalized:
            assert "ORDER BY id" in normalized
            return [
                {"id": 7, "name": "alias-project", "repo_root": repo_root},
                {"id": 8, "name": "alias_project", "repo_root": repo_root},
            ]
        return []

    async def fake_execute(query: str, *params: object) -> str:
        normalized = " ".join(query.split())
        if normalized.startswith("UPDATE scribe_projects"):
            row_id = int(params[3])
            project_key = str(params[2])
            assert project_key not in updated_keys.values()
            updated_keys[row_id] = project_key
        return "OK"

    monkeypatch.setattr(storage, "_ensure_column", fake_ensure_column)
    monkeypatch.setattr(storage, "_fetch", fake_fetch)
    monkeypatch.setattr(storage, "_execute", fake_execute)

    await storage._ensure_repo_scoped_project_identity()

    assert updated_keys[7] == canonical_key
    assert updated_keys[8].startswith("pk_legacy_")
    assert updated_keys[8] != canonical_key


@pytest.mark.asyncio
async def test_preflight_project_identity_repair_is_read_only_and_schema_qualified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe", schema_name="scribe")
    calls: list[str] = []

    class FakeAcquire:
        async def __aenter__(self) -> "FakeConn":
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakePool:
        def acquire(self) -> FakeAcquire:
            return FakeAcquire()

    class FakeConn:
        async def fetchval(self, query: str, *params: object) -> object:
            normalized = " ".join(query.split())
            calls.append(normalized)
            forbidden = ("ALTER ", "CREATE ", "DROP ", "UPDATE ", "INSERT ", "DELETE ")
            assert not any(token in normalized.upper() for token in forbidden)
            if "information_schema.table_constraints" in normalized:
                return True
            if "pg_indexes" in normalized:
                return False
            if "information_schema.tables" in normalized:
                return False
            raise AssertionError(f"unexpected fetchval query: {normalized} {params!r}")

        async def fetch(self, query: str, *params: object):
            normalized = " ".join(query.split())
            calls.append(normalized)
            assert "FROM scribe.scribe_projects" in normalized
            assert "ORDER BY id" in normalized
            forbidden = ("ALTER ", "CREATE ", "DROP ", "UPDATE ", "INSERT ", "DELETE ")
            assert not any(token in normalized.upper() for token in forbidden)
            return [
                {"id": 7, "name": "alias-project", "repo_root": "repo-alpha", "repo_id": None, "project_key": None},
                {"id": 8, "name": "alias_project", "repo_root": "repo-alpha", "repo_id": None, "project_key": None},
            ]

    async def fake_ensure_pool() -> FakePool:
        return FakePool()

    async def fail_ensure_repo_scoped_project_identity() -> None:
        raise AssertionError("preflight must not call repo identity setup")

    async def fail_backfill_missing_repo_scoped_project_identity() -> None:
        raise AssertionError("preflight must not call repo identity backfill")

    monkeypatch.setattr(storage, "_ensure_pool", fake_ensure_pool)
    monkeypatch.setattr(
        storage,
        "_ensure_repo_scoped_project_identity",
        fail_ensure_repo_scoped_project_identity,
    )
    monkeypatch.setattr(
        storage,
        "_backfill_missing_repo_scoped_project_identity",
        fail_backfill_missing_repo_scoped_project_identity,
    )

    report = await storage.preflight_project_identity_repair()
    payload = report.to_public_dict()

    assert payload["mutation_attempted"] is False
    assert payload["mutation_authorized"] is False
    assert payload["legacy_name_constraint_present"] is True
    assert payload["canonical_retention_candidates"] == 1
    assert payload["legacy_key_assignment_candidates"] == 1
    assert calls


@pytest.mark.asyncio
async def test_fetch_project_row_returns_unique_canonical_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    display_name = "Display Project"
    canonical_name = "display_project"
    canonical_row = {
        "id": 44,
        "name": canonical_name,
        "repo_root": "/tmp/display-project",
        "repo_id": "repo-44",
        "project_key": "pk-44",
        "progress_log_path": "/tmp/display-project/PROGRESS_LOG.md",
        "docs_json": None,
        "created_at": None,
        "updated_at": None,
        "bridge_id": None,
        "bridge_managed": False,
    }

    async def fake_ensure_repo_scoped_project_identity() -> None:
        return None

    async def fake_fetchval(query: str, *params):
        normalized = " ".join(query.split())
        if "SELECT COUNT(*) FROM scribe_projects WHERE name = $1;" in normalized:
            if params == (display_name,):
                return 0
            if params == (canonical_name,):
                return 1
        raise AssertionError(f"unexpected fetchval query: {normalized} {params!r}")

    async def fake_fetchrow(query: str, *params):
        normalized = " ".join(query.split())
        if "FROM scribe_projects WHERE name = $1;" in normalized:
            if params == (display_name,):
                return None
            if params == (canonical_name,):
                return canonical_row
        raise AssertionError(f"unexpected fetchrow query: {normalized} {params!r}")

    monkeypatch.setattr(
        storage,
        "_ensure_repo_scoped_project_identity",
        fake_ensure_repo_scoped_project_identity,
    )
    monkeypatch.setattr(storage, "_fetchval", fake_fetchval)
    monkeypatch.setattr(storage, "_fetchrow", fake_fetchrow)

    row = await storage._fetch_project_row(display_name)

    assert row == canonical_row


@pytest.mark.asyncio
async def test_fetch_project_row_returns_none_for_ambiguous_canonical_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    display_name = "Display Project"
    canonical_name = "display_project"
    fetchrow_calls: list[tuple[object, ...]] = []

    async def fake_ensure_repo_scoped_project_identity() -> None:
        return None

    async def fake_fetchval(query: str, *params):
        normalized = " ".join(query.split())
        if "SELECT COUNT(*) FROM scribe_projects WHERE name = $1;" in normalized:
            if params == (display_name,):
                return 0
            if params == (canonical_name,):
                return 2
        raise AssertionError(f"unexpected fetchval query: {normalized} {params!r}")

    async def fake_fetchrow(query: str, *params):
        normalized = " ".join(query.split())
        if "FROM scribe_projects WHERE name = $1;" in normalized and params == (
            display_name,
        ):
            fetchrow_calls.append(params)
            return None
        raise AssertionError(f"unexpected fetchrow query: {normalized} {params!r}")

    monkeypatch.setattr(
        storage,
        "_ensure_repo_scoped_project_identity",
        fake_ensure_repo_scoped_project_identity,
    )
    monkeypatch.setattr(storage, "_fetchval", fake_fetchval)
    monkeypatch.setattr(storage, "_fetchrow", fake_fetchrow)

    row = await storage._fetch_project_row(display_name)

    assert row is None
    assert fetchrow_calls == [(display_name,)]


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("row_present", [True, False])
async def test_session_binding_reconstructs_structured_postgres_row(monkeypatch, row_present):
    storage = PostgresStorage("postgresql://example.invalid/scribe")
    updated = datetime(2026, 9, 28, tzinfo=timezone.utc)
    row = {"project_key": "durable-key", "project_name": "durable", "repo_root": "/repo/durable",
           "binding_generation": 7, "updated_at": updated}
    calls = []

    async def fetchrow(query, *params):
        calls.append((query, params))
        assert "project_key" in query and "binding_generation" in query
        assert "binding_state = 'resolved'" in query
        return row if row_present else None

    async def fetchval(*args):
        raise AssertionError("binding reconstruction must fetch the complete structured row")

    monkeypatch.setattr(storage, "_fetchrow", fetchrow)
    monkeypatch.setattr(storage, "_fetchval", fetchval)
    binding = await storage.get_session_project("caller-key")
    assert calls[0][1] == ("caller-key",)
    if not row_present:
        assert binding is None
        return
    assert binding == SessionBindingRecordV2(
        caller_session_key_hash=hashlib.sha256(b"caller-key").hexdigest(),
        project_key="durable-key", project_name="durable", canonical_repo_root="/repo/durable",
        binding_generation=7, updated_at=updated,
    )
