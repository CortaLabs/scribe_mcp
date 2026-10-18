from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scribe_mcp.config import repo_config as repo_config_module
from scribe_mcp.config.repo_config import RepoConfig, RepoDiscovery
from scribe_mcp.shared.path_policy import (
    apply_path_policy,
    load_path_policy,
    looks_like_local_absolute_path,
    render_projection,
)


def test_repo_config_parses_and_serializes_path_policy(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    raw_policy = {
        "enabled": True,
        "rules": [
            {
                "label": "repo",
                "private_prefix": str(repo_root),
                "scopes": ["append"],
            }
        ],
    }

    config = RepoConfig.from_dict({"path_policy": raw_policy}, repo_root)

    assert config.path_policy == raw_policy
    assert config.to_dict()["path_policy"] == raw_policy


def test_explicit_prefix_mapping_uses_safe_label(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config = RepoConfig.from_dict(
        {
            "path_policy": {
                "enabled": True,
                "rules": [
                    {"label": "repo", "private_prefix": str(repo_root)},
                ],
            }
        },
        repo_root,
    )
    policy = load_path_policy(config, {"root": str(repo_root)})

    result = apply_path_policy(
        {"path": str(repo_root / "docs" / "plan.md")},
        policy=policy,
        scope="append",
    )

    assert result.mapped == {"path": "repo/docs/plan.md"}
    assert result.violations == ()


def test_active_project_root_helper_requires_explicit_source(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config = RepoConfig.from_dict(
        {
            "path_policy": {
                "enabled": True,
                "rules": [
                    {"label": "active_root", "source": "active_project_root"},
                ],
            }
        },
        repo_root,
    )
    policy = load_path_policy(config, {"active_project_root": str(repo_root)})

    result = render_projection({"file_path": str(repo_root / "src" / "a.py")}, policy=policy)

    assert result.mapped["file_path"] == "active_root/src/a.py"
    assert result.violations == ()


def test_unresolved_mode_defaults_to_reject(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config = RepoConfig.from_dict({"path_policy": {"enabled": True}}, repo_root)

    policy = load_path_policy(config, {"root": str(repo_root)})

    assert policy.unresolved == "reject"


def test_longest_prefix_precedence_uses_config_order_for_ties(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    src_root = repo_root / "src"
    config = RepoConfig.from_dict(
        {
            "path_policy": {
                "enabled": True,
                "rules": [
                    {"label": "root", "private_prefix": str(repo_root)},
                    {"label": "source", "private_prefix": str(src_root)},
                    {"label": "source_duplicate", "private_prefix": str(src_root)},
                ],
            }
        },
        repo_root,
    )
    policy = load_path_policy(config, {"root": str(repo_root)})

    result = apply_path_policy({"path": str(src_root / "pkg" / "__init__.py")}, policy=policy, scope="append")

    assert result.mapped["path"] == "source/pkg/__init__.py"


def test_already_safe_labels_are_idempotent(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config = RepoConfig.from_dict(
        {
            "path_policy": {
                "enabled": True,
                "rules": [{"label": "repo", "private_prefix": str(repo_root)}],
            }
        },
        repo_root,
    )
    policy = load_path_policy(config, {"root": str(repo_root)})

    result = apply_path_policy({"path": "repo/docs/plan.md"}, policy=policy, scope="append")

    assert result.mapped["path"] == "repo/docs/plan.md"
    assert result.violations == ()


@pytest.mark.parametrize(
    "label",
    [
        "",
        "bad/label",
        "bad\\label",
        "home",
        "my_home_repo",
        "C:",
        "file://repo",
    ],
)
def test_invalid_public_labels_are_rejected(tmp_path: Path, label: str) -> None:
    repo_root = tmp_path / "repo"
    config = RepoConfig.from_dict(
        {
            "path_policy": {
                "enabled": True,
                "rules": [{"label": label, "private_prefix": str(repo_root)}],
            }
        },
        repo_root,
    )

    with pytest.raises(ValueError, match="label is invalid"):
        load_path_policy(config, {"root": str(repo_root)})


def test_label_can_match_public_repo_alias_without_raw_prefix(tmp_path: Path) -> None:
    repo_root = tmp_path / "scribe_mcp"
    config = RepoConfig.from_dict(
        {
            "path_policy": {
                "enabled": True,
                "rules": [{"label": "scribe_mcp", "private_prefix": str(repo_root)}],
            }
        },
        repo_root,
    )

    policy = load_path_policy(config, {"root": str(repo_root)})

    assert policy.rules[0].label == "scribe_mcp"


def test_global_only_path_policy_does_not_influence_repo_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_config = tmp_path / "home_config"
    home_config.mkdir()
    (home_config / "scribe.yaml").write_text(
        yaml.safe_dump(
            {
                "repo_slug": "global",
                "path_policy": {
                    "enabled": True,
                    "rules": [{"label": "global", "private_prefix": "/private/global"}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(repo_config_module, "config_home_dir", lambda: home_config)

    config = RepoDiscovery.load_config(repo_root, seed_if_missing=False)
    policy = load_path_policy(config, {"root": str(repo_root)})

    assert config.path_policy == {}
    assert policy.enabled is False
    assert apply_path_policy({"path": "/private/global/file.txt"}, policy=policy, scope="append").mapped[
        "path"
    ] == "/private/global/file.txt"


def test_repo_local_path_policy_survives_global_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    config_dir = repo_root / ".scribe" / "config"
    config_dir.mkdir(parents=True)
    home_config = tmp_path / "home_config"
    home_config.mkdir()
    (home_config / "scribe.yaml").write_text(
        yaml.safe_dump(
            {
                "path_policy": {
                    "enabled": True,
                    "rules": [{"label": "global", "private_prefix": "/private/global"}],
                },
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "scribe.yaml").write_text(
        yaml.safe_dump(
            {
                "repo_slug": "repo",
                "path_policy": {
                    "enabled": True,
                    "rules": [{"label": "repo", "private_prefix": str(repo_root)}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(repo_config_module, "config_home_dir", lambda: home_config)

    config = RepoDiscovery.load_config(repo_root, seed_if_missing=False)
    policy = load_path_policy(config, {"root": str(repo_root)})
    result = apply_path_policy({"path": str(repo_root / "file.txt")}, policy=policy, scope="append")

    assert config.path_policy["rules"][0]["label"] == "repo"
    assert result.mapped["path"] == "repo/file.txt"


def test_safe_violation_diagnostics_do_not_expose_raw_local_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    secret_path = "/Users/alice/private/project/file.txt"
    config = RepoConfig.from_dict(
        {
            "path_policy": {
                "enabled": True,
                "detect_absolute_unknown_keys": True,
                "rules": [{"label": "repo", "private_prefix": str(repo_root)}],
            }
        },
        repo_root,
    )
    policy = load_path_policy(config, {"root": str(repo_root)})

    result = apply_path_policy({"unexpected": secret_path}, policy=policy, scope="projection")

    assert result.mapped["unexpected"] != secret_path
    assert str(result.mapped["unexpected"]).startswith("unmapped_local_absolute_path:")
    assert len(result.violations) == 1
    violation = result.violations[0]
    assert violation.key == "unexpected"
    assert violation.scope == "projection"
    assert violation.reason == "unmapped_absolute_path"
    assert violation.safe_descriptor == "local_absolute_path"
    assert violation.value_sha256_prefix is not None
    assert secret_path not in repr(violation)
    assert "/Users/alice" not in repr(violation)
    assert secret_path not in repr(result)
    assert "/Users/alice" not in repr(result)


def test_local_absolute_path_detection_handles_posix_windows_and_unc() -> None:
    assert looks_like_local_absolute_path("/home/austin/repo/file.txt")
    assert looks_like_local_absolute_path("C:\\Users\\Austin\\repo\\file.txt")
    assert looks_like_local_absolute_path("\\\\server\\share\\file.txt")
    assert not looks_like_local_absolute_path("repo/file.txt")
