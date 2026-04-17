# Test suite contract

This release lane is intentionally split into bounded surfaces:

- `tests/core/` — hermetic shipped-core regressions
- `tests/integration/` — broader multi-tool or end-to-end flows
- `tests/integration/storage/` — backend/storage integration coverage, including Postgres-marked shards
- `tests/fixtures/` — shared pytest fixture modules
- `tests/data/` — checked-in test inputs only

Shipped fast lane:

```bash
pytest -q tests/core -m "not slow and not performance"
```

Non-default lanes:

```bash
pytest -q tests/integration -m "not performance"
pytest -q tests/integration/storage -m postgres
pytest -q -m performance
```

Phase 5.2 storage-posture lane (release gate):

```bash
pytest -q tests/test_settings_schema_alias.py tests/test_storage_factory_backends.py tests/test_mode_detection.py tests/test_server_storage_policy.py
pytest -q tests/integration/storage -m postgres
```

The focused posture suite above must continue proving:

- fail-closed server/public-release resolution via `test_resolve_configured_mode_fail_closed_for_server_without_db_url` (`tests/test_mode_detection.py`)
- fail-closed server rebinding plus default server-class backend resolution via `test_server_rebind_fail_closed_for_server_mode_without_postgres` and `test_storage_factory_fail_closed_for_default_server_class_resolution` (`tests/test_server_storage_policy.py`)
- explicit standalone SQLite support via `test_create_storage_backend_allows_explicit_standalone_sqlite` (`tests/test_storage_factory_backends.py`)

The suite now enforces registered markers with `--strict-markers`. Strict `testpaths`
is intentionally deferred until the broader 4.2-D migration finishes moving the
remaining historical root-level tests into the new layout safely.
