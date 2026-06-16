from __future__ import annotations

import pytest

import scribe_mcp.storage.postgres as postgres_module
from scribe_mcp.storage.postgres import PostgresStorage


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
