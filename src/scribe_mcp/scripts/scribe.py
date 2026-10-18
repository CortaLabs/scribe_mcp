#!/usr/bin/env python3
"""Utility for appending structured progress log entries (MCP-aligned).

This CLI is a thin wrapper over the core MCP tools:
- set_project: ensure the project is registered and docs exist
- append_entry: write entries with the same rules agents use

It exists primarily as a convenience for humans; agents should prefer the
MCP interface directly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from scribe_mcp.config.paths import repo_root


ROOT_DIR = repo_root()

# Ensure Scribe sees this repo as its root and keeps state under the repo
# instead of ~/.scribe when the CLI is used.
os.environ.setdefault("SCRIBE_ROOT", str(ROOT_DIR))
os.environ.setdefault("SCRIBE_STATE_PATH", str(ROOT_DIR / "tmp_state_cli.json"))

from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.project_utils import slugify_project_name
from scribe_mcp.config.log_config import get_log_definition, resolve_log_path

PROJECTS_DIR = ROOT_DIR / "config" / "projects"
DEFAULT_PROJECT_NAME = os.environ.get("SCRIBE_DEFAULT_PROJECT", "scribe_mcp")

STATUS_EMOJI = {
    "info": "ℹ️",
    "success": "✅",
    "warn": "⚠️",
    "error": "❌",
    "bug": "🐞",
    "plan": "🧭",
}

def load_config(path: Path) -> Dict[str, Any]:
    config = _normalise_config(_read_json(path), ROOT_DIR)
    if not config:
        raise SystemExit(f"Config file is missing required fields: {path}")
    return config


def parse_meta(pairs: Iterable[str]) -> Tuple[Tuple[str, str], ...]:
    extracted = []
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"Meta value must be key=value, received: {pair}")
        key, value = pair.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key:
            raise SystemExit("Meta key cannot be empty.")
        extracted.append((key, value))
    return tuple(extracted)


def format_entry(
    message: str,
    emoji: str,
    agent: Optional[str],
    project_name: Optional[str],
    meta: Tuple[Tuple[str, str], ...],
    timestamp: Optional[str],
) -> str:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not emoji:
        emoji = "📝"

    segments = [f"[{emoji}]", f"[{timestamp}]"]

    if agent:
        segments.append(f"[Agent: {agent}]")

    if project_name:
        segments.append(f"[Project: {project_name}]")

    entry = " ".join(segments) + f" {message}"

    if meta:
        meta_str = "; ".join(f"{key}={value}" for key, value in meta)
        entry += f" | {meta_str}"

    return entry


async def log_via_tools(
    message: str,
    *,
    emoji: Optional[str],
    status: Optional[str],
    agent: Optional[str],
    meta: Mapping[str, Any],
    project_name: str,
    project_config: Dict[str, Any],
    timestamp: Optional[str],
    log_type: str = "progress",
    dry_run: bool = False,
) -> str:
    """Use set_project + append_entry so CLI matches MCP behavior."""

    # Ensure project is registered and docs exist.
    await set_project(
        name=project_name,
        root=project_config.get("root"),
        progress_log=project_config.get("progress_log"),
        defaults=project_config.get("defaults") or {},
    )

    # Compose metadata dict for append_entry.
    meta_dict = {str(k): str(v) for k, v in meta.items()}

    # Use append_entry tool; let it handle emoji/status mapping and DB mirroring.
    result = await append_entry(
        message=message,
        status=status,
        emoji=emoji,
        agent=agent,
        meta=meta_dict,
        timestamp_utc=timestamp,
        log_type=log_type,
        auto_split=False,
    )

    if not result.get("ok", False):
        raise SystemExit(result.get("error", "append_entry failed"))

    # For CLI feedback, synthesize a human-readable line similar to format_entry.
    resolved_emoji = emoji or STATUS_EMOJI.get(status or "", "") or "📝"
    entry_meta = tuple(meta_dict.items())
    display = format_entry(
        message=message,
        emoji=resolved_emoji,
        agent=agent,
        project_name=project_name,
        meta=entry_meta,
        timestamp=timestamp,
    )
    # In dry-run mode we don't care whether it actually wrote.
    return display


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append a formatted entry to the project progress log."
    )
    parser.add_argument("message", nargs="?", help="Primary log message.")
    status_help = ", ".join(f"{name!r}" for name in STATUS_EMOJI)
    parser.add_argument(
        "-e",
        "--emoji",
        help="Emoji or short indicator to include in the entry.",
    )
    parser.add_argument(
        "-s",
        "--status",
        choices=sorted(STATUS_EMOJI),
        help=f"Named status mapped to an emoji ({status_help}).",
    )
    parser.add_argument(
        "-a",
        "--agent",
        help="Name of the agent or component producing the entry.",
    )
    parser.add_argument(
        "-m",
        "--meta",
        action="append",
        default=[],
        help="Additional metadata as key=value pairs. Option may be repeated.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to project config JSON file.",
    )
    parser.add_argument(
        "--log",
        dest="log_type",
        default="progress",
        help="Log type key defined in .scribe/config/scribe.yaml logs (legacy log_config.json also supported; default: progress).",
    )
    parser.add_argument(
        "-p",
        "--project",
        help="Project config name under config/projects (e.g., 'scribe_mcp').",
    )
    parser.add_argument(
        "-t",
        "--timestamp",
        help="Override timestamp text (default: current UTC time).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the formatted entry without writing to disk.",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List available project configs and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    if args.list_projects:
        configs = discover_project_configs()
        if not configs:
            print("No project configs found under config/projects.")
        else:
            for name, info in configs.items():
                print(f"{name}\t{info['progress_log']}")
        return

    if not args.message:
        raise SystemExit("Message is required unless --list-projects is used.")

    if not args.message:
        raise SystemExit("Message is required unless --list-projects is used.")

    config_path: Optional[Path] = args.config
    config_data: Optional[Dict[str, Any]] = None

    if config_path is None:
        if args.project:
            config_path = PROJECTS_DIR / f"{args.project}.json"
        else:
            config_path = PROJECTS_DIR / f"{DEFAULT_PROJECT_NAME}.json"

    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    if args.config is None:
        config_data = _normalise_config(_read_json(config_path), ROOT_DIR)
        if not config_data:
            raise SystemExit(f"Config file is missing required fields: {config_path}")
    else:
        config_data = load_config(config_path)

    meta = parse_meta(args.meta)

    # Use MCP-aligned tools to perform the write.
    import asyncio
    project_name = config_data.get("name") or slugify_project_name(config_data.get("progress_log", "project"))
    entry = asyncio.run(
        log_via_tools(
            message=args.message,
            emoji=args.emoji,
            status=args.status,
            agent=args.agent,
            meta=dict(meta),
            project_name=project_name,
            project_config=config_data,
            timestamp=args.timestamp,
            log_type=args.log_type,
            dry_run=args.dry_run,
        )
    )

    if args.dry_run:
        print(entry)
    else:
        project_payload = {
            "name": config_data.get("name"),
            "root": config_data.get("root"),
            "progress_log": config_data.get("progress_log"),
            "docs_dir": config_data.get("docs_dir"),
        }
        log_definition = get_log_definition(args.log_type, repo_root=project_payload.get("root"))
        log_path = resolve_log_path(project_payload, log_definition)
        print(f"Wrote entry to {log_path}:")
        print(entry)


def discover_project_configs() -> Dict[str, Dict[str, Any]]:
    configs: Dict[str, Dict[str, Any]] = {}
    if PROJECTS_DIR.exists():
        for path in sorted(PROJECTS_DIR.glob("*.json")):
            data = _normalise_config(_read_json(path), ROOT_DIR)
            if data:
                configs[data["name"]] = data
    return configs


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _normalise_config(data: Dict[str, Any], base_root: Path) -> Optional[Dict[str, Any]]:
    if not data:
        return None
    name = data.get("name") or data.get("project_name")
    if not name:
        return None

    root_value = data.get("root")
    if root_value:
        root_path = Path(root_value)
        if not root_path.is_absolute():
            root_path = (base_root / root_path).resolve()
        else:
            root_path = root_path.resolve()
    else:
        root_path = base_root

    docs_value = data.get("docs_dir")
    if docs_value:
        docs_path = Path(docs_value)
        if not docs_path.is_absolute():
            docs_path = (root_path / docs_path).resolve()
        else:
            docs_path = docs_path.resolve()
    else:
        slug = slugify_project_name(name)
        docs_path = (root_path / "docs" / "dev_plans" / slug).resolve()

    progress_value = data.get("progress_log")
    if progress_value:
        log_path = Path(progress_value)
        if not log_path.is_absolute():
            log_path = (root_path / log_path).resolve()
        else:
            log_path = log_path.resolve()
    else:
        log_path = docs_path / "PROGRESS_LOG.md"

    defaults_raw = data.get("defaults") or {}
    defaults = {k: v for k, v in defaults_raw.items() if v}

    return {
        "name": name,
        "root": str(root_path),
        "progress_log": str(log_path),
        "docs_dir": str(docs_path),
        "defaults": defaults,
    }


if __name__ == "__main__":
    main()
