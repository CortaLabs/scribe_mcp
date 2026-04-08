"""S3-compatible remote provider for downstream OSS users.

Supports AWS S3, MinIO, Cloudflare R2, and any S3-compatible service.
Requires ``boto3`` as an optional dependency — install with
``pip install scribe-mcp[s3]``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from scribe_mcp.object_store.base import RemoteProvider

logger = logging.getLogger(__name__)


def _get_boto3() -> Any:
    """Lazy-import boto3, raising a clear error if missing."""
    try:
        import boto3  # type: ignore[import-untyped]

        return boto3
    except ImportError:
        raise ImportError(
            "S3 provider requires boto3. Install with: pip install scribe-mcp[s3]"
        ) from None


class S3Provider(RemoteProvider):
    """Standard S3-compatible object storage provider."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "scribe/",
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        timeout: float = 10.0,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._endpoint_url = endpoint_url
        self._region = region
        self._timeout = timeout
        self._client: Any = None

    def _s3_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def setup(self) -> None:
        boto3 = _get_boto3()
        kwargs: dict[str, Any] = {"region_name": self._region}
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        self._client = boto3.client("s3", **kwargs)

    async def close(self) -> None:
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            boto3 = _get_boto3()
            kwargs: dict[str, Any] = {"region_name": self._region}
            if self._endpoint_url:
                kwargs["endpoint_url"] = self._endpoint_url
            self._client = boto3.client("s3", **kwargs)
        return self._client

    # -- RemoteProvider interface ---------------------------------------------

    async def put(self, key: str, content: str) -> None:
        client = self._ensure_client()
        try:
            await asyncio.to_thread(
                client.put_object,
                Bucket=self._bucket,
                Key=self._s3_key(key),
                Body=content.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
        except Exception:
            logger.warning("S3 PUT failed for %s", key, exc_info=True)

    async def get(self, key: str) -> str | None:
        client = self._ensure_client()
        try:
            resp = await asyncio.to_thread(
                client.get_object,
                Bucket=self._bucket,
                Key=self._s3_key(key),
            )
            body = resp["Body"].read()
            return body.decode("utf-8")
        except client.exceptions.NoSuchKey:
            return None
        except Exception:
            logger.warning("S3 GET failed for %s", key, exc_info=True)
            return None

    async def head(self, key: str) -> bool:
        client = self._ensure_client()
        try:
            await asyncio.to_thread(
                client.head_object,
                Bucket=self._bucket,
                Key=self._s3_key(key),
            )
            return True
        except Exception:
            return False

    async def list(self, prefix: str = "") -> list[str]:
        client = self._ensure_client()
        full_prefix = self._s3_key(prefix)
        keys: list[str] = []
        try:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
                for obj in page.get("Contents", []):
                    # Strip the S3 prefix to return Scribe keys.
                    raw = obj["Key"]
                    if raw.startswith(self._prefix):
                        keys.append(raw[len(self._prefix):])
                    else:
                        keys.append(raw)
        except Exception:
            logger.warning("S3 LIST failed for prefix %s", prefix, exc_info=True)
        return keys

    async def delete(self, key: str) -> None:
        client = self._ensure_client()
        try:
            await asyncio.to_thread(
                client.delete_object,
                Bucket=self._bucket,
                Key=self._s3_key(key),
            )
        except Exception:
            logger.warning("S3 DELETE failed for %s", key, exc_info=True)

    async def bulk_check(self, keys: list[str]) -> list[str]:
        """S3 has no bulk-exists API — fall back to per-key HEAD."""
        missing: list[str] = []
        for k in keys:
            if not await self.head(k):
                missing.append(k)
        return missing
