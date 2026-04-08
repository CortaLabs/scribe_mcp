"""Tests for CortaStoreProvider and S3Provider."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ---------------------------------------------------------------------------
# CortaStoreProvider
# ---------------------------------------------------------------------------

from scribe_mcp.object_store.providers.corta import CortaStoreProvider


class TestCortaStoreHMAC:
    def test_sign_produces_valid_headers(self) -> None:
        provider = CortaStoreProvider(
            base_url="http://localhost:8201",
            hmac_key="test-secret",
            project="proj",
        )
        headers = provider._sign("PUT", "/v1/objects/abc123", body=b"hello")
        # Must use CortaStore-spec header names.
        assert "X-Signature" in headers
        assert "X-Timestamp" in headers
        assert "X-Nonce" in headers
        # Nonce should be a uuid4 string.
        import uuid
        uuid.UUID(headers["X-Nonce"])  # Raises if not valid UUID

        # Verify the signature is deterministic for a given timestamp.
        ts = headers["X-Timestamp"]
        body_hash = hashlib.sha256(b"hello").hexdigest()
        msg = f"{ts}:PUT:/v1/objects/abc123:{body_hash}"
        expected = hmac.new(b"test-secret", msg.encode(), hashlib.sha256).hexdigest()
        assert headers["X-Signature"] == expected

    def test_content_hash(self) -> None:
        h = CortaStoreProvider._content_hash("hello world")
        assert h == hashlib.sha256(b"hello world").hexdigest()


class TestCortaStoreProviderPut:
    @pytest.mark.asyncio
    async def test_put_calls_object_then_ref(self) -> None:
        provider = CortaStoreProvider(
            base_url="http://localhost:8201",
            hmac_key="key",
            project="proj",
        )

        responses: list[MagicMock] = []

        async def mock_request(method, path, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {}
            responses.append((method, path))
            return resp

        provider._request = mock_request  # type: ignore[assignment]

        await provider.put("docs/test.md", "# Test")

        methods_paths = responses
        # First call: PUT object.
        assert methods_paths[0][0] == "PUT"
        assert "/v1/objects/" in methods_paths[0][1]
        # Second call: PUT ref.
        assert methods_paths[1][0] == "PUT"
        assert "/v1/refs/proj/" in methods_paths[1][1]


class TestCortaStoreProviderGet:
    @pytest.mark.asyncio
    async def test_get_resolves_ref_then_object(self) -> None:
        provider = CortaStoreProvider(
            base_url="http://localhost:8201",
            hmac_key="key",
            project="proj",
        )
        content = "# Hello"
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        call_log: list[tuple[str, str]] = []

        async def mock_request(method, path, **kwargs):
            call_log.append((method, path))
            resp = MagicMock()
            if "/v1/refs/" in path:
                resp.status_code = 200
                resp.json.return_value = {"hash": content_hash}
            elif f"/v1/objects/{content_hash}" in path:
                resp.status_code = 200
                resp.text = content
            else:
                resp.status_code = 404
            return resp

        provider._request = mock_request  # type: ignore[assignment]

        result = await provider.get("docs/test.md")
        assert result == content
        assert len(call_log) == 2
        assert call_log[0][0] == "GET"  # ref
        assert call_log[1][0] == "GET"  # object


class TestCortaStoreProviderList:
    @pytest.mark.asyncio
    async def test_list_parses_refs_response(self) -> None:
        """Server returns {project, refs: [{ref, hash, ...}, ...]}."""
        provider = CortaStoreProvider(
            base_url="http://localhost:8201",
            hmac_key="key",
            project="proj",
        )

        async def mock_request(method, path, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "project": "proj",
                "refs": [
                    {"ref": "docs/a.md", "hash": "aaa", "updated_at": "..."},
                    {"ref": "docs/b.md", "hash": "bbb", "updated_at": "..."},
                    {"ref": "config/c.yaml", "hash": "ccc", "updated_at": "..."},
                ],
            }
            return resp

        provider._request = mock_request  # type: ignore[assignment]

        # All keys
        keys = await provider.list()
        assert keys == ["docs/a.md", "docs/b.md", "config/c.yaml"]

        # With prefix filter
        keys = await provider.list(prefix="docs/")
        assert keys == ["docs/a.md", "docs/b.md"]

    @pytest.mark.asyncio
    async def test_list_handles_empty_refs(self) -> None:
        provider = CortaStoreProvider(
            base_url="http://localhost:8201",
            hmac_key="key",
            project="proj",
        )

        async def mock_request(method, path, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"project": "proj", "refs": []}
            return resp

        provider._request = mock_request  # type: ignore[assignment]
        assert await provider.list() == []


class TestCortaStoreProviderHead:
    @pytest.mark.asyncio
    async def test_head_uses_get_not_head(self) -> None:
        """Refs endpoint has no HEAD support — we use GET."""
        provider = CortaStoreProvider(
            base_url="http://localhost:8201",
            hmac_key="key",
            project="proj",
        )
        call_log: list[tuple[str, str]] = []

        async def mock_request(method, path, **kwargs):
            call_log.append((method, path))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"ref": "docs/a.md", "hash": "aaa"}
            return resp

        provider._request = mock_request  # type: ignore[assignment]

        result = await provider.head("docs/a.md")
        assert result is True
        assert call_log[0][0] == "GET"  # NOT "HEAD"


# ---------------------------------------------------------------------------
# S3Provider — import guard
# ---------------------------------------------------------------------------

class TestS3ProviderImportGuard:
    def test_raises_when_boto3_missing(self) -> None:
        with patch.dict(sys.modules, {"boto3": None}):
            from scribe_mcp.object_store.providers.s3 import _get_boto3
            with pytest.raises(ImportError, match="boto3"):
                _get_boto3()


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

from scribe_mcp.object_store.providers import create_provider


class TestProviderRegistry:
    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            create_provider("nonexistent")

    def test_corta_provider_instantiates(self) -> None:
        p = create_provider(
            "corta",
            base_url="http://localhost:8201",
            hmac_key="k",
            project="p",
        )
        assert isinstance(p, CortaStoreProvider)
