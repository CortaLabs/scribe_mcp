# Scribe MCP

[![PyPI version](https://img.shields.io/pypi/v/scribe-mcp)](https://pypi.org/project/scribe-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://pypi.org/project/scribe-mcp/)
[![License](https://img.shields.io/badge/license-PolyForm--NC-orange)](https://github.com/CortaLabs/scribe_mcp/blob/main/LICENSE)

Scribe MCP is the accountability layer for agent-driven engineering work.

It gives your agents a durable audit trail, governed engineering documents, and repo-safe tool contracts so plans, edits, and verification do not disappear into chat history or terminal scrollback.

Scribe is strongest when you want three things at the same time:

- a project-scoped execution record you can query later
- managed docs that stay tied to the work instead of drifting away from it
- MCP-safe read/search/edit primitives that are easier to automate than ad hoc shell mutations

If you want the fast product tour first, start here:
- [Tour: Scribe as an MCP product](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TOUR.md)

## Why teams reach for Scribe

Without Scribe, agent-heavy work tends to fragment:

- plans live in one place, edits happen somewhere else, and rationale disappears
- project docs become stale snapshots instead of active engineering artifacts
- logs exist, but they are too noisy or too unstructured to explain what actually happened
- automation can touch files, but it is harder to keep the changes reviewable and reproducible

Scribe turns that into a tighter loop:

1. bind a project and repo root
2. generate or manage the project docs
3. log meaningful actions as the work happens
4. query the resulting history later by project, status, message, or scope

## What Scribe gives you

- project and session binding with explicit repo scope
- governed docs such as `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, and `CHECKLIST.md`
- audit logs such as `PROGRESS_LOG.md`, `DOC_LOG.md`, `SECURITY_LOG.md`, and `BUG_LOG.md`
- MCP tools for reading, searching, editing, and logging without leaving the repo boundary
- a Postgres-first runtime for shared use, plus explicit standalone SQLite for local-only workflows
- CLI helpers for bootstrap, MCP server startup, migrations, backups, metrics, and Codex projection

## Current release highlights

`2.2.23` focuses on git-clean managed-doc scaffolds, agent-safe reference provenance, scoped case identity, preserve-first managed-doc metadata, and a provenance-safe changelog/global reconciliation guard:

- `link_fix` now validates execution/session/entry references through a shared resolver before mutating case state.
- Bare or forged 32-hex tokens are no longer silently trusted; accepted IDs must come from current execution lineage, an authoritative session key, or an in-scope Scribe entry.
- BUG and security case registry ownership is scoped by repo/project identity, so the same case ID cannot mutate the wrong project.
- Managed-doc frontmatter is preserve-first: empty or null incoming values do not erase existing custom metadata, and runtime-owned fields stay tool-owned.
- Agent onboarding docs now describe accepted `link_fix` reference forms, rejection recovery, and the frontmatter mutation contract.
- Release governance now treats missing current-version changelog coverage as blocking quality truth: `SCF_CHANGELOG_CURRENT_VERSION_MISSING` is raised through `quality_check`, reflected in reminders, and visible in managed-doc `project_health` digests until coverage is repaired and reconciliation proof is run.

## What makes Scribe different

The pitch is simple: keep the work record, the docs, and the repo operations in one system. The reason it holds up in practice is the machinery underneath it.

- Scribe keeps a project registry with lifecycle and hygiene metadata, not just loose markdown files.
- It tracks doc readiness and drift using stored hashes, last-update timestamps, and advisory flags such as `doc_drift_suspected`.
- It computes activity signals like `days_since_last_entry`, `days_since_last_access`, `staleness_level`, and `activity_score` so projects become queryable operational objects instead of folders you have to inspect manually.
- Managed docs are anchored with stable section IDs like `<!-- ID: problem_statement -->`, which is what makes later `replace_section` and checklist `status_update` operations deterministic.
- The bootstrap and migration toolchain is deeper than most projects in this space: `scribe-bootstrap-postgres`, `scribe-migrate`, `scribe-migrate-postgres`, `scribe-migrate-objects`, `scribe-backup-postgres`, `scribe-metrics-postgres`, and `scribe-soak-postgres` all ship in the package.

## Five-minute quickstart

Install the package:

```bash
pip install scribe-mcp
```

Sanity-check the shipped commands:

```bash
scribe --help
scribe install --help
scribe-server --help
```

### Recommended: run the install wizard

Use the install wizard first. It is the preferred default path for a real installation.

```bash
scribe install
```

Default `scribe install` behavior is preview-only and safe-by-default:

- no DB mutation
- no `.env` mutation
- no Codex projection

Apply mutations only when you explicitly confirm commit mode:

```bash
scribe install --commit
```

For non-interactive commit flows, use the approved confirmation path:

```bash
scribe install --commit --yes
```

The commit flow is designed to handle the setup work for you:

- create or update database roles
- provision the Scribe app database
- apply schema grants
- write or update repo-root runtime keys in `.env`

After a successful commit, Scribe runs post-install diagnostics/readiness checks using the existing verification seam.

After bootstrap, load the environment and start the server:

```bash
set -a
source .env
set +a
scribe-server
```

### Just want to try Scribe locally?

You can use explicit standalone SQLite for a local-only demo or one-user workflow:

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
export SCRIBE_DB_PATH=".scribe/state/scribe.db"
scribe-server
```

### Create your first governed project scaffold

Once your runtime is configured, bind a project:

```bash
scribe call set_project \
  --agent demo-agent \
  --repo-root "$PWD" \
  --arg name=demo_docs \
  --arg root="$PWD" \
  --arg format=structured \
  --pretty
```

On a fresh project, that one call can generate the core scaffold:

```text
.scribe/docs/dev_plans/demo_docs/
  ARCHITECTURE_GUIDE.md
  PHASE_PLAN.md
  CHECKLIST.md
  PROGRESS_LOG.md
  DOC_LOG.md
  SECURITY_LOG.md
  BUG_LOG.md
```

That scaffold is the point. Scribe is not just starting a server. It is creating a project surface that later MCP calls can work against.

### Downstream customization now lives in the repo

On first bind/bootstrap, Scribe also seeds the downstream customization surface under `.scribe/` so each repo can own its local scaffolding and settings without forking the library:

```text
.scribe/
  config/
    scribe.yaml
    seed_registry.json
  templates/
    documents/
      ARCHITECTURE_GUIDE_TEMPLATE.md
      PHASE_PLAN_TEMPLATE.md
      CHECKLIST_TEMPLATE.md
      PROGRESS_LOG_TEMPLATE.md
      DOC_LOG_TEMPLATE.md
      SECURITY_LOG_TEMPLATE.md
      BUG_LOG_TEMPLATE.md
  .env.example
```

That seeded surface is live, not decorative:

- `generate_doc_templates` and template-driven doc flows now resolve repo-local `.scribe/templates/` first
- repo-local seeded files are tracked in `.scribe/config/seed_registry.json` so refreshes can update untouched files without clobbering customized ones
- `.scribe/.env.example` is a discovery artifact only; runtime never auto-loads it

The ownership split is intentional:

- shared infrastructure defaults such as `SCRIBE_DB_URL`, backend mode, and pool settings belong in user/global config by default
- repo-specific runtime overrides belong in repo root `.env`
- repo-scoped structured behavior belongs in `.scribe/config/scribe.yaml`

The user/global config home resolves in this order:

1. `SCRIBE_CONFIG_DIR`
2. `XDG_CONFIG_HOME/scribe_mcp`
3. `~/.config/scribe_mcp`

Inside that directory, use:

- `runtime.env` for shared env-backed defaults across repos
- `scribe.yaml` for user-level structured defaults such as display preferences

That means you do not need to restate DB credentials in every downstream Scribe project just to make the runtime work.

The tour walks through that loop in more detail:
- [Tour: Scribe as an MCP product](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TOUR.md)

If you want to see the registry surface after that first bind, Scribe also exposes project inventory and health-oriented views through tools such as `list_projects` and managed-doc `project_health`.

## How governed docs work

Generated docs are not just blank markdown files. They are structured scaffolds designed for later managed updates.

Example excerpt from a generated `ARCHITECTURE_GUIDE.md`:

```md
## 1. Problem Statement
<!-- ID: problem_statement -->
...

## 3. Architecture Overview
<!-- ID: architecture_overview -->
...
```

Those stable anchor IDs are what let Scribe patch sections deterministically later through managed doc operations instead of relying on brittle freeform edits.

Example excerpt from a generated `CHECKLIST.md`:

```md
## Phase 0
<!-- ID: phase_0 -->
- [ ] Add package-specific acceptance item with expected verification command
```

The value is not just that Scribe writes docs. It writes docs that agents and operators can update without turning them into mush.

## The project registry and drift story

Scribe does more than remember that a project exists.

The runtime keeps registry-backed metadata for each project, including:

- lifecycle timestamps such as `created_at`, `last_entry_at`, and `last_access_at`
- activity signals such as `days_since_last_entry`, `days_since_last_access`, `staleness_level`, and `activity_score`
- doc hygiene metadata such as `baseline_hashes`, `current_hashes`, `doc_drift_days_since_update`, `drift_score`, and `doc_drift_suspected`

This is the useful part: Scribe is not just storing docs and logs side by side. It keeps enough structured state to warn when active work has outpaced the planning docs.

If you want the template-side view of those fields, start with:
- [Template variables reference](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TEMPLATE_VARIABLES.md)
- [Scribe MCP whitepaper](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/whitepapers/scribe_mcp_whitepaper.md)

## The `.scribe/` working surface

Once Scribe is active, your repo grows a real working surface under `.scribe/`. Depending on runtime mode and the tools you use, that can include:

```text
.scribe/
  .env.example
  config/
    scribe.yaml
    seed_registry.json
  templates/
    documents/
      ARCHITECTURE_GUIDE_TEMPLATE.md
      PHASE_PLAN_TEMPLATE.md
      CHECKLIST_TEMPLATE.md
      PROGRESS_LOG_TEMPLATE.md
      DOC_LOG_TEMPLATE.md
      SECURITY_LOG_TEMPLATE.md
      BUG_LOG_TEMPLATE.md
  state/
  vectors/
  backups/
  sentinel/
  cli/
  docs/
    agent_report_cards/
    dev_plans/<project>/
      ARCHITECTURE_GUIDE.md
      PHASE_PLAN.md
      CHECKLIST.md
      PROGRESS_LOG.md
      DOC_LOG.md
      SECURITY_LOG.md
      BUG_LOG.md
      TOOL_LOG.jsonl
```

That layout is part of the product story. Scribe gives agents and operators a durable project memory layer inside the repo boundary instead of scattering evidence across chat threads, shell history, and CI logs.

The important new bit is that `.scribe/templates/` and `.scribe/config/` are now first-class downstream surfaces. Customize templates there when you want repo-specific scaffolds, keep repo behavior in `.scribe/config/scribe.yaml`, keep repo-specific env overrides in repo root `.env`, and keep shared cross-repo runtime defaults in the user/global config home.

## Run Scribe as an MCP server

For MCP hosts such as Codex or Claude-compatible setups, the usual entry point is:

```bash
scribe-server
```

Generic `mcp.json` example:

```json
{
  "mcpServers": {
    "scribe": {
      "command": "scribe-server",
      "env": {
        "SCRIBE_STORAGE_BACKEND": "postgres",
        "SCRIBE_DB_URL": "postgresql://scribe_app:pass@127.0.0.1:5432/scribe"
      }
    }
  }
}
```

Codex-specific guidance lives here:
- [MCP server guide](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/mcp_server_guide.md)
- [Codex projection path](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/INSTALL_AND_BOOTSTRAP.md#codex-projection-path)

The repo also ships bundled plugin assets for Codex and Claude under `plugins/`, so the MCP server surface is not the only integration story.

## Documentation map

Start with these:

- [Install and Bootstrap](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/INSTALL_AND_BOOTSTRAP.md)  
  The canonical install guide, including Postgres bootstrap, standalone mode, and Codex projection.
- [Tour: Scribe as an MCP product](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TOUR.md)  
  A short MCP-first walkthrough with verified live response shapes.
- [Scribe Usage Guide](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/Scribe_Usage.md)  
  The day-to-day operating loop and the tool families you will actually use.
- [MCP Server Guide](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/mcp_server_guide.md)  
  How to connect Scribe to Codex or other MCP hosts.

Reference and release docs:

- [Compatibility matrix](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/COMPATIBILITY_MATRIX.md)
- [Release surface](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/RELEASE_SURFACE.md)
- [Release file map](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/RELEASE_FILE_MAP.md)
- [Remote client contract](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/REMOTE_CLIENT.md)
- [Template variables reference](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TEMPLATE_VARIABLES.md)
- [Bridge development](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/BRIDGE_DEVELOPMENT.md)
- [Global deployment guide](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/GLOBAL_DEPLOYMENT_GUIDE.md)
- [Deployment README](https://github.com/CortaLabs/scribe_mcp/blob/main/deploy/README.md)
- [Scribe MCP whitepaper](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/whitepapers/scribe_mcp_whitepaper.md)

Examples:

- [mcp.json example](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/examples/mcp.json.example)
- [opencode.json example](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/examples/opencode.json.example)

## Who Scribe is for

Scribe is a strong fit if you are:

- building with MCP-hosted agents and want better operational memory
- running multi-agent engineering workflows that need a durable trail
- trying to keep specs, plans, and checklists attached to implementation reality
- tired of reconstructing "why did the agent do this?" from scattered logs

## What still needs work

There is still one obvious next step:

- a clean-room walkthrough of the full pip-installed path from bootstrap to first live MCP host integration

That work matters because the public install story should be proven end-to-end, not implied.

## License

See [LICENSE](https://github.com/CortaLabs/scribe_mcp/blob/main/LICENSE).
