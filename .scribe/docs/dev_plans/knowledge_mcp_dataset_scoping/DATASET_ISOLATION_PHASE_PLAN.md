---
id: knowledge_mcp_dataset_scoping-dataset-isolation-phase-plan
title: 'Phase Plan: Dataset Isolation for Knowledge MCP'
doc_type: custom
doc_name: DATASET_ISOLATION_PHASE_PLAN
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 13:47:06 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Phase Plan: Dataset Isolation for Knowledge MCP

**Author:** ArchitectAgent
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-02-22
**Project:** knowledge_mcp_dataset_scoping
**Architecture Reference:** DATASET_ISOLATION_ARCHITECTURE_GUIDE.md

---

## Phase Overview

| Phase | Name | Scope | Dependencies | Est. Complexity |
|-------|------|-------|--------------|-----------------|
| 1 | Query-Time Dataset Filtering | retrieval.py, tools/*.py | None | Low |
| 2 | Indexing Pipeline Dataset Identity | indexing.py | None (parallel with Phase 1) | Low-Medium |
| 3 | Config & Schema: Owner Binding | discovery.py, server.py, dataset_service.py, SQL | Phase 1 | Low |
| 4 | Testing & Re-indexing | tests/, data re-index | Phases 1-3 | Medium |

**Total estimated effort:** 4 bounded coder sessions.

---

## Phase 1: Query-Time Dataset Filtering

**Goal:** Callers can pass `datasets=["fire-red-lore"]` to `search_sources` and `query_answer`, and results are filtered to only matching datasets.

**Prerequisite:** None. This phase is independent.

### Task Package 1.1: Add `datasets` field to RetrievalRequest and build_retrieval_request()

**Scope:** Add the datasets field to the request dataclass and wire extraction from payload.
**Files to Modify:** `src/knowledge_mcp/providers/retrieval.py`
**Dependencies:** None

#### Specifications

1. Add `datasets: list[str] = field(default_factory=list)` to `RetrievalRequest` dataclass (after `source_types` field, before the underscore-prefixed profile fields).
2. In `build_retrieval_request()`, after `source_types` extraction (line ~211), add:
   ```python
   datasets = _dedupe(_as_text_list(options.get("datasets") or options.get("dataset")))
   ```
3. Pass `datasets=datasets` into the `RetrievalRequest(...)` constructor.

#### Verification
- [ ] `RetrievalRequest(query="test", scope="repo", workspace="w", datasets=["ds1"]).datasets == ["ds1"]`
- [ ] `build_retrieval_request(query="q", scope="repo", workspace="w", actor_grants=set(), actor_roles=set(), payload={"datasets": ["fire-red-lore"]}).datasets == ["fire-red-lore"]`
- [ ] `build_retrieval_request(query="q", scope="repo", workspace="w", actor_grants=set(), actor_roles=set(), payload={}).datasets == []` (empty default)

#### Out of Scope
- Do NOT modify `_result_allowed()` in this task (that is Task 1.2)
- Do NOT modify any tool files
- Do NOT modify any service files

---

### Task Package 1.2: Add dataset filter to _result_allowed()

**Scope:** Add dataset_name check as the FIRST filter in `_result_allowed()`.
**Files to Modify:** `src/knowledge_mcp/providers/retrieval.py`
**Dependencies:** Task 1.1 (datasets field must exist on RetrievalRequest)

#### Specifications

1. In `_result_allowed()` method of `AgentKitRetrievalProvider`, add at the TOP of the method (immediately after `metadata = dict(result.get("metadata") or {})` on line 528):
   ```python
   # Dataset filter (most selective check, fail-fast)
   if request.datasets:
       result_dataset = str(metadata.get("dataset_name") or "").strip()
       if not result_dataset or result_dataset not in request.datasets:
           return False
   ```
2. All existing checks remain UNCHANGED below this new block.

#### Verification
- [ ] Result with `metadata={"dataset_name": "fire-red-lore"}` is allowed when `request.datasets=["fire-red-lore"]`
- [ ] Result with `metadata={"dataset_name": "cooking"}` is blocked when `request.datasets=["fire-red-lore"]`
- [ ] Result with `metadata={}` (no dataset_name) is blocked when `request.datasets=["fire-red-lore"]`
- [ ] Result with ANY metadata is allowed when `request.datasets=[]` (empty = no filter)
- [ ] All existing 177 tests still pass (regression check)

#### Out of Scope
- Do NOT modify tool signatures
- Do NOT modify indexing pipeline

---

### Task Package 1.3: Add `datasets` parameter to MCP tools

**Scope:** Add optional `datasets` parameter to `search_sources` and `query_answer` tool functions.
**Files to Modify:**
- `src/knowledge_mcp/tools/search_sources.py`
- `src/knowledge_mcp/tools/query_answer.py`
**Dependencies:** Task 1.1 (payload must be extractable)

#### Specifications

1. In `search_sources.py`, add parameter `datasets: list[str] | None = None` after the `debug` parameter. Add to payload:
   ```python
   if datasets:
       payload["datasets"] = datasets
   ```
2. In `query_answer.py`, add parameter `datasets: list[str] | None = None` after the `limit` parameter. Add to payload:
   ```python
   if datasets:
       payload["datasets"] = datasets
   ```
3. Update docstrings for both tools to mention the `datasets` parameter.

#### Verification
- [ ] `search_sources(query="test", datasets=["fire-red-lore"])` dispatches with `payload["datasets"] == ["fire-red-lore"]`
- [ ] `search_sources(query="test")` dispatches WITHOUT `datasets` key in payload (backward compat)
- [ ] `query_answer(question="test", datasets=["fire-red-lore"])` dispatches with `payload["datasets"] == ["fire-red-lore"]`
- [ ] All existing tests still pass

#### Out of Scope
- Do NOT modify `list_datasets` tool in this task
- Do NOT modify `index_plan` or `index_run` tools

---

### Phase 1 Milestone

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `datasets` param on search_sources tool | | Tool signature updated |
| `datasets` param on query_answer tool | | Tool signature updated |
| RetrievalRequest.datasets field exists | | Dataclass field added |
| build_retrieval_request extracts datasets | | Payload extraction verified |
| _result_allowed filters by dataset_name | | Unit tests pass |
| All 177 existing tests pass | | `pytest` clean run |

---

## Phase 2: Indexing Pipeline Dataset Identity

**Goal:** When indexing, write `dataset_name` into FAISS metadata and tags so Phase 1 filtering works on real data.

**Prerequisite:** None (can be done in parallel with Phase 1, but Phase 1 must ship first for filtering to be testable).

### Task Package 2.1: Add dataset_name to FAISS JSONL ingestion

**Scope:** Modify `_ingest_preformed_chunks_faiss()` to accept and write dataset_name.
**Files to Modify:** `src/knowledge_mcp/providers/indexing.py`
**Dependencies:** None

#### Specifications

1. Add `dataset_name: str = ""` parameter to `_ingest_preformed_chunks_faiss()` (after `faiss_batch_size`).
2. Inside the chunk loop, after domain tag addition (line ~915), add:
   ```python
   if dataset_name:
       chunk_tags.append(f"dataset:{dataset_name}")
   ```
3. Inside the chunk loop, after `chunk_metadata.update(chunk.metadata)` (line ~917), add:
   ```python
   if dataset_name:
       chunk_metadata["dataset_name"] = dataset_name
   ```

#### Verification
- [ ] Calling `_ingest_preformed_chunks_faiss(dataset_name="fire-red-lore", ...)` produces IngestRequests with `"dataset:fire-red-lore"` in tags
- [ ] Calling `_ingest_preformed_chunks_faiss(dataset_name="fire-red-lore", ...)` produces IngestRequests with `metadata["dataset_name"] == "fire-red-lore"`
- [ ] Calling `_ingest_preformed_chunks_faiss(dataset_name="", ...)` produces IngestRequests WITHOUT dataset tag or metadata key (backward compat)
- [ ] All existing tests pass

#### Out of Scope
- Do NOT modify the `run()` method call sites in this task (that is Task 2.2)
- Do NOT modify standard text file ingestion path

---

### Task Package 2.2: Wire dataset_name from run() to FAISS ingestion

**Scope:** Pass dataset_name from `_IndexPlanState.options["dataset_names"]` through to ingestion calls.
**Files to Modify:** `src/knowledge_mcp/providers/indexing.py`
**Dependencies:** Task 2.1

#### Specifications

1. In the `run()` method, locate where `_ingest_preformed_chunks_faiss()` is called (currently around line 930-939).
2. Before the FAISS ingestion call, resolve dataset_name:
   ```python
   # Resolve dataset_name for FAISS metadata
   dataset_names = state.options.get("dataset_names", [])
   active_dataset_name = dataset_names[0] if len(dataset_names) == 1 else ""
   ```
3. Pass `dataset_name=active_dataset_name` to `_ingest_preformed_chunks_faiss()`.
4. Also add dataset_name to the standard text file FAISS ingestion path (the `IngestRequest` construction around lines 689-699). Add `"dataset_name": active_dataset_name` to metadata dict and `f"dataset:{active_dataset_name}"` to tags list when `active_dataset_name` is non-empty.
5. For the pgvector ingestion path (`_ingest_preformed_chunks_pgvector`), add `"dataset_name": active_dataset_name` to `chunk_metadata` when non-empty. This ensures pgvector results also carry dataset identity.

#### Verification
- [ ] Running `index.run` with `dataset_names=["fire-red-lore"]` produces FAISS embeddings with `dataset:fire-red-lore` tag
- [ ] Running `index.run` without dataset_names produces embeddings WITHOUT dataset tag (backward compat)
- [ ] Running `index.run` with `dataset_names=["fire-red-lore"]` produces pgvector chunks with `metadata.dataset_name = "fire-red-lore"`
- [ ] All existing tests pass

#### Out of Scope
- Do NOT modify `_normalize_options()` (dataset_names is already parsed there)
- Do NOT modify `_resolve_dataset_sources()` (it already uses dataset_names for source resolution)

---

### Phase 2 Milestone

| Criterion | Status | Evidence |
|-----------|--------|----------|
| JSONL FAISS ingestion writes dataset_name | | IngestRequest metadata verified |
| JSONL FAISS ingestion writes dataset tag | | IngestRequest tags verified |
| Standard text FAISS ingestion writes dataset_name | | IngestRequest metadata verified |
| pgvector ingestion writes dataset_name | | chunk metadata verified |
| run() passes dataset_name from options | | Integration test |
| All existing tests pass | | `pytest` clean run |

---

## Phase 3: Config & Schema -- Owner Binding

**Goal:** datasets.yaml supports `owner` field. DB stores `owner_slug`. Registration propagates owner.

**Prerequisite:** Phase 1 complete (filtering must work before owner binding matters).

### Task Package 3.1: Extend DatasetManifestEntry and parsing

**Scope:** Add `owner` field to manifest entry dataclass and YAML parsing.
**Files to Modify:** `src/knowledge_mcp/config/discovery.py`
**Dependencies:** None

#### Specifications

1. Add `owner: str = ""` field to `DatasetManifestEntry` (after `metadata` field).
2. In `discover_datasets_manifest()`, in the DatasetManifestEntry constructor call, add:
   ```python
   owner=str(item.get("owner") or "").strip(),
   ```
3. Update `.knowledge/datasets.yaml` to add `owner: "rom_lab"` to the fire-red-lore entry.

#### Verification
- [ ] `discover_datasets_manifest()` parses `owner: "rom_lab"` from datasets.yaml
- [ ] `discover_datasets_manifest()` returns `entry.owner == ""` when no owner field in YAML
- [ ] All existing tests pass

#### Out of Scope
- Do NOT create the SQL migration in this task
- Do NOT modify server.py or dataset_service.py

---

### Task Package 3.2: Database schema extension and registration

**Scope:** Add owner_slug column to knowledge_datasets table. Update registration to store owner.
**Files to Modify:**
- `db/schema_knowledge_only/knowledge/tables/041_dataset_registry_owner.sql` (NEW file)
- `src/knowledge_mcp/server.py`
- `src/knowledge_mcp/services/dataset_service.py`
**Dependencies:** Task 3.1

#### Specifications

1. Create `db/schema_knowledge_only/knowledge/tables/041_dataset_registry_owner.sql`:
   ```sql
   -- Dataset owner binding (council slug, soft reference - not FK)
   ALTER TABLE knowledge.knowledge_datasets
       ADD COLUMN IF NOT EXISTS owner_slug TEXT NOT NULL DEFAULT '';
   
   CREATE INDEX IF NOT EXISTS idx_knowledge_datasets_owner
       ON knowledge.knowledge_datasets(owner_slug)
       WHERE owner_slug != '';
   ```
2. In `_auto_register_datasets()` (server.py:95-139), pass `owner=entry.owner` to the `register_dataset()` call.
3. In `register_dataset()` (dataset_service.py), include `owner_slug` in the INSERT statement. Use the ON CONFLICT clause to also update `owner_slug` on conflict.

#### Verification
- [ ] `agentkit-schema plan` shows the new column and index
- [ ] After `agentkit-schema apply`, `knowledge_datasets` has `owner_slug` column
- [ ] After server startup, fire-red-lore has `owner_slug = 'rom_lab'` in DB
- [ ] All existing tests pass

#### Out of Scope
- Do NOT implement auto-scoping logic (Phase 2 future work)
- Do NOT modify _result_allowed() for owner filtering

---

### Phase 3 Milestone

| Criterion | Status | Evidence |
|-----------|--------|----------|
| DatasetManifestEntry has `owner` field | | Dataclass field exists |
| datasets.yaml parsing extracts owner | | Unit test |
| SQL migration adds owner_slug column | | Schema plan verified |
| Registration stores owner_slug | | DB query after startup |
| fire-red-lore has owner_slug = 'rom_lab' | | DB query |
| All existing tests pass | | `pytest` clean run |

---

## Phase 4: Testing & Re-indexing

**Goal:** Comprehensive tests for dataset isolation. Re-index fire-red data with dataset_name metadata.

**Prerequisite:** Phases 1-3 complete.

### Task Package 4.1: Unit tests for dataset filtering

**Scope:** Add test module for dataset isolation behavior.
**Files to Modify:** `tests/test_dataset_isolation.py` (NEW file)
**Dependencies:** Phases 1-2

#### Specifications

1. Create `tests/test_dataset_isolation.py` with tests:
   - `test_result_allowed_with_dataset_filter`: Verify _result_allowed() filters correctly with datasets set
   - `test_result_allowed_without_dataset_filter`: Verify backward compat (empty datasets = all pass)
   - `test_result_allowed_no_dataset_metadata`: Verify results without dataset_name in metadata are filtered when datasets is set
   - `test_retrieval_request_datasets_field`: Verify dataclass field default and construction
   - `test_build_retrieval_request_datasets_extraction`: Verify payload extraction
   - `test_ingest_preformed_chunks_dataset_tag`: Verify dataset tag is added during ingestion (mock ingest_texts)
   - `test_ingest_preformed_chunks_dataset_metadata`: Verify dataset_name in metadata during ingestion
   - `test_manifest_entry_owner_field`: Verify DatasetManifestEntry owner parsing
   - `test_search_sources_tool_datasets_param`: Verify tool passes datasets to dispatch

2. Use the `test_agent` fixture from conftest.py for any persona-related tests.

#### Verification
- [ ] All new tests pass: `pytest tests/test_dataset_isolation.py -v`
- [ ] All existing 177 tests still pass: `pytest`
- [ ] No test persona pollution (uses test_agent fixture)

#### Out of Scope
- Do NOT write integration tests requiring live FAISS/DB (unit tests with mocks only)
- Do NOT re-index data in this task

---

### Task Package 4.2: Re-index fire-red data with dataset identity

**Scope:** Re-run indexing for fire-red-lore dataset so existing vectors get dataset_name metadata.
**Files to Modify:** None (operational task)
**Dependencies:** Phases 1-3 deployed

#### Specifications

1. Run `index.plan` with `dataset_names=["fire-red-lore"]` to create a plan.
2. Run `index.run` with the plan_id to re-index all fire-red JSONL chunks.
3. Verify indexed vectors have `dataset:fire-red-lore` tag and `metadata.dataset_name = "fire-red-lore"`.
4. Verify `search_sources(query="Brock's Onix", datasets=["fire-red-lore"])` returns results.
5. Verify `search_sources(query="Brock's Onix", datasets=["nonexistent"])` returns no results.

#### Verification
- [ ] FAISS embeddings for fire-red chunks have `dataset:fire-red-lore` in tags array
- [ ] FAISS embeddings for fire-red chunks have `dataset_name: fire-red-lore` in metadata JSONB
- [ ] `search_sources(query="...", datasets=["fire-red-lore"])` returns fire-red results only
- [ ] `search_sources(query="...", datasets=["nonexistent"])` returns empty results
- [ ] `search_sources(query="...")` (no datasets param) returns all results (backward compat)

#### Out of Scope
- Do NOT delete old embeddings (re-indexing overwrites via content_hash dedup)
- Do NOT modify any source code

---

### Phase 4 Milestone

| Criterion | Status | Evidence |
|-----------|--------|----------|
| test_dataset_isolation.py all tests pass | | pytest output |
| All 177+ tests pass (including new ones) | | pytest full run |
| fire-red data re-indexed with dataset_name | | DB query verification |
| Dataset-scoped search works end-to-end | | search_sources with datasets param |
| Backward compatibility preserved | | search without datasets param works |

---

## Dependency Graph

```
Phase 1 (Query Filtering)        Phase 2 (Indexing Identity)
  Task 1.1 ─────────────┐          Task 2.1
       │                │               │
       v                │               v
  Task 1.2              │          Task 2.2
       │                │               │
       v                │               │
  Task 1.3              │               │
       │                │               │
       └────────┬───────┘───────────────┘
                │
                v
          Phase 3 (Owner Binding)
            Task 3.1
                │
                v
            Task 3.2
                │
                v
          Phase 4 (Testing)
            Task 4.1
                │
                v
            Task 4.2
```

**Critical path:** 1.1 -> 1.2 -> 1.3 -> 3.1 -> 3.2 -> 4.1 -> 4.2
**Parallelizable:** Phase 2 (Tasks 2.1, 2.2) can run in parallel with Phase 1.

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| k-reduction in post-filter (fewer results than requested) | Medium | Low | Over-fetch with k*2 multiplier when datasets filter active |
| Existing tests break from RetrievalRequest change | Low | Medium | datasets field has empty list default; existing code never references it |
| Re-indexing takes too long | Low | Low | fire-red is ~2625 chunks, indexing is <5 min |
| faiss_embeddings unique constraint conflict during re-index | Low | Medium | ON CONFLICT handles dedup; same content_hash overwrites |
| SearchFilters.tags overlap semantics cause false positives | Low | Low | dataset filter is in _result_allowed(), not SearchFilters.tags |
