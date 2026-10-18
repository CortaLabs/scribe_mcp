from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.execution_context import AgentIdentity, ExecutionContext
from scribe_mcp.tools.read_file import read_file


def _install_execution_context(repo_root: Path) -> object:
    context = ExecutionContext(
        repo_root=str(repo_root),
        mode="sentinel",
        session_id="read-only-session",
        execution_id="read-only-exec",
        agent_identity=AgentIdentity(
            agent_kind="test",
            model=None,
            instance_id="test-agent",
            sub_id=None,
            display_name=None,
        ),
        intent="read_file_read_only_contract",
        timestamp_utc="2026-04-17T00:00:00+00:00",
        affected_dev_projects=[],
        sentinel_day="2026-04-17",
    )
    return server_module.router_context_manager.set_current(context)


class _FakeDocumentStore:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def read(self, _key: str) -> str:
        self.calls += 1
        return self.content


@pytest.mark.asyncio
async def test_read_file_missing_synced_doc_does_not_write_or_hydrate_local_path(tmp_path: Path) -> None:
    token = _install_execution_context(tmp_path)
    original_store = getattr(server_module.app.state, "document_store", None)
    fake_store = _FakeDocumentStore("remote content that must not be hydrated during read")
    server_module.app.state.document_store = fake_store
    missing = tmp_path / "docs" / "missing.md"

    try:
        result = await read_file(
            agent="test-agent",
            path=str(missing),
            mode="full",
            format="structured",
        )

        assert result["ok"] is False
        assert result["error"] == "file not found"
        assert missing.exists() is False
        assert fake_store.calls == 0
    finally:
        server_module.router_context_manager.reset(token)
        if original_store is None:
            try:
                delattr(server_module.app.state, "document_store")
            except AttributeError:
                pass
        else:
            server_module.app.state.document_store = original_store
