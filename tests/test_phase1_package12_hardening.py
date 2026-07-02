from __future__ import annotations

import hashlib
import json
import textwrap
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scribe_mcp import server as server_module
import scribe_mcp.tools.read_file as read_file_module
from scribe_mcp.config.repo_config import RepoConfig
from scribe_mcp.plugins.registry import (
    PluginRegistry,
    trusted_plugin_runtime_enabled,
    trusted_plugin_runtime_opt_in_vars,
)
from scribe_mcp.shared.execution_context import AgentIdentity, ExecutionContext
from scribe_mcp.tools.read_file import read_file
from scribe_mcp.tools.search import search


def _write_repo_config(repo_root: Path, content: str) -> None:
    config_dir = repo_root / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scribe.yaml").write_text(textwrap.dedent(content), encoding="utf-8")


def _install_execution_context(repo_root: Path, *, transport_policy: dict[str, object]):
    old_policy = getattr(server_module.app.state, "transport_policy", None)
    server_module.app.state.transport_policy = transport_policy
    context = ExecutionContext(
        repo_root=str(repo_root),
        mode="sentinel",
        session_id="phase12-session",
        execution_id="phase12-exec",
        agent_identity=AgentIdentity(
            agent_kind="test",
            model=None,
            instance_id="test-agent",
            sub_id=None,
            display_name=None,
        ),
        intent="phase12-hardening-tests",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        affected_dev_projects=[],
        sentinel_day="2026-04-03",
    )
    token = server_module.router_context_manager.set_current(context)
    return token, old_policy


def _reset_execution_context(token, old_policy: object) -> None:
    server_module.router_context_manager.reset(token)
    if old_policy is None:
        try:
            delattr(server_module.app.state, "transport_policy")
        except AttributeError:
            pass
    else:
        server_module.app.state.transport_policy = old_policy


def _transport_policy(
    *,
    transport: str = "stdio",
    bind_host: str = "127.0.0.1",
    network_exposed: bool = False,
    auth_required: bool = False,
    auth_configured: bool = False,
    allow_outside_repo_reads: bool,
) -> dict[str, object]:
    return {
        "transport": transport,
        "bind_host": bind_host,
        "port": 8200,
        "network_exposed": network_exposed,
        "auth_required": auth_required,
        "auth_configured": auth_configured,
        "allow_outside_repo_reads": allow_outside_repo_reads,
    }


def _write_plugin(repo_root: Path, marker_path: Path) -> tuple[Path, Path]:
    plugins_dir = repo_root / ".scribe" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugins_dir / "sample_plugin.py"
    plugin_file.write_text(
        textwrap.dedent(
            f"""\
            from pathlib import Path

            from scribe_mcp.plugins.registry import ScribePlugin

            Path(r"{marker_path}").write_text("imported", encoding="utf-8")


            class SamplePlugin(ScribePlugin):
                name = "sample_plugin"

                def initialize(self, config):
                    self.description = "sample plugin"
            """
        ),
        encoding="utf-8",
    )

    manifest_file = plugin_file.with_suffix(".json")
    manifest_file.write_text(
        json.dumps(
            {
                "name": "sample_plugin",
                "version": "1.0.0",
                "description": "sample plugin",
                "author": "tests",
                "file_hash": hashlib.sha256(plugin_file.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return plugin_file, manifest_file


def _override_read_file_settings(monkeypatch: pytest.MonkeyPatch, **changes) -> None:
    monkeypatch.setattr(
        read_file_module,
        "settings",
        replace(read_file_module.settings, **changes),
    )


@pytest.mark.asyncio
async def test_read_file_allows_cross_repo_reads_for_loopback_authenticated_sse_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    sibling_repo_file = tmp_path / "other_repo" / "notes.txt"
    sibling_repo_file.parent.mkdir()
    sibling_repo_file.write_text("loopback authenticated cross repo", encoding="utf-8")

    _override_read_file_settings(monkeypatch, force_disable_outside_repo_reads=False)
    token, old_policy = _install_execution_context(
        repo_root,
        transport_policy=_transport_policy(
            transport="sse",
            bind_host="127.0.0.1",
            network_exposed=False,
            auth_required=True,
            auth_configured=True,
            allow_outside_repo_reads=False,
        ),
    )
    try:
        result = await read_file(
            agent="test-agent",
            path=str(sibling_repo_file),
            mode="full",
            allow_outside_repo=True,
            format="structured",
        )

        assert result["ok"] is True
        assert "loopback authenticated cross repo" in result["chunk"]["content"]
    finally:
        _reset_execution_context(token, old_policy)


@pytest.mark.asyncio
async def test_read_file_blocks_cross_repo_reads_for_network_posture_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    sibling_repo_file = tmp_path / "other_repo" / "notes.txt"
    sibling_repo_file.parent.mkdir()
    sibling_repo_file.write_text("blocked cross repo", encoding="utf-8")

    _override_read_file_settings(monkeypatch, force_disable_outside_repo_reads=False)
    token, old_policy = _install_execution_context(
        repo_root,
        transport_policy=_transport_policy(
            transport="sse",
            bind_host="0.0.0.0",
            network_exposed=True,
            auth_required=True,
            auth_configured=True,
            allow_outside_repo_reads=False,
        ),
    )
    try:
        result = await read_file(
            agent="test-agent",
            path=str(sibling_repo_file),
            mode="full",
            allow_outside_repo=True,
            format="structured",
        )

        assert result["ok"] is False
        assert result["reason"] == "outside_repo_reads_disabled_by_network_posture"
    finally:
        _reset_execution_context(token, old_policy)


@pytest.mark.asyncio
async def test_read_file_allows_cross_repo_reads_when_network_posture_is_explicitly_force_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    sibling_repo_file = tmp_path / "other_repo" / "notes.txt"
    sibling_repo_file.parent.mkdir()
    sibling_repo_file.write_text("force enabled cross repo", encoding="utf-8")

    _override_read_file_settings(monkeypatch, force_disable_outside_repo_reads=False)
    token, old_policy = _install_execution_context(
        repo_root,
        transport_policy=_transport_policy(
            transport="sse",
            bind_host="0.0.0.0",
            network_exposed=True,
            auth_required=True,
            auth_configured=True,
            allow_outside_repo_reads=True,
        ),
    )
    try:
        result = await read_file(
            agent="test-agent",
            path=str(sibling_repo_file),
            mode="full",
            allow_outside_repo=True,
            format="structured",
        )

        assert result["ok"] is True
        assert "force enabled cross repo" in result["chunk"]["content"]
    finally:
        _reset_execution_context(token, old_policy)


@pytest.mark.asyncio
async def test_read_file_global_force_disable_beats_network_force_enable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    sibling_repo_file = tmp_path / "other_repo" / "notes.txt"
    sibling_repo_file.parent.mkdir()
    sibling_repo_file.write_text("force disabled cross repo", encoding="utf-8")

    _override_read_file_settings(monkeypatch, force_disable_outside_repo_reads=True)
    token, old_policy = _install_execution_context(
        repo_root,
        transport_policy=_transport_policy(
            transport="sse",
            bind_host="0.0.0.0",
            network_exposed=True,
            auth_required=True,
            auth_configured=True,
            allow_outside_repo_reads=True,
        ),
    )
    try:
        result = await read_file(
            agent="test-agent",
            path=str(sibling_repo_file),
            mode="full",
            allow_outside_repo=True,
            format="structured",
        )

        assert result["ok"] is False
        assert result["reason"] == "outside_repo_reads_disabled_by_global_policy"
    finally:
        _reset_execution_context(token, old_policy)


@pytest.mark.asyncio
async def test_search_rejects_unsafe_nested_regex(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "sample.txt").write_text("aaaaaaaaaaaaaaaaaa", encoding="utf-8")

    token, old_policy = _install_execution_context(
        repo_root,
        transport_policy=_transport_policy(network_exposed=False, allow_outside_repo_reads=False),
    )
    try:
        result = await search(
            agent="test-agent",
            pattern="(a+)+$",
            regex=True,
            format="structured",
        )

        assert result["ok"] is False
        assert result["error"] == "unsafe regex rejected"
        assert "Nested quantifiers" in result["reason"]
    finally:
        _reset_execution_context(token, old_policy)


def test_plugin_registry_requires_trusted_runtime_opt_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    marker_path = tmp_path / "plugin-imported.txt"
    _write_repo_config(
        repo_root,
        """
        repo_slug: repo
        plugins_dir: .scribe/plugins
        plugin_config:
          enabled: true
        """,
    )
    _write_plugin(repo_root, marker_path)

    monkeypatch.delenv("SCRIBE_TRUST_REPO_PLUGINS", raising=False)
    monkeypatch.delenv("SCRIBE_ENABLE_EXTERNAL_PLUGINS", raising=False)

    config = RepoConfig.from_directory(repo_root)
    registry = PluginRegistry(repo_root=repo_root)
    registry.load_plugins(config)

    assert registry.plugins == {}
    assert marker_path.exists() is False
    assert trusted_plugin_runtime_enabled() is False
    assert "SCRIBE_TRUST_REPO_PLUGINS" in trusted_plugin_runtime_opt_in_vars()


def test_plugin_registry_loads_manifest_pinned_plugin_with_trusted_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    marker_path = tmp_path / "plugin-imported.txt"
    _write_repo_config(
        repo_root,
        """
        repo_slug: repo
        plugins_dir: .scribe/plugins
        plugin_config:
          enabled: true
        """,
    )
    _write_plugin(repo_root, marker_path)

    monkeypatch.setenv("SCRIBE_TRUST_REPO_PLUGINS", "1")

    config = RepoConfig.from_directory(repo_root)
    registry = PluginRegistry(repo_root=repo_root)
    registry.load_plugins(config)

    assert "sample_plugin" in registry.plugins
    assert marker_path.read_text(encoding="utf-8") == "imported"
