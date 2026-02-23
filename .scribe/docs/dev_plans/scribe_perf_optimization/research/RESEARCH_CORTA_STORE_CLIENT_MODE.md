---
id: scribe_perf_optimization-research-corta-store-client-mode
title: "\U0001F52C Research Corta Store Client Mode \u2014 scribe_perf_optimization"
doc_type: RESEARCH_CORTA_STORE_CLIENT_MODE
doc_name: RESEARCH_CORTA_STORE_CLIENT_MODE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 06:04:05 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Corta Store Client Mode — scribe_perf_optimization
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 06:02:26 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Research Goal:** Audit CortaStore (object store) integration in Scribe MCP CLIENT mode.

**Verdict: Mostly working, with two minor issues and one design consideration.**

CortaStore integration in CLIENT mode is correctly designed and implemented. The client Scribe instance initializes a `HybridStore` (local filesystem + CortaStore remote) independently of the remote DB backend. Document writes via `manage_docs`, `edit_file`, `special_create`, and `generate_doc_templates` are synced to CortaStore. Reads fall back to CortaStore on local cache miss.

Two minor issues were identified:
1. **Wasteful Postgres initialization at import time** — the module-level `create_storage_backend()` call in `server.py` creates a `PostgresStorage` object (because `SCRIBE_DB_URL` is set in `.env`) that is immediately discarded when `_startup()` replaces it with `RemoteStorageBackend`. Not a functional bug, but wastes memory and imports asyncpg unnecessarily.
2. **No CortaStore startup health check** — `HybridStore.setup()` creates an httpx client but does not probe CortaStore connectivity. Silent failures on every sync if Tailscale is down.

**Path mapping is NOT a concern.** Keys are repo-root-relative (absolute path stripped), so CLIENT (`/home/austin/...`) and SERVER (`/app`) generate identical keys. CortaStore is content-addressed, making concurrent writes idempotent.

**Confidence: 0.90** (high — all claims backed by direct code inspection)
<!-- ID: research_scope -->
## Research Scope

**Scope:** CortaStore integration in CLIENT mode — does document sync work correctly?

**Files Analyzed:**
- `src/scribe_mcp/server.py` — startup sequence, mode detection, document store initialization
- `src/scribe_mcp/config/settings.py` — object store env vars, mode settings
- `src/scribe_mcp/config/mode_detection.py` — CLIENT/SERVER/STANDALONE detection logic
- `src/scribe_mcp/object_store/__init__.py` — factory, `sync_file_to_store()` helper
- `src/scribe_mcp/object_store/base.py` — DocumentStore + RemoteProvider abstract interfaces
- `src/scribe_mcp/object_store/filesystem.py` — local filesystem store
- `src/scribe_mcp/object_store/hybrid.py` — write-through composite store
- `src/scribe_mcp/object_store/keys.py` — path-to-key conversion, sync eligibility rules
- `src/scribe_mcp/object_store/providers/corta.py` — CortaStore HTTP client
- `src/scribe_mcp/doc_management/manager.py` — managed doc write path, auto-resolve document_store
- `src/scribe_mcp/doc_management/special_create.py` — new doc creation + sync
- `src/scribe_mcp/doc_management/special_indexes.py` — index update + sync
- `src/scribe_mcp/utils/files.py` — `async_atomic_write()` with document_store parameter
- `src/scribe_mcp/tools/edit_file.py` — file edit + sync
- `src/scribe_mcp/tools/generate_doc_templates.py` — template generation + sync
- `src/scribe_mcp/storage/__init__.py` — `create_storage_backend()` factory
- `.env.example`, `.env` (via native Read) — current CLIENT mode configuration
<!-- ID: findings -->
## Findings

### Finding 1: Object Store Initialization Is Correctly Outside CLIENT Mode Guard
**Confidence: 0.95**

In `server.py` `_startup()` (lines 833-847), the document store initialization block has an explicit comment:
```python
# Initialize document store (object store layer)
# Client mode KEEPS this — client talks to CortaStore directly
try:
    from scribe_mcp.object_store import create_document_store
    document_store = create_document_store(settings)
    await document_store.setup()
    app.state.document_store = document_store
```

This block runs in ALL modes (CLIENT, SERVER, STANDALONE). When `SCRIBE_OBJECT_STORE_URL` is set, it creates a `HybridStore(local=FilesystemStore, remote=CortaStoreProvider)`. When not set, it creates a `FilesystemStore` (zero overhead).

**The CLIENT mode does correctly initialize CortaStore independently of the remote storage backend.**

---

### Finding 2: Path Keys Are Mode-Agnostic (Path Mapping Is Not A Problem)
**Confidence: 0.95** | File: `src/scribe_mcp/object_store/keys.py:31-41`

The `path_to_key()` function computes keys as repo-root-relative paths:
```python
def path_to_key(file_path, repo_root):
    rel = Path(file_path).resolve().relative_to(Path(repo_root).resolve())
    posix = str(PurePosixPath(rel))
    if posix.startswith(".scribe/"):
        posix = "scribe/" + posix[len(".scribe/"):]
    return posix
```

**Result:** A file at `.scribe/docs/dev_plans/foo/ARCHITECTURE_GUIDE.md` becomes key `scribe/docs/dev_plans/foo/ARCHITECTURE_GUIDE.md` regardless of whether the repo root is `/home/austin/projects/MCP_SPINE/scribe_mcp` (local dev) or `/app` (Docker server).

**There are no path conflicts between CLIENT and SERVER writes to CortaStore.** CortaStore is content-addressed — identical content produces identical hash, making concurrent writes idempotent.

---

### Finding 3: Sync Pipeline Coverage — All Major Write Paths Are Wired
**Confidence: 0.90**

The following tools and paths trigger CortaStore sync:

| Write Path | File | Sync Mechanism |
|------------|------|----------------|
| `manage_docs` (any edit) | `doc_management/manager.py:630` | `async_atomic_write(document_store=...)` |
| `manage_docs` (create) | `doc_management/special_create.py:419-423` | `sync_file_to_store()` |
| `manage_docs` (indexes) | `doc_management/special_indexes.py:171-178, 255-261, 343-350` | `sync_file_to_store()` |
| `edit_file` | `tools/edit_file.py:344-351` | `sync_file_to_store()` |
| `generate_doc_templates` | `tools/generate_doc_templates.py:352-361` | `sync_file_to_store()` |
| `read_file` (cache miss) | `tools/read_file.py:1887-1897` | Downloads from CortaStore, caches locally |

**`append_entry` does NOT sync to CortaStore** — progress logs are written via `_write_line()/_write_line_with_wal()`, which is intentionally bypassed. Only managed documents (architecture guides, research docs, checklists) are synced.

---

### Finding 4: Auto-Resolve Pattern Correctly Picks Up document_store In All Modes
**Confidence: 0.90** | File: `doc_management/manager.py:148-154`

```python
def apply_doc_change(..., document_store=None):
    # Auto-resolve document_store from app.state when not explicitly passed.
    if document_store is None:
        try:
            from scribe_mcp.server import app as _app
            document_store = getattr(getattr(_app, "state", None), "document_store", None)
        except Exception:
            pass
```

`sync_file_to_store()` also resolves via `from scribe_mcp.server import app` at call time. Since the server module is always imported in the same process, this correctly picks up `app.state.document_store` set during `_startup()` — regardless of CLIENT or SERVER mode.

---

### Finding 5: PROGRESS_LOG.md Matches Sync Prefix But Is Never Synced (By Design)
**Confidence: 0.95**

`keys.py` `_SYNC_PREFIXES` includes `.scribe/docs/dev_plans/`. PROGRESS_LOG.md is at `.scribe/docs/dev_plans/<project>/PROGRESS_LOG.md`, so `should_sync()` returns `True`. However, `append_entry` writes via `_write_line()`, not `async_atomic_write()`, so sync is never triggered.

**This is intentional** — high-frequency log writes stay local. The design separates log files (ephemeral, local) from managed documents (persistent, synced).
<!-- ID: technical_analysis -->
## Technical Analysis

### Architecture Diagram: CortaStore Data Flow in CLIENT Mode

```
LOCAL DEV MACHINE                          HETZNER (council-hub)
┌─────────────────────────────────┐        ┌──────────────────────────────┐
│  Scribe MCP (CLIENT mode)       │        │  Scribe MCP (SERVER mode)    │
│                                 │        │                              │
│  _startup():                    │        │  app.state.document_store    │
│    mode = CLIENT                │        │    = HybridStore             │
│    storage_backend              │        │      local=FilesystemStore   │
│      = RemoteStorageBackend─────┼─REST──►│      remote=CortaStoreProvider│
│    document_store               │        │             │                │
│      = HybridStore              │        └─────────────┼────────────────┘
│          local=FilesystemStore  │                       │
│          remote=CortaStoreProvider───►──┐               │
│                                 │       │               ▼
│  manage_docs / edit_file /      │       │  ┌─────────────────────────┐
│  special_create / etc.          │       │  │  CortaStore :8201       │
│    → sync_file_to_store()       │       └─►│  (Hetzner, Tailscale)   │
│    → HybridStore.write()        │          │                          │
│       → FilesystemStore.write() │          │  /v1/objects/{sha256}   │
│       → CortaStoreProvider.put()│◄─────────│  /v1/refs/{project}/...  │
│                                 │          └─────────────────────────┘
│  DB OPS (append_entry, etc.)    │
│    → RemoteStorageBackend ──────┼─REST──► Scribe MCP /api/* endpoints
└─────────────────────────────────┘
```

**Key Design Principle:** DB operations (Postgres) proxy to Hetzner via REST. Document storage (CortaStore) is accessed directly from the client — no double-proxying.

---

### Configuration Requirements for CLIENT Mode + CortaStore

Required in `.env`:
```bash
# Mode selection (explicit, no auto-detection delay)
SCRIBE_MODE=client

# Remote DB backend
SCRIBE_REMOTE_URL=http://council-hub:8200  # OR Tailscale IP

# Object store (optional but enables cross-machine sync)
SCRIBE_OBJECT_STORE_URL=http://council-hub:8201
SCRIBE_OBJECT_STORE_PROVIDER=corta
SCRIBE_OBJECT_STORE_KEY=<hmac-secret-hex-string>
SCRIBE_OBJECT_STORE_PROJECT=scribe

# NOT needed in client mode (but can coexist without breaking anything):
# SCRIBE_DB_URL — will cause wasteful PostgresStorage object creation at import
# SCRIBE_STORAGE_BACKEND — ignored once RemoteStorageBackend takes over
```

**Note on HMAC key format:** The key is stored as a raw hex string (e.g., `e7866795...`). `CortaStoreProvider.__init__` encodes it with `.encode()` (UTF-8 bytes). This must match what the CortaStore server expects.

---

### Object Store Module Structure

```
src/scribe_mcp/object_store/
├── __init__.py          # Factory: create_document_store(), sync_file_to_store()
├── base.py              # Abstract: DocumentStore, RemoteProvider
├── filesystem.py        # Local-only store (no remote overhead)
├── hybrid.py            # Write-through: local + remote, fire-and-forget
├── keys.py              # Path↔Key conversion, sync eligibility rules
└── providers/
    ├── __init__.py      # create_provider() factory
    ├── corta.py         # CortaStore HTTP client (HMAC signing, retry)
    └── s3.py            # S3-compatible provider (alternative)
```

---

### Sync Eligibility Rules (keys.py)

**Synced (ALLOW):**
- `.scribe/docs/dev_plans/**/*.md` — architecture, research, checklists, phase plans
- `.scribe/docs/agent_report_cards/**/*.md` — agent performance records
- `docs/bugs/**/*.md` — bug reports
- `.scribe/docs/**/reviews/**/*.md` — review documents

**NOT synced (DENY, takes priority):**
- `.scribe/sentinel/**` — event logs
- `.scribe/config/**` — configuration files
- `.scribe/logs/**` — tool logs
- `.scribe/templates/**` — Jinja2 source files

**NOTE:** PROGRESS_LOG.md matches the ALLOW prefix but is never synced because `append_entry` bypasses `async_atomic_write` entirely.
<!-- ID: recommendations -->
## Identified Issues and Recommendations

### Issue 1: Wasteful PostgresStorage Creation at Module Import Time (Minor)
**Severity: Low** | **File:** `src/scribe_mcp/server.py:117`, `src/scribe_mcp/storage/__init__.py:13-72`

**Problem:** Line 117 in server.py calls `create_storage_backend()` without a `mode` argument at Python import time. When `.env` has both `SCRIBE_MODE=client` AND `SCRIBE_DB_URL` set, this creates a `PostgresStorage` object (which imports asyncpg) that is immediately discarded in `_startup()` when it is replaced with `RemoteStorageBackend`.

**Impact:** Unnecessary asyncpg import, minor memory waste, slightly longer import time. Not a functional bug.

**Recommendation:** Modify `create_storage_backend()` to read `settings.mode` directly and return a `RemoteStorageBackend` when `mode == "client"`, even when called without an explicit mode argument. This eliminates the wasteful Postgres object.

```python
# storage/__init__.py - proposed fix
def create_storage_backend(mode=None):
    from scribe_mcp.config.settings import settings
    
    # Read mode from settings when not explicitly provided
    effective_mode = mode
    if effective_mode is None and settings.mode == "client":
        from scribe_mcp.config.mode_detection import OperatingMode
        effective_mode = OperatingMode.CLIENT
    
    if effective_mode is not None:
        from scribe_mcp.config.mode_detection import OperatingMode as _OM
        if effective_mode == _OM.CLIENT:
            from scribe_mcp.storage.remote import RemoteStorageBackend
            return RemoteStorageBackend(...)
    # ... rest of factory
```

---

### Issue 2: No CortaStore Startup Health Check (Minor)
**Severity: Low** | **File:** `src/scribe_mcp/object_store/hybrid.py:28-29`

**Problem:** `HybridStore.setup()` only calls `await self._remote.setup()`, which in `CortaStoreProvider.setup()` just creates an httpx client with no connectivity probe. If CortaStore (council-hub:8201) is unreachable (Tailscale down, service down), startup succeeds but every sync attempt quietly retries 3x and logs a warning.

**Impact:** No visibility at startup that CortaStore is unreachable. Operations degrade silently.

**Recommendation:** Add a startup connectivity check (ping `GET /health` or similar) in `CortaStoreProvider.setup()` with a warning log if unreachable. Do NOT make it a hard failure — current graceful degradation is correct for fire-and-forget sync.

```python
# corta.py - proposed addition to setup()
async def setup(self) -> None:
    self._client = httpx.AsyncClient(...)
    # Optional health probe — warn but don't fail
    try:
        resp = await self._client.get("/health", timeout=2.0)
        if resp.status_code != 200:
            logger.warning("CortaStore health check returned %d — sync may fail", resp.status_code)
    except Exception as exc:
        logger.warning("CortaStore unreachable at %s: %s — sync will be skipped", self._base_url, exc)
```

---

### Issue 3: Coexistence of SCRIBE_DB_URL + SCRIBE_MODE=client in .env (Consideration)
**Severity: Info** | **File:** `.env`

**Observation:** The current `.env` has both `SCRIBE_MODE=client` AND `SCRIBE_DB_URL=postgresql://...`. This creates the wasteful Postgres object at import (Issue 1). For a pure CLIENT deployment, `SCRIBE_DB_URL` is not needed — it's only used for direct server access.

**Recommendation:** Consider documenting in `.env.example` that CLIENT mode should typically NOT include `SCRIBE_DB_URL`. The current `.env` appears to be a transitional configuration from before CLIENT mode was fully implemented.

---

### What Works Correctly (No Action Needed)

1. **Path mapping** — `path_to_key()` produces identical keys across CLIENT and SERVER environments. No conflicts.
2. **Sync pipeline wiring** — All major write tools (`manage_docs`, `edit_file`, `special_create`, `generate_doc_templates`) correctly trigger CortaStore sync.
3. **document_store resolution** — Both `apply_doc_change()` and `sync_file_to_store()` correctly resolve `app.state.document_store` at call time, regardless of mode.
4. **Content-addressed storage** — Concurrent CLIENT+SERVER writes to same key are idempotent.
5. **Progress log isolation** — `append_entry` correctly bypasses CortaStore sync (no performance impact from high-frequency log writes).
6. **Graceful degradation** — CortaStore failures never propagate to callers (all wrapped in try/except pass).
7. **HMAC signing** — `CortaStoreProvider._sign()` uses standard `hmac.new()` API correctly.
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---