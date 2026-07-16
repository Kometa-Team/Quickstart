"""Unit tests for :mod:`modules.logscan_maintenance`.

Extracted alongside the PR that moved maintenance-marker and
quiet-period analysis out of :class:`modules.logscan.LogscanAnalyzer`.

The larger behavior is already covered by
``tests/test_logscan_runtime_parse.py`` and
``tests/test_logscan_endpoints.py`` -- those exercise the class
methods (now thin wrappers), so they lock in the extract's
byte-identical behavior.  These focused tests target the smaller
pure helpers plus edge cases that were previously buried.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from modules.logscan_maintenance import (
    _build_maintenance_intervals,
    _classify_gap_overlap,
    _empty_maintenance_summary,
    _empty_quiet_period_summary,
    _parse_maintenance_event_line,
    extract_maintenance_summary,
    extract_quickstart_marker,
    extract_quickstart_marker_capabilities,
    extract_quickstart_marker_fields,
    extract_quiet_period_summary,
    parse_log_timestamp,
)

# ---------------------------------------------------------------------------
# parse_log_timestamp
# ---------------------------------------------------------------------------


class TestParseLogTimestamp:
    def test_standard_timestamp(self):
        line = "[2024-01-15 08:30:45,123] [foo.py:1] [INFO] hello"
        ts = parse_log_timestamp(line)
        assert ts == datetime(2024, 1, 15, 8, 30, 45)

    def test_none_returns_none(self):
        assert parse_log_timestamp(None) is None

    def test_empty_returns_none(self):
        assert parse_log_timestamp("") is None

    def test_no_leading_bracket_returns_none(self):
        assert parse_log_timestamp("no timestamp here") is None

    def test_malformed_timestamp_returns_none(self):
        # Starts with [ but not a valid timestamp.
        assert parse_log_timestamp("[not a timestamp]") is None

    def test_unparseable_date_returns_none(self):
        # Well-formed pattern but impossible date -- shouldn't raise.
        assert parse_log_timestamp("[2024-13-45 08:30:45,123]") is None


# ---------------------------------------------------------------------------
# extract_quickstart_marker + fields + capabilities
# ---------------------------------------------------------------------------


class TestExtractQuickstartMarker:
    def test_present_returns_marker_line(self):
        content = "some log\n[Quickstart] Run marker: start_mode=current mode=analyze\nmore"
        result = extract_quickstart_marker(content)
        assert result == "[Quickstart] Run marker: start_mode=current mode=analyze"

    def test_missing_returns_none(self):
        assert extract_quickstart_marker("no marker here") is None

    def test_empty_returns_none(self):
        assert extract_quickstart_marker("") is None

    def test_none_returns_none(self):
        assert extract_quickstart_marker(None) is None


class TestExtractQuickstartMarkerFields:
    def test_extracts_kv_pairs(self):
        content = "[Quickstart] Run marker: start_mode=current mode=analyze foo=bar"
        fields = extract_quickstart_marker_fields(content)
        assert fields["mode"] == "analyze"
        assert fields["foo"] == "bar"

    def test_extracts_quickstart_version_fields(self):
        content = "[Quickstart] Run marker: quickstart=0.10.4-build302 branch=develop start_mode=current"
        fields = extract_quickstart_marker_fields(content)
        assert fields["quickstart"] == "0.10.4-build302"
        assert fields["branch"] == "develop"

    def test_valid_start_mode_kept(self):
        for mode in ("current", "recovery", "logged"):
            content = f"[Quickstart] Run marker: start_mode={mode}"
            assert extract_quickstart_marker_fields(content)["start_mode"] == mode

    def test_invalid_start_mode_coerced_to_empty(self):
        content = "[Quickstart] Run marker: start_mode=weird"
        assert extract_quickstart_marker_fields(content)["start_mode"] == ""

    def test_no_marker_returns_empty_dict(self):
        assert extract_quickstart_marker_fields("nothing") == {}


class TestExtractQuickstartMarkerCapabilities:
    def test_maintenance_markers_flag_set(self):
        content = "[Quickstart] Run marker: maintenance_markers=1 foo=bar"
        caps = extract_quickstart_marker_capabilities(content)
        assert caps["maintenance_markers"] is True

    def test_maintenance_markers_flag_unset(self):
        content = "[Quickstart] Run marker: maintenance_markers=0"
        assert extract_quickstart_marker_capabilities(content)["maintenance_markers"] is False

    def test_no_maintenance_markers_field_defaults_to_false(self):
        content = "[Quickstart] Run marker: foo=bar"
        assert extract_quickstart_marker_capabilities(content)["maintenance_markers"] is False

    def test_no_marker_returns_default_capabilities(self):
        caps = extract_quickstart_marker_capabilities("no marker")
        assert caps == {"maintenance_markers": False}


# ---------------------------------------------------------------------------
# _parse_maintenance_event_line
# ---------------------------------------------------------------------------


class TestParseMaintenanceEventLine:
    def test_full_line_extracts_all_fields(self):
        line = "[Quickstart] Maintenance marker: event=paused at=2024-01-15T08:30:00Z local_at=2024-01-15T00:30:00 window=01:00-02:00 paused_seconds=300"
        parsed = _parse_maintenance_event_line(line)
        assert parsed is not None
        assert parsed["event"] == "paused"
        assert parsed["at"] == "2024-01-15T08:30:00Z"
        assert parsed["local_at"] == "2024-01-15T00:30:00"
        assert parsed["window"] == "01:00-02:00"
        assert parsed["paused_seconds"] == 300

    def test_minimal_line_matches_optional_fields_none(self):
        line = "[Quickstart] Maintenance marker: event=resumed at=2024-01-15T09:30:00Z"
        parsed = _parse_maintenance_event_line(line)
        assert parsed is not None
        assert parsed["event"] == "resumed"
        assert parsed["local_at"] is None
        assert parsed["window"] is None
        assert parsed["paused_seconds"] is None

    def test_non_marker_line_returns_none(self):
        assert _parse_maintenance_event_line("random log line") is None

    def test_malformed_timestamp_still_parses_event(self):
        # Even if the ISO timestamp doesn't parse, we should still
        # return the parsed dict with event_ts=None so the caller
        # can decide what to do.
        line = "[Quickstart] Maintenance marker: event=paused at=garbage"
        parsed = _parse_maintenance_event_line(line)
        assert parsed is not None
        assert parsed["event"] == "paused"
        assert parsed["event_ts"] is None


# ---------------------------------------------------------------------------
# extract_maintenance_summary
# ---------------------------------------------------------------------------


class TestExtractMaintenanceSummary:
    def test_empty_content_returns_defaults(self):
        assert extract_maintenance_summary("") == _empty_maintenance_summary()

    def test_none_content_returns_defaults(self):
        assert extract_maintenance_summary(None) == _empty_maintenance_summary()

    def test_no_markers_returns_defaults(self):
        assert extract_maintenance_summary("nothing here") == _empty_maintenance_summary()

    def test_pause_resume_pair(self):
        content = "\n".join(
            [
                "[Quickstart] Maintenance marker: event=paused at=2024-01-15T08:30:00Z local_at=2024-01-15T00:30:00 window=01:00-02:00",
                "[Quickstart] Maintenance marker: event=resumed at=2024-01-15T09:30:00Z local_at=2024-01-15T01:30:00 paused_seconds=3600",
            ]
        )
        summary = extract_maintenance_summary(content)
        assert summary["had_pause"] is True
        assert summary["pause_count"] == 1
        assert summary["pause_seconds"] == 3600
        assert summary["open_pause"] is False
        assert summary["window"] == "01:00-02:00"
        assert len(summary["events"]) == 2

    def test_paused_seconds_derived_when_missing(self):
        # Paired pause/resume without paused_seconds on the resume;
        # we should compute it from the timestamps (3600s here).
        content = "\n".join(
            [
                "[Quickstart] Maintenance marker: event=paused at=2024-01-15T08:00:00Z",
                "[Quickstart] Maintenance marker: event=resumed at=2024-01-15T09:00:00Z",
            ]
        )
        summary = extract_maintenance_summary(content)
        assert summary["pause_seconds"] == 3600

    def test_open_pause_flagged(self):
        content = "[Quickstart] Maintenance marker: event=paused at=2024-01-15T08:30:00Z window=01:00-02:00"
        summary = extract_maintenance_summary(content)
        assert summary["open_pause"] is True
        assert summary["had_pause"] is True
        assert summary["window"] == "01:00-02:00"


# ---------------------------------------------------------------------------
# _build_maintenance_intervals
# ---------------------------------------------------------------------------


class TestBuildMaintenanceIntervals:
    def test_empty_events(self):
        assert _build_maintenance_intervals([]) == []

    def test_matched_pair(self):
        events = [
            {"event": "paused", "local_at": "2024-01-15T00:30:00"},
            {"event": "resumed", "local_at": "2024-01-15T01:30:00"},
        ]
        intervals = _build_maintenance_intervals(events)
        assert len(intervals) == 1
        assert intervals[0][0] == datetime(2024, 1, 15, 0, 30, 0)
        assert intervals[0][1] == datetime(2024, 1, 15, 1, 30, 0)

    def test_open_pause_produces_open_interval(self):
        events = [{"event": "paused", "local_at": "2024-01-15T00:30:00"}]
        intervals = _build_maintenance_intervals(events)
        assert len(intervals) == 1
        assert intervals[0][1] is None

    def test_missing_local_at_skipped(self):
        events = [
            {"event": "paused"},  # no local_at
            {"event": "resumed", "local_at": "2024-01-15T01:30:00"},
        ]
        assert _build_maintenance_intervals(events) == []

    def test_resume_without_pause_ignored(self):
        events = [{"event": "resumed", "local_at": "2024-01-15T01:30:00"}]
        assert _build_maintenance_intervals(events) == []


# ---------------------------------------------------------------------------
# _classify_gap_overlap
# ---------------------------------------------------------------------------


class TestClassifyGapOverlap:
    @pytest.fixture
    def intervals(self):
        return [
            (datetime(2024, 1, 15, 1, 0, 0), datetime(2024, 1, 15, 2, 0, 0)),
        ]

    def test_gap_fully_inside_maintenance_is_confirmed(self, intervals):
        result = _classify_gap_overlap(
            datetime(2024, 1, 15, 1, 15, 0),
            datetime(2024, 1, 15, 1, 45, 0),
            intervals,
            maintenance_supported=True,
        )
        assert result == "confirmed"

    def test_gap_before_maintenance_and_supported_is_none(self, intervals):
        result = _classify_gap_overlap(
            datetime(2024, 1, 15, 0, 0, 0),
            datetime(2024, 1, 15, 0, 30, 0),
            intervals,
            maintenance_supported=True,
        )
        assert result == "none"

    def test_gap_before_maintenance_and_unsupported_is_unknown(self, intervals):
        result = _classify_gap_overlap(
            datetime(2024, 1, 15, 0, 0, 0),
            datetime(2024, 1, 15, 0, 30, 0),
            intervals,
            maintenance_supported=False,
        )
        assert result == "unknown"

    def test_open_interval_matches_when_gap_ends_after_start(self):
        intervals = [(datetime(2024, 1, 15, 1, 0, 0), None)]
        result = _classify_gap_overlap(
            datetime(2024, 1, 15, 0, 30, 0),
            datetime(2024, 1, 15, 1, 30, 0),
            intervals,
            maintenance_supported=True,
        )
        assert result == "confirmed"


# ---------------------------------------------------------------------------
# extract_quiet_period_summary
# ---------------------------------------------------------------------------


class TestExtractQuietPeriodSummary:
    def test_empty_content_returns_defaults(self):
        assert extract_quiet_period_summary("") == _empty_quiet_period_summary()

    def test_none_content_returns_defaults(self):
        assert extract_quiet_period_summary(None) == _empty_quiet_period_summary()

    def test_less_than_two_timestamps_returns_defaults(self):
        # One timestamped line -- no pairs to compute gaps from.
        content = "[2024-01-15 08:30:00,000] [x.py:1] [INFO] only one"
        summary = extract_quiet_period_summary(content)
        assert summary["longest_gap_seconds"] == 0
        assert summary["notable_gaps"] == []

    def test_short_gap_not_notable(self):
        # 60-second gap -- below 300s threshold, not notable.
        content = "\n".join(
            [
                "[2024-01-15 08:30:00,000] [x.py:1] [INFO] first",
                "[2024-01-15 08:31:00,000] [x.py:1] [INFO] second",
            ]
        )
        summary = extract_quiet_period_summary(content)
        assert summary["longest_gap_seconds"] == 60
        assert summary["notable_gaps"] == []
        assert summary["gaps_over_300"] == 0

    def test_large_gap_bucketed_correctly(self):
        # 20-minute gap should count in over-300, over-900 buckets
        # (not over-1800).
        content = "\n".join(
            [
                "[2024-01-15 08:00:00,000] [x.py:1] [INFO] first",
                "[2024-01-15 08:20:00,000] [x.py:1] [INFO] second",
            ]
        )
        summary = extract_quiet_period_summary(content)
        assert summary["longest_gap_seconds"] == 1200
        assert summary["gaps_over_300"] == 1
        assert summary["gaps_over_900"] == 1
        assert summary["gaps_over_1800"] == 0
        assert len(summary["notable_gaps"]) == 1

    def test_gap_overlaps_maintenance_confirmed(self):
        # 5-hour gap and maintenance in the middle -- overlaps.
        # Also ensure the runtime advertised maintenance_markers=1
        # so the classification is deterministic.
        content = "\n".join(
            [
                "[Quickstart] Run marker: maintenance_markers=1",
                "[2024-01-15 00:00:00,000] [x.py:1] [INFO] start",
                "[2024-01-15 05:00:00,000] [x.py:1] [INFO] end",
            ]
        )
        maintenance = {
            "events": [
                {"event": "paused", "local_at": "2024-01-15T01:00:00"},
                {"event": "resumed", "local_at": "2024-01-15T02:00:00"},
            ]
        }
        summary = extract_quiet_period_summary(content, maintenance_summary=maintenance)
        assert summary["longest_gap_maintenance_overlap"] == "confirmed"
        assert summary["confirmed_maintenance_gaps_over_300"] == 1
        assert summary["unexplained_gaps_over_300"] == 0


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
