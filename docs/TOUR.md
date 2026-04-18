# Tour: What Scribe Feels Like

Release line: `2.2.7`  
Updated: `2026-04-18`

This is the fastest way to understand why Scribe is more interesting than "yet another MCP server."

The short answer:

- it binds work to a project and repo root
- it scaffolds governed docs immediately
- it gives later tools stable structure to update
- it keeps an audit trail next to the work
- it gives that work registry-backed health and drift signals later

## One command, real artifacts

After install and runtime setup, a fresh project bind looks like this:

```bash
scribe call set_project \
  --agent demo-agent \
  --repo-root "$PWD" \
  --arg name=demo_docs \
  --arg root="$PWD" \
  --arg format=structured \
  --pretty
```

On a fresh project, that one step can generate:

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

That is the first thing the public docs should have been showing all along.

## What the generated docs actually look like

Excerpt from a generated `ARCHITECTURE_GUIDE.md`:

```md
## 1. Problem Statement
<!-- ID: problem_statement -->
- **Context:** demo_docs needs a reliable documentation system.

## 3. Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** Document manager orchestrates template rendering and writes.
```

Excerpt from a generated `CHECKLIST.md`:

```md
## Phase 0
<!-- ID: phase_0 -->
- [ ] Add package-specific acceptance item with expected verification command.
```

Those `<!-- ID: ... -->` anchors are a big part of the value story. They give Scribe stable targets for managed updates later, which is much safer than hoping an agent can keep finding the right markdown heading by text alone.

The same template system can also inject registry and activity metadata into documents, including fields like:

- `staleness_level`
- `days_since_last_entry`
- `baseline_hashes`
- `current_hashes`
- `doc_drift_days_since_update`
- `drift_score`

That is how Scribe can move beyond "some markdown files exist" into "this project looks healthy" or "this work has drifted."

## Why that matters

Without a structure like this, agent-driven docs tend to rot fast:

- plans become stale snapshots
- checklists lose proof
- architecture notes drift away from implementation
- later updates turn into brittle search-and-replace hacks

Scribe gives the docs a managed shape from the beginning, so later operations like `replace_section`, `apply_patch`, and `status_update` have something reliable to work with.

## Projects become queryable, not just created

Scribe keeps registry-backed lifecycle and hygiene data for each project. In practice that means a project can carry:

- lifecycle timestamps like `created_at`, `last_entry_at`, and `last_access_at`
- activity signals like `activity_score` and `staleness_level`
- doc health hints like `doc_drift_suspected` and `drift_score`

So the system is not just "write a plan, then forget it." It has the ingredients to tell you when a project is warming up, going stale, or drifting away from its docs.

## The audit trail sits next to the docs

Scribe does not stop at scaffolding. It also lays down the log surface that explains what happened:

- `PROGRESS_LOG.md` for execution milestones
- `DOC_LOG.md` for documentation changes
- `SECURITY_LOG.md` for security-sensitive work
- `BUG_LOG.md` for defect tracking

That means the project artifacts and the execution trail live in the same working surface instead of being split across markdown, chat history, and terminal output.

## The `.scribe/` surface is part of the product

After Scribe has touched a repo, the local working surface can look something like this:

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

That is one of the reasons Scribe feels heavier-duty than a lot of agent tooling. It is building a local memory and evidence surface, not just exposing RPC calls.

## The setup story is stronger than the old docs admitted

The package does not just ship `scribe-server`. It also ships a serious operator toolchain:

- `scribe-bootstrap-postgres`
- `scribe-migrate`
- `scribe-migrate-postgres`
- `scribe-migrate-objects`
- `scribe-backup-postgres`
- `scribe-metrics-postgres`
- `scribe-soak-postgres`

That matters because the install experience is part of the product. Scribe is trying to be usable as real infrastructure, not just as a toy local demo.

## The operating loop

This is the normal Scribe rhythm:

```text
set_project
  -> read_recent / query_entries
  -> do work
  -> append_entry
  -> manage_docs
  -> verify
```

That is what makes Scribe feel different in practice. It is not just a server you connect to. It is a way to keep engineering work inspectable while it is happening.

## Where to go next

- [INSTALL_AND_BOOTSTRAP.md](INSTALL_AND_BOOTSTRAP.md) for the install and runtime setup path
- [Scribe_Usage.md](Scribe_Usage.md) for the day-to-day operating loop
- [mcp_server_guide.md](mcp_server_guide.md) for MCP host integration
- [guides/manage_docs_agent_guide.md](guides/manage_docs_agent_guide.md) for the deeper managed-doc operations
