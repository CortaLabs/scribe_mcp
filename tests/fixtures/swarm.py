"""The shared C-14 corpus and exact-effects oracle; no product implementation.

Consumers supply observations from the real runtime/storage.  This module never
resolves a project, schedules a job, executes an effect, or repairs a receipt.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping, Sequence


MIX = {"ambient_append": 30, "read": 20, "document": 20,
       "explicit_same_repo": 15, "explicit_cross_repo": 5,
       "reconnect": 5, "negative": 5}
TIMING_PHASES = ("ingress_decode", "session_binding_read", "project_record_read",
                 "target_resolution", "mode_resolution", "tool_body",
                 "authority_and_validation", "authoritative_durability",
                 "receipt_commit", "hooks", "response_format", "audit_append",
                 "egress_serialize", "unaccounted")


class ManualClock:
    """Monotonic seconds, advanced explicitly in integer milliseconds."""
    def __init__(self) -> None:
        self._milliseconds = 0

    def now(self) -> float:
        return self._milliseconds / 1000

    def advance(self, delta_ms: int) -> None:
        if isinstance(delta_ms, bool) or not isinstance(delta_ms, int) or delta_ms < 0:
            raise ValueError("delta_ms must be a nonnegative integer")
        self._milliseconds += delta_ms


@dataclass
class CausalGate:
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def hold(self) -> None:
        self.entered.set()
        await self.release.wait()


@dataclass(frozen=True)
class SwarmProject:
    project_key: str
    name: str
    root: Path
    progress_log: Path


@dataclass(frozen=True)
class SwarmCaller:
    caller_id: str
    agent_label: str
    default: SwarmProject
    same_repo: SwarmProject
    cross_repo: SwarmProject


@dataclass(frozen=True)
class SwarmTopology:
    repositories: tuple[Path, ...]
    projects: tuple[SwarmProject, ...]
    callers: tuple[SwarmCaller, ...]

    def as_json_dict(self) -> dict[str, object]:
        # Absolute temporary roots are deliberately excluded from portable C-14.
        return {"repositories": 4, "projects_per_repository": 4,
                "callers_per_project": 2, "callers": len(self.callers),
                "projects": [{"key": p.project_key, "name": p.name,
                              "repository": self.repositories.index(p.root)}
                             for p in self.projects]}


def build_swarm_topology(tmp_path: Path, *, agent_label: str, seed: int) -> SwarmTopology:
    """Create disposable files, never caller authority or synthetic sessions."""
    roots = tuple(tmp_path / f"repo-{i}" for i in range(4))
    projects = []
    for ri, root in enumerate(roots):
        (root / ".git").mkdir(parents=True)
        for pi in range(4):
            name = "shared" if pi == 0 else f"project-{ri}-{pi}"
            docs = root / ".scribe" / "docs" / "dev_plans" / name
            docs.mkdir(parents=True)
            log = docs / "PROGRESS_LOG.md"
            log.write_text("# Progress Log\n", encoding="utf-8")
            # Opaque test-corpus keys, replaced by persisted keys by runtime consumers.
            key = hashlib.sha256(f"{seed}:repo-{ri}:{name}".encode()).hexdigest()
            projects.append(SwarmProject(key, name, root, log))
    callers = tuple(SwarmCaller(f"caller-{i:02d}", agent_label, p,
                               projects[(i // 8) * 4 + ((i // 2 + 1) % 4)],
                               projects[(((i // 8) + 1) % 4) * 4 + ((i // 2) % 4)])
                    for i, p in enumerate(p for p in projects for _ in range(2)))
    return SwarmTopology(roots, tuple(projects), callers)


@dataclass(frozen=True)
class SwarmOperation:
    operation_id: str
    caller_id: str
    kind: str
    ordinal: int
    default_project_key: str
    explicit_project_key: str | None
    target_project_key: str
    mutation_fingerprint: str
    expected_effect: str
    expected_result_code: str


def build_mixed_schedule(caller: SwarmCaller, *, seed: int) -> tuple[SwarmOperation, ...]:
    kinds = [kind for kind, count in MIX.items() for _ in range(count)]
    random.Random(f"{seed}:{caller.caller_id}").shuffle(kinds)
    result = []
    negatives = iter(("SCRIBE_PROJECT_AMBIGUOUS", "SCRIBE_PROJECT_NOT_FOUND",
                      "SCRIBE_PROJECT_ROOT_MISMATCH", "SCRIBE_BINDING_MISSING",
                      "SCRIBE_CALLER_SESSION_UNVERIFIED"))
    for i, kind in enumerate(kinds):
        target = caller.same_repo if kind == "explicit_same_repo" else (
            caller.cross_repo if kind == "explicit_cross_repo" else caller.default)
        operation_id = f"{seed}:{caller.caller_id}:{i:03d}"
        effect = "log" if kind in ("ambient_append", "explicit_same_repo", "explicit_cross_repo") else (
            "document" if kind == "document" else "none")
        result.append(SwarmOperation(operation_id, caller.caller_id, kind, i,
                                     caller.default.project_key,
                                     target.project_key if kind.startswith("explicit_") else None,
                                     target.project_key, hashlib.sha256(operation_id.encode()).hexdigest(),
                                     effect, next(negatives) if kind == "negative" else "OK"))
    return tuple(result)


@dataclass(frozen=True)
class ExpectedEffect:
    run_id: str
    operation_id: str
    caller_id: str
    application_id: str
    stable_session_id: str
    default_project_key: str
    explicit_project_key: str | None
    target_project_key: str
    mutation_fingerprint: str
    effect: str
    result_code: str
    binding_generation: int = 1


@dataclass(frozen=True)
class ObservedEffect(ExpectedEffect):
    default_after: str = ""
    generation_after: int = 1
    binding_reads: int = 1
    project_reads: int = 1
    context_count: int = 1
    timing_envelope_count: int = 1
    accounted_ratio: float = 1.0
    stale_fence_accepted: bool = False


@dataclass(frozen=True)
class SwarmRunMetadata:
    source_revision: str
    seed: int
    topology: Mapping[str, object]
    set_project_count: Mapping[str, int]
    background_queue: Mapping[str, object] = field(default_factory=dict)
    timing_histograms: Mapping[str, object] = field(default_factory=dict)
    fault_timeline: Sequence[Mapping[str, object]] = ()
    teardown_counts: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SwarmResultsV1:
    metadata: SwarmRunMetadata
    operation_ledger: tuple[Mapping[str, object], ...]
    oracle_cardinalities: Mapping[str, int]

    @property
    def verdict(self) -> str:
        return "PASS" if not any(self.oracle_cardinalities.values()) else "FAIL"

    def as_json_dict(self) -> dict[str, object]:
        return copy.deepcopy({"schema_version": "scribe-swarm-results.v1",
                "source_revision": self.metadata.source_revision,
                "seed": self.metadata.seed, "topology": dict(self.metadata.topology),
                "set_project_count": dict(sorted(self.metadata.set_project_count.items())),
                "operation_ledger": [dict(row) for row in self.operation_ledger],
                "oracle_cardinalities": dict(sorted(self.oracle_cardinalities.items())),
                "background_queue": dict(self.metadata.background_queue),
                "timing_histograms": dict(self.metadata.timing_histograms),
                "fault_timeline": list(self.metadata.fault_timeline),
                "teardown_counts": dict(self.metadata.teardown_counts),
                "verdict": self.verdict})

    def as_markdown(self) -> str:
        data = self.as_json_dict()
        return f"C-14: {data['verdict']}\n\n```json\n{json.dumps(data, sort_keys=True, indent=2)}\n```\n"


def reconcile_exact_effects(expected: Sequence[ExpectedEffect], observed: Sequence[ObservedEffect],
                            *, metadata: SwarmRunMetadata) -> SwarmResultsV1:
    """Compare exact multisets, retaining all failed observations in one ledger."""
    fields = tuple(ExpectedEffect.__dataclass_fields__)
    def identity(row: ExpectedEffect) -> tuple[object, ...]:
        return tuple(getattr(row, name) for name in fields)

    wanted, actual = Counter(map(identity, expected)), Counter(map(identity, observed))
    by_operation = {row.operation_id: row for row in expected}
    counts = dict.fromkeys(("wrong_target", "default_drift", "cross_talk", "missing_effects",
                           "duplicate_effects", "denied_effects", "untyped_errors", "stale_fences",
                           "excess_reads", "context_or_timing", "unaccounted_calls",
                           "excess_capacity", "unfairness", "bind_count", "teardown_leaks"), 0)
    counts["missing_effects"] = sum((wanted - actual).values())
    counts["duplicate_effects"] = sum((actual - wanted).values())
    ledger = []
    for row in sorted(observed, key=lambda r: (r.run_id, r.operation_id, repr(identity(r)))):
        wanted_row = by_operation.get(row.operation_id)
        if wanted_row:
            counts["wrong_target"] += row.target_project_key != wanted_row.target_project_key
            counts["cross_talk"] += (row.caller_id, row.application_id, row.stable_session_id) != (
                wanted_row.caller_id, wanted_row.application_id, wanted_row.stable_session_id)
            counts["denied_effects"] += wanted_row.result_code != "OK" and row.effect != "none"
        counts["default_drift"] += (row.default_after != row.default_project_key
                                     or row.generation_after != row.binding_generation)
        counts["untyped_errors"] += row.result_code != "OK" and not row.result_code.startswith("SCRIBE_")
        counts["stale_fences"] += row.stale_fence_accepted
        counts["excess_reads"] += row.binding_reads > 1 or row.project_reads > 1
        counts["context_or_timing"] += ((row.result_code == "OK" and row.context_count != 1)
                                        or row.timing_envelope_count != 1)
        counts["unaccounted_calls"] += row.accounted_ratio < 0.95
        ledger.append({"expected": asdict(wanted_row) if wanted_row else None,
                       "observed": asdict(row)})
    for row in sorted(expected, key=lambda r: (r.run_id, r.operation_id, repr(identity(r)))):
        missing = wanted[identity(row)] - actual[identity(row)]
        if missing > 0:
            ledger.append({"expected": asdict(row), "observed": None})
            wanted[identity(row)] -= 1
    ledger.sort(key=lambda row: json.dumps(row, sort_keys=True))
    queue = metadata.background_queue
    for sample in queue.get("capacity_samples", ()):
        counts["excess_capacity"] += any(sample[k] > sample[f"{k}_limit"]
                                         for k in ("items", "bytes", "global", "project", "heavy"))
    # Consumers provide checkpoints from the real scheduler; this is an oracle,
    # never another implementation of scheduling or percentile measurement.
    for sample in queue.get("fairness_samples", ()):
        counts["unfairness"] += (sample["lead_units"] > 1
                                  or sample["eligible_peer_share"] > 0.5
                                  or sample["starvation_ms"] >= 5000)
    callers = {row.caller_id for row in expected} | set(metadata.set_project_count)
    counts["bind_count"] = sum(metadata.set_project_count.get(caller) != 1 for caller in callers)
    counts["teardown_leaks"] = sum(abs(n) for n in metadata.teardown_counts.values())
    return SwarmResultsV1(copy.deepcopy(metadata), tuple(ledger), counts)
