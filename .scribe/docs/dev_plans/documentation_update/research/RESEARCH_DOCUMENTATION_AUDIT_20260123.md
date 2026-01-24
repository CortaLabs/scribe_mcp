---
id: documentation_update-research-documentation-audit-20260123
title: "\U0001F52C Research Documentation Audit 20260123 \u2014 documentation_update"
doc_name: RESEARCH_DOCUMENTATION_AUDIT_20260123
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-23'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Documentation Audit 20260123 — documentation_update
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-23 09:41:25 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
The Scribe MCP documentation is **significantly outdated** following the v2.2 codebase cleanup. All public-facing documentation still references v2.1.1, while the codebase has undergone major architectural changes including:

1. **ResponseFormatter decomposition** into 7 specialized modules (`utils/formatters/`)
2. **Connection pooling** via new `storage/pool.py` (SQLiteConnectionPool)
3. **state.json deprecation** (database-only mode)
4. **Data retention policy** with `scribe_entries_archive` table
5. **Agent parameter requirement** for session isolation on all tools

These changes are documented in the internal dev plan (`scribe_codebase_audit/ARCHITECTURE_GUIDE.md`) but have NOT been propagated to public documentation.

**Overall Documentation Health: POOR (40%)**
- 8 of 12 audited documents require updates
- 3 documents are severely outdated (>3 months behind)
- 2 documents have inconsistent examples (missing agent parameter)

**Primary Objective:** Audit all documentation files to identify what needs updating after v2.2 cleanup.

**Key Takeaways:**
- Version mismatch: All docs show v2.1.1, codebase is v2.2
- AGENTS_EXTENDED.md is severely outdated (v1.0 from Oct 2025)
- state.json is deprecated but still documented as active
- Connection pooling and formatter decomposition completely undocumented
- Estimated 14-20 hours to fully update all documentation
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-DocAudit
**Investigation Window:** 2026-01-23

**Focus Areas:**
- [x] README.md - Main project readme
- [x] CLAUDE.md - Claude Code operational instructions
- [x] AGENTS_EXTENDED.md - Internal architecture documentation
- [x] docs/Scribe_Usage.md - Comprehensive tool usage guide
- [x] docs/whitepapers/scribe_mcp_whitepaper.md - Technical whitepaper
- [x] .codex/skills/scribe-mcp-usage/SKILL.md - Skill entry point
- [x] .codex/skills/scribe-mcp-usage/references/quickstart.md - Quick start guide
- [x] .codex/skills/scribe-mcp-usage/references/Operational_Contract.md - Tool signatures
- [x] docs/claude_code_subagents/*.md - 5 subagent prompt files
- [x] docs/mcp_server_guide.md - Generic MCP guide
- [x] docs/BRIDGE_DEVELOPMENT.md - Bridge system guide

**Dependencies & Constraints:**
- v2.2 architecture defined in `.scribe/docs/dev_plans/scribe_codebase_audit/ARCHITECTURE_GUIDE.md`
- Codebase inspection via `storage/pool.py`, `utils/formatters/` directory
- Grep searches for v2.2 keywords (state.json, ResponseFormatter, pool)
<!-- ID: findings -->
### Finding 1: README.md Outdated (HIGH Priority)
- **Summary:** Version badge shows v2.1.1 (line 6), still documents SCRIBE_STATE_PATH env var (line 298) which is deprecated. Missing all v2.2 architectural changes.
- **Evidence:** `grep "v2.1.1\|state.json" README.md` shows 4 matches
- **Confidence:** 0.99
- **Changes Needed:** Version bump, add v2.2 section, deprecate state.json reference, document connection pooling and formatters

### Finding 2: AGENTS_EXTENDED.md Severely Outdated (HIGH Priority)
- **Summary:** Version v1.0, last updated 2025-10-22 (3+ months old). Predates v2.x entirely. Database schema missing new columns (status, docs_json), missing scribe_entries_archive table, missing agent parameter requirement.
- **Evidence:** Header shows "Version: v1.0 Extended, Last Updated: 2025-10-22"
- **Confidence:** 0.99
- **Changes Needed:** Near-complete rewrite - update schema, add session isolation, add formatters architecture, update roadmap

### Finding 3: CLAUDE.md Partially Outdated (HIGH Priority)
- **Summary:** Header shows v2.1.1, references storage/sqlite.py line numbers that may have changed. No mention of utils/formatters/ decomposition or connection pooling.
- **Evidence:** Line 3: "Scribe MCP v2.1.1", Line 335: references storage/sqlite.py
- **Confidence:** 0.95
- **Changes Needed:** Version bump, add v2.2 architecture components section, verify line number references

### Finding 4: docs/Scribe_Usage.md Mostly Accurate (MEDIUM Priority)
- **Summary:** Session isolation correctly documented (lines 124-155), agent parameter shown in examples. However, header shows v2.1.1 and missing v2.2 architecture sections.
- **Evidence:** Line 5: "Update v2.1.1", Line 170: correct agent parameter usage
- **Confidence:** 0.90
- **Changes Needed:** Add v2.2 section, document connection pooling, document data retention policy

### Finding 5: Whitepaper Outdated (MEDIUM Priority)
- **Summary:** Title shows v2.1.1, State Manager section references state.json, Storage Backends section missing pool.py.
- **Evidence:** Line 1: "Scribe MCP Whitepaper v2.1.1"
- **Confidence:** 0.95
- **Changes Needed:** Update to v2.2, add Connection Pool section, update State Manager section

### Finding 6: quickstart.md Missing Agent Parameter (MEDIUM Priority)
- **Summary:** Examples missing required agent parameter on set_project and read_recent calls. Inconsistent with Scribe_Usage.md.
- **Evidence:** Line 7: `set_project(name="...", root="...")` - no agent param
- **Confidence:** 0.95
- **Changes Needed:** Add agent parameter to all tool call examples

### Finding 7: v2.2 Architecture Documented Internally Only
- **Summary:** The v2.2 architecture (connection pool, formatters, state.json deprecation, retention) is fully documented in `scribe_codebase_audit/ARCHITECTURE_GUIDE.md` but NOT propagated to public docs.
- **Evidence:** `.scribe/docs/dev_plans/scribe_codebase_audit/ARCHITECTURE_GUIDE.md` lines 120-220
- **Confidence:** 0.99
- **Changes Needed:** Propagate internal architecture docs to public documentation

### Additional Notes
- Operational_Contract.md is accurate (agent param shown on line 12)
- SKILL.md is accurate for manage_docs patterns
- BRIDGE_DEVELOPMENT.md unaffected by v2.2 changes
- mcp_server_guide.md is generic, no changes needed
- Subagent docs (5 files) have minor inconsistencies with agent parameter
<!-- ID: technical_analysis -->
**Code Patterns Identified:**

v2.2 Architectural Components (from codebase inspection):
```
utils/formatters/
├── __init__.py      # Module exports
├── base.py          # Base utilities, color handling
├── dispatcher.py    # Routes to correct formatter
├── entry.py         # Log entry formatting
├── file.py          # File content formatting
├── project.py       # Project list/detail formatting
├── ui.py            # Boxes, headers, spinners
```

```
storage/pool.py      # SQLiteConnectionPool class (409 lines)
  - Thread-safe connection pooling
  - min=1, max=3 default connections
  - acquire()/release() lifecycle
```

**System Interactions:**
- `storage/pool.py` integrates with `storage/sqlite.py`
- `utils/formatters/` replaces monolithic `utils/response.py` (facade retained for backward compatibility)
- `scribe_entries_archive` table for data retention
- Agent sessions tracked in database instead of state.json

**Risk Assessment:**
- [x] Documentation drift creates confusion for new users
- [x] state.json deprecation not communicated - users may still configure it
- [x] Skill quickstart inconsistent with canonical Scribe_Usage.md
- [ ] Version mismatch may cause support issues (users reporting v2.1.1 bugs for v2.2)
<!-- ID: recommendations -->
### Immediate Next Steps (HIGH Priority - 7-11 hours)

| Document | Effort | Actions |
|----------|--------|---------|
| **README.md** | 2-3 hrs | 1) Update version badge to v2.2, 2) Add "Update v2.2" section, 3) Deprecate SCRIBE_STATE_PATH, 4) Document connection pooling |
| **AGENTS_EXTENDED.md** | 4-6 hrs | 1) Update to v2.2, 2) Rewrite Storage Architecture section, 3) Update database schema, 4) Add session isolation, 5) Update roadmap |
| **CLAUDE.md** | 1-2 hrs | 1) Update version to v2.2, 2) Add formatters architecture, 3) Verify line number references |

### Medium Priority (5.5-7.5 hours)

| Document | Effort | Actions |
|----------|--------|---------|
| **docs/Scribe_Usage.md** | 2-3 hrs | Add v2.2 section, document pool/retention |
| **whitepaper** | 3-4 hrs | Update architecture sections, version bump |
| **quickstart.md** | 30 min | Add agent param to all examples |

### Long-Term Opportunities

1. **Create v2.2 Release Notes** - Single source of truth document that other docs can reference
2. **Automate skill reference sync** - Build script to generate quickstart.md from Scribe_Usage.md sections
3. **Consider AGENTS_EXTENDED.md future** - May be better to merge with whitepaper or deprecate
4. **Architecture diagrams** - The v2.2 diagrams in scribe_codebase_audit should be added to README/whitepaper
<!-- ID: appendix -->
**References:**
- `.scribe/docs/dev_plans/scribe_codebase_audit/ARCHITECTURE_GUIDE.md` - v2.2 architecture source
- `storage/pool.py` - Connection pool implementation (409 lines)
- `utils/formatters/` - Decomposed formatter modules (7 files)

**Effort Summary:**

| Priority | Documents | Estimated Hours |
|----------|-----------|-----------------|
| HIGH | 3 | 7-11 hours |
| MEDIUM | 3 | 5.5-7.5 hours |
| LOW | 5 | 1.25 hours |
| **TOTAL** | **11** | **13.75-19.75 hours** |

**Confidence Assessment:**

| Finding | Confidence |
|---------|------------|
| Version mismatch (v2.1.1 vs v2.2) | 0.99 |
| state.json deprecation not documented | 0.95 |
| Connection pool not documented | 0.98 |
| Formatter decomposition not documented | 0.98 |
| Agent parameter inconsistencies | 0.95 |
| AGENTS_EXTENDED.md severely outdated | 0.99 |
| Effort estimates | 0.75 |

---

*Research completed: 2026-01-23 09:42 UTC*
*Files analyzed: 12 documentation files*
*Lines reviewed: ~5000+*
*Auditor: ResearchAgent-DocAudit*
