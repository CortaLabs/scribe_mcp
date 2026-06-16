from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

from scribe_mcp.config.repo_config import RepoDiscovery, resolve_runtime_efficiency_budgets
from scribe_mcp.doc_management.scaffold_quality import DEFAULT_WARNING_POLICIES
from scribe_mcp.progress_log_parser import Entry, parse_lines
from scribe_mcp.runtime_timing_envelope import build_timing_envelope_from_entries

_LOG_FRICTION_CODES: dict[str, dict[str, Any]] = {
    "LOG_MISSING_PRIORITY": {"severity": "medium", "blocking": False},
    "LOG_MISSING_CATEGORY": {"severity": "medium", "blocking": False},
    "LOG_MISSING_TAGS": {"severity": "low", "blocking": False},
}


def _severity_for(code: str) -> str:
    if code in DEFAULT_WARNING_POLICIES:
        return str(DEFAULT_WARNING_POLICIES[code].get("severity", "medium"))
    return str(_LOG_FRICTION_CODES.get(code, {}).get("severity", "medium"))


def _signal(code: str, count: int) -> Dict[str, Any]:
    return {
        "code": code,
        "count": count,
        "severity": _severity_for(code),
        "blocking": bool(DEFAULT_WARNING_POLICIES.get(code, _LOG_FRICTION_CODES.get(code, {})).get("blocking", False)),
    }


def _build_counts(entries: Sequence[Entry]) -> Dict[str, Any]:
    missing_priority = sum(1 for e in entries if e.meta.get("priority") is None)
    missing_category = sum(1 for e in entries if e.meta.get("category") is None)
    missing_tags = sum(1 for e in entries if not e.meta.get("tags"))
    generic_tool_duration_entries = sum(1 for e in entries if isinstance(e.meta.get("duration_ms"), (int, float)))
    return {
        "entries_total": len(entries),
        "missing_priority": missing_priority,
        "missing_category": missing_category,
        "missing_tags": missing_tags,
        "generic_tool_duration_entries": generic_tool_duration_entries,
    }


def _build_signals(counts: Dict[str, Any]) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    if counts["missing_priority"]:
        signals.append(_signal("LOG_MISSING_PRIORITY", int(counts["missing_priority"])))
    if counts["missing_category"]:
        signals.append(_signal("LOG_MISSING_CATEGORY", int(counts["missing_category"])))
    if counts["missing_tags"]:
        signals.append(_signal("LOG_MISSING_TAGS", int(counts["missing_tags"])))
    if counts["generic_tool_duration_entries"] == 0:
        signals.append(_signal("missing_generic_tool_duration", 1))
    return signals


def _build_next_actions(signals: Sequence[Dict[str, Any]]) -> List[str]:
    actions: List[str] = []
    codes = {str(s.get("code")) for s in signals}
    if "LOG_MISSING_PRIORITY" in codes:
        actions.append("Backfill `priority` metadata on missing entries.")
    if "LOG_MISSING_CATEGORY" in codes:
        actions.append("Backfill `category` metadata on missing entries.")
    if "LOG_MISSING_TAGS" in codes:
        actions.append("Add `tags` metadata for searchability and triage.")
    if "missing_generic_tool_duration" in codes:
        actions.append("No compatible persisted generic tool duration data was found for this log source.")
    if not actions:
        actions.append("No immediate log-friction actions; continue normal logging cadence.")
    return actions


def build_log_intelligence_report(entries: Sequence[Entry], *, scope: Dict[str, Any]) -> Dict[str, Any]:
    counts = _build_counts(entries)
    signals = _build_signals(counts)
    source_path = Path(str(scope.get("source", ""))).resolve() if scope.get("source") else None
    repo_root = RepoDiscovery.find_repo_root(source_path.parent) if source_path else None
    budgets = resolve_runtime_efficiency_budgets(repo_root)
    timing_envelope = build_timing_envelope_from_entries(
        entries,
        source=str(scope.get("source", "log_file")),
        project=scope.get("project"),
        budget_thresholds=budgets,
    )
    if counts["generic_tool_duration_entries"] == 0:
        timing_envelope["tools"]["generic"]["phases_ms"]["missing_generic_tool_duration"] = True
    return {
        "scope": scope,
        "counts": counts,
        "signals": signals,
        "next_actions": _build_next_actions(signals),
        "timing_envelope": timing_envelope,
    }


def build_report_from_path(path: str | Path, *, project: str | None = None) -> Dict[str, Any]:
    file_path = Path(path)
    raw_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    entries = parse_lines(raw_lines)
    scope = {
        "source": str(file_path),
        "project": project,
    }
    return build_log_intelligence_report(entries, scope=scope)
