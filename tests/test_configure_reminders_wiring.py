"""P5.3 — configure_reminders wiring (WS3 Finding 3).

Behavioral contract tests proving the four ``configure_reminders`` knobs
(``enabled`` / ``cooldown_minutes`` / ``categories`` / ``tone``) persisted into
``defaults.reminder`` are actually consumed by the main reminder engine.

Two layers are covered:

1. **Read side** (``src/scribe_mcp/reminders.py::_build_legacy_context``): the
   top-level ``defaults.reminder`` knobs are normalized and threaded into
   ``ReminderContext.variables`` as ``main_reminder_*`` keys.
2. **Engine side** (``src/scribe_mcp/utils/reminder_engine.py``): each knob
   measurably changes ``generate_reminders`` / ``to_dict_list`` output —
   ``enabled=False`` gates the whole engine (recorded decision), ``categories``
   filters, ``cooldown_minutes`` suppresses same-key repeats, ``tone`` is applied.

These would have caught Finding 3: before the fix the knobs were saved but never
read by the main engine.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scribe_mcp.utils.reminder_engine import ReminderContext, ReminderEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine() -> ReminderEngine:
    """A fresh engine (packaged config, no storage -> in-memory cooldowns)."""
    return ReminderEngine()


def _ctx(variables: dict, **overrides) -> ReminderContext:
    """A context that fires reminders across context/docs/logging categories.

    ``probe_tool`` is intentionally NOT in ``selection.tool_specific_limits``,
    so it inherits the permissive default (``["all"]`` categories, behavior
    ``max_reminders_per_call``) — giving a multi-category surface to filter.
    """
    base = dict(
        tool_name="probe_tool",
        project_name="proj",
        project_root="/tmp/repo",
        agent_id="agent",
        total_entries=0,
        minutes_since_log=120,
        last_log_time=None,
        docs_status={"architecture": "missing", "phase_plan": "missing"},
        docs_changed=[],
        current_phase=None,
        session_age_minutes=None,
        variables=variables,
    )
    base.update(overrides)
    return ReminderContext(**base)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Read side — _build_legacy_context threads the four knobs into variables
# ---------------------------------------------------------------------------


def test_build_legacy_context_threads_main_reminder_knobs():
    """defaults.reminder top-level knobs land in ReminderContext.variables."""
    from scribe_mcp import reminders as reminders_mod

    project = {
        "name": "proj",
        "root": "/tmp/repo",
        "progress_log": "/tmp/repo/PROGRESS_LOG.md",
        "defaults": {
            "reminder": {
                "enabled": False,
                "cooldown_minutes": 45,
                "categories": ["Logging", "context"],
                "tone": "Gentle",
            }
        },
    }

    context = _run(
        reminders_mod._build_legacy_context(project, "read_recent", None)
    )

    assert context.variables["main_reminder_enabled"] is False
    assert context.variables["main_reminder_cooldown_minutes"] == 45
    # normalized to lowercase, order preserved
    assert context.variables["main_reminder_categories"] == ["logging", "context"]
    assert context.variables["main_reminder_tone"] == "gentle"


def test_build_legacy_context_defaults_when_no_reminder_cfg():
    """Absent defaults.reminder -> enabled defaults True, rest None."""
    from scribe_mcp import reminders as reminders_mod

    project = {
        "name": "proj",
        "root": "/tmp/repo",
        "progress_log": "/tmp/repo/PROGRESS_LOG.md",
    }

    context = _run(
        reminders_mod._build_legacy_context(project, "read_recent", None)
    )

    assert context.variables["main_reminder_enabled"] is True
    assert context.variables["main_reminder_cooldown_minutes"] is None
    assert context.variables["main_reminder_categories"] is None
    assert context.variables["main_reminder_tone"] is None


# ---------------------------------------------------------------------------
# Engine side — enabled gate (recorded decision: gates the WHOLE engine)
# ---------------------------------------------------------------------------


def test_enabled_false_gates_whole_engine():
    engine = _engine()
    enabled = _run(engine.generate_reminders(_ctx({})))
    assert len(enabled) > 0, "baseline context should fire reminders"

    disabled = _run(
        engine.generate_reminders(_ctx({"main_reminder_enabled": False}))
    )
    assert disabled == [], "enabled=False must silence the whole main engine"


def test_enabled_true_and_absent_both_produce_reminders():
    engine = _engine()
    explicit = _run(
        engine.generate_reminders(_ctx({"main_reminder_enabled": True}))
    )
    absent = _run(engine.generate_reminders(_ctx({})))
    assert len(explicit) > 0
    assert len(absent) > 0


# ---------------------------------------------------------------------------
# Engine side — categories filter
# ---------------------------------------------------------------------------


def test_categories_filter_excludes_other_categories():
    engine = _engine()
    baseline = _run(engine.generate_reminders(_ctx({})))
    baseline_cats = {r.category for r in baseline}
    assert "logging" in baseline_cats
    assert len(baseline_cats) > 1, "baseline should span multiple categories"

    filtered = _run(
        engine.generate_reminders(_ctx({"main_reminder_categories": ["logging"]}))
    )
    assert filtered, "logging reminders should survive the filter"
    assert {r.category for r in filtered} == {"logging"}


def test_categories_empty_or_none_does_not_filter():
    engine = _engine()
    baseline_cats = {r.category for r in _run(engine.generate_reminders(_ctx({})))}

    none_cats = {
        r.category
        for r in _run(
            engine.generate_reminders(_ctx({"main_reminder_categories": None}))
        )
    }
    assert none_cats == baseline_cats


# ---------------------------------------------------------------------------
# Engine side — cooldown suppresses same-key repeats within the window
# ---------------------------------------------------------------------------


def test_cooldown_suppresses_repeat_within_window():
    engine = _engine()
    ctx = _ctx({"main_reminder_cooldown_minutes": 60})

    first = _run(engine.generate_reminders(ctx))
    first_keys = {r.key for r in first}
    assert first_keys, "first call should emit reminders"

    second = _run(engine.generate_reminders(ctx))
    second_keys = {r.key for r in second}

    # No reminder emitted on the first call may re-appear within the window.
    assert first_keys.isdisjoint(second_keys), (
        f"cooldown must suppress same-key repeats: {first_keys & second_keys}"
    )

    # Steady state: once every distinct reminder has been shown, none remain.
    _run(engine.generate_reminders(ctx))
    final = _run(engine.generate_reminders(ctx))
    assert final == [], "all distinct reminders should be in cooldown by now"


def test_no_project_cooldown_allows_immediate_repeat():
    """Without a project cooldown, the baseline reminders re-emit."""
    engine = _engine()
    ctx = _ctx({})  # no main_reminder_cooldown_minutes

    first = {r.key for r in _run(engine.generate_reminders(ctx))}
    second = {r.key for r in _run(engine.generate_reminders(ctx))}
    # Reminders with no intrinsic cooldown repeat freely without a project floor.
    assert first & second, "absent project cooldown, reminders should repeat"


# ---------------------------------------------------------------------------
# Engine side — tone applied in the dict payload
# ---------------------------------------------------------------------------


def test_tone_applied_to_output():
    engine = _engine()
    reminders = _run(
        engine.generate_reminders(_ctx({"main_reminder_tone": "gentle"}))
    )
    payload = engine.to_dict_list(reminders)
    assert payload, "expected reminders to apply tone to"
    assert {row["tone"] for row in payload} == {"gentle"}


def test_tone_defaults_to_neutral_when_unset():
    engine = _engine()
    reminders = _run(engine.generate_reminders(_ctx({})))
    payload = engine.to_dict_list(reminders)
    assert payload
    assert {row["tone"] for row in payload} == {"neutral"}
