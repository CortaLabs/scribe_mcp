# Research Scribe Doc Registration — scribe_document_topology_foundation_20260524

## Executive Summary
This artifact documents a topology-aware registration model that reuses the existing project document registry and avoids introducing any second registry. The immediate goal is to unblock Wave 1 synthesis by replacing scaffold residue with concrete findings on registration paths, reconciliation behavior, change-history signals, and backend compatibility risks.

Primary conclusion: document identity remains single-registry and project-scoped. Topology awareness should be expressed as additive attributes and lifecycle state within the existing registration record.

## Research Scope
Covered in this recovery:
- Registration behavior for create/discover/register-existing/rehome flows.
- Registry reconciliation paths for missing files, unregistered discoveries, duplicates, and orphans.
- Change-history support (`scribe_doc_changes`, update history, content hash, mtime).
- Storage implications and parity risks across SQLite, PostgreSQL, and Remote backends.

Out of scope:
- Source code edits.
- Any second-registry design.
- Claiming schema migration completion.

## Findings
1. Single-registry ownership is already the stable contract.
- Managed-doc runtime and storage-backed registration expect one project registry identity for each document key.

2. Reconciliation flows already exist and should remain authoritative.
- `rehome_doc`, register-existing/discovery binding, and quality-check binding paths are the intended recovery mechanism when ownership/path drift occurs.

3. Gap states must be explicit and topology-aware.
- Registered + file exists: healthy.
- Registered + file missing: missing-file defect.
- File exists + unregistered: register-existing candidate.
- Duplicate logical key: conflict requiring deterministic canonical resolution.
- Orphan ownership: rehome or explicit exclusion decision.

4. Change-history enrichment is additive and migration-sensitive.
- `scribe_doc_changes`, content hash, and mtime support should extend existing records/history pathways; do not fork identity.
- Migration and parity validation are required before readiness claims.

## Technical Analysis
Canonical topology-aware registration record (existing model reuse, no second registry):
- Existing doc identity fields remain authoritative.
- Additive attributes: canonical path, discovered path, content hash, mtime, sync status, and last change marker.
- State flags should represent missing/duplicate/orphan conditions without introducing parallel registries.

Rehome/register-existing/doc discovery behavior:
- Rehome is the ownership correction path when project topology is wrong.
- Discovery/register-existing should bind unregistered files into existing registry semantics.
- Duplicate logical docs should be resolved by deterministic canonical selection plus audit metadata.

Storage backend implications:
- SQLite: additive columns/indexes with defaults are feasible; migration idempotency required.
- PostgreSQL: parity migrations are feasible but risk is higher due monolith complexity and decomposition debt.
- Remote: API compatibility must tolerate schema skew and partial feature rollout; absence of new fields must degrade safely.

Schema/migration risk (surfaced, not assumed):
- Any history/hash/mtime expansion requires explicit idempotent migrations and default values.
- Cross-backend parity requires validation coverage for register-existing, rehome, missing-file, duplicate, and orphan states.

## Recommendations
Immediate:
- Keep one canonical registry; express topology via additive fields/state.
- Define deterministic duplicate/orphan resolution rules.
- Plan additive migrations with defaults for SQLite/PostgreSQL and graceful compatibility behavior for Remote.
- Add parity tests for registration and reconciliation flows across all three backends.

Long-term:
- Add registry-health digest outputs for quicker synthesis/review gates.
- Standardize hash/mtime semantics to keep doc-change history consistent across backends.

## Appendix
Primary evidence files:
- src/scribe_mcp/doc_management/runtime.py
- src/scribe_mcp/doc_management/manager.py
- src/scribe_mcp/doc_management/special_create.py
- src/scribe_mcp/doc_management/quality/results.py
- src/scribe_mcp/tools/manage_docs.py
- src/scribe_mcp/storage/base.py
- src/scribe_mcp/storage/models.py
- src/scribe_mcp/storage/sqlite.py
- src/scribe_mcp/storage/postgres/__init__.py
- src/scribe_mcp/storage/remote.py
