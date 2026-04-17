from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import scribe_mcp.config.settings as settings_module
import scribe_mcp.server as server_module
import scribe_mcp.state.manager as manager_module
import scribe_mcp.storage as storage_module
import scribe_mcp.tools.doctor as doctor_module
from scribe_mcp.config.mode_detection import OperatingMode
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage


def _fake_settings(**overrides) -> SimpleNamespace:
    base = {
        "mode": "auto",
        "storage_backend": "postgres",
        "db_url": None,
        "sqlite_path": Path("runtime.sqlite3"),
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
        "default_state_path": Path(".scribe/state.json"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_storage_factory_fail_closed_for_default_server_class_resolution(monkeypatch) -> None:
    fake = _fake_settings(storage_backend="postgres", db_url=None, mode="auto")
    monkeypatch.setattr(settings_module, "settings", fake)

    with pytest.raises(RuntimeError, match="requires Postgres configuration"):
        storage_module.create_storage_backend()


def test_server_rebind_fail_closed_for_server_mode_without_postgres(monkeypatch) -> None:
    fake = _fake_settings(storage_backend="postgres", db_url=None, mode="server")
    monkeypatch.setattr(settings_module, "settings", fake)
    monkeypatch.setattr(server_module, "settings", fake)

    with pytest.raises(RuntimeError, match="SCRIBE_DB_URL"):
        server_module._rebind_storage_backend_for_mode(OperatingMode.SERVER)


def test_state_manager_default_backend_fail_closed_without_postgres(monkeypatch) -> None:
    fake = _fake_settings(storage_backend="postgres", db_url=None)
    monkeypatch.setattr(settings_module, "settings", fake)
    monkeypatch.setattr(manager_module, "settings", fake)

    with pytest.raises(RuntimeError, match="requires Postgres configuration"):
        StateManager(path=None, storage_backend=None)


def test_state_manager_explicit_db_path_preserves_standalone_sqlite(monkeypatch, tmp_path) -> None:
    fake = _fake_settings(storage_backend="postgres", db_url=None)
    monkeypatch.setattr(settings_module, "settings", fake)
    monkeypatch.setattr(manager_module, "settings", fake)

    backend = StateManager(path=tmp_path / "explicit-state", storage_backend=None)._storage_backend
    assert isinstance(backend, SQLiteStorage)


def test_server_mode_rejects_sqlite_backend_even_when_db_url_is_set(monkeypatch) -> None:
    fake = _fake_settings(
        mode="server",
        storage_backend="sqlite",
        db_url="postgresql://scribe_app:pass@127.0.0.1:5432/scribe",
    )
    monkeypatch.setattr(settings_module, "settings", fake)
    monkeypatch.setattr(server_module, "settings", fake)

    with pytest.raises(RuntimeError, match="requires SCRIBE_STORAGE_BACKEND=postgres"):
        server_module._rebind_storage_backend_for_mode(OperatingMode.SERVER)


def test_storage_diagnostics_reports_resolve_error_for_server_sqlite_db_url(monkeypatch) -> None:
    fake = _fake_settings(
        mode="server",
        storage_backend="sqlite",
        db_url="postgresql://scribe_app:pass@127.0.0.1:5432/scribe",
    )
    monkeypatch.setattr(settings_module, "settings", fake)
    monkeypatch.setattr(doctor_module, "settings", fake)

    diagnostics = doctor_module._storage_diagnostics()

    assert diagnostics["resolved_mode"] is None
    assert "requires SCRIBE_STORAGE_BACKEND=postgres" in (diagnostics["resolve_error"] or "")
    assert any("SQLite selected while SCRIBE_DB_URL is set" in warning for warning in diagnostics["warnings"])
