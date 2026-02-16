
# 🐞 Bug Log — scribe_object_store
**Maintained By:** Scribe
**Timezone:** UTC

> Track bug discoveries, investigations, and resolutions. Use `log_type="bugs"` (or `--log bugs`).

---



## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: scribe_object_store] Message text | severity=<severity>; component=<component>; status=<status>; [additional metadata]
```

**Required Metadata Fields:**
- `severity`: critical/high/medium/low/minimal
- `component`: Component or module where bug exists
- `status`: open/investigating/in_progress/fixed/verified/closed/wont_fix

**Optional Metadata Fields:**
- `bug_id`: Ticket number or identifier
- `environment`: production/staging/development/local
- `reproduction_steps`: Brief summary of repro steps
- `test_case`: Test case ID that should cover this bug
- `fix_commit`: Commit hash for the fix
- `reviewer`: Code reviewer
- `confidence`: Confidence in root cause analysis (0-1)
- `impact`: Business impact (critical/high/medium/low/minimal)
- `customer_impacted`: true/false
- `regression`: true/false
- `estimated_effort`: XS/S/M/L/XL
- `related_issues`: Comma-separated list of linked tickets

---

## Severity Classification Guide
- **Critical**: System down, data loss, security vulnerability, or production outage.
- **High**: Major feature broken or significant customer impact; workaround limited.
- **Medium**: Feature partially broken; minor impact; workaround available.
- **Low**: Minor UI issues, edge cases, documentation errors.
- **Minimal**: Cosmetic issues, typos, non-functional improvements.

---

## Component Categories
- **Backend**: Server-side code, APIs, databases.
- **Frontend**: UI and client-side logic.
- **Infrastructure**: Deployment, CI/CD, monitoring, configuration.
- **Tests**: Test suites or infrastructure.
- **Documentation**: READMEs, API docs, guides.
- **Performance**: Latency/throughput regressions.
- **Security**: Security-related bugs and vulnerabilities.
- **Data**: Migration, seeding, or validation errors.

---

## Status Flow Guide
1. **open** → Initial discovery and logging  
2. **investigating** → Root cause analysis  
3. **in_progress** → Fix under development  
4. **fixed** → Fix implemented, ready for testing  
5. **verified** → Fix tested and confirmed  
6. **closed** → Issue resolved and documented  
7. **wont_fix** → Issue accepted as-is (include justification)

---

## Entries will populate below
[🐞] [2026-02-16 08:49:27 UTC] [Agent: ReviewAgent-ObjectStore] [Project: scribe_object_store] CRITICAL BUG #1: HMAC Header Name Mismatch. Server (auth/hmac.py:101-103) expects: X-Signature, X-Timestamp, X-Nonce. Client (corta.py:79-81) sends: X-CortaStore-Signature, X-CortaStore-Timestamp. The CortaStore reference client (client/corta_client.py:84-88) correctly uses X-Signature, X-Timestamp, X-Nonce. Our client uses entirely wrong header names. Every authenticated request will return 401 Unauthorized. | component=corta_provider; finding_id=HMAC-001; reasoning={"how": "Line-by-line comparison of server middleware dispatch() vs client _sign() vs reference client _sign()", "what": "Server reads request.headers.get('X-Signature'), client sends 'X-CortaStore-Signature'. Reference client confirms correct names.", "why": "HMAC auth headers must match exactly or server rejects all requests"}; severity=critical; status=open; priority=high; log_type=bugs; content_type=log
[🐞] [2026-02-16 08:49:31 UTC] [Agent: ReviewAgent-ObjectStore] [Project: scribe_object_store] CRITICAL BUG #2: Missing X-Nonce Header. Server (auth/hmac.py:103,117-119) REQUIRES X-Nonce header for replay protection. Returns 401 'Missing X-Nonce header' if absent. Client _sign() method never generates or includes a nonce. Reference client (corta_client.py:68,87) correctly generates UUID4 nonce. Without nonce, EVERY request fails auth. | component=corta_provider; finding_id=HMAC-002; reasoning={"how": "Traced server auth flow: missing nonce returns 401 before signature check even happens", "what": "Server checks nonce is present (line 117-119) and validates via NonceCache. Client has no nonce generation at all.", "why": "Nonce is required by server for replay protection - not optional"}; severity=critical; status=open; priority=high; log_type=bugs; content_type=log
[🐞] [2026-02-16 08:50:06 UTC] [Agent: ReviewAgent-ObjectStore] [Project: scribe_object_store] MEDIUM BUG #6: list() method parses response incorrectly. Server (app.py:247-257) returns JSON: {"project": "...", "refs": [{"path": "...", "hash": "...", "updated_at": "..."}]}. Client list() (corta.py:173-177) tries to parse resp.json() as a raw list, checks isinstance(refs, list). It should be resp.json().get('refs', []) and then extract the 'path' field from each ref dict. Current code would get a list of dicts and then try r.startswith(prefix) on dicts, which would fail with AttributeError. | component=corta_provider; finding_id=LIST-001; reasoning={"how": "Compared RefListResponse model with client JSON parsing logic. Server wraps refs in an object with project key.", "what": "Server returns {project, refs: [{path, hash, updated_at}]}. Client parses as raw list and calls str.startswith on dict objects.", "why": "list() method will crash or return empty for any valid server response"}; severity=high; status=open; priority=high; log_type=bugs; content_type=log
[🐞] [2026-02-16 08:50:15 UTC] [Agent: ReviewAgent-ObjectStore] [Project: scribe_object_store] MEDIUM BUG #7: head() method checks ref existence via HEAD on ref endpoint, but server has NO HEAD handler for /v1/refs/ routes. Server only defines GET, PUT, DELETE for refs (app.py:259-287). A HEAD request to /v1/refs/{project}/{path} will return 405 Method Not Allowed, not 200/404. The correct approach is to use GET and check status code, or use the /v1/objects/{hash} HEAD endpoint (which IS defined at app.py:163-183) after resolving the ref. | component=corta_provider; finding_id=HEAD-001; reasoning={"how": "Scanned all @app.head, @app.get, @app.put, @app.delete decorators in app.py. HEAD is only defined for objects route.", "what": "Server defines @app.head('/v1/objects/{hash}') but NOT @app.head('/v1/refs/{project}/{path}'). FastAPI returns 405 for undefined methods.", "why": "head() is used by exists() in HybridStore and bulk_check() in base RemoteProvider. If it always fails, exists() remote fallback is broken."}; severity=high; status=open; priority=high; log_type=bugs; content_type=log
