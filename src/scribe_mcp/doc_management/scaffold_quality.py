from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence

from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.doc_management.quality.results import summarize_quality_warnings
from scribe_mcp.doc_management.quality.context import DocumentContextBuilder
from scribe_mcp.doc_management.quality.rules.research import build_research_index_hygiene_warnings
from scribe_mcp.doc_management.quality.rules.scaffold import evaluate_scaffold_rules
from scribe_mcp.doc_management.quality.rules.changelog import build_changelog_structure_warnings
from scribe_mcp.doc_management.changelog import (
    accepted_entries,
    preview_current_release_coverage,
    parse_changelog_entries,
)
from scribe_mcp.doc_management.version_context import resolve_observed_context
from scribe_mcp.doc_management.quality.rules.release_gate import UNSUPPRESSIBLE_BLOCKER_CODES

if TYPE_CHECKING:
    from scribe_mcp.doc_management.quality.context import DocumentContext

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
    "SCF_CHANGELOG_CURRENT_VERSION_MISSING": {"severity": "critical", "blocking": True},
    "SCF_RESEARCH_CONTEXT_DRIFT": {"severity": "medium", "blocking": False},
    "SCF_TRAILING_WHITESPACE": {"severity": "medium", "blocking": False},
    "SCF_FAILED_WRITE_RESIDUE": {"severity": "critical", "blocking": True},
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


def _in_code_fence(body: str, idx: int, context: Optional["DocumentContext"] = None) -> bool:
    if context is not None:
        return (
            context.offset_in_scope(idx, kind="fenced_code")
            or context.offset_in_scope(idx, kind="inline_code")
            or context.offset_in_scope(idx, kind="indented_code")
        )
    return body[:idx].count("```") % 2 == 1


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


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _looks_like_placeholder_bracket(content: str) -> bool:
    normalized = re.sub(r"\s+", " ", content.strip().lower())
    if not normalized:
        return False

    explicit_tokens = {
        "todo",
        "tbd",
        "placeholder",
        "fill",
        "fill in",
        "insert",
        "replace me",
        "your text",
    }
    if normalized in explicit_tokens:
        return True

    return bool(re.search(r"\b(todo|tbd|placeholder|fill|insert|replace\s+me)\b", normalized))


# Compatibility export; canonical implementation lives in quality.results.


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
            if code in UNSUPPRESSIBLE_BLOCKER_CODES or bool(entry.get("blocking")) and str(entry.get("severity") or "").lower() == "critical":
                entry["suppression_reason"] = "suppression_ignored_for_integrity_blocker"
                visible.append(entry)
                continue
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
    context = DocumentContextBuilder().build(text=text, doc_name=doc_name, metadata=metadata)
    frontmatter_status = str(parsed.frontmatter_data.get("status", "")).strip().lower()
    readiness_claim = frontmatter_status in _READINESS_VALUES

    warnings.extend(
        evaluate_scaffold_rules(
            body=body,
            doc_name=doc_name,
            frontmatter_status=frontmatter_status,
            readiness_claim=readiness_claim,
            document_context=context,
        )
    )
    failed_write_residue = re.search(r"failed\s+write|write\s+failed|partial\s+write\s+residue", body, flags=re.IGNORECASE)
    if failed_write_residue and not _in_code_fence(body, failed_write_residue.start(), context=context):
        warnings.append(
            _warning(
                "SCF_FAILED_WRITE_RESIDUE",
                "Detected failed-write residue marker text in managed document body.",
                body or "\n",
                failed_write_residue.start(),
                "Remove failed-write residue text and re-run quality_check before ready/complete handoff.",
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


def _trailing_whitespace_warnings(body: str) -> List[Dict[str, Any]]:
    for idx, line in enumerate(body.splitlines(), start=1):
        if line.endswith((" ", "\t")):
            offset = 0
            if idx > 1:
                prior = body.splitlines(keepends=True)[: idx - 1]
                offset = sum(len(item) for item in prior)
            return [
                _warning(
                    "SCF_TRAILING_WHITESPACE",
                    "Trailing whitespace found in document body.",
                    body or "\n",
                    offset,
                    "Remove trailing spaces/tabs from edited lines (manage_docs writes should normalize this automatically).",
                )
            ]
    return []


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


def _lifecycle_status_warnings(body: str, *, frontmatter_status: str, context: Optional["DocumentContext"] = None) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    normalized_frontmatter = frontmatter_status.replace("_", " ").replace("-", " ")
    frontmatter_ready = normalized_frontmatter in _READINESS_VALUES
    frontmatter_blocked = normalized_frontmatter == "blocked"

    offset = 0
    for raw_line in body.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        claim = _classify_lifecycle_claim(line)
        if claim and not _in_code_fence(body, offset, context=context) and not _is_quoted_line(body, offset):
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


def _placeholder_residue_warnings(body: str, *, context: Optional["DocumentContext"] = None) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    for m in re.finditer(r"\[[^\]]{4,}\]", body):
        if _in_code_fence(body, m.start(), context=context) or _is_quoted_line(body, m.start()):
            continue
        line = _line_text(body, m.start())
        line_idx = m.start() - (body.rfind("\n", 0, m.start()) + 1)
        if _is_checklist_marker(line, line_idx):
            continue
        if _is_progress_prefix_bracket(line, line_idx):
            continue
        if _is_markdown_link_label(line, line_idx, line_idx + (m.end() - m.start())):
            continue
        if _is_table_row(line):
            continue
        stripped = line.strip()
        line = stripped
        if line.startswith("<!--") and line.endswith("-->"):
            continue
        if line.startswith("#"):
            continue
        bracket_content = m.group(0)[1:-1]
        if not _looks_like_placeholder_bracket(bracket_content):
            continue
        warnings.append(_warning("SCF_PLACEHOLDER_BRACKET", "Bracketed placeholder found in body text.", body, m.start(), "Replace bracketed drafting text with final artifact content."))

    for pat in _TEMPLATE_PROSE_PATTERNS:
        m = re.search(pat, body, re.IGNORECASE)
        if m and not _in_code_fence(body, m.start(), context=context) and not _is_quoted_line(body, m.start()):
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
    research_docs: Optional[Sequence[Path]] = None,
) -> List[Dict[str, Any]]:
    """Collect quality warnings for a single managed document.

    Parameters
    ----------
    research_docs:
        Optional pre-computed list of ``*.md`` files in the research directory
        (same semantics as ``build_research_index_hygiene_warnings``).  Pass
        this when the caller has already done the ``rglob`` once so this
        function can avoid repeating it.  ``None`` (the default) preserves the
        original behavior and maintains full backward compatibility.
    """
    warnings = analyze_scaffold_quality(text=text, metadata=metadata, doc_name=doc_name)
    is_research_target = path is not None and is_research_doc_target(doc_name, path)

    quality_runtime = ((metadata or {}).get("_quality_runtime") or {}) if isinstance((metadata or {}).get("_quality_runtime"), dict) else {}
    quality_mode = str(quality_runtime.get("mode") or ((metadata or {}).get("quality") or {}).get("mode") or "local_default")
    if doc_name.lower() == "changelog":
        warnings.extend(_changelog_warnings(text=text))
        if quality_mode == "release_gate":
            warnings.extend(_changelog_current_version_coverage_warnings(text=text, project=project))
            warnings.extend(_research_context_drift_warnings(text=text, project=project))
    elif is_research_target and quality_mode == "release_gate":
        warnings.extend(_research_context_drift_warnings(text=text, project=project))
    if not is_research_target:
        return warnings

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
            warning_policies=DEFAULT_WARNING_POLICIES,
            research_docs=research_docs,
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


def _changelog_warnings(*, text: str) -> List[Dict[str, Any]]:
    return build_changelog_structure_warnings(text=text, warning_builder=_warning)


def _changelog_current_version_coverage_warnings(*, text: str, project: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    repo_root = Path(str((project or {}).get("root") or ".")).resolve()
    coverage = preview_current_release_coverage(
        project_changelog_text=text,
        repo_root=repo_root,
        pyproject_path=repo_root / "pyproject.toml",
    )
    if coverage.get("status") != "missing":
        return []
    context = coverage.get("current_context") if isinstance(coverage.get("current_context"), dict) else {}
    expected = str(context.get("value") or "unknown")
    idx = 0
    return [
        _warning(
            "SCF_CHANGELOG_CURRENT_VERSION_MISSING",
            f"Accepted CHANGELOG coverage is missing for current project version '{expected}'.",
            text or "\n",
            idx,
            str(coverage.get("suggested_repair") or "Add an accepted changelog entry covering the current project version."),
        )
    ]
