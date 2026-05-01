from __future__ import annotations

import json

from scribe_mcp.progress_log_parser import (
    compile_meta_filters,
    parse_filter_time,
    parse_lines,
    render_entry,
    run_cli,
    search_entries,
    summarize,
)


def test_parse_lines_multiline_and_malformed_meta() -> None:
    lines = [
        "intro",
        "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Started | priority=high; broken-frag; tags=[\"x\"]",
        "continued detail line",
    ]
    entries = parse_lines(lines)

    assert len(entries) == 1
    assert "continued detail line" in entries[0].message
    assert entries[0].meta["priority"] == "high"
    assert entries[0].meta["tags"] == ["x"]
    assert entries[0].meta["_extra"] == ["broken-frag"]


def test_search_filters_cover_agent_project_priority_category_tag_meta_since_until_tail_query_regex() -> None:
    lines = [
        "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Start feature | priority=high; category=milestone; tags=[\"parser\"]; run=7",
        "[ℹ️] [2026-05-01 02:00:00 UTC] [Agent: Mantis] [Project: Alpha] Follow-up check | priority=medium; category=investigation; tags=[\"regex\"]; run=8",
        "[⚠️] [2026-05-01 03:00:00 UTC] [Agent: Forge] [Project: Beta] tool friction note | priority=low; category=investigation; tags=[\"tool-friction\"]; run=9",
    ]
    entries = parse_lines(lines)

    results = search_entries(
        entries,
        newest_first=False,
        limit=0,
        agent="forge",
        project="alpha",
        priority="high",
        category="milestone",
        tag="parser",
        meta_filters=compile_meta_filters(["run=7"]),
        query="feature",
    )
    assert len(results) == 1

    regex_results = search_entries(entries, newest_first=False, limit=0, regex=__import__("re").compile("friction", __import__("re").I))
    assert len(regex_results) == 1

    tail_results = search_entries(entries, newest_first=False, limit=0, tail=1)
    assert len(tail_results) == 1
    assert tail_results[0].project == "Beta"

    since_results = search_entries(
        entries,
        newest_first=False,
        limit=0,
        since=parse_filter_time("2026-05-01 02:00:00 UTC"),
    )
    assert [entry.agent for entry in since_results] == ["Mantis", "Forge"]

    until_results = search_entries(
        entries,
        newest_first=False,
        limit=0,
        until=parse_filter_time("2026-05-01 02:00:00 UTC", end_of_day=True),
    )
    assert [entry.agent for entry in until_results] == ["Forge", "Mantis"]

    summary = summarize(entries)
    assert summary["entries"] == 3
    assert summary["projects"]["Alpha"] == 2


def test_run_cli_invalid_regex_returns_2(tmp_path, capsys) -> None:
    log = tmp_path / "log.md"
    log.write_text("[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Start\n", encoding="utf-8")

    code = run_cli([str(log), "--regex", "("])
    err = capsys.readouterr().err
    assert code == 2
    assert "Invalid --regex" in err


def test_run_cli_json_and_ndjson_outputs(tmp_path, capsys) -> None:
    log = tmp_path / "log.md"
    log.write_text(
        "\n".join(
            [
                "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Start | priority=high",
                "[ℹ️] [2026-05-01 02:00:00 UTC] [Agent: Mantis] [Project: Alpha] Follow-up | priority=medium",
            ]
        ),
        encoding="utf-8",
    )

    code_json = run_cli([str(log), "--json", "--limit", "0", "--oldest-first"])
    out_json = capsys.readouterr().out
    assert code_json == 0
    parsed = json.loads(out_json)
    assert len(parsed) == 2
    assert parsed[0]["agent"] == "Forge"

    code_ndjson = run_cli([str(log), "--ndjson", "--limit", "1"])
    out_ndjson = capsys.readouterr().out.strip().splitlines()
    assert code_ndjson == 0
    assert len(out_ndjson) == 1
    assert json.loads(out_ndjson[0])["agent"] in {"Forge", "Mantis"}


def test_render_entry_shape_no_meta_and_width() -> None:
    lines = [
        "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] This message is intentionally long for truncation checks | priority=high",
    ]
    entry = parse_lines(lines)[0]

    with_meta = render_entry(entry, show_meta=True, width=20)
    assert with_meta.startswith("#1 line 1 ✅ [2026-05-01 01:00:00 UTC] Forge/Alpha")
    assert "\n  This message is int…" in with_meta
    assert "\n  meta: {\"priority\": \"high\"}" in with_meta

    no_meta = render_entry(entry, show_meta=False, width=20)
    assert "\n  meta:" not in no_meta
