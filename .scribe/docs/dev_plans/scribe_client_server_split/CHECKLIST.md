---
id: scribe_client_server_split-checklist
title: "\u2705 Acceptance Checklist \u2014 scribe_client_server_split"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 02:44:22 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — scribe_client_server_split
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 01:59:42 UTC

> Acceptance checklist for scribe_client_server_split.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [x] Architecture guide updated (proof: ARCHITECTURE_GUIDE.md, 31KB) <!-- ID: doc_arch -->
- [x] Phase plan current (proof: PHASE_PLAN.md, 18KB) <!-- ID: doc_phase -->
- [x] Research documents complete (proof: 5 docs in research/, 112KB total) <!-- ID: doc_research -->
- [ ] All task packages have clear scope, verification, and out-of-scope <!-- ID: doc_task_packages -->
<!-- ID: phase_0 -->
## Phase 1 — Interface Cleanup
<!-- ID: phase_1_checklist -->
- [ ] 12 extended methods added to StorageBackend base class <!-- ID: p1_method_stubs -->
  - **Acceptance**: `from scribe_mcp.storage.base import StorageBackend` imports without error, all methods exist
  - **Verification**: `python -c "from scribe_mcp.storage.base import StorageBackend, RemoteUnavailableError"` succeeds
- [ ] RemoteUnavailableError exception added to base.py <!-- ID: p1_exception -->
  - **Acceptance**: Exception class importable
  - **Verification**: Import test passes
- [ ] Existing tests pass with no regression <!-- ID: p1_regression -->
  - **Acceptance**: `pytest tests/ -x -q` exits 0
  - **Verification**: Full test suite run

## Phase 2 — Mode Detection
<!-- ID: phase_2_checklist -->
- [ ] mode_detection.py created with OperatingMode enum <!-- ID: p2_mode_enum -->
  - **Acceptance**: `from scribe_mcp.config.mode_detection import OperatingMode` works
  - **Verification**: Import test
- [ ] detect_operating_mode() function works for all 3 modes <!-- ID: p2_detect -->
  - **Acceptance**: Returns correct mode for each scenario
  - **Verification**: `pytest tests/test_mode_detection.py -v`
- [ ] Settings has 4 new fields (remote_server_url, mode, timeout, fallback) <!-- ID: p2_settings -->
  - **Acceptance**: Settings loads with defaults when env vars unset
  - **Verification**: `pytest tests/test_mode_detection.py`
- [ ] Health probe connects to /health and validates service name <!-- ID: p2_probe -->
  - **Acceptance**: Returns True for valid scribe-mcp health response
  - **Verification**: Mock test

## Phase 3 — Server REST API
<!-- ID: phase_3_checklist -->
- [ ] /api/v1/backend/{operation} endpoint added to server_sse.py <!-- ID: p3_single_op -->
  - **Acceptance**: POST with valid operation returns {"result": ...}
  - **Verification**: `pytest tests/test_server_api.py::test_single_operation`
- [ ] /api/v1/batch endpoint added <!-- ID: p3_batch -->
  - **Acceptance**: POST with multiple operations returns all results
  - **Verification**: `pytest tests/test_server_api.py::test_batch_operations`
- [ ] _serialize() handles ProjectRecord, datetime, dict types <!-- ID: p3_serialize -->
  - **Acceptance**: Round-trip serialization preserves all fields
  - **Verification**: Unit test
- [ ] Invalid operations return 400, server errors return 500 <!-- ID: p3_errors -->
  - **Acceptance**: Error responses have {"error": "..."} format
  - **Verification**: `pytest tests/test_server_api.py::test_error_handling`

## Phase 4 — RemoteStorageBackend
<!-- ID: phase_4_checklist -->
- [ ] RemoteStorageBackend class created in storage/remote.py <!-- ID: p4_class -->
  - **Acceptance**: Extends StorageBackend, implements all abstract methods
  - **Verification**: `from scribe_mcp.storage.remote import RemoteStorageBackend`
- [ ] Session methods work locally in-memory <!-- ID: p4_sessions -->
  - **Acceptance**: get_session_by_transport, upsert_session, etc. work without network
  - **Verification**: `pytest tests/test_remote_backend.py -k session`
- [ ] Project methods proxy to remote via HTTP <!-- ID: p4_project_proxy -->
  - **Acceptance**: fetch_project, upsert_project call /api/v1/backend/*
  - **Verification**: `pytest tests/test_remote_backend.py -k project` (with respx mocks)
- [ ] Entry methods proxy to remote via HTTP <!-- ID: p4_entry_proxy -->
  - **Acceptance**: insert_entry, fetch_recent_entries call /api/v1/backend/*
  - **Verification**: `pytest tests/test_remote_backend.py -k entry`
- [ ] Batch endpoint used for multi-operation calls <!-- ID: p4_batch -->
  - **Acceptance**: execute_batch sends operations to /api/v1/batch
  - **Verification**: `pytest tests/test_remote_backend.py -k batch`
- [ ] Error handling: RemoteUnavailableError on connection failure <!-- ID: p4_errors -->
  - **Acceptance**: Connection errors raise RemoteUnavailableError
  - **Verification**: `pytest tests/test_remote_backend.py -k error`

## Phase 5 — Integration & Testing
<!-- ID: phase_5_checklist -->
- [ ] Storage factory returns RemoteStorageBackend for CLIENT mode <!-- ID: p5_factory -->
  - **Acceptance**: `create_storage_backend(OperatingMode.CLIENT)` returns RemoteStorageBackend
  - **Verification**: Unit test
- [ ] server.py _startup() detects mode and creates correct backend <!-- ID: p5_startup -->
  - **Acceptance**: Log shows "Operating mode: client" when SCRIBE_REMOTE_URL set
  - **Verification**: Integration test
- [ ] All 21 tools work in client mode <!-- ID: p5_tools -->
  - **Acceptance**: set_project, append_entry, read_file, search all work
  - **Verification**: Manual test with .env configured for client mode
- [ ] set_project latency < 500ms in client mode <!-- ID: p5_latency -->
  - **Acceptance**: Measured latency with `time` or perf_counter
  - **Verification**: Benchmark test over Tailscale
- [ ] Backward compatibility: server mode unchanged <!-- ID: p5_backward -->
  - **Acceptance**: `pytest tests/ -x -q` passes with no new env vars set
  - **Verification**: Full test suite
- [ ] Fallback to SQLite works when remote unreachable <!-- ID: p5_fallback -->
  - **Acceptance**: Scribe starts in standalone mode with warning when remote down
  - **Verification**: Start with SCRIBE_REMOTE_URL pointing to unreachable host
<!-- ID: final_verification -->
- [ ] All checklist items checked with proofs attached <!-- ID: final_all_checked -->
- [ ] Full test suite passes: `pytest tests/ -x -q` <!-- ID: final_tests -->
- [ ] set_project benchmark: < 500ms over Tailscale <!-- ID: final_benchmark -->
- [ ] All 3 modes work correctly (server, client, standalone) <!-- ID: final_modes -->
- [ ] No regression in existing functionality <!-- ID: final_regression -->
- [ ] Review Agent sign-off with >= 93% grade <!-- ID: final_review -->
- [ ] Retro completed and lessons learned in PHASE_PLAN.md <!-- ID: final_retro -->

Generated by ArchitectAgent-ClientServerSplit, 2026-02-17.
