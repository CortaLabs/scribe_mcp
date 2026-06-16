from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Sequence

SCHEMA_VERSION = "2026-05-24"
DEFAULT_MODE = "local_default"
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_BODY_RELATIVE_CODES = {
    "SCF_PLACEHOLDER_BRACKET",
    "SCF_TEMPLATE_PROSE",
    "SCF_EMPTY_FINDING",
    "SCF_UNFILLED_APPENDIX",
    "SCF_TODO_ONLY_SECTION",
    "SCF_LOG_TEMPLATE_ONLY",
    "SCF_FRONTMATTER_MISMATCH",
    "SCF_LIFECYCLE_STATUS_MISMATCH",
    "SCF_TRAILING_WHITESPACE",
    "SCF_FAILED_WRITE_RESIDUE",
}


def summarize_quality_warnings(warnings: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    severity_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    warning_counts_by_code: Dict[str, int] = {}
    blocking_warning_counts_by_code: Dict[str, int] = {}
    repair_kind_counts: Dict[str, int] = {}
    blocked = 0
    warning_codes: list[str] = []
    highest_severity = "pass"
    actionable = 0
    for warning in warnings:
        severity = str(warning.get("severity") or "unknown")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        if _SEVERITY_RANK.get(severity.lower(), 4) < _SEVERITY_RANK.get(highest_severity, 5):
            highest_severity = severity
        category = str(warning.get("category") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        repair_kind = str(warning.get("repair_kind") or "unknown")
        repair_kind_counts[repair_kind] = repair_kind_counts.get(repair_kind, 0) + 1
        if bool(warning.get("blocking")):
            blocked += 1
        code = str(warning.get("code") or "").strip()
        if code:
            warning_codes.append(code)
            warning_counts_by_code[code] = warning_counts_by_code.get(code, 0) + 1
            if bool(warning.get("blocking")):
                blocking_warning_counts_by_code[code] = blocking_warning_counts_by_code.get(code, 0) + 1
        if isinstance(warning.get("suggested_repair"), str) and str(warning.get("suggested_repair")).strip():
            actionable += 1
    return {
        "total_warnings": len(warnings),
        "severity_counts": severity_counts,
        "category_counts": dict(sorted(category_counts.items())),
        "readiness_blocker_count": blocked,
        "warning_codes": sorted(set(warning_codes)),
        "warning_counts_by_code": dict(sorted(warning_counts_by_code.items())),
        "blocking_warning_counts_by_code": dict(sorted(blocking_warning_counts_by_code.items())),
        "repair_kind_counts": dict(sorted(repair_kind_counts.items())),
        "highest_severity": highest_severity,
        "has_blockers": blocked > 0,
        "actionable_warning_count": actionable,
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
            _SEVERITY_RANK.get(str(item.get("severity") or "").lower(), 4),
            str(item.get("code") or ""),
            int((item.get("location") or {}).get("line", 0)) if isinstance(item.get("location"), dict) else 0,
        )
    )
    return normalized


def _frontmatter_body_start_line(text: str) -> int:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return 1
    for index, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return index + 1
    return 1


def _slug_heading(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "section"


def _heading_outline(lines: Sequence[str], *, file_line_offset: int = 0) -> list[Dict[str, Any]]:
    outline: list[Dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        heading = match.group(2).strip().strip("#").strip()
        outline.append(
            {
                "id": _slug_heading(heading),
                "heading": heading,
                "level": len(match.group(1)),
                "line": line_number,
                "file_line": file_line_offset + line_number,
            }
        )
    return outline


def _nearest_section(outline: Sequence[Mapping[str, Any]], *, line: int) -> Dict[str, Any] | None:
    section: Mapping[str, Any] | None = None
    for candidate in outline:
        try:
            candidate_line = int(candidate.get("line", 0))
        except (TypeError, ValueError):
            candidate_line = 0
        if candidate_line <= line:
            section = candidate
        else:
            break
    return dict(section) if section is not None else None


def _repair_profile_for_warning(warning: Mapping[str, Any]) -> Dict[str, str]:
    code = str(warning.get("code") or "")
    repair = str(warning.get("suggested_repair") or "").lower()
    if code in {"SCF_FRONTMATTER_MISMATCH", "SCF_LIFECYCLE_STATUS_MISMATCH"}:
        return {"repair_kind": "lifecycle_alignment", "edit_action_hint": "frontmatter_update"}
    if code == "SCF_NONCANONICAL_LOCATION":
        return {"repair_kind": "artifact_rehome", "edit_action_hint": "rehome_doc"}
    if code in {"SCF_INDEX_STALE", "SCF_INDEX_MISSING", "SCF_DOC_UNINDEXED"}:
        return {"repair_kind": "index_refresh", "edit_action_hint": "managed_doc_mutation"}
    if code.startswith("SCF_CHANGELOG_"):
        return {"repair_kind": "changelog_curation", "edit_action_hint": "replace_section"}
    if code == "SCF_FAILED_WRITE_RESIDUE":
        return {"repair_kind": "residue_cleanup", "edit_action_hint": "replace_text"}
    if code == "SCF_TRAILING_WHITESPACE":
        return {"repair_kind": "format_cleanup", "edit_action_hint": "apply_patch"}
    if "frontmatter" in repair:
        return {"repair_kind": "lifecycle_alignment", "edit_action_hint": "frontmatter_update"}
    if "index" in repair:
        return {"repair_kind": "index_refresh", "edit_action_hint": "managed_doc_mutation"}
    return {"repair_kind": "content_completion", "edit_action_hint": "replace_range"}


def enrich_quality_warning_context(warnings: Sequence[Mapping[str, Any]], *, text: str) -> list[Dict[str, Any]]:
    body_start_line = _frontmatter_body_start_line(text)
    all_lines = text.splitlines()
    body_lines = all_lines[body_start_line - 1 :]
    body_outline = _heading_outline(body_lines, file_line_offset=body_start_line - 1)
    document_outline = _heading_outline(all_lines)
    enriched: list[Dict[str, Any]] = []

    for warning in warnings:
        entry = dict(warning)
        code = str(entry.get("code") or "")
        loc = entry.get("location") if isinstance(entry.get("location"), Mapping) else {}
        try:
            source_line = int(loc.get("line", 0))
        except (TypeError, ValueError):
            source_line = 0
        try:
            source_column = int(loc.get("column", 1))
        except (TypeError, ValueError):
            source_column = 1

        body_relative = code in _BODY_RELATIVE_CODES
        file_line = body_start_line + source_line - 1 if body_relative and source_line > 0 else source_line
        section = _nearest_section(body_outline if body_relative else document_outline, line=source_line)
        profile = _repair_profile_for_warning(entry)
        entry.update(profile)
        entry["location_basis"] = "body_relative" if body_relative else "document"
        entry["file_location"] = {
            "line": file_line,
            "column": source_column,
            "source_line": source_line,
            "source_basis": entry["location_basis"],
        }
        entry["section"] = section
        entry["provenance"] = {
            "derived_from": ["normalized_warning", "document_outline"],
            "body_start_line": body_start_line,
        }
        enriched.append(entry)
    return enriched


def group_quality_warnings(
    warnings: Sequence[Mapping[str, Any]],
    *,
    max_lines_per_group: int = 5,
    max_messages_per_group: int = 2,
) -> list[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    line_sets: Dict[str, set[int]] = {}
    document_sets: Dict[str, set[str]] = {}
    for warning in warnings:
        code = str(warning.get("code") or "UNKNOWN").strip() or "UNKNOWN"
        group = groups.setdefault(
            code,
            {
                "code": code,
                "count": 0,
                "blocking_count": 0,
                "severity": str(warning.get("severity") or "unknown"),
                "category": str(warning.get("category") or "unknown"),
                "suggested_repair": None,
                "repair_kind": None,
                "edit_action_hint": None,
                "first_location": None,
                "first_file_location": None,
                "first_excerpt": None,
                "message_samples": [],
                "affected_lines": [],
                "sections": [],
                "documents": [],
                "document_count": 0,
            },
        )
        group["count"] = int(group["count"]) + 1
        if bool(warning.get("blocking")):
            group["blocking_count"] = int(group["blocking_count"]) + 1

        severity = str(warning.get("severity") or "unknown")
        if _SEVERITY_RANK.get(severity.lower(), 4) < _SEVERITY_RANK.get(str(group.get("severity") or "").lower(), 4):
            group["severity"] = severity

        if group.get("first_location") is None and isinstance(warning.get("location"), Mapping):
            group["first_location"] = dict(warning["location"])
        if group.get("first_file_location") is None and isinstance(warning.get("file_location"), Mapping):
            group["first_file_location"] = dict(warning["file_location"])
        if group.get("first_excerpt") is None and isinstance(warning.get("excerpt"), str):
            group["first_excerpt"] = str(warning["excerpt"])
        if group.get("suggested_repair") is None and isinstance(warning.get("suggested_repair"), str) and str(warning.get("suggested_repair")).strip():
            group["suggested_repair"] = str(warning["suggested_repair"])
        if group.get("repair_kind") is None and isinstance(warning.get("repair_kind"), str):
            group["repair_kind"] = str(warning["repair_kind"])
        if group.get("edit_action_hint") is None and isinstance(warning.get("edit_action_hint"), str):
            group["edit_action_hint"] = str(warning["edit_action_hint"])

        section = warning.get("section")
        sections = group["sections"]
        if isinstance(section, Mapping) and section not in sections:
            sections.append(dict(section))

        doc_name = str(warning.get("doc_name") or "").strip()
        path = str(warning.get("path") or "").strip()
        if doc_name or path:
            document_key = f"{doc_name}\0{path}"
            seen_documents = document_sets.setdefault(code, set())
            if document_key not in seen_documents:
                seen_documents.add(document_key)
                document: Dict[str, Any] = {}
                if doc_name:
                    document["doc_name"] = doc_name
                if path:
                    document["path"] = path
                documents = group["documents"]
                documents.append(document)
                group["document_count"] = len(documents)

        message = str(warning.get("message") or "").strip()
        messages = group["message_samples"]
        if message and message not in messages and len(messages) < max_messages_per_group:
            messages.append(message)

        loc = warning.get("file_location") if isinstance(warning.get("file_location"), Mapping) else warning.get("location")
        if isinstance(loc, Mapping):
            try:
                line = int(loc.get("line", 0))
            except (TypeError, ValueError):
                line = 0
            if line > 0:
                line_set = line_sets.setdefault(code, set())
                line_set.add(line)
                group["affected_lines"] = sorted(line_set)[:max_lines_per_group]

    return sorted(
        groups.values(),
        key=lambda item: (
            _SEVERITY_RANK.get(str(item.get("severity") or "").lower(), 4),
            -int(item.get("blocking_count") or 0),
            -int(item.get("count") or 0),
            str(item.get("code") or ""),
        ),
    )


def build_quality_agent_actions(
    warning_groups: Sequence[Mapping[str, Any]],
    *,
    max_items: int = 5,
) -> list[Dict[str, Any]]:
    actions: list[Dict[str, Any]] = []
    for group in warning_groups:
        repair = str(group.get("suggested_repair") or "").strip()
        if not repair:
            continue
        blocking = int(group.get("blocking_count") or 0) > 0
        messages = group.get("message_samples")
        summary = messages[0] if isinstance(messages, list) and messages else f"Resolve {group.get('code')}."
        actions.append(
            {
                "rank": len(actions) + 1,
                "code": group.get("code"),
                "severity": group.get("severity"),
                "blocking": blocking,
                "count": group.get("count"),
                "summary": summary,
                "suggested_repair": repair,
                "repair_kind": group.get("repair_kind"),
                "edit_action_hint": group.get("edit_action_hint"),
                "first_location": group.get("first_location"),
                "first_file_location": group.get("first_file_location"),
                "section": group.get("sections", [None])[0] if group.get("sections") else None,
                "affected_lines": group.get("affected_lines", []),
                "documents": list(group.get("documents") or []),
                "document_count": int(group.get("document_count") or 0),
            }
        )
        if len(actions) >= max_items:
            break
    return actions
