"""Core logic for managing project documentation updates."""

from __future__ import annotations

import asyncio
import ast
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Import with absolute paths from scribe_mcp root
from scribe_mcp.utils.files import async_atomic_write, ensure_parent, preflight_backup
from scribe_mcp.utils.slug import slugify_filename, slugify_project_name
from scribe_mcp.config.repo_config import RepoDiscovery
from scribe_mcp.utils.frontmatter import (
    apply_frontmatter_updates,
    build_frontmatter,
    parse_frontmatter,
)
from scribe_mcp.utils.diff_compiler import compile_unified_diff
from scribe_mcp.utils.time import utcnow
from scribe_mcp.templates import template_root
from scribe_mcp.utils.parameter_validator import (
    BulletproofParameterCorrector,
)
import re

# Setup logging for doc management operations
doc_logger = logging.getLogger(__name__)

FRAGMENT_DIR = (template_root().parent / "fragments").resolve()
SECTION_MARKER = "<!-- ID: {section} -->"
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_HEADER_LINE_PATTERN = re.compile(r"^(#{1,6})\s+(.*\S.*)$")
_SETEXT_UNDERLINE_PATTERN = re.compile(r"^(?:={3,}|-{3,})$")
_ATX_WITHOUT_SPACE_PATTERN = re.compile(r"^(#{1,6})([^#\s].*)$")
_MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PATCH_MODE_STRUCTURED = "structured"
PATCH_MODE_UNIFIED = "unified"
PATCH_MODE_ALIASES = {"diff": PATCH_MODE_UNIFIED}
PATCH_MODE_ALLOWED = {PATCH_MODE_STRUCTURED, PATCH_MODE_UNIFIED}


def _log_operation(
    level: str,
    operation: str,
    doc_name: str,
    section: Optional[str],
    action: str,
    file_path: Path,
    duration_ms: float,
    file_size_before: int,
    file_size_after: int,
    success: bool,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Log document operations with structured data."""
    log_data = {
        "timestamp": time.time(),
        "operation": operation,
        "doc_name": doc_name,
        "section": section,
        "action": action,
        "file_path": str(file_path),
        "duration_ms": duration_ms,
        "file_size_before": file_size_before,
        "file_size_after": file_size_after,
        "file_size_change": file_size_after - file_size_before,
        "success": success,
        "error_message": error_message,
        "metadata": metadata or {}
    }

    # Convert to JSON for structured logging
    log_message = json.dumps(log_data, separators=(',', ':'))

    if level == "error":
        doc_logger.error(f"Document operation failed: {operation} on {doc_name} - {error_message or 'Unknown error'}", extra={"structured_log": log_data})
    elif level == "warning":
        doc_logger.warning(f"Document operation warning: {operation} on {doc_name} - {error_message}", extra={"structured_log": log_data})
    elif level == "info":
        doc_logger.info(f"Document operation successful: {operation} on {doc_name}", extra={"structured_log": log_data})
    else:
        doc_logger.debug(f"Document operation: {operation} on {doc_name}", extra={"structured_log": log_data})


@dataclass
class DocChangeResult:
    doc_name: str
    section: Optional[str]
    action: str
    path: Path
    before_hash: str
    after_hash: str
    content_written: str
    diff_preview: str
    extra: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None
    verification_passed: bool = False
    file_size_before: int = 0
    file_size_after: int = 0


class DocumentOperationError(Exception):
    """Raised when a document operation fails."""
    def __init__(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.extra = extra or {}


class DocumentVerificationError(Exception):
    """Raised when document write verification fails."""
    pass


class DocumentValidationError(Exception):
    """Raised when document validation fails."""
    pass


async def apply_doc_change(
    project: Dict[str, Any],
    *,
    doc_name: Optional[str] = None,
    doc: Optional[str] = None,
    doc_category: Optional[str] = None,
    action: str,
    section: Optional[str],
    content: Optional[str],
    patch: Optional[str] = None,
    patch_source_hash: Optional[str] = None,
    edit: Optional[Dict[str, Any]] = None,
    patch_mode: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    template: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    document_store: Optional[Any] = None,
) -> DocChangeResult:
    """Apply a document change with comprehensive error handling and verification."""
    # Auto-resolve document_store from app.state when not explicitly passed.
    if document_store is None:
        try:
            from scribe_mcp.server import app as _app
            document_store = getattr(getattr(_app, "state", None), "document_store", None)
        except Exception:
            pass
    start_time = time.time()
    file_size_before = 0
    resolved_doc_name = doc_name or doc
    if not resolved_doc_name:
        return DocChangeResult(
            doc_name="",
            section=section,
            action=action,
            path=Path(""),
            before_hash="",
            after_hash="",
            content_written="",
            diff_preview="",
            extra={"missing_field": "doc_name"},
            success=False,
            error_message="DOC_NOT_FOUND: doc_name is required",
            verification_passed=False,
            file_size_before=0,
            file_size_after=0,
        )
    doc_name = resolved_doc_name

    try:
        # Validate and correct inputs (bulletproof - never fails)
        doc_name, action, section, content, template, metadata = _validate_and_correct_inputs(
            doc_name, action, section, content, patch, patch_source_hash, edit,
            start_line, end_line, template, metadata
        )

        # Resolve and validate document path
        if action == "create_doc":
            doc_path = _resolve_create_doc_path(project, metadata, doc_name)
        else:
            doc_path = _resolve_doc_path(project, doc_name)
            # Auto-register if file exists on disk but isn't in docs mapping
            docs_mapping = project.get("docs") or {}
            if doc_name not in docs_mapping:
                if doc_path.exists():
                    docs_mapping[doc_name] = str(doc_path)
                    project["docs"] = docs_mapping
                    doc_logger.info("Auto-registered '%s' at %s", doc_name, doc_path)
                else:
                    raise DocumentOperationError(f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered")
        repo_root = Path(project["root"]).resolve()
        await ensure_parent(doc_path, repo_root=repo_root)

        # Get original content and metadata
        original_text = ""
        file_size_before = 0
        if not doc_path.exists():
            # CortaStore fallback: fetch from remote object store if eligible.
            try:
                from scribe_mcp.object_store.keys import should_sync, path_to_key

                if should_sync(doc_path, repo_root):
                    from scribe_mcp import server as _srv

                    _store = getattr(getattr(_srv.app, "state", None), "document_store", None)
                    if _store:
                        _key = path_to_key(doc_path, repo_root)
                        _remote = await _store.read(_key)
                        if _remote:
                            doc_path.parent.mkdir(parents=True, exist_ok=True)
                            await asyncio.to_thread(doc_path.write_text, _remote, encoding="utf-8")
            except Exception:
                pass  # Fallback failed — treat as new doc.
        if doc_path.exists():
            try:
                original_text = await asyncio.to_thread(doc_path.read_text, encoding="utf-8")
                file_size_before = doc_path.stat().st_size
            except (OSError, UnicodeDecodeError) as e:
                raise DocumentOperationError(f"Failed to read existing document {doc_path}: {e}")

        before_hash = _hash_text(original_text)
        try:
            original_parsed = parse_frontmatter(original_text)
        except ValueError as exc:
            raise DocumentOperationError(str(exc))
        original_body = original_parsed.body
        frontmatter_line_count = len(original_parsed.frontmatter_raw.splitlines()) if original_parsed.has_frontmatter else 0

        # Render content when required
        rendered_content: Optional[str] = None
        if action in {"replace_section", "append"}:
            try:
                rendered_content = await _render_content(project, content, template, metadata)
            except Exception as e:
                raise DocumentOperationError(f"Failed to render content: {e}")

        # Apply the change based on action
        extra: Dict[str, Any] = {}
        try:
            if action == "replace_section":
                assert rendered_content is not None
                allow_append = False
                if isinstance(metadata, dict):
                    allow_append = bool(metadata.get("allow_append") or metadata.get("scaffold"))
                updated_body = _replace_section(
                    original_body,
                    section,
                    rendered_content,
                    allow_append=allow_append,
                )
            elif action == "append":
                assert rendered_content is not None
                meta_payload = metadata if isinstance(metadata, dict) else {}
                position_value = meta_payload.get("position", "after")
                updated_body = _append_block(
                    original_body,
                    rendered_content,
                    section=section,
                    position=str(position_value),
                )
            elif action == "status_update":
                updated_body = _toggle_checklist_status(original_body, section, metadata or {})
            elif action == "apply_patch":
                patch_text = patch or content
                current_hash = _hash_text(original_body)
                patch_hash_source = "provided" if patch_source_hash else "auto"
                patch_used = patch_text or ""
                meta_mode = None
                if isinstance(metadata, dict):
                    meta_mode = metadata.get("patch_mode") or metadata.get("mode")

                def _normalize_mode(value: Any) -> str:
                    if not value:
                        return ""
                    normalized = str(value).strip().lower()
                    return PATCH_MODE_ALIASES.get(normalized, normalized)

                if patch_mode and meta_mode:
                    normalized_arg = _normalize_mode(patch_mode)
                    normalized_meta = _normalize_mode(meta_mode)
                    if normalized_arg and normalized_meta and normalized_arg != normalized_meta:
                        raise DocumentOperationError(
                            "PATCH_MODE_CONFLICT: patch_mode argument conflicts with metadata"
                        )

                effective_mode = _normalize_mode(patch_mode) or _normalize_mode(meta_mode)
                if not effective_mode:
                    # Smart default: unified if patch provided, structured if edit provided
                    if patch_used:
                        effective_mode = PATCH_MODE_UNIFIED
                    elif edit:
                        effective_mode = PATCH_MODE_STRUCTURED
                    else:
                        effective_mode = PATCH_MODE_UNIFIED  # Prefer unified as default

                if patch_used and edit:
                    raise DocumentOperationError(
                        "PATCH_MODE_CONFLICT: provide either patch or edit, not both"
                    )

                if effective_mode not in PATCH_MODE_ALLOWED:
                    raise DocumentOperationError(
                        "PATCH_MODE_INVALID: use patch_mode=structured or patch_mode=unified"
                    )

                if effective_mode == PATCH_MODE_STRUCTURED:
                    if not isinstance(edit, dict):
                        raise DocumentOperationError(
                            "PATCH_MODE_STRUCTURED_REQUIRES_EDIT: provide edit payload"
                        )
                    allow_append = False
                    if isinstance(metadata, dict):
                        allow_append = bool(metadata.get("allow_append") or metadata.get("scaffold"))
                    updated_candidate = _apply_structured_edit(
                        original_body,
                        edit,
                        allow_append=allow_append,
                    )
                    patch_used = compile_unified_diff(
                        original_body,
                        updated_candidate,
                        fromfile="before",
                        tofile="after",
                    )
                elif not patch_used:
                    raise DocumentOperationError(
                        "PATCH_MODE_UNIFIED_REQUIRES_PATCH: provide patch content"
                    )

                if patch_source_hash and current_hash != patch_source_hash:
                    raise DocumentOperationError(
                        "PATCH_STALE_SOURCE: patch_source_hash does not match current file content",
                        extra={"precondition_failed": "SOURCE_HASH_MISMATCH"},
                    )

                # Calculate frontmatter offset for smart matching
                frontmatter_lines = 0
                if original_parsed.has_frontmatter and original_parsed.frontmatter_raw:
                    frontmatter_lines = len(original_parsed.frontmatter_raw.splitlines())
                body_line_count = len(original_body.splitlines())
                declared_ranges = _compute_patch_ranges(patch_used)
                header_out_of_date = any(
                    int(range_info.get("start_line", 0)) > body_line_count
                    for range_info in declared_ranges
                )

                try:
                    # Use context-aware smart patch application
                    updated_body, hunks_applied, smart_extra = _apply_unified_patch_smart(
                        original_body, patch_used, frontmatter_lines
                    )
                    extra = {
                        "hunks_applied": hunks_applied,
                        "patch_source_hash": current_hash,
                        "patch_source_hash_source": patch_hash_source,
                        **smart_extra,
                    }
                    if header_out_of_date:
                        extra["rebase_attempted"] = True
                        extra["rebase_applied"] = True
                except DocumentOperationError as exc:
                    error_message = str(exc)
                    # If smart matching failed, try rebase as last resort
                    if _is_patch_context_error(error_message) and not patch_source_hash:
                        try:
                            rebased_patch, rebase_info = _rebase_patch_to_current_context(
                                original_body, patch_used
                            )
                            patch_used = rebased_patch
                            try:
                                updated_body, hunks_applied, smart_rebase_extra = _apply_unified_patch_smart(
                                    original_body,
                                    patch_used,
                                    frontmatter_lines,
                                )
                            except DocumentOperationError:
                                updated_body, hunks_applied = _apply_unified_patch(
                                    original_body,
                                    patch_used,
                                )
                                smart_rebase_extra = {}
                            extra = {
                                "hunks_applied": hunks_applied,
                                "patch_source_hash": current_hash,
                                "patch_source_hash_source": "auto",
                                "rebase_attempted": True,
                                "rebase_applied": True,
                                "rebase_info": rebase_info,
                                **smart_rebase_extra,
                            }
                        except DocumentOperationError as rebase_error:
                            diagnostics = _build_patch_failure_diagnostics(
                                original_body, patch_text or "", str(rebase_error)
                            )
                            diagnostics.setdefault("smart_matching_failed", error_message)
                            diagnostics.setdefault("rebase_attempted", True)
                            if getattr(rebase_error, "extra", None):
                                diagnostics.setdefault("rebase_details", rebase_error.extra)
                            diagnostics.setdefault("rebase_failed_reason", str(rebase_error))
                            raise DocumentOperationError(
                                error_message,
                                extra={"patch_diagnostics": diagnostics},
                            )
                    else:
                        diagnostics = _build_patch_failure_diagnostics(
                            original_body, patch_used, error_message
                        )
                        raise DocumentOperationError(
                            error_message,
                            extra={"patch_diagnostics": diagnostics},
                        )
                patch_ranges = _compute_patch_ranges(patch_used)
                if patch_ranges:
                    extra["affected_ranges"] = patch_ranges
                if dry_run:
                    previews = _build_bounded_previews(original_body, updated_body, patch_ranges)
                    if previews:
                        extra["preview_window"] = previews[0]
                        extra["preview_windows"] = previews
            elif action == "normalize_headers":
                updated_body = _normalize_headers_text(original_body)
            elif action == "generate_toc":
                updated_body = _generate_toc_text(original_body)
            elif action == "replace_range":
                resolved_start = start_line
                resolved_end = end_line
                if isinstance(metadata, dict):
                    if resolved_start is None and "start_line" in metadata:
                        resolved_start = metadata["start_line"]
                    if resolved_end is None and "end_line" in metadata:
                        resolved_end = metadata["end_line"]
                if resolved_start is not None:
                    resolved_start = int(resolved_start)
                if resolved_end is not None:
                    resolved_end = int(resolved_end)

                # --- Coordinate system adjustment ---
                # replace_range operates on the *body* (frontmatter stripped).
                # Callers using line numbers from read_file (scan_only, line_range)
                # get full-file coordinates that include frontmatter lines.
                # When metadata.line_reference="file", auto-adjust by subtracting
                # frontmatter line count.  Default is "body" (legacy behavior) for
                # internal callers; the MCP tool layer injects "file" when the caller
                # doesn't specify.
                line_ref = "body"
                if isinstance(metadata, dict):
                    line_ref = str(metadata.get("line_reference", "body")).strip().lower()
                if line_ref not in ("file", "body"):
                    line_ref = "body"

                if line_ref == "file" and frontmatter_line_count > 0 and resolved_start is not None and resolved_end is not None:
                    resolved_start = resolved_start - frontmatter_line_count
                    resolved_end = resolved_end - frontmatter_line_count
                    if resolved_start < 1:
                        raise DocumentOperationError(
                            f"REPLACE_RANGE_IN_FRONTMATTER: adjusted start_line={resolved_start + frontmatter_line_count} "
                            f"(file-relative) falls within frontmatter ({frontmatter_line_count} lines). "
                            f"Use line numbers that target the document body (line {frontmatter_line_count + 1}+), "
                            f"or pass metadata.line_reference='body' if your numbers already exclude frontmatter."
                        )

                replacement_text = str(content or "")
                # NOTE: replacement content is a body fragment, NOT a standalone document.
                # Never parse it as frontmatter — a leading "---" is a Markdown horizontal
                # rule, not a YAML frontmatter delimiter.  False-positive frontmatter
                # detection here was silently stripping replacement content between "---"
                # lines, causing data loss.

                updated_body = _replace_range_text(
                    original_body,
                    resolved_start,
                    resolved_end,
                    replacement_text,
                )
                if line_ref == "file" and frontmatter_line_count > 0:
                    extra["line_adjustment"] = {
                        "line_reference": "file",
                        "frontmatter_lines": frontmatter_line_count,
                        "original_range": [start_line, end_line],
                        "adjusted_range": [resolved_start, resolved_end],
                    }
            elif action == "replace_text":
                if not isinstance(metadata, dict):
                    raise DocumentOperationError(
                        "REPLACE_TEXT_MISSING_METADATA: provide metadata with find/replace values"
                    )
                find_text = metadata.get("find")
                if not isinstance(find_text, str) or not find_text:
                    raise DocumentOperationError("REPLACE_TEXT_MISSING_FIND: metadata.find is required")
                replace_text = metadata.get("replace")
                if replace_text is None:
                    replace_text = ""
                match_mode = str(metadata.get("match_mode") or "literal").strip().lower()
                if match_mode not in {"literal", "regex", "prefix"}:
                    raise DocumentOperationError(
                        "REPLACE_TEXT_MATCH_MODE_INVALID: use literal, regex, or prefix"
                    )
                replace_all = bool(metadata.get("replace_all", True))
                scope = metadata.get("scope")
                allow_no_match = bool(metadata.get("allow_no_match", False))

                updated_body, hits = _replace_text_with_scope(
                    original_body,
                    find_text=find_text,
                    replace_text=str(replace_text),
                    match_mode=match_mode,
                    replace_all=replace_all,
                    scope=str(scope) if scope else None,
                    allow_no_match=allow_no_match,
                )
                extra["replace_text"] = {
                    "find": find_text,
                    "replace_all": replace_all,
                    "match_mode": match_mode,
                    "scope": scope,
                    "matches": hits,
                }
            elif action == "create_doc":
                overwrite = bool(metadata.get("overwrite")) if isinstance(metadata, dict) else False
                if doc_path.exists() and not overwrite:
                    raise DocumentOperationError(
                        "CREATE_DOC_EXISTS: target path already exists (use metadata.overwrite to replace or "
                        "metadata.register_existing to register without overwrite)"
                    )
                updated_body = _build_create_doc_body(content, metadata)
                if isinstance(metadata, dict) and isinstance(metadata.get("frontmatter"), dict):
                    metadata.setdefault("frontmatter", {})
                if isinstance(metadata, dict):
                    # Ensure frontmatter dict exists for downstream processing
                    metadata.setdefault("frontmatter", {})
                    # Pass doc_category through to frontmatter if not already set
                    if doc_category and "category" not in metadata["frontmatter"]:
                        metadata["frontmatter"]["category"] = doc_category
            elif action == "validate_crosslinks":
                extra = {"crosslinks": _validate_crosslinks(original_text, project, metadata)}
                updated_body = original_body
            else:
                raise ValueError(f"Unsupported action '{action}'.")
        except DocumentOperationError:
            raise
        except Exception as e:
            raise DocumentOperationError(f"Failed to apply {action} operation: {e}")

        after_hash = _hash_text(updated_body)

        body_diff_preview = compile_unified_diff(
            original_body,
            updated_body,
            fromfile="before",
            tofile="after",
        )

        # Short-circuit for read-only actions
        if action == "validate_crosslinks":
            return DocChangeResult(
                doc_name=doc_name,
                section=section,
                action=action,
                path=doc_path,
                before_hash=before_hash,
                after_hash=before_hash,
                content_written=original_text,
                diff_preview="",
                extra=extra if "extra" in locals() else {},
                success=True,
                verification_passed=True,
                file_size_before=file_size_before,
                file_size_after=file_size_before,
            )

        # Apply changes to file system
        file_size_after = 0
        verification_passed = False

        date_str = utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        frontmatter_extra: Dict[str, Any] = {}

        # === AUTO-TRANSFORM HOOK (opt-in via frontmatter) ===
        # Check if document has opted into auto-transforms
        frontmatter_data = original_parsed.frontmatter_data
        auto_normalize = frontmatter_data.get("auto_normalize_headers", False)
        auto_toc = frontmatter_data.get("auto_generate_toc", False)

        transforms_applied = []

        if auto_normalize and action not in ("normalize_headers", "generate_toc"):
            # Apply header normalization to body
            try:
                updated_body = _normalize_headers_text(updated_body)
                transforms_applied.append("normalize_headers")
            except Exception as e:
                # Non-fatal - log but continue
                doc_logger.warning(f"Auto-normalize failed for {doc_name}: {e}")

        if auto_toc and action not in ("normalize_headers", "generate_toc"):
            # Apply TOC generation to body
            try:
                updated_body = _generate_toc_text(updated_body)
                transforms_applied.append("generate_toc")
            except Exception as e:
                # Non-fatal - log but continue
                doc_logger.warning(f"Auto-TOC failed for {doc_name}: {e}")

        allow_frontmatter_create = action != "status_update"

        try:
            updated_text, frontmatter_extra, frontmatter_line_count = _apply_frontmatter_pipeline(
                original_parsed,
                updated_body,
                doc_name=doc_name,
                doc_category=doc_category,
                project=project,
                metadata=metadata,
                date_str=date_str,
                allow_create=allow_frontmatter_create,
            )
            after_hash = _hash_text(updated_text)
            frontmatter_only = updated_body == original_body and bool(frontmatter_extra.get("frontmatter_updated"))
            frontmatter_extra.update(
                {
                    "frontmatter_line_count": frontmatter_line_count,
                    "frontmatter_only": frontmatter_only,
                }
            )
            # Add auto-transforms metadata to frontmatter_extra (after pipeline returns its dict)
            if transforms_applied:
                frontmatter_extra["auto_transforms_applied"] = transforms_applied
            if frontmatter_only:
                diff_preview = ""
            else:
                diff_preview = body_diff_preview
        except ValueError as exc:
            raise DocumentOperationError(str(exc))

        if not dry_run:
            try:
                if doc_path.exists():
                    try:
                        backup_path = await asyncio.to_thread(
                            preflight_backup,
                            doc_path,
                            repo_root=repo_root,
                            context={
                                "component": "files",
                                "op": "backup",
                                "project_name": project.get("name"),
                            },
                        )
                        frontmatter_extra.setdefault("preflight_backup", str(backup_path))
                    except Exception as exc:
                        raise DocumentOperationError(
                            f"DOC_SNAPSHOT_FAILED: {exc}"
                        ) from exc
                # Write the file
                await async_atomic_write(doc_path, updated_text, mode="w", repo_root=repo_root, document_store=document_store)

                # Verify the write was successful
                verification_passed = await _verify_file_write(doc_path, updated_text, after_hash)
                if not verification_passed:
                    raise DocumentVerificationError(f"File write verification failed for {doc_path}")

                file_size_after = doc_path.stat().st_size

                # Log successful operation
                duration_ms = (time.time() - start_time) * 1000
                _log_operation(
                    level="info",
                    operation="apply_doc_change",
                    doc_name=doc_name,
                    section=section,
                    action=action,
                    file_path=doc_path,
                    duration_ms=duration_ms,
                    file_size_before=file_size_before,
                    file_size_after=file_size_after,
                    success=True,
                    metadata={
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                        "dry_run": dry_run
                    }
                )

            except Exception as e:
                # Attempt rollback if write failed
                try:
                    if original_text and doc_path.exists():
                        await async_atomic_write(doc_path, original_text, mode="w", repo_root=repo_root)
                        duration_ms = (time.time() - start_time) * 1000
                        _log_operation(
                            level="warning",
                            operation="apply_doc_change",
                            doc_name=doc_name,
                            section=section,
                            action=action,
                            file_path=doc_path,
                            duration_ms=duration_ms,
                            file_size_before=file_size_before,
                            file_size_after=file_size_before,  # Back to original
                            success=False,
                            error_message="Write failed, rolled back successfully",
                            metadata={"rollback": True, "original_error": str(e)}
                        )
                except Exception as rollback_error:
                    duration_ms = (time.time() - start_time) * 1000
                    _log_operation(
                        level="error",
                        operation="apply_doc_change",
                        doc_name=doc_name,
                        section=section,
                        action=action,
                        file_path=doc_path,
                        duration_ms=duration_ms,
                        file_size_before=file_size_before,
                        file_size_after=file_size_before,
                        success=False,
                        error_message=f"Write failed and rollback failed: {rollback_error}",
                        metadata={"rollback_failed": True, "original_error": str(e)}
                    )

                raise DocumentOperationError(f"Failed to write document {doc_path}: {e}")

        include_frontmatter_extra = bool(
            isinstance(metadata, dict) and metadata.get("include_frontmatter_extra")
        )
        if not include_frontmatter_extra and frontmatter_extra:
            frontmatter_extra = {
                key: value
                for key, value in frontmatter_extra.items()
                if not key.startswith("frontmatter")
            }

        # Always include document structure info so agents know the coordinate
        # system.  Frontmatter lines shift all body content; agents using
        # read_file line numbers need to know this.
        body_line_count = len(updated_body.splitlines()) if updated_body else 0
        document_info: Dict[str, Any] = {
            "frontmatter_lines": frontmatter_line_count,
            "body_lines": body_line_count,
            "total_lines": frontmatter_line_count + body_line_count,
        }
        if frontmatter_line_count > 0:
            document_info["body_starts_at_line"] = frontmatter_line_count + 1

        return DocChangeResult(
            doc_name=doc_name,
            section=section,
            action=action,
            path=doc_path,
            before_hash=before_hash,
            after_hash=after_hash,
            content_written=updated_text,
            diff_preview=diff_preview,
            extra={
                **(extra if "extra" in locals() else {}),
                **frontmatter_extra,
                "document_info": document_info,
            },
            success=True,
            verification_passed=verification_passed,
            file_size_before=file_size_before,
            file_size_after=file_size_after,
        )

    except (DocumentValidationError, DocumentOperationError, DocumentVerificationError) as e:
        duration_ms = (time.time() - start_time) * 1000
        _log_operation(
            level="error",
            operation="apply_doc_change",
            doc_name=doc_name,
            section=section,
            action=action,
            file_path=Path(""),
            duration_ms=duration_ms,
            file_size_before=file_size_before,
            file_size_after=file_size_before,
            success=False,
            error_message=str(e),
            metadata={"error_type": type(e).__name__}
        )

        extra: Dict[str, Any] = {}
        if isinstance(e, DocumentOperationError) and getattr(e, "extra", None):
            extra.update(e.extra)
        if "PATCH_STALE_SOURCE" in str(e):
            extra.setdefault("precondition_failed", "SOURCE_HASH_MISMATCH")

        return DocChangeResult(
            doc_name=doc_name,
            section=section,
            action=action,
            path=Path(""),
            before_hash="",
            after_hash="",
            content_written="",
            diff_preview="",
            extra=extra,
            success=False,
            error_message=str(e),
            verification_passed=False,
            file_size_before=file_size_before,
            file_size_after=file_size_before,
        )
    except Exception as e:
        # Catch any unexpected errors
        duration_ms = (time.time() - start_time) * 1000
        _log_operation(
            level="error",
            operation="apply_doc_change",
            doc_name=doc_name,
            section=section,
            action=action,
            file_path=Path(""),
            duration_ms=duration_ms,
            file_size_before=file_size_before,
            file_size_after=file_size_before,
            success=False,
            error_message=f"Unexpected error: {e}",
            metadata={"error_type": type(e).__name__, "unexpected": True}
        )

        return DocChangeResult(
            doc_name=doc_name,
            section=section,
            action=action,
            path=Path(""),
            before_hash="",
            after_hash="",
            content_written="",
            diff_preview="",
            extra={},
            success=False,
            error_message=f"Unexpected error: {e}",
            verification_passed=False,
            file_size_before=file_size_before,
            file_size_after=file_size_before,
        )


def _resolve_doc_path(project: Dict[str, Any], doc_name: str) -> Path:
    """
    Resolve documentation path with safety assertions.

    Ensures all resolved paths remain within the repository sandbox
    and provides sensible fallbacks when explicit paths are not defined.

    Args:
        project: Project configuration dictionary
        doc_name: Unique document identifier (e.g., "architecture", "phase_plan", "checklist")
    """
    # Validate inputs
    if not doc_name:
        raise ValueError("doc_name cannot be empty")

    project_name = project.get("name")
    if not project_name:
        raise ValueError("project must have a name")

    project_root = Path(project.get("root", ""))
    if not project_root.exists():
        raise ValueError(f"Project root does not exist: {project_root}")

    # Try explicit paths first
    docs = project.get("docs") or {}
    target = docs.get(doc_name)
    if not target and doc_name == "progress_log":
        target = project.get("progress_log")

    if target:
        resolved_path = Path(target).resolve()
        # CRITICAL: Ensure path is within project sandbox
        try:
            resolved_path.relative_to(project_root)
        except ValueError as e:
            raise SecurityError(f"Document path {resolved_path} is outside project root {project_root}") from e

        doc_logger.debug(f"Resolved doc path for {doc_name} using explicit target: {resolved_path}")
        return resolved_path

    # Fallback to conventional structure
    docs_dir = docs.get("architecture")
    if docs_dir:
        docs_dir = Path(docs_dir).parent
    else:
        docs_dir_str = project.get("docs_dir", "")
        if docs_dir_str:
            docs_dir = Path(docs_dir_str)
        else:
            slug = slugify_project_name(project_name)
            scribe_docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / slug
            legacy_docs_dir = project_root / "docs" / "dev_plans" / slug
            if scribe_docs_dir.exists():
                docs_dir = scribe_docs_dir
            elif legacy_docs_dir.exists():
                docs_dir = legacy_docs_dir
            else:
                docs_dir = scribe_docs_dir

    filename = {
        "architecture": "ARCHITECTURE_GUIDE.md",
        "phase_plan": "PHASE_PLAN.md",
        "checklist": "CHECKLIST.md",
        "progress_log": "PROGRESS_LOG.md",
        "doc_log": "DOC_LOG.md",
        "security_log": "SECURITY_LOG.md",
        "bug_log": "BUG_LOG.md",
    }.get(doc_name)
    if filename is None:
        # Accept extension-qualified doc references without creating ".md.md" paths.
        filename = doc_name if str(doc_name).lower().endswith(".md") else f"{doc_name}.md"

    resolved_path = (docs_dir / filename).resolve()

    # If file not found in main folder, check common subdirectories
    if not resolved_path.exists():
        subfolders_to_check = ["research", "architecture", "bugs"]
        for subfolder in subfolders_to_check:
            alt_path = (docs_dir / subfolder / filename).resolve()
            if alt_path.exists():
                resolved_path = alt_path
                break

    # CRITICAL: Ensure fallback path is within project sandbox
    try:
        resolved_path.relative_to(project_root)
    except ValueError as e:
        raise SecurityError(f"Fallback document path {resolved_path} is outside project root {project_root}") from e

    doc_logger.debug(f"Resolved doc path for {doc_name} using fallback: {resolved_path}")
    return resolved_path


def _resolve_create_doc_path(
    project: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    doc_name: str,
) -> Path:
    """
    Resolve path for creating a new document.

    Args:
        project: Project configuration dictionary
        metadata: Optional metadata dict with doc_name, register_as, or target_dir overrides
        doc_name: Unique document identifier (fallback if not in metadata)
    """
    project_root = Path(project.get("root", ""))
    if not project_root.exists():
        raise ValueError(f"Project root does not exist: {project_root}")

    metadata = metadata or {}
    resolved_name = doc_name or metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type")
    resolved_name = str(resolved_name or "").strip()
    if not resolved_name:
        raise DocumentOperationError("CREATE_DOC_MISSING_NAME: doc_name or register_as is required")

    safe_name = slugify_filename(resolved_name)

    docs_dir = project.get("docs_dir")
    if docs_dir:
        docs_dir = Path(docs_dir)
    else:
        docs_dir = _resolve_doc_path(project, "architecture").parent

    target_dir = metadata.get("target_dir")
    if target_dir:
        target_path = Path(target_dir)
        if not target_path.is_absolute():
            target_path = project_root / target_path
        try:
            target_path.resolve().relative_to(project_root.resolve())
        except ValueError as exc:
            raise SecurityError(
                f"Target directory {target_path} is outside project root {project_root}"
            ) from exc
        docs_dir = target_path

    resolved_path = (docs_dir / f"{safe_name}.md").resolve()
    try:
        resolved_path.relative_to(project_root)
    except ValueError as exc:
        raise SecurityError(
            f"Document path {resolved_path} is outside project root {project_root}"
        ) from exc
    return resolved_path


class SecurityError(RuntimeError):
    """Security violation when document paths escape project sandbox."""


async def _render_content(
    project: Dict[str, Any],
    content: Optional[str],
    template_name: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> str:
    """Render content using Jinja2 template engine with fallback to direct content."""
    # Handle case where metadata comes as JSON string from MCP framework
    if metadata is None:
        metadata = {}
    elif isinstance(metadata, str):
        try:
            import json
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    # Check if template_name is actually a fallback content string from parameter validator
    # Common fallback strings that should be treated as content, not template names
    fallback_strings = {"No message provided", "Invalid message format", "Empty message"}

    if template_name and template_name in fallback_strings:
        # Treat fallback strings as content, not template names
        if content is None:
            content = template_name
        template_name = None

    if template_name:
        try:
            # Import template engine dynamically to avoid circular imports
            from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

            # Initialize template engine
            engine = Jinja2TemplateEngine(
                project_root=Path(project.get("root", "")),
                project_name=project.get("name", ""),
                security_mode="sandbox"
            )

            # Add timestamp to metadata
            enhanced_metadata = metadata.copy() if metadata else {}
            enhanced_metadata.update({
                "timestamp": utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            })

            # Render template
            rendered = engine.render_template(
                template_name=f"{template_name}.md",
                metadata=enhanced_metadata
            )

            doc_logger.debug(f"Successfully rendered template '{template_name}' using Jinja2 engine")
            return rendered

        except TemplateEngineError as e:
            doc_logger.error(f"Template engine error for '{template_name}': {e}")
            raise DocumentOperationError(f"Failed to render template '{template_name}': {e}")
        except Exception as e:
            doc_logger.error(f"Unexpected error rendering template '{template_name}': {e}")
            raise DocumentOperationError(f"Unexpected template error: {e}")

    if isinstance(content, str) and content:
        # Preserve author-provided formatting, but allow inline Jinja rendering when present.
        normalized = content.replace("\r\n", "\n")
        if "{{" in normalized or "{%" in normalized or "{#" in normalized:
            try:
                from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

                engine = Jinja2TemplateEngine(
                    project_root=Path(project.get("root", "")),
                    project_name=project.get("name", ""),
                    security_mode="sandbox",
                )
                enhanced_metadata = metadata.copy() if metadata else {}
                enhanced_metadata.setdefault(
                    "timestamp", utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                )
                rendered_inline = engine.render_string(
                    normalized,
                    metadata=enhanced_metadata,
                    strict=False,
                    fallback=True,
                )
                return rendered_inline
            except Exception as e:  # pragma: no cover - defensive
                doc_logger.error(f"Inline Jinja rendering failed, returning raw content: {e}")
                return normalized

        return normalized

    raise ValueError("Either content or template must be provided.")


async def _load_fragment(name: str) -> str:
    fragment = (FRAGMENT_DIR / f"{name}.md").resolve()
    if not fragment.exists():
        raise FileNotFoundError(f"Template fragment '{name}' not found under {FRAGMENT_DIR}")
    return await asyncio.to_thread(fragment.read_text, encoding="utf-8")


def _replace_section(text: str, section: Optional[str], content: str, *, allow_append: bool = False) -> str:
    marker = SECTION_MARKER.format(section=section)

    # Strip redundant header+marker from content if present at the start.
    # This handles the common case where caller includes full section structure
    # (header + marker + body) instead of just the body content.
    content_stripped = content.lstrip()
    marker_pos = content_stripped.find(marker)
    # Only process if marker appears near the beginning (within ~500 chars for a header)
    if 0 <= marker_pos <= 500:
        prefix_before_marker = content_stripped[:marker_pos]
        prefix_clean = prefix_before_marker.strip()
        # Check if prefix is empty or consists only of markdown headers and blank lines
        if not prefix_clean or all(
            re.match(r'^#+\s', line) or not line.strip()
            for line in prefix_clean.splitlines()
        ):
            # Strip everything up to and including the marker
            after_marker = content_stripped[marker_pos + len(marker):]
            content = after_marker.lstrip('\n\r')

    idx = text.find(marker)
    if idx == -1:
        if not allow_append:
            raise DocumentOperationError(
                f"SECTION_ANCHOR_MISSING: '{section}' not found (set metadata.allow_append=true to append)"
            )
        doc_logger.warning(
            "Section anchor missing; auto-appending '%s' to document.",
            section,
            extra={"section": section, "action": "replace_section"},
        )
        prefix = text.rstrip()
        if prefix:
            prefix = prefix + "\n\n"
        return prefix + marker + "\n" + content.strip() + "\n"
    if text.find(marker, idx + 1) != -1:
        raise DocumentOperationError(
            f"SECTION_ANCHOR_AMBIGUOUS: '{section}' appears multiple times; resolve duplicates first"
        )
    start = idx + len(marker)
    # Skip newline right after marker
    if start < len(text) and text[start] == "\r":
        start += 1
    if start < len(text) and text[start] == "\n":
        start += 1
    next_marker = text.find("<!-- ID:", start)
    if next_marker == -1:
        next_marker = len(text)
    new_block = marker + "\n" + content.strip() + "\n"
    replacement = text[:idx] + new_block + text[next_marker:]
    return replacement


def _replace_text_literal(
    text: str,
    find_text: str,
    replace_text: str,
    *,
    replace_all: bool,
) -> tuple[str, int]:
    # Exact match — fast path
    if find_text in text:
        if replace_all:
            return text.replace(find_text, replace_text), text.count(find_text)
        return text.replace(find_text, replace_text, 1), 1

    # Fallback: normalize \r\n → \n and retry (handles cross-platform newline mismatch)
    norm_text = text.replace("\r\n", "\n")
    norm_find = find_text.replace("\r\n", "\n")
    if norm_find in norm_text:
        if replace_all:
            return norm_text.replace(norm_find, replace_text), norm_text.count(norm_find)
        return norm_text.replace(norm_find, replace_text, 1), 1

    # No match after normalization
    return text, 0


def _replace_text_regex(
    text: str,
    pattern: str,
    replace_text: str,
    *,
    replace_all: bool,
) -> tuple[str, int]:
    compiled = re.compile(pattern)
    count = 0 if replace_all else 1
    updated, hits = compiled.subn(replace_text, text, count=count)
    return updated, hits


def _replace_text_prefix(
    text: str,
    find_text: str,
    replace_text: str,
    *,
    replace_all: bool,
) -> tuple[str, int]:
    hits = 0
    updated_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        newline = ""
        body = line
        if line.endswith("\r\n"):
            body = line[:-2]
            newline = "\r\n"
        elif line.endswith("\n"):
            body = line[:-1]
            newline = "\n"

        leading_ws_len = len(body) - len(body.lstrip())
        leading_ws = body[:leading_ws_len]
        content = body[leading_ws_len:]

        if content.startswith(find_text) and (replace_all or hits == 0):
            content = replace_text + content[len(find_text):]
            hits += 1

        updated_lines.append(f"{leading_ws}{content}{newline}")

    return "".join(updated_lines), hits


def _replace_text_with_scope(
    text: str,
    *,
    find_text: str,
    replace_text: str,
    match_mode: str,
    replace_all: bool,
    scope: Optional[str],
    allow_no_match: bool,
) -> tuple[str, int]:
    target_text = text
    prefix = ""
    suffix = ""
    marker = None

    if scope:
        normalized = scope.strip()
        if normalized.startswith("section:"):
            section_id = normalized.split(":", 1)[1].strip()
            if not section_id:
                raise DocumentOperationError("REPLACE_TEXT_SCOPE_INVALID: section id missing")
            marker = SECTION_MARKER.format(section=section_id)
            idx = text.find(marker)
            if idx == -1:
                raise DocumentOperationError(
                    f"SECTION_ANCHOR_MISSING: '{section_id}' not found in replace_text scope"
                )
            if text.find(marker, idx + 1) != -1:
                raise DocumentOperationError(
                    f"SECTION_ANCHOR_AMBIGUOUS: '{section_id}' appears multiple times"
                )

            line_start = text.rfind("\n", 0, idx) + 1
            line_end = text.find("\n", idx)
            if line_end == -1:
                line_end = len(text)
            marker_is_block = text[line_start:line_end].strip() == marker

            if marker_is_block:
                start = idx + len(marker)
                if start < len(text) and text[start] == "\r":
                    start += 1
                if start < len(text) and text[start] == "\n":
                    start += 1
                next_marker_match = re.search(
                    r"(?m)^[ \t]*<!--\s*ID:\s*[^>]+-->\s*$",
                    text[start:],
                )
                if next_marker_match:
                    next_marker = start + next_marker_match.start()
                else:
                    next_marker = len(text)
                prefix = text[:start]
                target_text = text[start:next_marker]
                suffix = text[next_marker:]
            else:
                target_end = line_end + 1 if line_end < len(text) else len(text)
                prefix = text[:line_start]
                target_text = text[line_start:target_end]
                suffix = text[target_end:]
        elif normalized.startswith("line:"):
            line_number_raw = normalized.split(":", 1)[1].strip()
            if not line_number_raw:
                raise DocumentOperationError("REPLACE_TEXT_SCOPE_INVALID: line number missing")
            try:
                line_number = int(line_number_raw)
            except ValueError as exc:
                raise DocumentOperationError(
                    "REPLACE_TEXT_SCOPE_INVALID: line number must be an integer"
                ) from exc
            if line_number < 1:
                raise DocumentOperationError(
                    "REPLACE_TEXT_SCOPE_INVALID: line number must be >= 1"
                )

            scoped_lines = text.splitlines(keepends=True)
            if line_number > len(scoped_lines):
                raise DocumentOperationError(
                    f"REPLACE_TEXT_SCOPE_LINE_MISSING: line {line_number} not found"
                )

            prefix = "".join(scoped_lines[: line_number - 1])
            target_text = scoped_lines[line_number - 1]
            suffix = "".join(scoped_lines[line_number:])

    if match_mode == "regex":
        updated, hits = _replace_text_regex(
            target_text,
            find_text,
            replace_text,
            replace_all=replace_all,
        )
    elif match_mode == "prefix":
        updated, hits = _replace_text_prefix(
            target_text,
            find_text,
            replace_text,
            replace_all=replace_all,
        )
    else:
        updated, hits = _replace_text_literal(
            target_text,
            find_text,
            replace_text,
            replace_all=replace_all,
        )

    if hits == 0 and not allow_no_match:
        raise DocumentOperationError("REPLACE_TEXT_NO_MATCH: no matches found")

    return prefix + updated + suffix, hits


def _append_block(text: str, content: str, section: Optional[str] = None, position: str = "after") -> str:
    normalized = content.strip()
    if not normalized:
        return text

    if not section:
        if not text.endswith("\n"):
            text += "\n"
        if normalized:
            return text + normalized + "\n"
        return text

    marker = SECTION_MARKER.format(section=section)
    idx = text.find(marker)
    if idx == -1:
        doc_logger.warning(
            "Append anchor '%s' missing; creating new block.",
            section,
            extra={"section": section, "action": "append"},
        )
        prefix = text.rstrip()
        if prefix:
            prefix = prefix + "\n\n"
        return prefix + marker + "\n" + normalized + "\n"

    after_marker = idx + len(marker)
    while after_marker < len(text) and text[after_marker] in "\r\n":
        after_marker += 1
    next_marker = text.find("<!-- ID:", after_marker)
    if next_marker == -1:
        next_marker = len(text)

    position = position.lower()
    if position == "before":
        insertion_point = idx
    elif position in {"inside", "within", "start"}:
        insertion_point = after_marker
    else:
        insertion_point = next_marker

    prefix = text[:insertion_point]
    suffix = text[insertion_point:]

    insertion = normalized
    if insertion and not insertion.endswith("\n"):
        insertion += "\n"

    if prefix and not prefix.endswith("\n"):
        insertion = "\n" + insertion
    if suffix and not suffix.startswith("\n"):
        insertion = insertion + "\n"

    return prefix + insertion + suffix


def _line_matches(expected: str, actual: str) -> bool:
    if actual == expected:
        return True
    if expected.endswith("\n") and actual == expected[:-1]:
        return True
    if actual.endswith("\n") and expected == actual[:-1]:
        return True
    return False


def _format_hunk_header(old_start: int, old_count: int, new_start: int, new_count: int) -> str:
    return f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"


def _parse_patch_hunks(patch_text: str) -> tuple[list[str], list[Dict[str, Any]]]:
    """Parse unified diff into header lines and hunk definitions."""
    lines = patch_text.splitlines(keepends=False)
    header_lines: list[str] = []
    hunks: list[Dict[str, Any]] = []
    i = 0
    while i < len(lines) and (lines[i].startswith("--- ") or lines[i].startswith("+++ ")):
        header_lines.append(lines[i])
        i += 1

    while i < len(lines):
        line = lines[i]
        match = _HUNK_HEADER.match(line)
        if not match:
            if line.strip() == "":
                i += 1
                continue
            raise DocumentOperationError(f"PATCH_INVALID_FORMAT: expected hunk header: {line!r}")

        hunk_lines: list[str] = []
        header = line
        i += 1
        while i < len(lines) and not lines[i].startswith("@@ "):
            hunk_lines.append(lines[i])
            i += 1

        hunks.append(
            {
                "header": header,
                "lines": hunk_lines,
            }
        )
    return header_lines, hunks


def _collect_hunk_original_lines(hunk_lines: list[str]) -> list[str]:
    """Return original file lines implied by a hunk (context + deletions)."""
    original_lines: list[str] = []
    for line in hunk_lines:
        if not line or line.startswith("\\"):
            continue
        prefix = line[0]
        if prefix in {" ", "-"}:
            original_lines.append(f"{line[1:]}\n")
    return original_lines


def _find_sequence_indices(haystack: list[str], needle: list[str]) -> list[int]:
    if not needle:
        return []
    matches: list[int] = []
    limit = len(haystack) - len(needle)
    for idx in range(limit + 1):
        if haystack[idx: idx + len(needle)] == needle:
            matches.append(idx)
    return matches


def _find_alignment_with_one_line_gaps(
    original_lines: list[str], target_lines: list[str]
) -> Optional[list[int]]:
    """Find a unique alignment allowing a single skipped line between matches."""
    if not target_lines:
        return None
    alignments: list[list[int]] = []

    def dfs(target_index: int, next_start: int, positions: list[int]) -> None:
        if len(alignments) > 1:
            return
        if target_index >= len(target_lines):
            alignments.append(positions)
            return
        for offset in (0, 1):
            candidate_index = next_start + offset
            if candidate_index >= len(original_lines):
                continue
            if _line_matches(target_lines[target_index], original_lines[candidate_index]):
                dfs(target_index + 1, candidate_index + 1, positions + [candidate_index])
        return

    for index, line in enumerate(original_lines):
        if _line_matches(target_lines[0], line):
            dfs(1, index + 1, [index])
            if len(alignments) > 1:
                break

    if len(alignments) == 1:
        return alignments[0]
    return None


def _expand_hunk_with_one_line_gaps(
    original_lines: list[str], hunk_lines: list[str]
) -> Optional[tuple[list[str], Dict[str, Any]]]:
    """Insert missing single-gap context lines into hunk when alignment is unique."""
    effective_line_indices = [
        idx for idx, line in enumerate(hunk_lines) if line and line[0] in {" ", "-"}
    ]
    target_lines = [
        f"{hunk_lines[idx][1:]}\n" for idx in effective_line_indices
    ]
    if not target_lines:
        return None

    alignment = _find_alignment_with_one_line_gaps(original_lines, target_lines)
    if alignment is None:
        return None

    mapping = {hunk_idx: position for hunk_idx, position in zip(effective_line_indices, alignment)}
    expanded: list[str] = []
    gap_lines_added: list[int] = []

    for hunk_index, line in enumerate(hunk_lines):
        expanded.append(line)
        if hunk_index not in mapping:
            continue
        current_pos = mapping[hunk_index]
        next_effective_indices = [idx for idx in effective_line_indices if idx > hunk_index]
        if not next_effective_indices:
            continue
        next_hunk_index = next_effective_indices[0]
        next_pos = mapping.get(next_hunk_index)
        if next_pos is None:
            continue
        gap = next_pos - current_pos
        if gap == 2:
            missing_line = original_lines[current_pos + 1].rstrip("\n")
            missing_line = missing_line.rstrip("\r")
            expanded.append(f" {missing_line}")
            gap_lines_added.append(current_pos + 2)
        elif gap > 2:
            return None

    if not gap_lines_added:
        return None

    return expanded, {"gap_lines_added": gap_lines_added}


def _rebase_patch_to_current_context(
    original_text: str, patch_text: str
) -> tuple[str, Dict[str, Any]]:
    """Rebase patch hunk headers to current file context using exact matches."""
    header_lines, hunks = _parse_patch_hunks(patch_text)
    original_lines = original_text.splitlines(keepends=True)
    rebased_lines: list[str] = []
    if header_lines:
        rebased_lines.extend(header_lines)
    rebase_info: Dict[str, Any] = {"hunks": []}

    for hunk in hunks:
        hunk_lines = hunk["lines"]
        original_hunk_lines = _collect_hunk_original_lines(hunk_lines)
        matches = _find_sequence_indices(original_lines, original_hunk_lines)
        context_expanded = False
        expansion_info: Dict[str, Any] = {}
        if len(matches) != 1:
            expanded = _expand_hunk_with_one_line_gaps(original_lines, hunk_lines)
            if expanded:
                hunk_lines, expansion_info = expanded
                context_expanded = True
                original_hunk_lines = _collect_hunk_original_lines(hunk_lines)
                matches = _find_sequence_indices(original_lines, original_hunk_lines)

        if len(matches) != 1:
            reason = "ambiguous" if matches else "missing"
            extra = {
                "rebase_reason": reason,
                "match_candidates": [m + 1 for m in matches],
            }
            if context_expanded:
                extra["context_expanded"] = True
                extra.update(expansion_info)
            raise DocumentOperationError(
                f"PATCH_CONTEXT_REBASE_FAILED: {reason} context match",
                extra=extra,
            )
        start_index = matches[0]
        old_count = sum(1 for line in hunk_lines if line and line[0] in {" ", "-"})
        new_count = sum(1 for line in hunk_lines if line and line[0] in {" ", "+"})
        old_start = start_index + 1
        new_start = old_start
        rebased_lines.append(_format_hunk_header(old_start, old_count, new_start, new_count))
        rebased_lines.extend(hunk_lines)
        rebase_info["hunks"].append(
            {
                "start_line": old_start,
                "end_line": old_start + max(old_count - 1, 0),
                "match_start_line": old_start,
                "match_end_line": old_start + max(old_count - 1, 0),
                "context_expanded": context_expanded,
                **expansion_info,
            }
        )

    return ("\n".join(rebased_lines) + "\n", rebase_info)


def _extract_expected_line(error_message: str) -> Optional[str]:
    if "expected=" not in error_message:
        return None
    prefix = "expected="
    try:
        expected_part = error_message.split(prefix, 1)[1]
        expected_repr = expected_part.split(" got=", 1)[0]
        return ast.literal_eval(expected_repr)
    except (ValueError, SyntaxError):
        return None


def _build_patch_failure_diagnostics(
    original_text: str,
    patch_text: str,
    error_message: str,
) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {}
    if error_message.startswith("PATCH_"):
        diagnostics["error_code"] = error_message.split(":", 1)[0]
        if diagnostics["error_code"] == "PATCH_RANGE_ERROR":
            diagnostics["failure_stage"] = "range_validation"
        else:
            diagnostics["failure_stage"] = "apply_patch"
    expected_line = _extract_expected_line(error_message)
    if expected_line:
        diagnostics["expected_line"] = expected_line
        line_numbers: list[int] = []
        for idx, line in enumerate(original_text.splitlines(keepends=True), start=1):
            if _line_matches(expected_line, line):
                line_numbers.append(idx)
                if len(line_numbers) >= 5:
                    break
        if line_numbers:
            diagnostics["matching_line_numbers"] = line_numbers

    try:
        _, hunks = _parse_patch_hunks(patch_text)
        original_lines = original_text.splitlines(keepends=True)
        ranges: list[Dict[str, Any]] = []
        for hunk in hunks:
            original_hunk_lines = _collect_hunk_original_lines(hunk["lines"])
            matches = _find_sequence_indices(original_lines, original_hunk_lines)
            if len(matches) == 1:
                start = matches[0] + 1
                end = start + max(len(original_hunk_lines) - 1, 0)
                ranges.append({"start_line": start, "end_line": end})
        if ranges:
            diagnostics["current_line_ranges"] = ranges
    except DocumentOperationError:
        pass

    diagnostics.setdefault(
        "hint",
        "PATCH_CONTEXT_MISMATCH: file changed or hunk header out of date; re-extract context from current file.",
    )
    return diagnostics


def _compute_patch_ranges(patch_text: str) -> list[Dict[str, int]]:
    ranges: list[Dict[str, int]] = []
    _, hunks = _parse_patch_hunks(patch_text)
    for hunk in hunks:
        header = hunk["header"]
        match = _HUNK_HEADER.match(header)
        if not match:
            continue
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        end_line = old_start + max(old_count - 1, 0)
        ranges.append({"start_line": old_start, "end_line": end_line})
    return ranges


def _build_bounded_preview(
    original_text: str,
    updated_text: str,
    ranges: list[Dict[str, int]],
    context: int = 3,
) -> Dict[str, Any]:
    if not ranges:
        return {}
    first_range = ranges[0]
    start_line = max(1, first_range["start_line"] - context)
    end_line = first_range["end_line"] + context
    original_lines = original_text.splitlines()
    updated_lines = updated_text.splitlines()
    bounded_end = min(len(updated_lines), end_line)
    bounded_start = min(start_line, bounded_end if bounded_end else start_line)
    return {
        "start_line": bounded_start,
        "end_line": bounded_end,
        "before": "\n".join(original_lines[bounded_start - 1: bounded_end]),
        "after": "\n".join(updated_lines[bounded_start - 1: bounded_end]),
    }


def _build_bounded_previews(
    original_text: str,
    updated_text: str,
    ranges: list[Dict[str, int]],
    context: int = 3,
) -> list[Dict[str, Any]]:
    previews: list[Dict[str, Any]] = []
    for entry in ranges:
        previews.append(
            _build_bounded_preview(
                original_text,
                updated_text,
                [entry],
                context=context,
            )
        )
    return previews


def _adjust_patch_line_numbers(patch_text: str, offset: int) -> str:
    """Adjust line numbers in a unified diff patch by subtracting an offset.

    This handles the case where users create patches with line numbers relative
    to the raw file (including frontmatter) but patches are applied to body only.

    Args:
        patch_text: The unified diff patch string
        offset: Number of lines to subtract from line numbers (e.g., frontmatter line count)

    Returns:
        Adjusted patch with corrected line numbers
    """
    if offset <= 0:
        return patch_text

    lines = patch_text.splitlines(keepends=False)
    adjusted_lines = []

    for line in lines:
        match = _HUNK_HEADER.match(line)
        if match:
            old_start = max(1, int(match.group(1)) - offset)
            old_count = int(match.group(2)) if match.group(2) else 1
            new_start = max(1, int(match.group(3)) - offset)
            new_count = int(match.group(4)) if match.group(4) else 1
            adjusted_lines.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@")
        else:
            adjusted_lines.append(line)

    return "\n".join(adjusted_lines)


def _extract_hunk_context(hunk_lines: list[str]) -> list[str]:
    """Extract the context/delete lines from a hunk (lines that must match in original).

    Returns list of line contents (without prefix) that should exist in original.
    """
    context = []
    for line in hunk_lines:
        if not line:
            continue
        if line.startswith("\\"):  # "\ No newline at end of file"
            continue
        prefix = line[0] if line else ""
        if prefix in (" ", "-"):
            context.append(line[1:])  # Strip prefix
    return context


def _find_context_position(original_lines: list[str], context_lines: list[str], start_hint: int = 0) -> int | None:
    """Find where context_lines match in original_lines.

    Args:
        original_lines: Lines of the original document (with newlines)
        context_lines: Context lines to find (without newlines)
        start_hint: Suggested starting position (from hunk header)

    Returns:
        0-based index where context starts, or None if not found
    """
    if not context_lines:
        return start_hint  # No context to match, trust the hint

    # Normalize original lines for comparison
    orig_normalized = [line.rstrip("\n\r") for line in original_lines]

    # First, check at the hinted position
    if start_hint >= 0 and start_hint + len(context_lines) <= len(orig_normalized):
        if all(
            orig_normalized[start_hint + i] == context_lines[i]
            for i in range(len(context_lines))
        ):
            return start_hint

    # Search entire document for context match
    for pos in range(len(orig_normalized) - len(context_lines) + 1):
        if pos == start_hint:
            continue  # Already checked
        if all(
            orig_normalized[pos + i] == context_lines[i]
            for i in range(len(context_lines))
        ):
            return pos

    return None


def _apply_unified_patch_smart(
    original_text: str,
    patch_text: str,
    frontmatter_lines: int = 0
) -> tuple[str, int, dict]:
    """Apply unified diff with context-aware matching.

    Instead of blindly trusting line numbers, this function:
    1. Extracts context lines from each hunk
    2. Finds where context actually matches in the document
    3. Applies patch at the matched location
    4. Reports adjustments made

    Args:
        original_text: The document body to patch
        patch_text: Unified diff patch
        frontmatter_lines: Number of frontmatter lines (for smart adjustment hints)

    Returns:
        Tuple of (patched_text, hunks_applied, extra_info)
    """
    if not patch_text or not patch_text.strip():
        raise DocumentOperationError("apply_patch requires non-empty patch text")

    original_lines = original_text.splitlines(keepends=True)
    patch_lines = patch_text.splitlines(keepends=False)

    # Skip --- and +++ headers
    i = 0
    while i < len(patch_lines) and (patch_lines[i].startswith("--- ") or patch_lines[i].startswith("+++ ")):
        i += 1

    output: list[str] = []
    original_index = 0
    hunks_applied = 0
    adjustments = []

    while i < len(patch_lines):
        header = patch_lines[i]
        match = _HUNK_HEADER.match(header)
        if not match:
            if header.strip() == "":
                i += 1
                continue
            raise DocumentOperationError(f"PATCH_INVALID_FORMAT: expected hunk header: {header!r}")

        hunk_old_start = int(match.group(1))
        hunk_old_count = int(match.group(2)) if match.group(2) else 1
        i += 1

        # Collect all lines in this hunk
        hunk_lines = []
        while i < len(patch_lines) and not patch_lines[i].startswith("@@ "):
            hunk_lines.append(patch_lines[i])
            i += 1

        # Extract context lines for matching
        context_lines = _extract_hunk_context(hunk_lines)

        # Try to find where context actually matches
        expected_pos = hunk_old_start - 1  # 0-based

        # First try: exact position from hunk header
        actual_pos = _find_context_position(original_lines, context_lines, expected_pos)

        # Second try: if frontmatter offset might be the issue
        if actual_pos is None and frontmatter_lines > 0:
            adjusted_pos = expected_pos - frontmatter_lines
            if adjusted_pos >= 0:
                actual_pos = _find_context_position(original_lines, context_lines, adjusted_pos)
                if actual_pos is not None:
                    adjustments.append({
                        "hunk": hunks_applied + 1,
                        "expected_line": hunk_old_start,
                        "actual_line": actual_pos + 1,
                        "adjustment": "frontmatter_offset",
                        "offset": frontmatter_lines,
                    })

        # Third try: search entire document
        if actual_pos is None:
            actual_pos = _find_context_position(original_lines, context_lines, -1)  # Search all
            if actual_pos is not None and actual_pos != expected_pos:
                adjustments.append({
                    "hunk": hunks_applied + 1,
                    "expected_line": hunk_old_start,
                    "actual_line": actual_pos + 1,
                    "adjustment": "context_search",
                    "drift": actual_pos - expected_pos,
                })

        if actual_pos is None:
            # Context not found anywhere
            context_preview = context_lines[:3] if context_lines else ["<no context>"]
            delete_lines = [line[1:] for line in hunk_lines if line.startswith("-")]
            if delete_lines:
                raise DocumentOperationError(
                    f"PATCH_DELETE_MISMATCH: hunk {hunks_applied + 1} delete lines not found in document "
                    f"context (PATCH_CONTEXT_NOT_FOUND). Expected at line {hunk_old_start}. "
                    f"Delete starts with: {delete_lines[:3]}"
                )
            raise DocumentOperationError(
                f"PATCH_CONTEXT_NOT_FOUND: hunk {hunks_applied + 1} context not found in document. "
                f"Expected at line {hunk_old_start}, searched entire file. "
                f"Context starts with: {context_preview}"
            )

        # Copy unchanged content up to the patch position
        if actual_pos > original_index:
            output.extend(original_lines[original_index:actual_pos])
        original_index = actual_pos

        # Apply the hunk
        for hunk_line in hunk_lines:
            if not hunk_line:
                continue
            if hunk_line.startswith("\\"):
                continue

            prefix = hunk_line[0]
            text = hunk_line[1:]
            patched_line = f"{text}\n"

            if prefix == " ":
                # Context line - verify and copy
                if original_index >= len(original_lines):
                    raise DocumentOperationError(
                        f"PATCH_CONTEXT_MISMATCH: unexpected EOF at context line"
                    )
                if not _line_matches(patched_line, original_lines[original_index]):
                    raise DocumentOperationError(
                        f"PATCH_CONTEXT_MISMATCH: expected={patched_line!r} got={original_lines[original_index]!r}"
                    )
                output.append(original_lines[original_index])
                original_index += 1
            elif prefix == "-":
                # Delete line - verify and skip
                if original_index >= len(original_lines):
                    raise DocumentOperationError(
                        f"PATCH_DELETE_MISMATCH: unexpected EOF at delete line"
                    )
                if not _line_matches(patched_line, original_lines[original_index]):
                    raise DocumentOperationError(
                        f"PATCH_DELETE_MISMATCH: expected={patched_line!r} got={original_lines[original_index]!r}"
                    )
                original_index += 1  # Skip (delete) this line
            elif prefix == "+":
                # Add line
                output.append(patched_line)
            else:
                raise DocumentOperationError(f"PATCH_INVALID_FORMAT: invalid line prefix {prefix!r}")

        hunks_applied += 1

    # Copy remaining content
    output.extend(original_lines[original_index:])

    extra_info = {}
    if adjustments:
        extra_info["context_adjustments"] = adjustments
        extra_info["context_matching_used"] = True

    return ("".join(output), hunks_applied, extra_info)


def _apply_unified_patch(original_text: str, patch_text: str) -> tuple[str, int]:
    """Apply a unified diff patch to original_text with strict context matching."""
    if not patch_text or not patch_text.strip():
        raise DocumentOperationError("apply_patch requires non-empty patch text")

    original_lines = original_text.splitlines(keepends=True)
    lines = patch_text.splitlines(keepends=False)

    i = 0
    while i < len(lines) and (lines[i].startswith("--- ") or lines[i].startswith("+++ ")):
        i += 1

    output: list[str] = []
    original_index = 0
    hunks_applied = 0

    while i < len(lines):
        header = lines[i]
        match = _HUNK_HEADER.match(header)
        if not match:
            if header.strip() == "":
                i += 1
                continue
            raise DocumentOperationError(f"PATCH_INVALID_FORMAT: expected hunk header: {header!r}")

        old_start = int(match.group(1))
        target_index = old_start - 1

        if target_index < original_index or target_index > len(original_lines):
            raise DocumentOperationError("PATCH_RANGE_ERROR: hunk target out of range for original content")

        output.extend(original_lines[original_index:target_index])
        original_index = target_index
        i += 1

        while i < len(lines) and not lines[i].startswith("@@ "):
            line = lines[i]
            if line.startswith("\\"):
                i += 1
                continue
            if not line:
                raise DocumentOperationError("PATCH_INVALID_FORMAT: empty line without prefix")

            prefix = line[0]
            text = line[1:]
            patched_line = f"{text}\n"

            if prefix == " ":
                if original_index >= len(original_lines) or not _line_matches(
                    patched_line, original_lines[original_index]
                ):
                    got = original_lines[original_index] if original_index < len(original_lines) else "<EOF>"
                    raise DocumentOperationError(
                        f"PATCH_CONTEXT_MISMATCH: expected={patched_line!r} got={got!r}"
                    )
                output.append(original_lines[original_index])
                original_index += 1
            elif prefix == "-":
                if original_index >= len(original_lines) or not _line_matches(
                    patched_line, original_lines[original_index]
                ):
                    got = original_lines[original_index] if original_index < len(original_lines) else "<EOF>"
                    raise DocumentOperationError(
                        f"PATCH_DELETE_MISMATCH: expected={patched_line!r} got={got!r}"
                    )
                original_index += 1
            elif prefix == "+":
                output.append(patched_line)
            else:
                raise DocumentOperationError(f"PATCH_INVALID_FORMAT: invalid line prefix {prefix!r}")

            i += 1

        hunks_applied += 1

    output.extend(original_lines[original_index:])
    return ("".join(output), hunks_applied)


def _is_patch_context_error(error_message: str) -> bool:
    return any(
        code in error_message
        for code in (
            "PATCH_CONTEXT_MISMATCH",
            "PATCH_CONTEXT_NOT_FOUND",
            "PATCH_DELETE_MISMATCH",
            "PATCH_RANGE_ERROR",
        )
    )


def _replace_range_text(
    original_text: str,
    start_line: Optional[int],
    end_line: Optional[int],
    replacement: str,
) -> str:
    """Replace inclusive line range [start_line, end_line] (1-based).

    Safety rule: when line numbers are provided, always honor the explicit range.
    Header-based section replacement is only attempted when range endpoints are
    omitted (legacy fallback behavior).
    """
    if start_line is None or end_line is None:
        header_replacement = _replace_section_by_header(
            original_text,
            replacement,
            allow_missing_header_fallback=False,
        )
        if header_replacement is not None:
            return header_replacement
        raise DocumentOperationError("replace_range requires start_line and end_line")

    if start_line < 1 or end_line < start_line:
        raise DocumentOperationError(f"Invalid range: start_line={start_line} end_line={end_line}")

    lines = original_text.splitlines(keepends=True)
    if start_line > len(lines) + 1:
        raise DocumentOperationError("start_line out of range")
    if end_line > len(lines):
        raise DocumentOperationError("end_line out of range")

    repl = replacement.replace("\r\n", "\n")
    if repl and not repl.endswith("\n"):
        repl += "\n"
    new_lines = lines[: start_line - 1] + ([repl] if repl else []) + lines[end_line:]
    result = "".join(new_lines)
    if not result.strip():
        raise DocumentOperationError(
            f"REPLACE_RANGE_WOULD_EMPTY_DOC: operation would erase all document content "
            f"(range {start_line}-{end_line} covers {end_line - start_line + 1} of {len(lines)} lines)"
        )
    return result


def _replace_section_by_header(
    original_text: str,
    replacement: str,
    *,
    allow_missing_header_fallback: bool = False,
) -> Optional[str]:
    """Replace a Markdown header section when the replacement starts with a header.

    Section replacement is attempted before falling back to numeric ranges. When a header
    is present, it must match exactly (level and title) and only level ≥ 2 is considered.
    Headers inside fenced code blocks are ignored, so replacements remain deterministic.
    If the header is missing or ambiguous and fallback is allowed (both start/end provided),
    no error is raised so the caller can continue with the provided numeric range.
    """
    header_info = _extract_replacement_header(replacement)
    if header_info is None:
        return None

    level, title = header_info
    header_repr = f"{('#' * level)} {title}"
    headers = _collect_markdown_headers(original_text)
    matching_sections = [
        header for header in headers if header["level"] == level and header["title"] == title
    ]

    if not matching_sections:
        if allow_missing_header_fallback:
            return None
        raise DocumentOperationError(f"SECTION_HEADER_NOT_FOUND: {header_repr} is missing")
    if len(matching_sections) > 1:
        line_numbers = ", ".join(str(section["line_number"]) for section in matching_sections)
        raise DocumentOperationError(
            f"SECTION_HEADER_AMBIGUOUS: {header_repr} matches multiple sections (lines {line_numbers})"
        )

    target = matching_sections[0]
    section_end = len(original_text)
    for header in headers:
        if header["start"] <= target["start"]:
            continue
        if header["level"] <= level:
            section_end = header["start"]
            break

    insertion = replacement
    if insertion and not insertion.endswith("\n"):
        insertion += "\n"

    return original_text[: target["start"]] + insertion + original_text[section_end:]


def _collect_markdown_headers(text: str) -> list[dict[str, Any]]:
    """Return metadata for every Markdown header in `text`, skipping fenced code blocks."""
    headers: list[dict[str, Any]] = []
    lines = text.splitlines(keepends=True)
    in_fence = False
    position = 0

    for idx, line in enumerate(lines):
        line_start = position
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            position += len(line)
            continue
        if in_fence:
            position += len(line)
            continue

        match = _HEADER_LINE_PATTERN.match(stripped)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            if title:
                headers.append(
                    {
                        "level": level,
                        "title": title,
                        "start": line_start,
                        "line_number": idx + 1,
                    }
                )

        position += len(line)

    return headers


def _extract_replacement_header(content: str) -> Optional[tuple[int, str]]:
    """Return (level, title) if the content starts with a Markdown header (## or deeper)."""
    for line in content.splitlines():
        trimmed_line = line.strip()
        if not trimmed_line:
            continue
        match = _HEADER_LINE_PATTERN.match(line.lstrip())
        if not match:
            return None
        level = len(match.group(1))
        if level < 2:
            return None
        title = match.group(2).strip()
        if not title:
            return None
        return level, title
    return None


def _replace_block_text(original_text: str, anchor: str, replacement: str) -> str:
    """Replace a block starting at the anchor line through the next blank line."""
    if not anchor:
        raise DocumentOperationError("STRUCTURED_EDIT_ANCHOR_REQUIRED: anchor is required")

    lines = original_text.splitlines()
    matches: list[int] = []
    in_fence = False
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if anchor in line:
            matches.append(idx)

    if not matches:
        raise DocumentOperationError(
            f"STRUCTURED_EDIT_ANCHOR_NOT_FOUND: anchor '{anchor}' not found"
        )
    if len(matches) > 1:
        match_lines = ", ".join(f"line {idx + 1}" for idx in matches)
        raise DocumentOperationError(
            "STRUCTURED_EDIT_ANCHOR_AMBIGUOUS\n"
            f"anchor: \"{anchor}\"\n"
            f"matches: [{match_lines}]"
        )

    start_index = matches[0]
    end_index = start_index
    while end_index < len(lines) and lines[end_index].strip() != "":
        end_index += 1

    replacement_lines = replacement.splitlines()
    new_lines = lines[:start_index] + replacement_lines + lines[end_index:]
    return "\n".join(new_lines)


def _normalize_headers_text(original_text: str) -> str:
    """Normalize numbering for explicit ATX headers only, skipping fenced code blocks."""
    lines = original_text.splitlines()
    counters = [0] * 6
    in_fence = False
    output: list[str] = []
    violations: list[Dict[str, Any]] = []

    def _next_prefix(level: int) -> str:
        for idx in range(level - 1):
            if counters[idx] == 0:
                counters[idx] = 1
        counters[level - 1] += 1
        for idx in range(level, 6):
            counters[idx] = 0
        return ".".join(str(value) for value in counters[:level])

    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if _ATX_WITHOUT_SPACE_PATTERN.match(line):
            violations.append(
                {
                    "line_number": index + 1,
                    "reason": "atx_missing_space",
                    "line": line.rstrip(),
                }
            )

        if index + 1 < len(lines) and line.strip():
            underline = lines[index + 1].strip()
            if _SETEXT_UNDERLINE_PATTERN.match(underline) and not _HEADER_LINE_PATTERN.match(line):
                violations.append(
                    {
                        "line_number": index + 1,
                        "reason": "setext_pair",
                        "line": line.rstrip(),
                        "underline_line": index + 2,
                        "underline": underline,
                    }
                )

    if violations:
        preview = ", ".join(
            f"line {entry['line_number']} ({entry['reason']})" for entry in violations[:3]
        )
        doc_logger.warning(
            "normalize_headers aborted: non-ATX content would be promoted to headers",
            extra={
                "violation_count": len(violations),
                "violation_preview": preview,
            },
        )
        raise DocumentOperationError(
            "NORMALIZE_HEADERS_GUARDRAIL: non-ATX content would be promoted to headers; "
            "convert candidates to explicit '# ' headers first",
            extra={
                "guardrail": "non_atx_promotion",
                "violations": violations[:25],
            },
        )

    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
            continue

        match = _HEADER_LINE_PATTERN.match(line)
        if match:
            hashes, title = match.groups()
            title = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", title.strip())
            if title:
                level = len(hashes)
                prefix = _next_prefix(level)
                output.append(f"{hashes} {prefix} {title}")
                continue

        output.append(line)

    normalized = "\n".join(output)
    if original_text.endswith("\n"):
        normalized += "\n"
    return normalized


def _build_github_anchor(text: str, counts: Dict[str, int]) -> str:
    """Generate a GitHub-style anchor slug with de-duplication."""
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ascii_text.strip().lower()
    slug = slug.replace("_", "-")
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        slug = "section"
    count = counts.get(slug, 0)
    counts[slug] = count + 1
    if count:
        return f"{slug}-{count}"
    return slug


def _generate_toc_text(original_text: str) -> str:
    """Generate or update a TOC block based on headers, skipping fenced code."""
    import re
    lines = original_text.splitlines()
    toc_start = "<!-- TOC:start -->"
    toc_end = "<!-- TOC:end -->"
    in_fence = False
    in_toc = False
    filtered_lines: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if line.strip() == toc_start:
            in_toc = True
            continue
        if line.strip() == toc_end:
            in_toc = False
            continue
        if in_toc:
            continue
        filtered_lines.append(line)

    toc_lines: list[str] = []
    anchor_counts: Dict[str, int] = {}
    in_fence = False
    index = 0
    while index < len(filtered_lines):
        line = filtered_lines[index]
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence:
            index += 1
            continue
        if line.strip() and index + 1 < len(filtered_lines):
            underline = filtered_lines[index + 1].strip()
            if re.match(r"^={3,}$", underline) or re.match(r"^-{3,}$", underline):
                level = 1 if underline.startswith("=") else 2
                title = line.strip()
                if title:
                    anchor = _build_github_anchor(title, anchor_counts)
                    indent = "  " * (level - 1)
                    toc_lines.append(f"{indent}- [{title}](#{anchor})")
                    index += 2
                    continue
        match = re.match(r"^(#{1,6})(\s*)(.*)$", line)
        if match:
            hashes, _, title = match.groups()
            title = title.strip()
            if title:
                level = len(hashes)
                anchor = _build_github_anchor(title, anchor_counts)
                indent = "  " * (level - 1)
                toc_lines.append(f"{indent}- [{title}](#{anchor})")
        index += 1

    toc_block = [toc_start]
    toc_block.extend(toc_lines)
    toc_block.append(toc_end)

    body_lines = lines
    start_idx = None
    end_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == toc_start and start_idx is None:
            start_idx = idx
        if line.strip() == toc_end and start_idx is not None:
            end_idx = idx
            break

    if start_idx is not None and end_idx is not None and end_idx >= start_idx:
        body_lines = lines[:start_idx] + toc_block + lines[end_idx + 1 :]
    else:
        body_lines = toc_block + [""] + lines

    rendered = "\n".join(body_lines)
    if original_text.endswith("\n"):
        rendered += "\n"
    return rendered


def _apply_structured_edit(
    original_text: str,
    edit: Dict[str, Any],
    *,
    allow_append: bool = False,
) -> str:
    """Apply a structured edit specification to text and return updated content."""
    edit_type = str(edit.get("type") or "").strip().lower()
    if not edit_type:
        raise DocumentOperationError("STRUCTURED_EDIT_TYPE_REQUIRED: edit.type is required")

    if edit_type == "replace_range":
        start_line = edit.get("start_line")
        end_line = edit.get("end_line")
        content = edit.get("content", "")
        if start_line is None or end_line is None:
            raise DocumentOperationError(
                "STRUCTURED_EDIT_RANGE_REQUIRED: start_line and end_line are required"
            )
        return _replace_range_text(original_text, int(start_line), int(end_line), str(content))

    if edit_type == "replace_block":
        anchor = str(edit.get("anchor") or "").strip()
        content = edit.get("new_content", edit.get("content", ""))
        return _replace_block_text(original_text, anchor, str(content))

    if edit_type == "replace_section":
        section = str(edit.get("section") or "").strip()
        content = edit.get("content", "")
        if not section:
            raise DocumentOperationError("STRUCTURED_EDIT_SECTION_REQUIRED: section is required")
        return _replace_section(original_text, section, str(content), allow_append=allow_append)

    raise DocumentOperationError(f"STRUCTURED_EDIT_UNSUPPORTED: {edit_type}")


def _toggle_checklist_status(text: str, section: Optional[str], metadata: Dict[str, Any]) -> str:
    desired_raw = metadata.get("status")
    desired = desired_raw.lower().strip() if isinstance(desired_raw, str) else None
    proof = metadata.get("proof")
    label_raw = metadata.get("label") or metadata.get("item") or metadata.get("text") or metadata.get("title")
    label = label_raw.strip() if isinstance(label_raw, str) and label_raw.strip() else None
    item_index_raw = metadata.get("item_index")
    if item_index_raw is None:
        item_index_raw = metadata.get("index")
    item_index: Optional[int] = None
    if item_index_raw is not None:
        try:
            item_index = int(item_index_raw)
        except (TypeError, ValueError) as exc:
            raise DocumentOperationError(
                "CHECKLIST_ITEM_INDEX_INVALID: item_index must be a positive integer"
            ) from exc
        if item_index < 1:
            raise DocumentOperationError(
                "CHECKLIST_ITEM_INDEX_INVALID: item_index must be >= 1"
            )
    allow_append = bool(
        metadata.get("allow_append") or metadata.get("scaffold") or metadata.get("create_if_missing")
    )

    done_states = {"done", "completed", "complete", "true", "yes", "checked", "finished"}
    pending_states = {"pending", "todo", "not done", "open", "incomplete", "undone"}

    def resolve_token(existing_line: Optional[str]) -> str:
        if desired in done_states:
            return "[x]"
        if desired in pending_states:
            return "[ ]"
        if existing_line:
            return "[x]" if "- [x]" in existing_line else "[ ]"
        return "[x]"

    def extract_checklist_label(line: str) -> Optional[str]:
        trimmed = line.strip()
        if trimmed.startswith("- [ ] "):
            label_text = trimmed[len("- [ ] "):]
        elif trimmed.startswith("- [x] "):
            label_text = trimmed[len("- [x] "):]
        else:
            return None
        label_text = re.sub(r"\s*<!--\s*ID:\s*[^>]+-->\s*$", "", label_text).rstrip()
        return label_text.split(" | ", 1)[0].strip()

    def update_checklist_line(line: str, token: str) -> str:
        if "- [x]" in line:
            new_line = line.replace("- [x]", f"- {token}", 1)
        else:
            new_line = line.replace("- [ ]", f"- {token}", 1)

        trailing_anchor = ""
        anchor_match = re.search(r"\s*(<!--\s*ID:\s*[^>]+-->)\s*$", new_line)
        if anchor_match:
            trailing_anchor = " " + anchor_match.group(1)
            new_line = new_line[: anchor_match.start()].rstrip()

        parts = new_line.split(" | ")
        prefix = parts[0].rstrip()
        other_tokens = [part for part in parts[1:] if not part.startswith("proof=")]
        if proof:
            other_tokens.append(f"proof={proof}")
        new_line = " | ".join([prefix] + other_tokens) if other_tokens else prefix
        return new_line + trailing_anchor

    lines = text.splitlines()
    section_marker = SECTION_MARKER.format(section=section) if section else None
    inline_target_idx: Optional[int] = None
    section_start_idx: Optional[int] = None
    section_end_idx: int = len(lines)

    if section_marker:
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped == section_marker:
                section_start_idx = idx
                break
            if section_marker in line:
                inline_target_idx = idx
                break

        if section_start_idx is not None:
            for idx in range(section_start_idx + 1, len(lines)):
                stripped = lines[idx].strip()
                if stripped.startswith("<!-- ID:") and stripped != section_marker:
                    section_end_idx = idx
                    break
        elif inline_target_idx is None and not allow_append:
            raise DocumentOperationError(
                f"CHECKLIST_SECTION_NOT_FOUND: section '{section}' was not found; "
                "pass metadata.allow_append=true to create it"
            )
        elif inline_target_idx is None:
            doc_logger.warning(
                "Checklist section anchor '%s' missing; creating new block due allow_append.",
                section,
                extra={"section": section, "action": "status_update"},
            )
            token = resolve_token(None)
            entry_label = label or (section.replace("_", " ").title() if section else "Checklist item")
            new_line = f"- {token} {entry_label}"
            if proof:
                new_line += f" | proof={proof}"
            prefix = text.rstrip()
            if prefix:
                prefix = prefix + "\n\n"
            return prefix + section_marker + "\n" + new_line + "\n"

    replacement = False
    search_start = (section_start_idx + 1) if section_start_idx is not None else 0
    search_end = section_end_idx
    candidate_indices: List[int]
    if inline_target_idx is not None:
        candidate_indices = [inline_target_idx]
    else:
        candidate_indices = list(range(search_start, search_end))

    checklist_indices: list[int] = []
    for idx in candidate_indices:
        line = lines[idx]
        if "- [ ]" not in line and "- [x]" not in line:
            if inline_target_idx is not None:
                raise DocumentOperationError(
                    f"CHECKLIST_ITEM_INVALID: section '{section}' does not point to a checklist item"
                )
            continue
        checklist_indices.append(idx)

    target_indices: list[int]
    if inline_target_idx is not None:
        target_indices = checklist_indices
    elif label:
        normalized_label = label.casefold()
        matches = [
            idx for idx in checklist_indices
            if (extract_checklist_label(lines[idx]) or "").casefold() == normalized_label
        ]
        if len(matches) > 1:
            raise DocumentOperationError(
                f"CHECKLIST_ITEM_AMBIGUOUS: multiple checklist items match label '{label}'"
            )
        target_indices = matches
    elif item_index is not None:
        if item_index > len(checklist_indices):
            target_indices = []
        else:
            target_indices = [checklist_indices[item_index - 1]]
    elif section_start_idx is not None:
        target_indices = checklist_indices
    else:
        target_indices = checklist_indices[:1]

    for idx in target_indices:
        lines[idx] = update_checklist_line(lines[idx], resolve_token(lines[idx]))
        replacement = True

    if not replacement:
        token = resolve_token(None)
        if section and not allow_append:
            raise DocumentOperationError(
                f"CHECKLIST_ITEM_NOT_FOUND: no checklist item found for section '{section}'"
            )
        entry_label = label or (section.replace("_", " ").title() if section else "Checklist item")
        new_line = f"- {token} {entry_label}"
        if proof:
            new_line += f" | proof={proof}"
        insertion_index = search_end
        lines.insert(insertion_index, new_line)

    updated_text = "\n".join(lines)
    if text.endswith("\n"):
        return updated_text + "\n"
    return updated_text


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return fallback


def _extract_related_docs_from_body(
    body_text: str,
    docs_mapping: Dict[str, Any],
    current_doc_name: str,
) -> list[str]:
    if not body_text or not docs_mapping:
        return []

    target_lookup: Dict[str, str] = {}
    for key, value in docs_mapping.items():
        if not value:
            continue
        path_obj = Path(str(value))
        key_name = str(key).strip()
        target_lookup[path_obj.name.lower()] = key_name
        target_lookup[path_obj.stem.lower()] = key_name

    related_docs: list[str] = []
    seen: set[str] = set()
    for match in _MARKDOWN_LINK_PATTERN.finditer(body_text):
        target = (match.group(1) or "").strip()
        if not target or target.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
            continue

        target_path = target.split("#", 1)[0].split("?", 1)[0].strip()
        if not target_path:
            continue

        target_name = Path(target_path).name.lower()
        target_stem = Path(target_path).stem.lower()
        related_key = target_lookup.get(target_name) or target_lookup.get(target_stem)
        if not related_key or related_key == current_doc_name or related_key in seen:
            continue

        seen.add(related_key)
        related_docs.append(related_key)

    return related_docs


def _default_frontmatter(
    doc_name: str,
    doc_category: Optional[str],
    project_name: str,
    body_text: str,
    date_str: str,
) -> Dict[str, Any]:
    project_slug = slugify_project_name(project_name or "project")
    doc_name_slug = doc_name.lower().replace("_", "-")
    title = _extract_title(body_text, doc_name.replace("_", " ").title())
    # Build category string - combine doc_category with engineering
    category_parts = [doc_category] if doc_category else []
    if "engineering" not in category_parts:
        category_parts.append("engineering")
    category_str = "|".join(category_parts)
    return {
        "id": f"{project_slug}-{doc_name_slug}",
        "title": title,
        "doc_type": doc_name,
        "doc_name": doc_name,
        "category": category_str,
        "status": "draft",
        "version": "0.1",
        "last_updated": date_str,
        "maintained_by": "Corta Labs",
        "created_by": "Corta Labs",
        "owners": [],
        "related_docs": [],
        "tags": [],
        "summary": "",
    }


def _apply_frontmatter_pipeline(
    parsed: "FrontmatterResult",
    updated_body: str,
    *,
    doc_name: str,
    doc_category: Optional[str],
    project: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    date_str: str,
    allow_create: bool = True,
) -> tuple[str, Dict[str, Any], int]:
    if metadata and metadata.get("frontmatter_disable") is True:
        line_count = len(parsed.frontmatter_raw.splitlines()) if parsed.has_frontmatter else 0
        if parsed.has_frontmatter:
            return (
                parsed.frontmatter_raw + updated_body,
                {"frontmatter_updated": False},
                line_count,
            )
        updated_parsed = parse_frontmatter(updated_body)
        if updated_parsed.has_frontmatter:
            line_count = len(updated_parsed.frontmatter_raw.splitlines())
            return (
                updated_body,
                {"frontmatter_updated": False},
                line_count,
            )
        return updated_body, {"frontmatter_updated": False}, 0

    updates: Dict[str, Any] = {}
    updates["title"] = _extract_title(updated_body, doc_name.replace("_", " ").title())

    auto_related_docs_disabled = (
        bool(metadata.get("frontmatter_disable_related_docs")) if isinstance(metadata, dict) else False
    )
    if not auto_related_docs_disabled:
        project_docs = project.get("docs") if isinstance(project.get("docs"), dict) else {}
        updates["related_docs"] = _extract_related_docs_from_body(updated_body, project_docs, doc_name)

    if isinstance(metadata, dict):
        if metadata.get("doc_type"):
            updates["doc_type"] = metadata["doc_type"]
        if metadata.get("doc_name"):
            updates["doc_name"] = metadata["doc_name"]
    if isinstance(metadata, dict) and isinstance(metadata.get("frontmatter"), dict):
        updates.update(metadata["frontmatter"])

    updates["last_updated"] = date_str

    if not parsed.has_frontmatter:
        updated_parsed = parse_frontmatter(updated_body)
        if updated_parsed.has_frontmatter:
            if updates:
                frontmatter_raw, merged = apply_frontmatter_updates(
                    updated_parsed.frontmatter_raw,
                    updated_parsed.frontmatter_data,
                    updates,
                )
                line_count = len(frontmatter_raw.splitlines())
                new_text = frontmatter_raw + updated_parsed.body
                return (
                    new_text,
                    {
                        "frontmatter_updated": True,
                        "frontmatter_created": False,
                        "frontmatter": merged,
                    },
                    line_count,
                )
            line_count = len(updated_parsed.frontmatter_raw.splitlines())
            return (
                updated_body,
                {"frontmatter_updated": False, "frontmatter_created": False},
                line_count,
            )
        if not allow_create:
            return (
                updated_body,
                {"frontmatter_updated": False, "frontmatter_created": False},
                0,
            )

        defaults = _default_frontmatter(doc_name, doc_category, project.get("name", ""), updated_body, date_str)
        defaults.update(updates)
        frontmatter_block = build_frontmatter(defaults)
        line_count = len(frontmatter_block.splitlines())
        new_text = frontmatter_block + updated_body
        return new_text, {"frontmatter_updated": True, "frontmatter_created": True}, line_count

    frontmatter_raw, merged = apply_frontmatter_updates(
        parsed.frontmatter_raw, parsed.frontmatter_data, updates
    )
    line_count = len(frontmatter_raw.splitlines())
    new_text = frontmatter_raw + updated_body
    return new_text, {"frontmatter_updated": True, "frontmatter_created": False, "frontmatter": merged}, line_count


def _validate_comparison_symbols(value: Any) -> bool:
    """Validate that comparison symbols in strings are properly handled."""
    if not isinstance(value, str):
        return True

    # Check for patterns that look like they're meant to be numeric comparisons
    # These are the cases that typically cause "not supported between str and float" errors
    import re

    # Pattern: numeric value followed by comparison operator followed by numeric value
    # e.g., "5 > 3", "10.5 <= 20", etc.
    numeric_comparison_pattern = r'^\s*\d+\.?\d*\s*[><=]+\s*\d+\.?\d*\s*$'

    if re.match(numeric_comparison_pattern, value.strip()):
        # This looks like a numeric comparison that should be handled elsewhere
        return False

    # Also check for problematic metadata values that might be compared as numbers
    if value.strip().isdigit() or (value.replace('.', '', 1).isdigit() and '.' in value):
        # Pure numeric values might cause issues in string vs numeric comparisons
        return True  # Allow these, but be cautious

    return True


def _build_create_doc_body(
    content: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> str:
    if content:
        body = str(content)
    else:
        metadata = metadata or {}
        body = ""
        raw_body = metadata.get("body") or metadata.get("snippet")
        if isinstance(raw_body, str):
            body = raw_body
        elif isinstance(metadata.get("sections"), list):
            sections = []
            for section in metadata["sections"]:
                if not isinstance(section, dict):
                    continue
                title = str(section.get("title") or "").strip()
                text = str(section.get("content") or "").strip()
                if not title and not text:
                    continue
                if title:
                    sections.append(f"## {title}")
                if text:
                    sections.append(text)
                sections.append("")
            body = "\n".join(sections).rstrip()
    if not body:
        raise DocumentOperationError(
            "CREATE_DOC_MISSING_CONTENT: provide content, body, snippet, or sections"
        )
    if not body.endswith("\n"):
        body += "\n"
    return body


def _extract_header_anchors(text: str) -> set[str]:
    import re

    parsed = parse_frontmatter(text)
    lines = parsed.body.splitlines()
    anchors: set[str] = set()
    counts: Dict[str, int] = {}
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if not match:
            continue
        title = match.group(2).strip()
        if not title:
            continue
        anchors.add(_build_github_anchor(title, counts))
    return anchors


def _validate_crosslinks(
    text: str,
    project: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    parsed = parse_frontmatter(text)
    related_docs = []
    if isinstance(metadata, dict) and isinstance(metadata.get("related_docs"), list):
        related_docs = metadata.get("related_docs") or []
    else:
        related_docs = parsed.frontmatter_data.get("related_docs") or []
        if not isinstance(related_docs, list):
            related_docs = []

    check_anchors = bool(metadata.get("check_anchors")) if isinstance(metadata, dict) else False
    docs_dir = project.get("docs_dir")
    project_root = Path(project.get("root", ""))
    base_dir = Path(docs_dir) if docs_dir else _resolve_doc_path(project, "architecture").parent
    diagnostics: list[Dict[str, Any]] = []

    for entry in related_docs:
        target = str(entry)
        path_part, anchor_part = (target.split("#", 1) + [None])[:2]
        candidate = Path(path_part)
        if not candidate.is_absolute():
            candidate = base_dir / candidate
        resolved = candidate.resolve()
        exists = resolved.exists()
        anchor_found = None
        if exists and check_anchors and anchor_part:
            anchors = _extract_header_anchors(resolved.read_text(encoding="utf-8"))
            anchor_found = anchor_part in anchors
        diagnostics.append(
            {
                "target": target,
                "path": str(resolved),
                "exists": exists,
                "anchor": anchor_part,
                "anchor_found": anchor_found,
            }
        )

    return diagnostics


def _validate_and_correct_inputs(
    doc_name: Optional[str] = None,
    action: str = "append",
    section: Optional[str] = None,
    content: Optional[str] = None,
    patch: Optional[str] = None,
    patch_source_hash: Optional[str] = None,
    edit: Optional[Dict[str, Any]] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    template: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    doc: Optional[str] = None,
) -> tuple[str, str, Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
    """
    Bulletproof parameter validation and correction that NEVER fails.

    Returns corrected parameters tuple: (doc_name, action, section, content, template, metadata)
    """
    # Define validation schema
    validation_schema = {
        "doc_name": {
            "type": str,
            "required": True,
            "default": ""
        },
        "action": {
            "type": str,
            "required": True,
            "allowed_values": {"replace_section", "append", "status_update", "list_sections", "batch",
                             "apply_patch", "replace_range", "replace_text", "normalize_headers", "generate_toc", "create_doc", "validate_crosslinks",
                             "search", "create_research_doc", "create_bug_report", "create_review_report", "create_agent_report_card"},
            "default": "append"
        },
        "section": {
            "type": str,
            "required": False,
            "default": None
        },
        "content": {
            "type": str,
            "required": False,
            "default": None
        },
        "template": {
            "type": str,
            "required": False,
            "default": None
        },
        "metadata": {
            "type": dict,
            "required": False,
            "default": {}
        }
    }

    # Apply bulletproof parameter correction
    provided_doc_name = doc_name or doc or ""

    input_params = {
        "doc_name": provided_doc_name,
        "action": action,
        "section": section,
        "content": content,
        "patch_source_hash": patch_source_hash,
        "edit": edit,
        "template": template,
        "metadata": metadata
    }

    corrected_params = BulletproofParameterCorrector.ensure_parameter_validity(input_params, validation_schema)

    # Apply business logic corrections
    corrected_doc_name = corrected_params["doc_name"]
    corrected_action = corrected_params["action"]
    corrected_section = corrected_params["section"]
    corrected_content = corrected_params["content"]
    corrected_template = corrected_params["template"]
    corrected_metadata = corrected_params["metadata"]

    # Special handling for different actions
    strict_doc_actions = {
        "apply_patch",
        "replace_range",
        "replace_text",
        "normalize_headers",
        "generate_toc",
        "validate_crosslinks",
        "create_doc",
    }
    if action in strict_doc_actions and provided_doc_name:
        corrected_doc_name = str(provided_doc_name).strip()
    if corrected_action == "list_sections":
        return corrected_doc_name, corrected_action, None, None, None, {}

    if corrected_action == "batch":
        # Ensure metadata has operations list
        if not isinstance(corrected_metadata, dict):
            corrected_metadata = {}

        if "operations" not in corrected_metadata or not corrected_metadata["operations"]:
            corrected_metadata["operations"] = []

        if not isinstance(corrected_metadata["operations"], list):
            corrected_metadata["operations"] = [corrected_metadata["operations"]]

        return corrected_doc_name, corrected_action, None, None, None, corrected_metadata

    # Section validation for actions that need it
    if corrected_action in {"replace_section", "status_update"}:
        if not corrected_section:
            corrected_section = "main_content"

        # Sanitize section ID - keep only alphanumeric, hyphens, underscores
        import re
        sanitized_section = re.sub(r'[^a-zA-Z0-9_-]', '', corrected_section)
        if not sanitized_section:
            sanitized_section = "main_content"
        corrected_section = sanitized_section

    # For actions that do NOT require an explicit section (e.g. append, batch,
    # list_sections), treat missing/None sections as truly absent rather than
    # letting the generic corrector turn them into fallback strings like
    # "No message provided", which would create bogus anchors.
    if corrected_action not in {"replace_section", "status_update"}:
        if section is None:
            corrected_section = None

    # Content/template handling (preserve caller formatting for content)
    if content is not None:
        corrected_content = str(content).replace("\r\n", "\n")

    # Content/template handling
    if corrected_action == "status_update":
        # For status updates, ensure metadata has required fields
        if not isinstance(corrected_metadata, dict):
            corrected_metadata = {}

        if not any(key in corrected_metadata for key in ["status", "proof", "completed"]):
            corrected_metadata["status"] = "in_progress"

        # Clear content and template for status updates
        corrected_content = None
        corrected_template = None
    else:
        # For other actions, ensure we have either content or template
        if corrected_action in {"apply_patch", "replace_range", "replace_text", "normalize_headers", "generate_toc", "create_doc", "validate_crosslinks"}:
            if corrected_action == "apply_patch" and edit is not None:
                if corrected_content in {"No message provided", "Empty message"}:
                    corrected_content = None
            if corrected_action in {"normalize_headers", "generate_toc"}:
                corrected_content = None
                corrected_template = None
            if corrected_action in {"create_doc", "validate_crosslinks"}:
                corrected_content = corrected_content if corrected_content not in {"No message provided", "Empty message"} else None
                corrected_template = None
        elif not corrected_content and not corrected_template:
            corrected_content = f"## {corrected_action.replace('_', ' ').title()}\n\nContent placeholder."

    return corrected_doc_name, corrected_action, corrected_section, corrected_content, corrected_template, corrected_metadata


async def _verify_file_write(file_path: Path, expected_content: str, expected_hash: str) -> bool:
    """Verify that the file was written correctly."""
    try:
        # Check if file exists
        if not file_path.exists():
            return False

        # Read the actual content
        actual_content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")

        # Verify content matches exactly
        if actual_content != expected_content:
            doc_logger.error(f"Content mismatch in {file_path}: expected {len(expected_content)} chars, got {len(actual_content)} chars")
            return False

        # Verify hash matches
        actual_hash = _hash_text(actual_content)
        if actual_hash != expected_hash:
            doc_logger.error(f"Hash mismatch in {file_path}: expected {expected_hash[:8]}..., got {actual_hash[:8]}...")
            return False

        return True

    except Exception as e:
        doc_logger.error(f"Failed to verify file write for {file_path}: {e}")
        return False


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DefaultDict(dict):
    """Helper to avoid KeyError when formatting template fragments."""

    def __init__(self, base: Dict[str, Any]):
        super().__init__(base)

    def __missing__(self, key: str) -> str:
        return ""
