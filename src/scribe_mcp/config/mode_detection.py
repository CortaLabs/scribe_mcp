"""Operating mode detection for Scribe MCP client/server split.

Determines whether Scribe runs as:
- SERVER: Full server with direct DB access (Hetzner deployment)
- CLIENT: Lightweight client proxying DB ops to remote server
- STANDALONE: Local-only with SQLite (no remote server configured)
"""

from __future__ import annotations

import enum
import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from scribe_mcp.config.settings import Settings

logger = logging.getLogger(__name__)


class OperatingMode(str, enum.Enum):
    """Scribe MCP operating mode."""
    SERVER = "server"
    CLIENT = "client"
    STANDALONE = "standalone"


async def detect_operating_mode(settings: Settings) -> OperatingMode:
    """Detect operating mode from settings and remote server availability.

    Detection priority:
    1. Explicit SCRIBE_MODE setting (server/client/standalone) — honor directly
    2. SCRIBE_REMOTE_URL set — probe the remote server health endpoint
       - Reachable + valid response → CLIENT
       - Unreachable + fallback enabled → STANDALONE (with warning)
       - Unreachable + fallback disabled → raise RuntimeError
    3. SCRIBE_DB_URL set (no remote URL) → SERVER
    4. Nothing set → STANDALONE (default)
    """
    mode_setting = settings.mode

    # 1. Explicit mode override
    if mode_setting in ("server", "client", "standalone"):
        resolved = OperatingMode(mode_setting)
        logger.info("Operating mode: %s (explicit via SCRIBE_MODE)", resolved.value)
        return resolved

    # 2. Remote URL configured — probe it
    if settings.remote_server_url:
        reachable = await _probe_remote(
            settings.remote_server_url,
            timeout=settings.remote_connect_timeout,
        )
        if reachable:
            logger.info(
                "Operating mode: client (remote server at %s is reachable)",
                settings.remote_server_url,
            )
            return OperatingMode.CLIENT

        # Remote unreachable
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
    if settings.db_url:
        logger.info("Operating mode: server (SCRIBE_DB_URL configured, no remote URL)")
        return OperatingMode.SERVER

    # 4. Default → standalone
    logger.info("Operating mode: standalone (no remote URL or DB URL configured)")
    return OperatingMode.STANDALONE


async def _probe_remote(url: str, timeout: float = 3.0) -> bool:
    """Probe the remote Scribe server's health endpoint.

    Returns True if the server responds with a valid health check.
    """
    health_url = url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(health_url)
            if resp.status_code == 200:
                data = resp.json()
                # Verify it's actually a Scribe server
                if data.get("service") == "scribe-mcp" or data.get("status") == "ok":
                    return True
                logger.warning(
                    "Health endpoint at %s responded but doesn't look like Scribe: %s",
                    health_url, data,
                )
                return False
            logger.warning("Health endpoint at %s returned status %d", health_url, resp.status_code)
            return False
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.debug("Remote probe failed for %s: %s", health_url, exc)
        return False
    except Exception as exc:
        logger.warning("Unexpected error probing %s: %s", health_url, exc)
        return False
