---
id: council_downstream_cicd-checklist
title: "\u2705 Acceptance Checklist \u2014 council_downstream_cicd"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 09:51:35 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — council_downstream_cicd
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 09:05:17 UTC

> Acceptance checklist for council_downstream_cicd.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Documentation Hygiene

- [x] Architecture guide updated (proof: ARCHITECTURE_GUIDE.md -- all 10 sections written)
- [x] Phase plan current (proof: PHASE_PLAN.md -- 5 phases, 10 task packages)
- [x] Checklist current (proof: this document)
<!-- ID: phase_0 -->
## Phase 0 -- Quick Win
- [x] `deploy/docker-compose.repos.yaml` created with bind mounts (proof: file exists, 31 lines with rom_lab bind mount for council-web + council-daemon)
- [x] `deploy/docker-compose.repos.yaml` added to `.gitignore` (proof: grep .gitignore shows "deploy/docker-compose.repos.yaml")
- [x] `docker compose -f ... -f ... config` validates (proof: `docker compose config --services` returns all 6 services without error)
- [x] Custom pages discoverable in container after restart (proof: filesystem glob finds bizhawk.html.j2 + pokeapi.html.j2 inside container; docker inspect confirms /opt/rom_lab:ro mount; page route returns 307 auth redirect = working)

## Phase 1 -- Repo Sync Engine
- [x] `src/council_mcp/repo_sync.py` created with SyncResult, sync_repo, clone_repo, generate_compose_override (proof: `python -c "from council_mcp.repo_sync import SyncResult, sync_repo, clone_repo, generate_compose_override"` succeeds)
- [x] `get_managed_repos_sync()` added to registry.py (proof: function at line 370, queries council.councils WHERE metadata->>'managed' = 'true')
- [x] `update_council_metadata_sync()` added to registry.py (proof: function at line 385, merges JSONB into council metadata)
- [x] `tests/test_repo_sync.py` passes (proof: 23 passed in 0.38s -- sync_repo 6, clone_repo 6, compose_override 5, webhook_secret 4, registry 2)

## Phase 2 -- Repo CLI
- [ ] `src/council_mcp/cli/repo_cmd.py` created with add/list/sync/remove (proof: `council repo --help`)
- [ ] repo_group registered in main.py (proof: `council repo --help` works)
- [ ] `council repo add --help` shows correct arguments (proof: CLI output)
- [ ] `tests/test_repo_cmd.py` passes (proof: pytest output)

## Phase 3 -- Webhook Endpoint
- [x] `src/council_mcp/web/routes/webhooks.py` created with HMAC verification (proof: `python -c "from council_mcp.web.routes.webhooks import router"` succeeds, route at /api/webhooks/repo-sync)
- [x] Webhook router registered in routes/__init__.py (proof: webhooks_router included before downstream routes)
- [x] HMAC verification rejects invalid signatures (proof: test_invalid_signature_returns_403 PASSED)
- [x] Valid webhook triggers sync + cache clear (proof: test_successful_sync_clears_cache PASSED, verifies clear_cache called with correct Path)
- [x] `tests/test_webhook.py` passes (proof: 14 passed in 1.60s -- HMAC 4, repo resolution 2, sync behavior 3, payload validation 2, signature unit 3)
- [x] `.github/templates/downstream-sync.yml` created (proof: file exists, valid YAML verified with yaml.safe_load)

## Phase 4 -- Deploy Integration + E2E
- [ ] `deploy/scripts/deploy.sh` auto-detects repos override (proof: script inspection)
## Phase 2 -- Repo CLI
- [x] `src/council_mcp/cli/repo_cmd.py` created with add/list/sync/remove (proof: `council repo --help` shows all 4 subcommands: add, list, sync, remove)
- [x] repo_group registered in main.py (proof: import at line 19 + `cli.add_command(repo_group, name="repo")` at line 44)
- [x] `council repo add --help` shows correct arguments (proof: NAME, GIT_URL args + --branch, --clone-dir options all present)
- [x] `tests/test_repo_cmd.py` passes (proof: 23 passed in 0.41s -- add 4, list 5, sync 6, remove 6, help 2)
- [ ] Stakeholder sign-off recorded (name + date).  
- [ ] Retro completed and lessons learned documented.


---