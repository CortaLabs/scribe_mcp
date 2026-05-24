# Research Doc Quality External Patterns - quality_check_infrastructure_20260524

**Author:** external-patterns-researcher
**Version:** v0.2
**Status:** research-complete
**Last Updated:** 2026-05-24 03:15 UTC

External/product-pattern research for making `manage_docs quality_check` a markdown-aware, low-friction, machine-readable documentation quality gate.

---
## Executive Summary
<!-- ID: executive_summary -->

The strongest external pattern is simple: separate Markdown parsing from rule execution. Quality tools that behave well around code examples first classify document regions as prose, headings, code spans, fenced blocks, blockquotes, lists, tables, frontmatter, and HTML, then run rules only against scopes that make sense. Scribe should not try to fix nested fenced-code false positives with line regexes alone.

Recommended direction for later architecture: build a lightweight internal `DocumentContext` from a CommonMark/GFM-capable parser or equivalent tokenizer, then execute a small registry of deterministic rules over scoped spans. Default checks should be fast and local. Heavy or noisy checks, such as prose style, link crawling, spell checking, or changelog/release reconciliation across broad state, should stay opt-in, release-gate-only, or advisory unless they represent existing Scribe blockers.

Best parser candidates for Scribe to evaluate are `markdown-it-py` and Marko. `markdown-it-py` is the best initial candidate from an external-pattern standpoint because it advertises CommonMark baseline parsing, configurable rules, plugins, speed, and security posture. Marko is a credible pure-Python alternative with an explicit AST renderer and extension model, but its `Markdown` instance is not thread-safe and its docs prioritize spec compliance over speed. Python-Markdown's built-in fenced-code extension is not a good fit for this specific gate because it documents root-level-only fenced blocks and cannot handle nested fences inside lists or blockquotes without a third-party extension.

Overall confidence: 0.88. Confidence is high for Markdown/fence semantics and Vale/markdownlint product patterns, medium-high for Python library fit because final choice should be verified against Scribe's exact dependency policy and regression corpus.

---
## Research Scope
<!-- ID: research_scope -->

**Investigation Window:** 2026-05-24.

**Scope Boundaries:**
- External/product-pattern research only.
- No source edits, no implementation, no final architecture.
- Sources prioritized official specifications, official tool docs, package documentation, and current CI/product integration docs.
- All web URLs below were accessed on 2026-05-24.

**Research Targets Covered:**
- Markdown linting and Markdown AST/token parsing patterns.
- Fenced code block handling, including nested examples, escaped/larger fences, blockquotes, and lists.
- Vale/prose linting patterns for rule packs, scopes, severity, suppressions, vocabulary, and false-positive control.
- Docs-as-code quality gates and CI integrations, especially fast defaults and machine-readable outputs.
- Extensible rule-engine patterns without plugin sprawl.
- Lightweight Python libraries and dependency tradeoffs.

**Limitations:**
- This lane did not inspect Scribe source; Source Map owns that evidence.
- Package versions and dependency risk should be checked by the architecture stage against Scribe's current lock/dependency policy.
- External tool behavior was not executed locally; this is documentation-backed product-pattern research.

---
## Findings
<!-- ID: findings -->

### Finding 1: Fenced-code handling must be parser- or token-stream-aware

**Stable Pattern:** CommonMark/GFM treats fenced code content as literal text. A valid fence starts with at least three backticks or tildes, closing fences must use the same character and be at least as long as the opener, and an unclosed fence continues to the end of the containing block or document. Fenced blocks may interrupt paragraphs and do not require blank lines before or after. These rules are exactly the kind of context-sensitive behavior that brittle line scans get wrong.

**Implication For Scribe:** Quality checks should classify fenced blocks before applying prose/scaffold rules. Prose rules should skip fenced code by default. Rules that intentionally inspect code examples should opt into a `code_fence` scope and receive language/info-string metadata.

**Nested/escaped examples:** GitHub's authoring guidance recommends wrapping triple backticks inside quadruple backticks when displaying code fences. A parser-aware checker will naturally treat shorter inner fences as literal content if the outer fence is longer and the closing rule is honored.

**Blockquotes/lists:** GFM/CommonMark allow containing blocks such as blockquotes and list items to bound fenced code. Python-Markdown's standard fenced-code extension explicitly does not support nested fenced blocks inside lists or blockquotes without a third-party extension. That makes Python-Markdown's stock extension risky for Scribe's false-positive target.

**Evidence:** GFM spec, section 4.5, `https://github.github.com/gfm/`; GitHub Docs code block guidance, `https://docs.github.com/github/writing-on-github/working-with-advanced-formatting/creating-and-highlighting-code-blocks`; Python-Markdown fenced code docs, `https://python-markdown.github.io/extensions/fenced_code_blocks/`.

**Confidence:** 0.96.

### Finding 2: Markdown quality gates should use scopes, not global text rules

**Stable Pattern:** Mature documentation linters expose scopes, categories, rule IDs, and suppressions. Vale calls this being markup-aware: rules can target headings, paragraphs, blockquotes, comments, or negated/composed scopes. markdownlint rules are individually named and configurable; GitHub Docs documents scoped suppression comments for a file, section, current line, next line, or specific rule names.

**Implication For Scribe:** A Scribe rule should declare the scopes it reads and the scopes it ignores. Default prose/scaffold checks should operate on prose-like scopes only. Release or managed-doc metadata checks may operate on frontmatter/doc state instead of raw Markdown text. Suppressions should be narrow, explicit, and visible in output.

**False-positive control pattern:** Prefer local allowlists/vocabulary and scoped ignores over broad global disable switches. Suppression records should include rule ID, line/span, reason when present, and whether the rule is allowed to be suppressed.

**Evidence:** Vale Scopes, `https://vale.sh/docs/scopes`; Vale Styles, `https://vale.sh/docs/styles`; GitHub Docs content linter suppressions, `https://docs.github.com/en/contributing/collaborating-on-github-docs/using-the-content-linter`; markdownlint rules, `https://github.com/markdownlint/markdownlint/blob/main/docs/RULES.md`.

**Confidence:** 0.92.

### Finding 3: Vale's product model is a useful pattern, not a direct dependency requirement

**Tool-Specific Features:** Vale supports style packages, rule severities, scopes, vocabularies, JSON output, configuration inspection, globbing, and distinct exit codes. `MinAlertLevel` lets authors show all suggestions locally while CI only fails on errors. Packages can distribute styles/configuration; vocabularies use `accept.txt` and `reject.txt` under a styles path.

**Pattern To Reuse:** Scribe can borrow the shape without embedding Vale: rule packs for document types, severity thresholds by mode, accepted/rejected project vocabulary for Scribe/Council terms, and machine-readable output. This is especially useful for distinguishing authoring advice from readiness blockers.

**Risk:** Prose linting is often noisy. It should be advisory or separately configured unless a rule protects a Scribe invariant. Style packages are powerful but can become plugin sprawl if every downstream council invents its own executable rule surface.

**Evidence:** Vale CLI, `https://vale.sh/docs/cli`; Vale MinAlertLevel, `https://vale.sh/docs/keys/minalertlevel`; Vale Packages, `https://vale.sh/docs/keys/packages`; Vale Vocab, `https://vale.sh/docs/keys/vocab`; Vale Styles, `https://vale.sh/docs/styles`.

**Confidence:** 0.90.

### Finding 4: CI-friendly gates need fast default output plus optional heavy lanes

**Stable Pattern:** Docs-as-code linting works best when local and CI output share a stable machine-readable schema. Vale supports JSON output and distinct return codes. GitHub's CodeQL/SARIF guidance shows the wider static-analysis pattern: consumers should tolerate additive fields while relying on stable fields for rule ID, message, location, and severity. markdownlint has ecosystem formatters including SARIF output for code-scanning style integrations.

**Implication For Scribe:** `quality_check` should keep readable output but also preserve structured findings with stable codes, severity, blocking status, line ranges, excerpts, suggestions, categories, and doc-type context. For CI, support threshold/mode controls such as `fast`, `full`, and `release`, but default to fast deterministic local checks.

**Gate Pattern:** Separate three modes:
- `authoring`: shows suggestions and warnings; non-blocking by default.
- `readiness`: blocks on scaffold residue, malformed metadata, broken managed-doc structure, and known Scribe invariants.
- `release`: includes slower/global checks such as changelog coverage, version drift, cross-doc state, and packaging closeout.

**Evidence:** Vale CLI JSON and exit-code docs, `https://vale.sh/docs/cli`; Vale GitHub Action, `https://github.com/marketplace/actions/vale-linter`; GitHub CodeQL SARIF output stability notes, `https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli/sarif-output`; markdownlint SARIF formatter, `https://www.npmjs.com/package/markdownlint-cli2-formatter-sarif`.

**Confidence:** 0.86.

### Finding 5: Python parser tradeoffs favor CommonMark correctness over raw speed for this gate

**markdown-it-py:** Strong candidate. It follows CommonMark baseline parsing, exposes configurable rules and plugins, advertises speed and security configuration, and is a Python port of a widely used parser. Token streams are a natural fit for scoped quality rules.

**Marko:** Credible alternative. It provides AST rendering, extension hooks, CommonMark spec alignment, and direct AST traversal. Risk: its docs say `Markdown` instances are not thread-safe; architecture should account for instance lifecycle if used.

**mistletoe-ebp:** Useful if Scribe wants explicit AST walking with position metadata and CommonMark-compliant tokens. Its docs discuss the speed/correctness tradeoff and identify Mistune as faster but less robust for complex context-sensitive parsing.

**Mistune:** Attractive for speed and no external dependencies, with renderers/plugins. Risk: docs describe compatibility with "sane CommonMark rules" rather than full CommonMark, and external parser-comparison docs identify edge cases around complex precedence. Good for rendering/simple checks, weaker as the first choice for nested fence correctness.

**Python-Markdown:** Not recommended for this specific infrastructure unless paired with extensions. The stock fenced-code extension documents root-only support, which conflicts with Scribe's need to understand nested/quoted examples.

**Evidence:** markdown-it-py docs, `https://markdown-it-py.readthedocs.io/en/latest/`; Marko usage docs, `https://marko-py.readthedocs.io/en/latest/usage.html`; mistletoe docs, `https://mistletoe-ebp.readthedocs.io/en/latest/using/intro.html`; Mistune docs, `https://mistune.lepture.com/en/v2/`; Python-Markdown fenced code docs, `https://python-markdown.github.io/extensions/fenced_code_blocks/`.

**Confidence:** 0.84.

### Finding 6: Extensibility should be a registry of typed rules, not open plugin sprawl

**Stable Pattern:** Mature validators separate rule metadata from execution and return structured errors. Pydantic's validation model is useful as an analogy: custom validators enrich typed models, errors can be serialized, and JSON Schema can describe output contracts. Vale's rule model likewise keeps rule name, level, scope, link, limit, and vocabulary behavior as metadata.

**Implication For Scribe:** Define a small internal rule protocol with typed metadata and pure functions over `DocumentContext`. Avoid a free-for-all plugin loader until there is a proven downstream extension need. Let document types and gate modes select rules declaratively.

**Suggested Rule Metadata:** rule ID, title, category, severity, default blocking flag, applicable document types, applicable scopes, gate modes, suppressibility, fix suggestion text, source/invariant owner, and optional external reference URL.

**Suggested Finding Shape:** code, message, severity, blocking, category, document path, line start, line end, column if available, scope, excerpt, suggestion, suppressible, suppression status, rule version, and metadata.

**Evidence:** Pydantic validators, `https://docs.pydantic.dev/latest/concepts/validators/`; Pydantic JSON Schema, `https://docs.pydantic.dev/latest/concepts/json_schema/`; Vale Styles, `https://vale.sh/docs/styles`; Vale Scopes, `https://vale.sh/docs/scopes`.

**Confidence:** 0.82.

---
## Technical Analysis
<!-- ID: technical_analysis -->

### Stable Patterns To Carry Forward

1. Parse once, rule many. Build a document model/token stream once, then run deterministic rules over scopes.
2. Treat code fences, indented code, inline code, and raw examples as protected scopes unless a rule explicitly targets them.
3. Store rule metadata separately from rule logic so output is stable and categories/severity can be changed without rewriting parsing.
4. Make suppressions explicit and narrow: rule-specific, scoped, line-bound, and reported back to the caller.
5. Split gates by mode: authoring advice, readiness blockers, release/global checks.
6. Prefer additive structured output fields and stable finding codes; readable output can be rendered from the structured result.

### Tool-Specific Features Worth Borrowing Carefully

- From CommonMark/GFM: exact fence open/close semantics, literal fenced content, containing-block behavior, and info-string language metadata.
- From markdownlint/GitHub Docs: rule IDs, narrow inline suppression comments, and documented rule-specific disables.
- From Vale: style/rule packs, scoped rules, severity thresholding, vocabularies, JSON output, and separate CI fail thresholds.
- From SARIF/static-analysis tools: stable machine-readable findings with rule IDs, levels, physical locations, and forward-compatible output.
- From Pydantic/schema tooling: typed result models, JSON schema for consumers, and structured validation errors.

### Dependency Risk Assessment

- `markdown-it-py`: Medium-low dependency risk; good fit if already acceptable under Scribe dependency policy. Verify package footprint and current lock impact.
- Marko: Medium dependency risk; pure Python and AST-friendly, but thread-safety lifecycle must be handled.
- `mistletoe-ebp`: Medium risk; AST-friendly and spec-conscious, but may be heavier than Scribe needs.
- Mistune: Medium risk for this exact issue; speed is attractive but complex Markdown edge correctness is the requirement.
- Python-Markdown standard fenced extension: High mismatch risk for nested/quoted examples because stock fenced blocks are root-level only.
- External Vale invocation: Medium-high operational risk if made mandatory. Better as optional advisory integration or pattern source.

### Questions For Architecture Stage

- Does Scribe already depend on a Markdown parser or parser-adjacent package that can be reused?
- Does `quality_check` need exact CommonMark rendering semantics, or only block/span classification with line ranges?
- Should suppressions live only in comments, frontmatter, managed-doc metadata, or a combination?
- Which existing Scribe warnings are readiness blockers versus release-only advisories?
- Can structured output be additive without breaking existing `manage_docs(action="quality_check")` consumers?

---
## Recommendations
<!-- ID: recommendations -->

### Immediate Recommendations For Blueprint/Synthesis

1. Design `quality_check` around a markdown-aware classification layer, not per-rule regex scans over raw document text.
2. Evaluate `markdown-it-py` first against the nested fenced-code regression corpus; evaluate Marko as the pure-Python AST fallback.
3. Require every rule to declare scopes, severity, blocking behavior, gate mode, document types, and suppressibility.
4. Preserve current useful Scribe blockers, but route style/prose advice to advisory mode unless tied to a documented invariant.
5. Add structured output as the source of truth and render current readable output from it for backward compatibility.
6. Include regression cases for outer quadruple fences containing inner triple fences, tildes, escaped backticks, blockquoted fences, list-contained fences, unclosed fences, frontmatter, tables, and inline code.

### Recommended Confidence Thresholds

- Markdown structural parsing recommendation: 0.96.
- Scoped rule registry recommendation: 0.90.
- Fast/default plus optional heavy gate recommendation: 0.86.
- `markdown-it-py` first-candidate recommendation: 0.84 until repo dependency policy and local corpus tests confirm.
- Avoiding mandatory Vale integration recommendation: 0.88 because patterns fit better than an external runtime dependency.

### Non-Recommendations

- Do not patch the fence bug with only a single multiline regex.
- Do not make prose style linting blocking by default.
- Do not create a third-party plugin ecosystem for quality rules before the internal rule protocol is stable.
- Do not use Python-Markdown's stock fenced-code extension as the only parser if nested/quoted fenced examples are in scope.
- Do not collapse release reconciliation checks into the fast authoring/default path.

---
## Appendix
<!-- ID: appendix -->

### Source Index

- GitHub Flavored Markdown Spec, accessed 2026-05-24: `https://github.github.com/gfm/`
- GitHub Docs: Creating and highlighting code blocks, accessed 2026-05-24: `https://docs.github.com/github/writing-on-github/working-with-advanced-formatting/creating-and-highlighting-code-blocks`
- Python-Markdown Fenced Code Blocks, accessed 2026-05-24: `https://python-markdown.github.io/extensions/fenced_code_blocks/`
- markdown-it-py documentation, accessed 2026-05-24: `https://markdown-it-py.readthedocs.io/en/latest/`
- Marko usage documentation, accessed 2026-05-24: `https://marko-py.readthedocs.io/en/latest/usage.html`
- mistletoe documentation, accessed 2026-05-24: `https://mistletoe-ebp.readthedocs.io/en/latest/using/intro.html`
- Mistune documentation, accessed 2026-05-24: `https://mistune.lepture.com/en/v2/`
- markdownlint rules, accessed 2026-05-24: `https://github.com/markdownlint/markdownlint/blob/main/docs/RULES.md`
- GitHub Docs content linter suppression guidance, accessed 2026-05-24: `https://docs.github.com/en/contributing/collaborating-on-github-docs/using-the-content-linter`
- Vale CLI documentation, accessed 2026-05-24: `https://vale.sh/docs/cli`
- Vale scopes, accessed 2026-05-24: `https://vale.sh/docs/scopes`
- Vale styles, accessed 2026-05-24: `https://vale.sh/docs/styles`
- Vale MinAlertLevel, accessed 2026-05-24: `https://vale.sh/docs/keys/minalertlevel`
- Vale packages, accessed 2026-05-24: `https://vale.sh/docs/keys/packages`
- Vale vocabularies, accessed 2026-05-24: `https://vale.sh/docs/keys/vocab`
- Vale GitHub Action, accessed 2026-05-24: `https://github.com/marketplace/actions/vale-linter`
- GitHub CodeQL SARIF output notes, accessed 2026-05-24: `https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli/sarif-output`
- markdownlint-cli2 SARIF formatter, accessed 2026-05-24: `https://www.npmjs.com/package/markdownlint-cli2-formatter-sarif`
- Pydantic validators, accessed 2026-05-24: `https://docs.pydantic.dev/latest/concepts/validators/`
- Pydantic JSON Schema, accessed 2026-05-24: `https://docs.pydantic.dev/latest/concepts/json_schema/`

### Handoff Notes

This research lane is ready for synthesis after managed-doc quality proof. Source Map should decide whether an existing Scribe parser or helper can be reused before any new dependency is proposed. Architecture should convert these findings into bounded tasks only after all Wave 1 research artifacts are checked and summarized.
