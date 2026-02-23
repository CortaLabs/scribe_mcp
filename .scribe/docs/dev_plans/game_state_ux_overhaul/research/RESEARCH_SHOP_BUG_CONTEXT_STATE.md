---
id: game_state_ux_overhaul-research-shop-bug-context-state
title: "\U0001F52C Research Shop Bug Context State \u2014 game_state_ux_overhaul"
doc_type: RESEARCH_SHOP_BUG_CONTEXT_STATE
doc_name: RESEARCH_SHOP_BUG_CONTEXT_STATE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 15:24:36 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Shop Bug Context State — game_state_ux_overhaul
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-22 15:23:20 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** [Describe the primary research goal]

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** nexus

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Finding 1: The Shop Bug Root Cause

**Confidence: HIGH** — Code inspection.

The reported bug ("shop flag set but never unsets") stems from a **missing implementation**:

1. **Lua reader has NO shop detection** — `open_menu_id` is hardcoded to 0 in `socket_reader.lua:1008-1009`
2. **Schema field exists but unused** — `FireRedGameContext.open_menu_id: int` (line 415 of schema.py) is always 0
3. **Shop state is debug-only** — Only `tools.py` has shop detection via `_shop_window_active()` using debug RAM reads

**The Problem**: There is no way for a shop being open to flow through the perception pipeline (Lua → JSON → schema → API). The field exists but has no source data.

---

## Finding 2: Context Detection System Architecture

**Confidence: HIGH** — Code inspection of `read_context()` in socket_reader.lua (lines 945-1029).

### What Context Currently Detects

The Lua reader's `read_context()` function reads these RAM signals:

| Signal | RAM Source | Detection Logic |
|--------|-----------|-----------------|
| **Battle** | `gBattleTypeFlags` (0x02022B4C) + `gBattleOutcome` (0x02022B58) | `(flags ≠ 0) AND (outcome == 0)` — outcome clears on battle end |
| **Dialogue/Text** | `sTextPrinters[0].active` (0x0202002B) | Nonzero = text on screen, definitive signal |
| **Frozen** | `gObjectEvents[0].flags1` bit 0 | When scripts lock player movement |
| **Script Running** | `sGlobalScriptContext.mode` (0x03000EB1) | Nonzero = NPC/event script active |
| **Yes/No Menu** | `sYesNoWindowId` (0x0203ADF3) + `gSpecialVar_Result` (0x020370D0) | Window exists AND `gSpecialVar_Result == 255` (waiting) |
| **Facing Direction** | `gObjectEvents[0].facing` offset +0x18, lower nibble | Values 0-4 (none/S/N/W/E) |
| **Player Movement** | `gObjectEvents[0].flags0` bits 6-7 | Active/finished flags |

### What Context Does NOT Detect

**Shops, Bags, PC menus, Pokedex, and other UI menus** — These are completely absent from `read_context()`.

---

## Finding 3: Where Shop Detection Exists

**Confidence: HIGH** — Direct code inspection.

### Debug-Only Shop Detection (tools.py)

File: `/home/austin/projects/pokemon/rom_lab/mcp/src/rom_lab_mcp/tools.py`

```python
# Lines 1500-1501
_SHOP_MENU_WINDOW_ID_ADDR = 0x02039950
_SHOP_WINDOW_NONE = 0xFF

# Lines 1630-1648
def _read_shop_window_id() -> int:
    """Read sShopMenuWindowId (0xFF/0=no active shop window)."""
    # Uses debug_tools to read RAM directly
    result = debug_tools._send_debug_request(
        {"type": "read", "addresses": [_SHOP_MENU_WINDOW_ID_ADDR]},
        timeout=1.0,
    )
    # Returns 0xFF if no shop, otherwise the window ID

def _shop_window_active() -> bool:
    wid = _read_shop_window_id()
    return wid not in (0, _SHOP_WINDOW_NONE)
```

**Problem**: This is used ONLY in `shop_buy()` and `shop_sell()` functions (lines 4347+). It's a **runtime check** before performing shop actions, NOT a state-tracking mechanism that flows through the schema.

---

## Finding 4: Other Stale State Issues

**Confidence: MEDIUM** — Design analysis.

Similar to the shop bug, these context/menu states are likely stale:

| State | Current Detection | RAM Signal | Status |
|-------|-------------------|-----------|--------|
| **Bag Menu** | ❌ None in Lua | `gBagMenuDisplay` (RAM varies) | LIKELY STALE if opened |
| **PC Storage** | ❌ None in Lua | `sPokedexScreenData`, `gStorage` pointers (varies) | LIKELY STALE if opened |
| **Pokedex** | ❌ None in Lua | Similar heap pointers (varies) | LIKELY STALE if opened |
| **Trainer Card** | ❌ None in Lua | Menu state globals | LIKELY STALE if opened |
| **Yes/No Menu** | ✅ Partially (stale warning in code) | `sYesNoWindowId` at 0x0203ADF3 | **KNOWN STALE** — WARNING at line 992 of socket_reader.lua |

The comment at line 992 is revealing:
```lua
-- WARNING: sYesNoWindowId is STALE — it persists after the player selects.
-- Only trust it when gSpecialVar_Result is still SCR_MENU_UNSET (255).
```

This suggests the developers **knew about the stale window ID problem** but only added a workaround for Yes/No menus, not other UIs.

---

## Finding 5: The `get_context()` Tool

**Confidence: HIGH** — Code inspection of tools.py:1011-1014.

```python
def get_context() -> dict:
    """Get current game context — battle, menu, dialogue, or overworld."""
    state = manager.get_enriched_state()
    return state.context.model_dump()
```

**Returns**: The `context` field from the schema, which includes:
- `in_battle`, `is_double_battle`
- `facing_direction`, `is_moving`, `movement_finished`
- `in_dialogue`, `text_active`, `waiting_for_input`
- `script_running`, `yesno_active`, `menu_awaiting_input`
- `last_talked_npc`, `open_menu_id` (always 0)

**Missing from API**: No shop state, bag state, PC state, or other UI menu states.

---

## Finding 6: Data Flow Pipeline Architecture

**Confidence: HIGH** — Tracing through the codebase.

```
Lua Reader (socket_reader.lua)
  * read_context() JSON: {in_battle, in_dialogue, ...}
  * open_menu_id = 0 (HARDCODED)
  * No shop detection code exists
         |
         v
StateBridge (bridge/stream.py)
  * normalize(): validates via Pydantic
  * context["open_menu_id"] = raw.get("open_menu_id", 0)
         |
         v
Schema (schema.py FireRedGameContext)
  * open_menu_id: int = Field(default=0, ...)
         |
         v
API (tools.py get_context())
  * Returns state.context.model_dump()
  * open_menu_id is always 0 in response
         |
         v
Debug-Only Runtime Check (tools.py _shop_window_active())
  * Uses debug_tools to read sShopMenuWindowId at 0x02039950
  * Only called in shop_buy() and shop_sell()
  * DOES NOT feed back into schema or context
  * One-off check, not persistent state tracking
```

**Key Issue**: The debug check is OUTSIDE the perception pipeline. The AI cannot see shop state through the normal `get_context()` or `get_state()` API.

---

## Finding 7: Why the Bug Manifests

**Confidence: HIGH** — Design consequence.

The user reports: "shop flag set but never unsets — AI thinks we're stuck in shop forever"

This happens because:

1. User enters shop (any mart/shop NPC dialogue)
2. **No detection occurs** — `open_menu_id` stays 0
3. User performs shopping actions via `shop_buy()` / `shop_sell()`
4. These functions **internally check** `_shop_window_active()` for safety
5. User exits shop (presses B or completes transaction)
6. **No context change detected** — `open_menu_id` still 0
7. AI cannot perceive the transition (no state change in `get_context()`)
8. AI may think it's still in a menu context if it saw dialogue start
9. Result: Stuck state from AI's perspective

The bug is not that the flag gets "stuck on" — it's that **there is no flag at all** in the perception layer.

---

## Finding 8: Stale Menu Detection Pattern

**Confidence: HIGH** — Code comment analysis.

Found this warning pattern in socket_reader.lua around menu detection:

```lua
-- Signal 1: sTextPrinters[0].active — most reliable signal
-- WARNING: sYesNoWindowId is STALE — it persists after the player selects.
-- Only trust it when gSpecialVar_Result is still SCR_MENU_UNSET (255).
```

This indicates developers encountered stale heap pointer issues before. The `sYesNoWindowId` persists even after menu closes, so they added a composite check: `window exists AND special_var_result == 255`.

**For shop menus**, no equivalent guard exists. If `sShopMenuWindowId` persists after shop closes (likely), the flag would get stuck.

---

## Finding 9: RAM Addresses Summary

**Confidence: HIGH** — From code annotations.

Shop and menu-related addresses:

| State | Address | Type | Notes |
|-------|---------|------|-------|
| `sShopMenuWindowId` | 0x02039950 | u8 | Shop window ID (0xFF = none) |
| `gBagMenuDisplay` | ??? | heap | Bag menu data (stale-prone) |
| `gPokedexScreenData` | ??? | heap | Pokedex state (stale-prone) |
| `gStorage` | 0x020397B0 | pointer | PC storage root |
| `sYesNoWindowId` | 0x0203ADF3 | u8 | Yes/No window (known STALE) |
| `gSpecialVar_Result` | 0x020370D0 | u16 | Menu result (255=waiting, value=selected) |

---

## Recommendations

### To Fix the Shop Bug (HIGH PRIORITY)

1. **Add shop detection to Lua** — Read `sShopMenuWindowId` at 0x02039950 in `read_context()`
2. **Set open_menu_id** — If shop window is active AND awaiting input, set `open_menu_id = 1` (or shop-specific ID)
3. **Add composite check** — Like Yes/No menus, check both window ID AND a result variable to avoid stale state
4. **Verify it persists correctly** — Test that the flag clears when shop closes
5. **Mirror to reader.lua** — Keep socket_reader.lua and reader.lua in sync

### For Other UI Menus (MEDIUM PRIORITY)

1. **Bag menu** — Identify RAM signal for `gBagMenuDisplay` and add detection
2. **PC menu** — Add detection for Pokemon Storage state
3. **Pokedex** — Add detection for Pokedex screen state
4. **Trainer Card** — Add detection if needed

### To Prevent Future Stale State (LOW PRIORITY)

1. **Document stale pointer patterns** — Add notes to RAM map about which signals persist
2. **Add guards consistently** — Apply the "window + result" pattern to all menus, not just Yes/No
3. **Test transitions** — Automated tests that verify context changes when entering/exiting menus

---

## Key Files

- **Lua Reader**: `/home/austin/projects/pokemon/rom_lab/src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` (lines 945-1029 for `read_context()`)
- **Schema**: `/home/austin/projects/pokemon/rom_lab/src/rom_lab/plugins/pokemon_fire_red/schema.py` (lines 357-428 for `FireRedGameContext`)
- **Normalization**: `/home/austin/projects/pokemon/rom_lab/src/rom_lab/plugins/pokemon_fire_red/plugin.py` (lines 90-258 for `normalize()`)
- **API/Tools**: `/home/austin/projects/pokemon/rom_lab/mcp/src/rom_lab_mcp/tools.py` (lines 1011-1014 for `get_context()`, lines 1500-1648 for shop detection)
- **Bridge**: `/home/austin/projects/pokemon/rom_lab/src/rom_lab/bridge/stream.py` (lines 22-39 for `StateBridge.normalize()`)
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---