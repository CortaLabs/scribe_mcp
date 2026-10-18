"""Regression tests for P1.7 — append_entry heals pipe characters.

Live-reproduced defect (2026-06-11): logging an entry describing the
pipe-sanitization bug was rejected with "Message cannot contain pipe
characters." — the one validator with no healing path, violating the
"logging must never be blocked" invariant. Pipes now heal to the broken
bar (¦), preserving the rendered log line's message↔meta delimiter.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.tools.append_entry import _sanitize_message, _validate_message


def test_pipe_heals_to_broken_bar():
    healed = _sanitize_message("replace | with ; in metadata")
    assert "|" not in healed
    assert "¦" in healed
    assert _validate_message(healed) is None


def test_newlines_still_escape():
    healed = _sanitize_message("line one\nline two")
    assert "\n" not in healed
    assert "\\n" in healed
    assert _validate_message(healed) is None


def test_combined_pipe_and_newline():
    healed = _sanitize_message("a|b\nc|d")
    assert _validate_message(healed) is None
    assert healed == "a¦b\\nc¦d"


def test_clean_message_unchanged():
    msg = "ordinary log message with no special characters"
    assert _sanitize_message(msg) == msg
    assert _validate_message(msg) is None


def test_empty_message_passthrough():
    assert _sanitize_message("") == ""
