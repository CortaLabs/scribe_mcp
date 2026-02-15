"""Bootstrap Scribe Postgres roles/database/schema using superuser credentials."""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Mapping
from urllib.parse import quote_plus, urlsplit, urlunsplit

import asyncpg

from scribe_mcp.config.settings import settings

DEFAULT_SUPERUSER_HOST = "127.0.0.1"
DEFAULT_SUPERUSER_PORT = 5432
DEFAULT_SUPERUSER_DB = "postgres"
DEFAULT_ADMIN_USER = "scribe_admin"
DEFAULT_APP_USER = "scribe_app"
DEFAULT_APP_DB = "scribe"


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _build_dsn(*, user: str, password: str, host: str, port: int, database: str) -> str:
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{int(port)}/{quote_plus(database)}"
    )


def _redact_dsn(dsn: str) -> str:
    parts = urlsplit(dsn)
    if not parts.netloc:
        return dsn
    if "@" not in parts.netloc:
        return dsn
    userinfo, hostinfo = parts.netloc.rsplit("@", 1)
    username = userinfo.split(":", 1)[0]
    safe_netloc = f"{username}:***@{hostinfo}"
    return urlunsplit((parts.scheme, safe_netloc, parts.path, parts.query, parts.fragment))


def _generated_secret() -> str:
    return secrets.token_urlsafe(24)


def _read_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    loaded: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        loaded[key.strip()] = value
    return loaded


def _write_env_file(
    env_path: Path,
    updates: Mapping[str, str],
    *,
    create: bool = True,
    overwrite: bool = True,
) -> Path:
    if not env_path.exists():
        if not create:
            raise FileNotFoundError(f".env not found: {env_path}")
        env_path.write_text("", encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    existing: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        existing[key.strip()] = value

    for key, value in updates.items():
        if key in existing and not overwrite and existing[key] != "":
            continue
        existing[key] = value

    rendered: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            rendered.append(line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in existing:
            rendered.append(f"{key}={existing[key]}")
            existing.pop(key, None)
        else:
            rendered.append(line)

    for key, value in existing.items():
        rendered.append(f"{key}={value}")

    env_path.write_text("\n".join(rendered) + "\n", encoding="utf-8")
    return env_path


def _env_or(existing: Mapping[str, str], key: str, fallback: str) -> str:
    return (os.environ.get(key) or existing.get(key) or fallback).strip() or fallback


def _env_or_secret(existing: Mapping[str, str], key: str) -> str:
    current = (os.environ.get(key) or existing.get(key) or "").strip()
    return current or _generated_secret()


def _is_interactive_stdin() -> bool:
    return sys.stdin.isatty()


def _prompt_text(label: str, default: str) -> str:
    raw = input(f"{label} [{default}]: ").strip()
    return raw or default


def _prompt_int(label: str, default: int) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return int(default)
        try:
            return int(raw)
        except ValueError:
            print("Please enter a valid integer.")


def _prompt_secret(label: str, current_value: str | None = None) -> str:
    suffix = " [hidden]" if current_value else ""
    raw = getpass(f"{label}{suffix}: ").strip()
    if raw:
        return raw
    if current_value:
        return current_value
    raise SystemExit(f"{label} is required.")


def _prompt_bool(label: str, *, default: bool) -> bool:
    default_hint = "Y/n" if default else "y/N"
    raw = input(f"{label} [{default_hint}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1", "true"}


@dataclass(frozen=True)
class BootstrapConfig:
    superuser_user: str
    superuser_password: str
    superuser_host: str
    superuser_port: int
    superuser_db: str
    admin_user: str
    admin_password: str
    admin_host: str
    admin_port: int
    admin_db: str
    app_user: str
    app_password: str
    app_host: str
    app_port: int
    app_db: str
    schema_name: str
    env_path: Path
    overwrite_env: bool
    persist_superuser_env: bool
    dry_run: bool

    @property
    def superuser_dsn(self) -> str:
        return _build_dsn(
            user=self.superuser_user,
            password=self.superuser_password,
            host=self.superuser_host,
            port=self.superuser_port,
            database=self.superuser_db,
        )

    @property
    def admin_dsn(self) -> str:
        return _build_dsn(
            user=self.admin_user,
            password=self.admin_password,
            host=self.admin_host,
            port=self.admin_port,
            database=self.admin_db,
        )

    @property
    def app_dsn(self) -> str:
        return _build_dsn(
            user=self.app_user,
            password=self.app_password,
            host=self.app_host,
            port=self.app_port,
            database=self.app_db,
        )


def _print_bootstrap_intro() -> None:
    print("Corta Labs | Scribe MCP")
    print("Postgres Bootstrap (interactive)")
    print("")
    print("This setup will:")
    print("  1) Create or update admin and app roles")
    print("  2) Create or update the app database (where Scribe data lives)")
    print("  3) Create or update the Scribe schema and grants")
    print("  4) Enable pg_trgm (and vector when available)")
    print("  5) Write runtime keys to your .env file")
    print("")
    print("Press Enter to accept defaults.")
    print("")


def _print_bootstrap_plan(cfg: BootstrapConfig) -> None:
    print("")
    print("Configuration summary:")
    print(f"  Superuser connection (setup only): {_redact_dsn(cfg.superuser_dsn)}")
    print(f"  Admin connection (schema owner):   {_redact_dsn(cfg.admin_dsn)}")
    print(f"  App connection (SCRIBE_DB_URL):    {_redact_dsn(cfg.app_dsn)}")
    print(f"  App database (stores Scribe data): {cfg.app_db}")
    print(f"  Schema namespace:                  {cfg.schema_name}")
    print(f"  Env file:                          {cfg.env_path}")
    print(f"  Overwrite existing env keys:       {cfg.overwrite_env}")
    print(f"  Persist superuser env keys:        {cfg.persist_superuser_env}")
    if cfg.dry_run:
        print("  Dry run:                           true")
    print("")


async def _role_exists(conn: asyncpg.Connection, role_name: str) -> bool:
    return bool(await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1;", role_name))


async def _ensure_role(
    conn: asyncpg.Connection,
    *,
    role_name: str,
    password: str,
    createdb: bool = False,
    createrole: bool = False,
) -> str:
    role_sql = _quote_ident(role_name)
    pass_sql = _quote_literal(password)
    exists = await _role_exists(conn, role_name)
    if exists:
        await conn.execute(f"ALTER ROLE {role_sql} LOGIN PASSWORD {pass_sql};")
        return "updated"

    clauses: list[str] = []
    if createdb:
        clauses.append("CREATEDB")
    if createrole:
        clauses.append("CREATEROLE")
    clause_sql = (" " + " ".join(clauses)) if clauses else ""
    await conn.execute(f"CREATE ROLE {role_sql} LOGIN PASSWORD {pass_sql}{clause_sql};")
    return "created"


async def _database_exists(conn: asyncpg.Connection, db_name: str) -> bool:
    return bool(await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1;", db_name))


async def _ensure_database(
    conn: asyncpg.Connection,
    *,
    db_name: str,
    owner: str,
) -> str:
    db_sql = _quote_ident(db_name)
    owner_sql = _quote_ident(owner)
    if await _database_exists(conn, db_name):
        await conn.execute(f"ALTER DATABASE {db_sql} OWNER TO {owner_sql};")
        return "updated"
    await conn.execute(f"CREATE DATABASE {db_sql} OWNER {owner_sql};")
    return "created"


async def _ensure_schema_and_privileges(cfg: BootstrapConfig) -> None:
    schema_sql = _quote_ident(cfg.schema_name)
    app_sql = _quote_ident(cfg.app_user)
    admin_sql = _quote_ident(cfg.admin_user)
    db_sql = _quote_ident(cfg.app_db)

    superuser_app_dsn = _build_dsn(
        user=cfg.superuser_user,
        password=cfg.superuser_password,
        host=cfg.superuser_host,
        port=cfg.superuser_port,
        database=cfg.app_db,
    )
    conn = await asyncpg.connect(superuser_app_dsn)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        except Exception:
            # pgvector is optional and may not be installed on all hosts.
            pass
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_sql};")
        await conn.execute(f"ALTER SCHEMA {schema_sql} OWNER TO {admin_sql};")
        await conn.execute(f"GRANT ALL PRIVILEGES ON DATABASE {db_sql} TO {app_sql};")
        await conn.execute(f"GRANT USAGE, CREATE ON SCHEMA {schema_sql} TO {app_sql};")
        await conn.execute(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema_sql} TO {app_sql};")
        await conn.execute(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema_sql} TO {app_sql};")
        await conn.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_sql} "
            f"GRANT ALL PRIVILEGES ON TABLES TO {app_sql};"
        )
        await conn.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_sql} "
            f"GRANT ALL PRIVILEGES ON SEQUENCES TO {app_sql};"
        )
    finally:
        await conn.close()


def _build_env_updates(cfg: BootstrapConfig) -> dict[str, str]:
    updates = {
        "SCRIBE_STORAGE_BACKEND": "postgres",
        "SCRIBE_DB_URL": cfg.app_dsn,
        "SCRIBE_POSTGRES_SCHEMA": cfg.schema_name,
        "SCRIBE_POSTGRES_ADMIN_USER": cfg.admin_user,
        "SCRIBE_POSTGRES_ADMIN_PASSWORD": cfg.admin_password,
        "SCRIBE_POSTGRES_ADMIN_HOST": cfg.admin_host,
        "SCRIBE_POSTGRES_ADMIN_PORT": str(cfg.admin_port),
        "SCRIBE_POSTGRES_ADMIN_DB": cfg.admin_db,
        "SCRIBE_POSTGRES_APP_USER": cfg.app_user,
        "SCRIBE_POSTGRES_APP_PASSWORD": cfg.app_password,
        "SCRIBE_POSTGRES_APP_HOST": cfg.app_host,
        "SCRIBE_POSTGRES_APP_PORT": str(cfg.app_port),
        "SCRIBE_POSTGRES_APP_DB": cfg.app_db,
    }
    if cfg.persist_superuser_env:
        updates.update(
            {
                "SCRIBE_POSTGRES_SUPERUSER_USER": cfg.superuser_user,
                "SCRIBE_POSTGRES_SUPERUSER_PASSWORD": cfg.superuser_password,
                "SCRIBE_POSTGRES_SUPERUSER_HOST": cfg.superuser_host,
                "SCRIBE_POSTGRES_SUPERUSER_PORT": str(cfg.superuser_port),
                "SCRIBE_POSTGRES_SUPERUSER_DB": cfg.superuser_db,
            }
        )
    return updates


async def _bootstrap(cfg: BootstrapConfig) -> int:
    if cfg.dry_run:
        print("Dry run complete. No database or .env changes were made.")
        return 0

    superuser_conn = await asyncpg.connect(cfg.superuser_dsn)
    try:
        admin_state = await _ensure_role(
            superuser_conn,
            role_name=cfg.admin_user,
            password=cfg.admin_password,
            createdb=True,
            createrole=True,
        )
        app_state = await _ensure_role(
            superuser_conn,
            role_name=cfg.app_user,
            password=cfg.app_password,
        )
        await superuser_conn.execute(
            f"GRANT {_quote_ident(cfg.app_user)} TO {_quote_ident(cfg.admin_user)};"
        )
        db_state = await _ensure_database(
            superuser_conn,
            db_name=cfg.app_db,
            owner=cfg.app_user,
        )
    finally:
        await superuser_conn.close()

    await _ensure_schema_and_privileges(cfg)
    _write_env_file(cfg.env_path, _build_env_updates(cfg), overwrite=cfg.overwrite_env)

    print("Bootstrap complete.")
    print(f"  Admin role: {admin_state}")
    print(f"  App role:   {app_state}")
    print(f"  Database:   {db_state}")
    print(f"  Env file updated: {cfg.env_path}")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Corta Labs / Scribe MCP Postgres bootstrap.\n"
            "Provisions roles, app database, schema grants, and runtime .env settings."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  scribe bootstrap\n"
            "  scribe bootstrap --dry-run\n"
            "  scribe bootstrap --no-interactive --superuser-password '<password>'\n"
        ),
    )
    parser.add_argument("--env-path", default=".env", help="Path to .env file (default: .env).")
    parser.add_argument("--superuser-user", default=None, help="Postgres superuser login.")
    parser.add_argument("--superuser-password", default=None, help="Postgres superuser password.")
    parser.add_argument("--superuser-host", default=None, help="Postgres superuser host.")
    parser.add_argument("--superuser-port", type=int, default=None, help="Postgres superuser port.")
    parser.add_argument(
        "--superuser-db",
        default=None,
        help="Database used by the superuser setup connection (usually postgres).",
    )
    parser.add_argument("--admin-user", default=None, help="Scribe admin role name.")
    parser.add_argument("--admin-password", default=None, help="Scribe admin role password.")
    parser.add_argument("--admin-host", default=None, help="Scribe admin host.")
    parser.add_argument("--admin-port", type=int, default=None, help="Scribe admin port.")
    parser.add_argument(
        "--admin-db",
        default=None,
        help="Database used when connecting as admin role (usually postgres).",
    )
    parser.add_argument("--app-user", default=None, help="Scribe app role name.")
    parser.add_argument("--app-password", default=None, help="Scribe app role password.")
    parser.add_argument("--app-host", default=None, help="Scribe app host.")
    parser.add_argument("--app-port", type=int, default=None, help="Scribe app port.")
    parser.add_argument("--app-db", default=None, help="App database that stores Scribe data.")
    parser.add_argument(
        "--schema",
        default=None,
        help="Scribe Postgres schema name (defaults to SCRIBE_POSTGRES_SCHEMA or 'scribe').",
    )
    parser.add_argument(
        "--overwrite-env",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Overwrite existing env keys when writing .env (default: true).",
    )
    parser.add_argument(
        "--persist-superuser-env",
        action="store_true",
        help="Also write SCRIBE_POSTGRES_SUPERUSER_* keys into .env.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the intended DSNs/env targets without mutating DB or env file.",
    )
    parser.add_argument(
        "--interactive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Prompt for missing/bootstrap values interactively (default: auto when TTY).",
    )
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace, *, interactive: bool) -> BootstrapConfig:
    env_path = Path(args.env_path).expanduser()
    existing_env = _read_env_file(env_path)

    superuser_user_default = args.superuser_user or _env_or(
        existing_env,
        "SCRIBE_POSTGRES_SUPERUSER_USER",
        "postgres",
    )
    superuser_password_default = args.superuser_password or (
        os.environ.get("SCRIBE_POSTGRES_SUPERUSER_PASSWORD")
        or existing_env.get("SCRIBE_POSTGRES_SUPERUSER_PASSWORD")
        or ""
    )
    superuser_host_default = args.superuser_host or _env_or(
        existing_env,
        "SCRIBE_POSTGRES_SUPERUSER_HOST",
        DEFAULT_SUPERUSER_HOST,
    )
    superuser_port_default = int(
        args.superuser_port
        or _env_or(existing_env, "SCRIBE_POSTGRES_SUPERUSER_PORT", str(DEFAULT_SUPERUSER_PORT))
    )
    superuser_db_default = args.superuser_db or _env_or(
        existing_env,
        "SCRIBE_POSTGRES_SUPERUSER_DB",
        DEFAULT_SUPERUSER_DB,
    )

    admin_user_default = args.admin_user or _env_or(existing_env, "SCRIBE_POSTGRES_ADMIN_USER", DEFAULT_ADMIN_USER)
    admin_password_default = args.admin_password or _env_or_secret(existing_env, "SCRIBE_POSTGRES_ADMIN_PASSWORD")
    admin_host_default = args.admin_host or _env_or(existing_env, "SCRIBE_POSTGRES_ADMIN_HOST", superuser_host_default)
    admin_port_default = int(
        args.admin_port or _env_or(existing_env, "SCRIBE_POSTGRES_ADMIN_PORT", str(superuser_port_default))
    )
    admin_db_default = args.admin_db or _env_or(existing_env, "SCRIBE_POSTGRES_ADMIN_DB", superuser_db_default)

    app_user_default = args.app_user or _env_or(existing_env, "SCRIBE_POSTGRES_APP_USER", DEFAULT_APP_USER)
    app_password_default = args.app_password or _env_or_secret(existing_env, "SCRIBE_POSTGRES_APP_PASSWORD")
    app_host_default = args.app_host or _env_or(existing_env, "SCRIBE_POSTGRES_APP_HOST", superuser_host_default)
    app_port_default = int(args.app_port or _env_or(existing_env, "SCRIBE_POSTGRES_APP_PORT", str(superuser_port_default)))
    app_db_default = args.app_db or _env_or(existing_env, "SCRIBE_POSTGRES_APP_DB", DEFAULT_APP_DB)
    schema_default = (args.schema or _env_or(existing_env, "SCRIBE_POSTGRES_SCHEMA", settings.postgres_schema)).strip()
    if not schema_default:
        schema_default = "scribe"

    if interactive:
        _print_bootstrap_intro()
        print("Section 1/3: Superuser setup connection")
        superuser_user = _prompt_text("Postgres superuser user", superuser_user_default)
        superuser_host = _prompt_text("Postgres superuser host", superuser_host_default)
        superuser_port = _prompt_int("Postgres superuser port", superuser_port_default)
        superuser_db = _prompt_text("Superuser database (setup connection DB)", superuser_db_default)
        superuser_password = _prompt_secret("Postgres superuser password", superuser_password_default)

        print("")
        print("Section 2/3: Scribe admin role (schema owner)")
        admin_user = _prompt_text("Scribe admin role", admin_user_default)
        admin_password = _prompt_secret("Scribe admin password", admin_password_default)
        admin_host = _prompt_text("Scribe admin host", admin_host_default)
        admin_port = _prompt_int("Scribe admin port", admin_port_default)
        admin_db = _prompt_text(
            "Scribe admin database (usually postgres; setup/admin connection)",
            admin_db_default,
        )

        print("")
        print("Section 3/3: Scribe app runtime connection")
        app_user = _prompt_text("Scribe app role", app_user_default)
        app_password = _prompt_secret("Scribe app password", app_password_default)
        app_host = _prompt_text("Scribe app host", app_host_default)
        app_port = _prompt_int("Scribe app port", app_port_default)
        app_db = _prompt_text("Scribe app database (stores Scribe data)", app_db_default)
        schema_name = _prompt_text("Scribe schema (table namespace)", schema_default)
        if not schema_name:
            schema_name = "scribe"
        overwrite_env = bool(args.overwrite_env)
        if args.overwrite_env:
            overwrite_env = _prompt_bool("Overwrite existing .env keys", default=True)
        persist_superuser_env = bool(args.persist_superuser_env)
        if not args.persist_superuser_env:
            persist_superuser_env = _prompt_bool("Persist superuser credentials to .env", default=False)
    else:
        superuser_user = superuser_user_default
        superuser_host = superuser_host_default
        superuser_port = superuser_port_default
        superuser_db = superuser_db_default
        superuser_password = superuser_password_default
        if not superuser_password:
            raise SystemExit(
                "Missing superuser password. Set --superuser-password, SCRIBE_POSTGRES_SUPERUSER_PASSWORD, or use --interactive."
            )
        admin_user = admin_user_default
        admin_password = admin_password_default
        admin_host = admin_host_default
        admin_port = admin_port_default
        admin_db = admin_db_default
        app_user = app_user_default
        app_password = app_password_default
        app_host = app_host_default
        app_port = app_port_default
        app_db = app_db_default
        schema_name = schema_default
        overwrite_env = bool(args.overwrite_env)
        persist_superuser_env = bool(args.persist_superuser_env)

    if not schema_name:
        schema_name = "scribe"

    return BootstrapConfig(
        superuser_user=superuser_user,
        superuser_password=superuser_password,
        superuser_host=superuser_host,
        superuser_port=superuser_port,
        superuser_db=superuser_db,
        admin_user=admin_user,
        admin_password=admin_password,
        admin_host=admin_host,
        admin_port=admin_port,
        admin_db=admin_db,
        app_user=app_user,
        app_password=app_password,
        app_host=app_host,
        app_port=app_port,
        app_db=app_db,
        schema_name=schema_name,
        env_path=env_path,
        overwrite_env=overwrite_env,
        persist_superuser_env=persist_superuser_env,
        dry_run=bool(args.dry_run),
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    interactive = _is_interactive_stdin() if args.interactive is None else bool(args.interactive)
    try:
        cfg = _config_from_args(args, interactive=interactive)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: invalid bootstrap configuration: {exc}", file=sys.stderr)
        return 2

    _print_bootstrap_plan(cfg)

    if interactive and not cfg.dry_run:
        if not _prompt_bool("Proceed with Postgres bootstrap", default=True):
            print("Bootstrap cancelled.")
            return 130

    try:
        return asyncio.run(_bootstrap(cfg))
    except KeyboardInterrupt:
        print("\nBootstrap cancelled.")
        return 130
    except Exception as exc:
        print(f"error: bootstrap failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
