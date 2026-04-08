"""Compatibility package entrypoint shim for local repo execution."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from scribe_mcp.__main__ import main  # noqa: E402


if __name__ == "__main__":
    main()
