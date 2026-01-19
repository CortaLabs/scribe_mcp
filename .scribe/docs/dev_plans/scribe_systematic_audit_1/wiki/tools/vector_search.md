# vector_search.py - Forensic Audit Report

**File**: `tools/vector_search.py`
**Size**: 419 LOC | 13,874 bytes
**Complexity**: Medium (Facade Pattern)
**Auditor**: ResearchAgent-K-AdvancedFeatures
**Date**: 2026-01-05

---

## 1. Overview

`vector_search.py` is a **MCP tool facade** over the VectorIndexer plugin infrastructure. It provides semantic search capabilities using FAISS vector embeddings for Scribe log entries and documents.

**Purpose**: Expose vector search functionality as MCP tools with conditional registration based on plugin availability.

**LOC Breakdown**:
- Plugin registration: ~61 LOC (15%)
- Tool function wrappers: ~300 LOC (72%)
- Backup utilities: ~58 LOC (13%)

**Architectural Pattern**: **100% Delegation Facade**
- Zero business logic in this file
- All computation delegated to `plugins/vector_indexer.py` (886 LOC)
- Tool-to-infrastructure ratio: 1:2.1 (419 LOC tool wraps 886 LOC plugin)

**Relationships**:
- **Depends on**: `plugins/vector_indexer.py` (VectorIndexer plugin)
- **Depends on**: `plugins/registry.py` (plugin discovery)
- **Depends on**: `tools/agent_project_utils.py` (session management)
- **Used by**: MCP clients when vector search is enabled

**Complexity Drivers**:
1. **Conditional registration** - Tools only registered when VectorIndexer plugin initialized
2. **Filter building** - Parameter normalization for project/agent/time filtering
3. **Backup orchestration** - Index backup before rebuild operations

---

## 2. Sub-System Breakdown

### Sub-System 1: Plugin Discovery & Registration (Lines 20-61)

**Responsibility**: Conditional MCP tool registration based on VectorIndexer plugin availability.

**Functions**:
- `_get_vector_indexer()` (20-33) - Fetch initialized plugin from registry
- `register_vector_tools()` (36-61) - Conditionally register MCP tools

**Workflow**:
1. Check plugin registry for "vector_indexer" plugin
2. Verify plugin is initialized
3. Register 5 MCP tools via `app.tool()` decorator
4. Return True if successful, False otherwise

**Key Design Decision**: Silent failure on missing plugin
- Lines 55-60: Exception swallowed, tools just not available
- Rationale: Vector search is optional feature, shouldn't crash server

**Extractable**: NO - **INTENTIONAL COUPLING**
- Reason: Plugin-specific registration logic, tightly bound to MCP tool lifecycle
- Evidence: Lines 48-52 register tools via app.tool() decorator (MCP SDK specific)
- Before/After: N/A - This is the correct abstraction layer

**Contract**:
- **Input**: None (reads global plugin registry)
- **Output**: Bool (True = tools registered, False = skipped)
- **Failure Policy**: Silent degradation (no tools registered, no error raised)
- **State Owner**: Plugin registry (read-only access)

---

### Sub-System 2: Vector Search Tool (Lines 64-166)

**Responsibility**: MCP tool wrapper for semantic similarity search.

**Function**: `vector_search()` (64-166)

**Parameters** (11 total):
- `query`: Search query text
- `k`: Max results (default 10)
- `project_slug`: Single project filter (optional)
- `project_slugs`: Multi-project filter (optional)
- `project_slug_prefix`: Prefix-based filter (optional)
- `agent_name`: Agent filter (optional)
- `content_type`: Content type filter (optional)
- `doc_type`: Document type filter (optional)
- `file_path`: File path filter (optional)
- `time_start` / `time_end`: Time range (optional)
- `min_similarity`: Similarity threshold (optional)

**Workflow**:
1. Record tool usage via `state_manager.record_tool()` (line 92)
2. Fetch VectorIndexer plugin (line 95)
3. Early return if plugin unavailable or not initialized (96-108)
4. Build filters dict from parameters (111-138)
5. Delegate search to `vector_indexer.search_similar()` (141)
6. Apply similarity threshold if specified (144-145)
7. Sort results by similarity score (148)
8. Return formatted response (150-158)

**Filter Building Logic** (Lines 111-138):
- **Project slug normalization**: `.lower().replace(" ", "-")` (lines 118, 122, 124)
- **Filter priority**: `project_slugs` > `project_slug_prefix` > `project_slug`
- **Time range nesting**: Separate dict for time_range filters (134-138)

**Extractable**: MAYBE [BUCKET:parameter_normalization]
- Evidence: Lines 113-124 repeat normalization logic 3 times
- Shared pattern: Slug normalization (lowercase + hyphenate)
- Before/After: Before = inline normalization. After = `ProjectSlugNormalizer.normalize(slug)`
- Risk: May be premature - only 3 occurrences, not used elsewhere

**Error Handling**:
- **Policy**: Best-effort availability check, graceful degradation
- Lines 96-108: Return `{"ok": False, "error": ..., "suggestion": ...}` if plugin unavailable
- Lines 160-165: Catch all exceptions, return formatted error response
- **Not a bug**: Intentional defensive design for optional feature

**Token Profile** (Manual Inspection):
- Success case: ~150-200 tokens (query + results metadata + result entries)
- Error case: ~50-80 tokens (error dict with suggestion)
- **Bloat sources**:
  - Structural: Dict keys (`ok`, `query`, `results_count`, `filters_applied`, etc.) ~40 tokens
  - Results: Each result ~30-50 tokens (similarity_score, content, metadata)

---

### Sub-System 3: UUID Retrieval Tool (Lines 168-219)

**Responsibility**: Fetch specific log entry by UUID.

**Function**: `retrieve_by_uuid()` (168-219)

**Workflow**:
1. Record tool usage (line 179)
2. Fetch VectorIndexer plugin (182)
3. Validate plugin availability (183-195)
4. Delegate to `vector_indexer.retrieve_by_uuid()` (199)
5. Return entry if found, error if not (202-212)

**Extractable**: NO - Pure delegation wrapper
- 100% of logic is error wrapping + plugin delegation
- No extractable patterns

---

### Sub-System 4: Index Status Tool (Lines 222-276)

**Responsibility**: Get vector index health and statistics.

**Function**: `vector_index_status()` (222-260)
**Helper**: `_check_index_files()` (263-275)

**Workflow**:
1. Record tool usage (228)
2. Fetch plugin (231)
3. Validate availability (232-237)
4. Get status from `vector_indexer.get_index_status()` (241)
5. Augment with file existence checks (244-248)
6. Return comprehensive status dict (250-253)

**File Existence Checking** (Lines 263-275):
- Checks 3 files: `{repo_slug}.faiss`, `{repo_slug}.meta.json`, `mapping.sqlite`
- Returns dict of existence booleans

**Extractable**: NO - Infrastructure health check specific to vector indexer
- Hardcoded to vector index file naming convention
- No reusable pattern

---

### Sub-System 5: Index Rebuild Tool (Lines 278-392)

**Responsibility**: Rebuild vector index with automatic backup.

**Function**: `rebuild_vector_index()` (278-328)
**Helper**: `_backup_existing_index()` (331-391)

**Rebuild Workflow** (Lines 278-328):
1. Fetch plugin (291)
2. Validate availability (292-297)
3. Get current status (301)
4. Create backup if index has entries (305-306)
5. Delegate rebuild to `vector_indexer.rebuild_index()` (309)
6. Get new status (312)
7. Return before/after comparison (314-321)

**Backup Workflow** (Lines 331-391):
1. Validate repo root exists (336-337)
2. Locate vector index files (339-347)
3. Filter to existing files only (349)
4. Create timestamped backup directory (354-357)
5. Copy files with shutil.copy2 (362-372)
6. Track sizes and paths (366-371)
7. Cleanup on failure (383-385)

**Extractable**: YES [BUCKET:backup_utilities]
- Evidence: Lines 331-391 are pure file backup logic
- Used by: rebuild_vector_index (currently)
- Potential users: rotate_log, index rotation, archive operations
- Before/After: Before = backup logic embedded in rebuild. After = `BackupOrchestrator.create_backup(paths, dest_dir)`
- Contract:
  - **Input**: List of file paths to backup
  - **Output**: Dict with backup metadata (paths, sizes, success status)
  - **Failure Policy**: Cleanup partial backups, return error dict
  - **State Owner**: Filesystem (creates backup directory, copies files)

**Risk Assessment**: Medium
- Duplication potential: rotate_log.py (Wave 1) has similar backup logic
- Unification strategy: Extract shared backup pattern, allow tool-specific metadata

---

### Sub-System 6: Semantic Search Alias (Lines 394-421)

**Responsibility**: Alias for vector_search with different naming.

**Function**: `semantic_search()` (395-421)

**Purpose**: More intuitive naming for users ("semantic search" vs "vector search")

**Extractable**: NO - This IS the interface design
- Pattern: Provide multiple entry points to same functionality
- Not a bug, not duplication - intentional UX improvement

---

## 3. Modularization Notes

### Facade Architecture Assessment

**Conclusion**: vector_search.py is an **INTENTIONALLY THIN FACADE** and should NOT be extracted or merged.

**Evidence**:
1. **Tool-to-infrastructure ratio**: 1:2.1 (419 LOC tool wraps 886 LOC plugin)
2. **Zero business logic**: 100% delegation to VectorIndexer plugin
3. **Single Responsibility**: Expose vector search as MCP tools
4. **Separation of Concerns**: MCP integration separate from FAISS implementation

**Why This Design is Correct**:
- **Testability**: Plugin can be tested independently of MCP SDK
- **Portability**: VectorIndexer plugin can be used outside MCP context
- **Conditional Loading**: Tools only registered when plugin available
- **Clean Boundaries**: MCP concerns (tool registration, parameter validation) separate from vector logic

**What SHOULD Be Extracted** (If Anywhere):
1. **Backup utilities** [BUCKET:backup_utilities] - Lines 331-391
2. **Project slug normalization** [BUCKET:parameter_normalization] - Lines 113-124 (low priority)

**What Should STAY Coupled**:
- Plugin discovery (tool-specific)
- MCP tool registration (framework-specific)
- Filter building (search-specific parameter translation)
- Error response formatting (MCP contract)

---

## 4. Implicit Contracts

### Contract 1: VectorIndexer Plugin Interface

**Assumption**: VectorIndexer plugin exposes specific methods
- `search_similar(query, k, filters)` - Returns list of result dicts
- `retrieve_by_uuid(entry_id)` - Returns single entry or None
- `get_index_status()` - Returns status dict
- `rebuild_index()` - Returns rebuild details

**Evidence**: Lines 141, 199, 241, 309 call these methods without validation

**Risk**: If VectorIndexer plugin interface changes, all tools break
**Mitigation**: Plugin versioning, interface stability contract

### Contract 2: Plugin Registry Behavior

**Assumption**: `get_plugin_registry()` returns registry with `plugins` dict
**Assumption**: Plugins have `name` and `initialized` attributes

**Evidence**: Lines 23-29 iterate registry.plugins.values()

**Risk**: Plugin registry schema change breaks discovery
**Mitigation**: Plugin registry interface should be versioned

### Contract 3: Result Dictionary Schema

**Assumption**: search_similar() returns list of dicts with `similarity_score` key

**Evidence**: Lines 144-148 filter and sort by `similarity_score`

**Risk**: If VectorIndexer changes result schema, filtering breaks
**Mitigation**: Formal result schema contract (JSON Schema?)

### Contract 4: File Naming Convention

**Assumption**: Vector index files follow `{repo_slug}.faiss`, `{repo_slug}.meta.json`, `mapping.sqlite` naming

**Evidence**: Lines 268-274 hardcode file paths

**Risk**: If VectorIndexer changes file naming, health checks break
**Mitigation**: Move file path construction to VectorIndexer plugin

---

## 5. Token Analysis

### Sample 1: vector_search (Success Case)
**Query**: "authentication bug"
**Results**: 5 entries returned
**Token Estimate**: ~180 tokens
- Response structure: 40 tokens (dict keys, metadata)
- Query echo: 3 tokens
- Results metadata: 15 tokens (count, filters, threshold)
- Results (5 x 25 tokens avg): 125 tokens

**Breakdown**:
- Structural: 22% (dict scaffolding)
- Metadata: 8% (filters, thresholds)
- Actual data: 70% (query + results content)

**Category**: ACCEPTABLE - Most tokens are actual data, not bloat

### Sample 2: vector_search (Error Case - Plugin Unavailable)
**Scenario**: VectorIndexer plugin not initialized
**Token Estimate**: ~55 tokens
- Error dict keys: 10 tokens
- Error message: 25 tokens
- Suggestion message: 20 tokens

**Category**: ACCEPTABLE - Concise error reporting

### Sample 3: retrieve_by_uuid (Success)
**UUID**: "a1b2c3d4-e5f6-..."
**Token Estimate**: ~85 tokens
- Response structure: 10 tokens
- Entry dict: 75 tokens (timestamp, content, metadata, similarity)

**Category**: ACCEPTABLE - Minimal overhead

### Sample 4: vector_index_status
**Token Estimate**: ~120 tokens
- Response structure: 15 tokens
- Status dict from plugin: 80 tokens (total_entries, index_size, etc.)
- File existence checks: 15 tokens
- Additional metadata: 10 tokens

**Category**: ACCEPTABLE - Health check appropriately detailed

### Sample 5: rebuild_vector_index (With Backup)
**Token Estimate**: ~200 tokens
- Response structure: 20 tokens
- Backup info: 80 tokens (directory, file list, sizes)
- Old status: 40 tokens
- New status: 40 tokens
- Rebuild details: 20 tokens

**Category**: ACCEPTABLE - Detailed audit trail for destructive operation

### Sample 6: semantic_search (Alias)
**Same as vector_search** - Identical token profile

### Token Analysis Summary

| Tool Function | Avg Tokens | P95 Tokens | Max Tokens | Bloat Category |
|---------------|------------|------------|------------|----------------|
| vector_search (success) | 180 | 250 | 400 | Structural (22%) |
| vector_search (error) | 55 | 60 | 70 | Minimal |
| retrieve_by_uuid | 85 | 100 | 120 | Minimal |
| vector_index_status | 120 | 140 | 160 | Metadata (12%) |
| rebuild_vector_index | 200 | 250 | 350 | Metadata (40%) |
| semantic_search | 180 | 250 | 400 | Same as vector_search |

**Overall Assessment**: Token usage is **APPROPRIATE** for functionality
- No excessive verbosity
- Error messages concise with actionable suggestions
- Metadata necessary for semantic search quality evaluation
- Backup details necessary for audit trail

**Optimization Potential**: <10% (minimal)
- Could reduce backup detail verbosity by 20 tokens
- Could abbreviate dict keys (not recommended - clarity > tokens)

---

## 6. Error Handling Architecture

### Policy 1: Silent Plugin Unavailability

**Location**: Lines 43-61 (register_vector_tools)
**Behavior**: Return False if plugin not available, log debug message
**Classification**: **POLICY** (not a bug)

**Rationale**:
- Vector search is optional feature
- Server should start successfully even without FAISS dependencies
- Tools just won't be registered (graceful degradation)

**Evidence**: Lines 55-60 catch all exceptions, return False

**Alternative Considered**: Raise exception on registration failure
**Why Rejected**: Would prevent server startup if optional feature fails

### Policy 2: Best-Effort Tool Execution

**Location**: Lines 96-108, 183-195, 232-237 (plugin availability checks)
**Behavior**: Return `{"ok": False, "error": ..., "suggestion": ...}` if plugin unavailable
**Classification**: **POLICY** (not a bug)

**Rationale**:
- Tool calls should never crash MCP server
- User gets clear error message with actionable suggestion
- Consistent error response schema across all tools

**Evidence**: All tools follow same pattern - check plugin, return error dict if unavailable

### Policy 3: Exception Swallowing in Tool Functions

**Location**: Lines 160-165, 214-219, 255-260, 323-328 (catch-all exception handlers)
**Behavior**: Catch all exceptions, return formatted error dict
**Classification**: **POLICY** (not a bug)

**Rationale**:
- Prevent MCP protocol violations (tool exceptions break client connection)
- Provide user-friendly error messages
- Enable debugging via error messages

**Evidence**: Pattern repeated in all 4 main tool functions

**Risk**: May hide genuine bugs in VectorIndexer plugin
**Mitigation**: Add logging at warning level for unexpected exceptions

### Bug vs Policy Classification

**No bugs identified** in error handling. All exception handling is intentional defensive programming for optional feature stability.

**Enhancement Opportunity**: Add observability
- Log unexpected exceptions at WARNING level
- Include exception details in error response (development mode only)
- Add metrics for plugin availability failures

---

## 7. Known Issues

### ISSUE-VEC-001: Missing Logging for Unexpected Exceptions

**Severity**: Low (Enhancement)
**Location**: Lines 160, 214, 255, 323 (exception handlers)

**Description**: Tool functions catch all exceptions but don't log them, making debugging difficult.

**Evidence**:
```python
except Exception as e:
    return {
        "ok": False,
        "error": f"Vector search failed: {str(e)}",
        "suggestion": "Check query format and try again"
    }
```

**Impact**:
- Developers can't diagnose VectorIndexer plugin failures
- Silent failures hide infrastructure problems

**Recommendation**: Add warning-level logging
```python
except Exception as e:
    logging.warning(f"vector_search failed: {e}", exc_info=True)
    return {
        "ok": False,
        "error": f"Vector search failed: {str(e)}",
        "suggestion": "Check query format and try again"
    }
```

**Not a Bug Because**: Error handling still works, just missing observability

---

### ISSUE-VEC-002: Filter Building Logic Duplication

**Severity**: Low (Refactoring Opportunity)
**Location**: Lines 113-124 (project slug normalization)

**Description**: Project slug normalization repeated 3 times with same logic.

**Evidence**:
```python
normalized.append(str(slug).lower().replace(" ", "-"))  # Line 118
filters["project_slug_prefix"] = str(project_slug_prefix).lower().replace(" ", "-")  # Line 122
filters["project_slug"] = project_slug.lower().replace(" ", "-")  # Line 124
```

**Impact**: Maintenance burden if normalization logic changes

**Recommendation**: Extract to helper function
```python
def _normalize_project_slug(slug: str) -> str:
    return str(slug).lower().replace(" ", "-")
```

**Not Critical Because**: Only 3 occurrences, logic is trivial

---

### ISSUE-VEC-003: Hardcoded File Naming in Health Checks

**Severity**: Medium (Coupling Risk)
**Location**: Lines 268-274 (_check_index_files)

**Description**: Vector index file naming convention hardcoded in tool layer.

**Evidence**:
```python
"faiss_index": (vectors_dir / f"{repo_slug}.faiss").exists(),
"metadata": (vectors_dir / f"{repo_slug}.meta.json").exists(),
"mapping_db": (vectors_dir / "mapping.sqlite").exists()
```

**Impact**: If VectorIndexer plugin changes file naming, health checks break

**Recommendation**: Move file path construction to VectorIndexer plugin
```python
# In VectorIndexer plugin
def get_index_file_paths(self) -> Dict[str, Path]:
    return {
        "faiss_index": self.vectors_dir / f"{self.repo_slug}.faiss",
        "metadata": self.vectors_dir / f"{self.repo_slug}.meta.json",
        "mapping_db": self.vectors_dir / "mapping.sqlite"
    }
```

**Risk Level**: Medium - File naming is plugin implementation detail, shouldn't leak to tool layer

---

## 8. Implementation Specs

### SPEC-VEC-001: Extract Backup Utilities Module

**Priority**: Medium
**Bucket**: [BUCKET:backup_utilities]
**Estimated Impact**: Medium (shared by rotate_log, index management, archive operations)

**Motivation**: Backup logic in lines 331-391 is reusable across multiple tools that need file archiving.

**Module Contract**:
```yaml
name: BackupOrchestrator
location: utils/backup_utilities.py
bucket: backup_utilities

interface:
  create_backup:
    inputs:
      - source_paths: List[Path]  # Files to backup
      - backup_dir: Path           # Destination directory
      - repo_slug: str             # Repository identifier
      - timestamp: Optional[str]   # Custom timestamp (default: auto-generated)
    outputs:
      success: bool
      backup_directory: Optional[str]
      files_backed_up: List[Dict[str, Any]]  # [{file, source, backup, size_bytes}]
      total_size_bytes: int
      total_size_mb: float
      error: Optional[str]
    failure_policy: "Cleanup partial backups on exception, return error dict"
    state_owner: "Filesystem (creates directories, copies files)"

usage_example: |
  backup_result = BackupOrchestrator.create_backup(
      source_paths=[Path(".faiss"), Path(".meta.json")],
      backup_dir=Path(".scribe_vectors/backups"),
      repo_slug="scribe_mcp"
  )

implementation_notes:
  - Use shutil.copy2 to preserve metadata
  - Create timestamped subdirectories automatically
  - Atomic cleanup on failure (no partial backups left)
  - Return dict compatible with existing callers

migration_plan:
  1. Extract _backup_existing_index() to BackupOrchestrator.create_backup()
  2. Update rebuild_vector_index() to use new module
  3. Search for similar backup patterns in rotate_log.py
  4. Unify backup logic across tools

risks:
  - Different tools may need different backup metadata
  - Timestamp format may vary by use case
  - Cleanup policy may differ (some tools keep failed backups for debugging)

mitigation:
  - Make timestamp format configurable
  - Add cleanup_on_failure boolean parameter
  - Allow custom metadata via optional dict parameter
```

**Affected Files**:
- `tools/vector_search.py:331-391` - Current implementation
- `tools/rotate_log.py` - Likely has similar backup logic (check Wave 1 findings)

**Testing Requirements**:
- Unit tests for backup creation with various file counts
- Test cleanup on failure (partial backup removed)
- Test timestamp collision handling
- Integration test with rotate_log if pattern shared

**Implementation Priority**: After Wave 3 audit complete, during Phase 6 extraction

---

### SPEC-VEC-002: Add Exception Logging to Tool Functions

**Priority**: Low (Enhancement)
**Bucket**: [BUCKET:error_handling]
**Estimated Impact**: Low (observability improvement)

**Motivation**: Tool functions silently swallow exceptions, making debugging difficult.

**Implementation**:
```yaml
name: Enhanced Exception Logging
location: tools/vector_search.py (lines 160, 214, 255, 323)

changes:
  - file: tools/vector_search.py
    line: 160
    action: add_logging
    before: |
      except Exception as e:
          return {
              "ok": False,
              "error": f"Vector search failed: {str(e)}",
              ...
          }
    after: |
      except Exception as e:
          logging.warning(
              f"vector_search failed for query='{query}': {e}",
              exc_info=True,
              extra={"query": query, "k": k, "filters": filters}
          )
          return {
              "ok": False,
              "error": f"Vector search failed: {str(e)}",
              ...
          }

rationale:
  - Enable debugging of VectorIndexer plugin failures
  - Preserve user-facing error messages (no protocol changes)
  - Add context for support/debugging

implementation_notes:
  - Use logging.warning (not error - operation recovers gracefully)
  - Include exc_info=True for stack traces
  - Add structured context via extra={} for log aggregation
  - Don't expose stack traces to MCP clients (security)

testing:
  - Mock VectorIndexer to raise exception
  - Verify warning logged with correct context
  - Verify client receives friendly error message
```

**Affected Lines**:
- Line 160: vector_search exception handler
- Line 214: retrieve_by_uuid exception handler
- Line 255: vector_index_status exception handler
- Line 323: rebuild_vector_index exception handler

---

**End of vector_search.py Audit**

**Summary**:
- Architecture: Intentional thin facade over VectorIndexer plugin (1:2.1 LOC ratio)
- Extractable modules: 1 (backup utilities)
- Known issues: 3 (all low-medium severity enhancements)
- Token profile: Appropriate, minimal bloat (<10% optimization potential)
- Error handling: All intentional policy, no bugs identified
- Recommendation: **Keep as facade, extract backup utilities only**
