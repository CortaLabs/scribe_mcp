"""Search action helper for manage_docs decomposition."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.doc_management import indexing as indexing_shared
from scribe_mcp.utils.frontmatter import parse_frontmatter


def _matches_content_type(doc_key: str, content_type: str) -> bool:
    if content_type == "all":
        return True
    is_log_doc = indexing_shared.is_log_doc_key(doc_key)
    if content_type == "log":
        return is_log_doc
    if content_type == "doc":
        return not is_log_doc
    return True


async def handle_search_action(
    *,
    action: str,
    project: Dict[str, Any],
    doc_name: Optional[str],
    metadata: Optional[Dict[str, Any]],
    helper: Any,
    context: Any,
) -> Optional[Dict[str, Any]]:
    """Handle semantic/text search action and return response when consumed."""
    if action != "search":
        return None

    search_meta = metadata if isinstance(metadata, dict) else {}
    query = (search_meta.get("query") or search_meta.get("search") or "").strip()
    if not query:
        response = {"ok": False, "error": "search requires metadata.query"}
        return helper.apply_context_payload(response, context)

    raw_search_mode = str(search_meta.get("search_mode") or "exact").strip().lower() or "exact"
    search_mode = indexing_shared.normalize_doc_search_mode(raw_search_mode)
    fallback_requested = search_mode in {"semantic", "vector"}
    effective_mode = "exact" if fallback_requested else search_mode
    target_doc_name = doc_name if doc_name else ("*" if fallback_requested else None)

    if not target_doc_name:
        response = {"ok": False, "error": "search requires doc_name parameter (use '*' or 'all' to search all docs)"}
        return helper.apply_context_payload(response, context)
    targets = indexing_shared.iter_doc_search_targets(project, target_doc_name)
    if not targets:
        response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{target_doc_name}' is not registered"}
        return helper.apply_context_payload(response, context)

    content_type_raw = search_meta.get("content_type")
    content_type = str(content_type_raw).strip().lower() if content_type_raw is not None else "all"
    fuzzy_threshold = float(search_meta.get("fuzzy_threshold", 0.8))
    results: List[Dict[str, Any]] = []
    for doc_key, path in targets:
        if not _matches_content_type(doc_key, content_type):
            continue
        try:
            raw_text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            parsed = parse_frontmatter(raw_text)
            text = parsed.body
        except ValueError:
            text = raw_text
        matches = indexing_shared.search_doc_lines(
            text=text,
            query=query,
            mode=effective_mode,
            fuzzy_threshold=fuzzy_threshold,
        )
        if matches:
            results.append({
                "doc": doc_key,
                "path": str(path),
                "matches": matches,
            })

    response = {
        "ok": True,
        "action": "search",
        "search_mode": "text" if fallback_requested else effective_mode,
        "query": query,
        "results_count": len(results),
        "results": results,
    }
    if fallback_requested:
        response.update(
            {
                "fallback_applied": True,
                "requested_search_mode": raw_search_mode,
                "effective_search_mode": "text",
                "warning": (
                    "Core semantic/vector search is no longer shipped; "
                    "returning literal text search results instead."
                ),
                "reason": "core_text_only_search",
            }
        )
    return helper.apply_context_payload(response, context)
