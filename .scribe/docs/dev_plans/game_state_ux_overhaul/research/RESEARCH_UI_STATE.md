---
id: game_state_ux_overhaul-research-ui-state
title: "\U0001F52C Research Ui State \u2014 game_state_ux_overhaul"
doc_type: RESEARCH_UI_STATE
doc_name: RESEARCH_UI_STATE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 15:24:41 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Ui State — game_state_ux_overhaul
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-22 15:23:36 UTC

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
# Findings: BizHawk Web UI Game State Tab & Input Controls

## 1. Game State Tab Current Implementation

### Location & Rendering
- **Template**: `.council/web/pages/bizhawk.html.j2` (lines 248-302)
- **Rendering Module**: `.council/web/static/js/game-state.js` (632 lines)
- **CSS**: `.council/web/static/css/bizhawk.css` (7591 lines, game state classes start ~line 1315)
- **Active Tab**: Panel ID `panel-gamestate` is set to `active` by default

### Current Data Display (Confidence: HIGH)
The game state tab renders the following sections:

1. **Quick Actions Bar** (lines 254-259 in template)
   - Load Last (savestate)
   - Save Now
   - Restart (with warn styling)
   - Status indicator

2. **Game Mode Indicator** (lines 262-264)
   - Shows: `OVERWORLD`, `BATTLE`, `DIALOGUE`, `MENU`
   - Detection logic: `_detectMode()` in game-state.js (line 127)
   - Reads from: `context.in_battle`, `context.in_dialogue`, `context.in_menu`, `battle.active`

3. **Location Section** (lines 267-277)
   - Map name
   - Coordinates (X, Y)
   - Facing direction (North/South/East/West)
   - Map metadata (indoors flag, etc.)

4. **Trainer Section** (lines 280-285)
   - Player name + gender badge
   - Trainer ID / Secret ID
   - Rival name
   - Money (formatted with commas)
   - Play time (hours + minutes)
   - Pokedex count (owned / seen)
   - Badge display (8 badges, earned/unearned)

5. **Party Section** (lines 288-293)
   - Up to 6 Pokemon cards, each showing:
     - Species name / Nickname
     - Level
     - Shiny indicator (✦)
     - Gender (♂/♀/○)
     - Type badges (colored)
     - Nature name
     - Ability name
     - Status condition
     - HP bar (green/yellow/red based on %age)
     - HP text (current/max)
     - Move chips (PP visible)
     - Expandable detail panel (IV/nature/gender/moves/item)

6. **Battle Section** (lines 296-301, hidden when not in battle)
   - Enemy Pokemon card (same detail as party card)
   - Active player Pokemon card
   - Move effectiveness matchups (damage multipliers)

### Data Flow (Confidence: HIGH)
```
API: /api/romlab/state/enriched
  ↓ (polled every 2 seconds)
game-state.js._poll()
  ↓
_render(state) calls:
  - _renderMode()        (battle/dialogue/menu/overworld)
  - _renderLocation()    (map, coords, facing)
  - _renderPlayer()      (trainer info, badges)
  - _renderParty()       (6 party slots)
  - _renderBattle()      (enemy, active, matchups)
  ↓
HTML updated via .innerHTML = '...'
```

### Polling & Freshness
- **Poll Interval**: 2000ms (2 seconds) - Confidence: HIGH
- **Abort Timeout**: 3000ms per fetch - Confidence: HIGH
- **Freshness Indicator**: Panel header shows `Live` / `Paused` / `Offline` / `Error XXX`
- **Update Strategy**: Signature-based diff (only re-renders sections that changed) - prevents flashing
- **Visibility Gate**: Polling stops when tab is not active (`setVisible(false)`) - Confidence: HIGH

**Gap Found**: Endpoint `/api/romlab/state/enriched` is hardcoded in JS but DOES NOT EXIST in codebase - Confidence: CRITICAL

## 2. Input Controls (Virtual D-Pad & Buttons)

### Location & Structure
- **Template HTML**: `.council/web/pages/bizhawk.html.j2` (lines 139-172)
- **JS Binding**: `.council/web/static/js/bizhawk.js` (class BizHawkClient)
- **CSS**: `.council/web/static/css/bizhawk.css` (vcontrols classes)

### Button Types (Confidence: HIGH)
1. **D-Pad** (lines 141-155): Up, Down, Left, Right
2. **Action Buttons** (lines 157-160): A, B buttons
3. **Meta Buttons** (lines 162-164): Select, Start

All buttons use `data-button="ButtonName"` attribute.

### Event Handling (Confidence: HIGH)
- **Mouse**: mousedown → keydown, mouseup → keyup, mouseleave → keyup cleanup
- **Touch**: touchstart → keydown, touchend → keyup, touchcancel → keyup cleanup
- **D-Pad Swipe**: Unified pointer-based swipe handler (lines 2106-2151 in bizhawk.js)
  - Calculates angle from center point
  - 4-way direction mapping using atan2
  - Dead zone: 10px minimum distance
  - Smooth direction transitions (release old, press new)

### Current Behavior (Confidence: MEDIUM - NOT YET TESTED)
- **Hold Support**: Buttons use `mousedown/touchstart` → send keydown. No auto-repeat, but holding mouse/touch = continuous signal
- **Joystick Mode**: D-Pad has swipe/drag support (NOT traditional gamepad/joystick input)
- **Button Repeat**: Each hold sends ONE keydown + ONE keyup. NO repeating presses while held
- **Virtual Gamepad**: NO - D-Pad swipe is not true gamepad analog, just angle-based 4-way
- **Repeat Speed**: N/A - no auto-repeat implemented

### Critical Gap: Hold-to-Spam & Joystick (Confidence: HIGH)
- User request: "Hold buttons to spam A" - NOT IMPLEMENTED
- Current: Single press per hold
- User request: "Joystick toggle instead of d-pad" - NO JOYSTICK API INTEGRATION
- Current: D-Pad swipe only

## 3. Live Telemetry (Data Freshness)

### Current Status (Confidence: HIGH)
- **Poll Timer**: 2000ms interval
- **Fresh Data**: Guaranteed ≤2000ms old + network latency
- **Stale Data Conditions**: 
  - Network error → shows "Offline"
  - Timeout → shows "Offline"  
  - Tab hidden → polling stops (paused state)

### Update Mechanism (Confidence: HIGH)
- Signature-based dirty checking prevents DOM thrashing
- Section-level updates preserve scroll position and expanded state
- No full-panel reload animations

### Missing: "Actually Live" (Confidence: MEDIUM)
- Current 2-second poll might feel "delayed" for battle data
- No WebSocket push model (always pull-based)
- No frame-by-frame BizHawk integration (video stream ≠ state stream)

## 4. CSS/Layout Architecture

### CSS Pattern (Confidence: HIGH)
- **Methodology**: BEM (Block-Element-Modifier)
- **Prefix**: `.gamestate__` for all game state components
- **Color Scheme**: Dark blue/cyan (`#0d1117` bg, `#c8d6e5` text, `#00d4ff` accents)
- **Font**: `'SF Mono', 'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace`

### Layout System (Confidence: HIGH)
- **Sidebar Panel**: Flex column, scrollable
- **Quick Actions**: Flex row
- **Sections**: Block with dividers (`border-bottom: 1px solid #162230`)
- **Party List**: Flex column
- **Pokemon Card**: Collapsed/expanded toggles via `gamestate__pokemon--expanded` class

### Responsive Design (Confidence: MEDIUM)
- Sidebar is collapsible on mobile
- Virtual controls appear on smaller screens
- "Overlay mode" for controls on mobile (appears above sidebar)

## 5. API Endpoint Status

### `/api/romlab/state/enriched` Endpoint (Confidence: CRITICAL GAP)
- **Used by**: game-state.js, line 11
- **Expected Return**: `{ context, map, player, party, battle }`
- **Current Status**: DOES NOT EXIST in codebase
- **Existing Related**: `/api/romlab/raw-state` exists (raw Lua state)
- **Implication**: Game state panel is non-functional (network errors every 2 seconds)

### Raw State Flow (Confidence: MEDIUM)
- `/api/romlab/raw-state` returns unvalidated state
- No enrichment layer (no battle intelligence, no move damage calcs)
- No field lookups (species names, move names, ability names)

## 6. Data Sources & Availability

### Available Data (from game-state.js rendering, Confidence: HIGH)
✓ Mode (battle/dialogue/menu/overworld)
✓ Map name & coordinates
✓ Facing direction
✓ Trainer name, gender
✓ Trainer ID / Secret ID
✓ Money
✓ Play time
✓ Pokedex count
✓ Badges earned (count)
✓ Party Pokemon (species, level, HP, moves)
✓ Battle enemy Pokemon
✓ Move effectiveness vs active enemy
✓ Nature, ability, status, type, gender, shiny status

### Missing Data (from API gap, Confidence: MEDIUM)
- IVs (individual values)
- EVs (effort values)
- Hidden power type/damage
- Base stats breakdown
- Move damage calculations
- Ability descriptions
- Item information
- Battle move accuracy/priority
- Enemy Pokemon full stats (IVs, EVs, moveset)

## Confidence Summary

| Finding | Confidence | Notes |
|---------|-----------|-------|
| Game State Tab HTML structure | HIGH | Scanned template directly |
| Rendering logic (game-state.js) | HIGH | Code inspected, clear flow |
| Polling interval (2s) | HIGH | Hardcoded in JS |
| Input button events (mousedown/touchstart) | HIGH | Event handlers visible |
| D-Pad swipe mechanism | HIGH | Angle-based 4-way logic clear |
| Missing `/api/romlab/state/enriched` | CRITICAL | Hardcoded in JS, not in Python |
| No hold-to-spam implementation | HIGH | Button code uses single press only |
| No true joystick integration | HIGH | Only d-pad swipe exists |
| Live telemetry feels "stale" | MEDIUM | 2s poll + no WebSocket |
| CSS uses BEM pattern | HIGH | Class names inspected |
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