"""Package entrypoint for running the Scribe MCP server.

Supports two transport modes selectable via ``--transport`` (or the
``SCRIBE_TRANSPORT`` environment variable):

* **stdio** (default) -- runs the MCP server over stdin/stdout.
* **sse** -- starts an HTTP server with SSE transport on a configurable
  host/port for containerised deployments.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Sequence

from scribe_mcp.server import main as server_main


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Scribe MCP server.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="scribe-mcp 2.2",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=os.environ.get("SCRIBE_TRANSPORT", "stdio"),
        help="Transport mode (default: stdio, env: SCRIBE_TRANSPORT)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SCRIBE_TRANSPORT_PORT", "8200")),
        help="Port for SSE transport (default: 8200, env: SCRIBE_TRANSPORT_PORT)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("SCRIBE_TRANSPORT_HOST", "0.0.0.0"),
        help="Host for SSE transport (default: 0.0.0.0, env: SCRIBE_TRANSPORT_HOST)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.transport == "sse":
        from scribe_mcp.server_sse import run_sse
        asyncio.run(run_sse(host=args.host, port=args.port))
    else:
        asyncio.run(server_main())


if __name__ == "__main__":
    main()

