from __future__ import annotations

import math
import time
from typing import Any, Dict, Literal, Mapping, Optional, Sequence, TypedDict

from scribe_mcp.progress_log_parser import Entry


CALL_TIMING_PHASES_V2: tuple[str, ...] = (
    "ingress_decode",
    "session_binding_read",
    "project_record_read",
    "target_resolution",
    "mode_resolution",
    "tool_body",
    "authority_and_validation",
    "authoritative_durability",
    "receipt_commit",
    "hooks",
    "response_format",
    "audit_append",
    "egress_serialize",
    "unaccounted",
)

_MEASURED_CALL_TIMING_PHASES = CALL_TIMING_PHASES_V2[:-1]
_CALL_TIMING_PHASES_SET = frozenset(_MEASURED_CALL_TIMING_PHASES)


class CallTimingEnvelopeV2(TypedDict):
    schema_version: Literal["call-timing-envelope.v2"]
    correlation_id: str
    phases_ms: dict[str, float]
    total_ms: float
    accounted_ratio: float
    slow_stages: list[str]
    tripwire_exceeded: bool


def _validate_correlation_id(correlation_id: str) -> str:
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise ValueError("correlation_id must be a nonblank string")
    return correlation_id


def _validate_duration(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite nonnegative number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return normalized


def _validated_call_phases(phases_ms: Mapping[str, float]) -> dict[str, float]:
    if not isinstance(phases_ms, Mapping):
        raise ValueError("phases_ms must be a mapping")
    normalized: dict[str, float] = {}
    for phase, duration in phases_ms.items():
        if not isinstance(phase, str) or phase not in _CALL_TIMING_PHASES_SET:
            raise ValueError(f"unknown or derived timing phase: {phase!r}")
        normalized[phase] = _validate_duration(duration, name=f"phases_ms[{phase!r}]")
    return normalized


def build_call_timing_envelope_v2(
    *, correlation_id: str, phases_ms: Mapping[str, float], total_ms: float
) -> CallTimingEnvelopeV2:
    correlation_id = _validate_correlation_id(correlation_id)
    total = _validate_duration(total_ms, name="total_ms")
    measured = _validated_call_phases(phases_ms)
    accounted_ms = sum(measured.values())
    unaccounted_ms = max(total - accounted_ms, 0.0)
    phases = {
        phase: (unaccounted_ms if phase == "unaccounted" else measured.get(phase, 0.0))
        for phase in CALL_TIMING_PHASES_V2
    }
    slow_stages = [
        phase for phase in _MEASURED_CALL_TIMING_PHASES if phases[phase] > 100.0
    ]
    return {
        "schema_version": "call-timing-envelope.v2",
        "correlation_id": correlation_id,
        "phases_ms": phases,
        "total_ms": total,
        "accounted_ratio": min(accounted_ms / total, 1.0) if total else 1.0,
        "slow_stages": slow_stages,
        "tripwire_exceeded": bool(slow_stages) or total > 500.0,
    }


class CallTimingRecorderV2:
    def __init__(
        self,
        *,
        correlation_id: str,
        started_perf_counter: float,
        seed_phases_ms: Mapping[str, float] | None = None,
    ) -> None:
        self._correlation_id = _validate_correlation_id(correlation_id)
        self._started_perf_counter = _validate_duration(
            started_perf_counter, name="started_perf_counter"
        )
        self._phases_ms = _validated_call_phases(seed_phases_ms or {})

    @classmethod
    def start(
        cls,
        *,
        correlation_id: str,
        started_perf_counter: float | None = None,
        seed_phases_ms: Mapping[str, float] | None = None,
    ) -> CallTimingRecorderV2:
        started = time.perf_counter() if started_perf_counter is None else started_perf_counter
        return cls(
            correlation_id=correlation_id,
            started_perf_counter=started,
            seed_phases_ms=seed_phases_ms,
        )

    def record_phase(self, phase: str, duration_ms: float) -> None:
        if not isinstance(phase, str) or phase not in _CALL_TIMING_PHASES_SET:
            raise ValueError(f"unknown or derived timing phase: {phase!r}")
        duration = _validate_duration(duration_ms, name=f"duration_ms[{phase!r}]")
        aggregate = _validate_duration(
            self._phases_ms.get(phase, 0.0) + duration,
            name=f"phases_ms[{phase!r}]",
        )
        self._phases_ms[phase] = aggregate

    def finalize(self, *, total_ms: float | None = None) -> CallTimingEnvelopeV2:
        total = (
            (time.perf_counter() - self._started_perf_counter) * 1000.0
            if total_ms is None
            else total_ms
        )
        return build_call_timing_envelope_v2(
            correlation_id=self._correlation_id,
            phases_ms=self._phases_ms,
            total_ms=total,
        )

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
