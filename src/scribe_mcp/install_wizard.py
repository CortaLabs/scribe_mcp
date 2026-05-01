"""Install wizard planning and secure commit orchestration for local-first setup."""

from __future__ import annotations

import os
import stat
import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

from scribe_mcp.config.settings import Settings, settings
from scribe_mcp.scripts.bootstrap_postgres import BootstrapConfig, _bootstrap
from scribe_mcp.scripts.project_codex_plugin import project_codex_plugin, render_codex_projection_error
from scribe_mcp.tools.doctor import scribe_doctor
from scribe_mcp.utils.error_handler import sanitize_error_message

InstallProfile = Literal["local-postgres", "sqlite-eval", "existing-postgres", "internal-remote"]


@dataclass(frozen=True)
class InstallAction:
    category: Literal["db", "env", "docs", "projection"]
    intent: str
    mutation: Literal["none"]
    details: Dict[str, Any]


@dataclass(frozen=True)
class InstallPlan:
    mode: Literal["preview"]
    profile: InstallProfile
    redacted: bool
    repo_root: str
    security_posture: Dict[str, Any]
    actions: List[InstallAction]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["actions"] = [asdict(action) for action in self.actions]
        return data


def _redact_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    return "[redacted]"


def _redact_dsn(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    try:
        split = urlsplit(value)
    except Exception:
        return "[redacted]"
    netloc = split.netloc
    if "@" in netloc:
        _, host = netloc.rsplit("@", 1)
        netloc = f"[redacted]@{host}"
    return urlunsplit((split.scheme, netloc, split.path, split.query, split.fragment))


def _resolve_profile(profile: Optional[str]) -> InstallProfile:
    if profile is None:
        return "local-postgres"
    allowed = {"local-postgres", "sqlite-eval", "existing-postgres", "internal-remote"}
    if profile not in allowed:
        raise ValueError(f"unsupported install profile: {profile}")
    return profile  # type: ignore[return-value]


def _sanitize_text(value: str) -> str:
    text = sanitize_error_message(value)
    if "://" in text and "@" in text:
        text = str(_redact_dsn(text))
    return text


def _resolve_env_path(repo_root: Path, env_path: Optional[Path]) -> Path:
    target = (env_path or (repo_root / ".env")).expanduser()
    resolved = target.resolve(strict=False)
    repo_resolved = repo_root.resolve()
    if resolved != (repo_resolved / ".env"):
        raise ValueError("standard install only allows repo-root .env")
    if target.exists() and target.is_symlink():
        raise ValueError("refusing symlink .env target")
    return resolved


def _enforce_env_permissions(env_path: Path) -> None:
    mode = stat.S_IMODE(env_path.stat().st_mode)
    if mode > 0o600:
        os.chmod(env_path, 0o600)


def _build_bootstrap_config(repo_root: Path, env_path: Path, *, dry_run: bool, overwrite_env: bool, persist_superuser_env: bool) -> BootstrapConfig:
    return BootstrapConfig(
        superuser_user=os.environ.get("SCRIBE_POSTGRES_SUPERUSER_USER", "postgres"),
        superuser_password=os.environ.get("SCRIBE_POSTGRES_SUPERUSER_PASSWORD", ""),
        superuser_host=os.environ.get("SCRIBE_POSTGRES_SUPERUSER_HOST", "127.0.0.1"),
        superuser_port=int(os.environ.get("SCRIBE_POSTGRES_SUPERUSER_PORT", "5432")),
        superuser_db=os.environ.get("SCRIBE_POSTGRES_SUPERUSER_DB", "postgres"),
        admin_user=os.environ.get("SCRIBE_POSTGRES_ADMIN_USER", "scribe_admin"),
        admin_password=os.environ.get("SCRIBE_POSTGRES_ADMIN_PASSWORD", ""),
        admin_host=os.environ.get("SCRIBE_POSTGRES_ADMIN_HOST", "127.0.0.1"),
        admin_port=int(os.environ.get("SCRIBE_POSTGRES_ADMIN_PORT", "5432")),
        admin_db=os.environ.get("SCRIBE_POSTGRES_ADMIN_DB", "postgres"),
        app_user=os.environ.get("SCRIBE_POSTGRES_APP_USER", "scribe_app"),
        app_password=os.environ.get("SCRIBE_POSTGRES_APP_PASSWORD", ""),
        app_host=os.environ.get("SCRIBE_POSTGRES_APP_HOST", "127.0.0.1"),
        app_port=int(os.environ.get("SCRIBE_POSTGRES_APP_PORT", "5432")),
        app_db=os.environ.get("SCRIBE_POSTGRES_APP_DB", "scribe"),
        schema_name=os.environ.get("SCRIBE_POSTGRES_SCHEMA", "scribe"),
        env_path=env_path,
        overwrite_env=overwrite_env,
        persist_superuser_env=persist_superuser_env,
        dry_run=dry_run,
    )


def build_install_plan(*, repo_root: Path, profile: Optional[str] = None, include_advanced_profile: bool = False, runtime_settings: Optional[Settings] = None) -> InstallPlan:
    resolved = _resolve_profile(profile)
    if resolved == "internal-remote" and not include_advanced_profile:
        raise ValueError("profile 'internal-remote' is advanced/default-off; pass include_advanced_profile=True")

    cfg = runtime_settings or settings
    safe_remote_default = resolved != "internal-remote"
    safe_bind_default = cfg.transport_host in {"127.0.0.1", "localhost", "::1"}
    actions: List[InstallAction] = []
    if resolved in {"local-postgres", "existing-postgres"}:
        actions.append(
            InstallAction(
                category="db",
                intent="Prepare Postgres runtime connection surface for review",
                mutation="none",
                details={"db_url_preview": _redact_dsn(cfg.db_url), "postgres_schema": cfg.postgres_schema},
            )
        )
    if resolved == "internal-remote":
        actions.append(
            InstallAction(
                category="db",
                intent="Review internal remote/client posture before explicit opt-in",
                mutation="none",
                details={"remote_server_url": _redact_value(cfg.remote_server_url), "remote_fallback": False},
            )
        )
    actions.append(InstallAction(category="projection", intent="Keep Codex projection execution as explicit post-install opt-in", mutation="none", details={"auto_projection": False}))
    return InstallPlan(mode="preview", profile=resolved, redacted=True, repo_root=str(repo_root.resolve()), security_posture={"default_local_first": resolved in {"local-postgres", "sqlite-eval", "existing-postgres"}, "remote_default_off": safe_remote_default, "broad_bind_default_off": safe_bind_default, "db_mutation": False, "env_mutation": False, "projection_execution": False}, actions=actions)


async def execute_install_commit(*, repo_root: Path, profile: str, commit: bool, yes: bool, allow_advanced_profile: bool, dangerous_overwrite_secrets: bool = False) -> Dict[str, Any]:
    resolved_profile = _resolve_profile(profile)
    if resolved_profile == "internal-remote" and not allow_advanced_profile:
        raise ValueError("internal-remote profile is blocked by default")
    if not commit:
        raise ValueError("commit flag required for mutation")
    if not yes and not dangerous_overwrite_secrets:
        raise ValueError("explicit overwrite confirmation required")
    env_path = _resolve_env_path(repo_root, None)
    cfg = _build_bootstrap_config(repo_root, env_path, dry_run=False, overwrite_env=bool(dangerous_overwrite_secrets), persist_superuser_env=False)
    try:
        code = await _bootstrap(cfg)
    except Exception as exc:
        return {
            "ok": False,
            "profile": resolved_profile,
            "projection_executed": False,
            "persist_superuser_env": False,
            "env_path": str(env_path),
            "error": _sanitize_text(f"install commit failed: {exc}"),
        }
    _enforce_env_permissions(env_path)
    if code != 0:
        return {
            "ok": False,
            "profile": resolved_profile,
            "projection_executed": False,
            "persist_superuser_env": False,
            "env_path": str(env_path),
            "error": _sanitize_text("install commit failed"),
        }

    verification = await _run_post_install_verification()
    next_steps = _build_post_install_next_steps(repo_root=repo_root)
    return {
        "ok": True,
        "profile": resolved_profile,
        "projection_executed": False,
        "persist_superuser_env": False,
        "env_path": str(env_path),
        "message": _sanitize_text("install commit complete"),
        "post_install_verification": verification,
        "next_steps": next_steps,
    }


async def _run_post_install_verification() -> Dict[str, Any]:
    """Run existing lightweight diagnostics after base install commit."""
    try:
        payload = await asyncio.wait_for(
            scribe_doctor(agent="install-wizard"),
            timeout=10.0,
        )
        ok = bool(payload.get("ok", True)) and not bool(payload.get("error"))
        return {"ok": ok, "tool": "scribe_doctor", "result": payload}
    except TimeoutError:
        return {"ok": False, "tool": "scribe_doctor", "error": _sanitize_text("verification timed out")}
    except Exception as exc:
        return {"ok": False, "tool": "scribe_doctor", "error": _sanitize_text(f"verification failed: {exc}")}


def _build_post_install_next_steps(*, repo_root: Path) -> Dict[str, str]:
    root = str(repo_root.resolve())
    return {
        "project_root": root,
        "run_doctor": "python -m scribe_mcp.scripts.scribe_cli doctor --path .",
        "optional_projection": "scribe install --commit --yes --project-codex",
        "projection_note": "Projection is opt-in and never auto-runs during base install.",
    }


def execute_projection_opt_in(*, repo_root: Path, codex_home: Optional[Path] = None) -> Dict[str, Any]:
    """Explicit, optional Codex projection step run only by user selection."""
    plugin_root = repo_root / "plugins" / "codex"
    try:
        result = project_codex_plugin(plugin_root=plugin_root, codex_home=codex_home, config_path=None)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        return {"ok": False, "projection_executed": False, "error": _sanitize_text(render_codex_projection_error(exc))}
    return {"ok": True, "projection_executed": True, "result": result}
