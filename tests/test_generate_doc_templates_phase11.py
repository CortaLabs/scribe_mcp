from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.tools import generate_doc_templates as gen_module
from scribe_mcp.tools.generate_doc_templates import generate_doc_templates


@pytest.fixture
def _tool_runtime_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _record_tool(_name: str) -> dict:
        return {}

    async def _prepare_context(**_kwargs):
        return SimpleNamespace(project=None)

    def _apply_context_payload(payload: dict, _ctx: object) -> dict:
        return payload

    monkeypatch.setattr(gen_module.server_module.state_manager, "record_tool", _record_tool)
    monkeypatch.setattr(gen_module._GENERATE_DOC_TEMPLATES_HELPER, "prepare_context", _prepare_context)
    monkeypatch.setattr(gen_module._GENERATE_DOC_TEMPLATES_HELPER, "apply_context_payload", _apply_context_payload)


@pytest.mark.asyncio
async def test_generate_doc_templates_honors_downstream_template_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _tool_runtime_mocks: None,
) -> None:
    repo_root = tmp_path / "downstream_repo"
    repo_root.mkdir(parents=True)
    docs_dir = repo_root / ".scribe" / "docs" / "dev_plans" / "phase11_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    template_dir = repo_root / ".scribe" / "templates" / "documents"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "ARCHITECTURE_GUIDE_TEMPLATE.md").write_text(
        "# Downstream Override\n{{ project_name }}\n",
        encoding="utf-8",
    )

    async def _prepare_context(**_kwargs):
        return SimpleNamespace(project={"root": str(repo_root)})

    monkeypatch.setattr(gen_module._GENERATE_DOC_TEMPLATES_HELPER, "prepare_context", _prepare_context)

    result = await generate_doc_templates(
        project_name="phase11_project",
        documents=("architecture",),
        base_dir=str(repo_root),
        force=True,
    )

    assert result["ok"] is True
    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    assert architecture_path.exists()
    content = architecture_path.read_text(encoding="utf-8")
    assert "Downstream Override" in content
    assert "phase11_project" in content


@pytest.mark.asyncio
async def test_generate_doc_templates_uses_effective_repo_root_for_context_variables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _tool_runtime_mocks: None,
) -> None:
    effective_repo_root = tmp_path / "effective_repo_root"
    effective_repo_root.mkdir(parents=True)

    (effective_repo_root / ".scribe").mkdir(parents=True, exist_ok=True)
    (effective_repo_root / ".scribe" / "variables.json").write_text(
        '{"custom_var":"EFFECTIVE_ROOT_VALUE"}',
        encoding="utf-8",
    )

    template_dir = effective_repo_root / ".scribe" / "templates" / "documents"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "ARCHITECTURE_GUIDE_TEMPLATE.md").write_text(
        "{{ custom_var }}\n",
        encoding="utf-8",
    )

    async def _prepare_context(**_kwargs):
        return SimpleNamespace(project={"root": str(effective_repo_root)})

    monkeypatch.setattr(gen_module._GENERATE_DOC_TEMPLATES_HELPER, "prepare_context", _prepare_context)

    result = await generate_doc_templates(
        project_name="phase11_project",
        documents=("architecture",),
        base_dir=str(effective_repo_root),
        force=True,
    )

    assert result["ok"] is True
    architecture_path = (
        effective_repo_root / ".scribe" / "docs" / "dev_plans" / "phase11_project" / "ARCHITECTURE_GUIDE.md"
    )
    assert architecture_path.exists()
    content = architecture_path.read_text(encoding="utf-8")
    assert "EFFECTIVE_ROOT_VALUE" in content
    assert (effective_repo_root / ".scribe" / "config" / "seed_registry.json").exists()


@pytest.mark.asyncio
async def test_generate_doc_templates_preserves_existing_progress_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _tool_runtime_mocks: None,
) -> None:
    repo_root = tmp_path / "repo_with_progress"
    repo_root.mkdir(parents=True)
    docs_dir = repo_root / ".scribe" / "docs" / "dev_plans" / "phase11_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("existing-log-content\n", encoding="utf-8")

    async def _prepare_context(**_kwargs):
        return SimpleNamespace(project={"root": str(repo_root)})

    monkeypatch.setattr(gen_module._GENERATE_DOC_TEMPLATES_HELPER, "prepare_context", _prepare_context)

    result = await generate_doc_templates(
        project_name="phase11_project",
        documents=("progress_log",),
        base_dir=str(repo_root),
        force=True,
    )

    assert result["ok"] is True
    assert str(progress_log) in result["protected"]
    assert progress_log.read_text(encoding="utf-8") == "existing-log-content\n"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_dir_kind", "slug_in_base_dir"),
    [
        ("canonical", False),
        ("canonical", True),
        ("legacy", False),
        ("legacy", True),
    ],
)
async def test_generate_doc_templates_maps_docs_base_dir_to_repo_root_for_direct_calls(
    tmp_path: Path,
    base_dir_kind: str,
    slug_in_base_dir: bool,
    _tool_runtime_mocks: None,
) -> None:
    repo_root = tmp_path / f"repo_{base_dir_kind}_{'slug' if slug_in_base_dir else 'root'}"
    repo_root.mkdir(parents=True)
    project_slug = "phase11_project"

    if base_dir_kind == "canonical":
        docs_base = repo_root / ".scribe" / "docs" / "dev_plans"
    else:
        docs_base = repo_root / "docs" / "dev_plans"

    docs_base.mkdir(parents=True, exist_ok=True)
    base_dir = docs_base / project_slug if slug_in_base_dir else docs_base
    base_dir.mkdir(parents=True, exist_ok=True)

    template_dir = repo_root / ".scribe" / "templates" / "documents"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "ARCHITECTURE_GUIDE_TEMPLATE.md").write_text(
        "# DocsPath Root Resolution\n",
        encoding="utf-8",
    )

    result = await generate_doc_templates(
        project_name=project_slug,
        documents=("architecture",),
        base_dir=str(base_dir),
        force=True,
    )

    assert result["ok"] is True
    architecture_path = (
        docs_base / project_slug / "ARCHITECTURE_GUIDE.md"
        if not slug_in_base_dir
        else docs_base / project_slug / "ARCHITECTURE_GUIDE.md"
    )
    assert architecture_path.exists()
    assert "DocsPath Root Resolution" in architecture_path.read_text(encoding="utf-8")

    # Effective repo root must be the actual repo root, not docs folder.
    assert (repo_root / ".scribe" / "config" / "seed_registry.json").exists()


@pytest.mark.asyncio
async def test_generate_doc_templates_legacy_fallback_uses_packaged_templates_for_downstream_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _tool_runtime_mocks: None,
) -> None:
    repo_root = tmp_path / "downstream_repo_no_local_package_templates"
    repo_root.mkdir(parents=True)
    docs_base = repo_root / ".scribe" / "docs" / "dev_plans"
    docs_base.mkdir(parents=True, exist_ok=True)

    class _FailingEngine:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def validate_template(self, _template_name: str) -> dict:
            return {"valid": True}

        def render_template(self, _template_name: str, metadata: dict | None = None) -> str:
            raise gen_module.TemplateEngineError("forced failure to exercise legacy fallback")

    monkeypatch.setattr(gen_module, "Jinja2TemplateEngine", _FailingEngine)

    result = await generate_doc_templates(
        project_name="phase11_project",
        documents=("architecture",),
        base_dir=str(docs_base),
        legacy_fallback=True,
        force=True,
    )

    assert result["ok"] is True
    architecture_path = docs_base / "phase11_project" / "ARCHITECTURE_GUIDE.md"
    assert architecture_path.exists()
    content = architecture_path.read_text(encoding="utf-8")
    assert "Architecture Guide" in content
    assert '{% extends "documents/base_document.md" %}' in content
