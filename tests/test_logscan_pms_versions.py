"""Unit tests for :mod:`modules.logscan_pms_versions`.

Extracted alongside PR that moved the PMS-version helpers out of
``modules.logscan``.  The originals lived inside ``logscan.py`` with
no dedicated test file -- the only coverage was via integration
tests of ``LogscanAnalyzer.make_recommendations``.  These focused
unit tests fill that gap so future edits to the vulnerable-range
constants or the parsing helper can be verified in isolation.
"""

from __future__ import annotations

import pytest

from modules.logscan_pms_versions import (
    VULNERABLE_RANGE_HIGH,
    VULNERABLE_RANGE_LOW,
    format_version_tuple,
    is_vulnerable_pms_version,
    parse_version_tuple,
    version_in_inclusive_range,
)


class TestParseVersionTuple:
    def test_full_four_component_version(self):
        assert parse_version_tuple("1.41.7.9100") == (1, 41, 7, 9100)

    def test_trims_trailing_suffix_after_hyphen(self):
        assert parse_version_tuple("1.42.0.9700-abcd123") == (1, 42, 0, 9700)

    def test_pads_missing_components_with_zero(self):
        assert parse_version_tuple("1.41") == (1, 41, 0, 0)

    def test_empty_string_returns_all_zeros(self):
        assert parse_version_tuple("") == (0, 0, 0, 0)

    def test_non_integer_components_default_to_zero(self):
        # Kometa's log lines sometimes have garbled version fragments;
        # never raise -- just coerce non-int chunks to 0.
        assert parse_version_tuple("1.abc.7.9100") == (1, 0, 7, 9100)

    def test_ignores_extra_components_beyond_four(self):
        assert parse_version_tuple("1.2.3.4.5.6") == (1, 2, 3, 4)

    def test_strips_surrounding_whitespace_on_suffix(self):
        assert parse_version_tuple("  1.2.3.4  ") == (1, 2, 3, 4)


class TestVersionInInclusiveRange:
    def test_at_lower_bound_is_included(self):
        assert version_in_inclusive_range("1.41.7.0", (1, 41, 7, 0), (1, 42, 0, 99999))

    def test_at_upper_bound_is_included(self):
        assert version_in_inclusive_range("1.42.0.99999", (1, 41, 7, 0), (1, 42, 0, 99999))

    def test_below_range_is_excluded(self):
        assert not version_in_inclusive_range("1.41.6.9999", (1, 41, 7, 0), (1, 42, 0, 99999))

    def test_above_range_is_excluded(self):
        assert not version_in_inclusive_range("1.42.1.0", (1, 41, 7, 0), (1, 42, 0, 99999))

    def test_inside_range(self):
        assert version_in_inclusive_range("1.42.0.100", (1, 41, 7, 0), (1, 42, 0, 99999))


class TestIsVulnerablePmsVersion:
    """Wraps the module-level range constants; when those move the tests move."""

    def test_flags_current_vulnerable_version(self):
        # 1.41.7.x should be flagged.
        assert is_vulnerable_pms_version("1.41.7.9100")
        assert is_vulnerable_pms_version("1.42.0.9700")

    def test_does_not_flag_older_versions(self):
        assert not is_vulnerable_pms_version("1.40.5.8000")

    def test_does_not_flag_patched_versions(self):
        # Anything past 1.42.0.99999 should be considered patched.
        assert not is_vulnerable_pms_version("1.42.1.0")
        assert not is_vulnerable_pms_version("1.43.0.100")

    def test_handles_suffixed_versions(self):
        assert is_vulnerable_pms_version("1.41.7.9100-abc123")


class TestFormatVersionTuple:
    def test_full_four_component(self):
        assert format_version_tuple((1, 41, 7, 0)) == "1.41.7.0"

    def test_matches_range_constants(self):
        # Round-trip: format each constant and confirm parse gets it back.
        for constant in (VULNERABLE_RANGE_LOW, VULNERABLE_RANGE_HIGH):
            rendered = format_version_tuple(constant)
            assert parse_version_tuple(rendered) == constant

    def test_three_component_tuple(self):
        assert format_version_tuple((1, 2, 3)) == "1.2.3"

    def test_single_component(self):
        assert format_version_tuple((42,)) == "42"


class TestRangeConstantsSanity:
    """Guard rails on the module-level constants themselves."""

    def test_low_is_below_high(self):
        assert VULNERABLE_RANGE_LOW < VULNERABLE_RANGE_HIGH

    def test_constants_are_four_component_tuples(self):
        assert len(VULNERABLE_RANGE_LOW) == 4
        assert len(VULNERABLE_RANGE_HIGH) == 4

    def test_constants_are_all_ints(self):
        for constant in (VULNERABLE_RANGE_LOW, VULNERABLE_RANGE_HIGH):
            for component in constant:
                assert isinstance(component, int)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
