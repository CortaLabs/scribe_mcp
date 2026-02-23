---
id: knowledge_mcp_v1_finalization-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 knowledge_mcp_v1_finalization"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 08:57:46 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — knowledge_mcp_v1_finalization
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-21 07:33:09 UTC

> Execution roadmap for knowledge_mcp_v1_finalization.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview

| Phase | Goal | Key Deliverables | Parallel? | Confidence |
|-------|------|------------------|-----------|------------|
| Phase 1 — FAISS-First Retrieval | Remove pgvector similarity search from retrieval path | `include_pgvector` default flipped, `_search_pgvector()` removed, search() rewritten | YES (independent) | 0.95 |
| Phase 2 — Frontmatter Parser | Port Vantiel YAML parser into indexing pipeline | `_strip_yaml_frontmatter()` in indexing.py, frontmatter metadata flows to chunks | YES (independent) | 0.95 |
| Phase 3 — Knowledge Schema Expansion | Add knowledge_sources and knowledge_ingestion_jobs tables | 2 new SQL files, dataset_service.py wired to new tables | YES (independent) | 0.90 |
| Phase 4 — Cleanup & Hardening | Remove dead code, fix known bugs, standardize config | council.py deleted, extension stubs catalog-only, answer() cap configurable | Depends on P1+P2 | 0.90 |
| Phase 5 — Integration Testing & V1 Verification | End-to-end validation of complete pipeline | Integration test suite, all 101+ tests pass, v1 acceptance criteria met | Depends on P1-P4 | 0.85 |

**Parallelization Strategy:** Phases 1, 2, and 3 touch completely independent files and can be assigned to separate coding agents simultaneously. Phase 4 depends on P1 and P2 completion (touches files modified by both). Phase 5 is the final gate requiring all prior phases.

**Critical Path:** P1 or P2 (whichever finishes last) → P4 → P5

**Estimated Total Scope:** ~600 lines changed across ~12 files, 5-8 new test files
<!-- ID: phase_0 -->
## Phase 1 — FAISS-First Retrieval

**Objective:** Enforce FAISS-only vector similarity search. PostgreSQL is used for metadata lookup only — never for `<=>` cosine similarity.

**Research Evidence:** RESEARCH_FAISS_ARCHITECTURE.md documents the violation at retrieval.py:147 (`include_pgvector: bool = True`) and retrieval.py:365-436 (`_search_pgvector()` method using `<=>` operator).

**Why This Phase Exists:** The current default behavior routes search through pgvector's cosine similarity operator, which violates the FAISS-first architecture constraint. This is the highest-priority fix because it affects every search query.

---

### Task Package 1.1: Flip `include_pgvector` Default to False

**Scope:** Change one default parameter value.
**Files to Modify:**
- `src/knowledge_mcp/providers/retrieval.py` — line 147

**Specifications:**
1. Change `include_pgvector: bool = True` to `include_pgvector: bool = False` at line 147 in the `search()` method signature
2. Verify no other call sites pass `include_pgvector=True` explicitly (search codebase)

**Verification:**
- [ ] `grep -r "include_pgvector" src/` shows only the definition and no `=True` overrides
- [ ] Existing tests in `tests/` still pass (no test should depend on pgvector search path)

**Out of Scope:** Do NOT remove the parameter entirely (Phase 4 handles deprecation path). Do NOT modify `_search_pgvector()` yet.

---

### Task Package 1.2: Rewrite `search()` to Remove pgvector Branch

**Scope:** Remove the pgvector similarity search branch from the main search flow.
**Files to Modify:**
- `src/knowledge_mcp/providers/retrieval.py` — lines 230-339 (`search()` method)

**Dependencies:** Task 1.1 must be complete first.

**Specifications:**
1. In the `search()` method (lines 230-339), remove the conditional branch that calls `_search_pgvector()` when `include_pgvector` is True
2. The search flow must be: FAISS similarity search → PostgreSQL metadata enrichment only
3. Keep `_search_faiss()` (lines 493-538) as the sole similarity search path
4. Keep `_enrich_chunks_with_document_metadata()` (lines 439-491) — this is correct pgvector usage (metadata lookup, not similarity)
5. The `include_pgvector` parameter should still exist but be ignored with a deprecation comment: `# DEPRECATED: pgvector similarity search removed in v1. Parameter kept for API compatibility.`

**Verification:**
- [ ] `search()` method no longer calls `_search_pgvector()` under any condition
- [ ] `search()` always routes through `_search_faiss()` for similarity
- [ ] `_enrich_chunks_with_document_metadata()` is still called for metadata enrichment
- [ ] `pytest tests/` — all existing tests pass
- [ ] Manual trace: calling `search(query="test", scope="repo")` produces results via FAISS path only

**Out of Scope:** Do NOT delete `_search_pgvector()` method body yet (Phase 4). Do NOT modify `_search_faiss()` internals. Do NOT touch indexing.py.

---

### Task Package 1.3: Add FAISS-First Retrieval Tests

**Scope:** New test file validating FAISS-only search behavior.
**Files to Create:**
- `tests/test_faiss_first_retrieval.py`

**Dependencies:** Task 1.2 must be complete.

**Specifications:**
1. Test that `search()` with default parameters uses FAISS path (mock `_search_faiss` and verify it's called)
2. Test that `search()` does NOT call `_search_pgvector()` under any parameter combination
3. Test that `_enrich_chunks_with_document_metadata()` is still called after FAISS search (metadata enrichment is valid)
4. Test that `include_pgvector=True` does NOT re-enable pgvector similarity (parameter is deprecated)
5. Use existing test patterns from `tests/test_provider_scaffold.py` for mocking conventions

**Verification:**
- [ ] `pytest tests/test_faiss_first_retrieval.py -v` — all tests pass
- [ ] At least 4 test functions covering the above scenarios
- [ ] No new dependencies added

**Out of Scope:** Do NOT write integration tests that require a running FAISS index (Phase 5). Do NOT modify any source files.

---

**Phase 1 Acceptance Criteria:**
- [ ] `include_pgvector` defaults to `False`
- [ ] `search()` never calls `_search_pgvector()` regardless of parameters
- [ ] `_search_faiss()` is the sole similarity search path
- [ ] Metadata enrichment via PostgreSQL still works
- [ ] All 101+ existing tests pass
- [ ] New test file with 4+ tests passes
- [ ] No changes to indexing.py or server.py
<!-- ID: phase_1 -->
## Phase 2 — Frontmatter Parser Integration

**Objective:** Port the Vantiel YAML frontmatter parser into the indexing pipeline so that markdown files with `---` frontmatter blocks have metadata extracted and stored as chunk front_matter, while the body text excludes the YAML block.

**Research Evidence:** RESEARCH_VANTIEL_FRONTMATTER.md documents the parser at GPT_Manager/filesystem.py:164-216. RESEARCH_INGESTION_PIPELINE.md confirms the gap at indexing.py:518 (raw `path.read_text()` with no frontmatter stripping).

**Why This Phase Exists:** Markdown files with YAML frontmatter currently get indexed with the `---` block as body text, polluting search results and losing structured metadata (title, tags, category, etc.).

---

### Task Package 2.1: Add Frontmatter Parser Functions to indexing.py

**Scope:** Port two functions from Vantiel into indexing.py as private helpers.
**Files to Modify:**
- `src/knowledge_mcp/providers/indexing.py` — add near top of file (after imports, before class definitions)

**Source Reference:** Copy from `/home/austin/projects/GPT_Manager/src/gpt_manager/filesystem.py` lines 164-216.

**Specifications:**
1. Add `_quote_unescaped_values(text: str) -> str` — exact port of lines 164-182
   - Takes raw YAML text, quotes values containing unescaped colons
   - Returns sanitized YAML string safe for `yaml.safe_load()`
2. Add `_strip_yaml_frontmatter(text: str) -> tuple[dict, str]` — adapted from `parse_front_matter()` lines 185-216
   - Rename from `parse_front_matter` to `_strip_yaml_frontmatter` for clarity
   - Two-stage parsing: try `yaml.safe_load()` first, fall back to `_quote_unescaped_values()` then retry
   - Returns `(metadata_dict, body_without_frontmatter)`
   - On any error, returns `({}, original_text)` — never raises
   - Supported fields (from research): id, slug, title, doc_type/type, category, tags, core_nodes, crosslinks, audited_for, version, last_updated, author/created_by/maintained_by, status, summary, updates
3. `import yaml` is already available (PyYAML in dependencies) — verify, do not add new dependency
4. Add `import re` if not already imported (needed for `_quote_unescaped_values`)

**Verification:**
- [ ] Both functions exist in indexing.py
- [ ] `_strip_yaml_frontmatter("---\ntitle: Test\ntags: [a, b]\n---\nBody text")` returns `({"title": "Test", "tags": ["a", "b"]}, "Body text")`
- [ ] `_strip_yaml_frontmatter("No frontmatter here")` returns `({}, "No frontmatter here")`
- [ ] `_strip_yaml_frontmatter("")` returns `({}, "")`

**Out of Scope:** Do NOT wire into the indexing pipeline yet (Task 2.2). Do NOT modify any existing functions. Do NOT add new dependencies.

---

### Task Package 2.2: Wire Frontmatter Parser into Standard Text Indexing Path

**Scope:** Integrate `_strip_yaml_frontmatter()` into the file reading path at indexing.py:510-570.
**Files to Modify:**
- `src/knowledge_mcp/providers/indexing.py` — lines 510-570 region (standard text file indexing)

**Dependencies:** Task 2.1 must be complete.

**Specifications:**
1. After `body = path.read_text(encoding="utf-8")` at line 518, add:
   ```python
   parsed_meta, body = _strip_yaml_frontmatter(body)
   ```
2. Merge `parsed_meta` into the `front_matter` dict that gets built from `options` (lines 527-537):
   ```python
   front_matter = {**parsed_meta, **front_matter}  # options override parsed metadata
   ```
   This ensures explicitly passed options take precedence over parsed frontmatter.
3. If `parsed_meta` contains a `title` key and no title was in `options`, use it for the document record
4. Pass `frontmatter_offset=len(frontmatter_lines)` to `reindex_document()` if AgentKit supports it (verify — research says this parameter controls line number offset for chunk positioning)

**Verification:**
- [ ] Indexing a markdown file with `---` frontmatter extracts metadata into `front_matter` dict
- [ ] Indexing a markdown file without frontmatter works identically to before
- [ ] The body text passed to chunker does NOT contain the `---` block
- [ ] Existing tests pass unchanged
- [ ] `front_matter` dict from parsed YAML is merged correctly with options

**Out of Scope:** Do NOT modify JSONL ingestion path (already works correctly per research). Do NOT modify retrieval.py. Do NOT change the chunking algorithm.

---

### Task Package 2.3: Add Frontmatter Parser Tests

**Scope:** New test file for frontmatter parsing and integration.
**Files to Create:**
- `tests/test_frontmatter_parser.py`

**Dependencies:** Task 2.2 must be complete.

**Specifications:**
1. **Unit tests for `_strip_yaml_frontmatter()`:**
   - Standard frontmatter with title, tags, category
   - Frontmatter with unescaped colons in values (tests `_quote_unescaped_values` fallback)
   - No frontmatter (returns empty dict, full body)
   - Empty string input
   - Malformed YAML (returns empty dict, full body — never raises)
   - Frontmatter with all 14 supported fields
2. **Unit tests for `_quote_unescaped_values()`:**
   - Value with colon: `summary: This is: a test` → properly quoted
   - Value already quoted: no change
   - Multiple lines with mixed quoting needs
3. **Integration test with indexing pipeline:**
   - Mock file read to return markdown with frontmatter
   - Verify `front_matter` dict contains parsed metadata
   - Verify body text excludes `---` block

**Verification:**
- [ ] `pytest tests/test_frontmatter_parser.py -v` — all tests pass
- [ ] At least 8 test functions covering above scenarios
- [ ] No new dependencies added

**Out of Scope:** Do NOT test retrieval behavior. Do NOT test JSONL path.

---

**Phase 2 Acceptance Criteria:**
- [ ] `_strip_yaml_frontmatter()` and `_quote_unescaped_values()` exist in indexing.py
- [ ] Standard text file indexing path strips frontmatter before chunking
- [ ] Parsed metadata flows into `front_matter` dict on chunks
- [ ] Files without frontmatter index identically to current behavior
- [ ] All 101+ existing tests pass
- [ ] New test file with 8+ tests passes
- [ ] No changes to retrieval.py or server.py
- [ ] No new dependencies added (PyYAML already available)

---

## Phase 3 — Knowledge Schema Expansion

**Objective:** Add `knowledge.knowledge_sources` and `knowledge.knowledge_ingestion_jobs` tables to track data provenance and ingestion history.

**Research Evidence:** RESEARCH_FAISS_ARCHITECTURE.md provides SQL designs for both tables. RESEARCH_CODEBASE_AUDIT.md confirms current schema has only 2 tables (040_dataset_registry, 050_lore_graph).

**Why This Phase Exists:** The knowledge schema needs source tracking (where data came from) and ingestion job history (what was indexed, when, status) for operational visibility and debugging.

---

### Task Package 3.1: Create knowledge_sources Table

**Scope:** New SQL schema file for source tracking.
**Files to Create:**
- `db/schema_knowledge_only/knowledge/tables/042_knowledge_sources.sql`

**Specifications:**
1. Create table `knowledge.knowledge_sources` with columns:
   - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
   - `dataset_id UUID REFERENCES knowledge.knowledge_datasets(id) ON DELETE CASCADE`
   - `source_type TEXT NOT NULL` — enum-like: 'file', 'directory', 'jsonl', 'url', 'api'
   - `source_path TEXT NOT NULL` — filesystem path or URL
   - `source_hash TEXT` — SHA-256 of source content for change detection
   - `last_indexed_at TIMESTAMPTZ`
   - `chunk_count INTEGER DEFAULT 0`
   - `status TEXT NOT NULL DEFAULT 'pending'` — 'pending', 'indexed', 'failed', 'stale'
   - `metadata JSONB DEFAULT '{}'::jsonb`
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
2. Add index: `CREATE INDEX idx_knowledge_sources_dataset ON knowledge.knowledge_sources(dataset_id)`
3. Add index: `CREATE INDEX idx_knowledge_sources_status ON knowledge.knowledge_sources(status)`
4. Use `CREATE TABLE IF NOT EXISTS` for idempotency
5. File number 042 to slot between 040 (dataset_registry) and 050 (lore_graph)

**Verification:**
- [ ] SQL file exists at correct path
- [ ] `agentkit-schema plan` includes the new table (if DB available)
- [ ] All column types are valid PostgreSQL types
- [ ] Foreign key references knowledge.knowledge_datasets(id)

**Out of Scope:** Do NOT create migration files (agentkit-schema handles that). Do NOT modify existing SQL files.

---

### Task Package 3.2: Create knowledge_ingestion_jobs Table

**Scope:** New SQL schema file for ingestion job tracking.
**Files to Create:**
- `db/schema_knowledge_only/knowledge/tables/044_knowledge_ingestion_jobs.sql`

**Specifications:**
1. Create table `knowledge.knowledge_ingestion_jobs` with columns:
   - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
   - `dataset_id UUID REFERENCES knowledge.knowledge_datasets(id) ON DELETE CASCADE`
   - `source_id UUID REFERENCES knowledge.knowledge_sources(id) ON DELETE SET NULL`
   - `job_type TEXT NOT NULL` — 'full_reindex', 'incremental', 'single_file'
   - `status TEXT NOT NULL DEFAULT 'pending'` — 'pending', 'running', 'completed', 'failed'
   - `started_at TIMESTAMPTZ`
   - `completed_at TIMESTAMPTZ`
   - `chunks_created INTEGER DEFAULT 0`
   - `chunks_updated INTEGER DEFAULT 0`
   - `chunks_deleted INTEGER DEFAULT 0`
   - `error_message TEXT`
   - `metadata JSONB DEFAULT '{}'::jsonb`
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
2. Add index: `CREATE INDEX idx_ingestion_jobs_dataset ON knowledge.knowledge_ingestion_jobs(dataset_id)`
3. Add index: `CREATE INDEX idx_ingestion_jobs_status ON knowledge.knowledge_ingestion_jobs(status)`
4. Use `CREATE TABLE IF NOT EXISTS` for idempotency
5. File number 044 to slot between 042 (knowledge_sources) and 050 (lore_graph)

**Verification:**
- [ ] SQL file exists at correct path
- [ ] `agentkit-schema plan` includes the new table (if DB available)
- [ ] Foreign keys reference correct tables
- [ ] All column types are valid PostgreSQL types

**Out of Scope:** Do NOT create migration files. Do NOT modify existing SQL files. Do NOT wire into dataset_service.py yet.

---

### Task Package 3.3: Wire Schema into Dataset Service

**Scope:** Add methods to dataset_service.py for source and job CRUD.
**Files to Modify:**
- `src/knowledge_mcp/services/dataset_service.py`

**Dependencies:** Tasks 3.1 and 3.2 must be complete.

**Specifications:**
1. Add method `register_source(dataset_id: str, source_type: str, source_path: str, metadata: dict | None = None) -> dict`
   - Inserts into `knowledge.knowledge_sources`
   - Returns the created source record as dict
2. Add method `list_sources(dataset_id: str) -> list[dict]`
   - Returns all sources for a dataset
3. Add method `create_ingestion_job(dataset_id: str, source_id: str | None, job_type: str) -> dict`
   - Inserts into `knowledge.knowledge_ingestion_jobs` with status='pending'
   - Returns the created job record
4. Add method `update_ingestion_job(job_id: str, status: str, chunks_created: int = 0, chunks_updated: int = 0, error_message: str | None = None) -> dict`
   - Updates job status, sets `completed_at` if status in ('completed', 'failed')
   - Returns updated record
5. Use existing database connection patterns from the file (check with `scribe.read_file`)

**Verification:**
- [ ] All 4 methods exist in dataset_service.py
- [ ] Methods use parameterized queries (no SQL injection)
- [ ] Type annotations on all parameters and return values
- [ ] Existing dataset_service.py tests still pass

**Out of Scope:** Do NOT modify route handlers. Do NOT add new API endpoints. Do NOT modify indexing.py to call these methods (future work).

---

### Task Package 3.4: Add Schema and Service Tests

**Scope:** Tests for new schema tables and service methods.
**Files to Create:**
- `tests/test_knowledge_schema_expansion.py`

**Dependencies:** Task 3.3 must be complete.

**Specifications:**
1. Test `register_source()` creates a source record with correct fields
2. Test `list_sources()` returns sources for a specific dataset
3. Test `create_ingestion_job()` creates a job with 'pending' status
4. Test `update_ingestion_job()` transitions status and sets timestamps
5. Test foreign key constraints (source references valid dataset)
6. Use mocking for database layer if no test DB available

**Verification:**
- [ ] `pytest tests/test_knowledge_schema_expansion.py -v` — all tests pass
- [ ] At least 5 test functions
- [ ] No new dependencies

**Out of Scope:** Do NOT test SQL files directly (agentkit-schema handles validation).

---

**Phase 3 Acceptance Criteria:**
- [ ] `042_knowledge_sources.sql` exists with correct schema
- [ ] `044_knowledge_ingestion_jobs.sql` exists with correct schema
- [ ] dataset_service.py has 4 new methods for source/job CRUD
- [ ] All 101+ existing tests pass
- [ ] New test file with 5+ tests passes
- [ ] No changes to retrieval.py, indexing.py, or server.py

---

## Phase 4 — Cleanup & Hardening

**Objective:** Remove dead code, fix known bugs, standardize configuration, and prepare the codebase for v1 release.

**Research Evidence:** RESEARCH_BUG_AUDIT.md identifies orphaned adapters. RESEARCH_CODEBASE_AUDIT.md documents the answer() hardcoded cap and extension stub issues.

**Dependencies:** Phase 1 and Phase 2 must be complete (this phase touches files modified by both).

---

### Task Package 4.1: Delete Dead Adapters

**Scope:** Remove orphaned adapter files with 0% usage.
**Files to Delete:**
- `src/knowledge_mcp/adapters/council.py` — orphaned, 0% coverage per RESEARCH_BUG_AUDIT.md

**Files to Modify:**
- `src/knowledge_mcp/adapters/__init__.py` — remove any imports of council adapter

**Specifications:**
1. Delete `council.py` from adapters directory
2. Remove any references to council adapter from `__init__.py`
3. Search for any imports of council adapter across the codebase and remove them
4. Verify `scribe.py` adapter is NOT deleted — it may have legitimate future use (research says 0% coverage but doesn't recommend deletion)

**Verification:**
- [ ] `council.py` no longer exists in adapters/
- [ ] `grep -r "council" src/knowledge_mcp/adapters/` returns no references
- [ ] All existing tests pass
- [ ] No import errors when running `python -c "import knowledge_mcp"`

**Out of Scope:** Do NOT delete scribe.py adapter. Do NOT modify any service files.

---

### Task Package 4.2: Remove `_search_pgvector()` Method Body

**Scope:** Remove the now-unused pgvector similarity search method.
**Files to Modify:**
- `src/knowledge_mcp/providers/retrieval.py` — lines 365-436 (`_search_pgvector()` method)

**Dependencies:** Phase 1 (Task 1.2) must be complete — search() no longer calls this method.

**Specifications:**
1. Replace the entire `_search_pgvector()` method body with:
   ```python
   def _search_pgvector(self, *args, **kwargs):
       """REMOVED in v1: pgvector similarity search replaced by FAISS-first architecture."""
       raise NotImplementedError("pgvector similarity search removed in v1. Use FAISS search path.")
   ```
2. This preserves the method signature for any external callers while making it fail explicitly
3. Remove the `include_pgvector` parameter from `search()` method signature entirely (was deprecated in Phase 1)

**Verification:**
- [ ] `_search_pgvector()` raises `NotImplementedError` if called
- [ ] `search()` no longer has `include_pgvector` parameter
- [ ] All tests pass
- [ ] `grep "include_pgvector" src/` returns only the NotImplementedError docstring

**Out of Scope:** Do NOT modify `_search_faiss()`. Do NOT modify `_enrich_chunks_with_document_metadata()`.

---

### Task Package 4.3: Make answer() Evidence Cap Configurable

**Scope:** Remove hardcoded top-3 evidence cap in answer() method.
**Files to Modify:**
- `src/knowledge_mcp/providers/retrieval.py` — lines 342-353 (`answer()` method region)

**Specifications:**
1. Find the hardcoded evidence cap (top-3 slicing) in the `answer()` method
2. Replace with a parameter: `max_evidence: int = 3`
3. Add to method signature with default of 3 (preserves current behavior)
4. Use the parameter for slicing: `evidence[:max_evidence]`

**Verification:**
- [ ] `answer()` accepts `max_evidence` parameter
- [ ] Default behavior unchanged (still returns 3 by default)
- [ ] Passing `max_evidence=5` returns up to 5 evidence items
- [ ] Existing tests pass

**Out of Scope:** Do NOT make this configurable via config file (simple parameter is sufficient for v1).

---

### Task Package 4.4: Extension Routes — Catalog-Only Stubs

**Scope:** Ensure extension route stubs return proper catalog responses.
**Files to Modify:**
- `src/knowledge_mcp/api/routes/` — extension-related route file (verify exact file)

**Specifications:**
1. Verify `extensions.catalog` returns a valid response listing available extensions
2. Verify `extensions.reload` returns a proper "not implemented" response rather than crashing
3. If stubs are missing or broken, add minimal implementations that return structured JSON responses
4. All extension routes must still go through scope/permission policy checks

**Verification:**
- [ ] `extensions.catalog` returns valid JSON with extension list (may be empty)
- [ ] `extensions.reload` returns structured error/status response
- [ ] No crashes or unhandled exceptions from extension routes
- [ ] Existing tests pass

**Out of Scope:** Do NOT implement full extension loading. Do NOT add extension discovery beyond catalog.

---

**Phase 4 Acceptance Criteria:**
- [ ] council.py adapter deleted
- [ ] `_search_pgvector()` raises NotImplementedError
- [ ] `include_pgvector` parameter removed from `search()` signature
- [ ] `answer()` has configurable `max_evidence` parameter
- [ ] Extension stubs return proper responses
- [ ] All tests pass (101+ existing + new from P1-P3)
- [ ] `python -c "import knowledge_mcp"` succeeds

---

## Phase 5 — Integration Testing & V1 Verification

**Objective:** End-to-end validation that the complete indexing → search → answer pipeline works correctly with all Phase 1-4 changes integrated.

**Dependencies:** ALL previous phases must be complete.

---

### Task Package 5.1: Write Integration Test Suite

**Scope:** New integration test file testing the full pipeline.
**Files to Create:**
- `tests/test_v1_integration.py`

**Dependencies:** Phases 1-4 all complete.

**Specifications:**
1. **Indexing integration test:**
   - Create a temporary markdown file with YAML frontmatter
   - Index it through the standard indexing pipeline
   - Verify frontmatter is extracted (Phase 2 validation)
   - Verify chunks are created without frontmatter text in body
2. **Search integration test:**
   - Search for content in the indexed file
   - Verify results come through FAISS path only (Phase 1 validation)
   - Verify metadata enrichment includes frontmatter fields
3. **Schema integration test:**
   - Register a source via dataset_service
   - Create an ingestion job
   - Verify records exist in knowledge schema tables (Phase 3 validation)
4. **Answer integration test:**
   - Call answer() with a query matching indexed content
   - Verify evidence is returned with correct metadata
   - Test `max_evidence` parameter works (Phase 4 validation)
5. **Negative tests:**
   - Search with no FAISS index returns empty, not error
   - Indexing file without frontmatter works identically to pre-v1
   - Invalid source_type is rejected

**Verification:**
- [ ] `pytest tests/test_v1_integration.py -v` — all tests pass
- [ ] At least 8 integration test functions
- [ ] Tests are properly isolated (use temp directories, clean up after)

**Out of Scope:** Do NOT test deployment. Do NOT test Hetzner connectivity.

---

### Task Package 5.2: Run Full Test Suite and Document Results

**Scope:** Execute all tests and verify v1 acceptance.
**Files to Modify:**
- None (verification only)

**Dependencies:** Task 5.1 must be complete.

**Specifications:**
1. Run `pytest tests/ -v --tb=short` and capture full output
2. Verify all tests pass (target: 110+ tests, 0 failures)
3. Run `python -c "from knowledge_mcp.server import main; print('import OK')"` to verify clean imports
4. Verify no circular imports or missing dependencies
5. Document test count and any known limitations

**Verification:**
- [ ] `pytest tests/ -v` — 0 failures
- [ ] Total test count documented
- [ ] Import verification passes
- [ ] Any known limitations documented in CHECKLIST.md

---

**Phase 5 Acceptance Criteria:**
- [ ] Integration test suite with 8+ tests passes
- [ ] Full test suite passes with 0 failures
- [ ] Clean import verification
- [ ] All v1 goals from ARCHITECTURE_GUIDE.md met
- [ ] CHECKLIST.md fully updated with evidence
<!-- ID: milestone_tracking -->
## Milestone Tracking

| Milestone | Phase | Owner | Status | Evidence/Link |
|-----------|-------|-------|--------|---------------|
| FAISS-first default flipped | P1 - Task 1.1 | Coder Agent A | Pending | retrieval.py:147 |
| pgvector search branch removed | P1 - Task 1.2 | Coder Agent A | Pending | retrieval.py search() |
| FAISS-first tests pass | P1 - Task 1.3 | Coder Agent A | Pending | test_faiss_first_retrieval.py |
| Frontmatter parser ported | P2 - Task 2.1 | Coder Agent B | Pending | indexing.py top |
| Frontmatter wired into pipeline | P2 - Task 2.2 | Coder Agent B | Pending | indexing.py:518 region |
| Frontmatter tests pass | P2 - Task 2.3 | Coder Agent B | Pending | test_frontmatter_parser.py |
| knowledge_sources table created | P3 - Task 3.1 | Coder Agent C | Pending | 042_knowledge_sources.sql |
| ingestion_jobs table created | P3 - Task 3.2 | Coder Agent C | Pending | 044_knowledge_ingestion_jobs.sql |
| Dataset service wired | P3 - Task 3.3 | Coder Agent C | Pending | dataset_service.py |
| Schema tests pass | P3 - Task 3.4 | Coder Agent C | Pending | test_knowledge_schema_expansion.py |
| Dead adapters removed | P4 - Task 4.1 | Coder Agent D | Pending | adapters/council.py deleted |
| pgvector method gutted | P4 - Task 4.2 | Coder Agent D | Pending | retrieval.py _search_pgvector |
| answer() cap configurable | P4 - Task 4.3 | Coder Agent D | Pending | retrieval.py answer() |
| Extension stubs stable | P4 - Task 4.4 | Coder Agent D | Pending | api/routes/ extensions |
| Integration tests pass | P5 - Task 5.1 | Coder Agent E | Pending | test_v1_integration.py |
| Full suite green | P5 - Task 5.2 | Coder Agent E | Pending | pytest output |

**Agent Assignment Strategy:**
- **Agent A**: Phase 1 (FAISS-first) — touches only retrieval.py
- **Agent B**: Phase 2 (Frontmatter) — touches only indexing.py
- **Agent C**: Phase 3 (Schema) — touches only SQL files + dataset_service.py
- **Agents A/B/C run in parallel** — zero file overlap
- **Agent D**: Phase 4 (Cleanup) — starts after A and B complete
- **Agent E**: Phase 5 (Integration) — starts after all others complete
<!-- ID: retro_notes -->
## Retro Notes & Adjustments

### Pre-Implementation Notes
- Architecture designed from 6 verified research documents (~2,400 lines of research)
- All critical claims verified against actual source code before designing
- Zero discrepancies found between research and code reality
- Phase parallelization validated: P1/P2/P3 touch completely disjoint file sets
- Total scope estimated at ~600 lines changed, 5-8 new test files, 2 new SQL files

### Risk Register
| Risk | Mitigation | Severity |
|------|------------|----------|
| AgentKit `reindex_document()` doesn't support `frontmatter_offset` | P2 Task 2.2 spec says "verify and use if available" — graceful degradation | Low |
| FAISS multi-source_type filter silently drops results | Documented in RESEARCH_CODEBASE_AUDIT, deferred to post-v1 | Medium |
| Extension route stubs may have undocumented behavior | P4 Task 4.4 spec says "verify then fix" — investigation-first | Low |
| Database not available for schema testing | P3 Task 3.4 uses mocking as fallback | Low |

### Lessons Learned (Post-Implementation)
- *(To be filled after each phase completes)*
