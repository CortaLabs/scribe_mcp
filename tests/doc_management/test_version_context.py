from pathlib import Path
from unittest.mock import patch

from scribe_mcp.doc_management.version_context import resolve_observed_context, unknown_context


def test_manual_context_takes_precedence(tmp_path: Path) -> None:
    context = resolve_observed_context(
        repo_root=tmp_path,
        pyproject_path=tmp_path / "pyproject.toml",
        manual_value="release-candidate",
        observed_at="2026-05-12T00:00:00Z",
    )
    assert context.value == "release-candidate"
    assert context.source == "manual"
    assert context.observed_at == "2026-05-12T00:00:00Z"
    assert context.confidence == "exact"


def test_pyproject_context_used_when_present(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8")

    context = resolve_observed_context(
        repo_root=tmp_path,
        pyproject_path=pyproject,
        observed_at="2026-05-12T00:00:00Z",
    )

    assert context.value == "1.2.3"
    assert context.source == "pyproject"
    assert context.observed_at == "2026-05-12T00:00:00Z"
    assert context.confidence == "exact"


def test_unknown_fallback_when_no_sources(tmp_path: Path) -> None:
    context = resolve_observed_context(
        repo_root=tmp_path,
        pyproject_path=tmp_path / "missing.toml",
        observed_at="2026-05-12T00:00:00Z",
    )
    assert context == unknown_context(observed_at="2026-05-12T00:00:00Z")


def test_git_commit_fallback_when_pyproject_missing(tmp_path: Path) -> None:
    with patch("scribe_mcp.doc_management.version_context._run_git") as run_git:
        run_git.side_effect = ["abc1234", " M changed.py"]
        context = resolve_observed_context(
            repo_root=tmp_path,
            pyproject_path=tmp_path / "missing.toml",
            observed_at="2026-05-12T00:00:00Z",
        )
    assert context.source == "git_commit"
    assert context.value == "abc1234"
    assert context.commit == "abc1234"
    assert context.dirty is True
