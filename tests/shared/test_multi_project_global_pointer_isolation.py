"""Regression tests: multi-project (same repo) global-pointer isolation.

Surviving bug class after the actor-scoped *transport session* fix (v2.11.0,
commit 1c60a42). That fix stopped two actors on one MCP connection from
stealing each other's *session* binding. This test covers the remaining
cross-PROJECT conflict:

The "current/active project" pointer used by no-session readers (status/HUD
surfaces such as ``get_project`` compat recovery, ``scribe_doctor``,
``health_check``) resolves from a SINGLE shared row keyed by the constant
``_GLOBAL_AGENT_ID = "Scribe"`` in ``agent_projects``. Every ``set_project``
mirrors its project into that one row (``_set_global_project`` from
``persist()`` and ``set_current_project(mirror_global=True)``). With several
lanes in one repo, the pointer is LAST-WRITER-WINS: lane A's HUD probe reads
lane B's project moments after B ran ``set_project``.

Contract under test:
1. The mirrored "current project" pointer is scoped per calling actor, not a
   single shared row. Two actors binding two projects in one repo each get
   their own pointer row.
2. A no-session status read that carries actor A's identity (recovered from
   the actor-scoped transport id ``<conn>::actor=<agent>``) resolves A's
   project, never the last writer's.
3. Single-actor flows (no distinct actor identity) keep resolving their one
   project through the legacy shared pointer — backward compatible.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from scribe_mcp.state.manager import StateManager


class _GlobalPointerBackend:
    """In-memory backend mirroring the agent_projects / session schema.

    - agent_projects: PK agent_id (this is the row the "Scribe" global uses)
    - session_projects: keyed by session_id
    - scribe_projects: unique by name, scoped fetch by repo_root
    """

    def __init__(self) -> None:
        self.projects: Dict[str, SimpleNamespace] = {}
        self.session_projects: Dict[str, Optional[str]] = {}
        self.agent_projects: Dict[str, Dict[str, Any]] = {}
        self.agent_recent: Dict[str, str] = {}

    async def setup(self) -> None:
        return None

    # --- projects ---------------------------------------------------------
    async def upsert_project(
        self,
        *,
        name: str,
        repo_root: str,
        progress_log_path: str,
        docs_json: Optional[str] = None,
    ) -> SimpleNamespace:
        record = SimpleNamespace(
            name=name,
            repo_root=repo_root,
            progress_log_path=progress_log_path,
            docs_json=docs_json,
            repo_id=None,
            project_key=name,
        )
        self.projects[name] = record
        return record

    async def fetch_project(
        self,
        name: str,
        *,
        repo_root: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> Optional[SimpleNamespace]:
        return self.projects.get(name)

    async def list_projects(self) -> List[SimpleNamespace]:
        return list(self.projects.values())

    async def list_projects_by_repo(self, repo_root: str) -> List[SimpleNamespace]:
        resolved = str(Path(repo_root).resolve())
        return [
            record
            for record in self.projects.values()
            if str(Path(str(record.repo_root)).resolve()) == resolved
        ]

    # --- session bindings -------------------------------------------------
    async def set_session_project(self, session_id: str, project_name: Optional[str]) -> None:
        self.session_projects[session_id] = project_name

    async def get_session_project(self, session_id: str) -> Optional[str]:
        return self.session_projects.get(session_id)

    async def get_session_mode(self, session_id: str) -> Optional[str]:
        return "project"

    # --- agent (global/per-actor) pointer --------------------------------
    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self.agent_projects.get(agent_id)

    async def set_agent_project(
        self,
        agent_id: str,
        project_name: Optional[str],
        expected_version: Optional[int],
        updated_by: str,
        session_id: str,
    ) -> Dict[str, Any]:
        row = {
            "agent_id": agent_id,
            "project_name": project_name,
            "version": (self.agent_projects.get(agent_id, {}).get("version", 0) or 0) + 1,
            "updated_at": "now",
            "updated_by": updated_by,
            "session_id": session_id,
        }
        self.agent_projects[agent_id] = row
        return row

    async def upsert_agent_recent_project(self, agent_id: str, project_name: str) -> None:
        self.agent_recent[agent_id] = project_name


def _fake_context(*, transport_session_id: Optional[str], repo_root: Path) -> SimpleNamespace:
    """A runtime context with NO stable/session id but an actor-scoped
    transport id, matching a no-session status probe."""
    return SimpleNamespace(
        repo_root=str(repo_root),
        transport_session_id=transport_session_id,
        stable_session_id=None,
        session_id=None,
        agent_identity=SimpleNamespace(display_name=None),
    )


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = (tmp_path / "workspace").resolve()
    root.mkdir()
    (root / ".git").mkdir()
    return root


async def _bind(state_manager: StateManager, *, name: str, actor: str, session: str, root: Path) -> None:
    await state_manager.set_current_project(
        name,
        {"name": name, "root": str(root), "progress_log": str(root / "PROGRESS_LOG.md")},
        agent_id=actor,
        session_id=session,
        mirror_global=True,
    )


def _install_context(monkeypatch: pytest.MonkeyPatch, context: Optional[SimpleNamespace]) -> None:
    """Point the shared server module's context lookups at ``context``."""
    from scribe_mcp import server as server_module

    fake_router = SimpleNamespace(
        get_current=lambda: context,
        _process_instance_id="test-proc",
    )
    monkeypatch.setattr(server_module, "router_context_manager", fake_router, raising=False)
    monkeypatch.setattr(server_module, "get_execution_context", lambda: context, raising=False)


@pytest.mark.asyncio
async def test_two_actors_get_isolated_global_pointer_rows(repo_root: Path) -> None:
    """The mirrored current-project pointer must be per-actor, not one shared
    'Scribe' row that the last set_project clobbers."""
    backend = _GlobalPointerBackend()
    state_manager = StateManager(path=repo_root / "state.db", storage_backend=backend)

    await _bind(state_manager, name="proj_a", actor="actor-a", session="sess-a", root=repo_root)
    await _bind(state_manager, name="proj_b", actor="actor-b", session="sess-b", root=repo_root)

    row_a = await backend.get_agent_project("actor-a")
    row_b = await backend.get_agent_project("actor-b")

    assert row_a is not None and row_a["project_name"] == "proj_a", (
        "Actor A's global pointer row was not written per-actor; a shared "
        "'Scribe' row means the last set_project overwrote everyone."
    )
    assert row_b is not None and row_b["project_name"] == "proj_b"


@pytest.mark.asyncio
async def test_no_session_read_resolves_calling_actor_not_last_writer(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A no-session status read carrying actor A's identity must resolve A's
    project even after actor B was the last to run set_project."""
    backend = _GlobalPointerBackend()
    state_manager = StateManager(path=repo_root / "state.db", storage_backend=backend)

    await _bind(state_manager, name="proj_a", actor="actor-a", session="sess-a", root=repo_root)
    await _bind(state_manager, name="proj_b", actor="actor-b", session="sess-b", root=repo_root)

    # Actor A's HUD probe: actor-scoped transport id, no session in the
    # resolution path (the leaking surface).
    _install_context(
        monkeypatch,
        _fake_context(transport_session_id="conn-1::actor=actor-a", repo_root=repo_root),
    )
    state_a = await state_manager.load()
    assert state_a.current_project == "proj_a", (
        f"Actor A's status read resolved {state_a.current_project!r} — the "
        "last-writer global pointer leaked actor B's project into A's HUD."
    )

    # Actor B's probe resolves proj_b.
    _install_context(
        monkeypatch,
        _fake_context(transport_session_id="conn-1::actor=actor-b", repo_root=repo_root),
    )
    state_b = await state_manager.load()
    assert state_b.current_project == "proj_b"


@pytest.mark.asyncio
async def test_single_actor_flow_still_resolves_current_project(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backward compat: one actor, no distinguishable actor identity on the
    read path, still resolves its single project through the legacy pointer."""
    backend = _GlobalPointerBackend()
    state_manager = StateManager(path=repo_root / "state.db", storage_backend=backend)

    await _bind(state_manager, name="solo_project", actor="solo", session="sess-solo", root=repo_root)

    # No actor-scoped transport id -> legacy single-actor fallback.
    _install_context(
        monkeypatch,
        _fake_context(transport_session_id=None, repo_root=repo_root),
    )
    state = await state_manager.load()
    assert state.current_project == "solo_project", (
        "Single-actor flow must keep resolving its one project via the legacy "
        "global pointer when no distinct actor identity is present."
    )
