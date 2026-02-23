---
id: game_state_ux_overhaul-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 game_state_ux_overhaul"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 15:46:17 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — game_state_ux_overhaul
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 15:16:51 UTC

> Architecture guide for game_state_ux_overhaul.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement

**Context:** The BizHawk web UI's game state panel has multiple gaps in its perception pipeline and display layer. The AI agent cannot detect shop/bag/PC menus (open_menu_id hardcoded to 0), battle intelligence data is collected but not fully exposed (IVs, damage predictions), and the game state tab in the web UI polls an endpoint that requires a missing proxy route.

**Goals:**
- P0: Fix stale menu detection -- add shop, bag, PC menu detection to Lua perception pipeline with stale-state guards
- P1: Expose battle intelligence -- derive IVs from personality, add Gen 3 damage formula calculator, surface all data in enriched state
- P2: Fix game state tab -- create API proxy route so web UI can reach /state/enriched, add manual "look" button, battle intelligence panel
- P3: Input control UX -- hold-to-spam auto-repeat, joystick mode toggle
- P4: Live telemetry -- WebSocket push for state updates (future consideration)

**Non-Goals:**
- Redesigning the CSS architecture (existing BEM dark theme is good)
- Rewriting the existing BattleModel observation system (it serves learning; we add a formula calc alongside it)
- Mobile-specific layout changes
- Adding items/weather/terrain to damage calc (future)

**Success Metrics:**
- open_menu_id reflects actual menu state with < 500ms latency and auto-clears
- Enemy IVs visible in enriched state and battle panel
- Damage estimates per move shown in battle panel
- Game state tab polls successfully through proxy and renders live data
- Hold-to-spam works on all buttons
- All changes pass existing test suites + new tests

**Research References:**
- RESEARCH_SHOP_BUG_CONTEXT_STATE.md: 9 findings on menu detection architecture gaps
- RESEARCH_BATTLE_INTELLIGENCE.md: 5 findings on battle data collection vs display gaps
- RESEARCH_UI_STATE.md: Game state tab implementation, input controls, data flow analysis
<!-- ID: requirements_constraints -->
## 2. Requirements and Constraints

**Functional Requirements:**
- FR1: Lua `read_context()` must detect shop, bag, and PC menu states via RAM reads
- FR2: Menu detection must use composite guards (window ID + confirmation signal) to prevent stale states
- FR3: Both `socket_reader.lua` and `reader.lua` must be updated in sync (socket-first)
- FR4: Gen 3 IV derivation function: extract 6 IVs (HP/Atk/Def/Spe/SpA/SpD) from personality value
- FR5: Gen 3 damage formula function: compute damage range given move power, attacker stats, defender stats, type effectiveness, STAB, level
- FR6: `/state/enriched` must be accessible from the web UI via an API proxy route
- FR7: Enriched state response must include battle intelligence fields (IVs, damage estimates, move effectiveness)
- FR8: Input buttons must support hold-to-spam with configurable repeat interval
- FR9: D-pad must support joystick mode toggle (virtual analog stick)

**Non-Functional Requirements:**
- NFR1: Sacred separation preserved -- Lua reads bytes, bridge validates, schema is contract, API serves
- NFR2: No hardcoded values -- all thresholds in constants or config
- NFR3: BEM CSS architecture maintained for all new UI components
- NFR4: Dark theme consistency (existing color variables)
- NFR5: Menu detection latency <= game frame budget (1/60s for Lua execution)
- NFR6: Auto-repeat interval ~100ms (6 frames at 60fps), configurable

**Assumptions:**
- Fire Red GBA only (240x160 native, 960x640 displayed)
- `sShopMenuWindowId` at 0x02039950 is reliable (verified in tools.py)
- Personality-based IV extraction uses standard Gen 3 formula
- Council web server proxies to rom-lab API on localhost:8100

**Risks and Mitigations:**
- R1: Stale menu pointers -- Mitigate with composite checks (window + result variable), same pattern as yesno_active
- R2: Bag/PC menu RAM addresses unknown -- Mitigate by using gMain.callback2 callback matching (more reliable than heap pointers per RESEARCH_STALE_HEAP_POINTERS.md)
- R3: Proxy adds latency -- Mitigate by keeping proxy lightweight (pass-through, no transformation)
- R4: Damage formula accuracy -- Mitigate by implementing exact Gen 3 formula from decomp source, test against known values
<!-- ID: architecture_overview -->
## 3. Architecture Overview

**Solution Summary:** Five interconnected changes across the perception pipeline, backend API, and frontend UI. Each layer follows the sacred separation principle.

### 3.1 Component Diagram

```
[Lua Reader] ──read_context()──> [JSON state] ──> [StateBridge] ──> [Schema] ──> [API /state/enriched]
     |                                                                              |
     | NEW: shop/bag/PC                                                             | NEW: IV derivation
     | menu detection                                                               | damage estimates
     | (RAM reads + guards)                                                         | battle intel fields
     |                                                                              |
     v                                                                              v
[socket_reader.lua]                                                     [rom-lab API :8100]
[reader.lua]                                                                        |
                                                                            NEW: proxy route
                                                                                    |
                                                                                    v
                                                              [Council Web :8015] /api/romlab/*
                                                                                    |
                                                                                    v
                                                              [game-state.js] ──> [UI Panel]
                                                              [bizhawk.js]         |
                                                                            NEW: battle intel panel
                                                                            NEW: hold-to-spam
                                                                            NEW: joystick mode
```

### 3.2 Data Flow per Feature

**Menu Detection (P0):**
```
RAM (0x02039950 sShopMenuWindowId, gMain.callback2) 
  -> Lua read_context() reads bytes, applies composite guard
  -> JSON: open_menu_id = 1 (shop) | 2 (bag) | 3 (pc) | 0 (none)
  -> StateBridge validates via schema FireRedGameContext.open_menu_id
  -> API serves in context block
  -> UI _detectMode() can show SHOP/BAG/PC instead of generic MENU
```

**Battle Intelligence (P1):**
```
Schema: personality (u32) already collected from gBattleMons[1]
  -> NEW: iv_derivation.py: extract_ivs(personality) -> {hp, atk, def, spe, spa, spd}
  -> NEW: damage_calc.py: gen3_damage(move_power, atk, def, level, stab, effectiveness) -> {min, max, avg}
  -> /state/enriched adds: enemy.ivs, enemy.damage_estimates per move
  -> UI battle panel renders IV spread and damage ranges
```

**Game State Tab Fix (P2):**
```
game-state.js polls /api/romlab/state/enriched (port 8015)
  -> NEW: proxy route on Council web (/api/romlab/* -> localhost:8100/*)
  -> Response flows through existing _render() pipeline
  -> NEW: "Look" button calls MCP look() tool via SDK session
  -> Battle section expands with intelligence panel
```

**Input Controls (P3):**
```
bizhawk.js mousedown/touchstart handlers
  -> NEW: setInterval auto-repeat while button held (100ms default)
  -> mouseup/touchend clears interval
  -> NEW: joystick mode: replace d-pad swipe with virtual joystick (angle -> nearest direction)
```

### 3.3 External Integrations
- ROM Lab API (localhost:8100): Source of enriched game state
- BizHawk WebSocket (/bizhawk/stream): Button press commands forwarded to emulator
- Decomp database (pokeapi.db): Species data for type effectiveness, move details
- Council Web Server (localhost:8015): Hosts the UI, proxies to ROM Lab API
<!-- ID: detailed_design -->
## 4. Detailed Design

### 4.1 Menu Detection Subsystem (P0)

**Purpose:** Add shop menu detection to the Lua perception pipeline with stale-state guards.

**File: `src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua`** (and reader.lua mirror)

Changes to `read_context()` function (currently lines 945-1029):

1. Add RAM address constants to MENU table (near other menu constants):
```lua
MENU.shop_window_id = 0x02039950   -- sShopMenuWindowId (u8, 0xFF=none)
```

2. In `read_context()`, after yesno_active detection (line 1003), add:
```lua
-- Shop detection: sShopMenuWindowId (0xFF = no shop, other = active window ID)
-- Guard: only trust when script_mode ~= 0 (shop script running)
local shop_wid = mem.read_u8(MENU.shop_window_id, DOM)
local in_shop = (shop_wid ~= 0xFF and shop_wid ~= 0) and (script_mode ~= 0)
```

3. Replace `local open_menu_id = 0` (line 1009) with:
```lua
-- Menu ID: 0=none, 1=shop, 2=bag, 3=pc
local open_menu_id = 0
if in_shop then
    open_menu_id = 1
end
```

4. Bag and PC detection deferred (requires callback2 research per R2 risk).

**Schema:** No changes needed -- `open_menu_id: int = Field(default=0)` at schema.py:415 already exists.

**Stale-State Guard Pattern:**
Same pattern as yesno_active (verified at socket_reader.lua:992-1003):
- Read window ID from RAM
- Check window is not "none" sentinel (0xFF or 0)
- AND confirming signal is active (script_mode != 0)
- Prevents flag from persisting after shop closes

---

### 4.2 Battle Intelligence Subsystem (P1)

**Purpose:** Read enemy IVs from gBattleMons[1], implement Gen 3 damage formula, surface in enriched state.

#### 4.2.1 Enemy IV Reading

**VERIFIED FACT:** `BATTLE_MON.iv_bits = 0x14` is DEFINED at socket_reader.lua:297 but NOT READ by `read_battle_mon()`. The offset is already known and correct.

**Lua change:** In `read_battle_mon()` (socket_reader.lua:759-818), add:
```lua
local iv_bits = mem.read_u32_le(base + BATTLE_MON.iv_bits, DOM)
```
And include `iv_bits` in the JSON output string.

**Schema change:** Add to `FireRedEnemyPokemon` (schema.py ~line 430):
```python
ivs_raw: int = Field(default=0, ge=0, description="gBattleMons[1] offset +0x14, u32 LE packed IVs")
hp_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 0-4 of ivs_raw")
atk_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 5-9 of ivs_raw")
def_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 10-14 of ivs_raw")
spe_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 15-19 of ivs_raw")
spa_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 20-24 of ivs_raw")
spd_iv: int = Field(default=0, ge=0, le=31, description="Derived: bits 25-29 of ivs_raw")
```
Add model_validator to extract IVs from ivs_raw using `extract_ivs()` from battle_intel.py.

#### 4.2.2 Damage Calculator

**New file: `src/rom_lab/plugins/pokemon_fire_red/battle_intel.py`**

Two pure utility functions:

```python
def extract_ivs(ivs_raw: int) -> dict[str, int]:
    """Extract Gen 3 IVs from packed u32 (gBattleMons iv_bits field).
    
    Bits 0-4: HP, 5-9: Atk, 10-14: Def, 15-19: Spe, 20-24: SpA, 25-29: SpD
    """

def gen3_damage_calc(
    level: int, move_power: int, attack_stat: int, defense_stat: int,
    stab: bool, effectiveness: float, is_critical: bool = False,
) -> dict[str, int | float]:
    """Gen 3 damage formula. Returns {"min": int, "max": int, "avg": float}."""
```

Both are pure functions with zero external dependencies -- trivially testable.

#### 4.2.3 Enriched State Extension

**File: `src/rom_lab/api/server.py`** -- In `/state/enriched` handler or `_enrich_state_with_plugin_lookup()`:

After existing enrichment (species names, moves, abilities), add battle intelligence:
- IVs already flow through schema from Lua -> bridge -> schema (Task 2.2 handles this)
- For each of YOUR Pokemon's moves, compute damage estimate vs enemy:
  - Look up move power and category (physical/special) from decomp database
  - Use YOUR attacker's stat (attack for physical, sp_attack for special)
  - Use ENEMY defender's stat (defense for physical, sp_defense for special)
  - Compute STAB based on your Pokemon's types vs move type
  - Compute effectiveness vs enemy types
  - Call `gen3_damage_calc()` for each move
- Add `damage_estimates: list[dict]` to battle section of response
- Each: `{"move_name": str, "move_id": int, "min": int, "max": int, "avg": float, "effectiveness": float, "is_stab": bool}`

---

### 4.3 API Proxy Route (P2)

**VERIFIED:** The proxy route ALREADY EXISTS at `romlab_runtime.py:597`:
```python
@router.api_route("/api/romlab/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def romlab_http_proxy(request, path, current_user):
```

**The issue:** The proxy has a `_CONTAINER_MODE` gate at line 609:
```python
if not _CONTAINER_MODE:
    raise HTTPException(status_code=503, detail="Rom-lab HTTP proxy is only available in container mode")
```

This means in local development, the proxy returns 503. The game state tab only works in Docker container deployments.

**Fix options (choose one):**
1. **Remove the container-mode gate** (simplest) -- allow the proxy to work in all modes. Risk: attempts to connect to localhost:8100 when ROM Lab isn't running would 502.
2. **Add a dev-mode fallback** -- detect if ROM Lab is running on localhost:8100, proxy if so.
3. **Point JS directly at ROM Lab port** -- change game-state.js to dynamically select the URL based on runtime mode.

**Recommended: Option 1** -- Remove the `_CONTAINER_MODE` check. The proxy already handles connection errors gracefully (httpx timeout -> 502). This is safe because:
- ROM Lab always runs on localhost:8100 when active
- The proxy is behind Council auth (requires get_current_user)
- 502 is a clean error when ROM Lab isn't running

---

### 4.4 Frontend Battle Intelligence Panel (P2)

**File: `.council/web/static/js/game-state.js`**

Extend `_renderBattle(state)` to show:
1. Enemy IV spread: 6 bars (HP/Atk/Def/Spe/SpA/SpD), width proportional to value/31
2. Damage estimates per YOUR move: `MoveName: XX-YY dmg (X.Xeff)`
   - Green: survivable, Red: potential OHKO, Yellow: 2HKO range
3. Type effectiveness badges (already partially shown)
4. Shiny indicator (already computed in schema)

**File: `.council/web/static/css/bizhawk.css`**

Add BEM classes under `.gamestate__battle-intel`:
- `.gamestate__battle-intel__iv-bar` -- individual IV bar
- `.gamestate__battle-intel__damage-range` -- min/max damage
- `.gamestate__battle-intel__effectiveness` -- type matchup chip

---

### 4.5 Input Control Enhancements (P3)

**File: `.council/web/static/js/bizhawk.js`**

#### Hold-to-Spam:
In button event handlers (lines 2058-2093), add setInterval auto-repeat:
```javascript
// On mousedown/touchstart:
this._sendInput('keydown', button);
this._repeatTimers = this._repeatTimers || {};
this._repeatTimers[button] = setInterval(() => {
    this._sendInput('keydown', button);
}, REPEAT_INTERVAL_MS);

// On mouseup/touchend/mouseleave:
if (this._repeatTimers?.[button]) {
    clearInterval(this._repeatTimers[button]);
    delete this._repeatTimers[button];
}
this._sendInput('keyup', button);
```

Where `REPEAT_INTERVAL_MS = 100` (~6 frames at 60fps).

Apply to BOTH action buttons (A/B/Start/Select) AND d-pad directions.
For keyboard input (lines 408-443), same pattern: on keydown without repeat flag, start interval. On keyup, clear interval.

#### Joystick Mode (DEFERRED):
D-pad already has swipe support (bizhawk.js:2096-2098). True joystick mode deferred to future work -- hold-to-spam covers the primary UX pain point.
<!-- ID: directory_structure -->
## 5. Directory Structure

```
/home/austin/projects/pokemon/rom_lab/
├── src/rom_lab/
│   ├── plugins/pokemon_fire_red/
│   │   ├── lua/
│   │   │   ├── socket_reader.lua          # PRIMARY: read_context() menu detection (MODIFY)
│   │   │   └── reader.lua                 # MIRROR: same changes as socket_reader (MODIFY)
│   │   ├── schema.py                      # FireRedEnemyPokemon IV fields (MODIFY)
│   │   ├── battle_intel.py                # NEW: IV extraction + damage calc utilities
│   │   └── plugin.py                      # normalize() -- no changes needed
│   ├── api/
│   │   └── server.py                      # /state/enriched enrichment (MODIFY)
│   ├── learning/models/
│   │   └── battle.py                      # Existing BattleModel (NO CHANGES)
│   └── bridge/
│       └── stream.py                      # StateBridge (NO CHANGES)
├── .council/web/
│   ├── routes/
│   │   └── romlab_runtime.py              # Add proxy route /api/romlab/* (MODIFY)
│   ├── pages/
│   │   └── bizhawk.html.j2               # Template (NO CHANGES expected)
│   └── static/
│       ├── js/
│       │   ├── game-state.js              # Battle intel panel, look button (MODIFY)
│       │   └── bizhawk.js                 # Hold-to-spam, joystick mode (MODIFY)
│       └── css/
│           └── bizhawk.css                # Battle intel CSS classes (MODIFY)
├── mcp/src/rom_lab_mcp/
│   └── tools.py                           # look() tool (NO CHANGES)
└── tests/
    ├── test_battle_intel.py               # NEW: IV extraction + damage calc tests
    ├── test_menu_detection.py             # NEW: Menu state detection tests
    └── test_enriched_endpoint.py          # NEW: Enriched state proxy tests
```
<!-- ID: data_storage -->
## 6. Data and Storage

**No new datastores introduced.** All changes work within the existing data flow:

- **RAM** (read-only): New Lua reads of sShopMenuWindowId, gBattleMons[1].ivs
- **JSON state file**: Extended context and battle blocks (already structured)
- **Pydantic schema**: New fields on FireRedEnemyPokemon and FireRedGameContext
- **pokeapi.db**: Existing decomp database for species/move/type data (read-only, no changes)
- **No database migrations required**
<!-- ID: testing_strategy -->
## 7. Testing and Validation Strategy

**Unit Tests:**
- `tests/test_battle_intel.py`: IV extraction from packed u32, damage calc formula against known values
  - Test: extract_ivs(0x00000000) = all zeros
  - Test: extract_ivs(0x3FFFFFFF) = all 31s
  - Test: gen3_damage_calc with known move/stats produces expected range
  - Test: STAB modifier applies correctly (1.5x)
  - Test: Type effectiveness multipliers chain correctly

- `tests/test_menu_detection.py`: Mock Lua context output, verify open_menu_id values
  - Test: shop_wid=5, script_mode=1 -> open_menu_id=1
  - Test: shop_wid=0xFF, script_mode=1 -> open_menu_id=0 (no shop)
  - Test: shop_wid=5, script_mode=0 -> open_menu_id=0 (stale guard catches it)

**Integration Tests:**
- `tests/test_enriched_endpoint.py`: Test /state/enriched returns battle intelligence fields
  - Test: Response includes enemy.hp_iv, enemy.atk_iv, etc. when in battle
  - Test: Response includes enemy.damage_estimates when battle has moves
  - Test: Response includes context.open_menu_id from perception pipeline

**Manual QA:**
- Boot BizHawk with Fire Red, enter a shop, verify open_menu_id changes in /state/enriched
- Enter battle, verify enemy IVs appear in game state panel
- Hold A button in web UI, verify repeated inputs sent to emulator
- Toggle joystick mode, verify d-pad swipe changes behavior

**Existing Test Suites (must not break):**
- `pytest tests/test_automation_routes.py`
- `pytest tests/test_ws_endpoint_commands.py`
- `luac -p src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua`
- `luac -p src/rom_lab/plugins/pokemon_fire_red/lua/reader.lua`
<!-- ID: deployment_operations -->
## 8. Deployment and Operations

**Environments:** Local development only (BizHawk + rom-lab serve + council web)

**Release Process:**
1. Lua changes: Restart BizHawk to reload scripts
2. Python changes: Restart `rom-lab serve` (API on :8100)
3. Proxy route changes: Restart Council web (`council reload --web`)
4. JS/CSS changes: Hard refresh browser (Ctrl+Shift+R)

**Configuration:**
- `MENU.shop_window_id` in Lua constant table (hardcoded RAM address)
- `REPEAT_INTERVAL_MS` in bizhawk.js (JavaScript constant, configurable)
- Proxy target port (DEFAULT_PORT in romlab_runtime.py, already 8100)

**Verification Sequence:**
1. `luac -p socket_reader.lua && luac -p reader.lua` (syntax check)
2. `pytest tests/ -q` (all tests pass)
3. `scripts/build-streamer.sh` (if C# changes, not expected here)
4. Restart rom-lab serve, reload BizHawk
5. Open web UI, verify game state panel loads
6. Enter shop in game, verify open_menu_id = 1
7. Enter battle, verify enemy IVs visible
<!-- ID: open_questions -->
## 9. Open Questions and Follow-Ups

| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| gBattleMons[1] IV offset | -- | RESOLVED | Confirmed: BATTLE_MON.iv_bits = 0x14 at socket_reader.lua:297. Offset is +0x14 (20 bytes) into the BattlePokemon struct. Already defined in Lua but not read by read_battle_mon(). |
| Bag menu RAM signal | Research Agent | TODO | Need to identify reliable RAM address for bag menu detection (callback2-based approach preferred per RESEARCH_STALE_HEAP_POINTERS.md) |
| PC menu RAM signal | Research Agent | TODO | Same as bag -- heap pointers are stale-prone, need callback2-based approach |
| Proxy route container-mode gate | -- | RESOLVED | Proxy route ALREADY EXISTS at romlab_runtime.py:597. Issue is _CONTAINER_MODE gate at line 609 blocking local dev. Fix: remove the gate. |
| WebSocket push for state updates (P4) | Architect | DEFERRED | Would replace 2s polling. Requires server-side event source from StateBridge. Not in current scope. |
| Damage calc weather/terrain effects | Architect | DEFERRED | Gen 3 has weather modifiers (rain/sun/sand). Not collected in current Lua reader. Future enhancement. |
| Held item effects on damage | Architect | DEFERRED | Items like Choice Band affect damage. Not in current enemy schema. Future enhancement. |
| Damage estimates direction | -- | RESOLVED | Computes YOUR moves vs ENEMY (offensive), not enemy moves vs you. More useful for decision-making during battle. |
<!-- ID: references_appendix -->
## 10. References and Appendix

**Research Documents:**
- `.scribe/docs/dev_plans/game_state_ux_overhaul/research/RESEARCH_BATTLE_INTELLIGENCE.md`
- `.scribe/docs/dev_plans/game_state_ux_overhaul/research/RESEARCH_SHOP_BUG_CONTEXT_STATE.md`
- `.scribe/docs/dev_plans/game_state_ux_overhaul/research/RESEARCH_UI_STATE.md`

**Key Source Files (verified):**
- `src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua:945-1029` -- read_context() function
- `src/rom_lab/plugins/pokemon_fire_red/schema.py:415` -- open_menu_id field
- `src/rom_lab/plugins/pokemon_fire_red/schema.py:430-480` -- FireRedEnemyPokemon with personality/ot_id
- `src/rom_lab/api/server.py:281-313` -- /state/enriched endpoint
- `src/rom_lab/learning/models/battle.py:151-193` -- _predict_damage (observation-based, NOT formula)
- `.council/web/static/js/game-state.js:11` -- API_URL = '/api/romlab/state/enriched'
- `.council/web/routes/romlab_runtime.py` -- Existing runtime management routes
- `mcp/src/rom_lab_mcp/tools.py:1500-1648` -- _shop_window_active() debug detection

**RAM Addresses (verified):**
- `0x02039950` -- sShopMenuWindowId (u8, 0xFF=none)
- `0x0203ADF3` -- sYesNoWindowId (u8, stale-prone)
- `0x020370D0` -- gSpecialVar_Result (u16, 255=waiting)
- `0x03000EB1` -- sGlobalScriptContext.mode (u8, nonzero=script running)
- `0x02022B4C` -- gBattleTypeFlags (u32)
- `0x02022B58` -- gBattleOutcome (u8)

**Gen 3 Damage Formula Reference:**
```
damage = floor(floor(floor(2 * level / 5 + 2) * power * A / D) / 50 + 2)
damage *= STAB (1.5 if type matches attacker)
damage *= type effectiveness (0.0, 0.25, 0.5, 1.0, 2.0, 4.0)
damage *= random (85..100) / 100
```
Where A = attack stat (or sp.atk for special), D = defense stat (or sp.def for special).
