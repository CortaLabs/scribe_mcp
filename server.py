"""Entrypoint for the Scribe MCP server."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, Callable, Dict, Optional, Protocol, Union, cast, get_origin, get_args

# Ensure the repository root (which contains the `scribe_mcp` package) is on sys.path.
# This allows running `python server.py` or `python -m server` from within the package directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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

        def tool(self, _name: str | None = None):
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
from scribe_mcp.shared.execution_context import RouterContextManager
from scribe_mcp.utils.sentinel_logs import log_scope_violation
from scribe_mcp.state.agent_manager import init_agent_context_manager
from scribe_mcp.state.agent_identity import init_agent_identity
from scribe_mcp.storage import create_storage_backend

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
state_manager = StateManager()
storage_backend = create_storage_backend()
agent_context_manager = None  # Will be initialized in startup
agent_identity = None  # Will be initialized in startup
router_context_manager = RouterContextManager(storage_backend=storage_backend)
_startup_complete = False
_journal_replay_complete = False  # Tracks background journal replay status

# Background task management (prevents garbage collection of fire-and-forget tasks)
# See: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
background_tasks: set[asyncio.Task] = set()

def schedule_background_task(coro):
    """
    Schedule a background task with automatic cleanup.

    Prevents garbage collection of fire-and-forget tasks by maintaining
    a strong reference in the background_tasks set. Tasks are automatically
    removed when complete via add_done_callback.

    Args:
        coro: Coroutine to execute in background

    Returns:
        asyncio.Task: The created task (for testing/debugging)
    """
    logger.debug("schedule_background_task called, creating task...")
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
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
                        param_schema = {"type": "integer"}
                    elif annotation is float or annotation == float:
                        param_schema = {"type": "number"}
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
            description: str | None = None,
            input_schema: Dict[str, Any] | None = None,
            output_schema: Dict[str, Any] | None = None,
        ):
            def register(target: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
                tool_name = name or target.__name__
                # Build schema from function signature if not explicitly provided
                if input_schema is None:
                    schema = _build_schema_from_signature(target)
                else:
                    schema = input_schema
                tool_description = description or (inspect.getdoc(target) or "")
                Server._scribe_tool_registry[tool_name] = target
                Server._scribe_tool_defs[tool_name] = mcp_types.Tool(
                    name=tool_name,
                    description=tool_description,
                    inputSchema=schema,
                    outputSchema=output_schema,
                )
                return target

            if func is not None:
                return register(func)
            return register

        setattr(app, "tool", _tool_decorator)

        @app.list_tools()
        async def _list_tools() -> list[mcp_types.Tool]:
            defs = getattr(Server, "_scribe_tool_defs", {})
            return list(defs.values())

        @app.call_tool()
        async def _call_tool(name: str, arguments: Dict[str, Any], **kwargs: Any) -> Any:
            registry = getattr(Server, "_scribe_tool_registry", {})
            func = registry.get(name)

            # Check for bridge custom tools (format: bridge_id:tool_name)
            if not func and ":" in name and BRIDGES_AVAILABLE:
                try:
                    tool_registry = get_tool_registry()
                    parts = name.split(":", 1)
                    if len(parts) == 2:
                        bridge_id, tool_name = parts
                        func = tool_registry.get_custom_tool(bridge_id, tool_name)
                except Exception:
                    pass  # Fall through to error handling

            if not func:
                raise ValueError(f"Unknown tool '{name}'")

            # Tools that ONLY work in sentinel mode (blocked in project mode)
            sentinel_only = {"append_event"}
            # Tools allowed in sentinel mode (superset includes dual-mode tools)
            sentinel_allowed = sentinel_only | {"open_bug", "open_security", "link_fix", "read_file", "query_entries", "read_recent", "set_project", "append_entry", "list_projects", "get_project"}

            def derive_session_identity(exec_context, arguments: dict) -> tuple[str, dict]:
                """Derive stable session identity from execution context.

                Returns (identity_hash, identity_parts dict)
                """
                # 1. Canonicalize repo_root
                repo_root = os.path.realpath(exec_context.repo_root)

                # 2. Get mode and scope_key
                mode = exec_context.mode  # "project" or "sentinel"
                if mode == "sentinel":
                    scope_key = exec_context.sentinel_day  # e.g., "2026-01-03"
                else:
                    scope_key = exec_context.execution_id  # UUID

                # 3. Get agent_key (prefer stable ID, fallback to display_name)
                agent_key = None
                if exec_context.agent_identity:
                    agent_key = (
                        getattr(exec_context.agent_identity, 'id', None) or
                        getattr(exec_context.agent_identity, 'instance_id', None) or
                        exec_context.agent_identity.display_name
                    )
                if not agent_key:
                    agent_key = arguments.get("agent") or "default"

                # 4. Construct identity string
                identity = f"{repo_root}:{mode}:{scope_key}:{agent_key}"

                # 5. Hash it (full SHA-256, no truncation)
                identity_hash = hashlib.sha256(identity.encode()).hexdigest()

                return identity_hash, {
                    "repo_root": repo_root,
                    "mode": mode,
                    "scope_key": scope_key,
                    "agent_key": agent_key,
                }

            def derive_session_identity_preview(context_payload: dict, arguments: dict) -> tuple[str, dict]:
                """Preview stable session identity before ExecutionContext exists.

                Uses context_payload instead of exec_context so we can derive identity
                BEFORE building ExecutionContext.

                Returns (identity_hash, identity_parts dict)
                """
                from datetime import datetime, timezone
                import uuid

                # 1. Canonicalize repo_root
                repo_root = os.path.realpath(context_payload.get("repo_root", ""))

                # 2. Get mode and scope_key
                mode = context_payload.get("mode", "sentinel")
                if mode == "sentinel":
                    # For sentinel mode, derive scope_key from timestamp
                    timestamp_utc = context_payload.get("timestamp_utc")
                    if not timestamp_utc:
                        timestamp_utc = datetime.now(timezone.utc).isoformat()
                    scope_key = timestamp_utc.split("T")[0]  # e.g., "2026-01-03"
                else:
                    # For project mode, use transport_session_id (stable across tool calls)
                    scope_key = context_payload.get("transport_session_id") or context_payload.get("session_id") or str(uuid.uuid4())

                # 3. Get agent_key from arguments - REQUIRED, no fallback
                agent_key = arguments.get("agent")
                if not agent_key:
                    raise ValueError("agent parameter is required for all tool calls")

                # 4. Construct identity string
                identity = f"{repo_root}:{mode}:{scope_key}:{agent_key}"

                # 5. Hash it (full SHA-256, no truncation)
                identity_hash = hashlib.sha256(identity.encode()).hexdigest()

                return identity_hash, {
                    "repo_root": repo_root,
                    "mode": mode,
                    "scope_key": scope_key,
                    "agent_key": agent_key,
                }

            def _derive_transport_session_id() -> str | None:
                """Extract transport session ID from MCP request context.

                This is a backwards-compatible fallback that checks headers/meta
                for client-provided session identifiers. The stable session identity
                is now derived separately using derive_session_identity().
                """
                try:
                    request_context = app.request_context
                except Exception:
                    return None
                if not request_context:
                    return None
                request = getattr(request_context, "request", None)
                if request is not None:
                    headers = getattr(request, "headers", None)
                    if headers:
                        header_val = headers.get("mcp-session-id")
                        if header_val:
                            return str(header_val)
                meta = getattr(request_context, "meta", None)
                client_id = getattr(meta, "client_id", None) if meta else None
                if client_id:
                    return str(client_id)
                # No more id(session) fallback - stable identity derived elsewhere
                return None

            context_payload = arguments.pop("context", None)
            if context_payload is None and "context" in kwargs:
                context_payload = kwargs.get("context")
            if not isinstance(context_payload, dict):
                context_payload = {}

            def _extract_request_repo_root() -> Optional[str]:
                try:
                    request_context = app.request_context
                except Exception:
                    return None
                if not request_context:
                    return None
                meta = getattr(request_context, "meta", None)
                if not meta:
                    return None
                if isinstance(meta, dict):
                    for key in ("repo_root", "workspace_root", "cwd"):
                        value = meta.get(key)
                        if value:
                            return str(value)
                else:
                    for key in ("repo_root", "workspace_root", "cwd"):
                        value = getattr(meta, key, None)
                        if value:
                            return str(value)
                return None

            def _normalize_repo_root(value: Any) -> Optional[str]:
                if not value:
                    return None
                try:
                    root_path = Path(str(value)).expanduser()
                except (TypeError, ValueError):
                    return None
                if not root_path.is_absolute():
                    root_path = (settings.project_root / root_path).resolve()
                else:
                    root_path = root_path.resolve()
                return str(root_path)

            if not context_payload.get("repo_root"):
                request_repo_root = _extract_request_repo_root()
                if request_repo_root:
                    try:
                        request_path = Path(request_repo_root).expanduser()
                        if request_path.is_absolute():
                            from scribe_mcp.config.repo_config import RepoDiscovery
                            candidate_root = RepoDiscovery.find_repo_root(request_path)
                            if candidate_root and candidate_root.exists():
                                context_payload["repo_root"] = str(candidate_root.resolve())
                    except Exception:
                        pass

            repo_root_hint = _normalize_repo_root(context_payload.get("repo_root"))
            if not repo_root_hint and isinstance(arguments, dict):
                repo_root_hint = _normalize_repo_root(
                    arguments.get("root") or arguments.get("repo_root")
                )
            if repo_root_hint:
                context_payload["repo_root"] = repo_root_hint

            if not context_payload.get("session_id") and not context_payload.get("transport_session_id"):
                transport_fallback = (
                    kwargs.get("session_id")
                    or kwargs.get("client_id")
                    or kwargs.get("connection_id")
                )
                if not transport_fallback:
                    transport_fallback = _derive_transport_session_id()
                if not transport_fallback:
                    # No MCP session context - generate fallback based on process instance
                    # This will be converted to stable session via derive_session_identity()
                    transport_fallback = f"process:{router_context_manager._process_instance_id}"
                if transport_fallback:
                    context_payload["transport_session_id"] = str(transport_fallback)

            if not context_payload.get("session_id") and context_payload.get("transport_session_id"):
                backend = storage_backend
                if backend and hasattr(backend, "get_session_by_transport"):
                    # NO SILENT ERRORS - let it fail loudly
                    existing = await backend.get_session_by_transport(
                        str(context_payload["transport_session_id"])
                    )
                    if existing and existing.get("session_id"):
                        context_payload["session_id"] = existing["session_id"]
                    if existing and not context_payload.get("repo_root"):
                        context_payload["repo_root"] = _normalize_repo_root(existing.get("repo_root"))
                if not context_payload.get("session_id"):
                    # NO SILENT ERRORS - let it fail loudly
                    session_id = await router_context_manager.get_or_create_session_id(
                        context_payload["transport_session_id"]
                    )
                    context_payload["session_id"] = session_id

            # FIX: Prioritize explicit project argument for repo_root derivation.
            # This ensures the session identity matches what set_project used, since
            # the unstable session_id might not match the stable_session_id used for binding.
            if not context_payload.get("repo_root"):
                backend = storage_backend
                if backend and hasattr(backend, "fetch_project"):
                    # PRIORITY 1: Use explicit project argument if provided
                    # This is critical because set_project binds to stable_session_id,
                    # but we only have the unstable session_id at this point.
                    explicit_project = None
                    if isinstance(arguments, dict):
                        explicit_project = arguments.get("project") or arguments.get("name")

                    if explicit_project:
                        project_record = await backend.fetch_project(str(explicit_project))
                        if project_record:
                            context_payload["repo_root"] = _normalize_repo_root(
                                project_record.repo_root
                            )

                    # PRIORITY 2: Fall back to session-based lookup only if no explicit project
                    if not context_payload.get("repo_root") and context_payload.get("session_id"):
                        project_name = None
                        if hasattr(backend, "get_session_project"):
                            project_name = await backend.get_session_project(
                                context_payload.get("session_id")
                            )
                        if project_name:
                            project_record = await backend.fetch_project(str(project_name))
                            if project_record:
                                context_payload["repo_root"] = _normalize_repo_root(
                                    project_record.repo_root
                                )

            if not context_payload.get("repo_root"):
                context_payload["repo_root"] = str(settings.project_root.resolve())

            if context_payload.get("mode") not in {"sentinel", "project"}:
                # Project-scoped tools that should always run in project mode
                project_tools = {"set_project", "get_project", "append_entry", "read_recent", "query_entries", "rotate_log", "manage_docs", "generate_doc_templates"}

                if name in project_tools:
                    # Force project mode for project-scoped tools
                    context_payload["mode"] = "project"
                else:
                    # For other tools, query existing session mode
                    session_mode = None
                    if context_payload.get("session_id"):
                        backend = storage_backend
                        if backend and hasattr(backend, "get_session_mode"):
                            # NO SILENT ERRORS - let it fail loudly
                            session_mode = await backend.get_session_mode(context_payload.get("session_id"))
                        if session_mode is None:
                            # NO SILENT ERRORS - let it fail loudly
                            state = await state_manager.load()
                            session_mode = state.get_session_mode(context_payload.get("session_id"))
                    # Default to sentinel to avoid implicit project scope or audit pollution.
                    context_payload["mode"] = session_mode or "sentinel"

            if not context_payload.get("session_id") and not context_payload.get("transport_session_id"):
                raise ValueError("ExecutionContext requires context.session_id or context.transport_session_id")

            if not context_payload.get("intent"):
                context_payload["intent"] = f"tool:{name}"

            affected = context_payload.get("affected_dev_projects")
            if not isinstance(affected, list):
                affected = []
            if not affected and isinstance(arguments, dict):
                project_hint = arguments.get("project") or arguments.get("name")
                if project_hint:
                    affected = [str(project_hint)]
            context_payload["affected_dev_projects"] = affected

            backend = storage_backend
            if backend and hasattr(backend, "upsert_session"):
                try:
                    await backend.upsert_session(
                        session_id=context_payload.get("session_id"),
                        transport_session_id=context_payload.get("transport_session_id"),
                        repo_root=context_payload.get("repo_root"),
                        mode=context_payload.get("mode"),
                    )
                except Exception:
                    pass

            # PHASE 1 INTEGRATION: Derive stable session BEFORE building ExecutionContext
            import traceback
            debug_log = Path("/tmp/scribe_session_debug.log")
            with open(debug_log, "a") as f:
                f.write(f"\n=== {datetime.now(timezone.utc).isoformat()} ===\n")
                f.write(f"Tool: {name}\n")
                f.write(f"context_payload: {context_payload}\n")

            identity_hash, identity_parts = derive_session_identity_preview(context_payload, arguments)
            with open(debug_log, "a") as f:
                f.write(f"identity_hash: {identity_hash}\n")
                f.write(f"identity_parts: {identity_parts}\n")

            stable_session_id = None
            with open(debug_log, "a") as f:
                f.write(f"backend: {backend}\n")
                f.write(f"has method: {hasattr(backend, 'get_or_create_agent_session') if backend else False}\n")

            if backend and hasattr(backend, "get_or_create_agent_session"):
                with open(debug_log, "a") as f:
                    f.write(f"Calling get_or_create_agent_session...\n")
                try:
                    # NO SILENT ERRORS - let it fail loudly so we can debug
                    stable_session_id = await backend.get_or_create_agent_session(
                        identity_key=identity_hash,
                        agent_name=identity_parts["agent_key"],  # For display
                        agent_key=identity_parts["agent_key"],
                        repo_root=identity_parts["repo_root"],
                        mode=identity_parts["mode"],
                        scope_key=identity_parts["scope_key"],
                    )
                    with open(debug_log, "a") as f:
                        f.write(f"stable_session_id: {stable_session_id}\n")
                except Exception as e:
                    with open(debug_log, "a") as f:
                        f.write(f"ERROR: {e}\n")
                        f.write(f"Traceback:\n{traceback.format_exc()}\n")
                    raise

            # Add stable_session_id to context_payload BEFORE building ExecutionContext
            if stable_session_id:
                context_payload["stable_session_id"] = stable_session_id

            exec_context = await router_context_manager.build_execution_context(context_payload)

            if exec_context.mode == "sentinel" and name not in sentinel_allowed:
                log_scope_violation(
                    exec_context,
                    reason="tool_not_allowed_in_sentinel_mode",
                    tool_name=name,
                )
                raise ValueError(f"Tool '{name}' not allowed in sentinel mode")
            if exec_context.mode == "project" and name in sentinel_only and name != "append_event":
                raise ValueError(f"Tool '{name}' not allowed in project mode")

            token = router_context_manager.set_current(exec_context)

            # Auto-inject cached project if not explicitly provided
            if "project" not in arguments and "project_name" not in arguments:
                cached_project = await router_context_manager.get_cached_project(
                    exec_context.stable_session_id
                )
                if cached_project:
                    arguments["project"] = cached_project

            try:
                result = func(**arguments)
            except TypeError:
                raise ValueError(f"Invalid arguments for tool '{name}'")

            if inspect.isawaitable(result):
                try:
                    return await result
                finally:
                    router_context_manager.reset(token)
            try:
                return result
            finally:
                router_context_manager.reset(token)


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
            )
            available_projects = projects_result.get("projects", [])
            for project_info in available_projects:
                project_name = project_info.get("name")
                if project_name and project_info.get("progress_log"):
                    progress_log_path = Path(project_info["progress_log"])
                    if progress_log_path.exists():
                        wal = WriteAheadLog(progress_log_path)
                        replayed = wal.replay_uncommitted()
                        if replayed > 0:
                            total_replayed += replayed
                            recovered_projects.append(project_name)
        except Exception as list_error:
            logger.warning("Project listing failed during recovery: %s", list_error)

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


async def _startup() -> None:
    """Initialise shared resources before handling requests."""
    global agent_context_manager, agent_identity, _startup_complete
    if _startup_complete:
        return
    _startup_complete = True

    if storage_backend:
        await storage_backend.setup()

        # Cleanup old entries (>retention_days) after database initialization
        try:
            deleted = await storage_backend.cleanup_old_entries(retention_days=settings.retention_days)
            if deleted > 0:
                logger.info("Cleaned up %d old log entries (>%d days)", deleted, settings.retention_days)
        except Exception as e:
            logger.warning("Entry cleanup failed (non-fatal): %s", e)

    # Initialize plugins in background — vector indexer loads torch/faiss/transformers
    # which takes 8-10s and must not block the MCP readiness signal.
    async def _init_plugins_background():
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

    schedule_background_task(_init_plugins_background())

    # Initialize Bridge System (optional feature)
    bridge_registry = None
    if BRIDGES_AVAILABLE and storage_backend:
        try:
            from scribe_mcp.bridges.registry import BridgeRegistry
            from scribe_mcp.bridges.health import BridgeHealthMonitor, set_health_monitor

            # Task Package 1.1: Create BridgeRegistry
            bridge_registry = BridgeRegistry(
                storage_backend=storage_backend,
                config_dir=Path(".scribe/config/bridges")
            )
            logger.info("BridgeRegistry initialized")

            # Task Package 1.2: Discover and register manifests
            manifests = bridge_registry.discover_manifests()
            bridges_activated = 0
            bridges_total = len(manifests)

            for manifest_path in manifests:
                try:
                    # Load, register, and activate each bridge
                    manifest = bridge_registry.load_manifest(manifest_path)
                    await bridge_registry.register_bridge(manifest)
                    await bridge_registry.activate_bridge(manifest.bridge_id)
                    logger.info("  Registered & activated bridge: %s", manifest.bridge_id)
                    bridges_activated += 1
                except Exception as bridge_error:
                    logger.warning("  Failed to register bridge from %s: %s", manifest_path, bridge_error)
                    # Continue with next manifest

            if bridges_total > 0:
                logger.info("Bridge system initialized (%d/%d bridges active)", bridges_activated, bridges_total)
            else:
                logger.info("Bridge system initialized (no manifests found)")

            # Task Package 1.3: Start health monitor background task
            if bridge_registry:
                health_monitor = BridgeHealthMonitor(
                    registry=bridge_registry,
                    check_interval=60.0
                )
                set_health_monitor(health_monitor)
                asyncio.create_task(health_monitor.start())
                logger.info("Bridge health monitor started (60s interval)")

        except Exception as e:
            logger.warning("Bridge system initialization failed: %s", e)
            logger.warning("  Continuing without bridge support")
            bridge_registry = None

    # Initialize AgentContextManager for agent-scoped project context
    if storage_backend and state_manager:
        agent_context_manager = init_agent_context_manager(storage_backend, state_manager)
        agent_identity = init_agent_identity(state_manager)
        logger.info("AgentContextManager initialized for multi-agent support")
        logger.info("AgentIdentity system initialized for automatic agent detection")

        # Migrate legacy global state to agent-scoped context
        from scribe_mcp.state.agent_manager import migrate_legacy_state
        try:
            await migrate_legacy_state(state_manager, storage_backend)
        except Exception as e:
            logger.warning("Legacy state migration failed: %s", e)
            logger.warning("  Continuing with agent-scoped context (legacy state may be lost)")

        # Start background session cleanup task
        asyncio.create_task(_session_cleanup_task(agent_context_manager))
        logger.info("Session cleanup task started")

    # Register bridge custom tools with MCP server
    if BRIDGES_AVAILABLE:
        try:
            tool_registry = get_tool_registry()
            custom_tools = tool_registry.list_all_custom_tools()

            for tool_info in custom_tools:
                full_name = tool_info["full_name"]
                bridge_id = tool_info["bridge_id"]
                tool_name = tool_info["tool_name"]

                # Get the actual implementation
                impl = tool_registry.get_custom_tool(bridge_id, tool_name)
                if impl:
                    # Register with MCP server
                    # The tool name will be prefixed: council_mcp:custom_audit
                    Server._scribe_tool_registry[full_name] = impl
                    logger.info("Registered bridge tool: %s", full_name)
        except Exception as e:
            logger.warning("Bridge tool registration failed: %s", e)
            logger.warning("  Continuing without bridge tools")

    # Start background journal replay (non-blocking)
    # Journal recovery happens in background so server can respond to tool calls immediately
    schedule_background_task(_replay_journals_background())
    # Protocol signal — Council MCP and other process managers pattern-match
    # stderr for "Server ready" to know the subprocess is ready for MCP
    # handshake. WARNING level ensures visibility at the default log level.
    logger.warning("Server ready (journal replay continuing in background)")


async def _shutdown() -> None:
    """Ensure resources are released when the server stops."""
    if storage_backend:
        try:
            async with asyncio.timeout(settings.storage_timeout_seconds):
                await asyncio.shield(storage_backend.close())
        except Exception:
            pass


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


def get_execution_context():
    """Return the active ExecutionContext for the current request."""
    current = router_context_manager.get_current()
    if current is not None:
        return current
    return getattr(getattr(app, "state", None), "execution_context", None)


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
            break
        except Exception as e:
            logger.warning("Session cleanup error: %s", e)
            # Continue cleaning despite errors


async def main() -> None:
    """Run the MCP server over stdio."""
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "MCP Python SDK not installed. Install the 'mcp' package to run the server."
        )
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
