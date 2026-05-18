from __future__ import annotations

from pathlib import Path

import scribe_mcp.config.settings as settings_module


def test_settings_load_accepts_scribe_db_schema_alias(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("SCRIBE_DB_URL", "postgresql://user:pass@127.0.0.1:5432/scribe")
    monkeypatch.delenv("SCRIBE_POSTGRES_SCHEMA", raising=False)
    monkeypatch.setenv("SCRIBE_DB_SCHEMA", "scribe_alias")

    loaded = settings_module.Settings.load()

    assert loaded.postgres_schema == "scribe_alias"


def test_settings_load_defaults_to_postgres_backend(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.delenv("SCRIBE_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("SCRIBE_DB_URL", raising=False)

    loaded = settings_module.Settings.load()

    assert loaded.storage_backend == "postgres"


def test_settings_load_allows_explicit_sqlite_backend(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_STORAGE_BACKEND", "sqlite")

    loaded = settings_module.Settings.load()

    assert loaded.storage_backend == "sqlite"


def test_settings_load_prefers_canonical_postgres_schema_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("SCRIBE_DB_URL", "postgresql://user:pass@127.0.0.1:5432/scribe")
    monkeypatch.setenv("SCRIBE_POSTGRES_SCHEMA", "canonical_schema")
    monkeypatch.setenv("SCRIBE_DB_SCHEMA", "alias_schema")

    loaded = settings_module.Settings.load()

    assert loaded.postgres_schema == "canonical_schema"


def test_settings_load_accepts_scribe_sqlite_path_alias(monkeypatch, tmp_path) -> None:
    sqlite_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.delenv("SCRIBE_DB_PATH", raising=False)
    monkeypatch.setenv("SCRIBE_SQLITE_PATH", str(sqlite_path))

    loaded = settings_module.Settings.load()

    assert loaded.sqlite_path == sqlite_path


def test_settings_load_prefers_canonical_db_path_env(monkeypatch, tmp_path) -> None:
    canonical_path = tmp_path / "canonical.sqlite3"
    alias_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_DB_PATH", str(canonical_path))
    monkeypatch.setenv("SCRIBE_SQLITE_PATH", str(alias_path))

    loaded = settings_module.Settings.load()

    assert loaded.sqlite_path == canonical_path


def test_settings_load_skips_dotenv_loaders_when_disabled(monkeypatch, tmp_path) -> None:
    calls: list[Path] = []

    def _record_loader(dotenv_path: Path, override: bool = False) -> None:
        calls.append(Path(dotenv_path))

    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_DISABLE_DOTENV", "1")
    monkeypatch.setattr(settings_module, "load_dotenv", _record_loader)

    settings_module.Settings.load()

    assert calls == []


def test_settings_load_calls_dotenv_loader_when_enabled(monkeypatch, tmp_path) -> None:
    calls: list[Path] = []

    def _record_loader(dotenv_path: Path, override: bool = False) -> None:
        calls.append(Path(dotenv_path))

    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.delenv("SCRIBE_DISABLE_DOTENV", raising=False)
    monkeypatch.setattr(settings_module, "load_dotenv", _record_loader)

    settings_module.Settings.load()

    assert len(calls) == 2
