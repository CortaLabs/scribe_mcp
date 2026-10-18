from __future__ import annotations

import json
import shutil
import sys
import subprocess
import tomllib
from pathlib import Path

import yaml

from scribe_mcp.cli import main as cli_main
from scribe_mcp.scripts.project_codex_plugin import project_codex_plugin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sync_plugin_skills  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_PLUGIN_ROOT = REPO_ROOT / "plugins" / "claude"
CODEX_PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex"
MARKETPLACE_PATH = CODEX_PLUGIN_ROOT / "marketplace.json"
PACKAGE_BUNDLE_ROOT = REPO_ROOT / "src" / "scribe_mcp" / "plugins_bundle"
ALLOWED_PUBLIC_AGENTS = [
    "scribe-architect",
    "scribe-bug-hunter",
    "scribe-coder",
    "scribe-doc-writer",
    "scribe-research-analyst",
    "scribe-review-agent",
    "scribe-security-agent",
]
PRIVATE_LOGIC_MARKERS = (
    "ask agent",
    "ask council",
    "ask self",
    "council",
    "council only",
    "coordinator wait loop",
    "end session",
    "hidden internal authority",
    "internal authority",
    "internal orchestration",
    "internal workflow",
    "open session",
    "operator escalation",
    "orchestration loop",
    "orchestrator",
    "private agent",
    "private escalation",
    "private internal",
    "seshat",
    "store memory",
    "team escalation",
    "teamcreate",
    "unpublished tool",
    "wait loop",
)


def _only_manifest(directory: Path) -> list[str]:
    return sorted(str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file())


def _agent_slugs(directory: Path, suffix: str) -> list[str]:
    return sorted(path.stem for path in directory.glob(f"*{suffix}"))


def _normalized_policy_text(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _assert_public_safe_text(text: str) -> None:
    normalized_text = _normalized_policy_text(text)
    for marker in PRIVATE_LOGIC_MARKERS:
        assert _normalized_policy_text(marker) not in normalized_text


def _assert_public_safe_markdown_dir(directory: Path) -> None:
    for slug in ALLOWED_PUBLIC_AGENTS:
        _assert_public_safe_text((directory / f"{slug}.md").read_text(encoding="utf-8"))


def _assert_public_safe_catalog(catalog: dict[str, object]) -> None:
    agent_entries = catalog["agents"]
    assert isinstance(agent_entries, list)
    assert [agent["name"] for agent in agent_entries] == ALLOWED_PUBLIC_AGENTS
    for agent in agent_entries:
        description = agent["description"]
        assert isinstance(description, str)
        assert description.strip()
        _assert_public_safe_text(description)


def _assert_public_mcp_config(
    plugin_root: Path,
    bundle_root: Path,
    manifest: dict[str, object],
) -> None:
    config_reference = manifest["mcpServers"]
    assert config_reference == "./.mcp.json"
    config_path = Path(config_reference)
    canonical_config = plugin_root / config_path
    bundle_config = bundle_root / config_path
    canonical_bytes = canonical_config.read_bytes()
    assert bundle_config.read_bytes() == canonical_bytes
    assert json.loads(canonical_bytes) == {
        "mcpServers": {"scribe": {"command": "scribe-server"}}
    }


def test_claude_bundle_keeps_manifest_only_directory_shape_and_public_assets() -> None:
    assert _only_manifest(CLAUDE_PLUGIN_ROOT / ".claude-plugin") == ["plugin.json"]
    assert _agent_slugs(CLAUDE_PLUGIN_ROOT / "agents", ".md") == ALLOWED_PUBLIC_AGENTS

    manifest = json.loads((CLAUDE_PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "scribe-mcp"
    assert manifest["agents"] == "./agents/"
    assert manifest["skills"] == "./skills/"
    assert manifest["hooks"] == "./hooks/hooks.json"
    assert manifest["mcpServers"] == "./.mcp.json"
    _assert_public_mcp_config(
        CLAUDE_PLUGIN_ROOT,
        PACKAGE_BUNDLE_ROOT / "claude",
        manifest,
    )

    hooks_config = json.loads((CLAUDE_PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert list(hooks_config) == ["hooks"]
    hook_command = hooks_config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert hook_command == "${CLAUDE_PLUGIN_ROOT}/bin/protect-managed-docs.sh"

    for slug in ("scribe-integration", "scribe-onboarding"):
        assert (CLAUDE_PLUGIN_ROOT / "skills" / slug / "SKILL.md").exists()
    _assert_public_safe_markdown_dir(CLAUDE_PLUGIN_ROOT / "agents")


def test_codex_bundle_and_marketplace_keep_root_layout_and_allowlist_only() -> None:
    assert _only_manifest(CODEX_PLUGIN_ROOT / ".codex-plugin") == ["plugin.json"]
    assert _agent_slugs(CODEX_PLUGIN_ROOT / "agents", ".toml") == ALLOWED_PUBLIC_AGENTS
    assert _agent_slugs(CODEX_PLUGIN_ROOT / "assets" / "agents", ".md") == ALLOWED_PUBLIC_AGENTS

    manifest = json.loads((CODEX_PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "scribe-mcp"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    _assert_public_mcp_config(
        CODEX_PLUGIN_ROOT,
        PACKAGE_BUNDLE_ROOT / "codex",
        manifest,
    )
    assert "apps" not in manifest
    assert "council" not in manifest["description"].lower()
    assert "council" not in manifest["interface"]["longDescription"].lower()

    app_config = json.loads((CODEX_PLUGIN_ROOT / ".app.json").read_text(encoding="utf-8"))
    assert app_config == {"apps": {}}

    catalog = json.loads((CODEX_PLUGIN_ROOT / "assets" / "agents.json").read_text(encoding="utf-8"))
    _assert_public_safe_catalog(catalog)

    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    plugin_entry = marketplace["plugins"][0]
    assert plugin_entry["name"] == "scribe-mcp"
    assert plugin_entry["source"]["path"] == "./plugins/codex"
    assert plugin_entry["policy"]["installation"] == "AVAILABLE"

    _assert_public_safe_markdown_dir(CODEX_PLUGIN_ROOT / "assets" / "agents")


def test_project_codex_plugin_preserves_existing_user_files_and_is_idempotent(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    agents_dir = codex_home / "agents"
    agents_dir.mkdir(parents=True)
    skill_dir = codex_home / "skills" / "scribe-integration"
    skill_dir.mkdir(parents=True)

    config_path = codex_home / "config.toml"
    config_path.write_text(
        """
title = "custom"

[features]
existing_feature = true

[agents]
max_depth = 7

[agents.scribe-coder]
config_file = "agents/custom-coder.toml"
description = "Custom coder"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    custom_toml = agents_dir / "scribe-coder.toml"
    custom_md = agents_dir / "scribe-coder.md"
    custom_skill = skill_dir / "SKILL.md"
    custom_toml.write_text("custom coder toml\n", encoding="utf-8")
    custom_md.write_text("custom coder markdown\n", encoding="utf-8")
    custom_skill.write_text("# Custom skill\n", encoding="utf-8")

    first_result = project_codex_plugin(
        plugin_root=CODEX_PLUGIN_ROOT,
        codex_home=codex_home,
        config_path=config_path,
    )
    second_result = project_codex_plugin(
        plugin_root=CODEX_PLUGIN_ROOT,
        codex_home=codex_home,
        config_path=config_path,
    )

    config_data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config_data["title"] == "custom"
    assert config_data["features"]["existing_feature"] is True
    assert config_data["features"]["multi_agent"] is True
    assert config_data["agents"]["max_depth"] == 7
    assert config_data["agents"]["max_threads"] == 12
    assert config_data["agents"]["scribe-coder"]["config_file"] == "agents/custom-coder.toml"
    assert config_data["agents"]["scribe-coder"]["description"] == "Custom coder"

    assert custom_toml.read_text(encoding="utf-8") == "custom coder toml\n"
    assert custom_md.read_text(encoding="utf-8") == "custom coder markdown\n"
    assert custom_skill.read_text(encoding="utf-8") == "# Custom skill\n"

    projected_review_toml = codex_home / "agents" / "scribe-review-agent.toml"
    projected_review_md = codex_home / "agents" / "scribe-review-agent.md"
    assert projected_review_toml.exists()
    assert projected_review_md.exists()

    assert first_result["projected_agent_config_status"][str(custom_toml)] == "preserved_existing"
    assert first_result["projected_agent_markdown_status"][str(custom_md)] == "preserved_existing"
    assert first_result["projected_skill_status"][str(custom_skill)] == "preserved_existing"
    assert first_result["projected_agent_config_status"][str(projected_review_toml)] == "created"
    assert first_result["projected_agent_markdown_status"][str(projected_review_md)] == "created"
    assert second_result["projected_agent_config_status"][str(custom_toml)] == "preserved_existing"
    assert second_result["projected_agent_markdown_status"][str(custom_md)] == "preserved_existing"
    assert second_result["projected_agent_config_status"][str(projected_review_toml)] == "unchanged"
    assert second_result["projected_agent_markdown_status"][str(projected_review_md)] == "unchanged"
    assert second_result["projected_skill_status"][str(custom_skill)] == "preserved_existing"
    assert second_result["config_status"] == "unchanged"

    assert _agent_slugs(codex_home / "agents", ".toml") == ALLOWED_PUBLIC_AGENTS
    assert _agent_slugs(codex_home / "agents", ".md") == ALLOWED_PUBLIC_AGENTS
    for slug in ALLOWED_PUBLIC_AGENTS:
        _assert_public_safe_text((codex_home / "agents" / f"{slug}.toml").read_text(encoding="utf-8"))
        _assert_public_safe_text(config_data["agents"][slug]["description"])
    _assert_public_safe_markdown_dir(codex_home / "agents")


def test_scribe_cli_projects_codex_plugin_with_packaged_entry_flow(tmp_path: Path) -> None:
    codex_home = tmp_path / "cli-codex-home"
    exit_code = cli_main.main(
        [
            "plugins",
            "project-codex",
            "--plugin-root",
            str(CODEX_PLUGIN_ROOT),
            "--codex-home",
            str(codex_home),
        ]
    )

    assert exit_code == 0
    config_data = tomllib.loads((codex_home / "config.toml").read_text(encoding="utf-8"))
    assert config_data["agents"]["scribe-review-agent"]["config_file"] == "agents/scribe-review-agent.toml"
    assert _agent_slugs(codex_home / "agents", ".toml") == ALLOWED_PUBLIC_AGENTS
    assert _agent_slugs(codex_home / "agents", ".md") == ALLOWED_PUBLIC_AGENTS
    for slug in ALLOWED_PUBLIC_AGENTS:
        _assert_public_safe_text((codex_home / "agents" / f"{slug}.toml").read_text(encoding="utf-8"))
        _assert_public_safe_text(config_data["agents"][slug]["description"])
    _assert_public_safe_markdown_dir(codex_home / "agents")


def test_scribe_cli_projects_codex_plugin_reports_missing_manifest(tmp_path: Path, capsys) -> None:
    plugin_root = tmp_path / "missing-plugin-root"
    plugin_root.mkdir()

    exit_code = cli_main.main(
        [
            "plugins",
            "project-codex",
            "--plugin-root",
            str(plugin_root),
            "--codex-home",
            str(tmp_path / "codex-home"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error: Codex plugin manifest not found under" in captured.err


def test_scribe_cli_projects_codex_plugin_reports_malformed_config(tmp_path: Path, capsys) -> None:
    codex_home = tmp_path / "bad-config-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text("[agents\nbad = true\n", encoding="utf-8")

    exit_code = cli_main.main(
        [
            "plugins",
            "project-codex",
            "--plugin-root",
            str(CODEX_PLUGIN_ROOT),
            "--codex-home",
            str(codex_home),
            "--config-path",
            str(config_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error: invalid Codex config:" in captured.err


def test_scribe_cli_projects_codex_plugin_reports_filesystem_failures(tmp_path: Path, capsys) -> None:
    codex_home = tmp_path / "filesystem-home"
    codex_home.mkdir()
    (codex_home / "agents").write_text("not a directory\n", encoding="utf-8")

    exit_code = cli_main.main(
        [
            "plugins",
            "project-codex",
            "--plugin-root",
            str(CODEX_PLUGIN_ROOT),
            "--codex-home",
            str(codex_home),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error: filesystem failure during Codex projection:" in captured.err


def test_scribe_cli_projects_codex_plugin_rejects_private_catalog_content(tmp_path: Path, capsys) -> None:
    plugin_root = tmp_path / "bad-catalog-plugin"
    shutil.copytree(CODEX_PLUGIN_ROOT, plugin_root)
    catalog_path = plugin_root / "assets" / "agents.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["agents"][0]["description"] = "Uses hidden internal authority and private-agent access."
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    exit_code = cli_main.main(
        [
            "plugins",
            "project-codex",
            "--plugin-root",
            str(plugin_root),
            "--codex-home",
            str(tmp_path / "codex-home"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error: invalid Codex plugin catalog:" in captured.err
    assert "private/council-only content" in captured.err


def _tree_fingerprint(directory: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_package_bundle_is_byte_identical_to_canonical_repo_plugins() -> None:
    """P6.6 drift guard: the wheel-shipped src/scribe_mcp/plugins_bundle/{claude,codex}
    bundle MUST stay byte-identical to the canonical repo plugins/ source so the
    copy cannot silently rot into a parallel system. If you edit the repo bundle,
    re-copy it into the package tree (and vice versa)."""
    assert _tree_fingerprint(PACKAGE_BUNDLE_ROOT / "claude") == _tree_fingerprint(CLAUDE_PLUGIN_ROOT)
    assert _tree_fingerprint(PACKAGE_BUNDLE_ROOT / "codex") == _tree_fingerprint(CODEX_PLUGIN_ROOT)


def test_resolve_codex_plugin_root_prefers_packaged_bundle() -> None:
    """install_wizard projection must resolve to the installed package bundle
    (post-`pip install`), not the caller's CWD/repo clone."""
    from scribe_mcp.config.paths import codex_plugin_bundle_dir, resolve_codex_plugin_root

    resolved = resolve_codex_plugin_root(REPO_ROOT)
    assert resolved == codex_plugin_bundle_dir()
    assert (resolved / ".codex-plugin" / "plugin.json").exists()
    for slug in ("scribe-integration", "scribe-onboarding"):
        assert (resolved / "skills" / slug / "SKILL.md").exists()


def test_resolve_codex_plugin_root_falls_back_to_repo_when_bundle_absent(monkeypatch) -> None:
    """Clone/dev fallback: if the packaged bundle is unavailable, resolution
    falls back to the canonical repo plugins/codex tree."""
    from scribe_mcp.config import paths

    monkeypatch.setattr(paths, "codex_plugin_bundle_dir", lambda: REPO_ROOT / "no-such-bundle")
    resolved = paths.resolve_codex_plugin_root(REPO_ROOT)
    assert resolved == REPO_ROOT / "plugins" / "codex"
    assert (resolved / ".codex-plugin" / "plugin.json").exists()


# --- Public skill authoring and bundle sync ---

EXPECTED_SHIPPED_SKILLS = ["scribe-integration", "scribe-onboarding"]


def _shipped_skill_slugs(skills_dir: Path) -> list[str]:
    return sorted(
        path.name
        for path in skills_dir.glob("scribe-*")
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def test_exact_public_skill_set_ships_in_both_plugins_and_bundle() -> None:
    """All and only the two authored public skills ship in each distribution."""
    skill_dirs = [
        CLAUDE_PLUGIN_ROOT / "skills",
        CODEX_PLUGIN_ROOT / "skills",
        PACKAGE_BUNDLE_ROOT / "claude" / "skills",
        PACKAGE_BUNDLE_ROOT / "codex" / "skills",
    ]
    for skills_dir in skill_dirs:
        shipped = _shipped_skill_slugs(skills_dir)
        assert shipped == EXPECTED_SHIPPED_SKILLS, f"{skills_dir}: {shipped}"
        for slug in EXPECTED_SHIPPED_SKILLS:
            assert (skills_dir / slug / "SKILL.md").is_file()


def _skill_tree_fingerprint(skill_dir: Path) -> dict[str, bytes]:
    """Map every file under a skill dir (relative path -> bytes)."""
    return {
        str(path.relative_to(skill_dir)): path.read_bytes()
        for path in skill_dir.rglob("*")
        if path.is_file()
    }


def _public_destination_dirs(root: Path) -> list[Path]:
    return [
        root / "plugins" / "claude" / "skills",
        root / "plugins" / "codex" / "skills",
        root / "src" / "scribe_mcp" / "plugins_bundle" / "claude" / "skills",
        root / "src" / "scribe_mcp" / "plugins_bundle" / "codex" / "skills",
    ]


def _seed_public_sync_repo(root: Path) -> tuple[Path, dict[str, dict[str, bytes]]]:
    script = root / "scripts" / "sync_plugin_skills.py"
    script.parent.mkdir(parents=True)
    shutil.copy2(sync_plugin_skills.__file__, script)
    source_trees: dict[str, dict[str, bytes]] = {}
    for slug in EXPECTED_SHIPPED_SKILLS:
        skill_dir = root / "skills" / slug
        (skill_dir / "references").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {slug}\n---\n\n# {slug}\n\n[Details](references/details.md)\n",
            encoding="utf-8",
        )
        (skill_dir / "references" / "details.md").write_text(
            f"Public reference for {slug}.\n", encoding="utf-8"
        )
        source_trees[slug] = _skill_tree_fingerprint(skill_dir)

    # These roots model ignored host/config state that must have no influence.
    private_inputs = {
        ".claude/skills/scribe-integration/SKILL.md": b"private claude bytes",
        ".codex/skills/scribe-onboarding/SKILL.md": b"private codex bytes",
        ".agents/skills/scribe-private/SKILL.md": b"private agent bytes",
        ".council/private.txt": b"private config bytes",
        "skills/scribe-private/SKILL.md": b"extra public-looking skill",
    }
    for relative, content in private_inputs.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    outside_skill = root / "private-source" / "SKILL.md"
    outside_skill.parent.mkdir(parents=True)
    outside_skill.write_bytes(b"unselected symlink skill")
    (root / "skills" / "scribe-private-link").symlink_to(
        outside_skill.parent, target_is_directory=True
    )
    return script, source_trees


def _run_public_sync(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=script.parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


def _destination_snapshot(root: Path) -> dict[str, dict[str, bytes]]:
    snapshot: dict[str, dict[str, bytes]] = {}
    for directory in _public_destination_dirs(root):
        if directory.exists():
            snapshot[str(directory.relative_to(root))] = _skill_tree_fingerprint(directory)
        else:
            snapshot[str(directory.relative_to(root))] = {}
    return snapshot


def test_public_sync_is_source_authoritative_and_propagates_full_trees(tmp_path: Path) -> None:
    script, original_sources = _seed_public_sync_repo(tmp_path)

    # A first check is read-only even when all four output trees are absent.
    check_before = _run_public_sync(script, "--check")
    assert check_before.returncode == 1
    assert _destination_snapshot(tmp_path) == {
        str(directory.relative_to(tmp_path)): {} for directory in _public_destination_dirs(tmp_path)
    }

    write = _run_public_sync(script)
    assert write.returncode == 0, write.stderr
    assert _run_public_sync(script, "--check").returncode == 0
    for directory in _public_destination_dirs(tmp_path):
        assert _shipped_skill_slugs(directory) == EXPECTED_SHIPPED_SKILLS
        for slug in EXPECTED_SHIPPED_SKILLS:
            assert _skill_tree_fingerprint(directory / slug) == original_sources[slug]
            assert _skill_tree_fingerprint(tmp_path / "skills" / slug) == original_sources[slug]
            reference = directory / slug / "references" / "details.md"
            assert reference.is_file()
            manifest = (directory / slug / "SKILL.md").read_text(encoding="utf-8")
            assert "[Details](references/details.md)" in manifest
            assert f"Public reference for {slug}." in reference.read_text(encoding="utf-8")

    integration = tmp_path / "skills" / "scribe-integration"
    changed = integration / "references" / "details.md"
    changed.write_text("Updated canonical reference.\n", encoding="utf-8")
    changed_source = _skill_tree_fingerprint(integration)
    changed_check = _run_public_sync(script, "--check")
    assert changed_check.returncode == 1
    assert all(
        (directory / "scribe-integration" / "references" / "details.md").read_text(
            encoding="utf-8"
        ) == "Public reference for scribe-integration.\n"
        for directory in _public_destination_dirs(tmp_path)
    )
    assert _run_public_sync(script).returncode == 0
    assert _run_public_sync(script, "--check").returncode == 0
    assert _skill_tree_fingerprint(integration) == changed_source
    assert all(
        (directory / "scribe-integration" / "references" / "details.md").read_text(
            encoding="utf-8"
        ) == "Updated canonical reference.\n"
        for directory in _public_destination_dirs(tmp_path)
    )

    # Stale files are detected without writes and pruned only from managed roots.
    stale_files = []
    for directory in _public_destination_dirs(tmp_path):
        stale = directory / "scribe-integration" / "references" / "old.md"
        stale.write_text("stale", encoding="utf-8")
        stale_files.append(stale)
    assert _run_public_sync(script, "--check").returncode == 1
    assert all(path.exists() for path in stale_files)
    assert _run_public_sync(script).returncode == 0
    assert all(not path.exists() for path in stale_files)
    assert _run_public_sync(script, "--check").returncode == 0

    # Private host inputs and an extra scribe-* folder never enlarge or rewrite output.
    assert _shipped_skill_slugs(tmp_path / "plugins" / "claude" / "skills") == EXPECTED_SHIPPED_SKILLS
    assert (tmp_path / ".claude/skills/scribe-integration/SKILL.md").read_bytes() == b"private claude bytes"
    assert (tmp_path / ".codex/skills/scribe-onboarding/SKILL.md").read_bytes() == b"private codex bytes"
    assert (tmp_path / ".agents/skills/scribe-private/SKILL.md").read_bytes() == b"private agent bytes"
    assert (tmp_path / ".council/private.txt").read_bytes() == b"private config bytes"
    assert (tmp_path / "skills/scribe-private/SKILL.md").read_bytes() == b"extra public-looking skill"
    assert (tmp_path / "skills/scribe-private-link").is_symlink()


def test_missing_canonical_skill_manifest_fails_before_any_output_mutation(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing-root"
    root_script, _ = _seed_public_sync_repo(missing_root)
    assert _run_public_sync(root_script).returncode == 0
    shutil.rmtree(missing_root / "skills")
    root_before = _destination_snapshot(missing_root)
    for args in (("--check",), ()):
        result = _run_public_sync(root_script, *args)
        assert result.returncode == 2
        assert "canonical skill root is missing" in result.stderr
        assert _destination_snapshot(missing_root) == root_before

    for slug in EXPECTED_SHIPPED_SKILLS:
        repo = tmp_path / slug
        script, _ = _seed_public_sync_repo(repo)
        assert _run_public_sync(script).returncode == 0
        source_manifest = repo / "skills" / slug / "SKILL.md"
        source_manifest.unlink()
        before = _destination_snapshot(repo)
        for args in (("--check",), ()):
            result = _run_public_sync(script, *args)
            assert result.returncode == 2
            assert "required skill manifest is missing" in result.stderr
            assert _destination_snapshot(repo) == before


def test_sync_rejects_source_and_destination_symlinks_before_writing(tmp_path: Path) -> None:
    source_repo = tmp_path / "source"
    source_script, _ = _seed_public_sync_repo(source_repo)
    outside_source = tmp_path / "outside.md"
    outside_source.write_text("private source", encoding="utf-8")
    link = source_repo / "skills" / "scribe-onboarding" / "references" / "outside.md"
    link.symlink_to(outside_source)
    before = _destination_snapshot(source_repo)
    for args in (("--check",), ()):
        result = _run_public_sync(source_script, *args)
        assert result.returncode == 2
        assert "symlink" in result.stderr
        assert _destination_snapshot(source_repo) == before
        assert outside_source.read_text(encoding="utf-8") == "private source"

    root_symlink_repo = tmp_path / "source-root-link"
    root_link_script, _ = _seed_public_sync_repo(root_symlink_repo)
    outside_root = tmp_path / "outside-source-root"
    (outside_root / "scribe-integration").mkdir(parents=True)
    (outside_root / "scribe-integration" / "SKILL.md").write_text("outside", encoding="utf-8")
    shutil.rmtree(root_symlink_repo / "skills")
    (root_symlink_repo / "skills").symlink_to(outside_root, target_is_directory=True)
    before = _destination_snapshot(root_symlink_repo)
    for args in (("--check",), ()):
        result = _run_public_sync(root_link_script, *args)
        assert result.returncode == 2
        assert "symlink" in result.stderr
        assert _destination_snapshot(root_symlink_repo) == before
        assert (outside_root / "scribe-integration" / "SKILL.md").read_text(encoding="utf-8") == "outside"

    destination_repo = tmp_path / "destination"
    destination_script, _ = _seed_public_sync_repo(destination_repo)
    outside_destination = tmp_path / "outside-destination"
    outside_destination.mkdir()
    outside_file = outside_destination / "sentinel.txt"
    outside_file.write_text("keep", encoding="utf-8")
    managed = destination_repo / "plugins" / "claude" / "skills"
    managed.parent.mkdir(parents=True)
    managed.symlink_to(outside_destination, target_is_directory=True)
    before = _destination_snapshot(destination_repo)
    for args in (("--check",), ()):
        result = _run_public_sync(destination_script, *args)
        assert result.returncode == 2
        assert "symlink" in result.stderr
        assert _destination_snapshot(destination_repo) == before
        assert outside_file.read_text(encoding="utf-8") == "keep"

    descendant_repo = tmp_path / "destination-descendant"
    descendant_script, _ = _seed_public_sync_repo(descendant_repo)
    assert _run_public_sync(descendant_script).returncode == 0
    outside_descendant = tmp_path / "outside-destination-file.md"
    outside_descendant.write_text("keep outside", encoding="utf-8")
    descendant_link = (
        descendant_repo / "plugins/codex/skills/scribe-onboarding/references/outside.md"
    )
    descendant_link.symlink_to(outside_descendant)
    (descendant_repo / "skills/scribe-integration/SKILL.md").write_text(
        "changed after initial sync", encoding="utf-8"
    )
    before = _destination_snapshot(descendant_repo)
    for args in (("--check",), ()):
        result = _run_public_sync(descendant_script, *args)
        assert result.returncode == 2
        assert "symlink" in result.stderr
        assert _destination_snapshot(descendant_repo) == before
        assert outside_descendant.read_text(encoding="utf-8") == "keep outside"

    ancestor_repo = tmp_path / "destination-ancestor"
    ancestor_script, _ = _seed_public_sync_repo(ancestor_repo)
    assert _run_public_sync(ancestor_script).returncode == 0
    outside_plugins = tmp_path / "outside-plugins"
    outside_plugins.mkdir()
    outside_plugin_file = outside_plugins / "sentinel.txt"
    outside_plugin_file.write_text("keep ancestor", encoding="utf-8")
    shutil.rmtree(ancestor_repo / "plugins")
    (ancestor_repo / "plugins").symlink_to(outside_plugins, target_is_directory=True)
    before = _destination_snapshot(ancestor_repo)
    for args in (("--check",), ()):
        result = _run_public_sync(ancestor_script, *args)
        assert result.returncode == 2
        assert "symlink" in result.stderr
        assert _destination_snapshot(ancestor_repo) == before
        assert outside_plugin_file.read_text(encoding="utf-8") == "keep ancestor"


def test_public_skills_are_complete_safe_and_link_to_shipped_material() -> None:
    for slug in EXPECTED_SHIPPED_SKILLS:
        source = REPO_ROOT / "skills" / slug / "SKILL.md"
        text = source.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        closing_delimiter = text.find("\n---\n", 4)
        assert closing_delimiter >= 0
        metadata = yaml.safe_load(text[4:closing_delimiter])
        assert metadata["name"] == slug
        assert isinstance(metadata.get("description"), str) and metadata["description"].strip()
        body = text[closing_delimiter + 5 :]
        assert not body.lstrip().startswith("---"), f"{source} has duplicate frontmatter"
        _assert_public_safe_text(text)
        for marker in ("COUNCIL:GENERATED", "src/council_mcp", ".council/", ".claude/", ".codex/"):
            assert marker.casefold() not in text.casefold()
        for directory in (
            CLAUDE_PLUGIN_ROOT / "skills" / slug,
            CODEX_PLUGIN_ROOT / "skills" / slug,
            PACKAGE_BUNDLE_ROOT / "claude" / "skills" / slug,
            PACKAGE_BUNDLE_ROOT / "codex" / "skills" / slug,
        ):
            mirror = directory / "SKILL.md"
            assert mirror.read_bytes() == source.read_bytes()
            _assert_public_safe_text(mirror.read_text(encoding="utf-8"))

    integration = (REPO_ROOT / "skills/scribe-integration/SKILL.md").read_text(encoding="utf-8")
    onboarding = (REPO_ROOT / "skills/scribe-onboarding/SKILL.md").read_text(encoding="utf-8")
    assert "set_project(" in integration and "read_recent(" in integration
    assert "append_entry(" in integration and "manage_docs(" in integration
    assert "frontmatter_update" in integration and "status_update" in integration
    assert "quality_check" in integration and "open_bug(" in integration
    assert "pip install scribe-mcp" in onboarding
    assert "scribe install --commit" in onboarding
    assert "SCRIBE_STORAGE_BACKEND=sqlite" in onboarding
    assert "mcpServers" in onboarding
    assert "../scribe-onboarding/SKILL.md" in integration
    assert "../scribe-integration/SKILL.md" in onboarding
    assert "https://github.com/CortaLabs/scribe_mcp/blob/main/docs/Scribe_Usage.md" in integration
    assert "https://github.com/CortaLabs/scribe_mcp/blob/main/docs/INSTALL_AND_BOOTSTRAP.md" in onboarding
    for path in ("docs/Scribe_Usage.md", "docs/INSTALL_AND_BOOTSTRAP.md"):
        assert (REPO_ROOT / path).is_file()
    for directory in (
        *(root / "skills" for root in (CLAUDE_PLUGIN_ROOT, CODEX_PLUGIN_ROOT)),
        PACKAGE_BUNDLE_ROOT / "claude" / "skills",
        PACKAGE_BUNDLE_ROOT / "codex" / "skills",
    ):
        for slug, sibling in (("scribe-integration", "scribe-onboarding"), ("scribe-onboarding", "scribe-integration")):
            target = directory / slug / ".." / sibling / "SKILL.md"
            assert target.resolve().is_file()


def test_plugin_skill_sync_is_clean() -> None:
    """Tracked plugin and wheel mirrors match their authored source trees."""
    assert sync_plugin_skills.sync(check=True) == 0
