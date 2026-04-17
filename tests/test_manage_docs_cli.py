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
