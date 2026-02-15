"""JWT auth provider scaffold."""

from __future__ import annotations

from typing import Any, Mapping

from .base import AuthProvider, AuthRequest, AuthResult


class JWTAuthProvider(AuthProvider):
    """Placeholder JWT provider for remote client sessions."""

    def __init__(self, *, issuer: str | None = None, audience: str | None = None) -> None:
        self._issuer = issuer
        self._audience = audience

    @property
    def issuer(self) -> str | None:
        return self._issuer

    @property
    def audience(self) -> str | None:
        return self._audience

    async def authenticate(self, request: AuthRequest) -> AuthResult:
        raise NotImplementedError(
            "JWT auth provider is a scaffold. Implement token verification before production use."
        )

    async def authorize(
        self,
        *,
        principal_id: str,
        action: str,
        resource: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        raise NotImplementedError(
            "JWT auth provider is a scaffold. Implement claim/policy checks before production use."
        )

    async def revoke(
        self,
        *,
        principal_id: str,
        token_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        raise NotImplementedError(
            "JWT auth provider is a scaffold. Implement token revocation before production use."
        )

