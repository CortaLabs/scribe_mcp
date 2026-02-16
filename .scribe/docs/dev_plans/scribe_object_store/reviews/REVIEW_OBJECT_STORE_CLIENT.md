---
id: scribe_object_store-review-object-store-client
title: REVIEW - Object Store Client Cross-Validation - 2026-02-16
doc_type: custom
doc_name: REVIEW_OBJECT_STORE_CLIENT
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-16 08:52:46 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# REVIEW - Object Store Client Cross-Validation - 2026-02-16

**Stage:** Post-Implementation Review (Stage 5)
**Reviewer:** ReviewAgent-ObjectStore
**Date:** 2026-02-16T08:51:00Z
**Project:** scribe_object_store
**Scope:** Cross-validate Scribe object store client (`src/scribe_mcp/object_store/`) against CortaStore server (`/home/austin/projects/MCP_SPINE/corta_store/src/corta_store/`)

---

## Executive Summary

**VERDICT: REJECTED**
**Score: 45/100**

The object store client has a well-designed architecture (ABCs, HybridStore write-through, key resolution, fire-and-forget integration pattern) and the local-only path (FilesystemStore) works correctly. However, the **CortaStoreProvider** --- the component that actually talks to CortaStore --- has **2 CRITICAL and 2 HIGH severity bugs** that make it completely non-functional against the real server. Every authenticated API call will fail with HTTP 401 because the HMAC headers use wrong names and omit the required nonce. The reference client in the CortaStore repo (`client/corta_client.py`) implements all of this correctly, but the Scribe client diverges on every detail.

**Blocking Issues:** 4 (must fix before any remote operations work)
**Non-Blocking Issues:** 5 (quality, consistency, missing features)

---

## API Compatibility Matrix

| Endpoint | Method | Server Route | Client Implementation | Status |
|----------|--------|-------------|----------------------|--------|
| Store object | PUT | `/v1/objects/{hash}` | `put()` line 129 | BROKEN (auth fails) |
| Get object | GET | `/v1/objects/{hash}` | `get()` line 157 | BROKEN (auth fails) |
| Check object exists | HEAD | `/v1/objects/{hash}` | Not directly used | N/A |
| Delete object | DELETE | `/v1/objects/{hash}` | Not implemented | MISSING |
| Create/update ref | PUT | `/v1/refs/{project}/{path}` | `put()` line 135 | BROKEN (auth + body format) |
| Get ref | GET | `/v1/refs/{project}/{path}` | `get()` line 146 | BROKEN (auth fails) |
| List refs | GET | `/v1/refs/{project}/` | `list()` line 168 | BROKEN (auth + wrong parsing) |
| Delete ref | DELETE | `/v1/refs/{project}/{path}` | `delete()` line 181 | BROKEN (auth fails) |
| Bulk sync check | POST | `/v1/sync/check` | `bulk_check()` line 184 | NOT IMPLEMENTED (falls back to per-key) |
| Health check | GET | `/health` | Not implemented | NOT NEEDED (no auth) |

**Summary:** 0 of 8 authenticated endpoints would succeed against the real server.

---

## Issues Found

### CRITICAL Severity (Blocking)

#### HMAC-001: Header Names Mismatch
- **Server expects:** `X-Signature`, `X-Timestamp`, `X-Nonce` (auth/hmac.py lines 101-103)
- **Client sends:** `X-CortaStore-Signature`, `X-CortaStore-Timestamp` (corta.py lines 79-80)
- **Reference client uses:** `X-Signature`, `X-Timestamp`, `X-Nonce` (corta_client.py lines 84-88)
- **Impact:** Server returns 401 "Missing X-Signature header" for EVERY request
- **Fix:** Rename headers in `_sign()` method to match server expectations

#### HMAC-002: Missing X-Nonce Header
- **Server requires:** `X-Nonce` header containing a unique value per request (auth/hmac.py lines 103, 117-119)
- **Client omits:** No nonce generation or transmission whatsoever
- **Reference client generates:** `uuid.uuid4()` nonce per request (corta_client.py line 68)
- **Server behavior:** Returns 401 "Missing X-Nonce header" before even checking signature
- **Impact:** Even with correct header names, auth still fails without nonce
- **Fix:** Add `import uuid`, generate nonce in `_sign()`, include as `X-Nonce` header

### HIGH Severity (Blocking)

#### LIST-001: list() Response Parsing Incorrect
- **Server returns:** `{"project": "...", "refs": [{"path": "...", "hash": "...", "updated_at": "..."}]}` (RefListResponse model)
- **Client expects:** Raw list of strings from `resp.json()` (corta.py lines 173-177)
- **Client code:** `refs = resp.json(); if isinstance(refs, list): return [r for r in refs if r.startswith(prefix)]`
- **Actual behavior:** `resp.json()` returns a dict (not list), `isinstance(refs, list)` is False, returns `[]`
- **Fix:** Parse as `resp.json().get("refs", [])` and extract `r["path"]` from each dict

#### HEAD-001: head() Uses Unsupported HTTP Method on Refs
- **Server defines:** HEAD only for `/v1/objects/{hash}` (app.py line 163)
- **Server does NOT define:** HEAD for `/v1/refs/{project}/{path}`
- **FastAPI behavior:** Returns 405 Method Not Allowed for HEAD on GET-only routes
- **Client code:** `head()` sends HEAD to `/v1/refs/{project}/{key}` (corta.py line 163-165)
- **Impact:** `exists()` remote fallback in HybridStore always returns False; `bulk_check()` fallback returns all keys as "missing"
- **Fix:** Use GET instead of HEAD for ref existence checks (check status code)

### MEDIUM Severity (Non-blocking)

#### REF-001: Ref PUT Body Format Deviation
- Client sends `{"hash": ..., "updated_at": <float>}` (corta.py line 138)
- Server expects `{"hash": ..., "metadata": {...}}` and generates `updated_at` internally
- Extra `updated_at` field is ignored by server (benign) but `metadata` is never sent

#### OBJ-001: Missing Content-Type Headers
- Reference client sets `Content-Type: text/plain; charset=utf-8` for object PUT
- Reference client sets `Content-Type: application/json` for ref PUT
- Our client sets neither on any request
- Impact: May cause issues with proxies or strict middleware

#### HMAC-003: Latent json_body Signing Mismatch
- `_request()` has a `json_body` parameter path (corta.py line 97-98)
- When used, httpx serializes JSON internally but signature is computed on empty string body
- Currently NOT triggered (all calls use `body=` string parameter) but is a latent bug

#### SYNC-001: bulk_check() Not Implemented
- Server provides `POST /v1/sync/check` accepting `{"hashes": []}`, returning `{"missing": []}`
- Client punts to `super().bulk_check()` which does per-key `head()` calls
- Since `head()` is broken (HEAD-001), bulk_check returns incorrect results
- Migration script relies on this for efficiency

### LOW Severity

#### INT-001: Inconsistent Background Task Management
- Integration points manually create `asyncio.create_task()` and manage `background_tasks` set
- Server has a `schedule_background_task()` utility with logging, health tracking, error handling
- None of the integration points use the utility function

---

## HMAC Signing Verification

### Server Signing Format (auth/hmac.py)
```
Signing string: "{timestamp}:{METHOD}:{path}:{body_hash}"
Signature: HMAC-SHA256(secret, signing_string)
Body hash: SHA-256(request_body_bytes)
Headers required: X-Signature, X-Timestamp, X-Nonce
Timestamp tolerance: 300 seconds (5 minutes)
Nonce: Required, UUID4, replay-protected via NonceCache
```

### Client Signing Format (corta.py)
```
Signing string: "{timestamp}:{METHOD}:{path}:{body_hash}"
Signature: HMAC-SHA256(secret, signing_string)
Body hash: SHA-256(body_string.encode())
Headers sent: X-CortaStore-Signature, X-CortaStore-Timestamp
Timestamp: Unix epoch (correct)
Nonce: NOT GENERATED OR SENT
```

### Reference Client Signing Format (corta_client.py)
```
Signing string: "{timestamp}:{METHOD}:{path}:{body_hash}"
Signature: HMAC-SHA256(secret, signing_string)
Body hash: SHA-256(body_bytes)
Headers sent: X-Signature, X-Timestamp, X-Nonce
Timestamp: Unix epoch (correct)
Nonce: uuid.uuid4() per request
```

**Verdict:** The signing STRING formula is correct. The signing HEADERS are wrong. The nonce is completely missing.

---

## Integration Points Review

| Integration Point | File | Pattern | Safety | Grade |
|------------------|------|---------|--------|-------|
| Server lifecycle | server.py:807-815, 853-857 | setup/close on startup/shutdown | Correct, wrapped in try/except | A |
| doc_management manager | manager.py:142-154, 613 | Auto-resolve store, pass to atomic_write | Correct, graceful fallback | A |
| edit_file | tools/edit_file.py:344-353 | Fire-and-forget background task | Correct but manual task management | B+ |
| special_create | doc_management/special_create.py:418-424 | Sync after template render | Correct | A |
| special_indexes (x3) | doc_management/special_indexes.py:159-164, 241-246, 329-334 | Sync after index writes | Correct, consistent pattern | A |
| generate_doc_templates | tools/generate_doc_templates.py:350-362 | Sync with should_sync check | Correct, includes eligibility filter | A |
| utils/files.py | utils/files.py:386-392 | Sync after atomic_write | Correct, fire-and-forget with pass | A |

**Integration architecture is WELL-DESIGNED.** All hooks gracefully handle failure without impacting the primary write path.

---

## Test Coverage Assessment

| Category | Tests | Coverage | Quality |
|----------|-------|----------|----------|
| Key resolution | 5 | Complete | Good |
| should_sync filtering | 6 | Complete | Good |
| FilesystemStore CRUD | 7 | Complete | Good |
| HybridStore write-through | 3 | Good | Good |
| HybridStore read/fallback | 3 | Good | Good |
| HybridStore list/delete/exists | 4 | Good | Good |
| HMAC signing | 2 | Self-consistent but WRONG | BAD - reinforces bug |
| Provider put/get flow | 2 | Mocked _request | Shallow |
| S3 import guard | 1 | Basic | OK |
| Provider registry | 2 | Basic | OK |
| **Total** | **39** | | |

### Critical Test Coverage Gaps
1. **No cross-validation test** comparing client HMAC against server HMAC (would have caught HMAC-001/002)
2. **No test using actual HTTP** (all provider tests mock `_request()`)
3. **No test for list() response parsing** against actual server response format
4. **No test for head() behavior** (405 vs 200/404)
5. **No error handling tests** (400, 401, 404, 429, 500 status codes)
6. **No retry logic tests** (backoff, max retries, timeout behavior)
7. **No migration script tests**

---

## Positive Findings (What Works Well)

1. **Architecture** - The ABC hierarchy (DocumentStore, RemoteProvider) is clean and extensible
2. **HybridStore pattern** - Write-through with fire-and-forget remote is the right design
3. **Error isolation** - Remote failures never block or fail local writes
4. **Key resolution** - `.scribe/` prefix stripping for URL/S3-safe keys is well-tested
5. **should_sync filtering** - Deny list + allow list + suffix check is comprehensive
6. **FilesystemStore** - Delegates to battle-tested `atomic_write`, zero overhead
7. **Factory pattern** - `create_document_store()` auto-selects based on env vars
8. **Lifecycle management** - Proper setup/close with background task cleanup on shutdown
9. **S3Provider** - Clean implementation with lazy boto3 import and pagination
10. **Migration script** - Good UX with dry-run, per-project, quiet mode

---

## Required Fixes (Blocking)

These MUST be fixed before the object store can function with CortaStore:

### Fix 1: Correct HMAC Headers in `corta.py:_sign()`
```python
# BEFORE (wrong):
return {
    "X-CortaStore-Signature": sig,
    "X-CortaStore-Timestamp": ts,
}

# AFTER (correct):
import uuid
nonce = str(uuid.uuid4())
return {
    "X-Signature": sig,
    "X-Timestamp": ts,
    "X-Nonce": nonce,
}
```

### Fix 2: Fix list() Response Parsing in `corta.py:list()`
```python
# BEFORE (wrong):
refs = resp.json()
if isinstance(refs, list):
    return [r for r in refs if r.startswith(prefix)]
return []

# AFTER (correct):
data = resp.json()
refs = data.get("refs", [])
return [r["path"] for r in refs if isinstance(r, dict) and r.get("path", "").startswith(prefix)]
```

### Fix 3: Fix head() to Use GET Instead of HEAD in `corta.py:head()`
```python
# BEFORE (wrong - server returns 405):
async def head(self, key: str) -> bool:
    ref_path = f"/v1/refs/{self._project}/{key}"
    resp = await self._request("HEAD", ref_path)
    return resp is not None and resp.status_code == 200

# AFTER (correct):
async def head(self, key: str) -> bool:
    ref_path = f"/v1/refs/{self._project}/{key}"
    resp = await self._request("GET", ref_path)
    return resp is not None and resp.status_code == 200
```

### Fix 4: Add Content-Type Headers and Fix Ref Body
- Add `Content-Type: text/plain; charset=utf-8` for object PUT requests
- Add `Content-Type: application/json` for ref PUT requests
- Remove `updated_at` from ref body; add `metadata` field support

---

## Recommended Fixes (Non-blocking)

1. **Implement bulk_check()** using `/v1/sync/check` endpoint for migration performance
2. **Add cross-validation test** that verifies client HMAC output matches `corta_store.auth.hmac.sign_request()` output
3. **Add response format tests** using actual server response schemas
4. **Use schedule_background_task()** for consistency in integration points
5. **Update HMAC test** to validate against correct header names (X-Signature, X-Timestamp, X-Nonce)

---

## Agent Grades

| Agent | Category | Score | Notes |
|-------|----------|-------|-------|
| CoderAgent | Architecture Design | 92% | Excellent ABCs, HybridStore, key resolution |
| CoderAgent | Integration Hooks | 88% | Good fire-and-forget pattern, consistent |
| CoderAgent | CortaStore Provider | 25% | Wrong headers, missing nonce, broken list/head |
| CoderAgent | Test Quality | 55% | Good local tests, but provider tests self-validate wrong behavior |
| CoderAgent | **Overall** | **45%** | Architecture is A-grade but remote provider is non-functional |

---

## Conclusion

The object store client has an excellent architectural foundation that correctly separates concerns (local vs remote, ABCs vs concrete, write-through vs fire-and-forget). The FilesystemStore and HybridStore are production-ready. The integration into Scribe's write paths is safe and well-designed.

However, the CortaStoreProvider --- the only component that actually needs to talk to a real server --- was clearly developed without testing against the actual CortaStore server or reading its authentication code carefully. The reference client in the CortaStore repo implements everything correctly and should have been used as the specification.

**The 4 blocking fixes are straightforward (estimated 15-30 minutes of work) and would bring the provider to functional status.**

Review completed by ReviewAgent-ObjectStore on 2026-02-16.
