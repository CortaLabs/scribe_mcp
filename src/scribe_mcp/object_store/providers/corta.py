"""CortaStore remote provider — content-addressable storage with refs.

CortaStore is our Hetzner-hosted object store exposing a REST API on
port 8201.  This provider handles HMAC signing, content hashing, the
ref indirection layer, and retry logic.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from typing import Any

import httpx

from scribe_mcp.object_store.base import RemoteProvider

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # seconds


class CortaStoreProvider(RemoteProvider):
    """Client for the CortaStore content-addressable object store."""

    def __init__(
        self,
        base_url: str,
        hmac_key: str,
        project: str,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._hmac_key = hmac_key.encode() if hmac_key else b""
        self._project = project
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle ------------------------------------------------------------

    async def setup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout),
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- helpers --------------------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def _sign(self, method: str, path: str, body: bytes = b"") -> dict[str, str]:
        """Compute HMAC signature headers per CortaStore spec.

        Signed payload: ``timestamp:METHOD:path:body_hash``
        Headers: X-Signature, X-Timestamp, X-Nonce (uuid4 for replay protection).
        """
        ts = str(int(time.time()))
        nonce = str(uuid.uuid4())
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{ts}:{method.upper()}:{path}:{body_hash}"
        sig = hmac.new(self._hmac_key, message.encode(), hashlib.sha256).hexdigest()
        return {
            "X-Signature": sig,
            "X-Timestamp": ts,
            "X-Nonce": nonce,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response | None:
        """Issue an HTTP request with retry + exponential backoff on 5xx."""
        client = self._ensure_client()
        # Compute sign body: if json_body is provided, serialize it for signing.
        if json_body is not None:
            import json as _json
            sign_body = _json.dumps(json_body).encode()
        else:
            sign_body = body or b""
        headers = self._sign(method, path, sign_body)
        kwargs: dict[str, Any] = {"headers": headers}
        if body is not None:
            kwargs["content"] = body
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            kwargs["content"] = sign_body

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.request(method, path, **kwargs)
                if resp.status_code < 500:
                    return resp
                logger.warning(
                    "CortaStore %s %s returned %s (attempt %d/%d)",
                    method, path, resp.status_code, attempt + 1, _MAX_RETRIES,
                )
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning(
                    "CortaStore %s %s failed: %s (attempt %d/%d)",
                    method, path, exc, attempt + 1, _MAX_RETRIES,
                )
            if attempt < _MAX_RETRIES - 1:
                await _async_sleep(_BACKOFF_BASE * (2 ** attempt))

        if last_exc:
            logger.error("CortaStore request exhausted retries: %s %s", method, path)
        return None

    # -- RemoteProvider interface ---------------------------------------------

    async def put(self, key: str, content: str) -> None:
        content_hash = self._content_hash(content)
        content_bytes = content.encode("utf-8")

        # 1. Store the object blob.
        resp = await self._request("PUT", f"/v1/objects/{content_hash}", body=content_bytes)
        if resp is None or resp.status_code >= 400:
            logger.warning("CortaStore: failed to PUT object %s", content_hash)
            return

        # 2. Create/update the ref that maps key → hash.
        ref_path = f"/v1/refs/{self._project}/{key}"
        resp = await self._request(
            "PUT", ref_path, json_body={"hash": content_hash},
        )
        if resp is None or resp.status_code >= 400:
            logger.warning("CortaStore: failed to PUT ref %s", ref_path)

    async def get(self, key: str) -> str | None:
        # Resolve ref → hash.
        ref_path = f"/v1/refs/{self._project}/{key}"
        resp = await self._request("GET", ref_path)
        if resp is None or resp.status_code != 200:
            return None
        try:
            content_hash = resp.json().get("hash")
        except Exception:
            return None
        if not content_hash:
            return None

        # Fetch the object.
        resp = await self._request("GET", f"/v1/objects/{content_hash}")
        if resp is None or resp.status_code != 200:
            return None
        return resp.text

    async def head(self, key: str) -> bool:
        """Check if a ref exists by issuing GET (refs endpoint has no HEAD)."""
        ref_path = f"/v1/refs/{self._project}/{key}"
        resp = await self._request("GET", ref_path)
        return resp is not None and resp.status_code == 200

    async def list(self, prefix: str = "") -> list[str]:
        path = f"/v1/refs/{self._project}/"
        # CortaStore accepts ?prefix= query parameter for server-side filtering.
        # We still do client-side filtering as a safety net.
        resp = await self._request("GET", path)
        if resp is None or resp.status_code != 200:
            return []
        try:
            data = resp.json()
            # Server returns {"project": "...", "refs": [{ref, hash, ...}, ...]}
            refs_list = data.get("refs", [])
            keys: list[str] = []
            for ref_entry in refs_list:
                if isinstance(ref_entry, dict):
                    ref_key = ref_entry.get("ref", "")
                elif isinstance(ref_entry, str):
                    ref_key = ref_entry
                else:
                    continue
                if ref_key and (not prefix or ref_key.startswith(prefix)):
                    keys.append(ref_key)
            return keys
        except Exception:
            return []

    async def delete(self, key: str) -> None:
        ref_path = f"/v1/refs/{self._project}/{key}"
        await self._request("DELETE", ref_path)

    async def bulk_check(self, keys: list[str]) -> list[str]:
        """Use CortaStore's ``/v1/sync/check`` bulk API."""
        if not keys:
            return []
        # Compute hashes for all keys — we need to check object existence.
        # Since we don't have content here, fall back to ref-based head checks.
        # The migration script provides content and can use the hash-based bulk
        # endpoint directly.
        return await super().bulk_check(keys)


async def _async_sleep(seconds: float) -> None:
    """Thin wrapper so tests can mock sleep."""
    import asyncio

    await asyncio.sleep(seconds)
