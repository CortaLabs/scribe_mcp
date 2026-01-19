# Case Sensitivity Auto-Registration Issue

## Executive Summary

A case sensitivity mismatch in the `_resolve_doc_path` function causes auto-registration failures when `list_sections` attempts to locate newly created research documents. Documents are created with preserved case (e.g., `RESEARCH_test_create_action_20260119.md`) but lookup converts the doc_name to uppercase (e.g., `RESEARCH_TEST_CREATE_ACTION_20260119.md`), causing the file-not-found error.

## Root Cause Analysis

### Location: `doc_management/manager.py`, line 787

```python
filename = {
    "architecture": "ARCHITECTURE_GUIDE.md",
    "phase_plan": "PHASE_PLAN.md",
    "checklist": "CHECKLIST.md",
    "progress_log": "PROGRESS_LOG.md",
    "doc_log": "DOC_LOG.md",
    "security_log": "SECURITY_LOG.md",
    "bug_log": "BUG_LOG.md",
}.get(doc_name, f"{doc_name.upper()}.md")  # <-- UPPERCASE CONVERSION HERE
```

**Problem:** The fallback behavior `.get(doc_name, f"{doc_name.upper()}.md")` converts unknown doc_names to uppercase. This is intended for standard documents but breaks for custom research document names.

### Creation Flow: `tools/manage_docs.py`

When research documents are created (line 2542):
```python
target_path = research_dir / f"{safe_name}.md"
```

The `safe_name` is derived from `doc_name` via sanitization (lines 2500-2504):
- Input: `RESEARCH_test_create_action_20260119`
- After sanitization: `RESEARCH_test_create_action_20260119` (case preserved)
- File created: `/path/to/research/RESEARCH_test_create_action_20260119.md`

### Lookup Flow: `tools/manage_docs.py` → `doc_management/manager.py`

When `list_sections` is called with the same doc_name (line 2213):

1. **Step 1:** Check if doc_name is in project.docs mapping (line 2203)
   - Result: Not found (first auto-registration attempt)

2. **Step 2:** Call `_resolve_doc_path(project, doc_name)` (line 2213)
   - Input: `doc_name = "RESEARCH_test_create_action_20260119"`
   - Lookup in filename dict (line 751): Not found (only standard keys exist)
   - **Fallback triggered:** `f"{doc_name.upper()}.md"`
   - Output: `RESEARCH_TEST_CREATE_ACTION_20260119.md` (all uppercase)

3. **Step 3:** Check if resolved path exists (line 2215)
   - Expected file: `.../RESEARCH_TEST_CREATE_ACTION_20260119.md`
   - Actual file: `.../RESEARCH_test_create_action_20260119.md`
   - **Result:** File not found → Error: "Cannot auto-register..."

## Impact Assessment

**Severity:** Medium - affects UX of research document operations

**Affected Operations:**
- `list_sections` for any custom-named research document
- `auto_register` for custom document names that don't match standard patterns
- Any lookup operation using doc_name that falls through to the uppercase conversion

**Current Workaround:** None - auto-registration fails completely

## Recommended Fixes

### Option 1: Case-Preserving Fallback (RECOMMENDED)
**Rationale:** Research documents and custom documents should preserve their case as created.

**Change in `doc_management/manager.py` line 787:**
```python
# OLD:
.get(doc_name, f"{doc_name.upper()}.md")

# NEW:
.get(doc_name, f"{doc_name}.md")
```

**Pros:**
- Simple one-line fix
- Preserves case as intended by document creators
- No behavioral impact on standard documents (they're in the dict)

**Cons:**
- Changes behavior for any undocumented fallback cases
- May expose case-sensitive issues on case-insensitive filesystems (unlikely)

### Option 2: Case-Insensitive Lookup
**Rationale:** Support case-insensitive document discovery across filesystems.

**Implementation:**
1. Attempt exact match first (line 787 current behavior)
2. Fall back to case-insensitive directory scan if not found
3. Return first match or error if multiple matches

**Pros:**
- Robust across different filesystem types
- Forgives accidental case variations

**Cons:**
- More complex implementation
- Potential ambiguity with multiple similar-cased files
- Performance impact on lookup

### Option 3: Consistent Uppercase Convention
**Rationale:** Enforce all documents use uppercase naming consistently.

**Implementation:**
1. Modify creation code to uppercase doc_name before file creation
2. Document the uppercase convention

**Pros:**
- Clear, enforced naming convention
- Predictable behavior

**Cons:**
- Breaking change for existing research documents
- Uppercase filenames less intuitive for research docs
- Requires migration of existing documents

## Confidence Assessment

- **Root cause identified:** 100% (verified in code)
- **Execution path confirmed:** 95% (traced through both file creation and lookup)
- **Impact verified:** 100% (error message exactly matches code flow)

## Files Referenced

- `/home/austin/projects/MCP_SPINE/scribe_mcp/doc_management/manager.py:787` - root cause
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/manage_docs.py:2213` - lookup entry point
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/manage_docs.py:2542` - creation point
- `/home/austin/projects/MCP_SPINE/scribe_mcp/tools/manage_docs.py:2195-2254` - auto-registration logic

## Recommendation

**Implement Option 1 (Case-Preserving Fallback)** - It is the simplest, least invasive fix that aligns with how research documents are created and matches user expectations.
