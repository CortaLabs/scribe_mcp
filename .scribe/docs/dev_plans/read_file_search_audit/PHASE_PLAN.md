---
id: read_file_search_audit-phase-plan
title: "⚙️ Phase Plan — read_file_search_audit"
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-29'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — read_file_search_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-29 02:49:00 UTC

> Execution roadmap for read_file_search_audit.

---
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Goal | Key Deliverables | Est. Effort | Dependencies |
|-------|------|------------------|-------------|--------------|
| Phase 0 | Foundation Setup | ExecutionContext extension, security/sandbox updates | 2-3 hours | None |
| Phase 1 | search Tool MVP | Core search functionality with basic output modes | 6-8 hours | Phase 0 |
| Phase 2 | search Advanced Features | Context lines, multiline search, type filters | 4-6 hours | Phase 1 |
| Phase 3 | edit_file Tool | Complete edit_file implementation with safety | 4-6 hours | Phase 0 |
| Phase 4 | read_file Bug Fix | Fix repo root confusion | 2-3 hours | None |
| Phase 5 | Integration & Testing | Comprehensive tests, documentation | 4-6 hours | All phases |

**Total Estimated Effort:** 22-32 hours

**Critical Path:** Phase 0 → Phase 1 → Phase 2 (search complete) can run parallel to Phase 0 → Phase 3 (edit_file complete)

**Confidence:** 0.92 (High - architecture verified against existing patterns, clear scope, reusable infrastructure)

---
## Phase 0 — Foundation Setup
<!-- ID: phase_0 -->

**Objective:** Extend existing infrastructure to support new tools

**Estimated Effort:** 2-3 hours

### Task Package 0.1: RouterContextManager Extension

**Scope:** Add session state tracking for read-before-edit enforcement

**Files to Modify:**
- `shared/execution_context.py` (extend RouterContextManager class)

**Specifications:**
1. Add `_files_read_in_session: Dict[str, Set[str]]` field to RouterContextManager.__init__():
   - Maps session_id -> set of file paths
   - Initialize with `defaultdict(set)`
2. Add method `record_file_read(self, session_id: str, file_path: str) -> None`:
   - Guard: return early if session_id or file_path is empty
   - Acquire `self._lock` (async with)
   - Add file_path to `self._files_read_in_session[session_id]`
3. Add method `has_file_been_read(self, session_id: str, file_path: str) -> bool`:
   - Guard: return False if session_id or file_path is empty
   - Acquire `self._lock` (async with)
   - Return True if file_path in session's set, False otherwise
4. Extend `cleanup_session(self, session_id: str) -> None` method:
   - Add line: `self._files_read_in_session.pop(session_id, None)`
   - This method may not exist yet - create it if needed
   - Must also clean up `_transport_sessions` and `_session_projects`

**Verification:**
- [ ] Unit test: `test_router_context_manager_file_tracking()` passes
- [ ] Can record file read and verify it was read
- [ ] Different sessions have isolated tracking (session A can't see session B's reads)
- [ ] cleanup_session removes session from all caches

**Out of Scope:**
- Do NOT modify ExecutionContext class
- Do NOT add database persistence for file tracking
- Do NOT modify existing RouterContextManager methods (except cleanup_session extension)

**Integration Notes:**
- This follows the existing `_session_projects` cache pattern (line 59 of execution_context.py)
- Module-level singleton in server.py (line 112) ensures persistence across tool calls
- Will be called by read_file and edit_file tools in Phase 1 and Phase 3

---

### Task Package 0.2: Integrate read_file with Session Tracking

**Scope:** Modify existing read_file tool to record file reads

**Files to Modify:**
- `tools/read_file.py` (~5 lines added)

**Specifications:**
1. Add import at top of file:
   - `from scribe_mcp.server import router_context_manager, get_execution_context`
2. After successful file read (just before returning result), add tracking:
   ```python
   # Record file read for edit_file enforcement
   exec_ctx = get_execution_context()
   if exec_ctx and exec_ctx.session_id:
       await router_context_manager.record_file_read(
           exec_ctx.session_id,
           str(normalized_path)  # Use the resolved path
       )
   ```
3. Place this AFTER file content is read, BEFORE return statement
4. Should work for all read modes (scan_only, chunk, page, line_range, search)

**Verification:**
- [ ] read_file still works normally (existing tests pass)
- [ ] Session tracking captures file paths correctly
- [ ] Can verify via `router_context_manager.has_file_been_read()` after calling read_file

**Out of Scope:**
- Do NOT modify read_file's core logic
- Do NOT change read_file's return value or error handling

---

### Task Package 0.3: REMOVED (Unnecessary per review)

**Reason:** PermissionChecker.check_permission() already returns True for unrecognized operations via fallthrough at line 190 of security/sandbox.py. Adding explicit cases for "search" and "edit" is no-op code. Both operations are allowed by default.

**Alternative:** No code changes needed. Document in Phase 5 that search/edit operations use existing permission model.

---

**Phase 0 Deliverables:**
- RouterContextManager can track files read per session
- Three new methods: record_file_read(), has_file_been_read(), cleanup_session()
- read_file tool records file reads automatically
- Session cleanup prevents memory leaks
- Unit tests confirm tracking works with session isolation

**Dependencies:** None (standalone infrastructure updates)

**Notes:** This phase enables the safety mechanisms for Phase 3 (edit_file). Task 0.3 was removed as unnecessary - existing permission system already allows all operations by default.

---

## Phase 1 — search Tool MVP
<!-- ID: phase_1 -->

**Objective:** Build core search tool with basic functionality

**Estimated Effort:** 6-8 hours

### Task Package 1.1: Create search Tool Skeleton

**Scope:** Set up new tools/search.py with MCP registration and basic structure

**Files to Create:**
- `tools/search.py` (new file, ~200 lines for skeleton)

**Specifications:**
1. Copy import pattern from `tools/read_file.py` lines 17-25:
   - `from scribe_mcp import server as server_module`
   - `from scribe_mcp.config.settings import settings`
   - `from scribe_mcp.server import app`
   - `from scribe_mcp.shared.execution_context import ExecutionContext`
   - `from scribe_mcp.security.sandbox import PathSandbox, safe_file_operation`
   - `from scribe_mcp.utils.response import default_formatter`
   - Standard library: `Path`, `re`, `typing`, `os`
2. Define `@app.tool()` decorated async function `search()` with complete signature (all parameters from architecture)
   - Note: The `@app.tool()` decorator pattern is verified working in read_file.py line 1693
3. Implement basic structure:
   - Get execution context
   - Resolve repo root
   - Validate path with PathSandbox
   - Return placeholder response
4. Add docstring matching architecture specification

**Verification:**
- [ ] MCP server starts without errors
- [ ] `search` tool appears in tool list
- [ ] Can call search with minimal params (returns placeholder)

**Out of Scope:**
- Do NOT implement actual search logic yet
- Do NOT implement output formatting yet

---

### Task Package 1.2: Implement File Traversal

**Scope:** Add recursive directory traversal with filtering

**Files to Modify:**
- `tools/search.py` (add `_iterate_files()` helper function, ~100 lines)

**Specifications:**
1. Create `_iterate_files(root: Path, glob: Optional[str], type: Optional[str], sandbox: PathSandbox) -> Iterator[Path]`:
   - Use `Path.rglob()` for recursive traversal
   - Filter by glob pattern if provided (use `fnmatch`)
   - Filter by file type if provided (map type to extensions: py→.py, js→.js/.jsx, ts→.ts/.tsx, etc.)
   - Skip files rejected by `sandbox.is_allowed()`
   - Skip hidden files/directories (starting with `.` except `.scribe`)
   - Yield valid file paths
2. Add file type mapping dictionary: `TYPE_TO_EXTENSIONS = {"py": [".py"], "js": [".js", ".jsx"], ...}`
3. Integrate into main `search()` function

**Verification:**
- [ ] Unit test: `test_iterate_files()` traverses correctly
- [ ] Glob filtering works (`*.py` only yields Python files)
- [ ] Type filtering works (`type="py"` only yields Python files)
- [ ] Sandbox enforcement works (rejects files outside repo)

**Out of Scope:**
- Do NOT implement binary file detection yet
- Do NOT implement size limits yet

---

### Task Package 1.3: Implement Pattern Matching

**Scope:** Add regex and literal search logic

**Files to Modify:**
- `tools/search.py` (add `_search_file()` function, ~80 lines)

**Specifications:**
1. Create `_search_file(path: Path, pattern: str, regex: bool, case_insensitive: bool, max_matches: int) -> List[Match]`:
   - Read file content (UTF-8, handle decode errors)
   - Compile regex pattern if `regex=True`, else escape for literal matching
   - Apply case-insensitive flag if needed
   - Search line-by-line
   - Collect matches up to `max_matches_per_file`
   - Return list of `Match` objects (line_number, line_content)
2. Define `Match` dataclass for type safety
3. Integrate into main `search()` function

**Verification:**
- [ ] Unit test: `test_search_file_regex()` finds regex matches
- [ ] Unit test: `test_search_file_literal()` finds exact strings
- [ ] Case-insensitive search works
- [ ] Max matches limit enforced

**Out of Scope:**
- Do NOT implement multiline search yet (Phase 2)
- Do NOT implement context lines yet (Phase 2)

---

### Task Package 1.4: Implement Output Modes

**Scope:** Add content, files_with_matches, count output modes

**Files to Modify:**
- `tools/search.py` (add `_format_results()` function, ~100 lines)

**Specifications:**
1. Create `_format_results(results: Dict, output_mode: str, format: str) -> Union[Dict, str]`:
   - **Content mode:** Return full match details with line numbers and content
   - **Files-with-matches mode:** Return list of file paths only
   - **Count mode:** Return match counts per file
   - Use `default_formatter` for format conversion (readable/structured/compact)
2. Define result aggregation in main `search()`:
   - Track `files_searched`, `files_with_matches`, `total_matches`
   - Respect `max_total_matches` and `max_files` limits
3. Return formatted response

**Verification:**
- [ ] Unit test: `test_output_mode_content()` returns matches with lines
- [ ] Unit test: `test_output_mode_files()` returns paths only
- [ ] Unit test: `test_output_mode_count()` returns counts
- [ ] Limits enforced (max_total_matches, max_files)

**Out of Scope:**
- Do NOT implement advanced formatting yet
- Do NOT implement color highlighting yet

---

**Phase 1 Deliverables:**
- Functional `search` MCP tool
- Recursive file traversal with glob/type filtering
- Regex and literal pattern matching
- Three output modes working (content, files_with_matches, count)
- Basic integration tests passing

**Dependencies:** Phase 0

**Notes:** This phase delivers a working search tool. Phase 2 adds polish (context lines, multiline, binary detection).

---
## Phase 2 — search Tool Advanced Features
<!-- ID: phase_2 -->

**Objective:** Add context lines, multiline search, performance optimizations

**Estimated Effort:** 4-6 hours

### Task Package 2.1: Context Lines Support

**Scope:** Add before/after/around context line display

**Files to Modify:**
- `tools/search.py` (modify `_search_file()` and Match dataclass, ~60 lines)

**Specifications:**
1. Extend `Match` dataclass:
   - Add `context_before: List[str]`
   - Add `context_after: List[str]`
2. Modify `_search_file()` to collect context:
   - Track N lines before match in circular buffer
   - After match found, read N lines after
   - Respect `before_context`, `after_context`, `context_lines` params
3. Update output formatting to display context

**Verification:**
- [ ] Unit test: `test_context_lines()` shows before/after correctly
- [ ] `context_lines=3` shows 3 lines before and after
- [ ] `before_context=2, after_context=1` shows asymmetric context

**Out of Scope:**
- Do NOT overlap context from adjacent matches yet

---

### Task Package 2.2: Multiline Search

**Scope:** Add support for patterns spanning multiple lines

**Files to Modify:**
- `tools/search.py` (modify `_search_file()`, ~40 lines)

**Specifications:**
1. Add `multiline` parameter handling:
   - If `multiline=True`, read entire file as single string (with size limit check)
   - Apply pattern to full content
   - Track line numbers for multi-line matches
2. Add safety: Only allow multiline for files <1MB (configurable)

**Verification:**
- [ ] Unit test: `test_multiline_search()` finds patterns across lines
- [ ] Large files rejected with clear error message

**Out of Scope:**
- Do NOT implement streaming multiline search yet

---

### Task Package 2.3: Binary File Detection & Size Limits

**Scope:** Skip binary files, enforce size limits

**Files to Modify:**
- `tools/search.py` (add `_is_binary()` helper, modify `_search_file()`, ~50 lines)

**Specifications:**
1. Create `_is_binary(path: Path) -> bool`:
   - Read first 8KB of file
   - Check for null bytes or high ratio of non-text bytes
   - Return True if binary detected
2. Integrate into `_iterate_files()`:
   - Skip binary files if `skip_binary=True` (default)
   - Skip files larger than `max_file_size_mb`
3. Track skipped files in results

**Verification:**
- [ ] Binary files (images, executables) skipped by default
- [ ] Large files (>10MB) skipped by default
- [ ] Results show `files_skipped` count and reasons

**Out of Scope:**
- Do NOT add magic number detection yet

---

**Phase 2 Deliverables:**
- Context lines working (before/after/around)
- Multiline search supported for small files
- Binary file detection prevents crashes
- Size limits prevent performance issues

**Dependencies:** Phase 1

**Notes:** Phase 2 brings search tool to feature parity with grep/rg.

---
## Phase 3 — edit_file Tool
<!-- ID: phase_3 -->

**Objective:** Implement complete edit_file tool with safety mechanisms

**Estimated Effort:** 4-6 hours

### Task Package 3.1: Create edit_file Tool Skeleton

**Scope:** Set up new tools/edit_file.py with MCP registration

**Files to Create:**
- `tools/edit_file.py` (new file, ~150 lines for skeleton)

**Specifications:**
1. Copy import pattern from `tools/read_file.py` (same as search tool), plus:
   - `from scribe_mcp.server import router_context_manager, get_execution_context`
   - This gives access to session state tracking
2. Define `@app.tool()` decorated async function `edit_file()` with complete signature
3. Implement safety checks (read-before-edit enforcement):
   - Get execution context: `exec_ctx = get_execution_context()`
   - Validate session: `if not exec_ctx or not exec_ctx.session_id: raise ValueError(...)`
   - Check file was read: `if not await router_context_manager.has_file_been_read(exec_ctx.session_id, str(normalized_path)): raise ValueError("Must call read_file first")`
   - Validate path with PathSandbox
4. Return placeholder response

**Verification:**
- [ ] MCP server starts without errors
- [ ] `edit_file` tool appears in tool list
- [ ] Calling without read_file first returns "Must call read_file first" error
- [ ] Calling AFTER read_file in same session succeeds (gets to placeholder response)

**Out of Scope:**
- Do NOT implement actual editing yet
- Do NOT implement backup yet

---

### Task Package 3.2: Implement String Replacement Logic

**Scope:** Add exact string find/replace functionality

**Files to Modify:**
- `tools/edit_file.py` (add `_perform_replacement()` function, ~80 lines)

**Specifications:**
1. Create `_perform_replacement(content: str, old_string: str, new_string: str, replace_all: bool) -> Tuple[str, ReplaceResult]`:
   - Find all occurrences of `old_string` (exact match)
   - Track line numbers where found
   - Replace first or all occurrences based on `replace_all`
   - Return modified content and metadata
2. Define `ReplaceResult` dataclass with:
   - `occurrences_found: int`
   - `occurrences_replaced: int`
   - `lines_affected: List[int]`
3. Integrate into `edit_file()` for dry-run mode

**Verification:**
- [ ] Unit test: `test_replace_first()` replaces only first occurrence
- [ ] Unit test: `test_replace_all()` replaces all occurrences
- [ ] Line numbers tracked correctly

**Out of Scope:**
- Do NOT implement regex replacement yet (MVP is literal only)

---

### Task Package 3.3: Implement Diff Generation

**Scope:** Generate unified diff for preview

**Files to Modify:**
- `tools/edit_file.py` (add `_generate_diff()` function, ~40 lines)

**Specifications:**
1. Create `_generate_diff(original: str, modified: str, filepath: str) -> str`:
   - Use `difflib.unified_diff()`
   - Format as standard unified diff
   - Return diff string
2. Include diff in dry-run response
3. Include diff in commit response

**Verification:**
- [ ] Unit test: `test_generate_diff()` produces valid unified diff
- [ ] Diff shows correct before/after lines

**Out of Scope:**
- Do NOT implement colored diff yet

---

### Task Package 3.4: Implement Commit Mode with Backup

**Scope:** Actually write changes when dry_run=False

**Files to Modify:**
- `tools/edit_file.py` (add backup and write logic, ~60 lines)

**Specifications:**
1. Create `_backup_file(path: Path) -> Path`:
   - Create `.scribe/backups/` directory if needed
   - Copy file to backup with timestamp: `filename.YYYYMMDD_HHMM.bak`
   - Return backup path
2. Modify `edit_file()` to:
   - If `dry_run=False`:
     - Create backup
     - Write modified content to file
     - Return success response with backup path
3. Add comprehensive logging

**Verification:**
- [ ] Unit test: `test_edit_file_commit()` actually modifies file
- [ ] Backup created before modification
- [ ] File content matches expected replacement
- [ ] Response includes backup_path

**Out of Scope:**
- Do NOT implement backup rotation yet
- Do NOT implement undo functionality yet

---

**Phase 3 Deliverables:**
- Functional `edit_file` MCP tool
- Read-before-edit enforcement working
- Dry-run safe by default
- Unified diff preview
- Commit mode with automatic backups

**Dependencies:** Phase 0

**Notes:** Phase 3 can run in parallel with Phases 1-2 since both depend only on Phase 0.

---
## Phase 4 — read_file Repo Root Bug Fix
<!-- ID: phase_4 -->

**Objective:** Investigate and fix repo root confusion in read_file

**Estimated Effort:** 2-3 hours

### Task Package 4.1: Reproduce and Diagnose Bug

**Scope:** Understand when/why read_file gets confused about repo root

**Files to Analyze:**
- `tools/read_file.py` (repo root resolution logic)
- `config/repo_config.py` (RepoDiscovery)

**Investigation Steps:**
1. Search read_file.py for repo root resolution calls
2. Check how `repo_root` is determined (hardcoded vs discovered vs passed)
3. Identify edge cases where repo root might be incorrect
4. Create reproducible test case

**Verification:**
- [ ] Bug reproduced in test
- [ ] Root cause documented in PROGRESS_LOG

**Out of Scope:**
- Do NOT fix yet (diagnosis phase only)

---

### Task Package 4.2: Implement Fix

**Scope:** Fix repo root resolution based on diagnosis findings

**Files to Modify:**
- (TBD based on diagnosis - likely `tools/read_file.py`)

**Specifications:**
- (TBD based on root cause)
- Ensure consistent repo root resolution across all file operations
- Add validation to catch mismatches early

**Verification:**
- [ ] Bug reproduction test now passes
- [ ] All existing read_file tests still pass
- [ ] Repo root correctly resolved in edge cases

**Out of Scope:**
- Do NOT refactor entire read_file tool

---

**Phase 4 Deliverables:**
- Repo root bug identified and fixed
- Test coverage for edge cases

**Dependencies:** None (can run parallel to other phases)

**Notes:** Phase 4 is lower priority - can be deferred if timeline is tight.

---
## Phase 5 — Integration & Testing
<!-- ID: phase_5 -->

**Objective:** Comprehensive testing and documentation

**Estimated Effort:** 4-6 hours

### Task Package 5.1: Integration Tests

**Scope:** End-to-end tests for search and edit_file workflows

**Files to Create:**
- `tests/test_search_integration.py` (new file)
- `tests/test_edit_file_integration.py` (new file)

**Specifications:**
1. **search integration tests:**
   - Test real multi-file search across test fixtures
   - Test all output modes
   - Test filtering (glob, type)
   - Test limits enforcement
2. **edit_file integration tests:**
   - Test full workflow: read → edit (dry-run) → edit (commit)
   - Test read-before-edit enforcement
   - Test backup creation
   - Test error cases

**Verification:**
- [ ] `pytest tests/test_search_integration.py` passes (≥90% coverage)
- [ ] `pytest tests/test_edit_file_integration.py` passes (≥90% coverage)
- [ ] All integration scenarios covered

**Out of Scope:**
- Do NOT add performance benchmarks yet

---

### Task Package 5.2: Update Documentation

**Scope:** Update all documentation for new tools

**Files to Modify:**
- `docs/Scribe_Usage.md` (add search and edit_file sections)
- `CLAUDE.md` (update file operation policy)
- `.codex/skills/scribe-mcp-usage/references/` (add new tool refs)

**Specifications:**
1. Add complete tool documentation to Scribe_Usage.md:
   - Tool signatures with all parameters
   - Usage examples for common patterns
   - Security notes and best practices
2. Update CLAUDE.md policy:
   - Replace "use Bash grep" with "use search tool"
   - Replace "use Bash sed" with "use edit_file tool"
3. Add reference docs to skill

**Verification:**
- [ ] Documentation complete and accurate
- [ ] Examples tested and working
- [ ] Policy clearly stated

**Out of Scope:**
- Do NOT create video tutorials

---

### Task Package 5.3: Security Audit

**Scope:** Verify security model is sound

**Review Checklist:**
- [ ] PathSandbox enforced for all file access (search and edit_file)
- [ ] No path traversal vulnerabilities
- [ ] Binary file detection prevents code execution
- [ ] Backup mechanism cannot be abused
- [ ] Error messages don't leak sensitive paths
- [ ] Read-before-edit prevents blind destructive edits

**Files to Review:**
- `tools/search.py`
- `tools/edit_file.py`
- Integration with `security/sandbox.py`

**Verification:**
- [ ] Security review checklist completed
- [ ] No vulnerabilities identified
- [ ] Any issues found are fixed

**Out of Scope:**
- Do NOT perform full penetration testing

---

**Phase 5 Deliverables:**
- Comprehensive test coverage (≥90%)
- Complete documentation
- Security audit passed

**Dependencies:** All previous phases

**Notes:** Phase 5 is the quality gate before considering tools production-ready.

---
## Milestone Tracking
<!-- ID: milestone_tracking -->

| Milestone | Target | Status | Evidence |
|-----------|--------|--------|----------|
| Phase 0: Foundation Complete | - | ⏳ Planned | TBD |
| Phase 1: search MVP Complete | - | ⏳ Planned | TBD |
| Phase 2: search Advanced Complete | - | ⏳ Planned | TBD |
| Phase 3: edit_file Complete | - | ⏳ Planned | TBD |
| Phase 4: read_file Bug Fixed | - | ⏳ Planned | TBD |
| Phase 5: Integration Complete | - | ⏳ Planned | TBD |
| **ALL TOOLS PRODUCTION READY** | - | ⏳ Planned | Test coverage ≥90%, docs complete, security audit passed |

Update status and evidence as work progresses. Link to PROGRESS_LOG entries and commits.

---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->

*To be filled after each phase completes.*

**Format:**
- **Phase X Complete:** Date, key learnings, blockers encountered, scope adjustments
- **Example:** "Phase 1 complete 2026-01-30. Learned: File traversal is CPU-intensive for large repos. Added file count limit. Increased estimate for Phase 2 by 2 hours."

---
