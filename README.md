# Scribe MCP

[![PyPI version](https://img.shields.io/pypi/v/scribe-mcp)](https://pypi.org/project/scribe-mcp/)
[![Python 3.11+](https://img.shields.io/pypi/pyversions/scribe-mcp)](https://pypi.org/project/scribe-mcp/)
[![License](https://img.shields.io/github/license/CortaLabs/scribe_mcp)](https://github.com/CortaLabs/scribe_mcp/blob/main/LICENSE)

Scribe MCP is the accountability layer for agent-driven engineering work.

It gives your agents a durable audit trail, governed engineering documents, and repo-safe tool contracts so plans, edits, and verification do not disappear into chat history or terminal scrollback.

Scribe is strongest when you want three things at the same time:

- a project-scoped execution record you can query later
- managed docs that stay tied to the work instead of drifting away from it
- MCP-safe read/search/edit primitives that are easier to automate than ad hoc shell mutations

If you want the fast product tour first, start here:
- [Tour: what Scribe feels like](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TOUR.md)

## Why Teams Reach For Scribe

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

## What Scribe Gives You

- project and session binding with explicit repo scope
- governed docs such as `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, and `CHECKLIST.md`
- audit logs such as `PROGRESS_LOG.md`, `DOC_LOG.md`, `SECURITY_LOG.md`, and `BUG_LOG.md`
- MCP tools for reading, searching, editing, and logging without leaving the repo boundary
- a Postgres-first runtime for shared use, plus explicit standalone SQLite for local-only workflows
- CLI helpers for bootstrap, MCP server startup, migrations, backups, metrics, and Codex projection

## What Makes Scribe Different

The basic pitch is "audit trail plus governed docs," but the deeper value is in the mechanics behind that surface.

- Scribe keeps a project registry with lifecycle and hygiene metadata, not just loose markdown files.
- It tracks doc readiness and drift using stored hashes, last-update timestamps, and advisory flags such as `doc_drift_suspected`.
- It computes activity signals like `days_since_last_entry`, `days_since_last_access`, `staleness_level`, and `activity_score` so projects become queryable operational objects instead of folders you have to inspect manually.
- Managed docs are anchored with stable section IDs like `<!-- ID: problem_statement -->`, which is what makes later `replace_section` and checklist `status_update` operations deterministic.
- The bootstrap and migration toolchain is unusually complete for this kind of project: `scribe-bootstrap-postgres`, `scribe-migrate`, `scribe-migrate-postgres`, `scribe-migrate-objects`, `scribe-backup-postgres`, `scribe-metrics-postgres`, and `scribe-soak-postgres` all ship in the package.

That combination is why Scribe feels more like infrastructure than a thin MCP wrapper.

## Five-Minute Quickstart

Install the package:

```bash
pip install scribe-mcp
```

Sanity-check the shipped commands:

```bash
scribe --help
scribe bootstrap --help
scribe-server --help
```

### Recommended: bootstrap Postgres

Use the guided bootstrap first. It is the best default path for a real installation.

```bash
scribe bootstrap
```

The bootstrap flow is designed to handle the annoying setup work for you:

- create or update database roles
- provision the Scribe app database
- apply schema grants
- write or update the runtime keys you need in `.env`

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

That artifact flow is one of Scribe's best features, and it is easy to miss if you only read the old top-level docs. The tour page walks through it in more detail:
- [Tour: what Scribe feels like](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TOUR.md)

If you want to see the registry surface after that first bind, Scribe also exposes project inventory and health-oriented views through tools such as `list_projects` and managed-doc `project_health`.

## What The Governed Docs Story Looks Like

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

So the "magic" is not just that Scribe writes docs. It writes docs that are easier for agents and operators to keep current as work evolves.

## The Project Registry And Drift Story

Scribe does more than remember that a project exists.

The runtime keeps registry-backed metadata for each project, including:

- lifecycle timestamps such as `created_at`, `last_entry_at`, and `last_access_at`
- activity signals such as `days_since_last_entry`, `days_since_last_access`, `staleness_level`, and `activity_score`
- doc hygiene metadata such as `baseline_hashes`, `current_hashes`, `doc_drift_days_since_update`, `drift_score`, and `doc_drift_suspected`

That is the part the public docs used to hide. Scribe is not just storing docs and logs side by side. It is keeping enough structured state to warn when active work has outpaced planning docs.

If you want the template-side view of those fields, start with:
- [Template variables reference](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TEMPLATE_VARIABLES.md)
- [Scribe MCP whitepaper](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/whitepapers/scribe_mcp_whitepaper.md)

## The `.scribe/` Working Surface

Once Scribe is active, your repo grows a real working surface under `.scribe/`. Depending on runtime mode and the tools you use, that can include:

```text
.scribe/
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

## Run Scribe As An MCP Server

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

## Documentation Map

Start with these:

- [Install and Bootstrap](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/INSTALL_AND_BOOTSTRAP.md)  
  The canonical install guide, including Postgres bootstrap, standalone mode, and Codex projection.
- [Tour: what Scribe feels like](https://github.com/CortaLabs/scribe_mcp/blob/main/docs/TOUR.md)  
  The fastest way to understand the governed-doc and audit-trail workflow.
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

## Who Scribe Is For

Scribe is a strong fit if you are:

- building with MCP-hosted agents and want better operational memory
- running multi-agent engineering workflows that need a durable trail
- trying to keep specs, plans, and checklists attached to implementation reality
- tired of reconstructing "why did the agent do this?" from scattered logs

## What Still Needs Love

The docs are now much closer to the real product, but there is still one obvious next step:

- a clean-room walkthrough of the full pip-installed path from bootstrap to first live MCP host integration

That work matters because the public install story should be proven end-to-end, not implied.

## License

See [LICENSE](https://github.com/CortaLabs/scribe_mcp/blob/main/LICENSE).
