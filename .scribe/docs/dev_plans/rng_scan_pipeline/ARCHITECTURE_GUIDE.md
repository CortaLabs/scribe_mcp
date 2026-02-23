---
id: rng_scan_pipeline-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 rng_scan_pipeline"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 04:06:59 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — rng_scan_pipeline
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 03:52:59 UTC

> Architecture guide for rng_scan_pipeline.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement

**Context:** The starter automation RNG system currently operates as a single-pass, auto-execute pipeline: it scans for candidates, automatically picks the highest-ranked one (index 0), and executes immediately. Users never see the candidate pool before execution begins.

**Problem:** Users cannot inspect or choose from available RNG candidates before committing to execution. The system has rich candidate metadata (IVs, nature, gender, shiny status, scores) but none of it is surfaced to the user. Failed attempts waste time because users cannot redirect to a different candidate from the same scan.

**Goals:**
1. Expose the full ranked candidate pool to users before execution
2. Let users manually select their target from the pool with full stat visibility
3. Preserve existing scan math and execution state machine unchanged
4. Enable "scan once, try multiple candidates" workflows
5. Add hidden power type/power computation to candidate metadata

**Non-Goals:**
- Rewriting the RNG scan math (plan_starter_targets is already mature)
- Rewriting the 5-stage execution state machine (_run_exact_attempt is proven)
- Multi-game support (Fire Red only for this pipeline)
- Persistent candidate history across server restarts (in-memory cache with TTL is sufficient)

**Research Reference:** Per RESEARCH_CURRENT_RNG_AUTOMATION.md, the scan logic in `plan_starter_targets()` is fully decoupled from candidate selection. The existing `/target-plan/preview` endpoint already proves scan-without-execute works. This pipeline formalizes that separation into 3 explicit stages.
<!-- ID: requirements_constraints -->
## 2. Requirements and Constraints

**Functional Requirements:**
1. `POST /scan` endpoint runs the full 3-layer scan (base/deep/relaxed) and returns ALL ranked candidates with expanded metadata
2. Each candidate includes: species, nature, gender, shiny status, full IV spread, hidden power type/power, PID, delay frames, quality scores, filter check details
3. Scan results are cached in-memory keyed by `scan_id` with configurable TTL (default 10 minutes)
4. `POST /select` endpoint accepts `scan_id` + `plan_id` to lock a target candidate
5. `POST /execute` endpoint fires the existing 5-stage execution state machine on the locked target
6. Existing `/start` endpoint preserved for backward compatibility (auto-picks first candidate)
7. UI panel on BizHawk page shows sortable/filterable candidate table after scan completes
8. User can select a candidate from the table and trigger execution with one click

**Non-Functional Requirements:**
- Scan response time: under 2 seconds for 1000+ candidates (current system: 500-1000ms for thorough scan)
- No new external dependencies (pure Python hidden power computation)
- Memory: scan cache bounded by max 5 concurrent scan results (oldest evicted)
- UI renders 1000+ rows without freezing (virtual scrolling or pagination)

**Constraints:**
- MUST NOT modify `plan_starter_targets()` or `_run_exact_attempt()` internals
- MUST NOT break existing `/start` auto-execute flow
- MUST reuse existing `StarterResetStartRequest` Pydantic model for scan parameters
- UI MUST follow existing BizHawk page aesthetic (dark matte, cyan accents, SF Mono font)
- All new Pydantic models in `models.py` (no new model files)
- All new routes in `routes.py` (no new route files)
- All new controller logic in `controller.py` (extend existing class)
<!-- ID: architecture_overview -->
## 3. Architecture Overview

### System Design

The pipeline adds a 3-stage workflow on top of the existing automation infrastructure:

```
Stage 1: SCAN                    Stage 2: SELECT                Stage 3: EXECUTE
POST /scan                       POST /select                   POST /execute
  |                                |                              |
  v                                v                              v
controller.scan()                controller.select()            controller.execute()
  |                                |                              |
  v                                v                              v
_apply_target_overlay_to_plan()  Validate scan_id + plan_id    _run_exact_attempt()
  |  (reuses existing 3-layer)     |                              |  (reuses existing 5-stage)
  v                                v                              v
enrich_candidates()              Lock target in _state          Precheck -> A1 -> A2 -> A3 -> A4
  |  (add hidden power)            |                              |
  v                                v                              v
Cache in _scan_results{}         Return locked target info      Return hit/miss/error
  |
  v
Return full candidate pool
```

### Component Map

| Component | Location | Change Type |
|-----------|----------|-------------|
| `StarterResetController` | `controller.py` | EXTEND: add `scan()`, `select()`, `execute()` methods + `_scan_results` cache |
| `models.py` | `models.py` | EXTEND: add `ScanResponse`, `SelectRequest`, `SelectResponse`, `ExecuteRequest`, `ExecuteResponse`, `CandidateDetail` models |
| `routes.py` | `routes.py` | EXTEND: add 3 new route handlers |
| `starter_target_planner.py` | `starter_target_planner.py` | EXTEND: add `compute_hidden_power()` utility function |
| `automation.js` | `automation.js` | EXTEND: add scan panel UI module |
| `bizhawk.html.j2` | `bizhawk.html.j2` | EXTEND: add scan results HTML container |
| `bizhawk.css` | `bizhawk.css` | EXTEND: add scan panel styles |

### Data Flow

```
User clicks "Deep Scan"
  -> JS calls POST /api/romlab/api/automation/starter-reset/scan
    -> controller.scan() reads game state (seed, TID, SID)
      -> _apply_target_overlay_to_plan() runs 3-layer scan
        -> plan_starter_targets() generates raw candidates
      -> enrich_candidates() adds hidden power type/power
      -> Cache results with scan_id + timestamp
    -> Return { scan_id, candidates[], scan_meta }
  -> JS renders candidate table

User clicks candidate row
  -> JS highlights row, shows detail panel
  -> User clicks "Lock Target"
    -> JS calls POST /select { scan_id, plan_id }
      -> controller.select() validates scan_id exists + not expired
      -> Finds candidate by plan_id in cached results
      -> Stores locked target in controller._state
      -> Return { locked_target details }
    -> JS shows locked target confirmation

User clicks "Execute"
  -> JS calls POST /execute { scan_id }
    -> controller.execute() reads locked target from _state
    -> Calls _run_exact_attempt() with locked target (existing 5-stage machine)
    -> Return execution result
  -> JS shows hit/miss/error status
```
<!-- ID: detailed_design -->
## 4. Detailed Design

### 4.1 API Contract

#### POST /scan — Stage 1: Deep Scan

**Request:** Reuses existing `StarterResetStartRequest` model unchanged. Key parameters:
- `target_horizon_frames` (default 50000, up to 2M with thorough_scan)
- `target_candidate_count` (default 16, recommend 64-256 for pipeline)
- `target_thorough_scan` (bool, enables expanded horizon)
- `target_mode` ("hybrid_weighted" | "filter_first" | "pid_first")
- `filters` (StarterResetFilters: shiny, nature, gender, IV minimums)

**Response Model: `ScanResponse`**
```python
class CandidateDetail(BaseModel):
    plan_id: str                    # Unique candidate ID (e.g., "pid-d1234-pid12345678")
    rank: int                       # 1-based rank within pool
    delay_frames: int               # Frames from current seed to this candidate
    species_id: int                 # Pokemon species ID
    species_name: str               # Resolved species name (e.g., "Squirtle")
    nature: str                     # Nature name (e.g., "Jolly")
    gender: str                     # "male" | "female" | "genderless"
    is_shiny: bool                  # Shiny status
    pid: str                        # PID as hex string (e.g., "0x12345678")
    ability: str                    # Resolved ability name
    ivs: dict[str, int]            # {"hp": 31, "atk": 30, "def": 28, "spa": 31, "spd": 29, "spe": 31}
    iv_total: int                   # Sum of all IVs (0-186)
    hidden_power_type: str          # Computed HP type (e.g., "Fire")
    hidden_power_power: int         # Computed HP base power (30-70)
    stats_at_level_5: dict[str, int] | None  # Optional: computed stats at L5
    filter_score: float             # Match quality (0.0-1.0)
    trajectory_score: float         # Novelty/avoidance (0.0-1.0)
    total_score: float              # Weighted combo score
    filter_checks: list[dict[str, Any]]  # Detailed filter check results
    predicted_seed_start: str       # Hex seed for Lua-side matching
    predicted_seed_candidate: str   # Hex seed at candidate point

class ScanMeta(BaseModel):
    seed_at_scan: str               # Current gRngValue when scan ran (hex)
    tid: int                        # Trainer ID
    sid: int                        # Secret ID
    species_id: int                 # Target starter species
    scan_elapsed_ms: int            # Total scan time
    scan_mode: str                  # "base" | "deep" | "relaxed"
    base_scan_elapsed_ms: int       # Base layer time
    deep_scan_used: bool            # Whether deep scan was needed
    deep_scan_elapsed_ms: int       # Deep layer time (0 if not used)
    relaxed_scan_used: bool         # Whether relaxed scan was needed
    relaxed_scan_elapsed_ms: int    # Relaxed layer time (0 if not used)
    horizon_frames: int             # Actual horizon used
    total_candidates_generated: int # Raw candidates before ranking
    filters_active: bool            # Whether any filters were applied

class ScanResponse(BaseModel):
    scan_id: str                    # UUID for this scan result set
    created_at: str                 # ISO timestamp
    expires_at: str                 # ISO timestamp (created_at + TTL)
    candidates: list[CandidateDetail]  # Full ranked pool
    candidate_count: int            # len(candidates)
    scan_meta: ScanMeta             # Scan diagnostics
```

#### POST /select — Stage 2: Lock Target

**Request Model: `SelectRequest`**
```python
class SelectRequest(BaseModel):
    scan_id: str                    # From ScanResponse
    plan_id: str                    # CandidateDetail.plan_id to lock
```

**Response Model: `SelectResponse`**
```python
class SelectResponse(BaseModel):
    scan_id: str
    plan_id: str
    locked: bool                    # True if successfully locked
    candidate: CandidateDetail      # The locked candidate details
    message: str                    # Human-readable confirmation
```

#### POST /execute — Stage 3: Execute Locked Target

**Request Model: `ExecuteRequest`**
```python
class ExecuteRequest(BaseModel):
    scan_id: str                    # References the scan with locked target
```

**Response Model: `ExecuteResponse`**
```python
class ExecuteResponse(BaseModel):
    status: str                     # "started" | "error"
    scan_id: str
    plan_id: str                    # The locked target being executed
    run_id: str | None              # Automation run ID (if started)
    message: str
```

### 4.2 Controller Changes

**New instance attributes on `StarterResetController.__init__`:**
```python
self._scan_results: dict[str, dict[str, Any]] = {}  # scan_id -> {created_at, expires_at, candidates, scan_meta, request_snapshot}
self._scan_cache_max = 5           # Max concurrent scan results
self._scan_cache_ttl_seconds = 600 # 10 minute TTL
self._locked_target: dict[str, Any] | None = None  # Currently locked candidate
```

**New methods:**

1. **`async def scan(self, request: StarterResetStartRequest) -> dict`**
   - Calls `_ensure_socket_connected()` and `_read_enriched_state()`
   - Runs `_apply_target_overlay_to_plan_async()` with high candidate count
   - Post-processes candidates through `_enrich_candidates()` to add hidden power
   - Generates `scan_id` (UUID4), stores in `_scan_results` with TTL
   - Evicts oldest entry if cache exceeds `_scan_cache_max`
   - Returns `ScanResponse`

2. **`async def select(self, scan_id: str, plan_id: str) -> dict`**
   - Validates `scan_id` exists in `_scan_results` and not expired
   - Finds candidate with matching `plan_id`
   - Stores locked target in `self._locked_target`
   - Returns `SelectResponse`

3. **`async def execute(self, scan_id: str) -> dict`**
   - Validates `_locked_target` exists and matches `scan_id`
   - Constructs the `merged_plan` dict that `_run_exact_attempt` expects from the locked candidate
   - Calls existing `_run_loop` machinery
   - Returns `ExecuteResponse`

4. **`def _enrich_candidates(self, candidates: list[dict]) -> list[dict]`** (sync, pure)
   - For each candidate, computes hidden power type and power from IVs
   - Adds `hidden_power_type`, `hidden_power_power` fields
   - Resolves species name and ability from species_id
   - Computes `iv_total` sum
   - Formats PID and seed values as hex strings

5. **`def _evict_expired_scans(self) -> None`** (sync, pure)
   - Removes entries from `_scan_results` where `expires_at < now`
   - Called at the start of `scan()` and `select()`

### 4.3 Hidden Power Computation

**Location:** New function `compute_hidden_power(ivs: dict[str, int]) -> tuple[str, int]` in `starter_target_planner.py`

Gen 3 Hidden Power formula (verified from decomp):
```python
HP_TYPES = [
    "Fighting", "Flying", "Poison", "Ground", "Rock", "Bug",
    "Ghost", "Steel", "Fire", "Water", "Grass", "Electric",
    "Psychic", "Ice", "Dragon", "Dark"
]

def compute_hidden_power(ivs: dict[str, int]) -> tuple[str, int]:
    hp, atk, defe, spe, spa, spd = ivs["hp"], ivs["atk"], ivs["def"], ivs["spe"], ivs["spa"], ivs["spd"]
    # Type: uses bit 0 of each IV
    type_val = ((hp & 1) | ((atk & 1) << 1) | ((defe & 1) << 2) |
                ((spe & 1) << 3) | ((spa & 1) << 4) | ((spd & 1) << 5))
    type_index = type_val * 15 // 63
    # Power: uses bit 1 of each IV
    power_val = (((hp >> 1) & 1) | (((atk >> 1) & 1) << 1) | (((defe >> 1) & 1) << 2) |
                 (((spe >> 1) & 1) << 3) | (((spa >> 1) & 1) << 4) | (((spd >> 1) & 1) << 5))
    power = power_val * 40 // 63 + 30
    return HP_TYPES[type_index], power
```

### 4.4 Scan Cache Design

```
_scan_results = {
    "scan-uuid-1": {
        "created_at": "2026-02-22T04:00:00Z",
        "expires_at": "2026-02-22T04:10:00Z",
        "candidates": [...],          # Full enriched candidate list
        "scan_meta": {...},            # ScanMeta dict
        "request_snapshot": {...},     # Original request params (for re-scan)
        "locked_plan_id": None | str,  # Set by select()
    },
    ...  # Max 5 entries
}
```

**Eviction policy:** On new scan, if len >= 5, delete oldest by `created_at`. Expired entries cleaned on every `scan()` and `select()` call.

**Thread safety:** All `_scan_results` access is under the existing `self._lock` asyncio Lock.

### 4.5 UI Design

**Location:** New section within existing automation panel in `bizhawk.html.j2` + `automation.js`

**Layout:**
```
+------------------------------------------------------------------+
| AUTOMATION PANEL (existing)                                       |
| [Config Form] [Start] [Stop]                                     |
+------------------------------------------------------------------+
| SCAN PIPELINE (new)                                               |
| [Deep Scan] [Scan Status: idle / scanning... / 847 candidates]   |
+------------------------------------------------------------------+
| CANDIDATE TABLE (new, shown after scan)                           |
| Sort: [Rank v] [Score v] [IVs v] [Nature v]                     |
| Filter: [Shiny Only] [Nature: ___] [Min IVs: __]                |
|                                                                   |
| # | Nature  | IVs              | HP Type | Score | Shiny | Act  |
|---|---------|------------------|---------|-------|-------|------|
| 1 | Jolly   | 31/30/28/31/29/31| Fire 70 | 0.87  |       | [->] |
| 2 | Adamant | 31/31/25/30/28/31| Grass 62| 0.82  |       | [->] |
| 3 | Timid   | 28/31/31/31/31/30| Ice 70  | 0.79  | *     | [->] |
| ...                                                               |
+------------------------------------------------------------------+
| LOCKED TARGET (shown after select)                                |
| Squirtle #7 | Jolly | 31/30/28/31/29/31 | HP Fire 70 | Score 0.87|
| [Execute] [Clear] [Re-scan]                                      |
+------------------------------------------------------------------+
```

**CSS classes (BEM pattern: `scan-pipeline__*`):**
- `.scan-pipeline` — container
- `.scan-pipeline__controls` — scan button + status
- `.scan-pipeline__table` — candidate table container
- `.scan-pipeline__table-header` — sortable column headers
- `.scan-pipeline__row` — candidate row (clickable)
- `.scan-pipeline__row--selected` — highlighted selection
- `.scan-pipeline__row--shiny` — shiny candidate accent
- `.scan-pipeline__locked` — locked target confirmation panel
- `.scan-pipeline__stat-bar` — IV visualization bar

**Sorting:** Client-side sort on any column. Default: rank (ascending).
**Pagination:** Show first 50 candidates with "Load More" button (not virtual scroll, simpler for the existing IIFE pattern).
**Nature colors:** Each nature gets a subtle hue tint (boosted stat = cyan, reduced stat = dim).
<!-- ID: directory_structure -->
## 5. Directory Structure

**Files Modified (no new files created):**

```
src/rom_lab/api/routes/automation/
  controller.py          # EXTEND: +scan(), +select(), +execute(), +_enrich_candidates(), +_scan_results cache
  models.py              # EXTEND: +CandidateDetail, +ScanMeta, +ScanResponse, +SelectRequest, +SelectResponse, +ExecuteRequest, +ExecuteResponse
  routes.py              # EXTEND: +3 route handlers (/scan, /select, /execute)
  constants.py           # EXTEND: +SCAN_CACHE_MAX, +SCAN_CACHE_TTL_SECONDS

src/rom_lab/plugins/pokemon_fire_red/
  starter_target_planner.py  # EXTEND: +compute_hidden_power(), +HP_TYPES constant

.council/web/pages/
  bizhawk.html.j2        # EXTEND: +scan pipeline HTML section within automation panel

.council/web/static/js/
  automation.js           # EXTEND: +scan pipeline module (scan/select/execute flow + candidate table)

.council/web/static/css/
  bizhawk.css             # EXTEND: +.scan-pipeline BEM classes

tests/
  test_automation_routes.py  # EXTEND: +scan, +select, +execute endpoint tests
  test_hidden_power.py       # NEW: hidden power computation unit tests (pure math, no deps)
```
<!-- ID: data_storage -->
## 6. Data and Storage

**Scan Result Cache (in-memory):**
- Location: `StarterResetController._scan_results` dict
- Lifecycle: Created on `/scan`, read on `/select` and `/execute`, evicted after TTL (10 min) or when cache is full (5 max)
- NOT persisted across server restarts (ephemeral by design)
- Thread-safe: all access under `self._lock` (asyncio.Lock)

**Candidate History (existing SQLite):**
- Location: `StarterHistoryStore` at `data/fire_red/starter_history.db`
- Already stores per-attempt candidate data
- Pipeline extends this: after successful execution, the full scan result and selected candidate are appended to history
- No schema changes needed to existing history tables

**No new databases or tables required.** The scan cache is purely in-memory, and history persistence uses the existing StarterHistoryStore infrastructure.
<!-- ID: testing_strategy -->
## 7. Testing and Validation Strategy

**Unit Tests:**
1. `test_hidden_power.py` — Pure math tests for `compute_hidden_power()`:
   - Known IV spreads with expected HP type/power results
   - Edge cases: all 0 IVs, all 31 IVs, all same IV value
   - Verify all 16 HP types are reachable

2. `test_automation_routes.py` — Extend existing test file:
   - `/scan` endpoint: verify response shape matches `ScanResponse`, candidate count, enrichment fields present
   - `/select` endpoint: verify lock/unlock behavior, expired scan rejection, invalid plan_id rejection
   - `/execute` endpoint: verify locked target required, execution starts, backward compat with `/start`
   - Cache eviction: verify max 5 scans, TTL expiry, oldest-first eviction

**Integration Tests (manual, with running BizHawk):**
1. Full pipeline: scan -> inspect candidates -> select -> execute -> verify PID match
2. Re-scan after failed execution (same seed should produce same candidates)
3. Select different candidate from same scan after first execution fails

**Test Fixtures:**
- Mock `_read_enriched_state()` to return deterministic game state (known seed, TID, SID)
- Mock `plan_starter_targets()` to return pre-built candidate list
- Existing test patterns in `test_automation_routes.py` provide the model
<!-- ID: deployment_operations -->
## 8. Deployment and Operations

**No deployment changes required.** All changes are to existing Python modules and web assets:
- Python changes: restart `rom-lab serve` to pick up new routes/controller methods
- JS/CSS/HTML changes: browser refresh picks up new assets (no build step)
- No new dependencies, no new services, no database migrations

**Validation sequence after implementation:**
1. `pytest tests/test_hidden_power.py -v` — Hidden power math
2. `pytest tests/test_automation_routes.py -v` — API contract tests
3. Manual: boot BizHawk, navigate to starter selection screen, trigger full pipeline flow
<!-- ID: open_questions -->
## 9. Open Questions and Follow-Ups

| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Ability resolution from species_id | Coder | Open | Need to verify how ability is determined from PID + species in Fire Red (ability bit = PID & 1) |
| Stats at level 5 computation | Coder | Open | Optional enhancement: compute actual stats at L5 for each candidate. Requires base stat lookup. Low priority. |
| Candidate count default for pipeline | Architect | Resolved | 64-256 recommended for pipeline scans (vs 16 default for auto-execute). UI should default to 128. |
| WebSocket push for scan progress | Architect | Deferred | HTTP request/response sufficient for 500-1000ms scan. WebSocket streaming deferred to future enhancement. |
| Multi-candidate retry workflow | Architect | Deferred | "Try A, fail, try B from same scan" - design is compatible but implementation deferred to v2. |
<!-- ID: references_appendix -->
## 10. References and Appendix

**Research:**
- `RESEARCH_CURRENT_RNG_AUTOMATION.md` — Full system analysis (Specter, HIGH confidence)

**Key Source Files (verified):**
- `src/rom_lab/api/routes/automation/controller.py` (4603 lines) — Main controller, target overlay, selection logic
- `src/rom_lab/api/routes/automation/models.py` (280 lines) — Pydantic request models
- `src/rom_lab/api/routes/automation/routes.py` (164 lines) — API endpoint handlers
- `src/rom_lab/api/routes/automation/constants.py` (158 lines) — Default values
- `src/rom_lab/api/routes/automation/history_store.py` (257 lines) — SQLite candidate history
- `src/rom_lab/plugins/pokemon_fire_red/starter_target_planner.py` (788 lines) — Scan math
- `.council/web/static/js/automation.js` (2589 lines) — Existing automation UI
- `tests/test_automation_routes.py` (2409 lines) — Existing test suite

**Gen 3 Hidden Power Reference:**
- Formula: Type determined by bit 0 of each IV, power by bit 1
- 16 possible types: Fighting, Flying, Poison, Ground, Rock, Bug, Ghost, Steel, Fire, Water, Grass, Electric, Psychic, Ice, Dragon, Dark
- Power range: 30-70
- Source: pokefirered decomp `src/battle_util.c` (GetHiddenPowerType, GetHiddenPowerPower)
