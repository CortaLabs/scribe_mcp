"""Tool for generating documentation scaffolds from templates."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple
import hashlib

from scribe_mcp import server as server_module
from scribe_mcp.shared.project_registry import get_runtime_project_registry
from scribe_mcp.config.settings import settings
from scribe_mcp.config.downstream_assets import ensure_downstream_seed_assets
from scribe_mcp.tools.project_utils import slugify_project_name
from scribe_mcp.server import app
from scribe_mcp.tool_contracts import additive_local_tool
from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError
from scribe_mcp.templates import TEMPLATE_FILENAMES, load_templates, substitution_context
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import ProjectResolutionError


OUTPUT_FILENAMES: List[Tuple[str, str]] = [
    ("architecture", "ARCHITECTURE_GUIDE.md"),
    ("phase_plan", "PHASE_PLAN.md"),
    ("checklist", "CHECKLIST.md"),
    ("progress_log", "PROGRESS_LOG.md"),
    ("doc_log", "DOC_LOG.md"),
    ("security_log", "SECURITY_LOG.md"),
    ("bug_log", "BUG_LOG.md"),
]

logger = logging.getLogger(__name__)


class _GenerateDocTemplatesHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_GENERATE_DOC_TEMPLATES_HELPER = _GenerateDocTemplatesHelper()
_PROJECT_REGISTRY = get_runtime_project_registry()


@app.tool(**additive_local_tool(title="Generate Document Templates", tags=("docs", "templates", "write")))
async def generate_doc_templates(
    agent: str = "Codex",
    project_name: str = "",
    author: str | None = None,
    overwrite: bool = False,
    force: bool = False,
    documents: Iterable[str] | None = None,
    base_dir: str | None = None,
    custom_context: Any = None,
    legacy_fallback: bool = False,
    include_template_metadata: bool = False,
    validate_only: bool = False,
) -> Dict[str, Any]:
    """Render the standard documentation templates for a project.

    Notes:
    - Overwrites are blocked by default; set force=True (or legacy overwrite=True) to regenerate.
    - Existing progress logs are always preserved even when force is set.
    - Use documents=[...] to regenerate a single doc instead of all.
    """
    state_snapshot = await server_module.state_manager.record_tool("generate_doc_templates")
    if not project_name:
        return {
            "ok": False,
            "error": "project_name is required",
            "generated": [],
            "created": [],
            "warnings": [],
        }
    explicit_project = None if base_dir else project_name
    try:
        logging_context = await _GENERATE_DOC_TEMPLATES_HELPER.prepare_context(
            tool_name="generate_doc_templates",
            agent_id=None,
            explicit_project=explicit_project,
            require_project=False,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _GENERATE_DOC_TEMPLATES_HELPER.translate_project_error(exc)
        payload.setdefault(
            "suggestion",
            "Set project context or provide valid project configuration before generating templates.",
        )
        payload.setdefault("reminders", [])
        return payload

    effective_repo_root = _resolve_effective_repo_root(logging_context, base_dir=base_dir)
    try:
        await asyncio.to_thread(ensure_downstream_seed_assets, effective_repo_root)
    except Exception as exc:
        logger.warning("Downstream seed/adopt skipped for %s: %s", effective_repo_root, exc)

    templates: Dict[str, str] = {}
    if legacy_fallback:
        templates = await load_templates(repo_root=effective_repo_root)

    # INTELLIGENT PARAMETER HANDLING: Support custom context with bulletproof error recovery
    try:
        if custom_context is not None:
            # If custom_context is provided, use it for enhanced template rendering
            if isinstance(custom_context, dict):
                # Merge with base context
                base_context = substitution_context(project_name, author, repo_root=effective_repo_root)
                base_context.update(custom_context)
                render_context = base_context
            else:
                # Try to convert to dict if it's not already
                render_context = substitution_context(project_name, author, repo_root=effective_repo_root)
                logger.warning("custom_context should be a dict, got %s", type(custom_context).__name__)
        else:
            render_context = substitution_context(project_name, author, repo_root=effective_repo_root)
    except Exception as e:
        # Graceful fallback if context handling fails
        render_context = substitution_context(project_name, author, repo_root=effective_repo_root)
        logger.warning("Error handling custom_context: %s. Using base context.", e)

    engine_error: Exception | None = None
    try:
        engine = Jinja2TemplateEngine(
            project_root=effective_repo_root,
            project_name=project_name,
            security_mode="sandbox",
        )
    except Exception as exc:  # pragma: no cover - initialization rarely fails
        engine = None
        engine_error = exc
        logger.error("Failed to initialize Jinja2 template engine: %s", exc)

    if engine is None and not legacy_fallback:
        return {
            "ok": False,
            "error": f"Failed to initialize Jinja2 template engine: {engine_error}",
        }
    if validate_only and engine is None:
        return {
            "ok": False,
            "error": "Validation requires the Jinja2 template engine. Enable legacy_fallback only for emergency writes.",
        }

    selected = _select_documents(documents)

    # Treat legacy overwrite as opt-in force, but gate overwrites behind force for safety.
    force_overwrite = bool(force or overwrite)

    project_root_for_docs = effective_repo_root

    written: List[str] = []
    skipped: List[str] = []
    protected: List[str] = []
    template_metadata: Dict[str, Any] = {}
    validation_results: Dict[str, Any] = {}
    template_directories_info: List[Dict[str, str]] = []
    available_templates: List[str] = []
    all_templates_valid = True

    if include_template_metadata and engine:
        template_directories_info = engine.describe_template_directories()
        available_templates = engine.list_templates()
    output_dir = _target_directory(project_name, base_dir, project_root=project_root_for_docs)
    metadata_context = dict(render_context)
    metadata_context["project_docs_dir"] = str(output_dir)
    metadata_context["PROJECT_DOCS_DIR"] = str(output_dir)
    if not validate_only:
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

    for key, filename in OUTPUT_FILENAMES:
        if key not in selected:
            continue
        template_name = f"documents/{TEMPLATE_FILENAMES[key]}"
        rendered = None
        metadata_payload = _metadata_for(key, project_name, metadata_context)

        if engine:
            validation_result = engine.validate_template(template_name)
            if validation_result:
                validation_results[template_name] = validation_result
                if not validation_result.get("valid", False):
                    all_templates_valid = False
                    if not validate_only:
                        error_payload = _GENERATE_DOC_TEMPLATES_HELPER.error_response(
                            f"Template validation failed for {template_name}",
                            extra={
                                "template": template_name,
                                "validation": validation_result,
                            },
                        )
                        return _GENERATE_DOC_TEMPLATES_HELPER.apply_context_payload(error_payload, logging_context)
        if include_template_metadata and engine:
            template_metadata[key] = {
                "template": template_name,
                "info": engine.get_template_info(template_name),
            }

        if validate_only:
            continue

        if engine:
            try:
                rendered = engine.render_template(template_name, metadata=metadata_payload)
            except TemplateEngineError as template_error:
                logger.warning("Jinja2 rendering failed for %s: %s", template_name, template_error)
                if not legacy_fallback:
                    error_payload = _GENERATE_DOC_TEMPLATES_HELPER.error_response(
                        f"Jinja2 rendering failed for {template_name}: {template_error}",
                        extra={"template": template_name},
                    )
                    return _GENERATE_DOC_TEMPLATES_HELPER.apply_context_payload(error_payload, logging_context)

        if rendered is None:
            if not legacy_fallback:
                error_payload = _GENERATE_DOC_TEMPLATES_HELPER.error_response(
                    f"No rendered output generated for {template_name}",
                    extra={"template": template_name},
                )
                return _GENERATE_DOC_TEMPLATES_HELPER.apply_context_payload(error_payload, logging_context)
            template_body = templates.get(key)
            if not template_body:
                source_name = TEMPLATE_FILENAMES[key]
                error_payload = _GENERATE_DOC_TEMPLATES_HELPER.error_response(
                    f"Template missing: {source_name}",
                )
                return _GENERATE_DOC_TEMPLATES_HELPER.apply_context_payload(error_payload, logging_context)
            rendered = _render_template(template_body, render_context)
        path = output_dir / filename

        # Always protect existing progress log (never overwrite)
        if key == "progress_log" and path.exists():
            protected.append(str(path))
            continue

        if force_overwrite or not path.exists():
            await asyncio.to_thread(_write_template, path, rendered, force_overwrite, project_root_for_docs)
            written.append(str(path))

            # Record baseline hash for doc lifecycle tracking
            try:
                content_hash = hashlib.sha256(rendered.encode('utf-8')).hexdigest()
                _PROJECT_REGISTRY.record_doc_update(
                    project_name,
                    doc=key,
                    action="template_created",
                    before_hash=content_hash,  # Set baseline
                    after_hash=content_hash,   # Same = pristine
                )
            except Exception:
                pass  # Best-effort: Don't fail template generation
        else:
            skipped.append(str(path))

    if validate_only:
        response: Dict[str, Any] = {
            "ok": all_templates_valid,
            "validation": validation_results,
            "directory": str(output_dir),
        }
        if include_template_metadata:
            response["template_metadata"] = {
                "documents": template_metadata,
                "directories": template_directories_info,
                "available_templates": available_templates,
            }
        return _GENERATE_DOC_TEMPLATES_HELPER.apply_context_payload(response, logging_context)

    response: Dict[str, Any] = {
        "ok": True,
        "files": written,
        "skipped": skipped,
        "protected": protected,
        "directory": str(output_dir),
        "force_overwrite": force_overwrite,
    }
    if validation_results:
        response["validation"] = validation_results
    if include_template_metadata:
        response["template_metadata"] = {
            "documents": template_metadata,
            "directories": template_directories_info,
            "available_templates": available_templates,
        }
    return _GENERATE_DOC_TEMPLATES_HELPER.apply_context_payload(response, logging_context)


def _path_has_suffix(path: Path, suffix: Tuple[str, ...]) -> bool:
    parts = path.parts
    return len(parts) >= len(suffix) and tuple(parts[-len(suffix):]) == suffix


def _resolve_effective_repo_root(logging_context: Any, *, base_dir: str | None) -> Path:
    try:
        if logging_context.project and logging_context.project.get("root"):
            return Path(str(logging_context.project["root"])).resolve()
    except Exception:
        pass

    if base_dir:
        base_path = Path(base_dir).expanduser().resolve()
        canonical_suffix = tuple(settings.dev_plans_base.parts)
        legacy_suffix = ("docs", "dev_plans")
        suffixes = (canonical_suffix, legacy_suffix)

        # base_dir points at docs root: <repo>/.scribe/docs/dev_plans or <repo>/docs/dev_plans
        for suffix in suffixes:
            if _path_has_suffix(base_path, suffix):
                return base_path.parents[len(suffix) - 1].resolve()

        # base_dir points at docs project slug dir:
        # <repo>/.scribe/docs/dev_plans/<slug> or <repo>/docs/dev_plans/<slug>
        for suffix in suffixes:
            if _path_has_suffix(base_path.parent, suffix):
                return base_path.parent.parents[len(suffix) - 1].resolve()

        return base_path

    return settings.project_root.resolve()


def _target_directory(project_name: str, base_dir: str | None, *, project_root: Path) -> Path:
    slug = slugify_project_name(project_name)
    canonical_suffix = tuple(settings.dev_plans_base.parts)
    legacy_suffix = ("docs", "dev_plans")
    if base_dir:
        base_path = Path(base_dir)
        if not base_path.is_absolute():
            base_path = project_root / base_path
        base_path = base_path.resolve()

        # If caller already points at a project docs directory, avoid re-nesting.
        if base_path.name == slug and (
            _path_has_suffix(base_path.parent, canonical_suffix)
            or _path_has_suffix(base_path.parent, legacy_suffix)
        ):
            return base_path

        # If caller points at a supported docs base, append slug.
        if _path_has_suffix(base_path, canonical_suffix) or _path_has_suffix(base_path, legacy_suffix):
            return base_path / slug

        # Treat base_dir as repo root by default.
        return (base_path / settings.dev_plans_base / slug).resolve()

    return (project_root / settings.dev_plans_base / slug).resolve()


def _render_template(template: str, context: Dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    rendered = re.sub(r"\{\{[^{}]+\}\}", "TBD", rendered)
    return rendered


def _write_template(path: Path, content: str, overwrite: bool, repo_root: Path | None = None) -> None:
    _effective_root = repo_root or settings.project_root
    if overwrite and path.exists():
        # Create centralized backup directory
        from datetime import datetime, timezone
        backup_dir = _effective_root / ".scribe" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate path-preserving filename
        try:
            relative_path = path.relative_to(_effective_root)
        except ValueError:
            # File is outside repo root, use last 3 components
            relative_path = Path(*path.parts[-3:])

        # Replace directory separators with __
        path_parts = list(relative_path.parts)
        if len(path_parts) > 1:
            dir_prefix = "__".join(path_parts[:-1])
            filename = path_parts[-1]
            backup_name = f"{dir_prefix}__{filename}"
        else:
            backup_name = relative_path.name

        # Add timestamp and .bak extension
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
        backup_filename = f"{backup_name}.overwrite-{timestamp}.bak"
        backup_path = backup_dir / backup_filename

        # Copy to backup location instead of rename
        import shutil
        shutil.copy2(path, backup_path)

    with path.open("w", encoding="utf-8") as handle:
        handle.write(content)

    # Fire-and-forget sync to remote object store (sync context).
    try:
        from scribe_mcp.object_store import should_sync as _should_sync
        if _should_sync(path, _effective_root):
            from scribe_mcp.object_store import sync_file_to_store
            import asyncio
            loop = asyncio.get_running_loop()
            task = loop.create_task(sync_file_to_store(path, content, _effective_root))
            from scribe_mcp.server import background_tasks
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
    except RuntimeError:
        pass  # No running event loop — skip sync.
    except Exception:
        pass


def _select_documents(documents: Iterable[str] | None) -> List[str]:
    """
    Normalize requested documents.

    Accepts:
    - None -> all documents
    - Iterable[str]
    - JSON string list (e.g., '[\"architecture\",\"checklist\"]')
    - Comma-separated string (e.g., 'architecture,checklist')
    """
    if documents is None:
        return [key for key, _ in OUTPUT_FILENAMES]

    # Convert string payloads from MCP into a list
    if isinstance(documents, str):
        raw = documents.strip()
        parsed: Iterable[str] | None = None
        # Try JSON array
        if raw.startswith("[") and raw.endswith("]"):
            try:
                import json

                data = json.loads(raw)
                if isinstance(data, list):
                    parsed = data
            except Exception:
                parsed = None
        # Fallback to comma-separated
        if parsed is None:
            parsed = [part.strip() for part in raw.split(",") if part.strip()]
        documents = parsed

    normalized = {str(doc).strip().lower() for doc in documents or []}
    valid = [key for key, _ in OUTPUT_FILENAMES if key in normalized]

    # If nothing matched, default to all to avoid silent no-op
    if not valid:
        return [key for key, _ in OUTPUT_FILENAMES]
    return valid


MetadataBuilder = Callable[[str, Dict[str, str]], Dict[str, Any]]


def _metadata_for(doc_key: str, project_name: str, context: Dict[str, str]) -> Dict[str, Any]:
    builder = METADATA_BUILDERS.get(doc_key)
    if builder:
        meta = builder(project_name, context)
    else:
        meta = {}

    # Carry through author/time from render context so regenerated docs reflect caller metadata.
    if "author" in context:
        meta.setdefault("author", context["author"])
    if "date_utc" in context:
        meta.setdefault("last_updated", context["date_utc"])
    return meta


def _architecture_metadata(project_name: str, context: Dict[str, str]) -> Dict[str, Any]:
    project_root = context.get("project_root", "project")
    project_docs_dir = context.get("project_docs_dir")
    directory_structure = (
        str(Path(project_docs_dir))
        if project_docs_dir
        else str(Path(project_root) / settings.dev_plans_base / slugify_project_name(project_name))
    )
    return {
        "summary": f"Architecture guide for {project_name}.",
        "version": "Draft v0.1",
        "status": "Draft",
        "problem_statement": {
            "context": f"{project_name} needs a reliable documentation system.",
            "goals": [
                "Eliminate silent failures",
                "Improve template flexibility",
            ],
            "non_goals": ["Define UI/UX beyond documentation"],
            "success_metrics": [
                "All manage_docs operations verified",
                "Templates easy to customize",
            ],
        },
        "requirements": {
            "functional": [
                "Atomic document updates",
                "Jinja2 templates with inheritance",
            ],
            "non_functional": [
                "Backwards-compatible file layout",
                "Sandboxed template rendering",
            ],
            "assumptions": [
                "Filesystem read/write access",
                "Python runtime available",
            ],
            "risks": [
                "User edits outside manage_docs",
                "Template misuse causing errors",
            ],
        },
        "architecture_overview": {
            "summary": "Document manager orchestrates template rendering and writes.",
            "components": [
                {
                    "name": "Doc Manager",
                    "description": "Validates sections and applies atomic writes.",
                    "interfaces": "manage_docs tool",
                    "notes": "Provides verification and logging.",
                },
                {
                    "name": "Template Engine",
                    "description": "Renders templates via Jinja2 with sandboxing.",
                    "interfaces": "Jinja2 environment",
                    "notes": "Supports project/local overrides.",
                },
            ],
            "data_flow": "User -> manage_docs -> template engine -> filesystem/database.",
            "external_integrations": "SQLite mirror, git history.",
        },
        "subsystems": [
            {
                "name": "Doc Change Pipeline",
                "purpose": "Coordinate apply/verify steps.",
                "interfaces": "Atomic writer, storage backend",
                "notes": "Async aware",
                "error_handling": "Rollback on verification failure",
            }
        ],
        "directory_structure": directory_structure,
        "data_storage": {
            "datastores": ["Filesystem markdown", "SQLite mirror"],
            "indexing": "FTS for sections",
            "migrations": "Sequential migrations tracked in storage layer",
        },
        "testing_strategy": {
            "unit": "Template rendering + doc ops",
            "integration": "manage_docs tool exercises real files",
            "manual": "Project review after each release",
            "observability": "Structured logging via doc_updates log",
        },
        "deployment": {
            "environments": "Local development",
            "release": "Git commits drive deployment",
            "config": "Project-specific .scribe settings",
            "ownership": "Doc management team",
        },
        "open_questions": [
            {
                "item": "Should templates support conditionals per phase?",
                "owner": "Docs Lead",
                "status": "TODO",
                "notes": "Evaluate after initial rollout.",
            }
        ],
        "references": ["PROGRESS_LOG.md", "ARCHITECTURE_GUIDE.md"],
        "appendix": "Generated via generate_doc_templates.",
    }


def _phase_plan_metadata(project_name: str, context: Dict[str, str]) -> Dict[str, Any]:
    return {
        "summary": f"Execution roadmap for {project_name}.",
        "phases": [],
        "milestones": [],
    }


def _checklist_metadata(project_name: str, context: Dict[str, str]) -> Dict[str, Any]:
    return {
        "summary": f"Acceptance checklist for {project_name}.",
        "sections": [],
    }


def _log_metadata(label: str) -> MetadataBuilder:
    def builder(project_name: str, _: Dict[str, str]) -> Dict[str, Any]:
        return {
            "summary": f"{label} for {project_name}.",
            "is_rotation": False,
        }

    return builder


METADATA_BUILDERS: Dict[str, MetadataBuilder] = {
    "architecture": _architecture_metadata,
    "phase_plan": _phase_plan_metadata,
    "checklist": _checklist_metadata,
    "progress_log": _log_metadata("Progress log"),
    "doc_log": _log_metadata("Documentation updates"),
    "security_log": _log_metadata("Security log"),
    "bug_log": _log_metadata("Bug log"),
}
