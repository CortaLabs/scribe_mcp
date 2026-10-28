# Release Surface

Updated: **2026-10-28**
Applies to: **v3.3.62 development candidate; default projection, integration and fleet acceptance pending**

## Development candidate

The 3.3.62 checkpoint removes a global fake server from document-routing tests to prevent order-dependent failures.

The 3.3.61 checkpoint isolates append tests from collection-time fake modules so neighboring tests run in either order.

The 3.3.60 checkpoint returns a clear refusal after an identity-changing append retry instead of an internal error, without writing under the altered identity.

The 3.3.59 checkpoint aligns the development test dependencies with the async fixture API used by the test suite.

The 3.3.58 checkpoint handles timestamps whose offsets overflow the UTC date range during priority sorting, using the existing stable invalid-time fallback.

The 3.3.57 checkpoint corrects a schema test to verify both the patch hash type and its body-hash documentation.

The 3.3.56 checkpoint orders equal-priority file-backed entries by their full timestamps before applying sparse-log limits.

The 3.3.55 checkpoint keeps inline item anchors inside their parent section when applying a scoped text replacement.

The 3.3.54 checkpoint preserves Unicode separators in untouched fenced content during structured block replacement and header normalization, including unified-diff compilation and patch parsing.

The 3.3.53 checkpoint preserves Unicode line and paragraph separators in fenced document content during section and frontmatter updates. Existing CRLF normalization is unchanged.

The 3.3.52 checkpoint moves review and agent-card index discovery off the event loop while retaining the cancellation-safe write path.

The 3.3.51 checkpoint uses UTC for timestamps labeled UTC in generated indexes and reports.

The 3.3.50 checkpoint moves research and case-index filesystem work off the event loop and keeps index writes joined through cancellation.

The 3.3.49 checkpoint restores research-document tests using isolated MCP session binding, retaining their original assertions.

The 3.3.48 checkpoint fixes quality checks selecting a top-level alias over the canonical research document after registration.

The 3.3.47 checkpoint aligns the public setup and remote guides with the current 3.x MCP policy. Legacy code removal and old-request rejection remain open.

The 3.3.46 checkpoint moves project-health file inventory and stat work off the event loop, while keeping shared readiness state on the event loop.

The 3.3.45 checkpoint reads a research index once per project-health request and reuses registered paths while preserving the full findings.

The 3.3.44 checkpoint restores project-health tests with isolated native MCP session and real persisted project binding.

The 3.3.43 checkpoint keeps document-quality scans responsive during slow Git and filesystem work for both single and bulk checks, while awaiting the same results and errors.

The 3.3.42 checkpoint restores the changelog end-to-end test using an isolated persisted session and the real request router.

The 3.3.41 checkpoint reuses one Git/version observation for a document context-drift scan instead of repeating it for each accepted entry.

The 3.3.40 checkpoint distinguishes clean Git working trees from unavailable Git status when recording document version context.

The 3.3.39 checkpoint keeps managed-document registry updates awaited while moving their blocking SQLite work off the event loop. Isolated contention tests cover both persisted updates and nonfatal lock failures.

The 3.3.38 checkpoint pins the managed-document test client to the current MCP protocol rather than automatic negotiation.

The 3.3.37 checkpoint removes a redundant client process from the recency test harness while retaining a fresh real MCP server and isolated session for each case. Tests use the current protocol explicitly.

The 3.3.36 checkpoint isolates the managed-document test registry to each scenario database. The original test group and persisted registry checks remain intact while avoiding repeated SQLite lock timeouts.

The 3.3.35 checkpoint fixes managed-document edit metrics: edits now pass the document identifier using the registry API, allowing its existing hygiene hashes and flags to update. The original document-change and session-provenance behavior remains intact.

The 3.3.34 checkpoint keeps receipt-only `manage_docs/apply_preview` requests free of automatically injected project arguments. It preserves missing canonical receipt project keys from matching verified binding metadata while keeping explicit target keys and strict scope comparisons intact. Retained rehome execution reloads its source through the existing project context loader, preserving document-directory metadata for the unchanged transaction guards. Explicit caller project selectors still reach the unchanged receipt validator, and other actions and tools retain default-project projection. Identity, response-budget, foreign-recovery and fleet acceptance remain open.

The 3.3.33 checkpoint advertises the package version in current MCP server metadata. The CLI and MCP server both use the existing canonical runtime version, avoiding an empty wire version or a separate CLI version literal. Protocol admission, identity and binding behavior are unchanged; current PostgreSQL reconnection and full release acceptance remain open.

The 3.3.32 checkpoint places the nine database-free receipt codec cases in the core storage regression lane. The original assertions and payload bytes are preserved; shared receipt factories have one reusable location, and live PostgreSQL round trips retain their integration, PostgreSQL, storage and regression markers. Production receipt decoding is unchanged. Source review, foreign recovery and live-release acceptance remain open.

The 3.3.31 checkpoint fixes PostgreSQL preview-receipt persistence: JSONB text is decoded and written through the existing canonical JSON encoder before strict record comparison. Receipt equality, scope checks, fences and literal content remain intact. Regression coverage exercises text and decoded codecs, reordered keys, Unicode, malformed JSON and real PostgreSQL insert/fetch round trips. The isolated PostgreSQL receipt suite passes all 23 cases. Foreign managed-document recovery and live acceptance remain open.

The 3.3.30 checkpoint corrects two adapter descriptions that still implied named legacy protocol support. The adapter supports the current protocol and rejects historical modes; fixed historical identifiers remain rejection discriminants. Executable adapter behavior is unchanged. Binding and integration acceptance remains open.

The 3.3.29 checkpoint explicitly marks the HTTP rejection canary as synthetic test data. Authentication, rejection, no-echo and state-preservation checks are retained. This fixture clarification changes no publication policy or runtime behavior. Current-protocol binding, output, integration and live-release acceptance remain open.

The 3.3.28 checkpoint gives CLI advisory caches one locator per canonical repository, session name and agent. Alternating callers retain their own context, and reset preserves other callers and sibling sessions. Matching older cache files remain readable; corrupt or foreign cache contents cannot supply runtime authority. Genuine separate-process regressions cover retention, reset, shared-directory root isolation and corrupt-cache recovery. Trusted named-session reuse across CLI invocations and live-release acceptance remain open.

The 3.3.27 checkpoint rejects cached CLI context whose saved agent, repository or session name does not match the current caller. Separate-process regressions cover named and default cache isolation, and a current-protocol stdio check verifies live-client survival followed by prompt EOF exit. The shared cache filename can still be overwritten by another caller; independent per-agent cache retention and trusted named-session reuse across CLI invocations remain open. This checkpoint does not resolve those binding or live-release gates.

The 3.3.26 checkpoint removes stale compatibility-table guidance that still implied a supported legacy lane. SDK 1.x, old wire revisions and fallback to legacy mode are unsupported. Compatible SDK 2.x releases remain allowed; verification targets the latest stable SDK and current protocol. Runtime and live-release gates remain open.

The 3.3.25 checkpoint restores secrecy regression checks over captured HTTP server logs and verification receipts. Canary-containing logs and aggregate XML fail closed before unresolved runtime assertions can hide the result. The current-SDK policy and remaining binding, integration and live-release gates are unchanged.

The 3.3.24 checkpoint verifies against MCP SDK 2.3.0 and protocol 2026-07-28 without provisioning SDK 1.x. The matrix derives verdicts from actual test and phase results, checks retired-wire denials, and preserves the public HTTP operator restrictions alongside internal loopback coverage. Stdio binding and authoritative runtime failures remain explicit release gates.

The 3.3.23 checkpoint adds pure registered-project lookup and verified-binding projection helpers. Lookups reject invalid or contradictory selectors without changing persisted data or defaults; projection updates only the matching local session cache. These helpers are not yet wired into operational target resolution. Authorization, resolver integration, backend parity and live acceptance remain open.

The 3.3.22 checkpoint repairs the resolver test fixture to seed bindings through the current SQLite session APIs. A real regression guard verifies persistence, caller isolation and cleanup. All twelve original resolver cases remain intact; the resolver implementation and its authorization, runtime and release gates remain open.

The 3.3.21 checkpoint corrects the authenticated protocol-admission sensitivity test: authentication stays in place while an invalid-wire request bypasses only protocol admission, and the observer detects real identity-state effects. Current transport tests pass; final matrix, output, integration and live acceptance remain pending. The compatibility documentation labels earlier SDK 1.26 support as historical.

The 3.3.20 checkpoint strengthens HTTP verification with populated binding/default snapshots, exercised rejection sensitivity controls, progress-before-completion and server-side cancellation proof. The complete original node mapping and paired neighbor failure fingerprints are retained. The 74 transport tests pass; independent delta reviews, migration-matrix retirement and broader release acceptance remain open.

The 3.3.19 checkpoint serves current Streamable HTTP at /mcp and retires the paired /sse and /messages endpoints and their legacy setting. The existing sse entrypoint remains an alias with endpoint guidance. Origin, bearer, body-size, timeout and application-identity controls remain; real SDK 2.3.0 checks cover discovery, tool calls, POST SSE progress and rejected-request state preservation. Independent reviews remain pending; broader release gates remain open.

The 3.3.18 checkpoint tightens transport regression proof and adds bounded child-process cleanup with forced timeout and cancellation checks. Its behavioral, truth and quality reviews passed; the default-output integration failures remain visible.

The 3.3.17 checkpoint adds current-protocol ingress rejection before application dispatch. Real SDK 2.3.0 stdio discovery, listing and calling pass, including actual Scribe storage/session/file non-effect checks for rejected traffic. This source checkpoint awaits independent reviews; HTTP retirement, bounded output and integrated release validation remain pending.

The 3.3.16 checkpoint removes inherited Python source overrides from clean-room child commands. Installed-wheel probes and Codex projection now resolve the fresh installed package even when the development launcher injects PYTHONPATH. This repairs release verification; current-protocol and integration acceptance remain pending.

The 3.3.15 checkpoint targets the latest MCP SDK, currently 2.3.0, without excluding otherwise compatible SDK 2.x releases solely by minor version. The dependency range remains `mcp>=2.0.0,<3.0`; SDK 1.x and older wire protocols are unsupported. Latest-SDK verification is required; an older-SDK certification matrix is not part of the release. This supersedes the 3.3.14 SDK-minor restriction; current-protocol transport removal and integration gates remain open.

The 3.3.14 checkpoint makes agent/session regression checks enforce real results, isolation, rejection paths, heartbeat and expiry cleanup. The same pytest journeys drive the direct script and propagate assertion failures. Its SDK 2.3.x restriction was superseded in 3.3.15; protocol 2026-07-28 remains the release target, with obsolete protocol and endpoint removal still required.

The 3.3.13 development checkpoint carries the reviewed 2.15.34 maintenance fixes: heartbeat binding preservation, SQLite WAL startup and error cleanup, atomic entry/metric writes, genuine identity and format regressions, and isolated transport-policy tests. Public maintenance APIs and durability defaults are retained. This does not complete the original 3.x authority, output, background, schema or runtime gates.

Version 3.3.12 integrates maintenance 2.15.29. The existing authorized session root is persisted before binding classification so first reads and repository changes retain a resolved binding without recovery binds. The existing identity-upgrade preservation contract and all original 3.x source, output and runtime gates remain.

Version 3.3.11 integrates dev 2.15.28. Existing SQLite project identity preparation runs before catalog readiness. The transactional migration remains the sole identity backfill; removing a duplicate writer preserves already-keyed rows, including NULL repository identities, literal roots and extension data. Fresh, legacy and keyed catalog checks cover both entrypoints and reopen; genuine SDK guards reject startup discovery failures. The original authority, output and release gates remain open.

Version 3.3.10 integrates dev 2.15.27 without replacing the major-line authority or output contracts. Session regression fixtures establish genuine persisted bindings, and fenced-artifact checks assert metadata and attribution effects. The genuine SDK recency fixture remains unchanged.

Version 3.3.9 forwards the existing read_recent priority-sort flag to both limiting paths. False/default preserves database recency and file source order; explicit True retains priority sorting. Record membership, pagination, metadata and supplementation remain unchanged.

Version 3.3.8 stops treating valid JSON metadata strings as expression syntax. Comparisons such as `payload <=2048 bytes` and `1 > 2` retain their original operators without invented backslashes or quotes. Request healing no longer reports these unchanged values as corrections. Log-delimiter handling, existing size bounds and non-JSON fallback rules are retained.

Version 3.3.7 adds an inactive pure projector in the existing formatter dispatcher. Supported previews retain required identifiers, truthful counts, bounded UTF-8 excerpts with hashes, explicit omissions and same-page full-detail continuation. The existing budget manager checks complete modern and legacy MCP envelopes against 2 KiB. No production caller is activated; schema, producer and transport integration remain pending.

Version 3.3.6 requires setuptools 77.0.3 or newer to build its SPDX license metadata. It retains the accounting repair from 3.3.5, which measures complete response envelopes as compact JSON UTF-8 bytes, including SDK aliases, text, structured content, nested keys and metadata. The existing budget helper reports its whole returned response, including accounting and warning fields; token estimates remain heuristic. The formatter delegates to the same measurement owner. This is an accounting repair, not final default-response size enforcement or runtime certification.

Version 3.3.4 adds 78 regression cases for complete default-response size, honest envelope accounting, explicit full detail, preserved control facts and same-page continuation. This is a test-first checkpoint with expected contract failures. It does not implement or certify the bounded response contract; implementation, source integration and affected-client verification remain pending.

Version 3.3.3 adds `runtime_identity` to Doctor, reporting the loaded package version, package and Doctor module origins, and process ID. It reads the running package, not the configured repository version, and preserves deferred inventory collection. These observed diagnostics help identify a candidate; they do not attest source integrity or complete affected-client acceptance.

Version 3.3.2 restores consumer-agnostic Doctor bridge hygiene through existing YAML manifest discovery, retaining low severity, nonblocking warnings and runtime-plugin presence semantics. Deployment guidance no longer assumes a private consumer. This is a source repair; integration, publication and live acceptance remain pending.

Version 3.3.1 restores existing-project classification when a verified project's progress log is empty or rotated and baseline hashes are absent. The reader passes its already-resolved progress path to the existing classifier. This is a source repair; publication and live acceptance remain pending.

Version 3.3.0 adds SQLite persistence for bounded background-operation receipts. Admission checks global and project capacity atomically; duplicate requests share a project-scoped idempotency key. Claims and transitions check versions and fencing tokens, and reopening storage reconstructs nonterminal receipts and capacity. Scheduling, PostgreSQL parity and live acceptance remain pending.

Version 3.2.0 adds the abstract `StorageBackend.clear_session_project` API. The storage contract preserves persisted generations across clear and rebind, checks stale expectations before effects, and keeps caller authorization in the request layer. Concrete backend execution and live binding acceptance remain pending.

Version 3.1.1 clarifies that apply_patch checks a SHA-256 of the document body without YAML frontmatter. The tool schema, help and stale-source error now explain how to reuse extra.patch_source_hash from a fresh dry run. Validation predicates, reason codes and stale-write protections are unchanged.

Version 3.1.0 adds the pure call-timing recorder and envelope model. It validates finite phase durations and same-stage aggregates before recorder mutation, preserves fixed phase ordering and reports honest unaccounted time with strict latency thresholds. Consumer instrumentation and integrated latency validation remain pending.

Version 3.0.6 reuses canonical anchor offsets within each section helper operation. Extraction, snapshots, append and replacement collect Markdown scopes once per unchanged input. The reuse is local to the operation; changed text receives fresh offsets. Existing fenced-artifact and stale-write protections are retained.

Version 3.0.5 excludes fenced literal markers from section targeting, boundary detection, CAS duplicate checks, section inspection and error suggestions. Anchored append and replacement preserve fenced JSON/Markdown and neighboring headings and separators. The repair reuses existing Markdown scopes, including fallback handling for fence type, delimiter length and unclosed fences. Original CAS positive and stale-write denial behavior is retained.

Version 3.0.4 leaves the caller's repository and state-path environment unchanged when the probe module is imported. Explicit probe execution applies missing defaults before binding and preserves caller-supplied values. This prevents probe collection from changing unrelated callers' repository identity.

Version 3.0.2 builds from disposable tracked source, preserving existing artifacts and source files. It refuses same-version output collisions and includes nested tests in source archives. Plugin synchronization, metadata/README validation and archive privacy checks run before copying the new artifacts to the requested output directory.

Version 3.0.1 holds a configured SQLite connection for schema bootstrap to reduce repeated last-connection teardown, and closes newly created connections when configuration fails. Existing schema checks, commits, durability settings and initialization ordering are retained.

Version 3.0.0 introduced the Doctor default change: ordinary calls retain diagnostics and skip physical/logical inventory collection. Callers requiring the existing full v1 report must pass `reconciliation="full"`. Deferred results expose a null report and explicit `not_collected` metadata; full results preserve existing availability limits. The compatibility matrix and usage guide document migration.

This checkpoint is not a completed release or fleet rollout. Broader binding/schema work, integrated validation and actual failing-peer acceptance remain open. Public stdio validation is required if it is the affected peer's effective path. The 2.15.x maintenance candidate remains separate.

## Earlier checkpoint repairs

Version 2.15.19 corrects doctor module-origin reporting and repairs the existing document-test setup through real SDK ingress,
persisted caller bindings, and canonical metadata readback. All 53 original cases
pass with their assertions retained. Invalid actions retain both consumer and RPC
rejection checks; dependency faults still exercise partial-registration outcomes.
This is correctness evidence, not a performance or fleet certification. Broader
integration, public stdio, and actual peer acceptance remain open.

Version 2.15.17 carries the reviewed nonselecting metadata correction into this
larger development branch. Document registration refreshes existing stored
metadata and cache without changing caller or sibling project selection.
Remaining integration failures, the planned binding/schema work, public stdio
and actual peer acceptance remain release blockers. No publication or live
checkout update is implied.

Version 2.15.13 removes project-selection writes from document metadata updates.
Creating, editing, registering, or rehoming a document preserves the caller's
default project and sibling session bindings. Existing authority checks remain.
This candidate has not been promoted to the fleet. Internal-profile SDK canaries
pass; public-profile stdio binding and actual fleet acceptance remain open.

Version 2.15.12 reuses the canonical export-policy digest during document creation.
Equivalent grant lists receive the same digest in either order, while emitted
metadata order, document text, default-private behavior, and authority checks
remain unchanged.

Version 2.15.11 preserves complete bug and security report narratives during
metadata healing. Long descriptions, Unicode, line breaks, and code fences retain
their text; ordinary metadata sanitization and length limits remain enforced.

Version 2.15.10 preserves SQLite project and session extensions during canonical
identity upgrades, including typed values, column definitions, indexes, views,
and triggers. Legacy projects receive repository identities before startup indexes
are created. Project deletion and document metadata updates retain sibling
project data when labels are ambiguous.

Version 2.15.9 verifies project reads against the current caller binding and canonical
repository identity. Advisory caches and compatibility labels cannot authorize a
project selection; warm reads recheck the stored binding.

Version 2.15.8 loads tool definitions before validating a first call that precedes
tool discovery. Unknown tools and invalid arguments remain refused.

Version 2.15.7 preserves literal whitespace inside fenced artifacts across section
and frontmatter updates while retaining prose whitespace cleanup.

Version 2.15.6 makes PostgreSQL project deletion atomic. Ambiguous names refuse
deletion, and concurrent same-name projects retain their data and session context.

Version 2.15.5 strengthens binding recovery across reconnects while retaining
verified caller and repository scope.

Version 2.15.4 removes the obsolete onboarding-directory packaging rule.
Canonical onboarding and integration skills remain included from `skills/`
and the shipped plugin bundles.

Version 2.15.3 replaces a workstation-specific checkout path in the isolated
validation runbook with a portable placeholder.

Version 2.15.2 reduces repository dependency-scan work. Excluded build and cache
directories are pruned before traversal, and import extraction visits AST
statement containers without walking unrelated expression subtrees. Dependency
graphs, breadth-first import order, scan limits, and symlink behavior are retained.

Version 2.15.1 replaces the PostgreSQL session-binding classifier trigger in one
atomic batch. Concurrent binding writers retain canonical project classification
through startup, including databases upgraded from the legacy binding schema.
Release checks also handle normal TCP cleanup after a legacy SSE server stops
and use explicit synthetic credential fixtures.

## Public contract

Treat these as public release truth:

- Shipped package source and manifests:
  - `pyproject.toml`
  - `MANIFEST.in`
  - `src/scribe_mcp/**`
- Public docs and examples:
  - `README.md`
  - `docs/**`
  - `docs/examples/**`
  - `skills/**`

## Runtime truth in public docs

Public docs must keep these runtime truths aligned with current source:

- Postgres is the default storage posture.
- Standalone SQLite is explicit local-only opt-in.
- Remote/client remains internal compatibility only for this release line and is excluded by public-release posture.
- `SCRIBE_REMOTE_URL` is documented as service root; `/health` and `/sse` are distinct paths with different roles.
- Codex projection is documented through `scribe plugins project-codex`.
- Managed-doc hygiene behavior is public release truth: scaffold-aware `quality_check`, grouped `project_health` signals, project-local managed-doc preflight archives, centralized `edit_file` backups, canonical research artifact naming, and stale index-backup cleanup.
- Changelog/version memory behavior is public release truth: project `CHANGELOG.md` is curated source, `.scribe/docs/GLOBAL_CHANGELOG.md` is derived by preview/apply reconciliation, version context is advisory observed evidence, and malformed changelog escaped-newline content is a blocking quality failure.
- Missing current-version changelog coverage is a blocking warning (`SCF_CHANGELOG_CURRENT_VERSION_MISSING`) surfaced by `quality_check`, reminders, and `project_health` quality digests.
- The public release line retains the fail-closed provenance guard for changelog/global reconciliation, deterministic document topology, metadata scan/repair, quality handoff gates, agent-ready quality-check summaries/actions, bulk managed-doc checks, sanitized downstream export manifests, and governed case-registry closeout for resolved fixes.
- Fast same-binding `set_project` reuse, queryable runtime telemetry, append-entry phase timing, physical/logical reconciliation diagnostics, JSON probe output, same-server root comparison, clean success-path timing logs, and background telemetry drain behavior are public runtime truth for this release line.
- Bug/security case reports are governed repo-root documents; `open_bug`/`open_security` expose follow-up handles and `manage_docs` resolves those reports without dev-plan name guessing.
- Scribe-owned write barriers, owner-only Postgres backup/restore custody, sparse `read_recent` progress-log supplementation, and remote blocking for local operator-only tools are public runtime safety behavior.
- Downstream topology exports are generic publication artifacts. Public Scribe must not hard-code a private retrieval product as the consumer or source of truth.

## Local/operator boundary

Treat these as local/operator-only, not public contract:

- Repo overlays and agent/tooling configuration at repo root
- Local runtime state and logs under `.scribe/**`
- Build output and caches (`build/`, `dist/`, `*.egg-info/`, `__pycache__/`)
- Generated authoring/runtime overlays unless a future exported copy is intentionally tracked as public support material

If a path is workstation-specific or runtime-generated, it is not public guidance.

## Plugin and bridge boundary

Public docs should describe only shipped plugin/bridge surfaces:

- Core runtime/plugin framework in `src/scribe_mcp/bridges/**`
- Tracked onboarding and integration guides in `skills/**`
- Generic Claude and Codex plugin bundles in `.claude-plugin/` and `.codex-plugin/`

Do not present local manifests, local bridge config, unpromoted generated outputs, or local operator adapters as shipped public surface.

## Practical release check

Before publishing guidance, confirm all referenced files are:

1. Tracked in the repo
2. Part of shipped package/manifests or public docs/examples
3. Not runtime-generated and not workstation-specific

Reconnect hardening recovers scope from the persisted binding, rejects caller-supplied session identity as authority, and preserves legitimate reconstructed sessions. Public path validation and credential-shaped test fixtures remain intact.
