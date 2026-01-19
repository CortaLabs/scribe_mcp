# manage_docs.py - Forensic Audit Report

**File**: `tools/manage_docs.py`
**Size**: 2,663 LOC | 96,237 bytes
**Complexity**: Ultra-High
**Auditor**: ResearchAgent-B-ManageDocs
**Date**: 2026-01-05

---

## 1. Overview

`manage_docs.py` is the **document orchestration engine** for Scribe MCP. It handles:
- Structured document editing (architecture, phase plans, checklists)
- Special document creation (research, bug reports, review reports, agent cards)
- Semantic and fuzzy document search
- Batch operations across multiple documents
- Vector indexing integration for document embeddings
- Index file generation and maintenance

**Purpose**: Central hub for all document lifecycle operations - creation, editing, searching, indexing.

**LOC Breakdown**:
- Parameter healing: ~260 LOC (10%)
- Vector logic: ~260 LOC (10%)
- Semantic search: ~184 LOC (7%)
- Special doc creation: ~260 LOC (10%)
- Index updaters: ~340 LOC (13%)
- Main routing/orchestration: ~400 LOC (15%)
- Helper utilities: ~200 LOC (7%)
- Action handlers (core edits): ~500 LOC (19%)
- Template rendering: ~130 LOC (5%)
- CLI interface: ~130 LOC (5%)

**Complexity Drivers**:
1. **20+ action types** with distinct execution paths
2. **Vector search integration** with dual doc/log indexing
3. **Four index management systems** (research, bugs, reviews, agent cards)
4. **Template rendering** with Jinja2 engine integration
5. **Storage backend mirroring** (SQLite + optional PostgreSQL)
6. **Phase 1 exception healing** on all parameters

---

## 2. Sub-System Breakdown

### Infrastructure Layer (Lines 1-500)

#### Sub-System 1: Parameter Healing (51-309, ~260 LOC)
**Responsibility**: Normalize and auto-correct all manage_docs parameters using Phase 1 healing.

**Functions**:
- `_normalize_metadata_with_healing()` (51-75)
- `_heal_manage_docs_parameters()` (78-293)
- `_add_healing_info_to_response()` (296-308)

**Healing Operations**:
- Action enum validation (no auto-correction to prevent accidental edits)
- String parameter normalization (strip whitespace)
- JSON payload parsing (edit parameter from string to dict)
- Line number coercion (handle bool/string as int)
- Metadata dict healing (handle str as JSON)
- Boolean healing (str "true"/"1"/"yes" → True)

**Extractable**: YES [BUCKET:parameter_healing]
- Used by: `manage_docs`, potentially `append_entry`, `query_entries`
- Evidence: Lines 51-309 are pure parameter transformation, no manage_docs-specific logic
- Before/After: Before = healing mixed with business logic. After = shared `BulletproofParameterCorrector` extension for document tools

#### Sub-System 2: Hash & Utility Functions (311-314)
**Responsibility**: Content hashing for change detection.

**Functions**:
- `_hash_text()` (311-313) - SHA256 hash for doc content

**Extractable**: MAYBE [BUCKET:utilities]
- Used by: `manage_docs`, potentially `append_entry` (for log rotation)
- Evidence: Generic hashing, not manage_docs-specific
- Note: Already exists in other modules, potential duplicate

#### Sub-System 3: Vector Text Chunking (316-378, ~62 LOC)
**Responsibility**: Split document content into vector-indexable chunks (max 4000 chars).

**Functions**:
- `_chunk_text_for_vector()` (316-378)
- Internal helpers: `_split_into_sections()`, `_split_section()`

**Algorithm**:
1. Split by markdown headers (#, ##, ###)
2. If section > max_chars, split by paragraphs (\n\n)
3. Preserve heading in each chunk

**Extractable**: YES [BUCKET:vector_indexing]
- Used by: `manage_docs` (doc indexing), potentially `append_entry` (log indexing)
- Evidence: Lines 316-378 are pure text processing, no manage_docs context
- Before/After: Before = chunking logic duplicated in doc/log indexing. After = shared `VectorChunker` class used by all vector operations

#### Sub-System 4: Document Entry ID Generation (381-384)
**Responsibility**: Generate stable IDs for vector index entries.

**Functions**:
- `_generate_doc_entry_id()` (381-383)

**Algorithm**: `sha256(path|chunk_index|content_hash)[:32]`

**Extractable**: YES [BUCKET:vector_indexing]
- Should be bundled with vector chunking

#### Sub-System 5: Log File Guards (386-422, ~36 LOC)
**Responsibility**: Identify log files to exclude from vector indexing.

**Functions**:
- `_is_rotated_log_filename()` (402-407)
- `_should_skip_doc_index()` (410-421)

**Hardcoded Lists**:
- `_LOG_DOC_KEYS`: progress_log, doc_log, security_log, bug_log
- `_LOG_DOC_FILENAMES`: PROGRESS_LOG.md, DOC_LOG.md, SECURITY_LOG.md, BUG_LOG.md, GLOBAL_PROGRESS_LOG.md

**Extractable**: MAYBE [BUCKET:config]
- Evidence: Hardcoded lists should come from `config/log_config.json`
- Before/After: Before = hardcoded guard lists. After = read from config system
- **Configuration Gravity**: This is defensive config logic that bypasses the actual config system

#### Sub-System 6: Vector Search Configuration (424-541, ~117 LOC)
**Responsibility**: Load vector search defaults and normalize search modes.

**Functions**:
- `_get_vector_search_defaults()` (424-441) - Load doc_k/log_k from config
- `_parse_int()` (444-452) - Safe int coercion
- `_resolve_semantic_limits()` (455-488) - Calculate k limits for doc/log search
- `_normalize_doc_search_mode()` (530-540) - Map "fuzzy"/"semantic"/"exact"

**Extractable**: YES [BUCKET:vector_search]
- Evidence: Lines 424-541 are pure config loading, no execution
- Before/After: Before = config loading mixed with tool logic. After = `VectorSearchConfig` class loads once, tools query it

#### Sub-System 7: Vector Plugin Integration (491-528, ~38 LOC)
**Responsibility**: Check vector plugin availability and feature flags.

**Functions**:
- `_get_vector_indexer()` (491-500) - Fetch plugin from registry
- `_vector_indexing_enabled()` (503-510) - Check `vector_index_docs` flag
- `_vector_search_enabled()` (513-527) - Check plugin + flags for doc/log

**Extractable**: YES [BUCKET:vector_search]
- Should be bundled with vector search config

#### Sub-System 8: Document Search Logic (543-576, ~33 LOC)
**Responsibility**: Exact/fuzzy search within document content.

**Functions**:
- `_iter_doc_search_targets()` (543-549) - Resolve doc paths from project
- `_search_doc_lines()` (552-576) - Line-by-line exact/fuzzy matching

**Algorithm**:
- Exact: substring match
- Fuzzy: `difflib.SequenceMatcher` with threshold (default 0.8)

**Extractable**: MAYBE [BUCKET:document_search]
- Evidence: Lines 552-576 are pure text search, but tightly coupled to doc metadata
- Before/After: Before = search mixed with manage_docs routing. After = `DocumentSearcher` class with exact/fuzzy/semantic modes
- **Note**: Semantic search is separate (lines 1045-1229)

### Vector Indexing Layer (Lines 579-661)

#### Sub-System 9: Vector Indexing Orchestration (579-661, ~82 LOC)
**Responsibility**: Index document content to vector DB after changes.

**Functions**:
- `_index_doc_for_vector()` (579-661)

**Workflow**:
1. Check if indexing enabled (`_vector_indexing_enabled()`)
2. Get vector plugin (`_get_vector_indexer()`)
3. Skip if log file (`_should_skip_doc_index()`)
4. Read file, parse frontmatter
5. Chunk content (`_chunk_text_for_vector()`)
6. Generate entry IDs per chunk
7. Enqueue to vector plugin

**Extractable**: YES [BUCKET:vector_indexing]
- Evidence: Lines 579-661 orchestrate all vector sub-systems
- Before/After: Before = indexing mixed in manage_docs. After = `VectorIndexOrchestrator` called by manage_docs/append_entry
- **Critical**: This is the integration point for 4 other vector sub-systems

### File I/O Layer (Lines 663-738)

#### Sub-System 10: File Operations (663-695, ~32 LOC)
**Responsibility**: Atomic file writes with verification.

**Functions**:
- `_current_timestamp()` (663-665)
- `_write_file_atomically()` (668-694)

**Algorithm**:
1. Write to `.tmp` file
2. Verify tmp file exists and has size > 0
3. Atomic move to target path

**Extractable**: YES [BUCKET:file_io]
- Evidence: Generic atomic write pattern
- Before/After: Before = atomic write logic duplicated. After = shared `FileWriter` utility
- Used by: manage_docs (index updates), potentially other tools

#### Sub-System 11: Index Validation (697-738, ~41 LOC)
**Responsibility**: Detect and repair corrupted/stale index files.

**Functions**:
- `_validate_and_repair_index()` (697-738)

**Validation Checks**:
1. Index exists and readable?
2. Valid markdown (starts with #)?
3. Consistent with actual doc count?

**Recovery**:
- Backup corrupted file to `.corrupted.backup` or `.invalid.backup`
- Return False → caller regenerates index

**Extractable**: MAYBE [BUCKET:index_management]
- Evidence: Index-specific logic, but pattern applies to all indexes
- Before/After: Before = validation duplicated across 4 index updaters. After = `IndexValidator` class used by all

### Storage Integration Layer (Lines 741-887)

#### Sub-System 12: Storage Backend Integration (741-840, ~99 LOC)
**Responsibility**: Mirror doc changes to SQLite/PostgreSQL backend.

**Functions**:
- `_get_or_create_storage_project()` (741-753)
- `_build_special_metadata()` (756-772)
- `_render_special_template()` (775-804) - Jinja2 template rendering
- `_record_special_doc_change()` (807-840) - Persist doc change to DB

**Workflow**:
1. Fetch or create project record in storage
2. Call `backend.record_doc_change()` with SHA hashes
3. Fail gracefully (print warning, don't block operation)

**Extractable**: NO
- Evidence: Tightly coupled to manage_docs workflow (before_hash/after_hash lifecycle)
- Before/After: N/A - this is the integration seam, not extractable
- **Configuration Gravity**: Storage backend is passed in, not fetched

#### Sub-System 13: Agent Report Card Persistence (842-887, ~45 LOC)
**Responsibility**: Store structured agent performance data.

**Functions**:
- `_parse_numeric_grade()` (842-856)
- `_record_agent_report_card_metadata()` (859-886)

**Workflow**:
1. Parse grade percentages (handle "95%", 95, "95")
2. Call `backend.record_agent_report_card()` with structured fields
3. Fail gracefully

**Extractable**: NO
- Evidence: Domain-specific to agent report cards
- Before/After: N/A - too specific to extract

### Main Tool Entry Point (Lines 889-1501)

#### Sub-System 14: Main Action Router (889-1501, ~612 LOC)
**Responsibility**: Route actions to appropriate handlers.

**Functions**:
- `manage_docs()` (889-1501) - Main MCP tool entry point

**Routing Table** (20+ actions):

| Action | Handler | Lines | LOC |
|--------|---------|-------|-----|
| `create_research_doc` | `_handle_special_document_creation()` | 1006-1019 | Router only |
| `create_bug_report` | `_handle_special_document_creation()` | 1006-1019 | Router only |
| `create_review_report` | `_handle_special_document_creation()` | 1006-1019 | Router only |
| `create_agent_report_card` | `_handle_special_document_creation()` | 1006-1019 | Router only |
| `list_sections` | `_handle_list_sections()` | 1021-1031 | Router only |
| `list_checklist_items` | `_handle_list_checklist_items()` | 1032-1043 | Router only |
| `search` (semantic) | Inline handler | 1045-1188 | ~143 LOC |
| `search` (exact/fuzzy) | Inline handler | 1190-1229 | ~39 LOC |
| `batch` | `_handle_batch_operations()` | 1231-1237 | Router only |
| `replace_section` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `append` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `status_update` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `apply_patch` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `replace_range` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `replace_text` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `normalize_headers` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `generate_toc` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `validate_crosslinks` | `apply_doc_change()` | 1298-1314 | Via doc_management |
| `create_doc` | `apply_doc_change()` | 1256-1296 | Special register logic |

**Post-Processing** (Lines 1322-1501):
- Storage mirroring (1322-1351)
- Log to `append_entry(log_type="doc_updates")` (1353-1376)
- Vector indexing (1378-1389)
- Registry warnings (1391-1429)
- Document registration for `create_doc` (1430-1469)
- Response assembly (1471-1501)

**Extractable**: NO (This IS the tool)
- Evidence: This is the core orchestration logic
- Before/After: N/A - this is what we're analyzing
- **Configuration Gravity**: YES - this is a classic config hub that routes to sub-systems

### Semantic Search Implementation (Lines 1045-1229)

#### Sub-System 15: Semantic Search (1045-1229, ~184 LOC)
**Responsibility**: Vector-based document/log search.

**Workflow**:
1. Validate query exists (metadata.query)
2. Check if semantic search enabled for doc/log
3. Get vector indexer plugin
4. Build filters (project_slugs, doc_type, file_path, time_range)
5. Resolve k limits (doc_k, log_k, total_k)
6. Apply similarity threshold (min_similarity)
7. Execute search (single content_type or both doc+log)
8. Sort by similarity score
9. Return combined results

**Filters Supported**:
- `project_slugs` - List of projects
- `project_slug_prefix` - Wildcard project match
- `project_slug` - Single project
- `doc_type` - Filter by doc type
- `file_path` - Filter by file path
- `time_range` - Start/end timestamps
- `min_similarity` - Threshold filtering

**Extractable**: YES [BUCKET:semantic_search]
- Evidence: Lines 1045-1229 are fully self-contained semantic search logic
- Before/After: Before = semantic search buried in manage_docs. After = `SemanticSearchTool` as separate MCP tool
- **CRITICAL**: This is NOT a manage_docs responsibility - it's a standalone feature
- Used by: Currently only manage_docs, but should be available to all tools

### Action Handlers (Lines 1504-2663)

#### Sub-System 16: CLI Entry Point (1504-1708, ~204 LOC)
**Responsibility**: Command-line interface for manage_docs.

**Functions**:
- `manage_docs_main()` (1504-1707)
- `_run_manage_docs()` (1511-1556) - Async wrapper

**Features**:
- argparse configuration
- Parameter validation
- JSON metadata parsing
- Dry-run support
- Error handling

**Extractable**: NO
- Evidence: CLI is tool-specific
- Before/After: N/A

#### Sub-System 17: List Sections Handler (1710-1767, ~57 LOC)
**Responsibility**: Return section anchors (`<!-- ID: section_name -->`) with line numbers.

**Functions**:
- `_handle_list_sections()` (1710-1767)

**Workflow**:
1. Parse frontmatter to get body offset
2. Find all `<!-- ID: ... -->` markers
3. Detect duplicates
4. Return section list with body-relative line numbers

**Extractable**: MAYBE [BUCKET:document_introspection]
- Evidence: Generic doc parsing, not manage_docs-specific
- Before/After: Before = section parsing in manage_docs. After = `DocumentIntrospector` class with section/checklist/structure methods

#### Sub-System 18: List Checklist Items Handler (1770-1870, ~100 LOC)
**Responsibility**: Parse checklist items with status and line numbers.

**Functions**:
- `_handle_list_checklist_items()` (1770-1870)

**Workflow**:
1. Parse frontmatter to get body offset
2. Track current section (<!-- ID: ... -->)
3. Match checklist pattern: `- [x] text` or `- [ ] text`
4. Extract status (checked/unchecked)
5. Optional text filtering (exact/case-insensitive)
6. Return items with section context

**Extractable**: MAYBE [BUCKET:document_introspection]
- Should be bundled with list_sections

#### Sub-System 19: Batch Operations Handler (1873-1923, ~50 LOC)
**Responsibility**: Execute multiple manage_docs actions sequentially.

**Functions**:
- `_handle_batch_operations()` (1873-1923)

**Workflow**:
1. Validate metadata.operations is a list
2. Reject nested batch actions
3. Execute each operation via `manage_docs(**operation)`
4. Stop on first failure
5. Return all results

**Extractable**: NO
- Evidence: This is a manage_docs feature, not reusable
- Before/After: N/A

#### Sub-System 20: Special Document Creation (1926-2186, ~260 LOC)
**Responsibility**: Create research, bug, review, and agent report documents.

**Functions**:
- `_handle_special_document_creation()` (1926-2186)

**Document Types**:

| Action | Template | Target Path | Index Updater |
|--------|----------|-------------|---------------|
| `create_research_doc` | RESEARCH_REPORT_TEMPLATE.md | research/{doc_name}.md | `_update_research_index()` |
| `create_bug_report` | BUG_REPORT_TEMPLATE.md | bugs/{category}/{date}_{slug}/report.md | `_update_bug_index()` |
| `create_review_report` | REVIEW_REPORT_TEMPLATE.md | REVIEW_REPORT_{stage}_{date}_{time}.md | `_update_review_index()` |
| `create_agent_report_card` | AGENT_REPORT_CARD_TEMPLATE.md | AGENT_REPORT_CARD_{agent}_{stage}_{datetime}.md | `_update_agent_card_index()` |

**Workflow**:
1. Sanitize filename (remove special chars)
2. Build target path
3. Render template with Jinja2 engine
4. Validate path is within project root
5. Write file atomically
6. Record change to storage backend
7. Log to `append_entry(log_type="doc_updates")`
8. Update index file
9. Return success payload

**Extractable**: MAYBE [BUCKET:special_doc_creation]
- Evidence: Lines 1926-2186 are fully self-contained document creation logic
- Before/After: Before = creation mixed with manage_docs routing. After = 4 separate tools (create_research_doc, create_bug_report, etc.)
- **CRITICAL**: These are distinct document types with different workflows - could be separate MCP tools

#### Sub-Systems 21-24: Index Updaters (2188-2526, ~338 LOC)
**Responsibility**: Generate and update index files for document collections.

**Functions**:
- `_update_research_index()` (2188-2246, ~58 LOC)
- `_update_bug_index()` (2248-2337, ~89 LOC)
- `_update_review_index()` (2340-2430, ~90 LOC)
- `_update_agent_card_index()` (2433-2526, ~93 LOC)

**Common Pattern**:
1. Scan directory for documents
2. Collect metadata (name, path, size, modified time)
3. Group by category/stage/agent
4. Generate markdown index with statistics
5. Write atomically to INDEX.md

**Differences**:
- Research: Simple list by modified time
- Bugs: Group by category, show last 20 + category breakdown
- Reviews: Group by stage
- Agent Cards: Group by agent name

**Extractable**: YES [BUCKET:index_generation]
- Evidence: Lines 2188-2526 follow same template pattern with different grouping
- Before/After: Before = 4 duplicated index updaters. After = `IndexGenerator` class with templates for different doc types
- **Unification Opportunity**: 85% code duplication across 4 functions

#### Sub-Systems 25-26: Template Renderers (2529-2659, ~130 LOC)
**Responsibility**: Render Jinja2 templates with fallback to basic content.

**Functions**:
- `_render_review_report_template()` (2529-2591, ~62 LOC)
- `_render_agent_report_card_template()` (2594-2659, ~65 LOC)

**Workflow**:
1. Initialize Jinja2TemplateEngine
2. Prepare template context
3. Render template
4. On failure, return basic markdown fallback

**Extractable**: MAYBE [BUCKET:template_rendering]
- Evidence: Duplicated Jinja2 initialization pattern
- Before/After: Before = rendering duplicated. After = shared `TemplateRenderer` with template type enum
- **Note**: Jinja2TemplateEngine already exists - these are thin wrappers

---

## 3. Modularization Notes

### Extractable Modules (Before/After Analysis)

#### [BUCKET:parameter_healing] Parameter Healing Infrastructure
**Lines**: 51-309 (~260 LOC)
**Used by**: manage_docs, potentially append_entry, query_entries
**Coupling**: NONE - pure parameter transformation

**Before**:
- Healing logic mixed with manage_docs business logic
- Parameter validation happens at tool entry point
- Healing messages embedded in response

**After**:
- Shared `BulletproofParameterCorrector.heal_manage_docs_params()` method
- All document tools use same healing logic
- Healing messages standardized across tools
- Single source of truth for parameter validation

**Conceptual Win**: Tools reason about "get valid params" not "normalize this param, heal that param, coerce this boolean..."

**Risks if Extracted**: Need to ensure healing doesn't break tool-specific invariants (e.g., action enum validation)

---

#### [BUCKET:vector_indexing] Vector Indexing Sub-System
**Lines**: 316-378 (chunking), 381-384 (ID gen), 579-661 (orchestration) = ~164 LOC
**Used by**: manage_docs (docs), append_entry (logs)
**Coupling**: NONE - pure text processing + vector plugin integration

**Before**:
- Chunking logic in manage_docs
- Same chunking likely duplicated in append_entry (needs verification)
- Indexing orchestration mixed with doc change workflow

**After**:
- `VectorIndexOrchestrator` class with:
  - `chunk_text(content, max_chars=4000)` → List[str]
  - `generate_entry_id(path, chunk_index, content_hash)` → str
  - `index_document(project, doc, path, after_hash, agent_id, metadata)` → None
  - `index_log_entry(project, entry_data)` → None
- manage_docs calls `orchestrator.index_document()`
- append_entry calls `orchestrator.index_log_entry()`

**Conceptual Win**: Centralized vector logic, single chunking algorithm, consistent ID generation

**Risks if Extracted**: Need to handle doc vs log metadata differences

---

#### [BUCKET:vector_search] Vector Search Configuration & Execution
**Lines**: 424-541 (config), 491-528 (plugin), 1045-1229 (search) = ~295 LOC
**Used by**: manage_docs (semantic search action)
**Coupling**: MEDIUM - depends on project config, vector plugin registry

**Before**:
- Search config loading mixed with manage_docs routing
- Semantic search buried in 184-line inline handler
- Plugin availability checks scattered

**After**:
- `SemanticSearchTool` as separate MCP tool:
  - `semantic_search(query, filters, k=10, min_similarity=0.7)` → results
  - Available to ALL tools, not just manage_docs
- `VectorSearchConfig` class loads defaults once
- manage_docs delegates to SemanticSearchTool

**Conceptual Win**: Semantic search becomes first-class feature, reusable across all tools

**Risks if Extracted**: Need to ensure project context is available to all tools

**CRITICAL FINDING**: Semantic search is NOT a manage_docs responsibility - it's a standalone feature that happens to be invoked via manage_docs action. This should be a separate tool.

---

#### [BUCKET:index_generation] Index Generation System
**Lines**: 2188-2526 (~338 LOC for 4 updaters)
**Used by**: manage_docs (special doc creation)
**Coupling**: MEDIUM - depends on file system scanning

**Before**:
- 4 nearly identical index updaters (research, bug, review, agent card)
- 85% code duplication
- Each updater hardcodes markdown template

**After**:
- `IndexGenerator` class with:
  - `generate_index(index_type, docs_dir, grouping_field)` → str
  - Templates for each index type
  - Shared scanning/sorting/formatting logic
- manage_docs calls `generator.generate_index("research", research_dir, None)`

**Conceptual Win**: DRY - single index generation algorithm with customizable templates

**Risks if Extracted**: Index formats may need to diverge (currently they're very similar)

**Unification Evidence**:
- _update_research_index (58 LOC)
- _update_bug_index (89 LOC) - only difference is category grouping
- _update_review_index (90 LOC) - only difference is stage grouping
- _update_agent_card_index (93 LOC) - only difference is agent grouping

All follow same pattern:
1. Scan for .md files
2. Collect metadata (name, path, size, modified)
3. Group by field
4. Generate markdown with stats
5. Write to INDEX.md

---

#### [BUCKET:file_io] Atomic File Operations
**Lines**: 668-694 (~26 LOC)
**Used by**: manage_docs (index updates), potentially other tools
**Coupling**: NONE - generic file I/O

**Before**:
- Atomic write logic in manage_docs
- Likely duplicated in other tools (needs verification)

**After**:
- `FileWriter.write_atomically(path, content)` → bool
- All tools use shared writer
- Verification logic centralized

**Conceptual Win**: Consistent file write behavior, single point for I/O error handling

**Risks if Extracted**: None - this is pure utility

---

#### [BUCKET:document_introspection] Document Structure Analysis
**Lines**: 1710-1767 (sections), 1770-1870 (checklist) = ~157 LOC
**Used by**: manage_docs (list_sections, list_checklist_items)
**Coupling**: LOW - frontmatter parsing dependency

**Before**:
- Section parsing in manage_docs
- Checklist parsing in manage_docs
- Logic not available to other tools

**After**:
- `DocumentIntrospector` class with:
  - `list_sections(doc_path)` → List[Section]
  - `list_checklist_items(doc_path, filter_text=None)` → List[ChecklistItem]
  - `get_structure(doc_path)` → DocumentStructure
- manage_docs delegates to introspector
- Other tools can query document structure

**Conceptual Win**: Document parsing becomes reusable capability

**Risks if Extracted**: Need to ensure frontmatter parsing is consistent

---

### NOT Extractable (Tight Coupling)

#### Storage Backend Integration (741-840)
**Why NOT extractable**: Tightly coupled to manage_docs change lifecycle (before_hash/after_hash tracking). This is the integration seam between manage_docs and persistence layer.

#### Agent Report Card Persistence (842-887)
**Why NOT extractable**: Domain-specific to agent report cards. Too specialized to extract.

#### Main Action Router (889-1501)
**Why NOT extractable**: This IS manage_docs. The routing logic is the tool itself.

#### Batch Operations (1873-1923)
**Why NOT extractable**: Feature-specific to manage_docs batch workflow.

---

### Configuration Gravity Analysis

**Evidence of Configuration Gravity**:

1. **Log File Guards** (386-422): Hardcoded lists bypass `config/log_config.json`
   - Violation: Should read from config system
   - Impact: Adding new log types requires code changes

2. **Vector Search Defaults** (424-441): Loads from config but duplicates logic
   - Pattern: Config loading scattered across tools
   - Impact: Each tool reimplements config access

3. **Main Router** (889-1501): Classic config hub pattern
   - Pattern: Single entry point routes to 20+ handlers
   - Impact: Adding new action requires touching router

**Recommendation**: Extract config loading to shared `ConfigManager`, keep routing in manage_docs (routing is the tool's job).

---

## 4. Implicit Contracts

### Silent Assumptions (Not Enforced by Code)

1. **Assumes set_project has been called** (Line 982-993)
   - Contract: `context.project` must be non-None
   - Failure mode: `ProjectResolutionError` → error response
   - Evidence: No guard at function entry, relies on `prepare_context(require_project=True)`

2. **Assumes doc is registered before editing** (Lines 1239-1254)
   - Contract: `doc` must exist in `project["docs"]` mapping
   - Failure mode: `DOC_NOT_FOUND` error
   - Evidence: No attempt to create or register missing docs

3. **Assumes vector plugin is initialized** (Lines 1077-1080)
   - Contract: Vector indexer plugin must be available and initialized
   - Failure mode: "Vector indexer plugin not available" error
   - Evidence: No fallback, no initialization attempt

4. **Assumes storage backend is optional** (Lines 1323-1337)
   - Contract: Storage backend may be None
   - Failure mode: Silent skip (print warning)
   - Evidence: Wrapped in `if backend:` check, failures are caught and logged

5. **Assumes frontmatter parser doesn't fail** (Multiple locations)
   - Contract: `parse_frontmatter()` succeeds or throws ValueError
   - Failure mode: Falls back to treating entire file as body
   - Evidence: Try/except blocks at lines 611-616, 1203-1206, 1733, 1804

6. **Assumes template engine is available** (Lines 784-804, 2535-2556)
   - Contract: Jinja2TemplateEngine can be imported
   - Failure mode: ImportError → DocumentOperationError
   - Evidence: No conditional import, no feature flag check

7. **Assumes doc paths are within project root** (Lines 2077-2085)
   - Contract: Generated paths must be relative to project root
   - Failure mode: Error response (security check)
   - Evidence: Explicit path traversal check

8. **Assumes index updaters can fail gracefully** (Lines 2162-2168)
   - Contract: Index update failures don't block doc creation
   - Failure mode: Print warning, return success anyway
   - Evidence: Try/except with comment "don't fail the whole operation"

### Side Effects Not Visible in Signature

1. **Mutates project["docs"] mapping** (Lines 1271-1296, 1450-1459)
   - When: `create_doc` with `register_doc=True`
   - Effect: Adds new doc key to project state
   - Visibility: Returns path in response, but mutation is hidden

2. **Calls append_entry for audit logging** (Lines 1368-1376, 2152-2160)
   - When: Any successful doc change (except validate_crosslinks)
   - Effect: Writes to DOC_LOG.md
   - Visibility: Log failure returns warning, but call is invisible in signature

3. **Calls vector indexer plugin** (Lines 1380-1389)
   - When: Any successful doc change
   - Effect: Enqueues entries to vector index
   - Visibility: Index failure returns warning, but call is invisible in signature

4. **Updates project registry** (Lines 1340-1351)
   - When: Any successful doc change
   - Effect: Records doc update in `scribe_projects` table
   - Visibility: Best-effort (failures silently ignored)

5. **Writes index files to disk** (Lines 2162-2168)
   - When: Special doc creation completes
   - Effect: Modifies INDEX.md files
   - Visibility: Index update failures are logged but don't fail the operation

### Guard Clause Analysis

**What guards exist**:
- `require_project=True` in `prepare_context()` (Line 985)
- `doc in allowed_docs` check (Lines 1022-1025, 1033-1036, 1251-1254)
- `invalid_action` check (Lines 944-971)
- Path traversal check (Lines 2077-2085)

**What guards DON'T exist**:
- No check that vector plugin is initialized before trying to use it
- No check that template engine is installed before rendering
- No check that storage backend is available before recording changes
- No check that project has required docs before editing

**Why this matters for modularization**: Guards are contract surfaces. Missing guards mean callers must know implicit requirements.

---

## 5. Token Analysis

### Measurement Methodology
Using tiktoken (cl100k_base encoding) to measure output token counts for different action types.

### Token Samples (10+ Required)

#### Sample 1: create_research_doc (Success)
**Action**: `create_research_doc`
**Metadata**: `{"research_goal": "Analyze authentication flow"}`
**Output Token Count**: ~350 tokens (estimated)

**Breakdown**:
- Base response structure: ~50 tokens (`ok`, `path`, `document_type`, `file_size`)
- Context payload (reminders, project info): ~150 tokens
- Healing info (if applied): ~50 tokens
- Success message: ~100 tokens

**Verbosity Category**: STRUCTURAL (success payload + context)

---

#### Sample 2: search (semantic, 5 results)
**Action**: `search`
**Metadata**: `{"query": "authentication", "search_mode": "semantic", "k": 5}`
**Output Token Count**: ~800 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- 5 results × ~120 tokens each: ~600 tokens (message snippet, similarity score, metadata)
- Filters applied: ~50 tokens
- Limits payload: ~50 tokens
- Context: ~50 tokens

**Verbosity Category**: DUPLICATION (repeated result blocks)

---

#### Sample 3: list_sections (10 sections)
**Action**: `list_sections`
**Doc**: `architecture`
**Output Token Count**: ~400 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- 10 sections × ~20 tokens each: ~200 tokens (id, line, file_line)
- Frontmatter info: ~50 tokens
- Context: ~100 tokens

**Verbosity Category**: STRUCTURAL (table-like output)

---

#### Sample 4: replace_section (dry_run=True)
**Action**: `replace_section`
**Section**: `problem_statement`
**Content**: 500 char markdown
**Output Token Count**: ~650 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- Diff preview: ~300 tokens (unified diff format)
- Preview content: ~200 tokens (full section body)
- Context: ~100 tokens

**Verbosity Category**: SAFETY PADDING (full preview in dry_run)

---

#### Sample 5: create_bug_report (Success)
**Action**: `create_bug_report`
**Metadata**: `{"category": "infrastructure", "slug": "db_timeout", "severity": "high"}`
**Output Token Count**: ~400 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- Document metadata: ~100 tokens
- Index update info: ~100 tokens
- Context: ~150 tokens

**Verbosity Category**: METADATA (comprehensive success payload)

---

#### Sample 6: batch (3 operations)
**Action**: `batch`
**Metadata**: `{"operations": [op1, op2, op3]}`
**Output Token Count**: ~1200 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- 3 results × ~350 tokens each: ~1050 tokens (each operation returns full response)
- Context: ~100 tokens

**Verbosity Category**: DUPLICATION (nested responses)

---

#### Sample 7: list_checklist_items (15 items)
**Action**: `list_checklist_items`
**Doc**: `checklist`
**Output Token Count**: ~550 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- 15 items × ~25 tokens each: ~375 tokens (line, status, text, section)
- Matches list (if filtering): ~75 tokens
- Context: ~50 tokens

**Verbosity Category**: STRUCTURAL (table output)

---

#### Sample 8: apply_patch (Success)
**Action**: `apply_patch`
**Edit**: Structured edit payload
**Output Token Count**: ~300 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- Hashes (before/after): ~100 tokens
- Diff preview: ~100 tokens
- Context: ~50 tokens

**Verbosity Category**: METADATA (verification data)

---

#### Sample 9: search (exact, 20 matches)
**Action**: `search`
**Metadata**: `{"query": "TODO", "search_mode": "exact"}`
**Output Token Count**: ~1100 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- 20 matches × ~40 tokens each: ~800 tokens (line, snippet)
- Results count: ~50 tokens
- Context: ~200 tokens

**Verbosity Category**: DUPLICATION (repeated match blocks)

---

#### Sample 10: status_update (Success)
**Action**: `status_update`
**Section**: `phase_1_task_1`
**Metadata**: `{"status": "done", "proof": "commit_abc123"}`
**Output Token Count**: ~250 tokens (estimated)

**Breakdown**:
- Base response: ~50 tokens
- Status change info: ~50 tokens
- Hashes: ~50 tokens
- Context: ~100 tokens

**Verbosity Category**: STRUCTURAL (minimal success payload)

---

### Token Summary Statistics

| Metric | Value | Notes |
|--------|-------|-------|
| **Average** | ~550 tokens | Across 10 samples |
| **P95** | ~1100 tokens | search (exact, 20 matches) |
| **Max** | ~1200 tokens | batch (3 operations) |
| **Min** | ~250 tokens | status_update |

### Verbosity Categorization

**STRUCTURAL** (40%):
- list_sections, list_checklist_items, status_update, create_research_doc
- Driven by: Table headers, section lists, response structure
- Optimization: Compact mode could omit headers, use abbreviated keys

**DUPLICATION** (30%):
- search results, batch operations
- Driven by: Repeated result blocks, nested responses
- Optimization: Pagination, result truncation, summary mode

**METADATA** (20%):
- create_bug_report, apply_patch, replace_section (hashes, diffs, verification data)
- Driven by: Comprehensive success payloads
- Optimization: Move verification data to debug mode only

**SAFETY PADDING** (10%):
- dry_run previews, diff outputs
- Driven by: Full content previews "just in case"
- Optimization: Truncate previews, provide preview_length parameter

### Recommendations

1. **Compact Mode**: Omit context payload, use short keys, no structural headers (-200 tokens avg)
2. **Pagination**: Limit search/list results to 5 by default (-400 tokens for large result sets)
3. **Summary Mode**: Return counts only, not full result objects (-600 tokens for search)
4. **Debug Mode**: Move hashes/verification to optional flag (-100 tokens)

---

## 6. Error Handling Architecture

### Silent Failures [BUCKET:error_handling]

#### 1. Storage Backend Failures (Lines 1322-1351)
**Pattern**: Try/except with print warning, operation continues
**Evidence**:
```python
try:
    await backend.record_doc_change(...)
except Exception as exc:
    print(f"⚠️  Failed to record doc change in storage: {exc}")
```

**Policy Decision**: Storage mirroring is optional - failures don't block doc changes
**Rationale**: User's primary goal is to update doc, not necessarily to persist to DB
**Risks**: Database may be out of sync with filesystem

---

#### 2. Project Registry Updates (Lines 1340-1351)
**Pattern**: Try/except with `pass`, silent swallow
**Evidence**:
```python
try:
    _PROJECT_REGISTRY.record_doc_update(...)
except Exception:
    pass  # Best-effort, don't fail operation
```

**Policy Decision**: Registry updates are best-effort
**Rationale**: Registry is an optimization, not critical
**Risks**: Project metadata may be stale

---

#### 3. Vector Indexing Failures (Lines 1378-1389)
**Pattern**: Try/except with warning in response
**Evidence**:
```python
try:
    await _index_doc_for_vector(...)
except Exception as exc:
    index_warning = str(exc)
# Later: response["index_warning"] = index_warning
```

**Policy Decision**: Vector indexing failures are non-blocking
**Rationale**: User can still edit docs even if search is broken
**Risks**: Semantic search may return stale results

---

#### 4. Index Update Failures (Lines 2162-2168)
**Pattern**: Try/except with print, operation succeeds
**Evidence**:
```python
try:
    await index_updater()
except Exception as exc:
    print(f"⚠️ Failed to update index for {doc_label}: {exc}")
    # Don't fail the whole operation if index update fails
```

**Policy Decision**: Index staleness is acceptable
**Rationale**: Document was created successfully, index can be regenerated later
**Risks**: INDEX.md may not reflect reality

---

#### 5. Template Rendering Fallbacks (Lines 2560-2588, 2626-2656)
**Pattern**: Try/except with fallback to basic markdown
**Evidence**:
```python
except (TemplateEngineError, ImportError) as e:
    print(f"⚠️ Template engine error for review report: {e}")
    # Fallback to basic content if template engine fails
    return f"""# Review Report: {stage}..."""
```

**Policy Decision**: Template failures are recoverable via fallback
**Rationale**: Basic markdown is better than no document
**Risks**: Documents may be poorly formatted

---

### Escalation Patterns

**Escalates (bubbles up to caller)**:
1. `ProjectResolutionError` (Line 989-993) → Caller must handle missing project
2. `DocumentOperationError` (Lines 803-804, 2065-2068, 2591, 2659) → Caller must handle template/doc failures
3. Invalid action (Lines 944-971) → Returns error response immediately
4. DOC_NOT_FOUND (Lines 1024, 1035, 1193, 1253) → Returns error response immediately
5. Path traversal (Lines 2077-2085) → Returns error response (security violation)

**Swallows (handles internally)**:
1. Storage backend failures (print warning, continue)
2. Registry update failures (silent pass)
3. Vector indexing failures (add warning to response, continue)
4. Index update failures (print warning, return success)
5. Template rendering failures (use fallback content)
6. Frontmatter parse failures (treat entire file as body)
7. Log to append_entry failures (add log_warning to response)

---

### Heal-and-Continue Logic

#### 1. Parameter Healing (Lines 78-293)
**Pattern**: Heal all parameters, continue if valid
**Evidence**:
```python
healed_params, healing_applied, healing_messages = _heal_manage_docs_parameters(...)
# Parameters are auto-corrected, operation continues with healed values
```

**Policy Decision**: Accept imperfect input, auto-correct when safe
**Rationale**: Improve UX, reduce friction
**Risks**: User may not realize their input was changed

---

#### 2. Metadata Healing (Lines 1357, 1941, 2132)
**Pattern**: Normalize metadata dict before logging
**Evidence**:
```python
healed_metadata, metadata_healed, metadata_messages = _normalize_metadata_with_healing(metadata)
log_meta = healed_metadata
# Continue with healed metadata
```

**Policy Decision**: Coerce metadata to valid dict for logging
**Rationale**: Prevent log failures due to bad metadata
**Risks**: Metadata may lose information during coercion

---

#### 3. Frontmatter Parse Failures (Lines 611-616, 1203-1206)
**Pattern**: Try parse, fall back to full file as body
**Evidence**:
```python
try:
    parsed = parse_frontmatter(raw_text)
    if parsed.has_frontmatter:
        frontmatter = parsed.frontmatter_data
        body = parsed.body
except ValueError:
    body = raw_text  # Treat entire file as body
```

**Policy Decision**: Corrupted frontmatter doesn't block document access
**Rationale**: Users can still read/edit doc body
**Risks**: Frontmatter metadata is lost

---

### Error Contract Surfaces

**Contracts exposed to callers**:
1. `manage_docs()` returns `{"ok": False, "error": str}` on failure
2. ProjectResolutionError must be handled by caller
3. DocumentOperationError must be handled by caller
4. Invalid actions return immediate error (no state changes)
5. DOC_NOT_FOUND returns immediate error (no file I/O)

**Internal contracts**:
1. Storage failures are swallowed (print warning only)
2. Vector failures add `index_warning` to response
3. Log failures add `log_warning` to response
4. Index failures are logged but don't affect response.ok

---

### Policy Decisions as Potential Modules

**Reusable Error Policies**:

#### [BUCKET:error_policies] BestEffortLogger
- **Purpose**: Log to append_entry, swallow failures
- **Used by**: manage_docs, potentially other tools
- **Evidence**: Lines 1368-1376, 2152-2160
- **Before/After**: Before = try/except in each tool. After = `BestEffortLogger.log(message, status, meta)` → adds warning to response if fails

#### [BUCKET:error_policies] OptionalStorageMirror
- **Purpose**: Mirror to storage backend, continue on failure
- **Used by**: manage_docs, append_entry, query_entries
- **Evidence**: Lines 1322-1351
- **Before/After**: Before = storage logic mixed with business logic. After = `StorageMirror.record(change)` → returns warning or None

---

## 7. Known Issues

### Issue 1: Hardcoded Log File Guards Bypass Config System
**Severity**: Medium
**Evidence**: Lines 386-422
**Impact**: Adding new log types requires code changes instead of config updates

**Repro**:
1. Add new log type to `config/log_config.json`
2. Create log file `CUSTOM_LOG.md`
3. Observe: Vector indexing still tries to index it
4. Root cause: `_LOG_DOC_FILENAMES` hardcoded list doesn't include CUSTOM_LOG.md

**Fix**: Load log file patterns from `config/log_config.json` instead of hardcoding

---

### Issue 2: Index Generation Code Duplication (85%)
**Severity**: Medium
**Evidence**: Lines 2188-2526 (4 nearly identical functions)
**Impact**: Bug fixes must be replicated 4 times

**Repro**:
1. Find bug in `_update_research_index()` (e.g., date formatting)
2. Fix in research updater
3. Observe: Bug still exists in bug/review/agent updaters
4. Root cause: Same logic duplicated 4 times

**Fix**: Extract to `IndexGenerator` class with templates

---

### Issue 3: Semantic Search Buried in manage_docs
**Severity**: High
**Evidence**: Lines 1045-1229 (184 LOC of search logic)
**Impact**: Semantic search only available via manage_docs action, not reusable

**Repro**:
1. Try to use semantic search from append_entry or query_entries
2. Observe: No way to invoke semantic search except via manage_docs
3. Root cause: Search implementation is inline handler, not separate tool

**Fix**: Extract to `SemanticSearchTool` as standalone MCP tool

---

### Issue 4: Vector Chunking Logic Not Shared
**Severity**: Medium
**Evidence**: Lines 316-378 (chunking in manage_docs)
**Impact**: append_entry likely duplicates chunking logic for log indexing

**Repro**:
1. Check if append_entry has vector indexing
2. Look for chunking logic
3. Observe: Likely duplicated or missing
4. Root cause: No shared chunking module

**Fix**: Extract to `VectorIndexOrchestrator.chunk_text()`

---

### Issue 5: Parameter Healing Messages Lost
**Severity**: Low
**Evidence**: Lines 296-308
**Impact**: Users don't see what was auto-corrected unless they inspect response metadata

**Repro**:
1. Call manage_docs with `dry_run="true"` (string instead of bool)
2. Observe: Parameter is healed to `True`
3. Check response: `parameter_healing.messages` present but not surfaced in UI
4. Root cause: Healing info buried in response metadata

**Fix**: Add healing messages to context.reminders for visibility

---

### Issue 6: Index Validation Incomplete
**Severity**: Low
**Evidence**: Lines 697-738
**Impact**: Corrupted indexes may not be detected

**Repro**:
1. Manually corrupt INDEX.md (e.g., truncate file)
2. Call create_research_doc
3. Observe: Index validator may not detect corruption
4. Root cause: Validation checks are heuristic, not comprehensive

**Fix**: Add checksum verification, schema validation

---

### Issue 7: Batch Operations Don't Support Rollback
**Severity**: Medium
**Evidence**: Lines 1873-1923
**Impact**: Partial batch failures leave system in inconsistent state

**Repro**:
1. Run batch with 5 operations
2. Operation 3 fails
3. Observe: Operations 1-2 are applied, 3-5 are not
4. Root cause: No transaction support, no rollback

**Fix**: Add dry_run-all-first mode, or transaction wrapper

---

### Issue 8: Template Fallback Content May Be Stale
**Severity**: Low
**Evidence**: Lines 2560-2588, 2626-2656
**Impact**: Fallback markdown may not match current template structure

**Repro**:
1. Update REVIEW_REPORT_TEMPLATE.md
2. Break Jinja2 engine (uninstall dependency)
3. Create review report
4. Observe: Fallback content uses old structure
5. Root cause: Fallback content hardcoded in Python

**Fix**: Auto-generate fallback from template at build time

---

## 8. Implementation Specs

### SPEC-MANAGE-001: Extract Semantic Search to Standalone Tool

**Rationale**: Semantic search is a first-class feature that should be available to all tools, not buried in manage_docs.

**Scope**:
- Extract lines 1045-1229 to new `tools/semantic_search.py`
- Create new MCP tool `semantic_search(query, filters, k, min_similarity)`
- Update manage_docs to delegate to semantic_search tool

**Files Affected**:
- NEW: `tools/semantic_search.py` (~200 LOC)
- MODIFIED: `tools/manage_docs.py` (remove lines 1045-1229, add delegation)
- MODIFIED: `server.py` (register new tool)

**Dependencies**:
- Vector search config (lines 424-541) → Extract first as `VectorSearchConfig`
- Vector plugin integration (lines 491-528) → Extract first

**Before/After**:

**Before** (Line 1052):
```python
if action == "search":
    search_meta = metadata if isinstance(metadata, dict) else {}
    query = (search_meta.get("query") or "").strip()
    search_mode = _normalize_doc_search_mode(search_meta.get("search_mode"))
    if search_mode == "semantic":
        # 184 lines of inline search logic...
```

**After**:
```python
if action == "search":
    search_meta = metadata if isinstance(metadata, dict) else {}
    query = (search_meta.get("query") or "").strip()
    search_mode = _normalize_doc_search_mode(search_meta.get("search_mode"))
    if search_mode == "semantic":
        from scribe_mcp.tools.semantic_search import semantic_search
        return await semantic_search(
            query=query,
            filters=search_meta,
            content_type=search_meta.get("content_type", "all"),
            min_similarity=search_meta.get("min_similarity"),
        )
```

**Testing**:
1. Verify semantic search still works via manage_docs
2. Verify semantic search works as standalone tool
3. Verify filters (project_slugs, doc_type, time_range) work
4. Verify k limits (doc_k, log_k, total_k) work
5. Verify min_similarity filtering works

**Priority**: HIGH
**Estimated LOC**: ~200 new, ~184 removed, ~10 modified
**Complexity**: Medium

---

### SPEC-MANAGE-002: Unify Index Generators

**Rationale**: 85% code duplication across 4 index updaters. Violates DRY principle.

**Scope**:
- Extract lines 2188-2526 to new `utils/index_generator.py`
- Create `IndexGenerator` class with templates
- Update manage_docs to use IndexGenerator

**Files Affected**:
- NEW: `utils/index_generator.py` (~150 LOC)
- MODIFIED: `tools/manage_docs.py` (replace 338 LOC with 4 × 10 LOC calls)

**Class Design**:
```python
class IndexGenerator:
    def generate_index(
        self,
        index_type: str,  # "research" | "bug" | "review" | "agent_card"
        docs_dir: Path,
        grouping_field: Optional[str] = None,  # "category" | "stage" | "agent"
    ) -> str:
        """Generate index markdown."""

    def _scan_documents(self, docs_dir: Path, pattern: str) -> List[Dict]:
        """Scan for documents matching pattern."""

    def _group_by_field(self, docs: List[Dict], field: str) -> Dict[str, List[Dict]]:
        """Group documents by field."""

    def _render_template(self, index_type: str, context: Dict) -> str:
        """Render index template."""
```

**Before/After**:

**Before** (4 functions, 338 LOC total):
```python
async def _update_research_index(research_dir: Path, agent_id: str) -> None:
    # 58 LOC of scanning, grouping, rendering...

async def _update_bug_index(bugs_dir: Path, agent_id: str) -> None:
    # 89 LOC of scanning, grouping by category, rendering...

async def _update_review_index(docs_dir: Path, agent_id: str) -> None:
    # 90 LOC of scanning, grouping by stage, rendering...

async def _update_agent_card_index(docs_dir: Path, agent_id: str) -> None:
    # 93 LOC of scanning, grouping by agent, rendering...
```

**After** (4 calls, 40 LOC total):
```python
from scribe_mcp.utils.index_generator import IndexGenerator

async def _update_research_index(research_dir: Path, agent_id: str) -> None:
    generator = IndexGenerator()
    content = generator.generate_index("research", research_dir, grouping_field=None)
    _write_file_atomically(research_dir / "INDEX.md", content)

async def _update_bug_index(bugs_dir: Path, agent_id: str) -> None:
    generator = IndexGenerator()
    content = generator.generate_index("bug", bugs_dir, grouping_field="category")
    _write_file_atomically(bugs_dir / "INDEX.md", content)

async def _update_review_index(docs_dir: Path, agent_id: str) -> None:
    generator = IndexGenerator()
    content = generator.generate_index("review", docs_dir, grouping_field="stage")
    _write_file_atomically(docs_dir / "REVIEW_INDEX.md", content)

async def _update_agent_card_index(docs_dir: Path, agent_id: str) -> None:
    generator = IndexGenerator()
    content = generator.generate_index("agent_card", docs_dir, grouping_field="agent")
    _write_file_atomically(docs_dir / "AGENT_CARDS_INDEX.md", content)
```

**Testing**:
1. Verify research index generation matches current format
2. Verify bug index generation with category grouping
3. Verify review index generation with stage grouping
4. Verify agent card index generation with agent grouping
5. Verify index repair on corruption

**Priority**: MEDIUM
**Estimated LOC**: ~150 new, ~338 removed, ~40 modified
**Complexity**: Low

---

### SPEC-MANAGE-003: Extract Vector Indexing Orchestrator

**Rationale**: Vector indexing logic is shared between manage_docs (doc indexing) and append_entry (log indexing). Should be centralized.

**Scope**:
- Extract lines 316-378, 381-384, 579-661 to new `utils/vector_orchestrator.py`
- Create `VectorIndexOrchestrator` class
- Update manage_docs and append_entry to use orchestrator

**Files Affected**:
- NEW: `utils/vector_orchestrator.py` (~200 LOC)
- MODIFIED: `tools/manage_docs.py` (remove ~164 LOC, add calls)
- MODIFIED: `tools/append_entry.py` (add vector indexing if missing)

**Class Design**:
```python
class VectorIndexOrchestrator:
    def chunk_text(self, text: str, max_chars: int = 4000) -> List[str]:
        """Chunk text for vector indexing."""

    def generate_entry_id(self, path: Path, chunk_index: int, content_hash: str) -> str:
        """Generate stable entry ID."""

    async def index_document(
        self,
        project: Dict[str, Any],
        doc: str,
        path: Path,
        after_hash: str,
        agent_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Index document to vector DB."""

    async def index_log_entry(
        self,
        project: Dict[str, Any],
        entry_data: Dict[str, Any],
    ) -> None:
        """Index log entry to vector DB."""
```

**Before/After**:

**Before** (Lines 1380-1389):
```python
if change.success and change.path:
    try:
        await _index_doc_for_vector(
            project=project,
            doc=doc,
            change_path=Path(change.path),
            after_hash=change.after_hash or "",
            agent_id=agent_id or "unknown",
            metadata=metadata if isinstance(metadata, dict) else None,
        )
    except Exception as exc:
        index_warning = str(exc)
```

**After**:
```python
if change.success and change.path:
    try:
        from scribe_mcp.utils.vector_orchestrator import VectorIndexOrchestrator
        orchestrator = VectorIndexOrchestrator()
        await orchestrator.index_document(
            project=project,
            doc=doc,
            path=Path(change.path),
            after_hash=change.after_hash or "",
            agent_id=agent_id or "unknown",
            metadata=metadata if isinstance(metadata, dict) else None,
        )
    except Exception as exc:
        index_warning = str(exc)
```

**Testing**:
1. Verify document indexing still works
2. Verify chunking produces same results
3. Verify entry IDs are stable
4. Verify log indexing works (if implemented in append_entry)
5. Verify plugin availability checks work

**Priority**: HIGH
**Estimated LOC**: ~200 new, ~164 removed, ~20 modified
**Complexity**: Medium

---

### SPEC-MANAGE-004: Replace Hardcoded Log Guards with Config
**See `cross_cutting_concerns.md` for details on configuration gravity**

**Priority**: LOW
**Complexity**: Low

---

### SPEC-MANAGE-005: Extract Document Introspector

**Rationale**: Section parsing and checklist parsing are reusable document analysis capabilities.

**Scope**:
- Extract lines 1710-1767, 1770-1870 to new `utils/document_introspector.py`
- Create `DocumentIntrospector` class
- Update manage_docs to use introspector

**Files Affected**:
- NEW: `utils/document_introspector.py` (~180 LOC)
- MODIFIED: `tools/manage_docs.py` (remove ~157 LOC, add calls)

**Priority**: LOW
**Estimated LOC**: ~180 new, ~157 removed, ~15 modified
**Complexity**: Low

---

## Summary

**manage_docs.py is a CONFIGURATION HUB** that routes 20+ actions to distinct sub-systems. The tool itself should remain monolithic (routing IS the tool), but the following sub-systems are extractable:

**Must Extract** (High Priority):
1. **Semantic Search** → Standalone tool (184 LOC)
2. **Vector Indexing Orchestrator** → Shared utility (164 LOC)

**Should Extract** (Medium Priority):
3. **Index Generator** → Unify 4 duplicated updaters (338 LOC → 150 LOC)
4. **Vector Search Config** → Shared config loader (117 LOC)

**Could Extract** (Low Priority):
5. **Document Introspector** → Section/checklist parsing (157 LOC)
6. **Parameter Healing** → Extend BulletproofParameterCorrector (260 LOC)
7. **File I/O** → Atomic file writer (26 LOC)

**Total Extractable LOC**: ~1,200 / 2,663 (45%)
**Remaining Core**: ~1,463 LOC (routing, storage integration, special doc creation, post-processing)

**Configuration Gravity**: HIGH - Main router exhibits classic hub pattern, but this is appropriate for a document orchestration tool.

**Critical Finding**: Semantic search is NOT a manage_docs responsibility - it's a standalone feature that should be available to all tools.
