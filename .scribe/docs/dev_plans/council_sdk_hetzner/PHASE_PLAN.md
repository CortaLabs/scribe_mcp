---
id: council_sdk_hetzner-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 council_sdk_hetzner"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 10:23:23 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — council_sdk_hetzner
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-17 10:05:07 UTC

> Execution roadmap for council_sdk_hetzner.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Name | Scope | Est. Effort | Dependencies |
|-------|------|-------|-------------|--------------|
| 0 | Docker Image + Compose | Dockerfile, docker-compose.yaml, entrypoint | 1 Forge session | None |
| 1 | Volume Mounts + Host Setup | docker-compose.repos.yaml, host auth | 1 Forge session + manual | Phase 0 |
| 2 | Verify All Providers | E2E testing, troubleshooting | Manual on Hetzner | Phase 0 + 1 |

**Total: 2 Forge sessions + manual verification steps.**
All phases modify infrastructure files only — zero application code changes.
<!-- ID: phase_0 -->
**Objective:** Install all SDK dependencies in the Docker image, add ZAI_API_KEY secret, update entrypoint.

### Task Package 0.1: Dockerfile — Add Node.js + CLI Tools + Python SDK

**Scope**: Add Node.js 22.x, Claude Code CLI, Codex CLI, claude-agent-sdk, and HOME env to the Dockerfile base stage.
**Files to Modify**: `deploy/Dockerfile`
**Dependencies**: None

#### Specifications

1. **After the system deps block (line 60), before pip install, add Node.js 22.x LTS:**
   ```dockerfile
   RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
       apt-get install -y --no-install-recommends nodejs && \
       rm -rf /var/lib/apt/lists/*
   ```

2. **Add CLI tools (after Node.js install):**
   ```dockerfile
   RUN npm install -g @anthropic-ai/claude-code @openai/codex && \
       npm cache clean --force
   ```

3. **After the existing pip install layers (after line 105), add claude-agent-sdk:**
   ```dockerfile
   RUN pip install --no-cache-dir 'claude-agent-sdk>=0.1.29,<0.2.0'
   ```

4. **Set HOME env for CLI auth discovery (before COPY . .):**
   ```dockerfile
   ENV HOME=/home/appuser
   RUN mkdir -p /home/appuser
   ```

#### Verification
- [ ] `docker compose -f deploy/docker-compose.yaml build council-web` succeeds
- [ ] `docker run --rm <image> node --version` prints v22.x
- [ ] `docker run --rm <image> claude --version` prints a version string
- [ ] `docker run --rm <image> codex --version` prints a version string
- [ ] `docker run --rm <image> python -c "import claude_agent_sdk; print('OK')"` prints OK

#### Out of Scope (DO NOT TOUCH)
- `src/` directory (no application code changes)
- `pyproject.toml` (claude-agent-sdk is a runtime dep, not a build dep)
- `deploy/docker-compose.yaml` (separate task)
- `.council/council.yaml` (already correct)

---

### Task Package 0.2: docker-compose.yaml — Add ZAI_API_KEY Secret

**Scope**: Add the `zai_api_key` secret definition and wire it to `council-web` and `council-daemon`.
**Files to Modify**: `deploy/docker-compose.yaml`
**Dependencies**: None (can run in parallel with 0.1)

#### Specifications

1. **In the `secrets:` section (after line 584), add:**
   ```yaml
   zai_api_key:
     file: ../secrets/zai_api_key.txt
   ```

2. **In the `council-web` service `secrets:` list (after line 278), add:**
   ```yaml
   - zai_api_key
   ```

3. **In the `council-daemon` service `secrets:` list, add:**
   ```yaml
   - zai_api_key
   ```

#### Verification
- [ ] `docker compose -f deploy/docker-compose.yaml config` parses without errors (after creating a dummy secret file)
- [ ] The `zai_api_key` secret appears in both `council-web` and `council-daemon` service configs

#### Out of Scope (DO NOT TOUCH)
- Volume mounts (separate task in Phase 1)
- Port bindings
- Resource limits
- Any other service definitions

---

### Task Package 0.3: docker-entrypoint.sh — Load ZAI_API_KEY

**Scope**: Add ZAI_API_KEY loading from Docker secrets in the entrypoint script.
**Files to Modify**: `deploy/docker-entrypoint.sh`
**Dependencies**: None (can run in parallel with 0.1 and 0.2)

#### Specifications

1. **After the OPENAI_API_KEY block (after line 70), add:**
   ```bash
   # --- Z.AI API Key (for ZLM/GLM provider) ---
   # Used by ZLMAdapter to authenticate with Z.AI's Anthropic-compatible endpoint.
   if [ -z "${ZAI_API_KEY}" ] && [ -f /run/secrets/zai_api_key ]; then
       export ZAI_API_KEY
       ZAI_API_KEY="$(cat /run/secrets/zai_api_key)"
       echo "[entrypoint] Loaded ZAI_API_KEY from Docker secret"
   fi
   ```

#### Verification
- [ ] `shellcheck deploy/docker-entrypoint.sh` passes (or no new warnings)
- [ ] The ZAI_API_KEY block follows the exact same pattern as existing secret blocks

#### Out of Scope (DO NOT TOUCH)
- Existing secret loading blocks (DATABASE_URL, COUNCIL_API_KEY, etc.)
- Auto-bootstrap section
- Exec command at end of file
<!-- ID: phase_1 -->
**Objective:** Wire up volume mounts for main council repo and CLI auth dirs. Perform one-time host setup.

### Task Package 1.1: docker-compose.repos.yaml — Add Main Council + Auth Mounts

**Scope**: Update the repos override file to mount the main council repo and CLI auth directories.
**Files to Modify**: `deploy/docker-compose.repos.yaml`
**Dependencies**: Phase 0 complete (HOME=/home/appuser must be set in image)

#### Specifications

1. **Replace the entire file content with:**
   ```yaml
   # =============================================================================
   # Downstream Council Repo Mounts — Compose Override
   # =============================================================================
   #
   # AUTO-GENERATED by council repo management
   # Do not edit manually -- regenerated by `council repo add/remove`
   #
   # Purpose:
   #   Bind-mounts downstream council repos into the web and daemon containers
   #   so the template loader can discover custom pages, static assets, and
   #   route modules at runtime. Also mounts CLI auth dirs for SDK providers.
   #
   # Usage:
   #   docker compose -f docker-compose.yaml -f docker-compose.repos.yaml up -d
   #
   # Notes:
   #   - All mounts are read-only (:ro) — containers never write to repos
   #   - Paths match the Hetzner layout (/opt/<repo_name>)
   #   - This file is .gitignored — it is Hetzner-specific
   #
   # =============================================================================

   services:
     council-web:
       volumes:
         - /opt/rom_lab:/opt/rom_lab:ro
         - /opt/council_mcp:/opt/council_mcp:ro
         - /root/.claude:/home/appuser/.claude:ro
         - /root/.codex:/home/appuser/.codex:ro

     council-daemon:
       volumes:
         - /opt/rom_lab:/opt/rom_lab:ro
         - /opt/council_mcp:/opt/council_mcp:ro
   ```

2. **Verify the mount source paths exist on Hetzner:**
   ```bash
   ssh council-hub "ls -d /opt/council_mcp /root/.claude /root/.codex"
   ```
   If `/root/.claude` or `/root/.codex` do not exist, they must be created in the Host Setup task.

#### Verification
- [ ] `docker compose -f deploy/docker-compose.yaml -f deploy/docker-compose.repos.yaml config` parses without errors
- [ ] `council-web` service shows all 4 volume mounts in config output
- [ ] `council-daemon` service shows 2 volume mounts in config output

#### Out of Scope (DO NOT TOUCH)
- `deploy/docker-compose.yaml` (main compose, modified in Phase 0)
- `deploy/Dockerfile` (modified in Phase 0)
- Any application source code

---

### Task Package 1.2: Hetzner Host Setup (MANUAL — Operator)

**Scope**: One-time setup steps on the Hetzner host to install CLIs, authenticate, and create the ZAI_API_KEY secret.
**Files to Modify**: None in repo (host-only operations)
**Dependencies**: None (can start anytime, but must complete before Phase 2 verification)

#### Steps

```bash
# 1. Ensure Node.js is on host (for CLI auth flows)
ssh council-hub "node --version || (curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs)"

# 2. Install and authenticate Claude CLI
ssh council-hub "npm install -g @anthropic-ai/claude-code && claude login"
# Follow the browser auth flow. Creates /root/.claude/.credentials.json

# 3. Install and authenticate Codex CLI
ssh council-hub "npm install -g @openai/codex && codex login"
# Follow the auth flow. Creates /root/.codex/auth.json

# 4. Create ZAI_API_KEY secret file
ssh council-hub "echo -n 'YOUR_ZAI_API_KEY_HERE' > /opt/council_mcp/secrets/zai_api_key.txt && chmod 600 /opt/council_mcp/secrets/zai_api_key.txt"

# 5. Verify auth dirs exist
ssh council-hub "ls /root/.claude/.credentials.json /root/.codex/auth.json /opt/council_mcp/secrets/zai_api_key.txt"
```

#### Verification
- [ ] `/root/.claude/.credentials.json` exists on Hetzner host
- [ ] `/root/.codex/auth.json` exists on Hetzner host
- [ ] `/opt/council_mcp/secrets/zai_api_key.txt` exists with correct permissions (600)
- [ ] `claude --version` works on Hetzner host
- [ ] `codex --version` works on Hetzner host
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| P0.1: Dockerfile updated | 2026-02-17 | Forge | Pending | Build succeeds + CLI verification |
| P0.2: docker-compose.yaml ZAI secret | 2026-02-17 | Forge | Pending | Config parse test |
| P0.3: Entrypoint ZAI loading | 2026-02-17 | Forge | Pending | Pattern match test |
| P1.1: Volume mounts in repos.yaml | 2026-02-17 | Forge | Pending | Config parse test |
| P1.2: Host CLI setup | 2026-02-17 | Operator | Pending | SSH verification |
| P2: Deploy + verify all providers | 2026-02-17 | Operator | Pending | Session create API tests |
| P2: Custom pages load | 2026-02-17 | Operator | Pending | curl /pages/ returns HTML |
<!-- ID: retro_notes -->
**Objective:** Deploy the changes to Hetzner and verify all three providers work E2E.

### Deploy Steps
```bash
# 1. Push all changes
git push origin master

# 2. Deploy on Hetzner
ssh council-hub "cd /opt/council_mcp && \
  ./deploy/scripts/backup-postgres.sh && \
  git pull && \
  docker compose -f deploy/docker-compose.yaml build && \
  docker compose -f deploy/docker-compose.yaml -f deploy/docker-compose.repos.yaml up -d --remove-orphans && \
  ./deploy/scripts/health-check.sh"
```

### Verification Checklist
1. **Custom pages**: Navigate to `http://council-hub:8015/pages/` — pages from main council load
2. **Claude session**: Create session via web UI with provider=claude — session starts without error
3. **Codex session**: Create session via web UI with provider=codex — session starts without error  
4. **ZLM/GLM session**: Create session via web UI with provider=zlm — session starts without error
5. **Container health**: `docker compose ps` shows all services healthy

### Troubleshooting Guide
| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `claude: command not found` in container | Node.js/npm install failed in Dockerfile | Check build logs for npm errors |
| `SDKProviderError: claude-agent-sdk not installed` | pip install failed | Check Dockerfile pip layer |
| Claude session auth error | `~/.claude/` not mounted or empty | Verify volume mount, re-run `claude login` on host |
| Codex session auth error | `~/.codex/` not mounted or empty | Verify volume mount, re-run `codex login` on host |
| ZLM session fails with "API key not found" | ZAI_API_KEY not loaded | Check secret file exists, entrypoint loads it |
| Custom pages 404 | `/opt/council_mcp` not mounted | Check docker-compose.repos.yaml mounts |
| Custom pages 404 but mount exists | `repo_path` in council registry differs | Verify council registry has correct repo_path |
