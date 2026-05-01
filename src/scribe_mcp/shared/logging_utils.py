"""Shared logging utilities for Scribe MCP tools.

These helpers consolidate repeated normalization, project resolution, and
response-building logic that previously lived in multiple tool modules.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, MutableMapping, Optional, Sequence, Tuple
from collections.abc import Mapping

from scribe_mcp import reminders
from scribe_mcp.shared.session_utils import get_canonical_session_key
from scribe_mcp.utils.slug import normalize_project_input

META_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")

# Legacy compatibility anchors for downstream tests that validate historical
# query behavior from earlier direct-SQL implementations.
LEGACY_PROJECT_SELECT_SQL = "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects"
LEGACY_DOCS_JSON_PARSE_ANCHOR = 'json.loads(row["docs_json"])'
_SESSION_DEBUG_ENABLED = os.environ.get("SCRIBE_SESSION_DEBUG", "").lower() in {"1", "true", "yes", "on"}
_SESSION_DEBUG_LOG_PATH = Path(
    os.environ.get("SCRIBE_SESSION_DEBUG_LOG", "/tmp/scribe_session_debug.log")
)
logger = logging.getLogger(__name__)


def _session_debug_trace(title: str, lines: Sequence[str]) -> None:
    """Optional file-backed session tracing; disabled by default in production."""
    if not _SESSION_DEBUG_ENABLED:
        return
    logger.debug("%s | %s", title, " | ".join(lines))
    try:
        with open(_SESSION_DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(f"\n=== {title} ===\n")
            for line in lines:
                handle.write(f"{line}\n")
    except OSError:
        logger.debug("Session debug trace write failed for '%s'", title)


@dataclass(slots=True)
class LoggingContext:
    """Resolved context information required by most logging tools."""

    tool_name: str
    project: Optional[Dict[str, Any]]
    recent_projects: List[str]
    state_snapshot: Dict[str, Any]
    reminders: List[Dict[str, Any]]
    agent_id: Optional[str] = None
    resolution_source: str = "unresolved"
    fallback_used: bool = False
    fallback_chain: List[str] | None = None
    denied_fallback_attempts: List[str] | None = None
    compatibility_usage: Dict[str, Any] | None = None


class ProjectResolutionError(RuntimeError):
    """Raised when a project is required but cannot be resolved."""

    def __init__(self, message: str, recent_projects: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.recent_projects = list(recent_projects or [])


def build_resolution_metadata(
    context: LoggingContext,
    *,
    include_project: bool = True,
) -> Dict[str, Any]:
    """Create a consistent, readable resolution payload for tool responses."""
    source = context.resolution_source or "unresolved"
    fallback_used = bool(context.fallback_used)
    fallback_chain = list(context.fallback_chain or [])
    summary = (
        f"Resolved via '{source}'"
        if not fallback_used
        else f"Resolved via '{source}' with recovery chain: {', '.join(fallback_chain)}"
    )

    payload: Dict[str, Any] = {
        "resolution_source": source,
        "fallback_used": fallback_used,
        "fallback_chain": fallback_chain,
        "resolution_summary": summary,
    }
    denied_fallback_attempts = list(context.denied_fallback_attempts or [])
    if denied_fallback_attempts:
        payload["denied_fallback_attempts"] = denied_fallback_attempts
    if isinstance(context.compatibility_usage, dict):
        payload["compatibility_usage"] = dict(context.compatibility_usage)
    if include_project:
        payload["project"] = context.project.get("name") if context.project else None
    return payload


async def resolve_logging_context(
    *,
    tool_name: str,
    server_module,
    agent_id: Optional[str] = None,
    explicit_project: Optional[str] = None,
    require_project: bool = True,
    state_snapshot: Optional[Dict[str, Any]] = None,
    reminder_variables: Optional[Dict[str, Any]] = None,
    operation_status: Optional[str] = None,
    recovery_mode: Optional[str] = None,
) -> LoggingContext:
    """Resolve the active project and reminders for logging tools.

    Args:
        tool_name: Name of the invoking tool (used for reminders + logging).
        server_module: Reference to ``scribe_mcp.server`` module (provides state).
        agent_id: Optional agent identifier for agent-scoped project resolution.
        explicit_project: Optional project name override (as used by query tools).
        require_project: If True, raise ``ProjectResolutionError`` when no project found.
        state_snapshot: Optional state returned from ``state_manager.record_tool`` to avoid
            duplicate recording. When omitted the helper will record the tool automatically.
        recovery_mode: Optional compatibility recovery selector. Ordinary resolution is
            fail-closed; compatibility fallback branches only run when explicitly selected.
    """
    if state_snapshot is None:
        state_snapshot = await server_module.state_manager.record_tool(tool_name)

    if agent_id is None and hasattr(server_module, "get_agent_identity"):
        try:
            agent_identity = server_module.get_agent_identity()
            if agent_identity:
                agent_id = await agent_identity.get_or_create_agent_id()
        except Exception:
            agent_id = None

    project: Optional[Dict[str, Any]] = None
    recent_projects: List[str] = []
    resolution_source = "unresolved"
    fallback_used = False
    fallback_chain: List[str] = []
    denied_fallback_attempts: List[str] = []
    selected_recovery_mode = str(recovery_mode or "none").strip().lower()

    release_profile = os.environ.get("SCRIBE_RELEASE_PROFILE", "internal").strip().lower()
    public_release = release_profile == "public"
    authorized_project_names: set[str] = set()

    def allow_recovery(mode: str) -> bool:
        if public_release and mode in {
            "compat_state_current_project",
            "compat_active_project",
            "compat_recent_project",
        }:
            denied_marker = f"{mode}:public_release_blocked"
            if denied_marker not in denied_fallback_attempts:
                denied_fallback_attempts.append(denied_marker)
            return False
        return selected_recovery_mode in {mode, "compat_all"}
    explicit_requested = bool(explicit_project and str(explicit_project).strip())
    explicit_not_found = False
    exec_context = None
    if hasattr(server_module, "get_execution_context"):
        try:
            exec_context = server_module.get_execution_context()
        except Exception:
            exec_context = None

    # Primary path: session-scoped project resolution (project mode only).
    if exec_context and getattr(exec_context, "mode", None) == "project":
        try:
            session_project = None
            state = None
            backend_session_lookup_available = False
            backend_session_lookup_attempted = False
            backend = getattr(server_module, "storage_backend", None)
            if backend and hasattr(backend, "get_session_project"):
                backend_session_lookup_available = True
                # Canonical precedence follows the shared session utility unless
                # the stable id is an old prebinding key. Prebinding allocations
                # are provisional; once an execution session is present it is the
                # authoritative binding for project-mode logging.
                canonical_session_key = get_canonical_session_key(exec_context)
                execution_session_id = getattr(exec_context, "session_id", None)
                session_keys: List[str] = []
                if (
                    canonical_session_key
                    and "prebinding" in str(canonical_session_key)
                    and execution_session_id
                ):
                    candidates = (execution_session_id, canonical_session_key)
                else:
                    candidates = (canonical_session_key, execution_session_id)
                for candidate_key in candidates:
                    if candidate_key and str(candidate_key) not in session_keys:
                        session_keys.append(str(candidate_key))

                for session_key in session_keys:
                    backend_session_lookup_attempted = True
                    project_name = await backend.get_session_project(session_key)
                    from datetime import datetime, timezone

                    _session_debug_trace(
                        "get_session_project query",
                        [
                            f"timestamp: {datetime.now(timezone.utc).isoformat()}",
                            f"session_key: {session_key}",
                            f"project_name from DB: {project_name}",
                        ],
                    )
                    if not project_name:
                        continue
                    # Try database registry first (projects may not have JSON config files)
                    # CRITICAL FIX (Bug Fix #3): Resolve via StorageBackend APIs (not ad-hoc sqlite connections)
                    # or direct SQL in tool code) to avoid connection isolation issues in WAL mode.
                    # Legacy compatibility note: if a backend only exposes low-level access,
                    # use backend._fetchone(...) on the shared connection instead of opening
                    # a new sqlite connection.
                    try:
                        record = None
                        if hasattr(backend, "fetch_project"):
                            record = await backend.fetch_project(project_name)
                        if record:
                            session_project = {
                                "name": record.name,
                                "root": record.repo_root,
                                "progress_log": record.progress_log_path,
                            }

                            if getattr(record, "docs_json", None):
                                try:
                                    session_project["docs"] = json.loads(record.docs_json)
                                except (json.JSONDecodeError, TypeError):
                                    pass

                            _session_debug_trace(
                                "get_session_project resolved",
                                [f"session_project from storage backend: {session_project.get('name')}"],
                            )
                        else:
                            # Fallback to JSON config files for legacy projects
                            from scribe_mcp.tools.project_utils import load_project_config

                            session_project = load_project_config(project_name, allow_fallback=False)
                            _session_debug_trace(
                                "get_session_project resolved",
                                [f"session_project from config: {session_project.get('name') if session_project else None}"],
                            )
                    except Exception as e:
                        _session_debug_trace(
                            "get_session_project error",
                            [f"ERROR resolving session project: {e}"],
                        )
                        # Fallback to JSON config on error
                        from scribe_mcp.tools.project_utils import load_project_config
                        session_project = load_project_config(project_name, allow_fallback=False)
                    if session_project:
                        break
            if not session_project and (
                not backend_session_lookup_available
                or not backend_session_lookup_attempted
            ):
                state = await server_module.state_manager.load()
                # Canonical fallback follows write-path authority first.
                session_key_fallback = get_canonical_session_key(exec_context)
                session_project = state.get_session_project(session_key_fallback)
                from datetime import datetime, timezone
                _session_debug_trace(
                    "get_session_project FALLBACK",
                    [
                        f"timestamp: {datetime.now(timezone.utc).isoformat()}",
                        f"session_key_fallback: {session_key_fallback}",
                        f"session_project from state: {session_project.get('name') if session_project else None}",
                    ],
                )

            # NOTE: Session projects are explicitly set via set_project() - trust them.
            # Cross-repo session projects are allowed since the user deliberately set them.
            # Repo scoping only applies to auto-detected fallback projects (lines 284+).

            if session_project:
                project = dict(session_project)
                resolution_source = "session_binding"
                project_name = project.get("name")
                if project_name:
                    authorized_project_names.add(str(project_name))
                    alias = normalize_project_input(str(project_name))
                    if alias:
                        authorized_project_names.add(alias)
                recent_projects = [project.get("name")] if project.get("name") else []
                if state is None:
                    state = await server_module.state_manager.load()
                for name in state.recent_projects:
                    if name and name not in recent_projects:
                        recent_projects.append(name)
        except Exception as exc:
            logger.warning(
                "Session-bound logging context resolution failed for tool '%s': %s",
                tool_name,
                exc,
            )

    # EXPLICIT PROJECT OVERRIDE: If caller specifies a project, use it (cross-project support).
    # This takes precedence over session project to enable agents targeting other projects.
    if explicit_requested:
        explicit_name = str(explicit_project).strip()
        explicit_alias = normalize_project_input(explicit_name)
        allow_set_project_rebind = tool_name == "set_project"
        if (
            not allow_set_project_rebind
            and exec_context
            and getattr(exec_context, "mode", None) == "project"
            and authorized_project_names
        ):
            if explicit_name not in authorized_project_names and (
                not explicit_alias or explicit_alias not in authorized_project_names
            ):
                raise ProjectResolutionError(
                    f"Explicit project override '{explicit_project}' does not match the session-bound active project.",
                    recent_projects,
                )
        elif public_release and not allow_set_project_rebind:
            if explicit_name not in authorized_project_names and (
                not explicit_alias or explicit_alias not in authorized_project_names
            ):
                raise ProjectResolutionError(
                    f"Explicit project override '{explicit_project}' is not authorized for this session.",
                    recent_projects,
                )
        explicit_candidates = [explicit_name]
        if explicit_alias and explicit_alias not in explicit_candidates:
            explicit_candidates.append(explicit_alias)

        backend = getattr(server_module, "storage_backend", None)
        record = None
        if backend and hasattr(backend, "fetch_project"):
            for candidate in explicit_candidates:
                try:
                    record = await backend.fetch_project(candidate)
                except Exception:
                    record = None
                if record:
                    break

            # Fallback: resolve aliases by normalized slug against DB names.
            if (
                not record
                and explicit_alias
                and hasattr(backend, "list_projects")
            ):
                try:
                    records = await backend.list_projects()
                    for candidate_record in records:
                        candidate_name = getattr(candidate_record, "name", "")
                        if normalize_project_input(candidate_name) == explicit_alias:
                            record = candidate_record
                            break
                except Exception:
                    record = None

        if record:
            project = {
                "name": record.name,
                "root": record.repo_root,
                "progress_log": record.progress_log_path,
            }
            resolution_source = "explicit_project"
            if getattr(record, "docs_json", None):
                try:
                    project["docs"] = json.loads(record.docs_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            recent_projects = [project["name"]]
        else:
            from scribe_mcp.tools.project_utils import load_project_config  # Lazy import.

            explicit_resolved = load_project_config(explicit_name, allow_fallback=False)
            if not explicit_resolved and explicit_alias and explicit_alias != explicit_name:
                explicit_resolved = load_project_config(explicit_alias, allow_fallback=False)
            if explicit_resolved:
                project = explicit_resolved
                resolution_source = "explicit_project"
                recent_projects = [project["name"]]
            else:
                explicit_not_found = True

    # Fail hard on unresolved explicit project requests. Never silently fall back
    # to unrelated global/legacy project context.
    if explicit_requested and explicit_not_found:
        if not recent_projects:
            try:
                state = await server_module.state_manager.load()
                recent_projects = list(state.recent_projects)[:10]
            except Exception:
                recent_projects = []

        if require_project:
            raise ProjectResolutionError(
                f"Explicit project '{explicit_project}' was not found. Invoke set_project or pass a valid project name.",
                recent_projects,
            )
        return LoggingContext(
            tool_name=tool_name,
            project=None,
            recent_projects=recent_projects,
            state_snapshot=state_snapshot,
            reminders=[],
            agent_id=agent_id,
            resolution_source="explicit_project_missing",
            fallback_used=False,
            fallback_chain=[],
            denied_fallback_attempts=list(denied_fallback_attempts),
            compatibility_usage={
                "requested": selected_recovery_mode != "none",
                "requested_mode": selected_recovery_mode,
                "applied": False,
            },
        )

    # Primary path: agent-specific context if an agent_id is available.
    if agent_id and not project:
        from scribe_mcp.tools.agent_project_utils import get_agent_project_data  # Imported lazily to avoid circular import.

        project, recent_projects = await get_agent_project_data(agent_id)
        if project:
            resolution_source = "agent_context"

    # Sentinel mode: allow explicit project targeting, but never resolve from global state.
    # If explicit project was provided and resolved, allow it (enables cross-project docs).
    # Dual-write: when sentinel targets a project, also log to sentinel log for audit trail.
    if exec_context and getattr(exec_context, "mode", None) == "sentinel":
        if not recent_projects:
            try:
                state = await server_module.state_manager.load()
                recent_projects = list(state.recent_projects)[:10]
            except Exception:
                recent_projects = []

        # If explicit project was resolved, allow it (cross-project capability)
        if project:
            # Mark for dual-write: sentinel should also log to sentinel log
            state_snapshot["_sentinel_dual_write"] = True
            state_snapshot["_sentinel_target_project"] = project.get("name", "unknown")
            return LoggingContext(
                tool_name=tool_name,
                project=project,
                recent_projects=recent_projects,
                state_snapshot=state_snapshot,
                reminders=[],
                agent_id=agent_id,
                resolution_source=resolution_source,
                fallback_used=fallback_used,
                fallback_chain=list(fallback_chain),
                denied_fallback_attempts=list(denied_fallback_attempts),
                compatibility_usage={
                    "requested": selected_recovery_mode != "none",
                    "requested_mode": selected_recovery_mode,
                    "applied": bool(fallback_used),
                },
            )

        # No explicit project - require_project determines behavior
        if require_project:
            raise ProjectResolutionError(
                "Project resolution forbidden in sentinel mode. Provide explicit 'project' parameter to target a specific project.",
                recent_projects,
            )
        return LoggingContext(
            tool_name=tool_name,
            project=None,
            recent_projects=recent_projects,
            state_snapshot=state_snapshot,
            reminders=[],
            agent_id=agent_id,
            resolution_source="sentinel_mode_no_project",
            fallback_used=False,
            fallback_chain=[],
            denied_fallback_attempts=list(denied_fallback_attempts),
            compatibility_usage={
                "requested": selected_recovery_mode != "none",
                "requested_mode": selected_recovery_mode,
                "applied": False,
            },
        )

    # Project mode should prefer session bindings, but if an explicit active project
    # is already persisted in StateManager, honor it before failing hard. This keeps
    # direct StateManager-driven flows and tests functional without reopening a session.
    if (
        exec_context
        and getattr(exec_context, "mode", None) == "project"
        and not project
        and allow_recovery("compat_state_current_project")
    ):
        recovered_project = None
        try:
            state = await server_module.state_manager.load()
            if state.current_project:
                recovered_project = state.get_project(state.current_project)
                if not recovered_project and hasattr(server_module.state_manager, "_fetch_project"):
                    recovered_project = await server_module.state_manager._fetch_project(state.current_project)  # type: ignore[attr-defined]
                if recovered_project:
                    project = dict(recovered_project)
                    resolution_source = "compat_state_current_project"
                    fallback_used = True
                    fallback_chain.append("compat_state_current_project")
                    recent_projects = [project.get("name")] if project.get("name") else []
                    for name in state.recent_projects:
                        if name and name not in recent_projects:
                            recent_projects.append(name)
        except Exception:
            recovered_project = None

        if not project and require_project:
            raise ProjectResolutionError(
                "No session-scoped project configured. Invoke set_project for this session.",
                recent_projects,
            )
        if not project:
            return LoggingContext(
                tool_name=tool_name,
                project=None,
                recent_projects=recent_projects,
                state_snapshot=state_snapshot,
                reminders=[],
                agent_id=agent_id,
                resolution_source="project_mode_unresolved",
                fallback_used=fallback_used,
                fallback_chain=list(fallback_chain),
                denied_fallback_attempts=list(denied_fallback_attempts),
                compatibility_usage={
                    "requested": selected_recovery_mode != "none",
                    "requested_mode": selected_recovery_mode,
                    "applied": bool(fallback_used),
                },
            )

    # Compatibility hint path: inspect state snapshots for diagnostics only.
    # Do not promote global/recent state into operational authority.
    if not project and not exec_context and allow_recovery("compat_active_project"):
        from scribe_mcp.tools.project_utils import load_active_project, load_project_config  # Lazy import.

        active_project, active_name, recent = await load_active_project(server_module.state_manager)
        if active_project and selected_recovery_mode == "compat_active_project":
            project = dict(active_project)
            resolution_source = "compat_active_project"
            fallback_used = True
            fallback_chain.append("compat_active_project")
        elif active_project:
            resolution_source = "compat_active_project_hint"
            fallback_used = True
            fallback_chain.append("compat_active_project_hint")
        elif active_name:
            resolution_source = "compat_active_project_hint"
            fallback_used = True
            fallback_chain.append("compat_active_project_hint")
        if recent_projects:
            # Ensure active project recents are appended without duplicates.
            for name in recent:
                if name not in recent_projects:
                    recent_projects.append(name)
        else:
            recent_projects = list(recent)
        if not recent_projects and active_name:
            resolved = load_project_config(active_name)
            if resolved and resolved.get("name"):
                recent_projects = [str(resolved["name"])]

    # Compatibility hint path for recent names only; do not rebind authority.
    if not project and recent_projects and allow_recovery("compat_recent_project"):
        backend = getattr(server_module, "storage_backend", None)
        if backend and hasattr(backend, "fetch_project"):
            for candidate in recent_projects[:3]:
                try:
                    record = await backend.fetch_project(candidate)
                except Exception:
                    record = None
                if not record:
                    continue
                resolution_source = "compat_recent_project_hint"
                fallback_used = True
                fallback_chain.append("compat_recent_project_hint")
                break

    if not project and require_project:
        raise ProjectResolutionError(
            "No project configured. Invoke set_project before using this tool.",
            recent_projects,
        )

    reminders_payload: List[Dict[str, Any]] = []
    if project:
        try:
            try:
                reminders_payload = await reminders.get_reminders(
                    project,
                    tool_name=tool_name,
                    state=state_snapshot,
                    agent_id=agent_id,
                    variables=reminder_variables,
                    operation_status=operation_status,
                )
            except TypeError:
                # Backwards compatibility: some tests/patches provide get_reminders without agent_id.
                reminders_payload = await reminders.get_reminders(
                    project,
                    tool_name=tool_name,
                    state=state_snapshot,
                )
        except Exception:
            # Reminders should never block tool execution; ignore failures.
            reminders_payload = []

    return LoggingContext(
        tool_name=tool_name,
        project=project,
        recent_projects=recent_projects,
        state_snapshot=state_snapshot,
        reminders=reminders_payload,
        agent_id=agent_id,
        resolution_source=resolution_source,
        fallback_used=fallback_used,
        fallback_chain=list(fallback_chain),
        denied_fallback_attempts=list(denied_fallback_attempts),
        compatibility_usage={
            "requested": selected_recovery_mode != "none",
            "requested_mode": selected_recovery_mode,
            "applied": bool(fallback_used),
        },
    )


def coerce_metadata_mapping(
    meta: Any,
    *,
    allow_pair_strings: bool = True,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Coerce arbitrary metadata payloads into a dictionary."""
    if meta is None or meta == {}:
        return {}, None

    if isinstance(meta, dict):
        return dict(meta), None

    if isinstance(meta, MutableMapping) or isinstance(meta, Mapping):
        return dict(meta.items()), None

    if hasattr(meta, "items"):
        try:
            return dict(meta.items()), None  # type: ignore[arg-type]
        except Exception:
            pass

    if isinstance(meta, str):
        parsed = _try_parse_json_like(meta)
        if isinstance(parsed, dict):
            return dict(parsed), None
        if isinstance(parsed, list):
            try:
                pairs: List[Tuple[Any, Any]] = []
                for entry in parsed:
                    if isinstance(entry, Sequence) and not isinstance(entry, (str, bytes)) and len(entry) == 2:
                        key, value = entry
                        pairs.append((key, value))
                    else:
                        raise ValueError("Metadata JSON array items must be key/value pairs")
                return {str(key): value for key, value in pairs}, None
            except Exception:
                raw_preview = meta if len(meta) < 120 else f"{meta[:117]}..."
                return {"raw_meta": raw_preview}, "Expected dict when decoding JSON metadata list"
        if allow_pair_strings:
            pairs = _legacy_metadata_pairs(meta, allow_pair_strings=True)
            return {key: value for key, value in pairs}, None
        raw_preview = meta if len(meta) < 120 else f"{meta[:117]}..."
        return {"raw_meta": raw_preview}, "Metadata string must be a JSON object"

    if isinstance(meta, Sequence) and not isinstance(meta, (str, bytes)):
        try:
            pairs_seq: List[Tuple[Any, Any]] = []
            for entry in meta:
                if isinstance(entry, Sequence) and not isinstance(entry, (str, bytes)) and len(entry) == 2:
                    key, value = entry
                    pairs_seq.append((key, value))
                else:
                    raise ValueError("Metadata sequences must contain key/value pairs")
            return {str(key): value for key, value in pairs_seq}, None
        except Exception as exc:
            raw_preview = str(meta)
            if len(raw_preview) > 120:
                raw_preview = f"{raw_preview[:117]}..."
            return {"raw_meta": raw_preview}, str(exc)

    if hasattr(meta, "__dict__"):
        try:
            return {key: value for key, value in vars(meta).items() if not key.startswith("_")}, None
        except Exception:
            pass

    raw_preview = str(meta)
    if len(raw_preview) > 120:
        raw_preview = f"{raw_preview[:117]}..."
    return {"raw_meta": raw_preview}, f"Unsupported metadata payload type: {type(meta).__name__}"


def normalize_metadata(
    meta: Any,
    *,
    allow_pair_strings: bool = True,
) -> Tuple[Tuple[str, str], ...]:
    """Normalise metadata inputs into the append_entry tuple-of-tuples format."""
    if meta is None or meta == {}:
        return ()

    # Use shared parameter normalization utilities when possible.
    if isinstance(meta, str):
        parsed = _try_parse_json_like(meta)
        if isinstance(parsed, dict):
            meta = parsed
        elif isinstance(parsed, list):
            try:
                meta = dict(parsed)  # type: ignore[arg-type]
            except Exception:
                return (("parse_error", "Expected dict when decoding JSON metadata list"),)
        else:
            return _legacy_metadata_pairs(meta, allow_pair_strings)

    if isinstance(meta, tuple):
        # Allow callers to provide the canonical tuple format already.
        try:
            return tuple((str(k), str(v)) for k, v in meta)
        except Exception:
            return (("meta_error", "Invalid metadata tuple"),)

    mapping, error = coerce_metadata_mapping(meta, allow_pair_strings=allow_pair_strings)
    if error and not mapping:
        return (("parse_error", error),)
    if error:
        mapping.setdefault("meta_error", error)

    if not mapping:
        return ()

    try:
        normalised = []
        for key, value in sorted(mapping.items()):
            normalised.append((_sanitize_meta_key(str(key)), _stringify(value)))
        return tuple(normalised)
    except Exception as exc:  # pragma: no cover - defensive catch for unknown edge cases
        return (("meta_error", str(exc)),)
def _try_parse_json_like(value: str) -> Optional[Any]:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _legacy_metadata_pairs(value: str, allow_pair_strings: bool) -> Tuple[Tuple[str, str], ...]:
    if not allow_pair_strings:
        return (("message", value),)

    if "=" in value:
        delimiter = "," if "," in value else " "
        pairs: List[Tuple[str, str]] = []
        for token in value.split(delimiter):
            token = token.strip()
            if not token:
                continue
            if "=" in token:
                key, raw = token.split("=", 1)
                pairs.append((_sanitize_meta_key(key.strip()), _clean_meta_value(raw.strip())))
            else:
                pairs.append(("message", _clean_meta_value(token)))
        if pairs:
            return tuple(pairs)
    return (("message", value),)


def normalize_meta_filters(
    meta_filters: Any,
) -> Tuple[Dict[str, str], Optional[str]]:
    """Normalize metadata filters used by query-style tools."""
    if not meta_filters:
        return {}, None

    if isinstance(meta_filters, str):
        parsed = _try_parse_json_like(meta_filters)
        if isinstance(parsed, dict):
            meta_filters = parsed
        else:
            return {}, "Invalid JSON in meta filters."

    if not isinstance(meta_filters, dict):
        return {}, "Meta filters must be a dictionary."

    normalised: Dict[str, str] = {}
    for key, value in meta_filters.items():
        if key is None:
            return {}, "Meta filter keys cannot be null."
        key_str = str(key).strip()
        if not key_str:
            return {}, "Meta filter keys cannot be empty."
        if not META_KEY_PATTERN.match(key_str):
            return {}, f"Meta filter key '{key}' contains unsupported characters."
        normalised[key_str] = str(value)
    return normalised, None


def clean_list(
    values: Any,
    *,
    coerce_lower: bool = True,
) -> List[str]:
    """Clean list-like input while supporting JSON/string payloads."""
    if values is None or values == []:
        return []

    items: List[str]
    if isinstance(values, str):
        parsed = _try_parse_json_like(values)
        if isinstance(parsed, list):
            values = parsed
        else:
            values = [values]

    if isinstance(values, list):
        items = values
    elif isinstance(values, tuple):
        items = list(values)
    else:
        items = [values]

    cleaned: List[str] = []
    seen = set()
    for entry in items:
        text = str(entry).strip()
        if not text:
            continue
        value = text.lower() if coerce_lower else text
        if value not in seen:
            cleaned.append(value)
            seen.add(value)
    return cleaned


def resolve_log_definition(
    project: Dict[str, Any],
    log_type: str,
    *,
    cache: Optional[MutableMapping[str, Tuple[Path, Dict[str, Any]]]] = None,
) -> Tuple[Path, Dict[str, Any]]:
    """Return the log file path and definition for a given project + log type."""
    from scribe_mcp.config import log_config as log_config_module  # Lazy import.

    log_key = (log_type or "progress").lower()
    project_root = project.get("root")
    cache_key = f"{project_root or ''}:{log_key}"
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    definition = log_config_module.get_log_definition(log_key, repo_root=project_root)
    path = log_config_module.resolve_log_path(project, definition)

    if cache is not None:
        cache[cache_key] = (path, definition)

    return path, definition


def _sanitize_log_field(value: str) -> str:
    """Strip characters that could forge log entries.

    Removes newlines (\\n, \\r) and null bytes (\\x00) to prevent
    log injection attacks where user input could create fake log lines.
    """
    if not isinstance(value, str):
        return str(value)
    return value.replace('\n', ' ').replace('\r', ' ').replace('\x00', '')


def compose_log_line(
    *,
    emoji: str,
    timestamp: str,
    agent: str,
    project_name: str,
    message: str,
    meta_pairs: Tuple[Tuple[str, str], ...],
    entry_id: Optional[str] = None,
) -> str:
    """Compose a formatted log line with metadata pairs."""
    # Sanitize user-controlled fields to prevent log injection
    agent = _sanitize_log_field(agent)
    project_name = _sanitize_log_field(project_name)
    message = _sanitize_log_field(message)

    segments = [
        f"[{emoji}]",
        f"[{timestamp}]",
        f"[Agent: {agent}]",
        f"[Project: {project_name}]",
    ]

    if entry_id:
        segments.append(f"[ID: {entry_id}]")

    segments.append(message)
    base = " ".join(segments)
    if meta_pairs:
        meta_text = "; ".join(f"{key}={value}" for key, value in meta_pairs)
        return f"{base} | {meta_text}"
    return base


def ensure_metadata_requirements(
    definition: Dict[str, Any],
    meta_payload: Dict[str, Any],
) -> Optional[str]:
    """Validate metadata requirements defined in log configuration."""
    required = definition.get("metadata_requirements") or []
    missing = [key for key in required if key not in meta_payload]
    if missing:
        return f"Missing metadata for log entry: {', '.join(missing)}"
    return None


def default_status_emoji(
    *,
    explicit: Optional[str],
    status: Optional[str],
    project: Dict[str, Any],
) -> str:
    """Resolve the emoji that should prefix a log entry."""
    from scribe_mcp.tools.constants import STATUS_EMOJI  # Lazy import.

    if explicit:
        return explicit
    if status:
        emoji = STATUS_EMOJI.get(status) or STATUS_EMOJI.get(status.lower())
        if emoji:
            return emoji
    defaults = project.get("defaults") or {}
    return defaults.get("emoji") or STATUS_EMOJI["info"]


def _sanitize_meta_key(value: str) -> str:
    cleaned = value.replace(" ", "_").replace("|", "").strip()
    return cleaned or "meta_key"


def _clean_meta_value(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").replace("|", " ")


def _stringify(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        return _clean_meta_value(str(value))
    return _clean_meta_value(json.dumps(value, sort_keys=True))
