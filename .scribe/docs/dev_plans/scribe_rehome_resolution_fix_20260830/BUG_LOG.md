
# 🐞 Bug Log — scribe_rehome_resolution_fix_20260830
**Maintained By:** Scribe
**Timezone:** UTC

> Track bug discoveries, investigations, and resolutions for Scribe MCP. Use `log_type="bugs"` (or `--log bugs`).

---



## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: scribe_rehome_resolution_fix_20260830] Message text | severity=<severity>; component=<component>; status=<status>; [additional metadata]
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
[🐞] [2026-08-30 18:42:09 UTC] [Agent: seshat] [Project: scribe_rehome_resolution_fix_20260830] REVIEWER CUSTODY DEFECT: active exact Sentinel admissions are not joined to the spawned reviewer session, so governed security verdicts fail REVIEW_ADMISSION_MISMATCH. | admissions=["582d562d-a9c4-45ce-a012-25c487c8a309", "a330fef5-247c-435d-bc5b-008afa959ff5"]; component=council reviewer admission / SubagentStart; evidence_refs=["aitrace:v1:codex:dd32c58a9d84f02f43583c021afb470b", "aitrace:v1:codex:4cb9b8657b46428319a052a1599f8960"]; execution_state=BLOCKED; reasoning={"how": "Repair reviewer admission consumption/stamping/current-run session join; then record the unchanged two-finding BLOCK and dispatch the same work item for delta correction.", "what": "Two exact review-admit calls succeeded and review-doctor reported active projections, but both exact reviewer runs were observer-only with no mission binding/bound item; review returned REVIEW_ADMISSION_MISMATCH retry_safe=false.", "why": "The security research package cannot record its selected evidence verdict or enter the same-item repair loop."}; severity=high; status=open; work_item_id=90cf6903-5d6b-49c5-9543-f6b843561030; priority=critical; category=bug; log_type=bugs; content_type=log
[🐞] [2026-08-30 21:59:56 UTC] [Agent: seshat] [Project: scribe_rehome_resolution_fix_20260830] Review admission tuple is not auto-resolved by the admitted reviewer; an official admitted tuple still yields REVIEW_ADMISSION_REQUIRED unless the returned admission_id is passed explicitly. | component=council_work_review_admission; expected=Exact admitted tuple should resolve automatically or be injected into the reviewer task envelope.; reproduction=review-admit V1 behavioral tuple returned admitted id 758cf956-400f-4e2f-96c6-f9b9ddc0a504; same exact resumed reviewer attempted one receipt and received REVIEW_ADMISSION_REQUIRED before the id was supplied; severity=high; status=open; priority=high; category=bug; tags=["council-v2", "review-admission"]; log_type=bugs; content_type=log
[🐞] [2026-08-30 22:01:01 UTC] [Agent: seshat] [Project: scribe_rehome_resolution_fix_20260830] council work render-plan --apply degraded to stdout and wrote zero regions because the Council-to-Scribe bridge startup timed out, even though direct Scribe MCP calls in this session are healthy. | component=council_work_render_plan_scribe_bridge; expected=Apply should materialize both generated regions through the sanctioned Scribe bridge or return a retryable typed bridge failure.; reproduction=council work render-plan --project scribe_rehome_resolution_fix_20260830 --apply --json returned status=degraded, written_via=stdout, regions_written=0, fail_open_reason=scribe transport start timed out; severity=medium; status=open; priority=medium; category=bug; tags=["council-v2", "render-plan", "scribe-bridge"]; log_type=bugs; content_type=log
[🐞] [2026-08-30 22:10:12 UTC] [Agent: seshat] [Project: scribe_rehome_resolution_fix_20260830] SECURITY DEFECT — receipt-based rehome can adopt registry/index/authority drift because preview-time composite registry digests and index state are not persisted and revalidated during apply/recovery. | component=scribe_manage_docs_rehome_apply_preview; evidence_ref=scribe:progress:2b20a907420dd51782b9b434f63fbb07; expected=Receipt retains immutable full rehome authority, registry/index/file/mode/path binding; apply/recovery classifies every component and denies unsafe or unknown drift.; reproduction=RehomeCompositeBinding captures source_registry_digest, target_registry_digest, and index paths, but _classify_file_state consumes only file hashes; _attach_apply_preview_affordance persists only action/project/path data; _execute_retained re-enters manage_docs and re-captures current composite state.; severity=high; status=open; priority=critical; category=security; tags=["dry-run-apply", "rehome", "receipt", "security"]; log_type=bugs; content_type=log
[🐞] [2026-08-30 22:59:55 UTC] [Agent: seshat] [Project: scribe_rehome_resolution_fix_20260830] B2 exact bound Forge run could claim and consume a coordinator rebind at the current contract revision, but its single complete_work_item submission was denied non-retryably with CLIENT_BOUND_RUN_SCOPE_MISMATCH. | component=council_work_completion_attestation; expected=A current exact claim plus consumed rebind for the same work item/name/run should authorize one completion submission.; impact=Lifecycle row remains nonterminal despite verified package output; source and verification evidence are intact.; reproduction=forge_rehome_version_b2_2 claimed B2, coordinator rebind wrote the current revision, source mutation succeeded under custody, then exact completion returned CLIENT_BOUND_RUN_SCOPE_MISMATCH with run_bind_projection_scope_mismatch; severity=high; status=open; priority=high; category=bug; tags=["council-v2", "work-item", "completion-attestation"]; log_type=bugs; content_type=log
