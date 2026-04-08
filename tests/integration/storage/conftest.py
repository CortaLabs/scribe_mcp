"""Area-local fixtures for storage backend integration contract tests."""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio

from scribe_mcp.storage.postgres import PostgresStorage
from scribe_mcp.storage.sqlite import SQLiteStorage


def _replace_db_name(dsn: str, db_name: str) -> str:
    parts = urlsplit(dsn)
    path = f"/{db_name}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


async def _create_test_database(base_dsn: str, admin_dsn: str, db_name: str) -> str:
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{db_name}";')
    finally:
        await admin.close()
    return _replace_db_name(base_dsn, db_name)


async def _drop_test_database(admin_dsn: str, db_name: str) -> None:
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1
              AND pid <> pg_backend_pid();
            """,
            db_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}";')
    finally:
        await admin.close()


@pytest_asyncio.fixture(
    params=[
        pytest.param("sqlite", id="sqlite"),
        pytest.param("postgres", marks=pytest.mark.postgres, id="postgres"),
    ]
)
async def backend(request, tmp_path):
    backend_name = request.param
    if backend_name == "sqlite":
        storage = SQLiteStorage(db_path=tmp_path / "conformance.sqlite3")
        await storage.setup()
        try:
            yield storage, "sqlite"
        finally:
            await storage.close()
        return

    base_dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not base_dsn:
        pytest.skip("Set SCRIBE_TEST_POSTGRES_URL to enable Postgres conformance tests")
    admin_dsn = os.getenv("SCRIBE_TEST_POSTGRES_ADMIN_URL", _replace_db_name(base_dsn, "postgres"))

    db_name = f"scribe_p8_{uuid.uuid4().hex[:10]}"
    using_shared_db = False
    try:
        test_dsn = await _create_test_database(base_dsn, admin_dsn, db_name)
    except asyncpg.InsufficientPrivilegeError:
        using_shared_db = True
        test_dsn = base_dsn

    storage = PostgresStorage(test_dsn)
    setattr(storage, "_conformance_projects", [])
    setattr(storage, "_conformance_isolated_db", not using_shared_db)
    await storage.setup()
    try:
        yield storage, "postgres"
    finally:
        for project_name in getattr(storage, "_conformance_projects", []):
            try:
                await storage.delete_project(project_name)
            except Exception:
                pass
        await storage.close()
        if not using_shared_db:
            await _drop_test_database(admin_dsn, db_name)
