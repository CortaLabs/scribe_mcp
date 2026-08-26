from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
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
from scribe_mcp.storage.postgres.schema import SCHEMA_PATH, ensure_schema


def _sample_cfg(tmp_path: Path, *, persist_superuser_env: bool = False) -> BootstrapConfig:
    return BootstrapConfig(
        superuser_user="postgres",
        superuser_password="test-super-secret",
        superuser_host="127.0.0.1",
        superuser_port=5432,
        superuser_db="postgres",
        admin_user="scribe_admin",
        admin_password="test-admin-secret",
        admin_host="127.0.0.1",
        admin_port=5432,
        admin_db="postgres",
        app_user="scribe_app",
        app_password="test-app-secret",
        app_host="127.0.0.1",
        app_port=5432,
        app_db="scribe",
        schema_name="scribe",
        env_path=tmp_path / ".env",
        overwrite_env=True,
        persist_superuser_env=persist_superuser_env,
        dry_run=False,
    )


class _FakeSchemaConn:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    async def execute(self, query: str, *args: object) -> None:
        self.queries.append((query, args))

    async def fetchval(self, query: str, *args: object) -> object:
        self.queries.append((query, args))
        return None

    async def close(self) -> None:
        self.closed = True


class _FakeAcquire:
    def __init__(self, conn: _FakeSchemaConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeSchemaConn:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakePool:
    def __init__(self, conn: _FakeSchemaConn) -> None:
        self._conn = conn

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self._conn)


def test_init_sql_creates_repo_scoped_project_identity() -> None:
    sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
    projects_table = sql_text.split("CREATE TABLE IF NOT EXISTS scribe_projects", 1)[1]
    projects_table = projects_table.split(");", 1)[0]

    assert "name TEXT NOT NULL UNIQUE" not in projects_table
    assert "repo_id TEXT" in projects_table
    assert "project_key TEXT" in projects_table
    assert "REFERENCES scribe_projects(name)" not in sql_text


def test_build_dsn_escapes_credentials() -> None:
    dsn = _build_dsn(
        user="scribe user",
        password="test-p@ss:word",
        host="db.internal",
        port=5432,
        database="scribe-db",
    )
    assert dsn == "postgresql://scribe+user:test-p%40ss%3Aword@db.internal:5432/scribe-db"


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
    assert updates["SCRIBE_POSTGRES_SUPERUSER_PASSWORD"] == "test-super-secret"


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


def test_print_bootstrap_intro_omits_vector(capsys: pytest.CaptureFixture[str]) -> None:
    bootstrap_module._print_bootstrap_intro()

    captured = capsys.readouterr()
    assert "Enable pg_trgm" in captured.out
    assert "vector" not in captured.out.lower()


def test_ensure_schema_and_privileges_enables_pg_trgm_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = _sample_cfg(tmp_path)
    conn = _FakeSchemaConn()

    async def _connect(_dsn: str) -> _FakeSchemaConn:
        return conn

    monkeypatch.setattr(bootstrap_module.asyncpg, "connect", _connect)

    asyncio.run(bootstrap_module._ensure_schema_and_privileges(cfg))

    queries = [query for query, _args in conn.queries]
    assert queries[0] == "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
    assert any(query == 'CREATE SCHEMA IF NOT EXISTS "scribe";' for query in queries)
    assert all("vector" not in query.lower() for query in queries)


def test_ensure_schema_applies_pg_trgm_without_vector(tmp_path: Path) -> None:
    schema_path = tmp_path / "init.sql"
    schema_path.write_text(
        "CREATE TABLE IF NOT EXISTS example (id INTEGER);",
        encoding="utf-8",
    )
    conn = _FakeSchemaConn()
    pool = _FakePool(conn)

    async def _pool_provider() -> _FakePool:
        return pool

    result = asyncio.run(
        ensure_schema(
            pool_provider=_pool_provider,
            schema_lock=asyncio.Lock(),
            schema_ready=False,
            schema_name="scribe",
            schema_path=schema_path,
            migrations_path=tmp_path / "missing-migrations",
        )
    )

    queries = [query for query, _args in conn.queries]
    assert result is True
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm;" in queries
    assert any(query == 'SET search_path TO "scribe", public;' for query in queries)
    assert any("CREATE TABLE IF NOT EXISTS example (id INTEGER)" in query for query in queries)
    assert all("vector" not in query.lower() for query in queries)


def test_ensure_schema_defers_additive_tool_call_index_until_migration(tmp_path: Path) -> None:
    schema_path = tmp_path / "init.sql"
    schema_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS tool_calls (id SERIAL PRIMARY KEY, repo_root TEXT);
        CREATE INDEX IF NOT EXISTS idx_tool_calls_correlation ON tool_calls(correlation_id);
        """,
        encoding="utf-8",
    )
    migrations_path = tmp_path / "postgres_migrations"
    migrations_path.mkdir()
    migrations_path.joinpath("004_tool_call_correlation_metadata.sql").write_text(
        """
        ALTER TABLE tool_calls
            ADD COLUMN IF NOT EXISTS correlation_id TEXT,
            ADD COLUMN IF NOT EXISTS measurement_scope TEXT;

        CREATE INDEX IF NOT EXISTS idx_tool_calls_correlation
            ON tool_calls (correlation_id);
        """,
        encoding="utf-8",
    )

    class LegacyToolCallsConn(_FakeSchemaConn):
        async def execute(self, query: str, *args: object) -> None:
            self.queries.append((query, args))
            if "idx_tool_calls_correlation" in query and "ALTER TABLE" not in query:
                raise asyncpg.UndefinedColumnError('column "correlation_id" does not exist')

    conn = LegacyToolCallsConn()
    pool = _FakePool(conn)

    async def _pool_provider() -> _FakePool:
        return pool

    result = asyncio.run(
        ensure_schema(
            pool_provider=_pool_provider,
            schema_lock=asyncio.Lock(),
            schema_ready=False,
            schema_name="scribe",
            schema_path=schema_path,
            migrations_path=migrations_path,
        )
    )

    queries = [query for query, _args in conn.queries]
    assert result is True
    assert any("ADD COLUMN IF NOT EXISTS correlation_id" in query for query in queries)
    assert any(
        "INSERT INTO scribe_migrations" in query
        and args == ("sql:004_tool_call_correlation_metadata.sql",)
        for query, args in conn.queries
    )


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
            password="test-pa'ss",
        )
    )

    assert state == "updated"
    query, args = conn.queries[0]
    assert "$1" not in query
    assert "PASSWORD 'test-pa''ss'" in query
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
            password="test-app-pass",
            createdb=True,
            createrole=True,
        )
    )

    assert state == "created"
    query, args = conn.queries[0]
    assert "$1" not in query
    assert "CREATE ROLE \"scribe_app\" LOGIN PASSWORD 'test-app-pass' CREATEDB CREATEROLE;" == query
    assert args == ()
