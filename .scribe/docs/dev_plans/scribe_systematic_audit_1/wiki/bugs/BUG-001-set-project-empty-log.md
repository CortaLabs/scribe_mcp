# BUG-001: Empty Log Treated as New Project

**File**: `tools/set_project.py`
**Line**: 461
**Severity**: Medium
**Category**: Logic Error
**Status**: Confirmed
**Discovered By**: ResearchAgent-E-SetProject
**Date**: 2026-01-05

---

## Summary

The new/existing project detection logic in `set_project.py` incorrectly treats empty progress logs as "new" projects, triggering the wrong SITREP formatter and hiding valuable inventory/activity information.

---

## Root Cause

**File**: `tools/set_project.py`
**Lines**: 460-461

```python
# BUGGY CODE
entry_count = await _count_log_entries(progress_log_path)
is_new = not progress_log_path.exists() or entry_count == 0
                                           ^^^^^^^^^^^^^^^^^^
                                           This check is WRONG
```

**Issue**: The logic checks `entry_count == 0` to determine if a project is new. This fails for:
1. Rotated logs (empty file exists after `rotate_log()`)
2. Manually cleared logs (file exists but contains no entries)
3. Corrupted logs (file exists but entry counting fails)

**Canonical Signal**: File existence is the ONLY reliable indicator of "has this project been used before". Entry count is irrelevant for this decision.

---

## Impact

### User Experience
- Misleading output confuses users and agents about project state
- "NEW PROJECT CREATED" message when project already exists
- Loss of inventory information (research files, bugs, custom logs)
- Loss of activity summary (entry counts, last_entry_at timestamps)

### Data Loss
- Inventory gathering is bypassed for existing projects with empty logs
- Users don't see research files, TOOL_LOG.jsonl, or other custom content
- Activity metrics (total entries, last entry time) are hidden
- Per-log counts (progress/doc_updates/bugs) not displayed

### Token Impact
- Existing SITREP (~280-320 tokens) provides more context than new SITREP (~198 tokens)
- Paradoxically, bug REDUCES token usage by showing less useful information

---

## Reproduction Steps

### Automated Reproduction
```python
# Step 1: Create project
await set_project(name="test_bug_001")

# Step 2: Add entry to make it "used"
await append_entry(message="Test entry", project="test_bug_001")

# Step 3: Rotate log (creates empty PROGRESS_LOG.md file)
await rotate_log(project="test_bug_001", confirm=True)

# Step 4: Call set_project again
result = await set_project(name="test_bug_001", format="readable")

# BUG: result["is_new"] == True (should be False)
# BUG: No "inventory" key in response (should have inventory)
# BUG: readable_content shows "✨ NEW PROJECT CREATED" (should show "📂 PROJECT ACTIVATED")
```

### Manual Reproduction
1. Create a new project via MCP: `set_project(name="reproduction_test")`
2. Add at least one log entry: `append_entry(message="First entry")`
3. Rotate the progress log: `rotate_log(confirm=True)`
   - This creates an empty `PROGRESS_LOG.md` file
   - Archive contains old entries, but active log is empty
4. Call `set_project` again: `set_project(name="reproduction_test")`
5. **Observe**: Output shows "✨ NEW PROJECT CREATED" instead of "📂 PROJECT ACTIVATED"
6. **Observe**: No inventory section (research files, etc. are hidden)

---

## Expected vs Actual Behavior

### Expected (Correct)
```
╔══════════════════════════════════════════════════════════╗
║ 📂 PROJECT ACTIVATED: reproduction_test                  ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/reproduction_test/

📊 Documentation Inventory:
  ✓ ARCHITECTURE_GUIDE.md (768 lines)
  ✓ PHASE_PLAN.md (922 lines)
  ✓ CHECKLIST.md (322 lines)
  ✓ PROGRESS_LOG.md (0 entries, recently rotated)

📈 Activity Summary:
  Status: in_progress
  Total Entries: 1 (in archived logs)
  Last Entry: <timestamp>

🎯 Status: in_progress
```

### Actual (Bug)
```
╔══════════════════════════════════════════════════════════╗
║ ✨ NEW PROJECT CREATED: reproduction_test                ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/reproduction_test/

📄 Documents Created:
  ✓ ARCHITECTURE_GUIDE.md (template, 768 lines)
  ✓ PHASE_PLAN.md (template, 922 lines)
  ✓ CHECKLIST.md (template, 322 lines)
  ✓ PROGRESS_LOG.md (empty, ready for entries)

🎯 Status: planning (new project)
```

**Key Differences**:
1. Header: "NEW PROJECT CREATED" vs "PROJECT ACTIVATED"
2. Section: "Documents Created" vs "Documentation Inventory"
3. Missing: Activity summary completely absent
4. Wrong: Status shows "planning" instead of "in_progress"

---

## Fix Specification

### ⚠️ CRITICAL: ORIGINAL ANALYSIS WAS INCORRECT

**Agent E's Proposed Fix (WRONG)**:
```python
is_new = not progress_log_path.exists()
```

**Why This Fix FAILS**:
1. `set_project.py` line 246 calls `_ensure_documents()`
2. Line 667 calls `generate_doc_templates()` which **CREATES** `PROGRESS_LOG.md`
3. After template creation, `progress_log_path.exists()` is **ALWAYS True**
4. Using `is_new = not progress_log_path.exists()` means `is_new` is **ALWAYS False** after first call
5. **Result**: Every project would show as "existing" even on first creation (complete breakage)

### CORRECT FIX: Hash Comparison Architecture

**Infrastructure Already Exists**:
- `ProjectRegistry.record_doc_update()` (shared/project_registry.py:227-234) tracks:
  - `baseline_hashes`: Hash when doc first created from template
  - `current_hashes`: Hash after each modification

**Correct Detection Logic**:
```python
# When docs first created from templates
baseline_hash = hash(template_content)  # Pristine state

# When docs modified
current_hash = hash(modified_content)

# Detection
if baseline_hash == current_hash:
    # Docs are still templates (pristine) → "new" project
    is_new = True
else:
    # Docs have been modified → "existing" project
    is_new = False
```

**The Problem**:
`generate_doc_templates.py` does **NOT** call `record_doc_update()` to record baseline hashes when it creates templates. The infrastructure exists but isn't wired up.

### Required Changes

**File**: `tools/generate_doc_templates.py`
**Lines**: 220-224 (after template write)
**Change Type**: Integration - wire up existing infrastructure

#### Add After Template Write
```python
# After line 221: await asyncio.to_thread(_write_template, path, rendered, force_overwrite)
written.append(str(path))

# NEW: Record baseline hash for doc lifecycle tracking
try:
    content_hash = hashlib.sha256(rendered.encode('utf-8')).hexdigest()
    _PROJECT_REGISTRY.record_doc_update(
        project_name,
        doc=key,  # "architecture", "phase_plan", "checklist", "progress_log"
        action="template_created",
        before_hash=None,
        after_hash=content_hash,
    )
except Exception:
    pass  # Best-effort, don't fail template generation
```

**File**: `tools/set_project.py`
**Lines**: 456-461
**Change Type**: Use ProjectRegistry hash comparison

#### Replace Detection Logic
```python
# OLD (BROKEN):
entry_count = await _count_log_entries(progress_log_path)
is_new = not progress_log_path.exists() or entry_count == 0

# NEW (CORRECT):
from scribe_mcp.shared.project_registry import ProjectRegistry
registry = ProjectRegistry()
info = registry.get_project(name)

if info and info.meta:
    docs_meta = info.meta.get("docs", {})
    baseline_hashes = docs_meta.get("baseline_hashes", {})
    current_hashes = docs_meta.get("current_hashes", {})

    # Check if ANY core doc has been modified
    core_docs = {"architecture", "phase_plan", "checklist"}
    is_new = all(
        baseline_hashes.get(doc) == current_hashes.get(doc)
        for doc in core_docs
        if doc in baseline_hashes
    ) if baseline_hashes else not progress_log_path.exists()
else:
    # Fallback for projects without registry data
    is_new = not progress_log_path.exists()
```

### Semantic Distinction

**What We're Actually Detecting**:
- **NOT**: "Does the file exist?" (wrong question)
- **NOT**: "Are there log entries?" (wrong question)
- **CORRECT**: "Has this project been worked on?" (right question)

**Detection Methods**:
1. ❌ File existence - fails because templates are created immediately
2. ❌ Entry count - fails after rotation or manual clearing
3. ✅ Hash comparison - correctly distinguishes pristine templates from modified docs
4. ✅ Lifecycle state - alternative using ProjectRegistry status field

---

## Testing Requirements

### Unit Test
```python
async def test_bug_001_empty_log_shows_existing_sitrep():
    """
    BUG-001 Regression Test: Rotated/empty logs should show existing SITREP.

    Verifies that projects with empty progress logs (after rotation or manual
    clearing) are correctly identified as existing, not new.
    """
    # Create project
    result1 = await set_project(name="test_bug_001_regression")
    assert result1["is_new"] == True  # First call is genuinely new

    # Add entry to make it "used"
    await append_entry(message="Test entry", project="test_bug_001_regression")

    # Rotate log (creates empty file)
    await rotate_log(project="test_bug_001_regression", confirm=True)

    # Verify log is empty but exists
    log_path = Path(".scribe/docs/dev_plans/test_bug_001_regression/PROGRESS_LOG.md")
    assert log_path.exists()
    entry_count = await _count_log_entries(log_path)
    assert entry_count == 0  # Empty after rotation

    # Call set_project again - THIS IS THE TEST
    result2 = await set_project(name="test_bug_001_regression", format="readable")

    # FIXED BEHAVIOR (previously failed)
    assert result2["is_new"] == False, "Empty log should NOT be treated as new project"
    assert "inventory" in result2, "Existing project should have inventory"
    assert "📂 PROJECT ACTIVATED" in result2["readable_content"]
    assert "✨ NEW PROJECT CREATED" not in result2["readable_content"]
```

### Integration Test
```python
async def test_bug_001_manual_clearing():
    """
    BUG-001 Edge Case: Manually cleared logs should still show existing SITREP.
    """
    # Create and populate project
    await set_project(name="test_manual_clear")
    await append_entry(message="Entry 1")
    await append_entry(message="Entry 2")

    # Manually clear log (simulate user action)
    log_path = Path(".scribe/docs/dev_plans/test_manual_clear/PROGRESS_LOG.md")
    with open(log_path, 'w') as f:
        f.write("# PROGRESS_LOG\n\n")  # Empty header only

    # Call set_project
    result = await set_project(name="test_manual_clear", format="readable")

    # Should still be existing project
    assert result["is_new"] == False
    assert "inventory" in result
```

### Verification Checklist
- [ ] Unit test passes (empty log after rotation)
- [ ] Integration test passes (manually cleared log)
- [ ] New project still works (`is_new=True` when file doesn't exist)
- [ ] Inventory gathering works for empty logs (entry_count variable used correctly)
- [ ] Both SITREP formatters tested (new and existing)

---

## Related Issues

### Similar Pattern Search
Checked for similar `entry_count == 0` logic in other tools:
- `list_projects.py`: ❌ Not present
- `get_project.py`: ❌ Not present
- `append_entry.py`: ❌ Not present
- `rotate_log.py`: ✅ Uses entry count but correctly (for rotation threshold, not existence check)

**Conclusion**: This bug is isolated to `set_project.py` line 461. No other tools use entry count for project existence detection.

---

## Recommended Improvements (Future)

### 1. Add Rotation Metadata to SITREP
When log is empty due to rotation, show rotation info:
```
✓ PROGRESS_LOG.md (0 entries, rotated 2026-01-04 18:30:00 UTC)
```

### 2. Expose Archived Entry Counts
If rotation state is tracked, show total across archives:
```
📈 Activity Summary:
  Status: in_progress
  Total Entries: 127 (0 current, 127 archived)
  Last Rotation: 2026-01-04 18:30:00 UTC
```

### 3. Consider File Modification Time
Additional signal for "recently used":
```python
# Future enhancement (not required for fix)
if progress_log_path.exists():
    mtime = progress_log_path.stat().st_mtime
    is_recent = (time.time() - mtime) < 86400  # < 24 hours
```

---

## Verification Evidence

### Code Analysis
- **Line 461**: Confirmed boolean expression includes `entry_count == 0`
- **Line 494**: Confirmed `inventory = await _gather_project_inventory(project_data)` is only called in existing branch
- **Lines 463-489**: New SITREP path (no inventory gathering)
- **Lines 491-531**: Existing SITREP path (includes inventory + activity)

### Logic Trace
1. `_count_log_entries()` (line 460) counts lines matching `^\[\d{4}-\d{2}-\d{2}` pattern
2. Empty file returns `0` (no matches)
3. `is_new = not exists() or count == 0` evaluates to `True` (BUG)
4. Code takes new SITREP path (lines 463-489)
5. Inventory gathering skipped
6. User sees incorrect "NEW PROJECT CREATED" message

### Historical Context
This logic was likely introduced to handle:
- Truly new projects (file doesn't exist)
- Template-only projects (file exists but never used)

However, it conflates "never used" with "empty after rotation" - these are distinct states.

---

## Sign-off

**Confirmed By**: ResearchAgent-E-SetProject
**Audit Date**: 2026-01-05
**Evidence Level**: High (code analysis + reproduction steps + test spec)
**Fix Complexity**: Trivial (single line change)
**Regression Risk**: Low (existing tests should catch breaks)
**Review Required**: Yes (before implementation)

---

## Implementation Tracking

**Spec File**: `SPEC-SET-001-bug-fix.yaml` (see separate file)
**Target Phase**: Phase 6 (Modularization & Bug Fixes)
**Blocked By**: None
**Dependencies**: None (can be fixed independently)
**Estimated Time**: 30 minutes (fix + test + verification)
