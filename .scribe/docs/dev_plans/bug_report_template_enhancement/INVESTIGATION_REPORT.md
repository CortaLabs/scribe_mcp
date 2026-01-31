---
id: bug_report_template_enhancement-investigation-report
title: Bug Report Template Enhancement Investigation
doc_name: INVESTIGATION_REPORT
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-31'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Bug Report Template Enhancement Investigation

**Investigation Date:** 2026-01-31
**Agent:** BugHunterAgent-BugTemplate
**Project:** bug_report_template_enhancement

---

## Executive Summary

Investigated three issues in the scribe_mcp bug report workflow:
1. ✅ **Issue 1:** open_bug doesn't instruct agents to fill template sections
2. ✅ **Issue 2:** open_bug metadata not fully mapped to template fields
3. ✅ **Issue 3:** manage_docs edit capability for bug reports needs verification

**Overall Findings:** All issues confirmed. The bug report workflow creates comprehensive templates but doesn't guide agents on filling them out, wastes effort on dead code, and lacks documentation on post-creation editing.

---

## Issue 1: Missing Template Guidance in open_bug Return Value

### Current Behavior
**Location:** `tools/sentinel_tools.py` lines 374-381

open_bug returns:
```python
{
    "ok": True,
    "case_id": str(case_id),
    "entry_id": str(result.get("id", "")),
    "path": str(result.get("path", "")),
    "project_name": str(result.get("project_name", "")),
    "bug_report": str(doc_result.get("path", ""))
}
```

### Problem
Agents receive no information about:
- What template sections exist in the generated report
- Which sections are unfilled and need completion
- What section anchor IDs to use with manage_docs
- What metadata fields can be populated

### Template Structure (from BUG_REPORT_TEMPLATE.md)
**Section Anchors:**
- `bug_overview` - Basic metadata (severity, status, component, environment)
- `description` - Summary, expected/actual behavior, reproduction steps
- `investigation` - Root cause, affected areas, related issues
- `resolution_plan` - Immediate actions, long-term fixes, testing strategy
- `timeline` - Phase ownership and target dates
- `appendix` - Logs, fix references, open questions

**Unfilled Template Fields:**
- `summary_long` - Brief description
- `expected_behavior` - What should happen
- `actual_behavior` - What actually happens
- `reproduction_steps` - Checklist of steps
- `root_cause` - Suspected/confirmed root cause
- `affected_areas` - Impacted services/components/files
- `related_issues` - Links to related bugs/tickets
- `immediate_actions` - Urgent mitigation steps
- `long_term_fixes` - Remedial work/refactors
- `testing_strategy` - Validation steps (unit, integration, regression)
- `owners` - Phase ownership (investigation, fix, testing, deployment)
- `timeline` - Target dates for each phase
- `logs` - Relevant logs, traces, screenshots
- `fix_references` - Git commits, PRs, documentation
- `open_questions` - Unresolved unknowns

### Recommended Fix
Enhance open_bug return value to include:
```python
{
    "ok": True,
    "case_id": str(case_id),
    "entry_id": str(result.get("id", "")),
    "path": str(result.get("path", "")),
    "project_name": str(result.get("project_name", "")),
    "bug_report": str(doc_result.get("path", "")),
    # NEW FIELDS:
    "template_sections": [
        {"anchor": "bug_overview", "status": "partial"},
        {"anchor": "description", "status": "unfilled"},
        {"anchor": "investigation", "status": "unfilled"},
        {"anchor": "resolution_plan", "status": "unfilled"},
        {"anchor": "timeline", "status": "unfilled"},
        {"anchor": "appendix", "status": "unfilled"}
    ],
    "next_steps": "Use manage_docs(action='replace_section', doc_category='bugs', doc_name='{case_id}', section='<anchor>', content='...') to fill template sections",
    "unfilled_fields": [
        "summary_long", "expected_behavior", "actual_behavior",
        "reproduction_steps", "root_cause", "affected_areas",
        "related_issues", "immediate_actions", "long_term_fixes",
        "testing_strategy", "owners", "timeline", "logs",
        "fix_references", "open_questions"
    ]
}
```

---

## Issue 2: Incomplete Metadata Mapping & Dead Code

### Current Behavior
**Location:** `tools/sentinel_tools.py` lines 333-372

open_bug passes to manage_docs:
```python
metadata={
    "doc_type": "bug",
    "category": category,
    "slug": case_id,
    "title": title,
    "case_id": case_id,
    "symptoms": symptoms,
    "affected_paths": affected_paths or [],
    "body": "..."  # 119 lines of hardcoded markdown
}
```

### Problem 1: Dead Code (lines 344-370)
The `body` field contains 119 lines of handcrafted markdown that is **NEVER USED**.

**Evidence:** `tools/manage_docs.py` lines 2675-2698
```python
rendered_content = content  # content=None from open_bug call
if not rendered_content:
    # Template rendering path (this is what executes)
    rendered_content = await _render_special_template(
        project, agent_id, template_name, metadata,
        extra_metadata=extra_metadata,
        prepared_metadata=prepared_metadata,
    )
```

The template uses Jinja2 variables from `metadata`, **not** the `body` field. This hardcoded markdown is wasted effort.

### Problem 2: Poor Metadata Mapping
Template expects rich metadata fields, but open_bug only provides:
- ✅ `title` → Used in template header
- ✅ `slug` / `case_id` → Used in Bug Overview
- ✅ `category` → Used for directory structure
- ❌ `symptoms` → **NOT mapped to any template field**
- ❌ `affected_paths` → **NOT mapped to template's `affected_areas`**

**Mapping Opportunities:**
- `symptoms` could populate `summary_long` (line 30 in template)
- `symptoms` could inform `actual_behavior` (line 36)
- `affected_paths` should map to `affected_areas` (line 47)
- Could derive `expected_behavior` from title/symptoms analysis

### Recommended Fix

**Step 1: Remove dead code (lines 344-370)**

**Step 2: Enhance metadata mapping**
```python
metadata={
    "doc_type": "bug",
    "category": category,
    "slug": case_id,
    "title": title,
    "case_id": case_id,
    "reporter": agent,
    "reported_at": today,
    "severity": "medium",  # Could be parameter
    "status": "INVESTIGATING",
    # NEW MAPPINGS:
    "summary_long": symptoms,  # Use symptoms as summary
    "actual_behavior": symptoms,  # Symptoms describe what's happening
    "affected_areas": affected_paths or [],  # Direct mapping
    "component": category,  # Use category as component
    "environment": "[local/staging/production]",  # Could be parameter
    # Keep common fields as placeholders for agents to fill:
    "expected_behavior": "[What should happen]",
    "reproduction_steps": None,  # Checklist - agents fill this
    "root_cause": "[To be determined]",
    "immediate_actions": None,
    "long_term_fixes": None,
    "testing_strategy": None,
}
```

---

## Issue 3: manage_docs Edit Capability for Bug Reports

### Investigation Finding
✅ **CONFIRMED:** manage_docs CAN edit bug reports after creation.

**Mechanism:** `tools/manage_docs.py` lines 1272-1281 and lines 1020-1092

### How It Works

1. **Custom Document Path Resolution**
   - Bug reports are registered as `custom_doc_types` (line 1274)
   - When `doc_category="bugs"` is used with EDIT_ACTIONS, manage_docs calls `_resolve_custom_doc_path()`

2. **Bug Report Discovery** (lines 1072-1092)
   ```python
   elif doc_category == "bugs":
       bugs_root = project_root / "docs" / "bugs"
       # Search all category directories for matching slug
       for category_dir in bugs_root.iterdir():
           for bug_dir in category_dir.iterdir():
               # Check if directory name ends with _<slug>
               if bug_dir.name.endswith(f"_{doc_name}"):
                   report_file = bug_dir / "report.md"
                   if report_file.exists():
                       return report_file
   ```

3. **Edit Actions Supported**
   - `replace_section` - Replace content by section anchor
   - `apply_patch` - Apply unified diff patch
   - `replace_range` - Replace explicit line range
   - `replace_text` - Find/replace text pattern
   - `append` - Append to document/section
   - `status_update` - Update checklist items (if template has checklists)

### Usage Examples

**Edit bug report description section:**
```python
manage_docs(
    agent="BugHunterAgent",
    action="replace_section",
    doc_category="bugs",
    doc_name="BUG-2026-01-31-001",  # Use case_id as doc_name
    section="description",
    content="""### Summary
Detailed summary here...

### Expected Behaviour
System should...

### Actual Behaviour
System currently...

### Steps to Reproduce
1. Step one
2. Step two
3. Observe error
"""
)
```

**Update investigation section:**
```python
manage_docs(
    agent="BugHunterAgent",
    action="replace_section",
    doc_category="bugs",
    doc_name="BUG-2026-01-31-001",
    section="investigation",
    content="""**Root Cause Analysis:**
The issue occurs because...

**Affected Areas:**
- `src/auth/login.py` - Token validation logic
- `src/database/session.py` - Session management

**Related Issues:**
- Related to #456 - Session timeout bug
"""
)
```

**Append to appendix:**
```python
manage_docs(
    agent="BugHunterAgent",
    action="append",
    doc_category="bugs",
    doc_name="BUG-2026-01-31-001",
    section="appendix",
    content="- **Additional Evidence:** Found in production logs at /var/log/app.log:1234",
    metadata={"position": "inside"}
)
```

### Documentation Gap
**Problem:** This editing capability is not documented in:
- Scribe_Usage.md manage_docs section
- BUG_HUNTER.md agent instructions
- open_bug docstring/return value

**Recommendation:** Document this workflow explicitly so agents know the full bug lifecycle:
1. Call `open_bug()` to create initial report
2. Use `manage_docs(doc_category="bugs", doc_name=case_id, ...)` to fill sections
3. Reference section anchors: `bug_overview`, `description`, `investigation`, `resolution_plan`, `timeline`, `appendix`

---

## Proposed Code Changes Summary

### File: `tools/sentinel_tools.py`

**Change 1: Remove dead body code (lines 344-370)**
- DELETE the entire `body` field from metadata dict
- Saves 119 lines of unused code

**Change 2: Enhance metadata mapping (lines 336-343)**
```python
metadata={
    "doc_type": "bug",
    "category": category,
    "slug": case_id,
    "title": title,
    "case_id": case_id,
    "reporter": agent,
    "reported_at": today,
    "severity": metadata.get("severity", "medium"),
    "status": "INVESTIGATING",
    "component": category,
    "summary_long": symptoms,
    "actual_behavior": symptoms,
    "affected_areas": affected_paths or [],
}
```

**Change 3: Enhance return value (lines 374-381)**
```python
return {
    "ok": True,
    "case_id": str(case_id),
    "entry_id": str(result.get("id", "")),
    "path": str(result.get("path", "")),
    "project_name": str(result.get("project_name", "")),
    "bug_report": str(doc_result.get("path", "")),
    "template_sections": [
        {"anchor": "bug_overview", "status": "partial"},
        {"anchor": "description", "status": "partial"},
        {"anchor": "investigation", "status": "unfilled"},
        {"anchor": "resolution_plan", "status": "unfilled"},
        {"anchor": "timeline", "status": "unfilled"},
        {"anchor": "appendix", "status": "unfilled"},
    ],
    "edit_instructions": f"Use manage_docs(action='replace_section', doc_category='bugs', doc_name='{case_id}', section='<anchor>', content='...') to complete unfilled sections",
    "unfilled_fields": [
        "expected_behavior", "reproduction_steps", "root_cause",
        "related_issues", "immediate_actions", "long_term_fixes",
        "testing_strategy", "owners", "timeline", "logs",
        "fix_references", "open_questions",
    ],
}
```

### File: `docs/Scribe_Usage.md`

**Addition: Bug Report Lifecycle Documentation**

Add new section after manage_docs examples:
```markdown
## Bug Report Workflow

### Creating Bug Reports

Use `open_bug()` to create structured bug reports:
```python
result = open_bug(
    agent="BugHunterAgent",
    title="Auth token not invalidated on logout",
    symptoms="Users can reuse tokens after logout, session persists",
    category="auth",
    affected_paths=["src/auth/login.py", "src/database/session.py"]
)
```

This creates:
- Progress log entry with bug status
- Detailed bug report at `docs/bugs/<category>/<date>_<case_id>/report.md`
- Updated bug index at `docs/bugs/INDEX.md`

The return value includes template guidance:
```python
{
    "ok": True,
    "case_id": "BUG-2026-01-31-001",
    "bug_report": "/path/to/docs/bugs/auth/2026-01-31_BUG-2026-01-31-001/report.md",
    "template_sections": [...],  # What sections exist
    "unfilled_fields": [...],    # What needs completion
    "edit_instructions": "...",   # How to edit
}
```

### Editing Bug Reports

Use `manage_docs` with `doc_category="bugs"` and `doc_name=<case_id>`:

**Replace entire section:**
```python
manage_docs(
    agent="BugHunterAgent",
    action="replace_section",
    doc_category="bugs",
    doc_name="BUG-2026-01-31-001",
    section="investigation",
    content="""**Root Cause Analysis:**
Token cleanup handler not triggered on logout...
"""
)
```

**Available section anchors:**
- `bug_overview` - Severity, status, component, environment
- `description` - Summary, expected vs actual behavior, reproduction steps
- `investigation` - Root cause, affected areas, related issues
- `resolution_plan` - Immediate actions, long-term fixes, testing
- `timeline` - Phase ownership and dates
- `appendix` - Logs, fix references, open questions

**Append to section:**
```python
manage_docs(
    action="append",
    doc_category="bugs",
    doc_name="BUG-2026-01-31-001",
    section="appendix",
    content="- **Fix PR:** #789"
)
```
```

---

## Testing Recommendations

### Test 1: Verify Enhanced Return Value
```python
result = await open_bug(
    agent="TestAgent",
    title="Test bug",
    symptoms="Test symptoms",
    category="test"
)
assert "template_sections" in result
assert "unfilled_fields" in result
assert "edit_instructions" in result
```

### Test 2: Verify Metadata Mapping
```python
result = await open_bug(
    agent="TestAgent",
    title="Test bug",
    symptoms="Expected X but got Y",
    category="test",
    affected_paths=["file1.py", "file2.py"]
)
# Read generated report
report_path = result["bug_report"]
content = Path(report_path).read_text()
assert "Expected X but got Y" in content  # symptoms mapped to summary_long
assert "file1.py" in content  # affected_paths mapped to affected_areas
```

### Test 3: Verify Edit Capability
```python
# Create bug
result = await open_bug(...)
case_id = result["case_id"]

# Edit via manage_docs
edit_result = await manage_docs(
    agent="TestAgent",
    action="replace_section",
    doc_category="bugs",
    doc_name=case_id,
    section="investigation",
    content="Root cause found!"
)
assert edit_result["ok"]

# Verify edit
report_content = Path(result["bug_report"]).read_text()
assert "Root cause found!" in report_content
```

---

## Confidence Assessment

**Overall Confidence: 0.95**

### High Confidence (0.95+)
- ✅ Issue 1: Return value structure is straightforward to enhance
- ✅ Issue 2: Dead code identification is definitive
- ✅ Issue 3: Edit capability verified through code reading and path resolution logic

### Medium Confidence (0.80-0.94)
- Metadata mapping choices (which fields to auto-populate vs leave for agents)
- Template section status detection ("partial" vs "unfilled")

### Assumptions
- Template structure remains stable (section anchors don't change)
- manage_docs section anchor resolution works correctly (not tested live)
- Bug report directory naming convention `<date>_<slug>` is consistent

---

## Next Steps

1. **Implement fixes** in `tools/sentinel_tools.py`
2. **Add documentation** to `docs/Scribe_Usage.md`
3. **Write tests** for enhanced workflow
4. **Update BUG_HUNTER.md** with editing examples
5. **Consider** making severity/environment parameters instead of hardcoded defaults

---

**End of Investigation Report**
