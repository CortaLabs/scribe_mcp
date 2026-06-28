"""Tests for the generic pre_read/post_read hook vocabulary (SCRIBEHOOK.1).

These prove the read-event is GENERIC and content-agnostic: an arbitrary
(non-RI) HookPlugin can post-process a read result, non-None returns are
collected into ``result["read_annotations"]``, and a raising plugin never
breaks the read result (fail-open).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from scribe_mcp.bridges.manifest import HookConfig
from scribe_mcp.plugins.registry import HookPlugin, PluginRegistry


class _ArbitraryReadPlugin(HookPlugin):
    """A throwaway, non-RI hook plugin that annotates reads generically."""

    name = "arbitrary_read_plugin"

    def __init__(self, payload: Optional[Dict[str, Any]]) -> None:
        self._payload = payload

    def initialize(self, config) -> None:  # pragma: no cover - trivial
        pass

    def post_read(
        self, path: str, result: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        return self._payload


class _RaisingReadPlugin(HookPlugin):
    """A hook plugin whose post_read raises (to prove fail-open)."""

    name = "raising_read_plugin"

    def initialize(self, config) -> None:  # pragma: no cover - trivial
        pass

    def pre_read(self, path: str, context: Dict[str, Any]) -> None:
        raise RuntimeError("boom-pre")

    def post_read(
        self, path: str, result: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        raise RuntimeError("boom-post")


def test_hookplugin_post_read_default_returns_none() -> None:
    """The base HookPlugin.post_read default is a safe None (no annotation)."""

    class _BarePlugin(HookPlugin):
        name = "bare"

        def initialize(self, config) -> None:  # pragma: no cover - trivial
            pass

    plugin = _BarePlugin()
    assert plugin.post_read("some/path.py", {"content": "x"}, {}) is None
    # pre_read default is a no-op and returns nothing.
    assert plugin.pre_read("some/path.py", {}) is None


def test_execute_hook_post_read_collects_generic_annotations() -> None:
    """An ARBITRARY plugin's non-None payload is collected generically."""
    registry = PluginRegistry()
    registry.hook_plugins.append(_ArbitraryReadPlugin({"x": 1}))

    result: Dict[str, Any] = {"content": "data"}
    returned = registry.execute_hook_post_read("some/path.py", result, {"agent": "tester"})

    # Mutates and returns the same result dict.
    assert returned is result
    assert result["read_annotations"] == [{"x": 1}]


def test_execute_hook_post_read_none_payload_is_not_collected() -> None:
    """A plugin returning None contributes no annotation entry."""
    registry = PluginRegistry()
    registry.hook_plugins.append(_ArbitraryReadPlugin(None))

    result: Dict[str, Any] = {"content": "data"}
    returned = registry.execute_hook_post_read("some/path.py", result, {})

    assert returned is result
    assert "read_annotations" not in result


def test_execute_hook_post_read_fail_open() -> None:
    """A raising post_read does not propagate; the result is still returned."""
    registry = PluginRegistry()
    registry.hook_plugins.append(_RaisingReadPlugin())
    registry.hook_plugins.append(_ArbitraryReadPlugin({"ok": True}))

    result: Dict[str, Any] = {"content": "data"}
    # Must not raise even though the first plugin raises.
    returned = registry.execute_hook_post_read("some/path.py", result, {})

    assert returned is result
    # The healthy plugin still contributes its annotation.
    assert result["read_annotations"] == [{"ok": True}]


def test_execute_hook_pre_read_fail_open() -> None:
    """A raising pre_read does not propagate."""
    registry = PluginRegistry()
    registry.hook_plugins.append(_RaisingReadPlugin())

    # Must not raise.
    registry.execute_hook_pre_read("some/path.py", {"agent": "tester"})


def test_manifest_accepts_pre_post_read_hook_names() -> None:
    """HookConfig.from_dict accepts pre_read/post_read with no enum gate."""
    pre = HookConfig.from_dict({}, hook_name="pre_read")
    post = HookConfig.from_dict({"timeout_ms": 1234}, hook_name="post_read")

    assert pre.hook_name == "pre_read"
    assert post.hook_name == "post_read"
    assert post.timeout_ms == 1234
