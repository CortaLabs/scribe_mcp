from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import scribe_mcp.tools.doctor as doctor_module


class _FakeBackend:
    async def get_session_project(self, session_id: str):
        if session_id == "stable-1":
            return "demo"
        return None

    async def fetch_project(self, name: str, repo_root: str | None = None):
        if name != "demo":
            return None
        return SimpleNamespace(name="demo", repo_id="repo-1", project_key="pk-1")

    async def query_case_registry_records(
        self,
        repo_root: str | None = None,
        project_name: str | None = None,
        case_type: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ):
        return [
            SimpleNamespace(
                case_id="BUG-1",
                case_type="bug",
                status="open",
                project_name=project_name or "demo",
                repo_id="repo-1",
                project_key="pk-1",
                source_tool="open_bug",
            ),
            SimpleNamespace(
                case_id="SEC-1",
                case_type="security",
                status="in_progress",
                project_name=project_name or "demo",
                repo_id="repo-1",
                project_key="pk-1",
                source_tool="open_security",
            ),
        ]

    async def create_repo_scope_grant(self, **kwargs):
        return None

    async def fetch_repo_scope_grant(self, grant_id: str):
        return None


@pytest.mark.asyncio
async def test_scribe_doctor_surfaces_authority_and_case_telemetry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    fake_settings = SimpleNamespace(
        project_root=repo_root,
        storage_backend="sqlite",
        db_url=None,
        mode="project",
        remote_server_url=None,
        remote_auth_token=None,
        sqlite_path=repo_root / "runtime.sqlite3",
        postgres_schema="scribe",
    )
    monkeypatch.setattr(doctor_module, "settings", fake_settings)

    resolved_scope = SimpleNamespace(
        repo_root=str(repo_root),
        project_name="demo",
        resolution_source="session_binding",
        provenance=SimpleNamespace(repo_root="verified", project_name="verified"),
        authoritative_session_key="stable-1",
    )
    fake_context = SimpleNamespace(
        repo_root=str(repo_root),
        mode="project",
        session_id="transport-1",
        stable_session_id="stable-1",
        transport_session_id="transport-1",
        resolved_scope=resolved_scope,
        authoritative_session_key="stable-1",
    )

    fake_server = SimpleNamespace(
        storage_backend=_FakeBackend(),
        state_manager=SimpleNamespace(_storage_backend=None),
        router_context_manager=SimpleNamespace(_storage_backend=None),
        get_execution_context=lambda: fake_context,
    )
    monkeypatch.setattr(doctor_module, "server_module", fake_server)
    monkeypatch.setattr(
        doctor_module,
        "get_runtime_project_registry",
        lambda: SimpleNamespace(available=False, get_registry_advisory_context=lambda: {}),
    )

    result = await doctor_module.scribe_doctor(agent="test-agent")

    repo_authority = result["runtime"]["repo_authority"]
    assert repo_authority["authority_state"] == "verified"
    assert repo_authority["authority_source"] == "session_binding"
    assert repo_authority["project_key"] == "pk-1"
    assert repo_authority["repo_id"] == "repo-1"
    assert repo_authority["compatibility_usage"]["remaining_legacy_skip_validation_compatibility_usage"] == 0

    case_telemetry = result["runtime"]["case_telemetry"]
    assert case_telemetry["registry_surface_available"] is True
    assert case_telemetry["counts"]["total_cases"] == 2
    assert case_telemetry["counts"]["by_case_type"]["bug"] == 1
    assert case_telemetry["counts"]["by_normalized_status"]["in_progress"] == 1
    assert case_telemetry["ownership_snapshots"][0]["case_id"] == "BUG-1"
