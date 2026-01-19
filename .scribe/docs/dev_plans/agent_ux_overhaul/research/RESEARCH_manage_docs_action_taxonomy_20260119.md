
# manage_docs Action Taxonomy Research

**Research Date:** 2026-01-19
**Scope:** Complete action classification, parameter requirements, overlap analysis
**Confidence:** 0.95 (verified through direct code inspection)
**Lead:** ResearchAgent

---

## Executive Summary
<!-- ID: executive_summary -->

The `manage_docs` tool has **18 valid actions** with inconsistent parameter requirements and distributed handler logic across two files (tools/manage_docs.py and doc_management/manager.py).

**Primary Objective:** Create a complete map of manage_docs actions and identify complexity/confusion points affecting UX.

**Key Takeaways:**
- Parameter confusion (doc_category vs doc_name, patch vs edit vs content) causes user errors
- Three "replace_*" actions have similar names but wildly different parameter requirements
- Five "create_*" actions could be consolidated into one parameterized action
- Parameter healing happens silently, hiding bugs from users
- Auto-registration and parameter fallback behavior is undocumented

---

## Research Scope
<!-- ID: research_scope -->

**Research Lead:** ResearchAgent

**Investigation Window:** 2026-01-19 02:04 — 2026-01-19 07:04 UTC

**Focus Areas:**
- [x] All 18 valid actions and their handler locations
- [x] Parameter requirements per action (required vs optional vs conditional)
- [x] Parameter confusion points and overlaps
- [x] Action similarities and consolidation opportunities
- [x] Documentation vs reality gaps
- [x] Auto-correction and healing behavior

**Investigation Methods:**
- Direct code inspection of tools/manage_docs.py (3179 lines)
- Analysis of doc_management/manager.py (2467 lines)
- Parameter healing function analysis (_heal_manage_docs_parameters)
- Action dispatch mapping across multiple handlers

**Constraints:**
- Analysis based on code inspection only; no runtime behavior testing
- Focus on current implementation, not historical context
- No user interview data available


---

## Findings
<!-- ID: findings -->

### Finding 1: 18 Valid Actions Split Across 4 Categories

**Summary:** The manage_docs tool implements 18 distinct actions organized into 4 functional categories with different handler locations.

**Evidence:**
- Valid actions enum: tools/manage_docs.py lines 104-123
- Category 1 (Creation): create_doc, create_research_doc, create_bug_report, create_review_report, create_agent_report_card (5 actions)
- Category 2 (Editing): replace_section, append, replace_range, replace_text, apply_patch, status_update (6 actions)
- Category 3 (Transformation): normalize_headers, generate_toc, validate_crosslinks (3 actions)
- Category 4 (Inspection): list_sections, list_checklist_items, search, batch (4 actions)
- Creation actions handled by _handle_special_document_creation (line 1339)
- Editing actions handled by apply_doc_change (manager.py line 124)
- Inspection actions have individual handlers (lines 1354-1579)

**Confidence:** 0.99 (direct enum verification)

---

### Finding 2: doc_name vs doc_category Confusion

**Summary:** Users confuse the unique identifier (doc_name) with the type hint (doc_category), but they serve completely different purposes.

**Evidence:**
- doc_name is REQUIRED and acts as registry key (line 1594: `allowed_docs = set((project.get("docs") or {}).keys())`)
- doc_category defaults to empty string with only string normalization, no enum validation (lines 141-145)
- Custom doc resolution uses doc_category to SELECT handler, then doc_name to FIND document (lines 1236-1276)
- Parameter healing only normalizes doc_category, never validates it (line 141-145)

**Impact:** Users think doc_category selects the document type, but it's just a string label. The actual document is found by doc_name.

**Confidence:** 0.85 (parameter usage inconsistency across codebase)

---

### Finding 3: patch vs edit vs content Parameter Overloading

**Summary:** Three content parameters exist with conflicting use cases and undocumented fallback behavior.

**Evidence:**
- Line 218: `patch_text = patch or content` — apply_patch accepts EITHER patch OR content, but mutual exclusion message says only "patch or edit"
- Line 250-252: Explicit conflict check: `if patch_used and edit: raise DocumentOperationError(...)`
- Line 378-381: replace_text requires metadata.find/replace, not content parameter
- apply_patch smartly falls back from patch to content (line 218) but this isn't documented

**Impact:** Users don't know when to use each parameter. Silent fallback behavior causes confusion.

**Confidence:** 0.92 (code evidence of undocumented fallback)

---

### Finding 4: Action Similarity Confusion (replace_section, replace_range, replace_text)

**Summary:** Three actions all perform replacement but require completely different inputs and have inconsistent metadata requirements.

**Evidence:**
- replace_section (line 194-214): Uses section parameter (markdown header name), metadata.allow_append for scaffolding
- replace_range (line 359-376): Uses start_line/end_line parameters (1-indexed line numbers), optional metadata resolution
- replace_text (line 377-412): Requires metadata.find, metadata.replace, metadata.match_mode, metadata.scope, metadata.allow_no_match
- No shared logic between handlers; completely separate code paths

**Impact:** Users pick wrong action due to name similarity (all "replace"). Each action behaves differently.

**Confidence:** 0.95 (three distinct handler functions with different signatures)

---

### Finding 5: Metadata Parameter Overloading

**Summary:** Single metadata dict serves multiple purposes with action-specific keys that are undocumented.

**Evidence:**
- apply_patch: metadata.patch_mode, metadata.mode, metadata.allow_append, metadata.scaffold
- replace_text: metadata.find, metadata.replace, metadata.match_mode, metadata.scope, metadata.allow_no_match
- replace_range: metadata.start_line, metadata.end_line (can override params)
- append: metadata.position
- create_doc: metadata.frontmatter, metadata.overwrite, metadata.register_doc, metadata.register_as
- search: metadata.query, metadata.search_mode, metadata.project_slugs, metadata.fuzzy_threshold, etc.
- Line 378-395: replace_text ENTIRELY depends on metadata keys; no validation that required keys are present

**Impact:** Users must read source code to know what metadata keys their action needs.

**Confidence:** 0.98 (metadata handling spreads across lines 207-595 with different keys per action)

---

### Finding 6: Silent Parameter Healing and Auto-Correction

**Summary:** _heal_manage_docs_parameters (lines 80-296) silently auto-corrects inputs without explicit user feedback.

**Evidence:**
- Line 161-165: content auto-coerced to string if wrong type, healing_applied flag set
- Line 213-220: patch_mode auto-normalized to lowercase; invalid values replaced with None silently
- Line 239-240: start_line/end_line auto-coerced from string to int with healing message added
- Line 254-258: metadata normalized via separate _normalize_metadata_with_healing function
- Healing messages returned in response but users may not see them

**Impact:** Users don't realize their input was modified. Silent fixes hide bugs; could cause unexpected behavior.

**Confidence:** 0.98 (_heal_manage_docs_parameters function implementation)

---

### Finding 7: Auto-Registration Without User Knowledge

**Summary:** If doc_name not found during edit operations, system attempts auto-registration without user confirmation.

**Evidence:**
- Line 1299-1336: If action in EDIT_ACTIONS and doc_name not in registered docs, calls _auto_register_document
- Line 1309: Auto-registration attempted silently with minimal error handling
- Line 1314-1321: Context reloaded after auto-registration to reflect new state
- User is not asked for confirmation; happens as side effect of manage_docs call

**Impact:** Confuses project state management. Users don't expect documents to be registered automatically.

**Confidence:** 0.90 (lines 1299-1336 auto_register flow)

---

### Finding 8: Documentation vs Reality Gaps (4 instances)

**Summary:** Multiple discrepancies between documented behavior and actual implementation.

**Evidence:**

1. **apply_patch Content Fallback** (line 218)
   - Documented: requires patch parameter
   - Reality: falls back to content if patch is None

2. **doc_name Auto-Registration** (lines 1299-1336)
   - Documented: doc_name must be pre-registered
   - Reality: auto-registration happens if not found

3. **Search Mode Parameter Differences** (lines 1384-1571)
   - Documented: search requires metadata.query
   - Reality: semantic search doesn't require doc_name; exact/fuzzy search REQUIRES doc_name

4. **Status Update Metadata** (line 216)
   - Documented: status_update requires section
   - Reality: metadata is passed but no keys are documented

**Confidence:** 0.92 (code inspection shows actual behavior differs from docstring)

---

### Finding 9: Action Consolidation Opportunities

**Summary:** Three groups of actions could be merged into single parameterized actions.

**Evidence:**

1. **replace_* actions** (3 actions)
   - replace_section, replace_range, replace_text all modify content
   - Could merge into single `replace` action with mode="section|range|text"

2. **create_* actions** (5 actions)
   - create_doc, create_research_doc, create_bug_report, create_review_report, create_agent_report_card
   - All perform file creation with different metadata schemas
   - Could merge into single `create` action with doc_type parameter

3. **list/inspect actions** (2 actions)
   - list_sections, list_checklist_items both read-only
   - Could merge into single `inspect` action with inspection_type parameter

**Impact:** Reduces cognitive load from 18 actions to ~12, simplifies parameter requirements.

**Confidence:** 0.95 (action names and signatures clearly show overlap)

---

### Finding 10: Rarely-Used Actions

**Summary:** Four actions have low frequency use cases and could be moved to separate tools.

**Evidence:**
- validate_crosslinks (line 429-431): Read-only inspection, no file modification, specialized use case
- generate_toc (line 357-358): Markdown-specific operation, limited applicability
- normalize_headers (line 355-356): Maintenance operation, low-frequency use
- status_update (line 215-216): Checklist-only operation, narrow scope

**Impact:** These actions add complexity without proportional utility. Could simplify manage_docs by moving them.

**Confidence:** 0.80 (implementation analysis suggests low usage, not verified by metrics)

---

## Technical Analysis
<!-- ID: technical_analysis -->

**Code Patterns Identified:**
- Parameter healing pattern: Inputs auto-corrected via _heal_manage_docs_parameters before use
- Dispatch pattern: Action type determines which handler is called (if/elif chain starting line 1354)
- Metadata catch-all pattern: Multiple action-specific parameters stuffed into single metadata dict
- Handler distribution: Creation actions use special handler, editing actions use apply_doc_change, inspection actions are individual
- Auto-registration pattern: Documents registered on-demand if not found (lines 1299-1336)

**System Interactions:**
- manage_docs -> apply_doc_change (doc_management/manager.py) for editing operations
- manage_docs -> _handle_special_document_creation for create_* operations
- Custom doc resolution (lines 1236-1296) integrates with custom document path discovery
- Vector indexing integration (lines 1737-1746) indexes documents for semantic search
- Storage backend integration (lines 1680-1707) records document changes to database

**Risk Assessment:**
- Silent parameter healing could hide user errors or create unexpected behavior
- Auto-registration happens without user knowledge, could cause confusion about project state
- Metadata overloading makes it easy to miss required keys; no TypedDict or strict validation
- Action similarity (replace_* naming) could cause users to pick wrong action
- Parameter fallback (apply_patch -> content) is undocumented, could cause confusion

---

## Recommendations
<!-- ID: recommendations -->

### Priority 1: Parameter Clarity (HIGH)
1. **Eliminate doc_category ambiguity**
   - Make strict enum validation or rename to doc_type_hint
   - Document that doc_category is type-hint only; doc_name is unique identifier

2. **Clarify patch/edit/content behavior**
   - Document fallback: apply_patch(patch=None) -> use content parameter
   - Make mutual exclusion explicit in parameter validation

3. **Enumerate metadata keys per action**
   - Create TypedDict or strict schema validation per action
   - Validate that required metadata keys are present before operation
   - Return clear error if metadata keys missing with hint on required keys

### Priority 2: Action Consolidation (MEDIUM)
1. **Merge replace_* actions**
   - Single `replace` action with replace_mode parameter
   - Auto-infer mode from parameters provided (section vs start_line vs pattern)

2. **Merge create_* actions**
   - Single `create` action with doc_type parameter
   - Unified metadata schema with type-specific fields

3. **Merge list/inspect actions**
   - Single `inspect` action with inspection_type parameter
   - Consistent response format across different inspection types

### Priority 3: Documentation Alignment (MEDIUM)
1. **Document auto-registration trigger**
   - Document when and why auto-registration happens
   - Explain how users can prevent auto-registration

2. **Document parameter fallback behavior**
   - apply_patch: patch -> content fallback
   - Search: doc_name optional for semantic mode

3. **Document search mode differences**
   - Semantic search (all projects, doc_name optional)
   - Exact/fuzzy search (single document, doc_name required)

4. **Document healing vs validation**
   - Explain which parameters are auto-corrected (healing)
   - Explain which parameters are validated (rejection)

### Priority 4: UX Hardening (LOW-MEDIUM)
1. **Require doc_name explicitly**
   - Don't auto-register without explicit user action
   - Fail fast with clear error if doc_name missing

2. **Add action pre-flight checks**
   - Validate all required metadata keys before applying change
   - Return error with hint on missing keys

3. **Return explicit healing report**
   - Always report what was auto-corrected
   - Include confidence score on healing actions

4. **Add action examples**
   - Minimal working example per action
   - Show all required and optional parameters

---

## Appendix
<!-- ID: appendix -->

**Code References:**
- tools/manage_docs.py: Main manage_docs function entry point (line 1102)
- doc_management/manager.py: apply_doc_change dispatch and handlers (line 124)
- _heal_manage_docs_parameters: Parameter healing logic (lines 80-296 in tools/manage_docs.py)
- _handle_special_document_creation: Creation action handler (line 2334 in tools/manage_docs.py)
- Valid actions enum: lines 104-123 in tools/manage_docs.py

**Related Documents:**
- slugify_standardization project (cross-referenced)
- manage_docs UX fix project (this research informs it)

**Metrics:**
- 18 valid actions (verified)
- 5 creation actions, 6 editing actions, 3 transformation actions, 4 inspection actions
- Parameter healing: >10 auto-correction patterns identified
- Metadata keys: >40 distinct keys across actions (no centralized schema)