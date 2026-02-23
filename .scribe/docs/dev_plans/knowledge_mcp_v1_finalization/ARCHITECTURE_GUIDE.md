---
id: knowledge_mcp_v1_finalization-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 knowledge_mcp_v1_finalization"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 08:53:20 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — knowledge_mcp_v1_finalization
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-21 07:33:09 UTC

> Architecture guide for knowledge_mcp_v1_finalization.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement

**Context:** Knowledge MCP is a FastMCP-based RAG/indexing server providing 8 MCP tools for document retrieval, indexing, and dataset management. The codebase is architecturally sound (dispatcher-first routes, dual-backend indexing, scope/permission enforcement) but has 3 critical gaps that block v1 delivery:

1. **FAISS-first architecture violation** — The retrieval provider (`retrieval.py:252-272`) runs pgvector cosine similarity search (`<=>` operator) on every query by default, violating the hard constraint that FAISS is the ONLY search engine and pgvector is STORAGE ONLY.
2. **YAML frontmatter not parsed** — The indexing pipeline (`indexing.py:518`) reads markdown files raw with no frontmatter stripping. The `---` YAML block appears verbatim in chunk text, polluting RAG search results. All 14 Vantiel frontmatter fields are silently discarded.
3. **Knowledge schema too thin** — Only 2 domain tables exist (`knowledge_datasets`, `lore_entities/relationships`). No source provenance tracking, no ingestion job history, no document metadata overlay.

**Goals:**
- Enforce FAISS-first search: FAISS finds chunk IDs via vector similarity, PG does metadata lookup only
- Port Vantiel frontmatter parser: extract, strip, and store all 14 YAML fields as chunk metadata
- Expand knowledge schema: add tables for source tracking and ingestion job auditing
- Clean dead code: remove orphaned adapters, standardize config, fix remaining bugs
- Achieve v1 quality: all changes tested, documented, and verified

**Non-Goals:**
- Hetzner deployment (SSE transport, Dockerfile, docker-compose) — deferred post-v1
- LLM-assisted query expansion or summarization — Phase 1+ feature
- Extension route execution (handlers remain catalog stubs for v1)
- MetadataRegistry equivalent (`.knowledge/metadata.yaml` for per-project tag defaults)

**Success Metrics:**
- Zero pgvector similarity search calls in the retrieval path
- Frontmatter-bearing `.md` files produce chunks with no `---` lines in content
- All 14 frontmatter fields extractable and stored as chunk metadata
- `knowledge.knowledge_sources` and `knowledge.knowledge_ingestion_jobs` tables operational
- Test coverage increase from 54% toward 70%+ on modified modules

**Research Evidence:**
- RESEARCH_FAISS_ARCHITECTURE.md: pgvector violation at retrieval.py:365-436, confirmed by code inspection
- RESEARCH_INGESTION_PIPELINE.md: frontmatter gap at indexing.py:513-563, confirmed by code inspection
- RESEARCH_VANTIEL_FRONTMATTER.md: parser at GPT_Manager/filesystem.py:164-216, 14 fields documented
- RESEARCH_CODEBASE_AUDIT.md: full component status matrix, 2 blocking bugs, 3 non-blocking issues
- RESEARCH_BUG_AUDIT.md: 3 bugs fixed, 2 orphaned adapters, 54% coverage
- RESEARCH_DEPLOYMENT_READINESS.md: stdio transport ready, Hetzner blocked (deferred)
<!-- ID: requirements_constraints -->
## 2. Requirements and Constraints

**Hard Constraints (Non-Negotiable — from User):**
1. **FAISS-first search**: FAISS finds relevant chunk IDs via vector similarity. Direct PG lookup for metadata/content. pgvector is STORAGE ONLY. Remove all pgvector search paths from retrieval.
2. **Vantiel frontmatter parser**: Port `parse_front_matter()` and `_quote_unescaped_values()` from GPT_Manager. Use ALL 14 fields. Integrate into indexing pipeline.
3. **Dedicated knowledge schema**: knowledge_mcp shares the agentkit DB but gets its own `knowledge` schema for high-volume data.
4. **Modular for any codebase**: Any repo can plug in `.knowledge/datasets.yaml`, point at their docs, and get custom RAG. No hardcoded project-specific logic.
5. **No Hetzner deployment concern** — focus on code quality, architecture, and local Claude Code integration.
6. **Work packages must be parallelizable** — team of 3-5 coding agents working simultaneously.

**Functional Requirements:**
- FAISS search returns chunk IDs; PG enriches with metadata (no vector similarity in PG)
- Markdown frontmatter extracted, stripped from body, stored as chunk metadata
- 14 frontmatter fields: id, slug, title, doc_type/type, category, tags, core_nodes, crosslinks, audited_for, version, last_updated, author/created_by/maintained_by, status, summary, updates
- Knowledge sources tracked in dedicated schema table
- Ingestion jobs tracked with per-run stats (files processed, chunks created, errors)
- `frontmatter_offset` passed to `reindex_document()` for correct chunk line numbers

**Non-Functional Requirements:**
- Zero new third-party dependencies (PyYAML already installed)
- Backward compatibility: existing indexed data unaffected until re-indexed
- AgentKit is upstream read-only — NO modifications to agentkit code
- All changes must have test coverage

**Assumptions:**
- PostgreSQL with pgvector extension available (for storage)
- FAISS on-disk index files exist or will be built via `agentkit-faiss build`
- AgentKit `chunk_document(body, front_matter)` accepts frontmatter dict (verified in research)
- AgentKit `reindex_document()` accepts `frontmatter_offset` parameter (verified at indexer.py:83)
<!-- ID: architecture_overview -->
## 3. Architecture Overview

**Solution Summary:** Fix the retrieval path to be FAISS-only, add frontmatter parsing to the indexing pipeline, and expand the knowledge schema for source/job tracking. All changes are surgical edits to existing files — no new modules except 2 SQL schema files.

### Target Data Flow (Post-v1)

```
INDEXING FLOW (markdown file):
==============================
.md file on disk
    |
    v
path.read_text()                           [indexing.py:518]
    |
    v
parse_front_matter(body)                   [NEW: indexing.py — ported from Vantiel]
    |-- returns (stripped_body, fm_dict)
    |-- fm_dict has 14 fields: id, slug, title, doc_type, category, tags,
    |   core_nodes, crosslinks, audited_for, version, last_updated,
    |   author, status, summary
    v
merge fm_dict into front_matter            [indexing.py:527-537 — MODIFIED]
    |-- file frontmatter overrides option defaults for identity fields
    |-- option-level tags/domains ADDED to file tags (union, not replace)
    |-- confidence from fm → priority_tier mapping
    v
ensure_document_record()                   [indexing.py:545 — unchanged]
    |
    +---> reindex_document(body, front_matter, frontmatter_offset=N)  [pgvector STORAGE]
    |         chunk_document(body, front_matter) → embed → chunks/chunk_vectors
    |
    +---> chunk_document() + ingest_texts()                          [FAISS STORAGE + INDEX]
              IngestRequest per chunk → faiss_embeddings + .faiss file


SEARCH FLOW (FAISS-first):
===========================
query arrives at search()                  [retrieval.py:230]
    |
    v
_search_faiss(request)                     [retrieval.py:493 — now the ONLY search path]
    |-- embed query → vector
    |-- FAISS index.search(vector, k) → (scores[], faiss_ids[])
    |-- _fetch_embedding_records(shard_id, faiss_ids)
    |       → SELECT from faiss_embeddings WHERE faiss_id = ANY(ids)  [ID lookup, NOT similarity]
    v
_result_allowed(result, request)           [retrieval.py:540 — unchanged]
    |-- scope, visibility, grant, domain, tag filtering
    v
_enrich_chunks_with_document_metadata()    [retrieval.py:439 — unchanged, CORRECT pgvector usage]
    |-- SELECT from documents WHERE path = ANY(paths)  [path lookup, NOT similarity]
    v
_compute_quality_score()                   [retrieval.py:113 — unchanged]
    |-- weighted: embedding(0.55) + confidence(0.25) + source_type(0.10) + priority_tier(0.10)
    v
pipeline hooks (rerank, postprocess)       [pipeline.py — unchanged, dormant until hooks registered]
    v
return ranked results
```

### Component Map (Files Changed by Phase)

| File | Phase | Change Type | Lines Affected |
|------|-------|-------------|----------------|
| `src/knowledge_mcp/providers/retrieval.py` | P1 | **MAJOR** — remove pgvector search | ~150 lines removed/modified |
| `src/knowledge_mcp/providers/indexing.py` | P2 | **MAJOR** — add frontmatter parsing | ~80 lines added/modified |
| `db/schema_knowledge_only/knowledge/tables/060_knowledge_sources.sql` | P3 | **NEW** | ~30 lines |
| `db/schema_knowledge_only/knowledge/tables/070_ingestion_jobs.sql` | P3 | **NEW** | ~25 lines |
| `src/knowledge_mcp/services/dataset_service.py` | P3 | **MINOR** — wire source tracking | ~20 lines added |
| `src/knowledge_mcp/adapters/council.py` | P4 | **DELETE** or document stub | file deletion |
| `src/knowledge_mcp/adapters/scribe.py` | P4 | **DELETE** | file deletion |
| `tests/test_faiss_retrieval.py` | P1 | **NEW** | ~100 lines |
| `tests/test_frontmatter_ingestion.py` | P2 | **NEW** | ~120 lines |
| `tests/test_knowledge_schema.py` | P3 | **NEW** | ~60 lines |

### External Integrations

- **AgentKit** (upstream, read-only): `agentkit.faiss.search`, `agentkit.faiss.ingestion`, `agentkit.indexer`, `agentkit.chunker`, `agentkit.db`
- **PostgreSQL**: Shared `agentkit` DB with `public` schema (AgentKit base) + `knowledge` schema (knowledge_mcp domain)
- **FAISS**: On-disk `.faiss` index files per shard, managed by AgentKit FAISS engine
- **PyYAML**: Already installed, used for frontmatter parsing (no new dependency)
<!-- ID: detailed_design -->
## 4. Detailed Design

### 4.1 FAISS-First Retrieval (Phase 1)

**Goal:** Remove all pgvector similarity search from the retrieval path. FAISS is the only search engine.

**Changes to `src/knowledge_mcp/providers/retrieval.py`:**

1. **`RetrievalRequest` dataclass (line 147):** Change `include_pgvector: bool = True` to `include_pgvector: bool = False`

2. **`search()` method (lines 252-261):** Remove the `if request.include_pgvector` branch entirely. The pgvector search path should not execute. Replace with a comment explaining pgvector is storage-only.

3. **`_search_pgvector()` method (lines 365-436):** Delete this method entirely. It calls `agentkit.indexer.search_chunks()` which performs cosine similarity via `<=>` operator — this is the violation.

4. **Keep `_enrich_chunks_with_document_metadata()` (lines 439-491):** This is CORRECT — it does `SELECT FROM documents WHERE path = ANY(paths)`, which is a path-based lookup, not vector similarity. This remains the mechanism for enriching FAISS results with document-level metadata.

5. **`_search_faiss()` (lines 493-538):** Unchanged. This is already the correct FAISS-first pattern.

6. **Score normalization (lines 277-280):** Remove pgvector-specific normalization. Only FAISS scores need normalizing.

7. **`build_retrieval_request()` (lines 154-213):** Remove `include_pgvector` from payload parsing or hardcode to `False`.

8. **`answer()` method (lines 341-363):** Fix `matches[:3]` hardcoding — use `request.limit` or configurable `evidence_limit`. (Per RESEARCH_CODEBASE_AUDIT Finding ISSUE-4)

**Imports to remove:** `from agentkit.indexer import search_chunks` (line 367) — no longer needed after pgvector search removal.

**Test requirements:**
- Test that `search()` only calls FAISS, never pgvector
- Test that `include_pgvector=True` is either ignored or raises a deprecation warning
- Test that `_enrich_chunks_with_document_metadata()` still works for metadata enrichment
- Test answer() respects `request.limit` for evidence cap

---

### 4.2 Frontmatter Parser Integration (Phase 2)

**Goal:** Port Vantiel's `parse_front_matter()` and `_quote_unescaped_values()` into the indexing pipeline. Extract YAML frontmatter from markdown, strip it from body, store all 14 fields as chunk metadata.

**Changes to `src/knowledge_mcp/providers/indexing.py`:**

1. **Add `import yaml` at top** (if not already present — verify; config/discovery.py imports it but indexing.py may not)

2. **Add two module-level functions** (ported from GPT_Manager/filesystem.py:164-216):
   - `_quote_unescaped_values(raw_yaml: str) -> str` — sanitizes bare colons in YAML values
   - `parse_front_matter(text: str) -> tuple[dict[str, Any], str]` — splits frontmatter from body

   These are copied verbatim from the Vantiel codebase. Zero dependencies beyond `re`, `yaml`, `logging`.

3. **Modify standard text file path (lines 513-537):**

   After `body = path.read_text(encoding="utf-8")` (line 518), insert:
   ```python
   # Extract YAML frontmatter from markdown files
   file_front_matter: dict[str, Any] = {}
   frontmatter_line_count = 0
   if path.suffix.lower() in {".md", ".markdown"}:
       original_line_count = body.count("\n")
       file_front_matter, body = parse_front_matter(body)
       frontmatter_line_count = original_line_count - body.count("\n")
   ```

4. **Modify front_matter dict construction (lines 527-537):**

   Replace the current static dict with a merge of file frontmatter + option defaults:
   ```python
   file_tags = _as_text_list(file_front_matter.get("tags", []))
   front_matter = {
       "title": file_front_matter.get("title") or path.stem,
       "doc_type": file_front_matter.get("doc_type") or file_front_matter.get("type") or state.options["doc_type"],
       "category": file_front_matter.get("category") or state.options["category"],
       "tags": _dedupe(file_tags + base_tags),
       "domains": state.options["domains"],
       "visibility": state.options["visibility"],
       "required_grants": state.options["required_grants"],
       "workspace": state.workspace,
       "scope": state.scope,
       # Rich fields from frontmatter:
       "id": file_front_matter.get("id") or file_front_matter.get("slug"),
       "summary": file_front_matter.get("summary"),
       "core_nodes": _as_text_list(file_front_matter.get("core_nodes", [])),
       "crosslinks": _as_text_list(file_front_matter.get("crosslinks", [])),
       "audited_for": _as_text_list(file_front_matter.get("audited_for", [])),
       "status": file_front_matter.get("status"),
       "version": file_front_matter.get("version"),
       "author": file_front_matter.get("author") or file_front_matter.get("created_by") or file_front_matter.get("maintained_by"),
   }
   ```

   **Merge rule:** File frontmatter wins for identity fields (title, doc_type, category). Option-level tags/domains are ADDED (union). Option-level visibility/grants/workspace/scope always come from index options (not per-file overridable for security).

5. **Pass `frontmatter_offset` to `reindex_document()` (near line 567):**
   ```python
   reindex_document(
       project_slug=workspace,
       relative_path=relative_path,
       body=body,
       front_matter=front_matter,
       frontmatter_offset=frontmatter_line_count,  # NEW
   )
   ```

6. **Add priority_tier from frontmatter confidence (near line 538):**
   If `file_front_matter.get("confidence")` exists, use `_priority_tier()` to set tier in metadata — matching the JSONL chunk behavior already in the codebase.

**Test requirements:**
- `parse_front_matter()` with valid YAML — returns (dict, body)
- `parse_front_matter()` with no frontmatter — returns ({}, original_text)
- `parse_front_matter()` with malformed YAML — returns ({}, body_without_fence)
- `parse_front_matter()` with bare colons — sanitizer kicks in, parses successfully
- Integration: `.md` file with frontmatter indexed — verify chunks contain no `---` lines
- Verify `frontmatter_offset` is passed correctly (line number accuracy)
- Verify title from frontmatter overrides filename stem

---

### 4.3 Knowledge Schema Expansion (Phase 3)

**Goal:** Add source provenance and ingestion job tracking tables to the `knowledge` schema.

**New file: `db/schema_knowledge_only/knowledge/tables/060_knowledge_sources.sql`**

```sql
CREATE TABLE IF NOT EXISTS knowledge.knowledge_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_slug TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'repo',
    source_uri TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'filesystem',
    display_name TEXT NOT NULL,
    description TEXT,
    domains TEXT[] NOT NULL DEFAULT '{}',
    tags TEXT[] NOT NULL DEFAULT '{}',
    faiss_shard_name TEXT,
    visibility TEXT NOT NULL DEFAULT 'private',
    required_grants TEXT[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_indexed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_slug, source_uri)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_workspace ON knowledge.knowledge_sources(workspace_slug);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_scope ON knowledge.knowledge_sources(scope);
```

**New file: `db/schema_knowledge_only/knowledge/tables/070_ingestion_jobs.sql`**

```sql
CREATE TABLE IF NOT EXISTS knowledge.knowledge_ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES knowledge.knowledge_sources(id) ON DELETE SET NULL,
    workspace_slug TEXT NOT NULL,
    scope TEXT NOT NULL,
    plan_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    files_processed INTEGER NOT NULL DEFAULT 0,
    files_skipped INTEGER NOT NULL DEFAULT 0,
    chunks_created INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    errors JSONB NOT NULL DEFAULT '[]'::JSONB,
    options JSONB NOT NULL DEFAULT '{}'::JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_source ON knowledge.knowledge_ingestion_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_workspace ON knowledge.knowledge_ingestion_jobs(workspace_slug);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON knowledge.knowledge_ingestion_jobs(status);
```

**Changes to `src/knowledge_mcp/services/dataset_service.py`:**
- When `register_dataset()` is called, also upsert a `knowledge_sources` row linking the dataset to its source URI and workspace
- This is additive — existing logic unchanged, new INSERT added after dataset registration

---

### 4.4 Cleanup and Hardening (Phase 4)

**Goal:** Remove dead code, fix remaining minor bugs, standardize config access.

1. **Delete `src/knowledge_mcp/adapters/council.py`** — orphaned stub, `load_runtime_grants()` never called. Document in CLAUDE.md that runtime grants are caller-supplied.
2. **Delete `src/knowledge_mcp/adapters/scribe.py`** — dead code, `build_log_query()` never called.
3. **Fix FAISS multi-source_type filter warning** — `retrieval.py:496`: log warning when `len(request.source_types) > 1` before silently dropping to None.
4. **Document extension stub status** — Update CLAUDE.md to explicitly state extension route handlers are catalog-only in v1, execution deferred to v2.
5. **Update `adapters/__init__.py`** if it exports the deleted modules.

---

### 4.5 Integration Testing and V1 Verification (Phase 5)

**Goal:** Verify all phases work together end-to-end.

1. Run full test suite — all existing + new tests pass
2. Manual verification: index a markdown file with frontmatter, search via FAISS, verify chunks are clean
3. Verify schema migration: `agentkit-schema plan` shows new knowledge tables
4. Verify no pgvector similarity search in any code path (grep for `search_chunks` and `<=>`)
5. Coverage report: target 70%+ on modified modules
<!-- ID: directory_structure -->
## 5. Directory Structure

```
src/knowledge_mcp/
    __init__.py
    server.py                          # FastMCP entrypoint, tool registration, stdio transport
    api/
        dispatcher.py                  # RouteDispatcher — route registry + policy-aware dispatch
        context.py                     # KnowledgeContext builder
        routes/
            health.py                  # health.status
            query.py                   # query.answer
            search.py                  # search.sources
            index.py                   # index.plan, index.run
            datasets.py                # datasets.list, datasets.register
            relationships.py           # relationships.query, relationships.upsert
            permissions.py             # permissions.check
            admin.py                   # admin.describe
            extensions.py              # extensions.catalog, extensions.reload
    adapters/
        agentkit_db.py                 # DB connection wrapper, graceful degradation
        agentkit_knowledge.py          # HYBRID_RETRIEVER adapter (567 lines)
        filesystem.py                  # File candidate collection
        council.py                     # [P4: DELETE] — orphaned stub
        scribe.py                      # [P4: DELETE] — dead code
    config/
        discovery.py                   # Repo root, .council, .knowledge discovery
        settings.py                    # KnowledgeSettings dataclass
    extensions/
        registry.py                    # Extension manifest loading + stub handlers
    models/
        contracts.py                   # RouteRequest, RouteResponse, ActorContext
    policies/
        scopes.py                      # Scope validation (repo/council/global)
        permissions.py                 # Grant enforcement (knowledge:index/admin/global)
    providers/
        indexing.py                    # [P2: MODIFY] — add frontmatter parsing
        retrieval.py                   # [P1: MODIFY] — remove pgvector search
        pipeline.py                    # QueryPipelineHook protocol + runner
    services/
        dataset_service.py             # [P3: MODIFY] — wire source tracking
        index_service.py
        query_service.py
        search_service.py
        relationship_service.py
        extension_service.py
    tools/
        __init__.py                    # Eager import of all 8 MCP tools
        search_sources.py
        query_answer.py
        list_datasets.py
        index_plan.py
        index_run.py
        list_routes.py
        list_extensions.py
        dispatch_route.py

db/schema_knowledge_only/
    manifest.json                      # Generated by agentkit-schema tooling
    public/tables/                     # 15 AgentKit base tables (read-only reference)
    knowledge/tables/
        040_dataset_registry.sql       # knowledge_datasets table
        050_lore_graph.sql             # lore_entities + lore_relationships
        060_knowledge_sources.sql      # [P3: NEW] — source provenance
        070_ingestion_jobs.sql         # [P3: NEW] — ingestion job tracking

tests/
    conftest.py
    test_dispatcher.py
    test_extensions.py
    test_scope_policy.py
    test_provider_scaffold.py
    test_db_service_fallback.py
    test_indexing_dataset_sources.py
    test_dataset_autodiscovery.py
    test_agentkit_knowledge_adapter.py
    test_scoring.py
    test_pipeline.py
    test_jsonl_ingestion.py
    test_tool_registration.py
    test_faiss_retrieval.py            # [P1: NEW] — FAISS-only search tests
    test_frontmatter_ingestion.py      # [P2: NEW] — frontmatter parsing + integration
    test_knowledge_schema.py           # [P3: NEW] — schema validation
    bugs/
        test_2026_02_21_bug_audit.py   # Bug regression tests
```
<!-- ID: data_storage -->
## 6. Data and Storage

### PostgreSQL (shared agentkit DB)

**Public schema** (AgentKit-managed, read-only from knowledge_mcp perspective):
- `projects` — workspace/project registry
- `documents` — document records with path, title, doc_type, tags, front_matter JSONB
- `chunks` — chunk content with metadata JSONB, token_count, section_path
- `chunk_vectors` — embedding vectors per chunk (VECTOR(384))
- `vector_store` — pgvector index table (storage only, NOT used for search in v1)
- `faiss_shards` — FAISS shard registry (shard_name, embedding_dim, metric)
- `faiss_embeddings` — FAISS embedding metadata (faiss_id, source_ref, tags, metadata JSONB)
- `faiss_pending_updates`, `faiss_index_manifests` — FAISS housekeeping

**Knowledge schema** (knowledge_mcp-managed):
- `knowledge.knowledge_datasets` — dataset registry with workspace/scope/visibility/grants
- `knowledge.lore_entities` + `knowledge.lore_relationships` — knowledge graph
- `knowledge.knowledge_sources` — [NEW P3] source provenance tracking
- `knowledge.knowledge_ingestion_jobs` — [NEW P3] ingestion run history

### FAISS (on-disk)

- Index files at `{storage_root}/shards/{shard_name}/index.faiss`
- Shard naming: `repo-{workspace_slug}`, `council-{workspace_slug}`, `shared`
- Metric: cosine similarity (configurable in agentkit.yaml)
- Embedding dimension: 384 (all-MiniLM-L6-v2 local model)

### Storage Architecture Principle

pgvector stores vectors for durability and potential retraining. FAISS serves all search queries via on-disk index. PG is never used for vector similarity search — only for metadata lookups by ID or path after FAISS returns results.
<!-- ID: testing_strategy -->
## 7. Testing Strategy

### New Test Files

| Test File | Phase | Tests | Coverage Target |
|-----------|-------|-------|-----------------|
| `tests/test_faiss_retrieval.py` | P1 | FAISS-only search, no pgvector search calls, metadata enrichment, answer limit | retrieval.py 70%+ |
| `tests/test_frontmatter_ingestion.py` | P2 | parse_front_matter (valid/invalid/malformed/bare-colons), frontmatter merge, frontmatter_offset, integration with indexing | indexing.py 60%+ |
| `tests/test_knowledge_schema.py` | P3 | SQL file syntax validation, table existence after migration | schema files |

### Test Approach by Phase

**Phase 1 (FAISS-first):**
- Mock `agentkit.faiss.search.search` to return controlled SearchResult objects
- Assert `search_chunks` (pgvector similarity) is never called — use monkeypatch to verify
- Test `_enrich_chunks_with_document_metadata()` still works with FAISS results
- Test `answer()` respects `request.limit` instead of hardcoded `[:3]`

**Phase 2 (Frontmatter):**
- Unit test `parse_front_matter()` and `_quote_unescaped_values()` with edge cases
- Use `tmp_path` fixture to create test `.md` files with frontmatter
- Monkeypatch `reindex_document` and `ingest_texts` to capture arguments
- Verify `body` arg has no `---` lines, `front_matter` arg has extracted fields
- Verify `frontmatter_offset` matches expected line count

**Phase 3 (Schema):**
- Validate SQL syntax (parse with sqlparse or regex check for required clauses)
- Verify `CREATE TABLE IF NOT EXISTS` and index definitions are syntactically correct
- Full DB integration testing deferred (requires live postgres)

**Phase 4 (Cleanup):**
- Existing test suite must continue passing after adapter deletion
- Verify `import knowledge_mcp` doesn't fail with removed modules

**Phase 5 (Integration):**
- Full `pytest` run — all tests pass
- Grep verification: zero instances of `search_chunks` import in providers/
- Grep verification: zero instances of `<=>` operator in knowledge_mcp source
<!-- ID: deployment_operations -->
## 8. Deployment and Operations

**V1 Target: Local Claude Code Integration (stdio)**

Knowledge MCP runs as a local stdio process invoked by Claude Code. No remote deployment for v1.

**Local Setup:**
1. Install in uap environment: `pip install -e /home/austin/projects/MCP_SPINE/knowledge_mcp`
2. Set `DATABASE_URL` in `.env` pointing to local or Hetzner postgres
3. Add `.mcp.json` entry: `{"command": "knowledge-mcp", "env": {"DATABASE_URL": "..."}}`
4. Run `agentkit-schema plan` then `agentkit-schema apply` to ensure knowledge tables exist
5. Optionally build FAISS index: `agentkit-faiss build --shard repo-{workspace}`

**Post-V1 (Deferred):**
- SSE transport for Hetzner remote access (port 8202)
- Dockerfile following council_mcp deploy pattern
- Docker-compose service in Hetzner stack
- Health check endpoint for operational monitoring
<!-- ID: open_questions -->
## 9. Open Questions and Follow-Ups

| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should `include_pgvector` field be removed from RetrievalRequest entirely or kept as deprecated=False? | Architect | DECIDED | Keep field, default False, ignore if True. Removal can happen in v2. |
| HYBRID_RETRIEVER in agentkit_knowledge.py adapter — does it also use pgvector search? | Research | OPEN | The adapter path is not on the main search hot path for knowledge_mcp routes. Low priority for v1. |
| `.knowledge/metadata.yaml` for per-project tag defaults (like Vantiel's universal_metadata.yaml) | Architect | DEFERRED | Not needed for v1. Good v2 enhancement for frontmatter-driven dataset tagging. |
| Extension route execution model — stub vs invocable handlers | Architect | DECIDED | Catalog-only stubs for v1. Document explicitly. Execution model is v2. |
| council.py adapter — wire load_runtime_grants or delete? | Architect | DECIDED | Delete in P4. Document that grants are caller-supplied. Wire grant resolution from council sessions in v2. |
| Persistent plan cache (Redis/DB-backed) for durability across restarts | Architect | DEFERRED | In-memory plan cache acceptable for v1 (stdio process per session). |
<!-- ID: references_appendix -->
## 10. References and Appendix

### Research Documents (Source of Truth)
- `RESEARCH_FAISS_ARCHITECTURE.md` — pgvector violation, FAISS API, schema gaps
- `RESEARCH_INGESTION_PIPELINE.md` — frontmatter gap, indexing flow, dataset pipeline
- `RESEARCH_VANTIEL_FRONTMATTER.md` — parser implementation, 14 fields, portability assessment
- `RESEARCH_CODEBASE_AUDIT.md` — full component status matrix, blocking/non-blocking issues
- `RESEARCH_BUG_AUDIT.md` — 3 bugs fixed, 2 orphaned adapters, coverage analysis
- `RESEARCH_DEPLOYMENT_READINESS.md` — transport, schema, dependency, config analysis

### Key Source Files
- `src/knowledge_mcp/providers/retrieval.py` — FAISS-first changes (P1)
- `src/knowledge_mcp/providers/indexing.py` — frontmatter integration (P2)
- `src/knowledge_mcp/services/dataset_service.py` — source tracking wire-up (P3)
- `db/schema_knowledge_only/knowledge/tables/` — schema expansion (P3)
- `/home/austin/projects/GPT_Manager/src/gpt_manager/filesystem.py:164-216` — Vantiel parser source

### AgentKit API References
- `agentkit.faiss.search.search(SearchRequest)` — FAISS search entry point
- `agentkit.faiss.ingestion.ingest_texts([IngestRequest])` — FAISS ingestion
- `agentkit.indexer.reindex_document(project_slug, path, body, front_matter, frontmatter_offset)` — document indexing
- `agentkit.chunker.chunk_document(body, front_matter)` — heading-aware chunking

---
*Architecture Guide v1.0 — ArchitectAgent — 2026-02-21*
