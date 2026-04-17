"""Operating mode detection for Scribe MCP client/server split.

Determines whether Scribe runs as:
- SERVER: Full server with direct DB access (Hetzner deployment)
- CLIENT: Lightweight client proxying DB ops to remote server
- STANDALONE: Local-only with SQLite (no remote server configured)
"""

from __future__ import annotations

import enum
import logging
from typing import TYPE_CHECKING, Optional

import httpx

if TYPE_CHECKING:
    from scribe_mcp.config.settings import Settings

logger = logging.getLogger(__name__)


class OperatingMode(str, enum.Enum):
    """Scribe MCP operating mode."""
    SERVER = "server"
    CLIENT = "client"
    STANDALONE = "standalone"


class RemoteProbeStatus(str, enum.Enum):
    """Connectivity/auth result for the remote health probe."""

    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"


def resolve_configured_mode(settings: Settings) -> OperatingMode:
    """Resolve the configured storage contract without network probing."""
    mode_setting = settings.mode
    configured_backend = str(getattr(settings, "storage_backend", "postgres")).strip().lower() or "postgres"
    db_url = getattr(settings, "db_url", None)
    if _is_public_release(settings):
        if mode_setting == OperatingMode.CLIENT.value:
            raise RuntimeError(
                "SCRIBE_MODE=client is not supported in SCRIBE_RELEASE_PROFILE=public. "
                "Initial public release excludes remote/client mode."
            )
        if settings.remote_server_url:
            raise RuntimeError(
                "SCRIBE_REMOTE_URL is not supported in SCRIBE_RELEASE_PROFILE=public. "
                "Initial public release excludes remote/client mode."
            )
    if mode_setting in (
        OperatingMode.SERVER.value,
        OperatingMode.CLIENT.value,
        OperatingMode.STANDALONE.value,
    ):
        if mode_setting == OperatingMode.SERVER.value and configured_backend != "postgres":
            raise RuntimeError(
                "SCRIBE_MODE=server requires SCRIBE_STORAGE_BACKEND=postgres. "
                "SQLite is only supported when explicitly running standalone mode."
            )
        if mode_setting == OperatingMode.SERVER.value and not db_url:
            raise RuntimeError(
                "SCRIBE_MODE=server requires SCRIBE_DB_URL. "
                "Server/public-release runtime fail-closes when Postgres configuration is missing."
            )
        return OperatingMode(mode_setting)

    if settings.remote_server_url:
        return OperatingMode.CLIENT

    if configured_backend == "sqlite":
        return OperatingMode.STANDALONE

    if db_url:
        return OperatingMode.SERVER

    raise RuntimeError(
        "Server-class runtime requires Postgres configuration. "
        "Set SCRIBE_DB_URL for Postgres server mode, or explicitly opt into standalone SQLite "
        "with SCRIBE_MODE=standalone and SCRIBE_STORAGE_BACKEND=sqlite."
    )


async def detect_operating_mode(settings: Settings) -> OperatingMode:
    """Detect operating mode from settings and remote server availability.

    Detection priority:
    1. Explicit SCRIBE_MODE setting (server/client/standalone) — honor directly
    2. SCRIBE_REMOTE_URL set — probe the remote server health endpoint
       - Reachable + valid response → CLIENT
       - Unreachable + fallback enabled → STANDALONE (with warning)
       - Unreachable + fallback disabled → raise RuntimeError
    3. Local runtime storage selection
       - Explicit SQLite backend → STANDALONE
       - Direct Postgres runtime configured → SERVER
       - Postgres default without DB URL → fail closed
    """
    configured_mode = resolve_configured_mode(settings)
    mode_setting = settings.mode

    # 1. Explicit mode override
    if mode_setting in ("server", "client", "standalone"):
        resolved = configured_mode
        logger.info("Operating mode: %s (explicit via SCRIBE_MODE)", resolved.value)
        return resolved

    # 2. Remote URL configured — probe it
    if configured_mode == OperatingMode.CLIENT and settings.remote_server_url:
        probe_status = await _probe_remote(
            settings.remote_server_url,
            timeout=settings.remote_connect_timeout,
            auth_token=getattr(settings, "remote_auth_token", None),
        )
        if probe_status == RemoteProbeStatus.REACHABLE:
            logger.info(
                "Operating mode: client (remote server at %s is reachable)",
                settings.remote_server_url,
            )
            return OperatingMode.CLIENT

        if probe_status == RemoteProbeStatus.AUTH_FAILED:
            raise RuntimeError(
                "Remote server at "
                f"{settings.remote_server_url} rejected client authentication during health probing. "
                "Configure SCRIBE_REMOTE_AUTH_TOKEN "
                "(or compatibility aliases SCRIBE_TRANSPORT_AUTH_TOKEN / SCRIBE_AUTH_TOKEN)."
            )

        # Remote unreachable
        if _is_public_release(settings):
            raise RuntimeError(
                "Remote probing failed in SCRIBE_RELEASE_PROFILE=public. "
                "Public release mode fail-closes remote/client startup."
            )

        if settings.remote_fallback:
            logger.warning(
                "Remote server at %s unreachable — falling back to standalone mode. "
                "Set SCRIBE_REMOTE_FALLBACK=false to make this a hard failure.",
                settings.remote_server_url,
            )
            return OperatingMode.STANDALONE

        raise RuntimeError(
            f"Remote server at {settings.remote_server_url} is unreachable "
            f"and SCRIBE_REMOTE_FALLBACK is disabled. Cannot start."
        )

    # 3. DB URL set (direct database access) → server mode
    if configured_mode == OperatingMode.SERVER:
        logger.info("Operating mode: server (direct database runtime configured)")
        return configured_mode

    # 4. Default → standalone
    logger.info("Operating mode: standalone (local SQLite runtime configured)")
    return configured_mode


async def _probe_remote(
    url: str,
    timeout: float = 3.0,
    auth_token: Optional[str] = None,
) -> RemoteProbeStatus:
    """Probe the remote Scribe server's health endpoint.

    Returns a connectivity/auth status for the remote health endpoint.
    """
    health_url = url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(health_url, headers=_remote_auth_headers(auth_token))
            if resp.status_code in (401, 403):
                logger.warning(
                    "Health endpoint at %s rejected remote client auth with status %d",
                    health_url,
                    resp.status_code,
                )
                return RemoteProbeStatus.AUTH_FAILED
            if resp.status_code == 200:
                data = resp.json()
                # Verify it's actually a Scribe server
                if data.get("service") == "scribe-mcp" or data.get("status") == "ok":
                    return RemoteProbeStatus.REACHABLE
                logger.warning(
                    "Health endpoint at %s responded but doesn't look like Scribe: %s",
                    health_url, data,
                )
                return RemoteProbeStatus.UNREACHABLE
            logger.warning("Health endpoint at %s returned status %d", health_url, resp.status_code)
            return RemoteProbeStatus.UNREACHABLE
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.debug("Remote probe failed for %s: %s", health_url, exc)
        return RemoteProbeStatus.UNREACHABLE
    except Exception as exc:
        logger.warning("Unexpected error probing %s: %s", health_url, exc)
        return RemoteProbeStatus.UNREACHABLE


def _remote_auth_headers(auth_token: Optional[str]) -> dict[str, str]:
    """Build auth headers for remote health probes."""
    if not auth_token:
        return {}
    return {
        "Authorization": f"Bearer {auth_token}",
        "x-scribe-auth": auth_token,
    }


def _is_public_release(settings: Settings) -> bool:
    """Return whether runtime is using public-release fail-closed profile."""
    if bool(getattr(settings, "public_release", False)):
        return True
    return str(getattr(settings, "release_profile", "internal")).strip().lower() == "public"
