from __future__ import annotations

from types import SimpleNamespace

import scribe_mcp.config.settings as settings_module
import scribe_mcp.storage as storage_module
from scribe_mcp.storage.postgres import PostgresStorage
from scribe_mcp.storage.sqlite import SQLiteStorage


def _fake_settings(**overrides):
    base = {
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


def test_create_storage_backend_falls_back_to_sqlite_without_dsn(monkeypatch) -> None:
    monkeypatch.setattr(
        settings_module,
        "settings",
        _fake_settings(
            storage_backend="postgres",
            db_url=None,
            sqlite_path="fallback.sqlite3",
        ),
    )

    backend = storage_module.create_storage_backend()

    assert isinstance(backend, SQLiteStorage)
