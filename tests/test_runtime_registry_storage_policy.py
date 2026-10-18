import importlib
import sys
from types import SimpleNamespace

import scribe_mcp.shared.project_registry as project_registry_module


class _FakeApp:
    def tool(self, **_kwargs):
        def _decorator(func):
            return func

        return _decorator


def test_runtime_imports_do_not_bootstrap_sqlite_registry_in_server_mode(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "runtime_registry.sqlite3"
    fake_settings = SimpleNamespace(
        storage_backend="postgres",
        mode="server",
        db_url="postgresql://user:pass@localhost:5432/scribe",
        remote_server_url="",
        public_release=False,
        release_profile="internal",
        sqlite_path=str(sqlite_path),
    )

    monkeypatch.setattr(project_registry_module, "settings", fake_settings)
    monkeypatch.setattr(project_registry_module, "_RUNTIME_REGISTRY", None)
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "scribe_mcp.server", SimpleNamespace(app=_FakeApp()))

    modules = [
        "scribe_mcp.tools.set_project",
        "scribe_mcp.tools.get_project",
        "scribe_mcp.tools.list_projects",
        "scribe_mcp.tools.manage_docs",
        "scribe_mcp.tools.append_entry",
        "scribe_mcp.tools.generate_doc_templates",
    ]

    for module_name in modules:
        module = importlib.import_module(module_name)
        importlib.reload(module)

    registry = project_registry_module.get_runtime_project_registry()
    assert registry.available is False
    assert not sqlite_path.exists()
