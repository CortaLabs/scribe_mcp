"""Request-local repository authority helpers for runtime and set_project authorization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Tuple

from scribe_mcp.config.paths import map_client_root
from scribe_mcp.config.repo_config import RepoDiscovery


@dataclass(frozen=True)
class RepoAuthoritySnapshot:
    """Minimal authority snapshot shared across runtime surfaces."""

    verified_binding_root: Optional[str]
    verified_request_root: Optional[str]
    enrolled_first_party_roots: Tuple[str, ...]
    authoritative_session_key: Optional[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "verified_binding_root": self.verified_binding_root,
            "verified_request_root": self.verified_request_root,
            "enrolled_first_party_roots": list(self.enrolled_first_party_roots),
            "authoritative_session_key": self.authoritative_session_key,
        }


class RepoAuthorityResolutionError(ValueError):
    """Structured repository authority failure."""

    def __init__(self, message: str, *, payload: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.payload = dict(payload or {})


def _request_meta_value(meta: Any, key: str) -> Optional[str]:
    if isinstance(meta, dict):
        value = meta.get(key)
    else:
        value = getattr(meta, key, None)
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _verified_binding_root(current_context: Any) -> Optional[str]:
    if current_context is None:
        return None
    resolved_scope = getattr(current_context, "resolved_scope", None)
    repo_root = getattr(resolved_scope, "repo_root", None) or getattr(current_context, "repo_root", None)
    if not repo_root:
        return None

    provenance = getattr(getattr(resolved_scope, "provenance", None), "repo_root", None)
    if provenance is None:
        scope_provenance = getattr(current_context, "scope_provenance", None)
        if isinstance(scope_provenance, dict):
            provenance = scope_provenance.get("repo_root")
    if str(provenance or "").strip().lower() != "verified":
        return None

    try:
        return str(Path(str(repo_root)).expanduser().resolve())
    except (TypeError, ValueError):
        return None


def _verified_request_root(app: Any, scribe_user: Optional[str]) -> Optional[str]:
    try:
        request_context = getattr(app, "request_context", None)
    except LookupError:
        request_context = None
    meta = getattr(request_context, "meta", None) if request_context else None
    if meta is None:
        return None

    for key in ("repo_root", "workspace_root", "cwd"):
        claim = _request_meta_value(meta, key)
        if not claim:
            continue
        mapped_path, _original = map_client_root(claim, user=scribe_user)
        try:
            mapped = Path(mapped_path).expanduser()
        except (TypeError, ValueError):
            continue
        if not mapped.is_absolute():
            continue
        candidate_root = RepoDiscovery.find_repo_root(mapped)
        if candidate_root and candidate_root.exists():
            return str(candidate_root.resolve())
    return None


def build_repo_authority_snapshot(
    *,
    current_context: Any,
    app: Any,
    scribe_user: Optional[str],
    authoritative_session_key: Optional[str],
    enrolled_first_party_roots: Optional[Tuple[str, ...]] = None,
) -> RepoAuthoritySnapshot:
    """Build request-local authority snapshot for runtime context wiring."""

    return RepoAuthoritySnapshot(
        verified_binding_root=_verified_binding_root(current_context),
        verified_request_root=_verified_request_root(app, scribe_user),
        enrolled_first_party_roots=enrolled_first_party_roots or tuple(),
        authoritative_session_key=authoritative_session_key,
    )


def _normalize_root_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    try:
        return str(Path(rendered).expanduser().resolve())
    except (TypeError, ValueError):
        return None


def _normalize_explicit_root(
    *,
    root: str,
    base_root: Path,
    scribe_user: Optional[str],
) -> tuple[Path, Optional[str], Path]:
    candidate = Path(root).expanduser()
    if not candidate.is_absolute():
        candidate = (base_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    mapped_root, original_client_root = map_client_root(str(candidate), user=scribe_user)
    mapped_path = Path(mapped_root).expanduser().resolve()
    discovered_root = RepoDiscovery.find_repo_root(mapped_path)
    if discovered_root is None or not discovered_root.exists():
        raise RepoAuthorityResolutionError(
            "Explicit root must resolve to a local repository root before authorization.",
            payload={
                "reason_code": "explicit_root_not_local_repo",
                "requested_root": root,
                "resolved_root": str(mapped_path),
                "mapped_client_root": original_client_root,
                "suggestion": "Provide a repository root path or issue authorize_repo_root for sanctioned external access.",
            },
        )
    return discovered_root.resolve(), original_client_root, mapped_path


def _first_party_match(
    normalized_root: Path,
    snapshot: RepoAuthoritySnapshot,
) -> tuple[Optional[str], Optional[str]]:
    normalized = str(normalized_root)
    verified_request = _normalize_root_value(snapshot.verified_request_root)
    if verified_request and normalized == verified_request:
        return "verified_request_root", "first_party_verified_request_root_match"
    verified_binding = _normalize_root_value(snapshot.verified_binding_root)
    if verified_binding and normalized == verified_binding:
        return "verified_binding_root", "first_party_verified_binding_root_match"
    enrolled = {
        candidate
        for item in snapshot.enrolled_first_party_roots
        if (candidate := _normalize_root_value(item))
    }
    if normalized in enrolled:
        return "enrolled_first_party_roots", "first_party_enrolled_root_match"
    return None, None


def project_root_is_first_party(
    *,
    project_root: Optional[str],
    snapshot: RepoAuthoritySnapshot,
) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Return first-party visibility decision for discovery surfaces."""
    normalized_value = _normalize_root_value(project_root)
    if not normalized_value:
        return False, None, None, None

    normalized_root = Path(normalized_value)
    authority_source, reason_code = _first_party_match(normalized_root, snapshot)
    if authority_source and reason_code:
        return True, authority_source, reason_code, str(normalized_root)
    return False, None, None, str(normalized_root)


async def resolve_authorized_project_root(
    *,
    root: Optional[str],
    skip_validation: bool,
    grant_id: Optional[str],
    snapshot: RepoAuthoritySnapshot,
    base_root: Path,
    scribe_user: Optional[str],
    validate_repo_root_grant: Callable[
        [Any, str, str, Optional[str]],
        Awaitable[tuple[bool, dict[str, Any]]],
    ],
    storage_backend: Any,
) -> tuple[Path, dict[str, Any]]:
    """Authorize and resolve project root from verified snapshot + grant validator."""
    if not root:
        binding_root = _normalize_root_value(snapshot.verified_binding_root)
        if not binding_root:
            raise RepoAuthorityResolutionError(
                "Explicit trusted project root required. Omitted root may reuse only a verified active runtime binding.",
                payload={
                    "reason_code": "missing_root_without_verified_runtime_binding",
                    "authority_source": "none",
                    "verified_binding_root": snapshot.verified_binding_root,
                    "verified_request_root": snapshot.verified_request_root,
                    "enrolled_first_party_roots": list(snapshot.enrolled_first_party_roots),
                    "authoritative_session_key": snapshot.authoritative_session_key,
                },
            )
        resolved = Path(binding_root)
        return resolved, {
            "skip_validation_requested": bool(skip_validation),
            "compatibility_override_used": False,
            "authorization_mode": "first_party",
            "authority_source": "verified_binding_root",
            "reason_code": "first_party_verified_binding_root_match",
            "resolved_root": str(resolved),
            "authoritative_session_key": snapshot.authoritative_session_key,
            "verified_binding_root": snapshot.verified_binding_root,
            "verified_request_root": snapshot.verified_request_root,
            "enrolled_first_party_roots": list(snapshot.enrolled_first_party_roots),
        }

    normalized_root, mapped_client_root, mapped_path = _normalize_explicit_root(
        root=root,
        base_root=base_root,
        scribe_user=scribe_user,
    )
    authority_source, reason_code = _first_party_match(normalized_root, snapshot)
    if authority_source and reason_code:
        return normalized_root, {
            "skip_validation_requested": bool(skip_validation),
            "compatibility_override_used": False,
            "authorization_mode": "first_party",
            "authority_source": authority_source,
            "reason_code": reason_code,
            "resolved_root": str(normalized_root),
            "mapped_root": str(mapped_path),
            "mapped_client_root": mapped_client_root,
            "verified_binding_root": snapshot.verified_binding_root,
            "verified_request_root": snapshot.verified_request_root,
            "enrolled_first_party_roots": list(snapshot.enrolled_first_party_roots),
            "authoritative_session_key": snapshot.authoritative_session_key,
        }

    # In the trusted local Council/Scribe environment, an explicit path that
    # resolves to a real local repository root is itself first-party. Keeping
    # this explicit avoids the previous half-migrated state where grant code sat
    # below an unconditional return and silently became dead.
    return normalized_root, {
        "skip_validation_requested": bool(skip_validation),
        "compatibility_override_used": False,
        "authorization_mode": "first_party",
        "authority_source": "explicit_local_repo_root",
        "reason_code": "first_party_explicit_local_repo_root",
        "resolved_root": str(normalized_root),
        "mapped_root": str(mapped_path),
        "mapped_client_root": mapped_client_root,
        "verified_binding_root": snapshot.verified_binding_root,
        "verified_request_root": snapshot.verified_request_root,
        "enrolled_first_party_roots": list(snapshot.enrolled_first_party_roots),
        "authoritative_session_key": snapshot.authoritative_session_key,
    }
