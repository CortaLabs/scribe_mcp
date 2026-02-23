---
id: automation_rng_modular_2026_02_21-seed-match-architecture-guide
title: 'Architecture Guide: Seed-Match Tick-Perfect Execution'
doc_type: custom
doc_name: SEED_MATCH_ARCHITECTURE_GUIDE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 07:03:26 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Architecture Guide: Seed-Match Tick-Perfect Execution

**Sub-plan of:** automation_rng_modular_2026_02_21
**Author:** ArchitectAgent
**Status:** Draft
**Last Updated:** 2026-02-21

> Replaces frame-counting with direct gRngValue seed matching for 100% tick-perfect starter RNG manipulation.

---

<!-- ID: problem_statement -->
## 1. Problem Statement\n\n**Context:** The starter reset bot achieved 0/53 hits using frame-counting to target specific RNG states. The mathematical model is correct (PokeFinder parity confirmed), but execution fails because:\n\n1. **NPC RNG Chaos:** Oak's lab has 3 NPCs (2x LookAround, 1x WanderUpAndDown), each consuming 2 Random() calls per movement cycle at unpredictable intervals. This creates a chaotic advance count that frame-counting cannot predict.\n2. **Python A2/A3 Jitter:** The YES/NO dialogue stages (A2, A3) are Python-orchestrated with +/-3-5 frame jitter from polling intervals (POLL_STAGE_INTERVAL_SECONDS = 0.05s). This shifts the A4 hold start point non-deterministically.\n3. **Delay Cap Mismatch:** The max hold cap (LEARNER_MAX_PRE_A4_HOLD_FRAMES = 7200) was orders of magnitude below required delays (23K+ frames observed).\n4. **Calibration Thrashing:** The EWMA drift tracker cannot separate error sources (seed drift vs execution jitter vs NPC chaos), causing oscillation instead of convergence.\n\n**Goal:** Replace frame-counting with direct gRngValue seed matching, achieving 100% tick-perfect execution where every action lands on exactly the right frame with zero delays, zero jitter, and zero guesswork.\n\n**Key Insight:** Since Lua already reads gRngValue (0x03005000) every frame via `_current_seed()`, we can match on the actual RNG state rather than trying to predict when a specific state will occur. NPC chaos becomes irrelevant -- we wait for the right seed regardless of how many frames it takes.\n\n**Research Basis:**\n- Per RESEARCH_CONTROLLER_RNG_FLOW.md: Gap #1 (A2/A3 jitter) is the critical barrier\n- Per RESEARCH_DECOMP_STARTER_RNG_CHAIN.md: Exactly 4 Random() calls for starter generation, NPC advances are chaotic\n- Per RESEARCH_BIZHAWK_FRAME_CONTROL.md: Lua has single-frame precision, recommends rng_target_seed_wait stage\n- Per RESEARCH_POKEFINDER_FRAME_HITTING.md: PokeFinder \"frame\" = raw LCRNG advances, our oracle has parity"
</invoke>
<!-- ID: system_overview -->
## 2. System Overview

PLACEHOLDER

---

<!-- ID: target_seed_computation -->
## 3. Target Seed Computation

PLACEHOLDER

---

<!-- ID: lua_seed_monitor -->
## 4. Lua Seed Monitor Design

PLACEHOLDER

---

<!-- ID: ipc_protocol -->
## 5. IPC Protocol Additions

PLACEHOLDER

---

<!-- ID: controller_integration -->
## 6. Controller Integration

PLACEHOLDER

---

<!-- ID: planner_upgrades -->
## 7. Planner Upgrades

PLACEHOLDER

---

<!-- ID: verification_pipeline -->
## 8. Verification Pipeline

PLACEHOLDER

---

<!-- ID: obsolescence_map -->
## 9. What to Keep vs Remove

PLACEHOLDER

---

<!-- ID: data_flow -->
## 10. End-to-End Data Flow

PLACEHOLDER
