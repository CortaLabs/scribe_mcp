#!/usr/bin/env python3
"""Tests for ExecutionContext session identity requirements."""

import asyncio
import gc
import hashlib
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

import pytest

from scribe_mcp.bridges.manifest import BridgeManifest
from scribe_mcp.cli.main import (
    _load_tracked_reads,
    _normalize_tracked_path,
    _rehydrate_file_reads,
    _refresh_context_after_set_project,
    _result_is_success,
)
from scribe_mcp.config.paths import templates_dir
from scribe_mcp.cli.session_store import build_scoped_reuse_key, build_transport_session_id
from scribe_mcp.shared.execution_context import (
    AgentAttributionV1,
    AuthorizationEvidenceV1,
    BindingReceiptV1,
    ProjectTargetV1,
    ResolvedProjectTargetV1,
    ResolvedRequestContextV1,
    RouterContextManager,
    build_resolved_request_context,
)
from scribe_mcp.shared.tool_runtime import execute_tool_call, resolve_context_authoritative_session_key
from scribe_mcp.template_engine import Jinja2TemplateEngine


def _resolved_target(
    repo_root: Path,
    *,
    resolution_source: str = "project_key",
    generation: int = 3,
) -> ResolvedProjectTargetV1:
    return ResolvedProjectTargetV1(
        project_key="project-key",
        project_name="project-name",
        canonical_repo_root=str(repo_root),
        repository_id="repository-id",
        resolution_source=resolution_source,  # type: ignore[arg-type]
        default_binding_generation=generation,
    )


@pytest.mark.regression
def test_request_binding_contract_field_surfaces_are_frozen() -> None:
    assert [field.name for field in fields(ProjectTargetV1)] == [
        "project_key",
        "project",
        "repo_root",
    ]
    assert [field.name for field in fields(ResolvedProjectTargetV1)] == [
        "project_key",
        "project_name",
        "canonical_repo_root",
        "repository_id",
        "resolution_source",
        "default_binding_generation",
    ]
    assert [field.name for field in fields(AgentAttributionV1)] == ["agent", "agent_id"]
    assert [field.name for field in fields(AuthorizationEvidenceV1)] == [
        "source",
        "verified",
        "scope_refs",
    ]
    authorization_hints = get_type_hints(AuthorizationEvidenceV1)
    assert authorization_hints["source"] is str
    assert authorization_hints["verified"] is bool
    assert authorization_hints["scope_refs"] == tuple[str, ...]
    assert [field.name for field in fields(BindingReceiptV1)] == [
        "ok",
        "caller_session_key_hash",
        "project_key",
        "project_name",
        "canonical_repo_root",
        "binding_generation",
        "binding_reused",
        "persistent_write_performed",
        "resolution_source",
        "correlation_id",
    ]
    assert [field.name for field in fields(ResolvedRequestContextV1)] == [
        "caller_session_key_hash",
        "resolved_target",
        "default_binding_generation",
        "agent_attribution",
        "correlation_id",
        "operating_mode",
        "authorization_evidence",
    ]


@pytest.mark.regression
def test_project_target_v1_is_frozen_and_normalizes_selectors(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    assert ProjectTargetV1() == ProjectTargetV1()
    target = ProjectTargetV1(
        project_key=" project-key ",
        project=" project-name ",
        repo_root=str(repo_root / "."),
    )

    assert target.project_key == "project-key"
    assert target.project == "project-name"
    assert target.repo_root == str(repo_root.resolve())
    with pytest.raises(FrozenInstanceError):
        target.project = "other"  # type: ignore[misc]


@pytest.mark.regression
@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    [
        ({"project_key": " "}, ValueError),
        ({"project": " "}, ValueError),
        ({"repo_root": "/tmp/repo"}, ValueError),
        ({"project": "demo", "repo_root": "relative/repo"}, ValueError),
        ({"project_key": 7}, TypeError),
    ],
)
def test_project_target_v1_rejects_invalid_selectors(kwargs, error_type) -> None:
    with pytest.raises(error_type):
        ProjectTargetV1(**kwargs)


@pytest.mark.regression
@pytest.mark.parametrize(
    "resolution_source",
    ["project_key", "name_and_root", "unique_name", "caller_default"],
)
def test_resolved_project_target_v1_accepts_only_frozen_sources(
    tmp_path: Path,
    resolution_source: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    target = _resolved_target(repo_root / ".", resolution_source=resolution_source)

    assert target.canonical_repo_root == str(repo_root.resolve())
    assert target.resolution_source == resolution_source
    assert target.default_binding_generation == 3
    with pytest.raises(FrozenInstanceError):
        target.project_key = "other"  # type: ignore[misc]


@pytest.mark.regression
@pytest.mark.parametrize("generation", [0, -1, True, 1.5])
def test_resolved_project_target_v1_rejects_invalid_generations(
    tmp_path: Path,
    generation,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _resolved_target(tmp_path, generation=generation)


@pytest.mark.regression
def test_resolved_project_target_v1_rejects_invalid_source_and_identifiers(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="resolution_source"):
        _resolved_target(tmp_path, resolution_source="ambient")
    with pytest.raises(ValueError, match="project_key"):
        ResolvedProjectTargetV1(" ", "name", str(tmp_path), "repo", "project_key", 1)
    with pytest.raises(ValueError, match="project_name"):
        ResolvedProjectTargetV1("key", " ", str(tmp_path), "repo", "project_key", 1)
    with pytest.raises(ValueError, match="repository_id"):
        ResolvedProjectTargetV1("key", "name", str(tmp_path), " ", "project_key", 1)
    with pytest.raises(ValueError, match="absolute"):
        ResolvedProjectTargetV1("key", "name", "relative", "repo", "project_key", 1)


@pytest.mark.regression
def test_attribution_and_authorization_values_are_frozen_and_finalized() -> None:
    first = AgentAttributionV1(agent=" forge ", agent_id=" display ")
    second = AgentAttributionV1(agent="quill", agent_id="different")
    scope_refs = [" scope:one ", "scope:two"]
    evidence = AuthorizationEvidenceV1(" server ", True, scope_refs)  # type: ignore[arg-type]

    assert first.agent == "forge"
    assert first.agent_id == "display"
    assert first == second
    assert hash(first) == hash(second)
    assert evidence.source == "server"
    assert evidence.scope_refs == ("scope:one", "scope:two")
    scope_refs.append("scope:three")
    assert evidence.scope_refs == ("scope:one", "scope:two")
    with pytest.raises(FrozenInstanceError):
        first.agent = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        evidence.verified = False  # type: ignore[misc]


@pytest.mark.regression
@pytest.mark.parametrize(
    "factory",
    [
        lambda: AgentAttributionV1(" "),
        lambda: AgentAttributionV1("forge", " "),
        lambda: AuthorizationEvidenceV1(" ", True, ()),
        lambda: AuthorizationEvidenceV1("server", 1, ()),
        lambda: AuthorizationEvidenceV1("server", True, "scope"),
        lambda: AuthorizationEvidenceV1("server", True, (" ",)),
    ],
)
def test_attribution_and_authorization_reject_invalid_values(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


@pytest.mark.regression
@pytest.mark.parametrize(
    ("source", "scope_refs"),
    [
        ("Bearer live-access-token", ()),
        ("Basic dXNlcjpwYXNzd29yZA==", ()),
        ("api_key=live-secret", ()),
        ("server", ("scope=live-secret",)),
        ("server", (f"scope:sk-{'a' * 24}",)),
        ("server", (f"scope:AKIA{'A' * 16}",)),
        ("server", (f"scope:AIza{'a' * 35}",)),
        ("server", (f"scope:ghp_{'a' * 24}",)),
        ("server", (f"scope:glpat-{'a' * 24}",)),
        ("server", (f"scope:xoxb-{'a' * 24}",)),
        ("server", ("scope:eyJhbGciOiJIUzI1NiJ9.payload.signature",)),
    ],
)
def test_authorization_evidence_rejects_credential_shaped_material(
    source: str,
    scope_refs: tuple[str, ...],
) -> None:
    rejected_value = source if source != "server" else scope_refs[0]
    with pytest.raises(ValueError, match="opaque authorization reference") as exc_info:
        AuthorizationEvidenceV1(source, True, scope_refs)

    assert rejected_value not in str(exc_info.value)
    assert rejected_value not in repr(exc_info.value)


@pytest.mark.regression
def test_authorization_evidence_rejection_does_not_echo_secret() -> None:
    secret = "Bearer do-not-echo-this-secret"
    with pytest.raises(ValueError) as exc_info:
        AuthorizationEvidenceV1(secret, True, ())

    assert secret not in str(exc_info.value)


@pytest.mark.regression
def test_authorization_evidence_valid_references_are_repr_hidden(tmp_path: Path) -> None:
    evidence = AuthorizationEvidenceV1(
        "server_verified",
        True,
        (
            "scope:project",
            "scope:key",
            "grant:abc-123",
            "policy:read/key",
            "metadata:value",
        ),
    )
    context = build_resolved_request_context(
        caller_session_key="caller",
        resolved_target=_resolved_target(tmp_path),
        agent_attribution=AgentAttributionV1("forge"),
        correlation_id="correlation",
        operating_mode="project",
        authorization_evidence=evidence,
    )

    assert evidence.source == "server_verified"
    assert isinstance(evidence.source, str)
    assert evidence.scope_refs == (
        "scope:project",
        "scope:key",
        "grant:abc-123",
        "policy:read/key",
        "metadata:value",
    )
    assert repr(evidence) == "AuthorizationEvidenceV1(verified=True)"
    assert "server_verified" not in repr(context)
    assert "scope:project" not in repr(context)
    assert "grant:abc-123" not in repr(context)
    assert "policy:read/key" not in repr(context)
    assert "metadata:value" not in repr(context)


@pytest.mark.regression
def test_binding_receipt_v1_is_frozen_normalized_and_redacted(tmp_path: Path) -> None:
    digest = "AB" * 32
    receipt = BindingReceiptV1(
        ok=True,
        caller_session_key_hash=digest,
        project_key=" project-key ",
        project_name=" project-name ",
        canonical_repo_root=str(tmp_path),
        binding_generation=1,
        binding_reused=False,
        persistent_write_performed=True,
        resolution_source="set_project",
        correlation_id=" correlation ",
    )

    assert receipt.caller_session_key_hash == digest.lower()
    assert receipt.canonical_repo_root == str(tmp_path.resolve())
    assert receipt.correlation_id == "correlation"
    assert not hasattr(receipt, "__dict__")
    with pytest.raises(FrozenInstanceError):
        receipt.binding_generation = 2  # type: ignore[misc]


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("ok", 1),
        ("caller_session_key_hash", "not-a-digest"),
        ("project_key", " "),
        ("project_name", " "),
        ("canonical_repo_root", "relative"),
        ("binding_generation", 0),
        ("binding_generation", True),
        ("binding_reused", 1),
        ("persistent_write_performed", 0),
        ("resolution_source", "caller_default"),
        ("correlation_id", " "),
    ],
)
def test_binding_receipt_v1_rejects_invalid_values(
    tmp_path: Path,
    field_name: str,
    value,
) -> None:
    values = {
        "ok": True,
        "caller_session_key_hash": "ab" * 32,
        "project_key": "project-key",
        "project_name": "project-name",
        "canonical_repo_root": str(tmp_path),
        "binding_generation": 1,
        "binding_reused": False,
        "persistent_write_performed": True,
        "resolution_source": "set_project",
        "correlation_id": "correlation",
    }
    values[field_name] = value
    with pytest.raises((TypeError, ValueError)):
        BindingReceiptV1(**values)


@pytest.mark.regression
@pytest.mark.parametrize("operating_mode", ["project", "sentinel"])
def test_resolved_request_context_builder_hashes_once_and_preserves_identity(
    tmp_path: Path,
    operating_mode: str,
) -> None:
    caller_session_key = " raw server-owned caller key "
    target = _resolved_target(tmp_path)
    attribution = AgentAttributionV1("forge", "display-id")
    evidence = AuthorizationEvidenceV1("server", True, ("scope:one",))

    context = build_resolved_request_context(
        caller_session_key=caller_session_key,
        resolved_target=target,
        agent_attribution=attribution,
        correlation_id="correlation",
        operating_mode=operating_mode,  # type: ignore[arg-type]
        authorization_evidence=evidence,
    )

    assert context.caller_session_key_hash == hashlib.sha256(
        caller_session_key.encode("utf-8")
    ).hexdigest()
    assert caller_session_key not in repr(context)
    assert context.resolved_target is target
    assert context.default_binding_generation == target.default_binding_generation
    assert context.agent_attribution == attribution
    assert context.agent_attribution is not attribution
    assert context.authorization_evidence == evidence
    assert context.authorization_evidence is not evidence
    assert context.authorization_evidence.scope_refs is not evidence.scope_refs
    with pytest.raises(FrozenInstanceError):
        context.operating_mode = "sentinel"  # type: ignore[misc]


@pytest.mark.regression
def test_resolved_request_context_rejects_invalid_values(tmp_path: Path) -> None:
    target = _resolved_target(tmp_path)
    attribution = AgentAttributionV1("forge")
    evidence = AuthorizationEvidenceV1("server", True, ())
    valid = {
        "caller_session_key_hash": "ab" * 32,
        "resolved_target": target,
        "default_binding_generation": target.default_binding_generation,
        "agent_attribution": attribution,
        "correlation_id": "correlation",
        "operating_mode": "project",
        "authorization_evidence": evidence,
    }
    invalid = [
        {"caller_session_key_hash": "bad"},
        {"resolved_target": object()},
        {"default_binding_generation": target.default_binding_generation + 1},
        {"agent_attribution": object()},
        {"correlation_id": " "},
        {"operating_mode": "ambient"},
        {"authorization_evidence": object()},
    ]

    for replacement in invalid:
        with pytest.raises((TypeError, ValueError)):
            ResolvedRequestContextV1(**(valid | replacement))
    with pytest.raises(ValueError, match="operating_mode"):
        build_resolved_request_context(
            caller_session_key="caller",
            resolved_target=target,
            agent_attribution=attribution,
            correlation_id="correlation",
            operating_mode="ambient",  # type: ignore[arg-type]
            authorization_evidence=evidence,
        )


@pytest.mark.regression
@pytest.mark.parametrize(
    "overrides",
    [
        {"caller_session_key": " "},
        {"caller_session_key": 7},
        {"resolved_target": object()},
        {"agent_attribution": object()},
        {"authorization_evidence": object()},
    ],
)
def test_resolved_request_context_builder_rejects_invalid_inputs(
    tmp_path: Path,
    overrides,
) -> None:
    values = {
        "caller_session_key": "caller",
        "resolved_target": _resolved_target(tmp_path),
        "agent_attribution": AgentAttributionV1("forge"),
        "correlation_id": "correlation",
        "operating_mode": "project",
        "authorization_evidence": AuthorizationEvidenceV1("server", True, ()),
    }
    with pytest.raises((TypeError, ValueError)):
        build_resolved_request_context(**(values | overrides))


@pytest.mark.regression
@pytest.mark.asyncio
async def test_execution_context_resolved_request_context_is_optional_and_stable(
    tmp_path: Path,
) -> None:
    router = RouterContextManager()
    execution_context = await router.build_execution_context(
        {
            "repo_root": str(tmp_path),
            "mode": "project",
            "intent": "tool:test",
            "affected_dev_projects": [],
            "session_id": "session-id",
        }
    )
    resolved_context = build_resolved_request_context(
        caller_session_key="caller",
        resolved_target=_resolved_target(tmp_path),
        agent_attribution=AgentAttributionV1("forge"),
        correlation_id="correlation",
        operating_mode="project",
        authorization_evidence=AuthorizationEvidenceV1("server", True, ()),
    )

    assert execution_context.resolved_request_context is None
    finalized = replace(execution_context, resolved_request_context=resolved_context)
    assert finalized.resolved_request_context is resolved_context
    token = router.set_current(finalized)
    try:
        assert router.get_current() is finalized
        assert router.get_current().resolved_request_context is resolved_context
    finally:
        router.reset(token)


@pytest.mark.asyncio
async def test_execution_context_requires_session_id():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
    }
    with pytest.raises(ValueError, match="transport_session_id or session_id"):
        await router.build_execution_context(payload)


@pytest.mark.asyncio
async def test_execution_context_transport_session_id_is_stable():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "transport_session_id": "conn-1",
    }
    first = await router.build_execution_context(payload)
    second = await router.build_execution_context(payload)
    assert first.session_id == second.session_id
    assert first.transport_session_id == "conn-1"


@pytest.mark.asyncio
async def test_execution_context_transport_scope_changes_with_project_binding():
    router = RouterContextManager()
    repo_root = Path("/tmp/repo")
    transport_project_a = build_transport_session_id(
        repo_root,
        "session-main",
        "codex",
        project_name="project-a",
    )
    transport_project_b = build_transport_session_id(
        repo_root,
        "session-main",
        "codex",
        project_name="project-b",
    )

    assert transport_project_a != transport_project_b

    payload_a = {
        "repo_root": str(repo_root),
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "transport_session_id": transport_project_a,
    }
    payload_b = {
        "repo_root": str(repo_root),
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "transport_session_id": transport_project_b,
    }
    first = await router.build_execution_context(payload_a)
    second = await router.build_execution_context(payload_b)
    assert first.session_id != second.session_id


@pytest.mark.asyncio
async def test_execution_context_transport_scope_includes_repo_root_boundary():
    router = RouterContextManager()
    transport_repo_one = build_transport_session_id(
        Path("/tmp/repo-one"),
        "session-main",
        "codex",
        project_name="project-a",
    )
    transport_repo_two = build_transport_session_id(
        Path("/tmp/repo-two"),
        "session-main",
        "codex",
        project_name="project-a",
    )

    assert transport_repo_one != transport_repo_two


@pytest.mark.asyncio
async def test_execution_context_accepts_explicit_session_id():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "session_id": "session-explicit",
    }
    ctx = await router.build_execution_context(payload)
    assert ctx.session_id == "session-explicit"


@pytest.mark.asyncio
async def test_execution_context_prefers_transport_identity_over_claimed_session_id():
    router = RouterContextManager()
    payload_with_claim = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "session_id": "caller-session",
        "transport_session_id": "transport-claimed",
    }
    payload_transport_only = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "transport_session_id": "transport-claimed",
    }

    with_claim = await router.build_execution_context(payload_with_claim)
    transport_only = await router.build_execution_context(payload_transport_only)

    assert with_claim.transport_session_id == "transport-claimed"
    assert with_claim.session_id == transport_only.session_id
    assert with_claim.session_id != "caller-session"


@pytest.mark.asyncio
async def test_execution_context_exposes_resolved_scope_provenance():
    router = RouterContextManager()
    payload = {
        "repo_root": "/tmp/repo",
        "mode": "project",
        "intent": "tool:test",
        "affected_dev_projects": [],
        "session_id": "context-session-123",
        "transport_session_id": "transport-abc",
        "stable_session_id": "stable-session-456",
        "agent_session_id": "agent-session-999",
        "project_name": "demo-project",
        "scoped_reuse_key": "reuse-key-1",
        "resolution_source": "runtime_context",
        "trust_level": "verified",
        "scope_provenance": {
            "transport_session_id": "claimed",
            "stable_session_id": "verified",
            "agent_session_id": "verified",
            "repo_root": "verified",
            "project_name": "claimed",
        },
    }
    ctx = await router.build_execution_context(payload)

    assert ctx.resolved_scope is not None
    assert ctx.session_id == "context-session-123"
    assert ctx.resolved_scope.transport_session_id == "transport-abc"
    assert ctx.resolved_scope.stable_session_id == "stable-session-456"
    assert ctx.resolved_scope.agent_session_id == "agent-session-999"
    assert ctx.resolved_scope.authoritative_session_key == "stable-session-456"
    assert ctx.resolved_scope.stable_session_id != ctx.session_id
    assert ctx.resolved_scope.agent_session_id != ctx.resolved_scope.stable_session_id
    assert ctx.resolved_scope.scoped_reuse_key == "reuse-key-1"
    assert ctx.resolved_scope.provenance.transport_session_id == "claimed"
    assert ctx.resolved_scope.provenance.stable_session_id == "verified"
    assert ctx.resolved_scope.provenance.agent_session_id == "verified"
    assert ctx.authoritative_session_key == "stable-session-456"


@pytest.mark.asyncio
async def test_execute_tool_call_public_release_nested_reuses_server_owned_session() -> None:
    router = RouterContextManager()
    seed_context = await router.build_execution_context(
        {
            "repo_root": "/tmp/repo",
            "mode": "project",
            "intent": "tool:seed",
            "affected_dev_projects": [],
            "public_release": True,
            "transport_session_id": "process:seed",
        }
    )
    token = router.set_current(seed_context)
    observed: dict[str, str] = {}

    def capture(agent: str) -> str:
        current = router.get_current()
        assert current is not None
        observed["session_id"] = current.session_id
        observed["authoritative_session_key"] = str(current.authoritative_session_key or "")
        return agent

    try:
        result = await execute_tool_call(
            name="capture",
            arguments={"agent": "codex", "context": {"repo_root": "/tmp/repo", "mode": "project"}},
            kwargs={},
            registry={"capture": capture},
            app=SimpleNamespace(request_context=None),
            storage_backend=None,
            settings=SimpleNamespace(project_root=Path("/tmp/repo"), public_release=True),
            state_manager=SimpleNamespace(load=lambda: None),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"capture"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
    finally:
        router.reset(token)

    assert result == "codex"
    assert observed["session_id"] == seed_context.session_id
    assert observed["authoritative_session_key"] == seed_context.session_id


def test_resolve_context_authoritative_session_key_ignores_transport_only_identity() -> None:
    context = SimpleNamespace(
        transport_session_id="transport-only",
        resolved_scope=SimpleNamespace(
            transport_session_id="transport-only",
            authoritative_session_key=None,
            stable_session_id=None,
        ),
    )

    assert resolve_context_authoritative_session_key(context) is None


def test_refresh_context_after_set_project_marks_repo_scope_verified(tmp_path: Path) -> None:
    context = {
        "repo_root": str(tmp_path),
        "scope_provenance": {
            "project_name": "claimed",
            "repo_root": "claimed",
        },
        "session_scope_state": "pre_binding",
    }
    result = {
        "ok": True,
        "project": {
            "name": "demo_docs",
            "root": str(tmp_path),
        },
    }

    _refresh_context_after_set_project(
        context=context,
        result=result,
        repo_root=tmp_path,
    )

    assert context["project_name"] == "demo_docs"
    assert context["repo_root"] == str(tmp_path.resolve())
    assert context["scope_provenance"]["project_name"] == "verified"
    assert context["scope_provenance"]["repo_root"] == "verified"
    assert context["session_scope_state"] == "project_bound"
    assert context["scoped_reuse_key"] == f"{tmp_path.resolve()}:demo_docs"
    assert context["session_reuse_scope"] == f"{tmp_path.resolve()}:demo_docs"


class _DummyRuntimeRouter:
    _process_instance_id = "proc-test"

    async def get_or_create_session_id(self, _transport_session_id: str) -> str:
        return "session-1"

    async def build_execution_context(self, payload):
        return SimpleNamespace(mode=payload.get("mode", "project"), stable_session_id="stable-1")

    def set_current(self, _exec_context):
        return "token-1"

    def reset(self, _token):
        return None

    async def get_cached_project(self, _stable_session_id: str):
        return "cached-project"

    def get_current(self):
        return SimpleNamespace(
            session_id="session-1",
            stable_session_id="stable-1",
            resolved_scope=SimpleNamespace(
                repo_root="/tmp",
                project_name="cached-project",
                transport_session_id=None,
                stable_session_id="stable-1",
            ),
        )


class _CachingRuntimeRouter(_DummyRuntimeRouter):
    def __init__(self) -> None:
        self._stable_cache: dict[str, str] = {}

    async def get_cached_agent_session_id(self, identity_key: str) -> str | None:
        return self._stable_cache.get(identity_key)

    async def cache_agent_session_id(self, identity_key: str, session_id: str) -> None:
        self._stable_cache[identity_key] = session_id


class _DummyState:
    @staticmethod
    def get_session_mode(_session_id: str):
        return None


class _DummyStateManager:
    async def load(self):
        return _DummyState()


class _CountingStorageBackend:
    def __init__(self) -> None:
        self.calls = 0

    async def get_or_create_agent_session(self, **_kwargs):
        self.calls += 1
        return "stable-1"


class _ScopeBoundaryStorageBackend:
    async def get_session_by_transport(self, _transport_session_id: str) -> dict[str, str]:
        return {"session_id": "stable-session-42", "repo_root": "/tmp"}

    async def upsert_session(self, **_kwargs) -> None:
        return None

    async def get_or_create_agent_session(self, **_kwargs) -> str:
        return "agent-session-77"

    async def get_last_agent_session_allocation(self, _identity_key: str) -> dict[str, str]:
        return {
            "status": "allocated",
            "scoped_reuse_key": "/tmp:__prebinding__",
        }

    async def get_session_mode(self, _session_id: str) -> str:
        return "project"

    async def fetch_project(self, _project_name: str):
        return None

    async def get_session_project(self, _session_id: str):
        return None


class _RuntimePreferredStorageBackend:
    def __init__(self) -> None:
        self.lookup_order: list[str] = []

    async def get_session_by_transport(self, transport_session_id: str) -> dict[str, str]:
        self.lookup_order.append(transport_session_id)
        return {"session_id": f"stable:{transport_session_id}", "repo_root": "/tmp"}

    async def upsert_session(self, **_kwargs) -> None:
        return None

    async def get_or_create_agent_session(self, **_kwargs) -> str:
        return "agent-runtime"

    async def get_last_agent_session_allocation(self, _identity_key: str) -> dict[str, str]:
        return {
            "status": "allocated",
            "session_id": "agent-runtime",
            "scoped_reuse_key": "/tmp:__prebinding__",
        }

    async def get_session_mode(self, _session_id: str) -> str:
        return "project"

    async def fetch_project(self, _project_name: str):
        return None

    async def get_session_project(self, _session_id: str):
        return None


def _bind_verified_repo_context(
    router: RouterContextManager,
    *,
    repo_root: str = "/tmp",
    project_name: str | None = None,
    session_id: str | None = None,
    stable_session_id: str | None = None,
):
    return router.set_current(
        SimpleNamespace(
            session_id=session_id,
            stable_session_id=stable_session_id,
            execution_id="parent-exec-verified",
            resolved_scope=SimpleNamespace(
                repo_root=repo_root,
                project_name=project_name,
                transport_session_id=None,
                stable_session_id=stable_session_id,
            ),
        )
    )


@pytest.mark.asyncio
async def test_execute_tool_call_does_not_inject_project_to_set_project():
    def set_project_stub(agent: str, name: str, root: str) -> dict[str, str]:
        return {"agent": agent, "name": name, "root": root}

    result = await execute_tool_call(
        name="set_project",
        arguments={"agent": "codex", "name": "demo", "root": "/tmp/demo"},
        kwargs={},
        registry={"set_project": set_project_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(project_root=Path("/tmp")),
        state_manager=_DummyStateManager(),
        router_context_manager=_DummyRuntimeRouter(),
        sentinel_only=set(),
        sentinel_allowed={"set_project"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == {"agent": "codex", "name": "demo", "root": "/tmp/demo"}


@pytest.mark.asyncio
async def test_execute_tool_call_injects_project_for_project_aware_tool():
    def read_recent_stub(agent: str, project: str | None = None) -> str | None:
        return project

    result = await execute_tool_call(
        name="read_recent",
        arguments={"agent": "codex"},
        kwargs={"context": {"repo_root": "/tmp"}},
        registry={"read_recent": read_recent_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(project_root=Path("/tmp")),
        state_manager=_DummyStateManager(),
        router_context_manager=_DummyRuntimeRouter(),
        sentinel_only=set(),
        sentinel_allowed={"read_recent"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == "cached-project"


@pytest.mark.asyncio
async def test_execute_tool_call_allows_scribe_doctor_in_sentinel_mode():
    def scribe_doctor_stub(agent: str) -> dict[str, str]:
        return {"agent": agent, "status": "ok"}

    result = await execute_tool_call(
        name="scribe_doctor",
        arguments={"agent": "codex"},
        kwargs={"context": {"repo_root": "/tmp", "mode": "sentinel", "session_id": "session-1"}},
        registry={"scribe_doctor": scribe_doctor_stub},
        app=SimpleNamespace(request_context=None),
        storage_backend=None,
        settings=SimpleNamespace(project_root=Path("/tmp")),
        state_manager=_DummyStateManager(),
        router_context_manager=_DummyRuntimeRouter(),
        sentinel_only=set(),
        sentinel_allowed={"scribe_doctor"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == {"agent": "codex", "status": "ok"}


@pytest.mark.asyncio
async def test_execute_tool_call_reports_helpful_error_for_blocked_sentinel_tool():
    def manage_docs_stub(agent: str) -> dict[str, str]:
        return {"agent": agent}

    with pytest.raises(
        ValueError,
        match=r"Tool 'manage_docs' requires an active Scribe project\. "
        r"No project is active in sentinel mode; run set_project first\.",
    ):
        await execute_tool_call(
            name="manage_docs",
            arguments={"agent": "codex"},
            kwargs={"context": {"repo_root": "/tmp", "mode": "sentinel", "session_id": "session-1"}},
            registry={"manage_docs": manage_docs_stub},
            app=SimpleNamespace(request_context=None),
            storage_backend=None,
            settings=SimpleNamespace(project_root=Path("/tmp")),
            state_manager=_DummyStateManager(),
            router_context_manager=_DummyRuntimeRouter(),
            sentinel_only=set(),
            sentinel_allowed={"scribe_doctor"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )


@pytest.mark.asyncio
async def test_execute_tool_call_reuses_cached_stable_session_id():
    observed_statuses: list[str | None] = []

    def noop_stub(agent: str) -> str:
        current = router.get_current()
        assert current is not None
        observed_statuses.append(current.session_reuse_status)
        return agent

    router = RouterContextManager()
    backend = _CountingStorageBackend()
    token = _bind_verified_repo_context(router)

    try:
        result_one = await execute_tool_call(
            name="noop",
            arguments={"agent": "codex"},
            kwargs={"context": {"mode": "project", "session_id": "session-1"}},
            registry={"noop": noop_stub},
            app=SimpleNamespace(request_context=None),
            storage_backend=backend,
            settings=SimpleNamespace(project_root=Path("/tmp")),
            state_manager=_DummyStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"noop"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )

        result_two = await execute_tool_call(
            name="noop",
            arguments={"agent": "codex"},
            kwargs={"context": {"mode": "project", "session_id": "session-1"}},
            registry={"noop": noop_stub},
            app=SimpleNamespace(request_context=None),
            storage_backend=backend,
            settings=SimpleNamespace(project_root=Path("/tmp")),
            state_manager=_DummyStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"noop"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
    finally:
        router.reset(token)

    assert result_one == "codex"
    assert result_two == "codex"
    assert backend.calls == 1
    assert observed_statuses == ["allocated", "cache_hit_unverified"]


@pytest.mark.asyncio
async def test_execute_tool_call_boundary_reports_distinct_session_id_surfaces():
    router = RouterContextManager(storage_backend=_ScopeBoundaryStorageBackend())
    observed = {}
    token = _bind_verified_repo_context(router)

    def capture_scope_stub(agent: str) -> str:
        current = router.get_current()
        assert current is not None
        observed["transport_session_id"] = current.resolved_scope.transport_session_id
        observed["stable_session_id"] = current.resolved_scope.stable_session_id
        observed["agent_session_id"] = current.resolved_scope.agent_session_id
        observed["scoped_reuse_key"] = current.resolved_scope.scoped_reuse_key
        observed["resolution_source"] = current.resolved_scope.resolution_source
        observed["trust_level"] = current.resolved_scope.trust_level
        observed["agent_session_provenance"] = current.resolved_scope.provenance.agent_session_id
        observed["session_reuse_status"] = current.session_reuse_status
        observed["session_reuse_scope"] = current.session_reuse_scope
        return agent

    try:
        result = await execute_tool_call(
            name="capture_scope",
            arguments={"agent": "codex"},
            kwargs={
                "context": {
                    "mode": "project",
                    "transport_session_id": "transport-req-1",
                }
            },
            registry={"capture_scope": capture_scope_stub},
            app=SimpleNamespace(request_context=None),
            storage_backend=_ScopeBoundaryStorageBackend(),
            settings=SimpleNamespace(project_root=Path("/tmp")),
            state_manager=_DummyStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"capture_scope"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
    finally:
        router.reset(token)

    assert result == "codex"
    # Transport identity is actor-scoped: the connection id is namespaced by
    # the calling agent so concurrent actors on one connection stay isolated.
    assert observed["transport_session_id"] == "transport-req-1::actor=codex"
    assert observed["stable_session_id"] == "stable-session-42"
    assert observed["agent_session_id"] == "agent-session-77"
    assert observed["scoped_reuse_key"] == "/tmp:__prebinding__"
    assert observed["resolution_source"] == "runtime_context"
    assert observed["trust_level"] == "verified"
    assert observed["agent_session_provenance"] == "verified"
    assert observed["session_reuse_status"] == "allocated"
    assert observed["session_reuse_scope"] == "/tmp:__prebinding__"


@pytest.mark.asyncio
async def test_execute_tool_call_runtime_transport_overrides_compatibility_inputs() -> None:
    backend = _RuntimePreferredStorageBackend()
    router = RouterContextManager(storage_backend=backend)
    token = _bind_verified_repo_context(router)

    def capture_scope_stub(agent: str) -> dict[str, str | None]:
        current = router.get_current()
        assert current is not None
        assert current.resolved_scope is not None
        return {
            "agent": agent,
            "session_id": current.session_id,
            "transport_session_id": current.resolved_scope.transport_session_id,
            "transport_provenance": current.resolved_scope.provenance.transport_session_id,
        }

    try:
        result = await execute_tool_call(
            name="capture_scope",
            arguments={"agent": "codex"},
            kwargs={
                "session_id": "legacy-session-kwarg",
                "client_id": "legacy-client-kwarg",
                "connection_id": "legacy-connection-kwarg",
                "context": {
                    "mode": "project",
                    "session_id": "legacy-session-context",
                    "transport_session_id": "legacy-transport-context",
                },
            },
            registry={"capture_scope": capture_scope_stub},
            app=SimpleNamespace(
                request_context=SimpleNamespace(
                    request=SimpleNamespace(headers={"mcp-session-id": "runtime-transport-1"}),
                    meta=SimpleNamespace(client_id="runtime-client"),
                )
            ),
            storage_backend=backend,
            settings=SimpleNamespace(project_root=Path("/tmp")),
            state_manager=_DummyStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"capture_scope"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )
    finally:
        router.reset(token)

    assert result["agent"] == "codex"
    # Runtime transport wins over all compatibility inputs; the id carries the
    # actor scope so same-connection actors resolve distinct sessions.
    assert backend.lookup_order[0] == "runtime-transport-1::actor=codex"
    assert result["session_id"] == "stable:runtime-transport-1::actor=codex"
    assert result["transport_session_id"] == "runtime-transport-1::actor=codex"
    assert result["transport_provenance"] == "verified"


class _ProjectBoundReuseStorageBackend:
    def __init__(self) -> None:
        self._sessions_by_reuse_scope: dict[str, str] = {}
        self._last_allocation: dict[str, dict[str, str]] = {}
        self._counter = 0

    async def get_session_by_transport(self, _transport_session_id: str) -> dict[str, str]:
        return {"session_id": "stable-transport-session", "repo_root": "/tmp"}

    async def upsert_session(self, **_kwargs) -> None:
        return None

    async def get_or_create_agent_session(self, *, identity_key: str, repo_root: str, scope_key: str, **_kwargs) -> str:
        scoped_reuse_key = f"{repo_root}:{scope_key or '__prebinding__'}"
        existing = self._sessions_by_reuse_scope.get(scoped_reuse_key)
        if existing:
            self._last_allocation[identity_key] = {
                "status": "reused",
                "scoped_reuse_key": scoped_reuse_key,
            }
            return existing
        self._counter += 1
        session_id = f"agent-session-{self._counter}"
        self._sessions_by_reuse_scope[scoped_reuse_key] = session_id
        self._last_allocation[identity_key] = {
            "status": "allocated",
            "scoped_reuse_key": scoped_reuse_key,
        }
        return session_id

    async def get_last_agent_session_allocation(self, identity_key: str) -> dict[str, str] | None:
        return self._last_allocation.get(identity_key)

    async def get_session_mode(self, _session_id: str) -> str:
        return "project"

    async def fetch_project(self, _project_name: str):
        return SimpleNamespace(repo_root="/tmp")

    async def get_session_project(self, _session_id: str):
        return None


@pytest.mark.asyncio
async def test_execute_tool_call_project_binding_change_reallocates_with_same_transport_session():
    backend = _ProjectBoundReuseStorageBackend()
    router = RouterContextManager(storage_backend=backend)
    observed: dict[str, list[tuple[str | None, str | None, str | None]]] = {"calls": []}

    def capture_scope_stub(agent: str, project: str) -> str:
        current = router.get_current()
        assert current is not None
        observed["calls"].append(
            (
                current.resolved_scope.agent_session_id,
                current.session_reuse_status,
                current.session_reuse_scope,
            )
        )
        return agent

    common = {
        "name": "capture_scope",
        "registry": {"capture_scope": capture_scope_stub},
        "app": SimpleNamespace(request_context=None),
        "storage_backend": backend,
        "settings": SimpleNamespace(project_root=Path("/tmp")),
        "state_manager": _DummyStateManager(),
        "router_context_manager": router,
        "sentinel_only": set(),
        "sentinel_allowed": {"capture_scope"},
        "log_scope_violation_cb": lambda *_args, **_kwargs: None,
    }

    result_one = await execute_tool_call(
        **common,
        arguments={"agent": "codex", "project": "project-a"},
        kwargs={"context": {"mode": "project", "transport_session_id": "transport-stable"}},
    )
    result_two = await execute_tool_call(
        **common,
        arguments={"agent": "codex", "project": "project-b"},
        kwargs={"context": {"mode": "project", "transport_session_id": "transport-stable"}},
    )

    assert result_one == "codex"
    assert result_two == "codex"
    assert observed["calls"] == [
        ("agent-session-1", "allocated", "/tmp:project-a"),
        ("agent-session-2", "allocated", "/tmp:project-b"),
    ]


@pytest.mark.asyncio
async def test_execute_tool_call_project_binding_same_scope_reuses_session() -> None:
    backend = _ProjectBoundReuseStorageBackend()
    router = RouterContextManager(storage_backend=backend)
    observed: list[tuple[str | None, str | None, str | None]] = []

    def capture_scope_stub(agent: str, project: str) -> str:
        current = router.get_current()
        assert current is not None
        observed.append(
            (
                current.resolved_scope.agent_session_id,
                current.session_reuse_status,
                current.session_reuse_scope,
            )
        )
        return agent

    common = {
        "name": "capture_scope",
        "registry": {"capture_scope": capture_scope_stub},
        "app": SimpleNamespace(request_context=None),
        "storage_backend": backend,
        "settings": SimpleNamespace(project_root=Path("/tmp")),
        "state_manager": _DummyStateManager(),
        "router_context_manager": router,
        "sentinel_only": set(),
        "sentinel_allowed": {"capture_scope"},
        "log_scope_violation_cb": lambda *_args, **_kwargs: None,
    }

    first = await execute_tool_call(
        **common,
        arguments={"agent": "codex", "project": "project-a"},
        kwargs={"context": {"mode": "project", "transport_session_id": "transport-stable"}},
    )
    second = await execute_tool_call(
        **common,
        arguments={"agent": "codex", "project": "project-a"},
        kwargs={"context": {"mode": "project", "transport_session_id": "transport-stable"}},
    )
    third = await execute_tool_call(
        **common,
        arguments={"agent": "codex", "project": "project-b"},
        kwargs={"context": {"mode": "project", "transport_session_id": "transport-stable"}},
    )

    assert first == "codex"
    assert second == "codex"
    assert third == "codex"
    assert observed[0] == ("agent-session-1", "allocated", "/tmp:project-a")
    assert observed[1][0] == "agent-session-1"
    assert observed[1][1] in {"allocated", "reused"}
    assert observed[1][2] == "/tmp:project-a"
    assert observed[2] == ("agent-session-2", "allocated", "/tmp:project-b")


@pytest.mark.asyncio
async def test_execute_tool_call_accepts_dict_request_context_meta_transport_session_id() -> None:
    class _VerifiedProjectStorage(_ProjectBoundReuseStorageBackend):
        async def fetch_project(self, _project_name: str):
            return SimpleNamespace(repo_root="/tmp")

    backend = _VerifiedProjectStorage()
    router = RouterContextManager(storage_backend=backend)
    observed: dict[str, str | None] = {}

    def capture_scope_stub(agent: str, project: str) -> str:
        current = router.get_current()
        assert current is not None
        observed["transport_session_id"] = current.resolved_scope.transport_session_id
        return f"{agent}:{project}"

    result = await execute_tool_call(
        name="capture_scope",
        arguments={"agent": "codex", "project": "project-a"},
        kwargs={"context": {"mode": "project"}},
        registry={"capture_scope": capture_scope_stub},
        app=SimpleNamespace(
            request_context=SimpleNamespace(meta={"transport_session_id": "dict-meta-transport"})
        ),
        storage_backend=backend,
        settings=SimpleNamespace(project_root=Path("/tmp")),
        state_manager=_DummyStateManager(),
        router_context_manager=router,
        sentinel_only=set(),
        sentinel_allowed={"capture_scope"},
        log_scope_violation_cb=lambda *_args, **_kwargs: None,
    )

    assert result == "codex:project-a"
    assert observed["transport_session_id"] == "dict-meta-transport::actor=codex"


@pytest.mark.asyncio
async def test_execute_tool_call_public_release_requires_trusted_transport_identity() -> None:
    class _UnboundStorage:
        async def get_session_by_transport(self, _transport_session_id: str):
            return None

        async def fetch_project(self, _project_name: str):
            return None

        async def get_session_project(self, _session_id: str):
            return None

        async def upsert_session(self, **_kwargs):
            return None

    storage = _UnboundStorage()
    router = RouterContextManager(storage_backend=storage)

    def capture_scope_stub(agent: str) -> str:
        return agent

    with pytest.raises(
        ValueError,
        match="Public release requires trusted runtime-derived transport_session_id",
    ):
        await execute_tool_call(
            name="capture_scope",
            arguments={"agent": "codex"},
            kwargs={"context": {"repo_root": "/tmp", "mode": "project"}},
            registry={"capture_scope": capture_scope_stub},
            app=SimpleNamespace(request_context=None),
            storage_backend=storage,
            settings=SimpleNamespace(project_root=Path("/tmp"), public_release=True),
            state_manager=_DummyStateManager(),
            router_context_manager=router,
            sentinel_only=set(),
            sentinel_allowed={"capture_scope"},
            log_scope_violation_cb=lambda *_args, **_kwargs: None,
        )


def test_templates_dir_contains_builtin_documents():
    root = templates_dir()
    assert root.exists()
    assert (root / "documents" / "ARCHITECTURE_GUIDE_TEMPLATE.md").exists()


def test_template_engine_can_validate_builtin_document_templates():
    engine = Jinja2TemplateEngine(project_root=Path("/tmp"), project_name="template-probe")
    validation = engine.validate_template("documents/ARCHITECTURE_GUIDE_TEMPLATE.md")
    assert validation["valid"], validation


def test_bridge_manifest_hooks_support_keyed_config_without_hook_name_field():
    manifest = BridgeManifest.from_dict(
        {
            "bridge_id": "example_bridge",
            "name": "Example Bridge",
            "version": "1.0.0",
            "description": "Bridge",
            "author": "Scribe Team",
            "hooks": {
                "pre_append": {"callback_type": "async", "timeout_ms": 5000, "critical": False},
                "post_append": {"callback_type": "async", "timeout_ms": 5000, "critical": False},
            },
        }
    )

    assert manifest.hooks["pre_append"].hook_name == "pre_append"
    assert manifest.hooks["post_append"].hook_name == "post_append"
    assert manifest.validate() == []


def test_bridge_manifest_hooks_preserve_explicit_hook_name_override():
    manifest = BridgeManifest.from_dict(
        {
            "bridge_id": "bridge_test",
            "name": "Bridge Test",
            "version": "1.0.0",
            "description": "Bridge",
            "author": "Scribe Team",
            "hooks": {
                "pre_append": {
                    "hook_name": "pre_append_custom",
                    "callback_type": "async",
                    "timeout_ms": 5000,
                    "critical": False,
                }
            },
        }
    )

    assert manifest.hooks["pre_append"].hook_name == "pre_append_custom"


@pytest.mark.asyncio
async def test_background_service_status_tracks_success():
    from scribe_mcp import server as server_module

    server_module._background_services.clear()

    async def _work() -> None:
        await asyncio.sleep(0)

    task = server_module.schedule_background_task(
        _work(),
        service_name="unit_success",
        description="unit test successful task",
    )
    await task

    status = server_module.get_background_service_status()["unit_success"]
    assert status["status"] == "healthy"
    assert status["last_error"] is None
    assert status["last_duration_ms"] is not None


@pytest.mark.asyncio
async def test_background_service_status_tracks_failure():
    from scribe_mcp import server as server_module

    server_module._background_services.clear()

    async def _work() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("unit boom")

    task = server_module.schedule_background_task(
        _work(),
        service_name="unit_failure",
        description="unit test failing task",
    )
    with pytest.raises(RuntimeError, match="unit boom"):
        await task

    status = server_module.get_background_service_status()["unit_failure"]
    assert status["status"] == "failed"
    assert "unit boom" in (status["last_error"] or "")


@pytest.mark.asyncio
async def test_background_task_without_service_name_observes_exception():
    from scribe_mcp import server as server_module

    loop = asyncio.get_running_loop()
    captured: list[dict[str, object]] = []
    original_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: captured.append(context))

    async def _work() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("anonymous boom")

    try:
        task = server_module.schedule_background_task(_work())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert task.done()
        del task
        gc.collect()
        await asyncio.sleep(0)
    finally:
        loop.set_exception_handler(original_handler)

    assert captured == []


@pytest.mark.asyncio
async def test_drain_background_tasks_observes_anonymous_failures():
    from scribe_mcp import server as server_module

    async def _work() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("drained boom")

    task = server_module.schedule_background_task(_work())

    await server_module.drain_background_tasks()

    assert task.done()
    assert not server_module.background_tasks


def test_cli_path_tracking_normalizes_and_filters_outside_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "inside.txt").write_text("ok", encoding="utf-8")

    normalized_inside = _normalize_tracked_path(repo_root, "inside.txt")
    assert normalized_inside == str((repo_root / "inside.txt").resolve())

    assert _normalize_tracked_path(repo_root, str(tmp_path / "outside.txt")) is None


def test_cli_load_tracked_reads_deduplicates_entries(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "a.txt").write_text("a", encoding="utf-8")

    context = {
        "files_read": [
            "a.txt",
            str((repo_root / "a.txt").resolve()),
            str(tmp_path / "outside.txt"),
            42,
        ]
    }

    reads = _load_tracked_reads(context, repo_root)
    assert reads == [str((repo_root / "a.txt").resolve())]


def test_cli_result_success_detection_handles_mcp_and_tool_shapes() -> None:
    assert _result_is_success({"isError": False}) is True
    assert _result_is_success({"isError": True}) is False
    assert _result_is_success({"ok": True}) is True
    assert _result_is_success({"ok": False}) is False
    assert _result_is_success({"error": "boom"}) is False


@pytest.mark.asyncio
async def test_cli_rehydrate_file_reads_replays_paths() -> None:
    recorded: list[tuple[str, str]] = []

    class _DummyManager:
        async def record_file_read(self, session_id: str, file_path: str) -> None:
            recorded.append((session_id, file_path))

    dummy_server = SimpleNamespace(router_context_manager=_DummyManager())
    await _rehydrate_file_reads(
        server_module=dummy_server,
        session_id="session-123",
        tracked_reads=["/tmp/a.py", "/tmp/b.py"],
    )

    assert recorded == [
        ("session-123", "/tmp/a.py"),
        ("session-123", "/tmp/b.py"),
    ]


@pytest.mark.asyncio
async def test_get_execution_context_fails_closed_without_recovery_mode() -> None:
    from scribe_mcp import server as server_module

    original = getattr(server_module.app.state, "execution_context", None)
    server_module.app.state.execution_context = SimpleNamespace(session_id="bootstrap-session")
    try:
        # No request-local context + no explicit recovery mode must fail closed.
        resolved, metadata = server_module.get_execution_context(include_metadata=True)
        assert resolved is None
        assert metadata["resolution_source"] == "unresolved"
        assert metadata["trust_level"] == "anonymous"
        assert metadata["fallback_used"] is False
        assert metadata["fallback_chain"] == []
    finally:
        server_module.app.state.execution_context = original


@pytest.mark.asyncio
async def test_get_execution_context_explicit_bootstrap_recovery_is_downgraded() -> None:
    from scribe_mcp import server as server_module

    router = RouterContextManager()
    candidate = await router.build_execution_context(
        {
            "repo_root": "/tmp/repo",
            "mode": "project",
            "intent": "tool:test",
            "affected_dev_projects": [],
            "session_id": "bootstrap-session-1",
            "transport_session_id": "bootstrap-transport-1",
            "stable_session_id": "bootstrap-agent-session-1",
            "resolution_source": "runtime_context",
            "trust_level": "verified",
            "scope_provenance": {
                "transport_session_id": "verified",
                "stable_session_id": "verified",
                "agent_session_id": "verified",
                "repo_root": "verified",
                "project_name": "verified",
            },
        }
    )

    original = getattr(server_module.app.state, "execution_context", None)
    server_module.app.state.execution_context = candidate
    try:
        resolved, metadata = server_module.get_execution_context(
            recovery_mode="bootstrap_app_state",
            include_metadata=True,
        )
        assert resolved is not None
        assert resolved is not candidate
        assert resolved.resolved_scope is not None
        assert resolved.resolved_scope.resolution_source == "bootstrap_app_state"
        assert resolved.resolved_scope.trust_level == "inferred"
        assert metadata["resolution_source"] == "bootstrap_app_state"
        assert metadata["trust_level"] == "inferred"
        assert metadata["fallback_used"] is True
        assert metadata["fallback_chain"] == ["bootstrap_app_state"]
    finally:
        server_module.app.state.execution_context = original


@pytest.mark.asyncio
async def test_get_execution_context_prefers_runtime_context_over_bootstrap_state() -> None:
    from scribe_mcp import server as server_module

    router = RouterContextManager()
    runtime_ctx = await router.build_execution_context(
        {
            "repo_root": "/tmp/repo",
            "mode": "project",
            "intent": "tool:test",
            "affected_dev_projects": [],
            "session_id": "runtime-session-1",
            "transport_session_id": "runtime-transport-1",
        }
    )
    token = router.set_current(runtime_ctx)
    original = getattr(server_module.app.state, "execution_context", None)
    server_module.app.state.execution_context = SimpleNamespace(session_id="bootstrap-session")
    try:
        resolved, metadata = server_module.get_execution_context(include_metadata=True)
        assert resolved is runtime_ctx
        assert metadata["resolution_source"] == "runtime_context"
        assert metadata["trust_level"] == "verified"
        assert metadata["fallback_used"] is False
        assert metadata["fallback_chain"] == []
    finally:
        router.reset(token)
        server_module.app.state.execution_context = original


def test_cli_scoped_reuse_key_matches_runtime_scoped_reuse_key(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    assert build_scoped_reuse_key(repo_root, "demo-project") == RouterContextManager.derive_scoped_reuse_key(
        str(repo_root.resolve()),
        "demo-project",
    )
    assert build_scoped_reuse_key(repo_root, None) == RouterContextManager.derive_scoped_reuse_key(
        str(repo_root.resolve()),
        None,
    )
