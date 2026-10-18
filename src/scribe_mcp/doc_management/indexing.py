"""Shared text-only indexing helpers for doc management."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from scribe_mcp.config.repo_config import RepoDiscovery

from .utils import (
    classify_scribe_source_document,
)

_LOG_DOC_KEYS = {"progress_log", "doc_log", "security_log", "bug_log"}
_LOG_DOC_FILENAMES = {
    "PROGRESS_LOG.md",
    "DOC_LOG.md",
    "SECURITY_LOG.md",
    "BUG_LOG.md",
    "GLOBAL_PROGRESS_LOG.md",
}

def _is_rotated_log_filename(name: str) -> bool:
    upper = name.upper()
    for base in _LOG_DOC_FILENAMES:
        if upper.startswith(f"{base.upper()}."):
            return True
    return False

def should_skip_doc_index(doc_key: Optional[str], path: Path) -> bool:
    name = path.name
    upper = name.upper()
    if doc_key and doc_key.lower() in _LOG_DOC_KEYS:
        return True
    if name in _LOG_DOC_FILENAMES:
        return True
    if upper.endswith("_LOG.MD"):
        return True
    if _is_rotated_log_filename(name):
        return True
    return False

def is_log_doc_key(doc_key: Optional[str]) -> bool:
    return bool(doc_key and doc_key.lower() in _LOG_DOC_KEYS)


def vector_indexing_enabled(repo_root: Optional[Path]) -> bool:
    _ = repo_root
    return False

def normalize_doc_search_mode(value: Optional[str]) -> str:
    if not value:
        return "exact"
    normalized = value.strip().lower()
    if normalized in {"exact", "literal"}:
        return "exact"
    if normalized in {"fuzzy", "approx"}:
        return "fuzzy"
    if normalized in {"semantic", "vector"}:
        return normalized
    return normalized

def iter_doc_search_targets(project: Dict[str, Any], doc_name: str) -> List[tuple[str, Path]]:
    docs_mapping = project.get("docs") or {}
    if doc_name in {"*", "all"}:
        return [(key, Path(path)) for key, path in docs_mapping.items()]
    if doc_name not in docs_mapping:
        return []
    return [(doc_name, Path(docs_mapping[doc_name]))]

def get_index_updater_for_path(
    *,
    file_path: Path,
    project_root: Path,
    docs_dir: Path,
    agent_id: str,
    update_research_index: Callable[[Path, str], Awaitable[None]],
    update_bug_index: Callable[[Path, str], Awaitable[None]],
    update_security_index: Callable[[Path, str], Awaitable[None]],
    update_review_index: Callable[[Path, str], Awaitable[None]],
    update_agent_card_index: Callable[[Path, str], Awaitable[None]],
) -> Optional[Callable[[], Awaitable[None]]]:
    """Return an index updater callback for special managed document locations."""
    try:
        file_path = file_path.resolve()
        project_root = project_root.resolve()
        docs_dir = docs_dir.resolve()

        research_dir = docs_dir / "research"
        if research_dir.exists() and file_path.is_relative_to(research_dir):
            return lambda: update_research_index(research_dir, agent_id)

        classification = classify_scribe_source_document(
            file_path,
            project_root=project_root,
            docs_dir=docs_dir,
        )
        if classification and classification.source_family == "case_report":
            case_root = project_root / "docs" / (
                "security" if classification.doc_type == "security_report" else "bugs"
            )
            if case_root.exists():
                updater = update_security_index if classification.doc_type == "security_report" else update_bug_index
                return lambda: updater(case_root, agent_id)

        if file_path.parent == docs_dir and file_path.name.startswith("REVIEW_REPORT_"):
            return lambda: update_review_index(docs_dir, agent_id)

        if file_path.parent == docs_dir and file_path.name.startswith("AGENT_REPORT_CARD_"):
            return lambda: update_agent_card_index(docs_dir, agent_id)

        return None
    except (ValueError, OSError):
        return None

def search_doc_lines(
    *,
    text: str,
    query: str,
    mode: str,
    fuzzy_threshold: float,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    lines = text.splitlines()
    if mode == "exact":
        for idx, line in enumerate(lines, start=1):
            if query in line:
                results.append({"line": idx, "snippet": line})
        return results

    if mode == "fuzzy":
        import difflib

        for idx, line in enumerate(lines, start=1):
            score = difflib.SequenceMatcher(None, query, line).ratio()
            if score >= fuzzy_threshold:
                results.append({"line": idx, "snippet": line, "score": round(score, 4)})
        return results

    return results

async def index_doc_for_vector(
    *,
    project: Dict[str, Any],
    doc_name: str,
    change_path: Path,
    after_hash: str,
    agent_id: str,
    metadata: Optional[Dict[str, Any]],
    wait_for_queue: bool = False,
    queue_timeout: Optional[float] = None,
) -> None:
    _ = (
        project,
        doc_name,
        change_path,
        after_hash,
        agent_id,
        metadata,
        wait_for_queue,
        queue_timeout,
    )
    return None
