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


def test_plugin_diagnostics_names_trust_opt_in_action(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plugins_dir = tmp_path / ".scribe" / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "repo_intel.py").write_text("# local plugin\n", encoding="utf-8")
    config = SimpleNamespace(
        plugin_config={"enabled": True, "allowlist": ["repo_intel"], "blocklist": ["legacy"]},
        plugins_dir=plugins_dir,
        plugin_loading_requested=lambda: True,
    )
    monkeypatch.delenv("SCRIBE_TRUST_REPO_PLUGINS", raising=False)
    monkeypatch.delenv("SCRIBE_ENABLE_EXTERNAL_PLUGINS", raising=False)

    diagnostics = doctor_module._build_plugin_diagnostics(config, [])

    assert diagnostics["plugin_loading_requested"] is True
    assert diagnostics["repo_plugin_trust_enabled"] is False
    assert diagnostics["blocked_reason"] == "repo_plugin_trust_not_enabled"
    assert diagnostics["discovered_repo_local_stems"] == ["repo_intel"]
    assert "SCRIBE_TRUST_REPO_PLUGINS=1" in diagnostics["guidance"]["available_action"]
    assert diagnostics["guidance"]["restart_required"] is True


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
    envelope = result["runtime"]["timing_envelope"]
    assert envelope["schema_version"] == "timing-envelope.v1"
    assert "path" in envelope
    assert "startup" in envelope
    assert envelope["budget_status"]["schema_version"] == "runtime-efficiency-budget.v1"
    assert "cold_start_ms" in envelope["budget_status"]["metrics"]
    assert "set_project_total_ms" in envelope["budget_status"]["metrics"]
    assert envelope["budget_status"]["metrics"]["cold_start_ms"]["status"] in {
        "unknown",
        "within_budget",
        "near_budget",
        "over_budget",
    }
    hygiene = result["diagnostic_hygiene"]
    assert hygiene["status"] in {"deferred_hygiene", "not_present", "configured", "unknown"}


@pytest.mark.asyncio
async def test_scribe_doctor_labels_bridge_runtime_plugin_warning_as_deferred_hygiene(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    bridge_dir = repo_root / ".scribe" / "config" / "bridges"
    bridge_dir.mkdir(parents=True)
    (bridge_dir / "council_mcp.yaml").write_text("bridge_id: council_mcp\n", encoding="utf-8")

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
    monkeypatch.setattr(
        doctor_module,
        "server_module",
        SimpleNamespace(
            storage_backend=None,
            state_manager=None,
            router_context_manager=None,
            get_execution_context=lambda: None,
        ),
    )
    monkeypatch.setattr(
        doctor_module,
        "get_runtime_project_registry",
        lambda: SimpleNamespace(available=False, get_registry_advisory_context=lambda: {}),
    )

    result = await doctor_module.scribe_doctor(agent="test-agent")
    hygiene = result["diagnostic_hygiene"]
    assert hygiene["status"] == "deferred_hygiene"
    assert hygiene["deferred_non_blocking"][0]["blocking"] is False
    assert hygiene["deferred_non_blocking"][0]["code"] == "BRIDGE_RUNTIME_PLUGIN_DEFERRED"
