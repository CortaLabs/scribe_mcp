#!/usr/bin/env python3
"""Unit tests for sqlite session-domain resilience paths."""

from __future__ import annotations

import sqlite3

import pytest

from scribe_mcp.storage.sqlite.sessions import get_or_create_agent_session


@pytest.mark.asyncio
async def test_get_or_create_agent_session_returns_existing_row() -> None:
    calls = {"exec": 0}

    async def _init() -> None:
        return None

    async def _execute(_query: str, _params: tuple[object, ...]) -> None:
        calls["exec"] += 1

    async def _fetchone(_query: str, _params: tuple[object, ...]):
        return {"session_id": "existing-session"}

    session_id = await get_or_create_agent_session(
        initialise_fn=_init,
        write_lock=DummyAsyncLock(),
        execute_fn=_execute,
        fetchone_fn=_fetchone,
        identity_key="k1",
        agent_name="Codex",
        agent_key="Codex",
        repo_root="/tmp/repo",
        mode="project",
        scope_key="scope",
    )

    assert session_id == "existing-session"
    assert calls["exec"] == 1


@pytest.mark.asyncio
async def test_get_or_create_agent_session_uses_returning_upsert() -> None:
    calls = {"fetch": 0}

    async def _init() -> None:
        return None

    async def _execute(_query: str, _params: tuple[object, ...]) -> None:
        raise AssertionError("execute_fn should not be used when RETURNING path succeeds")

    async def _fetchone(_query: str, _params: tuple[object, ...]):
        calls["fetch"] += 1
        if calls["fetch"] == 1:
            return None
        if calls["fetch"] == 2:
            return {"session_id": "upsert-session"}
        raise AssertionError("unexpected fetchone call")

    session_id = await get_or_create_agent_session(
        initialise_fn=_init,
        write_lock=DummyAsyncLock(),
        execute_fn=_execute,
        fetchone_fn=_fetchone,
        identity_key="k2",
        agent_name="Codex",
        agent_key="Codex",
        repo_root="/tmp/repo",
        mode="project",
        scope_key="scope",
    )

    assert session_id == "upsert-session"


@pytest.mark.asyncio
async def test_get_or_create_agent_session_falls_back_when_returning_unsupported() -> None:
    calls = {"fetch": 0, "exec": 0}

    async def _init() -> None:
        return None

    async def _execute(_query: str, _params: tuple[object, ...]) -> None:
        calls["exec"] += 1

    async def _fetchone(_query: str, _params: tuple[object, ...]):
        calls["fetch"] += 1
        if calls["fetch"] == 1:
            return None
        if calls["fetch"] == 2:
            raise sqlite3.OperationalError("near \"RETURNING\": syntax error")
        if calls["fetch"] == 3:
            return {"session_id": "legacy-session"}
        raise AssertionError("unexpected fetchone call")

    session_id = await get_or_create_agent_session(
        initialise_fn=_init,
        write_lock=DummyAsyncLock(),
        execute_fn=_execute,
        fetchone_fn=_fetchone,
        identity_key="k3",
        agent_name="Codex",
        agent_key="Codex",
        repo_root="/tmp/repo",
        mode="project",
        scope_key="scope",
    )

    assert session_id == "legacy-session"
    assert calls["exec"] == 2


@pytest.mark.asyncio
async def test_get_or_create_agent_session_uses_tuple_recovery_when_identity_missing() -> None:
    calls = {"fetch": 0, "exec": 0}

    async def _init() -> None:
        return None

    async def _execute(_query: str, _params: tuple[object, ...]) -> None:
        calls["exec"] += 1

    async def _fetchone(_query: str, _params: tuple[object, ...]):
        calls["fetch"] += 1
        if calls["fetch"] == 1:
            return None
        if calls["fetch"] == 2:
            return None
        if calls["fetch"] == 3:
            return None
        if calls["fetch"] == 4:
            return {"session_id": "recovered-session"}
        raise AssertionError("unexpected fetchone call")

    session_id = await get_or_create_agent_session(
        initialise_fn=_init,
        write_lock=DummyAsyncLock(),
        execute_fn=_execute,
        fetchone_fn=_fetchone,
        identity_key="k4",
        agent_name="Codex",
        agent_key="Codex",
        repo_root="/tmp/repo",
        mode="project",
        scope_key="scope",
    )

    assert session_id == "recovered-session"
    assert calls["exec"] == 2


class DummyAsyncLock:
    async def __aenter__(self) -> "DummyAsyncLock":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        _ = (exc_type, exc, tb)
        return False
