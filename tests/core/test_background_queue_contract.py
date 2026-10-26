"""Frozen C-08/C-09 behavior, observed against real disposable SQLite storage.

Stage guards are deliberately inside tests: an absent future source boundary is
an assertion failure, never a collection failure or a simulated implementation.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import inspect
import json
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from statistics import quantiles

import pytest

from core.test_swarm_binding_reliability import canonical_sqlite_lifecycle, payload, world
from fixtures.swarm import (
    CausalGate, ExpectedEffect, ManualClock, ObservedEffect, SwarmRunMetadata,
    reconcile_exact_effects,
)

pytestmark = [pytest.mark.core, pytest.mark.regression,
              pytest.mark.usefixtures("test_agent")]
SEED = 20260927
SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
EPOCH = datetime(2026, 9, 27, tzinfo=timezone.utc)

# D3 is the registered pair vocabulary, not an implementation-derived oracle.
EVENT_PAIRS = {
    "admission": ("accepted", "duplicate", "digest_conflict", "busy", "shutting_down"),
    "retry_after": ("busy",),
    "queue_items": ("accepted", "ready", "leased", "retry_wait"),
    "queue_bytes": ("accepted", "ready", "leased", "retry_wait"),
    "high_water": ("items", "bytes", "concurrency"),
    "oldest_eligible": ("observed",), "queue_wait": ("claimed",),
    "run_time": ("succeeded", "retry_wait", "failed_terminal", "cancelled", "stale_fence"),
    "worker_claim": ("claimed",), "attempt": ("started",), "retry": ("scheduled",),
    "dead_letter": ("failed_terminal",),
    "cancellation": ("requested", "cancelled", "commit_started"), "lease": ("expired",),
    "fence": ("stale_fence",), "active_workers": ("observed",),
    "project_service": ("started",), "starvation": ("window_ge_5s",),
    "shutdown": ("admitted", "drained", "checkpointed", "cancelled_retryable",
                 "remaining_recoverable", "workers_stopped", "deadline_exceeded"),
    "recovery": ("recovered",),
    "lifecycle": ("starting", "running", "draining", "stopped", "degraded"),
}


def event_numbers(kind):
    return (None if kind == "lifecycle" else 3 if kind in {
        "admission", "oldest_eligible", "queue_wait", "run_time"} else None,
        None if kind in {"lifecycle", "oldest_eligible"} else 1)


def assert_queue_events(events):
    for event in events:
        assert event.kind in EVENT_PAIRS
        assert event.outcome in EVENT_PAIRS[event.kind]
        assert event.observed_at.tzinfo is not None
        assert event.observed_at.utcoffset() == timedelta(0)
        for value in (event.value, event.duration_ms):
            assert value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)
        if event.kind == "lifecycle":
            assert event.value is event.duration_ms is event.lane is event.canonical_project_key_hash is None


def required(module, *names):
    assert importlib.util.find_spec(module) is not None, f"Frozen contract absent: {module}"
    loaded = importlib.import_module(module)
    missing = [name for name in names if not hasattr(loaded, name)]
    assert not missing, f"Frozen contract absent: {module}: {', '.join(missing)}"
    assert loaded.__file__ is not None and Path(loaded.__file__).resolve().is_relative_to(SOURCE_ROOT), (
        f"Wrong artifact under test: {loaded.__file__}")
    return loaded


def scheduler_contract():
    module = required("scribe_mcp.background.scheduler", "BackgroundSchedulerConfigV1",
                      "BackgroundSchedulerMetricsV1", "BackgroundSchedulerV1")
    assert "project_weights" in inspect.signature(module.BackgroundSchedulerConfigV1).parameters, (
        "Frozen D1 contract absent: BackgroundSchedulerConfigV1.project_weights")
    return module


def worker_contract():
    return required("scribe_mcp.background.worker", "BackgroundWorkerV1",
                    "BackgroundCancellationProbeV1", "BackgroundExecutionOutcomeV1",
                    "BackgroundWorkerStepV1", "SeededRetryPolicyV1")


def service_contract():
    return required("scribe_mcp.background.service", "BackgroundJobServiceV1",
                    "BackgroundServiceConfigV1", "BackgroundServiceHealthV1",
                    "BackgroundShutdownReceiptV1", "BackgroundQueueEventV1",
                    "BackgroundDigestConflictError", "BackgroundQueueBusyError",
                    "BackgroundServiceShuttingDownError", "BackgroundOperationNotFoundError")


def lifecycle_contract():
    return required("scribe_mcp.server", "get_background_job_service",
                    "get_background_job_service_health", "_startup", "_shutdown",
                    "schedule_background_task", "drain_background_tasks")


def now(clock):
    return EPOCH + timedelta(seconds=clock.now())


async def canonical_projects(backend, root, labels):
    """Persist real project identities; duplicate display names are deliberate."""
    result = {}
    for label in labels:
        repo = root / label
        repo.mkdir(parents=True, exist_ok=True)
        record = await backend.upsert_project(name="shared-label", repo_root=str(repo),
            progress_log_path=str(repo / "PROGRESS_LOG.md"))
        result[label] = record.project_key
    assert len(set(result.values())) == len(result)
    return result


def limits(*, items=128, size=1048576, project_items=64, project_size=524288):
    models = required("scribe_mcp.background.models", "BackgroundQueueLimitsV1")
    return models.BackgroundQueueLimitsV1(items, size, project_items, project_size, 25)


def intent(clock, project, ordinal, *, lane="heavy", size=64):
    models = required("scribe_mcp.background.models", "BackgroundOperationIntentV1")
    operation = f"{project}:{lane}:{ordinal}"
    return models.BackgroundOperationIntentV1(operation, project, lane, operation,
        hashlib.sha256(operation.encode()).hexdigest(), size, "durable", now(clock))


async def ready(store, row, bound):
    model = required("scribe_mcp.background.models", "BackgroundTransitionOutcomeV1")
    admitted = await store.admit(row, bound)
    assert admitted.status == "accepted"
    receipt = admitted.receipt
    return await store.transition(receipt.operation_id, receipt.state_version,
        receipt.fencing_token, model.BackgroundTransitionOutcomeV1("ready"))


async def finish(store, receipt, state="succeeded"):
    model = required("scribe_mcp.background.models", "BackgroundTransitionOutcomeV1")
    outcome = model.BackgroundTransitionOutcomeV1(state,
        result_ref=f"effect:{receipt.operation_id}" if state == "succeeded" else None)
    return await store.transition(receipt.operation_id, receipt.state_version,
                                  receipt.fencing_token, outcome)


@asynccontextmanager
async def queue_world(tmp_path, *, stage="scheduler", bound=None, concurrency=4):
    scheduler = scheduler_contract()
    if stage in {"worker", "service"}:
        worker_contract()
    if stage == "service":
        service_contract()
    clock = ManualClock()
    async with canonical_sqlite_lifecycle(tmp_path / "queue.db") as backend:
        store_type = required("scribe_mcp.background.store", "BackgroundReceiptStoreV1")
        store = store_type.BackgroundReceiptStoreV1(backend, clock=lambda: now(clock))
        config = scheduler.BackgroundSchedulerConfigV1(concurrency, 1, 1, 1)
        scheduling = scheduler.BackgroundSchedulerV1(store, config, clock=lambda: now(clock))
        yield clock, backend, store, scheduling, bound or limits()


def retry_policy():
    return worker_contract().SeededRetryPolicyV1(3, 100, 400, 17, SEED)


def make_worker(name, scheduling, store, handler, clock):
    return worker_contract().BackgroundWorkerV1(name, scheduling, store, handler,
        retry_policy(), lease_ms=1000, clock=lambda: now(clock))


def make_service(store, handler, clock, events, *, bound=None, workers=2):
    service = service_contract()
    config = service.BackgroundServiceConfigV1(bound or limits(),
        scheduler_contract().BackgroundSchedulerConfigV1(4, 1, 1, 1), workers,
        1000, retry_policy(), 100)
    return service.BackgroundJobServiceV1(store, handler, config,
        clock=lambda: now(clock), emit=events.append)


def reconcile_receipt_effects(receipts, effects, *, capacity=(), fairness=()):
    """Feed actual sink writes and durable receipt identities into the one C-14 oracle."""
    expected, observed = [], []
    for row in receipts:
        wanted = ExpectedEffect("queue", row.operation_id, "caller", "app", "session",
            row.canonical_project_key, None, row.canonical_project_key,
            row.payload_digest, "background", "OK")
        expected.append(wanted)
    by_id = {row.operation_id: row for row in expected}
    for operation, project, digest in effects:
        row = by_id[operation]
        observed.append(ObservedEffect(**(asdict(row) | {
            "target_project_key": project, "mutation_fingerprint": digest}),
            default_after=row.default_project_key))
    metadata = SwarmRunMetadata("source-tree", SEED, {}, {"caller": 1},
        background_queue={"capacity_samples": tuple(capacity),
                          "fairness_samples": tuple(fairness)})
    result = reconcile_exact_effects(expected, observed, metadata=metadata)
    assert result.verdict == "PASS", result.as_json_dict()
    return result


async def task_result(task):
    return await asyncio.wait_for(task, 3)


async def clean_tasks(tasks):
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


class EmittedEvents(list):
    """Wait for real sink observations without sleeps or predicted events."""
    def __init__(self):
        super().__init__()
        self.changed = asyncio.Event()

    def append(self, event):
        super().append(event)
        self.changed.set()

    def select(self, kind, outcome):
        return [event for event in self if (event.kind, event.outcome) == (kind, outcome)]

    async def wait(self, kind, outcome, count=1):
        async def observed():
            while len(self.select(kind, outcome)) < count:
                self.changed.clear()
                if len(self.select(kind, outcome)) < count:
                    await self.changed.wait()
            return self.select(kind, outcome)
        return await asyncio.wait_for(observed(), 3)


def assert_emission(events, kind, outcome, values, *, durations=None):
    actual = [event for event in events if (event.kind, event.outcome) == (kind, outcome)]
    assert [event.value for event in actual] == values, (kind, outcome, actual)
    assert [event.duration_ms for event in actual] == (durations if durations is not None else [None] * len(values))
    assert_queue_events(actual)
    return actual


class TestSBRScheduler:
    def test_required_contract_is_present(self):
        scheduler = scheduler_contract()
        assert {"store", "config", "clock"} <= set(inspect.signature(
            scheduler.BackgroundSchedulerV1).parameters)
        assert all(callable(getattr(scheduler.BackgroundSchedulerV1, name, None))
                   for name in ("recover", "claim_next", "metrics_snapshot"))

    @pytest.mark.asyncio
    async def test_equal_project_progress_with_control_reserve(self, tmp_path):
        async with queue_world(tmp_path) as (clock, backend, store, scheduling, bound):
            projects = await canonical_projects(backend, tmp_path / "identities", ("A", "B", "C", "control", "extra-0", "extra-1", "extra-2"))
            for project in (projects["A"], projects["B"], projects["C"]):
                for ordinal in range(12):
                    await ready(store, intent(clock, project, ordinal), bound)
            starts = Counter({projects[label]: 0 for label in ("A", "B", "C")})
            fairness, capacity = [], []
            eligible_since = {project: now(clock) for project in starts}
            measured_waits = []
            for round_number in range(12):
                for turn in range(3):
                    row = await scheduling.claim_next(f"worker-{turn}", lease_ms=1000)
                    assert row is not None
                    age = int((now(clock) - eligible_since[row.canonical_project_key]).total_seconds() * 1000)
                    measured_waits.append(age)
                    assert age < 5000
                    eligible_since[row.canonical_project_key] = now(clock)
                    starts[row.canonical_project_key] += 1
                    assert max(starts.values()) - min(starts.values()) <= 1
                    snapshot = await store.recover(now(clock))
                    leased = [r for r in snapshot.receipts if r.state == "leased"]
                    sample = {"items": snapshot.pending_items, "items_limit": 128,
                        "bytes": snapshot.pending_bytes, "bytes_limit": 1048576,
                        "global": len(leased), "global_limit": 4, "project": max(Counter(
                            r.canonical_project_key for r in leased).values()), "project_limit": 1,
                        "heavy": sum(r.lane == "heavy" for r in leased), "heavy_limit": 2}
                    capacity.append(sample)
                    await finish(store, row)
                    clock.advance(1000)
                assert set(starts.values()) == {round_number + 1}
                fairness.append(dict(lead_units=max(starts.values()) - min(starts.values()),
                    eligible_peer_share=max(starts.values()) / sum(starts.values()),
                    starvation_ms=max(measured_waits[-3:])))
            assert starts == {projects[label]: 12 for label in ("A", "B", "C")}
            control = await ready(store, intent(clock, projects["control"], 0, lane="control"), bound)
            heavy = [await ready(store, intent(clock, projects[f"extra-{i}"], 0), bound) for i in range(3)]
            claims = [await scheduling.claim_next(f"reserve-{i}", lease_ms=1000) for i in range(4)]
            claims = [r for r in claims if r is not None]
            assert control.operation_id in {r.operation_id for r in claims}
            assert next(i for i, row in enumerate(claims) if row.operation_id == control.operation_id) < 3
            assert sum(r.lane == "heavy" for r in claims) <= 2
            assert len({r.canonical_project_key for r in claims}) == len(claims)
            assert len(heavy) == 3
            reconcile_receipt_effects([], [], capacity=capacity, fairness=fairness)
            assert scheduling.metrics_snapshot().starvation_windows_ge_5s == 0

    @pytest.mark.asyncio
    async def test_project_weight_2_1_1_is_within_one_quantum(self, tmp_path):
        async with queue_world(tmp_path, concurrency=8) as (clock, backend, store, scheduling, bound):
            module = scheduler_contract()
            projects = await canonical_projects(backend, tmp_path / "identities", ("A", "B", "C"))
            config = module.BackgroundSchedulerConfigV1(4, 1, 1, 1,
                control_quantum=1, durable_quantum=1, heavy_quantum=1,
                project_weights=((projects["A"], 2), (projects["B"], 1), (projects["C"], 1)))
            scheduling = module.BackgroundSchedulerV1(store, config, clock=lambda: now(clock))
            admitted, effects, counts = [], [], Counter()
            weights = dict(config.project_weights)
            eligible_since = {project: now(clock) for project in weights}
            for project in weights:
                for n in range(12):
                    admitted.append(await ready(store, intent(clock, project, n, lane="heavy"), bound))
            for turn in range(12):
                row = await scheduling.claim_next("weighted", lease_ms=1000)
                assert row is not None
                assert row.lane == "heavy"
                measured_age = int((now(clock) - eligible_since[row.canonical_project_key]).total_seconds() * 1000)
                assert measured_age < 5000
                eligible_since[row.canonical_project_key] = now(clock)
                counts[row.canonical_project_key] += 1
                done = await finish(store, row)
                effects.append((done.operation_id, done.canonical_project_key, done.payload_digest))
                clock.advance(750)
                for project, weight in weights.items():
                    assert abs(counts[project] - (turn + 1) * weight / 4) <= weight
                if (turn + 1) % 4 == 0:
                    rounds = (turn + 1) // 4
                    assert counts == {projects["A"]: 2 * rounds,
                                      projects["B"]: rounds, projects["C"]: rounds}
                    assert max(counts.values()) / sum(counts.values()) == 0.5
            for _ in range(24):
                row = await scheduling.claim_next("weighted", lease_ms=1000)
                assert row is not None
                done = await finish(store, row)
                effects.append((done.operation_id, done.canonical_project_key, done.payload_digest))
            assert await scheduling.claim_next("empty", lease_ms=1000) is None
            assert (await store.recover(now(clock))).pending_items == 0
            assert len(effects) == len({row[0] for row in effects}) == 36
            reconcile_receipt_effects(admitted, effects)
            assert scheduling.metrics_snapshot().starvation_windows_ge_5s == 0

    @pytest.mark.asyncio
    async def test_configured_idle_project_has_no_turn_capacity_or_banked_credit(self, tmp_path):
        async with queue_world(tmp_path) as (clock, backend, store, scheduling, bound):
            module = scheduler_contract()
            keys = await canonical_projects(backend, tmp_path / "identities", ("idle", "B", "C"))
            scheduling = module.BackgroundSchedulerV1(store,
                module.BackgroundSchedulerConfigV1(4, 1, 1, 1,
                    project_weights=((keys["idle"], 2), (keys["B"], 1), (keys["C"], 1))),
                clock=lambda: now(clock))
            for label in ("B", "C"):
                for n in range(40):
                    await ready(store, intent(clock, keys[label], n), bound)
            counts = Counter()
            for _ in range(48):
                row = await scheduling.claim_next("idle-observer", lease_ms=1000)
                assert row is not None and row.canonical_project_key != keys["idle"]
                snapshot = await store.recover(now(clock))
                assert [value.operation_id for value in snapshot.receipts if value.state == "leased"] == [row.operation_id]
                counts[row.canonical_project_key] += 1
                await finish(store, row)
                clock.advance(100)
                assert abs(counts[keys["B"]] - counts[keys["C"]]) <= 1
                assert keys["idle"] not in dict(scheduling.metrics_snapshot().project_service_starts)
            assert (await store.recover(now(clock))).pending_items == 32
            for n in range(12):
                await ready(store, intent(clock, keys["idle"], n), bound)
            fresh = Counter()
            for turn in range(12):
                row = await scheduling.claim_next("newly-eligible", lease_ms=1000)
                assert row is not None
                fresh[row.canonical_project_key] += 1
                await finish(store, row)
                # Every prefix stays within one configured quantum; accumulated
                # idle credit cannot purchase an arbitrarily long initial burst.
                for label, weight in (("idle", 2), ("B", 1), ("C", 1)):
                    assert abs(fresh[keys[label]] - (turn + 1) * weight / 4) <= weight
                assert (await store.recover(now(clock))).pending_items == 44 - turn - 1

    @pytest.mark.parametrize("weights", [(("A", 0),), (("A", -1),), (("A", True),),
        (("", 1),), ((" ", 1),), (("A", 1), ("A", 2))])
    def test_project_weight_config_rejects_invalid_keys_and_weights(self, weights):
        module = scheduler_contract()
        with pytest.raises(ValueError):
            module.BackgroundSchedulerConfigV1(4, 1, 1, 1, project_weights=weights)

    def test_project_weight_config_normalizes_canonical_pairs(self):
        module = scheduler_contract()
        config = module.BackgroundSchedulerConfigV1(4, 1, 1, 1,
            project_weights=(("C", 1), ("A", 2), ("B", 1)))
        assert config.project_weights == (("A", 2), ("B", 1), ("C", 1))

    @pytest.mark.asyncio
    async def test_lane_quantum_is_independent_of_project_weights(self, tmp_path):
        async with queue_world(tmp_path) as (clock, backend, store, scheduling, bound):
            module = scheduler_contract()
            keys = await canonical_projects(backend, tmp_path / "identities", ("control", "durable", "heavy"))
            scheduling = module.BackgroundSchedulerV1(store,
                module.BackgroundSchedulerConfigV1(4, 1, 1, 1, control_quantum=2,
                    durable_quantum=1, heavy_quantum=1, project_weights=()), clock=lambda: now(clock))
            for lane, key in keys.items():
                for n in range(24):
                    await ready(store, intent(clock, key, n, lane=lane), bound)
            counts = Counter()
            for turn in range(16):
                row = await scheduling.claim_next("lane-worker", lease_ms=1000)
                assert row is not None
                counts[row.lane] += 1
                await finish(store, row)
                if (turn + 1) % 4 == 0:
                    rounds = (turn + 1) // 4
                    assert counts == {"control": 2 * rounds, "durable": rounds, "heavy": rounds}

    @pytest.mark.asyncio
    async def test_project_cap_holds_with_multiple_same_project_candidates(self, tmp_path):
        async with queue_world(tmp_path) as (clock, backend, store, scheduling, bound):
            keys = await canonical_projects(backend, tmp_path / "identities", ("A", "B"))
            for n in range(3):
                await ready(store, intent(clock, keys["A"], n), bound)
            await ready(store, intent(clock, keys["B"], 0, lane="control"), bound)
            claimed = [await scheduling.claim_next(f"cap-worker-{n}", lease_ms=1000) for n in range(4)]
            claimed = [row for row in claimed if row is not None]
            assert Counter(row.canonical_project_key for row in claimed) == {keys["A"]: 1, keys["B"]: 1}
            assert (await store.recover(now(clock))).pending_items == 4
            a = next(row for row in claimed if row.canonical_project_key == keys["A"])
            await finish(store, a)
            assert (await scheduling.claim_next("released-slot", lease_ms=1000)).canonical_project_key == keys["A"]

    @pytest.mark.asyncio
    async def test_canonical_choices_do_not_depend_on_submission_order(self, tmp_path):
        schedules = []
        async with queue_world(tmp_path) as (clock, backend, store, scheduling, bound):
            keys = await canonical_projects(backend, tmp_path / "identities", ("A", "B", "C"))
            module = scheduler_contract()
            for run, projects in enumerate((("A", "B", "C"), ("C", "B", "A"))):
                scheduling = module.BackgroundSchedulerV1(store,
                    module.BackgroundSchedulerConfigV1(4, 1, 1, 1), clock=lambda: now(clock))
                for project in (keys[label] for label in projects):
                    for n in range(3):
                        await ready(store, intent(clock, project, run * 3 + n), bound)
                sequence = []
                for _ in range(9):
                    row = await scheduling.claim_next("worker", lease_ms=1000)
                    assert row is not None
                    sequence.append(row.canonical_project_key)
                    await finish(store, row)
                assert Counter(sequence) == {keys[label]: 3 for label in ("A", "B", "C")}
                schedules.append(sequence)
        assert schedules[0] == schedules[1]

    @pytest.mark.asyncio
    async def test_retry_wait_and_project_cap_do_not_consume_peer_turn(self, tmp_path):
        async with queue_world(tmp_path) as (clock, backend, store, scheduling, bound):
            models = required("scribe_mcp.background.models", "BackgroundTransitionOutcomeV1")
            await ready(store, intent(clock, "A", 0), bound)
            a = await scheduling.claim_next("held", lease_ms=1000)
            await store.transition(a.operation_id, a.state_version, a.fencing_token,
                models.BackgroundTransitionOutcomeV1("retry_wait", next_attempt_at=now(clock) + timedelta(seconds=2)))
            await ready(store, intent(clock, "B", 0), bound)
            await ready(store, intent(clock, "C", 0), bound)
            peers = []
            for _ in range(2):
                row = await scheduling.claim_next("peer", lease_ms=1000)
                peers.append(row.canonical_project_key)
                await finish(store, row)
            assert set(peers) == {"B", "C"}
            assert await scheduling.claim_next("not-due", lease_ms=1000) is None
            clock.advance(2000)
            assert (await scheduling.claim_next("due", lease_ms=1000)).operation_id == a.operation_id


class TestSBRWorker:
    def test_required_contract_is_present(self):
        module = worker_contract()
        assert {"worker_id", "scheduler", "store", "handler", "retry_policy", "lease_ms", "clock"} <= set(
            inspect.signature(module.BackgroundWorkerV1).parameters)

    @pytest.mark.asyncio
    async def test_seeded_retry_due_exhaustion_and_permanent_failure(self, tmp_path):
        worker_contract()
        async with queue_world(tmp_path, stage="worker") as (clock, backend, store, scheduling, bound):
            calls = []
            async def transient(row, probe):
                calls.append(row.attempt_count)
                return worker_contract().BackgroundExecutionOutcomeV1("transient_failure", error_code="TEMPORARY")
            row = await ready(store, intent(clock, "A", 0), bound)
            worker = make_worker("worker", scheduling, store, transient, clock)
            for attempt in range(1, 4):
                step = await worker.run_once()
                current = await store.get(row.operation_id)
                assert current.attempt_count == attempt
                if attempt < 3:
                    assert step.outcome == current.state == "retry_wait"
                    due = retry_policy().next_attempt_at(current, now=now(clock))
                    assert retry_policy().next_attempt_at(current, now=now(clock)) == due
                    assert current.next_attempt_at == due
                    assert (await worker.run_once()).outcome == "idle"
                    delay = int((current.next_attempt_at - now(clock)).total_seconds() * 1000)
                    assert 100 <= delay <= 417
                    clock.advance(delay + 1)
                else:
                    assert step.outcome == current.state == "failed_terminal"
            assert calls == [1, 2, 3]
            assert (await store.recover(now(clock))).pending_items == 0
            async def permanent(row, probe):
                return worker_contract().BackgroundExecutionOutcomeV1("permanent_failure", error_code="INVALID")
            second = await ready(store, intent(clock, "B", 0), bound)
            step = await make_worker("permanent", scheduling, store, permanent, clock).run_once()
            assert step.outcome == "failed_terminal"
            assert (await store.get(second.operation_id)).attempt_count == 1

    @pytest.mark.parametrize("commit_started", [False, True])
    @pytest.mark.asyncio
    async def test_leased_cancellation_respects_commit_barrier(self, tmp_path, commit_started):
        worker_contract()
        async with queue_world(tmp_path, stage="worker") as (clock, backend, store, scheduling, bound):
            gate, effects = CausalGate(), []
            async def handler(row, probe):
                if commit_started:
                    probe.mark_commit_started()
                await gate.hold()
                if not probe.is_cancel_requested() or commit_started:
                    effects.append((row.operation_id, row.canonical_project_key, row.payload_digest))
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            admitted = await ready(store, intent(clock, "A", 0), bound)
            worker = make_worker("worker", scheduling, store, handler, clock)
            task = asyncio.create_task(worker.run_once())
            try:
                await asyncio.wait_for(gate.entered.wait(), 3)
                worker.request_cancel(admitted.operation_id)
                gate.release.set()
                step = await task_result(task)
                receipt = await store.get(admitted.operation_id)
                assert step.outcome == receipt.state == ("succeeded" if commit_started else "cancelled")
                assert len(effects) == int(commit_started)
                assert (await store.recover(now(clock))).pending_items == 0
                if commit_started:
                    reconcile_receipt_effects([receipt], effects)
            finally:
                gate.release.set()
                await clean_tasks([task])

    @pytest.mark.asyncio
    async def test_worker_death_reclaim_rejects_late_completion(self, tmp_path):
        worker_contract()
        async with queue_world(tmp_path, stage="worker") as (clock, backend, store, scheduling, bound):
            gate, effects = CausalGate(), []
            async def old_handler(row, probe):
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="old")
            admitted = await ready(store, intent(clock, "A", 0), bound)
            task = asyncio.create_task(make_worker("old", scheduling, store, old_handler, clock).run_once())
            try:
                await asyncio.wait_for(gate.entered.wait(), 3)
                old = await store.get(admitted.operation_id)
                clock.advance(1001)
                async def fresh_handler(row, probe):
                    probe.mark_commit_started()
                    effects.append((row.operation_id, row.canonical_project_key, row.payload_digest))
                    return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="fresh")
                step = await make_worker("fresh", scheduling, store, fresh_handler, clock).run_once()
                assert step.outcome == "succeeded"
                completed = await store.get(admitted.operation_id)
                assert completed.fencing_token > old.fencing_token
                gate.release.set()
                assert (await task_result(task)).outcome == "stale_fence"
                assert await store.get(admitted.operation_id) == completed
                reconcile_receipt_effects([completed], effects)
            finally:
                gate.release.set()
                await clean_tasks([task])

    @pytest.mark.asyncio
    async def test_equal_capacity_worker_claims_differ_by_at_most_one(self, tmp_path):
        worker_contract()
        async with queue_world(tmp_path, stage="worker") as (clock, backend, store, scheduling, bound):
            effects, counts = [], Counter()
            async def handler(row, probe):
                probe.mark_commit_started()
                effects.append((row.operation_id, row.canonical_project_key, row.payload_digest))
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            for n in range(32):
                await ready(store, intent(clock, f"project-{n % 4}", n), bound)
            workers = [make_worker(f"worker-{i}", scheduling, store, handler, clock) for i in range(2)]
            async def consume(worker):
                for _ in range(32):
                    step = await worker.run_once()
                    if step.outcome == "idle":
                        return
                    assert step.outcome == "succeeded"
                    counts[step.worker_id] += 1
            await asyncio.wait_for(asyncio.gather(*(consume(worker) for worker in workers)), 3)
            assert sum(counts.values()) == 32
            assert len(counts) == 2
            assert max(counts.values()) - min(counts.values()) <= 1
            assert len(effects) == len({row[0] for row in effects}) == 32
            assert dict(scheduling.metrics_snapshot().worker_claims) == counts

    @pytest.mark.asyncio
    @pytest.mark.parametrize("malformed", [None, {"kind": "succeeded"}])
    async def test_malformed_handler_outcome_is_terminal_without_retry(self, tmp_path, malformed):
        worker_contract()
        async with queue_world(tmp_path, stage="worker") as (clock, backend, store, scheduling, bound):
            calls = []
            async def handler(row, probe):
                calls.append(row.operation_id)
                return malformed
            row = await ready(store, intent(clock, "A", 0), bound)
            step = await make_worker("malformed", scheduling, store, handler, clock).run_once()
            current = await store.get(row.operation_id)
            assert step.outcome == current.state == "failed_terminal"
            assert current.attempt_count == 1 and current.next_attempt_at is None
            assert calls == [row.operation_id]
            assert (await store.recover(now(clock))).pending_items == 0


class TestSBRService:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("handler_outcome,terminal", [("succeeded", "succeeded"),
        ("transient_failure", "retry_wait"), ("permanent_failure", "failed_terminal")])
    async def test_emitted_wait_runtime_retry_deadletter_and_project_retirement(
        self, tmp_path, monkeypatch, handler_outcome, terminal
    ):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            keys = await canonical_projects(backend, tmp_path / "identities", ("measured",))
            project = keys["measured"]
            claim_gate, run_gate, events = CausalGate(), CausalGate(), EmittedEvents()
            original_claim = store.claim
            async def held_claim(*args, **kwargs):
                await claim_gate.hold()
                return await original_claim(*args, **kwargs)
            monkeypatch.setattr(store, "claim", held_claim)
            async def handler(row, probe):
                await run_gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1(handler_outcome,
                    result_ref="effect" if terminal == "succeeded" else None,
                    error_code=None if terminal == "succeeded" else "BOUNDED_FAILURE")
            service = make_service(store, handler, clock, events, workers=1)
            await service.start()
            try:
                row = await service.submit(intent(clock, project, 0))
                await asyncio.wait_for(claim_gate.entered.wait(), 3)
                clock.advance(23)
                claim_gate.release.set()
                await asyncio.wait_for(run_gate.entered.wait(), 3)
                clock.advance(7)
                run_gate.release.set()
                await events.wait("run_time", terminal)
                actual = await store.get(row.operation_id)
                assert actual.state == terminal and actual.attempt_count == 1
                admission = assert_emission(events, "admission", "accepted", [1], durations=[0])[0]
                assert admission.canonical_project_key_hash and admission.canonical_project_key_hash != project
                assert_emission(events, "queue_wait", "claimed", [1], durations=[23])
                assert any(event.duration_ms == 23 for event in events
                           if event.kind == "oldest_eligible" and event.outcome == "observed")
                assert_emission(events, "run_time", terminal, [1], durations=[7])
                assert_emission(events, "worker_claim", "claimed", [1], durations=[None])
                assert_emission(events, "attempt", "started", [1], durations=[None])
                assert_emission(events, "project_service", "started", [1], durations=[None])
                assert_emission(events, "retry", "scheduled", [1] if terminal == "retry_wait" else [])
                assert_emission(events, "dead_letter", "failed_terminal", [1] if terminal == "failed_terminal" else [])
                scoped = [event for event in events if event.kind in
                    {"queue_wait", "run_time", "worker_claim", "attempt", "project_service", "retry", "dead_letter"}]
                assert all(event.lane == "heavy" and event.canonical_project_key_hash ==
                           admission.canonical_project_key_hash for event in scoped)
                assert all(event.observed_at in {EPOCH, EPOCH + timedelta(milliseconds=23),
                    EPOCH + timedelta(milliseconds=30)} for event in events)
                health = await service.health_snapshot()
                active = [event.value for event in events if event.kind == "active_workers" and event.outcome == "observed"]
                assert active and active[-1] == health.workers_active == 1
                if terminal == "retry_wait":
                    assert (await store.recover(now(clock))).pending_items == 1
                    assert sum(dict(health.metrics.project_service_starts).values()) == 1
                else:
                    assert (await store.recover(now(clock))).pending_items == 0
                    assert dict(health.metrics.project_service_starts) == {}
                assert_queue_events(events)
            finally:
                claim_gate.release.set()
                run_gate.release.set()
                await service.stop()

    @pytest.mark.asyncio
    async def test_real_five_second_eligibility_crossing_emits_once_and_counter_is_sensitive(self, tmp_path, monkeypatch):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            key = (await canonical_projects(backend, tmp_path / "identities", ("eligible",)))["eligible"]
            claim_gate, handler_gate, events = CausalGate(), CausalGate(), EmittedEvents()
            original_claim = store.claim
            async def held(*args, **kwargs):
                await claim_gate.hold()
                return await original_claim(*args, **kwargs)
            monkeypatch.setattr(store, "claim", held)
            async def handler(row, probe):
                await handler_gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events, workers=1)
            await service.start()
            try:
                row = await service.submit(intent(clock, key, 0))
                await asyncio.wait_for(claim_gate.entered.wait(), 3)
                eligible_at = now(clock)
                assert (await store.get(row.operation_id)).state in {"accepted", "ready"}
                clock.advance(4999)
                assert events.select("starvation", "window_ge_5s") == []
                clock.advance(1)
                measured_age = int((now(clock) - eligible_at).total_seconds() * 1000)
                assert measured_age == 5000
                claim_gate.release.set()
                await asyncio.wait_for(handler_gate.entered.wait(), 3)
                await events.wait("starvation", "window_ge_5s")
                assert_emission(events, "starvation", "window_ge_5s", [1], durations=[None])
                assert_emission(events, "queue_wait", "claimed", [1], durations=[measured_age])
                assert any(event.duration_ms == measured_age for event in events
                           if event.kind == "oldest_eligible" and event.outcome == "observed")
                assert (await service.health_snapshot()).metrics.starvation_windows_ge_5s == 1
                # The same immutable oracle must reject this genuinely observed
                # boundary; a permanently-zero producer counter cannot hide it.
                metadata = SwarmRunMetadata("source-tree", SEED, {}, {}, background_queue={
                    "fairness_samples": ({"lead_units": 0, "eligible_peer_share": 0.5,
                                          "starvation_ms": measured_age},)})
                assert reconcile_exact_effects([], [], metadata=metadata).verdict == "FAIL"
                await service.health_snapshot()
                assert len(events.select("starvation", "window_ge_5s")) == 1
            finally:
                claim_gate.release.set()
                handler_gate.release.set()
                await service.stop()

    @pytest.mark.asyncio
    async def test_emitted_expired_lease_and_stale_attempt_have_exact_deltas(self, tmp_path):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            events, old_gate, fresh_done, effects = EmittedEvents(), CausalGate(), asyncio.Event(), []
            async def handler(row, probe):
                if row.attempt_count == 1:
                    await old_gate.hold()
                else:
                    probe.mark_commit_started()
                    effects.append((row.operation_id, row.canonical_project_key, row.payload_digest))
                    fresh_done.set()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            key = (await canonical_projects(backend, tmp_path / "identities", ("fenced",)))["fenced"]
            service = make_service(store, handler, clock, events, workers=2)
            await service.start()
            try:
                row = await service.submit(intent(clock, key, 0))
                await asyncio.wait_for(old_gate.entered.wait(), 3)
                old = await store.get(row.operation_id)
                clock.advance(1001)
                await asyncio.wait_for(fresh_done.wait(), 3)
                await events.wait("run_time", "succeeded")
                final = await store.get(row.operation_id)
                assert final.state == "succeeded" and final.fencing_token > old.fencing_token
                old_gate.release.set()
                await events.wait("fence", "stale_fence")
                assert_emission(events, "lease", "expired", [1], durations=[None])
                assert_emission(events, "fence", "stale_fence", [1], durations=[None])
                assert_emission(events, "run_time", "stale_fence", [1], durations=[1001])
                assert_emission(events, "run_time", "succeeded", [1], durations=[0])
                assert_emission(events, "worker_claim", "claimed", [1, 1])
                assert_emission(events, "attempt", "started", [1, 1])
                assert await store.get(row.operation_id) == final
                reconcile_receipt_effects([final], effects)
                assert (await store.recover(now(clock))).pending_items == 0
            finally:
                old_gate.release.set()
                await service.stop()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("shutdown", [False, True])
    async def test_storage_admission_overlaps_cancel_or_shutdown(self, tmp_path, monkeypatch, shutdown):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            admission_gate, effect_gate, events, effects = CausalGate(), CausalGate(), EmittedEvents(), []
            original_admit = store.admit
            async def held_admit(*args, **kwargs):
                await admission_gate.hold()
                return await original_admit(*args, **kwargs)
            monkeypatch.setattr(store, "admit", held_admit)
            async def handler(row, probe):
                await effect_gate.hold()
                if not probe.is_cancel_requested():
                    probe.mark_commit_started()
                    effects.append((row.operation_id, row.canonical_project_key, row.payload_digest))
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events, workers=1)
            await service.start()
            row_intent = intent(clock, "admission-race", 0)
            submitting = asyncio.create_task(service.submit(row_intent))
            stopping = None
            try:
                await asyncio.wait_for(admission_gate.entered.wait(), 3)
                assert not submitting.done() and await store.get(row_intent.operation_id) is None
                if shutdown:
                    stopping = asyncio.create_task(service.stop(admission_close=True, drain_deadline_ms=100))
                    await events.wait("lifecycle", "draining")
                    assert not stopping.done()
                    with pytest.raises(service_contract().BackgroundServiceShuttingDownError):
                        await service.submit(intent(clock, "rejected-after-close", 1))
                else:
                    # Cancellation runs while the actual durable admission is
                    # suspended, rather than as an unrelated earlier call.
                    with pytest.raises(service_contract().BackgroundOperationNotFoundError):
                        await service.cancel(row_intent.operation_id, expected_state_version=1)
                clock.advance(17)
                admission_gate.release.set()
                admitted = await task_result(submitting)
                assert admitted.operation_id == row_intent.operation_id
                if shutdown:
                    effect_gate.release.set()
                    clock.advance(101)
                    stopped = await task_result(stopping)
                    assert_emission(events, "shutdown", "admitted", [1])
                    assert_emission(events, "shutdown", "deadline_exceeded", [int(stopped.deadline_exceeded)])
                    for field in ("drained", "checkpointed", "cancelled_retryable", "remaining_recoverable", "workers_stopped"):
                        assert_emission(events, "shutdown", field, [getattr(stopped, field)])
                    assert await store.get(admitted.operation_id) is not None
                    assert effects == []
                else:
                    current = await service.get_status(admitted.operation_id)
                    cancelled = await service.cancel(current.operation_id, expected_state_version=current.state_version)
                    effect_gate.release.set()
                    await events.wait("cancellation", "cancelled")
                    final = await service.get_status(admitted.operation_id)
                    assert final.state == "cancelled" and effects == []
                    before = await store.recover(now(clock))
                    assert before.pending_items == before.pending_bytes == 0
                    await service.cancel(final.operation_id, expected_state_version=final.state_version)
                    assert await store.recover(now(clock)) == before
                    assert_emission(events, "cancellation", "requested", [1])
                    assert_emission(events, "cancellation", "cancelled", [1])
                assert_emission(events, "admission", "accepted", [1], durations=[17])
                assert_queue_events(events)
            finally:
                admission_gate.release.set()
                effect_gate.release.set()
                await clean_tasks([submitting] + ([stopping] if stopping is not None else []))
                await service.stop()

    @pytest.mark.asyncio
    async def test_rejected_projects_do_not_accumulate_metric_labels_and_drained_labels_retire(self, tmp_path):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            keys = await canonical_projects(backend, tmp_path / "identities", [f"canonical-{n}" for n in range(17)])
            gate, events = CausalGate(), EmittedEvents()
            async def handler(row, probe):
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events, bound=limits(items=1, size=64), workers=1)
            await service.start()
            try:
                accepted = await service.submit(intent(clock, keys["canonical-0"], 0))
                await asyncio.wait_for(gate.entered.wait(), 3)
                for n in range(1, 17):
                    with pytest.raises(service_contract().BackgroundQueueBusyError) as busy:
                        await service.submit(intent(clock, keys[f"canonical-{n}"], n))
                    assert events.select("retry_after", "busy")[-1].value == busy.value.retry_after_ms
                    active = dict((await service.health_snapshot()).metrics.project_service_starts)
                    assert set(active) == {keys["canonical-0"]}
                gate.release.set()
                await events.wait("run_time", "succeeded")
                assert (await service.get_status(accepted.operation_id)).state == "succeeded"
                assert dict((await service.health_snapshot()).metrics.project_service_starts) == {}
                assert_emission(events, "admission", "accepted", [1])
                assert_emission(events, "admission", "busy", [1] * 16)
                assert len(events.select("retry_after", "busy")) == 16
                raw = json.dumps([asdict(event) for event in events], default=str)
                assert all(key not in raw for key in keys.values())
                assert all(f"canonical-{n}" not in raw for n in range(17))
            finally:
                gate.release.set()
                await service.stop()

    def test_required_contract_is_present(self):
        module = service_contract()
        exported = required("scribe_mcp.background", "BackgroundIntentV1", "BackgroundJobServiceV1")
        models = required("scribe_mcp.background.models", "BackgroundOperationIntentV1")
        assert exported.BackgroundIntentV1 is models.BackgroundOperationIntentV1
        assert exported.BackgroundJobServiceV1 is module.BackgroundJobServiceV1

    @pytest.mark.parametrize("kind,outcome", [(k, o) for k, outcomes in EVENT_PAIRS.items() for o in outcomes])
    def test_closed_telemetry_pairs_accept_exact_declared_fields(self, kind, outcome):
        module = service_contract()
        duration, value = event_numbers(kind)
        event = module.BackgroundQueueEventV1(kind, EPOCH, None, outcome, None, duration, value)
        assert (event.kind, event.outcome) == (kind, outcome)
        assert_queue_events([event])

    @pytest.mark.parametrize("kind,outcome", [("unbounded-user-input", "accepted"),
        ("admission", "unbounded-error"), ("admission", "stopped"), ("lifecycle", "accepted")])
    def test_invalid_telemetry_pair_refuses_before_sink_delivery(self, kind, outcome):
        module = service_contract()
        sink = []
        with pytest.raises(ValueError):
            sink.append(module.BackgroundQueueEventV1(kind, EPOCH, None, outcome, None, 1, 1))
        assert sink == []

    @pytest.mark.parametrize("field,value", [("value", -1), ("value", True), ("value", 1.5),
        ("duration_ms", -1), ("duration_ms", True), ("duration_ms", 0.5),
        ("observed_at", datetime(2026, 9, 27))])
    def test_telemetry_rejects_ambiguous_numbers_and_naive_time(self, field, value):
        module = service_contract()
        values = dict(kind="admission", observed_at=EPOCH, lane="durable", outcome="accepted",
                      canonical_project_key_hash="a" * 64, duration_ms=1, value=1)
        values[field] = value
        with pytest.raises(ValueError):
            module.BackgroundQueueEventV1(**values)

    @pytest.mark.asyncio
    async def test_cancellation_before_admission_and_queued_releases_capacity_once(self, tmp_path):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            gate, events = CausalGate(), []
            async def handler(row, probe):
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events, workers=1)
            await service.start()
            try:
                with pytest.raises(service_contract().BackgroundOperationNotFoundError):
                    await service.cancel("not-admitted", expected_state_version=1)
                assert await store.get("not-admitted") is None
                first = await service.submit(intent(clock, "A", 0))
                await asyncio.wait_for(gate.entered.wait(), 3)
                queued = await service.submit(intent(clock, "A", 1))
                current = await service.get_status(queued.operation_id)
                assert current.state in {"accepted", "ready"}
                cancelled = await service.cancel(current.operation_id, expected_state_version=current.state_version)
                assert cancelled.state == "cancelled"
                before = await store.recover(now(clock))
                assert before.pending_items == 1 and before.pending_bytes == 64
                repeated = await service.cancel(cancelled.operation_id, expected_state_version=cancelled.state_version)
                assert repeated == cancelled
                assert await store.recover(now(clock)) == before
                assert (await service.get_status(first.operation_id)).state == "leased"
            finally:
                gate.release.set()
                await service.stop()

    @pytest.mark.asyncio
    async def test_global_event_gauges_equal_durable_counts_and_bytes(self, tmp_path):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            gate, events = CausalGate(), []
            async def handler(row, probe):
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events, workers=1)
            await service.start()
            try:
                for n in range(3):
                    await service.submit(intent(clock, f"project-{n}", n))
                await asyncio.wait_for(gate.entered.wait(), 3)
                snapshot = await store.recover(now(clock))
                for kind, field in (("queue_items", "pending_items"), ("queue_bytes", "pending_bytes")):
                    latest = {}
                    for event in events:
                        if event.kind == kind and event.canonical_project_key_hash is None:
                            latest[event.outcome] = event.value
                    assert set(latest) == {"accepted", "ready", "leased", "retry_wait"}
                    assert sum(latest.values()) == getattr(snapshot, field)
                    for state in latest:
                        rows = [row for row in snapshot.receipts if row.state == state]
                        assert latest[state] == (len(rows) if kind == "queue_items" else sum(row.payload_bytes for row in rows))
                assert sum(event.kind == "admission" and event.outcome == "accepted" for event in events) == 3
                assert sum(event.kind == "worker_claim" for event in events) == 1
                assert sum(event.kind == "attempt" for event in events) == 1
                assert_queue_events(events)
            finally:
                gate.release.set()
                await service.stop()

    @pytest.mark.asyncio
    async def test_retry_wait_cancellation_is_terminal_and_releases_once(self, tmp_path):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            scheduled = asyncio.Event()
            class Events(list):
                def append(self, event):
                    super().append(event)
                    if (event.kind, event.outcome) == ("retry", "scheduled"):
                        scheduled.set()
            events = Events()
            async def handler(row, probe):
                return worker_contract().BackgroundExecutionOutcomeV1("transient_failure", error_code="TEMPORARY")
            service = make_service(store, handler, clock, events, workers=1)
            await service.start()
            try:
                accepted = await service.submit(intent(clock, "A", 0))
                await asyncio.wait_for(scheduled.wait(), 3)
                current = await service.get_status(accepted.operation_id)
                assert current.state == "retry_wait" and current.attempt_count == 1
                cancelled = await service.cancel(current.operation_id, expected_state_version=current.state_version)
                assert cancelled.state == "cancelled"
                assert (await store.recover(now(clock))).pending_items == 0
                repeated = await service.cancel(cancelled.operation_id, expected_state_version=cancelled.state_version)
                assert repeated == cancelled
                assert sum((event.kind, event.outcome) == ("cancellation", "cancelled") for event in events) == 1
            finally:
                await service.stop()

    @pytest.mark.parametrize("item_limit,byte_limit", [(7, 448), (32, 448), (7, 2048)])
    @pytest.mark.asyncio
    async def test_32_admissions_last_item_and_byte_slot_are_atomic(self, tmp_path, item_limit, byte_limit):
        service_contract()
        bound = limits(items=item_limit, size=byte_limit, project_items=32, project_size=2048)
        async with queue_world(tmp_path, stage="service", bound=bound) as (clock, backend, store, scheduling, bound):
            gate, events, tasks = CausalGate(), [], []
            async def handler(row, probe):
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events, bound=bound)
            await service.start()
            try:
                tasks = [asyncio.create_task(service.submit(intent(clock, f"project-{n % 3}", n)))
                         for n in range(32)]
                results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 3)
                receipts = [r for r in results if not isinstance(r, BaseException)]
                busy = [r for r in results if isinstance(r, service_contract().BackgroundQueueBusyError)]
                assert len(receipts) == 7 and len(busy) == 25
                assert all(r.retry_after_ms > 0 for r in busy)
                assert_emission(events, "retry_after", "busy", [r.retry_after_ms for r in busy],
                                durations=[None] * len(busy))
                assert_emission(events, "admission", "busy", [1] * len(busy))
                snapshot = await store.recover(now(clock))
                assert {r.operation_id for r in receipts} == {r.operation_id for r in snapshot.receipts}
                assert snapshot.pending_items == 7 and snapshot.pending_bytes == 448
                metrics = (await service.health_snapshot()).metrics
                assert metrics.item_high_water == 7 and metrics.byte_high_water == 448
                for outcome, maximum in (("items", 7), ("bytes", 448)):
                    observed = [event.value for event in events if event.kind == "high_water" and
                                event.outcome == outcome and event.canonical_project_key_hash is None]
                    assert observed and max(observed) == maximum
                concurrent = [event.value for event in events if event.kind == "high_water" and
                              event.outcome == "concurrency" and event.canonical_project_key_hash is None]
                assert concurrent and max(concurrent) == metrics.concurrency_high_water
                assert max(concurrent) <= 2
            finally:
                gate.release.set()
                await clean_tasks(tasks)
                await service.stop()

    @pytest.mark.parametrize("project_items,project_bytes", [(1, 4096), (32, 64)])
    @pytest.mark.asyncio
    async def test_per_project_item_and_byte_limits_preserve_peer_capacity(self, tmp_path, project_items, project_bytes):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            gate, events = CausalGate(), []
            async def handler(row, probe):
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            bound = limits(project_items=project_items, project_size=project_bytes)
            service = make_service(store, handler, clock, events, bound=bound)
            await service.start()
            try:
                a = await service.submit(intent(clock, "A", 0))
                with pytest.raises(service_contract().BackgroundQueueBusyError):
                    await service.submit(intent(clock, "A", 1))
                b = await service.submit(intent(clock, "B", 0))
                snapshot = await store.recover(now(clock))
                assert {r.operation_id for r in snapshot.receipts} == {a.operation_id, b.operation_id}
                assert snapshot.pending_items == 2 and snapshot.pending_bytes == 128
            finally:
                gate.release.set()
                await service.stop()

    @pytest.mark.asyncio
    async def test_duplicate_conflict_busy_shutdown_and_status_cas(self, tmp_path):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            gate, events = CausalGate(), []
            async def handler(row, probe):
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events, bound=limits(items=1, size=64))
            await service.start()
            try:
                submitted = intent(clock, "A", 0)
                first = await service.submit(submitted)
                duplicate = await service.submit(submitted)
                assert duplicate.operation_id == first.operation_id
                assert (await store.recover(now(clock))).pending_items == 1
                with pytest.raises(service_contract().BackgroundDigestConflictError):
                    await service.submit(replace(submitted, payload_digest="f" * 64))
                start = perf_counter()
                with pytest.raises(service_contract().BackgroundQueueBusyError) as busy:
                    await service.submit(intent(clock, "B", 0))
                assert busy.value.retry_after_ms > 0
                assert (perf_counter() - start) * 1000 <= 500
                current = await service.get_status(first.operation_id)
                models = required("scribe_mcp.background.models", "BackgroundStateVersionConflictError")
                with pytest.raises(models.BackgroundStateVersionConflictError):
                    await service.cancel(first.operation_id, expected_state_version=current.state_version + 10)
                assert (await service.get_status(first.operation_id)).operation_id == first.operation_id
                with pytest.raises(service_contract().BackgroundOperationNotFoundError):
                    await service.get_status("missing-operation")
            finally:
                gate.release.set()
                stopped = await service.stop()
            assert stopped.admission_closed
            with pytest.raises(service_contract().BackgroundServiceShuttingDownError):
                await service.submit(intent(clock, "C", 0))

    @pytest.mark.asyncio
    async def test_foreground_ack_status_cancel_budget_and_event_counts(self, tmp_path):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            events, elapsed = [], {"submit": [], "status": [], "cancel": []}
            async def handler(row, probe):
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events)
            await service.start()
            try:
                async def foreground(n):
                    start = perf_counter()
                    row = await service.submit(intent(clock, f"project-{n % 4}", n))
                    elapsed["submit"].append((perf_counter() - start) * 1000)
                    start = perf_counter()
                    status = await service.get_status(row.operation_id)
                    elapsed["status"].append((perf_counter() - start) * 1000)
                    assert status.operation_id == row.operation_id
                    start = perf_counter()
                    models = required("scribe_mcp.background.models", "BackgroundStateVersionConflictError")
                    try:
                        await service.cancel(row.operation_id, expected_state_version=status.state_version)
                    except models.BackgroundStateVersionConflictError:
                        changed = await service.get_status(row.operation_id)
                        assert changed.state_version > status.state_version
                    elapsed["cancel"].append((perf_counter() - start) * 1000)
                await asyncio.wait_for(asyncio.gather(*(foreground(n) for n in range(32))), 3)
                # Standard-library quantiles keep the original p95 budget and
                # separate profiles so status cannot conceal slow admission.
                for operation, samples in elapsed.items():
                    assert len(samples) == 32
                    assert quantiles(samples, n=20, method="inclusive")[-1] <= 500, {
                        "profile": "ephemeral-sqlite-32-callers", "operation": operation, "raw_ms": samples}
                health = await service.health_snapshot()
                assert health.accepted_receipts == 32
                assert sum(event.kind == "admission" and event.outcome == "accepted" for event in events) == 32
                blob = json.dumps([{key: getattr(event, key) for key in (
                    "kind", "observed_at", "lane", "outcome", "canonical_project_key_hash", "duration_ms", "value")}
                    for event in events], default=str)
                assert all(f"project-{i}" not in blob for i in range(4))
                assert all(intent(clock, f"project-{n % 4}", n).operation_id not in blob for n in range(32))
                assert_queue_events(events)
            finally:
                shutdown = await service.stop()
            assert sum(e.kind == "lifecycle" and e.outcome == "stopped" for e in events) == 1
            before = len(events)
            await service.stop()
            assert len(events) == before
            for field in ("drained", "checkpointed", "cancelled_retryable", "remaining_recoverable", "workers_stopped"):
                assert sum(e.value for e in events if e.kind == "shutdown" and e.outcome == field) == getattr(shutdown, field)


class TestSBRLifecycle:
    def test_required_contract_is_present(self):
        server = lifecycle_contract()
        assert "startup_profile" in inspect.signature(server._startup).parameters
        assert "persistent" in inspect.signature(server.schedule_background_task).parameters

    @pytest.mark.asyncio
    @pytest.mark.parametrize("state,accepting,workers", [("starting", False, 0), ("running", True, 2),
        ("degraded", False, 0), ("draining", False, 2), ("stopped", False, 0)])
    async def test_health_projection_of_canonical_service_states_is_bounded_and_redacted(
        self, tmp_path, monkeypatch, test_agent, state, accepting, workers
    ):
        server = lifecycle_contract()
        service_contract()
        async with world(tmp_path, monkeypatch, test_agent):
            (tmp_path / "health").mkdir()
            async with queue_world(tmp_path / "health", stage="service") as (clock, backend, store, scheduling, bound):
                async def handler(row, probe):
                    return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
                service = make_service(store, handler, clock, [])
                observed = await service.health_snapshot()
                metrics = type(observed.metrics)(**({key: getattr(observed.metrics, key) for key in (
                    "ready", "retry_wait", "leased", "pending_items", "pending_bytes", "item_high_water",
                    "byte_high_water", "concurrency_high_water", "starvation_windows_ge_5s",
                    "project_service_starts", "worker_claims")} | {
                        "project_service_starts": (("private-canonical-project", 1),)}))
                canonical = type(observed)(state=state, accepting=accepting, workers_active=workers, metrics=metrics,
                    accepted_receipts=observed.accepted_receipts, recovered_receipts=observed.recovered_receipts,
                    stale_fence_rejections=observed.stale_fence_rejections,
                    drain_deadline_exceeded=observed.drain_deadline_exceeded)
                # This is a projection test: the external C09 dependency supplies
                # its canonical DTO; the health tool/serializer remains real.
                monkeypatch.setattr(server, "get_background_job_service_health", lambda: canonical)
                tool = required("scribe_mcp.tools.health_check", "health_check")
                result = payload(await tool.health_check(agent=test_agent))
                component = result["components"]["background_job_service"]
                def dictionaries(value):
                    if isinstance(value, dict):
                        yield value
                        for child in value.values():
                            yield from dictionaries(child)
                    elif isinstance(value, list):
                        for child in value:
                            yield from dictionaries(child)
                states = [value for value in dictionaries(component) if "state" in value and "accepting" in value]
                assert len(states) == 1
                projected = states[0]
                assert projected["state"] == state and projected["accepting"] is accepting
                assert projected["workers_active"] == workers
                for key in ("accepted_receipts", "recovered_receipts", "stale_fence_rejections", "drain_deadline_exceeded"):
                    assert projected[key] == getattr(canonical, key)
                serialized = json.dumps(component, default=str)
                assert "private-canonical-project" not in serialized
                assert str(tmp_path) not in serialized
                assert not {"operation_id", "payload", "caller_session_key", "authorization_evidence"} & set().union(
                    *(set(value) for value in dictionaries(component)))

    @pytest.mark.asyncio
    async def test_server_recovers_starts_once_and_stops_before_backend_close(self, tmp_path, monkeypatch, test_agent):
        server = lifecycle_contract()
        module = service_contract()
        store_module = required("scribe_mcp.background.store", "BackgroundReceiptStoreV1")
        sqlite = required("scribe_mcp.storage.sqlite", "SQLiteStorage")
        timeline = []
        admission_probe = {"service": None, "checked": False}
        original_start = module.BackgroundJobServiceV1.start
        original_stop = module.BackgroundJobServiceV1.stop
        original_recover = store_module.BackgroundReceiptStoreV1.recover
        original_close = sqlite.SQLiteStorage.close
        async def observed_start(service, *args, **kwargs):
            timeline.append("start-enter")
            admission_probe["service"] = service
            result = await original_start(service, *args, **kwargs)
            timeline.append("start-return")
            return result
        async def observed_recover(store, *args, **kwargs):
            if not admission_probe["checked"] and admission_probe["service"] is not None:
                admission_probe["checked"] = True
                with pytest.raises(module.BackgroundServiceShuttingDownError):
                    await admission_probe["service"].submit(intent(ManualClock(), "closed-probe", 0, lane="control"))
            result = await original_recover(store, *args, **kwargs)
            timeline.append("recovered")
            return result
        async def observed_stop(service, *args, **kwargs):
            timeline.append("stop-enter")
            assert kwargs.get("admission_close", True) is True
            result = await original_stop(service, *args, **kwargs)
            assert result.admission_closed
            timeline.append("stop-return")
            return result
        async def observed_close(backend, *args, **kwargs):
            timeline.append("backend-close")
            return await original_close(backend, *args, **kwargs)
        baseline = set(asyncio.all_tasks())
        async with world(tmp_path, monkeypatch, test_agent) as observed:
            monkeypatch.setattr(module.BackgroundJobServiceV1, "start", observed_start)
            monkeypatch.setattr(module.BackgroundJobServiceV1, "stop", observed_stop)
            monkeypatch.setattr(store_module.BackgroundReceiptStoreV1, "recover", observed_recover)
            monkeypatch.setattr(sqlite.SQLiteStorage, "close", observed_close)
            monkeypatch.setattr(server, "_startup_complete", False)
            monkeypatch.setattr(server, "_transport_shutdown_phase", "running")
            monkeypatch.setattr(server, "_transport_inflight_operations", 0)
            monkeypatch.setattr(server, "_transport_shutdown_lock", asyncio.Lock())
            monkeypatch.setattr(server, "background_tasks", set())
            monkeypatch.setattr(server, "app", SimpleNamespace(state=SimpleNamespace()))
            for name in ("agent_context_manager", "agent_identity"):
                monkeypatch.setattr(server, name, getattr(server, name))
            monkeypatch.setattr(server, "settings", replace(observed.settings, object_store_url=None,
                object_store_key=None, allow_network=False))
            try:
                await asyncio.wait_for(server._startup(startup_profile="tool_probe"), 3)
                service = server.get_background_job_service()
                assert service is not None
                await server._startup(startup_profile="tool_probe")
                assert timeline.count("start-enter") == 1
                assert timeline.index("recovered") < timeline.index("start-return")
                assert admission_probe["checked"]
                class RecordedTasks(set):
                    def __init__(self, tasks):
                        super().__init__(tasks)
                        self.additions = []
                    def add(self, task):
                        self.additions.append(task)
                        super().add(task)
                legacy = RecordedTasks(server.background_tasks)
                monkeypatch.setattr(server, "background_tasks", legacy)
                row = await service.submit(intent(ManualClock(), "ephemeral-project", 0, lane="durable"))
                assert row.operation_id
                assert legacy.additions == []
                assert await server.storage_backend.get_background_receipt(row.operation_id) is not None
                health = server.get_background_job_service_health()
                assert health.accepting and health.state == "running"
                await asyncio.wait_for(server._shutdown(), 3)
                assert timeline.index("stop-return") < timeline.index("backend-close")
                count = len(timeline)
                await server._shutdown()
                assert len(timeline) == count
                assert all(task in baseline or task.done() for task in asyncio.all_tasks())
            finally:
                await asyncio.wait_for(server._shutdown(), 3)

    @pytest.mark.asyncio
    async def test_legacy_task_helper_preserves_result_and_drains(self):
        server = required("scribe_mcp.server", "schedule_background_task", "drain_background_tasks")
        gate = CausalGate()
        async def chore():
            await gate.hold()
            return "legacy-result"
        task = server.schedule_background_task(chore(), service_name="test-agent", description="ephemeral")
        try:
            await asyncio.wait_for(gate.entered.wait(), 3)
            gate.release.set()
            assert await task_result(task) == "legacy-result"
            assert await server.drain_background_tasks(timeout=1) == []
        finally:
            gate.release.set()
            await clean_tasks([task])

    @pytest.mark.asyncio
    async def test_shutdown_checkpoint_is_recoverable_and_no_task_leaks(self, tmp_path):
        lifecycle_contract()
        baseline = set(asyncio.all_tasks())
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            gate, draining = CausalGate(), asyncio.Event()
            class Events(list):
                def append(self, event):
                    super().append(event)
                    if (event.kind, event.outcome) == ("lifecycle", "draining"):
                        draining.set()
            events = Events()
            async def handler(row, probe):
                probe.mark_commit_started()
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            service = make_service(store, handler, clock, events)
            await service.start()
            await service.start()
            receipt = await service.submit(intent(clock, "A", 0))
            try:
                await asyncio.wait_for(gate.entered.wait(), 3)
                old_claim = await store.get(receipt.operation_id)
                assert old_claim.state == "leased"
                stopping = asyncio.create_task(service.stop(admission_close=True, drain_deadline_ms=10))
                await asyncio.wait_for(draining.wait(), 3)
                assert (await service.health_snapshot()).accepting is False
                clock.advance(11)
                shutdown = await task_result(stopping)
                assert shutdown.admission_closed and shutdown.workers_stopped == 2
                assert shutdown.deadline_exceeded
                durable = await store.get(receipt.operation_id)
                assert durable is not None
                assert durable.state in {"accepted", "ready", "leased", "retry_wait"}
                assert shutdown.remaining_recoverable >= 1
                assert_emission(events, "shutdown", "admitted", [0])
                assert_emission(events, "shutdown", "deadline_exceeded", [1])
                for field in ("drained", "checkpointed", "cancelled_retryable", "remaining_recoverable", "workers_stopped"):
                    assert_emission(events, "shutdown", field, [getattr(shutdown, field)])
                before_events = len(events)
                second = await service.stop()
                assert second.admission_closed
                assert len(events) == before_events
                assert all(t in baseline or t.done() for t in asyncio.all_tasks())
            finally:
                gate.release.set()
                await service.stop()
        # The first lifecycle has exited: its SQLite pool is closed. Reopen the
        # same file, with new store/service objects and no old worker tasks.
        clock.advance(1001)
        effects, completed, recovered_events = [], asyncio.Event(), EmittedEvents()
        async with canonical_sqlite_lifecycle(tmp_path / "queue.db") as fresh_backend:
            store_type = required("scribe_mcp.background.store", "BackgroundReceiptStoreV1")
            fresh_store = store_type.BackgroundReceiptStoreV1(fresh_backend, clock=lambda: now(clock))
            assert fresh_backend is not backend and fresh_store is not store
            async def replacement_handler(row, probe):
                probe.mark_commit_started()
                effects.append((row.operation_id, row.canonical_project_key, row.payload_digest))
                completed.set()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="fresh-effect")
            replacement_service = make_service(fresh_store, replacement_handler, clock, recovered_events, workers=1)
            await replacement_service.start()
            try:
                await asyncio.wait_for(completed.wait(), 3)
                await recovered_events.wait("run_time", "succeeded")
                final = await fresh_store.get(receipt.operation_id)
                assert final.state == "succeeded" and final.fencing_token > old_claim.fencing_token
                assert (await fresh_store.recover(now(clock))).pending_items == 0
                assert (await fresh_store.recover(now(clock))).pending_bytes == 0
                reconcile_receipt_effects([final], effects)
                assert_emission(recovered_events, "recovery", "recovered", [1])
                models = required("scribe_mcp.background.models", "BackgroundStaleFenceError", "BackgroundTransitionOutcomeV1")
                with pytest.raises(models.BackgroundStaleFenceError):
                    await fresh_store.transition(old_claim.operation_id, old_claim.state_version,
                        old_claim.fencing_token, models.BackgroundTransitionOutcomeV1("succeeded", result_ref="late-old"))
                assert await fresh_store.get(final.operation_id) == final
                assert len(effects) == 1
            finally:
                await replacement_service.stop()
        assert all(task in baseline or task.done() for task in asyncio.all_tasks())


# Original CORE-VAL.2 final selectors. They compose the same stage scenarios;
# stage tests are the upstream producer gates, these remain final acceptance.
@pytest.mark.asyncio
async def test_admission_is_atomically_bounded_by_items_and_bytes(tmp_path):
    await TestSBRService().test_32_admissions_last_item_and_byte_slot_are_atomic(tmp_path, 7, 448)


@pytest.mark.asyncio
async def test_duplicate_conflict_busy_and_shutdown_outcomes_are_exact(tmp_path):
    await TestSBRService().test_duplicate_conflict_busy_shutdown_and_status_cas(tmp_path)


@pytest.mark.asyncio
async def test_partition_fairness_caps_and_control_reserve(tmp_path):
    await TestSBRScheduler().test_equal_project_progress_with_control_reserve(tmp_path)


@pytest.mark.parametrize("blocked", ["running", "retry_wait", "failed_terminal", "cancelled", "draining"])
@pytest.mark.asyncio
async def test_blocked_project_does_not_head_of_line_block_peers(tmp_path, blocked):
    worker_contract()
    async with queue_world(tmp_path, stage="worker") as (clock, backend, store, scheduling, bound):
        gate, caller_gate, effects = CausalGate(), CausalGate(), []
        async def handler(row, probe):
            if row.canonical_project_key == "A":
                await gate.hold()
                kind = "transient_failure" if blocked == "retry_wait" else (
                    "permanent_failure" if blocked == "failed_terminal" else "succeeded")
                return worker_contract().BackgroundExecutionOutcomeV1(kind,
                    result_ref="A" if kind == "succeeded" else None,
                    error_code="FAULT" if kind != "succeeded" else None)
            effects.append(row.canonical_project_key)
            return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="peer")
        for n in range(31):
            await ready(store, intent(clock, "A", n, size=16384), bound)
        a_worker = make_worker("A-held", scheduling, store, handler, clock)
        async def blocked_caller():
            step = await a_worker.run_once()
            await caller_gate.hold()
            return step
        task = asyncio.create_task(blocked_caller())
        try:
            await asyncio.wait_for(gate.entered.wait(), 3)
            await ready(store, intent(clock, "B", 0), bound)
            await ready(store, intent(clock, "C", 0), bound)
            if blocked == "cancelled":
                a_worker.request_cancel("A:heavy:0")
            if blocked == "draining":
                a_worker.stop_claiming()
            if blocked in {"retry_wait", "failed_terminal", "cancelled"}:
                gate.release.set()
                await asyncio.wait_for(caller_gate.entered.wait(), 3)
                assert (await store.get("A:heavy:0")).state == blocked
            else:
                assert (await store.get("A:heavy:0")).state == "leased"
            peer_worker = make_worker("peer", scheduling, store, handler, clock)
            for _ in range(3):
                await asyncio.wait_for(peer_worker.run_once(), 3)
                if set(effects) == {"B", "C"}:
                    break
            assert set(effects) == {"B", "C"}
            assert not caller_gate.release.is_set()
            if blocked in {"running", "draining"}:
                assert not gate.release.is_set()
        finally:
            gate.release.set()
            caller_gate.release.set()
            await clean_tasks([task])


@pytest.mark.asyncio
async def test_retry_worker_death_and_stale_fence_are_deterministic(tmp_path):
    await TestSBRWorker().test_worker_death_reclaim_rejects_late_completion(tmp_path)


@pytest.mark.parametrize("commit_started", [False, True])
@pytest.mark.asyncio
async def test_cancellation_races_have_closed_cardinality_clean_outcomes(tmp_path, commit_started):
    await TestSBRWorker().test_leased_cancellation_respects_commit_barrier(tmp_path, commit_started)


@pytest.mark.asyncio
async def test_shutdown_checkpoints_recovers_and_leaks_no_tasks(tmp_path):
    await TestSBRLifecycle().test_shutdown_checkpoint_is_recoverable_and_no_task_leaks(tmp_path)


@pytest.mark.asyncio
async def test_background_metrics_are_exact_and_bounded_cardinality(tmp_path):
    await TestSBRService().test_foreground_ack_status_cancel_budget_and_event_counts(tmp_path)
