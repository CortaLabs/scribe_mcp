
# 🐞 Bug Log — manage_docs_agent_ux
**Maintained By:** Scribe
**Timezone:** UTC

> Track bug discoveries, investigations, and resolutions. Use `log_type="bugs"` (or `--log bugs`).

---



## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: manage_docs_agent_ux] Message text | severity=<severity>; component=<component>; status=<status>; [additional metadata]
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
- **Backend**: Server-side code, APIs, databases.
- **Frontend**: UI and client-side logic.
- **Infrastructure**: Deployment, CI/CD, monitoring, configuration.
- **Tests**: Test suites or infrastructure.
- **Documentation**: READMEs, API docs, guides.
- **Performance**: Latency/throughput regressions.
- **Security**: Security-related bugs and vulnerabilities.
- **Data**: Migration, seeding, or validation errors.

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
[🐞] [2026-01-20 03:59:27 UTC] [Agent: MyBB-ArchitectAgent] [Project: manage_docs_agent_ux] FULL REPORT: Why Agents Bypass manage_docs  ## Root Cause Analysis  ### Issue #1: Misunderstanding of manage_docs for Architecture Documents  **What I did wrong:** - Used `manage_docs(action="create", doc_name="ARCHITECTURE_GUIDE", metadata={"doc_type": "custom", "body": "..."})`  - Expected it to write to `ARCHITECTURE_GUIDE.md` - It actually wrote to `custom.md`  **Why this happened:** - The `doc_type: custom` in metadata appears to influence the output filename - The documentation shows `doc_name` as "Document identifier used for naming/registration" but the behavior created `custom.md` - There's a mismatch between expected behavior (doc_name = filename) and actual behavior  ### Issue #2: Architecture documents (ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST) are special  **The real pattern for these docs:** - These are TEMPLATE documents created by `generate_doc_templates`  - They already EXIST with section anchors (`<!-- ID: problem_statement -->`) - The correct approach is `replace... | category=agent_ux; component=manage_docs; reasoning={"how": "Need documentation updates, possible tool behavior investigation, and agent prompt clarification", "what": "Three issues identified: (1) create action writes to custom.md not doc_name.md, (2) architecture docs require replace_section not create, (3) fallback to Write tool when confused", "why": "Agents are bypassing manage_docs because the expected behavior does not match actual behavior, and training does not clarify the correct pattern for architecture documents"}; severity=high; status=open; priority=high; log_type=bugs; content_type=log
