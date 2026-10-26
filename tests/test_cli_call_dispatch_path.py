import argparse
import asyncio
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
from typing import Any

import pytest

from scribe_mcp.cli import main as cli_main


@pytest.fixture
def isolated_cli_env(tmp_path):
    (tmp_path / ".git").mkdir()
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
    env.update(
        PYTHONPATH=str(Path(cli_main.__file__).resolve().parents[2]),
        PYTHONDONTWRITEBYTECODE="1",
        SCRIBE_MODE="standalone",
        SCRIBE_STORAGE_BACKEND="sqlite",
        SCRIBE_DISABLE_DOTENV="1",
        SCRIBE_OBJECT_STORE_PROVIDER="filesystem",
        SCRIBE_ROOT=str(tmp_path),
        SCRIBE_DB_PATH=str(tmp_path / "test.db"),
        SCRIBE_STATE_PATH=str(tmp_path / "state.json"),
    )
    return env


@pytest.fixture
def cli_process(tmp_path, isolated_cli_env):
    def invoke(*arguments, repo_root=None, agent="test-agent", session="default", **options):
        root = repo_root or tmp_path
        env = dict(isolated_cli_env, SCRIBE_CLI_AGENT=agent)
        selector = [] if arguments[:2] == ("session", "reset") else ["--agent", agent]
        result = subprocess.run(
            [sys.executable, "-m", "scribe_mcp.cli.main", *arguments,
             *selector, "--repo-root", str(root),
             "--session" if arguments[0] == "call" else "--name", session],
            cwd=root, env=env, capture_output=True, text=True, timeout=20,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout if options.get("text") else json.loads(result.stdout)
    return invoke


def _bind_cli_project(invoke, root, agent, project, session):
    result = invoke(
        "call", "set_project", "--args-json",
        json.dumps({"name": project, "root": str(root), "format": "structured"}),
        repo_root=root, agent=agent, session=session,
    )
    assert result["ok"] is True


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("session", ["default", "named"])
def test_cli_cache_retains_each_callers_project(tmp_path, cli_process, test_agent, session):
    _bind_cli_project(cli_process, tmp_path, test_agent, "project-a", session)
    _bind_cli_project(cli_process, tmp_path, "other-" + test_agent, "project-b", session)
    for caller, project in [(test_agent, "project-a"), ("other-" + test_agent, "project-b")]:
        state = cli_process("session", "show", agent=caller, session=session)
        assert state["context"]["project_name"] == project
        assert state["agent"] == caller and state["session_name"] == session


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("session", ["default", "named"])
def test_cli_reset_preserves_other_callers_and_sessions(tmp_path, cli_process, test_agent, session):
    other = "other-" + test_agent
    _bind_cli_project(cli_process, tmp_path, test_agent, "project-a", session)
    _bind_cli_project(cli_process, tmp_path, test_agent, "sibling", "sibling")
    _bind_cli_project(cli_process, tmp_path, other, "project-b", session)
    cli_process("session", "reset", agent=test_agent, session=session, text=True)
    foreign = cli_process("session", "show", agent=other, session=session)
    assert foreign["context"]["project_name"] == "project-b"
    sibling = cli_process("session", "show", agent=test_agent, session="sibling")
    assert sibling["context"]["project_name"] == "sibling"
    reset = cli_process("session", "show", agent=test_agent, session=session)
    assert reset["context"]["session_scope_state"] == "pre_binding"


@pytest.mark.core
@pytest.mark.regression
def test_cli_cache_and_reset_select_canonical_repo_in_shared_directory(tmp_path, cli_process, test_agent):
    second = tmp_path / "second"
    (second / ".git").mkdir(parents=True)
    shared = tmp_path / "shared-cache"
    shared.mkdir()
    for root in (tmp_path, second):
        (root / ".scribe").mkdir(exist_ok=True)
        (root / ".scribe" / "cli").symlink_to(shared, target_is_directory=True)
    _bind_cli_project(cli_process, tmp_path, test_agent, "repo-a", "default")
    _bind_cli_project(cli_process, second, test_agent, "repo-b", "default")
    state = cli_process("session", "show", agent=test_agent)
    assert state["context"]["project_name"] == "repo-a"
    alias = tmp_path / "alias"
    alias.symlink_to(second, target_is_directory=True)
    state = cli_process("session", "show", repo_root=alias, agent=test_agent)
    assert state["context"]["project_name"] == "repo-b"
    cli_process("session", "reset", repo_root=alias, agent=test_agent, text=True)
    state = cli_process("session", "show", agent=test_agent)
    assert state["context"]["project_name"] == "repo-a"
    state = cli_process("session", "show", repo_root=second, agent=test_agent)
    assert state["context"]["session_scope_state"] == "pre_binding"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("session", ["default", "named"])
def test_cli_legacy_cache_requires_matching_tuple_and_scoped_reset(
    tmp_path, cli_process, test_agent, session,
):
    _bind_cli_project(cli_process, tmp_path, test_agent, "legacy-project", session)
    cache_dir = tmp_path / ".scribe" / "cli"
    cache = next(cache_dir.glob("*.json"))
    legacy = cache_dir / (session + ".json")
    cache.replace(legacy)
    own = cli_process("session", "show", agent=test_agent, session=session)
    assert own["context"]["project_name"] == "legacy-project"
    cli_process("session", "reset", agent="other-" + test_agent, session=session, text=True)
    assert legacy.exists()
    # The explicit selector wins over the environment, just as for session show.
    cli_process("session", "reset", "--agent", test_agent,
                agent="other-" + test_agent, session=session, text=True)
    assert not legacy.exists()
    own = cli_process("session", "show", agent=test_agent, session=session)
    assert own["context"]["session_scope_state"] == "pre_binding"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("invalid", ["agent", "repo_root", "session_name", "corrupt"])
def test_cli_foreign_or_corrupt_legacy_cache_stays_unbound(
    tmp_path, cli_process, test_agent, invalid,
):
    from scribe_mcp.cli.session_store import CliSessionState

    cache = tmp_path / ".scribe" / "cli" / "default.json"
    cache.parent.mkdir(parents=True)
    payload = CliSessionState(
        session_name="default", repo_root=str(tmp_path), agent=test_agent,
        transport_session_id="advisory-only", context={"project_name": "foreign"},
    ).to_dict()
    payload[invalid] = "mismatch"
    cache.write_text("{" if invalid == "corrupt" else json.dumps(payload), encoding="utf-8")
    before = cache.read_bytes()
    state = cli_process("session", "show", agent=test_agent)
    assert "project_name" not in state["context"]
    assert state["context"]["session_scope_state"] == "pre_binding"
    cli_process("session", "reset", agent=test_agent, text=True)
    assert cache.read_bytes() == before


@pytest.mark.core
@pytest.mark.regression
def test_corrupt_scoped_cache_does_not_resurrect_legacy_binding(tmp_path, cli_process, test_agent):
    _bind_cli_project(cli_process, tmp_path, test_agent, "current-project", "default")
    cache_dir = tmp_path / ".scribe" / "cli"
    scoped = next(cache_dir.glob("*.json"))
    legacy = cache_dir / "default.json"
    assert scoped != legacy
    saved = scoped.read_bytes()
    foreign = json.loads(saved)
    foreign["agent"] = "other-" + test_agent
    scoped.write_text(json.dumps(foreign), encoding="utf-8")
    before = scoped.read_bytes()
    state = cli_process("session", "show", agent=test_agent)
    assert "project_name" not in state["context"]
    cli_process("session", "reset", "--agent", test_agent, text=True)
    assert scoped.read_bytes() == before
    legacy.write_bytes(saved)
    scoped.write_text("{", encoding="utf-8")
    state = cli_process("session", "show", agent=test_agent)
    assert "project_name" not in state["context"]
    assert state["context"]["session_scope_state"] == "pre_binding"
    cli_process("session", "reset", "--agent", test_agent, text=True)
    assert not scoped.exists()
    assert not legacy.exists()


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("session", ["default", "named"])
def test_separate_cli_processes_do_not_inherit_another_agents_project(
    tmp_path, test_agent, session, isolated_cli_env,
):
    """A cache filename is not evidence that its saved context belongs to this caller."""

    def invoke(*arguments):
        result = subprocess.run(
            [sys.executable, "-m", "scribe_mcp.cli.main", *arguments],
            cwd=tmp_path, env=isolated_cli_env, capture_output=True, text=True, timeout=20,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    bound = invoke(
        "call", "set_project", "--repo-root", str(tmp_path), "--agent", test_agent,
        "--session", session, "--args-json",
        json.dumps({"name": "first-project", "root": str(tmp_path), "format": "structured"}),
    )
    assert bound["ok"] is True
    own = invoke("session", "show", "--repo-root", str(tmp_path), "--agent", test_agent, "--name", session)
    assert own["context"]["project_name"] == "first-project"
    foreign = invoke("session", "show", "--repo-root", str(tmp_path), "--agent", "other-" + test_agent, "--name", session)
    assert "project_name" not in foreign["context"]
    assert "scope_provenance" not in foreign["context"]
    assert foreign["context"]["session_scope_state"] == "pre_binding"


@pytest.mark.core
@pytest.mark.regression
def test_stdio_server_survives_live_client_and_exits_on_eof(tmp_path, isolated_cli_env):
    """Exercise the actual SDK transport; only the disposable child is cleaned up."""
    from mcp_types import CLIENT_CAPABILITIES_META_KEY, CLIENT_INFO_META_KEY, PROTOCOL_VERSION_META_KEY

    with tempfile.TemporaryFile(mode="w+t") as errors:
        child = subprocess.Popen(
            [sys.executable, "-m", "scribe_mcp"], cwd=tmp_path, env=isolated_cli_env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True,
        )
        try:
            assert child.stdin is not None and child.stdout is not None
            request = {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {
                "_meta": {
                    PROTOCOL_VERSION_META_KEY: "2026-07-28",
                    CLIENT_INFO_META_KEY: {"name": "scribe-eof-test", "version": "1"},
                    CLIENT_CAPABILITIES_META_KEY: {},
                },
            }}
            child.stdin.write(json.dumps(request) + "\n")
            child.stdin.flush()
            with selectors.DefaultSelector() as ready:
                ready.register(child.stdout, selectors.EVENT_READ)
                assert ready.select(timeout=10), "no response from disposable server"
            reply = json.loads(child.stdout.readline())
            assert reply["jsonrpc"] == "2.0" and reply["id"] == 1
            assert "error" not in reply
            assert isinstance(reply["result"], dict)
            with pytest.raises(subprocess.TimeoutExpired):
                child.wait(timeout=3)
            child.stdin.close()
            assert child.wait(timeout=3) == 0
        finally:
            if child.stdin is not None and not child.stdin.closed:
                child.stdin.close()
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
            if child.stdout is not None:
                child.stdout.close()


@pytest.mark.asyncio
async def test_call_prefers_bound_server_when_endpoint_configured(monkeypatch):
    class Server:
        storage_backend = None

        @staticmethod
        def resolve_tool_startup_profile(_name):
            return "storage_only"

        @staticmethod
        async def invoke_tool(_tool, _args, context=None):
            raise AssertionError("local invoke_tool should not run on healthy bound_server path")

    monkeypatch.setenv("SCRIBE_REMOTE_URL", "http://127.0.0.1:8200")
    monkeypatch.setattr("scribe_mcp.server", Server, raising=False)
    bound_calls = {"count": 0}

    async def fake_bound_call(**kwargs):
        bound_calls["count"] += 1
        assert kwargs["tool"] == "manage_docs"
        assert kwargs["endpoint"] == "http://127.0.0.1:8200"
        assert kwargs["context"]["dispatch_path"] == "bound_server"
        assert kwargs["context"].get("remote_server_url") == "http://127.0.0.1:8200"
        return {"ok": True}

    monkeypatch.setattr(cli_main, "_invoke_tool_bound_server", fake_bound_call)

    args = argparse.Namespace(
        repo_root=cli_main.Path.cwd(),
        session="default",
        agent="test-agent",
        args_json=None,
        arg=[],
        context_json=None,
        session_mode="auto",
        no_save_session=True,
        pretty=False,
        tool="manage_docs",
        tool_timeout_seconds=0.1,
    )
    rc = await cli_main._run_call_command(args, {})
    assert rc == 0
    assert bound_calls["count"] == 1


@pytest.mark.asyncio
async def test_call_bound_server_timeout_falls_back_to_local(monkeypatch, capsys):
    class Server:
        storage_backend = None
        local_attempts = 0

        @staticmethod
        def resolve_tool_startup_profile(_name):
            return "storage_only"

        @staticmethod
        async def invoke_tool(_tool, _args, context=None):
            Server.local_attempts += 1
            assert context.get("dispatch_path") == "local_one_shot"
            return {"ok": True, "path": context.get("dispatch_path")}

    monkeypatch.setenv("SCRIBE_REMOTE_URL", "http://127.0.0.1:8200")
    monkeypatch.setattr("scribe_mcp.server", Server, raising=False)
    bound_calls = {"count": 0}

    async def fake_bound_call(**_kwargs):
        bound_calls["count"] += 1
        raise asyncio.TimeoutError()

    monkeypatch.setattr(cli_main, "_invoke_tool_bound_server", fake_bound_call)

    args = argparse.Namespace(
        repo_root=cli_main.Path.cwd(),
        session="default",
        agent="test-agent",
        args_json=None,
        arg=[],
        context_json=None,
        session_mode="auto",
        no_save_session=True,
        pretty=False,
        tool="manage_docs",
        tool_timeout_seconds=0.01,
    )
    rc = await cli_main._run_call_command(args, {})
    assert rc == 0
    assert bound_calls["count"] == 1
    assert Server.local_attempts == 1
    assert "falling back to local_one_shot" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_call_skip_startup_tool_stays_local_one_shot(monkeypatch):
    class Server:
        storage_backend = None

        @staticmethod
        def resolve_tool_startup_profile(_name):
            return "local_only"

        @staticmethod
        async def invoke_tool(_tool, _args, context=None):
            return {"ok": True, "dispatch_path": context.get("dispatch_path")}

    monkeypatch.setenv("SCRIBE_REMOTE_URL", "http://127.0.0.1:8200")
    monkeypatch.setattr("scribe_mcp.server", Server, raising=False)

    args = argparse.Namespace(
        repo_root=cli_main.Path.cwd(),
        session="default",
        agent="test-agent",
        args_json=None,
        arg=[],
        context_json=None,
        session_mode="auto",
        no_save_session=True,
        pretty=False,
        tool="analyze_logs",
        tool_timeout_seconds=0.1,
    )
    rc = await cli_main._run_call_command(args, {})
    assert rc == 0


@pytest.mark.asyncio
async def test_bound_server_helper_uses_supported_route_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"result": {"ok": True}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setenv("SCRIBE_REMOTE_AUTH_TOKEN", "token-123")
    monkeypatch.setattr(cli_main.httpx, "AsyncClient", FakeAsyncClient)
    result = await cli_main._invoke_tool_bound_server(
        endpoint="http://127.0.0.1:8200",
        tool="manage_docs",
        call_args={"agent": "test-agent", "action": "project_health"},
        context={"mode": "project"},
        timeout_seconds=1.0,
    )
    assert result == {"ok": True}
    assert captured["url"] == "http://127.0.0.1:8200/api/v1/tools/invoke"
    assert captured["json"] == {
        "tool_name": "manage_docs",
        "arguments": {"agent": "test-agent", "action": "project_health"},
        "context": {"mode": "project"},
    }
