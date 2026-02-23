---
id: council_native_integration-research-config-devprod-downstream
title: Council Config Generation, Dev/Prod Switching & Downstream Integration
doc_type: RESEARCH_CONFIG_DEVPROD_DOWNSTREAM
doc_name: RESEARCH_CONFIG_DEVPROD_DOWNSTREAM
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 07:59:54 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Council Config Generation, Dev/Prod Switching & Downstream Integration

## Executive Summary

Council configuration generation is a three-layer system with clear precedence: package defaults < repo .council/council.yaml < environment variables. The deployment topology section exists but is minimally configured. Dev/prod switching can be achieved via environment variables or deployment.mode flag. Downstream councils are supported via hierarchical parent/child relationships and API registration. **HIGH CONFIDENCE on flow; MEDIUM on dev/prod; LOW on database URL pattern**.

## 1. Config Generation Flow (HIGH CONFIDENCE)

### Entry Point
`council init [path]` CLI command (src/council_mcp/cli/init_cmd.py:704)

### Workflow
1. `init()` calls `scaffold_council()` (line 791)
2. `scaffold_council()` calls `_build_council_yaml()` (line 450)
3. `_build_council_yaml()` loads package defaults from `src/council_mcp/templates/defaults/council.yaml` (line 392)
4. Package defaults based on `DEFAULT_CONFIG` in `src/council_mcp/config.py:38`
5. Defaults merged with identity fields (name, description, parent_council_name)
6. Full YAML written to `.council/council.yaml` with inline documentation

### Config Load Precedence (HIGH CONFIDENCE)

```
1. Package defaults: src/council_mcp/templates/defaults/council.yaml
2. Repo config: .council/council.yaml (via _find_council_config())
3. Global config: ~/.council/council.yaml
4. Environment variables: COUNCIL_<SECTION>__<KEY>=value
```

Merged via `deep_merge()` (config.py:1369) → env overrides applied by `_apply_env_overrides()` (config.py:1722)

## 2. Deployment Section (MEDIUM CONFIDENCE)

Located in both DEFAULT_CONFIG (config.py:797) and defaults YAML (defaults/council.yaml:777):

```yaml
deployment:
  mode: "local"                          # "local" or "remote"
  hub_tailscale_ip: ""                   # Tailscale IP of hub node (Hetzner)
  gateway_domain: ""                     # Public domain for Caddy gateway (Phase 5+)
```

**Finding**: Missing explicit database URL configuration in deployment section. Database connection likely from AgentKit or environment.

## 3. Dev/Prod Environment Switching (MEDIUM CONFIDENCE)

### Method 1: Environment Variables
- Format: `COUNCIL_<SECTION>__<KEY>=value`
- Example: `COUNCIL_DEPLOYMENT__MODE=remote COUNCIL_DEPLOYMENT__HUB_TAILSCALE_IP=100.103.34.13`
- Handler: `_apply_env_overrides()` (config.py:1722)
- All fields support env override via double-underscore syntax
- Examples from code (lines 1732-1801):
  - `COUNCIL_TRANSPORT__MODE`
  - `COUNCIL_TRANSPORT__WS_HOST`
  - `COUNCIL_TRANSPORT__WS_PORT`
  - And many timeouts...

### Method 2: deployment.mode Flag
- Values: "local" | "remote"
- Can switch by modifying .council/council.yaml or env var `COUNCIL_DEPLOYMENT__MODE`
- Used by downstream code to route compute/networking

### Method 3: Selective Config Profiles (NOT YET IMPLEMENTED)
- Could add Jinja2 templates or profile selector
- Would require new config schema section like:
  ```yaml
  config_profiles:
    dev:
      deployment.mode: "local"
      council.web.reload: true
    prod:
      deployment.mode: "remote"
      council.web.reload: false
  ```

## 4. Downstream Council Support (HIGH CONFIDENCE)

### Hierarchical Registration
- `council init --parent <parent_name>` scaffolds child council (line 668)
- Parent name stored in config: `council.parent_council_name`
- Council registry tracks parent/child relationships via database

### API Registration Flow
- `council init --auto-register --api-key <key>` registers with central web server (line 689)
- Calls `register_council()` (line 70) → POST `/api/councils/register`
- Registration requires:
  - Valid API key (validated against `/api/auth/validate-key`)
  - Council name
  - Council path (absolute)
  - Preset (standard|minimal|empty)
  - Optional parent council name

### Downstream Council Configuration
- Each council gets unique UUID: `council.council_id` (config.yaml:704)
- Isolated database schema per council for custom tables (via AgentKit extensions)
- Custom pages via `.council/web/pages/*.html.j2` (independent per council)
- Custom routes via `.council/web/routes/*.py` (independent per council)
- Per-council environment override: `COUNCIL_DEPLOYMENT__HUB_TAILSCALE_IP` for remote connection

## 5. Database Connection Pattern (HIGH CONFIDENCE - UPDATED)

Database connection uses **mandatory environment variable** `DATABASE_URL`:
- Location: src/council_mcp/web/cli.py:35
- Format: `postgresql://user:pass@host:port/dbname`
- **No fallback**: Missing DATABASE_URL raises ValueError
- Required for: Web startup, persona sync, admin creation
- AgentKit internally reads DATABASE_URL at initialization

**For downstream councils**:
```bash
# Set before starting council daemon or web UI
export DATABASE_URL="postgresql://council:password@hetzner-postgres:5432/agentkit"
```

**Architecture options**:
1. **Shared central DB** (recommended for operator infrastructure)
   - All councils use same Postgres instance + host
   - AgentKit schema isolation via `council_<id>` schemas
   - Single DATABASE_URL environment variable

2. **Isolated DB per council** (for federated deployments)
   - Each council has separate Postgres instance
   - Override DATABASE_URL per council environment

**Recommendation**: Add to DEFAULT_CONFIG/council.yaml for clarity:
```yaml
database:
  url_env_var: "DATABASE_URL"   # Environment variable name
  pool_size: 20                 # Connection pool size
```

## 6. Compute & Ray Configuration (PARTIAL COVERAGE)

Located in config.py:790:
```yaml
compute:
  ray_enabled: false
  ray_address: "auto"
  gpu_fallback_to_cpu: true
  dispatch_timeout_seconds: 30
```

Downstream councils can enable Ray by setting `COUNCIL_COMPUTE__RAY_ENABLED=true` and `COUNCIL_COMPUTE__RAY_ADDRESS=<hub_ray_gcs_ip>:6379`

## Key Files Involved

| File | Purpose |
|------|---------|
| src/council_mcp/cli/init_cmd.py | Generation (_build_council_yaml, scaffold_council) |
| src/council_mcp/config.py | Loading (load_council_config, _apply_env_overrides, deep_merge) |
| src/council_mcp/templates/defaults/council.yaml | Package defaults |
| src/council_mcp/cli/init_cmd.py:70 | Registration (validate_api_key, register_council) |

## Recommendations

1. **Add Database Config Section** to both DEFAULT_CONFIG and defaults/council.yaml
2. **Create Config Profiles** for easy dev/prod switching
3. **Downstream Council Bootstrap** needs automatic registration & config injection
4. **Investigate DB connection** in web/app.py startup

## Confidence Assessment

- **HIGH**: Config generation flow, load precedence, deployment section structure
- **MEDIUM**: Dev/prod switching via env vars, downstream registration
- **LOW**: Database URL pattern (needs app.py investigation)
---

## UPDATE: Confidence Reassessment (DATABASE_URL Investigation Complete)

**Upgraded to HIGH CONFIDENCE**: Database connection pattern confirmed via src/council_mcp/web/cli.py:35
- Database URL comes from mandatory `DATABASE_URL` environment variable
- No fallback — missing DATABASE_URL raises ValueError
- Applies to all downstream councils
- Architecture: Shared DB with AgentKit schema isolation vs isolated DB per council
