"""Unit tests for :mod:`modules.logscan_library_stats`.

Extracted alongside the PR that moved library / section stats
extraction out of :class:`modules.logscan.LogscanAnalyzer`.

Existing coverage via the LogscanAnalyzer method wrappers still
lives in tests/test_logscan_runtime_parse.py -- these focused
tests target the pure helpers directly, especially the priority
rules inside :func:`extract_library_counts` that are easy to
regress.
"""

from __future__ import annotations

import pytest

from modules.logscan_library_stats import (
    count_log_levels,
    extract_config_line_count,
    extract_library_counts,
    extract_section_runtimes,
    match_library_name,
    normalize_library_name,
    parse_hms_to_seconds,
)

# ---------------------------------------------------------------------------
# parse_hms_to_seconds
# ---------------------------------------------------------------------------


class TestParseHmsToSeconds:
    def test_hms(self):
        assert parse_hms_to_seconds("1:30:45") == 5445

    def test_ms(self):
        assert parse_hms_to_seconds("5:30") == 330

    def test_bare_int(self):
        assert parse_hms_to_seconds("42") == 42

    def test_whitespace_stripped(self):
        assert parse_hms_to_seconds("  1:30:45  ") == 5445

    def test_none_returns_none(self):
        assert parse_hms_to_seconds(None) is None

    def test_empty_returns_none(self):
        assert parse_hms_to_seconds("") is None

    def test_non_numeric_returns_none(self):
        assert parse_hms_to_seconds("not a time") is None

    def test_too_many_parts_returns_none(self):
        # 4 colon-separated parts is not a supported form.
        assert parse_hms_to_seconds("1:2:3:4") is None


# ---------------------------------------------------------------------------
# extract_section_runtimes
# ---------------------------------------------------------------------------


class TestExtractSectionRuntimes:
    def test_empty_content_returns_empty_dict(self):
        assert extract_section_runtimes("") == {}
        assert extract_section_runtimes(None) == {}

    def test_inline_form(self):
        content = "Finished Movies in 0:02:14"
        assert extract_section_runtimes(content) == {"Movies": 134}

    def test_split_form(self):
        content = "Finished Overlays\n   Overlays Run Time: 0:00:30"
        assert extract_section_runtimes(content) == {"Overlays": 30}

    def test_sums_multiple_occurrences(self):
        content = "Finished Movies in 0:02:14\nFinished Movies in 0:01:30"
        # 134 + 90 = 224 seconds total
        assert extract_section_runtimes(content) == {"Movies": 224}

    def test_ignores_finished_run_banner(self):
        # "Finished Run" is the whole-log marker, not a section.
        content = "Finished Run\n   Run Time: 1:00:00"
        assert extract_section_runtimes(content) == {}

    def test_ignores_finished_at_lines(self):
        # "Finished at: HH:MM:SS" -- Kometa sometimes uses this and
        # it looks close enough to trip the inline pattern.
        content = "Finished at: 08:30:00 in 0:00:30"
        # 'at:' prefixed section is skipped
        assert extract_section_runtimes(content) == {}


# ---------------------------------------------------------------------------
# count_log_levels
# ---------------------------------------------------------------------------


class TestCountLogLevels:
    def test_all_levels(self):
        content = "\n".join(
            [
                "[DEBUG] one",
                "[INFO] two",
                "[WARNING] three",
                "[ERROR] four",
                "[CRITICAL] five",
                "TRACEBACK line",
            ]
        )
        assert count_log_levels(content) == {
            "debug": 1,
            "info": 1,
            "warning": 1,
            "error": 1,
            "critical": 1,
            "trace": 1,
        }

    def test_empty_content(self):
        assert count_log_levels("") == {
            "debug": 0,
            "info": 0,
            "warning": 0,
            "error": 0,
            "critical": 0,
            "trace": 0,
        }

    def test_case_insensitive(self):
        # Lower/mixed case still matches (implementation upper-cases first).
        assert count_log_levels("[debug] hi")["debug"] == 1
        assert count_log_levels("[Info] hi")["info"] == 1

    def test_traceback_matches_anywhere(self):
        content = "some line before Traceback (most recent call last):"
        assert count_log_levels(content)["trace"] == 1


# ---------------------------------------------------------------------------
# normalize_library_name
# ---------------------------------------------------------------------------


class TestNormalizeLibraryName:
    def test_lowercases(self):
        assert normalize_library_name("MyMovies") == "mymovies"

    def test_underscores_and_dashes_become_spaces(self):
        assert normalize_library_name("4K_TV-Shows") == "4k tv shows"

    def test_strips_punctuation(self):
        assert normalize_library_name("Movies!! (HD)") == "movies hd"

    def test_collapses_multiple_spaces(self):
        assert normalize_library_name("A   B") == "a b"

    def test_empty_returns_empty(self):
        assert normalize_library_name("") == ""

    def test_none_returns_empty(self):
        assert normalize_library_name(None) == ""


# ---------------------------------------------------------------------------
# match_library_name
# ---------------------------------------------------------------------------


class TestMatchLibraryName:
    @pytest.fixture
    def entries(self):
        return [
            {"name": "Movies"},
            {"name": "TV Shows"},
            {"name": "4K Movies"},
        ]

    def test_exact_normalized_match_wins(self, entries):
        assert match_library_name("movies", entries) == "Movies"

    def test_underscore_normalized_match(self, entries):
        assert match_library_name("4k_movies", entries) == "4K Movies"

    def test_longest_substring_wins(self, entries):
        # "movie" is a substring of both "movies" and "4k movies".
        # The longer match ("4k movies") should win when both are
        # candidates.  BUT: "movies" is an EXACT match, so it wins
        # over any substring.
        # Try a substring that only matches longer:
        assert match_library_name("4k movies special", entries) == "4K Movies"

    def test_missing_returns_none(self, entries):
        assert match_library_name("unknown", entries) is None

    def test_empty_needle_returns_none(self, entries):
        assert match_library_name("", entries) is None

    def test_entry_without_name_skipped(self):
        entries = [{"name": None}, {"foo": "bar"}, {"name": "Movies"}]
        assert match_library_name("movies", entries) == "Movies"


# ---------------------------------------------------------------------------
# extract_config_line_count
# ---------------------------------------------------------------------------


class TestExtractConfigLineCount:
    def test_empty_content(self):
        assert extract_config_line_count("") == 0
        assert extract_config_line_count(None) == 0

    def test_no_config_block(self):
        content = "just some log lines\nwith no redacted config"
        assert extract_config_line_count(content) == 0

    def test_counts_yaml_lines(self):
        content = "\n".join(
            [
                "some noise",
                "[XXX] Redacted Config",
                "[XXX] [config.py:1] |  # comment line",
                "[XXX] [config.py:1] | libraries:",
                "[XXX] [config.py:1] |   Movies:",
                "[XXX] [config.py:1] | =====",
                "[XXX] [config.py:1] | ",
                "[XXX] [config.py:1] |   type: movie",
                "[XXX] some other line",
            ]
        )
        # libraries:, Movies:, type: movie => 3 (comment, divider, blank skipped)
        assert extract_config_line_count(content) == 3

    def test_stops_at_quickstart_marker(self):
        content = "\n".join(
            [
                "[XXX] Redacted Config",
                "[XXX] [config.py:1] | libraries:",
                "[XXX] [config.py:1] |   Quickstart run marker foo=bar",
                "[XXX] [config.py:1] |   type: movie",  # not counted
            ]
        )
        assert extract_config_line_count(content) == 1


# ---------------------------------------------------------------------------
# extract_library_counts -- priority rules
# ---------------------------------------------------------------------------


class TestExtractLibraryCounts:
    def test_empty_content(self):
        assert extract_library_counts("") == {}
        assert extract_library_counts(None) == {}

    def test_content_count_movies(self):
        content = "Processing Library: Movies\nContent Count: 500 movies"
        assert extract_library_counts(content) == {"Movies": {"items": 500, "type": "movie"}}

    def test_content_count_shows_with_episodes(self):
        content = "Processing Library: TV\nContent Count: 100 shows / 3000 episodes"
        assert extract_library_counts(content) == {"TV": {"items": 100, "episodes": 3000, "type": "show"}}

    def test_content_count_locks_against_lower_priority(self):
        # After Content Count sets 500, Items Found: 123 should be ignored.
        content = "\n".join(
            [
                "Processing Library: Movies",
                "Content Count: 500 movies",
                "Items Found: 123",
                "Movies Found: 456",
            ]
        )
        assert extract_library_counts(content) == {"Movies": {"items": 500, "type": "movie"}}

    def test_items_found_falls_back(self):
        content = "Processing Library: Movies\nItems Found: 100"
        # Type is None because no Movie/Show hint on the header line.
        assert extract_library_counts(content) == {"Movies": {"items": 100, "type": None}}

    def test_shows_and_episodes_merge_into_single_entry(self):
        content = "\n".join(
            [
                "Processing Library: TV",
                "Shows Found: 100",
                "Episodes Found: 3000",
            ]
        )
        assert extract_library_counts(content) == {"TV": {"items": 100, "type": "show", "episodes": 3000}}

    def test_direct_library_items_form(self):
        # "Library X has N items" doesn't need a preceding header.
        content = "Library Movies has 42 items"
        assert extract_library_counts(content) == {"Movies": {"items": 42}}

    def test_header_supports_arrow_form(self):
        # "Processing Library: Old -> New" -- keep the "New" part.
        content = "Processing Library: Old -> New\nItems Found: 5"
        assert extract_library_counts(content) == {"New": {"items": 5, "type": None}}

    def test_no_library_context_ignores_counts(self):
        # Items Found: without a preceding library header -- ignored.
        content = "Items Found: 100"
        assert extract_library_counts(content) == {}

    def test_header_type_hint_picked_up(self):
        # "Processing Library: Movies (Movie)" -- Type field on same line.
        content = "Processing Library: Movies (Movie)\nItems Found: 10"
        assert extract_library_counts(content) == {"Movies (Movie)": {"items": 10, "type": "movie"}}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
