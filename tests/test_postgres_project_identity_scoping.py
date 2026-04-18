from __future__ import annotations

import pytest

from scribe_mcp.storage.postgres import PostgresStorage


@pytest.mark.asyncio
async def test_fetch_project_row_backfills_only_matched_legacy_row(monkeypatch: pytest.MonkeyPatch) -> None:
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
