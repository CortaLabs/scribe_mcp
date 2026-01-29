---
id: read_file_search_audit-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 read_file_search_audit"
doc_name: architecture
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

# 🏗️ Architecture Guide — read_file_search_audit
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-29 01:54:36 UTC

> Architecture guide for read_file_search_audit.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
**Context:** Agents currently resort to Bash `grep`/`rg`/`sed` commands for multi-file search and file editing because the existing `read_file` tool only supports single-file operations. This creates security risks, requires user approval for shell commands, and violates the MCP tool-first policy.

**Goals:**
- Eliminate Bash grep/rg usage with native MCP `search` tool for multi-file codebase search
- Eliminate Bash sed usage with native MCP `edit_file` tool for safe file editing
- Fix read_file repo root confusion bug
- Maintain same security/sandbox model as read_file
- Provide grep/rg/sed feature parity through Python-native implementation
- Design for extensibility (future vectorization/semantic search)

**Non-Goals:**
- Replace existing read_file tool (it stays for single-file operations)
- Replace native Grep tool (Claude Code's ripgrep tool - different use case)
- Build version control into edit_file (git handles that)
- Add AI-powered code generation to these tools

**Success Metrics:**
- Zero Bash grep/sed commands in agent workflows
- All file searches use `search` tool
- All file edits use `edit_file` tool  
- 100% repo-boundary enforcement (no access outside sandbox)
- Comprehensive test coverage (≥90%)
- Clear error messages and validation
<!-- ID: requirements_constraints -->
**Functional Requirements:**

**search Tool:**
- Multi-file recursive search across repository
- Regex and literal search modes
- File type filtering (py, js, ts, rust, go, md, etc.)
- Glob pattern filtering (e.g., `*.py`, `src/**/*.ts`)
- Context lines (before/after/around matches)
- Output modes: content (matching lines), files_with_matches (paths only), count (match counts)
- Case-insensitive search option
- Multiline search support
- Result limiting (max matches per file, max total matches, max files)
- Line number display

**edit_file Tool:**
- Simple string replacement (old_string → new_string)
- Replace all occurrences or first match only
- **Mandatory read_file enforcement:** Cannot edit file unless read_file was called first in session
- Dry-run mode (preview changes without committing)
- Clear diff/preview output
- Session state tracking for read-before-edit validation

**read_file Bug Fix:**
- Investigate and fix repo root confusion
- Ensure consistent repo root resolution across all file operations

**Non-Functional Requirements:**
- **Security:** Same PathSandbox enforcement as read_file (no access outside repo boundary)
- **Performance:** Handle large repositories efficiently (skip binary files, size limits)
- **Compatibility:** Pure Python, no new dependencies beyond stdlib
- **Consistency:** Follow existing tool patterns from read_file.py exactly
- **Extensibility:** search tool designed with hooks for future vectorization/semantic search backend

**Assumptions:**
- Repository root is discoverable via RepoConfig/RepoDiscovery
- Agents understand tool contracts and use tools correctly
- File system access available with appropriate permissions

**Risks & Mitigations:**
- **Risk:** edit_file used without reading file first → **Mitigation:** Enforce read_file call in session state
- **Risk:** Search overwhelms with too many results → **Mitigation:** Configurable limits (max_matches, max_files)
- **Risk:** Binary file search crashes → **Mitigation:** Skip binary files by default
- **Risk:** Security bypass attempts → **Mitigation:** Reuse proven PathSandbox from read_file
- **Risk:** Future vectorization breaks current tool → **Mitigation:** Design with backend abstraction from day one
<!-- ID: architecture_overview -->
**Solution Summary:** Add two new MCP tools (`search` and `edit_file`) following the exact patterns established by `read_file`. Both tools reuse existing infrastructure (PathSandbox, ResponseFormatter, ExecutionContext) and integrate seamlessly with the MCP server registration system.

**Component Breakdown:**

### 3.1 search Tool (tools/search.py)
- **Purpose:** Multi-file codebase search (grep/rg replacement)
- **Location:** `tools/search.py` (new file, ~800-1000 lines estimated)
- **Interfaces:**
  - Input: MCP tool parameters (pattern, path, glob, type, output_mode, etc.)
  - Output: Formatted search results via ResponseFormatter
- **Dependencies:**
  - `security/sandbox.py` → PathSandbox for repo boundary enforcement
  - `utils/formatters/` → ResponseFormatter for output formatting
  - `shared/execution_context.py` → ExecutionContext for session management
  - `server.py` → @app.tool decorator for MCP registration
- **Key Features:**
  - Recursive directory traversal with file type/glob filtering
  - Regex and literal search modes
  - Three output modes: content, files_with_matches, count
  - Context lines support (before/after/around)
  - **Extension Point:** `SearchBackend` interface for future vectorization

### 3.2 edit_file Tool (tools/edit_file.py)
- **Purpose:** Safe file editing (sed replacement)
- **Location:** `tools/edit_file.py` (new file, ~400-600 lines estimated)
- **Interfaces:**
  - Input: MCP tool parameters (path, old_string, new_string, replace_all, dry_run)
  - Output: Diff preview or confirmation via ResponseFormatter
- **Dependencies:**
  - `security/sandbox.py` → PathSandbox for repo boundary enforcement
  - `utils/formatters/` → ResponseFormatter for diff display
  - `shared/execution_context.py` → ExecutionContext for read-before-edit tracking
  - `server.py` → @app.tool decorator for MCP registration
- **Key Features:**
  - Simple string replacement (exact match only, no regex in MVP)
  - Mandatory dry-run mode (safe by default)
  - **Session state validation:** Rejects edits if file wasn't read first
  - Unified diff output for preview

### 3.3 Shared Infrastructure (Reused from read_file)

**PathSandbox (security/sandbox.py):**
- Already exists, proven, ready to use
- Enforces repo boundary for all file operations
- Validates paths against forbidden patterns
- Used identically by read_file, search, edit_file

**ResponseFormatter (utils/formatters/):**
- Already exists, handles readable/structured/compact formats
- Will be extended with search-specific and edit-specific formatters
- Consistent output across all tools

**ExecutionContext (shared/execution_context.py):**
- Already exists, manages session state
- Will be extended to track read_file calls per session
- Enables read-before-edit enforcement for edit_file

**PermissionChecker (security/sandbox.py):**
- Already exists, validates operation permissions
- Will be extended with 'search' and 'edit' operation types
- Consistent permission model across all tools

### 3.4 Tool Registration (server.py)
- Both tools use `@app.tool()` decorator (same as read_file)
- MCP server automatically exposes them to clients
- Standard async function signature pattern
- Auto-generated schemas from function signatures

**Data Flow:**

**search Tool Flow:**
```
Agent → MCP Request → @app.tool(search) → PathSandbox validation →
Recursive file traversal → Pattern matching → Result aggregation →
ResponseFormatter → MCP Response → Agent
```

**edit_file Tool Flow:**
```
Agent → MCP Request → @app.tool(edit_file) → Session validation (read_file called?) →
PathSandbox validation → File read → String replacement → Diff generation →
Dry-run preview OR File write + backup → ResponseFormatter → MCP Response → Agent
```

**External Integrations:**
- None required (pure Python, existing infrastructure only)
- Future: Potential vectorization backend for semantic search (abstracted via SearchBackend interface)
<!-- ID: detailed_design -->
### 4.1 search Tool Signature

**File:** `tools/search.py`

```python
@app.tool()
async def search(
    # REQUIRED
    agent: str,
    pattern: str,

    # Scope
    path: Optional[str] = None,  # Default: repo root
    glob: Optional[str] = None,  # "*.py", "**/*.ts"
    type: Optional[str] = None,  # py, js, ts, md, rust, go, etc.

    # Output
    output_mode: str = "content",  # content | files_with_matches | count
    format: str = "readable",  # readable | structured | compact

    # Context
    context_lines: int = 0,  # Shorthand for before+after
    before_context: Optional[int] = None,  # Lines before match
    after_context: Optional[int] = None,  # Lines after match

    # Search Behavior
    case_insensitive: bool = False,
    regex: bool = True,  # Default regex, set False for literal
    multiline: bool = False,

    # Limits
    max_matches_per_file: int = 50,
    max_total_matches: int = 200,
    max_files: int = 100,

    # Display
    line_numbers: bool = True,

    # Performance
    skip_binary: bool = True,
    max_file_size_mb: int = 10,

) -> Union[Dict[str, Any], str]:
    """
    Multi-file codebase search with grep/rg feature parity.
    
    Returns formatted search results respecting repo boundaries.
    Future-ready for vectorization backend via SearchBackend abstraction.
    """
```

**Output Structures:**

**Content Mode (default):**
```json
{
  "ok": true,
  "output_mode": "content",
  "pattern": "AuthService",
  "files_searched": 142,
  "files_with_matches": 5,
  "total_matches": 23,
  "matches": [
    {
      "file": "src/auth/service.py",
      "matches": [
        {
          "line_number": 45,
          "line": "class AuthService:",
          "context_before": ["# Authentication service", ""],
          "context_after": ["    def __init__(self):", "        ..."]
        }
      ]
    }
  ]
}
```

**Files-with-matches Mode:**
```json
{
  "ok": true,
  "output_mode": "files_with_matches",
  "files_searched": 142,
  "files_with_matches": 5,
  "files": [
    "src/auth/service.py",
    "src/auth/handlers.py",
    "tests/test_auth.py"
  ]
}
```

**Count Mode:**
```json
{
  "ok": true,
  "output_mode": "count",
  "total_matches": 87,
  "counts": [
    {"file": "src/auth/service.py", "count": 12},
    {"file": "src/db/models.py", "count": 8}
  ]
}
```

### 4.2 edit_file Tool Signature

**File:** `tools/edit_file.py`

```python
@app.tool()
async def edit_file(
    # REQUIRED
    agent: str,
    path: str,  # File to edit (repo-relative or absolute)
    old_string: str,  # Exact string to find
    new_string: str,  # Replacement string

    # Behavior
    replace_all: bool = False,  # Replace all occurrences or just first

    # Safety
    dry_run: bool = True,  # Preview without committing (SAFE BY DEFAULT)

    # Output
    format: str = "readable",  # readable | structured | compact

) -> Union[Dict[str, Any], str]:
    """
    Safe file editing with exact string replacement.
    
    CRITICAL REQUIREMENTS:
    - read_file MUST have been called on this path in the current session
    - dry_run=True by default - must explicitly set False to commit changes
    - Only exact string matching (no regex in MVP)
    
    Returns diff preview in dry_run mode, confirmation in commit mode.
    """
```

**Output Structures:**

**Dry-Run Mode (default, safe):**
```json
{
  "ok": true,
  "path": "src/auth.py",
  "dry_run": true,
  "preview": {
    "old_string": "AuthService",
    "new_string": "AuthenticationService",
    "occurrences_found": 5,
    "occurrences_would_replace": 5,
    "lines_affected": [12, 45, 78, 92, 103],
    "diff": "--- src/auth.py\n+++ src/auth.py\n@@ -12,1 +12,1 @@\n-class AuthService:\n+class AuthenticationService:\n..."
  },
  "warning": "DRY_RUN: No changes written. Set dry_run=False to apply.",
  "next_step": "Review diff, then call again with dry_run=False"
}
```

**Commit Mode (dry_run=False):**
```json
{
  "ok": true,
  "path": "src/auth.py",
  "dry_run": false,
  "applied": {
    "old_string": "AuthService",
    "new_string": "AuthenticationService",
    "occurrences_found": 5,
    "replacements_made": 5,
    "lines_modified": [12, 45, 78, 92, 103],
    "file_size_before": 4582,
    "file_size_after": 4628,
    "backup_path": ".scribe/backups/auth.py.20260128_0230.bak"
  },
  "diff": "...",
  "success": "Changes applied successfully"
}
```

**Error: Read-Before-Edit Violation:**
```json
{
  "ok": false,
  "error": "READ_BEFORE_EDIT_REQUIRED",
  "message": "Cannot edit src/auth.py - file not read in this session",
  "required_action": "Call read_file(path='src/auth.py') before editing",
  "reason": "Safety mechanism prevents blind edits"
}
```

### 4.3 Extension Points (Future Vectorization)

**SearchBackend Interface (not implemented in MVP, architecture only):**

```python
class SearchBackend(ABC):
    """Abstract backend for search operations - enables future vectorization"""
    
    @abstractmethod
    async def search(
        self, 
        pattern: str, 
        files: List[Path], 
        **options
    ) -> List[SearchMatch]:
        """Execute search operation"""
        pass
        
    @abstractmethod
    def supports_semantic_search(self) -> bool:
        """Whether this backend supports semantic/vector search"""
        return False

class DefaultSearchBackend(SearchBackend):
    """Current MVP implementation - regex-based file traversal"""
    # This is what we'll build for MVP
    
class VectorSearchBackend(SearchBackend):
    """Future: Vector-based semantic search"""
    # Placeholder for future enhancement
    # Would integrate with embedding models, vector stores
```

**MVP builds DefaultSearchBackend only. VectorSearchBackend is architectural placeholder.**

### 4.4 Session State Tracking (edit_file enforcement)

**RouterContextManager Extension:**

The `edit_file` tool enforces "read before edit" by tracking which files have been read in the current session. This tracking is implemented in `RouterContextManager`, a module-level singleton that persists across MCP tool calls.

```python
# In shared/execution_context.py - extend RouterContextManager class
class RouterContextManager:
    def __init__(self, storage_backend=None) -> None:
        self._lock = asyncio.Lock()
        self._transport_sessions: Dict[str, str] = {}
        self._session_projects: Dict[str, str] = {}  # Existing pattern to follow
        self._files_read_in_session: Dict[str, Set[str]] = defaultdict(set)  # NEW
        self._process_instance_id = str(uuid.uuid4())
        self._storage_backend = storage_backend

    async def record_file_read(self, session_id: str, file_path: str) -> None:
        """Record that a file was read in this session. Called by read_file."""
        if not session_id or not file_path:
            return
        async with self._lock:
            self._files_read_in_session[session_id].add(file_path)
    
    async def has_file_been_read(self, session_id: str, file_path: str) -> bool:
        """Check if a file was read in this session. Called by edit_file."""
        if not session_id or not file_path:
            return False
        async with self._lock:
            return file_path in self._files_read_in_session.get(session_id, set())
    
    async def cleanup_session(self, session_id: str) -> None:
        """Remove session from all caches. Called by session cleanup task."""
        async with self._lock:
            self._transport_sessions.pop(session_id, None)
            self._session_projects.pop(session_id, None)
            self._files_read_in_session.pop(session_id, None)  # NEW
```

**Integration:**

```python
# In tools/read_file.py
from scribe_mcp.server import router_context_manager, get_execution_context

async def read_file(agent: str, path: str, ...):
    # ... existing logic ...
    
    # Record file read AFTER successful read
    exec_ctx = get_execution_context()
    if exec_ctx and exec_ctx.session_id:
        await router_context_manager.record_file_read(
            exec_ctx.session_id, 
            str(normalized_path)
        )

# In tools/edit_file.py
from scribe_mcp.server import router_context_manager, get_execution_context

async def edit_file(agent: str, path: str, ...):
    exec_ctx = get_execution_context()
    if not exec_ctx or not exec_ctx.session_id:
        raise ValueError("edit_file requires valid session context")
    
    # ENFORCE: Must read before edit
    normalized_path = Path(path).resolve()
    if not await router_context_manager.has_file_been_read(
        exec_ctx.session_id, 
        str(normalized_path)
    ):
        raise ValueError(
            f"Security policy: Must call read_file on '{path}' before editing. "
            f"This ensures you understand the file's current state."
        )
```

**Why RouterContextManager:**
- Module-level singleton in server.py (line 112) - persists across tool calls
- Already manages session state (`_session_projects` cache) - consistent pattern
- Built-in locking with `_lock` - thread-safe access
- Correct lifecycle - lives as long as server process, dies with server
- Session boundary = MCP connection lifetime

**Session Cleanup:**
The existing `_session_cleanup_task` in server.py will be extended to call `router_context_manager.cleanup_session()` for expired sessions, preventing memory leaks.
### 4.5 Security Model (Reuse PathSandbox)
---
## 6. Data & Storage
<!-- ID: data_storage -->

**No Database Changes Required:**
- Session state (`files_read_in_session`) is stored in-memory in `RouterContextManager`
- No new tables, migrations, or schema changes needed
- Ephemeral session data - dies with MCP connection, cleaned up by existing session cleanup task

**Performance Considerations:**
- In-memory tracking = zero disk I/O overhead
- Protected by existing `_lock` in RouterContextManager
- Session cleanup prevents memory leaks


---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->

**Unit Tests (per task package):**
- `test_router_context_manager_file_tracking()` - verify record/check/cleanup methods
- `test_search_tool_basic()` - file traversal and pattern matching
- `test_edit_file_read_enforcement()` - verify read-before-edit policy
- `test_edit_file_dry_run()` - preview without committing

**Integration Tests:**
- `test_search_multiline()` - cross-line pattern matching
- `test_edit_file_with_backup()` - backup creation and restoration
- `test_read_before_edit_workflow()` - full read → edit flow in same session

**Security Tests:**
- `test_sandbox_isolation()` - both tools respect PathSandbox boundaries
- `test_edit_file_blocks_unread()` - verify enforcement of read-before-edit

**Manual QA:**
- Test search across large codebases (performance validation)
- Test edit_file UX with dry_run default (user experience)
- Verify error messages are helpful (read-before-edit violations)


---
## 8. Deployment & Operations
<!-- ID: deployment_operations -->

**Deployment:**
- No migration required - pure code additions
- Tools auto-register via `@app.tool()` decorator
- Server restart picks up new tools immediately

**Rollback Safety:**
- New tools are additions, not modifications
- Existing tools (read_file, append_entry) unchanged
- Can disable new tools without breaking existing functionality

**Monitoring:**
- Session state size can be monitored via `len(router_context_manager._files_read_in_session)`
- Session cleanup logs can be added to track expired sessions
- Tool usage can be tracked via existing MCP request logging


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->

| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should edit_file support batch edits? | Architect | DEFERRED | Single-file focus for MVP, revisit if user demand |
| Vector search integration timeline? | Product | BACKLOG | Placeholder exists, build when semantic search needed |
| Session cleanup timing? | Backend | RESOLVED | Existing task handles it, extend to call cleanup_session() |

All critical questions resolved. Open items are future enhancements, not blockers.


---
## 10. References & Appendix
<!-- ID: references_appendix -->

**Research Documents:**
- `RESEARCH_SESSION_STATE_PERSISTENCE_20260128.md` - Session tracking investigation (Option 2 selected)
- `RESEARCH_SED_TAXONOMY_20260128.md` - Edit operation patterns
- `RESEARCH_READ_FILE_INTEGRATION_20260128.md` - Integration points analysis

**Review Documents:**
- `REVIEW_PRE_IMPLEMENTATION_20260128.md` - Pre-implementation review (89% → requires revision)

**Code References:**
- `shared/execution_context.py` lines 53-221 - RouterContextManager implementation
- `server.py` line 112 - RouterContextManager instantiation
- `tools/read_file.py` line 1693 - Tool registration pattern
- `security/sandbox.py` lines 16-190 - PathSandbox and PermissionChecker

**Related Work:**
- Phase 4 addresses existing read_file repo root detection bug
- Phase 5 covers integration testing and documentation
