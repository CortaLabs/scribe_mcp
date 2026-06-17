"""Regression guards for case-registry lifecycle correctness.

Three defects this protects against:

1. Divergent open/closed status vocab between link_fix (sentinel_tools) and
   list_open_cases. They previously hard-coded separate sets, so a case could be
   "closed" to the lister but still "open" to link_fix (and vice versa) — e.g.
   ``wontfix`` was closed to the lister but did not close the case in link_fix,
   while ``merged``/``implemented``/``landed``/``validated`` closed in link_fix
   but were not in the lister's closed set. Both now read one canonical source.

2. link_fix flattening every terminal status to a generic "closed". A non-fix
   closure (wontfix/duplicate/false_positive/mitigated) must preserve its reason
   as the recorded case status.

3. (F2) ``resolve_custom_doc_path`` collapsing a case path onto an unrelated
   report via a ``doc_name in report_dir_name`` substring match, and returning
   an arbitrary first glob hit. The filesystem report-resolution path now matches
   by EXACT case_id / exact ``_{doc_name}`` slug-suffix and REFUSES (returns
   ``None``) when more than one report matches the same identifier.
"""

from __future__ import annotations

from pathlib import Path

from scribe_mcp.doc_management import utils as doc_utils
from scribe_mcp.tools import list_open_cases as loc


# --- F2 filesystem fixtures (no DB; pure path resolution) --------------------

def _write_bug_report(
    project_root: Path,
    *,
    category: str,
    case_dir: str,
    case_id: str,
) -> Path:
    """Create a bug report at docs/bugs/<category>/<case_dir>/report.md.

    Layout mirrors the real case-report tree the resolver globs
    (``docs/bugs/*/*/report.md``). Frontmatter carries ``doc_type``/``case_id``
    so ``classify_scribe_source_document`` classifies it as a bug_report.
    """
    report_dir = project_root / "docs" / "bugs" / category / case_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / "report.md"
    report.write_text(
        f"---\ndoc_type: bug_report\ncase_id: {case_id}\n---\n\n# Report\n",
        encoding="utf-8",
    )
    return report


def _project(project_root: Path) -> dict:
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "proj"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "root": str(project_root),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
    }


def test_f2_ambiguous_case_id_refuses_rather_than_guessing(tmp_path):
    # Two distinct reports share the SAME case_id. The resolver must REFUSE
    # (return None) instead of returning an arbitrary first glob hit.
    _write_bug_report(tmp_path, category="logic", case_dir="20260101_dup", case_id="BUG-DUP")
    _write_bug_report(tmp_path, category="runtime", case_dir="20260102_dup", case_id="BUG-DUP")

    resolved = doc_utils.resolve_custom_doc_path(_project(tmp_path), "bugs", "BUG-DUP")
    assert resolved is None


def test_f2_unique_case_id_resolves(tmp_path):
    # A single report with the requested case_id resolves to exactly that file.
    report = _write_bug_report(
        tmp_path, category="logic", case_dir="20260101_solo", case_id="BUG-SOLO"
    )
    resolved = doc_utils.resolve_custom_doc_path(_project(tmp_path), "bugs", "BUG-SOLO")
    assert resolved == report


def test_f2_unique_slug_suffix_resolves(tmp_path):
    # No case_id frontmatter match; resolution falls back to a unique exact
    # ``_{doc_name}`` directory-suffix match.
    report = _write_bug_report(
        tmp_path, category="logic", case_dir="20260101_login", case_id="BUG-1"
    )
    resolved = doc_utils.resolve_custom_doc_path(_project(tmp_path), "bugs", "login")
    assert resolved == report


def test_f2_substring_no_longer_collapses_unrelated_report(tmp_path):
    # The core F2 defect: requesting slug ``auth`` must NOT collapse onto an
    # unrelated ``_oauth_flow`` report (whose dir merely *contains* "auth").
    # Old code matched ``"auth" in "20260101_oauth_flow"`` (True) and returned it.
    _write_bug_report(
        tmp_path, category="logic", case_dir="20260101_oauth_flow", case_id="BUG-OAUTH"
    )
    resolved = doc_utils.resolve_custom_doc_path(_project(tmp_path), "bugs", "auth")
    assert resolved is None


def test_link_fix_and_list_open_cases_share_one_closed_vocab():
    # list_open_cases must source its closed set from the canonical doc_utils set,
    # not a private divergent copy.
    assert loc._CLOSED_STATUS_VALUES is doc_utils.CASE_CLOSED_STATUS_VALUES
    assert loc._OPEN_STATUS_VALUES is doc_utils.CASE_OPEN_STATUS_VALUES


def test_previously_divergent_statuses_now_agree():
    # These were in exactly one of the two old sets — they must agree now.
    for status in ("merged", "implemented", "landed", "validated", "completed"):
        assert doc_utils.case_status_closes(status), f"{status} should close"
        assert not loc._is_open_case_status(status), f"{status} should not be open"
    for status in ("wontfix", "won't fix", "duplicate", "false_positive", "mitigated"):
        assert doc_utils.case_status_closes(status), f"{status} should close"
        assert not loc._is_open_case_status(status), f"{status} should not be open"


def test_open_statuses_stay_open_for_both():
    for status in ("open", "investigating", "triage", "in_progress", "todo", "new"):
        assert not doc_utils.case_status_closes(status)
        assert loc._is_open_case_status(status)


def test_normalization_is_shared_and_space_insensitive():
    # "won't fix" (space) and "won't_fix" (underscore) must both resolve closed —
    # the two call sites previously normalized differently (one kept spaces).
    assert doc_utils.normalize_case_status("Won't Fix") == "won't_fix"
    assert doc_utils.case_status_closes("Won't Fix")
    assert not loc._is_open_case_status("WON'T FIX")


def test_close_status_preserves_nonfix_reason_but_collapses_fix():
    # Non-fix terminal statuses keep their reason as the recorded status.
    assert doc_utils.resolved_case_close_status("wontfix") == "wontfix"
    assert doc_utils.resolved_case_close_status("duplicate") == "duplicate"
    assert doc_utils.resolved_case_close_status("false_positive") == "false_positive"
    # Fix terminal statuses collapse to "closed".
    assert doc_utils.resolved_case_close_status("merged") == "closed"
    assert doc_utils.resolved_case_close_status("resolved") == "closed"
    # Non-terminal statuses leave the case open (no close).
    assert doc_utils.resolved_case_close_status("investigating") is None
    assert doc_utils.resolved_case_close_status("") is None
