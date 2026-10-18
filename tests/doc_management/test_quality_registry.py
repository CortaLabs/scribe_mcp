from __future__ import annotations

from scribe_mcp.doc_management.quality.results import normalize_warnings
from scribe_mcp.doc_management.quality.registry import QualityRuleEntry, QualityRuleRegistry


def test_registry_evaluates_in_deterministic_order_with_activation_filters() -> None:
    calls: list[str] = []

    def make_rule(name: str):
        def _eval(_context):
            calls.append(name)
            return [{"code": name}]

        return _eval

    registry = QualityRuleRegistry(
        entries=(
            QualityRuleEntry(
                key="third",
                order=30,
                evaluator=make_rule("third"),
                metadata={"family": "test"},
                is_active=lambda _ctx: True,
            ),
            QualityRuleEntry(
                key="first",
                order=10,
                evaluator=make_rule("first"),
                metadata={"family": "test"},
                is_active=lambda _ctx: True,
            ),
            QualityRuleEntry(
                key="skip",
                order=20,
                evaluator=make_rule("skip"),
                metadata={"family": "test"},
                is_active=lambda _ctx: False,
            ),
            QualityRuleEntry(
                key="second",
                order=20,
                evaluator=make_rule("second"),
                metadata={"family": "test"},
                is_active=lambda _ctx: True,
            ),
        )
    )

    warnings = registry.evaluate(context={"doc_name": "SPEC"})

    assert [entry.key for entry in registry.ordered_entries()] == ["first", "second", "skip", "third"]
    assert calls == ["first", "second", "third"]
    assert [warning["code"] for warning in warnings] == ["first", "second", "third"]


def test_normalize_warnings_orders_by_explicit_severity_rank() -> None:
    warnings = [
        {"severity": "low", "code": "A_LOW"},
        {"severity": "critical", "code": "Z_CRIT"},
        {"severity": "high", "code": "M_HIGH"},
    ]
    normalized = normalize_warnings(warnings)
    assert [w["code"] for w in normalized] == ["Z_CRIT", "M_HIGH", "A_LOW"]
