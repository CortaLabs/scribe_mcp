from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


if "httpx" not in sys.modules:
    class _StubAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=503, json=lambda: {})

    sys.modules["httpx"] = types.SimpleNamespace(
        AsyncClient=_StubAsyncClient,
        ConnectError=Exception,
        TimeoutException=Exception,
    )

import scribe_mcp.config.mode_detection as mode_detection_module
import scribe_mcp.config.settings as settings_module
import scribe_mcp.storage as storage_module
from scribe_mcp.config.mode_detection import OperatingMode
from scribe_mcp.storage.sqlite import SQLiteStorage


def _fake_settings(**overrides):
    base = {
        "mode": "auto",
        "storage_backend": "postgres",
        "db_url": None,
        "sqlite_path": Path("default.sqlite3"),
        "postgres_schema": "scribe",
        "postgres_pool_min_size": 2,
        "postgres_pool_max_size": 20,
        "postgres_command_timeout_seconds": 30.0,
        "postgres_connect_timeout_seconds": 10.0,
        "postgres_max_inactive_connection_lifetime_seconds": 300.0,
        "postgres_connect_retries": 3,
        "postgres_connect_retry_backoff_seconds": 1.0,
        "remote_server_url": None,
        "remote_auth_token": None,
        "remote_connect_timeout": 3.0,
        "remote_fallback": False,
        "release_profile": "internal",
        "public_release": False,
        "project_root": Path("."),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_resolve_configured_mode_honors_repo_storage_backend_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SCRIBE_STORAGE_BACKEND", raising=False)
    monkeypatch.setattr(
        mode_detection_module,
        "resolve_repo_runtime_overrides",
        lambda _repo_root: {"storage_backend": "sqlite", "db_path": None, "config_path": None},
    )

    settings = _fake_settings(project_root=tmp_path, storage_backend="postgres", db_url=None)

    resolved = mode_detection_module.resolve_configured_mode(settings)
    assert resolved == OperatingMode.STANDALONE


def test_resolve_configured_mode_prefers_env_backend_over_repo_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SCRIBE_STORAGE_BACKEND", "postgres")
    monkeypatch.setattr(
        mode_detection_module,
        "resolve_repo_runtime_overrides",
        lambda _repo_root: {"storage_backend": "sqlite", "db_path": None, "config_path": None},
    )

    settings = _fake_settings(
        project_root=tmp_path,
        storage_backend="postgres",
        db_url="postgresql://scribe_app:pass@127.0.0.1:5432/scribe",
    )

    resolved = mode_detection_module.resolve_configured_mode(settings)
    assert resolved == OperatingMode.SERVER


def test_create_storage_backend_uses_repo_sqlite_db_path_when_allowed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SCRIBE_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("SCRIBE_DB_PATH", raising=False)
    monkeypatch.delenv("SCRIBE_SQLITE_PATH", raising=False)

    repo_sqlite_path = tmp_path / ".scribe" / "data" / "repo.sqlite3"

    monkeypatch.setattr(
        storage_module,
        "resolve_repo_runtime_overrides",
        lambda _repo_root: {
            "storage_backend": "sqlite",
            "db_path": repo_sqlite_path,
            "config_path": tmp_path / ".scribe" / "config" / "scribe.yaml",
        },
    )
    monkeypatch.setattr(
        mode_detection_module,
        "resolve_repo_runtime_overrides",
        lambda _repo_root: {
            "storage_backend": "sqlite",
            "db_path": repo_sqlite_path,
            "config_path": tmp_path / ".scribe" / "config" / "scribe.yaml",
        },
    )
    monkeypatch.setattr(settings_module, "settings", _fake_settings(project_root=tmp_path, sqlite_path=tmp_path / "default.sqlite3"))

    backend = storage_module.create_storage_backend()

    assert isinstance(backend, SQLiteStorage)
    assert backend._path == repo_sqlite_path  # noqa: SLF001 - focused runtime contract assertion


def test_repo_db_path_is_inactive_with_warning_under_postgres(monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.delenv("SCRIBE_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("SCRIBE_DB_PATH", raising=False)
    monkeypatch.delenv("SCRIBE_SQLITE_PATH", raising=False)

    repo_sqlite_path = tmp_path / ".scribe" / "data" / "repo.sqlite3"
    monkeypatch.setattr(
        storage_module,
        "resolve_repo_runtime_overrides",
        lambda _repo_root: {
            "storage_backend": "postgres",
            "db_path": repo_sqlite_path,
            "config_path": tmp_path / ".scribe" / "config" / "scribe.yaml",
        },
    )
    monkeypatch.setattr(
        settings_module,
        "settings",
        _fake_settings(
            project_root=tmp_path,
            storage_backend="postgres",
            db_url="postgresql://scribe_app:pass@127.0.0.1:5432/scribe",
        ),
    )
    class _FakePostgresStorage:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    sys.modules["scribe_mcp.storage.postgres"] = types.SimpleNamespace(PostgresStorage=_FakePostgresStorage)

    with caplog.at_level("WARNING"):
        backend = storage_module.create_storage_backend(mode=OperatingMode.SERVER)

    assert isinstance(backend, _FakePostgresStorage)
    assert "repo config db_path is ignored" in caplog.text.lower()
