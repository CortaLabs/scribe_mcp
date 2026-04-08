#!/usr/bin/env bash
# =============================================================================
# Scribe MCP - Docker Entrypoint Script
# =============================================================================
#
# Bridges Docker secrets to environment variables and hands off to CMD.
#
# Docker secrets are files mounted at /run/secrets/<name>. Our application
# reads SCRIBE_DB_URL from an environment variable, not a file. This script
# bridges the gap:
#   1. Checks if the secret file exists and the env var is not already set
#   2. Reads the file and exports it as an environment variable
#   3. Logs startup configuration for debugging
#   4. Hands off to the actual application command via exec
#
# The Dockerfile sets:
#   ENTRYPOINT ["tini", "--", "./deploy/docker-entrypoint.sh"]
#   CMD ["scribe-server-sse"]
#
# Docker combines these: tini runs this script with CMD as arguments.
# The "exec "$@"" at the bottom replaces this script with the actual
# command, so scribe-server-sse becomes the main process under tini.
#
# =============================================================================

# Exit immediately if any command fails.
# Treat unset variables as errors.
# Fail on any command in a pipeline, not just the last one.
set -euo pipefail

# ---------------------------------------------------------------------------
# Bridge Docker secrets to environment variables
# ---------------------------------------------------------------------------
# Only export if the env var is not already set AND the secret file exists.
# This lets you override secrets with regular environment variables for
# development and testing.
# ---------------------------------------------------------------------------

if [ -z "${SCRIBE_DB_URL:-}" ] && [ -f /run/secrets/scribe_db_url ]; then
    SCRIBE_DB_URL="$(cat /run/secrets/scribe_db_url)"
    export SCRIBE_DB_URL
    echo "[scribe-entrypoint] Loaded SCRIBE_DB_URL from Docker secret"
fi

if [ -z "${SCRIBE_OBJECT_STORE_KEY:-}" ] && [ -f /run/secrets/store_hmac_key ]; then
    SCRIBE_OBJECT_STORE_KEY="$(cat /run/secrets/store_hmac_key)"
    export SCRIBE_OBJECT_STORE_KEY
    echo "[scribe-entrypoint] Loaded SCRIBE_OBJECT_STORE_KEY from Docker secret"
fi

if [ -z "${SCRIBE_TRANSPORT_AUTH_TOKEN:-}" ] && [ -f /run/secrets/scribe_transport_auth_token ]; then
    SCRIBE_TRANSPORT_AUTH_TOKEN="$(cat /run/secrets/scribe_transport_auth_token)"
    export SCRIBE_TRANSPORT_AUTH_TOKEN
    echo "[scribe-entrypoint] Loaded SCRIBE_TRANSPORT_AUTH_TOKEN from Docker secret"
fi

# ---------------------------------------------------------------------------
# Log startup configuration
# ---------------------------------------------------------------------------
# Print key configuration values for debugging container startup issues.
# Sensitive values (SCRIBE_DB_URL) are intentionally not logged.
# ---------------------------------------------------------------------------

echo "[scribe-entrypoint] Transport: ${SCRIBE_TRANSPORT:-stdio}"
echo "[scribe-entrypoint] Port: ${SCRIBE_TRANSPORT_PORT:-8200}"
echo "[scribe-entrypoint] Storage: ${SCRIBE_STORAGE_BACKEND:-sqlite}"

# ---------------------------------------------------------------------------
# Hand off to the actual command as the scribe user
# ---------------------------------------------------------------------------
# The entrypoint runs as root to read secrets (owned by root).
# gosu drops privileges to the scribe user before exec'ing the app.
# This ensures the application process runs as non-root (UID 1001).
#
# "exec" replaces this shell process with the command.
# "$@" expands to all arguments passed to this script (the CMD from Dockerfile).
# ---------------------------------------------------------------------------
exec gosu scribe "$@"
