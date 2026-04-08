# Remote/Client Auth Posture

`scribe-mcp` ships with **local/standard core usage as the default public posture**. Remote/client mode is supported only as an **optional authenticated capability** for operators who intentionally deploy a managed remote Scribe service.

## 1. Default vs. optional posture

- **Default shipped posture:** local standalone usage, loopback-local server usage, and the standard core flows documented elsewhere in `scribe-mcp`.
- **Optional posture:** `remote/client` mode using `SCRIBE_REMOTE_URL` plus an auth token.
- **Not a default recipe:** setting a remote URL or binding a server broadly is **not** the normal public guidance for first-run or casual use.

If you enable remote/client mode, document and configure it as an explicit operator choice. Do not present it as the default way to run Scribe.

## 2. Auth contract for remote/client mode

Use the canonical client token variable:

- `SCRIBE_REMOTE_AUTH_TOKEN`

Compatibility aliases still load for single-env deployments:

- `SCRIBE_TRANSPORT_AUTH_TOKEN`
- `SCRIBE_AUTH_TOKEN`

Public docs should prefer the canonical client name. Remote/client mode is only supported when that auth contract is in place.

## 3. Release postures

| Posture | Bind / network expectation | Auth expectation | Support status |
| --- | --- | --- | --- |
| **Loopback-local** | Local process, stdio, or loopback bind such as `127.0.0.1` | Standard local posture; remote/client auth is not the default concern here | **Default / supported** |
| **Managed private-mesh / Tailscale** | Private mesh, VPN, or other managed operator-controlled network | **Required** for remote/client access | **Supported optional deployment** |
| **Casual public exposure** | Open or casually internet-reachable deployment | Not enough on its own; this posture is not a supported public recipe | **Unsupported** |

## 4. Bind/auth split

- `0.0.0.0` is allowed **only** for managed/private-mesh deployment guidance.
- Any `0.0.0.0` guidance must be paired with auth and an operator-managed private network boundary.
- Do **not** document unauthenticated `0.0.0.0` exposure as supported.
- Do **not** imply that remote/client mode is supported merely because the server is reachable.

## 5. Public guidance rule

When writing release or operator guidance for this repo:

1. Keep local/standard core usage as the default public story.
2. Treat remote/client mode as opt-in and authenticated.
3. Limit broad-bind (`0.0.0.0`) guidance to managed private-mesh/Tailscale deployments.
4. Reject casual public exposure as an endorsed deployment posture.
