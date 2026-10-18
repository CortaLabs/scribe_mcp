from __future__ import annotations

import pytest

from scribe_mcp.config.mode_detection import detect_operating_mode
from scribe_mcp.config.settings import Settings


@pytest.mark.asyncio
async def test_public_release_rejects_client_mode_on_startup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    monkeypatch.setenv("SCRIBE_MODE", "client")

    settings = Settings.load()
    with pytest.raises(RuntimeError, match="Initial public release excludes remote/client mode"):
        await detect_operating_mode(settings)


@pytest.mark.asyncio
async def test_public_release_rejects_remote_url_auto_mode_on_startup(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    monkeypatch.setenv("SCRIBE_MODE", "auto")
    monkeypatch.setenv("SCRIBE_REMOTE_URL", "http://127.0.0.1:8200")

    settings = Settings.load()
    with pytest.raises(RuntimeError, match="Initial public release excludes remote/client mode"):
        await detect_operating_mode(settings)


def test_public_release_defaults_remote_fallback_to_fail_closed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRIBE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    monkeypatch.delenv("SCRIBE_REMOTE_FALLBACK", raising=False)

    settings = Settings.load()
    assert settings.remote_fallback is False
