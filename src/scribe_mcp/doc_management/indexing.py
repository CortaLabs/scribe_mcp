"""Shared vector/text indexing helpers for doc management."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from scribe_mcp.config.repo_config import RepoDiscovery
from scribe_mcp.config.vector_config import load_vector_config
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.utils.time import format_utc

from .utils import (
    chunk_text_for_vector,
    classify_scribe_source_document,
    generate_doc_entry_id,
    hash_text,
    parse_int,
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

def get_vector_search_defaults(repo_root: Optional[Path]) -> Tuple[int, int]:
    default_doc_k = 5
    default_log_k = 3
    if not repo_root:
        return default_doc_k, default_log_k
    try:
        config = RepoDiscovery.load_config(repo_root)
    except Exception:
        return default_doc_k, default_log_k

    try:
        default_doc_k = max(0, int(config.vector_search_doc_k))
    except (TypeError, ValueError):
        default_doc_k = 5
    try:
        default_log_k = max(0, int(config.vector_search_log_k))
    except (TypeError, ValueError):
        default_log_k = 3
    return default_doc_k, default_log_k

def resolve_semantic_limits(
    *,
    search_meta: Dict[str, Any],
    repo_root: Optional[Path],
) -> Dict[str, Any]:
    default_doc_k, default_log_k = get_vector_search_defaults(repo_root)
    k_override = parse_int(search_meta.get("k"))
    doc_k_override = parse_int(search_meta.get("doc_k"))
    log_k_override = parse_int(search_meta.get("log_k"))

    total_k = max(0, k_override) if k_override is not None else max(0, default_doc_k + default_log_k)
    doc_k = max(0, doc_k_override) if doc_k_override is not None else default_doc_k
    log_k = max(0, log_k_override) if log_k_override is not None else default_log_k

    if doc_k > total_k:
        doc_k = total_k
    remaining = max(0, total_k - doc_k)
    if log_k > remaining:
        log_k = remaining

    return {
        "total_k": total_k,
        "doc_k": doc_k,
        "log_k": log_k,
        "default_doc_k": default_doc_k,
        "default_log_k": default_log_k,
        "k_override": k_override,
        "doc_k_override": doc_k_override,
        "log_k_override": log_k_override,
    }

def get_vector_indexer():
    try:
        from scribe_mcp.plugins.registry import get_plugin_registry

        registry = get_plugin_registry()
        for plugin in registry.plugins.values():
            if getattr(plugin, "name", None) == "vector_indexer" and getattr(plugin, "initialized", False):
                return plugin
    except Exception:
        return None
    return None

def vector_indexing_enabled(repo_root: Optional[Path]) -> bool:
    if not repo_root:
        return False
    try:
        config = RepoDiscovery.load_config(repo_root)
    except Exception:
        return False
    return bool(config.vector_index_docs)

def vector_search_enabled(repo_root: Optional[Path], content_type: str) -> bool:
    if not repo_root:
        return False
    try:
        config = RepoDiscovery.load_config(repo_root)
    except Exception:
        return False
    if not (config.plugin_config or {}).get("enabled", False):
        return False
    vector_config = load_vector_config(repo_root)
    if not vector_config.enabled:
        return False
    if content_type == "log":
        return bool(config.vector_index_logs)
    return bool(config.vector_index_docs)

def normalize_doc_search_mode(value: Optional[str]) -> str:
    if not value:
        return "exact"
    normalized = value.strip().lower()
    if normalized in {"exact", "literal"}:
        return "exact"
    if normalized in {"fuzzy", "approx"}:
        return "fuzzy"
    if normalized in {"semantic", "vector"}:
        return "semantic"
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
                return lambda: update_bug_index(case_root, agent_id)

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
    repo_root = project.get("root")
    if isinstance(repo_root, str):
        repo_root = Path(repo_root)
    if not vector_indexing_enabled(repo_root):
        return

    vector_indexer = get_vector_indexer()
    if not vector_indexer:
        return

    if should_skip_doc_index(doc_name, change_path):
        return

    try:
        raw_text = await asyncio.to_thread(change_path.read_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    frontmatter: Dict[str, Any] = {}
    body = raw_text
    try:
        parsed = parse_frontmatter(raw_text)
        if parsed.has_frontmatter:
            frontmatter = parsed.frontmatter_data
            body = parsed.body
    except ValueError:
        body = raw_text

    content = body.strip()
    if not content:
        return

    title = frontmatter.get("title")
    doc_type = frontmatter.get("doc_type")
    chunks = chunk_text_for_vector(content)
    if not chunks:
        return

    timestamp = format_utc()
    project_name = project.get("name", "")
    chunk_total = len(chunks)

    for idx, chunk in enumerate(chunks):
        content_hash = hash_text(chunk)
        entry_id = generate_doc_entry_id(change_path, idx, content_hash)
        message = f"{title}\n\n{chunk}" if title else chunk
        doc_meta: Dict[str, Any] = {
            "content_type": "doc",
            "doc_name": doc_name,
            "doc_title": title,
            "doc_type": doc_type,
            "file_path": str(change_path),
            "chunk_index": idx,
            "chunk_total": chunk_total,
            "sha_after": after_hash,
        }
        if metadata:
            doc_meta["doc_metadata"] = metadata

        entry_data = {
            "entry_id": entry_id,
            "project_name": project_name,
            "message": message,
            "agent": agent_id,
            "timestamp": timestamp,
            "meta": doc_meta,
        }
        if wait_for_queue and hasattr(vector_indexer, "enqueue_entry"):
            vector_indexer.enqueue_entry(entry_data, wait=True, timeout=queue_timeout)
        else:
            vector_indexer.post_append(entry_data)
