from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.shared.tool_runtime import execute_tool_call


class _DummyState:
    @staticmethod
    def get_session_mode(_session_id: str):
        return None


class _DummyStateManager:
    async def load(self):
        return _DummyState()


class _CapturingRuntimeRouter:
    _process_instance_id = "proc-test"

    def __init__(self) -> None:
        self.last_payload: dict[str, object] | None = None

    async def get_or_create_session_id(self, _transport_session_id: str) -> str:
        return "stable-session-1"

    async def build_execution_context(self, payload: dict[str, object]):
        self.last_payload = dict(payload)
        return SimpleNamespace(
            mode=payload.get("mode", "project"),
            stable_session_id=payload.get("session_id", "stable-session-1"),
            repo_root=payload.get("repo_root"),
            transport_session_id=payload.get("transport_session_id"),
            session_id=payload.get("session_id", "stable-session-1"),
        )

    def set_current(self, _exec_context):
        return "token-1"

    def reset(self, _token):
        return None

    async def get_cached_project(self, _stable_session_id: str):
        return None


@pytest.mark.asyncio
async def test_execute_tool_call_set_project_does_not_trust_root_argument_as_context_repo_root(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    external_root = tmp_path / "external"
    external_root.mkdir()

    router = _CapturingRuntimeRouter()

    def set_project_stub(agent: str, name: str, root: str) -> dict[str, str]:
        return {"agent": agent, "name": name, "root": root}

    result = await execute_tool_call(
        name="set_project",
        arguments={"agent": "codex", "name": "demo", "root": str(external_root)},
        kwargs={},
        registry={"set_project": set_project_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(project_root=workspace_root),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"set_project"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result["root"] == str(external_root)
    assert router.last_payload is not None
    assert router.last_payload["repo_root"] == str(workspace_root.resolve())
