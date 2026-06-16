from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence

from scribe_mcp.doc_management.scaffold_quality import (
    collect_managed_doc_quality_warnings,
    configured_log_quality_exclusion_paths,
    is_managed_doc_quality_target,
)

FUTURE_PHASE_PREFIXES = ("phase 2", "phase 3", "phase 4", "phase 5", "phase 6", "phase 7", "phase 8", "phase 9")

ReadinessRoundtripPayload = dict[str, str | bool]
_FileSignature = tuple[str, int | None, int | None]
_QualityCacheKey = tuple[
    str,
    str | None,
    tuple[tuple[str, str, int | None, int | None], ...],
    tuple[str, ...],
    tuple[_FileSignature, ...],
]
_MANAGED_DOC_QUALITY_STATE_CACHE: dict[_QualityCacheKey, Dict[str, Any]] = {}
_MANAGED_DOC_QUALITY_STATE_CACHE_MAX_SIZE = 32

COMMAND_CLASS_LABEL = "scribe_owned_local_postgres_readiness_roundtrip_preflight"
ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL = "approved_local_non_active_scribe_postgres_disposable_or_test_target"
ACCEPTED_SELECTOR_READBACK_STATUS_LABEL = "scribe_owned_public_safe_readback_emitted_required_selector_status_labels"
PASSED_CONNECTIVITY_LABEL = "passed_public_connectivity_label"
STORAGE_SETUP_NOT_RUN_LABEL = "not_run_storage_setup_not_required"
PASSED_ROUNDTRIP_LABEL = "passed_scribe_roundtrip_public_label"
PASSED_IDEMPOTENCY_LABEL = "passed_scribe_idempotency_public_label"
PASSED_CLEANUP_LABEL = "passed_cleanup_public_label"
PUBLIC_REDACTION_POLICY_LABEL = "public_labels_references_statuses_only_no_raw_values"

BLOCKED_PRIVATE_INPUT_UNSAFE = "blocked_private_input_unsafe"
BLOCKED_TARGET_CLASS_UNSAFE = "blocked_target_class_unsafe"
BLOCKED_SELECTOR_READBACK_UNSAFE = "blocked_selector_readback_unsafe"
BLOCKED_STORAGE_SETUP_REQUIRED = "blocked_storage_setup_required"
BLOCKED_CONNECTIVITY_FAILED_REDACTED = "blocked_connectivity_failed_redacted"
BLOCKED_ROUNDTRIP_FAILED_REDACTED = "blocked_roundtrip_failed_redacted"
BLOCKED_CLEANUP_FAILED_REDACTED = "blocked_cleanup_failed_redacted"

_BLOCKED_STATUS_LABELS = {
    BLOCKED_PRIVATE_INPUT_UNSAFE,
    BLOCKED_TARGET_CLASS_UNSAFE,
    BLOCKED_SELECTOR_READBACK_UNSAFE,
    BLOCKED_STORAGE_SETUP_REQUIRED,
    BLOCKED_CONNECTIVITY_FAILED_REDACTED,
    BLOCKED_ROUNDTRIP_FAILED_REDACTED,
    BLOCKED_CLEANUP_FAILED_REDACTED,
}


class LocalPostgresRoundtripRunner(Protocol):
    async def connect(self, private_target_handle_id: str) -> str: ...

    async def roundtrip(self, proof_namespace_label: str) -> str: ...

    async def cleanup(self, proof_namespace_label: str) -> str: ...


@dataclass(frozen=True)
class ReadinessSummary:
    current_phase: Optional[str]
    managed_doc_quality: Dict[str, Any]
    log_friction: Dict[str, Any]
    warning_count: int
    blocker_count: int
    next_actions: list[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_phase": self.current_phase,
            "managed_doc_quality": self.managed_doc_quality,
            "log_friction": self.log_friction,
            "warning_count": self.warning_count,
            "blocker_count": self.blocker_count,
            "next_actions": self.next_actions,
        }


def _is_public_safe_identifier(value: str) -> bool:
    if not value:
        return False
    if not (8 <= len(value) <= 128):
        return False
    return all(character.isalnum() or character in {"_", "-"} for character in value)


def _blocked_roundtrip_payload(status_label: str) -> ReadinessRoundtripPayload:
    return build_local_postgres_readiness_roundtrip_labels(
        target_class_label=BLOCKED_TARGET_CLASS_UNSAFE,
        selected_context_readback_status_label=(
            BLOCKED_SELECTOR_READBACK_UNSAFE if status_label == BLOCKED_SELECTOR_READBACK_UNSAFE else ACCEPTED_SELECTOR_READBACK_STATUS_LABEL
        ),
        connectivity_status_label=status_label,
        storage_setup_status_label=status_label,
        scribe_roundtrip_label=status_label,
        scribe_idempotency_label=status_label,
        cleanup_status_label=status_label,
    )


def build_local_postgres_readiness_roundtrip_labels(
    *,
    target_class_label: str,
    selected_context_readback_status_label: str,
    connectivity_status_label: str,
    storage_setup_status_label: str,
    scribe_roundtrip_label: str,
    scribe_idempotency_label: str,
    cleanup_status_label: str,
) -> ReadinessRoundtripPayload:
    return {
        "command_class_label": COMMAND_CLASS_LABEL,
        "target_class_label": target_class_label,
        "selected_context_readback_status_label": selected_context_readback_status_label,
        "connectivity_status_label": connectivity_status_label,
        "storage_setup_status_label": storage_setup_status_label,
        "scribe_roundtrip_label": scribe_roundtrip_label,
        "scribe_idempotency_label": scribe_idempotency_label,
        "cleanup_status_label": cleanup_status_label,
        "public_redaction_policy_label": PUBLIC_REDACTION_POLICY_LABEL,
        "private_values_recorded": False,
        "train_local_db_g_technical_pass_candidate_label": False,
        "train_local_db_g_technical_pass_earned": False,
        "train_02g2_b_routing_authorized": False,
    }


async def scribe_local_postgres_readiness_roundtrip_preflight(
    *,
    private_target_handle_id: str,
    target_class_label: str,
    selected_context_readback_status_label: str,
    proof_namespace_label: str,
    runner: LocalPostgresRoundtripRunner,
    **alternate_private_target_fields: object,
) -> ReadinessRoundtripPayload:
    if alternate_private_target_fields:
        return _blocked_roundtrip_payload(BLOCKED_PRIVATE_INPUT_UNSAFE)
    if not _is_public_safe_identifier(private_target_handle_id):
        return _blocked_roundtrip_payload(BLOCKED_PRIVATE_INPUT_UNSAFE)
    if not _is_public_safe_identifier(proof_namespace_label):
        return _blocked_roundtrip_payload(BLOCKED_PRIVATE_INPUT_UNSAFE)
    if target_class_label != ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL:
        return _blocked_roundtrip_payload(BLOCKED_TARGET_CLASS_UNSAFE)
    if selected_context_readback_status_label != ACCEPTED_SELECTOR_READBACK_STATUS_LABEL:
        return _blocked_roundtrip_payload(BLOCKED_SELECTOR_READBACK_UNSAFE)

    try:
        connectivity_status_label = await runner.connect(private_target_handle_id)
    except Exception:
        return build_local_postgres_readiness_roundtrip_labels(
            target_class_label=target_class_label,
            selected_context_readback_status_label=selected_context_readback_status_label,
            connectivity_status_label=BLOCKED_CONNECTIVITY_FAILED_REDACTED,
            storage_setup_status_label=STORAGE_SETUP_NOT_RUN_LABEL,
            scribe_roundtrip_label=BLOCKED_CONNECTIVITY_FAILED_REDACTED,
            scribe_idempotency_label=BLOCKED_CONNECTIVITY_FAILED_REDACTED,
            cleanup_status_label=BLOCKED_CONNECTIVITY_FAILED_REDACTED,
        )
    if connectivity_status_label == BLOCKED_STORAGE_SETUP_REQUIRED:
        return build_local_postgres_readiness_roundtrip_labels(
            target_class_label=target_class_label,
            selected_context_readback_status_label=selected_context_readback_status_label,
            connectivity_status_label=BLOCKED_STORAGE_SETUP_REQUIRED,
            storage_setup_status_label=BLOCKED_STORAGE_SETUP_REQUIRED,
            scribe_roundtrip_label=BLOCKED_STORAGE_SETUP_REQUIRED,
            scribe_idempotency_label=BLOCKED_STORAGE_SETUP_REQUIRED,
            cleanup_status_label=BLOCKED_STORAGE_SETUP_REQUIRED,
        )
    if connectivity_status_label != PASSED_CONNECTIVITY_LABEL:
        return build_local_postgres_readiness_roundtrip_labels(
            target_class_label=target_class_label,
            selected_context_readback_status_label=selected_context_readback_status_label,
            connectivity_status_label=BLOCKED_CONNECTIVITY_FAILED_REDACTED,
            storage_setup_status_label=STORAGE_SETUP_NOT_RUN_LABEL,
            scribe_roundtrip_label=BLOCKED_CONNECTIVITY_FAILED_REDACTED,
            scribe_idempotency_label=BLOCKED_CONNECTIVITY_FAILED_REDACTED,
            cleanup_status_label=BLOCKED_CONNECTIVITY_FAILED_REDACTED,
        )

    scribe_roundtrip_label = BLOCKED_ROUNDTRIP_FAILED_REDACTED
    scribe_idempotency_label = BLOCKED_ROUNDTRIP_FAILED_REDACTED
    cleanup_status_label = BLOCKED_CLEANUP_FAILED_REDACTED
    proof_touched = False
    try:
        proof_touched = True
        first_roundtrip_label = await runner.roundtrip(proof_namespace_label)
        if first_roundtrip_label != PASSED_ROUNDTRIP_LABEL:
            scribe_roundtrip_label = (
                first_roundtrip_label if first_roundtrip_label in _BLOCKED_STATUS_LABELS else BLOCKED_ROUNDTRIP_FAILED_REDACTED
            )
            return build_local_postgres_readiness_roundtrip_labels(
                target_class_label=target_class_label,
                selected_context_readback_status_label=selected_context_readback_status_label,
                connectivity_status_label=PASSED_CONNECTIVITY_LABEL,
                storage_setup_status_label=STORAGE_SETUP_NOT_RUN_LABEL,
                scribe_roundtrip_label=scribe_roundtrip_label,
                scribe_idempotency_label=BLOCKED_ROUNDTRIP_FAILED_REDACTED,
                cleanup_status_label=cleanup_status_label,
            )
        scribe_roundtrip_label = PASSED_ROUNDTRIP_LABEL

        second_roundtrip_label = await runner.roundtrip(proof_namespace_label)
        if second_roundtrip_label != PASSED_ROUNDTRIP_LABEL:
            scribe_idempotency_label = (
                second_roundtrip_label
                if second_roundtrip_label in _BLOCKED_STATUS_LABELS
                else BLOCKED_ROUNDTRIP_FAILED_REDACTED
            )
        else:
            scribe_idempotency_label = PASSED_IDEMPOTENCY_LABEL
    except Exception:
        if scribe_roundtrip_label == PASSED_ROUNDTRIP_LABEL:
            scribe_idempotency_label = BLOCKED_ROUNDTRIP_FAILED_REDACTED
        else:
            scribe_roundtrip_label = BLOCKED_ROUNDTRIP_FAILED_REDACTED
            scribe_idempotency_label = BLOCKED_ROUNDTRIP_FAILED_REDACTED
    finally:
        if proof_touched:
            try:
                cleanup_result = await runner.cleanup(proof_namespace_label)
                cleanup_status_label = (
                    PASSED_CLEANUP_LABEL if cleanup_result == PASSED_CLEANUP_LABEL else BLOCKED_CLEANUP_FAILED_REDACTED
                )
            except Exception:
                cleanup_status_label = BLOCKED_CLEANUP_FAILED_REDACTED

    return build_local_postgres_readiness_roundtrip_labels(
        target_class_label=target_class_label,
        selected_context_readback_status_label=selected_context_readback_status_label,
        connectivity_status_label=PASSED_CONNECTIVITY_LABEL,
        storage_setup_status_label=STORAGE_SETUP_NOT_RUN_LABEL,
        scribe_roundtrip_label=scribe_roundtrip_label,
        scribe_idempotency_label=scribe_idempotency_label,
        cleanup_status_label=cleanup_status_label,
    )


def _is_future_phase_warning(current_phase: Optional[str], warning: Mapping[str, Any]) -> bool:
    if not current_phase:
        return False
    excerpt = str(warning.get("excerpt") or "").lower()
    code = str(warning.get("code") or "")
    if code not in {"SCF_INDEX_STALE", "SCF_INDEX_MISSING", "SCF_DOC_UNINDEXED"}:
        return False
    if "phase" not in excerpt:
        return False
    return any(prefix in excerpt and prefix not in current_phase.lower() for prefix in FUTURE_PHASE_PREFIXES)


def clear_managed_doc_quality_state_cache() -> None:
    """Clear cached managed-doc quality state for tests and long-lived runtime resets."""
    _MANAGED_DOC_QUALITY_STATE_CACHE.clear()


def _path_signature(path: Path) -> _FileSignature:
    try:
        stat = path.stat()
    except OSError:
        return str(path), None, None
    return str(path), int(stat.st_mtime_ns), int(stat.st_size)


def _research_dir_signatures(docs_dir: object, doc_paths: Sequence[Path]) -> tuple[_FileSignature, ...]:
    research_dirs: set[Path] = set()
    if isinstance(docs_dir, str) and docs_dir.strip():
        research_dirs.add((Path(docs_dir) / "research").expanduser().resolve())
    for path in doc_paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path
        if "research" in {part.lower() for part in resolved.parts}:
            research_dirs.add(resolved.parent)

    signatures: list[_FileSignature] = []
    for directory in sorted(research_dirs, key=str):
        if not directory.exists():
            signatures.append((str(directory), None, None))
            continue
        try:
            markdown_files = sorted(directory.glob("*.md"), key=str)
        except OSError:
            signatures.append((str(directory), None, None))
            continue
        signatures.extend(_path_signature(path) for path in markdown_files)
    return tuple(signatures)


def _managed_doc_quality_cache_key(project: Mapping[str, Any]) -> _QualityCacheKey:
    docs = project.get("docs", {}) if isinstance(project.get("docs"), dict) else {}
    configured_log_paths = configured_log_quality_exclusion_paths(project)
    current_phase = str(project.get("current_phase") or "").strip() or None
    targets: list[tuple[str, str, int | None, int | None]] = []
    doc_paths: list[Path] = []

    for key, doc_path in docs.items():
        if not isinstance(doc_path, str) or not doc_path.endswith(".md"):
            continue
        if not is_managed_doc_quality_target(str(key), doc_path, configured_log_paths=configured_log_paths):
            continue
        path = Path(doc_path)
        signature = _path_signature(path)
        targets.append((str(key), signature[0], signature[1], signature[2]))
        doc_paths.append(path)

    repo_root = Path(str(project.get("root") or ".")).expanduser().resolve()
    pyproject_signature = _path_signature(repo_root / "pyproject.toml")
    return (
        str(repo_root),
        current_phase,
        tuple(sorted(targets)),
        tuple(sorted(str(path) for path in configured_log_paths)),
        (pyproject_signature, *_research_dir_signatures(project.get("docs_dir"), doc_paths)),
    )


def _collect_managed_doc_quality_state_uncached(project: Mapping[str, Any]) -> Dict[str, Any]:
    docs = project.get("docs", {}) if isinstance(project.get("docs"), dict) else {}
    configured_log_paths = configured_log_quality_exclusion_paths(project)
    current_phase = str(project.get("current_phase") or "").strip() or None

    documents: list[dict[str, Any]] = []
    blocker_count = 0
    frontmatter_mismatch_count = 0
    stale_research_index_count = 0
    total_warnings = 0
    warning_counts_by_code: dict[str, int] = {}
    readiness_blocker_counts_by_code: dict[str, int] = {}
    normalized_warnings: list[dict[str, Any]] = []

    for key, doc_path in docs.items():
        if not isinstance(doc_path, str) or not doc_path.endswith(".md"):
            continue
        if not is_managed_doc_quality_target(str(key), doc_path, configured_log_paths=configured_log_paths):
            continue
        path = Path(doc_path)
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        warnings = collect_managed_doc_quality_warnings(text=text, doc_name=str(key), path=path, project=project)
        total_warnings += len(warnings)
        blockers = []
        for warning in warnings:
            code = str(warning.get("code") or "")
            if code:
                warning_counts_by_code[code] = warning_counts_by_code.get(code, 0) + 1
            if code == "SCF_FRONTMATTER_MISMATCH":
                frontmatter_mismatch_count += 1
            if code in {"SCF_INDEX_STALE", "SCF_INDEX_MISSING", "SCF_DOC_UNINDEXED"}:
                stale_research_index_count += 1
            if bool(warning.get("blocking")) and not _is_future_phase_warning(current_phase, warning):
                blockers.append(warning)
                if code:
                    readiness_blocker_counts_by_code[code] = readiness_blocker_counts_by_code.get(code, 0) + 1
            normalized_warnings.append(
                {
                    "code": code,
                    "severity": warning.get("severity"),
                    "blocking": bool(warning.get("blocking")),
                    "doc_name": str(key),
                    "path": str(path),
                    "suggested_repair": warning.get("suggested_repair"),
                }
            )

        blocker_count += len(blockers)
        documents.append(
            {
                "doc_name": str(key),
                "path": str(path),
                "warning_codes": [w.get("code") for w in warnings],
                "readiness_blocker_codes": [w.get("code") for w in blockers],
                "blocking_warning_codes": [w.get("code") for w in blockers],
            }
        )

    return {
        "status": "blocked" if blocker_count else "pass",
        "readiness_blocker_count": blocker_count,
        "frontmatter_mismatch_count": frontmatter_mismatch_count,
        "stale_research_index_count": stale_research_index_count,
        "total_warning_count": total_warnings,
        "warnings": normalized_warnings,
        "warning_counts_by_code": warning_counts_by_code,
        "readiness_blocker_counts_by_code": readiness_blocker_counts_by_code,
        "documents": documents,
    }


def collect_managed_doc_quality_state(project: Mapping[str, Any]) -> Dict[str, Any]:
    cache_key = _managed_doc_quality_cache_key(project)
    cached = _MANAGED_DOC_QUALITY_STATE_CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    quality_state = _collect_managed_doc_quality_state_uncached(project)
    if len(_MANAGED_DOC_QUALITY_STATE_CACHE) >= _MANAGED_DOC_QUALITY_STATE_CACHE_MAX_SIZE:
        _MANAGED_DOC_QUALITY_STATE_CACHE.pop(next(iter(_MANAGED_DOC_QUALITY_STATE_CACHE)))
    _MANAGED_DOC_QUALITY_STATE_CACHE[cache_key] = copy.deepcopy(quality_state)
    return copy.deepcopy(quality_state)


def collect_managed_doc_quality_blockers(project: Mapping[str, Any]) -> Dict[str, Any]:
    """Return canonical managed-doc quality blockers using readiness semantics."""
    quality_state = collect_managed_doc_quality_state(project)
    blocker_docs: list[Dict[str, Any]] = []
    for document in quality_state.get("documents", []):
        if not isinstance(document, dict):
            continue
        blocker_codes = [str(code) for code in (document.get("readiness_blocker_codes") or []) if code]
        if not blocker_codes:
            continue
        blocker_docs.append(
            {
                "doc_name": document.get("doc_name"),
                "path": document.get("path"),
                "blocker_codes": blocker_codes,
            }
        )

    return {
        "blocked": bool(blocker_docs),
        "total_blocker_count": int(quality_state.get("readiness_blocker_count", 0)),
        "blocker_docs": blocker_docs,
        "quality_state": quality_state,
    }


def build_readiness_summary(*, current_phase: Optional[str], managed_doc_quality: Dict[str, Any], log_signals: Optional[Sequence[Mapping[str, Any]]] = None) -> ReadinessSummary:
    log_signals = list(log_signals or [])
    log_blockers = sum(1 for signal in log_signals if bool(signal.get("blocking")))
    log_warnings = [signal for signal in log_signals if bool(signal.get("blocking"))]
    warning_count = int(managed_doc_quality.get("total_warning_count", 0)) + len(log_warnings)
    blocker_count = int(managed_doc_quality.get("readiness_blocker_count", 0)) + log_blockers
    log_friction = {
        "status": "blocked" if log_blockers else ("advisory" if log_signals else "pass"),
        "signals": [dict(signal) for signal in log_signals],
    }
    next_actions: list[str] = []
    if managed_doc_quality.get("readiness_blocker_count", 0):
        next_actions.append("Resolve SCF_* readiness blockers in managed docs for the active phase.")
    if log_blockers:
        next_actions.append("Address blocking LOG_* progress-log friction signals to improve trace quality.")
    if not next_actions:
        next_actions.append("Readiness checks are green for current phase scope.")

    return ReadinessSummary(
        current_phase=current_phase,
        managed_doc_quality=managed_doc_quality,
        log_friction=log_friction,
        warning_count=warning_count,
        blocker_count=blocker_count,
        next_actions=next_actions,
    )
