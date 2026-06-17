from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from scribe_mcp.server import app
from scribe_mcp.tool_contracts import read_only_local_tool
from scribe_mcp.log_intelligence import build_report_from_path

_PATH_SUGGESTION = "Provide a path to an existing readable log file."


@app.tool(**read_only_local_tool(title="Analyze Log Intelligence", tags=("logs", "inspection", "read-only")))
async def analyze_logs(agent: str, path: str, project: Optional[str] = None) -> Dict[str, Any]:
    del agent
    # Boundary validation: MCP tools return error dictionaries, never raise to the
    # host (.claude/rules/error-handling.md). The inner builder reads the file with
    # no guard, so a missing/dir/unreadable path would propagate a raw OSError.
    if not isinstance(path, str) or not path.strip():
        return {
            "ok": False,
            "error": "path must be a non-empty string",
            "suggestion": _PATH_SUGGESTION,
        }
    file_path = Path(path)
    if not file_path.is_file():
        return {
            "ok": False,
            "error": f"log path is not an existing file: {path}",
            "path": str(file_path),
            "suggestion": _PATH_SUGGESTION,
        }
    try:
        return build_report_from_path(path, project=project)
    except OSError as exc:
        return {
            "ok": False,
            "error": f"could not read log file: {exc}",
            "path": str(file_path),
            "suggestion": _PATH_SUGGESTION,
        }
