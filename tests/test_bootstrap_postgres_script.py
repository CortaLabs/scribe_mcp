from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scribe_mcp.scripts import bootstrap_postgres as bootstrap_module
from scribe_mcp.scripts.bootstrap_postgres import (
    BootstrapConfig,
    _build_dsn,
    _build_env_updates,
    _config_from_args,
    _ensure_role,
    _parse_args,
    _quote_literal,
    _redact_dsn,
    _write_env_file,
)


def _sample_cfg(tmp_path: Path, *, persist_superuser_env: bool = False) -> BootstrapConfig:
    return BootstrapConfig(
        superuser_user="postgres",
        superuser_password="super-secret",
        superuser_host="127.0.0.1",
        superuser_port=5432,
        superuser_db="postgres",
        admin_user="scribe_admin",
        admin_password="admin-secret",
        admin_host="127.0.0.1",
        admin_port=5432,
        admin_db="postgres",
        app_user="scribe_app",
        app_password="app-secret",
        app_host="127.0.0.1",
        app_port=5432,
        app_db="scribe",
        schema_name="scribe",
        env_path=tmp_path / ".env",
        overwrite_env=True,
        persist_superuser_env=persist_superuser_env,
        dry_run=False,
    )


def test_build_dsn_escapes_credentials() -> None:
    dsn = _build_dsn(
        user="scribe user",
        password="p@ss:word",
        host="db.internal",
        port=5432,
        database="scribe-db",
    )
    assert dsn == "postgresql://scribe+user:p%40ss%3Aword@db.internal:5432/scribe-db"


def test_redact_dsn_masks_password() -> None:
    dsn = "postgresql://scribe_app:super-secret@127.0.0.1:5432/scribe"
    redacted = _redact_dsn(dsn)
    assert "super-secret" not in redacted
    assert "scribe_app:***@" in redacted


def test_build_env_updates_default_excludes_superuser(tmp_path: Path) -> None:
    cfg = _sample_cfg(tmp_path, persist_superuser_env=False)
    updates = _build_env_updates(cfg)
    assert updates["SCRIBE_STORAGE_BACKEND"] == "postgres"
    assert updates["SCRIBE_POSTGRES_APP_USER"] == "scribe_app"
    assert "SCRIBE_POSTGRES_SUPERUSER_PASSWORD" not in updates


def test_build_env_updates_with_superuser(tmp_path: Path) -> None:
    cfg = _sample_cfg(tmp_path, persist_superuser_env=True)
    updates = _build_env_updates(cfg)
    assert updates["SCRIBE_POSTGRES_SUPERUSER_USER"] == "postgres"
    assert updates["SCRIBE_POSTGRES_SUPERUSER_PASSWORD"] == "super-secret"


def test_write_env_file_overwrites_when_enabled(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("# base\nSCRIBE_STORAGE_BACKEND=sqlite\n", encoding="utf-8")

    _write_env_file(
        env_path,
        {
            "SCRIBE_STORAGE_BACKEND": "postgres",
            "SCRIBE_DB_URL": "postgresql://scribe_app:pass@127.0.0.1:5432/scribe",
        },
        overwrite=True,
    )

    written = env_path.read_text(encoding="utf-8")
    assert "SCRIBE_STORAGE_BACKEND=postgres" in written
    assert "SCRIBE_DB_URL=postgresql://scribe_app:pass@127.0.0.1:5432/scribe" in written


def test_write_env_file_keeps_existing_when_overwrite_disabled(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("SCRIBE_STORAGE_BACKEND=sqlite\n", encoding="utf-8")

    _write_env_file(
        env_path,
        {"SCRIBE_STORAGE_BACKEND": "postgres"},
        overwrite=False,
    )

    written = env_path.read_text(encoding="utf-8")
    assert "SCRIBE_STORAGE_BACKEND=sqlite" in written


def test_non_interactive_requires_superuser_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SCRIBE_POSTGRES_SUPERUSER_PASSWORD", raising=False)
    args = _parse_args(["--no-interactive", "--env-path", str(tmp_path / ".env")])
    with pytest.raises(SystemExit):
        _config_from_args(args, interactive=False)


def test_interactive_prompts_fill_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    text_answers = iter(
        [
            "postgres",      # superuser user
            "127.0.0.1",     # superuser host
            "postgres",      # superuser db
            "scribe_admin",  # admin role
            "127.0.0.1",     # admin host
            "postgres",      # admin db
            "scribe_app",    # app role
            "127.0.0.1",     # app host
            "scribe",        # app db
            "scribe",        # schema
        ]
    )
    int_answers = iter([5432, 5432, 5432])
    secret_answers = iter(["super-pass", "admin-pass", "app-pass"])
    bool_answers = iter([True, False])

    monkeypatch.setattr(bootstrap_module, "_prompt_text", lambda _label, default: next(text_answers, default))
    monkeypatch.setattr(bootstrap_module, "_prompt_int", lambda _label, default: next(int_answers, default))
    monkeypatch.setattr(
        bootstrap_module,
        "_prompt_secret",
        lambda _label, _current=None: next(secret_answers),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "_prompt_bool",
        lambda _label, default=True: next(bool_answers, default),
    )

    args = _parse_args(["--interactive", "--env-path", str(tmp_path / ".env"), "--dry-run"])
    cfg = _config_from_args(args, interactive=True)
    assert cfg.superuser_password == "super-pass"
    assert cfg.admin_password == "admin-pass"
    assert cfg.app_password == "app-pass"
    assert cfg.schema_name == "scribe"


def test_quote_literal_escapes_single_quotes() -> None:
    assert _quote_literal("pa'ss") == "'pa''ss'"


class _FakeRoleConn:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> None:
        self.queries.append((query, args))


def test_ensure_role_existing_uses_literal_password(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _exists(_conn: object, _name: str) -> bool:
        return True

    monkeypatch.setattr(bootstrap_module, "_role_exists", _exists)
    conn = _FakeRoleConn()

    state = asyncio.run(
        _ensure_role(
            conn,
            role_name="scribe_admin",
            password="pa'ss",
        )
    )

    assert state == "updated"
    query, args = conn.queries[0]
    assert "$1" not in query
    assert "PASSWORD 'pa''ss'" in query
    assert args == ()


def test_ensure_role_create_uses_literal_password_and_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _exists(_conn: object, _name: str) -> bool:
        return False

    monkeypatch.setattr(bootstrap_module, "_role_exists", _exists)
    conn = _FakeRoleConn()

    state = asyncio.run(
        _ensure_role(
            conn,
            role_name="scribe_app",
            password="app-pass",
            createdb=True,
            createrole=True,
        )
    )

    assert state == "created"
    query, args = conn.queries[0]
    assert "$1" not in query
    assert "CREATE ROLE \"scribe_app\" LOGIN PASSWORD 'app-pass' CREATEDB CREATEROLE;" == query
    assert args == ()
