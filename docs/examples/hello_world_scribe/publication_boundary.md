# Publication Boundary

This page defines the hard separation between live-local demo state and tracked-public example material.

## Two Lanes

| Lane | Purpose | Git status | Allowed content |
|---|---|---|---|
| Live local lane | Real operator run state | Ignored/local | runtime docs, logs, reminders, cases, scratch output |
| Tracked public lane | Curated example for readers | Tracked | markdown walkthroughs and sanitized example payloads |

## Live Local (Never Publish)

Keep these local-only:

- `.scribe/**` runtime docs, logs, state, backups, vectors
- local project DB/state files
- operator-specific config values and absolute local paths
- temp/scratch output under ignored demo paths

## Tracked Public (Safe to Publish)

Keep these in the example bundle:

- narrative docs for `Pocket Mission Control`
- sanitized JSON payload examples (later coder wave)
- generic, placeholder-only configuration examples
- diagrams/screenshots that do not expose runtime state

## Sanitization Checklist

1. Remove live project IDs and host-specific paths.
2. Replace user/org names with placeholders.
3. Exclude copied logs/case timelines from `.scribe/**`.
4. Keep examples explanatory, not archival.

## Enforcement

- Do not treat live workspace output as publication artifacts.
- Do not copy raw `.scribe/**` content into `docs/examples/hello_world_scribe/`.
- If a value must be shown, rewrite it as an explicit placeholder.
