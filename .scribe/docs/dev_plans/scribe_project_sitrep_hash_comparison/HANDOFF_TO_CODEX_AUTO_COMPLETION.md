# HANDOFF TO CODEX: Automatic Project Completion Logic

## Current State

**Working:**
- ✅ Database migrations fixed (all 18 columns now exist)
- ✅ Entry count working (148 entries showing correctly)
- ✅ Auto-promotion `planning → in_progress` exists (lines 104-130 in `shared/project_registry.py`)

**Broken:**
- ❌ Project `scribe_project_sitrep_hash_comparison` stuck at status="planning"
- ❌ Should be status="complete" (Review Agent approved 100/100, all tests passing)
- ❌ No automatic promotion logic for `in_progress → complete`

## The Issue

**File:** `/home/austin/projects/MCP_SPINE/scribe_mcp/shared/project_registry.py`

The `touch_entry()` method (lines 97-164) handles auto-promotion from `planning → in_progress`, but **there's NO logic to auto-promote to `complete`**.

## What Needs to Be Built

**Add automatic status promotion logic** that detects when a project is complete and auto-updates the status.

### Detection Criteria (choose ONE or combine):

**Option 1: Detect from progress log entries**
- When `append_entry` logs entry with metadata:
  - `final_grade >= 93` OR
  - `phase=protocol_complete` OR
  - `approval_status=APPROVED` OR
  - `project_status=ready_for_production`
- Auto-promote status to "complete"

**Option 2: Check checklist completion**
- Query checklist file for completion percentage
- If 100% complete → auto-promote to "complete"

**Option 3: Combine both**
- Check for review approval entries AND checklist completion

## Implementation Location

**File:** `/home/austin/projects/MCP_SPINE/scribe_mcp/shared/project_registry.py`

**Method:** `touch_entry()` (lines 97-164)

**Insert logic after line 147** (after the planning→in_progress promotion):

```python
# After line 147, add:

# Auto-promote: in_progress → complete
# Check if project status is in_progress and should be completed
if status == "in_progress":
    # Check for completion signals in the entry metadata
    # (You'll implement detection logic here based on Option 1, 2, or 3)

    # If completion detected:
    cursor.execute(
        "UPDATE scribe_projects SET status = ?, last_status_change = ? WHERE name = ?",
        ("complete", now, project_name),
    )
```

## Current Project Status

```bash
sqlite3 /home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/scribe.db \
  "SELECT name, status, phase FROM scribe_projects WHERE name='scribe_project_sitrep_hash_comparison';"
```

**Current:** `status=planning`
**Expected:** `status=complete`

## Test After Implementation

```python
# 1. Restart MCP server
# 2. Call set_project
mcp__scribe__set_project(name="scribe_project_sitrep_hash_comparison")

# Expected output should show:
# Status: complete (not planning)
```

## Key Files

- **Implementation:** `/home/austin/projects/MCP_SPINE/scribe_mcp/shared/project_registry.py` (line 147)
- **Test project:** `scribe_project_sitrep_hash_comparison` (has approval entry with final_grade=100)

## Progress Log Evidence

The project has these entries showing completion:
```
[✅] PROTOCOL COMPLETE ✅ - Review Agent graded implementation 100/100 (APPROVED FOR PRODUCTION)
| final_grade=100; verdict=APPROVED; project_status=ready_for_production
```

This metadata should trigger the auto-promotion to "complete".

## Additional Context: Recent Bug Fixes

**Fixed in this session:**
1. **Line 1184 in storage/sqlite.py:** Changed `row["name"]` to `row[1]` (PRAGMA table_info returns tuples, not Row objects)
2. **Lines 1079-1080 in storage/sqlite.py:** Removed DEFAULT clauses with unescaped quotes (caused SQL syntax errors that halted migrations)
3. **Line 413 in tools/get_project.py:** Fixed entry_count to fetch ProjectRecord first before calling backend.count_entries()

**These fixes enabled migrations to run successfully and add all missing database columns.**

---

**Goal:** Codex implements automatic status promotion logic so projects transition to "complete" automatically when approved, without manual intervention or new tools.
