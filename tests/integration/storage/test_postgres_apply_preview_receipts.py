"""PostgreSQL apply-preview receipt schema and atomic lifecycle coverage."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import asyncpg

from scribe_mcp.storage.models import ApplyPreviewReceiptRecord
from scribe_mcp.storage.postgres import PostgresStorage
from fixtures.storage import (
    apply_preview_receipt as _receipt,
    apply_preview_receipt_row as _row,
    apply_preview_receipt_with_nested_json as _receipt_with_nested_json,
)


pytestmark = pytest.mark.storage


REPO_ROOT = Path(__file__).resolve().parents[3]
INIT_SQL = REPO_ROOT / "src/scribe_mcp/db/init.sql"
MIGRATION_SQL = (
    REPO_ROOT / "src/scribe_mcp/db/postgres_migrations/005_apply_preview_receipts.sql"
)


@pytest_asyncio.fixture
async def live_postgres_storage():
    dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip(
            "Set SCRIBE_TEST_POSTGRES_URL to enable live PostgreSQL receipt tests"
        )
    schema_name = f"scribe_apply_preview_{uuid.uuid4().hex[:12]}"
    storage = PostgresStorage(
        dsn,
        schema_name=schema_name,
        pool_min_size=1,
        pool_max_size=8,
    )
    await storage.setup()
    try:
        yield storage
    finally:
        await storage.close()
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE;')
        finally:
            await conn.close()


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("state", ["issued", "applied"])
async def test_live_receipt_json_roundtrip_preserves_strict_record(
    live_postgres_storage: PostgresStorage, state: str,
) -> None:
    record = _receipt_with_nested_json(state=state)

    persisted = await live_postgres_storage.issue_apply_preview_receipt(record)
    fetched = await live_postgres_storage.fetch_apply_preview_receipt(record.token_sha256)

    assert persisted == record
    assert fetched == record


def _table_definition(sql: str) -> str:
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS apply_preview_receipts\s*\((.*?)\);",
        sql,
        flags=re.DOTALL,
    )
    assert match is not None
    return " ".join(match.group(1).split())


def test_fresh_schema_and_numbered_migration_define_identical_receipt_table() -> None:
    fresh = INIT_SQL.read_text(encoding="utf-8")
    migration = MIGRATION_SQL.read_text(encoding="utf-8")

    assert _table_definition(fresh) == _table_definition(migration)
    for index_name in (
        "idx_apply_preview_receipts_expires_at",
        "idx_apply_preview_receipts_state_lease",
    ):
        assert f"CREATE INDEX IF NOT EXISTS {index_name}" in fresh
        assert f"CREATE INDEX IF NOT EXISTS {index_name}" in migration
    assert "CREATE TABLE IF NOT EXISTS" in migration


@pytest.mark.asyncio
async def test_issue_uses_jsonb_and_decodes_the_persisted_record() -> None:
    storage = PostgresStorage("postgresql://unused")
    record = _receipt()
    fetchrow = AsyncMock(return_value=_row(record))
    storage._fetchrow = fetchrow  # type: ignore[method-assign]

    persisted = await storage.issue_apply_preview_receipt(record)

    assert persisted == record
    sql = fetchrow.await_args.args[0]
    assert "INSERT INTO apply_preview_receipts" in sql
    assert sql.count("::jsonb") == 5
    assert "token_sha256" in sql
    assert "receipt" not in persisted.__dict__


@pytest.mark.asyncio
async def test_fetch_decodes_jsonb_to_canonical_json_strings() -> None:
    storage = PostgresStorage("postgresql://unused")
    record = _receipt()
    storage._fetchrow = AsyncMock(return_value=_row(record))  # type: ignore[method-assign]

    fetched = await storage.fetch_apply_preview_receipt(record.token_sha256)

    assert fetched == record


@pytest.mark.asyncio
async def test_claim_is_one_atomic_database_time_update() -> None:
    storage = PostgresStorage("postgresql://unused")
    applying = _receipt(state="applying", fence=1)
    fetchrow = AsyncMock(return_value=_row(applying))
    storage._fetchrow = fetchrow  # type: ignore[method-assign]

    result = await storage.claim_apply_preview_receipt("a" * 64, lease_seconds=60)

    assert result.status == "claimed"
    assert result.record == applying
    assert fetchrow.await_count == 1
    sql = fetchrow.await_args.args[0]
    assert "UPDATE apply_preview_receipts" in sql
    assert "RETURNING" in sql
    assert "NOW()" in sql
    assert "fence = fence + 1" in sql
    assert "state = 'issued'" in sql
    assert "apply_lease_expires_at <= NOW()" in sql


@pytest.mark.asyncio
async def test_claim_reports_recovery_for_incremented_fence() -> None:
    storage = PostgresStorage("postgresql://unused")
    recovered = _receipt(state="applying", fence=2)
    storage._fetchrow = AsyncMock(return_value=_row(recovered))  # type: ignore[method-assign]

    result = await storage.claim_apply_preview_receipt("a" * 64, lease_seconds=60)

    assert result.status == "recovery"
    assert result.record == recovered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (_receipt(state="applied", fence=1), "terminal"),
        (_receipt(state="applying", fence=1), "busy"),
    ],
)
async def test_failed_claim_classifies_current_row(
    record: ApplyPreviewReceiptRecord,
    expected: str,
) -> None:
    storage = PostgresStorage("postgresql://unused")
    fetchrow = AsyncMock(side_effect=[None, _row(record)])
    storage._fetchrow = fetchrow  # type: ignore[method-assign]

    result = await storage.claim_apply_preview_receipt("a" * 64, lease_seconds=60)

    assert result.status == expected
    assert result.record == record
    assert fetchrow.await_count == 2


@pytest.mark.asyncio
async def test_finalize_is_fenced_and_rejects_stale_writer() -> None:
    storage = PostgresStorage("postgresql://unused")
    fetchrow = AsyncMock(return_value=None)
    storage._fetchrow = fetchrow  # type: ignore[method-assign]

    with pytest.raises(LookupError, match="no active fenced claim"):
        await storage.finalize_apply_preview_receipt(
            "a" * 64,
            fence=1,
            terminal_state="applied",
            result_code="APPLY_RECEIPT_APPLIED",
            result_json='{"ok":true}',
        )

    sql = fetchrow.await_args.args[0]
    assert "UPDATE apply_preview_receipts" in sql
    assert "state = 'applying'" in sql
    assert "fence = $2" in sql
    assert "NOW()" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_cleanup_uses_database_time_and_preserves_active_lease() -> None:
    storage = PostgresStorage("postgresql://unused")
    storage._fetchval = AsyncMock(return_value=3)  # type: ignore[method-assign]

    deleted = await storage.cleanup_apply_preview_receipts()

    assert deleted == 3
    sql = storage._fetchval.await_args.args[0]  # type: ignore[attr-defined]
    assert "expires_at <= NOW()" in sql
    assert "state <> 'applying'" in sql
    assert "LIMIT 100" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_claim_rejects_non_positive_lease_without_query() -> None:
    storage = PostgresStorage("postgresql://unused")
    storage._fetchrow = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="lease_seconds must be a positive integer"):
        await storage.claim_apply_preview_receipt("a" * 64, lease_seconds=0)

    storage._fetchrow.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.regression
async def test_live_migration_is_idempotent_and_schema_scoped(
    live_postgres_storage,
) -> None:
    storage = live_postgres_storage
    pool = await storage._ensure_pool()
    migration_sql = MIGRATION_SQL.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT current_schema();") == storage.schema_name
        await conn.execute(migration_sql)
        await conn.execute(migration_sql)
        assert (
            await conn.fetchval(
                """
            SELECT COUNT(*)
            FROM pg_tables
            WHERE schemaname = $1 AND tablename = 'apply_preview_receipts';
            """,
                storage.schema_name,
            )
            == 1
        )
        assert (
            await conn.fetchval(
                """
            SELECT COUNT(*)
            FROM pg_indexes
            WHERE schemaname = $1
              AND indexname IN (
                  'idx_apply_preview_receipts_expires_at',
                  'idx_apply_preview_receipts_state_lease'
              );
            """,
                storage.schema_name,
            )
            == 2
        )
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM scribe_migrations WHERE name = $1;",
                "sql:005_apply_preview_receipts.sql",
            )
            == 1
        )


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.regression
async def test_live_concurrent_claim_recovery_replay_and_cleanup(
    live_postgres_storage,
) -> None:
    storage = live_postgres_storage
    issued = replace(_receipt(), token_sha256="b" * 64)
    await storage.issue_apply_preview_receipt(issued)

    claims = await asyncio.gather(
        *(
            storage.claim_apply_preview_receipt(issued.token_sha256, lease_seconds=60)
            for _ in range(6)
        )
    )
    assert [claim.status for claim in claims].count("claimed") == 1
    assert [claim.status for claim in claims].count("busy") == 5
    assert (
        next(claim.record for claim in claims if claim.status == "claimed").fence == 1
    )

    now = datetime.now(timezone.utc)
    recoverable = replace(
        _receipt(state="applying", fence=1),
        token_sha256="c" * 64,
        apply_lease_expires_at=now - timedelta(seconds=1),
    )
    await storage.issue_apply_preview_receipt(recoverable)
    recovery = await storage.claim_apply_preview_receipt(
        recoverable.token_sha256, lease_seconds=60
    )
    assert recovery.status == "recovery"
    assert recovery.record is not None
    assert recovery.record.fence == 2

    with pytest.raises(LookupError, match="no active fenced claim"):
        await storage.finalize_apply_preview_receipt(
            recoverable.token_sha256,
            fence=1,
            terminal_state="applied",
            result_code="APPLY_RECEIPT_APPLIED",
            result_json='{"ok":true}',
        )
    terminal = await storage.finalize_apply_preview_receipt(
        recoverable.token_sha256,
        fence=2,
        terminal_state="applied",
        result_code="APPLY_RECEIPT_APPLIED",
        result_json='{"ok":true}',
    )
    replay = await storage.claim_apply_preview_receipt(
        recoverable.token_sha256, lease_seconds=60
    )
    assert replay.status == "terminal"
    assert replay.record == terminal

    old_issued = now - timedelta(minutes=20)
    old_expiry = now - timedelta(minutes=10)
    expired = replace(
        _receipt(),
        token_sha256="d" * 64,
        issued_at=old_issued,
        expires_at=old_expiry,
        updated_at=old_issued,
    )
    active_lease = replace(
        _receipt(state="applying", fence=1),
        token_sha256="e" * 64,
        issued_at=old_issued,
        expires_at=old_expiry,
        apply_lease_expires_at=now + timedelta(minutes=5),
        updated_at=now,
    )
    await storage.issue_apply_preview_receipt(expired)
    await storage.issue_apply_preview_receipt(active_lease)

    assert await storage.cleanup_apply_preview_receipts() == 1
    assert await storage.fetch_apply_preview_receipt(expired.token_sha256) is None
    assert (
        await storage.fetch_apply_preview_receipt(active_lease.token_sha256) is not None
    )
