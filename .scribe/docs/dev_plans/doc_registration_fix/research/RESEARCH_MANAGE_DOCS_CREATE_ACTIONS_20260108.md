
# 🔬 Research Manage Docs Create Actions 20260108 — doc_registration_fix
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-08 11:12:18 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->

**Primary Objective:** Investigate why `manage_docs` create_* actions (create_research_doc, create_bug_report, create_review_report, create_agent_report_card) fail to enable subsequent document operations via manage_docs despite successfully writing files to disk.

**Key Takeaways:**
- **Root Cause Found**: Files are written successfully but NOT registered in the project's `docs_json` field in the database
- **Breaking Impact**: Subsequent manage_docs operations fail with "DOC_NOT_FOUND" error when attempting to edit created documents
- **Code Location**: `tools/manage_docs.py` function `_handle_special_document_creation()` (lines 2337-2601), specifically missing call after file write at line 2525
- **Solution Scope**: Add 15-20 lines of registration code between lines 2584-2595
- **Implementation Pattern Available**: Reference implementation exists in `_auto_register_document()` (lines 954-981) used by EDIT_ACTIONS
- **Ready for Implementation**: Root cause clearly identified, fix well-scoped, no blocking unknowns


---
## Research Scope
<!-- ID: research_scope -->

**Research Lead:** ResearchAgent-ManageDocs

**Investigation Window:** 2026-01-08 11:10 UTC — 2026-01-08 11:13 UTC (3 minutes)

**Focus Areas:**
- [x] Locate implementations of create_research_doc, create_bug_report, create_review_report, create_agent_report_card actions
- [x] Trace execution path from action dispatch through file write to post-processing
- [x] Identify all calls made after file creation (changelog, logging, index)
- [x] Compare with working EDIT_ACTIONS pattern to find gaps
- [x] Identify exact code insertion point for fix
- [x] Propose solution with reference implementation

**Dependencies & Constraints:**
- Investigation focused on `tools/manage_docs.py` (114KB file, 3079 lines)
- Compared patterns against `_auto_register_document()` function which is proven working
- Limited to code inspection; no execution or test runs performed
- All file references use absolute paths: `/home/austin/projects/MCP_SPINE/scribe_mcp/`
- Verified root cause by attempting document edit immediately after creation - confirmed DOC_NOT_FOUND error despite file existing on disk


---
## Findings
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.

### Finding 1: Root Cause - Missing Registration in docs_json
- **Summary:** The `create_*` actions in `tools/manage_docs.py` write files successfully but **fail to register documents in the `docs_json` field** of the project record in the database. This breaks subsequent manage_docs operations that require document lookup.
- **Evidence:**
  - Affected actions: `create_research_doc` (line 2371), `create_bug_report` (line 2401), `create_review_report` (line 2431), `create_agent_report_card` (line 2438)
  - All routed through `_handle_special_document_creation()` (lines 2337-2601)
  - File write at line 2525, but no `update_project_docs()` call follows
  - Verified: File exists on disk but cannot be edited with subsequent manage_docs calls (get "DOC_NOT_FOUND" error)
- **Confidence:** Very High (0.95)

### Finding 2: What IS Called vs. What's Missing
- **Summary:** After file creation, the code performs partial registration (changelog/progress/index) but skips database registration.
- **Evidence:**
  - Lines 2529: Calls `_record_special_doc_change()` → records to changelog table only
  - Line 2568: Calls `append_entry()` → logs to progress_log
  - Line 2580: Calls `index_updater()` → updates INDEX.md file
  - **MISSING**: No call to `backend.update_project_docs()` to update the `docs` field in project record
- **Confidence:** Very High (0.95)

### Finding 3: How EDIT Actions Get It Right
- **Summary:** EDIT_ACTIONS correctly register documents via `_auto_register_document()` at line 1306.
- **Evidence:**
  - `manage_docs()` at line 1296 checks if doc is registered
  - Line 1306: Calls `await _auto_register_document(project, doc_category)`
  - `_auto_register_document()` function (lines 891-1000):
    - Line 963: Calls `await backend.update_project_docs(project_name, docs_json)` ✓
    - Line 972-978: Updates ProjectRegistry ✓
    - Line 985-995: Logs event ✓
- **Confidence:** Very High (0.95)

### Finding 4: Implementation Location for Fix
- **Summary:** The fix insertion point is clearly identified in the code.
- **Evidence:**
  - File: `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/manage_docs.py`
  - Function: `_handle_special_document_creation()`
  - Current section: Lines 2523-2601 (file write and post-processing)
  - Insertion point: After line 2584 (after index_updater() call), before line 2586 (success_payload)
  - Pattern to follow: Extract doc registration logic from `_auto_register_document()` (lines 954-963)
  - Key: Use `doc_label` as the key in docs mapping (e.g., "research_report", "bug_report", "review_report", "agent_report_card")
- **Confidence:** Very High (0.95)

### Additional Notes
- **Impact**: Created documents are on disk and indexed but inaccessible via manage_docs operations
- **Test Evidence**: Demonstrated by creating research doc and immediately attempting to edit it - received DOC_NOT_FOUND error despite file existing on disk
- **Parity Issue**: Create_* actions lack the registration calls that EDIT_ACTIONS have, creating asymmetric behavior


---
## Technical Analysis
<!-- ID: technical_analysis -->

**Code Patterns Identified:**

1. **Registration Pattern in EDIT_ACTIONS (CORRECT)**:
   - Check if doc is registered: `if doc_category not in docs:` (line 1300)
   - Auto-register if missing: `await _auto_register_document(project, doc_category)` (line 1306)
   - Result: docs_json field updated with new entry

2. **Bypass Pattern in CREATE_ACTIONS (BROKEN)**:
   - File written: `target_path.write_text(rendered_content)` (line 2525)
   - Changelog recorded: `_record_special_doc_change()` (line 2529)
   - Progress logged: `append_entry()` (line 2568)
   - Index updated: `await index_updater()` (line 2580)
   - **Missing**: No docs_json registration
   - Result: doc exists on disk but not in project.docs mapping

3. **The Asymmetry**:
   - EDIT_ACTIONS: Auto-register → Can lookup → Can edit ✓
   - CREATE_ACTIONS: Skip registration → Cannot lookup → Cannot edit ✗

**System Interactions:**

- **Project Model**: `project.get("docs")` returns dict mapping doc_name → file_path
- **Storage Backend**: `update_project_docs()` writes to scribe_projects.docs column
- **ProjectRegistry**: In-memory cache that mirrors database state
- **Validation**: Lines 1355-1357 check if `doc_name in (project.get("docs") or {}).keys()`

**Risk Assessment:**

- **Severity**: HIGH - Complete blocking of subsequent operations on created documents
- **Scope**: All CREATE_* actions (4 actions × N documents created = impact multiplier)
- **Duration**: Affects all created docs until project is reloaded or docs_json is manually fixed
- **Mitigation**: Add registration call before returning success (5-10 lines of code)


---
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.

### Immediate Next Steps

**Required Fix**: Add document registration to `_handle_special_document_creation()` after index update

**Location**: `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/manage_docs.py` lines 2584-2595

**Implementation**:
```python
# After line 2584 (after index_updater() call), add:

# Register document in project.docs mapping for lookup
try:
    current_docs = project.get("docs", {})
    current_docs[doc_label] = str(target_path)  # Use doc_label as key
    docs_json = json.dumps(current_docs)

    project_name = project.get("name")
    if project_name:
        await backend.update_project_docs(project_name, docs_json)

        # Update ProjectRegistry in-memory tracking
        await _PROJECT_REGISTRY.record_doc_update(
            project_name=project_name,
            doc_key=doc_label,
            file_path=str(target_path),
            baseline_hash=after_hash,
            current_hash=after_hash,
        )
except Exception as e:
    # Non-fatal - document is on disk and indexed, but not in docs mapping
    print(f"⚠️ Failed to register document '{doc_label}' in docs_json: {e}")
    # Continue - don't fail the operation
```

**Code Pattern**: Extract from `_auto_register_document()` (lines 954-981)

**Testing**:
1. Create a document with `create_research_doc` action
2. Immediately attempt to edit it with `replace_section` or `apply_patch`
3. Verify no "DOC_NOT_FOUND" error occurs
4. Verify `project.get("docs")` includes the new document
5. Verify INDEX.md is updated
6. Verify progress_log has creation entry

**Affected Actions** (all require fix):
- `create_research_doc`
- `create_bug_report`
- `create_review_report`
- `create_agent_report_card`

### Long-Term Opportunities

1. **Consolidate Registration Logic**: Extract doc registration into helper function to avoid duplication
   - Currently: `_auto_register_document()` for EDIT_ACTIONS
   - Need: Shared function for CREATE_ACTIONS
   - Opportunity: DRY principle improvement

2. **Add Integration Tests**: Create test suite verifying create → edit workflow
   - Test each CREATE_* action
   - Verify document appears in project.docs after creation
   - Verify INDEX.md is updated
   - Verify subsequent edits work without re-registration

3. **Document Registration Contract**: Create design doc explaining when/how docs are registered
   - Current behavior: Implicit and scattered across code
   - Recommended: Explicit contract with clear responsibilities
   - Benefit: Prevent similar gaps in future features


---
## Appendix
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---