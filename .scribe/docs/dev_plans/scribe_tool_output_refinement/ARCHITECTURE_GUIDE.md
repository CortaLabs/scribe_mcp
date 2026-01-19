---
id: scribe_tool_output_refinement-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe_tool_output_refinement"
doc_type: architecture
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-02'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — scribe_tool_output_refinement
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-02 13:47:01 UTC

> Architecture guide for scribe_tool_output_refinement.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement
<!-- ID: problem_statement -->
- **Context:** Scribe MCP tools return JSON-wrapped outputs that are difficult for AI agents to read and use effectively. The `read_file` tool exemplifies this: content is buried in nested structures with escaped newlines, no line numbers, and metadata mixed with content. Agents avoid using these tools despite their audit capabilities.
- **Goals:**
  - Make ALL Scribe MCP tool outputs agent-friendly and highly readable
  - Preserve full audit trail (sha256, provenance, timestamps, agent identity)
  - Start with `read_file` as the priority tool, then expand to all tools
  - Create output formats that agents WANT to use
  - Maintain backward compatibility for existing integrations
- **Non-Goals:**
  - Breaking existing API contracts
  - Removing audit/provenance capabilities
  - Creating entirely new tools (we refine existing ones)
- **Success Metrics:**
  - Agents prefer Scribe tools over raw file operations
  - Output is readable at a glance (line numbers, actual line breaks)
  - Audit data is accessible but not obstructive
  - All existing tests continue to pass
<!-- ID: requirements_constraints -->
## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->

### Functional Requirements

**FR1: Multi-Format Output Support**
- All tools MUST support three output formats: `readable`, `structured`, `compact`
- Format selection via optional `format` parameter (default: `structured` for backward compatibility)
- Each format serves distinct use case:
  - `readable`: Agent-friendly with line numbers, visual separators, actual line breaks
  - `structured`: Current JSON format for programmatic consumers (backward compatible)
  - `compact`: Minimal output for token-constrained scenarios

**FR2: Readable Format Specification**
- Content MUST be line-numbered using cat -n style: `  1→content`, `  2→content`
- Line numbers right-aligned with arrow separator for scannability
- Actual line breaks (NOT escaped `\n`)
- Metadata in separate collapsible section with visual boundaries
- ASCII art separators for clear visual hierarchy

**FR3: Priority Tool Coverage**
1. `read_file` - File content with provenance (HIGHEST PRIORITY)
2. `append_entry` - Log confirmation
3. `read_recent` - Recent log entries
4. `query_entries` - Search results
5. `list_projects` - Project listing
6. All remaining 9 tools

**FR4: Metadata Preservation**
- All audit data MUST be preserved: sha256, timestamps, provenance, agent identity
- Metadata placed in separate section (not mixed with content)
- Collapsible metadata blocks using ASCII separators
- Full audit trail accessible in all formats

### Non-Functional Requirements

**NFR1: Backward Compatibility**
- Default format MUST be `structured` (current behavior)
- Existing tool responses MUST remain unchanged when format parameter not specified
- All existing tests MUST pass without modification
- No breaking changes to tool APIs

**NFR2: Performance**
- Output formatting MUST NOT degrade performance below existing baselines
- `readable` format generation ≤ 5ms overhead per tool call
- Memory overhead ≤ 2x current usage (for formatted strings)
- Existing performance test suite MUST pass

**NFR3: Maintainability**
- Extend existing `utils/response.py` - NO new modules
- Single source of truth for formatting logic
- Consistent API across all tools
- Clear documentation for format implementations

### Hard Constraints

**C1: Audit Trail Completeness**
- SHA256 hashes for all file operations
- Timestamp precision to microsecond
- Agent identity tracking
- Execution context provenance
- All fields currently in responses MUST remain accessible

**C2: Error Reporting Structure**
- `ok` boolean for success/failure
- `error` field with descriptive messages
- Error format consistent across all three output modes
- Stack traces preserved in structured format

**C3: Reminders System Integration**
- Reminder arrays MUST be included in all responses
- Reminder format preserved for downstream processing
- Context-aware reminders based on project state

**C4: Storage Backend Neutrality**
- Formatting layer MUST NOT depend on SQLite vs PostgreSQL
- Work with abstract storage interface only
- No database-specific output formatting

**C5: MCP Protocol Compliance**
- All tools remain valid MCP tool definitions
- Parameter types compatible with MCP type system
- Response structure parseable by MCP clients

### Assumptions

- Filesystem read/write access for output operations
- Python 3.10+ runtime with typing support
- UTF-8 encoding for all text content
- Terminal width ≥ 80 characters for readable format optimal display

### Risks & Mitigations

**R1: Performance Degradation**
- Risk: String formatting overhead for readable mode
- Mitigation: Lazy formatting (only when format='readable'), optimize string operations, performance benchmarks in CI

**R2: Breaking Existing Consumers**
- Risk: Unknown external dependencies on current response structure
- Mitigation: Default format='structured', comprehensive testing, version documentation

**R3: Format Inconsistency**
- Risk: Different tools implement readable format differently
- Mitigation: Centralized ResponseFormatter, comprehensive format specification, code review checklist

**R4: Metadata Loss**
- Risk: Readable format might accidentally omit critical audit data
- Mitigation: Metadata preservation tests, audit trail validation, explicit metadata section in readable output

**R5: Maintenance Burden**
- Risk: Three formats = 3x maintenance cost
- Mitigation: Shared formatting logic in ResponseFormatter, automated testing for all formats, format specification document
<!-- ID: architecture_overview -->
## 3. Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** Introduce a unified output formatting layer for all Scribe MCP tools that separates audit metadata from readable content, with configurable format options.
- **Tools In Scope (Priority Order):**
  1. `read_file` - File reading with provenance (PRIORITY)
  2. `append_entry` - Log entry creation and confirmation
  3. `read_recent` - Recent log retrieval
  4. `query_entries` - Log search and filtering
  5. `manage_docs` - Document management operations
  6. `list_projects` - Project discovery
  7. `get_project` - Project context
  8. `set_project` - Project initialization
  9. `rotate_log` - Log rotation
  10. `scribe_doctor` - Diagnostics
- **Proposed Output Structure (To Be Refined by Research):**
  ```
  ┌─────────────────────────────────────────┐
  │ METADATA BLOCK (collapsible/optional)   │
  │ - sha256, provenance, timestamps        │
  ├─────────────────────────────────────────┤
  │ CONTENT BLOCK (primary, readable)       │
  │ - Line numbers, actual formatting       │
  │ - Clean, scannable output               │
  └─────────────────────────────────────────┘
  ```
- **Format Options (To Be Validated):**
  - `readable` - Human/agent-friendly (default)
  - `structured` - Full JSON for programmatic use
  - `compact` - Minimal output for quick checks
- **Key Constraints:**
  - Must not break existing API consumers
  - Audit trail must remain complete
  - Performance must not degrade significantly
<!-- ID: detailed_design -->
## 4. Detailed Design
<!-- ID: detailed_design -->

### 4.1 ResponseFormatter Extension Architecture

**Core Design Pattern: Extend Existing Infrastructure**

```python
# utils/response.py extension
class ResponseFormatter:
    """Enhanced with three output formats: readable, structured, compact"""
    
    # NEW: Format mode constants
    FORMAT_READABLE = "readable"  # Agent-friendly with line numbers
    FORMAT_STRUCTURED = "structured"  # Current JSON (default)
    FORMAT_COMPACT = "compact"  # Existing token-optimized mode
    
    # NEW: Readable format methods
    def format_readable_file_content(self, data: Dict[str, Any]) -> str:
        """Format read_file output for agent readability"""
        
    def format_readable_log_entries(self, entries: List[Dict]) -> str:
        """Format log entries with line numbers"""
        
    def format_readable_projects(self, projects: List[Dict]) -> str:
        """Format project list as readable table"""
        
    def format_readable_confirmation(self, data: Dict) -> str:
        """Format operation confirmations (append_entry, etc)"""
```

**Key Design Decisions:**

1. **Extend ResponseFormatter, Not Replace**
   - Add new methods alongside existing format_entry/format_response
   - Preserve all existing methods for backward compatibility
   - No breaking changes to current API

2. **Format Selection Strategy**
   - Tools accept optional `format` parameter (default: "structured")
   - Tools call appropriate formatter method based on format value
   - Return type changes from Dict → str for readable/compact, Dict for structured

3. **Line Numbering Specification**
   - Cat -n style: `  1→Line content`
   - Right-aligned numbers (padding for alignment)
   - Arrow separator (→) for visual scanning
   - Actual line breaks (\n), NOT escaped (\\n)

### 4.2 Tool Integration Pattern

**Standard Tool Signature Extension:**

```python
@app.tool()
async def read_file(
    path: str,
    mode: str = "chunk",
    # ... existing parameters ...
    format: str = "structured"  # NEW: output format control
) -> Union[Dict[str, Any], str]:  # Return type depends on format
    """
    Read file with provenance tracking.
    
    Args:
        format: Output format - "readable" | "structured" | "compact"
    """
    # ... existing logic to gather data ...
    
    # NEW: Format selection
    if format == "readable":
        return default_formatter.format_readable_file_content(response_data)
    elif format == "compact":
        return default_formatter.format_compact_file_content(response_data)
    else:  # structured (default)
        return response_data  # Current behavior
```

**Implementation Order (Priority):**

1. **Phase 1: read_file**
   - Highest priority (worst agent experience)
   - Implement all 6 output modes in readable format
   - Complete test coverage for readable format

2. **Phase 2: append_entry**
   - Log confirmation output
   - Bulk mode readable format
   - Written lines display

3. **Phase 3: read_recent & query_entries**
   - Log entry display with line numbers
   - Pagination in readable format

4. **Phase 4: Remaining tools**
   - list_projects, get_project, set_project
   - manage_docs, rotate_log, doctor
   - generate_doc_templates, delete_project, health_check

### 4.3 Readable Format Specification

**read_file Readable Output:**

```
┌─ File: /home/user/project/auth.py ────────────────────────────────┐
│ Lines 1-50 of 200 | SHA256: abc123... | Modified: 2026-01-02     │
│ Mode: chunk | Chunk 0 | Encoding: utf-8                           │
├───────────────────────────────────────────────────────────────────┤
     1→import os
     2→from typing import Dict, Optional
     3→
     4→def authenticate(user: str, password: str) -> Optional[Dict]:
     5→    """Authenticate user credentials."""
     6→    # Check against database
     7→    return {"user_id": 123, "token": "xyz"}
├───────────────────────────────────────────────────────────────────┤
│ 📊 Audit Trail                                                    │
│ • SHA256: abc123def456...                                         │
│ • Provenance: agent-id-4cad, session-37e2                         │
│ • Read Mode: chunk, Index: [0]                                    │
│ • Execution: 2026-01-02 13:59:41 UTC                              │
│                                                                    │
│ ⚠️  Reminders                                                      │
│ • Project: scribe_tool_output_refinement                          │
│ • Last entry: 5 minutes ago                                       │
└───────────────────────────────────────────────────────────────────┘
```

**append_entry Readable Output:**

```
✅ Log Entry Written Successfully

Entry: [ℹ️] [2026-01-02 13:59:41 UTC] [Agent: ArchitectAgent] 
       Architecture design phase initiated

Details:
• Path: .scribe/docs/dev_plans/scribe_tool_output_refinement/PROGRESS_LOG.md
• Line: 62
• Metadata: phase=architecture_planning, confidence=0.95

───────────────────────────────────────────────────────────────────
📊 Audit: entry-id-674eaf, timestamp-2026-01-02T13:59:41Z
⚠️  Reminders: Project active, 25 entries logged
```

**read_recent Readable Output:**

```
Recent Log Entries (Last 10)
Page 1 of 3 | Total: 25 entries

──────────────────────────────────────────────────────────────────
  1→ [ℹ️] [2026-01-02 13:59:41 UTC] [Agent: ArchitectAgent]
     Architecture design phase initiated | phase=architecture_planning

  2→ [✅] [2026-01-02 13:58:44 UTC] [Agent: ArchitectAgent]  
     Found existing utils/response.py - integration point identified

  3→ [ℹ️] [2026-01-02 13:58:28 UTC] [Agent: ArchitectAgent]
     Analyzed codebase structure - 14 tools identified
──────────────────────────────────────────────────────────────────
📊 Query: 10 results | Filters: none
⚠️  Use page=2 for next 10 entries
```

**list_projects Readable Output:**

```
Scribe Projects (5 total)
Page 1 of 1

┌────────────────────────────────────────────────────────────────┐
│ NAME                            │ STATUS      │ LAST ENTRY     │
├─────────────────────────────────┼─────────────┼────────────────┤
│ scribe_tool_output_refinement   │ in_progress │ 1 min ago      │
│ scribe_sentinel_concurrency_v1  │ complete    │ 2 days ago     │
│ scribe_mcp                      │ in_progress │ 5 hours ago    │
│ auth_system_redesign            │ blocked     │ 1 week ago     │
│ performance_optimization        │ planning    │ 3 days ago     │
└─────────────────────────────────┴─────────────┴────────────────┘

Active: scribe_tool_output_refinement
───────────────────────────────────────────────────────────────────
📊 Showing 5 of 5 | Use filter=<pattern> to narrow results
```

### 4.4 Metadata Handling Strategy

**Separation Principle:**
- Content: Primary data agents need (file content, log entries, project info)
- Metadata: Audit trail, provenance, execution context
- Reminders: Contextual warnings and suggestions

**Visual Hierarchy:**
1. Header: File/operation identification
2. Content Block: Line-numbered primary data
3. Footer: Audit trail (collapsible)
4. Reminders: Contextual alerts

**Metadata Preservation:**
- All current metadata fields remain in structured format
- Readable format selectively displays key metadata
- Full audit trail accessible in footer section

### 4.5 Error Handling in Readable Format

**Error Output Specification:**

```
❌ Error: File Not Found

Details:
• Path: /home/user/nonexistent.py
• Reason: File does not exist in repository
• Suggestion: Check path or use glob pattern to find files

───────────────────────────────────────────────────────────────────
📊 Error Code: FILE_NOT_FOUND | Timestamp: 2026-01-02 14:00:00 UTC
```

**Consistency Across Formats:**
- Structured: `{"ok": false, "error": "File not found", ...}`
- Readable: Formatted error with emoji, details, suggestions
- Compact: `❌ FILE_NOT_FOUND: /path/to/file`

### 4.6 Implementation Interfaces

**ResponseFormatter New Methods:**

```python
# Core formatting methods
def format_readable_file_content(self, data: Dict[str, Any]) -> str:
    """Format read_file response for readability"""
    
def format_readable_log_entries(self, entries: List[Dict], 
                                pagination: Optional[PaginationInfo]) -> str:
    """Format log entries with line numbers and pagination"""
    
def format_readable_projects(self, projects: List[Dict], 
                             active_project: Optional[str]) -> str:
    """Format project list as table"""
    
def format_readable_confirmation(self, operation: str, 
                                 data: Dict[str, Any]) -> str:
    """Format operation confirmation (append_entry, set_project, etc)"""
    
def format_readable_error(self, error: str, context: Dict[str, Any]) -> str:
    """Format error messages with context"""

# Helper methods
def _add_line_numbers(self, content: str, start: int = 1) -> str:
    """Add cat -n style line numbers to content"""
    
def _create_header_box(self, title: str, metadata: Dict) -> str:
    """Create ASCII box header with metadata"""
    
def _create_footer_box(self, audit_data: Dict, reminders: List) -> str:
    """Create ASCII box footer with audit trail"""
    
def _format_table(self, headers: List[str], rows: List[List[str]]) -> str:
    """Create aligned ASCII table"""
```

**Tool Integration Helper:**

```python
# utils/response.py
def finalize_tool_response(data: Dict[str, Any], 
                          format: str = "structured",
                          tool_name: str = "") -> Union[Dict, str]:
    """
    Universal tool response finalizer.
    
    Handles format selection and calls appropriate formatter method.
    Used by all tools for consistent output formatting.
    """
    if format == FORMAT_READABLE:
        # Route to appropriate readable formatter based on tool
        if tool_name == "read_file":
            return default_formatter.format_readable_file_content(data)
        elif tool_name in ["append_entry", "set_project", "rotate_log"]:
            return default_formatter.format_readable_confirmation(tool_name, data)
        elif tool_name in ["read_recent", "query_entries"]:
            return default_formatter.format_readable_log_entries(
                data.get("entries", []), 
                data.get("pagination")
            )
        elif tool_name == "list_projects":
            return default_formatter.format_readable_projects(
                data.get("projects", []),
                data.get("active_project")
            )
        # ... other tools ...
    elif format == FORMAT_COMPACT:
        # Use existing compact formatting
        return default_formatter.format_compact_response(data)
    else:  # structured
        return data
```

### 4.7 Testing Strategy

**Test Coverage Requirements:**

1. **Unit Tests** (`tests/test_response_formatter.py`)
   - Test each format_readable_* method independently
   - Validate line numbering logic
   - Test ASCII box generation
   - Test error formatting

2. **Integration Tests** (`tests/test_tool_formats.py`)
   - Test each tool with format="readable"
   - Verify backward compatibility (format="structured")
   - Test format="compact" integration
   - Validate metadata preservation

3. **Performance Tests** (`tests/test_performance.py`)
   - Benchmark readable format overhead (≤5ms target)
   - Memory usage comparison
   - Large file handling (read_file with 10K lines)

4. **Visual Tests** (`tests/test_output_visual.py`)
   - Generate sample outputs for manual review
   - Validate alignment and box drawing
   - Terminal width compatibility

**Backward Compatibility Validation:**
- All existing tests MUST pass without modification
- Run full test suite with format parameter unspecified
- Verify structured format output unchanged
<!-- ID: directory_structure -->
## 5. Directory Structure
<!-- ID: directory_structure -->

```
scribe_mcp/
├── utils/
│   ├── response.py          # EXTEND: Add readable format methods
│   ├── tokens.py            # EXISTING: Token estimation
│   ├── estimator.py         # EXISTING: Pagination support
│   └── ...
├── tools/
│   ├── read_file.py         # MODIFY: Add format parameter (Phase 1)
│   ├── append_entry.py      # MODIFY: Add format parameter (Phase 2)
│   ├── read_recent.py       # MODIFY: Add format parameter (Phase 3)
│   ├── query_entries.py     # MODIFY: Add format parameter (Phase 3)
│   ├── list_projects.py     # MODIFY: Add format parameter (Phase 4)
│   ├── get_project.py       # MODIFY: Add format parameter (Phase 4)
│   ├── set_project.py       # MODIFY: Add format parameter (Phase 4)
│   ├── manage_docs.py       # MODIFY: Add format parameter (Phase 4)
│   ├── rotate_log.py        # MODIFY: Add format parameter (Phase 4)
│   ├── doctor.py            # MODIFY: Add format parameter (Phase 4)
│   └── ...                  # All remaining tools
├── tests/
│   ├── test_response_formatter.py      # NEW: Unit tests for readable format
│   ├── test_tool_formats.py            # NEW: Integration tests for all tools
│   ├── test_output_visual.py           # NEW: Visual output validation
│   ├── test_performance.py             # EXTEND: Add readable format benchmarks
│   ├── test_read_file_tool.py          # EXISTING: Backward compat validation
│   ├── test_tools.py                   # EXISTING: Must pass unchanged
│   └── ...
└── docs/
    └── dev_plans/
        └── scribe_tool_output_refinement/
            ├── ARCHITECTURE_GUIDE.md   # THIS FILE
            ├── PHASE_PLAN.md           # Implementation roadmap
            ├── CHECKLIST.md            # Verification checklist
            ├── PROGRESS_LOG.md         # Development log
            └── research/
                └── RESEARCH_TOOL_OUTPUT_ANALYSIS_20260102_0853.md

Key Files Modified:
- utils/response.py (PRIMARY): ~300 lines added for readable format methods
- tools/*.py (ALL 14): ~10 lines each for format parameter integration
- tests/test_response_formatter.py (NEW): ~500 lines comprehensive tests
- tests/test_tool_formats.py (NEW): ~300 lines integration tests
- tests/test_output_visual.py (NEW): ~150 lines visual validation

No New Modules Created - All extensions to existing infrastructure
```

**Change Impact Analysis:**

| File | Lines Before | Lines After | Change Type | Risk |
|------|-------------|------------|-------------|------|
| utils/response.py | 242 | ~540 | Extend | Low - additive only |
| tools/read_file.py | 778 | ~810 | Modify | Low - backward compatible |
| tools/append_entry.py | 2000+ | ~2030 | Modify | Low - backward compatible |
| tests/test_response_formatter.py | 0 | ~500 | New | None - new tests |
| tests/test_tool_formats.py | 0 | ~300 | New | None - new tests |

**File Organization Principles:**
- All formatting logic in utils/response.py (single source of truth)
- Tools only handle format parameter routing
- Tests organized by layer (unit, integration, visual, performance)
- No duplicate formatter implementations
- Clear separation: format selection (tools) vs format implementation (utils)
<!-- ID: data_storage -->
## 6. Data & Storage
<!-- ID: data_storage -->

**No Data Storage Changes Required**

The readable format feature is a **presentation layer** enhancement only. No changes to:

- SQLite database schema
- PostgreSQL database schema  
- Storage abstraction interfaces
- Data models or serialization
- Progress log file formats
- Project configuration files

**Storage Layer Interaction:**

```
┌─────────────┐
│ Storage     │ (Unchanged)
│ Backend     ├─────> Dict[str, Any] (raw data)
└─────────────┘           │
                          ↓
                 ┌────────────────┐
                 │ ResponseFormatter │ (Extended)
                 │ - format_structured() │ (existing - returns Dict)
                 │ - format_compact()    │ (existing - returns Dict)
                 │ - format_readable()   │ (NEW - returns str)
                 └────────────────┘
                          │
                          ↓
                 Tool Output (format-dependent type)
```

**Key Principle: Separation of Concerns**
- Storage layer produces raw data dictionaries
- ResponseFormatter transforms data for presentation
- No coupling between storage backend choice and output format
- SQLite and PostgreSQL both produce identical raw data
- Format selection happens at tool boundary, not storage layer

**Data Integrity:**
- All audit fields (sha256, timestamps, provenance) preserved in all formats
- Structured format maintains byte-for-byte compatibility with current output
- Readable format displays subset of metadata but doesn't modify underlying data
- No risk of data loss or corruption from formatting changes

**Migration Requirements:**
- **NONE** - This is a pure presentation layer feature
- No database migrations needed
- No data format conversions needed
- No schema updates required
<!-- ID: testing_strategy -->
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->

### Test Pyramid Structure

```
                    ┌──────────────┐
                    │   Visual     │  (Manual review of sample outputs)
                    │   Tests      │
                    └──────────────┘
                  ┌──────────────────┐
                  │  Performance     │  (Benchmark readable format)
                  │  Tests           │
                  └──────────────────┘
              ┌────────────────────────┐
              │   Integration Tests    │  (All tools with all formats)
              └────────────────────────┘
          ┌──────────────────────────────┐
          │      Unit Tests              │  (ResponseFormatter methods)
          └──────────────────────────────┘
      ┌────────────────────────────────────┐
      │   Backward Compatibility Tests     │  (Existing test suite)
      └────────────────────────────────────┘
```

### 7.1 Unit Tests (`tests/test_response_formatter.py`)

**NEW TEST FILE - Comprehensive coverage of ResponseFormatter extensions**

```python
class TestReadableFormatting:
    """Test readable format methods"""
    
    def test_format_readable_file_content_line_numbers():
        """Verify cat -n style line numbering"""
        
    def test_format_readable_file_content_metadata_separation():
        """Verify metadata in footer, not mixed with content"""
        
    def test_format_readable_log_entries_pagination():
        """Verify pagination info in readable format"""
        
    def test_format_readable_projects_table_alignment():
        """Verify ASCII table alignment"""
        
    def test_format_readable_error_messages():
        """Verify error format with emoji and suggestions"""

class TestASCIIBoxDrawing:
    """Test helper methods for visual formatting"""
    
    def test_add_line_numbers_padding():
        """Verify line number right-alignment"""
        
    def test_create_header_box_width():
        """Verify box width calculations"""
        
    def test_create_footer_box_multiline():
        """Verify multi-section footers"""
        
    def test_format_table_column_alignment():
        """Verify table column width calculations"""

class TestFormatSelection:
    """Test finalize_tool_response routing"""
    
    def test_format_readable_routes_correctly():
        """Verify format=readable routes to correct formatter"""
        
    def test_format_structured_returns_dict():
        """Verify format=structured returns unchanged dict"""
        
    def test_format_compact_uses_existing_logic():
        """Verify format=compact uses existing compact formatter"""
```

**Coverage Target: 100% of new readable format methods**

### 7.2 Integration Tests (`tests/test_tool_formats.py`)

**NEW TEST FILE - Test all tools with all formats**

```python
class TestReadFileFormats:
    """Test read_file with all formats"""
    
    async def test_read_file_readable_chunk_mode():
        """read_file(format='readable', mode='chunk')"""
        
    async def test_read_file_readable_line_range():
        """read_file(format='readable', mode='line_range')"""
        
    async def test_read_file_structured_unchanged():
        """read_file(format='structured') == current behavior"""

class TestAppendEntryFormats:
    """Test append_entry with all formats"""
    
    async def test_append_entry_readable_single():
        """append_entry(format='readable') single entry"""
        
    async def test_append_entry_readable_bulk():
        """append_entry(format='readable', items=[...])"""

class TestLogQueryFormats:
    """Test read_recent and query_entries"""
    
    async def test_read_recent_readable_pagination():
        """read_recent(format='readable', page=1, page_size=10)"""
        
    async def test_query_entries_readable_search_results():
        """query_entries(format='readable', message='bug')"""

class TestProjectManagementFormats:
    """Test list_projects, get_project, set_project"""
    
    async def test_list_projects_readable_table():
        """list_projects(format='readable')"""
        
    async def test_set_project_readable_confirmation():
        """set_project(format='readable', name='test')"""
```

**Coverage Target: Every tool × every format = 42 test cases minimum**

### 7.3 Performance Tests (`tests/test_performance.py` - EXTEND)

**EXTEND EXISTING FILE - Add readable format benchmarks**

```python
class TestReadableFormatPerformance:
    """Performance benchmarks for readable format"""
    
    def test_read_file_readable_overhead():
        """Measure readable format overhead vs structured"""
        # Target: ≤5ms additional overhead
        
    def test_read_file_large_file_memory():
        """Memory usage for 10K line file in readable format"""
        # Target: ≤2x current memory usage
        
    def test_append_entry_bulk_readable_throughput():
        """Throughput for bulk append in readable format"""
        # Target: No degradation vs structured format
        
    def test_read_recent_pagination_performance():
        """Pagination performance in readable format"""
        # Target: Same as structured format
```

**Performance Acceptance Criteria:**
- Readable format overhead: ≤5ms per tool call
- Memory overhead: ≤2x current usage
- No degradation in structured format performance
- All existing performance benchmarks pass

### 7.4 Visual Tests (`tests/test_output_visual.py`)

**NEW TEST FILE - Generate sample outputs for manual review**

```python
def test_generate_visual_samples():
    """Generate sample outputs for all tools in readable format"""
    # Creates samples/ directory with:
    # - read_file_readable_sample.txt
    # - append_entry_readable_sample.txt
    # - read_recent_readable_sample.txt
    # - list_projects_readable_sample.txt
    # For manual visual inspection

def test_ascii_box_alignment():
    """Verify box drawing characters align correctly"""
    
def test_line_number_padding():
    """Verify line numbers align at various line counts"""
    # Test: 1, 10, 100, 1000 lines
    
def test_terminal_width_compatibility():
    """Verify output looks good at 80, 120, 160 char widths"""
```

**Visual Validation Checklist:**
- Line numbers right-aligned
- Box characters form continuous borders
- Tables aligned properly
- Emoji render correctly
- No text wrapping issues

### 7.5 Backward Compatibility Tests

**USE EXISTING TEST SUITE - No modifications required**

```python
# tests/test_read_file_tool.py - EXISTING
# tests/test_tools.py - EXISTING
# tests/test_append_entry.py - EXISTING
# All existing tests MUST pass without modification

# Key validation:
# 1. When format parameter NOT specified → structured format (current behavior)
# 2. All existing assertions pass unchanged
# 3. Response structure matches current implementation exactly
```

**Backward Compatibility Acceptance Criteria:**
- 100% of existing tests pass without modification
- Zero breaking changes to existing API contracts
- Default behavior (no format parameter) identical to current

### 7.6 Test Execution Strategy

**Pre-Commit Checks:**
```bash
# Run unit + integration + backward compat (fast subset)
pytest tests/test_response_formatter.py tests/test_tool_formats.py tests/test_tools.py -v
```

**Full Test Suite:**
```bash
# Run all tests including performance and visual
pytest -v --cov=scribe_mcp/utils/response.py --cov=scribe_mcp/tools/
```

**Performance Benchmarks:**
```bash
# Run performance tests separately (slower)
pytest tests/test_performance.py -v -m performance
```

**Manual Visual Review:**
```bash
# Generate visual samples for inspection
pytest tests/test_output_visual.py::test_generate_visual_samples
# Review files in samples/ directory
```

### 7.7 Continuous Integration

**CI Pipeline Stages:**

1. **Lint & Type Check** (Fast fail)
   ```bash
   flake8 scribe_mcp/utils/response.py scribe_mcp/tools/
   mypy scribe_mcp/utils/response.py
   ```

2. **Unit Tests** (Fast feedback)
   ```bash
   pytest tests/test_response_formatter.py -v
   ```

3. **Integration Tests** (Comprehensive coverage)
   ```bash
   pytest tests/test_tool_formats.py -v
   ```

4. **Backward Compatibility** (Critical validation)
   ```bash
   pytest tests/test_tools.py tests/test_read_file_tool.py -v
   ```

5. **Performance Benchmarks** (Regression detection)
   ```bash
   pytest tests/test_performance.py -v -m performance
   # Compare results against baseline JSON files
   ```

**Merge Criteria:**
- All stages pass ✅
- Code coverage ≥90% for new code
- No performance regressions
- Manual visual review completed and approved
<!-- ID: deployment_operations -->
## 8. Deployment & Operations
<!-- ID: deployment_operations -->

### Deployment Strategy

**Phased Rollout Approach:**

```
Phase 1: read_file only (1 week)
   ↓
Phase 2: append_entry (1 week)
   ↓
Phase 3: read_recent + query_entries (1 week)
   ↓
Phase 4: All remaining tools (2 weeks)
   ↓
Phase 5: Documentation + final review (1 week)
```

**Deployment Process Per Phase:**

1. **Implement** readable format for phase tools
2. **Test** unit + integration + performance
3. **Review** code + visual outputs
4. **Merge** to main branch
5. **Deploy** (automatic via git commit)
6. **Monitor** for issues in production use
7. **Iterate** based on feedback

### Release Management

**Version Strategy:**
- Feature releases as minor versions (v2.2.0, v2.3.0, etc.)
- Each phase = separate minor version bump
- Maintain CHANGELOG.md with format examples

**Backward Compatibility Guarantee:**
- Default behavior (no format parameter) NEVER changes
- Structured format output remains byte-for-byte identical
- Existing integrations unaffected by upgrades

**Rollback Plan:**
- If critical issues discovered, revert merge commit
- Default format=structured ensures system remains functional
- No data migrations to revert (presentation layer only)

### Configuration Management

**No Configuration Changes Required**

The format parameter is:
- Optional (default: "structured")
- Per-tool-call selection
- No persistent configuration
- No environment variables needed

**Future Configuration Opportunities:**
```python
# Potential project-level defaults (future enhancement)
# config/projects/my_project.json
{
  "defaults": {
    "format": "readable"  # Override default to readable for this project
  }
}
```

### Monitoring & Observability

**Metrics to Track:**
- Format parameter usage (readable vs structured vs compact)
- Performance: readable format overhead per tool
- Error rates by format type
- Agent satisfaction (qualitative feedback)

**Logging Strategy:**
- Log format selection in tool execution context
- Track readable format performance in tool timing logs
- Capture format-related errors separately

**Health Checks:**
- Existing health_check tool unaffected
- Add format=readable to health_check for format validation
- Monitor for format-related exceptions

### Maintenance & Ownership

**Code Ownership:**
- `utils/response.py`: Core team (centralized ownership)
- `tools/*.py`: Distributed ownership (each tool owner adds format param)
- Tests: QA team + tool owners

**Documentation Maintenance:**
- Update tool docstrings with format parameter
- Add format examples to CLAUDE.md
- Create FORMAT_SPECIFICATION.md with visual examples
- Update MCP server guide with format best practices

**Deprecation Policy:**
- Structured format: **NEVER** deprecated (default forever)
- Compact format: **NEVER** deprecated (existing feature)
- Readable format: New feature, no deprecation planned

### Operational Considerations

**No Infrastructure Changes:**
- No new services or processes
- No database migrations
- No configuration management changes
- Pure code enhancement

**Performance Impact:**
- Readable format: +5ms max overhead (only when requested)
- Structured format: Zero impact (no change)
- Compact format: Zero impact (existing code)

**Failure Modes:**
- Format parameter validation: Invalid format → default to structured + warning
- Formatting errors: Fall back to structured format + log error
- No cascading failures (format is presentation layer only)

**Support Considerations:**
- Document format parameter in all tool help text
- Provide visual examples in documentation
- Create troubleshooting guide for format-related issues
- Add format examples to error messages
<!-- ID: open_questions -->
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->

| Item | Owner | Status | Decision/Notes |
|------|-------|--------|----------------|
| Should MCP clients auto-detect format preference? | Architect | ⏳ OPEN | Consider agent_kind metadata to auto-select readable for AI agents. Defer to Phase 5. |
| Terminal width detection for box sizing? | Coder | ⏳ OPEN | Default to 80 chars. Consider environment variable override. Defer to implementation. |
| Colorized output support? | Coder | ⏳ OPEN | ANSI color codes for readable format? Research terminal compatibility first. |
| Should reminders be collapsible in readable format? | Architect | ✅ DECIDED | Yes - reminders in footer section, visually separated from content. |
| Performance target validation method? | Coder | ⏳ OPEN | Use existing test_performance.py infrastructure. Add readable format benchmarks. |
| Documentation format examples location? | Docs | ⏳ OPEN | Create FORMAT_SPECIFICATION.md with visual examples. Reference in CLAUDE.md. |
| Should errors include format recommendations? | Architect | ✅ DECIDED | Yes - error messages suggest using format=readable for better readability. |
| Compact format enhancement opportunity? | Architect | ⏳ DEFERRED | Existing compact format sufficient. Focus on readable format first. |

**Resolution Process:**
- Mark ⏳ OPEN items as ✅ DECIDED during implementation
- Document decisions in this table
- Reference relevant code/docs in Decision column
- Review all open questions before Phase 5 completion
<!-- ID: references_appendix -->
## 10. References & Appendix
<!-- ID: references_appendix -->

### Primary References

**Research Documentation:**
- `RESEARCH_TOOL_OUTPUT_ANALYSIS_20260102_0853.md` - Comprehensive research findings
- Research identified 7 key findings with high confidence (0.95)
- 14 tools inventoried, 4 analyzed in depth

**Code References:**
- `utils/response.py` (242 lines) - EXTEND with readable format methods
- `tools/read_file.py` (778 lines) - Priority tool for Phase 1
- `tools/append_entry.py` (85KB) - Phase 2 implementation
- `tools/read_recent.py`, `tools/query_entries.py` - Phase 3
- All remaining tools in `tools/` directory

**Test References:**
- `tests/test_performance.py` - Existing performance baselines
- `tests/test_read_file_tool.py` - Backward compatibility validation
- `tests/test_tools.py` - Existing test suite (must pass unchanged)

**Standards & Baselines:**
- Claude Code Read tool - Gold standard for readable output (cat -n format)
- MCP Protocol - Tool definition compliance
- Scribe MCP v2.1.1 - Current version baseline

### External Resources

**MCP Protocol Documentation:**
- https://github.com/modelcontextprotocol/specification
- Tool response format guidelines
- Type system documentation

**Python Standards:**
- PEP 8 - Style guide
- PEP 484 - Type hints
- Python 3.10+ typing module

### Design Decisions Log

| Decision | Rationale | Alternatives Considered | Outcome |
|----------|-----------|------------------------|----------|
| Extend ResponseFormatter vs new module | COMMANDMENT #0.5 - Infrastructure Primacy | Create new output_formatter.py module | ✅ Extend existing |
| Default format=structured | Backward compatibility requirement | Default to readable | ✅ Structured default |
| Cat -n line numbering style | Match Claude Code Read tool baseline | Python enumerate style (0-indexed) | ✅ Cat -n style |
| ASCII box drawing | Terminal compatibility, no dependencies | Unicode box characters | ✅ ASCII art |
| Three formats (readable/structured/compact) | Cover all use cases | Two formats only | ✅ Three formats |
| Phased rollout (5 phases) | Risk mitigation, incremental value | Big bang deployment | ✅ Phased approach |

### Appendix A: Format Examples

**Example A1: read_file readable format**
```
┌─ File: /home/user/auth.py ────────────────────────────────────────┐
│ Lines 1-10 of 50 | SHA256: abc123... | Modified: 2026-01-02     │
├───────────────────────────────────────────────────────────────────┤
     1→import os
     2→from typing import Dict
     3→
     4→def authenticate(user: str) -> Dict:
     5→    return {"user_id": 123}
├───────────────────────────────────────────────────────────────────┤
│ 📊 Audit: sha256=abc123..., provenance=agent-4cad               │
└───────────────────────────────────────────────────────────────────┘
```

**Example A2: append_entry readable format**
```
✅ Log Entry Written Successfully

Entry: [ℹ️] [2026-01-02 14:00:00 UTC] [Agent: ArchitectAgent]
       Architecture design completed

Details:
• Path: .scribe/docs/dev_plans/project/PROGRESS_LOG.md
• Metadata: phase=architecture, confidence=0.95
───────────────────────────────────────────────────────────────────
📊 Audit: entry-id-abc123, timestamp-2026-01-02T14:00:00Z
```

### Appendix B: Performance Targets

| Metric | Current Baseline | Target with Readable | Acceptance Criteria |
|--------|------------------|---------------------|---------------------|
| read_file (100 lines) | 2ms | ≤7ms | ≤5ms overhead |
| append_entry (single) | 1ms | ≤6ms | ≤5ms overhead |
| read_recent (50 entries) | 5ms | ≤10ms | ≤5ms overhead |
| Memory (10K line file) | 5MB | ≤10MB | ≤2x increase |

### Appendix C: Tool Format Parameter Signature

**Standard Format Parameter:**
```python
format: str = "structured"  # "readable" | "structured" | "compact"
```

**All 14 tools receive this parameter:**
1. read_file
2. append_entry  
3. read_recent
4. query_entries
5. list_projects
6. get_project
7. set_project
8. manage_docs
9. rotate_log
10. doctor
11. generate_doc_templates
12. delete_project
13. health_check
14. vector_search

### Document Metadata

- **Generated via:** generate_doc_templates + manual completion
- **Total Lines:** ~1000 (comprehensive architecture)
- **Sections Completed:** 10/10
- **Confidence Level:** 0.95 (High - research-backed, verified code analysis)
- **Ready for Review:** ✅ Yes
- **Ready for Implementation:** ✅ Yes
---
## SCOPE REFINEMENT: Default Format & Tool Audit Logging
<!-- ID: scope_refinement -->

**Decision Date:** 2026-01-02
**Requested By:** User (Orchestrator session)
**Status:** APPROVED

### Changes from Original Design

| Aspect | Original | Revised |
|--------|----------|---------|
| Default format | `structured` (JSON) | `readable` (string) |
| Backward compat concern | High - default preserves JSON | Low - agents get better UX |
| Audit trail | In response only | **Dual**: response + tool_logs |

### Revised Format Behavior

```python
# NEW DEFAULT: Agents get readable output automatically
result = read_file(path="config.py")  # Returns readable string

# JSON on demand for programmatic use
result = read_file(path="config.py", format="structured")  # Returns Dict

# Compact for low-token contexts
result = read_file(path="config.py", format="compact")  # Returns minimal Dict
```

### Tool Audit Logging (NEW REQUIREMENT)

**Every tool call MUST log structured JSON to `tool_logs`**, regardless of output format:

```python
def finalize_tool_response(data: Dict, format: str, tool_name: str) -> Union[Dict, str]:
    # 1. ALWAYS log structured data to tool_logs (audit trail)
    await append_entry(
        message=f"Tool call: {tool_name}",
        log_type="tool_logs",
        meta={
            "tool": tool_name,
            "format_requested": format,
            "response_data": data,  # Full structured response
            "timestamp": utc_now()
        }
    )
    
    # 2. Return formatted response based on format param
    if format == "readable":
        return format_readable(data, tool_name)
    elif format == "compact":
        return format_compact(data)
    else:  # structured
        return data
```

### Log Configuration Addition

Add to `config/log_config.json`:
```json
{
  "tool_logs": {
    "path_template": "{docs_dir}/TOOL_LOG.jsonl",
    "format": "jsonl",
    "required_meta": ["tool", "format_requested"],
    "rotation_threshold": 1000,
    "description": "Structured JSON audit trail for all tool calls"
  }
}
```

### Benefits of This Approach

1. **Agent UX**: Readable by default - agents see clean output immediately
2. **Complete Audit**: JSON logged regardless of display format
3. **Queryable**: `tool_logs` can be searched/analyzed
4. **Flexible**: Agents can still request JSON when needed
5. **No Data Loss**: Even readable responses have full JSON backing

### Implementation Impact

**Phase 0 additions**:
- Add `tool_logs` log type to config
- `finalize_tool_response()` always logs to tool_logs first
- JSONL format for efficient append/query

**All phases**:
- Change default from `format="structured"` to `format="readable"`
- Ensure tool_logs capture happens before format conversion

---

## 9. Session-Aware Reminder System Architecture
<!-- ID: reminder_system_architecture -->

### 9.1 Problem Statement

**Current State:**
The reminder system uses file-based cooldown tracking (`data/reminder_cooldowns.json`) that persists reminder display history across all agent sessions. Cooldown keys are generated as `{project_root}|{agent_id}|{tool_name}|{reminder_key}` without any session component, causing reminders shown in one context window to be suppressed in completely different contexts when the agent's session resets.

**Critical Gaps:**
1. **No Session Isolation**: Reminders persist globally across all sessions for the same project+agent+tool combination
2. **Singleton Pattern**: Global `_reminder_engine` instance in `reminders.py` shared across all sessions
3. **Missing DB Table**: No `reminder_history` table exists for DB-backed cooldown tracking
4. **No Failure Context**: Tools don't pass operation success/failure status to reminder system
5. **Session Tracking Unused**: Existing `agent_sessions` and `scribe_sessions` tables not leveraged by reminder engine

**Architectural Goals:**
- **Session Isolation**: Cooldowns reset when session_id changes or 10-minute idle threshold crossed
- **DB Integration**: Migrate from file-based to database-backed tracking using new `reminder_history` table
- **Failure Priority**: Surface reminders primarily on tool failures, lower priority on successes
- **Backward Compatible**: Existing reminder definitions and selection logic unchanged

### 9.2 Database Schema Design

**New Table: `reminder_history`**

```sql
CREATE TABLE IF NOT EXISTS reminder_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    reminder_hash TEXT NOT NULL,
    project_root TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    reminder_key TEXT NOT NULL,
    shown_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    operation_status TEXT CHECK (operation_status IN ('success', 'failure', 'neutral')) DEFAULT 'neutral',
    context_metadata TEXT,  -- JSON blob for additional context
    FOREIGN KEY(session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reminder_history_session_hash
    ON reminder_history(session_id, reminder_hash);

CREATE INDEX IF NOT EXISTS idx_reminder_history_shown_at
    ON reminder_history(shown_at);

CREATE INDEX IF NOT EXISTS idx_reminder_history_session_tool
    ON reminder_history(session_id, tool_name);
```

**Schema Rationale:**
- `session_id`: Links to `scribe_sessions.session_id` for automatic cleanup on session delete
- `reminder_hash`: New format includes session_id: `{session_id}|{project_root}|{agent_id}|{tool_name}|{reminder_key}`
- Denormalized fields (`project_root`, `agent_id`, `tool_name`, `reminder_key`): Enable querying without hash parsing
- `operation_status`: Enables failure-triggered reminder priority logic
- `context_metadata`: JSON storage for future enhancements (e.g., reminder fatigue tracking)
- `shown_at`: UTC timestamp for TTL cleanup and cooldown calculations

**Index Strategy:**
- `idx_reminder_history_session_hash`: Primary lookup for "has this reminder been shown in this session?"
- `idx_reminder_history_shown_at`: TTL cleanup queries (delete entries older than N days)
- `idx_reminder_history_session_tool`: Analytics queries (reminder frequency per tool per session)

### 9.3 Session Reset Strategy

**Hybrid Approach: Time-Based + Context-Based**

```python
def should_reset_reminder_cooldowns(current_session_id: str, last_session_id: str,
                                    session_age_minutes: float, idle_minutes: float) -> bool:
    """
    Determine if reminder cooldowns should reset.

    Reset Triggers:
    1. Session ID changed (explicit context reset)
    2. Idle time >= 10 minutes (implicit context boundary)
    3. Session age > 24 hours (long-running session cleanup)

    Args:
        current_session_id: Active session UUID
        last_session_id: Previous session UUID (from reminder engine state)
        session_age_minutes: Time since session_started_at
        idle_minutes: Time since last_active_at

    Returns:
        True if cooldowns should reset, False otherwise
    """
    # Trigger 1: Explicit session change
    if current_session_id != last_session_id:
        return True

    # Trigger 2: Idle boundary crossed (10-minute context window)
    if idle_minutes >= 10.0:
        return True

    # Trigger 3: Long-running session cleanup (prevent unbounded growth)
    if session_age_minutes >= (24 * 60):
        return True

    return False
```

**Session Metadata Integration:**

```python
# In RouterContextManager.get_or_create_session_id()
async def get_session_metadata(session_id: str) -> Dict[str, Any]:
    """Retrieve session age and idle time from scribe_sessions table."""
    session = await storage.get_session_by_id(session_id)
    now = datetime.now(timezone.utc)
    started_at = datetime.fromisoformat(session["started_at"])
    last_active_at = datetime.fromisoformat(session["last_active_at"])

    return {
        "session_age_minutes": (now - started_at).total_seconds() / 60,
        "idle_minutes": (now - last_active_at).total_seconds() / 60,
        "started_at": started_at,
        "last_active_at": last_active_at
    }
```

**Reset Implementation:**
- When `should_reset_reminder_cooldowns()` returns `True`, reminder engine clears in-memory `ReminderHistory` dict
- DB rows remain (for analytics), but cooldown checks filter by current `session_id` only
- Idle time updated via `scribe_sessions.last_active_at` heartbeat (already implemented in execution_context)

### 9.4 Hash Generation Refactoring

**Current Implementation (File-Based):**
```python
# utils/reminder_engine.py:282-287
def _get_reminder_hash(self, reminder_key: str, variables: Dict[str, Any]) -> str:
    project_root = str(variables.get("project_root") or "")
    agent_id = str(variables.get("agent_id") or "")
    tool_name = str(variables.get("tool_name") or "")
    return f"{project_root}|{agent_id}|{tool_name}|{reminder_key}"
```

**New Implementation (DB-Backed with Session):**
```python
def _get_reminder_hash(self, reminder_key: str, variables: Dict[str, Any],
                       session_id: Optional[str] = None) -> str:
    """
    Generate session-aware reminder hash for cooldown tracking.

    Args:
        reminder_key: Unique reminder identifier from reminder definitions
        variables: Context variables (project_root, agent_id, tool_name)
        session_id: Current session UUID (required for DB mode, optional for migration)

    Returns:
        Composite hash string for cooldown deduplication

    Hash Format (DB Mode):
        {session_id}|{project_root}|{agent_id}|{tool_name}|{reminder_key}

    Hash Format (Legacy File Mode - backward compatibility):
        {project_root}|{agent_id}|{tool_name}|{reminder_key}
    """
    project_root = str(variables.get("project_root") or "")
    agent_id = str(variables.get("agent_id") or "")
    tool_name = str(variables.get("tool_name") or "")

    # DB mode: Include session_id for session isolation
    if session_id and self.config.get("use_db_cooldown_tracking", False):
        return f"{session_id}|{project_root}|{agent_id}|{tool_name}|{reminder_key}"

    # Legacy file mode: Maintain backward compatibility
    return f"{project_root}|{agent_id}|{tool_name}|{reminder_key}"
```

**Migration Strategy:**
1. **Phase 1**: Add `session_id` parameter with feature flag `use_db_cooldown_tracking=False` (file mode default)
2. **Phase 2**: Implement DB storage methods, enable flag for testing
3. **Phase 3**: Default to DB mode (`use_db_cooldown_tracking=True`), archive old file
4. **Phase 4**: Remove file-based code after validation period

### 9.5 Storage Layer Integration

**New Methods in `storage/sqlite.py`:**

```python
async def upsert_reminder_shown(
    self,
    session_id: str,
    reminder_hash: str,
    project_root: str,
    agent_id: str,
    tool_name: str,
    reminder_key: str,
    operation_status: str = "neutral",
    context_metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Record a reminder display in the current session.

    Args:
        session_id: Active session UUID
        reminder_hash: Full hash including session_id
        project_root, agent_id, tool_name, reminder_key: Denormalized components
        operation_status: 'success', 'failure', or 'neutral'
        context_metadata: Optional JSON blob for analytics
    """
    async with self.connection() as conn:
        await conn.execute(
            """
            INSERT INTO reminder_history
                (session_id, reminder_hash, project_root, agent_id, tool_name,
                 reminder_key, shown_at, operation_status, context_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, reminder_hash, project_root, agent_id, tool_name,
             reminder_key, datetime.now(timezone.utc).isoformat(),
             operation_status, json.dumps(context_metadata) if context_metadata else None)
        )
        await conn.commit()

async def check_reminder_cooldown(
    self,
    session_id: str,
    reminder_hash: str,
    cooldown_minutes: int
) -> bool:
    """
    Check if reminder is still in cooldown period for this session.

    Args:
        session_id: Active session UUID
        reminder_hash: Full hash to check
        cooldown_minutes: Cooldown duration from reminder config

    Returns:
        True if reminder should be suppressed (still in cooldown), False if can show
    """
    async with self.connection() as conn:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        cursor = await conn.execute(
            """
            SELECT COUNT(*) FROM reminder_history
            WHERE session_id = ?
              AND reminder_hash = ?
              AND shown_at > ?
            """,
            (session_id, reminder_hash, cutoff.isoformat())
        )
        row = await cursor.fetchone()
        return row[0] > 0 if row else False

async def cleanup_reminder_history(self, cutoff_hours: int = 168) -> int:
    """
    Remove old reminder history entries (TTL cleanup).

    Args:
        cutoff_hours: Delete entries older than this (default: 7 days)

    Returns:
        Number of rows deleted
    """
    async with self.connection() as conn:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)
        cursor = await conn.execute(
            "DELETE FROM reminder_history WHERE shown_at < ?",
            (cutoff.isoformat(),)
        )
        await conn.commit()
        return cursor.rowcount
```

**Integration with Execution Context:**

```python
# In shared/execution_context.py
class ExecutionContext:
    def __init__(self, storage_backend: Optional[StorageBackend] = None):
        self._storage_backend = storage_backend
        self.session_id: Optional[str] = None  # Set via get_or_create_session_id()

    async def record_reminder_shown(
        self,
        reminder_hash: str,
        operation_status: str = "neutral",
        **context
    ) -> None:
        """Convenience method to record reminder display in current session."""
        if self.session_id and self._storage_backend:
            await self._storage_backend.upsert_reminder_shown(
                session_id=self.session_id,
                reminder_hash=reminder_hash,
                operation_status=operation_status,
                **context
            )
```

### 9.6 Tool Integration Pattern

**Failure Context Propagation:**

```python
# Example: tools/append_entry.py
async def append_entry(message: str, status: str = "info", ...) -> str:
    """Append log entry with failure-aware reminder generation."""
    operation_status = "neutral"

    try:
        # Main tool logic
        result = await _write_entry_to_log(...)
        operation_status = "success"
        return finalize_tool_response(result, format=format)

    except Exception as e:
        operation_status = "failure"
        logger.error(f"append_entry failed: {e}")
        raise

    finally:
        # Generate reminders with operation context
        if state and state.project_name:
            reminders = get_reminders(
                project=state.project_name,
                tool_name="append_entry",
                state=state,
                operation_status=operation_status  # NEW PARAMETER
            )
            if reminders and format == "readable":
                # Reminders appended to readable output
                pass
```

**Modified `get_reminders()` Signature:**

```python
# In reminders.py
def get_reminders(
    project: str,
    tool_name: str,
    state: Any,
    operation_status: str = "neutral"  # NEW
) -> List[str]:
    """
    Generate reminders with operation status awareness.

    Args:
        project: Project name
        tool_name: Tool identifier
        state: Project state object
        operation_status: 'success', 'failure', or 'neutral'

    Returns:
        List of reminder strings to display

    Behavior:
        - Failure reminders prioritized (always shown if applicable)
        - Success reminders lower priority (respect cooldowns strictly)
        - Neutral reminders (default behavior, backward compatible)
    """
    context = _build_legacy_context(state, tool_name, operation_status)
    engine = _get_engine()

    # Pass session_id from execution context to engine
    session_id = getattr(state, "session_id", None)

    return engine.generate_reminders(
        context=context,
        session_id=session_id,
        operation_status=operation_status
    )
```

**Priority Logic in ReminderEngine:**

```python
class ReminderEngine:
    def generate_reminders(
        self,
        context: ReminderContext,
        session_id: Optional[str] = None,
        operation_status: str = "neutral"
    ) -> List[str]:
        """Generate reminders with failure-triggered priority."""

        # Build candidate list
        candidates = self._select_candidate_reminders(context)

        # Filter by cooldown (session-aware)
        available = []
        for reminder in candidates:
            hash_key = self._get_reminder_hash(
                reminder.key,
                context.variables,
                session_id=session_id
            )

            # Failure-triggered reminders bypass cooldown
            if operation_status == "failure":
                in_cooldown = False  # Always show on failures
            else:
                in_cooldown = await self._check_db_cooldown(
                    session_id, hash_key, reminder.cooldown_minutes
                )

            if not in_cooldown:
                available.append(reminder)

        # Select final set (max 3, prioritize by score)
        return self._format_final_reminders(available[:3])
```

### 9.7 Migration Plan

**Stage 1: Schema Migration (Non-Breaking)**
- Add `reminder_history` table to SQLite schema
- Add indexes for efficient queries
- No behavior changes to reminder system
- **Validation**: `pytest storage/test_sqlite.py::test_reminder_history_schema`

**Stage 2: Storage Methods Implementation**
- Implement `upsert_reminder_shown()`, `check_reminder_cooldown()`, `cleanup_reminder_history()`
- Add feature flag `use_db_cooldown_tracking=False` (disabled by default)
- **Validation**: Unit tests for new storage methods

**Stage 3: Hash Refactoring (Backward Compatible)**
- Update `_get_reminder_hash()` to accept `session_id` parameter
- Maintain file-based behavior when `use_db_cooldown_tracking=False`
- **Validation**: Existing reminder tests pass unchanged

**Stage 4: Session Integration**
- Pass `session_id` from execution context to reminder engine
- Implement session reset logic (`should_reset_reminder_cooldowns()`)
- **Validation**: Session isolation tests (same reminder appears in different sessions)

**Stage 5: Failure Context Propagation**
- Add `operation_status` parameter to all tool reminder calls
- Implement failure-triggered priority logic
- **Validation**: Failure reminders bypass cooldown, success reminders respect cooldown

**Stage 6: DB Mode Activation**
- Set `use_db_cooldown_tracking=True` as default
- Archive `data/reminder_cooldowns.json` to `data/reminder_cooldowns.json.archive`
- Monitor for 48 hours in production
- **Validation**: No regression in reminder delivery, DB queries <5ms

**Stage 7: Cleanup**
- Remove file-based cooldown code after 2-week validation period
- Remove feature flag `use_db_cooldown_tracking`
- Update documentation to reflect DB-only mode

**Rollback Strategy:**
- Stage 6 rollback: Set `use_db_cooldown_tracking=False`, restore archived file
- Stage 7 rollback: Revert commits, redeploy previous version

### 9.8 Performance Considerations

**Query Performance Targets:**
- Cooldown check: <5ms per reminder (indexed lookup on `session_id` + `reminder_hash`)
- Reminder insert: <3ms per display (single row insert)
- TTL cleanup: <100ms for 10k rows (indexed on `shown_at`)

**Optimization Strategies:**
1. **Batch Inserts**: Record multiple reminder displays in single transaction
2. **Connection Pooling**: Reuse DB connections across tool calls (already implemented in `sqlite.py`)
3. **In-Memory Caching**: Session-level cache for "already shown" checks (reduce DB hits)
4. **Periodic Cleanup**: Run `cleanup_reminder_history()` daily via background task

**Memory Impact:**
- `reminder_history` table: ~200 bytes/row
- Expected growth: 50 reminders/session × 10 sessions/day = 500 rows/day = 100KB/day
- TTL cleanup (7 days): Max ~3500 rows = 700KB (negligible)

### 9.9 Testing Strategy

**Unit Tests:**
```python
# tests/test_reminder_db_integration.py

async def test_reminder_session_isolation():
    """Verify same reminder can appear in different sessions."""
    session1 = "session-uuid-1"
    session2 = "session-uuid-2"

    # Show reminder in session 1
    await storage.upsert_reminder_shown(session1, "hash1", ...)

    # Check cooldown in session 1 (should be active)
    assert await storage.check_reminder_cooldown(session1, "hash1", 60) == True

    # Check cooldown in session 2 (should be inactive - different session)
    assert await storage.check_reminder_cooldown(session2, "hash1", 60) == False

async def test_session_reset_on_idle():
    """Verify cooldowns reset after 10-minute idle period."""
    session_id = "session-uuid-1"

    # Simulate reminder shown
    await storage.upsert_reminder_shown(session_id, "hash1", ...)

    # Immediately check (should be in cooldown)
    assert await storage.check_reminder_cooldown(session_id, "hash1", 60) == True

    # Simulate 10-minute idle by backdating shown_at
    # (Test helper to modify shown_at timestamp)
    await _backdate_reminder_shown(session_id, "hash1", minutes=11)

    # Check cooldown after idle period (should be expired)
    assert await storage.check_reminder_cooldown(session_id, "hash1", 10) == False

async def test_failure_priority_bypasses_cooldown():
    """Verify failure-triggered reminders shown despite cooldown."""
    engine = ReminderEngine()
    context = ReminderContext(...)
    session_id = "session-uuid-1"

    # Show reminder once
    reminders = engine.generate_reminders(context, session_id, operation_status="neutral")
    assert len(reminders) > 0

    # Immediately try again with success status (should be suppressed)
    reminders = engine.generate_reminders(context, session_id, operation_status="success")
    assert len(reminders) == 0

    # Try again with failure status (should bypass cooldown)
    reminders = engine.generate_reminders(context, session_id, operation_status="failure")
    assert len(reminders) > 0
```

**Integration Tests:**
```python
# tests/integration/test_reminder_tool_integration.py

async def test_append_entry_failure_shows_reminders():
    """Verify append_entry failure triggers appropriate reminders."""
    # Simulate append_entry failure (invalid project)
    with pytest.raises(Exception):
        await append_entry(message="test", project="nonexistent")

    # Check that reminder was shown in output
    # (Test helper to capture tool output)
    output = get_last_tool_output()
    assert "Remember to set_project" in output  # Example reminder
```

**Performance Tests:**
```python
async def test_cooldown_check_performance():
    """Verify cooldown checks meet <5ms SLA."""
    session_id = "session-uuid-1"

    # Insert 100 reminders
    for i in range(100):
        await storage.upsert_reminder_shown(session_id, f"hash{i}", ...)

    # Measure cooldown check time
    start = time.perf_counter()
    for i in range(100):
        await storage.check_reminder_cooldown(session_id, f"hash{i}", 60)
    elapsed = time.perf_counter() - start

    avg_time_ms = (elapsed / 100) * 1000
    assert avg_time_ms < 5.0, f"Avg cooldown check: {avg_time_ms:.2f}ms (SLA: <5ms)"
```

### 9.10 Risk Assessment

**Technical Risks:**

| Risk | Severity | Mitigation |
|------|----------|------------|
| DB query latency exceeds 5ms | Medium | Comprehensive indexing, connection pooling, in-memory caching layer |
| Session ID not available in legacy code paths | High | Feature flag for gradual rollout, fallback to file mode if session_id=None |
| Reminder history table grows unbounded | Low | Automated TTL cleanup (7 days), ON DELETE CASCADE for session cleanup |
| Migration breaks existing reminder tests | Medium | Backward-compatible hash generation, feature flag allows A/B testing |
| Failure priority logic causes reminder spam | Medium | Cooldown still enforced within session, max 3 reminders per tool call |

**Operational Risks:**

| Risk | Severity | Mitigation |
|------|----------|------------|
| File-based cache corruption during migration | Low | Archive file before migration, feature flag rollback available |
| Session table not populated in all environments | Medium | Execution context auto-creates sessions, graceful degradation to file mode |
| 10-minute idle threshold too aggressive | Low | Configurable via `reminder_config.json`, can tune post-deployment |

### 9.11 Success Criteria

**Functional Requirements:**
- ✅ Reminders reset when `session_id` changes
- ✅ Reminders reset after 10-minute idle period
- ✅ Same reminder can appear in different sessions for same project+agent+tool
- ✅ Failure-triggered reminders bypass cooldown within session
- ✅ Success-triggered reminders respect standard cooldown

**Performance Requirements:**
- ✅ Cooldown check queries: <5ms (p95)
- ✅ Reminder insert operations: <3ms (p95)
- ✅ TTL cleanup: <100ms for 10k rows
- ✅ No memory leaks (stable after 24-hour run)

**Testing Requirements:**
- ✅ All existing reminder tests pass unchanged
- ✅ Session isolation tests verify cross-session behavior
- ✅ Failure priority tests confirm cooldown bypass
- ✅ Performance tests validate query SLAs
- ✅ Integration tests cover all tool integration points

**Documentation Requirements:**
- ✅ Architecture guide updated with schema, session logic, migration plan (this document)
- ✅ Phase plan includes sequential implementation stages
- ✅ Checklist contains all acceptance criteria and validation steps

---

**End of Architecture Guide**