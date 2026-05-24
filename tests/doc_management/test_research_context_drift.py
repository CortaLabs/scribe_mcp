from pathlib import Path

from scribe_mcp.doc_management.scaffold_quality import collect_managed_doc_quality_warnings


def _changelog_with_context(value: str, source: str = "pyproject") -> str:
    return f"""# Changelog

## Entry
- `entry_id`: 20260512:test
- `entry_status`: accepted
- `title`: Test
- `summary`: Something changed
- `evidence_refs`:
  - test
- `observed_context`:
  - `value`: {value}
  - `source`: {source}
  - `commit`: abc123
  - `dirty`: false
  - `observed_at`: 2026-05-12T00:00:00Z
  - `confidence`: exact
"""


def test_context_drift_warns_only_on_same_source_material_change(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    text = _changelog_with_context("1.0.0", "pyproject")
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
        metadata={"quality": {"mode": "release_gate"}},
    )
    codes = {w.get("code") for w in warnings}
    assert "SCF_RESEARCH_CONTEXT_DRIFT" in codes


def test_context_drift_ignores_absent_or_incidental_version_text(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    incidental = "# Research\nWe discussed version 1.2.3 in prose only.\n"
    warnings = collect_managed_doc_quality_warnings(
        text=incidental,
        doc_name="RESEARCH_NOTE",
        path=tmp_path / "research" / "RESEARCH_NOTE.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
    )
    assert all(w.get("code") != "SCF_RESEARCH_CONTEXT_DRIFT" for w in warnings)

    no_context_changelog = "# Changelog\n\n## E\n- `entry_id`: 20260512:test\n- `entry_status`: accepted\n"
    warnings2 = collect_managed_doc_quality_warnings(
        text=no_context_changelog,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
    )
    assert all(w.get("code") != "SCF_RESEARCH_CONTEXT_DRIFT" for w in warnings2)


def test_context_drift_suppressed_for_unknown_observed_source(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    text = _changelog_with_context("1.0.0", "unknown")
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
        metadata={"quality": {"mode": "release_gate"}},
    )
    assert all(w.get("code") != "SCF_RESEARCH_CONTEXT_DRIFT" for w in warnings)


def test_context_drift_suppressed_when_stored_source_differs_from_current_resolved_source(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    text = _changelog_with_context("1.0.0", "changelog")
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
        metadata={"quality": {"mode": "release_gate"}},
    )
    assert all(w.get("code") != "SCF_RESEARCH_CONTEXT_DRIFT" for w in warnings)
