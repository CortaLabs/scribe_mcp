from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from scribe_mcp.storage.base import ConflictError
from scribe_mcp.storage.postgres import PostgresStorage
from scribe_mcp.storage.sqlite import SQLiteStorage


def _sid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@pytest_asyncio.fixture
async def sqlite_storage(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "p31_storage.sqlite3")
    await storage.setup()
    try:
        yield storage
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_sqlite_session_linkage_invariants(sqlite_storage: SQLiteStorage) -> None:
    session_primary = _sid("sqlite_p31_primary")
    session_collision = _sid("sqlite_p31_collision")
    transport = _sid("sqlite_transport")

    await sqlite_storage.upsert_session(
        session_id=session_primary,
        transport_session_id=transport,
        agent_id="sia",
        repo_root="/tmp/sqlite",
        mode="project",
    )

    with pytest.raises(ConflictError, match="unknown session_id"):
        await sqlite_storage.set_session_project(_sid("sqlite_missing"), None)

    with pytest.raises(ConflictError, match="transport_session_id collision"):
        await sqlite_storage.upsert_session(
            session_id=session_collision,
            transport_session_id=transport,
            agent_id="sia",
            repo_root="/tmp/sqlite",
            mode="project",
        )

    # get_session_by_transport only resolves sessions with a live
    # agent_sessions linkage (hardened contract), so create it first.
    await sqlite_storage.upsert_agent_session("sia", session_primary, None)

    resolved = await sqlite_storage.get_session_by_transport(transport)
    assert resolved is not None
    assert resolved["session_id"] == session_primary


@pytest_asyncio.fixture
async def postgres_storage():
    dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip("Set SCRIBE_TEST_POSTGRES_URL to run Postgres storage invariants")
    storage = PostgresStorage(dsn)
    await storage.setup()
    try:
        yield storage
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_postgres_session_linkage_invariants(postgres_storage: PostgresStorage) -> None:
    session_primary = _sid("postgres_p31_primary")
    session_collision = _sid("postgres_p31_collision")
    transport = _sid("postgres_transport")

    await postgres_storage.upsert_session(
        session_id=session_primary,
        transport_session_id=transport,
        agent_id="sia",
        repo_root="/tmp/postgres",
        mode="project",
    )
    await postgres_storage._execute(
        "DELETE FROM agent_sessions WHERE session_id = $1;",
        session_primary,
    )
    assert await postgres_storage.fetch_agent_session(session_primary) is None

    with pytest.raises(ConflictError, match="unknown session_id"):
        await postgres_storage.set_session_project(_sid("postgres_missing"), None)

    with pytest.raises(ConflictError, match="transport_session_id collision"):
        await postgres_storage.upsert_session(
            session_id=session_collision,
            transport_session_id=transport,
            agent_id="sia",
            repo_root="/tmp/postgres",
            mode="project",
        )

    resolved = await postgres_storage.get_session_by_transport(transport)
    assert resolved is not None
    assert resolved["session_id"] == session_primary
