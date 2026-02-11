"""Package entrypoint for running the Scribe MCP server."""

from __future__ import annotations

import asyncio

from scribe_mcp.server import main as server_main


def main() -> None:
    asyncio.run(server_main())


if __name__ == "__main__":
    main()

