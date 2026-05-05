from __future__ import annotations

import asyncio

import pytest

from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.storage.base import ConflictError


class _CollisionRecoveringBackend:
    def __init__(self) -> None:
        self.upsert_calls = 0
        self.lookup_calls = 0

    async def get_session_by_transport(self, _transport_session_id: str):
        self.lookup_calls += 1
        if self.lookup_calls == 1:
            return None
        return {"session_id": "stable-existing"}

    async def upsert_session(self, **_kwargs) -> None:
        self.upsert_calls += 1
        raise ConflictError("transport_session_id collision detected; refusing ambiguous session binding")


def test_get_or_create_session_id_recovers_from_transport_collision() -> None:
    async def _run() -> None:
        backend = _CollisionRecoveringBackend()
        router = RouterContextManager(storage_backend=backend)

        session_id = await router.get_or_create_session_id("transport-shared")
        cached = await router.get_or_create_session_id("transport-shared")

        assert session_id == "stable-existing"
        assert cached == "stable-existing"
        assert backend.upsert_calls == 1

    asyncio.run(_run())
