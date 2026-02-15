#!/usr/bin/env python3
"""Tests for ExecutionContext session identity requirements."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.bridges.manifest import BridgeManifest
from scribe_mcp.cli.main import (
    _load_tracked_reads,
    _normalize_tracked_path,
    _rehydrate_file_reads,
    _result_is_success,
)
from scribe_mcp.config.paths import templates_dir
from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared.tool_runtime import execute_tool_call
from scribe_mcp.template_engine import Jinja2TemplateEngine


@pytest.mark.asyncio
async def test_execution_context_requires_session_id():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
    }
    with pytest.raises(ValueError, match="transport_session_id or session_id"):
        await router.build_execution_context(payload)


@pytest.mark.asyncio
async def test_execution_context_transport_session_id_is_stable():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "transport_session_id": "conn-1",
    }
    first = await router.build_execution_context(payload)
    second = await router.build_execution_context(payload)
    assert first.session_id == second.session_id
    assert first.transport_session_id == "conn-1"


@pytest.mark.asyncio
async def test_execution_context_accepts_explicit_session_id():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "session_id": "session-explicit",
    }
    ctx = await router.build_execution_context(payload)
    assert ctx.session_id == "session-explicit"


class _DummyRuntimeRouter:
    _process_instance_id = "proc-test"

    async def get_or_create_session_id(self, _transport_session_id: str) -> str:
        return "session-1"

    async def build_execution_context(self, payload):
        return SimpleNamespace(mode=payload.get("mode", "project"), stable_session_id="stable-1")

    def set_current(self, _exec_context):
        return "token-1"

    def reset(self, _token):
        return None

    async def get_cached_project(self, _stable_session_id: str):
        return "cached-project"


class _CachingRuntimeRouter(_DummyRuntimeRouter):
    def __init__(self) -> None:
        self._stable_cache: dict[str, str] = {}

    async def get_cached_agent_session_id(self, identity_key: str) -> str | None:
        return self._stable_cache.get(identity_key)

    async def cache_agent_session_id(self, identity_key: str, session_id: str) -> None:
        self._stable_cache[identity_key] = session_id


class _DummyState:
    @staticmethod
    def get_session_mode(_session_id: str):
        return None


class _DummyStateManager:
    async def load(self):
        return _DummyState()


class _CountingStorageBackend:
    def __init__(self) -> None:
        self.calls = 0

    async def get_or_create_agent_session(self, **_kwargs):
        self.calls += 1
        return "stable-1"


@pytest.mark.asyncio
async def test_execute_tool_call_does_not_inject_project_to_set_project():
    def set_project_stub(agent: str, name: str, root: str) -> dict[str, str]:
        return {"agent": agent, "name": name, "root": root}

    result = await execute_tool_call(
        name="set_project",
        arguments={"agent": "codex", "name": "demo", "root": "/tmp/demo"},
        kwargs={},
        registry={"set_project": set_project_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(project_root=Path("/tmp")),
        state_manager=_DummyStateManager(),
        router_context_manager=_DummyRuntimeRouter(),
        sentinel_only=set(),
        sentinel_allowed={"set_project"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == {"agent": "codex", "name": "demo", "root": "/tmp/demo"}


@pytest.mark.asyncio
async def test_execute_tool_call_injects_project_for_project_aware_tool():
    def read_recent_stub(agent: str, project: str | None = None) -> str | None:
        return project

    result = await execute_tool_call(
        name="read_recent",
        arguments={"agent": "codex"},
        kwargs={},
        registry={"read_recent": read_recent_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(project_root=Path("/tmp")),
        state_manager=_DummyStateManager(),
        router_context_manager=_DummyRuntimeRouter(),
        sentinel_only=set(),
        sentinel_allowed={"read_recent"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == "cached-project"


@pytest.mark.asyncio
async def test_execute_tool_call_reuses_cached_stable_session_id():
    def noop_stub(agent: str) -> str:
        return agent

    router = _CachingRuntimeRouter()
    backend = _CountingStorageBackend()

    kwargs = {
        "context": {
            "repo_root": "/tmp",
            "mode": "project",
            "session_id": "session-1",
        }
    }

    result_one = await execute_tool_call(
        name="noop",
        arguments={"agent": "codex"},
        kwargs=kwargs,
        registry={"noop": noop_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=backend,
        settings=SimpleNamespace(project_root=Path("/tmp")),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"noop"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    result_two = await execute_tool_call(
        name="noop",
        arguments={"agent": "codex"},
        kwargs=kwargs,
        registry={"noop": noop_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=backend,
        settings=SimpleNamespace(project_root=Path("/tmp")),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"noop"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result_one == "codex"
    assert result_two == "codex"
    assert backend.calls == 1


def test_templates_dir_contains_builtin_documents():
    root = templates_dir()
    assert root.exists()
    assert (root / "documents" / "ARCHITECTURE_GUIDE_TEMPLATE.md").exists()


def test_template_engine_can_validate_builtin_document_templates():
    engine = Jinja2TemplateEngine(project_root=Path("/tmp"), project_name="template-probe")
    validation = engine.validate_template("documents/ARCHITECTURE_GUIDE_TEMPLATE.md")
    assert validation["valid"], validation


def test_bridge_manifest_hooks_support_keyed_config_without_hook_name_field():
    manifest = BridgeManifest.from_dict(
        {
            "bridge_id": "example_bridge",
            "name": "Example Bridge",
            "version": "1.0.0",
            "description": "Bridge",
            "author": "Scribe Team",
            "hooks": {
                "pre_append": {"callback_type": "async", "timeout_ms": 5000, "critical": False},
                "post_append": {"callback_type": "async", "timeout_ms": 5000, "critical": False},
            },
        }
    )

    assert manifest.hooks["pre_append"].hook_name == "pre_append"
    assert manifest.hooks["post_append"].hook_name == "post_append"
    assert manifest.validate() == []


def test_bridge_manifest_hooks_preserve_explicit_hook_name_override():
    manifest = BridgeManifest.from_dict(
        {
            "bridge_id": "bridge_test",
            "name": "Bridge Test",
            "version": "1.0.0",
            "description": "Bridge",
            "author": "Scribe Team",
            "hooks": {
                "pre_append": {
                    "hook_name": "pre_append_custom",
                    "callback_type": "async",
                    "timeout_ms": 5000,
                    "critical": False,
                }
            },
        }
    )

    assert manifest.hooks["pre_append"].hook_name == "pre_append_custom"


@pytest.mark.asyncio
async def test_background_service_status_tracks_success():
    from scribe_mcp import server as server_module

    server_module._background_services.clear()

    async def _work() -> None:
        await asyncio.sleep(0)

    task = server_module.schedule_background_task(
        _work(),
        service_name="unit_success",
        description="unit test successful task",
    )
    await task

    status = server_module.get_background_service_status()["unit_success"]
    assert status["status"] == "healthy"
    assert status["last_error"] is None
    assert status["last_duration_ms"] is not None


@pytest.mark.asyncio
async def test_background_service_status_tracks_failure():
    from scribe_mcp import server as server_module

    server_module._background_services.clear()

    async def _work() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("unit boom")

    task = server_module.schedule_background_task(
        _work(),
        service_name="unit_failure",
        description="unit test failing task",
    )
    with pytest.raises(RuntimeError, match="unit boom"):
        await task

    status = server_module.get_background_service_status()["unit_failure"]
    assert status["status"] == "failed"
    assert "unit boom" in (status["last_error"] or "")


def test_cli_path_tracking_normalizes_and_filters_outside_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "inside.txt").write_text("ok", encoding="utf-8")

    normalized_inside = _normalize_tracked_path(repo_root, "inside.txt")
    assert normalized_inside == str((repo_root / "inside.txt").resolve())

    assert _normalize_tracked_path(repo_root, str(tmp_path / "outside.txt")) is None


def test_cli_load_tracked_reads_deduplicates_entries(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "a.txt").write_text("a", encoding="utf-8")

    context = {
        "files_read": [
            "a.txt",
            str((repo_root / "a.txt").resolve()),
            str(tmp_path / "outside.txt"),
            42,
        ]
    }

    reads = _load_tracked_reads(context, repo_root)
    assert reads == [str((repo_root / "a.txt").resolve())]


def test_cli_result_success_detection_handles_mcp_and_tool_shapes() -> None:
    assert _result_is_success({"isError": False}) is True
    assert _result_is_success({"isError": True}) is False
    assert _result_is_success({"ok": True}) is True
    assert _result_is_success({"ok": False}) is False
    assert _result_is_success({"error": "boom"}) is False


@pytest.mark.asyncio
async def test_cli_rehydrate_file_reads_replays_paths() -> None:
    recorded: list[tuple[str, str]] = []

    class _DummyManager:
        async def record_file_read(self, session_id: str, file_path: str) -> None:
            recorded.append((session_id, file_path))

    dummy_server = SimpleNamespace(router_context_manager=_DummyManager())
    await _rehydrate_file_reads(
        server_module=dummy_server,
        session_id="session-123",
        tracked_reads=["/tmp/a.py", "/tmp/b.py"],
    )

    assert recorded == [
        ("session-123", "/tmp/a.py"),
        ("session-123", "/tmp/b.py"),
    ]
