from __future__ import annotations

from types import SimpleNamespace

import scribe_mcp.config.settings as settings_module
import scribe_mcp.server as server_module
import scribe_mcp.storage as storage_module
from scribe_mcp.config.mode_detection import OperatingMode
from scribe_mcp.storage.remote import RemoteStorageBackend
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
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_settings_load_prefers_canonical_remote_auth_token_and_keeps_alias_fallbacks(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_REMOTE_AUTH_TOKEN", "canonical-token")
    monkeypatch.setenv("SCRIBE_TRANSPORT_AUTH_TOKEN", "transport-token")
    monkeypatch.setenv("SCRIBE_AUTH_TOKEN", "legacy-token")

    loaded = settings_module.Settings.load()
    assert loaded.remote_auth_token == "canonical-token"

    monkeypatch.delenv("SCRIBE_REMOTE_AUTH_TOKEN", raising=False)
    loaded = settings_module.Settings.load()
    assert loaded.remote_auth_token == "transport-token"

    monkeypatch.delenv("SCRIBE_TRANSPORT_AUTH_TOKEN", raising=False)
    loaded = settings_module.Settings.load()
    assert loaded.remote_auth_token == "legacy-token"


def test_create_storage_backend_uses_remote_backend_when_remote_url_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        settings_module,
        "settings",
        _fake_settings(
            mode="auto",
            storage_backend="postgres",
            db_url="postgresql://scribe_app:pass@127.0.0.1:5432/scribe",
            remote_server_url="https://remote.example",
            remote_auth_token="client-token",
        ),
    )

    backend = storage_module.create_storage_backend()

    assert isinstance(backend, RemoteStorageBackend)
    assert backend._server_url == "https://remote.example"  # noqa: SLF001 - focused contract assertion
    assert backend._auth_token == "client-token"  # noqa: SLF001 - focused contract assertion


def test_rebind_storage_backend_for_mode_updates_server_singletons(monkeypatch) -> None:
    sqlite_backend = SQLiteStorage("runtime.sqlite3")

    monkeypatch.setattr(server_module, "create_storage_backend", lambda mode=None: sqlite_backend)
    server_module.state_manager = SimpleNamespace(_storage_backend="before")
    server_module.router_context_manager = SimpleNamespace(_storage_backend="before")
    server_module.storage_backend = "before"

    rebound = server_module._rebind_storage_backend_for_mode(OperatingMode.STANDALONE)

    assert rebound is sqlite_backend
    assert server_module.storage_backend is sqlite_backend
    assert server_module.state_manager._storage_backend is sqlite_backend
    assert server_module.router_context_manager._storage_backend is sqlite_backend
