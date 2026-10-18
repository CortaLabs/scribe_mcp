from __future__ import annotations

from types import SimpleNamespace

import scribe_mcp.reminders as reminders
from scribe_mcp.storage.sqlite import SQLiteStorage


def test_reminder_storage_fail_closed_in_server_mode(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "server_fallback.sqlite3"

    import scribe_mcp.server as server_module

    monkeypatch.setattr(server_module, "storage_backend", None, raising=False)
    fake_settings = SimpleNamespace(
        storage_backend="postgres",
        mode="server",
        db_url="postgresql://user:pass@localhost:5432/scribe",
        remote_server_url="",
        public_release=False,
        release_profile="internal",
        sqlite_path=str(sqlite_path),
    )
    monkeypatch.setattr("scribe_mcp.config.settings.settings", fake_settings)
    monkeypatch.setattr("scribe_mcp.shared.project_registry.settings", fake_settings)
    monkeypatch.setattr("scribe_mcp.storage.create_storage_backend", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    storage = reminders._resolve_reminder_storage()

    assert storage is None
    assert not sqlite_path.exists()


def test_reminder_storage_standalone_sqlite_fallback_is_explicit(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "standalone_fallback.sqlite3"

    import scribe_mcp.server as server_module

    monkeypatch.setattr(server_module, "storage_backend", None, raising=False)
    fake_settings = SimpleNamespace(
        storage_backend="sqlite",
        mode="standalone",
        db_url=None,
        remote_server_url="",
        public_release=False,
        release_profile="internal",
        sqlite_path=str(sqlite_path),
    )
    monkeypatch.setattr("scribe_mcp.config.settings.settings", fake_settings)
    monkeypatch.setattr("scribe_mcp.shared.project_registry.settings", fake_settings)
    monkeypatch.setattr("scribe_mcp.storage.create_storage_backend", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr("scribe_mcp.config.paths.default_db_path", lambda: sqlite_path)

    storage = reminders._resolve_reminder_storage()

    assert isinstance(storage, SQLiteStorage)
