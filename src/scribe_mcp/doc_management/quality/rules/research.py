from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _research_warning(*, code: str, excerpt: str, message: str, repair: str, warning_policies: dict[str, dict[str, Any]]) -> Dict[str, Any]:
    policy = warning_policies[code]
    return {
        "code": code,
        "severity": policy["severity"],
        "blocking": bool(policy["blocking"]),
        "location": {"line": 1, "column": 1},
        "excerpt": excerpt,
        "message": message,
        "suggested_repair": repair,
        "source_owner": "research",
    }


def build_research_index_hygiene_warnings(*, research_dir: Path, warning_policies: dict[str, dict[str, Any]], changed_path: Optional[Path] = None, canonical_research_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    research_dir = research_dir.resolve()
    canonical_dir = (canonical_research_dir or research_dir).resolve()
    index_path = research_dir / "INDEX.md"
    research_docs = sorted(
        p for p in research_dir.rglob("*.md") if p.name != "INDEX.md" and not p.name.startswith("_")
    )
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

    if changed_path and changed_path.suffix.lower() == ".md" and changed_path.name != "INDEX.md":
        changed_resolved = changed_path.resolve()
        try:
            relative_to_canonical = changed_resolved.relative_to(canonical_dir)
            noncanonical = len(relative_to_canonical.parts) != 1
        except ValueError:
            noncanonical = True
        if noncanonical:
            nested_inside_canonical = False
            try:
                changed_resolved.relative_to(canonical_dir)
                nested_inside_canonical = True
            except ValueError:
                nested_inside_canonical = False
            warnings.append(
                _research_warning(
                    code="SCF_NONCANONICAL_LOCATION",
                    excerpt=str(changed_path),
                    message=(
                        "Research artifact is not in canonical flat research placement. "
                        "Files are expected directly under .scribe/docs/dev_plans/<project>/research/."
                        if nested_inside_canonical
                        else "Research artifact is outside canonical research storage and may not be indexed as expected."
                    ),
                    repair=(
                        "Rehome the artifact to the top-level canonical research directory and regenerate research/INDEX.md."
                        if nested_inside_canonical
                        else "Move the artifact into the canonical research directory and regenerate research/INDEX.md."
                    ),
                    warning_policies=warning_policies,
                )
            )

    if not index_path.exists():
        warnings.append(
            _research_warning(
                code="SCF_INDEX_MISSING",
                excerpt=str(index_path),
                message="Research index is missing.",
                repair="Run a research-doc create/edit flow to regenerate research/INDEX.md.",
                warning_policies=warning_policies,
            )
        )
        return warnings

    if changed_path and changed_path.suffix.lower() == ".md":
        try:
            rel_name = changed_path.name
            if rel_name != "INDEX.md" and rel_name not in index_text:
                warnings.append(
                    _research_warning(
                        code="SCF_DOC_UNINDEXED",
                        excerpt=rel_name,
                        message="Research document is unindexed: it is not listed in research/INDEX.md.",
                        repair="Regenerate the research index by editing or creating a research document.",
                        warning_policies=warning_policies,
                    )
                )
        except Exception:
            pass

    for match in re.finditer(r"\]\(([^)]+\.md)\)", index_text):
        linked = match.group(1).strip()
        if "://" in linked or linked.startswith("#"):
            continue
        linked_path = (research_dir / linked).resolve()
        try:
            linked_path.relative_to(research_dir)
        except ValueError:
            continue
        if not linked_path.exists():
            warnings.append(
                _research_warning(
                    code="SCF_DOC_UNINDEXED",
                    excerpt=linked,
                    message="Research index references an orphaned artifact that no longer exists.",
                    repair="Regenerate research/INDEX.md so removed or rehomed artifacts are dropped from the index.",
                    warning_policies=warning_policies,
                )
            )
            break

    for doc in research_docs:
        try:
            display_name = str(doc.relative_to(research_dir))
        except ValueError:
            display_name = doc.name
        if doc.name not in index_text and display_name not in index_text:
            warnings.append(
                _research_warning(
                    code="SCF_INDEX_STALE",
                    excerpt=display_name,
                    message="Research index appears stale relative to research artifacts.",
                    repair="Trigger research index refresh through managed-doc mutation flow.",
                    warning_policies=warning_policies,
                )
            )
            break

    return warnings
