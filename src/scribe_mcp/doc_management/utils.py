"""Shared utility helpers for doc management actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.utils.time import format_utc


CANONICAL_DEV_PLAN_DOCS: Dict[str, str] = {
    "ARCHITECTURE_GUIDE.md": "architecture_guide",
    "PHASE_PLAN.md": "phase_plan",
    "CHECKLIST.md": "checklist",
}


@dataclass(frozen=True)
class ScribeSourceDocument:
    """Canonical source-family classification for a Scribe-managed document."""

    path: Path
    source_family: str
    doc_type: str
    project_slug: Optional[str] = None
    category: Optional[str] = None
    case_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


def hash_text(content: str) -> str:
    """Return a deterministic hash for document content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _split_into_sections(raw: str) -> List[str]:
    lines = raw.splitlines()
    sections: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if line.lstrip().startswith("#"):
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)
    return [
        "\n".join(section).strip()
        for section in sections
        if "\n".join(section).strip()
    ]


def _split_section(section: str, max_chars: int) -> List[str]:
    section = section.strip()
    if not section:
        return []
    if len(section) <= max_chars:
        return [section]

    lines = section.splitlines()
    heading = lines[0].strip() if lines and lines[0].lstrip().startswith("#") else None
    body = "\n".join(lines[1:]).strip() if heading else section
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    chunks: List[str] = []
    buffer: List[str] = []
    buffer_len = 0
    header_len = len(heading) + 2 if heading else 0
    limit = max(1, max_chars - header_len)

    for paragraph in paragraphs:
        addition = len(paragraph) + (2 if buffer else 0)
        if buffer_len + addition > limit and buffer:
            chunk = "\n\n".join(buffer)
            if heading:
                chunk = f"{heading}\n\n{chunk}"
            chunks.append(chunk)
            buffer = [paragraph]
            buffer_len = len(paragraph)
            continue
        buffer.append(paragraph)
        buffer_len += addition

    if buffer:
        chunk = "\n\n".join(buffer)
        if heading:
            chunk = f"{heading}\n\n{chunk}"
        chunks.append(chunk)

    return chunks


def chunk_text_for_vector(text: str, max_chars: int = 4000) -> List[str]:
    """Chunk markdown text into stable semantic chunks for vector indexing."""
    if not text:
        return []
    sections = _split_into_sections(text)
    chunks: List[str] = []
    for section in sections:
        chunks.extend(_split_section(section, max_chars=max_chars))
    return chunks


def generate_doc_entry_id(path: Path, chunk_index: int, content_hash: str) -> str:
    """Generate a stable ID for doc-index entries."""
    seed = f"{path}|{chunk_index}|{content_hash}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def parse_int(value: Any) -> Optional[int]:
    """Parse integer-like values, returning None on invalid input."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_numeric_grade(value: Any) -> Optional[float]:
    """Convert percentage-like numeric values to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        if text.endswith("%"):
            text = text[:-1]
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def load_doc_frontmatter_metadata(path: Path) -> Dict[str, Any]:
    """Best-effort frontmatter metadata extraction for shared document classification."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}

    try:
        return parse_frontmatter(text).frontmatter_data
    except ValueError:
        return {}


def _normalize_metadata_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_metadata_hint(metadata: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = _normalize_metadata_value(metadata.get(key))
        if value:
            return value
    return None


def _map_explicit_doc_type(value: Optional[str]) -> Optional[tuple[str, str]]:
    normalized = (value or "").strip().lower().replace(" ", "_")
    if not normalized:
        return None

    mapping = {
        "research": ("dev_plan", "research"),
        "spec": ("dev_plan", "spec"),
        "architecture": ("dev_plan", "architecture_guide"),
        "architecture_guide": ("dev_plan", "architecture_guide"),
        "phase": ("dev_plan", "phase_plan"),
        "phase_plan": ("dev_plan", "phase_plan"),
        "checklist": ("dev_plan", "checklist"),
        "bug": ("case_report", "bug_report"),
        "bug_report": ("case_report", "bug_report"),
        "security": ("case_report", "security_report"),
        "security_report": ("case_report", "security_report"),
    }
    return mapping.get(normalized)


def _classify_from_case_reference(case_reference: Optional[str]) -> Optional[tuple[str, str]]:
    normalized = (case_reference or "").strip().upper()
    if normalized.startswith("SEC-"):
        return ("case_report", "security_report")
    if normalized.startswith("BUG-"):
        return ("case_report", "bug_report")
    return None


def classify_scribe_source_document(
    path: Path,
    metadata: Optional[Dict[str, Any]] = None,
    project_root: Optional[Path] = None,
    docs_dir: Optional[Path] = None,
) -> Optional[ScribeSourceDocument]:
    """Classify a Scribe corpus document with metadata-first, case-aware rules."""
    resolved_path = path.resolve()
    resolved_project_root = project_root.resolve() if project_root else None
    resolved_docs_dir = docs_dir.resolve() if docs_dir else None

    combined_metadata: Dict[str, Any] = load_doc_frontmatter_metadata(resolved_path)
    if metadata:
        combined_metadata.update(metadata)

    explicit_doc_type = _extract_metadata_hint(
        combined_metadata,
        "doc_type",
        "source_family",
        "template_type",
        "doc_category",
    )
    classification = _map_explicit_doc_type(explicit_doc_type)
    if classification is None:
        classification = _classify_from_case_reference(
            _extract_metadata_hint(combined_metadata, "case_id", "doc_name")
        )

    source_family: Optional[str] = None
    doc_type: Optional[str] = None
    if classification is not None:
        source_family, doc_type = classification

    category: Optional[str] = None
    project_slug = _extract_metadata_hint(combined_metadata, "project_slug", "project_name")
    case_id = _extract_metadata_hint(combined_metadata, "case_id")

    if resolved_docs_dir is not None:
        try:
            relative_to_docs = resolved_path.relative_to(resolved_docs_dir)
        except ValueError:
            relative_to_docs = None
        if relative_to_docs is not None:
            project_slug = project_slug or resolved_docs_dir.name
            if source_family is None and relative_to_docs.parts:
                if relative_to_docs.parts[0] == "research" and resolved_path.suffix.lower() == ".md":
                    source_family = "dev_plan"
                    doc_type = "research"
                elif len(relative_to_docs.parts) == 1:
                    doc_type = CANONICAL_DEV_PLAN_DOCS.get(resolved_path.name)
                    if doc_type:
                        source_family = "dev_plan"

    if resolved_project_root is not None:
        docs_root = resolved_project_root / "docs"
        for folder_name, fallback_doc_type in (
            ("security", "security_report"),
            ("bugs", "bug_report"),
        ):
            candidate_root = docs_root / folder_name
            try:
                relative_to_case_root = resolved_path.relative_to(candidate_root)
            except ValueError:
                continue
            if len(relative_to_case_root.parts) >= 3:
                category = category or relative_to_case_root.parts[0]
                if source_family is None:
                    source_family = "case_report"
                    doc_type = fallback_doc_type
            break

    if source_family is None or doc_type is None:
        return None

    return ScribeSourceDocument(
        path=resolved_path,
        source_family=source_family,
        doc_type=doc_type,
        project_slug=project_slug,
        category=category,
        case_id=case_id,
        metadata=combined_metadata or None,
    )


def discover_scribe_source_documents(
    project_root: Path,
    *,
    dev_plans_dir: Optional[Path] = None,
    include_case_reports: bool = True,
) -> List[ScribeSourceDocument]:
    """Enumerate canonical Scribe corpus documents for downstream consumers."""
    resolved_project_root = project_root.resolve()
    discovered: List[ScribeSourceDocument] = []

    for dev_plans_root in _candidate_dev_plans_roots(
        resolved_project_root,
        explicit_dev_plans_dir=dev_plans_dir,
    ):
        for project_dir in sorted(path for path in dev_plans_root.iterdir() if path.is_dir()):
            for canonical_doc in CANONICAL_DEV_PLAN_DOCS:
                candidate = project_dir / canonical_doc
                if candidate.exists():
                    classified = classify_scribe_source_document(
                        candidate,
                        project_root=resolved_project_root,
                        docs_dir=project_dir,
                    )
                    if classified:
                        discovered.append(classified)
            research_dir = project_dir / "research"
            if research_dir.exists():
                for candidate in sorted(research_dir.glob("*.md")):
                    classified = classify_scribe_source_document(
                        candidate,
                        project_root=resolved_project_root,
                        docs_dir=project_dir,
                    )
                    if classified:
                        discovered.append(classified)

    if include_case_reports:
        for case_root in (
            resolved_project_root / "docs" / "bugs",
            resolved_project_root / "docs" / "security",
        ):
            if not case_root.exists():
                continue
            for candidate in sorted(case_root.glob("*/*/report.md")):
                classified = classify_scribe_source_document(
                    candidate,
                    project_root=resolved_project_root,
                )
                if classified:
                    discovered.append(classified)

    return discovered


def _candidate_dev_plans_roots(
    project_root: Path,
    *,
    explicit_dev_plans_dir: Optional[Path] = None,
) -> List[Path]:
    """Resolve dev-plan roots from explicit input, repo config, and legacy fallbacks."""
    candidates: List[Path] = []

    def _push(candidate: Path) -> None:
        resolved = candidate.resolve()
        if resolved.exists() and resolved not in candidates:
            candidates.append(resolved)

    if explicit_dev_plans_dir is not None:
        explicit = explicit_dev_plans_dir
        if not explicit.is_absolute():
            explicit = project_root / explicit
        _push(explicit)

    configured_root = _load_configured_dev_plans_root(project_root)
    if configured_root is not None:
        _push(configured_root)

    _push(project_root / ".scribe" / "docs" / "dev_plans")
    _push(project_root / "docs" / "dev_plans")
    return candidates


def _load_configured_dev_plans_root(project_root: Path) -> Optional[Path]:
    """Load a configured dev-plans root without mutating repo state."""
    config_paths = [
        project_root / ".scribe" / "config" / "scribe.yaml",
        project_root / ".scribe" / "scribe.yaml",
        project_root / ".scribe" / "scribe.yml",
        project_root / "docs" / "dev_plans" / "scribe.yaml",
        project_root / ".scribe" / "config.json",
    ]

    for config_path in config_paths:
        if not config_path.exists():
            continue
        try:
            if config_path.suffix in {".yaml", ".yml"}:
                data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            else:
                data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        configured = data.get("dev_plans_dir")
        if not configured:
            continue

        candidate = Path(str(configured))
        if not candidate.is_absolute():
            candidate = project_root / candidate
        return candidate.resolve()

    return None


def build_special_metadata(
    project: Dict[str, Any],
    metadata: Dict[str, Any],
    agent_id: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Prepare metadata payload for template rendering and storage."""
    prepared = metadata.copy()
    prepared.setdefault("project_name", project.get("name"))
    prepared.setdefault("project_root", project.get("root"))
    prepared.setdefault("agent_id", agent_id)
    prepared.setdefault("agent_name", prepared.get("agent_name", agent_id))
    prepared.setdefault("timestamp", prepared.get("timestamp", format_utc()))
    if extra:
        for key, value in extra.items():
            prepared.setdefault(key, value)
    return prepared


def resolve_custom_doc_path(
    project: Dict[str, Any],
    doc_category: str,
    doc_name: str,
) -> Optional[Path]:
    """Resolve custom document path by category and identifier."""
    progress_log = project.get("progress_log")
    if not progress_log:
        return None

    docs_dir = Path(progress_log).parent
    project_root = Path(project.get("root", ""))

    if doc_category == "research":
        research_dir = docs_dir / "research"
        if not research_dir.exists():
            return None

        candidate = research_dir / f"{doc_name}.md"
        if candidate.exists():
            return candidate

        if doc_name.endswith(".md"):
            candidate = research_dir / doc_name
            if candidate.exists():
                return candidate
        return None

    if doc_category in {"bugs", "security"}:
        desired_doc_type = "security_report" if doc_category == "security" else "bug_report"
        case_roots = [
            project_root / "docs" / "bugs",
            project_root / "docs" / "security",
        ]
        for case_root in case_roots:
            if not case_root.exists():
                continue
            for report_file in sorted(case_root.glob("*/*/report.md")):
                classification = classify_scribe_source_document(
                    report_file,
                    project_root=project_root,
                )
                if classification is None or classification.doc_type != desired_doc_type:
                    continue
                report_dir_name = report_file.parent.name
                if report_dir_name.endswith(f"_{doc_name}") or doc_name in report_dir_name:
                    return report_file
                if classification.case_id and classification.case_id == doc_name:
                    return report_file
        return None

    if doc_category == "reviews":
        pattern = f"REVIEW_REPORT_*{doc_name}*.md"
        candidates = list(docs_dir.glob(pattern))
        if candidates:
            return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return None

    if doc_category == "agent_cards":
        pattern = f"AGENT_REPORT_CARD_*{doc_name}*.md"
        candidates = list(docs_dir.glob(pattern))
        if candidates:
            return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return None

    return None


def _normalize_case_status(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    if normalized in {"", "unknown"}:
        return "open"
    if normalized in {"open", "investigating", "triage", "proposed", "in_progress", "active"}:
        return "open"
    if normalized in {"resolved", "closed", "fixed", "landed", "done", "completed"}:
        return "closed"
    return normalized


def _derive_case_id_from_path(report_path: Path) -> Optional[str]:
    # Expected governed layout: docs/{bugs|security}/{category}/{yyyy-mm-dd}_{slug}/report.md
    report_dir = report_path.parent.name
    if "_" not in report_dir:
        return None
    return _normalize_metadata_value(report_dir.split("_", 1)[1])


def extract_case_registry_metadata_from_report(
    report_path: Path,
    *,
    project_root: Optional[Path] = None,
    metadata: Optional[Dict[str, Any]] = None,
    project: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build normalized case-registry metadata from a governed bug/security report."""
    resolved_path = report_path.resolve()
    resolved_project_root = project_root.resolve() if project_root else None
    classification = classify_scribe_source_document(
        resolved_path,
        metadata=metadata,
        project_root=resolved_project_root,
    )
    if classification is None or classification.source_family != "case_report":
        return None

    payload_metadata: Dict[str, Any] = dict(classification.metadata or {})
    if metadata:
        payload_metadata.update(metadata)

    case_type = "security" if classification.doc_type == "security_report" else "bug"
    case_id = (
        _extract_metadata_hint(payload_metadata, "case_id", "slug", "doc_name")
        or classification.case_id
        or _derive_case_id_from_path(resolved_path)
    )
    if not case_id:
        return None

    report_root: Optional[Path] = resolved_project_root
    if report_root is None and project:
        report_root = Path(str(project.get("root", ""))).resolve()
    project_name = _normalize_metadata_value(payload_metadata.get("project_name"))
    if project_name is None and project:
        project_name = _normalize_metadata_value(project.get("name"))

    repo_root = _normalize_metadata_value(payload_metadata.get("project_root"))
    if repo_root is None and project:
        repo_root = _normalize_metadata_value(project.get("root"))
    if repo_root is None and report_root is not None:
        repo_root = str(report_root)

    return {
        "case_id": case_id,
        "case_type": case_type,
        "status": _normalize_case_status(payload_metadata.get("status")),
        "category": classification.category or _extract_metadata_hint(payload_metadata, "category"),
        "title": _extract_metadata_hint(payload_metadata, "title"),
        "severity": _extract_metadata_hint(payload_metadata, "severity"),
        "report_path": str(resolved_path),
        "doc_type": classification.doc_type,
        "source_family": classification.source_family,
        "project_name": project_name,
        "project_key": _extract_metadata_hint(payload_metadata, "project_key")
        or (_normalize_metadata_value(project.get("project_key")) if project else None),
        "repo_id": _extract_metadata_hint(payload_metadata, "repo_id")
        or (_normalize_metadata_value(project.get("repo_id")) if project else None),
        "repo_root": repo_root,
        "reported_at": _extract_metadata_hint(payload_metadata, "reported_at", "timestamp"),
        "provenance": {
            "source": "governed_report_doc",
            "doc_path": str(resolved_path),
        },
    }


def _record_like_value(record: Any, key: str) -> Any:
    if record is None:
        return None
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def merge_case_registry_metadata(
    *,
    existing: Optional[Dict[str, Any]],
    updates: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Merge case metadata by namespace instead of replacing the full payload."""
    merged: Dict[str, Any] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    if not isinstance(updates, dict):
        return merged or None

    for key, value in updates.items():
        if value is None:
            continue
        if key in {"", None}:
            continue
        if key in {"category", "ownership", "execution_provenance", "fix_link", "reported_at"}:
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                nested = dict(merged.get(key) or {})
                nested.update(value)
                merged[key] = nested
            else:
                merged[key] = value
            continue
        merged[key] = value
    return merged or None


def build_case_registry_upsert_kwargs(
    *,
    extracted: Optional[Dict[str, Any]] = None,
    existing_record: Optional[Any] = None,
    overrides: Optional[Dict[str, Any]] = None,
    metadata_overrides: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build exact kwargs for StorageBackend.upsert_case_registry_record(...)."""
    extracted_payload = extracted if isinstance(extracted, dict) else {}
    override_payload = overrides if isinstance(overrides, dict) else {}

    def _pick(*keys: str) -> Optional[str]:
        for key in keys:
            override_value = _normalize_metadata_value(override_payload.get(key))
            if override_value is not None:
                return override_value
            extracted_value = _normalize_metadata_value(extracted_payload.get(key))
            if extracted_value is not None:
                return extracted_value
            record_value = _normalize_metadata_value(_record_like_value(existing_record, key))
            if record_value is not None:
                return record_value
        return None

    case_id = _pick("case_id")
    case_type = _pick("case_type")
    project_name = _pick("project_name")
    repo_root = _pick("repo_root")
    doc_type = _pick("doc_type")
    doc_name = _pick("doc_name") or case_id
    doc_path = _pick("doc_path", "report_path")
    if not all((case_id, case_type, project_name, repo_root, doc_type, doc_name, doc_path)):
        return None

    extracted_metadata: Dict[str, Any] = {}
    if isinstance(extracted_payload.get("metadata"), dict):
        extracted_metadata.update(extracted_payload["metadata"])
    if extracted_payload.get("category") is not None:
        extracted_metadata["category"] = extracted_payload.get("category")
    if extracted_payload.get("reported_at") is not None:
        extracted_metadata["reported_at"] = extracted_payload.get("reported_at")
    if isinstance(extracted_payload.get("provenance"), dict):
        extracted_metadata["provenance"] = extracted_payload.get("provenance")

    merged_metadata = merge_case_registry_metadata(
        existing=_record_like_value(existing_record, "metadata"),
        updates=extracted_metadata,
    )
    merged_metadata = merge_case_registry_metadata(
        existing=merged_metadata,
        updates=metadata_overrides if isinstance(metadata_overrides, dict) else None,
    )

    return {
        "case_id": case_id,
        "case_type": case_type,
        "project_name": project_name,
        "repo_root": repo_root,
        "doc_type": doc_type,
        "doc_name": doc_name,
        "doc_path": doc_path,
        "title": _pick("title"),
        "status": _pick("status"),
        "severity": _pick("severity"),
        "source_tool": _pick("source_tool"),
        "metadata": merged_metadata,
    }


def build_case_registry_backfill_records(
    project_root: Path,
    *,
    reports: Optional[List[Path]] = None,
) -> List[Dict[str, Any]]:
    """Enumerate existing governed bug/security reports into normalized registry rows."""
    resolved_root = project_root.resolve()
    candidates: List[Path]
    if reports is not None:
        candidates = sorted(path.resolve() for path in reports)
    else:
        candidates = []
        for case_root in (resolved_root / "docs" / "bugs", resolved_root / "docs" / "security"):
            if not case_root.exists():
                continue
            candidates.extend(sorted(path.resolve() for path in case_root.glob("*/*/report.md")))

    records: List[Dict[str, Any]] = []
    for candidate in candidates:
        extracted = extract_case_registry_metadata_from_report(
            candidate,
            project_root=resolved_root,
        )
        if extracted is not None:
            records.append(extracted)
    return records
