from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from scribe_mcp.doc_management.scaffold_quality import (
    collect_managed_doc_quality_warnings,
    configured_log_quality_exclusion_paths,
    is_managed_doc_quality_target,
)

FUTURE_PHASE_PREFIXES = ("phase 2", "phase 3", "phase 4", "phase 5", "phase 6", "phase 7", "phase 8", "phase 9")


@dataclass(frozen=True)
class ReadinessSummary:
    current_phase: Optional[str]
    managed_doc_quality: Dict[str, Any]
    log_friction: Dict[str, Any]
    warning_count: int
    blocker_count: int
    next_actions: list[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_phase": self.current_phase,
            "managed_doc_quality": self.managed_doc_quality,
            "log_friction": self.log_friction,
            "warning_count": self.warning_count,
            "blocker_count": self.blocker_count,
            "next_actions": self.next_actions,
        }


def _is_future_phase_warning(current_phase: Optional[str], warning: Mapping[str, Any]) -> bool:
    if not current_phase:
        return False
    excerpt = str(warning.get("excerpt") or "").lower()
    code = str(warning.get("code") or "")
    if code not in {"SCF_INDEX_STALE", "SCF_INDEX_MISSING", "SCF_DOC_UNINDEXED"}:
        return False
    if "phase" not in excerpt:
        return False
    return any(prefix in excerpt and prefix not in current_phase.lower() for prefix in FUTURE_PHASE_PREFIXES)


def collect_managed_doc_quality_state(project: Mapping[str, Any]) -> Dict[str, Any]:
    docs = project.get("docs", {}) if isinstance(project.get("docs"), dict) else {}
    configured_log_paths = configured_log_quality_exclusion_paths(project)
    current_phase = str(project.get("current_phase") or "").strip() or None

    documents: list[dict[str, Any]] = []
    blocker_count = 0
    frontmatter_mismatch_count = 0
    stale_research_index_count = 0
    total_warnings = 0

    for key, doc_path in docs.items():
        if not isinstance(doc_path, str) or not doc_path.endswith(".md"):
            continue
        if not is_managed_doc_quality_target(str(key), doc_path, configured_log_paths=configured_log_paths):
            continue
        path = Path(doc_path)
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        warnings = collect_managed_doc_quality_warnings(text=text, doc_name=str(key), path=path, project=project)
        total_warnings += len(warnings)
        blockers = []
        for warning in warnings:
            code = str(warning.get("code") or "")
            if code == "SCF_FRONTMATTER_MISMATCH":
                frontmatter_mismatch_count += 1
            if code in {"SCF_INDEX_STALE", "SCF_INDEX_MISSING", "SCF_DOC_UNINDEXED"}:
                stale_research_index_count += 1
            if bool(warning.get("blocking")) and not _is_future_phase_warning(current_phase, warning):
                blockers.append(warning)

        blocker_count += len(blockers)
        documents.append(
            {
                "doc_name": str(key),
                "path": str(path),
                "warning_codes": [w.get("code") for w in warnings],
                "readiness_blocker_codes": [w.get("code") for w in blockers],
            }
        )

    return {
        "status": "blocked" if blocker_count else "pass",
        "readiness_blocker_count": blocker_count,
        "frontmatter_mismatch_count": frontmatter_mismatch_count,
        "stale_research_index_count": stale_research_index_count,
        "total_warning_count": total_warnings,
        "documents": documents,
    }


def build_readiness_summary(*, current_phase: Optional[str], managed_doc_quality: Dict[str, Any], log_signals: Optional[Sequence[Mapping[str, Any]]] = None) -> ReadinessSummary:
    log_signals = list(log_signals or [])
    log_blockers = sum(1 for signal in log_signals if bool(signal.get("blocking")))
    warning_count = int(managed_doc_quality.get("total_warning_count", 0)) + len(log_signals)
    blocker_count = int(managed_doc_quality.get("readiness_blocker_count", 0)) + log_blockers
    log_friction = {
        "status": "warn" if log_signals else "pass",
        "signals": [dict(signal) for signal in log_signals],
    }
    next_actions: list[str] = []
    if managed_doc_quality.get("readiness_blocker_count", 0):
        next_actions.append("Resolve SCF_* readiness blockers in managed docs for the active phase.")
    if log_signals:
        next_actions.append("Address LOG_* progress-log friction signals to improve trace quality.")
    if not next_actions:
        next_actions.append("Readiness checks are green for current phase scope.")

    return ReadinessSummary(
        current_phase=current_phase,
        managed_doc_quality=managed_doc_quality,
        log_friction=log_friction,
        warning_count=warning_count,
        blocker_count=blocker_count,
        next_actions=next_actions,
    )
