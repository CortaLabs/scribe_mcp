
# 🐞 Bug Log — scribe_binding_reliability_repair_20260927
**Maintained By:** Scribe
**Timezone:** UTC

> Track bug discoveries, investigations, and resolutions for Scribe MCP. Use `log_type="bugs"` (or `--log bugs`).

---



## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: scribe_binding_reliability_repair_20260927] Message text | severity=<severity>; component=<component>; status=<status>; [additional metadata]
```

**Required Metadata Fields:**
- `severity`: critical/high/medium/low/minimal
- `component`: Component or module where bug exists
- `status`: open/investigating/in_progress/fixed/verified/closed/wont_fix

**Optional Metadata Fields:**
- `bug_id`: Ticket number or identifier
- `environment`: production/staging/development/local
- `reproduction_steps`: Brief summary of repro steps
- `test_case`: Test case ID that should cover this bug
- `fix_commit`: Commit hash for the fix
- `reviewer`: Code reviewer
- `confidence`: Confidence in root cause analysis (0-1)
- `impact`: Business impact (critical/high/medium/low/minimal)
- `customer_impacted`: true/false
- `regression`: true/false
- `estimated_effort`: XS/S/M/L/XL
- `related_issues`: Comma-separated list of linked tickets

---

## Severity Classification Guide
- **Critical**: System down, data loss, security vulnerability, or production outage.
- **High**: Major feature broken or significant customer impact; workaround limited.
- **Medium**: Feature partially broken; minor impact; workaround available.
- **Low**: Minor UI issues, edge cases, documentation errors.
- **Minimal**: Cosmetic issues, typos, non-functional improvements.

---

## Component Categories
- **Backend**: Server-side code, MCP tool paths, APIs, databases.
- **Frontend**: UI and client-side logic.
- **Infrastructure**: Deployment, CI/CD, monitoring, configuration, runtime wiring.
- **Tests**: Test suites or infrastructure.
- **Documentation**: READMEs, API docs, guides.
- **Performance**: Latency/throughput regressions.
- **Security**: Security-related bugs and vulnerabilities.
- **Data**: Migration, seeding, registry, or validation errors.

---

## Status Flow Guide
1. **open** → Initial discovery and logging
2. **investigating** → Root cause analysis
3. **in_progress** → Fix under development
4. **fixed** → Fix implemented, ready for testing
5. **verified** → Fix tested and confirmed
6. **closed** → Issue resolved and documented
7. **wont_fix** → Issue accepted as-is (include justification)

---

## Entries will populate below
[🐞] [2026-09-27 10:45:06 UTC] [Agent: witness_sbr_bind_resolve_1_delta] [Project: scribe_binding_reliability_repair_20260927] Council content-drift readback uses mtime attribution despite identical current receipt digests. | component=council_mcp.work_item.content_drift; evidence=behavioral and truth receipts both revision 5de705eb... and owned_content_digest 5f535ada..., while content_drift reports both stale via mtime_attribution; expected=Same owned-content digest and revision should not be reported as artifact drift.; reasoning={"how": "Captured current show_work_item readback after truth review.", "what": "Durable cross-system defect record only; no Council source fix is in this package.", "why": "False drift can invalidate legitimate current-revision gates."}; severity=high; status=open; work_item_id=6058f4c6-b437-4304-8dc4-ca7f99aaa194; priority=high; log_type=bugs; content_type=log
[🐞] [2026-09-28 07:34:41 UTC] [Agent: witness_sbr_schema_2_review_1] [Project: scribe_binding_reliability_repair_20260927] WITNESS FINDING — SBR-SCHEMA.2 implementation diverges from sovereign plan. PHASE_PLAN.md:1010 requires existing SQLite files to reopen without rebuild and forbids introducing a table-copy migration. Current schema.py:613-651 defines RELIABILITY_REBUILD_STATEMENTS that copy rows into replacement tables, drop originals, and rename replacements for both session_projects and background_receipts; ensure_reliability_schema executes that sequence unconditionally at line 937, including every reopen. The unchanged f96e7c46 task revision contains no plan amendment. This is a gating truth FAIL even though recovery probes demonstrate row preservation. | component=sqlite schema upgrade; contract_revision=f96e7c46312370438388453e23d90cbd3eff6013275490f47437be3f5332c521; reasoning={"how": "Compared PHASE_PLAN.md lines 1003-1011 against current schema.py lines 613-651 and 936-937 after verifying current hashes/source bytes.", "what": "The implementation uses exactly the rebuild/table-copy mechanism the active plan forbids.", "why": "Within the active package, plan intent and explicit implementation constraints are sovereign."}; severity=high; status=open; work_item_id=769f4ed9-3c46-4b50-84a5-002d2eda02f7; priority=critical; category=bug; tags=["SBR-SCHEMA.2", "witness", "plan-divergence", "truth-fail"]; log_type=bugs; content_type=log
[🐞] [2026-09-28 07:35:09 UTC] [Agent: witness_sbr_schema_2_review_1] [Project: scribe_binding_reliability_repair_20260927] Scribe manage_docs rejected the mandated verification doc_type as unregistered and reported only custom/spec/agent_card/bug/research/review/security. Following the live tool contract, the Witness report will use doc_type=review with stage=truth_check and explicit verdict metadata; no filesystem workaround will be used. | component=manage_docs; reasoning={"how": "Recorded the typed tool failure and selected the nearest registered managed-doc type, review, preserving truth_check stage and verdict metadata.", "what": "The live Scribe registry does not expose the verification doc type required by the role card.", "why": "The Witness role requires a persisted managed verification report."}; severity=medium; status=open; priority=medium; category=bug; tags=["scribe", "verification-report", "doc-type-drift"]; log_type=bugs; content_type=log
[🐞] [2026-09-28 09:18:32 UTC] [Agent: seshat] [Project: scribe_binding_reliability_repair_20260927] Verified Hoshin/Fudo P0 binding-drop: initial append lost repo scope; set_project recovered it but took 4.1s and emitted full inventory; retry append succeeded but outer call took 14.7s, internal total 584ms above the 500ms tripwire, with ~1.9KB structured response. Repeat set_project remains recovery evidence only. | component=session_binding_and_hot_path; fail_call=aitrace:v1:codex:9502ab422f872685bfa91dbda3992537; fail_result=aitrace:v1:codex:cbde89cc804e4418fda17fe16b2b1a57; retry_result=aitrace:v1:codex:7bef9b8974d5dd9bc45a7a3f7eb78f6e; set_project_result=aitrace:v1:codex:d8f588e626d7c90f69f18d629fdb6d1e; severity=critical; status=open; priority=critical; category=bug; log_type=bugs; content_type=log
[🐞] [2026-09-28 09:40:54 UTC] [Agent: seshat] [Project: scribe_binding_reliability_repair_20260927] BUG-2026-09-28-0002 recurred in the same Hoshin/Fudo session after a successful write while HUD still showed bound. Append failed repo-scope-unresolved; identical set_project restored it; retry succeeded. This proves HUD/executable-binding divergence and repeated same-session loss. | component=session_binding; fail_call=aitrace:v1:codex:cee57887db4e506fa68f9ebdfe38512e; fail_result=aitrace:v1:codex:14f3ebe02dd2fcb886167c82d12e09aa; recovery_result=aitrace:v1:codex:5c3f28a33813582929d4a143a7615a75; severity=critical; status=open; success_result=aitrace:v1:codex:393717e21d62872fff8ac57e191844d8; priority=critical; category=bug; log_type=bugs; content_type=log
[🐞] [2026-09-28 10:05:44 UTC] [Agent: seshat] [Project: scribe_binding_reliability_repair_20260927] BUG-2026-09-28-0002 third same-session recurrence generalized the loss beyond append_entry: Council work show succeeded while parallel manage_docs failed repo-scope-unresolved with HUD bound. Identical set_project restored manage_docs. Recovery was 3.9s inventory; retry response was about 4KB. | component=session_binding_and_response_projection; failure_result=aitrace:v1:codex:7dda6ce7d1ba3d72f96651f8ec77cec3; parallel_call=aitrace:v1:codex:c26c14f7774acb7041d9a04213f51fae; recovery_result=aitrace:v1:codex:6d2b38ceb4836c177a5084c501365157; severity=critical; status=open; success_result=aitrace:v1:codex:0e0a5e1668503ac58e7b0d9647473e3a; priority=critical; category=bug; log_type=bugs; content_type=log
