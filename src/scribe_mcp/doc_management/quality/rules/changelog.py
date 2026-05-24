from __future__ import annotations

import re
from typing import Any, Dict, List

from scribe_mcp.doc_management.changelog import accepted_entries, is_valid_entry_id, parse_changelog_entries

_PROGRESS_PREFIX_PATTERN = re.compile(
    r"^\s*\[(?:✅|☑️|❌|⚠️|ℹ️)\]\s*\[[^\]]+\]\s*\[[^\]]+\]\s*\[[^\]]+\]"
)


def build_changelog_structure_warnings(
    *,
    text: str,
    warning_builder,
) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    escaped_newline_count = text.count("\\n")
    has_escaped_newline_sludge = escaped_newline_count >= 3 and any(
        marker in text
        for marker in (
            "# Project Changelog\\n",
            "Use one section per curated project outcome.\\n",
            "## Entry Template\\n",
            "- `entry_id`:",
            "- `entry_status`:",
            "- `summary`:",
            "- `evidence_refs`:",
        )
    )
    if has_escaped_newline_sludge:
        warnings.append(
            warning_builder(
                "SCF_CHANGELOG_ESCAPED_NEWLINES",
                "Changelog content appears serialized with literal escaped newlines.",
                text,
                0,
                "Rewrite changelog with real multiline markdown instead of literal \\n escape sequences.",
            )
        )

    entries = accepted_entries(parse_changelog_entries(text))
    seen_keys: set[str] = set()
    for entry in entries:
        marker = f"entry_id: {entry.entry_id}" if entry.entry_id else entry.title or "accepted-entry"
        idx = text.find(marker)
        idx = 0 if idx < 0 else idx
        if not entry.entry_id:
            warnings.append(warning_builder("SCF_CHANGELOG_ENTRY_ID_MISSING", "Accepted changelog entry is missing entry_id.", text, idx, "Add entry_id in <yyyymmdd>:<slug> format."))
        elif not is_valid_entry_id(entry.entry_id):
            warnings.append(warning_builder("SCF_CHANGELOG_ENTRY_ID_INVALID", "Accepted changelog entry has invalid entry_id format.", text, idx, "Use entry_id format <yyyymmdd>:<slug>."))
        if not entry.summary:
            warnings.append(warning_builder("SCF_CHANGELOG_SUMMARY_MISSING", "Accepted changelog entry is missing summary.", text, idx, "Add a concise summary for accepted entry."))
        if not entry.evidence_refs:
            warnings.append(warning_builder("SCF_CHANGELOG_EVIDENCE_MISSING", "Accepted changelog entry is missing evidence_refs.", text, idx, "Add one or more concrete evidence_refs entries."))
        if entry.entry_id in seen_keys and entry.entry_id:
            warnings.append(warning_builder("SCF_CHANGELOG_DUPLICATE_SOURCE_KEY", "Duplicate changelog source key detected for accepted entries.", text, idx, "Keep one authoritative entry per (project_slug, entry_id)."))
        seen_keys.add(entry.entry_id)
        if _PROGRESS_PREFIX_PATTERN.search(entry.section_text) or "[agent:" in entry.section_text.lower():
            warnings.append(warning_builder("SCF_CHANGELOG_RAW_PROGRESS_DUMP", "Accepted changelog entry looks like a raw progress-log dump.", text, idx, "Curate a human-authored changelog summary instead of dumping log lines."))
        if re.search(r"(?im)^\s*status\s*:\s*accepted\s*$", entry.section_text):
            warnings.append(warning_builder("SCF_CHANGELOG_AMBIGUOUS_BODY_STATUS", "Accepted entry uses ambiguous body lifecycle text ('Status: accepted').", text, idx, "Use entry_status for changelog entry state and keep lifecycle status in frontmatter only."))

    return warnings
