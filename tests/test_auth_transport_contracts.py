from __future__ import annotations

import pytest

from scribe_mcp.auth import APIKeyAuthProvider, AuthRequest, JWTAuthProvider
from scribe_mcp.auth.base import AuthProvider
from scribe_mcp.transport import (
    HTTPSSETransportProvider,
    OutboundMessage,
    TransportProvider,
    WebSocketTransportProvider,
)


def test_auth_and_transport_base_imports() -> None:
    assert AuthProvider.__name__ == "AuthProvider"
    assert TransportProvider.__name__ == "TransportProvider"


@pytest.mark.asyncio
async def test_api_key_auth_stub_raises_clear_not_implemented() -> None:
    provider = APIKeyAuthProvider()
    request = AuthRequest(credentials={"api_key": "test"})

    with pytest.raises(NotImplementedError, match="scaffold"):
        await provider.authenticate(request)


@pytest.mark.asyncio
async def test_jwt_auth_stub_raises_clear_not_implemented() -> None:
    provider = JWTAuthProvider(issuer="https://issuer.local", audience="scribe")
    request = AuthRequest(credentials={"jwt": "token"})

    with pytest.raises(NotImplementedError, match="scaffold"):
        await provider.authenticate(request)


@pytest.mark.asyncio
async def test_transport_stubs_raise_clear_not_implemented() -> None:
    ws_provider = WebSocketTransportProvider(endpoint_url="wss://example.invalid/ws")
    sse_provider = HTTPSSETransportProvider(endpoint_url="https://example.invalid/sse")
    message = OutboundMessage(channel="control", payload={"ping": True})

    with pytest.raises(NotImplementedError, match="scaffold"):
        await ws_provider.start()
    with pytest.raises(NotImplementedError, match="scaffold"):
        await ws_provider.send_message(message)
    with pytest.raises(NotImplementedError, match="scaffold"):
        await sse_provider.start()
    with pytest.raises(NotImplementedError, match="scaffold"):
        await sse_provider.send_message(message)

