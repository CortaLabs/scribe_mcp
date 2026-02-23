---
id: council_env_enforcement-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 council_env_enforcement"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-18 07:35:57 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — council_env_enforcement
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-18 07:17:54 UTC

> Architecture guide for council_env_enforcement.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement

**Context:** Council MCP, AgentKit, and Scribe MCP rely on environment variables for credentials, infrastructure config, and feature flags. Three `.env.example` files exist (root, deploy, .council scaffold) but they are out of sync with each other and with the code that reads them.

**The Problem (quantified from research):**
- **23 dead declarations**: Variables listed in `.env.example` that no code ever reads (e.g., `REDIS_PASSWORD`, `EMBED_OPENAI_API_KEY`, all `POSTGRES_SUPERUSER_*`, all `SCRIBE_POSTGRES_*` families)
- **43+ undocumented reads**: Variables read by code (`os.getenv()`) that are not listed in any `.env.example` (32 Scribe vars, 11 Council vars)
- **4 default value mismatches**: Root vs deploy `.env.example` have different defaults for the same variables (`SCRIBE_STORAGE_BACKEND`, `POSTGRES_USER`, `DATABASE_URL`, `POSTGRES_ADMIN_*`)
- **No startup validation**: Missing required variables cause cryptic errors deep in the stack rather than clear fail-fast messages at boot
- **Scope confusion**: Root `.env.example` conflates council_mcp-owned vars, agentkit-owned vars, and scribe_mcp-owned vars in a single file

**Goals:**
1. `.env.example` becomes a machine-verifiable contract: every var declared is read, every var read is declared
2. Startup validation catches missing required vars before any service logic runs
3. Dead declarations are removed; undocumented reads are added
4. Root/deploy/scaffold `.env.example` files have identical variable sets with context-appropriate defaults
5. A CI-runnable linter enforces bidirectional parity going forward

**Non-Goals:**
- Moving COUNCIL_* config overrides into `.env.example` (they belong in `council.yaml` per existing separation)
- Changing the AgentKit or Scribe codebases (out of scope; we fix council_mcp's contract only)
- Redesigning the Docker secrets loading pattern (it works correctly)

**Success Metrics:**
- `council env check` passes with zero drift on every CI run
- `council start` refuses to boot with clear error when required vars are missing
- Docker container startup validates required vars before `exec "$@"`
- Zero dead declarations in any `.env.example` file
<!-- ID: requirements_constraints -->
## 2. Requirements & Constraints

**Functional Requirements:**
1. **Env Schema Module** (`src/council_mcp/config/env_schema.py`): Single source of truth defining every env var with name, required/optional status, default value, description, and owner (council_mcp/agentkit/scribe_mcp/system)
2. **Startup Validator**: Callable from `council start` and `docker-entrypoint.sh` that checks all required vars are set, reports all missing vars in a single error message (not one-at-a-time), and exits non-zero
3. **CLI Linter** (`council env check`): Bidirectional parity check — scans Python source for `os.getenv()`/`os.environ` reads and cross-references against the schema; reports undeclared reads and unused declarations
4. **.env.example Generator** (`council env generate`): Produces `.env.example` from the schema with grouped sections, comments, and context-appropriate defaults (local vs Docker)
5. **Docker Entrypoint Integration**: `docker-entrypoint.sh` calls the validator after secret loading and before auto-bootstrap
6. **Dead Var Cleanup**: Remove 23 dead declarations from all `.env.example` files

**Non-Functional Requirements:**
- Validation runs in <100ms (no network calls, no DB access)
- Schema module has zero external dependencies (stdlib only) so it can be imported from shell scripts via `python -c`
- Backward compatible: existing `.env` files continue to work
- No changes to sibling repos (agentkit, scribe_mcp)

**Assumptions:**
- `python-dotenv` is available in the Docker image (already a dependency)
- The env var override pattern in `config/__init__.py` (COUNCIL_TRANSPORT__*, etc.) stays as-is; these are config overrides, not infrastructure vars
- Docker secrets loading in `docker-entrypoint.sh` stays as-is

**Risks & Mitigations:**
| Risk | Impact | Mitigation |
|------|--------|------------|
| Schema drifts from code over time | Parity breaks silently | CI gate runs `council env check` on every PR |
| Validator blocks legitimate startup | Service downtime | `COUNCIL_SKIP_ENV_CHECK=1` escape hatch |
| Deploy `.env` has different var set than root | Deploy breaks | Generator produces both from same schema with context flag |
<!-- ID: architecture_overview -->
## 3. Architecture Overview

**Solution Summary:** A declarative env var schema module serves as the single source of truth. All `.env.example` files are generated from it. Startup validation and CI linting both read from the same schema.

**Component Diagram:**
```
                        env_schema.py
                    (source of truth)
                   /        |        \
                  /         |         \
    council env check    Validator    council env generate
    (CI linter)       (startup)      (.env.example writer)
         |               |                |
    Scans Python     Called by:       Produces:
    source for       - council start  - .env.example (root)
    os.getenv()      - entrypoint.sh  - deploy/.env.example
    calls                             - .council/.env.example
```

**Component Breakdown:**

1. **EnvVar dataclass** (`env_schema.py`)
   - Fields: `name`, `required`, `default_local`, `default_docker`, `description`, `group`, `owner`, `secret`
   - `owner` = which repo/component owns the var: `"council"`, `"agentkit"`, `"scribe"`, `"docker"`, `"system"`
   - `secret` = True for vars that should never have values in `.env.example` (API keys, passwords)
   - `group` = section grouping for `.env.example` output (e.g., "Database", "LLM", "Scribe")
   - Registry: `ENV_SCHEMA: list[EnvVar]` — the complete list of all env vars

2. **validate_env()** function (`env_schema.py`)
   - Input: optional context flag (`"local"` or `"docker"`)
   - Reads `os.environ`, checks all `required=True` vars are set and non-empty
   - Returns `list[str]` of error messages (empty = valid)
   - Pure function: no side effects, no imports beyond stdlib

3. **council env check** CLI command (`cli/env_cmd.py`)
   - Scans `src/council_mcp/**/*.py` for `os.getenv("VAR")` and `os.environ["VAR"]` and `os.environ.get("VAR")` patterns
   - Cross-references against `ENV_SCHEMA`
   - Reports: (a) vars in code but not in schema, (b) vars in schema but not read by code
   - Exit code: 0 = clean, 1 = drift detected
   - Excludes system vars (HOME, USER, TERM, etc.) via `owner="system"` filter

4. **council env generate** CLI command (`cli/env_cmd.py`)
   - Reads `ENV_SCHEMA`, groups by `group` field
   - Outputs `.env.example` with comments and defaults
   - `--context local` uses `default_local`, `--context docker` uses `default_docker`
   - `--target root|deploy|scaffold` controls output path
   - Secret vars get empty values with `# REQUIRED` comment

5. **Startup validation hook**
   - `council start` calls `validate_env(context="local")` before spawning daemon
   - `docker-entrypoint.sh` calls `python -m council_mcp.config.env_schema validate` after secret loading
   - Both fail with formatted error listing ALL missing vars

**Data Flow:**
```
Developer edits env_schema.py
  -> runs `council env generate` to update .env.example files
  -> CI runs `council env check` to verify code <-> schema parity
  -> At runtime, validate_env() blocks startup if required vars missing
```

**External Integrations:**
- AgentKit: Vars owned by agentkit are declared in schema with `owner="agentkit"` but NOT modified in agentkit source
- Scribe MCP: Vars owned by scribe are declared in schema with `owner="scribe"` but NOT modified in scribe source
- Docker secrets: `docker-entrypoint.sh` loads secrets first, THEN calls validator
<!-- ID: detailed_design -->
## 4. Detailed Design

### 4.1 EnvVar Schema Definition

```python
# src/council_mcp/config/env_schema.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import os
import sys

@dataclass(frozen=True, slots=True)
class EnvVar:
    """Declaration of a single environment variable."""
    name: str
    required: bool = False
    default_local: str = ""
    default_docker: str = ""
    description: str = ""
    group: str = "Other"
    owner: str = "council"     # council | agentkit | scribe | docker | system
    secret: bool = False       # True = never show value in .env.example
    conditional: str = ""      # e.g., "required if SCRIBE_STORAGE_BACKEND=postgres"
    include_in_dotenv: bool = True  # False = omit from .env.example (tuning vars)

# --- The Schema ---
ENV_SCHEMA: list[EnvVar] = [
    # ========== Database (Required) ==========
    EnvVar(
        name="DATABASE_URL",
        required=True,
        default_local="postgresql://user:password@localhost:5432/agentkit",
        default_docker="postgresql://council:CHANGE_ME@postgres:5432/agentkit",
        description="PostgreSQL connection string (AgentKit primary)",
        group="Database",
        owner="agentkit",
        secret=True,
    ),
    EnvVar(
        name="POSTGRES_APP_USER",
        required=True,
        default_local="",
        default_docker="council",
        description="Application database user",
        group="Database",
        owner="agentkit",
    ),
    EnvVar(
        name="POSTGRES_APP_PASSWORD",
        required=True,
        default_local="",
        default_docker="CHANGE_ME",
        description="Application database password",
        group="Database",
        owner="agentkit",
        secret=True,
    ),
    EnvVar(
        name="POSTGRES_HOST",
        required=False,
        default_local="localhost",
        default_docker="postgres",
        description="PostgreSQL hostname",
        group="Database",
        owner="agentkit",
    ),
    EnvVar(
        name="POSTGRES_PORT",
        required=False,
        default_local="5432",
        default_docker="5432",
        description="PostgreSQL port",
        group="Database",
        owner="agentkit",
    ),
    EnvVar(
        name="POSTGRES_APP_DB",
        required=False,
        default_local="agentkit",
        default_docker="agentkit",
        description="Application database name",
        group="Database",
        owner="agentkit",
    ),
    EnvVar(
        name="POSTGRES_USER",
        required=False,
        default_local="postgres",
        default_docker="council",
        description="PostgreSQL superuser name (used by Postgres container init)",
        group="Database",
        owner="docker",
    ),
    EnvVar(
        name="POSTGRES_PASSWORD",
        required=False,
        default_local="",
        default_docker="",
        description="PostgreSQL superuser password (Docker secret: pg_password.txt)",
        group="Database",
        owner="docker",
        secret=True,
        conditional="Required for Docker bootstrap; derived from Docker secret in entrypoint",
    ),

    # ========== Admin Credentials (AgentKit init/schema migration) ==========
    # These are consumed by AgentKit's init.py:882-886 and schema_manager.py.
    # In Docker, docker-entrypoint.sh DERIVES these from POSTGRES_PASSWORD.
    # Locally, only needed if running agentkit-schema plan/apply directly.
    EnvVar(
        name="POSTGRES_ADMIN_USER",
        required=False,
        default_local="",
        default_docker="council",
        description="Admin user for schema migrations (AgentKit init)",
        group="Admin Credentials",
        owner="agentkit",
        conditional="Required for agentkit init/schema migration; Docker derives from pg_password",
    ),
    EnvVar(
        name="POSTGRES_ADMIN_PASSWORD",
        required=False,
        default_local="",
        default_docker="CHANGE_ME",
        description="Admin password for schema migrations",
        group="Admin Credentials",
        owner="agentkit",
        secret=True,
        conditional="Required for agentkit init/schema migration; Docker derives from pg_password",
    ),
    EnvVar(
        name="POSTGRES_ADMIN_HOST",
        required=False,
        default_local="",
        default_docker="postgres",
        description="Admin host for schema migrations",
        group="Admin Credentials",
        owner="agentkit",
        conditional="Required for agentkit init/schema migration",
    ),
    EnvVar(
        name="POSTGRES_ADMIN_PORT",
        required=False,
        default_local="",
        default_docker="5432",
        description="Admin port for schema migrations",
        group="Admin Credentials",
        owner="agentkit",
        conditional="Required for agentkit init/schema migration",
    ),
    EnvVar(
        name="POSTGRES_ADMIN_DB",
        required=False,
        default_local="",
        default_docker="agentkit",
        description="Admin database for schema migrations",
        group="Admin Credentials",
        owner="agentkit",
        conditional="Required for agentkit init/schema migration",
    ),

    # ========== Superuser Credentials (AgentKit init fallback) ==========
    # Read by AgentKit config/loader.py:580-584. Fallback chain for bootstrap.
    # NOT required at runtime. Used by agentkit init if ADMIN vars insufficient.
    EnvVar(
        name="POSTGRES_SUPERUSER_USER",
        required=False,
        default_local="",
        default_docker="",
        description="PostgreSQL superuser (AgentKit init fallback). Defaults to POSTGRES_USER.",
        group="Admin Credentials",
        owner="agentkit",
        conditional="AgentKit init fallback only; defaults to POSTGRES_USER if unset",
    ),
    EnvVar(
        name="POSTGRES_SUPERUSER_PASSWORD",
        required=False,
        default_local="",
        default_docker="",
        description="PostgreSQL superuser password (AgentKit init fallback)",
        group="Admin Credentials",
        owner="agentkit",
        secret=True,
        conditional="AgentKit init fallback only; defaults to POSTGRES_PASSWORD if unset",
    ),
    EnvVar(
        name="POSTGRES_SUPERUSER_HOST",
        required=False,
        default_local="",
        default_docker="",
        description="PostgreSQL superuser host (AgentKit init fallback)",
        group="Admin Credentials",
        owner="agentkit",
        conditional="AgentKit init fallback only",
    ),
    EnvVar(
        name="POSTGRES_SUPERUSER_PORT",
        required=False,
        default_local="",
        default_docker="",
        description="PostgreSQL superuser port (AgentKit init fallback)",
        group="Admin Credentials",
        owner="agentkit",
        conditional="AgentKit init fallback only",
    ),
    EnvVar(
        name="POSTGRES_SUPERUSER_DB",
        required=False,
        default_local="",
        default_docker="",
        description="PostgreSQL superuser database (AgentKit init fallback)",
        group="Admin Credentials",
        owner="agentkit",
        conditional="AgentKit init fallback only",
    ),

    # ========== App Default User (AgentKit init) ==========
    # Read by AgentKit config/loader.py:630-636. Used during init for default user creation.
    EnvVar(
        name="APP_DEFAULT_USER_EMAIL",
        required=False,
        default_local="",
        default_docker="",
        description="Default user email (AgentKit init)",
        group="App Defaults",
        owner="agentkit",
        conditional="Used by agentkit init for default user creation",
    ),
    EnvVar(
        name="APP_DEFAULT_USER_NAME",
        required=False,
        default_local="",
        default_docker="",
        description="Default user name (AgentKit init)",
        group="App Defaults",
        owner="agentkit",
        conditional="Used by agentkit init for default user creation",
    ),
    EnvVar(
        name="APP_DEFAULT_USER_PASSWORD",
        required=False,
        default_local="",
        default_docker="",
        description="Default user password (AgentKit init)",
        group="App Defaults",
        owner="agentkit",
        secret=True,
        conditional="Used by agentkit init for default user creation",
    ),

    # ========== API Keys ==========
    EnvVar(
        name="OPENAI_API_KEY",
        required=False,
        description="OpenAI LLM API key (required if using OpenAI provider)",
        group="API Keys",
        owner="council",
        secret=True,
        conditional="Required if council.llm.primary_provider or fallback uses OpenAI",
    ),
    EnvVar(
        name="EMBED_OPENAI_API_KEY",
        required=False,
        description="OpenAI embeddings API key (AgentKit, falls back to OPENAI_API_KEY)",
        group="API Keys",
        owner="agentkit",
        secret=True,
        conditional="Read by AgentKit config/loader.py:565; falls back to OPENAI_API_KEY",
    ),
    EnvVar(
        name="ZAI_API_KEY",
        required=False,
        description="Z.AI provider API key (Anthropic-compatible endpoint)",
        group="API Keys",
        owner="council",
        secret=True,
    ),
    EnvVar(
        name="COUNCIL_API_KEY",
        required=False,
        description="Council web UI auth key (starts with ck_; Docker secret: api_key.txt)",
        group="API Keys",
        owner="council",
        secret=True,
    ),
    EnvVar(
        name="REDIS_PASSWORD",
        required=False,
        description="Redis connection password (AgentKit, currently unused at runtime)",
        group="API Keys",
        owner="agentkit",
        secret=True,
        conditional="Read by AgentKit config/loader.py:566; no active Redis usage",
    ),

    # ========== Scribe MCP (Runtime) ==========
    EnvVar(
        name="SCRIBE_DB_URL",
        required=False,
        description="Scribe PostgreSQL connection string (Docker secret: scribe_db_url.txt)",
        group="Scribe MCP",
        owner="scribe",
        secret=True,
        conditional="Required if SCRIBE_STORAGE_BACKEND=postgres",
    ),
    EnvVar(
        name="SCRIBE_STORAGE_BACKEND",
        required=False,
        default_local="sqlite",
        default_docker="postgres",
        description="Scribe storage backend: sqlite, postgres, or auto",
        group="Scribe MCP",
        owner="scribe",
    ),
    EnvVar(
        name="SCRIBE_USER",
        required=False,
        default_local="austin",
        default_docker="austin",
        description="Scribe agent user name",
        group="Scribe MCP",
        owner="scribe",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_SCHEMA",
        required=False,
        default_local="scribe",
        default_docker="scribe",
        description="PostgreSQL schema name for Scribe tables",
        group="Scribe MCP",
        owner="scribe",
    ),

    # ========== Scribe Bootstrap (AgentKit consumed inside Scribe container) ==========
    # These SCRIBE_POSTGRES_ADMIN_* vars are consumed by AgentKit's schema/init system
    # when running INSIDE the Scribe container. The Lens research incorrectly classified
    # these as "dead" because it only grepped scribe_mcp source, not AgentKit source.
    # AgentKit reads the non-prefixed versions (POSTGRES_ADMIN_*) which Scribe's
    # bootstrap_postgres.py maps from the SCRIBE_POSTGRES_* prefixed equivalents.
    EnvVar(
        name="SCRIBE_POSTGRES_ADMIN_USER",
        required=False,
        default_local="",
        default_docker="council",
        description="Scribe schema admin user (consumed by AgentKit inside Scribe container)",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_ADMIN_PASSWORD",
        required=False,
        default_local="",
        default_docker="CHANGE_ME",
        description="Scribe schema admin password",
        group="Scribe Bootstrap",
        owner="scribe",
        secret=True,
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_ADMIN_HOST",
        required=False,
        default_local="",
        default_docker="postgres",
        description="Scribe schema admin host",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_ADMIN_PORT",
        required=False,
        default_local="",
        default_docker="5432",
        description="Scribe schema admin port",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_ADMIN_DB",
        required=False,
        default_local="",
        default_docker="agentkit",
        description="Scribe schema admin database",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_APP_USER",
        required=False,
        default_local="",
        default_docker="council",
        description="Scribe app database user (consumed by AgentKit inside Scribe container)",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_APP_PASSWORD",
        required=False,
        default_local="",
        default_docker="CHANGE_ME",
        description="Scribe app database password",
        group="Scribe Bootstrap",
        owner="scribe",
        secret=True,
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_APP_HOST",
        required=False,
        default_local="",
        default_docker="postgres",
        description="Scribe app database host",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_APP_PORT",
        required=False,
        default_local="",
        default_docker="5432",
        description="Scribe app database port",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_APP_DB",
        required=False,
        default_local="",
        default_docker="agentkit",
        description="Scribe app database name",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="Required for Scribe schema bootstrap via AgentKit",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_SUPERUSER_USER",
        required=False,
        default_local="",
        default_docker="",
        description="Scribe superuser (AgentKit init fallback inside Scribe container)",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="AgentKit init fallback inside Scribe container",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_SUPERUSER_PASSWORD",
        required=False,
        default_local="",
        default_docker="",
        description="Scribe superuser password",
        group="Scribe Bootstrap",
        owner="scribe",
        secret=True,
        conditional="AgentKit init fallback inside Scribe container",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_SUPERUSER_HOST",
        required=False,
        default_local="",
        default_docker="",
        description="Scribe superuser host",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="AgentKit init fallback inside Scribe container",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_SUPERUSER_PORT",
        required=False,
        default_local="",
        default_docker="",
        description="Scribe superuser port",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="AgentKit init fallback inside Scribe container",
    ),
    EnvVar(
        name="SCRIBE_POSTGRES_SUPERUSER_DB",
        required=False,
        default_local="",
        default_docker="",
        description="Scribe superuser database",
        group="Scribe Bootstrap",
        owner="scribe",
        conditional="AgentKit init fallback inside Scribe container",
    ),

    # ========== Scribe Operational (optional, not in .env.example by default) ==========
    # These are Scribe tuning vars that ARE read by code but too numerous/noisy
    # for .env.example. The schema tracks them so `council env check` does not
    # flag them as drift, but they are omitted from generated .env.example.
    EnvVar(name="SCRIBE_LOG_RATE_LIMIT_COUNT", required=False, default_local="0", default_docker="0", description="Rate limit entries per window", group="Scribe Tuning", owner="scribe", include_in_dotenv=False),
    EnvVar(name="SCRIBE_LOG_RATE_LIMIT_WINDOW", required=False, default_local="0", default_docker="0", description="Rate limit window seconds", group="Scribe Tuning", owner="scribe", include_in_dotenv=False),
    EnvVar(name="SCRIBE_LOG_MAX_BYTES", required=False, default_local="524288", default_docker="524288", description="Progress log rotation size", group="Scribe Tuning", owner="scribe", include_in_dotenv=False),
    EnvVar(name="SCRIBE_DEFAULT_PROJECT", required=False, default_local="", default_docker="", description="Default project when none selected", group="Scribe Tuning", owner="scribe", include_in_dotenv=False),

    # ========== Deployment ==========
    EnvVar(
        name="ENVIRONMENT",
        required=False,
        default_local="dev",
        default_docker="dev",
        description="Deployment environment: dev, staging, or production",
        group="Deployment",
        owner="council",
    ),

    # ========== System Vars (excluded from .env.example and linter) ==========
    EnvVar(name="HOME", owner="system", description="User home directory", include_in_dotenv=False),
    EnvVar(name="USER", owner="system", description="Current user name", include_in_dotenv=False),
    EnvVar(name="TERM", owner="system", description="Terminal type", include_in_dotenv=False),
    EnvVar(name="TERM_PROGRAM", owner="system", description="Terminal program", include_in_dotenv=False),
    EnvVar(name="SHELL", owner="system", description="User shell", include_in_dotenv=False),
    EnvVar(name="COLORTERM", owner="system", description="Color terminal support", include_in_dotenv=False),
    EnvVar(name="TMUX", owner="system", description="tmux session", include_in_dotenv=False),
    EnvVar(name="STY", owner="system", description="GNU Screen session", include_in_dotenv=False),
    EnvVar(name="SSH_CONNECTION", owner="system", description="SSH connection info", include_in_dotenv=False),
    EnvVar(name="SSH_TTY", owner="system", description="SSH TTY", include_in_dotenv=False),
    EnvVar(name="VSCODE_PID", owner="system", description="VS Code process ID", include_in_dotenv=False),
    EnvVar(name="PYTHONPATH", owner="system", description="Python module path", include_in_dotenv=False),
    EnvVar(name="UVICORN_RELOAD_ACTIVE", owner="system", description="Uvicorn reload marker (set internally)", include_in_dotenv=False),
    EnvVar(name="XDG_CONFIG_HOME", owner="system", description="XDG config directory", include_in_dotenv=False),

    # ========== Docker Orchestration (deploy-context only) ==========
    EnvVar(
        name="TAILSCALE_IP",
        required=False,
        default_local="127.0.0.1",
        default_docker="127.0.0.1",
        description="Tailscale IP for port binding (deploy/.env only)",
        group="Docker Orchestration",
        owner="docker",
        include_in_dotenv=False,  # Only in deploy/.env, managed separately
    ),
    EnvVar(
        name="AGENTKIT_SKIP_AUTO_BOOTSTRAP",
        required=False,
        default_local="0",
        default_docker="0",
        description="Skip agentkit auto-bootstrap in Docker entrypoint",
        group="Docker Orchestration",
        owner="docker",
        include_in_dotenv=False,
    ),

    # ========== Internal Config Overrides (NOT in .env.example) ==========
    # COUNCIL_TRANSPORT__*, COUNCIL_LLM__*, COUNCIL_PROMPTS__*, etc.
    # These are council.yaml config overrides via env vars.
    # They are registered in schema so the linter can exclude them,
    # but they do NOT belong in .env.example.
    EnvVar(name="COUNCIL_CONFIG_PATH", owner="council", description="Override council.yaml path", include_in_dotenv=False),
    EnvVar(name="COUNCIL_WORKSPACE", owner="council", description="Override workspace detection", include_in_dotenv=False),
    EnvVar(name="COUNCIL_PROJECT", owner="council", description="Project identification override", include_in_dotenv=False),
    EnvVar(name="COUNCIL_LOG_LEVEL", owner="council", description="Logging level override", include_in_dotenv=False),
    EnvVar(name="COUNCIL_MODE", owner="council", description="Operating mode: server, client, auto", include_in_dotenv=False),
    EnvVar(name="COUNCIL_HUB_URL", owner="council", description="Hub URL for client mode", include_in_dotenv=False),
    EnvVar(name="COUNCIL_DAEMON_URL", owner="council", description="Daemon WebSocket URL", include_in_dotenv=False),
    EnvVar(name="COUNCIL_HOOK_SECRET", owner="council", description="Webhook signing secret", secret=True, include_in_dotenv=False),
    EnvVar(name="COUNCIL_DEV_MODE", owner="council", description="Enable dev mode features", include_in_dotenv=False),
    EnvVar(name="COUNCIL_AGENTKIT_CONFIG_PATH", owner="council", description="AgentKit config path override", include_in_dotenv=False),
    EnvVar(name="AGENTKIT_CONFIG_PATH", owner="agentkit", description="AgentKit config file path", include_in_dotenv=False),
    EnvVar(name="AGENTKIT_SKIP_ENV_PARITY", owner="agentkit", description="Skip AgentKit env parity check", include_in_dotenv=False),
    EnvVar(name="AGENTKIT_SKIP_SCHEMA_SYNC", owner="agentkit", description="Skip packaged schema sync", include_in_dotenv=False),
    EnvVar(name="AGENTKIT_EMBEDDING_DIM", owner="agentkit", description="Vector embedding dimension", include_in_dotenv=False),
    EnvVar(name="SCRIBE_SSE_ENDPOINT", owner="council", description="Scribe SSE endpoint URL", include_in_dotenv=False),
    EnvVar(name="SCRIBE_STORAGE_BACKEND", owner="scribe", description="Scribe storage backend (read by council services/mcp_servers.py)", include_in_dotenv=False),
    EnvVar(name="COUNCIL_SKIP_ENV_CHECK", owner="council", description="Skip env validation at startup (escape hatch)", include_in_dotenv=False),
]
```

**Design decisions:**
- `frozen=True` prevents accidental mutation
- Dual defaults (`default_local` / `default_docker`) handle the root-vs-deploy divergence from a single source
- `secret=True` vars render as `VAR_NAME=  # REQUIRED - set in .env` (never with real values)
- `conditional` allows documenting vars that are only required under certain conditions
- `include_in_dotenv=False` vars are tracked for linter exclusion but omitted from generated `.env.example`
- COUNCIL_* config overrides are registered but excluded from `.env.example` (they belong in council.yaml)

**CRITICAL CORRECTION from operator review:** The Lens research classified SCRIBE_POSTGRES_ADMIN_*, POSTGRES_SUPERUSER_*, APP_DEFAULT_USER_*, EMBED_OPENAI_API_KEY, and REDIS_PASSWORD as "dead declarations." This was INCORRECT. These variables are consumed by AgentKit as a transitive dependency:
- POSTGRES_SUPERUSER_* read by AgentKit config/loader.py:580-584
- APP_DEFAULT_USER_* read by AgentKit config/loader.py:630-636
- EMBED_OPENAI_API_KEY read by AgentKit config/loader.py:565
- REDIS_PASSWORD read by AgentKit config/loader.py:566
- SCRIBE_POSTGRES_* consumed by AgentKit when running inside the Scribe container

All of these are RETAINED in the schema with appropriate `conditional` documentation.

### 4.2 Validation Function

```python
def validate_env(
    context: str = "local",
    schema: list[EnvVar] | None = None,
) -> list[str]:
    """Validate environment variables against schema.

    Args:
        context: "local" or "docker" - determines which defaults apply
        schema: Override schema for testing (default: ENV_SCHEMA)

    Returns:
        List of error messages. Empty list = all valid.
    """
    errors: list[str] = []
    _schema = schema or ENV_SCHEMA

    for var in _schema:
        if not var.required:
            continue
        value = os.environ.get(var.name, "")
        if not value:
            default = var.default_docker if context == "docker" else var.default_local
            hint = f" (default: {default})" if default and not var.secret else ""
            errors.append(f"  {var.name}: {var.description}{hint}")

    return errors


def validate_env_or_exit(context: str = "local") -> None:
    """Validate env and exit with formatted error if missing vars."""
    if os.environ.get("COUNCIL_SKIP_ENV_CHECK", "") == "1":
        return

    errors = validate_env(context=context)
    if errors:
        print("ERROR: Required environment variables are not set:\n", file=sys.stderr)
        for err in errors:
            print(err, file=sys.stderr)
        print(
            "\nFix: Copy .env.example to .env and fill in the values above.",
            file=sys.stderr,
        )
        sys.exit(1)
```

**Key design choice:** `validate_env()` returns errors; `validate_env_or_exit()` is the opinionated wrapper. This allows tests to call `validate_env()` without risking `sys.exit()`.

### 4.3 CLI Commands

```python
# src/council_mcp/cli/env_cmd.py

@click.group()
def env():
    """Environment variable management."""
    pass

@env.command()
@click.option("--strict", is_flag=True, help="Fail on any drift (CI mode)")
def check(strict: bool):
    """Check env var parity between code and schema."""
    # 1. Scan source files for os.getenv/os.environ patterns
    # 2. Compare against ENV_SCHEMA
    # 3. Report drift
    # Exit 0 if clean, 1 if drift

@env.command()
@click.option("--context", type=click.Choice(["local", "docker"]), default="local")
@click.option("--target", type=click.Choice(["root", "deploy", "scaffold"]), default="root")
@click.option("--output", "-o", type=click.Path(), help="Custom output path")
def generate(context: str, target: str, output: str | None):
    """Generate .env.example from schema."""
    # 1. Read ENV_SCHEMA
    # 2. Group by var.group
    # 3. Render with context-appropriate defaults
    # 4. Write to target path

@env.command()
@click.option("--context", type=click.Choice(["local", "docker"]), default="local")
def validate(context: str):
    """Validate current environment against schema."""
    # 1. Call validate_env()
    # 2. Report results
    # Exit 0 if valid, 1 if missing vars
```

### 4.4 Source Code Scanner (for `council env check`)

```python
def scan_env_reads(src_dir: Path) -> set[str]:
    """Scan Python files for os.getenv/os.environ reads.

    Patterns matched:
    - os.getenv("VAR_NAME")
    - os.getenv("VAR_NAME", ...)
    - os.environ.get("VAR_NAME")
    - os.environ.get("VAR_NAME", ...)
    - os.environ["VAR_NAME"]

    Does NOT match:
    - Dynamic patterns like os.getenv(f"{prefix}_KEY")
    - os.environ.pop() or os.environ.setdefault()
    """
    import re

    patterns = [
        re.compile(r'os\.getenv\(\s*["\']([A-Z_][A-Z0-9_]*)["\']'),
        re.compile(r'os\.environ\.get\(\s*["\']([A-Z_][A-Z0-9_]*)["\']'),
        re.compile(r'os\.environ\[\s*["\']([A-Z_][A-Z0-9_]*)["\']'),
    ]

    found: set[str] = set()
    for py_file in src_dir.rglob("*.py"):
        text = py_file.read_text(errors="replace")
        for pattern in patterns:
            found.update(pattern.findall(text))

    return found
```

**Exclusions:** The scanner ignores dynamic patterns (e.g., `os.getenv(f"{provider}_API_KEY")` in `zlm_adapter.py`). These are documented in schema with `conditional` notes instead. System vars (HOME, USER, TERM, etc.) are excluded by checking `owner="system"` in the schema.

### 4.5 Docker Entrypoint Integration

Add validation call to `deploy/docker-entrypoint.sh` after secret loading (line ~110), before auto-bootstrap:

```bash
# --- Validate required environment variables ---
echo "[entrypoint] Validating environment variables..."
if ! python -m council_mcp.config.env_schema validate --context docker 2>&1; then
    echo "[entrypoint] ERROR: Environment validation failed. See above." >&2
    exit 1
fi
echo "[entrypoint] Environment validation passed."
```

### 4.6 council start Integration

In `src/council_mcp/cli/start_cmd.py`, add validation call at the beginning of the `start()` function (before `_start_background()`):

```python
from council_mcp.config.env_schema import validate_env_or_exit

@click.command()
def start(...):
    # Existing remote startup validation...
    validate_env_or_exit(context="local")
    # ... rest of start logic
```

### 4.7 Variable Classification Summary (CORRECTED)

Based on research AND operator correction about transitive AgentKit consumption:

| Category | Count | Treatment |
|----------|-------|-----------|
| **Required infrastructure** (DATABASE_URL, POSTGRES_APP_*) | 3 | required=True, validated at startup |
| **Conditional secrets** (OPENAI_API_KEY, COUNCIL_API_KEY, etc.) | 5 | required=False, secret=True, with conditional note |
| **Admin/bootstrap credentials** (POSTGRES_ADMIN_*, SUPERUSER_*) | 10 | required=False, consumed by AgentKit init transitively |
| **App defaults** (APP_DEFAULT_USER_*) | 3 | required=False, consumed by AgentKit init transitively |
| **Scribe runtime** (SCRIBE_DB_URL, SCRIBE_STORAGE_BACKEND, etc.) | 4 | required=False, owner="scribe", have defaults |
| **Scribe bootstrap** (SCRIBE_POSTGRES_ADMIN_*, APP_*, SUPERUSER_*) | 15 | required=False, owner="scribe", consumed by AgentKit inside Scribe container |
| **Scribe tuning** (rate limits, log rotation, default project) | 4 | include_in_dotenv=False (too noisy for .env.example) |
| **Docker/deployment** (POSTGRES_USER, POSTGRES_PASSWORD, ENVIRONMENT) | 3 | required=False, context-specific defaults |
| **System vars** (HOME, USER, TERM, etc.) | 14 | owner="system", excluded from .env.example and linter |
| **Internal config overrides** (COUNCIL_*, AGENTKIT_*, SCRIBE_SSE_*) | 17 | include_in_dotenv=False, council.yaml overrides |
| **Vars ACTUALLY dead** | 3 | SCRIBE_LOG_RATE_LIMIT_COUNT, SCRIBE_LOG_RATE_LIMIT_WINDOW, SCRIBE_LOG_MAX_BYTES (NOT read by Scribe code; listed in schema as tuning with include_in_dotenv=False for backward compat) |

**Total tracked in schema: ~78 vars**
**Total in generated .env.example: ~43 vars** (include_in_dotenv=True only)

**Key correction from operator:** The original Lens research classified 23 vars as "dead." After accounting for transitive consumption by AgentKit (which runs inside both council_mcp and scribe_mcp containers), only 3 are truly unreferenced by any code. The rest are consumed through the AgentKit dependency chain. These 3 are kept in the schema with `include_in_dotenv=False` for backward compatibility rather than being removed.

### 4.8 .env.example Output Format

```bash
# =============================================================================
# Council MCP Environment Variables
# Generated by: council env generate --context local
# Do NOT edit manually - regenerate with: council env generate
# =============================================================================

# --- Database (Required) ---
DATABASE_URL=                          # REQUIRED - PostgreSQL connection string
POSTGRES_APP_USER=                     # REQUIRED - Application database user
POSTGRES_APP_PASSWORD=                 # REQUIRED - Application database password
POSTGRES_HOST=localhost                # PostgreSQL hostname
POSTGRES_PORT=5432                     # PostgreSQL port
POSTGRES_APP_DB=agentkit              # Application database name
POSTGRES_USER=postgres                # PostgreSQL superuser name
POSTGRES_PASSWORD=                     # PostgreSQL superuser password (Docker secret)

# --- Admin Credentials (AgentKit schema migration) ---
POSTGRES_ADMIN_USER=                   # Admin user for schema migrations
POSTGRES_ADMIN_PASSWORD=               # Admin password for schema migrations
POSTGRES_ADMIN_HOST=                   # Admin host for schema migrations
POSTGRES_ADMIN_PORT=                   # Admin port for schema migrations
POSTGRES_ADMIN_DB=                     # Admin database for schema migrations
POSTGRES_SUPERUSER_USER=              # AgentKit init fallback (defaults to POSTGRES_USER)
POSTGRES_SUPERUSER_PASSWORD=          # AgentKit init fallback
POSTGRES_SUPERUSER_HOST=              # AgentKit init fallback
POSTGRES_SUPERUSER_PORT=              # AgentKit init fallback
POSTGRES_SUPERUSER_DB=                # AgentKit init fallback

# --- App Defaults (AgentKit init) ---
APP_DEFAULT_USER_EMAIL=               # Default user email
APP_DEFAULT_USER_NAME=                # Default user name
APP_DEFAULT_USER_PASSWORD=            # Default user password

# --- API Keys ---
OPENAI_API_KEY=                        # OpenAI LLM API key
EMBED_OPENAI_API_KEY=                  # OpenAI embeddings key (falls back to OPENAI_API_KEY)
ZAI_API_KEY=                           # Z.AI provider API key
COUNCIL_API_KEY=                       # Council web UI auth key (starts with ck_)
REDIS_PASSWORD=                        # Redis password (AgentKit, no active usage)

# --- Scribe MCP ---
SCRIBE_DB_URL=                         # Scribe PostgreSQL connection string
SCRIBE_STORAGE_BACKEND=sqlite         # sqlite or postgres (default: sqlite)
SCRIBE_USER=austin                     # Scribe agent user name
SCRIBE_POSTGRES_SCHEMA=scribe         # PostgreSQL schema for Scribe tables

# --- Scribe Bootstrap (AgentKit inside Scribe container) ---
SCRIBE_POSTGRES_ADMIN_USER=           # Scribe schema admin user
SCRIBE_POSTGRES_ADMIN_PASSWORD=       # Scribe schema admin password
SCRIBE_POSTGRES_ADMIN_HOST=           # Scribe schema admin host
SCRIBE_POSTGRES_ADMIN_PORT=           # Scribe schema admin port
SCRIBE_POSTGRES_ADMIN_DB=             # Scribe schema admin database
SCRIBE_POSTGRES_APP_USER=             # Scribe app database user
SCRIBE_POSTGRES_APP_PASSWORD=         # Scribe app database password
SCRIBE_POSTGRES_APP_HOST=             # Scribe app database host
SCRIBE_POSTGRES_APP_PORT=             # Scribe app database port
SCRIBE_POSTGRES_APP_DB=               # Scribe app database name
SCRIBE_POSTGRES_SUPERUSER_USER=       # Scribe superuser (init fallback)
SCRIBE_POSTGRES_SUPERUSER_PASSWORD=   # Scribe superuser password
SCRIBE_POSTGRES_SUPERUSER_HOST=       # Scribe superuser host
SCRIBE_POSTGRES_SUPERUSER_PORT=       # Scribe superuser port
SCRIBE_POSTGRES_SUPERUSER_DB=         # Scribe superuser database

# --- Deployment ---
ENVIRONMENT=dev                        # dev, staging, or production
# DOCKER_IMAGE_TAG=latest             # Set by CI/CD only
```

### 4.9 `__main__` Entry Point

The schema module doubles as a CLI tool callable from shell scripts:

```python
# At the bottom of env_schema.py
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Env var validation")
    sub = parser.add_subparsers(dest="cmd")
    val = sub.add_parser("validate")
    val.add_argument("--context", choices=["local", "docker"], default="local")
    args = parser.parse_args()

    if args.cmd == "validate":
        validate_env_or_exit(context=args.context)
    else:
        parser.print_help()
```

This allows `docker-entrypoint.sh` to call `python -m council_mcp.config.env_schema validate --context docker` without importing Click.
<!-- ID: directory_structure -->
## 5. Directory Structure

```
council_mcp/
├── .env.example                         # Generated by: council env generate --context local
├── deploy/
│   ├── .env.example                     # Generated by: council env generate --context docker
│   └── docker-entrypoint.sh             # Modified: adds env validation call
├── .council/
│   └── .env.example                     # Generated by: council env generate --context local --target scaffold
├── src/council_mcp/
│   ├── config/
│   │   ├── __init__.py                  # Existing: env override loading, _load_dotenv_from_council()
│   │   └── env_schema.py                # NEW: EnvVar dataclass, ENV_SCHEMA, validate_env()
│   └── cli/
│       ├── env_cmd.py                   # NEW: council env check/generate/validate commands
│       ├── start_cmd.py                 # Modified: adds validate_env_or_exit() call
│       └── main.py                      # Modified: registers env command group
└── tests/
    └── test_env_schema.py               # NEW: Unit tests for schema, validator, scanner
```
<!-- ID: data_storage -->
## 6. Data & Storage

- **No new datastores**: This system is purely file-based (Python module + generated `.env.example` files)
- **env_schema.py** is the single source of truth — a Python data structure, not a config file
- **Generated artifacts**: `.env.example` files are output artifacts, not source files. They carry a "Generated by" header to discourage manual editing
- **No migration needed**: This is additive (new module + new CLI commands + hooks into existing startup)
<!-- ID: testing_strategy -->
- **Unit Tests:** Template rendering + doc ops
- **Integration Tests:** manage_docs tool exercises real files
- **Manual QA:** Project review after each release
- **Observability:** Structured logging via doc_updates log


---
## 8. Deployment & Operations
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should COUNCIL_TRANSPORT__* env overrides be registered in schema? | Blueprint | DECIDED | No. They are council.yaml config overrides, not infrastructure vars. Registered with `include_in_dotenv=False` for linter exclusion only. |
| Are SCRIBE_POSTGRES_ADMIN_* truly dead? | Blueprint/Operator | DECIDED | No. Operator correction: consumed by AgentKit transitively inside Scribe container. Retained with conditional documentation. |
| Should SCRIBE_LOG_RATE_LIMIT_* be removed? | Blueprint | DECIDED | Kept with `include_in_dotenv=False` for backward compat. Not read by any current code but harmless to retain in schema. |
| Should `council env check` run in CI? | DevOps | TODO | Recommend adding to `.github/workflows/platform.yml` test step: `council env check --strict`. |
| Should `.council/.env.example` scaffold be generated? | Blueprint | DEFERRED | Architecture supports it (`--target scaffold`) but no current use case. Implement when needed. |
<!-- ID: references_appendix -->
- PROGRESS_LOG.md
- ARCHITECTURE_GUIDE.md

Generated via generate_doc_templates.


---