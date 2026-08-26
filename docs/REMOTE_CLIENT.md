# Remote/Client Posture

Release line: `2.12.0`
Updated: `2026-08-22`

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
- Named legacy SSE stream path: `<SCRIBE_REMOTE_URL>/sse`
- Named legacy message post path: `<SCRIBE_REMOTE_URL>/messages/`

MCP Python SDK v2 and the wire protocol are separate version axes. The Scribe server supports SDK `mcp>=2.0.0,<3.0`; the modern wire default is `2026-07-28`. The only preserved legacy client contract is `mcp==1.26.0` using protocol `2025-11-25`, handshake stdio, or the explicitly named `/sse` plus `/messages/` HTTP path.

## Supported Posture

| Posture | Network expectation | Auth expectation | Status |
| --- | --- | --- | --- |
| Local/core modern stdio | Local-only usage | Parent-process trust boundary | Default / supported |
| Modern `/mcp` on loopback or a managed private network | Operator-controlled reachability | Valid Origin plus bearer auth on non-health routes | Default HTTP protocol path; remote/client runtime remains internal only (`SCRIBE_RELEASE_PROFILE=internal`) |
| Named legacy `/sse` plus `/messages/` | Operator-controlled reachability; current single-worker/sticky process only | Same Origin and bearer-auth policy as `/mcp` | Explicit compatibility only |
| Casual public internet exposure | Open or casually internet-reachable endpoint | Not a supported public recipe | Unsupported |

## Bind and Auth Rules

- Treat remote/client as internal compatibility only for this release line.
- Treat `SCRIBE_TRANSPORT_AUTH_TOKEN` as an **operator-root credential**, not a scoped multi-user token. It grants the operator trust boundary access to every remotely permitted Scribe action.
- Apply the same Origin validation, authentication, request limits, and remote-tool authorization to `/mcp`, `/sse`, and `/messages/`; only `/health` is anonymous.
- Never derive authorization from an MCP session ID, agent label, `clientInfo`, request ID, capability, or caller-selected identifier.
- Never silently downgrade a failed modern request. Authentication, authorization, protocol, transport, capability, timeout, TLS, and malformed-request failures stay failures. Legacy mode is entered only by explicit compatibility policy or a recognized legacy endpoint.
- Legacy HTTP session continuity is supported only by the current single-worker, sticky-process deployment. Unknown-session and wrong-worker requests fail before dispatch; adding workers does not create a supported shared-session configuration.
- `0.0.0.0` guidance is only for managed deployments with explicit auth and private network controls.
- Do not publish unauthenticated broad-bind deployment as supported.
- Reachability alone does not make a deployment supported.

## Rollback and legacy retirement

Rollback is source-owned: restore the prior dependency, MCP adapter, and default protocol/transport policy from version control, then rerun the compatibility and auth/Origin checks. Do not implement rollback by treating a modern error as a legacy request.

Retire `/sse`, `/messages/`, protocol `2025-11-25`, and the `mcp==1.26.0` client lane only when all of these are true:

- protected telemetry shows no named legacy use for the agreed observation window
- every supported client has moved to modern stdio or `/mcp`
- modern and legacy tool schemas/results have passed the final parity gate
- Origin, bearer-auth, isolation, and malformed-no-fallback checks pass
- the source compatibility policy, public docs, and release notes are changed together

## Output safety and redaction

- Preview and commit surfaces must not emit plaintext secrets, bearer tokens, or credential-bearing DSNs.
- Treat any logs or screenshots as potentially shareable artifacts and keep credential material redacted.
