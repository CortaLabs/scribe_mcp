# Remote/Client Posture

Release line: `3.x` development candidate
Updated: `2026-10-28`

`scribe-mcp` public onboarding is Postgres-first and fail-closed for remote/client mode.
For this release line, remote/client is internal compatibility only and excluded when `SCRIBE_RELEASE_PROFILE=public`.

## Canonical public names

Use these names:

- `SCRIBE_REMOTE_URL`: remote service root URL (for example `http://127.0.0.1:8200`)
- `SCRIBE_REMOTE_AUTH_TOKEN`: client bearer token used for `Authorization: Bearer ...`
- `SCRIBE_TRANSPORT_AUTH_TOKEN`: server-side token that the deployed Scribe service validates

Compatibility aliases may still load in mixed environments (`SCRIBE_AUTH_TOKEN` and, on the client side, `SCRIBE_TRANSPORT_AUTH_TOKEN`), but they are not the primary public naming story.

## Endpoint distinction

- Health probe path: `<SCRIBE_REMOTE_URL>/health` (used during mode detection)
- Modern MCP path: `<SCRIBE_REMOTE_URL>/mcp` (Streamable HTTP, protocol `2026-07-28`)

MCP Python SDK and wire protocol versions are separate. The 3.x policy targets the latest SDK and protocol `2026-07-28`; release verification currently uses SDK `2.3.0`. SDK 1.x, older wire revisions, and legacy SSE endpoints are unsupported. Removal of obsolete compatibility code and explicit rejection of old requests remain release work; see [the compatibility matrix](COMPATIBILITY_MATRIX.md).

## Supported Posture

| Posture | Network expectation | Auth expectation | Status |
| --- | --- | --- | --- |
| Local/core modern stdio | Local-only usage | Parent-process trust boundary | Default / supported |
| Modern `/mcp` on loopback or a managed private network | Operator-controlled reachability | Valid Origin plus bearer auth on non-health routes | Default HTTP protocol path; remote/client runtime remains internal only (`SCRIBE_RELEASE_PROFILE=internal`) |
| Casual public internet exposure | Open or casually internet-reachable endpoint | Not a supported public recipe | Unsupported |

## Bind and Auth Rules

- Treat remote/client as internal compatibility only for this release line.
- Treat `SCRIBE_TRANSPORT_AUTH_TOKEN` as an **operator-root credential**, not a scoped multi-user token. It grants the operator trust boundary access to every remotely permitted Scribe action.
- Apply Origin validation, authentication, request limits, and remote-tool authorization to `/mcp`; only `/health` is anonymous.
- Never derive authorization from an MCP session ID, agent label, `clientInfo`, request ID, capability, or caller-selected identifier.
- Never silently downgrade a failed request. Authentication, authorization, protocol, transport, capability, timeout, TLS, and malformed-request failures stay failures.
- `0.0.0.0` guidance is only for managed deployments with explicit auth and private network controls.
- Do not publish unauthenticated broad-bind deployment as supported.
- Reachability alone does not make a deployment supported.

## Rollback

Rollback is source-owned: restore the prior dependency, MCP adapter, and default protocol/transport policy from version control, then rerun the compatibility and auth/Origin checks. Do not implement rollback by treating a modern error as a legacy request.

## Output safety and redaction

- Preview and commit surfaces must not emit plaintext secrets, bearer tokens, or credential-bearing DSNs.
- Treat any logs or screenshots as potentially shareable artifacts and keep credential material redacted.
