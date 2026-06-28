"""Tests for the generic bridge pre_read/post_read hook event (SCRIBEHOOK.1).

Proves the async BridgePlugin read-event and BridgeHookManager dispatch are
GENERIC and content-agnostic: an arbitrary bridge can annotate a read result,
non-None returns are collected into ``result["read_annotations"]``, INACTIVE
bridges are skipped, and failures/timeouts are isolated (fire-and-forget).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest

from scribe_mcp.bridges.manifest import (
    BridgeManifest,
    BridgeState,
    HookConfig,
)
from scribe_mcp.bridges.hooks import BridgeHookManager
from scribe_mcp.bridges.plugin import BridgePlugin


class _ReadBridgePlugin(BridgePlugin):
    """A throwaway bridge that annotates reads generically (non-RI)."""

    def __init__(
        self,
        manifest: BridgeManifest,
        *,
        payload: Optional[Dict[str, Any]] = None,
        raise_post: bool = False,
        sleep_post: float = 0.0,
    ) -> None:
        super().__init__(manifest)
        self._payload = payload
        self._raise_post = raise_post
        self._sleep_post = sleep_post
        self.pre_read_called = False
        self.post_read_called = False

    async def on_activate(self) -> None:  # pragma: no cover - trivial
        pass

    async def on_deactivate(self) -> None:  # pragma: no cover - trivial
        pass

    async def health_check(self) -> dict:  # pragma: no cover - trivial
        return {"healthy": True, "message": "ok", "latency_ms": 1}

    async def pre_read(self, path: str, context: Dict[str, Any]) -> None:
        self.pre_read_called = True

    async def post_read(
        self, path: str, result: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        self.post_read_called = True
        if self._sleep_post:
            await asyncio.sleep(self._sleep_post)
        if self._raise_post:
            raise RuntimeError("boom-post")
        return self._payload


def _manifest(bridge_id: str, *, timeout_ms: int = 1000) -> BridgeManifest:
    return BridgeManifest(
        bridge_id=bridge_id,
        name="Read Bridge",
        version="1.0.0",
        description="Test read bridge",
        author="Test",
        hooks={
            "pre_read": HookConfig(hook_name="pre_read", timeout_ms=timeout_ms, critical=False),
            "post_read": HookConfig(hook_name="post_read", timeout_ms=timeout_ms, critical=False),
        },
    )


@pytest.mark.asyncio
async def test_bridge_execute_post_read_collects_generic_annotations() -> None:
    """An active bridge's non-None payload is collected generically."""
    bridge = _ReadBridgePlugin(_manifest("read_bridge"), payload={"x": 1})
    bridge.state = BridgeState.ACTIVE

    manager = BridgeHookManager()
    manager.register_bridge(bridge)

    result: Dict[str, Any] = {"content": "data"}
    returned = await manager.execute_post_read("some/path.py", result, {"agent": "t"})

    assert returned is result
    assert result["read_annotations"] == [{"x": 1}]
    assert bridge.post_read_called is True


@pytest.mark.asyncio
async def test_bridge_execute_pre_read_active() -> None:
    """Active bridge pre_read fires."""
    bridge = _ReadBridgePlugin(_manifest("read_bridge"))
    bridge.state = BridgeState.ACTIVE

    manager = BridgeHookManager()
    manager.register_bridge(bridge)

    await manager.execute_pre_read("some/path.py", {})
    assert bridge.pre_read_called is True


@pytest.mark.asyncio
async def test_bridge_execute_post_read_active_only_and_timeout() -> None:
    """INACTIVE bridge is skipped; a timeout is isolated (fire-and-forget)."""
    # INACTIVE bridge must be skipped entirely.
    inactive = _ReadBridgePlugin(_manifest("inactive_bridge"), payload={"y": 2})
    inactive.state = BridgeState.INACTIVE

    # Active bridge whose post_read exceeds the configured timeout.
    slow = _ReadBridgePlugin(
        _manifest("slow_bridge", timeout_ms=10), payload={"z": 3}, sleep_post=1.0
    )
    slow.state = BridgeState.ACTIVE

    manager = BridgeHookManager()
    manager.register_bridge(inactive)
    manager.register_bridge(slow)

    result: Dict[str, Any] = {"content": "data"}
    # Must not raise despite the timeout.
    returned = await manager.execute_post_read("some/path.py", result, {})

    assert returned is result
    # Inactive bridge contributed nothing; timed-out bridge contributed nothing.
    assert "read_annotations" not in result
    assert inactive.post_read_called is False


@pytest.mark.asyncio
async def test_bridge_execute_post_read_fail_open_on_raise() -> None:
    """A raising post_read does not propagate; healthy bridges still collected."""
    raiser = _ReadBridgePlugin(_manifest("raiser"), raise_post=True)
    raiser.state = BridgeState.ACTIVE
    healthy = _ReadBridgePlugin(_manifest("healthy"), payload={"ok": True})
    healthy.state = BridgeState.ACTIVE

    manager = BridgeHookManager()
    manager.register_bridge(raiser)
    manager.register_bridge(healthy)

    result: Dict[str, Any] = {"content": "data"}
    returned = await manager.execute_post_read("some/path.py", result, {})

    assert returned is result
    assert result["read_annotations"] == [{"ok": True}]
