# Remote/Client Posture

`scribe-mcp` defaults to local/core usage. Initial public release artifacts set `SCRIBE_RELEASE_PROFILE=public`, which excludes remote/client mode.

## Canonical Public Names (v2.5)

Use these names in public docs and examples:

- `SCRIBE_REMOTE_URL`: client endpoint URL (for example `http://127.0.0.1:8200/sse`)
- `SCRIBE_REMOTE_AUTH_TOKEN`: client bearer token used for `Authorization: Bearer ...`
- `SCRIBE_TRANSPORT_AUTH_TOKEN`: server-side token that the deployed Scribe service validates

Compatibility aliases may still load in mixed environments (`SCRIBE_AUTH_TOKEN` and, on the client side, `SCRIBE_TRANSPORT_AUTH_TOKEN`), but they are not the primary public naming story.

## Supported Posture

| Posture | Network expectation | Auth expectation | Status |
| --- | --- | --- | --- |
| Local/core (stdio or loopback such as `127.0.0.1`) | Local-only usage | Remote auth variables are optional | Default / supported |
| Managed private network (private mesh, VPN, Tailscale, or equivalent) | Operator-controlled remote reachability | Required for remote/client mode | Internal compatibility only (`SCRIBE_RELEASE_PROFILE=internal`) |
| Casual public internet exposure | Open or casually internet-reachable endpoint | Not a supported public recipe | Unsupported |

## Bind and Auth Rules

- Treat remote/client as internal compatibility only for this release line.
- `0.0.0.0` guidance is only for managed deployments with explicit auth and private network controls.
- Do not publish unauthenticated broad-bind deployment as supported.
- Reachability alone does not make a deployment supported.
