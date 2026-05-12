from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.doc_management.changelog import accepted_entries, is_valid_entry_id, parse_changelog_entries
from scribe_mcp.doc_management.version_context import resolve_observed_context

_READINESS_VALUES = {"ready", "done", "complete", "finished"}

DEFAULT_WARNING_POLICIES: Dict[str, Dict[str, Any]] = {
    "SCF_PLACEHOLDER_BRACKET": {"severity": "critical", "blocking": True},
    "SCF_TEMPLATE_PROSE": {"severity": "high", "blocking": True},
    "SCF_EMPTY_FINDING": {"severity": "high", "blocking": True},
    "SCF_UNFILLED_APPENDIX": {"severity": "high", "blocking": True},
    "SCF_TODO_ONLY_SECTION": {"severity": "high", "blocking": True},
    "SCF_LOG_TEMPLATE_ONLY": {"severity": "high", "blocking": True},
    "SCF_FRONTMATTER_MISMATCH": {"severity": "critical", "blocking": True},
    "SCF_LIFECYCLE_STATUS_MISMATCH": {"severity": "critical", "blocking": True},
    "SCF_INDEX_STALE": {"severity": "medium", "blocking": False},
    "SCF_INDEX_MISSING": {"severity": "medium", "blocking": False},
    "SCF_DOC_UNINDEXED": {"severity": "medium", "blocking": False},
    "SCF_NONCANONICAL_LOCATION": {"severity": "medium", "blocking": False},
    "SCF_CHANGELOG_ENTRY_ID_MISSING": {"severity": "critical", "blocking": True},
    "SCF_CHANGELOG_ENTRY_ID_INVALID": {"severity": "critical", "blocking": True},
    "SCF_CHANGELOG_SUMMARY_MISSING": {"severity": "critical", "blocking": True},
    "SCF_CHANGELOG_EVIDENCE_MISSING": {"severity": "critical", "blocking": True},
    "SCF_CHANGELOG_DUPLICATE_SOURCE_KEY": {"severity": "critical", "blocking": True},
    "SCF_CHANGELOG_RAW_PROGRESS_DUMP": {"severity": "critical", "blocking": True},
    "SCF_CHANGELOG_AMBIGUOUS_BODY_STATUS": {"severity": "critical", "blocking": True},
    "SCF_CHANGELOG_ESCAPED_NEWLINES": {"severity": "critical", "blocking": True},
    "SCF_RESEARCH_CONTEXT_DRIFT": {"severity": "medium", "blocking": False},
}

_TEMPLATE_PROSE_PATTERNS = [
    r"\breplace\s+this\s+with\b",
    r"\bfill\s+in\s+this\s+section\b",
    r"\bplaceholder\s+text\b",
    r"\btemplate\s+instruction\b",
    r"\badd\s+details\s+here\b",
]

_NON_READINESS_DOC_KEYS = {"progress_log", "tool_log", "audit_log"}
_NON_READINESS_DOC_FILENAMES = {"PROGRESS_LOG.md", "TOOL_LOG.md", "AUDIT_LOG.md"}
_PROGRESS_PREFIX_PATTERN = re.compile(
    r"^\s*\[(?:✅|☑️|❌|⚠️|ℹ️)\]\s*\[[^\]]+\]\s*\[[^\]]+\]\s*\[[^\]]+\]"
)


def configured_log_quality_exclusion_paths(project: Mapping[str, Any]) -> set[Path]:
    """Resolve configured log files that should not block managed-doc readiness."""
    paths: set[Path] = set()
    progress_log = project.get("progress_log") if isinstance(project, Mapping) else None
    if isinstance(progress_log, str) and progress_log.strip():
        paths.add(Path(progress_log).expanduser().resolve())

    try:
        from scribe_mcp.config.log_config import load_log_config, resolve_log_path

        repo_root = project.get("root") if isinstance(project, Mapping) else None
        for definition in load_log_config(repo_root).values():
            if not isinstance(definition, Mapping):
                continue
            paths.add(resolve_log_path(dict(project), dict(definition)).expanduser().resolve())
    except Exception:
        pass
    return paths


def is_managed_doc_quality_target(
    doc_name: str,
    path: str | Path | None = None,
    *,
    configured_log_paths: Optional[set[Path]] = None,
) -> bool:
    """Return whether a managed doc should affect readiness-quality aggregation."""
    normalized_name = str(doc_name or "").strip().lower().replace("-", "_")
    if normalized_name in _NON_READINESS_DOC_KEYS:
        return False
    if path is not None:
        resolved = Path(path).expanduser().resolve()
        if configured_log_paths and resolved in configured_log_paths:
            return False
        filename = resolved.name
        if filename in _NON_READINESS_DOC_FILENAMES:
            return False
    return True


def is_research_doc_target(doc_name: str, path: str | Path | None = None) -> bool:
    normalized_name = str(doc_name or "").strip().upper()
    if normalized_name.startswith("RESEARCH_"):
        return True
    if path is None:
        return False
    try:
        return "research" in {part.lower() for part in Path(path).parts}
    except TypeError:
        return False


def _line_loc(text: str, idx: int) -> Dict[str, int]:
    line = text.count("\n", 0, idx) + 1
    col = idx - (text.rfind("\n", 0, idx) + 1) + 1
    return {"line": line, "column": col}


def _in_code_fence(text: str, idx: int) -> bool:
    return text[:idx].count("```") % 2 == 1


def _is_quoted_line(text: str, idx: int) -> bool:
    start = text.rfind("\n", 0, idx) + 1
    line = text[start:text.find("\n", idx) if text.find("\n", idx) != -1 else len(text)]
    return line.lstrip().startswith(">")


def _line_text(text: str, idx: int) -> str:
    start = text.rfind("\n", 0, idx) + 1
    end = text.find("\n", idx)
    if end == -1:
        end = len(text)
    return text[start:end]


def _strip_markdown_status_markup(line: str) -> str:
    stripped = line.strip()
    stripped = re.sub(r"^\s{0,3}#{1,6}\s+", "", stripped)
    stripped = re.sub(r"^\s*[-*]\s+", "", stripped)
    stripped = stripped.strip()
    stripped = stripped.replace("**", "").replace("__", "").strip("*_` ")
    return stripped.strip()


def _warning(code: str, message: str, text: str, idx: int, repair: str, suppression_reason: Optional[str] = None) -> Dict[str, Any]:
    policy = DEFAULT_WARNING_POLICIES[code]
    payload: Dict[str, Any] = {
        "code": code,
        "severity": policy["severity"],
        "blocking": bool(policy["blocking"]),
        "location": _line_loc(text, idx),
        "message": message,
        "suggested_repair": repair,
    }
    if suppression_reason:
        payload["suppression_reason"] = suppression_reason
    return payload


def _excerpt(text: str, idx: int) -> str:
    return _line_text(text, idx).strip()[:160]


def _is_checklist_marker(line: str, match_start: int) -> bool:
    # Suppress only canonical Markdown checklist markers: "- [ ]" / "- [x]" / "- [X]".
    return bool(re.match(r"^\s*-\s+\[[ xX]\]\s*$", line.strip()))


def _is_progress_prefix_bracket(line: str, match_start: int) -> bool:
    if not _PROGRESS_PREFIX_PATTERN.match(line.strip()):
        return False
    return line[:match_start].count("[") < 4


def _is_markdown_link_label(line: str, match_start: int, match_end: int) -> bool:
    match_body = line[match_start:match_end]
    escaped = re.escape(match_body)
    for candidate in re.finditer(rf"{escaped}\([^)]+\)", line):
        if candidate.start() == match_start:
            return True
    return False


def summarize_quality_warnings(warnings: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    severity_counts: Dict[str, int] = {}
    blocked = 0
    for warning in warnings:
        severity = str(warning.get("severity") or "unknown")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        if bool(warning.get("blocking")):
            blocked += 1
    return {
        "total_warnings": len(warnings),
        "severity_counts": severity_counts,
        "readiness_blocker_count": blocked,
    }


def _apply_quality_overrides(
    warnings: List[Dict[str, Any]],
    *,
    metadata: Optional[Mapping[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    cfg = (metadata or {}).get("quality") if isinstance((metadata or {}).get("quality"), dict) else {}
    include_suppressed = bool(cfg.get("include_suppressed", False))
    enabled_codes = cfg.get("enabled_codes")
    severity_overrides = cfg.get("severity_overrides") if isinstance(cfg.get("severity_overrides"), dict) else {}
    blocking_overrides = cfg.get("blocking_overrides") if isinstance(cfg.get("blocking_overrides"), dict) else {}
    suppressions = cfg.get("suppressions") if isinstance(cfg.get("suppressions"), dict) else {}
    active_codes = {str(c).strip() for c in enabled_codes if str(c).strip()} if isinstance(enabled_codes, list) else None

    visible: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []
    for warning in warnings:
        code = str(warning.get("code") or "")
        entry = dict(warning)
        if active_codes is not None and code not in active_codes:
            entry["suppression_reason"] = "disabled_by_enabled_codes_filter"
            suppressed.append(entry)
            continue
        if code in suppressions:
            entry["suppression_reason"] = str(suppressions[code] or "suppressed_by_config")
            suppressed.append(entry)
            continue
        if code in severity_overrides:
            entry["severity"] = str(severity_overrides[code])
        if code in blocking_overrides:
            entry["blocking"] = bool(blocking_overrides[code])
        visible.append(entry)
    if include_suppressed:
        visible.extend(suppressed)
    config_source = "metadata.quality" if cfg else "defaults"
    return visible, suppressed, {"config_source": config_source}


def analyze_scaffold_quality(*, text: str, metadata: Optional[Mapping[str, Any]] = None, doc_name: Optional[str] = None) -> List[Dict[str, Any]]:
    metadata = dict(metadata or {})
    warnings: List[Dict[str, Any]] = []
    parsed = parse_frontmatter(text)
    body = parsed.body
    frontmatter_status = str(parsed.frontmatter_data.get("status", "")).strip().lower()
    readiness_claim = frontmatter_status in _READINESS_VALUES

    warnings.extend(_placeholder_residue_warnings(body))
    warnings.extend(_lifecycle_status_warnings(body, frontmatter_status=frontmatter_status))
    warnings.extend(
        _conformance_warnings(
            body,
            readiness_claim=readiness_claim,
            doc_name=doc_name,
            existing_warnings=warnings,
        )
    )

    for warning in warnings:
        loc = warning.get("location") if isinstance(warning.get("location"), dict) else {}
        line = max(1, int(loc.get("line", 1)))
        body_lines = body.splitlines()
        excerpt = body_lines[line - 1].strip()[:160] if line <= len(body_lines) else ""
        warning["excerpt"] = excerpt
    configured, _suppressed, _meta = _apply_quality_overrides(warnings, metadata=metadata)
    return configured


def _classify_lifecycle_claim(line: str) -> Optional[str]:
    normalized = _strip_markdown_status_markup(line).lower().replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    status_match = re.match(
        r"^(?:status|handoff|handoff status)\s*:\s*(ready|complete|done|finished|blocked|draft|in progress|in-progress|wip)\b",
        normalized,
    )
    if status_match:
        return status_match.group(1).replace("-", " ")
    if normalized in {"ready", "complete", "done", "finished", "blocked"}:
        return normalized
    return None


def _lifecycle_status_warnings(body: str, *, frontmatter_status: str) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    normalized_frontmatter = frontmatter_status.replace("_", " ").replace("-", " ")
    frontmatter_ready = normalized_frontmatter in _READINESS_VALUES
    frontmatter_blocked = normalized_frontmatter == "blocked"

    offset = 0
    for raw_line in body.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        claim = _classify_lifecycle_claim(line)
        if claim and not _in_code_fence(body, offset) and not _is_quoted_line(body, offset):
            claim_ready = claim in _READINESS_VALUES
            claim_blocked = claim == "blocked"
            claim_draftish = claim in {"draft", "in progress", "wip"}
            mismatch = (
                (claim_ready and not frontmatter_ready)
                or (claim_blocked and not frontmatter_blocked)
                or (claim_draftish and frontmatter_ready)
            )
            if mismatch:
                warnings.append(
                    _warning(
                        "SCF_LIFECYCLE_STATUS_MISMATCH",
                        "Body lifecycle handoff conflicts with frontmatter status.",
                        body or "\n",
                        offset,
                        "Use frontmatter_update to align narrative document status with the body handoff, or revise the body handoff text.",
                    )
                )
                break
        offset += len(raw_line)
    return warnings


def _placeholder_residue_warnings(body: str) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    for m in re.finditer(r"\[[^\]]{4,}\]", body):
        if _in_code_fence(body, m.start()) or _is_quoted_line(body, m.start()):
            continue
        line = _line_text(body, m.start())
        line_idx = m.start() - (body.rfind("\n", 0, m.start()) + 1)
        if _is_checklist_marker(line, line_idx):
            continue
        if _is_progress_prefix_bracket(line, line_idx):
            continue
        if _is_markdown_link_label(line, line_idx, line_idx + (m.end() - m.start())):
            continue
        stripped = line.strip()
        line = stripped
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        if line.startswith("#"):
            continue
        warnings.append(_warning("SCF_PLACEHOLDER_BRACKET", "Bracketed placeholder found in body text.", body, m.start(), "Replace bracketed drafting text with final artifact content."))

    for pat in _TEMPLATE_PROSE_PATTERNS:
        m = re.search(pat, body, re.IGNORECASE)
        if m and not _in_code_fence(body, m.start()) and not _is_quoted_line(body, m.start()):
            warnings.append(_warning("SCF_TEMPLATE_PROSE", "Template prose residue detected.", body, m.start(), "Remove scaffold prose and replace with project-specific evidence."))
            break

    if re.search(r"\|\s*finding\s*\|", body, re.IGNORECASE) and re.search(r"\|\s*\|\s*$", body, re.MULTILINE):
        idx = re.search(r"\|\s*\|\s*$", body, re.MULTILINE).start()
        warnings.append(_warning("SCF_EMPTY_FINDING", "Empty finding/evidence row detected.", body, idx, "Fill the row with concrete finding and evidence."))

    appendix = re.search(r"(^|\n)#+\s+(appendix|references|attachments)\b", body, re.IGNORECASE)
    if appendix and re.search(r"(TBD|TODO|\[fill|placeholder)", body[appendix.start(): appendix.start()+250], re.IGNORECASE):
        warnings.append(_warning("SCF_UNFILLED_APPENDIX", "Appendix/reference section appears unfilled.", body, appendix.start(), "Replace placeholder appendix text with real references or remove section."))
    return warnings


def _conformance_warnings(
    body: str,
    *,
    readiness_claim: bool,
    doc_name: Optional[str],
    existing_warnings: Optional[Sequence[Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    todo_line = re.search(r"^\s*[-*]?\s*(TODO|TBD)\b.*$", body, re.IGNORECASE | re.MULTILINE)
    if todo_line and readiness_claim:
        warnings.append(_warning("SCF_TODO_ONLY_SECTION", "TODO-only section found while document claims readiness.", body, todo_line.start(), "Complete or remove TODO-only section before claiming readiness."))

    if doc_name and "log" in doc_name.lower() and readiness_claim:
        non_header_lines = [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        if len(non_header_lines) <= 2:
            warnings.append(_warning("SCF_LOG_TEMPLATE_ONLY", "Log document appears to contain only template structure.", body or "\n", 0, "Add real dated log entries with substantive content."))

    unresolved_warnings = list(existing_warnings or []) + warnings
    if readiness_claim and unresolved_warnings:
        warnings.append(_warning("SCF_FRONTMATTER_MISMATCH", "Frontmatter readiness claim conflicts with unfinished body state.", body or "\n", 0, "Set status to in_progress or resolve scaffold warnings before marking complete."))
    return warnings


def collect_managed_doc_quality_warnings(
    *,
    text: str,
    doc_name: str,
    path: str | Path | None = None,
    project: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    warnings = analyze_scaffold_quality(text=text, metadata=metadata, doc_name=doc_name)
    if str(doc_name).strip().lower() == "changelog":
        warnings.extend(_research_context_drift_warnings(text=text, project=project))
    if str(doc_name).strip().lower() == "changelog":
        warnings.extend(_changelog_warnings(text=text, doc_name=doc_name))
    if path is None or not is_research_doc_target(doc_name, path):
        return warnings
    warnings.extend(_research_context_drift_warnings(text=text, project=project))

    doc_path = Path(path)
    docs_dir_value = project.get("docs_dir") if isinstance(project, Mapping) else None
    canonical_research_dir = Path(docs_dir_value) / "research" if isinstance(docs_dir_value, str) and docs_dir_value else None
    research_dir = doc_path.parent if doc_path.parent.name == "research" else canonical_research_dir
    if research_dir is None or not research_dir.exists():
        return warnings
    warnings.extend(
        build_research_index_hygiene_warnings(
            research_dir=research_dir,
            changed_path=doc_path,
            canonical_research_dir=canonical_research_dir,
        )
    )
    configured, _suppressed, _meta = _apply_quality_overrides(warnings, metadata=metadata)
    return configured


def _research_context_drift_warnings(*, text: str, project: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    for entry in accepted_entries(parse_changelog_entries(text)):
        observed = entry.observed_context or {}
        source = str(observed.get("source") or "").strip()
        value = str(observed.get("value") or "").strip()
        if not source or not value or source == "unknown":
            continue
        if source not in {"manual", "pyproject", "git_commit", "git_tag"}:
            continue
        repo_root = Path(str((project or {}).get("root") or ".")).resolve()
        pyproject_path = repo_root / "pyproject.toml"
        current = resolve_observed_context(repo_root=repo_root, pyproject_path=pyproject_path)
        if current.source != source:
            continue
        if current.value == value:
            continue
        marker = f"entry_id: {entry.entry_id}" if entry.entry_id else entry.title or "accepted-entry"
        idx = text.find(marker)
        idx = 0 if idx < 0 else idx
        warnings.append(
            _warning(
                "SCF_RESEARCH_CONTEXT_DRIFT",
                f"Historical observed_context changed for source '{source}': stored '{value}', current '{current.value}'.",
                text,
                idx,
                "Review historical context; keep as-is if intentionally historical, or update with explicit evidence when needed.",
            )
        )
    return warnings


def _changelog_warnings(*, text: str, doc_name: str) -> List[Dict[str, Any]]:
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
            _warning(
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
            warnings.append(_warning("SCF_CHANGELOG_ENTRY_ID_MISSING", "Accepted changelog entry is missing entry_id.", text, idx, "Add entry_id in <yyyymmdd>:<slug> format."))
        elif not is_valid_entry_id(entry.entry_id):
            warnings.append(_warning("SCF_CHANGELOG_ENTRY_ID_INVALID", "Accepted changelog entry has invalid entry_id format.", text, idx, "Use entry_id format <yyyymmdd>:<slug>."))
        if not entry.summary:
            warnings.append(_warning("SCF_CHANGELOG_SUMMARY_MISSING", "Accepted changelog entry is missing summary.", text, idx, "Add a concise summary for accepted entry."))
        if not entry.evidence_refs:
            warnings.append(_warning("SCF_CHANGELOG_EVIDENCE_MISSING", "Accepted changelog entry is missing evidence_refs.", text, idx, "Add one or more concrete evidence_refs entries."))
        if entry.entry_id in seen_keys and entry.entry_id:
            warnings.append(_warning("SCF_CHANGELOG_DUPLICATE_SOURCE_KEY", "Duplicate changelog source key detected for accepted entries.", text, idx, "Keep one authoritative entry per (project_slug, entry_id)."))
        seen_keys.add(entry.entry_id)
        if _PROGRESS_PREFIX_PATTERN.search(entry.section_text) or "[agent:" in entry.section_text.lower():
            warnings.append(_warning("SCF_CHANGELOG_RAW_PROGRESS_DUMP", "Accepted changelog entry looks like a raw progress-log dump.", text, idx, "Curate a human-authored changelog summary instead of dumping log lines."))
        if re.search(r"(?im)^\s*status\s*:\s*accepted\s*$", entry.section_text):
            warnings.append(_warning("SCF_CHANGELOG_AMBIGUOUS_BODY_STATUS", "Accepted entry uses ambiguous body lifecycle text ('Status: accepted').", text, idx, "Use entry_status for changelog entry state and keep lifecycle status in frontmatter only."))
    return warnings


def _research_warning(code: str, *, excerpt: str, message: str, repair: str) -> Dict[str, Any]:
    policy = DEFAULT_WARNING_POLICIES[code]
    return {
        "code": code,
        "severity": policy["severity"],
        "blocking": bool(policy["blocking"]),
        "location": {"line": 1, "column": 1},
        "excerpt": excerpt,
        "message": message,
        "suggested_repair": repair,
    }


def build_research_index_hygiene_warnings(
    *,
    research_dir: Path,
    changed_path: Optional[Path] = None,
    canonical_research_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    research_dir = research_dir.resolve()
    canonical_dir = (canonical_research_dir or research_dir).resolve()
    index_path = research_dir / "INDEX.md"
    research_docs = sorted(
        p for p in research_dir.rglob("*.md") if p.name != "INDEX.md" and not p.name.startswith("_")
    )
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

    if changed_path and changed_path.suffix.lower() == ".md" and changed_path.name != "INDEX.md":
        changed_resolved = changed_path.resolve()
        try:
            relative_to_canonical = changed_resolved.relative_to(canonical_dir)
            noncanonical = len(relative_to_canonical.parts) != 1
        except ValueError:
            noncanonical = True
        if noncanonical:
            nested_inside_canonical = False
            try:
                changed_resolved.relative_to(canonical_dir)
                nested_inside_canonical = True
            except ValueError:
                nested_inside_canonical = False
            warnings.append(
                _research_warning(
                    "SCF_NONCANONICAL_LOCATION",
                    excerpt=str(changed_path),
                    message=(
                        "Research artifact is not in canonical flat research placement. "
                        "Files are expected directly under .scribe/docs/dev_plans/<project>/research/."
                        if nested_inside_canonical
                        else "Research artifact is outside canonical research storage and may not be indexed as expected."
                    ),
                    repair=(
                        "Rehome the artifact to the top-level canonical research directory and regenerate research/INDEX.md."
                        if nested_inside_canonical
                        else "Move the artifact into the canonical research directory and regenerate research/INDEX.md."
                    ),
                )
            )

    if not index_path.exists():
        warnings.append(
            _research_warning(
                "SCF_INDEX_MISSING",
                excerpt=str(index_path),
                message="Research index is missing.",
                repair="Run a research-doc create/edit flow to regenerate research/INDEX.md.",
            )
        )
        return warnings

    if changed_path and changed_path.suffix.lower() == ".md":
        try:
            rel_name = changed_path.name
            if rel_name != "INDEX.md" and rel_name not in index_text:
                warnings.append(
                    _research_warning(
                        "SCF_DOC_UNINDEXED",
                        excerpt=rel_name,
                        message="Research document is unindexed: it is not listed in research/INDEX.md.",
                        repair="Regenerate the research index by editing or creating a research document.",
                    )
                )
        except Exception:
            pass

    for match in re.finditer(r"\]\(([^)]+\.md)\)", index_text):
        linked = match.group(1).strip()
        if "://" in linked or linked.startswith("#"):
            continue
        linked_path = (research_dir / linked).resolve()
        try:
            linked_path.relative_to(research_dir)
        except ValueError:
            continue
        if not linked_path.exists():
            warnings.append(
                _research_warning(
                    "SCF_DOC_UNINDEXED",
                    excerpt=linked,
                    message="Research index references an orphaned artifact that no longer exists.",
                    repair="Regenerate research/INDEX.md so removed or rehomed artifacts are dropped from the index.",
                )
            )
            break

    for doc in research_docs:
        try:
            display_name = str(doc.relative_to(research_dir))
        except ValueError:
            display_name = doc.name
        if doc.name not in index_text and display_name not in index_text:
            warnings.append(
                _research_warning(
                    "SCF_INDEX_STALE",
                    excerpt=display_name,
                    message="Research index appears stale relative to research artifacts.",
                    repair="Trigger research index refresh through managed-doc mutation flow.",
                )
            )
            break
    return warnings
