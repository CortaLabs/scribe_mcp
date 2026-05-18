"""Tests for operating mode detection."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scribe_mcp.config.mode_detection import (
    OperatingMode,
    RemoteProbeStatus,
    _probe_remote,
    detect_operating_mode,
    resolve_configured_mode,
)


class FakeSettings:
    """Minimal settings stub for testing."""
    def __init__(self, mode="auto", remote_server_url=None, remote_connect_timeout=3.0,
                 remote_fallback=True, db_url=None, storage_backend=None, release_profile="internal",
                 project_root=None):
        self.mode = mode
        self.remote_server_url = remote_server_url
        self.remote_connect_timeout = remote_connect_timeout
        self.remote_fallback = remote_fallback
        self.db_url = db_url
        self.storage_backend = storage_backend or ("postgres" if db_url else "sqlite")
        self.release_profile = release_profile
        self.public_release = release_profile == "public"
        self.project_root = project_root or Path(__file__).parent / "_mode_detection_fixture_repo"


@pytest.mark.asyncio
async def test_explicit_server_mode():
    s = FakeSettings(mode="server", db_url="postgresql://localhost/scribe", storage_backend="postgres")
    assert await detect_operating_mode(s) == OperatingMode.SERVER


@pytest.mark.asyncio
async def test_explicit_client_mode():
    s = FakeSettings(mode="client")
    assert await detect_operating_mode(s) == OperatingMode.CLIENT


@pytest.mark.asyncio
async def test_explicit_standalone_mode():
    s = FakeSettings(mode="standalone")
    assert await detect_operating_mode(s) == OperatingMode.STANDALONE


@pytest.mark.asyncio
async def test_remote_url_reachable_returns_client():
    s = FakeSettings(remote_server_url="http://localhost:8200")
    with patch(
        "scribe_mcp.config.mode_detection._probe_remote",
        new_callable=AsyncMock,
        return_value=RemoteProbeStatus.REACHABLE,
    ):
        assert await detect_operating_mode(s) == OperatingMode.CLIENT


@pytest.mark.asyncio
async def test_remote_url_unreachable_fallback_returns_standalone():
    s = FakeSettings(remote_server_url="http://localhost:8200", remote_fallback=True)
    with patch(
        "scribe_mcp.config.mode_detection._probe_remote",
        new_callable=AsyncMock,
        return_value=RemoteProbeStatus.UNREACHABLE,
    ):
        assert await detect_operating_mode(s) == OperatingMode.STANDALONE


@pytest.mark.asyncio
async def test_remote_url_unreachable_no_fallback_raises():
    s = FakeSettings(remote_server_url="http://localhost:8200", remote_fallback=False)
    with patch(
        "scribe_mcp.config.mode_detection._probe_remote",
        new_callable=AsyncMock,
        return_value=RemoteProbeStatus.UNREACHABLE,
    ):
        with pytest.raises(RuntimeError, match="unreachable"):
            await detect_operating_mode(s)


@pytest.mark.asyncio
async def test_db_url_returns_server():
    s = FakeSettings(db_url="postgresql://localhost/scribe")
    assert await detect_operating_mode(s) == OperatingMode.SERVER


@pytest.mark.asyncio
async def test_nothing_set_returns_standalone():
    s = FakeSettings(storage_backend="postgres")
    with pytest.raises(RuntimeError, match="requires Postgres configuration"):
        await detect_operating_mode(s)


@pytest.mark.asyncio
async def test_auto_mode_with_remote_url_probes():
    """auto mode with remote_server_url should probe, not default."""
    s = FakeSettings(mode="auto", remote_server_url="http://example.com:8200")
    with patch(
        "scribe_mcp.config.mode_detection._probe_remote",
        new_callable=AsyncMock,
        return_value=RemoteProbeStatus.REACHABLE,
    ) as mock_probe:
        result = await detect_operating_mode(s)
        assert result == OperatingMode.CLIENT
        mock_probe.assert_called_once_with(
            "http://example.com:8200",
            timeout=3.0,
            auth_token=None,
        )


def test_resolve_configured_mode_prefers_remote_url_for_auto_mode():
    s = FakeSettings(
        mode="auto",
        remote_server_url="http://remote.example:8200",
        db_url="postgresql://localhost/scribe",
        storage_backend="postgres",
    )

    assert resolve_configured_mode(s) == OperatingMode.CLIENT


def test_resolve_configured_mode_keeps_sqlite_standalone_when_db_url_is_present():
    s = FakeSettings(
        mode="auto",
        db_url="postgresql://localhost/scribe",
        storage_backend="sqlite",
    )

    assert resolve_configured_mode(s) == OperatingMode.STANDALONE


def test_resolve_configured_mode_fail_closed_for_server_without_db_url():
    s = FakeSettings(mode="server", db_url=None, storage_backend="postgres")

    with pytest.raises(RuntimeError, match="requires SCRIBE_DB_URL"):
        resolve_configured_mode(s)


@pytest.mark.asyncio
async def test_public_release_profile_rejects_explicit_client_mode():
    s = FakeSettings(mode="client", release_profile="public")
    with pytest.raises(RuntimeError, match="Initial public release excludes remote/client mode"):
        await detect_operating_mode(s)


@pytest.mark.asyncio
async def test_public_release_profile_rejects_remote_url_auto_mode():
    s = FakeSettings(mode="auto", remote_server_url="http://localhost:8200", release_profile="public")
    with pytest.raises(RuntimeError, match="Initial public release excludes remote/client mode"):
        await detect_operating_mode(s)
