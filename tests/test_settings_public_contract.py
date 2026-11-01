from __future__ import annotations

import scribe_mcp.config.settings as settings_module


def test_public_storage_modes_publish_the_three_release_modes() -> None:
    assert settings_module.PUBLIC_STORAGE_MODES == (
        "sqlite",
        "postgres",
    )
    assert settings_module.NON_RELEASE_STORAGE_MODES == ("remote/client",)


def test_public_storage_contract_labels_runtime_aliases_and_bootstrap_envs() -> None:
    contract = settings_module.PUBLIC_STORAGE_SETTINGS_BY_NAME

    assert contract["SCRIBE_DB_PATH"].classification == "canonical"
    assert contract["SCRIBE_SQLITE_PATH"].classification == "compatibility"
    assert contract["SCRIBE_SQLITE_PATH"].canonical_name == "SCRIBE_DB_PATH"
    assert contract["SCRIBE_DB_SCHEMA"].classification == "compatibility"
    assert contract["SCRIBE_DB_SCHEMA"].canonical_name == "SCRIBE_POSTGRES_SCHEMA"

    assert contract["SCRIBE_POSTGRES_POOL_MAX_SIZE"].classification == "advanced/public"
    assert contract["SCRIBE_REMOTE_URL"].classification == "canonical"
    assert contract["SCRIBE_REMOTE_FALLBACK"].classification == "advanced/non-release"
    assert contract["SCRIBE_RELEASE_PROFILE"].classification == "canonical"

    assert contract["SCRIBE_POSTGRES_ADMIN_*"].scope == "bootstrap-only"
    assert contract["SCRIBE_POSTGRES_APP_*"].scope == "bootstrap-only"
    assert contract["SCRIBE_POSTGRES_SUPERUSER_*"].scope == "bootstrap-only"


# SBR-BG-HOST-FIXTURE.1: pure settings contract, architecture 628e0f08 §4.
# Keep the inherited public-contract assertions above byte-for-byte intact.
import copy
import json
import os
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest


# Produced by storage.models.compute_project_key for root /sbr-config-fixture,
# names alpha/beta; legacy key uses name legacy and row_id=7. Literal samples
# keep test collection independent of storage imports or identity resolution.
_SBR_PROJECT_KEY_A = "pk_f7259af8e4597d5d3234765a34c4863f9237a21fec20b73a84cc3a88af29a030"
_SBR_PROJECT_KEY_B = "pk_ca7bb43eddd37835f760afcdd3d5d5787c72406c4498c4ddbe42f16b4857749f"
_SBR_LEGACY_PROJECT_KEY = "pk_legacy_a8d201bac83d4cb8919af02f26b7baae134aaad8f1baffc7d254bf3122ec1c77"
_SBR_WEIGHT_PROFILE = {_SBR_LEGACY_PROJECT_KEY: 5, _SBR_PROJECT_KEY_A: 2, _SBR_PROJECT_KEY_B: 3}


# Input path, frozen DTO path, documented default, independent valid override,
# minimum integer (None denotes the signed seed; weights are a separate shape).
_SBR_CONFIG_LEAVES = (
    ("queue.max_pending_items", "queue_limits.max_pending_items", 256, 512, 1),
    ("queue.max_pending_bytes", "queue_limits.max_pending_bytes", 16777216, 33554432, 1),
    ("queue.max_project_pending_items", "queue_limits.max_project_pending_items", 64, 128, 1),
    ("queue.max_project_pending_bytes", "queue_limits.max_project_pending_bytes", 4194304, 8388608, 1),
    ("queue.retry_after_ms", "queue_limits.retry_after_ms", 100, 75, 1),
    ("scheduler.global_concurrency", "scheduler.global_concurrency", 4, 3, 1),
    ("scheduler.max_project_concurrency", "scheduler.max_project_concurrency", 1, 2, 1),
    ("scheduler.control_reserved_slots", "scheduler.control_reserved_slots", 1, 0, 0),
    ("scheduler.durable_reserved_slots", "scheduler.durable_reserved_slots", 1, 0, 0),
    ("scheduler.control_quantum", "scheduler.control_quantum", 1, 2, 1),
    ("scheduler.durable_quantum", "scheduler.durable_quantum", 1, 3, 1),
    ("scheduler.heavy_quantum", "scheduler.heavy_quantum", 1, 4, 1),
    ("scheduler.payload_quantum_bytes", "scheduler.payload_quantum_bytes", 65536, 32768, 1),
    ("scheduler.project_weights", "scheduler.project_weights", {}, _SBR_WEIGHT_PROFILE, None),
    ("worker_count", "worker_count", 4, 6, 1),
    ("lease_ms", "lease_ms", 30000, 45000, 1),
    ("retry.max_attempts", "retry_policy.max_attempts", 5, 7, 1),
    ("retry.base_delay_ms", "retry_policy.base_delay_ms", 100, 0, 0),
    ("retry.max_delay_ms", "retry_policy.max_delay_ms", 5000, 9000, 0),
    ("retry.jitter_ms", "retry_policy.jitter_ms", 100, 0, 0),
    ("retry.seed", "retry_policy.seed", 0, -17, None),
    ("drain_deadline_ms", "drain_deadline_ms", 2000, 750, 1),
)
_SBR_INTEGER_LEAVES = tuple(row for row in _SBR_CONFIG_LEAVES if row[0] != "scheduler.project_weights")
_SBR_BAD_SCALARS = (
    pytest.param(True, id="bool-true"),
    pytest.param(False, id="bool-false"),
    pytest.param("forbidden-sensitive-value", id="string"),
    pytest.param(1.0, id="integral-float"),
    pytest.param(1.5, id="fractional-float"),
    pytest.param(None, id="null"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param([], id="array"),
    pytest.param({}, id="object"),
)


def _sbr_required_builder():
    builder = getattr(settings_module, "build_background_service_config", None)
    assert callable(builder), (
        "required production symbol missing: "
        "scribe_mcp.config.settings.build_background_service_config"
    )
    return builder


def _sbr_put(mapping, path, value):
    parts = path.split(".")
    target = mapping
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _sbr_snapshot(config):
    result = {}
    for path, target, *_ in _SBR_CONFIG_LEAVES:
        value = config
        for attribute in target.split("."):
            value = getattr(value, attribute)
        result[path] = value
    return result


def _sbr_assert_config(config, overrides=None):
    from scribe_mcp.background.models import BackgroundQueueLimitsV1
    from scribe_mcp.background.scheduler import BackgroundSchedulerConfigV1
    from scribe_mcp.background.service import BackgroundServiceConfigV1
    from scribe_mcp.background.worker import SeededRetryPolicyV1

    assert isinstance(config, BackgroundServiceConfigV1)
    assert isinstance(config.queue_limits, BackgroundQueueLimitsV1)
    assert isinstance(config.scheduler, BackgroundSchedulerConfigV1)
    assert isinstance(config.retry_policy, SeededRetryPolicyV1)
    expected = {path: default for path, _, default, *_ in _SBR_CONFIG_LEAVES}
    expected.update(overrides or {})
    expected["scheduler.project_weights"] = tuple(sorted(expected["scheduler.project_weights"].items()))
    assert _sbr_snapshot(config) == expected


def _sbr_load(monkeypatch, options):
    monkeypatch.setenv("SCRIBE_EXTRA_OPTIONS", json.dumps(options))
    return settings_module.Settings.load()


def _sbr_reject(builder, loaded):
    # The architecture specifies the bounded code, not an invented exception
    # class. A generic import/setup/type error cannot satisfy this oracle.
    with pytest.raises(Exception, match=r"\bBACKGROUND_CONFIG_INVALID\b") as caught:
        builder(loaded)
    assert not isinstance(caught.value, (ImportError, AttributeError, TypeError))
    assert "forbidden-sensitive-value" not in str(caught.value)


@pytest.mark.core
@pytest.mark.storage
@pytest.mark.usefixtures("test_agent")
class TestSBRHostCompositionConfig:
    @pytest.fixture(autouse=True)
    def isolated_settings_environment(self, monkeypatch, tmp_path):
        # Clear only the process-local monkeypatch context, restored per case.
        for name in tuple(os.environ):
            if name.startswith("SCRIBE_"):
                monkeypatch.delenv(name)
        monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
        monkeypatch.setenv("SCRIBE_MODE", "standalone")
        monkeypatch.setenv("SCRIBE_STORAGE_BACKEND", "sqlite")
        monkeypatch.setenv("SCRIBE_DISABLE_DOTENV", "1")

    @pytest.mark.parametrize("raw", [None, "", "{}", '{"background_job_service": {}}'], ids=["absent", "empty", "empty-extra", "empty-namespace"])
    def test_missing_and_empty_use_all_documented_defaults(self, monkeypatch, raw):
        builder = _sbr_required_builder()
        if raw is not None:
            monkeypatch.setenv("SCRIBE_EXTRA_OPTIONS", raw)
        loaded = settings_module.Settings.load()
        _sbr_assert_config(builder(loaded))

    @pytest.mark.parametrize("row", _SBR_CONFIG_LEAVES, ids=[row[0] for row in _SBR_CONFIG_LEAVES])
    def test_each_partial_override_maps_one_leaf_and_preserves_other_defaults(self, monkeypatch, row):
        builder = _sbr_required_builder()
        path, _, _, override, _ = row
        namespace = {}
        _sbr_put(namespace, path, override)
        loaded = _sbr_load(monkeypatch, {"background_job_service": namespace})
        original = copy.deepcopy(loaded.extra_options)
        _sbr_assert_config(builder(loaded), {path: override})
        assert loaded.extra_options == original

    def test_complete_profile_maps_every_leaf_without_mutating_input(self, monkeypatch):
        builder = _sbr_required_builder()
        namespace = {}
        overrides = {}
        for path, _, _, override, _ in _SBR_CONFIG_LEAVES:
            _sbr_put(namespace, path, override)
            overrides[path] = override
        loaded = _sbr_load(monkeypatch, {"background_job_service": namespace, "unrelated": {"flag": True}})
        original = copy.deepcopy(loaded.extra_options)
        _sbr_assert_config(builder(loaded), overrides)
        assert loaded.extra_options == original

    @pytest.mark.parametrize("row", _SBR_INTEGER_LEAVES, ids=[row[0] for row in _SBR_INTEGER_LEAVES])
    @pytest.mark.parametrize("bad", _SBR_BAD_SCALARS)
    def test_each_integer_leaf_rejects_wrong_types_and_nonfinite_values(self, monkeypatch, row, bad):
        builder = _sbr_required_builder()
        namespace = {}
        _sbr_put(namespace, row[0], bad)
        _sbr_reject(builder, _sbr_load(monkeypatch, {"background_job_service": namespace}))

    @pytest.mark.parametrize("row", [row for row in _SBR_INTEGER_LEAVES if row[4] is not None], ids=[row[0] for row in _SBR_INTEGER_LEAVES if row[4] is not None])
    def test_each_integer_leaf_rejects_value_below_its_minimum(self, monkeypatch, row):
        builder = _sbr_required_builder()
        namespace = {}
        _sbr_put(namespace, row[0], row[4] - 1)
        _sbr_reject(builder, _sbr_load(monkeypatch, {"background_job_service": namespace}))

    @pytest.mark.parametrize("path", ["retry.max_delay_ms", "retry.seed"])
    def test_zero_is_valid_for_nonnegative_leaves_and_seed(self, monkeypatch, path):
        builder = _sbr_required_builder()
        namespace = {}
        overrides = {path: 0}
        if path == "retry.max_delay_ms":
            overrides["retry.base_delay_ms"] = 0
        for name, value in overrides.items():
            _sbr_put(namespace, name, value)
        _sbr_assert_config(builder(_sbr_load(monkeypatch, {"background_job_service": namespace})), overrides)

    @pytest.mark.parametrize("path", ["queue.max_pending_items", "queue.max_pending_bytes", "scheduler.global_concurrency", "scheduler.max_project_concurrency", "worker_count", "retry.base_delay_ms"])
    def test_cross_field_invalid_profile_reports_bounded_config_error(self, monkeypatch, path):
        builder = _sbr_required_builder()
        values = {"queue.max_pending_items": 63, "queue.max_pending_bytes": 4194303,
                  "scheduler.global_concurrency": 2, "scheduler.max_project_concurrency": 5,
                  "worker_count": 3, "retry.base_delay_ms": 5001}
        namespace = {}
        _sbr_put(namespace, path, values[path])
        _sbr_reject(builder, _sbr_load(monkeypatch, {"background_job_service": namespace}))

    @pytest.mark.parametrize("reserves", [(2, 2), (3, 2)], ids=["no-heavy-slot", "over-global"])
    def test_reserve_sum_must_leave_a_heavy_slot(self, monkeypatch, reserves):
        builder = _sbr_required_builder()
        namespace = {"scheduler": {"control_reserved_slots": reserves[0], "durable_reserved_slots": reserves[1]}}
        _sbr_reject(builder, _sbr_load(monkeypatch, {"background_job_service": namespace}))

    def test_minimal_valid_profile_accepts_all_integer_lower_boundaries(self, monkeypatch):
        builder = _sbr_required_builder()
        overrides = {path: minimum if minimum is not None else 0 for path, _, _, _, minimum in _SBR_INTEGER_LEAVES}
        namespace = {}
        for path, value in overrides.items():
            _sbr_put(namespace, path, value)
        _sbr_assert_config(builder(_sbr_load(monkeypatch, {"background_job_service": namespace})), overrides)

    def test_equal_project_caps_worker_concurrency_and_backoff_are_valid(self, monkeypatch):
        builder = _sbr_required_builder()
        overrides = {"queue.max_project_pending_items": 256, "queue.max_project_pending_bytes": 16777216,
                     "scheduler.max_project_concurrency": 4, "retry.base_delay_ms": 5000}
        namespace = {}
        for path, value in overrides.items():
            _sbr_put(namespace, path, value)
        _sbr_assert_config(builder(_sbr_load(monkeypatch, {"background_job_service": namespace})), overrides)

    @pytest.mark.parametrize("namespace", [
        {"queue": {"accepting": False}}, {"enabled": False},
        {"handler": "forbidden-sensitive-value"}, {"handler_path": "forbidden-sensitive-value"},
        {"provider_policy": {}}, {"shutdown_budget_ms": 1}, {"unknown": 1},
        {"queue": {"unknown": 1}}, {"scheduler": {"unknown": 1}}, {"retry": {"unknown": 1}},
    ], ids=["lifecycle-admission", "disabled", "handler", "handler-path", "provider-policy", "shutdown-budget", "unknown-top", "unknown-queue", "unknown-scheduler", "unknown-retry"])
    def test_unknown_or_runtime_policy_keys_cannot_override_composition(self, monkeypatch, namespace):
        builder = _sbr_required_builder()
        _sbr_reject(builder, _sbr_load(monkeypatch, {"background_job_service": namespace}))

    @pytest.mark.parametrize("section", [None, "queue", "scheduler", "retry"])
    @pytest.mark.parametrize("bad", [None, [], "forbidden-sensitive-value", True, 1, 1.5])
    def test_namespace_and_sections_must_be_objects(self, monkeypatch, section, bad):
        builder = _sbr_required_builder()
        namespace = bad if section is None else {section: bad}
        _sbr_reject(builder, _sbr_load(monkeypatch, {"background_job_service": namespace}))

    @pytest.mark.parametrize("bad", [None, [], [[_SBR_PROJECT_KEY_A, 2]], "forbidden-sensitive-value", True, 1])
    def test_weights_require_json_object(self, monkeypatch, bad):
        builder = _sbr_required_builder()
        loaded = _sbr_load(monkeypatch, {"background_job_service": {"scheduler": {"project_weights": bad}}})
        _sbr_reject(builder, loaded)

    @pytest.mark.parametrize("bad", _SBR_BAD_SCALARS + (pytest.param(0, id="zero"), pytest.param(-1, id="negative")))
    def test_weights_require_positive_integer_values(self, monkeypatch, bad):
        builder = _sbr_required_builder()
        loaded = _sbr_load(monkeypatch, {"background_job_service": {"scheduler": {"project_weights": {_SBR_PROJECT_KEY_A: bad}}}})
        _sbr_reject(builder, loaded)

    @pytest.mark.parametrize("key", ["", " ", "\t\n", None, 17, True])
    def test_weights_reject_blank_and_nonstring_canonical_keys(self, monkeypatch, key):
        builder = _sbr_required_builder()
        loaded = _sbr_load(monkeypatch, {})
        # Non-string mapping keys cannot survive JSON; exercise direct Settings
        # input too, without pretending labels can be resolved as identities.
        loaded.extra_options["background_job_service"] = {"scheduler": {"project_weights": {key: 1}}}
        _sbr_reject(builder, loaded)

    @pytest.mark.parametrize("label", ["project:a", "project:z", "Human Project Label"], ids=["old-project-a", "old-project-z", "human-label"])
    def test_weights_reject_labels_instead_of_canonical_project_keys(self, monkeypatch, label):
        builder = _sbr_required_builder()
        loaded = _sbr_load(monkeypatch, {"background_job_service": {"scheduler": {"project_weights": {label: 1}}}})
        _sbr_reject(builder, loaded)

    def test_weights_are_sorted_copied_and_frozen_for_service_lifetime(self, monkeypatch):
        builder = _sbr_required_builder()
        weights = dict(_SBR_WEIGHT_PROFILE)
        loaded = _sbr_load(monkeypatch, {"background_job_service": {"scheduler": {"project_weights": weights}}})
        config = builder(loaded)
        _sbr_assert_config(config, {"scheduler.project_weights": weights})
        loaded.extra_options["background_job_service"]["scheduler"]["project_weights"][_SBR_PROJECT_KEY_A] = 99
        loaded.extra_options["background_job_service"]["scheduler"]["project_weights"].pop(_SBR_LEGACY_PROJECT_KEY)
        assert config.scheduler.project_weights == ((_SBR_PROJECT_KEY_B, 3), (_SBR_PROJECT_KEY_A, 2), (_SBR_LEGACY_PROJECT_KEY, 5))
        with pytest.raises((FrozenInstanceError, AttributeError)):
            config.scheduler.project_weights = ()

    @pytest.mark.parametrize("seed", [-17, 0, 42])
    def test_seed_mapping_and_repeated_builds_are_deterministic(self, monkeypatch, seed):
        builder = _sbr_required_builder()
        from scribe_mcp.background.models import DurableOperationReceiptV1

        loaded = _sbr_load(monkeypatch, {"background_job_service": {"retry": {"seed": seed}}})
        first, second = builder(loaded), builder(loaded)
        _sbr_assert_config(first, {"retry.seed": seed})
        assert _sbr_snapshot(first) == _sbr_snapshot(second)
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        receipt = DurableOperationReceiptV1(
            operation_id="operation:seed", canonical_project_key="project:seed",
            lane="durable", idempotency_key="idempotency:seed", payload_digest="a" * 64,
            payload_bytes=1, durability_class="durable", state="retry_wait",
            state_version=4, attempt_count=1, next_attempt_at=now,
            lease_owner=None, lease_expires_at=None, fencing_token=1,
            cancel_requested=False, result_ref=None, error_code=None,
            created_at=now, updated_at=now,
        )
        scheduled = first.retry_policy.next_attempt_at(receipt, now=now)
        assert scheduled == second.retry_policy.next_attempt_at(receipt, now=now)
        assert now + timedelta(milliseconds=100) <= scheduled <= now + timedelta(milliseconds=200)

    @pytest.mark.parametrize("raw", ["{", "forbidden-sensitive-value", "[]", "[1]", "null", "true", "false", "1", "1.5", '"forbidden-sensitive-value"', "NaN", "Infinity", "-Infinity", "   "])
    def test_malformed_or_nonobject_extra_options_retains_invalid_namespace(self, monkeypatch, raw):
        builder = _sbr_required_builder()
        monkeypatch.setenv("SCRIBE_EXTRA_OPTIONS", raw)
        loaded = settings_module.Settings.load()
        assert loaded.extra_options == {"background_job_service": None}
        _sbr_reject(builder, loaded)

    @pytest.mark.parametrize("raw", [None, "", "{", "[]", "null", "1", "true", '{"keep": {"nested": [1, 2]}}'])
    def test_other_loader_names_preserve_original_json_contract(self, monkeypatch, raw):
        if raw is not None:
            monkeypatch.setenv("SCRIBE_TEST_JSON_OPTIONS", raw)
        expected = {"keep": {"nested": [1, 2]}} if raw and raw.startswith('{"keep"') else {}
        assert settings_module._load_env_json("SCRIBE_TEST_JSON_OPTIONS") == expected

    def test_unrelated_extra_options_remain_unchanged(self, monkeypatch):
        options = {"other_consumer": {"array": [1, "two", None]}, "feature_flag": False}
        loaded = _sbr_load(monkeypatch, options)
        assert loaded.extra_options == options

    def test_callable_handler_option_is_rejected_without_execution(self, monkeypatch):
        builder = _sbr_required_builder()
        called = []

        def forbidden_handler():
            called.append(True)

        loaded = _sbr_load(monkeypatch, {})
        loaded.extra_options["background_job_service"] = {"handler": forbidden_handler}
        _sbr_reject(builder, loaded)
        assert called == []
