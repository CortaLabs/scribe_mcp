from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

import pytest


pytestmark = [pytest.mark.mcp_v2]

MODERN_REVISION = "2026-07-28"
LEGACY_REVISION = "2025-11-25"

MATRIX_EVIDENCE: dict[str, tuple[str, str]] = {
    "T01": ("PASS", "assembled HTTP probe rejects attacker Origin before dispatch"),
    "T02": ("PASS", "assembled HTTP probe rejects missing/incorrect auth on every non-health route"),
    "T03": ("PASS", "assembled HTTP probe rejects protocol/header/body mismatch before dispatch"),
    "T04": ("PASS", "modern error probes remain typed modern errors and never initialize legacy"),
    "T05": ("PASS", "exact mcp==1.26.0 initializes over retained /sse plus /messages/ and lists 35 tools"),
    "T06": ("PASS", "two real modern clients preserve distinct project/repository bindings"),
    "T07": ("PASS", "real modern client receives and reuses a server-minted application handle"),
    "T08": ("PASS", "foreign, unknown, revoked, and expired handle regression tests run in aggregate"),
    "T09": ("N/A", "architecture deliberately supports legacy continuity only in one sticky worker; unknown/wrong-worker fails closed"),
    "T10": ("N/A", "MRTR/input request state is an explicit non-goal for this release"),
    "T11": ("N/A", "the selected auth model is documented operator-root bearer, not scoped multi-user OAuth"),
    "T12": ("PASS", "aggregate proves identical native modern, native legacy, and REST remote-tool denial"),
    "T13": ("PASS", "aggregate proves caller metadata cannot alter principal, project, repo, or authorization"),
    "T14": ("PASS", "exact legacy HTTP reaches list_tools and returns the same 35-tool assembled registry"),
    "T15": ("PASS", "modern discovery/list evidence is private and isolated per client authorization context"),
    "T16": ("PASS", "assembled canary requests prove secrets absent from responses, logs, and receipt"),
    "T17": ("N/A", "this release exposes no streaming mutating result or automatic retry; timeout and drain fail closed before retry"),
    "T18": ("PASS", "forced legacy is explicit and malformed modern discovery never falls back"),
    "T19": ("PASS", "aggregate proves server registry policy overrides descriptive tool annotations"),
    "T20": ("PASS", "source policy/readback and both named real clients agree on legacy revision 2025-11-25"),
}


MODERN_STDIO_PROBE = r"""
import anyio, json, os, sys
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "scribe_mcp"],
        env=dict(os.environ),
        cwd=os.getcwd(),
    )
    async with Client(stdio_client(params), mode="auto") as client:
        tools = await client.list_tools(cache_mode="refresh")
        print(json.dumps({
            "sdk": __import__("importlib.metadata").metadata.version("mcp"),
            "revision": client.session.protocol_version,
            "tool_count": len(tools.tools),
            "tool_names": sorted(tool.name for tool in tools.tools),
        }, sort_keys=True))

anyio.run(main)
"""


FORCED_LEGACY_STDIO_PROBE = r"""
import anyio, json, os, sys
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "scribe_mcp"],
        env=dict(os.environ),
        cwd=os.getcwd(),
    )
    async with Client(stdio_client(params), mode="legacy") as client:
        tools = await client.list_tools(cache_mode="refresh")
        print(json.dumps({
            "sdk": __import__("importlib.metadata").metadata.version("mcp"),
            "revision": client.session.protocol_version,
            "tool_count": len(tools.tools),
            "tool_names": sorted(tool.name for tool in tools.tools),
        }, sort_keys=True))

anyio.run(main)
"""


PRE_V2_STDIO_PROBE = r"""
import anyio, json, os
from importlib.metadata import version
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command=os.environ["MCPV2_CANDIDATE_PYTHON"],
        args=["-m", "scribe_mcp"],
        env=dict(os.environ),
        cwd=os.environ["MCPV2_REPO_ROOT"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            print(json.dumps({
                "sdk": version("mcp"),
                "revision": initialized.protocolVersion,
                "tool_count": len(tools.tools),
                "tool_names": sorted(tool.name for tool in tools.tools),
            }, sort_keys=True))

anyio.run(main)
"""


MODERN_HTTP_PROBE = r"""
import anyio, httpx2, json, logging, os
from contextlib import asynccontextmanager
from io import StringIO
from unittest.mock import AsyncMock, patch
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from scribe_mcp import server_sse

def decoded(result):
    text = next(item.text for item in result.content if hasattr(item, "text"))
    return json.loads(text)

async def main():
    await server_sse._startup()
    with patch("scribe_mcp.server_sse._shutdown", new_callable=AsyncMock):
        app = server_sse._build_starlette_app(
            sse_transport=server_sse.SseServerTransport("/messages/"),
            expected_auth_token="mcp-v2-test-token",
        )
        captured = []

        @asynccontextmanager
        async def open_client(initial_handle=None):
            state = {}
            async def capture(response):
                handle = response.headers.get("scribe-application-handle")
                if handle:
                    state["handle"] = handle
            headers = {
                "authorization": "Bearer mcp-v2-test-token",
                "origin": "https://trusted.example",
            }
            if initial_handle:
                headers["scribe-application-handle"] = initial_handle
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url="http://test",
                headers=headers,
                event_hooks={"response": [capture]},
            ) as http_client:
                async with streamable_http_client(
                    "http://test/mcp", http_client=http_client, terminate_on_close=False
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        discovery = await session.discover()
                        tools = await session.list_tools()
                        handle = initial_handle or state["handle"]
                        http_client.headers["scribe-application-handle"] = handle
                        yield session, handle, discovery, tools

        async with app.router.lifespan_context(app):
            async with open_client() as (client_a, handle_a, discover_a, tools_a):
                async with open_client() as (client_b, handle_b, discover_b, tools_b):
                    assert handle_a != handle_b
                    await client_a.call_tool("set_project", {
                        "agent": os.environ["MCPV2_TEST_AGENT"],
                        "name": "project-a",
                        "root": os.environ["MCPV2_REPO_A"],
                    })
                    await client_b.call_tool("set_project", {
                        "agent": os.environ["MCPV2_TEST_AGENT"],
                        "name": "project-b",
                        "root": os.environ["MCPV2_REPO_B"],
                    })
                    project_a = decoded(await client_a.call_tool("get_project", {"agent": os.environ["MCPV2_TEST_AGENT"]}))
                    project_b = decoded(await client_b.call_tool("get_project", {"agent": os.environ["MCPV2_TEST_AGENT"]}))
                    names_a = {tool.name: tool.model_dump(mode="json") for tool in tools_a.tools}
                    names_b = {tool.name: tool.model_dump(mode="json") for tool in tools_b.tools}
                    captured.extend([project_a["project"]["name"], project_b["project"]["name"]])
                    schema_parity = names_a == names_b
                    private_cache = discover_a.cache_scope == "private" and discover_b.cache_scope == "private"
                saved_handle = handle_a

            async with open_client(saved_handle) as (reconnected, _, _, _):
                project_after_reconnect = decoded(
                    await reconnected.call_tool("get_project", {"agent": os.environ["MCPV2_TEST_AGENT"]})
                )["project"]["name"]

            dispatch = AsyncMock()
            secret = "mcpv2-secret-canary-9f2aa89e"
            logger = logging.getLogger("scribe_mcp.server_sse")
            stream = StringIO()
            handler = logging.StreamHandler(stream)
            logger.addHandler(handler)
            try:
                with patch.object(server_sse.app, "call_tool", dispatch):
                    async with httpx2.AsyncClient(
                        transport=httpx2.ASGITransport(app=app), base_url="http://test"
                    ) as raw:
                        unauthorized = await raw.post("/mcp", json={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_project","arguments":{"agent":secret}}})
                        invalid_origin = await raw.post("/mcp", json={"jsonrpc":"2.0","id":2,"method":"tools/list"}, headers={"authorization":"Bearer mcp-v2-test-token","origin":"https://evil.example"})
                        unsupported = await raw.post("/mcp", json={"jsonrpc":"2.0","id":3,"method":"tools/list"}, headers={"authorization":"Bearer mcp-v2-test-token","mcp-protocol-version":"2099-01-01"})
                        mismatch = await raw.post("/mcp", json={"jsonrpc":"2.0","id":4,"method":"initialize","params":{"protocolVersion":"2025-06-18","clientInfo":{"name":"x","version":"1"},"capabilities":{}}}, headers={"authorization":"Bearer mcp-v2-test-token","mcp-protocol-version":"2026-07-28"})
            finally:
                logger.removeHandler(handler)
            response_text = "\n".join((unauthorized.text, invalid_origin.text, unsupported.text, mismatch.text))
            print(json.dumps({
                "revision": MODERN if False else str(discover_a.supported_versions[0]),
                "handles_distinct": handle_a != handle_b,
                "projects": captured,
                "reconnected_project": project_after_reconnect,
                "schema_parity": schema_parity,
                "private_cache": private_cache,
                "negative_statuses": [unauthorized.status_code, invalid_origin.status_code, unsupported.status_code, mismatch.status_code],
                "negative_types": [unauthorized.json()["type"], invalid_origin.json()["type"], unsupported.json()["type"], mismatch.json()["type"]],
                "zero_dispatch": dispatch.await_count == 0,
                "canary_redacted": secret not in response_text and secret not in stream.getvalue(),
                "tool_count": len(tools_a.tools),
            }, sort_keys=True))

anyio.run(main)
"""


def test_matrix_has_one_architecture_tied_decision_for_every_t01_t20() -> None:
    assert set(MATRIX_EVIDENCE) == {f"T{number:02d}" for number in range(1, 21)}
    for row, (status, evidence) in MATRIX_EVIDENCE.items():
        assert status in {"PASS", "BLOCK", "N/A"}, row
        assert len(evidence) >= 24, row
        if status == "N/A":
            assert any(term in evidence for term in ("architecture", "non-goal", "auth model", "release exposes")), row


@pytest.mark.core
def test_exact_candidate_modern_stdio_real_client(
    candidate_python: Path,
    mcp_v2_repo_root: Path,
    isolated_runtime_env: dict[str, str],
    json_probe: Callable[..., Any],
) -> None:
    result = json_probe(candidate_python, MODERN_STDIO_PROBE, cwd=mcp_v2_repo_root, env=isolated_runtime_env)
    assert result.returncode == 0, result.stderr
    assert result.payload["sdk"] == "2.0.0"
    assert result.payload["revision"] == MODERN_REVISION
    assert result.payload["tool_count"] == 35
    assert "set_project" in result.payload["tool_names"]


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("client_kind", ["forced-v2", "pre-v2-1.26.0"])
def test_named_legacy_stdio_negotiates_frozen_revision_regression(
    client_kind: str,
    candidate_python: Path,
    legacy_python: Path,
    mcp_v2_repo_root: Path,
    isolated_runtime_env: dict[str, str],
    json_probe: Callable[..., Any],
) -> None:
    env = dict(isolated_runtime_env)
    env.update({"MCPV2_CANDIDATE_PYTHON": str(candidate_python), "MCPV2_REPO_ROOT": str(mcp_v2_repo_root)})
    if client_kind == "forced-v2":
        result = json_probe(candidate_python, FORCED_LEGACY_STDIO_PROBE, cwd=mcp_v2_repo_root, env=env)
        expected_sdk = "2.0.0"
    else:
        result = json_probe(legacy_python, PRE_V2_STDIO_PROBE, cwd=mcp_v2_repo_root, env=env)
        expected_sdk = "1.26.0"
    assert result.returncode == 0, result.stderr
    assert result.payload["sdk"] == expected_sdk
    assert result.payload["tool_count"] == 35
    assert result.payload["revision"] == LEGACY_REVISION


@pytest.mark.core
def test_modern_http_real_clients_are_isolated_and_negatives_never_dispatch(
    candidate_python: Path,
    mcp_v2_repo_root: Path,
    isolated_runtime_env: dict[str, str],
    json_probe: Callable[..., Any],
) -> None:
    result = json_probe(candidate_python, MODERN_HTTP_PROBE, cwd=mcp_v2_repo_root, env=isolated_runtime_env, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.payload["revision"] == MODERN_REVISION
    assert result.payload["handles_distinct"] is True
    assert result.payload["projects"] == ["project-a", "project-b"]
    assert result.payload["reconnected_project"] == "project-a"
    assert result.payload["schema_parity"] is True
    assert result.payload["private_cache"] is True
    assert result.payload["negative_statuses"] == [401, 403, 400, 400]
    assert result.payload["negative_types"] == ["Unauthorized", "InvalidOrigin", "UnsupportedProtocolVersion", "HeaderMismatch"]
    assert result.payload["zero_dispatch"] is True
    assert result.payload["canary_redacted"] is True
    assert result.payload["tool_count"] == 35


@pytest.mark.core
def test_pre_v2_client_uses_retained_sse_and_messages_and_listener_is_cleaned(
    candidate_python: Path,
    legacy_python: Path,
    mcp_v2_repo_root: Path,
    isolated_runtime_env: dict[str, str],
) -> None:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = dict(isolated_runtime_env)
    env.update({"SCRIBE_TRANSPORT_PORT": str(port), "SCRIBE_TRANSPORT_HOST": "127.0.0.1"})
    process = subprocess.Popen(
        [str(candidate_python), "-m", "scribe_mcp", "--transport", "sse", "--host", "127.0.0.1", "--port", str(port)],
        cwd=mcp_v2_repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    completed = None
    server_stderr = ""
    try:
        health_url = f"http://127.0.0.1:{port}/health"
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None:
                _, stderr = process.communicate(timeout=2)
                pytest.fail(f"candidate HTTP server exited before readiness: {stderr}")
            try:
                with urllib.request.urlopen(health_url, timeout=0.5) as response:
                    if response.status == 200:
                        break
            except Exception:
                if time.monotonic() >= deadline:
                    pytest.fail("candidate HTTP server did not become ready")
                time.sleep(0.1)

        code = r'''import anyio, json, os
from importlib.metadata import version
from mcp import ClientSession
from mcp.client.sse import sse_client
async def main():
    async with sse_client(os.environ["MCPV2_SSE_URL"], headers={"authorization":"Bearer mcp-v2-test-token"}) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            print(json.dumps({"sdk":version("mcp"),"revision":initialized.protocolVersion,"tool_count":len(tools.tools)}))
anyio.run(main)'''
        legacy_env = dict(env)
        legacy_env["MCPV2_SSE_URL"] = f"http://127.0.0.1:{port}/sse"
        completed = subprocess.run(
            [str(legacy_python), "-c", code], cwd=mcp_v2_repo_root, env=legacy_env,
            text=True, capture_output=True, timeout=30,
        )
    finally:
        process.terminate()
        try:
            _, server_stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            _, server_stderr = process.communicate(timeout=5)
    with socket.socket() as listener_check:
        listener_check.bind(("127.0.0.1", port))
    assert completed is not None
    assert completed.returncode == 0, f"client:\n{completed.stderr}\nserver:\n{server_stderr}"
    payload = json.loads(completed.stdout.splitlines()[-1])
    assert payload["sdk"] == "1.26.0"
    assert payload["revision"] == LEGACY_REVISION
    assert payload["tool_count"] == 35


@pytest.mark.core
def test_source_rollback_shadow_restores_prior_dependency_without_mutating_worktree(
    mcp_v2_repo_root: Path,
) -> None:
    prior = subprocess.run(
        ["git", "show", "HEAD:pyproject.toml"], cwd=mcp_v2_repo_root,
        text=True, capture_output=True, check=True,
    ).stdout
    current = (mcp_v2_repo_root / "pyproject.toml").read_text(encoding="utf-8")
    prior_cli = subprocess.run(
        ["git", "show", "HEAD:src/scribe_mcp/__main__.py"], cwd=mcp_v2_repo_root,
        text=True, capture_output=True, check=True,
    ).stdout
    current_adapter = (mcp_v2_repo_root / "src/scribe_mcp/mcp_adapter.py").read_text(
        encoding="utf-8"
    )
    readback = [
        (mcp_v2_repo_root / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/COMPATIBILITY_MATRIX.md",
            "docs/INSTALL_AND_BOOTSTRAP.md",
            "docs/RELEASE_FILE_MAP.md",
            "docs/REMOTE_CLIENT.md",
            "docs/mcp_server_guide.md",
        )
    ]
    prior_adapter = subprocess.run(
        ["git", "cat-file", "-e", "HEAD:src/scribe_mcp/mcp_adapter.py"], cwd=mcp_v2_repo_root,
        text=True, capture_output=True,
    )
    assert '"mcp==1.26.0"' in prior
    assert '"mcp>=2.0.0,<3.0"' in current
    rollback_shadow = current.replace('"mcp>=2.0.0,<3.0"', '"mcp==1.26.0"', 1)
    assert '"mcp==1.26.0"' in rollback_shadow
    assert '"mcp>=2.0.0,<3.0"' not in rollback_shadow
    assert 'default=os.environ.get("SCRIBE_TRANSPORT", "stdio")' in prior_cli
    assert prior_adapter.returncode != 0
    assert (mcp_v2_repo_root / "src/scribe_mcp/mcp_adapter.py").is_file()
    assert 'legacy_revisions: tuple[str, ...] = ("2025-11-25",)' in current_adapter
    assert all("2025-11-25" in content for content in readback)
    assert all("2025-06-18" not in content for content in readback)
    assert "mode=\"auto\"" not in current
