from __future__ import annotations

from datetime import datetime, timezone

from scribe_mcp.utils.reminder_engine import ReminderContext, ReminderEngine


def test_reminder_engine_adds_now_variables() -> None:
    engine = ReminderEngine()
    context = ReminderContext(
        tool_name="set_project",
        project_name="x",
        project_root="/tmp/repo",
        agent_id="agent",
        total_entries=0,
        minutes_since_log=None,
        last_log_time=None,
        docs_status={},
        docs_changed=[],
        current_phase=None,
        session_age_minutes=None,
        variables={},
    )

    variables = engine._build_variables(context)
    assert "now_utc" in variables
    assert "now_iso_utc" in variables
    assert "date_utc" in variables
    assert "time_utc" in variables

    parsed = datetime.fromisoformat(variables["now_iso_utc"])
    assert parsed.tzinfo is not None
    assert parsed.tzinfo.utcoffset(parsed) == timezone.utc.utcoffset(parsed)
