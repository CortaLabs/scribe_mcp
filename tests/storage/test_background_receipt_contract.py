"""C-08 models and fail-closed contract; backend behavior lives beside this file.

Future symbols are checked inside tests, so absent implementation is an explicit
contract failure, never a collection failure. Helpers construct inputs only.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_args

import pytest

pytestmark = [pytest.mark.core, pytest.mark.regression, pytest.mark.usefixtures("test_agent")]
EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
STATES = {"accepted", "ready", "leased", "retry_wait", "succeeded", "failed_terminal", "cancelled"}
METHODS = {
    "admit_background_receipt": ("self", "intent", "limits", "now"),
    "get_background_receipt": ("self", "operation_id"),
    "claim_background_receipt": ("self", "partition", "worker_id", "lease_ms", "now"),
    "transition_background_receipt": ("self", "operation_id", "expected_state_version", "fencing_token", "outcome", "now"),
    "recover_background_receipts": ("self", "now"),
}


def load_suite(relative_path):
    """Import the named owned test artifact without legacy storage shadowing."""
    path = Path(__file__).resolve().parents[1] / relative_path
    name = "_scribe_c08_" + path.stem
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def api():
    modules = []
    for name in ("scribe_mcp.background.models", "scribe_mcp.background.store"):
        assert importlib.util.find_spec(name) is not None, f"C-08 missing source boundary: {name}"
        module = importlib.import_module(name)
        assert Path(module.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[2] / "src"), module.__file__
        modules.append(module)
    models, store = modules
    for name in ("BackgroundOperationIntentV1", "BackgroundQueueLimitsV1", "DurableOperationReceiptV1",
                 "BackgroundAdmissionResultV1", "BackgroundPartitionV1", "BackgroundTransitionOutcomeV1",
                 "BackgroundRecoverySnapshotV1", "BackgroundReceiptNotFoundError",
                 "BackgroundStateVersionConflictError", "BackgroundStaleFenceError"):
        assert hasattr(models, name), f"C-08 missing models.{name}"
    assert hasattr(store, "BackgroundReceiptStoreV1"), "C-08 missing store.BackgroundReceiptStoreV1"
    return models, store.BackgroundReceiptStoreV1


def require_backend(backend_class):
    from scribe_mcp.storage.base import StorageBackend
    api()
    for name, expected in METHODS.items():
        method = getattr(backend_class, name, None)
        assert method is not None and method is not getattr(StorageBackend, name, None), (
            f"C-08 unimplemented source boundary: {backend_class.__name__}.{name}"
        )
        assert inspect.iscoroutinefunction(method), name
        assert tuple(inspect.signature(method).parameters) == expected, name
    return backend_class


def intent(models, operation_id="operation-0", *, project="project-a", size=8, lane="durable", now=EPOCH):
    return models.BackgroundOperationIntentV1(operation_id, project, lane, operation_id,
                                             "a" * 64, size, "local_durable", now)


def limits(models, **changes):
    values = dict(max_pending_items=64, max_pending_bytes=4096,
                  max_project_pending_items=64, max_project_pending_bytes=4096, retry_after_ms=25)
    values.update(changes)
    return models.BackgroundQueueLimitsV1(**values)


def receipt(models, **changes):
    values = dict(operation_id="operation-0", canonical_project_key="project-a", lane="durable",
                  idempotency_key="operation-0", payload_digest="a" * 64, payload_bytes=8,
                  durability_class="local_durable", state="accepted", state_version=1,
                  attempt_count=0, next_attempt_at=None, lease_owner=None, lease_expires_at=None,
                  fencing_token=0, cancel_requested=False, result_ref=None, error_code=None,
                  created_at=EPOCH, updated_at=EPOCH)
    values.update(changes)
    return models.DurableOperationReceiptV1(**values)


def wall_time(clock):
    """Adapt the one C-14 monotonic clock to C-08's aware datetime boundary."""
    return EPOCH + timedelta(seconds=clock.now())


class TestSBRReceiptContract:
    def test_required_contract_is_present(self):
        models, store = api()
        assert set(get_args(models.BackgroundReceiptState)) == STATES
        assert set(get_args(models.BackgroundLane)) == {"control", "durable", "heavy"}
        for name, parameters in {
            "__init__": ("self", "backend", "clock"), "admit": ("self", "intent", "limits"),
            "get": ("self", "operation_id"), "claim": ("self", "partition", "worker_id", "lease_ms"),
            "transition": ("self", "operation_id", "expected_state_version", "fencing_token", "outcome"),
            "recover": ("self", "now"),
        }.items():
            assert tuple(inspect.signature(getattr(store, name)).parameters) == parameters
        assert inspect.signature(store.__init__).parameters["clock"].kind is inspect.Parameter.KEYWORD_ONLY
        from scribe_mcp.storage.base import StorageBackend
        for name, parameters in METHODS.items():
            method = getattr(StorageBackend, name, None)
            assert method is not None, f"C-08 missing StorageBackend.{name}"
            assert inspect.iscoroutinefunction(method)
            signature = inspect.signature(method)
            assert tuple(signature.parameters) == parameters
            if "now" in parameters and name != "recover_background_receipts":
                assert signature.parameters["now"].kind is inspect.Parameter.KEYWORD_ONLY

    def test_closed_transition_matrix_and_dataclass_fields(self):
        models, _ = api()
        assert models.BACKGROUND_LEGAL_TRANSITIONS == {
            "accepted": frozenset({"ready", "cancelled"}),
            "ready": frozenset({"leased", "cancelled"}),
            "leased": frozenset({"retry_wait", "succeeded", "failed_terminal", "cancelled"}),
            "retry_wait": frozenset({"leased", "cancelled"}),
            "succeeded": frozenset(), "failed_terminal": frozenset(), "cancelled": frozenset(),
        }
        assert tuple(field.name for field in fields(models.DurableOperationReceiptV1)) == (
            "operation_id", "canonical_project_key", "lane", "idempotency_key", "payload_digest",
            "payload_bytes", "durability_class", "state", "state_version", "attempt_count",
            "next_attempt_at", "lease_owner", "lease_expires_at", "fencing_token", "cancel_requested",
            "result_ref", "error_code", "created_at", "updated_at")
        values = (intent(models), limits(models), receipt(models), models.BackgroundPartitionV1("project-a", "durable"),
                  models.BackgroundTransitionOutcomeV1("ready"),
                  models.BackgroundAdmissionResultV1("accepted", receipt(models), None),
                  models.BackgroundRecoverySnapshotV1((receipt(models),), 1, 8, ()))
        for value in values:
            assert value.__dataclass_params__.frozen
            with pytest.raises(FrozenInstanceError):
                setattr(value, fields(value)[0].name, None)

    @pytest.mark.parametrize("field,value", [
        ("operation_id", ""), ("canonical_project_key", ""), ("idempotency_key", ""),
        ("durability_class", ""), ("lane", "unknown"), ("payload_digest", "A" * 64),
        ("payload_digest", "g" * 64), ("payload_digest", "a" * 63),
        ("payload_bytes", -1), ("payload_bytes", True), ("created_at", datetime(2026, 1, 1)),
    ])
    def test_intent_rejects_invalid_identifiers_digest_bytes_and_time(self, field, value):
        models, _ = api()
        with pytest.raises(ValueError):
            replace(intent(models), **{field: value})

    @pytest.mark.parametrize("field", ["max_pending_items", "max_pending_bytes", "max_project_pending_items",
                                       "max_project_pending_bytes", "retry_after_ms"])
    @pytest.mark.parametrize("value", [0, -1, True])
    def test_limits_are_positive_integers(self, field, value):
        models, _ = api()
        with pytest.raises(ValueError):
            limits(models, **{field: value})

    @pytest.mark.parametrize("changes", [
        {"state": "unknown"}, {"state_version": 0}, {"attempt_count": -1}, {"fencing_token": -1},
        {"cancel_requested": 1}, {"updated_at": EPOCH - timedelta(seconds=1)},
        {"updated_at": datetime(2026, 1, 1)}, {"lease_owner": "worker"},
        {"result_ref": "unexpected"}, {"error_code": "unexpected"},
        {"state": "leased", "state_version": 3, "attempt_count": 1, "fencing_token": 1},
        {"state": "retry_wait", "state_version": 4, "attempt_count": 1, "fencing_token": 1},
        {"state": "succeeded", "state_version": 4, "attempt_count": 1, "fencing_token": 1},
        {"state": "failed_terminal", "state_version": 4, "attempt_count": 1, "fencing_token": 1},
    ])
    def test_receipt_rejects_impossible_state_combinations(self, changes):
        models, _ = api()
        with pytest.raises(ValueError):
            receipt(models, **changes)

    @pytest.mark.parametrize("state,changes", [
        ("accepted", {}), ("leased", {}), ("retry_wait", {}), ("succeeded", {}),
        ("failed_terminal", {}), ("ready", {"result_ref": "invalid"}),
        ("cancelled", {"next_attempt_at": EPOCH}),
    ])
    def test_outcomes_cannot_bypass_claim_or_terminal_field_rules(self, state, changes):
        models, _ = api()
        with pytest.raises(ValueError):
            models.BackgroundTransitionOutcomeV1(state, **changes)

    @pytest.mark.parametrize("status,has_receipt,delay", [
        ("accepted", False, None), ("duplicate", False, None), ("busy", False, None),
        ("busy", True, 25), ("digest_conflict", True, None), ("shutting_down", False, 25),
        ("untyped", False, None),
    ])
    def test_admission_outcome_shape_is_closed(self, status, has_receipt, delay):
        models, _ = api()
        with pytest.raises(ValueError):
            models.BackgroundAdmissionResultV1(status, receipt(models) if has_receipt else None, delay)

    @pytest.mark.parametrize("changes", [
        {"pending_items": 0}, {"pending_bytes": 9}, {"receipts": ()},
        {"receipts": "invalid"}, {"reclaimable_operation_ids": ("missing",)},
    ])
    def test_recovery_rejects_inconsistent_capacity_and_reclaimability(self, changes):
        models, _ = api()
        values = dict(receipts=(receipt(models),), pending_items=1, pending_bytes=8, reclaimable_operation_ids=())
        values.update(changes)
        with pytest.raises(ValueError):
            models.BackgroundRecoverySnapshotV1(**values)

    @pytest.mark.asyncio
    async def test_unsupported_backend_defaults_fail_closed_without_persistence(self, tmp_path, test_agent):
        from scribe_mcp.storage.base import StorageBackend
        from scribe_mcp.storage.sqlite import SQLiteStorage
        models, _ = api()
        backend = SQLiteStorage(tmp_path / "must-not-be-created.db")
        calls = [("admit_background_receipt", (intent(models), limits(models)), {"now": EPOCH}),
                 ("get_background_receipt", ("missing",), {}),
                 ("claim_background_receipt", (models.BackgroundPartitionV1("project-a", "durable"), test_agent, 100), {"now": EPOCH}),
                 ("transition_background_receipt", ("missing", 1, 0, models.BackgroundTransitionOutcomeV1("ready")), {"now": EPOCH}),
                 ("recover_background_receipts", (EPOCH,), {})]
        for name, args, kwargs in calls:
            with pytest.raises(NotImplementedError, match="background receipt"):
                await getattr(StorageBackend, name)(backend, *args, **kwargs)
        assert not (tmp_path / "must-not-be-created.db").exists()

    @pytest.mark.asyncio
    async def test_facade_rejects_naive_clock_before_backend_access(self, tmp_path):
        from scribe_mcp.storage.sqlite import SQLiteStorage
        models, store_class = api()
        path = tmp_path / "must-not-be-created.db"
        store = store_class(SQLiteStorage(path), clock=lambda: datetime(2026, 1, 1))
        with pytest.raises(ValueError, match="timezone-aware"):
            await store.admit(intent(models), limits(models))
        assert not path.exists()
