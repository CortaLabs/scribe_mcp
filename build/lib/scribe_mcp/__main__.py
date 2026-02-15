"""Package entrypoint for running the Scribe MCP server."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from scribe_mcp.server import main as server_main


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Scribe MCP server over stdio.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="scribe-mcp 2.2",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    _parse_args(argv)
    asyncio.run(server_main())


if __name__ == "__main__":
    main()

