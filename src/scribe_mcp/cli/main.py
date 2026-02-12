"""Universal command-line interface for Scribe tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Sequence

from scribe_mcp.cli.session_store import (
    CliSessionState,
    load_session_state,
    save_session_state,
)
from scribe_mcp.config.paths import cli_session_state_path


_KNOWN_COMMANDS = {"call", "session", "tools"}


def _discover_repo_root(start: Path) -> Path:
    candidate = start.expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for current in (candidate, *candidate.parents):
        if (current / ".git").exists() or (current / ".scribe").exists():
            return current
    return candidate


def _coerce_value(raw: str) -> Any:
    stripped = raw.strip()
    if stripped == "":
        return ""
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return raw


def _load_json_object(raw: str | None, *, flag_name: str) -> Dict[str, Any]:
    if not raw:
        return {}
    payload = raw
    if raw.startswith("@"):
        payload = Path(raw[1:]).read_text(encoding="utf-8")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{flag_name} must be valid JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"{flag_name} must decode to a JSON object")
    return parsed


def _parse_key_value_pairs(values: Sequence[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise SystemExit(f"--arg values must be key=value (received: {item})")
        key, raw_value = item.split("=", 1)
        key = key.strip().replace("-", "_")
        if not key:
            raise SystemExit("Argument key cannot be empty")
        parsed[key] = _coerce_value(raw_value)
    return parsed


def _parse_passthrough_options(tokens: Sequence[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--"):
            raise SystemExit(f"Unexpected token: {token}. Tool options must be --key value.")
        key = token[2:]
        if not key:
            raise SystemExit("Empty option name is not valid")
        if key.startswith("no-"):
            parsed[key[3:].replace("-", "_")] = False
            index += 1
            continue
        if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
            parsed[key.replace("-", "_")] = _coerce_value(tokens[index + 1])
            index += 2
            continue
        parsed[key.replace("-", "_")] = True
        index += 1
    return parsed


def _normalize_argv(argv: Sequence[str]) -> list[str]:
    normalized = list(argv)
    if not normalized:
        return normalized
    first = normalized[0]
    if first in _KNOWN_COMMANDS or first in {"-h", "--help"}:
        return normalized
    if first.startswith("-"):
        return normalized
    # Shorthand: `scribe read_file --path ...` -> `scribe call read_file --path ...`
    return ["call", *normalized]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scribe",
        description="Unified Scribe CLI for calling any registered tool.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    tools_parser = subparsers.add_parser("tools", help="List registered tools")
    tools_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    tools_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )

    call_parser = subparsers.add_parser("call", help="Invoke a tool by name", allow_abbrev=False)
    call_parser.add_argument("tool", help="Tool name (for example: read_file)")
    call_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    call_parser.add_argument(
        "--session",
        default="default",
        help="Named CLI session used for persisted execution context.",
    )
    call_parser.add_argument(
        "--agent",
        required=True,
        help="Agent identity for this tool call (required).",
    )
    call_parser.add_argument(
        "--args-json",
        default="{}",
        help="JSON object merged into tool arguments (supports @path/to/file.json).",
    )
    call_parser.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Tool argument as key=value (repeatable, JSON values allowed).",
    )
    call_parser.add_argument(
        "--context-json",
        default=None,
        help="JSON object merged into runtime context (supports @path/to/file.json).",
    )
    call_parser.add_argument(
        "--session-mode",
        choices=["auto", "project", "sentinel"],
        default="auto",
        help="Override mode for this call. `auto` keeps persisted mode.",
    )
    call_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON responses.",
    )
    call_parser.add_argument(
        "--no-save-session",
        action="store_true",
        help="Do not persist updated session context after call.",
    )

    session_parser = subparsers.add_parser("session", help="Inspect/reset CLI session state")
    session_subparsers = session_parser.add_subparsers(dest="session_action", required=True)

    show_parser = session_subparsers.add_parser("show", help="Show current session state")
    show_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    show_parser.add_argument("--name", default="default", help="Session name")
    show_parser.add_argument("--agent", default=None, help="Agent identity override")

    reset_parser = session_subparsers.add_parser("reset", help="Delete a stored session")
    reset_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    reset_parser.add_argument("--name", default="default", help="Session name")

    return parser


def _resolve_agent(agent: str | None) -> str:
    if agent:
        return agent
    return os.environ.get("SCRIBE_CLI_AGENT", "cli")


def _prepare_environment(repo_root: Path) -> None:
    os.environ["SCRIBE_ROOT"] = str(repo_root.resolve())


def _normalize_tracked_path(repo_root: Path, candidate: Any) -> str | None:
    """Normalize and sandbox-check persisted read paths for CLI parity."""
    if not isinstance(candidate, str) or not candidate.strip():
        return None

    raw_path = Path(candidate).expanduser()
    if not raw_path.is_absolute():
        raw_path = repo_root / raw_path

    try:
        resolved = raw_path.resolve()
    except OSError:
        return None

    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return None

    return str(resolved)


def _load_tracked_reads(context: Dict[str, Any], repo_root: Path) -> list[str]:
    """Return deduplicated, normalized file-read history from context."""
    raw_values = context.get("files_read")
    if not isinstance(raw_values, list):
        return []

    seen: set[str] = set()
    normalized: list[str] = []
    for value in raw_values:
        normalized_value = _normalize_tracked_path(repo_root, value)
        if normalized_value and normalized_value not in seen:
            seen.add(normalized_value)
            normalized.append(normalized_value)

    return normalized


def _result_is_success(result: Any) -> bool:
    """Best-effort success detection for tool return payloads."""
    if isinstance(result, dict):
        if "isError" in result:
            return not bool(result.get("isError"))
        if "ok" in result:
            return bool(result.get("ok"))
        if result.get("error"):
            return False
    return True


async def _rehydrate_file_reads(
    *,
    server_module: Any,
    session_id: str | None,
    tracked_reads: Sequence[str],
) -> None:
    """Restore per-session read history into runtime cache for edit_file checks."""
    if not session_id or not tracked_reads:
        return

    context_manager = getattr(server_module, "router_context_manager", None)
    if context_manager is None or not hasattr(context_manager, "record_file_read"):
        return

    for file_path in tracked_reads:
        try:
            await context_manager.record_file_read(session_id, file_path)
        except Exception:
            # Rehydration should never block user tool calls.
            continue


def _json_print(payload: Any, pretty: bool = False) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    elif hasattr(payload, "dict") and callable(payload.dict):
        payload = payload.dict()

    if isinstance(payload, (dict, list)):
        if pretty:
            print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        else:
            print(json.dumps(payload, ensure_ascii=False))
        return
    print(payload)


def _session_record_value(record: Any, field: str) -> Any:
    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


async def _run_tools_command(args: argparse.Namespace) -> int:
    from scribe_mcp import server as server_module

    tools = server_module.describe_registered_tools()
    for details in tools.values():
        schema_required = details.get("input_schema", {}).get("required", [])
        if not isinstance(schema_required, list):
            schema_required = []

        effective_required = sorted({str(item) for item in schema_required if item} | {"agent"})
        details["runtime_required"] = ["agent"]
        details["effective_required"] = effective_required

    if args.json:
        _json_print(tools, pretty=True)
        return 0

    for tool_name in sorted(tools):
        details = tools[tool_name]
        required = details.get("effective_required", ["agent"])
        required_text = ", ".join(required)
        print(f"{tool_name}\trequired: {required_text}")
    return 0


async def _run_call_command(args: argparse.Namespace, passthrough_options: Dict[str, Any]) -> int:
    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)

    from scribe_mcp import server as server_module

    agent = _resolve_agent(args.agent)
    session_state = load_session_state(args.session, repo_root, agent)
    session_state.agent = agent
    session_state.repo_root = str(repo_root.resolve())

    call_args = _load_json_object(args.args_json, flag_name="--args-json")
    call_args.update(_parse_key_value_pairs(args.arg))
    call_args.update(passthrough_options)
    if "agent" not in call_args:
        call_args["agent"] = agent

    context = dict(session_state.context)
    context["repo_root"] = str(repo_root.resolve())
    context["transport_session_id"] = session_state.transport_session_id
    if args.session_mode != "auto":
        context["mode"] = args.session_mode

    context_overrides = _load_json_object(args.context_json, flag_name="--context-json")
    context.update(context_overrides)

    tracked_reads = _load_tracked_reads(context, repo_root)
    if tracked_reads:
        context["files_read"] = tracked_reads

    initial_session_id = context.get("session_id")
    await _rehydrate_file_reads(
        server_module=server_module,
        session_id=initial_session_id if isinstance(initial_session_id, str) else None,
        tracked_reads=tracked_reads,
    )

    result = await server_module.invoke_tool(args.tool, call_args, context=context)

    backend = getattr(server_module, "storage_backend", None)
    if backend and hasattr(backend, "get_session_by_transport"):
        session_record = await backend.get_session_by_transport(session_state.transport_session_id)
        if session_record:
            stored_session_id = _session_record_value(session_record, "session_id")
            stored_mode = _session_record_value(session_record, "mode")
            if stored_session_id:
                context["session_id"] = str(stored_session_id)
            if stored_mode:
                context["mode"] = str(stored_mode)

    if args.tool == "set_project":
        context["mode"] = "project"

    if args.tool == "read_file" and _result_is_success(result):
        tracked_path = _normalize_tracked_path(repo_root, call_args.get("path"))
        if tracked_path:
            if tracked_path not in tracked_reads:
                tracked_reads.append(tracked_path)
            context["files_read"] = tracked_reads

            session_id_value = context.get("session_id")
            await _rehydrate_file_reads(
                server_module=server_module,
                session_id=session_id_value if isinstance(session_id_value, str) else None,
                tracked_reads=[tracked_path],
            )

    session_state.context = context
    if not args.no_save_session:
        save_session_state(session_state)

    _json_print(result, pretty=args.pretty)
    return 0


def _run_session_command(args: argparse.Namespace) -> int:
    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)

    if args.session_action == "reset":
        session_path = cli_session_state_path(args.name)
        if session_path.exists():
            session_path.unlink()
            print(f"Removed session state: {session_path}")
        else:
            print(f"Session state not found: {session_path}")
        return 0

    agent = _resolve_agent(getattr(args, "agent", None))
    session_state = load_session_state(args.name, repo_root, agent)
    _json_print(session_state.to_dict(), pretty=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    normalized_argv = _normalize_argv(argv or sys.argv[1:])
    parser = _build_parser()
    args, unknown = parser.parse_known_args(normalized_argv)

    if args.command == "call":
        passthrough_options = _parse_passthrough_options(unknown)
    else:
        if unknown:
            parser.error(f"Unexpected arguments: {' '.join(unknown)}")
        passthrough_options = {}

    if args.command == "session":
        return _run_session_command(args)

    if args.command == "tools":
        repo_root = _discover_repo_root(args.repo_root)
        _prepare_environment(repo_root)
        return asyncio.run(_run_tools_command(args))

    return asyncio.run(_run_call_command(args, passthrough_options))


if __name__ == "__main__":
    raise SystemExit(main())
