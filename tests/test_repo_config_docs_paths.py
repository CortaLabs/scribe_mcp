from pathlib import Path

from scribe_mcp.config.repo_config import RepoConfig


def test_repo_config_defaults_to_scribe_docs_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    config = RepoConfig.defaults_for_repo(repo_root)

    assert config.dev_plans_dir == repo_root / ".scribe" / "docs" / "dev_plans"


def test_repo_config_preserves_existing_legacy_docs_tree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    legacy_dir = repo_root / "docs" / "dev_plans"
    legacy_dir.mkdir(parents=True)

    config = RepoConfig.defaults_for_repo(repo_root)

    assert config.dev_plans_dir == legacy_dir


def test_repo_config_from_dict_keeps_explicit_legacy_override(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    config = RepoConfig.from_dict({"dev_plans_dir": "docs/dev_plans"}, repo_root)

    assert config.dev_plans_dir == repo_root / "docs" / "dev_plans"
