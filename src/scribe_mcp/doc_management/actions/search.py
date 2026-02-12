"""Search action helper for manage_docs decomposition."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.doc_management import indexing as indexing_shared
from scribe_mcp.utils.frontmatter import parse_frontmatter


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

    search_mode = indexing_shared.normalize_doc_search_mode(search_meta.get("search_mode"))
    if search_mode == "semantic":
        content_type_raw = search_meta.get("content_type")
        content_type = str(content_type_raw).strip().lower() if content_type_raw is not None else "all"
        repo_root = project.get("root")
        if isinstance(repo_root, str):
            repo_root = Path(repo_root)

        if content_type not in {"doc", "log"}:
            enabled_for_doc = indexing_shared.vector_search_enabled(repo_root, "doc")
            enabled_for_log = indexing_shared.vector_search_enabled(repo_root, "log")
            if not (enabled_for_doc or enabled_for_log):
                response = {
                    "ok": False,
                    "error": "Semantic search disabled or unavailable",
                    "suggestion": "Enable plugin_config.enabled and vector_index_docs/logs, and ensure vector.json enabled",
                }
                return helper.apply_context_payload(response, context)
        elif not indexing_shared.vector_search_enabled(repo_root, content_type):
            response = {
                "ok": False,
                "error": "Semantic search disabled or unavailable",
                "suggestion": "Enable plugin_config.enabled and vector_index_docs/logs, and ensure vector.json enabled",
            }
            return helper.apply_context_payload(response, context)

        vector_indexer = indexing_shared.get_vector_indexer()
        if not vector_indexer:
            response = {"ok": False, "error": "Vector indexer plugin not available"}
            return helper.apply_context_payload(response, context)

        filters: Dict[str, Any] = {}
        project_slugs = search_meta.get("project_slugs")
        if isinstance(project_slugs, list):
            filters["project_slugs"] = [str(slug).lower().replace(" ", "-") for slug in project_slugs if slug]
        project_slug_prefix = search_meta.get("project_slug_prefix")
        if project_slug_prefix:
            filters["project_slug_prefix"] = str(project_slug_prefix).lower().replace(" ", "-")
        project_slug = search_meta.get("project_slug")
        if project_slug and "project_slugs" not in filters and "project_slug_prefix" not in filters:
            filters["project_slug"] = str(project_slug).lower().replace(" ", "-")

        if search_meta.get("doc_type"):
            filters["doc_type"] = str(search_meta.get("doc_type"))
        if search_meta.get("file_path"):
            filters["file_path"] = str(search_meta.get("file_path"))
        if search_meta.get("time_start") or search_meta.get("time_end"):
            filters["time_range"] = {
                "start": search_meta.get("time_start"),
                "end": search_meta.get("time_end"),
            }

        min_similarity = search_meta.get("min_similarity")

        def _apply_similarity_threshold(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            if min_similarity is None:
                return items
            try:
                min_val = float(min_similarity)
            except (TypeError, ValueError):
                return items
            return [r for r in items if r.get("similarity_score", 0) >= min_val]

        limits = indexing_shared.resolve_semantic_limits(search_meta=search_meta, repo_root=repo_root)
        if content_type in {"doc", "log"}:
            if limits["k_override"] is not None:
                single_k = limits["total_k"]
            elif content_type == "doc":
                single_k = limits["doc_k_override"] if limits["doc_k_override"] is not None else limits["default_doc_k"]
            else:
                single_k = limits["log_k_override"] if limits["log_k_override"] is not None else limits["default_log_k"]

            filters["content_type"] = content_type
            results = vector_indexer.search_similar(query, single_k, filters)
            results = _apply_similarity_threshold(results)
            results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            for item in results:
                item["content_type"] = content_type
            limits_payload = {
                "total_k": single_k,
                "doc_k": single_k if content_type == "doc" else 0,
                "log_k": single_k if content_type == "log" else 0,
                "default_doc_k": limits["default_doc_k"],
                "default_log_k": limits["default_log_k"],
            }
            response = {
                "ok": True,
                "action": "search",
                "search_mode": "semantic",
                "query": query,
                "results_count": len(results),
                "results": results,
                "filters_applied": filters,
                "limits": limits_payload,
            }
            return helper.apply_context_payload(response, context)

        base_filters = filters.copy()
        doc_filters = {**base_filters, "content_type": "doc"}
        log_filters = {**base_filters, "content_type": "log"}
        doc_results = _apply_similarity_threshold(vector_indexer.search_similar(query, limits["doc_k"], doc_filters))
        log_results = _apply_similarity_threshold(vector_indexer.search_similar(query, limits["log_k"], log_filters))
        doc_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        log_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        for item in doc_results:
            item["content_type"] = "doc"
        for item in log_results:
            item["content_type"] = "log"
        combined = (doc_results + log_results)[: limits["total_k"]]
        response = {
            "ok": True,
            "action": "search",
            "search_mode": "semantic",
            "query": query,
            "results_count": len(combined),
            "results": combined,
            "results_by_type": {
                "doc": doc_results,
                "log": log_results,
            },
            "results_count_by_type": {
                "doc": len(doc_results),
                "log": len(log_results),
            },
            "filters_applied": {**base_filters, "content_type": "all"},
            "limits": {
                "total_k": limits["total_k"],
                "doc_k": limits["doc_k"],
                "log_k": limits["log_k"],
                "default_doc_k": limits["default_doc_k"],
                "default_log_k": limits["default_log_k"],
            },
        }
        return helper.apply_context_payload(response, context)

    if not doc_name:
        response = {"ok": False, "error": "search requires doc_name parameter (use '*' or 'all' to search all docs)"}
        return helper.apply_context_payload(response, context)
    targets = indexing_shared.iter_doc_search_targets(project, doc_name)
    if not targets:
        response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
        return helper.apply_context_payload(response, context)

    fuzzy_threshold = float(search_meta.get("fuzzy_threshold", 0.8))
    results: List[Dict[str, Any]] = []
    for doc_key, path in targets:
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
            mode=search_mode,
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
        "search_mode": search_mode,
        "query": query,
        "results_count": len(results),
        "results": results,
    }
    return helper.apply_context_payload(response, context)
