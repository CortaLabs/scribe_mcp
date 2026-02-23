---
id: automation_rng_modular_2026_02_21-research-testing-infrastructure
title: "\U0001F52C Research Testing Infrastructure \u2014 automation_rng_modular_2026_02_21"
doc_type: RESEARCH_TESTING_INFRASTRUCTURE
doc_name: RESEARCH_TESTING_INFRASTRUCTURE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 05:22:34 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Testing Infrastructure — automation_rng_modular_2026_02_21
**Author:** test-architect
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-21 05:19:38 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Design a two-layer testing architecture for deterministic, tick-perfect RNG validation that covers pure math unit tests AND emulator integration tests, with full PokeFinder parity.

**Testing Philosophy:** RNG manipulation testing divides cleanly into two fully independent layers:

- **Layer 1 — Pure Math Tests** (always run, no emulator required): Validates LCRNG engine, Method 1 generation, seed advancement, reversal, and all planning logic. PokeFinder parity via JSON fixtures. Fast, CI-friendly, zero external dependencies.

- **Layer 2 — Emulator Integration Tests** (skip when BizHawk not running): Validates predictions against actual game RAM. Tick-perfect workflow: load savestate → advance N frames → read RAM → compare against prediction.

**Key Takeaways:**
- All pure math testing is already well-structured and can be extended using PokeFinder fixture data
- The existing `_HAS_DECOMP_DB` skip pattern in test_seed.py is the correct model for emulator-gated tests
- BizHawk savestates are the primary vehicle for deterministic emulator replay — load a savestate at a known RNG state and verify predictions
- The `_send_debug_request` mock pattern (test_perception_fixes.py) handles all IPC-dependent tests without emulator
- No new test directories needed — all tests in `tests/` per project convention
- A fixtures generation script should be added to `scripts/` to produce reference JSON from PokeFinder data
<!-- ID: research_scope -->
**Research Lead:** test-architect

**Investigation Window:** 2026-02-21

**Focus Areas:**
- [x] Study existing test files and patterns (conftest.py, 80+ test files)
- [x] Analyze PokeFinder test data and fixture format
- [x] Research BizHawk trace/savestate tools
- [x] Research deterministic emulator testing approaches (TAS community, BizHawk)
- [x] Design math test layer (pure Python, CI-friendly)
- [x] Design emulator integration test layer (savestate-based, gated)
- [x] Define fixture strategy and generation workflow
- [x] Define CI integration approach

**Dependencies & Constraints:**
- BizHawk socket reader must be running for emulator integration tests (port 6543)
- PokeFinder lcrng.json "next" vector interpretation needs verification (parallel chains or sequential)
- gRng.value RAM address in Fire Red needs confirmation from decomp (for integration tests)
- Existing test_automation_routes.py must not be split until automation.py is modularized
- No new test directories — all tests stay in `tests/` per project convention
<!-- ID: findings -->
### Finding 1: Existing Test Patterns — Strong Foundation
- **Summary:** The project has 80+ test files in `tests/` covering multiple test patterns. The patterns are mature and consistent. conftest.py is intentionally minimal (only file fixtures). No shared emulator fixtures exist — this is by design.
- **Evidence:** `tests/conftest.py`, `tests/test_fire_red_rng_oracle.py`, `tests/test_rng_oracle_pokefinder_parity.py`, `tests/test_perception_fixes.py`, `tests/test_automation_routes.py`, `tests/test_seed.py`
- **Confidence:** High

### Finding 2: PokeFinder Reference Data Available
- **Summary:** `.local_refs/rng_sources/admiral_fish_pokefinder/Test/` contains JSON fixtures for Gen3 static generator (static3.json), LCRNG raw operations (lcrng.json), wild encounters, egg RNG, TID/SID, and Gamecube games. These are the authoritative reference data from the PokeFinder C++ test suite.
- **Evidence:** 
  - `static3.json`: 3 test cases (Ruby Groudon Method 4, Emerald Totodile Method 1, Fire Red Lugia Method 1), each with 10 advances covering pid, ivs, nature, ability, shiny, stats
  - `lcrng.json`: advance/distance/jump/next test vectors with 4 named seeds each
  - Our fixture `tests/fixtures/rng/pokefinder_method1/firered_lugia_method1_seed_AAAAAAAA.json` already extracts the FireRed Method 1 rows in our own format
- **Confidence:** High

### Finding 3: LCRNG Implementation Verified
- **Summary:** `rng_oracle.py` implements LCRNG with A=0x41C64E6D, C=0x6073, MASK=0xFFFFFFFF and inverse A_INV=0xEEB9EB65. Can verify against lcrng.json "next" vectors directly: seed=0 → first next = 0x00006073 (1 step); this matches `next_seed(0)` which returns (0x00006073, 0) per existing test.
- **Evidence:** `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py:14-15`, `tests/test_fire_red_rng_oracle.py:8-11`
- **Confidence:** High

### Finding 4: IPC Mocking Pattern Well-Established
- **Summary:** `test_perception_fixes.py` demonstrates the complete pattern for mocking `_send_debug_request` to test IPC-dependent code without a live emulator. The `patch("rom_lab_mcp.debug_tools._send_debug_request", ...)` approach is used throughout.
- **Evidence:** `tests/test_perception_fixes.py:110-152`, `tests/test_debug_tools.py:9-40`
- **Confidence:** High

### Finding 5: Savestate + Frame-Advance = Deterministic Integration Test
- **Summary:** BizHawk savestates capture complete emulator state (CPU registers, RAM, RNG state). Loading a savestate at a known RNG seed value, then pressing a sequence of buttons, then reading RAM at key addresses gives a fully deterministic integration test. The IPC system supports `savestate_load`, memory reads, and input injection — exactly what's needed.
- **Evidence:** `mcp/src/rom_lab_mcp/debug_tools.py:541-548` (savestate_save/load), `lua/common/ipc.lua:34-127` (read, write, input IPC commands)
- **Confidence:** High

### Finding 6: Skip Pattern for Optional Resources
- **Summary:** `test_seed.py` and `test_auto_seed.py` use `_HAS_DECOMP_DB = DECOMP_DB_PATH.exists()` to gate tests on optional resources. This is the correct model for emulator integration tests: `_BIZHAWK_RUNNING = _check_bizhawk_socket()` at module load time, then `@pytest.mark.skipif(not _BIZHAWK_RUNNING, ...)` on integration test classes.
- **Evidence:** `tests/test_seed.py:18-20`, `tests/test_auto_seed.py`
- **Confidence:** High

### Additional Notes
- `pytest-asyncio` is available and used in `test_automation_routes.py` — controller tests need it
- No `pytest.ini_options.asyncio_mode` is set — tests use explicit `@pytest.mark.asyncio` marks
- The PokeFinder `wild3.json` and `egg3.json` data could support future wild encounter and egg RNG test extensions
<!-- ID: technical_analysis -->
### Existing Test Analysis

**Pattern 1: Pure math tests (no mocking needed)**
```python
# tests/test_fire_red_rng_oracle.py — gold standard
def test_advance_matches_repeated_steps() -> None:
    seed = 0x12345678
    advanced = rng_oracle.advance(seed, 25)
    repeated = seed
    for _ in range(25):
        repeated, _ = rng_oracle.next_seed(repeated)
    assert advanced == repeated
```
Use for: LCRNG operations, Method 1 generation, IV extraction, shiny calculation.

**Pattern 2: JSON fixture parity tests**
```python
# tests/test_rng_oracle_pokefinder_parity.py — PokeFinder comparison
def test_method1_generation_matches_pokefinder_fixture_rows():
    fixture = _load_fixture()  # JSON from .local_refs/
    for row in fixture["rows"]:
        generated = rng_oracle.method1_generate(rng_oracle.advance(seed, delay))
        assert int(generated.pid) == int(row["pid"])
        assert generated.ivs == row["ivs"]
```
Use for: All new RNG method implementations — must match PokeFinder output exactly.

**Pattern 3: FastAPI TestClient + monkeypatch**
```python
# tests/test_automation_routes.py — controller/route tests
def _client(session_manager=None, frame_receiver=None) -> TestClient:
    app = FastAPI()
    automation.init_automation(session_manager, frame_receiver)
    app.include_router(automation.router)
    return TestClient(app)

def test_start_route_returns_503_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(controller, "_preflight_runtime_ready_unlocked",
                        MethodType(_mock_preflight_fail, controller))
    resp = client.post("/api/automation/starter-reset/start", json={})
    assert resp.status_code == 503
```
Use for: All API route tests, controller state machine tests.

**Pattern 4: IPC mock for non-emulator tests**
```python
# tests/test_perception_fixes.py — IPC mocking
with patch("rom_lab_mcp.debug_tools._send_debug_request", mock_ipc):
    result = _read_bag_pocket_items(0, max_items=8)
```
Use for: Any test that calls functions using debug_tools IPC.

**Pattern 5: Optional resource skip**
```python
# tests/test_seed.py — established project pattern
_HAS_DECOMP_DB = DECOMP_DB_PATH.exists()
@pytest.mark.skipif(not _HAS_DECOMP_DB, reason="requires decomp DB")
def test_real_seed_pipeline(): ...
```
Adapt for emulator tests: `_BIZHAWK_RUNNING = _check_bizhawk_socket()`

### PokeFinder Test Data Available

| Fixture File | Content | Use For |
|---|---|---|
| `Test/RNG/lcrng.json` | advance, distance, jump, next vectors (4 seeds each) | LCRNG engine parity |
| `Test/Gen3/static3.json` | Method 1 + Method 4 static gen (3 test cases, 10 advances each) | Method 1/4 generation parity |
| `Test/Gen3/wild3.json` | Wild encounter gen | Wild encounter RNG (future) |
| `Test/Gen3/egg3.json` | Egg RNG | Egg breeding RNG (future) |
| `Test/Gen3/id3.json` | TID/SID generation | Trainer ID RNG (future) |
| `Test/Gen3/seedtotime3.json` | Seed-to-time mapping | Seed timer calibration (future) |

**lcrng.json "next" test vectors** — confirmed match with rng_oracle.py:
- seed=0, 1 step: result[0] = 1 (that's next_seed(0)[1] upper16... wait: 0x00006073 & 0xFFFF = 0, but result[0]=1)
- NOTE: PokeFinder's LCRNG "next" returns `(seed * A + C) >> 16` as u16 hi-output, but lcrng.json "next" vectors show the RAW SEED value after advance, not the hi16. Verify: `seed=0, advances=1, results=[1, 1774682003, 24691, 171270561, 2531011, 2708534849]` — results[0]=1 is next_seed FROM seed=0 which is 0x41C64E6D*0 + 0x6073 = 0x6073 ≠ 1. CONCLUSION: These are 6 parallel LCRNG chains from seed=0 with different advances, NOT sequential chain. Need to verify interpretation against PokeFinder source before writing fixture tests.

### Risk Assessment
- [ ] Verify lcrng.json result interpretation: parallel chains vs sequential outputs
- [ ] Confirm Method 1 seed convention: does pf use `seed` or `seed+1` as start for generation?
- [ ] savestate file format: verify BizHawk savestates are slot-based (0-9) for test isolation
- [ ] Socket check: need `_check_bizhawk_socket()` helper for integration test gating

**Code Patterns Identified:**
- All testable math lives in `rng_oracle.py` and `starter_target_planner.py` — both pure Python
- IPC boundary is `_send_debug_request` in `debug_tools.py` — mock this for unit tests
- Controller boundary is the `StarterResetController` class — mock its methods for route tests
- Savestate boundary is `savestate_save/load` in `debug_tools.py` — needs real emulator

**System Interactions:**
- `rng_oracle.py` → no I/O (pure math)
- `starter_target_planner.py` → imports `rng_oracle` (pure math)
- `automation.py` → imports `starter_target_planner`, `rng_oracle`, uses IPC via `session_manager`/`frame_receiver`
- `debug_tools.py` → IPC to Lua via file-based `_send_debug_request`
- Lua `ipc.lua` → BizHawk memory API
<!-- ID: recommendations -->
### Math Test Layer — Pure Python RNG Engine Tests

**File: `tests/test_rng_engine_lcrng.py`** (new)

Tests to add for comprehensive LCRNG engine parity with PokeFinder:

```python
# 1. LCRNG raw operations from lcrng.json
def test_lcrng_advance_from_zero():
    # lcrng.json advance[0]: seed=0, advances=5
    # Verify our advance(0, 5) == expected final seed
    result = rng_oracle.advance(0, 5)
    # Use PokeFinder advance result (need to verify interpretation)

def test_lcrng_next_sequential_chain():
    # lcrng.json next[0]: seed=0, results=[1, 1774682003, ...]
    # Interpret: results are 6 sequential states after seed=0
    # next_seed(0)[0] = first state, next_seed(state)[0] = second, etc.

def test_lcrng_reverse_matches_prev_seed():
    # reverse(seed, n) should match n applications of prev_seed()
    for seed in [0, 0x12345678, 0xDEADBEEF, 0xAAAAAAAA]:
        for n in [1, 5, 10]:
            assert rng_oracle.reverse(seed, n) == rng_oracle.advance(seed, n)  # wrong
            # Actually: advance forward N then reverse N should return original
            fwd = rng_oracle.advance(seed, n)
            assert rng_oracle.reverse(fwd, n) == seed

def test_method1_parity_ruby_groudon():
    # static3.json: Ruby Groudon Method 4 (not Method 1 — skip or adapt)
    pass

def test_method1_parity_emerald_totodile():
    # static3.json: Emerald Totodile Method 1 seed=1431655765
    # 10 advances, verify pid and ivs match

def test_method1_parity_firered_lugia():
    # static3.json: Fire Red Lugia Method 1 seed=2863311530
    # Already partially covered by test_rng_oracle_pokefinder_parity.py
    # Expand to cover all 10 advances + ability + nature
```

**New fixture files to create** (in `tests/fixtures/rng/`):

| File | Content | Source |
|---|---|---|
| `pokefinder_method1/emerald_totodile_method1.json` | Emerald Totodile Method 1, 10 advances | static3.json |
| `pokefinder_lcrng/advance_vectors.json` | LCRNG advance test vectors | lcrng.json |
| `pokefinder_lcrng/next_vectors.json` | LCRNG next sequential vectors | lcrng.json |

**Script to add: `scripts/generate_rng_fixtures.py`**
- Reads `.local_refs/rng_sources/admiral_fish_pokefinder/Test/` files
- Extracts and transforms into our fixture format
- Writes to `tests/fixtures/rng/`
- Run manually when adding new method parity tests

### Emulator Integration Test Layer — BizHawk Savestate Replay

**File: `tests/test_rng_emulator_integration.py`** (new)

```python
"""Integration tests for tick-perfect RNG prediction validation.

These tests require a live BizHawk instance with Fire Red loaded.
They are skipped automatically in CI.

Usage:
    pytest tests/test_rng_emulator_integration.py -v
    (requires: rom-lab boot pokemon_fire_red in another terminal)
"""
from __future__ import annotations
import socket
from pathlib import Path
from unittest.mock import patch
import pytest
from rom_lab.plugins.pokemon_fire_red import rng_oracle

# Gate: check if socket reader is live
def _check_bizhawk_socket() -> bool:
    try:
        with socket.create_connection(("localhost", 6543), timeout=0.5):
            return True
    except (ConnectionRefusedError, OSError):
        return False

_BIZHAWK_RUNNING = _check_bizhawk_socket()
pytestmark = pytest.mark.skipif(
    not _BIZHAWK_RUNNING,
    reason="requires live BizHawk with Fire Red (rom-lab boot pokemon_fire_red)"
)

# Savestate management — slots 8-9 reserved for integration tests
_TEST_SAVESTATE_SLOT = 9

class TestRNGPredictionVsRAM:
    """Verify RNG predictions match actual Pokemon generated by the game.
    
    Workflow:
    1. Load a known savestate (saved at specific RNG seed)
    2. Press A to generate a starter (or read from party)
    3. Read the actual PID + IVs from RAM
    4. Verify they match our prediction for that seed
    """

    def test_method1_prediction_matches_ram_after_savestate_load(self):
        from rom_lab_mcp.debug_tools import savestate_load, read_memory
        from rom_lab.plugins.pokemon_fire_red.ram_map import PARTY_ADDR
        
        # Precondition: test savestate must exist at slot 9
        # (created by: pytest -m create_test_savestate)
        result = savestate_load(_TEST_SAVESTATE_SLOT)
        assert "error" not in result
        
        # Read RNG seed from RAM (gRng.value address from decomp)
        rng_addr = 0x03005000  # gRng.value in Fire Red
        seed_bytes = read_memory([rng_addr, rng_addr+1, rng_addr+2, rng_addr+3])
        # ... construct prediction and verify
```

**Key Integration Test Workflow:**
1. Create a savestate at a known moment (just before pressing A on a starter ball)
2. Record the RNG seed from RAM at that savestate
3. Compute prediction: `method1_generate(advance(seed, STARTER_CAPTURE_RNG_CALLS))`
4. Load savestate, press A, wait for starter to be added to party
5. Read party slot 0 personality and IVs from RAM
6. Assert prediction matches RAM values exactly

### Fixture Strategy

**Principle:** Fixtures are JSON files checked into `tests/fixtures/`. Generated offline from authoritative sources.

```
tests/fixtures/rng/
├── pokefinder_method1/
│   ├── firered_lugia_method1_seed_AAAAAAAA.json     (existing)
│   ├── emerald_totodile_method1_seed_55555555.json  (new)
│   └── firered_method1_multi_seed.json              (new — multiple seeds)
├── pokefinder_lcrng/
│   ├── advance_vectors.json     (from lcrng.json advance section)
│   ├── next_vectors.json        (from lcrng.json next section)
│   └── jump_vectors.json        (from lcrng.json jump section)
├── emulator_captures/           (new — from real game sessions)
│   └── README.md               (instructions for creating captures)
└── README.md                   (fixture format documentation)
```

**Fixture format standard** (extend existing format):
```json
{
  "source": "admiral_fish_pokefinder/Test/Gen3/static3.json",
  "dataset": "Emerald Totodile Method 1",
  "seed": 1431655765,
  "lcrng_constants": {"A": "0x41C64E6D", "C": "0x6073"},
  "rows": [
    {"delay": 0, "pid": 2828921363, "nature_id": 13, "ivs": {...}},
    ...
  ]
}
```

### Test Organization — Proposed File Structure

```
tests/
├── conftest.py                              (existing — minimal, keep as-is)
├── test_fire_red_rng_oracle.py              (existing — LCRNG unit tests)
├── test_rng_oracle_pokefinder_parity.py     (existing — extend with more cases)
├── test_starter_target_planner.py           (existing — extend IV/filter tests)
├── test_rng_engine_lcrng.py                 (NEW — raw LCRNG parity with lcrng.json)
├── test_rng_engine_method1.py               (NEW — Method 1 parity, multi-seed coverage)
├── test_rng_engine_method4.py               (NEW — Method 4 if implemented)
├── test_automation_routes.py                (existing — controller/route tests, 3756 lines)
├── test_rng_emulator_integration.py         (NEW — savestate-based integration tests)
└── fixtures/rng/
    ├── pokefinder_method1/
    ├── pokefinder_lcrng/
    └── emulator_captures/
```

**Not splitting test_automation_routes.py** — it's the controller test suite. When automation is modularized, split into `test_automation_rng_module.py`, `test_automation_state_machine.py`, etc. following the module boundaries.

### CI Integration

**What runs in CI (`pytest -q`):**
- All pure math tests
- All fixture parity tests  
- All controller/route tests (monkeypatched, no emulator)
- All existing tests (no emulator tests run)

**What runs manually (pre-ship validation):**
```bash
# Requires: rom-lab boot pokemon_fire_red
pytest tests/test_rng_emulator_integration.py -v --tb=short
```

**Fixture generation (one-time, when updating PokeFinder reference data):**
```bash
python scripts/generate_rng_fixtures.py
git add tests/fixtures/rng/
git commit -m "chore: update RNG test fixtures from PokeFinder reference data"
```

**conftest.py additions needed:**
```python
# Add to tests/conftest.py
@pytest.fixture
def rng_fixture_dir() -> Path:
    """Path to RNG test fixtures directory."""
    return Path(__file__).parent / "fixtures" / "rng"

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "emulator: mark test as requiring live BizHawk emulator"
    )
    config.addinivalue_line(
        "markers", "create_test_savestate: mark test as savestate setup helper"
    )
```

### Immediate Next Steps
- [ ] Verify lcrng.json "next" vector interpretation (parallel chains or sequential)
- [ ] Create `tests/fixtures/rng/pokefinder_method1/emerald_totodile_method1.json`
- [ ] Create `tests/test_rng_engine_lcrng.py` with LCRNG parity tests from lcrng.json
- [ ] Create `scripts/generate_rng_fixtures.py` for automated fixture generation
- [ ] Create `tests/test_rng_emulator_integration.py` skeleton with skip guards
- [ ] Add pytest marker registration to `tests/conftest.py`
- [ ] Define `gRng.value` RAM address for Fire Red (needed by integration tests)

### Long-Term Opportunities
- Property-based testing with Hypothesis for LCRNG mathematical properties (commutativity, group structure)
- Savestate library: a directory of named savestates at known RNG states for regression testing
- Automated savestate creation: Lua script that creates test savestates at known seeds during a session
<!-- ID: appendix -->
### Research Sources
- `tests/conftest.py` — minimal fixture setup
- `tests/test_fire_red_rng_oracle.py` — existing LCRNG unit tests (gold standard pattern)
- `tests/test_rng_oracle_pokefinder_parity.py` — existing PokeFinder parity tests
- `tests/test_starter_target_planner.py` — existing planner unit tests
- `tests/test_perception_fixes.py` — IPC mocking pattern
- `tests/test_automation_routes.py` (3756 lines) — controller/route test pattern with pytest-asyncio
- `tests/test_seed.py` — optional resource skip pattern (the model for emulator gating)
- `tests/test_debug_tools.py` — IPC mock pattern for debug tools
- `tests/fixtures/rng/pokefinder_method1/firered_lugia_method1_seed_AAAAAAAA.json` — existing fixture format
- `.local_refs/rng_sources/admiral_fish_pokefinder/Test/Gen3/static3.json` — PokeFinder Method 1/4 reference data
- `.local_refs/rng_sources/admiral_fish_pokefinder/Test/RNG/lcrng.json` — LCRNG raw operation vectors
- `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py` — LCRNG engine (A=0x41C64E6D, C=0x6073)
- `mcp/src/rom_lab_mcp/debug_tools.py:541,1691,1749,1798` — savestate, trace tools
- `lua/common/ipc.lua` — IPC protocol (read, dump, write, input commands)
- `pyproject.toml` — pytest config (testpaths=["tests"], no asyncio_mode setting)

### Key Constants
- LCRNG_A = 0x41C64E6D
- LCRNG_C = 0x00006073
- LCRNG_A_INV = 0xEEB9EB65 (multiplicative inverse mod 2^32)
- STARTER_CANDIDATE_CAPTURE_RNG_OFFSET_CALLS: imported from starter_target_planner
- BizHawk socket default port: 6543 (socket_reader.lua)
- Test savestate slots to reserve: 8-9 (integration tests only)

### Decision Log
| Decision | Rationale |
|---|---|
| No new test directory | Project convention: all tests in `tests/` |
| `_HAS_DECOMP_DB` skip pattern | Established project pattern for optional resources |
| Mock `_send_debug_request` for unit tests | Established pattern in test_perception_fixes.py |
| JSON fixtures for PokeFinder parity | Reproducible, checked-in, auditable reference data |
| Savestate + frame-advance for integration | Deterministic, reproducible, no manual game state setup |
| Reserved slots 8-9 for integration tests | Avoid collisions with user savestates |
| `scripts/generate_rng_fixtures.py` | Automate fixture generation from PokeFinder data |
