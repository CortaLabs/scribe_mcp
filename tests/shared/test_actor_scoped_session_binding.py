"""Regression tests: actor-scoped session->project binding isolation.

Bug: multiple actors multiplexing one MCP connection (one transport session,
e.g. a pooled client) shared a single scribe_sessions row because the session
key was derived from the connection alone. The last set_project on the
connection silently rebound EVERY actor, and explicit `project=` overrides
were rejected because the authorized set came from the stolen binding.

Contract under test (backend-agnostic; enforced by the shared runtime layer):
1. Two actors on the same connection get distinct execution sessions.
2. An actor's binding can never be overwritten by another actor's set_project.
3. Single-actor flows keep one stable session across calls (backward compat).
4. Explicit `project=` override resolving inside the verified execution repo
   root is honored with set_project-equivalent authority.
5. Explicit override outside the verified repo root is still rejected.

The in-memory backend mirrors the Postgres constraints that shape the bug:
scribe_sessions has UNIQUE(transport_session_id); session_projects is keyed
by session_id and requires a live scribe_sessions row.
"""

from __future__ import annotations

import asyncio
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
    """Minimal storage backend mirroring the session-binding schema semantics.

    Matches the Postgres/SQLite contract relied on by the shared runtime:
    - scribe_sessions: PK session_id, UNIQUE transport_session_id
    - session_projects: PK session_id, requires a live scribe_sessions row
    - scribe_projects: unique by name, scoped fetch by repo_root
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.transport_index: Dict[str, str] = {}
        self.session_projects: Dict[str, Optional[str]] = {}
        self.projects: Dict[str, SimpleNamespace] = {}
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
        record = self.projects.get(name)
        if record is None:
            return None
        if repo_root and str(Path(str(record.repo_root)).resolve()) != str(Path(repo_root).resolve()):
            return None
        return record

    async def list_projects(self) -> List[SimpleNamespace]:
        return list(self.projects.values())

    async def list_projects_by_repo(self, repo_root: str) -> List[SimpleNamespace]:
        resolved = str(Path(repo_root).resolve())
        return [
            record
            for record in self.projects.values()
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
    """Drives the real dispatch layer for one simulated MCP connection."""

    def __init__(self, repo_root: Path, connection_id: str) -> None:
        self.repo_root = repo_root
        self.backend = _InMemoryBackend()
        self.router = RouterContextManager(storage_backend=self.backend)
        self.state_manager = StateManager(
            path=repo_root / "state.db",
            storage_backend=self.backend,
        )
        headers = {"mcp-session-id": connection_id}
        request = SimpleNamespace(headers=headers)
        self.app = SimpleNamespace(
            request_context=SimpleNamespace(request=request, meta=None)
        )
        self.settings = SimpleNamespace(project_root=repo_root)
        self.captured_contexts: Dict[str, ExecutionContext] = {}
        self.registry = {
            "set_project": self._set_project_stub(),
            "append_entry": self._probe_stub("append_entry"),
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
                repo_root=str(root or self.repo_root),
                progress_log_path=str(Path(str(root or self.repo_root)) / "PROGRESS_LOG.md"),
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
            sentinel_allowed={"set_project"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

    def binding_key(self, context: ExecutionContext) -> str:
        key = context.stable_session_id or context.session_id
        assert key
        return str(key)


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = (tmp_path / "workspace").resolve()
    root.mkdir()
    (root / ".git").mkdir()
    return root


@pytest.mark.asyncio
async def test_two_actors_same_connection_get_distinct_sessions(repo_root: Path) -> None:
    harness = _Harness(repo_root, connection_id="conn-shared-1")

    await harness.call(
        "set_project",
        {"agent": "actor-a", "name": "proj_a", "root": str(repo_root)},
    )
    await harness.call(
        "set_project",
        {"agent": "actor-b", "name": "proj_b", "root": str(repo_root)},
    )

    ctx_a = harness.captured_contexts["actor-a:set_project:proj_a"]
    ctx_b = harness.captured_contexts["actor-b:set_project:proj_b"]

    assert harness.binding_key(ctx_a) != harness.binding_key(ctx_b), (
        "Two actors sharing one MCP connection must not share a session "
        "binding key — a shared key means the last set_project on the "
        "connection silently rebinds every actor."
    )


@pytest.mark.asyncio
async def test_set_project_by_second_actor_cannot_steal_first_actors_binding(
    repo_root: Path,
) -> None:
    harness = _Harness(repo_root, connection_id="conn-shared-2")

    await harness.call(
        "set_project",
        {"agent": "actor-a", "name": "proj_a", "root": str(repo_root)},
    )
    await harness.call(
        "set_project",
        {"agent": "actor-b", "name": "proj_b", "root": str(repo_root)},
    )

    # Actor A logs again after actor B rebound the connection.
    await harness.call("append_entry", {"agent": "actor-a", "message": "hello"})
    ctx_a_append = harness.captured_contexts["actor-a:append_entry"]

    bound_project = await harness.backend.get_session_project(
        harness.binding_key(ctx_a_append)
    )
    assert bound_project == "proj_a", (
        f"Actor A's writes resolved to {bound_project!r} after actor B ran "
        "set_project on the same connection — binding theft."
    )

    # And actor B keeps its own binding.
    await harness.call("append_entry", {"agent": "actor-b", "message": "hello"})
    ctx_b_append = harness.captured_contexts["actor-b:append_entry"]
    assert (
        await harness.backend.get_session_project(harness.binding_key(ctx_b_append))
        == "proj_b"
    )


@pytest.mark.asyncio
async def test_interleaved_writes_from_two_actors_stay_isolated(repo_root: Path) -> None:
    harness = _Harness(repo_root, connection_id="conn-shared-3")

    await harness.call(
        "set_project",
        {"agent": "actor-a", "name": "proj_a", "root": str(repo_root)},
    )
    await harness.call(
        "set_project",
        {"agent": "actor-b", "name": "proj_b", "root": str(repo_root)},
    )

    resolved: Dict[str, List[str]] = {"actor-a": [], "actor-b": []}
    for _round in range(3):
        for agent, expected in (("actor-a", "proj_a"), ("actor-b", "proj_b")):
            await harness.call("append_entry", {"agent": agent, "message": "tick"})
            context = harness.captured_contexts[f"{agent}:append_entry"]
            project = await harness.backend.get_session_project(
                harness.binding_key(context)
            )
            resolved[agent].append(str(project))

    assert resolved["actor-a"] == ["proj_a"] * 3
    assert resolved["actor-b"] == ["proj_b"] * 3


@pytest.mark.asyncio
async def test_single_actor_flow_keeps_one_stable_session(repo_root: Path) -> None:
    """Backward compat: one connection, one actor, one set_project, bare calls."""
    harness = _Harness(repo_root, connection_id="conn-single-1")

    await harness.call(
        "set_project",
        {"agent": "codex", "name": "solo_project", "root": str(repo_root)},
    )
    ctx_bind = harness.captured_contexts["codex:set_project:solo_project"]

    keys = []
    for _ in range(3):
        await harness.call("append_entry", {"agent": "codex", "message": "tick"})
        context = harness.captured_contexts["codex:append_entry"]
        keys.append(harness.binding_key(context))

    assert set(keys) == {harness.binding_key(ctx_bind)}, (
        "A single actor must keep one stable session key across calls"
    )
    assert (
        await harness.backend.get_session_project(harness.binding_key(ctx_bind))
        == "solo_project"
    )


# ---------------------------------------------------------------------------
# Explicit project override authority (resolve_logging_context)
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
    repo_root: Path,
    session_key: str,
    bound_project: str,
) -> SimpleNamespace:
    backend = _InMemoryBackend()
    await backend.upsert_project(
        name=bound_project,
        repo_root=str(repo_root),
        progress_log_path=str(repo_root / "PROGRESS_LOG.md"),
    )
    await backend.upsert_session(
        session_id=session_key,
        transport_session_id=f"transport-{session_key}",
        mode="project",
    )
    await backend.set_session_project(session_key, bound_project)

    state_manager = StateManager(
        path=repo_root / "state.db",
        storage_backend=backend,
    )
    exec_context = _make_exec_context(session_key, repo_root)
    return SimpleNamespace(
        storage_backend=backend,
        state_manager=state_manager,
        get_execution_context=lambda: exec_context,
    )


@pytest.mark.asyncio
async def test_explicit_project_override_in_verified_repo_root_is_honored(
    repo_root: Path,
) -> None:
    server_module = await _bound_server_module(repo_root, "sess-override-1", "proj_bound")
    await server_module.storage_backend.upsert_project(
        name="proj_target",
        repo_root=str(repo_root),
        progress_log_path=str(repo_root / "PROGRESS_LOG.md"),
    )

    context = await resolve_logging_context(
        tool_name="append_entry",
        server_module=server_module,
        agent_id="actor-a",
        explicit_project="proj_target",
        state_snapshot={},
    )

    assert context.project is not None
    assert context.project["name"] == "proj_target", (
        "An explicit project override that resolves inside the verified "
        "execution repo root must be honored, not rejected as a mismatch."
    )


@pytest.mark.asyncio
async def test_explicit_project_override_outside_verified_repo_root_is_rejected(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    other_repo = (tmp_path / "other-repo").resolve()
    other_repo.mkdir()

    server_module = await _bound_server_module(repo_root, "sess-override-2", "proj_bound")
    await server_module.storage_backend.upsert_project(
        name="proj_foreign",
        repo_root=str(other_repo),
        progress_log_path=str(other_repo / "PROGRESS_LOG.md"),
    )

    with pytest.raises(ProjectResolutionError):
        await resolve_logging_context(
            tool_name="append_entry",
            server_module=server_module,
            agent_id="actor-a",
            explicit_project="proj_foreign",
            state_snapshot={},
        )


@pytest.mark.asyncio
async def test_same_named_actors_in_different_projects_via_explicit_override(
    repo_root: Path,
) -> None:
    """Several agents with the SAME name (e.g. three Forges) in different
    projects of one repo. Identically-named actors are indistinguishable at
    the wire, so they share a binding — the honored per-call explicit
    `project=` override is what keeps every write landing in the intended
    project regardless of which set_project won the shared binding.
    """
    session_key = "sess-forge-shared"
    server_module = await _bound_server_module(repo_root, session_key, "proj_forge_1")
    for name in ("proj_forge_2", "proj_forge_3"):
        await server_module.storage_backend.upsert_project(
            name=name,
            repo_root=str(repo_root),
            progress_log_path=str(repo_root / "PROGRESS_LOG.md"),
        )

    resolved: List[str] = []
    for _round in range(2):
        for target in ("proj_forge_1", "proj_forge_2", "proj_forge_3"):
            context = await resolve_logging_context(
                tool_name="append_entry",
                server_module=server_module,
                agent_id="forge",
                explicit_project=target,
                state_snapshot={},
            )
            assert context.project is not None
            resolved.append(str(context.project["name"]))

    assert resolved == ["proj_forge_1", "proj_forge_2", "proj_forge_3"] * 2


@pytest.mark.asyncio
async def test_explicit_override_matching_bound_project_still_resolves(
    repo_root: Path,
) -> None:
    """Passing the already-bound project explicitly keeps working."""
    server_module = await _bound_server_module(repo_root, "sess-override-3", "proj_bound")

    context = await resolve_logging_context(
        tool_name="append_entry",
        server_module=server_module,
        agent_id="actor-a",
        explicit_project="proj_bound",
        state_snapshot={},
    )

    assert context.project is not None
    assert context.project["name"] == "proj_bound"
