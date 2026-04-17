from types import SimpleNamespace

from scribe_mcp.scripts import scribe_probe


def test_registry_sanity_probe_reports_readiness_drift_conflict(monkeypatch) -> None:
    project = SimpleNamespace(
        project_name="demo",
        status="in_progress",
        total_files=4,
        total_entries=2,
        meta={
            "docs": {
                "flags": {
                    "docs_ready_for_work": True,
                    "docs_hash_drift": True,
                },
                "baseline_hashes": {"phase_plan": "aaa"},
                "current_hashes": {"phase_plan": "bbb"},
            },
            "activity": {
                "days_since_last_entry": 1,
                "days_since_last_access": 1,
            },
        },
    )

    class _Registry:
        def list_projects(self, limit=None):  # noqa: ARG002
            return [project]

    monkeypatch.setattr(scribe_probe, "ProjectRegistry", lambda: _Registry())
    result = scribe_probe._registry_sanity_probe()

    assert result["ok"] is True
    assert len(result["warnings"]) == 1
    warning = result["warnings"][0]
    assert warning["project"] == "demo"
    assert warning["docs_ready_for_work"] is True
    assert warning["docs_hash_drift"] is True
    assert "docs_ready_conflicts_with_hash_drift" in warning["warnings"]


def test_registry_sanity_probe_honors_project_scope(monkeypatch) -> None:
    project_a = SimpleNamespace(
        project_name="project_a",
        status="planning",
        total_files=1,
        total_entries=0,
        meta={"docs": {"flags": {}, "baseline_hashes": {}, "current_hashes": {}}, "activity": {}},
    )
    project_b = SimpleNamespace(
        project_name="project_b",
        status="in_progress",
        total_files=0,
        total_entries=0,
        meta={"docs": {"flags": {}, "baseline_hashes": {}, "current_hashes": {}}, "activity": {}},
    )

    class _Registry:
        def list_projects(self, limit=None):  # noqa: ARG002
            return [project_a, project_b]

    monkeypatch.setattr(scribe_probe, "ProjectRegistry", lambda: _Registry())
    result = scribe_probe._registry_sanity_probe(project="project_b")

    assert result["ok"] is True
    assert len(result["warnings"]) == 1
    assert result["warnings"][0]["project"] == "project_b"
