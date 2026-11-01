from __future__ import annotations

import asyncio
import copy
from contextvars import ContextVar
import dataclasses
import importlib
import inspect
import json
import math
import os
import platform
import signal
import statistics
import subprocess
import sys
import textwrap
from pathlib import Path
from time import perf_counter
from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from integration.storage import conftest as _reference_fixtures

from scribe_mcp.object_store.filesystem import FilesystemStore
from scribe_mcp.object_store.hybrid import HybridStore
from scribe_mcp.object_store.providers.corta import CortaStoreProvider
from scribe_mcp.scripts import scribe_probe


pytestmark = [pytest.mark.usefixtures("test_agent"), pytest.mark.startup]

# Resolve the same D5 fixture through pytest discovery, never its wrapped body
# or the legacy shared-database fallback. Absence stays a call-phase assertion.
if hasattr(_reference_fixtures, "swarm_postgres_backend"):
    swarm_postgres_backend = _reference_fixtures.swarm_postgres_backend

_REFERENCE_REQUEST = ContextVar("sbr_release_reference_request", default=None)


@pytest.fixture(autouse=True)
def _reference_request_binding(request):
    token = _REFERENCE_REQUEST.set(request)
    try:
        yield
    finally:
        _REFERENCE_REQUEST.reset(token)


@pytest.mark.asyncio
async def test_release_bootstrap_proof_reports_external_persona_mismatch() -> None:
    result = await scribe_probe._release_bootstrap_proof(
        project="demo",
        external_observations={"persona_registered": False},
    )

    assert result["ok"] is False
    assert result["classification"] == "environment_orchestration_mismatch"
    assert result["error_code"] == "persona_not_registered"
    assert result["failed_step"] == "persona_precondition"


@pytest.mark.asyncio
async def test_release_bootstrap_proof_flags_non_lazy_missing_set_project() -> None:
    result = await scribe_probe._release_bootstrap_proof(
        project="demo",
        external_observations={
            "persona_registered": True,
            "open_session_ok": True,
            "discovered_tools": ["read_recent"],
            "lazy_exposure": False,
        },
    )

    assert result["ok"] is False
    assert result["classification"] == "environment_orchestration_mismatch"
    assert result["error_code"] == "set_project_not_exposed"
    assert result["failed_step"] == "tool_discovery"


@pytest.mark.asyncio
async def test_release_bootstrap_proof_accepts_lazy_discovery_and_verifies_repo_flow(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _fake_run_tool(name: str, payload: dict):
        calls.append((name, dict(payload)))
        if name == "set_project":
            return {"ok": True, "project": payload.get("name")}
        if name == "query_entries":
            return {"ok": True, "entries": []}
        raise AssertionError(f"unexpected tool {name}")

    monkeypatch.setattr(scribe_probe, "_run_tool", _fake_run_tool)

    result = await scribe_probe._release_bootstrap_proof(
        project="demo",
        external_observations={
            "persona_registered": True,
            "open_session_ok": True,
            "discovered_tools": ["read_recent"],
            "lazy_exposure": True,
        },
        runtime_budget_ms=5000,
    )

    assert result["ok"] is True
    assert result["classification"] == "repo_flow_verified"
    assert result["release_artifact"]["type"] == "startup_probe_budget"
    assert result["release_artifact"]["within_runtime_budget"] is True
    assert [name for name, _ in calls] == ["set_project", "query_entries"]
    assert calls[0][1]["name"] == "demo"
    assert calls[1][1]["project"] == "demo"
    assert calls[1][1]["search_scope"] == "project"


@pytest.mark.asyncio
async def test_release_bootstrap_proof_runtime_budget_artifact_can_fail_without_reclassifying_flow(
    monkeypatch,
) -> None:
    async def _fake_run_tool(name: str, payload: dict):  # noqa: ARG001
        if name == "set_project":
            await asyncio.sleep(0.02)
            return {"ok": True}
        if name == "query_entries":
            return {"ok": True}
        raise AssertionError(f"unexpected tool {name}")

    monkeypatch.setattr(scribe_probe, "_run_tool", _fake_run_tool)

    result = await scribe_probe._release_bootstrap_proof(
        project="demo",
        external_observations={
            "persona_registered": True,
            "open_session_ok": True,
            "discovered_tools": ["set_project"],
            "lazy_exposure": False,
        },
        runtime_budget_ms=1,
    )

    assert result["ok"] is True
    assert result["classification"] == "repo_flow_verified"
    assert result["runtime_budget"]["within_budget"] is False
    assert result["release_artifact"]["within_runtime_budget"] is False


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.asyncio
async def test_optional_object_store_probe_is_not_in_foreground_startup(
    tmp_path: Path,
) -> None:
    provider = CortaStoreProvider(
        base_url="http://object-store.invalid",
        hmac_key="key",
        project="project",
    )
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=200))
    client.aclose = AsyncMock()
    provider._client = client
    store = HybridStore(local=FilesystemStore(tmp_path), remote=provider)

    await store.setup()

    client.get.assert_not_awaited()
    assert await store.probe_remote_health(timeout_seconds=0.25) is True
    client.get.assert_awaited_once_with("/health", timeout=0.25)
    await store.close()


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.asyncio
async def test_optional_object_store_outage_adds_at_most_50_ms_and_preserves_local_durability(
    tmp_path: Path,
) -> None:
    baseline = FilesystemStore(tmp_path / "baseline")
    baseline_started = perf_counter()
    await baseline.setup()
    baseline_ms = (perf_counter() - baseline_started) * 1000

    durable_content: dict[str, str] = {}
    local = MagicMock(spec=FilesystemStore)

    async def _write_local(key: str, content: str) -> None:
        durable_content[key] = content

    async def _read_local(key: str) -> str | None:
        return durable_content.get(key)

    local.write = AsyncMock(side_effect=_write_local)
    local.read = AsyncMock(side_effect=_read_local)
    remote = CortaStoreProvider(
        base_url="http://object-store.invalid",
        hmac_key="key",
        project="project",
    )
    client = MagicMock()
    client.get = AsyncMock()
    client.request = AsyncMock(side_effect=httpx.ConnectError("unavailable"))
    client.aclose = AsyncMock()
    backoff_started = asyncio.Event()
    release_backoff = asyncio.Event()
    backoff_calls: list[float] = []

    async def _controlled_backoff(seconds: float) -> None:
        backoff_calls.append(seconds)
        backoff_started.set()
        await release_backoff.wait()

    with (
        patch(
            "scribe_mcp.object_store.providers.corta.httpx.AsyncClient",
            return_value=client,
        ) as client_factory,
        patch(
            "scribe_mcp.object_store.providers.corta._async_sleep",
            new=_controlled_backoff,
        ),
    ):
        store = HybridStore(local=local, remote=remote)
        outage_started = perf_counter()
        await store.setup()
        outage_ms = (perf_counter() - outage_started) * 1000
        outage_delta_ms = max(0.0, outage_ms - baseline_ms)

        assert outage_delta_ms <= 50.0, {
            "baseline_ms": baseline_ms,
            "outage_ms": outage_ms,
            "outage_delta_ms": outage_delta_ms,
        }
        client_factory.assert_called_once()
        client.get.assert_not_awaited()
        client.request.assert_not_awaited()

        from scribe_mcp import server

        listed_tools = await server.app.list_tools()
        assert any(tool.name == "append_entry" for tool in listed_tools)

        key = "scribe/docs/dev_plans/startup/PROGRESS_LOG.md"
        content = "[test-agent] locally durable under remote outage"
        write_task = asyncio.create_task(store.write(key, content))
        try:
            await asyncio.wait_for(backoff_started.wait(), timeout=5.0)

            assert write_task.done() is False
            assert await local.read(key) == content
            local.write.assert_awaited_once_with(key, content)
            assert client.request.await_count == 1

            release_backoff.set()
            await asyncio.wait_for(write_task, timeout=5.0)
            assert client.request.await_count == 3
            assert backoff_calls == [0.5, 1.0]
        finally:
            # A failed timing assertion must never strand the remote retry task
            # on the controlled backoff event and stretch teardown indefinitely.
            release_backoff.set()
            if not write_task.done():
                write_task.cancel()
            await asyncio.gather(write_task, return_exceptions=True)
            await store.close()
        client.aclose.assert_awaited_once_with()


# These probes belong to the existing release file.  The C-14 fixture remains
# the only causal/effects oracle; percentile arithmetic uses the standard library.
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_SERVICE_FIELDS = {
    "service", "state", "required_for_core_ready", "last_error_code",
    "last_transition_at", "startup_phase_ms",
}
_SERVICE_STATES = {"initializing", "healthy", "degraded", "stopped"}
_RECEIPT_LIMITS = {
    "append_entry": 512, "read_recent": 1024, "query_entries": 1024,
    "set_project": 1024, "get_project": 1536, "manage_docs": 1536,
}
_REQUESTED_FIELDS = {
    "read_recent": ("entries",), "query_entries": ("entries",),
    "manage_docs": ("content", "diff", "findings"),
}


def _source_revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=_SOURCE_ROOT, text=True, timeout=5,
    ).strip()


def _require_startup_contract():
    from scribe_mcp import server

    for name in ("ServiceStateV1", "ServiceStateNameV1", "get_service_states",
                 "get_background_job_service", "get_background_job_service_health"):
        assert hasattr(server, name), f"SBR-STARTUP.3 missing source boundary: server.{name}"
    assert dataclasses.is_dataclass(server.ServiceStateV1)
    assert {f.name for f in dataclasses.fields(server.ServiceStateV1)} == _SERVICE_FIELDS
    assert server.ServiceStateV1.__dataclass_params__.frozen
    assert set(get_args(server.ServiceStateNameV1)) == _SERVICE_STATES
    return server


def _p(values: list[float], percentile: int) -> float:
    assert len(values) >= 5, "release measurement requires at least five raw samples"
    assert all(math.isfinite(v) and v >= 0 for v in values)
    return statistics.quantiles(values, n=100, method="inclusive")[percentile - 1]


def _record_evidence(record_property, name: str, value: dict) -> None:
    # Pytest's junit property and captured output retain the actual raw records.
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
    record_property(name, encoded)
    print(f"{name}={encoded}")


def _isolated_process(tmp_path: Path, action: str, *, cache: Path | None = None) -> dict:
    root = tmp_path / "repository"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    # Deliberate allowlist: no live database, provider, Council, identity, bridge,
    # object-store credential or caller-context variable is inherited.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT")
           if key in os.environ}
    env.update({
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_CACHE_HOME": str(home / "cache"), "TMPDIR": str(tmp_path),
        "SCRIBE_MODE": "standalone", "SCRIBE_STORAGE_BACKEND": "sqlite",
        "SCRIBE_DISABLE_DOTENV": "1", "SCRIBE_ROOT": str(root),
        "SCRIBE_DB_PATH": str(root / "scribe.db"),
        "SCRIBE_STATE_PATH": str(root / "state.json"),
        "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "PYTHONPATH": os.pathsep.join((str(_SOURCE_ROOT / "src"), str(_SOURCE_ROOT / "tests"))),
        "PYTHONPYCACHEPREFIX": str(cache or tmp_path / "pycache"),
        "PYTHONHASHSEED": "0", "PYTHONUNBUFFERED": "1",
        "SBR_PROBE_ACTION": action,
    })
    if action.startswith("core-") or action == "outage":
        env.update({"SCRIBE_OBJECT_STORE_PROVIDER": "corta",
                    "SCRIBE_OBJECT_STORE_URL": "http://object-store.invalid",
                    "SCRIBE_OBJECT_STORE_KEY": "unit-test-only", "SCRIBE_OBJECT_STORE_PROJECT": "test-agent"})
    started = perf_counter()
    env["SBR_PROBE_STARTED_PERF"] = repr(started)
    with subprocess.Popen(
        [sys.executable, "-c", _PROCESS_PROBE], cwd=root, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"isolated {action} exceeded finite 20s deadline: {stderr[-2000:]}")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
    assert process.returncode == 0, {
        "boundary": action, "returncode": process.returncode, "stderr": stderr[-6000:],
        "stdout": stdout[-2000:],
    }
    rows = [line.removeprefix("SBR_SAMPLE=") for line in stdout.splitlines()
            if line.startswith("SBR_SAMPLE=")]
    assert len(rows) == 1, {"action": action, "missing_or_duplicate_sample": stdout}
    sample = json.loads(rows[0])
    assert sample["source_origin"] == str(_SOURCE_ROOT / "src" / "scribe_mcp" / "server.py")
    sample["process_elapsed_ms"] = (perf_counter() - started) * 1000
    sample["source_revision"] = _source_revision()
    sample["cache_preparation"] = "fresh-private-pycache" if cache is None else "explicit-prewarmed-private-pycache"
    return sample


_PROCESS_PROBE = textwrap.dedent(r'''
    import asyncio, dataclasses, inspect, json, logging, os, socket, sys
    from pathlib import Path
    from time import perf_counter

    # All external contact is denied, including an accidental tokenizer download.
    def deny_network(*args, **kwargs):
        raise OSError("SBR_PROBE_NETWORK_DISABLED")
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    home = Path.home()
    before_metrics = sorted(str(p.relative_to(home)) for p in home.rglob("*scribe_metrics*"))
    started = perf_counter()
    from scribe_mcp import server
    imported_ms = (perf_counter() - started) * 1000
    def rss():
        return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    def fds():
        return len(list(Path("/proc/self/fd").iterdir()))
    def plain(value):
        return dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value
    sample = {"source_origin": str(Path(server.__file__).resolve()),
              "import_ms": imported_ms, "pre_tool_rss_bytes": rss(),
              "module_count": len(sys.modules),
              "token_module_before_use": "tiktoken" in sys.modules,
              "metrics_before": before_metrics,
              "metrics_after_import": sorted(str(p.relative_to(home)) for p in home.rglob("*scribe_metrics*"))}
    action = os.environ["SBR_PROBE_ACTION"]
    from scribe_mcp.utils.tokens import TokenEstimator
    estimator = TokenEstimator()
    sample["cheap_tokens"] = estimator.estimate_tokens("alpha beta gamma", exact=False)
    sample["cheap_stays_lazy"] = estimator.encoder is None and "tiktoken" not in sys.modules

    async def run():
        baseline_tasks = set(asyncio.all_tasks())
        baseline_fds = fds()
        if action in ("import", "lazy"):
            server.tools.ensure_all_tools_loaded()
            tools = await server.app.list_tools()
            sample["tool_count"] = len(tools)
            sample["all_tools_rss_bytes"] = rss()
            sample["all_tools_module_count"] = len(sys.modules)
            sample["all_tools_token_lazy"] = "tiktoken" not in sys.modules
            if action == "lazy":
                first = estimator.estimate_tokens("alpha beta gamma", exact=True)
                encoder = estimator.encoder
                second = estimator.estimate_tokens("alpha beta gamma", exact=True)
                sample.update(exact_tokens=first, exact_repeat_tokens=second,
                              exact_encoder_available=encoder is not None,
                              exact_encoder_reused=encoder is estimator.encoder,
                              exact_module_loaded="tiktoken" in sys.modules)
            return
        from fixtures.swarm import CausalGate
        schema_gate, recovery_gate, optional_gate = CausalGate(), CausalGate(), CausalGate()
        events, ready = [], []
        optional_tasks = set()
        remote_client = None
        class ReadyObserver(logging.Handler):
            def emit(self, record):
                if "Server ready" in record.getMessage():
                    ready.append({"startup_complete": server._startup_complete,
                                  "states": server.get_service_states(),
                                  "events": list(events)})
        observer = ReadyObserver()
        server.logger.addHandler(observer)
        from scribe_mcp.background import BackgroundJobServiceV1
        storage_type = type(server.storage_backend)
        original_setup = storage_type.setup
        original_start = BackgroundJobServiceV1.start
        original_stop = BackgroundJobServiceV1.stop
        original_close = storage_type.close
        async def setup(backend, *args, **kwargs):
            if action.startswith("core-"):
                await schema_gate.hold()
            if action == "core-schema-failure":
                raise RuntimeError("SCRIBE_SCHEMA_NOT_READY")
            await original_setup(backend, *args, **kwargs)
            events.append("schema_ready")
        async def start(service, *args, **kwargs):
            await original_start(service, *args, **kwargs)
            if action.startswith("core-"):
                await recovery_gate.hold()
            if action == "core-recovery-failure":
                raise RuntimeError("SCRIBE_BACKGROUND_RECOVERY_FAILED")
            events.append("recovery_complete")
        async def stop(service, *args, **kwargs):
            events.append("service_stop")
            result = await original_stop(service, *args, **kwargs)
            events.append("service_stopped")
            return result
        async def close(backend, *args, **kwargs):
            events.append("backend_close")
            return await original_close(backend, *args, **kwargs)
        storage_type.setup, storage_type.close = setup, close
        BackgroundJobServiceV1.start, BackgroundJobServiceV1.stop = start, stop
        from scribe_mcp.object_store.hybrid import HybridStore
        original_probe = HybridStore.probe_remote_health
        async def offline_probe(store, **kwargs):
            optional_tasks.add(asyncio.current_task())
            events.append("optional_probe")
            optional_gate.entered.set()
            if action.startswith("core-"):
                await optional_gate.hold()
            raise OSError("https://secret.invalid/password=never-publish")
        if action.startswith("core-") or action == "outage":
            HybridStore.probe_remote_health = offline_probe
        from scribe_mcp.bridges.registry import BridgeRegistry
        original_discovery = BridgeRegistry.discover_manifests
        def offline_discovery(registry):
            optional_tasks.add(asyncio.current_task())
            raise OSError("https://secret.invalid/password=bridge-never-publish")
        if action == "core-bridge-degraded":
            BridgeRegistry.discover_manifests = offline_discovery
        startup = asyncio.create_task(server._startup())
        try:
            if action.startswith("core-"):
                await asyncio.wait_for(schema_gate.entered.wait(), timeout=3)
                sample["schema_blocked_no_ready"] = not ready and not server._startup_complete
                schema_gate.release.set()
                if action != "core-schema-failure":
                    await asyncio.wait_for(recovery_gate.entered.wait(), timeout=3)
                    sample["recovery_blocked_no_ready"] = not ready and not server._startup_complete
                    recovery_gate.release.set()
            try:
                await asyncio.wait_for(asyncio.shield(startup), timeout=5)
            except RuntimeError as exc:
                sample["required_failure"] = str(exc)
            sample["ready_ms"] = (perf_counter() - float(os.environ["SBR_PROBE_STARTED_PERF"])) * 1000
            sample["ready_signals"] = ready
            sample["startup_complete"] = server._startup_complete
            optional_gate.release.set()
            # Drain the already tracked finite health task, never wait on a sleep.
            if server._startup_complete and (action.startswith("core-") or action == "outage"):
                await asyncio.wait_for(optional_gate.entered.wait(), timeout=3)
            probe_tasks = [t for t in optional_tasks if not t.done()]
            if probe_tasks:
                await asyncio.wait_for(asyncio.gather(*probe_tasks, return_exceptions=True), timeout=3)
            sample["service_states"] = server.get_service_states()
            health = server.get_background_job_service_health()
            if inspect.isawaitable(health):
                health = await health
            sample["background_health"] = plain(health)
            server.tools.ensure_all_tools_loaded()
            sample["all_tools_rss_bytes"] = rss()
            tools = await server.app.list_tools()
            sample["core_tools_available"] = "append_entry" in {tool.name for tool in tools}
            document_store = getattr(getattr(server.app, "state", None), "document_store", None)
            remote_client = getattr(getattr(document_store, "_remote", None), "_client", None)
            if server._startup_complete and document_store is not None:
                await asyncio.wait_for(document_store.write("local-durability.md", "[test-agent] complete α\n"), timeout=4)
                sample["local_document_durable"] = await document_store.read("local-durability.md") == "[test-agent] complete α\n"
        finally:
            schema_gate.release.set(); recovery_gate.release.set(); optional_gate.release.set()
            if not startup.done():
                startup.cancel()
            await asyncio.gather(startup, return_exceptions=True)
            await asyncio.wait_for(server._shutdown(), timeout=5)
            events_after_first = list(events)
            await asyncio.wait_for(server._shutdown(), timeout=5)
            sample["idempotent_shutdown"] = events == events_after_first
            sample["events"] = events
            sample["states_after_shutdown"] = server.get_service_states()
            sample["remaining_tasks"] = [t.get_coro().__qualname__ for t in asyncio.all_tasks()
                                         if t not in baseline_tasks and not t.done()]
            sample["fd_delta"] = fds() - baseline_fds
            sample["remote_client_closed"] = remote_client is None or remote_client.is_closed
            storage_type.setup, storage_type.close = original_setup, original_close
            BackgroundJobServiceV1.start, BackgroundJobServiceV1.stop = original_start, original_stop
            HybridStore.probe_remote_health = original_probe
            BridgeRegistry.discover_manifests = original_discovery
            server.logger.removeHandler(observer)
    asyncio.run(run())
    print("SBR_SAMPLE=" + json.dumps(sample, sort_keys=True))
''')


@pytest.mark.core
@pytest.mark.regression
def test_startup_contract_is_present(test_agent):
    server = _require_startup_contract()
    assert inspect.iscoroutinefunction(server._startup)
    assert inspect.iscoroutinefunction(server._shutdown)
    for name, state in server.get_service_states().items():
        assert set(state) == _SERVICE_FIELDS
        assert state["service"] == name and state["state"] in _SERVICE_STATES


@pytest.mark.core
@pytest.mark.regression
class TestSBRImportBudget:
    def test_required_contract_is_present(self, tmp_path, test_agent):
        from scribe_mcp.utils.tokens import TokenEstimator

        assert "exact" in inspect.signature(TokenEstimator.estimate_tokens).parameters
        estimator = TokenEstimator()
        estimator.metrics_dir = tmp_path / "metrics"
        estimator.metrics_file = estimator.metrics_dir / "tokens.json"
        assert estimator.encoder is None
        assert estimator.estimate_tokens("deterministic cheap mode", exact=False) == 6
        assert estimator.encoder is None and not estimator.metrics_dir.exists()
        compile(_PROCESS_PROBE, "isolated-release-probe", "exec")


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("scenario", ("schema-failure", "recovery-failure", "optional-degraded", "bridge-degraded"))
def test_core_ready_requires_c07_and_c09_but_not_optional_services(
    tmp_path, test_agent, record_property, scenario,
):
    _require_startup_contract()
    sample = _isolated_process(tmp_path, "core-" + scenario)
    _record_evidence(record_property, "core_ready", sample)
    assert sample["schema_blocked_no_ready"]
    if scenario != "schema-failure":
        assert sample["recovery_blocked_no_ready"]
    if scenario.endswith("failure"):
        assert sample["required_failure"]
        assert sample["ready_signals"] == [] and not sample["startup_complete"]
    else:
        assert len(sample["ready_signals"]) == 1 and sample["startup_complete"]
        at_ready = sample["ready_signals"][0]
        assert at_ready["startup_complete"]
        assert at_ready["events"].index("schema_ready") < at_ready["events"].index("recovery_complete")
        assert sample["background_health"]["state"] == "running"
        assert sample["background_health"]["accepting"] is True
        assert sample["core_tools_available"] and sample["local_document_durable"]
        optional = sample["service_states"]["object_store_remote"]
        assert optional["required_for_core_ready"] is False
        assert optional["state"] == "degraded" and optional["last_error_code"]
        if scenario == "bridge-degraded":
            bridge = sample["service_states"]["bridge_init"]
            assert bridge["required_for_core_ready"] is False and bridge["state"] == "degraded"
            assert bridge["last_error_code"]
        for state in sample["service_states"].values():
            assert set(state) == _SERVICE_FIELDS and state["state"] in _SERVICE_STATES
            assert "secret.invalid" not in json.dumps(state) and "password=" not in json.dumps(state)
            if state["required_for_core_ready"]:
                assert state["state"] == "healthy"
    assert sample["idempotent_shutdown"] and not sample["remaining_tasks"]
    assert sample["fd_delta"] <= 0 and sample["remote_client_closed"]


@pytest.mark.slow
@pytest.mark.regression
def test_server_import_is_token_lazy_and_filesystem_pure(tmp_path, test_agent, record_property):
    sample = _isolated_process(tmp_path, "lazy")
    _record_evidence(record_property, "token_laziness", sample)
    assert not sample["token_module_before_use"] and sample["cheap_stays_lazy"]
    assert sample["metrics_after_import"] == sample["metrics_before"] == []
    assert sample["exact_encoder_available"] and sample["exact_module_loaded"]
    assert sample["exact_encoder_reused"] and sample["exact_tokens"] == sample["exact_repeat_tokens"] > 0


@pytest.mark.slow
@pytest.mark.regression
@pytest.mark.parametrize("profile,limit_ms", (("warm", 1000), ("cold", 1500)))
def test_server_import_and_all_tools_loaded_meet_time_and_rss_budgets(
    tmp_path, test_agent, record_property, profile, limit_ms,
):
    cache = tmp_path / "warm-cache" if profile == "warm" else None
    if cache is not None:
        _isolated_process(tmp_path / "preparation", "import", cache=cache)
    samples = [_isolated_process(tmp_path / f"sample-{n}", "import", cache=cache) for n in range(5)]
    _record_evidence(record_property, "import_budget", {"profile": profile, "samples": samples,
                     "percentile_method": "statistics.quantiles-inclusive"})
    assert _p([s["import_ms"] for s in samples], 95) <= limit_ms
    assert max(s["pre_tool_rss_bytes"] for s in samples) <= 64 * 1024 * 1024
    assert max(s["all_tools_rss_bytes"] for s in samples) <= 80 * 1024 * 1024
    assert all(s["tool_count"] > 0 and not s["token_module_before_use"] and s["all_tools_token_lazy"] for s in samples)
    assert all(s["metrics_after_import"] == [] for s in samples)


@pytest.mark.slow
@pytest.mark.regression
@pytest.mark.parametrize("profile,limit_ms", (("warm", 1500), ("cold", 2500)))
def test_process_to_ready_meets_warm_and_cold_budgets(
    tmp_path, test_agent, record_property, profile, limit_ms,
):
    _require_startup_contract()
    cache = tmp_path / "warm-cache" if profile == "warm" else None
    if cache is not None:
        _isolated_process(tmp_path / "preparation", "startup", cache=cache)
    samples = [_isolated_process(tmp_path / f"sample-{n}", "startup", cache=cache) for n in range(5)]
    _record_evidence(record_property, "ready_budget", {"profile": profile, "samples": samples,
                     "percentile_method": "statistics.quantiles-inclusive"})
    assert _p([s["ready_ms"] for s in samples], 95) <= limit_ms
    assert all(len(s["ready_signals"]) == 1 and s["startup_complete"] for s in samples)
    assert all(not s["remaining_tasks"] and s["fd_delta"] <= 0 for s in samples)


@pytest.mark.slow
@pytest.mark.regression
def test_optional_service_shutdown_is_idempotent_and_leak_free(tmp_path, test_agent, record_property):
    _require_startup_contract()
    sample = _isolated_process(tmp_path, "outage")
    _record_evidence(record_property, "shutdown", sample)
    assert sample["idempotent_shutdown"] and sample["remaining_tasks"] == []
    assert sample["fd_delta"] <= 0 and sample["remote_client_closed"]
    assert sample["events"].index("service_stop") < sample["events"].index("service_stopped")
    assert sample["events"].index("service_stopped") < sample["events"].index("backend_close")
    assert all(state["state"] == "stopped" for state in sample["states_after_shutdown"].values())


def _json_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _projected_response_fixture(tool, tmp_path, test_agent):
    dispatcher = importlib.import_module("scribe_mcp.utils.formatters.dispatcher")
    assert callable(getattr(dispatcher, "project_structured_success", None)), (
        "SBR-HOTPATH.1 missing source boundary: project_structured_success"
    )
    assert callable(getattr(dispatcher, "resolve_structured_response_depth", None)), (
        "SBR-HOTPATH.1 missing source boundary: resolve_structured_response_depth"
    )
    from scribe_mcp.shared.execution_context import (
        AgentAttributionV1, AuthorizationEvidenceV1, ResolvedProjectTargetV1, ResolvedRequestContextV1,
    )
    target = ResolvedProjectTargetV1("project-key", "budget-project", str(tmp_path),
                                    "repository-key", "caller_default", 7)
    context = ResolvedRequestContextV1(
        "a" * 64, target, 7, AgentAttributionV1(agent=test_agent), "budget-correlation", "project",
        AuthorizationEvidenceV1(source="test-fixture", verified=True, scope_refs=("repo:budget",)),
    )
    full_input = {
        "ok": True, "operation": tool, "project": {"key": target.project_key, "name": target.project_name},
        "binding": {"id": "a" * 64, "generation": 7},
        "durability": {"file": "committed", "db_mirror": "committed", "audit_id": "audit-id"},
        "artifact": {"kind": "entry", "id": "artifact-id", "path": str(tmp_path / "log.md"), "affected_count": 1},
        "correlation_id": context.correlation_id,
        "retry": {"queued": False, "retryable": False, "retry_after_ms": None},
        "reminders": [{"message": f"diagnostic {n}: complete legacy detail"} for n in range(24)],
        "recent_projects": [{"name": f"old-{n}", "root": str(tmp_path / f"old-{n}")} for n in range(12)],
        "written_line": "original complete audit line", "paths": [str(tmp_path / "log.md")],
        "timing": {"phases_ms": {"tool_body": 1.0}, "total_ms": 1.0},
    }
    # Content-bearing fixtures carry distinguishable UTF-8 and nested body data.
    bodies = {
        "read_recent": {"entries": [{"message": "complete α entry", "id": "one"}]},
        "query_entries": {"entries": [{"message": "complete β result", "id": "two"}]},
        "get_project": {"project": {"key": target.project_key, "name": target.project_name,
                                      "root": str(tmp_path), "snapshot": {"goal": "complete γ project"}}},
        "manage_docs": {"content": "complete δ document\n" * 50, "diff": "-old\n+new\n",
                        "findings": [{"code": "QUALITY_1", "message": "complete finding"}]},
    }
    full_input.update(bodies.get(tool, {}))
    if tool in ("read_recent", "query_entries"):
        full_input["pagination"] = {"page": 1, "page_size": 1, "total_count": 1, "has_next": False}
    original = copy.deepcopy(full_input)
    responses = {}
    for mode in ("structured", "compact", "structured_full", "both", "both_full"):
        depth = dispatcher.resolve_structured_response_depth(mode)
        responses[mode] = dispatcher.project_structured_success(
            full_input, tool_name=tool, resolved_request_context=context, depth=depth,
        )
    assert full_input == original, "response measurement/projection mutated authoritative full input"
    assert responses["compact"] == responses["structured"] == responses["both"]
    assert responses["both_full"] == responses["structured_full"]
    for mode in ("structured", "compact", "both"):
        receipt = responses[mode]
        assert {"schema_version", "ok", "operation", "project", "binding", "durability",
                "artifact", "correlation_id", "retry"} <= receipt.keys()
        assert receipt["schema_version"] == "scribe-structured-receipt.v1"
        assert receipt["binding"] == full_input["binding"]
        assert receipt["durability"] == full_input["durability"]
        assert receipt["correlation_id"] == context.correlation_id
    for key, value in bodies.get(tool, {}).items():
        for response in responses.values():
            assert response[key] == value, f"{tool} lost requested {key} in response projection"
    return responses


def _metadata_and_content(tool, payload):
    metadata = copy.deepcopy(payload)
    requested = {}
    # Only these explicit contract fields are excluded, never arbitrary metadata.
    for key in _REQUESTED_FIELDS.get(tool, ()):
        if key in metadata:
            requested[key] = metadata[key]
            metadata[key] = "<requested-content>"
    return metadata, requested


def _measure_response(tool, payload, *, tokenizer=None, tokenizer_info=None, wrapper=None):
    metadata, content = _metadata_and_content(tool, payload)
    metadata_bytes = _json_bytes(metadata)
    content_bytes = _json_bytes(content) if content else b""
    duplicate_wrapper = wrapper is not None and any(
        isinstance(part, dict) and part.get("type") == "text"
        and part.get("text") == _json_bytes(payload).decode()
        for part in wrapper.get("content", ())
    )
    return {
        "tool": tool, "fixture_identity": "utf8-complete-requested-content-v1",
        "source_revision": _source_revision(),
        "metadata_bytes": len(metadata_bytes), "requested_content_bytes": len(content_bytes),
        "metadata_tokens": None if tokenizer is None else tokenizer(metadata_bytes.decode()),
        "requested_content_tokens": None if tokenizer is None else (tokenizer(content_bytes.decode()) if content else 0),
        "requested_fields": sorted(content), "tokenizer": tokenizer_info,
        "structured_content_bytes": len(_json_bytes(payload)),
        "upstream_wrapper_bytes": None if wrapper is None else len(_json_bytes(wrapper)),
        "wrapper_measurement": "upstream-owned-unmeasured" if wrapper is None else "separate",
        "wrapper_verdict": "UNMEASURED" if wrapper is None else ("FAIL" if duplicate_wrapper else "PASS"),
        "byte_verdict": "PASS" if len(metadata_bytes) <= _RECEIPT_LIMITS[tool] else "FAIL",
        "full_depth_verdict": "PASS" if len(metadata_bytes) <= 16 * 1024 else "FAIL",
    }


def _ratio_verdict(receipt: dict, full: dict) -> str:
    identity = receipt.get("tokenizer")
    if not identity or not identity.get("exact") or not identity.get("version") or not identity.get("encoding"):
        return "FAIL"
    if identity != full.get("tokenizer") or receipt.get("source_revision") != full.get("source_revision"):
        return "FAIL"
    values = (receipt.get("metadata_bytes"), full.get("metadata_bytes"),
              receipt.get("metadata_tokens"), full.get("metadata_tokens"))
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in values):
        return "FAIL"
    return "PASS" if values[1] > 0 and values[3] > 0 and values[0] <= values[1] / 2 and values[2] <= values[3] / 2 else "FAIL"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("tool", tuple(_RECEIPT_LIMITS))
def test_response_projection_byte_budget_boundaries(tmp_path, test_agent, record_property, tool):
    responses = _projected_response_fixture(tool, tmp_path, test_agent)
    measured = [_measure_response(tool, responses[mode]) | {"mode": mode}
                for mode in ("structured", "compact")]
    _record_evidence(record_property, "response_bytes", {"samples": measured})
    assert all(row["byte_verdict"] == "PASS" for row in measured), measured
    # Equality is accepted, one byte over is rejected by the same measurement path.
    empty_size = _measure_response(tool, {"padding": ""})["metadata_bytes"]
    for delta in (0, 1):
        padded = {"padding": "x" * (_RECEIPT_LIMITS[tool] - empty_size + delta)}
        boundary = _measure_response(tool, padded)
        assert boundary["metadata_bytes"] == _RECEIPT_LIMITS[tool] + delta
        assert boundary["byte_verdict"] == ("PASS" if delta == 0 else "FAIL")


@pytest.mark.slow
@pytest.mark.regression
@pytest.mark.parametrize("tool", tuple(_RECEIPT_LIMITS))
def test_response_projection_local_token_counts_and_half_size_ratio(
    tmp_path, test_agent, record_property, tool, monkeypatch,
):
    responses = _projected_response_fixture(tool, tmp_path, test_agent)
    from importlib.metadata import version
    import socket
    from scribe_mcp.utils.tokens import TokenEstimator

    def deny_network(*args, **kwargs):
        raise OSError("exact tokenizer must be locally available; network disabled")
    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    estimator = TokenEstimator()
    info = estimator.get_tokenizer_info()
    assert info.get("available") and estimator.encoder is not None, "missing exact local tokenizer"
    identity = {"package": "tiktoken", "version": version("tiktoken"), "encoding": info["name"],
                "model": info["model"], "exact": True}
    count = lambda text: estimator.estimate_tokens(text, exact=True)
    full = _measure_response(tool, responses["structured_full"], tokenizer=count, tokenizer_info=identity)
    samples = []
    for mode in ("structured", "compact"):
        row = _measure_response(tool, responses[mode], tokenizer=count, tokenizer_info=identity)
        row.update(mode=mode, full_metadata_bytes=full["metadata_bytes"],
                   full_metadata_tokens=full["metadata_tokens"],
                   byte_ratio=row["metadata_bytes"] / full["metadata_bytes"],
                   token_ratio=row["metadata_tokens"] / full["metadata_tokens"])
        row["ratio_verdict"] = _ratio_verdict(row, full)
        samples.append(row)
    _record_evidence(record_property, "response_tokens", {"samples": samples})
    assert all(row["ratio_verdict"] == "PASS" and row["byte_verdict"] == "PASS" for row in samples), samples


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("tool", tuple(_RECEIPT_LIMITS))
def test_response_projection_full_depth_metadata_bound(tmp_path, test_agent, record_property, tool):
    responses = _projected_response_fixture(tool, tmp_path, test_agent)
    samples = []
    for mode in ("structured_full", "both_full"):
        row = _measure_response(tool, responses[mode]) | {"mode": mode}
        samples.append(row)
        assert responses[mode]["written_line"] == "original complete audit line"
        assert len(responses[mode]["reminders"]) == 24
        assert len(responses[mode]["recent_projects"]) == 12
    _record_evidence(record_property, "full_depth_budget", {"samples": samples})
    assert all(row["full_depth_verdict"] == "PASS" for row in samples), samples


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("tool", tuple(_REQUESTED_FIELDS))
def test_response_projection_content_exclusion_accounting_is_explicit(
    tmp_path, test_agent, record_property, tool,
):
    responses = _projected_response_fixture(tool, tmp_path, test_agent)
    payload = responses["structured"]
    before = copy.deepcopy(payload)
    metadata, requested = _metadata_and_content(tool, payload)
    assert set(requested) == set(_REQUESTED_FIELDS[tool])
    assert all(metadata[key] == "<requested-content>" for key in requested)
    assert payload == before
    wrapper = {"content": [{"type": "text", "text": _json_bytes(payload).decode()}],
               "structuredContent": payload}
    row = _measure_response(tool, payload, wrapper=wrapper)
    _record_evidence(record_property, "content_accounting", row)
    assert row["requested_content_bytes"] == len(_json_bytes(requested))
    assert row["metadata_bytes"] == len(_json_bytes(metadata))
    assert row["upstream_wrapper_bytes"] > row["structured_content_bytes"]
    assert row["wrapper_verdict"] == "FAIL"
    # A wrapper that repeats serialized JSON as text must remain a failed upstream
    # observation; it is never included in, or excused by, direct Scribe budgets.
    assert wrapper["content"][0]["text"] == _json_bytes(wrapper["structuredContent"]).decode()
    enlarged = copy.deepcopy(payload)
    first = next(iter(requested))
    enlarged[first] = {"body": "requested UTF-8 α\n" * 2000}
    bigger = _measure_response(tool, enlarged)
    assert bigger["metadata_bytes"] == row["metadata_bytes"]
    assert bigger["requested_content_bytes"] > row["requested_content_bytes"]


def _evaluate_budget_samples(profile: str, samples: list[dict], *, source_revision: str) -> dict:
    """Evaluate retained measurements, not a second runtime/effects oracle.

    Only raw reference-lane observations may produce release evidence. Injected
    records below prove equality/one-over arithmetic; they cannot certify source.
    """
    from fixtures.swarm import TIMING_PHASES

    failures = []
    def check(condition, reason):
        if not condition:
            failures.append(reason)
    check(bool(samples), "missing raw samples")
    check(all(s.get("source_revision") == source_revision for s in samples), "mixed source revisions")
    if profile in ("warm", "cold"):
        check(len(samples) >= 5, "fewer than five raw subprocess samples")
        required = {"import_ms", "ready_ms", "pre_tool_rss_bytes", "all_tools_rss_bytes",
                    "metrics_after_import", "token_module_before_use", "remaining_tasks", "fd_delta"}
        check(all(required <= s.keys() for s in samples), "missing startup measurement")
        if samples and all(required <= s.keys() for s in samples) and len(samples) >= 5:
            check(_p([s["import_ms"] for s in samples], 95) <= (1000 if profile == "warm" else 1500), "import p95")
            check(_p([s["ready_ms"] for s in samples], 95) <= (1500 if profile == "warm" else 2500), "ready p95")
            check(max(s["pre_tool_rss_bytes"] for s in samples) <= 64 * 1024 * 1024, "pre-tool RSS")
            check(max(s["all_tools_rss_bytes"] for s in samples) <= 80 * 1024 * 1024, "all-tools RSS")
            check(all(not s["metrics_after_import"] and not s["token_module_before_use"] for s in samples), "import side effects")
            check(all(not s["remaining_tasks"] and s["fd_delta"] <= 0 for s in samples), "teardown leak")
    elif profile == "object-store-outage":
        check(len(samples) >= 5, "fewer than five paired outage samples")
        required = {"baseline_ms", "outage_ms", "local_durable", "core_tools_available", "optional_state"}
        check(all(required <= s.keys() for s in samples), "missing paired outage measurement")
        if samples and all(required <= s.keys() for s in samples):
            check(all(s["outage_ms"] - s["baseline_ms"] <= 50 for s in samples), "outage foreground delta")
            check(all(s["local_durable"] and s["core_tools_available"] and s["optional_state"] == "degraded"
                      for s in samples), "optional service blocked required work")
    elif profile == "schema-32":
        check(len(samples) == 32, "schema profile requires exactly 32 raw process observations")
        required = {"role", "schema_fingerprint", "schema_version", "warm_setup_ms", "peer_wait_ms", "ready"}
        check(all(required <= s.keys() for s in samples), "missing C-07 measurement")
        if samples and all(required <= s.keys() for s in samples):
            check(sum(s["role"] == "bootstrapper" for s in samples) == 1, "schema election count")
            check(len({s["schema_fingerprint"] for s in samples}) == 1, "schema fingerprint mismatch")
            check(len({s["schema_version"] for s in samples}) == 1, "schema version mismatch")
            check(all(s["ready"] for s in samples), "schema not ready")
            check(_p([s["warm_setup_ms"] for s in samples], 95) <= 100, "schema warm setup p95")
            check(all(s["peer_wait_ms"] <= 500 for s in samples if s["role"] != "bootstrapper"), "schema peer wait")
    elif profile == "hot-path":
        check(len(samples) >= 5, "missing hot-path repetitions")
        required = {"operation", "duration_ms", "binding_reads", "project_reads", "correlation_id", "timing"}
        check(all(required <= s.keys() for s in samples), "missing hot-path measurement")
        if samples and all(required <= s.keys() for s in samples):
            operations = {s["operation"] for s in samples}
            check(set(_RECEIPT_LIMITS) <= operations, "missing synchronous operation class")
            for operation in operations:
                durations = [s.get("observed_elapsed_ms", s["duration_ms"])
                             for s in samples if s["operation"] == operation]
                check(len(durations) >= 5, "missing per-operation repetitions")
                if len(durations) >= 5:
                    check(_p(durations, 95) <= 500, f"{operation} foreground p95")
                    if operation in ("get_project", "read_recent", "query_entries"):
                        check(statistics.median(durations) <= 75, f"{operation} read p50")
                        check(_p(durations, 95) <= 250, f"{operation} read p95")
            for sample in samples:
                check(sample["binding_reads"] <= 1 and sample["project_reads"] <= 1, "excess binding/project reads")
                if "caller_bind_count" in sample:
                    check(sample["caller_bind_count"] == 1, "hot-path caller did not bind exactly once")
                timing = sample["timing"]
                fields = {"schema_version", "correlation_id", "phases_ms", "total_ms", "accounted_ratio", "slow_stages", "tripwire_exceeded"}
                check(fields <= timing.keys(), "missing C-12 fields")
                if not fields <= timing.keys():
                    continue
                phases = timing["phases_ms"]
                check(set(phases) == set(TIMING_PHASES), "missing C-12 phases")
                check(timing["schema_version"] == "call-timing-envelope.v2", "wrong C-12 schema")
                check(timing["correlation_id"] == sample["correlation_id"], "uncorrelated timing")
                check(timing["total_ms"] == sample["duration_ms"], "unexplained call duration")
                check(timing["accounted_ratio"] >= .95, "unexplained time")
                if "observed_elapsed_ms" in sample:
                    elapsed = sample["observed_elapsed_ms"]
                    check(math.isfinite(elapsed) and elapsed >= timing["total_ms"], "invalid outer call measurement")
                    accounted = timing["total_ms"] - phases.get("unaccounted", timing["total_ms"])
                    check(elapsed > 0 and accounted / elapsed >= .95, "unexplained outer call time")
                check(math.isclose(sum(phases.values()), timing["total_ms"], abs_tol=.001), "phase/total mismatch")
                if timing["total_ms"] > 0 and "unaccounted" in phases:
                    check(math.isclose(timing["accounted_ratio"],
                                       1 - phases["unaccounted"] / timing["total_ms"], abs_tol=.000001), "dishonest timing ratio")
                check(set(timing["slow_stages"]) == {name for name, ms in phases.items() if ms > 100}, "missing/extraneous stage tripwire")
                check(timing["tripwire_exceeded"] == (timing["total_ms"] > 500 or any(ms > 100 for ms in phases.values())), "missing/extraneous total tripwire")
    else:
        raise ValueError(f"unknown release budget profile: {profile}")
    return {"profile": profile, "source_revision": source_revision,
            "raw_samples": copy.deepcopy(samples), "failures": failures,
            "percentile_method": "statistics.quantiles-inclusive",
            "verdict": "FAIL" if failures else "PASS"}


def _canonical_budget_postgres(stress):
    stress.fixture_contract()
    request = _REFERENCE_REQUEST.get()
    assert request is not None, "PostgreSQL reference profiles require pytest-owned fixture context"
    created = []
    def verify_cleanup():
        if created:
            asyncio.run(stress._assert_database_gone(created[0]))
    # Match AUTH5's ordering: canonical async fixture teardown precedes the
    # independent database-gone readback. No surrogate request/finalizer exists.
    request.node.addfinalizer(verify_cleanup)
    reference = stress.canonical_postgres(request)
    created.append(reference.database_name)
    return reference


def _collect_postgres_budget_observations(profile, source_revision, workdir):
    stress = importlib.import_module("integration.test_swarm_concurrency_stress")
    assert Path(stress.__file__).resolve() == _SOURCE_ROOT / "tests/integration/test_swarm_concurrency_stress.py"
    if profile == "schema-32":
        stress.schema_contract()
    else:
        stress._runtime_contract()
    reference = _canonical_budget_postgres(stress)
    environment = stress._postgres_environment(reference)
    if profile == "schema-32":
        cold = stress._run_schema_processes(reference.dsn, "release_budget", count=32)
        warm = stress._run_schema_processes(reference.dsn, "release_budget", count=32)
        assert len(cold) == len(warm) == 32
        assert all(row["result"]["bootstrap_role"] == "fast_path" for row in warm)
        assert {(row["result"]["schema_fingerprint"], row["result"]["migration_version"])
                for row in cold} == {(row["result"]["schema_fingerprint"], row["result"]["migration_version"])
                                     for row in warm}
        samples = [{"source_revision": source_revision, "role": first["result"]["bootstrap_role"],
                    "schema_fingerprint": first["result"]["schema_fingerprint"],
                    "schema_version": first["result"]["migration_version"],
                    "warm_setup_ms": second["elapsed_ms"], "peer_wait_ms": first["result"]["wait_ms"],
                    "ready": first["result"]["ready"] and second["result"]["ready"],
                    "cold_observation": first, "warm_observation": second}
                   for first, second in zip(cold, warm)]
    else:
        async def measure():
            core = stress._runtime_contract()
            topology = stress.build_swarm_topology(workdir / "topology", agent_label="test-agent", seed=stress.SEED)
            runtime_root = workdir / "runtime"
            runtime_root.mkdir()
            task_baseline = set(asyncio.all_tasks())
            samples = []
            async with stress._postgres_world(core, topology, reference.dsn, runtime_root, "test-agent") as world:
                async def observed(caller, operation, call):
                    started = perf_counter()
                    result = await asyncio.wait_for(call, timeout=5)
                    elapsed = (perf_counter() - started) * 1000
                    assert core.payload(result)["ok"] is True, "real hot-path operation failed"
                    observation = world.samples[caller.caller_id]
                    assert len(observation.envelopes) == 1, "missing or duplicate actual C-12 envelope"
                    timing = copy.deepcopy(observation.envelopes[0])
                    samples.append({"source_revision": source_revision, "operation": operation,
                        "duration_ms": timing["total_ms"], "observed_elapsed_ms": elapsed,
                        "binding_reads": observation.reads["get_session_project"],
                        "project_reads": observation.reads["fetch_project"],
                        "caller_bind_count": world.bind_counts[caller.caller_id],
                        "correlation_id": timing["correlation_id"], "timing": timing})
                for caller in topology.callers[:5]:
                    await observed(caller, "set_project", world.bind(caller))
                    assert world.bind_counts[caller.caller_id] == 1
                    binding = await world.binding(caller)
                    for operation in ("append_entry", "get_project", "read_recent", "query_entries", "manage_docs"):
                        arguments = ({"message": f"budget:{caller.caller_id}:entry"} if operation == "append_entry"
                                     else {"action": "append", "doc": "architecture", "content": f"budget:{caller.caller_id}:document"}
                                     if operation == "manage_docs" else {})
                        await observed(caller, operation, world.call(caller, operation, **arguments))
                        assert await world.binding(caller) == binding, "hot-path call changed the caller default"
            assert world.storage._internals._pool is None, "hot-path storage handle leaked"
            assert set(asyncio.all_tasks()) == task_baseline, "hot-path task leaked"
            return samples
        samples = asyncio.run(asyncio.wait_for(measure(), timeout=180))
    return samples, environment


def _collect_reference_budget_observations(*, profile: str, source_revision: str, results_dir: Path) -> dict:
    """Take source observations directly; never deserialize purported samples.

    This is the process-measurement seam unit tests may replace. Actual calls
    remain in the coordinator-held reference lane. PostgreSQL observations reuse
    AUTH5's real helpers and the sole D5 fixture, without accepting sample files.
    """
    assert os.environ.get("SCRIBE_SWARM_DISPOSABLE") == "1", "reference execution requires disposable opt-in"
    assert source_revision == _source_revision(), "mixed source revisions"
    from importlib.metadata import version
    from scribe_mcp import __version__ as source_version

    cpu_model = platform.processor()
    if not cpu_model:
        with Path("/proc/cpuinfo").open(encoding="utf-8") as stream:
            cpu_model = next((line.partition(":")[2].strip() for line in stream
                              if line.startswith("model name")), "")
    assert cpu_model, "reference CPU model unavailable"

    environment = {
        "python_executable": sys.executable, "python_version": platform.python_version(),
        "platform": platform.platform(), "kernel": platform.release(), "machine": platform.machine(),
        "cpu_count": os.cpu_count(), "cpu_model": cpu_model,
        "memory_bytes": os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"),
        "packages": {name: version(name) for name in ("pytest", "httpx", "mcp")} | {"scribe-mcp-source": source_version},
        "storage_backend": "sqlite", "postgres": "not-contacted",
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    # Temporary process roots are separate from persisted evidence and cleaned
    # even if a finite child deadline or required source boundary fails.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="sbr-reference-", dir=results_dir) as temporary:
        root = Path(temporary)
        if profile in ("schema-32", "hot-path"):
            samples, environment["postgres"] = _collect_postgres_budget_observations(profile, source_revision, root)
            environment["storage_backend"] = "postgres"
            assert source_revision == _source_revision(), "source revision changed during measurement"
            return {"source_revision": source_revision, "raw_samples": samples,
                    "environment_fingerprint": environment, "measurement_lane": "SBR_REFERENCE_STRESS",
                    "measurement_origin": "source-process-measurement"}
        _require_startup_contract()
        cache = root / "warm-cache" if profile != "cold" else None
        if cache is not None:
            _isolated_process(root / "preparation", "startup", cache=cache)
        samples = []
        for number in range(5):
            if profile == "object-store-outage":
                baseline = _isolated_process(root / f"baseline-{number}", "startup", cache=cache)
                outage = _isolated_process(root / f"outage-{number}", "outage", cache=cache)
                samples.append({
                    "source_revision": source_revision, "baseline_ms": baseline["ready_ms"],
                    "outage_ms": outage["ready_ms"], "local_durable": outage["local_document_durable"],
                    "core_tools_available": outage["core_tools_available"],
                    "optional_state": outage["service_states"]["object_store_remote"]["state"],
                    "baseline_observation": baseline, "outage_observation": outage,
                })
            else:
                samples.append(_isolated_process(root / f"sample-{number}", "startup", cache=cache))
    assert source_revision == _source_revision(), "source revision changed during measurement"
    return {"source_revision": source_revision, "raw_samples": samples,
            "environment_fingerprint": environment, "measurement_lane": "SBR_REFERENCE_STRESS",
            "measurement_origin": "source-process-measurement"}


def run_release_budget_probe(*, profile: str, source_revision: str, results_dir: Path) -> dict:
    """Measure source through the internal collector, then persist its verdict.

    A public caller supplies no samples or provenance label. Unit tests inject
    only at the internal process seam and retain explicit NOT_RUN qualification.
    """
    assert profile in {"warm", "cold", "object-store-outage", "schema-32", "hot-path"}
    assert not (results_dir / f"{profile}-samples.json").exists(), (
        "preseeded sample files are not actual reference measurements"
    )
    envelope = _collect_reference_budget_observations(
        profile=profile, source_revision=source_revision, results_dir=results_dir,
    )
    assert envelope.get("source_revision") == source_revision == _source_revision(), "mixed source revisions"
    assert envelope.get("raw_samples"), "missing actual source observations"
    assert envelope.get("environment_fingerprint"), "missing reference environment"
    assert envelope.get("measurement_lane") == "SBR_REFERENCE_STRESS", "wrong measurement lane"
    origin = envelope.get("measurement_origin")
    assert origin in ("source-process-measurement", "unit-only-injection"), "unknown internal measurement origin"
    result = _evaluate_budget_samples(profile, envelope["raw_samples"], source_revision=source_revision)
    result.update(environment_fingerprint=envelope["environment_fingerprint"], measurement_origin=origin,
                  measurement_lane=envelope["measurement_lane"], repetitions=len(envelope["raw_samples"]),
                  reference_verdict="NOT_RUN" if origin == "unit-only-injection" else result["verdict"])
    results_dir.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    (results_dir / f"{profile}-budget.json").write_text(encoded, encoding="utf-8")
    (results_dir / "startup-budget.json").write_text(encoded, encoding="utf-8")
    return result


def _boundary_samples(profile: str) -> list[dict]:
    from fixtures.swarm import TIMING_PHASES
    base = {"source_revision": "unit-boundary"}
    if profile in ("warm", "cold"):
        base.update(import_ms=1000 if profile == "warm" else 1500,
                    ready_ms=1500 if profile == "warm" else 2500,
                    pre_tool_rss_bytes=64 * 1024 * 1024, all_tools_rss_bytes=80 * 1024 * 1024,
                    metrics_after_import=[], token_module_before_use=False, remaining_tasks=[], fd_delta=0)
    elif profile == "object-store-outage":
        base.update(baseline_ms=1, outage_ms=51, local_durable=True, core_tools_available=True, optional_state="degraded")
    elif profile == "schema-32":
        return [base | {"role": "bootstrapper" if n == 0 else "peer", "schema_fingerprint": "fingerprint",
                        "schema_version": 1, "warm_setup_ms": 100, "peer_wait_ms": 500, "ready": True}
                for n in range(32)]
    elif profile == "hot-path":
        return [base | {"operation": tool, "duration_ms": 75, "binding_reads": 1, "project_reads": 1,
                        "correlation_id": "unit-correlation", "timing": {
                            "schema_version": "call-timing-envelope.v2", "correlation_id": "unit-correlation",
                            "phases_ms": {phase: 75.0 if phase == "tool_body" else 0.0 for phase in TIMING_PHASES},
                            "total_ms": 75, "accounted_ratio": 1.0, "slow_stages": [], "tripwire_exceeded": False}}
                for tool in _RECEIPT_LIMITS for n in range(5)]
    return [copy.deepcopy(base) for _ in range(5)]


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("profile", ("warm", "cold", "object-store-outage", "schema-32", "hot-path"))
def test_budget_evidence_accepts_equality_and_rejects_missing_or_mixed_samples(profile, test_agent, record_property):
    samples = _boundary_samples(profile)
    accepted = _evaluate_budget_samples(profile, samples, source_revision="unit-boundary")
    _record_evidence(record_property, "injected_boundary_arithmetic", accepted | {"not_release_evidence": True})
    assert accepted["verdict"] == "PASS", accepted
    assert _evaluate_budget_samples(profile, [], source_revision="unit-boundary")["verdict"] == "FAIL"
    samples[0]["source_revision"] = "foreign-revision"
    assert _evaluate_budget_samples(profile, samples, source_revision="unit-boundary")["verdict"] == "FAIL"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("profile,field,bad", (
    ("warm", "import_ms", 1000.001), ("cold", "import_ms", 1500.001),
    ("warm", "ready_ms", 1500.001), ("cold", "ready_ms", 2500.001),
    ("warm", "pre_tool_rss_bytes", 64 * 1024 * 1024 + 1),
    ("warm", "all_tools_rss_bytes", 80 * 1024 * 1024 + 1),
    ("warm", "metrics_after_import", ["token_usage.json"]), ("warm", "token_module_before_use", True),
    ("warm", "remaining_tasks", ["leaked-probe"]), ("warm", "fd_delta", 1),
    ("object-store-outage", "outage_ms", 51.001), ("object-store-outage", "local_durable", False),
    ("object-store-outage", "core_tools_available", False), ("object-store-outage", "optional_state", "healthy"),
    ("schema-32", "warm_setup_ms", 100.001), ("schema-32", "peer_wait_ms", 500.001),
    ("schema-32", "ready", False), ("hot-path", "binding_reads", 2), ("hot-path", "project_reads", 2),
))
def test_budget_evidence_rejects_one_over_and_forbidden_effects(profile, field, bad, test_agent):
    samples = _boundary_samples(profile)
    for sample in samples:
        sample[field] = bad
    result = _evaluate_budget_samples(profile, samples, source_revision="unit-boundary")
    assert result["verdict"] == "FAIL" and result["failures"], result


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("mutation", ("two-bootstrap", "fingerprint", "version", "31-starts"))
def test_schema_budget_rejects_invalid_election_or_mismatched_evidence(test_agent, mutation):
    samples = _boundary_samples("schema-32")
    if mutation == "two-bootstrap":
        samples[1]["role"] = "bootstrapper"
    elif mutation == "fingerprint":
        samples[1]["schema_fingerprint"] = "different"
    elif mutation == "version":
        samples[1]["schema_version"] = 2
    else:
        samples.pop()
    assert _evaluate_budget_samples("schema-32", samples, source_revision="unit-boundary")["verdict"] == "FAIL"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("field,bad", (("accounted_ratio", .949999), ("correlation_id", "foreign"),
                                       ("slow_stages", ["tool_body"]), ("tripwire_exceeded", True),
                                       ("total_ms", 76), ("schema_version", "v1")))
def test_timing_budget_rejects_unexplained_or_uncorrelated_records(test_agent, field, bad):
    samples = _boundary_samples("hot-path")
    samples[0]["timing"][field] = bad
    assert _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")["verdict"] == "FAIL"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("total,stage,tripwire", ((100, 100, False), (100.001, 100.001, True),
                                                (500, None, False), (500.001, None, True)))
def test_timing_budget_enforces_strict_stage_and_total_tripwire_boundaries(test_agent, total, stage, tripwire):
    from fixtures.swarm import TIMING_PHASES
    samples = _boundary_samples("hot-path")
    sample = samples[0]  # append: a single outlier stays inside foreground p95
    phases = dict.fromkeys(TIMING_PHASES, 0.0)
    if stage is not None:
        phases["tool_body"] = stage
    else:
        for phase in TIMING_PHASES[:6]:
            phases[phase] = total / 6
    sample["duration_ms"] = total
    sample["timing"].update(phases_ms=phases, total_ms=total,
                            slow_stages=["tool_body"] if stage is not None and stage > 100 else [],
                            tripwire_exceeded=tripwire)
    assert _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")["verdict"] == "PASS"
    sample["timing"]["tripwire_exceeded"] = not tripwire
    result = _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")
    assert result["verdict"] == "FAIL" and "missing/extraneous total tripwire" in result["failures"]


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("operation,bound", (("append_entry", 500), ("set_project", 500),
                                          ("get_project", 250), ("read_recent", 250), ("query_entries", 250)))
def test_hot_path_budget_rejects_foreground_and_read_percentile_overages(test_agent, operation, bound):
    samples = _boundary_samples("hot-path")
    # Delay the entire operation class, keeping timing internally consistent so
    # this fails its latency contract rather than an accounting/tripwire check.
    for sample in samples:
        if sample["operation"] == operation:
            duration = bound + .001
            sample["duration_ms"] = duration
            sample["timing"].update(total_ms=duration, tripwire_exceeded=True, slow_stages=["tool_body"])
            sample["timing"]["phases_ms"]["tool_body"] = duration
    result = _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")
    assert result["verdict"] == "FAIL"
    expected = f"{operation} read p95" if bound == 250 else f"{operation} foreground p95"
    assert expected in result["failures"]


def _replace_hot_path_durations(samples, operation, durations, *, accounted_ratio=1.0):
    """Inject internally consistent observations, leaving the evaluator real."""
    from fixtures.swarm import TIMING_PHASES
    rows = [sample for sample in samples if sample["operation"] == operation]
    assert len(rows) == len(durations)
    for sample, duration in zip(rows, durations):
        phases = dict.fromkeys(TIMING_PHASES, 0.0)
        phases["unaccounted"] = duration * (1 - accounted_ratio)
        for phase in TIMING_PHASES[:6]:
            phases[phase] = duration * accounted_ratio / 6
        sample["duration_ms"] = duration
        sample["timing"].update(
            total_ms=duration, phases_ms=phases, accounted_ratio=accounted_ratio,
            slow_stages=[phase for phase, value in phases.items() if value > 100],
            tripwire_exceeded=duration > 500 or any(value > 100 for value in phases.values()),
        )


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("operation", ("get_project", "read_recent", "query_entries"))
def test_hot_path_budget_read_median_failure_is_independent_of_p95(test_agent, operation):
    samples = _boundary_samples("hot-path")
    _replace_hot_path_durations(samples, operation, [75.001] * 5)
    result = _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")
    assert result["verdict"] == "FAIL"
    assert result["failures"] == [f"{operation} read p50"]


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("operation", ("get_project", "read_recent", "query_entries"))
def test_hot_path_budget_read_p95_equality_preserves_the_median_budget(test_agent, operation):
    samples = _boundary_samples("hot-path")
    _replace_hot_path_durations(samples, operation, [75, 75, 75, 75, 293.75])
    result = _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")
    assert result["verdict"] == "PASS" and result["failures"] == []


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("operation", tuple(_RECEIPT_LIMITS))
@pytest.mark.parametrize("last_duration,over", ((625, False), (625.00125, True)))
def test_hot_path_budget_foreground_p95_boundary_is_independent_of_tripwires(test_agent, operation, last_duration, over):
    samples = _boundary_samples("hot-path")
    _replace_hot_path_durations(samples, operation, [0, 0, 0, 0, last_duration])
    result = _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")
    expected = []
    if over:
        expected.append(f"{operation} foreground p95")
    # The stricter read ceiling remains enforced at both foreground boundaries;
    # its separate known failure cannot hide a missing 500ms comparison.
    if operation in ("get_project", "read_recent", "query_entries"):
        expected.append(f"{operation} read p95")
    assert result["failures"] == expected
    assert result["verdict"] == ("FAIL" if expected else "PASS")


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("ratio,expected", ((.95, []), (.949999, ["unexplained time"] * 5)))
def test_timing_budget_accounting_equality_is_internally_consistent(test_agent, ratio, expected):
    samples = _boundary_samples("hot-path")
    _replace_hot_path_durations(samples, "append_entry", [75] * 5, accounted_ratio=ratio)
    result = _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")
    assert result["failures"] == expected
    assert result["verdict"] == ("FAIL" if expected else "PASS")


@pytest.mark.core
@pytest.mark.regression
def test_release_budget_probe_refuses_missing_and_mixed_reference_evidence(tmp_path, test_agent, monkeypatch):
    revision = _source_revision()
    envelope = _unit_budget_observations("warm", revision)
    monkeypatch.setattr(sys.modules[__name__], "_collect_reference_budget_observations", lambda **_: envelope)
    envelope["raw_samples"] = []
    with pytest.raises(AssertionError, match="missing actual source observations"):
        run_release_budget_probe(profile="warm", source_revision=revision, results_dir=tmp_path)
    envelope.update(_unit_budget_observations("warm", revision))
    envelope["source_revision"] = "foreign"
    with pytest.raises(AssertionError, match="mixed source revisions"):
        run_release_budget_probe(profile="warm", source_revision=revision, results_dir=tmp_path)
    assert not (tmp_path / "warm-budget.json").exists(), "refused evidence must not emit a passing artifact"
    assert not (tmp_path / "startup-budget.json").exists()


def _unit_budget_observations(profile, revision):
    samples = _boundary_samples(profile)
    for sample in samples:
        sample["source_revision"] = revision
    return {"source_revision": revision, "raw_samples": samples,
            "environment_fingerprint": {"unit_only": True, "python_version": "injected-unit-record"},
            "measurement_lane": "SBR_REFERENCE_STRESS", "measurement_origin": "unit-only-injection"}


@pytest.mark.core
@pytest.mark.regression
def test_release_budget_probe_rejects_forged_preseeded_reference_file(tmp_path, test_agent):
    revision = _source_revision()
    forged = _unit_budget_observations("warm", revision)
    forged["measurement_origin"] = "source-process-measurement"
    (tmp_path / "warm-samples.json").write_text(json.dumps(forged), encoding="utf-8")
    # The unmodified public seam rejects this before any internal collector can
    # execute; a self-labelled lane/current revision cannot buy a measured PASS.
    with pytest.raises(AssertionError, match="preseeded sample files are not actual reference measurements"):
        run_release_budget_probe(profile="warm", source_revision=revision, results_dir=tmp_path)
    assert not (tmp_path / "warm-budget.json").exists()
    assert not (tmp_path / "startup-budget.json").exists()


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("profile", ("warm", "cold", "object-store-outage", "schema-32", "hot-path"))
@pytest.mark.parametrize("over_budget", (False, True))
def test_release_budget_probe_serializes_unit_only_pass_and_budget_failure(
    tmp_path, test_agent, monkeypatch, profile, over_budget,
):
    revision = _source_revision()
    envelope = _unit_budget_observations(profile, revision)
    failure = None
    if over_budget:
        if profile in ("warm", "cold"):
            for sample in envelope["raw_samples"]:
                sample["import_ms"] = 1000.001 if profile == "warm" else 1500.001
            failure = "import p95"
        elif profile == "object-store-outage":
            envelope["raw_samples"][0]["outage_ms"] = 51.001
            failure = "outage foreground delta"
        elif profile == "schema-32":
            envelope["raw_samples"][1]["peer_wait_ms"] = 500.001
            failure = "schema peer wait"
        else:
            _replace_hot_path_durations(envelope["raw_samples"], "manage_docs", [500.001] * 5)
            failure = "manage_docs foreground p95"
    inputs = copy.deepcopy(envelope)
    calls = []
    def unit_measurement_seam(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(envelope)
    monkeypatch.setattr(sys.modules[__name__], "_collect_reference_budget_observations", unit_measurement_seam)
    result = run_release_budget_probe(profile=profile, source_revision=revision, results_dir=tmp_path)
    assert calls == [{"profile": profile, "source_revision": revision, "results_dir": tmp_path}]
    persisted = json.loads((tmp_path / f"{profile}-budget.json").read_text(encoding="utf-8"))
    canonical = json.loads((tmp_path / "startup-budget.json").read_text(encoding="utf-8"))
    assert result == persisted == canonical
    assert result["profile"] == profile and result["source_revision"] == revision
    assert result["raw_samples"] == inputs["raw_samples"]
    assert result["environment_fingerprint"] == inputs["environment_fingerprint"]
    assert result["repetitions"] == len(inputs["raw_samples"])
    assert result["percentile_method"] == "statistics.quantiles-inclusive"
    assert result["verdict"] == ("FAIL" if over_budget else "PASS")
    assert result["failures"] == ([failure] if over_budget else [])
    assert result["measurement_origin"] == "unit-only-injection"
    assert result["reference_verdict"] == "NOT_RUN", "unit serialization must never qualify reference performance"
    assert envelope == inputs


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("field,value,reason", (
    ("environment_fingerprint", {}, "missing reference environment"),
    ("measurement_lane", "foreign-lane", "wrong measurement lane"),
))
def test_release_budget_probe_rejects_missing_environment_and_wrong_lane(
    tmp_path, test_agent, monkeypatch, field, value, reason,
):
    revision = _source_revision()
    envelope = _unit_budget_observations("warm", revision)
    envelope[field] = value
    monkeypatch.setattr(sys.modules[__name__], "_collect_reference_budget_observations", lambda **_: envelope)
    with pytest.raises(AssertionError, match=reason):
        run_release_budget_probe(profile="warm", source_revision=revision, results_dir=tmp_path)
    assert not (tmp_path / "warm-budget.json").exists()
    assert not (tmp_path / "startup-budget.json").exists()


@pytest.mark.core
@pytest.mark.regression
def test_release_budget_probe_actual_collection_requires_disposable_opt_in(tmp_path, test_agent, monkeypatch):
    monkeypatch.delenv("SCRIBE_SWARM_DISPOSABLE", raising=False)
    with pytest.raises(AssertionError, match="reference execution requires disposable opt-in"):
        run_release_budget_probe(profile="warm", source_revision=_source_revision(), results_dir=tmp_path)
    assert not (tmp_path / "warm-budget.json").exists()
    assert not (tmp_path / "startup-budget.json").exists()


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("operation", ("get_project", "read_recent", "query_entries"))
def test_hot_path_budget_uses_outer_observed_latency_without_losing_c12_accounting(test_agent, operation):
    samples = _boundary_samples("hot-path")
    _replace_hot_path_durations(samples, operation, [75, 75, 75, 75, 293.75])
    rows = [sample for sample in samples if sample["operation"] == operation]
    for sample in rows:
        sample["observed_elapsed_ms"] = sample["duration_ms"]
    assert _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")["verdict"] == "PASS"
    rows[-1]["observed_elapsed_ms"] = 293.75125
    result = _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")
    assert result["failures"] == [f"{operation} read p95"]


@pytest.mark.core
@pytest.mark.regression
def test_timing_budget_outer_elapsed_time_cannot_hide_unaccounted_work(test_agent):
    samples = _boundary_samples("hot-path")
    samples[0]["observed_elapsed_ms"] = samples[0]["duration_ms"] / .95
    assert _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")["verdict"] == "PASS"
    samples[0]["observed_elapsed_ms"] += .001
    result = _evaluate_budget_samples("hot-path", samples, source_revision="unit-boundary")
    assert result["failures"] == ["unexplained outer call time"]


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.regression
@pytest.mark.parametrize("profile", (
    "warm", "cold", "object-store-outage",
    pytest.param("schema-32", marks=(pytest.mark.integration, pytest.mark.postgres)),
    pytest.param("hot-path", marks=(pytest.mark.integration, pytest.mark.postgres)),
))
def test_release_budget_probe_actual_reference_profile(tmp_path, test_agent, profile):
    # Explicit reference lane only. Missing C07/C12/D5/C10 production contracts
    # fail in this body; no fixture stub or caller-supplied sample file helps.
    result = run_release_budget_probe(profile=profile, source_revision=_source_revision(), results_dir=tmp_path)
    assert result["measurement_origin"] == "source-process-measurement"
    assert result["reference_verdict"] == result["verdict"] == "PASS", result


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("receipt_bytes,receipt_tokens,expected", ((512, 50, "PASS"), (513, 50, "FAIL"),
                                                                 (512, 51, "FAIL"), (512, None, "FAIL")))
def test_token_budget_half_size_boundary_requires_both_exact_measures(test_agent, receipt_bytes, receipt_tokens, expected):
    identity = {"exact": True, "version": "unit-tokenizer", "encoding": "deterministic-unit-only"}
    receipt = {"metadata_bytes": receipt_bytes, "metadata_tokens": receipt_tokens,
               "tokenizer": identity, "source_revision": "unit-boundary"}
    full = {"metadata_bytes": 1024, "metadata_tokens": 100, "tokenizer": identity,
            "source_revision": "unit-boundary"}
    assert _ratio_verdict(receipt, full) == expected
    assert _ratio_verdict(receipt | {"tokenizer": None}, full) == "FAIL"
    assert _ratio_verdict(receipt, full | {"source_revision": "foreign"}) == "FAIL"


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("delta,expected", ((0, "PASS"), (1, "FAIL")))
def test_full_depth_budget_equality_and_one_byte_over_are_explicit(test_agent, delta, expected):
    # This arithmetic fixture is intentionally injected and cannot certify the
    # real projector. The original full-depth probes above exercise that source.
    payload = {"diagnostic": ""}
    payload["diagnostic"] = "x" * (16 * 1024 - len(_json_bytes(payload)) + delta)
    measured = _measure_response("get_project", payload)
    assert measured["metadata_bytes"] == 16 * 1024 + delta
    assert measured["full_depth_verdict"] == expected
