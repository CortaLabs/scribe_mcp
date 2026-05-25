from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from scribe_mcp.doc_management.intelligence_workflows import _doc_inventory
from scribe_mcp.doc_management.lifecycle import derive_canonical_doc_type, normalize_canonical_status
from scribe_mcp.doc_management.scaffold_quality import parse_frontmatter
from scribe_mcp.doc_management.topology import detect_hard_dependency_cycles, normalize_topology_edges

INDEX_DIR = Path('.scribe/indexes')

REJECTION_CODES = {
    'outside_repo': 'REJECTED_OUTSIDE_REPO',
    'unsafe_external_link': 'REJECTED_UNSAFE_EXTERNAL_LINK',
    'archived': 'REJECTED_ARCHIVED',
    'stale': 'REJECTED_STALE',
    'superseded': 'REJECTED_SUPERSEDED',
    'blocked': 'REJECTED_BLOCKED',
    'scaffolded': 'REJECTED_SCAFFOLDED_OR_IN_PROGRESS',
    'quality_fail': 'REJECTED_QUALITY_FAIL',
    'missing_quality': 'REJECTED_MISSING_QUALITY',
    'missing_metadata': 'REJECTED_MISSING_REQUIRED_METADATA',
    'dangling_edge': 'REJECTED_DANGLING_EDGE',
}


def _to_rel(path: Path, root: Path) -> str | None:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return None


def _metadata(path: Path) -> Dict[str, Any]:
    parsed = parse_frontmatter(path.read_text(encoding='utf-8'))
    data = parsed.frontmatter_data if isinstance(parsed.frontmatter_data, dict) else {}
    return dict(data)


def _quality_gate(doc_meta: Dict[str, Any]) -> tuple[bool, str | None]:
    quality = str(doc_meta.get('quality_status') or '').strip().lower()
    if not quality:
        return False, REJECTION_CODES['missing_quality']
    if quality in {'fail', 'blocked'}:
        return False, REJECTION_CODES['quality_fail']
    return True, None


def build_export_payload(*, active_project: Mapping[str, Any]) -> Dict[str, Any]:
    root = Path(str(active_project.get('root') or '')).resolve()
    docs_dir = Path(str(active_project.get('docs_dir') or '')).resolve()
    items = _doc_inventory(active_project)
    registered = {item['doc_name']: item['path'] for item in items}

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for item in items:
        path = item['path']
        rel = _to_rel(path, root)
        meta = _metadata(path)
        canonical_status = normalize_canonical_status(meta.get('status'))
        canonical_type = derive_canonical_doc_type(meta.get('doc_type'), meta.get('intended_doc_type'))
        doc_id = str(meta.get('id') or item['doc_name'])
        nodes.append({
            'doc_name': item['doc_name'],
            'doc_id': doc_id,
            'path': rel,
            'status': canonical_status,
            'canonical_doc_type': canonical_type,
            'summary': str(meta.get('summary') or ''),
            'project': str(active_project.get('name') or ''),
        })
        edge_map = meta.get('topology') if isinstance(meta.get('topology'), dict) else {}
        edges.extend(normalize_topology_edges(source_doc_id=doc_id, source_doc_path=path, edge_map=edge_map, docs_dir=docs_dir, project_root=root, registered_docs=registered))

    nodes = sorted(nodes, key=lambda n: (n['path'] or '', n['doc_name']))
    edges = sorted(edges, key=lambda e: (str(e.get('source_doc_id') or ''), str(e.get('target_ref') or ''), str(e.get('kind') or '')))

    unresolved_sources = {str(e.get('source_doc_id')) for e in edges if not e.get('target_resolved')}
    manifest_records: List[Dict[str, Any]] = []

    for n in nodes:
        reasons: List[str] = []
        if not n.get('path'):
            reasons.append(REJECTION_CODES['outside_repo'])
        if n['status'] == 'archived':
            reasons.append(REJECTION_CODES['archived'])
        if n['status'] == 'stale':
            reasons.append(REJECTION_CODES['stale'])
        if n['status'] == 'superseded':
            reasons.append(REJECTION_CODES['superseded'])
        if n['status'] == 'blocked':
            reasons.append(REJECTION_CODES['blocked'])
        if n['status'] in {'scaffolded', 'in_progress'}:
            reasons.append(REJECTION_CODES['scaffolded'])
        if not n.get('doc_id') or not n.get('summary') or not n.get('canonical_doc_type'):
            reasons.append(REJECTION_CODES['missing_metadata'])
        if n['doc_id'] in unresolved_sources:
            reasons.append(REJECTION_CODES['dangling_edge'])

        src = registered.get(n['doc_name'])
        if src and src.exists():
            qok, qreason = _quality_gate(_metadata(src))
            if not qok and qreason:
                reasons.append(qreason)

        manifest_records.append({
            'doc_id': n['doc_id'],
            'doc_name': n['doc_name'],
            'path': n['path'],
            'status': n['status'],
            'canonical_doc_type': n['canonical_doc_type'],
            'eligible': len(reasons) == 0,
            'rejection_codes': sorted(set(reasons)),
        })

    manifest_records = sorted(manifest_records, key=lambda r: (r['path'] or '', r['doc_name']))
    rejection_summary: Dict[str, int] = {}
    for record in manifest_records:
        for code in record['rejection_codes']:
            rejection_summary[code] = rejection_summary.get(code, 0) + 1

    return {
        'doc_topology': {'schema_version': 'v1', 'nodes': nodes, 'edges': edges},
        'work_topology': {'schema_version': 'v1', 'cycles': detect_hard_dependency_cycles(edges), 'edge_count': len(edges), 'node_count': len(nodes)},
        'downstream_ingestion_manifest': {
            'schema_version': 'v1',
            'records': manifest_records,
            'eligible_count': sum(1 for r in manifest_records if r['eligible']),
            'rejection_summary': dict(sorted(rejection_summary.items())),
        },
    }


def render_stable_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + '\n'


def write_export_artifacts(*, active_project: Mapping[str, Any]) -> Dict[str, str]:
    root = Path(str(active_project.get('root') or '')).resolve()
    out_dir = root / INDEX_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_export_payload(active_project=active_project)
    mapping = {
        'doc_topology': out_dir / 'doc_topology.json',
        'work_topology': out_dir / 'work_topology.json',
        'downstream_ingestion_manifest': out_dir / 'downstream_ingestion_manifest.json',
    }
    for key, path in mapping.items():
        path.write_text(render_stable_json(payload[key]), encoding='utf-8')
    return {k: str(v) for k, v in mapping.items()}
