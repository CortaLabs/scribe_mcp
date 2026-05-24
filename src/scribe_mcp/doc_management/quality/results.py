from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

SCHEMA_VERSION = "2026-05-24"
DEFAULT_MODE = "local_default"


def summarize_quality_warnings(warnings: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    severity_counts: Dict[str, int] = {}
    blocked = 0
    warning_codes: list[str] = []
    for warning in warnings:
        severity = str(warning.get("severity") or "unknown")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        if bool(warning.get("blocking")):
            blocked += 1
        code = str(warning.get("code") or "").strip()
        if code:
            warning_codes.append(code)
    return {
        "total_warnings": len(warnings),
        "severity_counts": severity_counts,
        "readiness_blocker_count": blocked,
        "warning_codes": sorted(set(warning_codes)),
    }


def normalize_warning_entry(warning: Mapping[str, Any]) -> Dict[str, Any]:
    entry = dict(warning)
    entry.setdefault("category", "scaffold")
    entry.setdefault("gate_scope", "quality_check")
    entry.setdefault("scope_kind", "document")
    entry.setdefault("suppressible", True)
    entry.setdefault("source_owner", "doc_management")
    entry.setdefault("rule_version", "v1")
    return entry


def normalize_warnings(warnings: Sequence[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    normalized = [normalize_warning_entry(warning) for warning in warnings]
    normalized.sort(
        key=lambda item: (
            str(item.get("severity") or ""),
            str(item.get("code") or ""),
            int((item.get("location") or {}).get("line", 0)) if isinstance(item.get("location"), dict) else 0,
        )
    )
    return normalized
