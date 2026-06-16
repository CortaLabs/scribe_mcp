from __future__ import annotations

import pytest

from scribe_mcp.storage.postgres import PostgresStorage


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
