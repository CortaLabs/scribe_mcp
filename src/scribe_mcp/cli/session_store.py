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


def build_transport_session_id(repo_root: Path, session_name: str, agent: str) -> str:
    """Build deterministic transport session ID for repeatable CLI sessions."""
    source = f"{repo_root.resolve()}:{session_name}:{agent}"
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

        transport_session_id = payload.get("transport_session_id")
        if not isinstance(transport_session_id, str) or not transport_session_id:
            transport_session_id = build_transport_session_id(repo_root, session_name, agent)

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


def load_session_state(session_name: str, repo_root: Path, agent: str) -> CliSessionState:
    """Load session state or create defaults when missing/corrupt."""
    session_path = cli_session_state_path(session_name)
    if session_path.exists():
        try:
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return CliSessionState.from_dict(
                    payload,
                    session_name=session_name,
                    repo_root=repo_root,
                    agent=agent,
                )
        except json.JSONDecodeError:
            pass

    transport_session_id = build_transport_session_id(repo_root, session_name, agent)
    return CliSessionState(
        session_name=session_name,
        repo_root=str(repo_root.resolve()),
        agent=agent,
        transport_session_id=transport_session_id,
        context={
            "repo_root": str(repo_root.resolve()),
            "transport_session_id": transport_session_id,
        },
    )


def save_session_state(state: CliSessionState) -> Path:
    """Persist session state to the repo-local `.scribe/cli/` runtime namespace."""
    session_path = cli_session_state_path(state.session_name)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = _utc_now_iso()
    session_path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return session_path
