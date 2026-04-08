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

The suite now enforces registered markers with `--strict-markers`. Strict `testpaths`
is intentionally deferred until the broader 4.2-D migration finishes moving the
remaining historical root-level tests into the new layout safely.
