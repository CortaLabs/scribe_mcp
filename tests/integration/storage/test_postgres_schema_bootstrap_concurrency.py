"""Concurrent scribe-server schema bootstrap (BUG-2026-09-13-0002).

Codex starts one scribe-server per subagent thread. init.sql used to drop and
re-create the unique ``idx_scribe_sessions_transport`` index on every start, and
the duplicate-index race guard only matched ``CREATE INDEX``, so a concurrent
start died before MCP initialize and its thread ran with no Scribe tools.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import asyncpg
import pytest

from scribe_mcp.storage.postgres import schema as schema_mod


REPO_ROOT = Path(__file__).resolve().parents[3]
INIT_SQL = REPO_ROOT / "src/scribe_mcp/db/init.sql"


class _IndexRace(asyncpg.UniqueViolationError):
    def __init__(self) -> None:
        pass

    def __str__(self) -> str:
        return (
            'duplicate key value violates unique constraint "pg_class_relname_nsp_index"'
        )


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE INDEX IF NOT EXISTS idx_a ON t(a)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_b ON t(b) WHERE b IS NOT NULL",
        "  create unique index idx_c on t(c)",
    ],
)
def test_duplicate_index_race_guard_matches_unique_indexes(statement: str) -> None:
    assert schema_mod._is_duplicate_index_race(statement, _IndexRace())


def test_duplicate_index_race_guard_ignores_other_statements() -> None:
    assert not schema_mod._is_duplicate_index_race(
        "CREATE TABLE IF NOT EXISTS t (a int)", _IndexRace()
    )
    assert not schema_mod._is_duplicate_index_race(
        "DROP INDEX IF EXISTS idx_scribe_sessions_transport", _IndexRace()
    )


def test_init_sql_no_longer_rebuilds_the_transport_index_every_start() -> None:
    text = INIT_SQL.read_text(encoding="utf-8")
    assert "DROP INDEX IF EXISTS idx_scribe_sessions_transport" not in text
    assert "idx_scribe_sessions_transport" not in text


class _RecordingConn:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append(query)
        if self.fail_on and self.fail_on in query:
            raise RuntimeError("boom")
        return "OK"

    async def fetchval(self, query: str, *args: object) -> object:
        self.calls.append(query)
        return None


def test_bootstrap_holds_the_advisory_lock_and_releases_it_on_failure(
    tmp_path: Path,
) -> None:
    schema_sql = tmp_path / "init.sql"
    schema_sql.write_text("CREATE TABLE IF NOT EXISTS t (a int);\n", encoding="utf-8")
    conn = _RecordingConn(fail_on="CREATE TABLE IF NOT EXISTS t")
    with pytest.raises(RuntimeError):
        asyncio.run(
            schema_mod.ensure_schema_on_connection(
                conn=conn,
                schema_name="scribe_lock_probe",
                schema_path=schema_sql,
                migrations_path=tmp_path / "absent",
            )
        )
    assert "pg_advisory_lock" in conn.calls[0]
    assert "pg_advisory_unlock" in conn.calls[-1]


def test_concurrent_bootstrap_on_one_schema_never_fails() -> None:
    dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip("Set SCRIBE_TEST_POSTGRES_URL to run the live concurrent bootstrap")
    schema_name = f"scribe_bootstrap_race_{uuid.uuid4().hex[:12]}"

    async def one_start() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await schema_mod.ensure_schema_on_connection(
                conn=conn, schema_name=schema_name
            )
        finally:
            await conn.close()

    async def run() -> list[object]:
        probe = await asyncpg.connect(dsn)
        try:
            trgm_schema = await probe.fetchval(
                "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n "
                "ON n.oid = e.extnamespace WHERE e.extname = 'pg_trgm'"
            )
        finally:
            await probe.close()
        if trgm_schema not in (None, "public"):
            # init.sql's gin_trgm_ops index resolves pg_trgm through
            # search_path = <schema>, public; an extension installed in another
            # schema cannot bootstrap a fresh disposable schema at all.
            pytest.skip(f"pg_trgm is installed in schema {trgm_schema!r}, not public")
        try:
            await one_start()  # a fresh schema first, then the steady-state race
            return await asyncio.gather(
                *(one_start() for _ in range(8)), return_exceptions=True
            )
        finally:
            conn = await asyncpg.connect(dsn)
            try:
                await conn.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE;')
            finally:
                await conn.close()

    results = asyncio.run(run())
    assert [r for r in results if isinstance(r, BaseException)] == []
