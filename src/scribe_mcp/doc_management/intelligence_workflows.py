from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from scribe_mcp.doc_management.scaffold_quality import parse_frontmatter
from scribe_mcp.doc_management.topology import detect_hard_dependency_cycles, normalize_topology_edges
from scribe_mcp.utils.frontmatter import apply_frontmatter_updates

_REPAIR_MODES = {"report_only", "repair_safe", "repair_assisted"}
_EDGE_FIELDS = {"depends_on", "supports", "validates", "supersedes", "blocked_by", "touches", "related_docs"}
_DOC_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _stable_doc_id(path: Path) -> str:
    return f"doc-{hashlib.sha1(str(path).encode('utf-8')).hexdigest()[:12]}"


def _metadata_for(path: Path) -> Dict[str, Any]:
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    data = parsed.frontmatter_data if isinstance(parsed.frontmatter_data, dict) else {}
    return dict(data)


def _doc_inventory(active_project: Mapping[str, Any]) -> List[Dict[str, Any]]:
    docs = active_project.get("docs") if isinstance(active_project.get("docs"), dict) else {}
    items_by_path: Dict[Path, Dict[str, Any]] = {}
    docs_dir_raw = str(active_project.get("docs_dir") or "").strip()
    docs_dir = Path(docs_dir_raw).resolve() if docs_dir_raw else None

    for name, raw_path in docs.items():
        if not isinstance(raw_path, str) or not raw_path.endswith(".md"):
            continue
        path = Path(raw_path).resolve()
        registered_aliases = [
            str(alias)
            for alias, alias_path in docs.items()
            if isinstance(alias_path, str) and Path(alias_path).resolve() == path
        ]
        if not path.exists() or not path.is_file():
            items_by_path[path] = {
                "doc_name": str(name),
                "path": path,
                "metadata": {},
                "registration_source": "docs_json_missing_file",
                "registered_aliases": sorted(set(registered_aliases)),
            }
            continue
        if path not in items_by_path:
            items_by_path[path] = {
                "doc_name": str(name),
                "path": path,
                "metadata": _metadata_for(path),
                "registration_source": "docs_json",
                "registered_aliases": sorted(set(registered_aliases)),
            }

    if docs_dir and docs_dir.exists():
        for path in sorted(docs_dir.rglob("*.md"), key=lambda candidate: str(candidate).lower()):
            resolved_path = path.resolve()
            if not resolved_path.is_file():
                continue
            existing = items_by_path.get(resolved_path)
            if existing is not None:
                continue
            items_by_path[resolved_path] = {
                "doc_name": resolved_path.stem,
                "path": resolved_path,
                "metadata": _metadata_for(resolved_path),
                "registration_source": "filesystem_only",
                "registered_aliases": [],
            }

    return sorted(items_by_path.values(), key=lambda item: (str(item["path"]).lower(), str(item["doc_name"]).lower()))


def topology_scan(*, active_project: Mapping[str, Any]) -> Dict[str, Any]:
    docs_dir = Path(str(active_project.get("docs_dir") or "")).resolve()
    project_root = Path(str(active_project.get("root") or "")).resolve()
    items = _doc_inventory(active_project)
    registered = {
        item["doc_name"]: item["path"]
        for item in items
        if item.get("registration_source") == "docs_json"
    }
    edges: List[Dict[str, Any]] = []
    duplicate_ids: Dict[str, List[str]] = {}
    id_to_docs: Dict[str, List[str]] = {}
    anomalies: List[Dict[str, Any]] = []

    for item in items:
        doc_id = str(item["metadata"].get("id") or item["doc_name"]).strip() or item["doc_name"]
        id_to_docs.setdefault(doc_id, []).append(str(item["path"]))
        edge_map = item["metadata"].get("topology") if isinstance(item["metadata"].get("topology"), dict) else {}
        for field, value in edge_map.items():
            if field in _EDGE_FIELDS and not isinstance(value, list):
                anomalies.append({"doc": item["doc_name"], "code": "INVALID_EDGE_SHAPE", "field": field, "proof": {"expected": "list", "actual": type(value).__name__}})
        edges.extend(normalize_topology_edges(source_doc_id=doc_id, source_doc_path=item["path"], edge_map=edge_map, docs_dir=docs_dir, project_root=project_root, registered_docs=registered))

    dangling = [e for e in edges if not e.get("target_resolved")]
    for doc_id, paths in id_to_docs.items():
        if len(paths) > 1:
            duplicate_ids[doc_id] = sorted(paths)

    return {
        "ok": True,
        "action": "topology_scan",
        "read_only": True,
        "snapshot": {
            "nodes": [{"doc_name": i["doc_name"], "path": str(i["path"]), "doc_id": str(i["metadata"].get("id") or i["doc_name"]) } for i in items],
            "edges": edges,
            "duplicate_ids": duplicate_ids,
            "dangling_targets": [{"edge_id": e.get("edge_id"), "target_ref": e.get("target_ref"), "state": e.get("state"), "proof": {"code": "UNRESOLVED_TARGET"}} for e in dangling],
            "anomalies": anomalies + [
                {
                    "doc": item["doc_name"],
                    "code": "DOC_REGISTRY_DRIFT",
                    "registration_source": item.get("registration_source"),
                    "path": str(item["path"]),
                    "proof": {
                        "registered_aliases": item.get("registered_aliases", []),
                        "available_action": "Register the file through manage_docs(create/rehome_doc) or repair/remove the stale docs_json mapping.",
                    },
                }
                for item in items
                if item.get("registration_source") in {"filesystem_only", "docs_json_missing_file"}
            ],
            "cycle_paths": detect_hard_dependency_cycles(edges),
        },
    }


def metadata_scan(*, active_project: Mapping[str, Any]) -> Dict[str, Any]:
    items = _doc_inventory(active_project)
    seen: Dict[str, List[str]] = {}
    findings: List[Dict[str, Any]] = []
    for item in items:
        md = item["metadata"]
        did = str(md.get("id") or "").strip()
        if not did:
            findings.append({"doc": item["doc_name"], "code": "MISSING_ID", "proof": {"field": "id"}})
        else:
            if not _DOC_ID_PATTERN.fullmatch(did):
                findings.append({"doc": item["doc_name"], "code": "INVALID_ID", "proof": {"field": "id", "value": did, "pattern": _DOC_ID_PATTERN.pattern}})
            seen.setdefault(did, []).append(str(item["path"]))
        if not str(md.get("doc_type") or "").strip():
            findings.append({"doc": item["doc_name"], "code": "MISSING_DOC_TYPE", "proof": {"field": "doc_type"}})
        if not str(md.get("doc_name") or "").strip():
            findings.append({"doc": item["doc_name"], "code": "MISSING_DOC_NAME", "proof": {"field": "doc_name"}})
        if not str(md.get("summary") or "").strip():
            findings.append({"doc": item["doc_name"], "code": "MISSING_SUMMARY", "proof": {"field": "summary"}})
        if not str(md.get("status") or "").strip():
            findings.append({"doc": item["doc_name"], "code": "MISSING_STATUS", "proof": {"field": "status"}})
        if any(k in md for k in ("owner", "author", "agent")):
            value = str(md.get("owner") or md.get("author") or md.get("agent") or "")
            if "agent" in value.lower() and " " not in value:
                findings.append({"doc": item["doc_name"], "code": "OPAQUE_AGENT_ID", "proof": {"field": "owner", "value": value}})

        topology = md.get("topology") if isinstance(md.get("topology"), dict) else {}
        for field, value in topology.items():
            if field in _EDGE_FIELDS and not isinstance(value, list):
                findings.append({"doc": item["doc_name"], "code": "INVALID_EDGE_SHAPE", "proof": {"field": field, "actual": type(value).__name__}})

    for did, paths in seen.items():
        if len(paths) > 1:
            findings.append({"doc": "*", "code": "CONFLICTING_IDS", "proof": {"id": did, "paths": sorted(paths)}})

    return {"ok": True, "action": "metadata_scan", "read_only": True, "findings": findings}


def metadata_repair(*, active_project: Mapping[str, Any], mode: str = "report_only") -> Dict[str, Any]:
    if mode not in _REPAIR_MODES:
        return {"ok": False, "action": "metadata_repair", "error": "invalid repair mode", "rejection_code": "INVALID_REPAIR_MODE", "allowed_modes": sorted(_REPAIR_MODES)}

    items = _doc_inventory(active_project)
    mutations: List[Dict[str, Any]] = []
    plans: List[Dict[str, Any]] = []

    for item in items:
        md = item["metadata"]
        changed = False
        if not str(md.get("id") or "").strip():
            if mode == "repair_safe":
                md["id"] = _stable_doc_id(item["path"])
                changed = True
            else:
                plans.append({"doc": item["doc_name"], "code": "MISSING_ID", "proposal": "generate_stable_id", "requires_review": mode == "repair_assisted"})

        topology = md.get("topology") if isinstance(md.get("topology"), dict) else {}
        for field in _EDGE_FIELDS:
            if field not in topology:
                continue
            if isinstance(topology[field], str) and mode == "repair_safe":
                topology[field] = [topology[field]]
                changed = True
            elif topology[field] is None and mode == "repair_safe":
                topology[field] = []
                changed = True

        if not str(md.get("status") or "").strip():
            if mode == "repair_safe":
                md["status"] = "scaffolded"
                changed = True
            else:
                plans.append({"doc": item["doc_name"], "code": "MISSING_STATUS", "proposal": "set_scaffolded", "requires_review": mode == "repair_assisted"})

        if changed and mode == "repair_safe":
            body = item["path"].read_text(encoding="utf-8")
            parsed = parse_frontmatter(body)
            new_frontmatter_raw, _ = apply_frontmatter_updates(
                parsed.frontmatter_raw if parsed.has_frontmatter else "---\n---\n",
                parsed.frontmatter_data if isinstance(parsed.frontmatter_data, dict) else {},
                md,
            )
            item["path"].write_text(f"{new_frontmatter_raw}{parsed.body}", encoding="utf-8")
            mutations.append({"doc": item["doc_name"], "path": str(item["path"]), "proof": {"mode": mode, "changed": True}})

    return {"ok": True, "action": "metadata_repair", "mode": mode, "writes_performed": mode == "repair_safe", "mutations": mutations, "repair_plan": plans}


def stale_cleanup_scan(*, active_project: Mapping[str, Any]) -> Dict[str, Any]:
    items = _doc_inventory(active_project)
    recommendations: List[Dict[str, Any]] = []
    for item in items:
        text = item["path"].read_text(encoding="utf-8")
        stripped = text.strip()
        if not stripped:
            recommendations.append({"doc": item["doc_name"], "class": "empty", "destructive": True, "rejection_code": "DESTRUCTIVE_CLEANUP_REQUIRES_CONFIRM", "proof": {"bytes": 0}})
            continue
        if len(stripped) < 40:
            recommendations.append({"doc": item["doc_name"], "class": "tiny", "destructive": False, "proof": {"chars": len(stripped)}})
        if "[Agent:" in text and "content_type=log" in text:
            recommendations.append({"doc": item["doc_name"], "class": "sentinel_log_candidate", "destructive": True, "rejection_code": "DESTRUCTIVE_CLEANUP_REQUIRES_CONFIRM", "proof": {"signal": "log_pattern"}})

    return {"ok": True, "action": "stale_cleanup_scan", "read_only": True, "recommendations": recommendations}
