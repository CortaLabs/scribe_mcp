from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import scribe_mcp.config.display_config as display_config_module
import scribe_mcp.config.repo_config as repo_config_module
import scribe_mcp.config.settings as settings_module


def _dotenv_loader(path: Path, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if override or key not in os.environ:
            os.environ[key] = value


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_settings_runtime_env_precedence_process_then_repo_then_global(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("SCRIBE_DB_URL=postgresql://repo\n", encoding="utf-8")

    cfg_home = tmp_path / "cfg-home"
    cfg_home.mkdir(parents=True, exist_ok=True)
    (cfg_home / "runtime.env").write_text("SCRIBE_DB_URL=postgresql://global\n", encoding="utf-8")

    monkeypatch.setenv("SCRIBE_ROOT", str(repo))
    monkeypatch.setenv("SCRIBE_CONFIG_DIR", str(cfg_home))
    monkeypatch.setattr(settings_module, "load_dotenv", _dotenv_loader)

    monkeypatch.delenv("SCRIBE_DB_URL", raising=False)
    loaded = settings_module.Settings.load()
    assert loaded.db_url == "postgresql://repo"

    monkeypatch.setenv("SCRIBE_DB_URL", "postgresql://process")
    loaded = settings_module.Settings.load()
    assert loaded.db_url == "postgresql://process"


def test_repo_config_global_structured_fallback_and_overlap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    cfg_home = tmp_path / "cfg-home"
    global_cfg = cfg_home / "scribe.yaml"
    _write_yaml(
        global_cfg,
        {
            "repo_slug": "global-slug",
            "default_emoji": "🌍",
            "dev_plans_dir": "global-docs",
            "storage_backend": "postgres",
            "reminder_config": {"mode": "global"},
            "display": {"verbosity": 2, "show_tips": True},
        },
    )

    repo_cfg = repo / ".scribe" / "config" / "scribe.yaml"
    _write_yaml(
        repo_cfg,
        {
            "repo_slug": "repo-slug",
            "dev_plans_dir": "repo-docs",
            "storage_backend": "sqlite",
            "db_path": ".scribe/data/repo.sqlite3",
            "reminder_config": {"mode": "repo"},
            "db_url": "postgresql://must-ignore",
            "postgres_pool_max_size": 99,
            "remote_auth_token": "must-ignore",
            "reminder_idle_minutes": 1,
        },
    )

    monkeypatch.setenv("SCRIBE_CONFIG_DIR", str(cfg_home))
    monkeypatch.setattr(
        repo_config_module,
        "settings",
        SimpleNamespace(dev_plans_base=Path(".scribe/docs/dev_plans")),
    )

    with caplog.at_level("WARNING"):
        config = repo_config_module.RepoDiscovery.load_config(repo, seed_if_missing=False)

    assert config.repo_slug == "repo-slug"
    assert config.storage_backend == "sqlite"
    assert config.db_path == repo / ".scribe" / "data" / "repo.sqlite3"
    assert config.dev_plans_dir == repo / "repo-docs"
    assert config.reminder_config == {"mode": "repo"}

    warning_text = "\n".join(record.message for record in caplog.records)
    assert "Ignoring env-owned repo config key 'db_url'" in warning_text
    assert "Ignoring env-owned repo config key 'postgres_pool_max_size'" in warning_text
    assert "Ignoring credential-like repo config key 'remote_auth_token'" in warning_text
    assert "Ignoring env-owned repo config key 'reminder_idle_minutes'" in warning_text


def test_display_config_repo_owned_with_global_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    cfg_home = tmp_path / "cfg-home"
    _write_yaml(
        cfg_home / "scribe.yaml",
        {
            "display": {
                "verbosity": 2,
                "show_tips": True,
                "box_drawing": True,
            }
        },
    )

    _write_yaml(
        repo / ".scribe" / "config" / "scribe.yaml",
        {
            "display": {
                "show_tips": False,
            }
        },
    )

    monkeypatch.setenv("SCRIBE_CONFIG_DIR", str(cfg_home))
    monkeypatch.setattr(
        repo_config_module,
        "get_current_repo_config",
        lambda refresh=False: (repo, SimpleNamespace()),
    )

    config = display_config_module.DisplayConfig()
    assert config.get_verbosity() == 2
    assert config.should_show_tips() is False
    assert config.should_use_box_drawing() is True
