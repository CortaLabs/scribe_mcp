import asyncio
from pathlib import Path
import sys
import types

from scribe_mcp.doc_management import indexing

if "scribe_mcp.server" not in sys.modules:
    class _AppStub:
        @staticmethod
        def tool(*_args, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

    sys.modules["scribe_mcp.server"] = types.SimpleNamespace(
        app=_AppStub(),
        settings=types.SimpleNamespace(storage_timeout_seconds=5),
        state_manager=None,
    )

from scribe_mcp.doc_management import special_create


class _Helper:
    @staticmethod
    def apply_context_payload(payload, _context):
        return payload

    @staticmethod
    def error_response(message, suggestion=None, extra=None):
        response = {"ok": False, "error": message}
        if suggestion:
            response["suggestion"] = suggestion
        if extra:
            response["extra"] = extra
        return response


class _ProjectRegistry:
    @staticmethod
    def record_doc_update(**_kwargs):
        return None


def test_indexing_routes_case_reports_to_explicit_security_updater(tmp_path: Path):
    project_root = tmp_path
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "p1"
    research_dir = docs_dir / "research"
    bugs_root = project_root / "docs" / "bugs"
    security_root = project_root / "docs" / "security"

    research_dir.mkdir(parents=True)
    bugs_root.mkdir(parents=True)
    security_root.mkdir(parents=True)

    paths = {
        "research": research_dir / "RESEARCH_SCOPE.md",
        "bug": bugs_root / "logic" / "2026-04-16_bug" / "report.md",
        "security": security_root / "auth" / "2026-04-16_sec" / "report.md",
        "review": docs_dir / "REVIEW_REPORT_phase0_2026-04-16_1200.md",
        "agent": docs_dir / "AGENT_REPORT_CARD_Coder_phase0_20260416_1200.md",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# content\n", encoding="utf-8")

    counts = {"research": 0, "bug": 0, "security": 0, "review": 0, "agent": 0}

    async def _inc(name):
        counts[name] += 1

    def _updater(path: Path, _agent: str, name: str):
        return _inc(name)

    expected = {
        "research": "research",
        "bug": "bug",
        "security": "security",
        "review": "review",
        "agent": "agent",
    }

    for family, file_path in paths.items():
        for key in counts:
            counts[key] = 0
        updater = indexing.get_index_updater_for_path(
            file_path=file_path,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test-agent",
            update_research_index=lambda p, a: _updater(p, a, "research"),
            update_bug_index=lambda p, a: _updater(p, a, "bug"),
            update_security_index=lambda p, a: _updater(p, a, "security"),
            update_review_index=lambda p, a: _updater(p, a, "review"),
            update_agent_card_index=lambda p, a: _updater(p, a, "agent"),
        )
        assert updater is not None
        asyncio.run(updater())
        assert counts[expected[family]] == 1
        assert sum(counts.values()) == 1


def test_create_security_report_uses_explicit_security_index_updater_once(monkeypatch, tmp_path: Path):
    counters = {"security": 0, "bug": 0}

    async def _capture_security(*_args, **_kwargs):
        counters["security"] += 1

    async def _capture_bug(*_args, **_kwargs):
        counters["bug"] += 1

    async def _noop_append_entry(**_kwargs):
        return {"ok": True}

    monkeypatch.setattr(special_create, "_update_security_index", _capture_security)
    monkeypatch.setattr(special_create, "_update_bug_index", _capture_bug)
    monkeypatch.setattr(special_create, "append_entry", _noop_append_entry)

    project_root = tmp_path
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "p1"
    docs_dir.mkdir(parents=True)
    project = {
        "name": "p1",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {},
    }

    result = asyncio.run(
        special_create.handle_special_document_creation(
            project=project,
            action="create_security_report",
            doc_name="SEC_CASE",
            target_dir=None,
            content="# Security Case\n",
            metadata={"category": "auth", "slug": "token_leak"},
            dry_run=False,
            agent_id="test-agent",
            storage_backend=None,
            helper=_Helper(),
            context={"test": True},
            project_registry=_ProjectRegistry(),
            logger=special_create.logging.getLogger("test"),
        )
    )

    assert result.get("ok") is True
    assert counters["security"] == 1
    assert counters["bug"] == 0
