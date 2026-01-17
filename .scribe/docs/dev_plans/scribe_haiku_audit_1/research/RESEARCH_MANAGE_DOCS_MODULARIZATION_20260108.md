---
id: scribe_haiku_audit_1-research-manage-docs-modularization-20260108
title: 'Modularization Analysis: tools/manage_docs.py'
doc_name: RESEARCH_MANAGE_DOCS_MODULARIZATION_20260108
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-08'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Modularization Analysis: tools/manage_docs.py

## Summary

- **Lines:** 3,079
- **Classes:** 1 helper class
- **Functions:** 28 functions
- **Complexity Rating:** Critical (multiple unrelated subsystems in single file)
- **Extraction Candidates:** 3 high-impact modules identified

---

## Logical Clusters Identified

### Cluster 1: Parameter Healing & Normalization

**Lines:** 52-295 (~244 LOC)

**Functions:**
- `_normalize_metadata_with_healing()` (lines 52-76, 25 LOC)
- `_heal_manage_docs_parameters()` (lines 79-295, 217 LOC) - HEAVYWEIGHT
- `_add_healing_info_to_response()` (lines 298-310, 13 LOC)
- `_coerce_line_number()` (nested at lines 224-236, 13 LOC)

**Purpose:** Bulletproof parameter validation and auto-correction for all manage_docs inputs using Phase 1 exception healing pattern.

**Extraction Candidate:** YES

**Proposed Module:** `tools/manage_docs_parameter_healing.py`

**Dependencies:**
- `BulletproofParameterCorrector` from utils
- `coerce_metadata_mapping()` from shared.logging_utils
- Standard library (json, str operations)

**Dependents:**
- Main `manage_docs()` function (line 1199: healing applied)
- Special document creation (line 2352: metadata healing)
- Response building throughout manage_docs

**Rationale:** This is a self-contained, heavily tested healing subsystem with zero interdependencies on doc operations. It converts malformed parameters into valid shapes. Can be extracted as pure utility functions with no side effects.

---

### Cluster 2: Vector Search Configuration & Detection

**Lines:** 426-542 (~117 LOC)

**Functions:**
- `_get_vector_search_defaults()` (lines 426-443, 18 LOC)
- `_parse_int()` (lines 446-454, 9 LOC)
- `_resolve_semantic_limits()` (lines 457-490, 34 LOC)
- `_get_vector_indexer()` (lines 493-502, 10 LOC)
- `_vector_indexing_enabled()` (lines 505-512, 8 LOC)
- `_vector_search_enabled()` (lines 515-529, 15 LOC)
- `_normalize_doc_search_mode()` (lines 532-542, 11 LOC)

**Purpose:** Detect and configure vector search capabilities; read config, validate enabled state, resolve search parameters.

**Extraction Candidate:** MAYBE (lower priority)

**Proposed Module:** `utils/vector_search_config.py`

**Dependencies:**
- `RepoDiscovery` from config.repo_config
- `load_vector_config()` from config.vector_config
- Standard library (type coercion, dict operations)

**Dependents:**
- Search action handler (lines 1388-1430: vector search enablement checks)
- Index function `_index_doc_for_vector()` (line 595: enabled check)
- Response building for semantic search

**Rationale:** This is tightly coupled to repo configuration discovery. If vector search becomes a separate subsystem, extract this. For now, low priority because it's only ~117 LOC and changes rarely.

---

### Cluster 3: Document Search & Line Matching

**Lines:** 545-578 (~34 LOC)

**Functions:**
- `_iter_doc_search_targets()` (lines 545-551, 7 LOC)
- `_search_doc_lines()` (lines 554-578, 25 LOC) - implements exact/fuzzy/semantic matching

**Purpose:** Search documents by line with multiple match modes (exact substring, fuzzy ratio, semantic embedding).

**Extraction Candidate:** NO (too small, tight coupling to search action)

**Rationale:** Only 34 LOC, used exclusively by search action handler. Not worth extracting.

---

### Cluster 4: Vector Indexing & Chunking

**Lines:** 313-380, 581-663 (~165 LOC)

**Functions:**
- `_hash_text()` (lines 313-315, 3 LOC)
- `_chunk_text_for_vector()` (lines 318-380, 63 LOC)
- `_generate_doc_entry_id()` (lines 383-385, 3 LOC)
- `_index_doc_for_vector()` (lines 581-663, 83 LOC) - CORE INDEXING LOGIC

**Purpose:** Break documents into vector-friendly chunks, hash content, and send to indexer plugin.

**Extraction Candidate:** YES (strategic)

**Proposed Module:** `tools/manage_docs_vector_indexing.py`

**Dependencies:**
- `_chunk_text_for_vector()` uses nested helpers for section/paragraph splitting
- `parse_frontmatter()` from utils.frontmatter
- `format_utc()` from utils.time
- Plugin registry (dynamic)

**Dependents:**
- Special document creation (line 1741: post-doc indexing)
- Main manage_docs (line 1734: async indexing)

**Rationale:** Clean vector-specific subsystem. Chunks, hashes, and indexes documents. Used by document lifecycle but independent of edit operations. Could be reused by other doc management tools.

---

### Cluster 5: File I/O & Validation

**Lines:** 665-740 (~76 LOC)

**Functions:**
- `_current_timestamp()` (lines 665-667, 3 LOC)
- `_write_file_atomically()` (lines 670-696, 27 LOC)
- `_validate_and_repair_index()` (lines 699-740, 42 LOC)

**Purpose:** Atomic file writes and index integrity checking.

**Extraction Candidate:** NO (too small, generic I/O)

**Rationale:** Only 76 LOC, generic file operations. Could live in utils but not urgent. Depends on doc_management.manager.

---

### Cluster 6: Special Document Creation (Research, Bug, Review, Agent Cards)

**Lines:** 758-1000, 2337-2600 (~600 LOC)

**Functions:**
- `_build_special_metadata()` (lines 758-774, 17 LOC)
- `_render_special_template()` (lines 777-806, 30 LOC)
- `_record_special_doc_change()` (lines 809-841, 33 LOC)
- `_parse_numeric_grade()` (lines 844-858, 15 LOC)
- `_record_agent_report_card_metadata()` (lines 861-888, 28 LOC)
- `_auto_register_document()` (lines 891-1000, 110 LOC)
- `_resolve_custom_doc_path()` (lines 1003-1097, 95 LOC)
- `_handle_special_document_creation()` (lines 2337-2600+, ~260 LOC) - HEAVYWEIGHT HANDLER
- `_update_research_index()` (lines 2604-2663, ~60 LOC)
- `_update_bug_index()` (lines 2664-2755, ~92 LOC)
- `_update_review_index()` (lines 2756-2848, ~93 LOC)
- `_update_agent_card_index()` (lines 2849-2944, ~96 LOC)

**Purpose:** Create research/bug/review/agent card documents with templating, indexing, and database integration.

**Extraction Candidate:** YES (HIGHEST PRIORITY)

**Proposed Module:** `tools/manage_docs_special_creation.py` (primary) + `utils/doc_index_updates.py` (secondary)

**Dependencies:**
- `apply_doc_change()` from doc_management.manager
- Template engine infrastructure
- `append_entry()` from tools.append_entry
- Storage backend (async operations)
- File I/O helpers

**Dependents:**
- Main `manage_docs()` function (line 1336-1349: routes to special creation)
- Special doc actions: create_research_doc, create_bug_report, create_review_report, create_agent_report_card

**Rationale:** **LARGEST AND MOST COHESIVE CLUSTER.** All 600+ LOC are devoted to a single concern: creating special document types with templates, indices, and database tracking. Complete subsystem that could be independently tested, evolved, and reused. Creates its own files, updates indices, and records metadata. Zero overlap with core document editing.

---

### Cluster 7: Action Handlers & Main Flow

**Lines:** 1100-1875, 2081-2336 (~800 LOC)

**Functions:**
- `manage_docs()` main function (lines 1100-1875, ~775 LOC) - ORCHESTRATOR
- `_handle_list_sections()` (lines 2081-2178, ~98 LOC)
- `_handle_list_checklist_items()` (lines 2181-2283, ~103 LOC)
- `_handle_batch_operations()` (lines 2284-2336, ~53 LOC)

**Purpose:** Route actions to handlers, manage project context, orchestrate document operations.

**Extraction Candidate:** NO (orchestration hub)

**Rationale:** Main coordination point. Cannot be extracted without refactoring the entire tool. Delegates to helpers but must remain as orchestrator.

---

### Cluster 8: Template Rendering & Review/Agent Card Reports

**Lines:** 2945-3079 (~135 LOC)

**Functions:**
- `_render_review_report_template()` (lines 2945-3009, ~65 LOC)
- `_render_agent_report_card_template()` (lines 3010-3079+, ~70 LOC)

**Purpose:** Render specialized Jinja2 templates for review reports and agent report cards.

**Extraction Candidate:** MAYBE (as part of special creation extraction)

**Rationale:** Already coupled to special document creation. Extract as submodule of manage_docs_special_creation.py.

---

## Shared Code Opportunities

1. **Vector indexing patterns** (lines 581-663) appear in `tools/append_entry.py` and `tools/read_file.py` - consider `shared/vector_indexing_base.py`

2. **File path resolution** (lines 1003-1097) duplicates logic in `doc_management/manager.py` - refactor to `utils/doc_path_resolver.py` and reuse everywhere

3. **Index updating pattern** (lines 2604-2944) is repeated 4 times (research, bug, review, agent) - extract to `utils/doc_index_builder.py` with pluggable generators

4. **Metadata normalization** (lines 52-295) should be reused in `tools/append_entry.py` and `tools/query_entries.py` instead of duplicating healing logic

---

## Existing Utilities to Leverage

1. **`tools/manage_docs_validation.py`** - Already exists! Check if it can absorb parameter healing functions (lines 52-295)

2. **`utils/` directory** - Parameter coercion utilities already scattered here; consolidate metadata healing into one place

3. **`doc_management/manager.py`** - Contains `_resolve_doc_path()` and `_resolve_create_doc_path()` which are duplicated/similar to `_resolve_custom_doc_path()` (lines 1003-1097)

4. **`shared/logging_utils.py`** - Already imports from here; consider moving all metadata coercion logic here

---

## Recommended Extractions (Priority Order)

### 1. **manage_docs_special_creation.py** (HIGHEST IMPACT)
- **Lines:** ~600 lines
- **Reason:** Largest cohesive cluster; complete subsystem for research/bug/review/agent card creation
- **Impact:** Reduces main file to ~2,500 LOC; enables independent evolution of special doc types
- **Risk:** Low - new module, no breaking changes
- **Estimated Effort:** 2-3 hours (extract + wire integration points)

### 2. **manage_docs_parameter_healing.py** (MEDIUM IMPACT)
- **Lines:** ~244 lines
- **Reason:** Self-contained Phase 1 exception healing; zero doc operation dependencies
- **Impact:** Reduces main file to ~2,800 LOC; consolidates all parameter correction logic
- **Risk:** Low - pure utility functions, isolated tests
- **Estimated Effort:** 1-2 hours (extract + update imports in main + special_creation)

### 3. **manage_docs_vector_indexing.py** (STRATEGIC)
- **Lines:** ~165 lines
- **Reason:** Clean vector-specific subsystem; reusable by other doc tools
- **Impact:** Clarifies separation between doc editing and vector operations
- **Risk:** Medium - requires async/plugin integration testing
- **Estimated Effort:** 2-3 hours (extract + test plugin integration + update indexing call sites)

---

## Risks & Considerations

1. **Tight coupling to doc_management.manager:** The main manage_docs function calls `apply_doc_change()` heavily. Extraction must preserve this coupling.

2. **Async/await patterns:** Special document creation uses async for template rendering and index updates. Must maintain async context when extracting.

3. **Plugin integration:** Vector indexing uses dynamic plugin discovery. Extract must preserve lazy loading pattern.

4. **Storage backend dependency:** Special creation and index updates depend on optional storage backend. Must handle None gracefully.

5. **Already extracted validation module:** `tools/manage_docs_validation.py` exists. Coordinate extraction to avoid duplication. Parameter healing should integrate with existing validation or replace it.

6. **Circular import risk:** If extracting to utils, ensure no circular dependencies with doc_management.manager or tools.append_entry.

---

## Questions for Architect

1. Should parameter healing (cluster 1) be merged into existing `manage_docs_validation.py`, or kept separate as `manage_docs_parameter_healing.py`?

2. For special document creation (cluster 6): Extract as single module or split by document type (research/bug/review separately)?

3. Vector indexing (cluster 4): Should this be extracted to `shared/` for reuse by append_entry, read_file, or keep tool-specific in manage_docs?

4. Path resolution duplication (lines 1003-1097 vs doc_management/manager): Should _resolve_custom_doc_path() be merged into doc_management/manager.py?

5. Index updating patterns (lines 2604-2944): Extract to abstract builder pattern in utils, or keep tool-specific implementations?

---

## Confidence Scores

- **Cluster 1 (Parameter Healing):** 0.95 - Should be extracted. Already isolated, self-contained.
- **Cluster 6 (Special Creation):** 0.90 - Should be extracted. Largest, most cohesive, independent subsystem.
- **Cluster 4 (Vector Indexing):** 0.80 - Could be extracted if vector search becomes priority. Medium priority.
- **Cluster 2 (Vector Config):** 0.60 - Low priority. Too small, tightly coupled to repo config.

---

*Research completed: 2026-01-08 08:27 UTC by ResearcherA1-Haiku*
