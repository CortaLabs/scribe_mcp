# 📄 TEMPLATE_VARIABLES.md — Core Template Contexts

This guide documents the **expected context variables** for Scribe’s core Jinja2 templates. It is a reference for both humans and agents when constructing `metadata` payloads or debugging template behavior.

> All contexts start from the shared defaults in `template_engine/engine.py:_build_context`, then merge `.scribe/variables.json` and per-call `metadata`.

---

## 1. Global Context Defaults

Always available in templates (and uppercased variants like `PROJECT_NAME`):

- `project_name: str` – Logical project name.
- `project_slug: str` – Slugified name (filesystem/URL friendly).
- `project_root: str` – Absolute path to the project root.
- `timestamp: str` – `"YYYY-MM-DD HH:MM:SS UTC"`.
- `utcnow: str` – ISO8601 UTC timestamp.
- `date_utc: str` – Human-readable UTC date/time.
- `author: str` – Defaults to `"Scribe"` unless overridden.
- `version: str` – Template version tag (currently `"1.0"`).
- `status: str` – Freeform status string (e.g. `"active"`).

Custom variables from `.scribe/variables.json` (if present) are merged in and exposed as top-level keys.

---

## 2. `ARCHITECTURE_GUIDE_TEMPLATE.md`

Used for `ARCHITECTURE_GUIDE.md` via `generate_doc_templates` and `manage_docs`.

### Expected `metadata` keys

- `summary: str` – High-level summary of the system.
- `problem_statement: dict`:
  - `context: str`
  - `goals: list[str]`
  - `non_goals: list[str]`
  - `success_metrics: list[str]`
- `requirements: dict`:
  - `functional: list[str]`
  - `non_functional: list[str]`
  - `assumptions: list[str]`
  - `risks: list[str]`
- `architecture_overview: dict`:
  - `summary: str`
  - `components: list[dict]` with `name`, `description`, `interfaces`, `notes`
  - `data_flow: str`
  - `external_integrations: str`
- `subsystems: list[dict]` – Optional; each with `name`, `purpose`, `interfaces`, `notes`, `error_handling`.
- `data_storage: dict` – `datastores`, `indexing`, `migrations`.
- `testing_strategy: dict` – `unit`, `integration`, `manual`, `observability`.
- `deployment: dict` – `environments`, `release`, `config`, `ownership`.
- `open_questions: list[dict]` – `item`/`title`, `owner`, `status`, `notes`.
- `references: list[str]` – Links to ADRs, diagrams, research, etc.
- `appendix: str` – Optional extra content appended at the end.

The template uses helpers/macros (e.g. `bullet_list`, `section`) and anchors like `<!-- ID: problem_statement -->` to enable `manage_docs.replace_section`.

---

## 3. `PHASE_PLAN_TEMPLATE.md`

Defines `PHASE_PLAN.md` structure.

### Expected `metadata` keys

- `summary: str` – Plan summary for the project.
- `phases: list[dict]` – Each phase entry:
  - `name: str`
  - `anchor: str` (e.g. `"phase_0"`)
  - `goal: str`
  - `deliverables: list[str]`
  - `confidence: float` (0–1)
  - `tasks: list[str]`
  - `acceptance: list[dict]` with `label`, `proof`
  - `dependencies: str`
  - `notes: str`
- `milestones: list[dict]`:
  - `name: str`
  - `target: str` (date string)
  - `owner: str`
  - `status: str` (emoji + text)
  - `evidence: str` (e.g. `PROGRESS_LOG.md` anchor)

---

## 4. `CHECKLIST_TEMPLATE.md`

Defines `CHECKLIST.md` layout.

### Expected `metadata` keys

- `summary: str` – What this checklist verifies.
- `sections: list[dict]`:
  - `title: str`
  - `anchor: str`
  - `items: list[dict]` with:
    - `label: str`
    - `proof: str` (link to PROGRESS_LOG entry, commit, PR, screenshot, etc.)

`manage_docs.status_update` toggles `[ ]` ↔ `[x]` and may attach proof links; it does not require extra template metadata beyond the anchors.

---

## 5. Log Templates (`PROGRESS_LOG`, `DOC_LOG`, `SECURITY_LOG`, `BUG_LOG`)

These templates are simpler and mostly depend on:

- Global context defaults (project name, timestamps).
- Minimal `metadata` from `generate_doc_templates` (`summary`, possibly `is_rotation` for rotated logs).

The per-entry structure for logs (emoji, timestamp, agent, message, meta) is governed by `append_entry`, **not** the Jinja templates.

---

## 6. Registry & Doc Meta in Templates (Read-Only)

Some templates or future report docs may rely on registry-driven meta:

- `metadata.activity` (from Project Registry; read-only in templates):
  - `project_age_days`
  - `days_since_last_entry`
  - `days_since_last_access`
  - `staleness_level` (`fresh|warming|stale|frozen`)
  - `activity_score`
- `metadata.docs` (doc hygiene view for this project):
  - `last_update_at`
  - `baseline_hashes` / `current_hashes`
  - `flags`:
    - `docs_started`
    - `docs_ready_for_work`
    - `architecture_touched`, `architecture_modified`, etc.
    - `doc_drift_suspected`
  - `doc_drift_days_since_update`
  - `drift_score`

These values are populated by the Project Registry and surfaced via `list_projects` or higher-level tools; templates should treat them as **optional** and guard with `default()` / `if` checks.

---

## 7. Template Precedence (Where Templates Come From)

The engine discovers template directories in this order (first match wins):

1. Project-specific: `<project_root>/.scribe/templates/`
2. Repo-level custom templates (if configured via `RepoConfig`)
3. Project-root templates: `<project_root>/templates/`
4. Built-in packs: `templates/packs/<pack>/...`
5. Built-in root and defaults: `templates/`, `templates/documents/`, `templates/fragments/`

This means:

- You can override any built-in template by placing a file with the same name under `.scribe/templates/`.
- Pack templates provide alternate styles but are still overridden by project-local templates.

For more details on discovery and security (including `include_file` restrictions), see `template_engine/engine.py` and the main whitepaper’s template section.

