"""Entrypoint for the Scribe MCP server."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
from time import perf_counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, Callable, Dict, Optional, Protocol, Union, cast, get_origin, get_args

# Centralised logging -- must run before any getLogger() calls import modules.
from scribe_mcp.config.logging import configure_logging as _configure_logging
_configure_logging()

import logging as _logging
logger = _logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from mcp.server import Server  # type: ignore
    from mcp.server import stdio as mcp_stdio  # type: ignore
    from mcp import types as mcp_types  # type: ignore
    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _MCP_AVAILABLE = False

# Bridge tool extension support (optional)
try:
    from scribe_mcp.bridges.tools import get_tool_registry
    BRIDGES_AVAILABLE = True
except ImportError:
    BRIDGES_AVAILABLE = False

    class _ServerStub:
        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self, _name: str | None = None, **_: Any):
            def decorator(func):
                return func

            return decorator

        def on_startup(self, func):
            return func

        def on_shutdown(self, func):
            return func

        def create_initialization_options(self) -> dict[str, Any]:
            return {}

        async def run(self, *args, **kwargs) -> None:
            raise RuntimeError(
                "MCP Python SDK not installed. Install the 'mcp' package to run the server."
            )

        def run_stdio(self) -> None:
            raise RuntimeError(
                "MCP Python SDK not installed. Install the 'mcp' package to run the server."
            )

    class _MissingStdIOServer:
        async def __aenter__(self) -> tuple[Any, Any]:
            raise RuntimeError(
                "MCP Python SDK not installed. Install the 'mcp' package to run the stdio server."
            )

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    def _missing_stdio_server() -> AsyncIterator[tuple[Any, Any]]:
        return _MissingStdIOServer()

    Server = _ServerStub  # type: ignore
    mcp_stdio = type("_StubStdIO", (), {"stdio_server": _missing_stdio_server})()  # type: ignore
    mcp_types = None  # type: ignore

from scribe_mcp.config.settings import settings
from scribe_mcp.state import StateManager
from scribe_mcp.shared.execution_context import (
    RouterContextManager,
    get_current_execution_context,
    resolve_bootstrap_execution_context,
)
from scribe_mcp.shared.tool_runtime import execute_tool_call
from scribe_mcp.shared.tool_runtime import resolve_context_authoritative_session_key
from scribe_mcp.shared.repo_authority import build_repo_authority_snapshot, project_root_is_first_party
from scribe_mcp.utils.sentinel_logs import log_scope_violation
from scribe_mcp.state.agent_manager import init_agent_context_manager
from scribe_mcp.state.agent_identity import init_agent_identity
from scribe_mcp.storage import create_storage_backend
from scribe_mcp.config.mode_detection import detect_operating_mode, OperatingMode

if TYPE_CHECKING:
    class ToolDecorator(Protocol):
        def __call__(self, func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]: ...

    class ToolServer(Server):
        def tool(
            self,
            func: Callable[..., Awaitable[Any]] | None = None,
            **_: Any,
        ) -> ToolDecorator: ...

        def list_tools(self, *args: Any, **kwargs: Any) -> ToolDecorator: ...

        def call_tool(self, *args: Any, **kwargs: Any) -> ToolDecorator: ...

if TYPE_CHECKING:
    _server_instance: ToolServer = cast("ToolServer", Server(settings.mcp_server_name))
    app = _server_instance
else:
    app = Server(settings.mcp_server_name)
if not hasattr(app, "state"):
    app.state = SimpleNamespace()
if not hasattr(app.state, "execution_context"):
    app.state.execution_context = None
storage_backend = create_storage_backend()
state_manager = StateManager(storage_backend=storage_backend)
agent_context_manager = None  # Will be initialized in startup
agent_identity = None  # Will be initialized in startup
router_context_manager = RouterContextManager(storage_backend=storage_backend)
_startup_complete = False
_journal_replay_complete = False  # Tracks background journal replay status

# Background task management (prevents garbage collection of fire-and-forget tasks)
# See: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
background_tasks: set[asyncio.Task] = set()
_transport_shutdown_lock = asyncio.Lock()
_transport_shutdown_phase = "running"  # running|draining|backend_close|closed
_transport_inflight_operations = 0


async def begin_transport_operation() -> str:
    """Mark an in-flight transport request or return the active shutdown phase."""
    global _transport_inflight_operations
    async with _transport_shutdown_lock:
        if _transport_shutdown_phase != "running":
            return _transport_shutdown_phase
        _transport_inflight_operations += 1
        return "running"


async def end_transport_operation() -> None:
    """Release a previously tracked in-flight transport request."""
    global _transport_inflight_operations
    async with _transport_shutdown_lock:
        if _transport_inflight_operations > 0:
            _transport_inflight_operations -= 1


def get_transport_shutdown_state() -> dict[str, Any]:
    """Return a snapshot of transport shutdown progress."""
    return {
        "phase": _transport_shutdown_phase,
        "inflight": _transport_inflight_operations,
    }


def _rebind_storage_backend_for_mode(mode: OperatingMode):
    """Recreate the process storage backend from the resolved operating mode."""
    global storage_backend

    storage_backend = create_storage_backend(mode=mode)
    state_manager._storage_backend = storage_backend
    router_context_manager._storage_backend = storage_backend
    return storage_backend


@dataclass
class BackgroundServiceStatus:
    name: str
    description: str
    status: str = "pending"  # pending|running|healthy|failed|stopped|cancelled
    persistent: bool = False
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    last_duration_ms: Optional[int] = None
    last_error: Optional[str] = None


@dataclass(frozen=True)
class TransportPolicy:
    transport: str
    bind_host: str
    port: int
    network_exposed: bool
    auth_required: bool
    auth_configured: bool
    allow_outside_repo_reads: bool


_background_services: dict[str, BackgroundServiceStatus] = {}
_LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}

_SENTINEL_ONLY_TOOLS = {"append_event"}
_SENTINEL_ALLOWED_TOOLS = _SENTINEL_ONLY_TOOLS | {
    "open_bug",
    "open_security",
    "link_fix",
    "list_open_cases",
    "read_file",
    "query_entries",
    "read_recent",
    "scribe_doctor",
    "set_project",
    "append_entry",
    "list_projects",
    "get_project",
}


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in _LOCAL_BIND_HOSTS


def build_transport_policy(
    *,
    transport: str,
    host: str | None = None,
    port: int | None = None,
    auth_required: bool | None = None,
    auth_configured: bool | None = None,
    allow_outside_repo_reads: bool | None = None,
) -> TransportPolicy:
    bind_host = (host or settings.transport_host).strip() or settings.transport_host
    bind_port = int(port if port is not None else settings.transport_port)
    network_exposed = transport == "sse" and not _is_loopback_host(bind_host)
    return TransportPolicy(
        transport=transport,
        bind_host=bind_host,
        port=bind_port,
        network_exposed=network_exposed,
        auth_required=(transport == "sse") if auth_required is None else auth_required,
        auth_configured=bool(settings.transport_auth_token) if auth_configured is None else auth_configured,
        allow_outside_repo_reads=(
            settings.allow_outside_repo_reads
            if allow_outside_repo_reads is None
            else allow_outside_repo_reads
        ),
    )


def set_transport_policy(policy: TransportPolicy) -> None:
    app.state.transport_policy = {
        "transport": policy.transport,
        "bind_host": policy.bind_host,
        "port": policy.port,
        "network_exposed": policy.network_exposed,
        "auth_required": policy.auth_required,
        "auth_configured": policy.auth_configured,
        "allow_outside_repo_reads": policy.allow_outside_repo_reads,
    }


def get_transport_policy() -> dict[str, Any]:
    policy = getattr(app.state, "transport_policy", None)
    if isinstance(policy, dict):
        return dict(policy)
    fallback = build_transport_policy(transport="stdio", host="stdio", port=0, auth_required=False)
    return {
        "transport": fallback.transport,
        "bind_host": fallback.bind_host,
        "port": fallback.port,
        "network_exposed": fallback.network_exposed,
        "auth_required": fallback.auth_required,
        "auth_configured": fallback.auth_configured,
        "allow_outside_repo_reads": fallback.allow_outside_repo_reads,
    }


_STARTUP_CLEANUP_DELAY_SECONDS = _float_env("SCRIBE_STARTUP_CLEANUP_DELAY_SECONDS", 60.0, 0.0)
set_transport_policy(build_transport_policy(transport="stdio", host="stdio", port=0, auth_required=False))
_STARTUP_LEGACY_MIGRATION_DELAY_SECONDS = _float_env(
    "SCRIBE_STARTUP_LEGACY_MIGRATION_DELAY_SECONDS",
    20.0,
    0.0,
)
_STARTUP_PLUGIN_INIT_DELAY_SECONDS = _float_env("SCRIBE_STARTUP_PLUGIN_INIT_DELAY_SECONDS", 25.0, 0.0)


def _resolve_bridge_tool(tool_name: str) -> Optional[Callable[..., Awaitable[Any]]]:
    if ":" not in tool_name or not BRIDGES_AVAILABLE:
        return None
    try:
        tool_registry = get_tool_registry()
        parts = tool_name.split(":", 1)
        if len(parts) == 2:
            bridge_id, custom_tool_name = parts
            return cast(Optional[Callable[..., Awaitable[Any]]], tool_registry.get_custom_tool(bridge_id, custom_tool_name))
    except Exception:
        return None
    return None

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run_after_delay(
    delay_seconds: float,
    coroutine_factory: Callable[[], Awaitable[None]],
    *,
    label: str,
) -> None:
    if delay_seconds > 0:
        logger.info("Delaying %s startup task by %.1fs", label, delay_seconds)
        await asyncio.sleep(delay_seconds)
    await coroutine_factory()


def get_background_service_status() -> dict[str, dict[str, Any]]:
    """Return health/status for all tracked background services."""
    status: dict[str, dict[str, Any]] = {}
    for name, service in sorted(_background_services.items()):
        status[name] = {
            "description": service.description,
            "status": service.status,
            "persistent": service.persistent,
            "started_at": service.started_at,
            "finished_at": service.finished_at,
            "last_duration_ms": service.last_duration_ms,
            "last_error": service.last_error,
        }
    return status


def _register_background_service(
    service_name: str,
    *,
    description: str,
    persistent: bool,
) -> BackgroundServiceStatus:
    service = _background_services.get(service_name)
    if service is None:
        service = BackgroundServiceStatus(
            name=service_name,
            description=description or service_name,
            persistent=persistent,
        )
        _background_services[service_name] = service
    else:
        if description:
            service.description = description
        service.persistent = persistent
    return service


def schedule_background_task(
    coro,
    *,
    service_name: str | None = None,
    description: str = "",
    persistent: bool = False,
):
    """
    Schedule a background task with automatic cleanup.

    Prevents garbage collection of fire-and-forget tasks by maintaining
    a strong reference in the background_tasks set. Tasks are automatically
    removed when complete via add_done_callback.

    Args:
        coro: Coroutine to execute in background
        service_name: Optional name used for service health tracking.
        description: Optional human-readable service description.
        persistent: True for long-running services expected to stay running.

    Returns:
        asyncio.Task: The created task (for testing/debugging)
    """
    logger.debug("schedule_background_task called, creating task...")
    start_monotonic = asyncio.get_running_loop().time()
    tracked_name = service_name
    if tracked_name:
        service = _register_background_service(
            tracked_name,
            description=description,
            persistent=persistent,
        )
        service.status = "running"
        service.started_at = _utc_now_iso()
        service.finished_at = None
        service.last_error = None

    task = asyncio.create_task(coro)
    background_tasks.add(task)

    def _on_done(completed_task: asyncio.Task) -> None:
        background_tasks.discard(completed_task)

        if not tracked_name:
            return

        service = _background_services.get(tracked_name)
        if service is None:
            return

        duration_ms = int((asyncio.get_running_loop().time() - start_monotonic) * 1000)
        service.last_duration_ms = duration_ms
        service.finished_at = _utc_now_iso()

        if completed_task.cancelled():
            service.status = "cancelled"
            service.last_error = "Task cancelled"
            return

        error: Exception | None
        try:
            error = completed_task.exception()
        except Exception as exc:
            error = exc

        if error is not None:
            service.status = "failed"
            service.last_error = str(error)
            logger.warning("Background service '%s' failed: %s", tracked_name, error)
            return

        if persistent:
            # A persistent service returning is unexpected but non-fatal.
            service.status = "stopped"
            service.last_error = None
            logger.warning(
                "Background service '%s' stopped (persistent service returned)",
                tracked_name,
            )
        else:
            service.status = "healthy"
            service.last_error = None

    task.add_done_callback(_on_done)
    logger.debug("Task created and added to background_tasks (total: %d)", len(background_tasks))
    return task

if _MCP_AVAILABLE:
    from mcp import types as mcp_types

    if not hasattr(app, "tool"):
        if not hasattr(Server, "_scribe_tool_registry"):
            Server._scribe_tool_registry = {}
            Server._scribe_tool_defs = {}

        def _build_schema_from_signature(func: Callable) -> Dict[str, Any]:
            """Build JSON Schema from function signature with type hints."""
            import typing
            sig = inspect.signature(func)
            properties = {}
            required = []

            # Use get_type_hints to resolve string annotations (from __future__ import annotations)
            try:
                type_hints = typing.get_type_hints(func)
            except Exception:
                type_hints = {}

            for param_name, param in sig.parameters.items():
                # Skip special parameters
                if param_name in ("_kwargs", "kwargs") and param.kind == inspect.Parameter.VAR_KEYWORD:
                    continue
                if param_name in ("args",) and param.kind == inspect.Parameter.VAR_POSITIONAL:
                    continue

                # Determine if required (no default value)
                has_default = param.default != inspect.Parameter.empty
                if not has_default and param_name not in ("doc",):  # doc is technically required but batch doesn't use it
                    required.append(param_name)

                # Build property schema from type hint
                param_schema = {"type": "string"}  # Default fallback

                # Get resolved annotation from type_hints (handles string annotations)
                annotation = type_hints.get(param_name, param.annotation)
                if annotation != inspect.Parameter.empty and annotation is not None:
                    # Handle Optional types (Union with None)
                    origin = getattr(annotation, "__origin__", None)
                    args = getattr(annotation, "__args__", ())

                    if origin is Union:
                        # Optional[X] is Union[X, None]
                        non_none_types = [t for t in args if t is not type(None)]
                        if non_none_types:
                            annotation = non_none_types[0]
                            # Re-compute origin for the inner type
                            origin = getattr(annotation, "__origin__", None)

                    # Map Python types to JSON Schema types
                    if annotation is str or annotation == str:
                        param_schema = {"type": "string"}
                    elif annotation is int or annotation == int:
                        # Accept both integer and string: MCP transport may serialize
                        # integer values as strings (e.g. "21" instead of 21).
                        # Coercion to int happens in execute_tool_call before dispatch.
                        param_schema = {"type": ["integer", "string"]}
                    elif annotation is float or annotation == float:
                        param_schema = {"type": ["number", "string"]}
                    elif annotation is bool or annotation == bool:
                        param_schema = {"type": "boolean"}
                    elif origin is list or annotation is list:
                        param_schema = {"type": "array"}
                    elif origin is dict or annotation is dict:
                        param_schema = {"type": "object"}
                    elif hasattr(annotation, "__name__") and annotation.__name__ == "Dict":
                        param_schema = {"type": "object"}
                    elif hasattr(annotation, "__name__") and annotation.__name__ == "List":
                        param_schema = {"type": "array"}
                    else:
                        # Unknown type, allow anything
                        param_schema = {}

                properties[param_name] = param_schema

            # Special handling for manage_docs: make doc_category optional when action is batch
            # This is a workaround since we can't make it conditionally required
            if func.__name__ == "manage_docs" and "doc_category" in required:
                required.remove("doc_category")

            schema = {
                "type": "object",
                "properties": properties,
                "additionalProperties": True,
            }
            if required:
                schema["required"] = required
            return schema

        def _tool_decorator(
            func: Callable[..., Awaitable[Any]] | None = None,
            *,
            name: str | None = None,
            title: str | None = None,
            description: str | None = None,
            input_schema: Dict[str, Any] | None = None,
            output_schema: Dict[str, Any] | None = None,
            annotations: Any = None,
            icons: Any = None,
            _meta: Dict[str, Any] | None = None,
            meta: Dict[str, Any] | None = None,
            execution: Any = None,
            tags: list[str] | tuple[str, ...] | None = None,
        ):
            def _coerce_tool_annotations(value: Any) -> Any:
                if value is None:
                    return None
                if isinstance(value, mcp_types.ToolAnnotations):
                    return value
                if isinstance(value, dict):
                    return mcp_types.ToolAnnotations(**value)
                raise TypeError(f"Unsupported tool annotations type: {type(value)!r}")

            def _coerce_icons(value: Any) -> list[Any] | None:
                if value is None:
                    return None
                if not isinstance(value, (list, tuple)):
                    raise TypeError(f"Unsupported tool icons type: {type(value)!r}")
                resolved_icons: list[Any] = []
                for item in value:
                    if isinstance(item, mcp_types.Icon):
                        resolved_icons.append(item)
                    elif isinstance(item, dict):
                        resolved_icons.append(mcp_types.Icon(**item))
                    else:
                        raise TypeError(f"Unsupported tool icon entry type: {type(item)!r}")
                return resolved_icons or None

            def _coerce_tool_execution(value: Any) -> Any:
                if value is None:
                    return None
                if isinstance(value, mcp_types.ToolExecution):
                    return value
                if isinstance(value, dict):
                    return mcp_types.ToolExecution(**value)
                raise TypeError(f"Unsupported tool execution type: {type(value)!r}")

            def _normalize_tool_meta(primary: Dict[str, Any] | None, alias: Dict[str, Any] | None) -> Dict[str, Any] | None:
                selected = primary if primary is not None else alias
                if selected is None:
                    return None
                return dict(selected)

            def _normalize_tags(value: list[str] | tuple[str, ...] | None) -> list[str] | None:
                if value is None:
                    return None
                normalized: list[str] = []
                seen: set[str] = set()
                for tag in value:
                    tag_str = str(tag).strip()
                    if not tag_str or tag_str in seen:
                        continue
                    seen.add(tag_str)
                    normalized.append(tag_str)
                return normalized or None

            def register(target: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
                tool_name = name or target.__name__
                # Build schema from function signature if not explicitly provided
                if input_schema is None:
                    schema = _build_schema_from_signature(target)
                else:
                    schema = input_schema
                tool_description = description or (inspect.getdoc(target) or "")
                tool_annotations = _coerce_tool_annotations(annotations)
                tool_icons = _coerce_icons(icons)
                tool_execution = _coerce_tool_execution(execution)
                tool_meta = _normalize_tool_meta(_meta, meta)
                tool_tags = _normalize_tags(tags)
                Server._scribe_tool_registry[tool_name] = target
                Server._scribe_tool_defs[tool_name] = mcp_types.Tool(
                    name=tool_name,
                    title=title,
                    description=tool_description,
                    inputSchema=schema,
                    outputSchema=output_schema,
                    icons=tool_icons,
                    annotations=tool_annotations,
                    _meta=tool_meta,
                    execution=tool_execution,
                    tags=tool_tags,
                )
                return target

            if func is not None:
                return register(func)
            return register

        setattr(app, "tool", _tool_decorator)

        @app.list_tools()
        async def _list_tools() -> list[mcp_types.Tool]:
            tools.ensure_all_tools_loaded()
            defs = getattr(Server, "_scribe_tool_defs", {})
            return list(defs.values())

        @app.call_tool()
        async def _call_tool(name: str, arguments: Dict[str, Any], **kwargs: Any) -> Any:
            tools.ensure_tool_loaded(name)
            registry = getattr(Server, "_scribe_tool_registry", {})
            return await execute_tool_call(
                name=name,
                arguments=dict(arguments or {}),
                kwargs=kwargs,
                registry=registry,
                app=app,
                storage_backend=storage_backend,
                settings=settings,
                state_manager=state_manager,
                router_context_manager=router_context_manager,
                sentinel_only=_SENTINEL_ONLY_TOOLS,
                sentinel_allowed=_SENTINEL_ALLOWED_TOOLS,
                log_scope_violation_cb=log_scope_violation,
                bridge_tool_resolver=_resolve_bridge_tool,
            )


# Import tool modules to register them with the server instance.
from scribe_mcp import tools  # noqa: E402  # isort:skip


_HAS_LIFECYCLE_HOOKS = hasattr(app, "on_startup") and hasattr(app, "on_shutdown")


async def _replay_journals_background() -> None:
    """Replay uncommitted journal entries in background (non-blocking startup).

    This function runs as a background task to avoid blocking server startup.
    The server can respond to tool calls immediately while journals are replayed.
    """
    global _journal_replay_complete

    logger.info("Starting background journal replay...")

    from scribe_mcp.utils.files import WriteAheadLog
    from scribe_mcp.tools.list_projects import list_projects
    from scribe_mcp.tools.project_utils import list_project_configs
    import glob

    try:
        # Enhanced recovery: Scan all projects for orphaned journals
        total_replayed = 0
        recovered_projects = []

        # Method 1: Try to get list of all configured projects
        try:
            # list_projects defaults to format="readable", which returns an MCP CallToolResult wrapper
            # (Issue #9962 fix). For internal server startup we need a plain dict payload.
            # Use internal system agent for startup operations
            projects_result = await list_projects(
                agent="__scribe_internal__",
                format="structured",
                limit=1000,
                include_test=True,
                global_mode=True,
            )
            available_projects = projects_result.get("projects", [])
            try:
                current_context = get_execution_context()
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
                scribe_user=os.environ.get("SCRIBE_USER"),
                authoritative_session_key=resolve_context_authoritative_session_key(current_context),
                enrolled_first_party_roots=enrolled_first_party_roots,
            )
            for project_info in available_projects:
                project_name = project_info.get("name")
                project_root_value = project_info.get("root")
                visible, _authority_source, _reason_code, _normalized_root = project_root_is_first_party(
                    project_root=project_root_value,
                    snapshot=authority_snapshot,
                )
                if not visible:
                    continue
                if not (project_name and project_info.get("progress_log")):
                    continue

                try:
                    progress_log_path = Path(project_info["progress_log"])
                    if not progress_log_path.exists():
                        continue
                    wal = WriteAheadLog(progress_log_path)
                    replayed = wal.replay_uncommitted()
                    if replayed > 0:
                        total_replayed += replayed
                        recovered_projects.append(project_name)
                except Exception as project_replay_error:
                    logger.debug(
                        "Skipping journal replay for project '%s': %s",
                        project_name,
                        project_replay_error,
                    )
        except Exception as list_error:
            logger.warning("Project discovery failed during recovery: %s", list_error)

        # Method 2: Fallback - scan for orphaned journal files in project directories
        try:
            # Look for .journal files in typical project locations
            journal_patterns = [
                str(settings.project_root / "config" / "projects" / "*" / "*.journal"),
                str(settings.project_root / ".scribe" / "docs" / "dev_plans" / "*" / "*.journal"),
                "**/PROGRESS_LOG.md.journal"  # Common pattern
            ]

            for pattern in journal_patterns:
                for journal_file in glob.glob(pattern, recursive=True):
                    journal_path = Path(journal_file)
                    if journal_path.exists():
                        # Find corresponding log file
                        log_path = journal_path.with_suffix('')
                        if log_path.exists():
                            wal = WriteAheadLog(log_path)
                            replayed = wal.replay_uncommitted()
                            if replayed > 0:
                                total_replayed += replayed
                                project_name = log_path.parent.name
                                if project_name not in recovered_projects:
                                    recovered_projects.append(project_name)
        except Exception as scan_error:
            logger.warning("Journal scan failed during recovery: %s", scan_error)

        # Report recovery results
        if total_replayed > 0:
            logger.info("CRASH RECOVERY: Replayed %d uncommitted entries across %d projects",
                        total_replayed, len(recovered_projects))
            for project_name in recovered_projects:
                logger.info("  Recovered entries for project: %s", project_name)
            logger.info("  Audit trail integrity maintained despite crash")
        else:
            logger.info("Background journal replay completed (no uncommitted entries)")

    except Exception as e:
        # Journal recovery should not prevent server operation
        logger.warning("Journal recovery warning: %s", e)
        logger.warning("  Server will continue but some audit entries may be missing")
    finally:
        _journal_replay_complete = True


async def _cleanup_old_entries_background() -> None:
    """Clean up old entries after startup without delaying MCP initialize."""
    if not storage_backend:
        return
    try:
        deleted = await storage_backend.cleanup_old_entries(retention_days=settings.retention_days)
        if deleted > 0:
            logger.info("Cleaned up %d old log entries (>%d days)", deleted, settings.retention_days)
    except Exception as e:
        logger.warning("Entry cleanup failed (non-fatal): %s", e)
        raise


async def _init_plugins_background() -> None:
    """Initialize plugins in background (can be expensive due model loading)."""
    try:
        from scribe_mcp.config.repo_config import RepoConfig
        from scribe_mcp.plugins.registry import initialize_plugins

        repo_root = settings.project_root or Path.cwd()
        repo_config = RepoConfig.from_directory(Path(repo_root))
        initialize_plugins(repo_config)
        logger.info("Plugin system initialized (background)")
    except Exception as e:
        logger.warning("Plugin initialization failed: %s", e)
        logger.warning("  Continuing without plugins (vector search will not be available)")
        raise


def _register_bridge_custom_tools() -> None:
    """Register bridge-provided custom tools with MCP server."""
    if not BRIDGES_AVAILABLE:
        return
    try:
        tool_registry = get_tool_registry()
        custom_tools = tool_registry.list_all_custom_tools()

        for tool_info in custom_tools:
            full_name = tool_info["full_name"]
            bridge_id = tool_info["bridge_id"]
            tool_name = tool_info["tool_name"]

            impl = tool_registry.get_custom_tool(bridge_id, tool_name)
            if impl:
                Server._scribe_tool_registry[full_name] = impl
                logger.info("Registered bridge tool: %s", full_name)
    except Exception as e:
        logger.warning("Bridge tool registration failed: %s", e)
        logger.warning("  Continuing without bridge tools")


async def _init_bridges_background() -> None:
    """Initialize bridge registry/manifests in background."""
    if not (BRIDGES_AVAILABLE and storage_backend):
        return

    bridge_registry = None
    try:
        from scribe_mcp.bridges.registry import BridgeRegistry
        from scribe_mcp.bridges.health import BridgeHealthMonitor, set_health_monitor
        from scribe_mcp.bridges.hooks import get_hook_manager

        bridge_registry = BridgeRegistry(
            storage_backend=storage_backend,
            config_dir=Path(".scribe/config/bridges"),
            hook_manager=get_hook_manager(),
        )
        logger.info("BridgeRegistry initialized")

        manifests = bridge_registry.discover_manifests()
        bridges_activated = 0
        bridges_total = len(manifests)

        bridge_failures = 0
        for manifest_path in manifests:
            try:
                manifest = bridge_registry.load_manifest(manifest_path)
                await bridge_registry.register_bridge(manifest)

                await bridge_registry.activate_bridge(manifest.bridge_id)
                logger.info("  Registered & activated bridge: %s", manifest.bridge_id)
                bridges_activated += 1
            except Exception as bridge_error:
                logger.warning("  Failed to register bridge from %s: %s", manifest_path, bridge_error)
                bridge_failures += 1

        if bridges_total > 0:
            logger.info("Bridge system initialized (%d/%d bridges active)", bridges_activated, bridges_total)
        else:
            logger.info("Bridge system initialized (no manifests found)")

        if bridge_registry:
            health_monitor = BridgeHealthMonitor(registry=bridge_registry, check_interval=60.0)
            set_health_monitor(health_monitor)
            schedule_background_task(
                _bridge_health_monitor_service(health_monitor),
                service_name="bridge_health_monitor",
                description="Bridge health monitor loop",
                persistent=True,
            )
            logger.info("Bridge health monitor started (60s interval)")

        _register_bridge_custom_tools()

        if bridge_failures > 0:
            raise RuntimeError(
                f"Bridge bootstrap completed with {bridge_failures} manifest failure(s)"
            )

    except Exception as e:
        logger.warning("Bridge system initialization failed: %s", e)
        logger.warning("  Continuing without bridge support")
        bridge_registry = None
        raise


async def _migrate_legacy_state_background() -> None:
    """Migrate legacy global state to agent-scoped context after startup."""
    if not (storage_backend and state_manager):
        return
    from scribe_mcp.state.agent_manager import migrate_legacy_state
    try:
        await migrate_legacy_state(state_manager, storage_backend)
    except Exception as e:
        logger.warning("Legacy state migration failed: %s", e)
        logger.warning("  Continuing with agent-scoped context (legacy state may be lost)")
        raise


async def _bridge_health_monitor_service(monitor: Any) -> None:
    """Keep bridge health monitor running until explicit cancellation."""
    await monitor.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await monitor.stop()


async def _startup() -> None:
    """Initialise shared resources before handling requests."""
    global agent_context_manager, agent_identity, _startup_complete
    global storage_backend, state_manager, router_context_manager
    global _transport_shutdown_phase
    if _startup_complete:
        return
    _transport_shutdown_phase = "running"
    _startup_complete = True
    startup_started = perf_counter()

    # --- Mode detection (client/server/standalone) ---
    mode = await detect_operating_mode(settings)
    logger.info("Operating mode: %s", mode.value)
    rebound_backend = _rebind_storage_backend_for_mode(mode)
    logger.info(
        "Storage backend rebound for %s mode → %s",
        mode.value,
        type(rebound_backend).__name__ if rebound_backend is not None else "None",
    )

    if storage_backend:
        storage_setup_started = perf_counter()
        await storage_backend.setup()
        logger.warning(
            "PERF storage.setup completed in %.1fms",
            (perf_counter() - storage_setup_started) * 1000.0,
        )
        # Server-only: entry cleanup contends on shared SQLite writers
        if mode != OperatingMode.CLIENT:
            schedule_background_task(
                _run_after_delay(
                    _STARTUP_CLEANUP_DELAY_SECONDS,
                    _cleanup_old_entries_background,
                    label="entry cleanup",
                ),
                service_name="entry_cleanup",
                description="Retention cleanup for old entries",
            )

    # Server-only background services: plugins, bridges, legacy migration
    if mode != OperatingMode.CLIENT:
        schedule_background_task(
            _run_after_delay(
                _STARTUP_PLUGIN_INIT_DELAY_SECONDS,
                _init_plugins_background,
                label="plugin initialization",
            ),
            service_name="plugin_init",
            description="Plugin subsystem initialization",
        )
        schedule_background_task(
            _init_bridges_background(),
            service_name="bridge_init",
            description="Bridge registry/bootstrap initialization",
        )

    # Initialize AgentContextManager for agent-scoped project context
    if storage_backend and state_manager:
        agent_context_manager = init_agent_context_manager(storage_backend, state_manager)
        agent_identity = init_agent_identity(state_manager)
        logger.info("AgentContextManager initialized for multi-agent support")
        logger.info("AgentIdentity system initialized for automatic agent detection")

        # Server-only: legacy migration and session cleanup loop
        if mode != OperatingMode.CLIENT:
            schedule_background_task(
                _run_after_delay(
                    _STARTUP_LEGACY_MIGRATION_DELAY_SECONDS,
                    _migrate_legacy_state_background,
                    label="legacy state migration",
                ),
                service_name="legacy_state_migration",
                description="One-time legacy state migration",
            )
            schedule_background_task(
                _session_cleanup_task(agent_context_manager),
                service_name="session_cleanup",
                description="Agent session lease cleanup loop",
                persistent=True,
            )
            logger.info("Session cleanup task started")

    # Server-only: register bridge custom tools
    if mode != OperatingMode.CLIENT:
        _register_bridge_custom_tools()

    # Initialize document store (object store layer)
    # Client mode KEEPS this — client talks to CortaStore directly
    try:
        from scribe_mcp.object_store import create_document_store

        doc_store_started = perf_counter()
        document_store = create_document_store(settings)
        await document_store.setup()
        app.state.document_store = document_store
        logger.warning(
            "PERF document_store.setup completed in %.1fms",
            (perf_counter() - doc_store_started) * 1000.0,
        )
    except Exception:
        logger.warning("Document store initialization failed — continuing without object store", exc_info=True)

    # Server-only: journal replay
    if mode != OperatingMode.CLIENT:
        schedule_background_task(
            _replay_journals_background(),
            service_name="journal_replay",
            description="Replay uncommitted journal entries",
        )

    total_startup_ms = (perf_counter() - startup_started) * 1000.0
    logger.warning(
        "PERF startup total=%.1fms (deferred services=%d, mode=%s)",
        total_startup_ms,
        len(background_tasks),
        mode.value,
    )
    # Protocol signal — Council MCP and other process managers pattern-match
    # stderr for "Server ready" to know the subprocess is ready for MCP
    # handshake. WARNING level ensures visibility at the default log level.
    logger.warning("Server ready (mode=%s, journal replay %s)",
                   mode.value,
                   "skipped" if mode == OperatingMode.CLIENT else "continuing in background")


async def _shutdown() -> None:
    """Ensure resources are released when the server stops."""
    global _transport_shutdown_phase

    async with _transport_shutdown_lock:
        if _transport_shutdown_phase == "closed":
            return
        _transport_shutdown_phase = "draining"

    shutdown_deadline = perf_counter() + max(float(settings.storage_timeout_seconds), 0.0)
    while True:
        async with _transport_shutdown_lock:
            inflight = _transport_inflight_operations
        if inflight <= 0:
            break
        if perf_counter() >= shutdown_deadline:
            logger.warning(
                "Transport shutdown proceeding with %d in-flight operation(s) after timeout.",
                inflight,
            )
            break
        await asyncio.sleep(0.01)

    async with _transport_shutdown_lock:
        _transport_shutdown_phase = "backend_close"

    if background_tasks:
        for task in list(background_tasks):
            task.cancel()
        try:
            await asyncio.gather(*list(background_tasks), return_exceptions=True)
        except Exception:
            pass

    if storage_backend:
        try:
            async with asyncio.timeout(settings.storage_timeout_seconds):
                await asyncio.shield(storage_backend.close())
        except Exception:
            pass

    # Close document store (object store layer)
    doc_store = getattr(getattr(app, "state", None), "document_store", None)
    if doc_store:
        try:
            await doc_store.close()
        except Exception:
            pass

    async with _transport_shutdown_lock:
        _transport_shutdown_phase = "closed"


if _HAS_LIFECYCLE_HOOKS:
    app.on_startup(_startup)
    app.on_shutdown(_shutdown)


def get_agent_context_manager():
    """Get the global AgentContextManager instance."""
    global agent_context_manager
    return agent_context_manager


def get_agent_identity():
    """Get the global AgentIdentity instance."""
    global agent_identity
    return agent_identity


def get_execution_context(*, recovery_mode: str | None = None, include_metadata: bool = False):
    """Return the active ExecutionContext for the current request.

    Default behavior is fail-closed and only consults request-local contextvars.
    Legacy app-state fallback remains available only through explicit recovery_mode.
    """
    current = get_current_execution_context()
    if current is not None:
        metadata = {
            "resolution_source": "runtime_context",
            "trust_level": "verified",
            "fallback_used": False,
            "fallback_chain": [],
        }
        return (current, metadata) if include_metadata else current

    recovered, metadata = resolve_bootstrap_execution_context(
        getattr(app, "state", None),
        recovery_mode=recovery_mode,
    )
    return (recovered, metadata) if include_metadata else recovered


def list_registered_tools() -> list[str]:
    """Return sorted tool names currently registered on the MCP server."""
    tools.ensure_all_tools_loaded()
    registry = getattr(Server, "_scribe_tool_registry", {})
    return sorted(str(name) for name in registry.keys())


def describe_registered_tools() -> dict[str, dict[str, Any]]:
    """Return tool metadata keyed by tool name for CLI discovery."""
    tools.ensure_all_tools_loaded()
    registry = getattr(Server, "_scribe_tool_registry", {})
    defs = getattr(Server, "_scribe_tool_defs", {})
    description_map: dict[str, dict[str, Any]] = {}
    for tool_name, func in registry.items():
        tool_def = defs.get(tool_name)
        schema = getattr(tool_def, "inputSchema", None) if tool_def else None
        output_schema = getattr(tool_def, "outputSchema", None) if tool_def else None
        description = getattr(tool_def, "description", "") if tool_def else ""
        if not description:
            description = inspect.getdoc(func) or ""
        annotations = getattr(tool_def, "annotations", None) if tool_def else None
        execution = getattr(tool_def, "execution", None) if tool_def else None
        meta = getattr(tool_def, "meta", None) if tool_def else None
        tags = getattr(tool_def, "tags", None) if tool_def else None
        description_map[str(tool_name)] = {
            "name": str(tool_name),
            "title": getattr(tool_def, "title", "") if tool_def else "",
            "description": description,
            "input_schema": schema if isinstance(schema, dict) else {},
            "output_schema": output_schema if isinstance(output_schema, dict) else {},
            "annotations": annotations.model_dump() if hasattr(annotations, "model_dump") else annotations,
            "execution": execution.model_dump() if hasattr(execution, "model_dump") else execution,
            "meta": meta if isinstance(meta, dict) else {},
            "tags": list(tags) if isinstance(tags, (list, tuple, set)) else [],
        }
    return description_map


async def invoke_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Any:
    """Invoke a registered tool through the same runtime path used by MCP."""
    if not name:
        raise ValueError("Tool name is required")

    payload = dict(arguments or {})
    kwargs: Dict[str, Any] = {}
    if context is not None:
        kwargs["context"] = context

    await _startup()
    try:
        tools.ensure_tool_loaded(name)
        registry = getattr(Server, "_scribe_tool_registry", {})
        return await execute_tool_call(
            name=name,
            arguments=payload,
            kwargs=kwargs,
            registry=registry,
            app=app,
            storage_backend=storage_backend,
            settings=settings,
            state_manager=state_manager,
            router_context_manager=router_context_manager,
            sentinel_only=_SENTINEL_ONLY_TOOLS,
            sentinel_allowed=_SENTINEL_ALLOWED_TOOLS,
            log_scope_violation_cb=log_scope_violation,
            bridge_tool_resolver=_resolve_bridge_tool,
        )
    finally:
        await _shutdown()


async def _session_cleanup_task(agent_manager):
    """Background task to clean up expired sessions."""
    import asyncio
    while True:
        try:
            await asyncio.sleep(300)  # Clean every 5 minutes
            cleaned = await agent_manager.cleanup_expired_sessions()
            if cleaned > 0:
                logger.info("Cleaned up %d expired sessions", cleaned)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Session cleanup error: %s", e)
            # Continue cleaning despite errors


async def main() -> None:
    """Run the MCP server over stdio."""
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "MCP Python SDK not installed. Install the 'mcp' package to run the server."
        )
    set_transport_policy(build_transport_policy(transport="stdio", host="stdio", port=0, auth_required=False))
    await _startup()

    try:
        async with mcp_stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
    finally:
        if not _HAS_LIFECYCLE_HOOKS:
            await _shutdown()


if __name__ == "__main__":
    asyncio.run(main())
