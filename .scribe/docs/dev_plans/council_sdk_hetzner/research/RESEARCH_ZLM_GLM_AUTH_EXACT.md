---
id: council_sdk_hetzner-research-zlm-glm-auth-exact
title: "\U0001F52C Research Zlm Glm Auth Exact \u2014 council_sdk_hetzner"
doc_type: RESEARCH_ZLM_GLM_AUTH_EXACT
doc_name: RESEARCH_ZLM_GLM_AUTH_EXACT
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 10:15:38 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Zlm Glm Auth Exact — council_sdk_hetzner
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 10:14:33 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

ZLM (Z.AI GLM) authentication is **NOT a separate provider**. ZLM is a `ClaudeSDKAdapter` subclass that reuses the Claude Agent SDK binary while injecting Z.AI credentials via environment variables. Authentication is **entirely environment variable-based**: the ZAI_API_KEY env var is read at session creation and injected into the Claude SDK subprocess. The API key is NEVER hardcoded or stored in config — it's purely runtime-injected.

**Confidence: HIGH** (all findings verified from source code with exact line numbers)
<!-- ID: research_scope -->
**Research Lead:** atlas

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### Finding 1: ZLMAdapter is a Subclass of ClaudeSDKAdapter (EXACT CODE)

**File:** `src/council_mcp/sdk/providers/zlm_adapter.py:41-52`

```python
class ZLMAdapter(ClaudeSDKAdapter):  # type: ignore[misc]
    """ZLM (Z.AI GLM) provider — Anthropic-compatible.

    Subclasses ClaudeSDKAdapter and overrides:
      - provider_slug: "zlm"
      - _get_provider_config: reads from council.sdk.providers.zlm
      - _build_options: injects ANTHROPIC_BASE_URL and API key into env

    Z.AI exposes GLM models via the same Anthropic Messages API.
    The Claude Agent SDK talks to them by setting ANTHROPIC_BASE_URL
    and ANTHROPIC_API_KEY as environment variables on the CLI subprocess.
    """
```

**What This Means:** ZLM does NOT use a separate SDK or API protocol. It reuses the Claude Agent SDK binary (same as Claude provider) but overrides only three methods: `provider_slug`, `_get_claude_config`, and `_build_options`. Everything else (session lifecycle, message streaming, tool approval) is inherited from the parent class.

**Confidence: HIGH** — Direct class inheritance at line 41.

---

### Finding 2: ZAI_API_KEY is Read from Environment at Runtime

**File:** `src/council_mcp/sdk/providers/zlm_adapter.py:118-128`

```python
# Inject API key: read from the configured env var name
api_key_var = env_cfg.get("api_key_var", "ZAI_API_KEY")
api_key = os.environ.get(api_key_var, "")
if api_key:
    options.env["ANTHROPIC_API_KEY"] = api_key
else:
    logger.warning(
        "ZLM API key not found in environment variable '%s'. "
        "Sessions may fail to authenticate with Z.AI.",
        api_key_var,
    )
```

**What This Means:**
1. The API key variable name is **configurable** via `council.sdk.providers.zlm.env.api_key_var` (default: `ZAI_API_KEY`)
2. The API key is read from **the OS environment** via `os.environ.get(api_key_var, "")`
3. If the env var is missing, a **warning is logged** but no exception is raised — sessions will fail later when they try to authenticate
4. The API key is injected into the Claude SDK subprocess via `options.env["ANTHROPIC_API_KEY"]`

**Key Point:** The API key is NEVER stored in config files or `.council/council.yaml`. It's ONLY read from the host environment.

**Confidence: HIGH** — Direct `os.environ.get()` call at line 120.

---

### Finding 3: ANTHROPIC_BASE_URL Injection for Z.AI Endpoint

**File:** `src/council_mcp/sdk/providers/zlm_adapter.py:114-116`

```python
# Inject Z.AI base URL from config
base_url = env_cfg.get("base_url", "https://api.z.ai/api/anthropic")
options.env["ANTHROPIC_BASE_URL"] = base_url
```

**What This Means:**
1. The Z.AI API endpoint is **configurable** via `council.sdk.providers.zlm.env.base_url`
2. Default endpoint: `https://api.z.ai/api/anthropic` (Z.AI's Anthropic-compatible proxy)
3. This is injected as an environment variable `ANTHROPIC_BASE_URL` into the Claude SDK subprocess
4. The Claude SDK subprocess (running the Claude Agent CLI binary) sees this env var and routes requests to Z.AI instead of Anthropic

**Confidence: HIGH** — Direct code at lines 115-116.

---

### Finding 4: Configuration Structure in DEFAULT_CONFIG

**File:** `src/council_mcp/config/__init__.py:568-598`

```yaml
"zlm": {
    "enabled": False,
    "display_name": "ZLM (GLM)",
    "default_model": "GLM-5",
    "fallback_model": "GLM-5-Air",
    "models": [
        "GLM-5",
        "GLM-5-Air",
        "GLM-5-Flash",
        # ... more models
    ],
    "permission_mode": "default",
    "setting_sources": ["project"],
    "max_budget_usd": 10.0,
    "max_turns": 100,
    "include_partial_messages": True,
    "max_thinking_tokens": None,
    "betas": [],
    "env": {
        "api_key_var": "ZAI_API_KEY",
        "base_url": "https://api.z.ai/api/anthropic",
        "timeout_ms": 3000000,
    },
}
```

**What This Means:**
1. ZLM config is under `council.sdk.providers.zlm` (NOT `council.sdk.providers.glm`)
2. The `env` section contains auth config: `api_key_var`, `base_url`, and `timeout_ms`
3. All three values are customizable (users can override in `.council/council.yaml`)
4. The config structure mirrors Claude provider but with Z.AI-specific env vars

**Confidence: HIGH** — Direct from DEFAULT_CONFIG at lines 568-598.

---

### Finding 5: Runtime Config Override in .council/council.yaml

**File:** `.council/council.yaml:518-521`

```yaml
zlm:
  env:
    api_key_var: ZAI_API_KEY
    base_url: https://api.z.ai/api/anthropic
    timeout_ms: 3000000
```

**What This Means:**
1. The runtime config shows `ZAI_API_KEY` as the env var to read
2. The Z.AI endpoint is `https://api.z.ai/api/anthropic`
3. API timeout is 50 minutes (3000000 ms = 3000 seconds)
4. Operators can override these values in their own `.council/council.yaml` without touching code

**Confidence: HIGH** — Direct from running config file.

---

### Finding 6: Claude Adapter Auth Pattern (Parent Class)

**File:** `src/council_mcp/sdk/providers/claude_adapter.py:426-483`

The `_build_options` method in Claude adapter (which ZLM inherits) shows the auth pattern:

```python
def _build_options(self, config: SessionConfig) -> Any:
    """Build ClaudeAgentOptions from SessionConfig + council.yaml.

    Merges per-session config with provider defaults from council.yaml.
    Per-session values take precedence over defaults.
    """
    claude_cfg = self._get_claude_config()
    
    # ... model, permission_mode, budget settings ...
    
    # Environment variables: merge session env with config env
    # All values must be strings — subprocess.Popen(env=...) requires it
    env = {k: str(v) for k, v in claude_cfg.get("env", {}).items()}
    for key, value in config.env:
        env[key] = str(value)
    
    # ... build options ...
    
    return _ClaudeAgentOptions(**options_kwargs)
```

**What This Means:**
1. Claude adapter reads env vars from config at line 481
2. Env vars are merged from two sources: config defaults + per-session overrides
3. All values are converted to strings (subprocess requirement)
4. ZLMAdapter calls `super()._build_options()` (line 109) to get parent options, THEN injects ZLM-specific env vars

**Confidence: HIGH** — Direct from claude_adapter.py lines 426-483.

---

### Finding 7: How ZLM Auth Works (Complete Flow)

**The Authentication Chain:**

1. **User requests ZLM session** → `ZLMAdapter.create_session(config)` is called
2. **Read config** → `_get_claude_config()` reads from `council.sdk.providers.zlm` section (not `claude`)
3. **Build options** → `_build_options(config)` calls parent, then injects:
   - `ANTHROPIC_BASE_URL = "https://api.z.ai/api/anthropic"` (from config)
   - `ANTHROPIC_API_KEY = os.environ.get("ZAI_API_KEY")` (from host environment)
   - `API_TIMEOUT_MS = "3000000"` (from config)
4. **Create ClaudeSDKClient** → Parent spawns Claude Agent SDK subprocess with injected env vars
5. **Claude SDK sees env vars** → Routes requests to Z.AI instead of Anthropic
6. **Authentication** → Z.AI validates `ANTHROPIC_API_KEY` against their GLM API
7. **Response** → GLM model responds via Anthropic-compatible API format

**Confidence: HIGH** — Verified across 6 code sections.

---

### Finding 8: Claude Adapter Auth (Does NOT Use ANTHROPIC_API_KEY)

**File:** `src/council_mcp/sdk/providers/claude_adapter.py:120-132`

```python
def __init__(self) -> None:
    if not _sdk_available:
        raise SDKProviderError(
            "claude-agent-sdk not installed. "
            "Install with: pip install 'claude-agent-sdk>=0.1.29,<0.2.0'",
            provider="claude",
            recoverable=False,
        )
    self._cfg = get_council_config()
    self._clients: dict[str, Any] = {}  # session_id -> ClaudeSDKClient
    self._pending_approvals: dict[str, asyncio.Event] = {}
    self._approval_decisions: dict[str, ToolDecision] = {}
    self._approval_events_queue: dict[str, list[ApprovalRequired]] = {}
```

**Finding:** Claude adapter __init__ does NOT set ANTHROPIC_API_KEY. It relies on the Claude Agent SDK CLI binary to use Claude Code CLI authentication (based on operator's local `.claude/` CLI auth). The `env` section in Claude config is empty by default (line 514 in DEFAULT_CONFIG).

**Verification:** In `.council/council.yaml`, Claude provider has `env: {}` (empty) while ZLM has populated env dict with `api_key_var` and `base_url`.

**Confidence: HIGH** — Direct from source code and config comparison.
<!-- ID: technical_analysis -->
## Technical Analysis

### Authentication Architecture

**The ZLM auth flow is a three-layer injection pattern:**

```
Layer 1 (Config)
  └─ council.sdk.providers.zlm.env
     ├─ api_key_var: "ZAI_API_KEY"
     └─ base_url: "https://api.z.ai/api/anthropic"
         ↓
Layer 2 (Runtime)
  └─ ZLMAdapter._build_options()
     ├─ Read api_key from os.environ[api_key_var]
     ├─ Inject ANTHROPIC_API_KEY into options.env
     └─ Inject ANTHROPIC_BASE_URL into options.env
         ↓
Layer 3 (Subprocess)
  └─ Claude Agent SDK CLI binary
     ├─ Reads env vars from parent process
     ├─ Routes to https://api.z.ai/api/anthropic (not Anthropic)
     └─ Authenticates using ANTHROPIC_API_KEY against Z.AI
```

### Why This Works

1. **Anthropic Compatibility**: Z.AI implements the Anthropic Messages API exactly. The Claude Agent SDK binary doesn't care which endpoint it's calling — it just sends requests to the URL in `ANTHROPIC_BASE_URL`.

2. **Env Var Injection**: By setting `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY` in the subprocess environment, the SDK binary routes to Z.AI and uses their API key. No code changes to the SDK needed.

3. **Configuration Flexibility**: The entire auth mechanism is config-driven:
   - Change `api_key_var` from `ZAI_API_KEY` to anything else → reads different env var
   - Change `base_url` → redirects to different Z.AI endpoint (or any Anthropic-compatible proxy)
   - All customizable without code modifications

### Comparison: Claude vs ZLM Auth

| Property | Claude | ZLM |
|----------|--------|-----|
| **SDK** | Claude Agent SDK | Claude Agent SDK (same) |
| **Auth Method** | Claude Code CLI (~/.claude/auth) | API Key (ZAI_API_KEY env var) |
| **Config env** | Empty dict `{}` | `{api_key_var, base_url, timeout_ms}` |
| **API Endpoint** | Anthropic | Z.AI (configurable) |
| **API Key Location** | ~/.claude/ (local fs) | OS environment variable |
| **Adapter Override** | Only inherits defaults | Overrides _get_claude_config(), _build_options() |

### Critical Implementation Details

1. **Line 120 in zlm_adapter.py**: `api_key = os.environ.get(api_key_var, "")` — API key is read from OS env, NOT from config
2. **Line 122 in zlm_adapter.py**: `options.env["ANTHROPIC_API_KEY"] = api_key` — Injected into subprocess env dict
3. **Line 116 in zlm_adapter.py**: `options.env["ANTHROPIC_BASE_URL"] = base_url` — Endpoint is config-driven
4. **Line 109 in zlm_adapter.py**: `options = super()._build_options(config)` — Parent class builds base options, ZLM adds auth injections on top
<!-- ID: recommendations -->
## Recommendations

### Immediate Next Steps

1. **Verify ZAI_API_KEY is Set**: Docker environment on Hetzner MUST have `ZAI_API_KEY` env var set before daemon starts. This is NOT in the Dockerfile — it must be injected via secrets or docker-compose env vars.

2. **Test ZLM Auth in Docker**: Deploy and run a test session to confirm:
   ```python
   config = SessionConfig(provider="zlm", model="GLM-5")
   session = await zlm_adapter.create_session(config)
   ```
   If `ZAI_API_KEY` is missing, session will fail with auth error.

3. **Document the Env Var Requirement**: Add to deployment guide:
   - ZLM requires `ZAI_API_KEY` in host environment
   - Set in `docker-compose.yaml` or CI/CD secrets
   - Claude provider does NOT require this (uses ~/.claude/ auth)

### Long-Term Opportunities

1. **Support Custom API Key Variable Names**: Operators can override `api_key_var` in `.council/council.yaml` — useful for organizations with different naming conventions.

2. **Support Custom Z.AI Endpoints**: `base_url` is configurable — operators can point to private Z.AI proxy or other Anthropic-compatible services.

3. **Runtime Validation**: Add health check to verify API key works before accepting sessions:
   ```python
   async def _verify_zlm_credentials():
       api_key = os.environ.get("ZAI_API_KEY")
       if not api_key:
           raise SDKProviderError("ZAI_API_KEY not set")
   ```
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---