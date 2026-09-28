from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from scribe_mcp.object_store.filesystem import FilesystemStore
from scribe_mcp.object_store.hybrid import HybridStore
from scribe_mcp.object_store.providers.corta import CortaStoreProvider
from scribe_mcp.scripts import scribe_probe


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
        await asyncio.wait_for(backoff_started.wait(), timeout=1.0)

        assert write_task.done() is False
        assert await local.read(key) == content
        assert client.request.await_count == 1

        release_backoff.set()
        await asyncio.wait_for(write_task, timeout=1.0)
        assert client.request.await_count == 3
        assert backoff_calls == [0.5, 1.0]
        await store.close()
        client.aclose.assert_awaited_once_with()
