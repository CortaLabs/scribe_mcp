from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from scribe_mcp.object_store.base import RemoteProvider
from scribe_mcp.object_store.filesystem import FilesystemStore
from scribe_mcp.object_store.hybrid import HybridStore
from scribe_mcp.object_store.providers.corta import CortaStoreProvider
from scribe_mcp.scripts import scribe_probe


class _UnavailableRemote(RemoteProvider):
    def __init__(self) -> None:
        self.health_requests = 0

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def probe_health(self, *, timeout_seconds: float = 2.0) -> bool:
        self.health_requests += 1
        await asyncio.sleep(min(timeout_seconds, 0.1))
        return False

    async def put(self, key: str, content: str) -> None:
        raise httpx.ConnectError(f"remote unavailable for {key}")

    async def get(self, key: str) -> str | None:
        return None

    async def head(self, key: str) -> bool:
        return False

    async def list(self, prefix: str = "") -> list[str]:
        return []

    async def delete(self, key: str) -> None:
        return None


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

    local = FilesystemStore(tmp_path / "outage")
    remote = _UnavailableRemote()
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
    assert remote.health_requests == 0

    from scribe_mcp import server

    listed_tools = await server.app.list_tools()
    assert any(tool.name == "append_entry" for tool in listed_tools)

    key = "scribe/docs/dev_plans/startup/PROGRESS_LOG.md"
    await store.write(key, "[test-agent] locally durable under remote outage")
    assert await local.read(key) == "[test-agent] locally durable under remote outage"
    assert remote.health_requests == 0
    await store.close()
