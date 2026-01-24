---
id: documentation_update-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 documentation_update"
doc_name: architecture
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

# 🏗️ Architecture Guide — documentation_update
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-23 09:36:41 UTC

> Architecture guide for documentation_update.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
### Context
Scribe MCP has undergone a major v2.2 codebase cleanup (documented in `scribe_codebase_audit/ARCHITECTURE_GUIDE.md`) that introduced significant architectural changes:

1. **ResponseFormatter Decomposition** - Monolithic 2,934-line class split into 7 specialized modules in `utils/formatters/`
2. **Connection Pooling** - New `storage/pool.py` with SQLiteConnectionPool for 50-80% latency reduction
3. **state.json Deprecation** - Database-only mode, session state migrated to agent_sessions table
4. **Data Retention Policy** - New `scribe_entries_archive` table with configurable cleanup
5. **Agent Parameter Requirement** - All tools now require `agent` parameter for session isolation

**The Problem:** These changes are NOT documented in public-facing documentation. All docs still reference v2.1.1.

### Current State Assessment

**Documentation Health: POOR (40%)**
- 8 of 12 audited documents require updates
- 3 documents severely outdated (>3 months behind)
- 2 documents have inconsistent examples (missing agent parameter)

**HIGH Priority Documents:**
| Document | Issue | Impact |
|----------|-------|--------|
| `README.md` | Version v2.1.1, references deprecated SCRIBE_STATE_PATH | New users get wrong info |
| `AGENTS_EXTENDED.md` | Version v1.0, dated 2025-10-22, predates v2.x | Internal architecture completely wrong |
| `CLAUDE.md` | Version v2.1.1, missing formatters/pool documentation | Claude Code operates with outdated info |

**MEDIUM Priority Documents:**
| Document | Issue | Impact |
|----------|-------|--------|
| `docs/Scribe_Usage.md` | Header v2.1.1, missing v2.2 architecture | Tool reference incomplete |
| `docs/whitepapers/scribe_mcp_whitepaper.md` | v2.1.1, state.json still documented | Technical whitepaper misleading |
| `.codex/skills/scribe-mcp-usage/references/quickstart.md` | Missing agent parameter in examples | Skill examples don't work |

**LOW Priority Documents:**
- Subagent docs in `docs/claude_code_subagents/` - minor agent param fixes
- `AGENTS.md` - minor version reference

### Goals
1. Update all documentation to reflect v2.2 architecture accurately
2. Deprecate state.json references and document database-only mode
3. Ensure all tool examples include required `agent` parameter
4. Propagate v2.2 architecture diagrams and component documentation
5. Maintain consistency across all documentation files

### Success Metrics
| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Documentation health | 40% | 95%+ | Audit score |
| Version consistency | v2.1.1 | v2.2 | All docs show same version |
| Agent param coverage | 60% | 100% | All tool examples have agent param |
| Architecture accuracy | 0% | 100% | v2.2 components documented |

### What is NOT in Scope
- Code changes - this is documentation only
- New feature documentation - only documenting existing v2.2 features
- External documentation (external websites, READMEs in other repos)
<!-- ID: requirements_constraints -->
### Functional Requirements

**FR-1: Version Consistency**
- All documentation must show v2.2 version
- Version badges, headers, and references must be updated
- Historical changelog sections preserved but clearly marked

**FR-2: Architecture Documentation**
- Document ResponseFormatter decomposition (`utils/formatters/`)
- Document connection pooling (`storage/pool.py`, SQLiteConnectionPool)
- Document data retention policy (`scribe_entries_archive`)
- Document session isolation via agent parameter

**FR-3: Deprecation Communication**
- Mark state.json as deprecated
- Update SCRIBE_STATE_PATH environment variable documentation
- Provide migration guidance for users still using state.json

**FR-4: Example Consistency**
- All tool examples must include `agent` parameter
- Examples must be consistent across all documentation
- Skill quickstart must match canonical Scribe_Usage.md

### Non-Functional Requirements

**NFR-1: Accuracy**
- All technical claims must be verified against actual code
- Line number references must be validated
- API signatures must match implementation

**NFR-2: Maintainability**
- Use consistent formatting across all documents
- Include source references where appropriate
- Structure for future version updates

### Constraints

1. **Documentation Only** - No code changes in this project
2. **Preserve History** - Changelog sections remain, clearly marked as historical
3. **Source of Truth** - `scribe_codebase_audit/ARCHITECTURE_GUIDE.md` is authoritative for v2.2
4. **Format Preservation** - Maintain existing document structures where possible
5. **Cross-Reference** - Update internal links that point to moved/changed content

### Assumptions
- All v2.2 code changes are complete and stable
- Source architecture documentation is accurate
- Coder Agent has access to all documentation files

### Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Inconsistent updates across files | Checklist with cross-verification |
| Missing edge cases in examples | Review against actual tool signatures |
| Breaking external links | Search for external references before changing |
<!-- ID: architecture_overview -->
### Solution Summary
A phased documentation update approach, prioritized by impact. HIGH priority documents updated first (widest user impact), followed by MEDIUM (reference materials), then LOW (minor fixes).

### v2.2 Content to Propagate

The following technical content from `scribe_codebase_audit/ARCHITECTURE_GUIDE.md` must be propagated to public documentation:

**1. ResponseFormatter Decomposition**
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
- Monolithic 2,934-line ResponseFormatter split into domain-specific modules
- Backwards-compatible facade retained in `utils/response.py`

**2. Connection Pooling**
```python
storage/pool.py - SQLiteConnectionPool class
- Thread-safe connection pooling
- Default: min=1, max=3 connections
- acquire()/release() lifecycle
- 50-80% latency reduction
```

**3. state.json Deprecation**
- Session state now stored in `agent_sessions` database table
- SCRIBE_STATE_PATH environment variable deprecated
- Database-only mode is now default

**4. Data Retention**
- New `scribe_entries_archive` table for audit trail
- `cleanup_old_entries()` method with configurable retention
- Default 90-day retention policy

**5. Agent Parameter Requirement**
- All Scribe tools now require `agent` parameter
- Enables session isolation for concurrent agents
- Format: `agent="AgentName"` or `agent="AgentName-TaskSlug"`

### Document Update Strategy

| Document | Update Type | Key Changes |
|----------|-------------|-------------|
| README.md | Version + Architecture | Add v2.2 section, deprecate state.json refs |
| AGENTS_EXTENDED.md | Major Rewrite | Update to v2.2, add formatters/pool, fix schema |
| CLAUDE.md | Version + Additions | Add formatters/pool sections |
| Scribe_Usage.md | Version + Additions | Add v2.2 architecture section |
| Whitepaper | Version + Sections | Add Connection Pool, update State Manager |
| quickstart.md | Example Fixes | Add agent param to all examples |

### Data Flow (Documentation Update Process)

```
Source (v2.2 Architecture)          Target Documents
┌─────────────────────────┐        ┌─────────────────────────┐
│ scribe_codebase_audit/  │        │ README.md               │
│ ARCHITECTURE_GUIDE.md   │───────>│ AGENTS_EXTENDED.md      │
│ (Source of Truth)       │        │ CLAUDE.md               │
└─────────────────────────┘        │ docs/Scribe_Usage.md    │
                                   │ docs/whitepapers/*.md   │
                                   │ .codex/skills/...       │
                                   └─────────────────────────┘
```
<!-- ID: detailed_design -->
### 4.1 HIGH Priority Document Specifications

#### README.md Update Specification
**File:** `README.md` (821 lines)
**Effort:** 2-3 hours

**Changes Required:**
1. **Line 6**: Update version badge from `2.1.1` to `2.2`
2. **Lines 17-39**: Rename "Update v2.1.1" section to historical, add new "Update v2.2" section
3. **Line 298**: Deprecate `SCRIBE_STATE_PATH` environment variable reference
4. **New Section**: Add v2.2 Architecture Overview after line ~50

**New v2.2 Section Content:**
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
```

**Verification:**
- Version badge shows v2.2
- SCRIBE_STATE_PATH marked deprecated with migration note
- New v2.2 section exists and is accurate

---

#### AGENTS_EXTENDED.md Update Specification
**File:** `AGENTS_EXTENDED.md` (207 lines)
**Effort:** 4-6 hours (major rewrite)

**Changes Required:**
1. **Lines 1-6**: Update header to v2.2, date to current
2. **Lines 29-51**: Update Architectural Overview for v2.2
3. **Database Schema Section**: Add missing columns (status, docs_json), add scribe_entries_archive
4. **New Section**: Add Session Isolation documentation
5. **New Section**: Add Formatters Architecture
6. **New Section**: Add Connection Pool documentation

**Header Update:**
```markdown
**Version:** v2.2
**Last Updated:** 2026-01-23
```

**New Formatters Section:**
```markdown
### ResponseFormatter Architecture (v2.2)

The monolithic ResponseFormatter has been decomposed into specialized modules:

| Module | Responsibility |
|--------|----------------|
| `formatters/base.py` | Base utilities, color handling |
| `formatters/entry.py` | Log entry formatting |
| `formatters/file.py` | File content formatting |
| `formatters/project.py` | Project list/detail formatting |
| `formatters/ui.py` | Boxes, headers, spinners |
| `formatters/dispatcher.py` | Routes to correct formatter |

The original `utils/response.py` is retained as a backwards-compatible facade.
```

**Verification:**
- Version shows v2.2, date is current
- Database schema includes status, docs_json columns
- scribe_entries_archive table documented
- Connection pool section exists
- Formatters architecture documented

---

#### CLAUDE.md Update Specification
**File:** `CLAUDE.md` (711 lines)
**Effort:** 1-2 hours

**Changes Required:**
1. **Line 3**: Update from "v2.1.1" to "v2.2"
2. **Line 628**: Update "v2.1.1 NEW Tools" header
3. **Line 711**: Update footer version reference
4. **New Section**: Add v2.2 Architecture Components after Essential Tools

**New v2.2 Architecture Section:**
```markdown
## v2.2 Architecture Components

### ResponseFormatter Decomposition
The monolithic ResponseFormatter (2,934 lines) has been split into 7 specialized modules in `utils/formatters/`:
- `base.py`, `entry.py`, `file.py`, `project.py`, `ui.py`, `dispatcher.py`
- Original `response.py` retained as backwards-compatible facade

### Connection Pooling
New `storage/pool.py` provides SQLiteConnectionPool:
- Thread-safe connection management
- Default min=1, max=3 connections
- 50-80% latency reduction

### State Migration
- state.json deprecated (database-only mode)
- Session state stored in agent_sessions table
- SCRIBE_STATE_PATH environment variable deprecated
```

**Verification:**
- All v2.1.1 references updated to v2.2
- New architecture section present and accurate
- Line numbers verified against actual code

---

### 4.2 MEDIUM Priority Document Specifications

#### docs/Scribe_Usage.md Update Specification
**File:** `docs/Scribe_Usage.md`
**Effort:** 2-3 hours

**Changes Required:**
1. Update header version reference
2. Add new "v2.2 Architecture" section
3. Document connection pooling configuration
4. Document data retention policy

**Verification:**
- Version updated
- New architecture section complete
- Configuration options documented

---

#### Whitepaper Update Specification
**File:** `docs/whitepapers/scribe_mcp_whitepaper.md`
**Effort:** 3-4 hours

**Changes Required:**
1. Update title version to v2.2
2. Update State Manager section to reflect database-only mode
3. Add Connection Pool section under Storage Backends
4. Update architecture diagrams if present

**Verification:**
- Title shows v2.2
- State Manager section accurate
- Connection Pool documented

---

#### quickstart.md Update Specification
**File:** `.codex/skills/scribe-mcp-usage/references/quickstart.md`
**Effort:** 30 minutes

**Changes Required:**
1. Add `agent` parameter to all `set_project` examples
2. Add `agent` parameter to all `read_recent` examples
3. Add `agent` parameter to all other tool examples

**Example Fix:**
```python
# Before (WRONG)
set_project(name="my_project", root="/path/to/repo")

# After (CORRECT)
set_project(agent="AgentName", name="my_project", root="/path/to/repo")
```

**Verification:**
- All tool examples include agent parameter
- Examples consistent with Scribe_Usage.md

---

### 4.3 LOW Priority Document Specifications

#### Subagent Docs Agent Parameter Fixes
**Files:** `docs/claude_code_subagents/*.md` (5 files)
**Effort:** ~15 minutes each

**Changes Required:**
- Add agent parameter to any tool examples that are missing it

**Verification:**
- All tool examples include agent parameter

#### AGENTS.md Version Reference
**File:** `AGENTS.md`
**Effort:** 15 minutes

**Changes Required:**
- Update any v2.1.1 references to v2.2

**Verification:**
- No v2.1.1 references remain
<!-- ID: directory_structure -->
### Documents to Update

```
scribe_mcp/
├── README.md                           # HIGH - Version, v2.2 section, deprecate state.json
├── CLAUDE.md                           # HIGH - Version, add architecture section
├── AGENTS_EXTENDED.md                  # HIGH - Major rewrite for v2.2
├── AGENTS.md                           # LOW - Version reference fix
├── docs/
│   ├── Scribe_Usage.md                 # MEDIUM - Add v2.2 architecture
│   ├── whitepapers/
│   │   └── scribe_mcp_whitepaper.md    # MEDIUM - Version, connection pool
│   └── claude_code_subagents/          # LOW - Agent param fixes
│       ├── architect.md
│       ├── bug_hunter.md
│       ├── coder.md
│       ├── research.md
│       └── review.md
└── .codex/skills/scribe-mcp-usage/
    └── references/
        └── quickstart.md               # MEDIUM - Agent param fixes
```

### Source Reference (DO NOT MODIFY)

```
.scribe/docs/dev_plans/scribe_codebase_audit/
└── ARCHITECTURE_GUIDE.md               # v2.2 architecture source of truth
```

### v2.2 Code Reference (Verify Against)

```
scribe_mcp/
├── storage/
│   └── pool.py                         # SQLiteConnectionPool (14KB)
├── utils/
│   └── formatters/                     # Decomposed formatters
│       ├── __init__.py
│       ├── base.py                     # Base utilities (10KB)
│       ├── dispatcher.py               # Routing (18KB)
│       ├── entry.py                    # Log entries (32KB)
│       ├── file.py                     # File content (34KB)
│       ├── project.py                  # Projects (40KB)
│       └── ui.py                       # UI components (15KB)
└── server.py                           # Pool lifecycle integration
```
<!-- ID: data_storage -->
### Documentation Files (Targets)

| File | Priority | Size | Format |
|------|----------|------|--------|
| README.md | HIGH | 821 lines | Markdown |
| AGENTS_EXTENDED.md | HIGH | 207 lines | Markdown |
| CLAUDE.md | HIGH | 711 lines | Markdown |
| docs/Scribe_Usage.md | MEDIUM | ~2000 lines | Markdown |
| docs/whitepapers/scribe_mcp_whitepaper.md | MEDIUM | ~800 lines | Markdown |
| .codex/skills/.../quickstart.md | MEDIUM | ~100 lines | Markdown |
| docs/claude_code_subagents/*.md | LOW | ~400 lines each | Markdown |
| AGENTS.md | LOW | ~600 lines | Markdown |

### Source Documentation (Reference Only)

| File | Purpose |
|------|---------|
| `.scribe/docs/dev_plans/scribe_codebase_audit/ARCHITECTURE_GUIDE.md` | v2.2 architecture source of truth |
| `storage/pool.py` | Connection pool implementation reference |
| `utils/formatters/*.py` | Formatter modules reference |

### No Database Changes

This project is documentation-only. No database schema changes required.
<!-- ID: testing_strategy -->
### Verification Approach

Since this is documentation-only work, testing focuses on accuracy verification:

**1. Version Consistency Check**
- Grep all updated files for version references
- Verify no v2.1.1 references remain (except historical changelog)
- Confirm v2.2 appears in all appropriate locations

**2. Agent Parameter Audit**
- Search all tool examples for missing `agent` parameter
- Cross-reference against canonical Scribe_Usage.md
- Verify quickstart examples work when executed

**3. Technical Accuracy Verification**
- Compare documented architectures against actual code
- Verify file paths mentioned exist
- Confirm API signatures match implementation
- Validate line number references

**4. Cross-Document Consistency**
- Ensure same information presented consistently across docs
- Verify internal links work
- Check for contradictions between documents

### Verification Commands

```bash
# Check no v2.1.1 remains (except historical)
grep -r "v2\.1\.1" *.md docs/ --include="*.md" | grep -v "historical\|changelog\|History"

# Find tool calls missing agent parameter
grep -rn "set_project\|append_entry\|read_recent" *.md docs/ .codex/ | grep -v "agent="

# Verify formatters directory exists
ls -la utils/formatters/

# Verify pool.py exists
ls -la storage/pool.py
```

### Review Checklist for Each Document

- [ ] Version updated to v2.2
- [ ] No deprecated references (state.json active, SCRIBE_STATE_PATH required)
- [ ] All tool examples include agent parameter
- [ ] v2.2 architecture components documented where appropriate
- [ ] Technical claims verified against code
- [ ] Internal links functional
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should templates support conditionals per phase? | Docs Lead | TODO | Evaluate after initial rollout. |
Close each question once answered and reference the relevant section above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->
- PROGRESS_LOG.md- ARCHITECTURE_GUIDE.md
Generated via generate_doc_templates.


---