# Appendix: Admin Tools

These tools are intentionally outside the beginner story but still part of complete capability accounting.

## Compatibility Logging

- `append_event`: compatibility/support path that delegates to standard logging behavior in project mode.
- Use when integrating legacy event flows, not as the primary mission log action.

## Reminder Administration

- `configure_reminders`: sets reminder defaults/policy.
- `reset_reminders`: clears reminder history/cooldowns under explicit flags.

Why appendix-only: these mutate reminder policy and are not needed for first-run understanding.

## Case/Template Support

- `list_open_cases`: operational case backlog visibility.
- `generate_doc_templates`: scaffold support for managed docs workflows.

Why appendix-only: support utilities are useful after core and advanced lanes are understood.

## Authorization And Log Maintenance

- `authorize_repo_root`: trust-boundary/repo authorization support.
- `rotate_log`: maintenance operation for log lifecycle.

Why appendix-only: operational hygiene, not first-use onboarding.

## Destructive/Constrained Surfaces

- `delete_project`: destructive admin action.
- `edit_file`: constrained mutation requiring prior `read_file` on target path and boundary checks.

Why appendix-only:
- high blast radius (`delete_project`)
- contract-heavy mutation path (`edit_file`)

These tools should be used with explicit intent after operators are fluent in core and advanced lanes.
