---
id: streamer_optimization-checklist
title: "\u2705 Acceptance Checklist \u2014 streamer_optimization"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 03:58:19 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — streamer_optimization
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 03:19:07 UTC

> Acceptance checklist for streamer_optimization.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Documentation Hygiene
- [ ] ARCHITECTURE_GUIDE.md complete with all 10 sections (proof: file exists, all sections populated)
- [ ] PHASE_PLAN.md complete with 3 phases, 7 task packages (proof: file exists, all phases populated)
- [ ] CHECKLIST.md complete with acceptance criteria (proof: this file)
- [ ] All 3 research reports read and referenced (proof: references_appendix in ARCHITECTURE_GUIDE)
- [ ] Research discrepancies documented (proof: discrepancy log in ARCHITECTURE_GUIDE)
<!-- ID: phase_0 -->
## Phase 1 — C# Warp Optimization

### Task 1.1: Enhanced SetWarpModeActive
- [x] `EnableRewind(false)` added to warp entry (proof: StreamerForm.cs SetWarpModeActive(true) block)
- [x] `FrameSkip(9)` added to warp entry (proof: StreamerForm.cs SetWarpModeActive(true) block)
- [x] Save/restore fields added for both settings (proof: _warpSavedRewindEnabled, _warpSavedFrameSkip fields at line 67-68)
- [x] Cleanup handler updated with restoration calls (proof: StopStreaming() now calls EnableRewind + FrameSkip)
- [x] `scripts/build-streamer.sh` compiles without error (proof: "Build succeeded. 0 Warning(s) 0 Error(s)")
- [ ] DLL loads in BizHawk without crash (proof: manual test — Phase 3)

### Task 1.2: CancelAdvance Command
- [x] `CancelAdvance = 0x0B` added to Protocol.cs SubCommand enum (proof: Protocol.cs line 43)
- [x] `DoCancelAdvance` handler in CommandHandler.cs (proof: DoCancelAdvance method + dispatch switch entry)
- [x] Cancel callback wired in StreamerForm.cs AdvanceFrames (proof: SetCancelAdvanceCallback + CancelAdvanceFrames method)
- [ ] Cancel during active warp terminates early (proof: manual WebSocket test — Phase 3)
- [ ] Cancel when no warp active returns no-op (proof: manual WebSocket test — Phase 3)

### Task 1.3: Warp Telemetry
- [x] `approx_framerate` field in warp mode response (proof: DoWarpMode returns [Enabled:1][ApproxFramerate:4 LE])
- [x] `approx_framerate` field in advance_frames response (proof: UpdateAfter completion returns [FramesAdvanced:4 LE][ApproxFramerate:4 LE])
- [ ] Value is positive integer during emulation (proof: observed values — Phase 3)

---
<!-- ID: final_verification -->
## Final Verification

### Regression Gates
- [ ] All existing tests pass: `pytest -q tests/test_ws_endpoint_commands.py tests/test_warp_mode.py tests/test_automation_routes.py` (proof: test output)
- [ ] No new test failures introduced (proof: CI or local test output)
- [ ] C# build succeeds: `scripts/build-streamer.sh` (proof: build output)

### Performance Target
- [ ] Warp frame throughput > 3000fps (proof: `approx_framerate` in warp responses)
- [ ] No measurable performance regression in non-warp operation (proof: normal gameplay observation)

### State Safety
- [ ] BizHawk sound restored after warp (proof: manual observation)
- [ ] BizHawk video streaming restored after warp (proof: WebSocket frame delivery resumes)
- [ ] BizHawk rewind restored after warp (proof: manual observation)
- [ ] BizHawk frame skip restored after warp (proof: manual observation)
- [ ] InvisibleEmulation(false) confirmed after warp (proof: screen visible in BizHawk)
- [ ] SpeedMode(100) confirmed after warp (proof: normal game speed)

### Architecture Compliance
- [ ] No new files created (proof: git diff --stat shows only modified files)
- [ ] All changes are to files listed in ARCHITECTURE_GUIDE directory_structure section
- [ ] No Lua files modified (proof: git diff shows no lua changes)
- [ ] Binary protocol backward compatible (existing commands unchanged, new 0x0B is additive)

### Sign-off
- [ ] Architect sign-off: ArchitectAgent (date: ___)
- [ ] Reviewer sign-off: Arbiter (date: ___)
- [ ] Orchestrator sign-off: nexus (date: ___)
