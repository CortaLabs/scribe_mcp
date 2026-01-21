# Phase Plan: Session Isolation & UX Fixes

**Project:** manage_docs_agent_ux
**Sub-Plan:** session_and_ux_fixes
**Created:** 2026-01-20
**Architect:** ArchitectAgent

---

## Phase Overview

| Phase | Focus | Est. Time | Risk | Dependency |
|-------|-------|-----------|------|------------|
| Phase 1 | Session Isolation Unification | 4-6 hours | HIGH | None |
| Phase 2 | Multi-Project Tool Parameters | 6-8 hours | MEDIUM | Phase 1 |
| Phase 3 | Custom Doc Naming Fix | 2-3 hours | LOW | None (parallel) |
| Phase 4 | Index Update Event Coverage | 4-6 hours | MEDIUM | None (parallel) |
| Phase 5 | Backup Location Cleanup | 3-4 hours | LOW | None (parallel) |

**Total Estimated Time:** 19-27 hours

---

## Phase 1: Session Isolation Unification (CRITICAL)

**Goal:** Create single canonical session key resolution function to prevent cross-project log contamination

**Research Reference:** RESEARCH_SESSION_ISOLATION_BUG_20260119.md

### Task Package 1.1: Create Session Utils Module

**Scope:** Add new utility module for unified session key resolution
**Files to Create:**
- `shared/session_utils.py`

**Files to Read (for context):**
- `shared/execution_context.py` (understand ExecutionContext structure)
- `tools/set_project.py` lines 510-516 (current session key logic)
- `shared/logging_utils.py` lines 88-95 (current session key logic)

**Specifications:**
1. Create `shared/session_utils.py` with single function:
   ```python
   from typing import Optional
   from scribe_mcp.shared.execution_context import ExecutionContext

   def get_canonical_session_key(exec_context: Optional[ExecutionContext]) -> Optional[str]:
       """Return THE canonical session key - stable_session_id always preferred.

       Args:
           exec_context: ExecutionContext with session_id and/or stable_session_id

       Returns:
           str: stable_session_id if available, else session_id, else None

       Design:
           - stable_session_id is DETERMINISTIC (same across MCP session)
           - session_id is EPHEMERAL (UUID per request)
           - Always prefer stable over ephemeral for project binding
       """
       if not exec_context:
           return None
       return exec_context.stable_session_id or exec_context.session_id
   ```

2. Add module docstring explaining purpose and usage
3. Add type hints for all parameters and return values
4. Keep module focused (single function, single purpose)

**Verification:**
- [ ] File created at `shared/session_utils.py`
- [ ] Function signature matches spec exactly
- [ ] Type hints present and correct
- [ ] Docstring explains stable vs ephemeral session IDs
- [ ] `python -m py_compile shared/session_utils.py` succeeds

**Out of Scope:**
- Do NOT modify any other files yet (that's next task)
- Do NOT add tests yet (separate task)
- Do NOT add validation logic beyond None check

---

### Task Package 1.2: Update set_project.py to Use Canonical Function

**Scope:** Replace inline session key logic in set_project with unified function
**Files to Modify:**
- `tools/set_project.py` (line ~513)

**Dependencies:** Task 1.1 complete

**Specifications:**
1. Add import at top of file:
   ```python
   from scribe_mcp.shared.session_utils import get_canonical_session_key
   ```

2. Replace lines 513 (current):
   ```python
   session_key = stable_session_id or context_session_id or session_id
   ```

   With (new):
   ```python
   session_key = get_canonical_session_key(exec_context)
   ```

3. Verify exec_context variable is available in scope (should be from line ~480)
4. Keep all other logic unchanged (backend call, error handling, etc.)

**Verification:**
- [ ] Import added at top of file
- [ ] Line 513 replaced with function call
- [ ] exec_context passed to function
- [ ] No other changes to set_project.py
- [ ] `python -m py_compile tools/set_project.py` succeeds
- [ ] Manual test: set_project() still works (MCP server restart required)

**Out of Scope:**
- Do NOT modify backend.set_session_project() call
- Do NOT change error handling
- Do NOT modify any other session-related logic

---

### Task Package 1.3: Update logging_utils.py to Use Canonical Function

**Scope:** Replace inline session key logic in logging_utils with unified function
**Files to Modify:**
- `shared/logging_utils.py` (lines 91-92)

**Dependencies:** Task 1.1 complete

**Specifications:**
1. Add import at top of file:
   ```python
   from scribe_mcp.shared.session_utils import get_canonical_session_key
   ```

2. Replace lines 91-92 (current):
   ```python
   session_key = getattr(exec_context, "stable_session_id", None) or getattr(exec_context, "session_id", None)
   ```

   With (new):
   ```python
   session_key = get_canonical_session_key(exec_context)
   ```

3. Verify exec_context variable is available in scope
4. Keep all other logic unchanged (backend.get_session_project call, debug logging, etc.)

**Verification:**
- [ ] Import added at top of file
- [ ] Lines 91-92 replaced with single function call
- [ ] exec_context passed to function
- [ ] No other changes to logging_utils.py
- [ ] `python -m py_compile shared/logging_utils.py` succeeds
- [ ] Manual test: append_entry() resolves correct project

**Out of Scope:**
- Do NOT modify resolve_logging_context signature
- Do NOT change global state fallback logic (that's future work)
- Do NOT modify any other session-related logic

---

### Task Package 1.4: Session Isolation Unit Tests

**Scope:** Add comprehensive unit tests for session key resolution
**Files to Create:**
- `tests/test_session_utils.py`

**Dependencies:** Tasks 1.1, 1.2, 1.3 complete

**Specifications:**
1. Create test file with 5 test cases:

   ```python
   import pytest
   from scribe_mcp.shared.session_utils import get_canonical_session_key
   from scribe_mcp.shared.execution_context import ExecutionContext

   def test_stable_session_id_only():
       \"\"\"When only stable_session_id exists, return it.\"\"\"
       ctx = ExecutionContext(stable_session_id="stable_123", session_id=None)
       assert get_canonical_session_key(ctx) == "stable_123"

   def test_session_id_only():
       \"\"\"When only session_id exists, return it (fallback).\"\"\"
       ctx = ExecutionContext(stable_session_id=None, session_id="ephemeral_456")
       assert get_canonical_session_key(ctx) == "ephemeral_456"

   def test_both_session_ids_stable_preferred():
       \"\"\"When both exist, stable_session_id takes precedence.\"\"\"
       ctx = ExecutionContext(stable_session_id="stable_123", session_id="ephemeral_456")
       assert get_canonical_session_key(ctx) == "stable_123"

   def test_neither_session_id_returns_none():
       \"\"\"When neither exists, return None.\"\"\"
       ctx = ExecutionContext(stable_session_id=None, session_id=None)
       assert get_canonical_session_key(ctx) is None

   def test_none_execution_context_returns_none():
       \"\"\"When ExecutionContext is None, return None.\"\"\"
       assert get_canonical_session_key(None) is None
   ```

2. All tests must pass
3. Use pytest conventions
4. Include docstrings for each test

**Verification:**
- [ ] File created at `tests/test_session_utils.py`
- [ ] All 5 test cases present
- [ ] `pytest tests/test_session_utils.py -v` passes (5/5 tests)
- [ ] Test coverage for all code paths
- [ ] Docstrings explain what each test validates

**Out of Scope:**
- Do NOT add integration tests yet (separate task)
- Do NOT test set_project or logging_utils (covered by integration tests)

---

### Task Package 1.5: Session Isolation Integration Test

**Scope:** End-to-end test that set_project() and append_entry() use same session key
**Files to Create:**
- `tests/test_session_isolation_integration.py`

**Dependencies:** All Phase 1 tasks complete

**Specifications:**
1. Create integration test:

   ```python
   import pytest
   from scribe_mcp.tools.set_project import set_project
   from scribe_mcp.tools.append_entry import append_entry
   from scribe_mcp.shared.execution_context import ExecutionContext

   @pytest.mark.asyncio
   async def test_session_isolation_end_to_end(tmp_path):
       \"\"\"Verify set_project and append_entry use same session key.\"\"\"
       # Setup: Create temp project directory
       project_root = tmp_path / "test_project"
       project_root.mkdir()

       # Simulate MCP session with stable_session_id
       exec_context = ExecutionContext(
           stable_session_id="test_session_123",
           session_id="ephemeral_456",
           repo_root=str(project_root)
       )

       # 1. Call set_project (binds session to project)
       result1 = await set_project(name="test_project", root=str(project_root))
       assert result1["ok"] is True

       # 2. Call append_entry in same session (should resolve to same project)
       result2 = await append_entry(
           message="Test entry",
           agent="TestAgent"
       )

       # 3. Verify logged to correct project
       assert result2["project"] == "test_project"
       assert "EmergencyFallback" not in result2["agent"]  # No fallback used
   ```

2. Test must pass with MCP server running
3. Cleanup temp project after test

**Verification:**
- [ ] File created at `tests/test_session_isolation_integration.py`
- [ ] `pytest tests/test_session_isolation_integration.py -v` passes
- [ ] Test confirms same project resolution
- [ ] No EmergencyFallback agent in logs
- [ ] Temp directory cleaned up after test

**Out of Scope:**
- Do NOT test cross-session isolation (complex, future work)
- Do NOT test session persistence across restarts (separate test)

---

## Phase 2: Multi-Project Tool Parameters

**Goal:** Add explicit `project` parameter to tools for cross-project operations

**Research Reference:** RESEARCH_MULTI_PROJECT_CONCURRENCY_20260119.md

### Task Package 2.1: Add Project Parameter to append_entry

**Scope:** Add optional `project` parameter to append_entry tool
**Files to Modify:**
- `tools/append_entry.py`
- `shared/logging_utils.py` (resolve_logging_context function)

**Dependencies:** Phase 1 complete

**Specifications:**

1. **Update append_entry.py signature (line ~1385):**

   Add `project` parameter AFTER `message`, BEFORE `status`:
   ```python
   async def append_entry(
       message: str = "",
       project: Optional[str] = None,  # NEW: Explicit project override
       status: str = "info",
       agent: str = "",
       meta: Optional[Dict[str, Any]] = None,
       # ... rest of params
   ) -> Dict[str, Any]:
   ```

2. **Pass project to resolve_logging_context (line ~1465):**

   Update the call:
   ```python
   context = await resolve_logging_context(
       tool_name="append_entry",
       server_module=server_module,
       explicit_project=project,  # NEW: Pass explicit override
       require_project=True
   )
   ```

3. **Update resolve_logging_context signature in logging_utils.py (line ~50):**

   Add `explicit_project` parameter:
   ```python
   async def resolve_logging_context(
       tool_name: str,
       server_module: Any,
       exec_context: Optional[ExecutionContext] = None,
       explicit_project: Optional[str] = None,  # NEW parameter
       require_project: bool = True,
   ) -> LoggingContext:
   ```

4. **Update precedence logic in resolve_logging_context (line ~70):**

   Check explicit_project FIRST:
   ```python
   # NEW: Explicit project parameter (highest priority)
   if explicit_project:
       # Validate project exists
       project_config = await load_project_config(server_module.state_manager, explicit_project)
       if not project_config:
           raise ProjectResolutionError(f"Explicit project '{explicit_project}' not found")
       return LoggingContext(
           tool_name=tool_name,
           project=project_config,
           ...
       )

   # Then check session binding...
   # Then check ExecutionContext.project...
   # Then global state fallback...
   ```

**Verification:**
- [ ] `project` parameter added to append_entry signature
- [ ] `explicit_project` parameter added to resolve_logging_context
- [ ] Precedence check added (explicit first)
- [ ] Manual test: `append_entry(message="test", project="other_project")` logs to other_project
- [ ] Manual test: Without project param, still uses session binding (backward compatible)
- [ ] `pytest tests/test_tool_project_params.py::test_append_entry_explicit_project` passes

**Out of Scope:**
- Do NOT modify other logging_utils functions
- Do NOT add access control (future work)
- Do NOT change error messages (keep existing)

---

### Task Package 2.2: Add Project Parameter to read_file

**Scope:** Add optional `project` parameter to read_file tool
**Files to Modify:**
- `tools/read_file.py`

**Dependencies:** Task 2.1 complete (uses same pattern)

**Specifications:**

1. **Add `project` parameter to read_file signature:**
   ```python
   async def read_file(
       path: str,
       project: Optional[str] = None,  # NEW: Explicit project override
       mode: str = "search",
       # ... rest of params
   ) -> Dict[str, Any]:
   ```

2. **Use project for path resolution:**

   If `project` provided, resolve path relative to that project's root:
   ```python
   if project:
       # Load project config to get root
       project_config = await load_project_config(server_module.state_manager, project)
       if not project_config:
           return {"ok": False, "error": f"Project '{project}' not found"}

       # Resolve path relative to project root
       project_root = Path(project_config.get("root"))
       resolved_path = project_root / path
   else:
       # Use current project context (existing logic)
       resolved_path = resolve_file_path(path)  # Existing function
   ```

3. **Validate resolved path is within project bounds:**
   ```python
   # Security: Ensure path doesn't escape project root
   if project and not resolved_path.is_relative_to(project_root):
       return {"ok": False, "error": "Path outside project root"}
   ```

**Verification:**
- [ ] `project` parameter added to read_file signature
- [ ] Path resolution uses project root when param provided
- [ ] Security check prevents path traversal
- [ ] Manual test: `read_file(path="file.py", project="other_project")` reads from other project
- [ ] Manual test: Without project param, reads from current context (backward compatible)
- [ ] `pytest tests/test_tool_project_params.py::test_read_file_explicit_project` passes

**Out of Scope:**
- Do NOT modify file reading logic (modes, chunking, etc.)
- Do NOT add file access control (future work)
- Do NOT change error messages

---

### Task Package 2.3: Fix generate_doc_templates Parameter Naming

**Scope:** Add clear `project` parameter for context, clarify `project_name` for template content
**Files to Modify:**
- `tools/generate_doc_templates.py`

**Dependencies:** Task 2.1 complete (uses same pattern)

**Specifications:**

1. **Update signature with explicit `project` parameter:**

   Current signature has confusing `project_name` parameter. Add new `project` for context:
   ```python
   async def generate_doc_templates(
       project_name: str,  # EXISTING: Name to put IN the templates (content)
       project: Optional[str] = None,  # NEW: Which project context to use (scope)
       author: Optional[str] = None,
       # ... rest of params
   ) -> Dict[str, Any]:
   ```

2. **Clarify parameter usage in docstring:**
   ```python
   \"\"\"Generate documentation templates for a project.

   Args:
       project_name: The name to use in template content (e.g., headers, metadata).
                     This is what appears IN the generated documents.
       project: Optional project context override. If provided, generates templates
                in this project's directory. If None, uses active project.
       author: Author name for template metadata
       ...

   Example:
       # Generate templates FOR project "my_feature" IN project "parent_project"
       generate_doc_templates(
           project_name="my_feature",  # Content name
           project="parent_project"     # Where to generate
       )
   \"\"\"
   ```

3. **Use `project` for path resolution:**
   ```python
   if project:
       # Generate in specified project's directory
       project_config = await load_project_config(server_module.state_manager, project)
       if not project_config:
           return {"ok": False, "error": f"Project '{project}' not found"}
       docs_dir = Path(project_config["root"]) / ".scribe/docs/dev_plans"
   else:
       # Use active project context (existing logic)
       docs_dir = get_active_project_docs_dir()
   ```

**Verification:**
- [ ] `project` parameter added to signature
- [ ] Docstring clarifies project_name vs project
- [ ] Path resolution uses project when provided
- [ ] Manual test: Can generate templates in different project context
- [ ] Backward compatible: Existing calls without `project` param still work
- [ ] `pytest tests/test_tool_project_params.py::test_generate_templates_explicit_project` passes

**Out of Scope:**
- Do NOT rename `project_name` parameter (breaking change, too risky)
- Do NOT modify template content generation
- Do NOT change document structure

---

### Task Package 2.4: Multi-Project Tool Tests

**Scope:** Add unit tests for cross-project tool usage
**Files to Create:**
- `tests/test_tool_project_params.py`

**Dependencies:** Tasks 2.1, 2.2, 2.3 complete

**Specifications:**

1. Create test file with 6 test cases:

   ```python
   import pytest
   from scribe_mcp.tools.append_entry import append_entry
   from scribe_mcp.tools.read_file import read_file
   from scribe_mcp.tools.generate_doc_templates import generate_doc_templates

   @pytest.mark.asyncio
   async def test_append_entry_explicit_project(tmp_path):
       \"\"\"Verify append_entry logs to explicit project, not active.\"\"\"
       # Setup: Create two projects
       project_a = create_project(tmp_path, "project_a")
       project_b = create_project(tmp_path, "project_b")

       # Active project is A
       await set_project(name="project_a")

       # Log to project B explicitly
       result = await append_entry(
           message="cross-project test",
           project="project_b",
           agent="TestAgent"
       )

       # Verify logged to B, not A
       assert result["project"] == "project_b"
       assert log_exists_in_project("project_b", "cross-project test")
       assert not log_exists_in_project("project_a", "cross-project test")

   @pytest.mark.asyncio
   async def test_read_file_explicit_project():
       \"\"\"Verify read_file reads from explicit project context.\"\"\"
       # ... similar pattern

   @pytest.mark.asyncio
   async def test_generate_templates_explicit_project():
       \"\"\"Verify generate_doc_templates creates in explicit project.\"\"\"
       # ... similar pattern

   @pytest.mark.asyncio
   async def test_precedence_explicit_over_session():
       \"\"\"Verify explicit project param wins over session binding.\"\"\"
       # ... test precedence

   @pytest.mark.asyncio
   async def test_error_when_require_project_and_none_available():
       \"\"\"Verify tools fail cleanly when require_project=True and no project.\"\"\"
       # ... test error case

   @pytest.mark.asyncio
   async def test_backward_compatible_without_project_param():
       \"\"\"Verify tools still work without project param (backward compatible).\"\"\"
       # ... test existing behavior preserved
   ```

2. All tests must pass
3. Use pytest conventions
4. Include setup/teardown for test projects

**Verification:**
- [ ] File created at `tests/test_tool_project_params.py`
- [ ] All 6 test cases present and pass
- [ ] `pytest tests/test_tool_project_params.py -v` passes (6/6 tests)
- [ ] Tests cover explicit param, precedence, errors, backward compat

**Out of Scope:**
- Do NOT test access control (not implemented yet)
- Do NOT test session persistence (separate concern)

---

## Phase 3: Custom Doc Naming Fix

**Goal:** Fix parameter precedence bug so `doc_name` takes priority over `metadata.doc_type`

**Research Reference:** RESEARCH_CUSTOM_DOC_NAMING_BUG_20260119.md

### Task Package 3.1: Fix Line 828 Parameter Precedence

**Scope:** Single line fix in manager.py
**Files to Modify:**
- `doc_management/manager.py` (line 828 only)

**Dependencies:** None (independent fix)

**Specifications:**

1. **Change line 828 from (BUGGY ORDER):**
   ```python
   resolved_name = metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type") or doc_name
   ```

   **To (CORRECT ORDER):**
   ```python
   resolved_name = doc_name or metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type")
   ```

2. **Rationale:** Function parameter `doc_name` should take precedence over metadata fallbacks

3. **Verification logic stays same (lines 829-831):**
   - No changes to validation
   - No changes to error messages
   - Just parameter order change

**Verification:**
- [ ] Line 828 modified (precedence order fixed)
- [ ] No other lines changed
- [ ] `python -m py_compile doc_management/manager.py` succeeds
- [ ] Manual test: `_resolve_create_doc_path(doc_name="TEST", metadata={"doc_type": "custom"})` returns "TEST.md", not "custom.md"

**Out of Scope:**
- Do NOT modify any other manager.py code
- Do NOT change validation logic
- Do NOT refactor the function

---

### Task Package 3.2: Add Regression Test for Doc Naming

**Scope:** Add comprehensive test for all precedence levels
**Files to Modify:**
- `tests/test_manage_docs_create_doc.py` (extend existing test file)

**Dependencies:** Task 3.1 complete

**Specifications:**

1. **Add new test case to existing file:**

   ```python
   @pytest.mark.asyncio
   async def test_doc_name_parameter_takes_precedence_over_metadata():
       \"\"\"Verify doc_name parameter takes precedence over metadata.doc_type.

       Regression test for bug where metadata.doc_type was checked before
       the doc_name parameter, causing wrong filename generation.

       Reference: RESEARCH_CUSTOM_DOC_NAMING_BUG_20260119.md
       \"\"\"
       from scribe_mcp.doc_management.manager import _resolve_create_doc_path

       # Test 1: doc_name parameter only
       result1 = _resolve_create_doc_path(
           doc_name="EXPLICIT_NAME",
           metadata={},
           project_root=tmp_path,
           project_name="test"
       )
       assert result1.name == "EXPLICIT_NAME.md"

       # Test 2: doc_name parameter + metadata.doc_type (parameter wins)
       result2 = _resolve_create_doc_path(
           doc_name="EXPLICIT_NAME",
           metadata={"doc_type": "custom"},
           project_root=tmp_path,
           project_name="test"
       )
       assert result2.name == "EXPLICIT_NAME.md"  # NOT custom.md

       # Test 3: metadata.doc_name only
       result3 = _resolve_create_doc_path(
           doc_name=None,
           metadata={"doc_name": "META_NAME"},
           project_root=tmp_path,
           project_name="test"
       )
       assert result3.name == "META_NAME.md"

       # Test 4: metadata.doc_type only (fallback)
       result4 = _resolve_create_doc_path(
           doc_name=None,
           metadata={"doc_type": "custom"},
           project_root=tmp_path,
           project_name="test"
       )
       assert result4.name == "custom.md"

       # Test 5: All precedence levels (parameter highest)
       result5 = _resolve_create_doc_path(
           doc_name="PARAM_NAME",
           metadata={
               "doc_name": "META_NAME",
               "register_as": "REGISTER_NAME",
               "doc_type": "TYPE_NAME"
           },
           project_root=tmp_path,
           project_name="test"
       )
       assert result5.name == "PARAM_NAME.md"  # Highest precedence
   ```

2. Test must catch the bug (fail before fix, pass after fix)

**Verification:**
- [ ] Test added to `tests/test_manage_docs_create_doc.py`
- [ ] Test includes all 5 precedence scenarios
- [ ] `pytest tests/test_manage_docs_create_doc.py::test_doc_name_parameter_takes_precedence_over_metadata -v` passes
- [ ] Test would have failed with old buggy code
- [ ] Docstring references research document

**Out of Scope:**
- Do NOT modify existing tests
- Do NOT test other manager.py functions
- Do NOT add integration tests (unit test sufficient)

---

## Phase 4: Index Update Event Coverage

**Goal:** Trigger index updates on ALL document changes, not just creation

**Research Reference:** RESEARCH_INDEX_FRONTMATTER_GAPS_20260120.md

### Task Package 4.1: Add Index Update Hook After Document Changes

**Scope:** Add index updater calls after successful document edits
**Files to Modify:**
- `tools/manage_docs.py` (lines ~1800, after apply_doc_change)

**Dependencies:** None (independent feature)

**Specifications:**

1. **Add helper function to determine doc category (before handle() function):**

   ```python
   def _determine_doc_category(doc_name: str, metadata: Dict[str, Any]) -> Optional[str]:
       \"\"\"Determine if document is a special type requiring index update.

       Args:
           doc_name: Document name or path
           metadata: Document metadata dict

       Returns:
           str: Category name (research, bugs, review, agent_cards) or None
       \"\"\"
       # Check metadata first
       doc_type = metadata.get("doc_type", "").lower()
       if doc_type in ["research", "bugs", "bug", "review", "agent_card", "agent_cards"]:
           if doc_type == "bug":
               return "bugs"
           if doc_type in ["agent_card", "agent_cards"]:
               return "agent_cards"
           return doc_type

       # Check filename patterns
       doc_name_upper = doc_name.upper()
       if doc_name_upper.startswith("RESEARCH_"):
           return "research"
       if doc_name_upper.startswith("BUG_") or "/bugs/" in doc_name.lower():
           return "bugs"
       if doc_name_upper.startswith("REVIEW_"):
           return "review"
       if doc_name_upper.startswith("AGENT_CARD_"):
           return "agent_cards"

       return None
   ```

2. **After apply_doc_change() returns successfully (line ~1800):**

   Add index update check:
   ```python
   # After this line:
   result = await apply_doc_change(...)

   # ADD NEW BLOCK:
   if result.status == "success":
       # NEW: Trigger index update for special doc types
       doc_category = _determine_doc_category(doc_name, metadata or {})

       if doc_category:
           # Map category to index updater function
           index_updater_map = {
               "research": _update_research_index,
               "bugs": _update_bug_index,
               "review": _update_review_index,
               "agent_cards": _update_agent_card_index,
           }

           updater_func = index_updater_map.get(doc_category)
           if updater_func:
               # Call index updater (functions already exist)
               await updater_func(
                   project_name=project_name,
                   project_root=project_root,
                   doc_dir=doc_dir  # Will need to determine this
               )
   ```

3. **Determine doc_dir for index updater:**

   Extract from document path or use convention:
   ```python
   # For research: .scribe/docs/dev_plans/{project}/research/
   # For bugs: .scribe/docs/dev_plans/{project}/bugs/
   # For review: .scribe/docs/dev_plans/{project}/
   # For agent_cards: .scribe/docs/dev_plans/{project}/

   doc_dir_map = {
       "research": project_root / ".scribe/docs/dev_plans" / project_name / "research",
       "bugs": project_root / ".scribe/docs/dev_plans" / project_name / "bugs",
       "review": project_root / ".scribe/docs/dev_plans" / project_name,
       "agent_cards": project_root / ".scribe/docs/dev_plans" / project_name,
   }
   doc_dir = doc_dir_map.get(doc_category, project_root)
   ```

**Verification:**
- [ ] `_determine_doc_category()` function added
- [ ] Index update block added after apply_doc_change()
- [ ] All 4 special doc types handled
- [ ] `python -m py_compile tools/manage_docs.py` succeeds
- [ ] Manual test: Edit research doc → INDEX.md updates
- [ ] Manual test: Edit bug report → bugs/INDEX.md updates

**Out of Scope:**
- Do NOT modify index updater functions (they already work)
- Do NOT add new doc types
- Do NOT change index format

---

### Task Package 4.2: Index Update Tests

**Scope:** Add tests verifying index updates on all edit actions
**Files to Create:**
- `tests/test_index_updates.py`

**Dependencies:** Task 4.1 complete

**Specifications:**

1. Create test file with 5 test cases:

   ```python
   import pytest
   from pathlib import Path
   from scribe_mcp.tools.manage_docs import manage_docs

   @pytest.mark.asyncio
   async def test_research_doc_edit_updates_index(tmp_path):
       \"\"\"Verify editing research doc triggers INDEX.md update.\"\"\"
       # 1. Create research doc
       await manage_docs(
           action="create",
           metadata={
               "doc_type": "research",
               "research_goal": "Initial goal"
           }
       )

       # 2. Read INDEX.md (before edit)
       index_path = tmp_path / ".scribe/docs/dev_plans/test/research/INDEX.md"
       index_before = index_path.read_text()
       assert "Initial goal" in index_before

       # 3. Edit research doc
       await manage_docs(
           action="replace_section",
           doc_name="RESEARCH_TEST",
           section="research_goal",
           content="Updated goal"
       )

       # 4. Read INDEX.md (after edit) - should be updated
       index_after = index_path.read_text()
       assert "Updated goal" in index_after
       assert index_after != index_before  # Changed!

   @pytest.mark.asyncio
   async def test_bug_report_edit_updates_index():
       \"\"\"Verify editing bug report triggers bugs/INDEX.md update.\"\"\"
       # ... similar pattern for bugs

   @pytest.mark.asyncio
   async def test_review_report_edit_updates_index():
       \"\"\"Verify editing review report triggers REVIEW_INDEX.md update.\"\"\"
       # ... similar pattern for reviews

   @pytest.mark.asyncio
   async def test_agent_card_edit_updates_index():
       \"\"\"Verify editing agent card triggers AGENT_CARDS_INDEX.md update.\"\"\"
       # ... similar pattern for agent cards

   @pytest.mark.asyncio
   async def test_multiple_edits_index_reflects_final_state():
       \"\"\"Verify multiple edits result in index showing final state.\"\"\"
       # Create doc
       # Edit 3 times
       # Verify index shows last edit, not intermediate states
   ```

2. All tests must pass
3. Use temp directories for isolation

**Verification:**
- [ ] File created at `tests/test_index_updates.py`
- [ ] All 5 test cases present
- [ ] `pytest tests/test_index_updates.py -v` passes (5/5 tests)
- [ ] Tests verify index content changes
- [ ] Tests verify timestamp updates

**Out of Scope:**
- Do NOT test index format/structure (separate concern)
- Do NOT test frontmatter updates (already covered)

---

## Phase 5: Backup Location Cleanup

**Goal:** Move inflight/preflight backups to dedicated `.scribe/backups/` directory

**Research Reference:** RESEARCH_INDEX_FRONTMATTER_GAPS_20260120.md (mentions backup pollution)

### Task Package 5.1: Create Backup Path Utility Function

**Scope:** Add utility function for generating backup paths
**Files to Modify:**
- `doc_management/manager.py` (add function before _resolve_create_doc_path)

**Dependencies:** None (independent feature)

**Specifications:**

1. **Add utility function:**

   ```python
   def get_backup_path(
       original_path: Path,
       project_name: str,
       backup_type: str = "inflight"  # inflight, preflight, manual
   ) -> Path:
       \"\"\"Generate backup path in dedicated backup directory.

       Args:
           original_path: Original file path (e.g., .scribe/docs/.../DOC.md)
           project_name: Project name for organization
           backup_type: Type of backup (inflight, preflight, manual)

       Returns:
           Path: .scribe/backups/{date}/{project}/{relative}/{file}.{timestamp}.{type}.bak

       Example:
           Input: .scribe/docs/dev_plans/proj/research/RESEARCH_DOC.md
           Output: .scribe/backups/2026-01-20/proj/research/RESEARCH_DOC.md.1705750000.inflight.bak
       \"\"\"
       from datetime import datetime

       # Find .scribe directory (walk up from original_path)
       scribe_root = original_path
       while scribe_root.parent != scribe_root:
           if scribe_root.name == ".scribe":
               break
           scribe_root = scribe_root.parent

       if scribe_root.name != ".scribe":
           # Fallback: use original directory
           return original_path.parent / f\"{original_path.name}.bak\"

       # Extract relative path from .scribe root
       try:
           relative = original_path.relative_to(scribe_root / \"docs\")
       except ValueError:
           relative = Path(original_path.name)

       # Generate backup directory structure
       backup_root = scribe_root / \"backups\"
       date_dir = datetime.now().strftime(\"%Y-%m-%d\")
       backup_dir = backup_root / date_dir / project_name / relative.parent
       backup_dir.mkdir(parents=True, exist_ok=True)

       # Generate timestamped filename
       timestamp = int(datetime.now().timestamp())
       backup_filename = f\"{original_path.stem}.{timestamp}.{backup_type}.bak\"

       return backup_dir / backup_filename
   ```

2. Add docstring explaining structure
3. Handle edge cases (file not in .scribe, invalid paths)

**Verification:**
- [ ] Function added to manager.py
- [ ] Docstring complete with example
- [ ] `python -m py_compile doc_management/manager.py` succeeds
- [ ] Manual test: Function generates correct paths
- [ ] Manual test: Creates directory structure

**Out of Scope:**
- Do NOT modify existing backup code yet (next task)
- Do NOT add cleanup logic (future work)

---

### Task Package 5.2: Update Backup Creation to Use New Path

**Scope:** Replace existing backup path logic with new utility function
**Files to Modify:**
- `doc_management/manager.py` (backup creation lines)
- `tools/manage_docs.py` (preflight/inflight backup calls)

**Dependencies:** Task 5.1 complete

**Specifications:**

1. **Find all backup creation calls in manager.py:**

   Search for:
   - `.bak` filename generation
   - `shutil.copy` or similar backup operations
   - Preflight/inflight backup code

2. **Replace inline backup path with function call:**

   Before:
   ```python
   backup_path = original_path.parent / f\"{original_path.name}.bak\"
   shutil.copy2(original_path, backup_path)
   ```

   After:
   ```python
   backup_path = get_backup_path(original_path, project_name, backup_type=\"inflight\")
   shutil.copy2(original_path, backup_path)
   ```

3. **Update all backup types:**
   - Inflight backups: `backup_type=\"inflight\"`
   - Preflight backups: `backup_type=\"preflight\"`
   - Manual backups: `backup_type=\"manual\"`

4. **Ensure project_name is available in scope:**
   - May need to pass as parameter to backup functions
   - Extract from context if needed

**Verification:**
- [ ] All backup creation calls updated
- [ ] Backups appear in `.scribe/backups/` directory
- [ ] Original directories clean (no .bak files)
- [ ] Timestamp in filename
- [ ] Date-based directory structure created
- [ ] Manual test: Create/edit doc → backup in correct location

**Out of Scope:**
- Do NOT add cleanup of old backups (future work)
- Do NOT migrate existing .bak files (manual cleanup acceptable)
- Do NOT change backup content/format

---

### Task Package 5.3: Backup Location Tests

**Scope:** Add tests verifying backup paths and cleanup
**Files to Create:**
- `tests/test_backup_paths.py`

**Dependencies:** Tasks 5.1, 5.2 complete

**Specifications:**

1. Create test file with 4 test cases:

   ```python
   import pytest
   from pathlib import Path
   from scribe_mcp.doc_management.manager import get_backup_path
   from scribe_mcp.tools.manage_docs import manage_docs

   def test_get_backup_path_structure():
       \"\"\"Verify backup path structure is correct.\"\"\"
       original = Path(\".scribe/docs/dev_plans/proj/research/DOC.md\")
       backup = get_backup_path(original, \"proj\", \"inflight\")

       # Verify structure: .scribe/backups/{date}/{project}/research/DOC.md.{timestamp}.inflight.bak
       assert backup.parts[0] == \".scribe\"
       assert backup.parts[1] == \"backups\"
       assert len(backup.parts[2]) == 10  # Date: YYYY-MM-DD
       assert backup.parts[3] == \"proj\"
       assert backup.parts[4] == \"research\"
       assert backup.name.startswith(\"DOC.md.\")
       assert backup.name.endswith(\".inflight.bak\")

   @pytest.mark.asyncio
   async def test_backup_created_in_dedicated_directory(tmp_path):
       \"\"\"Verify backups created in .scribe/backups/, not source dir.\"\"\"
       # Create and edit doc
       await manage_docs(action=\"create\", metadata={\"doc_type\": \"research\"})
       await manage_docs(action=\"replace_section\", doc_name=\"RESEARCH_TEST\", ...)

       # Verify backup in .scribe/backups/
       backup_dir = tmp_path / \".scribe/backups\"
       assert backup_dir.exists()
       assert len(list(backup_dir.rglob(\"*.bak\"))) > 0

       # Verify source directory clean
       research_dir = tmp_path / \".scribe/docs/dev_plans/test/research\"
       assert len(list(research_dir.glob(\"*.bak\"))) == 0  # No .bak files

   def test_timestamp_in_filename():
       \"\"\"Verify timestamp prevents backup collisions.\"\"\"
       # Create two backups of same file
       # Verify different timestamps
       # Verify both exist (no overwrite)

   def test_directory_structure_preserved():
       \"\"\"Verify backup preserves directory structure.\"\"\"
       # File in nested path
       # Verify backup in matching nested backup path
   ```

2. All tests must pass

**Verification:**
- [ ] File created at `tests/test_backup_paths.py`
- [ ] All 4 test cases present
- [ ] `pytest tests/test_backup_paths.py -v` passes (4/4 tests)
- [ ] Tests verify path structure, cleanup, timestamps

**Out of Scope:**
- Do NOT test backup retention (not implemented)
- Do NOT test backup content (separate concern)

---

## Phase Dependencies & Parallelization

```
Phase 1: Session Isolation
    │
    └─ Blocks Phase 2 (Multi-Project Params)

Phase 2: Multi-Project Params
    (depends on Phase 1)

Phase 3: Custom Doc Naming
    (independent - can run parallel)

Phase 4: Index Updates
    (independent - can run parallel)

Phase 5: Backup Cleanup
    (independent - can run parallel)
```

**Parallel Execution Strategy:**
- Phase 1 must complete first (foundational)
- Phase 2 waits for Phase 1
- Phases 3, 4, 5 can all run in parallel (independent)

---

## Testing & Deployment

### Pre-Deployment Checklist
- [ ] All unit tests pass (100% coverage)
- [ ] All integration tests pass
- [ ] Manual smoke tests complete
- [ ] No regressions in existing functionality
- [ ] Documentation updated (Scribe_Usage.md)
- [ ] CHANGELOG.md entry added

### Deployment Order
1. Phase 3 (lowest risk) → Deploy first, monitor
2. Phase 5 (cosmetic) → Deploy second
3. Phase 4 (medium risk) → Deploy third, monitor performance
4. Phase 1 (high risk) → Deploy fourth, monitor session bindings
5. Phase 2 (depends on 1) → Deploy last

### Rollback Plans
All phases have clear rollback plans documented in ARCHITECTURE_GUIDE.md

---

**End of Phase Plan**

Handoff to Coder: Each task package is independently testable and scoped to 2-4 hours work.
