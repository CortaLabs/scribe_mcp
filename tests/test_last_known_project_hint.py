import sqlite3
from datetime import datetime, timedelta, timezone

from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import ProjectResolutionError
from scribe_mcp.shared.project_registry import ProjectRegistry


def test_translate_project_error_includes_last_known_project_hint(tmp_path):
    registry = ProjectRegistry()

    now = datetime.now(timezone.utc)
    last_access = now - timedelta(minutes=7)

    with sqlite3.connect(registry._db_path) as conn:  # noqa: SLF001 - test-only access
        conn.execute(
            """
            INSERT OR REPLACE INTO scribe_projects (name, repo_root, progress_log_path, created_at, last_access_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("hint_project", "/tmp/repo", "/tmp/repo/PROGRESS_LOG.md", now.isoformat(), last_access.isoformat()),
        )
        conn.commit()

    error = ProjectResolutionError("No project configured.", recent_projects=["hint_project"])
    payload = LoggingToolMixin.translate_project_error(error)

    assert payload["ok"] is False
    assert payload["last_known_project"] == "hint_project"
    assert isinstance(payload["last_known_project_minutes_ago"], int)
    assert payload["last_known_project_minutes_ago"] >= 0
