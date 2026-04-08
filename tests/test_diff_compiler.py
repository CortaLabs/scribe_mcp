from __future__ import annotations

from scribe_mcp.doc_management.manager import _apply_unified_patch
from scribe_mcp.utils.diff_compiler import compile_unified_diff


def test_compile_unified_diff_applies_cleanly() -> None:
    before = "alpha\nbeta\n"
    after = "alpha\nbeta updated\n"
    patch_text = compile_unified_diff(before, after, fromfile="before", tofile="after")

    assert "--- before" in patch_text
    assert "+++ after" in patch_text
    assert "@@ " in patch_text

    updated, hunks_applied = _apply_unified_patch(before, patch_text)
    assert hunks_applied >= 1
    assert updated == after
