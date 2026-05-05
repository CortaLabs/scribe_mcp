from pathlib import Path

from scribe_mcp.doc_management.scaffold_quality import analyze_scaffold_quality, collect_managed_doc_quality_warnings


def _codes(warnings):
    return {w["code"] for w in warnings}


def test_scaffold_quality_emits_authoritative_codes_and_payload_shape():
    text = """---
status: complete
---
# Findings
| finding |
| |

[fill this section]
## Appendix
TODO: add references
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="ARCHITECTURE_GUIDE")
    codes = _codes(warnings)
    assert "SCF_PLACEHOLDER_BRACKET" in codes
    assert "SCF_EMPTY_FINDING" in codes
    assert "SCF_UNFILLED_APPENDIX" in codes
    assert "SCF_TODO_ONLY_SECTION" in codes
    assert "SCF_FRONTMATTER_MISMATCH" in codes
    sample = warnings[0]
    for key in ("code", "severity", "blocking", "location", "message", "suggested_repair"):
        assert key in sample


def test_scaffold_quality_suppresses_quoted_and_codefence_examples():
    text = """---
status: in_progress
---
> [example placeholder]
```md
[example in code fence]
```
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="SPEC")
    assert "SCF_PLACEHOLDER_BRACKET" not in _codes(warnings)


def test_nonblocking_code_catalog_defaults_present():
    from scribe_mcp.doc_management.scaffold_quality import DEFAULT_WARNING_POLICIES
    for code in ["SCF_INDEX_STALE", "SCF_INDEX_MISSING", "SCF_DOC_UNINDEXED", "SCF_NONCANONICAL_LOCATION"]:
        assert code in DEFAULT_WARNING_POLICIES
        assert DEFAULT_WARNING_POLICIES[code]["blocking"] is False


def test_template_prose_scaffold_phrase_triggers():
    text = """---
status: in_progress
---
Please replace this with implementation-specific evidence.
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="PHASE_PLAN")
    assert "SCF_TEMPLATE_PROSE" in _codes(warnings)


def test_log_template_only_triggers_for_ready_log_shell():
    text = """---
status: complete
---
# Progress Log
## Entries
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="PROGRESS_LOG")
    assert "SCF_LOG_TEMPLATE_ONLY" in _codes(warnings)


def test_proof_and_out_of_scope_labels_are_not_template_prose():
    text = """---
status: in_progress
---
Proof: command output attached below.
Out of Scope: reminder scheduler and quality_check action.
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="CHECKLIST")
    assert "SCF_TEMPLATE_PROSE" not in _codes(warnings)


def test_todo_readiness_behavior():
    in_progress_text = """---
status: in_progress
---
TODO: flesh this section out later.
"""
    ready_text = """---
status: complete
---
TODO: flesh this section out later.
"""
    in_progress_warnings = analyze_scaffold_quality(text=in_progress_text, doc_name="SPEC")
    ready_warnings = analyze_scaffold_quality(text=ready_text, doc_name="SPEC")
    assert "SCF_TODO_ONLY_SECTION" not in _codes(in_progress_warnings)
    assert "SCF_TODO_ONLY_SECTION" in _codes(ready_warnings)


def test_anchor_comments_and_headings_do_not_trigger_placeholder():
    text = """---
status: in_progress
---
<!-- id: p2-scaffold-analyzer -->
# [Title Placeholder]
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="CHECKLIST")
    assert "SCF_PLACEHOLDER_BRACKET" not in _codes(warnings)


def test_authored_markdown_literals_do_not_trigger_placeholder_brackets():
    text = """---
status: in_progress
---
- [x] Completed quality gate
[Package 2.1 plan](./PHASE_PLAN.md)
[✅] [2026-05-05 02:23:44 UTC] [Agent: Forge] [Project: X] Completed analyzer refactor
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="CHECKLIST")
    assert "SCF_PLACEHOLDER_BRACKET" not in _codes(warnings)


def test_authored_placeholders_still_trigger_blocking_warning():
    text = """---
status: in_progress
---
Please review [fill this section] before final approval.
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="CHECKLIST")
    codes = _codes(warnings)
    assert "SCF_PLACEHOLDER_BRACKET" in codes
    placeholder = next(w for w in warnings if w["code"] == "SCF_PLACEHOLDER_BRACKET")
    assert placeholder["blocking"] is True


def test_mixed_markdown_link_and_placeholder_still_warns_for_placeholder():
    text = """---
status: in_progress
---
See [Spec](./SPEC.md) and then [fill this section].
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="CHECKLIST")
    codes = _codes(warnings)
    assert "SCF_PLACEHOLDER_BRACKET" in codes
    placeholder_warning = next(w for w in warnings if w["code"] == "SCF_PLACEHOLDER_BRACKET")
    assert placeholder_warning["excerpt"] == "See [Spec](./SPEC.md) and then [fill this section]."


def test_ready_status_with_bracket_placeholder_emits_mismatch_and_placeholder():
    text = """---
status: complete
---
[fill this section]
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="ARCHITECTURE_GUIDE")
    codes = _codes(warnings)
    assert "SCF_PLACEHOLDER_BRACKET" in codes
    assert "SCF_FRONTMATTER_MISMATCH" in codes


def test_bullet_bracket_placeholder_is_not_suppressed_as_checklist_marker():
    text = """---
status: in_progress
---
- [fill this section]
"""
    warnings = analyze_scaffold_quality(text=text, doc_name="CHECKLIST")
    assert "SCF_PLACEHOLDER_BRACKET" in _codes(warnings)


def test_noncanonical_warning_for_nested_research_path_is_actionable(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    research_dir = docs_dir / "research"
    nested = research_dir / "wave_1"
    nested.mkdir(parents=True)
    (research_dir / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    changed = nested / "RESEARCH_NOTE.md"
    changed.write_text("# Note\n", encoding="utf-8")

    warnings = collect_managed_doc_quality_warnings(
        text=changed.read_text(encoding="utf-8"),
        doc_name="RESEARCH_NOTE",
        path=changed,
        project={"docs_dir": str(docs_dir)},
    )
    noncanonical = [w for w in warnings if w.get("code") == "SCF_NONCANONICAL_LOCATION"]
    assert noncanonical
    assert "not in canonical flat research placement" in str(noncanonical[0].get("message"))
