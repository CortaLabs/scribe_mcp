"""API key auth provider scaffold."""

from __future__ import annotations

from typing import Any, Mapping

from .base import AuthProvider, AuthRequest, AuthResult


class APIKeyAuthProvider(AuthProvider):
    """Placeholder API key provider for remote daemon->Scribe calls."""

    def __init__(self, *, key_header: str = "Authorization") -> None:
        self._key_header = key_header

    @property
    def key_header(self) -> str:
        return self._key_header

    async def authenticate(self, request: AuthRequest) -> AuthResult:
        raise NotImplementedError(
            "API key auth provider is a scaffold. Implement credential validation before production use."
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
            "API key auth provider is a scaffold. Implement policy checks before production use."
        )

    async def revoke(
        self,
        *,
        principal_id: str,
        token_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        raise NotImplementedError(
            "API key auth provider is a scaffold. Implement token revocation before production use."
        )

