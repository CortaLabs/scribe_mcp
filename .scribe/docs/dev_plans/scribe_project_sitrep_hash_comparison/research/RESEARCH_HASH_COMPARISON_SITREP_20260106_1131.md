# 🔬 Research: Hash Comparison SITREP Implementation — scribe_project_sitrep_hash_comparison
**Author:** ResearchAgent
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-06 11:32:00 UTC

> This research investigates BUG-001 where set_project/get_project/list_projects incorrectly detect project state using entry_count logic instead of hash comparison. Documents existing hash infrastructure and defines correct architecture for new/unchanged/modified project detection.

---

## Executive Summary
<!-- ID: executive_summary -->

**Primary Objective:** Fix BUG-001 SITREP detection logic by replacing `entry_count == 0` with proper baseline vs current hash comparison.

**Key Takeaways:**
- **Hash infrastructure ALREADY EXISTS and is FULLY FUNCTIONAL** in ProjectRegistry (lines 226-262)
- **BUG-001 confirmed** at `tools/set_project.py:459` - uses `entry_count == 0` which incorrectly marks rotated logs as "new"
- **Fix is trivial**: Tools already call `ProjectRegistry.get_project()` but ignore `meta.docs.flags` which contains per-document modification status
- **Three states needed**: NEW (no baseline hashes), UNCHANGED (baseline == current), MODIFIED (baseline != current)
- **No new infrastructure required** - only consumption of existing flags

**Confidence:** 1.0 (all findings verified through code inspection and tracing)

---

## Research Scope
<!-- ID: research_scope -->

**Research Lead:** ResearchAgent
**Investigation Window:** 2026-01-06 (single day deep-dive)

**Focus Areas:**
- [x] Current implementation analysis (set_project.py, get_project.py, list_projects.py)
- [x] Hash infrastructure location and lifecycle (ProjectRegistry, manage_docs)
- [x] Bug mechanism and reproduction steps (entry_count logic)
- [x] Correct architecture design (three-state detection)
- [x] Edge case handling (new projects, rotated logs, manual file changes)
- [x] Integration with docs_json infrastructure

**Dependencies & Constraints:**
- Hash tracking only works for documents modified via `manage_docs`
- New projects (template generation) don't record baseline hashes initially
- Must preserve backward compatibility with existing SITREP formatters
- Cannot break abstraction layer (direct sqlite3 usage in ProjectRegistry noted but out of scope)

---

## Findings
<!-- ID: findings -->

### Finding 1: Hash Infrastructure is Complete and Functional
**File:** `shared/project_registry.py:226-262`

**Summary:** ProjectRegistry.record_doc_update() maintains complete hash tracking with per-document modification flags.

**Evidence:**
```python
# Lines 227-234: Hash storage
baseline_map = docs_meta.get("baseline_hashes") or {}
current_map = docs_meta.get("current_hashes") or {}
if doc not in baseline_map and before_hash:
    baseline_map[doc] = before_hash  # Set ONCE
if after_hash:
    current_map[doc] = after_hash    # Updated ALWAYS
docs_meta["baseline_hashes"] = baseline_map
docs_meta["current_hashes"] = current_map

# Lines 245-251: Flag derivation
modified = (
    bool(baseline_val)
    and bool(current_val)
    and baseline_val != current_val
)
flags[f"{doc_name}_modified"] = modified
```

**Storage:** `scribe_projects.meta.docs.baseline_hashes`, `meta.docs.current_hashes`, `meta.docs.flags`

**Confidence:** 1.0

---

### Finding 2: BUG-001 Confirmed - Incorrect New Project Detection
**File:** `tools/set_project.py:459`

**Summary:** set_project uses `entry_count == 0` to detect new projects, which fails after log rotation.

**Evidence:**
```python
# Line 459: THE BUG
is_new = not progress_log_path.exists() or entry_count == 0

# Lines 36-58: _count_log_entries()
# Counts timestamp-prefixed lines - returns 0 after rotation
pattern = re.compile(r'^\[\d{4}-\d{2}-\d{2}')
return sum(1 for line in content.split('\n') if pattern.match(line.strip()))
```

**Reproduction Steps:**
1. Create project with set_project() → triggers NEW SITREP
2. Add entries via append_entry() → entry_count > 0
3. Call rotate_log() → PROGRESS_LOG.md becomes empty
4. Call set_project() again → entry_count == 0 → **INCORRECTLY shows NEW SITREP**

**Expected:** Should show EXISTING PROJECT SITREP (unchanged or modified based on doc hashes)

**Confidence:** 1.0

---

### Finding 3: list_projects Has TODO Comment Acknowledging Missing Implementation
**File:** `tools/list_projects.py:89`

**Summary:** The `modified` field exists in document inventory but is hardcoded to `False` with explicit TODO.

**Evidence:**
```python
# Line 89
result["architecture"] = {
    "exists": True,
    "lines": default_formatter._get_doc_line_count(arch_file),
    "modified": False  # TODO: Check against registry hashes if needed
}
```

**Implication:** Developer awareness that registry hashes should be used, but never implemented.

**Confidence:** 1.0

---

### Finding 4: get_project Also Ignores Hash Data
**File:** `tools/get_project.py:315-321`

**Summary:** get_project calls `ProjectRegistry.get_project()` but only extracts activity metrics, not hash flags.

**Evidence:**
```python
# Line 315: Calls get_project but...
registry_info = _PROJECT_REGISTRY.get_project(current_name)

# Lines 317-321: ...only uses activity data
activity_summary = {
    "total_entries": registry_info.total_entries,
    "last_entry_at": registry_info.last_entry_at,
    "status": registry_info.status
}
# IGNORES: registry_info.meta.docs.flags
```

**Confidence:** 1.0

---

### Finding 5: Hash Lifecycle Gap for New Projects
**File:** `tools/generate_doc_templates.py`

**Summary:** Template generation does NOT call `record_doc_update`, so new projects have no baseline hashes until first `manage_docs` call.

**Evidence:** Searched for `record_doc_update` in generate_doc_templates.py → 0 matches

**Implication:** Truly new projects need special handling. Detection logic should be:
- **NEW**: No database row OR no baseline hashes exist
- **UNCHANGED**: Baseline hashes exist AND baseline == current
- **MODIFIED**: Baseline hashes exist AND baseline != current

**Confidence:** 1.0

---

### Finding 6: ProjectInfo Fully Exposes Hash Data
**File:** `shared/project_registry.py:513-600`

**Summary:** ProjectInfo.meta contains complete docs metadata including flags.

**Evidence:**
```python
# Lines 519-527: Meta parsing
meta_raw = row["meta"]
if meta_raw:
    meta = json.loads(meta_raw)  # Full structure exposed

# Line 579-581: Flags accessible
docs_meta = (meta.get("docs") or {}).copy()
flags = (docs_meta.get("flags") or {}).copy()
```

**Access Path:** `registry_info.meta.docs.flags.architecture_modified` → `True/False`

**Confidence:** 1.0

---

### Finding 7: SITREP Formatters Have Two States, Need Three
**File:** `utils/response.py:1646-1820`

**Summary:** Current implementation has `format_project_sitrep_new` and `format_project_sitrep_existing` but no distinction for modified vs unchanged.

**Evidence:**
- Lines 1646-1729: format_project_sitrep_new() → "NEW PROJECT CREATED"
- Lines 1731-1820: format_project_sitrep_existing() → "PROJECT ACTIVATED"
- Inventory dict has `modified` field (line 1747) but it's always False

**Needed:** SITREP should indicate document modification status in existing project view.

**Confidence:** 1.0

---

## Technical Analysis
<!-- ID: technical_analysis -->

### Hash Lifecycle Documentation

**1. Template Generation (set_project → generate_doc_templates)**
- Creates ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md, PROGRESS_LOG.md
- **Does NOT** call record_doc_update()
- **Result:** No baseline hashes recorded

**2. First manage_docs Call**
- Computes before_hash (file content SHA256) and after_hash
- Calls `ProjectRegistry.record_doc_update(before_hash, after_hash)`
- **Sets baseline** if `doc not in baseline_map` (line 229)
- **Sets current** always (line 232)
- **Result:** Baseline hashes now exist

**3. Subsequent manage_docs Calls**
- Baseline remains unchanged (line 229 condition prevents overwrite)
- Current updated to new hash
- Flags recomputed: `modified = baseline != current` (line 245-248)

**4. Query Time (set_project/get_project/list_projects)**
- Calls `ProjectRegistry.get_project(name)` → returns `ProjectInfo`
- `ProjectInfo.meta.docs.flags` contains:
  - `architecture_modified`, `phase_plan_modified`, `checklist_modified`
  - `docs_started`, `docs_ready_for_work` (aggregate flags)
- **Current bug:** Tools don't read these flags

### Code Patterns Identified

**Pattern 1: Unused Infrastructure**
- Hash tracking fully implemented
- Modification flags computed
- Tools ignore this data and use primitive entry_count logic instead

**Pattern 2: Direct sqlite3 Usage**
- ProjectRegistry bypasses storage abstraction (noted in audit)
- Uses `sqlite3.connect()` directly at line 203, 284, 436
- Out of scope for this fix but noted as technical debt

**Pattern 3: TODO Comments as Design Intent**
- list_projects.py:89 TODO indicates developer knew about registry hashes
- Never implemented → technical debt

### System Interactions

**Data Flow:**
```
manage_docs (tools/manage_docs.py:1519)
    ↓ calls record_doc_update(before_hash, after_hash)
ProjectRegistry.record_doc_update() (shared/project_registry.py:187)
    ↓ stores in scribe_projects.meta
    ↓ computes flags
SQLite Database (scribe_projects table)
    ↓ queried by
ProjectRegistry.get_project() (shared/project_registry.py:282)
    ↓ returns ProjectInfo with meta.docs.flags
Tools (set_project/get_project/list_projects)
    ↓ CURRENTLY: ignore flags, use entry_count
    ↓ SHOULD: read flags for state detection
```

### Risk Assessment

**Risk 1: Baseline Hash Gap for New Projects**
- **Impact:** Cannot distinguish "truly new" from "templates created but never edited"
- **Mitigation:** Check for both database row absence AND baseline hash absence

**Risk 2: Manual File System Changes**
- **Impact:** If user edits files outside manage_docs, hashes won't update
- **Mitigation:** Accept as limitation; document that hash tracking requires manage_docs usage

**Risk 3: Baseline Reset Semantics**
- **Impact:** No mechanism to "reset baseline" after major refactor
- **Mitigation:** Could add optional `reset_baseline=True` parameter to manage_docs (future enhancement)

---

## Correct Architecture Design
<!-- ID: architecture_design -->

### Three-State Detection Logic

**State 1: NEW PROJECT**
```python
# Condition: No database row OR no baseline hashes exist
registry_info = _PROJECT_REGISTRY.get_project(name)
if not registry_info:
    state = "NEW"
else:
    baseline_hashes = registry_info.meta.get("docs", {}).get("baseline_hashes", {})
    if not baseline_hashes:
        state = "NEW"
```

**State 2: EXISTING - UNCHANGED**
```python
# Condition: Baseline hashes exist AND no documents modified
flags = registry_info.meta.get("docs", {}).get("flags", {})
core_docs = ["architecture", "phase_plan", "checklist"]
any_modified = any(flags.get(f"{doc}_modified", False) for doc in core_docs)
if not any_modified:
    state = "UNCHANGED"
```

**State 3: EXISTING - MODIFIED**
```python
# Condition: Baseline hashes exist AND at least one document modified
if any_modified:
    state = "MODIFIED"
    modified_docs = [doc for doc in core_docs if flags.get(f"{doc}_modified", False)]
```

### Implementation Changes Required

**File: tools/set_project.py**
- **Line 459:** Replace `entry_count == 0` logic with hash-based detection
- **Lines 461-489:** Update NEW vs EXISTING conditional to handle three states
- **Lines 495-502:** Enhance registry_info usage to extract flags

**File: tools/get_project.py**
- **Lines 315-321:** Add hash flags to activity_summary
- **Line 324:** Pass modification state to formatter

**File: tools/list_projects.py**
- **Lines 84-106:** Replace `"modified": False` with actual hash comparison
- Read registry_info for each project
- Extract per-doc modified flags

**File: utils/response.py**
- **No changes required** - existing formatters can display modified status if provided
- Optional: Add visual indicator for modified docs in inventory section

### Edge Case Handling

**Edge Case 1: Project Exists But No Docs Generated**
- **Scenario:** Database row exists but generate_doc_templates never called
- **Detection:** Check if doc files exist on filesystem
- **State:** Treat as NEW (no baseline hashes anyway)

**Edge Case 2: Documents Deleted After Creation**
- **Scenario:** Files deleted manually but database row persists
- **Detection:** File existence check before hash comparison
- **State:** Report as error or warning in SITREP

**Edge Case 3: Log Rotated But Docs Unchanged**
- **Scenario:** Progress log empty but architecture docs untouched
- **Detection:** entry_count == 0 BUT baseline_hashes exist and match current
- **State:** UNCHANGED (this is the PRIMARY fix for BUG-001)

**Edge Case 4: Hash Computation Failure**
- **Scenario:** manage_docs fails to compute hash for some reason
- **Detection:** before_hash or after_hash is None
- **Fallback:** Don't update hashes, log warning

---

## SITREP Message Specifications
<!-- ID: sitrep_messages -->

### NEW Project Messages

**Header:** `🆕 NEW PROJECT CREATED: <project_name>`

**Indicator:**
- "Status: planning (new project)"
- "Documents Created: [list with (template, N lines)]"
- "Next: Start with research or architecture phase"

**Detection:** `not registry_info OR not baseline_hashes`

---

### EXISTING - UNCHANGED Project Messages

**Header:** `📌 PROJECT ACTIVATED: <project_name>`

**Indicator:**
- "Status: <status> (no document changes since last baseline)"
- "Documents: ✓ All up-to-date"
- Optional: Show last_entry_at timestamp

**Detection:** `baseline_hashes exist AND no docs modified`

---

### EXISTING - MODIFIED Project Messages

**Header:** `📌 PROJECT ACTIVATED: <project_name>`

**Indicator:**
- "Status: <status> (documents modified since baseline)"
- "Modified Documents:"
  - "  ⚠️ ARCHITECTURE_GUIDE.md (baseline: abc123..., current: def456...)"
  - "  ⚠️ PHASE_PLAN.md (modified)"
- "Unchanged Documents:"
  - "  ✓ CHECKLIST.md"

**Detection:** `baseline_hashes exist AND any doc modified`

**Purpose:** Alert user that architectural documents have changed, may need review

---

## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps

**Phase 1: Fix set_project.py (BUG-001)**
- [ ] Replace line 459 logic with hash-based detection
- [ ] Extract `registry_info.meta.docs.flags`
- [ ] Implement three-state conditional (NEW/UNCHANGED/MODIFIED)
- [ ] Test with rotated logs to confirm fix

**Phase 2: Fix get_project.py**
- [ ] Add hash flags to activity_summary
- [ ] Pass modification state to formatter
- [ ] Update readable format output to show modified docs

**Phase 3: Fix list_projects.py**
- [ ] Replace hardcoded `"modified": False` at lines 89, 97, 105
- [ ] Read registry_info for each project
- [ ] Extract per-doc modified flags from meta.docs.flags

**Phase 4: Testing**
- [ ] Test new project creation → should show NEW
- [ ] Test existing unchanged project → should show UNCHANGED
- [ ] Test modified project → should show MODIFIED with doc list
- [ ] Test rotated log → should NOT show NEW (primary bug fix)

**Phase 5: Documentation**
- [ ] Update tool docstrings to explain three-state detection
- [ ] Document that hash tracking requires manage_docs usage
- [ ] Add example SITREP outputs to docs

### Long-Term Opportunities

**Enhancement 1: Baseline Reset Mechanism**
- Add `reset_baseline=True` parameter to manage_docs
- Useful after major refactors when "modified" state is no longer meaningful
- Copies current_hashes to baseline_hashes

**Enhancement 2: File System Hash Sync**
- Periodic background task to compute hashes of actual files
- Detect manual edits outside manage_docs
- Update current_hashes automatically

**Enhancement 3: Hash Diff Visualization**
- Show actual content differences when docs are modified
- Integration with git diff or custom diff algorithm
- Display in SITREP or via dedicated tool

**Enhancement 4: Cross-Project Hash Deduplication**
- Detect if multiple projects have identical architecture patterns
- Suggest template extraction or shared documentation
- Use hash similarity metrics

---

## Integration with docs_json Infrastructure
<!-- ID: docs_json_integration -->

**Clarification:** `docs_json` and `meta.docs` are SEPARATE fields in `scribe_projects` table.

**docs_json Purpose:**
- Stores document path mappings (which docs exist for a project)
- JSON structure: `{"architecture": "/path/to/ARCHITECTURE_GUIDE.md", ...}`
- Used for document discovery and validation

**meta.docs Purpose:**
- Stores hash tracking and modification flags
- JSON structure: `{"baseline_hashes": {...}, "current_hashes": {...}, "flags": {...}}`
- Used for state detection and change tracking

**No Conflict:** Both fields coexist. This fix uses `meta.docs`, not `docs_json`.

---

## Appendix
<!-- ID: appendix -->

### Files Investigated (with Key Lines)

1. **tools/set_project.py** - BUG-001 location
   - Line 459: `is_new = not progress_log_path.exists() or entry_count == 0`
   - Lines 36-58: `_count_log_entries()` function
   - Lines 495-502: Registry usage (ignores flags)

2. **tools/get_project.py** - No hash usage
   - Lines 315-321: Registry call but only activity metrics

3. **tools/list_projects.py** - TODO comment
   - Line 89: `"modified": False  # TODO: Check against registry hashes`

4. **shared/project_registry.py** - Hash infrastructure
   - Lines 187-280: `record_doc_update()` with hash storage
   - Lines 226-234: Baseline/current hash storage
   - Lines 245-251: Modification flag computation
   - Lines 282-324: `get_project()` returns ProjectInfo with meta
   - Lines 513-600: `_row_to_project_info()` exposes meta

5. **tools/manage_docs.py** - Hash recording trigger
   - Lines 1519-1525: Calls `record_doc_update(before_hash, after_hash)`

6. **utils/response.py** - SITREP formatters
   - Lines 1646-1729: `format_project_sitrep_new()`
   - Lines 1731-1820: `format_project_sitrep_existing()`

7. **storage/sqlite.py** - docs_json column
   - Lines 659, 1212-1316: Separate concern from meta.docs

### References

- **BUG-001 Original Audit:** "set_project bug (Line 459): Incorrectly marks empty logs as new (entry_count == 0 logic)"
- **ProjectRegistry Hash Tracking:** Implemented in scribe_manage_docs_implementation project
- **SITREP Formatter Design:** Established in scribe_tool_output_refinement project

### Code Snippets for Implementation

**Proposed Fix for set_project.py:459**
```python
# BEFORE (BROKEN):
is_new = not progress_log_path.exists() or entry_count == 0

# AFTER (CORRECT):
registry_info = _PROJECT_REGISTRY.get_project(name)
if not registry_info:
    is_new = True
else:
    baseline_hashes = registry_info.meta.get("docs", {}).get("baseline_hashes", {})
    flags = registry_info.meta.get("docs", {}).get("flags", {})
    is_new = not baseline_hashes  # No baseline = truly new

    # Determine modification state for existing projects
    if not is_new:
        core_docs = ["architecture", "phase_plan", "checklist"]
        any_modified = any(flags.get(f"{doc}_modified", False) for doc in core_docs)
        is_modified = any_modified
        modified_docs = [doc for doc in core_docs if flags.get(f"{doc}_modified", False)]
```

---

**Research Complete:** 2026-01-06 11:32:00 UTC
**Total Investigation Time:** ~1 hour
**Files Analyzed:** 7
**Log Entries:** 15+
**Confidence:** 1.0 (all findings code-verified)
