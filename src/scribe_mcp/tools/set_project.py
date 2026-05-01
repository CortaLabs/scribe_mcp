"""Tool for registering or selecting the active project."""

from __future__ import annotations

import logging
import os
import re
import asyncio
from time import perf_counter as _pc

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.config.downstream_assets import ensure_downstream_seed_assets
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp.tool_contracts import stateful_local_tool
from scribe_mcp import reminders
from scribe_mcp.tools.agent_project_utils import (
    ensure_agent_session,
    resolve_authoritative_write_scope,
)
from scribe_mcp.tools.project_utils import (
    list_project_configs,
    slugify_project_name,
)
from scribe_mcp.utils.slug import normalize_project_input
from scribe_mcp.tools.base.parameter_normalizer import normalize_dict_param, normalize_list_param
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.project_registry import get_runtime_project_registry
from scribe_mcp.shared.project_utils import detect_project_state, merge_project_inventory_authority
from scribe_mcp.shared.tool_runtime import (
    resolve_context_authoritative_session_key,
    validate_repo_root_grant,
)
from scribe_mcp.shared.repo_authority import (
    RepoAuthorityResolutionError,
    build_repo_authority_snapshot,
    resolve_authorized_project_root,
)
from scribe_mcp.runtime_timing_envelope import build_runtime_efficiency_budget_status


class _SetProjectHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_SET_PROJECT_HELPER = _SetProjectHelper()
_PROJECT_REGISTRY = get_runtime_project_registry()
_SESSION_DEBUG_ENABLED = os.environ.get("SCRIBE_SESSION_DEBUG", "").lower() in {"1", "true", "yes", "on"}
_TARGETED_REMINDER_REFRESH_TIMEOUT_SECONDS = 0.5
_POST_BIND_CONTEXT_REFRESH_TIMEOUT_SECONDS = 1.0


class ProjectRootAuthorizationError(ValueError):
    """Structured root-authorization failure surfaced by set_project."""

    def __init__(self, message: str, *, payload: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.payload = dict(payload or {})


def _trusted_workspace_user(_caller_user: Optional[str]) -> Optional[str]:
    """Resolve workspace mapping user from server-owned environment only."""
    return os.environ.get("SCRIBE_USER")


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
            # Support both legacy "[YYYY-MM-DD...]" lines and current
            # "[emoji] [YYYY-MM-DD ...]" progress-log entries.
            patterns = (
                re.compile(r'^\[\d{4}-\d{2}-\d{2}'),
                re.compile(r'^\[[^\]]+\]\s+\[\d{4}-\d{2}-\d{2}'),
            )
            return sum(
                1
                for line in content.split('\n')
                if any(pattern.match(line.strip()) for pattern in patterns)
            )
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


async def _build_existing_project_activity(
    *,
    project: Dict[str, Any],
    inventory: Dict[str, Any],
    project_state: str,
    entry_count: int,
    backend: Any,
    project_record: Any,
    registry_info: Any,
) -> Dict[str, Any]:
    """Build readable existing-project activity from authoritative sources first."""
    activity: Dict[str, Any] = {}
    progress_entries = int(
        inventory.get("docs", {})
        .get("progress", {})
        .get("entries", 0)
        or 0
    )
    total_entries = int(entry_count or 0)
    per_log_counts: Dict[str, int] = {}
    last_entry_at = None

    if backend and project_record and hasattr(backend, "count_entries"):
        log_filters = {
            "progress": ["progress"],
            "doc_updates": ["doc_updates"],
            "bugs": ["bugs", "bug"],
            "security": ["security"],
        }
        for label, log_types in log_filters.items():
            try:
                count = await backend.count_entries(
                    project_record,
                    filters={"log_type": log_types},
                )
            except Exception:
                count = 0
            if count:
                per_log_counts[label] = int(count)

        try:
            recent_entries = await backend.fetch_recent_entries(
                project=project_record,
                limit=1,
                filters={"log_type": ["progress", "doc_updates", "bugs", "bug", "security"]},
            )
            if recent_entries:
                last_entry_at = recent_entries[0].get("ts")
        except Exception:
            last_entry_at = None

    if total_entries == 0 and progress_entries > 0:
        total_entries = progress_entries
    if not per_log_counts and progress_entries > 0:
        per_log_counts["progress"] = progress_entries

    status = project.get("status") or project.get("lifecycle_status")
    backend_is_sqlite = bool(
        backend and "sqlite" in backend.__class__.__name__.lower()
    )
    if not status and backend_is_sqlite and registry_info and getattr(registry_info, "status", None):
        status = registry_info.status
    if not status:
        status = "planning" if project_state == "NEW" else "in_progress"

    authoritative_activity = merge_project_inventory_authority(
        {
            "status": status,
            "total_entries": total_entries,
            "per_log_counts": per_log_counts,
            "last_entry_at": last_entry_at,
        },
        registry_info=registry_info,
        backend_available=bool(backend),
    )

    activity["status"] = authoritative_activity.get("status")
    activity["total_entries"] = int(authoritative_activity.get("total_entries") or 0)
    if authoritative_activity.get("per_log_counts"):
        activity["per_log_counts"] = authoritative_activity["per_log_counts"]
    if authoritative_activity.get("last_entry_at"):
        activity["last_entry_at"] = authoritative_activity["last_entry_at"]

    return activity


async def _check_slug_collision(
    name: str,
    backend: Any,
    repo_root: Path,
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
    try:
        existing = await backend.fetch_project(name, repo_root=str(repo_root.resolve()))
    except TypeError:
        existing = await backend.fetch_project(name)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Unable to validate project name collision due to storage lookup failure: {exc}",
            "error_code": "storage_lookup_failed",
        }
    if existing:
        return None  # Same name update is allowed, not a collision

    # Query all projects to check for slug collisions
    try:
        all_projects = await backend.list_projects()
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Unable to validate project name collision due to project listing failure: {exc}",
            "error_code": "storage_lookup_failed",
        }

    resolved_repo_root = repo_root.resolve()

    # Check if any existing project in this repo has the same canonical slug but different raw name
    for project in all_projects:
        project_repo_root = getattr(project, "repo_root", None)
        if not project_repo_root:
            continue
        try:
            if Path(project_repo_root).resolve() != resolved_repo_root:
                continue
        except Exception:
            continue
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


async def _resolve_existing_project_alias_name(
    name: str,
    backend: Any,
    repo_root: Path,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Prefer the existing repo-scoped project name for canonical alias matches.

    Legacy data can contain both `my-project` and `my_project` rows for the same
    repository. `fetch_project(name, repo_root=...)` resolves by canonical
    project_key, so if that returns a different raw name we should bind to the
    existing stored name instead of attempting a second insert/update cycle.
    """
    if not name or not backend or not hasattr(backend, "fetch_project"):
        return name, None

    try:
        existing = await backend.fetch_project(name, repo_root=str(repo_root.resolve()))
    except TypeError:
        return name, None
    except Exception:
        return name, None

    if not existing:
        return name, None

    existing_name = getattr(existing, "name", None)
    if not existing_name or existing_name == name:
        return name, None

    requested_slug = normalize_project_input(name)
    existing_slug = normalize_project_input(str(existing_name))
    if not requested_slug or requested_slug != existing_slug:
        return name, None

    return str(existing_name), {
        "requested_name": name,
        "resolved_name": str(existing_name),
        "canonical_slug": requested_slug,
        "reason": "repo_scoped_canonical_alias_match",
    }


def _project_names_share_canonical_alias(left: str, right: str) -> bool:
    left_slug = normalize_project_input(left)
    right_slug = normalize_project_input(right)
    return bool(left_slug and right_slug and left_slug == right_slug)


async def _targeted_post_bind_refresh(
    *,
    project: Dict[str, Any],
    tool_name: str,
    state_snapshot: Dict[str, Any],
    agent_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Fetch post-bind reminders without a full context re-resolution."""
    async def _fetch_reminders() -> List[Dict[str, Any]]:
        try:
            return await reminders.get_reminders(
                project,
                tool_name=tool_name,
                state=state_snapshot,
                agent_id=agent_id,
            )
        except TypeError:
            return await reminders.get_reminders(
                project,
                tool_name=tool_name,
                state=state_snapshot,
            )

    try:
        return await asyncio.wait_for(
            _fetch_reminders(),
            timeout=_TARGETED_REMINDER_REFRESH_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("Timed out during targeted post-bind reminder refresh; returning no reminders")
        return []
    except Exception:
        return []


@app.tool(**stateful_local_tool(title="Set Project Context", tags=("projects", "context", "write")))
async def set_project(
    agent: str = "Codex",  # REQUIRED: Agent name for session identity (e.g., "Coder-1", "ResearchAgent")
    name: str = "",
    root: str = "",  # REQUIRED: Repository root path
    grant_id: Optional[str] = None,
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
    # Remote identity (injected by Council proxy)
    _scribe_user: Optional[str] = None,  # User identity for workspace scoping in Docker/SSE
) -> Dict[str, Any]:
    """Register the project (if needed) and mark it as the current context.

    IMPORTANT:
    - The `agent` parameter is REQUIRED and must match what you use in subsequent
      tool calls (append_entry, etc.) for session isolation to work.
    - The `root` parameter is REQUIRED and specifies the repository root path.
    """
    _t0 = _pc()
    _timings: list[tuple[str, float]] = []
    def _mark(label: str) -> None:
        _timings.append((label, (_pc() - _t0) * 1000))
    def _log_timings() -> None:
        total = (_pc() - _t0) * 1000
        parts = []
        prev = 0.0
        for lbl, cum in _timings:
            delta = cum - prev
            parts.append(f"{lbl}={delta:.0f}ms")
            prev = cum
        logger.warning("PERF set_project total=%.0fms | %s", total, " | ".join(parts))

    state_snapshot = await server_module.state_manager.record_tool("set_project")
    _mark("record_tool")

    # agent is now REQUIRED - use it as agent_id for internal tracking
    agent_id = agent
    trusted_workspace_user = _trusted_workspace_user(_scribe_user)

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
    if agent_identity and hasattr(agent_identity, "update_agent_activity"):
        await agent_identity.update_agent_activity(
            agent_id, "set_project", {"project_name": name, "expected_version": expected_version}
        )
    _mark("update_agent_activity")

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

    _mark("prepare_context")
    defaults = _normalise_defaults(defaults or {}, emoji, agent_id)
    try:
        current_context = server_module.get_execution_context()
    except Exception:
        current_context = None
    enrolled_first_party_roots = tuple(
        str(Path(str(project.get("root", ""))).expanduser().resolve())
        for project in list_project_configs().values()
        if project.get("root")
    )
    authority_snapshot = build_repo_authority_snapshot(
        current_context=current_context,
        app=app,
        scribe_user=trusted_workspace_user,
        authoritative_session_key=resolve_context_authoritative_session_key(current_context),
        enrolled_first_party_roots=enrolled_first_party_roots,
    )
    try:
        resolved_root, root_authorization = await _resolve_root(
            root,
            authority_snapshot,
            skip_validation,
            grant_id=grant_id,
            storage_backend=server_module.storage_backend,
            scribe_user=trusted_workspace_user,
        )
    except ProjectRootAuthorizationError as exc:
        return _SET_PROJECT_HELPER.apply_context_payload(
            _SET_PROJECT_HELPER.error_response(
                str(exc),
                extra=exc.payload,
            ),
            base_context,
        )

    # Detect if a path mapping occurred (for metadata).
    from scribe_mcp.config.paths import map_client_root as _mcr

    _, client_root_original = _mcr(root or str(authority_snapshot.verified_binding_root or ""), user=trusted_workspace_user)
    # client_root_original is non-None only when a mapping happened.

    alias_resolution: Optional[Dict[str, Any]] = None
    backend = server_module.storage_backend
    if backend:
        name, alias_resolution = await _resolve_existing_project_alias_name(
            name,
            backend,
            resolved_root,
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

    _mark("resolve_paths")
    if resolved_root.exists() and not resolved_root.is_dir():
        return _SET_PROJECT_HELPER.apply_context_payload(
            _SET_PROJECT_HELPER.error_response("Project root must be a directory."),
            base_context,
        )
    if not resolved_root.exists():
        if not auto_create_dirs:
            return _SET_PROJECT_HELPER.apply_context_payload(
                _SET_PROJECT_HELPER.error_response(
                    "Project root does not exist and auto_create_dirs is disabled."
                ),
                base_context,
            )
        resolved_root.mkdir(parents=True, exist_ok=True)

    try:
        ensure_downstream_seed_assets(resolved_root)
    except Exception as exc:
        logger.warning("Downstream asset bootstrap skipped for '%s': %s", resolved_root, exc)

    # Bootstrap documentation scaffolds when missing
    doc_result = await _ensure_documents(name, author, overwrite_docs, resolved_root, docs_dir, agent_id)
    _mark("ensure_documents")
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

    # Preserve original client root when server-side mapping occurred.
    if client_root_original:
        project_data.setdefault("meta", {})
        project_data["meta"]["client_root"] = client_root_original
    if alias_resolution:
        project_data.setdefault("meta", {})
        project_data["meta"]["alias_resolution"] = alias_resolution

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

    _mark("build_project_data")
    # Create/upsert project in database first
    project_record = None
    if backend:
        # Check for slug collisions before creating new project
        collision = await _check_slug_collision(name, backend, resolved_root)
        if collision:
            return _SET_PROJECT_HELPER.apply_context_payload(collision, base_context)

        _mark("check_slug_collision")
        import json as _json
        try:
            project_record = await backend.upsert_project(
                name=name,
                repo_root=str(resolved_root),
                progress_log_path=str(resolved_log),
                docs_json=_json.dumps(docs),  # Persist docs mapping to DB
                bridge_id=bridge_id,
                bridge_managed=bridge_managed,
            )
        except Exception as exc:
            exc_text = str(exc)
            duplicate_alias_conflict = (
                "idx_scribe_projects_project_key_unique" in exc_text
                or "scribe_projects_name_key" in exc_text
            )
            if not duplicate_alias_conflict:
                raise

            retry_name, retry_alias_resolution = await _resolve_existing_project_alias_name(
                name,
                backend,
                resolved_root,
            )
            if retry_name == name:
                raise

            name = retry_name
            project_data["name"] = name
            alias_resolution = alias_resolution or retry_alias_resolution
            if alias_resolution:
                project_data.setdefault("meta", {})
                project_data["meta"]["alias_resolution"] = alias_resolution

            project_record = await backend.upsert_project(
                name=name,
                repo_root=str(resolved_root),
                progress_log_path=str(resolved_log),
                docs_json=_json.dumps(docs),
                bridge_id=bridge_id,
                bridge_managed=bridge_managed,
            )

        _mark("upsert_project")
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

        _mark("project_registry")
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

                # Collect operations for batching
                dev_plan_ops = []
                for plan_type, path_str in core_docs.items():
                    if not path_str:
                        continue
                    path_obj = _Path(path_str)
                    if not path_obj.exists():
                        continue
                    dev_plan_ops.append({
                        "project_id": project_record.id,
                        "project_name": name,
                        "plan_type": plan_type,
                        "file_path": str(path_obj),
                        "version": "1.0",
                        "metadata": {"source": "set_project"},
                    })

                if dev_plan_ops:
                    # Use execute_batch if available (RemoteStorageBackend), else sequential
                    if hasattr(backend, "execute_batch"):
                        await backend.execute_batch([  # type: ignore[attr-defined]
                            {"operation": "upsert_dev_plan", "args": op}
                            for op in dev_plan_ops
                        ])
                    else:
                        for op in dev_plan_ops:
                            await backend.upsert_dev_plan(**op)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("dev_plans upsert failed in set_project: %s", exc)

    _mark("upsert_dev_plans")
    # Use AgentContextManager for agent-scoped project context
    agent_manager = server_module.get_agent_context_manager()
    session_id: Optional[str] = None
    mirror_global = False
    context_session_id: Optional[str] = None
    stable_session_id: Optional[str] = None
    compatibility_path: Optional[str] = None
    authoritative_scope = {
        "resolved_scope": None,
        "authoritative_session_id": None,
        "scope_resolution_source": "none",
    }
    write_side_effects: Dict[str, Any] = {
        "authoritative_session_id": None,
        "scope_resolution_source": "none",
        "global_mirror": {"enabled": False, "reason": None, "performed": False},
        "compatibility_writes": [],
    }
    context = None
    try:
        context, context_meta = server_module.get_execution_context(
            recovery_mode="none",
            include_metadata=True,
        )
        if context:
            context_session_id = context.session_id
            # PHASE 1 INTEGRATION: Get stable session from ExecutionContext
            stable_session_id = getattr(context, 'stable_session_id', None)
        _ = context_meta
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

        except Exception as e:
            # Fallback to legacy behavior if agent context fails
            logger.warning("Agent context management failed: %s", e)
            logger.warning("  Falling back to state_manager-only write path")
            compatibility_path = "agent_context_failure"
    authoritative_scope = resolve_authoritative_write_scope(
        context=context,
        agent_session_id=session_id,
    )
    authoritative_session_id = authoritative_scope.get("authoritative_session_id")
    if authoritative_session_id:
        project_data["session_id"] = authoritative_session_id
    write_side_effects["authoritative_session_id"] = authoritative_session_id
    write_side_effects["scope_resolution_source"] = authoritative_scope.get("scope_resolution_source")

    if not authoritative_session_id and os.environ.get("SCRIBE_ALLOW_SET_PROJECT_GLOBAL_COMPAT", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        mirror_global = True
        compatibility_path = compatibility_path or "explicit_global_compat_env"
        write_side_effects["global_mirror"] = {
            "enabled": True,
            "reason": compatibility_path,
            "performed": False,
        }
    elif not authoritative_session_id and context is None:
        mirror_global = True
        compatibility_path = compatibility_path or "no_runtime_context_global_compat"
        write_side_effects["global_mirror"] = {
            "enabled": True,
            "reason": compatibility_path,
            "performed": False,
        }
    # Mirror project data into JSON state; global current_project only updates for legacy fallback.

    _mark("agent_context_manager")
    state = await server_module.state_manager.set_current_project(
        name,
        project_data,
        agent_id=agent_id,
        session_id=authoritative_session_id,
        resolved_scope=authoritative_scope.get("resolved_scope"),
        mirror_global=mirror_global,
        skip_upsert=True,  # Already upserted at line 417
    )
    if state is None:
        logger.warning("StateManager.set_current_project returned None; reloading state snapshot.")
        state = await server_module.state_manager.load()
    _mark("state_set_current_project")
    if authoritative_session_id:
        await server_module.state_manager.set_session_mode(
            authoritative_session_id,
            "project",
        )
    _mark("state_set_session_mode")
    backend = server_module.storage_backend
    if backend:
        session_key = authoritative_session_id
        if session_key:
            await server_module.router_context_manager.cache_project_binding(
                session_key,
                name,
            )
            if _SESSION_DEBUG_ENABLED:
                logger.debug(
                    "set_project authoritative session binding | session_key=%s project=%s stable_session_id=%s context_session_id=%s",
                    session_key,
                    name,
                    stable_session_id,
                    context_session_id,
                )
        if mirror_global:
            write_side_effects["global_mirror"]["performed"] = True
            write_side_effects["compatibility_writes"].append("global_mirror")
        _mark("backend_session_ops")
        if agent_id and hasattr(backend, "upsert_agent_recent_project"):
            # NO SILENT ERRORS - agent tracking must work
            await backend.upsert_agent_recent_project(agent_id, name)
    _mark("upsert_agent_recent")
    recent_projects = list(state.recent_projects)

    # Handle readable format with SITREP formatters
    if format == "readable":
        context_after = base_context
        try:
            context_after = await asyncio.wait_for(
                _SET_PROJECT_HELPER.prepare_context(
                    tool_name="set_project",
                    agent_id=agent_id,
                    explicit_project=name,
                    require_project=False,
                    state_snapshot=state_snapshot,
                ),
                timeout=_POST_BIND_CONTEXT_REFRESH_TIMEOUT_SECONDS,
            )
        except ProjectResolutionError:
            context_after = base_context
        except TimeoutError:
            logger.warning(
                "Timed out during set_project post-bind context refresh; using base context"
            )
            context_after = base_context
        _mark("prepare_context_after")
        from scribe_mcp.utils.response import default_formatter

        # Compute docs_were_generated BEFORE count_entries so we can skip the call for new projects.
        # doc_result is set earlier (from _ensure_documents) and does not depend on count_entries.
        # Note: _ensure_documents returns "generated" key (list of generated doc types)
        docs_were_generated = bool(doc_result.get("generated") or doc_result.get("files"))

        # Detect project state using hash-based logic (fixes BUG-001)
        # Use backend.count_entries for accurate count instead of file parsing
        if docs_were_generated:
            # New project — no entries exist yet, skip remote call
            entry_count = 0
        elif backend and project_record:
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
        state, sitrep_message = detect_project_state(
            project_data,
            entry_count,
            str(resolved_log),
            docs_were_generated
        )
        is_new = (state == "NEW")
        readable_project_data = dict(project_data)
        readable_project_data["root_authorization"] = root_authorization

        if is_new:
            # NEW PROJECT SITREP
            docs_created = {
                "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
                "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
                "checklist": str(docs_dir / "CHECKLIST.md"),
                "progress_log": str(resolved_log)
            }

            readable_content = default_formatter.format_project_sitrep_new(
                readable_project_data,
                docs_created
            )

            response = {
                "ok": True,
                "project": project_data,
                "is_new": True,
                "docs_created": docs_created,
                "readable_content": readable_content
            }

            _mark("format_new_sitrep")
            _log_timings()
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

            activity = await _build_existing_project_activity(
                project=project_data,
                inventory=inventory,
                project_state=state,
                entry_count=entry_count,
                backend=backend,
                project_record=project_record,
                registry_info=registry_info,
            )

            readable_content = default_formatter.format_project_sitrep_existing(
                readable_project_data,
                inventory,
                activity
            )

            response = {
                "ok": True,
                "project": project_data,
                "is_new": False,
                "inventory": inventory,
                "activity": activity,
                "root_authorization": root_authorization,
                "readable_content": readable_content
            }

            _mark("format_existing_sitrep")
            _log_timings()
            return await default_formatter.finalize_tool_response(
                response,
                format="readable",
                tool_name="set_project"
            )



    def _build_timing_breakdown_ms() -> Dict[str, float]:
        timing_breakdown_ms: Dict[str, float] = {}
        prev = 0.0
        for lbl, cum in _timings:
            timing_breakdown_ms[lbl] = round(cum - prev, 3)
            prev = cum
        if _timings:
            timing_breakdown_ms["total_ms"] = round(_timings[-1][1], 3)
        return timing_breakdown_ms
    # For structured/compact formats, use existing logic
    response: Dict[str, Any] = {
        "ok": True,
        "project": project_data,
        "recent_projects": recent_projects,
        "generated": doc_result.get("files", []),
        "skipped": doc_result.get("skipped", []),
        "side_effects": write_side_effects,
        "root_authorization": root_authorization,
        "timing": {"set_project_phase_ms": {}},
        "scope_resolution": {
            "source": write_side_effects.get("scope_resolution_source"),
            "authoritative_session_id": write_side_effects.get("authoritative_session_id"),
            "compatibility_writes": list(write_side_effects.get("compatibility_writes", [])),
            "global_mirror_performed": bool(
                (write_side_effects.get("global_mirror") or {}).get("performed")
            ),
        },
        **({"warnings": validation.get("warnings", [])} if validation.get("warnings") else {}),
    }
    targeted_reminders = await _targeted_post_bind_refresh(
        project=project_data,
        tool_name="set_project",
        state_snapshot=state_snapshot,
        agent_id=agent_id,
    )
    _mark("targeted_refresh_after")
    if targeted_reminders:
        response["reminders"] = list(targeted_reminders)
    set_project_phase_ms = _build_timing_breakdown_ms()
    response["timing"]["set_project_phase_ms"] = set_project_phase_ms
    response["timing"]["budget_status"] = build_runtime_efficiency_budget_status(
        startup_phases_ms=None,
        set_project_phase_ms=set_project_phase_ms,
        dispatch_path=None,
        startup_profile=None,
        budget_thresholds=getattr(settings, "runtime_efficiency_budgets", None),
    )

    _mark("format_structured")
    _log_timings()
    return _SET_PROJECT_HELPER.apply_context_payload(response, base_context)


def _get_context_repo_root_details() -> Dict[str, Any]:
    try:
        context = server_module.get_execution_context()
    except Exception:
        context = None
    if not context or not getattr(context, "repo_root", None):
        return {
            "trusted_path": None,
            "claimed_path": None,
            "provenance": "missing",
            "authoritative_session_key": None,
        }
    repo_root_provenance = None
    try:
        resolved_scope = getattr(context, "resolved_scope", None)
        scope_provenance = getattr(resolved_scope, "provenance", None)
        repo_root_provenance = getattr(scope_provenance, "repo_root", None)
        if repo_root_provenance is None:
            raw_scope_provenance = getattr(context, "scope_provenance", None)
            if isinstance(raw_scope_provenance, dict):
                repo_root_provenance = raw_scope_provenance.get("repo_root")
    except Exception:
        repo_root_provenance = None
    authoritative_session_key = resolve_context_authoritative_session_key(context)
    try:
        resolved_path = Path(str(context.repo_root)).expanduser().resolve()
    except (TypeError, ValueError):
        return {
            "trusted_path": None,
            "claimed_path": None,
            "provenance": "invalid",
            "authoritative_session_key": authoritative_session_key,
        }

    provenance_label = str(repo_root_provenance or "unknown").strip().lower() or "unknown"
    if provenance_label == "verified":
        return {
            "trusted_path": resolved_path,
            "claimed_path": None,
            "provenance": provenance_label,
            "authoritative_session_key": authoritative_session_key,
        }
    if provenance_label in {"claimed", "inferred", "unknown", "anonymous", "missing"}:
        return {
            "trusted_path": None,
            "claimed_path": resolved_path,
            "provenance": provenance_label,
            "authoritative_session_key": authoritative_session_key,
        }
    return {
        "trusted_path": None,
        "claimed_path": resolved_path,
        "provenance": provenance_label,
        "authoritative_session_key": authoritative_session_key,
    }


async def _resolve_root(
    root: Optional[str],
    authority_snapshot: Any,
    skip_validation: bool,
    grant_id: Optional[str],
    storage_backend: Any,
    scribe_user: Optional[str] = None,
) -> tuple[Path, Dict[str, Any]]:
    base = settings.project_root.resolve()

    async def _validate_grant(
        backend: Any,
        grant: str,
        repo_root: str,
        session_key: Optional[str],
    ) -> tuple[bool, dict[str, Any]]:
        return await validate_repo_root_grant(
            storage_backend=backend,
            grant_id=grant,
            repo_root=repo_root,
            authoritative_session_key=session_key,
        )

    try:
        return await resolve_authorized_project_root(
            root=root,
            skip_validation=skip_validation,
            grant_id=grant_id,
            snapshot=authority_snapshot,
            base_root=base,
            scribe_user=scribe_user,
            validate_repo_root_grant=_validate_grant,
            storage_backend=storage_backend,
        )
    except RepoAuthorityResolutionError as exc:
        raise ProjectRootAuthorizationError(str(exc), payload=exc.payload) from exc


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
        if _project_names_share_canonical_alias(other_name, name) and paths["root"] == root_resolved:
            continue
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
