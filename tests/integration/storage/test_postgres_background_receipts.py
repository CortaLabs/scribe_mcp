"""C-08 PostgreSQL contracts; live nodes require the REL-VAL.1 fixture.

Collection and the presence selector are offline. All database/process nodes
consume only swarm_postgres_backend, never the generic shared-fallback fixture.
"""
from __future__ import annotations

import asyncio
import importlib.util
import multiprocessing
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from fixtures.swarm import ManualClock
_name = "_scribe_c08_test_background_receipt_contract"
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, Path(__file__).resolve().parents[2] / "storage/test_background_receipt_contract.py")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
_contract = sys.modules[_name]
api, intent, limits = _contract.api, _contract.intent, _contract.limits
require_backend, wall_time = _contract.require_backend, _contract.wall_time
_sqlite = _contract.load_suite("storage/test_sqlite_background_receipts.py")
check_atomic_last_slot = _sqlite.check_atomic_last_slot
check_claim_order_and_exclusivity = _sqlite.check_claim_order_and_exclusivity
check_fences_and_version, check_idempotency = _sqlite.check_fences_and_version, _sqlite.check_idempotency
check_retry_capacity_and_terminal_release = _sqlite.check_retry_capacity_and_terminal_release
ready, snapshot = _sqlite.ready, _sqlite.snapshot

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.regression,
              pytest.mark.usefixtures("test_agent")]


@asynccontextmanager
async def postgres_store(reference, *, clock=None):
    from scribe_mcp.storage.postgres import PostgresStorage
    require_backend(PostgresStorage)
    models, store_class = api()
    clock = clock if clock is not None else ManualClock()
    # REL-VAL.1 owns opt-in, collision/host policy, creation and exact DB drop.
    # The DSN remains in memory and is never part of assertions or artifacts.
    backend = PostgresStorage(reference.dsn, pool_min_size=1, pool_max_size=32)
    try:
        await backend.setup()
        yield store_class(backend, clock=lambda: wall_time(clock)), backend, models, clock
    finally:
        await backend.close()


def _process_admit(dsn, connection, release, index, bound):
    """One independent client process; control messages contain no credentials."""
    async def execute():
        from scribe_mcp.storage.postgres import PostgresStorage
        models, store_class = api()
        backend = PostgresStorage(dsn, pool_min_size=1, pool_max_size=1)
        clock = ManualClock()
        try:
            await backend.setup()
            connection.send("ready")
            released = await asyncio.to_thread(release.wait, 30)
            assert released, "coordinator did not release admission gate"
            cap = limits(models, **{f"max_pending_{bound}": 1 if bound == "items" else 8})
            result = await store_class(backend, clock=lambda: wall_time(clock)).admit(
                intent(models, f"process-{index:02d}"), cap)
            connection.send((result.status, result.receipt.operation_id if result.receipt else None))
        finally:
            await backend.close()
    try:
        asyncio.run(asyncio.wait_for(execute(), 45))
    finally:
        connection.close()


def _process_claim(dsn, connection, test_agent):
    async def execute():
        from scribe_mcp.storage.postgres import PostgresStorage
        models, store_class = api()
        backend = PostgresStorage(dsn, pool_min_size=1, pool_max_size=1)
        clock = ManualClock()
        try:
            await backend.setup()
            row = await store_class(backend, clock=lambda: wall_time(clock)).claim(
                models.BackgroundPartitionV1("project-a", "durable"), test_agent, 100)
            assert row is not None
            connection.send((row.operation_id, row.state_version, row.fencing_token))
            # Parent kills this process after the durable claim, before expiry.
            await asyncio.Event().wait()
        finally:
            await backend.close()
    try:
        asyncio.run(asyncio.wait_for(execute(), 45))
    finally:
        connection.close()


class TestSBRPostgresReceipts:
    def test_required_contract_is_present(self):
        from scribe_mcp.storage.postgres import PostgresStorage
        require_backend(PostgresStorage)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scope", ["global", "project"])
    @pytest.mark.parametrize("bound", ["items", "bytes"])
    async def test_last_item_and_byte_slot_is_atomic_under_32_connections(self, swarm_postgres_backend, scope, bound):
        async with postgres_store(swarm_postgres_backend) as (store, _, models, clock):
            await check_atomic_last_slot(store, models, clock, scope=scope, bound=bound)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bound", ["items", "bytes"])
    async def test_last_item_and_byte_slot_is_atomic_under_32_processes(self, swarm_postgres_backend, test_agent, bound):
        async with postgres_store(swarm_postgres_backend) as (store, _, models, clock):
            context = multiprocessing.get_context("spawn")
            release = context.Event()
            processes, connections, child_connections = [], [], []
            try:
                for index in range(32):
                    parent, child = context.Pipe()
                    child_connections.append(child)
                    process = context.Process(target=_process_admit,
                        args=(swarm_postgres_backend.dsn, child, release, index, bound))
                    connections.append(parent)
                    process.start()
                    processes.append(process)
                    child.close()
                for connection in connections:
                    assert await asyncio.to_thread(connection.poll, 30), "receipt child did not initialize"
                    assert connection.recv() == "ready"
                release.set()
                results = []
                for connection in connections:
                    assert await asyncio.to_thread(connection.poll, 30), "receipt child did not finish"
                    results.append(connection.recv())
                assert [status for status, _ in results].count("accepted") == 1
                assert [status for status, _ in results].count("busy") == 31
                recovered = await store.recover(wall_time(clock))
                assert recovered.pending_items == 1 and recovered.pending_bytes == 8
                assert {row.operation_id for row in recovered.receipts} == {operation for status, operation in results if status == "accepted"}
                for process in processes:
                    await asyncio.to_thread(process.join, 5)
                    assert process.exitcode == 0
            finally:
                release.set()
                leaked = []
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                    await asyncio.to_thread(process.join, 5)
                    if process.is_alive():
                        process.kill()
                        await asyncio.to_thread(process.join, 5)
                    if process.is_alive():
                        leaked.append(process.pid)
                for connection in connections:
                    connection.close()
                for connection in child_connections:
                    connection.close()
                assert not leaked, "owned receipt child leaked"

    @pytest.mark.asyncio
    async def test_idempotency_and_digest_conflict_are_race_safe(self, swarm_postgres_backend):
        async with postgres_store(swarm_postgres_backend) as (store, _, models, clock):
            original = intent(models)
            results = await asyncio.wait_for(asyncio.gather(*(
                store.admit(replace(original, operation_id=f"idempotent-{index:02d}"), limits(models))
                for index in range(32))), 15)
            assert [result.status for result in results].count("accepted") == 1
            assert [result.status for result in results].count("duplicate") == 31
            canonical = next(result.receipt for result in results if result.status == "accepted")
            assert all(result.receipt == canonical for result in results)
            conflicts = await asyncio.wait_for(asyncio.gather(*(
                store.admit(replace(original, operation_id=f"conflict-{index:02d}", payload_digest="b" * 64), limits(models))
                for index in range(32))), 15)
            assert all(result.status == "digest_conflict" and result.receipt is None for result in conflicts)
            await snapshot(store, models, clock, [canonical])

    @pytest.mark.asyncio
    async def test_duplicate_and_conflict_do_not_mutate_or_consume_capacity(self, swarm_postgres_backend):
        async with postgres_store(swarm_postgres_backend) as (store, _, models, clock):
            await check_idempotency(store, models, clock)

    @pytest.mark.asyncio
    async def test_skip_locked_claims_have_one_active_lease_per_partitioned_row(self, swarm_postgres_backend, test_agent):
        async with postgres_store(swarm_postgres_backend) as (store, _, models, clock):
            await check_claim_order_and_exclusivity(store, models, clock, test_agent)

    @pytest.mark.asyncio
    async def test_worker_death_lease_recovery_rejects_old_fence_and_version(self, swarm_postgres_backend, test_agent):
        async with postgres_store(swarm_postgres_backend) as (store, backend, models, clock):
            await check_fences_and_version(store, models, clock, test_agent)
            before = await store.recover(wall_time(clock))
            await backend.close()  # destroy the owning client and construct a fresh pool
            clock.advance(100)
            async with postgres_store(swarm_postgres_backend, clock=clock) as (fresh, _, _, _):
                expired = await fresh.recover(wall_time(clock))
                assert expired.receipts == before.receipts
                assert expired.reclaimable_operation_ids == ("operation-0",)
                old = expired.receipts[0]
                reclaimed = await fresh.claim(models.BackgroundPartitionV1("project-a", "durable"), test_agent, 100)
                assert reclaimed.fencing_token == old.fencing_token + 1
                with pytest.raises(models.BackgroundStaleFenceError):
                    await fresh.transition(reclaimed.operation_id, reclaimed.state_version, old.fencing_token,
                        models.BackgroundTransitionOutcomeV1("succeeded", result_ref="artifact:result"))
                assert await fresh.get(reclaimed.operation_id) == reclaimed

    @pytest.mark.asyncio
    async def test_forced_worker_process_death_preserves_receipt_until_fenced_reclaim(self, swarm_postgres_backend, test_agent):
        async with postgres_store(swarm_postgres_backend) as (store, _, models, clock):
            await ready(store, models)
            context = multiprocessing.get_context("spawn")
            parent, child = context.Pipe()
            process = context.Process(target=_process_claim, args=(swarm_postgres_backend.dsn, child, test_agent))
            try:
                process.start()
                child.close()
                assert await asyncio.to_thread(parent.poll, 30), "worker did not persist its claim"
                operation_id, version, fence = parent.recv()
                process.terminate()
                await asyncio.to_thread(process.join, 5)
                assert not process.is_alive() and process.exitcode != 0
                persisted = await store.get(operation_id)
                assert persisted.state == "leased" and persisted.state_version == version
                assert persisted.fencing_token == fence
                partition = models.BackgroundPartitionV1("project-a", "durable")
                assert await store.claim(partition, test_agent, 100) is None
                clock.advance(100)
                assert (await store.recover(wall_time(clock))).reclaimable_operation_ids == (operation_id,)
                reclaimed = await store.claim(partition, test_agent, 100)
                assert reclaimed.fencing_token == fence + 1 and reclaimed.state_version == version + 1
                with pytest.raises(models.BackgroundStaleFenceError):
                    await store.transition(operation_id, reclaimed.state_version, fence,
                        models.BackgroundTransitionOutcomeV1("succeeded", result_ref="artifact:result"))
                assert await store.get(operation_id) == reclaimed
            finally:
                if process.is_alive():
                    process.kill()
                await asyncio.to_thread(process.join, 5)
                parent.close()
                child.close()
                assert not process.is_alive(), "owned receipt worker leaked"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("terminal", ["succeeded", "failed_terminal", "cancelled"])
    async def test_terminal_release_and_retry_retention(self, swarm_postgres_backend, test_agent, terminal):
        async with postgres_store(swarm_postgres_backend) as (store, _, models, clock):
            await check_retry_capacity_and_terminal_release(store, models, clock, test_agent, terminal)

    @pytest.mark.asyncio
    async def test_fresh_runtime_recovers_exact_nonterminal_accounting(self, swarm_postgres_backend, test_agent):
        async with postgres_store(swarm_postgres_backend) as (store, backend, models, clock):
            accepted = (await store.admit(intent(models, "accepted", size=7), limits(models))).receipt
            pending = await ready(store, models, "ready", project="project-ready", size=9)
            await ready(store, models, "leased", project="project-leased", size=11)
            leased = await store.claim(models.BackgroundPartitionV1("project-leased", "durable"), test_agent, 100)
            await ready(store, models, "retry", project="project-retry", size=13)
            claimed = await store.claim(models.BackgroundPartitionV1("project-retry", "durable"), test_agent, 100)
            retry = await store.transition(claimed.operation_id, claimed.state_version, claimed.fencing_token,
                models.BackgroundTransitionOutcomeV1("retry_wait", next_attempt_at=wall_time(clock) + timedelta(seconds=1)))
            clock.advance(100)
            before = await snapshot(store, models, clock, [accepted, pending, leased, retry])
            assert before.pending_bytes == 40 and before.reclaimable_operation_ids == ("leased",)
            await backend.close()
            async with postgres_store(swarm_postgres_backend, clock=clock) as (fresh, _, _, _):
                assert await fresh.recover(wall_time(clock)) == before
                for row in before.receipts:
                    assert await fresh.get(row.operation_id) == row
