from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

UNSUPPRESSIBLE_BLOCKER_CODES = {
    "SCF_PLACEHOLDER_BRACKET",
    "SCF_TEMPLATE_PROSE",
    "SCF_EMPTY_FINDING",
    "SCF_UNFILLED_APPENDIX",
    "SCF_TODO_ONLY_SECTION",
    "SCF_LOG_TEMPLATE_ONLY",
    "SCF_FRONTMATTER_MISMATCH",
    "SCF_LIFECYCLE_STATUS_MISMATCH",
    "SCF_CHANGELOG_ENTRY_ID_MISSING",
    "SCF_CHANGELOG_ENTRY_ID_INVALID",
    "SCF_CHANGELOG_SUMMARY_MISSING",
    "SCF_CHANGELOG_EVIDENCE_MISSING",
    "SCF_CHANGELOG_DUPLICATE_SOURCE_KEY",
    "SCF_CHANGELOG_RAW_PROGRESS_DUMP",
    "SCF_CHANGELOG_AMBIGUOUS_BODY_STATUS",
    "SCF_CHANGELOG_ESCAPED_NEWLINES",
    "SCF_CHANGELOG_CURRENT_VERSION_MISSING",
}


def resolve_quality_mode(*, metadata: Mapping[str, Any] | None, project_root: Path | None = None) -> dict[str, Any]:
    quality = (metadata or {}).get("quality") if isinstance((metadata or {}).get("quality"), dict) else {}
    explicit_mode = str(quality.get("mode") or "").strip()
    release_trigger = quality.get("release_trigger")
    if explicit_mode == "release_gate":
        return {
            "mode": "release_gate",
            "release_trigger": str(release_trigger or "explicit_mode_release_gate"),
            "trigger_source": "explicit",
            "release_triggers": [str(release_trigger or "explicit_mode_release_gate")],
        }

    inferred_triggers: list[str] = []
    if isinstance(release_trigger, str) and release_trigger.strip():
        inferred_triggers.append(f"metadata.release_trigger:{release_trigger.strip()}")
    if project_root is not None and (project_root / "pyproject.toml").exists():
        inferred_triggers.append("repo.pyproject_present")

    if inferred_triggers and quality.get("infer_release_gate") is True:
        return {
            "mode": "release_gate",
            "release_trigger": inferred_triggers[0],
            "trigger_source": "inferred",
            "release_triggers": inferred_triggers,
        }

    return {"mode": "local_default", "release_trigger": None, "trigger_source": "default", "release_triggers": []}
