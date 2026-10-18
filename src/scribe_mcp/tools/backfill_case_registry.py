"""Dry-run planner for backfilling governed case reports into the registry."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Mapping, Optional

try:
    from scribe_mcp import server as server_module
    from scribe_mcp.server import app
except Exception:
    server_module = SimpleNamespace(storage_backend=None, get_execution_context=lambda: None)

    class _AppStub:
        def tool(self, _func=None, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

    app = _AppStub()

from scribe_mcp.doc_management import utils as doc_utils
from scribe_mcp.storage.models import compute_project_key, compute_repo_id, normalize_repo_root
from scribe_mcp.tool_contracts import read_only_local_tool


def _normalize_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _coerce_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 500
    return max(1, min(parsed, 5000))


def _context_mode_repo_project() -> tuple[str, Optional[str], Optional[str]]:
    if not hasattr(server_module, "get_execution_context"):
        return "unknown", None, None
    try:
        context = server_module.get_execution_context()
    except Exception:
        return "unknown", None, None
    if context is None:
        return "unknown", None, None

    mode = str(getattr(context, "mode", "") or "unknown")
    resolved_scope = getattr(context, "resolved_scope", None)
    repo_root = getattr(resolved_scope, "repo_root", None)
    project_name = getattr(resolved_scope, "project_name", None)
    return mode, _resolve_repo_root(repo_root), _normalize_str(project_name)


def _resolve_repo_root(value: object) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(Path(value).expanduser().resolve())
    except Exception:
        return value.strip()


def _empty_report(
    *,
    dry_run: bool,
    skipped: list[dict[str, object]] | None = None,
    warnings: list[str] | None = None,
    operator_review_required: bool = False,
) -> Dict[str, Any]:
    return {
        "ok": not operator_review_required,
        "dry_run": dry_run,
        "would_upsert": 0,
        "would_update_aliases": 0,
        "collisions": [],
        "operator_review_required": operator_review_required,
        "skipped": skipped or [],
        "records": [],
        "warnings": warnings or [],
        "next_step": (
            "Review skipped items and rerun backfill_case_registry in dry-run mode."
            if operator_review_required
            else "No backfill records were planned."
        ),
    }


def _project_docs(project_record: object | None) -> dict[str, str]:
    raw_docs = getattr(project_record, "docs_json", None)
    if not isinstance(raw_docs, str) or not raw_docs.strip():
        return {}
    try:
        parsed = json.loads(raw_docs)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    docs: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str):
            docs[key] = value
    return docs


def _existing_scope_key(record: object) -> tuple[str, str]:
    project_key = str(getattr(record, "project_key", "") or "")
    if not project_key:
        project_key = compute_project_key(
            repo_root=str(getattr(record, "repo_root", "") or ""),
            project_name=str(getattr(record, "project_name", "") or ""),
        )
    return project_key, str(getattr(record, "case_id", "") or "")


def _planned_scope_key(kwargs: Mapping[str, object]) -> tuple[str, str]:
    project_key = compute_project_key(
        repo_root=str(kwargs["repo_root"]),
        project_name=str(kwargs["project_name"]),
    )
    return project_key, str(kwargs["case_id"])


def _is_terminal_status(value: object) -> bool:
    return doc_utils.case_status_closes(doc_utils.normalize_case_status(value))


def _alias_tokens(metadata: object) -> set[str]:
    if not isinstance(metadata, Mapping):
        return set()
    binding = metadata.get("doc_binding")
    if not isinstance(binding, Mapping):
        return set()
    aliases = binding.get("aliases")
    if not isinstance(aliases, list):
        return set()
    tokens: set[str] = set()
    for alias in aliases:
        if isinstance(alias, Mapping) and alias.get("alias") is not None:
            tokens.add(str(alias["alias"]))
    return tokens


def _merge_doc_binding_aliases(
    current: dict[str, object] | None,
    candidate: object,
) -> tuple[dict[str, object] | None, bool]:
    if not isinstance(candidate, Mapping):
        return current, False
    candidate_binding = candidate.get("doc_binding")
    if not isinstance(candidate_binding, Mapping):
        return current, False
    if current is None:
        return dict(candidate), False
    current_binding = current.get("doc_binding")
    if not isinstance(current_binding, Mapping):
        merged = dict(current)
        merged["doc_binding"] = dict(candidate_binding)
        return merged, True

    merged = dict(current)
    merged_binding = dict(current_binding)
    aliases = list(merged_binding.get("aliases") or [])
    before = {str(item.get("alias")) for item in aliases if isinstance(item, Mapping) and item.get("alias") is not None}
    for alias in candidate_binding.get("aliases") or []:
        if not isinstance(alias, Mapping) or alias.get("alias") is None:
            continue
        alias_name = str(alias["alias"])
        if alias_name in before:
            continue
        aliases.append(dict(alias))
        before.add(alias_name)
    merged_binding["aliases"] = aliases
    merged["doc_binding"] = merged_binding
    return merged, _alias_tokens(current) != _alias_tokens(merged)


def _record_summary(kwargs: Mapping[str, object], *, action: str, alias_update: bool) -> dict[str, object]:
    metadata = kwargs.get("metadata")
    aliases = sorted(_alias_tokens(metadata))
    repo_root = str(kwargs["repo_root"])
    project_name = str(kwargs["project_name"])
    return {
        "action": action,
        "case_id": str(kwargs["case_id"]),
        "case_type": str(kwargs["case_type"]),
        "project_name": project_name,
        "project_key": compute_project_key(repo_root=repo_root, project_name=project_name),
        "repo_root": normalize_repo_root(repo_root),
        "repo_id": compute_repo_id(repo_root),
        "doc_type": str(kwargs["doc_type"]),
        "doc_name": str(kwargs["doc_name"]),
        "doc_path": str(kwargs["doc_path"]),
        "status": kwargs.get("status"),
        "severity": kwargs.get("severity"),
        "alias_update": alias_update,
        "aliases": aliases,
    }


def _conflicts(existing: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    return (
        str(existing.get("doc_path") or "") != str(candidate.get("doc_path") or "")
        or str(existing.get("case_type") or "") != str(candidate.get("case_type") or "")
    )


async def _fetch_project(backend: object, project_name: Optional[str]) -> object | None:
    if not project_name or not hasattr(backend, "fetch_project"):
        return None
    return await backend.fetch_project(project_name)


async def _query_existing_records(
    backend: object,
    *,
    repo_root: str,
    project_name: Optional[str],
    limit: int,
) -> list[object]:
    if not hasattr(backend, "query_case_registry_records"):
        return []
    return await backend.query_case_registry_records(
        repo_root=repo_root,
        project_name=project_name,
        limit=max(limit, 500),
        offset=0,
    )


@app.tool(
    **read_only_local_tool(
        title="Backfill Case Registry",
        tags=("cases", "bugs", "security", "backfill", "read-only"),
    )
)
async def backfill_case_registry(
    project: Optional[str] = None,
    repo_root: Optional[str] = None,
    dry_run: bool = True,
    apply: bool = False,
    limit: int = 500,
) -> Dict[str, Any]:
    """Plan a governed report backfill into the shared case registry."""
    normalized_project = _normalize_str(project)
    mode, active_repo_root, default_project = _context_mode_repo_project()
    query_repo_root = _resolve_repo_root(repo_root) or active_repo_root
    query_project = normalized_project or default_project
    normalized_limit = _coerce_limit(limit)
    effective_dry_run = True

    if apply:
        return _empty_report(
            dry_run=False,
            operator_review_required=True,
            skipped=[
                {
                    "reason": "apply_not_implemented",
                    "detail": "SBH-05 exposes dry-run/operator-review only; no registry writes were attempted.",
                }
            ],
            warnings=["apply=True is refused by the first-wave dry-run backfill contract."],
        )

    if not dry_run:
        return _empty_report(
            dry_run=True,
            operator_review_required=True,
            skipped=[
                {
                    "reason": "apply_required_for_write",
                    "detail": "dry_run=False without apply=True is refused; no registry writes were attempted.",
                }
            ],
            warnings=["backfill_case_registry defaults to dry-run and refuses implicit writes."],
        )

    if not query_repo_root:
        return _empty_report(
            dry_run=effective_dry_run,
            operator_review_required=True,
            skipped=[
                {
                    "reason": "missing_repo_root",
                    "detail": "Provide repo_root or bind Scribe to an active repo scope.",
                }
            ],
        )

    backend = getattr(server_module, "storage_backend", None)
    project_record = await _fetch_project(backend, query_project) if backend is not None else None
    docs_mapping = _project_docs(project_record)
    project_payload: dict[str, object] = {"root": query_repo_root, "docs": docs_mapping}
    if query_project:
        project_payload["name"] = query_project

    extracted_records = doc_utils.build_case_registry_backfill_records(
        Path(query_repo_root),
        project=project_payload,
    )[:normalized_limit]
    existing_records = (
        await _query_existing_records(
            backend,
            repo_root=query_repo_root,
            project_name=query_project,
            limit=normalized_limit,
        )
        if backend is not None
        else []
    )
    existing_by_scope = {_existing_scope_key(record): record for record in existing_records}

    planned: dict[tuple[str, str], dict[str, object]] = {}
    planned_alias_updates: dict[tuple[str, str], bool] = {}
    collisions: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for extracted in extracted_records:
        base_kwargs = doc_utils.build_case_registry_upsert_kwargs(extracted=extracted)
        if base_kwargs is None:
            skipped.append({"reason": "incomplete_extracted_record", "record": extracted})
            continue
        scope_key = _planned_scope_key(base_kwargs)
        existing = existing_by_scope.get(scope_key)
        overrides: dict[str, object] = {}
        if existing is not None and _is_terminal_status(getattr(existing, "status", None)):
            overrides["status"] = getattr(existing, "status", None)
        kwargs = doc_utils.build_case_registry_upsert_kwargs(
            extracted=extracted,
            existing_record=existing,
            overrides=overrides,
        )
        if kwargs is None:
            skipped.append({"reason": "incomplete_upsert_kwargs", "record": extracted})
            continue

        if scope_key in planned:
            current = planned[scope_key]
            if _conflicts(current, kwargs):
                collisions.append(
                    {
                        "project_key": scope_key[0],
                        "case_id": scope_key[1],
                        "existing": {
                            "case_type": current.get("case_type"),
                            "doc_path": current.get("doc_path"),
                        },
                        "candidate": {
                            "case_type": kwargs.get("case_type"),
                            "doc_path": kwargs.get("doc_path"),
                        },
                        "reason": "same-scope case_id collision with conflicting path or type",
                    }
                )
                continue
            merged_metadata, alias_changed = _merge_doc_binding_aliases(
                current.get("metadata") if isinstance(current.get("metadata"), dict) else None,
                kwargs.get("metadata"),
            )
            current["metadata"] = merged_metadata
            planned_alias_updates[scope_key] = planned_alias_updates.get(scope_key, False) or alias_changed
            continue

        existing_aliases = _alias_tokens(getattr(existing, "metadata", None))
        planned_aliases = _alias_tokens(kwargs.get("metadata"))
        planned[scope_key] = dict(kwargs)
        planned_alias_updates[scope_key] = existing is not None and planned_aliases != existing_aliases

    records: list[dict[str, object]] = []
    would_upsert = 0
    would_update_aliases = 0
    for scope_key, kwargs in sorted(planned.items(), key=lambda item: (item[0][0], item[0][1])):
        existing = existing_by_scope.get(scope_key)
        alias_update = planned_alias_updates.get(scope_key, False)
        if existing is None:
            would_upsert += 1
            action = "insert"
        else:
            action = "update_aliases" if alias_update else "no_change"
        if alias_update:
            would_update_aliases += 1
        records.append(_record_summary(kwargs, action=action, alias_update=alias_update))

    operator_review_required = bool(collisions)
    return {
        "ok": not operator_review_required,
        "dry_run": effective_dry_run,
        "would_upsert": would_upsert,
        "would_update_aliases": would_update_aliases,
        "collisions": collisions,
        "operator_review_required": operator_review_required,
        "skipped": skipped,
        "records": records,
        "warnings": ["collisions require operator review before apply"] if collisions else [],
        "filters": {
            "project": query_project,
            "repo_root": query_repo_root,
            "limit": normalized_limit,
            "mode": mode,
        },
        "next_step": (
            "Resolve same-scope collisions before any registry backfill apply."
            if operator_review_required
            else "Review dry-run records; SBH-05 does not perform writes."
        ),
    }
