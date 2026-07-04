"""Unit tests for :mod:`modules.logscan_content_extractors`.

Extracted alongside the PR that moved the pure content-parsing
helpers out of :class:`modules.logscan.LogscanAnalyzer`.

Each function is a pure ``content -> parsed value`` mapping so the
tests just poke small strings at them.
"""

from __future__ import annotations

import pytest

from modules.logscan_content_extractors import (
    DEFAULT_DIVIDER,
    contains_overlay_files,
    contains_overlay_path,
    detect_wsl_recommendation,
    extract_db_cache_value,
    extract_divider,
    extract_maintenance_times,
    extract_memory_value,
    extract_scheduled_run_time,
)

# ---------------------------------------------------------------------------
# extract_memory_value / extract_db_cache_value share a helper -- tested here
# because the boundaries are worth locking down.
# ---------------------------------------------------------------------------


class TestExtractMemoryValue:
    def test_gb_is_passthrough(self):
        assert extract_memory_value("Memory: 8 GB") == 8.0

    def test_mb_divides_by_1024(self):
        assert extract_memory_value("Memory: 4096 MB") == pytest.approx(4.0)

    def test_tb_multiplies_by_1024(self):
        assert extract_memory_value("Memory: 1 TB") == pytest.approx(1024.0)

    def test_units_are_case_insensitive(self):
        assert extract_memory_value("Memory: 8 gb") == 8.0
        assert extract_memory_value("Memory: 4096 mB") == pytest.approx(4.0)

    def test_decimal_values_are_preserved(self):
        assert extract_memory_value("Memory: 15.6 GB") == pytest.approx(15.6)

    def test_missing_label_returns_none(self):
        assert extract_memory_value("nothing to see here") is None

    def test_unrecognized_unit_returns_none(self):
        assert extract_memory_value("Memory: 5 PB") is None


class TestExtractDbCacheValue:
    def test_gb_is_passthrough(self):
        assert extract_db_cache_value("Plex DB cache setting: 2 GB") == 2.0

    def test_mb_divides_by_1024(self):
        assert extract_db_cache_value("Plex DB cache setting: 512 MB") == pytest.approx(0.5)

    def test_missing_label_returns_none(self):
        assert extract_db_cache_value("Memory: 8 GB") is None


# ---------------------------------------------------------------------------
# extract_divider (supports both KOMETA_ and legacy PMM_ names)
# ---------------------------------------------------------------------------


class TestExtractDivider:
    def test_kometa_divider(self):
        assert extract_divider('--divider (KOMETA_DIVIDER): "="') == "="

    def test_pmm_legacy_divider(self):
        assert extract_divider('--divider (PMM_DIVIDER): "|"') == "|"

    def test_default_when_missing(self):
        assert extract_divider("nothing here") == DEFAULT_DIVIDER

    def test_custom_fallback(self):
        assert extract_divider("nothing", fallback="*") == "*"

    def test_kometa_preferred_over_pmm_when_both_present(self):
        # KOMETA pattern is tried first; the divider from that line wins.
        content = "\n".join(
            [
                '--divider (KOMETA_DIVIDER): "="',
                '--divider (PMM_DIVIDER): "|"',
            ]
        )
        assert extract_divider(content) == "="


# ---------------------------------------------------------------------------
# extract_scheduled_run_time
# ---------------------------------------------------------------------------


class TestExtractScheduledRunTime:
    def test_kometa_times(self):
        assert extract_scheduled_run_time("--times (KOMETA_TIMES): 03:00") == "03:00"

    def test_pmm_legacy_times(self):
        assert extract_scheduled_run_time("--times (PMM_TIMES): 04:30") == "04:30"

    def test_short_hour_form(self):
        assert extract_scheduled_run_time("--times (KOMETA_TIMES): 3:00") == "3:00"

    def test_missing_returns_none(self):
        assert extract_scheduled_run_time("nothing here") is None


# ---------------------------------------------------------------------------
# extract_maintenance_times
# ---------------------------------------------------------------------------


class TestExtractMaintenanceTimes:
    def test_present_returns_pair(self):
        content = "Scheduled maintenance running between 03:00 and 05:00"
        assert extract_maintenance_times(content) == ("03:00", "05:00")

    def test_missing_returns_pair_of_nones(self):
        assert extract_maintenance_times("nothing here") == (None, None)

    def test_ignores_similar_but_wrong_lines(self):
        # "Scheduled maintenance" without "running between" doesn't match.
        assert extract_maintenance_times("Scheduled maintenance is happening") == (None, None)


# ---------------------------------------------------------------------------
# contains_overlay_*
# ---------------------------------------------------------------------------


class TestContainsOverlayPath:
    def test_matches_yaml_key(self):
        assert contains_overlay_path("overlay_path: /foo/bar") is True

    def test_case_insensitive(self):
        assert contains_overlay_path("OVERLAY_PATH: /foo") is True

    def test_word_boundary_required(self):
        # Substring inside a bigger word shouldn't match.
        assert contains_overlay_path("no_overlay_path_here") is False

    def test_no_match(self):
        assert contains_overlay_path("nothing") is False


class TestContainsOverlayFiles:
    def test_matches_yaml_key(self):
        assert contains_overlay_files("overlay_files: something") is True

    def test_case_insensitive(self):
        assert contains_overlay_files("OVERLAY_FILES: x") is True

    def test_no_match(self):
        assert contains_overlay_files("nothing") is False


# ---------------------------------------------------------------------------
# detect_wsl_recommendation
# ---------------------------------------------------------------------------


class TestDetectWslRecommendation:
    def test_wsl_platform_triggers_advisory(self):
        result = detect_wsl_recommendation("Platform: Linux-WSL")
        assert result is not None
        assert "WSL MEMORY RECOMMENDATION" in result

    def test_wsl_platform_windows_variant(self):
        # Any -WSL suffix qualifies (Kometa emits several platform names).
        assert detect_wsl_recommendation("Platform: Ubuntu-WSL") is not None

    def test_non_wsl_platform_returns_none(self):
        assert detect_wsl_recommendation("Platform: Linux") is None
        assert detect_wsl_recommendation("Platform: Darwin") is None

    def test_missing_platform_returns_none(self):
        assert detect_wsl_recommendation("nothing here") is None


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
