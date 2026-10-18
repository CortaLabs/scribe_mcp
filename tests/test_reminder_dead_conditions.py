"""P5.1 — reminder engine dead-condition coverage + priority sort (WS3 Findings 1+4).

Behavioral contract tests for src/scribe_mcp/utils/reminder_engine.py:

1. Every ``condition``/``trigger`` string declared in config/reminder_rules.json
   resolves to a real handler in ``_evaluate_condition`` (no silently-dead
   conditions), and each of the 16 previously-dead conditions evaluates
   correctly from a constructed ReminderContext.
2. ``get_priority`` (inside ``_select_reminders``) keys on ``reminder.category``
   against ``category_weights`` rather than ``reminder.level``, so a
   missing_docs/teaching/context reminder is ordered by its category weight.
"""

from __future__ import annotations

import json
from pathlib import Path

from scribe_mcp.utils.reminder_engine import (
    ReminderContext,
    ReminderEngine,
    ReminderInstance,
)


def _ctx(**overrides) -> ReminderContext:
    """Construct a ReminderContext with neutral defaults, overriding fields."""
    base = dict(
        tool_name="set_project",
        project_name="proj",
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
    base.update(overrides)
    return ReminderContext(**base)


def _rules_path() -> Path:
    # config/reminder_rules.json is shipped next to the engine config.
    return (
        Path(__file__).resolve().parent.parent
        / "src"
        / "scribe_mcp"
        / "config"
        / "reminder_rules.json"
    )


def _all_trigger_strings() -> set[str]:
    rules = json.loads(_rules_path().read_text(encoding="utf-8"))
    triggers: set[str] = set()
    for section in ("conditions", "teaching_rules"):
        for rule in rules.get(section, {}).values():
            for trig in rule.get("triggers", []):
                triggers.add(trig)
    return triggers


def _en_us_path() -> Path:
    # config/reminders/en-US.json ships the teaching template copy.
    return (
        Path(__file__).resolve().parent.parent
        / "src"
        / "scribe_mcp"
        / "config"
        / "reminders"
        / "en-US.json"
    )


def _new_project_welcome() -> dict:
    locale = json.loads(_en_us_path().read_text(encoding="utf-8"))
    return locale["reminders"]["teaching"]["new_project_welcome"]


# ---------------------------------------------------------------------------
# P7.4 (WS7 T3-1) — new_project_welcome hint points at the canonical skills
# ---------------------------------------------------------------------------


def test_new_project_welcome_template_points_at_scribe_integration_skill() -> None:
    """The first-bind teaching template must name /scribe-integration so agents
    can discover the canonical Scribe tool+workflow reference, plus
    /scribe-onboarding for install."""
    template = _new_project_welcome()
    assert "/scribe-integration" in template["template"]
    assert "/scribe-onboarding" in template["template"]
    # The compact variant carries the pointer too (some hosts use short_template).
    assert "/scribe-integration" in template["short_template"]


def test_new_project_welcome_pointer_stays_on_first_bind_only() -> None:
    """T3-3 guard: the pointer rides the EXISTING new-project first-bind
    condition (no new trigger, never wired to the warm-rebind/fire-every-call
    path). The conditions must remain exactly the new-project set_project gate."""
    template = _new_project_welcome()
    assert template["conditions"] == {"new_project": True, "tool": "set_project"}
    # It rides the existing teaching gate — no per-reminder enable toggle was added.
    assert template["category"] == "teaching"


# ---------------------------------------------------------------------------
# Finding 1 — every declared trigger has a live handler
# ---------------------------------------------------------------------------


def test_every_rules_trigger_has_a_handler() -> None:
    """No condition string in reminder_rules.json may be silently dead.

    A handler is "live" if there exists at least one ReminderContext under
    which it returns True. We probe each trigger with a context engineered to
    satisfy it; any trigger that can never be True indicates a missing handler.
    """
    engine = ReminderEngine()
    triggers = _all_trigger_strings()
    assert triggers, "expected reminder_rules.json to declare triggers"

    # Build a maximal context that satisfies every known trigger form at once,
    # plus targeted per-trigger contexts where a single context cannot.
    dead: list[str] = []
    for trig in sorted(triggers):
        ctx = _context_satisfying(trig)
        if not engine._evaluate_condition(trig, ctx):
            dead.append(trig)
    assert not dead, f"dead (unhandled) conditions: {dead}"


def _context_satisfying(trigger: str) -> ReminderContext:
    """Return a ReminderContext crafted to make ``trigger`` evaluate True."""
    if trigger == "no_log_entries":
        return _ctx(total_entries=0)
    if trigger == "always":
        return _ctx()
    if trigger == "docs_missing":
        return _ctx(docs_status={"architecture": "missing"})
    if trigger == "docs_changed":
        return _ctx(docs_changed=["ARCHITECTURE_GUIDE.md"])
    if trigger == "architecture_complete":
        return _ctx(docs_status={"architecture": "complete"})
    if trigger == "architecture_incomplete":
        return _ctx(docs_status={"architecture": "draft"})
    if trigger == "phase_plan_complete":
        return _ctx(docs_status={"phase_plan": "complete"})
    if trigger == "phase_plan_incomplete":
        return _ctx(docs_status={"phase_plan": "draft"})
    if trigger == "checklist_incomplete":
        return _ctx(docs_status={"checklist": "draft"})
    if trigger.startswith("minutes_since_log > "):
        n = int(trigger.split()[-1])
        return _ctx(minutes_since_log=n + 1)
    if trigger.startswith("log_entries > "):
        n = int(trigger.split()[-1])
        return _ctx(total_entries=n + 1)
    if trigger.startswith("total_items > "):
        n = int(trigger.split()[-1])
        return _ctx(variables={"total_items": n + 1})
    if trigger.startswith("doc_stale_days > "):
        n = int(trigger.split()[-1])
        return _ctx(variables={"doc_stale_days": n + 1})
    if trigger.startswith("tool="):
        return _ctx(tool_name=trigger.split("=", 1)[1])
    if trigger.startswith("action="):
        return _ctx(variables={"action": trigger.split("=", 1)[1]})
    if trigger.startswith("scaffold="):
        return _ctx(variables={"scaffold": trigger.split("=", 1)[1] == "true"})
    if trigger == "no_project=true":
        return _ctx(project_name=None)
    if "=" in trigger:
        name, _, value = trigger.partition("=")
        return _ctx(variables={name: value == "true"})
    raise AssertionError(f"test has no satisfying context for trigger {trigger!r}")


# ---------------------------------------------------------------------------
# Finding 1 — the 16 previously-dead conditions each fire correctly
# ---------------------------------------------------------------------------


def test_doc_status_conditions_fire_and_negate() -> None:
    engine = ReminderEngine()
    # complete vs incomplete are mutually exclusive on real status.
    complete = _ctx(docs_status={"architecture": "complete", "phase_plan": "complete", "checklist": "complete"})
    incomplete = _ctx(docs_status={"architecture": "draft", "phase_plan": "draft", "checklist": "draft"})

    assert engine._evaluate_condition("architecture_complete", complete) is True
    assert engine._evaluate_condition("architecture_incomplete", complete) is False
    assert engine._evaluate_condition("architecture_incomplete", incomplete) is True
    assert engine._evaluate_condition("architecture_complete", incomplete) is False

    assert engine._evaluate_condition("phase_plan_complete", complete) is True
    assert engine._evaluate_condition("phase_plan_incomplete", incomplete) is True
    assert engine._evaluate_condition("checklist_incomplete", incomplete) is True
    assert engine._evaluate_condition("checklist_incomplete", complete) is False


def test_missing_doc_status_is_treated_as_incomplete() -> None:
    """A status that is absent or 'missing' must read as incomplete, not complete."""
    engine = ReminderEngine()
    empty = _ctx(docs_status={})
    assert engine._evaluate_condition("architecture_incomplete", empty) is True
    assert engine._evaluate_condition("architecture_complete", empty) is False


def test_log_entries_threshold_conditions() -> None:
    engine = ReminderEngine()
    assert engine._evaluate_condition("log_entries > 5", _ctx(total_entries=6)) is True
    assert engine._evaluate_condition("log_entries > 5", _ctx(total_entries=5)) is False
    assert engine._evaluate_condition("log_entries > 10", _ctx(total_entries=11)) is True
    assert engine._evaluate_condition("log_entries > 10", _ctx(total_entries=10)) is False


def test_docs_changed_condition() -> None:
    engine = ReminderEngine()
    assert engine._evaluate_condition("docs_changed", _ctx(docs_changed=["a.md"])) is True
    assert engine._evaluate_condition("docs_changed", _ctx(docs_changed=[])) is False


def test_doc_stale_days_condition() -> None:
    engine = ReminderEngine()
    assert engine._evaluate_condition("doc_stale_days > 7", _ctx(variables={"doc_stale_days": 8})) is True
    assert engine._evaluate_condition("doc_stale_days > 7", _ctx(variables={"doc_stale_days": 7})) is False
    # Absent variable must fail closed, not raise.
    assert engine._evaluate_condition("doc_stale_days > 7", _ctx()) is False


def test_total_items_threshold_conditions() -> None:
    engine = ReminderEngine()
    assert engine._evaluate_condition("total_items > 3", _ctx(variables={"total_items": 4})) is True
    assert engine._evaluate_condition("total_items > 3", _ctx(variables={"total_items": 3})) is False
    assert engine._evaluate_condition("total_items > 5", _ctx(variables={"total_items": 6})) is True
    assert engine._evaluate_condition("total_items > 5", _ctx()) is False  # missing -> closed


def test_boolean_flag_conditions() -> None:
    engine = ReminderEngine()
    # not_compact=true
    assert engine._evaluate_condition("not_compact=true", _ctx(variables={"not_compact": True})) is True
    assert engine._evaluate_condition("not_compact=true", _ctx(variables={"not_compact": False})) is False
    # has_pagination=false
    assert engine._evaluate_condition("has_pagination=false", _ctx(variables={"has_pagination": False})) is True
    assert engine._evaluate_condition("has_pagination=false", _ctx(variables={"has_pagination": True})) is False
    # no_filter=true
    assert engine._evaluate_condition("no_filter=true", _ctx(variables={"no_filter": True})) is True
    # no_meta=true
    assert engine._evaluate_condition("no_meta=true", _ctx(variables={"no_meta": True})) is True
    assert engine._evaluate_condition("no_meta=true", _ctx(variables={"no_meta": False})) is False
    # absent flag fails closed
    assert engine._evaluate_condition("no_filter=true", _ctx()) is False


def test_no_project_condition_falls_back_to_project_name() -> None:
    engine = ReminderEngine()
    # No explicit flag: derive from project_name being unset.
    assert engine._evaluate_condition("no_project=true", _ctx(project_name=None)) is True
    assert engine._evaluate_condition("no_project=true", _ctx(project_name="proj")) is False
    # Explicit flag still honored.
    assert engine._evaluate_condition("no_project=true", _ctx(project_name="proj", variables={"no_project": True})) is True


def test_existing_handlers_still_work() -> None:
    """Regression guard: the original 7 handled forms still behave."""
    engine = ReminderEngine()
    assert engine._evaluate_condition("no_log_entries", _ctx(total_entries=0)) is True
    assert engine._evaluate_condition("no_log_entries", _ctx(total_entries=3)) is False
    assert engine._evaluate_condition("always", _ctx()) is True
    assert engine._evaluate_condition("docs_missing", _ctx(docs_status={"x": "missing"})) is True
    assert engine._evaluate_condition("minutes_since_log > 30", _ctx(minutes_since_log=31)) is True
    assert engine._evaluate_condition("minutes_since_log > 30", _ctx(minutes_since_log=None)) is False
    assert engine._evaluate_condition("tool=set_project", _ctx(tool_name="set_project")) is True
    assert engine._evaluate_condition("tool=set_project", _ctx(tool_name="append_entry")) is False
    assert engine._evaluate_condition("action=replace_section", _ctx(variables={"action": "replace_section"})) is True
    assert engine._evaluate_condition("scaffold=true", _ctx(variables={"scaffold": True})) is True
    assert engine._evaluate_condition("scaffold=false", _ctx(variables={"scaffold": False})) is True


def test_unknown_condition_returns_false() -> None:
    engine = ReminderEngine()
    assert engine._evaluate_condition("totally_made_up", _ctx()) is False


# ---------------------------------------------------------------------------
# Finding 4 — get_priority keys on category, not level
# ---------------------------------------------------------------------------


def _make(key: str, category: str, level: str) -> ReminderInstance:
    return ReminderInstance(key=key, level=level, emoji="ℹ️", message="m", category=category)


def test_get_priority_orders_by_category_weight() -> None:
    """Reminders not in priority_order must be ordered by category weight.

    category_weights (config) ranks missing_docs(900) > teaching(300) >
    context(200). With the old level-keyed fallback these all collapsed to the
    same bucket (level 'info' -> 100, or the 999 default) and were effectively
    unordered. Keying on category restores the intended ordering.
    """
    import asyncio

    engine = ReminderEngine()
    # Keys deliberately absent from priority_order so the category fallback runs.
    # "unlimited_tool" has no tool_specific_limits entry -> all categories kept.
    ctx = _ctx(tool_name="unlimited_tool")

    context_reminder = _make("context.project_context", "context", "info")
    teaching_reminder = _make("teaching.scribe_workflow_tip", "teaching", "info")
    missing_reminder = _make("documentation.missing_docs", "missing_docs", "warning")

    candidates = [context_reminder, teaching_reminder, missing_reminder]

    # _select_reminders applies the sort; patch _should_show to keep all.
    async def _keep_all(reminder, context):  # noqa: ANN001
        return True

    engine._should_show_reminder_async = _keep_all  # type: ignore[method-assign]

    selected = asyncio.run(engine._select_reminders(list(candidates), ctx))
    order = [r.category for r in selected]
    assert order == ["missing_docs", "teaching", "context"], order


def test_get_priority_level_is_secondary_tiebreak() -> None:
    """When two reminders share a category, level breaks the tie."""
    import asyncio

    engine = ReminderEngine()
    ctx = _ctx(tool_name="unlimited_tool")

    # Same (unknown-to-priority_order) category 'teaching'; different levels.
    urgent_level = _make("teaching.a", "teaching", "urgent")   # level urgent -> weight 1000
    info_level = _make("teaching.b", "teaching", "info")       # level info -> weight 100

    async def _keep_all(reminder, context):  # noqa: ANN001
        return True

    engine._should_show_reminder_async = _keep_all  # type: ignore[method-assign]

    selected = asyncio.run(engine._select_reminders([info_level, urgent_level], ctx))
    keys = [r.key for r in selected]
    assert keys == ["teaching.a", "teaching.b"], keys


def test_priority_order_keys_still_win() -> None:
    """Keys present in priority_order outrank category-weight fallback."""
    import asyncio

    engine = ReminderEngine()
    ctx = _ctx(tool_name="unlimited_tool")

    # 'urgent_logging' is first in priority_order; a high-category-weight
    # reminder whose key is NOT in priority_order must still sort after it.
    in_order = _make("urgent_logging", "context", "info")
    fallback = _make("documentation.missing_docs", "missing_docs", "warning")

    async def _keep_all(reminder, context):  # noqa: ANN001
        return True

    engine._should_show_reminder_async = _keep_all  # type: ignore[method-assign]

    selected = asyncio.run(engine._select_reminders([fallback, in_order], ctx))
    assert selected[0].key == "urgent_logging", [r.key for r in selected]
