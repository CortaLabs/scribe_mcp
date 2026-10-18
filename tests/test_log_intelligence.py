from __future__ import annotations

import json

from scribe_mcp.cli.main import main
from scribe_mcp.log_intelligence import build_log_intelligence_report, build_report_from_path
from scribe_mcp.progress_log_parser import parse_lines


def test_report_contract_counts_signals_and_next_actions() -> None:
    entries = parse_lines(
        [
            "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Complete task | priority=high; category=milestone; tags=[\"ship\"]",
            "[ℹ️] [2026-05-01 02:00:00 UTC] [Agent: Forge] [Project: Alpha] Missing priority | category=investigation; tags=[\"triage\"]",
            "[⚠️] [2026-05-01 03:00:00 UTC] [Agent: Forge] [Project: Alpha] Missing category and tags | priority=medium",
        ]
    )
    report = build_log_intelligence_report(entries, scope={"source": "x.md", "project": "Alpha"})

    assert set(report.keys()) == {"scope", "counts", "signals", "next_actions", "timing_envelope"}
    assert report["counts"] == {
        "entries_total": 3,
        "missing_priority": 1,
        "missing_category": 1,
        "missing_tags": 1,
        "generic_tool_duration_entries": 0,
    }
    signal_codes = {signal["code"] for signal in report["signals"]}
    assert signal_codes == {
        "LOG_MISSING_PRIORITY",
        "LOG_MISSING_CATEGORY",
        "LOG_MISSING_TAGS",
        "missing_generic_tool_duration",
    }
    assert any("priority" in action for action in report["next_actions"])


def test_build_report_from_path_uses_parser_schema_stably(tmp_path) -> None:
    log_file = tmp_path / "PROGRESS_LOG.md"
    log_file.write_text(
        "\n".join(
            [
                "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Complete task | priority=high; category=milestone; tags=[\"ship\"]",
                "[ℹ️] [2026-05-01 02:00:00 UTC] [Agent: Forge] [Project: Alpha] Missing category and tags | priority=medium",
            ]
        ),
        encoding="utf-8",
    )

    report = build_report_from_path(log_file, project="Alpha")

    assert report["scope"]["project"] == "Alpha"
    assert report["scope"]["source"] == str(log_file)
    assert report["counts"]["entries_total"] == 2
    assert report["counts"]["missing_category"] == 1
    assert report["counts"]["missing_tags"] == 1
    assert report["counts"]["generic_tool_duration_entries"] == 0
    assert report["signals"][0]["severity"] in {"low", "medium", "high", "critical"}


def test_cli_logs_analyze_entrypoint_matches_shared_builder_payload(tmp_path, capsys) -> None:
    log_file = tmp_path / "PROGRESS_LOG.md"
    log_file.write_text(
        "\n".join(
            [
                "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Complete task | priority=high; category=milestone; tags=[\"ship\"]",
                "[ℹ️] [2026-05-01 02:00:00 UTC] [Agent: Forge] [Project: Alpha] Missing category and tags | priority=medium",
            ]
        ),
        encoding="utf-8",
    )

    expected = build_report_from_path(log_file, project="Alpha")
    exit_code = main(["logs", "analyze", str(log_file), "--project", "Alpha"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == expected


def test_timing_envelope_graceful_when_missing_timing_data() -> None:
    entries = parse_lines(["[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Normal entry"])
    report = build_log_intelligence_report(entries, scope={"source": "x.md", "project": "Alpha"})
    envelope = report["timing_envelope"]
    assert envelope["schema_version"] == "timing-envelope.v1"
    assert envelope["path"]["dispatch"] == "unknown"
    assert envelope["startup"]["phases_ms"] == {}
    assert envelope["tools"]["set_project"]["phases_ms"] == {}
    assert envelope["tools"]["generic"]["phases_ms"]["missing_generic_tool_duration"] is True
    budget_status = envelope["budget_status"]
    assert budget_status["schema_version"] == "runtime-efficiency-budget.v1"
    assert budget_status["metrics"]["cold_start_ms"]["status"] == "unknown"
    assert budget_status["metrics"]["set_project_total_ms"]["status"] == "unknown"


def test_timing_envelope_budget_status_for_set_project_thresholds() -> None:
    entries = parse_lines(
        [
            "[ℹ️] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Perf set_project warm call | total_ms=18000; prepare_context_ms=11000",
        ]
    )
    report = build_log_intelligence_report(entries, scope={"source": "x.md", "project": "Alpha"})
    budget_status = report["timing_envelope"]["budget_status"]["metrics"]["set_project_total_ms"]
    assert budget_status["value_ms"] == 18000.0
    assert budget_status["warn_ms"] is not None
    assert budget_status["fail_ms"] is not None
    assert budget_status["status"] in {"near_budget", "over_budget"}


def test_timing_envelope_reports_persisted_generic_duration() -> None:
    entries = parse_lines(
        [
            "[ℹ️] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Generic tool call | duration_ms=12.5; correlation_id=call-123; measurement_scope=tool_only",
        ]
    )

    report = build_log_intelligence_report(entries, scope={"source": "x.md", "project": "Alpha"})

    assert report["counts"]["generic_tool_duration_entries"] == 1
    assert report["timing_envelope"]["tools"]["generic"]["phases_ms"]["latest_duration_ms"] == 12.5
    assert "missing_generic_tool_duration" not in {signal["code"] for signal in report["signals"]}
