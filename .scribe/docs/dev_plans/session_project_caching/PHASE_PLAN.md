---
id: session_project_caching-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 session_project_caching"
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-21'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — session_project_caching
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-21 02:05:13 UTC

> Execution roadmap for session_project_caching.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Effort | Confidence |
|-------|------|------------------|--------|------------|
| Phase 1 | Add cache infrastructure to RouterContextManager | `_session_projects` dict + 2 methods | 30 min | 0.95 |
| Phase 2 | Wire set_project to populate cache | Cache update call after DB write | 15 min | 0.95 |
| Phase 3 | Add auto-injection at server dispatch | Inject project from cache before tool exec | 20 min | 0.90 |
| Phase 4 | Testing and verification | Unit tests + manual verification | 30 min | 0.90 |

**Total Estimated Time:** 1.5-2 hours

**Execution Order:** Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 (strict sequence, each depends on previous)
<!-- ID: phase_0 -->
**Scope:** Add `_session_projects` dictionary and two async methods to `RouterContextManager` class.

**File to Modify:** `shared/execution_context.py`

**Dependencies:** None (first task)

### Specifications

**Step 1.1: Add `_session_projects` dict to `__init__` (line 59)**

Insert after line 58 (`self._transport_sessions`):
```python
self._session_projects: Dict[str, str] = {}  # session_id -> project_name cache
```

**Step 1.2: Add `cache_project_binding` method (after line 112)**

Insert before `_build_agent_identity` method:
```python
async def cache_project_binding(self, session_id: str, project_name: str) -> None:
    """Cache project binding for this session.
    
    Args:
        session_id: The stable_session_id from ExecutionContext
        project_name: Project name to cache
    """
    if not session_id or not project_name:
        return
    async with self._lock:
        self._session_projects[session_id] = project_name
```

**Step 1.3: Add `get_cached_project` method (after cache_project_binding)**

```python
async def get_cached_project(self, session_id: str) -> Optional[str]:
    """Get cached project for this session.
    
    Args:
        session_id: The stable_session_id from ExecutionContext
        
    Returns:
        Cached project name or None if not cached
    """
    if not session_id:
        return None
    async with self._lock:
        return self._session_projects.get(session_id)
```

### Verification
- [ ] File compiles without syntax errors: `python -c "from shared.execution_context import RouterContextManager"`
- [ ] Dict exists: Check `RouterContextManager().__dict__` contains `_session_projects`
- [ ] Methods exist: `hasattr(RouterContextManager, 'cache_project_binding')` returns True

### Out of Scope
- Do NOT modify server.py (Phase 3)
- Do NOT modify set_project.py (Phase 2)
- Do NOT change ExecutionContext dataclass
<!-- ID: phase_1 -->
**Scope:** Add cache update call to set_project.py after successful DB binding.

**File to Modify:** `tools/set_project.py`

**Dependencies:** Task Package 1 (RouterContextManager methods must exist)

### Specifications

**Step 2.1: Add import at top of file (near other imports)**

Find the imports section and add:
```python
from scribe_mcp.server import router_context_manager
```

**Step 2.2: Add cache update after DB write (line ~514)**

Find this code block (around lines 511-513):
```python
if hasattr(backend, "set_session_project"):
    await backend.set_session_project(session_key, name)
```

Add immediately after (before the debug logging):
```python
# Update in-memory cache for auto-injection
await router_context_manager.cache_project_binding(
    stable_session_id or session_key,
    name
)
```

### Verification
- [ ] File compiles: `python -c "from tools.set_project import set_project"`
- [ ] set_project call succeeds and cache is populated (manual test)

### Out of Scope
- Do NOT modify server.py (Phase 3)
- Do NOT modify execution_context.py (Phase 1 complete)
- Do NOT add tests yet (Phase 4)
<!-- ID: milestone_tracking -->
**Scope:** Add auto-injection logic at server tool dispatch to inject `project` from cache when not provided.

**File to Modify:** `server.py`

**Dependencies:** Task Package 1 and 2 (cache infrastructure and population must exist)

### Specifications

**Step 3.1: Locate injection point (lines 616-618)**

Find this code:
```python
token = router_context_manager.set_current(exec_context)
try:
    result = func(**arguments)
```

**Step 3.2: Add auto-injection between lines 616 and 618**

Replace with:
```python
token = router_context_manager.set_current(exec_context)

# Auto-inject cached project if not explicitly provided
if "project" not in arguments and "project_name" not in arguments:
    cached_project = await router_context_manager.get_cached_project(
        exec_context.stable_session_id
    )
    if cached_project:
        arguments["project"] = cached_project

try:
    result = func(**arguments)
```

### Verification
- [ ] MCP server starts without errors
- [ ] Manual test: call `set_project()` then `append_entry()` without project - verify entry goes to correct project

### Out of Scope
- Do NOT modify execution_context.py (Phase 1 complete)
- Do NOT modify set_project.py (Phase 2 complete)
- Do NOT add tests yet (Phase 4)
<!-- ID: retro_notes -->
**Scope:** Create unit tests and perform manual verification of the complete feature.

**File to Create:** `tests/test_session_project_cache.py`

**Dependencies:** Task Packages 1, 2, 3 (all implementation complete)

### Specifications

**Step 4.1: Create test file with unit tests**

Create `tests/test_session_project_cache.py`:
```python
"""Tests for session project caching feature."""
import pytest
from shared.execution_context import RouterContextManager


@pytest.fixture
def router_manager():
    """Create a fresh RouterContextManager for testing."""
    return RouterContextManager()


@pytest.mark.asyncio
async def test_cache_project_binding_stores_value(router_manager):
    """Test that cache_project_binding stores the value."""
    await router_manager.cache_project_binding("session_123", "my_project")
    result = await router_manager.get_cached_project("session_123")
    assert result == "my_project"


@pytest.mark.asyncio
async def test_cache_project_binding_overwrites_on_update(router_manager):
    """Test that subsequent bindings overwrite previous ones."""
    await router_manager.cache_project_binding("session_123", "project_a")
    await router_manager.cache_project_binding("session_123", "project_b")
    result = await router_manager.get_cached_project("session_123")
    assert result == "project_b"


@pytest.mark.asyncio
async def test_get_cached_project_returns_none_for_unknown(router_manager):
    """Test that unknown session returns None."""
    result = await router_manager.get_cached_project("unknown_session")
    assert result is None


@pytest.mark.asyncio
async def test_cache_project_binding_handles_none_session(router_manager):
    """Test that None session_id doesn't raise."""
    await router_manager.cache_project_binding(None, "project")
    # Should not raise, just return early


@pytest.mark.asyncio
async def test_cache_project_binding_handles_none_project(router_manager):
    """Test that None project_name doesn't raise."""
    await router_manager.cache_project_binding("session", None)
    # Should not raise, just return early
```

**Step 4.2: Run tests**

```bash
cd /home/austin/projects/MCP_SPINE/scribe_mcp
pytest tests/test_session_project_cache.py -v
```

**Step 4.3: Manual verification (optional but recommended)**

1. Start MCP server
2. Call: `set_project(agent="TestAgent", name="cache_test", root=".")`
3. Call: `append_entry(agent="TestAgent", message="Test entry")` - NO project param
4. Check that entry went to `cache_test` project

### Verification
- [ ] All unit tests pass
- [ ] Manual test confirms auto-injection works

### Out of Scope
- Do NOT add integration tests to test_set_project.py (future enhancement)
- Do NOT add observability/metrics (future enhancement)
