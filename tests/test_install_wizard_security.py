from __future__ import annotations

import os
from pathlib import Path

import pytest

from scribe_mcp.install_wizard import build_install_plan, execute_install_commit


def test_preview_no_mutation(tmp_path: Path) -> None:
    env = tmp_path / '.env'
    env.write_text('X=1\n', encoding='utf-8')
    build_install_plan(repo_root=tmp_path, profile='local-postgres')
    assert env.read_text(encoding='utf-8') == 'X=1\n'


@pytest.mark.asyncio
async def test_commit_requires_explicit_flag(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        await execute_install_commit(repo_root=tmp_path, profile='local-postgres', commit=False, yes=True, allow_advanced_profile=False)


@pytest.mark.asyncio
async def test_commit_blocks_without_confirm(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        await execute_install_commit(repo_root=tmp_path, profile='local-postgres', commit=True, yes=False, allow_advanced_profile=False)


def test_preview_redacts_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('SCRIBE_DB_URL', 'postgresql://u:pw@localhost:5432/db')
    text = str(build_install_plan(repo_root=tmp_path, profile='local-postgres').to_dict())
    assert 'pw' not in text


def test_remote_advanced_default_off(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_install_plan(repo_root=tmp_path, profile='internal-remote')


@pytest.mark.asyncio
async def test_internal_remote_commit_fail_closed_without_allow_flag(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="blocked by default"):
        await execute_install_commit(
            repo_root=tmp_path,
            profile='internal-remote',
            commit=True,
            yes=True,
            allow_advanced_profile=False,
        )


@pytest.mark.asyncio
async def test_commit_failure_redacts_secrets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")

    async def _boom(_cfg):
        raise RuntimeError("bootstrap failed token=abc123 Authorization=Bearer super-secret postgresql://u:pw@localhost:5432/db")

    monkeypatch.setattr("scribe_mcp.install_wizard._bootstrap", _boom)
    payload = await execute_install_commit(
        repo_root=tmp_path,
        profile='local-postgres',
        commit=True,
        yes=True,
        allow_advanced_profile=False,
    )
    text = str(payload)
    assert payload["ok"] is False
    assert "abc123" not in text
    assert "super-secret" not in text
    assert "pw" not in text
    assert "[REDACTED]" in text or "[redacted]" in text
