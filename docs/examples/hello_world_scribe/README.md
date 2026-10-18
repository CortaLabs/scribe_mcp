# Pocket Mission Control

A public, docs-first Hello World Scribe demo that starts small and grows by phase.

This bundle is the tracked/public lane for the `Pocket Mission Control` story. It shows how to run a first mission safely, then expand into discovery, advanced operations, and admin references without leaking live runtime state.

## Story Arc

1. Launch: bind one project and read recent mission history.
2. Log: write one mission update and optionally note compatibility logging.
3. Govern: create/update one managed document.
4. Expand: inspect repo surfaces and query deeper history.
5. Operate: run reminders, diagnostics, and incident drills.
6. Admin: review appendix-only tools that stay outside the beginner path.

## Read Order

1. `core_walkthrough.md`
2. `discovery_and_search.md`
3. `advanced_ops.md`
4. `incident_drill.md`
5. `appendix_admin_tools.md`
6. `capability_matrix.md`
7. `publication_boundary.md`

## Feature-Lane Contract

- Core lane keeps first use short and centered on `set_project`, `read_recent`, `append_entry`, `manage_docs`, and `get_project`.
- Expansion lane introduces `list_projects`, `read_file`, `search`, and `query_entries`.
- Advanced ops lane adds `query_reminders`, `scribe_doctor`, and incident flow (`open_bug`, `open_security`, `link_fix`).
- Appendix/admin lane covers support and destructive surfaces intentionally kept out of the opening flow.

## Safety Rule

This docs bundle is publishable because it is curated prose and sanitized examples, not copied live state. For boundary details, read `publication_boundary.md`.
