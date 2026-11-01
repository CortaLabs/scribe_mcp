from __future__ import annotations

from pathlib import Path
import os
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from scribe_mcp.doc_management.actions.edit import handle_edit_action
from scribe_mcp.doc_management.runtime import register_document_path
from scribe_mcp.tools.agent_project_utils import resolve_authoritative_write_scope


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.storage
@pytest.mark.parametrize("docs_base", [".scribe/docs/dev_plans", "custom/plans"])
@pytest.mark.parametrize("target_name", ["receipt_source", "receipt_target"])
def test_real_sdk_receipt_rehome_apply_and_replay(
    tmp_path: Path, test_agent: str, docs_base: str, target_name: str,
) -> None:
    """Retained rehome uses the same real project metadata as SDK preview."""
    source = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("SCRIBE_") and key not in {"DATABASE_URL", "REPO_ROOT"}}
    env.update({
        "SCRIBE_RELEASE_PROFILE": "internal", "SCRIBE_DISABLE_DOTENV": "1",
        "SCRIBE_LOAD_REPO_DOTENV": "0", "SCRIBE_MODE": "standalone",
        "SCRIBE_STORAGE_BACKEND": "sqlite", "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_DB_PATH": str(runtime / "scribe.sqlite3"),
        "SCRIBE_STATE_PATH": str(runtime / "state.json"), "SCRIBE_ROOT": str(runtime),
        "SCRIBE_PROJECT_ROOT": str(repo), "SCRIBE_DEV_PLANS_BASE": docs_base,
        "PYTHONPATH": str(source / "src"), "PYTHONDONTWRITEBYTECODE": "1",
        "SBR_TEST_AGENT": test_agent, "SBR_TEST_SOURCE": str(source), "SBR_TEST_REPO": str(repo),
        "SBR_TEST_TARGET": target_name,
    })
    probe = r'''
import asyncio, importlib.metadata, json, os, sqlite3, sys
from pathlib import Path
from mcp import Client, StdioServerParameters
import scribe_mcp

assert importlib.metadata.version("mcp") == "2.3.0"
assert Path(scribe_mcp.__file__).resolve() == Path(os.environ["SBR_TEST_SOURCE"]) / "src/scribe_mcp/__init__.py"
repo = Path(os.environ["SBR_TEST_REPO"])
agent = os.environ["SBR_TEST_AGENT"]
target_name = os.environ["SBR_TEST_TARGET"]

async def call(client, name, arguments):
    result = await client.call_tool(name, {"agent": agent, **arguments})
    assert not result.is_error, (name, result)
    body = result.model_dump(mode="json", by_alias=True)["structuredContent"]
    assert isinstance(body, dict)
    return body

def aliases(name="receipt_source"):
    with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
        row = connection.execute("SELECT docs_json FROM scribe_projects WHERE name = ?", (name,)).fetchone()
        return json.loads(row[0])

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "scribe_mcp"],
                                   env=dict(os.environ), cwd=str(repo))
    async with asyncio.timeout(60):
        async with Client(params, mode="2026-07-28", cache=None) as client:
            await client.session.send_discover("2026-07-28")
            target_docs = None
            if target_name != "receipt_source":
                target_bound = await call(client, "set_project", {
                    "name": target_name, "root": str(repo), "format": "structured",
                })
                assert target_bound["ok"] is True
                target_docs = Path(target_bound["project"]["docs_dir"])
            bound = await call(client, "set_project", {
                "name": "receipt_source", "root": str(repo), "format": "structured",
            })
            assert bound["ok"] is True
            docs = Path(bound["project"]["docs_dir"])
            assert docs == repo / os.environ["SCRIBE_DEV_PLANS_BASE"] / "receipt_source"
            target_docs = target_docs or docs
            source = docs / "ARCHITECTURE_GUIDE.md"
            target = target_docs / "archive/ARCHITECTURE_GUIDE.md"
            protected_target = target_docs / "ARCHITECTURE_GUIDE.md"
            protected_bytes = protected_target.read_bytes()
            before = source.read_bytes()
            before_aliases = aliases()
            before_target_aliases = aliases(target_name)
            preview = await call(client, "manage_docs", {
                "action": "rehome_doc", "doc": "architecture", "dry_run": True,
                "metadata": {"target_project": target_name,
                             "target_relative_path": "archive/ARCHITECTURE_GUIDE.md"},
            })
            assert preview["ok"] is True
            receipt = preview["apply"]["receipt"]
            assert source.read_bytes() == before and not target.exists()
            assert aliases() == before_aliases
            assert aliases(target_name) == before_target_aliases
            applied = await call(client, "manage_docs", {
                "action": "apply_preview", "metadata": {"receipt": receipt},
            })
            assert applied.get("code") == "APPLY_RECEIPT_APPLIED", applied
            assert not source.exists() and target.read_bytes() == before
            after_aliases = aliases()
            after_target_aliases = aliases(target_name)
            assert after_target_aliases["architecture"] == str(target)
            assert str(source) not in after_aliases.values()
            if target_name != "receipt_source":
                assert "architecture" not in after_aliases
                assert protected_target.read_bytes() == protected_bytes
            replayed = await call(client, "manage_docs", {
                "action": "apply_preview", "metadata": {"receipt": receipt},
            })
            assert replayed.get("code") == "APPLY_RECEIPT_REPLAYED", replayed
            assert not source.exists() and target.read_bytes() == before
            assert aliases() == after_aliases
            assert aliases(target_name) == after_target_aliases
            denied = await call(client, "manage_docs", {
                "action": "apply_preview", "project": "receipt_source",
                "metadata": {"receipt": receipt},
            })
            assert denied.get("code") == "APPLY_RECEIPT_INVALID", denied
            assert not source.exists() and target.read_bytes() == before
            assert aliases() == after_aliases
            assert aliases(target_name) == after_target_aliases
            print(json.dumps({"sdk": importlib.metadata.version("mcp"),
                "protocol": "2026-07-28", "docs_base": os.environ["SCRIBE_DEV_PLANS_BASE"],
                "target_project": target_name,
                "apply": applied["code"], "replay": replayed["code"],
                "caller_intent": denied["code"], "aliases_stable": True}), flush=True)
asyncio.run(main())
'''
    result = subprocess.run([sys.executable, "-c", probe], cwd=source, env=env,
                            capture_output=True, text=True, timeout=80)
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_retired_sdk_handshake_rejected(source: Path, env: dict[str, str]) -> None:
    """Handshake-only control; populated-state no-effects needs its separate matrix."""
    probe = r'''
import anyio, json, os, sys
from pathlib import Path
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError
from mcp.types import UNSUPPORTED_PROTOCOL_VERSION

bootstrap = r"""
import os, runpy, sys
from pathlib import Path
import scribe_mcp
assert Path(scribe_mcp.__file__).resolve() == Path(os.environ['SBR_TEST_SOURCE']) / 'src/scribe_mcp/__init__.py'
print('RETIRED_WIRE_SOURCE=' + scribe_mcp.__file__, file=sys.stderr, flush=True)
runpy.run_module('scribe_mcp', run_name='__main__')
"""

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-c", bootstrap], env=dict(os.environ))
    client = Client(stdio_client(params), mode="legacy")
    entered = False
    rejected = []
    with anyio.fail_after(60):
        try:
            async with client:
                entered = True
                raise AssertionError("retired handshake was accepted before tool dispatch")
        except* MCPError as errors:
            def leaves(error):
                if isinstance(error, BaseExceptionGroup):
                    for child in error.exceptions:
                        yield from leaves(child)
                else:
                    yield error
            for error in leaves(errors):
                assert error.code == UNSUPPORTED_PROTOCOL_VERSION, error
                assert error.message == "Unsupported protocol version", error
                assert error.data["supported"] == ["2026-07-28"], error.data
                assert error.data["requested"] != "2026-07-28", error.data
                rejected.append(error.message)
    assert rejected == ["Unsupported protocol version"], rejected
    assert not entered, "legacy client reached the tool-capable context"
    print(json.dumps({"rejected": rejected, "client_entered": entered}), flush=True)
anyio.run(main)
'''
    result = subprocess.run(
        [os.environ.get("SBR_SDK_PYTHON", sys.executable), "-c", probe],
        cwd=source, env={**env, "SBR_TEST_SOURCE": str(source)},
        capture_output=True, text=True, timeout=80,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"client_entered": false' in result.stdout, result.stdout
    assert result.stderr.count("RETIRED_WIRE_SOURCE=" + str(source / "src/scribe_mcp/__init__.py")) == 1


@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_real_sdk_heartbeats_preserve_binding_rows(tmp_path: Path, test_agent: str, mode: str) -> None:
    """Cross both heartbeat clocks through genuine ingress and disposable storage."""
    source = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("SCRIBE_") and key not in {"DATABASE_URL", "REPO_ROOT"}}
    env.update({
        "SCRIBE_RELEASE_PROFILE": "internal", "SCRIBE_DISABLE_DOTENV": "1",
        "SCRIBE_LOAD_REPO_DOTENV": "0", "SCRIBE_MODE": "standalone",
        "SCRIBE_STORAGE_BACKEND": "sqlite", "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_DB_PATH": str(runtime / "scribe.sqlite3"),
        "SCRIBE_STATE_PATH": str(runtime / "state.json"), "SCRIBE_ROOT": str(runtime),
        "PYTHONPATH": str(source / "src"), "PYTHONDONTWRITEBYTECODE": "1",
        "SBR_TEST_AGENT": test_agent, "SBR_TEST_MODE": mode, "SBR_TEST_SOURCE": str(source),
        "SBR_TEST_REPO": str(repo), "SBR_TEST_CLOCK": str(runtime / "clock"),
        "SBR_TEST_CLOCK_SAMPLES": str(runtime / "clock_samples"),
    })
    if mode == "legacy":
        _assert_retired_sdk_handshake_rejected(source, env)
        return
    probe = r'''
import anyio, json, os, sqlite3, sys
from pathlib import Path
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client

clock = Path(os.environ["SBR_TEST_CLOCK"])
clock.write_text("0")
samples = Path(os.environ["SBR_TEST_CLOCK_SAMPLES"])
repo = Path(os.environ["SBR_TEST_REPO"])
bootstrap = r"""
import os, runpy, sys, time
from pathlib import Path
from types import SimpleNamespace
import scribe_mcp
from scribe_mcp.config.settings import Settings
from scribe_mcp.state import agent_identity
settings = Settings.load()
assert settings.storage_backend == 'sqlite'
assert os.environ['SCRIBE_MODE'] == 'standalone'
assert Path(scribe_mcp.__file__).resolve() == Path(os.environ['SBR_TEST_SOURCE']) / 'src/scribe_mcp/__init__.py'
assert 'SCRIBE_AGENT_ACTIVITY_PERSIST_INTERVAL_SECONDS' not in os.environ
assert 'SCRIBE_AGENT_ID_PERSIST_INTERVAL_SECONDS' not in os.environ
real_monotonic = time.monotonic
def scheduling_clock():
    identity = agent_identity.get_agent_identity()
    assert identity._activity_persist_interval_seconds == 60
    assert identity._persist_interval_seconds == 300
    offset = float(Path(os.environ['SBR_TEST_CLOCK']).read_text())
    with Path(os.environ['SBR_TEST_CLOCK_SAMPLES']).open('a') as output:
        output.write(str(offset) + '\n')
    return real_monotonic() + offset
agent_identity.time = SimpleNamespace(monotonic=scheduling_clock)
print('HEARTBEAT_SOURCE=' + scribe_mcp.__file__, file=sys.stderr, flush=True)
runpy.run_module('scribe_mcp', run_name='__main__')
"""

def rows():
    with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
        connection.row_factory = sqlite3.Row
        return {row["session_id"]: dict(row) for row in connection.execute(
            "SELECT * FROM session_projects ORDER BY session_id").fetchall()}

async def call(client, name, args):
    result = await client.call_tool(name, {"agent": os.environ["SBR_TEST_AGENT"], **args})
    data = json.loads("\n".join(getattr(item, "text", "") for item in result.content))
    assert not result.is_error and data.get("ok", True) is not False, (name, data)
    return data

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-c", bootstrap], env=dict(os.environ))
    with anyio.fail_after(60):
        async with Client(stdio_client(params), mode=os.environ["SBR_TEST_MODE"]) as owner:
            async with Client(stdio_client(params), mode=os.environ["SBR_TEST_MODE"]) as sibling:
                selected = await call(owner, "set_project", {"name": "heartbeat_owner", "root": str(repo), "format": "structured"})
                await call(owner, "read_recent", {"limit": 1, "format": "structured"})
                peer = await call(sibling, "set_project", {"name": "heartbeat_sibling", "root": str(repo), "format": "structured"})
                session = selected["project"]["session_id"]
                peer_session = peer["project"]["session_id"]
                assert session != peer_session
                before = rows()
                assert before[session]["binding_generation"] == 1
                await anyio.sleep(1.05)  # Make SQLite's second-resolution timestamp observable.
                for offset in (61, 301):
                    clock.write_text(str(offset))
                    marker = "heartbeat-" + str(offset)
                    await call(owner, "append_entry", {"message": marker, "format": "structured"})
                    recent = await call(owner, "read_recent", {"limit": 1, "format": "structured"})
                    assert marker in json.dumps(recent)
                    assert float(offset) in [float(value) for value in samples.read_text().splitlines()]
                    after = rows()
                    print(json.dumps({"mode": os.environ["SBR_TEST_MODE"], "offset": offset,
                        "before": before, "after": after, "recovery_binds": 0}), flush=True)
                    assert after == before, "SDK heartbeat refreshed caller or sibling binding"
                rebound = await call(owner, "set_project", {"name": "heartbeat_rebound", "root": str(repo), "format": "structured"})
                assert rebound["project"]["session_id"] == session
                after = rows()
                assert after[session]["binding_generation"] == 2
                assert after[session]["project_key"] != before[session]["project_key"]
                assert after[peer_session] == before[peer_session]
                await call(owner, "delete_project", {"name": "heartbeat_rebound",
                    "root": str(repo), "confirm": True})
                with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
                    assert connection.execute("SELECT COUNT(*) FROM scribe_projects WHERE name = ?",
                        ("heartbeat_rebound",)).fetchone()[0] == 0
                assert rows()[peer_session] == before[peer_session]
anyio.run(main)
'''
    result = subprocess.run([os.environ.get("SBR_SDK_PYTHON", sys.executable), "-c", probe],
                            cwd=source, env=env, capture_output=True, text=True, timeout=80)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr.count("HEARTBEAT_SOURCE=" + str(source / "src/scribe_mcp/__init__.py")) == 2


class _BackendStub:
    def __init__(self) -> None:
        self.update_calls = 0

    async def update_project_docs(self, project_name: str, docs_json: str, **_kwargs: Any) -> None:
        self.update_calls += 1


class _RegistryStub:
    def __init__(self) -> None:
        self.calls = 0

    def record_doc_update(self, **_: object) -> None:
        self.calls += 1


@pytest.mark.asyncio
async def test_register_document_path_requires_authority_without_selecting_default(tmp_path: Path) -> None:
    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")

    backend = _BackendStub()
    registry = _RegistryStub()

    captured: dict[str, object] = {}

    async def _set_current_project(
        name: str,
        project_data: dict,
        *,
        agent_id: str,
        session_id: str,
        resolved_scope: object,
        mirror_global: bool,
    ) -> None:
        captured["name"] = name
        captured["session_id"] = session_id
        captured["agent_id"] = agent_id
        captured["mirror_global"] = mirror_global

    server_module = SimpleNamespace(
        storage_backend=backend,
        state_manager=SimpleNamespace(set_current_project=_set_current_project),
    )
    async def _append_entry(**_: object) -> None:
        return None

    project = {"name": "demo", "docs": {}}
    execution_context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")

    warning = await register_document_path(
        project,
        "checklist",
        doc_path,
        server_module=server_module,
        project_registry=registry,
        append_entry=_append_entry,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        execution_context=execution_context,
        agent_id="BugHunterAgent",
    )

    assert warning is None
    assert captured == {}, "metadata registration must never call the selecting setter"
    assert backend.update_calls == 1
    assert registry.calls == 1


@pytest.mark.asyncio
async def test_register_document_path_fails_closed_without_authoritative_session(tmp_path: Path) -> None:
    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")

    backend = _BackendStub()
    registry = _RegistryStub()
    server_module = SimpleNamespace(
        storage_backend=backend,
        state_manager=SimpleNamespace(set_current_project=lambda **_: None),
    )
    async def _append_entry(**_: object) -> None:
        return None

    project = {"name": "demo", "docs": {}}
    execution_context = SimpleNamespace(session_id=None, stable_session_id=None)

    with pytest.raises(ValueError, match="authoritative session binding"):
        await register_document_path(
            project,
            "checklist",
            doc_path,
            server_module=server_module,
            project_registry=registry,
            append_entry=_append_entry,
            logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
            execution_context=execution_context,
            agent_id="BugHunterAgent",
        )

    assert backend.update_calls == 0
    assert registry.calls == 0


def test_resolve_authoritative_write_scope_uses_context_authoritative_session_key() -> None:
    context = SimpleNamespace(
        session_id="context-session",
        stable_session_id="stable-session",
        authoritative_session_key="authoritative-session",
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_key"] == "authoritative-session"
    assert scope["authoritative_session_id"] == "authoritative-session"


def test_resolve_authoritative_write_scope_rejects_transport_only_scope() -> None:
    context = SimpleNamespace(
        transport_session_id="transport-only-session",
        resolved_scope=SimpleNamespace(
            transport_session_id="transport-only-session",
            stable_session_id=None,
            agent_session_id=None,
            authoritative_session_key=None,
            resolution_source="runtime_context",
        ),
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_key"] is None
    assert scope["authoritative_session_id"] is None


@pytest.mark.asyncio
async def test_handle_edit_action_register_doc_does_not_select_default(tmp_path: Path) -> None:
    created_path = tmp_path / "NOTE.md"
    created_path.write_text("# Note\n", encoding="utf-8")

    captured: dict[str, object] = {}

    async def _set_current_project(
        name: str,
        project_data: dict,
        *,
        agent_id: str,
        session_id: str,
        resolved_scope: object,
        mirror_global: bool,
    ) -> None:
        captured["name"] = name
        captured["session_id"] = session_id
        captured["mirror_global"] = mirror_global

    async def _apply_doc_change(*_args, **_kwargs):
        return SimpleNamespace(
            success=True,
            path=created_path,
            diff_preview="",
            before_hash=None,
            after_hash="after",
            extra={},
            error_message=None,
            verification_passed=True,
            file_size_before=0,
            file_size_after=created_path.stat().st_size,
            content_written=created_path.read_text(encoding="utf-8"),
        )

    async def _get_or_create_storage_project(*_args, **_kwargs):
        return object()

    async def _append_entry(**_kwargs):
        return None

    async def _index_doc_for_vector(**_kwargs):
        return None

    def _helper_error_response(message: str, extra: dict | None = None):
        payload = {"ok": False, "error": message}
        if extra:
            payload["extra"] = extra
        return payload

    helper = SimpleNamespace(
        apply_context_payload=lambda response, _context: response,
        error_response=_helper_error_response,
    )
    async def _record_doc_change(*_args, **_kwargs):
        return None

    async def _update_project_docs(*_args, **_kwargs):
        return None

    backend = SimpleNamespace(
        record_doc_change=_record_doc_change,
        update_project_docs=_update_project_docs,
    )
    server_module = SimpleNamespace(
        state_manager=SimpleNamespace(set_current_project=_set_current_project),
        storage_backend=backend,
    )
    context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")
    project = {"name": "demo", "docs": {}}

    result = await handle_edit_action(
        action="create_doc",
        project=project,
        doc_name="note_doc",
        doc_category="",
        section=None,
        content="# Note\n",
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"doc_name": "note_doc", "register_doc": True},
        dry_run=False,
        backend=backend,
        agent_id="BugHunterAgent",
        helper=helper,
        context=context,
        execution_context=context,
        deprecation_warning=None,
        apply_doc_change=_apply_doc_change,
        get_or_create_storage_project=_get_or_create_storage_project,
        append_entry=_append_entry,
        normalize_metadata_with_healing=lambda metadata: (dict(metadata or {}), False, []),
        index_doc_for_vector=_index_doc_for_vector,
        vector_indexing_enabled=lambda _repo_root: False,
        get_index_updater_for_path=lambda *_args, **_kwargs: None,
        project_registry=SimpleNamespace(record_doc_update=lambda **_kwargs: None),
        server_module=server_module,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert result is not None
    assert result["ok"] is True
    warnings = result.get("warnings") or []
    assert all("Registry update failed" not in warning for warning in warnings)
    assert captured == {}, "document registration must never select a caller default"


def test_resolve_authoritative_write_scope_prefers_context_session_id_over_stable() -> None:
    """Contract test (BUG-2026-06-11-0004): without a resolved_scope, the
    request's own session_id outranks a bare carried-over stable_session_id.
    Originally pinned in 08d4d22; regressed by e320b3d; restored 2026-06-11."""
    context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_id"] == "authoritative-session"


def test_resolve_authoritative_write_scope_verified_scope_still_wins() -> None:
    """Server-derived resolved_scope keys keep absolute priority — the
    trust-order fix only affects degraded contexts without a resolved scope."""
    resolved = SimpleNamespace(
        authoritative_session_key="scope-derived-key",
        stable_session_id="scope-stable",
        agent_session_id=None,
        resolution_source="runtime_context",
    )
    context = SimpleNamespace(
        resolved_scope=resolved,
        session_id="request-session",
        stable_session_id="raw-stable",
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_id"] == "scope-derived-key"


@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_real_sdk_document_target_preserves_default(tmp_path: Path, test_agent: str, mode: str) -> None:
    """Real stdio ingress must keep metadata writes separate from selection."""
    source = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("SCRIBE_") and key != "DATABASE_URL"}
    env.update({
        "SCRIBE_RELEASE_PROFILE": "internal", "SCRIBE_DISABLE_DOTENV": "1",
        "SCRIBE_LOAD_REPO_DOTENV": "0", "SCRIBE_MODE": "standalone",
        "SCRIBE_STORAGE_BACKEND": "sqlite", "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_DB_PATH": str(runtime / "scribe.sqlite3"),
        "SCRIBE_STATE_PATH": str(runtime / "state.json"), "SCRIBE_ROOT": str(runtime),
        "SCRIBE_REPO_ROOT": str(repo), "SCRIBE_TRUSTED_REPO_ROOTS": str(repo),
        "PYTHONPATH": str(source / "src"),
        "SBR_TEST_AGENT": test_agent, "SBR_TEST_MODE": mode, "SBR_TEST_SOURCE": str(source),
    })
    if mode == "legacy":
        _assert_retired_sdk_handshake_rejected(source, env)
        return
    probe = r'''
import anyio, json, os, sqlite3, sys
from pathlib import Path
from importlib.metadata import version
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client
import scribe_mcp
from scribe_mcp.utils.frontmatter import parse_frontmatter

agent = os.environ["SBR_TEST_AGENT"]
repo = Path(os.environ["SCRIBE_REPO_ROOT"])
fields = ("authoritative_session_key", "repo_root", "project_name", "project_key",
          "binding_generation", "caller_session_key_hash")

def bindings():
    # Read the disposable store, including timestamps; never manufacture authority.
    with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
        return connection.execute("SELECT * FROM session_projects ORDER BY session_id").fetchall()

async def call(client, name, arguments):
    result = await client.call_tool(name, {"agent": agent, **arguments})
    assert not result.is_error, (name, result)
    data = json.loads("\n".join(getattr(item, "text", "") for item in result.content))
    assert data.get("ok", True) is not False, (name, data)
    return data

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "scribe_mcp"],
                                   env=dict(os.environ), cwd=os.environ["SBR_TEST_SOURCE"])
    with anyio.fail_after(90):
        async with Client(stdio_client(params), mode=os.environ["SBR_TEST_MODE"]) as client:
            async with Client(stdio_client(params), mode=os.environ["SBR_TEST_MODE"]) as sibling:
                await call(sibling, "set_project", {"name": "sibling_default", "root": str(repo), "format": "structured"})
                await call(client, "set_project", {"name": "target_b", "root": str(repo), "format": "structured"})
                await call(client, "set_project", {"name": "default_a", "root": str(repo), "format": "structured"})
                doctor = await call(client, "scribe_doctor", {})
                before = tuple(doctor["runtime"]["repo_authority"].get(key) for key in fields)
                assert before[2] == "default_a" and before[4] == 2, before
                records = bindings()
                assert len(records) >= 2, records
                created = await call(client, "manage_docs", {"project": "target_b", "action": "create",
                    "doc_name": "DEFAULT_GUARD", "metadata": {"doc_type": "custom",
                    "body": "# Default guard\n\n<!-- ID: proof -->\nInitial text.\n",
                    "summary": "Isolated default binding regression.", "status": "in_progress"}})
                path = Path(created["path"]).resolve()
                assert path.is_relative_to(repo.resolve())
                await call(client, "manage_docs", {"project": "target_b", "action": "replace_section",
                    "doc": "DEFAULT_GUARD", "section": "proof", "content": "Verified default guard text.\n"})
                after_doc = await call(client, "scribe_doctor", {})
                observed = tuple(after_doc["runtime"]["repo_authority"].get(key) for key in fields)
                print(json.dumps({"sdk": version("mcp"), "source": scribe_mcp.__file__,
                    "mode": os.environ["SBR_TEST_MODE"], "before": before, "after": observed}), flush=True)
                assert observed == before, "explicit B document changed caller default A"
                assert bindings() == records, "document changed a binding record or timestamp"
                assert "Verified default guard text.\n" in path.read_text(encoding="utf-8")
                with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
                    docs = json.loads(connection.execute(
                        "SELECT docs_json FROM scribe_projects WHERE name = ? AND repo_root = ?",
                        ("target_b", str(repo))).fetchone()[0])
                assert docs["DEFAULT_GUARD"] == str(path)
                review = await call(client, "manage_docs", {"project": "target_b", "action": "create",
                    "doc_name": "REVIEW_DEFAULT_GUARD", "metadata": {"doc_type": "review",
                    "stage": "phase_4_2", "summary": "Review metadata persistence guard."}})
                await call(client, "manage_docs", {"project": "target_b", "action": "replace_section",
                    "doc": review["doc_name"], "section": "executive_summary",
                    "content": "Review metadata followup.\n"})
                review_path = Path(review["path"]).resolve()
                assert review_path.is_relative_to(repo.resolve())
                assert "Review metadata followup." in review_path.read_text(encoding="utf-8")
                spec = await call(client, "manage_docs", {"project": "target_b", "action": "create",
                    "doc": "spec_guard", "metadata": {"doc_type": "spec", "doc_name": "SPEC_DEFAULT_GUARD",
                    "body": "# Spec\n\nMetadata persistence guard.\n"}})
                await call(client, "manage_docs", {"project": "target_b", "action": "frontmatter_update",
                    "doc": "SPEC_DEFAULT_GUARD", "metadata": {"frontmatter": {"status": "ready"}}})
                spec_path = Path(spec["path"]).resolve()
                assert spec_path.is_relative_to(repo.resolve())
                spec_metadata = parse_frontmatter(spec_path.read_text(encoding="utf-8")).frontmatter_data
                assert spec_metadata["doc_type"] == "spec"
                assert spec_metadata["status"] == "ready"
                with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
                    docs = json.loads(connection.execute(
                        "SELECT docs_json FROM scribe_projects WHERE name = ? AND repo_root = ?",
                        ("target_b", str(repo))).fetchone()[0])
                assert docs[review["doc_name"]] == str(review_path)
                assert docs["SPEC_DEFAULT_GUARD"] == str(spec_path)
                assert bindings() == records, "metadata persistence changed a caller or sibling binding"
                for owner, project in ((client, "default_a"), (sibling, "sibling_default")):
                    marker = "default-guard-" + project
                    await call(owner, "append_entry", {"message": marker, "format": "structured"})
                    recent = await call(owner, "read_recent", {"limit": 1, "format": "structured"})
                    assert marker in json.dumps(recent)
                assert bindings() == records
anyio.run(main)
'''
    sdk_python = os.environ.get("SBR_SDK_PYTHON", sys.executable)
    result = subprocess.run([sdk_python, "-c", probe], cwd=source, env=env,
                            capture_output=True, text=True, timeout=110)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Project discovery failed during recovery:" not in result.stderr, result.stderr
    assert "Failed to load projects from backend:" not in result.stderr, result.stderr


@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("configured_default", [False, True])
def test_real_sdk_first_bind_and_cross_repo_rebind(
    tmp_path: Path, test_agent: str, mode: str, configured_default: bool,
) -> None:
    """Persist the authorized root before the first binding and a root change."""
    source = Path(__file__).resolve().parents[1]
    repo_a, repo_b = tmp_path / "repo_a", tmp_path / "repo_b"
    for repo in (repo_a, repo_b):
        (repo / ".git").mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("SCRIBE_") and key not in {"DATABASE_URL", "REPO_ROOT"}}
    env.update({
        "SCRIBE_RELEASE_PROFILE": "internal", "SCRIBE_DISABLE_DOTENV": "1",
        "SCRIBE_LOAD_REPO_DOTENV": "0", "SCRIBE_MODE": "standalone",
        "SCRIBE_STORAGE_BACKEND": "sqlite", "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_DB_PATH": str(runtime / "scribe.sqlite3"),
        "SCRIBE_STATE_PATH": str(runtime / "state.json"), "SCRIBE_ROOT": str(runtime),
        "PYTHONPATH": str(source / "src"), "PYTHONDONTWRITEBYTECODE": "1",
        "SBR_TEST_AGENT": test_agent, "SBR_TEST_MODE": mode,
        "SBR_TEST_REPO_A": str(repo_a), "SBR_TEST_REPO_B": str(repo_b),
        "SBR_TEST_CONFIGURED_DEFAULT": "1" if configured_default else "0",
    })
    if configured_default:
        env["SCRIBE_REPO_ROOT"] = str(repo_a)
    if mode == "legacy":
        _assert_retired_sdk_handshake_rejected(source, env)
        return
    probe = r'''
import anyio, json, os, sqlite3, sys
from pathlib import Path
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client
from scribe_mcp.config.settings import Settings
from scribe_mcp.storage.models import compute_project_key

agent = os.environ["SBR_TEST_AGENT"]
repo_a, repo_b = Path(os.environ["SBR_TEST_REPO_A"]), Path(os.environ["SBR_TEST_REPO_B"])
expected_default = repo_a if os.environ["SBR_TEST_CONFIGURED_DEFAULT"] == "1" else None
assert Settings.load().default_repo_root == expected_default

def bindings():
    # Include timestamps: reads, writes and denials must not silently rebind.
    with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""SELECT b.*, s.repo_root AS session_repo_root,
            p.repo_root AS canonical_repo_root FROM session_projects AS b
            JOIN scribe_sessions AS s ON s.session_id = b.session_id
            LEFT JOIN scribe_projects AS p ON p.project_key = b.project_key
            ORDER BY b.session_id""").fetchall()
        return {row["session_id"]: dict(row) for row in rows}

async def call(client, name, arguments, *, denied=False):
    result = await client.call_tool(name, {"agent": agent, **arguments})
    text = "\n".join(getattr(item, "text", "") for item in result.content)
    try:
        data = json.loads(text)
    except ValueError:
        assert denied and result.is_error, (name, text)
        return {"error": text}
    if denied:
        assert result.is_error or data.get("ok") is False, (name, data)
    else:
        assert not result.is_error and data.get("ok", True) is not False, (name, data)
    return data

def assert_binding(session, project, repo, generation):
    row = bindings()[session]
    assert row["project_name"] == project, row
    assert row["project_key"] == compute_project_key(repo_root=str(repo), project_name=project), row
    assert row["session_repo_root"] == row["canonical_repo_root"] == str(repo), row
    assert row["binding_state"] == "resolved" and row["binding_state_reason"] is None, row
    assert row["binding_generation"] == generation and row["updated_at"], row
    return row

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "scribe_mcp"],
                                   env=dict(os.environ))
    with anyio.fail_after(100):
        async with Client(stdio_client(params), mode=os.environ["SBR_TEST_MODE"]) as client:
            bound = await call(client, "set_project", {"name": "initial_a", "root": str(repo_a),
                                                       "format": "structured"})
            # No second set_project or diagnostic may mask the first-bind failure.
            await call(client, "read_recent", {"limit": 1, "format": "structured"})
            session = bound["project"]["session_id"]
            first = assert_binding(session, "initial_a", repo_a, 1)
            async with Client(stdio_client(params), mode=os.environ["SBR_TEST_MODE"]) as sibling:
                sibling_bound = await call(sibling, "set_project", {"name": "sibling_only",
                    "root": str(repo_a), "format": "structured"})
                await call(sibling, "read_recent", {"limit": 1, "format": "structured"})
                sibling_session = sibling_bound["project"]["session_id"]
                assert sibling_session != session
                sibling_record = assert_binding(sibling_session, "sibling_only", repo_a, 1)
                assert bindings()[session] == first
                rebound = await call(client, "set_project", {"name": "chosen_b", "root": str(repo_b),
                                                             "format": "structured"})
                await call(client, "read_recent", {"limit": 1, "format": "structured"})
                assert rebound["project"]["session_id"] == session
                second = assert_binding(session, "chosen_b", repo_b, 2)
                assert second["updated_at"] >= first["updated_at"]
                assert bindings()[sibling_session] == sibling_record
                records = bindings()
                foreign_log = repo_a / ".scribe/docs/dev_plans/sibling_only/PROGRESS_LOG.md"
                foreign_before = foreign_log.read_bytes()
                await call(client, "append_entry", {"project": "sibling_only",
                    "message": "must-not-reach-foreign-root", "format": "structured"}, denied=True)
                await call(client, "read_recent", {"project": "sibling_only", "limit": 1,
                    "format": "structured"}, denied=True)
                assert foreign_log.read_bytes() == foreign_before
                assert bindings() == records, "foreign denials changed caller or sibling binding"
                for owner, project in ((client, "chosen_b"), (sibling, "sibling_only")):
                    marker = "first-bind-rebind-" + project
                    await call(owner, "append_entry", {"message": marker, "format": "structured"})
                    recent = await call(owner, "read_recent", {"limit": 1, "format": "structured"})
                    assert marker in json.dumps(recent), recent
                assert bindings() == records, "mixed calls silently rebound or refreshed timestamps"
                print(json.dumps({"mode": os.environ["SBR_TEST_MODE"], "first_generation": 1,
                    "rebind_generation": 2, "recovery_binds": 0, "sibling_unchanged": True,
                    "foreign_denied": True}), flush=True)
anyio.run(main)
'''
    sdk_python = os.environ.get("SBR_SDK_PYTHON", sys.executable)
    result = subprocess.run([sdk_python, "-c", probe], cwd=source, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.asyncio
@pytest.mark.parametrize("catalog_state", ["fresh", "legacy", "legacy-keyed"])
@pytest.mark.parametrize("catalog", ["global", "repo"])
async def test_sqlite_catalog_ready_before_project_lookup(
    tmp_path: Path, catalog_state: str, catalog: str,
) -> None:
    """Startup discovery must work before fetch/upsert can prepare identity columns."""
    from scribe_mcp.storage.models import compute_project_key, compute_repo_id
    from scribe_mcp.storage.sqlite import SQLiteStorage

    db_path = tmp_path / "catalog.sqlite3"
    repo = str(tmp_path.resolve())
    progress_log = str(tmp_path / "PROGRESS_LOG.md")
    legacy = catalog_state != "fresh"
    retained_key = "pk-historical-retained" if catalog_state == "legacy-keyed" else None
    if legacy:
        # Supported historical project table, with a real row to verify backfill.
        with sqlite3.connect(db_path) as connection:
            connection.execute("""CREATE TABLE scribe_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                repo_root TEXT NOT NULL, progress_log_path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            connection.execute(
                "INSERT INTO scribe_projects (name, repo_root, progress_log_path) VALUES (?, ?, ?)",
                ("legacy_project", repo, progress_log),
            )
            if retained_key:
                connection.execute("ALTER TABLE scribe_projects ADD COLUMN project_key TEXT")
                connection.execute("ALTER TABLE scribe_projects ADD COLUMN repo_id TEXT")
                connection.execute("ALTER TABLE scribe_projects ADD COLUMN extension_blob BLOB")
                connection.execute("ALTER TABLE scribe_projects ADD COLUMN extension_num REAL")
                connection.execute("UPDATE scribe_projects SET project_key = ?", (retained_key,))
                connection.execute(
                    "UPDATE scribe_projects SET extension_blob = ?, extension_num = ?",
                    (b"\x00\xff", 1.25),
                )
                keyed_snapshot_sql = (
                    "SELECT id,name,repo_root,progress_log_path,created_at,updated_at,"
                    "project_key,repo_id,extension_blob,typeof(extension_blob),"
                    "extension_num,typeof(extension_num) FROM scribe_projects ORDER BY id"
                )
                keyed_before = connection.execute(keyed_snapshot_sql).fetchall()

    storage = SQLiteStorage(db_path)
    try:
        await storage.setup()
        projects = (await storage.list_projects() if catalog == "global"
                    else await storage.list_projects_by_repo(repo))
        assert [project.name for project in projects] == (["legacy_project"] if legacy else [])
        if legacy:
            project = projects[0]
            assert project.id == 1
            assert project.repo_root == repo
            assert project.progress_log_path == progress_log
            # MAJOR preserves established keyed rows, including nullable repo_id.
            assert project.repo_id == (None if retained_key else compute_repo_id(repo))
            assert project.project_key == (retained_key or compute_project_key(
                repo_root=repo, project_name=project.name,
            ))
            assert await storage.list_projects_by_repo(str(tmp_path / "other")) == []
        # Readiness includes the schema even when the catalog is empty.
        with sqlite3.connect(db_path) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(scribe_projects)")}
            assert {"repo_id", "project_key", "bridge_id", "bridge_managed"} <= columns
            if retained_key:
                assert connection.execute(keyed_snapshot_sql).fetchall() == keyed_before
        assert await storage.list_projects() == projects
    finally:
        await storage.close()
    reopened = SQLiteStorage(db_path)
    try:
        assert await reopened.list_projects() == projects
        if retained_key:
            with sqlite3.connect(db_path) as connection:
                assert connection.execute(keyed_snapshot_sql).fetchall() == keyed_before
    finally:
        await reopened.close()
