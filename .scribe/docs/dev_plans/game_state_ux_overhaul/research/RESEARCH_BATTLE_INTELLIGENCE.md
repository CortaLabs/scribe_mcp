
# 🔬 Research Battle Intelligence — game_state_ux_overhaul
**Author:** Specter
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-02-22 15:23:15 UTC

> Investigation of battle state perception, `look()` tool functionality, enemy Pokemon data collection, and damage calculation capabilities for UX overhaul project.

---
## Executive Summary
<!-- ID: executive_summary -->

The `look()` MCP tool already collects comprehensive battle intelligence including enemy IVs (via personality), nature, moves, abilities, gender, and stats. The `move_to()` tool correctly returns the full `look()` snapshot post-movement. Damage calculation data is available but not yet displayed; type effectiveness multipliers are shown in the move menu. All critical data for UX enhancements is collected; implementation primarily requires display layer work.

**Primary Objective:** Understand current state of battle intelligence in look tool and data collection infrastructure

**Key Takeaways:**
- **HIGH CONFIDENCE**: `look()` displays enemy nature, ability, gender, stats, and catch difficulty
- **HIGH CONFIDENCE**: `move_to()` includes full `look()` snapshot in return (both success and failure paths)
- **HIGH CONFIDENCE**: Enemy Pokemon personality and OT_ID are collected; IVs can be derived
- **MEDIUM-HIGH CONFIDENCE**: BattleModel has damage prediction logic; data available but not exposed
- **Immediate opportunity**: Display enemy IVs, personality, shiny value in look() output
- **Medium-term opportunity**: Integrate damage calculator into move menu


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** Specter

**Investigation Window:** 2026-02-22 15:23 — 2026-02-22 15:25 UTC

**Focus Areas:**
- [x] Implementation of the `look()` MCP tool and battle state rendering
- [x] Battle data collection in Lua readers (socket_reader.lua, reader.lua)
- [x] Battle schema in Python (FireRedEnemyPokemon, FireRedBattleState)
- [x] `move_to()` tool return value structure and look() integration
- [x] Damage calculation capabilities (BattleModel, type effectiveness)
- [x] Data collection vs. display gap analysis

**Dependencies & Constraints:**
- Analysis scoped to Pokemon Fire Red (GBA)
- No modifications to Lua or code; research only
- Based on commit ~5984ce5 (starter automation fixes checkpoint)


---
## Findings
<!-- ID: findings -->

### Finding 1: `look()` Already Shows Battle Intelligence
- **Summary:** The `look()` tool renders comprehensive enemy Pokemon details including nature, ability, gender, stats, catch difficulty, and move details with type/power/accuracy/category
- **Evidence:** `mcp/src/rom_lab_mcp/tools.py` lines 8724-8950 (battle section)
  - Enemy rendering: lines 8795-8851
  - Move effectiveness: lines 8928-8950
  - LookBattlePokemon snapshot: lines 8854-8876
- **Details:**
  - Enemy display includes: name, level, HP, types, status, gender (computed), nature (enriched), stats, catch difficulty (wild only), ability + description, moves with PP/type/power/category
  - Your Pokemon display includes: name, level, HP, types, status, nature, ability + description, moves
  - Move menu shows effectiveness multipliers (super_effective, not_very_effective, no_effect, status)
- **Confidence:** HIGH

### Finding 2: `move_to()` Correctly Returns `look()` Snapshot
- **Summary:** The `move_to()` tool returns a full `look()` result in both success and failure paths
- **Evidence:** `mcp/src/rom_lab_mcp/tools.py`
  - Success path: lines 11115-11117 calls `look()` and returns text + snapshot
  - Failure paths (marker resolution, pathfinding, policy): lines 10405-10427, 10715-10720, 10787-10792 all include look text + snapshot
  - Final return: line 11225 returns wrapped result with look_text + look_snapshot
- **Details:**
  - Return structure includes `"text"` and `"snapshot"` from `look()`
  - Plus metadata: path_taken, tiles_moved, success, adjusted_target, final_position, replans_used, etc.
  - UI can use snapshot for structured data access
- **Confidence:** HIGH

### Finding 3: Enemy Pokemon Data Collected but IVs Not Displayed
- **Summary:** Lua readers collect personality and ot_id from gBattleMons[1]; IVs can be derived but are not shown in text
- **Evidence:** 
  - Schema: `src/rom_lab/plugins/pokemon_fire_red/schema.py` lines 430-480 (FireRedEnemyPokemon)
  - Fields: personality (offset +0x50, u32 LE), ot_id (offset +0x54, u32 LE)
  - Shiny computation: validator line 477-480 calls `_compute_shiny_value(ot_id, personality)`
  - IVs: Can be derived from personality via Gen 3 IV extraction (not yet implemented)
- **Details:**
  - Personality is directly available in schema
  - OT ID is directly available in schema
  - Shiny value is computed and stored
  - IVs would require: personality XOR with species-specific constants (Gen 3 formula)
- **Confidence:** HIGH

### Finding 4: Damage Calculation Data Available but Not Exposed
- **Summary:** BattleModel has damage prediction logic; type effectiveness multipliers shown in move menu but full damage estimates not exposed
- **Evidence:**
  - BattleModel: `src/rom_lab/learning/models/battle.py` lines 151-230
  - _predict_damage() method: lines 151-193 computes damage from move + stats
  - _predict_type_effectiveness() method: lines 195-230 returns effectiveness multipliers
  - Effectiveness in schema: `src/rom_lab/plugins/pokemon_fire_red/schema.py` line 522 (move_effectiveness field)
  - Look rendering: lines 8933-8948 shows eff_by_name lookup but only as suffix to move name
- **Details:**
  - Move menu displays move effectiveness (1x, 2x, 0.5x, 0x) via eff_by_name dict
  - Full damage calc requires: move power, attacker level + stat mods, defender level + defenses, type effectiveness
  - Gen 3 damage formula is implementable with available data
  - Damage range (85-100% roll) would need simulation
- **Confidence:** MEDIUM-HIGH

### Finding 5: Gap Between Collection and Display
- **Summary:** Critical data is collected but not displayed in text or snapshot
- **Evidence:** 
  - Collected: personality, ot_id, shiny_value, stats, moves, ability, types, catch_rate
  - Text display: name, level, HP, types, status, gender, nature, stats, catch_rate (wild), ability, moves
  - Snapshot display: species_id, level, current_hp, max_hp, types, status, gender, moves, stats, ability, nature, catch_rate
  - Missing from snapshot: personality, ot_id, shiny_value, IVs
- **Details:**
  - Personality is available in raw schema but not in LookBattlePokemon snapshot
  - OT ID is available in raw schema but not in snapshot
  - IVs not displayed anywhere (would need derivation)
  - Text display already shows most important fields (nature, ability, moves, stats)
- **Confidence:** HIGH

---
## Technical Analysis
<!-- ID: technical_analysis -->

**Code Patterns Identified:**
- Clean separation: Lua reads bytes → Python validates schema → Bridge enriches → API serves
- Two-path rendering: `look()` produces both text (human) and snapshot (structured JSON)
- Enrichment pattern: `_clean_enemy_for_agent()` and `_clean_pokemon_for_agent()` lookup functions add nature, ability descriptions, move details
- Type effectiveness computed at render time from move_effectiveness field (lazy)

**System Interactions:**
- Lua reader (socket mode primary, file mode fallback) → JSON file → StateBridge → Enriched state
- LocalKnowledgeStore.enrich_state() populates move_effectiveness list
- decomp database lookups (species, move, type, ability data) happen in clean functions
- look() tool integrates output from multiple sources (context, party, map, battle, screen_text)

**Risk Assessment:**
- **Nature calculation**: Requires personality value; currently done inline in clean functions but not stored
- **IV derivation**: Personality-based; Gen 3 formula not yet implemented (doable)
- **Data freshness**: Snapshot is point-in-time; battle state changes may not reflect immediately if UI caches
- **Damage rollover**: Damage range (85-100%) requires simulation; snapshot only shows expected value


---
## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps
- [x] Analyze `look()` tool implementation and battle rendering
- [x] Verify `move_to()` includes look() snapshot
- [ ] **Next: Blueprint** — Design UX layout for displaying:
  - Enemy IVs (derived from personality)
  - Enemy shiny value (already computed)
  - Damage calculator (move vs. enemy type + stats)
  - Live move effectiveness as you cursor through move menu
- [ ] **Next: Forge** — Implement IV derivation function from personality (Gen 3 formula)
- [ ] **Next: Forge** — Add IV/shiny fields to LookBattlePokemon snapshot
- [ ] **Next: Forge** — Integrate BattleModel._predict_damage or write thin wrapper

### Long-Term Opportunities
- Store nature in schema (currently computed inline)
- Cache decomp lookups to avoid repeated DB calls during look() rendering
- Expose damage calculator as standalone MCP tool for AI reasoning
- Support damage range simulation (85-100% roll distribution)
- Add held item effects to damage calculation (currently not collected in battle)
- Add weather/terrain effects to damage calculation (not collected in battle)

---
## Appendix
<!-- ID: appendix -->

**References:**
- `mcp/src/rom_lab_mcp/tools.py` (11225 lines) — Primary MCP tool implementation
- `src/rom_lab/plugins/pokemon_fire_red/schema.py` (573 lines) — Data models
- `src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` (1973 lines) — Lua reader
- `src/rom_lab/learning/models/battle.py` (425 lines) — Damage prediction model

**Key Functions:**
- `look()` — Main tool for game state snapshots (lines 7816-9151)
- `move_to()` — Navigation tool with look() integration (lines 10300-11225)
- `_clean_enemy_for_agent()` — Enrichment with nature, ability desc, move details
- `_clean_pokemon_for_agent()` — Enrichment for active Pokemon
- `_compute_shiny_value()` — OT ID + personality → shiny value
- `_get_gender()` — Species ID + personality → gender

**Confidence Scoring:**
- HIGH: Code verified, design clear, no ambiguity
- MEDIUM-HIGH: Code verified, logic clear, minor unknowns
- MEDIUM: Pattern apparent, verification incomplete
- LOW: Hypothesis, needs confirmation

---