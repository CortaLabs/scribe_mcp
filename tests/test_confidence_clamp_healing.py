"""Confidence input-healing tests for ``append_entry`` (WS1 F6).

Prior behavior: any out-of-range or non-numeric ``confidence`` was silently
rewritten to ``1.0`` (MAX) — the worst-direction default for a system whose
reminder engine flags *low*-confidence research, because it hid exactly the
signal the reminder system relies on.

F6 heals toward truth instead: numeric values clamp into ``[0.0, 1.0]``,
non-numeric values are omitted (``None``), and every correction is surfaced via
``parameter_healing``.

These tests exercise the pure, synchronous parameter validator directly so they
need no project/DB context (bounded — op count is independent of any input size).
"""

from __future__ import annotations

from scribe_mcp.tools.append_entry import _validate_and_prepare_parameters


def _validate(confidence):
    """Call the parameter validator with one varying field (confidence)."""
    config, info = _validate_and_prepare_parameters(
        message="entry",
        status=None,
        emoji=None,
        agent="test-agent",
        meta=None,
        timestamp_utc=None,
        items=None,
        items_list=None,
        auto_split=True,
        split_delimiter="\n",
        stagger_seconds=1,
        agent_id=None,
        log_type=None,
        priority=None,
        category=None,
        tags=None,
        confidence=confidence,
        config=None,
    )
    return config.confidence, info


def test_above_range_clamps_to_ceiling_and_heals():
    final, info = _validate(5)
    assert final == 1.0
    assert info["healing_applied"] is True
    assert "clamped to 1.0" in info["healed_params"]["confidence_healing"]


def test_below_range_clamps_to_floor_not_max():
    """The regression core of F6: a negative value clamps to 0.0, NOT to 1.0."""
    final, info = _validate(-0.5)
    assert final == 0.0  # NOT promoted to 1.0
    assert info["healing_applied"] is True
    assert "clamped to 0.0" in info["healed_params"]["confidence_healing"]


def test_non_numeric_is_omitted_not_promoted():
    final, info = _validate("high")
    assert final is None  # omitted, not silently recorded at MAX
    assert info["healing_applied"] is True
    assert "omitted" in info["healed_params"]["confidence_healing"]


def test_bool_is_treated_as_non_numeric_and_omitted():
    """bool is an int subclass; ``confidence=True`` is non-numeric intent, not 1.0."""
    final, info = _validate(True)
    assert final is None
    assert info["healing_applied"] is True
    assert "omitted" in info["healed_params"]["confidence_healing"]


def test_valid_value_passes_through_without_healing():
    final, info = _validate(0.85)
    assert final == 0.85
    assert info["healing_applied"] is False
    assert "confidence_healing" not in info["healed_params"]


def test_boundary_values_are_not_flagged_as_healed():
    for value in (0.0, 1.0):
        final, info = _validate(value)
        assert final == value
        assert "confidence_healing" not in info["healed_params"]


def test_none_confidence_is_left_untouched():
    final, info = _validate(None)
    assert final is None
    assert "confidence_healing" not in info["healed_params"]
