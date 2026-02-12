"""CLI entrypoint for legacy state-file migration into DB storage."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from scribe_mcp.config.settings import settings
from scribe_mcp.state.migration import migrate_legacy_state_file
from scribe_mcp.storage import create_storage_backend


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate legacy state payload into Scribe's database tables.",
    )
    parser.add_argument(
        "--state-path",
        default=str(settings.default_state_path),
        help="Path to the legacy state payload (default: SCRIBE_STATE_PATH / settings default).",
    )
    parser.add_argument(
        "--no-rename",
        action="store_true",
        help="Do not rename the source file after successful migration.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    backend = create_storage_backend()
    if backend is None:
        print("error: unable to create storage backend", file=sys.stderr)
        return 2

    close_fn = getattr(backend, "close", None)
    try:
        result = await migrate_legacy_state_file(
            storage_backend=backend,
            state_path=Path(args.state_path).expanduser(),
            rename_source=not args.no_rename,
        )
    finally:
        if callable(close_fn):
            maybe_awaitable = close_fn()
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable

    print(result.message)
    print(f"projects_migrated={result.projects_migrated}")
    print(f"session_projects_migrated={result.session_projects_migrated}")
    print(f"session_modes_migrated={result.session_modes_migrated}")
    if result.renamed_to:
        print(f"renamed_to={result.renamed_to}")

    if result.migrated:
        return 0
    if result.message.lower().startswith("failed"):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
