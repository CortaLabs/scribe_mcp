---
id: agent_ux_overhaul-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 agent_ux_overhaul"
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-19'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — agent_ux_overhaul
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-19 06:54:56 UTC

> Execution roadmap for agent_ux_overhaul.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Risk | Key Deliverables | Est. Effort |
|-------|------|------|------------------|-------------|
| Phase 1 | Slugify Consolidation | LOW | normalize_project_input(), tool entry points, collision detection | 2-3 days |
| Phase 2 | manage_docs Simplification | MEDIUM | Action consolidation, deprecation aliases, auto-transform hook | 3-4 days |
| Phase 3 | Documentation Updates | LOW | 23 files updated with new action registry | 2 days |
| Phase 4 | Testing & Validation | LOW | Unit tests, integration tests, manual QA | 1-2 days |

**Total Estimated Effort:** 8-11 days

**Dependencies:**
- Phase 2 depends on Phase 1 (normalize_project_input used in manage_docs)
- Phase 3 depends on Phase 2 (can't document until code is stable)
- Phase 4 can run in parallel with Phase 3
<!-- ID: phase_0 -->
**Objective:** Create single-source normalization for project names across all tools.

**Risk Level:** LOW (additive changes, backwards compatible)

---

### Task Package 1.1: Create normalize_project_input()

**Scope:** Add canonical normalization function to utils/slug.py

**Files to Modify:** `utils/slug.py`

**Specifications:**
1. Add function `normalize_project_input(name: Optional[str]) -> Optional[str]` after line 35
2. Function returns None if input is None or empty string
3. Function calls existing `slugify_project_name()` for non-empty input
4. Add docstring with examples showing "My-Project", "my_project", "MY PROJECT" all returning "my_project"

**Verification:**
- [ ] `pytest tests/test_slugify_normalization.py::test_normalize_project_input_variants` passes
- [ ] Function handles None, empty string, whitespace-only inputs

**Out of Scope:** Do NOT modify existing `slugify_project_name()` function

---

### Task Package 1.2: Add Normalization to get_project

**Scope:** Normalize project parameter before lookups in get_project.py

**Files to Modify:** `tools/get_project.py`

**Specifications:**
1. Add import: `from utils.slug import normalize_project_input`
2. At line ~395, before `state.get_project(project)`, add: `project = normalize_project_input(project) or project`
3. This ensures lookups work regardless of input format

**Verification:**
- [ ] `set_project(name="My-Project")` then `get_project(project="my_project")` returns same project
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT modify return values or response format

---

### Task Package 1.3: Add Normalization to query_entries

**Scope:** Normalize project parameter in query_entries.py

**Files to Modify:** `tools/query_entries.py`

**Specifications:**
1. Add import: `from utils.slug import normalize_project_input`
2. At line ~1287, before `state.get_project(project_name)`, add normalization
3. Also normalize anywhere project is used for filtering

**Verification:**
- [ ] `query_entries(project="My-Project")` returns same results as `query_entries(project="my_project")`
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT change query logic or response format

---

### Task Package 1.4: Add Normalization to read_recent

**Scope:** Normalize project parameter in read_recent.py

**Files to Modify:** `tools/read_recent.py`

**Specifications:**
1. Add import: `from utils.slug import normalize_project_input`
2. In project resolution logic (~line 155), normalize before lookup
3. Ensure both explicit project parameter and context resolution are normalized

**Verification:**
- [ ] `read_recent(project="My-Project")` works with hyphenated input
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT change pagination or response format

---

### Task Package 1.5: Add Normalization to rotate_log

**Scope:** Normalize project parameter in rotate_log.py

**Files to Modify:** `tools/rotate_log.py`

**Specifications:**
1. Add import: `from utils.slug import normalize_project_input`
2. At line ~1367, normalize project parameter before use
3. Ensure log rotation works regardless of input format

**Verification:**
- [ ] `rotate_log(project="my-project")` works with hyphenated input
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT change rotation logic or archive naming

---

### Task Package 1.6: Fix delete_project Normalization

**Scope:** Use the existing (but unused) slugify import in delete_project.py

**Files to Modify:** `tools/delete_project.py`

**Specifications:**
1. Change import to: `from utils.slug import normalize_project_input`
2. At line ~23, normalize the `name` parameter before deletion
3. Ensure deletion works regardless of input format

**Verification:**
- [ ] Can delete project using any name variant
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT change deletion logic or confirmation flow

---

### Task Package 1.7: Fix load_project_config Normalization

**Scope:** Add normalization to config file lookup in project_utils.py

**Files to Modify:** `tools/project_utils.py`

**Specifications:**
1. Add import: `from utils.slug import normalize_project_input`
2. At line ~86, change to: `_load_project_file(PROJECTS_DIR / f"{normalize_project_input(project_name) or project_name}.json")`
3. This fixes the CRITICAL GAP identified in research

**Verification:**
- [ ] `load_project_config("My-Project")` finds `my_project.json` config file
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT change config file structure or fallback logic

---

### Task Package 1.8: Add Collision Detection to set_project

**Scope:** Prevent creating projects that would collide after normalization

**Files to Modify:** `tools/set_project.py`

**Specifications:**
1. Add import: `from utils.slug import normalize_project_input`
2. Add helper function `_check_slug_collision()` (see ARCHITECTURE_GUIDE.md section 4.1.3)
3. Call `_check_slug_collision()` before `backend.upsert_project()` for new projects
4. Raise clear error: "Project 'my-project' would collide with existing project 'my_project'"

**Verification:**
- [ ] Create "my_project", then attempt "my-project" -> error with suggestion
- [ ] Creating project with same name twice still works (update, not collision)
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT change existing project update logic

---

### Task Package 1.9: Normalize State Dict Keys (Optional)

**Scope:** Normalize project keys in state manager

**Files to Modify:** `state/manager.py`

**Specifications:**
1. Add import: `from utils.slug import normalize_project_input`
2. In `get_project()` method, normalize key before dict lookup
3. Optionally: In `set_current_project()`, store under normalized key

**Verification:**
- [ ] State lookups work with any name format
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT migrate existing state file (lazy approach)

**Note:** This task is OPTIONAL for Phase 1 MVP. Can be deferred if time-constrained.
<!-- ID: phase_1 -->
**Objective:** Consolidate 18 actions to 7 focused actions with backwards-compatible aliases.

**Risk Level:** MEDIUM (changes to frequently-used tool, but old code keeps working)

---

### Task Package 2.1: Define Action Registry Constants

**Scope:** Create clear action categorization in manage_docs.py

**Files to Modify:** `tools/manage_docs.py`

**Specifications:**
1. At line ~104, replace `valid_actions` set with three categorized sets:
   - `PRIMARY_ACTIONS`: create, replace_section, apply_patch, replace_range, replace_text, append, status_update
   - `DEPRECATED_ALIASES`: Dictionary mapping old names to (new_action, default_params)
   - `HIDDEN_ACTIONS`: normalize_headers, generate_toc, validate_crosslinks, list_sections, list_checklist_items, search, batch
2. Combine all three for validation: `valid_actions = PRIMARY_ACTIONS | set(DEPRECATED_ALIASES.keys()) | HIDDEN_ACTIONS`
3. See ARCHITECTURE_GUIDE.md section 4.2.1 for exact code

**Verification:**
- [ ] All 18 original actions still pass validation
- [ ] New "create" action passes validation
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT change action dispatch logic yet (that's next task)

---

### Task Package 2.2: Implement create Action with doc_type Routing

**Scope:** Add new unified "create" action that routes based on doc_type

**Files to Modify:** `tools/manage_docs.py`

**Specifications:**
1. In action dispatcher (around line 1354), add handling for "create" action
2. Extract `doc_type` from metadata (default: "custom")
3. Route to existing handlers:
   - doc_type="custom" -> _handle_custom_doc_creation() (existing create_doc logic)
   - doc_type="research" -> _handle_research_doc_creation() (existing create_research_doc logic)
   - doc_type="bug" -> _handle_bug_report_creation() (existing create_bug_report logic)
   - doc_type="review" -> _handle_review_report_creation() (existing create_review_report logic)
   - doc_type="agent_card" -> _handle_agent_card_creation() (existing create_agent_report_card logic)
4. See ARCHITECTURE_GUIDE.md section 4.2.2 for implementation pattern

**Verification:**
- [ ] `manage_docs(action="create", doc_type="research", ...)` creates research doc
- [ ] `manage_docs(action="create", doc_type="bug", ...)` creates bug report
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT remove old action names yet (that's deprecation task)

---

### Task Package 2.3: Implement Deprecation Aliases

**Scope:** Map old action names to new create action with warnings

**Files to Modify:** `tools/manage_docs.py`

**Specifications:**
1. In action dispatcher, before processing, check if action is in DEPRECATED_ALIASES
2. If deprecated:
   a. Get (new_action, default_params) from DEPRECATED_ALIASES
   b. Add deprecation message to healing_messages
   c. Apply default_params to metadata if not already set
   d. Change action to new_action
3. Deprecation message format: "DEPRECATED: 'create_research_doc' is deprecated. Use create(doc_type='research') instead."
4. Include deprecation warning in response under "deprecated" key

**Verification:**
- [ ] `create_research_doc(...)` still works but emits deprecation warning
- [ ] `create_bug_report(...)` still works but emits deprecation warning
- [ ] Response includes "deprecated" field with migration guidance
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT remove the old handlers (they're still used internally)

---

### Task Package 2.4: Add Auto-Transform Hook (Opt-in via Frontmatter)

**Scope:** Apply normalize_headers/generate_toc automatically when frontmatter opts in

**Files to Modify:** `doc_management/manager.py`

**Specifications:**
1. After line ~480 (after frontmatter pipeline), add auto-transform check
2. Check `frontmatter_data.get("auto_normalize_headers")` and `frontmatter_data.get("auto_generate_toc")`
3. If enabled AND action is not already normalize_headers/generate_toc:
   - Apply `_normalize_headers_text()` to body
   - Apply `_generate_toc_text()` to body
4. Add flags to frontmatter_extra to indicate transforms were applied
5. See ARCHITECTURE_GUIDE.md section 4.2.3 for exact code

**Verification:**
- [ ] Doc with `auto_normalize_headers: true` in frontmatter gets headers normalized after edit
- [ ] Doc with `auto_generate_toc: true` in frontmatter gets TOC generated after edit
- [ ] Docs WITHOUT these flags are NOT auto-transformed (no change from current behavior)
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT make auto-transform the default; frontmatter opt-in only

---

### Task Package 2.5: Add Normalization to manage_docs Project Parameter

**Scope:** Normalize project parameter in manage_docs.py

**Files to Modify:** `tools/manage_docs.py`

**Specifications:**
1. Add import: `from utils.slug import normalize_project_input`
2. Near line ~1102, normalize the project parameter if provided
3. Ensure document operations work regardless of project name format

**Verification:**
- [ ] `manage_docs(project="My-Project", ...)` works with hyphenated input
- [ ] Existing tests pass unchanged

**Out of Scope:** Do NOT change document resolution logic
<!-- ID: milestone_tracking -->
**Objective:** Update all documentation to reflect new 7-action registry and slugify changes.

**Risk Level:** LOW (documentation only, no code changes)

---

### Task Package 3.1: Update Critical Documentation (6 files)

**Scope:** Update highest-impact documentation files

**Files to Modify:**
- `docs/Scribe_Usage.md` - Main tool reference
- `CLAUDE.md` - Root orchestration guide
- `config/CLAUDE.md` - Server-specific guide
- `.codex/skills/scribe-mcp-usage/references/manage_docs.md` - Skill reference
- `.codex/skills/scribe-mcp-usage/references/Scribe_Usage.md` - Skill tool reference
- `.codex/skills/scribe-mcp-usage/SKILL.md` - Skill definition

**Specifications:**
1. Replace manage_docs action tables with new 7-action registry
2. Add "Deprecated Actions" section listing old names with migration guidance
3. Update project naming guidance to mention normalization
4. Add examples using new `create(doc_type="...")` syntax

**Verification:**
- [ ] All 6 files reflect new action registry
- [ ] Deprecated actions documented with migration path
- [ ] No references to removed actions without deprecation note

**Out of Scope:** Do NOT update agent-specific files (that's next task)

---

### Task Package 3.2: Update Agent Definitions (3 files)

**Scope:** Update agent definition files with new patterns

**Files to Modify:**
- `AGENTS.md` - Cross-agent governance
- `docs/guides/manage_docs_agent_guide.md` - Agent usage guide
- `.codex/skills/.../sections/documentation_management.md` - Section reference

**Specifications:**
1. Update manage_docs examples to use new action names
2. Add note about project name flexibility (hyphens/underscores work)
3. Remove references to deprecated actions in examples

**Verification:**
- [ ] All 3 files reflect new patterns
- [ ] Examples use `create(doc_type="...")` syntax

**Out of Scope:** Do NOT update individual agent instruction files (that's next task)

---

### Task Package 3.3: Update Agent Instructions (8 files)

**Scope:** Update individual agent instruction files

**Files to Modify:**
- `.claude/agents/scribe-architect.md`
- `.claude/agents/scribe-research-analyst.md`
- `.claude/agents/scribe-coder.md`
- `.claude/agents/scribe-review-agent.md`
- `.claude/agents/scribe-bug-hunter.md`
- `docs/guides/manage_docs_troubleshooting.md`
- `PROJECT_NAMING.md`
- `README.md`

**Specifications:**
1. Update any manage_docs examples to use new syntax
2. Update project naming guidance
3. Remove/update troubleshooting for deprecated actions

**Verification:**
- [ ] All 8 files reflect new patterns
- [ ] No stale examples using deprecated action names

**Out of Scope:** Do NOT update internal implementation comments

---

### Task Package 3.4: Update Supporting Documentation (6 files)

**Scope:** Update remaining documentation files

**Files to Modify:**
- `.codex/skills/.../sections/document_editing_manage_docs.md`
- `docs/whitepapers/scribe_mcp_whitepaper.md`
- Various .codex reference files as identified

**Specifications:**
1. Search for "create_research_doc", "create_bug_report", etc. and update
2. Update any action listings or tables
3. Add deprecation notes where appropriate

**Verification:**
- [ ] grep for deprecated action names returns only deprecation documentation
- [ ] All files consistent with new action registry

**Out of Scope:** Do NOT update test files (tests should continue using old actions to verify backwards compatibility)
<!-- ID: retro_notes -->
**Objective:** Comprehensive testing to ensure zero regressions and proper functionality.

**Risk Level:** LOW (testing only, catches issues before they reach production)

---

### Task Package 4.1: Create Slugify Normalization Tests

**Scope:** Unit tests for normalize_project_input()

**Files to Create:** `tests/test_slugify_normalization.py`

**Specifications:**
1. Test normalize_project_input() with various inputs:
   - "My-Project" -> "my_project"
   - "my_project" -> "my_project"
   - "MY PROJECT" -> "my_project"
   - None -> None
   - "" -> None
   - "   " -> None
2. Test collision detection in set_project
3. Test cross-tool consistency (set_project + get_project with different formats)

**Verification:**
- [ ] `pytest tests/test_slugify_normalization.py` passes
- [ ] All edge cases covered

**Out of Scope:** Do NOT test lazy migration (that's integration-level)

---

### Task Package 4.2: Create manage_docs Consolidation Tests

**Scope:** Tests for action consolidation and deprecation

**Files to Create:** `tests/test_manage_docs_consolidation.py`

**Specifications:**
1. Test new "create" action with each doc_type
2. Test deprecated action aliases emit warnings
3. Test hidden actions still work
4. Test auto-transform opt-in via frontmatter

**Verification:**
- [ ] `pytest tests/test_manage_docs_consolidation.py` passes
- [ ] All action routes verified

**Out of Scope:** Do NOT modify existing manage_docs tests (they verify backwards compatibility)

---

### Task Package 4.3: Run Full Test Suite

**Scope:** Verify all existing tests still pass

**Files to Modify:** None (just run tests)

**Specifications:**
1. Run `pytest tests/` - all tests must pass
2. Run `pytest tests/test_manage_docs*.py` - manage_docs tests specifically
3. Fix any regressions (should be none if implemented correctly)

**Verification:**
- [ ] `pytest tests/` passes with 0 failures
- [ ] No new warnings (except expected deprecation warnings)

**Out of Scope:** Do NOT add new tests (already covered in 4.1 and 4.2)

---

### Task Package 4.4: Manual QA Verification

**Scope:** Human verification of key scenarios

**Files to Modify:** None

**Specifications:**
Execute and verify each scenario:
1. Create project with hyphens: `set_project(name="my-test-project")`
2. Access with underscores: `get_project(project="my_test_project")` -> same project
3. Query with mixed case: `query_entries(project="MY_TEST_PROJECT")` -> returns entries
4. Use deprecated action: `create_research_doc(...)` -> works with warning
5. Use new action: `create(doc_type="research", ...)` -> works without warning
6. Test auto-transform: Create doc with `auto_normalize_headers: true`, edit, verify headers normalized
7. Test collision: Create "test_project", then try "test-project" -> error

**Verification:**
- [ ] All 7 scenarios pass
- [ ] Deprecation warnings are clear and actionable
- [ ] Error messages include suggestions

**Out of Scope:** Do NOT automate these tests (they verify UX, not just functionality)

---

## Milestone Tracking

| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Phase 1 Complete | TBD | Coder | Planned | CHECKLIST.md Phase 1 items |
| Phase 2 Complete | TBD | Coder | Planned | CHECKLIST.md Phase 2 items |
| Phase 3 Complete | TBD | Coder | Planned | CHECKLIST.md Phase 3 items |
| Phase 4 Complete | TBD | Coder | Planned | Test results |
| Full Rollout | TBD | Orchestrator | Planned | All phases complete |

---

## Retro Notes & Adjustments

*Document lessons learned and scope changes after each phase completes.*

---
*Phase Plan v1.0 - Agent UX Overhaul*
*Generated: 2026-01-19 by ArchitectAgent*
