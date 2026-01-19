# Template Lifecycle Integration Analysis — BUG-001 Architecture

**Analysis ID**: template_lifecycle_integration
**Related Bug**: BUG-001-set-project-empty-log
**Analyst**: ResearchAgent-I-GenTemplates
**Date**: 2026-01-05
**Status**: Complete

---

## Executive Summary

This analysis documents the **complete template lifecycle** in Scribe MCP and explains how the missing ProjectRegistry integration in `generate_doc_templates.py` causes BUG-001. The fix requires a **3-line integration** to enable correct "new vs existing project" detection in `set_project.py`.

**Key Finding**: The infrastructure for hash-based project state detection exists and is operational in `manage_docs.py`, but `generate_doc_templates.py` was never wired up to record baseline hashes when creating templates.

---

## Template Lifecycle Stages

### Stage 1: Template Creation (generate_doc_templates.py)

**Entry Point**: `set_project.py` line 667 calls `generate_doc_templates()`

**Current Flow**:
```
1. Select documents to generate (line 127)
   └─> [architecture, phase_plan, checklist, progress_log, ...]

2. Render each template (lines 188 or 213)
   └─> Jinja2: engine.render_template(template_name, metadata)
   └─> Legacy: _render_template(template_body, context)

3. Write to filesystem (line 222)
   └─> await asyncio.to_thread(_write_template, path, rendered, force_overwrite)

4. Record file path (line 223)
   └─> written.append(str(path))

5. Return response (lines 241-257)
   └─> {"ok": True, "files": [...], ...}
```

**Missing Step** 🚨 **Between lines 222-223**:
```python
# SHOULD BE HERE:
content_hash = hashlib.sha256(rendered.encode('utf-8')).hexdigest()
_PROJECT_REGISTRY.record_doc_update(
    project_name,
    doc=key,
    action="template_created",
    before_hash=content_hash,  # Set baseline
    after_hash=content_hash,   # Pristine state
)
```

**Impact**: Without this step, ProjectRegistry has **NO baseline_hashes** for the project.

---

### Stage 2: Template Modification (manage_docs.py)

**Entry Point**: User or agent calls `manage_docs(action="replace_section", ...)`

**Current Flow** (WORKS CORRECTLY):
```
1. Load existing document
   └─> before_content = path.read_text()
   └─> before_hash = hashlib.sha256(before_content.encode('utf-8')).hexdigest()

2. Apply edit (replace_section, append, etc.)
   └─> after_content = apply_edit(before_content, edit)
   └─> after_hash = hashlib.sha256(after_content.encode('utf-8')).hexdigest()

3. Write modified document
   └─> atomic_write(path, after_content)

4. Record hash change in ProjectRegistry (line 1343)
   └─> _PROJECT_REGISTRY.record_doc_update(
           project_name,
           doc=doc,
           action=action,
           before_hash=before_hash,
           after_hash=after_hash,
       )
```

**ProjectRegistry Behavior** (shared/project_registry.py:227-234):
```python
baseline_map = docs_meta.get("baseline_hashes") or {}
current_map = docs_meta.get("current_hashes") or {}

# Line 229: Set baseline ONLY if not already set
if doc not in baseline_map and before_hash:
    baseline_map[doc] = before_hash

# Line 232: Always update current hash
if after_hash:
    current_map[doc] = after_hash
```

**For existing project with baseline**:
- `baseline_map["architecture"]` remains unchanged (original template hash)
- `current_map["architecture"]` = new hash after modification
- **Result**: `baseline != current` → project has been worked on

**For new project WITHOUT baseline** (current bug):
- `baseline_map = {}` (empty, because generate_doc_templates didn't record)
- `current_map["architecture"]` = hash after first modification
- **Result**: No baseline to compare against → detection logic fails

---

### Stage 3: Project State Detection (set_project.py)

**Entry Point**: User calls `set_project(name="project")`

**Current Flow** (BUGGY):
```python
# Line 460-461 (CURRENT BUGGY CODE)
entry_count = await _count_log_entries(progress_log_path)
is_new = not progress_log_path.exists() or entry_count == 0
```

**Problems**:
1. **Rotated logs**: After `rotate_log()`, progress log is empty but project is NOT new
2. **Manually cleared logs**: User clears log, but project is NOT new
3. **Wrong semantic**: Checks "does log have entries" not "has project been worked on"

**Correct Flow** (AFTER FIX):
```python
# NEW CORRECT CODE (uses hash comparison)
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

**Logic**:
- If `baseline_hashes` exists and ALL core docs have `baseline == current` → **new** (pristine templates)
- If ANY core doc has `baseline != current` → **existing** (modified)
- If no baseline_hashes → fallback to file existence (legacy behavior)

**Why This Works**:
- **New project**: generate_doc_templates records baseline = current = template hash
- **Modified project**: manage_docs changes current hash, baseline stays same
- **Empty log project**: baseline != current even if log is empty (docs were modified)

---

## Hash Lifecycle Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ USER ACTION: set_project(name="my_project")                 │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Template Creation (generate_doc_templates)         │
├─────────────────────────────────────────────────────────────┤
│ 1. Render template                                           │
│    rendered = "# Architecture Guide..."                      │
│                                                              │
│ 2. Compute hash                                              │
│    template_hash = SHA256(rendered)                          │
│    = "a1b2c3d4..."                                           │
│                                                              │
│ 3. Write to filesystem                                       │
│    ARCHITECTURE_GUIDE.md ← rendered                          │
│                                                              │
│ 4. ❌ MISSING: Record baseline hash                         │
│    ProjectRegistry.record_doc_update(                        │
│        "my_project",                                         │
│        doc="architecture",                                   │
│        before_hash="a1b2c3d4",  # Baseline = pristine        │
│        after_hash="a1b2c3d4",   # Current = pristine         │
│    )                                                         │
│                                                              │
│ ProjectRegistry State:                                       │
│   baseline_hashes: {}  ← EMPTY! BUG!                        │
│   current_hashes: {}                                         │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │ TIME PASSES: User works       │
        └───────────────┬───────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: Template Modification (manage_docs)                │
├─────────────────────────────────────────────────────────────┤
│ 1. Load existing doc                                         │
│    before_content = "# Architecture Guide..."                │
│    before_hash = SHA256(before_content) = "a1b2c3d4"         │
│                                                              │
│ 2. Apply edit                                                │
│    after_content = "# Architecture Guide\n[MODIFIED]..."     │
│    after_hash = SHA256(after_content) = "e5f6g7h8"           │
│                                                              │
│ 3. Write modified doc                                        │
│    ARCHITECTURE_GUIDE.md ← after_content                     │
│                                                              │
│ 4. ✅ Record hash change (WORKS CORRECTLY)                  │
│    ProjectRegistry.record_doc_update(                        │
│        "my_project",                                         │
│        doc="architecture",                                   │
│        before_hash="a1b2c3d4",                               │
│        after_hash="e5f6g7h8",                                │
│    )                                                         │
│                                                              │
│ ProjectRegistry State:                                       │
│   baseline_hashes: {architecture: "a1b2c3d4"}  ← Set now!   │
│   current_hashes:  {architecture: "e5f6g7h8"}                │
│                                                              │
│ Problem: baseline set on FIRST EDIT, not template creation  │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │ USER ACTION: rotate_log()     │
        │ (empties PROGRESS_LOG.md)     │
        └───────────────┬───────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: Project State Detection (set_project)              │
├─────────────────────────────────────────────────────────────┤
│ CURRENT BUGGY LOGIC:                                         │
│   entry_count = count_log_entries()  = 0 (after rotation)   │
│   is_new = entry_count == 0          = TRUE ❌ WRONG!       │
│   → Shows "NEW PROJECT CREATED" (misleading)                 │
│                                                              │
│ CORRECT LOGIC (with hash comparison):                        │
│   baseline = baseline_hashes["architecture"] = "a1b2c3d4"    │
│   current  = current_hashes["architecture"]  = "e5f6g7h8"    │
│   is_new = (baseline == current)             = FALSE ✅      │
│   → Shows "PROJECT ACTIVATED" (correct)                      │
│                                                              │
│ Why it works:                                                │
│   - Empty log is irrelevant                                  │
│   - Hash comparison shows docs HAVE been modified            │
│   - Semantic: "has project been worked on?" answered via     │
│     document modification state, not log entry count         │
└─────────────────────────────────────────────────────────────┘
```

---

## Why the Current Implementation is Incomplete

### The Integration Gap

**What Exists**:
- ✅ `ProjectRegistry.record_doc_update()` infrastructure (shared/project_registry.py:227-234)
- ✅ Hash tracking in `manage_docs.py` (line 1343)
- ✅ Hash comparison logic planned in `set_project.py` (BUG-001 spec)

**What's Missing**:
- ❌ Hash recording in `generate_doc_templates.py` (lines 221-223)
- ❌ Imports: `hashlib` and `ProjectRegistry`
- ❌ Module-level `_PROJECT_REGISTRY` instance

**Why This Matters**:
Without baseline hash recording at template creation:
1. **New projects**: No baseline → hash comparison impossible
2. **Existing projects**: baseline set on FIRST EDIT not template creation (wrong semantic)
3. **set_project**: Cannot distinguish pristine templates from modified docs

---

### The Semantic Mismatch

**Current (Buggy) Semantic**:
- "Is this a new project?" = "Does the progress log have entries?"
- **Wrong** because: Rotated/cleared logs are still existing projects

**Correct Semantic**:
- "Is this a new project?" = "Have the documentation templates been modified?"
- **Right** because: Pristine templates = never worked on, modified templates = project in use

**How Hash Comparison Fixes This**:
```
New project:     baseline == current (both = template hash) → TRUE
Existing project: baseline != current (docs modified)       → FALSE
Empty log:        irrelevant (hash comparison works anyway)
```

---

## Migration Considerations

### Existing Projects Without Baseline Hashes

**Problem**: Projects created before SPEC-GEN-001 implementation won't have `baseline_hashes`.

**Impact**:
```python
baseline_hashes = {}  # Empty for old projects
current_hashes = {architecture: "e5f6g7h8"}  # Only current hashes

# Comparison logic fails
is_new = all(baseline == current for ...)  # No baselines to compare!
```

**Solution 1: Fallback Logic** (Recommended)
```python
if baseline_hashes:
    # New behavior: hash comparison
    is_new = all(baseline == current for doc in core_docs if doc in baseline_hashes)
else:
    # Legacy behavior: file existence
    is_new = not progress_log_path.exists()
```

**Advantage**: Backward compatible, no migration required.

**Disadvantage**: Old projects still use buggy logic (but better than breaking them).

---

**Solution 2: Baseline Backfill Tool** (Phase 6 Enhancement)
```python
async def backfill_baseline_hashes(project_name: str) -> None:
    """
    Compute baseline hashes for existing projects by hashing current doc state.

    WARNING: This assumes current docs are PRISTINE templates (not modified).
    Only use for projects that haven't been worked on yet.
    """
    for doc_key in ["architecture", "phase_plan", "checklist"]:
        path = get_doc_path(project_name, doc_key)
        if path.exists():
            content = path.read_text()
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            _PROJECT_REGISTRY.record_doc_update(
                project_name,
                doc=doc_key,
                action="baseline_backfill",
                before_hash=content_hash,  # Assume pristine
                after_hash=content_hash,
            )
```

**Advantage**: All projects use new logic after migration.

**Disadvantage**: Requires manual migration step, risk of incorrect baseline if docs already modified.

---

**Solution 3: Hybrid Approach** (Best Practice)
```python
# Phase 6A: Deploy SPEC-GEN-001 (new projects get baselines automatically)
# Phase 6B: Add fallback logic to set_project (old projects use file existence)
# Phase 6C (Optional): Provide backfill tool for users who want consistent behavior
```

**Recommendation**: Use Solution 3 (hybrid approach).

---

## Testing Strategy

### Unit Test: Baseline Hash Recording
**File**: `tests/test_generate_doc_templates.py`

```python
async def test_baseline_hash_recorded_on_template_creation():
    """
    SPEC-GEN-001: Verify generate_doc_templates records baseline hashes.
    """
    from scribe_mcp.shared.project_registry import ProjectRegistry

    registry = ProjectRegistry()
    project = "test_baseline_recording"

    # Generate templates
    result = await generate_doc_templates(project_name=project)
    assert result["ok"] == True

    # Verify baseline hashes exist
    info = registry.get_project(project)
    baseline_hashes = info.meta["docs"]["baseline_hashes"]
    current_hashes = info.meta["docs"]["current_hashes"]

    # Core docs should have identical baseline and current hashes
    for doc in ["architecture", "phase_plan", "checklist"]:
        assert doc in baseline_hashes
        assert doc in current_hashes
        assert baseline_hashes[doc] == current_hashes[doc]  # Pristine
```

---

### Integration Test: set_project Detection
**File**: `tests/test_set_project_integration.py`

```python
async def test_hash_comparison_detects_modified_project():
    """
    Integration: Verify set_project uses hash comparison for detection.
    """
    project = "test_detection"

    # Step 1: Create project (should be "new")
    result1 = await set_project(name=project)
    assert result1["is_new"] == True

    # Step 2: Call again immediately (still "new" - docs pristine)
    result2 = await set_project(name=project)
    assert result2["is_new"] == True

    # Step 3: Modify a document
    await manage_docs(
        action="replace_section",
        doc="architecture",
        section="problem_statement",
        content="## Modified\nContent here\n"
    )

    # Step 4: Call set_project again (now "existing" - docs modified)
    result3 = await set_project(name=project)
    assert result3["is_new"] == False
    assert "inventory" in result3  # Existing project shows inventory
```

---

### Regression Test: BUG-001 Fixed
**File**: `tests/test_bug_001_regression.py`

```python
async def test_bug_001_empty_log_not_treated_as_new():
    """
    BUG-001 Regression: Empty logs after rotation show as "existing".
    """
    project = "test_bug_001"

    # Create and populate project
    await set_project(name=project)
    await append_entry(message="Work done", project=project)

    # Rotate log (creates empty PROGRESS_LOG.md)
    await rotate_log(project=project, confirm=True)

    # Verify log is empty
    log_path = Path(f".scribe/docs/dev_plans/{project}/PROGRESS_LOG.md")
    assert log_path.exists()
    entry_count = await _count_log_entries(log_path)
    assert entry_count == 0

    # Call set_project - should be "existing" despite empty log
    result = await set_project(name=project)
    assert result["is_new"] == False  # ✅ Fixed
    assert "inventory" in result  # ✅ Shows inventory
    assert "📂 PROJECT ACTIVATED" in result["readable_content"]  # ✅ Correct message
```

---

## Implementation Checklist

### Phase 1: Code Integration (SPEC-GEN-001)
- [ ] Add imports to generate_doc_templates.py (hashlib, ProjectRegistry)
- [ ] Create module-level `_PROJECT_REGISTRY` instance
- [ ] Insert hash recording code between lines 222-223
- [ ] Use `before_hash=content_hash, after_hash=content_hash` for pristine state

### Phase 2: set_project Logic Update
- [ ] Add hash comparison logic to set_project.py
- [ ] Implement fallback for projects without baseline_hashes
- [ ] Update SITREP formatters to handle hash-based detection

### Phase 3: Testing
- [ ] Unit test: baseline hash recording
- [ ] Integration test: set_project detection
- [ ] Regression test: BUG-001 fixed
- [ ] Manual test: Verify SQLite baseline_hashes populated

### Phase 4: Migration Planning
- [ ] Document fallback behavior for old projects
- [ ] (Optional) Create baseline backfill tool
- [ ] Update CHANGELOG.md with breaking change notes

---

## Conclusion

The template lifecycle integration gap is a **3-line fix** in `generate_doc_templates.py`:

1. Add imports
2. Create registry instance
3. Record hash after write

This enables correct project state detection in `set_project.py` using hash comparison instead of entry count, fixing BUG-001 and improving semantic accuracy.

**Critical Path**:
- SPEC-GEN-001 must be implemented FIRST (generate_doc_templates integration)
- Then SPEC-SET-001 can be implemented (set_project hash comparison)
- Without baseline hashes, hash comparison cannot work

**Risk**: Low (best-effort error handling, backward compatible fallback)

**Effort**: 2-3 hours implementation, 1-2 hours testing

---

**Analysis Complete**: ResearchAgent-I-GenTemplates, 2026-01-05
**Next Steps**: Phase 6 implementation of SPEC-GEN-001
