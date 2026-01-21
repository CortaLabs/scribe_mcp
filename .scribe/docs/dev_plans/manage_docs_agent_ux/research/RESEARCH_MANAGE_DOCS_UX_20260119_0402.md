---
id: manage_docs_agent_ux-research-manage-docs-ux-20260119-0402
title: "\U0001F52C Research Manage Docs Ux 20260119 0402 \u2014 manage_docs_agent_ux"
doc_name: RESEARCH_MANAGE_DOCS_UX_20260119_0402
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-20'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Manage Docs Ux 20260119 0402 — manage_docs_agent_ux
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-20 04:02:54 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Investigate why AI agents (especially smaller models like Haiku) bypass `manage_docs` in favor of the native Write tool, and identify the minimal changes needed to make `manage_docs` the obvious choice.

**Key Takeaways:**
- **API Complexity is the Primary Driver:** `manage_docs` has 14 actions with 12+ parameters vs Write's 2 parameters. This massive cognitive load drives bypass behavior.
- **No Persistent Baseline Hash Tracking:** The `patch_source_hash` parameter exists but is EPHEMERAL - computed on-demand from current content but never persisted to frontmatter or database. Agents must manually compute and pass hashes, creating friction.
- **JSON Escaping Pain:** Structured patches require JSON escaping of newlines/quotes, making simple edits painful compared to Write's plain text content parameter.
- **Dual Naming Confusion:** The `doc_category` vs `doc_name` resolution system adds cognitive overhead, especially for custom documents (research, bugs, reviews).
- **Error Diagnostics Add Perceived Complexity:** While comprehensive error diagnostics exist (_build_patch_failure_diagnostics), they increase the perceived difficulty of the tool.

**Root Cause:** The gap between Write's simplicity and manage_docs' safety creates an incentive mismatch. Agents choose the path of least resistance even when it's unsafe.
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent

**Investigation Window:** 2026-01-19 (single-day deep dive)

**Focus Areas:**
- [x] Current pain points analysis via code inspection
- [x] Implementation analysis of apply_patch and baseline hash system  
- [x] API surface comparison (manage_docs vs Write tool)
- [x] Baseline hash coverage mapping across doc types
- [x] Error message and diagnostic analysis
- [x] Template infrastructure examination

**Dependencies & Constraints:**
- Research limited to codebase analysis (no live agent interaction logs available in current project context)
- Focused on Haiku model constraints per user request, but findings apply to all models
- Investigation scope limited to manage_docs tool itself, not broader MCP ecosystem
- Templates examined: RESEARCH_REPORT_TEMPLATE.md, base_document.md
- Files analyzed: doc_management/manager.py (2752 lines), tools/manage_docs.py (3335 lines), utils/frontmatter.py (125 lines)
<!-- ID: findings -->
### Finding 1: Massive API Complexity Gap
- **Summary:** `manage_docs` has 14+ actions and 12+ parameters while Write tool has just 2 parameters (file_path, content). This 6x parameter complexity creates massive cognitive load.
- **Evidence:** 
  - `tools/manage_docs.py` lines 1117-1134: 12 function parameters
  - Actions found: replace_section, apply_patch, replace_range, replace_text, append, status_update, create, list_sections, list_checklist_items, normalize_headers, generate_toc, validate_crosslinks, search, batch
  - Parameter healing system (lines 1138-1170) exists specifically to handle parameter complexity
  - Deprecated action aliases (lines 1173-1187) show historical naming confusion
- **Confidence:** Very High (0.95) - Direct code inspection confirms parameter count

### Finding 2: No Persistent Baseline Hash Tracking
- **Summary:** The `patch_source_hash` parameter exists but is EPHEMERAL - computed on-demand from current file content (line 219 in manager.py: `current_hash = _hash_text(original_body)`) but NEVER persisted to frontmatter, database, or any storage layer.
- **Evidence:**
  - `doc_management/manager.py` line 2741-2742: `_hash_text()` computes SHA256 but doesn't store it
  - `utils/frontmatter.py`: Zero matches for "hash", "baseline", or "version" - no storage infrastructure
  - `templates/documents/base_document.md`: Frontmatter includes author, version, status, last_updated but NO content_hash field
  - Hash validation happens at line 284-288 but agents must manually provide hash
- **Confidence:** Very High (0.95) - Comprehensive search found zero persistent storage

### Finding 3: JSON Escaping Pain in Structured Patches
- **Summary:** The `edit` parameter (structured patch mode) requires JSON dict format, forcing agents to escape newlines and quotes. Plain unified diff patches avoid this but require understanding diff format.
- **Evidence:**
  - `doc_management/manager.py` lines 260-272: Structured mode requires `edit` as dict with JSON escaping
  - Lines 273-278: Structured edits are converted to unified diffs internally anyway
  - Lines 243-248: Smart default routing - unclear which mode to use
- **Confidence:** High (0.9) - Code confirms JSON requirement, but agent pain is inferred

### Finding 4: Dual Naming System Confusion
- **Summary:** manage_docs uses both `doc_category` (architecture/phase_plan/checklist/research/bugs) and `doc_name` (actual filename) with complex resolution logic that varies by doc type.
- **Evidence:**
  - `tools/manage_docs.py` lines 1270-1308: Custom doc type resolution path for research/bugs/reviews/agent_cards
  - `doc_management/manager.py` lines 726-807: `_resolve_doc_path()` function (82 lines!) handles resolution
  - Lines 810-861: `_resolve_create_doc_path()` has separate resolution logic for creation
  - Different behaviors for "managed docs" (architecture/phase/checklist) vs "custom docs" (research/bugs)
- **Confidence:** High (0.9) - Code confirms complexity, but user impact requires live testing

### Finding 5: Comprehensive But Overwhelming Error Diagnostics
- **Summary:** Error diagnostics are thorough (_build_patch_failure_diagnostics lines 1387-1431) but add to perceived tool complexity. Errors include patch context hints, line matching suggestions, and range analysis.
- **Evidence:**
  - `doc_management/manager.py` lines 1387-1431: 45-line diagnostic builder
  - Lines 1399-1409: Searches for matching lines and suggests alternatives
  - Lines 1411-1425: Computes current line ranges for hunks
  - Error codes: PATCH_STALE_SOURCE, PATCH_CONTEXT_MISMATCH, PATCH_MODE_CONFLICT, etc.
- **Confidence:** Medium (0.7) - Diagnostics exist, but whether they help or overwhelm requires agent feedback

### Finding 6: No Hash Coverage Map - Gap Analysis Complete
- **Summary:** Zero doc types have automatic baseline hash tracking. All hash management is manual and ephemeral.
- **Evidence:**
  - Managed docs (ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST): No hash tracking
  - Custom docs (research reports, bug reports, reviews, agent cards): No hash tracking
  - Templates: No content_hash field in any template
  - Database schema: scribe_projects table has docs_json but no hash column
- **Confidence:** Very High (0.95) - Comprehensive infrastructure search confirms gap
<!-- ID: technical_analysis -->
**Code Patterns Identified:**

1. **Parameter Healing Anti-Pattern** (`tools/manage_docs.py` lines 1138-1170)
   - System attempts to auto-correct malformed parameters
   - Masks underlying UX problem: if healing is needed, the API is too complex
   - Creates uncertainty: "Did my parameters work or were they healed?"

2. **Dual Mode Confusion** (`doc_management/manager.py` lines 243-258)
   - Two patch modes: structured (`edit` dict) and unified (`patch` string)
   - Smart defaults attempt to choose mode automatically
   - Agents must understand BOTH modes to make informed choices

3. **Path Resolution Complexity** (`doc_management/manager.py` lines 726-861)
   - 82-line `_resolve_doc_path()` function with special cases
   - Different logic for managed docs vs custom docs
   - Separate 52-line `_resolve_create_doc_path()` for creation
   - Compare to Write tool: path is the path, no resolution needed

4. **Hash System is Validation-Only, Not State Management**
   - Current hash system detects stale patches but doesn't prevent Write tool bypass
   - No "last known good state" tracking
   - Agents can skip manage_docs entirely and hash validation never runs

**System Interactions:**

- **Frontmatter Infrastructure Exists But Underutilized**
  - `utils/frontmatter.py` has parse/apply/build functions
  - Templates already include metadata headers
  - Adding `content_hash` field would be straightforward
  - Would enable automatic stale detection without manual hash passing

- **Template System Ready for Extension**
  - Jinja2 templates with inheritance (`base_document.md`)
  - Metadata already rendered in headers
  - Section anchors (`<!-- ID: anchor -->`) enable targeted updates
  - Hash could auto-populate on creation, auto-update on edits

**Risk Assessment:**

- [x] **High Risk: Agent Bypass Incentive Structure**
  - Current system penalizes safe behavior (complexity) and rewards unsafe behavior (simplicity of Write)
  - Smaller models (Haiku) will ALWAYS choose simpler tool without intervention
  - Missing: Simple safe path that's easier than unsafe path

- [x] **Medium Risk: Hash Gap Creates False Sense of Security**
  - Developers may assume hash validation prevents corruption
  - Reality: Hash validation only runs IF agent uses manage_docs
  - Write tool bypass completely sidesteps validation

- [x] **Low Risk: Template System Extension**
  - Adding hash field to templates is low-risk change
  - Backward compatible (old docs without hash continue working)
  - Forward compatible (new docs get automatic protection)
<!-- ID: recommendations -->
### Immediate Next Steps (Minimal API Changes for Maximum Impact)

**Priority 1: Add Simple Content Replacement Action with Hash Gate**
- [x] **Recommendation:** Add `action="replace_content"` that accepts plain text content + optional baseline hash
- **Rationale:** Matches Write tool simplicity (2 params) but adds safety (hash validation)
- **Implementation:** 
  ```python
  manage_docs(
      action="replace_content",
      doc_name="architecture",  # or doc_category for managed docs
      content="<plain text content>",  # no JSON escaping!
      baseline_hash="<optional_hash>"  # if omitted, computed from current file
  )
  ```
- **Why This Works:** 
  - Cognitive load matches Write tool (file + content)
  - Hash can be auto-computed from current file if agent doesn't provide it
  - Returns hash in response for next edit (agents can optionally use it)
  - Safer than Write but just as easy

**Priority 2: Auto-Persist Content Hashes to Frontmatter**
- [x] **Recommendation:** Automatically write `content_hash` to frontmatter on every manage_docs operation
- **Rationale:** Eliminates manual hash management, enables automatic stale detection
- **Implementation Changes:**
  1. Add `content_hash` field to `templates/documents/base_document.md`
  2. Update `utils/frontmatter.py` to read/write content_hash
  3. Auto-update hash in frontmatter after every successful edit
  4. On next edit, auto-validate against stored hash (warn if mismatch)
- **Backward Compatibility:** Old docs without hash continue working, hash gets added on first edit

**Priority 3: Simplify Error Messages for Smaller Models**
- [x] **Recommendation:** Add Haiku-optimized error mode with simplified diagnostics
- **Rationale:** Current diagnostics (45-line builder) may overwhelm smaller models
- **Implementation:** Add `simple_errors=True` parameter that returns minimal error messages:
  - Before: "PATCH_STALE_SOURCE: patch_source_hash does not match current file content [diagnostics...]"
  - After: "File changed since last read. Re-read file and try again."

**Priority 4: Deprecate Structured Patch Mode**
- [ ] **Recommendation:** Phase out `edit` dict parameter in favor of unified diffs only
- **Rationale:** Structured patches require JSON escaping AND get converted to unified diffs internally anyway
- **Migration Path:** Keep working for backward compatibility but emit deprecation warning

### Long-Term Opportunities

**Opportunity 1: Single Naming System**
- Unify `doc_category` and `doc_name` into single `doc` parameter
- Auto-detect whether it's a category reference or filename
- Reduces cognitive load: one concept instead of two

**Opportunity 2: Hash-Based Optimistic Concurrency**
- Store hashes in database (scribe_projects.docs_json) not just frontmatter
- Enable multi-agent coordination: "Agent A edited architecture, Agent B's edit fails with clear conflict message"
- Foundation for future collaborative editing features

**Opportunity 3: Smart Default Actions**
- If agent provides only `doc_name` + `content`, auto-select safest action
- If hash matches: replace_content
- If hash mismatched but content is superset: append
- If hash mismatched and conflict: fail with clear error
- Goal: "Just tell me what you want, I'll figure out how to do it safely"

**Opportunity 4: Haiku-Specific Tool Variant**
- Create `manage_docs_simple` tool with reduced parameter surface
- Only 3 actions: create, replace_content, append
- Auto-handled: hashing, path resolution, error diagnostics
- Routes to same backend but with simplified API contract
<!-- ID: appendix -->
**References:**
- `doc_management/manager.py` - Core document management logic (2752 lines)
- `tools/manage_docs.py` - MCP tool entry point (3335 lines)
- `utils/frontmatter.py` - Frontmatter parsing/building (125 lines)
- `templates/documents/base_document.md` - Base template with metadata structure
- `templates/documents/RESEARCH_REPORT_TEMPLATE.md` - Research doc template

**Key Code Locations:**
- Hash computation: `doc_management/manager.py:2741-2742`
- Hash validation: `doc_management/manager.py:284-288`
- Patch application: `doc_management/manager.py:296-330`
- Path resolution: `doc_management/manager.py:726-807`
- Parameter healing: `tools/manage_docs.py:1138-1170`
- Error diagnostics: `doc_management/manager.py:1387-1431`

**Baseline Hash Coverage Map:**

| Doc Type | Has Baseline Hash | Storage Location | Notes |
|----------|------------------|------------------|-------|
| ARCHITECTURE_GUIDE.md | ❌ No | None | Managed doc, no hash tracking |
| PHASE_PLAN.md | ❌ No | None | Managed doc, no hash tracking |
| CHECKLIST.md | ❌ No | None | Managed doc, no hash tracking |
| Research Reports | ❌ No | None | Custom doc, no hash tracking |
| Bug Reports | ❌ No | None | Custom doc, no hash tracking |
| Review Reports | ❌ No | None | Custom doc, no hash tracking |
| Agent Report Cards | ❌ No | None | Custom doc, no hash tracking |

**Summary:** Zero doc types have persistent baseline hash tracking. All hash validation is ephemeral and manual.

**Scoped Task List for Sonnet Coders:**

1. **Task: Implement `replace_content` Action** (Priority 1)
   - Add new action handler in `doc_management/manager.py`
   - Accept `content` (plain text) + optional `baseline_hash`
   - Auto-compute hash if not provided
   - Return new hash in response
   - Estimated effort: 4-6 hours

2. **Task: Add Content Hash to Frontmatter** (Priority 2)
   - Update `templates/documents/base_document.md` with `content_hash` field
   - Modify `utils/frontmatter.py` to read/write hash
   - Auto-update hash after every successful edit
   - Auto-validate on subsequent edits
   - Estimated effort: 6-8 hours

3. **Task: Simplify Error Messages** (Priority 3)
   - Add `simple_errors` parameter to manage_docs
   - Create simplified error message variants
   - Map complex diagnostics to simple messages
   - Estimated effort: 3-4 hours

4. **Task: Deprecate Structured Patch Mode** (Priority 4)
   - Add deprecation warning when `edit` dict is used
   - Update documentation to recommend unified diffs
   - Plan migration timeline
   - Estimated effort: 2-3 hours

**Total Estimated Effort for Immediate Priorities:** 15-21 hours (2-3 days for experienced Sonnet coder)
