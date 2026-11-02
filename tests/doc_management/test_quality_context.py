import pytest
from markdown_it import MarkdownIt

from scribe_mcp.doc_management.quality.context import DocumentContextBuilder
from scribe_mcp.doc_management.quality.scopes import MarkdownItScopeProvider


COMMONMARK_CASES = [
    "# Plain *heading*\n\nParagraph with [link][ref] &amp; <em>HTML</em>.\n\n[ref]: /target\n",
    "# `heading`\n\n| a | b |\n| - | - |\n| `x` | text |\n",
    "\\`escaped\\` and `code` and ``multi ` tick`` and ```three```\n",
    "`multi\nline` and `&amp; <b>x</b>` and &#96;entity&#96;\n",
    "\tindented\r\n\r\nUnicode é中 `literal`\r\n",
    "- item\n  - nested `code`\n\n    ```python\n    [fill this section]\n    ```\n",
    "> quote `code`\n>\n> ~~~\n> quoted\n> ~~~\n",
    "    indented\n\n    continuation\n\nnormal `code`\n",
    "[link `code`](https://example.test) ![image `code`](image)\n",
    "[ref]: /target `title`\n\n[reference][ref] and <https://example.test>\n",
    "<!-- `html` -->\n\n<script>var x = `value`;</script>\n",
    "`same` then `same`\n\n`same`\n",
] + [
    f"{marker * length}python\n`literal` [fill this section]\n{marker * close}\n"
    for marker in ("`", "~") for length in (3, 4, 5) for close in (0, 3, 4, 5, 6)
]


@pytest.mark.regression
@pytest.mark.parametrize("body", COMMONMARK_CASES)
def test_scopes_and_context_match_unmodified_commonmark(body: str, monkeypatch) -> None:
    # Use the actual installed parser, comparing all fields and ordering.
    native = MarkdownItScopeProvider()
    native._md = MarkdownIt("commonmark")
    candidate = MarkdownItScopeProvider()
    assert list(candidate.collect_scopes(body)) == list(native.collect_scopes(body))
    text = "---\nstatus: ready\n---\n" + body
    assert DocumentContextBuilder(candidate).build(text=text) == DocumentContextBuilder(native).build(text=text)
    from scribe_mcp.doc_management import scaffold_quality

    actual = scaffold_quality.analyze_scaffold_quality(text=text, doc_name="CHECKLIST")
    with monkeypatch.context() as oracle:
        oracle.setattr(scaffold_quality, "DocumentContextBuilder", lambda: DocumentContextBuilder(native))
        assert actual == scaffold_quality.analyze_scaffold_quality(text=text, doc_name="CHECKLIST")


@pytest.mark.regression
def test_scope_provider_only_parses_code_bearing_inline_content(monkeypatch) -> None:
    provider = MarkdownItScopeProvider()
    original = provider._md.inline.parse
    calls = []

    def observed(src, md, env, tokens):
        calls.append(src)
        return original(src, md, env, tokens)

    monkeypatch.setattr(provider._md.inline, "parse", observed)
    body = "# Plain *heading*\n\nPlain [link](/target).\n\nUse `literal`.\n"
    provider.collect_scopes(body)
    assert calls == ["Use `literal`."]


def test_context_scopes_cover_required_fence_variants() -> None:
    text = """---
status: in_progress
---

````python
```inner
print('x')
```
````

~~~js
console.log('tilde')
~~~

> ```
> quoted
> ```

- list item
  ```md
  inside list
  ```

| col | finding |
| --- | --- |
| 1 | `inline` |

    indented code

```unclosed
still inside
"""
    context = DocumentContextBuilder().build(text=text, doc_name="CHECKLIST")
    fence_scopes = [s for s in context.scopes if s.kind == "fenced_code"]
    fence_texts = [context.body_text[s.start_offset : s.end_offset] for s in fence_scopes]
    assert context.parser_backend in {"markdown-it-py", "heuristic-fence-v1"}
    assert len(fence_scopes) >= 4
    assert any(s.attributes.get("fence_marker") == "`" and s.attributes.get("fence_length") == "4" for s in fence_scopes)
    assert any(s.attributes.get("fence_marker") == "~" for s in fence_scopes)
    assert any("inside list" in text for text in fence_texts)
    assert not any("quoted" in text for text in fence_texts)
    assert not any("| col | finding |" in text for text in fence_texts)
    assert not any("`inline`" in text for text in fence_texts)
    assert "`inline`" in context.body_text
    # Indented code is intentionally not modeled as a fenced-code scope.
    assert not any("indented code" in text for text in fence_texts)
    assert "    indented code" in context.body_text
    assert any(s.attributes.get("unclosed") == "true" for s in fence_scopes)


def test_context_parses_frontmatter_once_and_preserves_body() -> None:
    text = "---\nstatus: draft\n---\n\nBody line\n"
    context = DocumentContextBuilder().build(text=text, doc_name="SPEC")
    assert context.frontmatter_data.get("status") == "draft"
    assert "Body line" in context.body_text


def test_context_scopes_distinguish_repeated_identical_inline_code_literals() -> None:
    text = """---
status: in_progress
---
Use `[fill this section]` as literal one.
Use `[fill this section]` as literal two.
"""
    context = DocumentContextBuilder().build(text=text, doc_name="CHECKLIST")
    inline_scopes = [s for s in context.scopes if s.kind == "inline_code"]
    matching_scopes = [s for s in inline_scopes if context.body_text[s.start_offset : s.end_offset] == "`[fill this section]`"]

    assert len(matching_scopes) == 2
    assert matching_scopes[0].start_offset < matching_scopes[1].start_offset
