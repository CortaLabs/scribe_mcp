---
id: scribe_binding_reliability_repair_20260927-research-scribe-response-token-efficiency.md
title: Research Scribe Response Token Efficiency.Md
doc_type: RESEARCH_SCRIBE_RESPONSE_TOKEN_EFFICIENCY.md
doc_name: RESEARCH_SCRIBE_RESPONSE_TOKEN_EFFICIENCY.md
category: research
status: ready
version: '0.1'
last_updated: 2026-09-28 08:16:17 UTC
maintained_by: agent-20260928-080928-cd749fe0
created_by: lens_sbr_response_token_efficiency_18
owners: []
related_docs: []
tags: []
summary: Measured direct Scribe payload sizes and mapped compact durable receipt boundaries,
  budgets, and verification.
canonical_doc_type: research_scribe_response_token_efficiency.md
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 08:14:02 UTC
  created_via: create_doc
  last_edited_at: 2026-09-28 08:16:17 UTC
  last_edited_by: agent-20260928-080928-cd749fe0
  last_action: frontmatter_update
  work_item_id: 23b5c5ba-3302-41e8-94b2-cab0f9c7d8a6
---

## Executive Summary

Objective: measure hot-path Scribe response size and map the smallest compact-receipt contract that preserves durable audit truth. Evidence below is source-backed and uses live, non-destructive reads plus three append probes (the probes intentionally add ordinary audit rows; this report was not used as a representative payload).

Finding (high confidence): `format="compact"` currently does not materially compact structured responses for append_entry, read_recent, query_entries, get_project, or set_project. It mostly changes the human `content[0].text` wrapper; `structuredContent` retains the same broad payload. Append compact was 1,567 chars vs structured 1,568; read_recent 2,639 vs 2,642; query_entries 2,340 vs 2,340; get_project 4,959 vs 4,959; set_project 4,001 vs 4,007. At a 4-char/token deterministic estimate, append success is about 392 tokens, while full MCP serialized wrappers are ~841 tokens.

## System Surface Map

| Operation | Tool implementation | Formatter/runtime seam | Observed payload |
|---|---|---|---|
| append_entry | `src/scribe_mcp/tools/append_entry.py:1263+` | `src/scribe_mcp/utils/formatters/entry.py:494-672`; response dispatch in `src/scribe_mcp/utils/response.py:147-200` | id, written_line, meta, path+paths, line_id, project_name, recent_projects, reminders, db_mirror, timing |
| read_recent | `src/scribe_mcp/tools/read_recent.py:235+` | response formatter plus reminder/context enrichment | entries, pagination, project resolution, recent_projects, reminders, planning advisories, limit metadata |
| query_entries | `src/scribe_mcp/tools/query_entries.py:1208+` | same dispatcher; storage query at `src/scribe_mcp/storage/base.py:336-353` | entries, pagination, search_params, warnings, source, search_message, reminders, project resolution |
| manage_docs | `src/scribe_mcp/tools/manage_docs.py:179+` | document handlers and managed-doc response assembly | action/hash/path/diff/quality/readiness/registration metadata; list_sections probe returned typed error because the document was not registered before creation |
| get_project | `src/scribe_mcp/tools/get_project.py:401+` | project formatter/runtime | state, sitrep, timestamps, docs, recent entries, pagination, resolution/fallback, recent projects, reminders |
| set_project | `src/scribe_mcp/tools/set_project.py:659+` | project setup plus generated/readback and scope resolution | generated/skipped/side effects/root authorization, timing, reminders, scope resolution |

Trace: caller format -> tool implementation -> storage/managed-doc operation -> response formatter -> MCP `content`/structuredContent projection. Council wrappers are not present in these direct Scribe calls; any Council projection can amplify the already broad structured payload and must be measured separately.

## Core System Seams

The response formatter defines full and compact entry paths (`response.py:147-179`) and `format_response` (`response.py:181-200`), but tool-level payload assembly occurs before that formatter. Entry human formatting explicitly parses and re-emits `written_line` (`src/scribe_mcp/utils/formatters/entry.py:494-556`) and also samples `written_lines` (first five) at line 672. This duplicates durable message content and metadata in a hot-path response.

Reminders are a separate enrichment path in `src/scribe_mcp/reminders.py` (progress-log/doc-status scans at lines 117-279; reminder context classes at 639-676). The same reminder/project-context structures appear on read and write responses. `recent_projects` is inventory/context rather than operation truth. `timing`/append-entry timing is diagnostic and should be opt-in. `path` plus `paths` is direct duplication when one artifact path is affected. `db_mirror` is not removable: it is authoritative durability evidence and must survive compact receipts, but can be reduced to typed state and IDs.

## Invariants

Every success receipt must retain: `ok`; stable operation/entry/document identity; project identity; binding identity and generation when binding-scoped; authoritative commit/file state and DB mirror state; affected artifact/path; correlation ID; and queued/retry state. Server-side audit rows, WAL/file commit, and DB mirror behavior remain complete even when response detail is omitted.

Errors must retain full typed error code, message, retryability, retry-after/backoff if present, remediation, and candidate paths/options. Compact is a response projection, not a weaker write or validation path.

## Risk Surfaces

1. Removing `db_mirror` wholesale could hide DB/file divergence (high confidence risk).
2. Removing `written_line` from default output is safe only if the entry message/id/commit state remain available; content echo is nonessential response detail, not audit storage (high).
3. `recent_projects`, reminders, planning advisories, timing trees, and generated/skipped inventories can be stale or expensive and are not operation identity (high).
4. Council wrappers/projections may serialize both `content` and structuredContent. Direct measurements below therefore report both wrapper chars and structured chars; wrapper behavior is a separate ownership boundary (medium).
5. Exact tokenizer counts were unavailable in the direct tool process. Counts use a deterministic estimate of ceil(serialized UTF-8-like character count / 4); validate with the production tokenizer in regression tests (medium).

## Existing Verification Surfaces

Representative direct-call measurements (JSON.stringify character count; ASCII-dominant payloads make this a close byte proxy; estimated tokens = ceil(chars/4)):

| Tool / mode | wrapper chars (~tokens) | structured chars (~tokens) | compact delta vs structured |
|---|---:|---:|---:|
| append_entry readable | 344 (~86) | 4 (~1) | n/a (human text content only) |
| append_entry structured | 3,366 (~842) | 1,568 (~392) | baseline |
| append_entry compact | 3,364 (~841) | 1,567 (~392) | -1 char / -0.06% |
| read_recent readable | 442 (~111) | 4 (~1) | n/a |
| read_recent structured | 5,664 (~1,416) | 2,642 (~661) | baseline |
| read_recent compact | 5,658 (~1,415) | 2,639 (~660) | -3 / -0.1% |
| query_entries structured | 5,028 (~1,257) | 2,340 (~585) | baseline |
| query_entries compact | 5,028 (~1,257) | 2,340 (~585) | 0% |
| get_project structured | 10,482 (~2,621) | 4,959 (~1,240) | baseline |
| get_project compact | 10,482 (~2,621) | 4,959 (~1,240) | 0% |
| set_project structured | 8,428 (~2,107) | 4,007 (~1,002) | baseline |
| set_project compact | 8,416 (~2,104) | 4,001 (~1,001) | -6 / -0.15% |

The direct `manage_docs:list_sections` probe was a typed error (94 serialized chars, ~24 estimated tokens) because the report did not yet exist; after governed creation/rehome the document quality/readiness path passed with zero blocking warnings. Repeat measurements should use a read-only action against an existing managed document and record success/error separately.

## Minimal Receipt and Budgets

Recommended default success envelope:

```json
{"ok":true,"operation":"append_entry","entry_id":"...","project":"...","binding":{"id":"...","generation":7},"durability":{"file":"committed","db_mirror":"committed","audit_id":"..."},"artifact":{"path":"...","document_id":"..."},"correlation_id":"...","retry":{"queued":false,"retryable":false}}
```

Omit content/written_line, raw metadata, recent inventories, reminders, timing, full path arrays, generated/skipped lists, and human UI narration by default. Provide `diagnostics=true` or `format="verbose"` to opt in to current detail. For errors, retain typed remediation regardless of format.

Budgets: append/read-log success <=512 serialized bytes (~128 estimated tokens) by default; read_recent/query_entries <=1,024 bytes (~256 tokens) for one-page hot-path responses excluding requested entry content; get_project <=1,536 bytes (~384 tokens), set_project <=1,024 bytes (~256 tokens), and manage_docs success <=1,536 bytes (~384 tokens) excluding an explicitly requested diff/content body. Verbose mode may retain current payload but should be explicitly bounded (suggest <=16 KiB / 4,096 estimated tokens) and diagnostics tests should assert it. A compact response must be at least 50% smaller than structured for metadata-only success fixtures; content-bearing responses may define a documented floor.

## Recommendations

Amend the existing SBR hot-path ownership to introduce one shared receipt projection seam used by append_entry/read_recent/query_entries/get_project/set_project/manage_docs. Keep generic Scribe formatter/tool changes separate from Council wrapper/projection work. Preserve the existing full formatter as verbose compatibility mode; make compact the actual structured projection, not only a human text alias. Reduce `db_mirror` to authoritative status + mirror ID/generation; retain path singular unless multiple artifacts exist; omit reminders/inventory/timing/content echo.

Regression tests should serialize every mode and assert: default budgets; compact < structured by >=50% on metadata fixtures; required receipt keys; no `written_line`/reminders/recent_projects/timing in default success; complete audit row and DB mirror still exist; typed errors preserve code/remedy/retry fields; verbose retains diagnostics; Council wrapper tests separately assert no duplicate content+structured projection.

## Handoff

Blueprint should design around one shared, source-owned receipt projection seam, preserve authoritative file/DB durability and binding identity/generation, and verify byte/token budgets plus typed-error compatibility. Forge should avoid changing audit persistence while changing only response projection. Council wrapper amplification is a separate package/owner and must not be conflated with generic Scribe behavior.

## Unknowns

- Exact production tokenizer count is UNKNOWN; local measurement used deterministic 4-char estimates and must be replaced/compared with the deployed tokenizer.
- Council projection wrapper fields and duplication are UNKNOWN in direct Scribe evidence; require a separate wrapper-level capture.
- A successful manage_docs representative payload across all three formats is UNKNOWN; current direct probe was a typed error before the report existed. Add a read-only existing-doc fixture to the test matrix.
- Binding ID/generation field names are UNKNOWN in these direct tool payloads; derive canonical names from the binding implementation package before implementation.
