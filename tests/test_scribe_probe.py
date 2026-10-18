from types import SimpleNamespace

import asyncpg
import pytest

from scribe_mcp.scripts import scribe_probe


def test_registry_sanity_probe_reports_readiness_drift_conflict(monkeypatch) -> None:
    project = SimpleNamespace(
        project_name="demo",
        status="in_progress",
        total_files=4,
        total_entries=2,
        meta={
            "docs": {
                "flags": {
                    "docs_ready_for_work": True,
                    "docs_hash_drift": True,
                },
                "baseline_hashes": {"phase_plan": "aaa"},
                "current_hashes": {"phase_plan": "bbb"},
            },
            "activity": {
                "days_since_last_entry": 1,
                "days_since_last_access": 1,
            },
        },
    )

    class _Registry:
        def list_projects(self, limit=None):  # noqa: ARG002
            return [project]

    monkeypatch.setattr(scribe_probe, "ProjectRegistry", lambda: _Registry())
    result = scribe_probe._registry_sanity_probe()

    assert result["ok"] is True
    assert len(result["warnings"]) == 1
    warning = result["warnings"][0]
    assert warning["project"] == "demo"
    assert warning["docs_ready_for_work"] is True
    assert warning["docs_hash_drift"] is True
    assert "docs_ready_conflicts_with_hash_drift" in warning["warnings"]


def test_registry_sanity_probe_honors_project_scope(monkeypatch) -> None:
    project_a = SimpleNamespace(
        project_name="project_a",
        status="planning",
        total_files=1,
        total_entries=0,
        meta={"docs": {"flags": {}, "baseline_hashes": {}, "current_hashes": {}}, "activity": {}},
    )
    project_b = SimpleNamespace(
        project_name="project_b",
        status="in_progress",
        total_files=0,
        total_entries=0,
        meta={"docs": {"flags": {}, "baseline_hashes": {}, "current_hashes": {}}, "activity": {}},
    )

    class _Registry:
        def list_projects(self, limit=None):  # noqa: ARG002
            return [project_a, project_b]

    monkeypatch.setattr(scribe_probe, "ProjectRegistry", lambda: _Registry())
    result = scribe_probe._registry_sanity_probe(project="project_b")

    assert result["ok"] is True
    assert len(result["warnings"]) == 1
    assert result["warnings"][0]["project"] == "project_b"


def test_normalize_result_payload_serializes_call_tool_result_like_objects() -> None:
    from mcp.types import CallToolResult, TextContent

    result = CallToolResult(
        content=[TextContent(type="text", text="Readable result")],
        structuredContent={
            "ok": True,
            "nested": {"content": [TextContent(type="text", text="Nested text")]},
        },
        isError=False,
    )

    normalized = scribe_probe._normalize_result_payload(result)

    assert normalized["ok"] is True
    assert normalized["nested"]["content"][0]["text"] == "Nested text"


def test_build_payload_includes_project_and_agent_for_stateful_tools() -> None:
    args = scribe_probe.parse_args(
        [
            "--project",
            "latency-probe",
            "--agent",
            "test-agent",
            "--root",
            "/repo/scribe",
            "--doc-action",
            "quality_check",
            "--doc",
            "checklist",
        ]
    )

    set_project_payload = scribe_probe._build_payload("set_project", args)
    read_recent_payload = scribe_probe._build_payload("read_recent", args)
    manage_docs_payload = scribe_probe._build_payload("manage_docs", args)

    assert set_project_payload["agent"] == "test-agent"
    assert read_recent_payload["agent"] == "test-agent"
    assert "project" not in read_recent_payload
    assert manage_docs_payload["agent"] == "test-agent"
    assert "project" not in manage_docs_payload


@pytest.mark.asyncio
async def test_json_output_serializes_multi_tool_non_dict_results(monkeypatch, capsys) -> None:
    class _ToolResult:
        def __init__(self, text: str, is_error: bool = False) -> None:
            self.content = [SimpleNamespace(text=text, type="text")]
            self.isError = is_error

    async def fake_run_tool(name: str, payload: dict[str, object]) -> object:  # noqa: ARG001
        if name == "first":
            return _ToolResult("first ok")
        return SimpleNamespace(custom=name, payload=payload)

    async def fake_bind(args: scribe_probe.ProbeArgs) -> str:  # noqa: ARG001
        return "token"

    monkeypatch.setattr(scribe_probe, "_run_tool", fake_run_tool)
    monkeypatch.setattr(scribe_probe, "_bind_probe_execution_context", fake_bind)
    monkeypatch.setattr(scribe_probe, "_reset_probe_execution_context", lambda token: None)

    await scribe_probe.main(["--tools", "first,second", "--project", "probe", "--json-output"])

    captured = capsys.readouterr()
    assert "first ok" in captured.out
    assert "Object of type" not in captured.out
    payload = __import__("json").loads(captured.out)
    assert payload["results"][0]["result"]["message"] == "first ok"
    assert payload["results"][1]["result"]["error"] == "Unexpected result type: SimpleNamespace"


@pytest.mark.asyncio
async def test_probe_drains_background_tasks_before_exit(monkeypatch, capsys) -> None:
    events: list[str] = []

    async def fake_run_tool(name: str, payload: dict[str, object]) -> dict[str, object]:  # noqa: ARG001
        events.append(f"tool:{name}")
        return {"ok": True}

    async def fake_bind(args: scribe_probe.ProbeArgs) -> str:  # noqa: ARG001
        events.append("bind")
        return "token"

    async def fake_drain() -> None:
        events.append("drain")

    async def fake_close() -> None:
        events.append("close")

    def fake_reset(token: object) -> None:  # noqa: ARG001
        events.append("reset")

    monkeypatch.setattr(scribe_probe, "_run_tool", fake_run_tool)
    monkeypatch.setattr(scribe_probe, "_bind_probe_execution_context", fake_bind)
    monkeypatch.setattr(scribe_probe, "_reset_probe_execution_context", fake_reset)
    monkeypatch.setattr(scribe_probe, "_drain_probe_background_tasks", fake_drain)
    monkeypatch.setattr(scribe_probe, "_close_probe_storage_backend", fake_close)

    await scribe_probe.main(["--tools", "first", "--project", "probe", "--json-output"])

    captured = capsys.readouterr()
    assert __import__("json").loads(captured.out)["ok"] is True
    assert events == ["bind", "tool:first", "drain", "close", "reset"]


@pytest.mark.asyncio
async def test_probe_exception_handler_only_suppresses_asyncpg_shutdown_future() -> None:
    loop = __import__("asyncio").get_running_loop()
    forwarded: list[dict[str, object]] = []
    original_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: forwarded.append(context))

    restore = scribe_probe._install_probe_exception_handler()
    handler = loop.get_exception_handler()
    assert handler is not None

    try:
        handler(
            loop,
            {
                "message": "Future exception was never retrieved",
                "exception": asyncpg.exceptions.ConnectionDoesNotExistError(
                    "connection was closed in the middle of operation"
                ),
            },
        )
        assert forwarded == []

        runtime_context = {
            "message": "Future exception was never retrieved",
            "exception": RuntimeError("different failure"),
        }
        handler(loop, runtime_context)
        assert forwarded == [runtime_context]
    finally:
        restore()
        loop.set_exception_handler(original_handler)


@pytest.mark.parametrize(
    "hook_label",
    ["hook_excluded", "hook_included", "hook_state_unknown", "unexpected"],
)
def test_same_server_root_comparison_normalizes_hook_labels(hook_label: str) -> None:
    normalized = scribe_probe._normalize_hook_label(hook_label)
    assert normalized in {"hook_excluded", "hook_included", "hook_state_unknown"}
    if hook_label == "unexpected":
        assert normalized == "hook_state_unknown"
    else:
        assert normalized == hook_label


@pytest.mark.parametrize("hook_label", ["hook_excluded", "hook_included", "hook_state_unknown"])
@pytest.mark.asyncio
async def test_same_server_root_comparison_rows_include_host_and_scribe_timing(
    monkeypatch,
    hook_label: str,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_run_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append({"tool_name": name, **payload})
        total_ms = 10.0 if payload["root"] == "/repo/scribe" else 25.0
        return {
            "ok": True,
            "timing": {
                "set_project_phase_ms": {
                    "record_tool": 1.0,
                    "total_ms": total_ms,
                }
            },
        }

    monkeypatch.setattr(scribe_probe, "_run_tool", fake_run_tool)

    result = await scribe_probe._same_server_root_comparison(
        project="latency-probe",
        roots=["/repo/scribe", "/repo/council"],
        agent="test-agent",
        hook_label=hook_label,
    )

    assert result["ok"] is True
    assert result["schema_version"] == "same-server-root-comparison.v1"
    assert result["measurement_contract"] == {
        "server_constant": True,
        "varied_parameter": "root",
        "config_mutation": False,
        "optimization_claim": False,
    }
    assert [call["tool_name"] for call in calls] == ["set_project", "set_project"]
    assert calls[0]["name"] == calls[1]["name"] == "latency-probe"
    assert calls[0]["root"] != calls[1]["root"]
    for call in calls:
        assert call["agent"] == "test-agent"
        assert call["format"] == "structured"

    rows = result["rows"]
    assert len(rows) == 2
    assert {row["hook_label"] for row in rows} == {hook_label}
    for row in rows:
        assert isinstance(row["host_wall_ms"], float)
        assert row["host_wall_ms"] >= 0.0
        assert row["scribe_timing"]["schema_version"] == "set-project-phase-ms.v1"
        assert "total_ms" in row["scribe_timing"]["set_project_phase_ms"]
        assert isinstance(row["scribe_total_ms"], float)


def test_same_server_root_comparison_attribution_distinguishes_inside_scribe_phases() -> None:
    rows = [
        {"root": "/repo/scribe", "host_wall_ms": 100.0, "scribe_total_ms": 90.0},
        {"root": "/repo/council", "host_wall_ms": 125.0, "scribe_total_ms": 112.0},
    ]

    attribution = scribe_probe._build_root_comparison_attribution(rows)

    assert attribution["classification"] == "inside_scribe_phases"
    assert attribution["host_delta_ms"] == 25.0
    assert attribution["scribe_delta_ms"] == 22.0
    assert attribution["outside_scribe_delta_ms"] == 3.0


def test_same_server_root_comparison_attribution_distinguishes_outside_wrapper_time() -> None:
    rows = [
        {"root": "/repo/scribe", "host_wall_ms": 100.0, "scribe_total_ms": 95.0},
        {"root": "/repo/council", "host_wall_ms": 180.0, "scribe_total_ms": 100.0},
    ]

    attribution = scribe_probe._build_root_comparison_attribution(rows)

    assert attribution["classification"] == "outside_scribe_hook_or_wrapper_time"
    assert attribution["host_delta_ms"] == 80.0
    assert attribution["scribe_delta_ms"] == 5.0
    assert attribution["outside_scribe_delta_ms"] == 75.0
