"""Regression tests: session repo-root poisoning / provenance laundering.

Incident (2026-07-16, BUG: set_project succeeds, reads fail): after a
successful ``set_project`` for a project in repo A, every subsequent
``read_recent``/``query_entries`` failed with "Explicit project ... was not
found" and ``append_entry`` fell back to sentinel, while ``list_projects``
still saw the project. Mechanism, in dispatch order:

1. A pre-binding unbound-safe diagnostic call (``list_projects`` /
   ``scribe_doctor``) resolved no repo root and fell back to the server's own
   install root (``settings.project_root``) with provenance "anonymous"; the
   dispatch-level session upsert persisted that root into ``scribe_sessions``.
2. Every later call adopted the stored root as provenance "verified"
   (provenance laundering), overwriting even ``set_project``'s explicit root.
3. All DB project lookups are scoped by the execution root via a hashed
   ``project_key`` with no name fallback, so the wrong root turned an
   existing project into "not found".
4. ``set_project`` never persisted its verified root into ``scribe_sessions``,
   so re-running it could not heal the wedged session; only an MCP reconnect
   (new transport identity, fresh row) recovered.

Contracts under test:
A. A pre-binding unbound-safe tool call must NOT persist the diagnostic
   server root as the session's stored repo root.
B. A stored session root must not override ``set_project``'s explicit root
   at dispatch, and the binding sequence persists the verified root
   (healing a poisoned row).
C. The session-binding read path resolves the bound project even when the
   execution root disagrees with the project's registered repo root.
D. Explicit project resolution falls back to unique-name lookup when the
   scoped lookup misses; ambiguous names still fail closed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
import uuid

import pytest

from scribe_mcp.shared.execution_context import (
    ExecutionContext,
    RouterContextManager,
    get_current_execution_context,
)
from scribe_mcp.shared.logging_utils import (
    ProjectResolutionError,
    resolve_logging_context,
)
from scribe_mcp.shared.tool_runtime import execute_tool_call
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.base import ConflictError
from scribe_mcp.tools.agent_project_utils import resolve_authoritative_write_scope


class _InMemoryBackend:
    """Minimal backend mirroring the Postgres session/project semantics.

    - scribe_sessions: PK session_id, UNIQUE transport_session_id;
      repo_root updates COALESCE (a null incoming root keeps the stored one).
    - session_projects: keyed by session_id, requires a live session row.
    - scribe_projects: stored as a list so two repos may hold the same
      project name; scoped fetch matches (name, repo_root) exactly, unscoped
      fetch resolves only a UNIQUE name (ambiguity fails closed) — the same
      contract as the Postgres ``_fetch_project_row``.
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.transport_index: Dict[str, str] = {}
        self.session_projects: Dict[str, Optional[str]] = {}
        self.projects: List[SimpleNamespace] = []
        self.agent_sessions: Dict[str, str] = {}

    async def setup(self) -> None:
        return None

    async def upsert_session(
        self,
        *,
        session_id: str,
        transport_session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        repo_root: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> None:
        if transport_session_id:
            bound = self.transport_index.get(transport_session_id)
            if bound and bound != session_id:
                raise ConflictError(
                    "transport_session_id collision detected; refusing ambiguous session binding"
                )
        row = self.sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "transport_session_id": None,
                "agent_id": None,
                "repo_root": None,
                "mode": "sentinel",
            },
        )
        if transport_session_id:
            row["transport_session_id"] = transport_session_id
            self.transport_index[transport_session_id] = session_id
        if agent_id:
            row["agent_id"] = agent_id
        if repo_root:
            row["repo_root"] = repo_root
        if mode in ("sentinel", "project"):
            row["mode"] = mode

    async def get_session_by_transport(self, transport_session_id: str) -> Optional[Dict[str, Any]]:
        session_id = self.transport_index.get(transport_session_id)
        if not session_id:
            return None
        return dict(self.sessions[session_id])

    async def set_session_project(self, session_id: str, project_name: Optional[str]) -> None:
        if session_id not in self.sessions:
            raise ConflictError(f"Cannot bind project for unknown session_id={session_id!r}")
        self.session_projects[session_id] = project_name

    async def get_session_project(self, session_id: str) -> Optional[str]:
        return self.session_projects.get(session_id)

    async def get_session_mode(self, session_id: str) -> Optional[str]:
        row = self.sessions.get(session_id)
        return row["mode"] if row else None

    async def set_session_mode(self, session_id: str, mode: str) -> None:
        row = self.sessions.get(session_id)
        if row and mode in ("sentinel", "project"):
            row["mode"] = mode

    async def upsert_project(
        self,
        *,
        name: str,
        repo_root: str,
        progress_log_path: str,
        docs_json: Optional[str] = None,
    ) -> SimpleNamespace:
        resolved_root = str(Path(repo_root).resolve())
        for record in self.projects:
            if record.name == name and str(Path(str(record.repo_root)).resolve()) == resolved_root:
                record.progress_log_path = progress_log_path
                record.docs_json = docs_json
                return record
        record = SimpleNamespace(
            name=name,
            repo_root=repo_root,
            progress_log_path=progress_log_path,
            docs_json=docs_json,
            repo_id=None,
            project_key=f"{resolved_root}::{name}",
        )
        self.projects.append(record)
        return record

    async def fetch_project(
        self,
        name: str,
        *,
        repo_root: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> Optional[SimpleNamespace]:
        if repo_root:
            resolved_root = str(Path(repo_root).resolve())
            for record in self.projects:
                if record.name == name and str(Path(str(record.repo_root)).resolve()) == resolved_root:
                    return record
            return None
        matches = [record for record in self.projects if record.name == name]
        if len(matches) != 1:
            return None
        return matches[0]

    async def list_projects(self) -> List[SimpleNamespace]:
        return list(self.projects)

    async def list_projects_by_repo(self, repo_root: str) -> List[SimpleNamespace]:
        resolved = str(Path(repo_root).resolve())
        return [
            record
            for record in self.projects
            if str(Path(str(record.repo_root)).resolve()) == resolved
        ]

    async def get_or_create_agent_session(
        self,
        *,
        identity_key: str,
        agent_name: str,
        agent_key: str,
        repo_root: str,
        mode: str,
        scope_key: str,
        ttl_hours: int = 24,
    ) -> str:
        existing = self.agent_sessions.get(identity_key)
        if existing:
            return existing
        session_id = str(uuid.uuid4())
        self.agent_sessions[identity_key] = session_id
        return session_id


class _Harness:
    """Drives the real dispatch layer for one simulated MCP connection.

    ``server_root`` plays the scribe-mcp install root (``settings.project_root``,
    e.g. SCRIBE_ROOT) and is deliberately DIFFERENT from ``project_repo`` —
    the repo the bound project actually lives in — matching the incident
    (server rooted at scribe_mcp, project rooted at council_mcp).
    """

    def __init__(self, server_root: Path, project_repo: Path, connection_id: str) -> None:
        self.server_root = server_root
        self.project_repo = project_repo
        self.backend = _InMemoryBackend()
        self.router = RouterContextManager(storage_backend=self.backend)
        self.state_manager = StateManager(
            path=server_root / "state.db",
            storage_backend=self.backend,
        )
        headers = {"mcp-session-id": connection_id}
        request = SimpleNamespace(headers=headers)
        self.app = SimpleNamespace(
            request_context=SimpleNamespace(request=request, meta=None)
        )
        self.settings = SimpleNamespace(project_root=server_root)
        self.captured_contexts: Dict[str, ExecutionContext] = {}
        self.registry = {
            "set_project": self._set_project_stub(),
            "append_entry": self._probe_stub("append_entry"),
            "list_projects": self._probe_stub("list_projects"),
        }

    def _set_project_stub(self):
        async def set_project(agent: str, name: str, root: Optional[str] = None, **_kwargs: Any) -> Dict[str, Any]:
            context = get_current_execution_context()
            assert context is not None
            self.captured_contexts[f"{agent}:set_project:{name}"] = context
            scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)
            session_key = scope["authoritative_session_id"]
            assert session_key, "set_project requires an authoritative session key"
            record = await self.backend.upsert_project(
                name=name,
                repo_root=str(root or self.project_repo),
                progress_log_path=str(Path(str(root or self.project_repo)) / "PROGRESS_LOG.md"),
            )
            await self.state_manager.set_current_project(
                name,
                {
                    "name": name,
                    "root": record.repo_root,
                    "progress_log": record.progress_log_path,
                },
                agent_id=agent,
                session_id=session_key,
                resolved_scope=scope["resolved_scope"],
                mirror_global=False,
                skip_upsert=True,
            )
            await self.state_manager.set_session_mode(session_key, "project")
            await self.router.cache_project_binding(session_key, name)
            # Mirrors the real set_project binding sequence: the verified root
            # is persisted so the session row heals even if it was poisoned.
            await self.backend.upsert_session(
                session_id=session_key,
                repo_root=record.repo_root,
                mode="project",
            )
            return {"ok": True, "project": name, "session_key": session_key}

        return set_project

    def _probe_stub(self, tool_name: str):
        async def probe(agent: str, **_kwargs: Any) -> Dict[str, Any]:
            context = get_current_execution_context()
            assert context is not None
            self.captured_contexts[f"{agent}:{tool_name}"] = context
            return {"ok": True}

        return probe

    async def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        return await execute_tool_call(
            name=name,
            arguments=arguments,
            kwargs={},
            registry=self.registry,
            app=self.app,
            storage_backend=self.backend,
            settings=self.settings,
            state_manager=self.state_manager,
            router_context_manager=self.router,
            sentinel_only=set(),
            sentinel_allowed={"set_project", "list_projects"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

    def session_row_for_actor(self, agent: str, connection_id: str) -> Dict[str, Any]:
        transport = f"{connection_id}::actor={agent}"
        session_id = self.backend.transport_index.get(transport)
        assert session_id, f"no session row for transport {transport!r}"
        return self.backend.sessions[session_id]


@pytest.fixture()
def server_root(tmp_path: Path) -> Path:
    root = (tmp_path / "scribe-install").resolve()
    root.mkdir()
    (root / ".git").mkdir()
    return root


@pytest.fixture()
def project_repo(tmp_path: Path) -> Path:
    root = (tmp_path / "workspace-repo").resolve()
    root.mkdir()
    (root / ".git").mkdir()
    return root


# ---------------------------------------------------------------------------
# Contract A: no poisoning — diagnostic root is never persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prebinding_diagnostic_call_does_not_persist_server_root(
    server_root: Path, project_repo: Path
) -> None:
    harness = _Harness(server_root, project_repo, connection_id="conn-poison-a")

    await harness.call("list_projects", {"agent": "atlas"})

    row = harness.session_row_for_actor("atlas", "conn-poison-a")
    assert row["repo_root"] is None, (
        "A pre-binding unbound-safe call resolves the server's own install "
        "root as a request-local diagnostic fallback (provenance anonymous); "
        "persisting it into scribe_sessions lets later calls adopt it as the "
        "session's VERIFIED repo scope and wedges every project lookup."
    )


# ---------------------------------------------------------------------------
# Contract B: stored root never beats set_project; binding heals the row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_project_explicit_root_beats_poisoned_stored_root(
    server_root: Path, project_repo: Path
) -> None:
    harness = _Harness(server_root, project_repo, connection_id="conn-poison-b")

    await harness.call("list_projects", {"agent": "atlas"})
    row = harness.session_row_for_actor("atlas", "conn-poison-b")
    # Simulate a row poisoned before the fix (legacy data): stored root points
    # at the server install root, not the repo the project lives in.
    row["repo_root"] = str(server_root)

    await harness.call(
        "set_project",
        {"agent": "atlas", "name": "proj_gov", "root": str(project_repo)},
    )

    ctx = harness.captured_contexts["atlas:set_project:proj_gov"]
    assert str(ctx.repo_root) == str(project_repo), (
        "The stored session root must not override set_project's explicit "
        "root — that clobber is what kept the session wedged against the "
        "wrong repo no matter how many times set_project was re-run."
    )
    assert row["repo_root"] == str(project_repo), (
        "The binding sequence must persist the verified root so a poisoned "
        "session row heals on the next set_project."
    )


@pytest.mark.asyncio
async def test_read_after_set_project_adopts_binding_root_not_server_root(
    server_root: Path, project_repo: Path
) -> None:
    harness = _Harness(server_root, project_repo, connection_id="conn-poison-c")

    await harness.call("list_projects", {"agent": "atlas"})
    harness.session_row_for_actor("atlas", "conn-poison-c")["repo_root"] = str(server_root)

    await harness.call(
        "set_project",
        {"agent": "atlas", "name": "proj_gov", "root": str(project_repo)},
    )
    await harness.call("append_entry", {"agent": "atlas"})

    ctx = harness.captured_contexts["atlas:append_entry"]
    assert str(ctx.repo_root) == str(project_repo), (
        "Immediately after set_project, a read/write call on the same "
        "session must execute against the binding's repo root."
    )


# ---------------------------------------------------------------------------
# Contract C: session-binding resolution survives a wrong execution root
# ---------------------------------------------------------------------------


def _make_exec_context(session_key: str, repo_root: Path) -> SimpleNamespace:
    resolved_scope = SimpleNamespace(
        repo_root=str(repo_root),
        stable_session_id=session_key,
        agent_session_id=None,
        transport_session_id=None,
        authoritative_session_key=session_key,
        provenance=SimpleNamespace(repo_root="verified"),
        resolution_source="runtime_context",
    )
    return SimpleNamespace(
        mode="project",
        session_id=session_key,
        stable_session_id=session_key,
        resolved_scope=resolved_scope,
        authoritative_session_key=session_key,
    )


async def _bound_server_module(
    execution_root: Path,
    project_root: Path,
    session_key: str,
    bound_project: str,
) -> SimpleNamespace:
    backend = _InMemoryBackend()
    await backend.upsert_project(
        name=bound_project,
        repo_root=str(project_root),
        progress_log_path=str(project_root / "PROGRESS_LOG.md"),
    )
    await backend.upsert_session(
        session_id=session_key,
        transport_session_id=f"transport-{session_key}",
        mode="project",
    )
    await backend.set_session_project(session_key, bound_project)

    state_manager = StateManager(
        path=execution_root / "state.db",
        storage_backend=backend,
    )
    exec_context = _make_exec_context(session_key, execution_root)
    return SimpleNamespace(
        storage_backend=backend,
        state_manager=state_manager,
        get_execution_context=lambda: exec_context,
    )


@pytest.mark.asyncio
async def test_session_bound_project_resolves_despite_mismatched_execution_root(
    server_root: Path, project_repo: Path
) -> None:
    server_module = await _bound_server_module(
        execution_root=server_root,
        project_root=project_repo,
        session_key="sess-wedged-1",
        bound_project="proj_gov",
    )

    context = await resolve_logging_context(
        tool_name="append_entry",
        server_module=server_module,
        agent_id=None,
        state_snapshot={},
    )

    assert context.project is not None
    assert context.project["name"] == "proj_gov", (
        "An explicitly bound session project must resolve even when the "
        "request's execution root disagrees with the project's registered "
        "repo root — the repo-scoped key miss must fall back to the unique "
        "name, not report the project missing."
    )


@pytest.mark.asyncio
async def test_explicit_project_resolves_by_unique_name_when_root_mismatches(
    server_root: Path, project_repo: Path
) -> None:
    server_module = await _bound_server_module(
        execution_root=server_root,
        project_root=project_repo,
        session_key="sess-wedged-2",
        bound_project="proj_gov",
    )

    context = await resolve_logging_context(
        tool_name="read_recent",
        server_module=server_module,
        agent_id=None,
        explicit_project="proj_gov",
        state_snapshot={},
    )

    assert context.project is not None
    assert context.project["name"] == "proj_gov"
    assert context.resolution_source == "explicit_project", (
        "An explicit project= naming the session's own bound project must "
        "resolve via the DB record, not fail with 'was not found' because "
        "the execution root points at the server install repo."
    )


# ---------------------------------------------------------------------------
# Contract D: ambiguous names still fail closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ambiguous_project_name_still_fails_closed(
    server_root: Path, project_repo: Path, tmp_path: Path
) -> None:
    other_repo = (tmp_path / "other-repo").resolve()
    other_repo.mkdir()

    server_module = await _bound_server_module(
        execution_root=server_root,
        project_root=project_repo,
        session_key="sess-ambiguous-1",
        bound_project="proj_dup",
    )
    # A second project with the SAME name in a different repo makes the
    # unscoped fallback ambiguous — it must refuse to guess.
    await server_module.storage_backend.upsert_project(
        name="proj_dup",
        repo_root=str(other_repo),
        progress_log_path=str(other_repo / "PROGRESS_LOG.md"),
    )

    with pytest.raises(ProjectResolutionError):
        await resolve_logging_context(
            tool_name="read_recent",
            server_module=server_module,
            agent_id=None,
            explicit_project="proj_dup",
            state_snapshot={},
        )
