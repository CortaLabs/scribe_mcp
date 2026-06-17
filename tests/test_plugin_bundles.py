from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

from scribe_mcp.cli import main as cli_main
from scribe_mcp.scripts.project_codex_plugin import project_codex_plugin


REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_PLUGIN_ROOT = REPO_ROOT / "plugins" / "claude"
CODEX_PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex"
MARKETPLACE_PATH = CODEX_PLUGIN_ROOT / "marketplace.json"
PACKAGE_BUNDLE_ROOT = REPO_ROOT / "src" / "scribe_mcp" / "plugins_bundle"
PACKAGE_ONBOARDING_SKILL = (
    REPO_ROOT / "src" / "scribe_mcp" / "onboarding" / "skills" / "scribe-mcp-usage" / "SKILL.md"
)
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


def test_claude_bundle_keeps_manifest_only_directory_shape_and_public_assets() -> None:
    assert _only_manifest(CLAUDE_PLUGIN_ROOT / ".claude-plugin") == ["plugin.json"]
    assert _agent_slugs(CLAUDE_PLUGIN_ROOT / "agents", ".md") == ALLOWED_PUBLIC_AGENTS

    manifest = json.loads((CLAUDE_PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "scribe-mcp"
    assert manifest["agents"] == "./agents/"
    assert manifest["skills"] == "./skills/"
    assert manifest["hooks"] == "./hooks/hooks.json"
    assert manifest["mcpServers"] == "./.mcp.json"

    mcp_config = json.loads((CLAUDE_PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp_config["mcpServers"]["scribe"]["command"] == "scribe-server"

    hooks_config = json.loads((CLAUDE_PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert list(hooks_config) == ["hooks"]
    hook_command = hooks_config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert hook_command == "${CLAUDE_PLUGIN_ROOT}/bin/protect-managed-docs.sh"

    assert (CLAUDE_PLUGIN_ROOT / "skills" / "scribe-mcp-usage" / "SKILL.md").exists()
    _assert_public_safe_markdown_dir(CLAUDE_PLUGIN_ROOT / "agents")


def test_codex_bundle_and_marketplace_keep_root_layout_and_allowlist_only() -> None:
    assert _only_manifest(CODEX_PLUGIN_ROOT / ".codex-plugin") == ["plugin.json"]
    assert _agent_slugs(CODEX_PLUGIN_ROOT / "agents", ".toml") == ALLOWED_PUBLIC_AGENTS
    assert _agent_slugs(CODEX_PLUGIN_ROOT / "assets" / "agents", ".md") == ALLOWED_PUBLIC_AGENTS

    manifest = json.loads((CODEX_PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "scribe-mcp"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert "apps" not in manifest
    assert "council" not in manifest["description"].lower()
    assert "council" not in manifest["interface"]["longDescription"].lower()

    app_config = json.loads((CODEX_PLUGIN_ROOT / ".app.json").read_text(encoding="utf-8"))
    assert app_config == {"apps": {}}

    mcp_config = json.loads((CODEX_PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp_config["mcpServers"]["scribe"]["command"] == "scribe-server"

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
    skill_dir = codex_home / "skills" / "scribe-mcp-usage"
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


def test_packaged_onboarding_skill_matches_bundle_usage_skill() -> None:
    """The standalone packaged onboarding skill is the canonical usage SKILL.md."""
    canonical = (CLAUDE_PLUGIN_ROOT / "skills" / "scribe-mcp-usage" / "SKILL.md").read_bytes()
    assert PACKAGE_ONBOARDING_SKILL.read_bytes() == canonical


def test_resolve_codex_plugin_root_prefers_packaged_bundle() -> None:
    """install_wizard projection must resolve to the installed package bundle
    (post-`pip install`), not the caller's CWD/repo clone."""
    from scribe_mcp.config.paths import codex_plugin_bundle_dir, resolve_codex_plugin_root

    resolved = resolve_codex_plugin_root(REPO_ROOT)
    assert resolved == codex_plugin_bundle_dir()
    assert (resolved / ".codex-plugin" / "plugin.json").exists()
    assert (resolved / "skills" / "scribe-mcp-usage" / "SKILL.md").exists()


def test_resolve_codex_plugin_root_falls_back_to_repo_when_bundle_absent(monkeypatch) -> None:
    """Clone/dev fallback: if the packaged bundle is unavailable, resolution
    falls back to the canonical repo plugins/codex tree."""
    from scribe_mcp.config import paths

    monkeypatch.setattr(paths, "codex_plugin_bundle_dir", lambda: REPO_ROOT / "no-such-bundle")
    resolved = paths.resolve_codex_plugin_root(REPO_ROOT)
    assert resolved == REPO_ROOT / "plugins" / "codex"
    assert (resolved / ".codex-plugin" / "plugin.json").exists()


def test_roster_review_agent_uses_registered_slug_for_scribe_sign_in() -> None:
    roster_text = (REPO_ROOT / ".council" / "roster.yaml").read_text(encoding="utf-8")
    assert "You sign into Scribe as `scribe-review-agent`" in roster_text
    assert "You sign into Scribe as `ReviewAgent`" not in roster_text
