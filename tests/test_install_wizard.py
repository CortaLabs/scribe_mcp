from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scribe_mcp.cli.main import main
from scribe_mcp.install_wizard import _resolve_env_path, build_install_plan, execute_install_commit


@pytest.mark.parametrize(
    "profile",
    ["local-postgres", "sqlite-eval", "existing-postgres"],
)
def test_supported_profiles_preview_only(tmp_path: Path, profile: str) -> None:
    plan = build_install_plan(repo_root=tmp_path, profile=profile).to_dict()
    assert plan["mode"] == "preview"
    assert plan["security_posture"]["db_mutation"] is False
    assert plan["security_posture"]["env_mutation"] is False


def test_advanced_profile_is_default_off(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="advanced/default-off"):
        build_install_plan(repo_root=tmp_path, profile="internal-remote")

    plan = build_install_plan(
        repo_root=tmp_path,
        profile="internal-remote",
        include_advanced_profile=True,
    ).to_dict()
    assert plan["profile"] == "internal-remote"
    assert plan["security_posture"]["remote_default_off"] is False


def test_preview_redacts_sensitive_values_and_contains_no_plaintext_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCRIBE_DB_URL", "postgresql://user:secret@localhost:5432/dbname")
    monkeypatch.setenv("SCRIBE_REMOTE_URL", "http://token.example.internal")

    from scribe_mcp.config.settings import Settings

    plan = build_install_plan(
        repo_root=tmp_path,
        profile="existing-postgres",
        runtime_settings=Settings.load(),
    ).to_dict()

    plan_text = str(plan)
    assert "secret" not in plan_text
    assert "postgresql://user:secret" not in plan_text
    assert "token.example.internal" not in plan_text
    assert "[redacted]" in plan_text


def test_preview_has_zero_db_and_env_mutation(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    before = "EXISTING=1\n"
    env_path.write_text(before, encoding="utf-8")

    _ = build_install_plan(repo_root=tmp_path, profile="local-postgres").to_dict()

    assert env_path.read_text(encoding="utf-8") == before


def test_env_path_symlink_and_outside_repo_refused(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    target = tmp_path / "target.env"
    target.write_text("X=1\n", encoding="utf-8")
    env_path.symlink_to(target)
    with pytest.raises(ValueError, match="repo-root .env|symlink"):
        asyncio.run(execute_install_commit(repo_root=tmp_path, profile="local-postgres", commit=True, yes=True, allow_advanced_profile=False))
    with pytest.raises(ValueError, match="repo-root .env"):
        _resolve_env_path(tmp_path, tmp_path.parent / ".env")


@pytest.mark.asyncio
async def test_commit_preserves_existing_secrets_without_dangerous_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("SCRIBE_POSTGRES_APP_PASSWORD=keepme\n", encoding="utf-8")

    captured = {}

    async def _fake_bootstrap(cfg):
        captured["overwrite_env"] = cfg.overwrite_env
        return 0

    monkeypatch.setattr("scribe_mcp.install_wizard._bootstrap", _fake_bootstrap)
    payload = await execute_install_commit(repo_root=tmp_path, profile="local-postgres", commit=True, yes=True, allow_advanced_profile=False, dangerous_overwrite_secrets=False)
    assert payload["ok"] is True
    assert captured["overwrite_env"] is False


@pytest.mark.asyncio
async def test_commit_dangerous_override_sets_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SCRIBE_POSTGRES_APP_PASSWORD=replace\n", encoding="utf-8")
    captured = {}

    async def _fake_bootstrap(cfg):
        captured["overwrite_env"] = cfg.overwrite_env
        return 0

    monkeypatch.setattr("scribe_mcp.install_wizard._bootstrap", _fake_bootstrap)
    payload = await execute_install_commit(repo_root=tmp_path, profile="local-postgres", commit=True, yes=True, allow_advanced_profile=False, dangerous_overwrite_secrets=True)
    assert payload["ok"] is True
    assert captured["overwrite_env"] is True


@pytest.mark.asyncio
async def test_commit_hardens_env_permissions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("X=1\n", encoding="utf-8")
    env_path.chmod(0o666)

    async def _fake_bootstrap(_cfg):
        return 0

    monkeypatch.setattr("scribe_mcp.install_wizard._bootstrap", _fake_bootstrap)
    await execute_install_commit(repo_root=tmp_path, profile="local-postgres", commit=True, yes=True, allow_advanced_profile=False)
    assert env_path.stat().st_mode & 0o777 <= 0o600


@pytest.mark.asyncio
async def test_commit_runs_post_install_verification_without_projection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")

    async def _fake_bootstrap(_cfg):
        return 0

    async def _fake_doctor(agent: str):
        assert agent == "install-wizard"
        return {"ok": True, "checks": []}

    monkeypatch.setattr("scribe_mcp.install_wizard._bootstrap", _fake_bootstrap)
    monkeypatch.setattr("scribe_mcp.install_wizard.scribe_doctor", _fake_doctor)
    payload = await execute_install_commit(repo_root=tmp_path, profile="local-postgres", commit=True, yes=True, allow_advanced_profile=False)
    assert payload["ok"] is True
    assert payload["projection_executed"] is False
    assert payload["post_install_verification"]["tool"] == "scribe_doctor"
    assert payload["post_install_verification"]["ok"] is True
    assert payload["next_steps"]["optional_projection"] == "scribe install --commit --yes --project-codex"


def test_cli_project_codex_is_explicit_opt_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = {"projection": 0}

    async def _fake_execute_install_commit(**_kwargs):
        return {"ok": True, "projection_executed": False}

    def _fake_execute_projection_opt_in(**_kwargs):
        calls["projection"] += 1
        return {"ok": True, "projection_executed": True}

    monkeypatch.setattr("scribe_mcp.install_wizard.execute_install_commit", _fake_execute_install_commit)
    monkeypatch.setattr("scribe_mcp.install_wizard.execute_projection_opt_in", _fake_execute_projection_opt_in)

    rc = main(["install", "--repo-root", str(tmp_path), "--commit", "--yes"])
    assert rc == 0
    assert calls["projection"] == 0

    rc = main(["install", "--repo-root", str(tmp_path), "--commit", "--yes", "--project-codex"])
    assert rc == 0
    assert calls["projection"] == 1


def test_cli_yes_without_commit_is_preview_only(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    before = "A=1\n"
    env_path.write_text(before, encoding="utf-8")
    rc = main(["install", "--repo-root", str(tmp_path), "--yes"])
    assert rc == 0
    assert env_path.read_text(encoding="utf-8") == before
