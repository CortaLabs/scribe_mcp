---
id: knowledge_mcp_dataset_scoping-dataset-isolation-checklist
title: Dataset Isolation Checklist
doc_type: custom
doc_name: DATASET_ISOLATION_CHECKLIST
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 13:50:28 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Dataset Isolation Checklist

> **Project**: knowledge_mcp_dataset_scoping
> **Architecture**: DATASET_ISOLATION_ARCHITECTURE_GUIDE.md
> **Phase Plan**: DATASET_ISOLATION_PHASE_PLAN.md
> **Last Updated**: 2026-02-22
> **Status**: Pending Implementation

---

## Overview

This checklist provides verification criteria for each task package in the Dataset Isolation feature. Every item has a specific pass/fail test that can be executed by the Coder Agent and graded by the Review Agent.

**Grading Rule**: A phase is COMPLETE only when ALL items in that phase are checked. Partial completion blocks the next phase.

---

## Phase 1: Query-Time Dataset Filtering

### Task 1.1: Extend RetrievalRequest with datasets Field

<!-- ID: phase1_task1 -->

- [ ] **1.1.1**: `RetrievalRequest` dataclass at `src/knowledge_mcp/providers/retrieval.py` has a new field `datasets: list[str] = field(default_factory=list)`
  - **Verification**: `grep -n 'datasets.*list\[str\]' src/knowledge_mcp/providers/retrieval.py` returns a match inside the `RetrievalRequest` class
  - **Acceptance**: Field exists with correct type and empty-list default

- [ ] **1.1.2**: `build_retrieval_request()` extracts `datasets` from payload dict
  - **Verification**: Read `build_retrieval_request()` function body — must contain `payload.get("datasets", [])` or equivalent extraction
  - **Acceptance**: When payload contains `{"datasets": ["fire-red-lore"]}`, the returned `RetrievalRequest.datasets` equals `["fire-red-lore"]`

- [ ] **1.1.3**: When payload omits `datasets`, `RetrievalRequest.datasets` defaults to empty list
  - **Verification**: `pytest tests/test_retrieval_request_datasets.py::test_datasets_default_empty` passes
  - **Acceptance**: Empty list means "no dataset filter" — all results returned (backward compatible)

- [ ] **1.1.4**: All 177 existing tests still pass after this change
  - **Verification**: `pytest --tb=short -q` shows 177+ passed, 0 failed
  - **Acceptance**: Zero regressions

### Task 1.2: Add Dataset Filter to _result_allowed()

<!-- ID: phase1_task2 -->

- [ ] **1.2.1**: `_result_allowed()` at `src/knowledge_mcp/providers/retrieval.py` contains a dataset_name check as the FIRST filter (before doc_types, source_types, etc.)
  - **Verification**: Read `_result_allowed()` — first conditional block after function signature must check `req.datasets`
  - **Acceptance**: If `req.datasets` is non-empty and chunk metadata lacks matching `dataset_name`, return `False`

- [ ] **1.2.2**: Dataset filter extracts `dataset_name` from chunk metadata dict
  - **Verification**: Filter reads `chunk.get("metadata", {}).get("dataset_name", "")` or equivalent
  - **Acceptance**: Chunks with `metadata.dataset_name == "fire-red-lore"` pass when `req.datasets == ["fire-red-lore"]`

- [ ] **1.2.3**: Dataset filter also checks tags for `dataset:{name}` format
  - **Verification**: Filter checks `any(t.startswith("dataset:") and t.split(":", 1)[1] in req.datasets for t in tags)`
  - **Acceptance**: Chunks tagged `["dataset:fire-red-lore"]` pass when `req.datasets == ["fire-red-lore"]`

- [ ] **1.2.4**: Empty `req.datasets` means no filtering (all chunks pass dataset check)
  - **Verification**: `pytest tests/test_result_allowed_datasets.py::test_empty_datasets_passes_all` passes
  - **Acceptance**: Backward compatible — existing queries without datasets param return same results as before

- [ ] **1.2.5**: Dataset filter is fail-fast (returns False immediately, before more expensive checks)
  - **Verification**: Read `_result_allowed()` — dataset check is the first `if` block
  - **Acceptance**: Performance: dataset rejection happens before domain/grant/visibility checks

- [ ] **1.2.6**: All 177 existing tests still pass
  - **Verification**: `pytest --tb=short -q` shows 177+ passed, 0 failed
  - **Acceptance**: Zero regressions

### Task 1.3: Add datasets Parameter to MCP Tools

<!-- ID: phase1_task3 -->

- [ ] **1.3.1**: `search_sources` tool at `src/knowledge_mcp/tools/search_sources.py` has `datasets: list[str] | None = None` parameter
  - **Verification**: `grep -n 'datasets' src/knowledge_mcp/tools/search_sources.py` shows parameter in function signature
  - **Acceptance**: Parameter exists with correct type and None default

- [ ] **1.3.2**: `query_answer` tool at `src/knowledge_mcp/tools/query_answer.py` has `datasets: list[str] | None = None` parameter
  - **Verification**: `grep -n 'datasets' src/knowledge_mcp/tools/query_answer.py` shows parameter in function signature
  - **Acceptance**: Parameter exists with correct type and None default

- [ ] **1.3.3**: Both tools pass `datasets` into payload dict when non-None
  - **Verification**: Read tool functions — `if datasets: payload["datasets"] = datasets` present in both
  - **Acceptance**: Payload forwarding works for both tools

- [ ] **1.3.4**: `list_datasets` tool at `src/knowledge_mcp/tools/list_datasets.py` has `datasets: list[str] | None = None` parameter for filtering
  - **Verification**: `grep -n 'datasets' src/knowledge_mcp/tools/list_datasets.py` shows parameter
  - **Acceptance**: When provided, only matching datasets returned from registry

- [ ] **1.3.5**: Calling `search_sources(query="test")` without datasets param works identically to before
  - **Verification**: `pytest tests/test_tool_search_sources.py` passes (existing tests)
  - **Acceptance**: Backward compatible — None default means no filter

- [ ] **1.3.6**: All 177 existing tests still pass
  - **Verification**: `pytest --tb=short -q` shows 177+ passed, 0 failed
  - **Acceptance**: Zero regressions

---

## Phase 2: Indexing Pipeline Dataset Identity

### Task 2.1: Write Dataset Identity at Index Time

<!-- ID: phase2_task1 -->

- [ ] **2.1.1**: `_ingest_preformed_chunks_faiss()` at `src/knowledge_mcp/providers/indexing.py` accepts `dataset_name: str = ""` parameter
  - **Verification**: Read function signature — `dataset_name: str = ""` present
  - **Acceptance**: Parameter exists with empty-string default

- [ ] **2.1.2**: When `dataset_name` is non-empty, `dataset:{dataset_name}` tag is added to each chunk's tags
  - **Verification**: Read function body — tag construction logic for dataset present
  - **Acceptance**: `tags` list for each IngestRequest includes `"dataset:fire-red-lore"` when `dataset_name="fire-red-lore"`

- [ ] **2.1.3**: When `dataset_name` is non-empty, `metadata["dataset_name"] = dataset_name` is set on each chunk
  - **Verification**: Read function body — metadata assignment for dataset_name present
  - **Acceptance**: Each chunk's metadata dict contains `dataset_name` key

- [ ] **2.1.4**: When `dataset_name` is empty, no dataset tag or metadata is added (backward compatible)
  - **Verification**: `pytest tests/test_indexing_dataset_identity.py::test_empty_dataset_no_tag` passes
  - **Acceptance**: Pre-existing indexing behavior unchanged

- [ ] **2.1.5**: `_normalize_options()` result `dataset_names` list is used to populate `dataset_name` parameter
  - **Verification**: Read `run()` function — `dataset_names` from options flows to `_ingest_preformed_chunks_faiss(dataset_name=...)`
  - **Acceptance**: Options pipeline properly threads dataset identity to ingestion

- [ ] **2.1.6**: All 177 existing tests still pass
  - **Verification**: `pytest --tb=short -q` shows 177+ passed, 0 failed
  - **Acceptance**: Zero regressions

### Task 2.2: FAISS Search Filter Enhancement

<!-- ID: phase2_task2 -->

- [ ] **2.2.1**: `_search_faiss()` at `src/knowledge_mcp/providers/retrieval.py` adds `dataset:{name}` to SearchFilters.tags when `req.datasets` is non-empty
  - **Verification**: Read `_search_faiss()` — dataset tag injection into search filters present
  - **Acceptance**: FAISS search narrows to dataset-tagged vectors before scoring

- [ ] **2.2.2**: When `req.datasets` is empty, no dataset tags added to SearchFilters (backward compatible)
  - **Verification**: `pytest tests/test_faiss_search_datasets.py::test_no_dataset_filter_default` passes
  - **Acceptance**: Pre-existing FAISS search behavior unchanged

- [ ] **2.2.3**: Multi-dataset queries produce OR semantics (`dataset:a` OR `dataset:b`)
  - **Verification**: `pytest tests/test_faiss_search_datasets.py::test_multi_dataset_or_semantics` passes
  - **Acceptance**: `req.datasets=["a", "b"]` returns results from both datasets

- [ ] **2.2.4**: All 177 existing tests still pass
  - **Verification**: `pytest --tb=short -q` shows 177+ passed, 0 failed
  - **Acceptance**: Zero regressions

---

## Phase 3: Config and Schema Owner Binding

### Task 3.1: Extend DatasetManifestEntry with Owner Field

<!-- ID: phase3_task1 -->

- [ ] **3.1.1**: `DatasetManifestEntry` at `src/knowledge_mcp/config/discovery.py` has new field `owner: str = ""`
  - **Verification**: `grep -n 'owner' src/knowledge_mcp/config/discovery.py` shows field in dataclass
  - **Acceptance**: Field exists with empty-string default (standalone-safe)

- [ ] **3.1.2**: `discover_datasets_manifest()` correctly parses `owner` field from datasets.yaml
  - **Verification**: `pytest tests/test_dataset_manifest_owner.py::test_owner_parsed` passes
  - **Acceptance**: When datasets.yaml has `owner: "rom_lab"`, entry.owner == "rom_lab"

- [ ] **3.1.3**: Missing `owner` in datasets.yaml defaults to empty string (backward compatible)
  - **Verification**: `pytest tests/test_dataset_manifest_owner.py::test_owner_default_empty` passes
  - **Acceptance**: Existing datasets.yaml without owner field still parses correctly

- [ ] **3.1.4**: All 177 existing tests still pass
  - **Verification**: `pytest --tb=short -q` shows 177+ passed, 0 failed
  - **Acceptance**: Zero regressions

### Task 3.2: Add owner_slug to knowledge_datasets Table

<!-- ID: phase3_task2 -->

- [ ] **3.2.1**: Schema file `db/schema_knowledge_only/knowledge/tables/040_dataset_registry.sql` has `owner_slug TEXT DEFAULT ''` column
  - **Verification**: `grep -n 'owner_slug' db/schema_knowledge_only/knowledge/tables/040_dataset_registry.sql` returns match
  - **Acceptance**: Column exists with TEXT type and empty-string default

- [ ] **3.2.2**: `_auto_register_datasets()` in `src/knowledge_mcp/server.py` writes `owner` from manifest to `owner_slug` column
  - **Verification**: Read `_auto_register_datasets()` — INSERT/UPSERT includes `owner_slug`
  - **Acceptance**: After server startup with owner in datasets.yaml, DB row has correct owner_slug

- [ ] **3.2.3**: `agentkit-schema plan` shows the column addition (or has already been applied)
  - **Verification**: `agentkit-schema status` shows clean state or pending migration for owner_slug
  - **Acceptance**: Schema tooling recognizes the change

- [ ] **3.2.4**: All 177 existing tests still pass
  - **Verification**: `pytest --tb=short -q` shows 177+ passed, 0 failed
  - **Acceptance**: Zero regressions

---

## Phase 4: Testing and Re-indexing

### Task 4.1: Integration Test Suite

<!-- ID: phase4_task1 -->

- [ ] **4.1.1**: Test file `tests/test_dataset_isolation.py` exists with at least 8 test functions
  - **Verification**: `pytest tests/test_dataset_isolation.py --collect-only` shows 8+ collected tests
  - **Acceptance**: Comprehensive coverage of all dataset isolation paths

- [ ] **4.1.2**: Test: search with datasets param returns only matching dataset results
  - **Verification**: `pytest tests/test_dataset_isolation.py::test_search_with_dataset_filter` passes
  - **Acceptance**: Positive filtering works

- [ ] **4.1.3**: Test: search without datasets param returns all results (backward compat)
  - **Verification**: `pytest tests/test_dataset_isolation.py::test_search_no_dataset_filter` passes
  - **Acceptance**: No regression on existing behavior

- [ ] **4.1.4**: Test: query_answer with datasets param scopes retrieval
  - **Verification**: `pytest tests/test_dataset_isolation.py::test_query_with_dataset_filter` passes
  - **Acceptance**: Query service respects dataset scope

- [ ] **4.1.5**: Test: indexing with dataset_name writes correct tags and metadata
  - **Verification**: `pytest tests/test_dataset_isolation.py::test_index_writes_dataset_identity` passes
  - **Acceptance**: Indexed chunks carry dataset identity

- [ ] **4.1.6**: Test: multi-dataset query returns union of matching results
  - **Verification**: `pytest tests/test_dataset_isolation.py::test_multi_dataset_union` passes
  - **Acceptance**: OR semantics for multi-dataset queries

- [ ] **4.1.7**: Test: owner field parsed from datasets.yaml and written to DB
  - **Verification**: `pytest tests/test_dataset_isolation.py::test_owner_binding` passes
  - **Acceptance**: Config-to-DB pipeline for owner works

- [ ] **4.1.8**: Test: _result_allowed dataset check is first filter (ordering test)
  - **Verification**: `pytest tests/test_dataset_isolation.py::test_dataset_filter_order` passes
  - **Acceptance**: Performance: dataset rejection is fail-fast

### Task 4.2: Re-index Existing Data with Dataset Tags

<!-- ID: phase4_task2 -->

- [ ] **4.2.1**: Re-indexing fire-red-lore dataset applies `dataset:fire-red-lore` tag to all chunks
  - **Verification**: After re-index, query FAISS metadata for fire-red-lore chunks — all have dataset tag
  - **Acceptance**: Existing data now carries dataset identity

- [ ] **4.2.2**: After re-indexing, `search_sources(query="pikachu", datasets=["fire-red-lore"])` returns results
  - **Verification**: Manual test via MCP tool call
  - **Acceptance**: Dataset-scoped search works on real data

- [ ] **4.2.3**: After re-indexing, `search_sources(query="pikachu", datasets=["nonexistent"])` returns empty
  - **Verification**: Manual test via MCP tool call
  - **Acceptance**: Non-matching dataset correctly filters out all results

- [ ] **4.2.4**: After re-indexing, `search_sources(query="pikachu")` still returns results (no datasets = no filter)
  - **Verification**: Manual test via MCP tool call
  - **Acceptance**: Backward compatibility maintained on real data

---

## Cross-Cutting Verification

<!-- ID: cross_cutting -->

- [ ] **CC.1**: Full test suite passes: `pytest --tb=short -q` shows 177+ passed, 0 failed
  - **Acceptance**: Zero regressions across all phases

- [ ] **CC.2**: No new files created outside of `tests/` directory (existing files extended only)
  - **Verification**: `git diff --name-only --diff-filter=A` shows only test files as new
  - **Acceptance**: COMMANDMENT #0.5 respected — no replacement files

- [ ] **CC.3**: No LLM calls introduced (all logic is deterministic)
  - **Verification**: `grep -r 'llm_factory\|embed_text\|client.respond' src/knowledge_mcp/` returns no NEW matches
  - **Acceptance**: Phase 0 policy maintained

- [ ] **CC.4**: Knowledge MCP starts and serves without council_mcp running
  - **Verification**: Start knowledge_mcp standalone, call `search_sources` — works
  - **Acceptance**: Standalone constraint satisfied

- [ ] **CC.5**: `.knowledge/datasets.yaml` remains the primary config surface
  - **Verification**: All dataset metadata (name, source, type, scope, visibility, domains, tags, owner) configurable via datasets.yaml
  - **Acceptance**: No hardcoded dataset config in Python code

---

## Summary

| Phase | Total Items | Critical Items | Status |
|-------|-------------|----------------|--------|
| Phase 1: Query-Time Dataset Filtering | 16 | 6 (1.1.1, 1.2.1, 1.2.4, 1.3.1, 1.3.2, 1.3.5) | Pending |
| Phase 2: Indexing Pipeline Dataset Identity | 10 | 4 (2.1.1, 2.1.2, 2.1.3, 2.2.1) | Pending |
| Phase 3: Config & Schema Owner Binding | 8 | 3 (3.1.1, 3.1.3, 3.2.1) | Pending |
| Phase 4: Testing & Re-indexing | 12 | 4 (4.1.1, 4.1.2, 4.1.3, 4.2.1) | Pending |
| Cross-Cutting | 5 | 5 (all) | Pending |
| **TOTAL** | **51** | **22** | **Pending** |

---

## References

- Architecture: `DATASET_ISOLATION_ARCHITECTURE_GUIDE.md`
- Phase Plan: `DATASET_ISOLATION_PHASE_PLAN.md`
- Research: `research/RESEARCH_FAISS_SHARDING_20260222.md`
- Research: `research/RESEARCH_DATASET_REGISTRY.md`
- Research: `research/RESEARCH_COUNCIL_INTEGRATION.md`
