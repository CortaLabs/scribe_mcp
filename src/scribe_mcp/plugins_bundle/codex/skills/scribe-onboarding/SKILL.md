---
name: scribe-onboarding
description: Install and connect Scribe MCP — pip install, one-command Postgres bootstrap, host/plugin projection, and first-bind verification
user-invocable: true
context: full
visibility: exported
owner: scribe-mcp
---

# Scribe Onboarding

Use this skill to **install and connect** Scribe MCP from scratch: install the package, stand up the recommended Postgres runtime with one command, project the bundled plugin into your agent host, and verify that the runtime answers. Once Scribe is installed and a project is bound, switch to `/scribe-integration` for how to *use* the tools (logging cadence, managed docs, search, bug reporting). This skill is install-only; it does not teach the day-to-day workflow.

## Trigger Conditions

Reach for this skill when:

- You are setting up `scribe-mcp` on a new machine or in a new repo for the first time.
- You need the canonical `pip install` command and the recommended runtime path (Postgres vs. eval SQLite).
- You want the one-command Postgres bootstrap instead of provisioning roles, grants, and `.env` by hand.
- You are wiring Scribe into an MCP host (Codex, Claude, or a generic `mcp.json` host).
- A bind or server start failed and you need to confirm the install and connection are sound.

If Scribe is already installed and a project is already bound, you do not need this skill — go to `/scribe-integration`.

## Inputs

- Python 3.11+ available on PATH (`python3.11 --version`).
- For the recommended path: a local or reachable PostgreSQL instance. The `local-postgres` profile defaults the superuser to the standard local `postgres` role, so a default local Postgres needs near-zero extra config.
- Write access to the repo where you will run the install (the wizard writes a repo-scoped `.env`).
- Optional, for host projection: a Codex install (`CODEX_HOME`) or Claude plugin host.

## Procedure

### 1. Install the package

```bash
pip install scribe-mcp
```

When you want the Postgres runtime dependencies pinned through an explicit extra:

```bash
pip install 'scribe-mcp[postgres]'
```

> **Note (delivered by the package):** the `[postgres]` extra is a packaging surface owned by the `scribe-mcp` distribution. `asyncpg` is already a core dependency, so plain `pip install scribe-mcp` is Postgres-capable; use the `[postgres]` extra form when you want the documented, explicit Postgres install command. If your installed version predates the extra, drop the suffix and use `pip install scribe-mcp`.

Sanity-check the CLI surface — you should not have to guess entry points:

```bash
scribe --help
scribe install --help
scribe-server --help
```

### 2. One-command Postgres bootstrap (recommended)

Scribe ships an install wizard that does the setup most users do not want to do by hand: create/update DB roles, provision the application database, apply grants and extensions, generate secure app credentials, and write a repo-scoped `.env`.

Preview first (this is the default — **no** DB mutation, **no** `.env` mutation, **no** projection):

```bash
scribe install
scribe install --profile local-postgres
```

Apply the changes with an explicit commit:

```bash
# interactive confirmation
scribe install --profile local-postgres --commit

# non-interactive (CI / scripted)
scribe install --profile local-postgres --commit --yes
```

After a successful commit the wizard runs post-install readiness diagnostics automatically.

**Available profiles:**

| Profile | Use it for |
|---------|-----------|
| `local-postgres` | **Default, recommended.** Provision a local Postgres-backed runtime. |
| `existing-postgres` | Point Scribe at a Postgres instance you already manage. |
| `sqlite-eval` | Single-machine evaluation only — not a shared/team runtime. |
| `internal-remote` | Advanced, default-off (preview needs `--profile internal-remote --allow-advanced-profile`). |

Then load the generated environment and start the server:

```bash
set -a
source .env
set +a
scribe-server
```

### 3. Fast local-only eval path (SQLite)

If you only want to try Scribe on one machine without provisioning Postgres, SQLite is supported as an **explicit opt-in** (it is not the recommended shared runtime):

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
export SCRIBE_DB_PATH=".scribe/state/scribe.db"
scribe-server
```

Postgres is the default runtime posture; SQLite is eval-only. When you outgrow it, use the migration commands rather than a hand-rolled export/import.

### 4. Connect a host / project the plugin

Generic `mcp.json` host entry:

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

To project the bundled Scribe plugin into native Codex surfaces, use the shipped projection command (explicit opt-in; base install never touches `CODEX_HOME` unless you request it):

```bash
scribe install --commit --yes --project-codex
```

> **Note (capability delivered by the package):** plugin projection resolves the bundled plugin assets that ship inside the installed `scribe-mcp` package. On a plain `pip install`, projection works once those assets ship in the wheel. If you installed from a release where the plugins are not yet bundled, run projection from a repo clone, or upgrade to a release that ships the plugin assets. Do not hand-copy plugin files — use the projection command so host wiring stays correct.

### 5. Env vars (canonical)

| Variable | Purpose |
|----------|---------|
| `SCRIBE_STORAGE_BACKEND` | `postgres` (recommended) or `sqlite` (eval). |
| `SCRIBE_DB_URL` | Postgres DSN, e.g. `postgresql://scribe_app:pass@127.0.0.1:5432/scribe`. |
| `SCRIBE_MODE` | `standalone` for explicit local SQLite eval; omit for the default Postgres path. |
| `SCRIBE_DB_PATH` | SQLite file path when `SCRIBE_STORAGE_BACKEND=sqlite`. |

The install wizard writes the correct values into the repo-scoped `.env`; mirror them into your own secret/config system if you do not source `.env` directly.

## Verification

Confirm the install and connection are sound before you start real work:

```bash
# 1. CLI is on PATH and reports its surface
scribe --help

# 2. Runtime starts and answers (Ctrl-C after it binds)
scribe-server

# 3. First governed bind — scaffolds the managed docs for a project
scribe call set_project \
  --agent demo-agent \
  --repo-root "$PWD" \
  --arg name=demo_docs \
  --arg root="$PWD" \
  --arg format=structured \
  --pretty
```

A successful `set_project` scaffolds the core managed docs under `.scribe/docs/dev_plans/<project>/` (`ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md`, `PROGRESS_LOG.md`, and the log family). If that bind succeeds, Scribe is installed, connected, and ready — hand off to `/scribe-integration`.

## Output / Handoff

After this skill you have: an installed `scribe-mcp` CLI + server, a provisioned runtime (Postgres recommended, SQLite for eval), an optional host/plugin projection, and a verified first project bind.

**Cross-links (the two-skill split):**

- **`/scribe-onboarding`** (this skill) = how to **install and connect** Scribe.
- **`/scribe-integration`** = how to **use** Scribe — the mandatory startup sequence, logging cadence, managed-doc lifecycle, search, and bug/security reporting. Go there next.

## Boundaries

- **Install-only.** This skill does not teach the tool/workflow reference — that is `/scribe-integration`. Do not duplicate logging, managed-doc, search, or bug-reporting procedure here.
- **No build mechanics.** This skill describes the user-facing install/connect steps. It does not implement or restate how the `[postgres]` extra or the bundled plugin assets are packaged — those capabilities are delivered by the `scribe-mcp` distribution.
- **Truthful commands only.** Every command here matches the shipped `scribe` CLI surface and the canonical install doc. Do not invent flags, profiles, or env vars.
- **Repo-scoped and local-first.** The wizard is preview-by-default and only mutates DB/`.env` on explicit `--commit`. Remote/client posture is internal-only for this release line.

## References

- `/scribe-integration` — how to use the Scribe tools once installed.
- `/scribe-integration` — tool contracts, document rules, and day-to-day Scribe workflow.
- `docs/INSTALL_AND_BOOTSTRAP.md` — the canonical, full install-and-bootstrap guide.
