from pathlib import Path

from scribe_mcp.doc_management.quality.rules.release_gate import resolve_quality_mode
from scribe_mcp.doc_management.scaffold_quality import collect_managed_doc_quality_warnings


def test_release_gate_explicit_mode_records_trigger() -> None:
    info = resolve_quality_mode(metadata={"quality": {"mode": "release_gate", "release_trigger": "manual_release_intent"}})
    assert info["mode"] == "release_gate"
    assert info["release_trigger"] == "manual_release_intent"
    assert info["trigger_source"] == "explicit"


def test_release_gate_inferred_only_when_flagged(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='1.0.0'\n", encoding="utf-8")
    info = resolve_quality_mode(metadata={"quality": {"infer_release_gate": True}}, project_root=tmp_path)
    assert info["mode"] == "release_gate"
    assert "repo.pyproject_present" in info["release_triggers"]


def test_local_default_keeps_context_drift_advisory(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    text = """# Changelog

## Entry
- `entry_id`: 20260512:test
- `entry_status`: accepted
- `title`: Test
- `summary`: Something changed
- `evidence_refs`:
  - test
- `observed_context`:
  - `value`: 1.0.0
  - `source`: pyproject
"""
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
        metadata={"quality": {"mode": "local_default"}},
    )
    codes = {w.get("code") for w in warnings}
    assert "SCF_RESEARCH_CONTEXT_DRIFT" not in codes


def test_critical_blockers_are_not_suppressible() -> None:
    warnings = collect_managed_doc_quality_warnings(
        text="# X\n\nReplace this with final text.\n",
        doc_name="SPEC",
        metadata={"quality": {"suppressions": {"SCF_TEMPLATE_PROSE": "hide"}}},
    )
    codes = {w.get("code") for w in warnings}
    assert "SCF_TEMPLATE_PROSE" in codes


def test_release_gate_explicit_emits_current_version_missing_for_changelog(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    text = """# Project Changelog

## Prior release
- `entry_id`: 20260512:prior
- `entry_status`: accepted
- `title`: Prior
- `summary`: Something changed
- `evidence_refs`:
  - test
- `observed_context`:
  - `value`: 1.0.0
  - `source`: pyproject
"""
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
        metadata={"quality": {"mode": "release_gate"}},
    )
    codes = {w.get("code") for w in warnings}
    assert "SCF_CHANGELOG_CURRENT_VERSION_MISSING" in codes


def test_release_gate_inferred_emits_current_version_missing_for_changelog(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    text = """# Project Changelog

## Prior release
- `entry_id`: 20260512:prior
- `entry_status`: accepted
- `title`: Prior
- `summary`: Something changed
- `evidence_refs`:
  - test
- `observed_context`:
  - `value`: 1.0.0
  - `source`: pyproject
"""
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
        metadata={"quality": {"infer_release_gate": True}, "_quality_runtime": {"mode": "release_gate"}},
    )
    codes = {w.get("code") for w in warnings}
    assert "SCF_CHANGELOG_CURRENT_VERSION_MISSING" in codes


def test_local_default_does_not_emit_current_version_missing_for_changelog(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    text = """# Project Changelog

## Prior release
- `entry_id`: 20260512:prior
- `entry_status`: accepted
- `title`: Prior
- `summary`: Something changed
- `evidence_refs`:
  - test
- `observed_context`:
  - `value`: 1.0.0
  - `source`: pyproject
"""
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
        metadata={"quality": {"mode": "local_default"}},
    )
    codes = {w.get("code") for w in warnings}
    assert "SCF_CHANGELOG_CURRENT_VERSION_MISSING" not in codes


def test_release_gate_current_version_missing_is_unsuppressible(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")
    text = """# Project Changelog

## Prior release
- `entry_id`: 20260512:prior
- `entry_status`: accepted
- `title`: Prior
- `summary`: Something changed
- `evidence_refs`:
  - test
- `observed_context`:
  - `value`: 1.0.0
  - `source`: pyproject
"""
    warnings = collect_managed_doc_quality_warnings(
        text=text,
        doc_name="changelog",
        path=tmp_path / "CHANGELOG.md",
        project={"root": str(tmp_path), "docs_dir": str(tmp_path)},
        metadata={
            "quality": {
                "mode": "release_gate",
                "suppressions": {"SCF_CHANGELOG_CURRENT_VERSION_MISSING": "hide"},
            }
        },
    )
    codes = {w.get("code") for w in warnings}
    assert "SCF_CHANGELOG_CURRENT_VERSION_MISSING" in codes
