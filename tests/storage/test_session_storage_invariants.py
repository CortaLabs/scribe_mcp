from __future__ import annotations

import os
import uuid
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import get_type_hints

import pytest
import pytest_asyncio

from scribe_mcp.storage.base import ConflictError
from scribe_mcp.storage.models import SessionBindingRecordV2
from scribe_mcp.storage.postgres import PostgresStorage
from scribe_mcp.storage.sqlite import SQLiteStorage


def _sid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@pytest.mark.core
@pytest.mark.regression
def test_session_binding_record_v2_contract() -> None:
    updated_at = datetime.now(timezone.utc)
    valid = {
        "caller_session_key_hash": "a" * 64,
        "project_key": "pk_example",
        "project_name": "example",
        "canonical_repo_root": "/tmp/example",
        "binding_generation": 1,
        "updated_at": updated_at,
    }

    record = SessionBindingRecordV2(**valid)

    assert tuple(field.name for field in fields(record)) == (
        "caller_session_key_hash",
        "project_key",
        "project_name",
        "canonical_repo_root",
        "binding_generation",
        "updated_at",
    )
    assert get_type_hints(SessionBindingRecordV2) == {
        "caller_session_key_hash": str,
        "project_key": str,
        "project_name": str,
        "canonical_repo_root": str,
        "binding_generation": int,
        "updated_at": datetime,
    }
    assert record.updated_at is updated_at
    with pytest.raises(FrozenInstanceError):
        setattr(record, "project_name", "other")

    for invalid_generation in (0, -1, True):
        with pytest.raises(ValueError, match="binding_generation must be a positive integer"):
            SessionBindingRecordV2(**{**valid, "binding_generation": invalid_generation})

    with pytest.raises(ValueError, match="updated_at must be timezone-aware"):
        SessionBindingRecordV2(**{**valid, "updated_at": datetime.now()})

    for field_name in ("project_key", "project_name", "canonical_repo_root"):
        for invalid_identity in ("", None, 123):
            with pytest.raises(ValueError, match=rf"{field_name} must be a non-empty string"):
                SessionBindingRecordV2(
                    **{**valid, field_name: invalid_identity}  # type: ignore[arg-type]
                )

    for malformed_digest in ("", "a" * 63, "a" * 65, "A" * 64, "z" * 64, None, 123):
        with pytest.raises((TypeError, ValueError)):
            SessionBindingRecordV2(
                **{**valid, "caller_session_key_hash": malformed_digest}  # type: ignore[arg-type]
            )


@pytest_asyncio.fixture
async def sqlite_storage(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "p31_storage.sqlite3")
    await storage.setup()
    try:
        yield storage
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_sqlite_session_linkage_invariants(sqlite_storage: SQLiteStorage, test_agent) -> None:
    session_primary = _sid("sqlite_p31_primary")
    session_collision = _sid("sqlite_p31_collision")
    transport = _sid("sqlite_transport")

    await sqlite_storage.upsert_session(
        session_id=session_primary,
        transport_session_id=transport,
        agent_id=test_agent,
        repo_root="/tmp/sqlite",
        mode="project",
    )

    target = await sqlite_storage.upsert_project(
        name=_sid("sqlite_target"), repo_root="/tmp/sqlite",
        progress_log_path="/tmp/sqlite/PROGRESS_LOG.md")
    with pytest.raises(ConflictError, match="unknown session_id"):
        await sqlite_storage.set_session_project(_sid("sqlite_missing"), target.project_key)
    assert callable(getattr(sqlite_storage, "clear_session_project", None)), (
        "Frozen contract absent: SQLiteStorage.clear_session_project")
    with pytest.raises(ConflictError, match="unknown session_id"):
        await sqlite_storage.clear_session_project(_sid("sqlite_missing"))

    with pytest.raises(ConflictError, match="transport_session_id collision"):
        await sqlite_storage.upsert_session(
            session_id=session_collision,
            transport_session_id=transport,
            agent_id=test_agent,
            repo_root="/tmp/sqlite",
            mode="project",
        )

    # get_session_by_transport only resolves sessions with a live
    # agent_sessions linkage (hardened contract), so create it first.
    await sqlite_storage.upsert_agent_session(test_agent, session_primary, None)

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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_session_linkage_invariants(postgres_storage: PostgresStorage, test_agent) -> None:
    session_primary = _sid("postgres_p31_primary")
    session_collision = _sid("postgres_p31_collision")
    transport = _sid("postgres_transport")

    await postgres_storage.upsert_session(
        session_id=session_primary,
        transport_session_id=transport,
        agent_id=test_agent,
        repo_root="/tmp/postgres",
        mode="project",
    )
    await postgres_storage._execute(
        "DELETE FROM agent_sessions WHERE session_id = $1;",
        session_primary,
    )
    assert await postgres_storage.fetch_agent_session(session_primary) is None

    target = await postgres_storage.upsert_project(
        name=_sid("postgres_target"), repo_root="/tmp/postgres",
        progress_log_path="/tmp/postgres/PROGRESS_LOG.md")
    with pytest.raises(ConflictError, match="unknown session_id"):
        await postgres_storage.set_session_project(_sid("postgres_missing"), target.project_key)
    assert callable(getattr(postgres_storage, "clear_session_project", None)), (
        "Frozen contract absent: PostgresStorage.clear_session_project")
    with pytest.raises(ConflictError, match="unknown session_id"):
        await postgres_storage.clear_session_project(_sid("postgres_missing"))

    with pytest.raises(ConflictError, match="transport_session_id collision"):
        await postgres_storage.upsert_session(
            session_id=session_collision,
            transport_session_id=transport,
            agent_id=test_agent,
            repo_root="/tmp/postgres",
            mode="project",
        )

    resolved = await postgres_storage.get_session_by_transport(transport)
    assert resolved is not None
    assert resolved["session_id"] == session_primary
