"""Query/list action helpers for manage_docs."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.utils.estimator import PaginationCalculator
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.utils.slug import slugify_project_name


_QUERY_TRANSFORM_ACTIONS = {"normalize_headers", "generate_toc", "validate_crosslinks"}
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+\S.*)$")


def _normalize_heading_text(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"\s+#+$", "", cleaned).strip()
    return cleaned


def _heading_to_section_id(heading_text: str, fallback_index: int) -> str:
    candidate = slugify_project_name(_normalize_heading_text(heading_text))
    return candidate or f"section_{fallback_index}"


async def handle_query_actions(
    *,
    action: str,
    project: Dict[str, Any],
    doc_name: Optional[str],
    metadata: Optional[Dict[str, Any]],
    helper: Any,
    context: Any,
) -> Optional[Dict[str, Any]]:
    """Handle list/query actions and return a response when consumed."""
    if action == "list_sections":
        if not doc_name:
            response = {"ok": False, "error": "list_sections requires doc_name parameter"}
            return helper.apply_context_payload(response, context)
        allowed_docs = set((project.get("docs") or {}).keys())
        if doc_name not in allowed_docs:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return helper.apply_context_payload(response, context)
        return await _handle_list_sections(
            project,
            doc_name=doc_name,
            metadata=metadata,
            helper=helper,
            context=context,
        )

    if action == "list_checklist_items":
        if not doc_name:
            response = {"ok": False, "error": "list_checklist_items requires doc_name parameter"}
            return helper.apply_context_payload(response, context)
        allowed_docs = set((project.get("docs") or {}).keys())
        if doc_name not in allowed_docs:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return helper.apply_context_payload(response, context)
        return await _handle_list_checklist_items(
            project,
            doc_name=doc_name,
            metadata=metadata if isinstance(metadata, dict) else {},
            helper=helper,
            context=context,
        )

    return None


async def handle_query_transform_actions(
    *,
    action: str,
    action_kwargs: Dict[str, Any],
    handle_edit_action: Any,
) -> Optional[Dict[str, Any]]:
    """Route query-transform actions through the shared edit pipeline."""
    if action not in _QUERY_TRANSFORM_ACTIONS:
        return None
    return await handle_edit_action(**action_kwargs)


async def _handle_list_sections(
    project: Dict[str, Any],
    doc_name: str,
    metadata: Optional[Dict[str, Any]],
    helper: Any,
    context: Any,
) -> Dict[str, Any]:
    """Return the list of section anchors for a document."""
    docs_mapping = project.get("docs") or {}
    path_str = docs_mapping.get(doc_name)
    if not path_str:
        return helper.apply_context_payload(
            helper.error_response(f"Document '{doc_name}' is not registered for project '{project.get('name')}'."),
            context,
        )

    path = Path(path_str)
    if not path.exists():
        return helper.apply_context_payload(
            helper.error_response(f"Document path '{path}' does not exist."),
            context,
        )

    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    parsed = parse_frontmatter(text)
    body_lines = parsed.body.splitlines()
    body_line_offset = len(parsed.frontmatter_raw.splitlines()) if parsed.has_frontmatter else 0
    sections: List[Dict[str, Any]] = []
    anchor_duplicates: Dict[str, List[int]] = {}
    heading_sections: List[Dict[str, Any]] = []
    heading_duplicates: Dict[str, List[int]] = {}
    in_code_fence = False

    for line_no, line in enumerate(body_lines, start=1):
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_fence = not in_code_fence
            continue

        if stripped.startswith("<!-- ID:") and stripped.endswith("-->"):
            section_id = stripped[len("<!-- ID:"): -len("-->")].strip()
            anchor_duplicates.setdefault(section_id, []).append(line_no)
            sections.append(
                {
                    "id": section_id,
                    "line": line_no,
                    "file_line": line_no + body_line_offset,
                    "source": "anchor",
                }
            )
            continue

        if in_code_fence:
            continue

        heading_match = _HEADING_PATTERN.match(stripped)
        if not heading_match:
            continue

        heading_text = _normalize_heading_text(heading_match.group(2))
        if not heading_text:
            continue

        heading_level = len(heading_match.group(1))
        section_id = _heading_to_section_id(heading_text, line_no)
        heading_duplicates.setdefault(section_id, []).append(line_no)
        heading_sections.append(
            {
                "id": section_id,
                "line": line_no,
                "file_line": line_no + body_line_offset,
                "source": "heading",
                "heading": heading_text,
                "heading_level": heading_level,
            }
        )

    section_source = "anchors" if sections else "headings"
    resolved_sections = sections if sections else heading_sections
    source_duplicates = anchor_duplicates if sections else heading_duplicates
    duplicate_sections = {
        section_id: lines for section_id, lines in source_duplicates.items() if len(lines) > 1
    }

    page = metadata.get("page", 1) if metadata else 1
    page_size = metadata.get("page_size", 50) if metadata else 50
    total_count = len(resolved_sections)
    start_idx, end_idx = PaginationCalculator.calculate_pagination_indices(page, page_size, total_count)
    paginated_sections = resolved_sections[start_idx:end_idx]

    response = {
        "ok": True,
        "doc_name": doc_name,
        "path": str(path),
        "sections": paginated_sections,
        "section_source": section_source,
        "body_line_offset": body_line_offset,
        "frontmatter_line_count": body_line_offset,
        "hint": f"For full document structure, use: read_file(path='{path}', mode='scan_only')",
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "has_next": end_idx < total_count,
            "has_prev": page > 1,
        },
    }

    if not sections and heading_sections:
        response["warning"] = (
            "No explicit section anchors found; returning heading-derived section IDs. "
            "Use apply_patch/replace_range or add <!-- ID: ... --> anchors for stable replace_section targeting."
        )

    if duplicate_sections:
        response["duplicates"] = duplicate_sections
        if sections:
            response["warning"] = (
                "Duplicate section anchors detected; use apply_patch or fix anchors before replace_section."
            )
        elif "warning" not in response:
            response["warning"] = (
                "Duplicate heading-derived section IDs detected; headings may be ambiguous for targeting."
            )

    return helper.apply_context_payload(response, context)


async def _handle_list_checklist_items(
    project: Dict[str, Any],
    doc_name: str,
    metadata: Dict[str, Any],
    helper: Any,
    context: Any,
) -> Dict[str, Any]:
    """Return checklist items with line numbers for replace_range usage."""
    docs_mapping = project.get("docs") or {}
    path_str = docs_mapping.get(doc_name)
    if not path_str:
        return helper.apply_context_payload(
            helper.error_response(f"Document '{doc_name}' is not registered for project '{project.get('name')}'."),
            context,
        )

    path = Path(path_str)
    if not path.exists():
        return helper.apply_context_payload(
            helper.error_response(f"Document path '{path}' does not exist."),
            context,
        )

    if doc_name != "checklist":
        return helper.apply_context_payload(
            helper.error_response("list_checklist_items is only supported for checklist documents."),
            context,
        )

    query_text = metadata.get("text")
    case_sensitive = metadata.get("case_sensitive", True)
    require_match = metadata.get("require_match", False)

    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    parsed = parse_frontmatter(text)
    body_lines = parsed.body.splitlines()
    body_line_offset = len(parsed.frontmatter_raw.splitlines()) if parsed.has_frontmatter else 0
    items: List[Dict[str, Any]] = []
    matches: List[Dict[str, Any]] = []
    pattern = re.compile(r"^- \[(?P<mark>[ xX])\]\s*(?P<text>.*)$")
    section_id = None
    duplicates: Dict[str, List[int]] = {}

    for line_no, line in enumerate(body_lines, start=1):
        stripped = line.strip()
        if stripped.startswith("<!-- ID:") and stripped.endswith("-->"):
            section_id = stripped[len("<!-- ID:"): -len("-->")].strip()
            duplicates.setdefault(section_id, []).append(line_no)
            continue

        match = pattern.match(stripped)
        if not match:
            continue
        item_text = match.group("text")
        status = "checked" if match.group("mark").lower() == "x" else "unchecked"
        entry = {
            "line": line_no,
            "start_line": line_no,
            "end_line": line_no,
            "file_line": line_no + body_line_offset,
            "status": status,
            "text": item_text,
            "raw": line,
            "section": section_id,
        }
        items.append(entry)
        if query_text is None:
            matches.append(entry)
        elif case_sensitive and item_text == query_text:
            matches.append(entry)
        elif not case_sensitive and item_text.lower() == str(query_text).lower():
            matches.append(entry)

    if require_match and query_text and not matches:
        return helper.apply_context_payload(
            helper.error_response(f"No checklist items matched text: {query_text}"),
            context,
        )

    page = metadata.get("page", 1) if metadata else 1
    page_size = metadata.get("page_size", 20) if metadata else 20
    total_items_count = len(items)
    total_matches_count = len(matches)

    start_idx, end_idx = PaginationCalculator.calculate_pagination_indices(page, page_size, total_items_count)
    paginated_items = items[start_idx:end_idx]

    match_start, match_end = PaginationCalculator.calculate_pagination_indices(page, page_size, total_matches_count)
    paginated_matches = matches[match_start:match_end]

    response = {
        "ok": True,
        "doc": doc_name,
        "path": str(path),
        "total_items": total_items_count,
        "items": paginated_items,
        "matches": paginated_matches,
        "body_line_offset": body_line_offset,
        "frontmatter_line_count": body_line_offset,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items_count,
            "total_matches": total_matches_count,
            "has_next": end_idx < total_items_count,
            "has_prev": page > 1,
        },
    }
    duplicate_sections = {
        section: lines for section, lines in duplicates.items() if len(lines) > 1
    }
    if duplicate_sections:
        response["duplicates"] = duplicate_sections
        response["warning"] = (
            "Duplicate section anchors detected; checklist items may map to ambiguous sections."
        )
    return helper.apply_context_payload(response, context)
