"""Identical real SQLite/PostgreSQL C-08 inputs must yield identical truth."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_name = "_scribe_c08_test_background_receipt_contract"
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, Path(__file__).resolve().parents[2] / "storage/test_background_receipt_contract.py")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
_contract = sys.modules[_name]
require_backend = _contract.require_backend
_sqlite = _contract.load_suite("storage/test_sqlite_background_receipts.py")
parity_trace, sqlite_store = _sqlite.parity_trace, _sqlite.sqlite_store
postgres_store = _contract.load_suite("integration/storage/test_postgres_background_receipts.py").postgres_store

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.regression,
              pytest.mark.usefixtures("test_agent")]


class TestSBRReceiptParity:
    def test_required_contract_is_present(self):
        from scribe_mcp.storage.sqlite import SQLiteStorage
        from scribe_mcp.storage.postgres import PostgresStorage
        require_backend(SQLiteStorage)
        require_backend(PostgresStorage)

    @pytest.mark.asyncio
    async def test_identical_seeded_admission_claim_transition_conflict_and_recovery(self, tmp_path, swarm_postgres_backend, test_agent):
        async with sqlite_store(tmp_path) as (sqlite, _, models, clock):
            sqlite_trace = await parity_trace(sqlite, models, clock, test_agent)
        async with postgres_store(swarm_postgres_backend) as (postgres, _, models, clock):
            postgres_trace = await parity_trace(postgres, models, clock, test_agent)
        # No timestamp/id/error filtering: both use the same manual clock and
        # deterministic IDs, and return the exact canonical dataclass fields.
        assert postgres_trace == sqlite_trace
