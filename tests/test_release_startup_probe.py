from __future__ import annotations

import asyncio

import pytest

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
