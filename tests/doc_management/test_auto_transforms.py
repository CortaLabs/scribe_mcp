"""Tests for auto-transform hook (opt-in via frontmatter)."""

import pytest
from pathlib import Path
from doc_management.manager import apply_doc_change


@pytest.mark.asyncio
async def test_auto_normalize_headers_enabled(tmp_path):
    """Test that auto_normalize_headers flag triggers header normalization."""
    # Create test project with doc
    project = {
        "name": "test_auto_transforms",
        "root": str(tmp_path),
        "docs": {
            "test_doc": str(tmp_path / "test_doc.md")
        }
    }

    # Create initial document with auto_normalize_headers enabled and bad headers
    doc_path = tmp_path / "test_doc.md"
    initial_content = """---
auto_normalize_headers: true
---

# Bad Header Without Space
## Another  Bad   Header

Content here.
"""
    doc_path.write_text(initial_content)

    # Make a simple edit (not a normalize action)
    result = await apply_doc_change(
        project=project,
        doc_name="test_doc",
        action="replace_section",
        section=None,
        content="New content",
        template=None,
        metadata={"allow_append": True},
        dry_run=False
    )

    # Verify transform was applied
    assert result.success
    assert "auto_transforms_applied" in result.extra
    assert "normalize_headers" in result.extra["auto_transforms_applied"]

    # Verify headers were actually normalized in the file
    # normalize_headers adds numbering: "# 1 Bad Header", "## 1.1 Another"
    final_content = doc_path.read_text()
    assert "# 1 Bad Header Without Space" in final_content
    assert "## 1.1 Another" in final_content


@pytest.mark.asyncio
async def test_auto_generate_toc_enabled(tmp_path):
    """Test that auto_generate_toc flag triggers TOC generation."""
    # Create test project with doc
    project = {
        "name": "test_auto_transforms",
        "root": str(tmp_path),
        "docs": {
            "test_doc": str(tmp_path / "test_doc.md")
        }
    }

    # Create initial document with auto_generate_toc enabled
    doc_path = tmp_path / "test_doc.md"
    initial_content = """---
auto_generate_toc: true
---

# Introduction

Some intro text.

## Section A

Content A.

## Section B

Content B.
"""
    doc_path.write_text(initial_content)

    # Make a simple edit (not a toc action)
    result = await apply_doc_change(
        project=project,
        doc_name="test_doc",
        action="replace_section",
        section=None,
        content="Updated content",
        template=None,
        metadata={"allow_append": True},
        dry_run=False
    )

    # Verify transform was applied
    assert result.success
    assert "auto_transforms_applied" in result.extra
    assert "generate_toc" in result.extra["auto_transforms_applied"]

    # Verify TOC was generated in the file
    # generate_toc uses HTML comments: <!-- TOC:start -->
    final_content = doc_path.read_text()
    assert "<!-- TOC:start -->" in final_content
    assert "<!-- TOC:end -->" in final_content


@pytest.mark.asyncio
async def test_no_auto_transforms_without_flags(tmp_path):
    """Test that documents without flags do NOT get auto-transformed."""
    # Create test project with doc
    project = {
        "name": "test_auto_transforms",
        "root": str(tmp_path),
        "docs": {
            "test_doc": str(tmp_path / "test_doc.md")
        }
    }

    # Create initial document WITHOUT auto-transform flags
    doc_path = tmp_path / "test_doc.md"
    initial_content = """---
title: Test Doc
---

#Bad Header Without Space

Content here.
"""
    doc_path.write_text(initial_content)

    # Make a simple edit
    result = await apply_doc_change(
        project=project,
        doc_name="test_doc",
        action="replace_section",
        section=None,
        content="New content",
        template=None,
        metadata={"allow_append": True},
        dry_run=False
    )

    # Verify NO transforms were applied
    assert result.success
    assert "auto_transforms_applied" not in result.extra or not result.extra.get("auto_transforms_applied")

    # Verify header was NOT normalized (still bad)
    final_content = doc_path.read_text()
    assert "#Bad Header Without Space" in final_content


@pytest.mark.asyncio
async def test_both_auto_transforms_enabled(tmp_path):
    """Test that both auto_normalize and auto_toc work together."""
    # Create test project with doc
    project = {
        "name": "test_auto_transforms",
        "root": str(tmp_path),
        "docs": {
            "test_doc": str(tmp_path / "test_doc.md")
        }
    }

    # Create initial document with BOTH flags enabled
    doc_path = tmp_path / "test_doc.md"
    initial_content = """---
auto_normalize_headers: true
auto_generate_toc: true
---

# Bad Header

## Another Bad Header

Content here.
"""
    doc_path.write_text(initial_content)

    # Make a simple edit
    result = await apply_doc_change(
        project=project,
        doc_name="test_doc",
        action="replace_section",
        section=None,
        content="New content",
        template=None,
        metadata={"allow_append": True},
        dry_run=False
    )

    # Verify BOTH transforms were applied
    assert result.success
    assert "auto_transforms_applied" in result.extra
    assert "normalize_headers" in result.extra["auto_transforms_applied"]
    assert "generate_toc" in result.extra["auto_transforms_applied"]

    # Verify both transforms worked
    final_content = doc_path.read_text()
    assert "# 1 Bad Header" in final_content  # normalized with numbering
    assert "## 1.1 Another Bad Header" in final_content  # normalized with numbering
    assert "<!-- TOC:start -->" in final_content  # TOC added


@pytest.mark.asyncio
async def test_auto_transforms_skip_normalize_action(tmp_path):
    """Test that auto-transforms are NOT applied during normalize_headers action."""
    # Create test project with doc
    project = {
        "name": "test_auto_transforms",
        "root": str(tmp_path),
        "docs": {
            "test_doc": str(tmp_path / "test_doc.md")
        }
    }

    # Create initial document with auto_normalize_headers enabled
    doc_path = tmp_path / "test_doc.md"
    initial_content = """---
auto_normalize_headers: true
---

# Bad Header

Content here.
"""
    doc_path.write_text(initial_content)

    # Explicitly call normalize_headers action
    result = await apply_doc_change(
        project=project,
        doc_name="test_doc",
        action="normalize_headers",
        section=None,
        content=None,
        template=None,
        metadata=None,
        dry_run=False
    )

    # Verify auto-transform was NOT applied (avoided double-normalization)
    assert result.success
    assert "auto_transforms_applied" not in result.extra or "normalize_headers" not in result.extra.get("auto_transforms_applied", [])
