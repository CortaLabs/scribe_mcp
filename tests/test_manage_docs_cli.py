import sys

from scribe_mcp.doc_management.cli import run_manage_docs_cli


def test_preview_reconciliation_does_not_require_content_or_template(monkeypatch) -> None:
    async def _manage_docs_callable(**kwargs):
        assert kwargs["action"] == "preview_reconciliation"
        assert kwargs["doc"] == "checklist"
        return {"ok": True, "message": "preview ok"}

    monkeypatch.setattr(
        sys,
        "argv",
        ["manage_docs", "preview_reconciliation", "checklist"],
    )

    exit_code = run_manage_docs_cli(_manage_docs_callable)
    assert exit_code == 0


def test_frontmatter_update_does_not_require_content_or_template(monkeypatch) -> None:
    async def _manage_docs_callable(**kwargs):
        assert kwargs["action"] == "frontmatter_update"
        assert kwargs["doc"] == "architecture"
        assert kwargs["metadata"] == {"frontmatter": {"status": "ready"}}
        return {"ok": True, "message": "frontmatter ok"}

    monkeypatch.setattr(
        sys,
        "argv",
        ["manage_docs", "frontmatter_update", "architecture", "--metadata", '{"frontmatter":{"status":"ready"}}'],
    )

    exit_code = run_manage_docs_cli(_manage_docs_callable)
    assert exit_code == 0


def test_quality_check_accepts_custom_doc_name_without_content(monkeypatch) -> None:
    async def _manage_docs_callable(**kwargs):
        assert kwargs["action"] == "quality_check"
        assert kwargs["doc"] == "research_frontmatter"
        return {"ok": True, "message": "quality ok"}

    monkeypatch.setattr(sys, "argv", ["manage_docs", "quality_check", "research_frontmatter"])

    exit_code = run_manage_docs_cli(_manage_docs_callable)
    assert exit_code == 0


def test_apply_patch_cli_allows_patch_without_patch_mode(monkeypatch) -> None:
    async def _manage_docs_callable(**kwargs):
        assert kwargs["action"] == "apply_patch"
        assert kwargs["doc"] == "architecture"
        assert kwargs["patch"] == "--- before\n+++ after\n"
        assert kwargs["patch_mode"] is None
        return {"ok": True, "message": "patch ok"}

    monkeypatch.setattr(
        sys,
        "argv",
        ["manage_docs", "apply_patch", "architecture", "--patch", "--- before\n+++ after\n"],
    )

    exit_code = run_manage_docs_cli(_manage_docs_callable)
    assert exit_code == 0


def test_apply_patch_cli_dispatches_codex_patch_input(monkeypatch) -> None:
    codex_patch = "*** Begin Patch\n*** Update File: ARCHITECTURE_GUIDE.md\n*** End Patch"

    async def _manage_docs_callable(**kwargs):
        assert kwargs["action"] == "apply_patch"
        assert kwargs["doc"] == "architecture"
        assert kwargs["patch"] == codex_patch
        assert kwargs["patch_mode"] is None
        return {"ok": True, "message": "codex patch ok"}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "manage_docs",
            "apply_patch",
            "architecture",
            "--patch",
            codex_patch,
        ],
    )

    exit_code = run_manage_docs_cli(_manage_docs_callable)

    assert exit_code == 0
