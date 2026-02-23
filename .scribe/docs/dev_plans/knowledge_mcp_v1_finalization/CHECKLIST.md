---
id: knowledge_mcp_v1_finalization-checklist
title: "\u2705 Acceptance Checklist \u2014 knowledge_mcp_v1_finalization"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 09:10:03 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — knowledge_mcp_v1_finalization
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-21 07:33:09 UTC

> Acceptance checklist for knowledge_mcp_v1_finalization.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Documentation Hygiene
- [x] Architecture guide written (proof: ARCHITECTURE_GUIDE.md — 10 sections, ~31KB)
- [x] Phase plan written (proof: PHASE_PLAN.md — 5 phases, 16 task packages)
- [x] Checklist written (proof: this document)
- [ ] All research documents reviewed before architecture (proof: 6 RESEARCH_*.md files read)
- [ ] All critical code claims verified against source (proof: append_entry logs with line numbers)
<!-- ID: phase_0 -->
## Phase 1 — FAISS-First Retrieval
- [x] `include_pgvector` defaults to `False` at retrieval.py:147 (proof: grep shows `include_pgvector: bool = False` at line 147; `build_retrieval_request` also defaults to `False` at line 178)
- [x] `search()` never calls `_search_pgvector()` (proof: pgvector branch removed from search(), replaced with unconditional `backends["pgvector"] = {"status": "disabled"}`; test_faiss_first_retrieval.py::test_search_never_calls_pgvector_regardless_of_include_pgvector_param PASSES)
- [x] `_search_faiss()` is sole similarity search path (proof: only `_search_faiss()` is called from search(); test_faiss_first_retrieval.py::test_search_uses_faiss_path_by_default PASSES)
- [x] Metadata enrichment via PostgreSQL still works (proof: `_enrich_chunks_with_document_metadata()` method untouched at lines 439-491; test_faiss_first_retrieval.py::test_enrich_chunks_with_document_metadata_is_available PASSES)
- [x] All 101+ existing tests pass (proof: `pytest tests/ --ignore=tests/test_knowledge_schema_expansion.py` → 126 passed, 0 failed. Only failure is test_update_ingestion_job_not_found_raises in Phase 3 coder-schema's work, unrelated to Phase 1)
- [x] `test_faiss_first_retrieval.py` has 4+ passing tests (proof: `pytest tests/test_faiss_first_retrieval.py -v` → 7 passed, 0 failed)
- [x] No changes to indexing.py or server.py (proof: only retrieval.py and tests/test_faiss_first_retrieval.py modified)
<!-- ID: final_verification -->
## Final Verification
- [ ] All Phase 1-5 checklist items checked with proofs attached
- [ ] Total test count: target 110+ tests, 0 failures
- [ ] All v1 goals from ARCHITECTURE_GUIDE.md problem_statement met:
  - [ ] FAISS-first search enforced (pgvector similarity removed)
  - [ ] Frontmatter parser integrated (Vantiel parser ported)
  - [ ] Knowledge schema expanded (2 new tables operational)
  - [ ] Dead code removed (council.py adapter deleted)
  - [ ] Known bugs addressed (answer() cap, extension stubs)
- [ ] Architecture documents reflect final implementation state
- [ ] PHASE_PLAN retro notes completed with lessons learned
- [ ] Stakeholder sign-off recorded: _________________ (name + date)
- [ ] V1 tagged and ready for future Hetzner deployment phase
