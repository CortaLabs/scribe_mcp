"""Transport contracts for remote Scribe deployments."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class OutboundMessage:
    """Message envelope sent through a transport provider."""

    channel: str
    payload: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransportReceipt:
    """Delivery receipt returned by transport providers."""

    transport: str
    message_id: str
    delivered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Mapping[str, Any] = field(default_factory=dict)


class TransportProvider(ABC):
    """Contract for transport providers (websocket/http-sse/etc)."""

    @abstractmethod
    async def start(self) -> None:
        """Start transport lifecycle resources."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop transport lifecycle resources."""

    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> TransportReceipt:
        """Send an outbound message and return a delivery receipt."""

