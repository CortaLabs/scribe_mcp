---
id: game_state_ux_overhaul-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 game_state_ux_overhaul"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 16:28:09 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — game_state_ux_overhaul
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-22 15:16:51 UTC

> Execution roadmap for game_state_ux_overhaul.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview

| Phase | Goal | Key Deliverables | Est. Complexity | Dependencies |
|-------|------|------------------|-----------------|--------------|
| Wave 1 (P0) | Perception Fix | Shop menu detection in Lua + schema flow | Low | None |
| Wave 2 (P1) | Battle Intelligence Backend | IV extraction, damage calc, enriched state | Medium | Decomp struct verification |
| Wave 2 (P2a) | API Proxy Route | /api/romlab/* proxy on Council web | Low | Wave 1 (enriched state must exist) |
| Wave 3 (P2b) | Game State Tab Frontend | Battle intel panel, look button | Medium | Wave 2 complete |
| Wave 3 (P3) | Input Control UX | Hold-to-spam, joystick mode | Low | None (independent) |

**Execution Strategy:**
- Wave 1 is a blocker -- must be completed and verified before Wave 2
- Wave 2 tasks (P1 + P2a) can run in parallel (different files, no overlap)
- Wave 3 tasks (P2b + P3) can run in parallel (different JS files, no overlap)
- Frontend design done separately by orchestrator as noted in task brief
<!-- ID: phase_0 -->
## Wave 1: Perception Fix (P0 -- Shop Menu Detection)

**Objective:** Add shop menu detection to the Lua perception pipeline with stale-state guards, flowing through schema to API.

### Task Package 1.1: Lua Shop Detection

**Scope:** Add sShopMenuWindowId read and composite guard to read_context() in both Lua readers.
**Files to Modify:**
- `src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` (PRIMARY)
- `src/rom_lab/plugins/pokemon_fire_red/lua/reader.lua` (MIRROR)

**Specifications:**
1. Add `MENU.shop_window_id = 0x02039950` to the MENU constants table at top of file
2. In `read_context()` function (socket_reader.lua ~line 1003), after yesno_active detection, add:
   - Read `shop_wid = mem.read_u8(MENU.shop_window_id, DOM)`
   - Composite guard: `in_shop = (shop_wid ~= 0xFF and shop_wid ~= 0) and (script_mode ~= 0)`
3. Replace `local open_menu_id = 0` (line 1009) with conditional:
   - `open_menu_id = 1` when `in_shop` is true, else `0`
4. Mirror EXACT same changes to `reader.lua`

**Verification:**
- [ ] `luac -p socket_reader.lua` passes (syntax check)
- [ ] `luac -p reader.lua` passes (syntax check)
- [ ] Both files have identical read_context() logic
- [ ] When shop is active: open_menu_id = 1 in JSON output
- [ ] When shop closes: open_menu_id returns to 0 (stale guard test)

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify read_battle_state() (separate task)
- Do NOT add bag/PC detection (future research needed)
- Do NOT modify schema.py (field already exists)
- Do NOT modify plugin.py (flow is pass-through)
<!-- ID: phase_1 -->
## Wave 2: Battle Intelligence Backend (P1) + API Proxy (P2a)

**Objective:** Expose battle intelligence data and fix the API proxy so the game state tab can reach the enriched state endpoint.

### Task Package 2.1: Battle Intel Utilities (IV Extraction + Damage Calc)

**Scope:** Create a new battle intelligence module with pure utility functions for IV extraction and Gen 3 damage calculation.
**Files to Modify:**
- `src/rom_lab/plugins/pokemon_fire_red/battle_intel.py` (NEW FILE)

**Specifications:**
1. Create `extract_ivs(ivs_raw: int) -> dict[str, int]`:
   - Input: packed u32 from gBattleMons IV field
   - Bits 0-4: HP, 5-9: Atk, 10-14: Def, 15-19: Spe, 20-24: SpA, 25-29: SpD
   - Return: `{"hp": int, "atk": int, "def": int, "spe": int, "spa": int, "spd": int}`
2. Create `gen3_damage_calc(level: int, move_power: int, attack_stat: int, defense_stat: int, stab: bool, effectiveness: float, is_critical: bool = False) -> dict[str, int | float]`:
   - Implement Gen 3 damage formula: `floor(floor(floor(2*level/5+2) * power * A/D) / 50 + 2)`
   - Apply STAB (1.5x), effectiveness, critical (2x)
   - Return: `{"min": int, "max": int, "avg": float}` (min uses 85% roll, max uses 100% roll)
3. All functions must be pure (no side effects, no imports beyond stdlib)

**Verification:**
- [ ] `pytest tests/test_battle_intel.py` passes
- [ ] extract_ivs(0) returns all zeros
- [ ] extract_ivs(0x3FFFFFFF) returns all 31s
- [ ] extract_ivs(0x00108421) returns {hp:1, atk:1, def:1, spe:1, spa:1, spd:0} (verify math)
- [ ] gen3_damage_calc with Tackle (power=40, level=5, atk=12, def=11, stab=True, eff=1.0) returns plausible range

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify battle.py (existing BattleModel is observation-based, separate system)
- Do NOT modify tools.py
- Do NOT modify schema.py (separate task)

---

### Task Package 2.2: Lua + Schema IV Field Extension

**Scope:** Add enemy IV data read to Lua battle state and corresponding schema fields.
**Files to Modify:**
- `src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` (PRIMARY)
- `src/rom_lab/plugins/pokemon_fire_red/lua/reader.lua` (MIRROR)
- `src/rom_lab/plugins/pokemon_fire_red/schema.py`

**VERIFIED:** IV offset is CONFIRMED at +0x14. `BATTLE_MON.iv_bits = 0x14` is already defined at socket_reader.lua:297 but never read by `read_battle_mon()`. No decomp verification needed -- the constant is already in the codebase.

**Specifications:**
1. **Lua:** In `read_battle_mon()` (socket_reader.lua:759-818), add:
   - `local iv_bits = mem.read_u32_le(base + BATTLE_MON.iv_bits, DOM)`
   - Include `iv_bits` in the JSON output string for enemy mon
   - This is a ONE-LINE READ using the EXISTING offset constant
2. **Schema:** Add to `FireRedEnemyPokemon` class (schema.py ~line 430):
   - `ivs_raw: int = Field(default=0, ge=0, description="gBattleMons[1] offset +0x14, u32 LE packed IVs")`
   - `hp_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 0-4 of ivs_raw")`
   - `atk_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 5-9 of ivs_raw")`
   - `def_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 10-14 of ivs_raw")`
   - `spe_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 15-19 of ivs_raw")`
   - `spa_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 20-24 of ivs_raw")`
   - `spd_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 25-29 of ivs_raw")`
3. **Schema:** Add model_validator to `FireRedEnemyPokemon` to extract IVs from ivs_raw using `extract_ivs()` from battle_intel.py
4. Mirror Lua changes to reader.lua

**Verification:**
- [ ] `luac -p socket_reader.lua` passes
- [ ] `luac -p reader.lua` passes
- [ ] Both files have identical read_battle_mon() IV read
- [ ] Schema accepts ivs_raw and populates individual IV fields
- [ ] Existing tests still pass: `pytest tests/test_automation_routes.py`

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify read_context() (that was Wave 1)
- Do NOT modify server.py enrichment (separate task)

---

### Task Package 2.3: Fix API Proxy Container-Mode Gate

**Scope:** Remove the `_CONTAINER_MODE` gate from the existing proxy route so game-state.js can reach the ROM Lab API in local development.

**CRITICAL CORRECTION:** The proxy route ALREADY EXISTS at `.council/web/routes/romlab_runtime.py:597`:
```python
@router.api_route("/api/romlab/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def romlab_http_proxy(request, path, current_user):
```
The issue is a `_CONTAINER_MODE` gate at line 609:
```python
if not _CONTAINER_MODE:
    raise HTTPException(status_code=503, detail="Rom-lab HTTP proxy is only available in container mode")
```
This blocks the proxy in local development, causing the game state tab to get 503 errors.

**Files to Modify:**
- `.council/web/routes/romlab_runtime.py` (line 609 region)

**Specifications:**
1. Remove or comment out the `_CONTAINER_MODE` check at line 609
2. The proxy already handles connection errors gracefully (httpx timeout -> 502)
3. The proxy is already behind Council auth (requires get_current_user)
4. No new code needed -- just remove a 2-line gate

**Verification:**
- [ ] `curl -H "Authorization: Bearer <token>" http://localhost:8015/api/romlab/state/enriched` returns game state JSON (not 503)
- [ ] `curl -H "Authorization: Bearer <token>" http://localhost:8015/api/romlab/health` returns health check
- [ ] game-state.js in browser successfully fetches and renders state
- [ ] When ROM Lab is not running, proxy returns 502 (not 500 or 503)

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify existing `/api/romlab-runtime/*` routes
- Do NOT modify game-state.js (it already has the correct URL)
- Do NOT add new proxy routes -- fix the existing one

---

### Task Package 2.4: Enriched State Battle Intelligence

**Scope:** Extend the /state/enriched endpoint to include damage estimates for YOUR moves vs the enemy.
**Files to Modify:**
- `src/rom_lab/api/server.py`

**Specifications:**
1. In `_enrich_state_with_plugin_lookup()` or the `/state/enriched` handler (lines 281-313):
   - If state has battle data and YOUR active Pokemon has moves:
   - For each of YOUR Pokemon's moves, look up move power and category (physical/special) from decomp database
   - Use YOUR Pokemon's attack stat (attack for physical, sp_attack for special) as the attacker
   - Use ENEMY Pokemon's defense stat (defense for physical, sp_defense for special) as the defender
   - Compute STAB based on YOUR Pokemon's types vs move type
   - Compute effectiveness vs ENEMY types
   - Call `gen3_damage_calc()` from battle_intel.py for each move
   - Add `damage_estimates: list[dict]` to the battle section of the response
   - Each estimate: `{"move_name": str, "move_id": int, "min": int, "max": int, "avg": float, "effectiveness": float, "is_stab": bool}`
2. IVs already flow through schema (Task 2.2) -- just ensure they appear in model_dump()

**Verification:**
- [ ] /state/enriched in battle includes `battle.enemy.hp_iv` etc.
- [ ] /state/enriched in battle includes damage_estimates list with YOUR move names
- [ ] /state/enriched outside battle has no damage_estimates (no crash)
- [ ] Existing endpoint behavior unchanged for non-battle state

**Out of Scope (DO NOT TOUCH):**
- Do NOT modify the /state endpoint (only /state/enriched)
- Do NOT modify schema.py (already done in 2.2)
- Do NOT modify Lua readers (already done in 2.2)
<!-- ID: milestone_tracking -->
| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| Wave 1 Complete: Shop detection | Day 1 | Coder | Pending | luac -p passes, open_menu_id changes |
| Wave 2.1 Complete: Battle intel utils | Day 2 | Coder | Pending | pytest test_battle_intel.py passes |
| Wave 2.2 Complete: Lua+Schema IVs | Day 2 | Coder | Pending | luac -p passes, schema validation |
| Wave 2.3 Complete: API proxy | Day 2 | Coder | ✅ Complete | proxy gate removed, curl /api/romlab/state returns JSON |
| Wave 2.4 Complete: Enriched state | Day 3 | Coder | Pending | /state/enriched includes IVs+damage |
| Wave 3.1 Complete: Battle UI panel | Day 4 | Coder | Pending | Manual QA: IV bars + damage ranges |
| Wave 3.2 Complete: Hold-to-spam | Day 4 | Coder | ✅ Complete | REPEAT_INTERVAL_MS=100, all buttons repeat on hold, drag-off clears timer |
| All tests pass | Day 4 | Coder | Pending | pytest -q passes, no regressions |
<!-- ID: retro_notes -->
## Retrospective Notes

### Research Discrepancies Corrected

| Research Claim | Actual Reality | Impact on Design |
|---|---|---|
| `/api/romlab/state/enriched` endpoint DOES NOT EXIST | Endpoint EXISTS at `src/rom_lab/api/server.py:281` on port 8100 | Designed proxy route instead of new endpoint. Root cause is missing reverse proxy on Council web (8015), not missing endpoint. |
| IVs can be derived from personality value | Gen 3 IVs are a SEPARATE packed u32 in the battle mon struct, NOT derived from personality | Lua reader must read IV field at its own offset from `gBattleMons[1]`, not compute from personality. |
| BattleModel has damage prediction | `_predict_damage()` is observation-based (averages), not formula-based | Designed NEW pure-function Gen 3 damage calculator in `battle_intel.py` rather than modifying BattleModel |

### Design Trade-offs

1. **Proxy route vs CORS**: Chose reverse proxy (`/api/romlab/*` -> `localhost:8100/*`) over CORS headers. Rationale: Same-origin is simpler, avoids preflight requests, and matches existing `romlab_runtime.py` pattern that already imports httpx. The proxy adds ~2ms latency which is negligible for 2-second polling.

2. **New file vs extend existing for battle intel**: Created `battle_intel.py` as a NEW file rather than extending `BattleModel` in `learning/models/battle.py`. Rationale: The observation-based BattleModel serves a fundamentally different purpose (learning from historical data) than the formula-based damage calculator (deterministic preview). Mixing them would violate single-responsibility. The new file contains pure functions with zero external dependencies.

3. **Composite guard pattern for shop detection**: Adopted the proven `yesno_active` guard pattern (window_id AND confirming signal) rather than a simpler single-check approach. Rationale: Single RAM address checks are prone to stale-pointer false positives (the root cause of the current shop bug). The dual-check pattern was already proven reliable for yes/no menu detection.

4. **Wave-based task parallelism**: Organized 7 task packages into 3 sequential waves rather than a flat list. Rationale: Wave 1 (Lua/schema) must complete before Wave 2 (API/backend) can consume the new data. Wave 2 must complete before Wave 3 (frontend) can render it. Within each wave, task packages are independent and can execute in parallel via separate Coder agents.

### Deferred Items (P4 -- Future Work)

- **WebSocket push for live state updates**: Currently the game state tab polls at 2-second intervals. A WebSocket-based push system would reduce latency to <100ms. Deferred because the polling approach works adequately for the current use case and WebSocket infrastructure would require significant changes to both the ROM Lab API server and the frontend.
- **Bag/PC menu detection**: The research identified `sBagMenuDisplay` and `sPokedexScreenData` as potential bag/PC indicators, but flagged them as stale-heap-prone. Deferred pending deeper RAM investigation to find reliable confirming signals.
- **Joystick mode**: Virtual D-pad for mobile/touch interaction. Deferred because it requires UI design work and the hold-to-spam feature covers the most common input UX pain point.

### Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| IV offset in gBattleMons may differ from expected | Medium | High -- wrong IVs displayed | Task 2.2 includes decomp verification step; Coder must confirm exact offset before reading |
| Shop window_id RAM address stale during transitions | Low | Medium -- brief false positive | Composite guard pattern (window_id AND script_mode) prevents stale reads |
| httpx proxy adds latency to state polling | Low | Low -- 2ms on 2s interval | Negligible; can add connection pooling if needed |
| Hold-to-spam fires too fast for game engine | Low | Medium -- missed inputs | Configurable repeat rate (default 100ms); BizHawk processes at frame rate anyway |
