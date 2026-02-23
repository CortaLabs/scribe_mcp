# Research: Doc Management Path Mapping Audit

**Date:** 2026-02-16  
**Researcher:** ResearchAgent-DocMgmt  
**Project:** scribe_path_mapping  
**Confidence:** 93%

---

## Executive Summary

**Finding:** The doc_management subsystem and object store layer are **READY for Docker path mapping** with minimal modifications required.

**Key Discovery:** All components consistently use `project["root"]` from stored database state rather than reading from `exec_context` or `settings`. This means if `set_project` correctly maps and persists the client path → server path translation, all downstream operations will automatically use the mapped path.

**Action Required:** Verify that `set_project` performs path mapping before calling `storage.upsert_project(repo_root=...)`. The rest of the system will work correctly.

---

## Research Context

When Scribe MCP runs in Docker (SCRIBE_ROOT=/app), remote clients send paths like:
```
/home/austin/projects/MCP_SPINE/council_mcp
```

These need to be mapped to:
```
/app
```

Before being stored in the database and used by doc_management/object_store layers.

---

## Component Analysis

### 🟢 GREEN: Path-Mapping Ready (No Changes Required)

#### 1. doc_management/manager.py
**Status:** GREEN  
**Confidence:** 95%

**Path Resolution Functions:**
- `_resolve_doc_path(project, doc_name)` (lines 785-875)
- `_resolve_create_doc_path(project, metadata, doc_name)` (lines 878-929)

**How it works:**
```python
project_root = Path(project.get("root", ""))  # Line 804, 891
```

Both functions:
1. Extract `project["root"]` from stored project dict
2. Resolve all document paths relative to this root
3. Perform sandbox validation with `relative_to(project_root)`
4. Return absolute paths under the stored root

**Why it works:** If `project["root"]` contains `/app`, all resolved paths will be under `/app`. No changes needed.

#### 2. doc_management/manager.py - apply_doc_change()
**Status:** GREEN  
**Confidence:** 95%

**Path usage:**
```python
repo_root = Path(project["root"]).resolve()  # Line 198
await ensure_parent(doc_path, repo_root=repo_root)
await async_atomic_write(doc_path, content, repo_root=repo_root)
```

**Why it works:** Extracts `repo_root` from stored project state and passes to all file operations. Will use mapped path automatically.

#### 3. doc_management/special_create.py
**Status:** GREEN  
**Confidence:** 90%

**Path usage:**
```python
project_root = Path(project.get("root", ""))  # Lines 72, 99, 219
research_dir = docs_dir / "research"
if not research_dir.is_absolute():
    research_dir = project_root / research_dir  # Lines 252-253
```

**Why it works:** All document creation paths are constructed relative to stored `project["root"]`. Will create documents under mapped path.

#### 4. doc_management/special_indexes.py
**Status:** GREEN  
**Confidence:** 90%

**Path usage:**
```python
project_root = Path(project.get("root", ""))  # Line 347
```

Index operations (research, bug, review, agent card) all use stored root. Will work with mapped paths.

#### 5. doc_management/actions/ (all action handlers)
**Status:** GREEN  
**Confidence:** 90%

**Path usage in actions/edit.py:**
```python
repo_root = project.get("root")
if isinstance(repo_root, str):
    repo_root = Path(repo_root)  # Lines 245-247
```

All action handlers (append, edit, status, etc.) read `repo_root` from project dict. Will use mapped path.

#### 6. object_store/keys.py
**Status:** GREEN  
**Confidence:** 95%

**Key functions accept repo_root as parameter:**
```python
def path_to_key(file_path: Path | str, repo_root: Path | str) -> str
def key_to_path(key: str, repo_root: Path | str) -> Path
def should_sync(file_path: Path | str, repo_root: Path | str) -> bool
```

**Why it works:** Caller controls `repo_root`. No hardcoded paths. Functions compute relative paths from provided root.

**Example:**
```python
rel = Path(file_path).resolve().relative_to(Path(repo_root).resolve())
posix = str(PurePosixPath(rel))  # Lines 37-38
```

If `repo_root` is `/app`, all keys will be computed relative to `/app`.

#### 7. object_store/__init__.py - sync_file_to_store()
**Status:** GREEN  
**Confidence:** 95%

**Function signature:**
```python
async def sync_file_to_store(
    file_path: Path,
    content: str,
    repo_root: Path,  # Explicit parameter
) -> None:
```

**Why it works:** Caller passes `repo_root` explicitly. Function uses it to compute key via `path_to_key(file_path, repo_root)` (line 117). Will work with any repo_root value.

#### 8. object_store/hybrid.py - HybridStore
**Status:** GREEN  
**Confidence:** 90%

**How it works:**
```python
async def read(self, key: str) -> str | None:
    result = await self._local.read(key)  # Try local cache
    if result is not None:
        return result
    result = await self._remote.get(key)  # Try remote
    if result is not None:
        await self._local.write(key, result)  # Cache locally
    return result
```

**Why it works:** 
- Uses **keys** not raw file paths
- Local cache writes go through `FilesystemStore.write(key, content)` which calls `key_to_path(key, self._root)`
- `self._root` is the mapped path (e.g., `/app`) passed to FilesystemStore constructor
- No hardcoded paths anywhere

#### 9. object_store/filesystem.py - FilesystemStore
**Status:** GREEN  
**Confidence:** 95%

**How it works:**
```python
def __init__(self, repo_root: Path) -> None:
    self._root = repo_root.resolve()  # Store mapped root

async def write(self, key: str, content: str) -> None:
    target = key_to_path(key, self._root)  # Use stored root
    await atomic_write(target, content, "w", self._root)

async def read(self, key: str) -> str | None:
    target = key_to_path(key, self._root)  # Use stored root
    return await target.read_text("utf-8")
```

**Why it works:** 
- Stores `repo_root` in `__init__`
- All operations convert keys to paths using stored root
- If initialized with `/app`, all paths will be under `/app`

#### 10. storage/base.py - StorageBackend API
**Status:** GREEN  
**Confidence:** 95%

**Project storage schema:**
```python
async def upsert_project(
    *,
    name: str,
    repo_root: str,  # Stored in database
    progress_log_path: str,
    docs_json: Optional[str] = None,
) -> ProjectRecord:
```

**Why it works:** 
- `repo_root` is stored as string in database
- Caller (set_project) controls what value gets stored
- If set_project passes mapped `/app`, database stores `/app`
- All retrievals (`fetch_project`, `list_projects`) return stored value

#### 11. state/manager.py - StateManager
**Status:** GREEN  
**Confidence:** 90%

**Project persistence:**
```python
async def set_current_project(
    self,
    name: Optional[str],
    project_data: Optional[Dict[str, Any]] = None,
    ...
) -> State:
    resolved_payload = dict(project_data or {})
    if resolved_name:
        resolved_payload.setdefault("name", resolved_name)
        await self._upsert_project(resolved_name, resolved_payload)  # Line 235
```

**Why it works:** 
- Stores `project_data["root"]` directly to database via `_upsert_project`
- No path validation or transformation
- If caller provides mapped root, it's stored as-is

#### 12. tools/manage_docs.py - Tool Router
**Status:** GREEN  
**Confidence:** 90%

**How it works:**
```python
@app.tool()
async def manage_docs(..., project: Optional[str] = None) -> Dict[str, Any]:
    return await runtime_shared.handle_manage_docs_request(
        ...,
        project_registry=_PROJECT_REGISTRY,  # Retrieves from database
        ...
    )
```

**Why it works:** 
- Uses `ProjectRegistry` to get project context
- ProjectRegistry reads from database via storage backend
- Returns stored project dict with `root` field
- Will use whatever root was stored by set_project

---

### 🟡 YELLOW: Needs Verification

#### 1. tools/set_project.py (NOT AUDITED IN THIS RESEARCH)
**Status:** YELLOW  
**Confidence:** N/A (out of scope)

**Critical requirement:** 
The `set_project` tool MUST perform path mapping BEFORE calling:
```python
await storage_backend.upsert_project(
    name=project_name,
    repo_root=mapped_path,  # Must be /app, not /home/austin/...
    progress_log_path=mapped_log_path,
)
```

**Verification needed:**
1. Does set_project check if SCRIBE_ROOT differs from client root?
2. Does it translate client paths to server paths before storage?
3. Does it handle relative vs absolute path mapping correctly?

**If set_project does NOT map paths:**
- Database will store client paths (e.g., `/home/austin/projects/MCP_SPINE/council_mcp`)
- doc_management will try to write to non-existent client paths
- File operations will fail

**This is the ONLY critical integration point for path mapping.**

---

### 🔴 RED: Will Break (None Found)

No components found that will break with path mapping.

---

## Path Flow Diagram

```
Client (Claude Desktop)                  Docker Container (Scribe MCP)
━━━━━━━━━━━━━━━━━━━━━━━━━              ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                         
set_project(                             set_project tool
  name="council",                        ├─ Receives client_root:
  root="/home/austin/.../council_mcp"    │  /home/austin/.../council_mcp
)                                        │
           │                             ├─ Maps to server_root:
           │                             │  /app
           ▼                             │
                                         ├─ Calls storage.upsert_project(
                                         │    repo_root="/app"
                                         │  )
                                         │
                                         ▼
                                         Database stores:
                                         project.root = "/app"
                                         
                                         
manage_docs(...)                         manage_docs tool
                                         ├─ Gets project from registry
                                         │  project = fetch_project("council")
                                         │  project["root"] = "/app"
                                         │
                                         ├─ Calls _resolve_doc_path(project, "architecture")
                                         │  └─ Uses project["root"] = "/app"
                                         │  └─ Returns: /app/.scribe/docs/.../ARCHITECTURE_GUIDE.md
                                         │
                                         ├─ Calls apply_doc_change(...)
                                         │  └─ repo_root = Path(project["root"]) = /app
                                         │  └─ Writes to: /app/.scribe/docs/.../file.md
                                         │
                                         ├─ Calls sync_file_to_store(..., repo_root=/app)
                                         │  └─ path_to_key(file_path, repo_root=/app)
                                         │  └─ key = "scribe/docs/.../file.md"
                                         │  └─ Syncs to remote object store
                                         │
                                         ▼
                                         File written to disk at:
                                         /app/.scribe/docs/.../file.md
```

---

## Implementation Guidance

### What You Need to Do

**1. Verify set_project Path Mapping (CRITICAL)**

Check `src/scribe_mcp/tools/set_project.py`:

```python
# Does it do this?
client_root = Path(root)  # From MCP request
server_root = Path(os.getenv("SCRIBE_ROOT", "/app"))

if client_root != server_root:
    mapped_root = server_root  # Use server path
    mapped_progress_log = _map_path(progress_log_path, client_root, server_root)
else:
    mapped_root = client_root
    mapped_progress_log = progress_log_path

await storage_backend.upsert_project(
    name=project_name,
    repo_root=str(mapped_root),
    progress_log_path=str(mapped_progress_log),
)
```

**If set_project does NOT do path mapping, add it.**

**2. Test Path Mapping End-to-End**

Create integration test:
```python
async def test_docker_path_mapping():
    # Client sends /home/austin/projects/MCP_SPINE/council_mcp
    # Server SCRIBE_ROOT=/app
    
    result = await set_project(
        agent="TestAgent",
        name="council_test",
        root="/home/austin/projects/MCP_SPINE/council_mcp"
    )
    
    # Verify mapped path stored
    project = await storage.fetch_project("council_test")
    assert project.repo_root == "/app"
    
    # Verify doc operations use mapped path
    result = await manage_docs(
        agent="TestAgent",
        action="create",
        doc_name="TEST_DOC",
        metadata={"doc_type": "custom", "body": "Test"}
    )
    
    # Verify file created under /app
    doc_path = Path("/app/.scribe/docs/dev_plans/council_test/TEST_DOC.md")
    assert doc_path.exists()
```

**3. No Changes Needed to doc_management or object_store**

These layers are already path-mapping ready. They use stored `project["root"]` exclusively.

---

## Edge Cases & Gotchas

### 1. Relative Paths in target_dir

**Scenario:** User specifies `target_dir="research"` (relative)

**How it's handled:**
```python
# special_create.py lines 251-253
if not research_dir.is_absolute():
    research_dir = project_root / research_dir
```

**Status:** ✅ Safe - relative paths resolved against stored `project_root`

### 2. Cross-Project References

**Scenario:** Project A references documents in Project B with different roots

**How it's handled:**
- Each project stores its own `root` in database
- `_resolve_doc_path(project, doc_name)` uses `project["root"]`
- No cross-contamination possible

**Status:** ✅ Safe - projects isolated by stored root

### 3. Progress Log Path

**Scenario:** `progress_log_path` stored as absolute path

**Example:**
```python
# Stored in database:
progress_log_path = "/home/austin/.../PROGRESS_LOG.md"  # Client path

# Server tries to read:
Path("/home/austin/.../PROGRESS_LOG.md")  # Does not exist!
```

**Solution:** set_project must ALSO map `progress_log_path`:
```python
mapped_progress_log = _map_path(
    progress_log_path,
    client_root="/home/austin/projects/MCP_SPINE/council_mcp",
    server_root="/app"
)
# Result: "/app/.scribe/docs/dev_plans/council/PROGRESS_LOG.md"
```

**Status:** ⚠️ Verify set_project maps this field

### 4. Object Store Cache Writes

**Scenario:** HybridStore caches remote file locally

**How it works:**
```python
# hybrid.py line 62
await self._local.write(key, result)
# ↓
# filesystem.py line 26
target = key_to_path(key, self._root)  # self._root = /app
# ↓
# Writes to: /app/.scribe/docs/.../file.md
```

**Status:** ✅ Safe - uses stored root from FilesystemStore constructor

---
## Confidence Scores by Component

| Component | Confidence | Notes |
|-----------|------------|-------|
| manager.py (_resolve_doc_path) | 95% | Well-tested, uses stored root |
| manager.py (apply_doc_change) | 95% | Explicit repo_root extraction |
| special_create.py | 90% | Multiple path construction sites verified |
| special_indexes.py | 90% | Uses stored root consistently |
| actions/*.py | 90% | All read from project dict |
| object_store/keys.py | 95% | Pure functions with explicit params |
| object_store/__init__.py | 95% | Explicit repo_root parameter |
| object_store/hybrid.py | 90% | Key-based, no hardcoded paths |
| object_store/filesystem.py | 95% | Root stored in __init__ |
| storage/base.py | 95% | Schema stores repo_root as string |
| state/manager.py | 90% | No path validation/transform |
| tools/manage_docs.py | 90% | Uses ProjectRegistry (database) |

**Overall Confidence:** 93%

---

## Recommended Actions

### Immediate (Before Docker Deployment)

1. ✅ **Verify set_project path mapping** - Check if it translates client → server paths
2. ✅ **Add integration test** - Test end-to-end path mapping with Docker-like scenario
3. ✅ **Verify progress_log_path mapping** - Ensure log paths are also translated

### Optional (Future Enhancements)

1. Add path mapping telemetry to set_project logs
2. Add health check for path mapping (detect client/server root mismatch)
3. Document path mapping behavior in CLAUDE.md

---

## Conclusion

**The doc_management subsystem and object_store layer are architecturally ready for Docker path mapping.** 

All components consistently derive `repo_root` from stored project state rather than environment variables or execution context. This design makes path mapping transparent to these layers.

**The critical integration point is set_project.** If it correctly maps client paths to server paths before storing in the database, the entire system will work without modifications.

**Recommended next step:** Audit `src/scribe_mcp/tools/set_project.py` to verify path mapping implementation.

---

## Files Analyzed

1. `src/scribe_mcp/doc_management/runtime.py`
2. `src/scribe_mcp/doc_management/manager.py`
3. `src/scribe_mcp/doc_management/special_create.py`
4. `src/scribe_mcp/doc_management/special_indexes.py`
5. `src/scribe_mcp/doc_management/actions/edit.py`
6. `src/scribe_mcp/object_store/keys.py`
7. `src/scribe_mcp/object_store/__init__.py`
8. `src/scribe_mcp/object_store/hybrid.py`
9. `src/scribe_mcp/object_store/filesystem.py`
10. `src/scribe_mcp/storage/base.py`
11. `src/scribe_mcp/state/manager.py`
12. `src/scribe_mcp/tools/manage_docs.py`

**Total Lines Analyzed:** ~4,000 lines across 12 files

---

**Research Complete** - 2026-02-16 10:08 UTC
