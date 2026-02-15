"""Tool for registering or selecting the active project."""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp import reminders
from scribe_mcp.tools.agent_project_utils import ensure_agent_session
from scribe_mcp.tools.project_utils import (
    list_project_configs,
    slugify_project_name,
)
from scribe_mcp.utils.slug import normalize_project_input
from scribe_mcp.tools.base.parameter_normalizer import normalize_dict_param, normalize_list_param
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.project_registry import ProjectRegistry
from scribe_mcp.shared.project_utils import detect_project_state


class _SetProjectHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_SET_PROJECT_HELPER = _SetProjectHelper()
_PROJECT_REGISTRY = ProjectRegistry()
_SESSION_DEBUG_ENABLED = os.environ.get("SCRIBE_SESSION_DEBUG", "").lower() in {"1", "true", "yes", "on"}


async def _count_log_entries(progress_log_path: Path) -> int:
    """
    Count entries in progress log file.

    Counts only actual log entries with timestamps, not template headers.

    Args:
        progress_log_path: Path to PROGRESS_LOG.md

    Returns:
        Number of actual entries (lines matching [YYYY-MM-DD pattern)
    """
    if not progress_log_path.exists():
        return 0

    try:
        with open(progress_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # Match only lines starting with timestamp pattern [YYYY-MM-DD
            pattern = re.compile(r'^\[\d{4}-\d{2}-\d{2}')
            return sum(1 for line in content.split('\n') if pattern.match(line.strip()))
    except (OSError, UnicodeError, re.error) as exc:
        logger.warning(
            "Unable to count project log entries from '%s': %s",
            progress_log_path,
            exc,
        )
        return 0


async def _gather_project_inventory(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gather full project inventory for existing project SITREP.

    Returns:
        {
            "docs": {
                "architecture": {"exists": True, "lines": 1274, "modified": False},
                "phase_plan": {"exists": True, "lines": 542, "modified": False},
                "checklist": {"exists": True, "lines": 356, "modified": False},
                "progress": {"exists": True, "entries": 298}
            },
            "custom": {
                "research_files": 3,
                "bugs_present": False,
                "jsonl_files": ["TOOL_LOG.jsonl"]
            }
        }
    """
    from scribe_mcp.utils.response import default_formatter

    progress_log = project.get('progress_log', '')
    if not progress_log or not Path(progress_log).exists():
        return {"docs": {}, "custom": {}}

    dev_plan_dir = Path(progress_log).parent

    result = {"docs": {}, "custom": {}}

    # Check standard documents
    arch_file = dev_plan_dir / "ARCHITECTURE_GUIDE.md"
    if arch_file.exists():
        result["docs"]["architecture"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(arch_file),
            "modified": False  # TODO: Check registry hashes if needed
        }

    phase_file = dev_plan_dir / "PHASE_PLAN.md"
    if phase_file.exists():
        result["docs"]["phase_plan"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(phase_file),
            "modified": False
        }

    checklist_file = dev_plan_dir / "CHECKLIST.md"
    if checklist_file.exists():
        result["docs"]["checklist"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(checklist_file),
            "modified": False
        }

    # Progress log
    prog_file = Path(progress_log)
    if prog_file.exists():
        entry_count = await _count_log_entries(prog_file)
        result["docs"]["progress"] = {
            "exists": True,
            "entries": entry_count
        }

    # Detect custom content
    result["custom"] = default_formatter._detect_custom_content(dev_plan_dir)

    return result


async def _check_slug_collision(
    name: str,
    backend: Any,
) -> Optional[Dict[str, Any]]:
    """Check if a new project name would collide with an existing project's canonical slug.

    Args:
        name: The new project name being created
        backend: Storage backend to query existing projects

    Returns:
        None if no collision, or error dict with collision details if collision detected

    Example:
        If 'my_project' exists and user tries to create 'my-project':
        Returns {"ok": False, "error": "Project 'my-project' would collide with existing project 'my_project'..."}
    """
    # Get canonical slug for the new project name
    canonical_slug = normalize_project_input(name)
    if not canonical_slug:
        return None  # Invalid name, will be caught elsewhere

    # Check if a project with this exact name already exists (update case, not a collision)
    existing = await backend.fetch_project(name)
    if existing:
        return None  # Same name update is allowed, not a collision

    # Query all projects to check for slug collisions
    try:
        all_projects = await backend.list_projects()
    except Exception as exc:
        # If we can't query projects, allow operation to proceed
        # (backend errors should be caught at upsert time)
        return None

    # Check if any existing project has the same canonical slug but different raw name
    for project in all_projects:
        existing_slug = normalize_project_input(project.name)
        if existing_slug == canonical_slug and project.name != name:
            # Collision detected!
            return {
                "ok": False,
                "error": (
                    f"Project '{name}' would collide with existing project '{project.name}' "
                    f"(both normalize to '{canonical_slug}'). "
                    f"Please choose a different name or use the existing project."
                ),
                "collision": {
                    "new_name": name,
                    "existing_name": project.name,
                    "canonical_slug": canonical_slug,
                },
            }

    return None  # No collision detected


@app.tool()
async def set_project(
    agent: str = "Codex",  # REQUIRED: Agent name for session identity (e.g., "Coder-1", "ResearchAgent")
    name: str = "",
    root: str = "",  # REQUIRED: Repository root path
    progress_log: Optional[str] = None,
    defaults: Optional[Dict[str, Any]] = None,
    author: Optional[str] = None,
    overwrite_docs: bool = False,
    expected_version: Optional[int] = None,  # Optimistic concurrency control
    # Advanced parameters
    description: Optional[str] = None,  # Project description
    tags: Optional[List[str]] = None,  # Project tags
    template: Optional[str] = None,  # Custom template name
    auto_create_dirs: bool = True,  # Auto-create missing directories
    skip_validation: bool = False,  # Skip path validation for special cases
    # Reminder and notification settings
    reminder_settings: Optional[Dict[str, Any]] = None,
    notification_config: Optional[Dict[str, Any]] = None,
    reset_reminders: bool = False,
    # Quick emoji/agent settings (for convenience)
    emoji: Optional[str] = None,  # Default emoji for the project
    # Bridge management (Phase 3)
    bridge_id: Optional[str] = None,  # ID of bridge that owns this project
    bridge_managed: bool = False,  # Whether this project is bridge-managed
    # Output formatting
    format: str = "readable",  # Output format: readable, structured, compact
) -> Dict[str, Any]:
    """Register the project (if needed) and mark it as the current context.

    IMPORTANT:
    - The `agent` parameter is REQUIRED and must match what you use in subsequent
      tool calls (append_entry, etc.) for session isolation to work.
    - The `root` parameter is REQUIRED and specifies the repository root path.
    """
    state_snapshot = await server_module.state_manager.record_tool("set_project")

    # agent is now REQUIRED - use it as agent_id for internal tracking
    agent_id = agent

    # Use BaseTool parameter normalization for consistent MCP framework handling
    if isinstance(defaults, str):
        try:
            # Try our standardized normalization first (handles MCP framework JSON serialization)
            normalized_defaults = normalize_dict_param(defaults, "defaults")
            if isinstance(normalized_defaults, dict):
                defaults = normalized_defaults
            else:
                # Fall back to original JSON parsing if normalization fails
                pass
        except ValueError:
            # FALLBACK: Use original JSON parsing logic
            try:
                import json
                defaults = json.loads(defaults)
                if not isinstance(defaults, dict):
                    defaults = {}
            except (json.JSONDecodeError, TypeError):
                defaults = {}

    # Update agent activity tracking
    agent_identity = server_module.get_agent_identity()
    if agent_identity:
        await agent_identity.update_agent_activity(
            agent_id, "set_project", {"project_name": name, "expected_version": expected_version}
        )

    base_context: LoggingContext = await _SET_PROJECT_HELPER.prepare_context(
        tool_name="set_project",
        agent_id=agent_id,
        require_project=False,
        state_snapshot=state_snapshot,
    )

    # Normalize tags parameter if provided
    if isinstance(tags, str):
        try:
            normalized_tags = normalize_list_param(tags, "tags")
            if isinstance(normalized_tags, list):
                tags = normalized_tags
            else:
                tags = [tags]  # Fallback: treat as single item
        except ValueError:
            tags = [tags]  # Fallback: treat as single item

    defaults = _normalise_defaults(defaults or {}, emoji, agent_id)
    context_root = _get_context_repo_root()
    try:
        resolved_root = _resolve_root(root, context_root, skip_validation)
    except ValueError as exc:
        return _SET_PROJECT_HELPER.apply_context_payload(
            _SET_PROJECT_HELPER.error_response(str(exc)),
            base_context,
        )

    docs_dir = _resolve_docs_dir(name, resolved_root)
    try:
        resolved_log = _resolve_log(progress_log, resolved_root, docs_dir)
    except ValueError as exc:
        return _SET_PROJECT_HELPER.apply_context_payload(
            _SET_PROJECT_HELPER.error_response(str(exc)),
            base_context,
        )

    validation = await _validate_project_paths(
        name=name,
        root_path=resolved_root,
        docs_dir=docs_dir,
        progress_log=resolved_log,
    )
    if not validation.get("ok", False):
        return _SET_PROJECT_HELPER.apply_context_payload(validation, base_context)

    resolved_root.mkdir(parents=True, exist_ok=True)

    # Bootstrap documentation scaffolds when missing
    doc_result = await _ensure_documents(name, author, overwrite_docs, resolved_root, docs_dir, agent_id)
    if not doc_result.get("ok", False):
        return _SET_PROJECT_HELPER.apply_context_payload(doc_result, base_context)

    docs = {
        "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
        "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
        "checklist": str(docs_dir / "CHECKLIST.md"),
        "progress_log": str(resolved_log),
    }

    # Compute baseline_hashes for newly generated docs (fixes EXISTING_LEGACY state detection)
    # This allows get_project to distinguish NEW from EXISTING_LEGACY projects
    # Store hashes in _hashes subkey to avoid polluting the docs list
    docs_were_generated = len(doc_result.get("files", [])) > 0
    if docs_were_generated:
        from scribe_mcp.utils.integrity import compute_file_hash
        baseline_hashes = {}
        for doc_type in ["architecture", "phase_plan", "checklist"]:
            doc_path = docs.get(doc_type)
            if doc_path and Path(doc_path).exists():
                try:
                    file_hash, _ = compute_file_hash(doc_path)
                    baseline_hashes[doc_type] = file_hash[:8]  # Short hash for readability
                except Exception:
                    pass  # Skip hash on error
        if baseline_hashes:
            docs["_hashes"] = {
                "baseline_hashes": baseline_hashes,
                "current_hashes": dict(baseline_hashes),  # Initially same as baseline
            }

    project_data = {
        "name": name,
        "root": str(resolved_root),
        "progress_log": str(resolved_log),
        "docs_dir": str(docs_dir),
        "docs": docs,
        "defaults": defaults,
        "author": author or defaults.get("agent") or "Scribe",
        # Optional metadata for richer project views
        "description": description,
        "tags": tags or [],
    }

    # Optional: allow agents to clear reminder cooldowns if they're confused.
    # This is scoped to (project_root + agent_id) to avoid impacting other agents.
    if reset_reminders:
        try:
            cleared = reminders.reset_reminder_cooldowns(
                project_root=str(resolved_root),
                agent_id=agent_id,
            )
            project_data.setdefault("meta", {})
            project_data["meta"]["reminders_reset"] = True
            project_data["meta"]["reminders_reset_count"] = cleared
        except Exception as exc:  # pragma: no cover - defensive
            project_data.setdefault("meta", {})
            project_data["meta"]["reminders_reset_error"] = str(exc)

    # Create/upsert project in database first
    backend = server_module.storage_backend
    project_record = None
    if backend:
        # Check for slug collisions before creating new project
        collision = await _check_slug_collision(name, backend)
        if collision:
            return _SET_PROJECT_HELPER.apply_context_payload(collision, base_context)

        import json as _json
        project_record = await backend.upsert_project(
            name=name,
            repo_root=str(resolved_root),
            progress_log_path=str(resolved_log),
            docs_json=_json.dumps(docs),  # Persist docs mapping to DB
            bridge_id=bridge_id,
            bridge_managed=bridge_managed,
        )

        # Parse docs_json from project_record and populate project_data meta
        if project_record and project_record.docs_json:
            import json
            try:
                docs_metadata = json.loads(project_record.docs_json)
                project_data.setdefault("meta", {})
                project_data["meta"]["docs"] = docs_metadata
            except (json.JSONDecodeError, TypeError):
                # Invalid JSON - silently ignore and continue
                pass

        # Best-effort Project Registry touch for this project (SQLite-first).
        try:
            _PROJECT_REGISTRY.ensure_project(
                project_record,
                description=description,
                tags=tags,
                meta={"source": "set_project"},
            )
            _PROJECT_REGISTRY.touch_access(project_record.name)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ProjectRegistry ensure/touch_access failed in set_project: %s", exc)

        # Populate dev_plans table for core docs so lifecycle rules can see them.
        try:
            if hasattr(backend, "upsert_dev_plan") and project_record:
                from pathlib import Path as _Path

                core_docs = {
                    "architecture": docs.get("architecture"),
                    "phase_plan": docs.get("phase_plan"),
                    "checklist": docs.get("checklist"),
                    "progress_log": docs.get("progress_log"),
                }
                for plan_type, path_str in core_docs.items():
                    if not path_str:
                        continue
                    path_obj = _Path(path_str)
                    if not path_obj.exists():
                        continue
                    await backend.upsert_dev_plan(  # type: ignore[attr-defined]
                        project_id=project_record.id,
                        project_name=name,
                        plan_type=plan_type,
                        file_path=str(path_obj),
                        version="1.0",
                        metadata={"source": "set_project"},
                    )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("dev_plans upsert failed in set_project: %s", exc)

    # Use AgentContextManager for agent-scoped project context
    agent_manager = server_module.get_agent_context_manager()
    session_id: Optional[str] = None
    mirror_global = True
    context_session_id: Optional[str] = None
    stable_session_id: Optional[str] = None
    context = None
    try:
        context = server_module.get_execution_context()
        if context:
            context_session_id = context.session_id
            # PHASE 1 INTEGRATION: Get stable session from ExecutionContext
            stable_session_id = getattr(context, 'stable_session_id', None)
    except Exception:
        context_session_id = None
    if agent_manager:
        try:
            # Ensure agent has an active session, passing stable session if available
            session_id = await ensure_agent_session(agent_id, stable_session_id=stable_session_id)
            if not session_id:
                # Fallback: create simple session with stable session if available
                import uuid
                session_id = await agent_manager.start_session(
                    agent_id,
                    session_id=stable_session_id,  # Use stable session in fallback too
                    metadata={"tool": "set_project"}
                )

            # Set agent's current project with optimistic concurrency
            result = await agent_manager.set_current_project(
                agent_id=agent_id,
                project_name=name,
                session_id=session_id,
                expected_version=expected_version
            )
            if not isinstance(result, dict):
                logger.warning(
                    "AgentContextManager.set_current_project returned non-dict result (%s); using safe defaults.",
                    type(result).__name__,
                )
                result = {}

            # Update project_data with version info from database
            project_data["version"] = result.get("version", 1)
            project_data["updated_by"] = result.get("updated_by", agent_id)
            project_data["session_id"] = result.get("session_id", session_id)
            # Preserve legacy/global behavior when no execution context is bound.
            # Session-scoped calls (with stable or transport session IDs) should
            # stay isolated; context-free calls should still update global state.
            mirror_global = not (stable_session_id or context_session_id)

        except Exception as e:
            # Fallback to legacy behavior if agent context fails
            logger.warning("Agent context management failed: %s", e)
            logger.warning("  Falling back to legacy global state management")
            mirror_global = True
    # Mirror project data into JSON state; global current_project only updates for legacy fallback.

    state = await server_module.state_manager.set_current_project(
        name,
        project_data,
        agent_id=agent_id,
        session_id=context_session_id or session_id,
        mirror_global=mirror_global,
    )
    if state is None:
        logger.warning("StateManager.set_current_project returned None; reloading state snapshot.")
        state = await server_module.state_manager.load()
    await server_module.state_manager.set_session_mode(
        context_session_id or session_id,
        "project",
    )
    backend = server_module.storage_backend
    if backend:
        # CRITICAL: Use stable_session_id (deterministic) instead of context_session_id (unstable UUID)
        session_key = stable_session_id or context_session_id or session_id
        if session_key:
            if hasattr(backend, "set_session_project"):
                # NO SILENT ERRORS - this is THE critical project binding!
                await backend.set_session_project(session_key, name)
                # Update in-memory cache for auto-injection
                await server_module.router_context_manager.cache_project_binding(
                    stable_session_id or session_key,
                    name
                )
                if _SESSION_DEBUG_ENABLED:
                    logger.debug(
                        "set_project session binding | session_key=%s project=%s stable_session_id=%s context_session_id=%s",
                        session_key,
                        name,
                        stable_session_id,
                        context_session_id,
                    )
            if hasattr(backend, "set_session_mode"):
                # NO SILENT ERRORS - mode must be set correctly
                await backend.set_session_mode(session_key, "project")
            if hasattr(backend, "upsert_session"):
                # NO SILENT ERRORS - session data must be persisted
                await backend.upsert_session(
                    session_id=session_key,
                    transport_session_id=getattr(context, "transport_session_id", None),
                    agent_id=agent_id,
                    repo_root=str(resolved_root),
                    mode="project",
                )
        if agent_id and hasattr(backend, "upsert_agent_recent_project"):
            # NO SILENT ERRORS - agent tracking must work
            await backend.upsert_agent_recent_project(agent_id, name)
    recent_projects = list(state.recent_projects)

    try:
        context_after = await _SET_PROJECT_HELPER.prepare_context(
            tool_name="set_project",
            agent_id=agent_id,
            explicit_project=name,
            require_project=False,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError:
        context_after = base_context

    # Handle readable format with SITREP formatters
    if format == "readable":
        from scribe_mcp.utils.response import default_formatter

        # Detect project state using hash-based logic (fixes BUG-001)
        # Use backend.count_entries for accurate count instead of file parsing
        if backend and project_record:
            try:
                entry_count = await backend.count_entries(
                    project_record,
                    filters={"log_type": ["progress", "bugs", "bug", "security"]},
                )
            except TypeError:
                entry_count = await backend.count_entries(project_record)
        else:
            # Fallback to file-based counting if backend unavailable
            progress_log_path = Path(resolved_log)
            entry_count = await _count_log_entries(progress_log_path)

        # Use hash-based detection instead of entry_count for state determination
        # Pass docs_were_generated flag to distinguish NEW vs EXISTING (SPEC-SET-001 fix)
        # Note: _ensure_documents returns "generated" key (list of generated doc types)
        docs_were_generated = bool(doc_result.get("generated") or doc_result.get("files"))
        state, sitrep_message = detect_project_state(
            project_data,
            entry_count,
            str(resolved_log),
            docs_were_generated
        )
        is_new = (state == "NEW")

        if is_new:
            # NEW PROJECT SITREP
            docs_created = {
                "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
                "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
                "checklist": str(docs_dir / "CHECKLIST.md"),
                "progress_log": str(resolved_log)
            }

            readable_content = default_formatter.format_project_sitrep_new(
                project_data,
                docs_created
            )

            response = {
                "ok": True,
                "project": project_data,
                "is_new": True,
                "docs_created": docs_created,
                "readable_content": readable_content
            }

            return await default_formatter.finalize_tool_response(
                response,
                format="readable",
                tool_name="set_project"
            )

        else:
            # EXISTING PROJECT SITREP
            # Gather inventory
            inventory = await _gather_project_inventory(project_data)

            # Get activity from registry (use module-level instance)
            registry_info = _PROJECT_REGISTRY.get_project(name)

            # Build activity summary
            activity = {
                "status": registry_info.status if registry_info else "unknown",
                "total_entries": registry_info.total_entries if registry_info else 0,
                "last_entry_at": registry_info.last_entry_at if registry_info else None
            }

            # Add per-log counts if available
            if hasattr(registry_info, 'meta') and registry_info and registry_info.meta:
                log_counts = registry_info.meta.get('log_entry_counts', {})
                if log_counts:
                    activity["per_log_counts"] = log_counts

            readable_content = default_formatter.format_project_sitrep_existing(
                project_data,
                inventory,
                activity
            )

            response = {
                "ok": True,
                "project": project_data,
                "is_new": False,
                "inventory": inventory,
                "activity": activity,
                "readable_content": readable_content
            }

            return await default_formatter.finalize_tool_response(
                response,
                format="readable",
                tool_name="set_project"
            )

    # For structured/compact formats, use existing logic
    response: Dict[str, Any] = {
        "ok": True,
        "project": project_data,
        "recent_projects": recent_projects,
        "generated": doc_result.get("files", []),
        "skipped": doc_result.get("skipped", []),
        **({"warnings": validation.get("warnings", [])} if validation.get("warnings") else {}),
    }
    if context_after.reminders:
        response["reminders"] = list(context_after.reminders)

    return _SET_PROJECT_HELPER.apply_context_payload(response, context_after)


def _get_context_repo_root() -> Optional[Path]:
    try:
        context = server_module.get_execution_context()
    except Exception:
        context = None
    if not context or not getattr(context, "repo_root", None):
        return None
    try:
        return Path(str(context.repo_root)).expanduser().resolve()
    except (TypeError, ValueError):
        return None


def _resolve_root(root: Optional[str], context_root: Optional[Path], skip_validation: bool) -> Path:
    base = settings.project_root.resolve()
    if not root:
        if context_root and context_root != base:
            return context_root
        if settings.require_explicit_root and not skip_validation:
            raise ValueError(
                "Explicit project root required. Pass root=... or provide context.repo_root."
            )
        return base

    root_path = Path(root).expanduser()
    if not root_path.is_absolute():
        # Preserve relative-path compatibility while allowing roots outside the server repo
        root_path = (base / root_path).resolve()
    else:
        root_path = root_path.resolve()

    return root_path


def _resolve_docs_dir(name: str, root_path: Path) -> Path:
    slug = slugify_project_name(name)
    # Prefer repo-local .scribe dev plans to avoid cluttering repo root, but stay
    # backward compatible: if an existing docs/dev_plans path is present, keep using it.
    scribe_path = (root_path / settings.dev_plans_base / slug).resolve()
    legacy_path = (root_path / "docs" / "dev_plans" / slug).resolve()
    if scribe_path.exists():
        return scribe_path
    if legacy_path.exists():
        return legacy_path
    return scribe_path


def _resolve_log(log: Optional[str], root_path: Path, docs_dir: Path) -> Path:
    if not log:
        return (docs_dir / "PROGRESS_LOG.md").resolve()
    log_path = Path(log)
    if log_path.is_absolute():
        try:
            log_path.relative_to(root_path)
        except ValueError as exc:
            raise ValueError("Progress log must be within the project root.") from exc
        return log_path
    candidate = (root_path / log_path).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("Progress log must be within the project root.") from exc
    return candidate


def _normalise_defaults(
    defaults: Dict[str, Any],
    emoji_param: Optional[str] = None,
    agent_param: Optional[str] = None
) -> Dict[str, Any]:
    mapping = {}

    # Handle emoji from multiple sources (priority: emoji param > defaults > various default_*)
    emoji_value = emoji_param
    if not emoji_value:
        emoji_value = defaults.get("emoji") or defaults.get("default_emoji")
    if emoji_value:
        mapping["emoji"] = emoji_value

    # Handle agent from multiple sources (priority: agent_param > defaults > various default_*)
    agent_value = agent_param
    if not agent_value:
        agent_value = defaults.get("agent") or defaults.get("default_agent")
    if agent_value:
        mapping["agent"] = agent_value

    # Copy other defaults (excluding the ones we've already handled)
    for key, value in defaults.items():
        if (key not in ["emoji", "default_emoji", "agent", "default_agent"]) and value is not None:
            mapping[key] = value

    return mapping


async def _ensure_documents(
    name: str,
    author: Optional[str],
    overwrite: bool,
    root_path: Path,
    docs_dir: Path,
    agent_id: str,
) -> Dict[str, Any]:
    """
    Ensure project documentation exists with proper idempotency.

    This function checks if documentation already exists and skips generation
    unless explicitly requested to overwrite, making it truly idempotent.
    """
    # Check if docs already exist
    doc_files = {
        "architecture": docs_dir / "ARCHITECTURE_GUIDE.md",
        "phase_plan": docs_dir / "PHASE_PLAN.md",
        "checklist": docs_dir / "CHECKLIST.md",
        "progress_log": docs_dir / "PROGRESS_LOG.md",
        "doc_log": docs_dir / "DOC_LOG.md",
        "security_log": docs_dir / "SECURITY_LOG.md",
        "bug_log": docs_dir / "BUG_LOG.md",
    }

    existing_files = []
    missing_files = []

    for doc_type, file_path in doc_files.items():
        if file_path.exists() and file_path.stat().st_size > 0:
            existing_files.append(doc_type)
        else:
            missing_files.append(doc_type)

    # If all files exist and we're not overwriting, skip generation
    if not missing_files and not overwrite:
        return {
            "ok": True,
            "generated": [],
            "skipped": list(doc_files.keys()),
            "status": "docs_already_exist",
            "message": f"All documentation files already exist for project '{name}'"
        }

    # Generate missing files (or all if overwriting)
    from scribe_mcp.tools import generate_doc_templates as doc_templates

    result = await doc_templates.generate_doc_templates(
        agent=agent_id,
        project_name=name,
        author=author,
        overwrite=overwrite,
        # Thread the resolved docs_dir through to guarantee templates land in the
        # same location set_project will return (supports `.scribe` normalization
        # and legacy docs/dev_plans back-compat).
        base_dir=str(docs_dir),
    )

    # Add detailed status about what was done
    if result.get("ok"):
        result["idempotent_status"] = {
            "existing_files": existing_files,
            "missing_files_before": missing_files,
            "overwrite_requested": overwrite
        }

    return result


async def _validate_project_paths(
    *,
    name: str,
    root_path: Path,
    docs_dir: Path,
    progress_log: Path,
) -> Dict[str, Any]:
    """Ensure the provided paths do not collide with existing project definitions."""
    warnings: List[str] = []
    existing = await _gather_known_projects(skip=name)

    root_resolved = root_path.resolve()
    docs_resolved = docs_dir.resolve()
    log_resolved = progress_log.resolve()

    for other_name, paths in existing.items():
        if paths["progress_log"] == log_resolved:
            return {
                "ok": False,
                "error": f"Progress log '{log_resolved}' already belongs to project '{other_name}'.",
            }
        if paths["docs_dir"] == docs_resolved:
            return {
                "ok": False,
                "error": f"Docs directory '{docs_resolved}' already belongs to project '{other_name}'.",
            }
    root_parent = _first_existing_parent(root_resolved)
    if not os.access(root_parent, os.W_OK):
        return {
            "ok": False,
            "error": f"Insufficient permissions to write under '{root_parent}'.",
        }

    docs_parent = _first_existing_parent(docs_resolved)
    if not os.access(docs_parent, os.W_OK):
        return {
            "ok": False,
            "error": f"Insufficient permissions to write docs under '{docs_parent}'.",
        }

    log_parent = _first_existing_parent(log_resolved.parent)
    if not os.access(log_parent, os.W_OK):
        return {
            "ok": False,
            "error": f"Insufficient permissions to write progress log under '{log_parent}'.",
        }

    return {"ok": True, "warnings": warnings}


async def _gather_known_projects(skip: Optional[str]) -> Dict[str, Dict[str, Path]]:
    """Collect registered projects from state and configs."""
    collected: Dict[str, Dict[str, Path]] = {}
    state = await server_module.state_manager.load()
    for project_name, data in state.projects.items():
        if project_name == skip:
            continue
        paths = _extract_paths(data)
        if paths and not _is_temp_path(paths["root"]):
            collected[project_name] = paths

    for project_name, data in list_project_configs().items():
        if project_name == skip or project_name in collected:
            continue
        paths = _extract_paths(data)
        if paths and not _is_temp_path(paths["root"]):
            collected[project_name] = paths
    return collected


def _extract_paths(data: Dict[str, Any]) -> Optional[Dict[str, Path]]:
    try:
        root = Path(data["root"]).resolve()
        log = Path(data["progress_log"]).resolve()
    except (KeyError, TypeError):
        return None

    docs_dir_value = data.get("docs_dir")
    if docs_dir_value:
        docs_dir = Path(docs_dir_value).resolve()
    else:
        doc_entry = data.get("docs") or {}
        progress_path = doc_entry.get("progress_log")
        if progress_path:
            docs_dir = Path(progress_path).resolve().parent
        else:
            docs_dir = log.parent

    return {
        "root": root,
        "docs_dir": docs_dir,
        "progress_log": log,
    }


def _is_temp_path(path: Path) -> bool:
    """Filter out ephemeral tmp test projects to reduce noisy overlaps."""
    parts = {p.lower() for p in path.parts}
    return any(part.startswith("tmp_tests") or part == "tmp_tests" for part in parts)


def _overlaps(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _first_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            break
        current = current.parent
    return current
