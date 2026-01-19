# manage_docs Action Compatibility Matrix
**Phase:** 5.5 - manage_docs Tool Validation
**Date:** 2026-01-05
**Status:** PARTIAL - 3 of 17 Actions Tested
**Critical Bug:** BUG-MANAGE-DOCS-001 blocks 10+ actions

---

## Quick Reference Matrix

| # | Action | Status | Requires docs Field | Test Date | File Size | Notes |
|---|--------|--------|---------------------|-----------|-----------|-------|
| 1 | create_bug_report | ✅ PASS | ❌ No | 2026-01-05 | 1993 bytes | Auto-path creation |
| 2 | create_research_doc | ✅ PASS | ❌ No | 2026-01-05 | 2045 bytes | Auto-path creation |
| 3 | list_sections | ❌ BLOCKED | ✅ Yes | 2026-01-05 | - | DOC_NOT_FOUND error |
| 4 | list_checklist_items | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 5 | replace_section | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 6 | apply_patch | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 7 | replace_range | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 8 | replace_text | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 9 | append | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 10 | status_update | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 11 | normalize_headers | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 12 | generate_toc | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 13 | search | ⚠️ UNTESTED | ⚠️ Partial | - | - | Exact/fuzzy blocked, semantic unknown |
| 14 | batch | ⚠️ UNTESTED | ⚠️ Depends | - | - | Meta-action, status depends on delegates |
| 15 | validate_crosslinks | ⚠️ UNTESTED | ✅ Yes | - | - | Likely blocked |
| 16 | create_review_report | ⚠️ UNTESTED | ❌ No | - | - | Likely works |
| 17 | create_agent_report_card | ⚠️ UNTESTED | ❌ No | - | - | Likely works |

**Legend:**
- ✅ PASS: Action tested and works correctly
- ❌ BLOCKED: Action tested and fails due to bug
- ⚠️ UNTESTED: Not yet tested (predicted status based on code analysis)

---

## Detailed Action Profiles

### 1. create_bug_report ✅ WORKING

**Status:** PASS (Tested 2026-01-05)
**Category:** Document Creation - Auto-Path
**Requires docs Field:** ❌ No

**Function Signature:**
```python
manage_docs(
    action="create_bug_report",
    doc=<any_value>,  # conventionally "bug_report"
    metadata={
        "category": str,     # REQUIRED - sanitized for filesystem
        "slug": str,         # OPTIONAL - auto-generated if missing
        "severity": str,     # OPTIONAL
        "title": str,        # OPTIONAL
        "component": str,    # OPTIONAL
        "reported_at": str   # OPTIONAL - timestamp
    }
)
```

**Output Path:**
```
docs/bugs/<category>/<YYYY-MM-DD>_<slug>/report.md
```

**Test Results:**
- ✅ Successfully created `docs/bugs/infrastructure/2026-01-05_manage_docs_missing_docs_field/report.md`
- ✅ Template applied correctly (1993 bytes)
- ✅ Directory auto-created
- ✅ Path sanitization works (regex `r'[^\w\-_\.]'` → `'_'`)

**Why It Works:** Auto-generates file path from metadata, doesn't look up registered documents.

**Common Gotchas:**
- metadata.category is REQUIRED (error if missing)
- metadata.slug is auto-generated if missing: `f"bug_{int(now.timestamp())}"`
- Category and slug are sanitized for filesystem safety

**Usage Examples:**
```python
# Minimal usage (category only)
result = await manage_docs(
    action="create_bug_report",
    doc="bug_report",
    metadata={"category": "api"}
)

# Full usage
result = await manage_docs(
    action="create_bug_report",
    doc="bug_report",
    metadata={
        "category": "infrastructure",
        "slug": "database_schema_issue",
        "severity": "critical",
        "title": "Database missing column",
        "component": "storage/sqlite.py"
    }
)
```

---

### 2. create_research_doc ✅ WORKING

**Status:** PASS (Tested 2026-01-05)
**Category:** Document Creation - Auto-Path
**Requires docs Field:** ❌ No

**Function Signature:**
```python
manage_docs(
    action="create_research_doc",
    doc="research",  # conventional value
    doc_name=str,    # REQUIRED - filename without .md extension
    metadata={
        "research_goal": str,          # OPTIONAL
        "confidence_areas": list[str], # OPTIONAL
        "priority": str                # OPTIONAL
    }
)
```

**Output Path:**
```
docs/dev_plans/<project>/research/<doc_name>.md
```

**Test Results:**
- ✅ Successfully created `docs/dev_plans/scribe_systematic_audit_1/research/RESEARCH_MANAGE_DOCS_AUDIT_20260105.md`
- ✅ Template applied correctly (2045 bytes)
- ✅ Directory auto-created
- ✅ Metadata fields populated in template

**Why It Works:** Generates path from doc_name and project docs_dir, no registered document lookup needed.

**Common Gotchas:**
- doc_name is REQUIRED (unlike create_bug_report which auto-generates slug)
- Convention: use format `RESEARCH_<TOPIC>_<YYYYMMDD>` or `RESEARCH_<TOPIC>_<YYYYMMDD>_<HHMM>`
- No automatic INDEX.md update (manual step or future enhancement)

**Usage Examples:**
```python
# Minimal usage
result = await manage_docs(
    action="create_research_doc",
    doc="research",
    doc_name="RESEARCH_AUTH_FLOW_20260105"
)

# Full usage
result = await manage_docs(
    action="create_research_doc",
    doc="research",
    doc_name="RESEARCH_MANAGE_DOCS_AUDIT_20260105",
    metadata={
        "research_goal": "Audit all manage_docs actions",
        "confidence_areas": ["compatibility", "parameters", "edge_cases"],
        "priority": "critical"
    }
)
```

---

### 3. list_sections ❌ BLOCKED

**Status:** BLOCKED by BUG-MANAGE-DOCS-001
**Category:** Document Inspection
**Requires docs Field:** ✅ Yes

**Function Signature:**
```python
manage_docs(
    action="list_sections",
    doc=str  # REQUIRED - registered document key
)
```

**Expected Behavior:** Returns list of section anchors found in document.

**Expected Output:**
```python
{
    "ok": True,
    "sections": [
        "problem_statement",
        "system_overview",
        "component_design",
        # ... more section IDs
    ]
}
```

**Actual Result:**
```python
{
    "ok": False,
    "error": "DOC_NOT_FOUND: doc 'architecture' is not registered"
}
```

**Why It Fails:**
1. Code checks: `if doc not in (project.get("docs") or {}).keys()` (line 1023)
2. project dict from database has no 'docs' key
3. project.get("docs") → None → empty dict
4. "architecture" not in {} → fails validation
5. Returns DOC_NOT_FOUND error before attempting to read file

**Registered Document Keys:**
- `architecture` → ARCHITECTURE_GUIDE.md
- `phase_plan` → PHASE_PLAN.md
- `checklist` → CHECKLIST.md
- `progress_log` → PROGRESS_LOG.md

**Fix Required:** Implement SPEC-MANAGE-DOCS-001 to add docs_json column to database.

**Usage Example (will work after fix):**
```python
# List section anchors in architecture guide
result = await manage_docs(action="list_sections", doc="architecture")

# Expected output after fix:
# {
#     "ok": True,
#     "sections": ["problem_statement", "system_overview", "component_design", ...]
# }
```

---

### 4-15. Document Editing Actions ⚠️ UNTESTED (Likely Blocked)

All of these actions require the `docs` field and will likely fail with the same DOC_NOT_FOUND error:

#### 4. list_checklist_items
**Category:** Document Inspection
**Requires docs Field:** ✅ Yes
**Validation:** `manage_docs.py:1034-1036`

#### 5. replace_section
**Category:** Document Editing - Anchor-Based
**Requires docs Field:** ✅ Yes
**Validation:** `manage_docs.py:1252-1254`

**Expected Signature:**
```python
manage_docs(
    action="replace_section",
    doc=str,      # registered document key
    section=str,  # section anchor ID
    content=str   # replacement content
)
```

#### 6. apply_patch
**Category:** Document Editing - Structured
**Requires docs Field:** ✅ Yes
**Recommended for:** Precision edits with body-relative line numbers

**Expected Signature:**
```python
manage_docs(
    action="apply_patch",
    doc=str,
    edit={
        "type": "replace_range",
        "start_line": int,  # body-relative (excludes YAML frontmatter)
        "end_line": int,
        "content": str
    }
)
```

#### 7. replace_range
**Category:** Document Editing - Line-Targeted
**Requires docs Field:** ✅ Yes

**Expected Signature:**
```python
manage_docs(
    action="replace_range",
    doc=str,
    start_line=int,  # body-relative
    end_line=int,
    content=str
)
```

#### 8. replace_text
**Category:** Document Editing - Text-Based
**Requires docs Field:** ✅ Yes
**Note:** Undocumented action found in code

#### 9. append
**Category:** Document Editing - Append
**Requires docs Field:** ✅ Yes

**Expected Signature:**
```python
manage_docs(
    action="append",
    doc=str,
    content=str
)
```

#### 10. status_update
**Category:** Checklist Management
**Requires docs Field:** ✅ Yes

**Expected Signature:**
```python
manage_docs(
    action="status_update",
    doc="checklist",
    section=str,  # checklist item ID
    metadata={
        "status": "done",  # or "pending", "in_progress"
        "proof": str       # reference/evidence
    }
)
```

#### 11. normalize_headers
**Category:** Document Formatting
**Requires docs Field:** ✅ Yes
**Note:** Undocumented action - converts headers to canonical ATX format

#### 12. generate_toc
**Category:** Document Formatting
**Requires docs Field:** ✅ Yes
**Note:** Undocumented action - generates GitHub-style table of contents

---

### 13. search ⚠️ UNTESTED (Partial Dependency)

**Status:** UNTESTED
**Category:** Document Search
**Requires docs Field:** ⚠️ Partial

**Expected Signature:**
```python
manage_docs(
    action="search",
    doc="*",  # or specific doc key
    metadata={
        "query": str,
        "search_mode": "exact" | "fuzzy" | "semantic",
        "fuzzy_threshold": float,  # for fuzzy mode
        "k": int                    # for semantic mode
    }
)
```

**Dependency Analysis:**
- **Exact/Fuzzy Search:** Requires docs field (line 1192: `if not targets: DOC_NOT_FOUND`)
- **Semantic Search:** May work if vector indexing bypasses docs lookup
- **Status:** Partially blocked - exact/fuzzy modes definitely blocked

**Expected to Work After Fix:**
```python
# Exact search across all docs
result = await manage_docs(
    action="search",
    doc="*",
    metadata={"query": "authentication", "search_mode": "exact"}
)

# Semantic search
result = await manage_docs(
    action="search",
    doc="*",
    metadata={"query": "how does auth work", "search_mode": "semantic", "k": 8}
)
```

---

### 14. batch ⚠️ UNTESTED (Meta-Action)

**Status:** UNTESTED
**Category:** Meta-Action (Delegates to Others)
**Requires docs Field:** ⚠️ Depends on Delegated Actions

**Expected Signature:**
```python
manage_docs(
    action="batch",
    # ... batch operation parameters
)
```

**Dependency Analysis:**
- batch is a meta-action that delegates to other actions
- If batch delegates to blocked actions → blocked
- If batch delegates to working actions → works
- **Status:** Unknown until tested with specific operations

---

### 15. validate_crosslinks ⚠️ UNTESTED (Likely Blocked)

**Status:** UNTESTED
**Category:** Document Validation
**Requires docs Field:** ✅ Likely Yes
**Note:** Undocumented action found in code

---

### 16. create_review_report ⚠️ UNTESTED (Likely Works)

**Status:** UNTESTED
**Category:** Document Creation - Auto-Path
**Requires docs Field:** ❌ No

**Expected Signature:**
```python
manage_docs(
    action="create_review_report",
    doc="review_report",
    metadata={
        "stage": str  # e.g., "pre_implementation", "post_implementation"
    }
)
```

**Expected Output Path:**
```
docs/dev_plans/<project>/REVIEW_REPORT_<stage>_<YYYY-MM-DD>_<HHMM>.md
```

**Why It Should Work:** Similar to create_bug_report and create_research_doc - generates auto-path, no registered document lookup.

---

### 17. create_agent_report_card ⚠️ UNTESTED (Likely Works)

**Status:** UNTESTED
**Category:** Document Creation - Auto-Path
**Requires docs Field:** ❌ No

**Expected Signature:**
```python
manage_docs(
    action="create_agent_report_card",
    doc="agent_report_card",
    metadata={
        "agent_name": str,
        "stage": str
    }
)
```

**Expected Output Path:**
```
docs/dev_plans/<project>/AGENT_REPORT_CARD_<agent_name>_<stage>_<YYYYMMDD_HHMM>.md
```

**Why It Should Work:** Auto-path generation, no registered document dependency.

---

## Action Categories Summary

### Category A: Working Actions (2 tested, 2 likely) ✅
- create_bug_report ✅ TESTED
- create_research_doc ✅ TESTED
- create_review_report ⚠️ LIKELY WORKS
- create_agent_report_card ⚠️ LIKELY WORKS

**Pattern:** Auto-path generation, no docs field dependency

---

### Category B: Blocked Actions (1 tested, 9 likely) ❌
- list_sections ❌ TESTED
- list_checklist_items ⚠️ LIKELY BLOCKED
- replace_section ⚠️ LIKELY BLOCKED
- apply_patch ⚠️ LIKELY BLOCKED
- replace_range ⚠️ LIKELY BLOCKED
- replace_text ⚠️ LIKELY BLOCKED
- append ⚠️ LIKELY BLOCKED
- status_update ⚠️ LIKELY BLOCKED
- normalize_headers ⚠️ LIKELY BLOCKED
- generate_toc ⚠️ LIKELY BLOCKED

**Pattern:** Registered document operations, requires docs field

---

### Category C: Unknown Status (3 actions) ⚠️
- search ⚠️ PARTIAL - exact/fuzzy blocked, semantic unknown
- batch ⚠️ DEPENDS - meta-action status depends on delegates
- validate_crosslinks ⚠️ LIKELY BLOCKED

**Pattern:** Special operations with complex dependencies

---

## Testing Priority Recommendations

### High Priority (Critical for Wiki Maintenance)
1. **replace_section** - Primary editing action for architecture docs
2. **apply_patch** - Recommended v2.1.1 editing action
3. **status_update** - Checklist management
4. **append** - Adding new content
5. **search** - Finding content across documents

### Medium Priority (Nice to Have)
6. **normalize_headers** - Document formatting
7. **generate_toc** - Table of contents generation
8. **replace_range** - Alternative editing action
9. **validate_crosslinks** - Document integrity

### Low Priority (Edge Cases)
10. **replace_text** - Alternative to replace_range
11. **batch** - Meta-action complexity
12. **create_review_report** - Specialized use
13. **create_agent_report_card** - Specialized use

---

## Post-Fix Verification Checklist

After implementing SPEC-MANAGE-DOCS-001, verify all actions:

- [ ] list_sections returns section anchors
- [ ] list_checklist_items returns checklist items
- [ ] replace_section updates content
- [ ] apply_patch performs structured edits
- [ ] replace_range performs line edits
- [ ] append adds content to end
- [ ] status_update toggles checklist items
- [ ] normalize_headers converts to ATX format
- [ ] generate_toc creates table of contents
- [ ] search works in exact/fuzzy/semantic modes
- [ ] batch delegates correctly
- [ ] validate_crosslinks checks references
- [ ] create_bug_report still works (regression)
- [ ] create_research_doc still works (regression)
- [ ] create_review_report works
- [ ] create_agent_report_card works
- [ ] replace_text works

---

**Last Updated:** 2026-01-05 15:28:00 UTC
**Test Coverage:** 17.6% (3 of 17 actions)
**Blocked by:** BUG-MANAGE-DOCS-001 (database missing docs_json column)
**Fix Specification:** SPEC-MANAGE-DOCS-001-database-docs-field.yaml
