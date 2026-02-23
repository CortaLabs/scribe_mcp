
# 🔬 Research Sdk Session Architecture — council_sdk_hetzner
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 10:06:46 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
The Council SDK session system enables multi-turn interactive sessions with code-executing agents (Claude Code, Codex/OpenAI, GLM). The architecture uses a **daemon-owned process pool** with **Unix Domain Socket (UDS) communication** between parent (daemon) and child (worker) processes.

**Primary Objective:** Understand session lifecycle, worker spawning, provider registry, Docker requirements, environment variables, and ProcessManager integration.

**Key Takeaways:**
- **ProviderRegistry pattern:** Providers (Claude, Codex, Mock, ZLM) self-register at import time; registry is a singleton mapping provider slugs to SDKProvider subclasses
- **Worker spawning:** WorkerPool uses ProcessManager to spawn workers via `python -m council_mcp.sdk.worker` with config passed as JSON args
- **Provider execution:** Claude uses claude-agent-sdk Python package; Codex invokes `codex` CLI binary with subprocess; both communicate back to daemon via UDS
- **Docker requirements:** Container must have Python SDK packages (claude-agent-sdk) and CLI binaries (codex) available on PATH or configured via config
- **Configuration:** All behavior config-driven via `.council/council.yaml` under `council.sdk.*` section
- **ProcessManager integration:** SDK worker processes register via `ProcessType.SDK_SESSION`


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** atlas

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.

### Finding 1: Session Lifecycle Flow (Web → Daemon → Worker)
- **Summary:** Session creation follows a request chain: (1) Web UI calls SessionManager.create_session(), (2) SessionManager inserts DB row and spawns worker via WorkerPool, (3) WorkerPool starts process via ProcessManager with `python -m council_mcp.sdk.worker`, (4) Worker establishes UDS connection and sends "ready" notification, (5) SessionManager sends create_session RPC to worker over UDS, (6) Worker instantiates SDKProvider and returns session ID.
- **Evidence:** 
  - `src/council_mcp/sdk/session_manager.py:124-355` — create_session() method documents full flow
  - `src/council_mcp/sdk/worker_pool.py:471-550` — create_session spawns process, manages UDS connection
  - `src/council_mcp/sdk/worker.py:1-22` — CLI args, lifecycle stages (ready → create_session → message loop → end_session)
- **Confidence:** HIGH

### Finding 2: Provider Registry Pattern
- **Summary:** SDK providers (Claude, Codex, Mock, ZLM) are self-registering singleton classes. ProviderRegistry.instance() returns a singleton holding a dict of slug → provider_class. Providers register at import time in web app lifespan or during direct init. Registry.create(slug, **kwargs) instantiates the provider.
- **Evidence:**
  - `src/council_mcp/sdk/provider_registry.py:18-97` — ProviderRegistry singleton implementation, get_enabled_providers() filters by config
  - `src/council_mcp/web/app.py:86-105` — Web app registers: "mock", "claude" (try/except for optional install), "codex" (try/except), others loaded at import
  - `src/council_mcp/sdk/provider.py:36-163` — SDKProvider abstract base class defines interface
- **Confidence:** HIGH

### Finding 3: Worker Spawning via ProcessManager
- **Summary:** WorkerPool.create_session() builds a command `[sys.executable, "-m", "council_mcp.sdk.worker", "--provider", slug, "--session-id", uuid, "--uds-path", path, "--config-json", json.dumps(config)]` and calls ProcessManager.spawn(ProcessType.SDK_SESSION, config). ProcessManager creates OS process, tracks in SQLite registry, registers with system health monitor.
- **Evidence:**
  - `src/council_mcp/sdk/worker_pool.py:500-525` — command construction and ProcessManager.spawn() call with ProcessType.SDK_SESSION
  - `src/council_mcp/process_manager.py` — ProcessManager owns all subprocess lifecycle (spawn, health, stop, orphan recovery)
  - `src/council_mcp/sdk/worker.py:55-127` — SDKWorker.run() enters UDS server loop, waits for "ready" client connect
- **Confidence:** HIGH

### Finding 4: Provider-Specific Execution Modes
- **Summary:** 
  - **Claude:** Uses claude-agent-sdk Python package. ClaudeSDKAdapter imports ClaudeAgentOptions, ClaudeSDKClient, creates client with config, calls async methods (create_session, send_message, handle_tool_decision).
  - **Codex:** Invokes CLI binary `codex exec --json` via asyncio.create_subprocess_exec(). Parses JSONL streamed from subprocess stdout. Reads approval decisions from stdin if approval protocol detected.
  - **Mock:** Synchronous stub for testing (no external binary/SDK required).
  - **ZLM (GLM):** Uses Claude SDK (treated as a model variant, not a separate provider in current codebase).
- **Evidence:**
  - `src/council_mcp/sdk/providers/claude_adapter.py:1-150` — ClaudeSDKAdapter, lazy imports of claude-agent-sdk, SDKProviderError if not installed
  - `src/council_mcp/sdk/providers/codex_adapter.py:125-150, 1435-1495, 400-435` — CodexCLIAdapter, _build_command() constructs CLI args, asyncio.create_subprocess_exec() invokes binary, _ensure_cli_available() checks PATH
  - `src/council_mcp/sdk/providers/mock_adapter.py` — MockSDKProvider stub
- **Confidence:** HIGH

### Finding 5: Docker Container Requirements
- **Summary:** For Hetzner production deployment, the Docker image must include:
  - Python SDK packages: `claude-agent-sdk>=0.1.29,<0.2.0` (for Claude provider)
  - CLI binaries: `codex` CLI binary on PATH (for Codex provider), configured via `council.sdk.providers.codex.cli_path` or defaults to "codex"
  - Environment variables: Provider API keys (e.g., ANTHROPIC_API_KEY for Claude, OpenAI key for Codex if needed)
  - All above MUST be present before WorkerPool.create_session() is called, else subprocess fails with SDKProviderError
- **Evidence:**
  - `src/council_mcp/sdk/providers/claude_adapter.py:120-127` — Raises SDKProviderError if claude-agent-sdk not installed
  - `src/council_mcp/sdk/providers/codex_adapter.py:2498-2514` — _ensure_cli_available() checks shutil.which("codex") or configured path, raises SDKProviderError if not found
  - `src/council_mcp/web/app.py:96-105` — try/except during provider registration logs warnings but doesn't fail web startup
- **Confidence:** HIGH

### Finding 6: UDS Communication Protocol
- **Summary:** Worker establishes UDS server at uds_path. Daemon connects as client. Communication uses JSON-RPC 2.0: daemon sends requests (create_session, send_message, handle_tool_decision, end_session, interrupt, health), worker sends responses and notifications (stream_event notifications with type, seq, delta/input/output/cost/approval/error fields). UDSClient and UDSServer in uds_protocol.py handle framing and notification routing.
- **Evidence:**
  - `src/council_mcp/sdk/uds_protocol.py` — UDSServer, UDSClient, JSON-RPC framing, notification handler callback
  - `src/council_mcp/sdk/worker.py:131-150` — _handle_request() dispatches methods, returns result dict
  - `src/council_mcp/sdk/worker_pool.py:62-102` — _construct_event() maps notification payloads to StreamEvent subclasses
- **Confidence:** HIGH

### Additional Notes
- Config section `council.sdk.*` controls: max_concurrent_sessions, worker_startup_timeout_seconds, session_create_timeout_seconds, uds_socket_dir, warm_pool_size, providers.{slug}.enabled, providers.{slug}.config
- Warm pool (optional): WorkerPool can maintain pre-spawned workers to reduce session latency if warm_pool_size > 0
- StreamBridge buffers streamed events and broadcasts to WebSocket clients; no direct connection from worker to web UI
- SDK is disabled by default (enabled=false in config); must be explicitly enabled in `.council/council.yaml`


---
## Technical Analysis
<!-- ID: technical_analysis -->

**Code Patterns Identified:**
- **Singleton ProviderRegistry:** Self-registering pattern for extensibility; providers must be registered before use. Registration happens at import time or during app startup.
- **UDS-based IPC:** Unix Domain Sockets with JSON-RPC 2.0 for inter-process communication. Avoids network stack overhead; secure by filesystem permissions.
- **Async subprocess handling:** CodexCLIAdapter uses asyncio.create_subprocess_exec() with PIPE for stdin/stdout/stderr. Enables concurrent message processing without blocking.
- **Lazy imports in adapters:** try/except imports for optional dependencies (claude-agent-sdk, codex CLI) allow graceful degradation if not installed.
- **Config-driven worker spawning:** All spawn parameters (timeouts, socket dir, pool size) read from config at runtime; no hardcoding.

**System Interactions:**
- **Web → SessionManager → WorkerPool:** Web UI is request initiator; SessionManager coordinates; WorkerPool manages subprocess lifecycle.
- **SessionManager ↔ WorkerPool:** One-way requests + async event streaming back. SessionManager owns session DB records; WorkerPool owns process lifecycle.
- **Worker ↔ SDKProvider:** Worker instantiates provider (Claude SDK or Codex CLI wrapper); provider does the actual work (send_message, handle_tool_decision).
- **StreamBridge:** Buffers worker stream events and broadcasts to WebSocket clients. Decouples worker lifecycle from client connections.
- **ProcessManager:** Owns all SDK worker processes. Tracks in SQLite registry. Handles restart logic and health monitoring.
- **Database:** SDK sessions stored in `sdk_sessions` table with config_json blob. Status transitions: created → active → ended.

**Risk Assessment:**
- **Missing binaries in Docker:** If `codex` CLI not installed on Hetzner, CodexCLIAdapter raises SDKProviderError on first session creation. Mitigation: Ensure Dockerfile includes codex binary or use explicit cli_path config.
- **Missing Python packages:** If claude-agent-sdk not installed, ClaudeSDKAdapter raises SDKProviderError. Web startup tolerates missing adapters (try/except), but first Claude session creation fails. Mitigation: Pin version in Dockerfile requirements.txt.
- **UDS socket directory permissions:** If /tmp (default uds_socket_dir) has restrictive permissions, subprocess cannot create sockets. Mitigation: Ensure /tmp is world-writable or configure custom socket dir in `.council/council.yaml`.
- **Provider API key availability:** ClaudeSDKClient reads ANTHROPIC_API_KEY from environment; CodexCLIAdapter may need OpenAI key. If not set, provider fails during create_session. Mitigation: Set env vars in Docker run or via docker-compose secrets.
- **Config not loaded:** If `.council/council.yaml` missing or malformed, get_council_config() falls back to DEFAULT_CONFIG. SDK may work with minimal config, but provider-specific settings ignored. Mitigation: Validate config syntax before deployment.


---
## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps (For Hetzner Deployment)
- **Install SDK dependencies in Dockerfile:** Add `claude-agent-sdk>=0.1.29,<0.2.0` to `deploy/Dockerfile` base image layer or vendor wheel.
- **Verify Codex CLI availability:** Confirm `codex` binary is installed in Hetzner Docker image or set explicit `council.sdk.providers.codex.cli_path` config pointing to installed location.
- **Set provider API keys:** Ensure ANTHROPIC_API_KEY and/or OpenAI API key are set in docker-compose.yaml secrets or env vars before starting containers.
- **Enable SDK in config:** Add `council.sdk.enabled: true` and `council.sdk.providers.{claude,codex}.enabled: true` to `.council/council.yaml` on Hetzner server.
- **Validate UDS socket dir:** Ensure `/tmp` (default) is writable and has adequate permissions, or configure custom socket dir in config.
- **Test session creation:** Run integration test to verify `POST /api/sdk/sessions/create` succeeds with each enabled provider.

### Long-Term Opportunities
- **Provider auto-discovery:** Detect available providers at startup (check PATH for codex, try importing claude-agent-sdk) instead of hardcoding registration order.
- **Warm pool tuning:** Profile worker startup times to optimize warm_pool_size for minimal latency without wasting resources.
- **Cross-provider cost aggregation:** Extend CostTracker to normalize pricing across Claude, Codex, GLM for unified billing/budgeting.
- **Session persistence:** Implement session resume/fork persistence to SQLite for long-running agent workloads.
- **Provider healthchecks:** Add periodic health probes for each enabled provider (test create_session + immediate end_session) to detect missing binaries/keys early.


---
## Appendix
<!-- ID: appendix -->

### Key Source Files
- `src/council_mcp/sdk/provider_registry.py` — ProviderRegistry singleton, registration mechanism
- `src/council_mcp/sdk/provider.py` — SDKProvider abstract base class, ProviderCapabilities, SDKProviderError
- `src/council_mcp/sdk/session_manager.py` — SessionManager orchestrator, create_session, send_message lifecycle
- `src/council_mcp/sdk/worker_pool.py` — WorkerPool process spawn, UDS client, event queue management, warm pool
- `src/council_mcp/sdk/worker.py` — SDKWorker subprocess entry point, JSON-RPC server, provider initialization
- `src/council_mcp/sdk/types.py` — SessionConfig, SessionHandle, SessionRecord, StreamEvent types
- `src/council_mcp/sdk/uds_protocol.py` — UDSServer, UDSClient, JSON-RPC 2.0 framing
- `src/council_mcp/sdk/providers/claude_adapter.py` — ClaudeSDKAdapter, claude-agent-sdk wrapper
- `src/council_mcp/sdk/providers/codex_adapter.py` — CodexCLIAdapter, codex CLI subprocess wrapper
- `src/council_mcp/sdk/stream_bridge.py` — StreamBridge, WebSocket event broadcasting
- `src/council_mcp/web/app.py` — Web lifespan, SDK initialization, provider registration

### Configuration Reference
```yaml
# .council/council.yaml
council:
  sdk:
    enabled: true  # Enable/disable entire SDK module
    max_concurrent_sessions: 10
    worker_startup_timeout_seconds: 30
    session_create_timeout_seconds: 60
    uds_socket_dir: /tmp
    uds_socket_prefix: council_sdk_
    warm_pool_size: 0  # Pre-spawned workers per provider (0 = disabled)
    warm_pool_idle_timeout_seconds: 300
    warm_pool_check_interval_seconds: 30
    providers:
      claude:
        enabled: true
        # Defaults for claude-agent-sdk config (overridable per session)
        model: claude-sonnet-4
      codex:
        enabled: true
        cli_path: codex  # "codex" on PATH or absolute path
        # Additional Codex settings per session via metadata
```

### Database Schema
```sql
-- SDK sessions table (in public schema)
CREATE TABLE sdk_sessions (
    id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT,
    config_json TEXT,
    status TEXT DEFAULT 'created',  -- created, active, ended
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    worker_pid INTEGER,
    sdk_session_id TEXT
);
```

### Testing Checklist
- [ ] Verify Claude provider registration on startup (check logs for "Registered SDK provider: claude")
- [ ] Verify Codex provider registration on startup (check logs for "Registered SDK provider: codex")
- [ ] Test create_session with provider=claude, model=claude-sonnet-4 (should return session_id)
- [ ] Test create_session with provider=codex, model=codex-4 (should return session_id)
- [ ] Test send_message to Claude session (should receive stream events)
- [ ] Test send_message to Codex session (should receive stream events)
- [ ] Test session end (should clean up UDS socket and worker process)
- [ ] Test missing claude-agent-sdk (should log warning on registration, not fail web startup)
- [ ] Test missing codex binary (should log warning on registration, not fail web startup)
- [ ] Test missing API key (first session creation should fail with SDKProviderError)


---