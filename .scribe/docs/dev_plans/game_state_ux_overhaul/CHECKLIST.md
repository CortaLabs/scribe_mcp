---
id: game_state_ux_overhaul-checklist
title: "\u2705 Acceptance Checklist \u2014 game_state_ux_overhaul"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 16:27:21 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — game_state_ux_overhaul
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 15:16:51 UTC

> Acceptance checklist for game_state_ux_overhaul.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Documentation Hygiene
- [x] Architecture guide updated (proof: ARCHITECTURE_GUIDE.md -- detailed_design, open_questions corrected with verified code refs)
- [x] Phase plan current (proof: PHASE_PLAN.md -- 7 task packages in 3 waves, proxy/IV corrections applied)
<!-- ID: phase_0 -->
## Wave 1: Perception Fix (Task 1.1 -- Lua Shop Detection)
- [x] MENU.shop_window_id constant added to socket_reader.lua (proof: grep 0x02039950 → socket_reader.lua:263)
- [x] Composite guard reads shop_wid AND checks script_mode (proof: socket_reader.lua:1012-1013 — `(shop_wid ~= 0xFF and shop_wid ~= 0) and (script_mode ~= 0)`)
- [x] open_menu_id = 1 when in_shop is true (proof: socket_reader.lua:1016 — `in_shop and 1 or 0`)
- [x] EXACT same changes mirrored to reader.lua (proof: reader.lua:252,1001-1005 identical logic)
- [x] `luac -p socket_reader.lua` passes (proof: `luac -p socket_reader.lua && echo OK` → "socket_reader: OK")
- [x] `luac -p reader.lua` passes (proof: `luac -p reader.lua && echo OK` → "reader: OK")
- [x] Schema field open_menu_id already exists at schema.py:415 (proof: no schema changes needed — field pre-existing)
<!-- ID: final_verification -->
- [ ] All checklist items checked with proofs attached.  
- [ ] Stakeholder sign-off recorded (name + date).  
- [ ] Retro completed and lessons learned documented.


---