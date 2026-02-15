"""HTTP/SSE transport scaffold."""

from __future__ import annotations

from .base import OutboundMessage, TransportProvider, TransportReceipt


class HTTPSSETransportProvider(TransportProvider):
    """Placeholder HTTP/SSE transport for remote fallback delivery."""

    def __init__(self, *, endpoint_url: str) -> None:
        self._endpoint_url = endpoint_url

    @property
    def endpoint_url(self) -> str:
        return self._endpoint_url

    async def start(self) -> None:
        raise NotImplementedError(
            "HTTP/SSE transport is a scaffold. Implement connection/session startup before production use."
        )

    async def stop(self) -> None:
        raise NotImplementedError(
            "HTTP/SSE transport is a scaffold. Implement graceful shutdown before production use."
        )

    async def send_message(self, message: OutboundMessage) -> TransportReceipt:
        raise NotImplementedError(
            "HTTP/SSE transport is a scaffold. Implement outbound delivery before production use."
        )

