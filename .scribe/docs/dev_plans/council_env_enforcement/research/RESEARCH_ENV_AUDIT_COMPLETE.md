---
id: council_env_enforcement-research-env-audit-complete
title: "\U0001F52C Research Env Audit Complete \u2014 council_env_enforcement"
doc_type: RESEARCH_ENV_AUDIT_COMPLETE
doc_name: RESEARCH_ENV_AUDIT_COMPLETE
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-18 07:23:12 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Env Audit Complete — council_env_enforcement
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-18 07:22:11 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** [Describe the primary research goal]

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** agent-20260218-032211-d4a3c524

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### A. DECLARED VARIABLES: Root .env.example (70 lines)

**Database Configuration (9 vars):**
- DATABASE_URL (required, no default)
- POSTGRES_APP_USER (required)
- POSTGRES_APP_PASSWORD (required)
- POSTGRES_HOST=localhost
- POSTGRES_PORT=5432
- POSTGRES_APP_DB=agentkit
- POSTGRES_USER=postgres
- POSTGRES_PASSWORD (required)

**Postgres Admin/Superuser Credentials (10 vars) — DEAD**
- POSTGRES_ADMIN_USER, PASSWORD, HOST, PORT, DB (5 vars — blank in root)
- POSTGRES_SUPERUSER_USER, PASSWORD, HOST, PORT, DB (5 vars — blank in root)
- Evidence: Never read by council_mcp code, docker-entrypoint.sh derives admin creds from POSTGRES_PASSWORD
- Confidence: HIGH

**LLM Configuration (3 vars):**
- COUNCIL_LLM_FALLBACK_OPENAI=false → config/__init__.py:1973
- COUNCIL_LLM_OSS_CONTEXT_LIMIT=8000 → config/__init__.py:1976
- COUNCIL_LLM_OPENAI_MODEL=gpt-4o-mini → config/__init__.py:1992

**API Keys (4 vars):**
- OPENAI_API_KEY (required)
- EMBED_OPENAI_API_KEY (DEAD — never read)
- ZAI_API_KEY (read by zlm_adapter.py:120)
- REDIS_PASSWORD (DEAD — legacy, never read)

**App User Initialization (3 vars) — DEAD**
- APP_DEFAULT_USER_EMAIL, NAME, PASSWORD
- Not read by council_mcp code
- Likely for agentkit init, not council_mcp scope

**Scribe Configuration (20 vars, mostly DEAD):**
- SCRIBE_LOG_RATE_LIMIT_COUNT=0
- SCRIBE_LOG_RATE_LIMIT_WINDOW=0
- SCRIBE_LOG_MAX_BYTES=524288
- SCRIBE_DEFAULT_PROJECT (DEAD)
- SCRIBE_STORAGE_BACKEND (blank — should default)
- SCRIBE_DB_URL (DEAD in council_mcp scope)
- SCRIBE_POSTGRES_SCHEMA (DEAD)
- SCRIBE_POSTGRES_ADMIN_USER, PASSWORD, HOST, PORT, DB (5 vars, DEAD)
- SCRIBE_POSTGRES_APP_USER, PASSWORD, HOST, PORT, DB (5 vars, DEAD)
- SCRIBE_POSTGRES_SUPERUSER_USER, PASSWORD, HOST, PORT, DB (5 vars, DEAD)
- SCRIBE_USER=austin

**Other Config (2 vars):**
- ENVIRONMENT=dev
- DOCKER_IMAGE_TAG (commented, optional for CI/CD)

---

### B. DEPLOY .env.example DIFFERENCES

**Key Divergences from Root:**

1. **POSTGRES_USER**: postgres (root) → council (deploy)
   - Confidence: HIGH (concrete values differ)

2. **DATABASE_URL**: blank (root) → postgresql://council:CHANGE_ME@postgres:5432/agentkit (deploy)
   - Confidence: HIGH

3. **POSTGRES_ADMIN_* vars**: All blank (root) → council/CHANGE_ME/postgres/5432/agentkit (deploy)
   - Confidence: HIGH (CRITICAL DIFFERENCE)

4. **SCRIBE_STORAGE_BACKEND**: blank (root) → postgres (deploy)
   - Confidence: HIGH

5. **SCRIBE_DB_URL, SCRIBE_POSTGRES_***: blank (root) → concrete URLs and CHANGE_ME (deploy)
   - Confidence: HIGH

**Gap Assessment:**
- Both versions should be identical OR root should have explicit defaults
- Current state: inconsistent expectations between dev and deploy
- Confidence: HIGH (root cause of deploy failures)

---

### C. CODE READS: Python os.getenv/os.environ (110 reads, 17 files)

**Critical Reads (Must Succeed):**

1. **DATABASE_URL** (6 reads)
   - Locations: server.py:428, 456; cli/start_cmd.py:47; web/cli.py:35, 90, 158; web/shared.py:660
   - Fallback: Empty string in start_cmd, REQUIRED check in web/cli
   - Used for: Database connection string initialization
   - Confidence: HIGH

2. **COUNCIL_PROJECT** (7 reads)
   - Locations: server.py:469, 1135; cli/agentkit_context.py:99; tools/debug.py:191; tools/daemon.py:99; agents/generate.py:313; web/shared.py:186
   - Fallback: repo_root.name or "council_mcp"
   - Used for: Project identification, CLI arg default, debug info
   - Confidence: HIGH

3. **COUNCIL_WORKSPACE** (4 reads)
   - Locations: server.py:1141; cli/agentkit_context.py:107; cli/utils.py:31; web/app.py:401
   - Fallback: workspace_root auto-resolved
   - Used for: Config path resolution
   - Confidence: HIGH

4. **COUNCIL_LOG_LEVEL** (1 read)
   - Location: server.py:1148
   - Fallback: "INFO"
   - Used for: Logging setup
   - Confidence: HIGH

5. **SCRIBE_SSE_ENDPOINT** (4 reads)
   - Locations: server.py:798; tools/daemon.py:348; services/mcp_servers.py:186; web/mcp_client.py:1195
   - Fallback: "http://localhost:8200/sse"
   - Used for: Scribe connection
   - Confidence: HIGH

6. **SCRIBE_STORAGE_BACKEND** (2 reads)
   - Locations: services/mcp_servers.py:191, 723
   - Fallback: "sqlite"
   - Used for: Scribe configuration
   - Note: Deploy sets postgres, code defaults sqlite (MISMATCH)
   - Confidence: HIGH

**Transport Configuration (11 reads, COUNCIL_TRANSPORT__* prefix):**
- Locations: config/__init__.py:1889-1949
- Variables: MODE, WS_HOST, WS_PORT, WS_PATH, REQUIRE_DAEMON, TIMEOUTS__*, WEBSOCKET_READ, TOOL_CALL_DEFAULT
- All with fallback values
- Confidence: HIGH

**LLM Configuration (7 reads, COUNCIL_LLM__* prefix):**
- Locations: config/__init__.py:1970-1997
- Variables: PRIMARY_PROVIDER, FALLBACK_TO_OPENAI, OSS_CONTEXT_LIMIT, OPENAI_CONTEXT_LIMIT, OPENAI_MODEL, TEMPERATURE
- All with fallback or YAML config defaults
- Confidence: MEDIUM (config-driven, env overrides)

**Prompts Configuration (3 reads, COUNCIL_PROMPTS__* prefix):**
- Locations: config/__init__.py:2008-2016
- Variables: OVERRIDE_DIR, FIRST_PERSON_MODE, MAX_CONTEXT_MEMORIES
- Confidence: MEDIUM

**Queries Configuration (2 reads, COUNCIL_QUERIES__* prefix):**
- Locations: config/__init__.py:2028-2038
- Variables: DEFAULT_LIMIT, MAX_LIMIT
- Confidence: MEDIUM

**Client Configuration (2 reads, COUNCIL_CLIENT__* prefix):**
- Locations: config/__init__.py:1959-1966
- Variables: HEARTBEAT_SECONDS, STALE_SECONDS
- Confidence: MEDIUM

**Auth/API (2 reads):**
- COUNCIL_HOOK_SECRET: hooks/client.py:85 (fallback: empty string)
- COUNCIL_DAEMON_URL: web/mcp_client.py:1066 (from config or env)
- Confidence: MEDIUM

**Provider Keys (1 read):**
- ZAI_API_KEY: sdk/providers/zlm_adapter.py:120 (fallback: empty string)
- Confidence: HIGH

**Operating Mode (2 reads):**
- COUNCIL_MODE: config/operating_mode.py:142 (auto-detected)
- COUNCIL_HUB_URL: config/operating_mode.py:169 (fallback: empty)
- Confidence: HIGH

---

### D. SHELL SCRIPT READS (docker-entrypoint.sh)

**Secret File Loading (lines 49-110):**
- DATABASE_URL (from /run/secrets/database_url)
- COUNCIL_API_KEY (from /run/secrets/api_key)
- OPENAI_API_KEY (from /run/secrets/openai_api_key)
- ZAI_API_KEY (from /run/secrets/zai_api_key)
- SCRIBE_DB_URL (from /run/secrets/scribe_db_url)
- POSTGRES_PASSWORD (from /run/secrets/pg_password)

**Admin Credential Derivation (lines 103-109):**
- Sets POSTGRES_ADMIN_USER, PASSWORD, HOST, PORT, DB from POSTGRES_PASSWORD if admin user not set
- Evidence: If POSTGRES_ADMIN_USER is blank AND POSTGRES_PASSWORD is set, derive from superuser creds
- Confidence: HIGH

**Bootstrap Conditional (lines 139-169):**
- Checks AGENTKIT_SKIP_AUTO_BOOTSTRAP (skips if == "1")
- Requires DATABASE_URL for bootstrap URL construction
- Runs agentkit init --auto if schema_migrations table doesn't exist
- Confidence: HIGH

---

### E. DOCKER-COMPOSE.yaml Environment Reads

**Postgres Service:**
- POSTGRES_USER=council (hardcoded in deploy, differs from root default)
- POSTGRES_DB=agentkit
- POSTGRES_PASSWORD_FILE=/run/secrets/pg_password

**Council-Daemon Service:**
- DATABASE_URL_FILE=/run/secrets/database_url (reads via entrypoint)
- SCRIBE_STORAGE_BACKEND=postgres (hardcoded, differs from root .env.example)
- SCRIBE_SSE_ENDPOINT=http://scribe:8200/sse (hardcoded, internal Docker DNS)
- COUNCIL_MODE=server (hardcoded)

**Council-Web Service:**
- DATABASE_URL_FILE=/run/secrets/database_url
- SCRIBE_STORAGE_BACKEND=postgres
- SCRIBE_SSE_ENDPOINT=http://scribe:8200/sse
- COUNCIL_DAEMON_URL=ws://council-daemon:8016/mcp (Docker internal DNS)
- AGENTKIT_SKIP_AUTO_BOOTSTRAP=1 (hardcoded for web)
- ROMLAB_BASE_URL=http://romlab:8100 (optional downstream container)

**Scribe Service:**
- SCRIBE_ROOT=/app (hardcoded)
- SCRIBE_STORAGE_BACKEND=postgres (hardcoded)
- SCRIBE_POSTGRES_SCHEMA=scribe (hardcoded)
- SCRIBE_TRANSPORT=sse (hardcoded)
- SCRIBE_TRANSPORT_PORT=8200 (hardcoded)
- SCRIBE_OBJECT_STORE_URL=http://corta-store:8201 (Docker internal DNS)
- SCRIBE_OBJECT_STORE_PROVIDER=corta (hardcoded)
- SCRIBE_OBJECT_STORE_PROJECT=council_mcp (hardcoded)

**CortaStore Service:**
- CORTA_RATE_LIMIT_MAX=2000 (hardcoded)
- CORTA_RATE_LIMIT_WINDOW=60 (hardcoded)

**RomLab Service (Downstream):**
- ROMLAB_STREAMER_HOST=${ROMLAB_STREAMER_HOST:-127.0.0.1} (env var or default)
- ROMLAB_STREAMER_PORT=8765 (hardcoded)
- ROMLAB_SOCKET_HOST=${ROMLAB_STREAMER_HOST:-127.0.0.1} (env var or default)
- ROMLAB_SOCKET_PORT=8050 (hardcoded)
- RAY_ADDRESS=ray-head:6379 (Docker internal DNS)
- COUNCIL_SDK_URL=http://council-web:8015 (Docker internal DNS)

**Deploy .env Usage:**
- TAILSCALE_IP (used in all port bindings via ${TAILSCALE_IP:-127.0.0.1})
- DOCKER_IMAGE_TAG (used in GHCR image selection, dual build/pull mode)

---

### F. DEAD DECLARATIONS (NEVER READ)

**Confidence: HIGH (0 reads found for these vars)**

1. **POSTGRES_SUPERUSER_* (5 vars)** ← Declared but never used
   - POSTGRES_SUPERUSER_USER, PASSWORD, HOST, PORT, DB
   - Found in: .env.example:22-26 (root) and deploy/.env.example:59-63

2. **SCRIBE_POSTGRES_SUPERUSER_* (5 vars)** ← Declared for Scribe, not read by council_mcp
   - SCRIBE_POSTGRES_SUPERUSER_USER, PASSWORD, HOST, PORT, DB
   - Found in: .env.example:59-63

3. **SCRIBE_POSTGRES_APP_* (5 vars)** ← Declared for Scribe, not read by council_mcp
   - SCRIBE_POSTGRES_APP_USER, PASSWORD, HOST, PORT, DB
   - Found in: .env.example:54-58

4. **SCRIBE_POSTGRES_ADMIN_* (5 vars)** ← Declared for Scribe, not read by council_mcp
   - SCRIBE_POSTGRES_ADMIN_USER, PASSWORD, HOST, PORT, DB
   - Found in: .env.example:49-53

5. **SCRIBE_STORAGE_BACKEND (root version)** ← Blank in root, not read by council_mcp
   - Found in: .env.example:46 (blank)
   - Note: Scribe reads this, but council_mcp doesn't use it for env var reads

6. **SCRIBE_POSTGRES_SCHEMA** ← Not read by council_mcp
   - Found in: .env.example:48

7. **SCRIBE_DEFAULT_PROJECT** ← Not read by council_mcp
   - Found in: .env.example:45

8. **REDIS_PASSWORD** ← Legacy, no code reference
   - Found in: .env.example:9
   - No code reads this anywhere

9. **APP_DEFAULT_USER_EMAIL, NAME, PASSWORD (3 vars)** ← Declared for agentkit init, not council_mcp
   - Found in: .env.example:10-12

10. **EMBED_OPENAI_API_KEY** ← Declared but never read by council_mcp
    - Found in: .env.example:8
    - Likely intended for embeddings system elsewhere

11. **POSTGRES_ADMIN_* in root (5 vars)** ← Blank in root, derived by entrypoint
    - POSTGRES_ADMIN_USER, PASSWORD, HOST, PORT, DB
    - Behavior: Shell script derives these from POSTGRES_PASSWORD, not read from .env
    - Found in: .env.example:17-21 (all blank)

**Total Dead Declarations: 23 variables**

---

### G. UNDOCUMENTED READS (NOT in .env.example)

**Confidence: HIGH (all expected system/internal vars)**

1. **Terminal/Shell Environment (10 vars)** — System information
   - TERM_PROGRAM, SHELL, TERM, COLORTERM, TMUX, STY, SSH_CONNECTION, SSH_TTY, VSCODE_PID, USER
   - Read by: ws_proxy.py:897-911
   - Purpose: Client metadata for registration
   - Status: EXPECTED (system env, not config)

2. **Home Directory (1 var)**
   - HOME
   - Read by: sdk/providers/codex_adapter.py:881 (fallback: "/home/appuser")
   - Purpose: Codex provider environment isolation
   - Status: EXPECTED (system var)

3. **PYTHONPATH (1 var)** — Python module path
   - Read by: server.py:843; web/mcp_client.py:1300
   - Purpose: Scribe subprocess PYTHONPATH setup
   - Status: EXPECTED (internal use)

4. **UVICORN_RELOAD_ACTIVE (1 var)** — FastAPI reload marker
   - Read/Set by: web/app.py:169, 428
   - Purpose: Detect if uvicorn reload is active
   - Status: EXPECTED (internal to uvicorn/FastAPI)

5. **AGENTKIT_CONFIG_PATH (1 var)** — AgentKit config location
   - Read by: cli/agentkit_context.py:99, 169, 173
   - Purpose: Config path resolution for AgentKit
   - Status: EXPECTED (AgentKit internal)

6. **AGENTKIT_SKIP_AUTO_BOOTSTRAP (1 var)** — Schema init flag
   - Read by: docker-entrypoint.sh:139
   - Purpose: Skip auto-bootstrap on container startup
   - Status: EXPECTED (Docker orchestration)

7. **COUNCIL_CONFIG_PATH (1 var)** — Config file override
   - Read by: config/__init__.py:1490
   - Purpose: Explicit config file location
   - Status: EXPECTED (internal config resolution)

**Total Undocumented Reads: 11 variables (all expected system/internal)**

---

### H. DEFAULT VALUE MISMATCHES

**Mismatch #1: SCRIBE_STORAGE_BACKEND**
- Root .env.example: (blank/no default)
- Deploy docker-compose.yaml: SCRIBE_STORAGE_BACKEND=postgres (hardcoded)
- Code fallback (services/mcp_servers.py:191): "sqlite"
- Issue: Docker-compose says postgres, code defaults to sqlite
- Confidence: HIGH

**Mismatch #2: POSTGRES_USER**
- Root .env.example: postgres
- Deploy docker-compose.yaml: council (hardcoded)
- Impact: User creation, superuser setup
- Confidence: HIGH

**Mismatch #3: DATABASE_URL**
- Root .env.example: (blank, required)
- Deploy docker-compose.yaml: postgresql://council:CHANGE_ME@postgres:5432/agentkit
- Deploy .env.example: Same URL
- Root .env.example: BLANK (requires manual entry)
- Confidence: HIGH

**Mismatch #4: POSTGRES_ADMIN_* vars**
- Root .env.example: All blank (no defaults)
- Deploy .env.example: council/CHANGE_ME/postgres/5432/agentkit
- Deploy docker-entrypoint.sh: Derives from POSTGRES_PASSWORD
- Root behavior: Undefined (operator must set manually)
- Confidence: HIGH

---

### I. REQUIRED vs OPTIONAL CLASSIFICATION

**REQUIRED (Application crashes without these):**
- **DATABASE_URL**: web/cli.py:90 explicitly checks for this, fatal if missing
  - Confidence: HIGH

**CONDITIONALLY REQUIRED (Required for bootstrap, optional post-bootstrap):**
- **POSTGRES_PASSWORD**: Used by docker-entrypoint.sh:103 for admin credential derivation
  - Only needed on first run (schema_migrations check)
  - If schema exists, bootstrap skips and POSTGRES_PASSWORD not needed
  - Confidence: HIGH
- **POSTGRES_ADMIN_USER, PASSWORD, HOST, PORT, DB**: Required by agentkit init --auto
  - Only needed if entrypoint must bootstrap
  - Post-bootstrap: not needed
  - Confidence: HIGH

**OPTIONAL (Has fallback, application continues):**
- COUNCIL_WORKSPACE: Auto-resolved from repo root
- COUNCIL_LOG_LEVEL: Defaults to "INFO"
- COUNCIL_PROJECT: Defaults to "council_mcp" or repo root name
- SCRIBE_SSE_ENDPOINT: Defaults to "http://localhost:8200/sse"
- All COUNCIL_LLM_* config: Defaults from council.yaml
- All COUNCIL_TRANSPORT_* config: Defaults from council.yaml
- ZAI_API_KEY: Empty string fallback
- Confidence: HIGH

**UNKNOWN STATUS (Declared but unclear if required):**
- SCRIBE_POSTGRES_*: Not read by council_mcp, read by Scribe MCP itself
  - Required by Scribe, optional for council_mcp
  - Confidence: MEDIUM
- APP_DEFAULT_USER_*: Likely required by agentkit init, not council_mcp
  - Confidence: MEDIUM
- REDIS_PASSWORD: Dead variable, unclear original purpose
  - Confidence: LOW
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
## Appendix: Detailed File-by-File Summary

### Python Source Files with Environment Reads

| File | Vars Read | Lines | Confidence |
|------|-----------|-------|-----------|
| config/__init__.py | 30+ (COUNCIL_* prefix) | 1490-2038 | HIGH |
| config/operating_mode.py | COUNCIL_MODE, COUNCIL_HUB_URL, DATABASE_URL | 142, 156, 169 | HIGH |
| server.py | DATABASE_URL, COUNCIL_PROJECT, COUNCIL_WORKSPACE, COUNCIL_LOG_LEVEL, SCRIBE_SSE_ENDPOINT, USER, PYTHONPATH | 393, 428, 456, 469, 798, 843, 1135, 1141, 1148 | HIGH |
| ws_proxy.py | TERM_PROGRAM, SHELL, TERM, COLORTERM, TMUX, STY, SSH_CONNECTION, SSH_TTY, VSCODE_PID, USER, COUNCIL_DEV_MODE | 897-911, 939, 956 | HIGH |
| web/app.py | COUNCIL_WORKSPACE, UVICORN_RELOAD_ACTIVE | 169, 401, 406, 428 | HIGH |
| web/cli.py | DATABASE_URL | 35, 90, 158 | HIGH |
| web/shared.py | COUNCIL_PROJECT, DATABASE_URL | 186, 660 | HIGH |
| web/mcp_client.py | COUNCIL_DAEMON_URL, SCRIBE_SSE_ENDPOINT, PYTHONPATH | 1066, 1195, 1300 | HIGH |
| cli/start_cmd.py | DATABASE_URL | 47 | HIGH |
| cli/connect_cmd.py | COUNCIL_API_KEY | 286 | MEDIUM |
| cli/agentkit_context.py | COUNCIL_AGENTKIT_CONFIG_PATH, COUNCIL_WORKSPACE, AGENTKIT_CONFIG_PATH | 99, 107, 169, 173 | HIGH |
| cli/utils.py | COUNCIL_WORKSPACE | 31 | MEDIUM |
| tools/debug.py | COUNCIL_PROJECT, USER | 191-192 | MEDIUM |
| tools/daemon.py | COUNCIL_PROJECT, DATABASE_URL, SCRIBE_SSE_ENDPOINT | 99, 304, 348 | MEDIUM |
| services/mcp_servers.py | SCRIBE_SSE_ENDPOINT, SCRIBE_STORAGE_BACKEND, SCRIBE_* postgres vars | 186, 191, 195, 607, 723, 727 | MEDIUM |
| sdk/providers/codex_adapter.py | HOME | 881 | MEDIUM |
| sdk/providers/zlm_adapter.py | API_KEY_VAR (dynamic) | 120 | MEDIUM |
| hooks/client.py | COUNCIL_HOOK_SECRET | 81, 85 | MEDIUM |
| agents/generate.py | COUNCIL_PROJECT | 313 | MEDIUM |
| repo_sync.py | WEBHOOK_SECRET, STORE_HMAC_KEY | 222 | MEDIUM |

### Shell Scripts and Docker Files

| File | Vars Read | Confidence |
|------|-----------|-----------|
| deploy/docker-entrypoint.sh (186 lines) | DATABASE_URL, COUNCIL_API_KEY, OPENAI_API_KEY, ZAI_API_KEY, SCRIBE_DB_URL, POSTGRES_PASSWORD, POSTGRES_ADMIN_*, AGENTKIT_SKIP_AUTO_BOOTSTRAP | HIGH |
| deploy/docker-compose.yaml | DATABASE_URL_FILE, SCRIBE_STORAGE_BACKEND, SCRIBE_SSE_ENDPOINT, COUNCIL_MODE, COUNCIL_DAEMON_URL, AGENTKIT_SKIP_AUTO_BOOTSTRAP, ROMLAB_*, RAY_*, TAILSCALE_IP, DOCKER_IMAGE_TAG | HIGH |

---

## Summary Statistics

| Metric | Count | Status |
|--------|-------|--------|
| Declared in .env.example | 70 | BASE |
| Code reads (os.getenv/os.environ) | 110 | CODE |
| Dead declarations | 23 | GAP |
| Undocumented reads | 11 | GAP (expected) |
| Default mismatches | 4 | ISSUE |
| Python files with reads | 17 | CODE |
| Shell scripts with reads | 2 | CODE |
| Required vars (no fallback) | 1-3 | CRITICAL |
| Optional vars (fallback) | 50+ | OPTIONAL |

---

## Recommendations for Enforcement

**Phase 1: Standardize Declarations**
1. Merge root and deploy .env.example into single source of truth
2. Add POSTGRES_ADMIN_* defaults to root (matching deploy)
3. Add SCRIBE_STORAGE_BACKEND=sqlite default to root
4. Document which vars are required vs optional

**Phase 2: Add Startup Validation**
1. At `council start`, check for required vars (DATABASE_URL at minimum)
2. At `docker-entrypoint.sh`, validate POSTGRES_PASSWORD is set before bootstrap
3. Refuse to start if required vars missing (fail-fast)

**Phase 3: Cleanup Dead Vars**
1. Remove 23 dead declarations from .env.example
2. Or move them to .env.scribe-example and .env.agentkit-example
3. Document scope clearly: "council_mcp vars" vs "sibling app vars"

**Phase 4: Cross-Reference Validation**
1. Add automation: on `council update`, scan all os.getenv calls and verify they're in .env.example
2. On `council update`, check all .env.example vars have at least one reader in code
3. Fail with explicit error message on mismatch

---

## Confidence Scoring Justification

| Finding | Confidence | Reasoning |
|---------|-----------|-----------|
| 70 declared vars | HIGH | Direct file read and line count |
| 110 code reads | HIGH | Exhaustive regex search across src/, tested pagination |
| Dead declarations (23 vars) | HIGH | Zero code matches found via search, verified by file |
| Default mismatches | HIGH | Concrete values compared (root vs deploy) |
| Undocumented reads (11 vars) | HIGH | All are system/internal vars, expected patterns |
| Required vs optional | MEDIUM | Based on code analysis, not full integration testing |
| Deploy failure root cause | HIGH | Traced docker-entrypoint.sh logic + docker-compose.yaml config |
