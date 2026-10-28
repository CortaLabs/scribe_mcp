import asyncio
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import pytest

from scribe_mcp.doc_management import special_indexes as special_indexes_shared
from scribe_mcp.doc_management.scaffold_quality import analyze_scaffold_quality


def test_explicit_security_index_entrypoint_writes_security_heading():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        security_root = project_root / "docs" / "security"
        report_dir = security_root / "auth" / "2026-01-20_token_leak"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.md").write_text("# Security Report\n")

        asyncio.run(
            special_indexes_shared.update_security_index(
                security_root,
                agent_id="test_agent",
                repo_root=None,
            )
        )

        index_text = (security_root / "INDEX.md").read_text(encoding="utf-8")
        assert "# Security Reports Index" in index_text
        assert "## Security Statistics" in index_text
        assert "auth/2026-01-20_token_leak" in index_text


def test_index_families_share_preflight_write_policy(monkeypatch):
    calls = []

    def _capture_write_policy(index_path: Path, content: str, doc_dir: Path | None = None) -> bool:
        calls.append((index_path.name, doc_dir))
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(content, encoding="utf-8")
        return True

    monkeypatch.setattr(
        special_indexes_shared.preflight_shared,
        "write_index_with_policy",
        _capture_write_policy,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        docs_dir = root / ".scribe" / "docs" / "dev_plans" / "p1"
        research_dir = docs_dir / "research"
        bugs_dir = root / "docs" / "bugs"
        security_dir = root / "docs" / "security"
        research_dir.mkdir(parents=True, exist_ok=True)
        (research_dir / "RESEARCH_A.md").write_text("# Research\n")

        bug_report = bugs_dir / "logic" / "2026-01-20_bug"
        bug_report.mkdir(parents=True, exist_ok=True)
        (bug_report / "report.md").write_text("# Bug\n")

        sec_report = security_dir / "auth" / "2026-01-20_sec"
        sec_report.mkdir(parents=True, exist_ok=True)
        (sec_report / "report.md").write_text("# Security\n")

        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "REVIEW_REPORT_phase0_2026-01-20_1200.md").write_text("# Review\n")
        (docs_dir / "AGENT_REPORT_CARD_Coder_phase0_20260120_1200.md").write_text("# Card\n")

        asyncio.run(special_indexes_shared.update_research_index(research_dir, "test_agent", repo_root=None))
        asyncio.run(special_indexes_shared.update_bug_index(bugs_dir, "test_agent", repo_root=None))
        asyncio.run(
            special_indexes_shared.update_security_index(security_dir, "test_agent", repo_root=None)
        )
        asyncio.run(special_indexes_shared.update_review_index(docs_dir, "test_agent", repo_root=None))
        asyncio.run(
            special_indexes_shared.update_agent_card_index(docs_dir, "test_agent", repo_root=None)
        )

    written_index_names = {name for name, _ in calls}
    assert "INDEX.md" in written_index_names
    assert "REVIEW_INDEX.md" in written_index_names
    assert "AGENT_CARDS_INDEX.md" in written_index_names
    assert len(calls) == 5
    assert all(doc_dir is not None for _, doc_dir in calls)


def test_review_report_template_default_render_has_no_placeholder_bracket_residue():
    with tempfile.TemporaryDirectory() as tmpdir:
        project = {"root": tmpdir, "name": "scaffold_hygiene_proj"}
        rendered = asyncio.run(
            special_indexes_shared.render_review_report_template(
                project,
                agent_id="test_agent",
                prepared_metadata={"stage": "phase_1_review"},
                logger=logging.getLogger(__name__),
            )
        )

        warnings = analyze_scaffold_quality(text=rendered, doc_name="REVIEW_REPORT")
        assert not any(w.get("code") == "SCF_PLACEHOLDER_BRACKET" for w in warnings)


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("family", ["research", "bug", "security"])
@pytest.mark.parametrize("operation", ["scan", "stat", "write", "resolve"])
def test_index_filesystem_work_allows_concurrent_progress(tmp_path, monkeypatch, test_agent, family, operation):
    """Delay real I/O until a sibling runs; timeout is only a deadlock guard.

    This reproduces scheduling starvation, not production filesystem latency.
    """
    root = tmp_path / "docs" / family
    root.mkdir(parents=True)
    report = root / "RESEARCH_A.md" if family == "research" else root / "logic" / "case" / "report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Evidence\n", encoding="utf-8")
    entered, release, progressed = threading.Event(), threading.Event(), threading.Event()
    timed_out = []

    def delay():
        if not entered.is_set():
            entered.set()
            if not release.wait(1):
                timed_out.append(True)

    if operation == "write":
        original = special_indexes_shared.preflight_shared.write_index_with_policy

        def write(*args, **kwargs):
            delay()
            return original(*args, **kwargs)

        monkeypatch.setattr(special_indexes_shared.preflight_shared, "write_index_with_policy", write)
    else:
        method = ("glob" if family == "research" else "iterdir") if operation == "scan" else operation
        original = getattr(Path, method)
        target = root if operation == "scan" else root / "INDEX.md" if operation == "resolve" else report

        def filesystem(path, *args, **kwargs):
            if path == target:
                delay()
            result = original(path, *args, **kwargs)
            return list(result) if operation == "scan" else result

        monkeypatch.setattr(Path, method, filesystem)

    async def run():
        updater = getattr(special_indexes_shared, f"update_{family}_index")
        task = asyncio.create_task(updater(root, test_agent))
        try:
            while not task.done():
                if entered.is_set() and not release.is_set():
                    progressed.set()
                    release.set()
                await asyncio.sleep(0)
            await task
        finally:
            release.set()

    asyncio.run(run())
    assert entered.is_set(), "controlled filesystem boundary was never exercised"
    assert not timed_out, "event loop stalled during real filesystem operation"
    assert progressed.is_set(), "sibling coroutine made no progress during filesystem work"
    assert report.name in (root / "INDEX.md").read_text(encoding="utf-8")


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("family", ["research", "bug", "security"])
def test_missing_index_directory_and_filesystem_errors(tmp_path, monkeypatch, test_agent, family):
    root = tmp_path / "docs" / family
    updater = getattr(special_indexes_shared, f"update_{family}_index")
    asyncio.run(updater(root, test_agent))
    content = (root / "INDEX.md").read_text(encoding="utf-8")
    empty_message = "No research documents" if family == "research" else f"No {'bug' if family == 'bug' else 'security'} reports"
    assert f"*{empty_message} found.*" in content
    method = "glob" if family == "research" else "iterdir"
    original = getattr(Path, method)

    def fail_scan(path, *args, **kwargs):
        if path == root:
            raise PermissionError("controlled scan denial")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, method, fail_scan)
    with pytest.raises(PermissionError, match="controlled scan denial"):
        asyncio.run(updater(root, test_agent))
    assert (root / "INDEX.md").read_text(encoding="utf-8") == content


class _FixedIndexTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 20, 12, 0, tzinfo=tz)


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("family", ["review", "agent_card"])
@pytest.mark.parametrize("operation", ["glob", "iterate", "stat", "render"])
def test_review_card_scan_and_render_allow_concurrent_progress(tmp_path, monkeypatch, test_agent, family, operation):
    """Exercise real files with a controlled wait, not a filesystem speed claim."""
    root = tmp_path / "docs"
    root.mkdir()
    name = "REVIEW_REPORT_phase0_a.md" if family == "review" else "AGENT_REPORT_CARD_Coder_phase0_a.md"
    report = root / name
    report.write_text("# Evidence\n", encoding="utf-8")
    entered, release, progressed = threading.Event(), threading.Event(), threading.Event()
    timed_out = []

    def delay():
        entered.set()
        if not release.wait(1):
            timed_out.append(True)

    if operation == "render":
        original = special_indexes_shared._current_timestamp

        def timestamp():
            delay()
            return original()

        monkeypatch.setattr(special_indexes_shared, "_current_timestamp", timestamp)
    else:
        method = "stat" if operation == "stat" else "glob"
        original = getattr(Path, method)

        def filesystem(path, *args, **kwargs):
            if path == (report if operation == "stat" else root):
                if operation == "iterate":
                    def entries():
                        delay()
                        yield from original(path, *args, **kwargs)
                    return entries()
                delay()
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, method, filesystem)

    async def run():
        task = asyncio.create_task(getattr(special_indexes_shared, f"update_{family}_index")(root, test_agent))
        try:
            while not task.done():
                if entered.is_set():
                    progressed.set()
                    release.set()
                await asyncio.sleep(0)
            await task
        finally:
            release.set()

    asyncio.run(run())
    assert entered.is_set()
    assert not timed_out, "event loop stalled during scan/render"
    assert progressed.is_set()
    index_name = "REVIEW_INDEX.md" if family == "review" else "AGENT_CARDS_INDEX.md"
    assert name in (root / index_name).read_text(encoding="utf-8")


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("family", ["review", "agent_card"])
def test_review_card_content_and_sync_parity(tmp_path, monkeypatch, test_agent, family):
    from scribe_mcp import object_store

    class NonUtcLocalTime(_FixedIndexTime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 20, 12 if tz is not None else 7, 0, tzinfo=tz)

    monkeypatch.setattr(special_indexes_shared, "datetime", NonUtcLocalTime)
    root = tmp_path / "docs"
    root.mkdir()
    review = family == "review"
    index_name = "REVIEW_INDEX.md" if review else "AGENT_CARDS_INDEX.md"
    index_path = root / index_name
    index_path.write_text("invalid", encoding="utf-8")
    entries = []
    # Deliberately create oldest first; grouped display must retain newest first.
    for number in range(23):
        group = "beta" if number < 6 else "alpha"
        name = f"REVIEW_REPORT_{group}_{number:02}" if review else f"AGENT_REPORT_CARD_{group}_phase0_{number:02}"
        path = root / f"{name}.md"
        path.write_text("abc", encoding="utf-8")
        os.utime(path, (1000 + number, 1000 + number))
        entries.append((name, group, 1000 + number))
    for name in [index_name + ".backup", "_private.md", "unrelated.md", "REVIEW_REPORT_ignored.txt", "AGENT_REPORT_CARD_ignored.txt"]:
        (root / name).write_text("ignored", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / f"{entries[0][0]}_nested.md").write_text("ignored", encoding="utf-8")
    entries.reverse()
    recent = "".join(
        f"- **[{name}]({name}.md)** - {group} - "
        + ("" if review else "phase0 - ")
        + f"{datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M}\n"
        for name, group, mtime in entries[:20]
    )
    grouped = ""
    for group in ["alpha", "beta"]:
        members = [name for name, entry_group, _ in entries if entry_group == group]
        grouped += f"### {group.title() if review else group} ({len(members)} {'reports' if review else 'evaluations'})\n"
        grouped += "".join(f"- [{name}]({name}.md)\n" for name in members[:5])
        grouped += f"- ... and {len(members) - 5} more\n\n"
    timestamp = "2026-01-20 12:00:00 UTC"
    if review:
        expected = f"""# Review Reports Index

*Last Updated: {timestamp}*

This directory contains review reports generated during the development quality assurance process.

## Review Statistics

- **Total Reports:** 23
- **Stages Reviewed:** 2

## Recent Review Reports

{recent}
*... and 3 older reports*

## Browse by Stage

{grouped}

## Index Information

- **Index Location:** `{index_path}`
- **Total Stages:** 2
- **Last Scan:** {timestamp}

---

*This index is automatically updated when review reports are created or modified.*"""
    else:
        expected = f"""# Agent Report Cards Index

*Last Updated: {timestamp}*

This directory contains agent performance evaluation reports generated during the development process.

## Agent Statistics

- **Total Reports:** 23
- **Agents Evaluated:** 2
- **Stages Covered:** 1

## Recent Agent Evaluations

{recent}
*... and 3 older evaluations*

## Browse by Agent

{grouped}

## Index Information

- **Index Location:** `{index_path}`
- **Total Agents:** 2
- **Last Scan:** {timestamp}

---

*This index is automatically updated when agent report cards are created or modified.*"""
    synced = []

    async def sync(path, content, repo_root):
        assert path.read_text(encoding="utf-8") == content
        synced.append((path, content, repo_root))

    monkeypatch.setattr(object_store, "sync_file_to_store", sync)
    asyncio.run(getattr(special_indexes_shared, f"update_{family}_index")(root, test_agent, repo_root=tmp_path))
    assert index_path.read_text(encoding="utf-8") == expected
    assert synced == [(index_path, expected, tmp_path)]


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("family", ["review", "agent_card"])
@pytest.mark.parametrize("failure", ["glob", "iterate", "stat_missing", "stat_denied"])
def test_review_card_missing_directory_and_scan_errors(tmp_path, monkeypatch, test_agent, family, failure):
    root = tmp_path / "missing"
    updater = getattr(special_indexes_shared, f"update_{family}_index")
    asyncio.run(updater(root, test_agent))
    index_path = root / ("REVIEW_INDEX.md" if family == "review" else "AGENT_CARDS_INDEX.md")
    content = index_path.read_text(encoding="utf-8")
    assert ("*No review reports found.*" if family == "review" else "*No agent report cards found.*") in content
    report = root / ("REVIEW_REPORT_phase0_a.md" if family == "review" else "AGENT_REPORT_CARD_Coder_phase0_a.md")
    report.write_text("# Evidence\n", encoding="utf-8")
    method = "stat" if failure.startswith("stat") else "glob"
    original = getattr(Path, method)
    error = FileNotFoundError if failure == "stat_missing" else PermissionError

    def filesystem(path, *args, **kwargs):
        if path == (report if method == "stat" else root):
            if failure == "iterate":
                def entries():
                    raise error("controlled discovery failure")
                    yield
                return entries()
            raise error("controlled discovery failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, method, filesystem)
    with pytest.raises(error, match="controlled discovery failure"):
        asyncio.run(updater(root, test_agent))
    assert index_path.read_text(encoding="utf-8") == content


@pytest.mark.core
@pytest.mark.regression
def test_index_utc_label_uses_utc_clock(tmp_path, monkeypatch):
    class NonUtcLocalTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 20, 12 if tz is not None else 7, 0, tzinfo=tz)

    monkeypatch.setattr(special_indexes_shared, "datetime", NonUtcLocalTime)
    content = special_indexes_shared._build_research_index(tmp_path / "research")
    assert "Last Updated: 2026-01-20 12:00:00 UTC" in content


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("family", ["research", "bug", "security"])
def test_index_real_filesystem_content_and_sync_parity(tmp_path, monkeypatch, test_agent, family):
    from scribe_mcp import object_store

    monkeypatch.setattr(special_indexes_shared, "datetime", _FixedIndexTime)
    root = tmp_path / "docs" / family
    root.mkdir(parents=True)
    synced = []

    async def sync(path, content, repo_root):
        assert path.read_text(encoding="utf-8") == content
        synced.append((path, content, repo_root))

    monkeypatch.setattr(object_store, "sync_file_to_store", sync)
    (root / "INDEX.md").write_text("invalid", encoding="utf-8")
    (root / "INDEX.invalid.backup").write_text("stale", encoding="utf-8")
    timestamp = "2026-01-20 12:00:00 UTC"
    if family == "research":
        for name, mtime in [("OLDER.md", 1000), ("NEWER.md", 2000), ("_private.md", 3000), ("ignored.txt", 4000)]:
            path = root / name
            path.write_text("abc", encoding="utf-8")
            os.utime(path, (mtime, mtime))
        nested = root / "nested"
        nested.mkdir()
        (nested / "hidden.md").write_text("hidden", encoding="utf-8")
        rows = "".join(
            f"- **[{name}]({name}.md)** - {datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M} (3 bytes)\n"
            for name, mtime in [("NEWER", 2000), ("OLDER", 1000)]
        )
        expected = f"""# Research Documents Index

*Last Updated: {timestamp}*

This directory contains research documents generated during the development process.

## Available Research Documents

{rows}

## Index Information

- **Total Documents:** 2
- **Index Location:** `docs/{family}/INDEX.md`

---

*This index is automatically updated when research documents are created or modified.*"""
        kwargs = {}
    else:
        for number in range(23):
            report = root / "logic" / f"case_{number:02}" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("abc", encoding="utf-8")
            os.utime(report, (1000 + number, 1000 + number))
        for category in ["archived", "excluded"]:
            report = root / category / "hidden" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("hidden", encoding="utf-8")
        (root / "loose.txt").write_text("ignored", encoding="utf-8")
        (root / "logic" / "loose.txt").write_text("ignored", encoding="utf-8")
        (root / "logic" / "missing_report").mkdir()
        label = "Bug" if family == "bug" else "Security"
        heading = f"{label} Reports"
        recent = "".join(
            f"- **[logic/case_{n:02}](logic/case_{n:02}/report.md)** - {datetime.fromtimestamp(1000 + n):%Y-%m-%d %H:%M}\n"
            for n in range(22, 2, -1)
        )
        category_rows = "".join(f"- [case_{n:02}](logic/case_{n:02}/report.md)\n" for n in range(22, 17, -1))
        expected = f"""# {heading} Index

*Last Updated: {timestamp}*

This directory contains {heading.lower()} generated during development and testing.

## {label} Statistics

- **Total Reports:** 23
- **Categories:** 1

## Recent {heading}

{recent}
*... and 3 older reports*

## Browse by Category

### Logic (23 reports)
{category_rows}- ... and 18 more

---

## Index Information

- **Index Location:** `{root / 'INDEX.md'}`
- **Total Categories:** 1
- **Last Scan:** {timestamp}

---

*This index is automatically updated when {heading.lower()} are created or modified.*"""
        kwargs = {"exclude_paths": (path for path in [root / "excluded" / "hidden" / "report.md"])}
    asyncio.run(getattr(special_indexes_shared, f"update_{family}_index")(root, test_agent, repo_root=tmp_path, **kwargs))
    assert (root / "INDEX.md").read_text(encoding="utf-8") == expected
    assert not (root / "INDEX.invalid.backup").exists()
    assert synced == [(root / "INDEX.md", expected, tmp_path)]


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("family", ["research", "bug", "security", "review", "agent_card"])
@pytest.mark.parametrize("failure", ["policy_false", "policy_error", "sync_error"])
def test_index_persistence_error_contract(tmp_path, monkeypatch, test_agent, family, failure):
    from scribe_mcp import object_store

    root = tmp_path / "docs" / family
    root.mkdir(parents=True)
    index_name = {"review": "REVIEW_INDEX.md", "agent_card": "AGENT_CARDS_INDEX.md"}.get(family, "INDEX.md")
    synced = []

    async def sync(path, content, repo_root):
        synced.append((path, content, repo_root))
        if failure == "sync_error":
            raise OSError("controlled store failure")

    monkeypatch.setattr(object_store, "sync_file_to_store", sync)
    if failure != "sync_error":
        def policy(*args):
            if failure == "policy_error":
                raise OSError("controlled policy failure")
            return False

        monkeypatch.setattr(special_indexes_shared.preflight_shared, "write_index_with_policy", policy)

    operation = getattr(special_indexes_shared, f"update_{family}_index")(root, test_agent, repo_root=tmp_path)
    if failure == "policy_error":
        with pytest.raises(OSError, match="controlled policy failure"):
            asyncio.run(operation)
        assert not synced
    else:
        asyncio.run(operation)
        assert len(synced) == 1
        assert synced[0][0] == root / index_name
        assert synced[0][2] == tmp_path
        if failure == "sync_error":
            assert synced[0][1] == (root / index_name).read_text(encoding="utf-8")
        else:
            # A false policy result has historically still attempted store sync.
            assert not (root / index_name).exists()


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("family", ["research", "bug", "security", "review", "agent_card"])
@pytest.mark.parametrize("repeat_cancel", [False, True])
def test_cancelled_index_write_finishes_before_operation_releases_lock(tmp_path, monkeypatch, test_agent, family, repeat_cancel):
    from scribe_mcp import object_store

    root = tmp_path / "docs" / family
    root.mkdir(parents=True)
    entered, release, completed = threading.Event(), threading.Event(), threading.Event()
    order = []
    original = special_indexes_shared.preflight_shared.write_index_with_policy

    def slow_write(*args):
        entered.set()
        if not release.wait(2):
            raise TimeoutError("slow-write guard exhausted")
        result = original(*args)
        order.append("write_complete")
        completed.set()
        return result

    async def sync(*args):
        order.append("sync")
        assert completed.is_set()

    monkeypatch.setattr(special_indexes_shared.preflight_shared, "write_index_with_policy", slow_write)
    monkeypatch.setattr(object_store, "sync_file_to_store", sync)

    async def run():
        lock = asyncio.Lock()

        async def update_under_lock():
            async with lock:
                try:
                    await getattr(special_indexes_shared, f"update_{family}_index")(root, test_agent, repo_root=tmp_path)
                finally:
                    order.append("operation_exit")

        task = asyncio.create_task(update_under_lock())
        try:
            while not entered.is_set() and not task.done():
                await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            if repeat_cancel:
                task.cancel()
                await asyncio.sleep(0)
            state_during_write = (task.done(), lock.locked(), completed.is_set())
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert state_during_write == (False, True, False)
        assert not lock.locked()

    asyncio.run(run())
    assert completed.is_set()
    assert order == ["write_complete", "operation_exit"]
    index_name = {"review": "REVIEW_INDEX.md", "agent_card": "AGENT_CARDS_INDEX.md"}.get(family, "INDEX.md")
    assert "# " in (root / index_name).read_text(encoding="utf-8")
