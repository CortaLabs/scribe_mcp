"""C-08/C-09/C-13 restart tests against real disposable source artifacts."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import os
import stat
from datetime import datetime
from collections.abc import Awaitable, Callable, Mapping
from typing import get_args, get_origin, get_type_hints, Union
from types import UnionType
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import asdict, replace

import pytest

from core.test_background_queue_contract import (
    clean_tasks, intent, make_service, make_worker, now, queue_world, ready,
    reconcile_receipt_effects, required, service_contract, worker_contract,
)
from core.test_swarm_binding_reliability import payload, world
from fixtures.swarm import (CausalGate, ExpectedEffect, ObservedEffect, SwarmRunMetadata,
                            reconcile_exact_effects)

pytestmark = [pytest.mark.core, pytest.mark.regression,
              pytest.mark.usefixtures("test_agent")]


def wal_contract():
    module = required("scribe_mcp.utils.files", "WriteAheadLog", "WalEntryConflictError",
                      "WalJournalCorruptError", "atomic_write", "async_atomic_write")
    for method in ("read_uncommitted", "has_commit", "commit_entry", "replay_uncommitted"):
        assert callable(getattr(module.WriteAheadLog, method, None)), f"Frozen WAL contract absent: {method}"
    assert "entry_id" in inspect.signature(module.WriteAheadLog.write_entry).parameters
    return module


def document_contract():
    module = required("scribe_mcp.doc_management.apply_preview", "DocumentMutationReceiptV1",
                      "DocumentMutationState", "ApplyPreviewBinding", "ApplyPreviewService")
    expected = {"caller_session_key_hash", "binding_generation", "document_id",
                "document_generation_before", "content_digest_before", "content_digest_after"}
    assert expected <= module.ApplyPreviewBinding.__dataclass_fields__.keys(), (
        "Frozen C-13 ApplyPreviewBinding generation/digest fields absent")
    required("scribe_mcp.doc_management.runtime", "build_document_mutation_receipt",
             "admit_document_mutation", "replay_document_mutation")
    required("scribe_mcp.mcp_adapter", "ScribeExpectedError", "ScribeErrorV1")
    runtime = required("scribe_mcp.doc_management.runtime")
    contexts = required("scribe_mcp.shared.execution_context", "ExecutionContext", "ResolvedRequestContextV1")
    models = required("scribe_mcp.background.models", "DurableOperationReceiptV1")
    store = required("scribe_mcp.background.store", "BackgroundReceiptStoreV1")
    worker, service = worker_contract(), service_contract()
    common = {"request_context": contexts.ResolvedRequestContextV1,
        "binding": module.ApplyPreviewBinding, "normalized_intent": Mapping[str, object]}
    receipt_type = module.DocumentMutationReceiptV1
    signatures = {
        "build_document_mutation_receipt": common,
        "admit_document_mutation": common | {"execution_context": contexts.ExecutionContext,
            "wal": wal_contract().WriteAheadLog, "service": service.BackgroundJobServiceV1 | None,
            "clock": Callable[[], datetime]},
        "replay_document_mutation": {"operation_id": str, "execution_context": contexts.ExecutionContext,
            "request_context": contexts.ResolvedRequestContextV1, "claimed_receipt": models.DurableOperationReceiptV1,
            "cancellation": worker.BackgroundCancellationProbeV1, "wal": wal_contract().WriteAheadLog,
            "store": store.BackgroundReceiptStoreV1, "apply_service": module.ApplyPreviewService,
            "executor": module.RetainedIntentExecutor,
            "converge": Callable[[receipt_type], Awaitable[Mapping[str, str]]]},
    }
    def shape(annotation):
        if isinstance(annotation, list):
            return tuple(shape(item) for item in annotation)
        origin, args = get_origin(annotation), get_args(annotation)
        if origin in (Union, UnionType):
            return ("union", frozenset(shape(item) for item in args))
        return (origin, tuple(shape(item) for item in args)) if origin else annotation
    for name, expected in signatures.items():
        function = getattr(runtime, name)
        signature = inspect.signature(function)
        parameters = signature.parameters
        assert set(parameters) == set(expected), f"Frozen D2 signature absent: {name}"
        assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY and
            parameter.default is inspect.Parameter.empty for parameter in parameters.values())
        assert inspect.iscoroutinefunction(function) is (name != "build_document_mutation_receipt")
        annotations = get_type_hints(function)
        assert set(annotations) == set(expected) | {"return"}
        for parameter, expected_type in (expected | {"return": receipt_type}).items():
            assert shape(annotations[parameter]) == shape(expected_type), (name, parameter, annotations)
    return module


def journal(tmp_path, name="document.md"):
    return wal_contract().WriteAheadLog(tmp_path / name, repo_root=tmp_path)


def retained_row(tmp_path, *, project="canonical-A", content="after\n"):
    return {"op": "document_mutation", "project_key": project,
        "document_id": "document-1", "canonical_path": str(tmp_path / "document.md"),
        "binding_generation": 1, "document_generation_before": 0,
        "document_generation_after": 1,
        "content_digest_before": hashlib.sha256(b"before\n").hexdigest(),
        "content_digest_after": hashlib.sha256(content.encode()).hexdigest(),
        "retained_intent": {"action": "replace_section", "content": content},
        "authorization_evidence_ref": "opaque-evidence-ref", "caller_session_key_hash": "a" * 64}


class TestSBRWAL:
    def test_required_contract_is_present(self):
        wal_contract()

    def test_stable_id_duplicate_conflict_and_commit_are_append_idempotent(self, tmp_path):
        module = wal_contract()
        wal = journal(tmp_path)
        row = retained_row(tmp_path)
        original = copy.deepcopy(row)
        assert wal.write_entry(row, entry_id="operation-1") == "operation-1"
        before = wal.journal_path.read_bytes()
        assert journal(tmp_path).write_entry(row, entry_id="operation-1") == "operation-1"
        assert wal.journal_path.read_bytes() == before
        with pytest.raises(module.WalEntryConflictError):
            journal(tmp_path).write_entry(retained_row(tmp_path, content="conflicting\n"), entry_id="operation-1")
        assert wal.journal_path.read_bytes() == before
        assert row == original
        assert len(wal.read_uncommitted(operation_kind="document_mutation")) == 1
        wal.commit_entry("operation-1")
        committed = wal.journal_path.read_bytes()
        journal(tmp_path).commit_entry("operation-1")
        assert wal.journal_path.read_bytes() == committed
        assert journal(tmp_path).has_commit("operation-1")
        assert journal(tmp_path).read_uncommitted() == ()
        assert stat.S_IMODE(wal.journal_path.stat().st_mode) == 0o600
        rows = [json.loads(line) for line in committed.decode().splitlines()]
        assert Counter(row["op"] for row in rows) == {"document_mutation": 1, "commit": 1}

    def test_restart_before_effect_preserves_every_normalized_document_row(self, tmp_path):
        wal = journal(tmp_path)
        for n in range(3):
            wal.write_entry(retained_row(tmp_path, project=f"canonical-{n}"), entry_id=f"operation-{n}")
        wal.write_entry({"op": "append", "content": "legacy\n"}, entry_id="legacy")
        for restart in range(3):
            recovered = journal(tmp_path).read_uncommitted(operation_kind="document_mutation")
            assert tuple(row["id"] for row in recovered) == tuple(f"operation-{n}" for n in range(3))
            assert all(row["retained_intent"]["content"] == "after\n" for row in recovered)
        assert not (tmp_path / "document.md").exists()

    @pytest.mark.parametrize("tail", ['{"op":', 'not-json\n', '{"op":"commit","ref_id":"unknown"}\n'])
    def test_corrupt_or_truncated_tail_fails_closed_without_losing_valid_rows(self, tmp_path, tail):
        module = wal_contract()
        wal = journal(tmp_path)
        wal.write_entry(retained_row(tmp_path), entry_id="valid")
        before = wal.journal_path.read_bytes()
        with wal.journal_path.open("ab") as stream:
            stream.write(tail.encode())
        corrupt = wal.journal_path.read_bytes()
        assert corrupt.startswith(before)
        with pytest.raises(module.WalJournalCorruptError):
            journal(tmp_path).read_uncommitted()
        with pytest.raises(module.WalJournalCorruptError):
            journal(tmp_path).has_commit("valid")
        assert wal.journal_path.read_bytes() == corrupt
        assert not (tmp_path / "document.md").exists()

    def test_legacy_append_replay_once_and_atomic_overwrite_contract(self, tmp_path):
        module = wal_contract()
        wal = journal(tmp_path, "progress.log")
        wal.write_entry({"op": "append", "content": "one\n"}, entry_id="append-1")
        assert journal(tmp_path, "progress.log").replay_uncommitted() == 1
        assert journal(tmp_path, "progress.log").replay_uncommitted() == 0
        assert (tmp_path / "progress.log").read_text() == "one\n"
        target = tmp_path / "atomic.md"
        module.atomic_write(target, "before\n", repo_root=tmp_path)
        with pytest.raises(ValueError, match="overwrite"):
            module.atomic_write(target, "bad\n", mode="a", repo_root=tmp_path)
        assert target.read_text() == "before\n"
        module.atomic_write(target, "after\n", repo_root=tmp_path)
        assert target.read_text() == "after\n"
        assert not list(tmp_path.glob("*.tmp"))


class TestSBRWorkerReplay:
    def test_required_contract_is_present(self):
        worker_contract()
        wal_contract()

    @pytest.mark.asyncio
    async def test_post_effect_pre_transition_crash_is_exactly_once(self, tmp_path):
        worker_contract()
        async with queue_world(tmp_path, stage="worker") as (clock, backend, store, scheduling, bound):
            # The injected handler's durable sink is keyed by operation ID.
            # Product store/scheduler/worker still own every receipt transition.
            gate, writes = CausalGate(), []
            sink_path = tmp_path / "effects.jsonl"
            def effect(row):
                existing = [json.loads(line) for line in sink_path.read_text().splitlines()] if sink_path.exists() else []
                if row.operation_id not in {value[0] for value in existing}:
                    record = (row.operation_id, row.canonical_project_key, row.payload_digest)
                    with sink_path.open("a") as stream:
                        stream.write(json.dumps(record) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    writes.append(record)
            async def interrupted(row, probe):
                probe.mark_commit_started()
                effect(row)
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            admitted = await ready(store, intent(clock, "A", 0), bound)
            task = asyncio.create_task(make_worker("crashed", scheduling, store, interrupted, clock).run_once())
            try:
                await asyncio.wait_for(gate.entered.wait(), 3)
                crashed = await store.get(admitted.operation_id)
                assert crashed.state == "leased" and len(writes) == 1
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                clock.advance(1001)
                store_type = required("scribe_mcp.background.store", "BackgroundReceiptStoreV1")
                fresh_store = store_type.BackgroundReceiptStoreV1(backend, clock=lambda: now(clock))
                scheduler = required("scribe_mcp.background.scheduler", "BackgroundSchedulerV1", "BackgroundSchedulerConfigV1")
                fresh_scheduler = scheduler.BackgroundSchedulerV1(fresh_store,
                    scheduler.BackgroundSchedulerConfigV1(4, 1, 1, 1), clock=lambda: now(clock))
                async def replay(row, probe):
                    probe.mark_commit_started()
                    effect(row)
                    return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
                worker = make_worker("replay", fresh_scheduler, fresh_store, replay, clock)
                assert (await worker.run_once()).outcome == "succeeded"
                assert (await worker.run_once()).outcome == "idle"
                final = await fresh_store.get(admitted.operation_id)
                assert final.state == "succeeded" and final.fencing_token > crashed.fencing_token
                observed = [tuple(json.loads(line)) for line in sink_path.read_text().splitlines()]
                reconcile_receipt_effects([final], observed)
                assert len(writes) == 1
            finally:
                gate.release.set()
                await clean_tasks([task])


class TestSBRServiceRecovery:
    def test_required_contract_is_present(self):
        service_contract()

    @pytest.mark.asyncio
    async def test_fresh_runtime_recovers_ready_leased_retry_wait_and_capacity(self, tmp_path):
        service_contract()
        async with queue_world(tmp_path, stage="service") as (clock, backend, store, scheduling, bound):
            models = required("scribe_mcp.background.models", "BackgroundPartitionV1", "BackgroundTransitionOutcomeV1")
            receipts = []
            for project in ("ready", "leased", "retry"):
                receipts.append(await ready(store, intent(clock, project, 0), bound))
            held = await store.claim(models.BackgroundPartitionV1("leased", "heavy"), "dead", 1000)
            retry = await store.claim(models.BackgroundPartitionV1("retry", "heavy"), "retry", 1000)
            await store.transition(retry.operation_id, retry.state_version, retry.fencing_token,
                models.BackgroundTransitionOutcomeV1("retry_wait", next_attempt_at=now(clock)))
            before = await store.recover(now(clock))
            assert {row.state for row in before.receipts} == {"ready", "leased", "retry_wait"}
            assert before.pending_items == 3 and before.pending_bytes == 192
            clock.advance(1001)
            events, gate = [], CausalGate()
            async def handler(row, probe):
                await gate.hold()
                return worker_contract().BackgroundExecutionOutcomeV1("succeeded", result_ref="effect")
            fresh = make_service(store, handler, clock, events)
            await fresh.start()
            try:
                assert (await fresh.health_snapshot()).recovered_receipts == 3
                assert {row.operation_id for row in (await store.recover(now(clock))).receipts} == {
                    row.operation_id for row in receipts}
                assert (await fresh.get_status(held.operation_id)).fencing_token >= held.fencing_token
            finally:
                gate.release.set()
                shutdown = await fresh.stop()
            assert all([await store.get(row.operation_id) is not None for row in receipts])
            assert shutdown.drained + shutdown.checkpointed + shutdown.remaining_recoverable + shutdown.cancelled_retryable >= 3


class _HardCrash(BaseException):
    """Interrupt exactly one declared durability boundary, not a product error."""


def expected_error():
    return required("scribe_mcp.mcp_adapter", "ScribeExpectedError").ScribeExpectedError


def receipt(result):
    assert "document_mutation_receipt" in result, "Frozen C-13 mutation receipt missing"
    row = result["document_mutation_receipt"]
    assert row["state"] in {"accepted", "applied", "duplicate", "conflict", "terminal_error", "cancelled"}
    assert not row["queued_offline"] or (row["state"] == "accepted" and row["replay_safe"])
    assert len(row["caller_session_key_hash"]) == 64
    assert not {"caller_session_key", "authorization_evidence", "retained_intent", "journal_path",
                "lease_owner", "fencing_token", "backend"} & row.keys()
    return row


class _DocumentDriver:
    """Observation/fault adapter over the real runtime; no replay/effect engine.

    The outer accepted C14 world keeps the authenticated client transport alive.
    Restart discards Scribe connections, router, manager, service and executor
    objects. Only files/SQLite and the external client's opaque handle survive.
    """
    def __init__(self, observed, patch, *, fault=None, indexed=False, workers=None):
        from datetime import datetime, timezone
        from fixtures.swarm import ManualClock
        self.world, self.patch = observed, patch
        self.runtime = required("scribe_mcp.doc_management.runtime", "admit_document_mutation",
            "replay_document_mutation", "build_document_mutation_receipt")
        self.server = required("scribe_mcp.server", "get_background_job_service", "_startup", "_shutdown")
        self.caller = observed.topology.callers[0]
        self.path = self.caller.default.progress_log.parent / (
            "research/REPLAY_CASE.md" if indexed else "ARCHITECTURE_GUIDE.md")
        self.doc = "replay_case" if indexed else "architecture"
        self.clock, self.epoch = ManualClock(), datetime.now(timezone.utc)
        self.fault, self.used_fault = fault, False
        self.workers = workers
        self.fault_reached = asyncio.Event()
        self.before_effect, self.capture_hold = CausalGate(), CausalGate()
        self.after_write = CausalGate()
        self.hold_inspect = self.hold_capture = False
        self.hold_after_write = False
        self.admissions, self.admitted, self.replays, self.replayed = [], [], [], []
        self.convergence, self.stage_calls, self.writes = [], [], []
        self.terminal = {}
        self.result_events = {}
        self.refusal_events, self.replay_errors = {}, []
        self.active_contexts = {}
        self.phase = 0
        self.active_replays, self.race_attempts = {}, []
        self.race_gates = None
        self.race_tasks = set()
        self.race_entries = []
        self.race_arrived = (asyncio.Event(), asyncio.Event())
        self.operations = set()
        self.capture_operation = None
        self.tasks_baseline = set()
        self.globals_before = {}
        self.changed_globals = set()
        self.target_before = b""
        self.foreground_samples = {}
        self.service_configs = {}
        self.resolutions, self.target_reads = [], []
        self.quality_inputs, self.quality_calls, self.quality_evaluations = [], [], []
        self.quality_fault = None

    def utc_now(self):
        from datetime import timedelta
        return self.epoch + timedelta(seconds=self.clock.now())

    def terminal_event(self, operation):
        return self.terminal.setdefault(operation, asyncio.Event())

    def fail_once(self, name):
        if self.fault == name and not self.used_fault:
            self.used_fault = True
            self.fault_reached.set()
            raise _HardCrash(name)

    def install(self):
        from functools import wraps
        from scribe_mcp.doc_management import runtime
        from scribe_mcp.utils import files
        from scribe_mcp.background.store import BackgroundReceiptStoreV1
        from scribe_mcp.utils.formatters.dispatcher import FormatterDispatcher
        original_admit, original_replay = runtime.admit_document_mutation, runtime.replay_document_mutation
        original_write, original_commit = files.WriteAheadLog.write_entry, files.WriteAheadLog.commit_entry
        original_atomic = files.atomic_write
        original_transition = BackgroundReceiptStoreV1.transition
        original_inspect = runtime._RuntimeRetainedIntentExecutor.inspect_apply_preview_state
        original_execute = runtime._RuntimeRetainedIntentExecutor.execute_retained_intent
        original_store_init = BackgroundReceiptStoreV1.__init__
        service_type = service_contract().BackgroundJobServiceV1
        original_service_init = service_type.__init__
        original_submit = service_type.submit
        original_response = FormatterDispatcher.finalize_tool_response

        @wraps(original_store_init)
        def store_init(store, *args, **kwargs):
            kwargs["clock"] = self.utc_now
            original_store_init(store, *args, **kwargs)
        @wraps(original_service_init)
        def service_init(service, *args, **kwargs):
            kwargs["clock"] = self.utc_now
            bound = inspect.signature(original_service_init).bind(service, *args, **kwargs)
            if self.workers is not None:
                bound.arguments["config"] = replace(bound.arguments["config"], worker_count=self.workers)
            original_service_init(*bound.args, **bound.kwargs)
            self.service_configs[id(service)] = bound.arguments["config"]
        @wraps(original_admit)
        async def admitted(**kwargs):
            # Clock is the declared injected dependency. All authority/binding
            # inputs are the genuine objects supplied by the public runtime.
            kwargs["clock"] = self.utc_now
            assert kwargs["execution_context"].resolved_request_context is kwargs["request_context"]
            self.admissions.append((self.phase, dict(kwargs)))
            result = await original_admit(**kwargs)
            self.admitted.append(result)
            self.operations.add(result.operation_id)
            return result
        @wraps(original_replay)
        async def replayed(**kwargs):
            context = kwargs["request_context"]
            assert kwargs["execution_context"].resolved_request_context is context
            current = await kwargs["store"].get(kwargs["operation_id"])
            assert current == kwargs["claimed_receipt"]
            assert current.state in {"leased", "succeeded", "cancelled", "failed_terminal"}
            self.replays.append((self.phase, dict(kwargs)))
            self.operations.add(kwargs["operation_id"])
            if self.hold_capture and (self.capture_operation is None or self.capture_operation == kwargs["operation_id"]):
                await self.capture_hold.hold()
            original_converge = kwargs["converge"]
            async def converge(row):
                observed_digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
                assert row.content_digest_after == observed_digest
                if self.hold_after_write:
                    await self.after_write.hold()
                quality_before = len(self.quality_evaluations)
                result = await original_converge(row)
                assert set(result) == {"registration", "index", "quality"}
                if result["quality"] == "evaluated":
                    actual = self.quality_evaluations[quality_before:]
                    assert len(actual) == 1, "quality must observe one real evaluation"
                    assert actual[0]["digest"] == row.content_digest_after
                    actual[0]["generation"] = row.document_generation_after
                self.convergence.append((self.phase, row, dict(result), observed_digest))
                return result
            self.active_contexts[asyncio.current_task()] = context
            try:
                self.active_replays[asyncio.current_task()] = dict(kwargs)
                if self.race_gates is not None:
                    slot = len(self.race_entries)
                    assert slot < 2
                    self.race_entries.append((asyncio.current_task(), dict(kwargs)))
                    self.race_arrived[slot].set()
                result = await original_replay(**(kwargs | {"converge": converge}))
                self.replayed.append(result)
                self.result_events.setdefault(result.operation_id, asyncio.Event()).set()
                return result
            except expected_error() as error:
                self.replay_errors.append((kwargs["operation_id"], error.error.error_code))
                self.refusal_events.setdefault(kwargs["operation_id"], asyncio.Event()).set()
                raise
            finally:
                self.active_contexts.pop(asyncio.current_task(), None)
                self.active_replays.pop(asyncio.current_task(), None)
        @wraps(original_inspect)
        async def inspected(executor, *args, **kwargs):
            result = await original_inspect(executor, *args, **kwargs)
            context = self.active_contexts.get(asyncio.current_task())
            if context is not None:
                assert kwargs["execution_context"].resolved_request_context is context
                task = asyncio.current_task()
                if self.race_gates is not None and task not in self.race_tasks:
                    self.race_tasks.add(task)
                    slot = len(self.race_attempts)
                    assert slot < len(self.race_gates), "unexpected extra competing replay"
                    self.race_attempts.append((task, self.active_replays[task], result))
                    await self.race_gates[slot].hold()
                if self.hold_inspect:
                    await self.before_effect.hold()
            return result
        @wraps(original_execute)
        async def executed(executor, *args, **kwargs):
            context = self.active_contexts.get(asyncio.current_task())
            if context is not None:
                assert kwargs["execution_context"].resolved_request_context is context
            return await original_execute(executor, *args, **kwargs)
        @wraps(original_write)
        def write(wal, *args, **kwargs):
            if any(item[1]["wal"] is wal for item in self.admissions):
                if self.fault == "wal_unavailable" and not self.used_fault:
                    self.used_fault = True
                    self.fault_reached.set()
                    raise OSError("ephemeral journal unavailable")
                self.fail_once("before_journal")
            return original_write(wal, *args, **kwargs)
        @wraps(original_submit)
        async def submit(service, row):
            if self.fault == "offline" and not self.used_fault:
                self.used_fault = True
                self.fault_reached.set()
                raise service_contract().BackgroundQueueBusyError(retry_after_ms=25)
            if self.fault == "closed" and not self.used_fault:
                self.used_fault = True
                self.fault_reached.set()
                raise service_contract().BackgroundServiceShuttingDownError()
            if self.fault == "digest_conflict" and not self.used_fault:
                self.used_fault = True
                store = BackgroundReceiptStoreV1(self.world.storage, clock=self.utc_now)
                conflict = replace(row, payload_digest=("f" if row.payload_digest != "f" * 64 else "e") * 64)
                admission = await store.admit(conflict, self.service_configs[id(service)].queue_limits)
                assert admission.status == "accepted"
            return await original_submit(service, row)
        @wraps(original_atomic)
        def atomic(path, *args, **kwargs):
            result = original_atomic(path, *args, **kwargs)
            from pathlib import Path
            if Path(path).resolve() == self.path.resolve():
                self.writes.append((self.phase, hashlib.sha256(self.path.read_bytes()).hexdigest()))
                self.fail_once("after_replace")
            return result
        @wraps(original_commit)
        def commit(wal, operation):
            if operation in self.operations:
                self.fail_once("before_commit")
            return original_commit(wal, operation)
        @wraps(original_transition)
        async def transitioned(store, *args, **kwargs):
            operation = kwargs.get("operation_id", args[0] if args else None)
            outcome = kwargs.get("outcome", args[3] if len(args) > 3 else None)
            if operation in self.operations and outcome is not None and outcome.state == "succeeded":
                self.fail_once("before_success")
            row = await original_transition(store, *args, **kwargs)
            if row.state in {"succeeded", "failed_terminal", "cancelled"}:
                self.terminal_event(row.operation_id).set()
            return row
        @wraps(original_response)
        async def response(formatter, *args, **kwargs):
            result = await original_response(formatter, *args, **kwargs)
            if self.fault == "before_response" and not self.used_fault:
                data = payload(result)
                if isinstance(data, dict) and "document_mutation_receipt" in data:
                    operation = receipt(data)["operation_id"]
                    await asyncio.wait_for(self.terminal_event(operation).wait(), 3)
                    self.fail_once("before_response")
            return result
        self.patch.setattr(BackgroundReceiptStoreV1, "__init__", store_init)
        self.patch.setattr(service_type, "__init__", service_init)
        self.patch.setattr(runtime, "admit_document_mutation", admitted)
        self.patch.setattr(runtime, "replay_document_mutation", replayed)
        self.patch.setattr(runtime._RuntimeRetainedIntentExecutor, "inspect_apply_preview_state", inspected)
        self.patch.setattr(runtime._RuntimeRetainedIntentExecutor, "execute_retained_intent", executed)
        self.patch.setattr(files.WriteAheadLog, "write_entry", write)
        self.patch.setattr(files.WriteAheadLog, "commit_entry", commit)
        self.patch.setattr(files, "atomic_write", atomic)
        self.patch.setattr(service_type, "submit", submit)
        self.patch.setattr(BackgroundReceiptStoreV1, "transition", transitioned)
        self.patch.setattr(FormatterDispatcher, "finalize_tool_response", response)
        self.original_replay = original_replay
        original_collect = runtime.collect_managed_doc_quality_warnings
        def collected(*args, **kwargs):
            # Capture the exact arguments consumed by the real evaluator. The
            # two opt-in corruptions are sensitivity controls, never receipts.
            actual = dict(kwargs)
            if self.quality_fault == "stale-content":
                actual["text"] = self.target_before.decode()
            elif self.quality_fault == "wrong-target":
                actual["path"] = self.caller.cross_repo.root / "wrong-quality.md"
                actual["doc_name"] = "wrong-quality"
            result = original_collect(*args, **actual)
            self.quality_inputs.append((asyncio.current_task(), actual, result))
            return result
        self.patch.setattr(runtime, "collect_managed_doc_quality_warnings", collected)
        # These wrappers delegate actual convergence stages; no success map is
        # supplied by the fixture. Faults are infrastructure failures at a stage.
        for name, stage in (("auto_register_document", "registration"), ("_handle_quality_check", "quality")):
            original = getattr(runtime, name)
            async def measured(*args, _original=original, _stage=stage, **kwargs):
                if self.fault == "outage_" + _stage and not self.used_fault:
                    self.used_fault = True
                    self.fault_reached.set()
                    raise OSError("ephemeral convergence outage")
                start = len(self.quality_inputs)
                result = await _original(*args, **kwargs)
                if _stage == "quality":
                    self.quality_calls.append((args, dict(kwargs)))
                    consumed_rows = [(value, warnings) for task, value, warnings in self.quality_inputs[start:]
                                     if task is asyncio.current_task()]
                    consumed = [value for value, warnings in consumed_rows]
                    assert len(consumed) == 1, "quality must consume exactly one target"
                    actual = consumed[0]
                    from pathlib import Path
                    assert Path(actual["path"]).resolve() == self.path.resolve(), "quality wrong target"
                    assert actual["doc_name"] == self.doc, "quality wrong document"
                    scope = result["scope"]
                    assert scope["doc_name"] == self.doc and Path(scope["path"]).resolve() == self.path.resolve(), "quality wrong result scope"
                    digest = hashlib.sha256(actual["text"].encode()).hexdigest()
                    assert actual["text"].encode() == self.path.read_bytes(), "quality stale consumed content"
                    current_warnings = runtime.enrich_quality_warning_context(
                        runtime.normalize_warnings(consumed_rows[0][1]), text=actual["text"])
                    assert result["warnings"] == current_warnings, "quality stale result warnings"
                    for key, value in runtime.summarize_quality_warnings(current_warnings).items():
                        assert result["summary"][key] == value, "quality stale result summary"
                    bound = inspect.signature(_original).bind(*args, **kwargs)
                    borrowed = bound.arguments["execution_context"].resolved_request_context
                    current = self.active_contexts.get(asyncio.current_task())
                    assert current is None or borrowed is current, "quality must borrow the real replay C11"
                    self.quality_evaluations.append({"digest": digest, "scope": dict(scope),
                        "result": result, "consumed": actual, "generation": None})
                else:
                    digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
                self.stage_calls.append((self.phase, _stage, digest, result))
                return result
            self.patch.setattr(runtime, name, measured)
        tools = required("scribe_mcp.tools.manage_docs", "_get_index_updater_for_path")
        original_index = tools._get_index_updater_for_path
        def index(*args, **kwargs):
            updater = original_index(*args, **kwargs)
            if updater is None:
                return None
            async def run():
                if self.fault == "outage_index" and not self.used_fault:
                    self.used_fault = True
                    self.fault_reached.set()
                    raise OSError("ephemeral index outage")
                result = await updater()
                self.stage_calls.append((self.phase, "index", hashlib.sha256(self.path.read_bytes()).hexdigest(), result))
                return result
            return run
        self.patch.setattr(tools, "_get_index_updater_for_path", index)
        self.observe_resolution()

    def observe_resolution(self):
        """Spy on the one real C02 function and delegate every source alias."""
        import sys
        resolver = required("scribe_mcp.shared.logging_utils", "resolve_project_target")
        original_resolve = resolver.resolve_project_target
        for name in ("get_session_project", "fetch_project"):
            original = getattr(self.world.storage, name)
            async def read(*args, _name=name, _original=original, **kwargs):
                self.target_reads.append((asyncio.current_task(), _name))
                return await _original(*args, **kwargs)
            self.patch.setattr(self.world.storage, name, read)
        async def resolved(*args, **kwargs):
            bound = inspect.signature(original_resolve).bind(*args, **kwargs)
            result = await original_resolve(*args, **kwargs)
            self.resolutions.append((asyncio.current_task(), bound.arguments.get("target"), result))
            return result
        for module in tuple(sys.modules.values()):
            if getattr(module, "__name__", "").startswith("scribe_mcp."):
                for name, value in tuple(vars(module).items()):
                    if value is original_resolve:
                        self.patch.setattr(module, name, resolved)

    async def start(self):
        from types import SimpleNamespace
        from dataclasses import replace
        from scribe_mcp import server
        self.patch.setattr(server, "_startup_complete", False)
        self.patch.setattr(server, "_transport_shutdown_phase", "running")
        self.patch.setattr(server, "_transport_inflight_operations", 0)
        self.patch.setattr(server, "_transport_shutdown_lock", asyncio.Lock())
        self.patch.setattr(server, "background_tasks", set())
        self.patch.setattr(server, "app", SimpleNamespace(state=SimpleNamespace()))
        self.patch.setattr(server, "settings", replace(self.world.settings,
            object_store_url=None, object_store_key=None, allow_network=False))
        self.globals_before = dict(vars(server))
        self.tasks_baseline = set(asyncio.all_tasks())
        await asyncio.wait_for(server._startup(startup_profile="tool_probe"), 3)
        self.changed_globals = {key for key, value in vars(server).items()
            if key not in self.globals_before or value is not self.globals_before[key]}
        self.service = server.get_background_job_service()
        assert self.service is not None
        assert server.storage_backend is self.world.storage

    async def prepare(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("# Replay contract\n<!-- ID: contract -->\nbefore\n\n## Peer\n<!-- ID: peer -->\npeer\n", encoding="utf-8")
        self.target_before = self.path.read_bytes()
        if self.doc == "replay_case":
            record = self.world.project(self.caller.default)
            docs = json.loads(record.docs_json)
            docs[self.doc] = str(self.path)
            await self.world.storage.update_project_docs(self.caller.default.name, json.dumps(docs),
                repo_root=str(self.caller.default.root))
        assert payload(await self.world.bind(self.caller))["ok"]
        self.target_before = self.path.read_bytes()
        self.writes.clear()
        self.before_binding = await self.world.binding(self.caller)
        preview = payload(await self.world.call(self.caller, "manage_docs", action="replace_section",
            doc=self.doc, section="contract", content="after\n", dry_run=True))
        assert preview["ok"] and preview["apply"]["receipt"]
        assert "document_mutation_receipt" not in preview
        self.token = preview["apply"]["receipt"]
        assert self.path.read_bytes() == self.target_before

    async def apply(self):
        try:
            return payload(await self.world.call(self.caller, "manage_docs", action="apply_preview",
                metadata={"receipt": self.token}))
        finally:
            sample = self.world.samples.get(self.caller.caller_id)
            if sample is not None:
                for row in self.admitted:
                    self.foreground_samples.setdefault(row.operation_id, {
                        "binding_reads": sample.reads["get_session_project"],
                        "project_reads": sample.reads["fetch_project"],
                        "contexts": len({id(context) for context in sample.contexts if context is not None}),
                        "envelopes": copy.deepcopy(sample.envelopes)})

    async def wait_terminal(self, operation):
        await asyncio.wait_for(self.terminal_event(operation).wait(), 3)
        row = await self.service.get_status(operation)
        assert row.state in {"succeeded", "failed_terminal", "cancelled"}
        return row

    async def restart(self, *, hard=True):
        from scribe_mcp import server
        from scribe_mcp.state.manager import StateManager
        from scribe_mcp.shared.execution_context import RouterContextManager, resolve_application_identity
        from core.test_swarm_binding_reliability import CURRENT_OBSERVATION
        old_phase = [kwargs for phase, kwargs in self.replays if phase == self.phase]
        if old_phase:
            lease = old_phase[-1]["claimed_receipt"].lease_expires_at
            if lease is not None:
                self.clock.advance(max(0, int((lease - self.utc_now()).total_seconds() * 1000)) + 1)
        if hard:
            current = asyncio.current_task()
            owned = [task for task in asyncio.all_tasks() if task not in self.tasks_baseline and task is not current]
            await clean_tasks(owned)
        else:
            await asyncio.wait_for(server._shutdown(), 3)
        previous_backend = self.world.storage
        journal_source = self.admissions[-1][1]["wal"] if self.admissions else None
        if journal_source is not None:
            journal_location, journal_root = journal_source.log_path, journal_source.repo_root
        await previous_backend.close()
        # Restore only globals actually changed by this phase's startup. This
        # resets process-local lifecycle objects without guessing private names.
        for name in self.changed_globals:
            if name in self.globals_before:
                self.patch.setattr(server, name, self.globals_before[name])
            elif hasattr(server, name):
                self.patch.delattr(server, name)
        backend = required("scribe_mcp.storage.sqlite", "SQLiteStorage").SQLiteStorage(self.world.settings.sqlite_path)
        await backend.setup()
        self.world.storage = backend
        self.world.manager = StateManager(path=self.world.settings.default_state_path, storage_backend=backend)
        self.world.router = RouterContextManager(backend)
        self.patch.setattr(server, "storage_backend", backend)
        self.patch.setattr(server, "state_manager", self.world.manager)
        self.patch.setattr(server, "router_context_manager", self.world.router)
        self.patch.setattr(server, "get_execution_context", lambda: self.world.router.get_current())
        # A genuine still-connected client validates its previously issued
        # opaque handle through the real host function. No context is forged.
        for caller_id, identity in tuple(self.world.identities.items()):
            self.world.identities[caller_id] = resolve_application_identity(
                principal_id=identity.principal_id, protocol_era=identity.protocol_era,
                transport=identity.transport, supplied_handle=identity.application_handle, connection_id=None)
        for name in ("get_session_project", "fetch_project"):
            original = getattr(backend, name)
            async def measured(*args, _original=original, _name=name, **kwargs):
                sample = CURRENT_OBSERVATION.get()
                if sample is not None:
                    sample.reads[_name] += 1
                return await _original(*args, **kwargs)
            self.patch.setattr(backend, name, measured)
        self.phase += 1
        if journal_source is not None:
            self.current_wal = wal_contract().WriteAheadLog(journal_location, repo_root=journal_root)
        await self.start()
        assert server.storage_backend is not previous_backend
        for phase, fresh in self.replays:
            if phase == self.phase:
                assert all(fresh["request_context"] is not old["request_context"] for old in old_phase)
                assert all(fresh["executor"] is not old["executor"] for old in old_phase)
                assert all(fresh["store"] is not old["store"] for old in old_phase)
                assert all(fresh["apply_service"] is not old["apply_service"] for old in old_phase)

    async def assert_applied_once(self, operation):
        terminal = await self.wait_terminal(operation)
        assert terminal.state == "succeeded"
        assert self.path.read_text().count("after") == 1
        writes = [(phase, digest) for phase, digest in self.writes]
        assert len(writes) == 1, writes
        selected = [row for row in self.replayed if row.operation_id == operation and row.state == "applied"]
        assert selected
        row = selected[-1]
        assert row.document_generation_after == row.document_generation_before + 1
        assert row.content_digest_after == hashlib.sha256(self.path.read_bytes()).hexdigest()
        matching = [kw for phase, kw in self.replays if kw["operation_id"] == operation]
        assert matching
        current_wal = self.current_wal if hasattr(self, "current_wal") else matching[-1]["wal"]
        assert current_wal.has_commit(operation)
        assert all(row["id"] != operation for row in current_wal.read_uncommitted())
        old = [kw for phase, kw in self.replays if phase < self.phase]
        for phase, fresh in self.replays:
            if phase == self.phase:
                assert all(fresh["request_context"] is not previous["request_context"] for previous in old)
                assert all(fresh["executor"] is not previous["executor"] for previous in old)
                assert all(fresh["store"] is not previous["store"] for previous in old)
                assert all(fresh["apply_service"] is not previous["apply_service"] for previous in old)
        self.binding_after = await self.world.binding(self.caller)
        assert self.binding_after == self.before_binding
        expected, observed = document_ledger(self, row)
        result = reconcile_exact_effects(expected, observed, metadata=document_metadata(self, row))
        assert result.verdict == "PASS", result.as_json_dict()
        assert await self.world.binding(self.caller) == self.before_binding
        return row

    async def close(self):
        self.before_effect.release.set()
        self.after_write.release.set()
        self.capture_hold.release.set()
        try:
            await asyncio.wait_for(self.server._shutdown(), 3)
        finally:
            current = asyncio.current_task()
            owned = [task for task in asyncio.all_tasks() if task not in self.tasks_baseline and task is not current]
            await clean_tasks(owned)
            await self.world.storage.close()


def document_metadata(driver, row):
    return SwarmRunMetadata("682cd4a-source-tree", 20260927, driver.world.topology.as_json_dict(),
        {row.caller_session_key_hash: driver.world.bind_counts[driver.caller.caller_id]})


def document_ledger(driver, row, *, registration=(), indexes=(), quality=()):
    """Map actual file/registry/index/quality observations to the sole C14 oracle."""
    sample = driver.foreground_samples[row.operation_id]
    envelopes = sample["envelopes"]
    binding = driver.before_binding
    base = dict(run_id="document-replay", operation_id=row.operation_id,
        caller_id=row.caller_session_key_hash,
        application_id=driver.world.identity(driver.caller).identity_key,
        stable_session_id=driver.world.stable_sessions[driver.caller.caller_id],
        default_project_key=binding.project_key, explicit_project_key=None,
        target_project_key=row.project_key, mutation_fingerprint=row.content_digest_after,
        result_code="OK", binding_generation=binding.binding_generation)
    stages = {"document": [digest for phase, digest in driver.writes]}
    if registration or indexes or quality:
        stages.update(registration=list(registration), index=list(indexes), quality=list(quality))
    expected, observed = [], []
    for stage, actual_digests in stages.items():
        wanted = ExpectedEffect(**base, effect=stage)
        expected.append(wanted)
        for digest in actual_digests:
            observed.append(ObservedEffect(**(asdict(wanted) | {"mutation_fingerprint": digest}),
                default_after=driver.binding_after.project_key,
                generation_after=driver.binding_after.binding_generation,
                binding_reads=sample["binding_reads"], project_reads=sample["project_reads"],
                context_count=sample["contexts"], timing_envelope_count=len(envelopes),
                accounted_ratio=envelopes[0]["accounted_ratio"] if len(envelopes) == 1 else 0))
    return expected, observed


@asynccontextmanager
async def document_world(tmp_path, monkeypatch, test_agent, *, fault=None, indexed=False, workers=None):
    document_contract()
    worker_contract()
    service_contract()
    required("scribe_mcp.server", "get_background_job_service")
    async with world(tmp_path, monkeypatch, test_agent) as observed:
        with monkeypatch.context() as patch:
            driver = _DocumentDriver(observed, patch, fault=fault, indexed=indexed, workers=workers)
            driver.install()
            await driver.start()
            try:
                await driver.prepare()
                yield driver
            finally:
                await driver.close()


class TestSBRDocumentReplay:
    def test_required_contract_is_present(self):
        document_contract()
        runtime = required("scribe_mcp.doc_management.runtime", "admit_document_mutation", "replay_document_mutation")
        assert set(inspect.signature(runtime.admit_document_mutation).parameters) == {
            "execution_context", "request_context", "binding", "normalized_intent", "wal", "service", "clock"}
        assert set(inspect.signature(runtime.replay_document_mutation).parameters) == {
            "operation_id", "execution_context", "request_context", "claimed_receipt", "cancellation",
            "wal", "store", "apply_service", "executor", "converge"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fault", ["offline", "after_replace", "before_commit", "before_success", "before_response"])
    async def test_all_durable_crash_windows_reopen_and_apply_once(self, tmp_path, monkeypatch, test_agent, fault):
        async with document_world(tmp_path, monkeypatch, test_agent, fault=fault) as driver:
            task = asyncio.create_task(driver.apply())
            try:
                await asyncio.wait_for(driver.fault_reached.wait(), 3)
                assert driver.admissions
                kwargs = driver.admissions[-1][1]
                if fault == "offline":
                    first = receipt(await asyncio.wait_for(task, 3))
                    operation = first["operation_id"]
                    assert first["state"] == "accepted" and first["queued_offline"]
                    assert driver.writes == []
                else:
                    operation = driver.admitted[-1].operation_id if driver.admitted else driver.replays[-1][1]["operation_id"]
                if fault == "before_response":
                    with pytest.raises(_HardCrash):
                        await task
                    assert (await driver.service.get_status(operation)).state == "succeeded"
                else:
                    assert kwargs["wal"].read_uncommitted() or kwargs["wal"].has_commit(operation)
                if fault in {"after_replace", "before_commit", "before_success", "before_response"}:
                    assert len(driver.writes) == 1
                old_contexts = [kw["request_context"] for phase, kw in driver.replays]
                await driver.restart()
                final = await driver.assert_applied_once(operation)
                for phase, kw in driver.replays:
                    if phase == driver.phase:
                        assert all(kw["request_context"] is not old for old in old_contexts)
                before = len(driver.writes)
                replay = receipt(await driver.apply())
                assert replay["operation_id"] == operation
                assert replay["state"] in {"applied", "duplicate"}
                assert len(driver.writes) == before
                assert final.document_generation_after == final.document_generation_before + 1
            finally:
                await clean_tasks([task])

    @pytest.mark.asyncio
    async def test_pre_journal_failure_never_claims_acceptance(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent, fault="before_journal") as driver:
            with pytest.raises(_HardCrash):
                await driver.apply()
            assert driver.admitted == [] and driver.writes == [] and driver.convergence == []
            assert driver.path.read_bytes() == driver.target_before
            kw = driver.admissions[-1][1]
            assert kw["wal"].read_uncommitted() == ()

    @pytest.mark.asyncio
    async def test_journal_io_failure_is_typed_retryable_and_never_accepted(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent, fault="wal_unavailable") as driver:
            result = await driver.apply()
            assert result["ok"] is False and result["retryable"] is True
            assert result["error_code"] == "SCRIBE_BUSY"
            assert driver.admitted == [] and driver.writes == []
            assert driver.path.read_bytes() == driver.target_before

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["busy", "closed", "missing"])
    async def test_wal_durable_busy_closed_and_missing_service_recover_same_operation(self, tmp_path, monkeypatch, test_agent, mode):
        async with document_world(tmp_path, monkeypatch, test_agent,
            fault="offline" if mode == "busy" else "closed" if mode == "closed" else None) as driver:
            if mode == "missing":
                with monkeypatch.context() as unavailable:
                    unavailable.setattr(driver.server, "get_background_job_service", lambda: None)
                    first = receipt(await driver.apply())
                assert driver.admissions[-1][1]["service"] is None
            else:
                first = receipt(await driver.apply())
            assert first["state"] == "accepted" and first["queued_offline"] and first["replay_safe"]
            assert driver.writes == []
            before_rows = driver.admissions[-1][1]["wal"].read_uncommitted()
            assert sum(row["id"] == first["operation_id"] for row in before_rows) == 1
            await driver.restart()
            await driver.assert_applied_once(first["operation_id"])

    @pytest.mark.asyncio
    async def test_durable_digest_conflict_is_typed_and_effect_free_on_repeat(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent, fault="digest_conflict") as driver:
            first, second = await driver.apply(), await driver.apply()
            for result in (first, second):
                assert result["ok"] is False
                assert result["error_code"] == "SCRIBE_DOCUMENT_GENERATION_STALE"
            assert driver.writes == [] and driver.convergence == []
            assert driver.path.read_bytes() == driver.target_before

    @pytest.mark.asyncio
    async def test_foreground_and_replay_each_resolve_once_and_borrow_one_c11(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent) as driver:
            driver.resolutions.clear()
            driver.target_reads.clear()
            row = receipt(await driver.apply())
            await driver.wait_terminal(row["operation_id"])
            product_reads = Counter(driver.target_reads)
            assert len(driver.resolutions) == 2
            assert all(result.project_key == row["project_key"] for task, target, result in driver.resolutions)
            assert any(getattr(target, "project_key", None) == row["project_key"]
                       for task, target, result in driver.resolutions)
            assert all(count <= 1 for count in product_reads.values())
            foreground = driver.admissions[-1][1]
            background = driver.replays[-1][1]
            assert foreground["request_context"] is not background["request_context"]
            assert foreground["execution_context"].resolved_request_context is foreground["request_context"]
            assert background["execution_context"].resolved_request_context is background["request_context"]
            await driver.assert_applied_once(row["operation_id"])

    @pytest.mark.asyncio
    async def test_builder_is_pure_stable_and_sensitive_to_identity_components(self, tmp_path, monkeypatch, test_agent):
        from dataclasses import replace
        async with document_world(tmp_path, monkeypatch, test_agent, fault="offline") as driver:
            result = receipt(await driver.apply())
            kw = driver.admissions[-1][1]
            builder = driver.runtime.build_document_mutation_receipt
            inputs = {key: kw[key] for key in ("request_context", "binding", "normalized_intent")}
            before = await driver.world.snapshot()
            io = []
            path_type = type(driver.path)
            original_open = path_type.open
            original_connection = driver.world.storage._internals._run_with_connection
            def observed_open(path, *args, **kwargs):
                io.append("file")
                return original_open(path, *args, **kwargs)
            def observed_connection(*args, **kwargs):
                io.append("database")
                return original_connection(*args, **kwargs)
            with monkeypatch.context() as observing:
                observing.setattr(path_type, "open", observed_open)
                observing.setattr(driver.world.storage._internals, "_run_with_connection", observed_connection)
                first, second = builder(**inputs), builder(**inputs)
            assert io == []
            assert first.operation_id == second.operation_id == result["operation_id"]
            assert first.state == "accepted" and first.replay_safe and not first.queued_offline
            assert first.document_generation_after is first.content_digest_after is None
            assert await driver.world.snapshot() == before
            variants = []
            for field, value in (("document_id", "other-document"), ("document_generation_before", kw["binding"].document_generation_before + 1),
                                 ("content_digest_after", "f" * 64)):
                variants.append(inputs | {"binding": replace(kw["binding"], **{field: value})})
            variants.append(inputs | {"normalized_intent": dict(kw["normalized_intent"]) | {"content": "different"}})
            context = kw["request_context"]
            changed_generation = context.default_binding_generation + 1
            changed_context = replace(context, default_binding_generation=changed_generation,
                resolved_target=replace(context.resolved_target, default_binding_generation=changed_generation))
            variants.append(inputs | {"request_context": changed_context,
                "binding": replace(kw["binding"], binding_generation=changed_generation)})
            other = driver.world.project(driver.caller.same_repo)
            changed_context = replace(context, resolved_target=replace(context.resolved_target,
                project_key=other.project_key, project_name=other.name))
            variants.append(inputs | {"request_context": changed_context,
                "binding": replace(kw["binding"], project_key=other.project_key)})
            for variant in variants:
                assert builder(**variant).operation_id != first.operation_id
            assert await driver.world.snapshot() == before

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case,code", [
        ("binding", "SCRIBE_BINDING_GENERATION_STALE"),
        ("document_generation", "SCRIBE_DOCUMENT_GENERATION_STALE"),
        ("digest", "SCRIBE_DOCUMENT_GENERATION_STALE"),
        ("root", "SCRIBE_PROJECT_ROOT_MISMATCH"),
        ("target", "SCRIBE_PROJECT_ROOT_MISMATCH"),
        ("path", "SCRIBE_PROJECT_ROOT_MISMATCH"),
        ("revoked", "SCRIBE_CALLER_SESSION_UNVERIFIED"),
        ("fence", "SCRIBE_STALE_FENCE"),
        ("unclaimed", "SCRIBE_STALE_FENCE"),
    ])
    async def test_replay_refuses_current_identity_generation_digest_and_fence_drift(
        self, tmp_path, monkeypatch, test_agent, case, code
    ):
        from dataclasses import replace
        from scribe_mcp.shared.execution_context import revoke_application_identity
        async with document_world(tmp_path, monkeypatch, test_agent) as driver:
            if case == "document_generation":
                driver.hold_inspect = True
                first_task = asyncio.create_task(driver.apply())
                try:
                    await asyncio.wait_for(driver.before_effect.entered.wait(), 3)
                    first_operation = driver.replays[-1][1]["operation_id"]
                    second = payload(await driver.world.call(driver.caller, "manage_docs", action="replace_section",
                        doc=driver.doc, section="peer", content="second accepted generation"))
                    second_operation = receipt(second)["operation_id"]
                    assert second_operation != first_operation
                    driver.capture_operation = second_operation
                    driver.hold_capture = True
                    driver.hold_inspect = False
                    driver.before_effect.release.set()
                    await driver.wait_terminal(first_operation)
                    await asyncio.wait_for(driver.capture_hold.entered.wait(), 3)
                    kw = dict(driver.replays[-1][1])
                    assert kw["operation_id"] == second_operation
                    # The second intent was genuinely admitted before the first
                    # committed. Restore its preimage bytes after real lineage
                    # advancement so digest equality cannot hide the stale gen.
                    driver.path.write_bytes(driver.target_before)
                    before = driver.path.read_bytes(), len(driver.writes), len(driver.convergence)
                    with pytest.raises(expected_error()) as refused:
                        await driver.original_replay(**kw)
                    assert refused.value.error.error_code == code
                    assert (driver.path.read_bytes(), len(driver.writes), len(driver.convergence)) == before
                finally:
                    driver.before_effect.release.set()
                    driver.capture_hold.release.set()
                    await clean_tasks([first_task])
                return
            driver.hold_capture = True
            task = asyncio.create_task(driver.apply())
            try:
                await asyncio.wait_for(driver.capture_hold.entered.wait(), 3)
                kw = dict(driver.replays[-1][1])
                operation = kw["operation_id"]
                original_bytes = driver.path.read_bytes()
                if case == "binding":
                    assert payload(await driver.world.bind(driver.caller, project=driver.caller.same_repo))["ok"]
                elif case == "digest":
                    driver.path.write_text("external third digest\n", encoding="utf-8")
                elif case == "path":
                    saved = driver.path.with_suffix(".saved")
                    driver.path.rename(saved)
                    outside = driver.caller.cross_repo.root / "outside.md"
                    outside.write_text("peer document remains untouched\n", encoding="utf-8")
                    driver.path.symlink_to(outside)
                elif case in {"root", "target"}:
                    context = kw["request_context"]
                    target = context.resolved_target
                    if case == "root":
                        target = replace(target, canonical_repo_root=str(driver.caller.cross_repo.root))
                    else:
                        peer = driver.world.project(driver.caller.same_repo)
                        target = replace(target, project_key=peer.project_key, project_name=peer.name)
                    context = replace(context, resolved_target=target)
                    kw["request_context"] = context
                    kw["execution_context"] = replace(kw["execution_context"], resolved_request_context=context)
                elif case == "revoked":
                    assert revoke_application_identity(driver.world.identity(driver.caller).identity_key)
                elif case == "fence":
                    old = kw["claimed_receipt"]
                    driver.clock.advance(max(0, int((old.lease_expires_at - driver.utc_now()).total_seconds() * 1000)) + 1)
                    models = required("scribe_mcp.background.models", "BackgroundPartitionV1")
                    higher = await kw["store"].claim(models.BackgroundPartitionV1(old.canonical_project_key, old.lane), "higher", 1000)
                    assert higher is not None and higher.fencing_token > old.fencing_token
                else:
                    model = required("scribe_mcp.background.models", "BackgroundTransitionOutcomeV1")
                    actual = kw["claimed_receipt"]
                    await kw["store"].transition(operation, actual.state_version, actual.fencing_token,
                        model.BackgroundTransitionOutcomeV1("retry_wait", next_attempt_at=driver.utc_now()))
                    kw["claimed_receipt"] = await kw["store"].get(operation)
                    assert kw["claimed_receipt"].state == "retry_wait"
                before = driver.path.read_bytes(), len(driver.writes), len(driver.convergence)
                with pytest.raises(expected_error()) as refused:
                    await driver.original_replay(**kw)
                assert refused.value.error.error_code == code
                assert (driver.path.read_bytes(), len(driver.writes), len(driver.convergence)) == before
            finally:
                driver.capture_hold.release.set()
                await clean_tasks([task])

    @pytest.mark.asyncio
    async def test_anchor_cas_is_additional_and_refuses_before_any_effect(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent) as driver:
            before = await driver.world.snapshot()
            result = payload(await driver.world.call(driver.caller, "manage_docs", action="replace_section",
                doc=driver.doc, section="contract", content="must-not-write", expected_anchor_sha256="0" * 64))
            assert result["ok"] is False and result["error_code"] == "SCRIBE_DOCUMENT_GENERATION_STALE"
            assert driver.path.read_bytes() == driver.target_before
            assert driver.writes == [] and driver.convergence == []
            assert await driver.world.binding(driver.caller) == driver.before_binding

    @pytest.mark.asyncio
    async def test_reclaim_after_real_preflight_refuses_before_atomic_write(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent) as driver:
            driver.hold_inspect = True
            task = asyncio.create_task(driver.apply())
            try:
                await asyncio.wait_for(driver.before_effect.entered.wait(), 3)
                kw = driver.replays[-1][1]
                old = kw["claimed_receipt"]
                driver.clock.advance(max(0, int((old.lease_expires_at - driver.utc_now()).total_seconds() * 1000)) + 1)
                models = required("scribe_mcp.background.models", "BackgroundPartitionV1", "BackgroundTransitionOutcomeV1")
                higher = await kw["store"].claim(models.BackgroundPartitionV1(old.canonical_project_key, old.lane),
                    "replacement-worker", 1000)
                assert higher is not None and higher.fencing_token > old.fencing_token
                driver.before_effect.release.set()
                await asyncio.wait_for(driver.refusal_events.setdefault(old.operation_id, asyncio.Event()).wait(), 3)
                assert (old.operation_id, "SCRIBE_STALE_FENCE") in driver.replay_errors
                assert driver.writes == [] and driver.path.read_bytes() == driver.target_before
                assert await kw["store"].get(old.operation_id) == higher
                await kw["store"].transition(higher.operation_id, higher.state_version, higher.fencing_token,
                    models.BackgroundTransitionOutcomeV1("cancelled"))
            finally:
                driver.before_effect.release.set()
                await clean_tasks([task])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("after_commit", [False, True])
    async def test_cancellation_before_effect_and_after_commit_has_durable_closed_truth(
        self, tmp_path, monkeypatch, test_agent, after_commit
    ):
        async with document_world(tmp_path, monkeypatch, test_agent) as driver:
            if not after_commit:
                driver.hold_inspect = True
            else:
                driver.hold_after_write = True
            result_task = asyncio.create_task(driver.apply())
            try:
                if after_commit:
                    await asyncio.wait_for(driver.after_write.entered.wait(), 3)
                    operation = driver.replays[-1][1]["operation_id"]
                    assert len(driver.writes) == 1
                    terminal = await driver.service.get_status(operation)
                    assert terminal.state == "leased"
                else:
                    await asyncio.wait_for(driver.before_effect.entered.wait(), 3)
                    operation = driver.replays[-1][1]["operation_id"]
                    terminal = await driver.service.get_status(operation)
                await driver.service.cancel(operation, expected_state_version=terminal.state_version)
                driver.before_effect.release.set()
                driver.after_write.release.set()
                terminal = await driver.wait_terminal(operation)
                if after_commit:
                    assert terminal.state == "succeeded"
                    assert len(driver.writes) == 1
                else:
                    assert terminal.state == "cancelled"
                    assert driver.writes == [] and driver.path.read_bytes() == driver.target_before
                current = receipt(await driver.apply())
                assert current["state"] == ("applied" if after_commit else "cancelled")
                assert current["operation_id"] == operation
                assert len(driver.writes) == int(after_commit)
                await driver.restart()
                repeated = receipt(await driver.apply())
                assert repeated["state"] == ("applied" if after_commit else "cancelled")
                assert repeated["operation_id"] == operation
                assert len(driver.writes) == int(after_commit)
            finally:
                driver.before_effect.release.set()
                driver.after_write.release.set()
                await clean_tasks([result_task])

    @pytest.mark.asyncio
    async def test_failed_terminal_readback_cannot_execute_after_restart(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent) as driver:
            driver.hold_capture = True
            task = asyncio.create_task(driver.apply())
            try:
                await asyncio.wait_for(driver.capture_hold.entered.wait(), 3)
                kw = driver.replays[-1][1]
                claimed = kw["claimed_receipt"]
                models = required("scribe_mcp.background.models", "BackgroundTransitionOutcomeV1")
                terminal = await kw["store"].transition(claimed.operation_id, claimed.state_version,
                    claimed.fencing_token, models.BackgroundTransitionOutcomeV1(
                        "failed_terminal", error_code="SCRIBE_DOCUMENT_GENERATION_STALE"))
                assert terminal.state == "failed_terminal"
                driver.capture_hold.release.set()
                await asyncio.wait_for(task, 3)
                first = receipt(await driver.apply())
                assert first["state"] == "terminal_error"
                assert driver.writes == [] and driver.path.read_bytes() == driver.target_before
                driver.hold_capture = False
                await driver.restart()
                second = receipt(await driver.apply())
                assert second["operation_id"] == first["operation_id"] == claimed.operation_id
                assert second["state"] == "terminal_error"
                assert driver.writes == [] and driver.path.read_bytes() == driver.target_before
            finally:
                driver.capture_hold.release.set()
                await clean_tasks([task])

    @pytest.mark.asyncio
    async def test_concurrent_and_repeated_public_replay_has_one_generation_and_effect(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent) as driver:
            results = await asyncio.wait_for(asyncio.gather(driver.apply(), driver.apply()), 3)
            rows = [receipt(result) for result in results]
            assert len({row["operation_id"] for row in rows}) == 1
            operation = rows[0]["operation_id"]
            await driver.assert_applied_once(operation)
            for _ in range(3):
                replay = receipt(await driver.apply())
                assert replay["operation_id"] == operation and replay["state"] in {"applied", "duplicate"}
            assert len(driver.writes) == 1


    @pytest.mark.asyncio
    async def test_two_actual_replay_attempts_overlap_and_only_current_fence_commits(self, tmp_path, monkeypatch, test_agent):
        async with document_world(tmp_path, monkeypatch, test_agent, workers=2) as driver:
            assert (await driver.service.health_snapshot()).workers_active == 2
            old_gate, current_gate = CausalGate(), CausalGate()
            driver.race_gates = (old_gate, current_gate)
            admission = asyncio.create_task(driver.apply())
            try:
                await asyncio.wait_for(old_gate.entered.wait(), 3)
                old_task, old, inspected = driver.race_attempts[0]
                claimed = old["claimed_receipt"]
                operation = claimed.operation_id
                assert claimed.state == "leased" and not old_task.done()
                driver.clock.advance(max(0, int((claimed.lease_expires_at - driver.utc_now()).total_seconds() * 1000)) + 1)
                await asyncio.wait_for(driver.race_arrived[1].wait(), 3)
                current_task, current = driver.race_entries[1]
                assert old_task is not current_task and not old_task.done() and not current_task.done()
                assert old["operation_id"] == current["operation_id"] == operation
                assert current["claimed_receipt"].state == "leased"
                assert current["claimed_receipt"].fencing_token > claimed.fencing_token
                assert await current["store"].get(operation) == current["claimed_receipt"]
                assert current["request_context"] is not old["request_context"]
                assert current["execution_context"].resolved_request_context is current["request_context"]
                assert old["execution_context"].resolved_request_context is old["request_context"]
                assert current["cancellation"] is not old["cancellation"]
                # Both genuine helper calls are now in progress. Let the old
                # preflight finish first: a correct per-operation lock may
                # serialize inspection, while the higher claim already fences
                # the old attempt. No lock implementation is prescribed here.
                old_gate.release.set()
                await asyncio.wait_for(driver.refusal_events.setdefault(operation, asyncio.Event()).wait(), 3)
                assert driver.replay_errors == [(operation, "SCRIBE_STALE_FENCE")]
                assert driver.writes == []
                await asyncio.wait_for(current_gate.entered.wait(), 3)
                current_gate.release.set()
                final_document = await driver.assert_applied_once(operation)
                final_receipt = await current["store"].get(operation)
                assert len(driver.race_attempts) == 2
                assert len([row for row in driver.replayed if row.operation_id == operation and row.state == "applied"]) == 1
                assert await current["store"].get(operation) == final_receipt
                assert final_receipt.state == "succeeded"
                assert final_document.document_generation_after == final_document.document_generation_before + 1
                assert len(driver.writes) == 1
                repeated = receipt(await driver.apply())
                assert repeated["operation_id"] == operation and repeated["state"] in {"applied", "duplicate"}
                assert len(driver.writes) == 1
            finally:
                old_gate.release.set()
                current_gate.release.set()
                await clean_tasks([admission])


class TestSBRDocumentConvergence:
    def test_required_contract_is_present(self):
        document_contract()
        required("scribe_mcp.doc_management.runtime", "auto_register_document", "_handle_quality_check")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stage", ["registration", "index", "quality"])
    async def test_pending_convergence_reopens_to_current_generation_without_second_write(
        self, tmp_path, monkeypatch, test_agent, stage
    ):
        async with document_world(tmp_path, monkeypatch, test_agent, fault="outage_" + stage, indexed=True) as driver:
            first = receipt(await driver.apply())
            operation = first["operation_id"]
            await asyncio.wait_for(driver.fault_reached.wait(), 3)
            await asyncio.wait_for(driver.result_events.setdefault(operation, asyncio.Event()).wait(), 3)
            assert len(driver.writes) == 1
            pending = [row for row in driver.replayed if row.operation_id == operation]
            assert pending and pending[-1].state == "accepted" and pending[-1].queued_offline
            assert not driver.replays[-1][1]["wal"].has_commit(operation)
            await driver.restart()
            row = await driver.assert_applied_once(operation)
            evidence = [item for item in driver.convergence if item[1].operation_id == operation]
            assert evidence[-1][2] == {"registration": "converged", "index": "converged", "quality": "evaluated"}
            current_digest = hashlib.sha256(driver.path.read_bytes()).hexdigest()
            assert row.content_digest_after == evidence[-1][3] == current_digest
            assert any(item[1] == "quality" and item[2] == current_digest for item in driver.stage_calls)
            evaluated = driver.quality_evaluations[-1]
            assert evaluated["digest"] == current_digest
            assert evaluated["generation"] == row.document_generation_after
            assert evaluated["result"]["ok"] is True
            registered = await driver.world.storage.fetch_project(driver.caller.default.name,
                repo_root=str(driver.caller.default.root))
            docs = json.loads(registered.docs_json)
            assert sum(str(value) == str(driver.path) for value in docs.values()) == 1
            indexes = [path for path in driver.path.parent.glob("*.md") if path != driver.path and "INDEX" in path.name.upper()]
            assert indexes
            assert sum(text.count(driver.path.name) for text in (path.read_text() for path in indexes)) == 1
            registered_observations = [current_digest for value in docs.values() if str(value) == str(driver.path)]
            index_observations = [current_digest for index in indexes
                for line in index.read_text().splitlines() if driver.path.name in line]
            quality_observations = [evaluated["digest"]]
            expected, actual = document_ledger(driver, row, registration=registered_observations,
                indexes=index_observations, quality=quality_observations)
            metadata = document_metadata(driver, row)
            assert reconcile_exact_effects(expected, actual, metadata=metadata).verdict == "PASS"
            for kind in ("missing-registration", "duplicate-index", "stale-quality"):
                corrupted = list(actual)
                if kind == "missing-registration":
                    corrupted = [item for item in corrupted if item.effect != "registration"]
                elif kind == "duplicate-index":
                    corrupted.append(next(item for item in actual if item.effect == "index"))
                else:
                    corrupted = [replace(item, mutation_fingerprint="0" * 64) if item.effect == "quality" else item for item in corrupted]
                assert reconcile_exact_effects(expected, corrupted, metadata=metadata).verdict == "FAIL"
            # Run the actual quality delegate again with its captured genuine
            # inputs. Corrupting what its real evaluator consumes must be
            # refused before a current-digest observation enters C14.
            args, kwargs = driver.quality_calls[-1]
            before_quality = len(driver.quality_evaluations)
            for fault in ("wrong-target", "stale-content"):
                driver.quality_fault = fault
                try:
                    with pytest.raises(AssertionError, match="quality (wrong|stale)"):
                        await driver.runtime._handle_quality_check(*args, **kwargs)
                    assert len(driver.quality_evaluations) == before_quality
                finally:
                    driver.quality_fault = None
            before = driver.path.read_bytes(), len(driver.writes)
            await driver.apply()
            assert (driver.path.read_bytes(), len(driver.writes)) == before


# Frozen original CORE-VAL.3 selectors compose the substantive stage matrix.
@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["offline", "after_replace", "before_commit", "before_success", "before_response"])
async def test_crash_windows_replay_each_accepted_effect_exactly_once(tmp_path, monkeypatch, test_agent, fault):
    await TestSBRDocumentReplay().test_all_durable_crash_windows_reopen_and_apply_once(tmp_path, monkeypatch, test_agent, fault)


@pytest.mark.asyncio
async def test_concurrent_and_repeated_replayers_do_not_duplicate_effects(tmp_path, monkeypatch, test_agent):
    await TestSBRDocumentReplay().test_two_actual_replay_attempts_overlap_and_only_current_fence_commits(tmp_path, monkeypatch, test_agent)


def test_truncated_tail_and_one_project_failure_are_isolated(tmp_path):
    broken, peer = tmp_path / "broken", tmp_path / "peer"
    broken.mkdir()
    peer.mkdir()
    wal = journal(broken)
    wal.write_entry(retained_row(broken), entry_id="broken")
    with wal.journal_path.open("a") as stream:
        stream.write('{"truncated":')
    with pytest.raises(wal_contract().WalJournalCorruptError):
        wal.read_uncommitted()
    other = journal(peer, "progress.log")
    other.write_entry({"op": "append", "content": "peer-progress\n"}, entry_id="peer")
    assert other.replay_uncommitted() == 1
    assert other.replay_uncommitted() == 0
    assert (peer / "progress.log").read_text() == "peer-progress\n"


@pytest.mark.asyncio
async def test_offline_admission_and_runtime_reconstruction_preserve_receipts(tmp_path, monkeypatch, test_agent):
    await TestSBRDocumentReplay().test_all_durable_crash_windows_reopen_and_apply_once(tmp_path, monkeypatch, test_agent, "offline")


@pytest.mark.asyncio
@pytest.mark.parametrize("case,code", [("binding", "SCRIBE_BINDING_GENERATION_STALE"),
    ("document_generation", "SCRIBE_DOCUMENT_GENERATION_STALE"), ("digest", "SCRIBE_DOCUMENT_GENERATION_STALE"),
    ("root", "SCRIBE_PROJECT_ROOT_MISMATCH"), ("target", "SCRIBE_PROJECT_ROOT_MISMATCH"),
    ("path", "SCRIBE_PROJECT_ROOT_MISMATCH"),
    ("revoked", "SCRIBE_CALLER_SESSION_UNVERIFIED"), ("fence", "SCRIBE_STALE_FENCE"), ("unclaimed", "SCRIBE_STALE_FENCE")])
async def test_document_replay_revalidates_target_generations_digests_and_anchor(tmp_path, monkeypatch, test_agent, case, code):
    await TestSBRDocumentReplay().test_replay_refuses_current_identity_generation_digest_and_fence_drift(
        tmp_path, monkeypatch, test_agent, case, code)


@pytest.mark.asyncio
@pytest.mark.parametrize("after_commit", [False, True])
async def test_replay_cancellation_and_terminal_states_are_cardinality_clean(tmp_path, monkeypatch, test_agent, after_commit):
    await TestSBRDocumentReplay().test_cancellation_before_effect_and_after_commit_has_durable_closed_truth(
        tmp_path, monkeypatch, test_agent, after_commit)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["registration", "index", "quality"])
async def test_registration_index_and_quality_converge_once_after_replay(tmp_path, monkeypatch, test_agent, stage):
    await TestSBRDocumentConvergence().test_pending_convergence_reopens_to_current_generation_without_second_write(
        tmp_path, monkeypatch, test_agent, stage)
