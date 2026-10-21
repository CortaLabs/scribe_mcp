from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import copy
import hashlib
import inspect
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

import scribe_mcp
import scribe_mcp.physical_logical_reconciliation as reconciliation_module
import scribe_mcp.tools.doctor as doctor_module
from scribe_mcp.storage.models import SessionBindingRecordV2


class _FakeBackend:
    async def get_session_project(self, session_id: str):
        if session_id == "stable-1":
            return SessionBindingRecordV2(hashlib.sha256(session_id.encode()).hexdigest(), "pk-1", "demo", "/repo/demo", 4, datetime.now(timezone.utc))
        return None

    async def fetch_project(self, name: str, repo_root: str | None = None, project_key: str | None = None):
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

    loaded_package_root = str(Path(scribe_mcp.__file__).resolve().parent)
    assert result["repo_root"] == str(repo_root)
    assert result["module_root"] == loaded_package_root
    assert result["repo_root_candidates"]["from_module_root"] == loaded_package_root

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


@pytest.mark.asyncio
@pytest.mark.regression
async def test_doctor_reads_structured_binding_without_context_project():
    backend = _FakeBackend()
    snapshot = await doctor_module._active_project_authority_snapshot(
        storage_backend=backend,
        runtime_exec_context=SimpleNamespace(authoritative_session_key="stable-1"),
    )
    assert snapshot["project_name"] == "demo"
    assert snapshot["project_key"] == "pk-1"
    assert snapshot["binding_generation"] == 4


def _configure_doctor_fixture(monkeypatch: pytest.MonkeyPatch, repo_root: Path, backend: object) -> None:
    def deny_socket_connect(*args, **kwargs):
        pytest.fail("Doctor collection fixture attempted network access")

    monkeypatch.setattr(socket.socket, "connect", deny_socket_connect)
    fake_settings = SimpleNamespace(
        project_root=repo_root,
        storage_backend="sqlite",
        db_url=None,
        mode="standalone",
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
            storage_backend=backend,
            state_manager=SimpleNamespace(_storage_backend=None),
            router_context_manager=SimpleNamespace(_storage_backend=None),
            get_execution_context=lambda: None,
        ),
    )
    monkeypatch.setattr(
        doctor_module,
        "get_runtime_project_registry",
        lambda: SimpleNamespace(available=False, get_registry_advisory_context=lambda: {}),
    )


def _instrument_reconciliation(monkeypatch: pytest.MonkeyPatch, work: dict[str, int]) -> None:
    helper_names = (
        "_logical_projects",
        "_physical_core_docs",
        "_physical_progress_logs",
        "_physical_tool_logs",
        "_logical_dev_plan_rows",
        "_logical_tool_call_counts",
        "_fetch_rows",
    )
    for name in helper_names:
        original = getattr(reconciliation_module, name)

        if inspect.iscoroutinefunction(original):
            async def counted_async(*args, _name=name, _original=original, **kwargs):
                work[_name] = work.get(_name, 0) + 1
                return await _original(*args, **kwargs)

            monkeypatch.setattr(reconciliation_module, name, counted_async)
        else:
            def counted_sync(*args, _name=name, _original=original, **kwargs):
                work[_name] = work.get(_name, 0) + 1
                return _original(*args, **kwargs)

            monkeypatch.setattr(reconciliation_module, name, counted_sync)

    original_compare_projects = reconciliation_module._compare_projects

    def count_project_inputs(*, physical_configs, **kwargs):
        work["project_dictionary_evaluations"] = work.get("project_dictionary_evaluations", 0) + len(physical_configs)
        return original_compare_projects(physical_configs=physical_configs, **kwargs)

    monkeypatch.setattr(reconciliation_module, "_compare_projects", count_project_inputs)
    original_summary = reconciliation_module._summary

    def count_summary_items(items):
        materialized = list(items)
        work["summary_item_visits"] = work.get("summary_item_visits", 0) + len(materialized)
        return original_summary(materialized)

    monkeypatch.setattr(reconciliation_module, "_summary", count_summary_items)


def _configs(count: int, repo_root: Path) -> dict[str, dict[str, str]]:
    return {
        f"seed_{index:04d}": {"name": f"seed_{index:04d}", "root": str(repo_root)}
        for index in range(count)
    }


def _count_reconciliation_file_reads(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> list[Path]:
    observed: list[Path] = []
    original_read_text = Path.read_text
    inventory_names = {
        "ARCHITECTURE_GUIDE.md",
        "PHASE_PLAN.md",
        "CHECKLIST.md",
        "PROGRESS_LOG.md",
        "TOOL_LOG.jsonl",
    }

    def count_inventory_reads(path: Path, *args, **kwargs):
        try:
            relative = path.relative_to(repo_root)
        except ValueError:
            relative = None
        if relative is not None and "dev_plans" in relative.parts and path.name in inventory_names:
            observed.append(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", count_inventory_reads)
    return observed


@pytest.mark.asyncio
@pytest.mark.regression
async def test_doctor_deferred_skips_reconciliation_inventory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_agent: str
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    backend = _FakeBackend()
    _configure_doctor_fixture(monkeypatch, repo_root, backend)
    inventory_reads = _count_reconciliation_file_reads(monkeypatch, repo_root)
    configs = _configs(0, repo_root)
    list_calls = 0
    work: dict[str, int] = {}
    _instrument_reconciliation(monkeypatch, work)

    def list_configs():
        nonlocal list_calls
        list_calls += 1
        return configs

    monkeypatch.setattr(reconciliation_module, "list_project_configs", list_configs)
    builder_calls = 0
    original_builder = reconciliation_module.build_physical_logical_reconciliation

    async def counted_builder(**kwargs):
        nonlocal builder_calls
        builder_calls += 1
        return await original_builder(**kwargs)

    monkeypatch.setattr(doctor_module, "build_physical_logical_reconciliation", counted_builder)
    deferred_reports = []
    response_bytes = []
    for count in (0, 25, 1703):
        configs.clear()
        configs.update(_configs(count, repo_root))
        for selector in (None, "deferred"):
            result = await doctor_module.scribe_doctor(agent=test_agent, **({} if selector is None else {"reconciliation": selector}))
            runtime = result["runtime"]
            assert runtime["physical_logical_reconciliation"] is None
            assert runtime["physical_logical_reconciliation_collection"] == {
                "schema_version": "doctor-reconciliation-collection.v1",
                "mode": "deferred",
                "state": "not_collected",
                "reason": "not_requested",
            }
            assert runtime["repo_authority"]
            assert runtime["case_telemetry"]["counts"]["total_cases"] == 2
            assert runtime["timing_envelope"]["schema_version"] == "timing-envelope.v1"
            deferred_reports.append(runtime["physical_logical_reconciliation_collection"])
            response_size = len(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
            response_bytes.append(response_size)
            print(json.dumps({
                "fixture": "doctor-deferred-config-only",
                "input_configs": count,
                "selector": "omitted" if selector is None else selector,
                "doctor_bytes": response_size,
                "reconciliation": runtime["physical_logical_reconciliation_collection"],
                "builder_calls": builder_calls,
                "config_discovery_calls": list_calls,
                "collection_helper_calls": work,
                "backend_queries": 0,
                "reconciliation_document_log_reads": len(inventory_reads),
                "project_dictionary_evaluations": 0,
                "summary_item_visits": 0,
            }, sort_keys=True))

    assert len({json.dumps(report, sort_keys=True) for report in deferred_reports}) == 1
    assert len(set(response_bytes)) == 1
    assert builder_calls == 0
    assert list_calls == 0
    assert work == {}
    assert inventory_reads == []
    assert not any(hasattr(backend, method) for method in ("_fetch", "_fetchall", "list_projects_by_repo", "list_projects"))


@pytest.mark.asyncio
@pytest.mark.regression
async def test_doctor_full_preserves_reconciliation_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_agent: str
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    backend = _FakeBackend()
    _configure_doctor_fixture(monkeypatch, repo_root, backend)
    inventory_reads = _count_reconciliation_file_reads(monkeypatch, repo_root)
    configs = _configs(0, repo_root)
    work: dict[str, int] = {}
    _instrument_reconciliation(monkeypatch, work)
    list_calls = 0

    def list_configs():
        nonlocal list_calls
        list_calls += 1
        return configs

    monkeypatch.setattr(reconciliation_module, "list_project_configs", list_configs)
    doctor_builder_calls = 0
    original_builder = reconciliation_module.build_physical_logical_reconciliation

    async def doctor_builder(**kwargs):
        nonlocal doctor_builder_calls
        doctor_builder_calls += 1
        return await original_builder(**kwargs)

    monkeypatch.setattr(doctor_module, "build_physical_logical_reconciliation", doctor_builder)
    doctor_calls = 0
    for count in (0, 25, 1703):
        configs.clear()
        configs.update(_configs(count, repo_root))
        work.clear()
        before_list_calls = list_calls
        result = await doctor_module.scribe_doctor(agent=test_agent, reconciliation="full")
        report = result["runtime"]["physical_logical_reconciliation"]
        doctor_calls += 1
        doctor_work = dict(work)
        doctor_list_calls = list_calls - before_list_calls
        direct = await original_builder(repo_root=repo_root, storage_backend=backend, project_configs=configs)

        assert report == direct
        assert report["schema_version"] == "physical-logical-reconciliation.v1"
        assert report["read_only"] is True
        assert len(report["items"]) == count
        assert report["summary"]["total_items"] == count
        assert result["runtime"]["physical_logical_reconciliation_collection"] == {
            "schema_version": "doctor-reconciliation-collection.v1",
            "mode": "full",
            "state": "returned",
            "reason": None,
        }
        assert doctor_builder_calls == doctor_calls
        assert doctor_list_calls == 1
        assert doctor_work["project_dictionary_evaluations"] == count
        assert doctor_work["summary_item_visits"] == count
        assert inventory_reads == []
        assert not any(hasattr(backend, method) for method in ("_fetch", "_fetchall", "list_projects_by_repo", "list_projects", "count_entries"))
        assert all(doctor_work.get(name) == 1 for name in (
            "_logical_projects",
            "_physical_core_docs",
            "_physical_progress_logs",
            "_physical_tool_logs",
            "_logical_dev_plan_rows",
            "_logical_tool_call_counts",
            "_fetch_rows",
        ))
        print(json.dumps({
            "fixture": "doctor-full-config-only",
            "input_configs": count,
            "doctor_bytes": len(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
            "reconciliation_bytes": len(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
            "emitted_items": len(report["items"]),
            "summary_total": report["summary"]["total_items"],
            "builder_calls": 1,
            "config_discovery_calls": doctor_list_calls,
            "backend_queries": 0,
            "reconciliation_document_log_reads": len(inventory_reads),
            "collection_helper_calls": {name: doctor_work[name] for name in (
                "_logical_projects",
                "_physical_core_docs",
                "_physical_progress_logs",
                "_physical_tool_logs",
                "_logical_dev_plan_rows",
                "_logical_tool_call_counts",
                "_fetch_rows",
            )},
            "project_dictionary_evaluations": doctor_work["project_dictionary_evaluations"],
            "summary_item_visits": doctor_work["summary_item_visits"],
        }, sort_keys=True))


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("selector", [None, "", "FULL", " full", "deferred ", 1, True, [], {}, "partial"])
async def test_doctor_reconciliation_invalid_selector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_agent: str, selector: object
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _configure_doctor_fixture(monkeypatch, repo_root, _FakeBackend())
    collector_calls = 0

    async def builder(**kwargs):
        nonlocal collector_calls
        collector_calls += 1
        raise AssertionError("invalid selector reached reconciliation")

    monkeypatch.setattr(doctor_module, "build_physical_logical_reconciliation", builder)
    monkeypatch.setattr(doctor_module, "_list_loaded_plugins", lambda: pytest.fail("invalid selector reached plugin diagnostics"))
    monkeypatch.setattr(doctor_module, "_storage_diagnostics", lambda: pytest.fail("invalid selector reached storage diagnostics"))
    monkeypatch.setattr(
        doctor_module,
        "_active_project_authority_snapshot",
        lambda **kwargs: pytest.fail("invalid selector reached authority diagnostics"),
    )
    monkeypatch.setattr(
        doctor_module,
        "_case_telemetry_snapshot",
        lambda **kwargs: pytest.fail("invalid selector reached case diagnostics"),
    )
    with pytest.raises(ValueError, match="reconciliation must be 'deferred' or 'full'"):
        await doctor_module.scribe_doctor(agent=test_agent, reconciliation=selector)
    assert collector_calls == 0


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("error", [RuntimeError("builder failed"), asyncio.CancelledError()])
async def test_doctor_full_failure_is_not_reported_as_deferred(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_agent: str, error: Exception
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _configure_doctor_fixture(monkeypatch, repo_root, _FakeBackend())
    async def fail_builder(**kwargs):
        raise error

    monkeypatch.setattr(doctor_module, "build_physical_logical_reconciliation", fail_builder)
    with pytest.raises(type(error)) as exc:
        await doctor_module.scribe_doctor(agent=test_agent, reconciliation="full")
    assert exc.value is error


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.parametrize("selector", [None, "deferred"])
async def test_doctor_deferred_does_not_call_raising_builder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_agent: str, selector: str | None
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _configure_doctor_fixture(monkeypatch, repo_root, _FakeBackend())
    calls = 0
    sentinel = RuntimeError("deferred collection must stay unreachable")

    async def raising_builder(**kwargs):
        nonlocal calls
        calls += 1
        raise sentinel

    monkeypatch.setattr(doctor_module, "build_physical_logical_reconciliation", raising_builder)
    result = await doctor_module.scribe_doctor(
        agent=test_agent,
        **({} if selector is None else {"reconciliation": selector}),
    )

    assert result["runtime"]["physical_logical_reconciliation"] is None
    assert result["runtime"]["physical_logical_reconciliation_collection"] == {
        "schema_version": "doctor-reconciliation-collection.v1",
        "mode": "deferred",
        "state": "not_collected",
        "reason": "not_requested",
    }
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.regression
async def test_doctor_reconciliation_rich_fixture_read_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_agent: str
) -> None:
    from test_physical_logical_reconciliation import _ReadOnlyBackend, _write_project

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    demo_docs = _write_project(repo_root, "demo")
    orphan_docs = _write_project(repo_root, "orphan")
    configs = {
        "demo": {"name": "demo", "root": str(repo_root), "docs_dir": str(demo_docs), "progress_log": str(demo_docs / "PROGRESS_LOG.md")},
        "orphan": {"name": "orphan", "root": str(repo_root), "docs_dir": str(orphan_docs), "progress_log": str(orphan_docs / "PROGRESS_LOG.md")},
    }
    backend = _ReadOnlyBackend(repo_root)
    before_backend_records = copy.deepcopy(backend.projects)
    _configure_doctor_fixture(monkeypatch, repo_root, backend)
    plan_root = repo_root / ".scribe" / "docs" / "dev_plans"
    def byte_snapshot(root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    before_files = byte_snapshot(plan_root)
    read_counts: dict[str, int] = {}
    original_read_text = Path.read_text

    def count_seeded_reads(path: Path, *args, **kwargs):
        try:
            relative = path.relative_to(repo_root)
        except ValueError:
            relative = None
        if relative is not None and relative.parts[:3] == (".scribe", "docs", "dev_plans"):
            kind = relative.name if relative.name in {"PROGRESS_LOG.md", "TOOL_LOG.jsonl"} else "core_document"
            read_counts[kind] = read_counts.get(kind, 0) + 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", count_seeded_reads)

    project_list_calls = 0
    original_list_projects_by_repo = backend.list_projects_by_repo

    async def count_project_list_calls(repo_root_arg: str):
        nonlocal project_list_calls
        project_list_calls += 1
        return await original_list_projects_by_repo(repo_root_arg)

    monkeypatch.setattr(backend, "list_projects_by_repo", count_project_list_calls)
    list_config_calls = 0

    def list_configs():
        nonlocal list_config_calls
        list_config_calls += 1
        return configs

    monkeypatch.setattr(reconciliation_module, "list_project_configs", list_configs)
    work: dict[str, int] = {}
    _instrument_reconciliation(monkeypatch, work)
    builder_calls = 0
    original_builder = reconciliation_module.build_physical_logical_reconciliation

    async def count_doctor_builder(**kwargs):
        nonlocal builder_calls
        builder_calls += 1
        return await original_builder(**kwargs)

    monkeypatch.setattr(doctor_module, "build_physical_logical_reconciliation", count_doctor_builder)

    for selector in (None, "deferred"):
        before_backend_counts = (backend.fetchall_calls, backend.count_entries_calls, project_list_calls)
        before_collection_work = dict(work)
        result = await doctor_module.scribe_doctor(
            agent=test_agent,
            **({} if selector is None else {"reconciliation": selector}),
        )
        runtime = result["runtime"]
        assert runtime["physical_logical_reconciliation"] is None
        assert runtime["physical_logical_reconciliation_collection"] == {
            "schema_version": "doctor-reconciliation-collection.v1",
            "mode": "deferred",
            "state": "not_collected",
            "reason": "not_requested",
        }
        assert "repo_authority" in runtime
        assert "case_telemetry" in runtime
        assert builder_calls == 0
        assert list_config_calls == 0
        assert work == before_collection_work == {}
        assert (backend.fetchall_calls, backend.count_entries_calls, project_list_calls) == before_backend_counts == (0, 0, 0)
        assert read_counts == {}
        print(json.dumps({
            "fixture": "doctor-deferred-rich-read-only",
            "selector": "omitted" if selector is None else selector,
            "doctor_bytes": len(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
            "builder_calls": builder_calls,
            "config_discovery_calls": list_config_calls,
            "project_list_calls": 0,
            "backend_fetchall_calls": 0,
            "backend_count_entries_calls": 0,
            "collection_helper_calls": work,
            "seeded_file_reads": read_counts,
        }, sort_keys=True))

    read_counts.clear()
    work.clear()
    before_backend_counts = (backend.fetchall_calls, backend.count_entries_calls, project_list_calls)
    before_list_config_calls = list_config_calls
    result = await doctor_module.scribe_doctor(agent=test_agent, reconciliation="full")
    report = result["runtime"]["physical_logical_reconciliation"]
    doctor_backend_counts = (backend.fetchall_calls, backend.count_entries_calls, project_list_calls)
    doctor_reads = dict(read_counts)
    doctor_work = dict(work)
    doctor_list_config_calls = list_config_calls - before_list_config_calls
    direct = await original_builder(repo_root=repo_root, storage_backend=backend, project_configs=configs)

    assert report == direct
    assert report["summary"]["total_items"] == len(report["items"])
    assert {item["classification"] for item in report["items"]} >= {
        "consistent", "physical_only", "logical_only", "missing_logical_rows"
    }
    assert doctor_backend_counts[0] - before_backend_counts[0] == 3
    assert doctor_backend_counts[1] - before_backend_counts[1] == 2
    assert doctor_backend_counts[2] - before_backend_counts[2] == 1
    assert doctor_list_config_calls == 1
    assert builder_calls == 1
    assert {name: doctor_work.get(name, 0) for name in (
        "_logical_projects",
        "_physical_core_docs",
        "_physical_progress_logs",
        "_physical_tool_logs",
        "_logical_dev_plan_rows",
        "_logical_tool_call_counts",
        "_fetch_rows",
    )} == {
        "_logical_projects": 1,
        "_physical_core_docs": 1,
        "_physical_progress_logs": 1,
        "_physical_tool_logs": 1,
        "_logical_dev_plan_rows": 1,
        "_logical_tool_call_counts": 1,
        "_fetch_rows": 3,
    }
    assert doctor_reads == {"core_document": 6, "PROGRESS_LOG.md": 2, "TOOL_LOG.jsonl": 2}
    assert byte_snapshot(plan_root) == before_files
    assert backend.projects == before_backend_records
    print(json.dumps({
        "fixture": "doctor-full-rich-read-only",
        "emitted_items": len(report["items"]),
        "summary_total": report["summary"]["total_items"],
        "reconciliation_bytes": len(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
        "builder_calls": builder_calls,
        "config_discovery_calls": doctor_list_config_calls,
        "list_projects_by_repo_calls": doctor_backend_counts[2] - before_backend_counts[2],
        "backend_fetchall_calls": doctor_backend_counts[0] - before_backend_counts[0],
        "backend_count_entries_calls": doctor_backend_counts[1] - before_backend_counts[1],
        "project_dictionary_evaluations": doctor_work.get("project_dictionary_evaluations", 0),
        "summary_item_visits": doctor_work.get("summary_item_visits", 0),
        "collection_helper_calls": {name: doctor_work[name] for name in (
            "_logical_projects",
            "_physical_core_docs",
            "_physical_progress_logs",
            "_physical_tool_logs",
            "_logical_dev_plan_rows",
            "_logical_tool_call_counts",
            "_fetch_rows",
        )},
        "seeded_file_names": sorted(before_files),
        "seeded_file_bytes_total": sum(map(len, before_files.values())),
        "seeded_file_bytes_unchanged": byte_snapshot(plan_root) == before_files,
        "backend_record_values_unchanged": backend.projects == before_backend_records,
        "seeded_file_reads": doctor_reads,
    }, sort_keys=True))


@pytest.mark.asyncio
@pytest.mark.regression
async def test_doctor_full_reports_unavailable_backend_truthfully(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_agent: str
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _configure_doctor_fixture(monkeypatch, repo_root, None)
    monkeypatch.setattr(reconciliation_module, "list_project_configs", lambda: {})

    result = await doctor_module.scribe_doctor(agent=test_agent, reconciliation="full")

    assert result["runtime"]["physical_logical_reconciliation"]["backend"]["available"] is False
    assert result["runtime"]["physical_logical_reconciliation_collection"] == {
        "schema_version": "doctor-reconciliation-collection.v1",
        "mode": "full",
        "state": "returned",
        "reason": None,
    }
