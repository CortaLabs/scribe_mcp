from __future__ import annotations

from pathlib import Path

from scribe_mcp.cli import main as cli_main
from scribe_mcp.template_engine import Jinja2TemplateEngine


def test_builtin_architecture_template_passes_render_check() -> None:
    engine = Jinja2TemplateEngine(project_root=Path("/tmp"), project_name="template-probe")

    validation = engine.validate_template(
        "documents/ARCHITECTURE_GUIDE_TEMPLATE.md",
        render_check=True,
    )

    assert validation["valid"], validation
    assert validation["syntax_valid"] is True
    assert validation["render_valid"] is True


def test_validate_template_render_check_catches_runtime_undefined(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    template_dir = repo_root / ".scribe" / "templates" / "documents"
    template_dir.mkdir(parents=True)
    (template_dir / "BROKEN_TEMPLATE.md").write_text(
        "{% set item = metadata.missing.value %}\n# Broken\n",
        encoding="utf-8",
    )

    engine = Jinja2TemplateEngine(project_root=repo_root, project_name="template-probe")

    syntax_only = engine.validate_template("documents/BROKEN_TEMPLATE.md")
    render_checked = engine.validate_template(
        "documents/BROKEN_TEMPLATE.md",
        render_check=True,
    )

    assert syntax_only["valid"] is True
    assert syntax_only["syntax_valid"] is True
    assert syntax_only["render_valid"] is None

    assert render_checked["valid"] is False
    assert render_checked["syntax_valid"] is True
    assert render_checked["render_valid"] is False
    assert any("Render error:" in error for error in render_checked["errors"])


def test_scribe_templates_validate_returns_failure_for_render_error(
    tmp_path: Path,
    capsys,
) -> None:
    repo_root = tmp_path / "repo"
    template_dir = repo_root / ".scribe" / "templates" / "documents"
    template_dir.mkdir(parents=True)
    (template_dir / "BROKEN_TEMPLATE.md").write_text(
        "{% set item = metadata.missing.value %}\n# Broken\n",
        encoding="utf-8",
    )

    exit_code = cli_main.main(
        [
            "templates",
            "validate",
            "--repo-root",
            str(repo_root),
            "--template",
            "documents/BROKEN_TEMPLATE.md",
            "--render-check",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Render error:" in captured.out
    assert "documents/BROKEN_TEMPLATE.md" in captured.out
