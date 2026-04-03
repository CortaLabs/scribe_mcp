"""Runtime plugin registry detection tests."""

from __future__ import annotations

import textwrap

from scribe_mcp.config.repo_config import RepoConfig
from scribe_mcp.plugins.registry import get_plugin_registry, initialize_plugins


def test_plugin_registry_does_not_load_removed_builtin_vector_plugin(tmp_path) -> None:
    """Ensure legacy vector settings do not restore a built-in core plugin."""
    config_dir = tmp_path / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_yaml = textwrap.dedent(
        """\
        repo_slug: test-repo
        plugins_dir: .scribe/plugins
        plugin_config:
          enabled: true
        vector_index_docs: true
        vector_index_logs: true
        """
    )
    (config_dir / "scribe.yaml").write_text(config_yaml, encoding="utf-8")

    repo_config = RepoConfig.from_directory(tmp_path)
    initialize_plugins(repo_config)

    registry = get_plugin_registry(tmp_path)
    assert "vector_indexer" not in registry.plugins
    assert registry.plugins == {}

    registry.cleanup()
