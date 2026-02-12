"""Compatibility shim for `python -m server` during src-layout migration."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from scribe_mcp.server import (  # noqa: E402
    app,
    describe_registered_tools,
    get_agent_context_manager,
    get_agent_identity,
    get_execution_context,
    invoke_tool,
    list_registered_tools,
    main,
)

__all__ = [
    "app",
    "describe_registered_tools",
    "get_agent_context_manager",
    "get_agent_identity",
    "get_execution_context",
    "invoke_tool",
    "list_registered_tools",
    "main",
]


if __name__ == "__main__":
    asyncio.run(main())
