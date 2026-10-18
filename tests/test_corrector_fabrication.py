"""The parameter corrector must preserve or refuse — never fabricate a value.

Three data-integrity defects shared one cause: the corrector invented a value
rather than passing the caller's through or refusing it. Message text was
truncated to 1000 chars, a missing `content` became "No message provided", and a
None metadata value became the literal string "None" — which `replace_text` then
wrote into documents while reporting success.

A fabricated value is indistinguishable downstream from a caller who genuinely
meant it, which is what makes it corruption rather than a rejected input.
"""

from __future__ import annotations

import pytest

from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector


pytestmark = pytest.mark.regression


class TestNoneIsPreservedNotStringified:
    """A None metadata value must stay None so its owning boundary can refuse it."""

    def test_none_value_is_preserved(self) -> None:
        corrected = BulletproofParameterCorrector.correct_metadata_parameter(
            {"find": "X", "replace": None}
        )
        assert corrected["replace"] is None
        assert corrected["replace"] != "None"

    def test_none_is_preserved_for_arbitrary_keys(self) -> None:
        corrected = BulletproofParameterCorrector.correct_metadata_parameter(
            {"phase": None, "component": None}
        )
        assert corrected == {"phase": None, "component": None}

    def test_the_literal_string_none_is_still_carried_through(self) -> None:
        """A caller who really means the word "None" keeps it.

        This is the reason string-matching "None" downstream would be the wrong
        fix: the word is legitimate content.
        """
        corrected = BulletproofParameterCorrector.correct_metadata_parameter(
            {"replace": "None"}
        )
        assert corrected["replace"] == "None"


class TestOtherValuesAreUnaffected:
    """The None fix must not disturb the corrector's existing conversions."""

    def test_scalars_pass_through(self) -> None:
        corrected = BulletproofParameterCorrector.correct_metadata_parameter(
            {"count": 3, "ratio": 1.5, "enabled": True}
        )
        assert corrected == {"count": 3, "ratio": 1.5, "enabled": True}

    def test_containers_pass_through(self) -> None:
        corrected = BulletproofParameterCorrector.correct_metadata_parameter(
            {"tags": ["a", "b"], "nested": {"k": "v"}}
        )
        assert corrected == {"tags": ["a", "b"], "nested": {"k": "v"}}

    def test_non_stringable_object_still_becomes_a_safe_marker(self) -> None:
        class Hostile:
            def __str__(self) -> str:  # pragma: no cover - exercised via corrector
                raise RuntimeError("cannot stringify")

        corrected = BulletproofParameterCorrector.correct_metadata_parameter(
            {"weird": Hostile()}
        )
        assert corrected["weird"] == "invalid_value"

    def test_exact_match_payload_keys_are_still_preserved_verbatim(self) -> None:
        """`find`/`replace` carry exact document text; sanitizing corrupts matching."""
        payload = "line one\nline two | piped"
        corrected = BulletproofParameterCorrector.correct_metadata_parameter(
            {"find": payload, "replace": payload}
        )
        assert corrected["find"] == payload
        assert corrected["replace"] == payload
