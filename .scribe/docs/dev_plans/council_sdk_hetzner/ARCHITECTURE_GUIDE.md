---
id: council_sdk_hetzner-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 council_sdk_hetzner"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 10:21:56 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — council_sdk_hetzner
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 10:05:07 UTC

> Architecture guide for council_sdk_hetzner.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
The Hetzner Docker deployment cannot run SDK sessions. Three root causes:

### 1. No CLI Tools in Docker Image
The `deploy/Dockerfile` base image (`python:3.11-slim`) installs only: libpq-dev, gcc, curl, postgresql-client. No Node.js, no npm, no Claude CLI, no Codex CLI. The `claude-agent-sdk` Python package (required by `ClaudeSDKAdapter`) is not in `pyproject.toml` dependencies.

- **Claude provider**: `ClaudeSDKAdapter` imports `claude_agent_sdk` at runtime (lazy). If not installed, raises `SDKProviderError`. The SDK wraps the `claude` CLI binary (Node.js), so both the Python SDK and the CLI must be present.
- **Codex provider**: `CodexCLIAdapter._ensure_cli_available()` calls `shutil.which("codex")`. Codex is an npm package (`@openai/codex`). Without Node.js + npm, it cannot be installed.
- **ZLM/GLM provider**: `ZLMAdapter` subclasses `ClaudeSDKAdapter`. Same dependency chain — needs `claude-agent-sdk` + `claude` CLI + Node.js.

### 2. No Auth Volume Mounts
SDK sessions spawn worker subprocesses that inherit the container's filesystem. Auth credentials live on the host:
- **Claude**: `~/.claude/.credentials.json` (subscription auth via `claude login`)
- **Codex**: `~/.codex/auth.json` (CLI login auth)
- **ZLM/GLM**: `ZAI_API_KEY` env var (no filesystem auth)

Without volume mounts, Claude and Codex workers cannot authenticate.

### 3. Main Council Custom Pages/Routes Missing
The main council repo (`/opt/council_mcp`) is not mounted into containers. Custom pages at `.council/web/pages/` and routes at `.council/web/routes/` are discovered by scanning `repo_path` at runtime. The Docker image contains a copy of the code (via `COPY . .`), but the `repo_path` in the council registry points to `/opt/council_mcp` (the host path), which does not exist inside the container.

`docker-compose.repos.yaml` already handles downstream repos (e.g., `/opt/rom_lab`), but the main council repo is not included.
<!-- ID: requirements_constraints -->
### Functional Requirements
1. Claude SDK sessions start successfully in `council-web` container
2. Codex CLI sessions start successfully in `council-web` container
3. ZLM/GLM sessions start successfully using ZAI_API_KEY
4. Main council custom pages load at `/pages/*` in production
5. Main council custom routes load from `.council/web/routes/*.py`

### Auth Requirements (CORRECTED from research)
| Provider | Auth Method | Credential Location | Container Needs |
|----------|-------------|---------------------|-----------------|
| Claude | Subscription login | `~/.claude/.credentials.json` | Volume mount `~/.claude/` read-only |
| Codex | CLI login | `~/.codex/auth.json` | Volume mount `~/.codex/` read-only |
| ZLM/GLM | API key env var | `ZAI_API_KEY` in environment | Docker secret file + entrypoint loading |

### Constraints
- **Image size**: Node.js + npm adds ~200MB. Acceptable for production utility.
- **Security**: Auth dirs must be mounted read-only (`:ro`). ZAI_API_KEY must use Docker secrets (not environment variables in compose).
- **Port binding**: All ports stay on `TAILSCALE_IP` — never `0.0.0.0`.
- **Layer caching**: Node.js and npm packages should be installed in a cached layer (before source code copy) to keep rebuilds fast.
- **Existing pattern**: Volume mounts follow the established `docker-compose.repos.yaml` override pattern for downstream repos. Main council repo mount goes in the same file.
- **No code changes**: This is pure infrastructure wiring. No application code modifications.
<!-- ID: architecture_overview -->
### Solution: Three Layers of Change

```
Layer 1: Dockerfile (base stage)
  Add Node.js 22.x + npm
  Add Claude Code CLI (npm -g @anthropic-ai/claude-code)
  Add Codex CLI (npm -g @openai/codex)
  Add claude-agent-sdk Python package

Layer 2: docker-compose.repos.yaml (volume mounts)
  Mount /opt/council_mcp -> /opt/council_mcp (main council repo, :ro)
  Mount ~/.claude/ -> /home/appuser/.claude (Claude auth, :ro)
  Mount ~/.codex/ -> /home/appuser/.codex (Codex auth, :ro)

Layer 3: Secrets + Entrypoint
  Add zai_api_key secret file
  Add entrypoint.sh loading for ZAI_API_KEY
  Ensure HOME is set for CLI auth discovery
```

### Provider Dependency Chain

```
Claude Provider:
  Python: claude-agent-sdk>=0.1.29,<0.2.0 (pip)
  Binary: claude CLI (Node.js, npm)
  Auth: ~/.claude/.credentials.json (volume mount from host)
  
Codex Provider:
  Binary: codex CLI (Node.js, npm @openai/codex)
  Auth: ~/.codex/auth.json (volume mount from host)
  
ZLM/GLM Provider:
  Python: claude-agent-sdk (same as Claude — ZLM is a subclass)
  Binary: claude CLI (same as Claude — ZLM reuses it)
  Auth: ZAI_API_KEY env var -> injected as ANTHROPIC_API_KEY into subprocess
  Endpoint: ANTHROPIC_BASE_URL -> https://api.z.ai/api/anthropic (config-driven)
```

### Custom Pages/Routes Fix

The template loader in `web/template_loader.py` calls `discover_pages(repo_path)` where `repo_path` comes from the council registry. On Hetzner, `repo_path=/opt/council_mcp`. The container sees this path only if it is volume-mounted. Adding the main council repo to `docker-compose.repos.yaml` follows the existing pattern for downstream repos and fixes both pages and routes simultaneously.

**No application code changes needed** — the discovery system already works; it just needs the filesystem to be accessible.
<!-- ID: detailed_design -->
### 1. Dockerfile Changes (`deploy/Dockerfile`, base stage)

Insert Node.js installation BEFORE the pip install layers (after system deps, ~line 60):

```dockerfile
# --------------------------------------------------------------------------
# Node.js 22.x LTS (required for Claude Code CLI and Codex CLI)
# --------------------------------------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------
# CLI tools for SDK providers (cached until package versions change)
# --------------------------------------------------------------------------
RUN npm install -g @anthropic-ai/claude-code @openai/codex && \
    npm cache clean --force
```

After the existing pip install layers (~line 105), add `claude-agent-sdk`:

```dockerfile
# SDK provider Python package (Claude Agent SDK)
RUN pip install --no-cache-dir 'claude-agent-sdk>=0.1.29,<0.2.0'
```

**Decision: Install in Dockerfile, not at runtime.**
- Startup cost: 0 seconds (pre-installed).
- Image size: +~250MB (Node.js + npm packages + Python SDK). Acceptable — current image is ~1.5GB with PyTorch.
- Deterministic: pinned versions, reproducible builds.

**Decision: HOME env var for CLI auth.**
The Claude CLI looks for auth at `$HOME/.claude/`. The Codex CLI looks at `$HOME/.codex/`. Set `ENV HOME=/home/appuser` in the Dockerfile and mount auth dirs there.

```dockerfile
# Ensure HOME is set for CLI auth discovery
ENV HOME=/home/appuser
RUN mkdir -p /home/appuser
```

### 2. Volume Mounts (`deploy/docker-compose.repos.yaml`)

Add main council repo + CLI auth dirs. This file is auto-generated and `.gitignore`d (Hetzner-specific):

```yaml
services:
  council-web:
    volumes:
      - /opt/rom_lab:/opt/rom_lab:ro
      - /opt/council_mcp:/opt/council_mcp:ro       # Main council custom pages/routes
      - /root/.claude:/home/appuser/.claude:ro      # Claude CLI auth
      - /root/.codex:/home/appuser/.codex:ro        # Codex CLI auth

  council-daemon:
    volumes:
      - /opt/rom_lab:/opt/rom_lab:ro
      - /opt/council_mcp:/opt/council_mcp:ro        # Main council custom pages/routes
```

**Notes:**
- On Hetzner, the operator user is `root` (Docker host). Auth dirs are at `/root/.claude/` and `/root/.codex/`.
- If the operator runs as non-root, adjust source paths accordingly.
- Only `council-web` needs CLI auth dirs (SDK sessions are spawned from the web process).
- Both `council-web` and `council-daemon` need the main council repo (daemon proxies Scribe, web serves pages/routes).
- All mounts are `:ro` — containers never write to mounted repos or auth dirs.

### 3. ZAI_API_KEY Secret

Add new secret file and wire it through:

**File on Hetzner:** `/opt/council_mcp/secrets/zai_api_key.txt`
```bash
echo -n "your-zai-api-key" > /opt/council_mcp/secrets/zai_api_key.txt
chmod 600 /opt/council_mcp/secrets/zai_api_key.txt
```

**docker-compose.yaml additions:**

In secrets section:
```yaml
secrets:
  # ... existing secrets ...
  zai_api_key:
    file: ../secrets/zai_api_key.txt
```

In `council-web` service:
```yaml
secrets:
  - database_url
  - api_key
  - openai_api_key
  - scribe_db_url
  - zai_api_key          # NEW
```

### 4. Entrypoint Changes (`deploy/docker-entrypoint.sh`)

Add ZAI_API_KEY loading block after the existing OPENAI_API_KEY block (~line 70):

```bash
# --- Z.AI API Key (for ZLM/GLM provider) ---
# Used by ZLMAdapter to authenticate with Z.AI's Anthropic-compatible endpoint.
if [ -z "${ZAI_API_KEY}" ] && [ -f /run/secrets/zai_api_key ]; then
    export ZAI_API_KEY
    ZAI_API_KEY="$(cat /run/secrets/zai_api_key)"
    echo "[entrypoint] Loaded ZAI_API_KEY from Docker secret"
fi
```

### 5. Host Setup (Hetzner, One-Time)

These are manual steps performed once on the Hetzner host:

```bash
# 1. Install and authenticate Claude CLI on host
npm install -g @anthropic-ai/claude-code
claude login    # Follow browser auth flow, creates /root/.claude/.credentials.json

# 2. Install and authenticate Codex CLI on host
npm install -g @openai/codex
codex login     # Creates /root/.codex/auth.json

# 3. Create ZAI_API_KEY secret
echo -n "your-zai-api-key" > /opt/council_mcp/secrets/zai_api_key.txt
chmod 600 /opt/council_mcp/secrets/zai_api_key.txt
```

**Why authenticate on host?** The Docker container mounts auth dirs read-only. Auth tokens are created by CLI login flows that require browser interaction. Once created on the host, the container reuses them indefinitely (tokens auto-refresh).
<!-- ID: directory_structure -->
| File | Change Type | Description |
|------|-------------|-------------|
| `deploy/Dockerfile` | MODIFY | Add Node.js, npm, CLI tools, claude-agent-sdk, HOME env |
| `deploy/docker-compose.yaml` | MODIFY | Add zai_api_key secret definition, add secret to council-web |
| `deploy/docker-compose.repos.yaml` | MODIFY | Add main council + CLI auth volume mounts |
| `deploy/docker-entrypoint.sh` | MODIFY | Add ZAI_API_KEY loading from secret |
| `/opt/council_mcp/secrets/zai_api_key.txt` | CREATE (Hetzner) | Z.AI API key secret file |
<!-- ID: data_storage -->
### Claude Provider Auth Flow (Container)
```
1. Container starts with HOME=/home/appuser
2. Volume mount: /root/.claude -> /home/appuser/.claude (ro)
3. SDK worker spawns: python -m council_mcp.sdk.worker --provider claude
4. Worker instantiates ClaudeSDKAdapter -> ClaudeSDKClient(options)
5. ClaudeSDKClient spawns `claude` CLI subprocess
6. `claude` CLI reads $HOME/.claude/.credentials.json
7. Authenticated API calls to Anthropic
```

### Codex Provider Auth Flow (Container)
```
1. Container starts with HOME=/home/appuser
2. Volume mount: /root/.codex -> /home/appuser/.codex (ro)
3. SDK worker spawns: python -m council_mcp.sdk.worker --provider codex
4. Worker instantiates CodexCLIAdapter
5. CodexCLIAdapter spawns `codex exec --json` subprocess
6. `codex` CLI reads $HOME/.codex/auth.json
7. Authenticated API calls to OpenAI
```

### ZLM/GLM Provider Auth Flow (Container)
```
1. Entrypoint loads ZAI_API_KEY from /run/secrets/zai_api_key
2. ZAI_API_KEY exported as env var
3. SDK worker spawns: python -m council_mcp.sdk.worker --provider zlm
4. Worker instantiates ZLMAdapter (extends ClaudeSDKAdapter)
5. ZLMAdapter._build_options() reads os.environ["ZAI_API_KEY"]
6. Injects ANTHROPIC_API_KEY=<zai_key> + ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
7. ClaudeSDKClient spawns `claude` CLI with modified env
8. `claude` CLI calls Z.AI endpoint instead of Anthropic
```
<!-- ID: testing_strategy -->
### Build Verification (Local, before deploy)
```bash
# Build the Docker image (verify no build errors)
docker compose -f deploy/docker-compose.yaml build council-web

# Verify Node.js and CLIs are in the image
docker run --rm council-web node --version       # Should print v22.x
docker run --rm council-web claude --version      # Should print claude version
docker run --rm council-web codex --version       # Should print codex version
docker run --rm council-web python -c "import claude_agent_sdk; print('OK')"
```

### Deployment Verification (Hetzner)
```bash
# 1. Start the stack
docker compose -f deploy/docker-compose.yaml -f deploy/docker-compose.repos.yaml up -d

# 2. Verify custom pages load
curl -s http://council-hub:8015/pages/ | grep -q "200\|html"

# 3. Verify CLI tools inside container
docker exec council-web claude --version
docker exec council-web codex --version
docker exec council-web python -c "import claude_agent_sdk; print('OK')"

# 4. Verify auth dirs are mounted
docker exec council-web ls /home/appuser/.claude/.credentials.json
docker exec council-web ls /home/appuser/.codex/auth.json

# 5. Verify ZAI_API_KEY is loaded
docker exec council-web env | grep ZAI_API_KEY

# 6. Test session creation (via API)
curl -X POST http://council-hub:8015/api/sdk/sessions/create \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"provider": "claude", "model": "claude-sonnet-4-5"}' 

curl -X POST http://council-hub:8015/api/sdk/sessions/create \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"provider": "codex", "model": "gpt-5.3-codex"}'

curl -X POST http://council-hub:8015/api/sdk/sessions/create \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"provider": "zlm", "model": "GLM-5"}'
```
<!-- ID: deployment_operations -->
### Deploy Sequence (After Changes Merged)
```bash
# 1. Push changes
git push origin master

# 2. On Hetzner: pull + rebuild + restart
ssh council-hub "cd /opt/council_mcp && \
  ./deploy/scripts/backup-postgres.sh && \
  git pull && \
  docker compose -f deploy/docker-compose.yaml build && \
  docker compose -f deploy/docker-compose.yaml -f deploy/docker-compose.repos.yaml up -d --remove-orphans && \
  ./deploy/scripts/health-check.sh"
```

### Rollback
If SDK sessions break the web container:
```bash
ssh council-hub "cd /opt/council_mcp && \
  git checkout HEAD~1 -- deploy/Dockerfile deploy/docker-compose.yaml deploy/docker-entrypoint.sh && \
  docker compose -f deploy/docker-compose.yaml build && \
  docker compose -f deploy/docker-compose.yaml up -d"
```

### Image Size Impact
- Before: ~1.5GB (Python + PyTorch CPU + agentkit)
- After: ~1.75GB (+Node.js 22 ~100MB, +npm packages ~100MB, +claude-agent-sdk ~5MB)
- Acceptable trade-off for production SDK capability.
<!-- ID: open_questions -->
| Item | Owner | Status | Decision |
|------|-------|--------|----------|
| Claude CLI auth token expiry | Operator | OPEN | Monitor — if tokens expire, re-run `claude login` on host |
| Codex CLI auth token expiry | Operator | OPEN | Monitor — if tokens expire, re-run `codex login` on host |
| Node.js version pinning | Forge | DECIDED | Use NodeSource 22.x LTS (current LTS) |
| claude-agent-sdk version | Forge | DECIDED | Pin to `>=0.1.29,<0.2.0` (matches adapter imports) |
| Codex npm package version | Forge | DECIDED | Install latest `@openai/codex` (CLI auto-updates) |
| HOME dir ownership | Forge | DECIDED | `ENV HOME=/home/appuser` + `mkdir -p` in Dockerfile |
| Auth mount source paths | Operator | ASSUMPTION | Assuming Hetzner host runs as root (paths: `/root/.claude/`, `/root/.codex/`) |
<!-- ID: references_appendix -->
### Research Documents
- `RESEARCH_HETZNER_DOCKER_SDK_STATE.md` — Current Docker image analysis (HIGH confidence)
- `RESEARCH_SDK_PROVIDER_CONFIG.md` — Provider registration and config architecture
- `RESEARCH_SDK_SESSION_ARCHITECTURE.md` — Session lifecycle, worker spawning, UDS protocol
- `RESEARCH_ZLM_GLM_AUTH_EXACT.md` — ZLM auth mechanism with exact code references

### Key Source Files
| File | Lines | Relevance |
|------|-------|-----------|
| `deploy/Dockerfile` | 201 | Docker image definition (MODIFY) |
| `deploy/docker-compose.yaml` | 584 | Service definitions, secrets (MODIFY) |
| `deploy/docker-compose.repos.yaml` | 30 | Volume mount overrides (MODIFY) |
| `deploy/docker-entrypoint.sh` | 164 | Secret loading (MODIFY) |
| `src/council_mcp/sdk/providers/claude_adapter.py` | 960 | Claude SDK adapter (READ ONLY) |
| `src/council_mcp/sdk/providers/codex_adapter.py` | 2532 | Codex CLI adapter (READ ONLY) |
| `src/council_mcp/sdk/providers/zlm_adapter.py` | 156 | ZLM/GLM adapter (READ ONLY) |
| `src/council_mcp/config/__init__.py` | 2878 | DEFAULT_CONFIG with SDK section (READ ONLY) |
| `.council/council.yaml` | 724 | Runtime config (READ ONLY — already correct) |

### External References
- Claude Agent SDK: `pip install claude-agent-sdk` (Python wrapper for Claude CLI)
- Claude Code CLI: `npm install -g @anthropic-ai/claude-code` (Node.js)
- Codex CLI: `npm install -g @openai/codex` (Node.js)
- NodeSource: `https://deb.nodesource.com/setup_22.x` (Node.js APT repo)
