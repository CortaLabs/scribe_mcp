---
id: documentation_update-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 documentation_update"
doc_name: phase_plan
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

# ⚙️ Phase Plan — documentation_update
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-23 09:36:41 UTC

> Execution roadmap for documentation_update.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Est. Effort | Confidence |
|-------|------|------------------|-------------|------------|
| Phase 1 | HIGH Priority Docs | README.md, AGENTS_EXTENDED.md, CLAUDE.md updated | 7-11 hours | 0.95 |
| Phase 2 | MEDIUM Priority Docs | Scribe_Usage.md, whitepaper, quickstart.md updated | 5.5-7.5 hours | 0.90 |
| Phase 3 | LOW Priority Docs | Subagent docs, AGENTS.md agent param fixes | 1.25 hours | 0.95 |
| Phase 4 | Verification | Cross-document consistency check, final audit | 1-2 hours | 0.90 |

**Total Estimated Effort:** 14-22 hours

**Execution Order:** Phases must be completed sequentially. Phase 1 establishes the v2.2 baseline that later phases reference.

**Source of Truth:** All v2.2 content comes from `.scribe/docs/dev_plans/scribe_codebase_audit/ARCHITECTURE_GUIDE.md`
<!-- ID: phase_0 -->
**Objective:** Update the three most impactful documents that users and Claude Code interact with daily.

**Estimated Effort:** 7-11 hours

---

### Task Package 1.1: README.md Update

**Scope:** Update version badge, add v2.2 section, deprecate state.json references
**File:** `README.md`
**Dependencies:** None (first task)

**Specifications:**
1. **Line 6**: Change version badge from `2.1.1` to `2.2`
   ```markdown
   **[![Version](https://img.shields.io/badge/version-2.2-blue)](docs/whitepapers/)**
   ```

2. **After Line 16**: Add new "Update v2.2" section (insert before existing v2.1.1 section)
   ```markdown
   ## Update v2.2 (Architecture Cleanup)

   Scribe MCP v2.2 delivers major architectural improvements:

   **Performance:**
   - **Connection Pooling**: New `storage/pool.py` with SQLiteConnectionPool delivers 50-80% latency reduction
   - **Optimized Indexes**: New composite indexes for agent/emoji filtering

   **Code Quality:**
   - **ResponseFormatter Decomposition**: Monolithic 2,934-line class split into 7 specialized modules in `utils/formatters/`
   - **Database-First State**: Session state migrated from state.json to database

   **Data Management:**
   - **Retention Policy**: New `scribe_entries_archive` table with configurable cleanup (default 90 days)
   - **Agent Isolation**: All tools require `agent` parameter for session isolation

   ---
   ```

3. **Line 17**: Rename existing section to mark as historical
   ```markdown
   ## History: Update v2.1.1 (Diff Editor, Readable Output & ANSI Colors)
   ```

4. **Line 298**: Update SCRIBE_STATE_PATH reference with deprecation notice
   ```markdown
   - `SCRIBE_STATE_PATH=/abs/path/to/state.json` **(DEPRECATED in v2.2 - sessions now stored in database)**
   ```

**Verification:**
- [ ] Version badge shows v2.2
- [ ] New v2.2 section exists after line 16
- [ ] v2.1.1 section marked as "History"
- [ ] SCRIBE_STATE_PATH marked deprecated

**Out of Scope:**
- Do NOT modify code examples in other sections
- Do NOT change file structure or other badges

---

### Task Package 1.2: AGENTS_EXTENDED.md Update

**Scope:** Major update to reflect v2.2 architecture
**File:** `AGENTS_EXTENDED.md`
**Dependencies:** Task 1.1 (establishes v2.2 baseline language)

**Specifications:**
1. **Lines 1-6**: Update header
   ```markdown
   # AGENTS_EXTENDED.md - Scribe MCP Server (Internal)

   **Author:** CortaLabs
   **Maintainer:** UAP / Sanctum Division
   **Version:** v2.2
   **Last Updated:** 2026-01-23
   ```

2. **After Architectural Overview section (~line 51)**: Add new "v2.2 Architecture Components" section
   ```markdown
   ### v2.2 Architecture Components

   #### ResponseFormatter Decomposition
   The monolithic ResponseFormatter (2,934 lines) has been decomposed into specialized modules:

   | Module | Location | Responsibility |
   |--------|----------|----------------|
   | base.py | `utils/formatters/` | Base utilities, color handling |
   | entry.py | `utils/formatters/` | Log entry formatting |
   | file.py | `utils/formatters/` | File content formatting |
   | project.py | `utils/formatters/` | Project list/detail formatting |
   | ui.py | `utils/formatters/` | Boxes, headers, spinners |
   | dispatcher.py | `utils/formatters/` | Routes to correct formatter |

   The original `utils/response.py` is retained as a backwards-compatible facade.

   #### Connection Pooling
   New `storage/pool.py` provides SQLiteConnectionPool:
   - Thread-safe connection pooling with acquire()/release() lifecycle
   - Default configuration: min=1, max=3 connections
   - Delivers 50-80% latency reduction for database operations

   #### Session Isolation
   All Scribe tools now require the `agent` parameter for session isolation:
   - Format: `agent="AgentName"` or `agent="AgentName-TaskSlug"`
   - Enables concurrent agent operation without log collision
   - Sessions stored in `agent_sessions` database table (state.json deprecated)

   #### Data Retention
   - New `scribe_entries_archive` table preserves audit trail
   - `cleanup_old_entries()` method with configurable retention (default 90 days)
   - Archive-before-delete pattern maintains compliance
   ```

3. **Database Schema section**: Add missing columns
   - Add `status TEXT` column to scribe_projects
   - Add `docs_json TEXT` column to scribe_projects
   - Add `scribe_entries_archive` table documentation

**Verification:**
- [ ] Header shows v2.2 and current date
- [ ] v2.2 Architecture Components section exists
- [ ] ResponseFormatter decomposition documented
- [ ] Connection pooling documented
- [ ] Session isolation documented with agent parameter
- [ ] Database schema updated with new columns/tables

**Out of Scope:**
- Do NOT remove historical sections
- Do NOT modify the Guiding Principles section

---

### Task Package 1.3: CLAUDE.md Update

**Scope:** Update version references and add v2.2 architecture documentation
**File:** `CLAUDE.md`
**Dependencies:** Task 1.1 (establishes v2.2 baseline language)

**Specifications:**
1. **Line 3**: Update version
   ```markdown
   **Scribe MCP v2.2** - Enterprise-grade documentation governance for AI-powered development
   ```

2. **Line 628** (approximately): Update section header
   ```markdown
   ### v2.2 Enhanced Tools
   ```

3. **Line 711** (footer): Update version reference
   ```markdown
   *Scribe MCP v2.2 - Operational guidance for Claude Code orchestration*
   ```

4. **After "Essential Tools Quick Reference" section**: Add new section
   ```markdown
   ## v2.2 Architecture Components

   ### ResponseFormatter Decomposition
   The monolithic ResponseFormatter (2,934 lines) has been split into 7 specialized modules in `utils/formatters/`:
   - `base.py` - Base utilities, color handling
   - `entry.py` - Log entry formatting
   - `file.py` - File content formatting
   - `project.py` - Project list/detail formatting
   - `ui.py` - Boxes, headers, spinners
   - `dispatcher.py` - Routes to correct formatter

   Original `response.py` retained as backwards-compatible facade.

   ### Connection Pooling
   New `storage/pool.py` provides SQLiteConnectionPool:
   - Thread-safe connection management
   - Default min=1, max=3 connections
   - 50-80% latency reduction

   ### State Migration
   - state.json deprecated (database-only mode)
   - Session state stored in `agent_sessions` table
   - SCRIBE_STATE_PATH environment variable deprecated
   ```

**Verification:**
- [ ] Line 3 shows v2.2
- [ ] Section header updated (line ~628)
- [ ] Footer shows v2.2 (line ~711)
- [ ] New v2.2 Architecture Components section exists
- [ ] No other v2.1.1 references remain

**Out of Scope:**
- Do NOT modify operational instructions
- Do NOT change manage_docs playbook
- Do NOT update line number references to storage/sqlite.py (verify they're still accurate first)

---

**Phase 1 Acceptance Criteria:**
- [ ] All 3 HIGH priority documents updated
- [ ] Version consistency (all show v2.2)
- [ ] v2.2 architecture documented in all 3 files
- [ ] state.json deprecation noted where relevant
<!-- ID: phase_1 -->
**Objective:** Update reference documentation and skill materials.

**Estimated Effort:** 5.5-7.5 hours

---

### Task Package 2.1: docs/Scribe_Usage.md Update

**Scope:** Add v2.2 architecture section and update version references
**File:** `docs/Scribe_Usage.md`
**Dependencies:** Phase 1 complete

**Specifications:**
1. Update header version reference from v2.1.1 to v2.2

2. Add new "v2.2 Architecture" section after introduction:
   ```markdown
   ## v2.2 Architecture Updates

   ### Connection Pooling
   Scribe v2.2 introduces connection pooling via `storage/pool.py`:
   - SQLiteConnectionPool with acquire()/release() lifecycle
   - Configuration: `pool_min_size` (default 1), `pool_max_size` (default 3)
   - Delivers 50-80% latency reduction

   ### Data Retention
   New retention policy via `cleanup_old_entries()`:
   - Entries archived to `scribe_entries_archive` table before deletion
   - Configurable retention period (default 90 days)
   - Triggered during server startup or via explicit call

   ### State Migration
   - state.json deprecated - all session state stored in database
   - Agent sessions tracked in `agent_sessions` table
   - SCRIBE_STATE_PATH environment variable no longer required
   ```

3. Document connection pool configuration options in Configuration section

**Verification:**
- [ ] Version updated to v2.2
- [ ] v2.2 Architecture section exists
- [ ] Connection pool configuration documented
- [ ] Data retention documented

**Out of Scope:**
- Do NOT rewrite existing tool documentation
- Agent parameter already documented correctly

---

### Task Package 2.2: Whitepaper Update

**Scope:** Update whitepaper to reflect v2.2 architecture
**File:** `docs/whitepapers/scribe_mcp_whitepaper.md`
**Dependencies:** Phase 1 complete

**Specifications:**
1. **Title**: Update version to v2.2
   ```markdown
   # Scribe MCP Whitepaper v2.2
   ```

2. **State Manager section**: Update to reflect database-only mode
   - Remove or deprecate state.json references
   - Document agent_sessions table as session storage
   - Note SCRIBE_STATE_PATH deprecation

3. **Storage Backends section**: Add Connection Pool subsection
   ```markdown
   ### Connection Pooling (v2.2)

   SQLite operations now use connection pooling via `storage/pool.py`:

   | Setting | Default | Description |
   |---------|---------|-------------|
   | pool_min_size | 1 | Minimum connections maintained |
   | pool_max_size | 3 | Maximum concurrent connections |
   | pool_timeout | 30s | Connection acquire timeout |

   Benefits:
   - 50-80% latency reduction for database operations
   - Thread-safe connection management
   - Graceful degradation under load
   ```

4. Update any architecture diagrams that show state.json as active

**Verification:**
- [ ] Title shows v2.2
- [ ] State Manager section updated (no active state.json)
- [ ] Connection Pool section exists
- [ ] Architecture diagrams accurate

**Out of Scope:**
- Do NOT rewrite conceptual sections
- Keep existing structure intact

---

### Task Package 2.3: quickstart.md Agent Parameter Fix

**Scope:** Add agent parameter to all tool examples
**File:** `.codex/skills/scribe-mcp-usage/references/quickstart.md`
**Dependencies:** None (can run in parallel with 2.1/2.2)

**Specifications:**
Search for and update all tool examples to include agent parameter:

1. `set_project` examples:
   ```python
   # Before
   set_project(name="my_project", root="/path/to/repo")
   
   # After
   set_project(agent="AgentName", name="my_project", root="/path/to/repo")
   ```

2. `read_recent` examples:
   ```python
   # Before
   read_recent(limit=5)
   
   # After
   read_recent(agent="AgentName", limit=5)
   ```

3. `append_entry` examples:
   ```python
   # Before (if any)
   append_entry(message="...", status="info")
   
   # After
   append_entry(agent="AgentName", message="...", status="info")
   ```

4. Any other tool examples - add agent as first parameter

**Verification:**
- [ ] grep for tool calls without agent parameter returns no results
- [ ] All examples match Scribe_Usage.md format
- [ ] Examples are syntactically correct

**Out of Scope:**
- Do NOT add new examples
- Do NOT restructure the document

---

**Phase 2 Acceptance Criteria:**
- [ ] Scribe_Usage.md updated with v2.2 content
- [ ] Whitepaper updated to v2.2
- [ ] All quickstart.md examples include agent parameter
- [ ] Cross-reference check: quickstart matches Scribe_Usage.md
<!-- ID: milestone_tracking -->
**Objective:** Fix agent parameter inconsistencies in remaining documents.

**Estimated Effort:** 1.25 hours

---

### Task Package 3.1: Subagent Docs Agent Parameter Fixes

**Scope:** Add agent parameter to tool examples in subagent documentation
**Files:** `docs/claude_code_subagents/*.md` (5 files)
**Dependencies:** Phase 1 complete (establishes agent param patterns)

**Files to Update:**
- `docs/claude_code_subagents/architect.md`
- `docs/claude_code_subagents/bug_hunter.md`
- `docs/claude_code_subagents/coder.md`
- `docs/claude_code_subagents/research.md`
- `docs/claude_code_subagents/review.md`

**Specifications:**
For each file:
1. Search for tool examples missing `agent` parameter
2. Add `agent="<AgentType>Agent"` as first parameter
3. Use appropriate agent name for context:
   - architect.md: `agent="ArchitectAgent"`
   - bug_hunter.md: `agent="BugHunterAgent"`
   - coder.md: `agent="CoderAgent"`
   - research.md: `agent="ResearchAgent"`
   - review.md: `agent="ReviewAgent"`

**Verification:**
- [ ] Each file has no tool calls without agent parameter
- [ ] Agent names match the document context
- [ ] Examples are syntactically correct

**Out of Scope:**
- Do NOT rewrite subagent instructions
- Do NOT add new tool examples

---

### Task Package 3.2: AGENTS.md Version Reference Fix

**Scope:** Update any v2.1.1 references to v2.2
**File:** `AGENTS.md`
**Dependencies:** None

**Specifications:**
1. Search for "v2.1.1" in AGENTS.md
2. Update to "v2.2" where appropriate
3. Preserve any historical context (changelog references)

**Verification:**
- [ ] No active v2.1.1 references remain
- [ ] Historical references clearly marked
- [ ] Document structure unchanged

**Out of Scope:**
- Do NOT rewrite agent documentation
- Do NOT modify cross-repo instructions

---

**Phase 3 Acceptance Criteria:**
- [ ] All 5 subagent docs have agent parameter in examples
- [ ] AGENTS.md version references updated
- [ ] No v2.1.1 references remain (except historical)

---

## Phase 4 - Verification & Final Audit

**Objective:** Cross-document consistency check and final verification.

**Estimated Effort:** 1-2 hours

---

### Task Package 4.1: Version Consistency Audit

**Scope:** Verify all documents show v2.2 consistently
**Dependencies:** Phases 1-3 complete

**Specifications:**
Run verification commands:
```bash
# Check for remaining v2.1.1 references (should be historical only)
grep -r "v2\.1\.1" *.md docs/ .codex/ --include="*.md" | grep -v "History\|changelog\|historical"

# Verify v2.2 appears in key locations
grep -l "v2\.2" README.md CLAUDE.md AGENTS_EXTENDED.md docs/Scribe_Usage.md
```

**Verification:**
- [ ] No unexpected v2.1.1 references found
- [ ] All key documents contain v2.2

---

### Task Package 4.2: Agent Parameter Audit

**Scope:** Verify all tool examples include agent parameter
**Dependencies:** Phases 1-3 complete

**Specifications:**
Run audit command:
```bash
# Find tool calls that may be missing agent parameter
grep -rn "set_project\|append_entry\|read_recent\|manage_docs\|query_entries" *.md docs/ .codex/ --include="*.md" | grep -v "agent="
```

Review results - any matches should be:
- Prose descriptions (not code examples)
- Historical/deprecated examples clearly marked

**Verification:**
- [ ] No code examples missing agent parameter
- [ ] All tool invocations follow canonical format

---

### Task Package 4.3: Cross-Document Consistency Check

**Scope:** Verify architecture descriptions match across all documents
**Dependencies:** Task 4.1 and 4.2 complete

**Specifications:**
Verify consistency of:
1. Connection pool description (same numbers: min=1, max=3, 50-80% improvement)
2. Formatter modules (same 7 modules listed)
3. state.json deprecation language (consistent messaging)
4. Agent parameter format (consistent `agent="AgentName"` examples)

**Verification:**
- [ ] Connection pool specs match across docs
- [ ] Formatter list identical across docs
- [ ] Deprecation language consistent
- [ ] Agent param examples consistent

---

**Phase 4 Acceptance Criteria:**
- [ ] Version consistency verified
- [ ] Agent parameter consistency verified
- [ ] Cross-document consistency verified
- [ ] Final documentation health score: 95%+

---

## Milestone Tracking

| Milestone | Target Date | Owner | Status | Evidence |
|-----------|-------------|-------|--------|----------|
| Phase 1: HIGH Priority Complete | TBD | CoderAgent | Pending | PROGRESS_LOG |
| Phase 2: MEDIUM Priority Complete | TBD | CoderAgent | Pending | PROGRESS_LOG |
| Phase 3: LOW Priority Complete | TBD | CoderAgent | Pending | PROGRESS_LOG |
| Phase 4: Verification Complete | TBD | ReviewAgent | Pending | Audit Report |
| Project Complete | TBD | Orchestrator | Pending | All phases pass |
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.


---