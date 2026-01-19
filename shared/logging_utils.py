"""Shared logging utilities for Scribe MCP tools.

These helpers consolidate repeated normalization, project resolution, and
response-building logic that previously lived in multiple tool modules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, MutableMapping, Optional, Sequence, Tuple
from collections.abc import Mapping

from scribe_mcp import reminders

META_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(slots=True)
class LoggingContext:
    """Resolved context information required by most logging tools."""

    tool_name: str
    project: Optional[Dict[str, Any]]
    recent_projects: List[str]
    state_snapshot: Dict[str, Any]
    reminders: List[Dict[str, Any]]
    agent_id: Optional[str] = None


class ProjectResolutionError(RuntimeError):
    """Raised when a project is required but cannot be resolved."""

    def __init__(self, message: str, recent_projects: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.recent_projects = list(recent_projects or [])


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
            backend = getattr(server_module, "storage_backend", None)
            if backend and hasattr(backend, "get_session_project"):
                # Prefer stable_session_id for deterministic project resolution
                session_key = getattr(exec_context, "stable_session_id", None) or getattr(exec_context, "session_id", None)
                if session_key:
                    project_name = await backend.get_session_project(session_key)
                    # Debug logging
                    from pathlib import Path
                    from datetime import datetime, timezone
                    debug_log = Path("/tmp/scribe_session_debug.log")
                    with open(debug_log, "a") as f:
                        f.write(f"\n=== get_session_project query ===\n")
                        f.write(f"timestamp: {datetime.now(timezone.utc).isoformat()}\n")
                        f.write(f"session_key: {session_key}\n")
                        f.write(f"project_name from DB: {project_name}\n")
                    if project_name:
                        # Try database registry first (projects may not have JSON config files)
                        # CRITICAL FIX (Bug Fix #3): Resolve via StorageBackend APIs (not ad-hoc sqlite3.connect()
                        # or direct SQL in tool code) to avoid connection isolation issues in WAL mode.
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

                                with open(debug_log, "a") as f:
                                    f.write(
                                        f"session_project from storage backend: {session_project.get('name')}\n"
                                    )
                            else:
                                # Fallback to JSON config files for legacy projects
                                from scribe_mcp.tools.project_utils import load_project_config

                                session_project = load_project_config(project_name)
                                with open(debug_log, "a") as f:
                                    f.write(
                                        f"session_project from config: {session_project.get('name') if session_project else None}\n"
                                    )
                        except Exception as e:
                            with open(debug_log, "a") as f:
                                f.write(f"ERROR resolving session project: {e}\n")
                            # Fallback to JSON config on error
                            from scribe_mcp.tools.project_utils import load_project_config
                            session_project = load_project_config(project_name)
            if not session_project:
                state = await server_module.state_manager.load()
                # Prefer stable_session_id for deterministic project resolution
                session_key_fallback = getattr(exec_context, "stable_session_id", None) or getattr(exec_context, "session_id", None)
                session_project = state.get_session_project(session_key_fallback)
                # Debug logging
                from pathlib import Path
                from datetime import datetime, timezone
                debug_log = Path("/tmp/scribe_session_debug.log")
                with open(debug_log, "a") as f:
                    f.write(f"\n=== get_session_project FALLBACK ===\n")
                    f.write(f"timestamp: {datetime.now(timezone.utc).isoformat()}\n")
                    f.write(f"session_key_fallback: {session_key_fallback}\n")
                    f.write(f"session_project from state: {session_project.get('name') if session_project else None}\n")

            # NOTE: Session projects are explicitly set via set_project() - trust them.
            # Cross-repo session projects are allowed since the user deliberately set them.
            # Repo scoping only applies to auto-detected fallback projects (lines 284+).

            if session_project:
                project = dict(session_project)
                recent_projects = [project.get("name")] if project.get("name") else []
                if state is None:
                    state = await server_module.state_manager.load()
                for name in state.recent_projects:
                    if name and name not in recent_projects:
                        recent_projects.append(name)
        except Exception:
            pass

    # EXPLICIT PROJECT OVERRIDE: If caller specifies a project, use it (cross-project support).
    # This takes precedence over session project to enable agents targeting other projects.
    if explicit_project:
        backend = getattr(server_module, "storage_backend", None)
        record = None
        if backend and hasattr(backend, "fetch_project"):
            try:
                record = await backend.fetch_project(explicit_project)
            except Exception:
                record = None

        if record:
            project = {
                "name": record.name,
                "root": record.repo_root,
                "progress_log": record.progress_log_path,
            }
            if getattr(record, "docs_json", None):
                try:
                    project["docs"] = json.loads(record.docs_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            recent_projects = [project["name"]]
        else:
            from scribe_mcp.tools.project_utils import load_project_config  # Lazy import.

            explicit_resolved = load_project_config(explicit_project)
            if explicit_resolved:
                project = explicit_resolved
                recent_projects = [project["name"]]
            # If explicit project not found, fall through to other resolution methods

    # Primary path: agent-specific context if an agent_id is available.
    if agent_id and not project:
        from scribe_mcp.tools.agent_project_utils import get_agent_project_data  # Imported lazily to avoid circular import.

        project, recent_projects = await get_agent_project_data(agent_id)

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
        )

    # Project mode with an ExecutionContext should never fall back to global state.
    if exec_context and getattr(exec_context, "mode", None) == "project" and not project:
        if require_project:
            raise ProjectResolutionError(
                "No session-scoped project configured. Invoke set_project for this session.",
                recent_projects,
            )
        return LoggingContext(
            tool_name=tool_name,
            project=None,
            recent_projects=recent_projects,
            state_snapshot=state_snapshot,
            reminders=[],
            agent_id=agent_id,
        )

    # Final fallback: use the state's active project snapshot (legacy/no context).
    # WARNING: This path uses GLOBAL state - only safe when scoped to current repo.
    if not project and not exec_context:
        from scribe_mcp.tools.project_utils import load_active_project, load_project_config  # Lazy import.

        active_project, active_name, recent = await load_active_project(server_module.state_manager)

        # REPO SCOPING: Only use global fallback if project belongs to current repo
        if active_project and active_project.get("root"):
            try:
                from scribe_mcp.config.repo_config import get_current_repo_config
                current_repo_root, _ = get_current_repo_config()
                project_root = Path(active_project["root"]).resolve()
                if project_root != current_repo_root:
                    # Project is from different repo - don't use it
                    # Log this for debugging
                    debug_log = Path("/tmp/scribe_session_debug.log")
                    with open(debug_log, "a") as f:
                        from datetime import datetime, timezone
                        f.write(f"\n=== GLOBAL FALLBACK BLOCKED (cross-repo) ===\n")
                        f.write(f"timestamp: {datetime.now(timezone.utc).isoformat()}\n")
                        f.write(f"active_project: {active_name}\n")
                        f.write(f"project_root: {project_root}\n")
                        f.write(f"current_repo: {current_repo_root}\n")
                    active_project = None
                    active_name = None
            except Exception:
                pass  # If repo detection fails, allow fallback (backwards compat)

        project = active_project
        if recent_projects:
            # Ensure active project recents are appended without duplicates.
            for name in recent:
                if name not in recent_projects:
                    recent_projects.append(name)
        else:
            recent_projects = list(recent)
        if not project and active_name:
            # When an explicit project was requested but not found, attempt config lookup.
            project = load_project_config(active_name)

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
    if cache is not None and log_key in cache:
        return cache[log_key]

    definition = log_config_module.get_log_definition(log_key)
    path = log_config_module.resolve_log_path(project, definition)

    if cache is not None:
        cache[log_key] = (path, definition)

    return path, definition


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
