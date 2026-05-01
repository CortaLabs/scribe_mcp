from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from scribe_mcp.utils.frontmatter import parse_frontmatter

_READINESS_VALUES = {"ready", "done", "complete", "finished"}

DEFAULT_WARNING_POLICIES: Dict[str, Dict[str, Any]] = {
    "SCF_PLACEHOLDER_BRACKET": {"severity": "critical", "blocking": True},
    "SCF_TEMPLATE_PROSE": {"severity": "high", "blocking": True},
    "SCF_EMPTY_FINDING": {"severity": "high", "blocking": True},
    "SCF_UNFILLED_APPENDIX": {"severity": "high", "blocking": True},
    "SCF_TODO_ONLY_SECTION": {"severity": "high", "blocking": True},
    "SCF_LOG_TEMPLATE_ONLY": {"severity": "high", "blocking": True},
    "SCF_FRONTMATTER_MISMATCH": {"severity": "critical", "blocking": True},
    "SCF_INDEX_STALE": {"severity": "medium", "blocking": False},
    "SCF_INDEX_MISSING": {"severity": "medium", "blocking": False},
    "SCF_DOC_UNINDEXED": {"severity": "medium", "blocking": False},
    "SCF_NONCANONICAL_LOCATION": {"severity": "medium", "blocking": False},
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
    readiness_claim = str(parsed.frontmatter_data.get("status", "")).strip().lower() in _READINESS_VALUES

    for m in re.finditer(r"\[[^\]]{4,}\]", body):
        if _in_code_fence(body, m.start()) or _is_quoted_line(body, m.start()):
            continue
        line = _line_text(body, m.start()).strip()
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

    todo_line = re.search(r"^\s*[-*]?\s*(TODO|TBD)\b.*$", body, re.IGNORECASE | re.MULTILINE)
    if todo_line and readiness_claim:
        warnings.append(_warning("SCF_TODO_ONLY_SECTION", "TODO-only section found while document claims readiness.", body, todo_line.start(), "Complete or remove TODO-only section before claiming readiness."))

    if doc_name and "log" in doc_name.lower() and readiness_claim:
        non_header_lines = [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        if len(non_header_lines) <= 2:
            warnings.append(_warning("SCF_LOG_TEMPLATE_ONLY", "Log document appears to contain only template structure.", body or "\n", 0, "Add real dated log entries with substantive content."))

    if readiness_claim and warnings:
        warnings.append(_warning("SCF_FRONTMATTER_MISMATCH", "Frontmatter readiness claim conflicts with unfinished body state.", body or "\n", 0, "Set status to in_progress or resolve scaffold warnings before marking complete."))

    for warning in warnings:
        loc = warning.get("location") if isinstance(warning.get("location"), dict) else {}
        line = max(1, int(loc.get("line", 1)))
        body_lines = body.splitlines()
        excerpt = body_lines[line - 1].strip()[:160] if line <= len(body_lines) else ""
        warning["excerpt"] = excerpt
    configured, _suppressed, _meta = _apply_quality_overrides(warnings, metadata=metadata)
    return configured


def collect_managed_doc_quality_warnings(
    *,
    text: str,
    doc_name: str,
    path: str | Path | None = None,
    project: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    warnings = analyze_scaffold_quality(text=text, metadata=metadata, doc_name=doc_name)
    if path is None or not is_research_doc_target(doc_name, path):
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
        )
    )
    configured, _suppressed, _meta = _apply_quality_overrides(warnings, metadata=metadata)
    return configured


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
            warnings.append(
                _research_warning(
                    "SCF_NONCANONICAL_LOCATION",
                    excerpt=str(changed_path),
                    message=(
                        "Research artifact is outside canonical flat research storage. "
                        "Package 3.1 expects files directly under .scribe/docs/dev_plans/<project>/research/."
                    ),
                    repair=(
                        "Move or rehome the artifact into the canonical flat research directory and regenerate research/INDEX.md; "
                        "use index display grouping instead of physical wave/subdirectory placement."
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
