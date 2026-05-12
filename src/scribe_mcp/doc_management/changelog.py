from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence


_ENTRY_ID_RE = re.compile(r"^\d{8}:[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ChangelogEntry:
    entry_id: str
    entry_status: str
    title: str
    summary: str
    evidence_refs: list[str]
    observed_context: dict[str, Any] | None
    section_text: str

    @property
    def source_key(self) -> str:
        return self.entry_id


def parse_changelog_entries(text: str) -> list[ChangelogEntry]:
    entries: list[ChangelogEntry] = []
    sections = re.split(r"(?m)^##\s+", text)
    for section in sections[1:]:
        raw = "## " + section
        fields = _extract_fields(raw)
        if not fields:
            continue
        evidence_refs = [item.strip() for item in fields.get("evidence_refs", []) if item.strip()]
        entries.append(
            ChangelogEntry(
                entry_id=fields.get("entry_id", "").strip(),
                entry_status=fields.get("entry_status", "").strip().lower(),
                title=fields.get("title", "").strip(),
                summary=fields.get("summary", "").strip(),
                evidence_refs=evidence_refs,
                observed_context=_extract_observed_context(raw),
                section_text=raw,
            )
        )
    return entries


def is_valid_entry_id(entry_id: str) -> bool:
    return bool(_ENTRY_ID_RE.match(entry_id.strip()))


def accepted_entries(entries: Sequence[ChangelogEntry]) -> list[ChangelogEntry]:
    return [entry for entry in entries if entry.entry_status == "accepted"]


def parse_global_entry_ids(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"(?m)^-\s*`?source_entry_id`?\s*:\s*(.+)$", text)]


@dataclass(frozen=True)
class GlobalChangelogEntry:
    title: str
    source_project: str
    source_entry_id: str
    summary: str
    section_text: str

    @property
    def source_key(self) -> tuple[str, str]:
        return (self.source_project, self.source_entry_id)


def parse_global_changelog_entries(text: str, *, default_source_project: str = "") -> list[GlobalChangelogEntry]:
    entries: list[GlobalChangelogEntry] = []
    sections = re.split(r"(?m)^##\s+", text)
    for section in sections[1:]:
        raw = "## " + section
        title = section.splitlines()[0].strip()
        source_entry_id = _match_scalar_field(raw, "source_entry_id")
        if not source_entry_id:
            continue
        source_project = _match_scalar_field(raw, "source_project").strip() or default_source_project
        summary = _match_scalar_field(raw, "summary")
        entries.append(
            GlobalChangelogEntry(
                title=title,
                source_project=source_project,
                source_entry_id=source_entry_id.strip(),
                summary=summary.strip(),
                section_text=raw,
            )
        )
    return entries


def preview_global_reconciliation(
    *,
    project_slug: str,
    project_changelog_text: str,
    global_changelog_text: str,
) -> dict[str, Any]:
    accepted = accepted_entries(parse_changelog_entries(project_changelog_text))
    source_ids = [entry.entry_id for entry in accepted]
    duplicate_source_keys = sorted({entry_id for entry_id in source_ids if source_ids.count(entry_id) > 1})

    accepted_map = {entry.entry_id: entry for entry in accepted}
    global_entries = parse_global_changelog_entries(
        global_changelog_text,
        default_source_project=project_slug,
    )
    global_map = {entry.source_key: entry for entry in global_entries}
    global_project_entry_ids = {entry.source_entry_id for entry in global_entries if entry.source_project == project_slug}

    missing_in_global = sorted([entry_id for entry_id in accepted_map if (project_slug, entry_id) not in global_map])
    orphaned_global_entries = sorted([entry_id for entry_id in global_project_entry_ids if entry_id not in accepted_map])

    changed_since_global: list[str] = []
    for entry_id, entry in accepted_map.items():
        global_entry = global_map.get((project_slug, entry_id))
        if global_entry and entry.summary != global_entry.summary:
            changed_since_global.append(entry_id)

    unversioned_entries = sorted(
        [entry.entry_id for entry in accepted if re.search(r"(?m)^-\s*`?observed_context`?\s*:", entry.section_text) is None]
    )
    skipped = sorted(
        [entry_id for entry_id in accepted_map if (project_slug, entry_id) in global_map and entry_id not in changed_since_global]
    )

    return {
        "missing_in_global": missing_in_global,
        "changed_since_global": sorted(changed_since_global),
        "duplicate_source_keys": duplicate_source_keys,
        "orphaned_global_entries": orphaned_global_entries,
        "unversioned_entries": unversioned_entries,
        "source_entry_ids": {
            "adds": missing_in_global,
            "updates": sorted(changed_since_global),
            "removals": orphaned_global_entries,
            "skips": skipped,
        },
        "writes_performed": False,
    }


def render_global_changelog(*, project_slug: str, project_changelog_text: str) -> str:
    accepted = accepted_entries(parse_changelog_entries(project_changelog_text))
    header = "# Global Changelog\n\n"
    if not accepted:
        return header

    sections: list[str] = []
    for entry in accepted:
        sections.append(
            "\n".join(
                [
                    f"## {entry.title}",
                    f"- `source_project`: {project_slug}",
                    f"- `source_entry_id`: {entry.entry_id}",
                    f"- `summary`: {entry.summary}",
                ]
            )
        )
    return header + "\n\n".join(sections) + "\n"


def reconcile_global_changelog(
    *,
    project_slug: str,
    project_changelog_text: str,
    existing_global_changelog_text: str,
) -> str:
    accepted = accepted_entries(parse_changelog_entries(project_changelog_text))
    existing_entries = parse_global_changelog_entries(existing_global_changelog_text, default_source_project="")

    kept_other_projects = [entry for entry in existing_entries if entry.source_project != project_slug]
    derived_current_project: list[GlobalChangelogEntry] = [
        GlobalChangelogEntry(
            title=entry.title,
            source_project=project_slug,
            source_entry_id=entry.entry_id,
            summary=entry.summary,
            section_text="",
        )
        for entry in accepted
    ]
    merged_entries = kept_other_projects + derived_current_project
    return _render_global_entries(merged_entries)


def _render_global_entries(entries: Sequence[GlobalChangelogEntry]) -> str:
    header = "# Global Changelog\n\n"
    if not entries:
        return header
    sections: list[str] = []
    for entry in entries:
        sections.append(
            "\n".join(
                [
                    f"## {entry.title}",
                    f"- `source_project`: {entry.source_project}",
                    f"- `source_entry_id`: {entry.source_entry_id}",
                    f"- `summary`: {entry.summary}",
                ]
            )
        )
    return header + "\n\n".join(sections) + "\n"


def _extract_fields(section_text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for key in ("entry_id", "entry_status", "title", "summary"):
        match = re.search(rf"(?m)^-\s*`?{key}`?\s*:\s*(.+)$", section_text)
        if match:
            fields[key] = match.group(1).strip()

    evidence_match = re.search(r"(?ms)^-\s*`?evidence_refs`?\s*:\s*(.+?)(?:\n^-\s*`?[a-z_]+`?\s*:|\Z)", section_text)
    evidence: list[str] = []
    if evidence_match:
        block = evidence_match.group(1)
        evidence = [m.group(1).strip() for m in re.finditer(r"(?m)^\s*-\s+(.+)$", block)]
    fields["evidence_refs"] = evidence
    return fields


def _match_scalar_field(section_text: str, field_name: str) -> str:
    match = re.search(rf"(?m)^-\s*`?{field_name}`?\s*:\s*(.+)$", section_text)
    if match:
        return match.group(1)
    return ""


def _extract_observed_context(section_text: str) -> dict[str, Any] | None:
    block_match = re.search(
        r"(?ms)^-\s*`?observed_context`?\s*:\s*(.+?)(?:\n^-\s*`?[a-z_]+`?\s*:|\Z)",
        section_text,
    )
    if not block_match:
        return None

    block = block_match.group(1)
    values = {
        m.group(1).strip(): m.group(2).strip()
        for m in re.finditer(r"(?m)^\s*-\s*`?([a-z_]+)`?\s*:\s*(.+)$", block)
    }
    if not values:
        return None

    dirty_value = values.get("dirty")
    dirty: bool | None = None
    if dirty_value is not None:
        lowered = dirty_value.lower()
        if lowered in {"true", "yes", "1"}:
            dirty = True
        elif lowered in {"false", "no", "0"}:
            dirty = False

    return {
        "value": values.get("value", "unknown"),
        "source": values.get("source", "unknown"),
        "commit": values.get("commit"),
        "dirty": dirty,
        "observed_at": values.get("observed_at", ""),
        "confidence": values.get("confidence", "unknown"),
    }
