from scribe_mcp.doc_management import runtime


def test_frontmatter_update_is_primary_routed_and_write_intent() -> None:
    manifest = runtime.build_manage_docs_action_manifest()
    assert "frontmatter_update" in manifest["primary_actions"]
    assert runtime.ACTION_ROUTER.get("frontmatter_update") == "edit"
    assert runtime._is_manage_docs_write_intent("frontmatter_update") is True
