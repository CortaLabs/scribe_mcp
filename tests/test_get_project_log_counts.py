import pytest
from pathlib import Path

from scribe_mcp.config import log_config as log_config_module
from scribe_mcp.tools import get_project as get_project_tool


@pytest.mark.asyncio
async def test_compute_log_counts_counts_parsed_entries(tmp_path: Path) -> None:
    project = {
        "name": "X",
        "root": str(tmp_path),
        "docs_dir": str(tmp_path / ".scribe" / "docs" / "dev_plans" / "x"),
        "progress_log": str(tmp_path / ".scribe" / "docs" / "dev_plans" / "x" / "PROGRESS_LOG.md"),
    }
    (tmp_path / ".scribe" / "docs" / "dev_plans" / "x").mkdir(parents=True, exist_ok=True)

    logs = log_config_module.load_log_config()
    line = "[ℹ️] [2025-12-17 00:00:00 UTC] [Agent: Codex] [Project: X] hello\n"
    for log_type in logs.keys():
        definition = log_config_module.get_log_definition(log_type)
        path = log_config_module.resolve_log_path(project, definition)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(line + line, encoding="utf-8")

    counts = await get_project_tool._compute_log_counts(project)  # noqa: SLF001 - helper under test
    assert counts
    for log_type in logs.keys():
        assert counts.get(log_type) == 2
