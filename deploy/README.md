# Deploying Scribe MCP

This guide covers the tracked deployment assets in `deploy/` for the frozen **2.5 compatibility-release** documentation wave.

The deployment contract in this wave is intentionally narrow:

- **local/core remains the default public posture**
- **authenticated SSE/remote deployment is optional**
- **casual public exposure is unsupported**

## Table of contents

- [Supported deployment postures](#supported-deployment-postures)
- [Quick start: authenticated local container](#quick-start-authenticated-local-container)
- [Council compose overlay](#council-compose-overlay)
- [Client connection example](#client-connection-example)
- [Files in this directory](#files-in-this-directory)
- [Related docs](#related-docs)

## Supported deployment postures

| Posture | Status | Notes |
| --- | --- | --- |
| Local/core stdio or loopback-local usage | **Default / supported** | Primary public posture for Scribe. |
| Managed private-mesh or Tailscale-style SSE deployment | **Supported optional posture** | Use auth and treat it as an intentional operator deployment. |
| Casual public exposure | **Unsupported** | Do not document or ship this as a normal deployment recipe. |

If you bind broadly inside a container, keep the host exposure narrow and the auth boundary explicit.

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

`SCRIBE_TRANSPORT_AUTH_TOKEN` is the server-side auth setting here. Client-side docs should prefer `SCRIBE_REMOTE_AUTH_TOKEN`; see [`../docs/REMOTE_CLIENT.md`](../docs/REMOTE_CLIENT.md).

## Council compose overlay

When you need the synchronized Council pairing, compose the two overlays from
the roots of your local checkouts:

```bash
docker compose \
  -f /path/to/council_mcp/deploy/docker-compose.yaml \
  -f /path/to/scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d
```

This keeps the same frozen contract:

- `council_mcp` consumes the installed-package `scribe-server` contract
- local/core remains the default story
- authenticated remote/SSE is optional

Use the matching `council_mcp` release docs from that checkout for the
Council-side contract details.

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
