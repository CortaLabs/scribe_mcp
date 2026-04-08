from pathlib import Path

from scribe_mcp.tools.generate_doc_templates import _target_directory


def test_target_directory_defaults_to_project_root(tmp_path: Path) -> None:
    out = _target_directory("My Project", None, project_root=tmp_path)
    assert out == tmp_path / ".scribe" / "docs" / "dev_plans" / "my_project"


def test_target_directory_treats_base_dir_as_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    out = _target_directory("My Project", str(repo_root), project_root=tmp_path)
    assert out == repo_root / ".scribe" / "docs" / "dev_plans" / "my_project"


def test_target_directory_accepts_scribe_docs_dev_plans_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    base_dir = repo_root / ".scribe" / "docs" / "dev_plans"
    base_dir.mkdir(parents=True)
    out = _target_directory("My Project", str(base_dir), project_root=tmp_path)
    assert out == base_dir / "my_project"


def test_target_directory_accepts_scribe_docs_dev_plans_slug_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    base_dir = repo_root / ".scribe" / "docs" / "dev_plans" / "my_project"
    base_dir.mkdir(parents=True)
    out = _target_directory("My Project", str(base_dir), project_root=tmp_path)
    assert out == base_dir


def test_target_directory_accepts_docs_dev_plans_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    base_dir = repo_root / "docs" / "dev_plans"
    base_dir.mkdir(parents=True)
    out = _target_directory("My Project", str(base_dir), project_root=tmp_path)
    assert out == base_dir / "my_project"


def test_target_directory_accepts_docs_dev_plans_slug_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    base_dir = repo_root / "docs" / "dev_plans" / "my_project"
    base_dir.mkdir(parents=True)
    out = _target_directory("My Project", str(base_dir), project_root=tmp_path)
    assert out == base_dir


def test_target_directory_resolves_relative_docs_dev_plans_dir_against_project_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    out = _target_directory("My Project", "docs/dev_plans", project_root=repo_root)
    assert out == repo_root / "docs" / "dev_plans" / "my_project"


def test_target_directory_resolves_relative_docs_dev_plans_slug_dir_against_project_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    out = _target_directory("My Project", "docs/dev_plans/my_project", project_root=repo_root)
    assert out == repo_root / "docs" / "dev_plans" / "my_project"
