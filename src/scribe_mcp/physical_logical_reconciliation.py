"""Read-only physical/logical Scribe reconciliation diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from scribe_mcp.doc_management.utils import discover_scribe_source_documents
from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.tools.project_utils import list_project_configs

CLASSIFICATIONS = ("consistent", "physical_only", "logical_only", "missing_logical_rows")
CORE_PLAN_TYPES = {
    "architecture": "ARCHITECTURE_GUIDE.md",
    "phase_plan": "PHASE_PLAN.md",
    "checklist": "CHECKLIST.md",
}


async def build_physical_logical_reconciliation(
    *,
    repo_root: Path,
    storage_backend: Any,
    project_configs: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compare physical Scribe artifacts with logical storage rows without mutation."""
    root = Path(repo_root).expanduser().resolve()
    backend_name = type(storage_backend).__name__ if storage_backend is not None else None
    projects = await _logical_projects(storage_backend, root)
    projects_by_name = {project.name: project for project in projects}
    physical_configs = dict(project_configs) if project_configs is not None else list_project_configs()
    physical_docs = _physical_core_docs(root)
    physical_progress = _physical_progress_logs(root, physical_configs)
    physical_tool_logs = _physical_tool_logs(root)
    dev_plan_rows = await _logical_dev_plan_rows(storage_backend, projects)
    tool_call_counts = await _logical_tool_call_counts(storage_backend, root)

    project_items = _compare_projects(
        physical_configs=physical_configs,
        logical_projects=projects,
    )
    doc_items = _compare_core_docs(
        physical_docs=physical_docs,
        projects_by_name=projects_by_name,
        dev_plan_rows=dev_plan_rows,
    )
    entry_items = await _compare_progress_logs(
        storage_backend=storage_backend,
        physical_progress=physical_progress,
        projects_by_name=projects_by_name,
    )
    tool_call_items = _compare_tool_logs(
        physical_tool_logs=physical_tool_logs,
        projects_by_name=projects_by_name,
        logical_counts=tool_call_counts,
    )
    items = project_items + doc_items + entry_items + tool_call_items

    return {
        "schema_version": "physical-logical-reconciliation.v1",
        "read_only": True,
        "backend": {
            "name": backend_name,
            "available": storage_backend is not None,
            "fresh_postgres_relevance": _fresh_postgres_relevance(backend_name),
        },
        "repo_root": str(root),
        "summary": _summary(items),
        "items": items,
    }


async def _logical_projects(storage_backend: Any, repo_root: Path) -> List[ProjectRecord]:
    if storage_backend is None:
        return []
    if hasattr(storage_backend, "list_projects_by_repo"):
        try:
            return list(await storage_backend.list_projects_by_repo(str(repo_root)))
        except Exception:
            pass
    if hasattr(storage_backend, "list_projects"):
        try:
            projects = await storage_backend.list_projects()
        except Exception:
            return []
        return [
            project for project in projects
            if str(Path(getattr(project, "repo_root", "") or "").expanduser().resolve()) == str(repo_root)
        ]
    return []


def _physical_core_docs(repo_root: Path) -> Dict[tuple[str, str], Path]:
    docs: Dict[tuple[str, str], Path] = {}
    for document in discover_scribe_source_documents(repo_root, include_case_reports=False):
        if document.source_family != "dev_plan" or document.doc_type not in CORE_PLAN_TYPES:
            continue
        project_name = document.project_slug or document.path.parent.name
        docs[(project_name, document.doc_type)] = document.path
    return docs


def _physical_progress_logs(
    repo_root: Path,
    physical_configs: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Path]:
    logs: Dict[str, Path] = {}
    for name, config in physical_configs.items():
        progress_log = config.get("progress_log")
        if progress_log:
            path = Path(str(progress_log)).expanduser()
            if not path.is_absolute():
                path = repo_root / path
            if path.exists():
                logs[str(config.get("name") or name)] = path.resolve()
    for base in _candidate_dev_plan_roots(repo_root):
        for path in sorted(base.glob("*/PROGRESS_LOG.md")):
            logs.setdefault(path.parent.name, path.resolve())
    return logs


def _physical_tool_logs(repo_root: Path) -> Dict[str, Path]:
    logs: Dict[str, Path] = {}
    for base in _candidate_dev_plan_roots(repo_root):
        for path in sorted(base.glob("*/TOOL_LOG.jsonl")):
            logs[path.parent.name] = path.resolve()
    return logs


def _candidate_dev_plan_roots(repo_root: Path) -> Iterable[Path]:
    for path in (repo_root / ".scribe" / "docs" / "dev_plans", repo_root / "docs" / "dev_plans"):
        if path.exists():
            yield path


async def _logical_dev_plan_rows(
    storage_backend: Any,
    projects: Iterable[ProjectRecord],
) -> Dict[tuple[str, str], Dict[str, Any]]:
    rows_by_key: Dict[tuple[str, str], Dict[str, Any]] = {}
    if storage_backend is None:
        return rows_by_key
    for project in projects:
        rows = await _fetch_rows(
            storage_backend,
            sqlite_sql=(
                "SELECT project_id, project_name, plan_type, file_path "
                "FROM dev_plans WHERE project_id = ?;"
            ),
            postgres_sql=(
                "SELECT project_id, project_name, plan_type, file_path "
                "FROM dev_plans WHERE project_id = $1;"
            ),
            params=(project.id,),
        )
        for row in rows:
            item = dict(row)
            rows_by_key[(str(item.get("project_name") or project.name), str(item.get("plan_type")))] = item
    return rows_by_key


async def _logical_tool_call_counts(storage_backend: Any, repo_root: Path) -> Dict[str, int]:
    rows = await _fetch_rows(
        storage_backend,
        sqlite_sql=(
            "SELECT COALESCE(project_name, '') AS project_name, COUNT(*) AS count "
            "FROM tool_calls WHERE repo_root = ? GROUP BY project_name;"
        ),
        postgres_sql=(
            "SELECT COALESCE(project_name, '') AS project_name, COUNT(*)::int AS count "
            "FROM tool_calls WHERE repo_root = $1 GROUP BY project_name;"
        ),
        params=(str(repo_root),),
    )
    counts: Dict[str, int] = {}
    for row in rows:
        name = str(dict(row).get("project_name") or "")
        if name:
            counts[name] = int(dict(row).get("count") or 0)
    return counts


async def _fetch_rows(
    storage_backend: Any,
    *,
    sqlite_sql: str,
    postgres_sql: str,
    params: tuple[Any, ...],
) -> List[Any]:
    if storage_backend is None:
        return []
    dsn = getattr(storage_backend, "_dsn", None)
    if dsn:
        direct_rows = await _fetch_postgres_rows_direct(
            dsn=str(dsn),
            schema=str(getattr(storage_backend, "_schema_name", "public") or "public"),
            query=postgres_sql,
            params=params,
        )
        if direct_rows is not None:
            return direct_rows
    if hasattr(storage_backend, "_fetch"):
        try:
            return list(await storage_backend._fetch(postgres_sql, *params))
        except Exception:
            return []
    if hasattr(storage_backend, "_fetchall"):
        try:
            return list(await storage_backend._fetchall(sqlite_sql, params))
        except Exception:
            return []
    return []


async def _fetch_postgres_rows_direct(
    *,
    dsn: str,
    schema: str,
    query: str,
    params: tuple[Any, ...],
) -> Optional[List[Dict[str, Any]]]:
    try:
        import asyncpg
    except Exception:
        return None
    qualified_query = _qualify_postgres_query(query, schema=schema)
    try:
        conn = await asyncpg.connect(dsn, timeout=3, command_timeout=3)
    except Exception:
        return None
    try:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(qualified_query, *params)
        return [dict(row) for row in rows]
    except Exception:
        return None
    finally:
        await conn.close()


def _qualify_postgres_query(query: str, *, schema: str) -> str:
    qualified_schema = _quote_identifier(schema)
    replacements = {
        "FROM dev_plans": f"FROM {qualified_schema}.dev_plans",
        "FROM tool_calls": f"FROM {qualified_schema}.tool_calls",
    }
    qualified = query
    for needle, replacement in replacements.items():
        qualified = qualified.replace(needle, replacement)
    return qualified


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _compare_projects(
    *,
    physical_configs: Mapping[str, Mapping[str, Any]],
    logical_projects: Iterable[ProjectRecord],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    logical_by_name = {project.name: project for project in logical_projects}
    physical_names = {str(config.get("name") or name) for name, config in physical_configs.items()}
    for name in sorted(physical_names | set(logical_by_name)):
        physical = name in physical_names
        logical = name in logical_by_name
        items.append(
            {
                "kind": "project_config",
                "project": name,
                "classification": _presence_classification(physical=physical, logical=logical),
                "physical_present": physical,
                "logical_count": 1 if logical else 0,
            }
        )
    return items


def _compare_core_docs(
    *,
    physical_docs: Mapping[tuple[str, str], Path],
    projects_by_name: Mapping[str, ProjectRecord],
    dev_plan_rows: Mapping[tuple[str, str], Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    keys = set(physical_docs) | set(dev_plan_rows)
    items: List[Dict[str, Any]] = []
    for project_name, plan_type in sorted(keys):
        path = physical_docs.get((project_name, plan_type))
        row = dev_plan_rows.get((project_name, plan_type))
        logical = row is not None
        physical = path is not None and path.exists()
        classification = _child_classification(
            project_name=project_name,
            projects_by_name=projects_by_name,
            physical=physical,
            logical=logical,
        )
        items.append(
            {
                "kind": "core_plan_doc",
                "project": project_name,
                "plan_type": plan_type,
                "classification": classification,
                "physical_path": str(path) if path else row.get("file_path") if row else None,
                "physical_present": physical,
                "logical_count": 1 if logical else 0,
            }
        )
    return items


async def _compare_progress_logs(
    *,
    storage_backend: Any,
    physical_progress: Mapping[str, Path],
    projects_by_name: Mapping[str, ProjectRecord],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    project_names = set(physical_progress)
    logical_counts: Dict[str, int] = {}
    for project_name, project in projects_by_name.items():
        if storage_backend is None or not hasattr(storage_backend, "count_entries"):
            continue
        try:
            logical_counts[project_name] = int(await storage_backend.count_entries(project))
        except Exception:
            logical_counts[project_name] = 0
        if logical_counts[project_name] > 0:
            project_names.add(project_name)

    for project_name in sorted(project_names):
        path = physical_progress.get(project_name)
        physical_count = _count_log_lines(path) if path else 0
        project = projects_by_name.get(project_name)
        logical_count = logical_counts.get(project_name, 0)
        classification = _count_classification(
            project_name=project_name,
            projects_by_name=projects_by_name,
            physical_present=path is not None and path.exists(),
            physical_count=physical_count,
            logical_count=logical_count,
        )
        items.append(
            {
                "kind": "progress_log_entries",
                "project": project_name,
                "classification": classification,
                "physical_path": str(path) if path else getattr(project, "progress_log_path", None),
                "physical_count": physical_count,
                "logical_count": logical_count,
            }
        )
    return items


def _compare_tool_logs(
    *,
    physical_tool_logs: Mapping[str, Path],
    projects_by_name: Mapping[str, ProjectRecord],
    logical_counts: Mapping[str, int],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    project_names = set(physical_tool_logs) | set(logical_counts)
    for project_name in sorted(project_names):
        path = physical_tool_logs.get(project_name)
        physical_count = _count_jsonl_lines(path) if path else 0
        logical_count = int(logical_counts.get(project_name, 0))
        classification = _count_classification(
            project_name=project_name,
            projects_by_name=projects_by_name,
            physical_present=path is not None and path.exists(),
            physical_count=physical_count,
            logical_count=logical_count,
        )
        items.append(
            {
                "kind": "tool_calls",
                "project": project_name,
                "classification": classification,
                "physical_path": str(path) if path else None,
                "physical_count": physical_count,
                "logical_count": logical_count,
            }
        )
    return items


def _presence_classification(*, physical: bool, logical: bool) -> str:
    if physical and logical:
        return "consistent"
    if physical:
        return "physical_only"
    return "logical_only"


def _child_classification(
    *,
    project_name: str,
    projects_by_name: Mapping[str, ProjectRecord],
    physical: bool,
    logical: bool,
) -> str:
    if physical and logical:
        return "consistent"
    if physical and project_name in projects_by_name:
        return "missing_logical_rows"
    if physical:
        return "physical_only"
    return "logical_only"


def _count_classification(
    *,
    project_name: str,
    projects_by_name: Mapping[str, ProjectRecord],
    physical_present: bool,
    physical_count: int,
    logical_count: int,
) -> str:
    if physical_present and physical_count == logical_count:
        return "consistent"
    if physical_count > 0 and logical_count > 0:
        if physical_count > logical_count:
            return "missing_logical_rows"
        return "logical_only"
    if physical_present and project_name in projects_by_name:
        return "missing_logical_rows"
    if physical_present:
        return "physical_only"
    return "logical_only"


def _count_log_lines(path: Optional[Path]) -> int:
    if path is None or not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            continue
        count += 1
    return count


def _count_jsonl_lines(path: Optional[Path]) -> int:
    if path is None or not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            continue
        count += 1
    return count


def _summary(items: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    by_classification = {classification: 0 for classification in CLASSIFICATIONS}
    by_kind: Dict[str, Dict[str, int]] = {}
    total = 0
    for item in items:
        total += 1
        classification = str(item.get("classification") or "physical_only")
        by_classification[classification] = by_classification.get(classification, 0) + 1
        kind = str(item.get("kind") or "unknown")
        kind_counts = by_kind.setdefault(kind, {key: 0 for key in CLASSIFICATIONS})
        kind_counts[classification] = kind_counts.get(classification, 0) + 1
    return {
        "total_items": total,
        "by_classification": by_classification,
        "by_kind": by_kind,
    }


def _fresh_postgres_relevance(backend_name: Optional[str]) -> str:
    normalized = str(backend_name or "").lower()
    if "postgres" in normalized:
        return "active_postgres_backend"
    if backend_name:
        return "backend_agnostic_non_postgres_runtime"
    return "no_runtime_backend_available"
