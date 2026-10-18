#!/usr/bin/env python3
"""
Unit tests for SPEC-SET-001: Fix BUG-001 Empty Log Detection

Tests verify that empty progress logs (after rotation or manual clearing) are
correctly identified as EXISTING projects, not NEW projects.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest
from types import SimpleNamespace
import uuid

from scribe_mcp.tools import set_project as set_project_module
from scribe_mcp.tools import append_entry as append_entry_module
from scribe_mcp.tools import rotate_log as rotate_log_module

# Get actual functions (unwrapped from MCP decorator)
set_project = set_project_module.set_project
append_entry = append_entry_module.append_entry
rotate_log = rotate_log_module.rotate_log


def extract_result(result):
    """
    Extract data from tool result.

    For readable format: Returns dict by parsing CallToolResult
    For structured/compact: Returns dict directly
    """
    # Check if it's a CallToolResult (MCP framework object)
    if hasattr(result, 'content'):
        # Extract the text content (readable output)
        text_content = None
        for content_item in result.content:
            if hasattr(content_item, 'text'):
                text_content = content_item.text
                break

        # Parse dict from result if available (hidden in structured data)
        # For now, just return the text content
        return {"readable_content": text_content, "format": "readable", "ok": True}
    else:
        # It's already a dict (structured/compact format)
        return result


def _disable_live_storage_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests deterministic by avoiding live asyncpg-backed storage."""
    monkeypatch.setattr(set_project_module.server_module, "storage_backend", None)
    monkeypatch.setattr(
        set_project_module.server_module.state_manager,
        "_storage_backend",
        None,
        raising=False,
    )


class _InMemoryProjectBackend:
    def __init__(self) -> None:
        self._projects: dict[tuple[str, str], SimpleNamespace] = {}
        self._next_id = 1
        self.upsert_project_calls = 0
        self.upsert_agent_recent_project_calls = 0
        self.upsert_dev_plan_calls = 0

    async def fetch_project(self, name: str, *, repo_root: str | None = None):
        if repo_root is not None:
            return self._projects.get((name, repo_root))
        for (project_name, _root), record in self._projects.items():
            if project_name == name:
                return record
        return None

    async def list_projects(self):
        return list(self._projects.values())

    async def upsert_project(self, *, name: str, repo_root: str, progress_log_path: str, docs_json: str, bridge_id=None, bridge_managed=None):
        self.upsert_project_calls += 1
        key = (name, repo_root)
        record = self._projects.get(key)
        if record is None:
            record = SimpleNamespace(
                id=self._next_id,
                name=name,
                repo_root=repo_root,
                progress_log_path=progress_log_path,
                docs_json=docs_json,
                bridge_id=bridge_id,
                bridge_managed=bridge_managed,
            )
            self._next_id += 1
            self._projects[key] = record
        else:
            record.progress_log_path = progress_log_path
            record.docs_json = docs_json
            record.bridge_id = bridge_id
            record.bridge_managed = bridge_managed
        return record

    async def upsert_agent_recent_project(self, *args, **kwargs):
        self.upsert_agent_recent_project_calls += 1
        return None

    async def upsert_dev_plan(self, *args, **kwargs):
        self.upsert_dev_plan_calls += 1
        return None

    async def count_entries(self, project, filters=None):
        return 0

    async def fetch_recent_entries(self, project, limit=10, filters=None):
        return []


class _FakeAgentContextManager:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.set_current_project_calls = 0
        self.describe_current_project_binding_calls = 0
        self.binding: dict | None = None
        self.expired = False

    async def start_session(self, agent_id: str, session_id: str | None = None, metadata=None):
        return session_id or self.session_id

    async def set_current_project(
        self,
        *,
        agent_id: str,
        project_name: str | None,
        session_id: str,
        expected_version=None,
    ):
        self.set_current_project_calls += 1
        version = ((self.binding or {}).get("version") or 0) + 1
        self.binding = {
            "agent_id": agent_id,
            "project_name": project_name,
            "session_id": session_id,
            "version": version,
            "updated_by": agent_id,
        }
        return dict(self.binding)

    async def describe_current_project_binding(self, *, agent_id: str, session_id: str | None = None):
        self.describe_current_project_binding_calls += 1
        session_id = session_id or self.session_id
        if self.expired:
            return {"valid": False, "reason": "session_expired"}
        if not self.binding:
            return {"valid": False, "reason": "missing_agent_project_binding"}
        if self.binding.get("agent_id") != agent_id:
            return {"valid": False, "reason": "agent_mismatch"}
        if self.binding.get("session_id") != session_id:
            return {
                "valid": False,
                "reason": "agent_session_mismatch",
                "binding": dict(self.binding),
            }
        return {
            "valid": True,
            "reason": "binding_verified",
            "binding": dict(self.binding),
        }


def _install_project_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    agent_manager: _FakeAgentContextManager,
    repo_root: Path,
) -> str:
    session_id = agent_manager.session_id

    def _get_execution_context(*_args, **kwargs):
        context = SimpleNamespace(
            repo_root=str(repo_root),
            mode="project",
            session_id=session_id,
            stable_session_id=session_id,
            resolved_scope=None,
            authoritative_session_key=session_id,
        )
        if kwargs.get("include_metadata"):
            return context, {"fallback_used": False}
        return context

    async def _ensure_agent_session(_agent_id: str, stable_session_id: str | None = None):
        return stable_session_id or session_id

    monkeypatch.setattr(set_project_module.server_module, "get_execution_context", _get_execution_context)
    monkeypatch.setattr(set_project_module.server_module, "get_agent_context_manager", lambda: agent_manager)
    monkeypatch.setattr(set_project_module, "ensure_agent_session", _ensure_agent_session)
    return session_id


class TestBug001EmptyLogDetection:
    """Test suite for BUG-001: Empty log detection fix (SPEC-SET-001)."""

    @pytest.mark.asyncio
    async def test_bug_001_empty_log_shows_existing_sitrep(self, monkeypatch: pytest.MonkeyPatch):
        """
        Verify rotated/empty logs show existing SITREP, not new SITREP.

        This test reproduces the original bug:
        1. Create a project
        2. Add an entry
        3. Rotate the log (creating empty file)
        4. Call set_project again
        5. Verify it shows EXISTING, not NEW
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _disable_live_storage_backend(monkeypatch)
            fake_backend = _InMemoryProjectBackend()
            monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
            monkeypatch.setattr(rotate_log_module.server_module, "storage_backend", fake_backend)
            unique_id = str(uuid.uuid4())[:8]
            project_name = f"test_bug_001_rotation_{unique_id}"
            agent_name = f"TestAgent-Bug001-{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            # Step 1: Create initial project (use readable format to get is_new flag)
            raw_result1 = await set_project(
                agent=agent_name,
                name=project_name,
                root=str(project_root),
                format="readable"
            )
            result1 = extract_result(raw_result1)
            assert result1["ok"], "Initial project creation failed"

            # Check for NEW PROJECT message in readable content
            readable1 = result1.get("readable_content", "")
            assert "NEW PROJECT" in readable1.upper(), \
                f"Should show NEW PROJECT message initially. Got: {readable1[:200]}"

            # Step 2: Add an entry to make it non-empty
            await append_entry(
                message="Test entry before rotation",
                status="info",
                agent=agent_name
            )

            # Step 3: Rotate the log (creates empty file)
            raw_rotate = await rotate_log(agent=agent_name, confirm=True)
            rotate_result = extract_result(raw_rotate)
            if not rotate_result.get("ok"):
                progress_log = project_root / ".scribe" / "docs" / "dev_plans" / project_name / "PROGRESS_LOG.md"
                progress_log.write_text("", encoding="utf-8")

            # Step 4: Call set_project again after rotation
            raw_result2 = await set_project(
                agent=agent_name,
                name=project_name,
                root=str(project_root),
                format="readable"
            )
            result2 = extract_result(raw_result2)

            # Step 5: Verify it's detected as EXISTING, not NEW
            assert result2["ok"], "Second set_project call failed"

            # Check that it shows ACTIVATED (existing) not CREATED (new)
            readable2 = result2.get("readable_content", "")
            assert "PROJECT ACTIVATED" in readable2.upper() or "EXISTING PROJECT" in readable2.upper(), \
                f"BUG-001: Should show PROJECT ACTIVATED for rotated log. Got: {readable2[:200]}"
            assert "NEW PROJECT CREATED" not in readable2, \
                f"BUG-001: Should not show NEW PROJECT CREATED for rotated log. Got: {readable2[:200]}"

    @pytest.mark.asyncio
    async def test_bug_001_genuinely_new_project(self, monkeypatch: pytest.MonkeyPatch):
        """
        Regression test: Ensure truly new projects still work correctly.

        This verifies the fix doesn't break the happy path where a project
        is genuinely new (log file doesn't exist at all).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _disable_live_storage_backend(monkeypatch)
            fake_backend = _InMemoryProjectBackend()
            monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
            unique_id = str(uuid.uuid4())[:8]
            project_name = f"test_bug_001_new_{unique_id}"
            agent_name = f"TestAgent-Bug001New-{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            # Create a genuinely new project
            raw_result = await set_project(
                agent=agent_name,
                name=project_name,
                root=str(project_root),
                format="readable"
            )
            result = extract_result(raw_result)

            # Verify it's correctly detected as NEW
            assert result["ok"], "New project creation failed"

            # Verify NEW PROJECT message appears
            readable = result.get("readable_content", "")
            assert "NEW PROJECT" in readable.upper(), \
                f"New project should show NEW PROJECT message. Got: {readable[:200]}"

            # Verify log file exists after creation
            docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / project_name
            log_path = docs_dir / "PROGRESS_LOG.md"
            assert log_path.exists(), \
                f"Progress log should exist after creation at {log_path}"


class TestSlugCollisionDetection:
    """Test suite for slug collision detection in set_project (Task Package 1.8)."""

    @pytest.mark.asyncio
    async def test_collision_different_names_same_slug(self, monkeypatch: pytest.MonkeyPatch):
        """
        Verify that creating 'my-project' after 'my_project' is rejected with clear error.

        This tests the core collision detection: two different names that normalize to
        the same canonical slug should not be allowed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _disable_live_storage_backend(monkeypatch)
            fake_backend = _InMemoryProjectBackend()
            monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
            unique_id = str(uuid.uuid4())[:8]
            agent_name = f"TestAgent-Collision-{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            async def _resolve_root_stub(*_args, **_kwargs):
                return project_root.resolve(), {
                    "resolved_root": str(project_root.resolve()),
                    "reason_code": "test_stubbed_root",
                }

            monkeypatch.setattr(set_project_module, "_resolve_root", _resolve_root_stub)

            # Create first project: 'my_project'
            result1 = await set_project(
                agent=agent_name,
                name="my_project",
                root=str(project_root),
                format="structured"
            )
            result1 = extract_result(result1)
            assert result1.get("ok", False), f"First project creation failed: {result1}"

            # Try to create second project with different name but same slug: 'my-project'
            result2 = await set_project(
                agent=agent_name,
                name="my-project",
                root=str(project_root),
                format="structured"
            )
            result2 = extract_result(result2)

            # Should fail with collision error
            assert not result2.get("ok", False), \
                "Second project with colliding slug should be rejected"
            assert "error" in result2, "Collision response should include error message"
            assert "my_project" in result2["error"], \
                f"Error should mention existing project 'my_project'. Got: {result2['error']}"

            # Error can come from either path validation OR slug collision check
            # Both are valid ways to catch the same collision
            error_msg = result2["error"]
            is_path_collision = "already belongs to project" in error_msg
            is_slug_collision = "collision" in result2

            assert is_path_collision or is_slug_collision, \
                f"Should detect collision via path or slug check. Got: {result2}"

            # If it's a slug collision (reached our new check), verify details
            if is_slug_collision:
                collision = result2.get("collision", {})
                assert collision.get("new_name") == "my-project", \
                    "Collision should specify attempted new name"
                assert collision.get("existing_name") == "my_project", \
                    "Collision should specify existing project name"
                assert collision.get("canonical_slug") == "my_project", \
                    "Collision should show canonical slug both normalize to"

    @pytest.mark.asyncio
    async def test_no_collision_same_name_update(self, monkeypatch: pytest.MonkeyPatch):
        """
        Verify that updating a project with the same exact name is allowed (not a collision).

        This is critical: calling set_project twice with the same name should work
        (it's an update operation), even though the slugs are identical.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _disable_live_storage_backend(monkeypatch)
            fake_backend = _InMemoryProjectBackend()
            monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
            unique_id = str(uuid.uuid4())[:8]
            agent_name = f"TestAgent-NoCollision-{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            async def _resolve_root_stub(*_args, **_kwargs):
                return project_root.resolve(), {
                    "resolved_root": str(project_root.resolve()),
                    "reason_code": "test_stubbed_root",
                }

            monkeypatch.setattr(set_project_module, "_resolve_root", _resolve_root_stub)

            # Create project
            result1 = await set_project(
                agent=agent_name,
                name="test_project",
                root=str(project_root),
                format="structured"
            )
            result1 = extract_result(result1)
            assert result1.get("ok", False), f"First project creation failed: {result1}"

            # Update same project (same name) - should succeed
            result2 = await set_project(
                agent=agent_name,
                name="test_project",
                root=str(project_root),
                description="Updated description",
                format="structured"
            )
            result2 = extract_result(result2)

            # Should succeed
            assert result2.get("ok", False), \
                f"Updating project with same name should succeed. Got: {result2}"

    @pytest.mark.asyncio
    async def test_collision_multiple_variants(self, monkeypatch: pytest.MonkeyPatch):
        """
        Verify collision detection works with various slug variants.

        Tests: 'my_project', 'my-project', 'My Project', 'MY-PROJECT' all normalize
        to the same slug and should collide.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _disable_live_storage_backend(monkeypatch)
            fake_backend = _InMemoryProjectBackend()
            monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
            unique_id = str(uuid.uuid4())[:8]
            agent_name = f"TestAgent-MultiVariant-{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            async def _resolve_root_stub(*_args, **_kwargs):
                return project_root.resolve(), {
                    "resolved_root": str(project_root.resolve()),
                    "reason_code": "test_stubbed_root",
                }

            monkeypatch.setattr(set_project_module, "_resolve_root", _resolve_root_stub)

            # Create base project
            result1 = await set_project(
                agent=agent_name,
                name="my_project",
                root=str(project_root),
                format="structured"
            )
            result1 = extract_result(result1)
            assert result1.get("ok", False), f"Base project creation failed: {result1}"

            # Try various colliding names
            colliding_names = ["my-project", "My-Project", "MY_PROJECT", "my project"]

            for variant in colliding_names:
                result = await set_project(
                    agent=agent_name,
                    name=variant,
                    root=str(project_root),
                    format="structured"
                )
                result = extract_result(result)

                # All should fail with collision
                assert not result.get("ok", False), \
                    f"Variant '{variant}' should collide with 'my_project'"
                assert "collision" in result or "error" in result, \
                    f"Variant '{variant}' should have collision/error in response"

    @pytest.mark.asyncio
    async def test_slug_collision_precheck_ignores_other_repo(self):
        class FakeBackend:
            async def fetch_project(self, _name):
                return None

            async def list_projects(self):
                return [
                    SimpleNamespace(name="my_project", repo_root="/tmp/other_repo"),
                ]

        collision = await set_project_module._check_slug_collision(
            "my-project",
            FakeBackend(),
            Path("/tmp/current_repo"),
        )

        assert collision is None

    @pytest.mark.asyncio
    async def test_slug_collision_precheck_blocks_same_repo(self):
        class FakeBackend:
            async def fetch_project(self, _name):
                return None

            async def list_projects(self):
                return [
                    SimpleNamespace(name="my_project", repo_root="/tmp/current_repo"),
                ]

        collision = await set_project_module._check_slug_collision(
            "my-project",
            FakeBackend(),
            Path("/tmp/current_repo"),
        )

        assert collision is not None
        assert collision["collision"]["existing_name"] == "my_project"
        assert collision["collision"]["new_name"] == "my-project"
        assert collision["collision"]["canonical_slug"] == "my_project"

    @pytest.mark.asyncio
    async def test_slug_collision_precheck_fails_closed_on_runtime_error(self):
        class FakeBackend:
            async def fetch_project(self, _name, **_kwargs):
                raise RuntimeError("db is unavailable")

        collision = await set_project_module._check_slug_collision(
            "my-project",
            FakeBackend(),
            Path("/tmp/current_repo"),
        )

        assert collision is not None
        assert collision.get("ok") is False
        assert collision.get("error_code") == "storage_lookup_failed"
        assert "storage lookup failure" in collision.get("error", "")


@pytest.mark.asyncio
async def test_set_project_structured_includes_post_bind_reminders(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-Reminder-{unique_id}"
        project_name = f"reminder_project_{unique_id}"
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()

        result = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        )
        result = extract_result(result)
        assert result.get("ok", False), f"set_project failed: {result}"
        assert "reminders" in result, "structured response should include post-bind reminders when present"


@pytest.mark.asyncio
async def test_set_project_compact_includes_post_bind_reminders(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-CompactReminder-{unique_id}"
        project_name = f"compact_reminder_project_{unique_id}"
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()

        result = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="compact",
        )
        result = extract_result(result)
        assert result.get("ok", False), f"set_project failed: {result}"
        assert "reminders" in result, "compact response should include post-bind reminders when present"


@pytest.mark.asyncio
async def test_set_project_structured_timing_includes_targeted_refresh_after(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-StructuredTiming-{unique_id}"
        project_name = f"structured_timing_project_{unique_id}"
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()

        result = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        )
        result = extract_result(result)
        assert result.get("ok", False), f"set_project failed: {result}"
        phases = ((result.get("timing") or {}).get("set_project_phase_ms") or {})
        assert "targeted_refresh_after" in phases, "structured timing should include targeted_refresh_after"
        assert "prepare_context_after" not in phases, "structured timing should exclude readable-only prepare_context_after"


@pytest.mark.asyncio
async def test_set_project_compact_timing_includes_targeted_refresh_after(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-CompactTiming-{unique_id}"
        project_name = f"compact_timing_project_{unique_id}"
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()

        result = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="compact",
        )
        result = extract_result(result)
        assert result.get("ok", False), f"set_project failed: {result}"
        phases = ((result.get("timing") or {}).get("set_project_phase_ms") or {})
        assert "targeted_refresh_after" in phases, "compact timing should include targeted_refresh_after"
        assert "prepare_context_after" not in phases, "compact timing should exclude readable-only prepare_context_after"


@pytest.mark.asyncio
async def test_set_project_readable_existing_project_with_deterministic_backend(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-Existing-{unique_id}"
        project_name = f"existing_project_{unique_id}"
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()

        first = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="readable",
        )
        first_result = extract_result(first)
        assert first_result.get("ok", False)

        second = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="readable",
        )
        second_result = extract_result(second)
        assert second_result.get("ok", False)
        readable = second_result.get("readable_content", "") or ""
        assert "PROJECT ACTIVATED" in readable.upper() or "EXISTING PROJECT" in readable.upper()


@pytest.mark.asyncio
async def test_set_project_structured_timing_includes_budget_status_shape(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-StructuredBudget-{unique_id}"
        project_name = f"structured_budget_project_{unique_id}"
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()

        result = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        )
        result = extract_result(result)
        assert result.get("ok", False), f"set_project failed: {result}"

        timing = result.get("timing") or {}
        budget_status = timing.get("budget_status") or {}
        assert budget_status.get("schema_version") == "runtime-efficiency-budget.v1"
        metrics = budget_status.get("metrics") or {}
        assert "set_project_total_ms" in metrics
        set_project_metric = metrics["set_project_total_ms"]
        assert isinstance(set_project_metric.get("value_ms"), (int, float))
        assert set_project_metric.get("status") in {"within_budget", "near_budget", "over_budget", "unknown"}


@pytest.mark.asyncio
async def test_set_project_structured_reuses_same_binding_without_duplicate_writes(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        agent_manager = _FakeAgentContextManager(session_id=f"session-{uuid.uuid4()}")
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()
        _install_project_context(monkeypatch, agent_manager=agent_manager, repo_root=project_root)

        state_manager = set_project_module.server_module.state_manager
        state_counts = {"set_current_project": 0, "set_session_mode": 0}
        original_set_current_project = state_manager.set_current_project
        original_set_session_mode = state_manager.set_session_mode

        async def _count_state_set_current_project(*args, **kwargs):
            state_counts["set_current_project"] += 1
            return await original_set_current_project(*args, **kwargs)

        async def _count_state_set_session_mode(*args, **kwargs):
            state_counts["set_session_mode"] += 1
            return await original_set_session_mode(*args, **kwargs)

        monkeypatch.setattr(state_manager, "set_current_project", _count_state_set_current_project)
        monkeypatch.setattr(state_manager, "set_session_mode", _count_state_set_session_mode)

        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-Reuse-{unique_id}"
        project_name = f"reuse_project_{unique_id}"

        first = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        ))
        assert first.get("ok", False), f"first set_project failed: {first}"
        first_version = first["project"]["version"]
        write_counts_after_first = {
            "upsert_project": fake_backend.upsert_project_calls,
            "upsert_recent": fake_backend.upsert_agent_recent_project_calls,
            "upsert_dev_plan": fake_backend.upsert_dev_plan_calls,
            "agent_set_current_project": agent_manager.set_current_project_calls,
            "state_set_current_project": state_counts["set_current_project"],
            "state_set_session_mode": state_counts["set_session_mode"],
        }

        second = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        ))
        assert second.get("ok", False), f"second set_project failed: {second}"
        assert second["project"]["version"] == first_version
        assert second["side_effects"]["binding_reused"] is True
        assert second["scope_resolution"]["binding_reused"] is True
        assert second["side_effects"]["binding_reuse_reason"] == "same_agent_session_project_root"
        assert "upsert_project" in second["side_effects"]["skipped_persistent_writes"]
        assert "state_set_current_project" in second["side_effects"]["skipped_persistent_writes"]
        assert fake_backend.upsert_project_calls == write_counts_after_first["upsert_project"]
        assert fake_backend.upsert_agent_recent_project_calls == write_counts_after_first["upsert_recent"]
        assert fake_backend.upsert_dev_plan_calls == write_counts_after_first["upsert_dev_plan"]
        assert agent_manager.set_current_project_calls == write_counts_after_first["agent_set_current_project"]
        assert state_counts["set_current_project"] == write_counts_after_first["state_set_current_project"]
        assert state_counts["set_session_mode"] == write_counts_after_first["state_set_session_mode"]
        assert agent_manager.describe_current_project_binding_calls == 1

        phases = ((second.get("timing") or {}).get("set_project_phase_ms") or {})
        assert "same_binding_reuse_probe" in phases
        assert "prepare_context" not in phases
        assert "targeted_refresh_after" not in phases
        assert "ensure_documents" not in phases
        assert "upsert_project" not in phases
        assert "agent_context_manager" not in phases
        # WS3 Finding 2: warm rebind must run the targeted reminder refresh (not the
        # full-write path) instead of hardcoding reminders:[] and returning early.
        # The refresh ran (mark present) and the reminders key is always a list;
        # whether it is non-empty depends on engine/context state, so the
        # non-empty contract is proven in
        # test_set_project_warm_rebind_surfaces_stale_reminders.
        assert "targeted_refresh_reused" in phases
        assert isinstance(second.get("reminders"), list)


@pytest.mark.asyncio
async def test_set_project_structured_reuses_same_binding_without_execution_context(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        agent_manager = _FakeAgentContextManager(session_id=f"session-{uuid.uuid4()}")
        monkeypatch.setattr(set_project_module.server_module, "get_agent_context_manager", lambda: agent_manager)

        def _missing_execution_context(*_args, **_kwargs):
            if _kwargs.get("include_metadata"):
                return None, {}
            return None

        async def _ensure_agent_session(_agent_id: str, stable_session_id: str | None = None):
            return stable_session_id or agent_manager.session_id

        monkeypatch.setattr(set_project_module.server_module, "get_execution_context", _missing_execution_context)
        monkeypatch.setattr(set_project_module, "ensure_agent_session", _ensure_agent_session)

        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-DirectReuse-{unique_id}"
        project_name = f"direct_reuse_project_{unique_id}"

        first = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        ))
        assert first.get("ok", False), f"first set_project failed: {first}"
        write_counts_after_first = {
            "upsert_project": fake_backend.upsert_project_calls,
            "upsert_recent": fake_backend.upsert_agent_recent_project_calls,
            "upsert_dev_plan": fake_backend.upsert_dev_plan_calls,
            "agent_set_current_project": agent_manager.set_current_project_calls,
        }

        second = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        ))
        assert second.get("ok", False), f"second set_project failed: {second}"
        assert second["side_effects"]["binding_reused"] is True
        assert second["side_effects"]["binding_reuse_reason"] == "same_agent_session_project_root"
        assert "upsert_project" in second["side_effects"]["skipped_persistent_writes"]
        assert fake_backend.upsert_project_calls == write_counts_after_first["upsert_project"]
        assert fake_backend.upsert_agent_recent_project_calls == write_counts_after_first["upsert_recent"]
        assert fake_backend.upsert_dev_plan_calls == write_counts_after_first["upsert_dev_plan"]
        assert agent_manager.set_current_project_calls == write_counts_after_first["agent_set_current_project"]

        phases = ((second.get("timing") or {}).get("set_project_phase_ms") or {})
        assert "same_binding_reuse_probe" in phases
        assert "prepare_context" not in phases
        assert "targeted_refresh_after" not in phases
        assert "ensure_documents" not in phases
        assert "upsert_project" not in phases
        assert "agent_context_manager" not in phases
        # WS3 Finding 2: warm rebind must run the targeted reminder refresh (not the
        # full-write path) instead of hardcoding reminders:[] and returning early.
        # The refresh ran (mark present) and the reminders key is always a list;
        # whether it is non-empty depends on engine/context state, so the
        # non-empty contract is proven in
        # test_set_project_warm_rebind_surfaces_stale_reminders.
        assert "targeted_refresh_reused" in phases
        assert isinstance(second.get("reminders"), list)


@pytest.mark.asyncio
async def test_set_project_structured_different_root_falls_back_to_full_bind(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as first_tmpdir, tempfile.TemporaryDirectory() as second_tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        agent_manager = _FakeAgentContextManager(session_id=f"session-{uuid.uuid4()}")
        first_root = Path(first_tmpdir)
        second_root = Path(second_tmpdir)
        (first_root / ".git").mkdir()
        (second_root / ".git").mkdir()
        _install_project_context(monkeypatch, agent_manager=agent_manager, repo_root=first_root)

        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-ReuseRoot-{unique_id}"
        project_name = f"reuse_root_project_{unique_id}"

        first = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(first_root),
            format="structured",
        ))
        assert first.get("ok", False), f"first set_project failed: {first}"
        first_write_count = fake_backend.upsert_project_calls
        first_agent_write_count = agent_manager.set_current_project_calls

        second = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(second_root),
            format="structured",
        ))
        assert second.get("ok", False), f"second set_project failed: {second}"
        assert second["side_effects"].get("binding_reused") is not True
        assert fake_backend.upsert_project_calls == first_write_count + 1
        assert agent_manager.set_current_project_calls == first_agent_write_count + 1


@pytest.mark.asyncio
async def test_set_project_structured_expired_session_falls_back_to_full_bind(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        agent_manager = _FakeAgentContextManager(session_id=f"session-{uuid.uuid4()}")
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()
        _install_project_context(monkeypatch, agent_manager=agent_manager, repo_root=project_root)

        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-ReuseExpired-{unique_id}"
        project_name = f"reuse_expired_project_{unique_id}"

        first = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        ))
        assert first.get("ok", False), f"first set_project failed: {first}"
        first_write_count = fake_backend.upsert_project_calls
        first_agent_write_count = agent_manager.set_current_project_calls

        agent_manager.expired = True
        second = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        ))
        assert second.get("ok", False), f"second set_project failed: {second}"
        assert second["side_effects"].get("binding_reused") is not True
        assert fake_backend.upsert_project_calls == first_write_count + 1
        assert agent_manager.set_current_project_calls == first_agent_write_count + 1
        assert second["project"]["version"] == first["project"]["version"] + 1


@pytest.mark.asyncio
async def test_set_project_structured_and_compact_timeout_targeted_reminder_refresh(monkeypatch: pytest.MonkeyPatch):
    async def _never_return(*_args, **_kwargs):
        await asyncio.sleep(5)
        return []

    monkeypatch.setattr(set_project_module.reminders, "get_reminders", _never_return)
    for output_format in ("structured", "compact"):
        with tempfile.TemporaryDirectory() as tmpdir:
            _disable_live_storage_backend(monkeypatch)
            fake_backend = _InMemoryProjectBackend()
            monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
            unique_id = str(uuid.uuid4())[:8]
            agent_name = f"TestAgent-Timeout-{output_format}-{unique_id}"
            project_name = f"timeout_project_{output_format}_{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            result = await set_project(
                agent=agent_name,
                name=project_name,
                root=str(project_root),
                format=output_format,
            )
            result = extract_result(result)
            assert result.get("ok", False), f"set_project failed ({output_format}): {result}"
            phases = ((result.get("timing") or {}).get("set_project_phase_ms") or {})
            assert "targeted_refresh_after" in phases, f"{output_format} should include targeted_refresh_after"
            assert "prepare_context_after" not in phases, f"{output_format} should exclude prepare_context_after"
            budget_status = ((result.get("timing") or {}).get("budget_status") or {})
            assert budget_status.get("schema_version") == "runtime-efficiency-budget.v1"


@pytest.mark.asyncio
async def test_set_project_warm_rebind_surfaces_stale_reminders(monkeypatch: pytest.MonkeyPatch):
    """WS3 Finding 2: a warm rebind on a project with a blocking/stale condition
    must surface reminders instead of the old hardcoded ``reminders: []`` early
    return, and must invoke the targeted refresh exactly once (no double refresh
    against the cold path)."""
    stale_reminder = {
        "category": "context",
        "level": "urgent",
        "emoji": "🚨",
        "message": "Project is stale — log progress before continuing.",
        "context": "stale_project",
    }
    refresh_calls = {"count": 0}

    async def _stale_get_reminders(*_args, **_kwargs):
        refresh_calls["count"] += 1
        return [dict(stale_reminder)]

    monkeypatch.setattr(set_project_module.reminders, "get_reminders", _stale_get_reminders)

    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        agent_manager = _FakeAgentContextManager(session_id=f"session-{uuid.uuid4()}")
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()
        _install_project_context(monkeypatch, agent_manager=agent_manager, repo_root=project_root)

        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-WarmRebind-{unique_id}"
        project_name = f"warm_rebind_project_{unique_id}"

        first = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        ))
        assert first.get("ok", False), f"first set_project failed: {first}"
        # Cold path invokes the targeted refresh exactly once.
        assert refresh_calls["count"] == 1
        assert first.get("reminders") == [stale_reminder]

        second = extract_result(await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        ))
        assert second.get("ok", False), f"warm rebind set_project failed: {second}"
        assert second["side_effects"]["binding_reused"] is True

        # Return-path contract: the warm rebind produced reminders (was []).
        assert "reminders" in second, "reused branch must always include a reminders key"
        assert second.get("reminders") == [stale_reminder], (
            "warm rebind on a stale project must surface reminders, not []"
        )
        # The reused branch ran the targeted refresh exactly once — no double refresh.
        assert refresh_calls["count"] == 2
        phases = ((second.get("timing") or {}).get("set_project_phase_ms") or {})
        assert "targeted_refresh_reused" in phases
        # Cold-path full-write refresh mark must not appear on the warm path.
        assert "targeted_refresh_after" not in phases


@pytest.mark.asyncio
async def test_set_project_handles_execution_context_failure(monkeypatch):
    """set_project should still succeed when execution context lookup raises."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _disable_live_storage_backend(monkeypatch)
        fake_backend = _InMemoryProjectBackend()
        monkeypatch.setattr(set_project_module.server_module, "storage_backend", fake_backend)
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-ContextFail-{unique_id}"
        project_name = f"context_fail_project_{unique_id}"
        project_root = Path(tmpdir)
        (project_root / ".git").mkdir()

        def _raise_context_error():
            raise RuntimeError("forced execution-context failure")

        monkeypatch.setattr(set_project_module.server_module, "get_execution_context", _raise_context_error)

        result = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        )
        result = extract_result(result)
        assert result.get("ok", False), f"set_project should tolerate context failure. Got: {result}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_field"),
    [
        ({}, "name"),
        ({"name": "", "root": "/tmp/example"}, "name"),
        ({"name": "   ", "root": "/tmp/example"}, "name"),
        ({"name": "project_without_root"}, "root"),
        ({"name": "project_with_blank_root", "root": ""}, "root"),
        ({"name": "project_with_whitespace_root", "root": "\t"}, "root"),
        ({"name": "project_with_none_root", "root": None}, "root"),
    ],
)
async def test_set_project_rejects_missing_or_blank_required_inputs_before_resolution(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict,
    expected_field: str,
):
    async def _fail_if_resolving_root(*_args, **_kwargs):
        raise AssertionError("set_project should validate required inputs before root resolution")

    monkeypatch.setattr(set_project_module, "_resolve_root", _fail_if_resolving_root)

    result = await set_project(
        agent="TestAgent-RequiredInputs",
        format="structured",
        **payload,
    )
    result = extract_result(result)

    assert result["ok"] is False
    assert result["error_code"] == "missing_required_input"
    assert result["field"] == expected_field
    assert expected_field in result["error"]


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
