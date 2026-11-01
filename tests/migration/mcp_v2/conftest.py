from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "regression: permanent behavioral regression guard")
    config.addinivalue_line("markers", "mcp_v2: MCP SDK v2 migration compatibility lane")
    # A registered plugin sees the whole invocation, including sibling files.
    # Leaving this hook on the child conftest silently omitted those nodes.
    if not config.pluginmanager.has_plugin("scribe_mcp_v2_phase_recorder"):
        config.pluginmanager.register(_InvocationPhaseRecorder(), "scribe_mcp_v2_phase_recorder")


class _InvocationPhaseRecorder:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo):
        result = yield
        _record_phase_report(item, result.get_result())


def _record_phase_report(item: pytest.Item, report: pytest.TestReport) -> None:
    crash = getattr(report.longrepr, "reprcrash", None)
    message = crash.message if crash is not None else (report.longreprtext if report.failed else "")
    root = str(Path(__file__).resolve().parents[3])
    message = message.replace(root, "<REPO>")
    message = re.sub(r"/tmp/pytest-of-[^/]+/pytest-\d+[^\s'\"<>:,)\]]*", "<TMP>", message)
    message = message.replace(str(Path.home()), "<HOME>")
    message = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b", "<TIME>", message)
    message = re.sub(r"\bpid[=: ]+\d+", "pid=<PID>", message, flags=re.IGNORECASE)
    message = re.sub(r"\b\d+\.\d+\s*(?:seconds|ms)\b", "<TIME>", message)
    code = re.search(r"(?:rpc_code|error_code)['\"]?:\s*['\"]?([-A-Z0-9_]+)", message)
    location = None
    if crash is not None:
        location = str(crash.path).replace(root + "/", "") + ":" + str(crash.lineno)
    fingerprint = {"nodeid": report.nodeid, "phase": report.when,
                   "outcome": report.outcome, "code": code.group(1) if code else ("ASSERTION" if report.failed else None),
                   "assertion_location": location, "message": message,
                   "message_sha256": hashlib.sha256(message.encode()).hexdigest()}
    property_value = ("phase_report", json.dumps(fingerprint, sort_keys=True))
    item.user_properties.append(property_value)
    report.user_properties.append(property_value)


@dataclass(frozen=True)
class ProbeResult:
    returncode: int
    payload: dict[str, Any]
    stderr: str


@pytest.fixture(scope="session")
def mcp_v2_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def candidate_python(mcp_v2_repo_root: Path) -> Path:
    configured = os.environ.get("MCPV2_CANDIDATE_PYTHON")
    python = Path(configured).absolute() if configured else Path(sys.executable).absolute()
    result = subprocess.run(
        [str(python), "-c", "from importlib.metadata import version; print(version('mcp'))"],
        cwd=mcp_v2_repo_root,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == "2.3.0", result.stdout
    return python


@pytest.fixture
def isolated_runtime_env(
    tmp_path: Path,
    mcp_v2_repo_root: Path,
    test_agent: str,
) -> dict[str, str]:
    runtime = tmp_path / "runtime"
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    for path in (runtime, repo_a / ".git", repo_b / ".git"):
        path.mkdir(parents=True)
    # Allowlist the process substrate. In particular no live DB DSN, token,
    # endpoint or inherited Scribe binding reaches a disposable child.
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}}
    env.update(
        {
            "SCRIBE_DISABLE_DOTENV": "1",
            "SCRIBE_LOAD_REPO_DOTENV": "0",
            "SCRIBE_MODE": "standalone",
            "SCRIBE_RELEASE_PROFILE": "public",
            "SCRIBE_TRANSPORT": "stdio",
            "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
            "PYTHONDONTWRITEBYTECODE": "1",
            "SCRIBE_STORAGE_BACKEND": "sqlite",
            "SCRIBE_DB_PATH": str(runtime / "scribe.sqlite3"),
            "SCRIBE_STATE_PATH": str(runtime / "state.json"),
            "SCRIBE_ROOT": str(runtime),
            "SCRIBE_REPO_ROOT": str(repo_a),
            "SCRIBE_TRUSTED_REPO_ROOTS": os.pathsep.join((str(repo_a), str(repo_b))),
            "SCRIBE_TRANSPORT_ALLOWED_ORIGINS": "https://trusted.example",
            "SCRIBE_TRANSPORT_AUTH_TOKEN": "mcp-v2-test-token",
            "MCPV2_REPO_A": str(repo_a),
            "MCPV2_REPO_B": str(repo_b),
            "MCPV2_TEST_AGENT": test_agent,
        }
    )
    if os.environ.get("MCPV2_ISOLATED_INSTALL") == "1":
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = str(mcp_v2_repo_root / "src")
    return env


@pytest.fixture
def internal_loopback_runtime_env(isolated_runtime_env: dict[str, str]) -> dict[str, str]:
    """A distinct fixed profile; the public fixture is never modified."""
    env = dict(isolated_runtime_env)
    env["SCRIBE_RELEASE_PROFILE"] = "internal"
    env["SCRIBE_TRANSPORT_HOST"] = "127.0.0.1"
    return env


def run_json_probe(
    python: Path,
    code: str,
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 90,
) -> ProbeResult:
    process = subprocess.Popen(
        [str(python), "-c", code],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    finally:
        # This group contains only the probe and the children it created.
        for sig, budget in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=budget)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                break
            except subprocess.TimeoutExpired:
                continue
        process.wait(timeout=5)
    stdout_lines = [line for line in stdout.splitlines() if line.strip()]
    payload: dict[str, Any] = {}
    if stdout_lines:
        payload = json.loads(stdout_lines[-1])
    return ProbeResult(process.returncode, payload, stderr)


@pytest.fixture
def json_probe(request: pytest.FixtureRequest):
    def recorded(*args, **kwargs):
        result = run_json_probe(*args, **kwargs)
        request.node.user_properties.append(("probe_result", json.dumps({
            "python": str(args[0]), "returncode": result.returncode,
            "payload": result.payload, "stderr": result.stderr}, sort_keys=True)))
        return result
    return recorded


# Healthy children only observe real admission/identity/dispatch/store facts.
# Explicit disposable fault children below exercise mutation sensitivity;
# no binding, C11 result or Context is ever fabricated to populate a store.
CHILD_OBSERVER = r'''
import asyncio, dataclasses, hashlib, json, os, sqlite3, traceback
from pathlib import Path
import scribe_mcp.server as server
from scribe_mcp.shared import execution_context as identity
from starlette.responses import JSONResponse
from starlette.routing import Route

counters = {"identity": 0, "begin": 0, "end": 0, "dispatch": 0}
finite_writes = set()
original_schedule = server.schedule_background_task
def schedule_observed(coro, *args, **kwargs):
    task = original_schedule(coro, *args, **kwargs)
    # Formatter telemetry uses unnamed finite tasks; never drain/cancel the
    # persistent cleanup services or suppress any resulting DB/file effect.
    if not kwargs.get("persistent", False) and kwargs.get("service_name") is None:
        finite_writes.add(task)
        task.add_done_callback(finite_writes.discard)
    return task
server.schedule_background_task = schedule_observed

async def settle_finite_writes():
    deadline = asyncio.get_running_loop().time() + 5
    while finite_writes:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("finite seed writes did not quiesce within call10")
        await asyncio.wait_for(asyncio.shield(asyncio.gather(*tuple(finite_writes))), remaining)

http = None
if os.environ.get("SCRIBE_TRANSPORT") == "sse":
    import scribe_mcp.server_sse as http
original_resolve = http.resolve_application_identity if http is not None else None
def resolve(*args, **kwargs):
    counters["identity"] += 1
    return original_resolve(*args, **kwargs)
if http is not None:
    http.resolve_application_identity = resolve
for label, owner, name in (("begin", server, "begin_transport_operation"),
                           ("end", server, "end_transport_operation"),
                           ("dispatch", server.app, "call_tool")):
    def wrap(original, label):
        async def measured(*args, **kwargs):
            counters[label] += 1
            try:
                return await original(*args, **kwargs)
            except BaseException:
                traceback.print_exc()
                raise
        return measured
    setattr(owner, name, wrap(getattr(owner, name), label))

async def snapshot():
    manager = server.state_manager
    state = dataclasses.asdict(await manager.load())
    state.pop("operation_timestamp", None)
    agent = server.get_agent_context_manager()
    async with agent._lease_lock:
        leases = dict(agent._session_leases)
    router = server.router_context_manager
    async with router._lock:
        sessions = dict(router._transport_sessions)
        projects = dict(router._session_projects)
        stable = dict(router._stable_agent_sessions)
    bindings = {}
    for session in sorted(set(sessions.values()) | set(projects)):
        value = await server.storage_backend.get_session_project(session)
        if value is not None:
            bindings[session] = dataclasses.asdict(value)
    with identity._APPLICATION_IDENTITIES_LOCK:
        handles = {key: dataclasses.asdict(record.identity)
                   for key, record in identity._APPLICATION_IDENTITIES.items()}
        stdio = {key: dataclasses.asdict(value)
                 for key, value in identity._STDIO_IDENTITIES.items()}
    files = {}
    database = []
    db = Path(os.environ["SCRIBE_DB_PATH"])
    if db.exists():
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
            database = list(connection.iterdump())
    for label, root in (("runtime", os.environ["SCRIBE_ROOT"]),
                        ("a", os.environ["MCPV2_REPO_A"]),
                        ("b", os.environ["MCPV2_REPO_B"])):
        for path in sorted(Path(root).rglob("*")):
            if not path.is_file() or ".git" in path.parts or path.name.startswith(db.name):
                continue
            files[label + "/" + str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    value = {"profile": server.settings.release_profile,
             "transport_policy": server.get_transport_policy(),
             "state": state, "bindings": bindings, "leases": leases,
             "router": {"sessions": sessions, "projects": projects, "stable": stable},
             "handles": handles, "stdio": stdio, "database": database,
             "files": files, "counters": dict(counters)}
    return json.loads(json.dumps(value, sort_keys=True, default=str))

async def observe_request(ctx, call_next):
    wire = ctx.params
    params = wire.get("params", wire) if isinstance(wire, dict) else {}
    meta = params.get("_meta", {}) if isinstance(params, dict) else {}
    retired = ctx.method == "initialize" or meta.get("io.modelcontextprotocol/protocolVersion") == "2025-11-25"
    try:
        before = await snapshot()
    except BaseException:
        traceback.print_exc()
        raise
    try:
        return await call_next(ctx)
    finally:
        after = await snapshot()
        with Path(os.environ["MCPV2_OBSERVATIONS"]).open("a") as stream:
            stream.write(json.dumps({"method": ctx.method, "retired": retired,
                                     "before": before, "after": after}, sort_keys=True) + "\n")
server.app.middleware.insert(0, observe_request)

async def state_endpoint(request):
    await settle_finite_writes()
    return JSONResponse(await snapshot())
if http is not None:
    original_builder = http._build_starlette_app
    def builder(**kwargs):
        app = original_builder(**kwargs)
        app.routes.append(Route("/__matrix/state", state_endpoint, methods=["GET"]))
        # Mutation-sensitivity controls only, in disposable loopback children.
        # Healthy children use neither branch; no tool locality/grant changes.
        fault = os.environ.get("MCPV2_TEST_FAULT")
        if fault == "omit-auth":
            http._request_is_authenticated = lambda request, expected: True
        elif fault == "restore-old-route":
            class RestoredOldRoute:
                def __init__(self, app):
                    self.app = app
                async def __call__(self, scope, receive, send):
                    if scope["type"] == "http" and scope.get("path") == "/sse":
                        scope = dict(scope, path="/mcp", raw_path=b"/mcp")
                    await self.app(scope, receive, send)
            app.add_middleware(RestoredOldRoute)
        return app
    http._build_starlette_app = builder
'''


def _observed_env(tmp_path: Path, runtime_env: dict[str, str]) -> dict[str, str]:
    hook = tmp_path / ("observer-" + runtime_env["SCRIBE_RELEASE_PROFILE"])
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(CHILD_OBSERVER, encoding="utf-8")
    env = dict(runtime_env)
    # Installed-artifact validation also retains its artifact-first import path.
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(hook), env.get("PYTHONPATH"))))
    env["MCPV2_OBSERVATIONS"] = str(tmp_path / "observations.json")
    return env


@pytest.fixture
def observed_runtime_env(tmp_path: Path, isolated_runtime_env: dict[str, str]) -> dict[str, str]:
    return _observed_env(tmp_path, isolated_runtime_env)


@pytest.fixture
def observed_internal_runtime_env(tmp_path: Path, internal_loopback_runtime_env: dict[str, str]) -> dict[str, str]:
    return _observed_env(tmp_path, internal_loopback_runtime_env)
