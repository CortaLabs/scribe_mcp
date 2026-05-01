from __future__ import annotations

from typing import Any, Dict, Optional

from scribe_mcp.server import app
from scribe_mcp.tool_contracts import read_only_local_tool
from scribe_mcp.log_intelligence import build_report_from_path


@app.tool(**read_only_local_tool(title="Analyze Log Intelligence", tags=("logs", "inspection", "read-only")))
async def analyze_logs(agent: str, path: str, project: Optional[str] = None) -> Dict[str, Any]:
    del agent
    return build_report_from_path(path, project=project)
