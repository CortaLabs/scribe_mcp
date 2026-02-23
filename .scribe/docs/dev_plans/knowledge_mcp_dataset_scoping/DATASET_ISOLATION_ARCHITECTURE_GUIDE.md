---
id: knowledge_mcp_dataset_scoping-dataset-isolation-architecture-guide
title: 'Architecture Guide: Dataset Isolation for Knowledge MCP'
doc_type: custom
doc_name: DATASET_ISOLATION_ARCHITECTURE_GUIDE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 13:45:19 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Architecture Guide: Dataset Isolation for Knowledge MCP

**Author:** ArchitectAgent
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-02-22
**Project:** knowledge_mcp_dataset_scoping
**Confidence:** 0.95

---

## 1. Problem Statement
<!-- ID: problem_statement -->

### Context

Knowledge MCP serves as the shared RAG and indexing infrastructure for downstream councils and repositories. Currently, all indexed datasets (fire-red Pokemon lore, repo documentation, etc.) land in a single FAISS shard per workspace (`repo-knowledge-mcp`). There is no mechanism for callers to restrict queries to specific datasets, and no mechanism for councils to claim ownership of their datasets.

### The Problem

1. **No dataset-scoped queries**: `search_sources(query="Brock's Onix")` returns results from ALL indexed data — Pokemon lore, repo docs, and any future datasets — indiscriminately.
2. **No caller identity**: The MCP tools have no `datasets` parameter. A rom_lab agent cannot say "only search fire-red-lore."
3. **No council ownership**: `knowledge_datasets` table has no council binding. Any caller with scope access sees everything.
4. **Cross-dataset contamination**: As more datasets are indexed, result quality degrades because unrelated content pollutes search results.

### Goals

- **G1**: Callers can restrict search/query to specific named datasets via an explicit tool parameter.
- **G2**: Dataset identity is propagated through the full indexing and retrieval pipeline.
- **G3**: Council-based auto-scoping: when a council agent queries, they automatically see only their datasets.
- **G4**: Knowledge MCP works standalone without requiring council_mcp to be running.
- **G5**: Existing tests (177 passing) continue to pass with zero regressions.

---

## 2. System Overview
<!-- ID: system_overview -->

### Current Architecture (Before)

```
Caller -> search_sources(query, scope, domains)
  -> dispatch("search.sources", payload, scope)
    -> RouteRequest(workspace=settings.repo_root.name)  # always "knowledge_mcp"
      -> build_context() -> workspace fallback to settings.repo_root.name
        -> search_service.search_sources(context, query)
          -> build_retrieval_request(query, scope, workspace, ...)
            -> RetrievalRequest(query, scope, workspace="knowledge_mcp")
              -> _search_faiss() -> shard="repo-knowledge-mcp" (ALL datasets mixed)
              -> _result_allowed() -> NO dataset filter
```

### Target Architecture (After)

```
Caller -> search_sources(query, scope, domains, datasets=["fire-red-lore"])
  -> dispatch("search.sources", payload, scope)
    -> RouteRequest(workspace=settings.repo_root.name)
      -> build_context()
        -> search_service.search_sources(context, query, payload={"datasets": [...]})
          -> build_retrieval_request(query, scope, workspace, payload={"datasets": [...]})
            -> RetrievalRequest(query, scope, workspace, datasets=["fire-red-lore"])
              -> _search_faiss() -> shard="repo-knowledge-mcp" (Phase 1: shared shard)
              -> _result_allowed() -> dataset filter: metadata["dataset_name"] in request.datasets
```

### Data Flow: Indexing Path (After)

```
index.run(plan_id, scope)
  -> _ingest_preformed_chunks_faiss(...)
    -> For each chunk:
      chunk_tags.append(f"dataset:{dataset_name}")       # NEW: dataset tag
      chunk_metadata["dataset_name"] = dataset_name       # NEW: dataset identity in metadata
      IngestRequest(tags=chunk_tags, metadata=chunk_metadata, shard_name=...)
```

### Data Flow: Query Path (After)

```
search_sources(query, datasets=["fire-red-lore"])
  -> dispatch() passes datasets in payload
    -> build_retrieval_request() extracts datasets from payload
      -> RetrievalRequest.datasets = ["fire-red-lore"]
        -> _search_faiss() -> searches shared shard, returns all top-k
          -> _result_allowed() checks:
            1. (existing) doc_types, source_types, grants, visibility, workspace, tags, domains
            2. (NEW) if request.datasets: metadata["dataset_name"] must be in request.datasets
```

---

## 3. Component Design
<!-- ID: component_design -->

### 3.1 MCP Tool API Changes

**Files to modify:**
- `src/knowledge_mcp/tools/search_sources.py`
- `src/knowledge_mcp/tools/query_answer.py`
- `src/knowledge_mcp/tools/list_datasets.py`

**Change:** Add optional `datasets: list[str] | None = None` parameter to `search_sources` and `query_answer`. When provided, the parameter is passed through to `dispatch()` via the payload dict.

```python
# search_sources.py — target signature
@mcp.tool()
def search_sources(
    query: str,
    scope: str = "repo",
    domains: list[str] | None = None,
    source_types: list[str] | None = None,
    limit: int = 10,
    debug: bool = False,
    datasets: list[str] | None = None,    # NEW
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query, "limit": limit}
    if domains:
        payload["domains"] = domains
    if source_types:
        payload["source_types"] = source_types
    if debug:
        payload["debug"] = True
    if datasets:
        payload["datasets"] = datasets              # NEW
    return dispatch("search.sources", payload, scope=scope)
```

```python
# query_answer.py — target signature
@mcp.tool()
def query_answer(
    question: str,
    scope: str = "repo",
    domains: list[str] | None = None,
    limit: int = 6,
    datasets: list[str] | None = None,    # NEW
) -> dict[str, Any]:
    payload: dict[str, Any] = {"question": question, "limit": limit}
    if domains:
        payload["domains"] = domains
    if datasets:
        payload["datasets"] = datasets              # NEW
    return dispatch("query.answer", payload, scope=scope)
```

**Backward compatibility:** `datasets=None` (default) means no dataset filter — all datasets are searched, preserving current behavior. Existing callers are unaffected.

### 3.2 RetrievalRequest Extension

**File to modify:** `src/knowledge_mcp/providers/retrieval.py`

**Change:** Add `datasets: list[str]` field to `RetrievalRequest` dataclass.

```python
@dataclass(slots=True)
class RetrievalRequest:
    query: str
    scope: str
    workspace: str
    limit: int = 8
    actor_grants: set[str] = field(default_factory=set)
    actor_roles: set[str] = field(default_factory=set)
    domains: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    path_prefixes: list[str] = field(default_factory=list)
    required_grants: list[str] = field(default_factory=list)
    visibility: list[str] = field(default_factory=list)
    include_faiss: bool = True
    debug: bool = False
    scoring_weights: ScoringWeights = field(default_factory=ScoringWeights)
    source_types: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)  # NEW
    # ... existing profile-derived fields ...
```

**Change in `build_retrieval_request()`:** Extract `datasets` from payload options.

```python
# In build_retrieval_request(), after source_types extraction:
datasets = _dedupe(_as_text_list(options.get("datasets") or options.get("dataset")))

# Pass into RetrievalRequest constructor:
return RetrievalRequest(
    ...,
    datasets=datasets,  # NEW
    ...
)
```

### 3.3 Dataset Filter in _result_allowed()

**File to modify:** `src/knowledge_mcp/providers/retrieval.py`

**Change:** Add dataset_name check to `_result_allowed()` method in `AgentKitRetrievalProvider`.

```python
def _result_allowed(self, result: dict[str, Any], request: RetrievalRequest) -> bool:
    metadata = dict(result.get("metadata") or {})

    # --- NEW: Dataset filter (highest priority check) ---
    if request.datasets:
        result_dataset = str(metadata.get("dataset_name") or "").strip()
        if not result_dataset or result_dataset not in request.datasets:
            return False

    # ... existing checks unchanged ...
```

**Placement:** The dataset check goes FIRST in `_result_allowed()` (before doc_types check at current line 529). This is the most selective filter and short-circuits early for maximum performance.

**Behavior when `request.datasets` is empty:** The check is skipped entirely (existing behavior preserved). ALL datasets are returned.

### 3.4 Indexing Pipeline: Dataset Identity Propagation

**File to modify:** `src/knowledge_mcp/providers/indexing.py`

**Change 1: `_ingest_preformed_chunks_faiss()`** — Add `dataset_name` parameter, write into tags and metadata.

```python
def _ingest_preformed_chunks_faiss(
    *,
    preformed: list[_PreformedChunk],
    relative_path: str,
    base_tags: list[str],
    metadata: dict[str, Any],
    scope: str,
    workspace: str,
    visibility: str,
    faiss_batch_size: int,
    dataset_name: str = "",          # NEW
) -> tuple[int, list[dict[str, Any]]]:
    # ...
    for chunk in preformed:
        chunk_tags = list(base_tags)
        if chunk.domain:
            chunk_tags.append(f"domain:{chunk.domain}")
        if dataset_name:                                    # NEW
            chunk_tags.append(f"dataset:{dataset_name}")    # NEW
        chunk_metadata = dict(metadata)
        chunk_metadata.update(chunk.metadata)
        if dataset_name:                                    # NEW
            chunk_metadata["dataset_name"] = dataset_name   # NEW
        # ... rest unchanged ...
```

**Change 2: `run()` method** — Pass dataset_name from `_IndexPlanState.options["dataset_names"]` to the FAISS ingestion calls. The `dataset_names` value is already parsed in `_normalize_options()` at line 954 but never passed to ingestion. Wire it through.

```python
# In run(), where _ingest_preformed_chunks_faiss is called:
# Current code uses state.options["dataset_names"] to resolve sources
# but never passes the dataset name to ingestion.
# When indexing JSONL files from a specific dataset:
dataset_name = ""  # resolved from dataset lookup or state.options
if len(state.options["dataset_names"]) == 1:
    dataset_name = state.options["dataset_names"][0]
# If dataset_names has multiple entries, resolve per-source from
# _resolve_dataset_sources() lookup results.
```

**Change 3: Standard text file ingestion** — The `run()` method also ingests standard text files via `IngestRequest` (lines 689-699). Add `dataset_name` to those metadata dicts too when indexing within a named dataset context.

### 3.5 datasets.yaml Schema Extension

**File to modify:** `src/knowledge_mcp/config/discovery.py`

**Change:** Add `owner` field to `DatasetManifestEntry`.

```python
@dataclass(slots=True)
class DatasetManifestEntry:
    name: str
    source: str
    type: str = "custom"
    scope: str = "repo"
    visibility: str = "private"
    domains: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    required_grants: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    owner: str = ""                  # NEW: council slug that owns this dataset
```

**Change in `discover_datasets_manifest()`:** Parse `owner` field from YAML.

```python
entries.append(
    DatasetManifestEntry(
        ...,
        owner=str(item.get("owner") or "").strip(),  # NEW
    )
)
```

**Example datasets.yaml (target):**

```yaml
datasets:
  - name: "fire-red-lore"
    source: "/path/to/ai_chunks"
    type: "corpus"
    scope: "repo"
    visibility: "private"
    owner: "rom_lab"                  # NEW: council that owns this dataset
    domains: [pokemon, battle, navigation, progression]
    tags: [fire-red, gen-1]
    metadata:
      game: "pokefirered"
```

### 3.6 Database Schema Extension

**File to add:** `db/schema_knowledge_only/knowledge/tables/041_dataset_registry_owner.sql`

```sql
-- Dataset owner binding (council slug, soft reference)
ALTER TABLE knowledge.knowledge_datasets
    ADD COLUMN IF NOT EXISTS owner_slug TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_knowledge_datasets_owner
    ON knowledge.knowledge_datasets(owner_slug)
    WHERE owner_slug != '';
```

**Why text column, not UUID FK:** Knowledge MCP must work standalone. The council identity is a soft label (text slug like `"rom_lab"`), not a UUID foreign key to council_mcp's `persona_profiles` table. This decouples Knowledge MCP from council_mcp's database schema.

**Change in `_auto_register_datasets()`** (server.py:95-139): Pass `owner` from manifest entry to `register_dataset()`, store in `owner_slug` column.

### 3.7 Service Layer Changes

**Files to modify:**
- `src/knowledge_mcp/services/search_service.py`
- `src/knowledge_mcp/services/query_service.py`

**Change:** Pass `payload` (which now may contain `datasets`) through to `build_retrieval_request()`. Both services already accept a `payload` parameter and pass it through — the only change needed is that `build_retrieval_request()` extracts the new `datasets` field (handled in 3.2).

The service layer changes are minimal because the `payload` dict is already passed through. The `datasets` field extraction happens inside `build_retrieval_request()`, not in the service layer.

### 3.8 Dataset Auto-Scoping via Owner (Phase 2)

**Concept:** When a caller provides `scope=repo` and no explicit `datasets` param, but their `ActorContext.council_tags` contains `"rom_lab"`, the system can auto-resolve datasets owned by `"rom_lab"` and implicitly restrict results.

**Implementation path:**
1. Query `knowledge_datasets WHERE owner_slug IN (actor.council_tags)` to get dataset names.
2. Populate `RetrievalRequest.datasets` with those names.
3. Caller gets auto-scoped results without specifying `datasets=` explicitly.

**This is Phase 2 work.** Phase 1 requires explicit `datasets=` parameter. Auto-scoping requires the owner column to be populated and a reliable council_tags injection path.

---

## 4. FAISS Sharding Strategy
<!-- ID: data_flow -->

### Phase 1: Shared Shard + Metadata Filter (Ship First)

**Shard model:** All datasets remain in `repo-{workspace}` shard. Dataset identity is carried in:
- `faiss_embeddings.tags[]` as `"dataset:{name}"` (GIN-indexed, filterable via SearchFilters)
- `faiss_embeddings.metadata` JSONB as `{"dataset_name": "{name}"}` (used by `_result_allowed()`)

**Query flow:**
1. FAISS `index.search(vectors, k)` returns top-k from ALL vectors in shard
2. `_hydrate_results()` fetches full records from DB
3. `_result_allowed()` filters by `metadata["dataset_name"]`
4. Effective results may be fewer than k (post-filter reduction)

**Mitigation for k-reduction:** Over-fetch by requesting `k * 2` when `datasets` filter is active. The multiplier can be tuned based on dataset size ratios.

**Re-indexing requirement:** Existing fire-red data must be re-indexed to add `dataset_name` to metadata and tags. This is a one-time operation using `index.run` with the fire-red-lore dataset.

### Phase 2: Per-Dataset Shard (Future Optimization)

**Shard model:** Each dataset gets its own shard: `repo-{workspace}-{dataset_name}`.

**Change to `_scope_shard()`:**
```python
def _scope_shard(scope: str, workspace: str, dataset_name: str = "") -> str:
    slug = _workspace_slug(workspace)
    if scope == "global":
        return "shared"
    base = f"council-{slug}" if scope == "council" else f"repo-{slug}"
    if dataset_name:
        ds_slug = _workspace_slug(dataset_name)
        return f"{base}-{ds_slug}"
    return base
```

**Multi-shard search:** When `datasets=["fire-red-lore", "repo-docs"]`, search both shards and merge results:
```python
def _search_faiss_multi(self, request, dataset_names):
    all_results = []
    for name in dataset_names:
        shard = _scope_shard(request.scope, request.workspace, name)
        results = self._search_faiss_single(request, shard)
        all_results.extend(results)
    return self._dedupe_results(sorted(all_results, key=lambda r: r["score"], reverse=True))
```

**This is Phase 2+ work.** Not designed in detail here; will require its own sub-plan when Phase 1 is proven.

---

## 5. Council Integration Path
<!-- ID: api_design -->

### How Councils Claim Datasets

1. **Config-driven:** Council author adds `owner: "rom_lab"` to their dataset entry in `.knowledge/datasets.yaml`.
2. **Registration:** At server startup, `_auto_register_datasets()` reads `owner` field and stores as `owner_slug` in `knowledge_datasets` table.
3. **At query time:** `_result_allowed()` can check `metadata["owner"]` against `actor.council_tags` for visibility enforcement.

### Council Tags Flow

```
Caller (rom_lab agent) -> MCP call with _meta.council_id="rom_lab"
  -> ws_proxy injects council identity (future integration)
  -> dispatch() reads council_tags from ActorContext
  -> ActorContext(council_tags={"rom_lab"})
  -> Retrieval: datasets auto-resolved from knowledge_datasets WHERE owner_slug="rom_lab"
```

**Current state:** `ActorContext.council_tags` field EXISTS (verified at contracts.py:17) but is never populated by `dispatch()`. The `dispatch()` function at server.py:65-74 creates `ActorContext(persona_id=persona_id, runtime_grants=runtime_grants or set())` — no `council_tags`.

**Future change (Phase 2):** Populate `council_tags` in `dispatch()` from payload metadata (`payload.get("_meta", {}).get("council_tags")`) or from a dedicated parameter.

### Dataset Sharing Between Councils

Future capability. Design hooks:
- `visibility: "council"` + `owner: "rom_lab"` = only rom_lab sees it
- `visibility: "public"` + `owner: "rom_lab"` = anyone can search it
- `required_grants: ["knowledge:pokemon"]` = only callers with this grant see it

All three mechanisms already exist in the schema and `_result_allowed()` filter. The missing piece is populating the metadata correctly at index time.

---

## 6. Security Considerations
<!-- ID: security_considerations -->

### Threat Model

1. **Cross-dataset data leakage:** A caller without dataset access sees results from restricted datasets.
   - **Mitigation:** `_result_allowed()` is the single enforcement point. Dataset filter check is added FIRST (fail-fast). Empty `request.datasets` means no filter (backward compatible).

2. **Dataset enumeration:** A caller can call `list_datasets()` and see all dataset names.
   - **Mitigation:** `list_datasets` already filters by workspace. Owner-based filtering can be added in Phase 2 to hide datasets from non-owning councils.

3. **Bypass via omitting datasets param:** A caller omits `datasets=` and gets all results.
   - **Phase 1 behavior:** This is intentional — backward compatibility. No implicit restriction.
   - **Phase 2 behavior:** Auto-scoping via council_tags will implicitly restrict when council identity is available.

### Principle: Fail-Open in Phase 1, Fail-Closed in Phase 2

Phase 1 adds opt-in dataset filtering. Callers who don't use `datasets=` get current behavior (all datasets). Phase 2 adds auto-scoping that restricts by default when council identity is present.

---

## 7. Future Extensibility
<!-- ID: deployment_strategy -->

### Designed For But Not Implemented

1. **Dataset hierarchy (project > council > global):** The `scope` field on `knowledge_datasets` already has `repo/council/global` values. These can map to visibility tiers where `global` datasets are visible to all workspaces.

2. **Federation (push/share datasets):** A council publishes its dataset by re-indexing to the central server's shared shard. The `datasets.register` API route already exists. Federation requires a `workspace` override parameter on `index.run`.

3. **Global datasets:** `scope=global` + `visibility=public` on a dataset makes it searchable from any workspace. The existing `_scope_shard("global", workspace)` returns `"shared"` shard. Global datasets would be indexed into the shared shard.

4. **ContextVar injection:** When council_mcp integration matures, a `_request_datasets` ContextVar can provide automatic dataset scoping without tool parameter changes. This complements (not replaces) the explicit parameter approach.

5. **Per-workspace rag_profile:** Currently rag_profile.yaml is loaded once at server startup. Per-workspace profiles would require either (a) multiple profiles per `.knowledge/` dir keyed by workspace, or (b) API-based profile override per request.

---

## 8. Files Modified Summary

| File | Change | Lines Affected (approx) |
|------|--------|------------------------|
| `src/knowledge_mcp/tools/search_sources.py` | Add `datasets` param | ~5 lines |
| `src/knowledge_mcp/tools/query_answer.py` | Add `datasets` param | ~5 lines |
| `src/knowledge_mcp/providers/retrieval.py` | Add `datasets` to RetrievalRequest, build_retrieval_request(), _result_allowed() | ~15 lines |
| `src/knowledge_mcp/providers/indexing.py` | Add dataset_name to FAISS metadata/tags, wire from options | ~20 lines |
| `src/knowledge_mcp/config/discovery.py` | Add `owner` to DatasetManifestEntry, parse from YAML | ~5 lines |
| `src/knowledge_mcp/server.py` | Pass owner to register_dataset() | ~3 lines |
| `src/knowledge_mcp/services/dataset_service.py` | Store owner_slug on registration | ~5 lines |
| `db/schema_knowledge_only/knowledge/tables/041_dataset_registry_owner.sql` | Add owner_slug column | NEW file (~5 lines SQL) |
| `.knowledge/datasets.yaml` | Add `owner` field to fire-red-lore entry | ~1 line |

**Total estimated changes:** ~65 lines across 9 files (8 modified, 1 new SQL migration file).

---

## 9. Research References

- RESEARCH_FAISS_SHARDING_20260222.md: FAISS shard architecture, _scope_shard() root cause, Options A/B/C analysis
- RESEARCH_DATASET_REGISTRY.md: Schema gaps, RetrievalRequest missing datasets field, _result_allowed() extension path
- RESEARCH_COUNCIL_INTEGRATION.md: CWD anchoring, ContextVar pattern, 3 architectural options, council_tags mechanism
