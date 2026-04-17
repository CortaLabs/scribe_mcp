from __future__ import annotations

from types import SimpleNamespace

import pytest

from scribe_mcp.doc_management.runtime import _resolve_manage_docs_actor_id


class _Identity:
    async def get_or_create_agent_id(self) -> str:
        return "agent-20260417-abc12345"


@pytest.mark.asyncio
async def test_resolve_manage_docs_actor_prefers_caller_agent() -> None:
    execution_context = SimpleNamespace(agent_identity=SimpleNamespace(display_name="ReviewAgent"))
    server_module = SimpleNamespace(get_agent_identity=lambda: _Identity())

    actor_id = await _resolve_manage_docs_actor_id(
        caller_agent="ReviewAgent",
        execution_context=execution_context,
        server_module=server_module,
    )

    assert actor_id == "ReviewAgent"


@pytest.mark.asyncio
async def test_resolve_manage_docs_actor_prefers_execution_display_name() -> None:
    execution_context = SimpleNamespace(agent_identity=SimpleNamespace(display_name="ReviewAgent"))
    server_module = SimpleNamespace(get_agent_identity=lambda: _Identity())

    actor_id = await _resolve_manage_docs_actor_id(
        caller_agent=None,
        execution_context=execution_context,
        server_module=server_module,
    )

    assert actor_id == "ReviewAgent"


@pytest.mark.asyncio
async def test_resolve_manage_docs_actor_falls_back_to_internal_id() -> None:
    execution_context = SimpleNamespace(agent_identity=SimpleNamespace(display_name=None))
    server_module = SimpleNamespace(get_agent_identity=lambda: _Identity())

    actor_id = await _resolve_manage_docs_actor_id(
        caller_agent=None,
        execution_context=execution_context,
        server_module=server_module,
    )

    assert actor_id == "agent-20260417-abc12345"
