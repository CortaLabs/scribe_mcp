"""Connection-pool internals for the Postgres storage backend."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

import asyncpg

LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 10.0
MAX_INACTIVE_CONNECTION_LIFETIME_SECONDS = 300.0
POOL_MIN_SIZE = 2
POOL_MAX_SIZE = 20
CONNECT_RETRIES = 3
CONNECT_RETRY_BACKOFF_SECONDS = 1.0
DEFAULT_SCHEMA_NAME = "scribe"

_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_schema_name(schema_name: str) -> str:
    candidate = (schema_name or DEFAULT_SCHEMA_NAME).strip()
    if not candidate:
        return DEFAULT_SCHEMA_NAME
    if not _SCHEMA_NAME_RE.match(candidate):
        raise ValueError(f"Invalid Postgres schema name: {schema_name!r}")
    return candidate


@dataclass(frozen=True)
class PostgresPoolConfig:
    min_size: int = POOL_MIN_SIZE
    max_size: int = POOL_MAX_SIZE
    command_timeout_seconds: float = COMMAND_TIMEOUT_SECONDS
    connect_timeout_seconds: float = CONNECT_TIMEOUT_SECONDS
    max_inactive_connection_lifetime_seconds: float = MAX_INACTIVE_CONNECTION_LIFETIME_SECONDS
    connect_retries: int = CONNECT_RETRIES
    connect_retry_backoff_seconds: float = CONNECT_RETRY_BACKOFF_SECONDS
    schema_name: str = DEFAULT_SCHEMA_NAME

    def normalized(self) -> "PostgresPoolConfig":
        min_size = max(1, int(self.min_size))
        max_size = max(min_size, int(self.max_size))
        return PostgresPoolConfig(
            min_size=min_size,
            max_size=max_size,
            command_timeout_seconds=max(1.0, float(self.command_timeout_seconds)),
            connect_timeout_seconds=max(1.0, float(self.connect_timeout_seconds)),
            max_inactive_connection_lifetime_seconds=max(
                1.0,
                float(self.max_inactive_connection_lifetime_seconds),
            ),
            connect_retries=max(0, int(self.connect_retries)),
            connect_retry_backoff_seconds=max(0.1, float(self.connect_retry_backoff_seconds)),
            schema_name=_validate_schema_name(self.schema_name),
        )


class PostgresInternals:
    """Owns asyncpg pool lifecycle."""

    def __init__(
        self,
        dsn: str,
        *,
        config: Optional[PostgresPoolConfig] = None,
    ) -> None:
        self._dsn = dsn
        self._config = (config or PostgresPoolConfig()).normalized()
        self._schema_name = self._config.schema_name
        self._pool: Optional[asyncpg.Pool] = None
        self._pool_lock = asyncio.Lock()

    @property
    def schema_name(self) -> str:
        return self._schema_name

    async def ensure_pool(self) -> asyncpg.Pool:
        async with self._pool_lock:
            if self._pool:
                return self._pool

            # Remote Postgres over Tailscale can transiently fail during startup.
            max_attempts = self._config.connect_retries + 1
            for attempt in range(1, max_attempts + 1):
                try:
                    self._pool = await asyncpg.create_pool(
                        dsn=self._dsn,
                        min_size=self._config.min_size,
                        max_size=self._config.max_size,
                        command_timeout=self._config.command_timeout_seconds,
                        timeout=self._config.connect_timeout_seconds,
                        max_inactive_connection_lifetime=(
                            self._config.max_inactive_connection_lifetime_seconds
                        ),
                        server_settings={"search_path": f"{self._schema_name},public"},
                    )
                    break
                except Exception:
                    if attempt >= max_attempts:
                        raise
                    backoff = self._config.connect_retry_backoff_seconds * (2 ** (attempt - 1))
                    LOGGER.warning(
                        "Postgres pool init failed (attempt %d/%d), retrying in %.2fs",
                        attempt,
                        max_attempts,
                        backoff,
                    )
                    await asyncio.sleep(backoff)

        assert self._pool is not None
        return self._pool

    async def close(self) -> None:
        async with self._pool_lock:
            if self._pool:
                await self._pool.close()
                self._pool = None

