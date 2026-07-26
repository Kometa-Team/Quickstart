"""Unit tests for :mod:`modules.logscan_finished_runs`.

Extracted alongside PR that moved the finished-run parsing helpers
out of ``modules.logscan.LogscanAnalyzer``.  These focused unit
tests verify the pure helpers directly; integration coverage via
``LogscanAnalyzer`` methods still lives in
``tests/test_logscan_runtime_parse.py``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from modules.logscan_finished_runs import (
    extract_finished_runs,
    extract_last_lines,
    extract_validation_summary,
    find_last_run_time_index,
    format_contiguous_lines,
    parse_final_run_metadata,
    parse_run_time_from_line,
)

# ---------------------------------------------------------------------------
# parse_run_time_from_line
# ---------------------------------------------------------------------------


class TestParseRunTimeFromLine:
    def test_hms_only(self):
        delta = parse_run_time_from_line("Run Time: 1:24:07")
        assert delta == timedelta(hours=1, minutes=24, seconds=7)

    def test_days_with_comma(self):
        delta = parse_run_time_from_line("Run Time: 1 day, 2:20:31")
        assert delta == timedelta(days=1, hours=2, minutes=20, seconds=31)

    def test_days_plural_with_comma(self):
        delta = parse_run_time_from_line("Run Time: 3 days, 4:05:06")
        assert delta == timedelta(days=3, hours=4, minutes=5, seconds=6)

    def test_days_without_comma(self):
        # Non-comma variant: "3 days 4:05:06" (space-separated)
        delta = parse_run_time_from_line("Run Time: 3 days 4:05:06")
        assert delta == timedelta(days=3, hours=4, minutes=5, seconds=6)

    def test_none_when_no_match(self):
        assert parse_run_time_from_line("Nothing to see here") is None

    def test_none_when_line_is_empty(self):
        assert parse_run_time_from_line("") is None

    def test_none_when_line_is_none(self):
        assert parse_run_time_from_line(None) is None

    def test_case_insensitive(self):
        assert parse_run_time_from_line("RUN TIME: 0:00:30") == timedelta(seconds=30)

    def test_ignores_surrounding_context(self):
        line = "[timestamp] [foo.py:1] [INFO] | Start Time: 08:00:00 Finished: 08:30:00 Run Time: 0:30:00 |"
        assert parse_run_time_from_line(line) == timedelta(minutes=30)


# ---------------------------------------------------------------------------
# extract_finished_runs
# ---------------------------------------------------------------------------


class TestExtractFinishedRuns:
    def test_two_line_pair(self):
        content = "\n".join(
            [
                "some noise",
                "|  Finished collections  |",
                "|   Run Time: 0:32:14   |",
                "more noise",
            ]
        )
        result = extract_finished_runs(content)
        # Combined line preserves the trailing pipes/spaces from each
        # regex capture; the parser doesn't post-normalize whitespace.
        assert len(result) == 1
        assert "collections" in result[0]
        assert "0:32:14" in result[0]
        assert " - " in result[0]

    def test_single_line_form(self):
        # Needs a following line so the loop's for i in range(len-1) reaches it.
        content = "|   Finished: 2024-11-08 03:15:22 Run Time: 1:24:07   |\ntrailing line"
        result = extract_finished_runs(content)
        assert len(result) == 1
        assert result[0].startswith("Finished at:")
        assert "2024-11-08 03:15:22" in result[0]
        assert "1:24:07" in result[0]

    def test_empty_input(self):
        assert extract_finished_runs("") == []

    def test_input_with_no_finished_lines(self):
        assert extract_finished_runs("hello\nworld\n") == []

    def test_multiple_pairs_preserve_order(self):
        content = "\n".join(
            [
                "|  Finished collections  |",
                "|   Run Time: 0:32:14   |",
                "|  Finished overlays  |",
                "|   Run Time: 0:12:03   |",
            ]
        )
        result = extract_finished_runs(content)
        assert len(result) == 2
        assert "collections" in result[0]
        assert "overlays" in result[1]


# ---------------------------------------------------------------------------
# extract_validation_summary
# ---------------------------------------------------------------------------


class TestExtractValidationSummary:
    def test_passed_validation_report_is_terminal(self):
        content = "\n".join(
            [
                "[2026-07-24 18:24:37,827] [kometa.py:441] [INFO] | Validation Report (full)",
                "[2026-07-24 18:24:38,100] [validator.py:100] [INFO] | Result: PASSED",
            ]
        )

        result = extract_validation_summary(content)

        assert result == {
            "validation_run": True,
            "validation_level": "full",
            "validation_result": "passed",
            "finished_at": "2026-07-24 18:24:38",
        }

    def test_passed_validation_report_preserves_warning_suffix(self):
        content = "\n".join(
            [
                "[2026-07-24 18:24:37,827] [validator.py:452] [INFO] | Validation Report (structure+schema)",
                "[2026-07-24 18:24:38,100] [validator.py:485] [INFO] | Result: PASSED with 2 warning(s)",
            ]
        )

        result = extract_validation_summary(content)

        assert result is not None
        assert result["validation_level"] == "structure+schema"
        assert result["validation_result"] == "passed with 2 warning(s)"

    def test_failed_validation_report_is_terminal(self):
        content = "\n".join(
            [
                "[2026-07-24 18:24:37,827] [kometa.py:441] [INFO] | Validation Report (structure)",
                "[2026-07-24 18:24:38,100] [validator.py:100] [INFO] | Result: FAILED",
            ]
        )

        result = extract_validation_summary(content)

        assert result is not None
        assert result["validation_level"] == "structure"
        assert result["validation_result"] == "failed"

    def test_validator_result_without_report_line_is_terminal(self):
        content = "\n".join(
            [
                "[2026-07-24 23:12:08,515] [validator.py:481] [INFO] |",
                "[2026-07-24 23:12:08,515] [validator.py:482] [INFO] | ===============================================================",
                "[2026-07-24 23:12:08,515] [validator.py:485] [INFO] | Result: FAILED",
                "[2026-07-24 23:12:08,516] [validator.py:486] [INFO] | ===============================================================",
            ]
        )

        result = extract_validation_summary(content)

        assert result is not None
        assert result["validation_run"] is True
        assert result["validation_level"] is None
        assert result["validation_result"] == "failed"
        assert result["finished_at"] == "2026-07-24 23:12:08"

    def test_validator_result_text_does_not_have_to_be_passed_or_failed(self):
        content = "\n".join(
            [
                "[2026-07-24 18:24:37,827] [validator.py:452] [INFO] | Validation Report (syntax)",
                "[2026-07-24 18:24:38,100] [validator.py:485] [INFO] | Result: SKIPPED",
            ]
        )

        result = extract_validation_summary(content)

        assert result is not None
        assert result["validation_result"] == "skipped"

    def test_incomplete_validation_report_without_result_is_not_terminal(self):
        content = "[2026-07-24 18:24:37,827] [kometa.py:441] [INFO] | Validation Report (syntax)"

        assert extract_validation_summary(content) is None


# ---------------------------------------------------------------------------
# find_last_run_time_index
# ---------------------------------------------------------------------------


class TestFindLastRunTimeIndex:
    def test_no_run_time_returns_none(self):
        idx, is_final = find_last_run_time_index(["some", "lines", "without"])
        assert idx is None and is_final is False

    def test_final_run_marker_on_same_line_as_finished(self):
        lines = [
            "some line",
            "Start Time: 08:00 Finished: 08:30 Run Time: 0:30:00",
        ]
        idx, is_final = find_last_run_time_index(lines)
        assert idx == 1 and is_final is True

    def test_final_run_marker_after_finished_run_header(self):
        lines = [
            "|  Finished Run  |",
            "|   Run Time: 0:30:00   |",
        ]
        idx, is_final = find_last_run_time_index(lines)
        assert idx == 1 and is_final is True

    def test_interim_run_time_is_fallback(self):
        # Per-phase Run Time: reports without a Finished Run banner
        # aren't the final-run marker.
        lines = [
            "|  Finished collections  |",
            "|   Run Time: 0:32:14   |",
        ]
        idx, is_final = find_last_run_time_index(lines)
        assert idx == 1 and is_final is False

    def test_final_marker_preferred_over_interim(self):
        # Interim Run Time: earlier in the log, final Run Time: at end.
        lines = [
            "|  Finished collections  |",
            "|   Run Time: 0:32:14   |",  # interim
            "|  Finished Run  |",
            "|   Run Time: 1:00:00   |",  # final
        ]
        idx, is_final = find_last_run_time_index(lines)
        assert idx == 3 and is_final is True


# ---------------------------------------------------------------------------
# parse_final_run_metadata
# ---------------------------------------------------------------------------


class TestParseFinalRunMetadata:
    def test_full_line_extracts_all_three(self):
        line = "[2024-11-08 03:15:22,000] Start Time: 08:00:00 Finished: 03:15:22 Run Time: 1:24:07"
        result = parse_final_run_metadata(line)
        assert result["run_time"] == timedelta(hours=1, minutes=24, seconds=7)
        assert result["started_at"] == "08:00:00"
        # Prefers the log timestamp over Finished: text
        assert result["finished_at"] == "2024-11-08 03:15:22"

    def test_finished_at_falls_back_when_no_log_timestamp(self):
        line = "Start Time: 08:00 Finished: 08:30 Run Time: 0:30:00"
        result = parse_final_run_metadata(line)
        assert result["finished_at"] == "08:30"

    def test_missing_run_time_omits_the_key(self):
        result = parse_final_run_metadata("Just some text with no run time")
        assert "run_time" not in result

    def test_missing_started_at_omits_the_key(self):
        result = parse_final_run_metadata("Finished: 08:30 Run Time: 0:30:00")
        assert "started_at" not in result

    def test_missing_all_returns_empty_dict(self):
        assert parse_final_run_metadata("nothing here") == {}


# ---------------------------------------------------------------------------
# extract_last_lines
# ---------------------------------------------------------------------------


class TestExtractLastLines:
    def test_returns_none_when_no_run_time(self):
        tail, metadata = extract_last_lines("just\nsome\nrandom\nlines\n")
        assert tail is None and metadata is None

    def test_final_run_populates_metadata(self):
        content = "\n".join(
            [
                "|  Finished Run  |",
                "|   Start Time: 07:16:22 2024-11-08     Finished: 09:36:53 2024-11-08     Run Time: 1 day, 2:20:31   |",
            ]
        )
        tail, metadata = extract_last_lines(content)
        assert tail is not None
        assert "Finished Run" in tail
        assert metadata is not None
        assert metadata["run_time"] == timedelta(days=1, hours=2, minutes=20, seconds=31)

    def test_interim_run_time_returns_tail_but_no_metadata(self):
        # Per-phase Run Time: with no Finished Run banner -- should
        # still return the tail block but with metadata=None so the
        # caller doesn't overwrite whole-run state.
        content = "\n".join(
            [
                "|  Finished Movies  |",
                "|   Run Time: 0:00:02   |",
            ]
        )
        tail, metadata = extract_last_lines(content)
        assert tail is not None
        assert metadata is None

    def test_metadata_none_when_run_time_regex_fails(self):
        # Final-run banner present but Run Time: is malformed --
        # metadata should still be None because we can't anchor the
        # whole-run state without a Run Time value.  (Matches the\n"
        # legacy behavior of ``if parsed_run_time and run_time_is_final:``.)
        content = "\n".join(
            [
                "|  Finished Run  |",
                "|   Run Time: garbage   |",
            ]
        )
        tail, metadata = extract_last_lines(content)
        assert tail is not None
        assert metadata is None


# ---------------------------------------------------------------------------
# format_contiguous_lines
# ---------------------------------------------------------------------------


class TestFormatContiguousLines:
    def test_single_line(self):
        assert format_contiguous_lines([5]) == "5"

    def test_two_consecutive(self):
        assert format_contiguous_lines([5, 6]) == "5-6"

    def test_two_non_consecutive(self):
        assert format_contiguous_lines([5, 8]) == "5, 8"

    def test_mixed_ranges_and_singletons(self):
        assert format_contiguous_lines([1, 2, 3, 5, 7, 8]) == "1-3, 5, 7-8"

    def test_all_consecutive(self):
        assert format_contiguous_lines([10, 11, 12, 13, 14]) == "10-14"

    def test_all_singletons(self):
        assert format_contiguous_lines([1, 3, 5, 7]) == "1, 3, 5, 7"

    def test_empty_input_raises(self):
        # Documented behavior -- caller in LogscanAnalyzer guards
        # against empty input.
        with pytest.raises(IndexError):
            format_contiguous_lines([])


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
