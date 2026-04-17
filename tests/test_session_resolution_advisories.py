#!/usr/bin/env python3
"""Regression tests for advisory surfacing after truthful session resolution."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.shared.project_registry import RuntimeProjectRegistry
from scribe_mcp.tools import get_project as get_project_module
from scribe_mcp.tools import read_recent as read_recent_module


def test_runtime_registry_unavailable_returns_classified_advisory_payload() -> None:
    registry = RuntimeProjectRegistry(
        None,
        advisory_context={
            "available": False,
            "classification": "environment_mismatch",
            "reason_code": "runtime_mode_non_standalone",
            "mode": "server",
            "storage_backend": "postgres",
            "message": "Planning-doc drift advisories require standalone runtime mode.",
        },
    )

    payload = registry.get_planning_advisories("demo")

    assert payload["available"] is False
    assert payload["classification"] == "environment_mismatch"
    assert payload["reason_code"] == "runtime_mode_non_standalone"
    assert payload["advisories"][0]["code"] == "planning_registry_unavailable"


def test_read_recent_advisories_require_truthful_resolution() -> None:
    response = {}

    class _RegistryStub:
        def get_planning_advisories(self, _project_name: str):
            return {"available": False, "advisories": [{"code": "planning_registry_unavailable"}]}

    previous_registry = read_recent_module._PROJECT_REGISTRY
    read_recent_module._PROJECT_REGISTRY = _RegistryStub()
    try:
        unresolved = SimpleNamespace(resolution_source="unresolved")
        read_recent_module._attach_planning_advisories(
            response,
            "demo",
            context=unresolved,
        )
        assert "planning_advisories" not in response

        resolved = SimpleNamespace(resolution_source="session_binding")
        read_recent_module._attach_planning_advisories(
            response,
            "demo",
            context=resolved,
        )
        assert response["planning_advisories"]["advisories"][0]["code"] == "planning_registry_unavailable"
    finally:
        read_recent_module._PROJECT_REGISTRY = previous_registry


@pytest.mark.asyncio
async def test_get_project_surfaces_registry_classification_when_docs_status_unavailable(monkeypatch, tmp_path: Path) -> None:
    project_name = "resolution_truth_project"

    async def _prepare_context(**_kwargs):
        return LoggingContext(
            tool_name="get_project",
            project={
                "name": project_name,
                "root": str(tmp_path),
                "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
            },
            recent_projects=[project_name],
            state_snapshot={},
            reminders=[],
            resolution_source="session_binding",
            fallback_used=False,
            fallback_chain=[],
        )

    advisory_payload = {
        "available": False,
        "classification": "environment_mismatch",
        "reason_code": "runtime_mode_non_standalone",
        "mode": "server",
        "storage_backend": "postgres",
        "advisories": [{"code": "planning_registry_unavailable"}],
    }

    class _RegistryStub:
        available = False

        def get_planning_advisories(self, requested_name: str):
            if requested_name == project_name:
                return advisory_payload
            return {}

        def get_project(self, _requested_name: str):
            return None

        def get_registry_advisory_context(self):
            return {
                "available": False,
                "classification": "environment_mismatch",
                "reason_code": "runtime_mode_non_standalone",
                "mode": "server",
                "storage_backend": "postgres",
                "message": "Planning-doc drift advisories require standalone runtime mode.",
            }

    fake_backend = SimpleNamespace(
        fetch_project=AsyncMock(return_value=SimpleNamespace(name=project_name)),
        count_entries=AsyncMock(return_value=0),
    )
    fake_server = Mock()
    fake_server.state_manager = SimpleNamespace(record_tool=AsyncMock(return_value={"tool": "get_project"}))
    fake_server.storage_backend = fake_backend
    fake_server.get_execution_context.return_value = None
    fake_server.get_agent_identity.return_value = None

    monkeypatch.setattr(get_project_module, "server_module", fake_server)
    monkeypatch.setattr(get_project_module._GET_PROJECT_HELPER, "server_module", fake_server)
    monkeypatch.setattr(get_project_module._GET_PROJECT_HELPER, "prepare_context", _prepare_context)
    monkeypatch.setattr(get_project_module, "_PROJECT_REGISTRY", _RegistryStub())

    result = await get_project_module.get_project(agent="test_agent", format="structured")

    meta = result.get("project", {}).get("meta", {})
    assert meta.get("planning_advisories", {}).get("classification") == "environment_mismatch"
    assert meta.get("planning_advisories", {}).get("reason_code") == "runtime_mode_non_standalone"
    assert meta.get("docs_status", {}).get("classification") == "environment_mismatch"
    assert meta.get("docs_status", {}).get("reason_code") == "runtime_mode_non_standalone"
