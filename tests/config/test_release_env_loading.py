"""Release-safe repo-root dotenv loading tests for Package 4.2."""

from __future__ import annotations

from pathlib import Path

from scribe_mcp.config import settings as settings_module


def test_public_release_does_not_implicitly_load_repo_dotenv(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[Path, bool]] = []

    def fake_loader(path: Path, override: bool = False) -> None:
        calls.append((path, override))

    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    monkeypatch.delenv("SCRIBE_LOAD_REPO_DOTENV", raising=False)
    monkeypatch.setattr(settings_module, "repo_root", lambda: tmp_path)

    loaded = settings_module._load_repo_root_dotenv(load_dotenv_fn=fake_loader)

    assert loaded is False
    assert calls == []


def test_public_release_can_explicitly_enable_repo_dotenv_loading(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[Path, bool]] = []

    def fake_loader(path: Path, override: bool = False) -> None:
        calls.append((path, override))

    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    monkeypatch.setenv("SCRIBE_LOAD_REPO_DOTENV", "true")
    monkeypatch.setattr(settings_module, "repo_root", lambda: tmp_path)

    loaded = settings_module._load_repo_root_dotenv(load_dotenv_fn=fake_loader)

    assert loaded is True
    assert calls == [(tmp_path / ".env", False)]


def test_internal_release_loads_repo_dotenv_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[Path, bool]] = []

    def fake_loader(path: Path, override: bool = False) -> None:
        calls.append((path, override))

    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "internal")
    monkeypatch.delenv("SCRIBE_LOAD_REPO_DOTENV", raising=False)
    monkeypatch.setattr(settings_module, "repo_root", lambda: tmp_path)

    loaded = settings_module._load_repo_root_dotenv(load_dotenv_fn=fake_loader)

    assert loaded is True
    assert calls == [(tmp_path / ".env", False)]
