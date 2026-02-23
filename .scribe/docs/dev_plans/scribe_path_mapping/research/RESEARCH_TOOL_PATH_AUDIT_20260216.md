# Tool Path Audit: Docker Deployment Path Mapping

## Executive Summary

Audited 11 critical Scribe MCP tools to determine if path mapping in `set_project` is sufficient for Docker deployment where client root paths (e.g., `/home/austin/projects/MCP_SPINE/council_mcp`) differ from server root paths (e.g., `/app`).

**Key Finding:** Path mapping in `set_project` is NEARLY sufficient, but requires architectural adjustment to apply mapping BEFORE validation.

**Risk Assessment:**
- **GREEN (10 tools):** Will work with mapped paths - no independent filesystem validation
- **YELLOW (1 tool):** `set_project` validation walks directory tree - needs mapping adjustment
- **RED (0 tools):** No tools require per-tool path mapping

---

## Research Context

**Problem:** When Scribe runs in Docker (SCRIBE_ROOT=/app), remote clients send paths like `/home/austin/projects/MCP_SPINE/council_mcp` that don't exist on the server filesystem. Path mapping is being added to `set_project` to translate client paths to server paths.

**Question:** Is centralized mapping in `set_project` SUFFICIENT, or do individual tools do their own path resolution/validation that would bypass the mapping?

---

## Foundational Components

### config/paths.py

**Lines:** 1-149

**Path Resolution:**
```python
def repo_root() -> Path:
    override = _env_path("SCRIBE_ROOT")
    if override:
        return override
    # Falls back to package_root() detection
```

**Findings:**
- `repo_root()` uses SCRIBE_ROOT env var as primary source
- No filesystem existence checks in path functions
- Used by `settings.project_root` initialization

**Risk:** GREEN - Static helpers, no validation

---

### shared/execution_context.py

**Lines:** 1-259

**Path Handling:**
```python
@dataclass(frozen=True)
class ExecutionContext:
    repo_root: str  # Stored as string
    # ...

def build_execution_context(self, payload: Dict[str, Any]) -> ExecutionContext:
    repo_root = payload.get("repo_root")
    if not Path(repo_root).is_absolute():
        raise ValueError("ExecutionContext repo_root must be an absolute path")
    # No .exists() check!
```

**Findings:**
- `repo_root` stored as string in ExecutionContext
- Validated as absolute path only - NO filesystem existence check
- Tools receive `exec_context.repo_root` as pre-validated string

**Risk:** GREEN - Validation is format-only, not filesystem-dependent

---

## Tool Audit Results

### 1. read_file.py (GREEN)

**Lines Analyzed:** 1-2553 (focus: 1750-1850, path validation)

**Path Resolution:**
```python
repo_root = Path(exec_context.repo_root).resolve()  # Line 1763
target = Path(path).expanduser()
if not target.is_absolute():
    target = (repo_root / target).resolve()
```

**Filesystem Operations:**
- `target.exists()` - validates TARGET file, not repo_root
- Path traversal checks (symlinks, `.exists()` on target)
- Denylist/allowlist checks via `_enforce_path_policy()`
- Loads sentinel config: `repo_root / ".scribe" / "sentinel" / "sentinel_config.yaml"`

**Key Insight:** Tool uses `exec_context.repo_root` as trusted base path. Never validates repo_root exists. All filesystem checks are on constructed target paths (repo_root + relative_path).

**Risk:** GREEN - Will work with mapped repo_root as long as target files exist under mapped path

---

### 2. edit_file.py (GREEN)

**Lines Analyzed:** 1-399 (focus: 200-280, path resolution)

**Path Resolution:**
```python
repo_root = Path(exec_context.repo_root).resolve()  # Line 209
# Identical security checks to read_file
```

**Filesystem Operations:**
- Same path traversal prevention as `read_file`
- `file_path.exists()` check on target (line 280)
- Creates backups in `repo_root / ".scribe" / "backups"`
- Read-before-edit enforcement via session tracking

**Key Insight:** Mirrors `read_file` pattern - repo_root from context, validates targets not root.

**Risk:** GREEN - Backup directory will be created under mapped repo_root

---

### 3. search.py (GREEN)

**Lines Analyzed:** 1-919 (focus: 630-720, path validation)

**Path Resolution:**
```python
repo_root = Path(exec_context.repo_root)  # Line 636
repo_root = repo_root.resolve()  # Line 648
search_root = repo_root if not path else (repo_root / path).resolve()
```

**Filesystem Operations:**
- `search_root.exists()` check (line 695) - on SEARCH TARGET, not repo_root
- Same symlink/traversal checks as read_file/edit_file
- Fuzzy suggestions if search path doesn't exist

**Key Insight:** Validates search targets, never validates repo_root itself.

**Risk:** GREEN - Works with mapped repo_root

---

### 4. append_entry.py (GREEN)

**Lines Analyzed:** 1-2200 (focus: 500-530, log rotation)

**Path Resolution:**
```python
repo_root = Path(project.get("root") or settings.project_root).resolve()  # Line 504
```

**Filesystem Operations:**
- Gets repo_root from stored `project["root"]` (DB value)
- Passes to `_rotate_if_needed(log_path, repo_root=repo_root)`
- Passes to `append_line(log_path, line, repo_root=repo_root)`
- Loads config: `RepoDiscovery.load_config(repo_root)` for vector indexing check

**Key Insight:** Depends entirely on `project["root"]` from database. If set_project stores mapped path, append_entry uses mapped path.

**Risk:** GREEN - Trusts stored project root

---

### 5. generate_doc_templates.py (GREEN)

**Lines Analyzed:** 1-613 (focus: 140-170, path construction)

**Path Resolution:**
```python
project_root_for_docs = Path(str(logging_context.project["root"])).resolve()  # Line 147
output_dir = _target_directory(project_name, base_dir, project_root=project_root_for_docs)
```

**Filesystem Operations:**
- Gets repo_root from `logging_context.project["root"]`
- Constructs `.scribe/docs/dev_plans/<project>` paths
- Creates directories with `output_dir.mkdir(parents=True, exist_ok=True)` (line 165)

**Key Insight:** Will create doc directory structure under mapped repo_root.

**Risk:** GREEN - Creates directories under stored project root

---

### 6. rotate_log.py (GREEN)

**Lines Analyzed:** 1-2130 (focus: 960-1010, rotation execution)

**Path Resolution:**
```python
repo_root = Path(project.get("root") or settings.project_root).resolve()  # Line 962
archive_path = await rotate_file(log_path, ..., repo_root=repo_root)
archive_info = verify_file_integrity(archive_path, repo_root=repo_root)
```

**Filesystem Operations:**
- Gets repo_root from `project["root"]`
- Creates archives under `repo_root / ".scribe" / "archive"`
- Hash verification and integrity checks on rotated files

**Key Insight:** Archive directory created under mapped repo_root.

**Risk:** GREEN - Works with any valid filesystem path

---

### 7. list_projects.py (GREEN)

**Lines Analyzed:** 1-734 (focus: 250-310, project listing)

**Path Resolution:**
```python
# Displays stored project["root"] as-is
projects_map[record.name] = {
    "root": record.repo_root,  # Line 280 - from DB
    # ...
}
```

**Filesystem Operations:**
- NONE - purely informational display
- Can filter by `Path(root).resolve()` for normalization (line 259)
- No filesystem validation of displayed paths

**Key Insight:** Read-only tool - displays whatever is stored in DB.

**Risk:** GREEN - No filesystem operations

---

### 8. get_project.py (GREEN)

**Lines Analyzed:** 1-663 (focus: progress log validation)

**Path Resolution:**
```python
# Displays stored project data
if progress_log_path and Path(progress_log_path).exists():  # Line 129
    # Checks log file, NOT root
```

**Filesystem Operations:**
- Validates `progress_log` exists (lines 129, 330)
- Does NOT validate `project["root"]` exists
- Reads log file for entry count if it exists

**Key Insight:** Like list_projects - displays stored root, only validates log file.

**Risk:** GREEN - Shows mapped paths as stored

---

### 9. manage_docs.py (GREEN)

**Lines Analyzed:** 1-244 (complete tool)

**Path Resolution:**
```python
# Thin router - delegates to doc_management/ backend
def _resolve_semantic_limits(*, search_meta, repo_root):
    return indexing_shared.resolve_semantic_limits(...)  # Line 56-58
```

**Filesystem Operations:**
- NONE in tool itself - all operations in backend
- Backend uses `logging_context.project` for paths
- Tool just passes repo_root to semantic search limits

**Key Insight:** Router tool - backend uses stored project paths.

**Risk:** GREEN - No direct filesystem access

---

### 10. set_project.py (YELLOW) - CRITICAL

**Lines Analyzed:** 1-961 (focus: 692-710, 842-889, 955-961)

**Path Resolution:**
```python
def _resolve_root(root, context_root, skip_validation):
    root_path = Path(root).expanduser()
    if not root_path.is_absolute():
        root_path = (base / root_path).resolve()
    else:
        root_path = root_path.resolve()  # Line 708
    return root_path
```

**Validation Problem:**
```python
async def _validate_project_paths(*, name, root_path, docs_dir, progress_log):
    # ...
    root_parent = _first_existing_parent(root_resolved)  # Line 868
    if not os.access(root_parent, os.W_OK):
        return {"ok": False, "error": f"Insufficient permissions..."}

def _first_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():  # Line 957 - FILESYSTEM CHECK
        if current.parent == current:
            break
        current = current.parent
    return current  # Returns first existing ancestor
```

**Critical Issue:**
1. `_resolve_root()` accepts client path (e.g., `/home/austin/projects/...`)
2. `_validate_project_paths()` calls `_first_existing_parent()` on resolved path
3. `_first_existing_parent()` walks UP directory tree checking `.exists()`
4. If `/home/austin/projects/...` doesn't exist on server, walks to filesystem root
5. Validates `os.access(/, os.W_OK)` - will fail on Docker container

**Mitigation Options:**

**Option A: Path Mapping BEFORE Validation**
```python
# In set_project tool:
resolved_root = _resolve_root(root, context_root, skip_validation)

# ADD PATH MAPPING HERE (before validation)
if is_docker_environment():
    resolved_root = map_client_path_to_server(resolved_root)

validation = await _validate_project_paths(..., root_path=resolved_root, ...)
```

**Option B: Skip Validation for Docker**
```python
# Client explicitly passes skip_validation=True for Docker
set_project(agent="...", name="...", root="/home/austin/...", skip_validation=True)
```

**Option C: Make Validation Path-Mapping-Aware**
```python
def _first_existing_parent(path: Path, allow_missing_root: bool = False) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            if allow_missing_root:
                return path  # Return original, assume it will be created
            break
        current = current.parent
    return current
```

**Recommendation:** **Option A** (mapping before validation) is cleanest - apply path mapping in `_resolve_root()` or immediately after, before `_validate_project_paths()` runs.

**Risk:** YELLOW - Requires architectural change to apply mapping before validation

---

### 11. server.py / RouterContextManager (GREEN)

**Lines Analyzed:** ExecutionContext building (focus: context propagation)

**Path Handling:**
```python
# RouterContextManager.build_execution_context
repo_root = payload.get("repo_root")  # From caller
if not Path(repo_root).is_absolute():
    raise ValueError("ExecutionContext repo_root must be an absolute path")
# Stores as-is, no filesystem checks
```

**Key Insight:** Context manager validates format only, passes repo_root through to ExecutionContext unchanged.

**Risk:** GREEN - No filesystem validation

---

## Cross-Cutting Patterns

### Pattern 1: "Trust the Context" (10 tools)

Most tools follow this pattern:
1. Get `repo_root` from `exec_context.repo_root` OR `project["root"]`
2. Construct paths: `repo_root / relative_path`
3. Validate TARGET paths (`.exists()`, permissions)
4. NEVER validate repo_root itself

**Examples:** read_file, edit_file, search, append_entry, generate_doc_templates, rotate_log, list_projects, get_project, manage_docs

**Implication:** Centralized path mapping in `set_project` IS sufficient for these tools.

---

### Pattern 2: "Validate Before Trust" (1 tool)

`set_project` validates paths before storing:
1. Accept `root` parameter from client
2. Resolve to absolute path
3. **Walk directory tree to find writable parent** ← PROBLEM
4. Store validated path in database

**Implication:** Path mapping must happen BEFORE validation step.

---

## Recommended Implementation

### Where to Add Path Mapping

**File:** `src/scribe_mcp/tools/set_project.py`

**Location:** After `_resolve_root()`, before `_validate_project_paths()`

**Code Change:**
```python
# Line 284 (current):
resolved_root = _resolve_root(root, context_root, skip_validation)

# ADD PATH MAPPING HERE:
if settings.enable_path_mapping:  # Docker detection
    from scribe_mcp.utils.path_mapper import map_client_to_server
    resolved_root = map_client_to_server(resolved_root, 
                                          mapping=settings.path_mapping_rules)

# Then validate (Line 300):
validation = await _validate_project_paths(
    name=name,
    root_path=resolved_root,  # Now contains MAPPED path
    docs_dir=docs_dir,
    progress_log=resolved_log,
)
```

### Path Mapping Configuration

**Environment Variable:**
```bash
SCRIBE_PATH_MAPPING="/home/austin/projects/MCP_SPINE:/app,/Users/austin/projects:/app"
```

**Mapping Rules:**
- If `resolved_root` starts with `/home/austin/projects/MCP_SPINE` → replace with `/app`
- If `resolved_root` starts with `/Users/austin/projects` → replace with `/app`
- Otherwise → leave unchanged

**Parsing:**
```python
def parse_path_mapping(mapping_str: str) -> List[Tuple[str, str]]:
    rules = []
    for rule in mapping_str.split(","):
        if ":" in rule:
            client_prefix, server_prefix = rule.split(":", 1)
            rules.append((client_prefix.strip(), server_prefix.strip()))
    return rules

def map_client_to_server(client_path: Path, mapping: List[Tuple[str, str]]) -> Path:
    client_str = str(client_path.resolve())
    for client_prefix, server_prefix in mapping:
        if client_str.startswith(client_prefix):
            mapped_str = client_str.replace(client_prefix, server_prefix, 1)
            return Path(mapped_str)
    return client_path  # No mapping rule matched
```

---

## Testing Strategy

### Test Case 1: Unmapped Path (Local Development)

**Input:**
```python
set_project(agent="test", name="my_project", root="/home/austin/projects/my_repo")
```

**Expected:** Path passes through unchanged, validation checks `/home/austin/projects`, works if it exists.

---

### Test Case 2: Mapped Path (Docker)

**Config:** `SCRIBE_PATH_MAPPING="/home/austin/projects:/app"`

**Input:**
```python
set_project(agent="test", name="my_project", root="/home/austin/projects/my_repo")
```

**Expected:**
- Mapping converts to `/app/my_repo`
- Validation checks `/app`, finds it writable
- Stored in DB as `/app/my_repo`
- All subsequent tools use `/app/my_repo`

---

### Test Case 3: Multiple Mapping Rules

**Config:** `SCRIBE_PATH_MAPPING="/home/austin:/app,/Users/austin:/app"`

**Input A:** `/home/austin/projects/repo` → `/app/projects/repo`
**Input B:** `/Users/austin/work/repo` → `/app/work/repo`
**Input C:** `/opt/other/repo` → `/opt/other/repo` (no match)

---

## Confidence Assessment

| Finding | Confidence | Justification |
|---------|------------|---------------|
| 10 tools are GREEN | 95% | Verified by reading source - all trust exec_context/project dict |
| set_project is YELLOW | 95% | Direct code inspection of _first_existing_parent walk |
| Path mapping before validation works | 90% | Logical flow confirmed, but needs integration testing |
| No tools do independent validation | 85% | Audited primary tools, but may be edge cases in secondary tools |
| Mapping in set_project is sufficient | 90% | All tools use stored project["root"], but test coverage needed |

---

## Gaps and Unknowns

1. **Secondary tools not audited:**
   - `query_entries.py` - likely GREEN (uses project dict)
   - `read_recent.py` - likely GREEN (uses project dict)
   - `open_bug.py`, `open_security.py` - likely GREEN (use manage_docs)
   - **Recommendation:** Spot-check these, expect same pattern

2. **Backend modules:**
   - `doc_management/` - uses paths from project dict (indirect verification)
   - `storage/` - stores paths as strings, no validation
   - **Recommendation:** Verify in Phase 2 if issues arise

3. **Edge case: Sentinel mode:**
   - Some operations may use `settings.project_root` directly
   - **Recommendation:** Test sentinel logging in Docker

4. **Path mapping persistence:**
   - Once mapped path is stored, it's permanent until project deleted
   - Changing mapping rules won't affect existing projects
   - **Recommendation:** Document this behavior

---

## Conclusion

**Answer to Research Question:** Path mapping in `set_project` is NEARLY sufficient. The only blocker is `_validate_project_paths()` which must run AFTER mapping, not before.

**Implementation Priority:**

1. **HIGH:** Add path mapping to `set_project` between `_resolve_root()` and `_validate_project_paths()`
2. **MEDIUM:** Add `SCRIBE_PATH_MAPPING` environment variable parsing
3. **MEDIUM:** Integration tests for Docker path mapping
4. **LOW:** Spot-check secondary tools (query_entries, read_recent, etc.)

**Risk Mitigation:**

- **Before deployment:** Integration test in Docker with real client paths
- **Fallback:** `skip_validation=True` parameter works as immediate workaround
- **Monitoring:** Log path mapping operations for debugging

---

## References

- `src/scribe_mcp/config/paths.py` - Static path helpers
- `src/scribe_mcp/shared/execution_context.py` - Context propagation
- `src/scribe_mcp/tools/set_project.py` - Lines 692-710, 842-961 (validation)
- `src/scribe_mcp/tools/read_file.py` - Lines 1750-1850 (typical pattern)
- Docker path mapping context: Issue #<TBD> (containerization)

---

*Research conducted: 2026-02-16*
*Confidence: 90% - Code inspection complete, integration testing recommended*
