from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.config import repo_config as repo_config_module
from scribe_mcp.config.downstream_assets import ensure_downstream_seed_assets
from scribe_mcp.config.paths import (
    config_home_dir,
    downstream_seed_manifest_path,
    packaged_config_asset,
    packaged_template_asset,
)


def test_packaged_path_helpers_and_config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom_config_home = tmp_path / "cfg-home"
    monkeypatch.setenv("SCRIBE_CONFIG_DIR", str(custom_config_home))

    assert config_home_dir() == custom_config_home.resolve()
    assert downstream_seed_manifest_path() == packaged_config_asset("downstream_seed_manifest.yaml")
    assert packaged_template_asset("documents/ARCHITECTURE_GUIDE_TEMPLATE.md").exists()


def test_downstream_seed_blank_repo_creates_assets_and_registry(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = ensure_downstream_seed_assets(repo_root)

    assert result.seeded >= 3
    assert (repo_root / ".scribe" / "config" / "scribe.yaml").exists()
    assert (repo_root / ".scribe" / ".env.example").exists()
    assert (repo_root / ".scribe" / "templates" / "documents" / "ARCHITECTURE_GUIDE_TEMPLATE.md").exists()

    registry_path = repo_root / ".scribe" / "config" / "seed_registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert ".scribe/config/scribe.yaml" in payload["assets"]


def test_downstream_adopt_without_overwrite(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config_path = repo_root / ".scribe" / "config" / "scribe.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("repo_slug: custom\n", encoding="utf-8")

    result = ensure_downstream_seed_assets(repo_root, asset_ids=("repo_config",))

    assert result.seeded == 0
    assert config_path.read_text(encoding="utf-8") == "repo_slug: custom\n"

    registry_path = repo_root / ".scribe" / "config" / "seed_registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = payload["assets"][".scribe/config/scribe.yaml"]
    assert entry["status"] == "customized"


def test_downstream_safe_refresh_only_when_unmodified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    initial = ensure_downstream_seed_assets(repo_root, asset_ids=("repo_config",))
    assert initial.seeded == 1

    from scribe_mcp.config import downstream_assets as module
    original_source_bytes = module._source_bytes

    def replacement_source(asset):
        if asset.asset_id == "repo_config":
            return b"repo_slug: refreshed\n"
        return original_source_bytes(asset)

    monkeypatch.setattr(module, "_source_bytes", replacement_source)
    refreshed = ensure_downstream_seed_assets(repo_root, refresh=True, asset_ids=("repo_config",))
    assert refreshed.refreshed == 1
    assert (repo_root / ".scribe" / "config" / "scribe.yaml").read_text(encoding="utf-8") == "repo_slug: refreshed\n"


def test_downstream_safe_refresh_skips_customized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    ensure_downstream_seed_assets(repo_root, asset_ids=("repo_config",))
    config_path = repo_root / ".scribe" / "config" / "scribe.yaml"
    config_path.write_text("repo_slug: my-custom-version\n", encoding="utf-8")

    from scribe_mcp.config import downstream_assets as module
    original_source_bytes = module._source_bytes

    def replacement_source(asset):
        if asset.asset_id == "repo_config":
            return b"repo_slug: refreshed\n"
        return original_source_bytes(asset)

    monkeypatch.setattr(module, "_source_bytes", replacement_source)
    refresh = ensure_downstream_seed_assets(repo_root, refresh=True, asset_ids=("repo_config",))

    assert refresh.refreshed == 0
    assert refresh.customized == 1
    assert config_path.read_text(encoding="utf-8") == "repo_slug: my-custom-version\n"


def test_downstream_safe_refresh_stays_skipped_after_customization_classification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    ensure_downstream_seed_assets(repo_root, asset_ids=("repo_config",))
    config_path = repo_root / ".scribe" / "config" / "scribe.yaml"
    config_path.write_text("repo_slug: my-custom-version\n", encoding="utf-8")

    from scribe_mcp.config import downstream_assets as module

    original_source_bytes = module._source_bytes

    def replacement_source_v1(asset):
        if asset.asset_id == "repo_config":
            return b"repo_slug: refreshed-v1\n"
        return original_source_bytes(asset)

    monkeypatch.setattr(module, "_source_bytes", replacement_source_v1)
    first_refresh = ensure_downstream_seed_assets(repo_root, refresh=True, asset_ids=("repo_config",))

    assert first_refresh.refreshed == 0
    assert first_refresh.customized == 1
    assert config_path.read_text(encoding="utf-8") == "repo_slug: my-custom-version\n"

    def replacement_source_v2(asset):
        if asset.asset_id == "repo_config":
            return b"repo_slug: refreshed-v2\n"
        return original_source_bytes(asset)

    monkeypatch.setattr(module, "_source_bytes", replacement_source_v2)
    second_refresh = ensure_downstream_seed_assets(repo_root, refresh=True, asset_ids=("repo_config",))

    assert second_refresh.refreshed == 0
    assert second_refresh.customized == 1
    assert config_path.read_text(encoding="utf-8") == "repo_slug: my-custom-version\n"


def test_repo_config_seed_no_longer_depends_on_settings_project_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    fake_settings = SimpleNamespace(
        dev_plans_base=Path(".scribe/docs/dev_plans"),
        project_root=Path("/tmp/path-that-does-not-provide-config-template"),
    )
    monkeypatch.setattr(repo_config_module, "settings", fake_settings)

    config = repo_config_module.RepoDiscovery.load_config(repo_root, seed_if_missing=True)

    assert config.repo_root == repo_root
    assert (repo_root / ".scribe" / "config" / "scribe.yaml").exists()


def test_env_example_contains_guidance_and_classification_sections(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    ensure_downstream_seed_assets(repo_root, asset_ids=("env_example",))
    env_example = (repo_root / ".scribe" / ".env.example").read_text(encoding="utf-8")

    assert "Repo-specific runtime overrides belong in repo root .env." in env_example
    assert "Shared defaults belong in user/global runtime.env." in env_example
    assert "Runtime never auto-loads .scribe/.env.example." in env_example

    assert "# [Canonical Runtime Settings]" in env_example
    assert "# [Compatibility Aliases]" in env_example
    assert "# [Advanced Public Runtime Settings]" in env_example
    assert "# [Advanced Non-Release Settings]" in env_example
    assert "# [Bootstrap-Only Settings]" in env_example
