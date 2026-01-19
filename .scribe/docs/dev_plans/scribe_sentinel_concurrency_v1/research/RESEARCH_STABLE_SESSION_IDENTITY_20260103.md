# Research: Stable Session Identity for Multi-Agent Isolation

**Author:** Orchestrator + Human Review
**Date:** 2026-01-03
**Status:** APPROVED FOR IMPLEMENTATION
**Confidence:** 95%

---

## Executive Summary

The current session identity system uses `id(session)` (Python memory addresses) which changes every request, causing:
- `set_project` writes to session A
- `get_project` reads from session B
- Cross-agent contamination in swarm scenarios

**Solution:** Build a server-managed stable session identity system using:
- Canonicalized `repo_root` (realpath)
- Run-scoped keys (`execution_id` or `sentinel_day`)
- Agent identity (`agent_key` or fallback to `display_name`)
- Database-backed session registry with upsert

---

## Root Cause Analysis

### The Bug (server.py:179)
```python
session = getattr(request_context, "session", None)
if session is not None:
    return f"session:{id(session)}"  # ← Memory address - UNSTABLE
```

### Why It Fails
1. Memory addresses change on every request
2. Server restarts create new addresses
3. No persistence across tool calls
4. Concurrent agents get same/different sessions randomly

---

## Corrected Design

### Identity Key Construction

**Pre-hash identity material:**
```
{repo_root_realpath}:{mode}:{scope_key}:{agent_key}
```

| Component | Source | Purpose |
|-----------|--------|---------|
| `repo_root_realpath` | `os.path.realpath(exec_context.repo_root)` | Canonicalized path (handles symlinks) |
| `mode` | `exec_context.mode` | "project" or "sentinel" |
| `scope_key` | `execution_id` (project) or `sentinel_day` (sentinel) | Run isolation |
| `agent_key` | `agent_identity.id` → `display_name` → `"default"` | Agent isolation |

**Hash:** Full SHA-256 (64 hex chars, no truncation)

### Identity Derivation Priority

```python
def derive_session_identity(exec_context, arguments):
    # 1. Canonicalize repo_root
    repo_root = os.path.realpath(exec_context.repo_root)

    # 2. Get mode and scope_key
    mode = exec_context.mode  # "project" or "sentinel"
    if mode == "sentinel":
        scope_key = exec_context.sentinel_day  # e.g., "2026-01-03"
    else:
        scope_key = exec_context.execution_id  # UUID

    # 3. Get agent_key (prefer stable ID, fallback to display_name)
    agent_key = None
    if exec_context.agent_identity:
        agent_key = (
            getattr(exec_context.agent_identity, 'id', None) or
            getattr(exec_context.agent_identity, 'instance_id', None) or
            exec_context.agent_identity.display_name
        )
    if not agent_key:
        agent_key = arguments.get("agent") or "default"

    # 4. Construct identity string
    identity = f"{repo_root}:{mode}:{scope_key}:{agent_key}"

    # 5. Hash it
    identity_hash = hashlib.sha256(identity.encode()).hexdigest()

    return identity_hash, {
        "repo_root": repo_root,
        "mode": mode,
        "scope_key": scope_key,
        "agent_key": agent_key,
    }
```

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    identity_key TEXT UNIQUE NOT NULL,
    agent_name TEXT NOT NULL,           -- Display name (metadata)
    agent_key TEXT NOT NULL,            -- Actual identity component
    repo_root TEXT NOT NULL,            -- Canonicalized path
    mode TEXT NOT NULL,                 -- 'project' or 'sentinel'
    scope_key TEXT NOT NULL,            -- execution_id or sentinel_day
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP                -- For TTL cleanup
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_identity ON agent_sessions(identity_key);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_last_active ON agent_sessions(last_active_at);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_expires ON agent_sessions(expires_at);
```

### Upsert Logic (Race-Safe)

```python
async def get_or_create_agent_session(
    identity_key: str,
    agent_name: str,
    agent_key: str,
    repo_root: str,
    mode: str,
    scope_key: str,
    ttl_hours: int = 24
) -> str:
    """Get existing session or create new one. Race-safe via upsert."""

    new_session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    # Upsert: INSERT OR IGNORE, then UPDATE last_active, then SELECT
    await db.execute("""
        INSERT OR IGNORE INTO agent_sessions
        (session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key, expires_at))

    # Update activity timestamp
    await db.execute("""
        UPDATE agent_sessions
        SET last_active_at = CURRENT_TIMESTAMP,
            expires_at = ?
        WHERE identity_key = ?
    """, (expires_at, identity_key))

    # Get the actual session_id (might be pre-existing)
    row = await db.fetchone(
        "SELECT session_id FROM agent_sessions WHERE identity_key = ?",
        (identity_key,)
    )

    return row['session_id']
```

### Cleanup Function

```python
async def cleanup_expired_sessions(batch_size: int = 100) -> int:
    """Remove expired sessions. Call periodically."""
    result = await db.execute("""
        DELETE FROM agent_sessions
        WHERE expires_at < CURRENT_TIMESTAMP
        LIMIT ?
    """, (batch_size,))
    return result.rowcount
```

---

## Integration Points

### 1. Replace `_derive_transport_session_id()` in server.py

```python
async def _derive_transport_session_id() -> str | None:
    exec_context = router_context_manager.get_current()

    if not exec_context:
        # No context - try headers/meta fallback
        # ... existing header checks ...
        return None

    # Derive stable identity
    identity_hash, identity_parts = derive_session_identity(exec_context, arguments)

    # Get or create session from DB
    session_id = await get_or_create_agent_session(
        identity_key=identity_hash,
        agent_name=identity_parts["agent_key"],  # For display
        agent_key=identity_parts["agent_key"],
        repo_root=identity_parts["repo_root"],
        mode=identity_parts["mode"],
        scope_key=identity_parts["scope_key"],
    )

    return session_id
```

### 2. Backwards Compatibility

If no agent identity available:
- Still scope by `repo_root + mode + scope_key`
- Use `agent_key = "default"`
- This prevents eternal repo-only sessions

---

## Isolation Truth Table

| Scenario | Identity Components | Session |
|----------|---------------------|---------|
| CoderA in /repo1, run X | `/repo1:project:X:CoderA` | Session A |
| CoderB in /repo1, run X | `/repo1:project:X:CoderB` | Session B ✓ |
| CoderA in /repo1, run Y | `/repo1:project:Y:CoderA` | Session C ✓ |
| CoderA in /repo2, run X | `/repo2:project:X:CoderA` | Session D ✓ |
| CoderA via symlink to /repo1 | `/repo1:project:X:CoderA` | Session A (same!) ✓ |
| No agent, run X | `/repo1:project:X:default` | Session E |
| Sentinel mode, day D | `/repo1:sentinel:D:CoderA` | Session F |

---

## Required Tests (Gate for Ship)

### Test A: Parallel Bind Isolation
```python
async def test_parallel_agent_isolation():
    """Two agents in same repo, same execution - different sessions."""
    async def agent_work(agent_name: str):
        await set_project(name="test_project", agent=agent_name)
        await append_entry(message=f"Hello from {agent_name}", agent=agent_name)
        result = await get_project(agent=agent_name)
        return result

    # Fire concurrently
    result_a, result_b = await asyncio.gather(
        agent_work("CoderA"),
        agent_work("CoderB")
    )

    # Assert different sessions
    assert result_a["session_id"] != result_b["session_id"]

    # Assert each sees only their own entries
    entries_a = await read_recent(agent="CoderA")
    entries_b = await read_recent(agent="CoderB")
    assert all("CoderA" in e["message"] for e in entries_a["entries"])
    assert all("CoderB" in e["message"] for e in entries_b["entries"])
```

### Test B: Cross-Run Isolation
```python
async def test_cross_run_isolation():
    """Same agent, different execution_id - different sessions."""
    # Run 1
    with mock_execution_id("run-1"):
        await set_project(name="project", agent="Coder")
        session_1 = await get_session_id()

    # Run 2
    with mock_execution_id("run-2"):
        await set_project(name="project", agent="Coder")
        session_2 = await get_session_id()

    assert session_1 != session_2
```

### Test C: Repo Canonicalization
```python
async def test_symlink_canonicalization(tmp_path):
    """Symlink and real path resolve to same session."""
    real_dir = tmp_path / "real_repo"
    real_dir.mkdir()
    symlink = tmp_path / "symlink_repo"
    symlink.symlink_to(real_dir)

    # Access via real path
    with mock_repo_root(str(real_dir)):
        await set_project(name="project", agent="Coder")
        session_real = await get_session_id()

    # Access via symlink
    with mock_repo_root(str(symlink)):
        session_sym = await get_session_id()

    assert session_real == session_sym
```

### Test D: Missing Agent Fallback
```python
async def test_missing_agent_still_scoped():
    """No agent provided - still scoped by execution, not eternal."""
    with mock_execution_id("run-1"):
        await set_project(name="project")  # No agent
        session_1 = await get_session_id()

    with mock_execution_id("run-2"):
        await set_project(name="project")  # No agent
        session_2 = await get_session_id()

    # Different runs = different sessions (not eternal repo session)
    assert session_1 != session_2
```

---

## Implementation Checklist

- [ ] Add `agent_sessions` table to SQLite schema
- [ ] Implement `derive_session_identity()` helper
- [ ] Implement `get_or_create_agent_session()` with upsert
- [ ] Implement `cleanup_expired_sessions()`
- [ ] Replace `_derive_transport_session_id()` in server.py
- [ ] Add `agent` parameter to `get_project`, `read_recent` (optional, for explicit isolation)
- [ ] Write Test A: Parallel bind isolation
- [ ] Write Test B: Cross-run isolation
- [ ] Write Test C: Repo canonicalization
- [ ] Write Test D: Missing agent fallback
- [ ] All tests green
- [ ] Manual swarm test with two concurrent agents

---

## Files to Modify

1. **`storage/sqlite.py`**
   - Add `agent_sessions` table in `_initialise()`
   - Add `get_or_create_agent_session()` method
   - Add `cleanup_expired_sessions()` method

2. **`server.py`**
   - Replace `_derive_transport_session_id()` with stable version
   - Add `derive_session_identity()` helper

3. **`shared/execution_context.py`**
   - Ensure `agent_identity` is accessible
   - Add helper for agent_key extraction

4. **`tests/test_session_isolation.py`** (NEW)
   - All four required tests

---

## Security Note

`agent_name` / `display_name` is NOT a secure identity - it's a string anyone can set. In a multi-tenant or adversarial environment, you'd need:
- Session tokens generated by orchestrator
- Cryptographic signing
- Connection-bound salting

For local single-user dev box, current design is sufficient.

---

## Approval

This design has been reviewed and approved with the following conditions:
1. All four tests must pass before shipping
2. Concurrency tests must prove isolation under parallel load
3. No truncation of SHA hash
4. TTL/cleanup must be implemented

**Status: READY FOR IMPLEMENTATION**
