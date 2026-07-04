"""Unit tests for :mod:`modules.logscan_recommendations`.

Extracted alongside the PR that moved the system-tuning advisory
builders out of :class:`modules.logscan.LogscanAnalyzer`.  The
LogscanAnalyzer wrappers still delegate here; those wrapper
methods are covered indirectly by existing logscan tests.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest

from modules.logscan_recommendations import (
    db_cache_recommendation,
    format_time_value,
    maintenance_time_recommendation,
    memory_recommendation,
)

# ---------------------------------------------------------------------------
# format_time_value
# ---------------------------------------------------------------------------


class TestFormatTimeValue:
    def test_none_returns_na(self):
        assert format_time_value(None) == "N/A"

    def test_empty_string_returns_na(self):
        assert format_time_value("") == "N/A"

    def test_trims_leading_zero_from_hour(self):
        assert format_time_value(time(hour=8, minute=30)) == "8:30"

    def test_no_leading_zero_when_hour_is_double_digit(self):
        assert format_time_value(time(hour=14, minute=5)) == "14:05"

    def test_midnight_becomes_zero_prefixed_stripped(self):
        # 00:00 -> "00:00" -> starts with "0" -> "0:00"
        assert format_time_value(time(hour=0, minute=0)) == "0:00"


# ---------------------------------------------------------------------------
# db_cache_recommendation
# ---------------------------------------------------------------------------


class TestDbCacheRecommendation:
    def test_missing_both_values_returns_none(self):
        assert db_cache_recommendation(None, None) is None

    def test_missing_db_cache_returns_none(self):
        assert db_cache_recommendation(None, 8.0) is None

    def test_missing_total_memory_returns_none(self):
        assert db_cache_recommendation(2.0, None) is None

    def test_db_cache_equal_to_memory_flags_issue(self):
        result = db_cache_recommendation(8.0, 8.0)
        assert result is not None
        assert "PLEX DB CACHE ISSUE" in result
        assert "8.00 GB" in result

    def test_db_cache_greater_than_memory_flags_issue(self):
        result = db_cache_recommendation(16.0, 8.0)
        assert result is not None
        assert "PLEX DB CACHE ISSUE" in result

    def test_db_cache_below_one_gb_produces_advice(self):
        result = db_cache_recommendation(0.5, 8.0)
        assert result is not None
        assert "PLEX DB CACHE ADVICE" in result
        assert "0.50 GB" in result

    def test_reasonable_db_cache_returns_none(self):
        # 2GB cache vs 8GB memory: sensible, no advisory
        assert db_cache_recommendation(2.0, 8.0) is None


# ---------------------------------------------------------------------------
# memory_recommendation
# ---------------------------------------------------------------------------


class TestMemoryRecommendation:
    def test_missing_memory_returns_error_string(self):
        # Legacy behavior returns this string rather than None so that
        # make_recommendations can render it as-is.
        assert memory_recommendation(None, False) == "Error: Memory value not found in content."

    def test_under_4gb_with_overlays_targets_8gb(self):
        result = memory_recommendation(2.5, True)
        assert result is not None
        assert "less than 4 GB" in result
        assert "8GB of RAM" in result
        assert "with overlays" in result

    def test_under_4gb_without_overlays_targets_4gb(self):
        result = memory_recommendation(2.5, False)
        assert result is not None
        assert "less than 4 GB" in result
        assert "4GB of RAM" in result
        assert "without overlays" in result

    def test_between_4_and_8gb_with_overlays_targets_8gb(self):
        result = memory_recommendation(6.0, True)
        assert result is not None
        assert "less than 8 GB" in result
        assert "with overlays" in result

    def test_between_4_and_8gb_without_overlays_is_silent(self):
        # This is the "no advice needed" branch -- confirmed silent.
        assert memory_recommendation(6.0, False) is None

    def test_at_or_above_8gb_is_silent(self):
        assert memory_recommendation(8.0, True) is None
        assert memory_recommendation(16.0, False) is None


# ---------------------------------------------------------------------------
# maintenance_time_recommendation
# ---------------------------------------------------------------------------


class TestMaintenanceTimeRecommendation:
    def test_missing_kometa_time_returns_error_string(self):
        # Legacy behavior returns this string rather than None -- lets
        # make_recommendations render it as-is.
        result = maintenance_time_recommendation(None, "01:00", "02:00", timedelta(hours=1))
        assert result == "Error: Plex scheduled time is missing."

    def test_missing_maintenance_start_returns_none(self):
        # Can't compute anything without both maintenance times.
        result = maintenance_time_recommendation("00:00", None, "02:00", timedelta(hours=1))
        assert result is None

    def test_missing_maintenance_end_returns_none(self):
        result = maintenance_time_recommendation("00:00", "01:00", None, timedelta(hours=1))
        assert result is None

    def test_run_over_24_hours_wins_priority(self):
        # 25-hour run should always trigger the > 24 HOURS advisory
        # regardless of maintenance-window layout.
        result = maintenance_time_recommendation("00:00", "01:00", "02:00", timedelta(hours=25))
        assert result is not None
        assert "> 24 HOURS" in result

    def test_kometa_scheduled_inside_maintenance_window(self):
        # Kometa runs at 01:30 which is inside 01:00-02:00 window.
        result = maintenance_time_recommendation("01:30", "01:00", "02:00", timedelta(minutes=30))
        assert result is not None
        assert "KOMETA SCHEDULED TIME CONFLICT" in result

    def test_no_conflict_returns_none(self):
        # Kometa at 22:00, maintenance at 01:00-02:00, short run.
        # Should be a completely benign schedule.
        result = maintenance_time_recommendation("22:00", "01:00", "02:00", timedelta(minutes=15))
        assert result is None


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
