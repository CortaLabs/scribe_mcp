"""Persistent session state for the standalone Scribe CLI under `.scribe/cli/`."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scribe_mcp.config.paths import cli_session_state_path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_scoped_reuse_key(repo_root: Path, project_name: str | None) -> str:
    """Build deterministic repo/project scoped key for session reuse boundaries."""
    normalized_repo_root = str(repo_root.resolve())
    normalized_project = (project_name or "").strip() or "__prebinding__"
    return f"{normalized_repo_root}:{normalized_project}"


def build_transport_session_id(
    repo_root: Path,
    session_name: str,
    agent: str,
    project_name: str | None = None,
) -> str:
    """Build deterministic transport session ID for repeatable CLI sessions."""
    scope_key = build_scoped_reuse_key(repo_root, project_name)
    source = f"{repo_root.resolve()}:{session_name}:{agent}:{scope_key}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"cli:{digest}"


@dataclass
class CliSessionState:
    """Serializable state for one named CLI session."""

    session_name: str
    repo_root: str
    agent: str
    transport_session_id: str
    context: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_utc_now_iso)

    @classmethod
    def from_dict(
        cls,
        payload: Dict[str, Any],
        *,
        session_name: str,
        repo_root: Path,
        agent: str,
    ) -> "CliSessionState":
        context = payload.get("context")
        if not isinstance(context, dict):
            context = {}

        project_name_raw = context.get("project_name")
        project_name = str(project_name_raw) if isinstance(project_name_raw, str) else None
        transport_session_id = payload.get("transport_session_id")
        expected_transport_session_id = build_transport_session_id(
            repo_root,
            session_name,
            agent,
            project_name=project_name,
        )
        if not isinstance(transport_session_id, str) or not transport_session_id:
            transport_session_id = expected_transport_session_id
        elif transport_session_id != expected_transport_session_id:
            transport_session_id = expected_transport_session_id

        scoped_reuse_key = build_scoped_reuse_key(repo_root, project_name)
        context["scoped_reuse_key"] = scoped_reuse_key
        context["session_reuse_scope"] = scoped_reuse_key
        context["session_scope_state"] = "project_bound" if project_name else "pre_binding"

        context.setdefault("repo_root", str(repo_root.resolve()))
        context.setdefault("transport_session_id", transport_session_id)

        return cls(
            session_name=session_name,
            repo_root=str(repo_root.resolve()),
            agent=agent,
            transport_session_id=transport_session_id,
            context=context,
            updated_at=str(payload.get("updated_at") or _utc_now_iso()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_name": self.session_name,
            "repo_root": self.repo_root,
            "agent": self.agent,
            "transport_session_id": self.transport_session_id,
            "context": self.context,
            "updated_at": self.updated_at,
        }


def scoped_session_state_path(session_name: str, repo_root: Path, agent: str) -> Path:
    """Locate advisory cache by caller tuple, independently of project/transport identity."""
    key = json.dumps([str(repo_root.resolve()), session_name, agent], ensure_ascii=True)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return cli_session_state_path(f"scoped-{digest}")


def _read_payload(session_path: Path) -> Dict[str, Any] | None:
    try:
        payload = json.loads(session_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _matches_tuple(payload: Dict[str, Any], session_name: str, repo_root: Path, agent: str) -> bool:
    # Neither the filename nor its contents grant runtime authorization.
    return (
        payload.get("agent") == agent
        and payload.get("repo_root") == str(repo_root.resolve())
        and payload.get("session_name") == session_name
    )


def load_session_state(session_name: str, repo_root: Path, agent: str) -> CliSessionState:
    """Load caller-scoped state, with exact-tuple compatibility for old cache files."""
    session_path = scoped_session_state_path(session_name, repo_root, agent)
    # An invalid scoped cache must not resurrect an older legacy binding.
    if not session_path.exists():
        session_path = cli_session_state_path(session_name)
    payload = _read_payload(session_path)
    if payload is not None and _matches_tuple(payload, session_name, repo_root, agent):
        return CliSessionState.from_dict(
            payload, session_name=session_name, repo_root=repo_root, agent=agent,
        )

    transport_session_id = build_transport_session_id(repo_root, session_name, agent)
    scoped_reuse_key = build_scoped_reuse_key(repo_root, None)
    return CliSessionState(
        session_name=session_name,
        repo_root=str(repo_root.resolve()),
        agent=agent,
        transport_session_id=transport_session_id,
        context={
            "repo_root": str(repo_root.resolve()),
            "transport_session_id": transport_session_id,
            "scoped_reuse_key": scoped_reuse_key,
            "session_reuse_scope": scoped_reuse_key,
            "session_scope_state": "pre_binding",
        },
    )


def save_session_state(state: CliSessionState) -> Path:
    """Persist session state to the repo-local `.scribe/cli/` runtime namespace."""
    state.repo_root = str(Path(state.repo_root).resolve())
    session_path = scoped_session_state_path(state.session_name, Path(state.repo_root), state.agent)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = _utc_now_iso()
    session_path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return session_path


def reset_session_state(session_name: str, repo_root: Path, agent: str) -> list[Path]:
    """Remove only this caller's scoped or exact-matching legacy advisory state."""
    removed = []
    scoped = scoped_session_state_path(session_name, repo_root, agent)
    for path in (scoped, cli_session_state_path(session_name)):
        payload = _read_payload(path)
        # Corrupt state at our own locator can be reset. A shared legacy file
        # or a valid foreign tuple must never be removed as this caller's state.
        matches = payload is not None and _matches_tuple(payload, session_name, repo_root, agent)
        if path.exists() and (matches or (path == scoped and payload is None)):
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed
