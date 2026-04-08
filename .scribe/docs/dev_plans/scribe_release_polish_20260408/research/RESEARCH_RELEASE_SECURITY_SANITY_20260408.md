---
id: scribe_release_polish_20260408-research-release-security-sanity-20260408
title: "\U0001F52C Release Security Sanity 20260408 \u2014 scribe_release_polish_20260408"
doc_type: RESEARCH_RELEASE_SECURITY_SANITY_20260408
doc_name: RESEARCH_RELEASE_SECURITY_SANITY_20260408
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-08 02:20:11 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Release Security Sanity 20260408 — scribe_release_polish_20260408
**Author:** Scribe
**Version:** v0.1
**Status:** scaffolded
**Last Updated:** 2026-04-08 02:14:53 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
This was a light, bounded release-sanity audit of the current public surface after recent packaging/export changes. I inspected the tracked README/install/deploy guidance, release-safe examples, shipped plugin manifests, PyPI publish workflow, deploy overlay/entrypoint, and tracked `.scribe/**` runtime residue that could still bleed into the release story.

**Primary Objective:** Confirm whether the remaining public/release-facing surface still exposes secrets, encourages unsafe defaults, or leaks operator-local material.

**Key Takeaways:**
- One concrete blocker remains: **SEC-2026-04-08-0001**. The tracked backup manifest [`.scribe/backups/postgres/latest_backup_manifest.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/backups/postgres/latest_backup_manifest.json) still contains a raw Postgres password in `pg_dump_command` even though release policy classifies `.scribe/backups/**` as runtime-local only.
- I did **not** confirm a second concrete issue in the inspected public docs/examples/plugin bundles/release automation. Those surfaces generally reinforce the intended posture: local/core by default, authenticated remote/private-mesh use only as an explicit operator choice.
- The next polish wave is security-blocked only by the backup-manifest leak. Other observations from this pass are hardening suggestions, not separate vulnerabilities.
<!-- ID: research_scope -->
**Research Lead:** scribe-security-agent

**Investigation Window:** 2026-04-08 — 2026-04-08

**Focus Areas:**
- Public README/install/deploy guidance: [`README.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/README.md), [`install.sh`](/home/austin/projects/MCP_SPINE/scribe_mcp/install.sh), [`deploy/README.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/README.md), [`docs/REMOTE_CLIENT.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/REMOTE_CLIENT.md)
- Release-safe examples and plugin/export surfaces: [`docs/examples/mcp.json.example`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/examples/mcp.json.example), [`docs/examples/opencode.json.example`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/examples/opencode.json.example), [`plugins/codex/.codex-plugin/plugin.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/codex/.codex-plugin/plugin.json), [`plugins/claude/.claude-plugin/plugin.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/claude/.claude-plugin/plugin.json), [`plugins/codex/.mcp.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/codex/.mcp.json), [`plugins/claude/.mcp.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/claude/.mcp.json)
- Release automation and deploy overlays: [`.github/workflows/publish-pypi.yml`](/home/austin/projects/MCP_SPINE/scribe_mcp/.github/workflows/publish-pypi.yml), [`deploy/docker-compose.scribe.yaml`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/docker-compose.scribe.yaml), [`deploy/docker-entrypoint.sh`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/docker-entrypoint.sh)
- Tracked runtime residue vs documented release boundary: [`docs/RELEASE_SURFACE.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/RELEASE_SURFACE.md), [`docs/RELEASE_FILE_MAP.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/RELEASE_FILE_MAP.md), [`.gitignore`](/home/austin/projects/MCP_SPINE/scribe_mcp/.gitignore), [`.scribe/backups/postgres/latest_backup_manifest.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/backups/postgres/latest_backup_manifest.json)

**Dependencies & Constraints:**
- This was intentionally a **light release-polish sanity pass**, not a broad penetration-style audit.
- No implementation or secret rotation work was performed here.
- I reused the existing confirmed security case instead of opening a duplicate when the same concrete issue was revalidated.
<!-- ID: findings -->
### Finding 1
- **Summary:** **High severity / concrete blocker.** The tracked backup manifest [`.scribe/backups/postgres/latest_backup_manifest.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/backups/postgres/latest_backup_manifest.json):4-11 stores a live Postgres credential inside `pg_dump_command[4]` (`--dbname=postgresql://...`). This is a secret exposure issue in a tracked runtime artifact and remains the authoritative blocker already captured as **SEC-2026-04-08-0001**.
- **Severity:** High
- **CWE:** CWE-312 (Cleartext Storage of Sensitive Information) and CWE-200 (Exposure of Sensitive Information)
- **Impact:** Anyone with repository access can recover the database password from a file that release policy explicitly says should be runtime-local only.
- **Evidence:**
  - [`.scribe/backups/postgres/latest_backup_manifest.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/backups/postgres/latest_backup_manifest.json):4-11 shows a redacted `dsn` field but an unredacted credential in `pg_dump_command`.
  - [`docs/RELEASE_FILE_MAP.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/RELEASE_FILE_MAP.md):89-98 classifies `.scribe/backups/**` as runtime-local and not release truth.
  - [`docs/RELEASE_SURFACE.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/RELEASE_SURFACE.md):13-22 and :36-44 say mutable runtime/operator state should stay outside the public release contract.
  - [`.gitignore`](/home/austin/projects/MCP_SPINE/scribe_mcp/.gitignore):91-93 ignores other `.scribe` runtime paths but does not exclude `.scribe/backups/**`, which is consistent with how this artifact stayed tracked.
- **Confidence:** High

### Finding 2
- **Summary:** No additional concrete vulnerability was confirmed in the bounded public/release surface I inspected. The tracked docs/examples/plugin manifests and publish/deploy automation are generally aligned with the intended posture.
- **Evidence:**
  - [`README.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/README.md):60-75 and [`docs/REMOTE_CLIENT.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/REMOTE_CLIENT.md):1-40 consistently frame remote/client mode as authenticated and private-mesh only, with casual public exposure marked unsupported.
  - [`deploy/README.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/README.md):20-63 uses loopback host exposure for the quick-start container example and keeps auth explicit.
  - [`deploy/docker-compose.scribe.yaml`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/docker-compose.scribe.yaml):18-22 and :48-53 keep the compose overlay internal-only with no host ports exposed; secrets are mounted from files at :80-82 and :176-182.
  - [`deploy/docker-entrypoint.sh`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/docker-entrypoint.sh):39-54 reads secrets from `/run/secrets/*` and logs only that a secret was loaded, not the secret value.
  - [`.github/workflows/publish-pypi.yml`](/home/austin/projects/MCP_SPINE/scribe_mcp/.github/workflows/publish-pypi.yml):1-71 uses pinned actions and OIDC (`id-token: write`) instead of embedding a PyPI API token in the workflow.
  - [`docs/examples/mcp.json.example`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/examples/mcp.json.example):1-11, [`docs/examples/opencode.json.example`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/examples/opencode.json.example):1-20, [`plugins/codex/.mcp.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/codex/.mcp.json):1-8, and [`plugins/claude/.mcp.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/claude/.mcp.json):1-8 do not embed real tokens, host-specific secret paths, or operator-local credential material.
- **Confidence:** High

### Additional Notes
- Non-blocking hardening suggestion: make the `.gitignore` runtime section explicitly exclude `.scribe/backups/**` so the documented release boundary matches the actual VCS hygiene.
- Non-blocking hardening suggestion: the compose-file setup comment in [`deploy/docker-compose.scribe.yaml`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/docker-compose.scribe.yaml):166-171 uses `password` inside an example DSN. That is obviously placeholder text, not a live secret, but replacing it with `<db-password>` would reduce bad copy-paste behavior.
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- The public release guidance is internally consistent about trust boundaries: local/core is the default, and remote/client mode requires auth plus a managed private network boundary.
- The shipped plugin MCP manifests are minimal wrappers around `scribe-server` with empty `env` payloads, which avoids baking workstation-local configuration into the exported plugin bundles.
- The one broken boundary is the tracked backup manifest, where a runtime-local artifact retained a live credential even though the release policy and file map classify that whole path family as local-only.

**System Interactions:**
- Docs and examples point consumers toward tracked `docs/examples/**` files rather than repo-root overlays.
- Deployment material uses Docker secrets and an entrypoint bridge to populate env vars at runtime instead of hard-coding credentials into compose or workflow files.
- Publish automation is not the source of the blocker; the blocker is VCS hygiene around tracked runtime output.

**Risk Assessment:**
- **Confirmed blocker:** one high-severity secret exposure on the tracked release surface.
- **No second blocker identified:** the inspected release docs, examples, plugin manifests, deploy overlay, and publish workflow do not currently introduce a comparable secret exposure or unsafe-default vulnerability.
- **Residual risk:** if `.scribe/backups/**` remains trackable after the existing case is fixed, the same class of leakage can recur.
<!-- ID: recommendations -->
### Immediate Next Steps
- Treat **SEC-2026-04-08-0001** as the only confirmed security blocker from this bounded release-sanity pass.
- Remove the tracked credential-bearing backup artifact from the release surface, redact credential-bearing manifest output at generation time, and rotate the exposed Postgres credential.
- Align VCS hygiene with the documented release boundary by ensuring `.scribe/backups/**` cannot be re-tracked as public release material.
- After the fix lands, rerun this same narrow audit slice against tracked `.scribe/**` residue and public docs/examples to confirm the blocker is gone.

### Long-Term Opportunities
- Add a lightweight secret/hygiene guard for tracked runtime artifacts, especially `.scribe/backups/**`.
- Tighten example hygiene by using unmistakably placeholder secret text in commented setup examples.
- Keep the release-policy docs authoritative; they were useful here because they made the backup-manifest leak easy to classify as a real boundary violation rather than a benign dev artifact.
<!-- ID: appendix -->
- **Existing security case:** `SEC-2026-04-08-0001` (revalidated here; no duplicate case opened)
- **Primary references:**
  - [`.scribe/backups/postgres/latest_backup_manifest.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/backups/postgres/latest_backup_manifest.json)
  - [`docs/RELEASE_SURFACE.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/RELEASE_SURFACE.md)
  - [`docs/RELEASE_FILE_MAP.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/RELEASE_FILE_MAP.md)
  - [`README.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/README.md)
  - [`deploy/README.md`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/README.md)
  - [`deploy/docker-compose.scribe.yaml`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/docker-compose.scribe.yaml)
  - [`deploy/docker-entrypoint.sh`](/home/austin/projects/MCP_SPINE/scribe_mcp/deploy/docker-entrypoint.sh)
  - [`.github/workflows/publish-pypi.yml`](/home/austin/projects/MCP_SPINE/scribe_mcp/.github/workflows/publish-pypi.yml)
  - [`docs/examples/mcp.json.example`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/examples/mcp.json.example)
  - [`docs/examples/opencode.json.example`](/home/austin/projects/MCP_SPINE/scribe_mcp/docs/examples/opencode.json.example)
  - [`plugins/codex/.mcp.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/codex/.mcp.json)
  - [`plugins/claude/.mcp.json`](/home/austin/projects/MCP_SPINE/scribe_mcp/plugins/claude/.mcp.json)
- **Acceptance verdict:** The report is intentionally lightweight and targeted to release polish. It separates the one confirmed blocker from non-blocking hardening suggestions and does not expand into a broader security program.
