# MCP v2 isolated compatibility spike

This runbook produces the attributable, cleanup-authoritative receipt for the
Scribe MCP SDK v2 migration. It is a validation tool only: it does not deploy,
restart a shared runtime, edit production source, change the Git index, or
reinterpret a modern failure as legacy compatibility.

## Frozen axes

The SDK/package and wire-protocol axes are independent:

| Axis | Modern candidate | Named legacy |
|---|---|---|
| Python package | `mcp==2.0.0`, `mcp-types==2.0.0`, `httpx2==2.5.0` | `mcp==1.26.0` |
| Wire revision | `2026-07-28` | ratified contract: `2025-11-25` |
| stdio client | SDK v2 `mode="auto"` | SDK v2 `mode="legacy"` and real SDK 1.26.0 `ClientSession.initialize()` |
| HTTP client | SDK v2 Streamable HTTP `/mcp` | SDK 1.26.0 SSE `/sse` plus server-advertised `/messages/` |

The isolated probe deliberately asserts the ratified legacy revision. It must not
accept another handshake revision merely because list/call otherwise works.

## Command

Run from the validation worktree with no other repository-saturating lane active:

```bash
./.venv/bin/python scripts/mcp_v2_isolated_spike.py \
  --repo-root /home/austin/projects/MCP_SPINE/worktrees/scribe-mcp-v2 \
  --candidate 2.0.0 \
  --legacy 1.26.0 \
  --protocol 2026-07-28 \
  --json
```

The command creates two disposable `uv` environments, installs the current
worktree as a clean candidate distribution, hashes every installed file in the
four exact candidate distributions, runs `uv pip check`, executes the complete
registered aggregate, builds sdist/wheel artifacts in the disposable root,
checks console entry points and source-generated plugin readback, then removes
the entire temporary root. Cleanup failure overrides every earlier success.

The JSON object is the receipt. Preserve its stdout and process exit code
together. A `BLOCK` receipt still contains all independent passing evidence and
the exact failing commands.

## Behavioral journeys

The migration module uses the repository's canonical `test_agent` fixture and
only disposable SQLite files, state, repositories, documents, processes, and
ports.

- Modern stdio uses the real installed SDK v2 `Client`, performs discovery, and
  lists the assembled Scribe registry.
- Forced legacy stdio uses SDK v2 `mode="legacy"`; a second probe runs the real
  `mcp==1.26.0` client against the same candidate server.
- Modern HTTP uses the real SDK v2 Streamable HTTP client over the assembled
  Starlette application through `httpx2.ASGITransport`, so it opens no listener.
- Two modern clients carry the same `test-agent` label but distinct server-minted
  handles. They bind different projects/repositories, interleave reads, and one
  reconnects with its prior handle.
- Raw assembled HTTP negatives cover missing auth, invalid Origin, unsupported
  modern protocol, and header/body revision mismatch. The handler dispatch count
  remains zero and a secret canary is absent from response/log evidence.
- The real pre-v2 SSE client connects to a bounded loopback listener, follows the
  `/sse` to `/messages/` flow, and lists tools. The process is always terminated;
  the exact port must be bindable immediately afterward.
- The aggregate neighboring tests cover foreign/unknown/revoked/expired handles,
  native/REST authorization, caller-metadata poisoning, request limits/timeouts,
  shutdown/drain, entry points, schema/result adapters, and repo/session scope.

## T01-T20 disposition

`PASS` means executable evidence is present in the isolated module or registered
aggregate. `N/A` is permitted only when tied to the frozen architecture. `BLOCK`
is a product or contract defect and prevents advancement.

| ID | Disposition | Evidence / architecture decision |
|---|---|---|
| T01 | PASS | Assembled `/mcp` rejects attacker Origin before dispatch. |
| T02 | PASS | Every non-health route shares the authentication boundary; missing or wrong credentials return 401. |
| T03 | PASS | Unsupported revision and header/body mismatch return typed 400 errors with zero dispatch. |
| T04 | PASS | Recognized modern failures remain modern; the client never initializes legacy from auth, Origin, timeout, mismatch, or malformed responses. |
| T05 | PASS | Exact `mcp==1.26.0` initializes through retained `/sse` plus `/messages/` and lists 35 tools. |
| T06 | PASS | Two real same-label modern clients keep distinct project/repository bindings across interleave. |
| T07 | PASS | `/mcp` mints a Scribe application handle; reconnect with that handle restores only its binding. |
| T08 | PASS | Aggregate rejects unknown, foreign-principal, revoked, and expired handles before handler dispatch. |
| T09 | N/A | Architecture deliberately supports legacy continuity only in the current sticky single-worker model; unknown/wrong-worker state fails closed and no multi-worker continuity is promised. |
| T10 | N/A | MRTR/input state is an explicit non-goal for this release; no request-state authority exists to replay. |
| T11 | N/A | The chosen model is documented operator-root bearer, not scoped multi-user OAuth. No scoped-auth claim is made. |
| T12 | PASS | Aggregate applies the same server-owned remote-tool policy to modern MCP, legacy MCP, and REST. |
| T13 | PASS | Agent label, client info, capabilities, request/process identifiers, and forged session headers cannot become principal/project/repo authority. |
| T14 | PASS | Exact legacy HTTP reaches `list_tools` and returns the same 35-tool assembled registry. |
| T15 | PASS | Modern discovery is private and clients use separately partitioned SDK caches/handles. |
| T16 | PASS | Credential/parameter canary is absent from response, log, and redacted receipt output; reason/type evidence remains. |
| T17 | N/A | This release exposes no streaming mutating result or automatic retry. Request timeout and shutdown/drain fail closed; streaming write/resumability remains a non-goal. |
| T18 | PASS | Legacy selection is explicit; malformed modern discovery/error paths do not fall back. |
| T19 | PASS | Enforcement comes from the server registry/policy, not descriptive annotations. |
| T20 | PASS | Source policy/readback and both named real clients agree on legacy `2025-11-25`. |

## Repaired validation deltas

The initial validation found two load-bearing failures. Independent owner repairs
landed before this delta rerun, and the original failures remain encoded as
regression expectations rather than weakened or hidden:

1. Architecture and source/readback now ratify the observed public-client wire
   behavior: `mcp==2.0.0` forced legacy and exact `mcp==1.26.0` must both
   negotiate `2025-11-25` and list exactly 35 tools. `2025-06-18` is retained
   only as malformed/header-mismatch negative input, never expected readback.
2. The retained SSE handler now assembles initialization through the valid SDK v2
   compatibility boundary. Exact `mcp==1.26.0` must complete `/sse` plus
   `/messages/`, negotiate `2025-11-25`, list exactly 35 tools, and leave its
   listener port immediately reusable after shutdown.

I6 does not edit either repair. It proves their assembled behavior and blocks on
any regression, cleanup failure, or mismatch with the ratified contract.

## Rollback proof

Rollback is proven without touching the worktree or index:

- read current `pyproject.toml` and confirm `mcp>=2.0.0,<3.0`;
- read `HEAD:pyproject.toml` into memory and confirm the prior
  `mcp==1.26.0` dependency;
- construct an in-memory dependency rollback shadow and confirm the prior
  `mcp==1.26.0` pin replaces the candidate range while the prior transport
  default remains `stdio`;
- confirm `HEAD` has no `src/scribe_mcp/mcp_adapter.py` while the candidate does;
- confirm the current explicit legacy policy remains `2025-11-25` and every
  source-owned release/readback document names `2025-11-25` with no
  `2025-06-18` expected readback;
- record that only a disposable shadow/readback was used;
- record `modern_failure_reclassified_as_legacy=false`.

This proves source restoration material exists. It does not execute Git reset,
restore, checkout, stash, clean, commit, push, deployment, or restart.

## Cleanup gate

Cleanup is a hard override:

1. Every client/session/context exits through an async context manager.
2. The legacy HTTP child is terminated in `finally`, then killed only if bounded
   graceful termination times out.
3. The exact ephemeral port is rebound after the child exits.
4. Candidate/legacy venvs, SQLite/state files, repos, build outputs, and logs live
   under one `scribe-mcp-v2-isolated-*` temporary root.
5. `shutil.rmtree` removes that root. If it remains or removal raises, the final
   verdict is `BLOCK` even when all behavioral rows passed.

## Delta reruns

If either repaired journey regresses, run these focused deltas first:

```bash
./.venv/bin/python -m pytest -q \
  'tests/migration/mcp_v2/test_compatibility_matrix.py::test_named_legacy_stdio_negotiates_frozen_revision_regression' \
  tests/migration/mcp_v2/test_compatibility_matrix.py::test_pre_v2_client_uses_retained_sse_and_messages_and_listener_is_cleaned
```

Then rerun the exact isolated spike and the complete registered aggregate once.
The direct aggregate requires either configured Postgres or the same hermetic
`SCRIBE_MODE=standalone SCRIBE_STORAGE_BACKEND=sqlite` environment used by the
isolated spike; collection intentionally fails closed when neither is present.
