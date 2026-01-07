# Cross-Cutting Concerns

**Purpose**: Unified system map of patterns, issues, and architectural decisions discovered across multiple tools during Phase 1 forensic audit.

**Instructions for Agents**: Append to this document when you discover patterns that span multiple tools. Use structured format below.

---

## Duplicated Helper Patterns

<!-- Format: Tool name, file:line, pattern description, duplication count -->

### Pattern: `_count_log_entries`
**Discovery**: Found in 2 files with different implementations
- `set_project.py:36-58` - Uses regex pattern `^\[\d{4}-\d{2}-\d{2}`
- `get_project.py:43-52` - Uses `parse_log_line()` utility function
**Impact**: Code duplication, inconsistent counting methods
**Recommendation**: Consolidate into single utility function
**Reporter**: (Agent to fill)
**Status**: Pre-identified (DUPLICATION-001)

### Pattern: Doc Gathering Logic
**Discovery**: Repeated 3x across different tools
- `set_project.py:61-127` - `_gather_project_inventory()`
- `list_projects.py:50-128` - `_gather_doc_info()`
- `get_project.py:130-179` - `_gather_doc_info()`
**Impact**: 90-100 LOC duplicated, maintenance burden
**Recommendation**: Extract to shared utility module
**Reporter**: (Agent to fill)
**Status**: Pre-identified (DUPLICATION-002)

---

## Shared Token Bloat Sources

<!-- Format: Source type, tools affected, avg tokens, optimization target -->

### Source: Verbose SITREP Formatting
**Affected Tools**: `set_project.py`, `list_projects.py`, `get_project.py`
**Token Cost**: 400-1000 tokens per call
**Root Cause**: 3-way routing (no matches / single / multiple) with rich metadata
**Optimization Target**: <400 tokens (50-60% reduction)
**Reporter**: (Agent to fill)
**Status**: Pre-identified (TOKEN-001)

### Source: Reminder System Overhead
**Affected Tools**: append_entry.py (all responses include reminders)
**Token Cost**: 80-200 tokens per reminder (teaching messages + examples)
**Root Cause**: Reminder engine integrated into every tool response
**Reporter**: ResearchAgent-A-AppendEntry
**Status**: Documented in append_entry.md token analysis

### Source: Response Formatter Verbosity
**Affected Tools**: append_entry.py (structural + metadata verbosity)
**Token Cost**: 150-300 tokens structural overhead (boxes, headers, colors)
**Root Cause**: Readable format as default (not compact)
**Reporter**: ResearchAgent-A-AppendEntry
**Status**: 70% reduction possible with compact mode

---

## Storage Abstraction Violations

<!-- Format: File:line, violation type, impact, fix priority -->

### Violation: Direct sqlite3.connect() Bypass
**Location**: `shared/project_registry.py:77-98, 111-168, 177-185, 187-219`
**Type**: Bypasses StorageBackend abstraction layer
**Impact**: PostgreSQL users miss lifecycle operations (planning → in_progress transitions)
**Methods Affected**: `ensure_project()`, `touch_access()`, `touch_entry()`, `set_status()`, `record_doc_update()`
**Fix Priority**: P0 - Critical
**Reporter**: Pre-identified during exploration
**Status**: Pre-identified (BUG-STORAGE-001)

---

## Missing Infrastructure Integrations

<!-- Format: File:line, infrastructure available but not used, impact -->

### Integration Gap: Template Creation Not Tracked in ProjectRegistry
**Location**: `tools/generate_doc_templates.py:220-224` (template write completion)
**Available Infrastructure**: `ProjectRegistry.record_doc_update()` (shared/project_registry.py:187-263)
**Current Behavior**: Templates created but baseline hashes NOT recorded
**Impact**:
- **BUG-001**: set_project cannot distinguish new vs existing projects correctly
- **Consequence**: Relies on broken `entry_count == 0` check that fails after log rotation
- **Symptom**: Empty logs treated as new projects, inventory gathering skipped

**What Should Happen**:
```python
# After template write (line 221)
content_hash = hashlib.sha256(rendered.encode('utf-8')).hexdigest()
_PROJECT_REGISTRY.record_doc_update(
    project_name,
    doc=key,  # "architecture", "phase_plan", "checklist", "progress_log"
    action="template_created",
    before_hash=None,
    after_hash=content_hash,
)
```

**Correct Detection Logic** (for set_project.py):
```python
# Instead of: is_new = not progress_log_path.exists() or entry_count == 0
# Use hash comparison:
docs_meta = registry.get_project(name).meta.get("docs", {})
baseline_hashes = docs_meta.get("baseline_hashes", {})
current_hashes = docs_meta.get("current_hashes", {})

# If all core docs match baseline, project is pristine (new)
core_docs = {"architecture", "phase_plan", "checklist"}
is_new = all(baseline_hashes.get(d) == current_hashes.get(d) for d in core_docs if d in baseline_hashes)
```

**Why Correct**:
1. ✅ Distinguishes "file exists" from "project has been worked on"
2. ✅ Survives log rotation (hash comparison unaffected)
3. ✅ Survives manual clearing (hash comparison unaffected)
4. ✅ Uses existing infrastructure (no new code needed)
5. ✅ Semantic correctness: "pristine templates" = new, "modified docs" = existing

**Why Previous Fix Failed**:
- `is_new = not progress_log_path.exists()` breaks because:
  - Line 246: `_ensure_documents()` runs BEFORE `is_new` check at line 459
  - Line 667: `generate_doc_templates()` CREATES `PROGRESS_LOG.md`
  - After creation, `file.exists()` is ALWAYS True
  - Result: `is_new` is ALWAYS False (complete breakage)

**Fix Priority**: P0 - Critical (blocks correct project state detection)
**Reporter**: Orchestrator (Wave 1 Review), ResearchAgent-I-GenTemplates (Wave 2)
**Status**: Documented in BUG-001 (corrected analysis), SPEC-GEN-001 (implementation spec created)
**Deliverables**:
- `wiki/specs/SPEC-GEN-001-registry-integration.yaml` - Complete implementation spec
- `wiki/analysis/template_lifecycle_integration.md` - Full lifecycle documentation
- `wiki/tools/generate_doc_templates.md` - Tool architecture audit

**Key Discovery** (Wave 2): ProjectRegistry.record_doc_update() line 229 has subtle issue:
- Checks `if doc not in baseline_map and before_hash:`
- For new templates, `before_hash=None`, so baseline NOT set
- **Solution**: Pass `before_hash=content_hash, after_hash=content_hash` to create pristine state
- This enables set_project to detect `baseline == current` → new project

---

## Session Identity / Project Routing Assumptions

<!-- Format: Tool name, assumption, impact if violated -->

### Assumption: Active Project Context
**Tools Using**: (To be catalogued during audit)
**Assumption**: Tools assume `state_manager.get_active_project()` returns valid project
**Impact if Violated**: Tools may fail silently or use wrong project context
**Reporter**: (Agent to fill)
**Status**: Pending investigation

### Assumption: Agent Session Persistence
**Tools Using**: (To be catalogued during audit)
**Assumption**: Agent sessions persist across MCP reconnections
**Impact if Violated**: Session isolation may break, tool calls routed to wrong projects
**Reporter**: (Agent to fill)
**Status**: Pending investigation

---

## Parameter Proliferation Patterns

<!-- Format: Tool name, param count, consolidation opportunities -->

### Pattern: 20+ Parameter Signatures
**Tools Affected**:
- `append_entry.py` - 21 parameters
- `query_entries.py` - 25 parameters
- Others: (To be identified)
**Root Cause**: Feature creep without Config object migration
**Consolidation Opportunity**: Use Config objects (AppendEntryConfig pattern) consistently
**Reporter**: (Agent to fill)
**Status**: Pre-identified

---

## Silent Exception Swallowing

<!-- Format: File:line, exception type, impact -->

### Pattern: `except Exception: pass`
**Locations**:
- `append_entry.py:685` - TEE operations (intentional: never block logging)
- `append_entry.py:722` - DB mirroring (intentional: best-effort only)
- `append_entry.py:739` - Vector indexing (intentional: non-blocking)
- `append_entry.py:754` - State updates (intentional: nice-to-have)
**Impact**: Architectural decision - auxiliary operations must not block primary file write
**Fix Strategy**: Add observability hooks (metrics, optional warning logs) without breaking "never block" contract
**Reporter**: ResearchAgent-A-AppendEntry
**Status**: Documented as architectural policy in append_entry.md (not a bug)

---

## Non-Atomic Write Operations

<!-- Format: File:line, operation type, failure scenario -->

### Operation: Log Rotation Without Locks
**Location**: (To be determined during rotate_log.py audit)
**Failure Scenario**: Concurrent rotations could corrupt log files
**Reporter**: (Agent to fill - Agent D specifically)
**Status**: Pending investigation

---

## Notes for Agents

**When to Append**:
- You find the same helper function/pattern in 2+ files
- You discover shared token bloat mechanisms (formatting, reminders, metadata)
- You identify storage abstraction violations (direct DB access)
- You uncover implicit assumptions about sessions/projects/state
- You find exception swallowing or non-atomic operations

**Format Requirements**:
- Use structured headings (### Pattern:, **Location:**, etc.)
- Include file paths with line numbers
- Estimate impact (token cost, failure scenarios, maintenance burden)
- Propose fix priority (P0/P1/P2/P3)
- Sign with your agent name

**Quality Standard**:
- Evidence required (no "seems like" language)
- Verifiable claims only
- Link to specific wiki pages or bug reports when created

---

---

## Candidate Modules

### [BUCKET:utilities] Message Sanitization & ID Generation
**Origin**: `append_entry.py:97-168`
**Responsibilities**: MCP protocol sanitization (newlines → \n), slug generation (path → URL-friendly), deterministic UUIDs (SHA256-based)
**Used by**: append_entry, manage_docs (needs slug generation), set_project
**Why it should be shared**: Pure utility functions with no side effects, reusable across all tools
**Risks if extracted**: None - no implicit dependencies
**Before/After**:
- Before: 3 responsibilities mixed (sanitize + slug + UUID) in append_entry.py
- After: Single `scribe_mcp.utils.identifiers` module with clear contracts
- Conceptual win: Tools don't know MCP protocol details or hashing algorithms
**Reporter**: ResearchAgent-A-AppendEntry

### [BUCKET:persistence] Multi-Target Write Coordination
**Origin**: `append_entry.py:559-740`
**Responsibilities**: Coordinate writes to file (required), DB (best-effort), vector (best-effort) with failure isolation
**Used by**: append_entry (single entry processing)
**Why it should be shared**: Every write operation needs same pattern (primary → auxiliary with failure isolation)
**Risks if extracted**: Tight coupling to "never block logging" philosophy - would need clear contracts about required vs best-effort targets
**Before/After**:
- Before: 180 lines of try-except-pass for file → DB → vector embedded in entry processing
- After: `PersistenceCoordinator.write_entry(entry, targets=['file', 'db', 'vector'])` with clear failure isolation
- Conceptual win: Entry processing doesn't know about persistence infrastructure
**Reporter**: ResearchAgent-A-AppendEntry

### [BUCKET:utilities] TEE Coordination
**Origin**: `append_entry.py:1758-1816`
**Responsibilities**: Determine auxiliary logs (bugs/security) based on emoji/status/meta, write with failure isolation
**Used by**: `_process_single_entry()` in append_entry
**Why it should be shared**: TEE pattern (write to multiple logs) is reusable for any multi-log scenario
**Risks if extracted**: Tight coupling to log_config.json structure, hardcoded emoji sets (lines 1758-1759)
**Before/After**:
- Before: TEE logic embedded in entry processing with emoji checks, metadata checks, duplicate writes
- After: `TeeCoordinator.determine_targets(status, emoji, meta)` → `["bugs", "security"]`, then `TeeCoordinator.write_to_targets(entry, targets)`
- Conceptual win: Entry processing doesn't know which auxiliary logs exist or how to detect them
**Reporter**: ResearchAgent-A-AppendEntry

### [BUCKET:config] Dual Parameter Support Infrastructure
**Origin**: `append_entry.py:170-418` (plus similar logic in query_entries, list_projects, rotate_log)
**Responsibilities**: Validate legacy params, heal invalid inputs, merge with config object, apply emergency fallbacks
**Used by**: All tools with AppendEntryConfig-style dual parameter support (append_entry, query_entries, rotate_log)
**Why it should be shared**: All tools duplicate this 200+ line validation/healing/config merging pattern
**Risks if extracted**: Healing semantics differ per tool (append_entry heals differently than query_entries) - would need tool-specific adapters
**Unification strategy**: Extract base `ParameterCoordinator` framework + tool-specific healing adapters
**Before/After**:
- Before: Each tool has 200+ lines of parameter validation/healing/config merging with subtle differences
- After: Tools call `ParameterCoordinator.validate_and_prepare(AppendEntryConfig, locals())` with optional custom healers
- Conceptual win: Tools focus on business logic, not parameter gymnastics
**Reporter**: ResearchAgent-A-AppendEntry
**Status**: Needs unification across tools (not simple extraction)

### [BUCKET:utilities] Bulk Processing Infrastructure (Partial Extraction)
**Origin**: `append_entry.py:821-1137, 1842-2073, 2075-2360` + existing `BulkProcessor`, `ParallelBulkProcessor` utilities
**Responsibilities**: Input format normalization, parallel/sequential routing, item processing, result aggregation
**Used by**: append_entry (bulk mode)
**Why it should be shared**: Bulk processing pattern is reusable for any tool that processes multiple items
**Risks if extracted**: Item processing logic is tool-specific - would need callback pattern for tool-specific validation/resolution
**What's Already Extracted**: BulkProcessor utilities (detect, split, timestamp staggering), ParallelBulkProcessor (chunking, parallel execution)
**What's Still Embedded**: Input normalization (items_list vs items string), metadata inheritance, sequential processing loop, batch DB accumulation
**Before/After**:
- Before: 500+ lines of bulk processing logic with duplication between parallel and sequential paths
- After: `BulkCoordinator.execute(items, processor_callback, parallel_threshold=10)` handles all coordination
- Conceptual win: Bulk infrastructure is reusable, append_entry only provides item processor callback
**Reporter**: ResearchAgent-A-AppendEntry
**Status**: Partial extraction complete - needs finishing

### [BUCKET:indexing] Vector Indexer Plugin Discovery
**Origin**: `append_entry.py:77-94`
**Responsibilities**: Lazy-load vector indexer plugin from registry, check if vector indexing is enabled
**Used by**: `_process_single_entry()` in append_entry (line 727)
**Why it should be shared**: Plugin discovery logic is reusable across tools that need vector indexing
**Risks if extracted**: Tight coupling to plugin registry architecture
**Before/After**:
- Before: Vector setup mixed with entry processing logic
- After: Clean `get_vector_indexer()` interface, tools don't know about registry internals
- Conceptual win: Plugin discovery is abstracted, tools just call `get_indexer()`
**Reporter**: ResearchAgent-A-AppendEntry

---

### [BUCKET:vector_indexing] VectorIndexOrchestrator
**Origin**: `manage_docs.py:316-378, 381-384, 579-661` (~164 LOC)
**Responsibilities**:
- Chunk text for vector indexing (max 4000 chars, preserve headers)
- Generate stable entry IDs (sha256 hash)
- Orchestrate document/log vector indexing
**Used By**: manage_docs (doc indexing), potentially append_entry (log indexing)
**Why It Should Be Shared**:
- Chunking algorithm should be consistent across docs and logs
- Entry ID generation needs to be stable
- Vector indexing workflow is identical for docs/logs
**Risks if Extracted**: Need to handle doc vs log metadata differences
**Before/After**:
- Before = chunking logic in manage_docs, potentially duplicated in append_entry
- After = single `VectorIndexOrchestrator.chunk_text()` and `index_document()/index_log_entry()` methods used by all tools
**Reporter**: ResearchAgent-B-ManageDocs
**Status**: HIGH priority extraction

---

### [BUCKET:semantic_search] SemanticSearchTool (CRITICAL)
**Origin**: `manage_docs.py:1045-1229` (~184 LOC)
**Responsibilities**:
- Vector-based semantic search across docs and logs
- Filter construction (project_slugs, doc_type, file_path, time_range)
- k limit resolution (doc_k, log_k, total_k)
- Similarity threshold filtering
**Used By**: Currently only manage_docs, but should be available to ALL tools
**Why It Should Be Shared**:
- Semantic search is a general-purpose capability, not a manage_docs feature
- Other tools (append_entry, query_entries, read_recent) should be able to use semantic search
- Buried 184 LOC in document management tool violates separation of concerns
**Risks if Extracted**: Need to ensure project context is available to all tools
**Before/After**:
- Before = semantic search only accessible via manage_docs search action
- After = standalone `semantic_search` MCP tool, manage_docs delegates to it
**Reporter**: ResearchAgent-B-ManageDocs
**Status**: CRITICAL - semantic search is NOT a manage_docs responsibility

---

### [BUCKET:index_generation] IndexGenerator (Unification Opportunity)
**Origin**: `manage_docs.py:2188-2526` (4 updaters, ~338 LOC total)
**Responsibilities**:
- Generate INDEX.md files for document collections
- Scan directories for documents
- Group by field (category, stage, agent)
- Render markdown with statistics
**Used By**: manage_docs (research, bug, review, agent card creation)
**Why It Should Be Shared**:
- 85% code duplication across 4 index updaters
- Same pattern: scan → group → render → write
- Bug fixes must be replicated 4 times currently
**Risks if Extracted**: Index formats may need to diverge (currently very similar)
**Before/After**:
- Before = 4 nearly identical functions (58, 89, 90, 93 LOC each)
- After = `IndexGenerator.generate_index(type, grouping_field)` (~150 LOC total)
**Unification Evidence**:
- `_update_research_index()` (58 LOC)
- `_update_bug_index()` (89 LOC) - only diff is category grouping
- `_update_review_index()` (90 LOC) - only diff is stage grouping
- `_update_agent_card_index()` (93 LOC) - only diff is agent grouping
**Reporter**: ResearchAgent-B-ManageDocs
**Status**: MEDIUM priority unification

---

### [BUCKET:document_introspection] DocumentIntrospector
**Origin**: `manage_docs.py:1710-1767, 1770-1870` (~157 LOC)
**Responsibilities**:
- Parse section anchors (`<!-- ID: ... -->`) with line numbers
- Parse checklist items (`- [ ]` / `- [x]`) with status
- Return document structure metadata
**Used By**: manage_docs (list_sections, list_checklist_items actions)
**Why It Should Be Shared**:
- Document parsing is a reusable capability
- Other tools may want to query document structure
- Could be extended with header parsing, link extraction, etc.
**Risks if Extracted**: Need to ensure frontmatter parsing is consistent
**Before/After**:
- Before = section/checklist parsing in manage_docs only
- After = `DocumentIntrospector` class available to all tools
**Reporter**: ResearchAgent-B-ManageDocs
**Status**: LOW priority extraction

---

### [BUCKET:vector_search] VectorSearchConfig
**Origin**: `manage_docs.py:424-541` (~117 LOC)
**Responsibilities**:
- Load vector search defaults (doc_k, log_k from config)
- Normalize search modes ("fuzzy" → "fuzzy", "semantic" → "semantic", etc.)
- Resolve k limits with override handling
**Used By**: manage_docs (semantic search)
**Why It Should Be Shared**:
- Config loading scattered across tools
- Each tool reimplements config access
- Should be loaded once, queried by all tools
**Risks if Extracted**: None - pure config loading
**Before/After**:
- Before = config loading duplicated in each tool
- After = `VectorSearchConfig.load()` singleton, tools query it
**Reporter**: ResearchAgent-B-ManageDocs
**Status**: MEDIUM priority extraction

---

### [BUCKET:file_io] AtomicFileWriter
**Origin**: `manage_docs.py:668-694` (~26 LOC)
**Responsibilities**:
- Write file atomically using temp file + move
- Verify temp file exists and has size > 0
- Return success/failure boolean
**Used By**: manage_docs (index updates), potentially other tools
**Why It Should Be Shared**:
- Generic file I/O pattern
- Likely duplicated in other tools (needs verification)
- Single point for I/O error handling
**Risks if Extracted**: None - pure utility
**Before/After**:
- Before = atomic write logic duplicated
- After = `AtomicFileWriter.write(path, content)` → bool
**Reporter**: ResearchAgent-B-ManageDocs
**Status**: LOW priority extraction

---

### [BUCKET:parameter_healing] ParameterHealingExtensions
**Origin**: `manage_docs.py:51-309` (~260 LOC)
**Responsibilities**:
- Normalize all manage_docs parameters
- Auto-correct strings, JSON payloads, booleans, line numbers
- Generate healing messages
**Used By**: manage_docs, potentially other document tools
**Why It Should Be Shared**:
- Parameter healing pattern applies to all tools
- Should extend existing `BulletproofParameterCorrector`
- Healing messages should be standardized
**Risks if Extracted**: Need to ensure tool-specific healing doesn't break invariants
**Before/After**:
- Before = healing logic mixed with manage_docs business logic
- After = `BulletproofParameterCorrector.heal_manage_docs_params()` method
**Reporter**: ResearchAgent-B-ManageDocs
**Status**: MEDIUM priority extraction

---

### [BUCKET:config] Log File Guards (Configuration Gravity Issue)
**Origin**: `manage_docs.py:386-422` (~36 LOC)
**Problem**: Hardcoded log file lists bypass `config/log_config.json`
**Hardcoded Lists**:
- `_LOG_DOC_KEYS`: progress_log, doc_log, security_log, bug_log
- `_LOG_DOC_FILENAMES`: PROGRESS_LOG.md, DOC_LOG.md, SECURITY_LOG.md, BUG_LOG.md, GLOBAL_PROGRESS_LOG.md
**Impact**: Adding new log types requires code changes instead of config updates
**Why This Is Configuration Gravity**: Defensive config logic bypasses the actual config system
**Before/After**:
- Before = hardcoded guard lists in manage_docs.py
- After = read from `config/log_config.json`, single source of truth
**Reporter**: ResearchAgent-B-ManageDocs
**Status**: LOW priority fix (not extraction, just use existing config)

---

### [BUCKET:templating] Template Rendering Strategy
**Origin**: `generate_doc_templates.py:106-213` (~107 LOC)
**Responsibilities**: Initialize Jinja2 engine and render templates with fallback strategy
**Used By**: generate_doc_templates (primary), potential reuse in manage_docs for future custom templates
**Why It Should Be Shared**:
- Template rendering is reusable capability
- Strategy pattern (Jinja2 vs legacy) should be configurable
- Testing in isolation improves quality
**Risks if Extracted**: Need to maintain backward compatibility with legacy rendering
**Before/After**:
- Before = rendering logic mixed in main function (107 lines)
- After = `TemplateRenderer` class with strategy pattern for Jinja2 vs legacy modes
- Conceptual win: Clear rendering contract, testable in isolation
**Reporter**: ResearchAgent-I-GenTemplates
**Status**: MEDIUM priority extraction

---

### [BUCKET:utilities] Input Format Normalization
**Origin**: `generate_doc_templates.py:299-337` (~38 LOC)
**Responsibilities**: Parse and normalize document selection from various input formats (None, Iterable, JSON string, CSV string)
**Used By**: generate_doc_templates (documents parameter)
**Potential Reuse**: query_entries (document_types), rotate_log (log_types), any tool accepting flexible formats
**Why It Should Be Shared**:
- Multi-format input handling is common pattern
- JSON/CSV parsing logic duplicated across tools
- Safe defaults (return all) pattern is reusable
**Risks if Extracted**: Different tools have different valid value sets (documents vs log_types)
**Before/After**:
- Before = `_select_documents()` specific to this tool
- After = `normalize_multi_format_input(raw, valid_values, default_all=True)` in shared utilities
- Conceptual win: Reusable across all tools accepting flexible formats
**Reporter**: ResearchAgent-I-GenTemplates
**Status**: LOW priority extraction (nice-to-have)

---

### [BUCKET:templating] Metadata Builder Registry
**Origin**: `generate_doc_templates.py:343-546` (~203 LOC including builders)
**Responsibilities**: Plugin-based metadata generation for template rendering context
**Used By**: generate_doc_templates (METADATA_BUILDERS dict)
**Why It Should Be Shared**:
- Extensible metadata system for custom doc types
- Clear extension contract via builder functions
- Plugin pattern enables user customization
**Risks if Extracted**: Metadata builders are tightly coupled to specific document types
**Before/After**:
- Before = Hardcoded `METADATA_BUILDERS` dict with 7 builders
- After = Plugin-based registry allowing custom builders: `MetadataRegistry.register(doc_type, builder_func)`
- Conceptual win: Extensible metadata system, custom doc types supported
**Reporter**: ResearchAgent-I-GenTemplates
**Status**: LOW priority extraction (advanced feature)

---

### Token Bloat: Template Metadata Verbosity
**Affected Tools**: `generate_doc_templates.py` (validation mode with `include_template_metadata=True`)
**Token Cost**: 850+ tokens in validation mode (450 tokens from template metadata alone)
**Root Cause**: Template metadata includes full template info, directory lists, available templates
**Optimization Target**: Only include when explicitly requested (already implemented correctly)
**Current Behavior**: ✅ Metadata only added when `include_template_metadata=True`
**Further Optimization**: Consider compact format for metadata (omit rarely-used fields)
**Reporter**: ResearchAgent-I-GenTemplates
**Status**: No action needed (current behavior is correct)

---

**Last Updated**: 2026-01-05 03:30 UTC (ResearchAgent-I-GenTemplates findings added)
**Maintained By**: All Phase 1 & Phase 2 Research Agents (A through L)

## Duplicated Filter Logic [BUCKET:filtering]

<!-- Format: Tools affected, LOC duplicated, unification opportunity -->

### Pattern: Priority/Category/Confidence Filtering
**Discovery**: EXACT filter duplication between read_recent and query_entries
**Locations**:
- `read_recent.py:512-519` - Filter normalization (_normalise_filters)
- `read_recent.py:553-569` - Filter application (_apply_line_filters)
- `query_entries.py:710-726` - Filter chain application (priority, category, confidence)
**Filters Duplicated** (7 total):
1. Agent filter (exact name match)
2. Status/Emoji filter (status → emoji mapping)
3. Priority filter (meta.priority in list)
4. Category filter (meta.category in list)
5. Confidence filter (meta.confidence >= threshold)
6. Pagination (page/page_size calculation)
7. Format routing (readable/structured/compact)
**Impact**: ~120 LOC duplicated, identical metadata extraction logic
**Recommendation**: Extract FilterChain [BUCKET:filtering] with composable filter classes
**Reporter**: ResearchAgent-H-ReadRecent
**Status**: High priority extraction candidate

### Proposed FilterChain Architecture
```python
# Composable filter system (shared across tools)
class FilterChain:
    def __init__(self, filters: List[Filter]):
        self.filters = filters

    def apply(self, entries: List[Dict]) -> List[Dict]:
        return [e for e in entries if all(f.matches(e) for f in self.filters)]

# Individual reusable filters
class PriorityFilter(Filter):
    def matches(self, entry: Dict) -> bool:
        priority = entry.get("meta", {}).get("priority", "medium")
        return priority in self.priorities

# Usage in both tools
chain = FilterChain([
    AgentFilter(agent) if agent else None,
    PriorityFilter(priority) if priority else None,
    # ...
])
filtered = chain.apply(entries)
```
**Benefits**: Testable filters, composable, reusable, single bug fix location
**Lines Saved**: ~120 LOC

---

## Duplicated Parameter Healing [BUCKET:parameter_validation]

<!-- Format: Tools affected, healing patterns, consolidation opportunity -->

### Pattern: Numeric Parameter Healing
**Discovery**: Parameter healing logic duplicated across read_recent and query_entries
**Locations**:
- `read_recent.py:33-148` - _ReadRecentHelper.heal_parameters_with_exception_handling()
- `query_entries.py:61-407` - _validate_search_parameters()
**Parameters Healed**:
- n/limit → int with fallback
- page → int, min 1
- page_size → int, clamp 1-200
- compact → string "true" to boolean
- fields → comma-separated string to list
**Impact**: ~146 LOC duplicated
**Recommendation**: Extract ParameterHealer [BUCKET:parameter_validation] with tool-specific schemas
**Reporter**: ResearchAgent-H-ReadRecent
**Status**: Medium priority extraction candidate

---

## Token Bloat: raw_line Duplication

<!-- Format: Tool affected, bloat source, optimization target -->

### Source: raw_line Field in Structured Output
**Affected Tools**: `read_recent.py`, likely others returning log entries
**Token Cost**: 100% duplication (raw_line repeats entire entry as markdown string)
**Root Cause**: Entry has structured fields (id, ts, emoji, agent, message, meta) PLUS raw_line with same content
**Evidence**:
- Structured format 3 entries = 2940 chars
- Readable format 3 entries = 1891 chars
- 35% bloat from raw_line duplication
**Optimization Target**: Remove raw_line from structured/compact output = 50% token reduction
**Reporter**: ResearchAgent-H-ReadRecent
**Status**: See SPEC-RR-004 for removal plan

### Bloat Breakdown (read_recent specific)
1. **STRUCTURAL** (15%): JSON syntax, pagination object
2. **METADATA** (100%): raw_line duplicates entire entry
3. **DUPLICATION**: Message appears in both message field and raw_line
4. **SAFETY_PADDING**: limit_metadata, reminders, recent_projects always included

---

## Known Tool Bugs Requiring Cross-Tool Fixes

<!-- Format: Bug ID, tools affected, root cause, fix strategy -->

### BUG: Compact Mode Not Functioning
**Bug ID**: SPEC-RR-002 (may be broader than read_recent)
**Tools Affected**: read_recent.py (confirmed), possibly others using ResponseFormatter
**Location**: utils/response.py (likely)
**Symptoms**: format="compact" returns identical output to format="structured"
**Evidence**: read_recent token samples 1 and 3 both 2940 chars despite different format
**Root Cause**: ResponseFormatter not applying compact transformation
**Impact**: Users expecting compact output get full structured bloat
**Fix Strategy**: Investigate ResponseFormatter.finalize_tool_response() compact mode implementation
**Reporter**: ResearchAgent-H-ReadRecent
**Status**: Needs investigation across all tools using ResponseFormatter

### BUG: Priority Sort Backend Inconsistency
**Bug ID**: SPEC-RR-003
**Tools Affected**: read_recent.py
**Symptoms**: priority_sort works in file backend but ignored in database backend
**Root Cause**: Incomplete feature implementation - only file backend applies sorting
**Impact**: Inconsistent behavior depending on backend
**Fix**: Apply priority_sort to database results also
**Reporter**: ResearchAgent-H-ReadRecent
**Status**: Implementation spec provided

---

---

## Duplicated Frontmatter Parsing

### Pattern: Frontmatter Parser Duplication
**Discovery**: Two separate frontmatter parsing implementations exist
**Locations**:
- `tools/read_file.py:180-244` - Custom implementation with byte/line counting
- `utils/frontmatter.py` - Shared implementation (used by manage_docs)
**Impact**:
- Code duplication (~65 LOC duplicated logic)
- Divergence risk - updates must be made in two places
- Maintenance burden - bug fixes need double application
**Root Cause**: Shared frontmatter parser doesn't return byte/line counts needed by read_file
**Recommendation**: **UNIFICATION, not extraction** - enhance `utils/frontmatter.parse_frontmatter()` to return extended `FrontmatterResult` with `byte_count`, `line_count`, `raw_text` fields
**Before/After**:
- Before: Two frontmatter parsers - read_file custom (lines 180-244), utils/frontmatter shared
- After: Single source of truth - enhance utils/frontmatter with extended metadata, delete read_file custom parser
**Reporter**: ResearchAgent-F-ReadFile
**Status**: HIGH priority unification (not simple extraction - existing module incomplete)

---

## File I/O Infrastructure Gaps

### Pattern: File Scanning/Chunking/Extraction Duplication Risk
**Discovery**: read_file.py contains generic file I/O operations that could be reusable
**Locations**:
- `read_file.py:119-178` - `_scan_file()` (SHA256, encoding detection, line counting)
- `read_file.py:247-318` - `_iter_chunks()` (streaming chunk iteration)
- `read_file.py:320-349` - `_extract_line_range()` (arbitrary line extraction)
- `read_file.py:360-427` - `_search_file()` (literal/regex/fuzzy search)
**Impact**:
- If other tools need file scanning → duplication risk
- If log rotation needs chunking → duplication risk
- If grep-like functionality needed → duplication risk
**Recommendation**: Extract to [BUCKET:file_io] modules with clear contracts
**Modules Identified**:
1. `FileScanner` - File metadata extraction (size, hash, encoding, newlines, line count)
2. `FileChunker` - Memory-bounded streaming with byte/line metadata
3. `FileSearcher` - Multi-mode search (literal, regex, fuzzy) with context windows
**Reporter**: ResearchAgent-F-ReadFile
**Status**: MEDIUM priority extraction (no current duplication, but anticipatory)

---

## Security Boundary Infrastructure

### Pattern: Repo-Scoping Policy Enforcement
**Discovery**: read_file.py implements repo-scoping security boundary via denylist/allowlist
**Locations**:
- `read_file.py:26-117` - Security policy enforcement (path validation)
- `read_file.py:42-52` - Sentinel config loading from `.scribe/sentinel/sentinel_config.yaml`
**Impact**:
- Security boundary exists but NOT reusable for future file operations
- If future write_file tool created → must duplicate security logic
- If git operations need repo-scoping → must duplicate security logic
**Recommendation**: Extract to [BUCKET:security] - `RepoSecurityPolicy` class
**Contract**:
- **Inputs**: `path: Path`, `repo_root: Path`, `config: Optional[Dict]`
- **Outputs**: `None` (allowed) | `"denylist_match"` | `"absolute_path_not_allowlisted"`
- **Failure Policy**: Never raises, returns error strings for violations
- **State**: Stateless (loads config on every call)
**Before/After**:
- Before: Security logic embedded in read_file (96 LOC), not reusable
- After: `RepoSecurityPolicy.validate_path()` used by read_file, future write_file, git tools
**Reporter**: ResearchAgent-F-ReadFile
**Status**: HIGH priority extraction (security infrastructure should be centralized)

---

## Silent Configuration Failures

### Pattern: Silent YAML Config Parse Errors
**Discovery**: read_file.py silently returns empty dict on sentinel config parse errors
**Locations**:
- `read_file.py:42-52` - `_load_sentinel_config()` with broad `except Exception: return {}`
**Impact**:
- Security policy silently disabled on config typos
- Users don't know denylist/allowlist isn't enforced
- Silent security failures are dangerous
**Root Cause**: Error suppression without logging
**Recommendation**: Return tuple `(config: dict, error: Optional[str])`, caller logs warnings
**Before/After**:
- Before: Config errors swallowed silently, security policy disabled without warning
- After: Parse errors reported, users warned, can fix YAML syntax
**Reporter**: ResearchAgent-F-ReadFile
**Status**: BUG-READ-001 (HIGH priority security enhancement)

---

## Encoding Fallback Logic Duplication

### Pattern: UTF-8 → latin-1 Fallback Duplicated 4x
**Discovery**: Encoding fallback logic duplicated in multiple functions within read_file.py
**Locations**:
- `read_file.py:162-166` - In `_scan_file()`
- `read_file.py:261` - In `_iter_chunks()`
- `read_file.py:347` - In `_extract_line_range()`
- `read_file.py:386` - In `_search_file()`
**Impact**:
- Adding UTF-16 support requires changing 4 locations
- Divergence risk - fallback logic could drift
- Maintenance burden - same pattern repeated
**Recommendation**: Create shared `_decode_with_fallback(data, primary='utf-8', fallback='latin-1') -> str` function
**Before/After**:
- Before: 4 copies of identical try/except decode logic
- After: Single decode function, 4 call sites updated
**Reporter**: ResearchAgent-F-ReadFile
**Status**: BUG-READ-004 (LOW priority refactoring, no immediate bug)

---

## Resource Limit Gaps

### Pattern: Unbounded Response Sizes in Stream Modes
**Discovery**: read_file.py `full_stream` mode has no upper bound on max_chunks
**Locations**:
- `read_file.py:691-717` - `full_stream` mode handler
**Impact**:
- Caller passing `max_chunks=10000` on 50MB file → 200K+ tokens → OOM
- DoS vector - no resource protection
- Token explosion risk for agents
**Recommendation**: Add `_MAX_CHUNKS_PER_REQUEST = 50` constant, clamp max_chunks
**Before/After**:
- Before: No limit, full_stream can return entire 50MB file (200K+ tokens)
- After: Limited to 50 chunks max (10K lines), log warning if clamped
**Reporter**: ResearchAgent-F-ReadFile
**Status**: BUG-READ-003 (MEDIUM priority resource limit)

---

## Token Bloat: Reminders Always Included

### Pattern: Reminders Fetched for Every read_file Call
**Discovery**: read_file.py fetches and includes reminders in every response, even scan_only
**Locations**:
- `read_file.py:504-515` - `get_reminders()` helper
- `read_file.py:519` - Reminders added to all responses
**Impact**:
- 0-500 tokens overhead per read
- Especially problematic for high-frequency scan_only reads
- Reminder fetch is async - could introduce latency
**Recommendation**: Make reminders opt-in via `include_reminders=true` parameter
**Before/After**:
- Before: Reminders always fetched and included (even when not needed)
- After: Reminders only fetched if `include_reminders=true` (default false for high-freq tools)
**Reporter**: ResearchAgent-F-ReadFile
**Status**: Token optimization opportunity (documented in read_file.md)

---

## Token Bloat: Frontmatter Raw Text Duplication

### Pattern: frontmatter_raw Always Included in Responses
**Discovery**: read_file.py always includes `frontmatter_raw` field even when not needed
**Locations**:
- `read_file.py:586-593` - Response assembly with frontmatter fields
**Impact**:
- 50-200 tokens per read for frontmatter raw text
- Rarely needed by callers (debugging use case only)
- Duplicates information already in parsed `frontmatter` dict
**Recommendation**: Make `frontmatter_raw` opt-in via parameter (only include if requested)
**Before/After**:
- Before: All frontmatter fields always included (frontmatter, frontmatter_raw, has_frontmatter, etc.)
- After: `frontmatter` and `has_frontmatter` always included, `frontmatter_raw` only if `include_raw_frontmatter=true`
**Reporter**: ResearchAgent-F-ReadFile
**Status**: Token optimization opportunity (50-200 token savings per read)

---


## Wave 2 Findings: list_projects + get_project (ResearchAgent-G)

### [BUCKET:metadata] DocInventoryGatherer (CONFIRMED DUPLICATION-002)
**Origin**: `list_projects.py:50-128` + `get_project.py:130-179` + `set_project.py:61-127`
**LOC Impact**: ~90-100 LOC duplicated 3x = 270-300 LOC total waste
**Responsibilities**:
- Check existence of ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST, PROGRESS_LOG
- Count lines in each document (via `default_formatter._get_doc_line_count()`)
- Count entries in progress log (via entry marker detection)
- Detect custom content (research files, bugs, jsonl files)
- Optionally compute doc hashes for drift detection (get_project variant only)

**Why Extract**:
- 3x duplication creates maintenance burden (bug fixes must be replicated)
- Inconsistent implementations (set_project uses regex, get_project uses parse_log_line)
- Hash tracking only in get_project variant (should be universal capability)
- All tools need identical "project state" definition

**Risks if Extracted**:
- Custom content detection varies by tool (set_project includes different metadata)
- Hash tracking is optional feature (not all callers need it)
- **Mitigation**: Use feature flags (`compute_hashes`, `include_custom_metadata`)

**Before/After**:
- **Before**: 3 tools independently decide what "project inventory" means, leading to inconsistencies
- **After**: Single `DocInventoryGatherer` defines canonical project state, tools adapt results to presentation needs
- **Conceptual Win**: "Get project doc status" becomes a named, testable operation with consistent semantics

**Reporter**: ResearchAgent-G-ListGetProjects
**Status**: CRITICAL - unblocks BUG-001 fix (requires hash tracking integration)

---

### [BUCKET:parsing] LogEntryParser
**Origin**: `get_project.py:70-127` (~58 LOC)
**Responsibilities**:
- Parse log entry format: `[emoji] [timestamp] [Agent: name] [Project: name] message`
- Extract components without truncation
- Return last N entries with complete messages

**Why Extract**:
- Entry parsing appears in get_project (confirmed), likely in read_recent/query_entries (needs verification)
- Log format is centrally defined, tools shouldn't know parsing details
- Single source of truth for "what is a valid log entry"

**Risks if Extracted**: Need to verify read_recent/query_entries use same parsing logic

**Before/After**:
- **Before**: Each tool parses log format independently (potential inconsistencies)
- **After**: Single `LogEntryParser.parse_line()` used by all query tools
- **Conceptual Win**: Log format is centrally defined, tools don't know parsing details

**Reporter**: ResearchAgent-G-ListGetProjects
**Status**: MEDIUM priority - enables consistent log parsing

---

### [BUCKET:formatting] TOKEN-001 Root Cause (list_projects)
**Origin**: `list_projects.py:372-468` (3-way readable routing) + `utils/response.py:format_projects_table()`
**Impact**: 1000+ tokens for 10-project table (target: <400 tokens, 60% reduction required)

**Token Breakdown** (10 projects, page 1 of 2):

| Category | Token Estimate | Evidence | Removable? |
|----------|----------------|----------|------------|
| **Structural** | 350-400 | Box drawing (╔═╗), header, column headers, separator lines | Partially (compact mode can skip boxes) |
| **Metadata** | 200-250 | Project names (30 chars each × 10), status (12 chars × 10), entries, timestamps | No (essential data) |
| **Duplication** | 150-200 | Header text repeated in box, pagination shown twice, filter hints | Yes (consolidate header, single pagination line) |
| **Safety Padding** | 150-200 | "Use page=2 to see more" instruction, filter hints, emoji markers | Partially (move to docs, use symbols only) |

**TOTAL**: ~850-1050 tokens (matches 1000+ token observation)

**Optimization Targets**: See wiki/tools/list_projects.md SPEC-LIST-001 for detailed implementation plan (40-50% reduction achievable)

**Reporter**: ResearchAgent-G-ListGetProjects
**Status**: HIGH priority - addresses pre-identified TOKEN-001 issue

---

### [BUCKET:persistence] ProjectQueryEngine Unification Opportunity
**Origin**: `list_projects.py:183-251` (multi-source merge) + `get_project.py:28-40` (hash retrieval) + shared patterns
**Impact**: list_projects and get_project share 60-70% of data gathering logic (~230-280 LOC duplicated)

**Phased Extraction Strategy**:
- **Phase 1**: Extract DocInventoryGatherer + LogEntryParser utilities (150-160 LOC reduction)
- **Phase 2**: Create ProjectQueryEngine base class (additional 80-100 LOC reduction)
- **Total**: 230-260 LOC reduction (26-29% of combined 885 LOC)

**Before/After**:
- **Before**: 885 LOC with ~230-280 LOC duplicated across list_projects (533) + get_project (352)
- **After**: ~680-730 LOC with shared infrastructure + focused tool logic
- **Conceptual Win**: "Get project data" becomes a named, testable operation; tools focus on presentation

**Reporter**: ResearchAgent-G-ListGetProjects
**Status**: MEDIUM priority - architectural improvement (defer until Phase 1 utilities proven)
**Full Analysis**: See wiki/analysis/list_get_unification.md for complete unification strategy

---

**Last Updated**: 2026-01-05 03:32 UTC (ResearchAgent-G-ListGetProjects Wave 2 findings added)

---

## Base Infrastructure Patterns (Wave 3 - Agent L)

### Pattern: Response Formatter is TOKEN-001 Source [BUCKET:formatting]
**Discovery**: response.py (2424 LOC) produces 1000+ tokens per tool call
- **Origin**: `utils/response.py:1-2424` (entire file)
- **Token breakdown**:
  - Structural: 350 tokens (boxes, tables, borders, ANSI colors)
  - Metadata: 250 tokens (pagination, filters, tips, reminders)
  - Duplication: 150 tokens (repeated headers/footers)
  - Safety padding: 200 tokens (verbose empty states, defensive explanations)
- **Impact**: ALL tools route through `default_formatter` singleton → all token costs originate here
- **Optimization target**: 60% reduction possible (1000 → 400 tokens)
- **Extractable modules**:
  - BoxDrawing (lines 245-493): `_add_line_numbers()`, `_create_header_box()`, `_create_footer_box()`, `_format_table()`
  - ProjectFormatter (lines 1123-1700): Project table/detail/context formatters
  - LogFormatter (lines 607-799): Log entries with reasoning blocks
  - FileFormatter (lines 497-605): read_file output
- **Reporter**: ResearchAgent-L-BaseConfig
- **Status**: Documented in base_infrastructure_patterns.md, SPEC-TOKEN-001, SPEC-TOKEN-002

### Pattern: Debug Logging in Production (CRITICAL BUG) [BUCKET:error_handling]
**Discovery**: Production code writes to `/tmp/scribe_session_debug.log`
- **Origin**: `shared/logging_utils.py:95-147` (resolve_logging_context)
- **Impact**:
  - File handle leaks (opens 3x per context resolution)
  - Unbounded disk growth (no log rotation)
  - Security issue (world-readable /tmp file with project names)
- **Repro**: Call any logging tool → check `/tmp/scribe_session_debug.log` size
- **Reporter**: ResearchAgent-L-BaseConfig
- **Status**: BUG-BASE-001 (P0 - CRITICAL), SPEC-BASE-002 created

### Pattern: Parameter Healing Duplication [BUCKET:config]
**Discovery**: Two modules do similar parameter normalization
- **Origin**: `tools/base/parameter_normalizer.py:13-116` (163 LOC) + `shared/logging_utils.py:269-477` (208 LOC)
- **Overlap**:
  - Both normalize dict-like inputs (MCP JSON vs metadata)
  - Both support JSON strings
  - Both support legacy `key=value` formats
  - Both have `_try_parse_json_like()` helpers
- **Unification opportunity**: Extract to `utils/parameter_healer.py` (single module, ~300 LOC)
- **Before/After**:
  - Before: 371 LOC scattered across 2 modules
  - After: Single ParameterHealer class with 5 methods (normalize_dict_param, normalize_list_param, coerce_metadata_mapping, normalize_metadata, clean_list)
- **Reporter**: ResearchAgent-L-BaseConfig
- **Status**: SPEC-BASE-004 created

### Pattern: Config Complexity Explosion [BUCKET:config]
**Discovery**: Settings dataclass has 75 flat fields
- **Origin**: `config/settings.py:33-74`
- **Impact**: Hard to understand what settings exist, which are used, how they relate
- **Grouping opportunity**: 75 flat fields → 6 nested dataclasses
  - PathConfig (4 fields): project_root, default_state_path, sqlite_path, dev_plans_base
  - StorageConfig (4 fields): storage_backend, db_url, allow_network, storage_timeout_seconds
  - LimitConfig (5 fields): recent_projects_limit, log_rate_limit_*, log_max_bytes
  - ReminderConfig (5 fields): reminder_defaults, idle/warmup minutes, feature flags
  - VectorConfig (7 fields): vector_enabled, backend, dimension, model, gpu, queue, batch
  - TokenConfig (10 fields): page_size, compact mode, warning thresholds, limits, tokenizer
- **Reporter**: ResearchAgent-L-BaseConfig
- **Status**: CONFIG-002 (P3), SPEC-CONFIG-001 created

### Pattern: Dual Source of Truth (Architecture Smell) [BUCKET:persistence]
**Discovery**: Projects exist in JSON config files AND scribe_projects DB table
- **Origin**: `config/projects/*.json` (3 files) + `scribe_projects` table
- **Conflict**: `logging_utils.py:108-133` checks DB first, falls back to JSON
- **Impact**:
  - Confusion: which source is canonical?
  - Sync issues: DB and JSON can diverge
  - Maintenance burden: update both places
- **Recommendation**: Deprecate JSON configs (3-phase migration)
  - Phase 1: Migration tool to import JSON → DB
  - Phase 2: Warnings on JSON usage (2-3 releases)
  - Phase 3: Remove JSON support entirely
- **Reporter**: ResearchAgent-L-BaseConfig
- **Status**: CONFIG-PROJ-001 (P1), SPEC-CONFIG-PROJ-001 created

### Pattern: Multi-Log Routing System [BUCKET:config]
**Discovery**: log_config.json defines 6 log types with path templates and metadata requirements
- **Origin**: `config/log_config.json:1-32`
- **Log types**: progress (default), doc_updates (automatic via manage_docs), security, bugs, global (repo-wide), tool_logs (audit trail)
- **Features**:
  - Path templates: `{progress_log}`, `{docs_dir}` variables
  - Metadata requirements enforcement: `ensure_metadata_requirements()` validates before write
  - JSONL support: tool_logs uses JSONL format (not Markdown)
  - Auto-rotation: tool_logs has `rotation_threshold: 1000`
- **Why it works**: Declarative config, no code execution, easily extensible
- **Issue**: No JSON schema validation (invalid config causes runtime errors)
- **Reporter**: ResearchAgent-L-BaseConfig
- **Status**: Documented in log_config.md, SPEC-CONFIG-LOG-001 created

### Pattern: Base Classes Enforce Contracts [BUCKET:utilities]
**Discovery**: LoggingToolMixin provides standardized context resolution for ALL logging tools
- **Origin**: `shared/base_logging_tool.py:19-139`
- **Contracts enforced**:
  1. Context preparation: `prepare_context()` → `LoggingContext` dataclass
  2. Response payload assembly: `apply_context_payload()` attaches reminders/recent_projects
  3. Error standardization: `error_response()` for consistent error format
  4. Entry formatting: Routes to `default_formatter.format_response()` (TOKEN-001 coupling)
- **Usage**: 10+ logging tools inherit this mixin
- **Why it works**: Thin coordination layer, delegates to specialized modules (logging_utils, response.py, ProjectRegistry)
- **Reporter**: ResearchAgent-L-BaseConfig
- **Status**: Documented in base_logging_tool.md

### Pattern: Session Routing Monolith [BUCKET:state]
**Discovery**: resolve_logging_context() is 266-line function with 4 fallback paths
- **Origin**: `shared/logging_utils.py:41-266` (46% of entire file!)
- **Routing priority**:
  1. Session-scoped (ExecutionContext.mode == "project")
  2. Agent-scoped (agent_id provided)
  3. Explicit project (explicit_project parameter)
  4. Sentinel mode (ExecutionContext.mode == "sentinel")
  5. Global state fallback (legacy, no ExecutionContext)
- **Complexity**: 4 paths × 2 modes × 7 try-except blocks = difficult to test
- **Recommendation**: Extract routing paths into separate functions (_resolve_session_scoped_project, _resolve_agent_scoped_project, etc.)
- **Reporter**: ResearchAgent-L-BaseConfig
- **Status**: BUG-BASE-002 (P2), SPEC-BASE-003 created


---

## Wave 3 Cross-Cutting Findings (Advanced Features Tools)

**Date**: 2026-01-05
**Reporter**: ResearchAgent-K-AdvancedFeatures
**Tools Audited**: vector_search.py, agent_project_utils.py, manage_docs_validation.py, project_utils.py

---

### Facade Architecture Pattern (CRITICAL DISCOVERY)

**Pattern**: Wave 3 tools are intentional thin facades over infrastructure

**Evidence**:
- vector_search.py (419 LOC) wraps plugins/vector_indexer.py (886 LOC) - Ratio 1:2.1
- agent_project_utils.py (192 LOC) wraps state/agent_manager.py (513 LOC) - Ratio 1:2.7
- Tools contain ZERO business logic, 100% delegation
- All computation in plugins/, state/, doc_management/ directories

**Architectural Principle Discovered**:
- **tools/** directory = MCP tool wrappers only
- **plugins/** directory = Business logic (FAISS, vector indexing)
- **state/** directory = Session management, state coordination
- **doc_management/** directory = Document operations
- **utils/** directory = Shared utilities (SHOULD contain project_utils.py utilities)

**Implication**: Do NOT extract from facade tools - they are already optimally thin. Extract from infrastructure instead.

**Cross-Reference**: This validates Wave 1/2 pattern - monster tools contain business logic, medium tools integrate, small tools are facades.

---

### Critical Duplication: Slugification Logic

**Pattern**: Project name slugification duplicated between tools

**Locations**:
- `project_utils.py:21-24` - `slugify_project_name(name: str)` implementation
- `set_project.py` - Likely has similar slugification (Wave 1 audit needed)

**Duplication Evidence**:
```python
# project_utils.py
def slugify_project_name(name: str) -> str:
    normalised = name.strip().lower().replace(" ", "_").replace("-", "_")
    return _SLUG_CLEANER.sub("_", normalised).strip("_") or "project"
```

**Impact**:
- If slugification diverges, project discovery breaks
- set_project creates directory: `docs/dev_plans/{slug}/`
- list_projects looks for: `config/projects/{slug}.json`
- Mismatch = project not found

**Recommendation**: SPEC-UTIL-001 must unify slugification
1. Compare set_project.py implementation with project_utils.py
2. Extract to `utils/string_utils.py` as single source of truth
3. Update both tools to use shared slugification
4. Add unit tests for slug consistency

**Priority**: CRITICAL - Must be fixed before divergence causes production bugs

**Cross-Reference**: Wave 1 audit for set_project.py should document slugification logic

---

### Candidate Module: BackupOrchestrator [BUCKET:backup_utilities]

**Origin**: vector_search.py:331-391 (_backup_existing_index)
**Comparison Point**: rotate_log.py (Wave 1 - likely has similar backup logic)

**Responsibilities**: Create timestamped backups of files before destructive operations

**Used by**:
- vector_search.rebuild_vector_index() (currently)
- rotate_log() (Wave 1 - needs verification)
- Future: Index archival, log rotation, data migration operations

**Why it should be shared**: Backup orchestration is generic file operation pattern
- Create timestamped backup directory
- Copy files with shutil.copy2 (preserve metadata)
- Track sizes and paths for audit
- Cleanup partial backups on failure

**Contract**:
- **Input**: List[Path] source_paths, Path backup_dir, str repo_slug
- **Output**: Dict with backup metadata (success, paths, sizes)
- **Failure Policy**: Cleanup partial backups, return error dict
- **State Owner**: Filesystem (creates directories, copies files)

**Risks if extracted**:
- Different tools may need different backup metadata
- Timestamp format may vary by use case
- Cleanup policy may differ (some tools keep failed backups for debugging)

**Unification strategy**:
- Extract base contract with configurable metadata
- Add `cleanup_on_failure: bool` parameter
- Make timestamp format configurable
- Allow custom metadata via optional dict parameter

**Next Steps**:
1. Compare with rotate_log.py backup logic (Wave 1 audit)
2. Identify shared patterns vs tool-specific logic
3. Design unified BackupOrchestrator API
4. Extract to `utils/backup_utilities.py`

---

### Candidate Module: FileCacheLRU [BUCKET:caching]

**Origin**: project_utils.py:15-16, 145-161 (module-level _PROJECT_CACHE)
**Duplication**: No direct duplication found, but pattern may exist elsewhere

**Responsibilities**: File-based caching with mtime invalidation and LRU eviction

**Current Implementation**:
```python
_PROJECT_CACHE: Dict[Path, Tuple[float, Dict[str, Any]]] = {}
# Key: Path to file
# Value: (mtime, cached_dict)
# Eviction: LRU at 128 entries
```

**Why it should be shared**: Generic file caching pattern applicable to any config loading
- Prevents repeated disk I/O for frequently accessed configs
- mtime-based invalidation ensures freshness
- LRU eviction prevents unbounded memory growth

**Issues with Current Implementation**:
1. **Module-level global state**: Persists across all requests (stale read risk)
2. **No TTL**: Only mtime invalidation (doesn't handle same-second updates)
3. **Fixed size**: 128 entries hardcoded (should be configurable)
4. **No cache statistics**: Can't measure hit rate or effectiveness

**Recommended Design**:
```python
class FileCache:
    def __init__(self, max_size=128, ttl_seconds=None):
        self._cache = {}
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, path: Path, loader: Callable) -> Optional[Dict]:
        # Check mtime AND TTL
        ...

    def invalidate(self, path: Optional[Path] = None):
        # Explicit cache clearing
        ...

    def stats(self) -> Dict:
        # Return hit_rate, size, oldest_mtime
        ...
```

**Used by**:
- project_utils.py (config loading)
- Potential: Any tool loading JSON/YAML config files repeatedly

**Risks if extracted**:
- Cache lifecycle management (when to create/destroy instance)
- Thread safety (if multiple workers)
- Memory pressure (need configurable eviction policy)

**Unification strategy**:
- Extract class-based cache with configurable size and TTL
- Add explicit cache lifecycle (create in __init__, clear in shutdown)
- Add cache statistics for monitoring
- Make eviction policy configurable (LRU, LFU, TTL-based)

---

### Candidate Module: ParameterValidator [BUCKET:validation]

**Origin**: manage_docs_validation.py:56-165 (EnhancedManageDocsValidator)
**Production Equivalent**: doc_management/manager.py (DocumentValidationError)

**Responsibilities**: Structured parameter validation with actionable error messages

**Validation Methods**:
1. `validate_string()` - Type, length constraints
2. `validate_enum()` - Membership validation
3. `validate_metadata()` - Dict structure with string keys
4. `validate_list()` - List structure with max items
5. `validate_comparison_operators()` - Security validation (prevent injection)

**Why it should be shared**: Generic validation patterns applicable to all tool parameter validation

**Current Split (Problematic)**:
- **Test validation**: manage_docs_validation.py (ParameterValidationError)
- **Production validation**: doc_management/manager.py (DocumentValidationError)
- **Result**: Duplicate validation logic, inconsistent error handling

**Recommended Unification**:
```python
# utils/validation.py
class ParameterValidationError(Exception):
    """Base validation error with structured details"""
    def __init__(self, message, param_name=None, suggestion=None, tool_name=None):
        ...

class ParameterValidator:
    """Reusable parameter validation methods"""
    def validate_string(self, value, param_name, required=True, min_length=1, max_length=None):
        ...
    def validate_enum(self, value, param_name, allowed_values):
        ...
    def validate_metadata(self, value, param_name="metadata"):
        ...
    def validate_list(self, value, param_name, max_items=None):
        ...

class SecurityValidator:
    """Security-focused validation"""
    @staticmethod
    def check_comparison_operators(text: str) -> bool:
        """Prevent numeric comparison injection"""
        ...
```

**Used by**:
- manage_docs.py (production validation)
- append_entry.py (parameter healing)
- query_entries.py (filter validation)
- Tests (via explicit imports, not builtins injection)

**Risks if extracted**:
- Test backwards compatibility (currently uses builtins injection)
- Different tools may need different validation rules
- Error message format may vary by tool

**Unification strategy**:
1. Extract base ParameterValidator to utils/validation.py
2. Update production code to use shared validator
3. Migrate tests to explicit imports (remove builtins injection SPEC-VAL-002)
4. Deprecate manage_docs_validation.py as legacy test support

---

### Candidate Module: SecurityValidator [BUCKET:validation]

**Origin**: manage_docs_validation.py:20-27 (_validate_comparison_symbols)
**Used by**: manage_docs_validation.py (test validation), manage_docs.py (production likely needs it)

**Responsibilities**: Detect numeric comparison operators in user input to prevent injection

**Pattern**: `r"\b\d+(?:\.\d+)?\s*(?:<=|>=|<|>)\s*\d+(?:\.\d+)?\b"`

**Why it should be shared**: Security validation is critical across all tools accepting user content
- Prevents users from injecting code-like patterns
- Protects against comparison operator injection
- Reusable for any user-provided strings (content, templates, metadata)

**Current Issues**:
1. **False Positives**: Matches benign text like "Chapter 5 > Section 3"
2. **Hardcoded Pattern**: Regex not configurable or extensible
3. **Limited Context**: Doesn't distinguish code from prose

**Recommended Design**:
```python
class SecurityValidator:
    COMPARISON_REGEX = re.compile(r"\b\d+(?:\.\d+)?\s*(?:<=|>=|<|>)\s*\d+(?:\.\d+)?\b")

    @staticmethod
    def check_comparison_operators(text: str, strict: bool = True) -> bool:
        """
        Check for numeric comparison operators.

        Args:
            text: User-provided string
            strict: If True, any match fails. If False, context-aware checking.

        Returns:
            True if safe, False if contains operators
        """
        if not isinstance(text, str):
            return True  # Non-strings are safe

        if not strict:
            # Context-aware checking (future enhancement)
            # Could check for surrounding keywords, punctuation, etc.
            pass

        return not bool(SecurityValidator.COMPARISON_REGEX.search(text))

    @staticmethod
    def sanitize_comparison_operators(text: str) -> str:
        """
        Sanitize by escaping comparison operators.

        Returns text with operators HTML-entity encoded.
        """
        replacements = {">": "&gt;", "<": "&lt;", ">=": "&gt;=", "<=": "&lt;="}
        for op, entity in replacements.items():
            text = text.replace(op, entity)
        return text
```

**Used by**:
- manage_docs.py (content, template, metadata validation)
- append_entry.py (message validation)
- Any tool accepting user-provided text

**Risks if extracted**:
- False positives may frustrate users
- Pattern may need refinement (security vs usability trade-off)
- Different tools may need different strictness levels

**Unification strategy**:
- Extract to utils/validation.py with configurable strictness
- Add context-aware checking (future enhancement)
- Provide sanitization method as alternative to rejection
- Document false positive patterns and workarounds

---

### Candidate Module: PathUtils [BUCKET:utilities]

**Origin**: project_utils.py:250-255 (_is_within)
**Used by**: project_utils.py (path security in _normalise_project_data)

**Responsibilities**: Path security validation (prevent directory traversal)

**Why it should be shared**: Path security is critical wherever user-provided paths are resolved
- Prevents `../../etc/passwd` style attacks
- Ensures all paths stay within project root
- Generic pattern applicable to any path resolution

**Current Implementation**:
```python
def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
```

**Recommended Extension**:
```python
class PathUtils:
    @staticmethod
    def is_within(path: Path, parent: Path) -> bool:
        """Check if path is within parent directory (prevent traversal)."""
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def resolve_safe(
        path: Union[str, Path],
        base_dir: Path,
        must_exist: bool = False
    ) -> Optional[Path]:
        """
        Safely resolve path relative to base, return None if escapes.

        Args:
            path: Path to resolve (relative or absolute)
            base_dir: Base directory to resolve against
            must_exist: If True, return None if path doesn't exist

        Returns:
            Resolved path if safe, None otherwise
        """
        resolved = Path(path).expanduser()
        if not resolved.is_absolute():
            resolved = (base_dir / resolved).resolve()
        else:
            resolved = resolved.resolve()

        if not PathUtils.is_within(resolved, base_dir):
            return None  # Security: path escapes base_dir

        if must_exist and not resolved.exists():
            return None

        return resolved
```

**Used by**:
- project_utils.py (project config path resolution)
- set_project.py (likely has similar path security)
- Any tool resolving user-provided paths

**Risks if extracted**:
- Different tools may have different base directory expectations
- Error handling varies (return None vs raise exception)
- Symbolic link handling (should symlinks be followed?)

**Unification strategy**:
- Extract to utils/path_utils.py with configurable behavior
- Add explicit symlink handling policy
- Provide both exception-raising and None-returning variants
- Document security implications

---

### Candidate Module: StringUtils [BUCKET:utilities]

**Origin**: project_utils.py:21-24 (slugify_project_name)
**Duplication**: set_project.py (Wave 1 - needs verification)

**Responsibilities**: String transformation utilities (slugification, normalization)

**Why it should be shared**: Slugification must be consistent across all tools
- set_project creates directories with slugs
- list_projects searches for slugs
- Mismatch = broken project discovery

**Current Implementation**:
```python
_SLUG_CLEANER = re.compile(r"[^0-9a-z_]+")

def slugify_project_name(name: str) -> str:
    normalised = name.strip().lower().replace(" ", "_").replace("-", "_")
    return _SLUG_CLEANER.sub("_", normalised).strip("_") or "project"
```

**Recommended Design**:
```python
class StringUtils:
    SLUG_CLEANER = re.compile(r"[^0-9a-z_]+")

    @staticmethod
    def slugify(
        text: str,
        fallback: str = "default",
        separator: str = "_",
        lowercase: bool = True
    ) -> str:
        """
        Convert text to filesystem-safe slug.

        Args:
            text: Text to slugify
            fallback: Value to return if result is empty
            separator: Character to replace spaces/hyphens with
            lowercase: Convert to lowercase

        Returns:
            Filesystem-safe slug

        Examples:
            >>> StringUtils.slugify("My Project")
            'my_project'
            >>> StringUtils.slugify("Test-123")
            'test_123'
            >>> StringUtils.slugify("")
            'default'
        """
        result = text.strip()
        if lowercase:
            result = result.lower()
        result = result.replace(" ", separator).replace("-", separator)
        result = StringUtils.SLUG_CLEANER.sub(separator, result).strip(separator)
        return result or fallback
```

**Used by**:
- project_utils.py (project name slugification)
- set_project.py (directory creation - Wave 1 audit needed)
- Any tool converting user input to filesystem paths

**Risks if extracted**:
- set_project.py may have different slugification rules (CREATE BUG if diverged)
- Changing slugification breaks existing projects (must be backwards compatible)
- Different tools may need different separator characters

**Unification strategy**:
1. **CRITICAL**: Compare set_project.py implementation with project_utils.py
2. If different, determine which is correct (or if both are bugs)
3. Extract single source of truth to utils/string_utils.py
4. Update both tools to use shared slugification
5. Add unit tests to prevent future divergence
6. Add migration plan if slugification rules change

**Priority**: CRITICAL - Must be unified immediately to prevent project discovery bugs

---

### Misplaced Infrastructure: project_utils.py Should Move to utils/

**Issue**: project_utils.py contains generic utilities but lives in tools/ directory

**Evidence**:
- Contains 5 extractable utilities (caching, slugification, path security, JSON I/O, temp detection)
- Used by multiple tools as infrastructure
- Not an MCP tool itself (provides utilities, doesn't expose MCP endpoints)

**Impact**:
- Mixing utilities with MCP tools is confusing
- tools/ directory should only contain MCP tool wrappers
- Utilities should be in utils/ for clear architecture

**Recommendation**:
1. Extract utilities from project_utils.py to utils/ modules:
   - FileCache → utils/file_cache.py
   - slugify_project_name → utils/string_utils.py
   - _is_within → utils/path_utils.py
   - _read_json → utils/file_utils.py
   - _is_temp_project → utils/file_utils.py
2. Keep config discovery functions in tools/project_utils.py (Scribe-specific)
3. Update imports across codebase

**Timing**: Phase 6, during utility extraction (SPEC-UTIL-001)

---

### Misplaced Test Infrastructure: manage_docs_validation.py Should Move to tests/

**Issue**: manage_docs_validation.py is test infrastructure but lives in tools/ directory

**Evidence**:
- Module docstring: "expected by manage_docs enhancement tests"
- Injects symbols into builtins namespace for test backwards compatibility
- Never imported by production code (only tests/)

**Impact**:
- Confusing architecture (test infrastructure in production tools/)
- Builtins injection is fragile and hard to debug
- Should be in tests/ directory for clarity

**Recommendation**:
1. Extract validation patterns to utils/validation.py (SPEC-VAL-001)
2. Update tests to import explicitly (remove builtins injection SPEC-VAL-002)
3. Move manage_docs_validation.py to tests/ directory
4. Or deprecate entirely once tests use utils/validation.py

**Timing**: Phase 6, during test modernization (SPEC-VAL-002)

---

### Session Isolation Architecture (Migration Coordinator)

**Pattern**: agent_project_utils.py is temporary coordination layer for agent session migration

**Responsibilities**: Bridge AgentContextManager (new) with state_manager (legacy)

**Fallback Chain**:
1. AgentContextManager.get_current_project() (new, agent-scoped sessions)
2. storage_backend.get_project() (database)
3. state_manager.load() (JSON state file)
4. project_utils.load_project_config() (config files)

**Why This Exists**: Enables gradual adoption of agent-scoped sessions without breaking backwards compatibility

**Post-Migration Cleanup** (SPEC-AGT-002):
- After 100% agent session adoption
- Remove state_manager fallback paths
- Remove config file fallback paths
- Simplify from 4-tier to 1-tier lookup
- **Expected LOC reduction**: 40% (from 192 to ~115 LOC)

**Timing**: 6-12 months post Phase 6 (depends on adoption rate)

**Implication**: This is intentional temporary complexity, not over-engineering. Keep until migration complete.

---

### Builtins Namespace Pollution (Test Anti-Pattern)

**Pattern**: manage_docs_validation.py injects symbols into Python builtins for test backwards compatibility

**Problematic Code**:
```python
def _register_test_globals() -> None:
    import builtins
    builtins.ParameterValidationError = ParameterValidationError
    builtins._validate_inputs = _validate_inputs
    builtins._validate_comparison_symbols = _validate_comparison_symbols
    builtins.create_manage_docs_validator = create_manage_docs_validator

_register_test_globals()  # Module-level execution
```

**Impact**:
- Tests reference symbols without visible imports
- Hard to trace where symbols come from
- Pollutes global namespace
- Breaks if builtins change

**Why This Exists**: Backwards compatibility with legacy tests that don't import symbols

**Recommendation** (SPEC-VAL-002):
1. Add explicit imports to all test files
2. Remove _register_test_globals() and call
3. Run full test suite to verify
4. Add deprecation warning to module docstring

**Timing**: Phase 6, during test modernization

**Implication**: This is a temporary hack for backwards compatibility, should be removed

---

### Module-Level Global State (Cache Risk)

**Pattern**: project_utils.py uses module-level dict for caching

**Problematic Code**:
```python
_PROJECT_CACHE: Dict[Path, Tuple[float, Dict[str, Any]]] = {}
```

**Issues**:
1. **Global mutable state**: Persists across all requests
2. **Stale read risk**: If file modified externally between mtime checks
3. **Memory unbounded**: Grows to 128 entries before eviction (hardcoded)
4. **No TTL**: Only mtime invalidation (doesn't handle same-second updates)

**Impact**:
- Hard to debug stale config issues
- Multiple workers may have inconsistent cache views
- No explicit cache lifecycle management

**Recommendation** (SPEC-UTIL-001):
- Extract to class-based FileCache with explicit lifecycle
- Add TTL-based invalidation (not just mtime)
- Add cache statistics (hit rate, size)
- Make size and TTL configurable

**Timing**: Phase 6, during caching framework extraction

**Implication**: Module-level state should be avoided, use dependency injection instead

---

## Wave 3 Summary Statistics

**Tools Audited**: 4
**Total LOC**: 1,152
**Extractable Modules Identified**: 9
- 1 from vector_search.py (backup utilities)
- 0 from agent_project_utils.py (migration-specific)
- 3 from manage_docs_validation.py (validation framework)
- 5 from project_utils.py (configuration utilities)

**Critical Cross-Cutting Concerns**: 3
1. **Slugification duplication** with set_project.py (CRITICAL - must unify)
2. **Module-level cache state** in project_utils.py (high risk of stale reads)
3. **Builtins namespace pollution** in manage_docs_validation.py (fragile test hack)

**Architectural Insights**: 4
1. **Facade pattern validated**: tools/ are thin wrappers (1:2-1:4 ratio to infrastructure)
2. **Migration coordinators needed**: Temporary complexity for gradual adoption (40% reduction post-migration)
3. **Test infrastructure misplaced**: Should be in tests/, not tools/
4. **Configuration utilities misplaced**: Should be in utils/, not tools/

**Token Impact**: Minimal (50-400 tokens from vector_search.py only, other tools are internal utilities)

**Next Wave Dependencies**:
- Wave 3 findings enable utility extraction prioritization
- Slugification unification blocks Phase 6 start
- Validation framework extraction enables consistent validation across all tools


## Wave 3 Findings: Health & Lifecycle Utilities (ResearchAgent-J-HealthLifecycle)

### [BUCKET:diagnostics] Diagnostic Complementarity Pattern
**Discovery**: health_check.py + doctor.py are complementary diagnostic tools
**Reporter**: ResearchAgent-J-HealthLifecycle

### [BUCKET:persistence] BUG-DELETE-001: Multi-Layer Atomicity Failure (P0 CRITICAL)
**Location**: `delete_project.py:113-191`
**Severity**: P0 - Critical (state corruption)
**Problem**: delete_project operates on 3 storage layers (filesystem, DB, state cache) without transaction boundary
**Impact**: Partial failures corrupt state - files deleted but DB intact, or vice versa
**Extractable Module**: MultiLayerStateCleanup [BUCKET:persistence]
**Reporter**: ResearchAgent-J-HealthLifecycle
**Spec**: SPEC-DELETE-001 (complete implementation in delete_project.md)

### [BUCKET:lifecycle] BUG-DELETE-002: Missing Active Session Guards (P1 HIGH)
**Location**: `delete_project.py:101-107`
**Severity**: P1 - High (data loss risk)
**Problem**: Session check not implemented - agents can lose work if project deleted mid-operation
**Extractable Module**: ProjectLifecycleGuards [BUCKET:lifecycle]
**Reporter**: ResearchAgent-J-HealthLifecycle
**Spec**: SPEC-DELETE-002

### [BUCKET:logging] Mode-Aware Routing Pattern (Sentinel vs Project)
**Discovery**: sentinel_tools append_event demonstrates clean delegation (lines 48-70)
**Token Efficiency**: Sentinel mode 85% more efficient (~147 vs ~850 tokens)
**Extractable Module**: ModeAwareEventRouter [BUCKET:logging]
**Reporter**: ResearchAgent-J-HealthLifecycle

### Wave 3 Summary
**Tools**: health_check (274 LOC), doctor (113 LOC), delete_project (217 LOC), sentinel_tools (227 LOC)
**Total**: ~830 lines, 2520 wiki lines, 40 token samples, 10 specs
**Critical**: BUG-DELETE-001 (P0) - Multi-layer atomicity, BUG-DELETE-002 (P1) - Session guards
**Extractables**: 10 modules across 4 buckets (diagnostics, persistence, lifecycle, logging, utilities, bug_tracking)
**Full Analysis**: wiki/analysis/health_lifecycle_patterns.md

---

**Last Updated**: 2026-01-05 03:57 UTC (Wave 3 findings added)
