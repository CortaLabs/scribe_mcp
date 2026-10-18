"""SCRIBEHOOK.2 — generic read-event dispatch wiring in ``execute_tool_call``.

These tests prove the single dispatch chokepoint
(``scribe_mcp.shared.tool_runtime.execute_tool_call``) fires the generic
SCRIBEHOOK.1 ``pre_read``/``post_read`` vocabulary around a read result, keyed
strictly on the tool name and entirely fail-open:

1. A live ``read_file`` call through ``execute_tool_call`` surfaces an arbitrary
   plugin's ``post_read`` payload in ``result["read_annotations"]`` (and pre_read
   fires before the read).
2. A non-read tool name never invokes the read hooks.
3. A raising read-hook never breaks the read — the original result is intact
   (proven against the live ``read_file`` and against a stub).
4. Keying is purely on the tool name (a stub named ``read_file`` fires the same
   path; a raising plugin is isolated while a co-registered recording plugin
   still annotates — core result fields are preserved).

The wiring is content-agnostic: no council/RI concept appears anywhere.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest

from scribe_mcp import server
from scribe_mcp.plugins.registry import HookPlugin, get_plugin_registry
from scribe_mcp.server import _SENTINEL_ALLOWED_TOOLS, _SENTINEL_ONLY_TOOLS
from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.shared.tool_runtime import execute_tool_call

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# A committed, read-only file inside the repo scope (never mutated by these
# tests) used to exercise the live ``read_file`` path deterministically.
LIVE_READ_TARGET = REPO_ROOT / "pyproject.toml"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _DummyState:
    @staticmethod
    def get_session_mode(_session_id: str) -> Optional[str]:
        return None


class _DummyStateManager:
    async def load(self) -> _DummyState:
        return _DummyState()


class _RecordingHookPlugin(HookPlugin):
    """Generic (non-RI) hook plugin that records calls and annotates reads."""

    name = "scribehook2-recording-test"

    def __init__(self, marker: str = "generic-annotation") -> None:
        self._marker = marker
        self.pre_calls: List[Tuple[str, Dict[str, Any]]] = []
        self.post_calls: List[Tuple[str, Dict[str, Any]]] = []

    def initialize(self, config: Any) -> None:  # abstract on ScribePlugin
        return None

    def pre_read(self, path: str, context: Dict[str, Any]) -> None:
        self.pre_calls.append((path, dict(context)))

    def post_read(
        self, path: str, result: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        self.post_calls.append((path, dict(context)))
        return {"scribehook2_marker": self._marker, "annotated_path": path}


class _RaisingHookPlugin(HookPlugin):
    """Generic hook plugin whose read hooks always raise (fail-open probe)."""

    name = "scribehook2-raising-test"

    def initialize(self, config: Any) -> None:
        return None

    def pre_read(self, path: str, context: Dict[str, Any]) -> None:
        raise RuntimeError("boom: pre_read must never break the read")

    def post_read(
        self, path: str, result: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        raise RuntimeError("boom: post_read must never break the read")


@contextlib.contextmanager
def _registered_hooks(*plugins: HookPlugin) -> Iterator[None]:
    """Inject hook plugins into the live registry and restore exactly on exit.

    Hermetic: only the injected instances are removed; any pre-existing plugins
    are left untouched.
    """
    registry = get_plugin_registry()
    for plugin in plugins:
        registry.hook_plugins.append(plugin)
    try:
        yield
    finally:
        for plugin in plugins:
            with contextlib.suppress(ValueError):
                registry.hook_plugins.remove(plugin)


def _registered_tool_registry() -> Dict[str, Any]:
    server.list_registered_tools()
    registry = getattr(type(server.app), "_scribe_tool_registry", None) or getattr(
        server.app, "_scribe_tool_registry", None
    )
    assert isinstance(registry, dict)
    return registry


async def _execute(
    name: str,
    arguments: Dict[str, Any],
    *,
    registry: Optional[Dict[str, Any]] = None,
    sentinel_allowed: Optional[set] = None,
) -> Any:
    router = RouterContextManager()
    return await execute_tool_call(
        name=name,
        arguments=arguments,
        kwargs={
            "context": {
                "mode": "sentinel",
                "repo_root": str(REPO_ROOT),
                "session_id": "scribehook2-test-session",
            }
        },
        registry=registry if registry is not None else _registered_tool_registry(),
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(
            project_root=REPO_ROOT,
            default_repo_root=str(REPO_ROOT),
            trusted_repo_roots=(str(REPO_ROOT),),
            public_release=False,
        ),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=_SENTINEL_ONLY_TOOLS,
        sentinel_allowed=(
            sentinel_allowed if sentinel_allowed is not None else _SENTINEL_ALLOWED_TOOLS
        ),
        log_scope_violation_cb=lambda *_a, **_k: None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_file_through_runtime_fires_post_read_hook() -> None:
    """A live ``read_file`` surfaces an arbitrary plugin's post_read payload."""
    recorder = _RecordingHookPlugin(marker="live-read")

    with _registered_hooks(recorder):
        result = await _execute(
            "read_file",
            {
                "agent": "scribehook2-test",
                "path": str(LIVE_READ_TARGET),
                "mode": "scan_only",
                "format": "structured",
            },
        )

    # Core read result is intact (dict, succeeded) — hooks are purely additive.
    assert isinstance(result, dict)
    assert result.get("ok") is True

    # post_read annotation landed in the dedicated generic list, not core fields.
    annotations = result.get("read_annotations")
    assert isinstance(annotations, list)
    assert {"scribehook2_marker": "live-read", "annotated_path": str(LIVE_READ_TARGET)} in annotations

    # pre_read fired before the read with the derived path + generic context.
    assert recorder.pre_calls, "pre_read should fire before the read"
    pre_path, pre_ctx = recorder.pre_calls[0]
    assert pre_path == str(LIVE_READ_TARGET)
    assert pre_ctx == {"agent": "scribehook2-test", "tool": "read_file"}
    # Generic context only — no council/RI fields leaked in.
    assert set(pre_ctx) == {"agent", "tool"}

    # post_read saw the same generic context.
    assert recorder.post_calls
    assert recorder.post_calls[0][1] == {"agent": "scribehook2-test", "tool": "read_file"}


@pytest.mark.asyncio
async def test_non_read_tool_does_not_fire_read_hook() -> None:
    """A tool whose name is not a read tool never invokes the read hooks."""
    recorder = _RecordingHookPlugin()

    async def _stub_non_read(agent: str) -> Dict[str, Any]:
        return {"ok": True, "tool": "not_a_read_tool"}

    stub_registry = {"not_a_read_tool": _stub_non_read}

    with _registered_hooks(recorder):
        result = await _execute(
            "not_a_read_tool",
            {"agent": "scribehook2-test"},
            registry=stub_registry,
            sentinel_allowed={"not_a_read_tool"},
        )

    assert result == {"ok": True, "tool": "not_a_read_tool"}
    assert "read_annotations" not in result
    assert recorder.pre_calls == []
    assert recorder.post_calls == []


@pytest.mark.asyncio
async def test_read_hook_failure_is_fail_open_live() -> None:
    """A raising read-hook never breaks the live read; result stays intact."""
    raiser = _RaisingHookPlugin()

    with _registered_hooks(raiser):
        result = await _execute(
            "read_file",
            {
                "agent": "scribehook2-test",
                "path": str(LIVE_READ_TARGET),
                "mode": "scan_only",
                "format": "structured",
            },
        )

    # No exception propagated and the original read result is unchanged.
    assert isinstance(result, dict)
    assert result.get("ok") is True
    # The raising plugin contributed no annotation.
    assert "read_annotations" not in result


@pytest.mark.asyncio
async def test_read_hook_keyed_on_name_and_isolated_via_stub() -> None:
    """Keying is purely on the tool name; a raising plugin is isolated while a
    co-registered recording plugin still annotates (fail-open isolation)."""
    recorder = _RecordingHookPlugin(marker="stub-read")
    raiser = _RaisingHookPlugin()

    async def _stub_read_file(agent: str, path: str) -> Dict[str, Any]:
        return {"ok": True, "core_field": "preserved", "path": path}

    stub_registry = {"read_file": _stub_read_file}

    # Register the raising plugin FIRST so its failure cannot suppress the
    # recorder's annotation (per-plugin isolation).
    with _registered_hooks(raiser, recorder):
        result = await _execute(
            "read_file",
            {"agent": "scribehook2-test", "path": "/virtual/path.py"},
            registry=stub_registry,
            sentinel_allowed={"read_file"},
        )

    # Core fields preserved; annotation merged additively.
    assert result["ok"] is True
    assert result["core_field"] == "preserved"
    annotations = result.get("read_annotations")
    assert annotations == [
        {"scribehook2_marker": "stub-read", "annotated_path": "/virtual/path.py"}
    ]
    # Both pre/post fired with the path derived from arguments.
    assert recorder.pre_calls[0][0] == "/virtual/path.py"
    assert recorder.post_calls[0][0] == "/virtual/path.py"
