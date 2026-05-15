"""Query/list action helpers for manage_docs."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.doc_management.changelog import (
    accepted_entries_with_safe_provenance,
    parse_changelog_entries,
    parse_global_changelog_entries,
    preview_global_reconciliation,
    reconcile_global_changelog,
    render_global_changelog,
)
from scribe_mcp.utils.estimator import PaginationCalculator
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.utils.slug import slugify_project_name


_QUERY_TRANSFORM_ACTIONS = {"normalize_headers", "generate_toc", "validate_crosslinks"}
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+\S.*)$")
_PHASE_TASK_PACKAGE_PATTERN = re.compile(
    r"^\*\*Task Package\s+(?P<package_id>\d+(?:\.\d+)?)\s+[—-]\s+(?P<title>.+?)\*\*\s*$"
)
_CHECKLIST_ITEM_PATTERN = re.compile(r"^- \[(?P<mark>[ xX])\]\s*(?P<text>.*)$")
_CHECKLIST_ITEM_WITH_ID_PATTERN = re.compile(
    r"^- \[(?P<mark>[ xX])\]\s*<!--\s*id:\s*(?P<id>[a-zA-Z0-9_-]+)\s*-->\s*(?P<text>.*)$"
)
_CHECKLIST_ID_PHASE_PATTERN = re.compile(r"^p(?P<phase>\d+)-(?P<slug>[a-z0-9-]+)$")


def _resolve_registered_doc_name(project: Dict[str, Any], doc_name: str) -> Optional[str]:
    docs_mapping = project.get("docs") or {}
    if doc_name in docs_mapping:
        return doc_name

    requested = str(doc_name).strip()
    if not requested:
        return None

    requested_lower = requested.lower()
    requested_stem = Path(requested).stem.lower()

    for registered_name, registered_path in docs_mapping.items():
        name = str(registered_name).strip()
        if name.lower() == requested_lower:
            return registered_name

        path_obj = Path(str(registered_path))
        if path_obj.name.lower() == requested_lower or path_obj.stem.lower() == requested_stem:
            return registered_name

    return None


def _normalize_heading_text(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"\s+#+$", "", cleaned).strip()
    return cleaned


def _heading_to_section_id(heading_text: str, fallback_index: int) -> str:
    candidate = slugify_project_name(_normalize_heading_text(heading_text))
    return candidate or f"section_{fallback_index}"


async def inspect_document_sections(path: Path) -> Dict[str, Any]:
    """Inspect a document and return stable section targeting metadata."""
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return inspect_document_sections_from_text(text)


def inspect_document_sections_from_text(text: str) -> Dict[str, Any]:
    """Inspect markdown content and return stable section targeting metadata."""
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

    payload: Dict[str, Any] = {
        "sections": resolved_sections,
        "section_source": section_source,
        "body_line_offset": body_line_offset,
        "frontmatter_line_count": body_line_offset,
    }
    if not sections and heading_sections:
        payload["warning"] = (
            "No explicit section anchors found; returning heading-derived section IDs. "
            "Use apply_patch/replace_range or add <!-- ID: ... --> anchors for stable replace_section targeting."
        )
    if duplicate_sections:
        payload["duplicates"] = duplicate_sections
        if sections:
            payload["warning"] = (
                "Duplicate section anchors detected; use apply_patch or fix anchors before replace_section."
            )
        elif "warning" not in payload:
            payload["warning"] = (
                "Duplicate heading-derived section IDs detected; headings may be ambiguous for targeting."
            )
    return payload


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
        resolved_doc_name = _resolve_registered_doc_name(project, doc_name)
        if resolved_doc_name is None:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return helper.apply_context_payload(response, context)
        return await _handle_list_sections(
            project,
            doc_name=resolved_doc_name,
            metadata=metadata,
            helper=helper,
            context=context,
        )

    if action == "list_checklist_items":
        if not doc_name:
            response = {"ok": False, "error": "list_checklist_items requires doc_name parameter"}
            return helper.apply_context_payload(response, context)
        resolved_doc_name = _resolve_registered_doc_name(project, doc_name)
        if resolved_doc_name is None:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return helper.apply_context_payload(response, context)
        return await _handle_list_checklist_items(
            project,
            doc_name=resolved_doc_name,
            metadata=metadata if isinstance(metadata, dict) else {},
            helper=helper,
            context=context,
        )

    if action == "preview_reconciliation":
        return await _handle_preview_reconciliation(
            project,
            metadata=metadata if isinstance(metadata, dict) else {},
            helper=helper,
            context=context,
        )

    if action == "apply_global_changelog":
        return await _handle_apply_global_changelog(
            project,
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

    section_payload = await inspect_document_sections(path)
    resolved_sections = section_payload.get("sections", [])
    section_source = section_payload.get("section_source", "headings")
    body_line_offset = int(section_payload.get("body_line_offset", 0) or 0)
    duplicate_sections = section_payload.get("duplicates", {})

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

    warning = section_payload.get("warning")
    if warning:
        response["warning"] = warning
    if duplicate_sections:
        response["duplicates"] = duplicate_sections

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

    if doc_name.strip().lower() != "checklist":
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


def _resolve_planning_doc_name(
    *,
    project: Dict[str, Any],
    requested: str,
    fallback: str,
) -> Optional[str]:
    candidate = requested.strip() if requested else fallback
    resolved = _resolve_registered_doc_name(project, candidate)
    if resolved:
        return resolved
    return _resolve_registered_doc_name(project, fallback)


def _extract_phase_plan_packages(text: str) -> List[Dict[str, Any]]:
    parsed = parse_frontmatter(text)
    packages: List[Dict[str, Any]] = []
    for line_no, line in enumerate(parsed.body.splitlines(), start=1):
        match = _PHASE_TASK_PACKAGE_PATTERN.match(line.strip())
        if not match:
            continue
        package_id = match.group("package_id")
        title = match.group("title").strip()
        phase_part = package_id.split(".", maxsplit=1)[0]
        phase_number = int(phase_part) if phase_part.isdigit() else None
        packages.append(
            {
                "package_id": package_id,
                "title": title,
                "slug": slugify_project_name(title),
                "phase_number": phase_number,
                "line": line_no,
            }
        )
    return packages


def _extract_checklist_items(text: str) -> List[Dict[str, Any]]:
    parsed = parse_frontmatter(text)
    items: List[Dict[str, Any]] = []
    for line_no, line in enumerate(parsed.body.splitlines(), start=1):
        stripped = line.strip()
        rich_match = _CHECKLIST_ITEM_WITH_ID_PATTERN.match(stripped)
        if rich_match:
            checklist_id = rich_match.group("id").strip()
            item_text = rich_match.group("text").strip()
            status = "checked" if rich_match.group("mark").lower() == "x" else "unchecked"
            phase_number = None
            id_slug = None
            id_match = _CHECKLIST_ID_PHASE_PATTERN.match(checklist_id.lower())
            if id_match:
                phase_number = int(id_match.group("phase"))
                id_slug = id_match.group("slug")
            items.append(
                {
                    "id": checklist_id,
                    "text": item_text,
                    "status": status,
                    "phase_number": phase_number,
                    "id_slug": id_slug,
                    "line": line_no,
                }
            )
            continue

        fallback_match = _CHECKLIST_ITEM_PATTERN.match(stripped)
        if not fallback_match:
            continue
        item_text = fallback_match.group("text").strip()
        status = "checked" if fallback_match.group("mark").lower() == "x" else "unchecked"
        items.append(
            {
                "id": None,
                "text": item_text,
                "status": status,
                "phase_number": None,
                "id_slug": None,
                "line": line_no,
            }
        )
    return items


def _packages_match_checklist_item(package: Dict[str, Any], checklist_item: Dict[str, Any]) -> bool:
    package_phase = package.get("phase_number")
    item_phase = checklist_item.get("phase_number")
    if package_phase is not None and item_phase is not None and package_phase != item_phase:
        return False

    package_slug = (package.get("slug") or "").replace("_", "-")
    item_slug = (checklist_item.get("id_slug") or "").replace("_", "-")
    item_text_slug = slugify_project_name(checklist_item.get("text") or "").replace("_", "-")

    if not package_slug:
        return False
    if item_slug:
        return package_slug in item_slug or item_slug in package_slug
    return package_slug in item_text_slug or item_text_slug in package_slug


def _lookup_flag(flags: Dict[str, Any], doc_name: str, suffix: str) -> Any:
    direct_key = f"{doc_name}_{suffix}"
    if direct_key in flags:
        return flags[direct_key]
    lowered = doc_name.lower()
    lower_key = f"{lowered}_{suffix}"
    if lower_key in flags:
        return flags[lower_key]
    return None


def _build_hash_signal(*, docs_meta: Dict[str, Any], doc_name: str) -> Dict[str, Any]:
    baseline_hashes = docs_meta.get("baseline_hashes") or {}
    current_hashes = docs_meta.get("current_hashes") or {}
    baseline = baseline_hashes.get(doc_name)
    current = current_hashes.get(doc_name)
    changed = None
    if baseline is not None and current is not None:
        changed = baseline != current
    return {"doc_name": doc_name, "baseline": baseline, "current": current, "changed": changed}


async def _handle_preview_reconciliation(
    project: Dict[str, Any],
    metadata: Dict[str, Any],
    helper: Any,
    context: Any,
) -> Dict[str, Any]:
    preview_type = str(metadata.get("preview_type") or "").strip().lower()
    if preview_type == "changelog":
        return await _handle_changelog_reconciliation_preview(
            project=project,
            metadata=metadata,
            helper=helper,
            context=context,
        )

    docs_mapping = project.get("docs") or {}
    phase_doc_name = _resolve_planning_doc_name(
        project=project,
        requested=str(metadata.get("phase_doc_name") or "").strip(),
        fallback="phase_plan",
    )
    checklist_doc_name = _resolve_planning_doc_name(
        project=project,
        requested=str(metadata.get("checklist_doc_name") or "").strip(),
        fallback="checklist",
    )

    missing_docs: List[str] = []
    if phase_doc_name is None:
        missing_docs.append("phase_plan")
    if checklist_doc_name is None:
        missing_docs.append("checklist")
    if missing_docs:
        return helper.apply_context_payload(
            helper.error_response(
                "preview_reconciliation requires registered phase-plan and checklist documents.",
            ),
            context,
        )

    phase_path = Path(str(docs_mapping.get(phase_doc_name)))
    checklist_path = Path(str(docs_mapping.get(checklist_doc_name)))
    if not phase_path.exists() or not checklist_path.exists():
        missing_paths = [str(path) for path in (phase_path, checklist_path) if not path.exists()]
        return helper.apply_context_payload(
            helper.error_response(
                f"preview_reconciliation requires existing planning docs; missing: {', '.join(missing_paths)}"
            ),
            context,
        )

    phase_text, checklist_text = await asyncio.gather(
        asyncio.to_thread(phase_path.read_text, encoding="utf-8"),
        asyncio.to_thread(checklist_path.read_text, encoding="utf-8"),
    )

    packages = _extract_phase_plan_packages(phase_text)
    checklist_items = _extract_checklist_items(checklist_text)

    mapped_checklist_ids: set[str] = set()
    mapped_checklist_indices: set[int] = set()
    unmapped_packages: List[Dict[str, Any]] = []
    for package in packages:
        package_matches: List[Dict[str, Any]] = []
        for item_index, checklist_item in enumerate(checklist_items):
            if _packages_match_checklist_item(package, checklist_item):
                package_matches.append(checklist_item)
                mapped_checklist_indices.add(item_index)
                if checklist_item.get("id"):
                    mapped_checklist_ids.add(checklist_item["id"])
        if not package_matches:
            unmapped_packages.append(
                {
                    "package_id": package["package_id"],
                    "title": package["title"],
                    "phase_number": package.get("phase_number"),
                    "line": package.get("line"),
                }
            )

    stale_checklist_items: List[Dict[str, Any]] = []
    for item_index, checklist_item in enumerate(checklist_items):
        if item_index in mapped_checklist_indices:
            continue
        if checklist_item.get("id") is None:
            continue
        stale_checklist_items.append(
            {
                "id": checklist_item.get("id"),
                "text": checklist_item.get("text"),
                "phase_number": checklist_item.get("phase_number"),
                "line": checklist_item.get("line"),
                "status": checklist_item.get("status"),
            }
        )

    docs_meta = ((project.get("meta") or {}).get("docs") or {})
    flags = docs_meta.get("flags") or {}
    docs_ready_for_work = flags.get("docs_ready_for_work")

    phase_hash_signal = _build_hash_signal(docs_meta=docs_meta, doc_name=phase_doc_name)
    checklist_hash_signal = _build_hash_signal(docs_meta=docs_meta, doc_name=checklist_doc_name)

    readiness_conflicts: List[str] = []
    if docs_ready_for_work is True and (unmapped_packages or stale_checklist_items):
        readiness_conflicts.append(
            "docs_ready_for_work is true while reconciliation preview still reports unmapped or stale planning items."
        )

    phase_modified_flag = _lookup_flag(flags, phase_doc_name, "modified")
    checklist_modified_flag = _lookup_flag(flags, checklist_doc_name, "modified")
    if phase_hash_signal["changed"] is True and phase_modified_flag is False:
        readiness_conflicts.append(
            f"{phase_doc_name}_modified flag is false but baseline/current hashes indicate drift."
        )
    if checklist_hash_signal["changed"] is True and checklist_modified_flag is False:
        readiness_conflicts.append(
            f"{checklist_doc_name}_modified flag is false but baseline/current hashes indicate drift."
        )

    response = {
        "ok": True,
        "action": "preview_reconciliation",
        "writes_performed": False,
        "phase_plan_doc": phase_doc_name,
        "checklist_doc": checklist_doc_name,
        "summary": {
            "phase_task_packages": len(packages),
            "checklist_items": len(checklist_items),
            "mapped_checklist_ids": sorted(mapped_checklist_ids),
            "unmapped_package_count": len(unmapped_packages),
            "stale_checklist_count": len(stale_checklist_items),
            "has_drift": bool(unmapped_packages or stale_checklist_items),
            "readiness_conflict_count": len(readiness_conflicts),
        },
        "unmapped_packages": unmapped_packages,
        "stale_checklist_items": stale_checklist_items,
        "readiness_signals": {
            "docs_ready_for_work": docs_ready_for_work,
            "phase_plan_modified_flag": phase_modified_flag,
            "checklist_modified_flag": checklist_modified_flag,
            "phase_plan_hash_signal": phase_hash_signal,
            "checklist_hash_signal": checklist_hash_signal,
            "readiness_conflicts": readiness_conflicts,
        },
        "preview_examples": {
            "unmapped_package": unmapped_packages[0] if unmapped_packages else None,
            "stale_checklist_item": stale_checklist_items[0] if stale_checklist_items else None,
        },
    }
    return helper.apply_context_payload(response, context)


async def _handle_changelog_reconciliation_preview(
    project: Dict[str, Any],
    metadata: Dict[str, Any],
    helper: Any,
    context: Any,
) -> Dict[str, Any]:
    docs_mapping = project.get("docs") or {}
    changelog_doc_name = _resolve_registered_doc_name(project, str(metadata.get("changelog_doc_name") or "CHANGELOG"))
    if changelog_doc_name is None:
        return helper.apply_context_payload(
            helper.error_response("preview_reconciliation changelog mode requires a registered CHANGELOG document."),
            context,
        )

    changelog_path = Path(str(docs_mapping.get(changelog_doc_name)))
    global_path = Path(str(project.get("root") or "") ) / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"

    if not changelog_path.exists():
        return helper.apply_context_payload(helper.error_response(f"Changelog path '{changelog_path}' does not exist."), context)

    project_text = await asyncio.to_thread(changelog_path.read_text, encoding="utf-8")
    global_text = ""
    if global_path.exists():
        global_text = await asyncio.to_thread(global_path.read_text, encoding="utf-8")

    project_slug = slugify_project_name(str(project.get("name") or ""))
    preview = preview_global_reconciliation(
        project_slug=project_slug,
        project_changelog_text=project_text,
        global_changelog_text=global_text,
    )
    preview.update(
        {
            "ok": True,
            "action": "preview_reconciliation",
            "preview_type": "changelog",
            "project_changelog_doc": changelog_doc_name,
            "project_changelog_path": str(changelog_path),
            "global_changelog_path": str(global_path),
        }
    )
    return helper.apply_context_payload(preview, context)


async def _handle_apply_global_changelog(
    project: Dict[str, Any],
    metadata: Dict[str, Any],
    helper: Any,
    context: Any,
) -> Dict[str, Any]:
    docs_mapping = project.get("docs") or {}
    changelog_doc_name = _resolve_registered_doc_name(project, str(metadata.get("changelog_doc_name") or "CHANGELOG"))
    if changelog_doc_name is None:
        return helper.apply_context_payload(
            helper.error_response("apply_global_changelog requires a registered CHANGELOG document."),
            context,
        )
    changelog_path = Path(str(docs_mapping.get(changelog_doc_name)))
    global_path = Path(str(project.get("root") or "")) / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
    if not changelog_path.exists():
        return helper.apply_context_payload(helper.error_response(f"Changelog path '{changelog_path}' does not exist."), context)
    project_text = await asyncio.to_thread(changelog_path.read_text, encoding="utf-8")
    project_slug = slugify_project_name(str(project.get("name") or ""))
    _safe_entries, blocked_entries = accepted_entries_with_safe_provenance(parse_changelog_entries(project_text))
    if blocked_entries:
        return helper.apply_context_payload(
            {
                "ok": False,
                "error": "apply_global_changelog blocked: accepted changelog entries contain unsafe or missing observed_context provenance.",
                "action": "apply_global_changelog",
                "project_changelog_doc": changelog_doc_name,
                "project_changelog_path": str(changelog_path),
                "global_changelog_path": str(global_path),
                "writes_performed": False,
                "provenance_blocked_entries": blocked_entries,
            },
            context,
        )
    previous_text = ""
    if global_path.exists():
        previous_text = await asyncio.to_thread(global_path.read_text, encoding="utf-8")
    rendered = reconcile_global_changelog(
        project_slug=project_slug,
        project_changelog_text=project_text,
        existing_global_changelog_text=previous_text,
    )
    writes_performed = rendered != previous_text
    if writes_performed:
        await asyncio.to_thread(global_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(global_path.write_text, rendered, encoding="utf-8")
    applied_entries = parse_global_changelog_entries(rendered, default_source_project=project_slug)
    return helper.apply_context_payload(
        {
            "ok": True,
            "action": "apply_global_changelog",
            "project_changelog_doc": changelog_doc_name,
            "project_changelog_path": str(changelog_path),
            "global_changelog_path": str(global_path),
            "writes_performed": writes_performed,
            "applied_entry_count": len(applied_entries),
            "applied_source_keys": [list(entry.source_key) for entry in applied_entries],
        },
        context,
    )
