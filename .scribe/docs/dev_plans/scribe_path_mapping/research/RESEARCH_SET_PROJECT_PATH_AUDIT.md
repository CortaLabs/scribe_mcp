# Research: set_project.py Path Resolution Audit

**Research Goal:** Analyze how `set_project.py` handles repository root paths and identify the exact failure point when remote SSE clients (e.g., Council) send paths that don't exist on the Scribe server's filesystem (Docker container scenario).

**Confidence Score:** 1.0 (all findings verified against actual code)

---

## Executive Summary

### Problem Statement
When Scribe runs in Docker (SCRIBE_ROOT=/app) and a remote client like Council calls `set_project(root="/home/austin/projects/MCP_SPINE/council_mcp")`, the server attempts to validate this path against its own filesystem. Since the path doesn't exist in the container, validation fails.

### Key Finding
**The fix point is `_resolve_root()` at line 692 in `set_project.py`.** After path resolution (line 708), we need to:
1. Check if the resolved path exists on the server filesystem
2. If not AND `SCRIBE_ROOT` environment variable is set (Docker indicator)
3. Map the non-existent client path → `SCRIBE_ROOT` for server filesystem operations
4. Store the original client path in `docs_json` metadata for reference

### Impact Analysis
- **Scope:** All downstream tools (append_entry, manage_docs, read_file, etc.) retrieve `repo_root` from stored project state, NOT from per-request ExecutionContext
- **Implication:** Fixing `set_project` to store the mapped root will automatically fix ALL tools
- **No schema changes required:** Use existing `docs_json` field to store client's original path

---

## Problem Analysis

### Scenario: Remote SSE Client → Docker Server

**Client Side (Council):**
- Running on host machine with repo at `/home/austin/projects/MCP_SPINE/council_mcp`
- Calls Scribe MCP via SSE transport: `set_project(root="/home/austin/projects/MCP_SPINE/council_mcp")`

**Server Side (Scribe in Docker):**
- Running in container with SCRIBE_ROOT=/app
- Receives client's path `/home/austin/projects/MCP_SPINE/council_mcp`
- Path doesn't exist in container's filesystem (no `/home/austin/` directory)
- Validation fails → project creation blocked

### Why This Happens

Scribe was designed for:
1. **Local dev mode:** Server and client share the same filesystem
2. **Stdio transport:** Client spawns server as subprocess, same machine

SSE transport + Docker breaks this assumption:
- Client and server have **different filesystems**
- Client's path references **don't exist** on server
- Server **validates paths against its own filesystem**

---

## Code Flow Analysis

### 1. Path Entry Point: MCP Request Metadata

**File:** `src/scribe_mcp/shared/tool_runtime.py`  
**Function:** `_extract_request_repo_root()` (line 31)

```python
def _extract_request_repo_root(app: Any) -> Optional[str]:
    # Extracts repo_root from MCP request context metadata
    # Keys checked: "repo_root", "workspace_root", "cwd"
    ...
```

**Flow:**
```
SSE Client → MCP Request → request_context.meta["repo_root"] → _extract_request_repo_root()
```

### 2. ExecutionContext Construction

**File:** `src/scribe_mcp/shared/execution_context.py`  
**Function:** `RouterContextManager.build_execution_context()` (line 196)

```python
async def build_execution_context(self, payload: Dict[str, Any]) -> ExecutionContext:
    repo_root = payload.get("repo_root")  # Line 197
    
    if not repo_root or not isinstance(repo_root, str):
        raise ValueError("ExecutionContext missing required field: repo_root")
    if not Path(repo_root).is_absolute():
        raise ValueError("ExecutionContext repo_root must be an absolute path")
    # ⚠️ CRITICAL: Validates absoluteness but NOT existence
    ...
```

**Key Observation:** ExecutionContext accepts any absolute path without checking if it exists on the server's filesystem.

### 3. set_project Path Resolution

**File:** `src/scribe_mcp/tools/set_project.py`  
**Function:** `_resolve_root()` (line 692)

```python
def _resolve_root(root: Optional[str], context_root: Optional[Path], skip_validation: bool) -> Path:
    base = settings.project_root.resolve()
    if not root:
        if context_root and context_root != base:
            return context_root  # Uses ExecutionContext.repo_root if available
        if settings.require_explicit_root and not skip_validation:
            raise ValueError("Explicit project root required...")
        return base
    
    root_path = Path(root).expanduser()
    if not root_path.is_absolute():
        root_path = (base / root_path).resolve()  # Relative → absolute
    else:
        root_path = root_path.resolve()  # Clean up absolute path
    
    return root_path  # ← RETURNS PATH OBJECT (may not exist on filesystem)
```

**Flow in set_project:**
```python
# Line 282
context_root = _get_context_repo_root()  # Gets ExecutionContext.repo_root if available

# Line 284
resolved_root = _resolve_root(root, context_root, skip_validation)

# Line 300 - VALIDATION HAPPENS AFTER RESOLUTION
validation = await _validate_project_paths(
    name=name,
    root_path=resolved_root,  # Uses resolved path from _resolve_root
    docs_dir=docs_dir,
    progress_log=resolved_log,
)
```

### 4. Path Validation (The Failure Point)

**File:** `src/scribe_mcp/tools/set_project.py`  
**Function:** `_validate_project_paths()` (line 842)

```python
async def _validate_project_paths(
    *,
    name: str,
    root_path: Path,
    docs_dir: Path,
    progress_log: Path,
) -> Dict[str, Any]:
    ...
    # Line 868 - PERMISSION CHECK
    root_parent = _first_existing_parent(root_resolved)
    if not os.access(root_parent, os.W_OK):
        return {
            "ok": False,
            "error": f"Insufficient permissions to write under '{root_parent}'.",
        }
    ...
```

**Helper Function:** `_first_existing_parent()` (line 955)

```python
def _first_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():  # ← Walks UP directory tree
        if current.parent == current:  # Reached filesystem root (/)
            break
        current = current.parent
    return current  # Returns first existing parent OR filesystem root
```

**Failure Scenario with Docker:**

1. Client sends: `/home/austin/projects/MCP_SPINE/council_mcp`
2. Server (Docker) checks: `Path("/home/austin/...").exists()` → **False**
3. `_first_existing_parent()` walks up:
   - `/home/austin/projects/MCP_SPINE/council_mcp` → doesn't exist
   - `/home/austin/projects/MCP_SPINE` → doesn't exist
   - `/home/austin/projects` → doesn't exist
   - `/home/austin` → doesn't exist
   - `/home` → doesn't exist
   - `/` → **exists** (filesystem root)
4. `os.access("/", os.W_OK)` → **False** (root not writable in Docker)
5. Validation returns: `{"ok": False, "error": "Insufficient permissions to write under '/'"}`

**This is the exact failure point.**

### 5. Database Storage

**File:** `src/scribe_mcp/tools/set_project.py`  
**Storage:** Line 382

```python
project_record = await backend.upsert_project(
    name=name,
    repo_root=str(resolved_root),  # ← Stores whatever _resolve_root returned
    progress_log_path=str(resolved_log),
    docs_json=_json.dumps(docs),  # ← Can store metadata here
    bridge_id=bridge_id,
    bridge_managed=bridge_managed,
)
```

**Database Schema:** `src/scribe_mcp/storage/models.py`

```python
@dataclass
class ProjectRecord:
    id: int
    name: str
    repo_root: str  # ← Stored root path (string)
    progress_log_path: str
    docs_json: Optional[str] = None  # ← JSON metadata (can store client_root here)
    ...
```

### 6. Downstream Tool Usage

**File:** `src/scribe_mcp/tools/append_entry.py`  
**Pattern:** Line 504

```python
repo_root = Path(project.get("root") or settings.project_root).resolve()
```

**Critical Finding:**
- Downstream tools retrieve `repo_root` from **stored project state** (database)
- They do NOT use `ExecutionContext.repo_root` directly
- **Implication:** Fixing the stored root in `set_project` fixes ALL downstream tools automatically

**Verified in:**
- `append_entry.py` (line 504)
- `manage_docs.py` (similar pattern)
- `read_file.py` (similar pattern)

---

## Failure Point Summary

| Component | Location | Issue |
|-----------|----------|-------|
| **Entry Point** | `tool_runtime.py:31` | Extracts client path from request metadata (no validation) |
| **ExecutionContext** | `execution_context.py:197` | Accepts any absolute path (validates absoluteness, not existence) |
| **Path Resolution** | `set_project.py:692` | Returns Path object without checking filesystem existence |
| **Validation** | `set_project.py:868` | **FAILS HERE** - permission check on non-existent path's parent (/) |
| **Storage** | `set_project.py:382` | Would store resolved path IF validation passed |

**The fix must happen AFTER path resolution (line 708) but BEFORE validation (line 300).**

---

## Proposed Solution: Server-Side Path Mapping

### Design Principles

1. **Non-invasive:** No changes to ExecutionContext, MCP protocol, or client code
2. **Backward compatible:** Local dev mode (path exists) → no mapping, works as before
3. **Explicit opt-in:** Only activates when SCRIBE_ROOT environment variable is set (Docker indicator)
4. **Preserves client context:** Store original client path for reference/debugging

### Solution Architecture

**Mapping Logic in `_resolve_root()`:**

```python
def _resolve_root(root: Optional[str], context_root: Optional[Path], skip_validation: bool) -> Path:
    base = settings.project_root.resolve()
    if not root:
        if context_root and context_root != base:
            return context_root
        if settings.require_explicit_root and not skip_validation:
            raise ValueError("Explicit project root required...")
        return base
    
    root_path = Path(root).expanduser()
    if not root_path.is_absolute():
        root_path = (base / root_path).resolve()
    else:
        root_path = root_path.resolve()
    
    # ===== NEW: SERVER-SIDE PATH MAPPING =====
    scribe_root = os.environ.get("SCRIBE_ROOT")
    if scribe_root and not root_path.exists():
        # Docker mode: client path doesn't exist on server
        # Map to SCRIBE_ROOT for filesystem operations
        mapped_root = Path(scribe_root).resolve()
        logger.info(
            "Path mapping: Client path %s does not exist on server. "
            "Mapping to SCRIBE_ROOT: %s",
            root_path, mapped_root
        )
        # Return tuple: (mapped_path, original_client_path)
        # OR: Set a context variable to carry original path
        # OR: Return mapped path and handle metadata in set_project
        return mapped_root
    # ==========================================
    
    return root_path
```

**Metadata Storage in `set_project()`:**

```python
# After calling _resolve_root (line 284)
original_client_root = root  # Preserve user-provided root
resolved_root = _resolve_root(root, context_root, skip_validation)

# ... validation, document creation ...

# Before database storage (line 316)
docs = {
    "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
    "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
    "checklist": str(docs_dir / "CHECKLIST.md"),
    "progress_log": str(resolved_log),
}

# ===== NEW: STORE CLIENT PATH METADATA =====
if os.environ.get("SCRIBE_ROOT") and original_client_root:
    if not Path(original_client_root).exists():
        docs["_metadata"] = {
            "client_root": original_client_root,
            "mapped": True,
            "server_root": str(resolved_root)
        }
# ============================================

# Database storage (line 382)
project_record = await backend.upsert_project(
    name=name,
    repo_root=str(resolved_root),  # ← Mapped server path
    progress_log_path=str(resolved_log),
    docs_json=_json.dumps(docs),  # ← Contains client_root metadata
    ...
)
```

### Detailed Implementation Steps

**Step 1: Modify `_resolve_root()` (line 692)**

```python
def _resolve_root(
    root: Optional[str], 
    context_root: Optional[Path], 
    skip_validation: bool
) -> tuple[Path, Optional[str]]:  # ← Return tuple: (resolved_path, client_path)
    """Resolve repository root with server-side path mapping for Docker.
    
    Returns:
        Tuple of (resolved_path, original_client_path)
        - resolved_path: Server-side filesystem path (may be mapped)
        - original_client_path: Client's original path (None if no mapping)
    """
    base = settings.project_root.resolve()
    original_client_path = None  # Track if we mapped
    
    if not root:
        if context_root and context_root != base:
            return context_root, None
        if settings.require_explicit_root and not skip_validation:
            raise ValueError("Explicit project root required...")
        return base, None
    
    root_path = Path(root).expanduser()
    if not root_path.is_absolute():
        root_path = (base / root_path).resolve()
    else:
        root_path = root_path.resolve()
    
    # Server-side path mapping for Docker/SSE remote clients
    scribe_root = os.environ.get("SCRIBE_ROOT")
    if scribe_root and not root_path.exists():
        # Path doesn't exist on server AND we're in Docker
        original_client_path = str(root_path)  # Save for metadata
        mapped_root = Path(scribe_root).resolve()
        
        logger.info(
            "Server-side path mapping activated: client path '%s' does not exist "
            "on server filesystem. Mapped to SCRIBE_ROOT: '%s'",
            original_client_path,
            mapped_root,
        )
        
        return mapped_root, original_client_path
    
    return root_path, None  # No mapping needed
```

**Step 2: Update `set_project()` call site (line 284)**

```python
# OLD:
resolved_root = _resolve_root(root, context_root, skip_validation)

# NEW:
resolved_root, client_root = _resolve_root(root, context_root, skip_validation)
```

**Step 3: Store client path metadata (before line 316)**

```python
docs = {
    "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
    "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
    "checklist": str(docs_dir / "CHECKLIST.md"),
    "progress_log": str(resolved_log),
}

# Store client path metadata if mapping occurred
if client_root:
    docs["_metadata"] = {
        "client_root": client_root,
        "server_root": str(resolved_root),
        "mapped": True,
        "scribe_root": os.environ.get("SCRIBE_ROOT"),
    }
```

**Step 4: Update tests**

```python
# tests/test_set_project_path_mapping.py

import os
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_path_mapping_with_scribe_root(tmp_path, monkeypatch):
    """Test server-side path mapping when SCRIBE_ROOT is set."""
    # Setup
    scribe_root = tmp_path / "app"
    scribe_root.mkdir()
    
    monkeypatch.setenv("SCRIBE_ROOT", str(scribe_root))
    
    # Client sends path that doesn't exist on server
    client_path = "/home/austin/projects/MCP_SPINE/council_mcp"
    
    result = await set_project(
        agent="TestAgent",
        name="test_project",
        root=client_path,
    )
    
    # Verify
    assert result["ok"] is True
    project = result["project"]
    
    # Server uses mapped root
    assert project["root"] == str(scribe_root)
    
    # Client root preserved in metadata
    assert "_metadata" in project["docs"]
    assert project["docs"]["_metadata"]["client_root"] == client_path
    assert project["docs"]["_metadata"]["mapped"] is True

@pytest.mark.asyncio
async def test_no_mapping_when_path_exists(tmp_path):
    """Test no mapping occurs when client path exists on server."""
    # Client path exists on server (local dev mode)
    existing_path = tmp_path / "existing_repo"
    existing_path.mkdir()
    
    result = await set_project(
        agent="TestAgent",
        name="test_project",
        root=str(existing_path),
    )
    
    # Verify
    assert result["ok"] is True
    project = result["project"]
    
    # No mapping - uses original path
    assert project["root"] == str(existing_path)
    
    # No metadata added
    assert "_metadata" not in project.get("docs", {})
```

---

## Edge Cases & Considerations

### 1. Multiple Clients with Different Paths

**Scenario:** Two clients (Council, Research) both connect to same Scribe server with different local paths:
- Council: `/home/austin/projects/MCP_SPINE/council_mcp`
- Research: `/home/user/workspace/research_mcp`

**Solution:** Both get mapped to same SCRIBE_ROOT (`/app`). Projects are distinguished by `name` parameter, not `root` path. Each project stores its client's original path in metadata for reference.

### 2. Nested Projects

**Scenario:** Client has nested repos:
- Parent: `/home/austin/projects/MCP_SPINE`
- Child: `/home/austin/projects/MCP_SPINE/council_mcp`

**Solution:** Each project maps independently to SCRIBE_ROOT. Server doesn't preserve filesystem hierarchy relationships (they don't exist on server anyway). Client path metadata preserves the relationship for reference.

### 3. SCRIBE_ROOT Not Set (Local Dev)

**Behavior:** Mapping logic is skipped. Paths are validated against actual filesystem as before. Fully backward compatible.

### 4. Path Exists on Server (Even with SCRIBE_ROOT Set)

**Behavior:** No mapping occurs. Uses existing path. This allows mixing local and remote projects on same server (e.g., server's own projects + remote client projects).

### 5. Client Path is Relative

**Behavior:** `_resolve_root()` converts relative → absolute using `settings.project_root` as base (line 706). Then mapping check applies to the resolved absolute path.

---

## Implementation Guide for Architect/Coder

### Files to Modify

1. **`src/scribe_mcp/tools/set_project.py`**
   - Modify `_resolve_root()` (line 692): Add mapping logic, return tuple
   - Update call site (line 284): Destructure tuple
   - Add metadata storage (before line 316): Store client_root in docs["_metadata"]

2. **`tests/test_set_project_path_mapping.py`** (new file)
   - Test mapping with SCRIBE_ROOT set + non-existent path
   - Test no mapping with SCRIBE_ROOT set + existing path
   - Test no mapping without SCRIBE_ROOT (backward compat)
   - Test metadata storage

### No Changes Required

- **ExecutionContext:** Already accepts any absolute path
- **MCP Protocol:** No protocol changes
- **Client Code:** Clients continue sending their local paths
- **Database Schema:** Use existing `docs_json` field
- **Downstream Tools:** Already use stored `project["root"]`

### Testing Strategy

**Unit Tests:**
- `_resolve_root()` mapping logic
- Metadata storage in `set_project()`

**Integration Tests:**
- End-to-end: set_project → append_entry (verify root propagation)
- Docker simulation: Mock `SCRIBE_ROOT`, assert mapping

**Manual Testing:**
- Deploy to Docker, set `SCRIBE_ROOT=/app`
- Connect Council via SSE
- Call `set_project(root="/home/austin/projects/MCP_SPINE/council_mcp")`
- Verify project creation succeeds
- Verify `append_entry` writes to `/app/.scribe/...`

---

## References

### Key Code Locations

| Component | File | Line | Description |
|-----------|------|------|-------------|
| Request extraction | `shared/tool_runtime.py` | 31 | `_extract_request_repo_root()` |
| Context construction | `shared/execution_context.py` | 196 | `build_execution_context()` |
| Path resolution | `tools/set_project.py` | 692 | `_resolve_root()` - **FIX HERE** |
| Path validation | `tools/set_project.py` | 842 | `_validate_project_paths()` |
| Permission check | `tools/set_project.py` | 868 | `os.access()` - failure point |
| Parent traversal | `tools/set_project.py` | 955 | `_first_existing_parent()` |
| Database storage | `tools/set_project.py` | 382 | `backend.upsert_project()` |
| Downstream usage | `tools/append_entry.py` | 504 | `project.get("root")` pattern |
| SCRIBE_ROOT usage | `config/paths.py` | 60 | Existing env var infrastructure |

### Related Issues

- **Original Problem:** Remote SSE clients sending non-existent paths
- **Root Cause:** Server validates paths against its own filesystem
- **Solution Domain:** Server-side path mapping with SCRIBE_ROOT

---

## Conclusion

The path mapping solution is:
- **Minimal:** Single function change + metadata storage
- **Safe:** Backward compatible, explicit opt-in via SCRIBE_ROOT
- **Complete:** Fixes all downstream tools automatically
- **Verifiable:** Clear testing strategy with Docker simulation

Ready for Architect to design the implementation details and Coder to execute.
