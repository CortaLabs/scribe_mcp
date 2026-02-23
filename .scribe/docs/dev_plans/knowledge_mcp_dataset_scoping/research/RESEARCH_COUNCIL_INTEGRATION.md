---
id: knowledge_mcp_dataset_scoping-research-council-integration
title: "\U0001F52C Research Council Integration \u2014 knowledge_mcp_dataset_scoping"
doc_type: RESEARCH_COUNCIL_INTEGRATION
doc_name: RESEARCH_COUNCIL_INTEGRATION
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 13:34:30 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Council Integration — knowledge_mcp_dataset_scoping
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-22 13:31:37 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Research Goal**: Understand how downstream councils (rom_lab, cooking, etc.) can own datasets, control access, and have queries automatically scoped. Provide the Architect with a verified picture of current infrastructure and concrete gap analysis.

**Confidence**: 0.95 overall (all findings verified from direct code inspection).

**The Core Problem in One Sentence**: Knowledge MCP runs as a single server process anchored to its own repo directory; it discovers its own `.knowledge/` config at startup and assigns every query a workspace label derived from its own repo name — downstream repos have no mechanism to inject their own dataset identity into a running shared server instance.

**Key Findings Summary**:

1. CWD anchoring is absolute — startup locks workspace to knowledge_mcp's own repo
2. workspace is a server-side read-only label, not a per-call routing key
3. scope (repo/council/global) is filesystem breadth, not tenant identity
4. DB isolation (project_id + workspace_slug) is latent but correct
5. Retrieval has a workspace isolation hook in _result_allowed() but chunks lack workspace metadata
6. Extension council_tags hooks gate route activation only, not data access
7. Council MCP's ContextVar/_meta pattern is the proven isolation model to adopt
8. rom_lab data is accessed via an absolute path hardcoded in knowledge_mcp's datasets.yaml
<!-- ID: research_scope -->
**Research Lead:** thoth

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### 1. Workspace Discovery: CWD-Anchored Startup (VERIFIED, confidence: 0.98)

**File**: `src/knowledge_mcp/config/discovery.py:19-24`, `src/knowledge_mcp/config/settings.py:181-206`

`KnowledgeSettings.from_workspace(workspace=None)` calls `discover_repo_root(start=None)`, which walks up from `Path.cwd()` looking for `.git` or `.council`. With `.mcp.json` configuring `cwd=/home/austin/projects/MCP_SPINE/knowledge_mcp`, the server always anchors to knowledge_mcp's repo root.

```python
def discover_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists() or (candidate / COUNCIL_DIR).exists():
            return candidate
    return current
```

`from_workspace(workspace)` accepts a path string but **it is never called with a non-None value in production** — `init_server()` calls `KnowledgeSettings.from_workspace()` with no argument. There is a supported API path for workspace override but it is not wired to any user-facing trigger.

**Consequence**: All dataset discovery reads from knowledge_mcp's own `.knowledge/datasets.yaml`. All rag_profile settings come from knowledge_mcp's own `.knowledge/rag_profile.yaml`. This is fixed at server startup.

---

### 2. Workspace Is a Server-Side String Label, Not a Per-Call Routing Key (VERIFIED, confidence: 0.97)

**File**: `src/knowledge_mcp/server.py:50-76`, `src/knowledge_mcp/api/context.py:23-35`

In `dispatch()`:
```python
request = RouteRequest(
    route=route,
    payload=payload,
    scope=scope or settings.default_scope,
    workspace=settings.repo_root.name,   # <-- hardcoded from server settings
    actor=ActorContext(...)
)
```

In `build_context()`:
```python
workspace = request.workspace.strip() or settings.repo_root.name
```

`RouteRequest.workspace` defaults to `""` and is overridable in the contract, but no MCP tool passes it. All tools call `dispatch(route, payload, scope=scope)` — no workspace argument. The workspace therefore always equals `settings.repo_root.name` which is the directory name `"knowledge_mcp"`.

**FAISS shard consequence**: `_scope_shard("repo", "knowledge_mcp")` → `"repo-knowledge-mcp"`. All fire-red data lands in this shard regardless of which council indexed it.

---

### 3. Scope Model: Filesystem Breadth, Not Tenant Identity (VERIFIED, confidence: 0.97)

**File**: `src/knowledge_mcp/policies/scopes.py`

```python
VALID_SCOPES = {"repo", "council", "global"}

def resolve_source_roots(settings: KnowledgeSettings, scope: str) -> list[Path]:
    roots = [settings.repo_root]
    if settings.council_dir.exists():
        roots.append(settings.council_dir)   # .council/ of knowledge_mcp itself
    if settings.knowledge_dir.exists():
        roots.append(settings.knowledge_dir) # .knowledge/ of knowledge_mcp itself
    if scope == "global":
        roots.append(settings.repo_root.parent)  # parent of knowledge_mcp/
```

`scope=council` means "include knowledge_mcp's `.council/` directory in source roots." It does NOT mean "query this specific council's data." A rom_lab agent passing `scope=council` would still get knowledge_mcp's `.council/` directory — not rom_lab's.

---

### 4. DB Isolation Is Latent and Correct (VERIFIED, confidence: 0.95)

**File**: `db/schema_knowledge_only/knowledge/tables/040_dataset_registry.sql`, `src/knowledge_mcp/adapters/agentkit_db.py:29-89`

`knowledge_datasets` schema:
```sql
CREATE TABLE IF NOT EXISTS knowledge_datasets (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),  -- isolation FK
    workspace_slug TEXT NOT NULL,                       -- isolation label
    name TEXT NOT NULL,
    ...
    UNIQUE (project_id, name)
);
```

`ensure_workspace_project(workspace, repo_root)` creates or fetches a `projects` row keyed by `normalize_workspace_slug(workspace)`. If workspace were `"rom_lab"`, it would create a separate project row `{slug: "rom-lab"}`, and all datasets under that project would be isolated from `{slug: "knowledge-mcp"}`.

**The DB isolation mechanism works correctly.** The gap is that all current API paths hardcode `workspace = settings.repo_root.name = "knowledge_mcp"`, so every dataset lands in the same project.

---

### 5. Retrieval Has a Workspace Isolation Hook But Chunks Lack Workspace Metadata (VERIFIED, confidence: 0.93)

**File**: `src/knowledge_mcp/providers/retrieval.py:527-583`

```python
owner_workspace = str(
    metadata.get("workspace")
    or metadata.get("tenant")
    or metadata.get("council")
    or ""
).strip()
if visibility == "council" and owner_workspace and owner_workspace != request.workspace:
    return False
```

This filter in `_result_allowed()` enforces workspace isolation for `visibility="council"` chunks. If chunks from fire-red were indexed with `metadata.workspace = "rom_lab"` and a cooking council query came in with `request.workspace = "cooking"`, those fire-red chunks would be excluded.

However: fire-red chunks are JSONL records with `domain`, `confidence`, `bucket` fields — no `workspace` field. They are not indexed with `metadata.workspace`. And all data lands in the `"repo-knowledge-mcp"` FAISS shard regardless.

**This hook is sound architecture; the indexing pipeline does not yet populate the workspace field.**

---

### 6. Extension Model: Council Tags Gate Routes, Not Data (VERIFIED, confidence: 0.95)

**File**: `src/knowledge_mcp/extensions/contracts.py:32-47`, `src/knowledge_mcp/extensions/registry.py:51-76`

`ExtensionSpec.applies_to(actor, workspace)` checks:
- `actor.council_tags` (set injected by caller via `ActorContext`)
- `workspace_prefixes` (string prefix matching on workspace name)

This controls which extension **routes** are activated, not which data is returned. Extension route handlers currently return stub metadata dictionaries — not actual retrieval results.

The `rpg_graph.yaml` extension uses `council_tags_any: [rpg, game]` to gate `relationships.rpg_query` and `relationships.rpg_upsert` routes.

This is a viable hook for **route-level** council specialization. It is not a substitute for data-level isolation.

---

### 7. Council MCP's ContextVar Pattern Is the Proven Precedent (VERIFIED, confidence: 0.97)

**File**: `/home/austin/projects/MCP_SPINE/council_mcp/src/council_mcp/storage/hierarchy.py:1-73`

```python
_request_council_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_request_council_id", default=None
)

def get_council_id() -> str | None:
    # 1. Per-request ContextVar (from ws_proxy _meta.council_id injection)
    request_cid = _request_council_id.get()
    if request_cid:
        return request_cid
    # 2. Daemon runtime context fallback
    from council_mcp.server import get_runtime_health
    return get_runtime_health().get("council_id")
```

ws_proxy injects `_meta.council_id` on every tool call. The tool enforcement wrapper reads it into the ContextVar. All DB queries then call `get_council_id()` and filter `WHERE council_id = %s`.

This pattern provides:
- **Zero API signature changes** — callers add `_meta.council_id` to their MCP call metadata, not a new tool parameter
- **Per-request isolation** — each concurrent call sees its own council context
- **Fallback** — daemons without per-request context use startup-time value

**Knowledge MCP should adopt `_meta.datasets` or `_meta.workspace` injection via this same mechanism.**

---

### 8. Current rom_lab Workaround: Absolute Path Hardcoding (VERIFIED, confidence: 0.98)

**File**: `.knowledge/datasets.yaml`, `.mcp.json`

`.mcp.json`:
```json
"knowledge": {
  "command": "knowledge-mcp",
  "args": [],
  "cwd": "/home/austin/projects/MCP_SPINE/knowledge_mcp"
}
```

`.knowledge/datasets.yaml`:
```yaml
datasets:
  - name: "fire-red-lore"
    source: "/home/austin/projects/pokemon/rom_lab/data/fire_red/rag_exports/pokefirered-20260214T031540469969Z/ai_chunks"
    type: "corpus"
    scope: "repo"
```

rom_lab's data source is declared as an absolute filesystem path in knowledge_mcp's own config. This works but:
- rom_lab has no `.knowledge/` dir of its own — VERIFIED (directory does not exist)
- rom_lab has no `.mcp.json` — VERIFIED (file does not exist)
- The build_id in the path is hardcoded — will break when fire-red data is re-exported
- There is no mechanism for a second rom_lab game dataset without editing knowledge_mcp's files
- A cooking council cannot register its datasets without modifying knowledge_mcp's files

---

### 9. MCP Tool API Has No Dataset or Workspace Parameter (VERIFIED, confidence: 0.97)

**File**: `src/knowledge_mcp/tools/search_sources.py`, `src/knowledge_mcp/tools/list_datasets.py`

```python
@mcp.tool()
def search_sources(
    query: str,
    scope: str = "repo",
    domains: list[str] | None = None,
    source_types: list[str] | None = None,
    limit: int = 10,
    debug: bool = False,
) -> dict[str, Any]:
```

No `dataset` parameter. No `workspace` parameter. Downstream callers cannot specify which dataset to search or which workspace to scope to. The FAISS shard searched is always `"repo-knowledge-mcp"` (the server's own shard).

A rom_lab agent calling `search_sources(query="how does Brock's Onix resist?", domains=["battle"])` searches the same shard as every other agent. Currently this works because fire-red is the only indexed dataset. With a second council's data indexed, results would bleed across council boundaries.
<!-- ID: technical_analysis -->
## Technical Analysis

### The CWD / Workspace Discovery Problem

The fundamental architecture question is: **who owns the running knowledge-mcp instance?**

Currently: knowledge_mcp owns itself. One server. One `.knowledge/` config. One FAISS shard namespace.

A downstream council (rom_lab) consuming that server is a **client** — it has no mechanism to say "I am rom_lab, please use rom_lab's datasets." The server does not know who is calling.

Three architectural options exist:

**Option A — One Instance Per Downstream Repo (Per-Repo Server)**
Each downstream repo runs its own `knowledge-mcp` process with `cwd=<their_repo>`. Their `.mcp.json` points to their own instance. They own their `.knowledge/` config entirely.

- **Pros**: Zero changes to existing server. Full config isolation. Each repo's rag_profile is independent.
- **Cons**: N instances for N repos. Each instance manages its own FAISS shards. No cross-repo search. Resource multiplied.
- **Viable today**: `KnowledgeSettings.from_workspace()` already supports this — just change `cwd` in `.mcp.json`.

**Option B — Central Server with Per-Call Dataset/Workspace Identity**
One server. Downstream repos inject their identity (`_meta.workspace` or `_meta.datasets`) via ws_proxy or MCP metadata. The server routes searches to the correct FAISS shard and filters datasets by workspace.

- **Pros**: Shared infrastructure. Future cross-council search possible. Single FAISS index manager.
- **Cons**: Requires: (1) `_meta.workspace` injection mechanism, (2) per-call workspace ContextVar in knowledge_mcp, (3) FAISS shard-per-workspace at index time, (4) datasets.yaml discovery per downstream repo (or API-based registration).
- **Pattern exists in Council MCP**: ContextVar injection via `_meta.council_id` is proven.

**Option C — Central Registration API**
Downstream repos call `datasets.register` at startup to declare their datasets. The server stores them with their workspace identity. Queries include `workspace=` parameter.

- **Pros**: API-driven, no filesystem discovery needed for downstream repos.
- **Cons**: Registration must happen before queries. Requires datasets.register to be exposed and trusted. Currently `datasets.register` requires `knowledge:index` grant.
- **This is partially implemented**: `register_dataset()` in `dataset_service.py` already supports this. The missing piece is the workspace parameter at query time.

### FAISS Shard Architecture Under Each Option

| Option | Shard per entity | Isolation mechanism |
|--------|-----------------|---------------------|
| A (per-repo) | `repo-<their_repo_name>` | Separate server process |
| B (central + workspace injection) | `repo-<workspace_slug>` per downstream repo | ContextVar → `_scope_shard(scope, injected_workspace)` |
| C (registration API + workspace param) | Same as B | `workspace=` MCP param → `_scope_shard()` |

**Existing code in `_scope_shard()` already handles Options B and C** — the shard name already derives from workspace. The gap is that the workspace value is always fixed to `"knowledge_mcp"` at call time.

### Practical Scenario: rom_lab Today vs. What Should Happen

**Today** (broken architecture):
```
rom_lab agent → search_sources(query="Brock's Onix type?")
  → dispatch("search.sources", payload, scope="repo")
  → RouteRequest(workspace="knowledge_mcp")
  → FAISS shard: "repo-knowledge-mcp"
  → Returns fire-red results (happens to work, only 1 dataset)
```

**With a second council (e.g., cooking) added to same shard** (broken):
```
cooking agent → search_sources(query="beef stew recipe")
  → FAISS shard: "repo-knowledge-mcp"
  → Could return fire-red chunks + recipe chunks mixed (bleeding)
```

**Target architecture (Option B)**:
```
rom_lab agent → search_sources(query="Brock's Onix type?")
  _meta.workspace = "rom_lab" (injected by ws_proxy or caller config)
  → ContextVar: _request_workspace = "rom_lab"
  → dispatch() reads ContextVar instead of settings.repo_root.name
  → RouteRequest(workspace="rom_lab")
  → FAISS shard: "repo-rom-lab"
  → Only rom_lab's indexed data

cooking agent → search_sources(query="beef stew recipe")
  _meta.workspace = "cooking"
  → FAISS shard: "repo-cooking"
  → Only cooking's indexed data
```

### How Scribe Handles This (Comparison)

Scribe handles project scoping by accepting a `project_name` parameter at every tool call. Each `append_entry()`, `manage_docs()`, etc. takes `project_name` explicitly or resolves it from a session context. The session is opened with `set_project(name=...)`.

Knowledge MCP could adopt the same explicit parameter approach — adding `datasets: list[str]` or `workspace: str` to `search_sources`, `query_answer`, `list_datasets` — rather than using ContextVar injection. This is Option C.

The ContextVar approach (Option B) is more transparent to callers but requires ws_proxy-level coordination. The explicit parameter approach requires API changes but is simpler to debug.

**Both are viable. The Architect must choose.**

### What Does not Require Changes

- `knowledge_datasets` DB schema — already workspace-scoped via project_id
- `_result_allowed()` workspace filter logic — already implemented
- `_scope_shard()` shard naming — already workspace-parameterized
- `ensure_workspace_project()` — already creates per-workspace project rows
- `ExtensionSpec.applies_to()` — already has council_tags and workspace_prefixes hooks
- `KnowledgeSettings.from_workspace(workspace)` — already accepts a path override

All the infrastructure is in place. The gap is in the data flow path from caller → dispatch() → FAISS query.
<!-- ID: recommendations -->
## Recommendations for Architect

### Decision Point 1: Deployment Model (Decide First)

**Choose between per-repo instances (Option A) vs. central shared server (Options B/C).**

Recommendation: **Option A for now, Option B/C as target architecture.**

Rationale: Option A is zero-code. It works today. rom_lab can run its own knowledge-mcp instance anchored to its repo with its own `.knowledge/datasets.yaml` and rag_profile.yaml. This unblocks dataset isolation immediately.

Option B or C is the right end-state for cross-council search, shared indexing infrastructure, and dataset federation — but requires significant engineering. Design it now, implement it when the simpler option proves insufficient.

### Decision Point 2: Per-Call Identity Mechanism (for Options B/C)

**Choose between ContextVar injection (Option B) vs. explicit tool parameter (Option C).**

- ContextVar via `_meta.workspace`: Follows Council MCP precedent. Invisible to tool signatures. Requires ws_proxy coordination. Best for the "agent doesn't need to know" pattern.
- Explicit `workspace: str` param on tools: Simpler. Debuggable. Breaks backward compatibility if added as required. Works as optional with default fallback to server setting.

**Recommendation**: Add optional `workspace: str = ""` and `datasets: list[str] | None = None` parameters to `search_sources`, `query_answer`, `list_datasets`. Use ContextVar as a secondary injection path. This gives maximum flexibility.

### Decision Point 3: Dataset Registration for Downstream Repos

**How do downstream repos declare their datasets to a shared central server?**

Three sub-options:
- **Static file in knowledge_mcp**: Current approach. Does not scale. Requires PRs to add new councils.
- **API registration at startup**: Downstream repo's `.mcp.json` startup script calls `datasets.register`. Requires `knowledge:index` grant. Datasets persist in DB.
- **Filesystem crawl**: Server periodically scans known repo roots. Fragile, requires repo list.

**Recommendation**: API registration. Add a `datasets.register_workspace` route that accepts a repo path and crawls its `.knowledge/datasets.yaml`. Called once at downstream repo startup. Requires `knowledge:index` grant. Already supported by `register_dataset()` and `ensure_workspace_project()` — just needs a new route handler.

### Concrete Changes Required (for Options B/C)

1. **`server.py` / `dispatch()`**: Read `_request_workspace` ContextVar before falling back to `settings.repo_root.name`. Adds ~5 lines.

2. **`src/knowledge_mcp/storage/workspace.py` (new module)**: Add `_request_workspace: ContextVar`, `get_workspace()`, `set_workspace(value)`. Mirrors Council MCP's `hierarchy.py` pattern.

3. **`src/knowledge_mcp/tools/search_sources.py`**: Add `workspace: str = ""` parameter. Pass to `dispatch()`. If provided, set in ContextVar before dispatch.

4. **`src/knowledge_mcp/providers/indexing.py`**: Ensure indexed chunks carry `metadata.workspace = <indexing_workspace>`. This enables `_result_allowed()` to filter correctly.

5. **`.knowledge/datasets.yaml` in downstream repos**: Each downstream repo creates its own file. Either references local paths or registeres via API.

### Future Vision Notes (Document, Do Not Design)

These are for Architect awareness — the Research Agent is not designing them:

- **Dataset hierarchy tiers**: `project > council > global` — datasets could inherit visibility rules up/down the tier. The `scope` field on `knowledge_datasets` already has `repo/council/global` values that could map to tiers.
- **Push federation**: A council publishes its dataset (re-indexes it to the central server's shared shard). Requires `knowledge:index` grant + workspace identity.
- **Pull federation**: Central server discovers datasets from registered repos by crawling their `.knowledge/` dirs. Requires a repo registry table.
- **Cross-council search**: `scope=global` already enables global shard search. The existing `visibility` filter ensures only `public` data bleeds across workspaces.
- **Dataset grants**: `required_grants` field on `knowledge_datasets` already supports per-dataset access control. Could be used for "council A grants council B read access to dataset X."

### Open Questions for Architect

1. Should `workspace` in Knowledge MCP map 1:1 to a downstream repo name, or to a council identity? (rom_lab repo vs. the rom_lab council — they may differ)

2. When Option A (per-repo) is deployed, how do rom_lab agents know which knowledge-mcp URL to use? (Multiple `.mcp.json` entries? One per repo?)

3. If central server (Option B/C) is chosen, who holds the `knowledge:index` grant to register datasets? (Requires trust model decision)

4. Does the rag_profile need to be per-workspace (e.g., fire-red vs. cooking have different scoring weights)? If so, Option A is required since rag_profile is loaded at server startup.

5. Should `council_tags` in `ActorContext` be used to carry dataset affinity, or is `workspace` sufficient?
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---