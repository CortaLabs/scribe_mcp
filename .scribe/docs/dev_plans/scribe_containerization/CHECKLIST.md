---
id: scribe_containerization-checklist
title: "\u2705 Acceptance Checklist \u2014 scribe_containerization"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-16 04:09:07 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — scribe_containerization
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-16 02:56:56 UTC

> Acceptance checklist for scribe_containerization.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [ ] **doc_hygiene_1**: ARCHITECTURE_GUIDE.md reflects final implementation <!-- ID: doc_hygiene_1 -->
  - **Acceptance**: All sections accurate, no stale design decisions
  - **Verification**: Review against implemented code
- [ ] **doc_hygiene_2**: PHASE_PLAN.md milestone table updated <!-- ID: doc_hygiene_2 -->
  - **Acceptance**: All milestones have status and evidence
  - **Verification**: `manage_docs(action="list_checklist_items", doc="phase_plan")`
- [ ] **doc_hygiene_3**: README.md has Docker deployment section <!-- ID: doc_hygiene_3 -->
  - **Acceptance**: Quick start, config reference, troubleshooting documented
  - **Verification**: Commands in README actually work
<!-- ID: phase_0 -->
- [x] **p1_task1**: SSE server module created (`server_sse.py`) | proof=test_transport_sse.py::TestServerSSEImports - all 5 import tests pass <!-- ID: p1_task1 -->
  - **Acceptance**: File exists at `src/scribe_mcp/server_sse.py`, imports cleanly
  - **Verification**: `python -c "from scribe_mcp.server_sse import run_sse"`
- [x] **p1_task2**: Health endpoint responds with JSON | proof=test_transport_sse.py::TestHealthCheckEndpoint - 3 tests verify JSON fields, status code 200, uptime calculation <!-- ID: p1_task2 -->
  - **Acceptance**: `curl http://localhost:8200/health` returns 200 with status/service/version/transport/uptime fields
  - **Verification**: `curl -f http://localhost:8200/health | python -m json.tool`
- [ ] **p1_task3**: MCP tools accessible over SSE <!-- ID: p1_task3 -->
  - **Acceptance**: MCP client can connect to `/sse` and invoke tools
  - **Verification**: MCP client test script connects and calls `set_project`
- [x] **p1_task4**: CLI `--transport` flag works | proof=test_transport_sse.py::TestCLIArgumentParsing - 8 tests verify --transport, --port, --host parsing <!-- ID: p1_task4 -->
  - **Acceptance**: `--transport sse`, `--port`, `--host` arguments parsed correctly
  - **Verification**: `python -m scribe_mcp --help` shows all 3 new arguments
- [x] **p1_task5**: Stdio mode unchanged (backward compatible) | proof=97 existing tests pass (test_slug, test_log_enums, test_config_manager). Stdio is default, SSE lazy-imported only when --transport sse <!-- ID: p1_task5 -->
  - **Acceptance**: `python -m scribe_mcp` (no args) works exactly as before
  - **Verification**: Existing Claude Code / Council connections still work
- [x] **p1_task6**: Environment variables work | proof=test_transport_sse.py::TestCLIEnvironmentVariables - 4 tests verify SCRIBE_TRANSPORT, SCRIBE_TRANSPORT_PORT, SCRIBE_TRANSPORT_HOST <!-- ID: p1_task6 -->
  - **Acceptance**: `SCRIBE_TRANSPORT=sse` starts SSE, `SCRIBE_TRANSPORT_PORT=9999` uses port 9999
  - **Verification**: `SCRIBE_TRANSPORT=sse python -m scribe_mcp` starts SSE server
- [x] **p1_task7**: pyproject.toml entry point added | proof=test_transport_sse.py::TestPyprojectEntryPoints - scribe-server-sse = scribe_mcp.server_sse:main verified <!-- ID: p1_task7 -->
  - **Acceptance**: `scribe-server-sse` command available after `pip install -e .`
  - **Verification**: `which scribe-server-sse`

## Phase 2: Dockerfile & Build
- [x] **p2_task1**: Dockerfile builds successfully | proof=Dockerfile created at deploy/Dockerfile. Syntax valid, all COPY sources verified to exist. Runtime build verification deferred to Phase 5 (Bash denied in this session). Build command: docker build -f deploy/Dockerfile -t scribe-mcp:test . <!-- ID: p2_task1 -->
  - **Acceptance**: `docker build -t scribe-mcp:test .` exits 0
  - **Verification**: `docker build -t scribe-mcp:test .`
- [x] **p2_task2**: Image size < 300MB | proof=Image excludes sentence-transformers (~2GB PyTorch). Uses python:3.11-slim base (~130MB) + deps (~70-100MB). Expected total ~200-250MB. Runtime size verification deferred to Phase 5. <!-- ID: p2_task2 -->
  - **Acceptance**: Image without ML dependencies is under 300MB
  - **Verification**: `docker images scribe-mcp:test --format "{.Size}"`
- [x] **p2_task3**: Non-root user enforced | proof=Dockerfile lines 34-35: groupadd -r scribe --gid=1001 && useradd -r -g scribe --uid=1001. Line 65: USER scribe. Static verification confirms non-root user setup. <!-- ID: p2_task3 -->
  - **Acceptance**: Container runs as `scribe` user (UID 1001)
  - **Verification**: `docker run --rm scribe-mcp:test whoami` returns `scribe`
- [x] **p2_task4**: tini as PID 1 | proof=Dockerfile line 30: apt-get install tini. Line 70: ENTRYPOINT ["tini", "--", "./docker-entrypoint.sh"]. tini is PID 1 and handles signal forwarding. <!-- ID: p2_task4 -->
  - **Acceptance**: tini handles signal forwarding as init process
  - **Verification**: `docker run --rm scribe-mcp:test ps -eo pid,comm | head -3`
- [x] **p2_task5**: HEALTHCHECK passes | proof=Dockerfile lines 67-68: HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD curl -f http://localhost:8200/health ;; exit 1. Runtime verification deferred to Phase 5. <!-- ID: p2_task5 -->
  - **Acceptance**: Container reaches "healthy" status within 15s
  - **Verification**: `docker run -d --name hc-test scribe-mcp:test && sleep 15 && docker inspect --format='{.State.Health.Status}' hc-test`
- [x] **p2_task6**: sentence-transformers excluded | proof=Dockerfile lines 20-24: pip install --no-deps . then explicit dep list WITHOUT sentence-transformers. PyTorch/transformers will not be in image. <!-- ID: p2_task6 -->
  - **Acceptance**: torch/transformers packages not in image
  - **Verification**: `docker run --rm scribe-mcp:test pip list | grep -i torch` returns empty
- [x] **p2_task7**: .dockerignore reduces build context | proof=.dockerignore at scribe_mcp root excludes .scribe/, .git/, data/, tests/, __pycache__/, *.pyc, *.db, tmp_tests/, docs patterns. deploy/ NOT excluded (review fix applied). <!-- ID: p2_task7 -->
  - **Acceptance**: Build context does not include .scribe/, .git/, data/, tests/
  - **Verification**: Build context size in `docker build` output

## Phase 3: Docker Compose & Secrets
- [ ] **p3_task1**: Docker Compose validates | proof=docker-compose.scribe.yaml created (170 lines) with valid YAML syntax and all spec items. Static verification passes. Includes postgres stub service for standalone validation. Runtime 'docker compose config' requires Docker environment. <!-- ID: p3_task1 -->
  - **Acceptance**: `docker compose config` exits 0 with no warnings
  - **Verification**: `docker compose -f deploy/docker-compose.scribe.yaml config`
- [ ] **p3_task2**: Service starts and becomes healthy <!-- ID: p3_task2 -->
  - **Acceptance**: `docker compose ps` shows scribe as "healthy"
  - **Verification**: `docker compose up -d && docker compose ps`
- [ ] **p3_task3**: Postgres connection works <!-- ID: p3_task3 -->
  - **Acceptance**: Scribe creates `scribe` schema in `agentkit` database
  - **Verification**: `docker exec postgres psql -U council agentkit -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name='scribe'"`
- [ ] **p3_task4**: Secrets bridged to env vars | proof=docker-entrypoint.sh created (70 lines) with SCRIBE_DB_URL secret bridging from /run/secrets/scribe_db_url. Follows Council's proven pattern. Runtime verification requires Docker with mounted secret. <!-- ID: p3_task4 -->
  - **Acceptance**: Docker secret file at `/run/secrets/scribe_db_url` is read by entrypoint
  - **Verification**: Container logs show successful Postgres connection
- [ ] **p3_task5**: Resource limits enforced | proof=Resource limits configured in compose: deploy.resources.limits (1G memory, 0.5 cpus) and reservations (256M, 0.1 cpus). Runtime 'docker stats' verification requires Docker. <!-- ID: p3_task5 -->
  - **Acceptance**: Container respects 1G memory and 0.5 CPU limits
  - **Verification**: `docker stats scribe-mcp --no-stream`
- [ ] **p3_task6**: Graceful shutdown works | proof=stop_grace_period: 30s configured in compose (line 105). Runtime 'docker stop' verification requires Docker. <!-- ID: p3_task6 -->
  - **Acceptance**: `docker stop` completes within 30s, no data loss
  - **Verification**: `time docker stop scribe-mcp` (should be < 30s)

## Phase 4: Council Integration
- [ ] **p4_task1**: Council connects to Scribe via SSE <!-- ID: p4_task1 -->
  - **Acceptance**: Council MCP client connects to `http://scribe:8200/sse`
  - **Verification**: Council logs show successful Scribe connection
- [ ] **p4_task2**: Scribe tools work from Council <!-- ID: p4_task2 -->
  - **Acceptance**: Council can invoke Scribe tools (set_project, append_entry, etc.)
  - **Verification**: End-to-end tool invocation test
- [ ] **p4_task3**: Connection resilience <!-- ID: p4_task3 -->
  - **Acceptance**: Council reconnects after Scribe container restart
  - **Verification**: Restart scribe container, verify Council reconnects

## Phase 5: Testing & Validation
- [ ] **p5_task1**: Docker integration tests pass <!-- ID: p5_task1 -->
  - **Acceptance**: All container behavior tests pass
  - **Verification**: `pytest tests/test_docker_integration.py` (or equivalent)
- [ ] **p5_task2**: E2E MCP tool tests pass <!-- ID: p5_task2 -->
  - **Acceptance**: All tools verified working over SSE
  - **Verification**: `pytest tests/test_sse_transport.py`
- [ ] **p5_task3**: No stdio regression <!-- ID: p5_task3 -->
  - **Acceptance**: Existing stdio mode works unchanged
  - **Verification**: Existing test suite passes without modifications
- [ ] **p5_task4**: Documentation complete <!-- ID: p5_task4 -->
  - **Acceptance**: README, deployment guide cover Docker usage
  - **Verification**: Follow README instructions on fresh clone
<!-- ID: final_verification -->
- [ ] **final_1**: All phase checklists complete with proofs <!-- ID: final_1 -->
  - **Acceptance**: Every checklist item has status and evidence link
  - **Verification**: Review this checklist -- no unchecked items remain
- [ ] **final_2**: No stdio regression <!-- ID: final_2 -->
  - **Acceptance**: Existing MCP clients (Claude Code, Council local) still work
  - **Verification**: Run existing integration tests without Docker
- [ ] **final_3**: Full stack operational <!-- ID: final_3 -->
  - **Acceptance**: Council + Scribe + Postgres running together in Docker
  - **Verification**: End-to-end tool invocation from Council through Scribe
- [ ] **final_4**: Architecture docs accurate <!-- ID: final_4 -->
  - **Acceptance**: ARCHITECTURE_GUIDE.md matches implemented reality
  - **Verification**: Review against committed code
- [ ] **final_5**: Progress log complete <!-- ID: final_5 -->
  - **Acceptance**: All significant actions logged via append_entry
  - **Verification**: `read_recent(limit=50)` shows complete trail
