# Project Changelog

Use one section per curated project outcome.

## Entry Template
- `entry_id`: <yyyymmdd>:<slug>
- `entry_status`: draft|accepted|superseded
- `title`: <one concise outcome title>
- `summary`: <short human-readable outcome summary>
- `evidence_refs`:
  - <path-or-proof-reference>
## 20260927:binding-reliability-review-slice

- `entry_id`: `20260927:binding-reliability-review-slice`
- `entry_status`: `draft`
- `title`: Reviewable Scribe binding reliability foundation for 2.15.0
- `summary`: Publishes the current typed binding/context contracts, exact-session isolation tests, startup and token hot-path reductions, object-store probe separation, durability key coverage, and the evidence-backed RCA as a draft review slice. The durable binding integration, structured runtime failures, offline managed-document spool, Council adoption, and joint acceptance matrix remain open and are not claimed complete.
- `evidence_refs`:
  - `src/scribe_mcp/shared/execution_context.py`
  - `src/scribe_mcp/storage/models.py`
  - `tests/test_execution_context.py`
  - `tests/shared/test_actor_scoped_session_binding.py`
  - `research/RESEARCH_BINDING_RCA.md`
  - `BUG-2026-09-27-0009`
  - `BUG-2026-09-27-0010`
