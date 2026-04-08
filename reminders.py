"""Compatibility shim for reminder imports during src-layout migration."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from scribe_mcp.reminders import *  # noqa: F401,F403,E402
