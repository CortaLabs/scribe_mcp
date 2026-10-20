"""C07/C14 reference cases; collection never requires a future product symbol.

Only the explicit reference lane may execute PostgreSQL/process measurements.
Presence failures are source-availability RED, never performance evidence.
"""
from __future__ import annotations

import ast
import asyncio
import builtins
import hashlib
import importlib
import inspect
import json
import math
import multiprocessing
import os
import pickle
import re
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import MISSING, asdict, dataclass, fields, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

import pytest

# Import the canonical fixture owner, rather than relying on sibling discovery.
# The safe fixture is resolved only after the explicit source-presence assertion.
from integration.storage import conftest as postgres_fixtures
from fixtures.swarm import (
    CausalGate, ExpectedEffect, ManualClock, ObservedEffect, SwarmRunMetadata, SwarmResultsV1,
    build_mixed_schedule, build_swarm_topology, reconcile_exact_effects,
)

if hasattr(postgres_fixtures, "swarm_postgres_backend"):
    swarm_postgres_backend = postgres_fixtures.swarm_postgres_backend

pytestmark = [pytest.mark.regression, pytest.mark.usefixtures("test_agent")]
pytest_plugins = ("pytester",)
SEED = 20260927
REPO_ROOT = Path(__file__).resolve().parents[2]


def _required(module_name, *names):
    assert importlib.util.find_spec(module_name) is not None, f"Frozen contract absent: {module_name}"
    module = importlib.import_module(module_name)
    missing = [name for name in names if not hasattr(module, name)]
    assert not missing, f"Frozen contract absent: {module_name}: {', '.join(missing)}"
    return module


def _parameters(function, *names):
    missing = set(names) - inspect.signature(function).parameters.keys()
    assert not missing, f"Frozen contract absent: {function.__qualname__}: {sorted(missing)}"


def fixture_contract():
    missing = [name for name in ("validate_disposable_postgres_dsn", "swarm_postgres_backend", "SanitizedPostgresTarget",
                                "PostgresReferenceFixture") if not hasattr(postgres_fixtures, name)]
    assert not missing, f"Frozen contract absent: REL-VAL.1 canonical fixture: {', '.join(missing)}"
    _parameters(postgres_fixtures.validate_disposable_postgres_dsn, "dsn", "allow_hosts")
    fixture = postgres_fixtures.swarm_postgres_backend
    _parameters(fixture, "request", "tmp_path")
    _parameters(postgres_fixtures.PostgresReferenceFixture, "dsn", "database_name", "target", "postgres_version", "config_fingerprint", "cleanup")
    assert callable(getattr(postgres_fixtures.PostgresReferenceFixture, "as_environment_dict", None)), "Frozen contract absent: PostgresReferenceFixture.as_environment_dict"
    assert inspect.iscoroutinefunction(getattr(postgres_fixtures.PostgresReferenceFixture, "cleanup", None)), "Frozen contract absent: PostgresReferenceFixture.cleanup"
    return postgres_fixtures


def postgres_binding_contract():
    storage = _required("scribe_mcp.storage.postgres", "PostgresStorage").PostgresStorage
    _parameters(storage.set_session_project, "project_key", "expected_generation")
    return storage


def schema_contract():
    schema = _required("scribe_mcp.storage.postgres.schema", "SchemaReadinessV1", "ensure_schema_ready")
    _parameters(schema.ensure_schema_ready, "pool_provider", "schema_lock", "schema_name", "deadline_ms")
    storage = _required("scribe_mcp.storage.postgres", "PostgresStorage").PostgresStorage
    assert callable(getattr(storage, "ensure_schema_ready", None)), "Frozen contract absent: PostgresStorage.ensure_schema_ready"
    _parameters(storage.ensure_schema_ready, "deadline_ms")
    return storage, schema


def canonical_postgres(request):
    """Resolve the sole safe fixture; pytest owns its cache and finalizers."""
    fixture_contract()
    return request.getfixturevalue("swarm_postgres_backend")


def _pytest_postgres(preflight):
    """Resolve async fixtures before the scenario loop, after CALL-phase checks.

    Keeping preflight in the test call preserves explicit missing-source FAILs,
    rather than misclassifying them as fixture SETUP errors. The canonical
    fixture is resolved synchronously, so pytest-asyncio can run its setup loop.
    Scenarios use only its in-memory DSN/metadata, not its loop-owned handles.
    """
    def decorate(scenario):
        @wraps(scenario)
        def run(*args, **kwargs):
            preflight()
            fixture_contract()
            request = kwargs["request"]
            created = []
            def verify_pytest_cleanup():
                if created:
                    asyncio.run(_assert_database_gone(created[0]))
            # Registered before dynamic fixture setup: pytest tears down that
            # fixture first, then performs this independent database readback.
            request.node.addfinalizer(verify_pytest_cleanup)
            reference = canonical_postgres(request)
            created.append(reference.database_name)
            return asyncio.run(scenario(*args, **kwargs))
        return run
    return decorate


def _secret_free(value, *forbidden):
    data = asdict(value) if is_dataclass(value) else value
    rendered = json.dumps(data, default=str, sort_keys=True)
    assert all(secret not in rendered for secret in forbidden if secret)
    return data


_POSTGRES_ENVIRONMENT_KEYS = {"host_label", "port", "database_label", "host_allowlist_decision", "postgres_version", "config_fingerprint"}


def _assert_environment_record(record, expected):
    assert type(record) is dict and set(record) == _POSTGRES_ENVIRONMENT_KEYS
    assert type(record["port"]) is int and 1 <= record["port"] <= 65535
    assert record["host_allowlist_decision"] in {"loopback", "explicit_allowlist"}
    assert record["host_label"] in ({"127.0.0.1", "localhost", "::1"} if record["host_allowlist_decision"] == "loopback" else {"allowlisted-test-host"})
    assert re.fullmatch(r"scribe_swarm_[0-9a-f]{32}", record["database_label"])
    assert type(record["postgres_version"]) is str and re.fullmatch(r"[0-9]+", record["postgres_version"]) and int(record["postgres_version"]) > 0
    assert type(record["config_fingerprint"]) is str and re.fullmatch(r"[0-9a-f]{64}", record["config_fingerprint"])
    assert record == expected
    assert json.loads(json.dumps(record)) == expected
    return record


def _postgres_environment(reference):
    expected = {"host_label": reference.target.host_label, "port": reference.target.port,
        "database_label": reference.database_name, "host_allowlist_decision": reference.target.host_allowlist_decision,
        "postgres_version": reference.postgres_version, "config_fingerprint": reference.config_fingerprint}
    assert reference.target.database_label == reference.database_name
    return _assert_environment_record(reference.as_environment_dict(), expected)


def _constructed_reference(owner, delta=None, include_kwargs=False):
    name = "scribe_swarm_" + "a" * 32
    dsn = f"postgresql://private-user:fixture-secret@private-test.invalid/{name}?application_name=private-query#private-fragment"
    target = owner.SanitizedPostgresTarget(host_label="allowlisted-test-host", port=5432,
        database_label=name, host_allowlist_decision="explicit_allowlist")
    async def cleanup():
        return None
    kwargs = dict(dsn=dsn, database_name=name, target=target, postgres_version="170005",
        config_fingerprint="b" * 64, cleanup=cleanup)
    delta = dict(delta or {})
    if "target_database" in delta:
        kwargs["target"] = replace(target, database_label=delta.pop("target_database"))
    kwargs.update(delta)
    fixture = owner.PostgresReferenceFixture(**kwargs)
    expected = dict(host_label="allowlisted-test-host", port=5432, database_label=name,
        host_allowlist_decision="explicit_allowlist", postgres_version="170005", config_fingerprint="b" * 64)
    secrets = (dsn, "private-user", "fixture-secret", "private-query", "private-fragment", "private-test.invalid", "private-base-database")
    return (fixture, expected, secrets, kwargs) if include_kwargs else (fixture, expected, secrets)


_POSTGRES_SETTINGS = {"max_connections", "shared_buffers", "work_mem", "fsync", "full_page_writes", "synchronous_commit"}


def _expected_settings_checksum(rows):
    """F2 checksum assertion against producer output; never a fixture/exporter."""
    assert len(rows) == 6 and {row["name"] for row in rows} == _POSTGRES_SETTINGS
    settings = {row["name"]: row["setting"] for row in rows}
    for key in ("max_connections", "shared_buffers", "work_mem"):
        assert type(settings[key]) is str and re.fullmatch(r"[0-9]+", settings[key]) and int(settings[key]) > 0
        settings[key] = str(int(settings[key]))
    assert settings["fsync"] in {"on", "off"} and settings["full_page_writes"] in {"on", "off"}
    assert settings["synchronous_commit"] in {"on", "off", "local", "remote_write", "remote_apply"}
    return hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


class TestSBRDisposableFixture:
    @staticmethod
    def _fingerprint():
        helper = getattr(postgres_fixtures, "_postgres_config_fingerprint", None)
        assert callable(helper), "Frozen contract absent: REL-VAL.1 _postgres_config_fingerprint"
        signature = inspect.signature(helper)
        assert tuple(signature.parameters) == ("settings",)
        parameter = signature.parameters["settings"]
        assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is inspect.Parameter.empty
        annotations = get_type_hints(helper)
        assert get_origin(annotations.get("settings")) is Mapping
        assert get_args(annotations["settings"]) == (str, str)
        assert annotations.get("return") is str
        return helper

    @staticmethod
    def _settings():
        return dict(max_connections="100", shared_buffers="16384", work_mem="4096",
            fsync="on", full_page_writes="on", synchronous_commit="on")

    def test_fingerprint_matches_canonical_checksum_and_numeric_normalization(self):
        helper = self._fingerprint()
        settings = self._settings()
        expected = _expected_settings_checksum([dict(name=key, setting=value) for key, value in settings.items()])
        assert helper(settings) == expected
        reordered = dict(reversed(list(settings.items())))
        for key in ("max_connections", "shared_buffers", "work_mem"):
            reordered[key] = "000" + reordered[key]
        assert helper(reordered) == expected
        assert settings == self._settings()

    @pytest.mark.parametrize("key,value", [
        ("max_connections", "101"), ("shared_buffers", "16385"), ("work_mem", "4097"),
        ("fsync", "off"), ("full_page_writes", "off"),
        ("synchronous_commit", "off"), ("synchronous_commit", "local"),
        ("synchronous_commit", "remote_write"), ("synchronous_commit", "remote_apply"),
    ])
    def test_fingerprint_changes_for_each_selected_setting(self, key, value):
        helper = self._fingerprint()
        baseline = self._settings()
        changed = baseline | {key: value}
        result = helper(changed)
        assert result != helper(baseline)
        assert result == _expected_settings_checksum([dict(name=name, setting=setting) for name, setting in changed.items()])

    def test_fingerprint_reads_only_six_explicit_keys_without_io(self, monkeypatch, caplog):
        helper = self._fingerprint()
        selected = self._settings()
        reads = []
        class SelectedOnly(Mapping):
            def __getitem__(self, key):
                reads.append(key)
                assert key in selected, "unrelated setting was accessed"
                return selected[key]
            def __iter__(self):
                raise AssertionError("settings were enumerated/copied")
            def __len__(self):
                raise AssertionError("settings were enumerated/copied")
        def denied(*args, **kwargs):
            raise AssertionError("fingerprint accessed external state")
        expected = _expected_settings_checksum([dict(name=key, setting=value) for key, value in selected.items()])
        import asyncpg
        with monkeypatch.context() as guard:
            guard.setattr(asyncpg, "connect", denied)
            guard.setattr(builtins, "open", denied)
            guard.setattr(Path, "open", denied)
            guard.setattr(type(os.environ), "__getitem__", denied)
            guard.setattr(type(os.environ), "__iter__", denied)
            assert helper(SelectedOnly()) == expected
            assert helper(selected | {"private.api_token": "credential-sentinel-private"}) == expected
        assert set(reads) == _POSTGRES_SETTINGS
        assert "credential-sentinel-private" not in caplog.text
        assert selected == self._settings()

    @pytest.mark.parametrize("omitted", sorted(_POSTGRES_SETTINGS))
    def test_fingerprint_rejects_every_missing_selected_setting(self, omitted):
        helper = self._fingerprint()
        settings = self._settings()
        del settings[omitted]
        with pytest.raises(ValueError) as error:
            helper(settings)
        assert omitted in str(error.value)
        _secret_free(str(error.value), "credential-sentinel-private")

    @pytest.mark.parametrize("key,value", [
        ("max_connections", "0"), ("max_connections", "-1"), ("max_connections", "١٠٠"),
        ("max_connections", True), ("shared_buffers", 16384), ("work_mem", ""),
        ("work_mem", "+4096"), ("work_mem", " 4096"), ("work_mem", "4096.0"),
        ("fsync", "ON"), ("fsync", False), ("full_page_writes", "yes"),
        ("synchronous_commit", "remote"), ("synchronous_commit", None),
    ])
    def test_fingerprint_rejects_invalid_selected_values(self, key, value):
        helper = self._fingerprint()
        with pytest.raises(ValueError) as error:
            helper(self._settings() | {key: value})
        assert key in str(error.value)

    @pytest.mark.parametrize("key", sorted(_POSTGRES_SETTINGS))
    def test_fingerprint_errors_never_include_supplied_values(self, key):
        helper = self._fingerprint()
        messages = []
        for value in ("private-invalid-first", "private-invalid-second"):
            with pytest.raises(ValueError) as error:
                helper(self._settings() | {key: value})
            messages.append(str(error.value))
            assert key in messages[-1]
            _secret_free(messages[-1], value)
        assert messages[0] == messages[1]

    def test_required_contract_is_present(self, request):
        fixture_contract()
        assert request._fixturemanager.getfixturedefs("swarm_postgres_backend", request.node), "canonical safe fixture is not discoverable"

    @pytest.mark.parametrize("variable", ["SCRIBE_POSTGRES_URL", "DATABASE_URL"])
    def test_production_dsn_collision_is_refused(self, request, tmp_path, monkeypatch, variable):
        fixture_contract()  # absence must precede setup, env/DSN or network errors
        dsn = "postgresql://test:fixture-secret@127.0.0.1/scribe_test"
        monkeypatch.setenv("SCRIBE_SWARM_DISPOSABLE", "1")
        monkeypatch.setenv("SCRIBE_TEST_POSTGRES_URL", dsn)
        monkeypatch.setenv(variable, dsn)
        with pytest.raises(ValueError) as failure:
            canonical_postgres(request)
            pytest.fail("production collision was admitted")
        _secret_free(str(failure.value), "fixture-secret", dsn)

    def test_missing_disposable_opt_in_is_refused(self, request, tmp_path, monkeypatch):
        fixture_contract()
        monkeypatch.delenv("SCRIBE_SWARM_DISPOSABLE", raising=False)
        monkeypatch.delenv("SCRIBE_TEST_POSTGRES_URL", raising=False)
        with pytest.raises(ValueError):
            canonical_postgres(request)
            pytest.fail("missing opt-in was admitted")

    @pytest.mark.parametrize("host", ["untrusted.invalid", "192.0.2.1"])
    def test_non_allowlisted_host_is_refused_and_error_is_redacted(self, host):
        owner = fixture_contract()
        dsn = f"postgresql://private-user:fixture-secret@{host}/scribe_test?application_name=private-label"
        with pytest.raises(ValueError) as failure:
            owner.validate_disposable_postgres_dsn(dsn, allow_hosts=("127.0.0.1", "localhost", "::1"))
        _secret_free(str(failure.value), "private-user", "fixture-secret", "private-label", dsn)

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
    def test_loopback_metadata_never_contains_credentials_or_query(self, host):
        owner = fixture_contract()
        dsn = f"postgresql://private-user:fixture-secret@{host}/scribe_test?application_name=private-label"
        target = owner.validate_disposable_postgres_dsn(dsn, allow_hosts=("127.0.0.1", "localhost", "::1"))
        _secret_free(target, dsn, "private-user", "fixture-secret", "private-label")

    @pytest.mark.parametrize("host,port,database,label,decision", [
        ("127.0.0.1", None, "private-base-database", "127.0.0.1", "loopback"),
        ("localhost", 6543, "private-base-database", "localhost", "loopback"),
        ("[::1]", None, "private-base-database", "::1", "loopback"),
        ("127.0.0.1", 6543, "scribe_swarm_" + "a" * 32, "127.0.0.1", "loopback"),
        ("localhost", 1, "private-base-database", "localhost", "loopback"),
        ("localhost", 65535, "private-base-database", "localhost", "loopback"),
        ("private-test.invalid", None, "private-base-database", "allowlisted-test-host", "explicit_allowlist"),
        ("private-test.invalid", 6543, "scribe_swarm_" + "b" * 32, "allowlisted-test-host", "explicit_allowlist"),
    ])
    def test_target_has_exact_safe_fields(self, host, port, database, label, decision):
        owner = fixture_contract()
        authority = host if port is None else f"{host}:{port}"
        dsn = f"postgresql://private-user:fixture-secret@{authority}/{database}?application_name=private-query"
        target = owner.validate_disposable_postgres_dsn(dsn,
            allow_hosts=("127.0.0.1", "localhost", "::1", "private-test.invalid"))
        assert is_dataclass(target) and target.__dataclass_params__.frozen
        assert {field.name for field in fields(target)} == {"host_label", "port", "database_label", "host_allowlist_decision"}
        assert all(field.default is MISSING and field.default_factory is MISSING for field in fields(target))
        signature = inspect.signature(owner.SanitizedPostgresTarget)
        assert set(signature.parameters) == {field.name for field in fields(target)}
        assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())
        expected = {"host_label": label, "port": 5432 if port is None else port,
            "database_label": database if database.startswith("scribe_swarm_") else "test-database",
            "host_allowlist_decision": decision}
        assert asdict(target) == expected
        assert not hasattr(target, "__dict__")
        with pytest.raises(AttributeError):
            target.port = 1
        with pytest.raises(AttributeError):
            target.extra = "forbidden"
        _secret_free(repr(target), dsn, "private-user", "fixture-secret", "private-query", "private-base-database", "private-test.invalid")

    @pytest.mark.parametrize("port", ["0", "65536", "-1", "private-port-sentinel", ""])
    def test_supplied_invalid_dsn_port_never_defaults_to_5432(self, port):
        owner = fixture_contract()
        dsn = f"postgresql://private-user:fixture-secret@localhost:{port}/private-base-database"
        with pytest.raises(ValueError) as error:
            owner.validate_disposable_postgres_dsn(dsn, allow_hosts=("localhost",))
        _secret_free(str(error.value), dsn, "private-user", "fixture-secret", "private-base-database", "private-port-sentinel")

    @pytest.mark.parametrize("delta", [
        {"port": True}, {"port": 0}, {"port": 65536}, {"port": "5432"},
        {"host_label": "private-test.invalid"}, {"host_label": "::1", "host_allowlist_decision": "explicit_allowlist"},
        {"host_label": "allowlisted-test-host", "host_allowlist_decision": "loopback"},
        {"database_label": "private-base-database"}, {"database_label": "scribe_swarm_" + "A" * 32},
        {"host_allowlist_decision": "unknown-sensitive-decision"},
        {"host_label": None}, {"database_label": None}, {"host_allowlist_decision": True},
    ])
    def test_target_constructor_rejects_invalid_closed_values(self, delta):
        owner = fixture_contract()
        values = dict(host_label="localhost", port=5432, database_label="test-database", host_allowlist_decision="loopback")
        with pytest.raises(ValueError) as error:
            owner.SanitizedPostgresTarget(**(values | delta))
        _secret_free(str(error.value), "private-test.invalid", "private-base-database", "unknown-sensitive-decision")

    def test_reference_object_has_only_closed_safe_extraction(self):
        owner = fixture_contract()
        fixture, expected, secrets = _constructed_reference(owner)
        assert not is_dataclass(fixture)
        assert not isinstance(fixture, (Mapping, Iterable))
        assert str(fixture) == repr(fixture) == f"PostgresReferenceFixture(database_name='{fixture.database_name}')"
        first = fixture.as_environment_dict()
        _assert_environment_record(first, expected)
        _secret_free((repr(fixture), str(fixture), repr(fixture.target), json.dumps(first)), *secrets)
        for name in ("dsn", "database_name", "target", "postgres_version", "config_fingerprint", "extra"):
            with pytest.raises(AttributeError):
                setattr(fixture, name, "forbidden")
        for encode in (asdict, pickle.dumps):
            with pytest.raises(TypeError) as error:
                encode(fixture)
            _secret_free(str(error.value), *secrets)
        first["port"] = 1
        first["forbidden"] = "private-query"
        assert fixture.as_environment_dict() == expected

    def test_environment_extraction_performs_no_io_environment_scan_or_cleanup(self, monkeypatch):
        owner = fixture_contract()
        import asyncpg
        calls = []
        def cleanup():
            calls.append(1)
            async def complete():
                return None
            return complete()
        def denied(*args, **kwargs):
            raise AssertionError("environment extraction accessed external state")
        with monkeypatch.context() as guard:
            guard.setattr(asyncpg, "connect", denied)
            guard.setattr(builtins, "open", denied)
            guard.setattr(Path, "open", denied)
            guard.setattr(type(os.environ), "__getitem__", denied)
            guard.setattr(type(os.environ), "__iter__", denied)
            fixture, expected, _ = _constructed_reference(owner, {"cleanup": cleanup})
            first = fixture.as_environment_dict()
            second = fixture.as_environment_dict()
        assert first == second == expected and first is not second
        assert calls == []

    @pytest.mark.parametrize("delta", [
        {"dsn": None}, {"database_name": "private-base-database"}, {"target": None},
        {"postgres_version": ""}, {"postgres_version": "0"}, {"postgres_version": "١٥٠٠٠٠"},
        {"postgres_version": "private-version-banner"}, {"postgres_version": True},
        {"config_fingerprint": ""}, {"config_fingerprint": "A" * 64},
        {"config_fingerprint": "a" * 63}, {"config_fingerprint": True}, {"cleanup": None},
        {"target_database": "scribe_swarm_" + "c" * 32},
    ])
    def test_reference_constructor_rejects_invalid_required_facts(self, delta):
        owner = fixture_contract()
        with pytest.raises((TypeError, ValueError)) as error:
            _constructed_reference(owner, delta)
        _secret_free(str(error.value), "private-version-banner", "private-base-database", "fixture-secret")

    @pytest.mark.parametrize("omitted", ["dsn", "database_name", "target", "postgres_version", "config_fingerprint", "cleanup"])
    def test_reference_constructor_requires_every_keyword_and_rejects_extras(self, omitted):
        owner = fixture_contract()
        _, _, _, kwargs = _constructed_reference(owner, include_kwargs=True)
        assert all(parameter.kind == inspect.Parameter.KEYWORD_ONLY and parameter.default is inspect.Parameter.empty
            for parameter in inspect.signature(owner.PostgresReferenceFixture).parameters.values())
        with pytest.raises(TypeError) as missing:
            owner.PostgresReferenceFixture(**{key: value for key, value in kwargs.items() if key != omitted})
        _secret_free(str(missing.value), kwargs["dsn"], "fixture-secret", "private-query")
        with pytest.raises(TypeError) as extra:
            owner.PostgresReferenceFixture(**(kwargs | {"metadata": {"secret": "forbidden"}}))
        _secret_free(str(extra.value), kwargs["dsn"], "fixture-secret", "private-query")

    @pytest.mark.asyncio
    async def test_reference_cleanup_retries_failure_then_is_idempotent(self):
        owner = fixture_contract()
        calls = []
        async def cleanup():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("injected-cleanup-failure")
        fixture, _, _ = _constructed_reference(owner, {"cleanup": cleanup})
        with pytest.raises(RuntimeError, match="injected-cleanup-failure"):
            await fixture.cleanup()
        await fixture.cleanup()
        await fixture.cleanup()
        assert len(calls) == 2

    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(fixture_contract)
    async def test_created_environment_matches_same_database_measurements(self, request):
        import asyncpg
        reference = canonical_postgres(request)
        connection = await asyncpg.connect(reference.dsn)
        try:
            assert await connection.fetchval("SELECT current_database()") == reference.database_name
            assert await connection.fetchval("SHOW server_version_num") == reference.postgres_version
            rows = await connection.fetch("SELECT name, setting FROM pg_settings WHERE name = ANY($1::text[])", sorted(_POSTGRES_SETTINGS))
            assert _expected_settings_checksum(rows) == reference.config_fingerprint
        finally:
            await connection.close()
        environment = _postgres_environment(reference)
        assert environment["database_label"] == reference.database_name
        assert json.loads(json.dumps(environment)) == environment

    @pytest.mark.integration
    @pytest.mark.postgres
    @pytest.mark.parametrize("failure", ["metadata_failure", "metadata_cancellation"])
    def test_metadata_capture_failure_or_cancellation_drops_database(self, request, monkeypatch, failure):
        owner = fixture_contract()
        import asyncpg
        created, reached = [], []
        original_create = owner._create_test_database
        async def record_created(base_dsn, admin_dsn, name):
            result = await original_create(base_dsn, admin_dsn, name)
            created.append(name)
            return result
        monkeypatch.setattr(owner, "_create_test_database", record_created)
        for method in ("fetch", "fetchrow", "fetchval"):
            original = getattr(asyncpg.Connection, method)
            async def fail_metadata(connection, query, *args, _original=original, **kwargs):
                if "server_version_num" in str(query).lower():
                    assert len(created) == 1
                    reached.append(1)
                    if failure == "metadata_cancellation":
                        raise asyncio.CancelledError()
                    raise RuntimeError("injected-metadata-capture")
                return await _original(connection, query, *args, **kwargs)
            monkeypatch.setattr(asyncpg.Connection, method, fail_metadata)
        expected = asyncio.CancelledError if failure == "metadata_cancellation" else RuntimeError
        with pytest.raises(expected):
            canonical_postgres(request)
        assert reached and len(created) == 1
        asyncio.run(_assert_database_gone(created[0]))

    @pytest.mark.integration
    @pytest.mark.postgres
    def test_created_database_is_unique_and_dropped_on_normal_or_body_failure(self, request, tmp_path, monkeypatch):
        fixture_contract()
        pytester = request.getfixturevalue("pytester")
        names_file = pytester.path / "database-names.jsonl"
        monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(REPO_ROOT / "src"), str(REPO_ROOT / "tests"))))
        pytester.makeini("[pytest]\nasyncio_mode = auto\n")
        # Re-export the actual fixtures. No DB setup/drop implementation is
        # copied into the subprocess; pytest owns both fixture lifetimes.
        pytester.makeconftest(f"""
import importlib.util
import sys
from integration.storage.conftest import swarm_postgres_backend

spec = importlib.util.spec_from_file_location(
    "sbr_canonical_test_fixtures", {str(REPO_ROOT / "tests" / "conftest.py")!r})
canonical = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = canonical
spec.loader.exec_module(canonical)
test_agent = canonical.test_agent
""")
        pytester.makepyfile(test_consumer=f"""
import asyncio
import json
from pathlib import Path
import asyncpg
import pytest

@pytest.mark.parametrize("fail", [False, True])
def test_consumer(swarm_postgres_backend, test_agent, fail):
    assert test_agent == "test-agent"
    reference = swarm_postgres_backend
    async def current_database():
        conn = await asyncpg.connect(reference.dsn)
        try:
            return await conn.fetchval("SELECT current_database()")
        finally:
            await conn.close()
    assert asyncio.run(current_database()) == reference.database_name
    with Path({str(names_file)!r}).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(reference.database_name) + "\\n")
    if fail:
        raise RuntimeError("injected-body-failure")
""")
        result = pytester.runpytest_subprocess("-q", "--tb=no", "-o", "addopts=")
        result.assert_outcomes(passed=1, failed=1, errors=0, skipped=0)
        assert "injected-body-failure" in result.stdout.str()
        names = [json.loads(line) for line in names_file.read_text(encoding="utf-8").splitlines()]
        assert len(names) == len(set(names)) == 2
        for name in names:
            assert re.fullmatch(r"scribe_swarm_[0-9a-f]{32}", name)
            asyncio.run(_assert_database_gone(name))

    @pytest.mark.parametrize("fault", ["failure", "cancellation"])
    @pytest.mark.integration
    @pytest.mark.postgres
    def test_setup_failure_or_cancellation_drops_created_database(self, request, tmp_path, monkeypatch, fault):
        owner = fixture_contract()
        storage_type = _required("scribe_mcp.storage.postgres", "PostgresStorage").PostgresStorage
        created = []
        original = owner._create_test_database
        gate = CausalGate()
        async def record_created(base_dsn, admin_dsn, db_name):
            result = await original(base_dsn, admin_dsn, db_name)
            created.append(db_name)
            return result
        async def fail_setup(storage):
            if fault == "failure":
                raise RuntimeError("injected-setup-failure")
            task = asyncio.current_task()
            assert task is not None
            asyncio.get_running_loop().call_soon(task.cancel)
            await gate.hold()
        monkeypatch.setattr(owner, "_create_test_database", record_created)
        monkeypatch.setattr(storage_type, "setup", fail_setup)
        try:
            if fault == "cancellation":
                with pytest.raises(asyncio.CancelledError):
                    canonical_postgres(request)
                assert gate.entered.is_set()
            else:
                with pytest.raises(RuntimeError, match="injected-setup-failure"):
                    canonical_postgres(request)
            assert len(created) == 1, "failure injection must follow actual database creation"
            asyncio.run(_assert_database_gone(created[0]))
        finally:
            gate.release.set()


async def _assert_database_gone(name):
    import asyncpg
    assert re.fullmatch(r"scribe_swarm_[0-9a-f]{32}", name)
    # Only explicit test fixture DSNs; never configured/default production URLs.
    dsn = os.environ.get("SCRIBE_TEST_POSTGRES_ADMIN_URL") or os.environ["SCRIBE_TEST_POSTGRES_URL"]
    conn = await asyncpg.connect(dsn)
    try:
        assert await conn.fetchval("SELECT count(*) FROM pg_database WHERE datname=$1", name) == 0
        assert await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname=$1", name) == 0
    finally:
        await conn.close()


async def _snapshot(storage):
    """xmin/ctid also catch writes that restore the same logical values."""
    pool = await storage._ensure_pool()
    async with pool.acquire() as conn:
        tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname=$1 ORDER BY tablename", storage.schema_name)
        result = {}
        for table in tables:
            name = table["tablename"]
            quoted = name.replace('"', '""')
            rows = await conn.fetch(f'SELECT xmin::text, ctid::text, to_jsonb(t)::text FROM "{quoted}" t')
            result[name] = sorted(map(tuple, rows))
        return result


@asynccontextmanager
async def _binding_store(request, tmp_path, test_agent):
    storage_type = postgres_binding_contract()
    fixture_contract()
    reference = canonical_postgres(request)
    store = storage_type(reference.dsn)
    try:
        await store.setup()
        projects = []
        for index in range(2):
            root = tmp_path / f"repo-{index}"
            root.mkdir()
            projects.append(await store.upsert_project(name=f"project-{index}", repo_root=str(root),
                progress_log_path=str(root / "PROGRESS_LOG.md")))
        await store.upsert_session(session_id="stable-1", agent_id=test_agent,
            repo_root=projects[0].repo_root, mode="project")
        yield store, projects
    finally:
        await store.close()


class TestSBRPostgresBinding:
    @staticmethod
    def _clear_contract():
        storage = postgres_binding_contract()
        clear = getattr(storage, "clear_session_project", None)
        assert inspect.iscoroutinefunction(clear), "Frozen contract absent: PostgresStorage.clear_session_project"
        parameters = inspect.signature(clear).parameters
        assert tuple(parameters) == ("self", "session_id", "expected_generation")
        assert parameters["session_id"].default is inspect.Parameter.empty
        assert parameters["expected_generation"].default is None
        assert all(parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for parameter in parameters.values())
        annotations = get_type_hints(clear)
        assert annotations.get("session_id") is str
        assert set(get_args(annotations.get("expected_generation"))) == {int, type(None)}
        assert annotations.get("return") is type(None)
        return storage

    @staticmethod
    async def _raw_binding(store, session_id="stable-1"):
        pool = await store._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""SELECT b.*, b.xmin::text AS binding_xmin,
                b.ctid::text AS binding_ctid, p.repo_root AS actual_repo_root,
                s.repo_root AS session_repo_root FROM session_projects b
                JOIN scribe_sessions s ON s.session_id=b.session_id
                LEFT JOIN scribe_projects p ON p.project_key=b.project_key
                WHERE b.session_id=$1""", session_id)
        return None if row is None else dict(row)

    @staticmethod
    async def _assert_actual_binding(store, record, session_id="stable-1"):
        row = await TestSBRPostgresBinding._raw_binding(store, session_id)
        assert row is not None and row["binding_state"] == "resolved"
        assert record.project_key == row["project_key"]
        assert record.project_name == row["project_name"]
        assert record.canonical_repo_root == row["actual_repo_root"]
        assert record.binding_generation == row["binding_generation"]
        assert record.updated_at == row["updated_at"]
        assert await store.get_session_project(session_id) == record
        return row

    def test_required_contract_is_present(self):
        self._clear_contract()

    @pytest.mark.parametrize("expected", [None, 0, 1, -1])
    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(_clear_contract)
    async def test_absent_clear_compares_zero_before_any_write(self, request, tmp_path, test_agent, expected):
        async with _binding_store(request, tmp_path, test_agent) as (store, _):
            assert await self._raw_binding(store) is None
            snapshot = await _snapshot(store)
            if expected in (None, 0):
                assert await store.clear_session_project("stable-1", expected_generation=expected) is None
            else:
                conflict = _required("scribe_mcp.storage.base", "ConflictError").ConflictError
                with pytest.raises(conflict):
                    await store.clear_session_project("stable-1", expected_generation=expected)
            assert await self._raw_binding(store) is None
            assert await store.get_session_project("stable-1") is None
            assert await _snapshot(store) == snapshot

    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(_clear_contract)
    async def test_clear_preserves_tombstone_generation_and_denies_aba(self, request, tmp_path, test_agent):
        async with _binding_store(request, tmp_path, test_agent) as (store, projects):
            conflict = _required("scribe_mcp.storage.base", "ConflictError").ConflictError
            await store.upsert_session(session_id="clear-sibling", agent_id=test_agent,
                repo_root=projects[0].repo_root, mode="project")
            sibling = await store.set_session_project("clear-sibling", project_key=projects[0].project_key, expected_generation=0)
            sibling_row = await self._raw_binding(store, "clear-sibling")
            first = await store.set_session_project("stable-1", project_key=projects[0].project_key, expected_generation=0)
            assert first.binding_generation == 1
            await self._assert_actual_binding(store, first)
            assert await store.clear_session_project("stable-1", expected_generation=1) is None
            tombstone = await self._raw_binding(store)
            assert tombstone is not None and tombstone["binding_generation"] == 2
            assert tombstone["project_key"] is tombstone["project_name"] is None
            assert (tombstone["binding_state"], tombstone["binding_state_reason"]) == ("unresolved", "project_name_absent")
            assert tombstone["updated_at"] != first.updated_at
            assert await store.get_session_project("stable-1") is None
            snapshot = await _snapshot(store)
            assert await store.clear_session_project("stable-1", expected_generation=2) is None
            assert await self._raw_binding(store) == tombstone
            assert await _snapshot(store) == snapshot
            with pytest.raises(conflict):
                await store.clear_session_project("stable-1", expected_generation=1)
            assert await _snapshot(store) == snapshot
            with pytest.raises(conflict):
                await store.set_session_project("stable-1", project_key=first.project_key, expected_generation=1)
            assert await _snapshot(store) == snapshot
            rebound = await store.set_session_project("stable-1", project_key=first.project_key, expected_generation=2)
            assert rebound.binding_generation == 3
            await self._assert_actual_binding(store, rebound)
            snapshot = await _snapshot(store)
            for project in projects:
                with pytest.raises(conflict):
                    await store.set_session_project("stable-1", project_key=project.project_key, expected_generation=1)
                assert await _snapshot(store) == snapshot
            with pytest.raises(conflict):
                await store.clear_session_project("stable-1", expected_generation=1)
            assert await _snapshot(store) == snapshot
            assert await store.get_session_project("clear-sibling") == sibling
            assert await self._raw_binding(store, "clear-sibling") == sibling_row

    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(_clear_contract)
    async def test_unknown_session_and_invalid_key_conflicts_have_no_effects(self, request, tmp_path, test_agent):
        async with _binding_store(request, tmp_path, test_agent) as (store, projects):
            conflict = _required("scribe_mcp.storage.base", "ConflictError").ConflictError
            snapshot = await _snapshot(store)
            with pytest.raises(conflict):
                await store.set_session_project("unknown-session", project_key=projects[0].project_key, expected_generation=0)
            assert await _snapshot(store) == snapshot
            with pytest.raises(conflict):
                await store.clear_session_project("unknown-session", expected_generation=0)
            assert await _snapshot(store) == snapshot
            for key in (None, "", "missing-project-key", projects[0].name):
                with pytest.raises(conflict):
                    await store.set_session_project("stable-1", project_key=key, expected_generation=0)
                assert await _snapshot(store) == snapshot

    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(_clear_contract)
    async def test_keyed_cross_root_returns_exact_post_trigger_persisted_identity(self, request, tmp_path, test_agent):
        async with _binding_store(request, tmp_path, test_agent) as (store, projects):
            other_root = tmp_path / "same-label-other-root"
            other_root.mkdir()
            target = await store.upsert_project(name=projects[0].name, repo_root=str(other_root),
                progress_log_path=str(other_root / "PROGRESS_LOG.md"))
            assert target.project_key != projects[0].project_key
            record = await store.set_session_project("stable-1", project_key=target.project_key, expected_generation=0)
            row = await self._assert_actual_binding(store, record)
            assert record.project_key == target.project_key and record.project_name == target.name
            assert record.canonical_repo_root == target.repo_root != projects[0].repo_root
            assert row["session_repo_root"] == projects[0].repo_root
            assert record.binding_generation == 1, "classifier generation must not be incremented twice"
            snapshot = await _snapshot(store)
            assert await store.set_session_project("stable-1", project_key=target.project_key, expected_generation=1) == record
            assert await _snapshot(store) == snapshot

    @pytest.mark.parametrize("field", ["project_name", "project_key"])
    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(_clear_contract)
    async def test_trigger_identity_mismatch_rolls_back_before_success(self, request, tmp_path, test_agent, field):
        async with _binding_store(request, tmp_path, test_agent) as (store, projects):
            conflict = _required("scribe_mcp.storage.base", "ConflictError").ConflictError
            pool = await store._ensure_pool()
            # Fault injection is a real test-owned database trigger. Production
            # classifier/mapper/readback execute unchanged in the disposable DB.
            async with pool.acquire() as conn:
                await conn.execute(f"""CREATE FUNCTION sbr_test_binding_corruption() RETURNS trigger
                    LANGUAGE plpgsql AS $$ BEGIN NEW.{field} := 'sbr_missing_identity'; RETURN NEW; END; $$""")
                await conn.execute('''CREATE TRIGGER "000_sbr_binding_corruption" BEFORE INSERT OR UPDATE
                    ON session_projects FOR EACH ROW EXECUTE FUNCTION sbr_test_binding_corruption()''')
            try:
                snapshot = await _snapshot(store)
                with pytest.raises(conflict):
                    await store.set_session_project("stable-1", project_key=projects[0].project_key, expected_generation=0)
                assert await _snapshot(store) == snapshot
                assert await self._raw_binding(store) is None
                assert await store.get_session_project("stable-1") is None
            finally:
                async with pool.acquire() as conn:
                    await conn.execute('DROP TRIGGER "000_sbr_binding_corruption" ON session_projects')
                    await conn.execute("DROP FUNCTION sbr_test_binding_corruption()")
            record = await store.set_session_project("stable-1", project_key=projects[0].project_key, expected_generation=0)
            assert record.binding_generation == 1
            await self._assert_actual_binding(store, record)

    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(_clear_contract)
    async def test_getter_hides_unresolved_row_and_clear_normalizes_once(self, request, tmp_path, test_agent):
        async with _binding_store(request, tmp_path, test_agent) as (store, _):
            pool = await store._ensure_pool()
            async with pool.acquire() as conn:
                await conn.execute("INSERT INTO session_projects (session_id,project_name,project_key,updated_at) VALUES ($1,$2,NULL,NOW())",
                    "stable-1", "missing-legacy-project")
            unresolved = await self._raw_binding(store)
            assert unresolved["binding_state"] == "unresolved" and unresolved["binding_generation"] == 1
            assert unresolved["binding_state_reason"] != "project_name_absent"
            assert await store.get_session_project("stable-1") is None
            assert await store.clear_session_project("stable-1", expected_generation=1) is None
            tombstone = await self._raw_binding(store)
            assert tombstone["project_key"] is tombstone["project_name"] is None
            assert (tombstone["binding_state"], tombstone["binding_state_reason"], tombstone["binding_generation"]) == ("unresolved", "project_name_absent", 2)
            assert await store.get_session_project("stable-1") is None
            snapshot = await _snapshot(store)
            assert await store.clear_session_project("stable-1", expected_generation=2) is None
            assert await self._raw_binding(store) == tombstone and await _snapshot(store) == snapshot

    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(postgres_binding_contract)
    async def test_first_change_noop_and_stale_generations_have_exact_write_semantics(self, request, tmp_path, test_agent):
        postgres_binding_contract()
        async with _binding_store(request, tmp_path, test_agent) as (store, projects):
            first = await store.set_session_project("stable-1", project_key=projects[0].project_key)
            assert first.binding_generation == 1
            assert first == await store.get_session_project("stable-1")
            snapshot = await _snapshot(store)
            second = await store.set_session_project("stable-1", project_key=first.project_key, expected_generation=1)
            assert second == first and second.updated_at == first.updated_at
            assert await _snapshot(store) == snapshot
            conflict = _required("scribe_mcp.storage.base", "ConflictError").ConflictError
            for project in projects:
                with pytest.raises(conflict):
                    await store.set_session_project("stable-1", project_key=project.project_key, expected_generation=0)
                assert await _snapshot(store) == snapshot
            changed = await store.set_session_project("stable-1", project_key=projects[1].project_key, expected_generation=1)
            assert changed.binding_generation == 2
            assert changed.project_key == projects[1].project_key
            assert changed.caller_session_key_hash == first.caller_session_key_hash

    @pytest.mark.integration
    @pytest.mark.postgres
    @_pytest_postgres(postgres_binding_contract)
    async def test_32_same_label_bindings_survive_reopen_and_cas_race(self, request, tmp_path, test_agent):
        storage_type = postgres_binding_contract()
        async with _binding_store(request, tmp_path, test_agent) as (store, projects):
            for index in range(32):
                await store.upsert_session(session_id=f"session-{index}", agent_id=test_agent,
                    repo_root=projects[index % 2].repo_root, mode="project")
            rows = await asyncio.gather(*(store.set_session_project(f"session-{i}",
                project_key=projects[i % 2].project_key) for i in range(32)))
            assert len({row.caller_session_key_hash for row in rows}) == 32
            assert all(row.binding_generation == 1 for row in rows)
            reopened = storage_type(store._dsn)
            try:
                await reopened.setup()
                assert await asyncio.gather(*(reopened.get_session_project(f"session-{i}") for i in range(32))) == rows
                conflict = _required("scribe_mcp.storage.base", "ConflictError").ConflictError
                results = await asyncio.gather(*(reopened.set_session_project("session-0",
                    project_key=projects[1].project_key, expected_generation=1) for _ in range(32)), return_exceptions=True)
                assert sum(not isinstance(row, BaseException) for row in results) == 1
                assert sum(isinstance(row, conflict) for row in results) == 31
                final = await reopened.get_session_project("session-0")
                assert final.binding_generation == 2 and final.project_key == projects[1].project_key
                assert await asyncio.gather(*(reopened.get_session_project(f"session-{i}") for i in range(1, 32))) == rows[1:]
            finally:
                await reopened.close()


def test_schema_contract_is_present():
    schema_contract()


def _schema_process(dsn, schema_name, barrier, output, deadline_ms):
    """A real independently imported process; DSN stays in process memory."""
    async def run():
        storage_type, _ = schema_contract()
        storage = storage_type(dsn, schema_name=schema_name, pool_min_size=1, pool_max_size=1)
        try:
            await asyncio.to_thread(barrier.wait, 30)
            started = time.monotonic_ns()
            result = await storage.ensure_schema_ready(deadline_ms=deadline_ms)
            output.put({"result": asdict(result), "elapsed_ms": (time.monotonic_ns() - started) / 1e6})
        finally:
            await storage.close()
    try:
        asyncio.run(run())
    except BaseException as error:
        # Exception text can contain a DSN; only the bounded type crosses IPC.
        output.put({"failure_type": type(error).__name__})
        raise SystemExit(1)


def _run_schema_processes(dsn, schema_name, count=32, deadline_ms=2500):
    context = multiprocessing.get_context("spawn")
    barrier, output = context.Barrier(count), context.Queue()
    children = [context.Process(target=_schema_process, args=(dsn, schema_name, barrier, output, deadline_ms)) for _ in range(count)]
    try:
        for child in children:
            child.start()
        rows = [output.get(timeout=60) for _ in children]
        for child in children:
            child.join(timeout=10)
        assert all(child.exitcode == 0 for child in children), "schema child failed; inspect sanitized rows"
        assert all("result" in row for row in rows), rows
        return rows
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
            child.join(timeout=10)
            assert not child.is_alive(), "owned schema process leaked"
            child.close()
        output.close()
        output.join_thread()


@pytest.mark.integration
@pytest.mark.postgres
@pytest.mark.slow
@_pytest_postgres(schema_contract)
async def test_schema_bootstrap_32_simultaneous_starts_one_elected_bootstrapper(request, tmp_path):
    storage_type, _ = schema_contract()
    fixture_contract()
    reference = canonical_postgres(request)
    schema_name = "schema_election"
    rows = await asyncio.to_thread(_run_schema_processes, reference.dsn, schema_name)
    results = [row["result"] for row in rows]
    assert all(row["ready"] and row["error_code"] is None and not row["retryable"] for row in results)
    assert Counter(row["bootstrap_role"] for row in results)["bootstrapper"] == 1
    assert len({(row["schema_fingerprint"], row["migration_version"]) for row in results}) == 1
    assert all(row["wait_ms"] <= 500 for row in results if row["bootstrap_role"] == "peer")
    assert all(row["elapsed_ms"] <= 500 for row in rows if row["result"]["bootstrap_role"] == "peer")
    store = storage_type(reference.dsn, schema_name=schema_name)
    try:
        await store.setup()
        before = await _snapshot(store)
        warm = await asyncio.to_thread(_run_schema_processes, reference.dsn, schema_name)
        assert all(row["result"]["bootstrap_role"] == "fast_path" for row in warm)
        assert _percentiles([row["elapsed_ms"] for row in warm])["p95"] <= 100
        assert await _snapshot(store) == before
    finally:
        await store.close()


@pytest.mark.integration
@pytest.mark.postgres
@_pytest_postgres(schema_contract)
async def test_schema_fingerprint_mismatch_fails_closed_without_ledger_write(request, tmp_path):
    storage_type, _ = schema_contract()
    fixture_contract()
    reference = canonical_postgres(request)
    store = storage_type(reference.dsn)
    try:
        await store.setup()
        pool = await store._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE scribe_schema_readiness SET schema_fingerprint=$1", "0" * 64)
        before = await _snapshot(store)
        result = await store.ensure_schema_ready(deadline_ms=500)
        assert not result.ready and result.error_code == "SCHEMA_FINGERPRINT_MISMATCH"
        assert result.retryable is False
        assert await _snapshot(store) == before
        with pytest.raises(Exception) as failure:
            await store.setup()
        assert getattr(failure.value, "error_code", None) == "SCHEMA_FINGERPRINT_MISMATCH"
        assert await _snapshot(store) == before
    finally:
        await store.close()


@pytest.mark.integration
@pytest.mark.postgres
@_pytest_postgres(schema_contract)
async def test_schema_peer_deadline_is_bounded_and_retryable(request, tmp_path):
    storage_type, schema = schema_contract()
    fixture_contract()
    reference = canonical_postgres(request)
    import asyncpg
    schema_name = "held_bootstrap"
    holder = await asyncpg.connect(reference.dsn)
    store = storage_type(reference.dsn, schema_name=schema_name, pool_min_size=1, pool_max_size=1)
    try:
        await holder.execute("SELECT pg_advisory_lock(hashtext($1))", schema._bootstrap_lock_key(schema_name))
        started = time.monotonic()
        result = await asyncio.wait_for(store.ensure_schema_ready(deadline_ms=100), 0.5)
        assert not result.ready and result.error_code == "SCHEMA_BOOTSTRAP_TIMEOUT"
        assert result.retryable and result.wait_ms <= 100
        assert time.monotonic() - started <= 0.5
        assert result.schema_fingerprint and result.migration_version == "sql:007_reliability_receipts.sql"
    finally:
        await holder.close()
        await store.close()


@pytest.mark.integration
@pytest.mark.postgres
@_pytest_postgres(schema_contract)
async def test_schema_warm_fast_path_and_owner_failure_are_bounded(request, tmp_path):
    storage_type, schema = schema_contract()
    fixture_contract()
    reference = canonical_postgres(request)
    import asyncpg
    holder = await asyncpg.connect(reference.dsn)
    schema_name = "owner_failure"
    store = storage_type(reference.dsn, schema_name=schema_name, pool_min_size=1, pool_max_size=1)
    attempted = asyncio.Event()
    def query_observed(record):
        if "pg_try_advisory_lock" in record.query:
            attempted.set()
    async def observe_connection(conn):
        conn.add_query_logger(query_observed)
    peer_pool = await asyncpg.create_pool(reference.dsn, min_size=1, max_size=1,
        init=observe_connection, server_settings={"search_path": f"{schema_name},public"})
    async def pool_provider(**kwargs):
        return peer_pool
    waiting = None
    try:
        await holder.execute("SELECT pg_advisory_lock(hashtext($1))", schema._bootstrap_lock_key(schema_name))
        waiting = asyncio.create_task(schema.ensure_schema_ready(pool_provider=pool_provider,
            schema_lock=asyncio.Lock(), schema_name=schema_name, deadline_ms=500))
        # A completed real try-lock query, while the owner is still alive,
        # proves this is owner-loss recovery rather than an ordinary start.
        await asyncio.wait_for(attempted.wait(), .5)
        assert not waiting.done()
        await holder.close()
        result = await asyncio.wait_for(waiting, 1)
        assert result.ready and result.bootstrap_role == "bootstrapper"
        before = await _snapshot(store)
        for _ in range(20):
            warm = await store.ensure_schema_ready(deadline_ms=100)
            assert warm.ready and warm.bootstrap_role == "fast_path" and warm.wait_ms <= 100
        assert await _snapshot(store) == before
        pool = await store._ensure_pool()
        async with pool.acquire():
            exhausted = await asyncio.wait_for(store.ensure_schema_ready(deadline_ms=100), 0.5)
            assert not exhausted.ready and exhausted.retryable
            assert exhausted.error_code in {"SCHEMA_STORAGE_UNAVAILABLE", "SCHEMA_BOOTSTRAP_TIMEOUT"}
            assert exhausted.wait_ms <= 100
    finally:
        await holder.close()
        if waiting is not None and not waiting.done():
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
        await peer_pool.close()
        await store.close()


@dataclass(frozen=True)
class StressProfile:
    name: str
    callers: int
    calls_per_caller: int
    workers: int
    global_concurrency: int
    per_project_concurrency: int
    seed: int
    warmup_seconds: int
    duration_seconds: int
    recovery_seconds: int

    @classmethod
    def from_env(cls):
        name = os.environ.get("SCRIBE_SWARM_PROFILE")
        if name not in {"smoke", "background-queue", "release", "extended"}:
            raise ValueError("explicit SCRIBE_SWARM_PROFILE is required for SBR_REFERENCE_STRESS")
        def integer(key, default):
            value = int(os.environ.get(key, default))
            if value < 1:
                raise ValueError(f"{key} must be positive")
            return value
        profile = cls(name, integer("SCRIBE_SWARM_CALLERS", 64 if name == "release" else 32),
            integer("SCRIBE_SWARM_CALLS_PER_CALLER", 100), integer("SCRIBE_SWARM_WORKERS", 4),
            integer("SCRIBE_SWARM_GLOBAL_CONCURRENCY", 4), integer("SCRIBE_SWARM_PER_PROJECT_CONCURRENCY", 1),
            integer("SCRIBE_SWARM_SEED", SEED), integer("SCRIBE_SWARM_WARMUP_SECONDS", 300),
            integer("SCRIBE_SWARM_DURATION_SECONDS", 1800), integer("SCRIBE_SWARM_RECOVERY_SECONDS", 300))
        if profile.calls_per_caller != 100 or profile.workers < 4:
            raise ValueError("reference corpus requires 100 calls per caller and at least four processes")
        if name in {"smoke", "background-queue"} and profile.callers != 32:
            raise ValueError("smoke and queue profiles require exactly 32 callers")
        if name == "release" and (profile.callers != 64 or profile.warmup_seconds != 300
                                  or profile.duration_seconds != 1800 or profile.recovery_seconds != 300):
            raise ValueError("release requires 64 callers and fixed 300/1800/300 second phases")
        if name == "extended" and (profile.callers < 32 or profile.callers % 32):
            raise ValueError("extended topology scales in whole 32-caller cohorts")
        if profile.global_concurrency != 4 or profile.per_project_concurrency != 1:
            raise ValueError("reference heavy concurrency is fixed at global four / per-project one")
        return profile


class TestSBRReferenceProfile:
    @pytest.mark.parametrize("function_name,expected_seconds", [
        ("_queue_reference", (7.25, None)),
        ("_scheduler_fairness", (.25,)),
        ("_scheduler_causal_windows", (5.1, .1, 1, .1)),
        ("_checkpoint_restart_probe", (.01, 31)),
        ("_service_fence_probe", (.2,)),
    ])
    def test_actual_driver_clock_calls_preserve_elapsed_time(self, function_name, expected_seconds):
        """Run real source expressions without entering missing-product preflights."""
        from types import SimpleNamespace
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        names = {"_queue_reference", "_scheduler_fairness", "_scheduler_causal_windows",
            "_checkpoint_restart_probe", "_service_fence_probe"}
        functions = {node.name: node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names}
        def advances(node):
            return sorted((call for call in ast.walk(node) if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute) and call.func.attr == "advance"),
                key=lambda call: call.lineno)
        # An added consumer outside the audited paths must not escape validation.
        assert {call.lineno for call in advances(tree)} == {
            call.lineno for function in functions.values() for call in advances(function)}
        assert set(functions) == names
        calls = advances(functions[function_name])
        assert len(calls) == len(expected_seconds)
        for call, seconds in zip(calls, expected_seconds):
            assert isinstance(call.func.value, ast.Name) and call.func.value.id in {"manual", "clock"}
            assert len(call.args) == 1 and not call.keywords
            # Include sub-ms due boundaries and already-due inputs; integer
            # truncation must never leave a retry earlier than its due time.
            due_offsets_us = (-1001, -1, 0, 1, 999, 1000, 1001, 999999, 1000000, 1000001) if seconds is None else (0,)
            for due_us in due_offsets_us:
                real = ManualClock()
                origin = datetime(2026, 9, 27, tzinfo=timezone.utc)
                now = lambda: origin + timedelta(seconds=real.now())
                retry = SimpleNamespace(next_attempt_at=now() + timedelta(microseconds=due_us))
                scope = {"manual": real, "clock": now if call.func.value.id == "manual" else real,
                    "now": now, "retry": retry, "math": math, "max": max}
                argument = eval(compile(ast.Expression(call.args[0]), __file__, "eval"), {"__builtins__": {}}, scope)
                # Execute the owned call itself against the unmodified C14 API.
                result = eval(compile(ast.Expression(call), __file__, "eval"), {"__builtins__": {}}, scope)
                assert result is None and type(argument) is int and argument >= 0
                expected = ((max(0, due_us) + 999) // 1000) / 1000 if seconds is None else seconds
                assert real.now() == pytest.approx(expected, abs=1e-9)
                if seconds is None:
                    assert now() >= retry.next_attempt_at
                    if due_us > 0:
                        assert now() - retry.next_attempt_at < timedelta(milliseconds=1)

    @pytest.mark.parametrize("name,callers", [("smoke", 32), ("background-queue", 32), ("release", 64), ("extended", 128)])
    def test_profile_preserves_topology_and_frozen_release_windows(self, monkeypatch, name, callers):
        for key in tuple(os.environ):
            if key.startswith("SCRIBE_SWARM_"):
                monkeypatch.delenv(key)
        monkeypatch.setenv("SCRIBE_SWARM_PROFILE", name)
        monkeypatch.setenv("SCRIBE_SWARM_CALLERS", str(callers))
        profile = StressProfile.from_env()
        assert (profile.name, profile.callers, profile.calls_per_caller, profile.workers) == (name, callers, 100, 4)
        assert (profile.warmup_seconds, profile.duration_seconds, profile.recovery_seconds) == (300, 1800, 300)

    @pytest.mark.parametrize("key,value", [("SCRIBE_SWARM_CALLERS", "16"), ("SCRIBE_SWARM_CALLS_PER_CALLER", "99"),
        ("SCRIBE_SWARM_WORKERS", "3"), ("SCRIBE_SWARM_GLOBAL_CONCURRENCY", "8"), ("SCRIBE_SWARM_PER_PROJECT_CONCURRENCY", "2")])
    def test_reference_inputs_cannot_relax_frozen_smoke_requirements(self, monkeypatch, key, value):
        for name in tuple(os.environ):
            if name.startswith("SCRIBE_SWARM_"):
                monkeypatch.delenv(name)
        monkeypatch.setenv("SCRIBE_SWARM_PROFILE", "smoke")
        monkeypatch.setenv(key, value)
        with pytest.raises(ValueError):
            StressProfile.from_env()

    def test_reference_measurement_requires_explicit_profile(self, monkeypatch):
        monkeypatch.delenv("SCRIBE_SWARM_PROFILE", raising=False)
        with pytest.raises(ValueError, match="explicit"):
            StressProfile.from_env()


def _runtime_contract():
    core = importlib.import_module("core.test_swarm_binding_reliability")
    core.resolver_contract()
    core.receipt_contract()
    core.timing_contract()
    core.get_contract()
    core.read_contract()
    postgres_binding_contract()
    return core


def _postgres_observations(core, topology, storage, manager, router, config, agent, patch):
    """Observe PostgreSQL without the core driver's SQLite connection probe."""
    class PostgresObservations(core.ToolObservations):
        def __init__(self):
            self.topology, self.storage, self.manager, self.router = topology, storage, manager, router
            self.settings, self.agent, self._patch = config, agent, patch
            self.records, self.identities, self.sessions, self.bind_counts = {}, {}, {}, Counter()
            self.stable_sessions, self.initial_bindings, self.initial_sessions = {}, {}, {}
            self.raw_timings, self.fault_timeline, self.samples = [], [], {}

        async def snapshot(self):
            return {"database": await _snapshot(storage), "files": {
                str(path.relative_to(topology.repositories[0].parent)): path.read_bytes()
                for root in topology.repositories for path in root.rglob("*") if path.is_file()}}

    world = PostgresObservations()
    for name in ("get_session_project", "fetch_project"):
        original = getattr(storage, name)
        async def measured(*args, _name=name, _original=original, **kwargs):
            sample = core.CURRENT_OBSERVATION.get()
            if sample is not None:
                sample.reads[_name] += 1
            return await _original(*args, **kwargs)
        patch.setattr(storage, name, measured)
    timing = importlib.import_module("scribe_mcp.runtime_timing_envelope")
    finalize = timing.CallTimingRecorderV2.finalize
    def envelope(recorder, **kwargs):
        result = finalize(recorder, **kwargs)
        sample = core.CURRENT_OBSERVATION.get()
        if sample is not None:
            sample.envelopes.append(result)
        return result
    patch.setattr(timing.CallTimingRecorderV2, "finalize", envelope)
    from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
    prepare = LoggingToolMixin.prepare_context
    async def context(helper, *args, **kwargs):
        result = await prepare(helper, *args, **kwargs)
        sample = core.CURRENT_OBSERVATION.get()
        if sample is not None:
            sample.contexts.append(result.resolved_request_context)
        return result
    context.__signature__ = inspect.signature(prepare)
    patch.setattr(LoggingToolMixin, "prepare_context", context)
    from scribe_mcp.utils.formatters.dispatcher import FormatterDispatcher
    finalize_response = FormatterDispatcher.finalize_tool_response
    async def response(formatter, *args, **kwargs):
        sample = core.CURRENT_OBSERVATION.get()
        if sample is not None:
            sample.contexts.append(kwargs.get("resolved_request_context"))
        return await finalize_response(formatter, *args, **kwargs)
    response.__signature__ = inspect.signature(finalize_response)
    patch.setattr(FormatterDispatcher, "finalize_tool_response", response)
    return world


@asynccontextmanager
async def _postgres_world(core, topology, dsn, workdir, agent):
    from scribe_mcp import server
    from scribe_mcp.config.settings import settings
    from scribe_mcp.shared import execution_context
    from scribe_mcp.shared.execution_context import RouterContextManager
    from scribe_mcp.state.manager import StateManager
    storage = postgres_binding_contract()(dsn)
    try:
        await storage.setup()
        manager = StateManager(path=workdir / "state.json", storage_backend=storage)
        router = RouterContextManager(storage)
        config = replace(settings, project_root=workdir, default_repo_root=None,
            trusted_repo_roots=topology.repositories, db_url=dsn, storage_backend="postgres",
            default_state_path=workdir / "state.json", dev_plans_base=workdir / "plans", allow_network=False)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(execution_context, "_APPLICATION_IDENTITIES", {})
            patch.setattr(execution_context, "_STDIO_IDENTITIES", {})
            patch.setattr(server, "storage_backend", storage)
            patch.setattr(server, "state_manager", manager)
            patch.setattr(server, "router_context_manager", router)
            patch.setattr(server, "settings", config)
            for name in ("set_project", "append_entry", "get_project", "read_recent", "query_entries", "manage_docs"):
                importlib.import_module(f"scribe_mcp.tools.{name}")
            for module in tuple(sys.modules.values()):
                if (getattr(module, "__name__", "").startswith("scribe_mcp.")
                        and getattr(module, "settings", None) is settings):
                    patch.setattr(module, "settings", config)
            world = _postgres_observations(core, topology, storage, manager, router, config, agent, patch)
            patch.setattr(server, "get_execution_context", lambda: world.router.get_current())
            for project in topology.projects:
                world.records[project.project_key] = await storage.upsert_project(name=project.name,
                    repo_root=str(project.root), progress_log_path=str(project.progress_log),
                    docs_json=json.dumps({"progress_log": str(project.progress_log),
                        "architecture": str(project.progress_log.parent / "ARCHITECTURE_GUIDE.md")}))
            yield world
    finally:
        await storage.close()


def _runtime_process(dsn, topology, callers, workdir, barrier, output, seed, warmup, duration, recovery, agent):
    async def run():
        core = _runtime_contract()
        import psutil
        workdir.mkdir()
        process = psutil.Process()
        task_baseline = set(asyncio.all_tasks())
        expected, observed, rss = [], [], []
        ledger_path, events_path = workdir / "ledger.jsonl", workdir / "events.jsonl"
        async with _postgres_world(core, topology, dsn, workdir, agent) as world:
            for caller in callers:
                assert core.payload(await world.bind(caller))["ok"] is True
            await asyncio.to_thread(barrier.wait, 60)
            run_started = time.monotonic_ns()
            measurement_start = run_started + warmup * 1_000_000_000
            measurement_end = measurement_start + duration * 1_000_000_000
            epoch = 0
            while True:
                schedules = {caller.caller_id: build_mixed_schedule(caller, seed=seed + epoch) for caller in callers}
                for ordinal in range(100):
                    await asyncio.to_thread(barrier.wait, 60)
                    async def one(caller):
                        operation = schedules[caller.caller_id][ordinal]
                        started = time.monotonic_ns()
                        await core.execute_corpus_operation(world, caller, operation, expected, observed)
                        ended = time.monotonic_ns()
                        sample_key = ("unbound-" + caller.caller_id
                            if operation.kind == "negative" and operation.expected_result_code == "SCRIBE_BINDING_MISSING"
                            else caller.caller_id)
                        sample = world.samples[sample_key]
                        event = {"started_ns": started, "ended_ns": ended, "kind": operation.kind,
                            "duration_ms": (ended - started) / 1e6,
                            "measurement": duration == 0 or measurement_start <= started < measurement_end,
                            "envelopes": sample.envelopes}
                        with events_path.open("a", encoding="utf-8") as stream:
                            stream.write(json.dumps(event, sort_keys=True) + "\n")
                    await asyncio.gather(*(one(caller) for caller in callers))
                    with ledger_path.open("a", encoding="utf-8") as stream:
                        for wanted, actual in zip(expected, observed, strict=True):
                            stream.write(json.dumps({"expected": asdict(wanted), "observed": asdict(actual)}, sort_keys=True) + "\n")
                    expected.clear()
                    observed.clear()
                    world.raw_timings.clear()
                    rss.append((time.monotonic_ns(), process.memory_info().rss))
                epoch += 1
                await asyncio.to_thread(barrier.wait, 60)
                if duration == 0 or time.monotonic_ns() >= measurement_end:
                    break
            counts, faults = dict(world.bind_counts), world.fault_timeline
            assert len(world.initial_sessions) == len(callers)
        # Raw observations live on disk; the oracle runs in the parent so its
        # growing ledger cannot manufacture product-process RSS regression.
        if recovery:
            await asyncio.sleep(recovery)
        rss.append((time.monotonic_ns(), process.memory_info().rss))
        output.put({"ledger_path": str(ledger_path), "events_path": str(events_path), "rss": rss,
            "measurement_start_ns": measurement_start, "measurement_end_ns": measurement_end,
            "bind_counts": counts, "faults": faults, "tasks": len(set(asyncio.all_tasks()) - task_baseline),
            "storage_handles": int(world.storage._internals._pool is not None)})
    try:
        asyncio.run(run())
    except BaseException as error:
        output.put({"failure_type": type(error).__name__})
        raise SystemExit(1)


def _run_runtime_processes(profile, *, dsn, topology, workdir, agent, isolated=False):
    context = multiprocessing.get_context("spawn")
    count = 1 if isolated else profile.workers
    barrier, output = context.Barrier(count), context.Queue()
    warmup = profile.warmup_seconds if not isolated and profile.name in {"release", "extended"} else 0
    duration = profile.duration_seconds if not isolated and profile.name in {"release", "extended"} else 0
    recovery = profile.recovery_seconds if duration else 0
    chunks = [topology.callers[index::count] for index in range(count)]
    children = [context.Process(target=_runtime_process, args=(dsn, topology, chunk, workdir / f"worker-{index}",
        barrier, output, profile.seed, warmup, duration, recovery, agent)) for index, chunk in enumerate(chunks)]
    rows = []
    try:
        for child in children:
            child.start()
        timeout = warmup + duration + profile.recovery_seconds + 60
        for _ in children:
            rows.append(output.get(timeout=timeout))
        for child in children:
            child.join(timeout=10)
        assert all(child.exitcode == 0 for child in children), "runtime child failed"
        assert all("ledger_path" in row for row in rows), rows
        for row in rows:
            ledger = [json.loads(line) for line in Path(row.pop("ledger_path")).read_text(encoding="utf-8").splitlines()]
            row["expected"] = [ExpectedEffect(**record["expected"]) for record in ledger]
            row["observed"] = [ObservedEffect(**record["observed"]) for record in ledger]
            row["events"] = [json.loads(line) for line in Path(row.pop("events_path")).read_text(encoding="utf-8").splitlines()]
        return rows
    finally:
        for child in children:
            if child.pid is not None:
                if child.is_alive():
                    child.terminate()
                child.join(timeout=10)
                assert not child.is_alive(), "owned runtime process leaked"
                child.close()
        output.close()
        output.join_thread()


def _percentiles(samples):
    """Use stdlib quantiles, retaining the original samples."""
    assert len(samples) >= 2, "insufficient reference samples"
    values = statistics.quantiles(samples, n=100, method="inclusive")
    return {"p50": values[49], "p95": values[94], "p99": values[98], "samples": samples}


def _queue_contract():
    service = _required("scribe_mcp.background.service", "BackgroundJobServiceV1", "BackgroundServiceConfigV1",
        "BackgroundQueueEventV1", "BackgroundQueueBusyError", "BackgroundDigestConflictError",
        "BackgroundServiceShuttingDownError")
    scheduler = _required("scribe_mcp.background.scheduler", "BackgroundSchedulerV1", "BackgroundSchedulerConfigV1")
    worker = _required("scribe_mcp.background.worker", "BackgroundWorkerV1", "SeededRetryPolicyV1", "BackgroundExecutionOutcomeV1")
    models = _required("scribe_mcp.background.models", "BackgroundOperationIntentV1", "BackgroundQueueLimitsV1",
        "BackgroundTransitionOutcomeV1", "BackgroundStaleFenceError")
    store = _required("scribe_mcp.background.store", "BackgroundReceiptStoreV1")
    return service, scheduler, worker, models, store


async def _wait_until(predicate, *, deadline_seconds):
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        value = await predicate()
        if value:
            return value
        # This is an explicit reference profile, never a hermetic wall-time proof.
        await asyncio.sleep(.005)
    raise AssertionError("reference recovery deadline expired")


_D3_PAIRS = {
    "admission": {"accepted", "duplicate", "digest_conflict", "busy", "shutting_down"},
    "retry_after": {"busy"}, "queue_items": {"accepted", "ready", "leased", "retry_wait"},
    "queue_bytes": {"accepted", "ready", "leased", "retry_wait"},
    "high_water": {"items", "bytes", "concurrency"}, "oldest_eligible": {"observed"},
    "queue_wait": {"claimed"}, "run_time": {"succeeded", "retry_wait", "failed_terminal", "cancelled", "stale_fence"},
    "worker_claim": {"claimed"}, "attempt": {"started"}, "retry": {"scheduled"},
    "dead_letter": {"failed_terminal"}, "cancellation": {"requested", "cancelled", "commit_started"},
    "lease": {"expired"}, "fence": {"stale_fence"}, "active_workers": {"observed"},
    "project_service": {"started"}, "starvation": {"window_ge_5s"},
    "shutdown": {"admitted", "drained", "checkpointed", "cancelled_retryable", "remaining_recoverable", "workers_stopped", "deadline_exceeded"},
    "recovery": {"recovered"}, "lifecycle": {"starting", "running", "draining", "stopped", "degraded"},
}


def _assert_d3_event(event, event_type, keys, observed_now, forbidden_labels=()):
    """Assert the frozen wire contract on actual emitted DTOs, not an oracle."""
    assert isinstance(event, event_type)
    row = asdict(event)
    assert set(row) == {"kind", "observed_at", "lane", "outcome", "canonical_project_key_hash", "duration_ms", "value"}
    assert event.kind in _D3_PAIRS and event.outcome in _D3_PAIRS[event.kind]
    assert isinstance(event.observed_at, datetime) and event.observed_at.utcoffset() == timedelta(0)
    assert event.observed_at == observed_now, "D3 event must use the applicable injected clock value"
    durations = {"admission", "oldest_eligible", "queue_wait", "run_time"}
    no_value = {"lifecycle", "oldest_eligible"}
    for field, required in (("duration_ms", event.kind in durations), ("value", event.kind not in no_value)):
        value = getattr(event, field)
        if required:
            assert type(value) is int and value >= 0
        else:
            assert value is None
    if event.kind in {"admission", "queue_wait", "run_time", "worker_claim", "attempt", "retry", "dead_letter", "cancellation", "lease", "fence", "project_service", "starvation"}:
        assert event.value == 1
    if event.kind == "shutdown" and event.outcome == "deadline_exceeded":
        assert event.value in {0, 1}
    global_kinds = {"lifecycle", "shutdown", "recovery", "active_workers"}
    assert event.lane is None if event.kind in global_kinds else event.lane in {None, "control", "durable", "heavy"}
    if event.kind in {"admission", "retry_after", "queue_wait", "run_time", "worker_claim", "attempt", "retry", "dead_letter", "cancellation", "lease", "fence", "project_service"}:
        # Every C09 intent in these service phases is heavy; the separate D1
        # real-store windows exercise control and durable lanes.
        assert event.lane == "heavy"
        assert event.canonical_project_key_hash is not None
    digest = event.canonical_project_key_hash
    if event.kind in global_kinds:
        assert digest is None
    if digest is not None:
        assert type(digest) is str and digest.strip()
        if digest in set(keys) | set(forbidden_labels):
            raise AssertionError("D3 project label exposes raw identity")
    rendered = json.dumps(row, default=str)
    assert all(key not in rendered for key in keys)
    return row


def _driver_contract_boundaries(service_mod, scheduler_mod, keys, now, authorized_labels):
    """Exercise the actual D1 config and D3 DTO before any sink delivery."""
    base = dict(global_concurrency=3, max_project_concurrency=1, control_reserved_slots=1, durable_reserved_slots=0)
    assert scheduler_mod.BackgroundSchedulerConfigV1(**base).project_weights == ()
    pairs = [(keys[2], 1), (keys[0], 2), (keys[1], 1)]
    config = scheduler_mod.BackgroundSchedulerConfigV1(**base, project_weights=pairs)
    pairs.clear()
    assert config.project_weights == tuple(sorted(((keys[0], 2), (keys[1], 1), (keys[2], 1))))
    for invalid in ((("", 1),), ((" ", 1),), ((keys[0], 1), (keys[0], 2)),
                    ((keys[0], 0),), ((keys[0], -1),), ((keys[0], True),), ((keys[0], 1.5),),
                    ((keys[0], "2"),), ((None, 1),), ((True, 1),), ((42, 1),)):
        with pytest.raises(ValueError):
            scheduler_mod.BackgroundSchedulerConfigV1(**base, project_weights=invalid)
    event_type = service_mod.BackgroundQueueEventV1
    delivered = []
    for kind, outcomes in _D3_PAIRS.items():
        for outcome in sorted(outcomes):
            scoped = kind in {"admission", "retry_after", "queue_wait", "run_time", "worker_claim", "attempt", "retry", "dead_letter", "cancellation", "lease", "fence", "project_service"}
            event = event_type(kind=kind, outcome=outcome, observed_at=now(), lane="heavy" if scoped else None,
                canonical_project_key_hash=authorized_labels[0] if scoped else None,
                duration_ms=0 if kind in {"admission", "oldest_eligible", "queue_wait", "run_time"} else None,
                value=None if kind in {"oldest_eligible", "lifecycle"} else 1)
            _assert_d3_event(event, event_type, keys, now())
            if event.value is None:
                with pytest.raises(ValueError):
                    delivered.append(replace(event, value=1))
            if event.duration_ms is None:
                with pytest.raises(ValueError):
                    delivered.append(replace(event, duration_ms=0))
    template = dict(kind="attempt", outcome="started", observed_at=now(), lane="heavy",
        canonical_project_key_hash=authorized_labels[0], duration_ms=None, value=1)
    invalids = [dict(kind="unknown"), dict(outcome="unknown"), dict(kind="attempt", outcome="accepted"),
        dict(value=True), dict(value=-1), dict(value=1.5), dict(duration_ms=True), dict(duration_ms=-1),
        dict(observed_at=datetime(2026, 9, 27)),
        dict(canonical_project_key_hash=123)]
    for delta in invalids:
        before = len(delivered)
        rejection = ValueError if {"kind", "outcome"} & delta.keys() else (TypeError, ValueError)
        with pytest.raises(rejection):
            delivered.append(event_type(**(template | delta)))
        assert len(delivered) == before, "invalid DTO reached sink"
    try:
        normalized = event_type(**(template | {"observed_at": now().astimezone(timezone(timedelta(hours=1)))}))
    except ValueError:
        pass
    else:
        assert normalized.observed_at.utcoffset() == timedelta(0)
    all_outcomes = set().union(*_D3_PAIRS.values())
    for kind, allowed in _D3_PAIRS.items():
        for outcome in all_outcomes - allowed:
            before = len(delivered)
            with pytest.raises(ValueError):
                delivered.append(event_type(**(template | {"kind": kind, "outcome": outcome})))
            assert len(delivered) == before


def _assert_shutdown_events(events, receipt, admitted):
    rows = [event for event in events if event["kind"] == "shutdown"]
    expected = {name: int(getattr(receipt, name)) for name in _D3_PAIRS["shutdown"] - {"admitted"}}
    expected["admitted"] = admitted
    assert Counter(event["outcome"] for event in rows) == Counter({name: 1 for name in expected})
    assert {event["outcome"]: event["value"] for event in rows} == expected


def _reconcile_queue_events(events, status, health, observations, config, project_labels, busy_delays, handler_run_ms, phase_started_ns):
    """Reconcile service emissions with real receipts and stable store reads."""
    def total(kind, outcome=None):
        return sum(row["value"] for row in events if row["kind"] == kind and (outcome is None or row["outcome"] == outcome))
    attempts = sum(row.attempt_count for row in status.values())
    claims = dict(health.metrics.worker_claims)
    assert total("admission", "accepted") == len(status)
    assert total("admission", "duplicate") == total("admission", "digest_conflict") == total("admission", "shutting_down") == 1
    assert total("admission", "busy") > 0
    assert len([row for row in events if row["kind"] == "retry_after"]) == total("admission", "busy")
    assert Counter((row["value"], row["lane"], row["canonical_project_key_hash"])
        for row in events if row["kind"] == "retry_after") == Counter(busy_delays)
    assert total("worker_claim") == total("attempt") == total("project_service") == sum(claims.values()) == attempts
    expected_starts = Counter()
    for row in status.values():
        expected_starts[project_labels[row.canonical_project_key]] += row.attempt_count
    for kind in ("worker_claim", "attempt", "project_service", "queue_wait", "run_time"):
        assert Counter(row["canonical_project_key_hash"] for row in events if row["kind"] == kind) == +expected_starts
    assert health.accepted_receipts == len(status) and health.recovered_receipts == 0
    assert total("retry") == sum(max(0, row.attempt_count - 1) for row in status.values()) == 1
    assert total("dead_letter") == sum(row.state == "failed_terminal" for row in status.values()) == 1
    assert total("cancellation", "requested") == 3
    assert total("cancellation", "cancelled") == sum(row.state == "cancelled" for row in status.values()) == 2
    assert total("cancellation", "commit_started") == 1
    assert total("lease") == total("fence") == total("starvation") == 0
    assert total("recovery") == 0, "terminal rows must not become reconstructed admissions"
    assert any(row["kind"] == "queue_items" and row["outcome"] == "accepted" and row["value"] > 0 for row in events)
    queue_waits = [row["duration_ms"] for row in events if row["kind"] == "queue_wait"]
    runtimes = [row["duration_ms"] for row in events if row["kind"] == "run_time"]
    assert len(queue_waits) == len(runtimes) == attempts
    assert len([value for values in handler_run_ms.values() for value in values]) == attempts
    for key, measured in handler_run_ms.items():
        emitted = sorted(row["duration_ms"] for row in events if row["kind"] == "run_time" and row["canonical_project_key_hash"] == project_labels[key])
        assert len(emitted) == len(measured)
        assert all(actual + 1 >= lower for actual, lower in zip(emitted, sorted(measured)))
    assert max(runtimes) <= (time.monotonic_ns() - phase_started_ns) // 1000000 + 1
    terminal_counts = Counter(row.state for row in status.values() if row.attempt_count)
    run_counts = Counter(row["outcome"] for row in events if row["kind"] == "run_time")
    assert run_counts == terminal_counts + Counter({"retry_wait": 1})
    highwaters = {"items": health.metrics.item_high_water, "bytes": health.metrics.byte_high_water,
                  "concurrency": health.metrics.concurrency_high_water}
    for outcome, value in highwaters.items():
        actual = [row["value"] for row in events if row["kind"] == "high_water" and row["outcome"] == outcome and row["canonical_project_key_hash"] is None]
        assert actual and max(actual) == value
    assert highwaters["items"] <= config.queue_limits.max_pending_items
    assert highwaters["bytes"] <= config.queue_limits.max_pending_bytes
    assert highwaters["concurrency"] <= config.scheduler.global_concurrency
    state_observations = []
    for observed in observations:
        snapshot = observed["snapshot"]
        pending = [row for row in snapshot.receipts if row.state in {"accepted", "ready", "leased", "retry_wait"}]
        assert len(pending) == snapshot.pending_items
        assert sum(row.payload_bytes for row in pending) == snapshot.pending_bytes
        preceding = events[:observed["events_end"]]
        gauges = {}
        for kind in ("queue_items", "queue_bytes"):
            gauges[kind] = {}
            for state in _D3_PAIRS[kind]:
                rows = [row for row in preceding if row["kind"] == kind and row["outcome"] == state and row["canonical_project_key_hash"] is None and row["lane"] is None]
                assert rows, (kind, state)
                expected = sum((1 if kind == "queue_items" else row.payload_bytes) for row in pending if row.state == state)
                assert rows[-1]["value"] == expected
                gauges[kind][state] = expected
            assert sum(gauges[kind].values()) == (snapshot.pending_items if kind == "queue_items" else snapshot.pending_bytes)
        state_observations.append(gauges)
    assert state_observations
    assert max(row["duration_ms"] for row in events if row["kind"] == "oldest_eligible") < 5000
    active_workers = [row["value"] for row in events if row["kind"] == "active_workers"]
    assert max(active_workers) == config.worker_count and active_workers[-1] == 0
    return {"queue_wait_ms": _percentiles(queue_waits), "run_time_ms": _percentiles(runtimes),
            "worker_claim_totals": claims, "state_observations": state_observations}


async def _queue_reference(reference, topology, rotation=0):
    service_mod, scheduler_mod, worker_mod, models, store_mod = _queue_contract()
    storage = postgres_binding_contract()(reference.dsn)
    manual = ManualClock()
    clock_origin = datetime(2026, 9, 27, tzinfo=timezone.utc)
    clock = lambda: clock_origin + timedelta(seconds=manual.now())
    events, acknowledgements, capacity_samples, fairness_samples = [], [], [], []
    keys, observations, event_monotonic_ns = [], [], []
    submission_key = ContextVar(f"sbr-submission-{rotation}", default=None)
    submission_operation = ContextVar(f"sbr-operation-{rotation}", default=None)
    project_labels = {}
    held = CausalGate()
    before_commit, after_commit = CausalGate(), CausalGate()
    active, active_by_project, active_max, project_max = 0, Counter(), 0, 0
    forbidden_labels = {"test-agent"} | {project.name for project in topology.projects} | {str(project.root) for project in topology.projects} | {caller.caller_id for caller in topology.callers}
    def emit(event, observed_now=None):
        events.append(_assert_d3_event(event, service_mod.BackgroundQueueEventV1, keys,
            clock() if observed_now is None else observed_now, forbidden_labels))
        event_monotonic_ns.append(time.monotonic_ns())
        if event.kind == "admission":
            key = submission_key.get()
            assert key in keys
            label = event.canonical_project_key_hash
            assert label is not None
            assert project_labels.setdefault(key, label) == label
            assert len(set(project_labels.values())) == len(project_labels) <= len(keys)
        if event.kind == "retry_after":
            operation = submission_operation.get()
            assert operation is not None, "busy retry event lost its actual submission"
            assert event.lane == operation.lane
            assert event.canonical_project_key_hash == project_labels[operation.canonical_project_key]
    limits = models.BackgroundQueueLimitsV1(max_pending_items=64, max_pending_bytes=65536,
        max_project_pending_items=8, max_project_pending_bytes=8192, retry_after_ms=10)
    config = service_mod.BackgroundServiceConfigV1(queue_limits=limits,
        scheduler=scheduler_mod.BackgroundSchedulerConfigV1(global_concurrency=4, max_project_concurrency=1,
            control_reserved_slots=0, durable_reserved_slots=0), worker_count=4, lease_ms=30000,
        retry_policy=worker_mod.SeededRetryPolicyV1(max_attempts=3, base_delay_ms=10,
            max_delay_ms=50, jitter_ms=0, seed=SEED), drain_deadline_ms=1000)
    accepted, busy_delays, handler_run_ms = {}, [], {}
    phase_started_ns = time.monotonic_ns()
    service = None
    try:
        await storage.setup()
        pool = await storage._ensure_pool()
        async with pool.acquire() as conn:
            # External idempotent effect sink, not a replacement receipt store.
            await conn.execute("CREATE TABLE IF NOT EXISTS sbr_reference_effects (operation_id text PRIMARY KEY, project_key text NOT NULL, fence bigint NOT NULL)")
        store = store_mod.BackgroundReceiptStoreV1(storage, clock=clock)
        for project in topology.projects:
            row = await storage.upsert_project(name=project.name, repo_root=str(project.root),
                progress_log_path=str(project.progress_log))
            keys.append(row.project_key)
        keys = keys[rotation:] + keys[:rotation]
        def op(name):
            return f"rotation-{rotation}-{name}"
        async def handler(receipt, probe):
            nonlocal active, active_max, project_max
            handler_started_ns = time.monotonic_ns()
            active += 1
            active_by_project[receipt.canonical_project_key] += 1
            active_max = max(active_max, active)
            project_max = max(project_max, active_by_project[receipt.canonical_project_key])
            assert active <= 4 and active_by_project[receipt.canonical_project_key] <= 1
            try:
                logical_id = receipt.operation_id.removeprefix(f"rotation-{rotation}-")
                if logical_id.startswith("held-"):
                    await held.hold()
                if logical_id == "precommit-cancel":
                    await before_commit.hold()
                if logical_id == "commit-cancel":
                    probe.mark_commit_started()
                    await after_commit.hold()
                if logical_id.startswith("retry-") and receipt.attempt_count == 1:
                    return worker_mod.BackgroundExecutionOutcomeV1("transient_failure", error_code="INJECTED_RETRY")
                if logical_id.startswith("permanent-"):
                    return worker_mod.BackgroundExecutionOutcomeV1("permanent_failure", error_code="INJECTED_PERMANENT")
                if probe.is_cancel_requested() and logical_id != "commit-cancel":
                    return worker_mod.BackgroundExecutionOutcomeV1("succeeded", result_ref="cancel-observed")
                probe.mark_commit_started()
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        current = await conn.fetchrow("SELECT fencing_token, state FROM background_receipts WHERE operation_id=$1 FOR UPDATE", receipt.operation_id)
                        assert current["state"] == "leased" and current["fencing_token"] == receipt.fencing_token
                        await conn.execute("INSERT INTO sbr_reference_effects VALUES ($1,$2,$3) ON CONFLICT (operation_id) DO NOTHING",
                            receipt.operation_id, receipt.canonical_project_key, receipt.fencing_token)
                return worker_mod.BackgroundExecutionOutcomeV1("succeeded", result_ref=receipt.operation_id)
            finally:
                handler_run_ms.setdefault(receipt.canonical_project_key, []).append((time.monotonic_ns() - handler_started_ns) // 1000000)
                active -= 1
                active_by_project[receipt.canonical_project_key] -= 1
        service = service_mod.BackgroundJobServiceV1(store, handler, config, clock=clock, emit=emit)
        await service.start()
        assert events and all(event["observed_at"] == clock_origin for event in events)
        # A second deterministic instant rejects cached-startup and wall-clock
        # emissions while leaving duration measurements under C12 authority.
        manual.advance(7250)
        def intent(operation_id, project_index):
            operation_id = op(operation_id)
            return models.BackgroundOperationIntentV1(operation_id=operation_id,
                canonical_project_key=keys[project_index % 16], lane="heavy", idempotency_key=operation_id,
                payload_digest=hashlib.sha256(operation_id.encode()).hexdigest(), payload_bytes=256,
                durability_class="durable", created_at=clock())
        async def submit_authorized(operation):
            token = submission_key.set(operation.canonical_project_key)
            operation_token = submission_operation.set(operation)
            try:
                return await service.submit(operation)
            finally:
                submission_operation.reset(operation_token)
                submission_key.reset(token)
        async def submit(operation):
            started = time.monotonic_ns()
            try:
                receipt = await submit_authorized(operation)
            except service_mod.BackgroundQueueBusyError as error:
                assert error.retry_after_ms > 0
                busy_delays.append((error.retry_after_ms, operation.lane,
                    project_labels[operation.canonical_project_key]))
                return None
            finally:
                acknowledgements.append((time.monotonic_ns() - started) / 1e6)
            accepted[receipt.operation_id] = receipt
            return receipt
        fair_receipts = await asyncio.gather(*(submit(intent(f"fair-{index}", index % 16)) for index in range(32)))
        assert all(receipt is not None for receipt in fair_receipts)
        async def fair_done():
            return all(row.state == "succeeded" for row in await asyncio.gather(
                *(service.get_status(op(f"fair-{index}")) for index in range(32))))
        await _wait_until(fair_done, deadline_seconds=10)
        assert set(project_labels) == set(keys)
        _driver_contract_boundaries(service_mod, scheduler_mod, keys, clock, list(project_labels.values()))
        sample = next(event for event in events if event["kind"] == "admission")
        for raw_label in set(keys) | forbidden_labels:
            with pytest.raises((ValueError, AssertionError)):
                leaked = service_mod.BackgroundQueueEventV1(**(sample | {
                    "canonical_project_key_hash": raw_label, "observed_at": clock()}))
                _assert_d3_event(leaked, service_mod.BackgroundQueueEventV1, keys, clock(), forbidden_labels)
        claims = dict((await service.health_snapshot()).metrics.worker_claims)
        assert len(claims) == 4 and max(claims.values()) - min(claims.values()) <= 1
        held_intent = intent("held-0", 0)
        await submit(held_intent)
        await asyncio.wait_for(held.entered.wait(), 5)
        # Thirty-two simultaneous submitters; two per canonical partition.
        operations = [intent(f"unit-{index}", index % 16) for index in range(32)]
        operations += [intent("retry-0", 1), intent("permanent-0", 2)]
        receipts = await asyncio.gather(*(submit(operation) for operation in operations))
        assert all(receipt is not None for receipt in receipts)
        duplicate = await submit_authorized(operations[0])
        assert duplicate.operation_id == receipts[0].operation_id
        with pytest.raises(service_mod.BackgroundDigestConflictError):
            await submit_authorized(replace(operations[0], payload_digest="f" * 64))
        # Saturate the held partition. Leased work must still consume capacity.
        overload = await asyncio.gather(*(submit(intent(f"overload-{index}", 0)) for index in range(32)))
        assert any(receipt is None for receipt in overload), "forced overload must have typed non-admissions"
        async def peers_completed():
            retry = await service.get_status(op("retry-0"))
            if retry.state == "retry_wait":
                assert retry.next_attempt_at is not None
                manual.advance(math.ceil(max(0, (retry.next_attempt_at - clock()).total_seconds()) * 1000))
            rows = await asyncio.gather(*(service.get_status(op(f"unit-{index}")) for index in range(32) if index % 16 != 0))
            snapshot = await store.recover(clock())
            peers = [row for row in snapshot.receipts if row.canonical_project_key != keys[0] and row.state in {"accepted", "ready", "leased", "retry_wait"}]
            return rows and all(row.state == "succeeded" for row in rows) and not peers
        await _wait_until(peers_completed, deadline_seconds=5)
        assert not held.release.is_set(), "peers must progress while project A remains blocked"
        # Keep A blocked for ten seconds; cap-blocked A is not continuously eligible.
        hold_started = time.monotonic()
        while time.monotonic() - hold_started < 10:
            snapshot = await store.recover(clock())
            observations.append({"snapshot": snapshot, "events_end": len(events)})
            leased = Counter(row.canonical_project_key for row in snapshot.receipts if row.state == "leased")
            capacity_samples.append({"items": snapshot.pending_items, "items_limit": 64,
                "bytes": snapshot.pending_bytes, "bytes_limit": 65536,
                "global": sum(leased.values()), "global_limit": 4,
                "project": max(leased.values(), default=0), "project_limit": 1,
                "heavy": sum(leased.values()), "heavy_limit": 4})
            assert snapshot.pending_items <= 64 and snapshot.pending_bytes <= 65536
            assert sum(leased.values()) <= 4 and max(leased.values(), default=0) <= 1
            await asyncio.sleep(.05)
        # Cancellation before claim of a queued item in A's occupied partition.
        candidate = next(receipt for receipt in overload if receipt is not None)
        current = await service.get_status(candidate.operation_id)
        cancellation = await service.cancel(current.operation_id, expected_state_version=current.state_version)
        assert cancellation.state == "cancelled"
        held.release.set()
        async def drained():
            snapshot = await store.recover(clock())
            return snapshot.pending_items == 0
        await _wait_until(drained, deadline_seconds=60)
        for operation_id, gate, terminal in (("precommit-cancel", before_commit, "cancelled"),
                                            ("commit-cancel", after_commit, "succeeded")):
            await submit(intent(operation_id, 5))
            await asyncio.wait_for(gate.entered.wait(), 5)
            leased = await service.get_status(op(operation_id))
            assert leased.state == "leased"
            await service.cancel(op(operation_id), expected_state_version=leased.state_version)
            gate.release.set()
            async def terminal_state():
                row = await service.get_status(op(operation_id))
                return row if row.state in {"succeeded", "cancelled", "failed_terminal"} else None
            outcome = await _wait_until(terminal_state, deadline_seconds=5)
            assert outcome.state == terminal
        status = {key: await service.get_status(key) for key in accepted}
        # The held partition admits exactly five overload receipts: its held
        # lease and two unit jobs retain three of the eight project slots.
        assert len(accepted) == 74 and sum(receipt is not None for receipt in overload) == 5
        assert all(row.state in {"succeeded", "failed_terminal", "cancelled"} for row in status.values())
        assert status[op("retry-0")].state == "succeeded" and status[op("retry-0")].attempt_count == 2
        assert status[op("permanent-0")].state == "failed_terminal" and status[op("permanent-0")].attempt_count == 1
        async with pool.acquire() as conn:
            effects = await conn.fetch("SELECT operation_id, project_key FROM sbr_reference_effects WHERE operation_id = ANY($1::text[])", list(accepted))
        succeeded = {key for key, row in status.items() if row.state == "succeeded"}
        assert {row["operation_id"] for row in effects} == succeeded
        assert len(effects) == len(succeeded)
        assert len(effects) == 71 and len(status) == 74
        assert all(row["project_key"] == status[row["operation_id"]].canonical_project_key for row in effects)
        health = await service.health_snapshot()
        assert health.metrics.starvation_windows_ge_5s == 0
        assert health.metrics.item_high_water <= 64 and health.metrics.byte_high_water <= 65536
        assert health.metrics.concurrency_high_water <= 4
        assert active_max <= health.metrics.concurrency_high_water
        assert sum(event["value"] for event in events if event["kind"] == "attempt" and event["outcome"] == "started") == sum(row.attempt_count for row in status.values())
        assert sum(event["value"] for event in events if event["kind"] == "retry" and event["outcome"] == "scheduled") == 1
        assert sum(event["value"] for event in events if event["kind"] == "dead_letter" and event["outcome"] == "failed_terminal") == 1
        shutdown_start = len(events)
        shutdown = await service.stop(drain_deadline_ms=1000)
        _assert_shutdown_events(events[shutdown_start:], shutdown, admitted=0)
        observations.append({"snapshot": await store.recover(clock()), "events_end": len(events)})
        assert shutdown.admission_closed and shutdown.workers_stopped == 4
        assert shutdown.remaining_recoverable == 0 and not shutdown.deadline_exceeded
        with pytest.raises(service_mod.BackgroundServiceShuttingDownError):
            await submit_authorized(intent("after-close", 3))
        await service.stop()
        assert sum(event["kind"] == "lifecycle" and event["outcome"] == "stopped" for event in events) == 1
        # Reconstruct from durable rows using a fresh service instance.
        restarted = service_mod.BackgroundJobServiceV1(store, handler, config, clock=clock, emit=emit)
        try:
            await restarted.start()
            assert (await restarted.health_snapshot()).accepting
            assert {key: await restarted.get_status(key) for key in accepted} == status
        finally:
            restart_stop_start = len(events)
            restart_shutdown = await restarted.stop()
            _assert_shutdown_events(events[restart_stop_start:], restart_shutdown, admitted=0)
        # Reconcile this service before the independent fault/recovery services emit.
        assert all(event["canonical_project_key_hash"] is None or event["canonical_project_key_hash"] in project_labels.values() for event in events)
        telemetry = _reconcile_queue_events(events, status, health, observations, config, project_labels, busy_delays, handler_run_ms, phase_started_ns)
        fairness = await _scheduler_fairness(storage, keys, limits, namespace=f"rotation-{rotation}")
        fairness_samples.extend(fairness["samples"])
        crash_probes = await _crash_fence_probe(reference, storage, keys[4], limits, namespace=f"rotation-{rotation}")
        checkpoint = await _checkpoint_restart_probe(storage, reference, handler, config, emit, models, keys[6], namespace=f"rotation-{rotation}")
        service_fence = await _service_fence_probe(storage, keys[7], config, emit, namespace=f"rotation-{rotation}", submission_key=submission_key)
        capacity_samples.extend(fairness["causal_windows"]["capacity_samples"])
        total_claims = Counter(telemetry["worker_claim_totals"]) + Counter(checkpoint["worker_claims"]) + Counter(service_fence["worker_claims"])
        assert sum(total_claims.values()) == sum(event["value"] for event in events if event["kind"] == "worker_claim")
        queue_waits = [event["duration_ms"] for event in events if event["kind"] == "queue_wait"]
        runtimes = [event["duration_ms"] for event in events if event["kind"] == "run_time"]
        assert len(queue_waits) == len(runtimes) == sum(total_claims.values())
        assert time.monotonic_ns() - phase_started_ns <= 60 * 10**9
        assert _percentiles(acknowledgements)["p95"] <= 500
        return {"config": asdict(config), "capacity_samples": capacity_samples,
            "fairness_samples": fairness_samples, "fairness_windows": fairness, "events": events,
            "event_monotonic_ns": event_monotonic_ns,
            "queue_wait_ms": _percentiles(queue_waits), "run_time_ms": _percentiles(runtimes),
            "worker_claim_totals": dict(total_claims), "state_observations": telemetry["state_observations"],
            "_project_labels": project_labels, "rotation": rotation, "fault_projects": {"overload": keys[0], "retry": keys[1], "permanent": keys[2],
                "cancellation": keys[5], "crash": keys[4], "checkpoint": keys[6],
                "restart": keys[6], "shutdown": keys[6], "service_fence": keys[7]},
            "phase_started_ns": phase_started_ns, "phase_ended_ns": time.monotonic_ns(),
            "admission_outcomes": dict(Counter(event["outcome"] for event in events if event["kind"] == "admission")),
            "receipt_acknowledgement_ms": _percentiles(acknowledgements),
            "accepted_count": len(accepted), "effect_count": len(effects),
            "item_high_water": health.metrics.item_high_water, "byte_high_water": health.metrics.byte_high_water,
            "global_concurrency_high_water": active_max, "project_concurrency_high_water": project_max,
            "shutdown": asdict(shutdown), "restart_shutdown": asdict(restart_shutdown),
            "restart_count": 1, "crash_fence_probes": crash_probes,
            "checkpoint_restart": checkpoint, "service_fence": service_fence, "accepted_operation_ids": sorted(accepted),
            "terminal_receipts": [asdict(row) for row in status.values()],
            "effects": [dict(row) for row in effects]}
    finally:
        held.release.set()
        before_commit.release.set()
        after_commit.release.set()
        if service is not None:
            await service.stop(drain_deadline_ms=1000)
        await storage.close()


async def _scheduler_fairness(storage, keys, limits, namespace):
    """D1 observations use real claims/transitions and the single C14 clock."""
    _, scheduler_mod, _, models, store_mod = _queue_contract()
    clock = ManualClock()
    origin = datetime(2026, 9, 27, tzinfo=timezone.utc)
    now = lambda: origin + timedelta(seconds=clock.now())
    store = store_mod.BackgroundReceiptStoreV1(storage, clock=now)
    pool = await storage._ensure_pool()
    samples, partial_rounds, sequences, windows = [], [], {}, {}
    limits = replace(limits, max_project_pending_items=12)
    cohort = keys[:3]
    for ordering in (0, 1):
        for weighted in (False, True):
            weights = ((cohort[0], 2), (cohort[1], 1), (cohort[2], 1)) if weighted else ()
            if ordering:
                weights = tuple(reversed(weights))
            prefix = f"{namespace}-{ordering}-{'weighted' if weighted else 'equal'}"
            intents = []
            for key in (cohort if ordering == 0 else list(reversed(cohort))):
                for index in range(12):
                    # Caller labels are deliberately duplicate/reordered; only
                    # the canonical partition can affect the service sequence.
                    label = "same-label" if ordering else f"caller-{index}"
                    operation_id = f"{prefix}-{label}-{key}-{index}"
                    intent = models.BackgroundOperationIntentV1(operation_id=operation_id, canonical_project_key=key,
                        lane="heavy", idempotency_key=operation_id, payload_digest=hashlib.sha256(operation_id.encode()).hexdigest(),
                        payload_bytes=1, durability_class="durable", created_at=now())
                    admission = await store.admit(intent, limits)
                    receipt = admission.receipt
                    assert receipt is not None
                    if receipt.state == "accepted":
                        await store.transition(receipt.operation_id, expected_state_version=receipt.state_version,
                            fencing_token=receipt.fencing_token, outcome=models.BackgroundTransitionOutcomeV1("ready"))
                    intents.append(intent)
            config = scheduler_mod.BackgroundSchedulerConfigV1(global_concurrency=3, max_project_concurrency=1,
                control_reserved_slots=1, durable_reserved_slots=0, control_quantum=1, durable_quantum=1,
                heavy_quantum=1, project_weights=weights)
            scheduler = scheduler_mod.BackgroundSchedulerV1(store, config, clock=now)
            await scheduler.recover()
            counts, sequence = Counter(), []
            last_service = {key: now() for key in cohort}
            complete_rounds, shares = 0, []
            for decision in range(36):
                common_eligible = all(counts[key] < 12 for key in cohort)
                eligibility_started = dict(last_service)
                receipt = await scheduler.claim_next(f"worker-{decision % 4}", lease_ms=1000)
                assert receipt is not None
                key = receipt.canonical_project_key
                wait_ms = int((now() - last_service[key]).total_seconds() * 1000)
                assert 0 <= wait_ms < 5000
                last_service[key] = now()
                counts[key] += 1
                sequence.append(key)
                async with pool.acquire() as conn:
                    await conn.execute("INSERT INTO sbr_reference_effects VALUES ($1,$2,$3) ON CONFLICT (operation_id) DO NOTHING",
                        receipt.operation_id, key, receipt.fencing_token)
                await store.transition(receipt.operation_id, expected_state_version=receipt.state_version,
                    fencing_token=receipt.fencing_token, outcome=models.BackgroundTransitionOutcomeV1("succeeded", result_ref=receipt.operation_id))
                if common_eligible:
                    normalized = [counts[key] / (2 if weighted and key == cohort[0] else 1) for key in cohort]
                    assert max(normalized) - min(normalized) <= 1
                    partial_rounds.append({"ordering": ordering, "weighted": weighted, "decision": decision + 1,
                        "counts": {key: counts[key] for key in cohort}, "normalized_counts": normalized,
                        "eligible_since": {key: eligibility_started[key].isoformat() for key in cohort},
                        "service_at": now().isoformat(), "observed_wait_ms": wait_ms,
                        "complete_round": (decision + 1) % (4 if weighted else 3) == 0})
                    if (decision + 1) % (4 if weighted else 3) == 0:
                        complete_rounds += 1
                        assert [counts[key] for key in cohort] == ([2 * complete_rounds, complete_rounds, complete_rounds] if weighted else [complete_rounds] * 3)
                        share = max(counts.values()) / sum(counts.values())
                        shares.append(share)
                        samples.append({"lead_units": max(normalized) - min(normalized),
                            "eligible_peer_share": share,
                            "starvation_ms": max(wait_ms, max(int((now() - last_service[key]).total_seconds() * 1000) for key in cohort))})
                clock.advance(250)
            assert counts == Counter({key: 12 for key in cohort}) and complete_rounds >= 3
            metrics = scheduler.metrics_snapshot()
            if inspect.isawaitable(metrics):
                metrics = await metrics
            assert metrics.starvation_windows_ge_5s == 0
            claims = dict(metrics.worker_claims)
            assert len(claims) == 4 and max(claims.values()) - min(claims.values()) <= 1
            async with pool.acquire() as conn:
                effects = await conn.fetch("SELECT operation_id FROM sbr_reference_effects WHERE operation_id = ANY($1::text[])",
                    [intent.operation_id for intent in intents])
            assert len(effects) == len({row["operation_id"] for row in effects}) == 36
            windows[ordering, weighted] = set(shares)
            sequences[ordering, weighted] = sequence
    assert windows[0, False] == windows[1, False] == {1/3}
    assert windows[0, True] == windows[1, True] == {.5}
    assert sequences[0, False] == sequences[1, False]
    assert sequences[0, True] == sequences[1, True]
    assert any(not row["complete_round"] for row in partial_rounds if row["weighted"])
    causal = await _scheduler_causal_windows(store, storage, keys, limits, now, clock, namespace)
    return {"samples": samples, "partial_rounds": partial_rounds, "causal_windows": causal,
        "canonical_sequences": {f"{order}:{weighted}": value for (order, weighted), value in sequences.items()}}


async def _scheduler_causal_windows(store, storage, keys, limits, now, clock, namespace):
    """Hold actual leases across decisions; never emulate scheduler choices."""
    _, scheduler_mod, _, models, _ = _queue_contract()
    pool = await storage._ensure_pool()
    receipts, capacity, waits = [], [], []
    async def ready(name, key, lane="heavy", allow_busy=False):
        operation_id = f"{namespace}-causal-{name}"
        admitted = await store.admit(models.BackgroundOperationIntentV1(operation_id=operation_id,
            canonical_project_key=key, lane=lane, idempotency_key=operation_id,
            payload_digest=hashlib.sha256(operation_id.encode()).hexdigest(), payload_bytes=1,
            durability_class="durable", created_at=now()), limits)
        row = admitted.receipt
        if row is None and allow_busy:
            assert admitted.status == "busy" and admitted.retry_after_ms == limits.retry_after_ms
            return None
        assert row is not None
        if row.state == "accepted":
            row = await store.transition(row.operation_id, row.state_version, row.fencing_token,
                models.BackgroundTransitionOutcomeV1("ready"))
        receipts.append(row)
        return row
    async def finish(row):
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO sbr_reference_effects VALUES ($1,$2,$3)",
                row.operation_id, row.canonical_project_key, row.fencing_token)
        return await store.transition(row.operation_id, row.state_version, row.fencing_token,
            models.BackgroundTransitionOutcomeV1("succeeded", result_ref=row.operation_id))
    config = scheduler_mod.BackgroundSchedulerConfigV1(global_concurrency=4, max_project_concurrency=1,
        control_reserved_slots=1, durable_reserved_slots=1, project_weights=((keys[15], 99),))
    scheduler = scheduler_mod.BackgroundSchedulerV1(store, config, clock=now)
    submitted_a = await asyncio.gather(*(ready(f"A-{index}", keys[0], allow_busy=True) for index in range(31)))
    accepted_a = [row for row in submitted_a if row is not None]
    assert len(accepted_a) == limits.max_project_pending_items == 12
    assert sum(row is None for row in submitted_a) == 19
    await ready("B", keys[1])
    await scheduler.recover()
    held = [await scheduler.claim_next(f"cap-{index}", lease_ms=30000) for index in range(2)]
    assert all(held) and {row.canonical_project_key for row in held} == set(keys[:2])
    gate = CausalGate()
    blockers = [asyncio.create_task(gate.hold()) for _ in held]
    try:
        await gate.entered.wait()
        peer = await ready("C", keys[2])
        assert await scheduler.claim_next("blocked-heavy", lease_ms=30000) is None
        # Cap-blocked work is not continuously eligible even across 5 seconds.
        clock.advance(5100)
        control = await ready("control", keys[3], "control")
        durable = await ready("durable", keys[4], "durable")
        eligible_at = now()
        reserved = []
        for decision in range(2):
            row = await scheduler.claim_next(f"reserved-{decision}", lease_ms=30000)
            assert row is not None
            reserved.append(row)
            snapshot = await store.recover(now())
            leased = [item for item in snapshot.receipts if item.state == "leased"]
            by_lane = Counter(item.lane for item in leased)
            by_project = Counter(item.canonical_project_key for item in leased)
            assert len(leased) <= 4 and max(by_project.values()) <= 1
            assert by_lane["heavy"] <= 2 and by_lane["heavy"] + by_lane["durable"] <= 3
            assert snapshot.pending_items <= limits.max_pending_items and snapshot.pending_bytes <= limits.max_pending_bytes
            pending = [item for item in snapshot.receipts if item.state in {"accepted", "ready", "leased", "retry_wait"}]
            assert max(Counter(item.canonical_project_key for item in pending).values()) <= limits.max_project_pending_items
            assert all(sum(item.payload_bytes for item in pending if item.canonical_project_key == key) <= limits.max_project_pending_bytes for key in keys)
            capacity.append({"items": snapshot.pending_items, "items_limit": limits.max_pending_items,
                "bytes": snapshot.pending_bytes, "bytes_limit": limits.max_pending_bytes,
                "global": len(leased), "global_limit": 4, "project": max(by_project.values()),
                "project_limit": 1, "heavy": by_lane["heavy"], "heavy_limit": 2})
            waits.append(int((now() - eligible_at).total_seconds() * 1000))
            clock.advance(100)
        assert {row.operation_id for row in reserved} == {control.operation_id, durable.operation_id}
        assert await scheduler.claim_next("global-cap", lease_ms=30000) is None
        for row in reserved:
            await finish(row)
        # B completes and C claims before the saturated A caller cohort releases.
        row_b = next(row for row in held if row.canonical_project_key == keys[1])
        await finish(row_b)
        row_c = await scheduler.claim_next("peer-C", lease_ms=30000)
        assert row_c is not None and row_c.operation_id == peer.operation_id
        await finish(row_c)
        assert not gate.release.is_set()
        gate.release.set()
        await asyncio.gather(*blockers)
        await finish(next(row for row in held if row.canonical_project_key == keys[0]))
        # Remaining A work drains under the same cap, with actual effects.
        for index in range(len(accepted_a) - 1):
            row = await scheduler.claim_next(f"drain-{index % 4}", lease_ms=30000)
            assert row is not None and row.canonical_project_key == keys[0]
            await finish(row)
        assert await scheduler.claim_next("empty", lease_ms=30000) is None
        # Retry-not-due consumes neither a turn nor a capacity slot.
        retry = await ready("retry", keys[0])
        first = await scheduler.claim_next("retry-first", lease_ms=30000)
        assert first.operation_id == retry.operation_id
        due = now() + timedelta(seconds=1)
        await store.transition(first.operation_id, first.state_version, first.fencing_token,
            models.BackgroundTransitionOutcomeV1("retry_wait", next_attempt_at=due))
        peer = await ready("retry-peer", keys[1])
        next_peer = await scheduler.claim_next("retry-peer", lease_ms=30000)
        assert next_peer.operation_id == peer.operation_id
        await finish(next_peer)
        assert await scheduler.claim_next("not-due", lease_ms=30000) is None
        before_due = await store.get(first.operation_id)
        assert before_due.state == "retry_wait" and before_due.attempt_count == 1
        clock.advance(1000)
        retried = await scheduler.claim_next("due", lease_ms=30000)
        assert retried.operation_id == first.operation_id and retried.fencing_token == first.fencing_token + 1
        await finish(retried)
        # A distinct outer-lane sensitivity window, with project weights fixed.
        lane_sequences = {}
        for quantum in (1, 3):
            lane_ids = []
            for lane, key in zip(("control", "durable", "heavy"), keys[5:8]):
                for index in range(12):
                    lane_ids.append((await ready(f"lane-{quantum}-{lane}-{index}", key, lane)).operation_id)
            lane_scheduler = scheduler_mod.BackgroundSchedulerV1(store, replace(config,
                control_quantum=quantum, durable_quantum=1, heavy_quantum=1), clock=now)
            await lane_scheduler.recover()
            counts, sequence = Counter(), []
            for index in range(36):
                row = await lane_scheduler.claim_next(f"lane-{index % 4}", lease_ms=30000)
                assert row is not None
                sequence.append(row.lane)
                counts[row.lane] += 1
                await finish(row)
                if index < (12 if quantum == 1 else 20) and (index + 1) % (quantum + 2) == 0:
                    rounds = (index + 1) // (quantum + 2)
                    assert counts == Counter({"control": quantum * rounds, "durable": rounds, "heavy": rounds})
                clock.advance(100)
            assert counts == Counter({"control": 12, "durable": 12, "heavy": 12})
            lane_sequences[quantum] = sequence
        assert lane_sequences[1][:5] != lane_sequences[3][:5]
        metrics = scheduler.metrics_snapshot()
        if inspect.isawaitable(metrics):
            metrics = await metrics
        assert metrics.starvation_windows_ge_5s == 0 and max(waits) < 5000
        async with pool.acquire() as conn:
            effect_ids = await conn.fetch("SELECT operation_id FROM sbr_reference_effects WHERE operation_id = ANY($1::text[])",
                [row.operation_id for row in receipts])
        assert len(effect_ids) == len(receipts) == len({row["operation_id"] for row in effect_ids})
        return {"capacity_samples": capacity, "control_wait_ms": waits, "blocked_seconds": 5.1,
            "lane_sequences": lane_sequences, "receipt_count": len(receipts), "effect_count": len(effect_ids),
            "a_submission_count": 31, "a_accepted_count": len(accepted_a), "a_busy_count": 19, "limits": asdict(limits)}
    finally:
        gate.release.set()
        await asyncio.gather(*blockers)


def _crashing_worker(dsn, key, phase, output, gate):
    async def run():
        _, scheduler_mod, worker_mod, _, store_mod = _queue_contract()
        storage = postgres_binding_contract()(dsn)
        try:
            await storage.setup()
            clock = lambda: datetime.now(timezone.utc)
            store = store_mod.BackgroundReceiptStoreV1(storage, clock=clock)
            scheduler = scheduler_mod.BackgroundSchedulerV1(store,
                scheduler_mod.BackgroundSchedulerConfigV1(global_concurrency=1, max_project_concurrency=1,
                    control_reserved_slots=0, durable_reserved_slots=0), clock=clock)
            await scheduler.recover()
            async def handler(receipt, probe):
                if phase == "post-effect":
                    probe.mark_commit_started()
                    pool = await storage._ensure_pool()
                    async with pool.acquire() as conn:
                        await conn.execute("INSERT INTO sbr_reference_effects VALUES ($1,$2,$3) ON CONFLICT (operation_id) DO NOTHING",
                            receipt.operation_id, key, receipt.fencing_token)
                output.put(receipt)
                await asyncio.to_thread(gate.wait, 60)
                return worker_mod.BackgroundExecutionOutcomeV1("succeeded", result_ref=receipt.operation_id)
            worker = worker_mod.BackgroundWorkerV1("crash-worker", scheduler, store, handler,
                worker_mod.SeededRetryPolicyV1(max_attempts=3, base_delay_ms=10, max_delay_ms=10, jitter_ms=0, seed=SEED),
                lease_ms=100, clock=clock)
            await worker.run_once()
        finally:
            await storage.close()
    asyncio.run(run())


async def _crash_fence_probe(reference, storage, key, limits, namespace):
    _, scheduler_mod, worker_mod, models, store_mod = _queue_contract()
    context = multiprocessing.get_context("spawn")
    clock = lambda: datetime.now(timezone.utc)
    store = store_mod.BackgroundReceiptStoreV1(storage, clock=clock)
    pool = await storage._ensure_pool()
    faults = []
    for phase in ("pre-effect", "post-effect"):
        operation_id = f"{namespace}-crash-{phase}"
        intent = models.BackgroundOperationIntentV1(operation_id=operation_id, canonical_project_key=key,
            lane="heavy", idempotency_key=operation_id, payload_digest=hashlib.sha256(operation_id.encode()).hexdigest(),
            payload_bytes=1, durability_class="durable", created_at=clock())
        admission = await store.admit(intent, limits)
        receipt = admission.receipt
        assert receipt is not None
        if receipt.state == "accepted":
            await store.transition(operation_id, expected_state_version=receipt.state_version,
                fencing_token=receipt.fencing_token, outcome=models.BackgroundTransitionOutcomeV1("ready"))
        output, gate = context.Queue(), context.Event()
        child = context.Process(target=_crashing_worker, args=(reference.dsn, key, phase, output, gate))
        try:
            child.start()
            claimed = await asyncio.to_thread(output.get, True, 10)
            assert claimed.operation_id == operation_id and claimed.fencing_token > 0
            child.terminate()  # deliberate death of this test-owned worker only
            await asyncio.to_thread(child.join, 10)
            assert child.exitcode is not None and not child.is_alive()
            async def reclaimable():
                return operation_id in (await store.recover(clock())).reclaimable_operation_ids
            await _wait_until(reclaimable, deadline_seconds=5)
            scheduler = scheduler_mod.BackgroundSchedulerV1(store,
                scheduler_mod.BackgroundSchedulerConfigV1(global_concurrency=1, max_project_concurrency=1,
                    control_reserved_slots=0, durable_reserved_slots=0), clock=clock)
            await scheduler.recover()
            async def effect(receipt, probe):
                assert receipt.fencing_token > claimed.fencing_token
                probe.mark_commit_started()
                async with pool.acquire() as conn:
                    await conn.execute("INSERT INTO sbr_reference_effects VALUES ($1,$2,$3) ON CONFLICT (operation_id) DO NOTHING",
                        receipt.operation_id, key, receipt.fencing_token)
                return worker_mod.BackgroundExecutionOutcomeV1("succeeded", result_ref=operation_id)
            worker = worker_mod.BackgroundWorkerV1("replacement-worker", scheduler, store, effect,
                worker_mod.SeededRetryPolicyV1(max_attempts=3, base_delay_ms=10, max_delay_ms=10, jitter_ms=0, seed=SEED),
                lease_ms=100, clock=clock)
            step = await worker.run_once()
            assert step.outcome == "succeeded"
            final = await store.get(operation_id)
            assert final.state == "succeeded" and final.fencing_token > claimed.fencing_token
            with pytest.raises(models.BackgroundStaleFenceError):
                await store.transition(operation_id, expected_state_version=claimed.state_version,
                    fencing_token=claimed.fencing_token,
                    outcome=models.BackgroundTransitionOutcomeV1("succeeded", result_ref="late-worker"))
            assert await store.get(operation_id) == final
            async with pool.acquire() as conn:
                assert await conn.fetchval("SELECT count(*) FROM sbr_reference_effects WHERE operation_id=$1", operation_id) == 1
            faults.append({"phase": phase, "old_fence": claimed.fencing_token,
                "new_fence": final.fencing_token, "stale_completion_rejected": True, "effect_count": 1})
        finally:
            gate.set()
            if child.pid is not None:
                if child.is_alive():
                    child.terminate()
                await asyncio.to_thread(child.join, 10)
                assert not child.is_alive()
                child.close()
            output.close()
            output.join_thread()
    return faults


async def _checkpoint_restart_probe(storage, reference, handler, config, emit, models, key, namespace):
    service_mod, _, _, _, store_mod = _queue_contract()
    # Seed a real persisted cohort before workers start. A live, unexpired
    # orphan lease cap-blocks this project, so none of its ready work can race
    # the exact ready/leased/retry-wait checkpoint observation.
    manual = ManualClock()
    origin = datetime.now(timezone.utc) - timedelta(seconds=60)
    now = lambda: origin + timedelta(seconds=manual.now())
    backend = storage
    storage_type = postgres_binding_contract()
    phase_store = store_mod.BackgroundReceiptStoreV1(backend, clock=now)
    receipts = []
    config = replace(config, lease_ms=1000)
    for index in range(8):
        operation_id = f"{namespace}-checkpoint-{index}"
        admitted = await phase_store.admit(models.BackgroundOperationIntentV1(operation_id=operation_id,
            canonical_project_key=key, lane="heavy", idempotency_key=operation_id,
            payload_digest=hashlib.sha256(operation_id.encode()).hexdigest(), payload_bytes=1,
            durability_class="durable", created_at=now()), config.queue_limits)
        row = admitted.receipt
        assert row is not None
        if row.state == "accepted":
            row = await phase_store.transition(row.operation_id, row.state_version, row.fencing_token,
                models.BackgroundTransitionOutcomeV1("ready"))
        receipts.append(row)
    partition = _required("scribe_mcp.background.models", "BackgroundPartitionV1").BackgroundPartitionV1(key, "heavy")
    retry = await phase_store.claim(partition, "checkpoint-retry", 1000)
    assert retry is not None
    retry = await phase_store.transition(retry.operation_id, retry.state_version, retry.fencing_token,
        models.BackgroundTransitionOutcomeV1("retry_wait", next_attempt_at=now() + timedelta(seconds=10)))
    orphan = await phase_store.claim(partition, "checkpoint-orphan", 30000)
    assert orphan is not None and orphan.operation_id != retry.operation_id
    cancelled = receipts[-1]
    await phase_store.transition(cancelled.operation_id, cancelled.state_version, cancelled.fencing_token,
        models.BackgroundTransitionOutcomeV1("cancelled", cancel_requested=True))
    survivor_ids = {row.operation_id for row in receipts} - {cancelled.operation_id}
    before = await phase_store.recover(now())
    cohort = {row.operation_id: row for row in before.receipts if row.operation_id in survivor_ids}
    assert set(cohort) == survivor_ids and len(cohort) == 7
    assert Counter(row.state for row in cohort.values()) == Counter({"ready": 5, "leased": 1, "retry_wait": 1})
    restarted, fresh_storage = None, None
    events, draining_seen = [], asyncio.Event()
    def record(event):
        assert event.observed_at == now(), "checkpoint events must use the injected C14 clock"
        events.append(asdict(event))
        emit(event, observed_now=now())
        if (event.kind, event.outcome) == ("lifecycle", "draining"):
            draining_seen.set()
    stopped_service = service_mod.BackgroundJobServiceV1(phase_store, handler, config, clock=now, emit=record)
    try:
        await stopped_service.start()
        assert (await stopped_service.health_snapshot()).recovered_receipts == 7
        assert sum(row["value"] for row in events if row["kind"] == "recovery") == 7
        assert not any(row["kind"] == "admission" for row in events)
        shutdown_start = len(events)
        stopping = asyncio.create_task(stopped_service.stop(drain_deadline_ms=1))
        await asyncio.wait_for(draining_seen.wait(), .5)
        manual.advance(10)
        stopped = await asyncio.wait_for(stopping, .5)
        persisted = await phase_store.recover(now())
        pending = {row.operation_id: row for row in persisted.receipts if row.state in {"accepted", "ready", "leased", "retry_wait"}}
        assert set(pending) == survivor_ids, "checkpoint must preserve a nonempty exact cohort"
        assert Counter(row.state for row in pending.values()) == Counter({"ready": 5, "leased": 1, "retry_wait": 1})
        assert stopped.admission_closed and stopped.workers_stopped == config.worker_count
        assert stopped.remaining_recoverable == stopped.checkpointed == persisted.pending_items == 7
        assert stopped.cancelled_retryable == stopped.drained == 0
        _assert_shutdown_events(events[shutdown_start:], stopped, admitted=0)
        stopped_events = len([row for row in events if row["kind"] == "lifecycle" and row["outcome"] == "stopped"])
        await stopped_service.stop()
        assert len([row for row in events if row["kind"] == "lifecycle" and row["outcome"] == "stopped"]) == stopped_events == 1
        # A fresh storage/store/service proves reconstruction rather than an
        # in-memory queue surviving stop. The original fixture still owns DB.
        dsn = reference.dsn
        await backend.close()
        manual.advance(31000)
        fresh_storage = storage_type(dsn)
        await fresh_storage.setup()
        fresh_pool = await fresh_storage._ensure_pool()
        fresh_store = store_mod.BackgroundReceiptStoreV1(fresh_storage, clock=now)
        observed = []
        async def recovered_handler(receipt, probe):
            assert receipt.operation_id in survivor_ids
            assert receipt.fencing_token > cohort[receipt.operation_id].fencing_token
            probe.mark_commit_started()
            async with fresh_pool.acquire() as conn:
                await conn.execute("INSERT INTO sbr_reference_effects VALUES ($1,$2,$3)",
                    receipt.operation_id, receipt.canonical_project_key, receipt.fencing_token)
            observed.append((receipt.operation_id, receipt.fencing_token))
            return _queue_contract()[2].BackgroundExecutionOutcomeV1("succeeded", result_ref=receipt.operation_id)
        recovery_start = len(events)
        restarted = service_mod.BackgroundJobServiceV1(fresh_store, recovered_handler, config, clock=now, emit=record)
        await restarted.start()
        async def recovered():
            rows = await asyncio.gather(*(fresh_store.get(row.operation_id) for row in receipts))
            return rows if all(row.state in {"succeeded", "cancelled"} for row in rows) else None
        rows = await _wait_until(recovered, deadline_seconds=60)
        assert len(rows) == len(receipts) == 8
        assert {row.operation_id for row in rows if row.state == "succeeded"} == survivor_ids
        assert {row.operation_id for row in rows if row.state == "cancelled"} == {cancelled.operation_id}
        assert len(observed) == len({operation_id for operation_id, _ in observed}) == 7
        recovery_events = events[recovery_start:]
        assert sum(row["value"] for row in recovery_events if row["kind"] == "recovery") == 7
        assert not any(row["kind"] == "admission" for row in recovery_events)
        assert sum(row["value"] for row in recovery_events if row["kind"] == "worker_claim") == 7
        async with fresh_pool.acquire() as conn:
            effects = await conn.fetch("SELECT operation_id, fence FROM sbr_reference_effects WHERE operation_id = ANY($1::text[])",
                [row.operation_id for row in receipts])
        assert {row["operation_id"] for row in effects} == survivor_ids
        assert len(effects) == 7
        assert {row["operation_id"]: row["fence"] for row in effects} == dict(observed)
        recovered_health = await restarted.health_snapshot()
        assert recovered_health.recovered_receipts == 7
        assert sum(dict(recovered_health.metrics.worker_claims).values()) == 7
        assert sum(row["value"] for row in recovery_events if row["kind"] == "lease" and row["outcome"] == "expired") == 1
        shutdown_start = len(events)
        final_stop = await restarted.stop(drain_deadline_ms=1000)
        _assert_shutdown_events(events[shutdown_start:], final_stop, admitted=0)
        assert final_stop.remaining_recoverable == 0
        return {"shutdown": asdict(stopped), "accepted_count": 8, "recovered_terminal_count": 8,
            "restart_shutdown": asdict(final_stop),
            "survivor_count": 7, "effect_count": 7,
            "worker_claims": dict(recovered_health.metrics.worker_claims),
            "before_states": {operation_id: asdict(row) for operation_id, row in cohort.items()},
            "recovered_fences": dict(observed), "cancelled_count": 1, "events": events}
    finally:
        await stopped_service.stop(drain_deadline_ms=1000)
        if restarted is not None:
            await restarted.stop(drain_deadline_ms=1000)
        if fresh_storage is not None:
            await fresh_storage.close()
        # Restore the caller's independently owned handle for later rotations.
        await backend.setup()


async def _service_fence_probe(storage, key, config, emit, namespace, submission_key=None):
    """A real replacement service completes while the expired owner is held."""
    service_mod, _, worker_mod, models, store_mod = _queue_contract()
    manual = ManualClock()
    origin = datetime.now(timezone.utc) - timedelta(seconds=1)
    now = lambda: origin + timedelta(seconds=manual.now())
    store = store_mod.BackgroundReceiptStoreV1(storage, clock=now)
    gate, events = CausalGate(), []
    operation_id = f"{namespace}-service-stale-fence"
    config = replace(config, worker_count=1, lease_ms=100,
        scheduler=replace(config.scheduler, global_concurrency=1))
    def record(event):
        assert event.observed_at == now(), "fence events must use the injected C14 clock"
        events.append(asdict(event))
        if event.kind == "admission":
            # This dedicated service admits only this already-authorized key.
            token = submission_key.set(key) if submission_key is not None else None
            try:
                emit(event, observed_now=now())
            finally:
                if submission_key is not None:
                    submission_key.reset(token)
        else:
            emit(event, observed_now=now())
    async def old_handler(receipt, probe):
        await gate.hold()
        return worker_mod.BackgroundExecutionOutcomeV1("succeeded", result_ref=operation_id)
    async def replacement_handler(receipt, probe):
        probe.mark_commit_started()
        pool = await storage._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO sbr_reference_effects VALUES ($1,$2,$3)", operation_id, key, receipt.fencing_token)
        return worker_mod.BackgroundExecutionOutcomeV1("succeeded", result_ref=operation_id)
    old = service_mod.BackgroundJobServiceV1(store, old_handler, config, clock=now, emit=record)
    replacement = service_mod.BackgroundJobServiceV1(store, replacement_handler, config, clock=now, emit=record)
    try:
        await old.start()
        await old.submit(models.BackgroundOperationIntentV1(operation_id=operation_id, canonical_project_key=key,
            lane="heavy", idempotency_key=operation_id, payload_digest=hashlib.sha256(operation_id.encode()).hexdigest(),
            payload_bytes=1, durability_class="durable", created_at=now()))
        await asyncio.wait_for(gate.entered.wait(), 5)
        original = await store.get(operation_id)
        assert original.state == "leased" and original.fencing_token == 1
        manual.advance(200)
        await replacement.start()
        async def done():
            row = await store.get(operation_id)
            return row if row.state == "succeeded" else None
        final = await _wait_until(done, deadline_seconds=5)
        assert final.fencing_token == 2 and final.attempt_count == 2
        gate.release.set()
        async def stale_observed():
            health = await old.health_snapshot()
            return health if health.stale_fence_rejections == 1 else None
        old_health = await _wait_until(stale_observed, deadline_seconds=5)
        replacement_health = await replacement.health_snapshot()
        assert replacement_health.recovered_receipts == 1
        assert sum(row["value"] for row in events if row["kind"] == "recovery") == 1
        assert await store.get(operation_id) == final
        for kind, outcome, count in (("worker_claim", "claimed", 2), ("attempt", "started", 2),
                                    ("lease", "expired", 1), ("fence", "stale_fence", 1),
                                    ("run_time", "stale_fence", 1), ("run_time", "succeeded", 1)):
            assert sum(row["value"] for row in events if row["kind"] == kind and row["outcome"] == outcome) == count
        pool = await storage._ensure_pool()
        async with pool.acquire() as conn:
            effects = await conn.fetch("SELECT fence FROM sbr_reference_effects WHERE operation_id=$1", operation_id)
        assert len(effects) == 1 and effects[0]["fence"] == final.fencing_token
        claims = Counter(dict(old_health.metrics.worker_claims)) + Counter(dict(replacement_health.metrics.worker_claims))
        assert sum(claims.values()) == 2
        shutdowns = []
        for service in (old, replacement):
            start = len(events)
            receipt = await service.stop(drain_deadline_ms=1000)
            _assert_shutdown_events(events[start:], receipt, admitted=0)
            shutdowns.append(asdict(receipt))
        return {"old_fence": 1, "current_fence": final.fencing_token, "effect_count": 1,
            "worker_claims": dict(claims), "events": events, "shutdown_receipts": shutdowns}
    finally:
        gate.release.set()
        await old.stop(drain_deadline_ms=1000)
        await replacement.stop(drain_deadline_ms=1000)


def _throughput(rows):
    events = [event for row in rows for event in row["events"] if event["measurement"]]
    assert events
    elapsed = (max(event["ended_ns"] for event in events) - min(event["started_ns"] for event in events)) / 1e9
    return len(events) / elapsed


def _reference_budgets(rows, isolated, *, require_soak):
    events = [event for row in rows for event in row["events"] if event["measurement"]]
    reads = _percentiles([event["duration_ms"] for event in events if event["kind"] in {"read", "reconnect"}])
    foreground = _percentiles([event["duration_ms"] for event in events])
    assert reads["p50"] <= 75 and reads["p95"] <= 250
    assert foreground["p95"] <= 500
    envelopes = [envelope for event in events for envelope in event["envelopes"]]
    assert len(envelopes) == len(events)
    for envelope in envelopes:
        assert envelope["accounted_ratio"] >= .95 and envelope["correlation_id"]
        assert envelope["slow_stages"] == [phase for phase, value in envelope["phases_ms"].items()
            if phase != "unaccounted" and value > 100]
        assert envelope["tripwire_exceeded"] == (bool(envelope["slow_stages"]) or envelope["total_ms"] > 500)
    throughput = _throughput(rows)
    assert throughput >= 50
    assert len(isolated) == 4 and all(value > 0 for value in isolated)
    assert throughput >= .75 * sum(isolated)
    rss_results = []
    for row in rows:
        samples = row["rss"]
        peak_growth = max(value for _, value in samples) - samples[0][1]
        retained = samples[-1][1] - samples[0][1]
        assert peak_growth <= 256 * 1024**2 and retained <= 64 * 1024**2
        tail = [(at / 1e9 / 60, value / 1024**2) for at, value in samples
            if row["measurement_end_ns"] - 1200 * 1e9 <= at <= row["measurement_end_ns"]]
        if require_soak:
            assert tail[-1][0] - tail[0][0] >= 19.9, "final twenty-minute RSS window is incomplete"
            slope = statistics.linear_regression([at for at, _ in tail], [value for _, value in tail]).slope
            assert slope <= 2
        else:
            slope = None
        rss_results.append({"peak_growth_bytes": peak_growth, "retained_bytes": retained,
            "final_20_minute_slope_mib_per_minute": slope, "raw_samples": samples})
    # The fixed corpus's denials are injected. Any other exception fails the child;
    # therefore none is silently removed from a latency/error denominator.
    return {"read": reads, "foreground": foreground, "throughput_ops_per_second": throughput,
        "isolated_eight_caller_throughputs": isolated, "rss": rss_results,
        "transient_non_injected_error_rate": 0, "raw_events": events}


async def run_reference_stress(profile: StressProfile, *, postgres, source_revision: str, results_dir: Path) -> SwarmResultsV1:
    """One C14 result family for smoke, queue, release and extended profiles."""
    _runtime_contract()
    _queue_contract()
    fixture_contract()
    assert re.fullmatch(r"[0-9a-f]{40}", source_revision)
    assert os.environ.get("SCRIBE_SWARM_DISPOSABLE") == "1", "explicit disposable reference opt-in required"
    assert importlib.util.find_spec("psutil") is not None, "reference RSS sampler unavailable"
    results_dir.mkdir(parents=True, exist_ok=True)
    # The canonical persona comes from the pytest caller, never a novel identity.
    agent = "test-agent"
    topology = build_swarm_topology(results_dir / "topology", agent_label=agent, seed=profile.seed)
    if profile.callers != 32:
        topology = replace(topology, callers=tuple(replace(caller, caller_id=f"cohort-{cohort}-{caller.caller_id}")
            for cohort in range(profile.callers // 32) for caller in topology.callers))
    isolated = []
    # Four isolated eight-caller runs, on the same backend/source/profile.
    for index in range(4):
        isolated_root = results_dir / f"isolated-{index}"
        isolated_root.mkdir()
        isolated_topology = build_swarm_topology(isolated_root / "topology", agent_label=agent, seed=profile.seed + index + 1)
        isolated_topology = replace(isolated_topology, callers=isolated_topology.callers[index * 8:(index + 1) * 8])
        baseline = await asyncio.to_thread(_run_runtime_processes, profile, dsn=postgres.dsn,
            topology=isolated_topology, workdir=isolated_root, agent=agent, isolated=True)
        isolated.append(_throughput(baseline))
        baseline_result = reconcile_exact_effects([item for row in baseline for item in row["expected"]],
            [item for row in baseline for item in row["observed"]], metadata=SwarmRunMetadata(
                source_revision=source_revision, seed=profile.seed,
                topology=isolated_topology.as_json_dict(), set_project_count={key: count for row in baseline for key, count in row["bind_counts"].items()}))
        assert baseline_result.verdict == "PASS", baseline_result.as_json_dict()
    process_baseline = set(multiprocessing.active_children())
    rows = await asyncio.to_thread(_run_runtime_processes, profile, dsn=postgres.dsn,
        topology=topology, workdir=results_dir, agent=agent)
    expected = [item for row in rows for item in row["expected"]]
    observed = [item for row in rows for item in row["observed"]]
    if profile.name in {"smoke", "background-queue"}:
        assert len(expected) == len(observed) == 3200
    bindings = {key: value for row in rows for key, value in row["bind_counts"].items()}
    assert len(bindings) == profile.callers and set(bindings.values()) == {1}
    phases, project_labels = [], None
    for rotation in range(16):
        # Every fault role visits every canonical project exactly once. Each
        # phase retains its original finite receipt/effect counts and bound.
        phase = await asyncio.wait_for(_queue_reference(postgres, topology, rotation), 60)
        assert phase["accepted_count"] == 74 and phase["effect_count"] == 71
        assert phase["checkpoint_restart"]["accepted_count"] == 8
        assert phase["checkpoint_restart"]["survivor_count"] == phase["checkpoint_restart"]["effect_count"] == 7
        labels = phase.pop("_project_labels")
        if project_labels is None:
            project_labels = labels
        else:
            assert labels == project_labels, "same canonical identity changed its opaque project label"
        phases.append(phase)
    for role in phases[0]["fault_projects"]:
        assert len({phase["fault_projects"][role] for phase in phases}) == 16
    all_queue_events = [event for phase in phases for event in phase["events"]]
    claims = Counter()
    for phase in phases:
        claims.update(phase["worker_claim_totals"])
    assert all(phase["config"] == phases[0]["config"] for phase in phases)
    queue = {"config": phases[0]["config"], "phases": phases,
        "capacity_samples": [sample for phase in phases for sample in phase["capacity_samples"]],
        "fairness_samples": [sample for phase in phases for sample in phase["fairness_samples"]],
        "receipt_acknowledgement_ms": _percentiles([value for phase in phases for value in phase["receipt_acknowledgement_ms"]["samples"]]),
        "item_high_water": max(phase["item_high_water"] for phase in phases),
        "byte_high_water": max(phase["byte_high_water"] for phase in phases),
        "global_concurrency_high_water": max(phase["global_concurrency_high_water"] for phase in phases),
        "project_concurrency_high_water": max(phase["project_concurrency_high_water"] for phase in phases),
        "admission_outcomes": dict(Counter(event["outcome"] for event in all_queue_events if event["kind"] == "admission")),
        "retry_count": sum(event["value"] for event in all_queue_events if event["kind"] == "retry"),
        "cancellation_counts": dict(Counter({outcome: sum(event["value"] for event in all_queue_events
            if event["kind"] == "cancellation" and event["outcome"] == outcome) for outcome in _D3_PAIRS["cancellation"]})),
        "lease_expiry_count": sum(event["value"] for event in all_queue_events if event["kind"] == "lease"),
        "stale_fence_count": sum(event["value"] for event in all_queue_events if event["kind"] == "fence"),
        "recovery_count": sum(event["value"] for event in all_queue_events if event["kind"] == "recovery"),
        "direct_store_stale_completion_rejections": sum(probe["stale_completion_rejected"] for phase in phases for probe in phase["crash_fence_probes"]),
        "restart_count": 3 * len(phases),
        "shutdown_receipts": [receipt for phase in phases for receipt in
            (phase["shutdown"], phase["restart_shutdown"], phase["checkpoint_restart"]["shutdown"],
             phase["checkpoint_restart"]["restart_shutdown"], *phase["service_fence"]["shutdown_receipts"])],
        "queue_wait_ms": _percentiles([event["duration_ms"] for event in all_queue_events if event["kind"] == "queue_wait"]),
        "run_time_ms": _percentiles([event["duration_ms"] for event in all_queue_events if event["kind"] == "run_time"]),
        "worker_claim_totals": dict(claims)}
    assert sum(claims.values()) == 83 * len(phases)
    assert queue["retry_count"] == len(phases)
    assert queue["lease_expiry_count"] == 2 * len(phases) and queue["stale_fence_count"] == len(phases)
    assert queue["recovery_count"] == 15 * len(phases)
    assert queue["direct_store_stale_completion_rejections"] == 2 * len(phases)
    assert len(queue["shutdown_receipts"]) == 6 * len(phases)
    assert sum(event["kind"] == "lifecycle" and event["outcome"] == "stopped" for event in all_queue_events) == len(queue["shutdown_receipts"])
    queue["postgres_environment"] = _postgres_environment(postgres)
    queue = json.loads(json.dumps(queue, default=lambda value: value.isoformat()))
    histograms = _reference_budgets(rows, isolated, require_soak=profile.name in {"release", "extended"})
    queue["foreground_histograms"] = {"read": histograms["read"], "foreground": histograms["foreground"]}
    result = reconcile_exact_effects(expected, observed, metadata=SwarmRunMetadata(
        source_revision=source_revision, seed=profile.seed,
        topology=topology.as_json_dict() | {"callers_per_project": profile.callers // 16}, set_project_count=bindings,
        background_queue=queue, timing_histograms=histograms,
        fault_timeline=[fault for row in rows for fault in row["faults"]] +
            [{"rotation": phase["rotation"], "projects": phase["fault_projects"],
              "started_ns": phase["phase_started_ns"], "ended_ns": phase["phase_ended_ns"]} for phase in phases],
        teardown_counts={"tasks": sum(row["tasks"] for row in rows),
            "storage_handles": sum(row["storage_handles"] for row in rows),
            "worker_processes": len(set(multiprocessing.active_children()) - process_baseline)}))
    assert result.verdict == "PASS", result.as_json_dict()
    _assert_environment_record(result.as_json_dict()["background_queue"]["postgres_environment"],
        _postgres_environment(postgres))
    return result


def _reference_preflight():
    _runtime_contract()
    _queue_contract()
    fixture_contract()
    StressProfile.from_env()


@pytest.mark.integration
@pytest.mark.postgres
@pytest.mark.performance
@pytest.mark.slow
@_pytest_postgres(_reference_preflight)
async def test_reference_stress_profiles_share_the_exact_c14_oracle(request, tmp_path, test_agent):
    # Source-presence assertions precede all fixture/DSN/profile setup failures.
    _runtime_contract()
    _queue_contract()
    fixture_contract()
    profile = StressProfile.from_env()
    assert test_agent == "test-agent"
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        check=True, text=True, capture_output=True).stdout.strip()
    tasks = set(asyncio.all_tasks())
    children = set(multiprocessing.active_children())
    postgres = canonical_postgres(request)
    result = await run_reference_stress(profile, postgres=postgres, source_revision=revision,
        results_dir=tmp_path / "reference")
    # Canonical fixture teardown and database readback run through pytest.
    assert set(asyncio.all_tasks()) == tasks
    assert set(multiprocessing.active_children()) == children
    assert result.verdict == "PASS"
    output = result.as_json_dict()
    assert output["schema_version"] == "scribe-swarm-results.v1"
    environment = _postgres_environment(postgres)
    _assert_environment_record(output["background_queue"]["postgres_environment"], environment)
    for corrupted in ({key: value for key, value in environment.items() if key != "port"},
                      environment | {"port": environment["port"] % 65535 + 1},
                      environment | {"forbidden": "private-secret"}):
        with pytest.raises(AssertionError):
            _assert_environment_record(corrupted, environment)
    serialized = json.dumps(output, sort_keys=True)
    assert postgres.dsn not in serialized
    assert str(tmp_path) not in serialized
    (tmp_path / "swarm-results.json").write_text(serialized, encoding="utf-8")
    written = json.loads((tmp_path / "swarm-results.json").read_text(encoding="utf-8"))
    _assert_environment_record(written["background_queue"]["postgres_environment"], environment)
    markdown = result.as_markdown()
    markdown_record = json.loads(markdown.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
    _assert_environment_record(markdown_record["background_queue"]["postgres_environment"], environment)
    (tmp_path / "swarm-results.md").write_text(markdown, encoding="utf-8")
