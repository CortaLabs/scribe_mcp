from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

RuleWarnings = List[Dict[str, Any]]
ActivationPredicate = Callable[[Mapping[str, Any]], bool]
RuleEvaluator = Callable[[Mapping[str, Any]], RuleWarnings]


@dataclass(frozen=True)
class QualityRuleEntry:
    """Metadata + evaluator contract for deterministic quality execution."""

    key: str
    order: int
    evaluator: RuleEvaluator
    metadata: Mapping[str, Any]
    is_active: ActivationPredicate


def always_active(_context: Mapping[str, Any]) -> bool:
    return True


def doc_name_is(*names: str) -> ActivationPredicate:
    normalized = {name.strip().lower() for name in names if name.strip()}

    def _predicate(context: Mapping[str, Any]) -> bool:
        doc_name = str(context.get("doc_name") or "").strip().lower()
        return doc_name in normalized

    return _predicate


def research_target_only(context: Mapping[str, Any]) -> bool:
    return bool(context.get("is_research_target", False))


class QualityRuleRegistry:
    """Ordered registry for scaffold quality warnings."""

    def __init__(self, entries: Optional[Iterable[QualityRuleEntry]] = None) -> None:
        self._entries: List[QualityRuleEntry] = []
        if entries:
            for entry in entries:
                self.register(entry)

    def register(self, entry: QualityRuleEntry) -> None:
        self._entries.append(entry)
        self._entries.sort(key=lambda item: (item.order, item.key))

    def ordered_entries(self) -> Sequence[QualityRuleEntry]:
        return tuple(self._entries)

    def evaluate(self, *, context: Mapping[str, Any]) -> RuleWarnings:
        warnings: RuleWarnings = []
        for entry in self._entries:
            if not entry.is_active(context):
                continue
            warnings.extend(entry.evaluator(context))
        return warnings
