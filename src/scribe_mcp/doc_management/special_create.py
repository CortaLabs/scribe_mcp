"""Special document creation and index update helpers for manage_docs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from scribe_mcp import server as server_module
from scribe_mcp.doc_management import healing as healing_shared
from scribe_mcp.doc_management import indexing as indexing_shared
from scribe_mcp.doc_management import special_indexes as special_indexes_shared
from scribe_mcp.doc_management import utils as utils_shared
from scribe_mcp.doc_management.boundary_guidance import build_manage_docs_boundary_guidance
from scribe_mcp.doc_management.naming import normalize_research_doc_name
from scribe_mcp.doc_management.manager import (
    DocumentOperationError,
)
from scribe_mcp.tools.agent_project_utils import resolve_authoritative_write_scope
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.utils.slug import slugify_project_name


def _hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _resolve_inline_special_content(
    content: Optional[str],
    metadata: Dict[str, Any],
) -> Optional[str]:
    """Return explicit inline content for special create paths when provided."""
    inline_content: str = ""

    if isinstance(content, str) and content:
        inline_content = content
    else:
        raw_body = metadata.get("body") or metadata.get("snippet")
        if isinstance(raw_body, str):
            inline_content = raw_body
        elif isinstance(metadata.get("sections"), list):
            blocks = []
            for section in metadata["sections"]:
                if not isinstance(section, dict):
                    continue
                title = str(section.get("title") or "").strip()
                text = str(section.get("content") or "").strip()
                if not title and not text:
                    continue
                if title:
                    blocks.append(f"## {title}")
                if text:
                    blocks.append(text)
                blocks.append("")
            inline_content = "\n".join(blocks).rstrip()

    if not inline_content:
        return None
    if not inline_content.endswith("\n"):
        inline_content += "\n"
    return utils_shared.strip_trailing_whitespace_lines(inline_content)


def _normalize_stage(value: Any) -> str:
    """Normalize stage metadata for stage-bearing special docs."""
    stage = str(value or "").strip().lower()
    if not stage or stage == "unknown":
        return "general"
    stage = re.sub(r"[^\w\-_.]+", "_", stage).strip("_")
    return stage or "general"


def _is_truthy_metadata_flag(metadata: Dict[str, Any], key: str) -> bool:
    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _research_target_dir_override_enabled(metadata: Dict[str, Any]) -> bool:
    return _is_truthy_metadata_flag(metadata, "repo_research")


def _project_docs_dir(project: Dict[str, Any], project_root: Path) -> Path:
    """Resolve canonical project docs directory for project-scoped artifacts."""
    progress_log_path = str(project.get("progress_log") or "").strip()
    if progress_log_path:
        progress_parent = Path(progress_log_path).parent
        if progress_parent:
            return progress_parent

    docs_dir_str = str(project.get("docs_dir") or "").strip()
    if docs_dir_str and docs_dir_str not in {"", "."}:
        return Path(docs_dir_str)

    project_slug = slugify_project_name(project.get("name", ""))
    return project_root / ".scribe" / "docs" / "dev_plans" / project_slug


def _normalize_research_doc_name(doc_name: str) -> str:
    return normalize_research_doc_name(doc_name)


async def _get_or_create_storage_project(backend: Any, project: Dict[str, Any]) -> Any:
    timeout = server_module.settings.storage_timeout_seconds
    async with asyncio.timeout(timeout):
        storage_record = await backend.fetch_project(project["name"])
    if not storage_record:
        async with asyncio.timeout(timeout):
            storage_record = await backend.upsert_project(
                name=project["name"],
                repo_root=project["root"],
                progress_log_path=project["progress_log"],
            )
    return storage_record


def _build_special_metadata(
    project: Dict[str, Any],
    metadata: Dict[str, Any],
    agent_id: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return utils_shared.build_special_metadata(project, metadata, agent_id, extra=extra)


async def _render_special_template(
    project: Dict[str, Any],
    agent_id: str,
    template_name: str,
    metadata: Dict[str, Any],
    extra_metadata: Optional[Dict[str, Any]] = None,
    prepared_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox",
        )
        if prepared_metadata is None:
            prepared_metadata = _build_special_metadata(
                project,
                metadata,
                agent_id,
                extra=extra_metadata,
            )
        rendered = engine.render_template(
            template_name=f"documents/{template_name}",
            metadata=prepared_metadata,
        )
        return utils_shared.strip_trailing_whitespace_lines(rendered)
    except (ImportError, TemplateEngineError) as exc:
        raise DocumentOperationError(f"Failed to render template '{template_name}': {exc}") from exc


async def _record_special_doc_change(
    backend: Any,
    project: Dict[str, Any],
    agent_id: str,
    doc_label: str,
    target_path: Path,
    metadata: Dict[str, Any],
    before_hash: str,
    after_hash: str,
    logger: logging.Logger,
) -> None:
    if not backend:
        return
    try:
        storage_record = await _get_or_create_storage_project(backend, project)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to prepare storage record for %s: %s", doc_label, exc)
        return

    action = "create" if not before_hash else "update"
    try:
        await backend.record_doc_change(
            storage_record,
            doc=doc_label,
            section=None,
            action=action,
            agent=agent_id,
            metadata=metadata,
            sha_before=before_hash,
            sha_after=after_hash,
        )
    except Exception as exc:
        logger.warning("Failed to record special doc change for %s: %s", doc_label, exc)


async def _record_agent_report_card_metadata(
    backend: Any,
    project: Dict[str, Any],
    agent_id: str,
    target_path: Path,
    metadata: Dict[str, Any],
    logger: logging.Logger,
) -> None:
    if not backend:
        return
    try:
        storage_record = await _get_or_create_storage_project(backend, project)
    except Exception as exc:
        logger.warning("Failed to prepare storage project for agent card: %s", exc)
        return

    try:
        await backend.record_agent_report_card(
            storage_record,
            file_path=str(target_path),
            agent_name=metadata.get("agent_name", agent_id),
            stage=metadata.get("stage"),
            overall_grade=utils_shared.parse_numeric_grade(metadata.get("overall_grade")),
            performance_level=metadata.get("performance_level"),
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning("Failed to record agent report card metadata: %s", exc)


def _case_registry_method(storage_backend: Any) -> Optional[Callable[..., Any]]:
    for method_name in (
        "upsert_case_registry_record",
        "upsert_case_registry",
        "upsert_case_record",
        "register_case",
    ):
        candidate = getattr(storage_backend, method_name, None)
        if callable(candidate):
            return candidate
    return None


async def _call_case_registry_method(method: Callable[..., Any], upsert_kwargs: Dict[str, Any]) -> None:
    def _is_signature_mismatch(exc: TypeError) -> bool:
        message = str(exc)
        markers = (
            "unexpected keyword argument",
            "positional argument",
            "required positional argument",
            "keyword-only argument",
            "multiple values for argument",
            "takes",
            "missing",
        )
        return any(marker in message for marker in markers)

    attempts = (
        ((), upsert_kwargs),
        ((upsert_kwargs,), {}),
        ((), {"payload": upsert_kwargs}),
    )
    last_error: Optional[Exception] = None
    for args, kwargs in attempts:
        try:
            result = method(*args, **kwargs)
            if asyncio.iscoroutine(result):
                await result
            return
        except TypeError as exc:
            if not _is_signature_mismatch(exc):
                raise
            last_error = exc
            continue
    if last_error is not None:
        raise last_error


async def _register_case_in_shared_registry(
    storage_backend: Any,
    *,
    project: Dict[str, Any],
    target_path: Path,
    metadata: Dict[str, Any],
    doc_label: str,
) -> Optional[str]:
    if doc_label not in {"bug_report", "security_report"}:
        return None
    if not storage_backend:
        return None

    register_method = _case_registry_method(storage_backend)
    if register_method is None:
        return "Case registry registration skipped: storage backend does not expose a shared case registration method."

    extracted = utils_shared.extract_case_registry_metadata_from_report(
        target_path,
        project_root=Path(project.get("root", "")),
        metadata=metadata,
        project=project,
    )
    upsert_kwargs = utils_shared.build_case_registry_upsert_kwargs(
        extracted=extracted,
        overrides={"source_tool": "manage_docs.create"},
    )
    if upsert_kwargs is None:
        return "Case registry registration skipped: unable to derive normalized case metadata from created report."

    try:
        await _call_case_registry_method(register_method, upsert_kwargs)
    except Exception as exc:
        return f"Case registry registration failed: {exc}"
    return None


def get_index_updater_for_path(
    file_path: Path,
    project_root: Path,
    docs_dir: Path,
    agent_id: str,
) -> Optional[Callable[[], Awaitable[None]]]:
    return indexing_shared.get_index_updater_for_path(
        file_path=file_path,
        project_root=project_root,
        docs_dir=docs_dir,
        agent_id=agent_id,
        update_research_index=_update_research_index,
        update_bug_index=_update_bug_index,
        update_security_index=_update_security_index,
        update_review_index=_update_review_index,
        update_agent_card_index=_update_agent_card_index,
    )


async def handle_special_document_creation(
    project: Dict[str, Any],
    action: str,
    doc_name: Optional[str],
    target_dir: Optional[str],
    content: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    agent_id: str,
    storage_backend: Any,
    helper: Any,
    context: Any,
    project_registry: Any,
    logger: logging.Logger,
) -> Dict[str, Any]:
    healed_metadata, _, _ = healing_shared.normalize_metadata_with_healing(metadata)
    metadata = healed_metadata

    project_root = Path(project.get("root", ""))
    docs_dir = _project_docs_dir(project, project_root)
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    execution_context = None
    if hasattr(server_module, "get_execution_context"):
        try:
            execution_context = server_module.get_execution_context()
        except Exception:
            execution_context = None

    template_name = ""
    doc_label = ""
    target_path: Optional[Path] = None
    index_updater: Optional[Callable[[], Awaitable[None]]] = None
    index_path: Optional[Path] = None
    extra_metadata: Dict[str, Any] = {}
    placement_warning: Optional[str] = None
    primary_doc_key: Optional[str] = None

    if action == "create_research_doc":
        if not doc_name:
            return helper.apply_context_payload(
                helper.error_response(
                    "doc_name is required for research document creation",
                ),
                context,
            )
        safe_name = _normalize_research_doc_name(doc_name)

        canonical_research_dir = docs_dir / "research"
        research_dir = canonical_research_dir
        override_dir = target_dir or metadata.get("target_dir")
        if override_dir:
            requested_research_dir = Path(override_dir)
            if not requested_research_dir.is_absolute():
                requested_research_dir = project_root / requested_research_dir
            try:
                requested_is_canonical = (
                    requested_research_dir.resolve() == canonical_research_dir.resolve()
                )
            except Exception:
                requested_is_canonical = False

            if requested_is_canonical:
                research_dir = canonical_research_dir
            elif _research_target_dir_override_enabled(metadata):
                research_dir = requested_research_dir
                placement_warning = (
                    f"Explicit research override active: writing to '{research_dir.resolve()}/'. "
                    f"Canonical project research path is '{canonical_research_dir.resolve()}'."
                )
            else:
                placement_warning = (
                    "Ignored research target_dir because active Scribe project research "
                    "defaults to the canonical managed docs path. "
                    f"Requested '{requested_research_dir.resolve()}/'; using "
                    f"'{canonical_research_dir.resolve()}/'. Set metadata.repo_research=true "
                    "to write outside the active project research directory."
                )

        if research_dir == canonical_research_dir:
            legacy_docs_dir_str = str(project.get("docs_dir") or "").strip()
            if legacy_docs_dir_str:
                legacy_research_dir = Path(legacy_docs_dir_str) / "research"
                try:
                    if legacy_research_dir.resolve() != research_dir.resolve() and legacy_research_dir.exists():
                        legacy_docs = sorted(
                            p
                            for p in legacy_research_dir.glob("*.md")
                            if p.name != "INDEX.md" and not p.name.startswith("_")
                        )
                        if legacy_docs:
                            placement_warning = (
                                "Canonical research placement is now project-scoped. "
                                f"Detected {len(legacy_docs)} legacy research artifact(s) in "
                                f"'{legacy_research_dir.resolve()}'. "
                                "Those files are not reclassified automatically; use explicit migration."
                            )
                except Exception:
                    pass

        target_path = research_dir / f"{safe_name}.md"
        template_name = "RESEARCH_REPORT_TEMPLATE.md"
        doc_label = "research_report"
        primary_doc_key = safe_name
        extra_metadata = {
            "title": doc_name.replace("_", " ").title(),
            "doc_name": safe_name,
            "researcher": metadata.get("researcher", agent_id),
        }
        index_updater = lambda: _update_research_index(research_dir, agent_id, project_root)
        index_path = research_dir / "INDEX.md"
    elif action == "create_bug_report":
        category = metadata.get("category")
        if not category or not category.strip():
            return helper.apply_context_payload(
                helper.error_response(
                    "metadata with non-empty 'category' is required for bug report creation",
                ),
                context,
            )

        category = re.sub(r"[^\w\-_.]", "_", category.strip())

        slug = metadata.get("slug")
        if slug:
            slug = re.sub(r"[^\w\-_.]", "_", str(slug).strip())
        if not slug:
            slug = f"bug_{int(now.timestamp())}"
        bug_dir = project_root / "docs" / "bugs" / category / f"{now.strftime('%Y-%m-%d')}_{slug}"
        target_path = bug_dir / "report.md"
        template_name = "BUG_REPORT_TEMPLATE.md"
        doc_label = "bug_report"
        primary_doc_key = slug
        extra_metadata = {
            "slug": slug,
            "category": category,
            "reported_at": metadata.get("reported_at", timestamp_str),
        }
        index_updater = lambda: _update_bug_index(project_root / "docs" / "bugs", agent_id, project_root)
        index_path = project_root / "docs" / "bugs" / "INDEX.md"
    elif action == "create_security_report":
        category = metadata.get("category")
        if not category or not category.strip():
            return helper.apply_context_payload(
                helper.error_response(
                    "metadata with non-empty 'category' is required for security report creation",
                ),
                context,
            )

        category = re.sub(r"[^\w\-_.]", "_", category.strip())

        slug = metadata.get("slug")
        if slug:
            slug = re.sub(r"[^\w\-_.]", "_", str(slug).strip())
        if not slug:
            slug = f"sec_{int(now.timestamp())}"
        security_dir = project_root / "docs" / "security" / category / f"{now.strftime('%Y-%m-%d')}_{slug}"
        target_path = security_dir / "report.md"
        template_name = "SECURITY_REPORT_TEMPLATE.md"
        doc_label = "security_report"
        primary_doc_key = slug
        extra_metadata = {
            "slug": slug,
            "category": category,
            "reported_at": metadata.get("reported_at", timestamp_str),
        }
        index_updater = lambda: _update_security_index(project_root / "docs" / "security", agent_id, project_root)
        index_path = project_root / "docs" / "security" / "INDEX.md"
    elif action == "create_review_report":
        stage = _normalize_stage(metadata.get("stage"))
        target_path = docs_dir / f"REVIEW_REPORT_{stage}_{now.strftime('%Y-%m-%d')}_{now.strftime('%H%M')}.md"
        template_name = "REVIEW_REPORT_TEMPLATE.md"
        doc_label = "review_report"
        primary_doc_key = str(doc_name).strip() if doc_name else target_path.stem
        extra_metadata = {"stage": stage}
        index_updater = lambda: _update_review_index(docs_dir, agent_id, project_root)
        index_path = docs_dir / "REVIEW_INDEX.md"
    elif action == "create_agent_report_card":
        card_agent = metadata.get("agent_name", agent_id)
        stage = _normalize_stage(metadata.get("stage"))
        target_path = docs_dir / f"AGENT_REPORT_CARD_{card_agent}_{stage}_{now.strftime('%Y%m%d_%H%M')}.md"
        template_name = "AGENT_REPORT_CARD_TEMPLATE.md"
        doc_label = "agent_report_card"
        primary_doc_key = str(doc_name).strip() if doc_name else target_path.stem
        extra_metadata = {
            "agent_name": card_agent,
            "stage": stage,
        }
        index_updater = lambda: _update_agent_card_index(docs_dir, agent_id, project_root)
        index_path = docs_dir / "AGENT_CARDS_INDEX.md"
    else:
        return helper.apply_context_payload(
            helper.error_response(f"Unsupported special document action: {action}"),
            context,
        )

    prepared_metadata = _build_special_metadata(project, metadata, agent_id, extra_metadata)

    rendered_content = _resolve_inline_special_content(content, metadata)
    if not rendered_content:
        try:
            if action == "create_review_report":
                rendered_content = await _render_review_report_template(
                    project,
                    agent_id,
                    prepared_metadata,
                    logger=logger,
                )
            elif action == "create_agent_report_card":
                rendered_content = await _render_agent_report_card_template(
                    project,
                    agent_id,
                    prepared_metadata,
                    logger=logger,
                )
            else:
                rendered_content = await _render_special_template(
                    project,
                    agent_id,
                    template_name,
                    metadata,
                    extra_metadata=extra_metadata,
                    prepared_metadata=prepared_metadata,
                )
        except DocumentOperationError as exc:
            return helper.apply_context_payload(
                helper.error_response(str(exc)),
                context,
            )

    if rendered_content is None:
        return helper.apply_context_payload(
            helper.error_response("Failed to render document content."),
            context,
        )

    try:
        target_path.resolve().relative_to(project_root.resolve())
    except ValueError:
        boundary_guidance = build_manage_docs_boundary_guidance(
            project,
            rejected_target=str(target_path.parent),
        )
        return helper.apply_context_payload(
            helper.error_response(
                f"Generated document path {target_path} is outside project root",
                suggestion=(
                    "Use an in-project target_dir under the active project root, "
                    "or omit target_dir to use the canonical docs location."
                ),
                extra={"boundary_guidance": boundary_guidance},
            ),
            context,
        )

    overwrite = bool(metadata.get("overwrite")) if isinstance(metadata, dict) else False
    if target_path.exists() and not overwrite:
        return helper.apply_context_payload(
            helper.error_response(
                "CREATE_DOC_EXISTS: target path already exists (use metadata.overwrite to replace)",
            ),
            context,
        )

    if dry_run:
        return helper.apply_context_payload(
            {
                "ok": True,
                "dry_run": True,
                "path": str(target_path),
                "content": rendered_content,
                "next_step_guidance": (
                    "create only scaffolds the document. Follow up with "
                    "manage_docs(action='replace_section', ...) to add real content."
                ),
            },
            context,
        )

    before_hash = ""
    if target_path.exists():
        try:
            before_hash = _hash_text(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            before_hash = ""

    log_warning: Optional[str] = None

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(rendered_content, encoding="utf-8")

        # Fire-and-forget sync to remote object store
        try:
            from scribe_mcp.object_store import sync_file_to_store
            await sync_file_to_store(target_path, rendered_content, project_root)
        except Exception:
            pass

        after_hash = _hash_text(rendered_content)

        await _record_special_doc_change(
            storage_backend,
            project,
            agent_id,
            doc_label,
            target_path,
            prepared_metadata,
            before_hash,
            after_hash,
            logger=logger,
        )
        if doc_label == "agent_report_card":
            await _record_agent_report_card_metadata(
                storage_backend,
                project,
                agent_id,
                target_path,
                prepared_metadata,
                logger=logger,
            )
        case_registry_warning = await _register_case_in_shared_registry(
            storage_backend,
            project=project,
            target_path=target_path,
            metadata=prepared_metadata,
            doc_label=doc_label,
        )

        healed_metadata, _, _ = healing_shared.normalize_metadata_with_healing(prepared_metadata)
        log_meta = healed_metadata
        log_meta.update(
            {
                "doc": doc_label,
                "section": "",
                "action": "create",
                "document_type": doc_label,
                "file_path": str(target_path),
                "file_size": target_path.stat().st_size,
            }
        )
        for key, value in list(log_meta.items()):
            if isinstance(value, (dict, list)):
                try:
                    log_meta[key] = json.dumps(value, sort_keys=True)
                except (TypeError, ValueError):
                    log_meta[key] = str(value)

        try:
            await append_entry(
                message=f"Created {doc_label.replace('_', ' ')}: {target_path.name}",
                status="success",
                meta=log_meta,
                agent=agent_id,
                log_type="doc_updates",
                format="structured",
            )
        except Exception as exc:
            log_warning = str(exc)

        if index_updater:
            try:
                await index_updater()
            except Exception as exc:
                logger.warning("Failed to update index for %s: %s", doc_label, exc)

        registration_warning: Optional[str] = None
        if project:
            try:
                project_name = project.get("name")
                if project_name:
                    registration_keys: list[str] = []
                    if primary_doc_key and str(primary_doc_key).strip():
                        registration_keys.append(str(primary_doc_key).strip())
                    if doc_name and str(doc_name).strip():
                        alias_key = str(doc_name).strip()
                        if alias_key not in registration_keys:
                            registration_keys.append(alias_key)
                    legacy_key = f"{doc_label}_{target_path.stem}"
                    if legacy_key not in registration_keys:
                        registration_keys.append(legacy_key)

                    current_docs = dict(project.get("docs", {}) or {})
                    for key in registration_keys:
                        current_docs[key] = str(target_path)
                    project["docs"] = current_docs
                    state_manager = getattr(server_module, "state_manager", None)
                    authoritative_scope = resolve_authoritative_write_scope(
                        context=execution_context,
                        agent_session_id=None,
                    )
                    authoritative_session_id = authoritative_scope.get("authoritative_session_id")
                    if storage_backend:
                        docs_json = json.dumps(current_docs)
                        await storage_backend.update_project_docs(project_name, docs_json)
                    else:
                        registration_warning = "Doc registration used state-only fallback: storage backend unavailable."
                    if state_manager and hasattr(state_manager, "set_current_project"):
                        await state_manager.set_current_project(
                            project_name,
                            project,
                            agent_id=agent_id,
                            session_id=authoritative_session_id,
                            resolved_scope=authoritative_scope.get("resolved_scope"),
                            mirror_global=False,
                        )
                        if not authoritative_session_id:
                            message = (
                                "Doc registration could not bind authoritative session; "
                                "state updated without session binding."
                            )
                            registration_warning = f"{registration_warning}; {message}" if registration_warning else message
                    try:
                        project_registry.record_doc_update(
                            project_name=project_name,
                            doc=registration_keys[0] if registration_keys else legacy_key,
                            action="create",
                            before_hash=None,
                            after_hash=after_hash,
                        )
                    except Exception as reg_exc:
                        if registration_warning:
                            registration_warning += f"; Registry update failed: {reg_exc}"
                        else:
                            registration_warning = f"Registry update failed: {reg_exc}"
            except Exception as exc:
                registration_warning = f"Doc registration failed: {exc}"
        if case_registry_warning:
            if registration_warning:
                registration_warning += f"; {case_registry_warning}"
            else:
                registration_warning = case_registry_warning

        if storage_backend and project and index_path and index_path.exists():
            try:
                project_name = project.get("name")
                if project_name:
                    index_key = f"{doc_label}_index"
                    current_project = await storage_backend.fetch_project(project_name)
                    if current_project and current_project.docs_json:
                        current_docs = json.loads(current_project.docs_json)
                    else:
                        current_docs = project.get("docs", {})

                    current_docs[index_key] = str(index_path)
                    docs_json = json.dumps(current_docs)
                    await storage_backend.update_project_docs(project_name, docs_json)
            except Exception as exc:
                if registration_warning:
                    registration_warning += f"; Index registration failed: {exc}"
                else:
                    registration_warning = f"Index registration failed: {exc}"

        success_payload: Dict[str, Any] = {
            "ok": True,
            "path": str(target_path),
            "document_type": doc_label,
            "doc_name": primary_doc_key or target_path.stem,
            "file_size": target_path.stat().st_size,
            "next_step_guidance": (
                "create scaffolds the document. Next, use "
                "manage_docs(action='replace_section', ...) to fill required sections."
            ),
        }
        if log_warning:
            success_payload["log_warning"] = log_warning
        if registration_warning:
            success_payload["registration_warning"] = registration_warning
        if placement_warning:
            success_payload["placement_warning"] = placement_warning

        return helper.apply_context_payload(success_payload, context)
    except Exception as exc:
        return helper.apply_context_payload(
            helper.error_response(f"Failed to create document: {exc}"),
            context,
        )


async def _update_research_index(research_dir: Path, agent_id: str, repo_root: Path | None = None) -> None:
    await special_indexes_shared.update_research_index(research_dir, agent_id, repo_root=repo_root)


async def _update_bug_index(bugs_dir: Path, agent_id: str, repo_root: Path | None = None) -> None:
    await special_indexes_shared.update_bug_index(bugs_dir, agent_id, repo_root=repo_root)


async def _update_security_index(security_dir: Path, agent_id: str, repo_root: Path | None = None) -> None:
    await special_indexes_shared.update_security_index(security_dir, agent_id, repo_root=repo_root)


async def _update_review_index(docs_dir: Path, agent_id: str, repo_root: Path | None = None) -> None:
    await special_indexes_shared.update_review_index(docs_dir, agent_id, repo_root=repo_root)


async def _update_agent_card_index(docs_dir: Path, agent_id: str, repo_root: Path | None = None) -> None:
    await special_indexes_shared.update_agent_card_index(docs_dir, agent_id, repo_root=repo_root)


async def _render_review_report_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
    logger: logging.Logger,
) -> str:
    return await special_indexes_shared.render_review_report_template(
        project=project,
        agent_id=agent_id,
        prepared_metadata=prepared_metadata,
        logger=logger,
    )


async def _render_agent_report_card_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
    logger: logging.Logger,
) -> str:
    return await special_indexes_shared.render_agent_report_card_template(
        project=project,
        agent_id=agent_id,
        prepared_metadata=prepared_metadata,
        logger=logger,
    )
