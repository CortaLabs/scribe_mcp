---
id: council_sdk_hetzner-research-sdk-provider-config
title: "\U0001F52C Research: SDK Provider Configuration Architecture"
doc_type: RESEARCH_SDK_PROVIDER_CONFIG
doc_name: RESEARCH_SDK_PROVIDER_CONFIG
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 10:08:13 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# 🔬 Research: SDK Provider Configuration Architecture

**Author:** Lens
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-02-17
**Project:** council_sdk_hetzner

> Investigation of SDK provider configuration: how providers (Claude SDK, OpenAI/Codex, GLM/ZLM) are defined, registered, configured, and how GLM integrates with the Claude SDK.

---

## Executive Summary

SDK providers in Council are configured through a **code-driven registration system** combined with **config-driven enablement**. All four providers self-register at import time, but only enabled providers are instantiated. **Confidence: HIGH (source code verified)**.

### Critical Findings

1. **GLM = Claude SDK Wrapper**: GLM models are NOT a separate provider. ZLMAdapter **subclasses ClaudeSDKAdapter** and reuses the Claude Agent SDK binary with environment variable injection.

2. **Provider Architecture**: 4 providers registered via `ProviderRegistry.instance().register(slug, ProviderClass)`:
   - **Claude** (slug="claude") → ClaudeSDKAdapter → claude-agent-sdk binary
   - **Codex** (slug="codex") → CodexCLIAdapter → `codex exec --json` CLI
   - **ZLM/GLM** (slug="zlm") → ZLMAdapter (extends ClaudeSDKAdapter) → claude-agent-sdk with Anthropic API-compatible Z.AI endpoint
   - **Mock** (slug="mock") → MockProvider → in-memory test provider

3. **Configuration Two-Layer Design**:
   - **Code**: `src/council_mcp/config/__init__.py` DEFAULT_CONFIG holds all fallbacks
   - **Runtime**: `.council/council.yaml` overrides code defaults per-repo
   - **Enablement**: `ProviderRegistry.get_enabled_providers()` reads `council.sdk.providers.<slug>.enabled`

4. **Environment Variable Mapping**:
   - **Claude**: ANTHROPIC_API_KEY (standard Anthropic)
   - **ZLM/GLM**: ZAI_API_KEY → injected as ANTHROPIC_API_KEY to Claude SDK subprocess
   - **Codex**: Uses `codex` CLI binary (self-manages LLM routing)
   - **OpenAI**: Currently handled via Codex; separate OpenAI provider planned but not yet implemented

---

## Findings

### Finding 1: Provider Registration Pattern

**Summary**: Providers self-register at module import time via ProviderRegistry singleton.

**Code Evidence**:
- Registration: `/src/council_mcp/sdk/providers/claude_adapter.py` lines 950+, `/src/council_mcp/sdk/providers/zlm_adapter.py` lines 148-152
- Registry: `/src/council_mcp/sdk/provider_registry.py` lines 18-97

**Pattern**:
```python
# At module bottom (claude_adapter.py)
if _sdk_available:
    ProviderRegistry.instance().register("claude", ClaudeSDKAdapter)
```

**Confidence**: HIGH

### Finding 2: GLM Subclass Architecture

**Summary**: ZLMAdapter **extends ClaudeSDKAdapter**, not standalone. It reuses 90% of Claude SDK logic and overrides only:
- `provider_slug` → returns "zlm"
- `_get_claude_config()` → reads from "zlm" config section (not "claude")
- `_build_options()` → injects Z.AI endpoint + API key into ClaudeAgentOptions.env
- `create_session()` → sets provider="zlm" in returned SessionHandle

**Code Evidence**:
- Class definition: `/src/council_mcp/sdk/providers/zlm_adapter.py` lines 41-144
- Parent class: `/src/council_mcp/sdk/providers/claude_adapter.py` lines 111-960

**Implementation Details**:
- ZLM inherits Claude SDK capabilities: streaming, tool approval, session resume/fork, thinking, cost reporting, interrupt
- Z.AI endpoint: configurable via `council.sdk.providers.zlm.env.base_url` (default: "https://api.z.ai/api/anthropic")
- API key: injected from environment variable (configurable via `council.sdk.providers.zlm.env.api_key_var`, default: "ZAI_API_KEY")

**Confidence**: HIGH

### Finding 3: Configuration Structure

**Summary**: SDK providers configured in three locations with precedence: code defaults < config registry < environment.

**Code Evidence**:
- Config defaults: `/src/council_mcp/config/__init__.py` lines 475-618 (DEFAULT_CONFIG["council"]["sdk"])
- Config keys: `/src/council_mcp/config/__init__.py` lines 1080-1240 (CONFIG_SCHEMA entries)

**Configuration Hierarchy** (per provider, e.g., claude):
```yaml
council:
  sdk:
    enabled: false                                    # Master switch
    max_concurrent_sessions: 10                       # Shared across all providers
    providers:
      claude:
        enabled: true                                  # Provider-specific enable
        cli_path: null                                 # Path override (Claude SDK resolves)
        default_model: "claude-sonnet-4-5"            # Default if not in SessionConfig
        fallback_model: "claude-3-5-haiku"            # Fallback if main fails
        models: [list of supported models]            # Validation list
        permission_mode: "default"                     # Tool approval mode
        setting_sources: ["project"]                   # Config priority
        max_budget_usd: 10.0                          # Cost limit
        max_turns: 100                                 # Conversation depth limit
        betas: []                                      # Beta features list
        env: {}                                        # Env var overrides (Claude only)
```

**Confidence**: HIGH

### Finding 4: Provider Enablement via Config

**Summary**: Only providers with `council.sdk.providers.<slug>.enabled: true` are returned by `ProviderRegistry.get_enabled_providers()`.

**Code Evidence**:
- Enablement logic: `/src/council_mcp/sdk/provider_registry.py` lines 87-97
- Usage in SessionManager: `/src/council_mcp/sdk/session_manager.py` calls provider creation

**Default Enablement**:
- Claude: enabled=true (default)
- Codex: enabled=false (requires CLI installed)
- ZLM/GLM: enabled=false (requires Z.AI API key)
- OpenAI: enabled=false (separate provider not yet implemented; use Codex for OpenAI models)

**Confidence**: HIGH

### Finding 5: Claude Code CLI Path Resolution

**Summary**: Claude provider has `cli_path: null` by default, which triggers automatic resolution.

**Code Evidence**:
- Claude SDK client init: `/src/council_mcp/sdk/providers/claude_adapter.py` lines 158-192 (create_session calls `ClaudeSDKClient(options=...)`)
- Options builder: `/src/council_mcp/sdk/providers/claude_adapter.py` lines 350-450 (_build_options)

**Resolution Behavior**:
- Claude Agent SDK automatically searches $PATH for `claude` binary
- If `cli_path` is set in config, it uses that absolute path
- If binary not found and ANTHROPIC_API_KEY not set, session creation fails with SDKProviderError

**Hetzner Deployment Issue**: On Hetzner, if Claude Code CLI (`claude` binary) not in $PATH, sessions will fail. Solution: either install claude CLI or set absolute path in `.council/council.yaml`.

**Confidence**: HIGH

### Finding 6: Environment Variable Mapping for ZLM

**Summary**: ZLM uses environment variable injection to route Claude SDK to Z.AI endpoint.

**Code Evidence**:
- Injection logic: `/src/council_mcp/sdk/providers/zlm_adapter.py` lines 101-135 (_build_options)
- Config schema: `/src/council_mcp/config/__init__.py` lines 1225-1239

**Variables Injected**:
- `ANTHROPIC_BASE_URL` = configured base_url (default: "https://api.z.ai/api/anthropic")
- `ANTHROPIC_API_KEY` = read from environment variable named by `api_key_var` config (default: "ZAI_API_KEY")
- `API_TIMEOUT_MS` = optional timeout (configurable)

**Example `.council/council.yaml` for ZLM**:
```yaml
council:
  sdk:
    providers:
      zlm:
        enabled: true
        default_model: "GLM-5"
        env:
          api_key_var: "ZAI_API_KEY"           # Where to find the API key
          base_url: "https://api.z.ai/api/anthropic"  # Z.AI endpoint
          timeout_ms: 3000000                  # 50 min (production)
```

**Runtime Environment**:
```bash
export ZAI_API_KEY="your-z-ai-api-key"
```

**Confidence**: HIGH

---

## Technical Analysis

### Code Patterns Identified

1. **Lazy Import Pattern**: All providers lazy-import their SDK (claude_agent_sdk, codex SDK, etc.) and set `_sdk_available` flag. If import fails, provider is not registered. Allows graceful degradation.

2. **Adapter Pattern**: Each provider implements the `SDKProvider` ABC (abstract base class) with consistent interface: `create_session()`, `send_message()`, `end_session()`, `resume_session()`, `fork_session()`, `handle_tool_decision()`, `interrupt()`.

3. **Capability Declaration**: Each provider declares capabilities via `ProviderCapabilities` dataclass (supports_streaming, supports_tool_approval, supports_thinking, supports_resume, supports_fork, etc.).

4. **Config-Driven Enablement**: ProviderRegistry filters enabled providers at query time, not at registration. This allows disabling a provider without unloading its module.

### System Interactions

- **Provider Registration**: Happens at module import (when `/src/council_mcp/sdk/providers/__init__.py` is loaded)
- **Provider Instantiation**: Happens in SessionManager.create_session() via `ProviderRegistry.create(slug, **kwargs)`
- **Config Lookup**: SessionManager reads `council.sdk.providers.<slug>.*` settings and passes to provider constructor
- **Environment Variables**: Provider reads from `os.environ` at session creation time (allows runtime changes)

### Risk Assessment

**Risk 1: Missing Claude CLI on Hetzner** (CRITICAL)
- If `claude` binary not installed, Claude sessions will fail
- Mitigation: Ensure claude-agent-sdk installed and `claude` binary in $PATH or set explicit cli_path

**Risk 2: Missing ZAI_API_KEY at Runtime** (HIGH)
- If ZLM enabled but ZAI_API_KEY env var not set, sessions fail with warning
- Mitigation: Ensure ZAI_API_KEY is set in container environment or Docker secrets

**Risk 3: Codex CLI Not Installed** (MEDIUM if Codex enabled)
- If Codex provider enabled but `codex exec` not found, sessions fail
- Mitigation: Only enable Codex if CLI is installed and tested locally first

**Risk 4: Provider Configuration Drift** (LOW)
- If .council/council.yaml missing or incomplete, code defaults apply silently
- Mitigation: Use `council update --config-only` to sync package defaults into repo

---

## Recommendations

### Immediate Next Steps (Hetzner Deployment)

1. **Claude Code Setup on Hetzner**:
   - [ ] Install `claude-agent-sdk>=0.1.29,<0.2.0` in Docker image
   - [ ] Verify `claude --version` works in container
   - [ ] Test session creation with `provider: "claude"` in dev environment
   - [ ] Add ANTHROPIC_API_KEY to Docker secrets

2. **ZLM/GLM Setup** (if using):
   - [ ] Enable ZLM in `.council/council.yaml`: `council.sdk.providers.zlm.enabled: true`
   - [ ] Add ZAI_API_KEY to Docker secrets
   - [ ] Test session creation with `provider: "zlm"` and `model: "GLM-5"`

3. **Codex Setup** (optional):
   - [ ] If Codex needed, install codex CLI on Hetzner or in Docker
   - [ ] Enable in config: `council.sdk.providers.codex.enabled: true`
   - [ ] Test locally first before enabling in production

### Long-Term Opportunities

1. **Separate OpenAI Provider**: Currently OpenAI models routed through Codex. Could implement dedicated OpenAIAdapter for better control.

2. **Provider Health Checks**: Add startup validation to ensure all enabled providers have required dependencies (CLI binaries, API keys).

3. **Provider Metrics**: Track session creation latency, error rates per provider for observability.

4. **Dynamic Provider Discovery**: Scan .council/ for custom provider plugins (similar to custom pages/routes pattern).

---

## Appendix

### References

- **Provider Base Class**: `/src/council_mcp/sdk/provider.py` (SDKProvider ABC, ProviderCapabilities)
- **Provider Registry**: `/src/council_mcp/sdk/provider_registry.py`
- **Claude Adapter**: `/src/council_mcp/sdk/providers/claude_adapter.py` (960 lines, full implementation)
- **ZLM Adapter**: `/src/council_mcp/sdk/providers/zlm_adapter.py` (156 lines, subclass of Claude)
- **Codex Adapter**: `/src/council_mcp/sdk/providers/codex_adapter.py` (2532 lines, CLI wrapper)
- **Config Defaults**: `/src/council_mcp/config/__init__.py` lines 475-618 (DEFAULT_CONFIG)
- **Config Schema**: `/src/council_mcp/config/__init__.py` lines 1080-1240 (CONFIG_SCHEMA)
- **Session Manager**: `/src/council_mcp/sdk/session_manager.py` (consumer of providers)

### Key Files

| File | Lines | Purpose |
|------|-------|---------|
| provider.py | 174 | SDKProvider ABC, ProviderCapabilities |
| provider_registry.py | 97 | Registry singleton, enablement logic |
| claude_adapter.py | 960 | Claude SDK wrapper (full implementation) |
| zlm_adapter.py | 156 | ZLM/GLM wrapper (extends Claude) |
| codex_adapter.py | 2532 | Codex CLI wrapper (standalone) |
| mock_adapter.py | ~100 | Mock provider for testing |
| config/__init__.py | 2878 | DEFAULT_CONFIG + CONFIG_SCHEMA |

---
