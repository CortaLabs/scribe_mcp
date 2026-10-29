# Deploying Scribe MCP

This guide describes the supported public deployment posture for the v2.5 release docs.

The supported story is intentionally narrow:

- local/core is the default
- authenticated SSE server deployment is optional
- casual public internet exposure is unsupported

## Table of contents

- [Supported deployment postures](#supported-deployment-postures)
- [Quick start: authenticated local container](#quick-start-authenticated-local-container)
- [Composable deployment overlay](#composable-deployment-overlay)
- [Client connection example](#client-connection-example)
- [Files in this directory](#files-in-this-directory)
- [Related docs](#related-docs)

## Supported deployment postures

| Posture | Status | Notes |
| --- | --- | --- |
| Local/core stdio or loopback-local usage | **Default / supported** | Primary public posture. |
| Managed private-mesh or Tailscale-style SSE deployment | **Supported optional posture** | Auth is required for server transport access. |
| Casual public internet exposure | **Unsupported** | Not a supported public recipe. |

If you bind broadly inside a container, keep the host exposure narrow and the auth boundary explicit.

### Canonical env/auth names (v2.5)

Use these names in public docs and examples:

- `SCRIBE_REMOTE_URL`: client endpoint URL
- `SCRIBE_REMOTE_AUTH_TOKEN`: client bearer token
- `SCRIBE_TRANSPORT_AUTH_TOKEN`: server-side token the service validates

Compatibility aliases may still load in mixed environments (`SCRIBE_AUTH_TOKEN`, and on the client side `SCRIBE_TRANSPORT_AUTH_TOKEN`), but public docs should lead with the canonical names above.

## Quick start: authenticated local container

Build the image:

```bash
docker build -f deploy/Dockerfile -t scribe-mcp:latest .
```

Run an authenticated container with host-loopback exposure only:

```bash
export SCRIBE_TRANSPORT_AUTH_TOKEN="$(python - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"

docker run -d \
  --name scribe-mcp \
  -p 127.0.0.1:8200:8200 \
  -e SCRIBE_TRANSPORT=sse \
  -e SCRIBE_TRANSPORT_HOST=0.0.0.0 \
  -e SCRIBE_TRANSPORT_PORT=8200 \
  -e SCRIBE_TRANSPORT_AUTH_TOKEN="$SCRIBE_TRANSPORT_AUTH_TOKEN" \
  -v scribe_data:/app/.scribe \
  scribe-mcp:latest
```

Check health:

```bash
curl http://127.0.0.1:8200/health
```

`SCRIBE_TRANSPORT_AUTH_TOKEN` is the server-side auth setting here. The initial public release excludes remote/client mode (`SCRIBE_RELEASE_PROFILE=public` in release artifacts), so release docs do not publish a remote client bootstrap path.

## Composable deployment overlay

The overlay can be validated independently:

```bash
docker compose -f deploy/docker-compose.scribe.yaml config
```

For a deployment, combine it with your infrastructure Compose file. That file
must provide a healthy `postgres` service and the configured object-store service;
the overlay's PostgreSQL stub supports configuration validation only. Provision
the declared secrets before starting services. Scribe is internal to the shared
`backend` network and exposes no host ports in this overlay.

The deployment contract remains:

- local integrations use the installed-package `scribe-server` CLI contract
- local/core remains the default story
- authenticated SSE server transport is optional
- casual public internet exposure is unsupported

Use your infrastructure's deployment instructions for service readiness and secret provisioning.

## Client connection example

Minimal authenticated SSE client configuration:

```json
{
  "mcpServers": {
    "scribe": {
      "url": "http://127.0.0.1:8200/sse",
      "headers": {
        "Authorization": "Bearer ${SCRIBE_REMOTE_AUTH_TOKEN}"
      }
    }
  }
}
```

Public bootstrap examples should come from tracked files, not repo-root overlays. See [`../docs/examples/mcp.json.example`](../docs/examples/mcp.json.example).

## Files in this directory

| Path | Purpose |
| --- | --- |
| `deploy/Dockerfile` | Builds the Scribe container image. |
| `deploy/docker-compose.scribe.yaml` | Compose overlay for the synchronized Scribe deployment. |
| `deploy/docker-entrypoint.sh` | Entrypoint and environment/secrets wiring. |
| `deploy/README.md` | This concise deployment guide. |

## Related docs

- [`../docs/COMPATIBILITY_MATRIX.md`](../docs/COMPATIBILITY_MATRIX.md)
- [`../docs/RELEASE_SURFACE.md`](../docs/RELEASE_SURFACE.md)
- [`../docs/REMOTE_CLIENT.md`](../docs/REMOTE_CLIENT.md)
- [`../docs/RELEASE_FILE_MAP.md`](../docs/RELEASE_FILE_MAP.md)
