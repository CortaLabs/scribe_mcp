"""Authentication contracts for remote Scribe deployments."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class AuthRequest:
    """Input payload passed to authentication providers."""

    credentials: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthResult:
    """Authentication result used by authorization/transport layers."""

    authenticated: bool
    principal_id: str | None = None
    scopes: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)


class AuthProvider(ABC):
    """Contract for auth providers used by remote callers."""

    @abstractmethod
    async def authenticate(self, request: AuthRequest) -> AuthResult:
        """Validate credentials and return caller identity details."""

    @abstractmethod
    async def authorize(
        self,
        *,
        principal_id: str,
        action: str,
        resource: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return True when a principal can perform the requested action."""

    @abstractmethod
    async def revoke(
        self,
        *,
        principal_id: str,
        token_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Revoke active credentials/tokens for a principal."""

