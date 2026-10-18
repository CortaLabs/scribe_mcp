from __future__ import annotations

from datetime import datetime, timezone

from scribe_mcp.utils.reminder_engine import ReminderContext, ReminderEngine, ReminderInstance


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


def test_reminder_serializer_exposes_action_guidance() -> None:
    engine = ReminderEngine()
    payload = engine.to_dict_list(
        [
            ReminderInstance(
                key="quality.scaffold_residue",
                level="warning",
                emoji="!",
                message="Clear readiness blockers.",
                category="scaffold_residue",
                recommended_action="Run quality_check and clear blockers.",
                available_actions=["manage_docs quality_check"],
                suggested_tool="manage_docs",
                blocker_codes=["SCF_READINESS_BLOCKERS"],
            )
        ]
    )

    reminder = payload[0]
    assert reminder["key"] == "quality.scaffold_residue"
    assert reminder["source"] == "core.scaffold_residue"
    assert reminder["recommended_action"] == "Run quality_check and clear blockers."
    assert reminder["available_actions"] == ["manage_docs quality_check"]
    assert reminder["suggested_tool"] == "manage_docs"
    assert reminder["blocker_codes"] == ["SCF_READINESS_BLOCKERS"]
