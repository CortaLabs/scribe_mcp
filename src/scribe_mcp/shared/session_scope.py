"""Runtime boundary scope and provenance contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Mapping, Optional

ScopeProvenanceLabel = Literal["verified", "claimed", "inferred", "anonymous"]


@dataclass(frozen=True)
class ScopeProvenance:
    transport_session_id: ScopeProvenanceLabel = "anonymous"
    stable_session_id: ScopeProvenanceLabel = "anonymous"
    agent_session_id: ScopeProvenanceLabel = "anonymous"
    repo_root: ScopeProvenanceLabel = "anonymous"
    project_name: ScopeProvenanceLabel = "anonymous"


@dataclass(frozen=True)
class ResolvedScope:
    transport_session_id: Optional[str]
    stable_session_id: Optional[str]
    agent_session_id: Optional[str]
    repo_root: str
    project_name: Optional[str]
    scoped_reuse_key: Optional[str]
    resolution_source: str
    trust_level: ScopeProvenanceLabel
    provenance: ScopeProvenance
    authoritative_session_key: Optional[str] = None


def build_resolved_scope(payload: Mapping[str, Any]) -> ResolvedScope:
    """Build an additive scope contract from runtime payload metadata."""
    provenance_payload = payload.get("scope_provenance")
    provenance_fields: Dict[str, ScopeProvenanceLabel] = {}
    if isinstance(provenance_payload, dict):
        for key in (
            "transport_session_id",
            "stable_session_id",
            "agent_session_id",
            "repo_root",
            "project_name",
        ):
            raw_value = provenance_payload.get(key)
            if raw_value in ("verified", "claimed", "inferred", "anonymous"):
                provenance_fields[key] = raw_value

    provenance = ScopeProvenance(**provenance_fields)
    trust_level = payload.get("trust_level")
    if trust_level not in ("verified", "claimed", "inferred", "anonymous"):
        trust_level = _infer_trust_level(provenance)

    resolution_source = payload.get("resolution_source")
    if not resolution_source:
        resolution_source = "runtime_context"

    authoritative_session_key = _as_optional_str(payload.get("stable_session_id")) or _as_optional_str(
        payload.get("session_id")
    )

    return ResolvedScope(
        transport_session_id=_as_optional_str(payload.get("transport_session_id")),
        stable_session_id=_as_optional_str(payload.get("stable_session_id")),
        agent_session_id=_as_optional_str(payload.get("agent_session_id")),
        repo_root=str(payload.get("repo_root") or ""),
        project_name=_as_optional_str(payload.get("project_name")),
        scoped_reuse_key=_as_optional_str(payload.get("scoped_reuse_key") or payload.get("scope_key")),
        resolution_source=str(resolution_source),
        trust_level=trust_level,
        provenance=provenance,
        authoritative_session_key=authoritative_session_key,
    )


def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    stringified = str(value)
    return stringified if stringified else None


def _infer_trust_level(provenance: ScopeProvenance) -> ScopeProvenanceLabel:
    if "verified" in provenance.__dict__.values():
        return "verified"
    if "claimed" in provenance.__dict__.values():
        return "claimed"
    if "inferred" in provenance.__dict__.values():
        return "inferred"
    return "anonymous"
