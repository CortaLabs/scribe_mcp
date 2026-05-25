from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from scribe_mcp.doc_management.actions.query import inspect_document_sections_from_text

EDGE_FIELDS: tuple[str, ...] = (
    "depends_on",
    "supports",
    "validates",
    "supersedes",
    "blocked_by",
    "touches",
    "related_docs",
)
HARD_EDGE_FIELDS: set[str] = {"depends_on", "blocked_by", "supersedes"}


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned


def _derive_anchor_fallback(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    payload = inspect_document_sections_from_text(text)
    sections = payload.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if isinstance(section, dict):
                candidate = str(section.get("id") or "").strip()
                if candidate:
                    return candidate
    return None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _parse_entry(entry: Any) -> Dict[str, Any]:
    if isinstance(entry, str):
        return {"target_ref": entry.strip(), "relation_strength": "soft", "note": None}
    if isinstance(entry, dict):
        target = entry.get("target") or entry.get("target_ref") or ""
        return {
            "target_ref": str(target).strip(),
            "relation_strength": str(entry.get("relation") or "soft").strip() or "soft",
            "note": str(entry.get("note")).strip() if entry.get("note") is not None else None,
        }
    return {"target_ref": "", "relation_strength": "soft", "note": None}


def normalize_topology_edges(*, source_doc_id: str, source_doc_path: Path, edge_map: Dict[str, Any], docs_dir: Path, project_root: Path, registered_docs: Dict[str, Path]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    _ = source_doc_path
    for kind in EDGE_FIELDS:
        values = edge_map.get(kind)
        if not isinstance(values, list):
            continue
        for index, raw in enumerate(values):
            parsed = _parse_entry(raw)
            target_ref = parsed["target_ref"]
            if not target_ref:
                continue
            target_path, target_doc_id, target_anchor, target_resolved, state = resolve_topology_target(target_ref=target_ref, docs_dir=docs_dir, project_root=project_root, registered_docs=registered_docs)
            base = f"{source_doc_id}|{kind}|{target_ref}|{index}"
            edge_id = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
            edges.append({"edge_id": edge_id, "kind": kind, "source_doc_id": source_doc_id, "source_field": kind, "target_ref": target_ref, "target_doc_id": target_doc_id, "target_path": str(target_path) if target_path else None, "target_anchor": target_anchor, "target_resolved": target_resolved, "relation_strength": parsed["relation_strength"], "state": state, "note": parsed["note"]})
    return edges


def resolve_topology_target(*, target_ref: str, docs_dir: Path, project_root: Path, registered_docs: Dict[str, Path]) -> tuple[Optional[Path], Optional[str], Optional[str], bool, str]:
    ref = target_ref.strip()
    path_part, anchor_part = (ref.split("#", 1) + [None])[:2]
    if path_part in registered_docs:
        resolved_path = registered_docs[path_part].resolve()
        if not _is_within(resolved_path, project_root):
            return None, None, anchor_part, False, "rejected_outside_repo"
        if not _is_within(resolved_path, docs_dir):
            return None, None, anchor_part, False, "rejected_cross_project"
        anchor = anchor_part.strip() if isinstance(anchor_part, str) and anchor_part.strip() else _derive_anchor_fallback(resolved_path)
        return resolved_path, _slug(path_part), anchor, resolved_path.exists(), "ok"
    candidate = Path(path_part)
    candidate = candidate.resolve() if candidate.is_absolute() else (docs_dir / candidate).resolve()
    if not _is_within(candidate, project_root):
        return None, None, anchor_part, False, "rejected_outside_repo"
    if not _is_within(candidate, docs_dir):
        return None, None, anchor_part, False, "rejected_cross_project"
    explicit_anchor = anchor_part.strip() if isinstance(anchor_part, str) and anchor_part.strip() else None
    anchor = explicit_anchor or _derive_anchor_fallback(candidate)
    return candidate, _slug(candidate.stem), anchor, candidate.exists(), "ok"


def detect_hard_dependency_cycles(edges: Iterable[Dict[str, Any]]) -> List[List[str]]:
    adjacency: Dict[str, List[str]] = {}
    for edge in edges:
        if edge.get("kind") not in HARD_EDGE_FIELDS:
            continue
        source = edge.get("source_doc_id")
        target = edge.get("target_doc_id")
        if isinstance(source, str) and source and isinstance(target, str) and target:
            adjacency.setdefault(source, []).append(target)
    cycles: List[List[str]] = []
    seen: set[tuple[str, ...]] = set()

    def _canonical_cycle_key(cycle: List[str]) -> tuple[str, ...]:
        body = cycle[:-1]
        rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
        return min(rotations)

    def _visit(node: str, stack: List[str], active: set[str]) -> None:
        if node in active:
            idx = stack.index(node)
            cycle = stack[idx:] + [node]
            key = _canonical_cycle_key(cycle)
            if key not in seen:
                seen.add(key)
                cycles.append(cycle)
            return
        active.add(node)
        stack.append(node)
        for nxt in sorted(adjacency.get(node, [])):
            _visit(nxt, stack, active)
        stack.pop()
        active.remove(node)

    for node in sorted(adjacency):
        _visit(node, [], set())
    return sorted(cycles)
