import pytest

from scribe_mcp.tools import set_project as set_project_tool


@pytest.mark.asyncio
async def test_ensure_documents_creates_changelog(tmp_path) -> None:
    docs_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "sample"
    docs_dir.mkdir(parents=True)
    result = await set_project_tool._ensure_documents(
        name="sample",
        author="tester",
        overwrite=False,
        root_path=tmp_path,
        docs_dir=docs_dir,
        agent_id="test-agent",
    )
    assert result["ok"] is True
    changelog_path = docs_dir / "CHANGELOG.md"
    assert changelog_path.exists()
    text = changelog_path.read_text(encoding="utf-8")
    assert "entry_id" in text
    assert "\n" in text
    assert "\\n" not in text
