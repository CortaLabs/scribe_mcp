from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from scribe_mcp.progress_log_parser import Entry

DEFAULT_RUNTIME_EFFICIENCY_BUDGETS: Dict[str, Dict[str, float]] = {
    "cold_start_ms": {"warn": 5800.0, "fail": 7000.0},
    "warm_bound_call_ms": {"warn": 600.0, "fail": 1200.0},
    "set_project_total_ms": {"warn": 17292.0, "fail": 22000.0},
}


def _metric_value_from_envelope(
    *,
    startup_phases_ms: Optional[Mapping[str, float]],
    set_project_phase_ms: Optional[Mapping[str, float]],
    dispatch_path: Optional[str],
    startup_profile: Optional[str],
) -> Dict[str, Optional[float]]:
    startup = dict(startup_phases_ms or {})
    set_project = dict(set_project_phase_ms or {})
    return {
        "cold_start_ms": float(startup.get("total_ms")) if isinstance(startup.get("total_ms"), (int, float)) else None,
        "warm_bound_call_ms": float(startup.get("total_ms"))
        if dispatch_path == "bound_server" and startup_profile == "bound_server" and isinstance(startup.get("total_ms"), (int, float))
        else None,
        "set_project_total_ms": float(set_project.get("total_ms")) if isinstance(set_project.get("total_ms"), (int, float)) else None,
    }


def build_runtime_efficiency_budget_status(
    *,
    startup_phases_ms: Optional[Mapping[str, float]],
    set_project_phase_ms: Optional[Mapping[str, float]],
    dispatch_path: Optional[str],
    startup_profile: Optional[str],
    budget_thresholds: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> Dict[str, Any]:
    thresholds = dict(budget_thresholds or DEFAULT_RUNTIME_EFFICIENCY_BUDGETS)
    values = _metric_value_from_envelope(
        startup_phases_ms=startup_phases_ms,
        set_project_phase_ms=set_project_phase_ms,
        dispatch_path=dispatch_path,
        startup_profile=startup_profile,
    )
    metrics: Dict[str, Dict[str, Any]] = {}
    for metric_name, metric_value in values.items():
        threshold = thresholds.get(metric_name) or {}
        warn = threshold.get("warn")
        fail = threshold.get("fail")
        status = "unknown"
        if metric_value is not None and isinstance(warn, (int, float)) and isinstance(fail, (int, float)):
            if metric_value > float(fail):
                status = "over_budget"
            elif metric_value > float(warn):
                status = "near_budget"
            else:
                status = "within_budget"
        metrics[metric_name] = {
            "value_ms": metric_value,
            "warn_ms": float(warn) if isinstance(warn, (int, float)) else None,
            "fail_ms": float(fail) if isinstance(fail, (int, float)) else None,
            "status": status,
        }
    return {"schema_version": "runtime-efficiency-budget.v1", "metrics": metrics}


def build_timing_envelope(
    *,
    dispatch_path: Optional[str] = None,
    startup_profile: Optional[str] = None,
    startup_phases_ms: Optional[Mapping[str, float]] = None,
    set_project_phase_ms: Optional[Mapping[str, float]] = None,
    tool_phase_ms: Optional[Mapping[str, float]] = None,
    budget_thresholds: Optional[Mapping[str, Mapping[str, float]]] = None,
    source: str,
) -> Dict[str, Any]:
    budget_status = build_runtime_efficiency_budget_status(
        startup_phases_ms=startup_phases_ms,
        set_project_phase_ms=set_project_phase_ms,
        dispatch_path=dispatch_path,
        startup_profile=startup_profile,
        budget_thresholds=budget_thresholds,
    )
    return {
        "schema_version": "timing-envelope.v1",
        "path": {
            "dispatch": dispatch_path or "unknown",
            "temperature": "warm-ish" if dispatch_path == "bound_server" else ("cold-ish" if dispatch_path else "unknown"),
            "startup_profile": startup_profile or "unknown",
        },
        "startup": {
            "phases_ms": dict(startup_phases_ms or {}),
        },
        "tools": {
            "set_project": {"phases_ms": dict(set_project_phase_ms or {})},
            "generic": {"phases_ms": dict(tool_phase_ms or {})},
        },
        "provenance": {
            "source": source,
            "known_fields": sorted(
                [
                    key
                    for key, value in {
                        "dispatch_path": dispatch_path,
                        "startup_profile": startup_profile,
                        "startup_phases_ms": startup_phases_ms,
                        "set_project_phase_ms": set_project_phase_ms,
                        "tool_phase_ms": tool_phase_ms,
                    }.items()
                    if value
                ]
            ),
        },
        "budget_status": budget_status,
    }


def build_timing_envelope_from_entries(
    entries: Sequence[Entry], *, source: str, project: Optional[str], budget_thresholds: Optional[Mapping[str, Mapping[str, float]]] = None
) -> Dict[str, Any]:
    dispatch_path: Optional[str] = None
    startup_profile: Optional[str] = None
    set_project_phase_ms: Dict[str, float] = {}
    tool_phase_ms: Dict[str, float | bool] = {}

    for entry in entries:
        if project and entry.project and entry.project != project:
            continue
        if isinstance(entry.meta.get("dispatch_path"), str):
            dispatch_path = str(entry.meta.get("dispatch_path"))
        if isinstance(entry.meta.get("startup_profile"), str):
            startup_profile = str(entry.meta.get("startup_profile"))
        if entry.message.lower().startswith("perf set_project"):
            for key, value in entry.meta.items():
                if key.endswith("_ms") and isinstance(value, (int, float)):
                    set_project_phase_ms[key] = float(value)
        if isinstance(entry.meta.get("duration_ms"), (int, float)):
            tool_phase_ms["latest_duration_ms"] = float(entry.meta["duration_ms"])
        elif str(entry.meta.get("missing_generic_tool_duration", "")).lower() == "true":
            tool_phase_ms["missing_generic_tool_duration"] = True

    return build_timing_envelope(
        dispatch_path=dispatch_path,
        startup_profile=startup_profile,
        set_project_phase_ms=set_project_phase_ms,
        tool_phase_ms=tool_phase_ms,
        budget_thresholds=budget_thresholds,
        source=source,
    )
