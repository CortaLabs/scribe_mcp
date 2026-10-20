from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from scribe_mcp.doc_management.actions.edit import handle_edit_action
from scribe_mcp.doc_management.runtime import register_document_path
from scribe_mcp.tools.agent_project_utils import resolve_authoritative_write_scope


class _BackendStub:
    def __init__(self) -> None:
        self.update_calls = 0

    async def update_project_docs(self, project_name: str, docs_json: str, **_kwargs: Any) -> None:
        self.update_calls += 1


class _RegistryStub:
    def __init__(self) -> None:
        self.calls = 0

    def record_doc_update(self, **_: object) -> None:
        self.calls += 1


@pytest.mark.asyncio
async def test_register_document_path_requires_authority_without_selecting_default(tmp_path: Path) -> None:
    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")

    backend = _BackendStub()
    registry = _RegistryStub()

    captured: dict[str, object] = {}

    async def _set_current_project(
        name: str,
        project_data: dict,
        *,
        agent_id: str,
        session_id: str,
        resolved_scope: object,
        mirror_global: bool,
    ) -> None:
        captured["name"] = name
        captured["session_id"] = session_id
        captured["agent_id"] = agent_id
        captured["mirror_global"] = mirror_global

    server_module = SimpleNamespace(
        storage_backend=backend,
        state_manager=SimpleNamespace(set_current_project=_set_current_project),
    )
    async def _append_entry(**_: object) -> None:
        return None

    project = {"name": "demo", "docs": {}}
    execution_context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")

    warning = await register_document_path(
        project,
        "checklist",
        doc_path,
        server_module=server_module,
        project_registry=registry,
        append_entry=_append_entry,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        execution_context=execution_context,
        agent_id="BugHunterAgent",
    )

    assert warning is None
    assert captured == {}, "metadata registration must never call the selecting setter"
    assert backend.update_calls == 1
    assert registry.calls == 1


@pytest.mark.asyncio
async def test_register_document_path_fails_closed_without_authoritative_session(tmp_path: Path) -> None:
    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")

    backend = _BackendStub()
    registry = _RegistryStub()
    server_module = SimpleNamespace(
        storage_backend=backend,
        state_manager=SimpleNamespace(set_current_project=lambda **_: None),
    )
    async def _append_entry(**_: object) -> None:
        return None

    project = {"name": "demo", "docs": {}}
    execution_context = SimpleNamespace(session_id=None, stable_session_id=None)

    with pytest.raises(ValueError, match="authoritative session binding"):
        await register_document_path(
            project,
            "checklist",
            doc_path,
            server_module=server_module,
            project_registry=registry,
            append_entry=_append_entry,
            logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
            execution_context=execution_context,
            agent_id="BugHunterAgent",
        )

    assert backend.update_calls == 0
    assert registry.calls == 0


def test_resolve_authoritative_write_scope_uses_context_authoritative_session_key() -> None:
    context = SimpleNamespace(
        session_id="context-session",
        stable_session_id="stable-session",
        authoritative_session_key="authoritative-session",
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_key"] == "authoritative-session"
    assert scope["authoritative_session_id"] == "authoritative-session"


def test_resolve_authoritative_write_scope_rejects_transport_only_scope() -> None:
    context = SimpleNamespace(
        transport_session_id="transport-only-session",
        resolved_scope=SimpleNamespace(
            transport_session_id="transport-only-session",
            stable_session_id=None,
            agent_session_id=None,
            authoritative_session_key=None,
            resolution_source="runtime_context",
        ),
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_key"] is None
    assert scope["authoritative_session_id"] is None


@pytest.mark.asyncio
async def test_handle_edit_action_register_doc_does_not_select_default(tmp_path: Path) -> None:
    created_path = tmp_path / "NOTE.md"
    created_path.write_text("# Note\n", encoding="utf-8")

    captured: dict[str, object] = {}

    async def _set_current_project(
        name: str,
        project_data: dict,
        *,
        agent_id: str,
        session_id: str,
        resolved_scope: object,
        mirror_global: bool,
    ) -> None:
        captured["name"] = name
        captured["session_id"] = session_id
        captured["mirror_global"] = mirror_global

    async def _apply_doc_change(*_args, **_kwargs):
        return SimpleNamespace(
            success=True,
            path=created_path,
            diff_preview="",
            before_hash=None,
            after_hash="after",
            extra={},
            error_message=None,
            verification_passed=True,
            file_size_before=0,
            file_size_after=created_path.stat().st_size,
            content_written=created_path.read_text(encoding="utf-8"),
        )

    async def _get_or_create_storage_project(*_args, **_kwargs):
        return object()

    async def _append_entry(**_kwargs):
        return None

    async def _index_doc_for_vector(**_kwargs):
        return None

    def _helper_error_response(message: str, extra: dict | None = None):
        payload = {"ok": False, "error": message}
        if extra:
            payload["extra"] = extra
        return payload

    helper = SimpleNamespace(
        apply_context_payload=lambda response, _context: response,
        error_response=_helper_error_response,
    )
    async def _record_doc_change(*_args, **_kwargs):
        return None

    async def _update_project_docs(*_args, **_kwargs):
        return None

    backend = SimpleNamespace(
        record_doc_change=_record_doc_change,
        update_project_docs=_update_project_docs,
    )
    server_module = SimpleNamespace(
        state_manager=SimpleNamespace(set_current_project=_set_current_project),
        storage_backend=backend,
    )
    context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")
    project = {"name": "demo", "docs": {}}

    result = await handle_edit_action(
        action="create_doc",
        project=project,
        doc_name="note_doc",
        doc_category="",
        section=None,
        content="# Note\n",
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"doc_name": "note_doc", "register_doc": True},
        dry_run=False,
        backend=backend,
        agent_id="BugHunterAgent",
        helper=helper,
        context=context,
        execution_context=context,
        deprecation_warning=None,
        apply_doc_change=_apply_doc_change,
        get_or_create_storage_project=_get_or_create_storage_project,
        append_entry=_append_entry,
        normalize_metadata_with_healing=lambda metadata: (dict(metadata or {}), False, []),
        index_doc_for_vector=_index_doc_for_vector,
        vector_indexing_enabled=lambda _repo_root: False,
        get_index_updater_for_path=lambda *_args, **_kwargs: None,
        project_registry=SimpleNamespace(record_doc_update=lambda **_kwargs: None),
        server_module=server_module,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert result is not None
    assert result["ok"] is True
    warnings = result.get("warnings") or []
    assert all("Registry update failed" not in warning for warning in warnings)
    assert captured == {}, "document registration must never select a caller default"


def test_resolve_authoritative_write_scope_prefers_context_session_id_over_stable() -> None:
    """Contract test (BUG-2026-06-11-0004): without a resolved_scope, the
    request's own session_id outranks a bare carried-over stable_session_id.
    Originally pinned in 08d4d22; regressed by e320b3d; restored 2026-06-11."""
    context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_id"] == "authoritative-session"


def test_resolve_authoritative_write_scope_verified_scope_still_wins() -> None:
    """Server-derived resolved_scope keys keep absolute priority — the
    trust-order fix only affects degraded contexts without a resolved scope."""
    resolved = SimpleNamespace(
        authoritative_session_key="scope-derived-key",
        stable_session_id="scope-stable",
        agent_session_id=None,
        resolution_source="runtime_context",
    )
    context = SimpleNamespace(
        resolved_scope=resolved,
        session_id="request-session",
        stable_session_id="raw-stable",
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_id"] == "scope-derived-key"


@pytest.mark.regression
@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_real_sdk_document_target_preserves_default(tmp_path: Path, test_agent: str, mode: str) -> None:
    """Real stdio ingress must keep metadata writes separate from selection."""
    source = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("SCRIBE_") and key != "DATABASE_URL"}
    env.update({
        "SCRIBE_RELEASE_PROFILE": "internal", "SCRIBE_DISABLE_DOTENV": "1",
        "SCRIBE_LOAD_REPO_DOTENV": "0", "SCRIBE_MODE": "standalone",
        "SCRIBE_STORAGE_BACKEND": "sqlite", "SCRIBE_OBJECT_STORE_PROVIDER": "filesystem",
        "SCRIBE_DB_PATH": str(runtime / "scribe.sqlite3"),
        "SCRIBE_STATE_PATH": str(runtime / "state.json"), "SCRIBE_ROOT": str(runtime),
        "SCRIBE_REPO_ROOT": str(repo), "SCRIBE_TRUSTED_REPO_ROOTS": str(repo),
        "PYTHONPATH": str(source / "src"),
        "SBR_TEST_AGENT": test_agent, "SBR_TEST_MODE": mode, "SBR_TEST_SOURCE": str(source),
    })
    probe = r'''
import anyio, json, os, sqlite3, sys
from pathlib import Path
from importlib.metadata import version
from mcp import StdioServerParameters
from mcp.client.client import Client
from mcp.client.stdio import stdio_client
import scribe_mcp
from scribe_mcp.utils.frontmatter import parse_frontmatter

agent = os.environ["SBR_TEST_AGENT"]
repo = Path(os.environ["SCRIBE_REPO_ROOT"])
fields = ("authoritative_session_key", "repo_root", "project_name", "project_key",
          "binding_generation", "caller_session_key_hash")

def bindings():
    # Read the disposable store, including timestamps; never manufacture authority.
    with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
        return connection.execute("SELECT * FROM session_projects ORDER BY session_id").fetchall()

async def call(client, name, arguments):
    result = await client.call_tool(name, {"agent": agent, **arguments})
    assert not result.is_error, (name, result)
    data = json.loads("\n".join(getattr(item, "text", "") for item in result.content))
    assert data.get("ok", True) is not False, (name, data)
    return data

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "scribe_mcp"],
                                   env=dict(os.environ), cwd=os.environ["SBR_TEST_SOURCE"])
    with anyio.fail_after(90):
        async with Client(stdio_client(params), mode=os.environ["SBR_TEST_MODE"]) as client:
            async with Client(stdio_client(params), mode=os.environ["SBR_TEST_MODE"]) as sibling:
                await call(sibling, "set_project", {"name": "sibling_default", "root": str(repo), "format": "structured"})
                await call(client, "set_project", {"name": "target_b", "root": str(repo), "format": "structured"})
                await call(client, "set_project", {"name": "default_a", "root": str(repo), "format": "structured"})
                doctor = await call(client, "scribe_doctor", {})
                before = tuple(doctor["runtime"]["repo_authority"].get(key) for key in fields)
                assert before[2] == "default_a" and before[4] == 2, before
                records = bindings()
                assert len(records) >= 2, records
                created = await call(client, "manage_docs", {"project": "target_b", "action": "create",
                    "doc_name": "DEFAULT_GUARD", "metadata": {"doc_type": "custom",
                    "body": "# Default guard\n\n<!-- ID: proof -->\nInitial text.\n",
                    "summary": "Isolated default binding regression.", "status": "in_progress"}})
                path = Path(created["path"]).resolve()
                assert path.is_relative_to(repo.resolve())
                await call(client, "manage_docs", {"project": "target_b", "action": "replace_section",
                    "doc": "DEFAULT_GUARD", "section": "proof", "content": "Verified default guard text.\n"})
                after_doc = await call(client, "scribe_doctor", {})
                observed = tuple(after_doc["runtime"]["repo_authority"].get(key) for key in fields)
                print(json.dumps({"sdk": version("mcp"), "source": scribe_mcp.__file__,
                    "mode": os.environ["SBR_TEST_MODE"], "before": before, "after": observed}), flush=True)
                assert observed == before, "explicit B document changed caller default A"
                assert bindings() == records, "document changed a binding record or timestamp"
                assert "Verified default guard text.\n" in path.read_text(encoding="utf-8")
                with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
                    docs = json.loads(connection.execute(
                        "SELECT docs_json FROM scribe_projects WHERE name = ? AND repo_root = ?",
                        ("target_b", str(repo))).fetchone()[0])
                assert docs["DEFAULT_GUARD"] == str(path)
                review = await call(client, "manage_docs", {"project": "target_b", "action": "create",
                    "doc_name": "REVIEW_DEFAULT_GUARD", "metadata": {"doc_type": "review",
                    "stage": "phase_4_2", "summary": "Review metadata persistence guard."}})
                await call(client, "manage_docs", {"project": "target_b", "action": "replace_section",
                    "doc": review["doc_name"], "section": "executive_summary",
                    "content": "Review metadata followup.\n"})
                review_path = Path(review["path"]).resolve()
                assert review_path.is_relative_to(repo.resolve())
                assert "Review metadata followup." in review_path.read_text(encoding="utf-8")
                spec = await call(client, "manage_docs", {"project": "target_b", "action": "create",
                    "doc": "spec_guard", "metadata": {"doc_type": "spec", "doc_name": "SPEC_DEFAULT_GUARD",
                    "body": "# Spec\n\nMetadata persistence guard.\n"}})
                await call(client, "manage_docs", {"project": "target_b", "action": "frontmatter_update",
                    "doc": "SPEC_DEFAULT_GUARD", "metadata": {"frontmatter": {"status": "ready"}}})
                spec_path = Path(spec["path"]).resolve()
                assert spec_path.is_relative_to(repo.resolve())
                spec_metadata = parse_frontmatter(spec_path.read_text(encoding="utf-8")).frontmatter_data
                assert spec_metadata["doc_type"] == "spec"
                assert spec_metadata["status"] == "ready"
                with sqlite3.connect(os.environ["SCRIBE_DB_PATH"]) as connection:
                    docs = json.loads(connection.execute(
                        "SELECT docs_json FROM scribe_projects WHERE name = ? AND repo_root = ?",
                        ("target_b", str(repo))).fetchone()[0])
                assert docs[review["doc_name"]] == str(review_path)
                assert docs["SPEC_DEFAULT_GUARD"] == str(spec_path)
                assert bindings() == records, "metadata persistence changed a caller or sibling binding"
                for owner, project in ((client, "default_a"), (sibling, "sibling_default")):
                    marker = "default-guard-" + project
                    await call(owner, "append_entry", {"message": marker, "format": "structured"})
                    recent = await call(owner, "read_recent", {"limit": 1, "format": "structured"})
                    assert marker in json.dumps(recent)
                assert bindings() == records
anyio.run(main)
'''
    sdk_python = os.environ.get("SBR_SDK_PYTHON", sys.executable)
    result = subprocess.run([sdk_python, "-c", probe], cwd=source, env=env,
                            capture_output=True, text=True, timeout=110)
    assert result.returncode == 0, result.stdout + result.stderr
