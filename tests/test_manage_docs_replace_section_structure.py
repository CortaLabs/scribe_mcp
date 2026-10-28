from __future__ import annotations

import json
from pathlib import Path

import pytest

from scribe_mcp.doc_management.actions.query import inspect_document_sections_from_text
from scribe_mcp.doc_management.errors import document_anchor_ids
from scribe_mcp.doc_management.manager import _replace_section
from scribe_mcp.doc_management.manager import (
    AnchorCASDenied,
    DocumentOperationError,
    _append_block,
    _extract_section_body,
    _managed_anchor_snapshot,
    _replace_text_with_scope,
    apply_doc_change,
)
from scribe_mcp.doc_management.runtime import build_create_intent_payload
from scribe_mcp.template_engine import Jinja2TemplateEngine


@pytest.mark.regression
@pytest.mark.parametrize("separator", ["\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("fallback", [False, True])
def test_unicode_separators_are_literal_with_ascii_scope_lines(
    separator: str, newline: str, fallback: bool,
) -> None:
    from scribe_mcp.doc_management.quality.scopes import (
        HeuristicFenceScopeProvider, MarkdownItScopeProvider,
    )

    provider = HeuristicFenceScopeProvider() if fallback else MarkdownItScopeProvider()
    prefix = f"Prose{separator}continues{newline}"
    payload = f"```text{newline}alpha{separator}```{newline}<!-- ID: fake -->{newline}```{newline}"
    neighbor = f"<!-- ID: real -->{newline}"
    body = prefix + payload + neighbor
    scopes = [scope for scope in provider.collect_scopes(body) if scope.kind == "fenced_code"]
    assert len(scopes) == 1
    scope = scopes[0]
    assert scope.start_line == 2 and scope.end_line == 5
    assert scope.start_offset == len(prefix)
    assert scope.contains_offset(body.index("<!-- ID: fake -->"))
    assert not scope.contains_offset(body.index("<!-- ID: real -->"))


@pytest.mark.regression
@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\x85", "\v", "\f", "\x1c", "\x1d", "\x1e"])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("closed", [False, True])
def test_normalizer_preserves_literal_separators_and_prose_policy(
    separator: str, newline: str, closed: bool,
) -> None:
    from scribe_mcp.doc_management.utils import strip_trailing_whitespace_lines

    payload = f"```text{newline}alpha{separator}beta  \t{newline}"
    if closed:
        payload += f"```{newline}"
    original = f"prose{separator}continues  \t{newline}" + payload
    # The existing normalizer converts ASCII CR/CRLF to LF, including fences.
    expected = f"prose{separator}continues\n" + payload.replace(newline, "\n")
    assert strip_trailing_whitespace_lines(original).encode("utf-8") == expected.encode("utf-8")


def _count_marker(text: str, section_id: str) -> int:
    return text.count(f"<!-- ID: {section_id} -->")


@pytest.mark.regression
@pytest.mark.parametrize("fallback", [False, True], ids=["canonical", "heuristic"])
@pytest.mark.parametrize("operation", ["extract", "snapshot", "append", "replace", "preserve", "scoped"])
def test_section_helpers_collect_real_scopes_once_per_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fallback: bool, operation: str,
) -> None:
    from scribe_mcp.doc_management import errors
    from scribe_mcp.doc_management.quality.scopes import HeuristicFenceScopeProvider

    provider = HeuristicFenceScopeProvider() if fallback else errors.create_scope_provider()
    collected: list[str] = []

    class CountingProvider:
        def collect_scopes(self, text: str):
            collected.append(text)
            return provider.collect_scopes(text)

    monkeypatch.setattr(errors, "create_scope_provider", CountingProvider)
    original, _, neighbor = _fenced_document("````", duplicate_target=True)
    path = tmp_path / "DOC.md"

    # Each call owns its offsets. A later changed input must collect fresh scopes;
    # another call on the original must also avoid a persistent/global cache.
    for doc in (original, original.replace("keep exactly", "changed bytes"), original):
        collected.clear()
        if operation == "extract":
            result = _extract_section_body(doc, "verification")
            assert result == doc.split("<!-- ID: verification -->\n", 1)[1][:-len(neighbor)]
        elif operation == "snapshot":
            result = _managed_anchor_snapshot(doc, "verification", path)
            assert result["anchor_id"] == "verification"
            assert len(result["anchor_sha256"]) == 64
        elif operation == "append":
            result = _append_block(doc, "new evidence", "verification")
            assert result == doc[:-len(neighbor)].rstrip() + "\nnew evidence\n" + neighbor
        elif operation in {"replace", "preserve"}:
            result = _replace_section(doc, "verification", "new evidence", preserve_authored=operation == "preserve")
            body = doc.split("<!-- ID: verification -->\n", 1)[1][:-len(neighbor)]
            expected_body = body.rstrip() + "\n\nnew evidence" if operation == "preserve" else "new evidence"
            assert result == "## Verification\n<!-- ID: verification -->\n" + expected_body + "\n" + neighbor
        else:
            result, hits = _replace_text_with_scope(
                doc, find_text='"text"', replace_text='"renamed"',
                match_mode="literal", replace_all=True, scope="section:verification", allow_no_match=True,
            )
            assert hits == 1 and result == doc.replace('"text"', '"renamed"')
        assert collected == [doc], f"{operation}: full scope collections={len(collected)}"


def test_replace_section_preserves_adjacent_heading_and_anchor_on_repeated_updates() -> None:
    doc = (
        "# Phase Plan\n\n"
        "## Phase 0 — Initial\n"
        "<!-- ID: phase_0 -->\n"
        "old phase 0\n\n"
        "## Phase 1 — Neighbor\n"
        "<!-- ID: phase_1 -->\n"
        "old phase 1\n"
    )

    first = _replace_section(doc, "phase_0", "updated phase 0")
    assert "## Phase 1 — Neighbor" in first
    assert _count_marker(first, "phase_1") == 1

    second = _replace_section(
        first,
        "phase_0",
        "## Phase 0 — Revised\n<!-- ID: phase_0 -->\nrevised phase 0",
    )

    assert "## Phase 0 — Initial" not in second
    assert "## Phase 0 — Revised" in second
    assert "## Phase 1 — Neighbor" in second
    assert _count_marker(second, "phase_0") == 1
    assert _count_marker(second, "phase_1") == 1


def test_replace_section_keeps_phase_and_checklist_scaffolds_structurally_coherent() -> None:
    engine = Jinja2TemplateEngine(project_root=".", project_name="replace_section_structure")

    phase_plan = engine.render_template(
        "documents/PHASE_PLAN_TEMPLATE.md",
        metadata={"summary": "phase scaffold", "phases": [], "milestones": []},
    )
    checklist = engine.render_template(
        "documents/CHECKLIST_TEMPLATE.md",
        metadata={"summary": "checklist scaffold", "sections": []},
    )

    phase_plan = _replace_section(
        phase_plan,
        "phase_0",
        "## Phase 0 — Bounded Slice\n<!-- ID: phase_0 -->\n- [ ] package 2.3 proof",
    )
    phase_plan = _replace_section(phase_plan, "phase_1", "follow-up package details")
    phase_plan = _replace_section(phase_plan, "phase_0", "tightened phase 0 body")

    checklist = _replace_section(
        checklist,
        "phase_0",
        "## Phase 0\n<!-- ID: phase_0 -->\n- [x] proof attached",
    )
    checklist = _replace_section(checklist, "phase_1", "- [ ] next validation")
    checklist = _replace_section(checklist, "phase_0", "- [x] stability regression added")

    for doc_text in (phase_plan, checklist):
        lines = doc_text.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("<!-- ID:"):
                continue
            previous_non_blank = ""
            for back_index in range(index - 1, -1, -1):
                candidate = lines[back_index].strip()
                if candidate:
                    previous_non_blank = candidate
                    break
            assert previous_non_blank.startswith("#"), (
                f"anchor line {index + 1} became detached from heading context"
            )

    assert _count_marker(phase_plan, "phase_0") == 1
    assert _count_marker(phase_plan, "phase_1") == 1
    assert _count_marker(checklist, "phase_0") == 1
    assert _count_marker(checklist, "phase_1") == 1


def test_create_intent_guidance_calls_out_replace_range_fallback() -> None:
    payload = build_create_intent_payload(
        result={"ok": True, "doc_name": "PHASE_PLAN"},
        metadata={"doc_type": "plan"},
        requested_doc_name="PHASE_PLAN",
    )

    assert payload is not None
    guidance = payload.get("next_step_guidance", "")
    assert "replace_section" in guidance
    assert "replace_range" in guidance
    assert "apply_patch" in guidance


def _fenced_document(fence: str, *, duplicate_target: bool = False) -> tuple[str, str, str]:
    # Public synthetic artifacts only: one-line JSON and nested Markdown examples.
    artifact = json.dumps({"literal": "<!-- ID: example -->", "text": "keep exactly"})
    inner = fence[0] * 3 if len(fence) > 3 else ""
    payload = f"{fence}json\n{artifact}\n"
    if inner:
        payload += inner + "\n"
    if duplicate_target:
        payload += "## Example heading\n<!-- ID: verification -->\n"
    payload += "<!-- ID: fenced_only -->\n" + fence + "\n"
    neighbor = "\n---\n\n## Following\n<!-- ID: following -->\nneighbor bytes\n"
    return "## Verification\n<!-- ID: verification -->\n" + payload + neighbor, payload, neighbor


@pytest.mark.regression
@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~~"])
@pytest.mark.parametrize("duplicate_target", [False, True])
def test_anchored_append_preserves_fenced_artifacts_and_neighbor(
    fence: str, duplicate_target: bool
) -> None:
    doc, payload, neighbor = _fenced_document(fence, duplicate_target=duplicate_target)
    updated = _append_block(doc, "new evidence", "verification")
    assert payload.encode() in updated.encode()
    assert updated.endswith(neighbor)
    body = _extract_section_body(updated, "verification")
    assert body is not None and payload in body and "new evidence" in body
    assert body.index(payload) < body.index("new evidence")
    assert _replace_section(doc, "verification", "replacement").endswith(neighbor)
    assert payload not in _replace_section(doc, "verification", "replacement")


@pytest.mark.regression
@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~~"])
def test_anchor_discovery_and_missing_errors_exclude_fenced_ids(fence: str) -> None:
    doc, _, _ = _fenced_document(fence, duplicate_target=True)
    inspection = inspect_document_sections_from_text(doc)
    assert [entry["id"] for entry in inspection["sections"]] == ["verification", "following"]
    assert "duplicates" not in inspection
    assert document_anchor_ids(doc) == ["verification", "following"]
    with pytest.raises(DocumentOperationError, match="SECTION_ANCHOR_MISSING") as missing:
        _replace_section(doc, "fenced_only", "no write")
    assert missing.value.extra["alternatives"] == ["verification", "following"]
    with pytest.raises(AnchorCASDenied, match="ANCHOR_MISSING"):
        _managed_anchor_snapshot(doc, "fenced_only", Path("synthetic.md"))
    duplicate = doc + "\n## Real duplicate\n<!-- ID: verification -->\ncopy\n"
    with pytest.raises(DocumentOperationError, match="SECTION_ANCHOR_AMBIGUOUS"):
        _replace_section(duplicate, "verification", "no write")
    with pytest.raises(AnchorCASDenied, match="ANCHOR_AMBIGUOUS"):
        _managed_anchor_snapshot(duplicate, "verification", Path("synthetic.md"))
    assert "verification" in inspect_document_sections_from_text(duplicate)["duplicates"]


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~~"])
async def test_managed_writes_preserve_fenced_bytes_and_cas_guards(tmp_path: Path, fence: str) -> None:
    doc, payload, neighbor = _fenced_document(fence, duplicate_target=True)
    path = tmp_path / "DOC.md"
    path.write_text(doc, encoding="utf-8")
    project = {"name": "fenced-preservation", "root": str(tmp_path), "docs_dir": str(tmp_path), "docs": {"doc": str(path)}}

    async def change(action: str, **kwargs):
        return await apply_doc_change(
            project, doc_name="doc", action=action, section=kwargs.pop("section", None),
            content=kwargs.pop("content", ""), patch=None, patch_source_hash=None,
            template=None, metadata=kwargs.pop("metadata", {}), dry_run=False, **kwargs,
        )

    digest = _managed_anchor_snapshot(doc, "verification", path)["anchor_sha256"]
    assert (await change("append", section="verification", content="appended evidence")).success
    after_append = path.read_text(encoding="utf-8")
    assert payload in after_append and after_append.endswith(neighbor)
    before_stale = path.read_bytes()
    with pytest.raises(AnchorCASDenied, match="ANCHOR_STALE"):
        await change("replace_section", section="verification", content="no write", expected_anchor_sha256=digest)
    assert path.read_bytes() == before_stale

    assert (await change("frontmatter_update", metadata={"frontmatter": {"status": "ready"}})).success
    assert payload in path.read_text(encoding="utf-8")
    current = path.read_text(encoding="utf-8")
    fresh = _managed_anchor_snapshot(current, "verification", path)["anchor_sha256"]
    assert (await change("replace_section", section="verification", content=payload + "\nreplaced evidence", expected_anchor_sha256=fresh)).success
    final = path.read_text(encoding="utf-8")
    assert payload in final and final.endswith(neighbor)
    assert _managed_anchor_snapshot(final, "verification", path)["anchor_sha256"] != fresh


@pytest.mark.regression
@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~~"])
def test_fenced_target_before_real_anchor_and_scoped_replace(fence: str) -> None:
    doc, payload, neighbor = _fenced_document(fence, duplicate_target=True)
    preface = f"{fence}markdown\n## Example\n<!-- ID: verification -->\n{fence}\n\n"
    original = preface + doc
    updated, hits = _replace_text_with_scope(
        original, find_text="neighbor bytes", replace_text="must stay outside scope",
        match_mode="literal", replace_all=True, scope="section:verification",
        allow_no_match=True,
    )
    assert hits == 0 and updated == original
    assert _append_block(original, "appended evidence", "verification").startswith(preface)
    replaced = _replace_section(original, "verification", "replacement")
    assert replaced.startswith(preface) and replaced.endswith(neighbor)
    assert payload not in replaced


@pytest.mark.regression
@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~~"])
def test_existing_fence_fallback_keeps_same_anchor_semantics(
    fence: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scribe_mcp.doc_management import errors
    from scribe_mcp.doc_management.quality.scopes import HeuristicFenceScopeProvider

    monkeypatch.setattr(errors, "create_scope_provider", HeuristicFenceScopeProvider)
    doc, payload, neighbor = _fenced_document(fence, duplicate_target=True)
    assert document_anchor_ids(doc) == ["verification", "following"]
    assert payload in _append_block(doc, "new evidence", "verification")
    assert _replace_section(doc, "verification", "replacement").endswith(neighbor)
    unclosed = "## Real\n<!-- ID: real -->\n" + fence + "\n<!-- ID: fake -->\n"
    assert document_anchor_ids(unclosed) == ["real"]
    assert [item["id"] for item in inspect_document_sections_from_text(unclosed)["sections"]] == ["real"]


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["```", "~~~"])
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("closing_extra", [0, 2])
@pytest.mark.parametrize("literal_suffix", ["example", "\u00a0", "\u2003"], ids=["text", "nbsp", "em_space"])
async def test_fence_delimiter_with_text_does_not_hide_real_neighbor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fence: str, fallback: bool,
    closing_extra: int, literal_suffix: str,
) -> None:
    from scribe_mcp.doc_management import errors
    from scribe_mcp.doc_management.quality.scopes import HeuristicFenceScopeProvider

    if fallback:
        monkeypatch.setattr(errors, "create_scope_provider", HeuristicFenceScopeProvider)
    payload = (
        f"{fence}text\n{fence}{literal_suffix}\n"
        "<!-- ID: fake -->\n<!-- ID: verification -->\n"
        f"{fence}{fence[0] * closing_extra} \t\n"
    )
    neighbor = "\n---\n\n## Following\n<!-- ID: following -->\nneighbor bytes\n"
    doc = "## Verification\n<!-- ID: verification -->\n" + payload + neighbor
    appended = _append_block(doc, "new evidence", "verification")
    assert payload.encode() in appended.encode()
    assert appended.endswith(neighbor)
    assert appended.index("new evidence") < appended.index("## Following")
    replaced = _replace_section(doc, "verification", "replacement")
    assert replaced.endswith(neighbor) and payload not in replaced
    assert document_anchor_ids(doc) == ["verification", "following"]
    sections = inspect_document_sections_from_text(doc)
    assert [item["id"] for item in sections["sections"]] == ["verification", "following"]
    assert "duplicates" not in sections
    with pytest.raises(DocumentOperationError, match="SECTION_ANCHOR_MISSING") as missing:
        _replace_section(doc, "fake", "no write")
    assert missing.value.extra["alternatives"] == ["verification", "following"]

    path = tmp_path / "DOC.md"
    path.write_text(doc, encoding="utf-8")
    project = {"name": "fence-suffix", "root": str(tmp_path), "docs_dir": str(tmp_path), "docs": {"doc": str(path)}}
    digest = _managed_anchor_snapshot(doc, "verification", path)["anchor_sha256"]
    following_digest = _managed_anchor_snapshot(doc, "following", path)["anchor_sha256"]
    with pytest.raises(AnchorCASDenied, match="ANCHOR_MISSING"):
        _managed_anchor_snapshot(doc, "fake", path)

    async def replace(content: str):
        return await apply_doc_change(
            project, doc_name="doc", action="replace_section", section="verification",
            content=content, patch=None, patch_source_hash=None, template=None,
            metadata={}, dry_run=False, expected_anchor_sha256=digest,
        )

    assert (await replace(payload + "\nnew evidence")).success
    final = path.read_text(encoding="utf-8")
    assert payload.encode() in path.read_bytes() and final.endswith(neighbor)
    assert _managed_anchor_snapshot(final, "following", path)["anchor_sha256"] == following_digest
    before_stale = path.read_bytes()
    with pytest.raises(AnchorCASDenied, match="ANCHOR_STALE"):
        await replace("stale writer")
    assert path.read_bytes() == before_stale


@pytest.mark.regression
@pytest.mark.parametrize("fence", ["```", "~~~"])
@pytest.mark.parametrize("closing_padding", [" ", "\t", " \t\r"], ids=["space", "tab", "crlf"])
@pytest.mark.parametrize("fallback", [False, True])
def test_ascii_fence_closers_keep_following_real_section(
    fence: str, closing_padding: str, fallback: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scribe_mcp.doc_management import errors
    from scribe_mcp.doc_management.quality.scopes import HeuristicFenceScopeProvider

    if fallback:
        monkeypatch.setattr(errors, "create_scope_provider", HeuristicFenceScopeProvider)
    payload = f"{fence}text\n<!-- ID: verification -->\n{fence}{closing_padding}\n"
    neighbor = "\n---\n\n## Following\n<!-- ID: following -->\nneighbor bytes\n"
    doc = "## Verification\n<!-- ID: verification -->\n" + payload + neighbor
    appended = _append_block(doc, "new evidence", "verification")
    assert payload.encode() in appended.encode() and appended.endswith(neighbor)
    assert appended.index("new evidence") < appended.index("## Following")
    replaced = _replace_section(doc, "verification", payload + "updated evidence")
    assert payload.encode() in replaced.encode() and replaced.endswith(neighbor)
    assert document_anchor_ids(doc) == ["verification", "following"]
    assert [item["id"] for item in inspect_document_sections_from_text(doc)["sections"]] == ["verification", "following"]
    path = Path("synthetic.md")
    following_digest = _managed_anchor_snapshot(doc, "following", path)["anchor_sha256"]
    assert _managed_anchor_snapshot(appended, "following", path)["anchor_sha256"] == following_digest


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize(
    "invalid_opener",
    ["```bad`info", "\t```text", "\u00a0```text", "\t~~~text", "\u00a0~~~text"],
    ids=["backtick_info", "tab_backtick", "nbsp_backtick", "tab_tilde", "nbsp_tilde"],
)
async def test_invalid_fence_openers_do_not_hide_real_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fallback: bool, invalid_opener: str
) -> None:
    from scribe_mcp.doc_management import errors
    from scribe_mcp.doc_management.quality.scopes import HeuristicFenceScopeProvider

    if fallback:
        monkeypatch.setattr(errors, "create_scope_provider", HeuristicFenceScopeProvider)
    neighbor = "\n---\n\n## Following\n<!-- ID: following -->\nneighbor bytes\n"
    doc = (
        "## Real\n<!-- ID: real -->\n" + invalid_opener
        + "\n<!-- ID: literal -->\n" + neighbor
    )
    assert not any(
        scope.kind == "fenced_code"
        for scope in errors.create_scope_provider().collect_scopes(doc)
    )
    assert document_anchor_ids(doc) == ["real", "literal", "following"]
    assert [item["id"] for item in inspect_document_sections_from_text(doc)["sections"]] == ["real", "literal", "following"]
    appended = _append_block(doc, "new evidence", "real")
    assert invalid_opener in appended and appended.endswith(neighbor)
    assert appended.index("new evidence") < appended.index("## Following")
    assert _replace_section(doc, "real", "replacement").endswith(neighbor)
    with pytest.raises(DocumentOperationError, match="SECTION_ANCHOR_MISSING") as missing:
        _replace_section(doc, "missing", "no write")
    assert "following" in missing.value.extra["remediation"]

    path = tmp_path / "DOC.md"
    path.write_text(doc, encoding="utf-8")
    project = {"name": "non-fence", "root": str(tmp_path), "docs_dir": str(tmp_path), "docs": {"doc": str(path)}}
    digest = _managed_anchor_snapshot(doc, "real", path)["anchor_sha256"]
    following_digest = _managed_anchor_snapshot(doc, "following", path)["anchor_sha256"]

    async def replace(content: str):
        return await apply_doc_change(
            project, doc_name="doc", action="replace_section", section="real",
            content=content, patch=None, patch_source_hash=None, template=None,
            metadata={}, dry_run=False, expected_anchor_sha256=digest,
        )

    assert (await replace("replacement")).success
    final = path.read_text(encoding="utf-8")
    assert final.endswith(neighbor)
    assert _managed_anchor_snapshot(final, "following", path)["anchor_sha256"] == following_digest
    before_stale = path.read_bytes()
    with pytest.raises(AnchorCASDenied, match="ANCHOR_STALE"):
        await replace("stale writer")
    assert path.read_bytes() == before_stale


@pytest.mark.regression
@pytest.mark.parametrize("fence", ["```", "~~~"])
@pytest.mark.parametrize("indent", [0, 1, 2, 3])
@pytest.mark.parametrize("fallback", [False, True])
def test_valid_fence_openers_and_unclosed_blocks_keep_canonical_scope(
    monkeypatch: pytest.MonkeyPatch, fence: str, indent: int, fallback: bool
) -> None:
    from scribe_mcp.doc_management import errors
    from scribe_mcp.doc_management.quality.scopes import HeuristicFenceScopeProvider

    if fallback:
        monkeypatch.setattr(errors, "create_scope_provider", HeuristicFenceScopeProvider)
    padding = " " * indent
    info = "python" if fence[0] == "`" else "md `literal`"
    payload = f"{padding}{fence}{info}\n<!-- ID: fake -->\n{padding}{fence}\n"
    neighbor = "\n---\n\n## Following\n<!-- ID: following -->\nneighbor bytes\n"
    preface = "## Real\n<!-- ID: real -->\n"
    doc = preface + payload + neighbor
    assert document_anchor_ids(doc) == ["real", "following"]
    assert [item["id"] for item in inspect_document_sections_from_text(doc)["sections"]] == ["real", "following"]
    appended = _append_block(doc, "new evidence", "real")
    assert payload.encode() in appended.encode() and appended.endswith(neighbor)
    assert _replace_section(doc, "real", "replacement").endswith(neighbor)
    unclosed = preface + f"{padding}{fence}{info}\n<!-- ID: fake -->\n"
    assert document_anchor_ids(unclosed) == ["real"]
    assert [item["id"] for item in inspect_document_sections_from_text(unclosed)["sections"]] == ["real"]
    with pytest.raises(AnchorCASDenied, match="ANCHOR_MISSING"):
        _managed_anchor_snapshot(unclosed, "fake", Path("synthetic.md"))
