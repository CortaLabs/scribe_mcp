from pathlib import Path

from scribe_mcp.doc_management.version_context import resolve_observed_context


def test_version_context_unknown_for_unversioned_non_git(tmp_path: Path) -> None:
    context = resolve_observed_context(
        repo_root=tmp_path,
        pyproject_path=tmp_path / "missing.toml",
        observed_at="2026-05-12T00:00:00Z",
    )
    assert context.value == "unknown"
    assert context.source == "unknown"
    assert context.commit is None
    assert context.dirty is None
    assert context.confidence == "unknown"


def test_version_context_reads_pyproject_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\nversion = "9.8.7"\n', encoding="utf-8")

    context = resolve_observed_context(
        repo_root=tmp_path,
        pyproject_path=pyproject,
        observed_at="2026-05-12T00:00:00Z",
    )
    assert context.value == "9.8.7"
    assert context.source == "pyproject"
    assert context.confidence == "exact"
