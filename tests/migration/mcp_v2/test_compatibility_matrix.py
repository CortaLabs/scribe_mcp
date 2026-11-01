from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

import pytest

pytestmark = [pytest.mark.core, pytest.mark.mcp_v2]
MODERN_REVISION = "2026-07-28"
LEGACY_REVISION = "2025-11-25"
MATRIX_PATH = "tests/migration/mcp_v2/test_compatibility_matrix.py"
SECURITY_PATH = "tests/security/test_session_provenance.py"
AUTH_PATH = "tests/security/test_transport_authorization.py"

# Exact eleven-row retirement ledger. Historical labels are discriminants;
# they never select an SDK1 interpreter. Current canaries remain independent.
ROW_CONTRACTS = (
    ("test_matrix_has_one_architecture_tied_decision_for_every_t01_t20",
     "test_matrix_has_one_architecture_tied_decision_for_every_t01_t20",
     tuple(f"T{n:02d}" for n in range(1, 21)), "outcome coverage; missing or failed is BLOCK"),
    ("test_exact_candidate_modern_stdio_real_client",
     "test_exact_candidate_modern_stdio_real_client",
     ("T04", "T12", "T14", "T15", "T18", "T19", "T20"), "SDK2.3/current complete catalog and schema"),
    ("test_named_legacy_stdio_negotiates_frozen_revision_regression[forced-v2]",
     "test_retired_stdio_wire_rejected_before_effects[forced-v2]",
     ("T05", "T18", "T20"), "old initialize denied with -32022; populated real state unchanged"),
    ("test_named_legacy_stdio_negotiates_frozen_revision_regression[pre-v2-1.26.0]",
     "test_retired_stdio_wire_rejected_before_effects[pre-v2-1.26.0]",
     ("T05", "T14", "T20"), "raw old tools/list denied; no SDK1 or fallback"),
    ("test_modern_http_real_clients_are_isolated_and_negatives_never_dispatch",
     "test_modern_http_real_clients_are_isolated_and_negatives_never_dispatch",
     ("T01", "T02", "T03", "T04", "T06", "T07", "T08", "T12", "T13", "T15", "T16", "T19"),
     "internal loopback success plus public operator denial; two bindings/schema/reconnect/zero effects"),
    ("test_pre_v2_client_uses_retained_sse_and_messages_and_listener_is_cleaned",
     "test_retired_http_paths_rejected_and_listener_cleaned",
     ("T01", "T02", "T05", "T14", "T18", "T20"), "both fixed profiles: four old paths x GET/POST/auth/Origin; precedence/effects/rebind"),
    ("test_source_rollback_shadow_restores_prior_dependency_without_mutating_worktree",
     "test_source_rollback_shadow_restores_prior_dependency_without_mutating_worktree",
     ("T05", "T18", "T20"), "historical source/CLI shadow only; current policy modern-only"),
    ("test_public_stdio_binding_round_trip_isolated[modern-auto-2026-07-28]",
     "test_public_stdio_binding_round_trip_isolated[modern-auto-2026-07-28]",
     ("T06", "T07", "T12", "T14", "T20"), "explicit-current bind/read/append/read; exact entry/identity/default/generation"),
    ("test_public_stdio_binding_round_trip_isolated[legacy-legacy-2025-11-25]",
     "test_retired_stdio_wire_rejected_before_effects[binding-round-trip-legacy]",
     ("T05", "T06", "T20"), "old bind envelope denied before effects"),
    ("test_public_stdio_first_call_does_not_require_discovery[modern-auto-2026-07-28]",
     "test_public_stdio_first_call_does_not_require_discovery[modern-auto-2026-07-28]",
     ("T07", "T12", "T18", "T20"), "first set_project with no discover/list/initialize"),
    ("test_public_stdio_first_call_does_not_require_discovery[legacy-legacy-2025-11-25]",
     "test_retired_stdio_wire_rejected_before_effects[first-call-legacy]",
     ("T05", "T18", "T20"), "old first-call envelope denied before effects"),
)
ROW_ADDITIONAL_NODES = {
    "test_modern_http_real_clients_are_isolated_and_negatives_never_dispatch": (
        "test_public_http_local_operator_denial_before_effects",),
    "test_retired_http_paths_rejected_and_listener_cleaned": (
        "test_retired_public_http_paths_rejected_and_listener_cleaned",),
}

FROZEN_EXCLUSIONS = {
    "T09": "architecture excludes cross-worker continuity; wrong-worker fails closed",
    "T10": "MRTR/input request state is an explicit non-goal",
    "T11": "selected auth model is operator-root bearer, not scoped multi-user OAuth",
    "T17": "no automatic mutating replay; progress is supported; timeout/drain fail closed",
}
# Extra producers retain the public security facts; no gate is inferred from a
# prose label or an absent test. The aggregate's JUnit must contain every node.
T_REQUIRED_NODES = {
    f"T{n:02d}": tuple(MATRIX_PATH + "::" + new for _, new, keys, _ in ROW_CONTRACTS[1:]
                       if f"T{n:02d}" in keys)
    for n in range(1, 21) if f"T{n:02d}" not in FROZEN_EXCLUSIONS
}
for _, primary, keys, _ in ROW_CONTRACTS:
    for extra in ROW_ADDITIONAL_NODES.get(primary, ()):
        for key in keys:
            if key in T_REQUIRED_NODES:
                T_REQUIRED_NODES[key] += (MATRIX_PATH + "::" + extra,)
for key in ("T01", "T02", "T05", "T12", "T18", "T20"):
    T_REQUIRED_NODES[key] += tuple(
        MATRIX_PATH + "::test_public_http_no_effect_guard_detects_ingress_faults[" + fault + "]"
        for fault in ("omit-auth", "restore-old-route"))

T_REQUIRED_NODES["T08"] += tuple(SECURITY_PATH + "::" + name for name in (
    "test_modern_http_application_handle_is_server_minted_and_principal_bound",
    "test_modern_http_application_handle_rejects_missing_unknown_and_revoked",
    "test_modern_http_application_handle_rejects_expired"))
T_REQUIRED_NODES["T16"] += (
    MATRIX_PATH + "::test_spike_secret_guard_rejects_server_logs_and_aggregate_receipts",)
T_REQUIRED_NODES["T12"] += tuple(AUTH_PATH + "::" + name for name in (
    "test_public_exported_tool_invoke_denies_local_operator_tools_before_dispatch",
    "test_native_modern_tool_call_keeps_remote_authorization"))
T_REQUIRED_NODES["T13"] += (
    SECURITY_PATH + "::test_public_release_ignores_single_untrusted_identifier_and_uses_runtime_transport",
    AUTH_PATH + "::test_native_modern_dispatch_consumes_only_ingress_attached_identity")
T_REQUIRED_NODES["T19"] += tuple(
    AUTH_PATH + "::test_doctor_selector_modes_are_denied_before_remote_dispatch[" + f"{context}-{mode}-{profile}]"
    for context in ("empty_context", "forged_local_context")
    for mode in ("None", "deferred", "full", "invalid") for profile in ("public", "internal"))


def matrix_rows(outcomes: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Reduce actual exact node outcomes; historical evidence cannot grant PASS."""
    rows = {}
    for number in range(1, 21):
        key = f"T{number:02d}"
        if key in FROZEN_EXCLUSIONS:
            rows[key] = {"status": "N/A", "evidence": FROZEN_EXCLUSIONS[key], "nodes": []}
            continue
        required = T_REQUIRED_NODES[key]
        missing = [node for node in required if node not in outcomes]
        failed = [node for node in required if outcomes.get(node) != "PASS" and node not in missing]
        rows[key] = {"status": "PASS" if required and not missing and not failed else "BLOCK",
                     "evidence": "actual exact-node outcomes", "nodes": list(required),
                     "missing": missing, "failed": failed}
    return rows


# Compatibility API remains a tuple mapping, but unexecuted facts are BLOCK.
MATRIX_EVIDENCE = {key: (row["status"], row["evidence"]) for key, row in matrix_rows({}).items()}

COMMON_PROBE = r'''
import anyio, json, os, sys
from importlib.metadata import version
from pathlib import Path
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError
import scribe_mcp, mcp

def decoded(result):
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    for block in result.content:
        text = getattr(block, "text", "")
        try:
            value = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return {"text": "\n".join(getattr(block, "text", "") for block in result.content)}

def provenance():
    return {"sdk": version("mcp"), "executable": sys.executable,
            "source": scribe_mcp.__file__, "sdk_origin": mcp.__file__}

async def call(client, name, arguments):
    try:
        with anyio.fail_after(10):
            result = await client.call_tool(name, arguments)
    except MCPError as error:
        # Preserve an actual server RPC denial as product evidence, not a
        # subprocess/JSON setup failure. Positive assertions still reject it.
        return {"tool": name, "is_error": True, "data": {"ok": False,
                "rpc_code": error.code, "rpc_data": error.error.data,
                "message": error.error.message}, "text": [], "structured": None}
    return {"tool": name, "is_error": result.is_error, "data": decoded(result),
            "text": [getattr(item, "text", "") for item in result.content],
            "structured": getattr(result, "structured_content", None)}

def params():
    return StdioServerParameters(command=sys.executable, args=["-m", "scribe_mcp"],
                                 env=dict(os.environ), cwd=os.getcwd())
'''

PUBLIC_BINDING_STDIO_PROBE = COMMON_PROBE + r'''
async def main():
    steps = []
    discovered = None
    with anyio.fail_after(80):
        async with Client(stdio_client(params()), mode="2026-07-28", cache=None,
                          read_timeout_seconds=10) as client:
            if os.environ["SBR_PRELOAD_TOOLS"] == "1":
                await client.session.send_discover("2026-07-28")
                catalog = await client.list_tools(cache_mode="refresh")
                discovered = sorted(tool.name for tool in catalog.tools)
            calls = [("set_project", {"agent": os.environ["MCPV2_TEST_AGENT"],
                       "name": "stdio-binding", "root": os.environ["MCPV2_REPO_A"], "format": "structured"}),
                     ("read_recent", {"agent": os.environ["MCPV2_TEST_AGENT"], "n": 10, "format": "structured"}),
                     ("append_entry", {"agent": os.environ["MCPV2_TEST_AGENT"],
                       "project": "stdio-binding", "message": os.environ["SBR_CANARY_MESSAGE"],
                       "status": "info", "format": "structured"}),
                     ("read_recent", {"agent": os.environ["MCPV2_TEST_AGENT"], "n": 10, "format": "structured"})]
            if os.environ["SBR_PRELOAD_TOOLS"] != "1":
                calls = calls[:1]
            for name, arguments in calls:
                steps.append(await call(client, name, arguments))
            revision = client.session.protocol_version
    events = [json.loads(line) for line in Path(os.environ["MCPV2_OBSERVATIONS"]).read_text().splitlines()]
    print(json.dumps({**provenance(), "revision": revision, "steps": steps, "discovered": discovered,
                      "events": events},
                     sort_keys=True))
anyio.run(main)
'''

MODERN_STDIO_PROBE = COMMON_PROBE + r'''
async def main():
    with anyio.fail_after(80):
        async with Client(stdio_client(params()), mode="2026-07-28", cache=None,
                          read_timeout_seconds=10) as client:
            discovery = await client.session.send_discover("2026-07-28")
            catalog = await client.list_tools(cache_mode="refresh")
            tools = {tool.name: tool.model_dump(mode="json") for tool in catalog.tools}
            # Current schema, structured/text and error facts use actual SDK.
            sample = Path(os.environ["MCPV2_REPO_A"]) / "catalog-proof.txt"
            sample.write_text("current-catalog-proof\n")
            good = await call(client, "read_file", {"agent": os.environ["MCPV2_TEST_AGENT"],
                              "path": str(sample), "mode": "full"})
            bad = await call(client, "read_file", {"agent": os.environ["MCPV2_TEST_AGENT"],
                             "path": str(sample) + ".missing", "mode": "full"})
            denied = await call(client, "delete_project", {"agent": os.environ["MCPV2_TEST_AGENT"],
                                "name": "never-created"})
            result = {**provenance(), "revision": client.session.protocol_version,
                      "tool_count": len(tools), "tools": tools,
                      "private_cache": discovery.get("cacheScope", discovery.get("cache_scope")) == "private",
                      "good": good, "bad": bad, "denied": denied}
    print(json.dumps(result, sort_keys=True))
anyio.run(main)
'''

RETIRED_STDIO_PROBE = r'''
import json, os, selectors, subprocess, sys, time
from pathlib import Path
from importlib.metadata import version

def main():
    # Raw obsolete envelopes are intentional: no obsolete client is installed.
    process = subprocess.Popen([sys.executable, "-m", "scribe_mcp"], env=dict(os.environ),
        cwd=os.getcwd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)
    sequence = 0
    pending = b""
    barriers = []
    def barrier():
        reply = request("tools/list", {})
        assert "result" in reply, reply
        events = [json.loads(line) for line in Path(os.environ["MCPV2_OBSERVATIONS"]).read_text().splitlines()]
        assert events[-1]["method"] == "tools/list"
        barriers.append(events[-1]["after"])
    def request(method, arguments, revision="2026-07-28"):
        nonlocal sequence, pending
        sequence += 1
        params = dict(arguments)
        params["_meta"] = {"io.modelcontextprotocol/protocolVersion": revision,
                          "io.modelcontextprotocol/clientCapabilities": {},
                          "io.modelcontextprotocol/clientInfo": {"name": "matrix-wire", "version": "1"}}
        body = {"jsonrpc": "2.0", "id": sequence, "method": method, "params": params}
        process.stdin.write(json.dumps(body) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 10
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while b"\n" not in pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("raw stdio request exceeded call10")
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("real stdio child closed before replying")
                pending += chunk
        line, pending = pending.split(b"\n", 1)
        result = json.loads(line)
        assert result.get("id") == sequence, result
        return result
    try:
        seeded = request("tools/call", {"name": "set_project", "arguments": {
            "agent": os.environ["MCPV2_TEST_AGENT"], "name": "negative-seed", "root": os.environ["MCPV2_REPO_A"]}})
        request("tools/call", {"name": "append_entry", "arguments": {
            "agent": os.environ["MCPV2_TEST_AGENT"], "message": "populated-negative-state", "project": "negative-seed"}})
        barrier()
        label = os.environ["MCPV2_NEGATIVE_LABEL"]
        if label == "forced-v2":
            denied = request("initialize", {"protocolVersion": "2025-11-25",
                "capabilities": {}, "clientInfo": {"name": "old-envelope", "version": "1"}}, "2025-11-25")
        elif label == "pre-v2-1.26.0":
            denied = request("tools/list", {}, "2025-11-25")
        else:
            denied = request("tools/call", {"name": "set_project", "arguments": {
                "agent": os.environ["MCPV2_TEST_AGENT"], "name": "retired-must-not-bind",
                "root": os.environ["MCPV2_REPO_B"]}}, "2025-11-25")
        barrier()
        # A real authorized rebind proves snapshots/counters detect mutation.
        changed = request("tools/call", {"name": "set_project", "arguments": {
            "agent": os.environ["MCPV2_TEST_AGENT"], "name": "sensitivity-rebind", "root": os.environ["MCPV2_REPO_B"]}})
        barrier()
        process.stdin.close()
        process.wait(timeout=10)
        stderr = process.stderr.read()
        assert process.returncode == 0, stderr
        events = [json.loads(line) for line in Path(os.environ["MCPV2_OBSERVATIONS"]).read_text().splitlines()]
        print(json.dumps({"sdk": version("mcp"), "seeded": seeded, "denied": denied, "changed": changed,
                          "events": events, "barriers": barriers}, sort_keys=True))
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        sys.stderr.write(process.stderr.read())
main()
'''


def _assert_origin(payload: dict[str, Any], root: Path) -> None:
    assert payload["sdk"] == "2.3.0"
    source = Path(payload["source"]).resolve()
    if os.environ.get("MCPV2_ISOLATED_INSTALL") == "1":
        assert source.is_relative_to(Path(payload["executable"]).parent.parent.resolve())
        assert not source.is_relative_to(root / "src")
    else:
        assert source == root / "src/scribe_mcp/__init__.py"


def _assert_binding_steps(steps: list[dict[str, Any]], message: str, discover: bool) -> None:
    identities, bindings = [], []
    for step in steps:
        data = step["data"]
        assert not step["is_error"] and data.get("ok") is not False, (step["tool"], data)
        project, receipt = data.get("project", {}), data.get("binding_receipt", {})
        key = project.get("key") or project.get("project_key") or receipt.get("project_key") or data.get("project_key")
        name = project.get("name") or receipt.get("project_name") or data.get("project_name")
        assert isinstance(key, str) and key and name == "stdio-binding", ("C11/X project receipt", step)
        identities.append((key, name))
        binding = data.get("binding", {})
        identity = binding.get("id") or receipt.get("caller_session_key_hash")
        generation = binding.get("generation") or receipt.get("binding_generation")
        assert isinstance(identity, str) and len(identity) == 64, ("C11/X session identity", step)
        assert isinstance(generation, int) and generation > 0, ("C11/X generation", step)
        bindings.append((identity, generation))
    expected = ["set_project", "read_recent", "append_entry", "read_recent"] if discover else ["set_project"]
    assert [step["tool"] for step in steps] == expected
    assert identities == [identities[0]] * len(expected)
    assert bindings == [bindings[0]] * len(expected)
    if discover:
        entries = steps[-1]["data"]["entries"]
        assert sum(entry.get("message") == message for entry in entries) == 1, entries
        appended = steps[2]["data"]
        entry_id = appended.get("artifact", {}).get("id") or appended.get("id")
        assert entry_id and sum(entry.get("id") == entry_id for entry in entries) == 1


def _public_stdio_binding_round_trip(
    era: str, mode: str, revision: str, test_agent: str, candidate_python: Path,
    mcp_v2_repo_root: Path, isolated_runtime_env: dict[str, str], json_probe: Callable[..., Any],
    *, discover: bool,
) -> None:
    env = dict(isolated_runtime_env)
    message = f"{era}-public-stdio-retained-entry"
    env.update(SBR_PRELOAD_TOOLS="1" if discover else "0", SBR_CANARY_MESSAGE=message,
               MCPV2_TEST_AGENT=test_agent)
    result = json_probe(candidate_python, PUBLIC_BINDING_STDIO_PROBE, cwd=mcp_v2_repo_root, env=env)
    assert result.returncode == 0, f"SDK/probe setup defect: {result.stderr}"
    observed = result.payload
    _assert_origin(observed, mcp_v2_repo_root)
    assert observed["revision"] == revision
    if discover:
        assert "set_project" in observed["discovered"]
    else:
        assert observed["discovered"] is None
    _assert_binding_steps(observed["steps"], message, discover)
    operations = [event for event in observed["events"] if event.get("method") == "tools/call"]
    defaults = [event["after"]["bindings"] for event in operations]
    assert len(defaults) == len(observed["steps"]) and all(defaults), "C11/X authoritative defaults absent"
    assert defaults == [defaults[0]] * len(defaults), "C11/X persistent default/generation drift"


@pytest.mark.regression
@pytest.mark.parametrize("era,mode,revision", [("modern", "auto", MODERN_REVISION)])
def test_public_stdio_binding_round_trip_isolated(
    era, mode, revision, test_agent, candidate_python, mcp_v2_repo_root, observed_runtime_env, json_probe,
):
    _public_stdio_binding_round_trip(era, mode, revision, test_agent, candidate_python,
        mcp_v2_repo_root, observed_runtime_env, json_probe, discover=True)


@pytest.mark.regression
@pytest.mark.parametrize("era,mode,revision", [("modern", "auto", MODERN_REVISION)])
def test_public_stdio_first_call_does_not_require_discovery(
    era, mode, revision, test_agent, candidate_python, mcp_v2_repo_root, observed_runtime_env, json_probe,
):
    _public_stdio_binding_round_trip(era, mode, revision, test_agent, candidate_python,
        mcp_v2_repo_root, observed_runtime_env, json_probe, discover=False)


def test_matrix_has_one_architecture_tied_decision_for_every_t01_t20(test_agent) -> None:
    assert len(ROW_CONTRACTS) == 11
    assert len({row[0] for row in ROW_CONTRACTS}) == len({row[1] for row in ROW_CONTRACTS}) == 11
    assert set(matrix_rows({})) == {f"T{n:02d}" for n in range(1, 21)}
    assert all(row["status"] == ("N/A" if key in FROZEN_EXCLUSIONS else "BLOCK")
               for key, row in matrix_rows({}).items())
    outcomes = {node: "PASS" for nodes in T_REQUIRED_NODES.values() for node in nodes}
    assert all(row["status"] in {"PASS", "N/A"} for row in matrix_rows(outcomes).values())
    for key, required in T_REQUIRED_NODES.items():
        assert required
        for node in required:
            for failed in ("BLOCK", "SKIP", "XFAIL"):
                assert matrix_rows({**outcomes, node: failed})[key]["status"] == "BLOCK"
            assert matrix_rows({k: v for k, v in outcomes.items() if k != node})[key]["status"] == "BLOCK"


def test_exact_candidate_modern_stdio_real_client(
    candidate_python, mcp_v2_repo_root, isolated_runtime_env, json_probe, test_agent,
):
    result = json_probe(candidate_python, MODERN_STDIO_PROBE, cwd=mcp_v2_repo_root, env=isolated_runtime_env)
    assert result.returncode == 0, result.stderr
    data = result.payload
    _assert_origin(data, mcp_v2_repo_root)
    assert data["revision"] == MODERN_REVISION and data["private_cache"]
    assert data["tool_count"] == 35
    schema = data["tools"]["read_file"].get("input_schema", data["tools"]["read_file"].get("inputSchema"))
    assert {"agent", "path", "mode"} <= schema["properties"].keys()
    assert not data["good"]["is_error"]
    assert "current-catalog-proof" in "\n".join(data["good"]["text"])
    assert isinstance(data["good"]["structured"], dict)
    assert data["bad"]["is_error"], data["bad"]
    assert data["denied"]["is_error"], data["denied"]
    assert "remote" in json.dumps(data["denied"]).lower() or "denied" in json.dumps(data["denied"]).lower()


@pytest.mark.regression
@pytest.mark.parametrize("client_kind", ["forced-v2", "pre-v2-1.26.0",
                                        "binding-round-trip-legacy", "first-call-legacy"])
def test_retired_stdio_wire_rejected_before_effects(
    client_kind, candidate_python, mcp_v2_repo_root, observed_runtime_env, json_probe, test_agent,
):
    env = {**observed_runtime_env, "MCPV2_NEGATIVE_LABEL": client_kind}
    result = json_probe(candidate_python, RETIRED_STDIO_PROBE, cwd=mcp_v2_repo_root, env=env)
    assert result.returncode == 0, result.stderr
    data = result.payload
    assert data["sdk"] == "2.3.0"
    assert data["denied"]["error"]["code"] == -32022
    assert data["denied"]["error"]["data"]["supported"] == [MODERN_REVISION]
    barriers = data["barriers"]
    assert len(barriers) == 3, "observer barriers missing"
    before, after, changed = barriers
    assert before["database"] and before["state"]["projects"], before
    assert before["bindings"] and before["leases"] and before["stdio"], before
    assert before == after, (client_kind, before, after)
    assert after != changed
    assert changed["counters"]["dispatch"] > after["counters"]["dispatch"]
    assert after["state"] != changed["state"]


@contextmanager
def _http_child(python: Path, root: Path, env: dict[str, str]):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    child_env = {**env, "SCRIBE_TRANSPORT": "sse", "SCRIBE_TRANSPORT_PORT": str(port), "SCRIBE_TRANSPORT_HOST": "127.0.0.1"}
    log_path = Path(env["MCPV2_OBSERVATIONS"]).with_suffix(".stderr")
    log = log_path.open("w")
    process = subprocess.Popen(
        [str(python), "-m", "scribe_mcp", "--transport", "sse", "--host", "127.0.0.1", "--port", str(port)],
        cwd=root, env=child_env, stdout=subprocess.DEVNULL, stderr=log, text=True,
        start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None:
                process.communicate(timeout=5)
                pytest.fail(f"HTTP child exited before ready20: {log_path.read_text()}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                if time.monotonic() >= deadline:
                    pytest.fail("HTTP child did not become ready within20")
                time.sleep(0.1)
        yield f"http://127.0.0.1:{port}"
    finally:
        import signal
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
        log.close()
        # Rebind even if the body/probe failed. No assertion can skip cleanup.
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))


MODERN_HTTP_PROBE = COMMON_PROBE + r'''
import httpx2
from contextlib import asynccontextmanager
from mcp.client.streamable_http import streamable_http_client

async def main():
    base = os.environ["MCPV2_HTTP_BASE"]
    token = os.environ["SCRIBE_TRANSPORT_AUTH_TOKEN"]
    auth = {"authorization": "Bearer " + token, "origin": "https://trusted.example"}
    @asynccontextmanager
    async def open_client(handle=None):
        state = {}
        http_client = None
        async def capture(response):
            minted = response.headers.get("scribe-application-handle")
            if minted:
                state["handle"] = minted
                http_client.headers["scribe-application-handle"] = minted
        headers = dict(auth)
        if handle:
            headers["scribe-application-handle"] = handle
        async with httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(10),
                     event_hooks={"response": [capture]}) as http_client:
            async with Client(streamable_http_client(base + "/mcp", http_client=http_client,
                              terminate_on_close=False), mode="2026-07-28", cache=None,
                              read_timeout_seconds=10) as client:
                discovery = await client.session.send_discover("2026-07-28")
                catalog = await client.list_tools(cache_mode="refresh")
                yield client, handle or state["handle"], discovery, catalog
    async with httpx2.AsyncClient(headers=auth, timeout=httpx2.Timeout(10)) as raw:
        async def snapshot():
            response = await raw.get(base + "/__matrix/state")
            assert response.status_code == 200, response.text
            return response.json()
        with anyio.fail_after(110):
            async with open_client() as (a, ha, da, ta):
                async with open_client() as (b, hb, db, tb):
                    bound_a = await call(a, "set_project", {"agent": os.environ["MCPV2_TEST_AGENT"],
                        "name": "project-a", "root": os.environ["MCPV2_REPO_A"]})
                    bound_b = await call(b, "set_project", {"agent": os.environ["MCPV2_TEST_AGENT"],
                        "name": "project-b", "root": os.environ["MCPV2_REPO_B"]})
                    pa = await call(a, "get_project", {"agent": os.environ["MCPV2_TEST_AGENT"]})
                    pb = await call(b, "get_project", {"agent": os.environ["MCPV2_TEST_AGENT"]})
                    appended = await call(a, "append_entry", {"agent": os.environ["MCPV2_TEST_AGENT"],
                              "project": "project-a", "message": "populated-http-state"})
                    sample = Path(os.environ["MCPV2_REPO_A"]) / "http-current-proof.txt"
                    sample.write_text("current-http-proof\n")
                    good = await call(a, "read_file", {"agent": os.environ["MCPV2_TEST_AGENT"],
                                      "path": str(sample), "mode": "full"})
                    bad = await call(a, "read_file", {"agent": os.environ["MCPV2_TEST_AGENT"],
                                     "path": str(sample) + ".missing", "mode": "full"})
                    schemas_a = {t.name: t.model_dump(mode="json") for t in ta.tools}
                    schemas_b = {t.name: t.model_dump(mode="json") for t in tb.tools}
            async with open_client(ha) as (again, _, _, _):
                reconnected = await call(again, "get_project", {"agent": os.environ["MCPV2_TEST_AGENT"]})
            before = await snapshot()
            secret = "test-mcpv2-secret-canary-9f2aa89e"
            negatives = []
            cases = [
                ({}, {"jsonrpc":"2.0", "id":1, "method":"tools/call",
                      "params":{"name":"set_project","arguments":{"agent":secret}}}),
                ({"authorization":"Bearer "+token,"origin":"https://evil.example"},
                    {"jsonrpc":"2.0","id":2,"method":"tools/list"}),
                ({**auth, "mcp-protocol-version":"2099-01-01", "mcp-method":"tools/list"},
                    {"jsonrpc":"2.0","id":3,"method":"tools/list","params":{"_meta":{
                     "io.modelcontextprotocol/protocolVersion":"2099-01-01",
                     "io.modelcontextprotocol/clientCapabilities":{}}}}),
                ({**auth, "mcp-protocol-version":"2026-07-28"},
                    {"jsonrpc":"2.0","id":4,"method":"initialize","params":{"protocolVersion":"2025-11-25",
                     "clientInfo":{"name":"old","version":"1"},"capabilities":{}}}),
            ]
            # A separate unauthenticated client prevents inherited bearer headers.
            async with httpx2.AsyncClient(timeout=httpx2.Timeout(10)) as denial_client:
                for headers, body in cases:
                    response = await denial_client.post(base + "/mcp", headers=headers, json=body)
                    negatives.append({"status":response.status_code,"body":response.json(),
                                      "redirect":response.headers.get("location")})
            after = await snapshot()
            async with open_client(ha) as (again, _, _, _):
                await call(again, "set_project", {"agent": os.environ["MCPV2_TEST_AGENT"],
                           "name": "sensitivity-http", "root": os.environ["MCPV2_REPO_A"]})
            changed = await snapshot()
            print(json.dumps({**provenance(), "revision":"2026-07-28",
                "handles_distinct":ha != hb, "bound":[bound_a,bound_b], "projects":[pa,pb],
                "appended":appended, "good":good, "bad":bad,
                "reconnected":reconnected, "schema_parity":schemas_a == schemas_b,
                "private_cache":da.get("cacheScope", da.get("cache_scope")) == db.get("cacheScope", db.get("cache_scope")) == "private",
                "tools":schemas_a, "negatives":negatives, "before":before, "after":after,
                "changed":changed, "canary_redacted":secret not in json.dumps(negatives)}, sort_keys=True))
anyio.run(main)
'''


def test_modern_http_real_clients_are_isolated_and_negatives_never_dispatch(
    candidate_python, mcp_v2_repo_root, observed_internal_runtime_env, json_probe, test_agent, request, isolated_runtime_env,
):
    assert isolated_runtime_env["SCRIBE_RELEASE_PROFILE"] == "public"
    with _http_child(candidate_python, mcp_v2_repo_root, observed_internal_runtime_env) as base:
        result = json_probe(candidate_python, MODERN_HTTP_PROBE, cwd=mcp_v2_repo_root,
                            env={**observed_internal_runtime_env, "MCPV2_HTTP_BASE": base}, timeout=120)
    _assert_http_secret_evidence(mcp_v2_repo_root, request, observed_internal_runtime_env)
    assert result.returncode == 0, result.stderr
    data = result.payload
    _assert_origin(data, mcp_v2_repo_root)
    _assert_http_profile(data, "internal")
    assert data["revision"] == MODERN_REVISION and data["handles_distinct"]
    failures = [value for value in (*data["bound"], *data["projects"], data["reconnected"])
                if value["is_error"] or value["data"].get("ok") is False]
    assert failures == [], ("SOURCE_X_INTERNAL_HTTP_CURRENT_AUTHORITY", failures)
    assert [value["data"]["project"]["name"] for value in data["projects"]] == ["project-a", "project-b"]
    assert data["reconnected"]["data"]["project"]["name"] == "project-a"
    assert data["schema_parity"] and data["private_cache"]
    assert len(data["tools"]) == 35
    assert [r["status"] for r in data["negatives"]] == [401, 403, 400, 400]
    assert [r["body"]["type"] for r in data["negatives"]] == [
        "Unauthorized", "InvalidOrigin", "UnsupportedProtocolVersion", "HeaderMismatch"]
    assert all(r["redirect"] is None for r in data["negatives"])
    assert data["canary_redacted"]
    assert data["before"]["bindings"] and data["before"]["handles"] and data["before"]["database"]
    _assert_no_effects(data["before"], data["after"])
    assert not data["good"]["is_error"] and "current-http-proof" in "\n".join(data["good"]["text"])
    assert isinstance(data["good"]["structured"], dict), ("C04 structured HTTP result", data["good"])
    assert data["bad"]["is_error"]
    assert not data["appended"]["is_error"]
    schema = data["tools"]["read_file"].get("input_schema", data["tools"]["read_file"].get("inputSchema"))
    assert {"agent", "path", "mode"} <= schema["properties"].keys()
    records = list(data["before"]["bindings"].values())
    assert {item["project_name"] for item in records} >= {"project-a", "project-b"}
    assert all(item["binding_generation"] > 0 for item in records)
    assert data["after"] != data["changed"]


RETIRED_HTTP_PROBE = COMMON_PROBE + r'''
import httpx2
from mcp.client.streamable_http import streamable_http_client

async def main():
    base = os.environ["MCPV2_HTTP_BASE"]
    auth = {"authorization":"Bearer "+os.environ["SCRIBE_TRANSPORT_AUTH_TOKEN"],
            "origin":"https://trusted.example"}
    async with httpx2.AsyncClient(headers=auth, timeout=httpx2.Timeout(10)) as raw:
        async def snapshot():
            response = await raw.get(base + "/__matrix/state")
            assert response.status_code == 200, response.text
            return response.json()
        async def capture(response):
            handle = response.headers.get("scribe-application-handle")
            if handle:
                raw.headers["scribe-application-handle"] = handle
        raw.event_hooks["response"] = [capture]
        async with Client(streamable_http_client(base + "/mcp", http_client=raw,
                          terminate_on_close=False), mode="2026-07-28", cache=None,
                          read_timeout_seconds=10) as current:
            await current.session.send_discover("2026-07-28")
            await current.list_tools(cache_mode="refresh")
            await call(current, "set_project", {"agent":os.environ["MCPV2_TEST_AGENT"],
                       "name":"retired-http-seed", "root":os.environ["MCPV2_REPO_A"]})
            await call(current, "append_entry", {"agent":os.environ["MCPV2_TEST_AGENT"],
                       "project":"retired-http-seed", "message":"retired-http-populated"})
        before = await snapshot()
        results = []
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(10), follow_redirects=False) as denial:
            for path in ("/sse", "/sse/", "/messages", "/messages/"):
                for method in ("GET", "POST"):
                    for headers, status in ((auth,404), ({},401),
                        ({"authorization":auth["authorization"],"origin":"https://evil.example"},403),
                        ({"origin":"https://evil.example"},403)):
                        response = await denial.request(method, base + path, headers=headers,
                            json={"jsonrpc":"2.0","id":1,"method":"tools/call",
                                  "params":{"name":"set_project","arguments":{"agent":os.environ["MCPV2_TEST_AGENT"],
                                  "name":"must-not-bind","root":os.environ["MCPV2_REPO_B"]}}})
                        results.append({"path":path,"method":method,"expected":status,
                            "actual":response.status_code,"redirect":response.headers.get("location"),
                            "type":response.json().get("type") if status != 404 else None})
        after = await snapshot()
        async with Client(streamable_http_client(base + "/mcp", http_client=raw,
                          terminate_on_close=False), mode="2026-07-28", cache=None,
                          read_timeout_seconds=10) as current:
            await call(current, "set_project", {"agent":os.environ["MCPV2_TEST_AGENT"],
                       "name":"http-path-sensitivity", "root":os.environ["MCPV2_REPO_B"]})
        changed = await snapshot()
        print(json.dumps({**provenance(), "paths":results,"before":before,"after":after,"changed":changed},sort_keys=True))
anyio.run(main)
'''


def test_retired_http_paths_rejected_and_listener_cleaned(
    candidate_python, mcp_v2_repo_root, observed_internal_runtime_env, json_probe, test_agent, request, isolated_runtime_env,
):
    assert isolated_runtime_env["SCRIBE_RELEASE_PROFILE"] == "public"
    with _http_child(candidate_python, mcp_v2_repo_root, observed_internal_runtime_env) as base:
        result = json_probe(candidate_python, RETIRED_HTTP_PROBE, cwd=mcp_v2_repo_root,
                            env={**observed_internal_runtime_env, "MCPV2_HTTP_BASE": base}, timeout=120)
    _assert_http_secret_evidence(mcp_v2_repo_root, request, observed_internal_runtime_env)
    assert result.returncode == 0, result.stderr
    data = result.payload
    _assert_origin(data, mcp_v2_repo_root)
    _assert_http_profile(data, "internal")
    assert len(data["paths"]) == 32
    for row in data["paths"]:
        assert row["actual"] == row["expected"] and row["redirect"] is None, row
        assert row["type"] == {404:None,401:"Unauthorized",403:"InvalidOrigin"}[row["expected"]]
    assert data["before"]["bindings"] and data["before"]["database"] and data["before"]["handles"]
    _assert_no_effects(data["before"], data["after"])
    assert data["changed"] != data["after"]
    assert data["changed"]["state"] != data["after"]["state"]


def _assert_http_profile(data: dict[str, Any], profile: str) -> None:
    for name in ("before", "after", "changed"):
        if name not in data:
            continue
        snapshot = data[name]
        assert snapshot["profile"] == profile, (name, snapshot["profile"])
        assert snapshot["transport_policy"]["network_exposed"] is False
        assert snapshot["transport_policy"]["bind_host"] == "127.0.0.1"


def _assert_no_effects(before: dict[str, Any], after: dict[str, Any]) -> None:
    assert before == after, ("effects changed", before, after)


def _public_companion(candidate_python, root, public_env, json_probe, label):
    env = dict(public_env)
    assert env["SCRIBE_RELEASE_PROFILE"] == "public"
    env.update(SCRIBE_TRANSPORT="stdio", SBR_PRELOAD_TOOLS="1",
               SBR_CANARY_MESSAGE="public-companion-" + label)
    env["MCPV2_OBSERVATIONS"] = str(Path(public_env["MCPV2_OBSERVATIONS"]).with_name(label + ".jsonl"))
    result = json_probe(candidate_python, PUBLIC_BINDING_STDIO_PROBE, cwd=root, env=env)
    assert result.returncode == 0, ("companion setup failure", result.stderr)
    _assert_origin(result.payload, root)
    return result.payload, env["SBR_CANARY_MESSAGE"]


def _assert_public_companion_ready(seed, message):
    # Until E serves real public stdio, fail on that actual producer response.
    # HTTP policy denial is deliberately not used as evidence of missing C11.
    failed = [step for step in seed["steps"] if step["is_error"] or step["data"].get("ok") is False]
    assert failed == [], ("PUBLIC_STDIO_COMPANION_BIND_APPEND_PRODUCER_FAILED", failed)
    _assert_binding_steps(seed["steps"], message, True)
    calls = [event for event in seed["events"] if event.get("method") == "tools/call"]
    assert calls and calls[-1]["after"]["profile"] == "public"
    records = list(calls[-1]["after"]["bindings"].values())
    assert records and all(record["binding_generation"] > 0 for record in records)


HTTP_SNAPSHOT_PROBE = COMMON_PROBE + r'''
import httpx2
async def main():
    async with httpx2.AsyncClient(headers={"authorization":"Bearer "+os.environ["SCRIBE_TRANSPORT_AUTH_TOKEN"],
            "origin":"https://trusted.example"},timeout=httpx2.Timeout(10)) as raw:
        response=await raw.get(os.environ["MCPV2_HTTP_BASE"]+"/__matrix/state")
        assert response.status_code==200,response.text
        print(json.dumps({**provenance(),"snapshot":response.json()},sort_keys=True))
anyio.run(main)
'''


PUBLIC_HTTP_PROBE = COMMON_PROBE + r'''
import httpx2
from mcp.client.streamable_http import streamable_http_client
async def main():
    base=os.environ["MCPV2_HTTP_BASE"]
    token=os.environ["SCRIBE_TRANSPORT_AUTH_TOKEN"]
    auth={"authorization":"Bearer "+token,"origin":"https://trusted.example"}
    meta={"io.modelcontextprotocol/protocolVersion":"2026-07-28",
          "io.modelcontextprotocol/clientCapabilities":{},
          "io.modelcontextprotocol/clientInfo":{"name":"policy-probe","version":"1"}}
    async with httpx2.AsyncClient(headers=auth,timeout=httpx2.Timeout(10)) as raw:
        async def snapshot():
            response=await raw.get(base+"/__matrix/state")
            assert response.status_code==200,response.text
            return response.json()
        async def capture(response):
            handle=response.headers.get("scribe-application-handle")
            if handle:
                raw.headers["scribe-application-handle"]=handle
        raw.event_hooks["response"]=[capture]
        async with Client(streamable_http_client(base+"/mcp",http_client=raw,terminate_on_close=False),
                          mode="2026-07-28",cache=None,read_timeout_seconds=10) as current:
            discovery=await current.session.send_discover("2026-07-28")
            catalog=await current.list_tools(cache_mode="refresh")
            handle=raw.headers.get("scribe-application-handle")
            assert handle
            before=await snapshot()
            wire=[];sdk=[]
            if os.environ["MCPV2_PUBLIC_CASE"]=="operators":
                operations=[("set_project",{"agent":os.environ["MCPV2_TEST_AGENT"],"name":"must-not-bind",
                                            "root":os.environ["MCPV2_REPO_A"]}),
                            ("get_project",{"agent":os.environ["MCPV2_TEST_AGENT"]}),
                            ("append_entry",{"agent":os.environ["MCPV2_TEST_AGENT"],"project":"stdio-binding",
                                             "message":"mcpv2-secret-canary-9f2aa89e","status":"info"})]
                for index,(name,arguments) in enumerate(operations,1):
                    response=await raw.post(base+"/mcp",headers={"mcp-protocol-version":"2026-07-28",
                        "mcp-method":"tools/call","mcp-name":name,"accept":"application/json, text/event-stream"},
                        json={"jsonrpc":"2.0","id":index,"method":"tools/call",
                              "params":{"name":name,"arguments":arguments,"_meta":meta}})
                    wire.append({"tool":name,"status":response.status_code,"body":response.json(),
                                 "redirect":response.headers.get("location")})
                    sdk.append(await call(current,name,arguments))
                async with httpx2.AsyncClient(timeout=httpx2.Timeout(10)) as denial:
                    body={"jsonrpc":"2.0","id":20,"method":"server/discover","params":{"_meta":meta}}
                    headers={"mcp-protocol-version":"2026-07-28","mcp-method":"server/discover",
                             "accept":"application/json, text/event-stream"}
                    missing=await denial.post(base+"/mcp",headers=headers,json=body)
                    origin=await denial.post(base+"/mcp",headers={**headers,"authorization":"Bearer "+token,
                                               "origin":"https://evil.example"},json=body)
                    auth_origin=[{"status":r.status_code,"body":r.json()} for r in (missing,origin)]
            else:
                auth_origin=[]
                async with httpx2.AsyncClient(timeout=httpx2.Timeout(10),follow_redirects=False) as denial:
                    for path in ("/sse","/sse/","/messages","/messages/"):
                        for method in ("GET","POST"):
                            for headers,status in ((auth,404),({},401),
                                ({"authorization":auth["authorization"],"origin":"https://evil.example"},403),
                                ({"origin":"https://evil.example"},403)):
                                response=await denial.request(method,base+path,headers=headers,
                                    json={"jsonrpc":"2.0","id":30,"method":"tools/call",
                                          "params":{"name":"set_project","arguments":{
                                            "agent":os.environ["MCPV2_TEST_AGENT"],"name":"must-not-bind",
                                            "root":os.environ["MCPV2_REPO_B"]}}})
                                wire.append({"path":path,"method":method,"expected":status,
                                    "status":response.status_code,"redirect":response.headers.get("location"),
                                    "type":response.json().get("type") if status!=404 else None})
            after=await snapshot()
            print(json.dumps({**provenance(),"revision":current.session.protocol_version,
                 "handle_present":bool(handle),"private_cache":discovery.get("cacheScope",discovery.get("cache_scope"))=="private",
                 "tools":{t.name:t.model_dump(mode="json") for t in catalog.tools},
                 "wire":wire,"sdk_denials":sdk,"auth_origin":auth_origin,"before":before,"after":after},sort_keys=True))
anyio.run(main)
'''


def _public_http_populated_trace(candidate_python, root, public_env, json_probe, request, case):
    seed, seed_message = _public_companion(candidate_python, root, public_env, json_probe, case + "-seed")
    with _http_child(candidate_python, root, public_env) as base:
        env = {**public_env, "MCPV2_HTTP_BASE":base, "MCPV2_PUBLIC_CASE":case}
        result = json_probe(candidate_python, PUBLIC_HTTP_PROBE, cwd=root, env=env, timeout=120)
        assert result.returncode == 0, result.stderr
        mutation, mutation_message = _public_companion(candidate_python, root, public_env, json_probe,
                                                       case + "-mutation")
        snapshot = json_probe(candidate_python, HTTP_SNAPSHOT_PROBE, cwd=root, env=env)
        assert snapshot.returncode == 0, snapshot.stderr
    data = result.payload
    data["changed"] = snapshot.payload["snapshot"]
    request.node.user_properties.append(("public_companion_trace", json.dumps({
        "seed":seed,"seed_message":seed_message,"mutation":mutation,
        "mutation_message":mutation_message,"http":data},sort_keys=True)))
    _assert_http_secret_evidence(root, request, public_env)
    _assert_origin(data,root)
    _assert_http_profile(data,"public")
    assert data["revision"] == MODERN_REVISION and data["handle_present"] and data["private_cache"]
    assert len(data["tools"]) == 35 and "read_file" in data["tools"]
    assert data["before"]["handles"]
    return data, seed, seed_message, mutation, mutation_message


@pytest.mark.regression
def test_public_http_local_operator_denial_before_effects(
    candidate_python,mcp_v2_repo_root,observed_runtime_env,json_probe,request,test_agent,
):
    data,seed,message,mutation,mutation_message = _public_http_populated_trace(
        candidate_python,mcp_v2_repo_root,observed_runtime_env,json_probe,request,"operators")
    assert [r["tool"] for r in data["wire"]] == ["set_project","get_project","append_entry"]
    for result in data["wire"]:
        assert result["status"] == 403 and result["body"]["reason_code"] == "local_operator_tool_blocked", result
        assert result["redirect"] is None
    assert [r["data"].get("rpc_code") for r in data["sdk_denials"]] == [-32603,-32603,-32603]
    assert [r["status"] for r in data["auth_origin"]] == [401,403]
    assert data["auth_origin"][0]["body"]["type"] == "Unauthorized"
    assert data["auth_origin"][1]["body"]["type"] == "InvalidOrigin"
    assert "mcpv2-secret-canary-9f2aa89e" not in json.dumps(data["wire"] + data["sdk_denials"])
    _assert_no_effects(data["before"],data["after"])
    # No HTTP operator default is invented; the only populated seed is stdio.
    _assert_public_companion_ready(seed,message)
    _assert_public_companion_ready(mutation,mutation_message)
    assert any("stdio-binding" in row for row in data["before"]["database"])
    assert data["changed"]["database"] != data["after"]["database"]


@pytest.mark.regression
def test_retired_public_http_paths_rejected_and_listener_cleaned(
    candidate_python,mcp_v2_repo_root,observed_runtime_env,json_probe,request,test_agent,
):
    data,seed,message,mutation,mutation_message = _public_http_populated_trace(
        candidate_python,mcp_v2_repo_root,observed_runtime_env,json_probe,request,"old-paths")
    assert len(data["wire"]) == 32
    for row in data["wire"]:
        assert row["status"] == row["expected"] and row["redirect"] is None, row
        assert row["type"] == {404:None,401:"Unauthorized",403:"InvalidOrigin"}[row["expected"]]
    _assert_no_effects(data["before"],data["after"])
    _assert_public_companion_ready(seed,message)
    _assert_public_companion_ready(mutation,mutation_message)
    assert any("stdio-binding" in row for row in data["before"]["database"])
    assert data["changed"]["database"] != data["after"]["database"]


FAULT_HTTP_PROBE = COMMON_PROBE + r'''
import httpx2
from mcp.client.streamable_http import streamable_http_client
async def main():
    base=os.environ["MCPV2_HTTP_BASE"];token=os.environ["SCRIBE_TRANSPORT_AUTH_TOKEN"]
    auth={"authorization":"Bearer "+token,"origin":"https://trusted.example"}
    async with httpx2.AsyncClient(headers=auth,timeout=httpx2.Timeout(10)) as raw:
        async def capture(response):
            handle=response.headers.get("scribe-application-handle")
            if handle: raw.headers["scribe-application-handle"]=handle
        raw.event_hooks["response"]=[capture]
        async with Client(streamable_http_client(base+"/mcp",http_client=raw,terminate_on_close=False),
                          mode="2026-07-28",cache=None,read_timeout_seconds=10) as client:
            await client.list_tools(cache_mode="refresh")
        before=(await raw.get(base+"/__matrix/state")).json()
        headers={"mcp-protocol-version":"2026-07-28","mcp-method":"server/discover",
                 "accept":"application/json, text/event-stream","origin":"https://trusted.example"}
        path="/mcp"
        if os.environ["MCPV2_TEST_FAULT"]=="restore-old-route":
            path="/sse";headers["authorization"]="Bearer "+token
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(10)) as fault_client:
            response=await fault_client.post(base+path,headers=headers,json={"jsonrpc":"2.0","id":70,
                "method":"server/discover","params":{"_meta":{
                    "io.modelcontextprotocol/protocolVersion":"2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities":{},
                    "io.modelcontextprotocol/clientInfo":{"name":"fault-sensitivity","version":"1"}}}})
        after=(await raw.get(base+"/__matrix/state")).json()
        print(json.dumps({**provenance(),"before":before,"after":after,
                          "fault_status":response.status_code},sort_keys=True))
anyio.run(main)
'''


@pytest.mark.regression
@pytest.mark.parametrize("fault",["omit-auth","restore-old-route"])
def test_public_http_no_effect_guard_detects_ingress_faults(
    fault,candidate_python,mcp_v2_repo_root,observed_runtime_env,json_probe,request,test_agent,
):
    env = {**observed_runtime_env,"MCPV2_TEST_FAULT":fault}
    with _http_child(candidate_python,mcp_v2_repo_root,env) as base:
        result = json_probe(candidate_python,FAULT_HTTP_PROBE,cwd=mcp_v2_repo_root,
                            env={**env,"MCPV2_HTTP_BASE":base},timeout=120)
    assert result.returncode == 0,result.stderr
    data=result.payload
    _assert_origin(data,mcp_v2_repo_root)
    _assert_http_profile(data,"public")
    assert data["before"]["handles"]
    assert data["fault_status"] == 200
    assert data["after"]["counters"]["identity"] > data["before"]["counters"]["identity"]
    with pytest.raises(AssertionError,match="effects changed"):
        _assert_no_effects(data["before"],data["after"])


def _assert_http_secret_evidence(root, request, runtime_env):
    stderr = Path(runtime_env["MCPV2_OBSERVATIONS"]).with_suffix(".stderr").read_text()
    # Check the same raw properties the JUnit writer retains, before E/X
    # assertions can end the test. Keep every duplicate probe_result property.
    properties = [*request.node.user_properties, ("server_stderr", stderr)]
    _spike_module(root)._assert_secret_free({"junit_properties": properties})
    request.node.user_properties.append(("server_stderr", stderr))
    request.node.user_properties.append(("t16_log_and_receipt_secrecy_checked", True))


def _spike_module(root: Path):
    spec = importlib.util.spec_from_file_location("matrix_spike", root / "scripts/mcp_v2_isolated_spike.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.regression
def test_spike_legacy_cli_refuses_before_any_effect(mcp_v2_repo_root, monkeypatch, test_agent):
    spike = _spike_module(mcp_v2_repo_root)
    def forbidden(*args, **kwargs):
        pytest.fail("retired CLI launched a process or allocated temporary state")
    monkeypatch.setattr(spike.subprocess, "run", forbidden)
    monkeypatch.setattr(spike.tempfile, "mkdtemp", forbidden)
    with pytest.raises(SystemExit) as denied:
        spike.main(["--repo-root",str(mcp_v2_repo_root),"--candidate","2.3.0",
                    "--protocol",MODERN_REVISION,"--legacy","1.26.0"])
    assert denied.value.code == 2


@pytest.mark.regression
def test_spike_secret_guard_rejects_server_logs_and_aggregate_receipts(mcp_v2_repo_root, tmp_path, request, test_agent):
    """T16 covers the raw evidence retained by an eventual aggregate receipt."""
    spike = _spike_module(mcp_v2_repo_root)
    clean = '<testsuites><testsuite><testcase name="safe"><properties><property name="server_stderr" value="safe log"/></properties></testcase></testsuite></testsuites>'
    report = tmp_path / "aggregate.xml"
    report.write_text(clean)
    observations = tmp_path / "observer.json"
    server_log = observations.with_suffix(".stderr")
    server_log.write_text("safe log")
    runtime_env = {"MCPV2_OBSERVATIONS": str(observations)}
    _assert_http_secret_evidence(mcp_v2_repo_root, request, runtime_env)
    spike._assert_secret_free({"server_stderr": "safe log", "denial_response": {"error": "denied"}})
    assert spike._aggregate_junit_evidence(report) == clean
    for secret in spike.REDACTIONS:
        server_log.write_text("child log: " + secret)
        with pytest.raises(ValueError, match="T16_SECRET_EVIDENCE_LEAK"):
            _assert_http_secret_evidence(mcp_v2_repo_root, request, runtime_env)
        with pytest.raises(ValueError, match="T16_SECRET_EVIDENCE_LEAK"):
            spike._assert_secret_free({"server_stderr": "child log: " + secret})
        with pytest.raises(ValueError, match="T16_SECRET_EVIDENCE_LEAK"):
            spike._assert_secret_free({"passed": True, "aggregate_junit": clean.replace("safe log", secret)})
        report.write_text(clean.replace("safe log", "child log: " + secret))
        with pytest.raises(ValueError, match="T16_SECRET_EVIDENCE_LEAK"):
            spike._aggregate_junit_evidence(report)


@pytest.mark.regression
def test_spike_current_commands_and_history_cannot_grant_success(mcp_v2_repo_root, test_agent):
    spike = _spike_module(mcp_v2_repo_root)
    commands = spike._install_commands("uv", Path("/tmp/isolated"), mcp_v2_repo_root, "2.3.0")
    assert commands and all("mcp==1.26.0" not in arg for cmd in commands.values() for arg in cmd)
    assert set(commands) == {"candidate_venv", "candidate_install"}
    historical = spike._rollback_receipt(mcp_v2_repo_root)
    assert historical["prior_dependency"] == "mcp==1.26.0"
    assert historical["current_modern_only"] is True
    assert historical["shadow_restore_only"] is True and historical["source_mutated"] is False
    assert all(row["status"] in {"BLOCK", "N/A"} for row in spike._matrix_rows(mcp_v2_repo_root, {}).values())


@pytest.mark.regression
def test_spike_node_outcomes_reject_missing_failed_and_skipped(mcp_v2_repo_root, tmp_path, test_agent):
    spike = _spike_module(mcp_v2_repo_root)
    report = tmp_path / "outcomes.xml"
    report.write_text('<testsuites><testsuite><testcase classname="tests.migration.mcp_v2.test_compatibility_matrix" '
                      'name="test_exact_candidate_modern_stdio_real_client"/></testsuite></testsuites>')
    nodes = spike._junit_outcomes(report)
    expected = MATRIX_PATH + "::test_exact_candidate_modern_stdio_real_client"
    assert nodes == {expected:"PASS"}
    assert spike._matrix_rows(mcp_v2_repo_root, nodes)["T20"]["status"] == "BLOCK"
    for tag in ("failure", "error", "skipped"):
        report.write_text('<testsuites><testsuite><testcase classname="tests.migration.mcp_v2.test_compatibility_matrix" '
                          'name="test_exact_candidate_modern_stdio_real_client"><' + tag +
                          '/></testcase></testsuite></testsuites>')
        assert spike._junit_outcomes(report)[expected] == "BLOCK"
    assert spike._junit_outcomes(tmp_path / "absent.xml") == {}
    assert spike._matrix_rows(mcp_v2_repo_root, {})["T20"]["status"] == "BLOCK"


@pytest.mark.regression
def test_aggregate_phase_coverage_includes_sibling_nodes_and_rejects_incomplete_evidence(
    candidate_python, mcp_v2_repo_root, isolated_runtime_env, tmp_path, request, test_agent,
):
    """The retained multi-file aggregate must account for every real test phase."""
    import copy

    spike = _spike_module(mcp_v2_repo_root)
    selected = (
        MATRIX_PATH + "::test_matrix_has_one_architecture_tied_decision_for_every_t01_t20",
        AUTH_PATH + "::test_public_release_allowed_operation_succeeds",
    )
    env = dict(isolated_runtime_env)
    if os.environ.get("MCPV2_ISOLATED_INSTALL") == "1":
        env["MCPV2_ISOLATED_INSTALL"] = "1"
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = os.pathsep.join((str(mcp_v2_repo_root / "src"), str(mcp_v2_repo_root / "tests")))
    report = tmp_path / "crossfile.xml"
    command = [str(candidate_python), "-m", "pytest", "-q", "-n0", *selected, f"--junitxml={report}"]
    executed = spike._run(command, cwd=mcp_v2_repo_root, env=env, timeout=90)
    outcomes = spike._junit_outcomes(report)
    phases = spike._junit_fingerprints(report)
    evidence = {"command_result": executed, "junit": report.read_text() if report.is_file() else None,
                "outcomes": outcomes, "phases": phases}
    request.node.user_properties.append(("crossfile_phase_evidence", json.dumps(evidence, sort_keys=True)))
    assert executed["returncode"] == 0 and executed["passed"], executed
    assert outcomes == dict.fromkeys(selected, "PASS")
    assert len(phases) == 6, ("sibling phases absent or duplicated", phases)
    assert {row["nodeid"] for row in phases} == set(selected)
    assert spike._phase_coverage_ok(outcomes, phases)

    controls = {
        "missing_phase": (outcomes, phases[1:]),
        "duplicate_phase": (outcomes, phases + [phases[0]]),
        "duplicate_equal_total": (outcomes, phases[1:] + [phases[1]]),
        "missing_sibling_node": (outcomes, [row for row in phases if row["nodeid"] == selected[0]]),
        "missing_outcome": ({selected[0]: "PASS"}, phases),
        "failed_outcome": ({**outcomes, selected[0]: "BLOCK"}, phases),
    }
    for status in ("failed", "skipped"):
        changed = copy.deepcopy(phases)
        changed[0]["outcome"] = status
        controls[status + "_phase"] = (outcomes, changed)
    wrong_phase = copy.deepcopy(phases)
    wrong_phase[0]["phase"] = "collection"
    controls["unknown_phase"] = (outcomes, wrong_phase)
    results = {name: spike._phase_coverage_ok(nodes, records) for name, (nodes, records) in controls.items()}
    request.node.user_properties.append(("phase_gate_controls", json.dumps(results, sort_keys=True)))
    assert results == dict.fromkeys(controls, False)
    assert spike._phase_coverage_ok({}, []) is False


def test_source_rollback_shadow_restores_prior_dependency_without_mutating_worktree(
    mcp_v2_repo_root: Path, test_agent: str,
) -> None:
    # Retain history/CLI/adapter evidence while current support is explicitly
    # modern-only. This never installs or executes the historical shadow.
    spike = _spike_module(mcp_v2_repo_root)
    receipt = spike._rollback_receipt(mcp_v2_repo_root)
    assert receipt["prior_dependency"] == "mcp==1.26.0"
    assert receipt["current_dependency"] == "mcp>=2.0.0,<3.0"
    assert receipt["dependency_shadow_restored"]
    assert receipt["prior_default_transport"] == "stdio" and receipt["prior_adapter_absent"]
    assert receipt["historical_revision"] == LEGACY_REVISION
    assert receipt["current_modern_only"] is True
    assert receipt["shadow_restore_only"] and receipt["source_mutated"] is False
    assert receipt["modern_failure_reclassified_as_legacy"] is False
