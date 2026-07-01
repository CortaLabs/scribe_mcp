from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping

from scribe_mcp.doc_management.intelligence_workflows import _doc_inventory
from scribe_mcp.doc_management.lifecycle import derive_canonical_doc_type, normalize_canonical_status
from scribe_mcp.doc_management.quality.results import summarize_quality_warnings
from scribe_mcp.doc_management.scaffold_quality import collect_managed_doc_quality_warnings, parse_frontmatter
from scribe_mcp.doc_management.topology import detect_hard_dependency_cycles, normalize_topology_edges

INDEX_DIR = Path('.scribe/indexes')
KNOWLEDGE_EXPORT_DIR = Path('.knowledge/scribe_exports')
LOCAL_ABSOLUTE_PATH_RE = re.compile(r'(?<![\w./-])(?:/(?:home|Users)/[^\s`"\'<>)\]]+|[A-Za-z]:\\[^\s`"\'<>)\]]+)')
RELATIVE_EVIDENCE_ANCHORS = (
    '.scribe/',
    '.knowledge/',
    '.council/',
    'docs/',
    'src/',
    'tests/',
)

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
    'raw_progress_log': 'REJECTED_RAW_PROGRESS_LOG',
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


def _project_slug(active_project: Mapping[str, Any]) -> str:
    raw = str(active_project.get('slug') or active_project.get('name') or 'project').strip().lower()
    slug = re.sub(r'[^a-z0-9._-]+', '-', raw).strip('-._')
    return slug or 'project'


def _section_slug(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug or 'document'


def _body(path: Path) -> str:
    return parse_frontmatter(path.read_text(encoding='utf-8')).body.strip()


def _sanitize_local_absolute_path(match: re.Match[str]) -> str:
    value = match.group(0)
    path_value = value.rstrip('.,;:')
    trailing = value[len(path_value):]
    normalized = path_value.replace('\\', '/')
    for anchor in RELATIVE_EVIDENCE_ANCHORS:
        marker = f'/{anchor}'
        index = normalized.find(marker)
        if index >= 0:
            return f'{normalized[index + 1:]}{trailing}'
    fallback = normalized.rsplit('/', 1)[-1]
    return f'{fallback or "[local path removed]"}{trailing}'


def _sanitize_knowledge_content(content: str) -> str:
    return LOCAL_ABSOLUTE_PATH_RE.sub(_sanitize_local_absolute_path, content)


def _quality_summary(*, path: Path, doc_name: str, project: Mapping[str, Any], metadata: Mapping[str, Any]) -> Dict[str, Any]:
    text = path.read_text(encoding='utf-8')
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name=doc_name,
        path=path,
        project=project,
        metadata=metadata,
    )
    summary = summarize_quality_warnings(warnings)
    if summary['has_blockers']:
        status = 'fail'
    elif summary['total_warnings']:
        status = 'warn'
    else:
        status = 'pass'
    return {
        'quality_status': status,
        'quality_summary': summary,
    }


def _is_curated_rollup(doc_meta: Mapping[str, Any]) -> bool:
    export_meta = doc_meta.get('scribe_export') if isinstance(doc_meta.get('scribe_export'), dict) else {}
    return bool(doc_meta.get('curated_rollup') or export_meta.get('curated_rollup'))


def _is_progress_like(*, doc_name: str, doc_type: str, path: str | None) -> bool:
    name = doc_name.strip().lower()
    rel = str(path or '').strip().lower()
    return (
        doc_type == 'progress_log'
        or name in {'progress_log', 'progress'}
        or name.startswith('progress_')
        or rel.endswith('/progress_log.md')
        or rel.endswith('progress_log.md')
    )


def _heading_title(line: str) -> str | None:
    match = re.match(r'^(#{1,6})\s+(.+?)\s*$', line)
    if not match:
        return None
    return match.group(2).strip().strip('#').strip() or None


def _heading_before_anchor(lines: List[str], anchor_line: int) -> tuple[int, str] | None:
    previous = anchor_line - 1
    while previous >= 0 and not lines[previous].strip():
        previous -= 1
    if previous < 0:
        return None
    title = _heading_title(lines[previous])
    if not title:
        return None
    return previous, title


def _anchored_sections(*, body: str, fallback_title: str) -> List[Dict[str, Any]]:
    lines = body.splitlines()
    anchors: List[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r'^\s*<!--\s*ID:\s*(.+?)\s*-->\s*$', line)
        if match:
            anchor_id = match.group(1).strip()
            if anchor_id:
                anchors.append((index, anchor_id))

    sections: List[Dict[str, Any]] = []
    for section_index, (anchor_line, anchor_id) in enumerate(anchors):
        next_anchor_line = anchors[section_index + 1][0] if section_index + 1 < len(anchors) else len(lines)
        heading_before = _heading_before_anchor(lines, anchor_line)
        next_heading_before = _heading_before_anchor(lines, next_anchor_line) if section_index + 1 < len(anchors) else None
        start_line = heading_before[0] if heading_before else anchor_line + 1
        end_line = next_heading_before[0] if next_heading_before else next_anchor_line
        section_lines = [
            line
            for index, line in enumerate(lines[start_line:end_line], start=start_line)
            if index != anchor_line
        ]
        content = '\n'.join(section_lines).strip()
        if not content:
            continue

        title = heading_before[1] if heading_before else None
        if not title:
            for line in section_lines:
                if not line.strip():
                    continue
                title = _heading_title(line)
                break

        sections.append({
            'section_id': anchor_id,
            'section_title': title or anchor_id or fallback_title,
            'section_index': len(sections),
            'content': content,
        })
    return sections


def _sections(*, path: Path, fallback_title: str) -> List[Dict[str, Any]]:
    body = _body(path)
    anchored = _anchored_sections(body=body, fallback_title=fallback_title)
    if anchored:
        return anchored
    for index, line in enumerate(body.splitlines()):
        title = _heading_title(line)
        if title:
            content = '\n'.join(body.splitlines()[index:]).strip()
            return [{
                'section_id': _section_slug(title),
                'section_title': title,
                'section_index': 0,
                'content': content,
            }]
    return [{
        'section_id': 'document',
        'section_title': fallback_title,
        'section_index': 0,
        'content': body,
    }]


def _knowledge_rows(
    *,
    node: Mapping[str, Any],
    path: Path,
    active_project: Mapping[str, Any],
    project_slug: str,
    quality_status: str,
) -> List[Dict[str, Any]]:
    meta = node['metadata']
    rows: List[Dict[str, Any]] = []
    for section in _sections(path=path, fallback_title=str(meta.get('title') or node['doc_name'])):
        citation_ref = f"{node['path']}#{section['section_id']}"
        rows.append({
            'chunk_id': f"{project_slug}:{node['doc_id']}:{section['section_id']}",
            'content': _sanitize_knowledge_content(section['content']),
            'title': str(meta.get('title') or node['doc_name']),
            'domain': str(meta.get('domain') or node['canonical_doc_type']),
            'confidence': 1.0,
            'project': str(active_project.get('name') or ''),
            'project_slug': project_slug,
            'doc_id': node['doc_id'],
            'doc_name': node['doc_name'],
            'doc_type': node['canonical_doc_type'],
            'source_type': 'scribe',
            'path': node['path'],
            'source_refs': [citation_ref],
            'status': node['status'],
            'lifecycle': node['status'],
            'quality_status': quality_status,
            'section_id': section['section_id'],
            'section_title': section['section_title'],
            'section_index': section['section_index'],
            'citation_ref': citation_ref,
        })
    return rows


def build_export_payload(*, active_project: Mapping[str, Any]) -> Dict[str, Any]:
    root = Path(str(active_project.get('root') or '')).resolve()
    docs_dir = Path(str(active_project.get('docs_dir') or '')).resolve()
    project_slug = _project_slug(active_project)
    knowledge_export_rel = str(KNOWLEDGE_EXPORT_DIR / f'{project_slug}.jsonl')
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
            'metadata': meta,
        })
        edge_map = meta.get('topology') if isinstance(meta.get('topology'), dict) else {}
        edges.extend(normalize_topology_edges(source_doc_id=doc_id, source_doc_path=path, edge_map=edge_map, docs_dir=docs_dir, project_root=root, registered_docs=registered))

    nodes = sorted(nodes, key=lambda n: (n['path'] or '', n['doc_name']))
    edges = sorted(edges, key=lambda e: (str(e.get('source_doc_id') or ''), str(e.get('target_ref') or ''), str(e.get('kind') or '')))

    unresolved_sources = {str(e.get('source_doc_id')) for e in edges if not e.get('target_resolved')}
    manifest_records: List[Dict[str, Any]] = []
    knowledge_rows: List[Dict[str, Any]] = []

    for n in nodes:
        reasons: List[str] = []
        quality = {'quality_status': 'fail', 'quality_summary': {'total_warnings': 0, 'has_blockers': True}}
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
            if not str(n['metadata'].get('quality_status') or '').strip():
                reasons.append(REJECTION_CODES['missing_quality'])
        if not n.get('doc_id') or not n.get('summary') or not n.get('canonical_doc_type'):
            reasons.append(REJECTION_CODES['missing_metadata'])
        if n['doc_id'] in unresolved_sources:
            reasons.append(REJECTION_CODES['dangling_edge'])

        src = registered.get(n['doc_name'])
        if src and src.exists():
            quality = _quality_summary(path=src, doc_name=n['doc_name'], project=active_project, metadata=n['metadata'])
            if quality['quality_status'] == 'fail':
                reasons.append(REJECTION_CODES['quality_fail'])
        else:
            reasons.append(REJECTION_CODES['missing_quality'])

        if _is_progress_like(doc_name=n['doc_name'], doc_type=n['canonical_doc_type'], path=n.get('path')) and not _is_curated_rollup(n['metadata']):
            reasons.append(REJECTION_CODES['raw_progress_log'])

        eligible = len(reasons) == 0
        if eligible and src and src.exists():
            knowledge_rows.extend(
                _knowledge_rows(
                    node=n,
                    path=src,
                    active_project=active_project,
                    project_slug=project_slug,
                    quality_status=quality['quality_status'],
                )
            )

        manifest_records.append({
            'doc_id': n['doc_id'],
            'doc_name': n['doc_name'],
            'path': n['path'],
            'status': n['status'],
            'canonical_doc_type': n['canonical_doc_type'],
            'quality_status': quality['quality_status'],
            'quality_summary': quality['quality_summary'],
            'eligible': eligible,
            'rejection_codes': sorted(set(reasons)),
        })

    manifest_records = sorted(manifest_records, key=lambda r: (r['path'] or '', r['doc_name']))
    knowledge_rows = sorted(knowledge_rows, key=lambda r: (r['path'], r['doc_name'], r['section_index'], r['chunk_id']))
    rejection_summary: Dict[str, int] = {}
    for record in manifest_records:
        for code in record['rejection_codes']:
            rejection_summary[code] = rejection_summary.get(code, 0) + 1

    return {
        'doc_topology': {
            'schema_version': 'v1',
            'nodes': [{k: v for k, v in node.items() if k != 'metadata'} for node in nodes],
            'edges': edges,
        },
        'work_topology': {'schema_version': 'v1', 'cycles': detect_hard_dependency_cycles(edges), 'edge_count': len(edges), 'node_count': len(nodes)},
        'downstream_ingestion_manifest': {
            'schema_version': 'v1',
            'records': manifest_records,
            'eligible_count': sum(1 for r in manifest_records if r['eligible']),
            'knowledge_scribe_export_path': knowledge_export_rel,
            'knowledge_scribe_export_count': len(knowledge_rows),
            'rejection_summary': dict(sorted(rejection_summary.items())),
        },
        'knowledge_scribe_export': knowledge_rows,
    }


def render_stable_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + '\n'


def render_stable_jsonl(rows: List[Dict[str, Any]]) -> str:
    return ''.join(json.dumps(row, sort_keys=True, ensure_ascii=True) + '\n' for row in rows)


def write_export_artifacts(*, active_project: Mapping[str, Any]) -> Dict[str, str]:
    root = Path(str(active_project.get('root') or '')).resolve()
    out_dir = root / INDEX_DIR
    knowledge_out_dir = root / KNOWLEDGE_EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    knowledge_out_dir.mkdir(parents=True, exist_ok=True)
    project_slug = _project_slug(active_project)
    payload = build_export_payload(active_project=active_project)
    mapping = {
        'doc_topology': out_dir / 'doc_topology.json',
        'work_topology': out_dir / 'work_topology.json',
        'downstream_ingestion_manifest': out_dir / 'downstream_ingestion_manifest.json',
        'knowledge_scribe_export': knowledge_out_dir / f'{project_slug}.jsonl',
    }
    for key, path in mapping.items():
        if key == 'knowledge_scribe_export':
            path.write_text(render_stable_jsonl(payload[key]), encoding='utf-8')
        else:
            path.write_text(render_stable_json(payload[key]), encoding='utf-8')
    return {k: str(v) for k, v in mapping.items()}
