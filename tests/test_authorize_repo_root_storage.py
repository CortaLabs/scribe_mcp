from __future__ import annotations

import asyncio
from pathlib import Path

from scribe_mcp.storage.models import compute_repo_id, normalize_repo_root
from scribe_mcp.storage.sqlite import SQLiteStorage


def test_sqlite_repo_scope_grant_persists_and_fetches(tmp_path: Path) -> None:
    async def _run() -> None:
        db_path = tmp_path / "grants.sqlite3"
        storage = SQLiteStorage(db_path)
        await storage.setup()
        try:
            raw_repo_root = str(tmp_path / "repo" / ".." / "repo")
            expected_root = normalize_repo_root(raw_repo_root)

            grant = await storage.create_repo_scope_grant(
                authoritative_session_key="sess-key-1",
                repo_root=raw_repo_root,
                reason="phase-1.2a test",
                ttl_minutes=30,
            )

            assert grant.grant_id
            assert grant.authoritative_session_key == "sess-key-1"
            assert grant.repo_root == expected_root
            assert grant.repo_id == compute_repo_id(expected_root)
            assert grant.reason == "phase-1.2a test"

            fetched = await storage.fetch_repo_scope_grant(grant.grant_id)
            assert fetched is not None
            assert fetched.grant_id == grant.grant_id
            assert fetched.repo_root == expected_root
            assert fetched.repo_id == compute_repo_id(expected_root)
        finally:
            await storage.close()

    asyncio.run(_run())


def test_sqlite_repo_scope_grant_expired_not_returned(tmp_path: Path) -> None:
    async def _run() -> None:
        storage = SQLiteStorage(tmp_path / "grants_expired.sqlite3")
        await storage.setup()
        try:
            grant = await storage.create_repo_scope_grant(
                authoritative_session_key="sess-key-2",
                repo_root=str(tmp_path),
                reason="expired",
                ttl_minutes=-1,
            )

            assert grant.grant_id
            assert await storage.fetch_repo_scope_grant(grant.grant_id) is None
        finally:
            await storage.close()

    asyncio.run(_run())
