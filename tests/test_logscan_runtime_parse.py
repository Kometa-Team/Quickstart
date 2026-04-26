from modules.logscan import LogscanAnalyzer


def test_parse_run_time_with_days():
    analyzer = LogscanAnalyzer()
    delta = analyzer._parse_run_time_from_line("Run Time: 1 day, 2:20:31")
    assert delta is not None
    assert int(delta.total_seconds()) == (1 * 24 * 3600) + (2 * 3600) + (20 * 60) + 31


def test_analyze_content_marks_complete_for_day_runtime():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |====================================================================================================|",
            "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |                                            Finished Run                                            |",
            "[2026-04-14 09:37:06,902] [kometa.py:522]             [INFO]     |   Start Time: 07:16:22 2026-04-13     Finished: 09:36:53 2026-04-14     Run Time: 1 day, 2:20:31   |",
            "[2026-04-14 09:37:06,902] [kometa.py:522]             [INFO]     |====================================================================================================|",
        ]
    )
    result = analyzer.analyze_content(content, include_people_scan=False)
    summary = result.get("summary")
    assert isinstance(summary, dict)
    assert summary.get("run_complete") is True
    assert summary.get("started_at") == "2026-04-13 07:16:22"
    assert summary.get("run_time_seconds") == (1 * 24 * 3600) + (2 * 3600) + (20 * 60) + 31


def test_library_runtime_does_not_become_finished_run_total():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-22 06:50:18,000] [metadata.py:100] [INFO] |                                      Finished Movies                                      |",
            "[2026-04-22 06:50:20,000] [metadata.py:100] [INFO] |                                      Run Time: 0:00:02                                     |",
        ]
    )

    analyzer.extract_last_lines(content)

    assert analyzer.run_time is None


def test_extract_progress_playlist_runtime_from_continuation_line():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-18 10:00:00,000] [kometa.py:803] [INFO] |                                            Playlists                                             |",
            "[2026-04-18 10:00:01,000] [kometa.py:1226] [INFO] |                               Finished Demo Playlist                                |",
            "Playlist Run Time: 0:00:05",
            "[2026-04-18 10:00:02,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
        ]
    )

    progress = analyzer.extract_progress(content, library_list=[{"name": "Movies", "type": "movie"}])
    assert progress.get("playlist_total_seconds") == 5
    assert progress.get("playlists_detected") is True


def test_extract_progress_playlist_runtime_when_logged_from_playlists_module():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-18 10:00:00,000] [playlists.py:100] [INFO] |                                            Playlists                                             |",
            "[2026-04-18 10:00:01,000] [playlists.py:222] [INFO] |                               Finished Demo Playlist                                |",
            "[2026-04-18 10:00:01,000] [playlists.py:222] [INFO] |                                    Playlist Run Time: 0:00:07                                    |",
            "[2026-04-18 10:00:02,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
        ]
    )

    progress = analyzer.extract_progress(content, library_list=[{"name": "Movies", "type": "movie"}])
    assert progress.get("playlist_total_seconds") == 7
    assert progress.get("playlists_detected") is True


def test_analyze_content_extracts_quickstart_maintenance_summary():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[Quickstart] Run marker: started=2026-04-18T10:00:00Z config=demo quickstart=1.0.0 branch=develop maintenance_markers=1",
            "[2026-04-18 10:10:00,000] [kometa.py:100] [INFO] | Resumed Work |",
            "[Quickstart] Maintenance marker: event=paused at=2026-04-18T10:05:00Z local_at=2026-04-18T10:05:00 window=01:00-02:00",
            "[Quickstart] Maintenance marker: event=resumed at=2026-04-18T10:10:00Z local_at=2026-04-18T10:10:00 window=01:00-02:00 paused_seconds=300",
            "[2026-04-18 10:15:00,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
            "[2026-04-18 10:15:00,000] [kometa.py:522] [INFO] |   Start Time: 10:00:00 2026-04-18     Finished: 10:15:00 2026-04-18     Run Time: 0:15:00   |",
        ]
    )

    result = analyzer.analyze_content(content, include_people_scan=False)
    summary = result.get("summary")

    assert isinstance(summary, dict)
    assert summary.get("run_complete") is True
    assert summary.get("maintenance_summary") == {
        "had_pause": True,
        "pause_count": 1,
        "pause_seconds": 300,
        "open_pause": False,
        "window": "01:00-02:00",
        "events": [
            {
                "event": "paused",
                "at": "2026-04-18T10:05:00Z",
                "local_at": "2026-04-18T10:05:00",
                "window": "01:00-02:00",
                "paused_seconds": None,
            },
            {
                "event": "resumed",
                "at": "2026-04-18T10:10:00Z",
                "local_at": "2026-04-18T10:10:00",
                "window": "01:00-02:00",
                "paused_seconds": 300,
            },
        ],
    }
    assert summary.get("quiet_period_summary") == {
        "longest_gap_seconds": 300,
        "longest_gap_started_at": "2026-04-18T10:10:00",
        "longest_gap_ended_at": "2026-04-18T10:15:00",
        "longest_gap_start_line": 2,
        "longest_gap_end_line": 5,
        "longest_gap_last_line": "[2026-04-18 10:10:00,000] [kometa.py:100] [INFO] | Resumed Work |",
        "longest_gap_first_line": "[2026-04-18 10:15:00,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
        "gaps_over_300": 1,
        "gaps_over_900": 0,
        "gaps_over_1800": 0,
        "longest_gap_maintenance_overlap": "none",
        "longest_unexplained_gap_seconds": 300,
        "longest_unexplained_gap_started_at": "2026-04-18T10:10:00",
        "longest_unexplained_gap_ended_at": "2026-04-18T10:15:00",
        "longest_unexplained_gap_start_line": 2,
        "longest_unexplained_gap_end_line": 5,
        "longest_unexplained_gap_last_line": "[2026-04-18 10:10:00,000] [kometa.py:100] [INFO] | Resumed Work |",
        "longest_unexplained_gap_first_line": "[2026-04-18 10:15:00,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
        "longest_unexplained_gap_maintenance_overlap": "none",
        "confirmed_maintenance_gaps_over_300": 0,
        "unexplained_gaps_over_300": 1,
        "notable_gaps": [
            {
                "gap_seconds": 300,
                "started_at": "2026-04-18T10:10:00",
                "ended_at": "2026-04-18T10:15:00",
                "start_line": 2,
                "end_line": 5,
                "last_line": "[2026-04-18 10:10:00,000] [kometa.py:100] [INFO] | Resumed Work |",
                "first_line": "[2026-04-18 10:15:00,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
                "maintenance_overlap": "none",
            }
        ],
    }


def test_analyze_content_marks_quiet_period_overlap_as_confirmed_when_gap_matches_maintenance():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[Quickstart] Run marker: started=2026-04-18T10:00:00Z config=demo quickstart=1.0.0 branch=develop maintenance_markers=1",
            "[2026-04-18 10:00:00,000] [kometa.py:100] [INFO] | Starting Run |",
            "[Quickstart] Maintenance marker: event=paused at=2026-04-18T10:05:00Z local_at=2026-04-18T10:05:00 window=01:00-02:00",
            "[Quickstart] Maintenance marker: event=resumed at=2026-04-18T10:20:00Z local_at=2026-04-18T10:20:00 window=01:00-02:00 paused_seconds=900",
            "[2026-04-18 10:20:00,000] [kometa.py:101] [INFO] | Resumed Work |",
            "[2026-04-18 10:25:00,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
            "[2026-04-18 10:25:00,000] [kometa.py:522] [INFO] |   Start Time: 10:00:00 2026-04-18     Finished: 10:25:00 2026-04-18     Run Time: 0:25:00   |",
        ]
    )

    result = analyzer.analyze_content(content, include_people_scan=False)
    quiet_summary = result["summary"]["quiet_period_summary"]

    assert quiet_summary["longest_gap_seconds"] == 1200
    assert quiet_summary["longest_gap_start_line"] == 2
    assert quiet_summary["longest_gap_end_line"] == 5
    assert quiet_summary["longest_unexplained_gap_seconds"] == 300
    assert quiet_summary["longest_unexplained_gap_start_line"] == 5
    assert quiet_summary["longest_unexplained_gap_end_line"] == 6
    assert quiet_summary["confirmed_maintenance_gaps_over_300"] == 1
    assert quiet_summary["unexplained_gaps_over_300"] == 1
    assert quiet_summary["gaps_over_300"] == 2
    assert quiet_summary["gaps_over_900"] == 1
    assert quiet_summary["longest_gap_maintenance_overlap"] == "confirmed"


def test_analyze_content_marks_historical_quiet_period_overlap_as_unknown_without_capability_marker():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-18 10:00:00,000] [kometa.py:100] [INFO] | Starting Run |",
            "[2026-04-18 10:20:00,000] [kometa.py:101] [INFO] | Working |",
            "[2026-04-18 10:25:00,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
            "[2026-04-18 10:25:00,000] [kometa.py:522] [INFO] |   Start Time: 10:00:00 2026-04-18     Finished: 10:25:00 2026-04-18     Run Time: 0:25:00   |",
        ]
    )

    result = analyzer.analyze_content(content, include_people_scan=False)
    quiet_summary = result["summary"]["quiet_period_summary"]

    assert quiet_summary["longest_gap_seconds"] == 1200
    assert quiet_summary["longest_gap_start_line"] == 1
    assert quiet_summary["longest_gap_end_line"] == 2
    assert quiet_summary["longest_unexplained_gap_seconds"] == 1200
    assert quiet_summary["unexplained_gaps_over_300"] == 2
    assert quiet_summary["gaps_over_300"] == 2
    assert quiet_summary["gaps_over_900"] == 1
    assert quiet_summary["longest_gap_maintenance_overlap"] == "unknown"
