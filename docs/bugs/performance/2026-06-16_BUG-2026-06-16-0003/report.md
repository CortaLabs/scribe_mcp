
# 🐞 Postgres legacy project name uniqueness mutates active project root during same-server root comparison — integrate-system-scribe-latency-20260616T050042Z
**Author:** Scribe
**Version:** v0.1
**Status:** RESOLVED
**Last Updated:** 2026-06-16 09:55:00 UTC

This report tracks the Postgres project identity defect that could mutate a named project onto the wrong repository root.

---
## Bug Overview
<!-- ID: bug_overview -->
**Bug ID:** BUG-2026-06-16-0003

**Reported By:** seshat

**Date Reported:** 2026-06-16 06:58:10 UTC

**Severity:** CRITICAL

**Status:** RESOLVED

**Component:** postgres-project-identity

**Environment:** local Postgres scribe schema

**Customer Impact:** Critical for governed multi-repo Scribe/Council work. A controlled root-comparison or cross-repo `set_project` call can silently move a named project record from its source-authoritative repo root to another repo. That causes later logs, docs, and telemetry to land under the wrong physical `.scribe` tree or fail with duplicate-name errors, undermining auditability and making latency measurements untrustworthy.

**Operational Impact:** Blocks P5 acceptance and any final optimization claim because the same-server probe currently mutates project configuration while declaring `config_mutation=false`. It also creates recurring coordinator recovery work and can make agents misdiagnose Scribe tool availability or project context as a surface issue when the real defect is durable project identity drift.

**Severity Rationale:** Critical because it corrupts the workstream's project binding and can redirect governance evidence across repositories without explicit operator intent.


---
## Description
<!-- ID: description -->
### Summary
P5 same_server_root_comparison can call set_project with the same project name for scribe_mcp and council_mcp roots. On a live Postgres DB that still has legacy global unique constraint/index scribe_projects_name_key, upsert_project cannot create separate repo-scoped project identities and instead updates the single scribe_projects row from scribe_mcp to council_mcp. Subsequent set_project for the exact workstream root fails or writes to the wrong docs/progress path until the row is manually ...

### Expected Behaviour
Repo-scoped project identity must allow the same project name in different repo roots using project_key/repo_id without mutating the existing root, and the P5 same-server comparison must honor config_mutation=false.

### Actual Behaviour
P5 same_server_root_comparison can call set_project with the same project name for scribe_mcp and council_mcp roots. On a live Postgres DB that still has legacy global unique constraint/index scribe_projects_name_key, upsert_project cannot create separate repo-scoped project identities and instead updates the single scribe_projects row from scribe_mcp to council_mcp. Subsequent set_project for the exact workstream root fails or writes to the wrong docs/progress path until the row is manually ...

### Steps to Reproduce
- [ ] Ensure live Postgres schema contains legacy unique constraint/index scribe_projects_name_key on scribe.scribe_projects(name).
- [ ] Bind project integrate-system-scribe-latency-20260616T050042Z at /home/austin/projects/MCP_SPINE/scribe_mcp.
- [ ] Run: uv run python -m scribe_mcp.scripts.scribe_probe --tools same_server_root_comparison --project integrate-system-scribe-latency-20260616T050042Z --agent SeshatProbe --hook-label hook_excluded --roots /home/austin/projects/MCP_SPINE/scribe_mcp,/home/austin/projects/MCP_SPINE/council_mcp
- [ ] Query scribe.scribe_projects for that project name; row is left bound to /home/austin/projects/MCP_SPINE/council_mcp.



---
## Investigation
<!-- ID: investigation -->
**Root Cause Analysis:**
Legacy global project-name uniqueness remains in the live schema. The recent compatibility path handles scribe_projects_name_key by updating the existing row to the requested repo_root/project_key, which corrupts repo-scoped identity during cross-root comparisons.

**Affected Areas:**
- src/scribe_mcp/storage/postgres/__init__.py
- src/scribe_mcp/storage/postgres/schema.py
- src/scribe_mcp/scripts/scribe_probe.py
- tests/test_postgres_project_identity_scoping.py
- tests/test_scribe_probe.py


**Related Issues:**
- Link to related bugs, tickets, or documentation.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Actions
- [x] Fix schema/bootstrap so repo-scoped project identity uses project_key/repo_id and refuses legacy same-name root swaps.
- [x] Update the Postgres upsert path so same-name different-root calls do not silently mutate the existing project row.
- [x] Verify the same-server/root-comparison path preserves the active project binding.


### Long-Term Fixes
- Keep project identity checks in the Postgres backend, where durable root/project_key truth is enforced for every caller.

### Testing Strategy
- Focused regression coverage: tests/test_postgres_project_identity_scoping.py and tests/test_scribe_probe.py.
- Popper bug-hunter closeout verification: `uv run pytest tests/test_dispatcher.py tests/test_log_intelligence.py tests/test_tool_calls_schema.py tests/test_postgres_project_identity_scoping.py tests/test_scribe_probe.py tests/test_set_project.py -q` -> 93 passed.


---
## Timeline & Ownership
<!-- ID: timeline -->
| Phase | Owner | Target Date | Notes |
| --- | --- | --- | --- |
| Investigation | [Name] | [Date] | [Details] |
| Fix Development | [Name] | [Date] | [Details] |
| Testing | [Name] | [Date] | [Details] |
| Deployment | [Name] | [Date] | [Details] |


---
## Appendix
<!-- ID: appendix -->
- **Fix Reference:** src/scribe_mcp/storage/postgres/__init__.py:198; src/scribe_mcp/storage/postgres/schema.py; tests/test_postgres_project_identity_scoping.py; tests/test_scribe_probe.py (execution: 18eabb5e-4710-45c2-86ea-16c12dfbb618)
- **Landing Status:** resolved
- **Fix Linked By:** seshat


---
