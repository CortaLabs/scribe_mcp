from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path


def _load_probe_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "probe_repo_plugins.py"
    spec = importlib.util.spec_from_file_location("probe_repo_plugins", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_demo_repo_plugin(repo_root: Path) -> None:
    plugins_dir = repo_root / ".scribe" / "plugins"
    config_dir = repo_root / ".scribe" / "config"
    plugins_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    plugin_source = '''from __future__ import annotations

from typing import Any

from scribe_mcp.plugins.registry import HookPlugin


class DemoHookPlugin(HookPlugin):
    name = "demo_hook"
    version = "1.0.0"
    description = "Demo repo-local hook plugin"
    author = "Tests"

    def initialize(self, config: Any) -> None:
        self.repo_slug = config.repo_slug
'''
    plugin_file = plugins_dir / "demo_hook.py"
    plugin_file.write_text(plugin_source, encoding="utf-8")
    file_hash = hashlib.sha256(plugin_source.encode("utf-8")).hexdigest()
    (plugins_dir / "demo_hook.json").write_text(
        json.dumps(
            {
                "name": "demo_hook",
                "version": "1.0.0",
                "description": "Demo repo-local hook plugin",
                "author": "Tests",
                "file_hash": file_hash,
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "scribe.yaml").write_text(
        "\n".join(
            [
                "repo_slug: demo-repo",
                "plugins_dir: .scribe/plugins",
                "plugin_config:",
                "  enabled: true",
                "  allowlist:",
                "    - demo_hook",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_missing_dependency_plugin(repo_root: Path) -> None:
    plugins_dir = repo_root / ".scribe" / "plugins"
    config_dir = repo_root / ".scribe" / "config"
    plugins_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    plugin_source = "import definitely_missing_scribe_probe_dependency\n"
    plugin_file = plugins_dir / "missing_dep.py"
    plugin_file.write_text(plugin_source, encoding="utf-8")
    file_hash = hashlib.sha256(plugin_source.encode("utf-8")).hexdigest()
    (plugins_dir / "missing_dep.json").write_text(
        json.dumps(
            {
                "name": "missing_dep",
                "version": "1.0.0",
                "description": "Plugin with a missing dependency",
                "author": "Tests",
                "file_hash": file_hash,
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "scribe.yaml").write_text(
        "\n".join(
            [
                "repo_slug: demo-repo",
                "plugins_dir: .scribe/plugins",
                "plugin_config:",
                "  enabled: true",
                "  allowlist:",
                "    - missing_dep",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_repo_plugin_probe_distinguishes_blocked_and_trusted_load(
    tmp_path: Path, monkeypatch
) -> None:
    probe = _load_probe_module()
    _write_demo_repo_plugin(tmp_path)
    monkeypatch.delenv("SCRIBE_TRUST_REPO_PLUGINS", raising=False)
    monkeypatch.delenv("SCRIBE_ENABLE_EXTERNAL_PLUGINS", raising=False)

    import_root = tmp_path / "import-root"
    import_root.mkdir()

    result = probe.probe_repo_plugins(tmp_path, import_roots=[import_root])

    assert result["applied_import_roots"] == [str(import_root)]
    blocked = result["blocked_without_opt_in"]
    assert blocked["loaded_plugins"] == []
    assert blocked["diagnostics"]["blocked_reason"] == "repo_plugin_trust_not_enabled"
    assert (
        blocked["loader_diagnostics"]["blocked_reason"]
        == "repo_plugin_trust_not_enabled"
    )
    assert blocked["diagnostics"]["guidance"]["restart_required"] is True
    assert "SCRIBE_TRUST_REPO_PLUGINS" in blocked["diagnostics"]["guidance"]["available_action"]

    trusted = result["trusted_opt_in"]
    assert trusted["loaded_plugins"] == ["demo_hook"]
    assert trusted["loader_diagnostics"]["load_errors"] == []
    assert trusted["diagnostics"]["repo_plugin_trust_enabled"] is True
    assert trusted["diagnostics"]["eligible"] is True
    assert result["operator_workflow"]["restart_required"] is True

    assert os.environ.get("SCRIBE_TRUST_REPO_PLUGINS") is None
    assert os.environ.get("SCRIBE_ENABLE_EXTERNAL_PLUGINS") is None


def test_repo_plugin_probe_reports_trusted_import_errors(tmp_path: Path, monkeypatch) -> None:
    probe = _load_probe_module()
    _write_missing_dependency_plugin(tmp_path)
    monkeypatch.delenv("SCRIBE_TRUST_REPO_PLUGINS", raising=False)
    monkeypatch.delenv("SCRIBE_ENABLE_EXTERNAL_PLUGINS", raising=False)

    result = probe.probe_repo_plugins(tmp_path)

    trusted = result["trusted_opt_in"]
    assert trusted["loaded_plugins"] == []
    assert trusted["diagnostics"]["eligible"] is True
    assert trusted["loader_diagnostics"]["load_errors"] == [
        {
            "stem": "missing_dep",
            "reason": "plugin_module_load_failed",
            "error_type": "ModuleNotFoundError",
            "message": "No module named 'definitely_missing_scribe_probe_dependency'",
        }
    ]


def test_repo_plugin_probe_main_can_require_trusted_load(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    probe = _load_probe_module()
    _write_demo_repo_plugin(tmp_path)
    monkeypatch.delenv("SCRIBE_TRUST_REPO_PLUGINS", raising=False)
    monkeypatch.delenv("SCRIBE_ENABLE_EXTERNAL_PLUGINS", raising=False)

    import_root = tmp_path / "import-root"
    import_root.mkdir()

    exit_code = probe.main(
        [
            "--repo-root",
            str(tmp_path),
            "--import-root",
            str(import_root),
            "--require-loaded",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied_import_roots"] == [str(import_root)]
    assert payload["blocked_without_opt_in"]["loaded_count"] == 0
    assert payload["trusted_opt_in"]["loaded_count"] == 1
