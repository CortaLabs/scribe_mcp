from __future__ import annotations

from types import SimpleNamespace

import pytest

import scribe_mcp.config.settings as settings_module
import scribe_mcp.storage as storage_module
from scribe_mcp.config.mode_detection import OperatingMode
from scribe_mcp.storage.postgres import PostgresStorage
from scribe_mcp.storage.sqlite import SQLiteStorage


def _fake_settings(**overrides):
    base = {
        "mode": "auto",
        "storage_backend": "sqlite",
        "db_url": None,
        "sqlite_path": "test.sqlite3",
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
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_create_storage_backend_uses_postgres_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        settings_module,
        "settings",
        _fake_settings(
            storage_backend="postgres",
            db_url="postgresql://scribe_app:pass@127.0.0.1:5432/scribe",
            postgres_schema="scribe",
        ),
    )

    backend = storage_module.create_storage_backend()

    assert isinstance(backend, PostgresStorage)
    assert backend._dsn.endswith("/scribe")  # noqa: SLF001 - integration assertion


def test_create_storage_backend_fail_closed_without_dsn_for_server_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        settings_module,
        "settings",
        _fake_settings(
            storage_backend="postgres",
            db_url=None,
            sqlite_path="fallback.sqlite3",
        ),
    )

    with pytest.raises(RuntimeError, match="SCRIBE_DB_URL is missing"):
        storage_module.create_storage_backend(mode=OperatingMode.SERVER)


def test_create_storage_backend_allows_explicit_standalone_sqlite(monkeypatch) -> None:
    monkeypatch.setattr(
        settings_module,
        "settings",
        _fake_settings(
            storage_backend="sqlite",
            db_url=None,
            sqlite_path="standalone.sqlite3",
        ),
    )

    backend = storage_module.create_storage_backend(mode=OperatingMode.STANDALONE)

    assert isinstance(backend, SQLiteStorage)


def test_create_storage_backend_rejects_server_mode_with_sqlite_even_with_db_url(monkeypatch) -> None:
    monkeypatch.setattr(
        settings_module,
        "settings",
        _fake_settings(
            mode="server",
            storage_backend="sqlite",
            db_url="postgresql://scribe_app:pass@127.0.0.1:5432/scribe",
            sqlite_path="invalid.sqlite3",
        ),
    )

    with pytest.raises(RuntimeError, match="requires SCRIBE_STORAGE_BACKEND=postgres"):
        storage_module.create_storage_backend(mode=OperatingMode.SERVER)
