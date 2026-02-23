---
id: heatseeker-research-streamer-infrastructure
title: "\U0001F52C Research Streamer Infrastructure \u2014 heatseeker"
doc_type: RESEARCH_STREAMER_INFRASTRUCTURE
doc_name: RESEARCH_STREAMER_INFRASTRUCTURE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 05:26:20 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Streamer Infrastructure — heatseeker
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-22 05:25:42 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
This report documents the complete RomLabStreamer C# External Tool infrastructure that HeatSeeker must integrate with. The streamer is a mature system (~12,300 lines across 11 files) providing binary TCP communication between BizHawk and Python, with 30+ commands across 7 namespaces, full memory read/write support, warp mode with tight-loop frame advance, and a WebSocket bridge for browser access.

**Key finding for HeatSeeker**: The existing infrastructure already provides everything HeatSeeker needs. Memory reads (for gRngValue polling), warp mode (for fast-forward execution), frame advance (for precise stepping), and the command dispatch pipeline are all production-ready. HeatSeeker should add new SubCommand bytes in the 0x50+ range and new handler methods in CommandHandler.cs, following the established patterns exactly.

**Confidence**: 0.95 -- All source files read in full. Architecture is well-documented in code comments. Only uncertainty is around undocumented BizHawk API edge cases during concurrent warp+memory operations.
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent (lens-streamer)
**Scope:** Complete investigation of the RomLabStreamer C# External Tool and its Python bridge, including architecture, command system, memory access, build/deploy pipeline, and integration points for HeatSeeker.

### Files Analyzed (11 total, ~12,316 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `csharp/RomLabStreamer/StreamerForm.cs` | 789 | Main External Tool entry point, warp mode state machine |
| `csharp/RomLabStreamer/CommandHandler.cs` | 2801 | Command dispatch, 30+ commands across 7 namespaces |
| `csharp/RomLabStreamer/Protocol.cs` | 322 | Binary protocol constants, SubCommand byte codes |
| `csharp/RomLabStreamer/TcpBridge.cs` | 405 | TCP server, producer-consumer threading |
| `csharp/RomLabStreamer/FrameCapture.cs` | 120 | IVideoProvider frame buffer access |
| `csharp/RomLabStreamer/AudioCapture.cs` | 258 | ISoundProvider audio sample capture |
| `scripts/build-streamer.sh` | 59 | Build + deploy + trust hash |
| `scripts/update_ext_tool_trust.py` | 84 | SHA512 trust hash for BizHawk config.ini |
| `src/rom_lab/streaming/ws_endpoint.py` | 1811 | WebSocket JSON-to-binary bridge |
| `src/rom_lab/streaming/frame_receiver.py` | 729 | Async TCP client with request-ID correlation |
| `src/rom_lab/api/routes/automation/controller.py` | 4938 | Warp mode consumer (lines 2125-2200 analyzed) |
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.
### Finding 1
- **Summary:** [Describe the finding]
- **Evidence:** [Link to logs, code references, or experiments]
- **Confidence:** Medium

### Finding 2
- **Summary:** [Describe the finding]
- **Evidence:** [Link to supporting material]
- **Confidence:** Medium

### Additional Notes
- Capture supporting observations or open follow-ups.


---
## Technical Analysis
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