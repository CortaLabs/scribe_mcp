"""Real SQLite C-08 lifecycle, capacity, race and reopen contracts.

The reusable checks are also consumed by PostgreSQL; they contain assertions,
not a receipt-store implementation or a second effects oracle.
"""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

import pytest

from fixtures.swarm import CausalGate, ManualClock, SwarmRunMetadata, reconcile_exact_effects
# Bootstrap the shared helpers by exact file path. tests/conftest.py also puts
# legacy src/scribe_mcp on sys.path, where "storage" names production code.
_name = "_scribe_c08_test_background_receipt_contract"
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, Path(__file__).with_name("test_background_receipt_contract.py"))
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
_contract = sys.modules[_name]
api, intent, limits = _contract.api, _contract.intent, _contract.limits
require_backend, wall_time = _contract.require_backend, _contract.wall_time

pytestmark = [pytest.mark.core, pytest.mark.regression, pytest.mark.usefixtures("test_agent")]


@asynccontextmanager
async def sqlite_store(tmp_path):
    from scribe_mcp.storage.sqlite import SQLiteStorage
    # This assertion executes in the test body, before setup/DDL or any call to
    # an inherited fail-closed stub. It is the exact expected feature-RED seam.
    require_backend(SQLiteStorage)
    models, store_class = api()
    clock = ManualClock()
    backend = SQLiteStorage(tmp_path / "background.sqlite3")
    try:
        await backend.setup()
        yield store_class(backend, clock=lambda: wall_time(clock)), backend, models, clock
    finally:
        await backend.close()


async def ready(store, models, operation_id="operation-0", **changes):
    admitted = await store.admit(intent(models, operation_id, **changes), limits(models))
    assert admitted.status == "accepted"
    row = admitted.receipt
    assert row.state == "accepted" and (row.state_version, row.attempt_count, row.fencing_token) == (1, 0, 0)
    result = await store.transition(operation_id, row.state_version, row.fencing_token,
                                    models.BackgroundTransitionOutcomeV1("ready"))
    assert result.state == "ready" and result.state_version == row.state_version + 1
    return result


async def snapshot(store, models, clock, expected):
    result = await store.recover(wall_time(clock))
    assert result.pending_items == len(expected)
    assert result.pending_bytes == sum(row.payload_bytes for row in expected)
    assert {row.operation_id: row for row in result.receipts} == {row.operation_id: row for row in expected}
    return result


async def check_atomic_last_slot(store, models, clock, *, scope, bound, contenders=None):
    """32 simultaneous attempts contend for one real item/byte slot."""
    values = dict(max_pending_items=64, max_pending_bytes=4096,
                  max_project_pending_items=64, max_project_pending_bytes=4096)
    values[f"max_{'project_' if scope == 'project' else ''}pending_{bound}"] = 1 if bound == "items" else 8
    cap = limits(models, **values)
    gates = [CausalGate() for _ in range(32)]

    async def admit(index):
        await gates[index].hold()
        project = "project-a" if scope == "project" else f"project-{index}"
        client = contenders[index] if contenders is not None else store
        return await client.admit(intent(models, f"race-{index:02d}", project=project), cap)

    tasks = [asyncio.create_task(admit(index)) for index in range(32)]
    try:
        await asyncio.wait_for(asyncio.gather(*(gate.entered.wait() for gate in gates)), 15)
        for gate in gates:
            gate.release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 15)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    accepted = [result.receipt for result in results if result.status == "accepted"]
    assert len(accepted) == 1
    assert [result.status for result in results].count("busy") == 31
    for result in results:
        if result.status == "busy":
            assert result.receipt is None and result.retry_after_ms == cap.retry_after_ms
    recovered = await snapshot(store, models, clock, accepted)
    for index, result in enumerate(results):
        persisted = await store.get(f"race-{index:02d}")
        assert persisted == (result.receipt if result.status == "accepted" else None)
    # Feed measured real-store counts into the existing C-14 reconciler.
    sample = {"items": recovered.pending_items, "items_limit": cap.max_pending_items,
              "bytes": recovered.pending_bytes, "bytes_limit": cap.max_pending_bytes,
              "global": recovered.pending_items, "global_limit": cap.max_pending_items,
              "project": max(sum(row.canonical_project_key == project for row in recovered.receipts)
                             for project in {row.canonical_project_key for row in accepted}),
              "project_limit": cap.max_project_pending_items, "heavy": 0, "heavy_limit": cap.max_pending_items}
    result = reconcile_exact_effects([], [], metadata=SwarmRunMetadata(
        source_revision=subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"], text=True).strip(),
        seed=0, topology={}, set_project_count={},
        background_queue={"capacity_samples": [sample]}))
    assert result.verdict == "PASS", result.as_json_dict()


async def check_idempotency(store, models, clock):
    original = intent(models)
    first = await store.admit(original, limits(models, max_pending_items=1))
    assert first.status == "accepted"
    clock.advance(1000)
    duplicate = await store.admit(replace(original, operation_id="duplicate"), limits(models, max_pending_items=1))
    conflict = await store.admit(replace(original, operation_id="conflict", payload_digest="b" * 64), limits(models))
    assert duplicate.status == "duplicate" and duplicate.receipt == first.receipt
    assert duplicate.retry_after_ms is None
    assert conflict.status == "digest_conflict" and conflict.receipt is None and conflict.retry_after_ms is None
    assert await store.get("duplicate") is None and await store.get("conflict") is None
    assert await store.get(original.operation_id) == first.receipt
    await snapshot(store, models, clock, [first.receipt])
    other = await store.admit(replace(original, operation_id="other-project", canonical_project_key="project-b"), limits(models))
    assert other.status == "accepted"  # idempotency namespace includes canonical project
    await snapshot(store, models, clock, [first.receipt, other.receipt])


async def check_retry_capacity_and_terminal_release(store, models, clock, test_agent, terminal):
    cap = limits(models, max_pending_items=1, max_pending_bytes=8)
    row = await ready(store, models)
    partition = models.BackgroundPartitionV1("project-a", "durable")
    clock.advance(100)
    leased = await store.claim(partition, test_agent, 100)
    assert leased.operation_id == row.operation_id
    assert leased.updated_at == wall_time(clock)
    assert leased.lease_expires_at == wall_time(clock) + timedelta(milliseconds=100)
    retry = await store.transition(leased.operation_id, leased.state_version, leased.fencing_token,
        models.BackgroundTransitionOutcomeV1("retry_wait", next_attempt_at=wall_time(clock) + timedelta(milliseconds=200)))
    assert retry.lease_owner is None and retry.lease_expires_at is None
    await snapshot(store, models, clock, [retry])
    busy = await store.admit(intent(models, "over-capacity"), cap)
    assert busy.status == "busy" and busy.receipt is None
    assert await store.get("over-capacity") is None
    assert await store.claim(partition, test_agent, 100) is None
    clock.advance(200)
    claimed = await store.claim(partition, test_agent, 100)
    assert claimed.attempt_count == 2 and claimed.fencing_token == 2
    assert claimed.state_version == retry.state_version + 1
    kwargs = {"result_ref": "artifact:result"} if terminal == "succeeded" else (
        {"error_code": "PERMANENT_FAILURE"} if terminal == "failed_terminal" else {"cancel_requested": True})
    final = await store.transition(claimed.operation_id, claimed.state_version, claimed.fencing_token,
                                  models.BackgroundTransitionOutcomeV1(terminal, **kwargs))
    assert final.state == terminal and final.state_version == claimed.state_version + 1
    assert final.lease_owner is None and final.lease_expires_at is None and final.next_attempt_at is None
    await snapshot(store, models, clock, [])
    with pytest.raises((ValueError, models.BackgroundStateVersionConflictError)):
        await store.transition(final.operation_id, final.state_version, final.fencing_token,
                               models.BackgroundTransitionOutcomeV1("ready"))
    assert await store.get(final.operation_id) == final
    replacement = await store.admit(intent(models, "replacement"), cap)
    assert replacement.status == "accepted"
    denied = await store.admit(intent(models, "second-replacement"), cap)
    assert denied.status == "busy" and await store.get("second-replacement") is None
    await snapshot(store, models, clock, [replacement.receipt])


async def check_fences_and_version(store, models, clock, test_agent):
    row = await ready(store, models)
    partition = models.BackgroundPartitionV1("project-a", "durable")
    first = await store.claim(partition, test_agent, 100)
    assert (first.attempt_count, first.fencing_token, first.state_version) == (1, 1, row.state_version + 1)
    assert await store.claim(partition, test_agent, 100) is None
    clock.advance(99)
    assert (await store.recover(wall_time(clock))).reclaimable_operation_ids == ()
    clock.advance(1)
    before = await store.recover(wall_time(clock))
    assert before.reclaimable_operation_ids == (first.operation_id,)
    assert await store.get(first.operation_id) == first  # recover does not rewrite expired leases
    second = await store.claim(partition, test_agent, 100)
    assert (second.attempt_count, second.fencing_token, second.state_version) == (2, 2, first.state_version + 1)
    outcome = models.BackgroundTransitionOutcomeV1("succeeded", result_ref="artifact:result")
    with pytest.raises(models.BackgroundStaleFenceError):
        await store.transition(second.operation_id, second.state_version, first.fencing_token, outcome)
    assert await store.get(second.operation_id) == second
    with pytest.raises(models.BackgroundStateVersionConflictError):
        await store.transition(second.operation_id, first.state_version, second.fencing_token, outcome)
    assert await store.get(second.operation_id) == second
    with pytest.raises(models.BackgroundReceiptNotFoundError):
        await store.transition("not-found", 1, 0, models.BackgroundTransitionOutcomeV1("ready"))
    await snapshot(store, models, clock, [second])


async def check_claim_order_and_exclusivity(store, models, clock, test_agent):
    oldest = await ready(store, models, "oldest")
    clock.advance(1)
    later = await ready(store, models, "later", now=wall_time(clock))
    await ready(store, models, "other-project", project="project-b")
    await ready(store, models, "other-lane", lane="heavy")
    partition = models.BackgroundPartitionV1("project-a", "durable")
    claims = await asyncio.wait_for(asyncio.gather(*(store.claim(partition, test_agent, 100) for _ in range(32))), 15)
    rows = [row for row in claims if row is not None]
    assert len(rows) == 2 and {row.operation_id for row in rows} == {oldest.operation_id, later.operation_id}
    assert all(row.fencing_token == 1 and row.attempt_count == 1 for row in rows)
    assert (await store.get("other-project")).state == "ready"
    assert (await store.get("other-lane")).state == "ready"


async def parity_trace(store, models, clock, test_agent):
    """Return actual canonical dataclasses/errors for identical seeded calls."""
    trace = []
    original = intent(models)
    cap = limits(models, max_pending_items=1)
    for item, admission_limits in (
        (original, cap), (replace(original, operation_id="dup"), cap),
        (replace(original, operation_id="conflict", payload_digest="b" * 64), cap),
        (intent(models, "busy"), cap), (intent(models, "closed"), replace(cap, accepting=False)),
    ):
        trace.append(asdict(await store.admit(item, admission_limits)))
    row = await store.get(original.operation_id)
    trace.append(asdict(row))
    row = await store.transition(row.operation_id, row.state_version, row.fencing_token, models.BackgroundTransitionOutcomeV1("ready"))
    trace.append(asdict(row))
    row = await store.claim(models.BackgroundPartitionV1("project-a", "durable"), test_agent, 100)
    trace.append(asdict(row))
    clock.advance(100)
    trace.append(asdict(await store.recover(wall_time(clock))))
    reclaimed = await store.claim(models.BackgroundPartitionV1("project-a", "durable"), test_agent, 100)
    trace.append(asdict(reclaimed))
    for version, fence, exception in ((reclaimed.state_version, row.fencing_token, models.BackgroundStaleFenceError),
                                      (row.state_version, reclaimed.fencing_token, models.BackgroundStateVersionConflictError)):
        with pytest.raises(exception) as failure:
            await store.transition(reclaimed.operation_id, version, fence, models.BackgroundTransitionOutcomeV1("succeeded", result_ref="artifact:result"))
        trace.append(type(failure.value).__name__)
    terminal = await store.transition(reclaimed.operation_id, reclaimed.state_version, reclaimed.fencing_token,
                                     models.BackgroundTransitionOutcomeV1("succeeded", result_ref="artifact:result"))
    trace.append(asdict(terminal))
    trace.append(asdict(await store.recover(wall_time(clock))))
    trace.append(asdict(await store.admit(intent(models, "replacement"), cap)))
    return trace


class TestSBRSQLiteReceipts:
    def test_required_contract_is_present(self):
        from scribe_mcp.storage.sqlite import SQLiteStorage
        require_backend(SQLiteStorage)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scope", ["global", "project"])
    @pytest.mark.parametrize("bound", ["items", "bytes"])
    async def test_last_item_and_byte_slot_is_atomic_under_32_admissions(self, tmp_path, scope, bound):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            from scribe_mcp.storage.sqlite import SQLiteStorage
            _, store_class = api()
            backends = []
            try:
                for _ in range(31):
                    backend = SQLiteStorage(tmp_path / "background.sqlite3")
                    backends.append(backend)
                    await backend.setup()
                clients = [store] + [store_class(backend, clock=lambda: wall_time(clock)) for backend in backends]
                await check_atomic_last_slot(store, models, clock, scope=scope, bound=bound, contenders=clients)
            finally:
                await asyncio.gather(*(backend.close() for backend in backends))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scope", ["global", "project"])
    async def test_exact_byte_boundary_and_one_byte_overflow(self, tmp_path, scope):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            cap = limits(models, **{f"max_{'project_' if scope == 'project' else ''}pending_bytes": 8})
            first = await store.admit(intent(models, "seven", size=7), cap)
            second = await store.admit(intent(models, "one", size=1), cap)
            assert first.status == second.status == "accepted"
            denied = await store.admit(intent(models, "one-too-many", size=1), cap)
            assert denied.status == "busy" and denied.retry_after_ms == cap.retry_after_ms
            assert await store.get("one-too-many") is None
            await snapshot(store, models, clock, [first.receipt, second.receipt])

    @pytest.mark.asyncio
    async def test_facade_propagates_the_one_manual_clock_to_persistence(self, tmp_path, test_agent):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            clock.advance(123)
            admitted = await store.admit(intent(models), limits(models))
            assert admitted.receipt.updated_at == wall_time(clock)
            clock.advance(17)
            row = await store.transition(admitted.receipt.operation_id, 1, 0, models.BackgroundTransitionOutcomeV1("ready"))
            assert row.updated_at == wall_time(clock)
            clock.advance(23)
            claimed = await store.claim(models.BackgroundPartitionV1("project-a", "durable"), test_agent, 100)
            assert claimed.updated_at == wall_time(clock)
            assert claimed.lease_expires_at == wall_time(clock) + timedelta(milliseconds=100)
            assert await store.recover(claimed.lease_expires_at) == models.BackgroundRecoverySnapshotV1(
                (claimed,), 1, 8, (claimed.operation_id,))

    @pytest.mark.asyncio
    async def test_duplicate_and_digest_conflict_preserve_original_row_and_capacity(self, tmp_path):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            await check_idempotency(store, models, clock)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("terminal", ["succeeded", "failed_terminal", "cancelled"])
    async def test_retry_wait_retains_capacity_and_terminal_releases_exactly_once(self, tmp_path, test_agent, terminal):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            await check_retry_capacity_and_terminal_release(store, models, clock, test_agent, terminal)

    @pytest.mark.asyncio
    async def test_expired_lease_reclaims_with_higher_fence_and_rejects_stale_writers(self, tmp_path, test_agent):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            await check_fences_and_version(store, models, clock, test_agent)

    @pytest.mark.asyncio
    async def test_claim_is_partitioned_ordered_and_exclusive(self, tmp_path, test_agent):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            # Sequential order is distinct from race exclusivity.
            await ready(store, models, "oldest")
            clock.advance(1)
            await ready(store, models, "newer", now=wall_time(clock))
            partition = models.BackgroundPartitionV1("project-a", "durable")
            assert (await store.claim(partition, test_agent, 100)).operation_id == "oldest"
            assert (await store.claim(partition, test_agent, 100)).operation_id == "newer"
        async with sqlite_store(tmp_path / "race") as (store, _, models, clock):
            await check_claim_order_and_exclusivity(store, models, clock, test_agent)

    @pytest.mark.asyncio
    async def test_busy_and_shutdown_have_no_hidden_accepted_row(self, tmp_path):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            first = await store.admit(intent(models), limits(models, max_pending_items=1))
            for name, cap, status in (("busy", limits(models, max_pending_items=1), "busy"),
                                      ("shutdown", limits(models, accepting=False), "shutting_down")):
                result = await store.admit(intent(models, name), cap)
                assert result.status == status and result.receipt is None
                assert result.retry_after_ms == (cap.retry_after_ms if status == "busy" else None)
                assert await store.get(name) is None
            await snapshot(store, models, clock, [first.receipt])

    @pytest.mark.asyncio
    async def test_reopen_reconstructs_all_nonterminal_states_without_mutation(self, tmp_path, test_agent):
        from scribe_mcp.storage.sqlite import SQLiteStorage
        async with sqlite_store(tmp_path) as (store, backend, models, clock):
            accepted = (await store.admit(intent(models, "accepted"), limits(models))).receipt
            pending = await ready(store, models, "ready", project="project-ready")
            await ready(store, models, "leased", project="project-leased")
            leased = await store.claim(models.BackgroundPartitionV1("project-leased", "durable"), test_agent, 100)
            await ready(store, models, "retry", project="project-retry")
            claimed = await store.claim(models.BackgroundPartitionV1("project-retry", "durable"), test_agent, 100)
            retry = await store.transition(claimed.operation_id, claimed.state_version, claimed.fencing_token,
                models.BackgroundTransitionOutcomeV1("retry_wait", next_attempt_at=wall_time(clock) + timedelta(seconds=1)))
            clock.advance(100)
            before = await snapshot(store, models, clock, [accepted, pending, leased, retry])
            await backend.close()
            reopened = SQLiteStorage(tmp_path / "background.sqlite3")
            try:
                await reopened.setup()
                _, store_class = api()
                fresh = store_class(reopened, clock=lambda: wall_time(clock))
                assert await fresh.recover(wall_time(clock)) == before
                for row in before.receipts:
                    assert await fresh.get(row.operation_id) == row
                assert await fresh.recover(wall_time(clock)) == before
            finally:
                await reopened.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("source", ["accepted", "ready", "leased", "retry_wait", "succeeded", "failed_terminal", "cancelled"])
    @pytest.mark.parametrize("target", ["ready", "retry_wait", "succeeded", "failed_terminal", "cancelled"])
    async def test_legal_transition_matrix_is_enforced_without_failed_cas_mutation(self, tmp_path, test_agent, source, target):
        async with sqlite_store(tmp_path) as (store, _, models, clock):
            row = (await store.admit(intent(models), limits(models))).receipt
            if source != "accepted":
                row = await store.transition(row.operation_id, row.state_version, row.fencing_token, models.BackgroundTransitionOutcomeV1("ready"))
            if source in {"leased", "retry_wait", "succeeded", "failed_terminal"}:
                row = await store.claim(models.BackgroundPartitionV1("project-a", "durable"), test_agent, 100)
            if source in {"retry_wait", "succeeded", "failed_terminal", "cancelled"}:
                kwargs = {"next_attempt_at": wall_time(clock) + timedelta(seconds=1)} if source == "retry_wait" else (
                    {"result_ref": "artifact:result"} if source == "succeeded" else ({"error_code": "PERMANENT"} if source == "failed_terminal" else {}))
                row = await store.transition(row.operation_id, row.state_version, row.fencing_token, models.BackgroundTransitionOutcomeV1(source, **kwargs))
            kwargs = {"next_attempt_at": wall_time(clock) + timedelta(seconds=1)} if target == "retry_wait" else (
                {"result_ref": "artifact:result"} if target == "succeeded" else ({"error_code": "PERMANENT"} if target == "failed_terminal" else {}))
            outcome = models.BackgroundTransitionOutcomeV1(target, **kwargs)
            legal = {"accepted": {"ready", "cancelled"}, "ready": {"cancelled"},
                     "leased": {"retry_wait", "succeeded", "failed_terminal", "cancelled"}, "retry_wait": {"cancelled"}}
            if target in legal.get(source, set()):
                changed = await store.transition(row.operation_id, row.state_version, row.fencing_token, outcome)
                assert changed.state == target and changed.state_version == row.state_version + 1
                assert changed.fencing_token == row.fencing_token and changed.attempt_count == row.attempt_count
            else:
                with pytest.raises((ValueError, models.BackgroundStateVersionConflictError)):
                    await store.transition(row.operation_id, row.state_version, row.fencing_token, outcome)
                assert await store.get(row.operation_id) == row
