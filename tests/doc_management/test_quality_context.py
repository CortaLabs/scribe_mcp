from scribe_mcp.doc_management.quality.context import DocumentContextBuilder


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
