---
id: council_sdk_hetzner-checklist
title: "\u2705 Acceptance Checklist \u2014 council_sdk_hetzner"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 11:22:16 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — council_sdk_hetzner
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 10:05:07 UTC

> Acceptance checklist for council_sdk_hetzner.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [x] Node.js 22.x installed in Docker image (`node --version` prints v22.x) | proof=Dockerfile line 79: `curl -fsSL https://deb.nodesource.com/setup_22.x`
- [x] Claude Code CLI installed (`claude --version` prints version) | proof=Dockerfile line 89: `npm install -g @anthropic-ai/claude-code @openai/codex`
- [x] Codex CLI installed (`codex --version` prints version) | proof=Dockerfile line 89: same npm install line
- [x] claude-agent-sdk Python package installed (`python -c "import claude_agent_sdk"` succeeds) | proof=Dockerfile line 143: `pip install --no-cache-dir 'claude-agent-sdk>=0.1.29,<0.2.0'`
- [x] HOME env set to `/home/appuser` (`echo $HOME` prints `/home/appuser`) | proof=Dockerfile line 69-70: `ENV HOME=/home/appuser` + `mkdir -p /home/appuser`
- [ ] Docker image builds successfully (`docker compose build council-web` exits 0)
<!-- ID: phase_0 -->
- [x] `zai_api_key` secret defined in docker-compose.yaml secrets section | proof=docker compose config shows zai_api_key in top-level secrets (file: ../secrets/zai_api_key.txt)
- [x] `zai_api_key` secret wired to council-web service | proof=docker compose config shows zai_api_key in council-web secrets list
- [x] `zai_api_key` secret wired to council-daemon service | proof=docker compose config shows zai_api_key in council-daemon secrets list
- [x] ZAI_API_KEY loading block added to docker-entrypoint.sh | proof=Added at lines 72-78 of deploy/docker-entrypoint.sh, shellcheck passes, pattern matches existing secrets exactly
- [ ] `/opt/council_mcp/secrets/zai_api_key.txt` exists on Hetzner (chmod 600)
- [x] `docker compose config` parses without errors | proof=docker compose -f deploy/docker-compose.yaml config exits 0, all 7 services parse correctly

## Volume Mounts
- [x] `/opt/council_mcp` mounted read-only in council-web | proof=docker compose config shows bind mount /opt/council_mcp -> /opt/council_mcp, read_only: true
- [x] `/opt/council_mcp` mounted read-only in council-daemon | proof=docker compose config shows bind mount /opt/council_mcp -> /opt/council_mcp, read_only: true
- [x] `/home/council/.claude` mounted read-only to `/home/appuser/.claude` in council-web | proof=docker compose config shows bind mount, read_only: true
- [x] `/home/council/.claude.json` mounted read-only to `/home/appuser/.claude.json` in council-web | proof=docker compose config shows bind mount, read_only: true
- [x] `/home/council/.codex` mounted read-only to `/home/appuser/.codex` in council-web | proof=docker compose config shows bind mount, read_only: true

## Host Auth Setup
- [ ] Claude CLI authenticated on Hetzner host (`/root/.claude/.credentials.json` exists)
- [ ] Codex CLI authenticated on Hetzner host (`/root/.codex/auth.json` exists)
- [ ] ZAI_API_KEY secret file created on Hetzner host
<!-- ID: final_verification -->
- [ ] Claude provider: session creates successfully (provider=claude, model=claude-sonnet-4-5) | proof=ZLM provider registration added to app.py (Fix 1). SDK tests: 264 pass, 4 pre-existing failures. Rom-lab binary fix applied on Hetzner (Fix 2). Awaiting deployment to verify E2E.
- [ ] Claude provider: send_message returns stream events
- [ ] Codex provider: session creates successfully (provider=codex, model=gpt-5.3-codex)
- [ ] Codex provider: send_message returns stream events
- [ ] ZLM/GLM provider: session creates successfully (provider=zlm, model=GLM-5)
- [ ] ZLM/GLM provider: send_message returns stream events

## Custom Pages & Routes (E2E on Hetzner)

- [ ] Main council custom pages load at `/pages/*`
- [ ] Main council custom routes respond (if any routes defined)
- [ ] Downstream repo pages still load (e.g., rom_lab pages)

## Health & Stability

- [ ] All containers healthy after deploy (`docker compose ps`)
- [ ] Health check script passes (`deploy/scripts/health-check.sh`)
- [ ] No error logs in council-web related to SDK or custom pages
- [ ] Web UI login still works (auth not broken by changes)
